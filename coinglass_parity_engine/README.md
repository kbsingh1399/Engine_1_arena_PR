# CoinGlass Parity Engine & Historical Data Pipeline

High-performance market microstructure ingestor, mathematical parity engine, and historical data pipeline for Binance Futures (`BTCUSDT`, 15-minute timeframe).

---

## 📁 Directory Structure

```
coinglass_parity_engine/
├── core/                                # Shared mathematical models & schema contracts
│   ├── __init__.py
│   ├── schema.py                       # Canonical 28-indicator schema definition
│   ├── canonical_indicators.py         # Vector & streaming indicator math (EMA, RSI, ATR, CVD, Depth)
│   └── mathematical_liquidation_engine.py # Upgraded Non-Linear Cascade & Funding Asymmetry LMC Model
│
├── pipeline/                            # Bulk data ingestion & Parquet export
│   ├── __init__.py
│   ├── binance_historical_fetcher.py   # Multi-threaded Vision & REST archive downloader
│   ├── historical_metrics_processor.py # Indicator synthesis & data alignment
│   └── parquet_exporter.py             # Partitioned & master Parquet file exporter
│
├── verification/                        # Test suites & integrity verification
│   ├── verify_parquet_integrity.py     # Deep Parquet health & continuity checker
│   └── parity_comparator.py            # Ground truth CoinGlass parity validator
│
├── run_historical_pipeline.py           # Master CLI runner (2020 -> Present dump)
└── README.md
```

---

## 🚀 Running the Historical Pipeline (2020 -> Present)

To fetch and dump all data from 2020 onwards directly to Google Drive in Parquet format:

```bash
python coinglass_parity_engine/run_historical_pipeline.py --start-year 2020 --end-year 2026 --target-dir "G:\My Drive\_Trading_Data\Binance_Pipeline\15_Min" --workers 16
```

### Generated Files in Target Directory:
- `BTCUSDT_15m_2020.parquet`
- `BTCUSDT_15m_2021.parquet`
- `BTCUSDT_15m_2022.parquet`
- `BTCUSDT_15m_2023.parquet`
- `BTCUSDT_15m_2024.parquet`
- `BTCUSDT_15m_2025.parquet`
- `BTCUSDT_15m_2026.parquet`
- `BTCUSDT_15m_master_2020_2026.parquet`
- `dataset_manifest.json`

---

## 📊 Canonical 28 Indicators Schema

| # | Indicator Name | Column Name | Type | Description |
|---|---|---|---|---|
| 1 | Asset | `symbol` | string | Symbol identifier (`BTCUSDT`) |
| 2 | Close Price | `close` | float64 | 15m candle close price ($) |
| 3 | Volume USD (SMA 9) | `volume_sma9` | float64 | 9-period SMA of quote volume ($) |
| 3b | Volume BTC | `volume_base` | float64 | 15m candle base volume (BTC) |
| 4 | RSI (14) | `rsi_14` | float64 | 14-period Wilder RMA smoothed RSI |
| 5 | Fut CVD 15m Delta | `future_cvd_15m` | float64 | Futures Taker Buy - Taker Sell (BTC) |
| 5b | Fut CVD Session | `future_cvd_session` | float64 | Session cumulative Futures CVD (BTC) |
| 6 | Spot CVD 15m Delta | `spot_cvd_15m` | float64 | Spot Taker Buy - Taker Sell (BTC) |
| 6b | Spot CVD Session | `spot_cvd_session` | float64 | Session cumulative Spot CVD (BTC) |
| 7 | Funding Rate % | `funding_rate_pct` | float64 | 8-hour funding rate (%) |
| 8 | Open Interest (K) | `open_interest_k` | float64 | Open interest in thousands of contracts |
| 9 | Long Liquidations USD | `long_liq_usd` | float64 | Long liquidations in USD (Negative polarity) |
| 10 | Short Liquidations USD | `short_liq_usd` | float64 | Short liquidations in USD (Positive polarity) |
| 11 | L/S Global Accounts | `ls_ratio_global` | float64 | Global accounts Long/Short ratio |
| 11b | L/S Top Trader | `ls_ratio_top` | float64 | Top trader positions Long/Short ratio |
| 12 | Footprint Delta BTC | `fp_delta` | float64 | Footprint net volume delta (BTC) |
| 13 | Footprint POC | `fp_poc` | float64 | Footprint Point of Control price ($) |
| 14 | Bid Dollar Depth | `bid_depth_usd` | float64 | Resting bid liquidity (+1%) in USD |
| 15 | Ask Dollar Depth | `ask_depth_usd` | float64 | Resting ask liquidity (-1%) in USD (Negative) |
| 16 | Bid Coin Depth | `bid_depth_coin` | float64 | Resting bid liquidity (+1%) in BTC |
| 17 | Ask Coin Depth | `ask_depth_coin` | float64 | Resting ask liquidity (-1%) in BTC (Negative) |
| 18 | Whale Index | `whale_index` | float64 | Top trader ratio * 100 |
| 19 | Taker Buy Count | `taker_buy_count` | int64 | Number of aggressive taker buy trades |
| 20 | Taker Sell Count | `taker_sell_count` | int64 | Number of aggressive taker sell trades (Negative) |
| 21 | EMA 8 | `ema_8` | float64 | 8-period Exponential Moving Average ($) |
| 22 | EMA 21 | `ema_21` | float64 | 21-period Exponential Moving Average ($) |
| 23 | EMA 50 | `ema_50` | float64 | 50-period Exponential Moving Average ($) |
| 24 | EMA 200 | `ema_200` | float64 | 200-period Exponential Moving Average ($) |
| 25 | EMA 800 | `ema_800` | float64 | 800-period Exponential Moving Average ($) |
| 26 | ATR 14 | `atr_14` | float64 | 14-period Wilder Average True Range ($) |
| 27 | ATR 100 | `atr_100` | float64 | 100-period Wilder Average True Range ($) |
| 28 | Basis | `basis_usd` | float64 | Futures Mark Price - Spot Index Price Spread ($) |

---

## ⚡ Real-Time Alignment with `binance_live_monitor.py`

The historical Parquet schema matches `binance_live_monitor.py` 1:1, allowing direct concatenation of live feature snapshots onto historical Parquet archives without schema migration.
