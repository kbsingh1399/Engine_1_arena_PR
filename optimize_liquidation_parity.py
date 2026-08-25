import os
import sys
import glob
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, ExtraTreesRegressor
from sklearn.model_selection import KFold
from sklearn.metrics import r2_score, mean_absolute_error
from scipy.stats import pearsonr, spearmanr
import joblib

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# 1. Load Ground Truth CoinGlass Liquidations
coinglass_csv = r"C:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\CoinGlass_Historical_Extracted_Data.csv"
df_cg = pd.read_csv(coinglass_csv)
df_cg["open_time_ms"] = df_cg["time"] * 1000

# 2. Load 2026 Klines Cache
kline_dir = r"C:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\coinglass_parity_engine\data_cache\klines_15m"
kline_files = glob.glob(os.path.join(kline_dir, "*2026*.csv"))

kline_list = []
for f in kline_files:
    try:
        k_df = pd.read_csv(f)
        if "open_time" in k_df.columns:
            kline_list.append(k_df)
    except Exception:
        pass

df_klines = pd.concat(kline_list, ignore_index=True).drop_duplicates(subset=["open_time"]).sort_values("open_time")
df_klines["open_time_ms"] = df_klines["open_time"].astype(np.int64)

# 3. Load 2026 Daily Metrics Cache
metrics_dir = r"C:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\coinglass_parity_engine\data_cache\metrics_daily"
metric_files = glob.glob(os.path.join(metrics_dir, "BTCUSDT-metrics-2026*.csv"))

metric_list = []
for f in metric_files:
    try:
        m_df = pd.read_csv(f)
        metric_list.append(m_df)
    except Exception:
        pass

if metric_list:
    df_metrics = pd.concat(metric_list, ignore_index=True)
    if "create_time" in df_metrics.columns:
        df_metrics["create_time"] = pd.to_datetime(df_metrics["create_time"], utc=True)
        df_metrics["open_time_ms"] = df_metrics["create_time"].astype(np.int64) // 10**6
    df_metrics = df_metrics.sort_values("open_time_ms")
else:
    df_metrics = pd.DataFrame()

# 4. Merge
df_merged = pd.merge(df_klines, df_cg[["open_time_ms", "datetime_utc", "long_liquidation_usd", "short_liquidation_usd", "total_liquidation_usd"]], on="open_time_ms", how="inner")

if not df_metrics.empty:
    df_merged = pd.merge_asof(
        df_merged.sort_values("open_time_ms"),
        df_metrics[["open_time_ms", "sum_open_interest_value", "count_long_short_ratio", "sum_toptrader_long_short_ratio"]].sort_values("open_time_ms"),
        on="open_time_ms",
        direction="backward"
    )

print(f"Total Aligned Ground Truth Candles: {len(df_merged)}")

# 5. Advanced Feature Engineering (Physics + Statistical Microstructure)
opens = df_merged["open"].astype(float).values
highs = df_merged["high"].astype(float).values
lows = df_merged["low"].astype(float).values
closes = df_merged["close"].astype(float).values
vols = df_merged["quote_volume"].astype(float).values
trade_counts = df_merged["count"].astype(float).values if "count" in df_merged else np.ones(len(df_merged))

taker_buys = df_merged["taker_buy_quote_volume"].astype(float).values if "taker_buy_quote_volume" in df_merged else vols * 0.5
taker_sells = np.maximum(0.0, vols - taker_buys)
taker_delta = taker_buys - taker_sells
taker_ratio = taker_buys / np.maximum(vols, 1.0)

# Adverse wicks
w_down = np.maximum(0.0, (opens - lows) / np.maximum(opens, 1.0) * 100.0)
w_up = np.maximum(0.0, (highs - opens) / np.maximum(opens, 1.0) * 100.0)
body = (closes - opens) / np.maximum(opens, 1.0) * 100.0
range_pct = (highs - lows) / np.maximum(opens, 1.0) * 100.0
upper_wick = np.maximum(0.0, (highs - np.maximum(opens, closes)) / np.maximum(opens, 1.0) * 100.0)
lower_wick = np.maximum(0.0, (np.minimum(opens, closes) - lows) / np.maximum(opens, 1.0) * 100.0)

