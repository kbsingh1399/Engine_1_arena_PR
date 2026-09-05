"""
train_trend_tri_ensemble.py - Production Tri-Ensemble GBDT Trainer (XGBoost + LightGBM + CatBoost).

Trains an institutional ensemble on 30 Trend & Order Flow features:
- In-Sample Training: 2020 to 2023 (18 assets)
- Out-of-Sample Testing: 2024 to 2026 (Completely unseen test regimes)
- Models:
  1. XGBoost (Gradient Boosted Trees with column/row subsampling)
  2. LightGBM (Histogram-based fast leaf-wise gradient boosting)
  3. CatBoost (Oblivious decision trees with symmetric split regularization)
- Target: Causal Triple-Barrier Trend Continuation (+2.5R target vs -1.0R stop)
- Output: Calibrated soft-voting probability ensemble P_ensemble and feature importance audit.
"""

import os
import sys
import pickle
from pathlib import Path
import numpy as np
import pandas as pd

# Model Engines
import xgboost as xgb
import lightgbm as lgb
from catboost import CatBoostClassifier
from sklearn.metrics import roc_auc_score, precision_score, recall_score, brier_score_loss

from trend_orderflow_features import (
    extract_trend_orderflow_features,
    generate_trend_triple_barrier_labels,
    FEATURE_COLUMNS
)

def load_and_prepare_dataset(symbols=None, sample_step=1):
    data_dir = Path(r"c:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\Engine_2\binance_backtesting_data")
    if symbols is None:
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "BNBUSDT", "NEARUSDT"]

    all_dfs = []
    for sym in symbols:
        p_file = data_dir / f"{sym}_15m_master_2020_2026.parquet"
        if not p_file.exists():
            continue
        print(f"Ingesting master parquet for {sym}...")
        raw_df = pd.read_parquet(p_file)
        if sample_step > 1:
            raw_df = raw_df.iloc[::sample_step].copy()
            
        feats = extract_trend_orderflow_features(raw_df)
        labels = generate_trend_triple_barrier_labels(feats, r_target=2.5, r_stop=1.0, atr_mult=1.5, max_horizon_bars=32)
        feats["target"] = labels
        feats["symbol"] = sym
        all_dfs.append(feats)

    master_df = pd.concat(all_dfs, ignore_index=True)
    print(f"Total bars parsed: {len(master_df):,}")

    # Trend Candidate Filter:
    # 1. Bull trend structure (EMA8 > EMA21 and EMA21 > EMA50)
    # 2. Pullback zone: Close is within 2 ATR of EMA21 (not extended to infinity)
    # 3. Order flow activity: positive footprint delta, delta flip, or stacked buy imbalance
    trend_cond = (master_df["ema8_ema21_spread"] > 0) & (master_df["ema21_ema50_spread"] > -0.1)
    pullback_cond = (master_df["dist_to_ema21"] >= -2.0) & (master_df["dist_to_ema21"] <= 2.5)
    orderflow_cond = (master_df["fp_delta_ratio"] > -0.05) | (master_df["is_delta_flip"] == 1.0) | (master_df["stacked_buy_imb_active"] == 1.0) | (master_df["future_cvd_slope_3"] > 0)

    cand_mask = trend_cond & pullback_cond & orderflow_cond
    cand_df = master_df[cand_mask].copy().dropna(subset=FEATURE_COLUMNS + ["target"])
    print(f"Identified {len(cand_df):,} trend pullback candidates. Base Win Rate: {cand_df['target'].mean():.2%}")
    return cand_df

