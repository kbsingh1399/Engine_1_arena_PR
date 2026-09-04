"""
================================================================================
CANONICAL TECHNICAL & MICROSTRUCTURE INDICATORS ENGINE
================================================================================
High-performance continuous vector calculation for:
  - Exponential Moving Averages: EMA 8, 21, 50, 200, 800
  - Wilder RSI 14 (RMA smoothed)
  - Wilder Average True Range: ATR 14, 100 (RMA smoothed)
  - Volume SMA 9 (USD Quote Volume & Base BTC)
  - Footprint POC & Delta
  - Session Cumulative Volume Deltas (Futures & Spot)
  - Span-Normalized Order Book Depth Estimates (+-1%)
================================================================================
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple

def get_merge_level(symbol: str) -> float:
    """Returns canonical tick merge level based on asset price scale."""
    s = symbol.upper()
    if s.startswith("BTC"):
        return 25.0
    elif s.startswith("ETH"):
        return 1.0
    elif any(s.startswith(x) for x in ["SOL", "BNB", "BCH", "AVAX", "LTC", "APT", "LINK"]):
        return 0.1
    elif any(s.startswith(x) for x in ["DOT", "NEAR", "SUI", "OP", "ARB"]):
        return 0.01
    else:
        return 0.0001

def compute_ema_series(prices: np.ndarray, period: int) -> np.ndarray:
    """
    Computes standard Exponential Moving Average seeded from the first available bar.
    alpha = 2.0 / (period + 1.0)
    """
    n = len(prices)
    if n == 0:
        return np.array([])
    
    ema = np.empty(n, dtype=np.float64)
    k = 2.0 / (period + 1.0)
    
    # Initialize first valid value
    ema[0] = prices[0]
    for i in range(1, n):
        ema[i] = prices[i] * k + ema[i - 1] * (1.0 - k)
        
    return ema

def compute_wilder_rma_series(values: np.ndarray, period: int) -> np.ndarray:
    """
    Computes Wilder's Running Moving Average (RMA):
    RMA(x, p): y_t = alpha * x_t + (1 - alpha) * y_{t-1}, where alpha = 1 / p.
    """
    n = len(values)
    if n == 0:
        return np.array([])
    
    rma = np.empty(n, dtype=np.float64)
    alpha = 1.0 / period
    
    # Causal initialization: bar 0 is values[0]
    # For bars 1..period-1, use causal expanding mean (mean of values[:i+1])
    # This ensures no future bars leak into early bars
    rma[0] = values[0]
    for i in range(1, min(period, n)):
        rma[i] = (rma[i - 1] * i + values[i]) / (i + 1.0)
        
    for i in range(period, n):
        rma[i] = values[i] * alpha + rma[i - 1] * (1.0 - alpha)
        
    return rma

def compute_wilder_rsi_series(closes: np.ndarray, period: int = 14) -> np.ndarray:
    """
    Computes Wilder 14-period Relative Strength Index matching TradingView & CoinGlass.
    Strictly causal initialization with zero future lookahead.
    """
    n = len(closes)
    if n == 0:
        return np.array([])
    if n == 1:
        return np.full(1, 50.0)
    
    deltas = np.diff(closes)
    gains = np.maximum(deltas, 0.0)
    losses = np.maximum(-deltas, 0.0)
    
    rsi = np.full(n, 50.0, dtype=np.float64)
    if len(deltas) < period:
        return rsi
    
    avg_gain = np.empty(n, dtype=np.float64)
    avg_loss = np.empty(n, dtype=np.float64)
    
    # Causal expanding average for early bars
    avg_gain[0] = gains[0] if len(gains) > 0 else 0.0
    avg_loss[0] = losses[0] if len(losses) > 0 else 0.0
    for i in range(1, min(period, len(deltas))):
        avg_gain[i] = (avg_gain[i - 1] * i + gains[i]) / (i + 1.0)
        avg_loss[i] = (avg_loss[i - 1] * i + losses[i]) / (i + 1.0)
        
    for i in range(period, len(deltas)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i]) / period
        
    for i in range(len(deltas)):
        if avg_loss[i] == 0:
            rsi[i + 1] = 100.0 if avg_gain[i] > 0 else 50.0
        else:
            rs = avg_gain[i] / avg_loss[i]
            rsi[i + 1] = 100.0 - (100.0 / (1.0 + rs))
            
    rsi[0] = 50.0
    return np.round(rsi, 2)

def compute_wilder_atr_series(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    """
    Computes Wilder Average True Range (ATR) matching TradingView & CoinGlass.
    TR = max(High - Low, abs(High - PrevClose), abs(Low - PrevClose))
    """
    n = len(closes)
    if n == 0:
        return np.array([])
    if n == 1:
        return np.full(1, highs[0] - lows[0])
    
    prev_closes = np.roll(closes, 1)
    prev_closes[0] = closes[0]
    
    tr0 = highs - lows
    tr1 = np.abs(highs - prev_closes)
    tr2 = np.abs(lows - prev_closes)
    tr = np.maximum(tr0, np.maximum(tr1, tr2))
    
    atr = compute_wilder_rma_series(tr, period)
    return np.round(atr, 2)

def compute_volume_sma9_series(volumes: np.ndarray) -> np.ndarray:
    """
    Computes 9-period Simple Moving Average of Volume.
    """
    n = len(volumes)
    if n == 0:
        return np.array([])
    
    sma = np.empty(n, dtype=np.float64)
    window = 9
    for i in range(n):
        start = max(0, i - window + 1)
        sma[i] = np.mean(volumes[start : i + 1])
    return np.round(sma, 2)

def compute_session_cvd(timestamps_ms: np.ndarray, deltas: np.ndarray) -> np.ndarray:
    """
    Computes running Cumulative Volume Delta (CVD) resetting at 00:00 UTC daily session boundary.
    """
    n = len(timestamps_ms)
    session_cvd = np.empty(n, dtype=np.float64)
    
    current_day = -1
    running_sum = 0.0
    
    for i in range(n):
        day_num = timestamps_ms[i] // (86400 * 1000)
        if day_num != current_day:
            current_day = day_num
            running_sum = 0.0
        running_sum += deltas[i]
        session_cvd[i] = running_sum
        
    return np.round(session_cvd, 2)

def estimate_depth_from_volatility(closes: np.ndarray, atrs: np.ndarray, base_vols: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Estimates +-1% resting order book depth proxy in USD and Coin from ATR volatility and base volume.
    Note: Both bid and ask depths are returned as positive non-negative liquidity magnitudes.
    """
    # Liquidity elasticity proxy: higher ATR slightly widens the book, reducing immediate resting depth
    vol_scaling = np.clip(1.0 / (np.maximum(atrs / np.maximum(closes, 1e-4), 0.001) * 100.0), 0.5, 2.0)
    bid_depth_coin = np.round(base_vols * 0.025 * vol_scaling, 4)
    ask_depth_coin = np.round(base_vols * 0.025 * vol_scaling, 4) # Positive magnitude
    bid_depth_usd = np.round(bid_depth_coin * closes, 2)
    ask_depth_usd = np.round(ask_depth_coin * closes, 2)
    return bid_depth_usd, ask_depth_usd, bid_depth_coin, ask_depth_coin

