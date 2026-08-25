import asyncio
import websockets
import json

async def test_ws():
    url = 'wss://fstream.binance.com/stream?streams=btcusdt@aggTrade'
    print('Connecting...')
    try:
        async with websockets.connect(url, ping_interval=None) as ws:
            print('Connected. Waiting for messages...')
            for i in range(5):
                msg = await ws.recv()
                print(f'Msg {i}: {msg[:300]}')
    except Exception as e:
        print(f'Error: {e}')

asyncio.run(test_ws())
