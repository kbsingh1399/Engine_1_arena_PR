import pandas as pd
from datetime import datetime, timezone

# Load the master parquet - get the EXACT last completed candle (14:30 UTC)
df = pd.read_parquet(r'G:\My Drive\_Trading_Data\Binance_Pipeline\15_Min\BTCUSDT_15m_master_2020_2026.parquet')
last = df.iloc[-1]
ts = int(last['open_time_ms'])
dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)

print('=' * 80)
print('GROUND TRUTH FROM PARQUET (Last Completed Candle: 2026-08-25 14:30 UTC)')
print('=' * 80)
print('Timestamp: {} UTC ({})'.format(dt, ts))
print()
print('PRICE & VOLUME:')
print('  close:              {:.2f}'.format(last['close']))
print('  volume_quote:       {:,.0f} USD ({:.2f}M)'.format(last['volume_quote'], last['volume_quote']/1e6))
print('  volume_base:        {:,.2f} BTC'.format(last['volume_base']))
print('  volume_sma9:        {:,.0f} USD ({:.2f}M)'.format(last['volume_sma9'], last['volume_sma9']/1e6))
print('  trade_count:        {:,.0f}'.format(last['trade_count']))
print()
print('TECHNICAL INDICATORS:')
print('  ema_8:              {:.2f}'.format(last['ema_8']))
print('  ema_21:             {:.2f}'.format(last['ema_21']))
print('  ema_50:             {:.2f}'.format(last['ema_50']))
print('  ema_200:            {:.2f}'.format(last['ema_200']))
print('  ema_800:            {:.2f}'.format(last['ema_800']))
print('  rsi_14:             {:.2f}'.format(last['rsi_14']))
print('  atr_14:             {:.2f}'.format(last['atr_14']))
print('  atr_100:            {:.2f}'.format(last['atr_100']))
print()
print('CVD & FLOW:')
print('  future_cvd_15m:     {:.2f} BTC'.format(last['future_cvd_15m']))
print('  future_cvd_session: {:.2f} BTC'.format(last['future_cvd_session']))
print('  future_cvd_lifetime:{:.2f} BTC'.format(last['future_cvd_lifetime']))
print('  spot_cvd_15m:       {:.2f} BTC'.format(last['spot_cvd_15m']))
print('  spot_cvd_session:   {:.2f} BTC'.format(last['spot_cvd_session']))
print('  spot_cvd_lifetime:  {:.2f} BTC'.format(last['spot_cvd_lifetime']))
print('  fp_delta:           {:.2f} BTC'.format(last['fp_delta']))
print('  fp_poc:             {:.2f} USD'.format(last['fp_poc']))
print()
print('POSITIONING & FUNDING:')
print('  funding_rate_pct:   {:.6f}%'.format(last['funding_rate_pct']))
print('  basis_usd:          {:.2f} USD'.format(last['basis_usd']))
print('  open_interest_k:    {:.3f}K BTC'.format(last['open_interest_k']))
print('  open_interest_usd:  {:,.0f} USD'.format(last['open_interest_usd']))
print('  oi_change_pct:      {:.4f}%'.format(last['oi_change_pct']))
print('  ls_ratio_global:    {:.4f}'.format(last['ls_ratio_global']))
print('  ls_ratio_top:       {:.4f}'.format(last['ls_ratio_top']))
print('  top_account_ratio:  {:.4f}'.format(last['top_account_ratio']))
print('  whale_index:        {:.2f}'.format(last['whale_index']))
print('  taker_volume_ratio: {:.4f}'.format(last['taker_volume_ratio']))
print()
print('LIQUIDATIONS:')
print('  long_liq_usd:       {:,.2f} USD'.format(last['long_liq_usd']))
print('  short_liq_usd:      {:,.2f} USD'.format(last['short_liq_usd']))
print()
print('VALUE AREA:')
print('  session_vah:        {:.1f} USD'.format(last['session_vah']))
print('  session_val:        {:.1f} USD'.format(last['session_val']))
print('  prev_day_vah:       {:.1f} USD'.format(last['prev_day_vah']))
print('  prev_day_val:       {:.1f} USD'.format(last['prev_day_val']))
print()
print('DEPTH:')
print('  bid_depth_usd:      {:,.0f} USD'.format(last['bid_depth_usd']))
print('  ask_depth_usd:      {:,.0f} USD'.format(last['ask_depth_usd']))
print('  bid_depth_coin:     {:.2f} BTC'.format(last['bid_depth_coin']))
print('  ask_depth_coin:     {:.2f} BTC'.format(last['ask_depth_coin']))
print()
print('MICROSTRUCTURE:')
print('  taker_buy_count:    {:,.0f}'.format(last['taker_buy_count']))
print('  taker_sell_count:   {:,.0f}'.format(last['taker_sell_count']))
print('  taker_buy_vol_btc:  {:.3f} BTC'.format(last['taker_buy_vol_btc']))
print('  taker_sell_vol_btc: {:.3f} BTC'.format(last['taker_sell_vol_btc']))
print('  max_trade_vol_btc:  {:.4f} BTC'.format(last['max_trade_vol_btc']))
print('  avg_trade_size_usd: {:.2f} USD'.format(last['avg_trade_size_usd']))

