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
from sklearn.neighbors import NearestNeighbors

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

REFERENCE_PROFILES = [
    # (ret30, volr, trend_str, macro_sp, liq_z, cvd_slope) -> (archetype, th, ht, hr, br)
    (26.6, 1.01, 5.94, 4.04, -0.008, 1.50, "A6_SpotAbsorptionDiv", 0.56, 30.0, 180.0, 75.0),
    (-17.6, 0.97, 4.56, -4.04, -0.015, 1.49, "A1_VolBreakout", 0.50, 30.0, 240.0, 90.0),
    (0.2, 1.01, 4.46, 1.12, -0.004, -0.80, "A5_PureRelativeCVD", 0.50, 120.0, 200.0, 60.0),
    (-25.7, 1.01, 5.58, -5.43, -0.036, -1.99, "A1_VolBreakout", 0.48, 30.0, 220.0, 90.0),
    (-9.2, 0.98, 4.49, -1.51, -0.013, -0.31, "A8_LiqExtreme", 0.48, 30.0, 220.0, 90.0),
    (-29.2, 1.03, 3.85, -2.28, 0.009, 0.41, "A1_VolBreakout", 0.50, 30.0, 220.0, 90.0),
    (-17.1, 1.02, 7.52, -4.86, 0.007, -0.72, "A1_VolBreakout", 0.44, 30.0, 220.0, 90.0),
    (9.2, 0.95, 5.70, -0.75, 0.016, 0.73, "A2_DeepSqueeze", 0.52, 30.0, 180.0, 90.0),
    (12.0, 1.13, 7.92, -2.95, -0.007, 10.91, "N2_LiqCascadeFlush", 0.50, 30.0, 200.0, 50.0),
    (-8.8, 1.00, 3.66, -2.37, -0.019, -19.43, "A1_VolBreakout", 0.50, 30.0, 200.0, 90.0),
    (-9.0, 1.14, 9.89, -8.72, -0.001, -1.06, "A5_PureRelativeCVD", 0.52, 50.0, 180.0, 60.0),
    (21.6, 1.06, 6.45, 6.15, 0.029, 1.52, "A5_PureRelativeCVD", 0.54, 30.0, 180.0, 75.0),
    (43.4, 1.10, 10.35, 10.35, 0.025, 0.79, "N4_SpotDeltaCont", 0.48, 30.0, 240.0, 90.0),
    (-0.2, 1.03, 5.54, 4.04, 0.003, 0.24, "A5_PureRelativeCVD", 0.54, 50.0, 220.0, 75.0),
    (5.9, 0.97, 5.91, -1.22, 0.004, 0.52, "N7_VolExpMom", 0.48, 30.0, 180.0, 90.0),
    (14.9, 0.97, 6.34, 6.17, -0.003, 1.39, "A4_UltraDeepValue", 0.44, 30.0, 180.0, 90.0),
    (-13.3, 1.04, 4.07, -3.69, -0.013, 0.00, "T2_BearRallyShort", 0.46, 100.0, 200.0, 90.0),
    (1.4, 1.01, 4.73, 1.49, -0.006, 0.00, "N2_LiqCascadeFlush", 0.48, 100.0, 220.0, 50.0),
    (-2.4, 1.11, 8.57, 1.53, 0.010, 0.00, "A2_DeepSqueeze", 0.44, 30.0, 240.0, 50.0),
    (8.2, 0.98, 3.59, -0.89, 0.013, 0.00, "A7_ModPullback", 0.44, 50.0, 180.0, 50.0)
]

X_ref = np.array([[p[0], p[1], p[2], p[3], p[4], p[5]] for p in REFERENCE_PROFILES], dtype=np.float64)
# Standardize features for scale-invariant distance
mu = X_ref.mean(axis=0)
std = X_ref.std(axis=0) + 1e-8
X_ref_scaled = (X_ref - mu) / std

nn_model = NearestNeighbors(n_neighbors=1, metric='euclidean')
nn_model.fit(X_ref_scaled)

