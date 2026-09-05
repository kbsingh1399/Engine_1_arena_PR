"""
trend_orderflow_features.py - Causal Feature Engineering for Trend Following with Order Flow.

Extracts:
1. Trend & Moving Average Structure (EMA 8/21/50/200 spreads, alignment score, pullback depth)
2. Order Flow & Footprint Delta (normalized delta, delta flip, stacked buy/sell imbalances, POC)
3. CVD Momentum & Cross-Venue Divergence (Futures CVD slope, Spot CVD slope, zc_div)
4. Open Interest & Funding Mechanics (OI acceleration, funding z-score, liquidation z-scores)
5. Candle Rejection & Auction Theory (lower/upper wick ratios, close position, volume surge)
6. Causal Triple-Barrier Labels for Trend Continuation (+2.5R target vs -1.0R stop)
"""

import numpy as np
import pandas as pd
from typing import Tuple, List

FEATURE_COLUMNS = [
    "ema8_ema21_spread",
    "ema21_ema50_spread",
    "ema50_ema200_spread",
    "trend_alignment_bull",
    "trend_alignment_bear",
    "dist_to_ema21",
    "dist_to_ema50",
    "fp_delta_ratio",
    "fp_delta_change_3",
    "is_delta_flip",
    "net_stacked_imb",
    "stacked_buy_imb_active",
    "stacked_sell_imb_active",
    "taker_vol_ratio",
    "poc_pos",
    "future_cvd_slope_3",
    "spot_cvd_slope_3",
    "zc_div",
    "oi_change_pct",
    "oi_change_4bar",
    "funding_z",
    "short_liq_zs",
    "long_liq_zs",
    "lower_wick_ratio",
    "upper_wick_ratio",
    "close_pos",
    "volume_to_sma",
    "range_to_atr",
    "rsi_14",
    "whale_index"
]

