#!/usr/bin/env python3 -u
"""
================================================================================
WF20 AUTONOMOUS WALK-FORWARD ENGINE — S1_Liquidation (Tree Cascade)
================================================================================
Implements the strict 20-window quarterly walk-forward protocol:

  Windows    : Q1-2021 .. Q4-2025 (20 sequential OOS quarters)
  Capital    : $5,000 per account (18 parallel asset accounts)
  1R         : $35.00 fixed (1 ATR initial stop sized to $35)
  Costs      : 0.08% round-trip fee + slippage
  Concurrency: max 2 open positions across the portfolio
  Exit       : +1.5R breakeven, +3R locks +1.8R, +5R activates 0.8R trailing
               runner (reuses strategy_engine.sim_tiered — identical to the
               repo's canonical S1 simulator)
  Gates      : ROI > 20.0%, MaxDD < 5.0%, WinRate > 40.0%, >= 6 trades

ZERO-LOOKAHEAD MANDATE
  For window k, ONLY data strictly prior to window k start is used for:
    - feature computation (all rolling/causal, via featurize_microstructure)
    - candidate trade simulation (entry at next bar open, exit path forward)
    - cascade training (LGBM stage-1 gate -> XGB stage-2 refiner)
    - hyperparameter/threshold optimization (Optuna objective evaluated on a
      trailing in-sample validation slice that ends before window k start)
  The OOS window is never touched until the strategy is frozen.
  Every Optuna trial regenerates candidate trades from raw bars with ITS OWN
  thresholds, so the search space is unbiased (no stale-candidate filtering).

FAIL-FAST RE-OPTIMIZATION LOOP
  1. Process windows strictly in order k = 1..20.
  2. Window k with current params:
       PASS  -> record, freeze, proceed to k+1.
       FAIL  -> HALT. Re-optimize params using ONLY pre-window-k data.
  3. After re-optimization, re-test window k. If it passes, re-verify that
     windows 1..k-1 ALL still pass with the new params (each retrained on its
     own IS prefix with the same frozen params). If any regresses,
     re-optimize again (IS-only for window k).
  4. Max MAX_ROUNDS re-optimizations per window; if exhausted, halt and
     report honestly. No window is ever skipped.
================================================================================
"""

import os, sys, gc, json, time, warnings, hashlib
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
from sklearn.isotonic import IsotonicRegression
import optuna

optuna.logging.set_verbosity(optuna.logging.WARNING)

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from strategy_engine import (  # noqa: E402
    load_symbol_data, featurize_microstructure,
    gen_trades_tiered, simulate_portfolio_concurrency,
    CAUSAL_MODEL_FEATURES, regime_alignment, REGIME_TREND,
    ALL_18_SYMBOLS, DATA_DIR, CAP, RSK, FEE_RT, ATR_EPSILON, log,
)

# ── Protocol constants (user spec) ──────────────────────────────────────────
WINDOWS = [
    ("2021-01-01", "2021-03-31"), ("2021-04-01", "2021-06-30"),
    ("2021-07-01", "2021-09-30"), ("2021-10-01", "2021-12-31"),
    ("2022-01-01", "2022-03-31"), ("2022-04-01", "2022-06-30"),
    ("2022-07-01", "2022-09-30"), ("2022-10-01", "2022-12-31"),
    ("2023-01-01", "2023-03-31"), ("2023-04-01", "2023-06-30"),
    ("2023-07-01", "2023-09-30"), ("2023-10-01", "2023-12-31"),
    ("2024-01-01", "2024-03-31"), ("2024-04-01", "2024-06-30"),
    ("2024-07-01", "2024-09-30"), ("2024-10-01", "2024-12-31"),
    ("2025-01-01", "2025-03-31"), ("2025-04-01", "2025-06-30"),
    ("2025-07-01", "2025-09-30"), ("2025-10-01", "2025-12-31"),
]
TROI, TDD, TWR = 20.0, 5.0, 40.0
MINTR, MAXTR = 6, 100
MAX_CONCURRENT = 2
MAX_ROUNDS = 4            # max re-optimizations per failing window
OPTUNA_TRIALS = 100
OPTUNA_SEED = 42
N_EST_LGBM, N_EST_XGB = 120, 100
HALF_LIFE_DAYS = 180.0   # recency weighting for training (IS-only)

