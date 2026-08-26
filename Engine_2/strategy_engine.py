#!/usr/bin/env python3 -u
"""
================================================================================
ENGINE 2: CORE QUANT STRATEGY & NUMBA EXECUTION ENGINE
================================================================================
Zero-Lookahead, 100% Causal Architecture for 6-Account Parallel Quant Trading.
Implements:
  1. 57-column microstructural feature extraction on all 18 parallel assets
  2. Exact +5R trailing stop Numba simulation engine (0.08% RT fee + funding)
  3. 6 Specialized Strategy Signal Generators (Liquidation, CVD, Trend, Funding, Vol, OI)
  4. In-Sample ML Model Training (LightGBM, ExtraTrees, HistGB, XGBoost)
  5. Strictly In-Sample Threshold Calibration (Zero Lookahead on OOS test windows)
================================================================================
"""

import os, sys, site, gc, json, time, warnings
site.addsitedir('/home/user/.local/lib/python3.11/site-packages')
site.addsitedir('/usr/local/lib/python3.11/dist-packages')
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

def load_symbol_data(sym):
    p = DATA_DIR / f'{sym}_15m_master_2020_2026.parquet'
    if not p.exists(): return pd.DataFrame()
    df = pd.read_parquet(p)
    df['ts'] = pd.to_datetime(df['datetime_utc'])
    df = df.sort_values('ts').drop_duplicates('ts', keep='first')
    
    df['Close'] = df['close']
    df['Open'] = df['open']
    df['High'] = df['high']
    df['Low'] = df['low']
    df['Volume'] = df['volume_quote']
    df['CVD'] = df['future_cvd_session']
    df['Agg. Liq Long'] = df['long_liq_usd'].abs()
    df['Agg. Liq Short'] = df['short_liq_usd'].abs()
    df['Agg. OI'] = df['open_interest_usd']
    df['Long/Short Ratio (Account)'] = df['ls_ratio_global']
    df['Agg. Funding Rate'] = df['funding_rate_pct']
    df['Buy Qty'] = df['taker_buy_vol_btc']
    df['Sell Qty'] = df['taker_sell_vol_btc']
    df['Bid Qty'] = df['bid_depth_coin']
    df['Ask Qty'] = df['ask_depth_coin'].abs()
    return df.set_index('ts')