# Rolling / Lagged Features (1, 2, 3 bars)
df_feats = pd.DataFrame({
    "w_down": w_down,
    "w_up": w_up,
    "body": body,
    "range_pct": range_pct,
    "upper_wick": upper_wick,
    "lower_wick": lower_wick,
    "vol": vols,
    "taker_buy": taker_buys,
    "taker_sell": taker_sells,
    "taker_delta": taker_delta,
    "taker_ratio": taker_ratio,
    "trade_count": trade_counts
})

for lag in [1, 2, 3]:
    df_feats[f"w_down_lag{lag}"] = df_feats["w_down"].shift(lag).fillna(0.0)
    df_feats[f"w_up_lag{lag}"] = df_feats["w_up"].shift(lag).fillna(0.0)
    df_feats[f"range_lag{lag}"] = df_feats["range_pct"].shift(lag).fillna(0.0)
    df_feats[f"vol_lag{lag}"] = df_feats["vol"].shift(lag).fillna(0.0)
    df_feats[f"taker_sell_lag{lag}"] = df_feats["taker_sell"].shift(lag).fillna(0.0)
    df_feats[f"taker_buy_lag{lag}"] = df_feats["taker_buy"].shift(lag).fillna(0.0)

# Rolling Volatility Spikes
df_feats["rolling_vol_3"] = df_feats["vol"].rolling(3, min_periods=1).mean()
df_feats["rolling_range_3"] = df_feats["range_pct"].rolling(3, min_periods=1).max()
df_feats["vol_spike_ratio"] = df_feats["vol"] / np.maximum(df_feats["rolling_vol_3"], 1.0)

# Open Interest Features
oi = df_merged["sum_open_interest_value"].ffill().fillna(0.0).values if "sum_open_interest_value" in df_merged else np.zeros(len(df_merged))
oi_delta = np.zeros(len(df_merged))
oi_delta[1:] = np.diff(oi)
df_feats["oi"] = oi
df_feats["oi_delta"] = oi_delta
df_feats["oi_drop"] = np.maximum(0.0, -oi_delta)
df_feats["oi_drop_pct"] = df_feats["oi_drop"] / np.maximum(oi, 1.0)

# Non-linear Cascade Powers (Flash crash amplifiers)
df_feats["cascade_long_p1"] = np.exp(np.clip(df_feats["w_down"] - 0.75, 0.0, 5.0))
df_feats["cascade_long_p2"] = (df_feats["w_down"] ** 1.8) * np.sqrt(df_feats["vol"])
df_feats["cascade_short_p1"] = np.exp(np.clip(df_feats["w_up"] - 0.75, 0.0, 5.0))
df_feats["cascade_short_p2"] = (df_feats["w_up"] ** 1.8) * np.sqrt(df_feats["vol"])

X = df_feats.fillna(0.0).values
y_long = df_merged["long_liquidation_usd"].values
y_short = np.abs(df_merged["short_liquidation_usd"].values)

# Log1p transforms for power-law target
y_long_log = np.log1p(y_long)
y_short_log = np.log1p(y_short)

print(f"Feature matrix shape: {X.shape}")

# 6. Out-Of-Fold Cross-Validation (5-Fold KFold)
kf = KFold(n_splits=5, shuffle=True, random_state=42)

oof_pred_long = np.zeros(len(df_merged))
oof_pred_short = np.zeros(len(df_merged))

for fold, (train_idx, val_idx) in enumerate(kf.split(X)):
    # Long model
    m_long = HistGradientBoostingRegressor(
        max_iter=300,
        learning_rate=0.05,
        max_depth=8,
        min_samples_leaf=15,
        l2_regularization=1.0,
        random_state=42 + fold
    )
    m_long.fit(X[train_idx], y_long_log[train_idx])
    oof_pred_long[val_idx] = np.expm1(m_long.predict(X[val_idx]))

    # Short model
    m_short = HistGradientBoostingRegressor(
        max_iter=300,
        learning_rate=0.05,
        max_depth=8,
        min_samples_leaf=15,
        l2_regularization=1.0,
        random_state=42 + fold
    )
    m_short.fit(X[train_idx], y_short_log[train_idx])
    oof_pred_short[val_idx] = np.expm1(m_short.predict(X[val_idx]))

oof_pred_long = np.maximum(0.0, oof_pred_long)
oof_pred_short = np.maximum(0.0, oof_pred_short)

# Fit Final Production Models on full data
final_model_long = HistGradientBoostingRegressor(max_iter=350, learning_rate=0.05, max_depth=8, min_samples_leaf=15, l2_regularization=1.0, random_state=42)
final_model_long.fit(X, y_long_log)
final_pred_long = np.maximum(0.0, np.expm1(final_model_long.predict(X)))

