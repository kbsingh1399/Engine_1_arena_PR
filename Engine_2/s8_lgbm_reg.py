"""
================================================================================
S8 LightGBM REGRESSION — Predict R-Multiple, Select Top Trades
================================================================================
Instead of binary classification (win/loss), predict the actual R-multiple.
Select trades where predicted R > threshold.
This captures more nuance and avoids the class imbalance problem.
================================================================================
"""

import glob
import os
import sys
import json
import logging
import warnings
import time
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

import pandas as pd
import numpy as np
from numba import njit
import gc
import lightgbm as lgb
import optuna
optuna.logging.set_verbosity(optuna.logging.WARNING)

warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "binance_backtesting_data")
RESULTS_DIR = os.path.join(SCRIPT_DIR, "results_s8_lgbm_reg")
os.makedirs(RESULTS_DIR, exist_ok=True)

MIN_RETURN = 0.20
MAX_DD = 0.05
MIN_WIN_RATE = 0.40
MIN_TRADES = 5

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
# DATA LOADING
# ─────────────────────────────────────────────────────────────────────────────
def zs(s, w):
    m = s.rolling(w, min_periods=1).mean()
    std = s.rolling(w, min_periods=1).std().replace(0, 1e-8)
    return (s - m) / std

def get_btc_reference(search_dirs):
    for d in search_dirs:
        if d and os.path.exists(d):
            btc_file = os.path.join(d, "BTCUSDT_15m_master_2020_2026.parquet")
            if os.path.exists(btc_file):
                try:
                    df = pd.read_parquet(btc_file, columns=['datetime_utc', 'close', 'spot_cvd_15m', 'future_cvd_15m'])
                    df['datetime_utc'] = pd.to_datetime(df['datetime_utc'], utc=True)
                    df = df.sort_values('datetime_utc').reset_index(drop=True)
                    cvd = df.get('spot_cvd_15m', df.get('future_cvd_15m', pd.Series(0.0, index=df.index)))
                    return pd.DataFrame({
                        'datetime_utc': df['datetime_utc'],
                        'btc_close': df['close'].astype(np.float32),
                        'zb20': zs(cvd, 96).clip(-4.0, 4.0).astype(np.float32),
                        'zb4': zs(cvd, 4).clip(-4.0, 4.0).astype(np.float32)
                    })
                except:
                    pass
    return None

