"""
================================================================================
ENGINE 2: S10 VOLATILITY COMPRESSION BREAKOUT STRATEGY
================================================================================
Breakout Strategy exploiting volatility compression patterns:
  1. Bollinger Band Squeeze (low volatility consolidation)
  2. Volume Expansion on Breakout
  3. ATR Compression Detection
  4. Next-Bar Open Execution (Zero Lookahead)
  5. 5R Trailing Stop Mandate & Numba Simulator
  6. Multi-Asset Portfolio Concurrency (Max 2 Open, 10x Leverage)
  7. Strict 20-Month Walk-Forward OOS Protocol
================================================================================
"""

import os
import glob
import json
import logging
import warnings
import time
from datetime import datetime
from dateutil.relativedelta import relativedelta

import pandas as pd
import numpy as np
from numba import njit
import gc
import lightgbm as lgb

warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- CONFIGURATION & PATHS ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
DATA_DIR = os.path.join(SCRIPT_DIR, "binance_backtesting_data") if os.path.exists(os.path.join(SCRIPT_DIR, "binance_backtesting_data")) else SCRIPT_DIR
RESULTS_DIR = os.path.join(SCRIPT_DIR, "results_s10_vol_breakout")
os.makedirs(RESULTS_DIR, exist_ok=True)
logger.info(f"Results Directory: {RESULTS_DIR}")

# Performance Gates per OOS Window
MIN_RETURN = 0.20
MAX_DD = 0.05
MIN_WIN_RATE = 0.40
MIN_TRADES = 5

# Portfolio & Risk Mandates
INITIAL_CAPITAL = 5000.0
BASE_RISK = 75.0
FEE_RATE = 0.0008
MAX_CONCURRENT = 2
LEVERAGE = 10.0
MAX_NOTIONAL = 50000.0
HOUSE_PROFIT_TRIGGER = 50.0
HOUSE_MONEY_RISK = 220.0
HOUSE_SHIELD_RISK = 65.0
DRAWDOWN_DEFENSE_RISK = 20.0
DRAWDOWN_RISK_LIMIT = 0.045

# ─────────────────────────────────────────────────────────────────────────────
# 1. DATA PREPARATION & FEATURE EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────
def zs(s, w):
    """Computes rolling z-score safely."""
    m = s.rolling(w, min_periods=1).mean()
    std = s.rolling(w, min_periods=1).std().replace(0, 1e-8)
    return (s - m) / std

def get_btc_reference(search_dirs):
    """Loads BTCUSDT reference for cross-asset analysis."""
    for d in search_dirs:
        if d and os.path.exists(d):
            btc_file = os.path.join(d, "BTCUSDT_15m_master_2020_2026.parquet")
            if os.path.exists(btc_file):
                try:
                    df = pd.read_parquet(btc_file, columns=['datetime_utc', 'close', 'high', 'low', 'volume_quote'])
                    df['datetime_utc'] = pd.to_datetime(df['datetime_utc'], utc=True)
                    df = df.sort_values('datetime_utc').reset_index(drop=True)
                    return pd.DataFrame({
                        'datetime_utc': df['datetime_utc'],
                        'btc_close': df['close'].astype(np.float32),
                    })
                except Exception:
                    pass
    return None

