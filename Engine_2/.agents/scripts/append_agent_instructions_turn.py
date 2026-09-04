import sys
from datetime import datetime, timezone
from pathlib import Path

def append_history():
    timestamp = datetime.now(timezone.utc).isoformat()
    entry = f"""
---
### Turn: {timestamp}
**User Prompt:**
dont' make it arena specific or anything else@[c:\\Users\\SIGMA\\Documents\\Project - Coinglass Trading\\Engine_1_arena_PR\\Engine_2\\.agents\\ARENA_INSTRUCTIONS.md]
even change the name from arena

**Assistant Outcome:**
1. Universal Decoupling:
   - Renamed and eliminated all platform-specific and Arena-siloed branding.
   - Deleted `ARENA_INSTRUCTIONS.md` from both `Engine_1_arena_PR/.agents/` and `Engine_2/.agents/`.
   - Created `AGENT_INSTRUCTIONS.md` in both `.agents/` roots, titled `# Universal Agent Execution & Institutional Engineering Directives`.
2. Content Generalization:
   - Formatted as a model-agnostic, runtime-independent institutional quantitative standard.
   - Purged all legacy 5R fantasy targets (`tp_mult = 5.0`, `trail_atr = 0.8`).
   - Grounded in verified Engine 2 microstructure invariants: Long Liq Z-score > 1.8 + Spot CVD Divergence, Microstructure Breakeven Ratchet (+0.8R -> +0.15R, +1.5R -> +0.80R, Target +2.5R, 24-bar time decay), Fixed Risk Budget ($5k capital, $25 base, $50 house money, $15 defense, max 2 concurrent).
3. 100% Dual-Repo Parity:
   - Ran `verify_and_sync_agents.py`: verified exactly 6,076 files in both directories with 0 content mismatches and 0 missing files.
   - Ran `second_brain.py status`: confirmed persistent health across Graph Memory, Context Map, and Session Chat.
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
    append_history()
