# Quantitative Trading Architecture & Directives

## Core Gates (All 20 OOS Windows Independently):
- ROI > 20.0%
- Max Drawdown < 5.0%
- Win Rate > 40.0%
- Min Trades >= 6
- 5R Trailing Stop Mandate
- Portfolio Concurrency <= 2

## Sizing & Risk Management (Dynamic Dual Shield):
- Drawdown Defense Risk:  (underwater <= -)
- Baseline Recon Risk:  - 
- House Money Expansion Risk:  -  (profit >= +)
- Target Lock: cumulative PnL >= + (+20.5% ROI) with >= 6 trades clears the month.

## Multi-Tier Profit Lock:
- Peak >= +1.8R -> Lock +1.2R (covers 0.08% taker fee drag)
- Peak >= +3.0R -> Lock +2.0R
- Peak >= +5.0R -> Trail at 0.8R distance from peak high/low.