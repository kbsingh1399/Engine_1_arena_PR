#!/usr/bin/env python3
"""
================================================================================
ENGINE 2: S1 - LIQUIDATION CASCADE (5R RUNNER & TOP-5 SELECTION)
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("S1_LiquidationCascade")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
DATA_DIR = os.path.join(SCRIPT_DIR, "binance_backtesting_data") if os.path.exists(os.path.join(SCRIPT_DIR, "binance_backtesting_data")) else SCRIPT_DIR
RESULTS_DIR = os.path.join(SCRIPT_DIR, "results_s1")
os.makedirs(RESULTS_DIR, exist_ok=True)

MIN_RETURN = 0.20
MAX_DD = 0.05
MIN_WIN_RATE = 0.40
MIN_TRADES = 5

INITIAL_CAPITAL = 5000.0
BASE_RISK = 45.0
MAX_HOUSE_RISK = 260.0
MIN_DEFENSE_RISK = 15.0
FEE_RATE = 0.0009
MAX_CONCURRENT = 2
LEVERAGE = 10.0
MAX_NOTIONAL = 50000.0
DRAWDOWN_LIMIT = 0.042

def zs(s, w):
    m = s.rolling(w, min_periods=1).mean()
    std = s.rolling(w, min_periods=1).std().replace(0.0, 1e-8)
    return ((s - m) / std).clip(-5.0, 5.0).fillna(0.0)

def compute_true_atr(df, period=14):
    prev_close = df['close'].shift(1)
    tr1 = df['high'] - df['low']
    tr2 = (df['high'] - prev_close).abs()
    tr3 = (df['low'] - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=1).mean()

@njit(nogil=True)
def simulate_single_trade_path(highs, lows, closes, entry_idx, entry_price, atr, direction, max_bars=144):
    stop_dist = max(2.2 * atr, entry_price * 0.0065)
    cur_stop = entry_price - stop_dist if direction == 1 else entry_price + stop_dist
    best_price = entry_price
    
    exit_price = closes[min(entry_idx + max_bars, len(closes) - 1)]
    exit_offset = max_bars
    max_idx = min(entry_idx + max_bars + 1, len(closes))
    
    SLIPPAGE_PCT = 0.0005
    
    for j in range(entry_idx + 1, max_idx):
        bars_held = j - entry_idx
        
        if direction == 1: # LONG
            if lows[j] <= cur_stop:
                exit_price = cur_stop * (1.0 - SLIPPAGE_PCT)
                exit_offset = bars_held
                break
                
            if bars_held == 48 and (highs[j] - entry_price) < 0.35 * stop_dist:
                exit_price = closes[j]
                exit_offset = bars_held
                break
                
            if highs[j] > best_price:
                best_price = highs[j]
                gain = best_price - entry_price
                if gain >= 5.0 * stop_dist:
                    exit_price = entry_price + 5.0 * stop_dist
                    exit_offset = bars_held
                    break
                elif gain >= 3.2 * stop_dist:
                    new_stop = entry_price + 2.2 * stop_dist
                    if new_stop > cur_stop: cur_stop = new_stop
                elif gain >= 1.8 * stop_dist:
                    new_stop = entry_price + 0.40 * stop_dist
                    if new_stop > cur_stop: cur_stop = new_stop
        else: # SHORT
            if highs[j] >= cur_stop:
                exit_price = cur_stop * (1.0 + SLIPPAGE_PCT)
                exit_offset = bars_held
                break
                
            if bars_held == 48 and (entry_price - lows[j]) < 0.35 * stop_dist:
                exit_price = closes[j]
                exit_offset = bars_held
                break
                
            if lows[j] < best_price:
                best_price = lows[j]
                gain = entry_price - best_price
                if gain >= 5.0 * stop_dist:
                    exit_price = entry_price - 5.0 * stop_dist
                    exit_offset = bars_held
                    break
                elif gain >= 3.2 * stop_dist:
                    new_stop = entry_price - 2.2 * stop_dist
                    if new_stop < cur_stop: cur_stop = new_stop
                elif gain >= 1.8 * stop_dist:
                    new_stop = entry_price - 0.40 * stop_dist
                    if new_stop < cur_stop: cur_stop = new_stop
                    
    return exit_price, exit_offset

@njit(nogil=True)
def gen_symbol_trades(highs, lows, closes, next_opens, atrs, sig):
    n = len(closes)
    results = []
    i = 100
    cd = 0
    
    while i < n - 100:
        if i >= cd:
            dr = sig[i]
            if dr != 0:
                entry = next_opens[i]
                av = atrs[i]
                if av > 0 and not np.isnan(av) and entry > 0 and not np.isnan(entry):
                    ep, offset = simulate_single_trade_path(
                        highs, lows, closes, i, entry, av, int(dr), 144
                    )
                    stop_dist = max(2.2 * av, entry * 0.0065)
                    r_mult = (ep - entry) / stop_dist if dr == 1 else (entry - ep) / stop_dist
                    lb = 1.0 if r_mult >= 1.0 else 0.0
                    results.append((i, dr, ep, r_mult, lb, offset))
                    cd = i + max(offset, 1) + 2
        i += 1
    return results

def s1_signal_predicate(df):
    long_mask = (df['long_liq_zscore'] > 1.2) & (df['spot_cvd_delta'] > 0) & (df['vol_ratio'] > 1.1) & (df['btc_trend'] > -0.02)
    short_mask = (df['short_liq_zscore'] > 1.2) & (df['spot_cvd_delta'] < 0) & (df['vol_ratio'] > 1.1) & (df['btc_trend'] < 0.02)
    return long_mask, short_mask

def load_s1_trades(feature_cols):
    search_dirs = [DATA_DIR, SCRIPT_DIR, os.path.join(SCRIPT_DIR, "binance_backtesting_data")]
    files = []
    for d in search_dirs:
        if d and os.path.exists(d):
            found = glob.glob(os.path.join(d, "*_15m_master_*.parquet"))
            if found:
                files = sorted(list(set(found)))
                break
                
    if not files: return pd.DataFrame()

    btc_ref = None
    for f in files:
        if "BTCUSDT" in os.path.basename(f):
            try:
                bdf = pd.read_parquet(f, columns=['datetime_utc', 'close', 'spot_cvd_15m', 'future_cvd_15m'])
                bdf['datetime_utc'] = pd.to_datetime(bdf['datetime_utc'], utc=True)
                bdf = bdf.sort_values('datetime_utc').reset_index(drop=True)
                s_raw = bdf['spot_cvd_15m'].fillna(0.0)
                f_raw = bdf['future_cvd_15m'].fillna(0.0)
                s_diff = s_raw.diff().fillna(0.0)
                f_diff = f_raw.diff().fillna(0.0)
                cvd_delta = np.where(s_diff.abs() > 1e-5, s_diff, f_diff)
                cvd_cum = pd.Series(np.cumsum(cvd_delta), index=bdf.index)
                
                btc_ema50 = bdf['close'].ewm(span=50).mean()
                btc_trend = ((bdf['close'] - btc_ema50) / btc_ema50).clip(-0.20, 0.20).fillna(0.0)
                
                btc_ref = pd.DataFrame({
                    'datetime_utc': bdf['datetime_utc'],
                    'btc_close': bdf['close'].astype(np.float32),
                    'btc_trend': btc_trend.astype(np.float32),
                    'zb20': zs(cvd_cum, 96).astype(np.float32),
                    'zb4': zs(cvd_cum, 4).astype(np.float32)
                })
                del bdf; gc.collect()
                break
            except Exception as e: pass

    trades_list = []
    cols_to_load = [
        'datetime_utc', 'open', 'high', 'low', 'close', 'volume_base',
        'spot_cvd_15m', 'future_cvd_15m', 'long_liq_usd', 'short_liq_usd'
    ]
    for f in sorted(files):
        sym = os.path.basename(f).split('_')[0]
        if not sym.endswith("USDT"): continue
        try:
            df = pd.read_parquet(f, columns=cols_to_load)
            df['datetime_utc'] = pd.to_datetime(df['datetime_utc'], utc=True)
            df = df.sort_values('datetime_utc').reset_index(drop=True)
            
            s_raw = df.get('spot_cvd_15m', pd.Series(0.0, index=df.index)).fillna(0.0)
            f_raw = df.get('future_cvd_15m', pd.Series(0.0, index=df.index)).fillna(0.0)
            s_diff = s_raw.diff().fillna(0.0)
            f_diff = f_raw.diff().fillna(0.0)
            active_delta = pd.Series(np.where(s_diff.abs() > 1e-5, s_diff, f_diff), index=df.index)
            active_cvd = pd.Series(np.cumsum(active_delta), index=df.index)
            
            if btc_ref is not None and sym != "BTCUSDT":
                df = pd.merge_asof(df, btc_ref, on='datetime_utc', direction='backward')
            elif sym == "BTCUSDT":
                df['btc_close'] = df['close']
                btc_ema50 = df['close'].ewm(span=50).mean()
                df['btc_trend'] = ((df['close'] - btc_ema50) / btc_ema50).clip(-0.20, 0.20).fillna(0.0).astype(np.float32)
                df['zb20'] = zs(active_cvd, 96).astype(np.float32)
                df['zb4'] = zs(active_cvd, 4).astype(np.float32)
                
            df['atr'] = compute_true_atr(df, 14).astype(np.float32)
            df['cvd_divergence'] = (s_raw - f_raw).astype(np.float32)
            df['spot_cvd_delta'] = active_delta.astype(np.float32)
            df['future_cvd_delta'] = f_diff.astype(np.float32)
            df['spot_cvd_accel'] = active_delta.diff().fillna(0.0).astype(np.float32)
            
            df['zc4'] = zs(active_cvd, 4).astype(np.float32)
            df['zc10'] = zs(active_cvd, 10).astype(np.float32)
            df['zc20'] = zs(active_cvd, 96).astype(np.float32)
            df['zc_rel_btc'] = (df['zc20'] - df.get('zb20', 0.0)).astype(np.float32)
            df['zc4_rel_btc'] = (df['zc4'] - df.get('zb4', 0.0)).astype(np.float32)
            
            long_liq = df.get('long_liq_usd', pd.Series(0.0, index=df.index)).abs().fillna(0.0)
            short_liq = df.get('short_liq_usd', pd.Series(0.0, index=df.index)).abs().fillna(0.0)
            df['long_liq_zscore'] = zs(long_liq, 96).astype(np.float32)
            df['short_liq_zscore'] = zs(short_liq, 96).astype(np.float32)
            denom = long_liq + short_liq + 1e-8
            df['liq_imbalance'] = ((long_liq - short_liq) / denom).astype(np.float32)
            vol_q = df.get('volume_quote', df['close'] * df.get('volume_base', 1.0))
            df['liq_vol_ratio'] = (denom / (vol_q + 1e-8)).astype(np.float32)
            
            c = df['close']
            df['p8'] = ((c - c.ewm(span=8).mean()) / c.ewm(span=8).mean()).clip(-1.0, 1.0).astype(np.float32)
            df['p21'] = ((c - c.ewm(span=21).mean()) / c.ewm(span=21).mean()).clip(-1.0, 1.0).astype(np.float32)
            df['p50'] = ((c - c.ewm(span=50).mean()) / c.ewm(span=50).mean()).clip(-1.0, 1.0).astype(np.float32)
            df['p200'] = ((c - c.ewm(span=200).mean()) / c.ewm(span=200).mean()).clip(-1.0, 1.0).astype(np.float32)
            df['mc'] = ((c.ewm(span=8).mean() - c.ewm(span=21).mean()) / c).astype(np.float32)
            
            diff = c.diff()
            gain = diff.clip(lower=0).rolling(14, min_periods=1).mean()
            loss = (-diff.clip(upper=0)).rolling(14, min_periods=1).mean()
            rs = gain / (loss + 1e-8)
            df['rsi'] = (100.0 - (100.0 / (1.0 + rs))).astype(np.float32)
            
            v = df.get('volume_base', pd.Series(1.0, index=df.index)).fillna(1.0)
            df['vol_ratio'] = (v / (v.rolling(96, min_periods=1).mean() + 1e-8)).clip(0.0, 10.0).astype(np.float32)
            
            df['next_open'] = df['open'].shift(-1).astype(np.float64)
            df = df.dropna(subset=['next_open', 'atr']).reset_index(drop=True)
            
            highs = df['high'].to_numpy(dtype=np.float64)
            lows = df['low'].to_numpy(dtype=np.float64)
            closes = df['close'].to_numpy(dtype=np.float64)
            next_opens = df['next_open'].to_numpy(dtype=np.float64)
            atrs = df['atr'].to_numpy(dtype=np.float64)
            datetimes = df['datetime_utc'].to_numpy()
            
            feat_dict = {col: df[col].to_numpy(dtype=np.float32) for col in feature_cols if col in df.columns}
            
            mask_l, mask_s = s1_signal_predicate(df)
            sig = np.zeros(len(df), dtype=np.int8)
            sig[mask_l] = 1
            sig[mask_s] = -1
            
            res = gen_symbol_trades(highs, lows, closes, next_opens, atrs, sig)
            if res:
                for r in res:
                    idx, dr, ep, r_mult, lb, offset = r
                    row = {
                        'symbol': sym,
                        'entry_time': datetimes[idx],
                        'exit_time': datetimes[min(idx + offset, len(datetimes) - 1)],
                        'entry_price': next_opens[idx],
                        'exit_price': ep,
                        'atr': atrs[idx],
                        'direction': dr,
                        'r_multiple': r_mult,
                        'label': lb
                    }
                    for col in feature_cols:
                        if col in feat_dict:
                            row[col] = feat_dict[col][idx]
                    trades_list.append(row)
                    
            del df, highs, lows, closes, next_opens, atrs, datetimes, feat_dict
            gc.collect()
        except Exception as e: pass
            
    if not trades_list: return pd.DataFrame()
    df_out = pd.DataFrame(trades_list)
    df_out['entry_time'] = pd.to_datetime(df_out['entry_time'], utc=True)
    df_out['exit_time'] = pd.to_datetime(df_out['exit_time'], utc=True)
    return df_out.sort_values('entry_time').reset_index(drop=True)

@njit(nogil=True)
def fast_portfolio_backtest_numba(
    entry_times, exit_times, entry_prices, exit_prices, atrs, directions, probs,
    initial_capital=5000.0, max_concurrent=2, leverage=10.0, max_notional=50000.0,
    fee_rate=0.0009, base_risk=45.0, max_house_risk=260.0, min_defense_risk=15.0,
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
        streak_bonus = min(consecutive_wins * 60.0, 140.0)
        
        if realized_pnl > 0.0:
            target_risk = min(base_risk + 0.80 * realized_pnl + streak_bonus, max_house_risk)
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
            
        stop_dist = max(2.2 * atrs[i], entry_prices[i] * 0.0065)
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

def run_s1_walkforward():
    feature_cols = [
        'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
        'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
        'long_liq_zscore', 'short_liq_zscore', 'liq_imbalance', 'liq_vol_ratio',
        'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'btc_trend'
    ]
    
    df_all = load_s1_trades(feature_cols)
    if df_all.empty: return
    windows = get_oos_windows(num_windows=20)
    
    print("\n" + "="*95)
    print(f"{'Win':<4} {'Test Period':<24} {'Strategy':<18} {'p*':<5} {'Trades':<7} {'Win Rate':<9} {'ROI (%)':<9} {'Max DD (%)':<11} {'Status'}")
    print("="*95)
    
    pass_count = 0
    total_count = len(windows)
    
    for w in windows:
        w_idx = w['idx']
        t_start = w['test_start']
        t_end = w['test_end']
        tr_start = w['train_start']
        tr_end_purged = w['train_end'] - pd.Timedelta(hours=3)
        
        df_is = df_all[(df_all['entry_time'] >= tr_start) & (df_all['exit_time'] < tr_end_purged)].copy()
        if len(df_is) < 30: continue
            
        fcols = [c for c in feature_cols if c in df_is.columns]
        X_is = df_is[fcols].fillna(0.0)
        y_is = df_is['label'].to_numpy(dtype=np.int32)
        p = int(y_is.sum())
        sw = max(0.1, float((len(y_is) - p) / p)) if p > 0 else 1.0
        
        model = lgb.LGBMClassifier(
            max_depth=4, learning_rate=0.03, n_estimators=60, scale_pos_weight=sw,
            random_state=42, verbose=-1, min_child_samples=15, n_jobs=2
        )
        model.fit(X_is, y_is)
        
        df_oos_win = df_all[(df_all['entry_time'] >= t_start) & (df_all['entry_time'] < t_end)].copy()
        if len(df_oos_win) == 0: continue
            
        X_oos = df_oos_win[fcols].fillna(0.0)
        probs_oos = model.predict_proba(X_oos)[:, 1].astype(np.float64)
        
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
        
        print(f"W{w_idx:02d} {t_start.strftime('%Y-%m-%d')} to {t_end.strftime('%Y-%m-%d')}  {'S1_Cascade':<18} {eff_th:.2f}   {tr:3d}     {wr*100:5.1f}%    {roi*100:+6.2f}%     {dd*100:4.2f}%     {verdict}")
        
    print("="*95)
    print(f"S1 LIQUIDATION CASCADE RESULT: {pass_count}/{total_count} PASSED ({pass_count/total_count*100:.1f}%)")
    print("="*95)

if __name__ == "__main__":
    run_s1_walkforward()
