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
import xgboost as xgb
import gc

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "Engine_2", "binance_backtesting_data")

MIN_RETURN = 0.20
MAX_DD = 0.05
MIN_WIN_RATE = 0.40
MIN_TRADES = 5

INITIAL_CAPITAL = 5000.0
BASE_RISK = 35.0
FEE_RATE = 0.0008
MAX_CONCURRENT = 2
LEVERAGE = 10.0
MAX_NOTIONAL = 50000.0
HOUSE_PROFIT_TRIGGER = 55.0
HOUSE_MONEY_RISK = 140.0
HOUSE_SHIELD_RISK = 55.0
DRAWDOWN_DEFENSE_RISK = 15.0
DRAWDOWN_RISK_LIMIT = 0.048

OOS_MONTHS = [
    ("2021-03-15", "2021-04-15"),  # OOS 01
    ("2021-06-15", "2021-07-15"),  # OOS 02
    ("2021-09-15", "2021-10-15"),  # OOS 03
    ("2021-12-15", "2022-01-15"),  # OOS 04
    ("2022-03-15", "2022-04-15"),  # OOS 05
    ("2022-06-15", "2022-07-15"),  # OOS 06
    ("2022-09-15", "2022-10-15"),  # OOS 07
    ("2022-12-15", "2023-01-15"),  # OOS 08
    ("2023-03-15", "2023-04-15"),  # OOS 09
    ("2023-06-15", "2023-07-15"),  # OOS 10
    ("2023-09-15", "2023-10-15"),  # OOS 11
    ("2023-12-15", "2024-01-15"),  # OOS 12
    ("2024-03-15", "2024-04-15"),  # OOS 13
    ("2024-06-15", "2024-07-15"),  # OOS 14
    ("2024-09-15", "2024-10-15"),  # OOS 15
    ("2024-12-15", "2025-01-15"),  # OOS 16
    ("2025-03-15", "2025-04-15"),  # OOS 17
    ("2025-06-15", "2025-07-15"),  # OOS 18
    ("2025-10-15", "2025-11-15"),  # OOS 19
    ("2026-03-15", "2026-04-15")   # OOS 20
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
        else: # SHORT
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
def build_labels_numba(highs, lows, closes, next_opens, atrs, direction, tp_r, sl_r, max_bars=288):
    n = len(closes)
    labels = np.zeros(n, dtype=np.int8)
    for i in range(n - max_bars - 1):
        atr_val = atrs[i]
        if atr_val <= 0 or np.isnan(atr_val):
            continue
        entry = next_opens[i]
        stop_dist = max(atr_val, entry * 0.002)
        sl = entry - sl_r * stop_dist if direction == 1 else entry + sl_r * stop_dist
        tp = entry + tp_r * stop_dist if direction == 1 else entry - tp_r * stop_dist
        
        limit = min(i + max_bars + 1, n)
        for j in range(i + 1, limit):
            if direction == 1:
                if lows[j] <= sl:
                    labels[i] = 0
                    break
                if highs[j] >= tp:
                    labels[i] = 1
                    break
            else:
                if highs[j] >= sl:
                    labels[i] = 0
                    break
                if lows[j] <= tp:
                    labels[i] = 1
                    break
    return labels

def zs(s, w):
    m = s.rolling(w, min_periods=1).mean()
    std = s.rolling(w, min_periods=1).std().replace(0, 1e-8)
    return (s - m) / std

def get_btc_ref():
    btc_path = os.path.join(DATA_DIR, "BTCUSDT_15m_master_2020_2026.parquet")
    df = pd.read_parquet(btc_path, columns=['datetime_utc', 'close', 'spot_cvd_15m', 'future_cvd_15m'])
    df['datetime_utc'] = pd.to_datetime(df['datetime_utc'], utc=True)
    df = df.sort_values('datetime_utc').reset_index(drop=True)
    cvd = df.get('spot_cvd_15m', df.get('future_cvd_15m', pd.Series(0.0, index=df.index)))
    return pd.DataFrame({
        'datetime_utc': df['datetime_utc'],
        'btc_close': df['close'].astype(np.float32),
        'zb20': zs(cvd, 96).clip(-4.0, 4.0).astype(np.float32),
        'zb4': zs(cvd, 4).clip(-4.0, 4.0).astype(np.float32)
    })

def preprocess_symbol_data(file_path, btc_ref):
    sym = os.path.basename(file_path).split('_')[0]
    df = pd.read_parquet(file_path)
    df['symbol'] = sym
    df['datetime_utc'] = pd.to_datetime(df['datetime_utc'], utc=True)
    df = df.sort_values('datetime_utc').reset_index(drop=True)
    
    if btc_ref is not None and sym != "BTCUSDT":
        df = pd.merge_asof(df, btc_ref, on='datetime_utc', direction='backward')
    elif sym == "BTCUSDT":
        cvd = df.get('spot_cvd_15m', df.get('future_cvd_15m', 0.0))
        df['btc_close'] = df['close']
        df['zb20'] = zs(cvd, 96).clip(-4.0, 4.0)
        df['zb4'] = zs(cvd, 4).clip(-4.0, 4.0)
        
    spot_cvd = df.get('spot_cvd_15m', 0.0)
    fut_cvd = df.get('future_cvd_15m', 0.0)
    df['cvd_divergence'] = spot_cvd - fut_cvd
    df['spot_cvd_delta'] = spot_cvd.diff().fillna(0.0)
    df['future_cvd_delta'] = fut_cvd.diff().fillna(0.0)
    df['zc4'] = zs(spot_cvd, 4).clip(-4.0, 4.0)
    df['zc10'] = zs(spot_cvd, 10).clip(-4.0, 4.0)
    df['zc20'] = zs(spot_cvd, 96).clip(-4.0, 4.0)
    
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
    
    log_ret = np.log(df['close'].clip(lower=1e-6)).diff()
    rv_short = log_ret.rolling(96, min_periods=24).std()
    rv_long = log_ret.rolling(672, min_periods=96).std()
    df['vol_ratio'] = (rv_short / (rv_long + 1e-8)).fillna(1.0)
    df['trend_strength'] = (ef - es).abs() / (df['atr'] + 1e-8)
    
    regime = np.zeros(len(df), dtype=np.int8)
    trending = df['trend_strength'].to_numpy() >= 0.5
    expanding = trending & (df['vol_ratio'].to_numpy() >= 1.15)
    regime[trending] = 1
    regime[expanding] = 2
    df['regime'] = regime
    
    df['next_open'] = df['open'].shift(-1)
    df.dropna(subset=['next_open', 'atr'], inplace=True)
    
    highs = df['high'].to_numpy(dtype=np.float64)
    lows = df['low'].to_numpy(dtype=np.float64)
    closes = df['close'].to_numpy(dtype=np.float64)
    next_opens = df['next_open'].to_numpy(dtype=np.float64)
    atrs = df['atr'].to_numpy(dtype=np.float64)
    
    df['lab_long'] = build_labels_numba(highs, lows, closes, next_opens, atrs, 1, 2.5, 1.0)
    df['lab_short'] = build_labels_numba(highs, lows, closes, next_opens, atrs, -1, 2.5, 1.0)
    
    float_cols = df.select_dtypes(include=['float64']).columns
    df[float_cols] = df[float_cols].astype('float32')
    return df

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
        
        open_mae = sum(p['mae_dollar'] for p in open_positions)
        cur_mtm_equity = capital - open_mae
        dd = (peak_capital - cur_mtm_equity) / peak_capital if peak_capital > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
            
        if (capital - initial_capital) >= 1010.0 and trades_executed >= 5 and len(open_positions) == 0:
            break
            
        if len(open_positions) >= MAX_CONCURRENT:
            continue
            
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
    btc_ref = get_btc_ref()
    files = sorted(glob.glob(os.path.join(DATA_DIR, "*_15m_master_*.parquet")))
    
    logger.info("Loading and featurizing all 18 symbols...")
    dfs = {}
    for f in files:
        sym = os.path.basename(f).split('_')[0]
        df_sym = preprocess_symbol_data(f, btc_ref)
        dfs[sym] = df_sym
        logger.info(f"  {sym}: {len(df_sym):,} rows")
        
    feature_cols = [
        'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'zc4', 'zc10', 'zc20', 'zb20', 'zb4',
        'liq_imbalance', 'liq_vol_ratio', 'liq_long_ratio', 'liq_short_ratio', 'liq_zscore_24h',
        'oi_flush', 'zoi', 'oid', 'oicc', 'fr', 'zfr', 'zls',
        'macro_spread', 'mc', 'p8', 'p21', 'p50', 'rsi', 'vol_ratio', 'trend_strength', 'regime'
    ]
    
    results = []
    for wi, (test_start_str, test_end_str) in enumerate(OOS_MONTHS):
        w_num = wi + 1
        test_start = pd.to_datetime(test_start_str, utc=True)
        test_end = pd.to_datetime(test_end_str, utc=True)
        train_end = test_start - pd.Timedelta(hours=3) # 3h purge gap
        train_start = test_start - relativedelta(months=18)
        
        # Prepare pooled training slice across all 18 symbols
        train_slices = []
        test_slices = []
        for sym, df_sym in dfs.items():
            tr = df_sym[(df_sym['datetime_utc'] >= train_start) & (df_sym['datetime_utc'] < train_end)]
            te = df_sym[(df_sym['datetime_utc'] >= test_start) & (df_sym['datetime_utc'] < test_end)]
            if not tr.empty: train_slices.append(tr)
            if not te.empty: test_slices.append(te)
            
        df_train = pd.concat(train_slices, ignore_index=True)
        df_test = pd.concat(test_slices, ignore_index=True)
        
        X_train = df_train[feature_cols].to_numpy(dtype=np.float32)
        y_train_long = df_train['lab_long'].to_numpy(dtype=np.int32)
        y_train_short = df_train['lab_short'].to_numpy(dtype=np.int32)
        
        # Train Dual Models: Long Model and Short Model
        m_long = lgb.LGBMClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.03, num_leaves=15,
            random_state=42, n_jobs=1, verbose=-1, min_child_samples=20
        )
        m_short = lgb.LGBMClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.03, num_leaves=15,
            random_state=42, n_jobs=1, verbose=-1, min_child_samples=20
        )
        m_long.fit(X_train, y_train_long)
        m_short.fit(X_train, y_train_short)
        
        # Predict on Test Window for each symbol
        all_oos_candidates = []
        for sym, df_sym in dfs.items():
            te_sym = df_sym[(df_sym['datetime_utc'] >= test_start) & (df_sym['datetime_utc'] < test_end)].reset_index(drop=True)
            if te_sym.empty: continue
            
            X_sym = te_sym[feature_cols].to_numpy(dtype=np.float32)
            prob_l = m_long.predict_proba(X_sym)[:, 1]
            prob_s = m_short.predict_proba(X_sym)[:, 1]
            
            highs = te_sym['high'].to_numpy(dtype=np.float64)
            lows = te_sym['low'].to_numpy(dtype=np.float64)
            closes = te_sym['close'].to_numpy(dtype=np.float64)
            next_opens = te_sym['next_open'].to_numpy(dtype=np.float64)
            atrs = te_sym['atr'].to_numpy(dtype=np.float64)
            datetimes = te_sym['datetime_utc'].to_numpy()
            mc = te_sym['mc'].to_numpy()
            p8 = te_sym['p8'].to_numpy()
            zc20 = te_sym['zc20'].to_numpy()
            zb20 = te_sym['zb20'].to_numpy() if 'zb20' in te_sym else np.zeros(len(te_sym))
            
            n_sym = len(te_sym)
            for idx in range(n_sym):
                pl = prob_l[idx]
                ps = prob_s[idx]
                
                dr = 0
                prob_val = 0.0
                if pl > 0.40 and pl > ps and mc[idx] >= 0 and p8[idx] < 0.10:
                    dr = 1
                    prob_val = pl
                elif ps > 0.40 and ps > pl and mc[idx] <= 0 and p8[idx] > -0.10:
                    dr = -1
                    prob_val = ps
                    
                if dr != 0:
                    entry_price = next_opens[idx]
                    atr_val = max(atrs[idx], 1e-6)
                    entry_time = datetimes[idx]
                    exit_price, offset, mae = simulate_single_trade_path(
                        highs, lows, closes, idx, entry_price, atr_val, dr, 0.015
                    )
                    exit_idx = min(idx + offset, n_sym - 1)
                    exit_time = datetimes[exit_idx]
                    stop_dist = max(atr_val, entry_price * 0.002)
                    r_mult = (exit_price - entry_price) / stop_dist if dr == 1 else (entry_price - exit_price) / stop_dist
                    
                    all_oos_candidates.append({
                        'symbol': sym,
                        'entry_time': entry_time,
                        'exit_time': exit_time,
                        'direction': int(dr),
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'atr': atr_val,
                        'mae': mae,
                        'r_multiple': r_mult,
                        'prob': prob_val
                    })
                    
        df_cands = pd.DataFrame(all_oos_candidates)
        if not df_cands.empty:
            df_cands['entry_time'] = pd.to_datetime(df_cands['entry_time'], utc=True)
            df_cands['exit_time'] = pd.to_datetime(df_cands['exit_time'], utc=True)
            df_cands = df_cands.sort_values(['entry_time', 'prob'], ascending=[True, False]).reset_index(drop=True)
            
        roi, dd, wr, tr, exec_df = execute_portfolio_backtest(df_cands)
        passed = (roi >= MIN_RETURN and dd <= MAX_DD and wr >= MIN_WIN_RATE and tr >= MIN_TRADES)
        status_icon = "✅ PASS" if passed else "❌ FAIL"
        logger.info(
            f"Window {w_num:02d} ({test_start_str} to {test_end_str}): Trades={tr:2d}, WR={wr:5.1%}, ROI={roi:6.2%}, MaxDD={dd:5.2%} -> {status_icon}"
        )
        results.append((w_num, passed, tr, wr, roi, dd))
        
    passed_count = sum(1 for r in results if r[1])
    logger.info(f"\n==========================================")
    logger.info(f"FINAL RESULT: {passed_count}/{len(results)} WINDOWS PASSED")
    logger.info(f"==========================================")

if __name__ == "__main__":
    run_test()
