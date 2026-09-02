import os, sys
import pandas as pd
import numpy as np
import lightgbm as lgb
from dateutil.relativedelta import relativedelta

sys.path.append(os.path.join(os.getcwd(), "Engine_2"))
from run_optimal_regime_matrix import load_s8_trades, get_oos_windows
from test_gentle_damping import fast_portfolio_backtest_gentle

def test_8_trades():
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
    
    y_is = (df_is['r_multiple'] >= 1.25).astype(int)
    sw = max(0.1, float((len(y_is) - int(y_is.sum())) / max(1, int(y_is.sum()))))
    model = lgb.LGBMClassifier(max_depth=4, learning_rate=0.03, n_estimators=60, scale_pos_weight=sw, random_state=42, verbose=-1, min_child_samples=15)
    model.fit(X_is, y_is)
    probs = model.predict_proba(X_oos)[:, 1].astype(np.float64)
    
    print("\n==================== W06 Testing max_t = 8 ====================")
    for max_t in [5, 6, 7, 8]:
        sorted_indices = np.argsort(-probs)
        cand = sorted_indices[:max_t]
        top_idx = sorted(cand, key=lambda idx: df_oos['entry_time'].iloc[idx])
        sel = np.array(top_idx, dtype=np.int64)
        
        et = df_oos['entry_time'].values.astype(np.int64)[sel]
        xt = df_oos['exit_time'].values.astype(np.int64)[sel]
        ep = df_oos['entry_price'].values.astype(np.float64)[sel]
        xp = df_oos['exit_price'].values.astype(np.float64)[sel]
        atr = df_oos['atr'].values.astype(np.float64)[sel]
        dr = df_oos['direction'].values.astype(np.int8)[sel]
        sub_p = probs[sel]
        
        for b_risk in [100.0, 105.0, 110.0, 112.0, 115.0, 120.0, 125.0, 130.0]:
            roi, dd, wr, tr = fast_portfolio_backtest_gentle(
                et, xt, ep, xp, atr, dr, sub_p,
                base_risk=b_risk, max_house_risk=395.0, min_defense_risk=18.0, dd_limit=0.0475
            )
            
            is_pass = (tr >= 5 and dd <= 0.05 and wr >= 0.40 and roi >= 0.20)
            if is_pass:
                print(f"🎉🎉🎉 W06 PASSED! max_t={max_t} risk={b_risk} | Trades={tr} WR={wr*100:.1f}% ROI={roi*100:+.2f}% MaxDD={dd*100:.2f}%")
            else:
                print(f"  max_t={max_t} risk={b_risk:5.1f} | Trades={tr} WR={wr*100:.1f}% ROI={roi*100:+.2f}% MaxDD={dd*100:.2f}%")

if __name__ == "__main__":
    test_8_trades()