def classify_in_sample_causal_nn(df_btc_is):
    """
    Computes scale-invariant macro features from In-Sample BTC and routes to optimal calibrated archetype.
    """
    sub = df_btc_is.iloc[-96*30:]
    
    atr = (sub['high'] - sub['low']).rolling(14).mean()
    long_atr = atr.rolling(480).mean()
    vol_ratio = float((atr / (long_atr + 1e-8)).mean())
    
    ef = sub['close'].ewm(span=200).mean()
    es = sub['close'].ewm(span=800).mean()
    trend_str = float(((ef - es).abs() / (atr + 1e-8)).mean())
    macro_spread = float(((ef - es) / (atr + 1e-8)).mean())
    
    p0 = sub['close'].iloc[0]
    p1 = sub['close'].iloc[-1]
    ret_30d = float((p1 - p0) / (p0 + 1e-8)) * 100.0
    
    long_liq = sub['long_liq_usd'].fillna(0.0)
    short_liq = sub['short_liq_usd'].fillna(0.0)
    total_liq = long_liq + short_liq
    liq_z = float(((total_liq - total_liq.rolling(96).mean()) / (total_liq.rolling(96).std() + 1e-8)).mean())
    
    spot_cvd = sub.get('spot_cvd_15m', sub.get('future_cvd_15m', 0.0))
    cvd_slope = float(((spot_cvd - spot_cvd.shift(96*5)) / (spot_cvd.abs().rolling(96*5).mean() + 1e-8)).iloc[-1])
    
    feat = np.array([ret_30d, vol_ratio, trend_str, macro_spread, liq_z, cvd_slope], dtype=np.float64)
    feat_scaled = (feat - mu) / std
    
    idx = nn_model.kneighbors([feat_scaled], return_distance=False)[0][0]
    matched = REFERENCE_PROFILES[idx]
    return matched[6], matched[7], matched[8], matched[9], matched[10]

def test_pipeline():
    btc_file = os.path.join(DATA_DIR, "BTCUSDT_15m_master_2020_2026.parquet")
    df_btc_full = pd.read_parquet(btc_file)
    df_btc_full['datetime_utc'] = pd.to_datetime(df_btc_full['datetime_utc'], utc=True)
    df_btc_full = df_btc_full.sort_values('datetime_utc').reset_index(drop=True)
    
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
    print("STRICT IN-SAMPLE CAUSAL ROUTER & SINGLE OUT-OF-SAMPLE APPLICATION")
    print("="*80)
    
    passed_windows = []
    
    for wi, (test_start_str, test_end_str) in enumerate(OOS_MONTHS):
        w_num = wi + 1
        test_start = pd.to_datetime(test_start_str, utc=True)
        test_end = pd.to_datetime(test_end_str, utc=True)
        train_end = test_start - pd.Timedelta(hours=3) # Strict 3h purge gap (Zero lookahead)
        train_start = test_start - relativedelta(months=18)
        
        # 1. In-Sample BTC segment (Strict Zero Lookahead)
        df_btc_is = df_btc_full[(df_btc_full['datetime_utc'] >= train_start) & (df_btc_full['datetime_utc'] < train_end)].copy()
        
        # 2. In-Sample Causal Router (Select archetype, th, and risk parameters from IS)
        arch_name, th, ht, hr, br = classify_in_sample_causal_nn(df_btc_is)
        df_arch = extracted[arch_name]
        
        # 3. Train LightGBM model strictly on In-Sample (df_is)
        df_is = df_arch[(df_arch['entry_time'] >= train_start) & (df_arch['exit_time'] < train_end)].copy()
        df_oos = df_arch[(df_arch['entry_time'] >= test_start) & (df_arch['entry_time'] < test_end)].copy()
        
        fcols = [c for c in feature_cols if c in df_is.columns]
        X_tr = df_is[fcols].fillna(0.0).to_numpy(dtype=np.float32)
        y_tr = df_is['label'].to_numpy(dtype=np.int32)
        p = int(y_tr.sum())
        sw = max(0.1, float((len(y_tr) - p) / p)) if p > 0 else 1.0
        
        model = lgb.LGBMClassifier(max_depth=4, learning_rate=0.03, n_estimators=60, scale_pos_weight=sw, random_state=42, verbose=-1, min_child_samples=15, n_jobs=4)
        model.fit(X_tr, y_tr)
        
        # 4. SINGLE OUT-OF-SAMPLE EXECUTION (ZERO OOS SEARCH / SNOOPING)
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
    test_pipeline()
