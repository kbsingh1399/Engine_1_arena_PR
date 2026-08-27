#!/usr/bin/env python3 -u
"""
================================================================================
WF20 ENSEMBLE ENGINE — S1 multi-concept universe x 4-model voting ensemble
================================================================================
Universe : 17 causal market concepts pooled (wf20_screen.py) — 407,983
           candidate trades, 2020-09..2026-08, 18 symbols, simulated with
           the canonical $35-1R tiered engine (+5R trailing runner, 0.08% RT).
Ensemble : LightGBM + XGBoost + CatBoost + sklearn-HistGBM  (voting = mean
           raw P(win)), isotonic-calibrated on the IS calibration band.
Protocol : identical strict 20-window walk-forward with zero-lookahead and
           fail-fast re-optimization (see wf20_autonomous.py header).

Zero-lookahead: for window k, training rows, the calibration band, and the
entire Optuna search operate ONLY on candidates strictly before window k.
The concept universe itself is frozen a priori (no per-window design changes
from OOS data).
================================================================================
"""
import os, sys, gc, json, time, warnings
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
warnings.filterwarnings('ignore')
os.environ.update({k: "1" for k in [
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"
]})

from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd
import lightgbm as lgb
from xgboost import XGBClassifier
from catboost import CatBoostClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
import optuna

optuna.logging.set_verbosity(optuna.logging.WARNING)

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from strategy_engine import (  # noqa: E402
    simulate_portfolio_concurrency, regime_alignment,
    ALL_18_SYMBOLS, CAP, RSK, ATR_EPSILON,
)
import wf20_screen as scr  # MTF_COLS  # noqa: E402
import wf20_autonomous as wfa  # reuse: WINDOWS, gates, splits, metrics, report bits

WINDOWS = wfa.WINDOWS
TROI, TDD, TWR = wfa.TROI, wfa.TDD, wfa.TWR
MINTR, MAXTR = wfa.MINTR, wfa.MAXTR
MAX_CONCURRENT = 2
MAX_ROUNDS = 4
OPTUNA_TRIALS = 120
OPTUNA_SEED = 42
TRAIN_TAIL = 25000          # max IS rows for model training (recency-capped)
HALF_LIFE_DAYS = wfa.HALF_LIFE_DAYS

RESULTS_DIR = SCRIPT_DIR / 'wf20_results'
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
UNI_PATH = wfa.CACHE_DIR / 'uni_pooled.parquet'


def log2(msg):
    print(f"[{datetime.now().strftime('%m-%d %H:%M:%S')}] {msg}", flush=True)


DEFAULT_PARAMS = {
    'p_long': 0.55, 'p_short': 0.55, 'skip_chop': 0,
    'lgbm_depth': 4, 'lgbm_lr': 0.03,
    'xgb_depth': 3, 'xgb_lr': 0.04,
    'cat_lr': 0.05, 'hgb_lr': 0.02,
}


# ── Data ────────────────────────────────────────────────────────────────────
def load_universe():
    uni = pd.read_parquet(UNI_PATH)
    uni['symbol_id'] = uni['symbol'].map(
        {s: i for i, s in enumerate(ALL_18_SYMBOLS)}).fillna(99).astype(np.int32)
    fcs = [c for c in wfa.CAUSAL_MODEL_FEATURES if c in uni.columns]
    fcs += [c for c in scr.MTF_COLS if c in uni.columns]
    fcs += ['concept', 'symbol_id']
    return uni, fcs


# ── Models ──────────────────────────────────────────────────────────────────
def _model_frame(tdf, fcs):
    return tdf[fcs].replace([np.inf, -np.inf], 0.0).fillna(0.0).astype(np.float32)


def recency_weights(df):
    t = np.asarray(df['entry_time'].to_numpy(), dtype='float64') / 86400e9
    return np.power(0.5, (t.max() - t) / HALF_LIFE_DAYS)


