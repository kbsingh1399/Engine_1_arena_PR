import asyncio
import json
import websockets

async def test_ws():
    url = "wss://fstream.binance.com/ws/btcusdt@aggTrade"
    print(f"Connecting to {url}...")
    async with websockets.connect(url) as ws:
        print("Connected! Waiting for 5 messages...")
        for i in range(5):
            msg = await ws.recv()
            data = json.loads(msg)
            print(f"Msg {i+1}: p={data.get('p')} q={data.get('q')} a={data.get('a')} m={data.get('m')} T={data.get('T')}")

if __name__ == "__main__":
    asyncio.run(test_ws())
