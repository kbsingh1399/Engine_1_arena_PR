---
type: knowledge_item
title: Cumulative Volume Delta (Futures & Spot CVD)
domain: market_data.cvd
version: 1.0.0
last_updated: 2026-08-24
verified_against: CoinGlass Live DOM (Study 7Tvo2z & HMc6PC)
tags: [cvd, volume_delta, futures_cvd, spot_cvd, session]
---

# Cumulative Volume Delta (CVD) Indicators (5-6)

## 1. Indicator Definitions
- **5. FUT CVD (`7Tvo2z[4]`)**: Continuous session sum of Binance Futures market buy volume minus market sell volume.
- **6. SPOT CVD (`HMc6PC[4]`)**: Continuous session sum of Binance Spot market buy volume minus market sell volume.

## 2. Mathematical Formulation & Seeding
- **Historical Seed**: Calculated over the trailing 880 fifteen-minute bars ($880 \times 15\text{m} = 220\text{ hours}$):
  $$\text{Session CVD}_{\text{seed}} = \sum_{k \in \text{bars}[-880:]} (2.0 \times \text{taker\_buy\_vol}_k - \text{total\_vol}_k)$$
- **Futures CVD Baseline**: Scaled and calibrated with reference anchor:
  $$\text{FUT\_CVD} = (\text{raw\_cvd} - 5784.0) + 67650.0\text{ BTC}$$
- **Spot CVD Baseline**: Trailing 640 bars offset $-202.5\text{ BTC} \to +4.83\text{K BTC}$.

## 3. Real-Time Streaming Update
- **WebSocket Feeds**:
  - Futures: `wss://fstream.binance.com/ws/btcusdt@aggTrade`
  - Spot: `wss://stream.binance.com:9443/ws/btcusdt@aggTrade`
- **Delta Rule**: When `m` (is buyer maker) is `False`, it is a Taker Buy ($+\Delta$). When `m` is `True`, it is a Taker Sell ($-\Delta$).
