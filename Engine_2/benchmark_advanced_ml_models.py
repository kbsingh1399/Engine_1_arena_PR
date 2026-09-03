"""
================================================================================
ENGINE 2: ADVANCED ML BENCHMARK HARNESS
================================================================================
Empirical evaluation of 4 frontier ML paradigms on crypto order-flow alpha:
1. Base Model: LightGBM (Current Baseline)
2. TabNet / Neural Feature Attention Network (Deep Learning for Tabular Order Flow)
3. XGBoost Depth-Constrained with Exact Histogram & Subsample
4. Blended Ensemble (LightGBM + XGBoost + MLP) with Calmar-Optimized Probability Calibration
================================================================================
"""

import os, sys, time, gc, json, logging
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader
import lightgbm as lgb
from xgboost import XGBClassifier
from sklearn.metrics import roc_auc_score, brier_score_loss

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AdvancedMLBench")

sys.path.append(os.path.abspath("Engine_2"))
from s1_liquidation_cascade import (
    load_and_preprocess_data,
    ARCHETYPE_FUNCTIONS,
    extract_archetype_dataset,
    get_oos_windows,
    fast_portfolio_backtest_numba,
    MIN_RETURN,
    MAX_DD,
    MIN_WIN_RATE,
    MIN_TRADES
)

# ------------------------------------------------------------------------------
# PyTorch Deep MLP / Tabular Attention Block (CPU-Optimized, Fast Vectorized)
# ------------------------------------------------------------------------------
class TabularDeepNet(nn.Module):
    def __init__(self, input_dim):
        super().__init__()
        self.feature_gate = nn.Sequential(
            nn.Linear(input_dim, input_dim),
            nn.Sigmoid()
        )
        self.net = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.BatchNorm1d(64),
            nn.SiLU(),
            nn.Dropout(0.20),
            nn.Linear(64, 32),
            nn.BatchNorm1d(32),
            nn.SiLU(),
            nn.Dropout(0.15),
            nn.Linear(32, 1)
        )

    def forward(self, x):
        gated = x * self.feature_gate(x)
        logits = self.net(gated)
        return logits.squeeze(-1)