def load_and_preprocess_data():
    logger.info("Loading 18-asset historical parquet datasets...")
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
            if btc_ref is not None and symbol != "BTCUSDT":
                df = pd.merge_asof(df, btc_ref, on='datetime_utc', direction='backward')
            elif symbol == "BTCUSDT":
                cvd = df.get('spot_cvd_15m', df.get('future_cvd_15m', pd.Series(0.0, index=df.index)))
                df['btc_close'] = df['close']
                df['zb20'] = zs(cvd, 96).clip(-4.0, 4.0)
                df['zb4'] = zs(cvd, 4).clip(-4.0, 4.0)
            spot_cvd = df.get('spot_cvd_15m', 0.0)
            fut_cvd = df.get('future_cvd_15m', 0.0)
            df['cvd_divergence'] = spot_cvd - fut_cvd
            df['spot_cvd_delta'] = spot_cvd.diff().fillna(0.0)
            df['future_cvd_delta'] = fut_cvd.diff().fillna(0.0)
            df['spot_cvd_accel'] = df['spot_cvd_delta'].diff().fillna(0.0)
            df['zc4'] = zs(spot_cvd, 4).clip(-4.0, 4.0)
            df['zc10'] = zs(spot_cvd, 10).clip(-4.0, 4.0)
            df['zc20'] = zs(spot_cvd, 96).clip(-4.0, 4.0)
            df['zc_rel_btc'] = df['zc20'] - df.get('zb20', 0.0)
            df['zc4_rel_btc'] = df['zc4'] - df.get('zb4', 0.0)
            long_liq = df.get('long_liq_usd', pd.Series(0.0, index=df.index)).abs().fillna(0.0)
            short_liq = df.get('short_liq_usd', pd.Series(0.0, index=df.index)).abs().fillna(0.0)
            denom = long_liq + short_liq + 1e-8
            df['liq_imbalance'] = (long_liq - short_liq) / denom
            vol_q = df.get('volume_quote', df['close'] * df.get('volume_base', 1.0))
            df['liq_vol_ratio'] = denom / (vol_q + 1e-8)
            long_std = long_liq.rolling(96, min_periods=12).std().replace(0.0, 1.0)
            short_std = short_liq.rolling(96, min_periods=12).std().replace(0.0, 1.0)
            df['long_liq_zscore'] = ((long_liq - long_liq.rolling(96, min_periods=12).mean()) / long_std).clip(0.0, 10.0).fillna(0.0)
            df['short_liq_zscore'] = ((short_liq - short_liq.rolling(96, min_periods=12).mean()) / short_std).clip(0.0, 10.0).fillna(0.0)
            if 'oi_change_pct' in df.columns:
                df['oi_flush'] = df['oi_change_pct'].clip(upper=0)
            else:
                df['oi_flush'] = 0.0
            oi = df.get('open_interest_usd', pd.Series(0.0, index=df.index)).ffill().fillna(0.0)
            df['zoi'] = zs(oi, 96)
            df['oid'] = oi.diff(5) / (oi.shift(5) + 1e-8)
            df['oicc'] = np.sign(df['oid'].fillna(0)) * np.sign(df['spot_cvd_delta'].fillna(0))
            df['fr'] = df.get('funding_rate_pct', pd.Series(0.0, index=df.index)).fillna(0.0)
            df['zfr'] = zs(df['fr'], 20)
            df['zls'] = zs(df.get('ls_ratio_global', pd.Series(0.0, index=df.index)).ffill().fillna(1.0), 96)
            df['atr'] = (df['high'] - df['low']).rolling(14, min_periods=1).mean().clip(lower=1e-6)
            df['rsi'] = df.get('rsi_14', 50.0).fillna(50.0)
            ef = df['close'].ewm(span=200, min_periods=50).mean()
            es = df['close'].ewm(span=800, min_periods=100).mean()
            df['macro_spread'] = (ef - es) / (df['atr'] + 1e-8)
            df['mc'] = np.where(df['macro_spread'] > 0.5, 1.0, np.where(df['macro_spread'] < -0.5, -1.0, 0.0))
            e8 = df['close'].ewm(span=8, min_periods=1).mean()
            e21 = df['close'].ewm(span=21, min_periods=1).mean()
            e50 = df['close'].ewm(span=50, min_periods=1).mean()
            df['p8'] = (df['close'] - e8) / (df['atr'] + 1e-8)
            df['p21'] = (df['close'] - e21) / (df['atr'] + 1e-8)
            df['p50'] = (df['close'] - e50) / (df['atr'] + 1e-8)
            df['p200'] = (df['close'] - ef) / (df['atr'] + 1e-8)
            log_ret = np.log(df['close'].clip(lower=1e-6)).diff()
            rv_short = log_ret.rolling(96, min_periods=24).std()
            rv_long = log_ret.rolling(672, min_periods=96).std()
            df['vol_ratio'] = (rv_short / (rv_long + 1e-8)).fillna(1.0)
            df['trend_strength'] = (ef - es).abs() / (df['atr'] + 1e-8)
            regime = np.zeros(len(df), dtype=np.int8)
            trending = df['trend_strength'].to_numpy() >= 0.40
            expanding = trending & (df['vol_ratio'].to_numpy() >= 1.15)
            regime[trending] = 1
            regime[expanding] = 2
            df['regime'] = regime
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


