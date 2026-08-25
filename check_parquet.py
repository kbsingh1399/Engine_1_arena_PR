import pandas as pd
from datetime import datetime, timezone

# Check what candles exist in parquet after 14:30
df = pd.read_parquet(r'G:\My Drive\_Trading_Data\Binance_Pipeline\15_Min\BTCUSDT_15m_master_2020_2026.parquet')
print('Parquet date range:')
print('  First:', datetime.fromtimestamp(df.iloc[0]['open_time_ms']/1000, tz=timezone.utc))
print('  Last:', datetime.fromtimestamp(df.iloc[-1]['open_time_ms']/1000, tz=timezone.utc))
print('  Total candles:', len(df))

# Check last 10 candles
print()
print('Last 10 candles:')
for i in range(-10, 0):
    row = df.iloc[i]
    ts = row['open_time_ms']
    dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
    print('  {} UTC | close={:.1f} | vol={:.1f}M'.format(dt, row['close'], row['volume_quote']/1e6))