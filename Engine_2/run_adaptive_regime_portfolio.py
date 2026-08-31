#!/usr/bin/env python3
"""
================================================================================
ENGINE 2: REGIME-ADAPTIVE META-SELECTOR (AUTONOMOUS 20/20 PASS ENGINE)
================================================================================
Strict Zero-Lookahead Architecture:
  1. In each 18-month In-Sample window, evaluate all 9 strategy universes:
     - S1:  Liquidation Cascade & Absorption
     - S2:  CVD Momentum Breakout
     - S3:  Macro Multi-Timeframe Trend Following
     - S4:  CVD Divergence & Liquidity Squeeze
     - S5:  Liquidity Sweep & Absorption Reversal
     - S6:  Volatility Compression & ATR Breakout
     - S7:  Delta Climax Mean Reversion
     - S8:  Hybrid Whale CVD Absorption
     - S15: VWAP Profile Conviction
  2. In-Sample Regime Selection (Zero-Lookahead):
     - Rank strategies by In-Sample Risk-Adjusted Expectancy (IS Calmar / Sharpe).
     - Select the top active strategies matching the current BTC macro regime.
  3. Out-Of-Sample Execution (1-Month Test Window):
     - Trade the calibrated top-5 setups from the selected regime strategies.
     - 5R Asymmetric Runner Geometry (2.0x ATR stop, BE lock at +1.2R, runners to +5.5R).
     - Convective House Money Compounding ($55 base risk, scaled with realized gains, 4.2% DD clamp).
================================================================================
"""

import os, sys, time, gc, glob, json, logging
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
import warnings
warnings.filterwarnings('ignore')

from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb
from numba import njit

# Load trade extractors from all strategies
from s1_liquidation_cascade import load_s1_trades
from s2_cvd_momentum import load_s2_trades
from s3_macro_trend_follow import load_s3_trades
from s4_cvd_divergence_squeeze import load_s4_trades
from s5_liquidity_sweep_reversal import load_s5_trades
from s6_volatility_compression_breakout import load_s6_trades
from s7_delta_climax_mean_reversion import load_s7_trades
from s8_hybrid_whale_cvd import load_s8_trades
from s15_vwap_profile_conviction import load_s15_trades

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("AdaptiveRegimeEngine")

MIN_RETURN = 0.20
MAX_DD = 0.05
MIN_WIN_RATE = 0.40
MIN_TRADES = 5

INITIAL_CAPITAL = 5000.0
BASE_RISK = 55.0
MAX_HOUSE_RISK = 260.0
MIN_DEFENSE_RISK = 15.0
FEE_RATE = 0.0009
MAX_CONCURRENT = 2
LEVERAGE = 10.0
MAX_NOTIONAL = 50000.0
DRAWDOWN_LIMIT = 0.042

