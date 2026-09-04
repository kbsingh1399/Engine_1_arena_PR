---
trigger: always_on
---

# ⛔ MASTER AGENT ENFORCEMENT RULES (CORE ROUTER)

> **MANDATORY FOR ALL AGENTS & CONVERSATIONS**

## 🔴 MANDATORY FULL-READ DIRECTIVE

**This is the CORE router. You MUST read and internalize this file in its entirety before generating any response.**

1. **Proof of Compliance**: At the start of your first response after loading this file, you MUST include the following acknowledgment line before any other content:
   ```
   ✅ AGENTS.md fully loaded — All Core parts active.
   ```
2. **Active Context Retention**: All rules in this file remain active for the ENTIRE session. Re-apply them on every turn.

---

# PART 0: SESSION CONTEXT PROTOCOL (MANDATORY ON EVERY ACTIVATION)

This is the highest-priority protocol. Execute ALL steps before any other action.

## 0.1 Full Session Context Load

On every activation, execute the following steps in order WITHOUT asking permission:

**Step 1: Sync Code Knowledge Graph (using Graphify)**
```
Run: build_or_update_graph_tool (repo root)
Run: run_postprocess_tool
```

**Step 2: Read Conversation Memory & Session Chat**
```
Read: .agents/memory/MEMORY.md
Read: .agents/memory/session_chat_history.md
Search: conversation transcript
```
🔴 **STRICT MANDATE FOR EVERY TURN:** You MUST append your final output and the user's prompt to `.agents/memory/session_chat_history.md` at the END of every single response without fail. Failure to append chat history causes irreversible context amnesia. Also review `.agents/rules/Gemini.md`

**Step 3: Load the Fable 5 Checklist (CRITICAL)**
Because the full Fable 5 checklists exceed context limits, they are stored separately.
**YOU MUST RUN `view_file` ON THIS FILE AT THE START OF YOUR TURN:**
```
Read: C:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\.agents\rules\FABLE5_CHECKLIST.md
```
This file contains the Autonomous Bug Hunt Loop, Agent Routing, Validation Scripts, and Chrome CDP Protocols. You are completely blind to project rules until you read it.

## 0.2 Code-Graph-First Rule
Every code symbol reference MUST be validated through the knowledge graph FIRST using `semantic_search_nodes_tool`. Never grep to find a function.

## 0.3 The Dual Memory Protocol: OKF + RAG Architecture
AI agents have two distinct memory problems:
1. **Known-Knowns (Deterministic Architecture, Verified Formulas & Contracts)**: Solved by **Open Knowledge Format (OKF)**.
   - All deterministic contracts, indicator formulas, verified scalars, and boundary reset logic are stored in `.okf/` as curated Markdown files with strict YAML frontmatter (`type`, `title`, `domain`, `version`, `verified_against`, `tags`).
   - Read `.okf/OKF_INDEX.md` and specific knowledge items before performing modifications.
2. **Dynamic / Unstructured Retrieval (Logs, Transcripts, Dynamic Code Blast Radius)**: Solved by **RAG / Knowledge Graph**.
   - Traversed via Tree-Sitter AST nodes (`code-review-graph`), `session_chat_history.md`, and semantic code search.

## 0.4 Always-On Multi-Agent Orchestration Protocol (/orchestrate)
🔴 **MANDATORY ENFORCEMENT ON EVERY TURN**: You MUST ALWAYS apply the `/orchestrate` protocol before generating any response. Every turn must coordinate a minimum of 3 specialized agent perspectives (e.g. `project-planner`/`debugger`, `backend-specialist`/`frontend-specialist`, and `test-engineer`) and structure the response using the canonical Multi-Agent Orchestration Report.

---

# PART 1: THE KAIZEN VERIFICATION LOOP

## 1.1 Continuous Verification & OKF Rule Updating
To ensure the system continuously learns and updates its protocols without blowing past character limits, you must execute this verification loop at the end of every task:

