"""
================================================================================
FETCH BINANCE FUTURES REAL FORCE ORDERS (LIQUIDATIONS)
================================================================================
Tests fetching recent liquidation orders from Binance fapi.
================================================================================
"""

import json
import urllib.request
import time

def fetch_force_orders():
    url = "https://fapi.binance.com/fapi/v1/allForceOrders?symbol=BTCUSDT&limit=50"
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            orders = json.loads(r.read().decode())
            print(f"Fetched {len(orders)} liquidation orders from Binance:")
            for o in orders[:5]:
                t_str = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(o['time'] // 1000))
                side = "LONG LIQ (SELL)" if o['side'] == 'SELL' else "SHORT LIQ (BUY)"
                usd_val = float(o['executedQty']) * float(o['avgPrice'])
                print(f"  [{t_str}] {side}: {o['executedQty']} BTC @ ${float(o['avgPrice']):,.2f} = ${usd_val:,.2f}")
    except Exception as e:
        print("Error fetching allForceOrders:", e)

if __name__ == "__main__":
    fetch_force_orders()
