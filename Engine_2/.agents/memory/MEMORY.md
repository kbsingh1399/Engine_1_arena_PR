# 🧠 INSTITUTIONAL MEMORY & ARCHITECTURE INDEX
> **Dual Memory Architecture**: Open Knowledge Format (OKF) + Graph Memory (MCP & Graphify) + Structured Context Subdirectories.
> **Dual Repository Parity**: Active simultaneously across `Engine_1_arena_PR/.agents/` and `Engine_2/.agents/`.

---

## 1. Master Operational Protocols
- **[MANDATORY] DeepSeek Harness Integration**: DeepSeek Harness (`deepseek-harness/`) is permanently active. All multi-agent evaluations, benchmark verification loops, and code gates must be routed through `deepseek_harness_runner.py` or `pnpm run dsh` → `architecture/AGENT_FRAMEWORKS_ARCHITECTURE.md`
- **[MANDATORY] Multi-Agent Orchestration (/orchestrate)**: Always simulate/execute a minimum of 3 specialist agents (Planning/Strategy, Core Implementation/Math, QA/Verification) → `protocols/OPERATIONAL_PREFERENCES.md`
- **[MANDATORY] Graph Memory & AST Verification**: Graph Memory is active across two layers:
  1. Relational Knowledge Graph via MCP `memory` (`mcp_graph_memory.json`)
  2. AST Code Knowledge Graph via Graphify (`graphify-out/graph.json`)
  Always check knowledge nodes before modifying code symbols → `graph/mcp_graph_memory.json` & `.agents/rules/graphify.md`
- **[MANDATORY] Context Rot Prevention**: Strict adherence to the 5-tier Anti-Context-Rot stack (Hierarchical Indexing via `SESSION_CONTEXT_MAP.md`, sub-turn retrieval via `second_brain.py`, invariant state freezing, zero paid API token swarms via local `gemini-web2api` on port 8081).
- **[MANDATORY] Dual `.agents` Folder Parity**: Every rule, script, memory update, and prompt modification MUST be applied simultaneously to both `Engine_1_arena_PR/.agents/` and `Engine_2/.agents/`.

---

## 2. Directory Taxonomy & Navigation Map

```
.agents/memory/
├── MEMORY.md                          # Master Directory Index & Operational Contracts
├── SESSION_CONTEXT_MAP.md             # Token-Optimized 7-Phase Milestone Registry (<1k tokens)
├── session_chat_history.md            # Comprehensive Turn-by-Turn Transcript & Audit Archive (1.59 MB)
│
├── invariants/                        # Immutable System & Mathematical Contracts
│   └── SYSTEM_INVARIANTS.md           # Unified: CoinGlass S9/L_1 Layout, Fee Friction, Ratchet & Project Conventions
│
├── architecture/                      # Research Papers, Model Architecture & Engine Specs
│   ├── AGENT_FRAMEWORKS_ARCHITECTURE.md # Unified: Claude Code Architecture, DeepSeek Harness & V3/R1 Reasoning Core
│   ├── claude_fable_5_1_directives.md # Autonomous Multi-Agent Loop Specifications
│   ├── trading_knowledge_base.md     # 29-Node Institutional Trading Second Brain (68.9 KB)
│   └── raw_transcripts.json          # Verbatim Transcripts for all 24 YouTube Trading Cruxes (212 KB)
│
├── protocols/                         # Execution Guidelines, Security, & Skill Directives
│   ├── autonomous_loop_protocol.md   # Autonomous Agent Execution Engine & Recovery Loops
│   ├── OPERATIONAL_PREFERENCES.md     # Unified: Chrome Preview Mode, /orchestrate Defaults & Threat Model
│   └── skills_stack.md                # 37-Skill Engineering & Pocock Agentic Taxonomy
│
└── graph/                             # Graph Memory & Knowledge Graph Snapshots
    └── mcp_graph_memory.json          # Exported Persistent MCP Knowledge Graph (14 Entities, 13 Relations)
```

---

## 3. Core Strategy Invariants (Engine 2)
- **Universe**: 18 Institutional Binance USDT-M Perpetuals (3,464,074 15-minute candles, 0 nulls, strictly monotonic timestamps).
- **Validation**: 20 Non-Overlapping Out-Of-Sample (OOS) Walk-Forward Windows (2021–2026) with strictly causal 72-hour trade resolution purge boundaries ($t_{\text{purge}} = t_{\text{start}} - 72\text{h}$).
- **The Confluence Formula**: Long Liq Z-Score > 1.8 + Spot CVD Divergence > 0.8 + $\Delta\text{Spot} > 0 \land \Delta\text{Futures} < 0$ + RSI < 40 + VWAP Z < -0.5.
- **Microstructure Ratchet**: Phase 0 Breakeven Ratchet at $+0.8\text{R} \to +0.15\text{R}$ (eliminates 22.9% retracement trap); Phase 1 Lock at $+1.5\text{R} \to +0.80\text{R}$; Target $+2.5\text{R}$; 24-bar time decay.
- **Fixed Portfolio Risk Budget**: Initial Capital $5,000, Base Risk $25, House Money $50 (max 2×), Drawdown Limit 4.5% ($225 hard stop), Max Concurrent Positions = 2.
- **Anti-Lookahead Blacklist**: Zero lookup tables (`winning_configuration.json`, `s1_status.json`), zero external status caches, zero test-set `nlargest` overrides.
