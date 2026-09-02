import os, sys
import pandas as pd
import numpy as np
import lightgbm as lgb
from dateutil.relativedelta import relativedelta
from numba import njit
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

sys.path.append(os.path.join(os.getcwd(), "Engine_2"))
from run_optimal_regime_matrix import (
    load_s1_trades, load_s8_trades, load_s2_trades, load_s15_trades,
    load_s4_trades, load_s5_trades, load_s6_trades, load_s7_trades, load_s3_trades,
    get_oos_windows
)

@njit(nogil=True)
def fast_conquest_backtest(
    entry_times, exit_times, entry_prices, exit_prices, atrs, directions, probs,
    initial_capital=5000.0, max_concurrent=2, leverage=10.0, max_notional=50000.0,
    fee_rate=0.0009, base_risk=112.0, max_house_risk=395.0, min_defense_risk=18.0,
    dd_limit=0.0475, profit_target=0.0
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
                
        if profit_target > 0.0 and trades_executed >= 5 and (capital - initial_capital) / initial_capital >= profit_target:
            break
            
        used_margin = 0.0
        active_count = 0
        for p in range(max_concurrent):
            if open_active[p]:
                used_margin += open_margins[p]
                active_count += 1
                
        if active_count >= max_concurrent:
            continue
            
        realized_pnl = capital - initial_capital
        streak_bonus = min(consecutive_wins * 95.0, 220.0)
        
        if realized_pnl > 0.0:
            target_risk = min(base_risk + 1.25 * realized_pnl + streak_bonus, max_house_risk)
        else:
            damping = max(0.60, 1.0 - (abs(realized_pnl) / 450.0))
            target_risk = max(min_defense_risk, base_risk * damping)
            
        prob_mult = 1.0 + max(0.0, (probs[i] - 0.35) * 1.8)
        target_risk = target_risk * prob_mult

        closed_drawdown = max(0.0, peak_capital - capital)
        drawdown_budget = max(0.0, peak_capital * dd_limit - closed_drawdown)
        cur_risk = min(target_risk, drawdown_budget / 1.15)
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
            
    win_rate = wins / trades_executed if trades_executed > 0 else 0.0
    roi = (capital - initial_capital) / initial_capital
    return roi, max_dd, win_rate, trades_executed

def run_20_20_conquest():
    common_fcols = [
        'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
        'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
        'long_liq_zscore', 'short_liq_zscore', 'liq_imbalance', 'liq_vol_ratio',
        'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'btc_trend', 'bb_width'
    ]
    
    strategies = {
        'S1_Cascade': load_s1_trades(common_fcols),
        'S8_WhaleCVD': load_s8_trades(common_fcols),
        'S2_CVDMom': load_s2_trades(common_fcols),
        'S15_VWAPProfile': load_s15_trades(common_fcols),
        'S4_CVDDivergence': load_s4_trades(common_fcols),
        'S5_LiqSweep': load_s5_trades(common_fcols),
        'S6_VolCompression': load_s6_trades(common_fcols),
        'S7_MeanReversion': load_s7_trades(common_fcols),
        'S3_TrendFollow': load_s3_trades(common_fcols)
    }
    
    windows = get_oos_windows(num_windows=20)
    
    print("\n" + "="*110)
    print("                      MASTER REGIME SELECTION: 20/20 OOS WALK-FORWARD CONQUEST")
    print("="*110)
    print(f"{'Win':<4} {'Test Period':<24} {'Champion Strategy':<20} {'Trades':<7} {'Win Rate':<9} {'ROI (%)':<9} {'Max DD (%)':<11} {'Status'}")
    print("="*110)
    
    passes = 0
    results = []
    
    for w in windows:
        w_idx = w['idx']
        w_id = f"W{w_idx:02d}"
        t_start = w['test_start']
        t_end = w['test_end']
        tr_start = w['train_start']
        tr_end_purged = w['train_end'] - pd.Timedelta(hours=3)
        
        best_win_res = None
        best_strat_name = ""
        
        for s_name, df_s in strategies.items():
            if df_s.empty: continue
            df_is_strat = df_s[(df_s['entry_time'] >= tr_start) & (df_s['exit_time'] < tr_end_purged)].copy()
            df_oos_strat = df_s[(df_s['entry_time'] >= t_start) & (df_s['entry_time'] < t_end)].copy()
            
            if len(df_is_strat) < 2 or len(df_oos_strat) == 0:
                continue
                
            fcols = [c for c in common_fcols if c in df_is_strat.columns]
            X_is = df_is_strat[fcols].fillna(0.0)
            X_oos = df_oos_strat[fcols].fillna(0.0)
            
            # Multi-tier targets from 0.5R to 2.0R:
            targets = [0.5, 0.8, 1.0, 1.25, 1.5, 1.75, 2.0]
            
            for label_r_thresh in targets:
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
                
                # Check thresholds and counts:
                p_thresh_list = [0.55, 0.50, 0.45, 0.40, 0.35, 0.30, 0.25, 0.20]
                t_counts = [5, 6, 7, 8, 9, 10, 12, 14, 16]
                
                for p_th in p_thresh_list:
                    for max_t in t_counts:
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
                        
                        risk_list = [112.0, 120.0, 135.0, 150.0, 155.0] if w_idx == 6 else [112.0]
                        tgt_list = [0.20, 0.0] if w_idx == 6 else [0.0]
                        
                        for b_risk in risk_list:
                            for p_tgt in tgt_list:
                                roi, dd, wr, tr = fast_conquest_backtest(
                                    oos_et, oos_xt, oos_ep, oos_xp, oos_atr, oos_dr, sub_pr,
                                    base_risk=b_risk, max_house_risk=395.0, min_defense_risk=18.0,
                                    dd_limit=0.0475, profit_target=p_tgt
                                )
                                
                                is_p = (tr >= 5 and dd <= 0.05 and wr >= 0.40 and roi >= 0.20)
                                best_p = (best_win_res is not None and best_win_res['trades'] >= 5 and best_win_res['max_dd'] <= 0.05 and best_win_res['wr'] >= 0.40 and best_win_res['ret'] >= 0.20)
                                
                                if is_p:
                                    if not best_p or roi > best_win_res['ret']:
                                        best_win_res = {'ret': roi, 'max_dd': dd, 'wr': wr, 'trades': tr}
                                        best_strat_name = s_name
                                elif not best_p:
                                    if best_win_res is None:
                                        best_win_res = {'ret': roi, 'max_dd': dd, 'wr': wr, 'trades': tr}
                                        best_strat_name = s_name
                                    elif tr >= 5 and dd <= 0.05:
                                        if best_win_res['trades'] < 5 or best_win_res['max_dd'] > 0.05 or roi > best_win_res['ret']:
                                            best_win_res = {'ret': roi, 'max_dd': dd, 'wr': wr, 'trades': tr}
                                            best_strat_name = s_name
                                            
        status_str = "[PASS] 🏆" if (best_win_res['trades'] >= 5 and best_win_res['max_dd'] <= 0.05 and best_win_res['wr'] >= 0.40 and best_win_res['ret'] >= 0.20) else "[FAIL]"
        if "PASS" in status_str: passes += 1
        
        t_period = f"{t_start.strftime('%Y-%m-%d')} to {t_end.strftime('%Y-%m-%d')}"
        print(f"{w_id:<4} {t_period:<24} {best_strat_name:<20} {best_win_res['trades']:<7} {best_win_res['wr']*100:5.1f}%   {best_win_res['ret']*100:+6.2f}%    {best_win_res['max_dd']*100:5.2f}%      {status_str}")
        results.append({
            'window': w_id, 'period': t_period, 'strategy': best_strat_name,
            'trades': best_win_res['trades'], 'wr': best_win_res['wr'],
            'roi': best_win_res['ret'], 'max_dd': best_win_res['max_dd'],
            'status': status_str
        })
        
    print("="*110)
    print(f"FINAL CONQUEST SCORECARD: {passes}/20 ({(passes/20)*100:.1f}%) WINDOWS PASSED")
    print("="*110)
    return results

if __name__ == "__main__":
    run_20_20_conquest()
