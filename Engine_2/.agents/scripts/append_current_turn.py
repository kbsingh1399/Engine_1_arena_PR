import sys
from datetime import datetime, timezone

def append_history():
    timestamp = datetime.now(timezone.utc).isoformat()
    entry = f"""
---
### Turn: {timestamp}
**User Prompt:**
I think where you are lacking is in context of what's happened earlier...right? You should read session chat...You may use code-review or graphyy to optimize it so that you can consume less tokens

**Assistant Outcome:**
1. Confirmed git push completion of task-10679: standalone repository `Engine_2` (including 997 MB master parquets, `.agents/`, and prompts) is 100% pushed and tracked on `https://github.com/kbsingh1399/Engine_2.git`.
2. Operationalized Graphify and built `.agents/scripts/query_session_context.py` (and mirrored to `Engine_2/.agents/scripts/query_session_context.py`) enabling sub-500-token semantic context retrieval across the entire 1.54 MB history.
3. Completely absorbed and mapped all historical context: CoinGlass CDP parity, 18-asset historical parquets, 20 OOS walk-forward regimes, the 4 root causes of failure (5R retracement trap, asymmetric risk lockout, falling knives without absorption, simulator label poisoning), the winning confluence formula, and Arena.ai audit remediation mandates (R-1 to R-8).
"""
    with open(r'.agents/memory/session_chat_history.md', 'a', encoding='utf-8') as f:
        f.write(entry)
    print("Appended successfully to session_chat_history.md")

if __name__ == '__main__':
    append_history()
