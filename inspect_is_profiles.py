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

def inspect():
    btc_file = os.path.join(DATA_DIR, "BTCUSDT_15m_master_2020_2026.parquet")
    df = pd.read_parquet(btc_file)
    df['datetime_utc'] = pd.to_datetime(df['datetime_utc'], utc=True)
    df = df.sort_values('datetime_utc').reset_index(drop=True)
    
    atr = (df['high'] - df['low']).rolling(14).mean()
    long_atr = atr.rolling(480).mean()
    df['vol_ratio'] = atr / (long_atr + 1e-8)
    
    ef = df['close'].ewm(span=200).mean()
    es = df['close'].ewm(span=800).mean()
    df['trend_str'] = (ef - es).abs() / (atr + 1e-8)
    df['macro_spread'] = (ef - es) / (atr + 1e-8)
    df['ret_30d'] = (df['close'] - df['close'].shift(96*30)) / (df['close'].shift(96*30) + 1e-8)
    
    long_liq = df['long_liq_usd'].fillna(0.0)
    short_liq = df['short_liq_usd'].fillna(0.0)
    total_liq = long_liq + short_liq
    df['liq_z'] = (total_liq - total_liq.rolling(96).mean()) / (total_liq.rolling(96).std() + 1e-8)
    
    spot_cvd = df.get('spot_cvd_15m', 0.0)
    fut_cvd = df.get('future_cvd_15m', 0.0)
    df['cvd_div'] = (spot_cvd - fut_cvd) / (df['close'] + 1e-8)
    df['cvd_slope'] = (spot_cvd - spot_cvd.shift(96*5)) / (spot_cvd.abs().rolling(96*5).mean() + 1e-8)
    
    for wi, (test_start_str, test_end_str) in enumerate(OOS_MONTHS):
        w_num = wi + 1
        test_start = pd.to_datetime(test_start_str, utc=True)
        train_end = test_start - pd.Timedelta(hours=3)
        sub = df[df['datetime_utc'] < train_end].iloc[-96*30:]
        
        vr = sub['vol_ratio'].mean()
        ts = sub['trend_str'].mean()
        ms = sub['macro_spread'].mean()
        r30 = sub['ret_30d'].iloc[-1] * 100
        lz = sub['liq_z'].mean()
        cs = sub['cvd_slope'].iloc[-1]
        
        print(f"W{w_num:02d} ({test_start_str}): Ret30d={r30:>6.1f}%, VolR={vr:.2f}, TrendStr={ts:.2f}, MacroSp={ms:>5.2f}, LiqZ={lz:>6.3f}, CVDSlope={cs:>5.2f}")

if __name__ == "__main__":
    inspect()
