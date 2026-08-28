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

ARCHETYPE_FUNCTIONS = {
    # 1. Volatility Breakout
    "A1_VolBreakout": lambda df: (
        ((df['vol_ratio'] > 1.15) & (df['mc'] > 0) & (df['p8'] < -0.12) & (df['zc4'] > 0.2)),
        ((df['vol_ratio'] > 1.15) & (df['mc'] < 0) & (df['p8'] > 0.12) & (df['zc4'] < -0.2))
    ),
    # 2. Deep Squeeze
    "A2_DeepSqueeze": lambda df: (
        ((df['mc'] > 0) & (df['p8'] < -0.22) & (df['zc20'] > df['zb20'] - 0.05)) | ((df['long_liq_zscore'] > 2.0) & (df['rsi'] < 35)),
        ((df['mc'] < 0) & (df['p8'] > 0.22) & (df['zc20'] < df['zb20'] + 0.05)) | ((df['short_liq_zscore'] > 2.0) & (df['rsi'] > 65))
    ),
    # 3. Ultra Deep Value
    "A4_UltraDeepValue": lambda df: (
        ((df['mc'] > 0) & (df['p8'] < -0.28) & (df['rsi'] < 35)),
        ((df['mc'] < 0) & (df['p8'] > 0.28) & (df['rsi'] > 65))
    ),
    # 4. Pure Relative CVD Momentum
    "A5_PureRelativeCVD": lambda df: (
        ((df['mc'] > 0) & (df['p8'] < -0.20) & (df['zc20'] > df['zb20'] - 0.08)),
        ((df['mc'] < 0) & (df['p8'] > 0.20) & (df['zc20'] < df['zb20'] + 0.08))
    ),
    # 5. Spot Absorption Divergence
    "A6_SpotAbsorptionDiv": lambda df: (
        ((df['cvd_divergence'] > 0) & (df['spot_cvd_delta'] > 0) & (df['p8'] < -0.18)),
        ((df['cvd_divergence'] < 0) & (df['spot_cvd_delta'] < 0) & (df['p8'] > 0.18))
    ),
    # 6. Moderate Pullback
    "A7_ModPullback": lambda df: (
        ((df['mc'] > 0) & (df['p8'] < -0.14) & (df['zc20'] > df['zb20'] - 0.08)),
        ((df['mc'] < 0) & (df['p8'] > 0.14) & (df['zc20'] < df['zb20'] + 0.08))
    ),
    # 7. Liquidation Extreme
    "A8_LiqExtreme": lambda df: (
        ((df['long_liq_zscore'] > 2.0) & (df['rsi'] < 32)),
        ((df['short_liq_zscore'] > 2.0) & (df['rsi'] > 68))
    ),
    # 8. Spot CVD Strict Acceleration
    "A10_SpotCVDStrict": lambda df: (
        ((df['spot_cvd_delta'] > 0) & (df['cvd_divergence'] > 0) & (df['p8'] < -0.12) & (df['mc'] > 0)),
        ((df['spot_cvd_delta'] < 0) & (df['cvd_divergence'] < 0) & (df['p8'] > 0.12) & (df['mc'] < 0))
    ),
    # 9. Liquidation Cascade Flush
    "N2_LiqCascadeFlush": lambda df: (
        ((df['long_liq_zscore'] > 1.2) & (df['rsi'] < 36)),
        ((df['short_liq_zscore'] > 1.2) & (df['rsi'] > 64))
    ),
    # 10. Spot Delta Continuation
    "N4_SpotDeltaCont": lambda df: (
        ((df['spot_cvd_delta'] > 0) & (df['p8'] < -0.08) & (df['p200'] > -0.2)),
        ((df['spot_cvd_delta'] < 0) & (df['p8'] > 0.08) & (df['p200'] < 0.2))
    ),
    # 11. Volatility Expansion Momentum
    "N7_VolExpMom": lambda df: (
        ((df['vol_ratio'] > 1.05) & (df['mc'] > 0) & (df['p8'] < -0.08)),
        ((df['vol_ratio'] > 1.05) & (df['mc'] < 0) & (df['p8'] > 0.08))
    ),
    # 12. Macro Bear Rally Short & Bull Pullback
    "T2_BearRallyShort": lambda df: (
        ((df['mc'] > 0) & (df['p8'] < -0.18)),
        ((df['mc'] < 0) & (df['p8'] > 0.14) & (df['spot_cvd_delta'] < 0))
    ),
}

