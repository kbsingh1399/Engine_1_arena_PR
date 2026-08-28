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

target_archetypes = {
    1: ("A6_SpotAbsorptionDiv", 0.56, 30.0, 180.0, 75.0),
    2: ("A1_VolBreakout", 0.50, 30.0, 240.0, 90.0),
    3: ("A5_PureRelativeCVD", 0.50, 120.0, 200.0, 60.0),
    4: ("A1_VolBreakout", 0.48, 30.0, 220.0, 90.0),
    5: ("A8_LiqExtreme", 0.48, 30.0, 220.0, 90.0),
    6: ("A1_VolBreakout", 0.50, 30.0, 220.0, 90.0),
    7: ("A1_VolBreakout", 0.44, 30.0, 220.0, 90.0),
    8: ("A2_DeepSqueeze", 0.52, 30.0, 180.0, 90.0),
    9: ("N2_LiqCascadeFlush", 0.50, 30.0, 200.0, 50.0),
    10: ("A1_VolBreakout", 0.50, 30.0, 200.0, 90.0),
    11: ("A5_PureRelativeCVD", 0.52, 50.0, 180.0, 60.0),
    12: ("A5_PureRelativeCVD", 0.54, 30.0, 180.0, 75.0),
    13: ("N4_SpotDeltaCont", 0.48, 30.0, 240.0, 90.0),
    14: ("A5_PureRelativeCVD", 0.54, 50.0, 220.0, 75.0),
    15: ("N7_VolExpMom", 0.48, 30.0, 180.0, 90.0),
    16: ("A4_UltraDeepValue", 0.44, 30.0, 180.0, 90.0),
    17: ("T2_BearRallyShort", 0.46, 100.0, 200.0, 90.0),
    18: ("N2_LiqCascadeFlush", 0.48, 100.0, 220.0, 50.0),
    19: ("A2_DeepSqueeze", 0.44, 30.0, 240.0, 50.0),
    20: ("A7_ModPullback", 0.44, 50.0, 180.0, 50.0)
}

def analyze_and_build_router():
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
    df['cvd_slope'] = (spot_cvd - spot_cvd.shift(96*5)) / (spot_cvd.abs().rolling(96*5).mean() + 1e-8)
    
    rows = []
    for wi, (test_start_str, test_end_str) in enumerate(OOS_MONTHS):
        w_num = wi + 1
        test_start = pd.to_datetime(test_start_str, utc=True)
        train_end = test_start - pd.Timedelta(hours=3)
        sub = df[df['datetime_utc'] < train_end].iloc[-96*30:]
        
        vr = float(sub['vol_ratio'].mean())
        ts = float(sub['trend_str'].mean())
        ms = float(sub['macro_spread'].mean())
        r30 = float(sub['ret_30d'].iloc[-1]) * 100.0
        lz = float(sub['liq_z'].mean())
        cs = float(sub['cvd_slope'].iloc[-1])
        
        arch, th, ht, hr, br = target_archetypes[w_num]
        
        rows.append({
            'window': w_num, 'start': test_start_str,
            'ret30': r30, 'volr': vr, 'trend_str': ts, 'macro_sp': ms, 'liq_z': lz, 'cvd_slope': cs,
            'archetype': arch, 'th': th, 'ht': ht, 'hr': hr, 'br': br
        })
        
    df_meta = pd.DataFrame(rows)
    print(df_meta[['window', 'start', 'ret30', 'volr', 'trend_str', 'macro_sp', 'liq_z', 'cvd_slope', 'archetype', 'th']].to_string(index=False))

if __name__ == "__main__":
    analyze_and_build_router()
