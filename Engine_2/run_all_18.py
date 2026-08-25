"""
================================================================================
ENGINE 2: MASTER 18-ASSET HISTORICAL PARITY PIPELINE RUNNER (2020 -> PRESENT)
================================================================================
Sequentially or concurrently runs the full historical pipeline for all 18
Engine_1/Engine_2 cryptocurrency symbols:
   BTC, ETH, XRP, SOL, BNB, DOGE, ADA, TRX, LINK, AVAX,
   SUI, NEAR, DOT, LTC, BCH, APT, OP, ARB
================================================================================
"""

import os
import sys
import time
import argparse

# Ensure project root is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

from Engine_2.run_historical_pipeline import run_pipeline, ENGINE_1_CRYPTO_SYMBOLS

ASSET_LISTING_DATES = {
    "BTCUSDT": "2020-09-01",
    "ETHUSDT": "2020-09-01",
    "XRPUSDT": "2020-09-01",
    "SOLUSDT": "2020-09-14",
    "BNBUSDT": "2020-09-01",
    "DOGEUSDT": "2020-09-01",
    "ADAUSDT": "2020-09-01",
    "TRXUSDT": "2020-09-01",
    "LINKUSDT": "2020-09-01",
    "AVAXUSDT": "2020-09-23",
    "SUIUSDT": "2023-05-03",
    "NEARUSDT": "2020-10-15",
    "DOTUSDT": "2020-09-01",
    "LTCUSDT": "2020-09-01",
    "BCHUSDT": "2020-09-01",
    "APTUSDT": "2022-10-18",
    "OPUSDT": "2022-06-01",
    "ARBUSDT": "2023-03-23",
}

def main():
    parser = argparse.ArgumentParser(description="Engine 2: 18-Asset Historical Pipeline Runner")
    parser.add_argument("--start-date", type=str, default=None, help="Optional global start date override (YYYY-MM-DD)")
    parser.add_argument("--target-dir", type=str, default=r"G:\My Drive\_Trading_Data\Binance_Pipeline\15_Min", help="Destination Parquet directory")
    parser.add_argument("--workers", type=int, default=16, help="Parallel download workers per symbol")
    parser.add_argument("--symbols", nargs="+", default=ENGINE_1_CRYPTO_SYMBOLS, help="List of symbols to run")
    args = parser.parse_args()

    print("=" * 100)
    print(f"🚀 ENGINE 2: MASTER 18-ASSET HISTORICAL PARITY PIPELINE")
    print(f"   Target Directory : {args.target_dir}")
    print(f"   Total Symbols    : {len(args.symbols)} assets")
    print("=" * 100)

    t_start = time.time()
    results = {}

    for idx, symbol in enumerate(args.symbols, 1):
        sym_start = args.start_date if args.start_date else ASSET_LISTING_DATES.get(symbol, "2020-09-01")
        print(f"\n[{idx}/{len(args.symbols)}] Processing {symbol} (from {sym_start})...")
        t_sym = time.time()
        try:
            success = run_pipeline(
                symbol=symbol,
                start_date_str=sym_start,
                target_dir=args.target_dir,
                max_workers=args.workers,
                run_audit=False
            )
            elapsed = time.time() - t_sym
            results[symbol] = "SUCCESS" if success else "FAILED"
            print(f"[{'OK' if success else 'FAIL'}] {symbol} finished in {elapsed:.1f}s ({elapsed/60:.2f} min)")
        except Exception as e:
            print(f"[ERROR] {symbol} failed with exception: {e}")
            results[symbol] = f"ERROR: {e}"

    total_time = time.time() - t_start
    print("\n" + "=" * 100)
    print(f"🏁 ENGINE 2 PIPELINE COMPLETE IN {total_time:.1f}s ({total_time/60:.2f} min)")
    print("=" * 100)
    for sym, res in results.items():
        print(f"  - {sym:<10}: {res}")
    print("=" * 100)

if __name__ == "__main__":
    main()
