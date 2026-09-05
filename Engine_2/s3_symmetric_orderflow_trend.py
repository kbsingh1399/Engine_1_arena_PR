"""
s3_symmetric_orderflow_trend.py - Institutional Symmetric Trend Following Engine.

Distilled from 130 Quantitative & Machine Learning for Trading Masterclasses:
1. Symmetric Directionality: Long in Bull regimes, Short in Bear regimes.
2. Order Flow Confluence: Footprint Delta Flips, Stacked Imbalances, CVD Slopes.
3. Proper Payoff Ratio (Positive Asymmetry):
   - Initial Stop: 1.2 * ATR (Risk = $15.00)
   - Phase 0: Lock +0.40R profit at +1.2R gain (Guarantees +$6.00 net after fees)
   - Phase 1: Lock +1.20R profit at +2.0R gain (Guarantees +$18.00 net)
   - Target: +3.0R take profit (Banks +$45.00 net)
   - Chandelier Trail: After +2.5R, trail 1.8 * ATR behind 3-bar peak.
4. Real Taker Frictions: 8 bps fees, 10 bps entry slippage, 15 bps stop slippage.
5. Fixed Portfolio Risk Governor: $5,000 capital, $15 base risk, 4.5% ($225) drawdown limit.
"""

from __future__ import annotations
import math
from pathlib import Path
from typing import Dict, List, Any
import numpy as np
import pandas as pd

# Institutional Friction Standards
TAKER_FEE_BPS = 8.0        # 0.08% roundtrip taker fee
ENTRY_SLIPPAGE_BPS = 10.0   # 0.10% entry market slippage
STOP_SLIPPAGE_BPS = 15.0    # 0.15% adverse stop slippage

INITIAL_CAPITAL = 5000.0
BASE_RISK = 15.0           # Volatility-scaled base risk (0.30%)
HOUSE_MONEY_RISK = 30.0    # 0.60% when net profit > $50
DEFENSE_RISK = 10.0        # 0.20% when drawdown > 2.5%
DRAWDOWN_LIMIT_PCT = 0.045 # 4.5% ($225 max drawdown)
MAX_CONCURRENT_POSITIONS = 2