def make_models(p, fast=False):
    nlb = 60 if fast else 120
    nx = 50 if fast else 100
    nc = 120 if fast else 200
    nh = 120 if fast else 200
    m_lgb = lgb.LGBMClassifier(
        objective='binary', max_depth=int(p['lgbm_depth']),
        learning_rate=float(p['lgbm_lr']), n_estimators=nlb,
        random_state=42, n_jobs=2, verbose=-1, min_child_samples=20, max_bin=63)
    m_xgb = XGBClassifier(
        max_depth=int(p['xgb_depth']), learning_rate=float(p['xgb_lr']),
        n_estimators=nx, eval_metric='logloss', tree_method='hist',
        n_jobs=2, random_state=42, subsample=0.9, colsample_bytree=0.9)
    m_cat = CatBoostClassifier(
        iterations=nc, depth=4, learning_rate=float(p['cat_lr']),
        l2_leaf_reg=3.0, random_seed=42, thread_count=2, verbose=0,
        bootstrap_type='Bernoulli', subsample=0.9)
    m_hgb = HistGradientBoostingClassifier(
        learning_rate=float(p['hgb_lr']), max_iter=nh, max_leaf_nodes=31,
        min_samples_leaf=25, l2_regularization=1.0, random_state=42)
    return [m_lgb, m_xgb, m_cat, m_hgb]


def train_ensemble(train_df, fcs, p, fast=False):
    """Train the 4-model voting ensemble on IS rows (recency-weighted)."""
    if len(train_df) < 300 or train_df['label'].nunique() < 2:
        return None
    tail = train_df.tail(TRAIN_TAIL) if not fast else train_df.tail(12000)
    X = _model_frame(tail, fcs)
    y = tail['label'].to_numpy(np.int32)
    w = recency_weights(tail)
    models = make_models(p, fast=fast)
    for m in models:
        m.fit(X, y, sample_weight=w)
    return models


def ensemble_proba(models, fcs, tdf):
    X = _model_frame(tdf, fcs)
    return np.mean([m.predict_proba(X)[:, 1] for m in models], axis=0)


def fit_calibrator(models, fcs, cal_df):
    if cal_df is None or len(cal_df) < 60:
        return None
    p_e = ensemble_proba(models, fcs, cal_df)
    y = cal_df['label'].to_numpy(np.int32)
    if len(np.unique(y)) < 2:
        return None
    try:
        cal = IsotonicRegression(out_of_bounds='clip', y_min=0.0, y_max=1.0)
        cal.fit(p_e, y)
        thr = np.quantile(p_e, 0.75)
        top = y[p_e >= thr]
        if len(top) >= 10 and top.mean() > y.mean():
            return cal
    except Exception:
        pass
    return None


def score_candidates(models, fcs, tdf, cal):
    if tdf.empty:
        tdf = tdf.copy(); tdf['prob'] = 0.0
        return tdf
    if models is None:
        tdf = tdf.copy(); tdf['prob'] = 0.0
        return tdf
    p_e = ensemble_proba(models, fcs, tdf)
    if cal is not None:
        p_e = cal.predict(p_e)
    tdf = tdf.copy()
    tdf['prob'] = p_e
    return tdf


def apply_regime_gate(tdf, p):
    if tdf.empty:
        return tdf
    routed = tdf.copy()
    routed['route_score'] = routed['prob'] + 0.04 * regime_alignment(
        'S1_Liquidation', routed['regime'].to_numpy())
    if int(p.get('skip_chop', 0)) >= 1:
        routed = routed[routed['regime'] >= 1]
        if routed.empty:
            return routed
    thr = np.where(routed['direction'].to_numpy() == 1,
                   float(p['p_long']), float(p['p_short']))
    return routed[routed['route_score'].to_numpy() >= thr].sort_values('entry_time')


def window_metrics(sel):
    n = len(sel)
    if n == 0:
        return {'trades': 0, 'pnl': 0.0, 'roi': 0.0, 'wr': 0.0, 'dd': 0.0, 'passed': False}
    pnl = float(sel['net_pnl'].sum())
    roi = pnl / CAP * 100.0
    wr = float((sel['net_pnl'] > 0).mean() * 100.0)
    dd = max(wfa.closed_dd(sel['net_pnl'].to_numpy(), sel['exit_time'].to_numpy()),
             wfa.mtm_dd(sel))
    passed = (roi > TROI) and (dd < TDD) and (wr > TWR) and (n >= MINTR)
    return {'trades': int(n), 'pnl': round(pnl, 2), 'roi': round(roi, 2),
            'wr': round(wr, 2), 'dd': round(dd, 2), 'passed': bool(passed)}


def pipeline_select(uni, p, fcs, ws, we, is_df, fast=False):
    ws, we = pd.Timestamp(ws), pd.Timestamp(we)
    oos = uni[(uni['entry_time'] >= ws) & (uni['entry_time'] <= we)]
    train, calb, _ = wfa.is_split3(is_df, ws)
    models = None; cal = None
    if train is not None and len(train) >= 300:
        models = train_ensemble(train, fcs, p, fast=fast)
        if models is not None:
            cal = fit_calibrator(models, fcs, calb)
    scored = score_candidates(models, fcs, oos, cal)
    gated = apply_regime_gate(scored, p)
    sel = simulate_portfolio_concurrency(gated, max_concurrent=MAX_CONCURRENT).head(MAXTR)
    return sel


