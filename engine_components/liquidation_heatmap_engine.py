"""
Liquidation Heatmap & Symbol Liquidation Engine
===============================================
Computes:
1. Rolling Historical Liquidation Heatmap Zones & Density (Last 15+ days)
2. Immediate Warmup State for Live Market Execution
3. Tick-by-Tick Live WebSocket Liquidation & Heatmap Updates
"""

import os
import sys
import time
import math
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Tuple

class LiquidationHeatmapEngine:
    """
    Simulates and tracks resting liquidation clusters across price ladders
    based on historical OHLCV, Open Interest, Footprint Delta, and Leverage Tiers.
    """
    def __init__(self, bucket_size: float = 100.0, lookback_bars: int = 1440): # 1440 bars = 15 days of 15m
        self.bucket_size = bucket_size
        self.lookback_bars = lookback_bars
        
        # Leverage Tiers: (Leverage, Population Weight, Maintenance Margin Rate)
        self.leverage_tiers = [
            {"lev": 100, "weight": 0.15, "mmr": 0.004}, # ~1% distance
            {"lev": 50,  "weight": 0.25, "mmr": 0.004}, # ~2% distance
            {"lev": 25,  "weight": 0.30, "mmr": 0.005}, # ~4% distance
            {"lev": 10,  "weight": 0.20, "mmr": 0.010}, # ~10% distance
            {"lev": 5,   "weight": 0.10, "mmr": 0.020}, # ~20% distance
        ]
        
        # Active live resting buckets: {price_bucket: estimated_liquidation_usd}
        self.long_buckets = {}  # Liquidation pools resting BELOW price (Longs getting liquidated)
        self.short_buckets = {} # Liquidation pools resting ABOVE price (Shorts getting squeezed)
        self.current_price = 0.0

    def round_bucket(self, price: float) -> float:
        return round(price / self.bucket_size) * self.bucket_size

    def update_bar(self, open_p: float, high_p: float, low_p: float, close_p: float,
                   volume_usd: float, buy_qty: float, sell_qty: float, oi_usd: float = 0.0):
        """
        Updates the liquidation heatmap state with a completed candle:
        1. Clears (liquidates) resting buckets that were traversed by [low_p, high_p].
        2. Injects new estimated long and short liquidation clusters from the new position volume.
        """
        self.current_price = close_p
        tot_qty = buy_qty + sell_qty
        buy_ratio = (buy_qty / tot_qty) if tot_qty > 0 else 0.5
        
        long_inflow = volume_usd * buy_ratio
        short_inflow = volume_usd * (1.0 - buy_ratio)
        
        # 1. Clear traversed buckets (Executed liquidations)
        cleared_longs = [p for p in self.long_buckets.keys() if p >= low_p]
        for p in cleared_longs:
            del self.long_buckets[p]
            
        cleared_shorts = [p for p in self.short_buckets.keys() if p <= high_p]
        for p in cleared_shorts:
            del self.short_buckets[p]
            
        # 2. Inject new estimated liquidation clusters
        for tier in self.leverage_tiers:
            L = tier["lev"]
            w = tier["weight"]
            mmr = tier["mmr"]
            
            # Long Liquidation Price = P_entry * (1 - 1/L + MMR)
            p_long_liq = close_p * (1.0 - (1.0 / L) + mmr)
            if p_long_liq < low_p:
                b_long = self.round_bucket(p_long_liq)
                self.long_buckets[b_long] = self.long_buckets.get(b_long, 0.0) + (long_inflow * w)
                
            # Short Liquidation Price = P_entry * (1 + 1/L - MMR)
            p_short_liq = close_p * (1.0 + (1.0 / L) - mmr)
            if p_short_liq > high_p:
                b_short = self.round_bucket(p_short_liq)
                self.short_buckets[b_short] = self.short_buckets.get(b_short, 0.0) + (short_inflow * w)
                
        # 3. Decay distant or stale buckets (> 30% away)
        min_p = close_p * 0.70
        max_p = close_p * 1.30
        self.long_buckets = {k: v for k, v in self.long_buckets.items() if min_p <= k < close_p}
        self.short_buckets = {k: v for k, v in self.short_buckets.items() if close_p < k <= max_p}

    def get_heatmap_metrics(self) -> Dict[str, Any]:
        """
        Extracts summary features from the current liquidation heatmap state.
        """
        px = self.current_price if self.current_price > 0 else 1.0
        
        # Sort long clusters below price
        sorted_longs = sorted(
            [{"price": p, "usd": v, "dist_pct": ((px - p) / px) * 100} for p, v in self.long_buckets.items() if p < px],
            key=lambda x: x["usd"],
            reverse=True
        )
        
        # Sort short clusters above price
        sorted_shorts = sorted(
            [{"price": p, "usd": v, "dist_pct": ((p - px) / px) * 100} for p, v in self.short_buckets.items() if p > px],
            key=lambda x: x["usd"],
            reverse=True
        )
        
        nearest_long = sorted_longs[0] if sorted_longs else {"price": px * 0.95, "usd": 0.0, "dist_pct": 5.0}
        nearest_short = sorted_shorts[0] if sorted_shorts else {"price": px * 1.05, "usd": 0.0, "dist_pct": 5.0}
        
        tot_long_liq_usd = sum(x["usd"] for x in sorted_longs)
        tot_short_liq_usd = sum(x["usd"] for x in sorted_shorts)
        imbalance = tot_short_liq_usd / (tot_long_liq_usd + 1e-6)
        
        return {
            "current_price": px,
            "nearest_long_liq_price": nearest_long["price"],
            "nearest_long_liq_usd": nearest_long["usd"],
            "nearest_long_liq_dist_pct": nearest_long["dist_pct"],
            "nearest_short_liq_price": nearest_short["price"],
            "nearest_short_liq_usd": nearest_short["usd"],
            "nearest_short_liq_dist_pct": nearest_short["dist_pct"],
            "total_resting_long_liq_usd": tot_long_liq_usd,
            "total_resting_short_liq_usd": tot_short_liq_usd,
            "liq_heatmap_imbalance": imbalance, # > 1.5 = Heavy Short Squeeze Magnet, < 0.7 = Heavy Long Flush Magnet
            "top_3_long_zones": sorted_longs[:3],
            "top_3_short_zones": sorted_shorts[:3]
        }

    def warmup_from_dataframe(self, df: pd.DataFrame):
        """
        Replays historical DataFrame (e.g. last 15 days of 15m bars) to warm up the exact heatmap state.
        """
        df_sorted = df.sort_values("TimeStamp" if "TimeStamp" in df.columns else df.columns[0]).tail(self.lookback_bars)
        
        for _, row in df_sorted.iterrows():
            o = float(row["Open"])
            h = float(row["High"])
            l = float(row["Low"])
            c = float(row["Close"])
            vol = float(row["Volume"]) * c if "Volume" in row else float(row.get("quote_volume", 0.0))
            bq = float(row.get("Buy Qty", row.get("taker_buy_vol", vol * 0.5)))
            sq = float(row.get("Sell Qty", vol * 0.5))
            oi = float(row.get("Agg. OI", 0.0)) * c
            
            self.update_bar(o, h, l, c, vol, bq, sq, oi)

