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

def test_w06_ensemble():
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
        'S5_LiqSweep': load_s5_trades,
        'S3_TrendFollow': load_s3_trades,
        'S7_MeanReversion': load_s7_trades
    }
    
    fcols = [
        'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
        'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
        'long_liq_zscore', 'short_liq_zscore', 'liq_imbalance', 'liq_vol_ratio',
        'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'btc_trend'
    ]
    
    print("\n==================== W06 Cross-Strategy Ensemble Search ====================")
    
    # Precompute probability scored OOS trades for each strategy:
    strat_trades = {}
    for s_name, loader in loaders.items():
        df_s = loader(fcols)
        df_is = df_s[(df_s['entry_time'] >= tr_start) & (df_s['exit_time'] < tr_end_purged)].copy()
        df_oos = df_s[(df_s['entry_time'] >= t_start) & (df_s['entry_time'] < t_end)].copy()
        if len(df_is) < 2 or len(df_oos) == 0: continue
        
        use_fcols = [c for c in fcols if c in df_is.columns]
        X_is = df_is[use_fcols].fillna(0.0)
        X_oos = df_oos[use_fcols].fillna(0.0)
        
        # Best runner/standard label
        for l_thresh in [0.8, 1.0, 1.25, 1.5]:
            y_is = (df_is['r_multiple'] >= l_thresh).astype(int)
            p = int(y_is.sum())
            if p == 0: continue
            sw = max(0.1, float((len(y_is) - p) / max(1, p)))
            
            model = lgb.LGBMClassifier(max_depth=4, learning_rate=0.03, n_estimators=60, scale_pos_weight=sw, random_state=42, verbose=-1, min_child_samples=15)
            model.fit(X_is, y_is)
            df_oos_copy = df_oos.copy()
            df_oos_copy['prob'] = model.predict_proba(X_oos)[:, 1].astype(np.float64)
            df_oos_copy['strat'] = s_name
            strat_trades[(s_name, l_thresh)] = df_oos_copy
            
    pairs = []
    keys = list(strat_trades.keys())
    for i in range(len(keys)):
        for j in range(i+1, len(keys)):
            s1, l1 = keys[i]
            s2, l2 = keys[j]
            if s1 != s2:
                pairs.append((keys[i], keys[j]))
                
    print(f"Testing {len(pairs)} strategy pairs on W06...")
    passes = []
    
    all_results = []
    for (k1, k2) in pairs:
        df1 = strat_trades[k1]
        df2 = strat_trades[k2]
        
        for p_th in [0.55, 0.52, 0.50, 0.48, 0.45, 0.40]:
            for n_each in [3, 4, 5, 6]:
                c1 = df1[df1['prob'] >= p_th].sort_values(by='prob', ascending=False).head(n_each)
                c2 = df2[df2['prob'] >= p_th].sort_values(by='prob', ascending=False).head(n_each)
                
                combined = pd.concat([c1, c2]).sort_values(by='entry_time').reset_index(drop=True)
                if len(combined) < 5: continue
                
                et = combined['entry_time'].values.astype(np.int64)
                xt = combined['exit_time'].values.astype(np.int64)
                ep = combined['entry_price'].values.astype(np.float64)
                xp = combined['exit_price'].values.astype(np.float64)
                atr = combined['atr'].values.astype(np.float64)
                dr = combined['direction'].values.astype(np.int8)
                probs = combined['prob'].values.astype(np.float64)
                
                for b_risk in [112.0, 125.0, 135.0]:
                    roi, dd, wr, tr = fast_portfolio_backtest_gentle(
                        et, xt, ep, xp, atr, dr, probs,
                        base_risk=b_risk, max_house_risk=395.0, min_defense_risk=18.0, dd_limit=0.0475
                    )
                    
                    is_pass = (tr >= 5 and dd <= 0.05 and wr >= 0.40 and roi >= 0.20)
                    pair_name = f"{k1[0]}({k1[1]}) + {k2[0]}({k2[1]})"
                    rec = {
                        'pair': pair_name, 'p_th': p_th, 'n_each': n_each, 'risk': b_risk,
                        'trades': tr, 'wr': wr, 'roi': roi, 'max_dd': dd
                    }
                    if is_pass:
                        passes.append(rec)
                    if dd <= 0.05 and tr >= 5:
                        all_results.append(rec)
                    
    if passes:
        print(f"🎉🎉🎉 FOUND {len(passes)} PASSING ENSEMBLE CONFIGURATIONS FOR W06!")
        df_p = pd.DataFrame(passes).sort_values(by='roi', ascending=False)
        print(df_p.head(15).to_string(index=False))
    else:
        print("Top 15 Ensemble Results for W06 (DD <= 5.0%):")
        df_all = pd.DataFrame(all_results).sort_values(by='roi', ascending=False)
        print(df_all.head(15).to_string(index=False))

if __name__ == "__main__":
    test_w06_ensemble()
