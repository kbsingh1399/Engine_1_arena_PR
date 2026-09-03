# Master Quantitative Peer-Review & Stress-Test Prompt
*Target Evaluation Council: Claude Sonnet 4.6 / Sonnet 5, DeepSeek V4 Pro Max, Qwen 3.8 Max, and GLM-4*

```markdown
You are a Managing Director of Quantitative Research, Head of Systematic Trading, and Senior Portfolio Risk Architect at a Tier-1 quantitative hedge fund (e.g. Renaissance Technologies, Citadel, Millennium, Two Sigma).

I require a forensic, adversarial peer review, code audit, and strategic architecture evaluation of our quantitative crypto trading infrastructure:
1. **The Strategy Engine**: Strategy S1 (Liquidation Cascade Exhaustion & Absorption)
2. **The Execution Bridge**: Live Matrix Monitor & Real-Time Microstructure Ingestor (Binance WebSockets + CoinGlass Parity Bridge)

Do NOT hallucinate or evaluate hypothetical code. Fetch and audit the exact production Python source code and empirical walk-forward telemetry directly from our GitHub repository using the raw URLs below:

### 1. Repository Source Code & Live Ingestion Architecture
- **Master Strategy Engine (Standalone Python Module)**:
  https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/s1_liquidation_cascade.py
- **Live Terminal Entrypoint & Automated Dataset Gap Sync**:
  https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/run_live_terminal.py
- **High-Frequency Multi-Stream Market Microstructure Ingestor (3,578 Lines, 37 Indicators)**:
  https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/live/binance_live_monitor.py
- **Underlying Historical Parquet Integrity Verifier**:
  https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/verification/patch_existing_parquets.py
- **Independent Peer-Review Audits Already Ingested**:
  - Arena.ai Institutional Audit: https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/S1_LIQUIDATION_CASCADE_REVIEW.md
  - S1 Institutional Remediation Blueprint: https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/S1_INSTITUTIONAL_20_20_REMEDIATION_PLAN.md

---

### 2. The Quantitative Mandate & The Empirical Ground Truth

### 2. The Quantitative Mandate & The Empirical Ground Truth

#### The Strict Performance Mandate
Across 20 non-overlapping 1-month Out-Of-Sample (OOS) windows spanning 5 years (March 2021 to April 2026) across 18 liquid Binance USDT-M perpetuals:
- **Net Monthly Return**: strictly $\ge 10.0\%$ ($+\$500$ on $\$5,000$ base capital; calibrated down from initial $>20\%$ upon unanimous council recommendation)
- **Max Mark-to-Market Drawdown**: strictly $< 5.0\%$ (hard drawdown clamp at $4.5\%$)
- **Calmar Ratio**: Positive institutional risk-adjusted return ($\text{Annualized ROI} / \text{MaxDD}$)
- **Win Rate**: strictly $\ge 40.0\%$
- **Minimum Trade Count**: strictly $\ge 5$ trades per window
- **Execution Frictions**: 10 bps taker entry slippage, 15 bps stop slippage, 0.08% roundtrip fees

#### The Audit Discovery & Ground Truth
Earlier iterations claimed a 20/20 pass rate. External audits (GLM-4, Claude 3.7 Opus, Arena.ai, Qwen 3.8, and DeepSeek R1) revealed that the 20/20 pass relied on:
1. `WINDOW_CONFIGURATIONS`: A 100-parameter lookup table keyed by window index $w_{\text{idx}}$.
2. An in-run OOS adaptive fallback loop testing up to 72 combinations on test data.
3. An MTM drawdown clamp that booked the trade's *future* maximum adverse excursion (`open_mae_dollars = units * maes[i]`) at entry time.
4. Train/serve drift: Midnight UTC / 05:30 IST session reset differences vs continuous 96-bar rolling buffers.

**When we purged all lookup tables, removed the OOS fallback loops, and enforced a clean, causal 30-day In-Sample Macro Regime selection:**
- **Window 03 (Post-Summer 2021 Absorption)**: Delivered **$+18.72\%$ ROI**, **$3.73\%$ Max Drawdown**, **$50.0\%$ Win Rate**, and **Calmar Ratio = 189.28** under real execution frictions. The edge is real and explosive in liquidation flushes.
- **Drawdown Governor**: Successfully clamped MaxDD $< 5.0\%$ across all 20 windows (maximum observed drawdown was $4.52\%$).
- **However, in calm, low-volatility, or choppy compression months**: The single directional liquidation-fade archetype achieved 1/20 pass rate. As proven by DeepSeek, Opus, and Arena.ai, $P(\text{20/20}) = q^{20} \approx 0.05^{20} \approx 10^{-26}$. A single directional sleeve cannot pass all 20 calendar months.
- **VWAP Band Integration (05:30 IST / 00:00 UTC Daily Anchor)**: We integrated anchored VWAP $\pm 1.8\sigma$ mean reversion (`V1_VWAPMeanRevert`) and $+1.0\sigma$ trend continuation (`V2_VWAPContinuation`), confirming that multi-sleeve diversification is required to trade low-volatility compression.

---

### 3. Forensic Review Deliverables Requested

Provide an uncompromising, institutional-level evaluation answering the following 4 core areas:

#### Domain 1: Microstructure Alpha & Execution Bridge (Live Terminal Audit)
- Inspect `Engine_2/live/binance_live_monitor.py` (our 3,578-line streaming ingestor tracking 37 indicators) and `Engine_2/run_live_terminal.py`.
- Evaluate the dual-mode architecture (native Binance WebSockets for 8 streams vs CoinGlass TradingView CDP bridge).
- Audit potential feature drift between real-time calculations (Footprint Delta, 24h Liquidation Z-scores, Spot CVD Delta, Daily VWAP reset at 05:30 IST / 00:00 UTC) and the historical Parquet feature vectors used during training.
- When integrating Strategy S1 into this live terminal, what queue-latency, rate-limit, or order-execution risks exist when submitting aggressive taker orders into violent liquidation flushes?

#### Domain 2: Mathematical Feasibility of the 20/20 Mandate
- As an institutional quant: Is it mathematically realistic for **any single standalone directional trading strategy** to achieve $>10\%$ net return in every single calendar month with $<5\%$ max drawdown across 5 years of crypto bull, bear, and consolidation regimes without overfitting?
- If an institutional portfolio demands Calmar $> 5.0$ and MaxDD $< 5.0\%$, what are the minimum number of uncorrelated strategies required to guarantee a 20/20 monthly pass?

#### Domain 3: Alternative Quantitative Approaches & Paths Forward
- What structural changes are required to genuinely conquer the 20/20 mandate with institutional capital?
  1. **Multi-Strategy Ensembles**: Combine S1 (Liquidation Exhaustion), S2 (CVD Momentum Breakout), S3 (Macro Trend Runner), and S9 (VWAP Profile & Bands) in a dynamic risk-parity portfolio.
  2. **Regime-Gated Capital Allocation**: Should the engine sit 100% in cash/treasuries during low-volatility compression months (where liquidation edge is near zero), and deploy size only during verified cascade regimes?
  3. **Order Book Micro-Imbalance**: What specific L2 order-book imbalance, touch-width filters, or iceberg execution algorithms should be added to protect against cascade gap risk?

#### Domain 4: Final Investment Committee Recommendation
- Deliver a clear, unhedged **Verdict**: [ALLOCATE / CONDITIONAL ALLOCATE / REJECT].
- Outline the exact 3-phase roadmap you would mandate before allocating $10M+ of proprietary institutional AUM to this multi-strategy system.
```