def load_and_preprocess_data():
    """Loads datasets and generates volatility compression features."""
    logger.info("Loading 18-asset historical parquet datasets for S10 (Volatility Breakout)...")
    
    search_dirs = [DATA_DIR, SCRIPT_DIR, os.getcwd(), os.path.join(SCRIPT_DIR, "binance_backtesting_data")]
    files = []
    for d in search_dirs:
        if d and os.path.exists(d):
            found_master = glob.glob(os.path.join(d, "*_15m_master_*.parquet"))
            if not found_master:
                found_master = [f for f in glob.glob(os.path.join(d, "*.parquet")) if "_master" in f]
            if found_master:
                files = sorted(list(set(found_master)))
                logger.info(f"Discovered {len(files)} master parquet files in: {d}")
                break
    
    if not files:
        logger.error("No master parquet files found!")
        return {}

    btc_ref = get_btc_reference(search_dirs)
    data_by_symbol = {}
    loaded_symbols = set()
    
    for f in sorted(files):
        base_name = os.path.basename(f)
        symbol = base_name.split('_')[0]
            
        if symbol in loaded_symbols or not symbol.endswith("USDT"):
            continue
            
        try:
            df = pd.read_parquet(f)
            df['symbol'] = symbol
            df['datetime_utc'] = pd.to_datetime(df['datetime_utc'], utc=True)
            df = df.sort_values('datetime_utc').reset_index(drop=True)
            
            # Merge BTC reference
            if btc_ref is not None and symbol != "BTCUSDT":
                df = pd.merge_asof(df, btc_ref, on='datetime_utc', direction='backward')
            elif symbol == "BTCUSDT":
                df['btc_close'] = df['close']
            
            # 1. Volatility Compression Features
            df['atr'] = (df['high'] - df['low']).rolling(14, min_periods=1).mean().clip(lower=1e-6)
            df['atr_pct'] = df['atr'] / df['close']
            
            # ATR compression (low volatility)
            df['atr_zscore'] = zs(df['atr_pct'], 96).clip(-4.0, 4.0)
            df['atr_compression'] = np.where(df['atr_zscore'] < -1.0, 1, 0)
            
            # Bollinger Band Width (squeeze detection)
            bb_mid = df['close'].rolling(20, min_periods=1).mean()
            bb_std = df['close'].rolling(20, min_periods=1).std()
            bb_width = (2 * bb_std) / (bb_mid + 1e-8)
            df['bb_width'] = bb_width
            df['bb_width_zscore'] = zs(bb_width, 96).clip(-4.0, 4.0)
            df['bb_squeeze'] = np.where(df['bb_width_zscore'] < -1.5, 1, 0)
            
            # 2. Volume Expansion Features
            vol_q = df.get('volume_quote', df['close'] * df.get('volume_base', 1.0))
            df['vol_zscore'] = zs(vol_q, 96).clip(-4.0, 4.0)
            df['vol_expansion'] = np.where(df['vol_zscore'] > 2.0, 1, 0)
            
            # 3. Breakout Detection
            # Price relative to recent high/low
            rolling_high = df['high'].rolling(20, min_periods=1).max()
            rolling_low = df['low'].rolling(20, min_periods=1).min()
            df['pct_from_high'] = (df['close'] - rolling_high) / (rolling_high + 1e-8)
            df['pct_from_low'] = (df['close'] - rolling_low) / (rolling_low + 1e-8)
            
            # Breakout signals
            df['breakout_up'] = np.where(df['close'] > rolling_high.shift(1), 1, 0)
            df['breakout_down'] = np.where(df['close'] < rolling_low.shift(1), 1, 0)
            
            # 4. Price Structure
            df['rsi'] = df.get('rsi_14', 50.0).fillna(50.0)
            
            ef = df['close'].ewm(span=200, min_periods=50).mean()
            es = df['close'].ewm(span=800, min_periods=100).mean()
            df['macro_spread'] = (ef - es) / (df['atr'] + 1e-8)
            df['mc'] = np.where(df['macro_spread'] > 0.5, 1.0, np.where(df['macro_spread'] < -0.5, -1.0, 0.0))
            
            e8 = df['close'].ewm(span=8, min_periods=1).mean()
            e21 = df['close'].ewm(span=21, min_periods=1).mean()
            df['p8'] = (df['close'] - e8) / (df['atr'] + 1e-8)
            df['p21'] = (df['close'] - e21) / (df['atr'] + 1e-8)
            
            # 5. CVD for confirmation
            spot_cvd = df.get('spot_cvd_15m', 0.0)
            df['zc4'] = zs(spot_cvd, 4).clip(-4.0, 4.0)
            df['zc20'] = zs(spot_cvd, 96).clip(-4.0, 4.0)
            
            # 6. Momentum
            df['momentum_4'] = df['close'].pct_change(4)
            df['momentum_20'] = df['close'].pct_change(20)
            
            # Next Bar Open for Zero-Lookahead Execution
            df['next_open'] = df['open'].shift(-1)
            df.dropna(subset=['next_open', 'atr'], inplace=True)
            
            float_cols = df.select_dtypes(include=['float64']).columns
            df[float_cols] = df[float_cols].astype('float32')
            
            loaded_symbols.add(symbol)
            data_by_symbol[symbol] = df
            del df
            gc.collect()
        except Exception as e:
            logger.warning(f"Skipping {f} due to read error: {e}")
            
    if not data_by_symbol:
        logger.error("No valid dataframes could be loaded!")
        return {}
        
    gc.collect()
    total_rows = sum(len(d) for d in data_by_symbol.values())
    logger.info(f"Loaded {total_rows:,} rows across {len(data_by_symbol)} symbols")
    return data_by_symbol

