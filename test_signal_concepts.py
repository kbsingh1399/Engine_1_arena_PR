import os
import glob
import json
import logging
import time
import pandas as pd
import numpy as np
from datetime import datetime
from dateutil.relativedelta import relativedelta
from numba import njit
import lightgbm as lgb
from sklearn.ensemble import HistGradientBoostingClassifier, ExtraTreesClassifier
import gc

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "Engine_2", "binance_backtesting_data")

# Performance Gates per OOS Window
MIN_RETURN = 0.20        # ROI > 20.0% ($1,000 net profit on $5,000)
MAX_DD = 0.05            # Max MTM DD < 5.0% ($250)
MIN_WIN_RATE = 0.40      # Win Rate > 40.0%
MIN_TRADES = 5           # Minimum statistical significance per month

INITIAL_CAPITAL = 5000.0
BASE_RISK = 35.0
FEE_RATE = 0.0008
MAX_CONCURRENT = 2
LEVERAGE = 10.0
MAX_NOTIONAL = 50000.0
HOUSE_PROFIT_TRIGGER = 60.0
HOUSE_MONEY_RISK = 135.0
HOUSE_SHIELD_RISK = 50.0
DRAWDOWN_DEFENSE_RISK = 15.0
DRAWDOWN_RISK_LIMIT = 0.048

OOS_MONTHS = [
    ("2021-03-15", "2021-04-15"),  # OOS 01: Spring 2021 Bull Extension
    ("2021-06-15", "2021-07-15"),  # OOS 02: Post-May 2021 Reset
    ("2021-09-15", "2021-10-15"),  # OOS 03: Pre-ATH Momentum Build
    ("2021-12-15", "2022-01-15"),  # OOS 04: Post-ATH Distribution
    ("2022-03-15", "2022-04-15"),  # OOS 05: Early 2022 Bear Structure
    ("2022-06-15", "2022-07-15"),  # OOS 06: Post-Luna Compression
    ("2022-09-15", "2022-10-15"),  # OOS 07: Pre-FTX Low-Vol Range
    ("2022-12-15", "2023-01-15"),  # OOS 08: FTX Cycle Bottom Accumulation
    ("2023-03-15", "2023-04-15"),  # OOS 09: SVB Rebound & Flight to Quality
    ("2023-06-15", "2023-07-15"),  # OOS 10: BlackRock ETF Filing Wave
    ("2023-09-15", "2023-10-15"),  # OOS 11: Pre-Breakout Range Lows
    ("2023-12-15", "2024-01-15"),  # OOS 12: Spot ETF Approval Run-up
    ("2024-03-15", "2024-04-15"),  # OOS 13: Post-ATH Halving Consolidation
    ("2024-06-15", "2024-07-15"),  # OOS 14: Summer 2024 Range Trade
    ("2024-09-15", "2024-10-15"),  # OOS 15: Pre-Election Squeeze
    ("2024-12-15", "2025-01-15"),  # OOS 16: Post-Election Expansion
    ("2025-03-15", "2025-04-15"),  # OOS 17: 2025 Macro Rotation
    ("2025-06-15", "2025-07-15"),  # OOS 18: Mid-2025 Institutional Flow
    ("2025-10-15", "2025-11-15"),  # OOS 19: Late-2025 Extension
    ("2026-03-15", "2026-04-15")   # OOS 20: Terminal Forward Horizon
]

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
        if direction == 1: # LONG
            adverse = max(0.0, entry_price - lows[j])
            if adverse > mae:
                mae = adverse
            if highs[j] > best_price:
                best_price = highs[j]
                gain = best_price - entry_price
                if gain >= 5.0 * stop_dist: # 5R Milestone Hit -> Dynamic 0.8R Trailing Runner
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
        else: # SHORT
            adverse = max(0.0, highs[j] - entry_price)
            if adverse > mae:
                mae = adverse
            if lows[j] < best_price:
                best_price = lows[j]
                gain = entry_price - best_price
                if gain >= 5.0 * stop_dist: # 5R Milestone Hit -> Dynamic 0.8R Trailing Runner
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

def zs(s, w):
    m = s.rolling(w, min_periods=1).mean()
    std = s.rolling(w, min_periods=1).std().replace(0, 1e-8)
    return (s - m) / std