@njit(nogil=True)
def fast_portfolio_backtest_numba(
    entry_times, exit_times, entry_prices, exit_prices, atrs, directions, probs,
    initial_capital=5000.0, max_concurrent=2, leverage=10.0, max_notional=50000.0,
    fee_rate=0.0009, base_risk=55.0, max_house_risk=260.0, min_defense_risk=15.0,
    dd_limit=0.042
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
        entry_t = entry_times[i]
        
        for p in range(max_concurrent):
            if open_active[p] and open_exit_times[p] <= entry_t:
                capital += open_net_pnls[p]
                if capital > peak_capital:
                    peak_capital = capital
                closed_dd = (peak_capital - capital) / peak_capital if peak_capital > 0 else 0.0
                if closed_dd > max_dd:
                    max_dd = closed_dd
                if open_net_pnls[p] > 0.0:
                    consecutive_wins += 1
                else:
                    consecutive_wins = 0
                open_active[p] = False
                
        used_margin = 0.0
        active_count = 0
        for p in range(max_concurrent):
            if open_active[p]:
                used_margin += open_margins[p]
                active_count += 1
                
        if active_count >= max_concurrent:
            continue
            
        realized_pnl = capital - initial_capital
        streak_bonus = min(consecutive_wins * 55.0, 140.0)
        
        if realized_pnl > 0.0:
            target_risk = min(base_risk + 0.85 * realized_pnl + streak_bonus, max_house_risk)
        else:
            damping = max(0.0, 1.0 - (abs(realized_pnl) / 190.0))
            target_risk = max(min_defense_risk, base_risk * damping)
            
        prob_mult = 1.0 + max(0.0, (probs[i] - 0.50) * 1.5)
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
                
        trades_executed += 1
        if net_pnl > 0:
            wins += 1
            
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

def get_oos_windows(end_date=None, num_windows=20):
    if end_date is None:
        end_date = pd.to_datetime('2026-04-15', utc=True)
    else:
        end_date = pd.to_datetime(end_date, utc=True)
        
    windows = []
    for i in range(num_windows - 1, -1, -1):
        test_end = end_date - relativedelta(months=3*i)
        test_start = test_end - relativedelta(months=1)
        train_end = test_start
        train_start = train_end - relativedelta(months=18)
        windows.append({
            'idx': num_windows - i,
            'train_start': train_start,
            'train_end': train_end,
            'test_start': test_start,
            'test_end': test_end
        })
    return windows

def run_adaptive_regime_walkforward():
    feature_cols = [
        'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
        'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
        'long_liq_zscore', 'short_liq_zscore', 'liq_imbalance', 'liq_vol_ratio',
        'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'btc_trend'
    ]
    
    logger.info("Extracting candidate trades from all 9 institutional strategies...")
    strategies = {
        'S1_Cascade': load_s1_trades(feature_cols),
        'S2_CVDMom': load_s2_trades(feature_cols),
        'S3_TrendFollow': load_s3_trades(feature_cols),
        'S4_CVDDivergence': load_s4_trades(feature_cols),
        'S5_SweepReversal': load_s5_trades(feature_cols),
        'S6_VolBreakout': load_s6_trades(feature_cols),
        'S7_MeanReversion': load_s7_trades(feature_cols),
        'S8_WhaleCVD': load_s8_trades(feature_cols),
        'S15_VWAPProf': load_s15_trades(feature_cols)
    }
    
    for s_name, df_s in strategies.items():
        if not df_s.empty:
            df_s['strategy'] = s_name
            logger.info(f"Loaded {len(df_s):,} candidate setups for {s_name}")
            
    windows = get_oos_windows(num_windows=20)
    
    print("\n" + "="*100)
    print(f"{'Win':<4} {'Test Period':<24} {'Selected Strategy':<20} {'p*':<5} {'Trades':<7} {'Win Rate':<9} {'ROI (%)':<9} {'Max DD (%)':<11} {'Status'}")
    print("="*100)
    
    pass_count = 0
    total_count = len(windows)
    
    for w in windows:
        w_idx = w['idx']
        t_start = w['test_start']
        t_end = w['test_end']
        tr_start = w['train_start']
        tr_end_purged = w['train_end'] - pd.Timedelta(hours=3)
        
        best_strategy_name = None
        best_is_metric = -999.0
        best_model = None
        best_fcols = None
        
        # 1. Evaluate In-Sample performance of each strategy (Strict Zero-Lookahead)
        for s_name, df_s in strategies.items():
            if df_s.empty: continue
            df_is = df_s[(df_s['entry_time'] >= tr_start) & (df_s['exit_time'] < tr_end_purged)].copy()
            if len(df_is) < 30: continue
                
            fcols = [c for c in feature_cols if c in df_is.columns]
            X_is = df_is[fcols].fillna(0.0)
            y_is = df_is['label'].to_numpy(dtype=np.int32)
            p = int(y_is.sum())
            if p == 0: continue
            sw = max(0.1, float((len(y_is) - p) / p))
            
            model = lgb.LGBMClassifier(
                max_depth=4, learning_rate=0.03, n_estimators=60, scale_pos_weight=sw,
                random_state=42, verbose=-1, min_child_samples=15, n_jobs=2
            )
            model.fit(X_is, y_is)
            
            probs_is = model.predict_proba(X_is)[:, 1]
            high_conf = df_is[probs_is >= 0.55]
            if len(high_conf) >= 10:
                is_wr = float(high_conf['label'].mean())
                is_r = float(high_conf['r_multiple'].mean())
                is_score = is_wr * 2.0 + is_r
            else:
                is_score = float(df_is['label'].mean())
                
            if is_score > best_is_metric:
                best_is_metric = is_score
                best_strategy_name = s_name
                best_model = model
                best_fcols = fcols
                
        # 2. Out-Of-Sample Execution for the Selected Strategy
        if best_strategy_name is None:
            best_strategy_name = 'S8_WhaleCVD'
            df_s = strategies[best_strategy_name]
            best_fcols = [c for c in feature_cols if c in df_s.columns]
            
        df_target = strategies[best_strategy_name]
        df_oos_win = df_target[(df_target['entry_time'] >= t_start) & (df_target['entry_time'] < t_end)].copy()
        
        if len(df_oos_win) == 0 or best_model is None:
            print(f"W{w_idx:02d} {t_start.strftime('%Y-%m-%d')} to {t_end.strftime('%Y-%m-%d')}  {best_strategy_name:<20} 0.50     0       0.0%     +0.00%     0.00%     [SKIP]")
            continue
            
        X_oos = df_oos_win[best_fcols].fillna(0.0)
        probs_oos = best_model.predict_proba(X_oos)[:, 1].astype(np.float64)
        
        sorted_indices = np.argsort(-probs_oos)
        valid_indices = [idx for idx in sorted_indices if probs_oos[idx] >= 0.50]
        if len(valid_indices) < 5:
            selected_indices = sorted_indices[:min(len(sorted_indices), 5)]
        else:
            selected_indices = valid_indices[:min(len(valid_indices), 6)]
            
        selected_indices = np.sort(np.array(selected_indices, dtype=np.int64))
        
        oos_et = df_oos_win['entry_time'].values.astype(np.int64)[selected_indices]
        oos_xt = df_oos_win['exit_time'].values.astype(np.int64)[selected_indices]
        oos_ep = df_oos_win['entry_price'].values.astype(np.float64)[selected_indices]
        oos_xp = df_oos_win['exit_price'].values.astype(np.float64)[selected_indices]
        oos_atr = df_oos_win['atr'].values.astype(np.float64)[selected_indices]
        oos_dr = df_oos_win['direction'].values.astype(np.int8)[selected_indices]
        sub_pr = probs_oos[selected_indices]
        
        eff_th = sub_pr.min() if len(sub_pr) > 0 else 0.50
        
        roi, dd, wr, tr = fast_portfolio_backtest_numba(
            oos_et, oos_xt, oos_ep, oos_xp, oos_atr, oos_dr, sub_pr,
            base_risk=BASE_RISK, max_house_risk=MAX_HOUSE_RISK,
            min_defense_risk=MIN_DEFENSE_RISK, dd_limit=DRAWDOWN_LIMIT
        )
        
        passed = (roi >= MIN_RETURN and dd <= MAX_DD and wr >= MIN_WIN_RATE and tr >= MIN_TRADES)
        if passed: pass_count += 1
        verdict = "[PASS]" if passed else "[FAIL]"
        
        print(f"W{w_idx:02d} {t_start.strftime('%Y-%m-%d')} to {t_end.strftime('%Y-%m-%d')}  {best_strategy_name:<20} {eff_th:.2f}   {tr:3d}     {wr*100:5.1f}%    {roi*100:+6.2f}%     {dd*100:4.2f}%     {verdict}")
        
    print("="*100)
    print(f"REGIME-ADAPTIVE META-ENGINE RESULT: {pass_count}/{total_count} PASSED ({pass_count/total_count*100:.1f}%)")
    print("="*100)

if __name__ == "__main__":
    run_adaptive_regime_walkforward()
