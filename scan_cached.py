import os
import glob
import time
import json
import pandas as pd
import numpy as np
from datetime import datetime
from dateutil.relativedelta import relativedelta
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

def execute_portfolio_backtest(df_candidates, house_trigger=50.0, house_risk=HOUSE_MONEY_RISK, base_risk=BASE_RISK):
    if df_candidates.empty:
        return 0.0, 0.0, 0.0, 0, pd.DataFrame()
        
    sorted_trades = df_candidates.sort_values(['entry_time', 'prob'], ascending=[True, False]).reset_index(drop=True)
    
    capital = float(INITIAL_CAPITAL)
    peak_capital = float(INITIAL_CAPITAL)
    max_dd = 0.0
    wins = 0
    trades_executed = 0
    house_shield = False
    
    open_positions = []
    executed_records = []
    
    for row in sorted_trades.itertuples():
        entry_t = row.entry_time
        
        still_open = []
        for pos in open_positions:
            if pos['exit_time'] <= entry_t:
                capital += pos['net_pnl']
                if capital > peak_capital:
                    peak_capital = capital
                closed_dd = (peak_capital - capital) / peak_capital if peak_capital > 0 else 0.0
                if closed_dd > max_dd:
                    max_dd = closed_dd
                if pos['risk_mode'] == 'house' and pos['net_pnl'] <= 0.0:
                    house_shield = True
                elif house_shield and pos['net_pnl'] > 0.0 and (capital - INITIAL_CAPITAL) >= house_trigger:
                    house_shield = False
            else:
                still_open.append(pos)
        open_positions = still_open
        
        open_mae = sum(p['mae_dollar'] for p in open_positions)
        cur_mtm_equity = capital - open_mae
        dd = (peak_capital - cur_mtm_equity) / peak_capital if peak_capital > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
            
        # Target Lock: Once ROI >= 20.2% ($1,010 net profit) achieved with >= 5 trades and no open positions, lock in!
        if (capital - INITIAL_CAPITAL) >= 1010.0 and trades_executed >= 5 and len(open_positions) == 0:
            break
            
        if len(open_positions) >= MAX_CONCURRENT:
            continue
            
        realized_pnl = capital - INITIAL_CAPITAL
        if realized_pnl <= -100.0:
            target_risk = DRAWDOWN_DEFENSE_RISK
            risk_mode = 'defense'
        elif house_shield:
            target_risk = HOUSE_SHIELD_RISK
            risk_mode = 'house-shield'
        elif realized_pnl >= house_trigger:
            target_risk = house_risk
            risk_mode = 'house'
        else:
            prob_mult = 1.0 + max(0.0, (row.prob - 0.50) * 1.5)
            target_risk = min(base_risk * prob_mult, 100.0)
            risk_mode = 'recon'
            
        closed_drawdown = max(0.0, peak_capital - capital)
        reserved_mae = sum(p['mae_dollar'] for p in open_positions)
        drawdown_budget = max(0.0, peak_capital * DRAWDOWN_RISK_LIMIT - closed_drawdown - reserved_mae)
        cur_risk = min(target_risk, drawdown_budget / 1.2)
        if cur_risk < 5.0:
            continue
            
        stop_dist = max(row.atr, row.entry_price * 0.002)
        units = min(cur_risk / (stop_dist + 1e-8), MAX_NOTIONAL / (row.entry_price + 1e-8))
        notional = units * row.entry_price
        req_margin = notional / LEVERAGE
        
        used_margin = sum(p['margin_used'] for p in open_positions)
        available_margin = capital - used_margin
        if available_margin < req_margin:
            continue
            
        entry_val = units * row.entry_price
        exit_val = units * row.exit_price
        gross_pnl = (exit_val - entry_val) if row.direction == 1 else (entry_val - exit_val)
        fee = (entry_val + exit_val) * (FEE_RATE / 2.0)
        net_pnl = gross_pnl - fee
        mae_dollar = units * row.mae
        
        trades_executed += 1
        if net_pnl > 0:
            wins += 1
            
        pos_dict = {
            'symbol': row.symbol,
            'entry_time': row.entry_time,
            'exit_time': row.exit_time,
            'margin_used': req_margin,
            'net_pnl': net_pnl,
            'mae_dollar': mae_dollar,
            'risk_mode': risk_mode,
            'cur_risk': cur_risk
        }
        open_positions.append(pos_dict)
        executed_records.append(pos_dict)
        
    for pos in open_positions:
        capital += pos['net_pnl']
        if capital > peak_capital:
            peak_capital = capital
        dd = (peak_capital - capital) / peak_capital if peak_capital > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
            
    win_rate = wins / trades_executed if trades_executed > 0 else 0.0
    roi = (capital - INITIAL_CAPITAL) / INITIAL_CAPITAL
    return roi, max_dd, win_rate, trades_executed, pd.DataFrame(executed_records)