# ── Re-optimization (IS-only, fast 2-of-4 proxy for the objective) ─────────
def fast_proxy(models4, p, fcs, df):
    """Objective proxy: LGBM+XGB half of the ensemble (models[0], models[1])."""
    if models4 is None or df.empty:
        return df.assign(prob=0.0)
    X = _model_frame(df, fcs)
    pr = np.mean([models4[0].predict_proba(X)[:, 1], models4[1].predict_proba(X)[:, 1]], axis=0)
    out = df.copy(); out['prob'] = pr
    return out


def reoptimize(params, uni, fcs, ws, seed=OPTUNA_SEED, trials=OPTUNA_TRIALS):
    ws = pd.Timestamp(ws)

    def objective(trial):
        p = dict(params)
        p['p_long'] = trial.suggest_float('p_long', 0.45, 0.85)
        p['p_short'] = trial.suggest_float('p_short', 0.45, 0.85)
        p['skip_chop'] = trial.suggest_int('skip_chop', 0, 1)
        p['lgbm_depth'] = trial.suggest_int('lgbm_depth', 3, 6)
        p['lgbm_lr'] = trial.suggest_float('lgbm_lr', 0.01, 0.08)
        p['xgb_depth'] = trial.suggest_int('xgb_depth', 2, 5)
        p['xgb_lr'] = trial.suggest_float('xgb_lr', 0.02, 0.08)
        p['cat_lr'] = trial.suggest_float('cat_lr', 0.02, 0.10)
        p['hgb_lr'] = trial.suggest_float('hgb_lr', 0.01, 0.05)

        is_df = uni[uni['exit_time'] < ws]
        if len(is_df) < 500:
            return -1e9
        train, calb, ev = wfa.is_split3(is_df, ws)
        if train is None or len(ev) < MINTR or len(train) < 300:
            return -1e9
        # proxy = LGBM + XGB (fast half of the voting ensemble)
        t = train.tail(12000)
        X = _model_frame(t, fcs); y = t['label'].to_numpy(np.int32); w = recency_weights(t)
        m1 = lgb.LGBMClassifier(objective='binary', max_depth=int(p['lgbm_depth']),
                                learning_rate=float(p['lgbm_lr']), n_estimators=60,
                                random_state=42, n_jobs=2, verbose=-1,
                                min_child_samples=20, max_bin=63)
        m1.fit(X, y, sample_weight=w)
        m2 = XGBClassifier(max_depth=int(p['xgb_depth']), learning_rate=float(p['xgb_lr']),
                           n_estimators=50, eval_metric='logloss', tree_method='hist',
                           n_jobs=2, random_state=42, subsample=0.9, colsample_bytree=0.9)
        m2.fit(X, y, sample_weight=w)
        # calibrate the proxy on the cal band (kept only with real lift)
        cal = None
        if calb is not None and len(calb) >= 60:
            pe = ensemble_proba([m1, m2], fcs, calb)
            yy = calb['label'].to_numpy(np.int32)
            if len(np.unique(yy)) == 2:
                try:
                    c = IsotonicRegression(out_of_bounds='clip', y_min=0.0, y_max=1.0)
                    c.fit(pe, yy)
                    thr = np.quantile(pe, 0.75)
                    top = yy[pe >= thr]
                    if len(top) >= 10 and top.mean() > yy.mean():
                        cal = c
                except Exception:
                    pass
        Xev = _model_frame(ev, fcs)
        pr = (m1.predict_proba(Xev)[:, 1] + m2.predict_proba(Xev)[:, 1]) / 2.0
        if cal is not None:
            pr = cal.predict(pr)
        evc = ev.copy(); evc['prob'] = pr
        gated = apply_regime_gate(evc, p)
        sel = simulate_portfolio_concurrency(gated, max_concurrent=MAX_CONCURRENT).head(MAXTR)
        n = len(sel)
        if n < MINTR:
            return -1e9
        pnl = float(sel['net_pnl'].sum()); roi = pnl / CAP * 100.0
        wr = float((sel['net_pnl'] > 0).mean() * 100.0)
        dd = max(wfa.closed_dd(sel['net_pnl'].to_numpy(), sel['exit_time'].to_numpy()),
                 wfa.mtm_dd(sel))
        if wr >= 40.0 and dd <= 4.5 and roi > 20.0:
            return float(roi * (wr / 100.0) - max(0.0, dd - 3.9))
        return float(roi - 100.0)

    study = optuna.create_study(direction='maximize',
                                sampler=optuna.samplers.TPESampler(seed=seed))
    study.enqueue_trial({k: params[k] for k in DEFAULT_PARAMS})
    study.optimize(objective, n_trials=trials, catch=(ValueError,))
    if not study.trials or study.best_value <= -1e8:
        return dict(params)
    best = dict(params)
    best.update({k: v for k, v in study.best_params.items() if k in DEFAULT_PARAMS})
    return best


