"""
Test Honest In-Sample Calibration on S1
"""
import os
import sys
import gc
import time
import json
import logging
import numpy as np
import pandas as pd
import lightgbm as lgb
from numba import njit

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("HonestS1Test")

sys.path.append(os.path.abspath("Engine_2"))
from s1_liquidation_cascade import (
    load_and_preprocess_data,
    ARCHETYPE_FUNCTIONS,
    extract_archetype_dataset,
    get_oos_windows,
    fast_portfolio_backtest_numba,
    INITIAL_CAPITAL,
    MIN_RETURN,
    MAX_DD,
    MIN_WIN_RATE,
    MIN_TRADES
)

feature_cols = [
    'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
    'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
    'liq_imbalance', 'liq_vol_ratio', 'liq_long_ratio', 'liq_short_ratio', 'liq_zscore_24h',
    'long_liq_zscore', 'short_liq_zscore', 'oi_flush', 'zoi', 'oid', 'oicc', 'fr', 'zfr', 'zls',
    'macro_spread', 'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'trend_strength', 'regime'
]

def run_test():
    data_by_symbol = load_and_preprocess_data()
    if not data_by_symbol:
        logger.error("No data loaded!")
        return
        
    windows = get_oos_windows()
    logger.info(f"Loaded {len(windows)} OOS windows.")
    
    # Extract trades for all archetypes
    archetypes = list(ARCHETYPE_FUNCTIONS.keys())
    archetype_datasets = {}
    logger.info(f"Pre-extracting trade streams for {len(archetypes)} archetypes...")
    for name in archetypes:
        df_arch = extract_archetype_dataset(data_by_symbol, ARCHETYPE_FUNCTIONS[name], feature_cols)
        archetype_datasets[name] = df_arch
        logger.info(f"  {name}: {len(df_arch):,} trades")
        
    print("\n" + "="*80)
    print("STARTING HONEST IN-SAMPLE CALIBRATION ON FIRST 5 WINDOWS")
    print("="*80 + "\n")
    
    for w_idx in range(1, 6):
        w = windows[w_idx - 1]
        train_start = w['train_start']
        test_start = w['test_start']
        test_end = w['test_end']
        train_end_purged = w['train_end'] - pd.Timedelta(hours=3)
        
        logger.info(f"--- Window {w_idx:02d}: {test_start.strftime('%Y-%m-%d')} to {test_end.strftime('%Y-%m-%d')} ---")
        
        # 1. Honest In-Sample Archetype Selection
        best_arch = None
        best_score = -999.0
        best_is_metrics = None
        
        for name in archetypes:
            df_arch = archetype_datasets[name]
            df_is = df_arch[(df_arch['entry_time'] >= train_start) & (df_arch['exit_time'] < train_end_purged)].copy()
            if len(df_is) < 60:
                continue
                
            fcols = [c for c in feature_cols if c in df_is.columns]
            
            # 80/20 train/val split strictly on In-Sample data
            split_idx = int(len(df_is) * 0.80)
            df_train = df_is.iloc[:split_idx]
            df_val = df_is.iloc[split_idx:]
            
            X_tr = df_train[fcols].fillna(0.0).to_numpy(dtype=np.float32)
            y_tr = df_train['label'].to_numpy(dtype=np.int32)
            p = int(y_tr.sum())
            sw = max(0.1, float((len(y_tr) - p) / p)) if p > 0 else 1.0
            
            model_is = lgb.LGBMClassifier(
                max_depth=4, learning_rate=0.03, n_estimators=50,
                scale_pos_weight=sw, random_state=42, verbose=-1,
                min_child_samples=15, n_jobs=2
            )
            model_is.fit(X_tr, y_tr)
            
            X_val = df_val[fcols].fillna(0.0).to_numpy(dtype=np.float32)
            probs_val = model_is.predict_proba(X_val)[:, 1].astype(np.float64)
            
            # Select top-k on validation slice
            k_val = min(len(probs_val), 8)
            if k_val < 3:
                continue
            idx_top = np.argsort(-probs_val)[:k_val]
            mask_val = np.zeros(len(probs_val), dtype=np.bool_)
            mask_val[idx_top] = True
            
            val_et = df_val['entry_time'].values.astype(np.int64)
            val_xt = df_val['exit_time'].values.astype(np.int64)
            val_ep = df_val['entry_price'].values.astype(np.float64)
            val_xp = df_val['exit_price'].values.astype(np.float64)
            val_atr = df_val['atr'].values.astype(np.float64)
            val_mae = df_val['mae'].values.astype(np.float64)
            val_dr = df_val['direction'].values.astype(np.int8)
            
            roi_val, dd_val, wr_val, tr_val = fast_portfolio_backtest_numba(
                val_et[mask_val], val_xt[mask_val], val_ep[mask_val], val_xp[mask_val],
                val_atr[mask_val], val_mae[mask_val], val_dr[mask_val], probs_val[mask_val],
                initial_capital=5000.0, base_risk=30.0, house_risk=180.0,
                house_trigger=30.0, house_shield_risk=65.0, defense_risk=20.0,
                fee_rate=0.0008, max_concurrent=2, leverage=10.0, max_notional=50000.0,
                dd_limit=0.045
            )
            
            score = (roi_val * 100.0) * (wr_val ** 1.5) / (dd_val + 0.01)
            if score > best_score:
                best_score = score
                best_arch = name
                best_is_metrics = (roi_val, dd_val, wr_val, tr_val)
                
        logger.info(f"  Selected Archetype: {best_arch} (IS Val Score: {best_score:.2f}, ROI: {best_is_metrics[0]*100:.1f}%, DD: {best_is_metrics[1]*100:.2f}%, WR: {best_is_metrics[2]*100:.1f}%, Trades: {best_is_metrics[3]})")
        
        # 2. Train on FULL 100% of In-Sample data for the winning archetype
        df_arch = archetype_datasets[best_arch]
        df_is_full = df_arch[(df_arch['entry_time'] >= train_start) & (df_arch['exit_time'] < train_end_purged)].copy()
        df_oos = df_arch[(df_arch['entry_time'] >= test_start) & (df_arch['entry_time'] < test_end)].copy()
        
        fcols = [c for c in feature_cols if c in df_is_full.columns]
        X_train_full = df_is_full[fcols].fillna(0.0).to_numpy(dtype=np.float32)
        y_train_full = df_is_full['label'].to_numpy(dtype=np.int32)
        p = int(y_train_full.sum())
        sw = max(0.1, float((len(y_train_full) - p) / p)) if p > 0 else 1.0
        
        model_final = lgb.LGBMClassifier(
            max_depth=4, learning_rate=0.03, n_estimators=60,
            scale_pos_weight=sw, random_state=42, verbose=-1,
            min_child_samples=15, n_jobs=2
        )
        model_final.fit(X_train_full, y_train_full)
        
        # 3. SINGLE TRIAL OUT-OF-SAMPLE EXECUTION (NO LOOPS, NO SNOOPING)
        X_oos = df_oos[fcols].fillna(0.0).to_numpy(dtype=np.float32)
        probs_oos = model_final.predict_proba(X_oos)[:, 1].astype(np.float64)
        
        k_oos = min(len(probs_oos), 7)
        idx_top_oos = np.argsort(-probs_oos)[:k_oos]
        mask_oos = np.zeros(len(probs_oos), dtype=np.bool_)
        mask_oos[idx_top_oos] = True
        
        oos_et = df_oos['entry_time'].values.astype(np.int64)
        oos_xt = df_oos['exit_time'].values.astype(np.int64)
        oos_ep = df_oos['entry_price'].values.astype(np.float64)
        oos_xp = df_oos['exit_price'].values.astype(np.float64)
        oos_atr = df_oos['atr'].values.astype(np.float64)
        oos_mae = df_oos['mae'].values.astype(np.float64)
        oos_dr = df_oos['direction'].values.astype(np.int8)
        
        roi_oos, dd_oos, wr_oos, tr_oos = fast_portfolio_backtest_numba(
            oos_et[mask_oos], oos_xt[mask_oos], oos_ep[mask_oos], oos_xp[mask_oos],
            oos_atr[mask_oos], oos_mae[mask_oos], oos_dr[mask_oos], probs_oos[mask_oos],
            initial_capital=5000.0, base_risk=30.0, house_risk=180.0,
            house_trigger=30.0, house_shield_risk=65.0, defense_risk=20.0,
            fee_rate=0.0008, max_concurrent=2, leverage=10.0, max_notional=50000.0,
            dd_limit=0.045
        )
        
        passed = (roi_oos >= MIN_RETURN) and (dd_oos <= MAX_DD) and (wr_oos >= MIN_WIN_RATE) and (tr_oos >= MIN_TRADES)
        status_str = "PASS" if passed else "FAIL"
        logger.info(f"  >>> OOS Window {w_idx:02d} [{status_str}]: ROI={roi_oos*100:+.2f}%, MaxDD={dd_oos*100:.2f}%, WR={wr_oos*100:.1f}%, Trades={tr_oos}\n")

if __name__ == "__main__":
    run_test()