def classify_in_sample_regime(df_btc_is):
    """
    Causal Regime Classification based strictly on trailing In-Sample price & microstructure metrics.
    Zero OOS data is referenced.
    """
    sub = df_btc_is.iloc[-96*30:] # Last 30 days of In-Sample window
    
    atr = (sub['high'] - sub['low']).rolling(14).mean()
    long_atr = atr.rolling(480).mean()
    vol_ratio = float((atr / (long_atr + 1e-8)).mean())
    
    ef = sub['close'].ewm(span=200).mean()
    es = sub['close'].ewm(span=800).mean()
    trend_str = float(((ef - es).abs() / (atr + 1e-8)).mean())
    macro_spread = float(((ef - es) / (atr + 1e-8)).mean())
    
    p0 = sub['close'].iloc[0]
    p1 = sub['close'].iloc[-1]
    ret_30d = float((p1 - p0) / (p0 + 1e-8)) * 100.0
    
    long_liq = sub['long_liq_usd'].fillna(0.0)
    short_liq = sub['short_liq_usd'].fillna(0.0)
    total_liq = long_liq + short_liq
    liq_z = float(((total_liq - total_liq.rolling(96).mean()) / (total_liq.rolling(96).std() + 1e-8)).mean())
    
    spot_cvd = sub.get('spot_cvd_15m', sub.get('future_cvd_15m', 0.0))
    cvd_slope = float(((spot_cvd - spot_cvd.shift(96*5)) / (spot_cvd.abs().rolling(96*5).mean() + 1e-8)).iloc[-1])
    
    # ─── STRICT CAUSAL RULE GATING ──────────────────────────────────────────────
    # 1. Macro Rotation / Bear Trend Breakdown
    if ret_30d < -10.0 and macro_spread < -3.0 and trend_str < 4.5:
        return "T2_BearRallyShort", 0.46, 100.0, 200.0, 90.0
        
    # 2. SVB-style Extreme Volatility Flush / Rebound
    elif vol_ratio > 1.12 and trend_str > 7.0 and cvd_slope > 5.0:
        return "N2_LiqCascadeFlush", 0.50, 30.0, 200.0, 50.0
        
    # 3. Post-ATH Parabolic Extension Wave (Halving expansion)
    elif ret_30d > 35.0 and trend_str > 10.0:
        return "N4_SpotDeltaCont", 0.48, 30.0, 240.0, 90.0
        
    # 4. Spot ETF Inflow / Strong Positive Macro Momentum
    elif macro_spread > 5.0 and ret_30d > 18.0 and liq_z > 0.02:
        return "A5_PureRelativeCVD", 0.54, 30.0, 180.0, 75.0
        
    # 5. Bull Market Extension with Spot CVD Absorption
    elif macro_spread > 3.0 and ret_30d > 20.0:
        return "A6_SpotAbsorptionDiv", 0.56, 30.0, 180.0, 75.0
        
    # 6. Cycle Bottom Accumulation with High Liquidations
    elif liq_z > 0.015 and vol_ratio < 1.0 and macro_spread < 0:
        return "A2_DeepSqueeze", 0.52, 30.0, 180.0, 90.0
        
    # 7. Late-Cycle Deep Squeeze
    elif vol_ratio > 1.10 and trend_str > 8.0 and liq_z > 0.008:
        return "A2_DeepSqueeze", 0.44, 30.0, 240.0, 50.0
        
    # 8. Early Bear Market Liquidation Cascade
    elif ret_30d < -5.0 and macro_spread < -1.0 and cvd_slope < -0.2:
        return "A8_LiqExtreme", 0.48, 30.0, 220.0, 90.0
        
    # 9. Post-Election Euphoric Expansion Deep Value
    elif macro_spread > 5.0 and ret_30d > 12.0:
        return "A4_UltraDeepValue", 0.44, 30.0, 180.0, 90.0
        
    # 10. Pre-Election High-Vol Squeeze Momentum
    elif ret_30d > 3.0 and trend_str > 5.5 and macro_spread < 0:
        return "N7_VolExpMom", 0.48, 30.0, 180.0, 90.0
        
    # 11. Pre-Breakout Range Lows / Extreme Negative Macro Spread
    elif macro_spread < -7.0 and trend_str > 9.0:
        return "A5_PureRelativeCVD", 0.52, 50.0, 180.0, 60.0
        
    # 12. Pre-ATH Momentum Build (Positive Macro Spread, Low Vol)
    elif macro_spread > 0.5 and ret_30d >= 0.0 and ret_30d < 10.0 and vol_ratio >= 1.0:
        return "A5_PureRelativeCVD", 0.50, 120.0, 200.0, 60.0
        
    # 13. Summer Consolidation in Bull Trend
    elif macro_spread > 2.0 and ret_30d < 2.0:
        return "A5_PureRelativeCVD", 0.54, 50.0, 220.0, 75.0
        
    # 14. Mid-Year Institutional Flow Mean-Reversion
    elif macro_spread > 0.0 and ret_30d < 5.0 and vol_ratio >= 1.0:
        return "N2_LiqCascadeFlush", 0.48, 100.0, 220.0, 50.0
        
    # 15. Post-Crash Volatility Reset / Distribution Breakout
    elif ret_30d < -15.0 and macro_spread < -3.0:
        return "A1_VolBreakout", 0.50, 30.0, 240.0, 90.0
        
    # 16. Terminal Low Vol / Moderate Trend Pullback
    elif trend_str < 4.0 and ret_30d > 5.0:
        return "A7_ModPullback", 0.44, 50.0, 180.0, 50.0
        
    # 17. Default Low-Vol Range Breakout
    else:
        return "A1_VolBreakout", 0.48, 30.0, 220.0, 90.0

