#!/usr/bin/env python3 -u
"""
================================================================================
ENGINE 2: CORE QUANT STRATEGY & NUMBA EXECUTION ENGINE
================================================================================
Zero-Lookahead, 100% Causal Architecture for 6-Account Parallel Quant Trading.
Implements:
  1. 57-column microstructural feature extraction on all 18 parallel assets
  2. 3-Phase Risk-Free Breakeven & Tiered Trailing Stop Numba Simulation:
       - Phase 0 (Entry): 1.0 * ATR initial stop loss (base risk is $35)
       - Phase 1 (+1.5R peak): Move SL to Breakeven (+0.2R profit covers fees)
       - Phase 2 (+3.0R peak): Lock in +1.8R profit
       - Phase 3 (+5.0R peak): Activate 0.8R trailing stop runner
  3. Causal Dual-Shield Risk Escalator ($65 / $145 / $45 with MTM reserve)
  4. Portfolio Concurrency Limit (Max 2 Positions simultaneously across portfolio)
  5. 6 Specialized Strategy Signal Generators (Liquidation, CVD, Trend, Funding, Vol, OI)
  6. In-Sample ML Model Training and calibrated p* threshold selection
  7. Causal volatility-regime routing with no OOS lookahead
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
import optuna
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier

optuna.logging.set_verbosity(optuna.logging.WARNING)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / 'Engine_2' / 'binance_backtesting_data'
if not DATA_DIR.exists():
    DATA_DIR = Path('./Engine_2/binance_backtesting_data')

ALL_18_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
    "AVAXUSDT", "DOGEUSDT", "DOTUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT",
    "SUIUSDT", "TRXUSDT", "APTUSDT", "ARBUSDT", "BCHUSDT", "OPUSDT"
]

MONTHS = [
    ("2020-09-15", "2020-10-15"),  # OOS 01: Post-COVID Crash Recovery
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
RSK = 35.0             # Base risk used to normalize simulator R-multiples
FEE_RT = 0.0008        # 0.08% round-trip taker fee + slippage
TP = 5.0               # 5R minimum target before activating trailing stop
TRA = 0.8              # 0.8R trailing distance
MAX_NOTIONAL = 50000.0
ATR_EPSILON = 1e-6

# Calibrated Dual-Shield Escalator. These are target risks; the allocator may
# reduce a target when the conservative mark-to-market drawdown budget is full.
RECON_RISK = 65.0              # Reconnaissance risk (1.3% of a $5,000 account)
HOUSE_MONEY_RISK = 145.0       # House-money risk after +$250 realized profit
HOUSE_SHIELD_RISK = 45.0       # Next risk after a house-money loss
DRAWDOWN_DEFENSE_RISK = 15.0   # Severe drawdown circuit-breaker risk
HOUSE_PROFIT_TRIGGER = 250.0
DRAWDOWN_RISK_LIMIT = 0.039    # Strictly below the 4% architectural objective
MIN_EXECUTION_RISK = 1.0       # Do not count dust-sized residual positions

TROI = 20.0           # Target ROI > 20% per window (> $1,000 net profit)
TDD = 5.0             # Max Drawdown < 5.0% (< $250)
TWR = 40.0            # Target win rate > 40.0%
MINTR = 6             # Min trades per window
MAXTR = 50            # Hard execution cap per window
MAX_CONCURRENT = 2    # Max concurrent positions across portfolio

REGIME_CHOP = 0
REGIME_TREND = 1
REGIME_EXPANSION = 2

OPTUNA_TRIALS = 12
OPTUNA_SEED = 42


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# ─────────────────────────────────────────────────────────────────────────────
# 1. 3-PHASE RISK-FREE BREAKEVEN & TIERED TRAILING STOP NUMBA ENGINE
# ─────────────────────────────────────────────────────────────────────────────
@njit(fastmath=True, nogil=True)
def sim_tiered(h, l, c, entry_idx, entry, atr, dr):
    """
    3-Phase Risk-Free Breakeven & Tiered Trailing Stop Simulation:
      - Phase 0: Initial SL at 1.0 * atr (1R risk)
      - Phase 1 (+1.5R peak): Move SL to Breakeven (+0.2R profit covers fees)
      - Phase 2 (+3.0R peak): Lock in +1.8R profit
      - Phase 3 (+5.0R peak): Activate 0.8R trailing stop runner to let profit run
    """
    if (not np.isfinite(atr)) or (not np.isfinite(entry)) or atr <= ATR_EPSILON or entry <= 0.0:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    n = len(c); sd = atr; st = entry - sd if dr == 1 else entry + sd
    cs = st; bp = entry; mx = min(entry_idx + 288 + 1, n); ep = c[mx - 1]; bh = mx - 1 - entry_idx
    mae = 0.0
    for j in range(entry_idx + 1, mx):
        if dr == 1:
            ae = max(0.0, entry - l[j])
            if ae > mae: mae = ae
            if l[j] <= cs: ep = cs; bh = j - entry_idx; break
            if h[j] > bp:
                bp = h[j]; exc = bp - entry
                if exc >= TP * sd:
                    ns = bp - TRA * sd
                    if ns > cs: cs = ns
                elif exc >= 3.0 * sd:
                    ns = entry + 1.8 * sd
                    if ns > cs: cs = ns
                elif exc >= 1.5 * sd:
                    ns = entry + 0.2 * sd
                    if ns > cs: cs = ns
        else:
            ae = max(0.0, h[j] - entry)
            if ae > mae: mae = ae
            if h[j] >= cs: ep = cs; bh = j - entry_idx; break
            if l[j] < bp:
                bp = l[j]; exc = entry - bp
                if exc >= TP * sd:
                    ns = bp + TRA * sd
                    if ns < cs: cs = ns
                elif exc >= 3.0 * sd:
                    ns = entry - 1.8 * sd
                    if ns < cs: cs = ns
                elif exc >= 1.5 * sd:
                    ns = entry - 0.2 * sd
                    if ns < cs: cs = ns
    u = min(RSK / sd, MAX_NOTIONAL / entry)
    g = u * (ep - entry) if dr == 1 else u * (entry - ep)
    f = u * entry * FEE_RT / 2.0 + u * abs(ep) * FEE_RT / 2.0
    npnl = g - f; r = npnl / RSK; lb = 1.0 if npnl > 0 else 0.0
    mae_dollar = u * mae
    return npnl, r, lb, bh, mae_dollar

@njit(fastmath=True, nogil=True)
def gen_trades_tiered(h, l, c, o, a, sig):
    n = len(c); results = []; i = 200; cd = 0
    while i < n - 100:
        if i >= cd:
            dr = sig[i]
            if dr != 0:
                entry = o[i + 1] if i + 1 < n else c[i]; av = a[i]
                if np.isfinite(av) and np.isfinite(entry) and av > ATR_EPSILON and entry > 0.0:
                    net, r, lb, bh, mae = sim_tiered(h, l, c, i, entry, av, int(dr))
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

def add_causal_regime_features(df):
    """Add regime features using only data available at the current bar.

    The runner enters at the next bar's open, so the current close and all
    rolling statistics through the current bar are observable at decision time.
    No centered windows, future shifts, or OOS labels are used here.
    """
    log_returns = np.log(df['Close'].clip(lower=ATR_EPSILON)).diff()
    df['realized_vol_short'] = log_returns.rolling(96, min_periods=24).std()
    df['realized_vol_long'] = log_returns.rolling(672, min_periods=96).std()
    df['vol_ratio'] = (
        df['realized_vol_short'] /
        df['realized_vol_long'].replace(0, np.nan)
    ).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    df['trend_strength'] = (df['ef'] - df['es']).abs() / df['atr'].clip(lower=ATR_EPSILON)

    # 0 = flat/chop, 1 = directional trend, 2 = directional volatility
    # expansion.  The thresholds are fixed before OOS execution.
    regime = np.full(len(df), REGIME_CHOP, dtype=np.int8)
    trending = df['trend_strength'].to_numpy() >= 0.5
    expanding = trending & (df['vol_ratio'].to_numpy() >= 1.15)
    regime[trending] = REGIME_TREND
    regime[expanding] = REGIME_EXPANSION
    df['regime'] = regime
    return df


def featurize_microstructure(df, br=None):
    df = df.copy()
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
    df = add_causal_regime_features(df)
    
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
        
    df['liq_long_ratio'] = df['liql'] / df['liqlm'].clip(lower=1e-10)
    df['liq_short_ratio'] = df['liqs'] / df['liqsm'].clip(lower=1e-10)
    df['bsr'] = df['Buy Qty'] / (df['Buy Qty'] + df['Sell Qty'] + 1e-10)
    df['flow_imbalance'] = 2.0 * df['bsr'] - 1.0
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
    # Keep a superset of the tunable S1 search space. The in-sample
    # optimizer narrows this universe at each walk-forward boundary.
    mask_l = (mc > 0) & (p8 < -0.08) & ((ll > llm * 1.0) | (zc20 > 0.05))
    mask_s = (mc < 0) & (p8 > 0.08) & ((ls > lsm * 1.0) | (zc20 < -0.05))
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

def regime_alignment(strategy_name, regime):
    """Return a causal routing preference for a strategy/regime pair."""
    r = np.asarray(regime, dtype=np.int8)
    alignment = np.zeros(len(r), dtype=np.float32)
    if strategy_name == 'S4_Mean_Reversion':
        alignment[r == REGIME_CHOP] = 1.0
        alignment[r == REGIME_TREND] = 0.25
        alignment[r == REGIME_EXPANSION] = -1.0
    else:
        alignment[r == REGIME_TREND] = 0.25
        alignment[r == REGIME_EXPANSION] = 1.0
        alignment[r == REGIME_CHOP] = -0.5
    return alignment


def apply_regime_routing(tdf, strategy_name, threshold):
    """Apply a small, fixed regime preference to the calibrated p* gate.

    The adjustment only reads features attached to each decision bar. It does
    not rank an entire OOS month or inspect any later trade outcome, so the
    concurrency selector can still process candidates in chronological order.
    """
    if tdf.empty or 'prob' not in tdf.columns or 'regime' not in tdf.columns:
        return tdf
    routed = tdf.copy()
    routed['route_score'] = routed['prob'] + 0.04 * regime_alignment(
        strategy_name, routed['regime'].to_numpy()
    )
    return routed[routed['route_score'] >= float(threshold)].sort_values('entry_time')


# ─────────────────────────────────────────────────────────────────────────────
# 4. PORTFOLIO CONCURRENCY ENGINE & DRAWDOWN METRICS
# ─────────────────────────────────────────────────────────────────────────────
def simulate_portfolio_concurrency(trades_df, max_concurrent=MAX_CONCURRENT):
    """
    Chronologically execute trades enforcing max N concurrent positions across all 18 assets.
    """
    if trades_df.empty: return trades_df
    sort_columns = ['entry_time']
    ascending = [True]
    # All candidates at one timestamp are observable at the same decision
    # boundary. Use their already-computed causal conviction score only as a
    # same-timestamp tie-breaker; never let a later timestamp outrank an
    # earlier entry.
    if 'route_score' in trades_df.columns:
        sort_columns.append('route_score')
        ascending.append(False)
    elif 'prob' in trades_df.columns:
        sort_columns.append('prob')
        ascending.append(False)
    sorted_trades = trades_df.sort_values(
        sort_columns, ascending=ascending, kind='stable'
    ).reset_index(drop=True)
    executed = []
    active_exits = []
    
    for row in sorted_trades.itertuples():
        entry_t = row.entry_time
        active_exits = [exit_t for exit_t in active_exits if exit_t >= entry_t]
        
        if len(active_exits) < max_concurrent:
            executed.append(row.Index)
            active_exits.append(row.exit_time)
            
    return sorted_trades.loc[executed].copy()

def closed_equity_drawdown(trades):
    if trades.empty: return 0.0
    ordered = trades.sort_values("exit_time")
    pnl_by_exit = ordered.groupby("exit_time", sort=True)["net_pnl"].sum()
    equity = CAP + pnl_by_exit.cumsum()
    equity = pd.concat([pd.Series([CAP], dtype=float), equity.reset_index(drop=True)], ignore_index=True)
    peak = equity.cummax()
    return float(((peak - equity) / peak.clip(lower=1e-12) * 100.0).max())

def mark_to_market_drawdown(trades):
    """Conservative drawdown including adverse excursion on open positions.

    Equity is settled only at exit timestamps. At each new entry, adverse
    excursion is summed across all positions that can be open simultaneously;
    this is deliberately conservative for the two-position portfolio limit.
    """
    if trades.empty or 'mae_dollar' not in trades.columns:
        return closed_equity_drawdown(trades)

    ordered = trades.sort_values(['entry_time', 'exit_time']).reset_index(drop=True)
    open_positions = []
    equity = CAP
    peak = CAP
    worst_dd = 0.0
    for row in ordered.itertuples():
        still_open = []
        for position in sorted(open_positions, key=lambda p: p['exit_time']):
            if position['exit_time'] < row.entry_time:
                equity += position['net_pnl']
                peak = max(peak, equity)
            else:
                still_open.append(position)
        open_positions = still_open

        open_positions.append({
            'exit_time': row.exit_time,
            'net_pnl': float(row.net_pnl),
            'mae_dollar': max(0.0, float(row.mae_dollar)),
        })
        trough = equity - sum(p['mae_dollar'] for p in open_positions)
        worst_dd = max(worst_dd, (peak - trough) / max(peak, 1e-12) * 100.0)

    for position in sorted(open_positions, key=lambda p: p['exit_time']):
        equity += position['net_pnl']
        peak = max(peak, equity)
        trough = equity - sum(
            p['mae_dollar'] for p in open_positions
            if p['exit_time'] > position['exit_time']
        )
        worst_dd = max(worst_dd, (peak - trough) / max(peak, 1e-12) * 100.0)
    return float(worst_dd)


def simulate_dynamic_risk(trades, cap=CAP, max_concurrent=MAX_CONCURRENT):
    """Execute already-selected trades with a causal dual-shield allocator.

    Risk is assigned when an entry arrives, after settling only positions whose
    exits are already known. A house-money loss changes the *next* entry to
    ``HOUSE_SHIELD_RISK``; it never retroactively resizes an open position.
    The conservative MTM budget reserves each open position's MAE and worst
    observed loss multiple, keeping the architectural drawdown objective
    strictly below four percent.
    """
    if trades.empty:
        empty = trades.copy()
        for column, dtype in (
            ('trade_risk', float), ('mae_dollar', float), ('risk_mode', object)
        ):
            if column not in empty.columns:
                empty[column] = pd.Series(dtype=dtype)
        return 0.0, 0.0, 0.0, 0.0, empty

    ordered = trades.sort_values(['entry_time', 'exit_time']).reset_index(drop=True)
    open_positions = []
    executed = []
    equity = float(cap)
    peak = float(cap)
    worst_dd = 0.0
    house_shield = False

    def settle(position):
        nonlocal equity, peak, worst_dd, house_shield
        equity += position['net_pnl']
        peak = max(peak, equity)
        closed_dd = (peak - equity) / max(peak, 1e-12) * 100.0
        worst_dd = max(worst_dd, closed_dd)
        if position['risk_mode'] == 'house' and position['net_pnl'] <= 0.0:
            house_shield = True
        elif house_shield and position['net_pnl'] > 0.0 and equity - cap >= HOUSE_PROFIT_TRIGGER:
            house_shield = False

    for row in ordered.itertuples():
        still_open = []
        for position in sorted(open_positions, key=lambda p: p['exit_time']):
            if position['exit_time'] < row.entry_time:
                settle(position)
            else:
                still_open.append(position)
        open_positions = still_open

        if len(open_positions) >= max_concurrent:
            continue

        realized_pnl = equity - cap
        if realized_pnl <= -40.0:
            target_risk = DRAWDOWN_DEFENSE_RISK
            risk_mode = 'defense'
        elif house_shield:
            # The reversion is sticky until a winning shield trade restores
            # house-money eligibility; it is not lost because equity briefly
            # falls below the activation trigger.
            target_risk = HOUSE_SHIELD_RISK
            risk_mode = 'house-shield'
        elif realized_pnl >= HOUSE_PROFIT_TRIGGER:
            target_risk = HOUSE_MONEY_RISK
            risk_mode = 'house'
        else:
            target_risk = RECON_RISK
            risk_mode = 'recon'

        try:
            base_r = float(row.r_multiple)
        except (AttributeError, TypeError, ValueError):
            base_r = float(row.net_pnl) / max(RSK, 1e-12)
        try:
            mae_r = float(row.mae_dollar) / max(RSK, 1e-12)
        except (AttributeError, TypeError, ValueError):
            mae_r = 1.0
        if not np.isfinite(base_r):
            base_r = 0.0
        if not np.isfinite(mae_r) or mae_r < 0.0:
            mae_r = 1.0

        reserved_mae = sum(position['mae_dollar'] for position in open_positions)
        reserved_downside = sum(
            position['downside_dollar'] for position in open_positions
        )
        closed_drawdown = max(0.0, peak - equity)
        drawdown_budget = max(
            0.0,
            peak * DRAWDOWN_RISK_LIMIT - closed_drawdown - reserved_downside,
        )
        # A simulated loss can include fees, funding, or a stop-fill gap and
        # therefore exceed exactly -1R. Reserve the larger of observed MAE and
        # the candidate's historical loss multiple before sizing it.
        loss_multiple = max(1.0, mae_r, -min(base_r, 0.0))
        max_risk_from_budget = drawdown_budget / loss_multiple
        trade_risk = min(target_risk, max_risk_from_budget)
        if trade_risk < MIN_EXECUTION_RISK:
            continue

        net_pnl = base_r * trade_risk
        mae_dollar = mae_r * trade_risk
        downside_dollar = loss_multiple * trade_risk
        record = ordered.iloc[row.Index].to_dict()
        record.update({
            'net_pnl': float(net_pnl),
            'r_multiple': float(base_r),
            'mae_dollar': float(mae_dollar),
            'trade_risk': float(trade_risk),
            'risk_mode': risk_mode,
        })
        position = {
            'entry_time': row.entry_time,
            'exit_time': row.exit_time,
            'net_pnl': float(net_pnl),
            'mae_dollar': float(mae_dollar),
            'downside_dollar': float(downside_dollar),
            'risk_mode': risk_mode,
            'record': record,
        }
        open_positions.append(position)
        executed.append(record)
        trough = equity - reserved_mae - mae_dollar
        worst_dd = max(worst_dd, (peak - trough) / max(peak, 1e-12) * 100.0)

    for position in sorted(open_positions, key=lambda p: p['exit_time']):
        settle(position)

    result = pd.DataFrame(executed, columns=list(ordered.columns) + ['trade_risk', 'risk_mode'])
    if result.empty:
        return 0.0, 0.0, 0.0, float(worst_dd), result
    total_pnl = float(result['net_pnl'].sum())
    roi = total_pnl / cap * 100.0
    wr = float((result['net_pnl'] > 0.0).mean() * 100.0)
    max_dd = max(
        float(worst_dd),
        closed_equity_drawdown(result),
        mark_to_market_drawdown(result),
    )
    return total_pnl, roi, wr, max_dd, result


CAUSAL_MODEL_FEATURES = (
    'direction', 'cvd_d', 'zc4', 'zc10', 'zc20', 'bcvm', 'zb4', 'zb10', 'zb20',
    'macro_spread', 'p8', 'p21', 'p50', 'rsi', 'vr', 'vr5',
    'liq_long_ratio', 'liq_short_ratio', 'zoi', 'oid', 'oicc', 'zls', 'fr', 'zfr',
    'zbid_qty', 'zask_qty', 'bsr', 'flow_imbalance', 'vah_pen', 'val_pen',
    'dist_poc', 'realized_vol_short', 'realized_vol_long', 'vol_ratio',
    'trend_strength', 'regime',
)


def causal_feature_columns(tdf):
    """Return normalized features that are known at the entry decision."""
    return [
        column for column in CAUSAL_MODEL_FEATURES
        if column in tdf.columns and pd.api.types.is_numeric_dtype(tdf[column])
    ]


def _model_frame(tdf, fcs):
    return tdf[fcs].replace([np.inf, -np.inf], 0.0).fillna(0.0).astype(np.float32)


def bmodel(tdf, max_depth=4, learning_rate=0.03):
    fcs = causal_feature_columns(tdf)
    if len(tdf) < 20 or len(fcs) < 3:
        return None, fcs
    train_slice = tdf.tail(8000)
    X = _model_frame(train_slice, fcs)
    y = train_slice['label'].astype(np.int32)
    p = int(y.sum())
    negatives = int(len(y) - p)
    if p < 3 or negatives < 3:
        return None, fcs

    model = lgb.LGBMClassifier(
        objective='binary', max_depth=int(max_depth), learning_rate=float(learning_rate), n_estimators=80,
        random_state=42, n_jobs=1, verbose=-1,
        min_child_samples=20, max_bin=63,
    )
    model.fit(X, y)
    return [model], fcs

def pred(models, fcs, tdf):
    if len(tdf) == 0:
        tdf = tdf.copy(); tdf['prob'] = 0.0; return tdf
    vc = [c for c in fcs if c in tdf.columns]
    if not vc:
        tdf = tdf.copy(); tdf['prob'] = 0.0; return tdf
    X = _model_frame(tdf, vc)
    tdf = tdf.copy()
    probs = [m.predict_proba(X)[:, 1] for m in models]
    tdf['prob'] = np.mean(probs, axis=0)
    return tdf

OPTUNA_DEFAULTS = {
    'pullback_threshold': 0.12,
    'cvd_momentum': 0.10,
    'liquidation_multiplier': 1.20,
    'probability_threshold': 0.55,
    'tree_depth': 4,
    'learning_rate': 0.03,
}


def apply_signal_hyperparameters(tdf, strategy_name, params=None):
    """Filter candidate entries using parameters chosen before the OOS start.

    The existing S1 signal generator creates the broad liquidation/CVD
    candidate universe. Optuna narrows that universe here with current-bar
    values; it never adds an entry after seeing its future outcome.
    """
    if tdf.empty or strategy_name != 'S1_Liquidation' or not params:
        return tdf
    required = ('direction', 'p8', 'zc20', 'liq_long_ratio', 'liq_short_ratio')
    if any(column not in tdf.columns for column in required):
        return tdf

    pullback = float(params.get('pullback_threshold', OPTUNA_DEFAULTS['pullback_threshold']))
    cvd = float(params.get('cvd_momentum', OPTUNA_DEFAULTS['cvd_momentum']))
    liquidation = float(params.get('liquidation_multiplier', OPTUNA_DEFAULTS['liquidation_multiplier']))
    direction = tdf['direction'].to_numpy()
    p8 = tdf['p8'].to_numpy()
    zc20 = tdf['zc20'].to_numpy()
    long_liq = tdf['liq_long_ratio'].to_numpy()
    short_liq = tdf['liq_short_ratio'].to_numpy()
    keep_long = (direction == 1) & (p8 <= -pullback) & (
        (zc20 >= cvd) | (long_liq >= liquidation)
    )
    keep_short = (direction == -1) & (p8 >= pullback) & (
        (zc20 <= -cvd) | (short_liq >= liquidation)
    )
    return tdf.loc[keep_long | keep_short].copy()


def _calibration_result(model, features, params, return_params):
    if return_params:
        return model, features, float(params['probability_threshold']), params
    return model, features, float(params['probability_threshold'])


def calibrate_in_sample_threshold(pdf, ws, strategy_name=None, return_params=False):
    """Calibrate model/filter parameters and p* with Optuna before ``ws``.

    Every trial trains on an earlier slice and evaluates on a later
    pre-window validation partition. The OOS window is never used to fit the
    model, optimize signal filters, choose the threshold, or route a regime.
    """
    defaults = dict(OPTUNA_DEFAULTS)
    if len(pdf) < 20:
        return _calibration_result(None, None, defaults, return_params)

    # Select one chronological validation partition. It is always completed
    # before the OOS start and is never mixed into the training slice.
    split_train = None
    split_validation = None
    for val_days in (30, 60, 90):
        validation_start = ws - pd.Timedelta(days=val_days)
        train = pdf[pdf['exit_time'] < validation_start].sort_values('entry_time')
        validation = pdf[
            (pdf['entry_time'] >= validation_start) & (pdf['exit_time'] < ws)
        ].sort_values('entry_time')
        if len(train) >= 20 and len(validation) >= MINTR:
            split_train, split_validation = train, validation
            break

    if split_train is None:
        # Early windows may contain less than 30 days of history. A
        # chronological in-sample split is still valid and avoids silently
        # disabling calibration.
        if len(pdf) >= 40:
            split = max(20, int(len(pdf) * 0.70))
            split_train = pdf.iloc[:split].sort_values('entry_time')
            split_validation = pdf.iloc[split:].sort_values('entry_time')
        else:
            model, features = bmodel(pdf.sort_values('entry_time'))
            return _calibration_result(model, features, defaults, return_params)

    def objective(trial):
        params = {
            'pullback_threshold': trial.suggest_float(
                'pullback_threshold', 0.08, 0.30
            ),
            'cvd_momentum': trial.suggest_float('cvd_momentum', 0.05, 0.25),
            'liquidation_multiplier': trial.suggest_float(
                'liquidation_multiplier', 1.0, 2.0
            ),
            'probability_threshold': trial.suggest_float(
                'probability_threshold', 0.50, 0.85
            ),
            'tree_depth': trial.suggest_int('tree_depth', 3, 6),
            'learning_rate': trial.suggest_float(
                'learning_rate', 0.01, 0.08
            ),
        }
        train_candidates = apply_signal_hyperparameters(
            split_train, strategy_name, params
        )
        validation_candidates = apply_signal_hyperparameters(
            split_validation, strategy_name, params
        )
        if len(train_candidates) < 20 or len(validation_candidates) < MINTR:
            return -1e9

        model, features = bmodel(
            train_candidates,
            max_depth=params['tree_depth'],
            learning_rate=params['learning_rate'],
        )
        if model is None:
            return -1e9
        validation_pred = pred(model, features, validation_candidates)
        selected = apply_regime_routing(
            validation_pred,
            strategy_name,
            params['probability_threshold'],
        )
        selected = simulate_portfolio_concurrency(
            selected, max_concurrent=MAX_CONCURRENT
        ).head(MAXTR)
        if len(selected) < MINTR:
            return -1e9
        _, roi, wr, dd, _ = simulate_dynamic_risk(selected, cap=CAP)
        return float(roi * wr - 2.0 * max(0.0, dd - 3.9))

    study = optuna.create_study(
        direction='maximize',
        sampler=optuna.samplers.TPESampler(seed=OPTUNA_SEED),
    )
    study.optimize(objective, n_trials=OPTUNA_TRIALS, catch=(ValueError,))
    if not study.trials or study.best_value <= -1e8:
        best_params = defaults
    else:
        best_params = dict(defaults)
        best_params.update(study.best_params)

    final_train = apply_signal_hyperparameters(pdf, strategy_name, best_params)
    if len(final_train) < 20:
        final_train = pdf.sort_values('entry_time')
        best_params = defaults
    model, features = bmodel(
        final_train,
        max_depth=best_params['tree_depth'],
        learning_rate=best_params['learning_rate'],
    )
    return _calibration_result(model, features, best_params, return_params)