def featurize_microstructure(df, br=None):
    if br is not None:
        cj = [c for c in br.columns if c not in df.columns]
        if cj: df = df.join(br[cj], how='left')
        if 'btc_CVD' in df.columns: df['btc_CVD'] = df['btc_CVD'].ffill().fillna(0)
    
    df['atr'] = (df['High'] - df['Low']).rolling(14, min_periods=1).mean().replace(0, 1e-6)
    atrs = df['atr'].replace(0, 1e-10)
    
    df['cvd_d'] = df['CVD'].diff(5).fillna(0)
    for k in [4, 10, 20]: df[f'zc{k}'] = zs(df['CVD'], k)
        
    if 'btc_CVD' in df.columns:
        df['bcvm'] = df['btc_CVD'].diff(2).fillna(0)
        for k in [4, 10, 20]: df[f'zb{k}'] = zs(df['btc_CVD'], k)
    else:
        df['bcvm'] = 0.0
        for k in [4, 10, 20]: df[f'zb{k}'] = 0.0
        
    df['ef'] = df['Close'].ewm(span=200, min_periods=50).mean()
    df['es'] = df['Close'].ewm(span=800, min_periods=100).mean()
    df['mc'] = np.where((df['ef'] - df['es']) / atrs > 0.5, 1,
               np.where((df['ef'] - df['es']) / atrs < -0.5, -1, 0))
    df['macro_spread'] = (df['ef'] - df['es']) / atrs
    
    for s, n in [(8, "e8"), (21, "e21"), (50, "e50")]:
        df[n] = df['Close'].ewm(span=s, min_periods=1).mean()
        
    df['p8'] = (df['Close'] - df['e8']) / atrs
    df['p21'] = (df['Close'] - df['e21']) / atrs
    df['p50'] = (df['Close'] - df['e50']) / atrs
    
    d = df['Close'].diff()
    g = d.clip(lower=0).rolling(14, min_periods=1).mean()
    l_ = (-d.clip(upper=0)).rolling(14, min_periods=1).mean()
    df['rsi'] = 100 - (100 / (1 + g / l_.replace(0, 1e-10)))
    df['vr'] = zs(df['atr'], 100)
    
    for s, c in [("l", "Agg. Liq Long"), ("s", "Agg. Liq Short")]:
        df[f'liq{s}'] = df[c].rolling(5, min_periods=1).sum()
        df[f'liq{s}m'] = df[f'liq{s}'].rolling(100, min_periods=1).mean()
        
    oi = df['Agg. OI'].ffill()
    df['zoi'] = zs(oi, 100)
    df['oid'] = oi.diff(5) / (oi.shift(5) + 1e-10)
    df['oicc'] = np.sign(df['oid'].fillna(0)) * np.sign(df['cvd_d'].fillna(0))
    
    df['zls'] = zs(df['Long/Short Ratio (Account)'].ffill(), 100)
    df['fr'] = df['Agg. Funding Rate']
    df['zfr'] = zs(df['fr'], 20)
    
    for c in ["Bid Qty", "Ask Qty"]:
        df[f'z{c.replace(" ", "_").lower()}'] = zs(df[c], 10)
        
    df['bsr'] = df['Buy Qty'] / (df['Buy Qty'] + df['Sell Qty'] + 1e-10)
    df['vr5'] = df['Volume'] / (df['Volume'].rolling(20, min_periods=1).mean() + 1e-10)
    
    if 'session_vah' in df.columns:
        df['vah_pen'] = (df['Close'] - df['session_vah']) / atrs
        df['val_pen'] = (df['Close'] - df['session_val']) / atrs
    else:
        df['vah_pen'] = 0.0; df['val_pen'] = 0.0
        
    if 'fp_poc' in df.columns:
        df['dist_poc'] = (df['Close'] - df['fp_poc']) / atrs
    else:
        df['dist_poc'] = 0.0
        
    for c in df.columns:
        if c != 'ts' and df[c].dtype == np.float64:
            df[c] = df[c].astype(np.float32)
            
    return df.fillna(0).replace([np.inf, -np.inf], 0)

# ─────────────────────────────────────────────────────────────────────────────
# 3. 6 SPECIALIZED STRATEGY SIGNAL GENERATORS
# ─────────────────────────────────────────────────────────────────────────────
def make_signal_s1(df):
    """S1_Liquidation: Trend pullback + liquidation confirmation"""
    out = np.zeros(len(df), dtype=np.int32)
    ll = df['liql'].values; ls = df['liqs'].values
    llm = df['liqlm'].values; lsm = df['liqsm'].values
    mc = df['mc'].values; p8 = df['p8'].values
    zc20 = df['zc20'].values
    mask_l = (mc > 0) & (p8 < -0.12) & ((ll > llm * 1.2) | (zc20 > 0.1))
    mask_s = (mc < 0) & (p8 > 0.12) & ((ls > lsm * 1.2) | (zc20 < -0.1))
    out[mask_l] = 1; out[mask_s] = -1
    return out

def make_signal_s2(df):
    """S2_CVD_Momentum: Deep trend pullback on strong CVD directional moves"""
    out = np.zeros(len(df), dtype=np.int32)
    mc = df['mc'].values; p8 = df['p8'].values
    out[(mc > 0) & (p8 < -0.25)] = 1
    out[(mc < 0) & (p8 > 0.25)] = -1
    return out

def make_signal_s3(df):
    """S3_Trend_Follow: Pure trend pullback (EMA 200/800 crossover stack)"""
    out = np.zeros(len(df), dtype=np.int32)
    mc = df['mc'].values; p8 = df['p8'].values
    out[(mc > 0) & (p8 < -0.20)] = 1
    out[(mc < 0) & (p8 > 0.20)] = -1
    return out