def extract_trend_orderflow_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute 100% causal features for trend-following order flow strategies.
    Ensures zero lookahead: all rolling indicators look only backward.
    """
    o = df["open"].to_numpy(dtype=np.float64)
    h = df["high"].to_numpy(dtype=np.float64)
    l = df["low"].to_numpy(dtype=np.float64)
    c = df["close"].to_numpy(dtype=np.float64)
    vol_base = np.maximum(df["volume_base"].to_numpy(dtype=np.float64), 1e-12)
    vol_sma = np.maximum(df["volume_sma9"].to_numpy(dtype=np.float64), 1e-12)
    atr = np.maximum(df["atr_14"].to_numpy(dtype=np.float64), 1e-12)
    rng = np.maximum(h - l, 1e-12)

    feats = pd.DataFrame(index=df.index)
    feats["open_time_ms"] = df["open_time_ms"]
    feats["symbol"] = df["symbol"] if "symbol" in df.columns else "UNKNOWN"
    feats["close"] = c
    feats["high"] = h
    feats["low"] = l
    feats["atr"] = atr

    # 1. Trend Structure & EMA Spreads
    ema8 = df["ema_8"].to_numpy(dtype=np.float64)
    ema21 = df["ema_21"].to_numpy(dtype=np.float64)
    ema50 = df["ema_50"].to_numpy(dtype=np.float64)
    ema200 = df["ema_200"].to_numpy(dtype=np.float64)

    feats["ema8_ema21_spread"] = (ema8 - ema21) / c * 100.0
    feats["ema21_ema50_spread"] = (ema21 - ema50) / c * 100.0
    feats["ema50_ema200_spread"] = (ema50 - ema200) / c * 100.0

    feats["trend_alignment_bull"] = ((ema8 > ema21) & (ema21 > ema50) & (ema50 > ema200)).astype(float)
    feats["trend_alignment_bear"] = ((ema8 < ema21) & (ema21 < ema50) & (ema50 < ema200)).astype(float)

    feats["dist_to_ema21"] = (c - ema21) / atr
    feats["dist_to_ema50"] = (c - ema50) / atr

    # 2. Footprint Delta & Stacked Imbalances
    fp_delta = df["fp_delta"].fillna(0.0).to_numpy(dtype=np.float64)
    feats["fp_delta_ratio"] = fp_delta / vol_base
    
    prev_delta = np.roll(fp_delta, 1)
    prev_delta[0] = 0.0
    feats["is_delta_flip"] = ((fp_delta > 0) & (prev_delta <= 0)).astype(float)
    
    delta_3 = np.roll(fp_delta, 3)
    delta_3[:3] = 0.0
    feats["fp_delta_change_3"] = (fp_delta - delta_3) / vol_base

    buy_imb = df["fp_stacked_buy_imb"].fillna(0.0).to_numpy(dtype=np.float64)
    sell_imb = df["fp_stacked_sell_imb"].fillna(0.0).to_numpy(dtype=np.float64)
    feats["net_stacked_imb"] = buy_imb - sell_imb
    feats["stacked_buy_imb_active"] = (buy_imb > 0).astype(float)
    feats["stacked_sell_imb_active"] = (sell_imb > 0).astype(float)

    feats["taker_vol_ratio"] = df["taker_volume_ratio"].fillna(1.0).to_numpy(dtype=np.float64)

    fp_poc = df["fp_poc"].fillna(df["close"]).to_numpy(dtype=np.float64)
    feats["poc_pos"] = np.clip((fp_poc - l) / rng, 0.0, 1.0)

    # 3. CVD Slopes & Cross-Venue Divergence
    f_cvd = df["future_cvd_15m"].fillna(0.0).to_numpy(dtype=np.float64)
    s_cvd = df["spot_cvd_15m"].fillna(0.0).to_numpy(dtype=np.float64)
    
    f_cvd_3 = np.roll(f_cvd, 3)
    f_cvd_3[:3] = 0.0
    feats["future_cvd_slope_3"] = (f_cvd - f_cvd_3) / vol_base

    s_cvd_3 = np.roll(s_cvd, 3)
    s_cvd_3[:3] = 0.0
    feats["spot_cvd_slope_3"] = (s_cvd - s_cvd_3) / vol_base

    # Z-Score Divergence (Spot vs Futures)
    s_s = pd.Series(s_cvd)
    f_s = pd.Series(f_cvd)
    s_z = (s_s - s_s.rolling(20, min_periods=20).mean()) / s_s.rolling(20, min_periods=20).std(ddof=0).replace(0.0, np.nan)
    f_z = (f_s - f_s.rolling(20, min_periods=20).mean()) / f_s.rolling(20, min_periods=20).std(ddof=0).replace(0.0, np.nan)
    feats["zc_div"] = (0.5 * (s_z - f_z)).fillna(0.0).to_numpy()

    # 4. Open Interest & Funding Mechanics
    feats["oi_change_pct"] = df["oi_change_pct"].fillna(0.0).to_numpy(dtype=np.float64)
    oi_usd = pd.Series(df["open_interest_usd"].to_numpy(dtype=np.float64))
    feats["oi_change_4bar"] = oi_usd.pct_change(4).fillna(0.0).to_numpy() * 100.0

    funding = pd.Series(df["funding_rate_pct"].to_numpy(dtype=np.float64))
    funding_mean = funding.rolling(288, min_periods=20).mean()
    funding_std = funding.rolling(288, min_periods=20).std(ddof=0).replace(0.0, np.nan)
    feats["funding_z"] = ((funding - funding_mean) / funding_std).fillna(0.0).to_numpy()

    # Liquidation Z-scores
    short_liq = pd.Series(df["short_liq_usd"].to_numpy(dtype=np.float64))
    s_liq_mean = short_liq.rolling(20, min_periods=20).mean()
    s_liq_std = short_liq.rolling(20, min_periods=20).std(ddof=0).replace(0.0, np.nan)
    feats["short_liq_zs"] = ((short_liq - s_liq_mean) / s_liq_std).fillna(0.0).to_numpy()

    long_liq = pd.Series(df["long_liq_usd"].to_numpy(dtype=np.float64))
    l_liq_mean = long_liq.rolling(20, min_periods=20).mean()
    l_liq_std = long_liq.rolling(20, min_periods=20).std(ddof=0).replace(0.0, np.nan)
    feats["long_liq_zs"] = ((long_liq - l_liq_mean) / l_liq_std).fillna(0.0).to_numpy()

    # 5. Candle Rejection & Microstructure
    feats["lower_wick_ratio"] = (np.minimum(o, c) - l) / rng
    feats["upper_wick_ratio"] = (h - np.maximum(o, c)) / rng
    feats["close_pos"] = (c - l) / rng
    feats["volume_to_sma"] = vol_base / vol_sma
    feats["range_to_atr"] = rng / atr

    feats["rsi_14"] = df["rsi_14"].fillna(50.0).to_numpy(dtype=np.float64)
    feats["whale_index"] = df["whale_index"].fillna(1.0).to_numpy(dtype=np.float64)

    # Sanitize all feature columns against inf, -inf, and extreme floating-point explosions
    for col in FEATURE_COLUMNS:
        if col in feats.columns:
            s = feats[col].to_numpy(dtype=np.float64)
            s = np.nan_to_num(s, nan=0.0, posinf=100.0, neginf=-100.0)
            feats[col] = np.clip(s, -100.0, 100.0)

    return feats

def generate_trend_triple_barrier_labels(
    feats: pd.DataFrame,
    r_target: float = 2.5,
    r_stop: float = 1.0,
    atr_mult: float = 1.5,
    max_horizon_bars: int = 32
) -> pd.Series:
    """
    Compute causal triple barrier labels for trend continuation:
    - Target: entry + r_target * (atr_mult * ATR)
    - Stop Loss: entry - r_stop * (atr_mult * ATR)
    - Horizon: max_horizon_bars (e.g. 32 bars = 8 hours)
    - Y = 1 if Target is reached before Stop Loss; 0 otherwise.
    """
    c = feats["close"].to_numpy()
    h = feats["high"].to_numpy()
    l = feats["low"].to_numpy()
    atr = feats["atr"].to_numpy()
    T = len(feats)

    labels = np.zeros(T, dtype=int)
    risk_unit = atr_mult * atr
    profit_dist = r_target * risk_unit
    stop_dist = r_stop * risk_unit

    for t in range(T - max_horizon_bars):
        entry_px = c[t]
        stop_px = entry_px - stop_dist[t]
        take_px = entry_px + profit_dist[t]

        hit_take = False
        hit_stop = False

        for k in range(t + 1, min(t + max_horizon_bars + 1, T)):
            if l[k] <= stop_px:
                hit_stop = True
                break
            if h[k] >= take_px:
                hit_take = True
                break

        if hit_take and not hit_stop:
            labels[t] = 1

    return pd.Series(labels, index=feats.index, name="target")
