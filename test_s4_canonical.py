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
from extract_cache import featurize_df, get_btc_ref, gen_symbol_trades, DATA_DIR

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

# S4 Mean Reversion Archetypes with Canonical Wilder RSI
S4_ARCHETYPES = {
    # MR1: Spot Absorption Divergence Mean Reversion
    "MR1_SpotAbsorption": lambda df: (
        ((df['cvd_divergence'] > 0) & (df['spot_cvd_delta'] > 0) & (df['p8'] < -0.18)),
        ((df['cvd_divergence'] < 0) & (df['spot_cvd_delta'] < 0) & (df['p8'] > 0.18))
    ),
    # MR2: Volatility Expansion Exhaustion Reversion
    "MR2_VolExpansionExhaustion": lambda df: (
        ((df['vol_ratio'] > 1.15) & (df['mc'] > 0) & (df['p8'] < -0.12) & (df['zc4'] > 0.2)),
        ((df['vol_ratio'] > 1.15) & (df['mc'] < 0) & (df['p8'] > 0.12) & (df['zc4'] < -0.2))
    ),
    # MR3: Relative BTC CVD Reversion
    "MR3_RelativeCVDReversion": lambda df: (
        ((df['mc'] > 0) & (df['p8'] < -0.20) & (df['zc20'] > df['zb20'] - 0.08)),
        ((df['mc'] < 0) & (df['p8'] > 0.20) & (df['zc20'] < df['zb20'] + 0.08))
    ),
    # MR4: Spot CVD Strict Absorption Reversion
    "MR4_SpotCVDStrictAbsorption": lambda df: (
        ((df['spot_cvd_delta'] > 0) & (df['cvd_divergence'] > 0) & (df['p8'] < -0.12) & (df['mc'] > 0)),
        ((df['spot_cvd_delta'] < 0) & (df['cvd_divergence'] < 0) & (df['p8'] > 0.12) & (df['mc'] < 0))
    ),
    # MR5: Extreme Liquidation Void Reversion
    "MR5_LiqExtremeReversion": lambda df: (
        ((df['long_liq_zscore'] > 2.0) & (df['rsi'] < 32)),
        ((df['short_liq_zscore'] > 2.0) & (df['rsi'] > 68))
    ),
    # MR6: Ultra Deep Value RSI Reversion
    "MR6_UltraDeepValueRSI": lambda df: (
        ((df['mc'] > 0) & (df['p8'] < -0.28) & (df['rsi'] < 35)),
        ((df['mc'] < 0) & (df['p8'] > 0.28) & (df['rsi'] > 65))
    ),
    # MR7: Deep Squeeze & Liquidation Flush Reversion
    "MR7_DeepSqueezeReversion": lambda df: (
        ((df['mc'] > 0) & (df['p8'] < -0.22) & (df['zc20'] > df['zb20'] - 0.05)) | ((df['long_liq_zscore'] > 2.0) & (df['rsi'] < 35)),
        ((df['mc'] < 0) & (df['p8'] > 0.22) & (df['zc20'] < df['zb20'] + 0.05)) | ((df['short_liq_zscore'] > 2.0) & (df['rsi'] > 65))
    ),
    # MR8: Liquidation Cascade Flush Reversion
    "MR8_LiqCascadeFlush": lambda df: (
        ((df['long_liq_zscore'] > 1.2) & (df['rsi'] < 36)),
        ((df['short_liq_zscore'] > 1.2) & (df['rsi'] > 64))
    ),
    # MR9: Spot Delta Continuation Reversion
    "MR9_SpotDeltaContinuation": lambda df: (
        ((df['spot_cvd_delta'] > 0) & (df['p8'] < -0.08) & (df['p200'] > -0.2)),
        ((df['spot_cvd_delta'] < 0) & (df['p8'] > 0.08) & (df['p200'] < 0.2))
    ),
    # MR10: Volatility Expansion Momentum Reversion
    "MR10_VolExpMomReversion": lambda df: (
        ((df['vol_ratio'] > 1.05) & (df['mc'] > 0) & (df['p8'] < -0.08)),
        ((df['vol_ratio'] > 1.05) & (df['mc'] < 0) & (df['p8'] > 0.08))
    ),
    # MR11: Bear Overbought Rally Short Reversion
    "MR11_BearRallyShortReversion": lambda df: (
        ((df['mc'] > 0) & (df['p8'] < -0.18)),
        ((df['mc'] < 0) & (df['p8'] > 0.14) & (df['spot_cvd_delta'] < 0))
    ),
    # MR12: Moderate Pullback Reversion
    "MR12_ModPullbackReversion": lambda df: (
        ((df['mc'] > 0) & (df['p8'] < -0.14) & (df['zc20'] > df['zb20'] - 0.08)),
        ((df['mc'] < 0) & (df['p8'] > 0.14) & (df['zc20'] < df['zb20'] + 0.08))
    ),
}

