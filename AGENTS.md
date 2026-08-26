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
