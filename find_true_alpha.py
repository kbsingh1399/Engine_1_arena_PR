import os
import glob
import pandas as pd
import numpy as np
from numba import njit

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
def test_all_bars(highs, lows, closes, next_opens, atrs, directions):
    n = len(closes)
    r_multiples = np.zeros(n, dtype=np.float32)
    for i in range(100, n - 289):
        dr = directions[i]
        if dr != 0:
            entry = next_opens[i]
            av = atrs[i]
            if av > 0 and not np.isnan(av) and entry > 0:
                ep, offset, mae = simulate_single_trade_path(highs, lows, closes, i, entry, av, int(dr), 0.015)
                stop_dist = max(av, entry * 0.002)
                r_mult = (ep - entry) / stop_dist if dr == 1 else (entry - ep) / stop_dist
                r_multiples[i] = r_mult
    return r_multiples

def zs(s, w):
    m = s.rolling(w, min_periods=1).mean()
    std = s.rolling(w, min_periods=1).std().replace(0, 1e-8)
    return (s - m) / std

def analyze():
    files = sorted(glob.glob(os.path.join(DATA_DIR, "*_15m_master_*.parquet")))
    btc_path = os.path.join(DATA_DIR, "BTCUSDT_15m_master_2020_2026.parquet")
    btc_df = pd.read_parquet(btc_path)
    btc_df['datetime_utc'] = pd.to_datetime(btc_df['datetime_utc'], utc=True)
    btc_df = btc_df.sort_values('datetime_utc').reset_index(drop=True)
    btc_cvd = btc_df.get('spot_cvd_15m', btc_df.get('future_cvd_15m', pd.Series(0.0, index=btc_df.index)))
    btc_ref = pd.DataFrame({
        'datetime_utc': btc_df['datetime_utc'],
        'btc_close': btc_df['close'].astype(np.float32),
        'zb20': zs(btc_cvd, 96).clip(-4.0, 4.0).astype(np.float32)
    })
    
    # Analyze BTCUSDT and ETHUSDT and SOLUSDT
    sample_files = [f for f in files if any(s in f for s in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'DOGEUSDT'])]
    
    all_rows = []
    for f in sample_files:
        sym = os.path.basename(f).split('_')[0]
        df = pd.read_parquet(f)
        df['symbol'] = sym
        df['datetime_utc'] = pd.to_datetime(df['datetime_utc'], utc=True)
        df = df.sort_values('datetime_utc').reset_index(drop=True)
        if sym != 'BTCUSDT':
            df = pd.merge_asof(df, btc_ref, on='datetime_utc', direction='backward')
        else:
            df['zb20'] = zs(btc_cvd, 96).clip(-4.0, 4.0)
            
        spot_cvd = df.get('spot_cvd_15m', 0.0)
        fut_cvd = df.get('future_cvd_15m', 0.0)
        df['cvd_divergence'] = spot_cvd - fut_cvd
        df['spot_cvd_delta'] = spot_cvd.diff().fillna(0.0)
        df['zc4'] = zs(spot_cvd, 4).clip(-4.0, 4.0)
        df['zc10'] = zs(spot_cvd, 10).clip(-4.0, 4.0)
        df['zc20'] = zs(spot_cvd, 96).clip(-4.0, 4.0)
        
        long_liq = df.get('long_liq_usd', pd.Series(0.0, index=df.index)).abs().fillna(0.0)
        short_liq = df.get('short_liq_usd', pd.Series(0.0, index=df.index)).abs().fillna(0.0)
        denom = long_liq + short_liq + 1e-8
        df['liq_imbalance'] = (long_liq - short_liq) / denom
        
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
        
        highs = df['high'].to_numpy(dtype=np.float64)
        lows = df['low'].to_numpy(dtype=np.float64)
        closes = df['close'].to_numpy(dtype=np.float64)
        next_opens = df['next_open'].to_numpy(dtype=np.float64)
        atrs = df['atr'].to_numpy(dtype=np.float64)
        
        # Test long on all bars and short on all bars
        long_dirs = np.ones(len(df), dtype=np.int8)
        short_dirs = -np.ones(len(df), dtype=np.int8)
        
        df['r_long'] = test_all_bars(highs, lows, closes, next_opens, atrs, long_dirs)
        df['r_short'] = test_all_bars(highs, lows, closes, next_opens, atrs, short_dirs)
        
        keep_cols = [
            'datetime_utc', 'symbol', 'mc', 'macro_spread', 'p8', 'p21', 'rsi',
            'zc4', 'zc10', 'zc20', 'zb20', 'cvd_divergence', 'spot_cvd_delta',
            'liq_long_ratio', 'liq_short_ratio', 'liq_imbalance', 'fr', 'zfr',
            'vol_ratio', 'trend_strength', 'r_long', 'r_short'
        ]
        all_rows.append(df[keep_cols])
        print(f"Processed {sym}")
        
    master_df = pd.concat(all_rows, ignore_index=True)
    print(f"Total bars analyzed: {len(master_df):,}")
    
    # Evaluate specific high-probability conditions
    print("\n" + "="*70)
    print("SEARCHING FOR HIGH-WIN-RATE MICROSTRUCTURAL CONDITIONS (>40% WR, high avg R)")
    print("="*70)
    
    tests = [
        # Trend Pullback variations
        ("Long: mc > 0, p8 < -0.30, zc20 > zb20", (master_df['mc'] > 0) & (master_df['p8'] < -0.30) & (master_df['zc20'] > master_df['zb20']), 1),
        ("Long: mc > 0, p8 < -0.40, rsi < 35", (master_df['mc'] > 0) & (master_df['p8'] < -0.40) & (master_df['rsi'] < 35), 1),
        ("Long: mc > 0, p8 < -0.20, zc4 > 1.0", (master_df['mc'] > 0) & (master_df['p8'] < -0.20) & (master_df['zc4'] > 1.0), 1),
        ("Long: mc > 0, p8 < -0.20, liq_long > 2.0", (master_df['mc'] > 0) & (master_df['p8'] < -0.20) & (master_df['liq_long_ratio'] > 2.0), 1),
        
        # Consolidation & Mean Reversion
        ("Long: trend_str < 0.4, rsi < 28, p8 < -0.35", (master_df['trend_strength'] < 0.4) & (master_df['rsi'] < 28) & (master_df['p8'] < -0.35), 1),
        ("Long: trend_str < 0.4, zfr < -1.5, rsi < 32", (master_df['trend_strength'] < 0.4) & (master_df['zfr'] < -1.5) & (master_df['rsi'] < 32), 1),
        ("Long: trend_str < 0.4, liq_long > 2.5, rsi < 30", (master_df['trend_strength'] < 0.4) & (master_df['liq_long_ratio'] > 2.5) & (master_df['rsi'] < 30), 1),
        ("Long: liq_long > 2.0, zc4 > 0.0, rsi < 32", (master_df['liq_long_ratio'] > 2.0) & (master_df['zc4'] > 0.0) & (master_df['rsi'] < 32), 1),
        ("Long: zfr < -1.2, zc4 > 0.5, p8 < -0.20", (master_df['zfr'] < -1.2) & (master_df['zc4'] > 0.5) & (master_df['p8'] < -0.20), 1),
        
        # Shorts
        ("Short: mc < 0, p8 > 0.30, zc20 < zb20", (master_df['mc'] < 0) & (master_df['p8'] > 0.30) & (master_df['zc20'] < master_df['zb20']), -1),
        ("Short: mc < 0, p8 > 0.40, rsi > 65", (master_df['mc'] < 0) & (master_df['p8'] > 0.40) & (master_df['rsi'] > 65), -1),
        ("Short: trend_str < 0.4, rsi > 72, p8 > 0.35", (master_df['trend_strength'] < 0.4) & (master_df['rsi'] > 72) & (master_df['p8'] > 0.35), -1),
        ("Short: trend_str < 0.4, zfr > 1.5, rsi > 68", (master_df['trend_strength'] < 0.4) & (master_df['zfr'] > 1.5) & (master_df['rsi'] > 68), -1),
        ("Short: trend_str < 0.4, liq_short > 2.5, rsi > 70", (master_df['trend_strength'] < 0.4) & (master_df['liq_short_ratio'] > 2.5) & (master_df['rsi'] > 70), -1),
        ("Short: liq_short > 2.0, zc4 < 0.0, rsi > 68", (master_df['liq_short_ratio'] > 2.0) & (master_df['zc4'] < 0.0) & (master_df['rsi'] > 68), -1),
        ("Short: zfr > 1.2, zc4 < -0.5, p8 > 0.20", (master_df['zfr'] > 1.2) & (master_df['zc4'] < -0.5) & (master_df['p8'] > 0.20), -1),
    ]
    
    for desc, mask, dr in tests:
        sub = master_df[mask]
        n = len(sub)
        if n == 0: continue
        r_vals = sub['r_long'] if dr == 1 else sub['r_short']
        wins = (r_vals > 0.0).sum()
        wr = wins / n * 100
        avg_r = r_vals.mean()
        tot_r = r_vals.sum()
        print(f"{desc:<55s} | n={n:5d} | WR={wr:5.1f}% | Avg R={avg_r:5.2f} | Tot R={tot_r:7.1f}")

if __name__ == "__main__":
    analyze()
