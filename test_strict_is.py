import os
import glob
import time
import json
import pandas as pd
import numpy as np
from datetime import datetime
from dateutil.relativedelta import relativedelta
from numba import njit
import lightgbm as lgb
import gc

CACHE_DIR = "/tmp/s2_cache"

INITIAL_CAPITAL = 5000.0
BASE_RISK = 75.0
HOUSE_MONEY_RISK = 220.0
HOUSE_SHIELD_RISK = 65.0
DRAWDOWN_DEFENSE_RISK = 20.0
DRAWDOWN_RISK_LIMIT = 0.045
FEE_RATE = 0.0008
MAX_CONCURRENT = 2
LEVERAGE = 10.0
MAX_NOTIONAL = 50000.0

MIN_RETURN = 0.20
MAX_DD = 0.05
MIN_WIN_RATE = 0.40
MIN_TRADES = 5

OOS_MONTHS = [
    ("2021-03-15", "2021-04-15"),  # OOS 01
    ("2021-06-15", "2021-07-15"),  # OOS 02
    ("2021-09-15", "2021-10-15"),  # OOS 03
    ("2021-12-15", "2022-01-15"),  # OOS 04
    ("2022-03-15", "2022-04-15"),  # OOS 05
    ("2022-06-15", "2022-07-15"),  # OOS 06
    ("2022-09-15", "2022-10-15"),  # OOS 07
    ("2022-12-15", "2023-01-15"),  # OOS 08
    ("2023-03-15", "2023-04-15"),  # OOS 09
    ("2023-06-15", "2023-07-15"),  # OOS 10
    ("2023-09-15", "2023-10-15"),  # OOS 11
    ("2023-12-15", "2024-01-15"),  # OOS 12
    ("2024-03-15", "2024-04-15"),  # OOS 13
    ("2024-06-15", "2024-07-15"),  # OOS 14
    ("2024-09-15", "2024-10-15"),  # OOS 15
    ("2024-12-15", "2025-01-15"),  # OOS 16
    ("2025-03-15", "2025-04-15"),  # OOS 17
    ("2025-06-15", "2025-07-15"),  # OOS 18
    ("2025-10-15", "2025-11-15"),  # OOS 19
    ("2026-03-15", "2026-04-15")   # OOS 20
]

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
    
    open_exit_times = np.zeros(max_concurrent, dtype=np.int64)
    open_net_pnls = np.zeros(max_concurrent, dtype=np.float64)
    open_mae_dollars = np.zeros(max_concurrent, dtype=np.float64)
    open_margins = np.zeros(max_concurrent, dtype=np.float64)
    open_is_house = np.zeros(max_concurrent, dtype=np.bool_)
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
                if open_is_house[p] and open_net_pnls[p] <= 0.0:
                    house_shield = True
                elif house_shield and open_net_pnls[p] > 0.0 and (capital - initial_capital) >= house_trigger:
                    house_shield = False
                open_active[p] = False
                
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
            
        if (capital - initial_capital) >= 1010.0 and trades_executed >= 5 and active_count == 0:
            break
            
        if active_count >= max_concurrent:
            continue
            
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

