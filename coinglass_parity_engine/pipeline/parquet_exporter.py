"""
================================================================================
PARQUET EXPORTER & PARTITIONING ENGINE
================================================================================
Exports fully processed canonical 28-indicator historical datasets directly
to the Google Drive destination in high-performance Apache Parquet format.
================================================================================
"""

import os
import json
import pandas as pd
from typing import Dict, Any, List
from datetime import datetime, timezone

class ParquetExporter:
    def __init__(self, output_dir: str = r"G:\My Drive\_Trading_Data\Binance_Pipeline\15_Min"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def export_dataset(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Exports DataFrame partitioned by Year and as a master consolidated Parquet file.
        """
        print(f"[EXPORTER] Exporting {len(df):,} records to {self.output_dir}...")
        
        # Ensure timestamp datetime parsing
        df["_year"] = pd.to_datetime(df["open_time_ms"], unit="ms", utc=True).dt.year
        years: List[int] = sorted(df["_year"].unique().tolist())

        exported_files: List[Dict[str, Any]] = []

        # 1. Export Yearly Partitions
        for y in years:
            sub_df = df[df["_year"] == y].drop(columns=["_year"]).copy()
            out_filename = f"BTCUSDT_15m_{y}.parquet"
            out_path = os.path.join(self.output_dir, out_filename)
            
            sub_df.to_parquet(out_path, index=False, engine="pyarrow", compression="snappy")
            size_mb = os.path.getsize(out_path) / (1024 * 1024)
            print(f"  -> Exported: {out_filename} ({len(sub_df):,} rows, {size_mb:.2f} MB)")
            
            exported_files.append({
                "year": y,
                "file": out_filename,
                "path": out_path,
                "rows": len(sub_df),
                "size_mb": round(size_mb, 2),
                "first_date": sub_df["datetime_utc"].iloc[0],
                "last_date": sub_df["datetime_utc"].iloc[-1],
            })

        # 2. Export Master Consolidated Parquet
        master_clean = df.drop(columns=["_year"]).copy()
        master_filename = f"BTCUSDT_15m_master_2020_{years[-1]}.parquet"
        master_path = os.path.join(self.output_dir, master_filename)
        master_clean.to_parquet(master_path, index=False, engine="pyarrow", compression="snappy")
        master_size_mb = os.path.getsize(master_path) / (1024 * 1024)
        print(f"  -> Exported Master: {master_filename} ({len(master_clean):,} rows, {master_size_mb:.2f} MB)")

        # 3. Export Manifest Metadata JSON
        manifest = {
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "total_rows": len(master_clean),
            "columns": list(master_clean.columns),
            "start_time_utc": master_clean["datetime_utc"].iloc[0],
            "end_time_utc": master_clean["datetime_utc"].iloc[-1],
            "exported_at_utc": datetime.now(timezone.utc).isoformat(),
            "master_file": master_filename,
            "yearly_partitions": exported_files,
        }

        manifest_path = os.path.join(self.output_dir, "dataset_manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        print(f"[EXPORTER] Master Export Complete. Manifest saved to {manifest_path}")
        return manifest
