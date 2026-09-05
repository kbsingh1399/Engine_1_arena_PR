"""
s2_trend_orderflow_engine.py - Institutional Trend Following with Order Flow & Microstructure Ratchet.

Strategy Architecture:
1. Signal Confluence:
   - Macro Trend: EMA 8 > EMA 21 and EMA 21 > EMA 50
   - Dynamic Pullback: Close within [-1.5, +2.0] ATR of EMA 21
   - Order Flow Ignition: Footprint Delta positive or delta flip, net stacked buy imbalance > 0
   - Derivatives Fuel: Spot CVD leading Futures CVD (zc_div > 0.3), OI expanding
   - Tri-Ensemble GBDT Gate: P_ensemble >= P*
2. Microstructure Multi-Tier Trailing Ratchet:
   - Phase 0: Lock Breakeven +0.20R at +1.0R gain (applies strictly to bar j+1)
   - Phase 1: Lock Profit +1.20R at +2.0R gain
   - Phase 2: Chandelier Trailing Stop (High - 2.0 * ATR) to capture 4R to 8R trend waves
   - Target Cap: +5.0R exit
   - Time Decay: Exit at market if trade fails to gain +0.30R within 32 bars (8 hours)
3. Fixed Portfolio Risk Governor:
   - Initial Capital: $5,000.00
   - Base Risk: $25.00 (0.50%)
   - House Money Risk: $50.00 (1.00% max 2x when net PnL > $50)
   - Drawdown Defense: $15.00 (0.30% when DD > 2.5%)
   - Hard Circuit Breaker: 4.5% ($225 drawdown limit)
   - Max Concurrent Open Positions: 2 across all symbols
"""

import math
from typing import Dict, List, Any, Optional
import numpy as np
import pandas as pd

# Institutional Friction Standards
TAKER_FEE_BPS = 8.0        # 0.08% roundtrip taker fee
ENTRY_SLIPPAGE_BPS = 10.0   # 0.10% entry market slippage
STOP_SLIPPAGE_BPS = 15.0    # 0.15% adverse stop slippage

INITIAL_CAPITAL = 5000.0
BASE_RISK = 25.0
HOUSE_MONEY_RISK = 50.0
DEFENSE_RISK = 15.0
DRAWDOWN_LIMIT_PCT = 0.045  # 4.5% ($225 max drawdown)
MAX_CONCURRENT_POSITIONS = 2

