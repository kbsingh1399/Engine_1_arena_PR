import asyncio
import websockets

async def test_ws(domain):
    url = f'wss://{domain}/stream?streams=btcusdt@aggTrade'
    print(f'Connecting to {domain}...')
    try:
        async with websockets.connect(url, ping_interval=None) as ws:
            print(f'Connected to {domain}')
            msg = await ws.recv()
            print(f'Received from {domain}: {msg[:50]}')
    except Exception as e:
        print(f'Error on {domain}: {e}')

async def main():
    domains = ['fstream.binance.com', 'fstream-auth.binance.com', 'dstream.binance.com']
    for d in domains:
        try:
            await asyncio.wait_for(test_ws(d), timeout=3.0)
        except asyncio.TimeoutError:
            print(f'Timeout on {domain}')

asyncio.run(main())