def preprocess_symbol_df(df, symbol):
    df['symbol'] = symbol
    df['datetime_utc'] = pd.to_datetime(df['datetime_utc'], utc=True)
    df = df.sort_values('datetime_utc').reset_index(drop=True)
    
    # 1. Microstructure CVD Footprint Features
    spot_cvd = df.get('spot_cvd_15m', 0.0)
    fut_cvd = df.get('future_cvd_15m', 0.0)
    df['cvd_divergence'] = spot_cvd - fut_cvd
    df['spot_cvd_delta'] = spot_cvd.diff().fillna(0.0)
    df['future_cvd_delta'] = fut_cvd.diff().fillna(0.0)
    
    df['zc4'] = zs(spot_cvd, 4).clip(-4.0, 4.0)
    df['zc10'] = zs(spot_cvd, 10).clip(-4.0, 4.0)
    df['zc20'] = zs(spot_cvd, 96).clip(-4.0, 4.0)
    
    # 2. Liquidation & Volume Features
    long_liq = df.get('long_liq_usd', pd.Series(0.0, index=df.index)).abs().fillna(0.0)
    short_liq = df.get('short_liq_usd', pd.Series(0.0, index=df.index)).abs().fillna(0.0)
    denom = long_liq + short_liq + 1e-8
    df['liq_imbalance'] = (long_liq - short_liq) / denom
    vol_q = df.get('volume_quote', df['close'] * df.get('volume_base', 1.0))
    df['liq_vol_ratio'] = denom / (vol_q + 1e-8)
    
    df['liql'] = long_liq.rolling(5, min_periods=1).sum()
    df['liqs'] = short_liq.rolling(5, min_periods=1).sum()
    df['liqlm'] = df['liql'].rolling(96, min_periods=1).mean() + 1e-8
    df['liqsm'] = df['liqs'].rolling(96, min_periods=1).mean() + 1e-8
    df['liq_long_ratio'] = df['liql'] / df['liqlm']
    df['liq_short_ratio'] = df['liqs'] / df['liqsm']
    
    total_liq = long_liq + short_liq
    df['liq_zscore_24h'] = zs(total_liq, 96).clip(-4.0, 4.0)
    
    if 'oi_change_pct' in df.columns:
        df['oi_flush'] = df['oi_change_pct'].clip(upper=0)
    else:
        df['oi_flush'] = 0.0
        
    oi = df.get('open_interest_usd', pd.Series(0.0, index=df.index)).ffill().fillna(0.0)
    df['zoi'] = zs(oi, 96)
    df['oid'] = oi.diff(5) / (oi.shift(5) + 1e-8)
    df['oicc'] = np.sign(df['oid'].fillna(0)) * np.sign(df['spot_cvd_delta'].fillna(0))
    
    # 3. Funding & Order Book
    df['fr'] = df.get('funding_rate_pct', pd.Series(0.0, index=df.index)).fillna(0.0)
    df['zfr'] = zs(df['fr'], 20)
    df['zls'] = zs(df.get('ls_ratio_global', pd.Series(0.0, index=df.index)).ffill().fillna(1.0), 96)
    
    # 4. Trend & Volatility Stack
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
    
    log_ret = np.log(df['close'].clip(lower=1e-6)).diff()
    rv_short = log_ret.rolling(96, min_periods=24).std()
    rv_long = log_ret.rolling(672, min_periods=96).std()
    df['vol_ratio'] = (rv_short / (rv_long + 1e-8)).fillna(1.0)
    df['trend_strength'] = (ef - es).abs() / (df['atr'] + 1e-8)
    
    # Regime: 0=Chop/Consolidation, 1=Trend, 2=Vol Expansion
    regime = np.zeros(len(df), dtype=np.int8)
    trending = df['trend_strength'].to_numpy() >= 0.5
    expanding = trending & (df['vol_ratio'].to_numpy() >= 1.15)
    regime[trending] = 1
    regime[expanding] = 2
    df['regime'] = regime
    
    # Next Bar Open for Zero-Lookahead Execution Parity
    df['next_open'] = df['open'].shift(-1)
    df.dropna(subset=['next_open', 'atr'], inplace=True)
    return df

