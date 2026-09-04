"""
query_session_context.py
-------------------------
Token-optimized semantic retrieval engine for session_chat_history.md.
Allows instant, sub-500-token contextual recall of past decisions, audits,
empirical discoveries, and user instructions without reading the entire 1.54 MB file.
"""

import sys
import io
import re
from pathlib import Path

# Ensure UTF-8 output across all Windows consoles
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

SESSION_CHAT_PATH = Path(r"c:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\.agents\memory\session_chat_history.md")
CONTEXT_MAP_PATH = Path(r"c:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\.agents\memory\SESSION_CONTEXT_MAP.md")

def search_session(query: str, max_results: int = 3, max_chars_per_result: int = 1200):
    if not SESSION_CHAT_PATH.exists():
        print(f"Error: {SESSION_CHAT_PATH} does not exist.")
        return

    query_tokens = [q.lower().strip() for q in query.split() if len(q) > 2]
    if not query_tokens:
        print("Please provide a query with keywords.")
        return

    with open(SESSION_CHAT_PATH, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    # Split into sections by header lines
    sections = re.split(r'\n(?=#{2,3}\s+)', content)
    
    scored_sections = []
    for sec in sections:
        sec_lower = sec.lower()
        score = sum(sec_lower.count(tok) for tok in query_tokens)
        if score > 0:
            # Bonus score if tokens appear in the header/first line
            first_line = sec.split('\n')[0].lower()
            header_bonus = sum(5 for tok in query_tokens if tok in first_line)
            scored_sections.append((score + header_bonus, sec))

    scored_sections.sort(key=lambda x: x[0], reverse=True)

    print(f"=== Session Context Query: '{query}' (Found {len(scored_sections)} relevant blocks) ===\n")
    for i, (score, sec) in enumerate(scored_sections[:max_results]):
        header = sec.split('\n')[0].strip()
        body = sec[len(header):].strip()
        if len(body) > max_chars_per_result:
            body = body[:max_chars_per_result] + "\n... [truncated for token economy]"
        print(f"--- [Result {i+1} | Score {score}] {header} ---")
        print(body)
        print("\n" + "="*70 + "\n")

if __name__ == '__main__':
    q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "root cause 5R trailing stop"
    search_session(q)