def enrich_historical_dataset_with_heatmap(df: pd.DataFrame, bucket_size: float = 100.0, lookback_bars: int = 1440) -> pd.DataFrame:
    """
    Vectorized/rolling enrichment of historical DataFrame with continuous Liquidation Heatmap features.
    """
    engine = LiquidationHeatmapEngine(bucket_size=bucket_size, lookback_bars=lookback_bars)
    
    n = len(df)
    n_long_p = np.zeros(n)
    n_long_usd = np.zeros(n)
    n_long_dist = np.zeros(n)
    n_short_p = np.zeros(n)
    n_short_usd = np.zeros(n)
    n_short_dist = np.zeros(n)
    imbalance = np.zeros(n)
    
    print(f"[LiquidationHeatmapEngine] Enriching {n} bars with continuous rolling Liquidation Heatmap...")
    for i in range(n):
        row = df.iloc[i]
        o = float(row["Open"])
        h = float(row["High"])
        l = float(row["Low"])
        c = float(row["Close"])
        vol = float(row["Volume"]) * c if "Volume" in row else float(row.get("quote_volume", 0.0))
        bq = float(row.get("Buy Qty", row.get("taker_buy_vol", vol * 0.5)))
        sq = float(row.get("Sell Qty", vol * 0.5))
        oi = float(row.get("Agg. OI", 0.0)) * c
        
        engine.update_bar(o, h, l, c, vol, bq, sq, oi)
        m = engine.get_heatmap_metrics()
        
        n_long_p[i] = m["nearest_long_liq_price"]
        n_long_usd[i] = m["nearest_long_liq_usd"]
        n_long_dist[i] = m["nearest_long_liq_dist_pct"]
        n_short_p[i] = m["nearest_short_liq_price"]
        n_short_usd[i] = m["nearest_short_liq_usd"]
        n_short_dist[i] = m["nearest_short_liq_dist_pct"]
        imbalance[i] = m["liq_heatmap_imbalance"]
        
    df_out = df.copy()
    df_out["Heatmap_Nearest_Long_Liq_Price"] = n_long_p
    df_out["Heatmap_Nearest_Long_Liq_USD"] = n_long_usd
    df_out["Heatmap_Long_Liq_Distance_Pct"] = n_long_dist
    df_out["Heatmap_Nearest_Short_Liq_Price"] = n_short_p
    df_out["Heatmap_Nearest_Short_Liq_USD"] = n_short_usd
    df_out["Heatmap_Short_Liq_Distance_Pct"] = n_short_dist
    df_out["Heatmap_Liquidity_Imbalance"] = imbalance
    
    return df_out
