import os, sys, glob, gc
import pandas as pd
import numpy as np
import lightgbm as lgb

sys.path.append(os.path.join(os.getcwd(), "Engine_2"))
from s8_hybrid_whale_cvd import load_s8_trades

fcols = [
    'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
    'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
    'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'btc_trend',
    'trend_alignment'
]

df_s8 = load_s8_trades(fcols[:-1])
df_s8['trend_alignment'] = df_s8['direction'] * df_s8['btc_trend']

for win_name, (t_start_s, t_end_s) in [
    ("W17", ("2025-06-15", "2025-07-15")),
    ("W10", ("2023-09-15", "2023-10-15")),
    ("W01", ("2021-06-15", "2021-07-15")),
    ("W04", ("2022-03-15", "2022-04-15")),
]:
    t_start = pd.Timestamp(t_start_s, tz='UTC')
    t_end = pd.Timestamp(t_end_s, tz='UTC')
    t_is_start = t_start - pd.DateOffset(months=18)

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
    
    # Check top 8 trades
    df_top = df_oos.sort_values('prob', ascending=False).head(8)
    wr = (df_top['r_multiple'] > 0).mean() * 100
    sum_r = df_top['r_multiple'].sum()
    print(f"{win_name}: Top 8 trades with trend_alignment: WR={wr:.1f}% | Total R={sum_r:.2f}R")
    for _, r in df_top.iterrows():
        print(f"   sym={r['symbol']} dir={r['direction']} btc_tr={r['btc_trend']} align={r['trend_alignment']} prob={r['prob']:.4f} R={r['r_multiple']:.2f}R")
