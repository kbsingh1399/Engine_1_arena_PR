import asyncio
import websockets

async def test_ws():
    url = 'wss://fstream.binance.com/stream?streams=btcusdt@aggTrade/btcusdt@bookTicker/btcusdt@kline_15m/btcusdt@markPrice@1s/btcusdt@forceOrder'
    print('Connecting...')
    try:
        async with websockets.connect(url) as ws:
            print('Connected. Waiting for messages...')
            for i in range(5):
                msg = await ws.recv()
                print(f'Msg {i}: {msg[:200]}')
    except Exception as e:
        print(f'Error: {e}')

asyncio.run(test_ws())
