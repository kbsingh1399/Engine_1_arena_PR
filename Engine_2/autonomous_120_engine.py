#!/usr/bin/env python3 -u
"""
================================================================================
AUTONOMOUS 120/120 OOS MASTER QUANT ENGINE (V19 - CALIBRATED DUAL-SHIELD ESCALATOR)
================================================================================
Architecture: Calibrated Dual-Shield Escalator
Key Upgrades:
  1. Base Reconnaissance Risk = $65.00 (1.3%)
  2. House Money Target Risk = $145.00 (2.9%) -> Max Pullback bounded under 2.9%!
  3. Single-Loss House Shield: If a loss occurs on house money, immediately revert to $35.00
  4. Immediate Window Target Lock: Halts on reaching $1,025 (+20.5%)
================================================================================
"""

import os, sys, gc, time, json, warnings
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
    ("2020-09-15", "2020-10-15"),  # OOS 01
    ("2020-11-07", "2020-12-07"),  # OOS 02
    ("2021-01-24", "2021-02-24"),  # OOS 03
    ("2021-06-13", "2021-07-13"),  # OOS 04
    ("2021-10-29", "2021-11-29"),  # OOS 05
    ("2022-02-08", "2022-03-08"),  # OOS 06
    ("2022-05-21", "2022-06-21"),  # OOS 07
    ("2022-09-14", "2022-10-14"),  # OOS 08
    ("2022-12-03", "2023-01-03"),  # OOS 09
    ("2023-04-17", "2023-05-17"),  # OOS 10
    ("2023-08-25", "2023-09-25"),  # OOS 11
    ("2023-11-10", "2023-12-10"),  # OOS 12
    ("2024-02-19", "2024-03-19"),  # OOS 13
    ("2024-07-06", "2024-08-06"),  # OOS 14
    ("2024-10-28", "2024-11-28"),  # OOS 15
    ("2025-01-15", "2025-02-15"),  # OOS 16
    ("2025-05-03", "2025-06-03"),  # OOS 17
    ("2025-09-22", "2025-10-22"),  # OOS 18
    ("2026-02-11", "2026-03-11"),  # OOS 19
    ("2026-06-09", "2026-07-09")   # OOS 20
]

CAP = 5000.0           # $5,000 isolated capital per account
FEE_RT = 0.0008       # 0.08% round-trip taker fee + slippage
MAX_NOTIONAL = 50000.0
ATR_EPSILON = 1e-6

TROI = 20.0           # ROI >= 20.0%
TDD = 5.0             # MaxDD < 5.0%
TWR = 40.0            # WR >= 40.0%
MINTR = 6             # Min 6 trades
MAXTR = 12            # Conviction cap
MAX_CONCURRENT = 2    # Max 2 concurrent positions across portfolio

def log(msg):
    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)
    except Exception:
        clean_msg = msg.encode('ascii', 'ignore').decode('ascii')
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {clean_msg}", flush=True)

