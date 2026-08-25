"""
Direct Parquet Seed Verification for Matrix Mode
Tests the bootstrap_matrix_symbol parquet loading logic in isolation
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone

# Load parquet
df = pd.read_parquet(r'G:\My Drive\_Trading_Data\Binance_Pipeline\15_Min\BTCUSDT_15m_master_2020_2026.parquet')
last_row = df.iloc[-1]

print("=" * 100)
print("PARQUET LAST ROW (14:30 UTC) vs MATRIX MODE BOOTSTRAP LOADING")
print("=" * 100)

# What bootstrap_matrix_symbol loads from parquet (lines 2733-2747)
# Note: bootstrap uses different key names than parquet columns
loaded = {
    'ema_8': float(last_row.get("ema_8", 0.0)),
    'ema_21': float(last_row.get("ema_21", 0.0)),
    'ema_50': float(last_row.get("ema_50", 0.0)),
    'ema_200': float(last_row.get("ema_200", 0.0)),
    'ema_800': float(last_row.get("ema_800", 0.0)),
    'rsi_14': float(last_row.get("rsi_14", 50.0)),
    'atr_14': float(last_row.get("atr_14", 0.0)),
    'atr_100': float(last_row.get("atr_100", 0.0)),
    'vol_sma9': float(last_row.get("volume_sma9", 0.0)),
    'fut_cvd_session': float(last_row.get("future_cvd_session", 0.0)),
    'spot_cvd_session': float(last_row.get("spot_cvd_session", 0.0)),
    'prev_day_vah': float(last_row.get("prev_day_vah", 0.0)),
    'prev_day_val': float(last_row.get("prev_day_val", 0.0)),
    'session_vah': float(last_row.get("session_vah", 0.0)),
    'session_val': float(last_row.get("session_val", 0.0)),
}

# Parquet column mapping
parquet_map = {
    'ema_8': 'ema_8',
    'ema_21': 'ema_21',
    'ema_50': 'ema_50',
    'ema_200': 'ema_200',
    'ema_800': 'ema_800',
    'rsi_14': 'rsi_14',
    'atr_14': 'atr_14',
    'atr_100': 'atr_100',
    'vol_sma9': 'volume_sma9',
    'fut_cvd_session': 'future_cvd_session',
    'spot_cvd_session': 'spot_cvd_session',
    'prev_day_vah': 'prev_day_vah',
    'prev_day_val': 'prev_day_val',
    'session_vah': 'session_vah',
    'session_val': 'session_val',
}

print("\nValues loaded from parquet by bootstrap_matrix_symbol:")
for k, v in loaded.items():
    print(f"  {k:20s}: {v:>15,.4f}")

print("\nParquet actual values:")
for k in loaded.keys():
    val = last_row[parquet_map[k]]
    print(f"  {k:20s}: {val:>15,.4f}")

print("\nMatch check:")
all_match = True
for k in loaded.keys():
    parquet_val = last_row[parquet_map[k]]
    loaded_val = loaded[k]
    diff = abs(parquet_val - loaded_val)
    match = "OK" if diff < 0.01 else "FAIL"
    if diff >= 0.01:
        all_match = False
    print(f"  {k:20s}: parquet={parquet_val:>12,.4f} loaded={loaded_val:>12,.4f} diff={diff:.6f} {match}")

print(f"\nAll match: {all_match}")

# Now check what's NOT loaded but should be
print("\n" + "=" * 100)
print("MISSING FROM PARQUET LOAD (should be added to bootstrap_matrix_symbol)")
print("=" * 100)

missing = {
    'future_cvd_lifetime': last_row.get('future_cvd_lifetime', 0.0),
    'spot_cvd_lifetime': last_row.get('spot_cvd_lifetime', 0.0),
    'fp_poc': last_row.get('fp_poc', 0.0),
    'fp_delta': last_row.get('fp_delta', 0.0),
    'taker_buy_vol_btc': last_row.get('taker_buy_vol_btc', 0.0),
    'taker_sell_vol_btc': last_row.get('taker_sell_vol_btc', 0.0),
    'taker_buy_count': last_row.get('taker_buy_count', 0),
    'taker_sell_count': last_row.get('taker_sell_count', 0),
    'max_trade_vol_btc': last_row.get('max_trade_vol_btc', 0.0),
    'avg_trade_size_usd': last_row.get('avg_trade_size_usd', 0.0),
    'bid_depth_usd': last_row.get('bid_depth_usd', 0.0),
    'ask_depth_usd': last_row.get('ask_depth_usd', 0.0),
    'bid_depth_coin': last_row.get('bid_depth_coin', 0.0),
    'ask_depth_coin': last_row.get('ask_depth_coin', 0.0),
    'open_interest_k': last_row.get('open_interest_k', 0.0),
    'open_interest_usd': last_row.get('open_interest_usd', 0.0),
    'oi_change_pct': last_row.get('oi_change_pct', 0.0),
    'ls_ratio_global': last_row.get('ls_ratio_global', 0.0),
    'ls_ratio_top': last_row.get('ls_ratio_top', 0.0),
    'top_account_ratio': last_row.get('top_account_ratio', 0.0),
    'whale_index': last_row.get('whale_index', 0.0),
    'taker_volume_ratio': last_row.get('taker_volume_ratio', 0.0),
    'funding_rate_pct': last_row.get('funding_rate_pct', 0.0),
    'basis_usd': last_row.get('basis_usd', 0.0),
    'long_liq_usd': last_row.get('long_liq_usd', 0.0),
    'short_liq_usd': last_row.get('short_liq_usd', 0.0),
}

for k, v in missing.items():
    if isinstance(v, float):
        if abs(v) >= 1e6:
            print(f"  {k:25s}: {v:>15,.0f} ({v/1e6:.2f}M)")
        elif abs(v) >= 1e3:
            print(f"  {k:25s}: {v:>15,.2f} ({v/1e3:.2f}K)")
        else:
            print(f"  {k:25s}: {v:>15,.4f}")
    else:
        print(f"  {k:25s}: {v}")

# Check the single-symbol mode KL_STATE seed
print("\n" + "=" * 100)
print("SINGLE-SYMBOL MODE: start_kline_stream parquet loading (lines 1504-1528)")
print("=" * 100)
print("Loads last 100 bars from parquet + catchup REST bars")
print("Seeds KL_STATE only (EMAs, RSI, ATR, Volume via incremental computation)")
print("Does NOT seed: AGG_STATE (CVD), SPOT_AGG, MARK_PRICE, REST_CACHE, LIQ_STATE")
print("Does NOT load: Lifetime CVD, Session Profile, Depth, Liquidations")

# Verify KL_STATE.seed_from_rest computes correct EMAs from 100-bar tail
print("\nKL_STATE.seed_from_rest computes EMAs incrementally from provided klines")
print("If given 100 parquet bars + catchup bars, EMAs should converge correctly")
print("But CVD lifetime is computed as sum(2*taker_buy - volume) over provided bars only")
print("This gives ~100-bar CVD, not lifetime from 2020")

# Compute what 100-bar CVD would be
tail_100 = df.tail(100)
cvd_100 = (2 * tail_100['taker_buy_vol_btc'] - tail_100['volume_base']).sum()
print(f"\n100-bar CVD (what single mode would compute): {cvd_100:.2f} BTC")
print(f"Parquet lifetime CVD: {last_row['future_cvd_lifetime']:.2f} BTC")
print(f"Difference: {last_row['future_cvd_lifetime'] - cvd_100:.2f} BTC")