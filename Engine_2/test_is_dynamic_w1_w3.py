"""
Test In-Sample Archetype Selection on W1 to W3
"""
import sys, os, glob, json
sys.path.append('Engine_2')
from s1_liquidation_cascade import load_and_preprocess_data, ARCHETYPE_FUNCTIONS, extract_archetype_dataset, get_oos_windows, fast_portfolio_backtest_numba
import pandas as pd, numpy as np, lightgbm as lgb

feature_cols = [
    'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
    'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
    'liq_imbalance', 'liq_vol_ratio', 'liq_long_ratio', 'liq_short_ratio', 'liq_zscore_24h',
    'long_liq_zscore', 'short_liq_zscore', 'oi_flush', 'zoi', 'oid', 'oicc', 'fr', 'zfr', 'zls',
    'macro_spread', 'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'trend_strength', 'regime'
]

data = load_and_preprocess_data()
windows = get_oos_windows()

# Test W1, W2, W3 with K=9
for w_idx in [1, 2, 3]:
    w = windows[w_idx - 1]
    train_start = w['train_start']
    train_end_purged = w['train_end'] - pd.Timedelta(hours=3)
    test_start = w['test_start']
    test_end = w['test_end']
    
    # In-Sample Archetype Selection based on 18-month training data
    best_arch = None
    best_score = -1e9
    best_model = None
    best_df_oos = None
    
    for name in ['A1_VolBreakout', 'A6_SpotAbsorptionDiv', 'A5_PureRelativeCVD', 'A2_DeepSqueeze', 'A4_UltraDeepValue']:
        df_arch = extract_archetype_dataset(data, ARCHETYPE_FUNCTIONS[name], feature_cols)
        df_is = df_arch[(df_arch['entry_time'] >= train_start) & (df_arch['exit_time'] < train_end_purged)]
        if len(df_is) < 60:
            continue
            
        fcols = [c for c in feature_cols if c in df_is.columns]
        X_tr = df_is[fcols].fillna(0.0).to_numpy(np.float32)
        y_tr = df_is['label'].to_numpy(np.int32)
        p_tr = int(y_tr.sum())
        if p_tr == 0: continue
        sw = max(0.1, float((len(y_tr) - p_tr) / p_tr))
        
        m = lgb.LGBMClassifier(max_depth=4, learning_rate=0.03, n_estimators=60, scale_pos_weight=sw, random_state=42, verbose=-1, n_jobs=2)
        m.fit(X_tr, y_tr)
        
        # IS fit score: evaluate on last 3 months of IS
        split_t = train_end_purged - pd.Timedelta(days=90)
        df_val = df_is[df_is['entry_time'] >= split_t]
        if len(df_val) < 10:
            val_score = float(y_tr[-50:].mean())
        else:
            X_val = df_val[fcols].fillna(0.0).to_numpy(np.float32)
            val_probs = m.predict_proba(X_val)[:, 1]
            val_score = float((val_probs * df_val['label'].to_numpy()).sum() / max(1, len(val_probs)))
            
        if val_score > best_score:
            best_score = val_score
            best_arch = name
            best_model = m
            df_oos = df_arch[(df_arch['entry_time'] >= test_start) & (df_arch['entry_time'] < test_end)]
            best_df_oos = df_oos
            
    print(f"Window {w_idx:02d}: In-Sample Selected Arch = {best_arch} (IS Score = {best_score:.4f})")
    
    # OOS Single Trial Execution with K=9
    fcols = [c for c in feature_cols if c in best_df_oos.columns]
    X_oos = best_df_oos[fcols].fillna(0.0).to_numpy(np.float32)
    p_oos = best_model.predict_proba(X_oos)[:, 1]
    
    k = min(9, len(p_oos))
    idx_top = np.argsort(-p_oos)[:k]
    mask = np.zeros(len(p_oos), dtype=np.bool_)
    mask[idx_top] = True
    
    sub_et = best_df_oos['entry_time'].values.astype(np.int64)[mask]
    sub_xt = best_df_oos['exit_time'].values.astype(np.int64)[mask]
    sub_ep = best_df_oos['entry_price'].values.astype(np.float64)[mask]
    sub_xp = best_df_oos['exit_price'].values.astype(np.float64)[mask]
    sub_atr = best_df_oos['atr'].values.astype(np.float64)[mask]
    sub_mae = best_df_oos['mae'].values.astype(np.float64)[mask]
    sub_dr = best_df_oos['direction'].values.astype(np.int8)[mask]
    
    roi, dd, wr, tr = fast_portfolio_backtest_numba(
        sub_et, sub_xt, sub_ep, sub_xp, sub_atr, sub_mae, sub_dr, p_oos[mask],
        base_risk=75.0, house_risk=180.0, house_trigger=30.0
    )
    passed = (roi >= 0.20) and (dd <= 0.05) and (wr >= 0.40) and (tr >= 5)
    status_str = "PASS" if passed else "FAIL"
    print(f">>> OOS Window {w_idx:02d} [{status_str}]: ROI={roi*100:+.2f}%, MaxDD={dd*100:.2f}%, WR={wr*100:.1f}%, Trades={tr}\n")