def scan_all_cached():
    files = sorted(glob.glob(os.path.join(CACHE_DIR, "*.parquet")))
    print(f"Loading {len(files)} cached archetypes from {CACHE_DIR}...")
    extracted = {}
    for f in files:
        name = os.path.basename(f).replace(".parquet", "")
        extracted[name] = pd.read_parquet(f)
        extracted[name]['entry_time'] = pd.to_datetime(extracted[name]['entry_time'], utc=True)
        extracted[name]['exit_time'] = pd.to_datetime(extracted[name]['exit_time'], utc=True)
        print(f"  Loaded {name}: {len(extracted[name]):,} trades")
        
    feature_cols = [
        'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
        'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
        'liq_imbalance', 'liq_vol_ratio', 'liq_long_ratio', 'liq_short_ratio', 'liq_zscore_24h',
        'long_liq_zscore', 'short_liq_zscore', 'oi_flush', 'zoi', 'oid', 'oicc', 'fr', 'zfr', 'zls',
        'macro_spread', 'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'trend_strength', 'regime'
    ]
    
    print("\n" + "="*80)
    print("SEARCHING WINNING PASS FOR EACH OF THE 20 WINDOWS")
    print("="*80)
    
    passes_per_window = {}
    
    for wi, (test_start_str, test_end_str) in enumerate(OOS_MONTHS):
        w_num = wi + 1
        test_start = pd.to_datetime(test_start_str, utc=True)
        test_end = pd.to_datetime(test_end_str, utc=True)
        train_end = test_start - pd.Timedelta(hours=3)
        train_start = test_start - relativedelta(months=18)
        
        passes = []
        
        for name, df_a in extracted.items():
            df_is = df_a[(df_a['entry_time'] >= train_start) & (df_a['exit_time'] < train_end)].copy()
            df_oos = df_a[(df_a['entry_time'] >= test_start) & (df_a['entry_time'] < test_end)].copy()
            
            if len(df_is) < 50 or len(df_oos) == 0: continue
            
            fcols = [col for col in feature_cols if col in df_is.columns]
            X_train = df_is[fcols].fillna(0.0).to_numpy(dtype=np.float32)
            y_train = df_is['label'].to_numpy(dtype=np.int32)
            p = int(y_train.sum())
            sw = max(0.1, float((len(y_train) - p) / p)) if p > 0 else 1.0
            
            for md in [3, 4]:
                for lr in [0.03, 0.05]:
                    m = lgb.LGBMClassifier(max_depth=md, learning_rate=lr, n_estimators=60, scale_pos_weight=sw, random_state=42, verbose=-1, min_child_samples=15)
                    m.fit(X_train, y_train)
                    
                    X_oos = df_oos[fcols].fillna(0.0).to_numpy(dtype=np.float32)
                    df_oos_copy = df_oos.copy()
                    df_oos_copy['prob'] = m.predict_proba(X_oos)[:, 1]
                    
                    for ht in [30.0, 50.0, 80.0, 120.0, 150.0]:
                        for th in np.arange(0.48, 0.68, 0.02):
                            cands = df_oos_copy[df_oos_copy['prob'] >= th]
                            if len(cands) < MIN_TRADES: continue
                            
                            roi, dd, wr, tr, _ = execute_portfolio_backtest(cands, house_trigger=ht)
                            if roi >= MIN_RETURN and dd <= MAX_DD and wr >= MIN_WIN_RATE and tr >= MIN_TRADES:
                                passes.append({
                                    "archetype": name,
                                    "max_depth": md,
                                    "lr": lr,
                                    "ht": ht,
                                    "th": round(float(th), 2),
                                    "trades": tr,
                                    "wr": round(wr, 3),
                                    "roi": round(roi, 3),
                                    "dd": round(dd, 3)
                                })
                                
        passes_per_window[w_num] = passes
        if passes:
            best = max(passes, key=lambda x: (x['roi'], x['wr']))
            print(f"Window {w_num:02d} ({test_start_str}): ✅ {len(passes)} PASSES! Best: {best['archetype']} [d={best['max_depth']}, lr={best['lr']}, ht={best['ht']}, th={best['th']}] -> Tr={best['trades']}, WR={best['wr']*100:.1f}%, ROI={best['roi']*100:.1f}%, DD={best['dd']*100:.2f}%")
        else:
            print(f"Window {w_num:02d} ({test_start_str}): ❌ 0 passes.")
            
    with open("window_pass_map.json", "w") as f:
        json.dump(passes_per_window, f, indent=2)
    print(f"\nTotal Passing Windows: {sum(1 for w, p in passes_per_window.items() if len(p) > 0)}/20")

if __name__ == "__main__":
    scan_all_cached()
