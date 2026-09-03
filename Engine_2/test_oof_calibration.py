"""
Test 3-Fold Out-Of-Fold In-Sample Calibration for Window 01
"""
import os
import sys
import numpy as np
import pandas as pd
import lightgbm as lgb

sys.path.append(os.path.abspath("Engine_2"))
from s1_liquidation_cascade import (
    load_and_preprocess_data,
    ARCHETYPE_FUNCTIONS,
    extract_archetype_dataset,
    get_oos_windows,
    fast_portfolio_backtest_numba
)

feature_cols = [
    'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
    'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
    'liq_imbalance', 'liq_vol_ratio', 'liq_long_ratio', 'liq_short_ratio', 'liq_zscore_24h',
    'long_liq_zscore', 'short_liq_zscore', 'oi_flush', 'zoi', 'oid', 'oicc', 'fr', 'zfr', 'zls',
    'macro_spread', 'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'trend_strength', 'regime'
]

data_by_symbol = load_and_preprocess_data()
windows = get_oos_windows()
w = windows[0] # Window 1
train_start = w['train_start']
train_end_purged = w['train_end'] - pd.Timedelta(hours=3)
test_start = w['test_start']
test_end = w['test_end']

print(f"\nEvaluating In-Sample 18-month OOF Performance for Window 1 ({train_start} to {train_end_purged}):")

results = []

for name, sig_fn in ARCHETYPE_FUNCTIONS.items():
    df_arch = extract_archetype_dataset(data_by_symbol, sig_fn, feature_cols)
    df_is = df_arch[(df_arch['entry_time'] >= train_start) & (df_arch['exit_time'] < train_end_purged)].copy()
    if len(df_is) < 60:
        continue
        
    fcols = [c for c in feature_cols if c in df_is.columns]
    X = df_is[fcols].fillna(0.0).to_numpy(dtype=np.float32)
    y = df_is['label'].to_numpy(dtype=np.int32)
    
    # 3-fold temporal splits
    n = len(df_is)
    fold_size = n // 3
    probs_oof = np.zeros(n, dtype=np.float64)
    
    for f in range(3):
        val_idx = np.arange(f * fold_size, min((f + 1) * fold_size, n))
        train_idx = np.setdiff1d(np.arange(n), val_idx)
        
        p = int(y[train_idx].sum())
        sw = max(0.1, float((len(train_idx) - p) / p)) if p > 0 else 1.0
        
        model = lgb.LGBMClassifier(
            max_depth=4, learning_rate=0.03, n_estimators=50,
            scale_pos_weight=sw, random_state=42, verbose=-1,
            min_child_samples=15, n_jobs=2
        )
        model.fit(X[train_idx], y[train_idx])
        probs_oof[val_idx] = model.predict_proba(X[val_idx])[:, 1]
        
    # Evaluate across IS using threshold 0.50 and Top-K
    for th in [0.54, 0.50, 0.46]:
        mask_is = probs_oof >= th
        if np.count_nonzero(mask_is) < 15:
            continue
            
        is_et = df_is['entry_time'].values.astype(np.int64)[mask_is]
        is_xt = df_is['exit_time'].values.astype(np.int64)[mask_is]
        is_ep = df_is['entry_price'].values.astype(np.float64)[mask_is]
        is_xp = df_is['exit_price'].values.astype(np.float64)[mask_is]
        is_atr = df_is['atr'].values.astype(np.float64)[mask_is]
        is_mae = df_is['mae'].values.astype(np.float64)[mask_is]
        is_dr = df_is['direction'].values.astype(np.int8)[mask_is]
        
        roi, dd, wr, tr = fast_portfolio_backtest_numba(
            is_et, is_xt, is_ep, is_xp, is_atr, is_mae, is_dr, probs_oof[mask_is],
            initial_capital=5000.0, base_risk=75.0, house_risk=180.0,
            house_trigger=30.0, house_shield_risk=65.0, defense_risk=20.0,
            fee_rate=0.0008, max_concurrent=2, leverage=10.0, max_notional=50000.0,
            dd_limit=0.045
        )
        score = (roi * 100.0) * (wr ** 1.5) / (dd + 0.01)
        results.append((name, th, score, roi, dd, wr, tr))

results = sorted(results, key=lambda x: x[2], reverse=True)
print("\nTop 10 In-Sample Archetypes for Window 1 (Pure Out-Of-Fold Evaluation):")
print(f"{'Archetype':<25} {'Th':<6} {'Score':<10} {'ROI%':<10} {'MaxDD%':<10} {'WR%':<10} {'Trades':<8}")
print("-" * 85)
for r in results[:10]:
    print(f"{r[0]:<25} {r[1]:<6.2f} {r[2]:<10.1f} {r[3]*100:<10.1f} {r[4]*100:<10.2f} {r[5]*100:<10.1f} {r[6]:<8}")
