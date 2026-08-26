#!/usr/bin/env python3 -u
"""
================================================================================
AUTONOMOUS LOCAL QUANT OPTIMIZER & FAIL-FAST SEARCH
================================================================================
Iteratively tests and verifies 100% causal zero-lookahead ML models across
all 18 crypto assets and 20 walk-forward Out-Of-Sample (OOS) windows.
================================================================================
"""

import os, sys, gc, time, warnings
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

warnings.filterwarnings('ignore')
os.environ.update({k: "1" for k in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"]})

from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd
from numba import njit
import lightgbm as lgb

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = SCRIPT_DIR / 'binance_backtesting_data'
if not DATA_DIR.exists():
    DATA_DIR = PROJECT_ROOT / 'Engine_2' / 'binance_backtesting_data'

ALL_18_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
    "AVAXUSDT", "DOGEUSDT", "DOTUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT",
    "SUIUSDT", "TRXUSDT", "APTUSDT", "ARBUSDT", "BCHUSDT", "OPUSDT"
]

MONTHS = [
    ("2020-03-18", "2020-04-18"),  # OOS 01: Post-COVID Crash Recovery
    ("2020-11-07", "2020-12-07"),  # OOS 02: Early Bull Breakout
    ("2021-01-24", "2021-02-24"),  # OOS 03: Momentum Expansion
    ("2021-06-13", "2021-07-13"),  # OOS 04: Post-May 2021 Chop
    ("2021-10-29", "2021-11-29"),  # OOS 05: Double-Top ATH Blow-Off
    ("2022-02-08", "2022-03-08"),  # OOS 06: Early Bear Macro Shock
    ("2022-05-21", "2022-06-21"),  # OOS 07: Terra/Luna Liquidation Cascade
    ("2022-09-14", "2022-10-14"),  # OOS 08: Low-Vol Bear Compression
    ("2022-12-03", "2023-01-03"),  # OOS 09: Post-FTX Cycle Bottom
    ("2023-04-17", "2023-05-17"),  # OOS 10: Spring 2023 Bank Crisis Rebound
    ("2023-08-25", "2023-09-25"),  # OOS 11: Summer 2023 Grayscale Flush
    ("2023-11-10", "2023-12-10"),  # OOS 12: Pre-ETF Institutional Run-Up
    ("2024-02-19", "2024-03-19"),  # OOS 13: Spot ETF Inflow Squeeze
    ("2024-07-06", "2024-08-06"),  # OOS 14: Summer 2024 Yen Carry Flush
    ("2024-10-28", "2024-11-28"),  # OOS 15: Post-Election Expansion
    ("2025-01-15", "2025-02-15"),  # OOS 16: Altseason Rotation
    ("2025-05-03", "2025-06-03"),  # OOS 17: Mid-2025 Realignment Chop
    ("2025-09-22", "2025-10-22"),  # OOS 18: Late-2025 Macro Expansion
    ("2026-02-11", "2026-03-11"),  # OOS 19: Q1 2026 Structural Flow
    ("2026-06-09", "2026-07-09")   # OOS 20: Terminal Forward Horizon
]

CAP = 5000.0           # $5,000 isolated capital per account
RSK = 25.0            # 0.5% risk per trade (1R)
FEE_RT = 0.0008       # 0.08% round-trip taker fee + slippage
TP = 5.0              # 5R minimum target before activating trailing stop
TRA = 0.8             # 0.8R trailing distance
MAX_NOTIONAL = 50000.0
ATR_EPSILON = 1e-6

TROI = 20.0           # Target ROI > 20% per window (> $1,000 net profit)
TDD = 5.0             # Max Drawdown < 5.0% (< $250)
TWR = 40.0            # Win Rate > 40.0%
MINTR = 6             # Min trades per window
MAXTR = 50            # Max trades per window

def log(msg):
    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)
    except Exception:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg.encode('ascii', 'replace').decode('ascii')}", flush=True)

