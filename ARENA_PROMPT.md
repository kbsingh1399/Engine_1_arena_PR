# Autonomous Arena.ai Strategy Prompt

We need to backtest a quantitative trading strategy with strict criteria. 

**Data Path:**
`c:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\Engine_2\binance_backtesting_data`
Please use the 15-minute Parquet files in this directory.

**Git Repository:**
`https://github.com/kbsingh1399/Engine_1_arena_PR.git` (Branch: `main`)
Clone/pull from this repo to access the latest engine logic, rules (`.agents/rules/AGENTS.md`), and historical terminal runners.

**Core Concept:**
Strategy S1: S1_Liquidation
The strategy should utilize market microstructural features and liquidation data to predict sharp price movements. Focus on building the signal using a cascade of tree-based models.

**Objective:**
Develop and run the backtest autonomously until it meets the following criteria for a walk-forward out-of-sample (OOS) validation:
- Capital per Account: $5,000 (Total Portfolio: $30,000)
- Round-trip Fee+Slip: 0.08%
- Risk per Trade (1R): $35.00
- Target Gates: ROI > 20.0%, MaxDD < 5.0%, Win Rate > 40.0%, +5R Trailing Stop
- Portfolio Limit: Max 2 Concurrent Open Positions
- Parallel Assets: 18 crypto pairs
- Walk-Forward Windows: 20 monthly OOS windows (from 2021 to 2026)

Create the necessary scripts to accomplish this, implementing causal re-optimization loops if the OOS windows fail. Do not stop until all criteria are met across all 20 windows.
