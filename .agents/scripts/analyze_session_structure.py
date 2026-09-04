import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def analyze_session_chat():
    with open(r'.agents/memory/session_chat_history.md', 'r', encoding='utf-8', errors='ignore') as f:
        text = f.read()

    print(f"Total characters: {len(text)}")
    headers = re.findall(r'^(#{1,3}\s+[^\n]+)', text, flags=re.MULTILINE)
    print(f"Total headers: {len(headers)}")
    
    print("\n--- Header Samples Across File ---")
    step = max(1, len(headers) // 20)
    for i in range(0, len(headers), step):
        print(f"[{i}] {headers[i]}")

if __name__ == '__main__':
    analyze_session_chat()
