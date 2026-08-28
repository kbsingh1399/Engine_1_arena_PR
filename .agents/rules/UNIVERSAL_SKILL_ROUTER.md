---
trigger: always_on
---

# 🌐 UNIVERSAL SKILL ROUTER (ALWAYS-ON)

> **MANDATORY PROTOCOL:** This rule file is triggered on EVERY prompt. You CANNOT bypass this protocol. 
> To prevent context amnesia and ensure high-fidelity engineering, you MUST dynamically discover and load relevant repository methodologies and skills BEFORE proposing solutions or writing any code.

## 🔴 THE FORCED SKILL-LOADING LOOP (Execute Immediately)

On every single turn, before doing anything else, you must execute the following 3 steps:

### STEP 1: Domain Classification
Analyze the user's request and classify it into one or more of the following core domains:
- `Data/ML/Quant` (e.g., Pandas, XGBoost, Optuna, Dataflow)
- `Backend/Architecture` (e.g., Python, FastAPI, API Design, System Architecture)
- `Frontend/UI` (e.g., React, UI Design, CSS)
- `Security/Testing/QA` (e.g., TDD, Security Scan, Pytest)
- `DevOps/Cloud` (e.g., GCP, CI/CD, Deployment)

### STEP 2: Dynamic Skill Discovery
You MUST search the installed skills directories (`.agents/skills/` and `C:\Users\SIGMA\.gemini\config\skills`) to find at least **2 highly relevant skills** for the classified domain.
- *Tip:* Use `list_dir` or refer to your internal `Available skills` list.
- Look for premium methodologies like `karpathy-guidelines`, `clean-code`, `systematic-debugging`, or domain-specific skills (e.g., `agent-data-ml-model`).

### STEP 3: Core Orchestration & Framework Validation
Before finalizing skill selection, you MUST check if the task intersects with our installed high-end orchestration frameworks. You MUST actively query and load methodologies for:
- `DeepSeek Harness` (Evaluation & Multi-agent execution)
- `Claude Code` (Dynamic Prompt Boundary Caching, Proactive Loops, Verification Agent)
- `Serena` / `Pony` / `Arena` (Advanced reasoning, routing, and deployment constraints)
- `Prime Intellect` (Compute & large-context synthesis)
- `Hermes` (Agent loops & delegation)
If applicable, prioritize loading their specific rule files (e.g., from `AGENTS.md` or `.agents/rules/`) or their corresponding `SKILL.md`.

### STEP 4: Mandatory Load
You MUST use the `view_file` tool to physically load and read the `SKILL.md` or rule file for the selected methodologies. 
- *Rule:* You cannot assume you know what is in the skill file. You must explicitly load it into context.

---

## 📝 OUTPUT REQUIREMENT (Strict Formatting)

At the very top of your final response to the user, you MUST include a header confirming which skills you dynamically loaded and applied, using this exact format:

```markdown
> 📚 **Active Skills Loaded & Applied:** `@[skill-1]`, `@[skill-2]`
```

If you fail to include this header, or if you failed to physically read the skill files before responding, your execution is considered a **TOTAL FAILURE**.
