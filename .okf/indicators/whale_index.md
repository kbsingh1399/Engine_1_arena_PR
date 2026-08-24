---
type: indicator_contract
title: Whale Index Mathematical Parity Contract
domain: microstructure
version: 1.0.0
verified_against: coinglass_live_tv
tags: [whale_index, top_traders, long_short_ratio, formula]
---

# Whale Index Mathematical Specification

## 1. Provenance & Formula
CoinGlass calculates the **Whale Index** directly from Binance Futures Top Trader Long/Short Account/Position Ratio:

$$\text{Whale Index} = (\text{TopTrader\_LS\_Ratio} - 1.0000) \times 100$$

### Interpretation
- A Top Trader Ratio of `1.89375` yields a Whale Index of `+89.3750`.
- A Top Trader Ratio of `1.00000` (neutral parity) yields a Whale Index of `0.0000`.
- A Top Trader Ratio of `0.85000` yields a Whale Index of `-15.0000`.

## 2. API Source
- Endpoint: `https://fapi.binance.com/futures/data/topLongShortPositionRatio?symbol=BTCUSDT&period=15m`
- Mapping: Field `longShortRatio`.
