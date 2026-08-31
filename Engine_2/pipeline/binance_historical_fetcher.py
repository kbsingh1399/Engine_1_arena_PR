"""
================================================================================
BINANCE HISTORICAL VISION & REST ARCHIVE FETCHER
================================================================================
High-throughput concurrent fetcher for:
  1. Monthly & Daily 15m Futures Klines (data.binance.vision + fapi REST)
  2. Daily Futures Metrics Archives (Open Interest, L/S Ratios, Whale Ratios)
  3. Continuous Historical Funding Rates (/fapi/v1/fundingRate)
================================================================================
"""

import os
import sys
import io
import time
import json
import zipfile
import urllib.request
import urllib.error
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timezone

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
}

class BinanceHistoricalFetcher:
    def __init__(self, cache_dir: str = "./data_cache", max_workers: int = 16):
        self.cache_dir = os.path.abspath(cache_dir)
        self.klines_dir = os.path.join(self.cache_dir, "klines_15m")
        self.metrics_dir = os.path.join(self.cache_dir, "metrics_daily")
        self.funding_dir = os.path.join(self.cache_dir, "funding_rates")
        self.max_workers = max_workers
        
        for d in [self.klines_dir, self.metrics_dir, self.funding_dir]:
            os.makedirs(d, exist_ok=True)

    def _fetch_url(self, url: str, timeout: int = 15) -> Optional[bytes]:
        req = urllib.request.Request(url, headers=HEADERS)
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return resp.read()
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                time.sleep(0.3 * (attempt + 1))
            except Exception:
                time.sleep(0.3 * (attempt + 1))
        return None

    # --------------------------------------------------------------------------
    # 1. Klines Ingestion (2020-01 -> Present)
    # --------------------------------------------------------------------------
    def fetch_all_klines(self, symbol: str = "BTCUSDT", start_year: int = 2019, end_year: int = 2026) -> pd.DataFrame:
        """
        Fetches all 15m Klines from Sept 2019 to present for the specified symbol.
        Combines Binance Vision Monthly + Daily + Live REST.
        """
        print(f"[FETCHER] Fetching Historical 15m Klines for {symbol} ({start_year} -> {end_year})...")
        now = datetime.now(timezone.utc)
        current_year = now.year
        current_month = now.month

        # Generate list of monthly targets
        monthly_targets = []
        for y in range(start_year, end_year + 1):
            max_m = current_month - 1 if y == current_year else 12
            for m in range(1, max_m + 1):
                monthly_targets.append(f"{y}-{m:02d}")

        kline_dfs: List[pd.DataFrame] = []
        
        def _get_monthly_kline(ym: str) -> Optional[pd.DataFrame]:
            cache_file = os.path.join(self.klines_dir, f"{symbol}-15m-{ym}.csv")
            if os.path.exists(cache_file) and os.path.getsize(cache_file) > 100:
                try:
                    return pd.read_csv(cache_file)
                except Exception:
                    pass
            
            url = f"https://data.binance.vision/data/futures/um/monthly/klines/{symbol}/15m/{symbol}-15m-{ym}.zip"
            data = self._fetch_url(url)
            if data:
                try:
                    zf = zipfile.ZipFile(io.BytesIO(data))
                    raw_text = zf.read(zf.namelist()[0]).decode('utf-8')
                    first_line = raw_text.splitlines()[0] if raw_text else ""
                    has_header = first_line.startswith("open_time")
                    df = pd.read_csv(io.StringIO(raw_text), header=0 if has_header else None)
                    if not has_header:
                        df.columns = [
                            "open_time", "open", "high", "low", "close", "volume",
                            "close_time", "quote_volume", "count", "taker_buy_volume",
                            "taker_buy_quote_volume", "ignore"
                        ][:len(df.columns)]
                    df = df[pd.to_numeric(df["open_time"], errors="coerce").notnull()].copy()
                    for c in ["open_time", "close_time", "count"]:
                        if c in df.columns:
                            df[c] = df[c].astype(int)
                    for c in ["open", "high", "low", "close", "volume", "quote_volume", "taker_buy_volume", "taker_buy_quote_volume"]:
                        if c in df.columns:
                            df[c] = df[c].astype(float)
                    df.to_csv(cache_file, index=False)
                    return df
                except Exception as e:
                    print(f"[WARN] Failed parsing klines for {symbol} {ym}: {e}")
            return None

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_ym = {executor.submit(_get_monthly_kline, ym): ym for ym in monthly_targets}
            for future in as_completed(future_to_ym):
                res = future.result()
                if res is not None and not res.empty:
                    kline_dfs.append(res)

        # Download daily klines for current month
        current_daily_targets = []
        for d in range(1, now.day):
            current_daily_targets.append(f"{current_year}-{current_month:02d}-{d:02d}")

        def _get_daily_kline(ymd: str) -> Optional[pd.DataFrame]:
            cache_file = os.path.join(self.klines_dir, f"{symbol}-15m-{ymd}.csv")
            if os.path.exists(cache_file) and os.path.getsize(cache_file) > 100:
                try:
                    return pd.read_csv(cache_file)
                except Exception:
                    pass
            url = f"https://data.binance.vision/data/futures/um/daily/klines/{symbol}/15m/{symbol}-15m-{ymd}.zip"
            data = self._fetch_url(url)
            if data:
                try:
                    zf = zipfile.ZipFile(io.BytesIO(data))
                    raw_text = zf.read(zf.namelist()[0]).decode('utf-8')
                    first_line = raw_text.splitlines()[0] if raw_text else ""
                    has_header = first_line.startswith("open_time")
                    df = pd.read_csv(io.StringIO(raw_text), header=0 if has_header else None)
                    if not has_header:
                        df.columns = [
                            "open_time", "open", "high", "low", "close", "volume",
                            "close_time", "quote_volume", "count", "taker_buy_volume",
                            "taker_buy_quote_volume", "ignore"
                        ][:len(df.columns)]
                    df = df[pd.to_numeric(df["open_time"], errors="coerce").notnull()].copy()
                    for c in ["open_time", "close_time", "count"]:
                        if c in df.columns:
                            df[c] = df[c].astype(int)
                    for c in ["open", "high", "low", "close", "volume", "quote_volume", "taker_buy_volume", "taker_buy_quote_volume"]:
                        if c in df.columns:
                            df[c] = df[c].astype(float)
                    df.to_csv(cache_file, index=False)
                    return df
                except Exception:
                    pass
            return None

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_ymd = {executor.submit(_get_daily_kline, ymd): ymd for ymd in current_daily_targets}
            for future in as_completed(future_to_ymd):
                res = future.result()
                if res is not None and not res.empty:
                    kline_dfs.append(res)

        # Fetch recent bars from REST API to fill up to the latest closed candle
        try:
            rest_url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=15m&limit=1500"
            raw = self._fetch_url(rest_url)
            if raw:
                rows = json.loads(raw.decode('utf-8'))
                rest_df = pd.DataFrame(rows, columns=[
                    "open_time", "open", "high", "low", "close", "volume",
                    "close_time", "quote_volume", "count", "taker_buy_volume",
                    "taker_buy_quote_volume", "ignore"
                ])
                for c in ["open_time", "close_time", "count"]:
                    rest_df[c] = rest_df[c].astype(int)
                for c in ["open", "high", "low", "close", "volume", "quote_volume", "taker_buy_volume", "taker_buy_quote_volume"]:
                    rest_df[c] = rest_df[c].astype(float)
                
                # Filter out currently forming unclosed candle to prevent partial bar contamination
                now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                rest_df = rest_df[rest_df["close_time"] < now_ms]
                if not rest_df.empty:
                    kline_dfs.append(rest_df)
        except Exception as e:
            print(f"[WARN] REST klines fetch failed for {symbol}: {e}")

        if not kline_dfs:
            raise RuntimeError(f"No historical klines were fetched for {symbol}.")

        master_df = pd.concat(kline_dfs, ignore_index=True)
        master_df.drop_duplicates(subset=["open_time"], inplace=True)
        master_df.sort_values(by="open_time", inplace=True)
        master_df.reset_index(drop=True, inplace=True)
        print(f"[FETCHER] Total Historical Klines loaded for {symbol}: {len(master_df):,} bars (From {datetime.fromtimestamp(master_df['open_time'].iloc[0]/1000, tz=timezone.utc)} to {datetime.fromtimestamp(master_df['open_time'].iloc[-1]/1000, tz=timezone.utc)})")
        return master_df

    # --------------------------------------------------------------------------
    # 1b. Spot Klines (for real Basis USD and real Spot CVD)
    # --------------------------------------------------------------------------
    def fetch_spot_klines(self, symbol: str = "BTCUSDT", start_date: str = "2020-01-01") -> pd.DataFrame:
        """
        Fetches spot 15m klines from Binance Vision.
        Returns df with: open_time, spot_close, spot_taker_buy_volume, spot_volume
        """
        print(f"[FETCHER] Fetching Spot 15m Klines for {symbol} from {start_date}...")
        spot_dir = os.path.join(self.cache_dir, "spot_klines_15m")
        os.makedirs(spot_dir, exist_ok=True)

        now = datetime.now(timezone.utc)
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)

        SPOT_COLS = [
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "count", "taker_buy_volume",
            "taker_buy_quote_volume", "ignore"
        ]

        def _parse_spot_zip(data: bytes) -> Optional[pd.DataFrame]:
            try:
                zf = zipfile.ZipFile(io.BytesIO(data))
                raw_text = zf.read(zf.namelist()[0]).decode('utf-8')
                first_line = raw_text.splitlines()[0] if raw_text else ""
                has_header = first_line.startswith("open_time")
                df = pd.read_csv(io.StringIO(raw_text), header=0 if has_header else None)
                if not has_header:
                    df.columns = SPOT_COLS[:len(df.columns)]
                df = df[pd.to_numeric(df["open_time"], errors="coerce").notnull()].copy()
                df["open_time"] = df["open_time"].astype(int)
                df["close"] = df["close"].astype(float)
                df["volume"] = df["volume"].astype(float)
                df["taker_buy_volume"] = df["taker_buy_volume"].astype(float)
                return df[["open_time", "close", "volume", "taker_buy_volume"]]
            except Exception:
                return None

        # Monthly archives
        monthly_targets = []
        for y in range(start_dt.year, now.year + 1):
            max_m = now.month - 1 if y == now.year else 12
            start_m = start_dt.month if y == start_dt.year else 1
            for m in range(start_m, max_m + 1):
                monthly_targets.append(f"{y}-{m:02d}")

        spot_dfs: List[pd.DataFrame] = []

        def _get_monthly_spot(ym: str) -> Optional[pd.DataFrame]:
            cache_file = os.path.join(spot_dir, f"{symbol}-spot-15m-{ym}.csv")
            if os.path.exists(cache_file) and os.path.getsize(cache_file) > 100:
                try:
                    return pd.read_csv(cache_file)
                except Exception:
                    pass
            url = f"https://data.binance.vision/data/spot/monthly/klines/{symbol}/15m/{symbol}-15m-{ym}.zip"
            data = self._fetch_url(url)
            if data:
                df = _parse_spot_zip(data)
                if df is not None:
                    df.to_csv(cache_file, index=False)
                    return df
            return None

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(_get_monthly_spot, ym): ym for ym in monthly_targets}
            for f in as_completed(futures):
                res = f.result()
                if res is not None and not res.empty:
                    spot_dfs.append(res)

        # Daily archives for current month
        for d in range(1, now.day):
            ymd = f"{now.year}-{now.month:02d}-{d:02d}"
            cache_file = os.path.join(spot_dir, f"{symbol}-spot-15m-{ymd}.csv")
            if os.path.exists(cache_file) and os.path.getsize(cache_file) > 100:
                try:
                    spot_dfs.append(pd.read_csv(cache_file))
                    continue
                except Exception:
                    pass
            url = f"https://data.binance.vision/data/spot/daily/klines/{symbol}/15m/{symbol}-15m-{ymd}.zip"
            data = self._fetch_url(url)
            if data:
                df = _parse_spot_zip(data)
                if df is not None:
                    df.to_csv(cache_file, index=False)
                    spot_dfs.append(df)

        # REST fallback for recent bars
        try:
            rest_url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=15m&limit=1500"
            raw = self._fetch_url(rest_url)
            if raw:
                rows = json.loads(raw.decode('utf-8'))
                rest_df = pd.DataFrame(rows, columns=SPOT_COLS)
                rest_df["open_time"] = rest_df["open_time"].astype(int)
                rest_df["close_time"] = rest_df["close_time"].astype(int)
                rest_df["close"] = rest_df["close"].astype(float)
                rest_df["volume"] = rest_df["volume"].astype(float)
                rest_df["taker_buy_volume"] = rest_df["taker_buy_volume"].astype(float)
                
                # Filter out currently forming candle
                now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                rest_df = rest_df[rest_df["close_time"] < now_ms]
                if not rest_df.empty:
                    spot_dfs.append(rest_df[["open_time", "close", "volume", "taker_buy_volume"]])
        except Exception:
            pass

        if not spot_dfs:
            print(f"[WARN] No spot klines fetched for {symbol}.")
            return pd.DataFrame()

        master = pd.concat(spot_dfs, ignore_index=True)
        master.drop_duplicates(subset=["open_time"], inplace=True)
        master.sort_values("open_time", inplace=True)
        master.reset_index(drop=True, inplace=True)
        master.rename(columns={
            "close": "spot_close",
            "volume": "spot_volume",
            "taker_buy_volume": "spot_taker_buy_volume"
        }, inplace=True)
        print(f"[FETCHER] Total Spot Klines loaded for {symbol}: {len(master):,} bars")
        return master

    # --------------------------------------------------------------------------
    # 2. Daily Metrics Ingestion (Sept 2020 -> Present)
    # --------------------------------------------------------------------------
    def fetch_all_metrics(self, symbol: str = "BTCUSDT", start_date: str = "2020-09-01") -> pd.DataFrame:
        """
        Fetches all daily metrics archives (Open Interest, L/S Ratios, Whale Index)
        for the specified symbol (and USDC companion if applicable).
        """
        print(f"[FETCHER] Fetching Historical Daily Metrics for {symbol} from {start_date}...")
        now = datetime.now(timezone.utc)
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        
        day_diff = (now - start_dt).days
        all_dates = [(start_dt + pd.Timedelta(days=i)).strftime("%Y-%m-%d") for i in range(day_diff + 1)]

        def _get_daily_metric(sym: str, ymd: str) -> Optional[pd.DataFrame]:
            cache_file = os.path.join(self.metrics_dir, f"{sym}-metrics-{ymd}.csv")
            if os.path.exists(cache_file) and os.path.getsize(cache_file) > 100:
                try:
                    return pd.read_csv(cache_file)
                except Exception:
                    pass
            url = f"https://data.binance.vision/data/futures/um/daily/metrics/{sym}/{sym}-metrics-{ymd}.zip"
            data = self._fetch_url(url)
            if data:
                try:
                    zf = zipfile.ZipFile(io.BytesIO(data))
                    raw_text = zf.read(zf.namelist()[0]).decode('utf-8')
                    df = pd.read_csv(io.StringIO(raw_text))
                    df.to_csv(cache_file, index=False)
                    return df
                except Exception:
                    pass
            return None

        # Fetch Primary Symbol Metrics
        metric_dfs_primary: List[pd.DataFrame] = []
        total_targets = len(all_dates)
        completed_count = 0
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_date = {executor.submit(_get_daily_metric, symbol, d): d for d in all_dates}
            for future in as_completed(future_to_date):
                completed_count += 1
                if completed_count % 250 == 0 or completed_count == total_targets:
                    print(f"  [FETCHER] {symbol} daily metrics progress: {completed_count}/{total_targets} ({completed_count*100//total_targets}%)")
                res = future.result()
                if res is not None and not res.empty:
                    metric_dfs_primary.append(res)
                    
        # Optional companion USDC metrics
        usdc_symbol = symbol.replace("USDT", "USDC") if symbol.endswith("USDT") else None
        metric_dfs_usdc: List[pd.DataFrame] = []
        if usdc_symbol and usdc_symbol != symbol:
            completed_usdc = 0
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_date = {executor.submit(_get_daily_metric, usdc_symbol, d): d for d in all_dates}
                for future in as_completed(future_to_date):
                    completed_usdc += 1
                    res = future.result()
                    if res is not None and not res.empty:
                        metric_dfs_usdc.append(res)

        if not metric_dfs_primary:
            print(f"[WARN] No historical metrics archives found for {symbol}. Will use smooth interpolation / REST fallback.")
            master_metrics = pd.DataFrame()
        else:
            master_metrics_usdt = pd.concat(metric_dfs_primary, ignore_index=True)
            master_metrics_usdt["create_time"] = pd.to_datetime(master_metrics_usdt["create_time"], utc=True)
            master_metrics_usdt["timestamp_ms"] = (master_metrics_usdt["create_time"] - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1ms")
            master_metrics_usdt.drop_duplicates(subset=["timestamp_ms"], inplace=True)
            master_metrics_usdt.sort_values(by="timestamp_ms", inplace=True)
            master_metrics_usdt.reset_index(drop=True, inplace=True)
            
            master_metrics = master_metrics_usdt.copy()
            
            if metric_dfs_usdc:
                master_metrics_usdc = pd.concat(metric_dfs_usdc, ignore_index=True)
                master_metrics_usdc["create_time"] = pd.to_datetime(master_metrics_usdc["create_time"], utc=True)
                master_metrics_usdc["timestamp_ms"] = (master_metrics_usdc["create_time"] - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1ms")
                master_metrics_usdc.drop_duplicates(subset=["timestamp_ms"], inplace=True)
                master_metrics_usdc.sort_values(by="timestamp_ms", inplace=True)
                
                # Rename USDC columns and merge
                usdc_sub = master_metrics_usdc[["timestamp_ms", "sum_open_interest", "sum_open_interest_value"]].copy()
                usdc_sub.rename(columns={
                    "sum_open_interest": "sum_open_interest_usdc",
                    "sum_open_interest_value": "sum_open_interest_value_usdc"
                }, inplace=True)
                
                master_metrics = pd.merge(master_metrics, usdc_sub, on="timestamp_ms", how="left")
                
                # Combine STABLECOIN-margined OI
                master_metrics["sum_open_interest"] = master_metrics["sum_open_interest"].fillna(0) + master_metrics["sum_open_interest_usdc"].fillna(0)
                master_metrics["sum_open_interest_value"] = master_metrics["sum_open_interest_value"].fillna(0) + master_metrics["sum_open_interest_value_usdc"].fillna(0)
                master_metrics.drop(columns=["sum_open_interest_usdc", "sum_open_interest_value_usdc"], inplace=True)

        # ----------------------------------------------------------------------
        # BRIDGE LIVE REST METRICS FOR TODAY'S MISSING HOURS
        # ----------------------------------------------------------------------
        try:
            print(f"[FETCHER] Bridging recent hours for {symbol} via live Binance Futures REST API...")
            rest_oi_raw = self._fetch_url(f"https://fapi.binance.com/futures/data/openInterestHist?symbol={symbol}&period=15m&limit=500")
            rest_oi_usdc_raw = self._fetch_url(f"https://fapi.binance.com/futures/data/openInterestHist?symbol={usdc_symbol}&period=15m&limit=500") if usdc_symbol else None
            rest_ls_raw = self._fetch_url(f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={symbol}&period=15m&limit=500")
            rest_top_raw = self._fetch_url(f"https://fapi.binance.com/futures/data/topLongShortPositionRatio?symbol={symbol}&period=15m&limit=500")
            rest_top_acc_raw = self._fetch_url(f"https://fapi.binance.com/futures/data/topLongShortAccountRatio?symbol={symbol}&period=15m&limit=500")
            rest_tk_raw = self._fetch_url(f"https://fapi.binance.com/futures/data/takerlongshortRatio?symbol={symbol}&period=15m&limit=500")

            if rest_oi_raw and rest_ls_raw:
                df_roi = pd.DataFrame(json.loads(rest_oi_raw.decode('utf-8')))
                if rest_oi_usdc_raw:
                    try:
                        df_roi_usdc = pd.DataFrame(json.loads(rest_oi_usdc_raw.decode('utf-8')))
                        if not df_roi_usdc.empty:
                            df_roi_usdc.rename(columns={
                                "sumOpenInterest": "sumOpenInterest_usdc",
                                "sumOpenInterestValue": "sumOpenInterestValue_usdc"
                            }, inplace=True)
                            df_roi = pd.merge(df_roi, df_roi_usdc[["timestamp", "sumOpenInterest_usdc", "sumOpenInterestValue_usdc"]], on="timestamp", how="left")
                            df_roi["sumOpenInterest"] = df_roi["sumOpenInterest"].astype(float) + df_roi["sumOpenInterest_usdc"].fillna(0).astype(float)
                            df_roi["sumOpenInterestValue"] = df_roi["sumOpenInterestValue"].astype(float) + df_roi["sumOpenInterestValue_usdc"].fillna(0).astype(float)
                    except Exception:
                        pass
                df_rls = pd.DataFrame(json.loads(rest_ls_raw.decode('utf-8')))
                df_rtop = pd.DataFrame(json.loads(rest_top_raw.decode('utf-8'))) if rest_top_raw else pd.DataFrame()
                df_rtop_acc = pd.DataFrame(json.loads(rest_top_acc_raw.decode('utf-8'))) if rest_top_acc_raw else pd.DataFrame()
                df_rtk = pd.DataFrame(json.loads(rest_tk_raw.decode('utf-8'))) if rest_tk_raw else pd.DataFrame()

                # Normalize columns
                df_roi.rename(columns={
                    "timestamp": "timestamp_ms",
                    "sumOpenInterest": "sum_open_interest",
                    "sumOpenInterestValue": "sum_open_interest_value"
                }, inplace=True)
                df_rls.rename(columns={"timestamp": "timestamp_ms", "longShortRatio": "count_long_short_ratio"}, inplace=True)
                
                rest_merged = df_roi[["timestamp_ms", "sum_open_interest", "sum_open_interest_value", "symbol"]].copy()
                rest_merged = pd.merge(rest_merged, df_rls[["timestamp_ms", "count_long_short_ratio"]], on="timestamp_ms", how="left")
                
                if not df_rtop.empty:
                    df_rtop.rename(columns={"timestamp": "timestamp_ms", "longShortRatio": "sum_toptrader_long_short_ratio"}, inplace=True)
                    rest_merged = pd.merge(rest_merged, df_rtop[["timestamp_ms", "sum_toptrader_long_short_ratio"]], on="timestamp_ms", how="left")
                
                if not df_rtop_acc.empty:
                    df_rtop_acc.rename(columns={"timestamp": "timestamp_ms", "longShortRatio": "count_toptrader_long_short_ratio"}, inplace=True)
                    rest_merged = pd.merge(rest_merged, df_rtop_acc[["timestamp_ms", "count_toptrader_long_short_ratio"]], on="timestamp_ms", how="left")

                if not df_rtk.empty:
                    df_rtk.rename(columns={"timestamp": "timestamp_ms", "buySellRatio": "sum_taker_long_short_vol_ratio"}, inplace=True)
                    rest_merged = pd.merge(rest_merged, df_rtk[["timestamp_ms", "sum_taker_long_short_vol_ratio"]], on="timestamp_ms", how="left")

                rest_merged["create_time"] = pd.to_datetime(rest_merged["timestamp_ms"], unit="ms", utc=True)
                for col in ["sum_open_interest", "sum_open_interest_value", "count_long_short_ratio", "sum_toptrader_long_short_ratio", "count_toptrader_long_short_ratio", "sum_taker_long_short_vol_ratio"]:
                    if col in rest_merged.columns:
                        rest_merged[col] = rest_merged[col].astype(float)

                # Filter REST rows that are newer than the vision archives
                max_archived_ts = master_metrics["timestamp_ms"].max() if not master_metrics.empty else 0
                new_rest_rows = rest_merged[rest_merged["timestamp_ms"] > max_archived_ts].copy()
                if not new_rest_rows.empty:
                    master_metrics = pd.concat([master_metrics, new_rest_rows], ignore_index=True)
                    master_metrics.drop_duplicates(subset=["timestamp_ms"], inplace=True)
                    master_metrics.sort_values(by="timestamp_ms", inplace=True)
                    master_metrics.reset_index(drop=True, inplace=True)
                    print(f"  [FETCHER] Successfully stitched {len(new_rest_rows)} live REST metrics bars for {symbol} up to {master_metrics['create_time'].iloc[-1]} UTC.")
        except Exception as e:
            print(f"  [WARN] Live REST metrics bridge for {symbol} encountered non-fatal error: {e}")

        print(f"[FETCHER] Total Historical Metrics records loaded for {symbol}: {len(master_metrics):,} rows")
        return master_metrics

    # --------------------------------------------------------------------------
    # 3. Continuous Funding Rates Ingestion (2020 -> Present)
    # --------------------------------------------------------------------------
    def fetch_all_funding_rates(self, symbol: str = "BTCUSDT", start_time_ms: int = 1577836800000) -> pd.DataFrame:
        """
        Fetches all 8h funding rates via paginated REST API.
        """
        cache_file = os.path.join(self.funding_dir, f"{symbol}_funding_rates_master.csv")
        print(f"[FETCHER] Fetching Historical Funding Rates for {symbol}...")
        
        all_rates = []
        cur_start = start_time_ms
        while True:
            url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}&startTime={cur_start}&limit=1000"
            raw = self._fetch_url(url)
            if not raw:
                break
            try:
                data = json.loads(raw.decode('utf-8'))
                if not data or not isinstance(data, list):
                    break
                for item in data:
                    all_rates.append({
                        "fundingTime": int(item["fundingTime"]),
                        "fundingRate": float(item["fundingRate"]),
                    })
                if len(data) < 1000:
                    break
                cur_start = int(data[-1]["fundingTime"]) + 1
            except Exception:
                break

        if all_rates:
            df = pd.DataFrame(all_rates)
            df.drop_duplicates(subset=["fundingTime"], inplace=True)
            df.sort_values(by="fundingTime", inplace=True)
            df.reset_index(drop=True, inplace=True)
            df.to_csv(cache_file, index=False)
            print(f"[FETCHER] Total Historical Funding Rates loaded for {symbol}: {len(df):,} events")
            return df
        elif os.path.exists(cache_file):
            return pd.read_csv(cache_file)
        
        return pd.DataFrame(columns=["fundingTime", "fundingRate"])
