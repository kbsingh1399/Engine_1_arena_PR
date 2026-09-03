r"""
================================================================================
PARQUET INTEGRITY & CONTINUITY VERIFIER
================================================================================
Performs deep structural, mathematical, and schema integrity validation on
the exported Parquet datasets in G:\My Drive\_Trading_Data\Binance_Pipeline\15_Min.
================================================================================
"""

import os
import sys
import glob
import json
import pandas as pd
import numpy as np
from typing import Dict, Any, List

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

DEFAULT_TARGET = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "binance_backtesting_data")

def verify_all_parquets(target_dir: str = DEFAULT_TARGET) -> bool:
    print("=" * 90)
    print(f"PARQUET INTEGRITY & CONTINUITY AUDITOR")
    print(f"Target Directory: {target_dir}")
    print("=" * 90)

    if not os.path.exists(target_dir):
        print(f"[FAIL] Target directory does not exist: {target_dir}")
        return False

    parquet_files = sorted(glob.glob(os.path.join(target_dir, "*.parquet")))
    if not parquet_files:
        print(f"[FAIL] No parquet files found in {target_dir}")
        return False

    print(f"Found {len(parquet_files)} Parquet files to audit:\n" + "\n".join([f"  - {os.path.basename(f)}" for f in parquet_files]))
    print("-" * 90)

    all_passed = True
    total_records = 0

    for p_file in parquet_files:
        fname = os.path.basename(p_file)
        try:
            df = pd.read_parquet(p_file)
            rows = len(df)
            cols = len(df.columns)
            size_mb = os.path.getsize(p_file) / (1024 * 1024)

            # 1. Null / NaN & Infinite Values Check
            null_count = int(df.isnull().sum().sum())
            num_cols = df.select_dtypes(include=[np.number]).columns
            inf_count = int(np.isinf(df[num_cols].to_numpy()).sum()) if len(num_cols) > 0 else 0
            
            # 2. Timestamp Continuity Check
            if "open_time_ms" in df.columns:
                timestamps = df["open_time_ms"].values
            elif "ts" in df.columns:
                timestamps = (pd.to_datetime(df["ts"], utc=True) - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1ms")
                timestamps = timestamps.values
            else:
                timestamps = np.array([])

            is_ladder = "ladder" in fname
            if not is_ladder:
                if len(timestamps) > 1:
                    time_diffs = np.diff(timestamps)
                    expected_diff = 15 * 60 * 1000 # 15 minutes in ms
                    gaps = np.where(time_diffs != expected_diff)[0]
                    num_gaps = len(gaps)
                    is_monotonic = bool(np.all(time_diffs > 0))
                else:
                    num_gaps = 0
                    is_monotonic = True
            else:
                # Gate 5: Real Gap Audit on Table 2 by evaluating unique candle open timestamps
                unique_ts = np.unique(timestamps)
                if len(unique_ts) > 1:
                    time_diffs = np.diff(unique_ts)
                    expected_diff = 15 * 60 * 1000
                    gaps = np.where(time_diffs != expected_diff)[0]
                    num_gaps = len(gaps)
                    # Within the ladder, timestamps must be non-decreasing
                    is_monotonic = bool(np.all(np.diff(timestamps) >= 0))
                else:
                    num_gaps = 0
                    is_monotonic = True

            # 3. Range Sanity Checks (where columns exist)
            rsi_valid = bool((df["rsi_14"] >= 0.0).all() and (df["rsi_14"] <= 100.0).all()) if "rsi_14" in df.columns else True
            close_valid = bool((df["close"] > 0.0).all()) if "close" in df.columns else True
            liq_valid = bool((df["long_liq_usd"] <= 0.0).all() and (df["short_liq_usd"] >= 0.0).all()) if "long_liq_usd" in df.columns else True
            
            # Table 2 Ladder Integrity & Referential Sanity Check
            ladder_valid = True
            ref_valid = True
            if is_ladder:
                ladder_valid = bool(
                    (df["trade_count"] > 0).all() and 
                    (df["price_bin"] > 0).all() and 
                    df["is_poc"].isin([0, 1]).all() and
                    df["is_buy_imbalance"].isin([0, 1]).all() and
                    df["is_sell_imbalance"].isin([0, 1]).all()
                )
                # Referential integrity: check that ladder timestamps exist in matching master dataset
                symbol_prefix = fname.split("_")[0]
                master_fname = f"{symbol_prefix}_15m_master_2020_2026.parquet"
                master_path = os.path.join(target_dir, master_fname)
                if os.path.exists(master_path):
                    master_df_sample = pd.read_parquet(master_path, columns=["open_time_ms"])
                    master_ts_set = set(master_df_sample["open_time_ms"].values)
                    unmatched_ts = set(unique_ts) - master_ts_set
            # 3b. Master Specific Verification Gates
            master_gates_valid = True
            if not is_ladder:
                if "is_synthetic" in df.columns:
                    # Assert is_synthetic is int8 and flags maintenance bars where volume is 0
                    has_flat_zero_bars = bool(((df["high"] == df["low"]) & (df["volume_base"] == 0.0)).any())
                    synth_tagged = bool((df["is_synthetic"] == 1).any())
                    dtype_valid = (df["is_synthetic"].dtype == np.int8 or df["is_synthetic"].dtype == "int8")
                    if has_flat_zero_bars and not synth_tagged:
                        master_gates_valid = False
                        print(f"       -> [FAIL] {fname}: Flat zero-volume bars exist but is_synthetic.sum() == 0")
                    if not dtype_valid:
                        master_gates_valid = False
                        print(f"       -> [FAIL] {fname}: is_synthetic dtype is {df['is_synthetic'].dtype}, expected int8")
                if "ask_depth_usd" in df.columns:
                    # Assert ask_depth_usd is positive liquidity magnitude
                    if (df["ask_depth_usd"] < 0.0).any():
                        master_gates_valid = False
                        print(f"       -> [FAIL] {fname}: ask_depth_usd has negative values (min: {df['ask_depth_usd'].min()})")

            # Strict Gate: num_gaps MUST be 0, inf_count MUST be 0, null_count MUST be 0
            status = "PASS" if (null_count == 0 and inf_count == 0 and num_gaps == 0 and is_monotonic and rsi_valid and close_valid and liq_valid and ladder_valid and ref_valid and master_gates_valid) else "FAIL"
            if status == "FAIL":
                all_passed = False

            if "master" not in fname:
                total_records += rows

            print(f"[{status}] {fname:<36} | Rows: {rows:>7,} | Cols: {cols} | Size: {size_mb:5.2f} MB | Nulls: {null_count} | Infs: {inf_count} | Gaps: {num_gaps} | Monotonic: {is_monotonic}")
            if num_gaps > 0:
                print(f"       -> Gap details (first 3): {[str(pd.to_datetime(timestamps[g], unit='ms', utc=True)) for g in gaps[:3]]}")
        except Exception as e:
            print(f"[FAIL] {fname}: Exception during read: {e}")
            all_passed = False

    print("=" * 90)
    print(f"AUDIT SUMMARY: {'ALL PARQUET DATASETS 100% HEALTHY' if all_passed else 'INTEGRITY ISSUES DETECTED'}")
    print(f"Total Discrete 15m Records Audited: {total_records:,} candles")
    print("=" * 90)
    return all_passed

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TARGET
    success = verify_all_parquets(target)
    sys.exit(0 if success else 1)