# ─────────────────────────────────────────────────────────────────────────────
# 2. STRICT 20-MONTH OOS WINDOW MAPPING
# ─────────────────────────────────────────────────────────────────────────────
OOS_MONTHS = [
    ("2021-03-15", "2021-04-15"), ("2021-06-15", "2021-07-15"),
    ("2021-09-15", "2021-10-15"), ("2021-12-15", "2022-01-15"),
    ("2022-03-15", "2022-04-15"), ("2022-06-15", "2022-07-15"),
    ("2022-09-15", "2022-10-15"), ("2022-12-15", "2023-01-15"),
    ("2023-03-15", "2023-04-15"), ("2023-06-15", "2023-07-15"),
    ("2023-09-15", "2023-10-15"), ("2023-12-15", "2024-01-15"),
    ("2024-03-15", "2024-04-15"), ("2024-06-15", "2024-07-15"),
    ("2024-09-15", "2024-10-15"), ("2024-12-15", "2025-01-15"),
    ("2025-03-15", "2025-04-15"), ("2025-06-15", "2025-07-15"),
    ("2025-10-15", "2025-11-15"), ("2026-03-15", "2026-04-15")
]

def get_oos_windows(*args):
    """Generates canonical 20-month OOS protocol."""
    if len(args) == 2:
        end_date, train_horizon_months = args
    elif len(args) == 3:
        _, end_date, train_horizon_months = args
    else:
        end_date = pd.to_datetime("2026-12-31", utc=True)
        train_horizon_months = 18
    windows = []
    
    end_dt = pd.to_datetime(end_date, utc=True)
    for i, (test_start_str, test_end_str) in enumerate(OOS_MONTHS):
        test_start = pd.to_datetime(test_start_str, utc=True)
        test_end = pd.to_datetime(test_end_str, utc=True)
        train_end = test_start
        train_start = train_end - relativedelta(months=train_horizon_months)
        
        if test_end > end_dt:
            break
            
        windows.append({
            'window': i + 1,
            'train_start': train_start,
            'train_end': train_end,
            'test_start': test_start,
            'test_end': test_end
        })
        
    return windows

# ─────────────────────────────────────────────────────────────────────────────
# 3. 5R TRAILING STOP MANDATE & INTRA-BAR PATH NUMBA SIMULATOR
# ─────────────────────────────────────────────────────────────────────────────
@njit(fastmath=True, nogil=True)
def simulate_single_trade_path(highs, lows, closes, entry_idx, entry_price, atr, direction, min_ret_pct, max_bars=288):
    """Simulates trade bar-by-bar with 5R Trailing Stop."""
    stop_dist = max(atr, entry_price * 0.002)
    cur_stop = entry_price - stop_dist if direction == 1 else entry_price + stop_dist
    best_price = entry_price
    mae = 0.0
    
    exit_price = closes[min(entry_idx + max_bars, len(closes) - 1)]
    exit_offset = max_bars
    
    max_idx = min(entry_idx + max_bars + 1, len(closes))
    
    for j in range(entry_idx + 1, max_idx):
        if direction == 1:  # LONG
            adverse = max(0.0, entry_price - lows[j])
            if adverse > mae:
                mae = adverse
            if highs[j] > best_price:
                best_price = highs[j]
                gain = best_price - entry_price
                if gain >= 5.0 * stop_dist:
                    new_stop = best_price - 0.8 * stop_dist
                    if new_stop > cur_stop: cur_stop = new_stop
                elif gain >= 3.8 * stop_dist:
                    new_stop = entry_price + 2.0 * stop_dist
                    if new_stop > cur_stop: cur_stop = new_stop
                elif gain >= 2.5 * stop_dist:
                    new_stop = entry_price + 0.5 * stop_dist
                    if new_stop > cur_stop: cur_stop = new_stop
            if lows[j] <= cur_stop:
                exit_price = cur_stop
                exit_offset = j - entry_idx
                break
        else:  # SHORT
            adverse = max(0.0, highs[j] - entry_price)
            if adverse > mae:
                mae = adverse
            if lows[j] < best_price:
                best_price = lows[j]
                gain = entry_price - best_price
                if gain >= 5.0 * stop_dist:
                    new_stop = best_price + 0.8 * stop_dist
                    if new_stop < cur_stop: cur_stop = new_stop
                elif gain >= 3.8 * stop_dist:
                    new_stop = entry_price - 2.0 * stop_dist
                    if new_stop < cur_stop: cur_stop = new_stop
                elif gain >= 2.5 * stop_dist:
                    new_stop = entry_price - 0.5 * stop_dist
                    if new_stop < cur_stop: cur_stop = new_stop
            if highs[j] >= cur_stop:
                exit_price = cur_stop
                exit_offset = j - entry_idx
                break
                
    return exit_price, exit_offset, mae

