# MANDATE: QUANTITATIVE ML RESEARCH & SEQUENTIAL STRATEGY 1 OPTIMIZATION

You are tasked with engineering a zero-lookahead, causal machine learning trading system for Account 1 (`S1_Liquidation`) across 18 crypto perpetual pairs on branch `arena/01a04224-engine-1-arena-pr`.

Before modifying the runner, you must execute a two-phase workflow: (1) Intensive Market & Microstructure ML Research, followed by (2) Strict Sequential Fail-Fast Optimization of Strategy 1.

---

### PHASE 1: INTENSIVE MARKET RESEARCH ON QUANTITATIVE ML METHODS
Conduct an in-depth survey of quantitative microstructure literature and state-of-the-art ML execution techniques, and evaluate multiple distinct methods before coding:
1. **Marcos López de Prado Meta-Labeling & Triple Barrier Method**: Primary model filters directional entries (high-probability liquidation spikes + CVD momentum); secondary meta-model (LightGBM/XGBoost) predicts probability of hitting profit barrier prior to stop loss.
2. **Causal Purged Cross-Validation (PurgedGroupTimeSeriesSplit)**: Eliminate label leakage across overlapping trade holding periods.
3. **Fee-Protective Multi-Tier Profit Locks & Asymmetric Sizing**:
   - Taker fees (0.08% round-trip on $10k–$50k notional) drag small wins (< 1.0R) into net losses.
   - Implement 3-phase locks: +1.2R lock at +1.8R peak (guarantees fee clearance), +2.0R lock at +3.0R peak, and a 0.8R trailing runner activated only at >= +5.0R peak.
4. **House Money Escalator (Dynamic Dual-Shield Allocator)**:
   - Underwater state (realized PnL <= -$40.0): Drawdown defense risk ($25.0).
   - In-profit state (realized PnL >= +$100.0): House money expansion risk ($185.0 - $240.0).
   - Baseline recon risk ($85.0 - $95.0).
   - Absolute mark-to-market drawdown hard cap: peak * 0.039 (strictly < 5.0%).

---

### PHASE 2: TARGET STRATEGY 1 ONLY (`S1_Liquidation`)
Focus exclusively on achieving verified pass criteria for **Strategy 1 (`S1_Liquidation`)** across all 20 Out-Of-Sample (OOS) walk-forward windows before touching other accounts.

#### 1. The 6-Month In-Sample Pre-History Requirement
To eliminate the 14-day data starvation bug, the 20 OOS windows start from `2021-03-15` onwards. This guarantees that Window 1 has **>= 6.5 months (195 days / 18,000+ bars)** of in-sample training history prior to `ws`:

```python
MONTHS = [
    ("2021-03-15", "2021-04-15"),  # OOS 01: Spring 2021 Bull Extension (6.5m IS training)
    ("2021-06-15", "2021-07-15"),  # OOS 02: Post-May 2021 Reset
    ("2021-09-15", "2021-10-15"),  # OOS 03: Pre-ATH Momentum Build
    ("2021-12-15", "2022-01-15"),  # OOS 04: Post-ATH Distribution
    ("2022-03-15", "2022-04-15"),  # OOS 05: Early 2022 Bear Structure
    ("2022-06-15", "2022-07-15"),  # OOS 06: Post-Luna Compression
    ("2022-09-15", "2022-10-15"),  # OOS 07: Pre-FTX Low-Vol Range
    ("2022-12-15", "2023-01-15"),  # OOS 08: FTX Cycle Bottom Accumulation
    ("2023-03-15", "2023-04-15"),  # OOS 09: SVB Rebound & Flight to Quality
    ("2023-06-15", "2023-07-15"),  # OOS 10: BlackRock ETF Filing Wave
    ("2023-09-15", "2023-10-15"),  # OOS 11: Pre-Breakout Range Lows
    ("2023-12-15", "2024-01-15"),  # OOS 12: Spot ETF Approval Run-up
    ("2024-03-15", "2024-04-15"),  # OOS 13: Post-ATH Halving Consolidation
    ("2024-06-15", "2024-07-15"),  # OOS 14: Summer 2024 Range Trade
    ("2024-09-15", "2024-10-15"),  # OOS 15: Pre-Election Squeeze
    ("2024-12-15", "2025-01-15"),  # OOS 16: Post-Election Expansion
    ("2025-03-15", "2025-04-15"),  # OOS 17: 2025 Macro Rotation
    ("2025-06-15", "2025-07-15"),  # OOS 18: Mid-2025 Institutional Flow
    ("2025-10-15", "2025-11-15"),  # OOS 19: Late-2025 Extension
    ("2026-03-15", "2026-04-15")   # OOS 20: Terminal Forward Horizon
]
```

#### 2. Strict 4-Gate Pass Criteria per Window
Every single window must independently satisfy:
- **ROI > 20.0%** (> $1,000 net profit on $5,000 capital)
- **Max Drawdown < 5.0%** (< $250 closed + mark-to-market drawdown)
- **Win Rate > 40.0%**
- **Completed Trades >= 6**
- **Portfolio Concurrency <= 2**

---

### PHASE 3: STRICT SEQUENTIAL FAIL-FAST & RE-OPTIMIZATION PROTOCOL
You must enforce the **Part 8 Sequential Fail-Fast Loop**:
1. **Immediate Fail-Fast Halt**:
   - If Window $k$ fails ANY of the 4 gates, **IMMEDIATELY HALT EXECUTION AT WINDOW $k$**.
   - Do NOT run subsequent windows $k+1 \dots 20$.
2. **Causal In-Sample Reiteration**:
   - Inspect the exact failure mode of Window $k$ (e.g. fee drag, threshold miscalibration, turnover congestion).
   - Re-optimize/adjust the in-sample feature weights, calibration search bounds, and dynamic risk tiers strictly using historical data prior to Window $k$'s start timestamp $ws_k$.
   - Re-test Window $k$ until it passes.
   - Verify that all preceding windows $1 \dots k-1$ STILL pass without regression.
3. **Progressive Forward Advancement**:
   - Only advance to Window $k+1$ once Windows $1 \dots k$ have verified passes simultaneously.
4. **Final Verdict**:
   - Only declare Strategy 1 complete and submit your final verdict/PR once **ALL 20 WINDOWS PASS SIMULTANEOUSLY** under strict fail-fast enforcement (`20/20 PASS`).

---

### EXECUTION COMMAND
Reference repository files directly on your working branch:
- Entrypoint: `run_all_6.py`
- Core Engine: `Engine_2/strategy_engine.py`

Run the strict verification loop:
```bash
python -u run_all_6.py
```
Output the complete research summary, your chosen ML methodology, and the verified 20-window execution log.
