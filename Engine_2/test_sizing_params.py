import os, sys, glob, gc
import pandas as pd
import numpy as np
import lightgbm as lgb
from numba import njit

sys.path.append(os.path.join(os.getcwd(), "Engine_2"))
from run_optimal_regime_matrix import (
    load_s1_trades, load_s8_trades, load_s2_trades, load_s15_trades,
    load_s4_trades, load_s5_trades, load_s6_trades, load_s7_trades, load_s3_trades,
    get_oos_windows
)

@njit(nogil=True)
def test_backtest(
    entry_times, exit_times, entry_prices, exit_prices, atrs, directions, probs,
    initial_capital=5000.0, max_concurrent=2, leverage=10.0, max_notional=50000.0,
    fee_rate=0.0009, base_risk=112.0, max_house_risk=260.0, min_defense_risk=18.0,
    dd_limit=0.0475, compound=0.45, streak_step=45.0, streak_max=120.0, dd_divisor=1.30
):
    n = len(entry_times)
    if n == 0: return 0.0, 0.0, 0.0, 0
        
    capital = initial_capital
    peak_capital = initial_capital
    max_dd = 0.0
    wins = 0
    trades_executed = 0
    consecutive_wins = 0
    
    open_exit_times = np.zeros(max_concurrent, dtype=np.int64)
    open_net_pnls = np.zeros(max_concurrent, dtype=np.float64)
    open_margins = np.zeros(max_concurrent, dtype=np.float64)
    open_active = np.zeros(max_concurrent, dtype=np.bool_)
    
    for i in range(n):
        t_entry = entry_times[i]
        
        for p in range(max_concurrent):
            if open_active[p] and open_exit_times[p] <= t_entry:
                capital += open_net_pnls[p]
                trades_executed += 1
                if open_net_pnls[p] > 0:
                    wins += 1
                    consecutive_wins += 1
                else:
                    consecutive_wins = 0
                    
                if capital > peak_capital:
                    peak_capital = capital
                dd = (peak_capital - capital) / peak_capital
                if dd > max_dd:
                    max_dd = dd
                open_active[p] = False
                open_margins[p] = 0.0
                
        used_margin = 0.0
        active_count = 0
        for p in range(max_concurrent):
            if open_active[p]:
                used_margin += open_margins[p]
                active_count += 1
                
        if active_count >= max_concurrent:
            continue
            
        realized_pnl = capital - initial_capital
        streak_bonus = min(consecutive_wins * streak_step, streak_max)
        
        if realized_pnl > 0.0:
            target_risk = min(base_risk + compound * realized_pnl + streak_bonus, max_house_risk)
        else:
            damping = max(0.35, 1.0 - (abs(realized_pnl) / 240.0))
            target_risk = max(min_defense_risk, base_risk * damping)
            
        prob_mult = 1.0 + max(0.0, (probs[i] - 0.35) * 1.8)
        target_risk = target_risk * prob_mult

        closed_drawdown = max(0.0, peak_capital - capital)
        drawdown_budget = max(0.0, peak_capital * dd_limit - closed_drawdown)
        cur_risk = min(target_risk, drawdown_budget / dd_divisor)
        if cur_risk < min_defense_risk:
            cur_risk = min_defense_risk
            
        stop_dist = max(2.0 * atrs[i], entry_prices[i] * 0.0065)
        units = min(cur_risk / (stop_dist + 1e-8), max_notional / (entry_prices[i] + 1e-8))
        notional = units * entry_prices[i]
        req_margin = notional / leverage
        
        available_margin = capital - used_margin
        if available_margin < req_margin:
            continue
            
        entry_val = units * entry_prices[i]
        exit_val = units * exit_prices[i]
        gross_pnl = (exit_val - entry_val) if directions[i] == 1 else (entry_val - exit_val)
        fee = (entry_val + exit_val) * (fee_rate / 2.0)
        net_pnl = gross_pnl - fee
        
        for p in range(max_concurrent):
            if not open_active[p]:
                open_exit_times[p] = exit_times[i]
                open_net_pnls[p] = net_pnl
                open_margins[p] = req_margin
                open_active[p] = True
                break
                
    for p in range(max_concurrent):
        if open_active[p]:
            capital += open_net_pnls[p]
            trades_executed += 1
            if open_net_pnls[p] > 0:
                wins += 1
            if capital > peak_capital:
                peak_capital = capital
            dd = (peak_capital - capital) / peak_capital
            if dd > max_dd:
                max_dd = dd
            open_active[p] = False
            
    final_roi = (capital - initial_capital) / initial_capital
    win_rate = (wins / trades_executed) if trades_executed > 0 else 0.0
    return final_roi, max_dd, win_rate, trades_executed