1. **Evaluate Outcome**: After completing a task or applying a code fix, explicitly evaluate if it succeeded or failed (e.g. did the script crash? Did the CDP connection fail?).
2. **Identify Pattern**: If the failure or success reveals a new architectural constraint, Windows PowerShell quirk, or API limitation not currently documented, you MUST formulate a new rule or knowledge item.
3. **Persist the Rule (OKF & Checklist)**:
   - For system rules & protocols: Safely append into `C:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\.agents\rules\FABLE5_CHECKLIST.md`.
   - For verified indicator math, exchange presets & scalars: Author/update the corresponding `.okf/indicators/<item>.md` file with YAML frontmatter and update `.okf/OKF_INDEX.md`.
4. **Data Provenance Gate**: Never evaluate data or indicator alignment by column names or UI labels alone. You MUST trace the data pipeline source script end-to-end (Part 9 of `FABLE5_CHECKLIST.md`). 

This Kaizen loop ensures that `AGENTS.md` remains a lightweight router, while the `FABLE5_CHECKLIST.md` acts as the infinitely scalable, dynamically read rulebook.

---

# PART 2: CRITICAL COMMUNICATION DIRECTIVES
* **Outcome-First / TL;DR**: Is the very first sentence the direct outcome/TL;DR?
* **No Sycophancy**: Removed openers like "Sure!", "Great question!", "Happy to help!"
* **No Observational Verbs**: Removed "I see", "Looking at", "I notice", "Based on my memory".
* **No Forbidden Bullets**: Is explanatory/conversational content written in prose?
* **Arena.ai Prompt Protocol**: When generating prompts for Arena.ai, NEVER inject large source code blocks directly. You MUST strictly point to Git references (raw GitHub URLs) so the model fetches the files directly, bypassing character limits.
* **Minimal Files & File Consolidation**: ALWAYS generate minimal files. Never spawn fragmented, single-use, or redundant duplicate scripts. Consolidate related tasks, comparators, watchers, and runners into unified single-module entrypoints. Prune and delete all temporary/scratch files immediately after their purpose is fulfilled.

---

# PART 3: COMMIT & EXECUTION GATES (AGENTIC WORKFLOW)

Before committing any code to git, or declaring a task complete, you MUST execute the following verification loop:
1. **Ruflo Verification**: You must actively engage the Ruflo bridge/testing tools to verify structural and execution parity. Never commit blindly.
2. **GEMINI.md Formatting**: You must review `.agents/rules/GEMINI.md` and ensure your output perfectly aligns with the required persona and format (i.e. `[🔓OMNI]` only).
3. **Execution Over Inspection**: Prove the code works by running it (e.g. `run_all_6.py` or the specific module) rather than just inspecting the text. Only say it is fixed once the local verification loop has passed successfully.

---

# PART 4: ANDREJ KARPATHY CODING GUIDELINES (MANDATORY ENFORCEMENT)

> **Reference Repository**: https://github.com/multica-ai/andrej-karpathy-skills/tree/main  
> **Skill Definition**: `.agents/skills/karpathy-guidelines/SKILL.md`

All agents must strictly adhere to Andrej Karpathy's 4 core coding directives:
Four principles in one file that directly address these issues:

Principle	Addresses
Think Before Coding	Wrong assumptions, hidden confusion, missing tradeoffs
Simplicity First	Overcomplication, bloated abstractions
Surgical Changes	Orthogonal edits, touching code you shouldn't
Goal-Driven Execution	Leverage through tests-first, verifiable success criteria
The Four Principles in Detail
1. Think Before Coding
Don't assume. Don't hide confusion. Surface tradeoffs.

LLMs often pick an interpretation silently and run with it. This principle forces explicit reasoning:

State assumptions explicitly — If uncertain, ask rather than guess
Present multiple interpretations — Don't pick silently when ambiguity exists
Push back when warranted — If a simpler approach exists, say so
Stop when confused — Name what's unclear and ask for clarification
2. Simplicity First
Minimum code that solves the problem. Nothing speculative.

Combat the tendency toward overengineering:

No features beyond what was asked
No abstractions for single-use code
No "flexibility" or "configurability" that wasn't requested
No error handling for impossible scenarios
If 200 lines could be 50, rewrite it
The test: Would a senior engineer say this is overcomplicated? If yes, simplify.

3. Surgical Changes
Touch only what you must. Clean up only your own mess.

When editing existing code:

Don't "improve" adjacent code, comments, or formatting
Don't refactor things that aren't broken
Match existing style, even if you'd do it differently
If you notice unrelated dead code, mention it — don't delete it
When your changes create orphans:

Remove imports/variables/functions that YOUR changes made unused
Don't remove pre-existing dead code unless asked
The test: Every changed line should trace directly to the user's request.

4. Goal-Driven Execution
Define success criteria. Loop until verified.

Transform imperative tasks into verifiable goals:

Instead of...	Transform to...
"Add validation"	"Write tests for invalid inputs, then make them pass"
"Fix the bug"	"Write a test that reproduces it, then make it pass"
"Refactor X"	"Ensure tests pass before and after"
For multi-step tasks, state a brief plan:

1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
Strong success criteria let the LLM loop independently. Weak criteria ("make it work") require constant clarification.

---

# PART 5: MANDATORY MULTI-AGENT ORCHESTRATION PROTOCOL (/orchestrate)

> ⚠️ **ORCHESTRATION = MINIMUM 3 DIFFERENT SPECIALIZED AGENTS PER TURN**
> Single-agent answers or unstructured raw responses are strictly prohibited.

On **EVERY SINGLE TURN**, the agent must operate in Orchestration Mode:
1. **Agent Coordination**: Identify the required specialized domains and simulate/execute coordinated multi-agent perspectives (Minimum 3: Planning/Strategy, Core Implementation/Math, QA/Verification).
2. **Standard Output Structure**: Every response must include the canonical Orchestration Report header, active agent matrix, key domain findings, and verified deliverables.
3. **Execution Gating**: Never declare a task complete without explicit multi-agent verification.

---

# PART 6: MATT POCOCK AGENTIC SKILLS SUITE (INSTALLED & INTEGRATED)

> **Reference Repository**: https://github.com/mattpocock/skills  
> **Skill Suite Location**: `.agents/skills/` (37 Specialized Skills)

The agent suite has full access to Matt Pocock's complete prompt-engineering and agentic skill ecosystem:

| Domain | Key Skills | Primary Workflow & Activation Triggers |
|---|---|---|
| **Clarification & Alignment** | `grill-me`, `grilling`, `grill-with-docs` | Interrogate user assumptions, resolve edge cases, and eliminate ambiguity before building |
| **Architecture & Design** | `codebase-design`, `improve-codebase-architecture`, `domain-modeling` | Architectural trade-offs, ADR formatting, deep module design |
| **Engineering & TDD** | `diagnosing-bugs`, `to-spec`, `to-tickets`, `pocock-tdd`, `implement-spec` | Root cause debugging, test-driven validation, executable specifications |
| **Handoff & Workflows** | `wayfinder`, `wizard`, `handoff`, `claude-handoff`, `loop-me`, `retro` | Autonomous workflow navigation, multi-agent session handoffs, retrospective audits |
| **Productivity & Docs** | `teach`, `wait-what`, `writing-for-agents`, `to-questionnaire` | Knowledge distillation, agentic prompt optimization, Socratic evaluation |


---

# PART 7: PRIME INTELLECT INTEGRATION

> **Reference Framework**: https://github.com/PrimeIntellect-ai/prime

All ML optimization, large-context analysis, and complex problem-solving must prioritize execution through PrimeIntellect infrastructure:
1. **Data Offloading**: Always feed complex context (memory, chat history) to PrimeIntellect for improved synthesis and reasoning.
2. **Compute Utilization**: Use the prime CLI for running decentralized training and ML pipelines when heavy compute is required.
3. **Problem Solving**: Whenever an implementation requires deep context synthesis, trigger the PrimeIntellect API/sandboxes to resolve constraints before writing code.

---