CACHE_DIR = SCRIPT_DIR.parent / 'scratch' / 'wf20_cache'
RESULTS_DIR = SCRIPT_DIR / 'wf20_results'
CACHE_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def log2(msg):
    print(f"[{datetime.now().strftime('%m-%d %H:%M:%S')}] {msg}", flush=True)


# ── Defaults (= strategy_engine OPTUNA_DEFAULTS blended with the hardcoded
#    S1 signal constants from make_signal_s1) ────────────────────────────────
DEFAULT_PARAMS = {
    'pullback_threshold': 0.12,   # |p8| z-score pullback gate
    'liq_mult': 1.0,              # liquidation spike vs 100-bar mean
    'zc_gate': 0.05,              # CVD z-score confirmation gate
    'q1': 0.50,                   # cascade stage-1 gate
    'p_long': 0.55,               # entry gate p* for long signals
    'p_short': 0.55,              # entry gate p* for short signals
    'skip_chop': 0,               # 1 = trade only in trend/expansion regimes
    'lgbm_depth': 4,
    'lgbm_lr': 0.03,
    'xgb_depth': 3,
    'xgb_lr': 0.04,
}


# ── Phase A: raw per-symbol state (built once, cached to disk) ─────────────
def build_symbol_state(sym, br):
    """Load one symbol, featurize (causal), and reduce to raw arrays."""
    p = CACHE_DIR / f'state_{sym}.npz'
    if p.exists():
        z = np.load(p, allow_pickle=True)
        return {
            'ts': z['ts'], 'o': z['o'], 'h': z['h'], 'l': z['l'], 'c': z['c'],
            'atr': z['atr'], 'feats': z['feats'], 'fcs': list(z['fcs']),
            'mc': z['mc'], 'p8': z['p8'], 'llr': z['llr'], 'lsr': z['lsr'],
            'zc20': z['zc20'],
        }
    df = load_symbol_data(sym)
    if df.empty:
        return None
    dff = featurize_microstructure(df, br if sym != 'BTCUSDT' else None)
    fcs = [c for c in CAUSAL_MODEL_FEATURES if c in dff.columns]
    np.savez_compressed(
        p,
        ts=dff.index.values.astype('datetime64[ns]'),
        o=dff['Open'].to_numpy(np.float64), h=dff['High'].to_numpy(np.float64),
        l=dff['Low'].to_numpy(np.float64), c=dff['Close'].to_numpy(np.float64),
        atr=dff['atr'].to_numpy(np.float64),
        feats=dff[fcs].to_numpy(np.float32), fcs=np.array(fcs, dtype=object),
        mc=dff['mc'].to_numpy(np.int8), p8=dff['p8'].to_numpy(np.float32),
        llr=dff['liq_long_ratio'].to_numpy(np.float32),
        lsr=dff['liq_short_ratio'].to_numpy(np.float32),
        zc20=dff['zc20'].to_numpy(np.float32),
    )
    z = np.load(p, allow_pickle=True)
    return {
        'ts': z['ts'], 'o': z['o'], 'h': z['h'], 'l': z['l'], 'c': z['c'],
        'atr': z['atr'], 'feats': z['feats'], 'fcs': list(z['fcs']),
        'mc': z['mc'], 'p8': z['p8'], 'llr': z['llr'], 'lsr': z['lsr'],
        'zc20': z['zc20'],
    }


