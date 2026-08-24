"""
================================================================================
MASTER BINANCE HISTORICAL 15M PARITY PIPELINE RUNNER (2020 -> PRESENT)
================================================================================
Production pipeline orchestrator:
  1. Concurrently fetches full historical Klines, Metrics, and Funding Rates.
  2. Computes all 28 canonical microstructure and technical indicators.
  3. Applies upgraded Non-Linear Cascade & Funding-Biased Liquidation Engine.
  4. Exports partitioned & master Parquet datasets to Google Drive target.
  5. Performs end-to-end integrity and continuity validation.
================================================================================
"""

import os
import sys
import time
import argparse
import pandas as pd
from datetime import datetime, timezone

# Configure console encoding for Windows terminals
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# Ensure project root is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from coinglass_parity_engine.pipeline.binance_historical_fetcher import BinanceHistoricalFetcher
from coinglass_parity_engine.pipeline.historical_metrics_processor import HistoricalMetricsProcessor
from coinglass_parity_engine.pipeline.parquet_exporter import ParquetExporter
from coinglass_parity_engine.verification.verify_parquet_integrity import verify_all_parquets
from coinglass_parity_engine.pipeline.tick_footprint_fetcher import TickFootprintFetcher

def run_pipeline(
    start_year: int = 2019,
    end_year: int = 2026,
    start_date_str: str = None,
    target_dir: str = r"G:\My Drive\_Trading_Data\Binance_Pipeline\15_Min",
    cache_dir: str = os.path.join(SCRIPT_DIR, "data_cache"),
    max_workers: int = 16
):
    start_time = time.time()
    
    # If a precise start date is provided, override the start_year
    if start_date_str:
        try:
            parsed_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
            start_year = parsed_dt.year
        except ValueError:
            print(f"Error: Invalid start_date format '{start_date_str}'. Use YYYY-MM-DD.")
            return False
            
    # For daily metrics fallback, use start_date_str if provided
    metrics_start = start_date_str if start_date_str else "2019-09-08"

    print("=" * 100)
    print("BINANCE 15M HISTORICAL DATA PIPELINE (2019 -> PRESENT)")
    print(f"   Date Range : {metrics_start} -> Present ({end_year})")
    print(f"   Target Dir : {target_dir}")
    print(f"   Cache Dir  : {cache_dir}")
    print(f"   Workers    : {max_workers}")
    print("=" * 100)

    # 1. Fetch Historical Data
    fetcher = BinanceHistoricalFetcher(cache_dir=cache_dir, max_workers=max_workers)
    
    t0 = time.time()
    klines_df = fetcher.fetch_all_klines(start_year=2019, end_year=end_year)
    print(f"[OK] Klines fetched in {time.time() - t0:.1f}s ({len(klines_df):,} bars)")

    t1 = time.time()
    # Fetch metrics from the requested start date (Metrics do not need historical warmup, only Klines do)
    metrics_df = fetcher.fetch_all_metrics(start_date=metrics_start)
    print(f"[OK] Metrics fetched in {time.time() - t1:.1f}s ({len(metrics_df):,} records)")

    t2 = time.time()
    ms_start = int(datetime.strptime(metrics_start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    funding_df = fetcher.fetch_all_funding_rates(start_time_ms=ms_start)
    print(f"[OK] Funding rates fetched in {time.time() - t2:.1f}s ({len(funding_df):,} events)")

    # Fetch footprint data ONLY for the requested start_date_str to save time,
    # because footprint tick data is massive and takes a long time to fetch.
    t_fp = time.time()
    fp_fetcher = TickFootprintFetcher(cache_dir=cache_dir, max_workers=max_workers)
    fp_df = fp_fetcher.fetch_footprint(start_date=metrics_start)
    print(f"[OK] Tick Footprint data aggregated in {time.time() - t_fp:.1f}s ({len(fp_df):,} bars)")

    # Fetch spot klines for real basis USD and real spot CVD
    t_sp = time.time()
    spot_df = fetcher.fetch_spot_klines(start_date=metrics_start)
    print(f"[OK] Spot klines fetched in {time.time() - t_sp:.1f}s ({len(spot_df):,} bars)")

    # 2. Process All 28 Indicators on ENTIRE HISTORY for proper EMA warmup
    t3 = time.time()
    processor = HistoricalMetricsProcessor()
    master_df = processor.process_master_dataset(
        klines_df=klines_df,
        metrics_df=metrics_df,
        funding_df=funding_df,
        footprint_df=fp_df,
        spot_df=spot_df
    )
    
    # 2b. Now filter the final master dataset to the requested start date
    if start_date_str:
        start_ms = int(datetime.strptime(start_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
        master_df = master_df[master_df['open_time_ms'] >= start_ms].copy()
        print(f"[PROCESSOR] Sliced dataset to requested start date {start_date_str}: {len(master_df):,} bars")

    print(f"[OK] Indicators computed in {time.time() - t3:.1f}s ({len(master_df):,} bars x {len(master_df.columns)} cols)")

    # 3. Export Parquet Datasets
    t4 = time.time()
    exporter = ParquetExporter(output_dir=target_dir)
    manifest = exporter.export_dataset(master_df)
    
    # Export the separate Footprint summary file requested by run_all_6.py
    if not fp_df.empty:
        fp_out = os.path.join(target_dir, "Master_BTCUSDT_15m_Final_Footprint.parquet")
        fp_export = fp_df.copy()
        fp_export.rename(columns={"open_time_ms": "ts"}, inplace=True)
        fp_export["ts"] = pd.to_datetime(fp_export["ts"], unit="ms", utc=True)
        # run_all_6.py will merge this file directly if found.
        # But we ALSO incorporate it inside process_master_dataset for completeness.
        fp_export.to_parquet(fp_out, index=False)
        print(f"[OK] Exported Footprint supplemental parquet to {fp_out}")
    
    print(f"[OK] Parquet export complete in {time.time() - t4:.1f}s")

    # 4. Audit & Verification
    print("\n" + "=" * 100)
    print("RUNNING AUTOMATED INTEGRITY AUDIT...")
    print("=" * 100)
    audit_passed = verify_all_parquets(target_dir=target_dir)

    total_elapsed = time.time() - start_time
    print("\n" + "=" * 100)
    if audit_passed:
        print(f"SUCCESS: Pipeline completed in {total_elapsed:.1f}s ({total_elapsed/60:.2f} min).")
        print(f"   All {len(master_df):,} candles successfully archived in {target_dir}")
    else:
        print(f"WARNING: Pipeline finished but some audit checks failed. Please review the report.")
    print("=" * 100)
    return audit_passed

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Binance Historical 15m Parquet Pipeline")
    parser.add_argument("--start-year", type=int, default=2020, help="Start year (default: 2020)")
    parser.add_argument("--end-year", type=int, default=2026, help="End year (default: 2026)")
    parser.add_argument("--start-date", type=str, default=None, help="Specific start date YYYY-MM-DD")
    parser.add_argument("--target-dir", type=str, default=r"G:\My Drive\_Trading_Data\Binance_Pipeline\15_Min", help="Output directory")
    parser.add_argument("--workers", type=int, default=16, help="Concurrent worker threads")
    
    args = parser.parse_args()
    success = run_pipeline(
        start_year=args.start_year,
        end_year=args.end_year,
        start_date_str=args.start_date,
        target_dir=args.target_dir,
        max_workers=args.workers
    )
    sys.exit(0 if success else 1)
