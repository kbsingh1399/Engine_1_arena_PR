import json
from pathlib import Path

def sync_memory():
    src = Path(r"C:\Users\SIGMA\.gemini\antigravity-ide\brain\0cde74c0-35f6-4fbf-98c5-70553681380f\.system_generated\steps\10952\output.txt")
    if not src.exists():
        print("Source snapshot not found.")
        return
    with open(src, 'r', encoding='utf-8') as f:
        data = json.load(f)

    p1 = Path(r".agents/memory/graph/mcp_graph_memory.json")
    p2 = Path(r"Engine_2/.agents/memory/graph/mcp_graph_memory.json")

    p1.parent.mkdir(parents=True, exist_ok=True)
    p2.parent.mkdir(parents=True, exist_ok=True)

    with open(p1, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    with open(p2, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

    print(f"Successfully synced graph memory to both .agents folders!")
    print(f"Entities count: {len(data.get('entities', []))}")
    print(f"Relations count: {len(data.get('relations', []))}")

if __name__ == '__main__':
    sync_memory()
