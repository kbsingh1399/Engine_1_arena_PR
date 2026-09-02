import os, sys
import pandas as pd
import numpy as np
import lightgbm as lgb
from dateutil.relativedelta import relativedelta

sys.path.append(os.path.join(os.getcwd(), "Engine_2"))
from run_optimal_regime_matrix import load_s3_trades, get_oos_windows

def inspect_s3():
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
        'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'btc_trend', 'bb_width'
    ]
    
    df_s = load_s3_trades(fcols)
    df_is = df_s[(df_s['entry_time'] >= tr_start) & (df_s['exit_time'] < tr_end_purged)].copy()
    df_oos = df_s[(df_s['entry_time'] >= t_start) & (df_s['entry_time'] < t_end)].copy()
    
    use_fcols = [c for c in fcols if c in df_is.columns]
    X_is = df_is[use_fcols].fillna(0.0)
    X_oos = df_oos[use_fcols].fillna(0.0)
    
    y_is = (df_is['r_multiple'] >= 0.5).astype(int)
    sw = max(0.1, float((len(y_is) - int(y_is.sum())) / max(1, int(y_is.sum()))))
    model = lgb.LGBMClassifier(max_depth=4, learning_rate=0.03, n_estimators=60, scale_pos_weight=sw, random_state=42, verbose=-1, min_child_samples=15)
    model.fit(X_is, y_is)
    probs = model.predict_proba(X_oos)[:, 1].astype(np.float64)
    
    sorted_indices = np.argsort(-probs)
    valid = [idx for idx in sorted_indices if probs[idx] >= 0.50]
    cand = valid[:9] if len(valid) >= 9 else sorted_indices[:9]
    top_idx = sorted(cand, key=lambda idx: df_oos['entry_time'].iloc[idx])
    sel = np.array(top_idx, dtype=np.int64)
    
    df_sel = df_oos.iloc[sel].copy()
    df_sel['prob'] = probs[sel]
    
    print("\n=== S3 Trades on W06 (Target 0.5R, max_t=9) ===")
    for i, (_, r) in enumerate(df_sel.iterrows()):
        stop_dist = max(2.0 * r['atr'], r['entry_price'] * 0.0065)
        r_mult = (r['exit_price'] - r['entry_price'])/stop_dist if r['direction'] == 1 else (r['entry_price'] - r['exit_price'])/stop_dist
        print(f"Trade {i+1} | Sym: {r['symbol']:<10} | Dir: {r['direction']:+d} | Prob: {r['prob']:.3f} | Entry: {r['entry_time']} | Exit: {r['exit_time']} | R: {r_mult:+5.2f}R")

if __name__ == "__main__":
    inspect_s3()