@njit(fastmath=True, nogil=True)
def sim(h, l, c, entry_idx, entry, atr, dr):
    if (not np.isfinite(atr)) or (not np.isfinite(entry)) or atr <= ATR_EPSILON or entry <= 0.0:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    n = len(c); sd = atr; td = TP * atr; trd = TRA * atr
    st = entry - sd if dr == 1 else entry + sd
    cs = st; bp = entry; ns = st
    mx = min(entry_idx + 288 + 1, n); ep = c[mx - 1]; bh = mx - 1 - entry_idx
    mae = 0.0
    for j in range(entry_idx + 1, mx):
        if dr == 1:
            ae = max(0.0, entry - l[j])
            if ae > mae: mae = ae
            if l[j] <= cs: ep = cs; bh = j - entry_idx; break
            if h[j] > bp: bp = h[j]
            if (bp - entry) >= td:
                ns = bp - trd
                if ns > cs: cs = ns
        else:
            ae = max(0.0, h[j] - entry)
            if ae > mae: mae = ae
            if h[j] >= cs: ep = cs; bh = j - entry_idx; break
            if l[j] < bp: bp = l[j]
            if (entry - bp) >= td:
                ns = bp + trd
                if ns < cs: cs = ns
    u = min(RSK / sd, MAX_NOTIONAL / entry)
    g = u * (ep - entry) if dr == 1 else u * (entry - ep)
    f = u * entry * FEE_RT / 2.0 + u * abs(ep) * FEE_RT / 2.0
    npnl = g - f; r = npnl / RSK; lb = 1.0 if npnl > 0 else 0.0
    mae_dollar = u * mae
    return npnl, r, lb, bh, mae_dollar

@njit(fastmath=True, nogil=True)
def gen_trades_numba(h, l, c, o, a, sig):
    n = len(c); results = []; i = 200; cd = 0
    while i < n - 100:
        if i >= cd:
            dr = sig[i]
            if dr != 0:
                entry = o[i + 1] if i + 1 < n else c[i]; av = a[i]
                if np.isfinite(av) and np.isfinite(entry) and av > ATR_EPSILON and entry > 0.0:
                    net, r, lb, bh, mae = sim(h, l, c, i, entry, av, int(dr))
                    results.append((i, dr, net, r, lb, bh, mae))
                    cd = i + bh + 2
        i += 1
    return results

def zs(s, w):
    m = s.rolling(w, min_periods=1).mean()
    std = s.rolling(w, min_periods=1).std().replace(0, 1e-10)
    return (s - m) / std

def load_data(sym):
    p = DATA_DIR / f'{sym}_15m_master_2020_2026.parquet'
    if not p.exists(): return pd.DataFrame()
    df = pd.read_parquet(p)
    df['ts'] = pd.to_datetime(df['datetime_utc'])
    df = df.sort_values('ts').drop_duplicates('ts', keep='first')
    return df.set_index('ts')

def featurize_advanced(df, br=None):
    if br is not None:
        cj = [c for c in br.columns if c not in df.columns]
        if cj: df = df.join(br[cj], how='left')
        if 'btc_CVD' in df.columns: df['btc_CVD'] = df['btc_CVD'].ffill().fillna(0)

    atrs = df['atr_14'].replace(0, 1e-10)
    df['atr'] = df['atr_14']
    df['p8'] = (df['close'] - df['ema_8']) / atrs
    df['p21'] = (df['close'] - df['ema_21']) / atrs
    df['p50'] = (df['close'] - df['ema_50']) / atrs
    
    # Macro Trend & Regime
    df['macro_spread'] = (df['ema_200'] - df['ema_800']) / atrs
    df['fast_spread'] = (df['ema_8'] - df['ema_50']) / atrs
    df['mc'] = np.where(df['macro_spread'] > 0.3, 1, np.where(df['macro_spread'] < -0.3, -1, 0))
    df['vr'] = df['atr_14'] / df['atr_100'].replace(0, 1e-10)
    
    # Flow & CVD
    df['cvd_d'] = df['future_cvd_15m'].diff(3).fillna(0)
    df['spot_cvd_d'] = df['spot_cvd_15m'].diff(3).fillna(0)
    for k in [4, 10, 20]:
        df[f'zc{k}'] = zs(df['future_cvd_session'], k)
        df[f'zspot{k}'] = zs(df['spot_cvd_session'], k)
        
    # Liquidations
    df['liql'] = df['long_liq_usd'].abs().rolling(4, min_periods=1).sum()
    df['liqs'] = df['short_liq_usd'].abs().rolling(4, min_periods=1).sum()
    df['liqlm'] = df['liql'].rolling(50, min_periods=1).mean()
    df['liqsm'] = df['liqs'].rolling(50, min_periods=1).mean()
    df['liq_imb'] = (df['liql'] - df['liqs']) / (df['liql'] + df['liqs'] + 1e-6)
    
    # Open Interest & Flow Coherence
    oi = df['open_interest_usd'].ffill()
    df['zoi'] = zs(oi, 50)
    df['oid'] = oi.diff(4) / (oi.shift(4) + 1e-10)
    df['oicc'] = np.sign(df['oid'].fillna(0)) * np.sign(df['cvd_d'].fillna(0))
    
    # Microstructure & Depth
    df['fr'] = df['funding_rate_pct'].fillna(0)
    df['zfr'] = zs(df['fr'], 20)
    df['zls'] = zs(df['ls_ratio_global'].ffill(), 50)
    df['dist_poc'] = (df['close'] - df['fp_poc']) / atrs
    df['bsr'] = df['taker_buy_vol_btc'] / (df['taker_buy_vol_btc'] + df['taker_sell_vol_btc'] + 1e-6)
    df['vr5'] = df['volume_quote'] / (df['volume_sma9'].replace(0, 1e-10) + 1e-10)
    
    for c in df.columns:
        if c != 'ts' and df[c].dtype == np.float64:
            df[c] = df[c].astype(np.float32)
            
    return df.fillna(0).replace([np.inf, -np.inf], 0)

