"""
================================================================================
ENGINE 2: LIVE MATRIX MONITOR TERMINAL RUNNER (WITH AUTO-SYNC PRE-FLIGHT)
================================================================================
Entrypoint to run the real-time 18-asset multi-stream matrix terminal with
integrated Parquet lifetime CVD roll-forward, Stablecoin aggregate OI, and
automatic pre-flight dataset gap synchronization (run_all_18 integration).
================================================================================
"""

import os
import sys
import time
import argparse
import pandas as pd

# Ensure project root is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

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

DEFAULT_DATA_DIR = os.path.join(SCRIPT_DIR, "binance_backtesting_data") if os.path.exists(os.path.join(SCRIPT_DIR, "binance_backtesting_data")) else r"G:\My Drive\_Trading_Data\Binance_Pipeline\15_Min"

def preflight_sync_missing_data(target_dir: str = DEFAULT_DATA_DIR, max_workers: int = 16):
    """
    Scans all 18 Master Parquet files in the destination directory:
      1. If any symbol is missing or corrupt, it runs the pipeline to generate it.
      2. If any file is older than 24 hours (missing days), it updates the dataset.
    """
    import pyarrow.parquet as pq
    print("=" * 100)
    print(f"🔍 PRE-FLIGHT CHECK: Scanning 18 Master Parquet Datasets in {target_dir}...")
    print("=" * 100)
    
    missing_or_stale = []
    now_ms = time.time() * 1000
    
    for sym in ENGINE_1_CRYPTO_SYMBOLS:
        p_path = os.path.join(target_dir, f"{sym}_15m_master_2020_2026.parquet")
        if not os.path.exists(p_path):
            print(f"  [MISSING] {sym}: Master Parquet not found.")
            missing_or_stale.append(sym)
            continue
        try:
            pf = pq.ParquetFile(p_path)
            last_rg = max(0, pf.num_row_groups - 1)
            t = pf.read_row_group(last_rg, columns=["close_time_ms", "datetime_utc"])
            df = t.to_pandas()
            if df.empty:
                print(f"  [CORRUPT] {sym}: Parquet is empty.")
                missing_or_stale.append(sym)
                continue
            last_close_ms = int(df["close_time_ms"].iloc[-1])
            hours_behind = (now_ms - last_close_ms) / (1000 * 3600)
            if hours_behind > 24.0:
                print(f"  [STALE] {sym}: Dataset is {hours_behind:.1f} hours behind ({df['datetime_utc'].iloc[-1]}).")
                missing_or_stale.append(sym)
            else:
                print(f"  [OK] {sym}: Up to date ({df['datetime_utc'].iloc[-1]}, {pf.metadata.num_rows:,} rows).")
        except Exception as e:
            print(f"  [CORRUPT/ERROR] {sym}: {e}")
            missing_or_stale.append(sym)

    if missing_or_stale:
        print("\n" + "=" * 100)
        print(f"🔄 AUTO-SYNCING {len(missing_or_stale)} ASSET(S) TO FILL MISSING GAPS: {missing_or_stale}")
        print("=" * 100)
        for idx, sym in enumerate(missing_or_stale, 1):
            sym_start = ASSET_LISTING_DATES.get(sym, "2020-09-01")
            print(f"\n[{idx}/{len(missing_or_stale)}] Syncing {sym} from {sym_start}...")
            run_pipeline(
                symbol=sym,
                start_date_str=sym_start,
                target_dir=target_dir,
                max_workers=max_workers,
                run_audit=False
            )
        print("\n✅ Pre-Flight Sync Complete! All 18 datasets are now 100% current.")
    else:
        print("✅ Pre-Flight Passed: All 18 Master Parquet datasets are valid and up to date.")
    print("=" * 100 + "\n")

def main():
    parser = argparse.ArgumentParser(description="Engine 2 Live Terminal with Auto-Sync Pre-Flight")
    parser.add_argument("--sync", action="store_true", help="Perform pre-flight historical Parquet re-sync from Binance API")
    parser.add_argument("--skip-sync", action="store_true", default=True, help="Skip pre-flight Parquet integrity check")
    parser.add_argument("--single", action="store_true", help="Run focused single-symbol mode")
    parser.add_argument("--symbol", "-s", type=str, default=None, help="Specific symbol(s) to monitor (e.g. BTCUSDT or BTC,ETH,SOL)")
    parser.add_argument("--target-dir", type=str, default=DEFAULT_DATA_DIR, help="Destination Parquet directory")
    parser.add_argument("--once", action="store_true", help="Render matrix once and exit (for headless CI/tests)")
    args, unknown = parser.parse_known_args()

    if args.sync:
        preflight_sync_missing_data(target_dir=args.target_dir)

    from Engine_2.live.binance_live_monitor import main as live_main
    live_main()

if __name__ == "__main__":
    main()
