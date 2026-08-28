import os
import glob
import pandas as pd
import numpy as np
from datetime import datetime
from dateutil.relativedelta import relativedelta

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Engine_2", "binance_backtesting_data")

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

def analyze_is_regimes():
    btc_file = os.path.join(DATA_DIR, "BTCUSDT_15m_master_2020_2026.parquet")
    df_btc = pd.read_parquet(btc_file)
    df_btc['datetime_utc'] = pd.to_datetime(df_btc['datetime_utc'], utc=True)
    df_btc = df_btc.sort_values('datetime_utc').reset_index(drop=True)
    
    # Calculate BTC rolling metrics
    atr = (df_btc['high'] - df_btc['low']).rolling(14).mean()
    long_atr = atr.rolling(480).mean()
    df_btc['vol_ratio'] = atr / (long_atr + 1e-8)
    
    ef = df_btc['close'].ewm(span=200).mean()
    es = df_btc['close'].ewm(span=800).mean()
    df_btc['trend_str'] = (ef - es).abs() / (atr + 1e-8)
    df_btc['macro_dir'] = np.where(ef > es, 1, -1)
    
    long_liq = df_btc['long_liq_usd'].fillna(0.0)
    short_liq = df_btc['short_liq_usd'].fillna(0.0)
    total_liq = long_liq + short_liq
    df_btc['liq_zscore'] = (total_liq - total_liq.rolling(96).mean()) / (total_liq.rolling(96).std() + 1e-8)
    
    print(f"{'Win':<4} | {'Test Start':<10} | {'IS 30d VolRatio':<16} | {'IS 30d TrendStr':<16} | {'Macro Dir':<10} | {'Liq Intensity':<14} | {'Best Archetype'}")
    print("-" * 105)
    
    best_known = {
        1: "A6_SpotAbsorptionDiv",
        2: "A1_VolBreakout",
        3: "A5_PureRelativeCVD",
        4: "A1_VolBreakout",
        5: "A8_LiqExtreme",
        6: "A1_VolBreakout",
        7: "A1_VolBreakout",
        8: "A2_DeepSqueeze",
        9: "N2_LiqCascadeFlush",
        10: "A1_VolBreakout",
        11: "A5_PureRelativeCVD",
        12: "A5_PureRelativeCVD",
        13: "N4_SpotDeltaCont",
        14: "A5_PureRelativeCVD",
        15: "N7_VolExpMom",
        16: "A4_UltraDeepValue",
        17: "T2_BearRallyShort",
        18: "N2_LiqCascadeFlush",
        19: "A2_DeepSqueeze",
        20: "A7_ModPullback"
    }
    
    for wi, (test_start_str, test_end_str) in enumerate(OOS_MONTHS):
        w_num = wi + 1
        test_start = pd.to_datetime(test_start_str, utc=True)
        train_end = test_start - pd.Timedelta(hours=3)
        train_30d = train_end - pd.Timedelta(days=30)
        
        sub = df_btc[(df_btc['datetime_utc'] >= train_30d) & (df_btc['datetime_utc'] < train_end)]
        vr = sub['vol_ratio'].mean()
        ts = sub['trend_str'].mean()
        md = "BULL" if sub['macro_dir'].iloc[-1] == 1 else "BEAR"
        lq = sub['liq_zscore'].mean()
        
        arch = best_known.get(w_num, "N/A")
        print(f"{w_num:02d}   | {test_start_str:<10} | {vr:>14.3f}   | {ts:>14.3f}   | {md:<10} | {lq:>12.3f}   | {arch}")

if __name__ == "__main__":
    analyze_is_regimes()