def compute_session_value_area(
    timestamps_ms: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    volumes: np.ndarray,
    bucket_size: float = 25.0,
    volume_pct: float = 0.70
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Computes Developing Daily Session Value Area High (VAH) and Low (VAL)
    starting at 00:00:00 UTC daily session boundary, along with Prior Day finalized VAH/VAL.
    """
    from collections import defaultdict
    n = len(timestamps_ms)
    session_vah = np.zeros(n, dtype=np.float64)
    session_val = np.zeros(n, dtype=np.float64)
    prev_day_vah = np.zeros(n, dtype=np.float64)
    prev_day_val = np.zeros(n, dtype=np.float64)
    
    current_day = -1
    profile = defaultdict(float)
    total_vol = 0.0
    last_locked_vah = np.nan
    last_locked_val = np.nan
    
    for i in range(n):
        day = timestamps_ms[i] // (86400 * 1000)
        if day != current_day:
            if current_day != -1 and total_vol > 0:
                last_locked_vah = session_vah[i - 1]
                last_locked_val = session_val[i - 1]
            current_day = day
            profile.clear()
            total_vol = 0.0
            
        low_b = int(round(lows[i] / bucket_size))
        high_b = int(round(highs[i] / bucket_size))
        num_bins = max(1, high_b - low_b + 1)
        vol_per_bin = volumes[i] / num_bins
        for b in range(low_b, high_b + 1):
            profile[b] += vol_per_bin
        total_vol += volumes[i]
        
        target = total_vol * volume_pct
        sorted_bins = sorted(profile.keys())
        poc_bin = max(profile, key=profile.get)
        poc_idx = sorted_bins.index(poc_bin)
        
        cur_v = profile[poc_bin]
        up_idx = poc_idx + 1
        down_idx = poc_idx - 1
        
        while cur_v < target and (up_idx < len(sorted_bins) or down_idx >= 0):
            up_v = profile[sorted_bins[up_idx]] if up_idx < len(sorted_bins) else -1.0
            down_v = profile[sorted_bins[down_idx]] if down_idx >= 0 else -1.0
            if up_v >= down_v and up_v >= 0:
                cur_v += up_v
                up_idx += 1
            elif down_v >= 0:
                cur_v += down_v
                down_idx -= 1
            else:
                break
                
        val_bin = sorted_bins[down_idx + 1]
        vah_bin = sorted_bins[up_idx - 1]
        
        session_vah[i] = round(vah_bin * bucket_size, 1)
        session_val[i] = round(val_bin * bucket_size, 1)
        prev_day_vah[i] = last_locked_vah if not np.isnan(last_locked_vah) else session_vah[i]
        prev_day_val[i] = last_locked_val if not np.isnan(last_locked_val) else session_val[i]
        
    return session_vah, session_val, prev_day_vah, prev_day_val
