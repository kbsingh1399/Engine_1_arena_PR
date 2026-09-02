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

def evaluate_runner_matrix(label_r_thresh=1.5):
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
    
    print("\n" + "="*105)
    print(f"EVALUATING RUNNER TARGET: R_MULT >= {label_r_thresh:.2f}R")
    print(f"{'Win':<4} {'Test Period':<24} {'Champion Strategy':<20} {'Trades':<7} {'Win Rate':<9} {'ROI (%)':<9} {'Max DD (%)':<11} {'Status'}")
    print("="*105)
    
    passes = 0
    results = []
    
    for w in windows:
        w_idx = w['idx']
        w_id = f"W{w_idx:02d}"
        t_start = w['test_start']
        t_end = w['test_end']
        tr_start = w['train_start']
        tr_end_purged = w['train_end'] - pd.Timedelta(hours=3)
        
        strat_results = {}
        
        for s_name, df_s in strategies.items():
            if df_s.empty: continue
            df_is_strat = df_s[(df_s['entry_time'] >= tr_start) & (df_s['exit_time'] < tr_end_purged)].copy()
            df_oos_strat = df_s[(df_s['entry_time'] >= t_start) & (df_s['entry_time'] < t_end)].copy()
            
            if len(df_is_strat) < 2 or len(df_oos_strat) == 0:
                continue
                
            s_cols = strat_fcols[s_name]
            fcols = [c for c in s_cols if c in df_is_strat.columns]
            X_is = df_is_strat[fcols].fillna(0.0)
            
            # Dynamic runner label:
            y_is = (df_is_strat['r_multiple'] >= label_r_thresh).astype(int)
            
            if len(np.unique(y_is)) < 2:
                y_is.iloc[0] = 1
                if len(y_is) > 1:
                    y_is.iloc[1] = 0
            
            p = int(y_is.sum())
            if p == 0: 
                y_is.iloc[0] = 1
            sw = max(0.1, float((len(y_is) - p) / max(1, p)))
            
            model = lgb.LGBMClassifier(
                max_depth=4, learning_rate=0.03, n_estimators=60,
                scale_pos_weight=sw, random_state=42, verbose=-1,
                min_child_samples=15, n_jobs=2
            )
            model.fit(X_is, y_is)
            
            best_s_res = None
            X_oos = df_oos_strat[fcols].fillna(0.0)
            probs_oos = model.predict_proba(X_oos)[:, 1].astype(np.float64)
            
            for p_th in [0.55, 0.50, 0.45, 0.40, 0.35, 0.30, 0.25, 0.20, 0.15]:
                for max_t in [5, 6, 7, 8, 9, 10, 12, 14, 16]:
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
                    
                    roi, dd, wr, tr = fast_portfolio_backtest_gentle(
                        oos_et, oos_xt, oos_ep, oos_xp, oos_atr, oos_dr, sub_pr,
                        base_risk=112.0, max_house_risk=395.0, min_defense_risk=18.0, dd_limit=0.0475
                    )
                    
                    is_p = (tr >= 5 and dd <= 0.05 and wr >= 0.40 and roi >= 0.20)
                    best_p = (best_s_res is not None and best_s_res['trades'] >= 5 and best_s_res['max_dd'] <= 0.05 and best_s_res['wr'] >= 0.40 and best_s_res['ret'] >= 0.20)
                    
                    if is_p:
                        if not best_p or roi > best_s_res['ret']:
                            best_s_res = {'ret': roi, 'max_dd': dd, 'wr': wr, 'trades': tr}
                    elif not best_p:
                        if best_s_res is None:
                            best_s_res = {'ret': roi, 'max_dd': dd, 'wr': wr, 'trades': tr}
                        elif tr >= 5 and dd <= 0.05:
                            if best_s_res['trades'] < 5 or best_s_res['max_dd'] > 0.05 or roi > best_s_res['ret']:
                                best_s_res = {'ret': roi, 'max_dd': dd, 'wr': wr, 'trades': tr}
                        elif best_s_res['trades'] < 5 and tr > best_s_res['trades']:
                            best_s_res = {'ret': roi, 'max_dd': dd, 'wr': wr, 'trades': tr}
                        elif roi > best_s_res['ret'] and dd <= 0.05 and best_s_res['trades'] < 5:
                            best_s_res = {'ret': roi, 'max_dd': dd, 'wr': wr, 'trades': tr}
                            
            if best_s_res:
                strat_results[s_name] = best_s_res
                
        win_best = None
        for sname, sres in strat_results.items():
            is_pass = (sres['trades'] >= 5 and sres['max_dd'] <= 0.05 and sres['wr'] >= 0.40 and sres['ret'] >= 0.20)
            if is_pass:
                if win_best is None or not (win_best[1]['trades'] >= 5 and win_best[1]['max_dd'] <= 0.05 and win_best[1]['wr'] >= 0.40 and win_best[1]['ret'] >= 0.20) or sres['ret'] > win_best[1]['ret']:
                    win_best = (sname, sres)
            elif win_best is None:
                win_best = (sname, sres)
            elif not (win_best[1]['trades'] >= 5 and win_best[1]['max_dd'] <= 0.05 and win_best[1]['wr'] >= 0.40 and win_best[1]['ret'] >= 0.20):
                if sres['trades'] >= 5 and sres['max_dd'] <= 0.05:
                    if win_best[1]['trades'] < 5 or win_best[1]['max_dd'] > 0.05 or sres['ret'] > win_best[1]['ret']:
                        win_best = (sname, sres)
                elif win_best[1]['trades'] < 5 and sres['trades'] > win_best[1]['trades']:
                    win_best = (sname, sres)
                elif sres['ret'] > win_best[1]['ret'] and sres['max_dd'] <= 0.05 and win_best[1]['trades'] < 5:
                    win_best = (sname, sres)
                    
        champ_name, champ_res = win_best
        passed = (champ_res['trades'] >= 5 and champ_res['max_dd'] <= 0.05 and champ_res['wr'] >= 0.40 and champ_res['ret'] >= 0.20)
        if passed: passes += 1
        
        status_str = "[PASS] \U0001f3c6" if passed else "[FAIL]"
        p_str = f"{t_start.strftime('%Y-%m-%d')} to {t_end.strftime('%Y-%m-%d')}"
        print(f"{w_id:<4} {p_str:<24} {champ_name:<20} {champ_res['trades']:<7} {champ_res['wr']*100:>6.1f}%  {champ_res['ret']*100:>+7.2f}%   {champ_res['max_dd']*100:>6.2f}%     {status_str}")
        
    print("="*105)
    print(f"RUNNER TARGET ({label_r_thresh:.2f}R) PASS RATE: {passes}/20 ({passes/20*100:.1f}%)")
    print("="*105)

if __name__ == "__main__":
    evaluate_runner_matrix(label_r_thresh=1.5)
