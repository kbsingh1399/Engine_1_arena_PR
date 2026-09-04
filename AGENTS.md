# Agent Directives & Repository Architecture

<!-- reticle:begin (managed by `reticle init` — edit outside these markers) -->
## Verifying with Reticle

This repository is instrumented by **Reticle**, an in-app verification layer exposed as `reticle_*` MCP tools and the `npx @reticlehq/server` CLI (or `reticle` command). Verifying is part of "done", not an optional extra.

**Verify when you have changed something a user can see or do.** A component, a form, a route, a request, a piece of state that reaches the screen. Do it BEFORE telling the user it is complete. Reading the diff proves nothing and unit tests do not run the app.

**Do not reach for Reticle when the change cannot show up in the running app.** Skip it for: documentation, comments, tests, build config, CI, dependency bumps with no user-facing effect, backend or CLI work with no UI surface. Say in one line that you skipped verification and why.

**How to verify:**
- Drive the flow with `reticle_act_and_wait({ ref, action, until })`. It names the consequence you expect BEFORE the action.
- Batch a multi-step journey into one `reticle_act_sequence` rather than one round trip per field.
- Read surrounding evidence with `reticle_snapshot`, `reticle_state`, `reticle_network`, `reticle_console`.
- **Only `reticle_act_and_wait` and `reticle_assert` produce a verdict.**
<!-- reticle:end -->

## Quantitative Trading & ML Directives

1. **Strict Zero-Lookahead & Causal ML Execution**:
   - Zero access to future data or labels at decision time $t$.
   - Calibration of entry thresholds ($p^*$) must be strictly in-sample.
   - All 20 Out-Of-Sample (OOS) walk-forward windows must independently achieve:
     - Return > 20.0%
     - Max Drawdown < 5.0%
     - Win Rate > 40.0%
     - 5R Trailing Stop Mandate
2. **Portfolio Concurrency**: Max 2 simultaneous open positions across all 18 parallel symbols.

---

## 🔴 Master Agent Enforcement Router
This repository is governed by the centralized master agent router at:
👉 **[.agents/rules/AGENTS.md](file:///c:/Users/SIGMA/Documents/Project%20-%20Coinglass%20Trading/Engine_1_arena_PR/.agents/rules/AGENTS.md)**

Instantiating `AGENTS.md` automatically activates:
- **Autonomous Bug Hunt & CDP Protocols**: [.agents/rules/FABLE5_CHECKLIST.md](file:///c:/Users/SIGMA/Documents/Project%20-%20Coinglass%20Trading/Engine_1_arena_PR/.agents/rules/FABLE5_CHECKLIST.md)
- **Institutional Forensic Reviews & Audit Baselines**: [Opus_5.md](file:///c:/Users/SIGMA/Documents/Project%20-%20Coinglass%20Trading/Engine_1_arena_PR/Opus_5.md) & [Engine_2/S1_LIQUIDATION_CASCADE_REVIEW.md](file:///c:/Users/SIGMA/Documents/Project%20-%20Coinglass%20Trading/Engine_1_arena_PR/Engine_2/S1_LIQUIDATION_CASCADE_REVIEW.md)
- **Anti-Lookahead & Zero-Hallucination Checklist**: [.agents/rules/AGENTS.md Part 12](file:///c:/Users/SIGMA/Documents/Project%20-%20Coinglass%20Trading/Engine_1_arena_PR/.agents/rules/AGENTS.md#L309)
- **Session Memory & Transcript Sync**: [.agents/memory/session_chat_history.md](file:///c:/Users/SIGMA/Documents/Project%20-%20Coinglass%20Trading/Engine_1_arena_PR/.agents/memory/session_chat_history.md) & [.agents/memory/MEMORY.md](file:///c:/Users/SIGMA/Documents/Project%20-%20Coinglass%20Trading/Engine_1_arena_PR/.agents/memory/MEMORY.md)
- **Deterministic Indicator Contracts**: [.okf/OKF_INDEX.md](file:///c:/Users/SIGMA/Documents/Project%20-%20Coinglass%20Trading/Engine_1_arena_PR/.okf/OKF_INDEX.md)
- **Omni Execution Persona**: [.agents/rules/GEMINI.md](file:///c:/Users/SIGMA/Documents/Project%20-%20Coinglass%20Trading/Engine_1_arena_PR/.agents/rules/GEMINI.md)