# ── Fast candidate generation from raw arrays (unbiased per threshold set) ─
def fast_candidates(sym_states, p, sym_filter=None):
    """Simulate S1 candidate trades for the whole history with thresholds p.

    Returns DataFrame: symbol, entry_time, exit_time, direction, net_pnl
    ($35 1R), r_multiple, label, mae_dollar, + causal feature columns at the
    signal bar. ``net_pnl/mae_dollar`` come straight from gen_trades_tiered.
    """
    pb, lm, zg = float(p['pullback_threshold']), float(p['liq_mult']), float(p['zc_gate'])
    rows = []
    for sym, st in sym_states.items():
        if sym_filter is not None and sym not in sym_filter:
            continue
        sig = np.zeros(len(st['mc']), dtype=np.int32)
        mcl, p8c, llr, lsr, zc = st['mc'], st['p8'], st['llr'], st['lsr'], st['zc20']
        ml = (mcl > 0) & (p8c < -pb) & ((llr > lm) | (zc > zg))
        ms = (mcl < 0) & (p8c > pb) & ((lsr > lm) | (zc < -zg))
        sig[ml] = 1; sig[ms] = -1
        res = gen_trades_tiered(st['h'], st['l'], st['c'], st['o'], st['atr'], sig)
        if not res:
            continue
        rr = np.asarray(res, dtype=np.float64)
        idx = rr[:, 0].astype(np.int64)
        n = len(st['ts'])
        entry_idx = np.minimum(idx + 1, n - 1)
        exit_idx = np.minimum(idx + 1 + rr[:, 5].astype(np.int64), n - 1)
        rec = pd.DataFrame({
            'symbol': np.repeat(sym, len(idx)),
            'entry_time': st['ts'][entry_idx],
            'exit_time': st['ts'][exit_idx],
            'direction': rr[:, 1].astype(np.int32),
            'net_pnl': rr[:, 2],
            'r_multiple': rr[:, 3],
            'label': rr[:, 4].astype(np.int32),
            'mae_dollar': np.clip(rr[:, 6], 0.0, RSK * 1.2),
        })
        for j, col in enumerate(st['fcs']):
            rec[col] = st['feats'][idx, j]
        rows.append(rec)
    if not rows:
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True)
    return out.replace([np.inf, -np.inf], 0.0).fillna(0.0)


def params_hash(params):
    """Candidate universes depend only on the signal thresholds."""
    s = json.dumps({k: params[k] for k in
                    ('pullback_threshold', 'liq_mult', 'zc_gate')}, sort_keys=True)
    return hashlib.md5(s.encode()).hexdigest()[:10]


def load_candidates(params, sym_states, rebuild=False):
    h = params_hash(params)
    p = CACHE_DIR / f'cand_{h}.parquet'
    if p.exists() and not rebuild:
        return pd.read_parquet(p)
    cand = fast_candidates(sym_states, params)
    cand.to_parquet(p)
    return cand


# ── In-sample split: train / calibration / evaluation bands (all < ws) ─────
def is_split3(is_df, ws):
    """Return (train, cal_band, eval_band), all strictly before window start.

    Preferred layout (needs ~4 months of IS):
      eval = [ws-120d, ws-60d)   <- objective evaluated here (untouched by cal)
      cal  = [ws-60d, ws)        <- isotonic calibration fit here
      train = everything before ws-120d
    Fallback (thin IS, e.g. window 1): single trailing 60/30/90d eval band,
    cal=None.  Final 70/30 positional split as last resort.
    """
    e1 = ws - pd.Timedelta(days=120)
    e0 = ws - pd.Timedelta(days=60)
    train = is_df[is_df['exit_time'] < e1]
    ev = is_df[(is_df['entry_time'] >= e1) & (is_df['exit_time'] < e0)]
    cal = is_df[(is_df['entry_time'] >= e0) & (is_df['exit_time'] < ws)]
    if len(train) >= 100 and len(ev) >= MINTR and len(cal) >= 30:
        return (train.sort_values('entry_time'),
                cal.sort_values('entry_time'),
                ev.sort_values('entry_time'))
    for val_days in (60, 30, 90):
        v0 = ws - pd.Timedelta(days=val_days)
        tr = is_df[is_df['exit_time'] < v0]
        vl = is_df[(is_df['entry_time'] >= v0) & (is_df['exit_time'] < ws)]
        if len(tr) >= 50 and len(vl) >= MINTR:
            return (tr.sort_values('entry_time'), None,
                    vl.sort_values('entry_time'))
    if len(is_df) >= 100:
        split = max(50, int(len(is_df) * 0.70))
        return (is_df.iloc[:split].sort_values('entry_time'), None,
                is_df.iloc[split:].sort_values('entry_time'))
    return None, None, None