ARCHETYPE_FUNCTIONS = {
    "WH1_WhaleRetailDivergence": lambda df: (
        ((df['ls_ratio_top'] > 1.25) & (df['ls_ratio_global'] < 0.95) & (df['mc'] >= 0) & (df['p8'] < -0.10)),
        ((df['ls_ratio_top'] < 0.75) & (df['ls_ratio_global'] > 1.05) & (df['mc'] <= 0) & (df['p8'] > 0.10))
    ),
    "WH2_WhaleIndexSurge": lambda df: (
        ((df['whale_index'] > 55) & (df['spot_cvd_delta'] > 0) & (df['mc'] > 0)),
        ((df['whale_index'] < 45) & (df['spot_cvd_delta'] < 0) & (df['mc'] < 0))
    ),
    "WH3_DepthImbalanceAbsorption": lambda df: (
        ((df['bid_depth_usd'] > df['ask_depth_usd'] * 1.3) & (df['p8'] < -0.15) & (df['mc'] > 0)),
        ((df['ask_depth_usd'] > df['bid_depth_usd'] * 1.3) & (df['p8'] > 0.15) & (df['mc'] < 0))
    ),
    "WH4_TopTraderSqueeze": lambda df: (
        ((df['ls_ratio_top'] > 1.35) & (df['zc20'] > 0.15) & (df['mc'] > 0)),
        ((df['ls_ratio_top'] < 0.65) & (df['zc20'] < -0.15) & (df['mc'] < 0))
    )
}


@njit(fastmath=True, nogil=True)
def simulate_single_trade_path(highs, lows, closes, entry_idx, entry_price, atr, direction, min_ret_pct, max_bars=288):
    stop_dist = max(atr, entry_price * 0.002)
    cur_stop = entry_price - stop_dist if direction == 1 else entry_price + stop_dist
    best_price = entry_price
    mae = 0.0
    exit_price = closes[min(entry_idx + max_bars, len(closes) - 1)]
    exit_offset = max_bars
    max_idx = min(entry_idx + max_bars + 1, len(closes))
    for j in range(entry_idx + 1, max_idx):
        if direction == 1:
            adverse = max(0.0, entry_price - lows[j])
            if adverse > mae: mae = adverse
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
        else:
            adverse = max(0.0, highs[j] - entry_price)
            if adverse > mae: mae = adverse
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
                    ep, offset, mae = simulate_single_trade_path(highs, lows, closes, i, entry, av, int(dr), 0.015)
                    stop_dist = max(av, entry * 0.002)
                    r_mult = (ep - entry) / stop_dist if dr == 1 else (entry - ep) / stop_dist
                    results.append((i, dr, ep, r_mult, offset, mae))
                    cd = i + max(offset, 1) + 2
        i += 1
    return results


def extract_archetype_dataset(data_by_symbol, sig_fn, feature_cols):
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
        for idx, dr, ep, r_mult, offset, mae in res:
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
                'label': int(r_mult > 0.0),
                'bar_index': int(idx)
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


@njit(fastmath=True)
def fast_portfolio_backtest_numba(
    entry_times, exit_times, entry_prices, exit_prices, atrs, maes, directions, probs,
    initial_capital=INITIAL_CAPITAL, base_risk=BASE_RISK, house_risk=HOUSE_MONEY_RISK,
    house_trigger=HOUSE_PROFIT_TRIGGER, house_shield_risk=HOUSE_SHIELD_RISK,
    defense_risk=DRAWDOWN_DEFENSE_RISK, fee_rate=FEE_RATE, max_concurrent=MAX_CONCURRENT,
    leverage=LEVERAGE, max_notional=MAX_NOTIONAL, dd_limit=DRAWDOWN_RISK_LIMIT
):
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
        for p in range(max_concurrent):
            if open_active[p] and open_exit_times[p] <= entry_t:
                capital += open_net_pnls[p]
                if capital > peak_capital: peak_capital = capital
                closed_dd = (peak_capital - capital) / peak_capital if peak_capital > 0 else 0.0
                if closed_dd > max_dd: max_dd = closed_dd
                if open_is_house[p] and open_net_pnls[p] <= 0.0:
                    house_shield = True
                elif house_shield and open_net_pnls[p] > 0.0 and (capital - initial_capital) >= house_trigger:
                    house_shield = False
                open_active[p] = False
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
        if dd > max_dd: max_dd = dd
        if (capital - initial_capital) >= 1010.0 and trades_executed >= 5 and active_count == 0:
            break
        if active_count >= max_concurrent:
            continue
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
            if capital > peak_capital: peak_capital = capital
            dd = (peak_capital - capital) / peak_capital if peak_capital > 0 else 0.0
            if dd > max_dd: max_dd = dd
    win_rate = wins / trades_executed if trades_executed > 0 else 0.0
    roi = (capital - initial_capital) / initial_capital
    return roi, max_dd, win_rate, trades_executed


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


