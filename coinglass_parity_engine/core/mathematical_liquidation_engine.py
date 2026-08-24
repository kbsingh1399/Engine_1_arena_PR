"""
================================================================================
UPGRADED 5-FACTOR CONTINUOUS LIQUIDATION MATHEMATICAL ENGINE (MASTER v3)
================================================================================
High-Performance Mathematical Formulation for Historical Binance Liquidation:
  Factors:
    1. Current Adverse Wick Penetration (W_down_t / W_up_t)
    2. Lagged Prior Bar Margin Plunge (W_down_{t-1} / W_up_{t-1})
    3. Funding Rate Crowd Leverage Asymmetry Bias
    4. Non-Linear Exponential Cascade Multiplier for Flash Crashes
    5. Non-Linear Open Interest Net Flush Factor
    6. Taker CVD Flow Imbalance
================================================================================
"""

import math
import numpy as np
import pandas as pd
from typing import Tuple

class MathematicalLiquidationModel:
    def __init__(self):
        # Calibrated weights & physics parameters
        self.alpha_long = 245000.0
        self.alpha_short = 210000.0
        self.c_lag = 0.450
        self.p_wick = 1.450
        self.p_vol = 0.880
        self.k_cvd = 4.850
        self.k_oi = 2.150
        self.k_cascade = 0.850
        self.base_floor = 18500.0
        self.wick_threshold_pct = 0.75

    def compute_single_bar(self, open_px: float, high_px: float, low_px: float, close_px: float,
                           open_prev: float, high_prev: float, low_prev: float, close_prev: float,
                           fut_vol_usd: float, delta_cvd_btc: float, delta_oi_btc: float,
                           ls_ratio: float, funding_rate_pct: float = 0.01) -> Tuple[float, float]:
        """
        Calculates mathematical estimate of Long and Short Liquidations (USD) for a single bar.
        Returns: (long_liq_usd, short_liq_usd) with signed polarities (-Long, +Short).
        """
        if open_px <= 0:
            return 0.0, 0.0

        # 1. Adverse wicks for current bar (%)
        w_down_curr = max(0.0, (open_px - low_px) / open_px * 100.0)
        w_up_curr   = max(0.0, (high_px - open_px) / open_px * 100.0)

        # 2. Adverse wicks for lagged prior bar (%)
        w_down_prev = max(0.0, (open_prev - low_prev) / open_prev * 100.0) if open_prev > 0 else 0.0
        w_up_prev   = max(0.0, (high_prev - open_prev) / open_prev * 100.0) if open_prev > 0 else 0.0

        # 3. Volume Scaling Term
        vol_scale = (max(fut_vol_usd, 1.0e5) / 100.0e6) ** self.p_vol

        # 4. Funding Rate Leverage Asymmetry Multiplier
        fr_dec = funding_rate_pct / 100.0
        funding_bias_long  = 1.0 + max(0.0, fr_dec * 2500.0)
        funding_bias_short = 1.0 + max(0.0, -fr_dec * 2500.0)

        # 5. Non-Linear Exponential Cascade Multipliers
        cascade_long  = math.exp(self.k_cascade * max(0.0, w_down_curr - self.wick_threshold_pct))
        cascade_short = math.exp(self.k_cascade * max(0.0, w_up_curr - self.wick_threshold_pct))

        # 6. Non-Linear Open Interest Flush ($M drop)
        oi_drop_m = max(0.0, -delta_oi_btc * close_px / 1.0e6)
        oi_term = self.k_oi * ((oi_drop_m ** 1.30) if oi_drop_m > 0 else 0.0) * 1000.0

        # 7. Long Liquidation Formula
        wick_long = (w_down_curr ** self.p_wick) + self.c_lag * (w_down_prev ** self.p_wick)
        cvd_sell_term = self.k_cvd * max(0.0, -delta_cvd_btc) * (close_px / 1000.0)
        
        long_base = (self.alpha_long * wick_long * vol_scale * ls_ratio * funding_bias_long * cascade_long)
        long_liq = long_base + cvd_sell_term + oi_term + self.base_floor
        
        # Zero floor suppression for calm non-volatile bars
        if w_down_curr < 0.05 and w_down_prev < 0.10 and delta_cvd_btc > 50:
            long_liq = max(0.0, long_liq * 0.15)

        # 8. Short Liquidation Formula
        wick_short = (w_up_curr ** self.p_wick) + self.c_lag * (w_up_prev ** self.p_wick)
        cvd_buy_term = self.k_cvd * max(0.0, delta_cvd_btc) * (close_px / 1000.0)
        
        short_base = (self.alpha_short * wick_short * vol_scale * (1.0 / max(ls_ratio, 0.5)) * funding_bias_short * cascade_short)
        short_liq = short_base + cvd_buy_term + oi_term + self.base_floor
        
        if w_up_curr < 0.08 and w_up_prev < 0.10 and delta_cvd_btc < -50:
            short_liq = 0.0

        return -round(long_liq, 2), round(short_liq, 2)

    def compute_vectorized(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        High-speed vectorized computation across millions of bars using NumPy.
        Expects df with columns: open, high, low, close, volume_quote, future_cvd_15m, open_interest_k, ls_ratio_global, funding_rate_pct.
        """
        n = len(df)
        if n == 0:
            return np.array([]), np.array([])

        opens = df['open'].values.astype(float)
        highs = df['high'].values.astype(float)
        lows  = df['low'].values.astype(float)
        closes = df['close'].values.astype(float)
        vols_usd = df['volume_quote'].values.astype(float)
        cvds = df['future_cvd_15m'].values.astype(float)
        
        ois = df['open_interest_k'].values.astype(float) * 1000.0 if 'open_interest_k' in df else np.zeros(n)
        ls_ratios = df['ls_ratio_global'].values.astype(float) if 'ls_ratio_global' in df else np.ones(n)
        frs = df['funding_rate_pct'].values.astype(float) if 'funding_rate_pct' in df else np.full(n, 0.01)

        # Lagged prices
        opens_prev = np.roll(opens, 1)
        opens_prev[0] = opens[0]
        lows_prev = np.roll(lows, 1)
        lows_prev[0] = lows[0]
        highs_prev = np.roll(highs, 1)
        highs_prev[0] = highs[0]

        # OI delta
        oi_delta = np.zeros(n)
        oi_delta[1:] = np.diff(ois)

        # Adverse wicks
        w_down_curr = np.maximum(0.0, (opens - lows) / np.maximum(opens, 1.0) * 100.0)
        w_up_curr   = np.maximum(0.0, (highs - opens) / np.maximum(opens, 1.0) * 100.0)
        w_down_prev = np.maximum(0.0, (opens_prev - lows_prev) / np.maximum(opens_prev, 1.0) * 100.0)
        w_up_prev   = np.maximum(0.0, (highs_prev - opens_prev) / np.maximum(opens_prev, 1.0) * 100.0)

        # Volume scale
        vol_scale = (np.maximum(vols_usd, 1.0e5) / 100.0e6) ** self.p_vol

        # Funding rate bias
        fr_dec = frs / 100.0
        funding_bias_long  = 1.0 + np.maximum(0.0, fr_dec * 2500.0)
        funding_bias_short = 1.0 + np.maximum(0.0, -fr_dec * 2500.0)

        # Cascades
        cascade_long  = np.exp(self.k_cascade * np.maximum(0.0, w_down_curr - self.wick_threshold_pct))
        cascade_short = np.exp(self.k_cascade * np.maximum(0.0, w_up_curr - self.wick_threshold_pct))

        # OI Flush
        oi_drop_m = np.maximum(0.0, -oi_delta * closes / 1.0e6)
        oi_term = self.k_oi * (oi_drop_m ** 1.30) * 1000.0

        # Long Liq
        wick_long = (w_down_curr ** self.p_wick) + self.c_lag * (w_down_prev ** self.p_wick)
        cvd_sell_term = self.k_cvd * np.maximum(0.0, -cvds) * (closes / 1000.0)
        long_liq = (self.alpha_long * wick_long * vol_scale * ls_ratios * funding_bias_long * cascade_long) + cvd_sell_term + oi_term + self.base_floor

        # Calm bar suppression
        calm_mask_long = (w_down_curr < 0.05) & (w_down_prev < 0.10) & (cvds > 50)
        long_liq[calm_mask_long] = np.maximum(0.0, long_liq[calm_mask_long] * 0.15)

        # Short Liq
        wick_short = (w_up_curr ** self.p_wick) + self.c_lag * (w_up_prev ** self.p_wick)
        cvd_buy_term = self.k_cvd * np.maximum(0.0, cvds) * (closes / 1000.0)
        short_liq = (self.alpha_short * wick_short * vol_scale * (1.0 / np.maximum(ls_ratios, 0.5)) * funding_bias_short * cascade_short) + cvd_buy_term + oi_term + self.base_floor

        calm_mask_short = (w_up_curr < 0.08) & (w_up_prev < 0.10) & (cvds < -50)
        short_liq[calm_mask_short] = 0.0

        return -np.round(long_liq, 2), np.round(short_liq, 2)
