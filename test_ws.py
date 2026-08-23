import asyncio
import websockets
import json
import time
from collections import Counter

async def test_binance_ws():
    url = "wss://fstream.binance.com/stream?streams=btcusdt@kline_15m/btcusdt@forceOrder/btcusdt@markPrice@1s/btcusdt@depth20@100ms/btcusdt@ticker"
    print(f"Connecting to {url}", flush=True)
    try:
        async with websockets.connect(url, ping_interval=20, ping_timeout=10, open_timeout=5) as ws:
            print("Connected!", flush=True)
            c = Counter()
            t0 = time.time()
            for i in range(200):
                msg = await ws.recv()
                data = json.loads(msg)
                stream = data.get("stream", "UNKNOWN")
                c[stream] += 1
            print(f"Time taken: {time.time()-t0:.2f}s", flush=True)
            print("Stream counts:", c, flush=True)
    except Exception as e:
        print(f"Error: {e}", flush=True)

asyncio.run(test_binance_ws())