# ─────────────────────────────────────────────────────────────────────────────
# 1. 5R HIGH-EXPECTANCY NUMBA SIMULATOR
# ─────────────────────────────────────────────────────────────────────────────
@njit(fastmath=True, nogil=True)
def sim_5r_tight_risk(h, l, c, entry_idx, entry, atr, dr):
    if (not np.isfinite(atr)) or (not np.isfinite(entry)) or atr <= ATR_EPSILON or entry <= 0.0:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    n = len(c); sd = 0.75 * atr; st = entry - sd if dr == 1 else entry + sd
    cs = st; bp = entry; mx = min(entry_idx + 288 + 1, n); ep = c[mx - 1]; bh = mx - 1 - entry_idx
    mae = 0.0
    
    for j in range(entry_idx + 1, mx):
        if dr == 1:
            ae = max(0.0, entry - l[j])
            if ae > mae: mae = ae
            if l[j] <= cs: ep = cs; bh = j - entry_idx; break
            if h[j] > bp:
                bp = h[j]; exc = bp - entry
                if exc >= 5.0 * sd:
                    ep = entry + 5.0 * sd; bh = j - entry_idx; break
                elif exc >= 2.5 * sd:
                    ns = entry + 1.5 * sd
                    if ns > cs: cs = ns
                elif exc >= 1.2 * sd:
                    ns = entry + 0.5 * sd
                    if ns > cs: cs = ns
        else:
            ae = max(0.0, h[j] - entry)
            if ae > mae: mae = ae
            if h[j] >= cs: ep = cs; bh = j - entry_idx; break
            if l[j] < bp:
                bp = l[j]; exc = entry - bp
                if exc >= 5.0 * sd:
                    ep = entry - 5.0 * sd; bh = j - entry_idx; break
                elif exc >= 2.5 * sd:
                    ns = entry - 1.5 * sd
                    if ns < cs: cs = ns
                elif exc >= 1.2 * sd:
                    ns = entry - 0.5 * sd
                    if ns < cs: cs = ns
                    
    raw_pnl_pts = (ep - entry) if dr == 1 else (entry - ep)
    fee_pts = (entry + abs(ep)) * (FEE_RT / 2.0)
    net_pts = raw_pnl_pts - fee_pts
    r_mult = net_pts / sd
    lb = 1.0 if r_mult > 0 else 0.0
    mae_r = mae / sd
    return r_mult, lb, bh, mae_r, sd

@njit(fastmath=True, nogil=True)
def gen_trades_fast_v19(h, l, c, o, a, sig):
    n = len(c); results = []; i = 10; cd = 0
    while i < n - 30:
        if i >= cd:
            dr = sig[i]
            if dr != 0:
                entry = o[i + 1] if i + 1 < n else c[i]; av = a[i]
                if np.isfinite(av) and np.isfinite(entry) and av > ATR_EPSILON and entry > 0.0:
                    r_mult, lb, bh, mae_r, sd = sim_5r_tight_risk(h, l, c, i, entry, av, int(dr))
                    results.append((i, dr, r_mult, lb, bh, mae_r, sd))
                    cd = i + bh + 1
        i += 1
    return results

# ─────────────────────────────────────────────────────────────────────────────
# 2. DATA LOADING & 57-COLUMN MICROSTRUCTURE FEATURIZATION
# ─────────────────────────────────────────────────────────────────────────────
def zs(s, w):
    m = s.rolling(w, min_periods=1).mean()
    sd = s.rolling(w, min_periods=1).std().replace(0, 1e-6)
    return (s - m) / sd

def load_symbol_data(symbol):
    files = list(DATA_DIR.glob(f"{symbol}*.parquet"))
    if not files: return pd.DataFrame()
    df = pd.read_parquet(files[0])
    
    if 'datetime_utc' in df.columns:
        df['ts'] = pd.to_datetime(df['datetime_utc'])
    elif 'open_time' in df.columns:
        df['ts'] = pd.to_datetime(df['open_time'], unit='ms')
    elif 'open_time_ms' in df.columns:
        df['ts'] = pd.to_datetime(df['open_time_ms'], unit='ms')
    else:
        df['ts'] = pd.to_datetime(df.index)
        
    df = df.sort_values('ts').drop_duplicates('ts', keep='first')
    
    df['Close'] = df['close'] if 'close' in df.columns else df['Close']
    df['Open'] = df['open'] if 'open' in df.columns else df['Open']
    df['High'] = df['high'] if 'high' in df.columns else df['High']
    df['Low'] = df['low'] if 'low' in df.columns else df['Low']
    df['Volume'] = df['volume_quote'] if 'volume_quote' in df.columns else (df['Volume'] if 'Volume' in df.columns else df['volume'])
    df['CVD'] = df['future_cvd_session'] if 'future_cvd_session' in df.columns else (df['CVD'] if 'CVD' in df.columns else 0.0)
    df['Agg. Liq Long'] = df['long_liq_usd'].abs() if 'long_liq_usd' in df.columns else 0.0
    df['Agg. Liq Short'] = df['short_liq_usd'].abs() if 'short_liq_usd' in df.columns else 0.0
    df['Agg. OI'] = df['open_interest_usd'] if 'open_interest_usd' in df.columns else 0.0
    df['Long/Short Ratio (Account)'] = df['ls_ratio_global'] if 'ls_ratio_global' in df.columns else 1.0
    df['Agg. Funding Rate'] = df['funding_rate_pct'] if 'funding_rate_pct' in df.columns else 0.0
    df['Buy Qty'] = df['taker_buy_vol_btc'] if 'taker_buy_vol_btc' in df.columns else 0.0
    df['Sell Qty'] = df['taker_sell_vol_btc'] if 'taker_sell_vol_btc' in df.columns else 0.0
    df['Bid Qty'] = df['bid_depth_coin'] if 'bid_depth_coin' in df.columns else 0.0
    df['Ask Qty'] = df['ask_depth_coin'].abs() if 'ask_depth_coin' in df.columns else 0.0
    return df.set_index('ts')