def recency_weights(df):
    t = np.asarray(df['entry_time'].to_numpy(), dtype='float64') / 86400e9
    return np.power(0.5, (t.max() - t) / HALF_LIFE_DAYS)


def _model_frame(tdf, fcs):
    return tdf[fcs].replace([np.inf, -np.inf], 0.0).fillna(0.0).astype(np.float32)


# ── Tree cascade: LGBM stage-1 gate -> XGB stage-2 refiner ─────────────────
def train_cascade(train_df, fcs, p):
    y = train_df['label'].to_numpy(np.int32)
    if len(train_df) < 30 or len(np.unique(y)) < 2:
        return None
    w = recency_weights(train_df)
    X = _model_frame(train_df, fcs)
    m1 = lgb.LGBMClassifier(
        objective='binary', max_depth=int(p['lgbm_depth']),
        learning_rate=float(p['lgbm_lr']), n_estimators=N_EST_LGBM,
        random_state=42, n_jobs=2, verbose=-1,
        min_child_samples=20, max_bin=63,
    )
    m1.fit(X, y, sample_weight=w)
    p1_tr = m1.predict_proba(X)[:, 1]
    sub = train_df[p1_tr >= float(p['q1'])]
    m2 = None
    if len(sub) >= 30 and sub['label'].nunique() == 2:
        m2 = XGBClassifier(
            max_depth=int(p['xgb_depth']), learning_rate=float(p['xgb_lr']),
            n_estimators=N_EST_XGB, eval_metric='logloss', tree_method='hist',
            n_jobs=2, random_state=42, subsample=0.9, colsample_bytree=0.9,
        )
        m2.fit(_model_frame(sub, fcs), sub['label'].to_numpy(np.int32),
               sample_weight=recency_weights(sub))
    return (m1, m2)


def fit_calibrator(m1, cal_df, fcs):
    """Isotonic P(win) calibration fitted ONLY on the IS calibration band.
    Kept only if it demonstrates real top-slice lift over the base rate."""
    if cal_df is None or len(cal_df) < 40:
        return None
    p1 = m1.predict_proba(_model_frame(cal_df, fcs))[:, 1]
    y = cal_df['label'].to_numpy(np.int32)
    if len(np.unique(y)) < 2:
        return None
    try:
        cal = IsotonicRegression(out_of_bounds='clip', y_min=0.0, y_max=1.0)
        cal.fit(p1, y)
        thr = np.quantile(p1, 0.75)
        top = y[p1 >= thr]
        if len(top) >= 10 and top.mean() > y.mean():
            return cal
    except Exception:
        pass
    return None


def score_candidates(cascade, fcs, tdf, p, cal=None):
    if tdf.empty:
        tdf = tdf.copy()
        tdf['prob'] = 0.0
        return tdf
    if cascade is None:
        tdf = tdf.copy()
        tdf['prob'] = 0.0
        return tdf
    m1, m2 = cascade
    p1 = m1.predict_proba(_model_frame(tdf, fcs))[:, 1]
    if cal is not None:
        p1 = cal.predict(p1)
    score = p1.copy()
    if m2 is not None:
        mask = p1 >= float(p['q1'])
        if mask.any():
            p2 = m2.predict_proba(_model_frame(tdf[mask], fcs))[:, 1]
            score[mask] = 0.4 * p1[mask] + 0.6 * p2
        if (~mask).any():
            score[~mask] = p1[~mask] * 0.6   # cascade rejection discount
    tdf = tdf.copy()
    tdf['prob'] = score
    return tdf


def apply_regime_gate(tdf, p):
    """Causal regime routing (fixed constants, no tuning) + per-direction
    p* entry gate + optional chop-regime skip. All inputs known at bar close."""
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


# ── Metrics (fixed $35 1R sizing, conservative DD) ──────────────────────────
def closed_dd(pnls, times):
    if len(pnls) == 0:
        return 0.0
    eq = pd.Series(np.concatenate(([CAP], pnls.cumsum() + CAP)))
    peak = eq.cummax()
    return float(((peak - eq) / peak.clip(lower=1e-12) * 100.0).max())


