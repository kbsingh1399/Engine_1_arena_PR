---
type: indicator_contract
title: Cumulative Volume Delta (CVD) Auto-Anchor Protocol
domain: market_microstructure
version: 2.0.0
verified_against: Binance Futures (fapi) & CoinGlass Multi-Venue Baseline
tags: [cvd, orderflow, okf, auto-calibration]
---

# CVD Auto-Anchor & Cold-Start Protocol

## 1. Mathematical Definition
CVD is an unbounded relative accumulator:
$$CVD_t = CVD_0 + \sum_{i=1}^t (2 \times \text{TakerBuy}_i - \text{TotalVolume}_i)$$

## 2. Inception Alignment Problem
Because Binance does not offer a native historical cumulative delta endpoint across years, any cold-boot rolling window calculation (e.g. 1000 candles ~ 10 days) will have an initial scalar offset relative to multi-year platforms like CoinGlass.

## 3. Automated Dual-Mode Resolution
1. **Interactive / Manual Override**: `--cvd-offset <float>` explicitly overrides the offset and instantly updates `.okf/cvd_anchor.json`.
2. **Autonomous ML Cold-Start**: In headless / ML inference mode, `binance_live_monitor.py` reads `.okf/cvd_anchor.json` on boot, completely removing the need for manual human runtime input while preserving mathematical delta integrity.
