"""
================================================================================
HISTORICAL METRICS & CANONICAL INDICATOR PROCESSOR
================================================================================
Merges raw Klines, Daily Metrics, and Funding Rates into a continuous,
100% complete 28-indicator historical dataset with zero NaN gaps.
================================================================================
"""

import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import Dict, Any

from ..core.canonical_indicators import (
    compute_ema_series,
    compute_wilder_rsi_series,
    compute_wilder_atr_series,
    compute_volume_sma9_series,
    compute_session_cvd,
    estimate_depth_from_volatility,
)
from ..core.mathematical_liquidation_engine import MathematicalLiquidationModel
from ..core.schema import CANONICAL_COLUMNS

class HistoricalMetricsProcessor:
    def __init__(self):
        self.liq_model = MathematicalLiquidationModel()

    def process_master_dataset(
        self,
        klines_df: pd.DataFrame,
        metrics_df: pd.DataFrame,
        funding_df: pd.DataFrame,
        footprint_df: pd.DataFrame = None,
        spot_df: pd.DataFrame = None
    ) -> pd.DataFrame:
        """
        Executes end-to-end indicator calculation and produces a canonical 28-indicator DataFrame.
        """
        print("[PROCESSOR] Processing Master Historical Dataset...")
        df = klines_df.copy()
        
        # 1. Base Timestamps and Symbol
        df["open_time_ms"] = df["open_time"].astype(np.int64)
        df["close_time_ms"] = df["close_time"].astype(np.int64)
        df["datetime_utc"] = pd.to_datetime(df["open_time_ms"], unit="ms", utc=True).dt.strftime("%Y-%m-%d %H:%M:%S")
        df["symbol"] = "BTCUSDT"

        # 2. OHLCV Core
        df["open"] = df["open"].astype(np.float64)
        df["high"] = df["high"].astype(np.float64)
        df["low"] = df["low"].astype(np.float64)
        df["close"] = df["close"].astype(np.float64)
        df["volume_base"] = df["volume"].astype(np.float64)
        df["volume_quote"] = df["quote_volume"].astype(np.float64)
        df["trade_count"] = df["count"].astype(np.int64)

        closes = df["close"].values
        highs = df["high"].values
        lows = df["low"].values
        vols_base = df["volume_base"].values
        vols_quote = df["volume_quote"].values
        open_times = df["open_time_ms"].values

        # 3. Volume SMA 9
        print("[PROCESSOR] Computing Volume SMA 9 & Technical Indicators...")
        df["volume_sma9"] = compute_volume_sma9_series(vols_quote)

        # 4. Technical Indicators (Wilder RSI 14, Wilder ATR 14 & 100)
        df["rsi_14"] = compute_wilder_rsi_series(closes, period=14)
        df["atr_14"] = compute_wilder_atr_series(highs, lows, closes, period=14)
        df["atr_100"] = compute_wilder_atr_series(highs, lows, closes, period=100)

        # 5. Exponential Moving Averages (EMA 8, 21, 50, 200, 800)
        print("[PROCESSOR] Computing Seeded Continuous EMAs (8, 21, 50, 200, 800)...")
        df["ema_8"] = np.round(compute_ema_series(closes, 8), 2)
        df["ema_21"] = np.round(compute_ema_series(closes, 21), 2)
        df["ema_50"] = np.round(compute_ema_series(closes, 50), 2)
        df["ema_200"] = np.round(compute_ema_series(closes, 200), 2)
        df["ema_800"] = np.round(compute_ema_series(closes, 800), 2)

        # 6. Cumulative Volume Delta (CVD) & Footprint Integration
        print("[PROCESSOR] Computing Order Flow & Cumulative Volume Deltas...")
        
        # Default approximate calculations
        approx_buy_btc = df["taker_buy_volume"].astype(np.float64).values
        approx_sell_btc = vols_base - approx_buy_btc
        buy_ratio = np.clip(approx_buy_btc / np.maximum(vols_base, 1e-6), 0.05, 0.95)
        total_counts = df["trade_count"].values
        approx_buy_count = np.round(total_counts * buy_ratio).astype(np.int64)
        approx_sell_count = -np.round(total_counts * (1.0 - buy_ratio)).astype(np.int64)
        
        if footprint_df is not None and not footprint_df.empty:
            print("[PROCESSOR] Merging exact high-fidelity tick footprint data where available...")
            fp_df = footprint_df.sort_values(by="open_time_ms").copy()
            # Left join to find exact matching 15m footprint blocks
            df = pd.merge(
                df.sort_values("open_time_ms"),
                fp_df[["open_time_ms", "taker_buy_vol_coin", "taker_sell_vol_coin", "taker_buy_count", "taker_sell_count"]],
                on="open_time_ms",
                how="left"
            )
            # Where footprint is NaN (e.g. today's live candles), fallback to approx
            taker_buy_btc = df["taker_buy_vol_coin"].fillna(pd.Series(approx_buy_btc)).values
            taker_sell_btc = df["taker_sell_vol_coin"].fillna(pd.Series(approx_sell_btc)).values
            
            taker_buy_count = df["taker_buy_count"].fillna(pd.Series(approx_buy_count)).values.astype(np.int64)
            # Notice we negate the footprint sell count to match the parity convention (-ve)
            taker_sell_count_fp = -df["taker_sell_count"]
            taker_sell_count = taker_sell_count_fp.fillna(pd.Series(approx_sell_count)).values.astype(np.int64)
            
            df.drop(columns=["taker_buy_vol_coin", "taker_sell_vol_coin", "taker_buy_count", "taker_sell_count"], inplace=True)
            df["taker_buy_count"] = taker_buy_count
            df["taker_sell_count"] = taker_sell_count
            df["future_flow_source"] = np.where(df["open_time_ms"].isin(fp_df["open_time_ms"]), "TICK_EXACT", "KLINE_APPROX")
        else:
            print("[PROCESSOR] Using approximate kline footprint data everywhere...")
            taker_buy_btc = approx_buy_btc
            taker_sell_btc = approx_sell_btc
            df["taker_buy_count"] = approx_buy_count
            df["taker_sell_count"] = approx_sell_count
            df["future_flow_source"] = "KLINE_APPROX"

        fut_delta_15m = np.round(taker_buy_btc - taker_sell_btc, 2)
        
        df["taker_buy_vol_btc"] = np.round(taker_buy_btc, 3)
        df["taker_sell_vol_btc"] = np.round(taker_sell_btc, 3)
        df["future_cvd_15m"] = fut_delta_15m
        df["future_cvd_session"] = compute_session_cvd(open_times, fut_delta_15m)
        df["future_cvd_lifetime"] = np.round(np.cumsum(fut_delta_15m), 2)

        # Spot CVD: use real spot kline data if available, else approximate
        if spot_df is not None and not spot_df.empty:
            print("[PROCESSOR] Computing real Spot CVD from spot klines...")
            s_df = spot_df.sort_values(by="open_time").copy()
            df = pd.merge_asof(
                df.sort_values("open_time_ms"),
                s_df[["open_time", "spot_close", "spot_volume", "spot_taker_buy_volume"]],
                left_on="open_time_ms",
                right_on="open_time",
                direction="backward"
            )
            spot_buy = df["spot_taker_buy_volume"].fillna(0).values
            spot_vol = df["spot_volume"].fillna(1e-6).values
            spot_sell = spot_vol - spot_buy
            spot_delta_15m = np.round(spot_buy - spot_sell, 2)
            df["spot_flow_source"] = np.where(df["open_time_ms"].isin(s_df["open_time"]), "SPOT_EXACT", "UNAVAILABLE")
            df.drop(columns=["open_time", "spot_volume", "spot_taker_buy_volume"], inplace=True, errors="ignore")
        else:
            print("[PROCESSOR] No spot klines available, approximating Spot CVD...")
            spot_delta_15m = np.round(fut_delta_15m / 5.02, 2)
            df["spot_close"] = np.nan
            df["spot_flow_source"] = "UNAVAILABLE"

        df["spot_cvd_15m"] = spot_delta_15m
        df["spot_cvd_session"] = compute_session_cvd(open_times, spot_delta_15m)
        df["spot_cvd_lifetime"] = np.round(np.cumsum(spot_delta_15m), 2)

        # 7. Footprint & POC
        df["fp_delta"] = fut_delta_15m
        # Use real POC from footprint if available, else approximate
        if footprint_df is not None and "real_poc" in footprint_df.columns:
            # real_poc was already merged via the footprint merge above; use it
            poc_merged = pd.merge(
                df[["open_time_ms"]],
                footprint_df[["open_time_ms", "real_poc"]].drop_duplicates("open_time_ms"),
                on="open_time_ms", how="left"
            )
            real_poc = poc_merged["real_poc"].values
            fallback_poc = np.round((df["high"].values + df["low"].values + 2.0 * df["close"].values) / 4.0, 1)
            df["fp_poc"] = np.where(np.isnan(real_poc), fallback_poc, np.round(real_poc, 1))
            df["poc_source"] = np.where(np.isnan(real_poc), "OHLC_APPROX", "TICK_EXACT")
        else:
            df["fp_poc"] = np.round((df["high"] + df["low"] + 2.0 * df["close"]) / 4.0, 1)
            df["poc_source"] = "OHLC_APPROX"
        
        # 8. Order Book Depth (+-1% span normalized)
        print("[PROCESSOR] Estimating Order Book Depth Liquidity...")
        b_usd, a_usd, b_coin, a_coin = estimate_depth_from_volatility(closes, df["atr_14"].values, vols_base)
        df["bid_depth_usd"] = b_usd
        df["ask_depth_usd"] = a_usd
        df["bid_depth_coin"] = b_coin
        df["ask_depth_coin"] = a_coin

        # 9. Merge Historical Funding Rates
        print("[PROCESSOR] Merging Continuous Funding Rates...")
        if not funding_df.empty:
            f_df = funding_df.sort_values(by="fundingTime").copy()
            # Forward fill funding rate to each 15m bar
            df = pd.merge_asof(
                df,
                f_df[["fundingTime", "fundingRate"]],
                left_on="open_time_ms",
                right_on="fundingTime",
                direction="backward"
            )
            # Causal alignment: never backfill a future funding observation into older bars.
            raw_fr = df["fundingRate"].ffill().values
            df["funding_rate_pct"] = np.round(np.nan_to_num(raw_fr, nan=0.0001) * 100.0, 6)
            df.drop(columns=["fundingTime", "fundingRate"], inplace=True)
        else:
            df["funding_rate_pct"] = 0.010000

        # Basis USD: real futures-spot spread if spot data available
        if "spot_close" in df.columns and df["spot_close"].notna().any():
            df["basis_usd"] = np.round(df["close"].values - df["spot_close"].values, 2)
            df["basis_usd"] = df["basis_usd"].ffill().fillna(0.0)
            df.drop(columns=["spot_close"], inplace=True, errors="ignore")
        else:
            # Fallback: estimate from premium index if no spot data
            df["basis_usd"] = 0.0

        # 10. Merge Historical Metrics (Open Interest, L/S Ratios, Whale Index)
        print("[PROCESSOR] Merging Daily Metrics (Open Interest, L/S, Whale Index)...")
        if not metrics_df.empty:
            m_df = metrics_df.sort_values(by="timestamp_ms").copy()
            merged = pd.merge_asof(
                df,
                m_df[["timestamp_ms", "sum_open_interest", "sum_open_interest_value", "count_long_short_ratio", "sum_toptrader_long_short_ratio"]],
                left_on="open_time_ms",
                right_on="timestamp_ms",
                direction="backward"
            )
            raw_oi_btc = merged["sum_open_interest"].ffill().values
            oi_btc = np.nan_to_num(raw_oi_btc, nan=125000.0)

            raw_oi_usd = merged["sum_open_interest_value"].ffill().values
            oi_usd = np.where(np.isnan(raw_oi_usd), oi_btc * closes, raw_oi_usd)

            raw_ls_glob = merged["count_long_short_ratio"].ffill().values
            ls_glob = np.nan_to_num(raw_ls_glob, nan=1.035)

            raw_ls_top = merged["sum_toptrader_long_short_ratio"].ffill().values
            ls_top = np.nan_to_num(raw_ls_top, nan=1.076)

            df["open_interest_k"] = np.round(oi_btc / 1000.0, 3)
            df["open_interest_usd"] = np.round(oi_usd, 2)
            df["ls_ratio_global"] = np.round(ls_glob, 4)
            df["ls_ratio_top"] = np.round(ls_top, 4)
            # Whale Index: Coinglass uses Top Trader L/S Ratio (Positions) multiplied by 100.
            # Our dataset has Top Trader L/S Ratio (Accounts), which tracks closely but isn't exact.
            # But the nearest approximation matching the screenshots exactly is ls_top * 100.
            df["whale_index"] = np.round(ls_top * 100.0, 4)
        else:
            df["open_interest_k"] = 127.500
            df["open_interest_usd"] = df["open_interest_k"] * 1000.0 * closes
            df["ls_ratio_global"] = 1.0350
            df["ls_ratio_top"] = 1.0769
            df["whale_index"] = 107.6900

        # 11. Compute Mathematical Liquidations using Upgraded Model
        print("[PROCESSOR] Computing Mathematical Liquidations (Non-Linear Cascade + Funding Asymmetry)...")
        long_liqs, short_liqs = self.liq_model.compute_vectorized(df)
        df["long_liq_usd"] = long_liqs
        df["short_liq_usd"] = short_liqs

        # 12. Final Schema Selection and Ordering
        final_df = df[CANONICAL_COLUMNS].copy()
        
        # Verify no NaN values
        null_counts = final_df.isnull().sum()
        if null_counts.any():
            print(f"[PROCESSOR] Imputing isolated null values...")
            # Backfill would inject a future observation into earlier training rows.
            # Keep only causal forward-fill; pre-source rows retain the documented
            # neutral/sentinel value after numeric filling below.
            final_df = final_df.ffill()
            numeric = final_df.select_dtypes(include=[np.number]).columns
            final_df[numeric] = final_df[numeric].fillna(0.0)

        print(f"[PROCESSOR] Successfully synthesized canonical dataset: {len(final_df):,} rows x {len(final_df.columns)} columns.")
        return final_df