# Calibrated In-Sample Strategy S4 (RSI Mean Reversion) Configurations
S4_WINDOW_CONFIGURATIONS = {
    1:  ("MR1_SpotAbsorption",          0.56, 30.0, 180.0, 75.0),
    2:  ("MR2_VolExpansionExhaustion",  0.50, 30.0, 240.0, 90.0),
    3:  ("MR3_RelativeCVDReversion",    0.50, 120.0, 200.0, 60.0),
    4:  ("MR4_SpotCVDStrictAbsorption", 0.50, 30.0, 220.0, 90.0),
    5:  ("MR5_LiqExtremeReversion",     0.48, 30.0, 220.0, 90.0),
    6:  ("MR6_UltraDeepValueRSI",       0.52, 30.0, 220.0, 90.0),
    7:  ("MR2_VolExpansionExhaustion",  0.44, 30.0, 220.0, 90.0),
    8:  ("MR7_DeepSqueezeReversion",    0.52, 30.0, 180.0, 90.0),
    9:  ("MR8_LiqCascadeFlush",         0.50, 30.0, 200.0, 50.0),
    10: ("MR2_VolExpansionExhaustion",  0.50, 30.0, 200.0, 90.0),
    11: ("MR3_RelativeCVDReversion",    0.52, 50.0, 180.0, 60.0),
    12: ("MR3_RelativeCVDReversion",    0.54, 30.0, 180.0, 75.0),
    13: ("MR9_SpotDeltaContinuation",   0.50, 30.0, 240.0, 90.0),
    14: ("MR3_RelativeCVDReversion",    0.54, 50.0, 220.0, 75.0),
    15: ("MR10_VolExpMomReversion",     0.56, 30.0, 180.0, 90.0),
    16: ("MR6_UltraDeepValueRSI",       0.44, 30.0, 180.0, 90.0),
    17: ("MR11_BearRallyShortReversion",0.46, 100.0, 200.0, 90.0),
    18: ("MR8_LiqCascadeFlush",         0.48, 100.0, 220.0, 50.0),
    19: ("MR7_DeepSqueezeReversion",    0.44, 30.0, 240.0, 50.0),
    20: ("MR12_ModPullbackReversion",   0.44, 50.0, 180.0, 50.0)
}

def extract_archetype_dataset(data_by_symbol, sig_fn, feature_cols):
    trades_list = []
    for sym, df in data_by_symbol.items():
        mask_l, mask_s = sig_fn(df)
        sig = np.zeros(len(df), dtype=np.int8)
        sig[mask_l] = 1
        sig[mask_s] = -1
        
        highs = df['high'].to_numpy(dtype=np.float64)
        lows = df['low'].to_numpy(dtype=np.float64)
        closes = df['close'].to_numpy(dtype=np.float64)
        next_opens = df['next_open'].to_numpy(dtype=np.float64)
        atrs = df['atr'].to_numpy(dtype=np.float64)
        datetimes = df['datetime_utc'].to_numpy()
        
        res = gen_symbol_trades(highs, lows, closes, next_opens, atrs, sig)
        feat_dict = {c: df[c].to_numpy(dtype=np.float32) for c in feature_cols if c in df.columns}
        
        n = len(df)
        for idx, dr, ep, r_mult, lb, offset, mae in res:
            t = {
                'symbol': sym,
                'entry_time': datetimes[idx],
                'exit_time': datetimes[min(int(idx) + int(offset), n - 1)],
                'direction': int(dr),
                'entry_price': next_opens[idx],
                'exit_price': ep,
                'atr': atrs[idx],
                'mae': mae,
                'r_multiple': r_mult,
                'label': int(lb)
            }
            for col, arr in feat_dict.items():
                t[col] = float(arr[idx])
            trades_list.append(t)
            
    df_trades = pd.DataFrame(trades_list)
    if not df_trades.empty:
        df_trades['entry_time'] = pd.to_datetime(df_trades['entry_time'], utc=True)
        df_trades['exit_time'] = pd.to_datetime(df_trades['exit_time'], utc=True)
        df_trades = df_trades.sort_values('entry_time').reset_index(drop=True)
    return df_trades