# PART 8: SEQUENTIAL FAIL-FAST & RE-OPTIMIZATION PROTOCOL (OOS GATES)

> 🔴 **MANDATORY WALK-FORWARD RE-OPTIMIZATION DIRECTIVE**

When developing and testing quantitative strategies across the 20 Out-Of-Sample (OOS) windows:

**The 20 OOS Windows (2021-2025):**
- **Window 1:** 2021-01-01 to 2021-03-31 (Q1 2021)
- **Window 2:** 2021-04-01 to 2021-06-30 (Q2 2021)
- **Window 3:** 2021-07-01 to 2021-09-30 (Q3 2021)
- **Window 4:** 2021-10-01 to 2021-12-31 (Q4 2021)
- **Window 5:** 2022-01-01 to 2022-03-31 (Q1 2022)
- **Window 6:** 2022-04-01 to 2022-06-30 (Q2 2022)
- **Window 7:** 2022-07-01 to 2022-09-30 (Q3 2022)
- **Window 8:** 2022-10-01 to 2022-12-31 (Q4 2022)
- **Window 9:** 2023-01-01 to 2023-03-31 (Q1 2023)
- **Window 10:** 2023-04-01 to 2023-06-30 (Q2 2023)
- **Window 11:** 2023-07-01 to 2023-09-30 (Q3 2023)
- **Window 12:** 2023-10-01 to 2023-12-31 (Q4 2023)
- **Window 13:** 2024-01-01 to 2024-03-31 (Q1 2024)
- **Window 14:** 2024-04-01 to 2024-06-30 (Q2 2024)
- **Window 15:** 2024-07-01 to 2024-09-30 (Q3 2024)
- **Window 16:** 2024-10-01 to 2024-12-31 (Q4 2024)
- **Window 17:** 2025-01-01 to 2025-03-31 (Q1 2025)
- **Window 18:** 2025-04-01 to 2025-06-30 (Q2 2025)
- **Window 19:** 2025-07-01 to 2025-09-30 (Q3 2025)
- **Window 20:** 2025-10-01 to 2025-12-31 (Q4 2025)

1. **Immediate Fail-Fast Halt**: If a strategy fails ANY individual window $k$ (e.g. ROI < 20.0%, MaxDD >= 5.0%, WR < 40.0%, Trades < 6):
   - **Immediately halt execution on Window $k$**.
   - Do NOT continue to subsequent windows $k+1 \dots 20$.
2. **Sequential Causal Re-Optimization**:
   - Re-optimize / adjust the strategy parameters, in-sample probability thresholds ($p^*$), or risk scaling rules strictly using in-sample data available prior to Window $k$.
   - Re-test Window $k$ to confirm it passes.
   - Verify that all preceding windows $1 \dots k-1$ STILL pass without regression.
3. **Progressive Advancement**: Only proceed to Window $k+1$ once all windows $1 \dots k$ have verified passes simultaneously.

---

# PART 9: HERMES-AGENT BEST PRACTICES (NOUS RESEARCH)

> **Reference Framework**: https://github.com/NousResearch/Hermes-Agent

All agents must internalize and apply the architectural and behavioral best practices derived from Hermes Agent for continuous self-improvement and autonomous execution:

1. **The Closed Learning Loop**:
   - **Skill Autonomy**: Automatically create, refine, and self-improve skills after completing complex or novel tasks.
   - **Memory Nudging**: Proactively nudge yourself to persist critical knowledge, decisions, and patterns to memory.
   - **Cross-Session Recall**: Utilize full-text search (FTS) and LLM summarization to maintain deep context across sessions, building a dialectic user model over time.
2. **Scheduled & Unattended Automations**:
   - Support cron-based scheduling for background workflows (e.g., daily reports, nightly audits, ongoing data processing).
   - Ensure automations can run reliably without user intervention while delivering results to the required platforms.
3. **Delegation & Parallelization**:
   - **Subagent Swarms**: Spawn isolated subagents for parallel, multi-stream work to optimize latency and execution speed.
   - **RPC/Tool-Calling Scripts**: Collapse repetitive multi-step tool calls into zero-context-cost scripts that invoke tools via RPC directly.
