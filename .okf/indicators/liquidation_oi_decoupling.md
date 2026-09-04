---
type: knowledge_item
title: Open Interest Liquidation Decoupling & Cascade Filter
domain: market_data.liquidations
version: 1.0.0
last_updated: 2026-09-05
verified_against: Giagkiozis & Sa'id (Ledger 2024, 10.5195/ledger.2024.325)
tags: [open_interest, liquidations, cascade, decoupling, volume]
---

# Open Interest Liquidation Decoupling & Cascade Filter

## 1. Empirical Formulation (Giagkiozis & Sa'id 2024)
In crypto perpetual contracts, total traded volume $V_t$ consists of position openings, voluntary closures, and involuntary forced liquidations. Open interest $\text{OI}_t$ tracks total active positions:

$$\Delta\text{OI}_t = \text{New Positions Opened} - \text{Positions Closed}$$

## 2. Decoupling Cascade Flushes from Aggressive Shorting
During sharp price drops:
- **Case 1: Aggressive Short Initiative (Breakdown continuation)**
  $$\Delta P_t < 0 \quad \land \quad \Delta\text{OI}_t > 0 \quad \implies \quad \text{Fresh short positions entering market. DO NOT FADE.}$$
- **Case 2: Forced Liquidation Cascade (Exhaustion flush)**
  $$\Delta P_t < 0 \quad \land \quad \Delta\text{OI}_t < 0 \quad \land \quad \text{long\_liq\_zs} > 1.8 \quad \implies \quad \text{Forced margin closures. S1 ENTRY CANDIDATE.}$$

## 3. S1 Alpha Invariant
A long liquidation spike is valid if and only if open interest contracts simultaneously ($\Delta\text{OI} < 0$), confirming that open leverage was destroyed rather than expanded.
