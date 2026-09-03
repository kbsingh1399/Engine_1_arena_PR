"""
Engine_2/verification/patch_existing_parquets.py
Patch existing 18 Parquet files to:
1. Clean all Infs in oi_change_pct (replace inf with 0.0)
2. Add metrics_available (1 where sum_open_interest > 0, 0 where 0.0)
3. Add is_synthetic (0 default)
4. Re-save in place with clean schema
"""

import os, glob
import pandas as pd
import numpy as np

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "binance_backtesting_data")
files = sorted(glob.glob(os.path.join(DATA_DIR, "*_15m_master_*.parquet")))
print(f"Patching {len(files)} Parquet files in {DATA_DIR}...")

for f in files:
    fname = os.path.basename(f)
    df = pd.read_parquet(f)
    
    # 1. Clean Infs in all numeric columns
    num_cols = df.select_dtypes(include=[np.number]).columns
    infs_before = int(np.isinf(df[num_cols].to_numpy()).sum())
    
    for c in num_cols:
        if np.isinf(df[c].to_numpy()).any():
            df[c] = df[c].replace([np.inf, -np.inf], 0.0)
            
    infs_after = int(np.isinf(df[num_cols].to_numpy()).sum())
    
    # 2. Add metrics_available
    if "metrics_available" not in df.columns:
        if "open_interest_usd" in df.columns:
            # Metrics are real when open_interest_usd > 0
            df["metrics_available"] = np.where(df["open_interest_usd"] > 0, 1, 0).astype(np.int8)
        else:
            df["metrics_available"] = 1
            
    # 3. Add is_synthetic (1 for true exchange downtime maintenance bars where volume was 0)
    if "volume_base" in df.columns:
        df["is_synthetic"] = np.where(df["volume_base"] == 0.0, 1, 0).astype(np.int8)
    else:
        df["is_synthetic"] = np.int8(0)
        
    df.to_parquet(f, index=False, compression="snappy")
    synth_count = int(df["is_synthetic"].sum())
    print(f"[PATCHED] {fname}: Cleaned {infs_before} Infs -> {infs_after} Infs remaining. is_synthetic count: {synth_count}.")

print("All 18 Parquet files successfully patched.")
