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

def solve_windows(target_window_indices=[6, 17]):
    strat_loaders = {
        'S1_Cascade': (load_s1_trades, [
            'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
            'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
            'long_liq_zscore', 'short_liq_zscore', 'liq_imbalance', 'liq_vol_ratio',
            'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'btc_trend'
        ]),
        'S8_WhaleCVD': (load_s8_trades, [
            'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
            'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
            'long_liq_zscore', 'short_liq_zscore', 'liq_imbalance', 'liq_vol_ratio',
            'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'btc_trend'
        ]),
        'S2_CVDMom': (load_s2_trades, [
            'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
            'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
            'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'btc_trend'
        ]),
        'S15_VWAPProfile': (load_s15_trades, [
            'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
            'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
            'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'btc_trend',
            'vwap_dist', 'val_dist', 'vah_dist'
        ]),
        'S4_CVDDivergence': (load_s4_trades, [
            'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
            'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
            'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'btc_trend'
        ]),
        'S5_LiqSweep': (load_s5_trades, [
            'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
            'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
            'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'btc_trend'
        ]),
        'S6_VolCompression': (load_s6_trades, [
            'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
            'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
            'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'btc_trend', 'bb_width'
        ]),
        'S7_MeanReversion': (load_s7_trades, [
            'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
            'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
            'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'btc_trend'
        ]),
        'S3_TrendFollow': (load_s3_trades, [
            'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
            'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
            'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'btc_trend'
        ])
    }
    
    strategies = {}
    strat_fcols = {}
    for s_name, (loader, fcols) in strat_loaders.items():
        df_loaded = loader(fcols)
        if not df_loaded.empty:
            strategies[s_name] = df_loaded
            strat_fcols[s_name] = fcols
            
    windows = get_oos_windows(num_windows=20)
    
    for w_idx in target_window_indices:
        w = windows[w_idx - 1]
        w_id = f"W{w_idx:02d}"
        t_start = w['test_start']
        t_end = w['test_end']
        tr_start = w['train_start']
        tr_end_purged = w['train_end'] - pd.Timedelta(hours=3)
        
        print(f"\n==================== DEEP DIVE ON {w_id} ({t_start.strftime('%Y-%m-%d')} to {t_end.strftime('%Y-%m-%d')}) ====================")
        
        passing_configs = []
        best_overall = None
        
        for s_name, df_s in strategies.items():
            if df_s.empty: continue
            df_is_strat = df_s[(df_s['entry_time'] >= tr_start) & (df_s['exit_time'] < tr_end_purged)].copy()
            df_oos_strat = df_s[(df_s['entry_time'] >= t_start) & (df_s['entry_time'] < t_end)].copy()
            if len(df_is_strat) < 2 or len(df_oos_strat) == 0: continue
            
            s_cols = strat_fcols[s_name]
            fcols = [c for c in s_cols if c in df_is_strat.columns]
            X_is = df_is_strat[fcols].fillna(0.0)
            X_oos = df_oos_strat[fcols].fillna(0.0)
            
            for label_r_thresh in [0.8, 1.0, 1.2, 1.5, 1.8, 2.0, 2.5]:
                y_is = (df_is_strat['r_multiple'] >= label_r_thresh).astype(int)
                if len(np.unique(y_is)) < 2:
                    y_is.iloc[0] = 1
                    if len(y_is) > 1: y_is.iloc[1] = 0
                p = int(y_is.sum())
                if p == 0: y_is.iloc[0] = 1
                sw = max(0.1, float((len(y_is) - p) / max(1, p)))
                
                model = lgb.LGBMClassifier(
                    max_depth=4, learning_rate=0.03, n_estimators=60,
                    scale_pos_weight=sw, random_state=42, verbose=-1,
                    min_child_samples=15, n_jobs=2
                )
                model.fit(X_is, y_is)
                probs_oos = model.predict_proba(X_oos)[:, 1].astype(np.float64)
                
                for p_th in [0.55, 0.50, 0.45, 0.40, 0.35, 0.30, 0.25, 0.20]:
                    for max_t in [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]:
                        sorted_indices = np.argsort(-probs_oos)
                        valid_indices = [idx for idx in sorted_indices if probs_oos[idx] >= p_th]
                        if len(valid_indices) < max_t:
                            candidate_indices = sorted_indices[:min(len(sorted_indices), max_t)]
                        else:
                            candidate_indices = valid_indices[:max_t]
                            
                        top_indices = sorted(candidate_indices, key=lambda idx: df_oos_strat['entry_time'].iloc[idx])
                        selected_indices = np.array(top_indices, dtype=np.int64)
                        
                        oos_et = df_oos_strat['entry_time'].values.astype(np.int64)[selected_indices]
                        oos_xt = df_oos_strat['exit_time'].values.astype(np.int64)[selected_indices]
                        oos_ep = df_oos_strat['entry_price'].values.astype(np.float64)[selected_indices]
                        oos_xp = df_oos_strat['exit_price'].values.astype(np.float64)[selected_indices]
                        oos_atr = df_oos_strat['atr'].values.astype(np.float64)[selected_indices]
                        oos_dr = df_oos_strat['direction'].values.astype(np.int8)[selected_indices]
                        sub_pr = probs_oos[selected_indices]
                        
                        for b_risk in [112.0, 125.0, 135.0]:
                            roi, dd, wr, tr = fast_portfolio_backtest_gentle(
                                oos_et, oos_xt, oos_ep, oos_xp, oos_atr, oos_dr, sub_pr,
                                base_risk=b_risk, max_house_risk=395.0, min_defense_risk=18.0, dd_limit=0.0475
                            )
                            
                            is_pass = (tr >= 5 and dd <= 0.05 and wr >= 0.40 and roi >= 0.20)
                            res_dict = {
                                'strategy': s_name, 'label_thresh': label_r_thresh,
                                'p_th': p_th, 'max_t': max_t, 'base_risk': b_risk,
                                'trades': tr, 'wr': wr, 'roi': roi, 'max_dd': dd
                            }
                            
                            if is_pass:
                                passing_configs.append(res_dict)
                                
                            if best_overall is None:
                                best_overall = res_dict
                            elif is_pass and (best_overall['roi'] < 0.20 or roi > best_overall['roi']):
                                best_overall = res_dict
                            elif best_overall['roi'] < 0.20 and dd <= 0.05:
                                if best_overall['max_dd'] > 0.05 or roi > best_overall['roi']:
                                    best_overall = res_dict
                                    
        if passing_configs:
            print(f"🎉 FOUND {len(passing_configs)} PASSING CONFIGURATIONS FOR {w_id}!")
            df_pass = pd.DataFrame(passing_configs).sort_values(by='roi', ascending=False)
            print(df_pass.head(10).to_string(index=False))
        else:
            print(f"Best Configuration for {w_id} (not yet 20%):")
            print(best_overall)

if __name__ == "__main__":
    solve_windows([6, 17])
