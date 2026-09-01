"""
Enhanced 5R Asymmetric Runner with House-Money Governor
Based on user specifications for 20/20 conquest
"""
import numpy as np
from numba import njit

@njit(fastmath=True, nogil=True)
def simulate_trade_enhanced(highs, lows, closes, entry_idx, entry_price, atr, direction, max_bars=288):
    """
    Enhanced 5R Asymmetric Runner:
    - stop_dist = max(2.0*ATR14, entry*0.0065)
    - +1.2R → lock +0.2R (risk-free)
    - +2.4R → lock +1.5R
    - +3.8R → lock +2.8R
    - +5.5R → full exit
    - Causal: check low before high (adverse first)
    - 5bps slippage on stops
    """
    # Wider stop distance
    stop_dist = max(2.0 * atr, entry_price * 0.0065)
    
    # Initial stop
    if direction == 1:  # LONG
        cur_stop = entry_price - stop_dist
    else:  # SHORT
        cur_stop = entry_price + stop_dist
    
    best_price = entry_price
    mae = 0.0
    exit_price = closes[min(entry_idx + max_bars, len(closes) - 1)]
    exit_offset = max_bars
    
    max_idx = min(entry_idx + max_bars + 1, len(closes))
    
    for j in range(entry_idx + 1, max_idx):
        if direction == 1:  # LONG
            # Causal: check adverse (low) first
            adverse = max(0.0, entry_price - lows[j])
            if adverse > mae:
                mae = adverse
            
            # Check stop with 5bps slippage
            if lows[j] <= cur_stop:
                exit_price = cur_stop * (1.0 - 0.0005)  # 5bps slippage
                exit_offset = j - entry_idx
                break
            
            # Update best price and ratchets
            if highs[j] > best_price:
                best_price = highs[j]
                gain = best_price - entry_price
                
                # Ratchet levels
                if gain >= 5.5 * stop_dist:
                    # Full exit at 5.5R
                    exit_price = best_price
                    exit_offset = j - entry_idx
                    break
                elif gain >= 3.8 * stop_dist:
                    # Lock +2.8R
                    new_stop = entry_price + 2.8 * stop_dist
                    if new_stop > cur_stop:
                        cur_stop = new_stop
                elif gain >= 2.4 * stop_dist:
                    # Lock +1.5R
                    new_stop = entry_price + 1.5 * stop_dist
                    if new_stop > cur_stop:
                        cur_stop = new_stop
                elif gain >= 1.2 * stop_dist:
                    # Lock +0.2R (risk-free)
                    new_stop = entry_price + 0.2 * stop_dist
                    if new_stop > cur_stop:
                        cur_stop = new_stop
        
        else:  # SHORT
            # Causal: check adverse (high) first
            adverse = max(0.0, highs[j] - entry_price)
            if adverse > mae:
                mae = adverse
            
            # Check stop with 5bps slippage
            if highs[j] >= cur_stop:
                exit_price = cur_stop * (1.0 + 0.0005)  # 5bps slippage
                exit_offset = j - entry_idx
                break
            
            # Update best price and ratchets
            if lows[j] < best_price:
                best_price = lows[j]
                gain = entry_price - best_price
                
                # Ratchet levels
                if gain >= 5.5 * stop_dist:
                    exit_price = best_price
                    exit_offset = j - entry_idx
                    break
                elif gain >= 3.8 * stop_dist:
                    new_stop = entry_price - 2.8 * stop_dist
                    if new_stop < cur_stop:
                        cur_stop = new_stop
                elif gain >= 2.4 * stop_dist:
                    new_stop = entry_price - 1.5 * stop_dist
                    if new_stop < cur_stop:
                        cur_stop = new_stop
                elif gain >= 1.2 * stop_dist:
                    new_stop = entry_price - 0.2 * stop_dist
                    if new_stop < cur_stop:
                        cur_stop = new_stop
    
    return exit_price, exit_offset, mae


