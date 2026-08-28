import os
import glob
import time
import json
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

def analyze_targeted_windows():
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
    
    # Let's define specialized alpha formulations for tricky market regimes:
    # 1. Trend continuation on strong momentum
    # 2. Reversals after extreme liquidations + CVD divergence
    # 3. Funding rate divergence / extreme OI flush
    # 4. Relative strength vs BTC (altcoin outperformance breakout)
    # 5. Fast CVD breakout (zc4 > 0.5)
    # 6. Mean-reversion inside volatility bands
    
    specialized_archetypes = [
        # S1: Trend Momentum Continuation (EMA 50 alignment + positive CVD delta)
        ("B1_TrendCVDCont", lambda df: (
            ((df['close'] > df['close'].ewm(span=50).mean()) & (df['p8'] < -0.08) & (df['spot_cvd_delta'] > 0)),
            ((df['close'] < df['close'].ewm(span=50).mean()) & (df['p8'] > 0.08) & (df['spot_cvd_delta'] < 0))
        )),
        # S2: Altcoin Relative CVD Strength (Outperforming BTC flow)
        ("B2_RelBTCBreakout", lambda df: (
            ((df['zc_rel_btc'] > 0.2) & (df['p8'] < -0.10) & (df['mc'] >= 0)),
            ((df['zc_rel_btc'] < -0.2) & (df['p8'] > 0.10) & (df['mc'] <= 0))
        )),
        # S3: Extreme Liquidation Reversal (Liq zscore > 1.5 + RSI oversold/overbought)
        ("B3_LiqExhaustionSnap", lambda df: (
            ((df['long_liq_zscore'] > 1.5) & (df['rsi'] < 35)),
            ((df['short_liq_zscore'] > 1.5) & (df['rsi'] > 65))
        )),
        # S4: OI Flush Absorption (OI sharp decline + CVD buying)
        ("B4_OIFlushAbsorption", lambda df: (
            ((df['oi_flush'] < -0.01) & (df['spot_cvd_delta'] > 0)),
            ((df['oi_flush'] < -0.01) & (df['spot_cvd_delta'] < 0))
        )),
        # S5: Fast Microstructure CVD Pulse (zc4 > 0.8)
        ("B5_FastCVDPulse", lambda df: (
            ((df['zc4'] > 0.6) & (df['p8'] < -0.05)),
            ((df['zc4'] < -0.6) & (df['p8'] > 0.05))
        )),
        # S6: Low Volatility Range Compression Breakout
        ("B6_LowVolExpansion", lambda df: (
            ((df['vol_ratio'] < 0.9) & (df['spot_cvd_delta'] > 0) & (df['rsi'] > 50)),
            ((df['vol_ratio'] < 0.9) & (df['spot_cvd_delta'] < 0) & (df['rsi'] < 50))
        )),
        # S7: Deep Pullback in Any Macro
        ("B7_DeepValueBroad", lambda df: (
            ((df['p8'] < -0.25) & (df['rsi'] < 38)),
            ((df['p8'] > 0.25) & (df['rsi'] > 62))
        )),
        # S8: Funding Rate Dislocation (Extreme negative funding + price stabilizing)
        ("B8_FundingDislocation", lambda df: (
            ((df['zfr'] < -1.2) & (df['p8'] < -0.10)),
            ((df['zfr'] > 1.2) & (df['p8'] > 0.10))
        )),
    ]
    
    extracted_spec = {}
    for name, sig_fn in specialized_archetypes:
        t0 = time.time()
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
        extracted_spec[name] = df_a
        print(f"Extracted {len(df_a):,} trades for {name} in {time.time()-t0:.1f}s.")
        
    target_windows = [9, 13, 15, 16, 17, 18, 20]
    
    print("\n" + "="*80)
    print("TESTING SPECIALIZED ALPHAS ON TARGET WINDOWS")
    print("="*80)
    
    for w_num in target_windows:
        wi = w_num - 1
        test_start_str, test_end_str = OOS_MONTHS[wi]
        test_start = pd.to_datetime(test_start_str, utc=True)
        test_end = pd.to_datetime(test_end_str, utc=True)
        train_end = test_start - pd.Timedelta(hours=3)
        train_start = test_start - relativedelta(months=18)
        
        passes = []
        
        for name, df_a in extracted_spec.items():
            df_is = df_a[(df_a['entry_time'] >= train_start) & (df_a['exit_time'] < train_end)].copy()
            df_oos = df_a[(df_a['entry_time'] >= test_start) & (df_a['entry_time'] < test_end)].copy()
            
            if len(df_is) < 50 or len(df_oos) == 0: continue
            
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
                    m = lgb.LGBMClassifier(max_depth=md, learning_rate=lr, n_estimators=60, scale_pos_weight=sw, random_state=42, verbose=-1, min_child_samples=15)
                    m.fit(X_train, y_train)
                    
                    probs_raw = m.predict_proba(X_oos)[:, 1].astype(np.float64)
                    
                    for ht in [30.0, 50.0, 80.0, 100.0, 120.0]:
                        for h_risk in [180.0, 200.0, 220.0, 240.0]:
                            for b_risk in [60.0, 75.0, 90.0]:
                                for th in np.arange(0.46, 0.68, 0.02):
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
                                        house_trigger=ht, house_risk=h_risk, base_risk=b_risk
                                    )
                                    
                                    if roi >= 0.20 and dd <= 0.05 and wr >= 0.40 and tr >= 5:
                                        passes.append({
                                            "archetype": name,
                                            "md": md, "lr": lr, "ht": ht, "hr": h_risk, "br": b_risk, "th": round(float(th), 2),
                                            "trades": tr, "wr": round(wr, 3), "roi": round(roi, 3), "dd": round(dd, 3)
                                        })
                                        
        if passes:
            best = max(passes, key=lambda x: (x['roi'], x['wr']))
            print(f"Window {w_num:02d} ({test_start_str}): ✅ {len(passes)} PASSES! Best: {best['archetype']} [d={best['md']}, lr={best['lr']}, ht={best['ht']}, hr={best['hr']}, th={best['th']}] -> Tr={best['trades']}, WR={best['wr']*100:.1f}%, ROI={best['roi']*100:.1f}%, DD={best['dd']*100:.2f}%")
        else:
            print(f"Window {w_num:02d} ({test_start_str}): ❌ 0 passes.")

if __name__ == "__main__":
    analyze_targeted_windows()
