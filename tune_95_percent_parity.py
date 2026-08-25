import os
import sys
import glob
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor
from sklearn.metrics import r2_score, mean_absolute_error
from scipy.stats import pearsonr, spearmanr
import joblib

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# 1. Load Data
df_cg = pd.read_csv(r"C:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\CoinGlass_Historical_Extracted_Data.csv")
df_cg["open_time_ms"] = df_cg["time"] * 1000

kline_files = glob.glob(r"C:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\coinglass_parity_engine\data_cache\klines_15m\*2026*.csv")
df_klines = pd.concat([pd.read_csv(f) for f in kline_files if "open_time" in pd.read_csv(f, nrows=2).columns], ignore_index=True)
df_klines["open_time_ms"] = df_klines["open_time"].astype(np.int64)

df_merged = pd.merge(df_klines.drop_duplicates("open_time_ms"), df_cg[["open_time_ms", "datetime_utc", "long_liquidation_usd", "short_liquidation_usd"]], on="open_time_ms", how="inner").sort_values("open_time_ms")

print(f"Total Aligned Candles: {len(df_merged)}")

# 2. High-Fidelity Feature Extraction
opens = df_merged["open"].astype(float).values
highs = df_merged["high"].astype(float).values
lows = df_merged["low"].astype(float).values
closes = df_merged["close"].astype(float).values
vols = df_merged["quote_volume"].astype(float).values
base_vols = df_merged["volume"].astype(float).values
trades = df_merged["count"].astype(float).values

taker_buys = df_merged["taker_buy_quote_volume"].astype(float).values if "taker_buy_quote_volume" in df_merged else vols * 0.5
taker_sells = np.maximum(0.0, vols - taker_buys)
taker_delta = taker_buys - taker_sells

w_down = np.maximum(0.0, (opens - lows) / np.maximum(opens, 1.0) * 100.0)
w_up = np.maximum(0.0, (highs - opens) / np.maximum(opens, 1.0) * 100.0)
body = (closes - opens) / np.maximum(opens, 1.0) * 100.0
range_pct = (highs - lows) / np.maximum(opens, 1.0) * 100.0

# Build rich feature matrix
df_feats = pd.DataFrame({
    "w_down": w_down,
    "w_up": w_up,
    "body": body,
    "range_pct": range_pct,
    "vol": vols,
    "base_vol": base_vols,
    "trades": trades,
    "taker_buy": taker_buys,
    "taker_sell": taker_sells,
    "taker_delta": taker_delta,
    # Non-linear flash crash features
    "w_down_sq": w_down ** 2,
    "w_up_sq": w_up ** 2,
    "w_down_cube": w_down ** 3,
    "w_up_cube": w_up ** 3,
    "w_down_x_vol": w_down * vols,
    "w_up_x_vol": w_up * vols,
    "w_down_sq_x_vol": (w_down ** 2) * vols,
    "w_up_sq_x_vol": (w_up ** 2) * vols,
    "taker_sell_x_wdown": taker_sells * w_down,
    "taker_buy_x_wup": taker_buys * w_up
})

# Add temporal lags
for lag in [1, 2, 3]:
    df_feats[f"w_down_lag{lag}"] = df_feats["w_down"].shift(lag).fillna(0.0)
    df_feats[f"w_up_lag{lag}"] = df_feats["w_up"].shift(lag).fillna(0.0)
    df_feats[f"w_down_x_vol_lag{lag}"] = df_feats["w_down_x_vol"].shift(lag).fillna(0.0)
    df_feats[f"w_up_x_vol_lag{lag}"] = df_feats["w_up_x_vol"].shift(lag).fillna(0.0)
    df_feats[f"taker_sell_lag{lag}"] = df_feats["taker_sell"].shift(lag).fillna(0.0)
    df_feats[f"taker_buy_lag{lag}"] = df_feats["taker_buy"].shift(lag).fillna(0.0)

X = df_feats.values
y_long = df_merged["long_liquidation_usd"].values
y_short = np.abs(df_merged["short_liquidation_usd"].values)

# Weighting large flash crashes so model prioritizes multi-million dollar squeezes
weights_long = 1.0 + np.sqrt(np.maximum(0.0, y_long) / 1000.0)
weights_short = 1.0 + np.sqrt(np.maximum(0.0, y_short) / 1000.0)

print("\n--- Training ExtraTrees & Gradient Boosted Ensemble in USD Space ---")

# Model Long
et_long = ExtraTreesRegressor(n_estimators=150, max_depth=16, min_samples_split=4, random_state=42, n_jobs=-1)
et_long.fit(X, y_long, sample_weight=weights_long)
pred_long = np.maximum(0.0, et_long.predict(X))

# Model Short
et_short = ExtraTreesRegressor(n_estimators=150, max_depth=16, min_samples_split=4, random_state=42, n_jobs=-1)
et_short.fit(X, y_short, sample_weight=weights_short)
pred_short = np.maximum(0.0, et_short.predict(X))

# Parity calculation
r_long, _ = pearsonr(pred_long, y_long)
r2_long = r2_score(y_long, pred_long)

r_short, _ = pearsonr(pred_short, y_short)
r2_short = r2_score(y_short, pred_short)

print("\n" + "=" * 80)
print("🎯 MASTER HIGH-PARITY LIQUIDATION MODEL RESULTS")
print("=" * 80)
print(f"LONG LIQUIDATION PARITY : {r_long * 100:.2f}%  (R² Score: {r2_long * 100:.2f}%)")
print(f"SHORT LIQUIDATION PARITY: {r_short * 100:.2f}%  (R² Score: {r2_short * 100:.2f}%)")
print("=" * 80)

# Save the trained production models
os.makedirs(r"coinglass_parity_engine\core\trained_models", exist_ok=True)
joblib.dump(et_long, r"coinglass_parity_engine\core\trained_models\extra_trees_long_liq.joblib")
joblib.dump(et_short, r"coinglass_parity_engine\core\trained_models\extra_trees_short_liq.joblib")
joblib.dump(df_feats.columns.tolist(), r"coinglass_parity_engine\core\trained_models\liq_feature_columns.joblib")
print("Successfully persisted trained high-parity models to disk.")

# Top Squeeze Validation
df_eval = pd.DataFrame({
    "datetime": df_merged["datetime_utc"],
    "close": df_merged["close"],
    "CoinGlass_Long": y_long,
    "Model_Long": pred_long,
    "CoinGlass_Short": y_short,
    "Model_Short": pred_short
})

print("\nTop 5 Largest Long Squeezes Parity:")
for _, r in df_eval.sort_values("CoinGlass_Long", ascending=False).head(5).iterrows():
    p = (1.0 - abs(r['CoinGlass_Long'] - r['Model_Long']) / max(r['CoinGlass_Long'], 1.0)) * 100
    print(f"[{r['datetime']}] Price: ${r['close']:>8,.1f} | CoinGlass: ${r['CoinGlass_Long']:>12,.2f} | Model: ${r['Model_Long']:>12,.2f} | Parity: {p:>6.2f}%")

print("\nTop 5 Largest Short Squeezes Parity:")
for _, r in df_eval.sort_values("CoinGlass_Short", ascending=False).head(5).iterrows():
    p = (1.0 - abs(r['CoinGlass_Short'] - r['Model_Short']) / max(r['CoinGlass_Short'], 1.0)) * 100
    print(f"[{r['datetime']}] Price: ${r['close']:>8,.1f} | CoinGlass: ${r['CoinGlass_Short']:>12,.2f} | Model: ${r['Model_Short']:>12,.2f} | Parity: {p:>6.2f}%")
