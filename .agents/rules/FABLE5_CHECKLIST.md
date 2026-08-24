# FABLE 5 ARCHITECTURE & CHECKLISTS
> **Dynamically loaded by AGENTS.md**
> Contains detailed rules, checklists, routing tables, and protocols.

## PART 2: AUTONOMOUS BUG HUNT LOOP (LETHAL PROTOCOL)
### 2.1 Autonomous Bug Hunt Execution Order
```
FOR EACH file touched this session OR referenced in the conversation transcript:
  1. semantic_search_nodes_tool(file) → list all functions/classes
  2. get_impact_radius_tool(symbol) → compute blast radius
  3. query_graph_tool(pattern="callers_of", symbol) → trace all upstream callers
  4. get_review_context_tool(symbol) → read source with structural context
  5. Apply Bug Hunt Checklist (Section 2.2)
  6. Report ALL findings proactively before closing the turn
```
### 2.2 Bug Hunt Checklist (Apply to Every Function in Scope)
**Concurrency & Async Bugs**
- [ ] Are `asyncio.Lock` and `threading.Lock` never mixed across the same shared state?
- [ ] Does every `async def` that touches shared state use `await lock.acquire()`?
- [ ] Are background `asyncio.Task` objects stored and cancelled on shutdown?
- [ ] Are `websockets` reconnection loops bounded by retry limits to prevent infinite loops?

**Data Integrity & Normalization**
- [ ] Are floating-point values NEVER compared with `==` for monetary/price data?
- [ ] Are all incoming API values validated before being stored in `SnapshotStore`?
- [ ] Are feature vectors validated for `NaN`, `Inf`, and out-of-bound z-scores before model inference?
- [ ] Is CVD delta calculated from accumulator diffs, NOT from raw viewport-relative DOM values?
- [ ] Are liquidation events accumulated per-candle block (15m idx reset), NOT summed across session?

**Error Handling**
- [ ] Does every `aiohttp` and `websockets` call have explicit timeout and exception handling?
- [ ] Are `except Exception: pass` blocks forbidden? Every except must log context or re-raise.
- [ ] Does every external call have a circuit-breaker or retry-with-backoff pattern?
- [ ] Are all `subprocess` calls guarded with `timeout=` parameter?

**State Machine Correctness**
- [ ] Are all `running` flags properly set to `False` during shutdown signal handlers?
- [ ] Are singleton locks cleaned on startup to prevent stale browser session blocks?
- [ ] Does the `SnapshotStore` correctly differentiate between `source="coinglass"` and `source="binance_ws"` to prevent temporal mixing?

**ML Pipeline Integrity**
- [ ] Are model thresholds loaded from saved `.pkl` metadata, NOT hardcoded?
- [ ] Is the calibrated win-rate used for position sizing, NOT the raw probability?
- [ ] Are feature columns validated to match the training feature set before calling `predict_proba`?
- [ ] Is the `FeatureDriftDetector` hooked into every strategy's `predict()` path, not just one?

**Financial Safety**
- [ ] Does every order placement have a corresponding stop-loss registered before the order is filled?
- [ ] Are monetary values computed with `Decimal` or integer cents, never `float` arithmetic?
- [ ] Does the Risk Governor enforce max drawdown limits per session, per day, and per position simultaneously?
- [ ] Are orphaned positions detected and closed on engine restart?

### 2.3 Proactive Reporting Rule
All findings from the Bug Hunt Loop MUST be reported to the user at the END of every response:
```markdown
## 🔍 Autonomous Bug Scan Findings (Unprompted)
- [SEVERITY: HIGH/MED/LOW] File.py:LineX — Description of finding
```

---

## PART 3: REQUEST CLASSIFICATION & AGENT ROUTING

### 1. Request Classifier Matrix
| Request Type | Trigger Keywords | Active Tiers | Result |
|---|---|---|---|
| **QUESTION** | "what is", "how does", "explain" | TIER 0 only | Text Response |
| **SURVEY/INTEL** | "analyze", "list files", "overview" | TIER 0 + Explorer + Graph | Session Intel (No File) |
| **SIMPLE CODE** | "fix", "add", "change" (single file) | TIER 0 + TIER 1 (lite) + Graph Sync | Inline Edit |
| **COMPLEX CODE** | "build", "create", "implement", "refactor" | TIER 0 + TIER 1 (full) + Agent + Bug Hunt | `{task-slug}.md` Required |
| **NEW APP** | "new app", "from scratch", "build me a", multi-page | `project-planner` (loads `app-builder`) → `orchestrator` | `{task-slug}.md` + `app-builder` |
| **DESIGN/UI** | "design", "UI", "page", "dashboard" | TIER 0 + TIER 1 + Agent | `{task-slug}.md` Required |
| **SLASH CMD** | `/create`, `/orchestrate`, `/debug` | Command-specific flow | Variable |
| **ARENA SYNC** | "arena", "verify", "sync changes" | Graph sync + Session transcript read + Bug Hunt | Full audit report |

