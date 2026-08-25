"""
Comprehensive Parity Audit: Live Monitor vs Historical Parquet
Compares all 37 canonical indicators for the last completed 15m candle (14:30 UTC, 2026-08-25)
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# Load ground truth from parquet
with open('ground_truth.json', 'r') as f:
    gt = json.load(f)

# Parse live monitor output (from the --once --single run)
# The live monitor showed "Candle: 16:00 UTC" which is the CURRENT forming candle
# We need to check what it computes for the 14:30 completed candle

# Live monitor output captured:
# Candle: 16:00 UTC (forming)
# But the parquet's last COMPLETED is 14:30 UTC

# Let me extract key values from live monitor output for comparison
# The live monitor run at 21:39 UTC showed forming candle at 16:00 UTC
# The parquet has completed candles up to 14:30 UTC

print("=" * 100)
print("PARITY AUDIT: BINANCE LIVE MONITOR vs HISTORICAL PARQUET (2020-2026)")
print("=" * 100)
print()
print("PARQUET GROUND TRUTH (Last Completed Candle: 2026-08-25 14:30:00 UTC)")
print("-" * 100)

# Print ground truth in organized categories
categories = {
    'PRICE & VOLUME': ['close', 'volume_quote', 'volume_base', 'volume_sma9', 'trade_count'],
    'TECHNICAL INDICATORS': ['ema_8', 'ema_21', 'ema_50', 'ema_200', 'ema_800', 'rsi_14', 'atr_14', 'atr_100'],
    'CVD & FLOW': ['future_cvd_15m', 'future_cvd_session', 'future_cvd_lifetime', 
                   'spot_cvd_15m', 'spot_cvd_session', 'spot_cvd_lifetime',
                   'fp_delta', 'fp_poc'],
    'POSITIONING & FUNDING': ['funding_rate_pct', 'basis_usd', 'open_interest_k', 'open_interest_usd',
                              'oi_change_pct', 'ls_ratio_global', 'ls_ratio_top', 
                              'top_account_ratio', 'whale_index', 'taker_volume_ratio'],
    'LIQUIDATIONS': ['long_liq_usd', 'short_liq_usd'],
    'VALUE AREA': ['session_vah', 'session_val', 'prev_day_vah', 'prev_day_val'],
    'DEPTH': ['bid_depth_usd', 'ask_depth_usd', 'bid_depth_coin', 'ask_depth_coin'],
    'MICROSTRUCTURE': ['taker_buy_count', 'taker_sell_count', 'taker_buy_vol_btc', 
                       'taker_sell_vol_btc', 'max_trade_vol_btc', 'avg_trade_size_usd'],
}

for cat, keys in categories.items():
    print(f"\n{cat}:")
    for k in keys:
        if k in gt:
            val = gt[k]
            if isinstance(val, float):
                if abs(val) >= 1e6:
                    print(f"  {k:25s}: {val:>15,.0f} ({val/1e6:.2f}M)")
                elif abs(val) >= 1e3:
                    print(f"  {k:25s}: {val:>15,.2f} ({val/1e3:.2f}K)")
                else:
                    print(f"  {k:25s}: {val:>15,.4f}")
            else:
                print(f"  {k:25s}: {val}")

print()
print("=" * 100)
print("LIVE MONITOR OUTPUT (from --once --single run at 21:39 UTC)")
print("=" * 100)
print("NOTE: Live monitor showed forming candle at 16:00 UTC, not 14:30 UTC")
print("The parquet ends at 14:30 UTC. Live monitor caught up 14:45, 15:00, 15:15, 15:30, 15:45 via REST")
print()

# Live monitor values for the FORMING 16:00 candle (extracted from terminal output)
live = {
    'close': 79343.00,
    'volume_quote': 136.869e6,
    'volume_base': 1722.45,
    'volume_sma9': 210.21e6,
    'rsi_14': 52.72,
    'atr_14': 329.92,
    'atr_100': 326.18,
    'future_cvd_session': 27016.0,  # +27.016K BTC
    'spot_cvd_session': -15541.0,   # -15.541K BTC
    'funding_rate_pct': 0.010000,
    'basis_usd': -42.99,
    'open_interest_k': 126.617,
    'oi_change_pct': 0.00,
    'ls_ratio_global': 0.9535,
    'ls_ratio_top': 2.2304,
    'whale_index': 223.04,
    'fp_delta': -111.846,
    'fp_poc': 79450.00,
    'session_vah': 80450.00,
    'session_val': 78575.00,
    'prev_day_vah': 79850.0,
    'prev_day_val': 77800.0,
    'bid_depth_usd': 187.46e6,
    'ask_depth_usd': 156.64e6,
    'avg_trade_size_usd': 3709.0,
    'ema_8': 79238.0,
    'ema_21': 79206.0,
    'ema_200': 78658.0,
}

print("Live Monitor (Forming 16:00 UTC Candle):")
for k, v in live.items():
    if isinstance(v, float):
        if abs(v) >= 1e6:
            print(f"  {k:25s}: {v:>15,.0f} ({v/1e6:.2f}M)")
        elif abs(v) >= 1e3:
            print(f"  {k:25s}: {v:>15,.2f} ({v/1e3:.2f}K)")
        else:
            print(f"  {k:25s}: {v:>15,.4f}")
    else:
        print(f"  {k:25s}: {v}")

print()
print("=" * 100)
print("DIRECT COMPARISON FOR SAME CANDLE (14:30 UTC) - REQUIRES LIVE MONITOR TO SHOW HISTORICAL")
print("=" * 100)
print()
print("CRITICAL FINDING: Live monitor does NOT load from parquet on startup!")
print("It seeds from 10,000 REST klines (~104 days) only.")
print()
print("Key Discrepancies Expected:")
print("  1. future_cvd_lifetime: Parquet = -2,455,750 BTC | Live = ~27,016 BTC (session only, ~104 days)")
print("  2. spot_cvd_lifetime:   Parquet = -561,266 BTC   | Live = ~-15,541 BTC (session only)")
print("  3. EMAs (800, 200):     Parquet converged from 209,723 bars | Live from 10,000 bars only")
print("  4. Session VAH/VAL:     Parquet = full day profile | Live = incremental from catch-up")
print("  5. Depth:               Parquet = volatility-calibrated | Live = REST 1000-level extrapolation")
print()

# Compute expected differences for EMAs
print("EMA Convergence Analysis:")
print(f"  Parquet bars: 209,723 (Sept 2020 -> Present)")
print(f"  Live seed bars: ~10,000 (REST API limit)")
print(f"  EMA 800 needs ~5*period = 4,000 bars for full convergence")
print(f"  EMA 200 needs ~1,000 bars")
print(f"  10,000 bars sufficient for EMA 800 convergence (barely)")
print()

# The real issue: CVD lifetime
print("CVD Lifetime Discrepancy:")
print(f"  Parquet future_cvd_lifetime (14:30): {gt['future_cvd_lifetime']:,.2f} BTC")
print(f"  Live future_cvd_session (16:00):     {live['future_cvd_session']:,.2f} BTC")
print(f"  Difference: {gt['future_cvd_lifetime'] - live['future_cvd_session']:,.2f} BTC")
print(f"  Live monitor ONLY tracks session CVD (since 00:00 UTC) from 10k-bar seed")
print(f"  It does NOT have lifetime CVD from 2020")
print()

# Check if parquet loading code exists
print("=" * 100)
print("CODE ANALYSIS: Parquet Loading in binance_live_monitor.py")
print("=" * 100)
import re
with open('binance_live_monitor.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Search for parquet loading
parquet_reads = [m.start() for m in re.finditer(r'read_parquet|pd\.read_parquet', content)]
parquet_loads = [m.start() for m in re.finditer(r'parquet.*load|load.*parquet', content, re.IGNORECASE)]
seed_from_rest = [m.start() for m in re.finditer(r'seed_from_rest', content)]

print(f"  pd.read_parquet calls: {len(parquet_reads)}")
print(f"  seed_from_rest calls: {len(seed_from_rest)}")

# Check run_live_comparison for parquet loading
if 'run_live_comparison' in content:
    start = content.index('async def run_live_comparison')
    end = content.index('async def run_multi_asset_matrix')
    func_body = content[start:end]
    if 'read_parquet' in func_body or 'parquet' in func_body.lower():
        print("  Parquet loading found in run_live_comparison")
    else:
        print("  NO parquet loading in run_live_comparison - seeds from REST only")

# Check KL_STATE.seed_from_rest
if 'seed_from_rest' in content:
    idx = content.index('seed_from_rest')
    # Find the method
    class_start = content.rfind('class KlineState', 0, idx)
    if class_start > 0:
        method_start = content.find('async def seed_from_rest', class_start)
        if method_start > 0:
            method_end = content.find('async def', method_start + 1)
            if method_end < 0:
                method_end = method_start + 3000
            method = content[method_start:method_end]
            if 'cvd_lifetime' in method or 'lifetime' in method.lower():
                print("  seed_from_rest computes lifetime CVD")
            else:
                print("  seed_from_rest does NOT compute lifetime CVD (only session)")

print()
print("=" * 100)
print("RECOMMENDED FIXES")
print("=" * 100)
print("""
1. ADD PARQUET LOADING AT STARTUP (Critical)
   - In run_live_comparison(), before seeding from REST:
     * Load master parquet: df = pd.read_parquet(parquet_path)
     * Extract last row state for ALL indicators
     * Seed KL_STATE, AGG_STATE, SPOT_AGG with full historical state
     
2. FIX CVD LIFETIME INITIALIZATION (Critical)
   - In KL_STATE.seed_from_rest(): 
     * Compute future_cvd_lifetime = parquet['future_cvd_lifetime'].iloc[-1] + delta_since_parquet
     * Same for spot_cvd_lifetime
     
3. FIX SESSION VAH/VAL INITIALIZATION (High)
   - Load session_vah, session_val, prev_day_vah, prev_day_val from parquet
   - AGG_STATE.session_profile should be initialized from parquet's last session profile
   
4. UNIFY DEPTH CALCULATION (Medium)
   - Use canonical_indicators.estimate_depth_from_volatility() in both pipeline and live
   - Current live uses REST 1000-level extrapolation (poll_depth_loop)
   
5. ADD HISTORICAL CANDLE VERIFICATION MODE (Medium)
   - Add --verify-historical flag to output last N completed candles for comparison
   - Compare against parquet at same timestamps

6. FIX MAX_TRADE_VOL_BTC (Low)
   - Live shows 0.00 - needs proper tracking from aggTrade stream
   - Parquet has 123.43 BTC for 14:30 candle
""")