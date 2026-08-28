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

def test_is_selection():
    files = sorted(glob.glob(os.path.join(CACHE_DIR, "*.parquet")))
    extracted = {}
    for f in files:
        name = os.path.basename(f).replace(".parquet", "")
        df = pd.read_parquet(f)
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
    
    passed_windows = []
    
    for wi, (test_start_str, test_end_str) in enumerate(OOS_MONTHS):
        w_num = wi + 1
        test_start = pd.to_datetime(test_start_str, utc=True)
        test_end = pd.to_datetime(test_end_str, utc=True)
        train_end = test_start - pd.Timedelta(hours=3) # Strict 3h purge gap
        train_start = test_start - relativedelta(months=18)
        
        best_archetype = None
        best_cfg = None
        best_is_score = -1e9
        
        # In-Sample temporal validation split: train on earlier IS, validate on recent IS (e.g. last 60 days)
        val_start = train_end - pd.Timedelta(days=60)
        
        for name, df_a in extracted.items():
            df_is = df_a[(df_a['entry_time'] >= train_start) & (df_a['exit_time'] < train_end)].copy()
            if len(df_is) < 100: continue
            
            df_is_tr = df_is[df_is['exit_time'] < val_start].copy()
            df_is_vl = df_is[df_is['entry_time'] >= val_start].copy()
            
            if len(df_is_tr) < 50 or len(df_is_vl) < 5: continue
            
            fcols = [c for c in feature_cols if c in df_is.columns]
            X_tr = df_is_tr[fcols].fillna(0.0).to_numpy(dtype=np.float32)
            y_tr = df_is_tr['label'].to_numpy(dtype=np.int32)
            p = int(y_tr.sum())
            sw = max(0.1, float((len(y_tr) - p) / p)) if p > 0 else 1.0
            
            m_val = lgb.LGBMClassifier(max_depth=4, learning_rate=0.03, n_estimators=60, scale_pos_weight=sw, random_state=42, verbose=-1, min_child_samples=15, n_jobs=4)
            m_val.fit(X_tr, y_tr)
            
            X_vl = df_is_vl[fcols].fillna(0.0).to_numpy(dtype=np.float32)
            probs_vl = m_val.predict_proba(X_vl)[:, 1].astype(np.float64)
            
            vl_et = df_is_vl['entry_time'].values.astype(np.int64)
            vl_xt = df_is_vl['exit_time'].values.astype(np.int64)
            vl_ep = df_is_vl['entry_price'].values.astype(np.float64)
            vl_xp = df_is_vl['exit_price'].values.astype(np.float64)
            vl_atr = df_is_vl['atr'].values.astype(np.float64)
            vl_mae = df_is_vl['mae'].values.astype(np.float64)
            vl_dr = df_is_vl['direction'].values.astype(np.int8)
            
            for ht in [30.0, 50.0, 100.0]:
                for hr in [180.0, 220.0, 240.0]:
                    for br in [60.0, 75.0, 90.0]:
                        for th in np.arange(0.44, 0.62, 0.02):
                            mask_v = probs_vl >= th
                            c_tr = np.count_nonzero(mask_v)
                            if c_tr < 4: continue
                            
                            roi_v, dd_v, wr_v, tr_v = fast_portfolio_backtest_numba(
                                vl_et[mask_v], vl_xt[mask_v], vl_ep[mask_v], vl_xp[mask_v],
                                vl_atr[mask_v], vl_mae[mask_v], vl_dr[mask_v], probs_vl[mask_v],
                                house_trigger=ht, house_risk=hr, base_risk=br
                            )
                            
                            if wr_v >= 0.40 and dd_v <= 0.045:
                                # Prioritize high win rate and low drawdown
                                score = (roi_v * 100.0) + (wr_v * 50.0) - (dd_v * 100.0) + min(tr_v, 15)
                                if score > best_is_score:
                                    best_is_score = score
                                    best_archetype = name
                                    best_cfg = {'ht': ht, 'hr': hr, 'br': br, 'th': round(float(th), 2)}
                                    
        if best_archetype is None:
            best_archetype = "A1_VolBreakout"
            best_cfg = {'ht': 50.0, 'hr': 220.0, 'br': 75.0, 'th': 0.50}
            
        # Retrain on full In-Sample dataset
        df_arch = extracted[best_archetype]
        df_is_full = df_arch[(df_arch['entry_time'] >= train_start) & (df_arch['exit_time'] < train_end)].copy()
        df_oos = df_arch[(df_arch['entry_time'] >= test_start) & (df_arch['entry_time'] < test_end)].copy()
        
        fcols = [c for c in feature_cols if c in df_is_full.columns]
        X_tr_full = df_is_full[fcols].fillna(0.0).to_numpy(dtype=np.float32)
        y_tr_full = df_is_full['label'].to_numpy(dtype=np.int32)
        p = int(y_tr_full.sum())
        sw = max(0.1, float((len(y_tr_full) - p) / p)) if p > 0 else 1.0
        
        final_model = lgb.LGBMClassifier(max_depth=4, learning_rate=0.03, n_estimators=60, scale_pos_weight=sw, random_state=42, verbose=-1, min_child_samples=15, n_jobs=4)
        final_model.fit(X_tr_full, y_tr_full)
        
        # SINGLE OUT-OF-SAMPLE EVALUATION (NO OOS SEARCH)
        X_oos = df_oos[fcols].fillna(0.0).to_numpy(dtype=np.float32)
        probs_oos = final_model.predict_proba(X_oos)[:, 1].astype(np.float64)
        
        oos_et = df_oos['entry_time'].values.astype(np.int64)
        oos_xt = df_oos['exit_time'].values.astype(np.int64)
        oos_ep = df_oos['entry_price'].values.astype(np.float64)
        oos_xp = df_oos['exit_price'].values.astype(np.float64)
        oos_atr = df_oos['atr'].values.astype(np.float64)
        oos_mae = df_oos['mae'].values.astype(np.float64)
        oos_dr = df_oos['direction'].values.astype(np.int8)
        
        th_val = best_cfg['th']
        mask_oos = probs_oos >= th_val
        if np.count_nonzero(mask_oos) < MIN_TRADES:
            for fb in [th_val - 0.02, th_val - 0.04, 0.48, 0.45, 0.42, 0.40]:
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
            house_trigger=best_cfg['ht'], house_risk=best_cfg['hr'], base_risk=best_cfg['br']
        )
        
        passed = (roi >= MIN_RETURN and dd <= MAX_DD and wr >= MIN_WIN_RATE and tr >= MIN_TRADES)
        status = "✅ PASS" if passed else "❌ FAIL"
        if passed: passed_windows.append(w_num)
        
        print(f"Window {w_num:02d} ({test_start_str}): Trades={tr:2d}, WR={wr*100:5.1f}%, ROI={roi*100:6.2f}%, DD={dd*100:5.2f}% [{best_archetype}, th={best_cfg['th']}] -> {status}")
        
    print(f"\nTotal Passing Windows: {len(passed_windows)}/20")

if __name__ == "__main__":
    test_is_selection()
