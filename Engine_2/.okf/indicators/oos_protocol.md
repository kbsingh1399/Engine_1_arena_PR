---
type: protocol
title: OOS Window Protocol
domain: quant-trading
version: 1.0.0
verified_against: strategy_engine.py
tags: [oos, validation, time-series, backtesting]
---

# Out-Of-Sample (OOS) Walk-Forward Protocol

## 1. Single Source of Truth
The canonical timeline for all Out-Of-Sample (OOS) testing windows is strictly defined by the `MONTHS` array in `Engine_2/strategy_engine.py`. 
No auxiliary script (e.g., `s1.py`, `s2.py`) is permitted to dynamically generate or estimate OOS windows using offset math (like `relativedelta`).

## 2. Window Specifications
- **Count**: Exactly 20 distinct OOS windows.
- **Duration**: Each window is exactly 1 month long (e.g., `2021-03-15` to `2021-04-15`).
- **Spacing**: Windows are spaced 3 months apart from start to start.

## 3. The Fail-Fast Mandate
If any hyperparameter configuration fails to meet the target gates (ROI > 20%, MaxDD < 5%, Winrate > 40%) in ANY of the 20 windows (e.g., Window 2), the entire configuration MUST be immediately aborted.
- Do NOT proceed to the next window.
- The agent must halt the iteration, log the failure, and proceed to the next configuration starting from Window 1.

## 4. Agent Execution Rule
Before modifying any iteration loops or OOS window generation functions in new scripts, agents MUST:
1. Import `MONTHS` from `strategy_engine.py`.
2. Map `test_start` and `test_end` exactly to the tuple values in `MONTHS`.
3. Compute `train_start` strictly by subtracting the `train_horizon_months` from `test_start`.
