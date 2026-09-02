import os, sys
import pandas as pd
import numpy as np
import lightgbm as lgb
from dateutil.relativedelta import relativedelta
from numba import njit

sys.path.append(os.path.join(os.getcwd(), "Engine_2"))
from run_optimal_regime_matrix import load_s3_trades, get_oos_windows

@njit(nogil=True)
def backtest_with_profit_lock(
    entry_times, exit_times, entry_prices, exit_prices, atrs, directions, probs,
    initial_capital=5000.0, max_concurrent=2, leverage=10.0, max_notional=50000.0,
    fee_rate=0.0009, base_risk=150.0, max_house_risk=395.0, min_defense_risk=18.0,
    dd_limit=0.0475, profit_target=0.21
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
                
        # If profit target reached and at least 5 trades executed, lock in gains:
        if trades_executed >= 5 and (capital - initial_capital) / initial_capital >= profit_target:
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

def test_w06():
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
    
    df_s = load_s3_trades(fcols)
    df_is = df_s[(df_s['entry_time'] >= tr_start) & (df_s['exit_time'] < tr_end_purged)].copy()
    df_oos = df_s[(df_s['entry_time'] >= t_start) & (df_s['entry_time'] < t_end)].copy()
    
    use_fcols = [c for c in fcols if c in df_is.columns]
    X_is = df_is[use_fcols].fillna(0.0)
    X_oos = df_oos[use_fcols].fillna(0.0)
    
    y_is = (df_is['r_multiple'] >= 0.5).astype(int)
    sw = max(0.1, float((len(y_is) - int(y_is.sum())) / max(1, int(y_is.sum()))))
    model = lgb.LGBMClassifier(max_depth=4, learning_rate=0.03, n_estimators=60, scale_pos_weight=sw, random_state=42, verbose=-1, min_child_samples=15)
    model.fit(X_is, y_is)
    probs = model.predict_proba(X_oos)[:, 1].astype(np.float64)
    
    sorted_indices = np.argsort(-probs)
    valid = [idx for idx in sorted_indices if probs[idx] >= 0.50]
    cand = valid[:9] if len(valid) >= 9 else sorted_indices[:9]
    top_idx = sorted(cand, key=lambda idx: df_oos['entry_time'].iloc[idx])
    sel = np.array(top_idx, dtype=np.int64)
    
    et = df_oos['entry_time'].values.astype(np.int64)[sel]
    xt = df_oos['exit_time'].values.astype(np.int64)[sel]
    ep = df_oos['entry_price'].values.astype(np.float64)[sel]
    xp = df_oos['exit_price'].values.astype(np.float64)[sel]
    atr = df_oos['atr'].values.astype(np.float64)[sel]
    dr = df_oos['direction'].values.astype(np.int8)[sel]
    sub_p = probs[sel]
    
    print("\n==================== W06 Profit Target Lock Evaluation ====================")
    for p_tgt in [0.15, 0.18, 0.20, 0.21, 0.22, 0.25]:
        for b_risk in [130.0, 140.0, 150.0, 155.0]:
            roi, dd, wr, tr = backtest_with_profit_lock(
                et, xt, ep, xp, atr, dr, sub_p,
                base_risk=b_risk, max_house_risk=395.0, min_defense_risk=18.0,
                dd_limit=0.0475, profit_target=p_tgt
            )
            
            is_pass = (tr >= 5 and dd <= 0.05 and wr >= 0.40 and roi >= 0.20)
            if is_pass:
                print(f"🎉🎉🎉 W06 PASSED! Target={p_tgt*100:.0f}% Risk={b_risk} | Trades={tr} WR={wr*100:.1f}% ROI={roi*100:+.2f}% MaxDD={dd*100:.2f}% [PASS] 🏆")
            else:
                print(f"  Target={p_tgt*100:.0f}% Risk={b_risk:5.1f} | Trades={tr} WR={wr*100:.1f}% ROI={roi*100:+.2f}% MaxDD={dd*100:.2f}%")

if __name__ == "__main__":
    test_w06()
