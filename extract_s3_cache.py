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

MIN_RETURN = 0.20
MAX_DD = 0.05
MIN_WIN_RATE = 0.40
MIN_TRADES = 5

OOS_MONTHS = [
    ("2021-03-15", "2021-04-15"),  # OOS 01: Spring 2021 Bull Extension
    ("2021-06-15", "2021-07-15"),  # OOS 02: Post-May 2021 Reset
    ("2021-09-15", "2021-10-15"),  # OOS 03: Pre-ATH Momentum Build
    ("2021-12-15", "2022-01-15"),  # OOS 04: Post-ATH Distribution
    ("2022-03-15", "2022-04-15"),  # OOS 05: Early 2022 Bear Structure
    ("2022-06-15", "2022-07-15"),  # OOS 06: Post-Luna Compression
    ("2022-09-15", "2022-10-15"),  # OOS 07: Pre-FTX Low-Vol Range
    ("2022-12-15", "2023-01-15"),  # OOS 08: FTX Cycle Bottom Accumulation
    ("2023-03-15", "2023-04-15"),  # OOS 09: SVB Rebound & Flight to Quality
    ("2023-06-15", "2023-07-15"),  # OOS 10: BlackRock ETF Filing Wave
    ("2023-09-15", "2023-10-15"),  # OOS 11: Pre-Breakout Range Lows
    ("2023-12-15", "2024-01-15"),  # OOS 12: Spot ETF Approval Run-up
    ("2024-03-15", "2024-04-15"),  # OOS 13: Post-ATH Halving Consolidation
    ("2024-06-15", "2024-07-15"),  # OOS 14: Summer 2024 Range Trade
    ("2024-09-15", "2024-10-15"),  # OOS 15: Pre-Election Squeeze
    ("2024-12-15", "2025-01-15"),  # OOS 16: Post-Election Expansion
    ("2025-03-15", "2025-04-15"),  # OOS 17: 2025 Macro Rotation
    ("2025-06-15", "2025-07-15"),  # OOS 18: Mid-2025 Institutional Flow
    ("2025-10-15", "2025-11-15"),  # OOS 19: Late-2025 Extension
    ("2026-03-15", "2026-04-15")   # OOS 20: Terminal Forward Horizon
]

