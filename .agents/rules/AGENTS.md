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

---

# PART 1: THE KAIZEN VERIFICATION LOOP

## 1.1 Continuous Verification & Rule Updating
To ensure the system continuously learns and updates its protocols without blowing past character limits, you must execute this verification loop at the end of every task:

1. **Evaluate Outcome**: After completing a task or applying a code fix, explicitly evaluate if it succeeded or failed (e.g. did the script crash? Did the CDP connection fail?).
2. **Identify Pattern**: If the failure or success reveals a new architectural constraint, Windows PowerShell quirk, or API limitation not currently documented, you MUST formulate a new rule.
3. **Persist the Rule**: Use the `replace_file_content` or `run_command` tool to safely append the new rule into `C:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\.agents\rules\FABLE5_CHECKLIST.md` under the appropriate section. 
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