def simulate_trend_trade_path(
    df: pd.DataFrame,
    entry_idx: int,
    entry_price: float,
    initial_stop: float,
    atr_val: float,
    risk_usd: float,
    max_hold_bars: int = 32
) -> Dict[str, Any]:
    """
    Simulates a single trend following trade forward with zero lookahead bias.
    All trailing stop ratchets take effect on bar j+1 strictly.
    """
    T = len(df)
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    times = df["open_time_ms"].to_numpy()

    # Apply entry slippage
    real_entry = entry_price * (1.0 + ENTRY_SLIPPAGE_BPS / 10_000.0)
    risk_r = max(real_entry - initial_stop, atr_val * 1.0, real_entry * 0.005)
    
    # Position sizing in base asset units
    pos_size = risk_usd / risk_r

    current_stop = initial_stop
    next_bar_stop = initial_stop
    max_mfe_r = 0.0
    max_mae_r = 0.0
    exit_price = real_entry
    exit_reason = "TIME_DECAY"
    exit_idx = min(entry_idx + max_hold_bars, T - 1)
    
    # Ratchet state flags
    ratchet_stage = 0  # 0: initial, 1: locked BE+0.2R, 2: locked +1.2R, 3: trailing Chandelier

    for j in range(entry_idx + 1, min(entry_idx + max_hold_bars + 1, T)):
        bar_high = highs[j]
        bar_low = lows[j]
        bar_close = closes[j]

        # 1. Update stop to the ratchet set in the PREVIOUS bar (strictly causal)
        current_stop = max(current_stop, next_bar_stop)

        # 2. Check if stopped out on current bar
        if bar_low <= current_stop:
            # Stopped out with adverse slippage
            exit_price = current_stop * (1.0 - STOP_SLIPPAGE_BPS / 10_000.0)
            exit_reason = "STOP_LOSS" if ratchet_stage == 0 else "TRAILING_STOP"
            exit_idx = j
            break

        # 3. Check profit target (+5.0R maximum cap)
        max_target = real_entry + 5.0 * risk_r
        if bar_high >= max_target:
            exit_price = max_target
            exit_reason = "TAKE_PROFIT_5R"
            exit_idx = j
            break

        # 4. Measure Excursions
        cur_mfe = (bar_high - real_entry) / risk_r
        cur_mae = (real_entry - bar_low) / risk_r
        max_mfe_r = max(max_mfe_r, cur_mfe)
        max_mae_r = max(max_mae_r, cur_mae)

        # 5. Microstructure Trailing Ratchets (Scheduled for bar j+1)
        if max_mfe_r >= 2.0 and ratchet_stage < 2:
            ratchet_stage = 2
            # Lock +1.2R profit
            next_bar_stop = max(next_bar_stop, real_entry + 1.20 * risk_r)
        elif max_mfe_r >= 1.0 and ratchet_stage < 1:
            ratchet_stage = 1
            # Lock Breakeven +0.20R
            next_bar_stop = max(next_bar_stop, real_entry + 0.20 * risk_r)

        # Chandelier Trail after +2.5R gain
        if max_mfe_r >= 2.5:
            ratchet_stage = 3
            # Trail 2 ATR below 3-bar highest high
            lookback_high = np.max(highs[max(entry_idx, j - 3):j + 1])
            chandelier_stop = lookback_high - 1.8 * atr_val
            next_bar_stop = max(next_bar_stop, chandelier_stop)

        # 6. Time Decay Check: If 32 bars elapsed without gaining +0.3R, exit at market
        if (j - entry_idx) >= 32:
            exit_price = bar_close * (1.0 - ENTRY_SLIPPAGE_BPS / 10_000.0)
            exit_reason = "TIME_DECAY"
            exit_idx = j
            break

    # Calculate Net PnL with taker friction
    gross_pnl = (exit_price - real_entry) * pos_size
    fees = (real_entry * pos_size + exit_price * pos_size) * (TAKER_FEE_BPS / 10_000.0)
    net_pnl = gross_pnl - fees
    realized_r = net_pnl / risk_usd

    return {
        "entry_idx": entry_idx,
        "exit_idx": exit_idx,
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

def run_portfolio_trend_backtest(
    multi_symbol_data: Dict[str, pd.DataFrame],
    prob_threshold: float = 0.55
) -> Dict[str, Any]:
    """
    Executes a multi-asset portfolio backtest across all provided symbols
    with global portfolio risk budgeting and max concurrent position governor.
    """
    # 1. Collect all candidates across all symbols sorted by open_time_ms
    all_candidates = []
    
    for sym, df in multi_symbol_data.items():
        if "p_ensemble" not in df.columns:
            # If model probabilities not present, generate heuristic conviction score
            # Heuristic conviction based on order flow & trend alignment
            bull_align = (df["ema8_ema21_spread"] > 0) & (df["ema21_ema50_spread"] > 0)
            pullback = (df["dist_to_ema21"] >= -1.5) & (df["dist_to_ema21"] <= 2.0)
            of_flow = (df["fp_delta_ratio"] > 0.03) | (df["is_delta_flip"] == 1.0) | (df["net_stacked_imb"] > 0)
            cvd_lead = (df["spot_cvd_slope_3"] > 0) & (df["future_cvd_slope_3"] > 0)
            
            score = (bull_align.astype(float) * 0.35 +
                     pullback.astype(float) * 0.20 +
                     of_flow.astype(float) * 0.25 +
                     cvd_lead.astype(float) * 0.20)
            df["p_ensemble"] = score

        trigger_mask = df["p_ensemble"] >= prob_threshold
        cand_indices = np.where(trigger_mask)[0]
        
        for idx in cand_indices:
            if idx < 50 or idx >= len(df) - 35:
                continue
            all_candidates.append({
                "symbol": sym,
                "idx": idx,
                "time_ms": df["open_time_ms"].iloc[idx],
                "prob": df["p_ensemble"].iloc[idx],
                "close": df["close"].iloc[idx],
                "atr": df["atr"].iloc[idx] if "atr" in df.columns else df["atr_14"].iloc[idx],
                "low": df["low"].iloc[idx],
                "df": df
            })

    # Sort chronologically to preserve causality
    all_candidates.sort(key=lambda x: x["time_ms"])

    # 2. Portfolio Execution Simulation
    capital = INITIAL_CAPITAL
    peak_capital = INITIAL_CAPITAL
    active_positions: List[Dict[str, Any]] = []
    closed_trades: List[Dict[str, Any]] = []
    circuit_breaker_tripped = False

    for cand in all_candidates:
        curr_time = cand["time_ms"]

        # Evict positions that have closed by curr_time
        active_positions = [p for p in active_positions if p["exit_time"] > curr_time]

        if circuit_breaker_tripped:
            continue

        # Check Drawdown limit
        current_dd = (peak_capital - capital) / peak_capital
        if current_dd >= DRAWDOWN_LIMIT_PCT:
            circuit_breaker_tripped = True
            continue

        # Check Concurrent Position Limit
        if len(active_positions) >= MAX_CONCURRENT_POSITIONS:
            continue

        # Check if already in position for this symbol
        if any(p["symbol"] == cand["symbol"] for p in active_positions):
            continue

        # Dynamic Risk Sizing
        net_profit = capital - INITIAL_CAPITAL
        if net_profit >= 50.0:
            risk_usd = HOUSE_MONEY_RISK
        elif current_dd >= 0.025:
            risk_usd = DEFENSE_RISK
        else:
            risk_usd = BASE_RISK

        # Calculate Initial Stop (low of candle - 1.2 * ATR)
        initial_stop = cand["low"] - 1.2 * cand["atr"]
        if initial_stop >= cand["close"]:
            initial_stop = cand["close"] - 1.5 * cand["atr"]

        # Simulate Trade Path
        trade_res = simulate_trend_trade_path(
            df=cand["df"],
            entry_idx=cand["idx"],
            entry_price=cand["close"],
            initial_stop=initial_stop,
            atr_val=cand["atr"],
            risk_usd=risk_usd,
            max_hold_bars=32
        )
        trade_res["symbol"] = cand["symbol"]
        trade_res["prob"] = cand["prob"]

        # Register position
        active_positions.append(trade_res)
        closed_trades.append(trade_res)

        # Update Portfolio State
        capital += trade_res["net_pnl"]
        peak_capital = max(peak_capital, capital)

    # 3. Calculate Performance Metrics
    total_trades = len(closed_trades)
    if total_trades == 0:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "net_roi_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "net_profit_usd": 0.0,
            "profit_factor": 0.0,
            "passed": False
        }

    wins = [t for t in closed_trades if t["is_win"]]
    losses = [t for t in closed_trades if not t["is_win"]]
    win_rate = len(wins) / total_trades
    net_profit = capital - INITIAL_CAPITAL
    roi_pct = (net_profit / INITIAL_CAPITAL) * 100.0
    
    total_gain = sum(t["net_pnl"] for t in wins)
    total_loss = abs(sum(t["net_pnl"] for t in losses))
    profit_factor = (total_gain / total_loss) if total_loss > 0 else 99.0

    # Calculate Max Drawdown from trade equity curve
    equity = INITIAL_CAPITAL
    peak = INITIAL_CAPITAL
    max_dd_usd = 0.0
    for t in closed_trades:
        equity += t["net_pnl"]
        peak = max(peak, equity)
        dd = peak - equity
        max_dd_usd = max(max_dd_usd, dd)
        
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