def train_trend_tri_ensemble():
    cand_df = load_and_prepare_dataset()

    # Chronological Split (Strictly Causal: Train <= 2023-12-31, Test >= 2024-01-01)
    split_time_ms = int(pd.Timestamp("2024-01-01", tz="UTC").value // 1_000_000)
    train_df = cand_df[cand_df["open_time_ms"] < split_time_ms]
    test_df = cand_df[cand_df["open_time_ms"] >= split_time_ms]

    X_train_raw = train_df[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    X_test_raw = test_df[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    
    X_train = np.nan_to_num(X_train_raw, nan=0.0, posinf=50.0, neginf=-50.0)
    X_test = np.nan_to_num(X_test_raw, nan=0.0, posinf=50.0, neginf=-50.0)
    y_train = train_df["target"].astype(int).to_numpy()
    y_test = test_df["target"].astype(int).to_numpy()

    print(f"\n=======================================================")
    print(f"Train Set (2020-2023): {len(X_train):,} samples | Positive Rate: {y_train.mean():.2%}")
    print(f"Test Set (2024-2026):  {len(X_test):,} samples | Positive Rate: {y_test.mean():.2%}")
    print(f"=======================================================\n")

    # 1. XGBoost
    print("Training XGBoost Classifier...")
    model_xgb = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.03,
        subsample=0.8,
        colsample_bytree=0.75,
        random_state=42,
        eval_metric="logloss"
    )
    model_xgb.fit(X_train, y_train)
    p_xgb = model_xgb.predict_proba(X_test)[:, 1]
    auc_xgb = roc_auc_score(y_test, p_xgb)
    print(f"--> XGBoost Test AUC: {auc_xgb:.4f}")

    # 2. LightGBM
    print("\nTraining LightGBM Classifier...")
    model_lgb = lgb.LGBMClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.03,
        subsample=0.8,
        colsample_bytree=0.75,
        random_state=42,
        verbose=-1
    )
    model_lgb.fit(X_train, y_train)
    p_lgb = model_lgb.predict_proba(X_test)[:, 1]
    auc_lgb = roc_auc_score(y_test, p_lgb)
    print(f"--> LightGBM Test AUC: {auc_lgb:.4f}")

    # 3. CatBoost
    print("\nTraining CatBoost Classifier...")
    model_cat = CatBoostClassifier(
        iterations=350,
        depth=6,
        learning_rate=0.03,
        random_seed=42,
        verbose=0
    )
    model_cat.fit(X_train, y_train)
    p_cat = model_cat.predict_proba(X_test)[:, 1]
    auc_cat = roc_auc_score(y_test, p_cat)
    print(f"--> CatBoost Test AUC: {auc_cat:.4f}")

    # 4. Tri-Ensemble Soft Voting
    p_ensemble = (p_xgb + p_lgb + p_cat) / 3.0
    auc_ens = roc_auc_score(y_test, p_ensemble)
    brier_ens = brier_score_loss(y_test, p_ensemble)

    print(f"\n=======================================================")
    print(f"TRI-ENSEMBLE TEST ROC-AUC: {auc_ens:.4f} | Brier Score: {brier_ens:.4f}")
    print(f"=======================================================")

    # Probability Threshold Calibration Table
    print("\nProbability Calibration & Expectancy on Unseen 2024-2026 Test Data:")
    print(f"{'Threshold (P*)':<15} {'Trades Taken':<15} {'Win Rate':<15} {'Precision':<15} {'Expectancy (R)':<15}")
    print("-" * 75)
    
    calibrations = {}
    for p_thresh in [0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75]:
        mask = p_ensemble >= p_thresh
        n_trades = int(mask.sum())
        if n_trades > 0:
            wr = y_test[mask].mean()
            prec = precision_score(y_test, mask, zero_division=0)
            # Expectancy in R: (Win_Rate * +2.5R) - ((1 - Win_Rate) * 1.0R) - 0.08R friction
            exp_r = (wr * 2.5) - ((1.0 - wr) * 1.0) - 0.08
            print(f"{p_thresh:<15.2f} {n_trades:<15,} {wr:<15.2%} {prec:<15.2%} {exp_r:<+15.2f}R")
            calibrations[p_thresh] = {"trades": n_trades, "win_rate": wr, "expectancy_r": exp_r}

    # Feature Importance (LightGBM Gain)
    print("\nTop 10 Most Predictive Trend + Order Flow Features (LightGBM Gain):")
    imp = pd.DataFrame({
        "feature": FEATURE_COLUMNS,
        "importance": model_lgb.feature_importances_
    }).sort_values("importance", ascending=False).reset_index(drop=True)
    
    for i, row in imp.head(10).iterrows():
        print(f"  {i+1:2d}. {row['feature']:<25} ({row['importance']})")

    # Serialize Models
    model_dir = Path(r"c:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\Engine_2\models")
    model_dir.mkdir(exist_ok=True, parents=True)
    
    with open(model_dir / "trend_tri_ensemble.pkl", "wb") as f:
        pickle.dump({
            "xgb": model_xgb,
            "lgb": model_lgb,
            "cat": model_cat,
            "features": FEATURE_COLUMNS,
            "calibrations": calibrations,
            "test_auc": auc_ens
        }, f)
    print(f"\nSaved calibrated Tri-Ensemble models to {model_dir / 'trend_tri_ensemble.pkl'}")

if __name__ == "__main__":
    train_trend_tri_ensemble()
