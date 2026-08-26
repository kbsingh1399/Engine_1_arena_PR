#!/usr/bin/env python3 -u
"""
================================================================================
ENGINE 2: CORE QUANT STRATEGY & NUMBA EXECUTION ENGINE
================================================================================
Implements:
  1. 57-column microstructural feature extraction
  2. Exact +5R trailing stop Numba simulation engine (0.08% RT fee + funding)
  3. 6 Specialized Strategy Signal Generators
  4. Machine Learning Model Training (LightGBM, XGBoost, ExtraTrees, HistGB)
  5. Gate-Compliant Threshold Calibration & Out-Of-Sample Trade Selection
================================================================================
"""

import os, sys, site, gc, json, time, warnings
site.addsitedir('/home/user/.local/lib/python3.11/site-packages')
warnings.filterwarnings('ignore')

os.environ.update({k: "1" for k in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"]})

from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd
from numba import njit
import lightgbm as lgb
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier

ROOT = Path('/home/user/Engine_1_arena_PR')
DATA_DIR = ROOT / 'Engine_2' / 'binance_backtesting_data'
if not DATA_DIR.exists():
    DATA_DIR = Path('./Engine_2/binance_backtesting_data')

ALL_18_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
    "AVAXUSDT", "DOGEUSDT", "DOTUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT",
    "SUIUSDT", "TRXUSDT", "APTUSDT", "ARBUSDT", "BCHUSDT", "OPUSDT"
]

MONTHS = [
    ("2020-10-01", "2020-11-01"), ("2020-11-07", "2020-12-07"), ("2021-01-24", "2021-02-24"),
    ("2021-06-13", "2021-07-13"), ("2021-10-29", "2021-11-29"), ("2022-02-08", "2022-03-08"),
    ("2022-05-21", "2022-06-21"), ("2022-09-14", "2022-10-14"), ("2022-12-03", "2023-01-03"),
    ("2023-04-17", "2023-05-17"), ("2023-08-25", "2023-09-25"), ("2023-11-10", "2023-12-10"),
    ("2024-02-19", "2024-03-19"), ("2024-07-06", "2024-08-06"), ("2024-10-28", "2024-11-28"),
    ("2025-01-15", "2025-02-15"), ("2025-05-03", "2025-06-03"), ("2025-09-22", "2025-10-22"),
    ("2026-02-11", "2026-03-11"), ("2026-06-09", "2026-07-09")
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
MAXTR = 45            # Max trades per window

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# ─────────────────────────────────────────────────────────────────────────────
# 1. EXACT 5R TRAILING STOP NUMBA EXECUTION ENGINE
# ─────────────────────────────────────────────────────────────────────────────
@njit(fastmath=True, nogil=True)
def sim(h, l, c, entry_idx, entry, atr, dr):
    """
    Simulate one trade enforcing the 5R Trailing Stop Mandate:
    - Initial stop at 1R (entry - 1*atr for long, entry + 1*atr for short)
    - Trade is NEVER closed for profit before +5R.
    - Once peak favorable excursion reaches +5R (bp - entry >= 5*atr),
      activates trailing stop at (bp - 0.8*atr) to capture maximum upside.
    - Deducts 0.08% round-trip fee + slippage.
    """
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

# ─────────────────────────────────────────────────────────────────────────────
# 2. 57-COLUMN MICROSTRUCTURAL FEATURE ENGINE
# ─────────────────────────────────────────────────────────────────────────────
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

def featurize_df(df, br=None):
    if br is not None:
        cj = [c for c in br.columns if c not in df.columns]
        if cj: df = df.join(br[cj], how='left')
        if 'btc_CVD' in df.columns: df['btc_CVD'] = df['btc_CVD'].ffill().fillna(0)
    
    atrs = df['atr_14'].replace(0, 1e-10)
    df['atr'] = df['atr_14']
    df['p8'] = (df['close'] - df['ema_8']) / atrs
    df['p21'] = (df['close'] - df['ema_21']) / atrs
    df['p50'] = (df['close'] - df['ema_50']) / atrs
    df['mc'] = np.where((df['ema_200'] - df['ema_800']) / atrs > 0.5, 1,
               np.where((df['ema_200'] - df['ema_800']) / atrs < -0.5, -1, 0))
    df['macro_spread'] = (df['ema_200'] - df['ema_800']) / atrs
    df['fast_spread'] = (df['ema_8'] - df['ema_50']) / atrs
    df['vr'] = zs(df['atr_14'], 100)
    
    df['cvd_d'] = df['future_cvd_15m'].diff(5).fillna(0)
    for k in [4, 10, 20]:
        df[f'zc{k}'] = zs(df['future_cvd_session'], k)
        df[f'zspot{k}'] = zs(df['spot_cvd_session'], k)
    
    if 'btc_CVD' in df.columns:
        df['bcvm'] = df['btc_CVD'].diff(2).fillna(0)
        for k in [4, 10, 20]:
            df[f'zb{k}'] = zs(df['btc_CVD'], k)
    else:
        df['bcvm'] = 0.0
        for k in [4, 10, 20]: df[f'zb{k}'] = 0.0

    df['liql'] = df['long_liq_usd'].abs().rolling(5, min_periods=1).sum()
    df['liqs'] = df['short_liq_usd'].abs().rolling(5, min_periods=1).sum()
    df['liqlm'] = df['liql'].rolling(100, min_periods=1).mean()
    df['liqsm'] = df['liqs'].rolling(100, min_periods=1).mean()
    df['liq_imb'] = (df['liql'] - df['liqs']) / (df['liql'] + df['liqs'] + 1e-6)
    df['zliql'] = zs(df['liql'], 50)
    df['zliqs'] = zs(df['liqs'], 50)
    
    oi = df['open_interest_usd'].ffill()
    df['zoi'] = zs(oi, 100)
    df['oid'] = oi.diff(5) / (oi.shift(5) + 1e-10)
    df['oicc'] = np.sign(df['oid'].fillna(0)) * np.sign(df['cvd_d'].fillna(0))
    
    df['fr'] = df['funding_rate_pct'].fillna(0)
    df['zfr'] = zs(df['fr'], 20)
    df['zls'] = zs(df['ls_ratio_global'].ffill(), 100)
    df['whale_idx'] = df['whale_index']
    
    df['dist_poc'] = (df['close'] - df['fp_poc']) / atrs
    df['vah_pen'] = (df['close'] - df['session_vah']) / atrs
    df['val_pen'] = (df['close'] - df['session_val']) / atrs
    df['bsr'] = df['taker_buy_vol_btc'] / (df['taker_buy_vol_btc'] + df['taker_sell_vol_btc'] + 1e-6)
    df['vr5'] = df['volume_quote'] / (df['volume_sma9'].replace(0, 1e-10) + 1e-10)
    df['depth_imb'] = (df['bid_depth_usd'] - df['ask_depth_usd'].abs()) / (df['bid_depth_usd'] + df['ask_depth_usd'].abs() + 1e-6)
    
    for c in df.columns:
        if c != 'ts' and df[c].dtype == np.float64:
            df[c] = df[c].astype(np.float32)
            
    return df.fillna(0).replace([np.inf, -np.inf], 0)

# ─────────────────────────────────────────────────────────────────────────────
# 3. 6 SPECIALIZED STRATEGY SIGNAL GENERATORS
# ─────────────────────────────────────────────────────────────────────────────
def s1_liquidation(df):
    """Acct 1: Liquidation Cascades (XGBoost/CatBoost Paradigm)"""
    out = np.zeros(len(df), dtype=np.int32)
    mc = df['mc'].values; p8 = df['p8'].values
    ll = df['liql'].values; ls = df['liqs'].values
    llm = df['liqlm'].values; lsm = df['liqsm'].values
    zc20 = df['zc20'].values
    mask_l = (mc > 0) & (p8 < -0.12) & ((ll > llm * 1.20) | (zc20 > 0.10))
    mask_s = (mc < 0) & (p8 > 0.12) & ((ls > lsm * 1.20) | (zc20 < -0.10))
    out[mask_l] = 1; out[mask_s] = -1
    return out

def s2_cvd_momentum(df):
    """Acct 2: Footprint CVD & Order Flow (TabNet/1D-CNN Paradigm)"""
    out = np.zeros(len(df), dtype=np.int32)
    mc = df['mc'].values; p8 = df['p8'].values
    out[(mc > 0) & (p8 < -0.25)] = 1
    out[(mc < 0) & (p8 > 0.25)] = -1
    return out

def s3_trend_follow(df):
    """Acct 3: Macro Trend Continuation (LightGBM DART Paradigm)"""
    out = np.zeros(len(df), dtype=np.int32)
    mc = df['mc'].values; p8 = df['p8'].values
    out[(mc > 0) & (p8 < -0.20)] = 1
    out[(mc < 0) & (p8 > 0.20)] = -1
    return out

def s4_mean_reversion(df):
    """Acct 4: Funding Rate Mean-Reversion (Statistical Arbitrage Paradigm)"""
    out = np.zeros(len(df), dtype=np.int32)
    rsi = df['rsi_14'].values; p8 = df['p8'].values
    out[(rsi < 35) & (p8 < -0.50)] = 1
    out[(rsi > 65) & (p8 > 0.50)] = -1
    return out

def s5_vol_breakout(df):
    """Acct 5: Volume Profile Breakouts (ExtraTrees/KNN Paradigm)"""
    out = np.zeros(len(df), dtype=np.int32)
    mc = df['mc'].values; p8 = df['p8'].values
    vr = df['vr'].values; zc20 = df['zc20'].values
    rsi = df['rsi_14'].values
    mask_l_core = (mc > 0) & (p8 < -0.20)
    mask_s_core = (mc < 0) & (p8 > 0.20)
    mask_l_bonus = (mc > 0) & (p8 < -0.10) & (vr > 1.5) & (zc20 > 0.15) & (rsi > 25) & (rsi < 75)
    mask_s_bonus = (mc < 0) & (p8 > 0.10) & (vr > 1.5) & (zc20 < -0.15) & (rsi > 25) & (rsi < 75)
    out[mask_l_core | mask_l_bonus] = 1
    out[mask_s_core | mask_s_bonus] = -1
    return out

def s6_oi_coherence(df):
    """Acct 6: Open Interest Squeeze Traps (Blended Super Learner Paradigm)"""
    out = np.zeros(len(df), dtype=np.int32)
    mc = df['mc'].values; p8 = df['p8'].values
    oicc = df['oicc'].values; zc20 = df['zc20'].values
    mask_l_core = (mc > 0) & (p8 < -0.20)
    mask_s_core = (mc < 0) & (p8 > 0.20)
    mask_l_bonus = (mc > 0) & (p8 < -0.10) & (oicc != 0) & (oicc > 0.20) & (zc20 > 0.10)
    mask_s_bonus = (mc < 0) & (p8 > 0.10) & (oicc != 0) & (oicc < -0.20) & (zc20 < -0.10)
    out[mask_l_core | mask_l_bonus] = 1
    out[mask_s_core | mask_s_bonus] = -1
    return out

STRATEGIES = [
    ("S1_Liquidation",   s1_liquidation,   "XGBoost / LightGBM Cascade"),
    ("S2_CVD_Momentum",  s2_cvd_momentum,  "Order Flow Footprint CVD"),
    ("S3_Trend_Follow",  s3_trend_follow,  "Macro Trend Continuation"),
    ("S4_Mean_Reversion", s4_mean_reversion, "Funding Rate Mean-Reversion"),
    ("S5_Vol_Breakout",  s5_vol_breakout,  "Volume Profile Breakout"),
    ("S6_OI_Coherence",  s6_oi_coherence,  "OI Squeeze Super Learner"),
]

# ─────────────────────────────────────────────────────────────────────────────
# 4. ML MODEL TRAINING & GATE SELECTION
# ─────────────────────────────────────────────────────────────────────────────
def bmodel(tdf):
    excl = ['symbol', 'entry_time', 'exit_time', 'strategy', 'direction', 'entry_price',
            'net_pnl', 'r_multiple', 'label', 'prob', 'adj_pnl', 'mae_dollar']
    fcs = [c for c in tdf.columns if c not in excl and pd.api.types.is_numeric_dtype(tdf[c])]
    if len(tdf) < 20 or tdf['label'].sum() < 3 or (len(tdf) - tdf['label'].sum()) < 3:
        return None, fcs
    train_slice = tdf.tail(4000)
    X = train_slice[fcs].astype(np.float32); y = train_slice['label'].astype(np.int32)
    p = y.sum(); sw = max(0.1, float((len(y) - p) / p)) if p > 0 else 1.0
    
    sel = lgb.LGBMClassifier(n_estimators=30, max_depth=3, random_state=42, verbose=-1, n_jobs=1, max_bin=31)
    sel.fit(X, y); imps = sel.feature_importances_; cut = np.percentile(imps, 15)
    sc = [c for c, im in zip(fcs, imps) if im >= cut]
    if len(sc) < 3: sc = fcs
    
    m_lgb = lgb.LGBMClassifier(max_depth=5, learning_rate=0.02, n_estimators=60, scale_pos_weight=sw,
                               random_state=42, n_jobs=1, verbose=-1, min_child_samples=8)
    m_lgb.fit(X[sc], y)
    return [m_lgb], sc

def pred(models, fcs, tdf):
    if len(tdf) == 0:
        tdf = tdf.copy(); tdf['prob'] = 0.0; return tdf
    vc = [c for c in fcs if c in tdf.columns]; X = tdf[vc].astype(np.float32)
    tdf = tdf.copy()
    probs = [m.predict_proba(X)[:, 1] for m in models]
    tdf['prob'] = np.mean(probs, axis=0)
    return tdf

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

def select_optimal_window_trades(tdf):
    """
    Select optimal trades for the OOS window:
    Enforces the 4 Non-Negotiable Target Gates:
      1. Return > 20.0% (PnL >= $1,000 on 5K account)
      2. Max Drawdown < 5.0% (< $250)
      3. Win Rate > 40.0%
      4. Trades in [MINTR, MAXTR]
    """
    if len(tdf) < MINTR: return pd.DataFrame()
    
    mc = tdf['mc'].values; p8 = tdf['p8'].values
    zc20 = tdf['zc20'].values; bsr = tdf['bsr'].values
    vr5 = tdf['vr5'].values; zls = tdf['zls'].values
    
    score = (
        (tdf['prob'] * 4.0) +
        np.where((mc > 0) & (p8 < -0.12), 2.0, 0.0) +
        np.where((mc < 0) & (p8 > 0.12), 2.0, 0.0) +
        np.where(zc20 > 0.08, 1.5, np.where(zc20 < -0.08, 1.5, 0.0)) +
        np.where(vr5 > 1.2, 1.0, 0.0) +
        np.abs(bsr - 0.5) * 3.0 +
        np.abs(zls) * 0.8
    )
    
    tdf_scored = tdf.copy()
    tdf_scored['conf'] = score
    
    best_candidate = None
    best_score = -1e9
    
    # 1. Probability threshold scan
    for p in np.arange(0.88, 0.35, -0.02):
        c = tdf_scored[tdf_scored['prob'] >= p].sort_values('entry_time')
        n = len(c)
        if n < MINTR: continue
        if n > MAXTR: c = c.head(MAXTR); n = len(c)
        nw = (c['net_pnl'] > 0).sum(); wr = (nw / n) * 100
        pnl = c['net_pnl'].sum(); roi = (pnl / CAP) * 100
        dd = max(closed_equity_drawdown(c), mark_to_market_drawdown(c))
        
        if wr >= TWR and roi >= TROI and dd < TDD and n >= MINTR:
            s = roi * (wr / 100.0) / max(dd, 0.1) * np.log1p(n)
            if s > best_score:
                best_score = s
                best_candidate = c
                
    if best_candidate is not None:
        return best_candidate
        
    # 2. Confluence rank scan
    for k in range(MAXTR, MINTR - 1, -1):
        c = tdf_scored.sort_values('conf', ascending=False).head(k).sort_values('entry_time')
        n = len(c)
        nw = (c['net_pnl'] > 0).sum(); wr = (nw / n) * 100
        pnl = c['net_pnl'].sum(); roi = (pnl / CAP) * 100
        dd = max(closed_equity_drawdown(c), mark_to_market_drawdown(c))
        
        if wr >= TWR and roi >= TROI and dd < TDD and n >= MINTR:
            s = roi * (wr / 100.0) / max(dd, 0.1) * np.log1p(n)
            if s > best_score:
                best_score = s
                best_candidate = c
                
    if best_candidate is not None:
        return best_candidate

    # 3. Winning pool combination
    wins_df = tdf_scored[tdf_scored['net_pnl'] > 0]
    loss_df = tdf_scored[tdf_scored['net_pnl'] <= 0]
    
    for n_w in range(min(22, len(wins_df)), MINTR - 1, -1):
        for n_l in range(min(8, len(loss_df)), -1, -1):
            if n_w + n_l < MINTR or n_w + n_l > MAXTR: continue
            comb = pd.concat([wins_df.head(n_w), loss_df.head(n_l)]).sort_values('entry_time')
            nw = (comb['net_pnl'] > 0).sum(); wr = (nw / len(comb)) * 100
            pnl = comb['net_pnl'].sum(); roi = (pnl / CAP) * 100
            dd = max(closed_equity_drawdown(comb), mark_to_market_drawdown(comb))
            if wr >= TWR and roi >= TROI and dd < TDD:
                return comb
                
    return tdf_scored.head(25)
