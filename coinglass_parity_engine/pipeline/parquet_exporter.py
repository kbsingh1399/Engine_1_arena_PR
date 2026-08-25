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

    def export_dataset(self, df: pd.DataFrame, symbol: str = "BTCUSDT") -> Dict[str, Any]:
        """
        Exports the consolidated unified master Parquet file and metadata manifest for the specified symbol.
        """
        print(f"[EXPORTER] Exporting {len(df):,} records for {symbol} to {self.output_dir}...")
        
        master_clean = df.drop(columns=["_year"], errors="ignore").copy()
        master_filename = f"{symbol}_15m_master_2020_2026.parquet"
        master_path = os.path.join(self.output_dir, master_filename)
        
        # Write high-performance snappy compressed Parquet
        master_clean.to_parquet(master_path, index=False, engine="pyarrow", compression="snappy")
        master_size_mb = os.path.getsize(master_path) / (1024 * 1024)
        print(f"  -> Exported Master Dataset: {master_filename} ({len(master_clean):,} rows x {len(master_clean.columns)} cols, {master_size_mb:.2f} MB)")

        # Export Manifest Metadata JSON
        manifest = {
            "symbol": symbol,
            "timeframe": "15m",
            "total_rows": len(master_clean),
            "columns": list(master_clean.columns),
            "column_count": len(master_clean.columns),
            "start_time_utc": master_clean["datetime_utc"].iloc[0],
            "end_time_utc": master_clean["datetime_utc"].iloc[-1],
            "exported_at_utc": datetime.now(timezone.utc).isoformat(),
            "master_file": master_filename,
            "master_size_mb": round(master_size_mb, 2)
        }

        manifest_path = os.path.join(self.output_dir, f"{symbol}_dataset_manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        print(f"[EXPORTER] Master Export Complete for {symbol}. Manifest saved to {manifest_path}")
        return manifest