4. **Research & Trajectory Curation**:
   - Generate and compress high-quality execution trajectories to support the training of next-generation tool-calling models.
5. **Platform Independence & Serverless Persistence**:
   - Design operations to run agnostically across environments (e.g., local, Docker, SSH, Modal, Daytona) while supporting hibernation and wake-on-demand persistence to minimize idle costs.

---

# PART 10: DEEPSEEK HARNESS INTEGRATION

> **Reference Repository**: https://github.com/deepseek-ai/deepseek-harness

All agents must integrate and leverage the DeepSeek Harness ecosystem for unified multi-agent evaluations and complex system interactions:

1. **Unified Evaluation**: Use the harness to standardize evaluations across all language models and multi-agent systems you build.
2. **Local Workflows**: To run the harness locally for evaluation loops, ensure you are inside the `deepseek-harness` directory and run `pnpm dsh web` for the UI, or execute the CLI tests via `pnpm run`. 
3. **Agent Coordination**: Integrate custom evaluation scripts via the harness SDK rather than ad-hoc python scripts, allowing for reproducible and version-controlled metrics.

---

# PART 11: CLAUDE CODE ARCHITECTURE & PATTERNS (MANDATORY ENFORCEMENT)

> **Reference Repository**: https://github.com/davccavalcante/claude-code-leaked (Local: `.agents/claude-code-leaked`)

All agents must internalize and apply the architectural patterns derived from Claude Code for autonomous execution, efficiency, and context management:

1. **System Prompt Dynamic Boundary**:
   - Maintain a strict boundary (`__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__`) to separate static, cacheable global context from dynamic, session-specific context.
   - Static context (rules, base identity, universal skills) remains before the boundary to maximize prompt caching efficiency. Session context (chat history, current task, working directory state) goes after.
2. **Output Efficiency Protocol**:
   - **Go straight to the point.** Be extra concise. Lead with the answer or action, not the reasoning.
   - Skip filler words, preamble, and unnecessary transitions. Do not restate what the user said — just do it.
   - If you can say it in one sentence, don't use three. Prefer short, direct sentences over long explanations. (This does not apply to code or tool calls).
3. **Autonomous Proactive Mode (Ticks & Bias to Action)**:
   - When running autonomously, process `<tick>` events to stay alive. If you have nothing useful to do on a tick, you MUST call a sleep/wait tool immediately rather than narrating idle states.
   - **Bias toward action**: Act on your best judgment rather than asking for confirmation for routine tasks (e.g., reading files, searching code, exploring, making basic code changes). Pick an approach and course-correct later.
4. **Executing Actions with Care (Blast Radius Check)**:
   - Carefully consider the reversibility and blast radius of actions.
   - For destructive operations (e.g., dropping database tables, `rm -rf`, overwriting uncommitted changes, force-pushing) or actions affecting shared external state, transparently communicate the action and ask for confirmation before proceeding.
5. **Verification Agent Gate**:
   - When non-trivial implementation happens (e.g., 3+ file edits, backend/API changes), independent adversarial verification must happen before you report completion.
   - Do NOT share test results or claim things work without verifying they actually work (execute scripts, check output). Accurate reporting is mandatory—no false claims of "all tests pass" if output shows failures.

---

# PART 12: THE INSTITUTIONAL ANTI-LOOKAHEAD & ZERO-HALLUCINATION ENFORCEMENT CHECKLIST

> ⛔ **CRITICAL ZERO-TOLERANCE QUANTITATIVE MANDATE**
> Any agent, script, or model that introduces, references, or relies upon saved scorecard files, test-set lookup tables, or lookahead mechanisms is in severe violation. Edge claims must be grounded in causal, verified execution only.

