import sys
from datetime import datetime, timezone
from pathlib import Path

def append_history():
    timestamp = datetime.now(timezone.utc).isoformat()
    entry = f"""
---
### Turn: {timestamp}
**User Prompt:**
and we have 2 .agents folder so ensure that you doing changes in both
Also I hope we have skills as well in graph memory for us to call at any time and don't poll to take save tokens

**Assistant Outcome:**
1. Dual Repository Parity Strictly Maintained: Both `.agents/` folders (`Engine_1_arena_PR/.agents/` and `Engine_2/.agents/`) structured simultaneously with identical categorized taxonomy:
   - `invariants/`: System and quantitative mathematical contracts.
   - `architecture/`: Research, context rot paper, and DeepSeek Harness specs.
   - `protocols/`: Autonomous loops, orchestration, and preview preferences.
   - `graph/`: MCP graph memory snapshots (`mcp_graph_memory.json`).
2. DeepSeek Harness Integration: Built `.agents/scripts/deepseek_harness_runner.py` (and mirrored to `Engine_2/.agents/scripts/deepseek_harness_runner.py`) bridging CLI `pnpm run dsh` (headless & web profiles) for zero-lookahead evaluations.
3. Skills Embedded in Graph Memory: Registered 7 primary agentic skills (`Skill_KarpathyGuidelines`, `Skill_CleanCode`, `Skill_DeepSeekHarness`, `Skill_Graphify`, `Skill_Web2API_Swarm`, `Skill_Reticle`, `Skill_SubTurnContextRetrieval`) as live entities and relations inside MCP Knowledge Graph (`memory`).
4. Graph Memory Snapshots Synced: Exported 14 entities and 13 relations to `mcp_graph_memory.json` across both `.agents/memory/graph/` folders.
5. Strict Zero-Polling Rule: No polling loops used; all asynchronous processes rely on native reactive system wakeups to preserve token budget.
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