# ─────────────────────────────────────────────────────────────────────────────
# ADVANCED HIGH-CONVICTION SIGNAL GENERATORS
# ─────────────────────────────────────────────────────────────────────────────
def sig_s1_liquidation(df):
    out = np.zeros(len(df), dtype=np.int32)
    ll = df['liql'].values; ls = df['liqs'].values
    llm = df['liqlm'].values; lsm = df['liqsm'].values
    mc = df['mc'].values; p8 = df['p8'].values; zc20 = df['zc20'].values
    # Reversal off liquidation flush
    mask_l = (ll > llm * 1.5) & (p8 < -0.15) & (zc20 > -0.2)
    mask_s = (ls > lsm * 1.5) & (p8 > 0.15) & (zc20 < 0.2)
    out[mask_l] = 1; out[mask_s] = -1
    return out

def sig_s2_cvd_divergence(df):
    out = np.zeros(len(df), dtype=np.int32)
    mc = df['mc'].values; p8 = df['p8'].values
    zc20 = df['zc20'].values; zspot20 = df['zspot20'].values
    bsr = df['bsr'].values
    mask_l = (mc >= 0) & (p8 < -0.20) & (zc20 > 0.10) & (bsr > 0.52)
    mask_s = (mc <= 0) & (p8 > 0.20) & (zc20 < -0.10) & (bsr < 0.48)
    out[mask_l] = 1; out[mask_s] = -1
    return out

def sig_s3_trend_continuation(df):
    out = np.zeros(len(df), dtype=np.int32)
    mc = df['mc'].values; p8 = df['p8'].values; p50 = df['p50'].values
    vr = df['vr'].values
    mask_l = (mc > 0) & (p8 < -0.15) & (p50 > -0.8) & (vr > 0.8)
    mask_s = (mc < 0) & (p8 > 0.15) & (p50 < 0.8) & (vr > 0.8)
    out[mask_l] = 1; out[mask_s] = -1
    return out

def sig_s4_funding_mean_reversion(df):
    out = np.zeros(len(df), dtype=np.int32)
    zfr = df['zfr'].values; rsi = df['rsi_14'].values; p8 = df['p8'].values
    mask_l = (zfr < -1.2) & (rsi < 36) & (p8 < -0.35)
    mask_s = (zfr > 1.2) & (rsi > 64) & (p8 > 0.35)
    out[mask_l] = 1; out[mask_s] = -1
    return out

def sig_s5_vol_profile_breakout(df):
    out = np.zeros(len(df), dtype=np.int32)
    mc = df['mc'].values; dist_poc = df['dist_poc'].values
    vr5 = df['vr5'].values; zc20 = df['zc20'].values
    mask_l = (mc > 0) & (dist_poc > 0.1) & (dist_poc < 1.5) & (vr5 > 1.3) & (zc20 > 0.1)
    mask_s = (mc < 0) & (dist_poc < -0.1) & (dist_poc > -1.5) & (vr5 > 1.3) & (zc20 < -0.1)
    out[mask_l] = 1; out[mask_s] = -1
    return out

def sig_s6_oi_trap(df):
    out = np.zeros(len(df), dtype=np.int32)
    zoi = df['zoi'].values; oicc = df['oicc'].values; p8 = df['p8'].values
    mask_l = (zoi > 1.0) & (oicc < -0.2) & (p8 < -0.10)
    mask_s = (zoi > 1.0) & (oicc > 0.2) & (p8 > 0.10)
    out[mask_l] = 1; out[mask_s] = -1
    return out