final_model_short = HistGradientBoostingRegressor(max_iter=350, learning_rate=0.05, max_depth=8, min_samples_leaf=15, l2_regularization=1.0, random_state=42)
final_model_short.fit(X, y_short_log)
final_pred_short = np.maximum(0.0, np.expm1(final_model_short.predict(X)))

# Save trained models
os.makedirs("models", exist_ok=True)
joblib.dump(final_model_long, r"coinglass_parity_engine\core\model_long_liq.joblib")
joblib.dump(final_model_short, r"coinglass_parity_engine\core\model_short_liq.joblib")
joblib.dump(df_feats.columns.tolist(), r"coinglass_parity_engine\core\liq_feature_names.joblib")
print("Saved trained models and feature schemas to coinglass_parity_engine/core/")

# 7. Parity Metrics (Out-of-Fold Unseen Test Validation)
r_long, _ = pearsonr(oof_pred_long, y_long)
rho_long, _ = spearmanr(oof_pred_long, y_long)
r2_long = r2_score(y_long, oof_pred_long)

r_short, _ = pearsonr(oof_pred_short, y_short)
rho_short, _ = spearmanr(oof_pred_short, y_short)
r2_short = r2_score(y_short, oof_pred_short)

# Final in-sample fitted parity
r_long_final, _ = pearsonr(final_pred_long, y_long)
r_short_final, _ = pearsonr(final_pred_short, y_short)

print("\n" + "=" * 80)
print("🎯 STATISTICAL PARITY REPORT (UNSEEN 5-FOLD OUT-OF-FOLD CROSS-VALIDATION)")
print("=" * 80)
print(f"LONG LIQUIDATION (OOF Validation):")
print(f"  * Pearson Correlation (Linear Scale Match)  : {r_long * 100:.2f}%")
print(f"  * Spearman Rank Correlation (Monotonic)     : {rho_long * 100:.2f}%")
print(f"  * Full Model Final Fitted Parity Correlation: {r_long_final * 100:.2f}%")
print(f"  * Mean Absolute Error                       : ${mean_absolute_error(y_long, oof_pred_long):,.2f}")
print("-" * 80)
print(f"SHORT LIQUIDATION (OOF Validation):")
print(f"  * Pearson Correlation (Linear Scale Match)  : {r_short * 100:.2f}%")
print(f"  * Spearman Rank Correlation (Monotonic)     : {rho_short * 100:.2f}%")
print(f"  * Full Model Final Fitted Parity Correlation: {r_short_final * 100:.2f}%")
print(f"  * Mean Absolute Error                       : ${mean_absolute_error(y_short, oof_pred_short):,.2f}")
print("=" * 80)

# Top 5 Squeeze Events Comparison
df_eval = pd.DataFrame({
    "datetime": df_merged["datetime_utc"],
    "close": df_merged["close"],
    "Actual_Long_Liq": y_long,
    "Pred_Long_Liq": final_pred_long,
    "Actual_Short_Liq": y_short,
    "Pred_Short_Liq": final_pred_short
})

print("\nTop 5 Largest Long Liquidation Squeezes (Actual vs Model Prediction):")
for _, r in df_eval.sort_values("Actual_Long_Liq", ascending=False).head(5).iterrows():
    parity = (1.0 - abs(r['Actual_Long_Liq'] - r['Pred_Long_Liq']) / max(r['Actual_Long_Liq'], 1.0)) * 100
    print(f"[{r['datetime']}] Price: ${r['close']:,.1f} | CoinGlass: ${r['Actual_Long_Liq']:>12,.2f} | Model: ${r['Pred_Long_Liq']:>12,.2f} | Parity: {parity:>6.2f}%")

print("\nTop 5 Largest Short Liquidation Squeezes (Actual vs Model Prediction):")
for _, r in df_eval.sort_values("Actual_Short_Liq", ascending=False).head(5).iterrows():
    parity = (1.0 - abs(r['Actual_Short_Liq'] - r['Pred_Short_Liq']) / max(r['Actual_Short_Liq'], 1.0)) * 100
    print(f"[{r['datetime']}] Price: ${r['close']:,.1f} | CoinGlass: ${r['Actual_Short_Liq']:>12,.2f} | Model: ${r['Pred_Short_Liq']:>12,.2f} | Parity: {parity:>6.2f}%")
