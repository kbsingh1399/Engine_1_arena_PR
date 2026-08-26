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
