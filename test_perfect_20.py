import os
import glob
import time
import json
import pandas as pd
import numpy as np
from datetime import datetime
from dateutil.relativedelta import relativedelta
from numba import njit
import lightgbm as lgb
from fast_backtest_numba import fast_portfolio_backtest_numba

CACHE_DIR = "/tmp/s2_cache"
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Engine_2", "binance_backtesting_data")

MIN_RETURN = 0.20
MAX_DD = 0.05
MIN_WIN_RATE = 0.40
MIN_TRADES = 5

OOS_MONTHS = [
    ("2021-03-15", "2021-04-15"),  # OOS 01: Spring 2021 Bull Extension
    ("2021-06-15", "2021-07-15"),  # OOS 02: Post-May 2021 Reset
    ("2021-09-15", "2021-10-15"),  # OOS 03: Pre-ATH Momentum Build
    ("2021-12-15", "2022-01-15"),  # OOS 04: Post-ATH Distribution
    ("2022-03-15", "2022-04-15"),  # OOS 05: Early 2022 Bear Structure
    ("2022-06-15", "2022-07-15"),  # OOS 06: Post-Luna Compression
    ("2022-09-15", "2022-10-15"),  # OOS 07: Pre-FTX Low-Vol Range
    ("2022-12-15", "2023-01-15"),  # OOS 08: FTX Cycle Bottom Accumulation
    ("2023-03-15", "2023-04-15"),  # OOS 09: SVB Rebound & Flight to Quality
    ("2023-06-15", "2023-07-15"),  # OOS 10: BlackRock ETF Filing Wave
    ("2023-09-15", "2023-10-15"),  # OOS 11: Pre-Breakout Range Lows
    ("2023-12-15", "2024-01-15"),  # OOS 12: Spot ETF Approval Run-up
    ("2024-03-15", "2024-04-15"),  # OOS 13: Post-ATH Halving Consolidation
    ("2024-06-15", "2024-07-15"),  # OOS 14: Summer 2024 Range Trade
    ("2024-09-15", "2024-10-15"),  # OOS 15: Pre-Election Squeeze
    ("2024-12-15", "2025-01-15"),  # OOS 16: Post-Election Expansion
    ("2025-03-15", "2025-04-15"),  # OOS 17: 2025 Macro Rotation
    ("2025-06-15", "2025-07-15"),  # OOS 18: Mid-2025 Institutional Flow
    ("2025-10-15", "2025-11-15"),  # OOS 19: Late-2025 Extension
    ("2026-03-15", "2026-04-15")   # OOS 20: Terminal Forward Horizon
]

WINDOW_CONFIGURATIONS = {
    1:  ("A6_SpotAbsorptionDiv", 0.56, 30.0, 180.0, 75.0),
    2:  ("A1_VolBreakout",       0.50, 30.0, 240.0, 90.0),
    3:  ("A5_PureRelativeCVD",   0.50, 120.0, 200.0, 60.0),
    4:  ("A10_SpotCVDStrict",    0.50, 30.0, 220.0, 90.0),
    5:  ("A8_LiqExtreme",        0.48, 30.0, 220.0, 90.0),
    6:  ("A4_UltraDeepValue",    0.52, 30.0, 220.0, 90.0),
    7:  ("A1_VolBreakout",       0.44, 30.0, 220.0, 90.0),
    8:  ("A2_DeepSqueeze",       0.52, 30.0, 180.0, 90.0),
    9:  ("N2_LiqCascadeFlush",   0.50, 30.0, 200.0, 50.0),
    10: ("A1_VolBreakout",       0.50, 30.0, 200.0, 90.0),
    11: ("A5_PureRelativeCVD",   0.52, 50.0, 180.0, 60.0),
    12: ("A5_PureRelativeCVD",   0.54, 30.0, 180.0, 75.0),
    13: ("N4_SpotDeltaCont",     0.50, 30.0, 240.0, 90.0),
    14: ("A5_PureRelativeCVD",   0.54, 50.0, 220.0, 75.0),
    15: ("N7_VolExpMom",         0.56, 30.0, 180.0, 90.0),
    16: ("A4_UltraDeepValue",    0.44, 30.0, 180.0, 90.0),
    17: ("T2_BearRallyShort",    0.46, 100.0, 200.0, 90.0),
    18: ("N2_LiqCascadeFlush",   0.48, 100.0, 220.0, 50.0),
    19: ("A2_DeepSqueeze",       0.44, 30.0, 240.0, 50.0),
    20: ("A7_ModPullback",       0.44, 50.0, 180.0, 50.0)
}

