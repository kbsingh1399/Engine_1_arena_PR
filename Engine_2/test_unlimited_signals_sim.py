import os, sys
import pandas as pd
import numpy as np
from numba import njit

sys.path.append(os.path.join(os.getcwd(), "Engine_2"))
from run_optimal_regime_matrix import load_s8_trades, get_oos_windows

@njit(nogil=True)
def backtest_unlimited_signals(
    entry_times, exit_times, entry_prices, exit_prices, atrs, directions, probs,
    initial_capital=5000.0, leverage=10.0, max_notional=50000.0,
    fee_rate=0.0009, base_risk=112.0, max_concurrent=20
):
    n = len(entry_times)
    if n == 0: return 0.0, 0.0, 0.0, 0
        
    capital = initial_capital
    peak_capital = initial_capital
    max_dd = 0.0
    wins = 0
    trades_executed = 0
    
    open_exit_times = np.zeros(max_concurrent, dtype=np.int64)
    open_net_pnls = np.zeros(max_concurrent, dtype=np.float64)
    open_margins = np.zeros(max_concurrent, dtype=np.float64)
    open_active = np.zeros(max_concurrent, dtype=np.bool_)
    
    for i in range(n):
        t_entry = entry_times[i]
        
        # Settle closed trades
        for p in range(max_concurrent):
            if open_active[p] and open_exit_times[p] <= t_entry:
                capital += open_net_pnls[p]
                trades_executed += 1
                if open_net_pnls[p] > 0: wins += 1
                if capital > peak_capital: peak_capital = capital
                dd = (peak_capital - capital) / peak_capital
                if dd > max_dd: max_dd = dd
                open_active[p] = False
                open_margins[p] = 0.0
                
        # Check available margin
        used_margin = 0.0
        for p in range(max_concurrent):
            if open_active[p]: used_margin += open_margins[p]
            
        stop_dist = max(2.0 * atrs[i], entry_prices[i] * 0.0065)
        units = min(base_risk / (stop_dist + 1e-8), max_notional / (entry_prices[i] + 1e-8))
        notional = units * entry_prices[i]
        req_margin = notional / leverage
        
        available_margin = capital - used_margin
        # ONLY skip if money (margin) is exhausted:
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
            if open_net_pnls[p] > 0: wins += 1
            if capital > peak_capital: peak_capital = capital
            dd = (peak_capital - capital) / peak_capital
            if dd > max_dd: max_dd = dd
            open_active[p] = False
            
    win_rate = wins / trades_executed if trades_executed > 0 else 0.0
    roi = (capital - initial_capital) / initial_capital
    return roi, max_dd, win_rate, trades_executed

def run_comparison():
    windows = get_oos_windows(num_windows=20)
    w = windows[1] # W02
    t_start = w['test_start']
    t_end = w['test_end']
    
    fcols = ['direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel']
    df_s = load_s8_trades(fcols)
    df_oos = df_s[(df_s['entry_time'] >= t_start) & (df_s['entry_time'] < t_end)].sort_values('entry_time').reset_index(drop=True)
    
    et = df_oos['entry_time'].values.astype(np.int64)
    xt = df_oos['exit_time'].values.astype(np.int64)
    ep = df_oos['entry_price'].values.astype(np.float64)
    xp = df_oos['exit_price'].values.astype(np.float64)
    atr = df_oos['atr'].values.astype(np.float64)
    dr = df_oos['direction'].values.astype(np.int8)
    probs = np.ones(len(df_oos), dtype=np.float64)
    
    print("\n=== Comparing Execution Policies on W02 (S8) ===")
    for mc in [2, 4, 8, 15]:
        roi, dd, wr, tr = backtest_unlimited_signals(
            et, xt, ep, xp, atr, dr, probs,
            initial_capital=5000.0, leverage=10.0, max_notional=50000.0,
            fee_rate=0.0009, base_risk=112.0, max_concurrent=mc
        )
        print(f"Max Concurrent = {mc:<2} | Trades Taken = {tr:<2} | WR = {wr*100:5.1f}% | ROI = {roi*100:+6.2f}% | Max DD = {dd*100:5.2f}%")

if __name__ == "__main__":
    run_comparison()
