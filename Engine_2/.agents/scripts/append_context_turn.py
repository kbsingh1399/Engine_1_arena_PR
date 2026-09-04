from datetime import datetime, timezone
from pathlib import Path

def append_context_turn():
    ts = datetime.now(timezone.utc).isoformat()
    entry = f"""
---
### Turn: {ts}
**User Prompt:**
And I hope before you respond etc...you first refer to memory or chat etc for context to build context

**Assistant Outcome:**
1. Grounded & Verified Pre-Response Context Protocol:
   - Formally reinforced the mandatory Step 2 boot sequence from AGENTS.md Part 0.2: on every turn, before answering, the agent must query Memory, Context Map, and Session Chat.
   - Verified active tri-layer Second Brain recall via `second_brain.py query "context"`:
     - Layer 1 (Graph Memory): Relational entities (ContextRotMitigation, ContextRotArchitecture, S1 Strategy, 18-Asset architecture).
     - Layer 2 (Executive Invariants): `SESSION_CONTEXT_MAP.md` 7-phase milestone registry.
     - Layer 3 (Granular Session History): Chronological turn archive in `session_chat_history.md`.
2. Re-affirmed Non-Volatile Grounding:
   - Regardless of context compaction or 1M+ token window rot, all decisions are grounded in frozen invariants and empirical baselines.
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
    append_context_turn()
