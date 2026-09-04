import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def extract_user_prompts():
    with open(r'.agents/memory/session_chat_history.md', 'r', encoding='utf-8', errors='ignore') as f:
        text = f.read()

    # Match lines like **User:** or ### User Prompt or **User Prompt:**
    pattern = re.compile(r'(?:\*\*User(?:\s+Prompt)?:\*\*|###\s+User\s+Prompt:?)\s*(.*?)(?=\n\s*(?:\*\*Assistant|\*\*OMNI|###\s+Assistant|###\s+Turn|##|\Z))', re.DOTALL)
    matches = pattern.findall(text)
    print(f"Total user prompts captured: {len(matches)}")
    
    print("\n--- Chronological Sample of User Intent & Prompts ---")
    for idx, prompt in enumerate(matches):
        clean_p = prompt.strip().replace('\n', ' ')
        if len(clean_p) > 120:
            clean_p = clean_p[:120] + '...'
        if len(clean_p) > 0:
            print(f"[{idx+1}] {clean_p}")

if __name__ == '__main__':
    extract_user_prompts()