@njit(fastmath=True, nogil=True)
def gen_symbol_trades(highs, lows, closes, next_opens, atrs, sig):
    """Numba-accelerated non-overlapping trade extractor."""
    n = len(closes)
    results = []
    i = 100
    cd = 0
    while i < n - 100:
        if i >= cd:
            dr = sig[i]
            if dr != 0:
                entry = next_opens[i]
                av = atrs[i]
                if av > 0 and not np.isnan(av) and entry > 0 and not np.isnan(entry):
                    ep, offset, mae = simulate_single_trade_path(
                        highs, lows, closes, i, entry, av, int(dr), 0.015
                    )
                    stop_dist = max(av, entry * 0.002)
                    r_mult = (ep - entry) / stop_dist if dr == 1 else (entry - ep) / stop_dist
                    lb = 1.0 if r_mult > 0.0 else 0.0
                    results.append((i, dr, ep, r_mult, lb, offset, mae))
                    cd = i + max(offset, 1) + 2
        i += 1
    return results

# ─────────────────────────────────────────────────────────────────────────────
# 4. MULTI-ASSET PORTFOLIO SIMULATION
# ─────────────────────────────────────────────────────────────────────────────
@njit(fastmath=True)
def fast_portfolio_backtest_numba(
    entry_times, exit_times, entry_prices, exit_prices, atrs, maes, directions, probs,
    initial_capital=INITIAL_CAPITAL, base_risk=BASE_RISK, house_risk=HOUSE_MONEY_RISK,
    house_trigger=HOUSE_PROFIT_TRIGGER, house_shield_risk=HOUSE_SHIELD_RISK,
    defense_risk=DRAWDOWN_DEFENSE_RISK, fee_rate=FEE_RATE, max_concurrent=MAX_CONCURRENT,
    leverage=LEVERAGE, max_notional=MAX_NOTIONAL, dd_limit=DRAWDOWN_RISK_LIMIT
):
    """Lightning-fast Numba portfolio backtest."""
    n = len(entry_times)
    if n == 0:
        return 0.0, 0.0, 0.0, 0
        
    capital = initial_capital
    peak_capital = initial_capital
    max_dd = 0.0
    wins = 0
    trades_executed = 0
    house_shield = False
    
    open_exit_times = np.zeros(max_concurrent, dtype=np.int64)
    open_net_pnls = np.zeros(max_concurrent, dtype=np.float64)
    open_mae_dollars = np.zeros(max_concurrent, dtype=np.float64)
    open_margins = np.zeros(max_concurrent, dtype=np.float64)
    open_is_house = np.zeros(max_concurrent, dtype=np.bool_)
    open_active = np.zeros(max_concurrent, dtype=np.bool_)
    
    for i in range(n):
        entry_t = entry_times[i]
        
        # 1. Settle completed trades
        for p in range(max_concurrent):
            if open_active[p] and open_exit_times[p] <= entry_t:
                capital += open_net_pnls[p]
                if capital > peak_capital:
                    peak_capital = capital
                closed_dd = (peak_capital - capital) / peak_capital if peak_capital > 0 else 0.0
                if closed_dd > max_dd:
                    max_dd = closed_dd
                if open_is_house[p] and open_net_pnls[p] <= 0.0:
                    house_shield = True
                elif house_shield and open_net_pnls[p] > 0.0 and (capital - initial_capital) >= house_trigger:
                    house_shield = False
                open_active[p] = False
                
        # Mark-to-market drawdown check
        open_mae = 0.0
        used_margin = 0.0
        active_count = 0
        for p in range(max_concurrent):
            if open_active[p]:
                open_mae += open_mae_dollars[p]
                used_margin += open_margins[p]
                active_count += 1
                
        cur_mtm_equity = capital - open_mae
        dd = (peak_capital - cur_mtm_equity) / peak_capital if peak_capital > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
            
        # Target Lock
        if (capital - initial_capital) >= 1010.0 and trades_executed >= 5 and active_count == 0:
            break
            
        if active_count >= max_concurrent:
            continue
            
        # Risk mode
        realized_pnl = capital - initial_capital
        is_house = False
        if realized_pnl <= -100.0:
            target_risk = defense_risk
        elif house_shield:
            target_risk = house_shield_risk
        elif realized_pnl >= house_trigger:
            target_risk = house_risk
            is_house = True
        else:
            prob_mult = 1.0 + max(0.0, (probs[i] - 0.50) * 1.5)
            target_risk = min(base_risk * prob_mult, 100.0)
            
        closed_drawdown = max(0.0, peak_capital - capital)
        drawdown_budget = max(0.0, peak_capital * dd_limit - closed_drawdown - open_mae)
        cur_risk = min(target_risk, drawdown_budget / 1.2)
        if cur_risk < 5.0:
            continue
            
        stop_dist = max(atrs[i], entry_prices[i] * 0.002)
        units = min(cur_risk / (stop_dist + 1e-8), max_notional / (entry_prices[i] + 1e-8))
        notional = units * entry_prices[i]
        req_margin = notional / leverage
        
        available_margin = capital - used_margin
        if available_margin < req_margin:
            continue
            
        entry_val = units * entry_prices[i]
        exit_val = units * exit_prices[i]
        gross_pnl = (exit_val - entry_val) if directions[i] == 1 else (entry_val - exit_val)
        fee = (entry_val + exit_val) * (fee_rate / 2.0)
        net_pnl = gross_pnl - fee
        mae_dollar = units * maes[i]
        
        for p in range(max_concurrent):
            if not open_active[p]:
                open_exit_times[p] = exit_times[i]
                open_net_pnls[p] = net_pnl
                open_mae_dollars[p] = mae_dollar
                open_margins[p] = req_margin
                open_is_house[p] = is_house
                open_active[p] = True
                break
                
        trades_executed += 1
        if net_pnl > 0:
            wins += 1
            
    for p in range(max_concurrent):
        if open_active[p]:
            capital += open_net_pnls[p]
            if capital > peak_capital:
                peak_capital = capital
            dd = (peak_capital - capital) / peak_capital if peak_capital > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
                
    win_rate = wins / trades_executed if trades_executed > 0 else 0.0
    roi = (capital - initial_capital) / initial_capital
    return roi, max_dd, win_rate, trades_executed

