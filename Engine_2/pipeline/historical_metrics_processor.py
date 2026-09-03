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
    get_merge_level,
    compute_ema_series,
    compute_wilder_rsi_series,
    compute_wilder_atr_series,
    compute_volume_sma9_series,
    compute_session_cvd,
    estimate_depth_from_volatility,
    compute_session_value_area,
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
        spot_df: pd.DataFrame = None,
        symbol: str = "BTCUSDT"
    ) -> pd.DataFrame:
        """
        Executes end-to-end indicator calculation and produces a canonical multi-indicator DataFrame.
        """
        print(f"[PROCESSOR] Processing Master Historical Dataset for {symbol}...")
        df = klines_df.copy()
        
        # Guarantee 100% continuous, unbroken 15m timeline
        df.drop_duplicates(subset=["open_time"], inplace=True)
        df.sort_values(by="open_time", inplace=True)
        df.reset_index(drop=True, inplace=True)
        
        start_ms = int(df["open_time"].iloc[0])
        end_ms = int(df["open_time"].iloc[-1])
        expected_ms = np.arange(start_ms, end_ms + 900_000, 900_000, dtype=np.int64)
        
        if len(df) < len(expected_ms):
            missing_bars = len(expected_ms) - len(df)
            print(f"[PROCESSOR] Symbol {symbol} has {missing_bars} residual missing bars. Reindexing to unbroken continuous 15m timeline...")
            df = df.set_index("open_time").reindex(expected_ms)
            df.index.name = "open_time"
            df.reset_index(inplace=True)
            df["open_time"] = df["open_time"].astype(np.int64)
            df["close_time"] = df["open_time"] + 899_999
            
            # Forward fill prices so no NaNs exist
            df["close"] = df["close"].ffill().bfill()
            df["open"] = df["open"].fillna(df["close"])
            df["high"] = df["high"].fillna(df["close"])
            df["low"] = df["low"].fillna(df["close"])
            
            # Zero out volume on exchange downtime
            for col in ["volume", "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume"]:
                if col in df.columns:
                    df[col] = df[col].fillna(0.0)
        
        # 1. Base Timestamps and Symbol
        df["open_time_ms"] = df["open_time"].astype(np.int64)
        df["close_time_ms"] = df["close_time"].astype(np.int64)
        df["datetime_utc"] = pd.to_datetime(df["open_time_ms"], unit="ms", utc=True).dt.strftime("%Y-%m-%d %H:%M:%S")
        df["symbol"] = symbol

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

        # 3. Volume SMA 9 & Average Trade Size
        print("[PROCESSOR] Computing Volume SMA 9 & Technical Indicators...")
        df["volume_sma9"] = compute_volume_sma9_series(vols_quote)
        df["avg_trade_size_usd"] = np.round(vols_quote / np.maximum(df["trade_count"].values, 1), 2)

        # 4. Technical Indicators (Wilder RSI 14, Wilder ATR 14 & 100)
        df["rsi_14"] = compute_wilder_rsi_series(closes, 14)
        df["atr_14"] = compute_wilder_atr_series(highs, lows, closes, 14)
        df["atr_100"] = compute_wilder_atr_series(highs, lows, closes, 100)

        # 5. Continuous Seeded EMAs
        print("[PROCESSOR] Computing Seeded Continuous EMAs (8, 21, 50, 200, 800)...")
        df["ema_8"] = np.round(compute_ema_series(closes, 8), 2)
        df["ema_21"] = np.round(compute_ema_series(closes, 21), 2)
        df["ema_50"] = np.round(compute_ema_series(closes, 50), 2)
        df["ema_200"] = np.round(compute_ema_series(closes, 200), 2)
        df["ema_800"] = np.round(compute_ema_series(closes, 800), 2)

        # 6. Developing Daily Session Value Area High (VAH) & Low (VAL)
        m_lvl = get_merge_level(symbol)
        print(f"[PROCESSOR] Computing Developing Daily Session Value Area (VAH / VAL) with bucket size {m_lvl}...")
        svah, sval, pvah, pval = compute_session_value_area(open_times, highs, lows, closes, vols_base, bucket_size=m_lvl)
        df["session_vah"] = svah
        df["session_val"] = sval
        df["prev_day_vah"] = pvah
        df["prev_day_val"] = pval

        # 7. Order Flow & Cumulative Volume Deltas
        print("[PROCESSOR] Computing Order Flow & Cumulative Volume Deltas...")
        approx_buy_btc = df["taker_buy_volume"].astype(np.float64).values
        approx_sell_btc = vols_base - approx_buy_btc
        approx_buy_count = np.round(df["trade_count"].values * (approx_buy_btc / np.maximum(vols_base, 1e-6))).astype(np.int64)
        approx_sell_count = df["trade_count"].values - approx_buy_count

        if footprint_df is not None and not footprint_df.empty:
            print("[PROCESSOR] Merging exact high-fidelity tick footprint data where available...")
            fp_clean = footprint_df.sort_values(by="open_time_ms").copy()
            merged_fp = pd.merge_asof(
                df.sort_values("open_time_ms"),
                fp_clean,
                on="open_time_ms",
                direction="nearest",
                tolerance=60000
            )
            
            exact_mask = merged_fp["taker_buy_vol_coin"].notna()
            taker_buy_btc = np.where(exact_mask, merged_fp["taker_buy_vol_coin"].values, approx_buy_btc)
            taker_sell_btc = np.where(exact_mask, merged_fp["taker_sell_vol_coin"].values, approx_sell_btc)
            df["taker_buy_count"] = np.where(exact_mask, merged_fp["taker_buy_count"].values, approx_buy_count).astype(np.int64)
            df["taker_sell_count"] = np.where(exact_mask, merged_fp["taker_sell_count"].values, approx_sell_count).astype(np.int64)
            df["future_flow_source"] = np.where(exact_mask, "TICK_EXACT", "KLINE_APPROX")
            
            if "max_single_trade_vol" in merged_fp.columns:
                real_max_trade = merged_fp["max_single_trade_vol"].values
                df["max_trade_vol_btc"] = np.round(np.where(np.isnan(real_max_trade), vols_base * 0.05, real_max_trade), 4)
            else:
                df["max_trade_vol_btc"] = np.round(vols_base * 0.05, 4)
        else:
            taker_buy_btc = approx_buy_btc
            taker_sell_btc = approx_sell_btc
            df["taker_buy_count"] = approx_buy_count
            df["taker_sell_count"] = approx_sell_count
            df["future_flow_source"] = "KLINE_APPROX"
            df["max_trade_vol_btc"] = np.round(vols_base * 0.05, 4)

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

        # 8. Footprint POC
        df["fp_delta"] = fut_delta_15m
        if footprint_df is not None and "real_poc" in footprint_df.columns:
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
        
        # 9. Order Book Depth (+-1% span normalized)
        print("[PROCESSOR] Estimating Order Book Depth Liquidity...")
        b_usd, a_usd, b_coin, a_coin = estimate_depth_from_volatility(closes, df["atr_14"].values, vols_base)
        df["bid_depth_usd"] = b_usd
        df["ask_depth_usd"] = a_usd
        df["bid_depth_coin"] = b_coin
        df["ask_depth_coin"] = a_coin

        # 10. Merge Historical Funding Rates
        print("[PROCESSOR] Merging Continuous Funding Rates...")
        if not funding_df.empty:
            f_df = funding_df.sort_values(by="fundingTime").copy()
            df = pd.merge_asof(
                df,
                f_df[["fundingTime", "fundingRate"]],
                left_on="open_time_ms",
                right_on="fundingTime",
                direction="backward"
            )
            raw_fr = df["fundingRate"].ffill().values
            df["funding_rate_pct"] = np.round(np.nan_to_num(raw_fr, nan=0.0001) * 100.0, 6)
            df.drop(columns=["fundingTime", "fundingRate"], inplace=True, errors="ignore")
        else:
            df["funding_rate_pct"] = 0.010000

        # Basis USD
        if "spot_close" in df.columns and df["spot_close"].notna().any():
            df["basis_usd"] = np.round(df["close"].values - df["spot_close"].values, 2)
            df["basis_usd"] = df["basis_usd"].ffill().fillna(0.0)
            df.drop(columns=["spot_close"], inplace=True, errors="ignore")
        else:
            df["basis_usd"] = 0.0

        # 11. Merge Historical Metrics (Open Interest, L/S Ratios, Whale Index, Taker Ratio)
        print("[PROCESSOR] Merging Daily Metrics (Open Interest, L/S, Whale Index, Taker Ratio)...")
        if not metrics_df.empty:
            m_df = metrics_df.sort_values(by="timestamp_ms").copy()
            cols_to_merge = ["timestamp_ms", "sum_open_interest", "sum_open_interest_value", "count_long_short_ratio", "sum_toptrader_long_short_ratio"]
            if "count_toptrader_long_short_ratio" in m_df.columns:
                cols_to_merge.append("count_toptrader_long_short_ratio")
            if "sum_taker_long_short_vol_ratio" in m_df.columns:
                cols_to_merge.append("sum_taker_long_short_vol_ratio")

            merged = pd.merge_asof(
                df,
                m_df[cols_to_merge],
                left_on="open_time_ms",
                right_on="timestamp_ms",
                direction="backward"
            )
            raw_oi_btc = merged["sum_open_interest"].ffill().values
            oi_btc = np.nan_to_num(raw_oi_btc, nan=0.0)

            raw_oi_usd = merged["sum_open_interest_value"].ffill().values
            oi_usd = np.where(np.isnan(raw_oi_usd), oi_btc * closes, raw_oi_usd)

            raw_ls_glob = merged["count_long_short_ratio"].ffill().values
            ls_glob = np.nan_to_num(raw_ls_glob, nan=1.0)

            raw_ls_top = merged["sum_toptrader_long_short_ratio"].ffill().values
            ls_top = np.nan_to_num(raw_ls_top, nan=1.0)

            df["open_interest_k"] = np.round(oi_btc / 1000.0, 3)
            df["open_interest_usd"] = np.round(oi_usd, 2)
            df["ls_ratio_global"] = np.round(ls_glob, 4)
            df["ls_ratio_top"] = np.round(ls_top, 4)
            # CoinGlass Whale Index = (Top Trader Long % / Global Trader Long %) * 100
            top_long_p = ls_top / (1.0 + ls_top)
            glob_long_p = ls_glob / (1.0 + ls_glob)
            df["whale_index"] = np.round((top_long_p / np.maximum(glob_long_p, 0.0001)) * 100.0, 4)

            if "count_toptrader_long_short_ratio" in merged.columns:
                raw_top_acc = merged["count_toptrader_long_short_ratio"].ffill().values
                df["top_account_ratio"] = np.round(np.nan_to_num(raw_top_acc, nan=1.0), 4)
            else:
                df["top_account_ratio"] = np.round(ls_glob, 4)

            fallback_taker = np.round(df["taker_buy_vol_btc"].values / np.maximum(df["taker_sell_vol_btc"].values, 1e-6), 4)
            if "sum_taker_long_short_vol_ratio" in merged.columns:
                raw_taker_ratio = merged["sum_taker_long_short_vol_ratio"].ffill().values
                df["taker_volume_ratio"] = np.round(np.where(np.isnan(raw_taker_ratio), fallback_taker, raw_taker_ratio), 4)
            else:
                df["taker_volume_ratio"] = fallback_taker
        else:
            df["open_interest_k"] = 0.0
            df["open_interest_usd"] = 0.0
            df["ls_ratio_global"] = 1.0
            df["ls_ratio_top"] = 1.0
            df["top_account_ratio"] = 1.0
            df["whale_index"] = 100.0
            df["taker_volume_ratio"] = np.round(df["taker_buy_vol_btc"].values / np.maximum(df["taker_sell_vol_btc"].values, 1e-6), 4)

        # OI rate of change (% per 15m bar)
        df["oi_change_pct"] = np.round(df["open_interest_k"].pct_change().fillna(0.0).values * 100.0, 4)

        # 12. Compute Mathematical Liquidations using Upgraded Model
        print("[PROCESSOR] Computing Mathematical Liquidations (Non-Linear Cascade + Funding Asymmetry)...")
        long_liqs, short_liqs = self.liq_model.compute_vectorized(df)
        df["long_liq_usd"] = long_liqs
        df["short_liq_usd"] = short_liqs

        # 13. Final Schema Selection and Ordering
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
