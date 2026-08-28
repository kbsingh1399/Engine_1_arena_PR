import os
import glob
import pandas as pd
import numpy as np

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

def map_is_regimes():
    btc_file = os.path.join(DATA_DIR, "BTCUSDT_15m_master_2020_2026.parquet")
    df_btc = pd.read_parquet(btc_file)
    df_btc['datetime_utc'] = pd.to_datetime(df_btc['datetime_utc'], utc=True)
    df_btc = df_btc.sort_values('datetime_utc').reset_index(drop=True)
    
    atr = (df_btc['high'] - df_btc['low']).rolling(14).mean()
    long_atr = atr.rolling(480).mean()
    df_btc['vol_ratio'] = atr / (long_atr + 1e-8)
    
    ef = df_btc['close'].ewm(span=200).mean()
    es = df_btc['close'].ewm(span=800).mean()
    df_btc['trend_str'] = (ef - es).abs() / (atr + 1e-8)
    df_btc['macro_spread'] = (ef - es) / (atr + 1e-8)
    
    long_liq = df_btc['long_liq_usd'].fillna(0.0)
    short_liq = df_btc['short_liq_usd'].fillna(0.0)
    total_liq = long_liq + short_liq
    df_btc['liq_zscore'] = (total_liq - total_liq.rolling(96).mean()) / (total_liq.rolling(96).std() + 1e-8)
    
    cvd = df_btc.get('spot_cvd_15m', df_btc.get('future_cvd_15m', 0.0))
    df_btc['cvd_slope'] = (cvd - cvd.shift(96)) / (cvd.abs().rolling(96).mean() + 1e-8)
    
    records = []
    for wi, (test_start_str, test_end_str) in enumerate(OOS_MONTHS):
        w_num = wi + 1
        test_start = pd.to_datetime(test_start_str, utc=True)
        train_end = test_start - pd.Timedelta(hours=3)
        train_30d = train_end - pd.Timedelta(days=30)
        
        sub = df_btc[(df_btc['datetime_utc'] >= train_30d) & (df_btc['datetime_utc'] < train_end)]
        vr = sub['vol_ratio'].mean()
        ts = sub['trend_str'].mean()
        ms = sub['macro_spread'].mean()
        lq = sub['liq_zscore'].mean()
        cs = sub['cvd_slope'].mean()
        
        records.append({
            'window': w_num,
            'start': test_start_str,
            'vol_ratio': round(float(vr), 3),
            'trend_str': round(float(ts), 3),
            'macro_spread': round(float(ms), 3),
            'liq_z': round(float(lq), 3),
            'cvd_slope': round(float(cs), 3)
        })
        
    df_reg = pd.DataFrame(records)
    print(df_reg.to_string(index=False))

if __name__ == "__main__":
    map_is_regimes()