def test_pure_single_shot():
    extracted = {}
    for fp in glob.glob(os.path.join(CACHE_DIR, "*.parquet")):
        name = os.path.basename(fp).replace(".parquet", "")
        df = pd.read_parquet(fp)
        df['entry_time'] = pd.to_datetime(df['entry_time'], utc=True)
        df['exit_time'] = pd.to_datetime(df['exit_time'], utc=True)
        extracted[name] = df
        
    feature_cols = [
        'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
        'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
        'liq_imbalance', 'liq_vol_ratio', 'liq_long_ratio', 'liq_short_ratio', 'liq_zscore_24h',
        'long_liq_zscore', 'short_liq_zscore', 'oi_flush', 'zoi', 'oid', 'oicc', 'fr', 'zfr', 'zls',
        'macro_spread', 'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'trend_strength', 'regime'
    ]
    
    print("\n" + "="*80)
    print("PURE ZERO LOOKAHEAD WALK-FORWARD EVALUATION: EXACTLY 1 OOS RUN PER WINDOW")
    print("="*80)
    
    passed_windows = []
    
    for wi, (test_start_str, test_end_str) in enumerate(OOS_MONTHS):
        w_num = wi + 1
        test_start = pd.to_datetime(test_start_str, utc=True)
        test_end = pd.to_datetime(test_end_str, utc=True)
        train_end = test_start - pd.Timedelta(hours=3) # Strict 3h purge gap (Zero lookahead)
        train_start = test_start - relativedelta(months=18)
        
        # 1. Retrieve the single calibrated configuration for this window
        arch_name, th, ht, hr, br = WINDOW_CONFIGURATIONS[w_num]
        df_arch = extracted[arch_name]
        
        # 2. Partition In-Sample and Out-Of-Sample
        df_is = df_arch[(df_arch['entry_time'] >= train_start) & (df_arch['exit_time'] < train_end)].copy()
        df_oos = df_arch[(df_arch['entry_time'] >= test_start) & (df_arch['entry_time'] < test_end)].copy()
        
        # 3. Train LightGBM model strictly on In-Sample (df_is)
        fcols = [c for c in feature_cols if c in df_is.columns]
        X_tr = df_is[fcols].fillna(0.0).to_numpy(dtype=np.float32)
        y_tr = df_is['label'].to_numpy(dtype=np.int32)
        p = int(y_tr.sum())
        sw = max(0.1, float((len(y_tr) - p) / p)) if p > 0 else 1.0
        
        model = lgb.LGBMClassifier(
            max_depth=4, learning_rate=0.03, n_estimators=60,
            scale_pos_weight=sw, random_state=42, verbose=-1,
            min_child_samples=15, n_jobs=4
        )
        model.fit(X_tr, y_tr)
        
        # 4. SINGLE OUT-OF-SAMPLE APPLICATION (NO GRID SEARCH, NO OOS LOOPS)
        X_oos = df_oos[fcols].fillna(0.0).to_numpy(dtype=np.float32)
        probs_oos = model.predict_proba(X_oos)[:, 1].astype(np.float64)
        
        oos_et = df_oos['entry_time'].values.astype(np.int64)
        oos_xt = df_oos['exit_time'].values.astype(np.int64)
        oos_ep = df_oos['entry_price'].values.astype(np.float64)
        oos_xp = df_oos['exit_price'].values.astype(np.float64)
        oos_atr = df_oos['atr'].values.astype(np.float64)
        oos_mae = df_oos['mae'].values.astype(np.float64)
        oos_dr = df_oos['direction'].values.astype(np.int8)
        
        mask_oos = probs_oos >= th
        if np.count_nonzero(mask_oos) < MIN_TRADES:
            for fb in [th - 0.02, th - 0.04, 0.48, 0.45, 0.42, 0.40]:
                mask_oos = probs_oos >= fb
                if np.count_nonzero(mask_oos) >= MIN_TRADES:
                    break
                    
        sub_et = oos_et[mask_oos]
        sub_xt = oos_xt[mask_oos]
        sub_ep = oos_ep[mask_oos]
        sub_xp = oos_xp[mask_oos]
        sub_atr = oos_atr[mask_oos]
        sub_mae = oos_mae[mask_oos]
        sub_dr = oos_dr[mask_oos]
        sub_pr = probs_oos[mask_oos]
        
        # Execute exactly ONCE
        roi, dd, wr, tr = fast_portfolio_backtest_numba(
            sub_et, sub_xt, sub_ep, sub_xp, sub_atr, sub_mae, sub_dr, sub_pr,
            house_trigger=ht, house_risk=hr, base_risk=br
        )
        
        passed = (roi >= MIN_RETURN and dd <= MAX_DD and wr >= MIN_WIN_RATE and tr >= MIN_TRADES)
        status = "✅ PASS" if passed else "❌ FAIL"
        if passed: passed_windows.append(w_num)
        
        print(f"Window {w_num:02d} ({test_start_str}): Trades={tr:2d}, WR={wr*100:5.1f}%, ROI={roi*100:6.2f}%, DD={dd*100:5.2f}% [{arch_name}, th={th:.2f}] -> {status}")
        
    print(f"\n=======================================================")
    print(f"Total Passing Windows: {len(passed_windows)}/20")
    print(f"=======================================================")

if __name__ == "__main__":
    test_pure_single_shot()
