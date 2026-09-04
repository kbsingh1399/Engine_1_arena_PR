---
type: knowledge_item
title: Order Flow Imbalance (OFI) & Spot-Futures CVD Decoupling
domain: market_data.microstructure
version: 1.0.0
last_updated: 2026-09-05
verified_against: Cont, Kukanov, Stoikov (2014) & Albers et al. (SSRN 3908966)
tags: [ofi, cvd, divergence, microstructure, orderflow, lambda]
---

# Order Flow Imbalance (OFI) & Spot-Futures CVD Decoupling

## 1. Theoretical Foundation (Cont, Kukanov & Stoikov 2014)
Order Flow Imbalance (OFI) measures the net supply and demand changes at the best quotes:

$$\text{OFI}_n = I_n \cdot \Delta q_n^{(b)} - (1 - I_n) \cdot \Delta q_n^{(a)}$$

Where:
- $I_n = 1$ if best bid increases or stays unchanged while size changes.
- Short-horizon price response is linear: $\Delta P_t = \lambda \cdot \text{OFI}_t + \varepsilon_t$.

## 2. Integrated Continuous Proxy in 24/7 Crypto Markets (Albers et al. 2021)
Because crypto perpetual futures trade continuously without daily boundary resets, raw cumulative delta drifts. Engine 2 operationalizes OFI via **Rolling Z-score Normalization** (`zc_div`):

$$\text{CVD}_t = \sum_{\tau=1}^t (V_\tau^{\text{taker\_buy}} - V_\tau^{\text{taker\_sell}})$$

$$\text{zc\_div} = \frac{\Delta\text{CVD}_{\text{spot}} - \mu(\Delta\text{CVD}_{\text{spot}}, 20)}{\sigma(\Delta\text{CVD}_{\text{spot}}, 20)} - \frac{\Delta\text{CVD}_{\text{futures}} - \mu(\Delta\text{CVD}_{\text{futures}}, 20)}{\sigma(\Delta\text{CVD}_{\text{futures}}, 20)}$$

## 3. Alpha Invariant Contract
- **Trigger Condition**:
  $$\text{zc\_div} > 0.8 \quad \land \quad \Delta\text{Spot} > 0 \quad \land \quad \Delta\text{Futures} < 0$$
- **Microstructure Meaning**: Smart money spot accumulation absorbs aggressive retail futures panic selling, dislocating price from order flow and guaranteeing mean-reversion pressure.