STRATS = [
    ("S1_Liquidation", sig_s1_liquidation, "Liquidation Reversal"),
    ("S2_CVD_Momentum", sig_s2_cvd_divergence, "CVD Divergence"),
    ("S3_Trend_Follow", sig_s3_trend_continuation, "Trend Continuation"),
    ("S4_Mean_Reversion", sig_s4_funding_mean_reversion, "Funding Rate Mean Reversion"),
    ("S5_Vol_Breakout", sig_s5_vol_profile_breakout, "Volume Profile Breakout"),
    ("S6_OI_Coherence", sig_s6_oi_trap, "OI Delta Trap"),
]

def closed_equity_drawdown(trades):
    if trades.empty: return 0.0
    ordered = trades.sort_values("exit_time")
    pnl_by_exit = ordered.groupby("exit_time", sort=True)["net_pnl"].sum()
    equity = CAP + pnl_by_exit.cumsum()
    equity = pd.concat([pd.Series([CAP], dtype=float), equity.reset_index(drop=True)], ignore_index=True)
    peak = equity.cummax()
    return float(((peak - equity) / peak.clip(lower=1e-12) * 100.0).max())

def mark_to_market_drawdown(trades):
    if trades.empty or "mae_dollar" not in trades.columns: return closed_equity_drawdown(trades)
    equity = CAP; peak = CAP; worst_dd = 0.0
    for row in trades.sort_values("entry_time").itertuples():
        worst_equity = equity - max(0.0, float(row.mae_dollar))
        worst_dd = max(worst_dd, (peak - worst_equity) / max(peak, 1e-12) * 100.0)
        equity += float(row.net_pnl); peak = max(peak, equity)
    return float(worst_dd)

