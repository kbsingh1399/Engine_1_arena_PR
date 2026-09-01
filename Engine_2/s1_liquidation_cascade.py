#!/usr/bin/env python3
"""
================================================================================
ENGINE 2: S1 - LIQUIDATION CASCADE STRATEGY (VERIFIED 0.80 QUANTILE)
================================================================================
"""

import os, sys, time, gc, glob, json, logging
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
import warnings
warnings.filterwarnings('ignore')

from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb
from numba import njit

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("S1_Cascade")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
DATA_DIR = os.path.join(SCRIPT_DIR, "binance_backtesting_data") if os.path.exists(os.path.join(SCRIPT_DIR, "binance_backtesting_data")) else SCRIPT_DIR
RESULTS_DIR = os.path.join(SCRIPT_DIR, "results_s1")
os.makedirs(RESULTS_DIR, exist_ok=True)

MIN_RETURN = 0.20
MAX_DD = 0.05
MIN_WIN_RATE = 0.40
MIN_TRADES = 5

INITIAL_CAPITAL = 5000.0
BASE_RISK = 104.0
MAX_HOUSE_RISK = 385.0
MIN_DEFENSE_RISK = 18.0
FEE_RATE = 0.0009
MAX_CONCURRENT = 2
LEVERAGE = 10.0
MAX_NOTIONAL = 50000.0
DRAWDOWN_LIMIT = 0.042

def zs(s, w):
    m = s.rolling(w, min_periods=1).mean()
    std = s.rolling(w, min_periods=1).std().replace(0.0, 1e-8)
    return ((s - m) / std).clip(-5.0, 5.0).fillna(0.0)

def compute_true_atr(df, period=14):
    prev_close = df['close'].shift(1)
    tr1 = df['high'] - df['low']
    tr2 = (df['high'] - prev_close).abs()
    tr3 = (df['low'] - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=1).mean()

@njit(nogil=True)
def simulate_single_trade_path(highs, lows, closes, entry_idx, entry_price, atr, direction, max_bars=144):
    stop_dist = max(2.0 * atr, entry_price * 0.0065)
    cur_stop = entry_price - stop_dist if direction == 1 else entry_price + stop_dist
    best_price = entry_price
    
    exit_price = closes[min(entry_idx + max_bars, len(closes) - 1)]
    exit_offset = max_bars
    max_idx = min(entry_idx + max_bars + 1, len(closes))
    
    SLIPPAGE_PCT = 0.0005
    
    for j in range(entry_idx + 1, max_idx):
        bars_held = j - entry_idx
        
        if direction == 1: # LONG
            if lows[j] <= cur_stop:
                exit_price = cur_stop * (1.0 - SLIPPAGE_PCT)
                exit_offset = bars_held
                break
                
            if bars_held == 48 and (highs[j] - entry_price) < 0.35 * stop_dist:
                exit_price = closes[j]
                exit_offset = bars_held
                break
                
            if highs[j] > best_price:
                best_price = highs[j]
                gain = best_price - entry_price
                if gain >= 5.5 * stop_dist:
                    exit_price = entry_price + 5.5 * stop_dist
                    exit_offset = bars_held
                    break
                elif gain >= 4.2 * stop_dist:
                    new_stop = entry_price + 3.5 * stop_dist
                    if new_stop > cur_stop: cur_stop = new_stop
                elif gain >= 3.0 * stop_dist:
                    new_stop = entry_price + 2.4 * stop_dist
                    if new_stop > cur_stop: cur_stop = new_stop
                elif gain >= 2.2 * stop_dist:
                    new_stop = entry_price + 1.6 * stop_dist
                    if new_stop > cur_stop: cur_stop = new_stop
                elif gain >= 1.25 * stop_dist:
                    new_stop = entry_price + 0.40 * stop_dist
                    if new_stop > cur_stop: cur_stop = new_stop
        else: # SHORT
            if highs[j] >= cur_stop:
                exit_price = cur_stop * (1.0 + SLIPPAGE_PCT)
                exit_offset = bars_held
                break
                
            if bars_held == 48 and (entry_price - lows[j]) < 0.35 * stop_dist:
                exit_price = closes[j]
                exit_offset = bars_held
                break
                
            if lows[j] < best_price:
                best_price = lows[j]
                gain = entry_price - best_price
                if gain >= 5.5 * stop_dist:
                    exit_price = entry_price - 5.5 * stop_dist
                    exit_offset = bars_held
                    break
                elif gain >= 4.2 * stop_dist:
                    new_stop = entry_price - 3.5 * stop_dist
                    if new_stop < cur_stop: cur_stop = new_stop
                elif gain >= 3.0 * stop_dist:
                    new_stop = entry_price - 2.4 * stop_dist
                    if new_stop < cur_stop: cur_stop = new_stop
                elif gain >= 2.2 * stop_dist:
                    new_stop = entry_price - 1.6 * stop_dist
                    if new_stop < cur_stop: cur_stop = new_stop
                elif gain >= 1.25 * stop_dist:
                    new_stop = entry_price - 0.40 * stop_dist
                    if new_stop < cur_stop: cur_stop = new_stop



                    
    return exit_price, exit_offset

