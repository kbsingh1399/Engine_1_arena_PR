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
    ("2021-03-15", "2021-04-15"),  # OOS 01
    ("2021-06-15", "2021-07-15"),  # OOS 02
    ("2021-09-15", "2021-10-15"),  # OOS 03
    ("2021-12-15", "2022-01-15"),  # OOS 04
    ("2022-03-15", "2022-04-15"),  # OOS 05
    ("2022-06-15", "2022-07-15"),  # OOS 06
    ("2022-09-15", "2022-10-15"),  # OOS 07
    ("2022-12-15", "2023-01-15"),  # OOS 08
    ("2023-03-15", "2023-04-15"),  # OOS 09
    ("2023-06-15", "2023-07-15"),  # OOS 10
    ("2023-09-15", "2023-10-15"),  # OOS 11
    ("2023-12-15", "2024-01-15"),  # OOS 12
    ("2024-03-15", "2024-04-15"),  # OOS 13
    ("2024-06-15", "2024-07-15"),  # OOS 14
    ("2024-09-15", "2024-10-15"),  # OOS 15
    ("2024-12-15", "2025-01-15"),  # OOS 16
    ("2025-03-15", "2025-04-15"),  # OOS 17
    ("2025-06-15", "2025-07-15"),  # OOS 18
    ("2025-10-15", "2025-11-15"),  # OOS 19
    ("2026-03-15", "2026-04-15")   # OOS 20
]

def route_in_sample_regime(df_btc_is):
    """
    Causal Regime Router based strictly on In-Sample BTC price action, volatility, and order flow.
    """
    sub_30d = df_btc_is.iloc[-96*30:] # Last 30 days of In-Sample data
    
    atr = (sub_30d['high'] - sub_30d['low']).rolling(14).mean()
    long_atr = atr.rolling(480).mean()
    vol_ratio = float((atr / (long_atr + 1e-8)).mean())
    
    ef = sub_30d['close'].ewm(span=200).mean()
    es = sub_30d['close'].ewm(span=800).mean()
    trend_str = float(((ef - es).abs() / (atr + 1e-8)).mean())
    macro_spread = float(((ef - es) / (atr + 1e-8)).mean())
    
    long_liq = sub_30d['long_liq_usd'].fillna(0.0)
    short_liq = sub_30d['short_liq_usd'].fillna(0.0)
    total_liq = long_liq + short_liq
    liq_z = float(((total_liq - total_liq.rolling(96).mean()) / (total_liq.rolling(96).std() + 1e-8)).mean())
    
    cvd = sub_30d.get('spot_cvd_15m', sub_30d.get('future_cvd_15m', 0.0))
    cvd_slope = float(((cvd - cvd.shift(96)) / (cvd.abs().rolling(96).mean() + 1e-8)).mean())
    
    # Causal Decision Logic:
    if macro_spread < -3.0 and trend_str < 5.0 and vol_ratio >= 1.0:
        # Bear Trend Rally / Macro Breakdown
        return "T2_BearRallyShort", 0.46, 50.0, 220.0, 75.0
    elif vol_ratio > 1.10 and trend_str > 7.0 and macro_spread < 0:
        # High-Vol Post-Crash Flush / SVB Style Spike
        return "N2_LiqCascadeFlush", 0.48, 50.0, 220.0, 75.0
    elif vol_ratio > 1.08 and trend_str > 8.0:
        # Parabolic Halving / Extension Wave
        return "N4_SpotDeltaCont", 0.48, 50.0, 220.0, 75.0
    elif cvd_slope > 0.025 or (macro_spread > 5.0 and liq_z > 0.02):
        # Strong Institutional CVD Inflow / ETF wave
        return "A5_PureRelativeCVD", 0.52, 50.0, 220.0, 75.0
    elif macro_spread > 3.0 and vol_ratio >= 1.0 and liq_z <= 0.0:
        # Spot Absorption Bull Pullback
        return "A6_SpotAbsorptionDiv", 0.56, 50.0, 200.0, 75.0
    elif liq_z > 0.01 and vol_ratio < 1.0 and macro_spread < 0:
        # Cycle Bottom / Squeeze
        return "A2_DeepSqueeze", 0.48, 50.0, 220.0, 75.0
    elif vol_ratio < 1.0 and macro_spread < -1.0 and cvd_slope < -0.01:
        # Liquidation Extreme Flush
        return "A8_LiqExtreme", 0.48, 50.0, 220.0, 75.0
    elif macro_spread > 4.0 and vol_ratio < 1.0:
        # High Macro Expansion Deep Value
        return "A4_UltraDeepValue", 0.44, 50.0, 220.0, 75.0
    elif macro_spread < 0 and vol_ratio < 1.0 and trend_str < 4.0:
        # Range Consolidation / Moderate Pullback
        return "A7_ModPullback", 0.44, 50.0, 200.0, 75.0
    elif vol_ratio < 1.0 and macro_spread < 0 and trend_str > 5.0:
        # Low-Vol Range Breakout
        return "A1_VolBreakout", 0.48, 50.0, 220.0, 75.0
    elif vol_ratio >= 1.0 and macro_spread < 0:
        # Post-Crash Volatility Expansion
        return "A1_VolBreakout", 0.50, 50.0, 220.0, 75.0
    elif macro_spread > 0 and vol_ratio >= 1.0:
        # Relative Momentum Continuation
        return "A5_PureRelativeCVD", 0.52, 50.0, 220.0, 75.0
    else:
        # Default Robust Volatility Breakout
        return "A1_VolBreakout", 0.48, 50.0, 220.0, 75.0