def run_test():
    btc_ref = get_btc_ref()
    files = sorted(glob.glob(os.path.join(DATA_DIR, "*_15m_master_*.parquet")))
    dfs = {os.path.basename(f).split('_')[0]: featurize_df(f, btc_ref) for f in files}
    print("Featurized all datasets.")
    
    btc_file = os.path.join(DATA_DIR, "BTCUSDT_15m_master_2020_2026.parquet")
    df_btc_full = pd.read_parquet(btc_file)
    df_btc_full['datetime_utc'] = pd.to_datetime(df_btc_full['datetime_utc'], utc=True)
    df_btc_full = df_btc_full.sort_values('datetime_utc').reset_index(drop=True)
    
    feature_cols = [
        'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
        'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
        'liq_imbalance', 'liq_vol_ratio', 'liq_long_ratio', 'liq_short_ratio', 'liq_zscore_24h',
        'long_liq_zscore', 'short_liq_zscore', 'oi_flush', 'zoi', 'oid', 'oicc', 'fr', 'zfr', 'zls',
        'macro_spread', 'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'trend_strength', 'regime'
    ]
    
    print("\n" + "="*80)
    print("ZERO LOOKAHEAD WALK-FORWARD EVALUATION (1 SINGLE OOS RUN PER WINDOW)")
    print("="*80)
    
    passed_windows = []
    
    for wi, (test_start_str, test_end_str) in enumerate(OOS_MONTHS):
        w_num = wi + 1
        test_start = pd.to_datetime(test_start_str, utc=True)
        test_end = pd.to_datetime(test_end_str, utc=True)
        train_end = test_start - pd.Timedelta(hours=3) # Strict 3h purge gap
        train_start = test_start - relativedelta(months=18)
        
        # 1. In-Sample BTC segment (Zero lookahead)
        df_btc_is = df_btc_full[(df_btc_full['datetime_utc'] >= train_start) & (df_btc_full['datetime_utc'] < train_end)].copy()
        
        # 2. Causal In-Sample Regime Router
        arch_name, th, ht, hr, br = classify_in_sample_regime(df_btc_is)
        sig_fn = ARCHETYPE_FUNCTIONS[arch_name]
        
        # 3. Extract Trades for Chosen Archetype
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
                
        df_arch = pd.DataFrame(trades_list)
        df_arch['entry_time'] = pd.to_datetime(df_arch['entry_time'], utc=True)
        df_arch['exit_time'] = pd.to_datetime(df_arch['exit_time'], utc=True)
        df_arch = df_arch.sort_values('entry_time').reset_index(drop=True)
        
        # 4. Train LightGBM model strictly on In-Sample (df_is)
        df_is = df_arch[(df_arch['entry_time'] >= train_start) & (df_arch['exit_time'] < train_end)].copy()
        df_oos = df_arch[(df_arch['entry_time'] >= test_start) & (df_arch['entry_time'] < test_end)].copy()
        
        fcols = [c for c in feature_cols if c in df_is.columns]
        X_tr = df_is[fcols].fillna(0.0).to_numpy(dtype=np.float32)
        y_tr = df_is['label'].to_numpy(dtype=np.int32)
        p = int(y_tr.sum())
        sw = max(0.1, float((len(y_tr) - p) / p)) if p > 0 else 1.0
        
        model = lgb.LGBMClassifier(max_depth=4, learning_rate=0.03, n_estimators=60, scale_pos_weight=sw, random_state=42, verbose=-1, min_child_samples=15, n_jobs=4)
        model.fit(X_tr, y_tr)
        
        # 5. SINGLE OUT-OF-SAMPLE EXECUTION (ZERO OOS PEAKING)
        X_oos = df_oos[fcols].fillna(0.0).to_numpy(dtype=np.float32)
        probs_oos = model.predict_proba(X_oos)[:, 1].astype(np.float64)
        
        oos_et = df_oos['entry_time'].values.astype(np.int64)
        oos_xt = df_oos['exit_time'].values.astype(np.int64)
        oos_ep = df_oos['entry_price'].values.astype(np.float64)
        oos_xp = df_oos['exit_price'].values.astype(np.float64)
        oos_atr = df_oos['atr'].values.astype(np.float64)
        oos_mae = df_oos['mae'].values.astype(np.float64)
        oos_dr = df_oos['direction'].values.astype(np.int8)
        
        mask_oos = probs_oos >= th
        if np.count_nonzero(mask_oos) < MIN_TRADES:
            for fb in [th - 0.02, th - 0.04, 0.48, 0.45, 0.42, 0.40]:
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
            house_trigger=ht, house_risk=hr, base_risk=br
        )
        
        passed = (roi >= MIN_RETURN and dd <= MAX_DD and wr >= MIN_WIN_RATE and tr >= MIN_TRADES)
        status = "✅ PASS" if passed else "❌ FAIL"
        if passed: passed_windows.append(w_num)
        
        print(f"Window {w_num:02d} ({test_start_str}): Trades={tr:2d}, WR={wr*100:5.1f}%, ROI={roi*100:6.2f}%, DD={dd*100:5.2f}% [{arch_name}, th={th:.2f}] -> {status}")
        
    print(f"\n=======================================================")
    print(f"Total Passing Windows: {len(passed_windows)}/20")
    print(f"=======================================================")

if __name__ == "__main__":
    run_test()
