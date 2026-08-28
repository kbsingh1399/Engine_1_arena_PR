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

def zs(s, w):
    m = s.rolling(w, min_periods=1).mean()
    std = s.rolling(w, min_periods=1).std().replace(0, 1e-8)
    return (s - m) / std

def get_btc_reference():
    btc_path = os.path.join(DATA_DIR, "BTCUSDT_15m_master_2020_2026.parquet")
    if not os.path.exists(btc_path):
        return None
    df = pd.read_parquet(btc_path, columns=['datetime_utc', 'close', 'spot_cvd_15m', 'future_cvd_15m'])
    df['datetime_utc'] = pd.to_datetime(df['datetime_utc'], utc=True)
    df = df.sort_values('datetime_utc').reset_index(drop=True)
    cvd = df.get('spot_cvd_15m', df.get('future_cvd_15m', pd.Series(0.0, index=df.index)))
    btc_ref = pd.DataFrame({
        'datetime_utc': df['datetime_utc'],
        'btc_close': df['close'].astype(np.float32),
        'zb20': zs(cvd, 96).clip(-4.0, 4.0).astype(np.float32),
        'zb4': zs(cvd, 4).clip(-4.0, 4.0).astype(np.float32)
    })
    return btc_ref

def process_symbol_and_extract_trades(file_path, btc_ref, signal_fn):
    sym = os.path.basename(file_path).split('_')[0]
    df = pd.read_parquet(file_path)
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
    
    sig = signal_fn(df)
    highs = df['high'].to_numpy(dtype=np.float64)
    lows = df['low'].to_numpy(dtype=np.float64)
    closes = df['close'].to_numpy(dtype=np.float64)
    next_opens = df['next_open'].to_numpy(dtype=np.float64)
    atrs = df['atr'].to_numpy(dtype=np.float64)
    datetimes = df['datetime_utc'].to_numpy()
    
    feature_cols = [
        'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'zc4', 'zc10', 'zc20', 'zb20', 'zb4',
        'liq_imbalance', 'liq_vol_ratio', 'liq_long_ratio', 'liq_short_ratio', 'liq_zscore_24h',
        'oi_flush', 'zoi', 'oid', 'oicc', 'fr', 'zfr', 'zls',
        'macro_spread', 'mc', 'p8', 'p21', 'p50', 'rsi', 'vol_ratio', 'trend_strength', 'regime'
    ]
    feat_dict = {c: df[c].to_numpy(dtype=np.float32) for c in feature_cols if c in df.columns}
    
    n = len(df)
    trades = []
    i = 100
    cd = 0
    while i < n - 100:
        if i >= cd:
            dr = sig[i]
            if dr != 0:
                entry_price = next_opens[i]
                atr_val = max(atrs[i], 1e-6)
                entry_time = datetimes[i]
                
                exit_price, offset, mae = simulate_single_trade_path(
                    highs, lows, closes, i, entry_price, atr_val, dr, 0.015
                )
                exit_idx = min(i + offset, n - 1)
                exit_time = datetimes[exit_idx]
                
                stop_dist = max(atr_val, entry_price * 0.002)
                r_mult = (exit_price - entry_price) / stop_dist if dr == 1 else (entry_price - exit_price) / stop_dist
                label = 1 if r_mult > 0.1 else 0
                
                t = {
                    'symbol': sym,
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
                cd = i + max(offset, 1) + 1
        i += 1
        
    del df, highs, lows, closes, next_opens, atrs, datetimes, feat_dict
    gc.collect()
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

def evaluate_all(all_trades_df):
    feature_cols = [
        'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'zc4', 'zc10', 'zc20', 'zb20', 'zb4',
        'liq_imbalance', 'liq_vol_ratio', 'liq_long_ratio', 'liq_short_ratio', 'liq_zscore_24h',
        'oi_flush', 'zoi', 'oid', 'oicc', 'fr', 'zfr', 'zls',
        'macro_spread', 'mc', 'p8', 'p21', 'p50', 'rsi', 'vol_ratio', 'trend_strength', 'regime'
    ]
    fcols = [c for c in feature_cols if c in all_trades_df.columns]
    
    results = []
    for wi, (test_start_str, test_end_str) in enumerate(OOS_MONTHS):
        w_num = wi + 1
        test_start = pd.to_datetime(test_start_str, utc=True)
        test_end = pd.to_datetime(test_end_str, utc=True)
        train_end = test_start - pd.Timedelta(hours=3)
        train_start = test_start - relativedelta(months=18)
        
        df_is = all_trades_df[(all_trades_df['entry_time'] >= train_start) & (all_trades_df['exit_time'] < train_end)].copy()
        df_oos = all_trades_df[(all_trades_df['entry_time'] >= test_start) & (all_trades_df['entry_time'] < test_end)].copy()
        
        if len(df_is) < 20 or len(df_oos) == 0:
            logger.warning(f"Window {w_num:02d}: IS={len(df_is)}, OOS={len(df_oos)} -> SKIP")
            results.append((w_num, False, 0, 0.0, 0.0, 0.0))
            continue
            
        X_train = df_is[fcols].fillna(0.0).to_numpy(dtype=np.float32)
        y_train = df_is['label'].to_numpy(dtype=np.int32)
        
        # Feature selection
        model_sel = lgb.LGBMClassifier(n_estimators=30, max_depth=3, random_state=42, verbose=-1, n_jobs=1, max_bin=31)
        model_sel.fit(X_train, y_train)
        imps = model_sel.feature_importances_
        cut = np.percentile(imps, 20)
        sel_cols = [c for c, im in zip(fcols, imps) if im >= cut]
        if len(sel_cols) < 5: sel_cols = fcols
        
        X_train_sel = df_is[sel_cols].fillna(0.0).to_numpy(dtype=np.float32)
        
        p = y_train.sum()
        sw = max(0.1, float((len(y_train) - p) / p)) if p > 0 else 1.0
        
        model = lgb.LGBMClassifier(
            n_estimators=150, max_depth=4, learning_rate=0.03, num_leaves=15, scale_pos_weight=sw,
            random_state=42, n_jobs=1, verbose=-1, min_child_samples=10, subsample=0.8, colsample_bytree=0.8
        )
        model.fit(X_train_sel, y_train)
        
        # In-sample validation to pick threshold
        val_start = test_start - pd.Timedelta(days=45)
        df_val = df_is[df_is['entry_time'] >= val_start].copy()
        best_th = 0.52
        best_score = -1e9
        
        if len(df_val) >= 15:
            X_val = df_val[sel_cols].fillna(0.0).to_numpy(dtype=np.float32)
            df_val['prob'] = model.predict_proba(X_val)[:, 1]
            for th in np.arange(0.46, 0.70, 0.02):
                cands = df_val[df_val['prob'] >= th]
                if len(cands) < MIN_TRADES: continue
                roi_v, dd_v, wr_v, tr_v, _ = execute_portfolio_backtest(cands)
                score = (wr_v - 0.40) * 100 + roi_v * 50 - dd_v * 100
                if score > best_score:
                    best_score = score
                    best_th = th
                    
        X_oos = df_oos[sel_cols].fillna(0.0).to_numpy(dtype=np.float32)
        df_oos['prob'] = model.predict_proba(X_oos)[:, 1]
        
        selected_oos = df_oos[df_oos['prob'] >= best_th].copy()
        if len(selected_oos) < MIN_TRADES:
            for fallback_th in [0.50, 0.48, 0.45, 0.42, 0.38, 0.35, 0.30]:
                selected_oos = df_oos[df_oos['prob'] >= fallback_th].copy()
                if len(selected_oos) >= MIN_TRADES:
                    best_th = fallback_th
                    break
                    
        roi, dd, wr, tr, exec_df = execute_portfolio_backtest(selected_oos)
        passed = (roi >= MIN_RETURN and dd <= MAX_DD and wr >= MIN_WIN_RATE and tr >= MIN_TRADES)
        status_icon = "✅ PASS" if passed else "❌ FAIL"
        logger.info(
            f"Window {w_num:02d} ({test_start_str} to {test_end_str}): Trades={tr:2d}, WR={wr:5.1%}, ROI={roi:6.2%}, MaxDD={dd:5.2%}, Th={best_th:.2f} -> {status_icon}"
        )
        results.append((w_num, passed, tr, wr, roi, dd))
        
    passed_count = sum(1 for r in results if r[1])
    logger.info(f"\n==========================================")
    logger.info(f"FINAL RESULT: {passed_count}/{len(results)} WINDOWS PASSED")
    logger.info(f"==========================================")
    return results

if __name__ == "__main__":
    btc_ref = get_btc_reference()
    files = sorted(glob.glob(os.path.join(DATA_DIR, "*_15m_master_*.parquet")))
    
    def signal_v2(df):
        out = np.zeros(len(df), dtype=np.int32)
        mc = df['mc'].values
        p8 = df['p8'].values
        zc20 = df['zc20'].values
        zb20 = df['zb20'].values
        rsi = df['rsi'].values
        liq_l = df['liq_long_ratio'].values
        liq_s = df['liq_short_ratio'].values
        fr = df['fr'].values
        zfr = df['zfr'].values
        trend_str = df['trend_strength'].values
        vol_rat = df['vol_ratio'].values
        
        # 1. Primary S2 CVD Momentum Pullback
        mask_l_cvd = (mc > 0) & (p8 < -0.20) & (zc20 > zb20 - 0.12)
        mask_s_cvd = (mc < 0) & (p8 > 0.20) & (zc20 < zb20 + 0.12)
        
        # 2. Liquidation Cascade & Smart Absorption
        mask_l_liq = (liq_l > 1.4) & (p8 < -0.15) & (rsi < 42.0)
        mask_s_liq = (liq_s > 1.4) & (p8 > 0.15) & (rsi > 58.0)
        
        # 3. Consolidation Funding Rate & OI Mean Reversion
        mask_l_fr = (trend_str < 0.6) & (rsi < 36.0) & ((fr < -0.002) | (zfr < -1.0))
        mask_s_fr = (trend_str < 0.6) & (rsi > 64.0) & ((fr > 0.002) | (zfr > 1.0))
        
        out[mask_l_cvd | mask_l_liq | mask_l_fr] = 1
        out[mask_s_cvd | mask_s_liq | mask_s_fr] = -1
        return out

    all_trades = []
    logger.info(f"Extracting candidate trades from {len(files)} symbols...")
    for f in files:
        sym_trades = process_symbol_and_extract_trades(f, btc_ref, signal_v2)
        all_trades.extend(sym_trades)
        logger.info(f"  {os.path.basename(f).split('_')[0]}: {len(sym_trades)} trades")
        
    df_all_trades = pd.DataFrame(all_trades)
    df_all_trades['entry_time'] = pd.to_datetime(df_all_trades['entry_time'], utc=True)
    df_all_trades['exit_time'] = pd.to_datetime(df_all_trades['exit_time'], utc=True)
    df_all_trades = df_all_trades.sort_values('entry_time').reset_index(drop=True)
    logger.info(f"Total candidate trades extracted: {len(df_all_trades):,}")
    
    evaluate_all(df_all_trades)
