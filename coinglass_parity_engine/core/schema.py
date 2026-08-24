"""
================================================================================
CANONICAL MARKET DATA SCHEMA & COLUMN SPECIFICATIONS
================================================================================
Unified 28-indicator schema contract for both:
  1. Historical Parquet Data Pipeline (2020 -> Present)
  2. Real-Time Binance Live Streaming Monitor (binance_live_monitor.py)
================================================================================
"""

from typing import List, Dict, Any

# Canonical 28 Indicator Column Definitions with Data Types & Description
CANONICAL_COLUMNS: List[str] = [
    # 1. Timestamps & Identification
    "open_time_ms",           # int64: Candle open Unix timestamp in milliseconds
    "close_time_ms",          # int64: Candle close Unix timestamp in milliseconds
    "datetime_utc",           # string / timestamp: Human-readable UTC timestamp (YYYY-MM-DD HH:MM:SS)
    "symbol",                 # string: Asset pair symbol (e.g. BTCUSDT)
    
    # 2. OHLCV Core Price & Volume
    "open",                   # float64: Open price in USD
    "high",                   # float64: Highest price in USD
    "low",                    # float64: Lowest price in USD
    "close",                  # float64: Close price in USD (Indicator 2. CLOSE PRICE)
    "volume_base",            # float64: Base volume in BTC (Indicator 3b. VOLUME BTC)
    "volume_quote",           # float64: Quote volume in USD
    "volume_sma9",            # float64: 9-period SMA of Quote Volume in USD (Indicator 3. VOLUME USD SMA 9)
    "trade_count",            # int64: Total number of trades executed in 15m candle
    
    # 3. Technical Momentum & Volatility Indicators
    "rsi_14",                 # float64: 14-period Wilder RMA smoothed RSI (Indicator 4. RSI 14)
    "atr_14",                 # float64: 14-period Wilder RMA Average True Range in USD (Indicator 26. ATR 14)
    "atr_100",                # float64: 100-period Wilder RMA Average True Range in USD (Indicator 27. ATR 100)
    
    # 4. Exponential Moving Averages (Seeded from Bar 0)
    "ema_8",                  # float64: 8-period EMA (Indicator 21. EMA 8)
    "ema_21",                 # float64: 21-period EMA (Indicator 22. EMA 21)
    "ema_50",                 # float64: 50-period EMA (Indicator 23. EMA 50)
    "ema_200",                # float64: 200-period EMA (Indicator 24. EMA 200)
    "ema_800",                # float64: 800-period EMA (Indicator 25. EMA 800)
    
    # 5. Cumulative Volume Delta (CVD) & Flow
    "future_cvd_15m",         # float64: Futures Taker Buy - Taker Sell Volume in BTC (Indicator 5. FUT CVD 15m)
    "future_cvd_session",     # float64: Cumulative running Futures CVD in BTC (Indicator 5b. FUT CVD SESSION)
    "future_cvd_lifetime",    # float64: Lifetime Cumulative running Futures CVD in BTC
    "spot_cvd_15m",           # float64: Spot Taker Buy - Taker Sell Volume in BTC (Indicator 6. SPOT CVD 15m)
    "spot_cvd_session",       # float64: Cumulative running Spot CVD in BTC (Indicator 6b. SPOT CVD SESSION)
    "spot_cvd_lifetime",      # float64: Lifetime Cumulative running Spot CVD in BTC
    
    # 6. Rates, Basis, and Open Interest
    "funding_rate_pct",       # float64: 8-hour funding rate in percent (e.g. 0.0100) (Indicator 7. FUNDING RATE %)
    "basis_usd",              # float64: Futures Mark Price - Spot Index Price Spread in USD (Indicator 28. BASIS)
    "open_interest_k",        # float64: Open Interest in thousands of BTC contracts (Indicator 8. OPEN INT K)
    "open_interest_usd",      # float64: Open Interest value in USD
    
    # 7. Liquidations (Mathematical LMC Engine)
    "long_liq_usd",           # float64: Long liquidation dollar volume in USD (Negative polarity, Indicator 9. LONG LIQ)
    "short_liq_usd",          # float64: Short liquidation dollar volume in USD (Positive polarity, Indicator 10. SHORT LIQ)
    
    # 8. Crowd Positioning & Whale Metrics
    "ls_ratio_global",        # float64: Global Accounts Long/Short Ratio (Indicator 11. L/S GLOBAL)
    "ls_ratio_top",           # float64: Top Trader Long/Short Position Ratio (Indicator 11b. L/S TOP)
    "whale_index",            # float64: CoinGlass Whale Index = Top Trader Ratio * 100 (Indicator 18. WHALE IDX)
    
    # 9. Order Flow Footprint & Microstructure
    "fp_delta",               # float64: Footprint Net Delta in BTC (Indicator 12. FOOTPRINT DELTA)
    "fp_poc",                 # float64: Footprint Point of Control Price in USD (Indicator 13. FOOTPRINT POC)
    "taker_buy_count",        # int64: Taker aggressive buy trade count (Indicator 19. TAKER BUY COUNT)
    "taker_sell_count",       # int64: Taker aggressive sell trade count (Negative polarity, Indicator 20. TAKER SELL)
    "taker_buy_vol_btc",      # float64: Taker aggressive buy volume in BTC
    "taker_sell_vol_btc",     # float64: Taker aggressive sell volume in BTC
    
    # 10. Order Book Resting Depth (+-1% around Mid Price)
    "bid_depth_usd",          # float64: Resting Bid liquidity in USD within +1% (Indicator 14. BID DOLLAR DEPTH)
    "ask_depth_usd",          # float64: Resting Ask liquidity in USD within -1% (Negative, Indicator 15. ASK DOLLAR DEPTH)
    "bid_depth_coin",         # float64: Resting Bid liquidity in BTC within +1% (Indicator 16. BID COIN DEPTH)
    "ask_depth_coin",         # float64: Resting Ask liquidity in BTC within -1% (Negative, Indicator 17. ASK COIN DEPTH)
    
    # 11. Feature Provenance Metadata
    "future_flow_source",     # string: TICK_EXACT or KLINE_APPROX
    "spot_flow_source",       # string: SPOT_EXACT or UNAVAILABLE
    "poc_source",             # string: TICK_EXACT or OHLC_APPROX
]

