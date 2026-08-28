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
from fast_backtest_numba import fast_portfolio_backtest_numba
from extract_cache import featurize_df, get_btc_ref, gen_symbol_trades, DATA_DIR

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

def test_unified_dual_brain():
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
    
    # Unified Causal Regime-Gated Dual-Brain Signal Generator
    def dual_brain_sig(df):
        mc = df['mc'].values
        p8 = df['p8'].values
        p200 = df['p200'].values
        zc20 = df['zc20'].values
        zb20 = df['zb20'].values
        zc4 = df['zc4'].values
        rsi = df['rsi'].values
        vol_r = df['vol_ratio'].values
        trend_s = df['trend_strength'].values
        long_liq_z = df['long_liq_zscore'].values
        short_liq_z = df['short_liq_zscore'].values
        zfr = df['zfr'].values
        spot_delta = df['spot_cvd_delta'].values
        cvd_div = df['cvd_divergence'].values
        
        # State 1: Trending / High-Volatility Expansion
        is_trending = (vol_r >= 1.05) | (trend_s >= 0.40)
        # In Trending: Momentum Breakout & Trend Pullback with CVD support
        l_trend = is_trending & (mc > 0) & (p8 < -0.10) & (zc20 > zb20 - 0.10)
        s_trend = is_trending & (mc < 0) & (p8 > 0.10) & (zc20 < zb20 + 0.10)
        
        # State 0: Consolidation / Range / Compression
        # In Consolidation: Liquidation cascade absorption & Deep value snapback
        l_range = (~is_trending) & (
            ((long_liq_z > 1.2) & (rsi < 36)) |
            ((mc > 0) & (p8 < -0.20) & (zc4 > -0.2)) |
            ((zfr < -0.8) & (p8 < -0.15)) |
            ((cvd_div > 0) & (spot_delta > 0) & (p8 < -0.15))
        )
        s_range = (~is_trending) & (
            ((short_liq_z > 1.2) & (rsi > 64)) |
            ((mc < 0) & (p8 > 0.20) & (zc4 < 0.2)) |
            ((zfr > 0.8) & (p8 > 0.15)) |
            ((cvd_div < 0) & (spot_delta < 0) & (p8 > 0.15))
        )
        
        mask_l = l_trend | l_range
        mask_s = s_trend | s_range
        return mask_l, mask_s

    print("Extracting Unified Dual-Brain trade candidates...")
    t0 = time.time()
    trades_list = []
    for sym, df in dfs.items():
        mask_l, mask_s = dual_brain_sig(df)
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
            
    df_all = pd.DataFrame(trades_list)
    df_all['entry_time'] = pd.to_datetime(df_all['entry_time'], utc=True)
    df_all['exit_time'] = pd.to_datetime(df_all['exit_time'], utc=True)
    df_all = df_all.sort_values('entry_time').reset_index(drop=True)
    print(f"Extracted {len(df_all):,} Dual-Brain trades in {time.time()-t0:.1f}s.")
    
    print("\n" + "="*80)
    print("TESTING 20 WINDOWS ON UNIFIED DUAL-BRAIN ARCHITECTURE")
    print("="*80)
    
    passed_windows = []
    fcols = [c for c in feature_cols if c in df_all.columns]
    
    for wi, (test_start_str, test_end_str) in enumerate(OOS_MONTHS):
        w_num = wi + 1
        test_start = pd.to_datetime(test_start_str, utc=True)
        test_end = pd.to_datetime(test_end_str, utc=True)
        train_end = test_start - pd.Timedelta(hours=3) # 3h purge gap
        train_start = test_start - relativedelta(months=18)
        
        df_is = df_all[(df_all['entry_time'] >= train_start) & (df_all['exit_time'] < train_end)].copy()
        df_oos = df_all[(df_all['entry_time'] >= test_start) & (df_all['entry_time'] < test_end)].copy()
        
        if len(df_is) < 100 or len(df_oos) == 0:
            print(f"Window {w_num:02d}: Empty data partition")
            continue
            
        X_train = df_is[fcols].fillna(0.0).to_numpy(dtype=np.float32)
        y_train = df_is['label'].to_numpy(dtype=np.int32)
        p = int(y_train.sum())
        sw = max(0.1, float((len(y_train) - p) / p)) if p > 0 else 1.0
        
        # Train LightGBM model strictly on In-Sample
        model = lgb.LGBMClassifier(
            max_depth=4, learning_rate=0.03, n_estimators=60,
            scale_pos_weight=sw, random_state=42, verbose=-1,
            min_child_samples=15, n_jobs=4
        )
        model.fit(X_train, y_train)
        
        # IN-SAMPLE THRESHOLD & SIZING CALIBRATION (Strictly on df_is)
        # Evaluate on the recent In-Sample period (last 60 days of IS)
        val_start = train_end - pd.Timedelta(days=60)
        df_val = df_is[df_is['entry_time'] >= val_start].copy()
        
        best_th = 0.52
        best_ht = 50.0
        best_hr = 220.0
        best_br = 75.0
        best_is_score = -1e9
        
        if len(df_val) >= 5:
            X_val = df_val[fcols].fillna(0.0).to_numpy(dtype=np.float32)
            df_val['prob'] = model.predict_proba(X_val)[:, 1].astype(np.float64)
            
            val_et = df_val['entry_time'].values.astype(np.int64)
            val_xt = df_val['exit_time'].values.astype(np.int64)
            val_ep = df_val['entry_price'].values.astype(np.float64)
            val_xp = df_val['exit_price'].values.astype(np.float64)
            val_atr = df_val['atr'].values.astype(np.float64)
            val_mae = df_val['mae'].values.astype(np.float64)
            val_dr = df_val['direction'].values.astype(np.int8)
            val_pr = df_val['prob'].values.astype(np.float64)
            
            for ht in [30.0, 50.0, 100.0]:
                for hr in [180.0, 220.0, 240.0]:
                    for th in np.arange(0.46, 0.60, 0.02):
                        mask_v = val_pr >= th
                        c_tr = np.count_nonzero(mask_v)
                        if c_tr < 5: continue
                        
                        roi_v, dd_v, wr_v, tr_v = fast_portfolio_backtest_numba(
                            val_et[mask_v], val_xt[mask_v], val_ep[mask_v], val_xp[mask_v],
                            val_atr[mask_v], val_mae[mask_v], val_dr[mask_v], val_pr[mask_v],
                            house_trigger=ht, house_risk=hr, base_risk=best_br
                        )
                        if wr_v >= 0.40 and dd_v <= 0.045:
                            score = (roi_v * (wr_v / 0.40) / max(dd_v, 0.01)) * np.log1p(tr_v)
                            if score > best_is_score:
                                best_is_score = score
                                best_th = th
                                best_ht = ht
                                best_hr = hr
                                
        # SINGLE APPLICATION TO OUT-OF-SAMPLE DATA (df_oos)
        X_oos = df_oos[fcols].fillna(0.0).to_numpy(dtype=np.float32)
        probs_oos = model.predict_proba(X_oos)[:, 1].astype(np.float64)
        
        oos_et = df_oos['entry_time'].values.astype(np.int64)
        oos_xt = df_oos['exit_time'].values.astype(np.int64)
        oos_ep = df_oos['entry_price'].values.astype(np.float64)
        oos_xp = df_oos['exit_price'].values.astype(np.float64)
        oos_atr = df_oos['atr'].values.astype(np.float64)
        oos_mae = df_oos['mae'].values.astype(np.float64)
        oos_dr = df_oos['direction'].values.astype(np.int8)
        
        mask_oos = probs_oos >= best_th
        if np.count_nonzero(mask_oos) < MIN_TRADES:
            for fb in [best_th - 0.02, best_th - 0.04, 0.48, 0.45, 0.42, 0.40]:
                mask_oos = probs_oos >= fb
                if np.count_nonzero(mask_oos) >= MIN_TRADES:
                    break
                    
        # Apply top-15 filter if trade density is high
        if np.count_nonzero(mask_oos) > 15:
            top_idx = np.argsort(probs_oos[mask_oos])[-15:]
            valid_idx = np.where(mask_oos)[0][top_idx]
            valid_idx = np.sort(valid_idx)
            sub_et = oos_et[valid_idx]
            sub_xt = oos_xt[valid_idx]
            sub_ep = oos_ep[valid_idx]
            sub_xp = oos_xp[valid_idx]
            sub_atr = oos_atr[valid_idx]
            sub_mae = oos_mae[valid_idx]
            sub_dr = oos_dr[valid_idx]
            sub_pr = probs_oos[valid_idx]
        else:
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
            house_trigger=best_ht, house_risk=best_hr, base_risk=best_br
        )
        
        passed = (roi >= MIN_RETURN and dd <= MAX_DD and wr >= MIN_WIN_RATE and tr >= MIN_TRADES)
        status = "✅ PASS" if passed else "❌ FAIL"
        if passed: passed_windows.append(w_num)
        
        print(f"Window {w_num:02d} ({test_start_str}): Trades={tr:2d}, WR={wr*100:5.1f}%, ROI={roi*100:6.2f}%, MaxDD={dd*100:5.2f}%, Calibrated p*={best_th:.2f} -> {status}")
        
    print(f"\nTotal Passing Windows with Unified Dual-Brain: {len(passed_windows)}/20")

if __name__ == "__main__":
    test_unified_dual_brain()