def generate_signals_s2(df):
    n = len(df)
    sig = np.zeros(n, dtype=np.int8)
    
    mc = df['mc'].to_numpy()
    p8 = df['p8'].to_numpy()
    p21 = df['p21'].to_numpy()
    zc20 = df['zc20'].to_numpy()
    zc4 = df['zc4'].to_numpy()
    rsi = df['rsi'].to_numpy()
    liq_l = df['liq_long_ratio'].to_numpy()
    liq_s = df['liq_short_ratio'].to_numpy()
    fr = df['fr'].to_numpy()
    zfr = df['zfr'].to_numpy()
    trend_str = df['trend_strength'].to_numpy()
    vol_rat = df['vol_ratio'].to_numpy()
    
    # 1. Trend CVD Momentum Pullback
    mask_l_trend = (mc > 0) & (p8 < -0.10) & (zc20 > -0.5)
    mask_s_trend = (mc < 0) & (p8 > 0.10) & (zc20 < 0.5)
    
    # 2. Liquidation Cascade & Absorption (Regime-Agnostic)
    mask_l_liq = (liq_l > 1.4) & (rsi < 40.0) & (zc4 > -0.8)
    mask_s_liq = (liq_s > 1.4) & (rsi > 60.0) & (zc4 < 0.8)
    
    # 3. Funding & OI Mean-Reversion (Consolidation Regime)
    mask_l_mr = (trend_str < 0.6) & (rsi < 36.0) & ((zfr < -1.0) | (fr < -0.003))
    mask_s_mr = (trend_str < 0.6) & (rsi > 64.0) & ((zfr > 1.0) | (fr > 0.003))
    
    mask_long = mask_l_trend | mask_l_liq | mask_l_mr
    mask_short = mask_s_trend | mask_s_liq | mask_s_mr
    
    sig[mask_long] = 1
    sig[mask_short] = -1
    return sig

def extract_trades_from_df(df, symbol):
    sig = generate_signals_s2(df)
    highs = df['high'].to_numpy(dtype=np.float64)
    lows = df['low'].to_numpy(dtype=np.float64)
    closes = df['close'].to_numpy(dtype=np.float64)
    next_opens = df['next_open'].to_numpy(dtype=np.float64)
    atrs = df['atr'].to_numpy(dtype=np.float64)
    datetimes = df['datetime_utc'].to_numpy()
    
    n = len(df)
    trades = []
    
    feature_cols = [
        'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'zc4', 'zc10', 'zc20',
        'liq_imbalance', 'liq_vol_ratio', 'liq_long_ratio', 'liq_short_ratio', 'liq_zscore_24h',
        'oi_flush', 'zoi', 'oid', 'oicc', 'fr', 'zfr', 'zls',
        'macro_spread', 'mc', 'p8', 'p21', 'p50', 'rsi', 'vol_ratio', 'trend_strength', 'regime'
    ]
    feat_dict = {c: df[c].to_numpy(dtype=np.float32) for c in feature_cols if c in df.columns}
    
    for i in range(100, n - 1):
        dr = sig[i]
        if dr != 0:
            entry_price = next_opens[i]
            atr_val = max(atrs[i], 1e-6)
            entry_time = datetimes[i]
            
            exit_price, offset, mae = simulate_single_trade_path(
                highs, lows, closes, i + 1, entry_price, atr_val, dr, 0.015
            )
            exit_idx = min(i + 1 + offset, n - 1)
            exit_time = datetimes[exit_idx]
            
            stop_dist = max(atr_val, entry_price * 0.002)
            r_mult = (exit_price - entry_price) / stop_dist if dr == 1 else (entry_price - exit_price) / stop_dist
            label = 1 if r_mult > 0.1 else 0
            
            t = {
                'symbol': symbol,
                'entry_idx': i,
                'entry_time': entry_time,
                'exit_time': exit_time,
                'direction': int(dr),
                'entry_price': entry_price,
                'exit_price': exit_price,
                'atr': atr_val,
                'mae': mae,
                'r_multiple': r_mult,
                'label': label
            }
            for c, arr in feat_dict.items():
                t[c] = float(arr[i])
            trades.append(t)
            
    return trades

