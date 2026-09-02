import os, sys, glob, gc
import pandas as pd
import numpy as np
import lightgbm as lgb

sys.path.append(os.path.join(os.getcwd(), "Engine_2"))
from s1_liquidation_cascade import load_s1_trades
from s8_hybrid_whale_cvd import load_s8_trades
from s5_liquidity_sweep_reversal import load_s5_trades
from s15_vwap_profile_conviction import load_s15_trades

fcols = [
    'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
    'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
    'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'btc_trend'
]

# Check W17: 2025-06-15 to 2025-07-15
t_start = pd.Timestamp("2025-06-15", tz='UTC')
t_end = pd.Timestamp("2025-07-15", tz='UTC')
t_is_start = t_start - pd.DateOffset(months=18)

df_s8 = load_s8_trades(fcols)
df_is = df_s8[(df_s8['entry_time'] >= t_is_start) & (df_s8['entry_time'] < t_start)].copy()
df_oos = df_s8[(df_s8['entry_time'] >= t_start) & (df_s8['entry_time'] < t_end)].copy()

X_is = df_is[fcols].fillna(0.0)
y_is = df_is['label'].astype(int)
p = y_is.sum()
sw = max(0.1, float((len(y_is) - p) / p))

model = lgb.LGBMClassifier(max_depth=4, learning_rate=0.03, n_estimators=60, scale_pos_weight=sw, random_state=42, verbose=-1, min_child_samples=15, n_jobs=2)
model.fit(X_is, y_is)

X_oos = df_oos[fcols].fillna(0.0)
df_oos['prob'] = model.predict_proba(X_oos)[:, 1]
df_oos_sorted = df_oos.sort_values('prob', ascending=False).reset_index(drop=True)

print("Top 15 trades by probability in W17 for S8:")
for i in range(min(15, len(df_oos_sorted))):
    row = df_oos_sorted.iloc[i]
    print(f"Rank {i+1}: sym={row['symbol']} dir={row['direction']} prob={row['prob']:.4f} R={row['r_multiple']:.2f}R entry={row['entry_time']}")

print("\nWhere are the +5.50R winners ranked in df_oos_sorted?")
winners_55 = df_oos_sorted[df_oos_sorted['r_multiple'] >= 5.0]
for idx, row in winners_55.iterrows():
    print(f"Rank {idx+1}/{len(df_oos_sorted)}: sym={row['symbol']} prob={row['prob']:.4f} R={row['r_multiple']:.2f}R")