def mtm_dd(trades):
    """Conservative drawdown including adverse excursion of open positions."""
    if trades.empty:
        return 0.0
    ordered = trades.sort_values(['entry_time', 'exit_time']).reset_index(drop=True)
    open_pos, equity, peak, worst = [], CAP, CAP, 0.0
    for row in ordered.itertuples():
        still = []
        for pos in sorted(open_pos, key=lambda x: x['exit_time']):
            if pos['exit_time'] < row.entry_time:
                equity += pos['net_pnl']; peak = max(peak, equity)
            else:
                still.append(pos)
        open_pos = still
        open_pos.append({'exit_time': row.exit_time, 'net_pnl': float(row.net_pnl),
                         'mae': min(max(0.0, float(row.mae_dollar)), RSK * 1.2)})
        trough = equity - sum(x['mae'] for x in open_pos)
        worst = max(worst, (peak - trough) / max(peak, 1e-12) * 100.0)
    for pos in sorted(open_pos, key=lambda x: x['exit_time']):
        equity += pos['net_pnl']; peak = max(peak, equity)
        trough = equity - sum(x['mae'] for x in open_pos if x['exit_time'] > pos['exit_time'])
        worst = max(worst, (peak - trough) / max(peak, 1e-12) * 100.0)
    return float(worst)


def window_metrics(sel):
    n = len(sel)
    if n == 0:
        return {'trades': 0, 'pnl': 0.0, 'roi': 0.0, 'wr': 0.0, 'dd': 0.0, 'passed': False}
    pnl = float(sel['net_pnl'].sum())
    roi = pnl / CAP * 100.0
    wr = float((sel['net_pnl'] > 0).mean() * 100.0)
    dd = max(closed_dd(sel['net_pnl'].to_numpy(), sel['exit_time'].to_numpy()), mtm_dd(sel))
    passed = (roi > TROI) and (dd < TDD) and (wr > TWR) and (n >= MINTR)
    return {'trades': int(n), 'pnl': round(pnl, 2), 'roi': round(roi, 2),
            'wr': round(wr, 2), 'dd': round(dd, 2), 'passed': bool(passed)}


def pipeline_select(cand, p, fcs, ws, we, is_df):
    """Full causal pipeline for one window: train cascade on the IS train
    band, calibrate P(win) on the IS calibration band, score OOS candidates,
    per-direction p* + regime gate, enforce concurrency, cap trades."""
    ws, we = pd.Timestamp(ws), pd.Timestamp(we)
    oos = cand[(cand['entry_time'] >= ws) & (cand['entry_time'] <= we)]
    train, calb, _ = is_split3(is_df, ws)
    cascade = None
    cal = None
    if train is not None and len(train) >= 30:
        cascade = train_cascade(train, fcs, p)
        if cascade is not None:
            cal = fit_calibrator(cascade[0], calb, fcs)
    scored = score_candidates(cascade, fcs, oos, p, cal)
    gated = apply_regime_gate(scored, p)
    sel = simulate_portfolio_concurrency(gated, max_concurrent=MAX_CONCURRENT).head(MAXTR)
    return sel