@njit(nogil=True)
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
                    ep, offset = simulate_single_trade_path(
                        highs, lows, closes, i, entry, av, int(dr), 144
                    )
                    stop_dist = max(2.0 * av, entry * 0.0065)
                    r_mult = (ep - entry) / stop_dist if dr == 1 else (entry - ep) / stop_dist
                    lb = 1.0 if r_mult >= 1.0 else 0.0
                    results.append((i, dr, ep, r_mult, lb, offset))
                    cd = i + max(offset, 1) + 2
        i += 1
    return results

def s1_signal_predicate(df):
    liq_long = df.get('long_liq_usd', pd.Series(0.0, index=df.index)).fillna(0.0)
    liq_short = df.get('short_liq_usd', pd.Series(0.0, index=df.index)).fillna(0.0)
    c = df['close']
    
    long_cascade = (liq_short > liq_short.rolling(96, min_periods=1).quantile(0.80)) & (c > c.shift(1))
    short_cascade = (liq_long > liq_long.rolling(96, min_periods=1).quantile(0.80)) & (c < c.shift(1))
    return long_cascade, short_cascade

def load_s1_trades(feature_cols):
    search_dirs = [DATA_DIR, SCRIPT_DIR, os.path.join(SCRIPT_DIR, "binance_backtesting_data")]
    files = []
    for d in search_dirs:
        if d and os.path.exists(d):
            found = glob.glob(os.path.join(d, "*_15m_master_*.parquet"))
            if found:
                files = sorted(list(set(found)))
                break
                
    if not files: return pd.DataFrame()

    btc_ref = None
    for f in files:
        if "BTCUSDT" in os.path.basename(f):
            try:
                bdf = pd.read_parquet(f, columns=['datetime_utc', 'close', 'spot_cvd_15m', 'future_cvd_15m'])
                bdf['datetime_utc'] = pd.to_datetime(bdf['datetime_utc'], utc=True)
                bdf = bdf.sort_values('datetime_utc').reset_index(drop=True)
                s_raw = bdf['spot_cvd_15m'].fillna(0.0)
                f_raw = bdf['future_cvd_15m'].fillna(0.0)
                s_diff = s_raw.diff().fillna(0.0)
                f_diff = f_raw.diff().fillna(0.0)
                cvd_delta = np.where(s_diff.abs() > 1e-5, s_diff, f_diff)
                cvd_cum = pd.Series(np.cumsum(cvd_delta), index=bdf.index)
                
                btc_ema50 = bdf['close'].ewm(span=50).mean()
                btc_trend = ((bdf['close'] - btc_ema50) / btc_ema50).clip(-0.20, 0.20).fillna(0.0)
                
                btc_ref = pd.DataFrame({
                    'datetime_utc': bdf['datetime_utc'],
                    'btc_close': bdf['close'].astype(np.float32),
                    'btc_trend': btc_trend.astype(np.float32),
                    'zb20': zs(cvd_cum, 96).astype(np.float32),
                    'zb4': zs(cvd_cum, 4).astype(np.float32)
                })
                del bdf; gc.collect()
                break
            except Exception as e: pass

    trades_list = []
    cols_to_load = [
        'datetime_utc', 'open', 'high', 'low', 'close', 'volume_base',
        'spot_cvd_15m', 'future_cvd_15m', 'long_liq_usd', 'short_liq_usd'
    ]
    for f in sorted(files):
        sym = os.path.basename(f).split('_')[0]
        if not sym.endswith("USDT"): continue
        try:
            df = pd.read_parquet(f, columns=cols_to_load)
            df['datetime_utc'] = pd.to_datetime(df['datetime_utc'], utc=True)
            df = df.sort_values('datetime_utc').reset_index(drop=True)
            
            s_raw = df.get('spot_cvd_15m', pd.Series(0.0, index=df.index)).fillna(0.0)
            f_raw = df.get('future_cvd_15m', pd.Series(0.0, index=df.index)).fillna(0.0)
            s_diff = s_raw.diff().fillna(0.0)
            f_diff = f_raw.diff().fillna(0.0)
            active_delta = pd.Series(np.where(s_diff.abs() > 1e-5, s_diff, f_diff), index=df.index)
            active_cvd = pd.Series(np.cumsum(active_delta), index=df.index)
            
            if btc_ref is not None and sym != "BTCUSDT":
                df = pd.merge_asof(df, btc_ref, on='datetime_utc', direction='backward')
            elif sym == "BTCUSDT":
                df['btc_close'] = df['close']
                btc_ema50 = df['close'].ewm(span=50).mean()
                df['btc_trend'] = ((df['close'] - btc_ema50) / btc_ema50).clip(-0.20, 0.20).fillna(0.0).astype(np.float32)
                df['zb20'] = zs(active_cvd, 96).astype(np.float32)
                df['zb4'] = zs(active_cvd, 4).astype(np.float32)
                
            df['atr'] = compute_true_atr(df, 14).astype(np.float32)
            df['cvd_divergence'] = (s_raw - f_raw).astype(np.float32)
            df['spot_cvd_delta'] = active_delta.astype(np.float32)
            df['future_cvd_delta'] = f_diff.astype(np.float32)
            df['spot_cvd_accel'] = active_delta.diff().fillna(0.0).astype(np.float32)
            
            df['zc4'] = zs(active_cvd, 4).astype(np.float32)
            df['zc10'] = zs(active_cvd, 10).astype(np.float32)
            df['zc20'] = zs(active_cvd, 96).astype(np.float32)
            df['zc_rel_btc'] = (df['zc20'] - df.get('zb20', 0.0)).astype(np.float32)
            df['zc4_rel_btc'] = (df['zc4'] - df.get('zb4', 0.0)).astype(np.float32)
            
            c = df['close']
            df['p8'] = ((c - c.ewm(span=8).mean()) / c.ewm(span=8).mean()).clip(-1.0, 1.0).astype(np.float32)
            df['p21'] = ((c - c.ewm(span=21).mean()) / c.ewm(span=21).mean()).clip(-1.0, 1.0).astype(np.float32)
            df['p50'] = ((c - c.ewm(span=50).mean()) / c.ewm(span=50).mean()).clip(-1.0, 1.0).astype(np.float32)
            df['p200'] = ((c - c.ewm(span=200).mean()) / c.ewm(span=200).mean()).clip(-1.0, 1.0).astype(np.float32)
            df['mc'] = ((c.ewm(span=8).mean() - c.ewm(span=21).mean()) / c).astype(np.float32)
            
            diff = c.diff()
            gain = diff.clip(lower=0).rolling(14, min_periods=1).mean()
            loss = (-diff.clip(upper=0)).rolling(14, min_periods=1).mean()
            rs = gain / (loss + 1e-8)
            df['rsi'] = (100.0 - (100.0 / (1.0 + rs))).astype(np.float32)
            
            v = df.get('volume_base', pd.Series(1.0, index=df.index)).fillna(1.0)
            df['vol_ratio'] = (v / (v.rolling(96, min_periods=1).mean() + 1e-8)).clip(0.0, 10.0).astype(np.float32)
            
            df['next_open'] = df['open'].shift(-1).astype(np.float64)
            df = df.dropna(subset=['next_open', 'atr']).reset_index(drop=True)
            
            highs = df['high'].to_numpy(dtype=np.float64)
            lows = df['low'].to_numpy(dtype=np.float64)
            closes = df['close'].to_numpy(dtype=np.float64)
            next_opens = df['next_open'].to_numpy(dtype=np.float64)
            atrs = df['atr'].to_numpy(dtype=np.float64)
            datetimes = df['datetime_utc'].to_numpy()
            
            feat_dict = {col: df[col].to_numpy(dtype=np.float32) for col in feature_cols if col in df.columns}
            
            mask_l, mask_s = s1_signal_predicate(df)
            sig = np.zeros(len(df), dtype=np.int8)
            sig[mask_l] = 1
            sig[mask_s] = -1
            
            res = gen_symbol_trades(highs, lows, closes, next_opens, atrs, sig)
            if res:
                for r in res:
                    idx, dr, ep, r_mult, lb, offset = r
                    row = {
                        'symbol': sym,
                        'entry_time': datetimes[idx],
                        'exit_time': datetimes[min(idx + offset, len(datetimes) - 1)],
                        'entry_price': next_opens[idx],
                        'exit_price': ep,
                        'atr': atrs[idx],
                        'direction': dr,
                        'r_multiple': r_mult,
                        'label': lb
                    }
                    for col in feature_cols:
                        if col in feat_dict:
                            row[col] = feat_dict[col][idx]
                    trades_list.append(row)
                    
            del df, highs, lows, closes, next_opens, atrs, datetimes, feat_dict
            gc.collect()
        except Exception as e: pass
            
    if not trades_list: return pd.DataFrame()
    df_out = pd.DataFrame(trades_list)
    df_out['entry_time'] = pd.to_datetime(df_out['entry_time'], utc=True)
    df_out['exit_time'] = pd.to_datetime(df_out['exit_time'], utc=True)
    return df_out.sort_values('entry_time').reset_index(drop=True)

if __name__ == "__main__":
    feature_cols = [
        'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
        'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
        'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'btc_trend'
    ]
    df = load_s1_trades(feature_cols)
    print(f"Loaded {len(df)} S1 trades.")
