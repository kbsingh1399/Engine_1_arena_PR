import urllib.request
import json

endpoints = [
    "https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=15m&limit=5",
    "https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol=BTCUSDT&period=15m&limit=5",
    "https://fapi.binance.com/futures/data/topLongShortPositionRatio?symbol=BTCUSDT&period=15m&limit=5",
    "https://fapi.binance.com/futures/data/takerlongshortRatio?symbol=BTCUSDT&period=15m&limit=5",
]

for ep in endpoints:
    try:
        req = urllib.request.Request(ep, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode())
            print(f"[200 OK] {ep.split('/')[-1]} -> {data[0]}")
    except Exception as e:
        print(f"[FAIL] {ep} -> {e}")
