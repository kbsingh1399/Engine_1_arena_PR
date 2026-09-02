import os, sys
import pandas as pd
import numpy as np
import lightgbm as lgb
from dateutil.relativedelta import relativedelta

sys.path.append(os.path.join(os.getcwd(), "Engine_2"))
from run_optimal_regime_matrix import (
    load_s1_trades, load_s5_trades, load_s7_trades, get_oos_windows
)

def inspect_w(w_num, strat_loader, s_name, fcols):
    windows = get_oos_windows(num_windows=20)
    w = windows[w_num - 1]
    t_start = w['test_start']
    t_end = w['test_end']
    tr_start = w['train_start']
    tr_end_purged = w['train_end'] - pd.Timedelta(hours=3)
    
    df_s = strat_loader(fcols)
    df_is = df_s[(df_s['entry_time'] >= tr_start) & (df_s['exit_time'] < tr_end_purged)].copy()
    df_oos = df_s[(df_s['entry_time'] >= t_start) & (df_s['entry_time'] < t_end)].copy()
    
    fcols = [c for c in fcols if c in df_is.columns]
    X_is = df_is[fcols].fillna(0.0)
    y_is = df_is['label'].astype(int)
    p = int(y_is.sum())
    sw = max(0.1, float((len(y_is) - p) / max(1, p)))
    
    model = lgb.LGBMClassifier(max_depth=4, learning_rate=0.03, n_estimators=60, scale_pos_weight=sw, random_state=42, verbose=-1, min_child_samples=15)
    model.fit(X_is, y_is)
    
    X_oos = df_oos[fcols].fillna(0.0)
    probs_oos = model.predict_proba(X_oos)[:, 1].astype(np.float64)
    df_oos['prob'] = probs_oos
    
    df_sorted = df_oos.sort_values(by='prob', ascending=False)
    print(f"\n=== {s_name} in W{w_num:02d} ({t_start.strftime('%Y-%m-%d')} to {t_end.strftime('%Y-%m-%d')}) ===")
    print(f"Total OOS Candidates: {len(df_oos)}")
    
    for i, (_, row) in enumerate(df_sorted.head(15).iterrows()):
        ret = (row['exit_price'] - row['entry_price'])/row['entry_price'] if row['direction'] == 1 else (row['entry_price'] - row['exit_price'])/row['entry_price']
        stop_dist = max(2.0 * row['atr'], row['entry_price'] * 0.0065)
        r_mult = (row['exit_price'] - row['entry_price'])/stop_dist if row['direction'] == 1 else (row['entry_price'] - row['exit_price'])/stop_dist
        print(f"Rank {i+1:2d} | Prob: {row['prob']:.3f} | Sym: {row['symbol']:<10} | Dir: {row['direction']:+d} | Entry: {row['entry_time']} | R: {r_mult:+5.2f}R | RawRet: {ret*100:+5.2f}%")

if __name__ == "__main__":
    fcols_s5 = ['direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
                 'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
                 'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'btc_trend']
    inspect_w(17, load_s5_trades, 'S5_LiqSweep', fcols_s5)
    
    fcols_s1 = ['direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
                 'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
                 'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'btc_trend']
    inspect_w(1, load_s1_trades, 'S1_Cascade', fcols_s1)