COLUMN_DTYPES: Dict[str, str] = {
    "open_time_ms": "int64",
    "close_time_ms": "int64",
    "datetime_utc": "string",
    "symbol": "string",
    "future_flow_source": "string",
    "spot_flow_source": "string",
    "poc_source": "string",
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "volume_base": "float64",
    "volume_quote": "float64",
    "volume_sma9": "float64",
    "trade_count": "int64",
    "rsi_14": "float64",
    "atr_14": "float64",
    "atr_100": "float64",
    "ema_8": "float64",
    "ema_21": "float64",
    "ema_50": "float64",
    "ema_200": "float64",
    "ema_800": "float64",
    "future_cvd_15m": "float64",
    "future_cvd_session": "float64",
    "future_cvd_lifetime": "float64",
    "spot_cvd_15m": "float64",
    "spot_cvd_session": "float64",
    "spot_cvd_lifetime": "float64",
    "funding_rate_pct": "float64",
    "basis_usd": "float64",
    "open_interest_k": "float64",
    "open_interest_usd": "float64",
    "long_liq_usd": "float64",
    "short_liq_usd": "float64",
    "ls_ratio_global": "float64",
    "ls_ratio_top": "float64",
    "whale_index": "float64",
    "fp_delta": "float64",
    "fp_poc": "float64",
    "taker_buy_count": "int64",
    "taker_sell_count": "int64",
    "taker_buy_vol_btc": "float64",
    "taker_sell_vol_btc": "float64",
    "bid_depth_usd": "float64",
    "ask_depth_usd": "float64",
    "bid_depth_coin": "float64",
    "ask_depth_coin": "float64",
}
