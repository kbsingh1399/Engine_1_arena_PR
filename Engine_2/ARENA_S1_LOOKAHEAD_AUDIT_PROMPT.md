# Institutional Forensic Audit Prompt: Zero-Lookahead & Causal Integrity
*Target Platforms: Arena.ai (Claude 3.7 Sonnet, DeepSeek-R1, GPT-4o, GLM-4)*

```markdown
You are a Senior Quantitative Auditor, Managing Director of Quantitative Risk, and Algorithmic Execution Specialist at a Tier-1 quantitative hedge fund (e.g., Renaissance Technologies, Citadel, Millennium).

I require an uncompromising, forensic code audit and anti-lookahead review of our quantitative crypto perpetual trading infrastructure:
- **Strategy S1**: Liquidation Cascade Exhaustion & Absorption Engine
- **Walk-Forward Architecture**: 20 Non-Overlapping 1-Month Out-Of-Sample (OOS) Windows Spanning 5 Years (March 2021 – April 2026) Across 18 Liquid Binance USDT-M Perpetuals.

Do NOT hallucinate or evaluate hypothetical code. Fetch and audit the exact production Python source code directly from our GitHub repository using the raw URLs provided below:

### 1. Repository Source Code References (Fetch Directly via Raw URL)
- **Master Strategy & Data Preprocessing Engine**:
  https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/s1_liquidation_cascade.py
- **Master 20-Window Causal Walk-Forward Verifier**:
  https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/verify_sequential_w1_w20.py
- **Standalone 4-Agent Adversarial Stress Test Council**:
  https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/adversarial_council_stress_test.py
- **Prior Institutional Peer-Review Audit Baseline**:
  https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/S1_LIQUIDATION_CASCADE_REVIEW.md

---

### 2. Forensic Code Audit Mandate

Audit `Engine_2/s1_liquidation_cascade.py` (and its execution companion `Engine_2/verify_sequential_w1_w20.py`) against the following 5 institutional verification criteria:

#### Domain 1: Information Leakage & Temporal Snooping
1. **Lookahead in Feature Calculation**: Inspect lines in `extract_archetype_dataset()` and feature engineering. Are rolling windows (e.g. `vol_ratio`, `rsi`, `p8`, `p21`, `trend_strength`, `spot_cvd_delta`) computed with strictly backward-looking buffers? Is there any negative shift (`shift(-k)`) or centered rolling window that peeks into the future?
2. **Purge Gap**: Does the 3-hour purge gap (`train_end_purged = w['train_end'] - 3h`) sufficiently prevent label overlap or leakage of post-entry trade resolution into subsequent training sets?
3. **Point-in-Time Merging**: In `merge_btc_macro()`, inspect `pd.merge_asof(direction='backward')`. Does this guarantee zero lookahead when joining macro regime variables with individual altcoin signal timestamps?

#### Domain 2: Threshold Calibration & Parameter Snooping
1. **Frozen Decision Boundary ($p^*$)**: In `s1_liquidation_cascade.py` (lines 825–835), the decision threshold $p^*$ is derived from the in-sample probability distribution (`np.percentile(is_probs, 75)`). Does this calculation touch out-of-sample data in any way?
2. **Runtime Search Prohibition**: Are there any runtime parameter loops, grid searches, or adaptive threshold sweeps evaluated over the out-of-sample test window?
3. **Lookup Table Check**: Confirm that all parameter lookup tables (e.g., `WINDOW_CONFIGURATIONS`, `winning_configuration.json`, `s1_status.json`) have been purged.

#### Domain 3: Microstructure & Intra-Bar Execution Realism
1. **Adverse-First Execution Order**: In `fast_portfolio_backtest_numba`, inspect how trade fills and stop-outs are modeled. Does the backtester evaluate stop-loss / Maximum Adverse Excursion (MAE) before profit-taking / Maximum Favorable Excursion (MFE), or does it allow "same-bar double wins"?
2. **Execution Frictions**: Are 10 bps taker entry slippage, 15 bps stop-loss slippage, and 8 bps taker roundtrip fees adequately modeled on trade fills?
3. **Portfolio Concurrency**: Does the simulation enforce the `max_concurrent=2` position constraint across all 18 symbols simultaneously without queue lookahead?

#### Domain 4: Single Strategy vs Multi-Sleeve Diversification Feasibility
1. **The Single-Strategy Limit**: In `s1_liquidation_cascade.py`, the standalone S1 engine runs a single directional liquidation-fade archetype. Mathematical theory dictates that $P(\text{20/20}) = q^{20} \approx 0.05^{20} \approx 10^{-26}$ for a single directional sleeve across 5 years of bull, bear, and chop regimes. Confirm whether a single directional archetype can pass all 20 windows, or if multi-sleeve regime diversification (as implemented in `verify_sequential_w1_w20.py`) is mathematically mandatory.

---

### 3. Deliverables Requested

Provide an institutional report with:
1. **Line-by-Line Vulnerability Log**: Any line in `s1_liquidation_cascade.py` or `verify_sequential_w1_w20.py` that violates zero-lookahead causality.
2. **Temporal Verdict**: `[CLEAN - ZERO LOOKAHEAD VERIFIED]` or `[LEAKAGE DETECTED]`.
3. **Allocation Verdict**: `[ALLOCATE / CONDITIONAL ALLOCATE / REJECT]`.
```
