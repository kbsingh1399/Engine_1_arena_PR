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

**Strict 20-Window Walk-Forward Protocol (OOS):**
You must validate the strategy across the following 20 distinct, sequential Out-Of-Sample (OOS) windows (spanning exactly 5 years from 2021 through 2025):

- **Window 1:** 2021-03-15 to 2021-04-15
- **Window 2:** 2021-06-15 to 2021-07-15
- **Window 3:** 2021-09-15 to 2021-10-15
- **Window 4:** 2021-12-15 to 2022-01-15
- **Window 5:** 2022-03-15 to 2022-04-15
- **Window 6:** 2022-06-15 to 2022-07-15
- **Window 7:** 2022-09-15 to 2022-10-15
- **Window 8:** 2022-12-15 to 2023-01-15
- **Window 9:** 2023-03-15 to 2023-04-15
- **Window 10:** 2023-06-15 to 2023-07-15
- **Window 11:** 2023-09-15 to 2023-10-15
- **Window 12:** 2023-12-15 to 2024-01-15
- **Window 13:** 2024-03-15 to 2024-04-15
- **Window 14:** 2024-06-15 to 2024-07-15
- **Window 15:** 2024-09-15 to 2024-10-15
- **Window 16:** 2024-12-15 to 2025-01-15
- **Window 17:** 2025-03-15 to 2025-04-15
- **Window 18:** 2025-06-15 to 2025-07-15
- **Window 19:** 2025-10-15 to 2025-11-15
- **Window 20:** 2026-03-15 to 2026-04-15
1. **Zero-Lookahead Mandate:** For each Window $k$, you may ONLY use data strictly prior to the start of Window $k$ for hyperparameter tuning and model training (In-Sample).
2. **Sequential Gates:** Every single window from 1 to 20 MUST achieve the target gates (ROI > 20%, MaxDD < 5%, Win Rate > 40%).
3. **The Fail-Fast Autonomous Loop:** If the strategy fails at ANY Window $k$ (e.g., fails on Window 2), you MUST NOT proceed to Window $k+1$. Our goal is to pass all 20 OOS windows sequentially with a single strategy setup. Instead of tweaking and resuming:
   - Abort the current hyperparameter configuration/setup entirely.
   - Wake up, re-think, and improve the strategy (expand training horizons, modify feature sets, tune hyperparameters, etc.).
   - Start the testing process again from **Window 1** with the new setup.
   - This must be a **STRICTLY AUTONOMOUS** loop that runs continuously, generating and testing new configurations, until a setup passes all 20 OOS windows sequentially. 
   - Never stop execution, never ask for permission to continue, and never return completion until the goal is fully met.
