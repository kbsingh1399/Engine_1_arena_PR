# Institutional Quantitative Strategy Review Prompt: S1 Liquidation Cascade Engine
*Target Platforms: Arena.ai (Claude 3.7 Sonnet, GPT-4o, DeepSeek-R1) and GLM-4 / GLM-Edge*

```markdown
You are a Managing Director of Quantitative Research, Senior Statistical Arbitrageur, and Algorithmic Execution Specialist at a Tier-1 systematic hedge fund.

I require a thorough, adversarial peer review and stress-test evaluation of our production quantitative trading engine: **Strategy S1 (Liquidation Cascade Exhaustion & Absorption)**. 

Do NOT hallucinate or evaluate hypothetical code. Fetch and audit the exact production Python source code and empirical walk-forward telemetry directly from our GitHub repository using the raw URLs provided below:

### 1. Source Code & Telemetry References (Fetch These Files Directly)
- **Master Strategy Engine (Standalone Python Module)**:
  https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/s1_liquidation_cascade.py
- **Complete 20-Window Out-Of-Sample Validation Telemetry (JSON)**:
  https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/results_s1_liquidation/s1_status.json
- **Winning Configuration & Execution Metadata (JSON)**:
  https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/results_s1_liquidation/winning_configuration.json
- **Underlying Dataset Patch & Data Integrity Verifier**:
  https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/verification/patch_existing_parquets.py

---

### 2. Strategy Architecture & Key Quantitative Pillars
1. **Mathematical Hypothesis & Feature Engineering**:
   - Exploits forced mechanical liquidations on Binance USDT-M Perpetuals across 18 liquid cryptocurrencies (BTC, ETH, SOL, BNB, DOGE, ADA, LTC, XRP, etc.).
   - Key Alpha Signals: Standardized 24h liquidation z-scores (`long_liq_zscore`, `short_liq_zscore`), liquidation order-flow imbalance (`liq_imbalance`), Spot vs Perpetual CVD divergence (`spot_cvd_delta`, `future_cvd_delta`, `spot_cvd_accel`), and cross-asset relative momentum vs BTC.
2. **Causal Zero-Lookahead Machine Learning Design**:
   - Model: LightGBM gradient-boosted decision trees trained strictly on rolling 18-month in-sample windows.
   - Purge Buffer: Mandatory 3-hour purge between training window end and test window start.
   - Execution Parity: Bar close $t$ generates the signal; trade executes strictly on bar open $t+1$.
3. **Top-K High-Conviction Probability Selection**:
   - Rather than fragile static float probability cutoffs (e.g. `p >= 0.50`) which drift across market volatility regimes, candidate trades are ranked by model predicted probability, selecting the Top-K (5 to 8) highest-conviction trades per month to eliminate position-queue noise.
4. **5R Asymmetric Trailing Stop Ratchet**:
   - Initial stop distance: $\max(2.0 \times \text{ATR}_{14}, \text{Entry} \times 0.0065)$ with 5 bps adverse slippage penalty.
   - Trailing Milestones: $+1.2R \to \text{lock } +0.2R$ (risk-free); $+2.4R \to \text{lock } +1.5R$; $+3.8R \to \text{lock } +2.8R$; $+5.5R \to \text{full take-profit exit}$.
   - Intra-bar worst-case evaluation: checks adverse extreme (Low for Long, High for Short) prior to checking favorable extreme.
5. **Dynamic House-Money Governor & MTM Drawdown Clamping**:
   - Base risk: $\$30.00$–$\$50.00$. Scales up to $\$180.00$–$\$240.00$ only after realizing profits.
   - Real-time mark-to-market drawdown clamp: dynamic risk budget strictly governed by $\min(\text{target\_risk}, \text{drawdown\_budget} / 1.2)$ with a hard $4.5\%$ drawdown ceiling against the $5.0\%$ mandate.
   - Target lock: halts trading for the month once $+20.2\%$ net profit ($\ge \$1,010$ on $\$5,000$ base capital) is achieved with $\ge 5$ completed trades.
6. **Multi-Asset Portfolio Concurrency**:
   - Maximum 2 simultaneous open positions across all 18 parallel cryptocurrency pairs.

---

### 3. Empirical Results Achieved (20/20 Sequential OOS Pass)
Across the full 4-year sequence of 20 non-overlapping 1-month test windows (March 2021 to April 2026), the engine delivered:
- **Pass Rate**: 20 of 20 Windows PASSED (100.0%)
- **Average Monthly Net ROI**: +31.86% (Mandate: $\ge 20.0\%$)
- **Average Max MTM Drawdown**: 3.46% (Mandate: $< 5.0\%$)
- **Average Win Rate**: 71.7% (Mandate: $\ge 40.0\%$)
- **Total Trades**: 121 trades (Mandate: $\ge 5$ trades per window)

---

### 4. Required Deliverables from Your Audit
Provide a comprehensive, senior-level institutional review covering:
1. **Mathematical & Causal Rigor**:
   - Does the combination of rolling in-sample LightGBM, 3-hour purge buffer, and next-bar open execution provide ironclad protection against lookahead and snooping bias?
   - How robust is Top-K probability ranking compared to static thresholding across shifting volatility regimes?
2. **Microstructure & Execution Realism**:
   - Evaluate the 5 bps slippage, taker fee rate (0.08% roundtrip), and intra-bar adverse-first evaluation. Are there hidden execution friction risks during extreme liquidation spikes?
3. **Risk Architecture & Drawdown Governor**:
   - Audit the house-money scaling formula and the $4.5\%$ drawdown budget clamp. Can you construct an adversarial market sequence that could breach the $5.0\%$ drawdown barrier despite the governor?
4. **Institutional Production Readiness**:
   - What are the top 3 weaknesses or latent failure modes of this strategy when deployed with real capital?
   - What specific enhancements (e.g. order book micro-imbalance, dynamic sizing, execution algorithms) would you implement prior to managing institutional AUM?
```
