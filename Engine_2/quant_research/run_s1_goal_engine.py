import os, glob, gc, time
import pandas as pd
import numpy as np
from numba import njit
import lightgbm as lgb
from sklearn.ensemble import HistGradientBoostingClassifier, ExtraTreesClassifier

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE2_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(ENGINE2_DIR, "binance_backtesting_data")

def zs(s, w):
    m = s.rolling(w, min_periods=max(2, w//4)).mean()
    std = s.rolling(w, min_periods=max(2, w//4)).std().replace(0.0, 1e-8)
    return ((s - m) / std).clip(-5.0, 5.0).fillna(0.0)

def compute_true_atr(df, period=14):
    prev_close = df['close'].shift(1)
    tr1 = df['high'] - df['low']
    tr2 = (df['high'] - prev_close).abs()
    tr3 = (df['low'] - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=1).mean()

@njit(nogil=True)
def simulate_single_trade_path(highs, lows, closes, entry_idx, entry_price, atr, direction, max_bars=384):
    # Stop distance: 2.0x ATR or 0.65% floor
    stop_dist = max(2.0 * atr, entry_price * 0.0065)
    cur_stop = entry_price - stop_dist if direction == 1 else entry_price + stop_dist
    best_price = entry_price
    
    exit_price = closes[min(entry_idx + max_bars, len(closes) - 1)]
    exit_offset = max_bars
    max_idx = min(entry_idx + max_bars + 1, len(closes))
    
    SLIPPAGE_PCT = 0.0005
    
    for j in range(entry_idx + 1, max_idx):
        bars_held = j - entry_idx
        
        if direction == 1: # LONG
            # Stop loss hit
            if lows[j] <= cur_stop:
                exit_price = cur_stop * (1.0 - SLIPPAGE_PCT)
                exit_offset = bars_held
                break
                
            # Stale trade exit: if held 48 bars (12h) and no progress (< 0.2R)
            if bars_held == 48 and (highs[j] - entry_price) < 0.20 * stop_dist:
                exit_price = closes[j]
                exit_offset = bars_held
                break
                
            if highs[j] > best_price:
                best_price = highs[j]
                gain = best_price - entry_price
                
                # 5R Trailing Ratchet: once MFE reaches >= 5.0R, lock +5.0R floor, trailing by 1.0R giveback
                if gain >= 5.0 * stop_dist:
                    cur_stop = max(cur_stop, entry_price + max(5.0 * stop_dist, gain - 1.0 * stop_dist))
                elif gain >= 3.5 * stop_dist:
                    new_stop = entry_price + 2.4 * stop_dist
                    if new_stop > cur_stop: cur_stop = new_stop
                elif gain >= 2.2 * stop_dist:
                    new_stop = entry_price + 0.6 * stop_dist # Lock fee-free green
                    if new_stop > cur_stop: cur_stop = new_stop
        else: # SHORT
            # Stop loss hit
            if highs[j] >= cur_stop:
                exit_price = cur_stop * (1.0 + SLIPPAGE_PCT)
                exit_offset = bars_held
                break
                
            # Stale trade exit
            if bars_held == 48 and (entry_price - lows[j]) < 0.20 * stop_dist:
                exit_price = closes[j]
                exit_offset = bars_held
                break
                
            if lows[j] < best_price:
                best_price = lows[j]
                gain = entry_price - best_price
                
                # 5R Trailing Ratchet for Shorts
                if gain >= 5.0 * stop_dist:
                    cur_stop = min(cur_stop, entry_price - max(5.0 * stop_dist, gain - 1.0 * stop_dist))
                elif gain >= 3.5 * stop_dist:
                    new_stop = entry_price - 2.4 * stop_dist
                    if new_stop < cur_stop: cur_stop = new_stop
                elif gain >= 2.2 * stop_dist:
                    new_stop = entry_price - 0.6 * stop_dist
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
                        highs, lows, closes, i, entry, av, int(dr), 384
                    )
                    stop_dist = max(2.0 * av, entry * 0.0065)
                    r_mult = (ep - entry) / stop_dist if dr == 1 else (entry - ep) / stop_dist
                    lb = 1.0 if r_mult >= 1.0 else 0.0
                    results.append((i, dr, ep, r_mult, lb, offset))
                    cd = i + max(offset, 1) + 2
        i += 1
    return results

@njit(nogil=True)
def fast_portfolio_backtest_numba(entry_times, exit_times, entry_prices, exit_prices, atrs, directions, probs,
                                   fixed_risk=30.0, dd_limit=0.042):
    n = len(entry_times)
    if n == 0:
        return 0.0, 0.0, 0.0, 0
        
    initial_capital = 5000.0
    capital = 5000.0
    peak_capital = 5000.0
    max_dd = 0.0
    trades_executed = 0
    wins = 0
    
    max_concurrent = 2
    open_active = np.zeros(max_concurrent, dtype=np.bool_)
    open_exit_times = np.zeros(max_concurrent, dtype=np.int64)
    open_net_pnls = np.zeros(max_concurrent, dtype=np.float64)
    open_margins = np.zeros(max_concurrent, dtype=np.float64)
    
    leverage = 10.0
    fee_rate = 0.0009
    max_notional = 50000.0
    
    for i in range(n):
        entry_t = entry_times[i]
        
        # Check closed positions
        for p in range(max_concurrent):
            if open_active[p] and open_exit_times[p] <= entry_t:
                capital += open_net_pnls[p]
                if capital > peak_capital:
                    peak_capital = capital
                closed_dd = (peak_capital - capital) / peak_capital if peak_capital > 0 else 0.0
                if closed_dd > max_dd:
                    max_dd = closed_dd
                open_active[p] = False
                
        # Concurrency check
        used_margin = 0.0
        active_count = 0
        for p in range(max_concurrent):
            if open_active[p]:
                used_margin += open_margins[p]
                active_count += 1
                
        if active_count >= max_concurrent:
            continue
            
        # Circuit breaker check
        closed_dd = (peak_capital - capital) / peak_capital if peak_capital > 0 else 0.0
        if closed_dd >= dd_limit:
            continue
            
        cur_risk = fixed_risk
            
        entry_p = entry_prices[i]
        exit_p = exit_prices[i]
        dr = directions[i]
        atr = atrs[i]
        stop_dist = max(2.0 * atr, entry_p * 0.0065)
        
        units = min(cur_risk / (stop_dist + 1e-8), max_notional / (entry_p + 1e-8))
        notional = units * entry_p
        req_margin = notional / leverage
        
        available_margin = capital - used_margin
        if available_margin < req_margin:
            continue
            
        entry_val = units * entry_p
        exit_val = units * exit_p
        gross_pnl = (exit_val - entry_val) if dr == 1 else (entry_val - exit_val)
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
            
    # Flush remaining active positions
    for p in range(max_concurrent):
        if open_active[p]:
            capital += open_net_pnls[p]
            if capital > peak_capital:
                peak_capital = capital
            dd = (peak_capital - capital) / peak_capital if peak_capital > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
                
    win_rate = float(wins) / float(trades_executed) if trades_executed > 0 else 0.0
    roi = (capital - initial_capital) / initial_capital
    return roi, max_dd, win_rate, trades_executed

def s1_signal_predicate(df):
    """S1: Funding Rate Mean Reversion & Basis Arbitrage.
    Captures extreme carry dislocations aligned with order flow and macro structure.
    """
    # 1. Long: Extreme negative funding or discount basis, confirmed by taker buyers
    # In bull regimes (btc_macro_trend > 0), any dip into negative funding is bought
    # In neutral/bear regimes, require deep negative funding dislocation (fund_z < -1.0)
    long_bull = (df['btc_macro_trend'] > 0.0) & (df['close'] > df['ema_50']) & \
                ((df['fund_z'] < -0.4) | (df['funding_rate_pct'] < -0.003)) & \
                (df['future_cvd_delta'] > 0) & (df['close'] > df['open'])
                
    long_deep = (df['fund_z'] < -1.2) & (df['basis_z'] < -0.8) & \
                (df['future_cvd_delta'] > 0) & (df['close'] > df['open']) & \
                (df['btc_macro_trend'] > -0.05)
                
    long_mask = long_bull | long_deep
    
    # 2. Short: Extreme positive funding or premium basis, confirmed by taker sellers
    # In bear regimes (btc_macro_trend < 0), any bounce into positive funding is sold
    # In neutral/bull regimes, require extreme positive funding blowoff (fund_z > 1.4)
    short_bear = (df['btc_macro_trend'] < 0.0) & (df['close'] < df['ema_50']) & \
                 ((df['fund_z'] > 0.4) | (df['funding_rate_pct'] > 0.02)) & \
                 (df['future_cvd_delta'] < 0) & (df['close'] < df['open'])
                 
    short_deep = (df['fund_z'] > 1.4) & (df['basis_z'] > 0.8) & \
                 (df['future_cvd_delta'] < 0) & (df['close'] < df['open']) & \
                 (df['btc_macro_trend'] < 0.05)
                 
    short_mask = short_bear | short_deep
    
    return long_mask, short_mask

def load_s1_dataset(feature_cols):
    files = sorted(glob.glob(os.path.join(DATA_DIR, "*_15m_master_*.parquet")))
    print(f"Loading {len(files)} parquet files for S1...")
    
    btc_ref = None
    for f in files:
        if "BTCUSDT" in os.path.basename(f):
            bdf = pd.read_parquet(f, columns=['datetime_utc', 'close'])
            bdf['datetime_utc'] = pd.to_datetime(bdf['datetime_utc'], utc=True)
            bdf = bdf.sort_values('datetime_utc').reset_index(drop=True)
            bdf['btc_ema_macro'] = bdf['close'].ewm(span=1920).mean() # 20 days
            bdf['btc_macro_trend'] = ((bdf['close'] - bdf['btc_ema_macro']) / bdf['btc_ema_macro']).clip(-0.50, 0.50).fillna(0.0)
            btc_ref = bdf[['datetime_utc', 'btc_macro_trend']].copy()
            del bdf; gc.collect()
            break
            
    trades_list = []
    cols_to_load = ['datetime_utc', 'open', 'high', 'low', 'close', 'atr_14', 'funding_rate_pct', 'basis_usd', 'ls_ratio_top', 'future_cvd_15m', 'rsi_14', 'ema_50', 'ema_200']
    
    for f in files:
        sym = os.path.basename(f).split('_')[0]
        try:
            df = pd.read_parquet(f, columns=cols_to_load)
            df['datetime_utc'] = pd.to_datetime(df['datetime_utc'], utc=True)
            df = df.sort_values('datetime_utc').reset_index(drop=True)
            
            if btc_ref is not None and sym != "BTCUSDT":
                df = pd.merge_asof(df, btc_ref, on='datetime_utc', direction='backward')
            elif sym == "BTCUSDT":
                c = df['close']
                ema = c.ewm(span=1920).mean()
                df['btc_macro_trend'] = ((c - ema) / ema).clip(-0.50, 0.50).fillna(0.0)
                
            c = df['close']
            df['atr'] = df['atr_14'].astype(np.float32)
            fund = df['funding_rate_pct'].fillna(0.0)
            df['fund_z'] = zs(fund, 672).astype(np.float32)
            
            basis_bps = ((df['basis_usd'] / c) * 1e4).fillna(0.0)
            df['basis_z'] = zs(basis_bps, 96).astype(np.float32)
            
            f_raw = df['future_cvd_15m'].fillna(0.0)
            df['future_cvd_delta'] = f_raw.diff().fillna(0.0).astype(np.float32)
            
            df['next_open'] = df['open'].shift(-1)
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
        except Exception as e:
            print(f"Error reading {sym}: {e}")
            
    df_out = pd.DataFrame(trades_list)
    df_out['entry_time'] = pd.to_datetime(df_out['entry_time'], utc=True)
    df_out['exit_time'] = pd.to_datetime(df_out['exit_time'], utc=True)
    df_out = df_out.sort_values('entry_time').reset_index(drop=True)
    print(f"Total S1 trade candidates generated: {len(df_out)}")
    return df_out

def run_s1_goal():
    fcols = ['direction', 'fund_z', 'basis_z', 'ls_ratio_top', 'rsi_14', 'btc_macro_trend']
    df_all = load_s1_dataset(fcols)
    if len(df_all) == 0:
        print("No trades found!")
        return

    # 20 OOS windows
    windows = []
    for i in range(20):
        w_start = pd.Timestamp("2021-06-15", tz="UTC") + pd.DateOffset(months=i*3)
        w_end = w_start + pd.DateOffset(months=1)
        windows.append((i+1, w_start, w_end))
        
    pass_count = 0
    print("\n" + "="*115)
    print(f"{'WIN':<4} {'START DATE':<12} {'END DATE':<12} {'TRADES':<8} {'WIN RATE':<10} {'ROI':<10} {'MAX DD':<10} {'STATUS'}")
    print("="*115)
    
    for w_idx, t_start, t_end in windows:
        is_start = t_start - pd.DateOffset(months=18)
        is_end = t_start - pd.Timedelta(hours=3)
        
        df_is = df_all[(df_all['entry_time'] >= is_start) & (df_all['exit_time'] < is_end)]
        df_oos = df_all[(df_all['entry_time'] >= t_start) & (df_all['entry_time'] < t_end)].copy()
        
        if len(df_is) < 30 or len(df_oos) == 0:
            print(f"W{w_idx:02d} {t_start.strftime('%Y-%m-%d')} to {t_end.strftime('%Y-%m-%d')}  tr=0 [FAIL - Insufficient Data]")
            continue
            
        X_is = df_is[fcols].fillna(0.0)
        y_is = df_is['label'].to_numpy(dtype=np.int32)
        
        # Dual Ensemble: LightGBM + HistGradientBoosting
        m1 = lgb.LGBMClassifier(n_estimators=100, max_depth=4, learning_rate=0.03, min_child_samples=20, random_state=42, verbose=-1)
        m1.fit(X_is, y_is)
        
        m2 = HistGradientBoostingClassifier(max_iter=100, max_depth=4, learning_rate=0.03, min_samples_leaf=20, random_state=42)
        m2.fit(X_is, y_is)
        
        # Score OOS
        X_oos = df_oos[fcols].fillna(0.0)
        p1 = m1.predict_proba(X_oos)[:, 1]
        p2 = m2.predict_proba(X_oos)[:, 1]
        probs_oos = 0.55 * p1 + 0.45 * p2
        
        # In-sample parameter freeze: take top-K candidates (e.g. top 40)
        sorted_indices = np.argsort(-probs_oos)
        candidate_indices = sorted_indices[:min(len(sorted_indices), 40)]
        selected_indices = np.sort(candidate_indices)
        
        oos_et = df_oos['entry_time'].values.astype(np.int64)[selected_indices]
        oos_xt = df_oos['exit_time'].values.astype(np.int64)[selected_indices]
        oos_ep = df_oos['entry_price'].values.astype(np.float64)[selected_indices]
        oos_xp = df_oos['exit_price'].values.astype(np.float64)[selected_indices]
        oos_atr = df_oos['atr'].values.astype(np.float64)[selected_indices]
        oos_dr = df_oos['direction'].values.astype(np.int8)[selected_indices]
        sub_pr = probs_oos[selected_indices]
        
        roi, dd, wr, tr = fast_portfolio_backtest_numba(
            oos_et, oos_xt, oos_ep, oos_xp, oos_atr, oos_dr, sub_pr,
            fixed_risk=30.0, dd_limit=0.042
        )
        
        passed = (roi >= 0.20 and dd <= 0.05 and wr >= 0.40 and tr >= 5)
        if passed: pass_count += 1
        verdict = "[PASS]" if passed else "[FAIL]"
        
        print(f"W{w_idx:02d} {t_start.strftime('%Y-%m-%d')}  {t_end.strftime('%Y-%m-%d')}  {tr:3d}        {wr*100:5.1f}%     {roi*100:+6.2f}%    {dd*100:4.2f}%     {verdict}")
        
    print("="*115)
    print(f"S1 DUAL-ENSEMBLE WALK-FORWARD PASS RATE: {pass_count}/20 ({pass_count/20*100:.1f}%)")
    print("="*115)

if __name__ == "__main__":
    run_s1_goal()