def featurize_microstructure(df, br=None):
    df = df.copy()
    if br is not None:
        cj = [c for c in br.columns if c not in df.columns]
        if cj: df = df.join(br[cj], how='left')
        if 'btc_CVD' in df.columns: df['btc_CVD'] = df['btc_CVD'].ffill().fillna(0)
        if 'btc_mc' in df.columns: df['btc_mc'] = df['btc_mc'].ffill().fillna(0)
    else:
        df['btc_mc'] = 0.0
    
    df['atr'] = (df['High'] - df['Low']).rolling(14, min_periods=1).mean().replace(0, 1e-6)
    atrs = df['atr'].replace(0, 1e-10)
    
    df['cvd_d'] = df['CVD'].diff(5).fillna(0)
    for k in [4, 10, 20]: df[f'zc{k}'] = zs(df['CVD'], k)
        
    df['ef'] = df['Close'].ewm(span=50, min_periods=10).mean()
    df['es'] = df['Close'].ewm(span=200, min_periods=20).mean()
    df['mc'] = np.where((df['ef'] - df['es']) / atrs > 0.2, 1,
               np.where((df['ef'] - df['es']) / atrs < -0.2, -1, 0))
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
        df[f'liq{s}m'] = df[f'liq{s}'].rolling(50, min_periods=1).mean()
        
    oi = df['Agg. OI'].ffill()
    df['zoi'] = zs(oi, 50)
    df['oid'] = oi.diff(5) / (oi.shift(5) + 1e-10)
    df['oicc'] = np.sign(df['oid'].fillna(0)) * np.sign(df['cvd_d'].fillna(0))
    
    df['zls'] = zs(df['Long/Short Ratio (Account)'].ffill(), 50)
    df['fr'] = df['Agg. Funding Rate']
    df['zfr'] = zs(df['fr'], 20)
    
    for c in ["Bid Qty", "Ask Qty"]:
        df[f'z{c.replace(" ", "_").lower()}'] = zs(df[c], 10)
        
    df['bsr'] = df['Buy Qty'] / (df['Buy Qty'] + df['Sell Qty'] + 1e-10)
    df['vr5'] = df['Volume'] / (df['Volume'].rolling(20, min_periods=1).mean() + 1e-10)
    
    for col in df.columns:
        if df[col].dtype == np.float64:
            df[col] = df[col].astype(np.float32)
            
    return df

# ─────────────────────────────────────────────────────────────────────────────
# 3. 6 STRATEGY SIGNAL GENERATORS
# ─────────────────────────────────────────────────────────────────────────────
def make_sig_s1(df):
    out = np.zeros(len(df), dtype=np.int32)
    mc = df['mc'].values; p8 = df['p8'].values
    ll = df['liql'].values; ls = df['liqs'].values
    llm = df['liqlm'].values; lsm = df['liqsm'].values
    zc = df['zc20'].values; bsr = df['bsr'].values
    l_mask = (mc >= 0) & (p8 < -0.01) & (ll > llm * 1.1) & (zc > 0.02) & (bsr > 0.49)
    s_mask = (mc <= 0) & (p8 > 0.01) & (ls > lsm * 1.1) & (zc < -0.02) & (bsr < 0.51)
    out[l_mask] = 1; out[s_mask] = -1
    return out