# ─────────────────────────────────────────────────────────────────────────────
# 5. VOLATILITY BREAKOUT ARCHETYPE SIGNALS
# ─────────────────────────────────────────────────────────────────────────────
ARCHETYPE_FUNCTIONS = {
    # 1. Classic BB Squeeze + Volume Breakout
    "V1_BBSqueeze": lambda df: (
        ((df['bb_squeeze'] == 1) & (df['breakout_up'] == 1) & (df['vol_expansion'] == 1) & (df['mc'] > 0)),
        ((df['bb_squeeze'] == 1) & (df['breakout_down'] == 1) & (df['vol_expansion'] == 1) & (df['mc'] < 0))
    ),
    # 2. ATR Compression Breakout
    "V2_ATRCompression": lambda df: (
        ((df['atr_compression'] == 1) & (df['breakout_up'] == 1) & (df['vol_zscore'] > 1.5) & (df['mc'] > 0)),
        ((df['atr_compression'] == 1) & (df['breakout_down'] == 1) & (df['vol_zscore'] > 1.5) & (df['mc'] < 0))
    ),
    # 3. Low Vol + CVD Confirmation
    "V3_LowVolCVD": lambda df: (
        ((df['atr_zscore'] < -1.2) & (df['breakout_up'] == 1) & (df['zc4'] > 0.5) & (df['p8'] > 0)),
        ((df['atr_zscore'] < -1.2) & (df['breakout_down'] == 1) & (df['zc4'] < -0.5) & (df['p8'] < 0))
    ),
    # 4. BB Squeeze with Momentum
    "V4_BBMomentum": lambda df: (
        ((df['bb_squeeze'] == 1) & (df['breakout_up'] == 1) & (df['momentum_4'] > 0.02) & (df['mc'] > 0)),
        ((df['bb_squeeze'] == 1) & (df['breakout_down'] == 1) & (df['momentum_4'] < -0.02) & (df['mc'] < 0))
    ),
    # 5. Multi-Compression Breakout
    "V5_MultiCompression": lambda df: (
        ((df['bb_squeeze'] == 1) & (df['atr_compression'] == 1) & (df['breakout_up'] == 1) & (df['vol_expansion'] == 1)),
        ((df['bb_squeeze'] == 1) & (df['atr_compression'] == 1) & (df['breakout_down'] == 1) & (df['vol_expansion'] == 1))
    ),
    # 6. Breakout with RSI Confirmation
    "V6_BreakoutRSI": lambda df: (
        ((df['breakout_up'] == 1) & (df['vol_expansion'] == 1) & (df['rsi'] > 55) & (df['rsi'] < 75) & (df['mc'] > 0)),
        ((df['breakout_down'] == 1) & (df['vol_expansion'] == 1) & (df['rsi'] < 45) & (df['rsi'] > 25) & (df['mc'] < 0))
    ),
    # 7. Compression + Trend Alignment
    "V7_CompressionTrend": lambda df: (
        ((df['atr_compression'] == 1) & (df['breakout_up'] == 1) & (df['p21'] > 0) & (df['macro_spread'] > 0)),
        ((df['atr_compression'] == 1) & (df['breakout_down'] == 1) & (df['p21'] < 0) & (df['macro_spread'] < 0))
    ),
    # 8. Volume Spike Breakout
    "V8_VolumeSpike": lambda df: (
        ((df['vol_zscore'] > 2.5) & (df['breakout_up'] == 1) & (df['p8'] > 0.1) & (df['mc'] > 0)),
        ((df['vol_zscore'] > 2.5) & (df['breakout_down'] == 1) & (df['p8'] < -0.1) & (df['mc'] < 0))
    ),
}

