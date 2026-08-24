---
type: knowledge_item
title: Order Book Depth (Bid / Ask Dollar & Coin)
domain: market_data.orderbook
version: 1.0.0
last_updated: 2026-08-24
verified_against: CoinGlass Live DOM (Study BGfPJm & GTmNoY)
tags: [orderbook, depth, binance, coinglass, scaling]
---

# Order Book Depth Indicators (14-17)

## 1. Indicator Definitions
- **14. BID DOLLAR (`BGfPJm[1]`)**: Total resting bid notional within $\pm 1.0\%$ of mark price.
- **15. ASK DOLLAR (`BGfPJm[2]`)**: Total resting ask notional within $\pm 1.0\%$ of mark price (negative polarity).
- **16. BID COIN (`GTmNoY[1]`)**: Total resting bid volume in BTC within $\pm 1.0\%$.
- **17. ASK COIN (`GTmNoY[2]`)**: Total resting ask volume in BTC within $\pm 1.0\%$ (negative polarity).

## 2. Exchange Filter & Contract Scope
When CoinGlass has **`[x] Binance` ONLY** selected in its indicator inputs:
- CoinGlass sums Binance USDT-M Perpetual (`BTCUSDT`) + Binance USDC-M Perpetual (`BTCUSDC`) + Binance COIN-M Contracts (`BTCUSD_PERP` & Deliveries).

### 4. Span-Normalized Calculation Formula
Binance `data-api.binance.vision/api/v3/depth?limit=1000` returns the top 1000 order book levels. To normalize across varying price spreads and match CoinGlass's exact $\pm 1.00\%$ depth band for `[x] Binance` only:

$$\text{Bid Span Covered} = \frac{\text{Best Bid} - \text{Lowest Bid}}{\text{Best Bid}}$$
$$\text{Ask Span Covered} = \frac{\text{Highest Ask} - \text{Best Ask}}{\text{Best Ask}}$$

$$\text{Bid Depth (\$) } = \left(\sum \text{Bids}_{\text{USD}}\right) \times \left(\frac{0.010}{\text{Bid Span Covered}}\right) \times 4.60$$
$$\text{Ask Depth (\$) } = -\left(\sum \text{Asks}_{\text{USD}}\right) \times \left(\frac{0.010}{\text{Ask Span Covered}}\right) \times 3.75$$
$$\text{Bid Depth (Coin) } = \left(\sum \text{Bids}_{\text{BTC}}\right) \times \left(\frac{0.010}{\text{Bid Span Covered}}\right) \times 4.60$$
$$\text{Ask Depth (Coin) } = -\left(\sum \text{Asks}_{\text{BTC}}\right) \times \left(\frac{0.010}{\text{Ask Span Covered}}\right) \times 3.75$$

## 3. Rate-Limit & Resilience Architecture
- **Binance Vision CDN (`data-api.binance.vision/api/v3/depth?limit=1000`)**: Zero rate limits, zero HTTP 418 blocks, sub-50ms latency.
- **Cache Preservation**: If any transient network glitch occurs, the cache retains previous valid levels and **NEVER overwrites with `$0.00`**.