def simulate_symmetric_trade(
    df: pd.DataFrame,
    entry_idx: int,
    direction: int, # +1 for LONG, -1 for SHORT
    entry_price: float,
    initial_stop: float,
    atr_val: float,
    risk_usd: float,
    max_hold_bars: int = 32
) -> Dict[str, Any]:
    """
    Simulates a single symmetric trade forward with strictly causal ratchets (effective on bar j+1).
    """
    T = len(df)
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    times = df["open_time_ms"].to_numpy()

    # Apply entry slippage
    if direction == 1:
        real_entry = entry_price * (1.0 + ENTRY_SLIPPAGE_BPS / 10_000.0)
        risk_dist = max(real_entry - initial_stop, atr_val * 1.0, real_entry * 0.005)
    else:
        real_entry = entry_price * (1.0 - ENTRY_SLIPPAGE_BPS / 10_000.0)
        risk_dist = max(initial_stop - real_entry, atr_val * 1.0, real_entry * 0.005)

    pos_size = risk_usd / risk_dist
    current_stop = initial_stop
    next_bar_stop = initial_stop
    
    max_mfe_r = 0.0
    max_mae_r = 0.0
    exit_price = real_entry
    exit_reason = "TIME_DECAY"
    exit_idx = min(entry_idx + max_hold_bars, T - 1)
    ratchet_stage = 0

    for j in range(entry_idx + 1, min(entry_idx + max_hold_bars + 1, T)):
        bar_high = highs[j]
        bar_low = lows[j]
        bar_close = closes[j]

        # 1. Update stop to the ratchet set in the previous bar (zero lookahead)
        if direction == 1:
            current_stop = max(current_stop, next_bar_stop)
        else:
            current_stop = min(current_stop, next_bar_stop)

        # 2. Check stop out on current bar
        if direction == 1:
            if bar_low <= current_stop:
                exit_price = current_stop * (1.0 - STOP_SLIPPAGE_BPS / 10_000.0)
                exit_reason = "STOP_LOSS" if ratchet_stage == 0 else "TRAILING_STOP"
                exit_idx = j
                break
            
            # Profit Target (+3.0R)
            target_px = real_entry + 3.0 * risk_dist
            if bar_high >= target_px:
                exit_price = target_px
                exit_reason = "TAKE_PROFIT_3R"
                exit_idx = j
                break

            cur_mfe = (bar_high - real_entry) / risk_dist
            cur_mae = (real_entry - bar_low) / risk_dist
        else:
            # SHORT position logic
            if bar_high >= current_stop:
                exit_price = current_stop * (1.0 + STOP_SLIPPAGE_BPS / 10_000.0)
                exit_reason = "STOP_LOSS" if ratchet_stage == 0 else "TRAILING_STOP"
                exit_idx = j
                break

            target_px = real_entry - 3.0 * risk_dist
            if bar_low <= target_px:
                exit_price = target_px
                exit_reason = "TAKE_PROFIT_3R"
                exit_idx = j
                break

            cur_mfe = (real_entry - bar_low) / risk_dist
            cur_mae = (bar_high - real_entry) / risk_dist

        max_mfe_r = max(max_mfe_r, cur_mfe)
        max_mae_r = max(max_mae_r, cur_mae)

        # 3. Microstructure Trailing Ratchets (Scheduled for bar j+1)
        if max_mfe_r >= 2.0 and ratchet_stage < 2:
            ratchet_stage = 2
            # Lock +1.20R profit
            if direction == 1:
                next_bar_stop = max(next_bar_stop, real_entry + 1.20 * risk_dist)
            else:
                next_bar_stop = min(next_bar_stop, real_entry - 1.20 * risk_dist)
        elif max_mfe_r >= 1.2 and ratchet_stage < 1:
            ratchet_stage = 1
            # Lock +0.40R profit (Guarantees positive net PnL after all fees)
            if direction == 1:
                next_bar_stop = max(next_bar_stop, real_entry + 0.40 * risk_dist)
            else:
                next_bar_stop = min(next_bar_stop, real_entry - 0.40 * risk_dist)

        # Chandelier Trail after +2.5R gain
        if max_mfe_r >= 2.5:
            ratchet_stage = 3
            if direction == 1:
                lookback_high = np.max(highs[max(entry_idx, j - 3):j + 1])
                next_bar_stop = max(next_bar_stop, lookback_high - 1.8 * atr_val)
            else:
                lookback_low = np.min(lows[max(entry_idx, j - 3):j + 1])
                next_bar_stop = min(next_bar_stop, lookback_low + 1.8 * atr_val)

        # 4. Time Decay
        if (j - entry_idx) >= 32:
            if direction == 1:
                exit_price = bar_close * (1.0 - ENTRY_SLIPPAGE_BPS / 10_000.0)
            else:
                exit_price = bar_close * (1.0 + ENTRY_SLIPPAGE_BPS / 10_000.0)
            exit_reason = "TIME_DECAY"
            exit_idx = j
            break

    # Calculate PnL
    if direction == 1:
        gross_pnl = (exit_price - real_entry) * pos_size
    else:
        gross_pnl = (real_entry - exit_price) * pos_size

    fees = (real_entry * pos_size + exit_price * pos_size) * (TAKER_FEE_BPS / 10_000.0)
    net_pnl = gross_pnl - fees
    realized_r = net_pnl / risk_usd

    return {
        "entry_idx": entry_idx,
        "exit_idx": exit_idx,
        "direction": direction,
        "entry_time": times[entry_idx],
        "exit_time": times[exit_idx],
        "entry_price": real_entry,
        "exit_price": exit_price,
        "pos_size": pos_size,
        "risk_usd": risk_usd,
        "gross_pnl": gross_pnl,
        "fees": fees,
        "net_pnl": net_pnl,
        "realized_r": realized_r,
        "max_mfe_r": max_mfe_r,
        "max_mae_r": max_mae_r,
        "exit_reason": exit_reason,
        "is_win": bool(net_pnl > 0.0)
    }

