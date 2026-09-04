---
type: knowledge_item
title: 15-Minute Candle Rollover Edge Case Protocol
domain: market_data.lifecycle
version: 1.0.0
last_updated: 2026-08-24
verified_against: High-Frequency Boundary Capture (task-4157)
tags: [candle, rollover, lifecycle, volume_reset, taker_reset]
---

# 15-Minute Candle Rollover Protocol

## 1. Boundary Trigger Mechanism
Binance 15-minute candles begin strictly at Unix epoch millisecond boundaries where $\text{ts} \pmod{900\,000} = 0$ (e.g. 14:00:00, 14:15:00, 14:30:00, 14:45:00).

$$\text{now\_cts} = \left(\left\lfloor \frac{\text{current\_time\_ms}}{900\,000} \right\rfloor\right) \times 900\,000$$

## 2. Instant Zero-Reset Rule
At the exact transition $T = 0\text{s}$ ($\text{now\_cts} \neq \text{kline\_start\_ts}$):
- **15m Bar Volume**: Evaluates to `$0.000M` ($0.00\text{ BTC}$).
- **Taker Buy / Taker Sell**: Evaluates to `0 / 0` trades.
- **Footprint Delta**: Evaluates to `+0.0000 BTC`.

## 3. Session Continuity Preservation
The following metrics MUST NOT reset to zero and must maintain 100% mathematical continuity across the candle boundary:
- **Session CVD (Futures & Spot)**
- **EMAs (8, 21, 50, 200, 800)**
- **ATRs (14, 100)**
- **Order Book Depth (Bids & Asks)**
- **Open Interest & Funding Rate**
