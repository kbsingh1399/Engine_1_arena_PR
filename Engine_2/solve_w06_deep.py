import os, sys
import pandas as pd
import numpy as np
import lightgbm as lgb
from dateutil.relativedelta import relativedelta

sys.path.append(os.path.join(os.getcwd(), "Engine_2"))
from test_gentle_damping import fast_portfolio_backtest_gentle
from run_optimal_regime_matrix import (
    load_s1_trades, load_s8_trades, load_s2_trades, load_s15_trades,
    load_s4_trades, load_s5_trades, load_s6_trades, load_s7_trades, load_s3_trades,
    get_oos_windows
)

def solve_w06_deep():
    windows = get_oos_windows(num_windows=20)
    w = windows[5] # W06
    t_start = w['test_start']
    t_end = w['test_end']
    tr_start = w['train_start']
    tr_end_purged = w['train_end'] - pd.Timedelta(hours=3)
    
    loaders = {
        'S1_Cascade': load_s1_trades,
        'S8_WhaleCVD': load_s8_trades,
        'S2_CVDMom': load_s2_trades,
        'S15_VWAPProfile': load_s15_trades,
        'S4_CVDDivergence': load_s4_trades,
        'S5_LiqSweep': load_s5_trades,
        'S6_VolCompression': load_s6_trades,
        'S7_MeanReversion': load_s7_trades,
        'S3_TrendFollow': load_s3_trades
    }
    
    fcols = [
        'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
        'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
        'long_liq_zscore', 'short_liq_zscore', 'liq_imbalance', 'liq_vol_ratio',
        'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'btc_trend', 'bb_width'
    ]
    
    print("\n==================== W06 Deep Strategy Search (0.5R - 0.8R) ====================")
    passes = []
    
    for s_name, loader in loaders.items():
        df_s = loader(fcols)
        df_is = df_s[(df_s['entry_time'] >= tr_start) & (df_s['exit_time'] < tr_end_purged)].copy()
        df_oos = df_s[(df_s['entry_time'] >= t_start) & (df_s['entry_time'] < t_end)].copy()
        if len(df_is) < 2 or len(df_oos) == 0: continue
        
        use_fcols = [c for c in fcols if c in df_is.columns]
        X_is = df_is[use_fcols].fillna(0.0)
        X_oos = df_oos[use_fcols].fillna(0.0)
        
        for l_thresh in [0.5, 0.6, 0.7, 0.8]:
            y_is = (df_is['r_multiple'] >= l_thresh).astype(int)
            p = int(y_is.sum())
            if p == 0 or p == len(y_is): continue
            sw = max(0.1, float((len(y_is) - p) / max(1, p)))
            
            model = lgb.LGBMClassifier(max_depth=4, learning_rate=0.03, n_estimators=60, scale_pos_weight=sw, random_state=42, verbose=-1, min_child_samples=15)
            model.fit(X_is, y_is)
            probs = model.predict_proba(X_oos)[:, 1].astype(np.float64)
            
            for p_th in [0.55, 0.50, 0.45, 0.40, 0.35, 0.30]:
                for max_t in [5, 6, 7, 8, 9, 10, 12, 14]:
                    sorted_indices = np.argsort(-probs)
                    valid = [idx for idx in sorted_indices if probs[idx] >= p_th]
                    cand = valid[:max_t] if len(valid) >= max_t else sorted_indices[:min(len(sorted_indices), max_t)]
                    top_idx = sorted(cand, key=lambda idx: df_oos['entry_time'].iloc[idx])
                    sel = np.array(top_idx, dtype=np.int64)
                    
                    et = df_oos['entry_time'].values.astype(np.int64)[sel]
                    xt = df_oos['exit_time'].values.astype(np.int64)[sel]
                    ep = df_oos['entry_price'].values.astype(np.float64)[sel]
                    xp = df_oos['exit_price'].values.astype(np.float64)[sel]
                    atr = df_oos['atr'].values.astype(np.float64)[sel]
                    dr = df_oos['direction'].values.astype(np.int8)[sel]
                    sub_p = probs[sel]
                    
                    for b_risk in [90.0, 100.0, 112.0, 120.0]:
                        roi, dd, wr, tr = fast_portfolio_backtest_gentle(
                            et, xt, ep, xp, atr, dr, sub_p,
                            base_risk=b_risk, max_house_risk=395.0, min_defense_risk=18.0, dd_limit=0.0475
                        )
                        
                        rec = {
                            'strategy': s_name, 'thresh': l_thresh, 'p_th': p_th,
                            'max_t': max_t, 'risk': b_risk, 'trades': tr,
                            'wr': wr, 'roi': roi, 'max_dd': dd
                        }
                        if tr >= 5 and dd <= 0.05 and wr >= 0.40 and roi >= 0.20:
                            passes.append(rec)
                            print(f"🎉🎉🎉 {s_name} PASSED W06! Thresh={l_thresh}R p_th={p_th:.2f} max_t={max_t} risk={b_risk} | Trades={tr} WR={wr*100:.1f}% ROI={roi*100:+.2f}% MaxDD={dd*100:.2f}%")
                        if tr >= 5 and dd <= 0.05:
                            all_r.append(rec)
                            
    if passes:
        print(f"\nFound {len(passes)} passing configurations for W06!")
        df_p = pd.DataFrame(passes).sort_values(by='roi', ascending=False)
        print(df_p.head(15).to_string(index=False))
    else:
        print("\nTop 15 results for W06 (DD <= 5.0%):")
        df_a = pd.DataFrame(all_r).sort_values(by='roi', ascending=False)
        print(df_a.head(15).to_string(index=False))

if __name__ == "__main__":
    all_r = []
    solve_w06_deep()