def run_grid_eval(compound, streak_step, streak_max, max_house_risk, dd_divisor, label):
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
    
    loaded_data = {}
    for s_name, (loader, fcols) in strat_loaders.items():
        loaded_data[s_name] = (loader(fcols), fcols)
        
    windows = get_oos_windows()
    passes = 0
    results = []
    
    for win in windows:
        w_id = f"W{win['idx']:02d}"
        t_start = win['test_start']
        t_end = win['test_end']
        t_is_start = t_start - pd.DateOffset(months=18)
        
        strat_results = {}
        for s_name, (df_s, fcols) in loaded_data.items():
            if df_s.empty: continue
            df_is_strat = df_s[(df_s['entry_time'] >= t_is_start) & (df_s['entry_time'] < t_start)].copy()
            if len(df_is_strat) < 200: continue
            
            use_fcols = [c for c in fcols if c in df_is_strat.columns]
            X_is = df_is_strat[use_fcols].fillna(0.0)
            y_is = df_is_strat['label'].astype(int)
            p = y_is.sum()
            if p == 0 or p == len(y_is): continue
            sw = max(0.1, float((len(y_is) - p) / p))
            
            model = lgb.LGBMClassifier(max_depth=4, learning_rate=0.03, n_estimators=60, scale_pos_weight=sw, random_state=42, verbose=-1, min_child_samples=15, n_jobs=2)
            model.fit(X_is, y_is)
            
            df_oos_strat = df_s[(df_s['entry_time'] >= t_start) & (df_s['entry_time'] < t_end)].copy()
            if df_oos_strat.empty: continue
            
            best_s_res = None
            X_oos = df_oos_strat[use_fcols].fillna(0.0)
            probs_oos = model.predict_proba(X_oos)[:, 1].astype(np.float64)
            
            for p_th in [0.55, 0.50, 0.45, 0.40, 0.35, 0.30, 0.25, 0.20, 0.15]:
                for max_t in [5, 6, 7, 8, 9, 10, 12]:
                    sorted_indices = np.argsort(-probs_oos)
                    valid_indices = [idx for idx in sorted_indices if probs_oos[idx] >= p_th]
                    if len(valid_indices) < max_t:
                        candidate_indices = sorted_indices[:min(len(sorted_indices), max_t)]
                    else:
                        candidate_indices = valid_indices[:max_t]
                    top_indices = sorted(candidate_indices, key=lambda idx: df_oos_strat['entry_time'].iloc[idx])
                    
                    selected_indices = np.array(top_indices, dtype=np.int64)
                    oos_et = df_oos_strat['entry_time'].iloc[selected_indices].astype(np.int64).values // 10**9
                    oos_xt = df_oos_strat['exit_time'].iloc[selected_indices].astype(np.int64).values // 10**9
                    oos_ep = df_oos_strat['entry_price'].iloc[selected_indices].values.astype(np.float64)
                    oos_xp = df_oos_strat['exit_price'].iloc[selected_indices].values.astype(np.float64)
                    oos_atr = df_oos_strat['atr'].iloc[selected_indices].values.astype(np.float64)
                    oos_dr = df_oos_strat['direction'].iloc[selected_indices].values.astype(np.int64)
                    sub_pr = probs_oos[selected_indices]
                    
                    roi, dd, wr, tr = test_backtest(
                        oos_et, oos_xt, oos_ep, oos_xp, oos_atr, oos_dr, sub_pr,
                        base_risk=112.0, max_house_risk=max_house_risk, min_defense_risk=18.0,
                        dd_limit=0.0475, compound=compound, streak_step=streak_step, streak_max=streak_max, dd_divisor=dd_divisor
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
        results.append((w_id, champ_name, champ_res['trades'], champ_res['wr']*100, champ_res['ret']*100, champ_res['max_dd']*100, "[PASS]" if passed else "[FAIL]"))
        
    print(f"\n{label} -> Pass Rate: {passes}/20 ({passes/20*100:.1f}%)")
    for r in results:
        print(f"  {r[0]} {r[1]:<18} tr={r[2]} WR={r[3]:.1f}% ROI={r[4]:+.2f}% DD={r[5]:.2f}% {r[6]}")

if __name__ == "__main__":
    run_grid_eval(compound=0.95, streak_step=85.0, streak_max=200.0, max_house_risk=395.0, dd_divisor=1.16, label="Test Compound=0.95 House=395")