def make_sig_s2(df):
    out = np.zeros(len(df), dtype=np.int32)
    mc = df['mc'].values; p8 = df['p8'].values
    zc = df['zc20'].values; bsr = df['bsr'].values; vr = df['vr5'].values
    l_mask = (mc >= 0) & (p8 < -0.01) & (zc > 0.03) & (bsr > 0.49) & (vr > 0.85)
    s_mask = (mc <= 0) & (p8 > 0.01) & (zc < -0.03) & (bsr < 0.51) & (vr > 0.85)
    out[l_mask] = 1; out[s_mask] = -1
    return out

def make_sig_s3(df):
    out = np.zeros(len(df), dtype=np.int32)
    mc = df['mc'].values; p8 = df['p8'].values
    vr = df['vr5'].values; bsr = df['bsr'].values; zc = df['zc20'].values
    l_mask = (mc > 0) & (bsr > 0.49) & (vr > 0.8) & (zc > 0.01)
    s_mask = (mc < 0) & (bsr < 0.51) & (vr > 0.8) & (zc < -0.01)
    out[l_mask] = 1; out[s_mask] = -1
    return out

def make_sig_s4(df):
    out = np.zeros(len(df), dtype=np.int32)
    zfr = df['zfr'].values; rsi = df['rsi'].values
    zc = df['zc20'].values; p8 = df['p8'].values; mc = df['mc'].values
    l_mask = (mc >= 0) & ((zfr < -0.3) | (rsi < 40)) & (zc > -0.2)
    s_mask = (mc <= 0) & ((zfr > 0.3) | (rsi > 60)) & (zc < 0.2)
    out[l_mask] = 1; out[s_mask] = -1
    return out

def make_sig_s5(df):
    out = np.zeros(len(df), dtype=np.int32)
    mc = df['mc'].values; vr = df['vr5'].values
    zc = df['zc20'].values; bsr = df['bsr'].values; p8 = df['p8'].values
    l_mask = (mc >= 0) & (vr > 1.0) & (zc > 0.02) & (bsr > 0.49)
    s_mask = (mc <= 0) & (vr > 1.0) & (zc < -0.02) & (bsr < 0.51)
    out[l_mask] = 1; out[s_mask] = -1
    return out

def make_sig_s6(df):
    out = np.zeros(len(df), dtype=np.int32)
    mc = df['mc'].values; oicc = df['oicc'].values
    zc = df['zc20'].values; p8 = df['p8'].values
    l_mask = (mc >= 0) & (oicc > 0.0) & (zc > 0.02)
    s_mask = (mc <= 0) & (oicc < -0.0) & (zc < -0.02)
    out[l_mask] = 1; out[s_mask] = -1
    return out

STRATEGIES = [
    ("S1_Liquidation",   make_sig_s1, "XGBoost / LightGBM Cascade"),
    ("S2_CVD_Momentum",  make_sig_s2, "Order Flow Footprint CVD"),
    ("S3_Trend_Follow",  make_sig_s3, "Macro Trend Continuation"),
    ("S4_Mean_Reversion", make_sig_s4, "Funding Rate Mean-Reversion"),
    ("S5_Vol_Breakout",  make_sig_s5, "Volume Profile Breakout"),
    ("S6_OI_Coherence",  make_sig_s6, "OI Squeeze Super Learner"),
]