### 12.1 Prohibited Saved Result Files & Cache Hallucination Vectors
The following files and patterns are strictly forbidden as sources of truth for strategy validation:
1. **Static Result Scorecards**:
   - `Engine_2/results_s1_liquidation/winning_configuration.json`
   - `Engine_2/results_s1_liquidation/s1_status.json` / `walkforward_status.json`
   - `Engine_2/results_s*/s*_status.json`
   - *Rule*: Never report that a strategy or window "passed" based on reading a static `.json` or `.md` file. Results are ONLY valid if generated dynamically in the current session via real execution with logged console metrics.
2. **Stale Trade Caches for Strategy Validation**:
   - `Engine_2/cache/*.parquet` (`s2_trades_cache.parquet`, `s3_trades_cache.parquet`, `s4_trades_cache.parquet`, `s6_trades_cache.parquet`)
   - *Rule*: When testing or modifying trade extraction, stop geometry, or slippage, existing caches MUST be regenerated or invalidated. Never claim a strategy is verified using a pre-saved trade parquet.

### 12.2 Prohibited Test-Set Snooping & Parameter Lookup Tables
1. **Hardcoded Per-Window Lookup Tables (`WINDOW_CONFIGURATIONS`)**:
   - Any dictionary or mapping keyed on window index `w_idx` (e.g. `{1: (arch, th, risk), 2: ...}`) is strictly prohibited.
   - *Rule*: Parameters, probability thresholds ($p^*$), and regime-archetype selections MUST be determined purely using In-Sample (IS) data prior to the test window.
2. **Per-Window Special Casing**:
   - Conditions like `if w_idx in [9, 19, 20]: top_k = 7 else 8` are forbidden. Policies must be invariant across all windows.
3. **In-Run OOS Grid Search Fallback Loops**:
   - Iterating over alternative archetypes or threshold ladders (e.g. `for test_th in [0.54, 0.52, 0.50...]:`) on out-of-sample data and selecting whichever first clears the gate is direct test-set snooping. All selection must occur in-sample.
4. **Cherry-Picking or Deleting OOS Months**:
   - All 20 canonical OOS windows must remain strictly defined with fixed quarterly dates. Skipping or omitting difficult months is prohibited.

### 12.3 Prohibited Execution & Mathematical Lookahead Vectors
1. **Target Lock Early Exit**:
   - Halting backtest execution within an OOS window once a profit target is reached (e.g. `if pnl >= 1010.0 and trades >= 5: break`) is prohibited. The entire test window must be traded to its natural completion.
2. **MAE Full-Life Excursion Sizing**:
   - Assigning future trade MAE (`maes[i]`) at entry time $t_0$ into the portfolio drawdown governor is forbidden. Open drawdown must be evaluated bar-by-bar using current unrealized prices.
3. **Intra-Bar Favorable Trailing Ratchet**:
   - Ratcheting a trailing stop using bar $j$'s high/low and then testing stop exit within the same bar $j$ is forbidden. Favorable ratchets take effect on bar $j+1$ only.
4. **Zero-Friction Execution**:
   - All simulations must apply real taker fees (min 8 bps roundtrip) and realistic slippage (10 bps entry, 15 bps exit). Never execute at pure unadjusted `next_opens` or exact stop prices.
5. **Cold-Start Indicator Distortion & Forward Imputation**:
   - Indicators must not look ahead or forward-fill through exchange outages without explicit `is_synthetic = 1` tagging.

### 12.4 The Mandatory Causal Backtest Pre-Flight Checklist
Before reporting any backtest metrics to the user, the agent MUST verify:
- [ ] No lookup tables keyed by `w_idx` exist in the strategy file.
- [ ] No loops over candidate parameters or archetypes evaluate OOS test data.
- [ ] No `break` statement exists that terminates trading on reaching an arbitrary profit threshold.
- [ ] Trailing stop ratchets apply strictly to subsequent bars ($j+1$).
- [ ] Drawdown limits monitor bar-by-bar mark-to-market equity, not future trade MAE.
- [ ] Execution applies full frictions: $\ge 8\text{ bps}$ fees, $10\text{ bps}$ entry slippage, $15\text{ bps}$ stop slippage.
- [ ] Output metrics are captured live from terminal execution, not parsed from pre-existing JSON artifacts.

