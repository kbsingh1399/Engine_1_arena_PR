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

def test_setups():
    btc_ref = get_btc_ref()
    files = sorted(glob.glob(os.path.join(DATA_DIR, "*_15m_master_*.parquet")))
    
    setups = {
        "1. Deep Flash Liquidation Flush (Liq Spike + Extreme RSI + CVD Turn)": lambda df: (
            ((df['liq_long_ratio'] > 2.0) & (df['rsi'] < 28) & (df['p8'] < -0.40) & (df['spot_cvd_delta'] > 0)),
            ((df['liq_short_ratio'] > 2.0) & (df['rsi'] > 72) & (df['p8'] > 0.40) & (df['spot_cvd_delta'] < 0))
        ),
        "2. Funding Rate Squeeze Extreme (ZFR < -1.8 / > 1.8 + RSI Extreme)": lambda df: (
            ((df['zfr'] < -1.8) & (df['rsi'] < 30) & (df['p8'] < -0.35)),
            ((df['zfr'] > 1.8) & (df['rsi'] > 70) & (df['p8'] > 0.35))
        ),
        "3. Spot CVD Divergence at Support/Resistance (Spot CVD > EMA but Price < EMA)": lambda df: (
            ((df['zc4'] > 1.0) & (df['p8'] < -0.35) & (df['rsi'] < 35)),
            ((df['zc4'] < -1.0) & (df['p8'] > 0.35) & (df['rsi'] > 65))
        ),
        "4. Squeeze Breakout Expansion (Vol Expansion + Trend Breakout + High CVD)": lambda df: (
            ((df['vol_ratio'] > 1.25) & (df['trend_strength'] > 0.8) & (df['mc'] > 0) & (df['p8'] > 0.1) & (df['p8'] < 0.5) & (df['zc20'] > 0.5)),
            ((df['vol_ratio'] > 1.25) & (df['trend_strength'] > 0.8) & (df['mc'] < 0) & (df['p8'] < -0.1) & (df['p8'] > -0.5) & (df['zc20'] < -0.5))
        ),
        "5. Extreme Macro Pullback in Strong Trend (MC=1 + P8 < -0.45 + Relative CVD > 0)": lambda df: (
            ((df['mc'] > 0) & (df['p8'] < -0.45) & (df['rsi'] < 35) & (df['zc20'] > df['zb20'] - 0.05)),
            ((df['mc'] < 0) & (df['p8'] > 0.45) & (df['rsi'] > 65) & (df['zc20'] < df['zb20'] + 0.05))
        )
    }
    
    for name, setup_func in setups.items():
        total_tr = 0
        total_wn = 0
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
            
            mask_l, mask_s = setup_func(df)
            sig = np.zeros(len(df), dtype=np.int8)
            sig[mask_l] = 1
            sig[mask_s] = -1
            
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
                        total_tr += 1
                        if r_mult > 0.0:
                            total_wn += 1
                        total_r += r_mult
                        r_list.append(r_mult)
                        cd = i + max(offset, 1) + 1
                i += 1
                
        wr = total_wn / max(total_tr, 1) * 100
        avg_r = total_r / max(total_tr, 1)
        print(f"\n{name}:")
        print(f"  Trades: {total_tr:,} | Win Rate: {wr:.1f}% | Avg R: {avg_r:.3f} | Total R: {total_r:,.1f}")

if __name__ == "__main__":
    test_setups()