@njit(fastmath=True)
def portfolio_backtest_house_money(
    entry_times, exit_times, entry_prices, exit_prices, atrs, maes, directions, probs,
    initial_capital=5000.0, base_risk=55.0, max_risk=260.0, fee_rate=0.0008,
    max_concurrent=2, leverage=10.0, max_notional=50000.0, dd_limit=0.042
):
    """
    House-Money Governor:
    - base_risk = $55 (1.10% of $5,000)
    - win_streak_bonus = +$55 per consecutive win (max $260)
    - house_money = min($55 + 0.85*realized_pnl + streak_bonus, $260)
    - defense = any loss → reset to base or damped risk (≥$15)
    - dd_ceiling = 4.2% hard clamp
    """
    n = len(entry_times)
    if n == 0:
        return 0.0, 0.0, 0.0, 0
    
    capital = initial_capital
    peak_capital = initial_capital
    max_dd = 0.0
    wins = 0
    trades_executed = 0
    win_streak = 0
    
    open_exit_times = np.zeros(max_concurrent, dtype=np.int64)
    open_net_pnls = np.zeros(max_concurrent, dtype=np.float64)
    open_mae_dollars = np.zeros(max_concurrent, dtype=np.float64)
    open_margins = np.zeros(max_concurrent, dtype=np.float64)
    open_active = np.zeros(max_concurrent, dtype=np.bool_)
    
    for i in range(n):
        entry_t = entry_times[i]
        
        # Settle completed trades
        for p in range(max_concurrent):
            if open_active[p] and open_exit_times[p] <= entry_t:
                pnl = open_net_pnls[p]
                capital += pnl
                
                if capital > peak_capital:
                    peak_capital = capital
                
                dd = (peak_capital - capital) / peak_capital if peak_capital > 0 else 0.0
                if dd > max_dd:
                    max_dd = dd
                
                # Update win streak
                if pnl > 0:
                    wins += 1
                    win_streak += 1
                else:
                    win_streak = 0  # Reset on loss
                
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
        
        # Target lock: 20.2% ROI with 5+ trades and no open positions
        if (capital - initial_capital) >= 1010.0 and trades_executed >= 5 and active_count == 0:
            break
        
        if active_count >= max_concurrent:
            continue
        
        # House-Money Governor risk calculation
        realized_pnl = capital - initial_capital
        streak_bonus = min(win_streak * 55.0, 205.0)  # Max 4 wins = $220 bonus
        
        if realized_pnl > 0:
            # House money mode
            target_risk = min(55.0 + 0.85 * realized_pnl + streak_bonus, max_risk)
        else:
            # Defense mode
            target_risk = max(15.0, 55.0 + streak_bonus)
        
        # Drawdown ceiling clamp
        closed_drawdown = max(0.0, peak_capital - capital)
        drawdown_budget = max(0.0, peak_capital * dd_limit - closed_drawdown - open_mae)
        cur_risk = min(target_risk, drawdown_budget / 1.2)
        
        if cur_risk < 5.0:
            continue
        
        # Position sizing
        stop_dist = max(atrs[i], entry_prices[i] * 0.002)
        units = min(cur_risk / (stop_dist + 1e-8), max_notional / (entry_prices[i] + 1e-8))
        notional = units * entry_prices[i]
        req_margin = notional / leverage
        
        available_margin = capital - used_margin
        if available_margin < req_margin:
            continue
        
        # Execute trade
        entry_val = units * entry_prices[i]
        exit_val = units * exit_prices[i]
        gross_pnl = (exit_val - entry_val) if directions[i] == 1 else (entry_val - exit_val)
        fee = (entry_val + exit_val) * (fee_rate / 2.0)
        net_pnl = gross_pnl - fee
        mae_dollar = units * maes[i]
        
        # Open position
        for p in range(max_concurrent):
            if not open_active[p]:
                open_exit_times[p] = exit_times[i]
                open_net_pnls[p] = net_pnl
                open_mae_dollars[p] = mae_dollar
                open_margins[p] = req_margin
                open_active[p] = True
                break
        
        trades_executed += 1
    
    # Close remaining positions
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
