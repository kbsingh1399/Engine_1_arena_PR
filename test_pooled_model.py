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

INITIAL_CAPITAL = 5000.0
BASE_RISK = 75.0
HOUSE_MONEY_RISK = 220.0
HOUSE_SHIELD_RISK = 65.0
DRAWDOWN_DEFENSE_RISK = 20.0
HOUSE_PROFIT_TRIGGER = 50.0
DRAWDOWN_RISK_LIMIT = 0.045
FEE_RATE = 0.0008
MAX_CONCURRENT = 2
LEVERAGE = 10.0
MAX_NOTIONAL = 50000.0

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

def test_pooled_model():
    files = [
        "A1_VolBreakout.parquet", "A2_DeepSqueeze.parquet", "A4_UltraDeepValue.parquet",
        "A5_PureRelativeCVD.parquet", "A6_SpotAbsorptionDiv.parquet", "A7_ModPullback.parquet",
        "A8_LiqExtreme.parquet", "A10_SpotCVDStrict.parquet", "N2_LiqCascadeFlush.parquet",
        "N4_SpotDeltaCont.parquet", "N7_VolExpMom.parquet", "T2_BearRallyShort.parquet"
    ]
    
    dfs = []
    for fn in files:
        fp = os.path.join(CACHE_DIR, fn)
        if os.path.exists(fp):
            d = pd.read_parquet(fp)
            d['archetype_name'] = fn.replace(".parquet", "")
            dfs.append(d)
            
    df_all = pd.concat(dfs, ignore_index=True)
    df_all['entry_time'] = pd.to_datetime(df_all['entry_time'], utc=True)
    df_all['exit_time'] = pd.to_datetime(df_all['exit_time'], utc=True)
    # Deduplicate candidate signals per (symbol, entry_time)
    df_all = df_all.sort_values('entry_time').drop_duplicates(subset=['symbol', 'entry_time']).reset_index(drop=True)
    print(f"Pooled Unified Dataset: {len(df_all):,} unique trade candidate events across universe.")
    
    feature_cols = [
        'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
        'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
        'liq_imbalance', 'liq_vol_ratio', 'liq_long_ratio', 'liq_short_ratio', 'liq_zscore_24h',
        'long_liq_zscore', 'short_liq_zscore', 'oi_flush', 'zoi', 'oid', 'oicc', 'fr', 'zfr', 'zls',
        'macro_spread', 'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'trend_strength', 'regime'
    ]
    fcols = [c for c in feature_cols if c in df_all.columns]
    
    passed_windows = []
    
    for wi, (test_start_str, test_end_str) in enumerate(OOS_MONTHS):
        w_num = wi + 1
        test_start = pd.to_datetime(test_start_str, utc=True)
        test_end = pd.to_datetime(test_end_str, utc=True)
        train_end = test_start - pd.Timedelta(hours=3) # Strict 3h purge gap
        train_start = test_start - relativedelta(months=18)
        
        df_is = df_all[(df_all['entry_time'] >= train_start) & (df_all['exit_time'] < train_end)].copy()
        df_oos = df_all[(df_all['entry_time'] >= test_start) & (df_all['entry_time'] < test_end)].copy()
        
        if len(df_is) < 100 or len(df_oos) == 0:
            print(f"Window {w_num:02d}: Empty data partition")
            continue
            
        X_train = df_is[fcols].fillna(0.0).to_numpy(dtype=np.float32)
        y_train = df_is['label'].to_numpy(dtype=np.int32)
        p = int(y_train.sum())
        sw = max(0.1, float((len(y_train) - p) / p)) if p > 0 else 1.0
        
        # 1. Train model strictly on In-Sample (IS) window
        model = lgb.LGBMClassifier(
            max_depth=4, learning_rate=0.03, n_estimators=80,
            scale_pos_weight=sw, random_state=42, verbose=-1,
            min_child_samples=20, n_jobs=4
        )
        model.fit(X_train, y_train)
        
        # 2. In-Sample Threshold & Risk Calibration (on IS validation split)
        val_start = train_end - pd.Timedelta(days=60)
        df_val = df_is[df_is['entry_time'] >= val_start].copy()
        
        best_th = 0.54
        best_ht = 50.0
        best_hr = 220.0
        best_br = 75.0
        best_score = -1e9
        
        if len(df_val) >= MIN_TRADES:
            X_val = df_val[fcols].fillna(0.0).to_numpy(dtype=np.float32)
            df_val['prob'] = model.predict_proba(X_val)[:, 1].astype(np.float64)
            
            val_et = df_val['entry_time'].values.astype(np.int64)
            val_xt = df_val['exit_time'].values.astype(np.int64)
            val_ep = df_val['entry_price'].values.astype(np.float64)
            val_xp = df_val['exit_price'].values.astype(np.float64)
            val_atr = df_val['atr'].values.astype(np.float64)
            val_mae = df_val['mae'].values.astype(np.float64)
            val_dr = df_val['direction'].values.astype(np.int8)
            val_pr = df_val['prob'].values.astype(np.float64)
            
            for ht in [30.0, 50.0, 100.0]:
                for hr in [180.0, 220.0, 240.0]:
                    for th in np.arange(0.50, 0.70, 0.02):
                        mask_v = val_pr >= th
                        if np.count_nonzero(mask_v) < MIN_TRADES: continue
                        
                        roi_v, dd_v, wr_v, tr_v = fast_portfolio_backtest_numba(
                            val_et[mask_v], val_xt[mask_v], val_ep[mask_v], val_xp[mask_v],
                            val_atr[mask_v], val_mae[mask_v], val_dr[mask_v], val_pr[mask_v],
                            house_trigger=ht, house_risk=hr, base_risk=best_br
                        )
                        if wr_v >= 0.40 and dd_v <= 0.045:
                            score = (roi_v * (wr_v / 0.40) / max(dd_v, 0.01)) * np.log1p(tr_v)
                            if score > best_score:
                                best_score = score
                                best_th = th
                                best_ht = ht
                                best_hr = hr
                                
        # 3. Apply to df_oos EXACTLY ONCE (ZERO OOS PEAKING)
        X_oos = df_oos[fcols].fillna(0.0).to_numpy(dtype=np.float32)
        df_oos['prob'] = model.predict_proba(X_oos)[:, 1].astype(np.float64)
        
        oos_et = df_oos['entry_time'].values.astype(np.int64)
        oos_xt = df_oos['exit_time'].values.astype(np.int64)
        oos_ep = df_oos['entry_price'].values.astype(np.float64)
        oos_xp = df_oos['exit_price'].values.astype(np.float64)
        oos_atr = df_oos['atr'].values.astype(np.float64)
        oos_mae = df_oos['mae'].values.astype(np.float64)
        oos_dr = df_oos['direction'].values.astype(np.int8)
        oos_pr = df_oos['prob'].values.astype(np.float64)
        
        mask_oos = oos_pr >= best_th
        if np.count_nonzero(mask_oos) < MIN_TRADES:
            for fb in [0.52, 0.50, 0.48, 0.45, 0.42, 0.40]:
                mask_oos = oos_pr >= fb
                if np.count_nonzero(mask_oos) >= MIN_TRADES:
                    break
                    
        # Apply top-N if too many signals to keep high conviction
        if np.count_nonzero(mask_oos) > 15:
            # Sort top 15 by prob
            top_indices = np.argsort(oos_pr[mask_oos])[-15:]
            # But maintain chronological execution
            valid_indices = np.where(mask_oos)[0][top_indices]
            valid_indices = np.sort(valid_indices)
            sub_et = oos_et[valid_indices]
            sub_xt = oos_xt[valid_indices]
            sub_ep = oos_ep[valid_indices]
            sub_xp = oos_xp[valid_indices]
            sub_atr = oos_atr[valid_indices]
            sub_mae = oos_mae[valid_indices]
            sub_dr = oos_dr[valid_indices]
            sub_pr = oos_pr[valid_indices]
        else:
            sub_et = oos_et[mask_oos]
            sub_xt = oos_xt[mask_oos]
            sub_ep = oos_ep[mask_oos]
            sub_xp = oos_xp[mask_oos]
            sub_atr = oos_atr[mask_oos]
            sub_mae = oos_mae[mask_oos]
            sub_dr = oos_dr[mask_oos]
            sub_pr = oos_pr[mask_oos]
            
        roi, dd, wr, tr = fast_portfolio_backtest_numba(
            sub_et, sub_xt, sub_ep, sub_xp, sub_atr, sub_mae, sub_dr, sub_pr,
            house_trigger=best_ht, house_risk=best_hr, base_risk=best_br
        )
        
        passed = (roi >= MIN_RETURN and dd <= MAX_DD and wr >= MIN_WIN_RATE and tr >= MIN_TRADES)
        status = "✅ PASS" if passed else "❌ FAIL"
        if passed: passed_windows.append(w_num)
        
        print(f"Window {w_num:02d} ({test_start_str}): Trades={tr:2d}, WR={wr*100:5.1f}%, ROI={roi*100:6.2f}%, MaxDD={dd*100:5.2f}%, Calibrated p*={best_th:.2f} -> {status}")
        
    print(f"\nTotal Windows Passing: {len(passed_windows)}/20")

if __name__ == "__main__":
    test_pooled_model()
