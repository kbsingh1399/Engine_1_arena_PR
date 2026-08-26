# Reticle Integration & Architecture Reference

Reticle embeds an in-app verification layer exposed as `reticle_*` MCP tools and the `reticle` CLI (`@reticlehq/server`).
It enables autonomous verification of live runtime applications (DOM, network requests, console errors, state) without guessing or unverified assertions.

## Installation & Configuration

- **CLI / Server Package**: `@reticlehq/server` (installed globally and callable via `reticle` or `npx @reticlehq/server`).
- **Bridge Port**: `4400` (default bridge daemon port configured in `.reticle.json`).
- **MCP Configuration**: Registered in `.agents/mcp_config.json` and `.vscode/mcp.json`.
- **Project Configuration**: `.reticle.json` at repository root.

## Agent Skills Installed

The full suite of 13 Reticle skills is installed in `.agents/skills/` and symlinked in `.claude/skills/`:

| Skill | Description |
| :--- | :--- |
| `reticle` | Core Reticle engine and workflow orchestrator. |
| `install-and-verify` | Install, instrument, and verify runtime applications end-to-end. |
| `agentic-tdd` | Test-driven development for behaviour across the running app before writing code. |
| `audit-my-app` | Sweep whole running apps for broken buttons, console errors, or failed requests. |
| `debug-broken-ui` | Root-cause analysis combining click events, network requests, and runtime store state. |
| `design-system-compliance`| Check computed styles against project design tokens. |
| `drive-desktop-app` | Drive and verify Electron / Tauri desktop apps via IPC and main-process hooks. |
| `false-green-tests` | Catch false greens where test suites pass despite runtime failure. |
| `fix-what-i-pointed-at` | Fix UI bugs flagged with element pointers and source coordinates. |
| `replay-user-flows` | Save and replay deterministic regression checks with zero model overhead. |
| `test-error-states` | Stress-test edge cases: failing APIs, timeouts, debounces, and empty states. |
| `verify-ui-change` | Verify code changes against running apps with pass/fail consequence verdicts. |
| `verify-unattended` | Unattended autonomous verification for CI and non-interactive workflows. |

## Quick CLI Reference

```bash
# Check daemon, bridge port, and project instrumentation status
reticle doctor
reticle status

# Start daemon or MCP bridge
reticle serve --port 4400
reticle mcp --port 4400

# Run one-shot flow verification
reticle verify <url>

# Submit agent feedback or report tool gaps
reticle feedback --agent --kind <bug|gap|ambiguity|feature_request|improvement> "description"
```

## Definition of Done with Reticle

1. **Only `reticle_act_and_wait` and `reticle_assert` produce a verdict.**
2. A verdict of `verified: "unknown"` or `verified: "no-fault"` is not a pass.
3. Assert consequences before actions fire to guarantee causality.
4. Record verified journeys once, and replay them cheaply in regression loops.