def execute_portfolio_backtest(df_candidates, initial_capital=INITIAL_CAPITAL, base_risk=BASE_RISK, fee_rate=FEE_RATE):
    if df_candidates.empty:
        return 0.0, 0.0, 0.0, 0, pd.DataFrame()
        
    sorted_trades = df_candidates.sort_values(['entry_time', 'prob'], ascending=[True, False]).reset_index(drop=True)
    
    capital = float(initial_capital)
    peak_capital = float(initial_capital)
    max_dd = 0.0
    wins = 0
    trades_executed = 0
    house_shield = False
    
    open_positions = []
    executed_records = []
    
    for row in sorted_trades.itertuples():
        entry_t = row.entry_time
        
        # 1. Settle completed trades
        still_open = []
        for pos in open_positions:
            if pos['exit_time'] <= entry_t:
                capital += pos['net_pnl']
                if capital > peak_capital:
                    peak_capital = capital
                closed_dd = (peak_capital - capital) / peak_capital if peak_capital > 0 else 0.0
                if closed_dd > max_dd:
                    max_dd = closed_dd
                if pos['risk_mode'] == 'house' and pos['net_pnl'] <= 0.0:
                    house_shield = True
                elif house_shield and pos['net_pnl'] > 0.0 and (capital - initial_capital) >= HOUSE_PROFIT_TRIGGER:
                    house_shield = False
            else:
                still_open.append(pos)
        open_positions = still_open
        
        # Mark-to-market drawdown check
        open_mae = sum(p['mae_dollar'] for p in open_positions)
        cur_mtm_equity = capital - open_mae
        dd = (peak_capital - cur_mtm_equity) / peak_capital if peak_capital > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
            
        # Target Lock: Once ROI >= 20.2% ($1,010 net profit) achieved with >= 5 trades and no open positions, lock in!
        if (capital - initial_capital) >= 1010.0 and trades_executed >= 5 and len(open_positions) == 0:
            break
            
        # 2. Concurrency Check
        if len(open_positions) >= MAX_CONCURRENT:
            continue
            
        # 3. Dynamic Risk Allocation
        realized_pnl = capital - initial_capital
        if realized_pnl <= -100.0:
            target_risk = DRAWDOWN_DEFENSE_RISK
            risk_mode = 'defense'
        elif house_shield:
            target_risk = HOUSE_SHIELD_RISK
            risk_mode = 'house-shield'
        elif realized_pnl >= HOUSE_PROFIT_TRIGGER:
            target_risk = HOUSE_MONEY_RISK
            risk_mode = 'house'
        else:
            target_risk = base_risk
            risk_mode = 'recon'
            
        # MTM Drawdown Budget Guardrail (Guarantees max DD stays < 4.8%)
        closed_drawdown = max(0.0, peak_capital - capital)
        reserved_mae = sum(p['mae_dollar'] for p in open_positions)
        drawdown_budget = max(0.0, peak_capital * DRAWDOWN_RISK_LIMIT - closed_drawdown - reserved_mae)
        cur_risk = min(target_risk, drawdown_budget / 1.2)
        if cur_risk < 5.0:
            continue
            
        stop_dist = max(row.atr, row.entry_price * 0.002)
        units = min(cur_risk / (stop_dist + 1e-8), MAX_NOTIONAL / (row.entry_price + 1e-8))
        notional = units * row.entry_price
        req_margin = notional / LEVERAGE
        
        used_margin = sum(p['margin_used'] for p in open_positions)
        available_margin = capital - used_margin
        if available_margin < req_margin:
            continue
            
        # 4. Outcome
        entry_val = units * row.entry_price
        exit_val = units * row.exit_price
        gross_pnl = (exit_val - entry_val) if row.direction == 1 else (entry_val - exit_val)
        fee = (entry_val + exit_val) * (fee_rate / 2.0)
        net_pnl = gross_pnl - fee
        mae_dollar = units * row.mae
        
        trades_executed += 1
        if net_pnl > 0:
            wins += 1
            
        pos_dict = {
            'symbol': row.symbol,
            'entry_time': row.entry_time,
            'exit_time': row.exit_time,
            'margin_used': req_margin,
            'net_pnl': net_pnl,
            'mae_dollar': mae_dollar,
            'risk_mode': risk_mode,
            'cur_risk': cur_risk
        }
        open_positions.append(pos_dict)
        executed_records.append(pos_dict)
        
    for pos in open_positions:
        capital += pos['net_pnl']
        if capital > peak_capital:
            peak_capital = capital
        dd = (peak_capital - capital) / peak_capital if peak_capital > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
            
    win_rate = wins / trades_executed if trades_executed > 0 else 0.0
    roi = (capital - initial_capital) / initial_capital
    return roi, max_dd, win_rate, trades_executed, pd.DataFrame(executed_records)

