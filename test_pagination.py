import asyncio
import time
import aiohttp

async def test_pagination():
    start_time_ms = (int(time.time()) // 900) * 900 * 1000
    print(f"Candle start: {start_time_ms}")
    
    url = f"https://fapi.binance.com/fapi/v1/aggTrades?symbol=BTCUSDT&startTime={start_time_ms}&limit=1000"
    
    async with aiohttp.ClientSession() as session:
        page = 1
        total_trades = 0
        from_id = None
        
        while True:
            if from_id:
                url = f"https://fapi.binance.com/fapi/v1/aggTrades?symbol=BTCUSDT&fromId={from_id}&limit=1000"
            
            async with session.get(url) as resp:
                data = await resp.json()
                if not data:
                    break
                
                total_trades += len(data)
                from_id = data[-1]['a'] + 1
                
                print(f"Page {page}: Fetched {len(data)} trades. Total: {total_trades}. Last TS: {data[-1]['T']}")
                
                if len(data) < 1000:
                    break
                
                page += 1
                # Small sleep to be nice to API
                await asyncio.sleep(0.1)
                
asyncio.run(test_pagination())