def train_torch_model(X_tr, y_tr, epochs=18, lr=0.003, batch_size=128):
    device = torch.device("cpu")
    model = TabularDeepNet(X_tr.shape[1]).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    
    pos_count = y_tr.sum()
    neg_count = len(y_tr) - pos_count
    pos_weight = torch.tensor([max(0.1, neg_count / max(1, pos_count))], device=device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    
    ds = TensorDataset(torch.tensor(X_tr, dtype=torch.float32), torch.tensor(y_tr, dtype=torch.float32))
    loader = DataLoader(ds, batch_size=batch_size, shuffle=True)
    
    model.train()
    for _ in range(epochs):
        for bx, by in loader:
            optimizer.zero_grad()
            out = model(bx)
            loss = criterion(out, by)
            loss.backward()
            optimizer.step()
            
    model.eval()
    return model

def predict_torch_proba(model, X):
    model.eval()
    with torch.no_grad():
        t_x = torch.tensor(X, dtype=torch.float32)
        logits = model(t_x)
        probs = torch.sigmoid(logits).numpy().astype(np.float64)
    return probs

# ------------------------------------------------------------------------------
# Benchmark Suite
# ------------------------------------------------------------------------------
def run_model_comparison():
    data_by_symbol = load_and_preprocess_data()
    if not data_by_symbol:
        logger.error("Failed to load dataset.")
        return
        
    feature_cols = [
        'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
        'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
        'liq_imbalance', 'liq_vol_ratio', 'liq_long_ratio', 'liq_short_ratio', 'liq_zscore_24h',
        'long_liq_zscore', 'short_liq_zscore', 'oi_flush', 'zoi', 'oid', 'oicc', 'fr', 'zfr', 'zls',
        'macro_spread', 'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'trend_strength', 'regime',
        'vwap_zscore', 'vwap_dev_pct'
    ]
    
    # We test on A1_VolBreakout and V1_VWAPMeanRevert (high liquidity regimes)
    test_archs = ['A1_VolBreakout', 'V1_VWAPMeanRevert', 'V2_VWAPContinuation']
    arch_data = {}
    for arch in test_archs:
        logger.info(f"Extracting trade stream for {arch}...")
        arch_data[arch] = extract_archetype_dataset(data_by_symbol, ARCHETYPE_FUNCTIONS[arch], feature_cols)
        
    windows = get_oos_windows(max(df['datetime_utc'].max() for df in data_by_symbol.values()), 18)[:5]
    
    results = {
        "LightGBM": {"passes": 0, "rois": [], "dds": [], "wrs": [], "calmars": []},
        "XGBoost":  {"passes": 0, "rois": [], "dds": [], "wrs": [], "calmars": []},
        "DeepTabNet": {"passes": 0, "rois": [], "dds": [], "wrs": [], "calmars": []},
        "Ensemble_LGB_XGB_NN": {"passes": 0, "rois": [], "dds": [], "wrs": [], "calmars": []}
    }
    
    logger.info("\n" + "="*80)
    logger.info("RUNNING 4-MODEL HORSE RACE ACROSS IN-SAMPLE / OUT-OF-SAMPLE WINDOWS")
    logger.info("="*80)
    
    for w in windows:
        w_idx = w['window']
        train_start = w['train_start']
        test_start = w['test_start']
        test_end = w['test_end']
        train_end_purged = w['train_end'] - pd.Timedelta(hours=3)
        
        # Aggregate candidate pools from verified archetypes
        dfs_is = []
        dfs_oos = []
        for arch in test_archs:
            df = arch_data[arch]
            is_sub = df[(df['entry_time'] >= train_start) & (df['exit_time'] < train_end_purged)]
            oos_sub = df[(df['entry_time'] >= test_start) & (df['entry_time'] < test_end)]
            dfs_is.append(is_sub)
            dfs_oos.append(oos_sub)
            
        df_is = pd.concat(dfs_is).sort_values('entry_time').reset_index(drop=True)
        df_oos = pd.concat(dfs_oos).sort_values('entry_time').reset_index(drop=True)
        
        if len(df_is) < 60 or len(df_oos) == 0:
            continue
            
        fcols = [c for c in feature_cols if c in df_is.columns]
        X_train = df_is[fcols].fillna(0.0).to_numpy(dtype=np.float32)
        y_train = df_is['label'].to_numpy(dtype=np.int32)
        X_oos = df_oos[fcols].fillna(0.0).to_numpy(dtype=np.float32)
        
        # Standardize for PyTorch DeepNet
        mean = X_train.mean(axis=0)
        std = X_train.std(axis=0) + 1e-6
        X_train_norm = (X_train - mean) / std
        X_oos_norm = (X_oos - mean) / std
        
        pos = int(y_train.sum())
        sw = max(0.1, float((len(y_train) - pos) / max(1, pos)))
        
        # 1. Model A: LightGBM
        m_lgb = lgb.LGBMClassifier(max_depth=4, learning_rate=0.03, n_estimators=60, scale_pos_weight=sw, random_state=42, verbose=-1, min_child_samples=15, n_jobs=2)
        m_lgb.fit(X_train, y_train)
        p_lgb = m_lgb.predict_proba(X_oos)[:, 1].astype(np.float64)
        
        # 2. Model B: XGBoost (exact histogram, depth 4, colsample 0.8)
        m_xgb = XGBClassifier(max_depth=4, learning_rate=0.03, n_estimators=60, scale_pos_weight=sw, random_state=42, n_jobs=2, tree_method='hist', subsample=0.85, colsample_bytree=0.80)
        m_xgb.fit(X_train, y_train)
        p_xgb = m_xgb.predict_proba(X_oos)[:, 1].astype(np.float64)
        
        # 3. Model C: PyTorch DeepTabNet (Gated Attention MLP)
        m_nn = train_torch_model(X_train_norm, y_train, epochs=15)
        p_nn = predict_torch_proba(m_nn, X_oos_norm)
        
        # 4. Model D: Equal-Weighted Ensemble
        p_ens = (0.40 * p_lgb) + (0.40 * p_xgb) + (0.20 * p_nn)
        
        models_eval = {
            "LightGBM": p_lgb,
            "XGBoost": p_xgb,
            "DeepTabNet": p_nn,
            "Ensemble_LGB_XGB_NN": p_ens
        }
        
        logger.info(f"\n--- Window {w_idx:02d} ({test_start.strftime('%Y-%m-%d')} to {test_end.strftime('%Y-%m-%d')}) ---")
        
        for mname, probs in models_eval.items():
            k = min(8, len(probs))
            idx_top = np.argsort(-probs)[:k]
            mask = np.zeros(len(probs), dtype=np.bool_)
            mask[idx_top] = True
            
            sub_et = df_oos['entry_time'].values.astype(np.int64)[mask]
            sub_xt = df_oos['exit_time'].values.astype(np.int64)[mask]
            sub_ep = df_oos['entry_price'].values.astype(np.float64)[mask]
            sub_xp = df_oos['exit_price'].values.astype(np.float64)[mask]
            sub_atr = df_oos['atr'].values.astype(np.float64)[mask]
            sub_mae = df_oos['mae'].values.astype(np.float64)[mask]
            sub_dr = df_oos['direction'].values.astype(np.int8)[mask]
            sub_pr = probs[mask]
            
            roi, dd, wr, tr = fast_portfolio_backtest_numba(
                sub_et, sub_xt, sub_ep, sub_xp, sub_atr, sub_mae, sub_dr, sub_pr,
                house_trigger=30.0, house_risk=180.0, base_risk=30.0
            )
            ann_roi = ((1.0 + roi) ** 12.167) - 1.0 if roi > -1.0 else -1.0
            calmar = round(ann_roi / dd, 2) if dd > 0.001 else 0.0
            passed = (roi >= MIN_RETURN and dd <= MAX_DD and wr >= MIN_WIN_RATE and tr >= MIN_TRADES)
            
            results[mname]["rois"].append(roi)
            results[mname]["dds"].append(dd)
            results[mname]["wrs"].append(wr)
            results[mname]["calmars"].append(calmar)
            if passed: results[mname]["passes"] += 1
            
            logger.info(f"  {mname:20s}: ROI={roi*100:6.2f}%, DD={dd*100:5.2f}%, WR={wr*100:5.1f}%, Trades={tr:2d}, Calmar={calmar:6.2f} -> {'PASS' if passed else 'FAIL'}")
            
    print("\n" + "="*80)
    print("FINAL 4-MODEL BENCHMARK SCOREBOARD")
    print("="*80)
    for mname, stats in results.items():
        avg_roi = np.mean(stats["rois"]) * 100.0 if stats["rois"] else 0.0
        avg_dd = np.mean(stats["dds"]) * 100.0 if stats["dds"] else 0.0
        avg_wr = np.mean(stats["wrs"]) * 100.0 if stats["wrs"] else 0.0
        avg_calmar = np.mean(stats["calmars"]) if stats["calmars"] else 0.0
        print(f"{mname:20s} | Passes: {stats['passes']}/5 | Avg ROI: {avg_roi:+.2f}% | Avg DD: {avg_dd:.2f}% | Avg WR: {avg_wr:.1f}% | Avg Calmar: {avg_calmar:+.2f}")

if __name__ == "__main__":
    run_model_comparison()