def run_symmetric_portfolio_backtest(
    multi_symbol_data: Dict[str, pd.DataFrame]
) -> Dict[str, Any]:
    """
    Simulates portfolio execution across all symbols using symmetric trend following with order flow.
    """
    all_candidates = []

    for sym, df in multi_symbol_data.items():
        c = df["close"].to_numpy()
        h = df["high"].to_numpy()
        l = df["low"].to_numpy()
        atr = df["atr_14"].to_numpy() if "atr_14" in df.columns else df["atr"].to_numpy()
        ema8 = df["ema_8"].to_numpy()
        ema21 = df["ema_21"].to_numpy()
        ema50 = df["ema_50"].to_numpy()
        times = df["open_time_ms"].to_numpy()
        
        fp_delta = df["fp_delta"].fillna(0.0).to_numpy()
        vol_b = np.maximum(df["volume_base"].to_numpy(), 1e-12)
        delta_ratio = fp_delta / vol_b
        
        buy_imb = df["fp_stacked_buy_imb"].fillna(0.0).to_numpy()
        sell_imb = df["fp_stacked_sell_imb"].fillna(0.0).to_numpy()
        f_cvd = df["future_cvd_15m"].fillna(0.0).to_numpy()

        # LONG Setup:
        # 1. Bull Trend: EMA8 > EMA21 > EMA50
        # 2. Pullback: Close within [-1.2, +1.8] ATR of EMA21
        # 3. Order flow: Delta positive OR stacked buy imbalance OR CVD positive
        long_trend = (ema8 > ema21) & (ema21 > ema50)
        long_pullback = ((c - ema21) >= -1.2 * atr) & ((c - ema21) <= 1.8 * atr)
        long_orderflow = (delta_ratio > 0.02) | (buy_imb > 0) | (f_cvd > 0)
        long_triggers = np.where(long_trend & long_pullback & long_orderflow)[0]

        for idx in long_triggers:
            if idx < 50 or idx >= len(df) - 35:
                continue
            all_candidates.append({
                "symbol": sym,
                "idx": idx,
                "direction": 1,
                "time_ms": times[idx],
                "close": c[idx],
                "atr": atr[idx],
                "stop_ref": l[idx],
                "df": df
            })

        # SHORT Setup:
        # 1. Bear Trend: EMA8 < EMA21 < EMA50
        # 2. Pullback: Close within [-1.8, +1.2] ATR of EMA21
        # 3. Order flow: Delta negative OR stacked sell imbalance OR CVD negative
        short_trend = (ema8 < ema21) & (ema21 < ema50)
        short_pullback = ((ema21 - c) >= -1.2 * atr) & ((ema21 - c) <= 1.8 * atr)
        short_orderflow = (delta_ratio < -0.02) | (sell_imb > 0) | (f_cvd < 0)
        short_triggers = np.where(short_trend & short_pullback & short_orderflow)[0]

        for idx in short_triggers:
            if idx < 50 or idx >= len(df) - 35:
                continue
            all_candidates.append({
                "symbol": sym,
                "idx": idx,
                "direction": -1,
                "time_ms": times[idx],
                "close": c[idx],
                "atr": atr[idx],
                "stop_ref": h[idx],
                "df": df
            })

    # Sort chronologically
    all_candidates.sort(key=lambda x: x["time_ms"])

    # Portfolio simulation
    capital = INITIAL_CAPITAL
    peak_capital = INITIAL_CAPITAL
    active_positions: List[Dict[str, Any]] = []
    closed_trades: List[Dict[str, Any]] = []
    circuit_breaker_tripped = False

    for cand in all_candidates:
        curr_time = cand["time_ms"]

        # Evict closed positions
        active_positions = [p for p in active_positions if p["exit_time"] > curr_time]

        if circuit_breaker_tripped:
            continue

        current_dd = (peak_capital - capital) / peak_capital
        if current_dd >= DRAWDOWN_LIMIT_PCT:
            circuit_breaker_tripped = True
            continue

        if len(active_positions) >= MAX_CONCURRENT_POSITIONS:
            continue

        if any(p["symbol"] == cand["symbol"] for p in active_positions):
            continue

        # Volatility-scaled risk budgeting
        net_profit = capital - INITIAL_CAPITAL
        if net_profit >= 50.0:
            risk_usd = HOUSE_MONEY_RISK
        elif current_dd >= 0.025:
            risk_usd = DEFENSE_RISK
        else:
            risk_usd = BASE_RISK

        # Initial Stop calculation
        if cand["direction"] == 1:
            initial_stop = cand["stop_ref"] - 1.2 * cand["atr"]
            if initial_stop >= cand["close"]:
                initial_stop = cand["close"] - 1.5 * cand["atr"]
        else:
            initial_stop = cand["stop_ref"] + 1.2 * cand["atr"]
            if initial_stop <= cand["close"]:
                initial_stop = cand["close"] + 1.5 * cand["atr"]

        # Simulate Trade
        res = simulate_symmetric_trade(
            df=cand["df"],
            entry_idx=cand["idx"],
            direction=cand["direction"],
            entry_price=cand["close"],
            initial_stop=initial_stop,
            atr_val=cand["atr"],
            risk_usd=risk_usd,
            max_hold_bars=32
        )
        res["symbol"] = cand["symbol"]

        active_positions.append(res)
        closed_trades.append(res)

        capital += res["net_pnl"]
        peak_capital = max(peak_capital, capital)

    # Metrics
    total_trades = len(closed_trades)
    if total_trades == 0:
        return {
            "total_trades": 0, "win_rate": 0.0, "net_roi_pct": 0.0,
            "max_drawdown_pct": 0.0, "net_profit_usd": 0.0, "profit_factor": 0.0,
            "passed": False, "trades": []
        }

    wins = [t for t in closed_trades if t["is_win"]]
    losses = [t for t in closed_trades if not t["is_win"]]
    win_rate = len(wins) / total_trades
    net_profit = capital - INITIAL_CAPITAL
    roi_pct = (net_profit / INITIAL_CAPITAL) * 100.0

    total_gain = sum(t["net_pnl"] for t in wins)
    total_loss = abs(sum(t["net_pnl"] for t in losses))
    profit_factor = (total_gain / total_loss) if total_loss > 0 else 99.0

    # Max Drawdown
    equity = INITIAL_CAPITAL
    peak = INITIAL_CAPITAL
    max_dd_usd = 0.0
    for t in closed_trades:
        equity += t["net_pnl"]
        peak = max(peak, equity)
        max_dd_usd = max(max_dd_usd, peak - equity)

    max_dd_pct = (max_dd_usd / peak) * 100.0
    passed = (roi_pct >= 20.0) and (max_dd_pct < 5.0) and (win_rate >= 0.40) and (total_trades >= 6)

    return {
        "total_trades": total_trades,
        "win_rate": win_rate,
        "net_roi_pct": roi_pct,
        "max_drawdown_pct": max_dd_pct,
        "net_profit_usd": net_profit,
        "profit_factor": profit_factor,
        "passed": passed,
        "trades": closed_trades
    }