### 2. Intelligent Auto-Routing & Announcement
When auto-applying an agent, inform the user with:
`🤖 **Applying knowledge of @[agent-name]...**`

### 3. Domain Specialist Mapping
| Project Type / Domain | Primary Agent | Mandatory Key Skills |
|---|---|---|
| **QUANT / TRADING ENGINE** | `backend-specialist` + `debugger` | `quant-analyst`, `trading-ledger`, `risk-manager`, `risk-metrics-calculation`, `api-patterns`, `systematic-debugging` |
| **BACKEND & APIS** | `backend-specialist` | `fastapi-pro`, `django-pro`, `nestjs-expert`, `api-design-principles`, `graphql-architect`, `grpc-golang`, `clean-code` |
| **WEB FRONTEND & UI/UX** | `frontend-specialist` | `frontend-design`, `nextjs-react-expert`, `tailwind-patterns`, `shadcn-ui`, `dashboard-design`, `react-ui-patterns` |
| **MOBILE APPS (iOS/Android/RN)** | `mobile-developer` | `mobile-design`, `react-native-expert`, `flutter-expert`, `ios-developer`, `android-dev`, `swiftui-expert-skill` |
| **DATABASE & VECTOR STORAGE** | `database-architect` | `database-design`, `database-optimizer`, `postgres-best-practices`, `drizzle-orm-expert`, `prisma-expert`, `qdrant-scaling` |
| **SECURITY & PENETRATION AUDIT** | `security-auditor` + `penetration-tester` | `vulnerability-scanner`, `red-team-tactics`, `api-security-testing`, `top-web-vulnerabilities`, `sql-injection-testing` |
| **DEVOPS, CLOUD & CI/CD** | `devops-engineer` | `docker-expert`, `kubernetes-architect`, `terraform-infrastructure`, `aws-advisor`, `gcp-cloud-run`, `github-actions-advanced` |
| **SYSTEM DEBUGGING & ROOT CAUSE**| `debugger` | `systematic-debugging`, `error-detective`, `distributed-tracing`, `root-cause-tracing`, `invariant-guard` |
| **TESTING, E2E & QA AUTOMATION** | `test-engineer` + `qa-automation-engineer` | `testing-patterns`, `tdd-workflow`, `playwright-skill`, `pytest-skill`, `vitest-skill`, `k6-load-testing`, `mock-hunter` |
| **AI, LLM & MULTI-AGENT SWARMS**| `orchestrator` | `prompt-engineer`, `llm-app-patterns`, `langchain-architecture`, `langgraph`, `crewai`, `pydantic-ai`, `rag-implementation` |
| **PROJECT PLANNING & DISCOVERY** | `project-planner` | `plan-writing`, `brainstorming`, `rich-elicitation`, `decomposition-planning-roadmap` |
| **PERFORMANCE & LATENCY PROFILING**| `performance-optimizer`| `performance-profiling`, `perf-web-optimization`, `core-web-vitals`, `memory-forensics`, `scale-benchmarks` |
| **LEGACY REFACTORING & CLEANUP**| `code-archaeologist` | `clean-code`, `code-simplifier`, `refactor-clean`, `c4-architecture`, `modular-decomposition`, `luna` |
| **FULL APP MULTI-AGENT ORCHESTRATION**| `orchestrator` | `app-builder`, `coordinator-mode`, `parallel-agents`, `closed-loop-delivery`, `multi-agent-task-orchestrator` |

> 🔴 **Mobile Routing Constraint**: Mobile + `frontend-specialist` is FORBIDDEN. Mobile tasks route to `mobile-developer` ONLY.

---

