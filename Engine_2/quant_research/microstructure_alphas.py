"""
Cryptocurrency Market Microstructure Alpha Features
Computes Order Flow Imbalance (OFI), VPIN Toxicity, Liquidation Cascades, and Liquidity Absorption metrics.
"""

import numpy as np
import pandas as pd


def compute_liquidation_alphas(
    df: pd.DataFrame,
    long_liq_col: str = "long_liq_usd",
    short_liq_col: str = "short_liq_usd",
    rolling_window_bars: int = 96  # 24 hours of 15m bars
) -> pd.DataFrame:
    """
    Computes rolling liquidation z-scores, imbalance ratios, and cascade flags.
    
    Args:
        df: DataFrame with liquidation USD columns
        long_liq_col: Name of long liquidations column
        short_liq_col: Name of short liquidations column
        rolling_window_bars: Lookback window for baseline z-score
        
    Returns:
        pd.DataFrame with engineered liquidation features
    """
    out = pd.DataFrame(index=df.index)
    
    long_liq = df[long_liq_col].fillna(0.0) if long_liq_col in df.columns else pd.Series(0.0, index=df.index)
    short_liq = df[short_liq_col].fillna(0.0) if short_liq_col in df.columns else pd.Series(0.0, index=df.index)
    total_liq = long_liq + short_liq
    
    # 1. Net Liquidation Imbalance Ratio [-1.0, 1.0]
    # Positive indicates short liquidation dominance (forced market buys)
    # Negative indicates long liquidation dominance (forced market sells)
    denom = total_liq + 1e-5
    out['liq_imbalance'] = (short_liq - long_liq) / denom
    
    # 2. 24h Rolling Liquidation Z-Score
    roll_mean = total_liq.rolling(rolling_window_bars, min_periods=12).mean()
    roll_std = total_liq.rolling(rolling_window_bars, min_periods=12).std().replace(0.0, 1.0)
    out['liq_zscore_24h'] = ((total_liq - roll_mean) / roll_std).clip(-5.0, 10.0).fillna(0.0)
    
    # 3. Individual Long/Short Z-Scores
    long_std = long_liq.rolling(rolling_window_bars, min_periods=12).std().replace(0.0, 1.0)
    short_std = short_liq.rolling(rolling_window_bars, min_periods=12).std().replace(0.0, 1.0)
    out['long_liq_zscore'] = ((long_liq - long_liq.rolling(rolling_window_bars, min_periods=12).mean()) / long_std).clip(0.0, 10.0).fillna(0.0)
    out['short_liq_zscore'] = ((short_liq - short_liq.rolling(rolling_window_bars, min_periods=12).mean()) / short_std).clip(0.0, 10.0).fillna(0.0)
    
    # 4. Cascade Exhaustion Flag (Extreme flush followed by volume absorption)
    out['is_long_cascade'] = (out['long_liq_zscore'] > 2.5).astype(np.int8)
    out['is_short_cascade'] = (out['short_liq_zscore'] > 2.5).astype(np.int8)
    
    return out


def compute_vpin_approximation(
    df: pd.DataFrame,
    buy_vol_col: str = "taker_buy_vol",
    sell_vol_col: str = "taker_sell_vol",
    total_vol_col: str = "volume_quote",
    bucket_bars: int = 16  # 4 hours of 15m bars
) -> pd.Series:
    """
    Computes rolling Volume-Synchronized Probability of Toxicity (VPIN) proxy from taker buy/sell volume.
    
    Args:
        df: DataFrame containing taker buy and sell volume
        buy_vol_col: Column name for taker buy volume
        sell_vol_col: Column name for taker sell volume
        total_vol_col: Column name for total quote volume
        bucket_bars: Number of bars per VPIN rolling bucket
        
    Returns:
        pd.Series: Rolling VPIN toxicity proxy [0.0, 1.0]
    """
    if buy_vol_col in df.columns and sell_vol_col in df.columns:
        buy_vol = df[buy_vol_col].fillna(0.0)
        sell_vol = df[sell_vol_col].fillna(0.0)
    elif total_vol_col in df.columns:
        # Approximate using close position relative to high-low range
        hl_range = (df['high'] - df['low']).replace(0.0, 1e-6)
        buy_ratio = ((df['close'] - df['low']) / hl_range).clip(0.0, 1.0)
        buy_vol = df[total_vol_col] * buy_ratio
        sell_vol = df[total_vol_col] * (1.0 - buy_ratio)
    else:
        return pd.Series(0.0, index=df.index, name="vpin_proxy")
        
    abs_imbalance = (buy_vol - sell_vol).abs()
    rolling_imbalance = abs_imbalance.rolling(bucket_bars, min_periods=4).sum()
    rolling_total_vol = (buy_vol + sell_vol).rolling(bucket_bars, min_periods=4).sum().replace(0.0, 1e-6)
    
    vpin = (rolling_imbalance / rolling_total_vol).clip(0.0, 1.0).fillna(0.0)
    vpin.name = "vpin_toxicity"
    return vpin


def compute_cvd_divergence(
    df: pd.DataFrame,
    cvd_col: str = "future_cvd_15m",
    price_col: str = "close",
    lookback_bars: int = 8
) -> pd.Series:
    """
    Detects divergence between Cumulative Volume Delta (CVD) orderflow and price displacement.
    Positive value: Bullish absorption (Price falling or flat while CVD rising).
    Negative value: Bearish absorption (Price rising or flat while CVD falling).
    """
    if cvd_col not in df.columns:
        return pd.Series(0.0, index=df.index, name="cvd_divergence")
        
    cvd = df[cvd_col]
    price = df[price_col]
    
    delta_cvd = (cvd - cvd.shift(lookback_bars)).fillna(0.0)
    norm_delta_cvd = delta_cvd / (cvd.abs().rolling(96, min_periods=12).mean() + 1e-6)
    
    ret_price = (price / price.shift(lookback_bars) - 1.0).fillna(0.0)
    norm_ret_price = ret_price / (ret_price.abs().rolling(96, min_periods=12).mean() + 1e-6)
    
    divergence = (norm_delta_cvd - norm_ret_price).clip(-5.0, 5.0)
    divergence.name = "cvd_absorption_divergence"
    return divergence
