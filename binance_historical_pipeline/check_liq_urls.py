"""
================================================================================
CHECK BINANCE VISION HISTORICAL LIQUIDATION ARCHIVES
================================================================================
Tests different URL structures on data.binance.vision for historical liquidation
orders / snapshots to find where Binance stores them.
================================================================================
"""

import urllib.request

def check_url(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            print(f"[FOUND 200 OK] {url} (Content-Length: {r.headers.get('Content-Length')})")
            return True
    except urllib.error.HTTPError as e:
        print(f"[{e.code}] {url}")
        return False
    except Exception as e:
        print(f"[ERR] {url} - {e}")
        return False

def main():
    date_test = "2026-08-20" # Recent date
    symbols = ["BTCUSDT"]
    
    test_urls = [
        # Daily UM liquidationSnapshot
        f"https://data.binance.vision/data/futures/um/daily/liquidationSnapshot/BTCUSDT/BTCUSDT-liquidationSnapshot-{date_test}.zip",
        # Daily UM liquidationOrders
        f"https://data.binance.vision/data/futures/um/daily/liquidationOrders/BTCUSDT/BTCUSDT-liquidationOrders-{date_test}.zip",
        # Daily CM liquidationSnapshot
        f"https://data.binance.vision/data/futures/cm/daily/liquidationSnapshot/BTCUSD_PERP/BTCUSD_PERP-liquidationSnapshot-{date_test}.zip",
        # Monthly UM liquidationSnapshot
        f"https://data.binance.vision/data/futures/um/monthly/liquidationSnapshot/BTCUSDT/BTCUSDT-liquidationSnapshot-2026-07.zip",
        # Monthly UM liquidationOrders
        f"https://data.binance.vision/data/futures/um/monthly/liquidationOrders/BTCUSDT/BTCUSDT-liquidationOrders-2026-07.zip",
    ]
    
    print("Testing Binance Vision historical liquidation URLs:")
    for u in test_urls:
        check_url(u)

if __name__ == "__main__":
    main()
