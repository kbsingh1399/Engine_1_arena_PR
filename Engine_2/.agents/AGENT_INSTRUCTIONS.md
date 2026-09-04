# Universal Agent Execution & Institutional Engineering Directives
> **MANDATORY FOR ALL AGENTS, RUNTIMES & SPECIALISTS**

This repository is governed by an institutional, model-agnostic quantitative engineering architecture. All agents, automated workflows, and researchers operating in this workspace must load and adhere to these directives:

---

## 1. Mandatory Universal Prerequisites
Before conducting any code review, quantitative analysis, backtest execution, or refactoring, you MUST load:
1. `@[.agents/rules/AGENTS.md]` — Master enforcement router & central activation hub.
2. `@[.agents/rules/FABLE5_CHECKLIST.md]` — 13-step autonomous bug hunt loop & institutional anti-lookahead rules.
3. `@[.agents/memory/SESSION_CONTEXT_MAP.md]` — Token-optimized 7-phase milestone registry (<1k tokens).
4. `@[.agents/memory/MEMORY.md]` — Master memory taxonomy & architecture index.
5. `@[.agents/memory/session_chat_history.md]` — Chronological session transcript & forensic audit archive.

---

## 2. Core Execution Skills & Frameworks
Every agent must apply domain-specific skills from `.agents/skills/` and local infrastructure tools:
- **`@[skills/karpathy-guidelines]`**: Andrej Karpathy's 4 principles (Think Before Coding, Simplicity First, Surgical Changes, Goal-Driven Execution).
- **`@[skills/clean-code]`**: Anti-slop, concise, pragmatic coding standards with immediate pruning of unused code.
- **DeepSeek Harness (`deepseek-harness/`)**: Permanently active evaluation and benchmarking engine. Execute verification via `.agents/scripts/deepseek_harness_runner.py` or `pnpm run dsh`.
- **Graph Memory (MCP `memory` + Graphify)**:
  - Code AST Traversal: `python -m graphify query "<concept>"` (bounded within 2k tokens).
  - Relational Facts: `.agents/memory/graph/mcp_graph_memory.json` (14 entities, 13 relations).
- **Zero-Paid-Token Swarm (`gemini-web2api`)**: Run parallel auxiliary agents via `.agents/scripts/web2api_multi_agent.py` on `http://localhost:8081` to prevent coordinator context rot.
- **Sub-Turn Fast Recall**: Retrieve granular session context in <500 tokens using `python .agents/scripts/second_brain.py query "<concept>"`.

---

## 3. Verified Quantitative Strategy Invariants (Engine 2)
Do NOT re-introduce legacy or unverified parameters. All trading engines must adhere to the verified institutional architecture:
1. **Universe**: 18 Institutional Binance USDT-M Perpetuals (3,464,074 15-minute bars, 0 nulls, monotonic timestamps in `Engine_2/binance_backtesting_data/`).
2. **Walk-Forward Protocol**: 20 Non-Overlapping Out-Of-Sample (OOS) 1-Month Windows (2021–2026) with strictly causal 72-hour trade resolution purge boundaries ($t_{\text{purge}} = t_{\text{start}} - 72\text{h}$).
3. **Signal Confluence**:
   $$\text{long\_liq\_zs} > 1.8 \quad \land \quad \text{zc\_div} > 0.8 \quad \land \quad \Delta\text{Spot} > 0 \quad \land \quad \Delta\text{Futures} < 0 \quad \land \quad \text{RSI} < 40 \quad \land \quad \text{VWAP Z} < -0.5$$
4. **Microstructure Exit Ratchet** (Eliminates the 22.9% win-rate retracement trap):
   - **Phase 0 Breakeven Ratchet**: Move stop to entry $+0.15\text{R}$ at $+0.8\text{R}$ price gain.
   - **Phase 1 Profit Lock**: Move stop to entry $+0.80\text{R}$ at $+1.5\text{R}$ price gain.
   - **Target**: Exit at $+2.5\text{R}$.
   - **Time Decay**: Exit at market if trade fails to gain $+0.2\text{R}$ within 24 bars (6 hours).
5. **Fixed Portfolio Risk Budget**:
   - `INITIAL_CAPITAL = 5000.0`
   - `BASE_RISK = 25.0` (0.50% base risk)
   - `HOUSE_MONEY_RISK = 50.0` (1.00% max 2× risk when net profit > $50)
   - `DRAWDOWN_DEFENSE_RISK = 15.0` (0.30% risk when drawdown exceeds 2.5%)
   - `DRAWDOWN_RISK_LIMIT = 0.045` (4.5% / $225 hard drawdown stop)
   - `MAX_CONCURRENT = 2` (Max 2 open positions across all 18 symbols simultaneously).
6. **Zero Lookahead Mandate**: Zero lookup tables (`winning_configuration.json`, `s1_status.json`), zero external status caches, zero test-set `nlargest` overrides.

---

## 4. Verification & Testing Gates
- Never apply raw or unverified code patches.
- Prove changes by running local verification tests end-to-end rather than text inspection.
- When background tasks are launched, **DO NOT POLL**; wait for native completion signals to conserve tokens.
