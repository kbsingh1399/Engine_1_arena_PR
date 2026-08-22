import urllib.request, json
try:
    resp = urllib.request.urlopen('http://127.0.0.1:19333/json/list')
    pages = json.loads(resp.read())
    for p in pages:
        print(f"[{p.get('type')}] {p.get('title')} - {p.get('url')}")
except Exception as e:
    print('Error:', e)
