import json

def inspect_session_graph():
    with open('graphify-out/graph.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    nodes = data.get('nodes', [])
    edges = data.get('edges', [])
    
    # Find all nodes related to session_chat_history.md
    session_nodes = [n for n in nodes if 'session_chat_history' in n.get('src', '').lower() or 'session_chat_history' in n.get('label', '').lower()]
    print(f"Direct session_chat_history nodes: {len(session_nodes)}")
    
    labels = {n.get('label') for n in session_nodes}
    
    # Find edges connecting to these nodes
    connected_edges = [e for e in edges if e.get('source') in labels or e.get('target') in labels]
    print(f"Connected edges: {len(connected_edges)}")
    for e in connected_edges[:15]:
        print(f"  {e.get('source')} --[{e.get('relation')}]--> {e.get('target')}")

if __name__ == '__main__':
    inspect_session_graph()