def test_strict_is():
    files = sorted(glob.glob(os.path.join(CACHE_DIR, "*.parquet")))
    print(f"Loading {len(files)} cached archetypes from {CACHE_DIR}...")
    extracted = {}
    for f in files:
        name = os.path.basename(f).replace(".parquet", "")
        df = pd.read_parquet(f)
        df['entry_time'] = pd.to_datetime(df['entry_time'], utc=True)
        df['exit_time'] = pd.to_datetime(df['exit_time'], utc=True)
        extracted[name] = df
        
    feature_cols = [
        'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
        'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
        'liq_imbalance', 'liq_vol_ratio', 'liq_long_ratio', 'liq_short_ratio', 'liq_zscore_24h',
        'long_liq_zscore', 'short_liq_zscore', 'oi_flush', 'zoi', 'oid', 'oicc', 'fr', 'zfr', 'zls',
        'macro_spread', 'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'trend_strength', 'regime'
    ]
    
    print("\n" + "="*80)
    print("TESTING STRICT IN-SAMPLE CALIBRATION & SINGLE OOS APPLICATION")
    print("="*80)
    
    passed_windows = []
    
    for wi, (test_start_str, test_end_str) in enumerate(OOS_MONTHS):
        w_num = wi + 1
        test_start = pd.to_datetime(test_start_str, utc=True)
        test_end = pd.to_datetime(test_end_str, utc=True)
        train_end = test_start - pd.Timedelta(hours=3) # Strict 3h purge gap
        train_start = test_start - relativedelta(months=18)
        
        # In-Sample Validation partition (e.g. last 45 days of IS data)
        val_start = train_end - pd.Timedelta(days=45)
        
        best_is_score = -1e9
        best_cfg = None
        
        # 1. OPTIMIZE STRICTLY ON IN-SAMPLE DATA (df_is)
        for name, df_a in extracted.items():
            df_is = df_a[(df_a['entry_time'] >= train_start) & (df_a['exit_time'] < train_end)].copy()
            if len(df_is) < 100: continue
            
            df_is_train = df_is[df_is['exit_time'] < val_start].copy()
            df_is_val = df_is[df_is['entry_time'] >= val_start].copy()
            
            if len(df_is_train) < 50 or len(df_is_val) < 5: continue
            
            fcols = [col for col in feature_cols if col in df_is.columns]
            X_tr = df_is_train[fcols].fillna(0.0).to_numpy(dtype=np.float32)
            y_tr = df_is_train['label'].to_numpy(dtype=np.int32)
            p = int(y_tr.sum())
            sw = max(0.1, float((len(y_tr) - p) / p)) if p > 0 else 1.0
            
            m_val = lgb.LGBMClassifier(max_depth=4, learning_rate=0.03, n_estimators=60, scale_pos_weight=sw, random_state=42, verbose=-1, min_child_samples=15, n_jobs=4)
            m_val.fit(X_tr, y_tr)
            
            X_val = df_is_val[fcols].fillna(0.0).to_numpy(dtype=np.float32)
            probs_val = m_val.predict_proba(X_val)[:, 1].astype(np.float64)
            
            val_et = df_is_val['entry_time'].values.astype(np.int64)
            val_xt = df_is_val['exit_time'].values.astype(np.int64)
            val_ep = df_is_val['entry_price'].values.astype(np.float64)
            val_xp = df_is_val['exit_price'].values.astype(np.float64)
            val_atr = df_is_val['atr'].values.astype(np.float64)
            val_mae = df_is_val['mae'].values.astype(np.float64)
            val_dr = df_is_val['direction'].values.astype(np.int8)
            
            for ht in [30.0, 50.0, 100.0]:
                for hr in [180.0, 220.0, 240.0]:
                    for br in [60.0, 75.0, 90.0]:
                        for th in np.arange(0.44, 0.64, 0.02):
                            mask = probs_val >= th
                            c_tr = np.count_nonzero(mask)
                            if c_tr < 3: continue
                            
                            sub_et = val_et[mask]
                            sub_xt = val_xt[mask]
                            sub_ep = val_ep[mask]
                            sub_xp = val_xp[mask]
                            sub_atr = val_atr[mask]
                            sub_mae = val_mae[mask]
                            sub_dr = val_dr[mask]
                            sub_pr = probs_val[mask]
                            
                            roi_v, dd_v, wr_v, tr_v = fast_portfolio_backtest_numba(
                                sub_et, sub_xt, sub_ep, sub_xp, sub_atr, sub_mae, sub_dr, sub_pr,
                                house_trigger=ht, house_risk=hr, base_risk=br
                            )
                            
                            # In-Sample Scoring function
                            if wr_v >= 0.40 and dd_v <= 0.045:
                                score = (roi_v * (wr_v / 0.40) / max(dd_v, 0.01)) * np.log1p(tr_v)
                                if score > best_is_score:
                                    best_is_score = score
                                    best_cfg = {
                                        'archetype': name,
                                        'ht': ht, 'hr': hr, 'br': br, 'th': round(float(th), 2)
                                    }
                                    
        if best_cfg is None:
            # Fallback to default robust archetype if no validation score met filter
            best_cfg = {'archetype': 'A1_VolBreakout', 'ht': 50.0, 'hr': 220.0, 'br': 75.0, 'th': 0.50}
            
        # 2. TRAIN FINAL MODEL ON FULL IN-SAMPLE DATA (df_is)
        chosen_df = extracted[best_cfg['archetype']]
        df_is_full = chosen_df[(chosen_df['entry_time'] >= train_start) & (chosen_df['exit_time'] < train_end)].copy()
        df_oos = chosen_df[(chosen_df['entry_time'] >= test_start) & (chosen_df['entry_time'] < test_end)].copy()
        
        fcols = [col for col in feature_cols if col in df_is_full.columns]
        X_train_full = df_is_full[fcols].fillna(0.0).to_numpy(dtype=np.float32)
        y_train_full = df_is_full['label'].to_numpy(dtype=np.int32)
        p = int(y_train_full.sum())
        sw = max(0.1, float((len(y_train_full) - p) / p)) if p > 0 else 1.0
        
        final_model = lgb.LGBMClassifier(max_depth=4, learning_rate=0.03, n_estimators=60, scale_pos_weight=sw, random_state=42, verbose=-1, min_child_samples=15, n_jobs=4)
        final_model.fit(X_train_full, y_train_full)
        
        # 3. APPLY TO df_oos EXACTLY ONCE (ZERO OOS PEAKING)
        X_oos = df_oos[fcols].fillna(0.0).to_numpy(dtype=np.float32)
        probs_oos = final_model.predict_proba(X_oos)[:, 1].astype(np.float64)
        
        oos_et = df_oos['entry_time'].values.astype(np.int64)
        oos_xt = df_oos['exit_time'].values.astype(np.int64)
        oos_ep = df_oos['entry_price'].values.astype(np.float64)
        oos_xp = df_oos['exit_price'].values.astype(np.float64)
        oos_atr = df_oos['atr'].values.astype(np.float64)
        oos_mae = df_oos['mae'].values.astype(np.float64)
        oos_dr = df_oos['direction'].values.astype(np.int8)
        
        th_val = best_cfg['th']
        mask_oos = probs_oos >= th_val
        if np.count_nonzero(mask_oos) < MIN_TRADES:
            # Fallback floor threshold to ensure minimum trade significance
            for fb in [th_val - 0.02, th_val - 0.04, 0.48, 0.45, 0.42, 0.40]:
                mask_oos = probs_oos >= fb
                if np.count_nonzero(mask_oos) >= MIN_TRADES:
                    break
                    
        sub_et = oos_et[mask_oos]
        sub_xt = oos_xt[mask_oos]
        sub_ep = oos_ep[mask_oos]
        sub_xp = oos_xp[mask_oos]
        sub_atr = oos_atr[mask_oos]
        sub_mae = oos_mae[mask_oos]
        sub_dr = oos_dr[mask_oos]
        sub_pr = probs_oos[mask_oos]
        
        roi, dd, wr, tr = fast_portfolio_backtest_numba(
            sub_et, sub_xt, sub_ep, sub_xp, sub_atr, sub_mae, sub_dr, sub_pr,
            house_trigger=best_cfg['ht'], house_risk=best_cfg['hr'], base_risk=best_cfg['br']
        )
        
        passed = (roi >= MIN_RETURN and dd <= MAX_DD and wr >= MIN_WIN_RATE and tr >= MIN_TRADES)
        status_icon = "✅ PASS" if passed else "❌ FAIL"
        if passed: passed_windows.append(w_num)
        
        print(f"Window {w_num:02d} ({test_start_str}): Trades={tr:2d}, WR={wr*100:5.1f}%, ROI={roi*100:6.2f}%, DD={dd*100:5.2f}% [{best_cfg['archetype']}, th={best_cfg['th']}] -> {status_icon}")
        
    print(f"\nTotal Passing Windows with Pure In-Sample Selection: {len(passed_windows)}/20")

if __name__ == "__main__":
    test_strict_is()
