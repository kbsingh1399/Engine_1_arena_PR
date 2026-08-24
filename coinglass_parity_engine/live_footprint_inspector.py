"""
================================================================================
COINGLASS LEGEND STYLE LIVE FOOTPRINT INSPECTOR (MERGE LEVEL = $5.0)
================================================================================
Direct single-module entrypoint for Binance Futures 15m Footprint & Indicators.
Runs all 8 WebSocket streams concurrently with zero blocking latency.
================================================================================
"""

import os
import sys
import asyncio

# Ensure project root is in pythonpath
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from binance_live_monitor import run_live_comparison

if __name__ == "__main__":
    try:
        asyncio.run(run_live_comparison(show_indicators=False))
    except KeyboardInterrupt:
        print("\n[EXIT] Live footprint monitor closed.")
