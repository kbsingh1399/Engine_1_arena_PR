# 🏆 CORE MISSION: CONQUER S3 (MACRO TREND FOLLOW) IN AUTONOMOUS LOOP

You are tasked with building the autonomous optimization loop for **Strategy 3 (S3_Trend_Follow)**. S1 and S2 have already been successfully conquered with 20/20 Out-Of-Sample (OOS) windows passed. Now, it is time for S3 to achieve the exact same perfection.

## 🧠 S3 Core Concept: Classic Macro Trend Pullback
S3 relies on the macro trend defined by the **EMA 200 / EMA 800 spread**. 
- **Long Condition:** `mc > 0` (Macro spread positive) combined with a deep short-term pullback, e.g., `p8 < -0.20` or similar oscillator extremes (RSI < 35).
- **Short Condition:** `mc < 0` (Macro spread negative) combined with a short-term overbought rally, e.g., `p8 > 0.20` or RSI > 65.

## 🚨 STRICT SYSTEM MANDATES (NON-NEGOTIABLE)

### 1. The 5 Quantitative Gates
Every single OOS window (all 20) MUST sequentially pass these gates:
- **Monthly ROI:** $> 20.0\%$ ($> \$1,000$ net profit on a $\$5,000$ initial capital)
- **Max MTM Drawdown:** $< 5.0\%$ ($< \$250$)
- **Win Rate:** $> 40.0\%$
- **Statistical Significance:** $\ge 5$ completed trades
- **Portfolio Concurrency:** Maximum 2 simultaneous open positions across all 18 symbols.

### 2. Zero-Lookahead Walk-Forward Engine
- There MUST be a strict 3-hour purge gap between the In-Sample (IS) training data and Out-Of-Sample (OOS) test data.
- The ML model (LightGBM) must be calibrated **strictly** on the IS data. 
- You will execute **exactly 1 single-shot OOS test per window**. Zero loops over OOS, zero threshold tuning on OOS.

### 3. The 5R Trailing Stop Mandate
Your Numba simulator MUST include the multi-phase trailing stop:
- Initial SL at 1.0 * ATR
- Phase 1 (+2.5R): Lock in +0.5R
- Phase 2 (+3.8R): Lock in +2.0R
- Phase 3 (+5.0R): Activate 0.8R trailing runner.

### 4. Autonomous Fail-Fast Loop
Implement a `FOCUSED_CONFIGS` array (varying train_horizon_months, min_ret, learning_rate). The engine must iterate through configurations. If any window fails the mandates, it must immediately abort, log the failure, and try the next configuration until a 20/20 pass is achieved.

## ⏱️ AGENT WORKFLOW DIRECTIVE
1. Begin writing and executing the `s3.py` script based on the above constraints.
2. Ensure you utilize the `fast_portfolio_backtest_numba` and `simulate_single_trade_path` architectures.
3. **CRITICAL:** Set a scheduled cron job (or an internal heartbeat loop) to wake you up every 15 minutes to check on the optimization status and report the progress. Do not stay idle if the loop gets stuck.

---
**EXECUTE WITH LETHAL PRECISION. DO NOT STOP UNTIL S3 REACHES 20/20 PASS RATE.**