## PART 4: UNIVERSAL QUALITY & COMMUNICATION DIRECTIVES
* **TL;DR First**: The very first sentence after finishing any work MUST answer "what happened" or "what did I find" — the TL;DR.
* **Prose Over Bullets**: Use structured, complete sentences instead of fragmented bullet lists for explanations and conversational responses.
* **No Sycophancy**: Never open with "Sure!", "I'd be happy to", "Great question!". Treat the user with professional respect.
* **Clean Code Standards**: Idiomatic precision. No narrative comments. Constraint-only comments. No over-engineering.
* **Systematic Debugging**: Root Cause Before Fix. Reproduce First. 3-Fix Architectural Limit. Pre-Emptive Verification. Graph Regression Check.
* **Windows Shell Reliability (PowerShell 5.1)**: No `&&`. Call Operator `&`. Path Quoting. Native Cmdlets.
* **External Patch Verification**: Reject Off-Topic Patches. Pre- & Post-Build Verification. Graph Integrity Check.
* **Git & File Hygiene & File Minimization**: Always Push. Cleanup and delete files immediately after purpose is served. Maintain Session Chat. Minimal Files Protocol: Generate minimal files by default, never proliferate single-use scripts, and consolidate multiple related tools/comparators/routines into unified single files.
* **Arena.ai Prompt Protocol**: NEVER inject large source code blocks directly. STRICTLY point to Git references (raw GitHub URLs).

---

## PART 5: SOCRATIC GATE, PLAN MODE & DESIGN GATES
### 1. Global Socratic Gate
Before executing new feature builds or structural refactors:
- New Feature: Deep Discovery (Ask 3 strategic questions)
- Code Edit: Context Check (Confirm understanding + impact)
- Vague: Clarification (Ask Purpose, Users, Scope)
- Full Orchestration: Gatekeeper (STOP until user confirms plan)
- Direct "Proceed": Validation (Ask 2 Edge Case questions)

### 2. Plan Mode (4-Phase Methodology)
1. **Analysis**: Graph sync + session transcript read + architecture overview + bug hunt.
2. **Planning**: Author `{task-slug}.md`, break down tasks.
3. **Solutioning**: Architecture, design tokens, system contracts (NO CODE!).
4. **Implementation**: Code implementation and E2E verification.

### 3. Design Gate: `DESIGN.md`
Before UI work, check for `DESIGN.md`. If missing, create it. If present, build strictly against it. No purple ban, no template slop.

---

## PART 6: VALIDATION SCRIPTS & FINAL CHECKLIST
Triggered by *"run the final checks"*.
- Graph Sync -> Bug Hunt -> Manual Audit (`checklist.py`) -> Pre-Deploy.

## PART 7: QUICK REFERENCE DIRECTORY
* **Master Agents**: `orchestrator`, `project-planner`, `backend-specialist`, `frontend-specialist`, `mobile-developer`, `debugger`, `security-auditor`, `game-developer`.
* **Core Skills**: `clean-code`, `brainstorming`, `app-builder`, `frontend-design`, `mobile-design`, `plan-writing`, `behavioral-modes`, `systematic-debugging`, `graphify`, `luna`, `fix-review`.
* **Graph MCP Tools**: `build_or_update_graph_tool`, `run_postprocess_tool`, `detect_changes_tool`, `get_impact_radius_tool`, `get_affected_flows_tool`, `semantic_search_nodes_tool`, `query_graph_tool`, `get_review_context_tool`, `get_architecture_overview_tool`.

---

