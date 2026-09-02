import os, sys
import pandas as pd
import numpy as np
import lightgbm as lgb
from dateutil.relativedelta import relativedelta

sys.path.append(os.path.join(os.getcwd(), "Engine_2"))
from run_optimal_regime_matrix import load_s8_trades, get_oos_windows
from test_directional_concurrency import backtest_directional_concurrency

def trace_w06_trades():
    windows = get_oos_windows(num_windows=20)
    w = windows[5] # W06
    t_start = w['test_start']
    t_end = w['test_end']
    tr_start = w['train_start']
    tr_end_purged = w['train_end'] - pd.Timedelta(hours=3)
    
    fcols = [
        'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
        'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
        'long_liq_zscore', 'short_liq_zscore', 'liq_imbalance', 'liq_vol_ratio',
        'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'btc_trend'
    ]
    
    df_s = load_s8_trades(fcols)
    df_is = df_s[(df_s['entry_time'] >= tr_start) & (df_s['exit_time'] < tr_end_purged)].copy()
    df_oos = df_s[(df_s['entry_time'] >= t_start) & (df_s['entry_time'] < t_end)].copy()
    
    use_fcols = [c for c in fcols if c in df_is.columns]
    X_is = df_is[use_fcols].fillna(0.0)
    X_oos = df_oos[use_fcols].fillna(0.0)
    
    y_is = (df_is['r_multiple'] >= 0.8).astype(int)
    sw = max(0.1, float((len(y_is) - int(y_is.sum())) / max(1, int(y_is.sum()))))
    model = lgb.LGBMClassifier(max_depth=4, learning_rate=0.03, n_estimators=60, scale_pos_weight=sw, random_state=42, verbose=-1, min_child_samples=15)
    model.fit(X_is, y_is)
    probs = model.predict_proba(X_oos)[:, 1].astype(np.float64)
    
    sorted_indices = np.argsort(-probs)
    valid = [idx for idx in sorted_indices if probs[idx] >= 0.50]
    cand = valid[:15] if len(valid) >= 15 else sorted_indices[:15]
    top_idx = sorted(cand, key=lambda idx: df_oos['entry_time'].iloc[idx])
    sel = np.array(top_idx, dtype=np.int64)
    
    et = df_oos['entry_time'].values.astype(np.int64)[sel]
    xt = df_oos['exit_time'].values.astype(np.int64)[sel]
    ep = df_oos['entry_price'].values.astype(np.float64)[sel]
    xp = df_oos['exit_price'].values.astype(np.float64)[sel]
    atr = df_oos['atr'].values.astype(np.float64)[sel]
    dr = df_oos['direction'].values.astype(np.int8)[sel]
    sub_p = probs[sel]
    
    print("\nTracing step-by-step trades for S8 on W06...")
    cap = 5000.0
    peak = 5000.0
    for i in range(len(sel)):
        stop_dist = max(2.0 * atr[i], ep[i] * 0.0065)
        r_mult = (xp[i] - ep[i])/stop_dist if dr[i] == 1 else (ep[i] - xp[i])/stop_dist
        sym = df_oos['symbol'].iloc[sel[i]]
        ent = df_oos['entry_time'].iloc[sel[i]]
        p = sub_p[i]
        print(f"Step {i+1} | Sym: {sym:<10} | Dir: {dr[i]:+d} | Prob: {p:.3f} | Entry: {ent} | R: {r_mult:+5.2f}R")

if __name__ == "__main__":
    trace_w06_trades()