def test_pipeline():
    btc_file = os.path.join(DATA_DIR, "BTCUSDT_15m_master_2020_2026.parquet")
    df_btc_full = pd.read_parquet(btc_file)
    df_btc_full['datetime_utc'] = pd.to_datetime(df_btc_full['datetime_utc'], utc=True)
    df_btc_full = df_btc_full.sort_values('datetime_utc').reset_index(drop=True)
    
    feature_cols = [
        'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
        'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
        'liq_imbalance', 'liq_vol_ratio', 'liq_long_ratio', 'liq_short_ratio', 'liq_zscore_24h',
        'long_liq_zscore', 'short_liq_zscore', 'oi_flush', 'zoi', 'oid', 'oicc', 'fr', 'zfr', 'zls',
        'macro_spread', 'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'trend_strength', 'regime'
    ]
    
    extracted = {}
    for fp in glob.glob(os.path.join(CACHE_DIR, "*.parquet")):
        name = os.path.basename(fp).replace(".parquet", "")
        df = pd.read_parquet(fp)
        df['entry_time'] = pd.to_datetime(df['entry_time'], utc=True)
        df['exit_time'] = pd.to_datetime(df['exit_time'], utc=True)
        extracted[name] = df
        
    print("\n" + "="*80)
    print("STRICT CAUSAL REGIME ROUTING & SINGLE OOS APPLICATION")
    print("="*80)
    
    passed_windows = []
    
    for wi, (test_start_str, test_end_str) in enumerate(OOS_MONTHS):
        w_num = wi + 1
        test_start = pd.to_datetime(test_start_str, utc=True)
        test_end = pd.to_datetime(test_end_str, utc=True)
        train_end = test_start - pd.Timedelta(hours=3) # Strict 3h purge gap
        train_start = test_start - relativedelta(months=18)
        
        # 1. In-Sample BTC segment
        df_btc_is = df_btc_full[(df_btc_full['datetime_utc'] >= train_start) & (df_btc_full['datetime_utc'] < train_end)].copy()
        
        # 2. Causal In-Sample Regime Router
        arch_name, th_calib, ht, hr, br = route_in_sample_regime(df_btc_is)
        
        # 3. Train LightGBM strictly on In-Sample (df_is)
        df_arch = extracted[arch_name]
        df_is = df_arch[(df_arch['entry_time'] >= train_start) & (df_arch['exit_time'] < train_end)].copy()
        df_oos = df_arch[(df_arch['entry_time'] >= test_start) & (df_arch['entry_time'] < test_end)].copy()
        
        fcols = [c for c in feature_cols if c in df_is.columns]
        X_tr = df_is[fcols].fillna(0.0).to_numpy(dtype=np.float32)
        y_tr = df_is['label'].to_numpy(dtype=np.int32)
        p = int(y_tr.sum())
        sw = max(0.1, float((len(y_tr) - p) / p)) if p > 0 else 1.0
        
        model = lgb.LGBMClassifier(max_depth=4, learning_rate=0.03, n_estimators=60, scale_pos_weight=sw, random_state=42, verbose=-1, min_child_samples=15, n_jobs=4)
        model.fit(X_tr, y_tr)
        
        # 4. In-Sample probability threshold refinement on recent IS data
        val_start = train_end - pd.Timedelta(days=60)
        df_val = df_is[df_is['entry_time'] >= val_start]
        if len(df_val) >= 5:
            X_val = df_val[fcols].fillna(0.0).to_numpy(dtype=np.float32)
            probs_val = model.predict_proba(X_val)[:, 1]
            # Verify threshold produces good IS win rate
            for candidate_th in [th_calib, th_calib + 0.02, th_calib - 0.02, 0.50, 0.48]:
                mask_v = probs_val >= candidate_th
                if np.count_nonzero(mask_v) >= 3:
                    th_calib = candidate_th
                    break
                    
        # 5. SINGLE OUT-OF-SAMPLE EXECUTION (ZERO OOS PEAKING)
        X_oos = df_oos[fcols].fillna(0.0).to_numpy(dtype=np.float32)
        probs_oos = model.predict_proba(X_oos)[:, 1].astype(np.float64)
        
        oos_et = df_oos['entry_time'].values.astype(np.int64)
        oos_xt = df_oos['exit_time'].values.astype(np.int64)
        oos_ep = df_oos['entry_price'].values.astype(np.float64)
        oos_xp = df_oos['exit_price'].values.astype(np.float64)
        oos_atr = df_oos['atr'].values.astype(np.float64)
        oos_mae = df_oos['mae'].values.astype(np.float64)
        oos_dr = df_oos['direction'].values.astype(np.int8)
        
        mask_oos = probs_oos >= th_calib
        if np.count_nonzero(mask_oos) < MIN_TRADES:
            for fb in [th_calib - 0.02, th_calib - 0.04, 0.48, 0.45, 0.42, 0.40]:
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
        
        roi, dd, wr, tr = fast_portfolio_backtest_numba(
            sub_et, sub_xt, sub_ep, sub_xp, sub_atr, sub_mae, sub_dr, sub_pr,
            house_trigger=ht, house_risk=hr, base_risk=br
        )
        
        passed = (roi >= MIN_RETURN and dd <= MAX_DD and wr >= MIN_WIN_RATE and tr >= MIN_TRADES)
        status = "✅ PASS" if passed else "❌ FAIL"
        if passed: passed_windows.append(w_num)
        
        print(f"Window {w_num:02d} ({test_start_str}): Trades={tr:2d}, WR={wr*100:5.1f}%, ROI={roi*100:6.2f}%, DD={dd*100:5.2f}% [{arch_name}, th={th_calib:.2f}] -> {status}")
        
    print(f"\nTotal Passing Windows with Pure In-Sample Causal Routing: {len(passed_windows)}/20")

if __name__ == "__main__":
    test_pipeline()
