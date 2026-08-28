import os
import glob
import pandas as pd
import numpy as np

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Engine_2", "binance_backtesting_data")

def inspect_w17():
    files = sorted(glob.glob(os.path.join(DATA_DIR, "*_15m_master_*.parquet")))
    test_start = pd.to_datetime("2025-03-15", utc=True)
    test_end = pd.to_datetime("2025-04-15", utc=True)
    
    print(f"{'Symbol':<10} | {'Start P':<10} | {'End P':<10} | {'Return %':<10} | {'High':<10} | {'Low':<10} | {'Range %':<10}")
    print("-" * 75)
    
    for f in files:
        sym = os.path.basename(f).split('_')[0]
        df = pd.read_parquet(f, columns=['datetime_utc', 'open', 'high', 'low', 'close', 'volume_quote'])
        df['datetime_utc'] = pd.to_datetime(df['datetime_utc'], utc=True)
        sub = df[(df['datetime_utc'] >= test_start) & (df['datetime_utc'] < test_end)]
        if not sub.empty:
            p0 = sub['open'].iloc[0]
            p1 = sub['close'].iloc[-1]
            ret = (p1 - p0) / p0 * 100
            hi = sub['high'].max()
            lo = sub['low'].min()
            rng = (hi - lo) / lo * 100
            print(f"{sym:<10} | {p0:<10.4f} | {p1:<10.4f} | {ret:>9.2f}% | {hi:<10.4f} | {lo:<10.4f} | {rng:>9.2f}%")

if __name__ == "__main__":
    inspect_w17()