# Also save as dict for comparison
import json
ground_truth = {
    'timestamp': ts,
    'close': last['close'],
    'volume_quote': last['volume_quote'],
    'volume_base': last['volume_base'],
    'volume_sma9': last['volume_sma9'],
    'trade_count': last['trade_count'],
    'ema_8': last['ema_8'],
    'ema_21': last['ema_21'],
    'ema_50': last['ema_50'],
    'ema_200': last['ema_200'],
    'ema_800': last['ema_800'],
    'rsi_14': last['rsi_14'],
    'atr_14': last['atr_14'],
    'atr_100': last['atr_100'],
    'future_cvd_15m': last['future_cvd_15m'],
    'future_cvd_session': last['future_cvd_session'],
    'future_cvd_lifetime': last['future_cvd_lifetime'],
    'spot_cvd_15m': last['spot_cvd_15m'],
    'spot_cvd_session': last['spot_cvd_session'],
    'spot_cvd_lifetime': last['spot_cvd_lifetime'],
    'fp_delta': last['fp_delta'],
    'fp_poc': last['fp_poc'],
    'funding_rate_pct': last['funding_rate_pct'],
    'basis_usd': last['basis_usd'],
    'open_interest_k': last['open_interest_k'],
    'open_interest_usd': last['open_interest_usd'],
    'oi_change_pct': last['oi_change_pct'],
    'ls_ratio_global': last['ls_ratio_global'],
    'ls_ratio_top': last['ls_ratio_top'],
    'top_account_ratio': last['top_account_ratio'],
    'whale_index': last['whale_index'],
    'taker_volume_ratio': last['taker_volume_ratio'],
    'long_liq_usd': last['long_liq_usd'],
    'short_liq_usd': last['short_liq_usd'],
    'session_vah': last['session_vah'],
    'session_val': last['session_val'],
    'prev_day_vah': last['prev_day_vah'],
    'prev_day_val': last['prev_day_val'],
    'bid_depth_usd': last['bid_depth_usd'],
    'ask_depth_usd': last['ask_depth_usd'],
    'bid_depth_coin': last['bid_depth_coin'],
    'ask_depth_coin': last['ask_depth_coin'],
    'taker_buy_count': last['taker_buy_count'],
    'taker_sell_count': last['taker_sell_count'],
    'taker_buy_vol_btc': last['taker_buy_vol_btc'],
    'taker_sell_vol_btc': last['taker_sell_vol_btc'],
    'max_trade_vol_btc': last['max_trade_vol_btc'],
    'avg_trade_size_usd': last['avg_trade_size_usd'],
}

with open('ground_truth.json', 'w') as f:
    json.dump(ground_truth, f, indent=2)

print('\nSaved ground_truth.json for comparison')