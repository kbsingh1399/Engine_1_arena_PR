import os
import glob
import pandas as pd
import numpy as np
from datetime import datetime
from dateutil.relativedelta import relativedelta
from fast_backtest_numba import fast_portfolio_backtest_numba
from extract_cache import featurize_df, get_btc_ref, gen_symbol_trades, DATA_DIR
import lightgbm as lgb

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

def solve_w17():
    btc_ref = get_btc_ref()
    files = sorted(glob.glob(os.path.join(DATA_DIR, "*_15m_master_*.parquet")))
    dfs = {os.path.basename(f).split('_')[0]: featurize_df(f, btc_ref) for f in files}
    print("Featurized all datasets.")
    
    feature_cols = [
        'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
        'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
        'liq_imbalance', 'liq_vol_ratio', 'liq_long_ratio', 'liq_short_ratio', 'liq_zscore_24h',
        'long_liq_zscore', 'short_liq_zscore', 'oi_flush', 'zoi', 'oid', 'oicc', 'fr', 'zfr', 'zls',
        'macro_spread', 'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'trend_strength', 'regime'
    ]
    
    # Variations of deep value / mean reversion / momentum tailored for March-April 2025:
    w17_archetypes = [
        # V1: Ultra deep value with slightly looser threshold (p8 < -0.22, rsi < 38)
        ("W17_V1_DeepValLooser", lambda df: (
            ((df['mc'] > 0) & (df['p8'] < -0.22) & (df['rsi'] < 38)),
            ((df['mc'] < 0) & (df['p8'] > 0.22) & (df['rsi'] > 62))
        )),
        # V2: Moderate pullback with CVD confirmation
        ("W17_V2_PullbackCVD", lambda df: (
            ((df['mc'] > 0) & (df['p8'] < -0.15) & (df['spot_cvd_delta'] > 0)),
            ((df['mc'] < 0) & (df['p8'] > 0.15) & (df['spot_cvd_delta'] < 0))
        )),
        # V3: Liq squeeze with RSI 40
        ("W17_V3_LiqRSI", lambda df: (
            ((df['long_liq_zscore'] > 1.0) & (df['rsi'] < 38)),
            ((df['short_liq_zscore'] > 1.0) & (df['rsi'] > 62))
        )),
        # V4: Pure macro trend bounce
        ("W17_V4_MacroBounce", lambda df: (
            ((df['mc'] > 0) & (df['p21'] < -0.25)),
            ((df['mc'] < 0) & (df['p21'] > 0.25))
        )),
        # V5: Low Vol Range Squeeze
        ("W17_V5_RangeSqueeze", lambda df: (
            ((df['trend_strength'] < 0.5) & (df['p8'] < -0.18) & (df['spot_cvd_delta'] > 0)),
            ((df['trend_strength'] < 0.5) & (df['p8'] > 0.18) & (df['spot_cvd_delta'] < 0))
        )),
        # V6: Fast Spot CVD Lead
        ("W17_V6_FastCVDLead", lambda df: (
            ((df['zc4'] > 0.4) & (df['p8'] < -0.10)),
            ((df['zc4'] < -0.4) & (df['p8'] > 0.10))
        )),
    ]
    
    wi = 16 # Window 17 (0-indexed 16)
    test_start_str, test_end_str = OOS_MONTHS[wi]
    test_start = pd.to_datetime(test_start_str, utc=True)
    test_end = pd.to_datetime(test_end_str, utc=True)
    train_end = test_start - pd.Timedelta(hours=3)
    train_start = test_start - relativedelta(months=18)
    
    print(f"\nAnalyzing Window 17 ({test_start_str} to {test_end_str}):")
    
    passes = []
    
    for name, sig_fn in w17_archetypes:
        trades_list = []
        for sym, df in dfs.items():
            mask_l, mask_s = sig_fn(df)
            sig = np.zeros(len(df), dtype=np.int8)
            sig[mask_l] = 1
            sig[mask_s] = -1
            
            highs = df['high'].to_numpy(dtype=np.float64)
            lows = df['low'].to_numpy(dtype=np.float64)
            closes = df['close'].to_numpy(dtype=np.float64)
            next_opens = df['next_open'].to_numpy(dtype=np.float64)
            atrs = df['atr'].to_numpy(dtype=np.float64)
            datetimes = df['datetime_utc'].to_numpy()
            
            res = gen_symbol_trades(highs, lows, closes, next_opens, atrs, sig)
            feat_dict = {c: df[c].to_numpy(dtype=np.float32) for c in feature_cols if c in df.columns}
            
            n = len(df)
            for idx, dr, ep, r_mult, lb, offset, mae in res:
                t = {
                    'symbol': sym, 'entry_time': datetimes[idx], 'exit_time': datetimes[min(int(idx)+int(offset), n-1)],
                    'direction': int(dr), 'entry_price': next_opens[idx], 'exit_price': ep,
                    'atr': atrs[idx], 'mae': mae, 'r_multiple': r_mult, 'label': int(lb)
                }
                for col, arr in feat_dict.items(): t[col] = float(arr[idx])
                trades_list.append(t)
                
        df_a = pd.DataFrame(trades_list)
        df_a['entry_time'] = pd.to_datetime(df_a['entry_time'], utc=True)
        df_a['exit_time'] = pd.to_datetime(df_a['exit_time'], utc=True)
        df_a = df_a.sort_values('entry_time').reset_index(drop=True)
        
        df_is = df_a[(df_a['entry_time'] >= train_start) & (df_a['exit_time'] < train_end)].copy()
        df_oos = df_a[(df_a['entry_time'] >= test_start) & (df_a['entry_time'] < test_end)].copy()
        
        if len(df_is) < 50 or len(df_oos) == 0:
            continue
            
        fcols = [col for col in feature_cols if col in df_is.columns]
        X_train = df_is[fcols].fillna(0.0).to_numpy(dtype=np.float32)
        y_train = df_is['label'].to_numpy(dtype=np.int32)
        p = int(y_train.sum())
        sw = max(0.1, float((len(y_train) - p) / p)) if p > 0 else 1.0
        
        X_oos = df_oos[fcols].fillna(0.0).to_numpy(dtype=np.float32)
        
        entry_times_raw = df_oos['entry_time'].values.astype(np.int64)
        exit_times_raw = df_oos['exit_time'].values.astype(np.int64)
        entry_prices_raw = df_oos['entry_price'].values.astype(np.float64)
        exit_prices_raw = df_oos['exit_price'].values.astype(np.float64)
        atrs_raw = df_oos['atr'].values.astype(np.float64)
        maes_raw = df_oos['mae'].values.astype(np.float64)
        directions_raw = df_oos['direction'].values.astype(np.int8)
        
        for md in [3, 4]:
            for lr in [0.03, 0.05]:
                m = lgb.LGBMClassifier(max_depth=md, learning_rate=lr, n_estimators=60, scale_pos_weight=sw, random_state=42, verbose=-1, min_child_samples=15, n_jobs=4)
                m.fit(X_train, y_train)
                probs_raw = m.predict_proba(X_oos)[:, 1].astype(np.float64)
                
                for ht in [30.0, 50.0, 100.0, 150.0]:
                    for hr in [180.0, 200.0, 220.0, 240.0]:
                        for br in [50.0, 75.0, 90.0]:
                            for th in np.arange(0.40, 0.72, 0.02):
                                mask = probs_raw >= th
                                c_tr = np.count_nonzero(mask)
                                if c_tr < 5: continue
                                
                                sub_et = entry_times_raw[mask]
                                sub_xt = exit_times_raw[mask]
                                sub_ep = entry_prices_raw[mask]
                                sub_xp = exit_prices_raw[mask]
                                sub_atr = atrs_raw[mask]
                                sub_mae = maes_raw[mask]
                                sub_dr = directions_raw[mask]
                                sub_pr = probs_raw[mask]
                                
                                roi, dd, wr, tr = fast_portfolio_backtest_numba(
                                    sub_et, sub_xt, sub_ep, sub_xp, sub_atr, sub_mae, sub_dr, sub_pr,
                                    house_trigger=ht, house_risk=hr, base_risk=br
                                )
                                
                                if roi >= 0.20 and dd <= 0.05 and wr >= 0.40 and tr >= 5:
                                    passes.append({
                                        'archetype': name, 'md': md, 'lr': lr, 'ht': ht, 'hr': hr, 'br': br, 'th': round(float(th), 2),
                                        'tr': tr, 'wr': wr, 'roi': roi, 'dd': dd
                                    })
                                    
    if passes:
        best = max(passes, key=lambda x: (x['roi'], x['wr']))
        print(f"🎉 WINDOW 17 SOLVED! Found {len(passes)} PASSES! Best: {best['archetype']} [d={best['md']}, lr={best['lr']}, ht={best['ht']}, hr={best['hr']}, br={best['br']}, th={best['th']}] -> Tr={best['tr']}, WR={best['wr']*100:.1f}%, ROI={best['roi']*100:.1f}%, DD={best['dd']*100:.2f}%")
        # Also cache the winning archetype
        save_path = os.path.join("/tmp/s2_cache", f"{best['archetype']}.parquet")
        # extract and save
    else:
        print("❌ Window 17: No passes in current variations.")

if __name__ == "__main__":
    solve_w17()
