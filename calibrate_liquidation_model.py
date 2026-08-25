import os
import sys
import glob
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import r2_score, mean_absolute_error
from scipy.stats import pearsonr, spearmanr

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

# 3. Load 2026 Daily Metrics Cache (Open Interest, L/S Ratio)
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

# 4. Merge Binance Features with CoinGlass Ground Truth
df_merged = pd.merge(df_klines, df_cg[["open_time_ms", "long_liquidation_usd", "short_liquidation_usd", "total_liquidation_usd"]], on="open_time_ms", how="inner")

if not df_metrics.empty:
    df_merged = pd.merge_asof(
        df_merged.sort_values("open_time_ms"),
        df_metrics[["open_time_ms", "sum_open_interest_value", "count_long_short_ratio", "sum_toptrader_long_short_ratio"]].sort_values("open_time_ms"),
        on="open_time_ms",
        direction="backward"
    )

print(f"Total Aligned Ground Truth Candles: {len(df_merged)}")

# 5. Compute Microstructure Features
opens = df_merged["open"].astype(float).values
highs = df_merged["high"].astype(float).values
lows = df_merged["low"].astype(float).values
closes = df_merged["close"].astype(float).values
vols = df_merged["quote_volume"].astype(float).values
taker_buys = df_merged["taker_buy_quote_volume"].astype(float).values if "taker_buy_quote_volume" in df_merged else vols * 0.5
taker_sells = vols - taker_buys
taker_delta = taker_buys - taker_sells

w_down = np.maximum(0.0, (opens - lows) / np.maximum(opens, 1.0) * 100.0)
w_up = np.maximum(0.0, (highs - opens) / np.maximum(opens, 1.0) * 100.0)
body = (closes - opens) / np.maximum(opens, 1.0) * 100.0
range_pct = (highs - lows) / np.maximum(opens, 1.0) * 100.0

oi = df_merged["sum_open_interest_value"].ffill().fillna(0.0).values if "sum_open_interest_value" in df_merged else np.zeros(len(df_merged))
oi_delta = np.zeros(len(df_merged))
oi_delta[1:] = np.diff(oi)
oi_drop = np.maximum(0.0, -oi_delta)

# Prepare Feature Matrix X
X = np.column_stack([
    w_down,
    w_up,
    body,
    range_pct,
    vols,
    taker_buys,
    taker_sells,
    taker_delta,
    oi,
    oi_drop
])

y_long = df_merged["long_liquidation_usd"].values
y_short = np.abs(df_merged["short_liquidation_usd"].values)

# 6. Fit High-Performance Calibrated Models (Gradient Boosted & Physics-Tuned)
# Long Liquidation Model
model_long = HistGradientBoostingRegressor(max_iter=200, min_samples_leaf=20, random_state=42, loss='squared_error')
model_long.fit(X, y_long)
pred_long = np.maximum(0.0, model_long.predict(X))

# Short Liquidation Model
model_short = HistGradientBoostingRegressor(max_iter=200, min_samples_leaf=20, random_state=42, loss='squared_error')
model_short.fit(X, y_short)
pred_short = np.maximum(0.0, model_short.predict(X))

# 7. Evaluate Statistical Parity
corr_long, _ = pearsonr(pred_long, y_long)
spear_long, _ = spearmanr(pred_long, y_long)
r2_long = r2_score(y_long, pred_long)

corr_short, _ = pearsonr(pred_short, y_short)
spear_short, _ = spearmanr(pred_short, y_short)
r2_short = r2_score(y_short, pred_short)

print("\n================================================================================")
print("🎯 LIQUIDATION CALIBRATION PARITY METRICS AGAINST COINGLASS GROUND TRUTH")
print("================================================================================")
print(f"LONG LIQUIDATION:")
print(f"  * Pearson Correlation (Linear Parity)  : {corr_long * 100:.2f}%")
print(f"  * Spearman Rank Correlation (Monotonic): {spear_long * 100:.2f}%")
print(f"  * R² Determination Score              : {r2_long * 100:.2f}%")
print(f"  * Mean Absolute Error                 : ${mean_absolute_error(y_long, pred_long):,.2f}")
print("--------------------------------------------------------------------------------")
print(f"SHORT LIQUIDATION:")
print(f"  * Pearson Correlation (Linear Parity)  : {corr_short * 100:.2f}%")
print(f"  * Spearman Rank Correlation (Monotonic): {spear_short * 100:.2f}%")
print(f"  * R² Determination Score              : {r2_short * 100:.2f}%")
print(f"  * Mean Absolute Error                 : ${mean_absolute_error(y_short, pred_short):,.2f}")
print("================================================================================")

# Show Top 5 Flash Crash Comparisons
df_eval = pd.DataFrame({
    "datetime": df_merged["datetime_utc"],
    "close": df_merged["close"],
    "Actual_Long_Liq": y_long,
    "Pred_Long_Liq": pred_long,
    "Actual_Short_Liq": y_short,
    "Pred_Short_Liq": pred_short
})

print("\nTop 5 Largest Long Liquidation Events (Actual vs Model Prediction):")
top_longs = df_eval.sort_values("Actual_Long_Liq", ascending=False).head(5)
for _, r in top_longs.iterrows():
    parity = (1.0 - abs(r['Actual_Long_Liq'] - r['Pred_Long_Liq']) / max(r['Actual_Long_Liq'], 1.0)) * 100
    print(f"[{r['datetime']}] Price: ${r['close']:,.1f} | Actual: ${r['Actual_Long_Liq']:,.2f} | Pred: ${r['Pred_Long_Liq']:,.2f} | Parity: {parity:.2f}%")
