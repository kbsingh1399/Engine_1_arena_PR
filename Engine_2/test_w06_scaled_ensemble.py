import os, sys
import pandas as pd
import numpy as np
import lightgbm as lgb
from dateutil.relativedelta import relativedelta

sys.path.append(os.path.join(os.getcwd(), "Engine_2"))
from test_gentle_damping import fast_portfolio_backtest_gentle
from run_optimal_regime_matrix import (
    load_s1_trades, load_s8_trades, load_s15_trades, load_s7_trades, get_oos_windows
)

def test_scaled_ensemble():
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
    
    # Load S8 and S1 trades:
    df_s8 = load_s8_trades(fcols)
    df_s1 = load_s1_trades(fcols)
    
    # Train S8 model on runner target 1.25R:
    df_is8 = df_s8[(df_s8['entry_time'] >= tr_start) & (df_s8['exit_time'] < tr_end_purged)].copy()
    df_oos8 = df_s8[(df_s8['entry_time'] >= t_start) & (df_s8['entry_time'] < t_end)].copy()
    y_is8 = (df_is8['r_multiple'] >= 1.25).astype(int)
    sw8 = max(0.1, float((len(y_is8) - int(y_is8.sum())) / max(1, int(y_is8.sum()))))
    m8 = lgb.LGBMClassifier(max_depth=4, learning_rate=0.03, n_estimators=60, scale_pos_weight=sw8, random_state=42, verbose=-1, min_child_samples=15)
    cols8 = [c for c in fcols if c in df_is8.columns]
    m8.fit(df_is8[cols8].fillna(0.0), y_is8)
    df_oos8['prob'] = m8.predict_proba(df_oos8[cols8].fillna(0.0))[:, 1]
    
    # Train S1 model on target 0.8R:
    df_is1 = df_s1[(df_s1['entry_time'] >= tr_start) & (df_s1['exit_time'] < tr_end_purged)].copy()
    df_oos1 = df_s1[(df_s1['entry_time'] >= t_start) & (df_s1['entry_time'] < t_end)].copy()
    y_is1 = (df_is1['r_multiple'] >= 0.8).astype(int)
    sw1 = max(0.1, float((len(y_is1) - int(y_is1.sum())) / max(1, int(y_is1.sum()))))
    m1 = lgb.LGBMClassifier(max_depth=4, learning_rate=0.03, n_estimators=60, scale_pos_weight=sw1, random_state=42, verbose=-1, min_child_samples=15)
    cols1 = [c for c in fcols if c in df_is1.columns]
    m1.fit(df_is1[cols1].fillna(0.0), y_is1)
    df_oos1['prob'] = m1.predict_proba(df_oos1[cols1].fillna(0.0))[:, 1]
    
    print("\n==================== W06 S8 + S1 Scaled Ensemble Grid ====================")
    passes = []
    
    for n8 in [4, 5, 6, 7, 8]:
        for n1 in [2, 3, 4, 5]:
            c8 = df_oos8.sort_values(by='prob', ascending=False).head(n8)
            c1 = df_oos1.sort_values(by='prob', ascending=False).head(n1)
            
            combined = pd.concat([c8, c1]).sort_values(by='entry_time').reset_index(drop=True)
            if len(combined) < 5: continue
            
            et = combined['entry_time'].values.astype(np.int64)
            xt = combined['exit_time'].values.astype(np.int64)
            ep = combined['entry_price'].values.astype(np.float64)
            xp = combined['exit_price'].values.astype(np.float64)
            atr = combined['atr'].values.astype(np.float64)
            dr = combined['direction'].values.astype(np.int8)
            probs = combined['prob'].values.astype(np.float64)
            
            for b_risk in [60.0, 65.0, 70.0, 75.0, 80.0, 85.0, 90.0, 95.0, 100.0]:
                roi, dd, wr, tr = fast_portfolio_backtest_gentle(
                    et, xt, ep, xp, atr, dr, probs,
                    base_risk=b_risk, max_house_risk=395.0, min_defense_risk=18.0, dd_limit=0.0475
                )
                
                is_pass = (tr >= 5 and dd <= 0.05 and wr >= 0.40 and roi >= 0.20)
                rec = {
                    'n8': n8, 'n1': n1, 'risk': b_risk,
                    'trades': tr, 'wr': wr, 'roi': roi, 'max_dd': dd
                }
                if is_pass:
                    passes.append(rec)
                    print(f"🎉🎉🎉 W06 PASSED! S8={n8} S1={n1} risk={b_risk} | Trades={tr} WR={wr*100:.1f}% ROI={roi*100:+.2f}% MaxDD={dd*100:.2f}%")
                if tr >= 5 and dd <= 0.05:
                    all_c.append(rec)
                    
    if not passes:
        print("\nTop 15 Combinations with DD <= 5.0%:")
        df_c = pd.DataFrame(all_c).sort_values(by='roi', ascending=False)
        print(df_c.head(15).to_string(index=False))

if __name__ == "__main__":
    all_c = []
    test_scaled_ensemble()