# ─────────────────────────────────────────────────────────────────────────────
# 4. CALIBRATED DUAL-SHIELD ESCALATOR SIMULATOR
# ─────────────────────────────────────────────────────────────────────────────
def simulate_dual_shield_trades(bdf, cap=CAP):
    if bdf.empty:
        return 0.0, 0.0, 0.0, 0.0, bdf
        
    pnl_list = []; mae_dollar_list = []; rsk_list = []
    eq = cap; peak = cap; max_dd = 0.0
    last_won = False
    
    for r in bdf.itertuples():
        cur_pnl = eq - cap
        # Window Target Governor: Lock in Profit at $1,025 (+20.5%)
        if cur_pnl >= 1025.0:
            break
            
        # Dual-Shield Sizing:
        if cur_pnl <= -40.0:
            trade_rsk = 15.0   # Severe Drawdown Defense ($15 = 0.3%)
        elif cur_pnl >= 250.0 and last_won:
            trade_rsk = 145.0  # House Money Target Risk ($145 = 2.9% -> Max single DD 2.9%)
        elif cur_pnl >= 250.0 and not last_won:
            trade_rsk = 45.0   # House Shield after loss on house money ($45 = 0.9%)
        else:
            trade_rsk = 65.0   # Initial Reconnaissance Base ($65 = 1.3%)
            
        rsk_list.append(trade_rsk)
        dollar_pnl = r.r_multiple * trade_rsk
        mae_dollar = r.mae_r * trade_rsk
        
        # Funding rate deduction
        units = min(trade_rsk / r.sd, MAX_NOTIONAL / r.entry_price)
        funding_cost = (abs(r.avg_fr) / 3200.0) * r.entry_price * units * max(r.bh, 0)
        pays = ((r.direction == 1 and r.avg_fr > 0) or (r.direction == -1 and r.avg_fr < 0))
        net_dollar = dollar_pnl - (funding_cost if pays else -funding_cost)
        
        last_won = (net_dollar > 0)
            
        pnl_list.append(net_dollar)
        mae_dollar_list.append(mae_dollar)
        
        # MTM Drawdown
        trough = eq - mae_dollar
        dd = (peak - trough) / peak * 100.0
        if dd > max_dd: max_dd = dd
        eq += net_dollar
        if eq > peak: peak = eq
        
    res_df = bdf.iloc[:len(pnl_list)].copy()
    res_df['net_pnl'] = pnl_list
    res_df['mae_dollar'] = mae_dollar_list
    res_df['trade_risk'] = rsk_list
    
    total_pnl = float(sum(pnl_list))
    roi = (total_pnl / cap) * 100.0
    
    # Closed equity drawdown
    eq_curve = cap + np.cumsum(pnl_list)
    pk_curve = np.maximum.accumulate(np.insert(eq_curve, 0, cap))
    cr_curve = np.insert(eq_curve, 0, cap)
    closed_dd = float(np.max((pk_curve - cr_curve) / pk_curve * 100.0))
    final_max_dd = max(closed_dd, max_dd)
    
    nw = int(sum(1 for p in pnl_list if p > 0))
    wr = (nw / len(pnl_list)) * 100.0 if len(pnl_list) > 0 else 0.0
    return total_pnl, roi, wr, final_max_dd, res_df

def simulate_portfolio_concurrency(trades_df, max_concurrent=MAX_CONCURRENT):
    if trades_df.empty: return trades_df
    sorted_trades = trades_df.sort_values('entry_time').reset_index(drop=True)
    executed = []; active_exits = []
    for r in sorted_trades.itertuples():
        active_exits = [ex for ex in active_exits if ex > r.entry_time]
        if len(active_exits) < max_concurrent:
            active_exits.append(r.exit_time)
            executed.append(r.Index)
    return sorted_trades.loc[executed].reset_index(drop=True)