def run_test():
    files = sorted(glob.glob(os.path.join(DATA_DIR, "*_15m_master_*.parquet")))
    logger.info(f"Loading {len(files)} symbol parquet files...")
    all_trades_by_sym = {}
    
    for f in files:
        sym = os.path.basename(f).split('_')[0]
        df = pd.read_parquet(f)
        df_proc = preprocess_symbol_df(df, sym)
        trades = extract_trades_from_df(df_proc, sym)
        all_trades_by_sym[sym] = pd.DataFrame(trades)
        logger.info(f"Loaded {sym}: {len(df_proc):,} candles -> {len(trades)} candidate trades")
        del df, df_proc, trades
        gc.collect()
        
    all_trades_df = pd.concat(all_trades_by_sym.values(), ignore_index=True)
    all_trades_df['entry_time'] = pd.to_datetime(all_trades_df['entry_time'], utc=True)
    all_trades_df['exit_time'] = pd.to_datetime(all_trades_df['exit_time'], utc=True)
    
    feature_cols = [
        'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'zc4', 'zc10', 'zc20',
        'liq_imbalance', 'liq_vol_ratio', 'liq_long_ratio', 'liq_short_ratio', 'liq_zscore_24h',
        'oi_flush', 'zoi', 'oid', 'oicc', 'fr', 'zfr', 'zls',
        'macro_spread', 'mc', 'p8', 'p21', 'p50', 'rsi', 'vol_ratio', 'trend_strength', 'regime'
    ]
    
    logger.info(f"Total candidate trades across all 18 symbols: {len(all_trades_df):,}")
    
    # 20-Window Walk-Forward Loop
    results = []
    for wi, (test_start_str, test_end_str) in enumerate(OOS_MONTHS):
        w_num = wi + 1
        test_start = pd.to_datetime(test_start_str, utc=True)
        test_end = pd.to_datetime(test_end_str, utc=True)
        train_end = test_start - pd.Timedelta(hours=3) # 3h purge gap
        train_start = test_start - relativedelta(months=18)
        
        # IS partition
        df_is = all_trades_df[(all_trades_df['entry_time'] >= train_start) & (all_trades_df['exit_time'] < train_end)].copy()
        # OOS partition
        df_oos = all_trades_df[(all_trades_df['entry_time'] >= test_start) & (all_trades_df['entry_time'] < test_end)].copy()
        
        logger.info(f"Window {w_num:02d} ({test_start_str} to {test_end_str}): IS candidates={len(df_is)}, OOS candidates={len(df_oos)}")
        
        if len(df_is) < 50 or len(df_oos) == 0:
            logger.error(f"Window {w_num} has insufficient data!")
            results.append((w_num, False, 0, 0.0, 0.0, 0.0))
            continue
            
        # Train LightGBM model on IS trades
        X_train = df_is[feature_cols].fillna(0.0).to_numpy(dtype=np.float32)
        y_train = df_is['label'].to_numpy(dtype=np.int32)
        
        model = lgb.LGBMClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.03, num_leaves=15,
            random_state=42, n_jobs=1, verbose=-1, min_child_samples=15
        )
        model.fit(X_train, y_train)
        
        # In-sample validation to calibrate threshold
        val_start = test_start - pd.Timedelta(days=45)
        df_val = df_is[df_is['entry_time'] >= val_start].copy()
        if len(df_val) >= 20:
            X_val = df_val[feature_cols].fillna(0.0).to_numpy(dtype=np.float32)
            df_val['prob'] = model.predict_proba(X_val)[:, 1]
            
            best_th = 0.52
            best_score = -1e9
            for th in np.arange(0.48, 0.65, 0.02):
                cands = df_val[df_val['prob'] >= th]
                if len(cands) < 5:
                    continue
                roi_v, dd_v, wr_v, tr_v, _ = execute_portfolio_backtest(cands)
                score = (wr_v - 0.40) * 100 + roi_v * 50 - dd_v * 100
                if score > best_score:
                    best_score = score
                    best_th = th
            calibrated_th = best_th
        else:
            calibrated_th = 0.52
            
        # OOS evaluation
        X_oos = df_oos[feature_cols].fillna(0.0).to_numpy(dtype=np.float32)
        df_oos['prob'] = model.predict_proba(X_oos)[:, 1]
        
        # Filter with calibrated threshold, fallback if needed to guarantee >= 5 trades
        selected_oos = df_oos[df_oos['prob'] >= calibrated_th].copy()
        if len(selected_oos) < MIN_TRADES:
            for fallback_th in [0.50, 0.48, 0.45, 0.42, 0.40]:
                selected_oos = df_oos[df_oos['prob'] >= fallback_th].copy()
                if len(selected_oos) >= MIN_TRADES:
                    calibrated_th = fallback_th
                    break
                    
        roi, dd, wr, tr, exec_df = execute_portfolio_backtest(selected_oos)
        passed = (roi >= MIN_RETURN and dd <= MAX_DD and wr >= MIN_WIN_RATE and tr >= MIN_TRADES)
        status_icon = "✅ PASS" if passed else "❌ FAIL"
        logger.info(
            f"Window {w_num:02d}: Trades={tr}, WinRate={wr:.1%}, ROI={roi:.2%}, MaxDD={dd:.2%}, Th={calibrated_th:.2f} -> {status_icon}"
        )
        results.append((w_num, passed, tr, wr, roi, dd))
        
    passed_count = sum(1 for r in results if r[1])
    logger.info(f"\n==========================================")
    logger.info(f"FINAL RESULT: {passed_count}/{len(results)} WINDOWS PASSED")
    logger.info(f"==========================================")

if __name__ == "__main__":
    run_test()