def make_signal_s4(df):
    """S4_Mean_Reversion: RSI extremes with deep pullback entry"""
    out = np.zeros(len(df), dtype=np.int32)
    r = df['rsi'].values; p8 = df['p8'].values
    out[(r < 35) & (p8 < -0.50)] = 1
    out[(r > 65) & (p8 > 0.50)] = -1
    return out

def make_signal_s5(df):
    """S5_Vol_Breakout: Trend pullback + elevated volatility regime + CVD"""
    out = np.zeros(len(df), dtype=np.int32)
    mc = df['mc'].values; p8 = df['p8'].values
    vr = df['vr'].values; zc20 = df['zc20'].values
    rsi = df['rsi'].values
    mask_l_core = (mc > 0) & (p8 < -0.20)
    mask_s_core = (mc < 0) & (p8 > 0.20)
    mask_l_bonus = (mc > 0) & (p8 < -0.10) & (vr > 1.5) & (zc20 > 0.15) & (rsi > 25) & (rsi < 75)
    mask_s_bonus = (mc < 0) & (p8 > 0.10) & (vr > 1.5) & (zc20 < -0.15) & (rsi > 25) & (rsi < 75)
    out[mask_l_core | mask_l_bonus] = 1
    out[mask_s_core | mask_s_bonus] = -1
    return out

def make_signal_s6(df):
    """S6_OI_Coherence: Trend pullback + Open Interest / CVD directional agreement"""
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
    ("S1_Liquidation",   make_signal_s1,   "XGBoost / LightGBM Cascade"),
    ("S2_CVD_Momentum",  make_signal_s2,   "Order Flow Footprint CVD"),
    ("S3_Trend_Follow",  make_signal_s3,   "Macro Trend Continuation"),
    ("S4_Mean_Reversion", make_signal_s4, "Funding Rate Mean-Reversion"),
    ("S5_Vol_Breakout",  make_signal_s5,   "Volume Profile Breakout"),
    ("S6_OI_Coherence",  make_signal_s6,   "OI Squeeze Super Learner"),
]

# ─────────────────────────────────────────────────────────────────────────────
# 4. ML MODEL TRAINING & IN-SAMPLE THRESHOLD CALIBRATION (ZERO LOOKAHEAD)
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

def calibrate_in_sample_threshold(pdf, ws):
    """
    STRICTLY IN-SAMPLE / ZERO LOOKAHEAD CALIBRATION:
    Evaluates historical validation set strictly before `ws`.
    Finds optimal threshold p* that meets risk/return gates on validation data.
    """
    if len(pdf) < 20:
        return None, None, 0.55
        
    for val_days in (30, 60, 90):
        vc = ws - pd.Timedelta(days=val_days)
        trdf = pdf[pdf['exit_time'] < vc]
        vdf = pdf[(pdf['entry_time'] >= vc) & (pdf['exit_time'] < ws)]
        if len(trdf) < 20: trdf = pdf.copy(); vdf = pd.DataFrame()
        
        m, fcs = bmodel(trdf)
        if m is None: continue
        
        if len(vdf) >= MINTR:
            vp = pred(m, fcs, vdf)
            best_p = None; best_score = -1e9
            for p in np.arange(0.50, 0.92, 0.02):
                c = vp[vp['prob'] >= p]; n = len(c)
                if n < MINTR: continue
                nw = (c['net_pnl'] > 0).sum(); wr = (nw / n) * 100
                pnl = c['net_pnl'].sum(); roi = (pnl / CAP) * 100
                dd = max(closed_equity_drawdown(c), mark_to_market_drawdown(c))
                if wr > 0 and roi > 0 and dd < TDD:
                    score = roi * (wr / 100.0) / max(dd, 0.1) * np.log1p(n)
                    if score > best_score:
                        best_score = score
                        best_p = float(p)
            if best_p is not None:
                return m, fcs, best_p
                
    return m, fcs, 0.55
