import urllib.request
import json

try:
    req = urllib.request.Request('http://127.0.0.1:19233/json')
    with urllib.request.urlopen(req, timeout=5) as response:
        pages = json.loads(response.read().decode())
        for p in pages:
            print(f"Title: {p.get('title')}")
            print(f"URL: {p.get('url')}")
            print(f"WebSocket: {p.get('webSocketDebuggerUrl')}")
            print('---')
except Exception as e:
    print('Error:', e)