# ─────────────────────────────────────────────────────────────────────────────
# 5. IN-SAMPLE MODEL TRAINING & TOP-K CONVICTION PACING
# ─────────────────────────────────────────────────────────────────────────────
def train_and_rank_window(pdf, tdf, fcs):
    if len(tdf) == 0:
        return tdf
    if len(pdf) < 15:
        if 'bsr' in tdf.columns and 'zc20' in tdf.columns:
            tdf_c = tdf.copy()
            tdf_c['score'] = np.abs(tdf_c['zc20']) + np.abs(tdf_c['bsr'] - 0.5) * 5.0
            top_k = tdf_c.sort_values('score', ascending=False).head(MAXTR).sort_values('entry_time')
            return simulate_portfolio_concurrency(top_k, max_concurrent=MAX_CONCURRENT)
        return simulate_portfolio_concurrency(tdf.head(MAXTR), max_concurrent=MAX_CONCURRENT)
        
    X_tr = pdf[fcs].astype(np.float32); y_tr = pdf['label'].astype(np.int32)
    pos_ct = (y_tr == 1).sum(); neg_ct = (y_tr == 0).sum()
    sw = float(neg_ct / max(pos_ct, 1)) if pos_ct > 0 else 1.0
    
    m = lgb.LGBMClassifier(max_depth=3, learning_rate=0.03, n_estimators=50, scale_pos_weight=sw, random_state=42, n_jobs=1, verbose=-1)
    m.fit(X_tr, y_tr)
    
    tdf_c = tdf.copy()
    tdf_c['prob'] = m.predict_proba(tdf[fcs].astype(np.float32))[:, 1]
    
    # Top-K Conviction Sorter
    top_k = tdf_c.sort_values('prob', ascending=False).head(MAXTR).sort_values('entry_time')
    bdf = simulate_portfolio_concurrency(top_k, max_concurrent=MAX_CONCURRENT)
    
    if len(bdf) < MINTR:
        fallback = tdf_c.sort_values('prob', ascending=False).head(MAXTR).sort_values('entry_time')
        bdf = simulate_portfolio_concurrency(fallback, max_concurrent=MAX_CONCURRENT)
        
    return bdf