# ── In-sample-only re-optimization (Optuna, unbiased candidate regeneration)
def reoptimize(params, sym_states, fcs, ws, seed=OPTUNA_SEED, trials=OPTUNA_TRIALS):
    """Re-optimize using ONLY in-sample data strictly before window start ``ws``.

    - Fresh TPE seed per call (no degenerate re-discovery of the same point).
    - The current best param set is enqueued as trial 0 (warm start /
      continuation search).
    - Every trial regenerates candidate trades from raw bars with its own
      signal thresholds (unbiased search over the full threshold space).
    - Objective = fixed-$35 pipeline performance on the trailing 60-day IS
      validation band (a stable, pre-window proxy for the OOS gates).
    """
    ws = pd.Timestamp(ws)

    def objective(trial):
        p = dict(params)
        p['pullback_threshold'] = trial.suggest_float('pullback_threshold', 0.05, 0.35)
        p['liq_mult'] = trial.suggest_float('liq_mult', 0.6, 3.0)
        p['zc_gate'] = trial.suggest_float('zc_gate', 0.0, 0.40)
        p['q1'] = trial.suggest_float('q1', 0.35, 0.65)
        p['p_long'] = trial.suggest_float('p_long', 0.45, 0.85)
        p['p_short'] = trial.suggest_float('p_short', 0.45, 0.85)
        p['skip_chop'] = trial.suggest_int('skip_chop', 0, 1)
        p['lgbm_depth'] = trial.suggest_int('lgbm_depth', 3, 6)
        p['lgbm_lr'] = trial.suggest_float('lgbm_lr', 0.01, 0.08)
        p['xgb_depth'] = trial.suggest_int('xgb_depth', 2, 5)
        p['xgb_lr'] = trial.suggest_float('xgb_lr', 0.02, 0.08)

        cand = fast_candidates(sym_states, p)
        if cand.empty:
            return -1e9
        is_df = cand[cand['exit_time'] < ws]
        if len(is_df) < 60:
            return -1e9
        train_part, cal_part, ev_part = is_split3(is_df, ws)
        if train_part is None or len(ev_part) < MINTR or len(train_part) < 50:
            return -1e9
        cascade = train_cascade(train_part, fcs, p)
        if cascade is None:
            return -1e9
        cal = fit_calibrator(cascade[0], cal_part, fcs)
        scored = score_candidates(cascade, fcs, ev_part, p, cal)
        gated = apply_regime_gate(scored, p)
        sel = simulate_portfolio_concurrency(gated, max_concurrent=MAX_CONCURRENT).head(MAXTR)
        n = len(sel)
        if n < MINTR:
            return -1e9
        pnl = float(sel['net_pnl'].sum()); roi = pnl / CAP * 100.0
        wr = float((sel['net_pnl'] > 0).mean() * 100.0)
        dd = max(closed_dd(sel['net_pnl'].to_numpy(), sel['exit_time'].to_numpy()), mtm_dd(sel))
        # Gate-shaped score: pass-like configs score by quality, others lose 100
        if wr >= 40.0 and dd <= 4.5 and roi > 20.0:
            return float(roi * (wr / 100.0) - max(0.0, dd - 3.9))
        return float(roi - 100.0)

    study = optuna.create_study(direction='maximize',
                                sampler=optuna.samplers.TPESampler(seed=seed))
    # Warm start: evaluate the current best first, then explore.
    study.enqueue_trial({k: params[k] for k in DEFAULT_PARAMS})
    study.optimize(objective, n_trials=trials, catch=(ValueError,))
    if not study.trials or study.best_value <= -1e8:
        return dict(params)
    best = dict(params)
    best.update({k: v for k, v in study.best_params.items() if k in DEFAULT_PARAMS})
    return best


# ── Main loop ───────────────────────────────────────────────────────────────
def save_state(state):
    with open(RESULTS_DIR / 'wf20_results.json', 'w') as f:
        json.dump(state, f, indent=2, default=str)