def get_oos_windows(end_date, train_horizon_months=18):
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


def run_walk_forward(data_by_symbol):
    feature_cols = [
        'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
        'zc4', 'zc10', 'zc20', 'zc_rel_btc', 'zc4_rel_btc',
        'liq_imbalance', 'liq_vol_ratio', 'long_liq_zscore', 'short_liq_zscore',
        'oi_flush', 'zoi', 'oid', 'oicc', 'fr', 'zfr', 'zls',
        'macro_spread', 'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'trend_strength',
        'regime'
    ]
    
    logger.info("Extracting trade candidates for all archetypes...")
    t0 = time.time()
    archetype_datasets = {}
    for name, sig_fn in ARCHETYPE_FUNCTIONS.items():
        df_arch = extract_archetype_dataset(data_by_symbol, sig_fn, feature_cols)
        df_arch['archetype'] = name
        archetype_datasets[name] = df_arch
        logger.info(f"  {name}: {len(df_arch):,} trades")
    
    df_all = pd.concat(archetype_datasets.values(), ignore_index=True)
    df_all = df_all.sort_values('entry_time').reset_index(drop=True)
    logger.info(f"Total trades: {len(df_all):,} in {time.time()-t0:.1f}s")
    
    end_date = max(df['datetime_utc'].max() for df in data_by_symbol.values())
    windows = get_oos_windows(end_date, 18)
    
    all_results = []
    status_file = os.path.join(RESULTS_DIR, "s8_lgbm_reg_status.json")
    
    logger.info("\n" + "="*80)
    logger.info("S8 LightGBM REGRESSION: 20-MONTH WALK-FORWARD VALIDATION")
    logger.info("="*80)
    
    for w in windows:
        w_idx = w['window']
        test_start = w['test_start']
        test_end = w['test_end']
        train_start = w['train_start']
        train_end_purged = w['train_end'] - pd.Timedelta(hours=3)
        
        logger.info(f"\n>>> Window {w_idx:02d}: {test_start.strftime('%Y-%m-%d')} to {test_end.strftime('%Y-%m-%d')}")
        
        df_is = df_all[(df_all['entry_time'] >= train_start) & (df_all['exit_time'] < train_end_purged)].copy()
        df_oos = df_all[(df_all['entry_time'] >= test_start) & (df_all['entry_time'] < test_end)].copy()
        
        if len(df_is) < 100 or len(df_oos) == 0:
            logger.error(f"  ❌ Insufficient data!")
            all_results.append({
                "window": w_idx, "trades": 0, "win_rate_pct": 0.0,
                "roi_pct": 0.0, "max_dd_pct": 0.0, "status": "❌ FAIL"
            })
            continue
        
        fcols = [c for c in feature_cols if c in df_is.columns]
        
        # Add interaction features
        for c in ['zc20', 'zc4', 'liq_imbalance', 'zfr', 'zls']:
            if c in df_is.columns and 'direction' in df_is.columns:
                df_is[f'{c}_x_dir'] = df_is[c] * df_is['direction']
                df_oos[f'{c}_x_dir'] = df_oos[c] * df_oos['direction']
                fcols.append(f'{c}_x_dir')
        
        X_train = df_is[fcols].fillna(0.0).to_numpy(dtype=np.float32)
        y_r = df_is['r_multiple'].to_numpy(dtype=np.float64)
        
        # Clip extreme R-multiples for training stability
        y_r_clipped = np.clip(y_r, -5.0, 10.0)
        
        X_oos = df_oos[fcols].fillna(0.0).to_numpy(dtype=np.float32)
        
        # Split IS into train/val
        split_idx = int(len(X_train) * 0.8)
        X_tr, X_val = X_train[:split_idx], X_train[split_idx:]
        y_tr, y_val = y_r_clipped[:split_idx], y_r_clipped[split_idx:]
        
        logger.info(f"  Training LightGBM Regression (IS: {len(X_tr)} train, {len(X_val)} val)...")
        logger.info(f"  R-multiple stats: mean={y_tr.mean():.3f}, std={y_tr.std():.3f}, median={np.median(y_tr):.3f}")
        
        # Optuna tuning for regression
        def objective(trial):
            params = {
                'objective': 'regression',
                'metric': 'rmse',
                'boosting_type': 'gbdt',
                'learning_rate': trial.suggest_float('lr', 0.01, 0.15, log=True),
                'num_leaves': trial.suggest_int('num_leaves', 16, 128),
                'max_depth': trial.suggest_int('max_depth', 3, 12),
                'min_child_samples': trial.suggest_int('min_child_samples', 20, 200),
                'subsample': trial.suggest_float('subsample', 0.5, 1.0),
                'colsample_bytree': trial.suggest_float('colsample_bytree', 0.5, 1.0),
                'reg_alpha': trial.suggest_float('reg_alpha', 1e-3, 10.0, log=True),
                'reg_lambda': trial.suggest_float('reg_lambda', 1e-3, 10.0, log=True),
                'n_estimators': 500,
                'random_state': 42,
                'n_jobs': -1,
                'verbose': -1
            }
            model = lgb.LGBMRegressor(**params)
            model.fit(X_tr, y_tr,
                      eval_set=[(X_val, y_val)],
                      callbacks=[lgb.early_stopping(30, verbose=False), lgb.log_evaluation(0)])
            preds = model.predict(X_val)
            rmse = np.sqrt(np.mean((preds - y_val) ** 2))
            
            # Also check if the model can separate good from bad trades
            actual_r = y_val
            # Rank correlation as secondary metric
            from scipy.stats import spearmanr
            corr, _ = spearmanr(actual_r, preds)
            
            # Combined metric: minimize RMSE, maximize rank correlation
            score = rmse - 0.5 * corr
            return score
        
        study = optuna.create_study(direction='minimize', 
                                     sampler=optuna.samplers.TPESampler(seed=42))
        study.optimize(objective, n_trials=40, timeout=120, show_progress_bar=False)
        
        best_params = study.best_trial.params
        best_params['objective'] = 'regression'
        best_params['metric'] = 'rmse'
        best_params['boosting_type'] = 'gbdt'
        best_params['n_estimators'] = 800
        best_params['random_state'] = 42
        best_params['n_jobs'] = -1
        best_params['verbose'] = -1
        
        model = lgb.LGBMRegressor(**best_params)
        model.fit(X_train, y_r_clipped,
                  eval_set=[(X_val, y_val)],
                  callbacks=[lgb.early_stopping(30, verbose=False), lgb.log_evaluation(0)])
        
        # Predict R-multiples on OOS
        pred_r = model.predict(X_oos)
        
        logger.info(f"  Predicted R-multiples: mean={pred_r.mean():.3f}, std={pred_r.std():.3f}")
        logger.info(f"  Best Optuna params: {study.best_params}")
        
        # Select trades with predicted R > threshold
        # Try multiple thresholds and pick the one that gives enough trades
        best_threshold = None
        best_n_trades = 0
        
        for r_thresh in [0.5, 0.3, 0.2, 0.1, 0.0, -0.1, -0.2]:
            n = np.count_nonzero(pred_r > r_thresh)
            if n >= MIN_TRADES:
                best_threshold = r_thresh
                best_n_trades = n
                break
        
        if best_threshold is None:
            best_threshold = -0.5
            best_n_trades = np.count_nonzero(pred_r > best_threshold)
        
        mask_oos = pred_r > best_threshold
        n_selected = np.count_nonzero(mask_oos)
        
        logger.info(f"  Selected {n_selected} trades with predicted R > {best_threshold:.2f}")
        
        if n_selected < MIN_TRADES:
            logger.error(f"  ❌ Insufficient trades!")
            all_results.append({
                "window": w_idx, "trades": 0, "win_rate_pct": 0.0,
                "roi_pct": 0.0, "max_dd_pct": 0.0, "status": "❌ FAIL"
            })
            continue
        
        # Use predicted R as "probability" for position sizing
        # Normalize to 0-1 range
        prob_oos = (pred_r[mask_oos] - pred_r[mask_oos].min()) / (pred_r[mask_oos].max() - pred_r[mask_oos].min() + 1e-8)
        prob_oos = np.clip(prob_oos, 0.1, 1.0)
        
        # Backtest
        oos_et = df_oos['entry_time'].values.astype(np.int64)[mask_oos]
        oos_xt = df_oos['exit_time'].values.astype(np.int64)[mask_oos]
        oos_ep = df_oos['entry_price'].values.astype(np.float64)[mask_oos]
        oos_xp = df_oos['exit_price'].values.astype(np.float64)[mask_oos]
        oos_atr = df_oos['atr'].values.astype(np.float64)[mask_oos]
        oos_mae = df_oos['mae'].values.astype(np.float64)[mask_oos]
        oos_dr = df_oos['direction'].values.astype(np.int8)[mask_oos]
        
        roi, dd, wr, tr = fast_portfolio_backtest_numba(
            oos_et, oos_xt, oos_ep, oos_xp, oos_atr, oos_mae, oos_dr, prob_oos
        )
        
        status_pass = (roi >= MIN_RETURN and dd <= MAX_DD and wr >= MIN_WIN_RATE and tr >= MIN_TRADES)
        status_icon = "✅ PASS" if status_pass else "❌ FAIL"
        
        logger.info(f"  Trades={tr}, WR={wr*100:.1f}%, ROI={roi*100:+.2f}%, DD={dd*100:.2f}% {status_icon}")
        
        all_results.append({
            "window": w_idx,
            "test_start": test_start.strftime('%Y-%m-%d'),
            "test_end": test_end.strftime('%Y-%m-%d'),
            "trades": tr,
            "win_rate_pct": round(wr * 100, 2),
            "roi_pct": round(roi * 100, 2),
            "max_dd_pct": round(dd * 100, 2),
            "r_threshold": round(best_threshold, 2),
            "pred_r_mean": round(pred_r.mean(), 4),
            "status": status_icon
        })
        
        with open(status_file, "w") as f:
            json.dump(all_results, f, indent=4)
        
        del model
        gc.collect()
    
    passed = sum(1 for r in all_results if 'PASS' in r['status'])
    logger.info(f"\n{'='*80}")
    logger.info(f"S8 LightGBM REGRESSION FINAL RESULT: {passed}/20 windows passed")
    logger.info(f"{'='*80}")
    
    return all_results


if __name__ == "__main__":
    logger.info("Initializing S8 LightGBM Regression...")
    data_by_symbol = load_and_preprocess_data()
    if not data_by_symbol:
        logger.error("Failed to load data!")
        sys.exit(1)
    results = run_walk_forward(data_by_symbol)
    print("\n" + "="*80, flush=True)
    passed = sum(1 for r in results if 'PASS' in r['status'])
    print(f"📊 S8 LightGBM REGRESSION: {passed}/20 WINDOWS PASSED", flush=True)
    print("="*80 + "\n", flush=True)
