#!/usr/bin/env python3
"""
================================================================================
ENGINE 2: STRATEGY CALIBRATOR & MULTI-STRATEGY PASS FINDER
================================================================================
Evaluates all 9 strategies across all 20 OOS windows with:
  - Top-5 / Top-6 trade selection
  - 5R Asymmetric runner geometry
  - Dynamic House-Money compounding
  - In-Sample probability thresholding
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

import pandas as pd
import numpy as np

# Import all strategy modules
from s1_liquidation_cascade import run_s1_walkforward
from s2_cvd_momentum import run_s2_walkforward
from s3_macro_trend_follow import run_s3_walkforward
from s4_cvd_divergence_squeeze import run_s4_walkforward
from s5_liquidity_sweep_reversal import run_s5_walkforward
from s6_volatility_compression_breakout import run_s6_walkforward
from s7_delta_climax_mean_reversion import run_s7_walkforward
from s8_hybrid_whale_cvd import run_s8_walkforward
from s15_vwap_profile_conviction import run_s15_walkforward

print("All 9 strategy modules successfully imported and ready for autonomous optimization.")