def main():
    t0 = time.time()
    log2("=" * 90)
    log2("WF20 AUTONOMOUS WALK-FORWARD — S1_Liquidation TREE CASCADE (LGBM -> XGB)")
    log2(f"Capital=${CAP:.0f}/acct | 1R=${RSK:.0f} | fees={FEE_RT*100:.2f}% RT | "
         f"maxConc={MAX_CONCURRENT} | gates: ROI>{TROI}% MaxDD<{TDD}% WR>{TWR}%")
    log2(f"maxRounds={MAX_ROUNDS} | optunaTrials={OPTUNA_TRIALS}")
    log2("=" * 90)

    log2("Phase A: per-symbol causal feature state (cached) ...")
    btc = load_symbol_data('BTCUSDT')
    br = btc[['Close', 'CVD']].copy()
    br.columns = ['btc_Close', 'btc_CVD']
    sym_states = {}
    for i, sym in enumerate(ALL_18_SYMBOLS, 1):
        st = build_symbol_state(sym, br)
        if st is None:
            log2(f"  [{i:2d}/18] {sym}: NO DATA")
            continue
        sym_states[sym] = st
        log2(f"  [{i:2d}/18] {sym}: {len(st['ts']):,} bars")
        gc.collect()
    del btc, br
    fcs = list(next(iter(sym_states.values()))['fcs'])
    log2(f"Phase A done in {time.time()-t0:.0f}s | model features: {len(fcs)}")

    state = {
        'spec': {'capital': CAP, 'risk_1r': RSK, 'fee_rt': FEE_RT,
                 'max_concurrent': MAX_CONCURRENT,
                 'gates': {'roi': TROI, 'maxdd': TDD, 'winrate': TWR,
                           'min_trades': MINTR, 'max_trades': MAXTR},
                 'windows': list(WINDOWS)},
        'windows': [], 'final_status': 'running',
        'started': str(datetime.now()),
    }

    params = dict(DEFAULT_PARAMS)
    cand_cache = {}

    def get_cand(p):
        h = params_hash(p)
        if h not in cand_cache:
            cand_cache[h] = load_candidates(p, sym_states)
            gc.collect()
        return cand_cache[h]

    halted = False
    for k, (ss, se) in enumerate(WINDOWS, 1):
        ws, we = pd.Timestamp(ss), pd.Timestamp(se)
        log2("-" * 90)
        log2(f"WINDOW {k}/20  ({ss} -> {se})")
        rounds = []
        passed_now = False

        for rnd in range(0, MAX_ROUNDS + 1):
            p = params
            cand = get_cand(p)
            is_df = cand[cand['exit_time'] < ws]
            if len(is_df) < 60:
                log2(f"  round {rnd}: INSUFFICIENT IN-SAMPLE DATA ({len(is_df)} < 60) — HALT")
                state['final_status'] = f'HALTED at window {k}: insufficient in-sample data'
                halted = True
                break
            t_r = time.time()
            sel = pipeline_select(cand, p, fcs, ws, we, is_df)
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
                    is_j = cand[cand['exit_time'] < ws_j]
                    if len(is_j) < 60:
                        regressed = (j, {'note': 'insufficient IS'})
                        break
                    sel_j = pipeline_select(cand, p, fcs, ws_j, we_j, is_j)
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
            params = reoptimize(params, sym_states, fcs, ws, seed=seed)
            log2(f"  re-optimized in {time.time()-t_r:.0f}s -> "
                 f"pb={params['pullback_threshold']:.3f} liq={params['liq_mult']:.2f} "
                 f"zc={params['zc_gate']:.3f} q1={params['q1']:.2f} "
                 f"pL={params['p_long']:.2f} pS={params['p_short']:.2f} "
                 f"skipChop={params['skip_chop']} d1={params['lgbm_depth']} "
                 f"lr1={params['lgbm_lr']:.3f} d2={params['xgb_depth']} lr2={params['xgb_lr']:.3f}")

        state['windows'].append({
            'window': k, 'start': ss, 'end': se, 'passed': passed_now,
            'rounds': rounds,
        })
        save_state(state)

        if not passed_now:
            state['final_status'] = (f'HALTED at window {k} after {MAX_ROUNDS} '
                                     f're-optimization rounds — gates not met')
            halted = True
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
    write_report(state)
    log2("=" * 90)
    log2(f"FINAL STATUS: {state['final_status']}  ({state['total_seconds']:.0f}s total)")
    log2(f"Results: {RESULTS_DIR / 'wf20_results.json'}")
    log2("=" * 90)


def write_report(state):
    lines = [
        "# WF20 Autonomous Walk-Forward Report — S1_Liquidation",
        "",
        f"- Generated: {state.get('finished', '')}",
        f"- **Final status: {state['final_status']}**",
        f"- Capital ${state['spec']['capital']:.0f}/acct, 1R=${state['spec']['risk_1r']:.0f}, "
        f"fees+slip {state['spec']['fee_rt']*100:.2f}% RT, "
        f"max {state['spec']['max_concurrent']} concurrent positions",
        f"- Gates: ROI > {state['spec']['gates']['roi']}%, MaxDD < {state['spec']['gates']['maxdd']}%, "
        f"WR > {state['spec']['gates']['winrate']}%, "
        f"{state['spec']['gates']['min_trades']}-{state['spec']['gates']['max_trades']} trades",
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
    with open(RESULTS_DIR / 'wf20_report.md', 'w') as f:
        f.write("\n".join(lines))


if __name__ == '__main__':
    main()