# S3 Trend Follow Archetype Definitions
S3_ARCHETYPES = {
    # TF1: Classic Macro Trend Pullback (EMA 200/800 stack + EMA 8 pullback)
    "TF1_ClassicTrendPullback": lambda df: (
        ((df['mc'] > 0) & (df['p8'] < -0.20)),
        ((df['mc'] < 0) & (df['p8'] > 0.20))
    ),
    # TF2: Moderate Trend Pullback with Relative CVD support
    "TF2_ModPullbackCVD": lambda df: (
        ((df['mc'] > 0) & (df['p8'] < -0.14) & (df['zc20'] > df['zb20'] - 0.08)),
        ((df['mc'] < 0) & (df['p8'] > 0.14) & (df['zc20'] < df['zb20'] + 0.08))
    ),
    # TF3: Ultra Deep Value Macro Pullback
    "TF3_UltraDeepValue": lambda df: (
        ((df['mc'] > 0) & (df['p8'] < -0.28) & (df['rsi'] < 35)),
        ((df['mc'] < 0) & (df['p8'] > 0.28) & (df['rsi'] > 65))
    ),
    # TF4: Volatility Expansion Trend Breakout
    "TF4_VolExpansionTrend": lambda df: (
        ((df['vol_ratio'] > 1.15) & (df['mc'] > 0) & (df['p8'] < -0.12) & (df['zc4'] > 0.2)),
        ((df['vol_ratio'] > 1.15) & (df['mc'] < 0) & (df['p8'] > 0.12) & (df['zc4'] < -0.2))
    ),
    # TF5: Relative BTC CVD Momentum Trend
    "TF5_RelativeCVDTrend": lambda df: (
        ((df['mc'] > 0) & (df['p8'] < -0.20) & (df['zc20'] > df['zb20'] - 0.08)),
        ((df['mc'] < 0) & (df['p8'] > 0.20) & (df['zc20'] < df['zb20'] + 0.08))
    ),
    # TF6: Spot Absorption Divergence in Trend
    "TF6_SpotAbsorptionTrend": lambda df: (
        ((df['cvd_divergence'] > 0) & (df['spot_cvd_delta'] > 0) & (df['p8'] < -0.18)),
        ((df['cvd_divergence'] < 0) & (df['spot_cvd_delta'] < 0) & (df['p8'] > 0.18))
    ),
    # TF7: Liquidation Cascade Pullback in Macro Trend
    "TF7_LiqCascadeTrend": lambda df: (
        ((df['long_liq_zscore'] > 1.2) & (df['rsi'] < 36)),
        ((df['short_liq_zscore'] > 1.2) & (df['rsi'] > 64))
    ),
    # TF8: Spot Delta Continuation in Macro Trend
    "TF8_SpotDeltaTrend": lambda df: (
        ((df['spot_cvd_delta'] > 0) & (df['p8'] < -0.08) & (df['p200'] > -0.2)),
        ((df['spot_cvd_delta'] < 0) & (df['p8'] > 0.08) & (df['p200'] < 0.2))
    ),
    # TF9: Volatility Expansion Momentum Trend
    "TF9_VolExpMomTrend": lambda df: (
        ((df['vol_ratio'] > 1.05) & (df['mc'] > 0) & (df['p8'] < -0.08)),
        ((df['vol_ratio'] > 1.05) & (df['mc'] < 0) & (df['p8'] > 0.08))
    ),
    # TF10: Macro Bear Breakdown / Rally Short
    "TF10_BearRallyShort": lambda df: (
        ((df['mc'] > 0) & (df['p8'] < -0.18)),
        ((df['mc'] < 0) & (df['p8'] > 0.14) & (df['spot_cvd_delta'] < 0))
    ),
    # TF11: Deep Squeeze S3 Pullback
    "TF11_DeepSqueezeTrend": lambda df: (
        ((df['mc'] > 0) & (df['p8'] < -0.22) & (df['zc20'] > df['zb20'] - 0.05)) | ((df['long_liq_zscore'] > 2.0) & (df['rsi'] < 35)),
        ((df['mc'] < 0) & (df['p8'] > 0.22) & (df['zc20'] < df['zb20'] + 0.05)) | ((df['short_liq_zscore'] > 2.0) & (df['rsi'] > 65))
    ),
    # TF12: Spot CVD Strict Momentum Trend
    "TF12_SpotCVDStrictTrend": lambda df: (
        ((df['spot_cvd_delta'] > 0) & (df['cvd_divergence'] > 0) & (df['p8'] < -0.12) & (df['mc'] > 0)),
        ((df['spot_cvd_delta'] < 0) & (df['cvd_divergence'] < 0) & (df['p8'] > 0.12) & (df['mc'] < 0))
    ),
    # TF13: Extreme Liquidation Pullback
    "TF13_LiqExtremeTrend": lambda df: (
        ((df['long_liq_zscore'] > 2.0) & (df['rsi'] < 32)),
        ((df['short_liq_zscore'] > 2.0) & (df['rsi'] > 68))
    )
}

CACHE_DIR_S3 = "/tmp/s3_cache"
os.makedirs(CACHE_DIR_S3, exist_ok=True)

def extract_and_cache_s3():
    btc_ref = get_btc_ref()
    files = sorted(glob.glob(os.path.join(DATA_DIR, "*_15m_master_*.parquet")))
    dfs = {os.path.basename(f).split('_')[0]: featurize_df(f, btc_ref) for f in files}
    print(f"Featurized {len(dfs)} datasets for Strategy S3 (Macro Trend Follow).")
    
    feature_cols = [
        'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
        'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
        'liq_imbalance', 'liq_vol_ratio', 'liq_long_ratio', 'liq_short_ratio', 'liq_zscore_24h',
        'long_liq_zscore', 'short_liq_zscore', 'oi_flush', 'zoi', 'oid', 'oicc', 'fr', 'zfr', 'zls',
        'macro_spread', 'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'trend_strength', 'regime'
    ]
    
    for name, sig_fn in S3_ARCHETYPES.items():
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
        
        save_path = os.path.join(CACHE_DIR_S3, f"{name}.parquet")
        df_a.to_parquet(save_path)
        print(f"Saved {name}: {len(df_a):,} trades in {time.time()-t0:.1f}s.")

if __name__ == "__main__":
    extract_and_cache_s3()
