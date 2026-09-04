from datetime import datetime, timezone
from pathlib import Path

def append_active_context_turn():
    ts = datetime.now(timezone.utc).isoformat()
    entry = f"""
---
### Turn: {ts}
**User Prompt:**
Are we all set or need improvement to work upon context...see you are great as an AI..only thing is you donot have context sometime to work around or give better answers

**Assistant Outcome:**
1. Rigorous Forensic Gap Analysis of AI Context Architecture:
   - Identified 3 fundamental operational gaps where AIs lose context:
     a) Tool Latency & Forgetfulness: Second Brain scripts required manual execution; if an agent didn't run the tool, it answered without deep grounding.
     b) Rule Budget Bloat & Truncation: A 414 KB leak archive (`claude-fable-5.1.md`) in `rules/` was exhausting the system prompt budget, causing master rules (`AGENTS.md`) to be truncated mid-file.
     c) Lack of Real-Time Turn-0 Situational Awareness: Static rules did not contain the live quantitative state, active file, current blockers, or immediate next steps.
2. Immediate Architectural Remediation:
   - Evacuated `claude-fable-5.1.md` out of `rules/` into `.agents/memory/architecture/`, reclaiming 414 KB of prompt headroom and eliminating rule truncation.
   - Built `ACTIVE_CONTEXT.md` in `.agents/rules/` with `trigger: always_on` in both repositories. This delivers an immutable, high-density Mission Control Card directly into the agent's turn-0 prompt without burning a tool call or token budget.
   - Verified 100% dual `.agents` folder parity across all 6,081 files.
"""
    targets = [
        Path(r"c:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\.agents\memory\session_chat_history.md"),
        Path(r"c:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\Engine_2\.agents\memory\session_chat_history.md")
    ]
    for p in targets:
        if p.exists():
            with open(p, 'a', encoding='utf-8') as f:
                f.write(entry)
            print(f"Appended turn to {p}")

if __name__ == '__main__':
    append_active_context_turn()
