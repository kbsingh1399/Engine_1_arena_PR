---
trigger: always_on
---

# ⚡ ACTIVE OPERATIONAL CONTEXT & MISSION CONTROL CARD

> **ALWAYS-ON TURN-0 SITUATIONAL AWARENESS**
> Auto-injected on every turn. Eliminates context amnesia, retrieval latency, and model hallucination.

## 1. Active Mission & Quantitative Target
- **Repository**: Quantitative Trading Infrastructure (`Engine_1_arena_PR` & `Engine_2`).
- **Active Focus**: `Engine_2/s1_liquidation_cascade.py` Walk-Forward Optimization across the **20 Out-Of-Sample (OOS) Windows (2021–2026)** on 18 Binance USDT-M Perpetual assets (3.46M 15m candles).
- **Target Pass Criteria**: ROI > 20.0%, Max Drawdown < 5.0%, Win Rate > 40.0%, Min Trades >= 6 per window under ONE causal configuration.
- **Status (2026-09-05, Arena fresh prompt session)**: Purged previous pessimistic baseline. Initiating fresh strategy construction utilizing the expanded Alpha feature set from Second Brain v11.0 (Nodes 1-76), dynamic volatility-scaled targets, and multi-tier microstructure ratchets.

## 2. Settled Mathematical & Strategy Invariants
- **Alpha Confluence Signal**:
  $$\text{long\_liq\_zs} > 1.8 \quad \land \quad \text{zc\_div} > 0.8 \quad \land \quad \Delta\text{Spot} > 0 \quad \land \quad \Delta\text{Futures} < 0 \quad \land \quad \text{RSI} < 40 \quad \land \quad \text{VWAP Z} < -0.5$$
- **Microstructure Exit Ratchet (Anti-Retracement)**:
  - $+0.8\text{R} \to \text{Stop to Entry} + 0.15\text{R}$ (Breakeven Lock)
  - $+1.5\text{R} \to \text{Stop to Entry} + 0.80\text{R}$ (Profit Lock)
  - Target: $+2.5\text{R}$ exit (Purged legacy 5.0R fantasy that retraced 85.8% of winners)
  - Time Decay: Exit at market if trade fails to gain $+0.2\text{R}$ within 24 bars (6 hours)
- **Fixed Risk Budget**:
  - Initial Capital: $5,000.00
  - Base Risk: $25.00 (0.50%) | House Money: $50.00 (1.00% max 2×) | Defense Risk: $15.00 (0.30%)
  - Drawdown Limit: 4.5% ($225 hard stop) | Max Concurrent Positions: 2 across all 18 symbols
- **Anti-Lookahead Blacklist**:
  - Permanently banned: `winning_configuration.json`, `s1_status.json`, per-window hand-picked parameter tables, test-set `nlargest` overrides.

## 3. Core Architecture & Local Tooling
- **Second Brain Recall**: `python .agents/scripts/second_brain.py query "<topic>"` (Graph Memory + Context Map + Session History).
- **DeepSeek Harness**: Local evaluation suite in `deepseek-harness/` via `.agents/scripts/deepseek_harness_runner.py`.
- **Memory Cleaner**: Run `.agents/scripts/free_ram.ps1` to unthrottle CPU and reclaim physical RAM.
- **Dual `.agents` Folder Parity**: Every edit to rules, memory, or scripts must be mirrored 1:1 between `Engine_1_arena_PR/.agents` and `Engine_2/.agents`.