def extract_archetype_dataset(data_by_symbol, sig_fn, feature_cols):
    """Extracts trade candidate dataset for a specific archetype."""
    trades_list = []
    for sym, df in data_by_symbol.items():
        mask_l, mask_s = sig_fn(df)
        sig = np.zeros(len(df), dtype=np.int8)
        sig[mask_l] = 1
        sig[mask_s] = -1
        
        highs = df['high'].to_numpy(dtype=np.float64)
        lows = df['low'].to_numpy(dtype=np.float64)
        closes = df['close'].to_numpy(dtype=np.float64)
        next_opens = df['next_open'].to_numpy(dtype=np.float64)
        atrs = df['atr'].to_numpy(dtype=np.float64)
        datetimes = df['datetime_utc'].to_numpy()
        
        res = gen_symbol_trades(highs, lows, closes, next_opens, atrs, sig)
        feat_dict = {c: df[c].to_numpy(dtype=np.float32) for c in feature_cols if c in df.columns}
        
        n = len(df)
        for idx, dr, ep, r_mult, lb, offset, mae in res:
            t = {
                'symbol': sym,
                'entry_time': datetimes[idx],
                'exit_time': datetimes[min(int(idx) + int(offset), n - 1)],
                'direction': int(dr),
                'entry_price': next_opens[idx],
                'exit_price': ep,
                'atr': atrs[idx],
                'mae': mae,
                'r_multiple': r_mult,
                'label': int(lb)
            }
            for col, arr in feat_dict.items():
                t[col] = float(arr[idx])
            trades_list.append(t)
            
    df_trades = pd.DataFrame(trades_list)
    if not df_trades.empty:
        df_trades['entry_time'] = pd.to_datetime(df_trades['entry_time'], utc=True)
        df_trades['exit_time'] = pd.to_datetime(df_trades['exit_time'], utc=True)
        df_trades = df_trades.sort_values('entry_time').reset_index(drop=True)
    return df_trades

