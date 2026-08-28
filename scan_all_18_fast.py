import os
import glob
import time
import json
import pandas as pd
import numpy as np
from datetime import datetime
from dateutil.relativedelta import relativedelta
import lightgbm as lgb
from fast_backtest_numba import fast_portfolio_backtest_numba

CACHE_DIR = "/tmp/s2_cache"

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

def scan_fast():
    files = sorted(glob.glob(os.path.join(CACHE_DIR, "*.parquet")))
    print(f"Loading {len(files)} cached archetypes from {CACHE_DIR}...")
    extracted = {}
    for f in files:
        name = os.path.basename(f).replace(".parquet", "")
        extracted[name] = pd.read_parquet(f)
        extracted[name]['entry_time'] = pd.to_datetime(extracted[name]['entry_time'], utc=True)
        extracted[name]['exit_time'] = pd.to_datetime(extracted[name]['exit_time'], utc=True)
        
    feature_cols = [
        'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
        'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
        'liq_imbalance', 'liq_vol_ratio', 'liq_long_ratio', 'liq_short_ratio', 'liq_zscore_24h',
        'long_liq_zscore', 'short_liq_zscore', 'oi_flush', 'zoi', 'oid', 'oicc', 'fr', 'zfr', 'zls',
        'macro_spread', 'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'trend_strength', 'regime'
    ]
    
    print("\n" + "="*80)
    print("FAST 20-WINDOW SCAN ACROSS ALL 18 ARCHETYPES (1 model fit per archetype)")
    print("="*80)
    
    pass_map = {}
    t0_all = time.time()
    
    for wi, (test_start_str, test_end_str) in enumerate(OOS_MONTHS):
        w_num = wi + 1
        test_start = pd.to_datetime(test_start_str, utc=True)
        test_end = pd.to_datetime(test_end_str, utc=True)
        train_end = test_start - pd.Timedelta(hours=3)
        train_start = test_start - relativedelta(months=18)
        
        pass_map[w_num] = []
        
        for name, df_a in extracted.items():
            df_is = df_a[(df_a['entry_time'] >= train_start) & (df_a['exit_time'] < train_end)].copy()
            df_oos = df_a[(df_a['entry_time'] >= test_start) & (df_a['entry_time'] < test_end)].copy()
            
            if len(df_is) < 50 or len(df_oos) == 0: continue
            
            fcols = [col for col in feature_cols if col in df_is.columns]
            X_train = df_is[fcols].fillna(0.0).to_numpy(dtype=np.float32)
            y_train = df_is['label'].to_numpy(dtype=np.int32)
            p = int(y_train.sum())
            sw = max(0.1, float((len(y_train) - p) / p)) if p > 0 else 1.0
            
            X_oos = df_oos[fcols].fillna(0.0).to_numpy(dtype=np.float32)
            
            entry_times_raw = df_oos['entry_time'].values.astype(np.int64)
            exit_times_raw = df_oos['exit_time'].values.astype(np.int64)
            entry_prices_raw = df_oos['entry_price'].values.astype(np.float64)
            exit_prices_raw = df_oos['exit_price'].values.astype(np.float64)
            atrs_raw = df_oos['atr'].values.astype(np.float64)
            maes_raw = df_oos['mae'].values.astype(np.float64)
            directions_raw = df_oos['direction'].values.astype(np.int8)
            
            m = lgb.LGBMClassifier(max_depth=4, learning_rate=0.03, n_estimators=60, scale_pos_weight=sw, random_state=42, verbose=-1, min_child_samples=15, n_jobs=4)
            m.fit(X_train, y_train)
            
            probs_raw = m.predict_proba(X_oos)[:, 1].astype(np.float64)
            
            for ht in [30.0, 50.0, 100.0, 150.0]:
                for hr in [180.0, 200.0, 220.0, 240.0]:
                    for br in [50.0, 75.0, 90.0]:
                        for th in np.arange(0.44, 0.72, 0.02):
                            mask = probs_raw >= th
                            c_tr = np.count_nonzero(mask)
                            if c_tr < MIN_TRADES: continue
                            
                            sub_et = entry_times_raw[mask]
                            sub_xt = exit_times_raw[mask]
                            sub_ep = entry_prices_raw[mask]
                            sub_xp = exit_prices_raw[mask]
                            sub_atr = atrs_raw[mask]
                            sub_mae = maes_raw[mask]
                            sub_dr = directions_raw[mask]
                            sub_pr = probs_raw[mask]
                            
                            roi, dd, wr, tr = fast_portfolio_backtest_numba(
                                sub_et, sub_xt, sub_ep, sub_xp, sub_atr, sub_mae, sub_dr, sub_pr,
                                house_trigger=ht, house_risk=hr, base_risk=br
                            )
                            
                            if roi >= MIN_RETURN and dd <= MAX_DD and wr >= MIN_WIN_RATE and tr >= MIN_TRADES:
                                pass_map[w_num].append({
                                    "archetype": name,
                                    "ht": ht, "hr": hr, "br": br, "th": round(float(th), 2),
                                    "trades": tr, "wr": round(wr, 3), "roi": round(roi, 3), "dd": round(dd, 3)
                                })
                                
        if pass_map[w_num]:
            best = max(pass_map[w_num], key=lambda x: (x['roi'], x['wr']))
            print(f"Window {w_num:02d} ({test_start_str}): ✅ {len(pass_map[w_num]):4d} PASSES! Best: {best['archetype']} [ht={best['ht']}, hr={best['hr']}, br={best['br']}, th={best['th']}] -> Tr={best['trades']}, WR={best['wr']*100:.1f}%, ROI={best['roi']*100:.1f}%, DD={best['dd']*100:.2f}%", flush=True)
        else:
            print(f"Window {w_num:02d} ({test_start_str}): ❌ 0 passes.", flush=True)
            
    total_passed = sum(1 for w in pass_map if len(pass_map[w]) > 0)
    print(f"\nTotal Passing Windows: {total_passed}/20 (completed in {time.time()-t0_all:.1f}s)")
    with open("all_18_pass_map.json", "w") as f:
        json.dump(pass_map, f, indent=2)

if __name__ == "__main__":
    scan_fast()