# ── Main loop (identical protocol to wf20_autonomous) ───────────────────────
def save_state(state):
    with open(RESULTS_DIR / 'wf20_ensemble_results.json', 'w') as f:
        json.dump(state, f, indent=2, default=str)


def write_ensemble_report(state):
    """Writes wf20_ensemble_report.md (keeps the V1 wf20_report.md intact)."""
    lines = [
        "# WF20 Ensemble Walk-Forward Report — S1_Liquidation (multi-concept universe)",
        "",
        f"- Generated: {state.get('finished', '')}",
        f"- **Final status: {state['final_status']}**",
        f"- Capital ${state['spec']['capital']:.0f}/acct, 1R=${state['spec']['risk_1r']:.0f}, "
        f"fees+slip {state['spec']['fee_rt']*100:.2f}% RT, "
        f"max {state['spec']['max_concurrent']} concurrent positions",
        f"- Gates: ROI > {state['spec']['gates']['roi']}%, MaxDD < {state['spec']['gates']['maxdd']}%, "
        f"WR > {state['spec']['gates']['winrate']}%, "
        f"{state['spec']['gates']['min_trades']}-{state['spec']['gates']['max_trades']} trades",
        f"- Universe: {state['spec']['universe']}",
        f"- Ensemble: {' + '.join(state['spec']['ensemble'])} (mean-vote, isotonic-calibrated)",
        "",
        "| # | Window | Trades | WR % | ROI % | MaxDD % | PnL $ | Pass |",
        "|---|--------|--------|------|-------|---------|-------|------|",
    ]
    for w in state['windows']:
        last = w['rounds'][-1]['metrics'] if w['rounds'] else {}
        lines.append(
            f"| {w['window']} | {w['start']} → {w['end']} | {last.get('trades','')} | "
            f"{last.get('wr','')} | {last.get('roi','')} | {last.get('dd','')} | "
            f"{last.get('pnl','')} | {'PASS' if w['passed'] else 'FAIL'} |")
    lines += ["", "## Final parameters", "```json",
              json.dumps(state.get('final_params', {}), indent=2), "```", ""]
    with open(RESULTS_DIR / 'wf20_ensemble_report.md', 'w') as f:
        f.write("\n".join(lines))


