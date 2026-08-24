import urllib.request
import json

urls = [
    "https://fapi.binance.com/fapi/v1/forceOrders?symbol=BTCUSDT",
    "https://fapi.binance.com/fapi/v1/allForceOrders?symbol=BTCUSDT",
    "https://fapi.binance.com/fapi/v1/allForceOrders",
    "https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=15m",
]

for u in urls:
    try:
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode())
            print(f"[200 OK] {u} -> returned {len(data)} items")
    except Exception as e:
        print(f"[FAIL] {u} -> {e}")
