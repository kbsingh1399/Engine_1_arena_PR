import os
import glob
import json
import logging
import pandas as pd
import numpy as np
from numba import njit

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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

def test_concept(sig_name, sig_func):
    btc_ref = get_btc_ref()
    files = sorted(glob.glob(os.path.join(DATA_DIR, "*_15m_master_*.parquet")))
    
    total_trades = 0
    total_wins = 0
    total_r = 0.0
    r_list = []
    
    for f in files:
        sym = os.path.basename(f).split('_')[0]
        df = pd.read_parquet(f)
        df['datetime_utc'] = pd.to_datetime(df['datetime_utc'], utc=True)
        df = df.sort_values('datetime_utc').reset_index(drop=True)
        
        if sym != "BTCUSDT":
            df = pd.merge_asof(df, btc_ref, on='datetime_utc', direction='backward')
        else:
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
        
        df['fr'] = df.get('funding_rate_pct', pd.Series(0.0, index=df.index)).fillna(0.0)
        df['zfr'] = zs(df['fr'], 20)
        
        df['atr'] = (df['high'] - df['low']).rolling(14, min_periods=1).mean().clip(lower=1e-6)
        df['rsi'] = df.get('rsi_14', 50.0).fillna(50.0)
        
        ef = df['close'].ewm(span=200, min_periods=50).mean()
        es = df['close'].ewm(span=800, min_periods=100).mean()
        df['macro_spread'] = (ef - es) / (df['atr'] + 1e-8)
        df['mc'] = np.where(df['macro_spread'] > 0.5, 1.0, np.where(df['macro_spread'] < -0.5, -1.0, 0.0))
        
        e8 = df['close'].ewm(span=8, min_periods=1).mean()
        e21 = df['close'].ewm(span=21, min_periods=1).mean()
        df['p8'] = (df['close'] - e8) / (df['atr'] + 1e-8)
        df['p21'] = (df['close'] - e21) / (df['atr'] + 1e-8)
        
        log_ret = np.log(df['close'].clip(lower=1e-6)).diff()
        rv_short = log_ret.rolling(96, min_periods=24).std()
        rv_long = log_ret.rolling(672, min_periods=96).std()
        df['vol_ratio'] = (rv_short / (rv_long + 1e-8)).fillna(1.0)
        df['trend_strength'] = (ef - es).abs() / (df['atr'] + 1e-8)
        
        df['next_open'] = df['open'].shift(-1)
        df.dropna(subset=['next_open', 'atr'], inplace=True)
        
        sig = sig_func(df)
        highs = df['high'].to_numpy(dtype=np.float64)
        lows = df['low'].to_numpy(dtype=np.float64)
        closes = df['close'].to_numpy(dtype=np.float64)
        next_opens = df['next_open'].to_numpy(dtype=np.float64)
        atrs = df['atr'].to_numpy(dtype=np.float64)
        
        n = len(df)
        i = 100
        cd = 0
        while i < n - 100:
            if i >= cd:
                dr = sig[i]
                if dr != 0:
                    entry_price = next_opens[i]
                    atr_val = max(atrs[i], 1e-6)
                    exit_price, offset, mae = simulate_single_trade_path(
                        highs, lows, closes, i, entry_price, atr_val, dr, 0.015
                    )
                    stop_dist = max(atr_val, entry_price * 0.002)
                    r_mult = (exit_price - entry_price) / stop_dist if dr == 1 else (entry_price - exit_price) / stop_dist
                    total_trades += 1
                    if r_mult > 0.0:
                        total_wins += 1
                    total_r += r_mult
                    r_list.append(r_mult)
                    cd = i + max(offset, 1) + 1
            i += 1
            
    wr = total_wins / max(total_trades, 1) * 100
    avg_r = total_r / max(total_trades, 1)
    print(f"[{sig_name}] Total Trades: {total_trades:,} | Win Rate: {wr:.1f}% | Avg R: {avg_r:.3f} | Total R: {total_r:,.1f}")

if __name__ == "__main__":
    # 1. Pure Trend Pullback with CVD
    def sig_cvd_trend(df):
        out = np.zeros(len(df), dtype=np.int8)
        mc = df['mc'].values
        p8 = df['p8'].values
        zc20 = df['zc20'].values
        zb20 = df['zb20'].values
        mask_l = (mc > 0) & (p8 < -0.22) & (zc20 > zb20 - 0.08)
        mask_s = (mc < 0) & (p8 > 0.22) & (zc20 < zb20 + 0.08)
        out[mask_l] = 1; out[mask_s] = -1
        return out

    # 2. Liquidation Cascade Exhaustion
    def sig_liq_cascade(df):
        out = np.zeros(len(df), dtype=np.int8)
        liq_l = df['liq_long_ratio'].values
        liq_s = df['liq_short_ratio'].values
        rsi = df['rsi'].values
        p8 = df['p8'].values
        zc4 = df['zc4'].values
        mask_l = (liq_l > 2.0) & (rsi < 32) & (p8 < -0.30) & (zc4 > -0.5)
        mask_s = (liq_s > 2.0) & (rsi > 68) & (p8 > 0.30) & (zc4 < 0.5)
        out[mask_l] = 1; out[mask_s] = -1
        return out

    # 3. Funding Rate & OI Exhaustion
    def sig_funding_oi(df):
        out = np.zeros(len(df), dtype=np.int8)
        fr = df['fr'].values
        zfr = df['zfr'].values
        rsi = df['rsi'].values
        p8 = df['p8'].values
        mask_l = (zfr < -1.5) & (rsi < 30) & (p8 < -0.30)
        mask_s = (zfr > 1.5) & (rsi > 70) & (p8 > 0.30)
        out[mask_l] = 1; out[mask_s] = -1
        return out

    # 4. Spot CVD Divergence
    def sig_spot_div(df):
        out = np.zeros(len(df), dtype=np.int8)
        div = df['cvd_divergence'].values
        p8 = df['p8'].values
        rsi = df['rsi'].values
        mask_l = (div > 0) & (p8 < -0.25) & (rsi < 35)
        mask_s = (div < 0) & (p8 > 0.25) & (rsi > 65)
        out[mask_l] = 1; out[mask_s] = -1
        return out

    print("Benchmarking signal concepts across full 6-year history (3.4M candles)...")
    test_concept("1. CVD Trend Pullback", sig_cvd_trend)
    test_concept("2. Liquidation Cascade", sig_liq_cascade)
    test_concept("3. Funding / OI Squeeze", sig_funding_oi)
    test_concept("4. Spot CVD Divergence", sig_spot_div)
