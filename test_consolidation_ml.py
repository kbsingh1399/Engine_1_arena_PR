import os
import glob
import pandas as pd
import numpy as np
from datetime import datetime
from numba import njit
import lightgbm as lgb
import gc

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "Engine_2", "binance_backtesting_data")

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

def featurize_and_extract(file_path, btc_ref):
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
    
    df['liql'] = long_liq.rolling(5, min_periods=1).sum()
    df['liqs'] = short_liq.rolling(5, min_periods=1).sum()
    df['liqlm'] = df['liql'].rolling(96, min_periods=1).mean() + 1e-8
    df['liqsm'] = df['liqs'].rolling(96, min_periods=1).mean() + 1e-8
    df['liq_long_ratio'] = df['liql'] / df['liqlm']
    df['liq_short_ratio'] = df['liqs'] / df['liqsm']
    df['liq_zscore_24h'] = zs(long_liq + short_liq, 96).clip(-4.0, 4.0)
    
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
    
    df['next_open'] = df['open'].shift(-1)
    df.dropna(subset=['next_open', 'atr'], inplace=True)
    
    mc = df['mc'].values
    p8 = df['p8'].values
    zc20 = df['zc20'].values
    zb20 = df['zb20'].values
    zc4 = df['zc4'].values
    rsi = df['rsi'].values
    liq_l = df['liq_long_ratio'].values
    liq_s = df['liq_short_ratio'].values
    fr = df['fr'].values
    zfr = df['zfr'].values
    trend_str = df['trend_strength'].values
    
    # Combined Multi-Regime Signal Generator
    mask_l_tr = (trend_str >= 0.35) & (mc > 0) & (p8 < -0.16) & (zc20 > zb20 - 0.08)
    mask_s_tr = (trend_str >= 0.35) & (mc < 0) & (p8 > 0.16) & (zc20 < zb20 + 0.08)
    
    mask_l_rg = (trend_str < 0.45) & (
        ((liq_l > 1.3) & (p8 < -0.12) & (rsi < 40) & (zc4 > -0.5)) |
        ((rsi < 35) & (p8 < -0.20) & ((zfr < -0.8) | (fr < -0.002)))
    )
    mask_s_rg = (trend_str < 0.45) & (
        ((liq_s > 1.3) & (p8 > 0.12) & (rsi > 60) & (zc4 < 0.5)) |
        ((rsi > 65) & (p8 > 0.20) & ((zfr > 0.8) | (fr > 0.002)))
    )
    
    sig = np.zeros(len(df), dtype=np.int8)
    sig[mask_l_tr | mask_l_rg] = 1
    sig[mask_s_tr | mask_s_rg] = -1
    
    highs = df['high'].to_numpy(dtype=np.float64)
    lows = df['low'].to_numpy(dtype=np.float64)
    closes = df['close'].to_numpy(dtype=np.float64)
    next_opens = df['next_open'].to_numpy(dtype=np.float64)
    atrs = df['atr'].to_numpy(dtype=np.float64)
    datetimes = df['datetime_utc'].to_numpy()
    
    res = gen_symbol_trades(highs, lows, closes, next_opens, atrs, sig)
    
    feature_cols = [
        'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
        'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
        'liq_imbalance', 'liq_vol_ratio', 'liq_long_ratio', 'liq_short_ratio', 'liq_zscore_24h',
        'oi_flush', 'zoi', 'oid', 'oicc', 'fr', 'zfr', 'zls',
        'macro_spread', 'mc', 'p8', 'p21', 'p50', 'rsi', 'vol_ratio', 'trend_strength'
    ]
    feat_dict = {c: df[c].to_numpy(dtype=np.float32) for c in feature_cols if c in df.columns}
    
    trades = []
    n = len(df)
    for idx, dr, ep, r_mult, lb, offset, mae in res:
        et = datetimes[idx]
        xi = min(int(idx) + int(offset), n - 1)
        xt = datetimes[xi]
        atr_val = atrs[idx]
        entry_price = next_opens[idx]
        
        t = {
            'symbol': sym,
            'entry_time': et,
            'exit_time': xt,
            'direction': int(dr),
            'entry_price': entry_price,
            'exit_price': ep,
            'atr': atr_val,
            'mae': mae,
            'r_multiple': r_mult,
            'label': int(lb)
        }
        for col, arr in feat_dict.items():
            t[col] = float(arr[idx])
        trades.append(t)
        
    del df, highs, lows, closes, next_opens, atrs, datetimes, feat_dict
    gc.collect()
    return trades

print("Loaded extractor.")
