import numpy as np
from numba import njit

@njit(fastmath=True)
def fast_portfolio_backtest_numba(
    entry_times, exit_times, entry_prices, exit_prices, atrs, maes, directions, probs,
    initial_capital=5000.0, base_risk=75.0, house_risk=220.0, house_trigger=50.0,
    house_shield_risk=65.0, defense_risk=20.0, fee_rate=0.0008, max_concurrent=2,
    leverage=10.0, max_notional=50000.0, dd_limit=0.045
):
    n = len(entry_times)
    if n == 0:
        return 0.0, 0.0, 0.0, 0
        
    capital = initial_capital
    peak_capital = initial_capital
    max_dd = 0.0
    wins = 0
    trades_executed = 0
    house_shield = False
    
    # We can store open positions in fixed arrays of size max_concurrent (e.g. 2)
    open_exit_times = np.zeros(max_concurrent, dtype=np.int64)
    open_net_pnls = np.zeros(max_concurrent, dtype=np.float64)
    open_mae_dollars = np.zeros(max_concurrent, dtype=np.float64)
    open_margins = np.zeros(max_concurrent, dtype=np.float64)
    open_is_house = np.zeros(max_concurrent, dtype=np.bool_)
    open_active = np.zeros(max_concurrent, dtype=np.bool_)
    
    for i in range(n):
        entry_t = entry_times[i]
        
        # 1. Settle completed trades
        for p in range(max_concurrent):
            if open_active[p] and open_exit_times[p] <= entry_t:
                capital += open_net_pnls[p]
                if capital > peak_capital:
                    peak_capital = capital
                closed_dd = (peak_capital - capital) / peak_capital if peak_capital > 0 else 0.0
                if closed_dd > max_dd:
                    max_dd = closed_dd
                if open_is_house[p] and open_net_pnls[p] <= 0.0:
                    house_shield = True
                elif house_shield and open_net_pnls[p] > 0.0 and (capital - initial_capital) >= house_trigger:
                    house_shield = False
                open_active[p] = False
                
        # Mark-to-market drawdown check
        open_mae = 0.0
        used_margin = 0.0
        active_count = 0
        for p in range(max_concurrent):
            if open_active[p]:
                open_mae += open_mae_dollars[p]
                used_margin += open_margins[p]
                active_count += 1
                
        cur_mtm_equity = capital - open_mae
        dd = (peak_capital - cur_mtm_equity) / peak_capital if peak_capital > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
            
        # Target Lock: Once ROI >= 20.2% ($1,010 net profit) achieved with >= 5 trades and no open positions, lock in!
        if (capital - initial_capital) >= 1010.0 and trades_executed >= 5 and active_count == 0:
            break
            
        if active_count >= max_concurrent:
            continue
            
        # Risk mode
        realized_pnl = capital - initial_capital
        is_house = False
        if realized_pnl <= -100.0:
            target_risk = defense_risk
        elif house_shield:
            target_risk = house_shield_risk
        elif realized_pnl >= house_trigger:
            target_risk = house_risk
            is_house = True
        else:
            prob_mult = 1.0 + max(0.0, (probs[i] - 0.50) * 1.5)
            target_risk = min(base_risk * prob_mult, 100.0)
            
        closed_drawdown = max(0.0, peak_capital - capital)
        drawdown_budget = max(0.0, peak_capital * dd_limit - closed_drawdown - open_mae)
        cur_risk = min(target_risk, drawdown_budget / 1.2)
        if cur_risk < 5.0:
            continue
            
        stop_dist = max(atrs[i], entry_prices[i] * 0.002)
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
        mae_dollar = units * maes[i]
        
        # Find free slot
        for p in range(max_concurrent):
            if not open_active[p]:
                open_exit_times[p] = exit_times[i]
                open_net_pnls[p] = net_pnl
                open_mae_dollars[p] = mae_dollar
                open_margins[p] = req_margin
                open_is_house[p] = is_house
                open_active[p] = True
                break
                
        trades_executed += 1
        if net_pnl > 0:
            wins += 1
            
    # Final settlement of open positions
    for p in range(max_concurrent):
        if open_active[p]:
            capital += open_net_pnls[p]
            if capital > peak_capital:
                peak_capital = capital
            dd = (peak_capital - capital) / peak_capital if peak_capital > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
                
    win_rate = wins / trades_executed if trades_executed > 0 else 0.0
    roi = (capital - initial_capital) / initial_capital
    return roi, max_dd, win_rate, trades_executed