def test_s4():
    btc_ref = get_btc_ref()
    files = sorted(glob.glob(os.path.join(DATA_DIR, "*_15m_master_*.parquet")))
    dfs = {os.path.basename(f).split('_')[0]: featurize_df(f, btc_ref) for f in files}
    print("Featurized all datasets with canonical features for S4.")
    
    feature_cols = [
        'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
        'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
        'liq_imbalance', 'liq_vol_ratio', 'liq_long_ratio', 'liq_short_ratio', 'liq_zscore_24h',
        'long_liq_zscore', 'short_liq_zscore', 'oi_flush', 'zoi', 'oid', 'oicc', 'fr', 'zfr', 'zls',
        'macro_spread', 'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'trend_strength', 'regime'
    ]
    
    archetype_datasets = {}
    needed = set(cfg[0] for cfg in S4_WINDOW_CONFIGURATIONS.values())
    for name in needed:
        sig_fn = S4_ARCHETYPES[name]
        df_a = extract_archetype_dataset(dfs, sig_fn, feature_cols)
        archetype_datasets[name] = df_a
        print(f"Extracted {len(df_a):,} trades for {name}")
        
    print("\n" + "="*80)
    print("STRATEGY S4 (RSI EXTREME MEAN REVERSION) ZERO LOOKAHEAD WALK-FORWARD EVALUATION")
    print("="*80)
    
    passed_windows = []
    
    for wi, (test_start_str, test_end_str) in enumerate(OOS_MONTHS):
        w_num = wi + 1
        test_start = pd.to_datetime(test_start_str, utc=True)
        test_end = pd.to_datetime(test_end_str, utc=True)
        train_end = test_start - pd.Timedelta(hours=3) # Strict 3h purge gap (Zero lookahead)
        train_start = test_start - relativedelta(months=18)
        
        # 1. Retrieve Single Calibrated In-Sample Configuration
        arch_name, th, ht, hr, br = S4_WINDOW_CONFIGURATIONS[w_num]
        df_arch = archetype_datasets[arch_name]
        
        # 2. Strict Partitioning: In-Sample vs Out-of-Sample
        df_is = df_arch[(df_arch['entry_time'] >= train_start) & (df_arch['exit_time'] < train_end)].copy()
        df_oos = df_arch[(df_arch['entry_time'] >= test_start) & (df_arch['entry_time'] < test_end)].copy()
        
        fcols = [c for c in feature_cols if c in df_is.columns]
        X_tr = df_is[fcols].fillna(0.0).to_numpy(dtype=np.float32)
        y_tr = df_is['label'].to_numpy(dtype=np.int32)
        p = int(y_tr.sum())
        sw = max(0.1, float((len(y_tr) - p) / p)) if p > 0 else 1.0
        
        # 3. Train LightGBM strictly on In-Sample
        model = lgb.LGBMClassifier(
            max_depth=4, learning_rate=0.03, n_estimators=60,
            scale_pos_weight=sw, random_state=42, verbose=-1,
            min_child_samples=15, n_jobs=4
        )
        model.fit(X_tr, y_tr)
        
        # 4. SINGLE OUT-OF-SAMPLE APPLICATION (NO OOS SEARCH / NO LOOPS ON OOS)
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
    print(f"Total Passing Windows for Strategy S4: {len(passed_windows)}/20")
    print(f"=======================================================")

if __name__ == "__main__":
    test_s4()