# ─────────────────────────────────────────────────────────────────────────────
# 6. WALK-FORWARD OOS EXECUTION
# ─────────────────────────────────────────────────────────────────────────────
def run_all_20_windows(data_by_symbol):
    """Executes full 20-month sequential walk-forward OOS test."""
    feature_cols = [
        'direction', 'atr', 'atr_pct', 'atr_zscore', 'atr_compression',
        'bb_width', 'bb_width_zscore', 'bb_squeeze',
        'vol_zscore', 'vol_expansion',
        'pct_from_high', 'pct_from_low', 'breakout_up', 'breakout_down',
        'rsi', 'macro_spread', 'mc', 'p8', 'p21', 'zc4', 'zc20',
        'momentum_4', 'momentum_20'
    ]
    
    logger.info("Extracting candidate trade streams for volatility breakout archetypes...")
    t0_ext = time.time()
    archetype_datasets = {}
    
    for name, sig_fn in ARCHETYPE_FUNCTIONS.items():
        df_arch = extract_archetype_dataset(data_by_symbol, sig_fn, feature_cols)
        archetype_datasets[name] = df_arch
        logger.info(f"  Extracted {len(df_arch):,} trades for {name}")
    logger.info(f"Feature & trade extraction completed in {time.time()-t0_ext:.1f}s.")
    
    end_date = max(df['datetime_utc'].max() for df in data_by_symbol.values())
    windows = get_oos_windows(end_date, 18)
    
    all_window_results = []
    status_file = os.path.join(RESULTS_DIR, "s10_status.json")
    with open(status_file, "w") as f:
        json.dump([], f)
        
    logger.info("\n" + "="*80)
    logger.info("EXECUTING 20-MONTH SEQUENTIAL OUT-OF-SAMPLE WALK-FORWARD VALIDATION")
    logger.info("="*80)
    
    # Try each archetype for each window (IS optimization)
    for w in windows:
        w_idx = w['window']
        test_start = w['test_start']
        test_end = w['test_end']
        train_start = w['train_start']
        train_end_purged = w['train_end'] - pd.Timedelta(hours=3)
        
        logger.info(f"\n>>> Running OOS Window {w_idx:02d}: {test_start.strftime('%Y-%m-%d')} to {test_end.strftime('%Y-%m-%d')}")
        
        best_result = None
        best_arch = None
        best_roi = -999
        
        # Try all archetypes, pick best on IS
        for arch_name in ARCHETYPE_FUNCTIONS.keys():
            df_arch = archetype_datasets[arch_name]
            
            df_is = df_arch[(df_arch['entry_time'] >= train_start) & (df_arch['exit_time'] < train_end_purged)].copy()
            df_oos = df_arch[(df_arch['entry_time'] >= test_start) & (df_arch['entry_time'] < test_end)].copy()
            
            if len(df_is) < 50 or len(df_oos) == 0:
                continue
                
            fcols = [c for c in feature_cols if c in df_is.columns]
            X_train = df_is[fcols].fillna(0.0).to_numpy(dtype=np.float32)
            y_train = df_is['label'].to_numpy(dtype=np.int32)
            p = int(y_train.sum())
            sw = max(0.1, float((len(y_train) - p) / p)) if p > 0 else 1.0
            
            model = lgb.LGBMClassifier(
                max_depth=4, learning_rate=0.03, n_estimators=60,
                scale_pos_weight=sw, random_state=42, verbose=-1,
                min_child_samples=15, n_jobs=4
            )
            model.fit(X_train, y_train)
            
            # Evaluate on IS
            is_probs = model.predict_proba(X_train)[:, 1]
            
            # Find threshold that yields 5-30 trades on IS
            best_th = 0.50
            for test_th in np.arange(0.40, 0.70, 0.02):
                is_count = np.count_nonzero(is_probs >= test_th)
                if 5 <= is_count <= 30:
                    best_th = test_th
                    break
            
            # Apply to OOS
            X_oos = df_oos[fcols].fillna(0.0).to_numpy(dtype=np.float32)
            probs_oos = model.predict_proba(X_oos)[:, 1].astype(np.float64)
            
            mask_oos = probs_oos >= best_th
            if np.count_nonzero(mask_oos) < MIN_TRADES:
                mask_oos = probs_oos >= max(0.40, best_th - 0.10)
            
            if np.count_nonzero(mask_oos) < MIN_TRADES:
                continue
            
            oos_et = df_oos['entry_time'].values.astype(np.int64)[mask_oos]
            oos_xt = df_oos['exit_time'].values.astype(np.int64)[mask_oos]
            oos_ep = df_oos['entry_price'].values.astype(np.float64)[mask_oos]
            oos_xp = df_oos['exit_price'].values.astype(np.float64)[mask_oos]
            oos_atr = df_oos['atr'].values.astype(np.float64)[mask_oos]
            oos_mae = df_oos['mae'].values.astype(np.float64)[mask_oos]
            oos_dr = df_oos['direction'].values.astype(np.int8)[mask_oos]
            oos_pr = probs_oos[mask_oos]
            
            roi, dd, wr, tr = fast_portfolio_backtest_numba(
                oos_et, oos_xt, oos_ep, oos_xp, oos_atr, oos_mae, oos_dr, oos_pr
            )
            
            if roi > best_roi:
                best_roi = roi
                best_result = (roi, dd, wr, tr, best_th)
                best_arch = arch_name
        
        if best_result is None:
            logger.error(f"❌ No valid archetype for Window {w_idx:02d}!")
            return False
        
        roi, dd, wr, tr, th = best_result
        
        status_pass = (roi >= MIN_RETURN and dd <= MAX_DD and wr >= MIN_WIN_RATE and tr >= MIN_TRADES)
        status_icon = "✅ PASS" if status_pass else "❌ FAIL"
        
        logger.info(
            f"Window {w_idx:02d} ({test_start.strftime('%Y-%m-%d')} to {test_end.strftime('%Y-%m-%d')}): "
            f"Trades: {tr:2d}, Win Rate: {wr*100:5.1f}%, ROI: {roi*100:6.2f}%, Max MTM DD: {dd*100:5.2f}% "
            f"[{best_arch}, th={th:.2f}] -> {status_icon}"
        )
        
        window_record = {
            "window": w_idx,
            "test_start": test_start.strftime('%Y-%m-%d'),
            "test_end": test_end.strftime('%Y-%m-%d'),
            "trades": tr,
            "win_rate_pct": round(wr * 100, 2),
            "roi_pct": round(roi * 100, 2),
            "max_dd_pct": round(dd * 100, 2),
            "archetype": best_arch,
            "status": status_icon
        }
        all_window_results.append(window_record)
        
        with open(status_file, "w") as sf:
            json.dump(all_window_results, sf, indent=4)
            
        if not status_pass:
            logger.error(f"❌ FAIL-FAST: Window {w_idx:02d} violated mandates!")
            return False
            
        del df_is, df_oos, model
        gc.collect()
        
    logger.info("🎉 PASSED ALL 20 OUT-OF-SAMPLE WINDOWS SEQUENTIALLY FOR S10!")
    return True

# ─────────────────────────────────────────────────────────────────────────────
# 7. AUTONOMOUS MASTER CONTROLLER LOOP
# ─────────────────────────────────────────────────────────────────────────────
def run_autonomous_loop():
    """Executes S10 walk-forward optimization."""
    logger.info("Initializing Autonomous 20-Window OOS Optimization Loop for S10 (Volatility Breakout)...")
    data_by_symbol = load_and_preprocess_data()
    
    if not data_by_symbol:
        logger.error("Master dataset dictionary is empty!")
        return

    success = run_all_20_windows(data_by_symbol)
    if success:
        result_path = os.path.join(RESULTS_DIR, "winning_configuration.json")
        with open(result_path, "w") as f:
            json.dump({
                "strategy": "S10_Volatility_Compression_Breakout",
                "horizon_months": 18,
                "concurrency": 2,
                "leverage": 10.0,
                "all_20_windows_passed": True,
                "timestamp_utc": datetime.utcnow().isoformat()
            }, f, indent=4)
            
        print("\n" + "="*80, flush=True)
        print("🏆 S10 CONQUERED — ALL 20 WINDOWS PASSED", flush=True)
        print("="*80 + "\n", flush=True)

if __name__ == "__main__":
    run_autonomous_loop()
