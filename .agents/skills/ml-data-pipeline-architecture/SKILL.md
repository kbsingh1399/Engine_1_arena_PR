---
name: ml-data-pipeline-architecture
description: High-throughput ML data pipelines using Polars, Apache Arrow zero-copy memory buffers, ClickHouse, and PyTorch streaming DataLoaders.
---

# ML Data Pipeline Architecture: Polars, Arrow & ClickHouse

This skill provides the architectural framework for building production-grade, high-throughput machine learning data pipelines for large-scale financial and time-series datasets.

## 1. Core Architecture Principles
- **Polars vs. Pandas Decision Matrix:**
  - Always default to **Polars LazyFrames (`pl.scan_parquet`)** when dealing with multi-gigabyte files to enable streaming execution and query plan optimization.
  - Use Pandas only for final legacy compatibility layers or quick single-candle scalars.
- **Zero-Copy Memory Transfers:**
  - Leverage **Apache Arrow (PyArrow)** IPC format and shared memory buffers (`pyarrow.RecordBatch`) to pass high-frequency tick and 15m order flow data directly to PyTorch / C++ / Numba layers without redundant memory copies.
- **ClickHouse High-Concurrency Ingestion:**
  - Use ClickHouse MergeTree engines for real-time tick and orderbook level-2/3 aggregates.
  - Implement bulk buffer flushes (`INSERT INTO ... SETTINGS async_insert=1, wait_for_async_insert=0`).

## 2. Fast Parquet Ingestion Template (Polars Lazy)
```python
import polars as pl

def load_microstructure_data(parquet_path: str) -> pl.DataFrame:
    """Lazy scan and optimized predicate pushdown for 57-column feature sets."""
    q = (
        pl.scan_parquet(parquet_path)
        .select([
            "open_time_ms", "close", "volume_base", 
            "future_cvd_15m", "spot_cvd_15m", 
            "long_liq_usd", "short_liq_usd", 
            "fp_delta", "fp_poc", "whale_index"
        ])
        .filter(pl.col("volume_base") > 0)
        .with_columns([
            (pl.col("close").log().diff()).alias("log_return"),
            (pl.col("future_cvd_15m") - pl.col("future_cvd_15m").rolling_mean(window_size=20)).alias("cvd_divergence")
        ])
    )
    return q.collect(streaming=True)
```

## 3. Zero-Copy PyTorch Streaming DataLoader
```python
import torch
import pyarrow.dataset as ds
from torch.utils.data import IterableDataset, DataLoader

class ArrowStreamDataset(IterableDataset):
    def __init__(self, parquet_files, batch_size=1024):
        self.dataset = ds.dataset(parquet_files, format="parquet")
        self.batch_size = batch_size

    def __iter__(self):
        scanner = self.dataset.scanner(batch_size=self.batch_size)
        for record_batch in scanner.to_batches():
            # Convert Arrow RecordBatch to PyTorch Tensor zero-copy via PyArrow C Buffer
            pydict = record_batch.to_pydict()
            tensor_batch = torch.tensor(
                [pydict[col] for col in pydict if col != "open_time_ms"], 
                dtype=torch.float32
            ).T
            yield tensor_batch
```

## 4. Pre-Window Data Leakage Guard
- Never compute rolling z-scores or standardizations across the boundary of an Out-Of-Sample (OOS) window.
- Persist state parameters (mean, std, min, max, POC levels) strictly from the training window and apply them out-of-sample.