def main():
    t0 = time.time()
    log2("=" * 90)
    log2("WF20 ENSEMBLE ENGINE — multi-concept universe x 4-model voting ensemble")
    log2(f"Capital=${CAP:.0f}/acct | 1R=${RSK:.0f} | fees=0.08% RT | maxConc={MAX_CONCURRENT} | "
         f"gates: ROI>{TROI}% MaxDD<{TDD}% WR>{TWR}%")
    log2(f"models: LightGBM+XGBoost+CatBoost+HistGBM (mean-vote, isotonic-calibrated) | "
         f"maxRounds={MAX_ROUNDS} optunaTrials={OPTUNA_TRIALS}")
    log2("=" * 90)

    log2("loading pooled concept universe ...")
    uni, fcs = load_universe()
    log2(f"universe: {len(uni):,} candidates | features: {len(fcs)}")

    state = {
        'spec': {'capital': CAP, 'risk_1r': RSK, 'fee_rt': 0.0008,
                 'max_concurrent': MAX_CONCURRENT,
                 'gates': {'roi': TROI, 'maxdd': TDD, 'winrate': TWR,
                           'min_trades': MINTR, 'max_trades': MAXTR},
                 'windows': list(WINDOWS),
                 'universe': '17 causal concepts pooled (see wf20_screen.py)',
                 'ensemble': ['LightGBM', 'XGBoost', 'CatBoost', 'HistGBM']},
        'windows': [], 'final_status': 'running', 'started': str(datetime.now()),
    }

    params = dict(DEFAULT_PARAMS)

    for k, (ss, se) in enumerate(WINDOWS, 1):
        ws, we = pd.Timestamp(ss), pd.Timestamp(se)
        log2("-" * 90)
        log2(f"WINDOW {k}/20  ({ss} -> {se})")
        rounds = []
        passed_now = False

        for rnd in range(0, MAX_ROUNDS + 1):
            p = params
            is_df = uni[uni['exit_time'] < ws]
            if len(is_df) < 500:
                log2(f"  round {rnd}: INSUFFICIENT IN-SAMPLE DATA ({len(is_df)} < 500) — HALT")
                state['final_status'] = f'HALTED at window {k}: insufficient in-sample data'
                break
            t_r = time.time()
            sel = pipeline_select(uni, p, fcs, ws, we, is_df, fast=False)
            res = window_metrics(sel)
            verdict = 'PASS' if res['passed'] else 'FAIL'
            log2(f"  round {rnd}: trades={res['trades']:2d} WR={res['wr']:5.1f}% "
                 f"ROI={res['roi']:6.1f}% MaxDD={res['dd']:5.1f}% PnL=${res['pnl']:8.2f} "
                 f"({time.time()-t_r:.0f}s) -> {verdict}")
            rounds.append({'round': rnd, 'params': p, 'metrics': res, 'passed': res['passed']})

            if res['passed']:
                if rnd == 0:
                    passed_now = True
                    log2(f"  WINDOW {k} PASSED on baseline params")
                    break
                log2(f"  verifying no regression on windows 1..{k-1} with new params ...")
                regressed = None
                for j in range(1, k):
                    ws_j, we_j = pd.Timestamp(WINDOWS[j-1][0]), pd.Timestamp(WINDOWS[j-1][1])
                    is_j = uni[uni['exit_time'] < ws_j]
                    if len(is_j) < 500:
                        regressed = (j, {'note': 'insufficient IS'})
                        break
                    sel_j = pipeline_select(uni, p, fcs, ws_j, we_j, is_j, fast=False)
                    res_j = window_metrics(sel_j)
                    log2(f"    re-verify W{j:2d}: trades={res_j['trades']:2d} "
                         f"WR={res_j['wr']:5.1f}% ROI={res_j['roi']:6.1f}% "
                         f"MaxDD={res_j['dd']:5.1f}% -> {'PASS' if res_j['passed'] else 'FAIL'}")
                    if not res_j['passed']:
                        regressed = (j, res_j)
                        break
                if regressed is None:
                    passed_now = True
                    log2(f"  WINDOW {k} PASSED (round {rnd}) — prefix 1..{k-1} verified, no regression")
                    break
                log2(f"  REGRESSION at window {regressed[0]} — re-optimizing again")

            if rnd == MAX_ROUNDS:
                break
            log2(f"  FAIL-FAST: re-optimizing with IS data prior to {ss} only "
                 f"({len(is_df)} candidate trades) ...")
            t_r = time.time()
            seed = OPTUNA_SEED + (k - 1) * 1000 + rnd
            params = reoptimize(params, uni, fcs, ws, seed=seed)
            log2(f"  re-optimized in {time.time()-t_r:.0f}s -> "
                 f"pL={params['p_long']:.2f} pS={params['p_short']:.2f} "
                 f"chop={params['skip_chop']} d1={params['lgbm_depth']} lr1={params['lgbm_lr']:.3f} "
                 f"d2={params['xgb_depth']} lr2={params['xgb_lr']:.3f} "
                 f"cat={params['cat_lr']:.3f} hgb={params['hgb_lr']:.3f}")

        state['windows'].append({
            'window': k, 'start': ss, 'end': se, 'passed': passed_now, 'rounds': rounds,
        })
        save_state(state)

        if not passed_now:
            state['final_status'] = (f'HALTED at window {k} after {MAX_ROUNDS} '
                                     f're-optimization rounds — gates not met')
            log2("!" * 90)
            log2(f"HALT: window {k} failed after {MAX_ROUNDS} re-optimization rounds.")
            log2("Protocol requires every window to pass; stopping here (no skipping).")
            break

    if state['final_status'] == 'running':
        state['final_status'] = 'ALL 20 WINDOWS PASSED'
    state['finished'] = str(datetime.now())
    state['total_seconds'] = round(time.time() - t0, 1)
    state['final_params'] = params
    save_state(state)
    write_ensemble_report(state)
    log2("=" * 90)
    log2(f"FINAL STATUS: {state['final_status']}  ({state['total_seconds']:.0f}s total)")
    log2(f"Results: {RESULTS_DIR / 'wf20_ensemble_results.json'}")
    log2("=" * 90)


if __name__ == '__main__':
    main()