def main():
    t0 = time.time()
    log("=================================================================================")
    log("🚀 LOCAL CAUSAL ZERO-LOOKAHEAD OPTIMIZER RUNNING")
    log("=================================================================================")
    
    btc = load_data('BTCUSDT')
    br = btc[['close', 'future_cvd_session']].copy(); br.columns = ['btc_Close', 'btc_CVD']
    del btc; gc.collect()
    
    log("Loading and featurizing 18 assets...")
    sym_dfs = {}
    for sym in ALL_18_SYMBOLS:
        df = load_data(sym)
        if not df.empty:
            sym_dfs[sym] = featurize_advanced(df, br if sym != 'BTCUSDT' else None)
    log(f"Featurized {len(sym_dfs)} assets.")
    
    er = ['open', 'high', 'low', 'close', 'open_time_ms', 'close_time_ms', 'datetime_utc', 'symbol',
          'future_flow_source', 'spot_flow_source', 'poc_source', 'btc_Close', 'btc_CVD']
          
    strat_trades = {}
    for sname, sfn, desc in STRATS:
        trades = []
        for sym, dff in sym_dfs.items():
            h = dff['high'].values.astype(np.float64); l = dff['low'].values.astype(np.float64)
            c = dff['close'].values.astype(np.float64); o = dff['open'].values.astype(np.float64)
            a = dff['atr'].values.astype(np.float64); ts = dff.index.values
            fc = [col for col in dff.columns if col not in er and pd.api.types.is_numeric_dtype(dff[col])]
            fa = {col: dff[col].values.astype(np.float32) for col in fc}
            sg = sfn(dff)
            res = gen_trades_numba(h, l, c, o, a, sg)
            if res:
                rr = np.asarray(res, dtype=np.float64)
                idx = rr[:, 0].astype(np.int64); dr = rr[:, 1].astype(np.int32)
                net = rr[:, 2].copy(); bh = rr[:, 5].astype(np.int64); mae = rr[:, 6].copy()
                entry_idx = np.minimum(idx + 1, len(ts) - 1); exit_idx = np.minimum(idx + bh, len(ts) - 1)
                r_mult = rr[:, 3].copy(); label = rr[:, 4].astype(np.int32)
                
                tdf_sym = pd.DataFrame({
                    'symbol': sym, 'entry_time': ts[entry_idx], 'exit_time': ts[exit_idx],
                    'strategy': sname, 'direction': dr, 'entry_price': o[entry_idx],
                    'net_pnl': net, 'r_multiple': r_mult, 'label': label, 'mae_dollar': mae
                })
                for col in fc: tdf_sym[col] = fa[col][idx]
                trades.append(tdf_sym)
        if trades:
            strat_trades[sname] = pd.concat(trades, ignore_index=True).sort_values('entry_time')
            log(f"  - {sname:<22s}: {len(strat_trades[sname]):,} candidate trades")

    log("\nExecuting 120-Window Causal Zero-Lookahead Walk-Forward Backtest...")
    total_pass = 0
    for sname, _, _ in STRATS:
        log(f"\nEvaluating {sname}...")
        tdf_all = strat_trades.get(sname, pd.DataFrame())
        if tdf_all.empty: continue
        passes = 0
        for wi, (ss, se) in enumerate(MONTHS, 1):
            ws = pd.Timestamp(ss); we = pd.Timestamp(se)
            pdf = tdf_all[tdf_all['exit_time'] < ws].sort_values('entry_time')
            tdf = tdf_all[(tdf_all['entry_time'] >= ws) & (tdf_all['entry_time'] <= we)].sort_values('entry_time')
            if len(tdf) < MINTR:
                continue
                
            # Train LightGBM model on in-sample prior data
            excl = ['symbol', 'entry_time', 'exit_time', 'strategy', 'direction', 'entry_price',
                    'net_pnl', 'r_multiple', 'label', 'prob', 'adj_pnl', 'mae_dollar']
            fcs = [c for c in pdf.columns if c not in excl and pd.api.types.is_numeric_dtype(pdf[c])]
            
            if len(pdf) >= 20 and pdf['label'].sum() >= 2:
                train_slice = pdf.tail(3000)
                X_tr = train_slice[fcs].astype(np.float32); y_tr = train_slice['label'].astype(np.int32)
                p_cnt = y_tr.sum(); sw = max(0.1, float((len(y_tr) - p_cnt) / p_cnt)) if p_cnt > 0 else 1.0
                m = lgb.LGBMClassifier(max_depth=4, learning_rate=0.03, n_estimators=50, scale_pos_weight=sw,
                                       random_state=42, n_jobs=1, verbose=-1, min_child_samples=5)
                m.fit(X_tr, y_tr)
                
                # Calibrate threshold on in-sample validation (prior 60 days)
                vc = ws - pd.Timedelta(days=60)
                vdf = pdf[(pdf['entry_time'] >= vc) & (pdf['exit_time'] < ws)]
                if len(vdf) >= 10:
                    v_prob = m.predict_proba(vdf[fcs].astype(np.float32))[:, 1]
                    vdf_p = vdf.copy(); vdf_p['prob'] = v_prob
                    best_p = 0.50; best_sc = -1e9
                    for cand_p in np.arange(0.40, 0.85, 0.05):
                        sub = vdf_p[vdf_p['prob'] >= cand_p]
                        if len(sub) >= 4 and (sub['net_pnl'] > 0).mean() >= 0.35:
                            best_p = cand_p
                else:
                    best_p = 0.50
                    
                # Apply best_p CAUSALLY to OOS test window
                t_prob = m.predict_proba(tdf[fcs].astype(np.float32))[:, 1]
                tdf_eval = tdf.copy(); tdf_eval['prob'] = t_prob
                selected = tdf_eval[tdf_eval['prob'] >= best_p]
            else:
                selected = tdf.head(MAXTR)
                
            nt = len(selected)
            if nt < MINTR:
                selected = tdf.head(MINTR); nt = len(selected)
                
            nw = int((selected['net_pnl'] > 0).sum())
            wr = (nw / nt) * 100.0
            pnl = float(selected['net_pnl'].sum())
            roi = (pnl / CAP) * 100.0
            dd = closed_equity_drawdown(selected)
            mtm_dd = mark_to_market_drawdown(selected)
            max_dd = max(dd, mtm_dd)
            
            passed = (wr >= TWR) and (roi >= TROI) and (max_dd < TDD) and (nt >= MINTR)
            if passed:
                passes += 1
                total_pass += 1
            verdict = "PASS" if passed else "FAIL"
            log(f"  W{wi:2d} ({ss}->{se}): {verdict} | Tr={nt:2d} Wn={nw:2d} WR={wr:5.1f}% PnL=${pnl:7.2f} ROI={roi:5.1f}% MaxDD={max_dd:4.1f}%")
            
        log(f"Strategy {sname} Passes: {passes}/20")
        
    log(f"\n=================================================================================")
    log(f"TOTAL CAUSAL PASSES: {total_pass}/120 ({(total_pass/120)*100:.1f}%) in {time.time()-t0:.1f}s")
    log(f"=================================================================================")

if __name__ == '__main__':
    main()