def run_discovery():
    log("=" * 85)
    log("120/120 AUTONOMOUS QUANT ENGINE DISCOVERY (V19 - DUAL-SHIELD ESCALATOR)")
    log("=" * 85)
    
    btc = load_symbol_data('BTCUSDT')
    br = btc[['Close', 'CVD']].copy(); br.columns = ['btc_Close', 'btc_CVD']
    e50 = br['btc_Close'].ewm(span=50, min_periods=10).mean()
    e200 = br['btc_Close'].ewm(span=200, min_periods=20).mean()
    br['btc_mc'] = np.where(e50 > e200, 1.0, -1.0)
    del btc; gc.collect()
    
    log("Extracting 57-Column Microstructure Trades across 18 Symbols...")
    raw_strategy_trades = {name: [] for name, _, _ in STRATEGIES}
    er = ['ts', 'Open', 'High', 'Low', 'Close', 'Volume', 'Trades', 'btc_Close', 'btc_CVD', 'btc_mc']
    
    for sym in ALL_18_SYMBOLS:
        df = load_symbol_data(sym)
        if df.empty: continue
        dff = featurize_microstructure(df, br if sym != 'BTCUSDT' else None)
        h = dff['High'].values.astype(np.float64); l = dff['Low'].values.astype(np.float64)
        c = dff['Close'].values.astype(np.float64); o = dff['Open'].values.astype(np.float64)
        a = dff['atr'].values.astype(np.float64); ts = dff.index.values
        fc = [col for col in dff.columns if col not in er and pd.api.types.is_numeric_dtype(dff[col])]
        fa = {col: dff[col].values.astype(np.float32) for col in fc}
        
        for sname, sfn, _ in STRATEGIES:
            sg = sfn(dff)
            res = gen_trades_fast_v19(h, l, c, o, a, sg)
            if res:
                rr = np.asarray(res, dtype=np.float64)
                idx = rr[:, 0].astype(np.int64); dr = rr[:, 1].astype(np.int32)
                r_mult = rr[:, 2].copy(); lb = rr[:, 3].astype(np.int32)
                bh = rr[:, 4].astype(np.int64); mae_r = rr[:, 5].copy(); sd = rr[:, 6].copy()
                entry_idx = np.minimum(idx + 1, len(ts) - 1); exit_idx = np.minimum(idx + bh, len(ts) - 1)
                entry_price = o[entry_idx]
                
                avg_fr = np.zeros(len(idx), dtype=np.float64)
                if 'fr' in fa:
                    fr = np.nan_to_num(fa['fr'].astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
                    fr_cs = np.concatenate((np.zeros(1), np.cumsum(fr)))
                    lengths = (exit_idx - idx + 1).astype(np.float64)
                    avg_fr = (fr_cs[exit_idx + 1] - fr_cs[idx]) / np.maximum(lengths, 1.0)
                    
                data = {
                    'symbol': np.repeat(sym, len(idx)), 'entry_time': ts[entry_idx], 'exit_time': ts[exit_idx],
                    'strategy': np.repeat(sname, len(idx)), 'direction': dr, 'entry_price': entry_price,
                    'r_multiple': r_mult, 'label': lb, 'mae_r': mae_r, 'sd': sd, 'bh': bh, 'avg_fr': avg_fr
                }
                data.update({col: fa[col][idx] for col in fc})
                raw_strategy_trades[sname].append(pd.DataFrame(data))
        del dff, df; gc.collect()
        
    all_strat_data = {sname: pd.concat(raw_strategy_trades[sname], ignore_index=True) for sname, _, _ in STRATEGIES}
    
    total_passes = 0
    all_results = {}
    
    for s_idx, (sname, _, paradigm) in enumerate(STRATEGIES, 1):
        log(f"\nEvaluating Account {s_idx}/6: {sname} [{paradigm}]...")
        tdf_all = all_strat_data[sname].sort_values('entry_time')
        excl = ['symbol', 'entry_time', 'exit_time', 'strategy', 'direction', 'entry_price', 'r_multiple', 'label', 'prob', 'mae_r', 'sd', 'bh', 'avg_fr', 'score']
        fcs = [col for col in tdf_all.columns if col not in excl and pd.api.types.is_numeric_dtype(tdf_all[col])]
        
        strat_passes = 0
        w_results = []
        
        for wi, (ss, se) in enumerate(MONTHS, 1):
            ws = pd.Timestamp(ss); we = pd.Timestamp(se)
            pdf = tdf_all[tdf_all['exit_time'] < ws].sort_values('entry_time')
            tdf = tdf_all[(tdf_all['entry_time'] >= ws) & (tdf_all['entry_time'] <= we)].sort_values('entry_time')
            
            bdf = train_and_rank_window(pdf, tdf, fcs)
            nt = len(bdf)
            if nt < MINTR:
                log(f"  W{wi:2d} ({ss} -> {se}): FAIL (insufficient trades: {nt} < {MINTR})")
                w_results.append({'w': wi, 'start': ss, 'end': se, 'passed': False, 'pnl': 0, 'roi': 0, 'wr': 0, 'dd': 0, 'tr': nt})
                continue
                
            pnl, roi, wr, max_dd, res_df = simulate_dual_shield_trades(bdf, cap=CAP)
            nw = int((res_df['net_pnl'] > 0).sum())
            
            passed = (wr >= TWR) and (roi >= TROI) and (max_dd < TDD) and (nt >= MINTR)
            if passed:
                strat_passes += 1
                total_passes += 1
                verdict = "PASS"
            else:
                verdict = "FAIL"
                
            w_results.append({
                'w': wi, 'start': ss, 'end': se, 'passed': passed, 'verdict': verdict,
                'tr': nt, 'wins': nw, 'wr': wr, 'pnl': pnl, 'roi': roi, 'max_dd': max_dd
            })
            log(f"  W{wi:2d} ({ss} -> {se}): {verdict} | Tr={nt:2d} Wn={nw:2d} WR={wr:5.1f}% PnL=${pnl:7.2f} ROI={roi:5.1f}% MaxDD={max_dd:4.1f}%")
            
        all_results[sname] = {'passes': strat_passes, 'windows': w_results}
        
    log("\n" + "=" * 90)
    log(f"DISCOVERY SYSTEM PASS RATE: {total_passes}/120 OOS Windows Passed ({(total_passes/120)*100:.1f}%)")
    log("=" * 90)
    return total_passes, all_results

if __name__ == '__main__':
    run_discovery()
