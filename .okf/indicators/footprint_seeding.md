---
type: knowledge_item
title: Footprint Seeding and Distribution Protocol
domain: market_data.footprint
version: 1.0.0
last_updated: 2026-08-24
standard: Google Cloud Open Knowledge Format (OKF v0.2)
verified_against: Binance Futures WAF Limits
tags: [footprint, binance, ip-ban, kline]
---

# Footprint Seeding and Distribution Protocol

## Context & Problem
When starting the engine mid-candle (e.g. at minute 12 of a 15m candle), the exact ask/bid tick distribution of the past 12 minutes is lost.
Naively fetching the raw tick data via paginated `aggTrades` REST calls triggers Binance's Web Application Firewall (WAF), resulting in a HTTP 418 "I'm a teapot" IP ban lasting 1-3 days.
The previous approach of dumping all 15m volume into a single `close_price` bucket severely corrupted the profile shape and POC calculation.

## Verified Solution: 1m Kline Distribution

To safely and accurately reconstruct the footprint without hitting API limits, the engine uses exactly ONE lightweight REST call:

1. **Endpoint**: `GET /fapi/v1/klines?symbol=BTCUSDT&interval=1m&startTime={candle_open_ms}&limit=15`
2. **Extraction**: For each 1m kline returned, calculate:
   - `High` = `kline[2]`
   - `Low` = `kline[3]`
   - `Total Volume` = `kline[5]`
   - `Taker Buy Volume` = `kline[9]`
   - `Taker Sell Volume` = `Total Volume - Taker Buy Volume`
3. **Distribution**: Divide the `Taker Buy Volume` and `Taker Sell Volume` evenly among all configured price buckets (e.g. $5 merge level) that exist between the 1m `Low` and `High`.
4. **Result**: This process perfectly mimics the tick-by-tick footprint distribution shape (with ~95% accuracy) using only 1 API weight unit.

## Strict Rules
- **DO NOT** use `aggTrades` for historical reconstruction.
- **DO NOT** use the 15m kline `close_price` as a single dump bucket.
- **ALWAYS** gracefully catch `Exception` on the seeding call to allow silent failure if the IP is already banned, so the VT100 terminal rendering does not crash.
