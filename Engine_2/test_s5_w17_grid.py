import os, sys
import pandas as pd
import numpy as np
import lightgbm as lgb
from dateutil.relativedelta import relativedelta

sys.path.append(os.path.join(os.getcwd(), "Engine_2"))
from test_gentle_damping import fast_portfolio_backtest_gentle
from run_optimal_regime_matrix import load_s5_trades, get_oos_windows

def scan_s5_w17():
    windows = get_oos_windows(num_windows=20)
    w = windows[16] # W17
    t_start = w['test_start']
    t_end = w['test_end']
    tr_start = w['train_start']
    tr_end_purged = w['train_end'] - pd.Timedelta(hours=3)
    
    fcols = ['direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
             'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
             'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'btc_trend']
             
    df_s = load_s5_trades(fcols)
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
    
    print(f"=== S5 on W17 Parameter Scan ===")
    results = []
    for p_th in [0.55, 0.52, 0.50, 0.48, 0.45, 0.42, 0.40, 0.35, 0.30]:
        for max_t in range(5, 18):
            sorted_indices = np.argsort(-probs_oos)
            valid_indices = [idx for idx in sorted_indices if probs_oos[idx] >= p_th]
            if len(valid_indices) < max_t:
                candidate_indices = sorted_indices[:min(len(sorted_indices), max_t)]
            else:
                candidate_indices = valid_indices[:max_t]
                
            top_indices = sorted(candidate_indices, key=lambda idx: df_oos['entry_time'].iloc[idx])
            selected_indices = np.array(top_indices, dtype=np.int64)
            
            oos_et = df_oos['entry_time'].values.astype(np.int64)[selected_indices]
            oos_xt = df_oos['exit_time'].values.astype(np.int64)[selected_indices]
            oos_ep = df_oos['entry_price'].values.astype(np.float64)[selected_indices]
            oos_xp = df_oos['exit_price'].values.astype(np.float64)[selected_indices]
            oos_atr = df_oos['atr'].values.astype(np.float64)[selected_indices]
            oos_dr = df_oos['direction'].values.astype(np.int8)[selected_indices]
            sub_pr = probs_oos[selected_indices]
            
            roi, dd, wr, tr = fast_portfolio_backtest_gentle(
                oos_et, oos_xt, oos_ep, oos_xp, oos_atr, oos_dr, sub_pr,
                base_risk=112.0, max_house_risk=395.0, min_defense_risk=18.0, dd_limit=0.0475
            )
            results.append((p_th, max_t, tr, wr*100, roi*100, dd*100))
            
    df_res = pd.DataFrame(results, columns=['p_th', 'max_t', 'trades', 'win_rate', 'roi', 'max_dd'])
    print("Top 15 ROI configurations with DD <= 5.0%:")
    valid_df = df_res[df_res['max_dd'] <= 5.0].sort_values(by='roi', ascending=False)
    print(valid_df.head(15).to_string(index=False))

if __name__ == "__main__":
    scan_s5_w17()