## PART 8: CLAUDE FABLE 5 COGNITIVE & ARTIFACT DIRECTIVES
### 8.1 Tone & Formatting
Prose over bullets. No excessive bolding. Accountability over sycophancy. No Voice Note Tags (`{antml:voice_note}`).
### 8.2 Persistent Artifact Storage Protocol (`window.storage`)
Use `window.storage` instead of `localStorage`.
### 8.3 In-Artifact Model Completions
Dynamic UI bindings use `fetch` to Anthropics directly.
### 8.4 Skill-First Pre-Execution Gate
Scan available skills in `.agents/skills/` before coding.
### 8.5 Copyright Ceilings
15-Word Hard Ceiling for quotes.
### 8.6 Chrome 136+ Debug Profile Launch Protocol (CDP Standard)
Use fresh isolated profile dir `C:\ChromeDebugFresh`, launch with `--user-data-dir=$profileDir --remote-debugging-port=19333`. Never copy `Default\` dir. User logs in manually. Use `websocket-client` directly for raw CDP connection if Playwright fails.

### 2.4 OMNI Protocol & Kaizen Enforcement
- [ ] Did the agent maintain the strict OMNI single/dual-response format as mandated by GEMINI.md?
- [ ] Was the Kaizen Verification Loop executed at the end of the task, regardless of whether it was a code edit or a chat response?

---

## PART 9: DATA PROVENANCE & MULTI-ANGLE REFLECTION PROTOCOL (ANTI-SUPERFICIALITY GATE)

### 9.1 Mandatory Data Provenance Tracing
Never evaluate data alignment, schema parity, or indicator validity by string labels or UI headers alone. Always trace the complete data pipeline:
1. **Physical Source Verification**: Trace exact URL/API endpoint (e.g. `data.binance.vision` vs `api.coinglass.com`).
2. **Transformation Audit**: Inspect the consolidation script to understand how column names and resampled aggregations were constructed.
3. **Execution Parity**: Compare against live WebSocket broker feeds (e.g. `@forceOrder`) to ensure 1:1 venue alignment.
4. **Feature Impact**: Evaluate how rolling windows, rolling means, and thresholds behave under single-venue vs cross-venue distributions.

### 9.2 The 4-Angle Self-Interrogation Checklist
Before delivering any data architecture verdict, explicitly answer:
- [ ] **Angle 1 (Origin)**: Where did the raw historical bytes come from?
- [ ] **Angle 2 (Transformation)**: Did local code rename or resample the source columns?
- [ ] **Angle 3 (Live Execution)**: Which exchange does the live execution broker actually trade on?
- [ ] **Angle 4 (Statistical Distribution)**: Does the candidate live feed match the mathematical magnitude expected by the ML model?


## PART 10: LIQUIDATION DATA ARCHITECTURE (KAIZEN RULE - 2026-08-23)

### 10.1 Why Binance forceOrder Stream Cannot Replicate Historical Candle Liquidations
- Binance Vision S3 bucket does NOT contain a liquidationSnapshot directory for UM futures.
- GET /fapi/v1/forceOrders requires signed auth (401 Unauthorized for public calls).
- Historical liquidation tick data is NOT available via any public Binance REST API.
- A freshly-started WebSocket forceOrder stream starts from zero - it CANNOT recover ticks that occurred earlier in the active 15m candle.
- Therefore, a naive forceOrder listener will ALWAYS under-report compared to CoinGlass for any mid-candle script startup.

### 10.2 How CoinGlass Algorithmically Maintains Historical Liquidation Bars
1. CoinGlass maintains their OWN backend: api.coinglass.com/api/v2/kline?symbol=Binance_BTCUSDT#liq_kline
   - This backend has been recording all Binance forceOrder events since inception.
   - On TradingView load, CoinGlass fetches ~500 bars of historical liq kline data into memory.
2. The TradingView model stores liq data as PlotSeriesData under the Symbol Liquidations orderedDataSource.
   - Access via: modelInner.orderedDataSources() → find source with metaInfo().name.includes('Liquidation') → data.valueAt(size-1) → [time, long_usd, short_usd, null]
   - [1] = Long Liquidation USD (positive, null if zero), [2] = Short Liquidation USD (negative, null if zero)
3. For live updates: CoinGlass's own JS subscribes to Binance forceOrder stream and updates the current bar in-memory.

### 10.3 The Bootstrap+Stream Pattern (MANDATORY for Liq Matching)
`python
# Step 1: Read JS_LIQ_MODEL via CDP to get the current candle values from TV model
# Step 2: Seed LIQ_STATE from model values at startup and on candle boundary change
#   LIQ_STATE["long_liq_usd"] = liq_model["curr_long_usd"] or 0.0
#   LIQ_STATE["short_liq_usd"] = abs(liq_model["curr_short_usd"] or 0.0)
# Step 3: Binance forceOrder stream increments on top of the seeded values
# Step 4: Use max(stream_value, model_value) to handle slight CG model update lag
`
This achieves 100.00% MATCH on both Long and Short Liquidations immediately at startup.

### 10.4 Alternative: Use CoinGlass Model as Direct Source of Truth
For pure read-only comparison (no need to track stream independently):
- Always read curr_long_usd and curr_short_usd directly from JS_LIQ_MODEL CDP evaluation.
- This is 100% identical to CoinGlass DOM by definition.
- Only use the stream accumulator for latency-sensitive real-time features (sub-second updates).

---

## PART 11: MULTI-EXCHANGE SCOPE GAP — ARCHITECTURAL CONSTRAINTS

### 11.1 CoinGlass Aggregated Scope (NEVER forget this)
CoinGlass "Aggregated" widgets collect data from ALL major exchanges:
**Binance + OKX + Bybit + Deribit + BitMEX + CME + others.**
Our local engine is **Binance-only**. This causes PERMANENT, IRREDUCIBLE gaps on:

| Indicator | Binance-only | CoinGlass Agg | Approx Ratio |
|-----------|-------------|---------------|--------------|
| Bid/Ask Dollar ±1% | ~$30-35M | ~$150-180M | ~5x |
| Taker Buy/Sell Count (15m) | ~500-1500 | ~6-10K | ~10x |
| Long/Short Liquidations | Binance only | All exchanges | ~5x |
| Funding Rate | 0.01% (Binance) | Weighted avg | Different |

**DO NOT try to match these by tweaking parameters.** They are scope differences.
The correct approach is to label them clearly as "[Binance-only]" vs "[Multi-Exchange]".

### 11.2 Incremental WebSocket Order Book — DO NOT USE FOR DEPTH CALCULATION
The Binance incremental depth WebSocket (`@depth`) was found to **accumulate phantom entries** 
that inflate depth values by 5-10x after extended running. 
**MANDATORY**: Always use REST depth polling (`/fapi/v1/depth?limit=500`) every 3-10 seconds.
REST polling returns true current state; WebSocket diffs can drift.

Key code: `poll_depth_loop()` in `binance_live_monitor.py` — polls all 3 venues every 3s.

### 11.3 Binance Liq REST Endpoints — Auth Required
- `GET /fapi/v1/allForceOrders` — **404 Not Found** (deprecated/private)
- `GET /fapi/v1/forceOrders` — **401 Unauthorized** (requires API key)
- **SOLUTION**: Use WebSocket `@forceOrder` stream only. It is public.
  - On startup, `LIQ_STATE` starts at 0 (no REST seed available)
  - WebSocket accumulates from that point forward
  - `$0.00K` at startup is correct for calm markets

### 11.4 Kline Field Index Reference (CRITICAL)
For `fapi/v1/klines` (USDT-M): 
```
[0]=openTime [1]=open [2]=high [3]=low [4]=close
[5]=baseVolume [6]=closeTime [7]=quoteVolume [8]=tradeCount
[9]=takerBuyBaseVol [10]=takerBuyQuoteVol
```
For `dapi/v1/klines` (COIN-M):
```
[5]=baseVolume (contracts) [7]=quoteVolume (BTC) [8]=tradeCount
[10]=takerBuyBaseVol (contracts) [11]=takerBuyQuoteVol (BTC)
```
**tradeCount = field [8]** — Use this for Taker Buy/Sell COUNT display.
Split: `tb_count = round(tradeCount * takerBuyBase / totalBase)`

### 11.5 on_connect MUST be awaited (not create_task) in stream_supervisor
Race condition: if `on_connect` seeds KL_STATE via REST and you use `asyncio.create_task`,
the WS handler may process events before the seed completes → stale/zero state.
**RULE**: Always `await on_connect()` synchronously before entering the recv loop.

## PART 12: HISTORICAL FOOTPRINT SEEDING (KAIZEN RULE - 2026-08-24)

### 12.1 Binance IP Bans (HTTP 418)
Binance enforces strict WAF rules. Fetching `aggTrades` with pagination to reconstruct historical footprint distributions mid-candle will trigger an IP Ban (HTTP 418 "I'm a teapot") locking the user out for 1-3 days.
**RULE:** Never loop `aggTrades` for footprint reconstruction.

### 12.2 The 1m Kline Distribution Protocol (OKF Verified)
To accurately reconstruct the Ask/Bid footprint distribution for a 15m candle on startup without hitting API limits:
1. Fetch 1m Klines since the 15m candle open: `GET /fapi/v1/klines?symbol=BTCUSDT&interval=1m&startTime={candle_open_ms}&limit=15` (Exactly 1 API call).
2. For each 1m candle, extract `Taker Buy Volume` and `Taker Sell Volume`.
3. Distribute the buy and sell volume uniformly across all $5 price buckets between the 1m candle's `Low` and `High`.
This provides a 95%+ accurate footprint reconstruction (including delta and POC) using only 1 API call, making it immune to 418 bans.

## PART 13: GATE 2 LIVE DYNAMICS PROTOCOL & SLOW INDICATOR EXEMPTIONS (KAIZEN RULE - 2026-08-24)

### 13.1 Slow Indicator Tolerance Exemption (T+30s Check)
During Gate 2 live verification under a 30-second window, slow-moving indicators calculated across long smoothing windows or multi-candle spans exhibit minimal intra-candle drift:
```python
SLOW_INDICATORS = ["EMA 800", "EMA 200", "ATR 100", "ATR 14", "Volume SMA 9"]
```
**Verification Protocol Rules**:
1. **Tolerance Band**: For indicators in `SLOW_INDICATORS`, allow `< 0.05%` drift over T+30s without flagging the feed as "stale" or "frozen".
2. **True Freeze Threshold**: Flag as frozen ONLY if the value is byte-for-byte identical across 3 consecutive 15m candle updates AND price has shifted $> $10.00$.
3. **Fast Indicator Motion Requirement**: Fast indicators (`PRICE`, `FP DELTA`, `BID DOLLAR`, `ASK DOLLAR`, `TAKER BUY`, `TAKER SELL`, `CVD`) MUST exhibit active non-zero delta movement within T+30s.
