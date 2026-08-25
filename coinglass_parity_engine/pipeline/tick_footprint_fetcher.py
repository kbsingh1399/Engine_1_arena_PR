import os
import io
import time
import zipfile
import urllib.request
import urllib.error
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
}

class TickFootprintFetcher:
    def __init__(self, cache_dir: str = "./data_cache", max_workers: int = 8):
        self.cache_dir = os.path.abspath(cache_dir)
        self.fp_dir = os.path.join(self.cache_dir, "footprint_15m")
        self.max_workers = max_workers
        os.makedirs(self.fp_dir, exist_ok=True)

    def _fetch_url(self, url: str, timeout: int = 30) -> Optional[bytes]:
        req = urllib.request.Request(url, headers=HEADERS)
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return resp.read()
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                time.sleep(1.0 * (attempt + 1))
            except Exception as e:
                print(f"[WARN] Fetch {url} failed: {e}")
                time.sleep(1.0 * (attempt + 1))
        return None

    def fetch_footprint(self, symbol: str = "BTCUSDT", start_date: str = "2026-08-20") -> pd.DataFrame:
        print(f"[FOOTPRINT] Fetching daily aggTrades for {symbol} from {start_date} and aggregating to 15m footprint...")
        now = datetime.now(timezone.utc)
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        day_diff = (now - start_dt).days
        all_dates = [(start_dt + pd.Timedelta(days=i)).strftime("%Y-%m-%d") for i in range(day_diff + 1)]

        # Determine sensible price bin step for Footprint POC
        if "BTC" in symbol:
            bin_step = 25.0
        elif "ETH" in symbol:
            bin_step = 1.0
        elif any(c in symbol for c in ["SOL", "BNB", "BCH", "AVAX", "LTC", "APT", "LINK"]):
            bin_step = 0.1
        elif any(c in symbol for c in ["DOT", "NEAR", "UNI", "SUI", "OP", "ARB"]):
            bin_step = 0.01
        else:
            bin_step = 0.0001

        def _process_daily_ticks(ymd: str) -> Optional[pd.DataFrame]:
            cache_file = os.path.join(self.fp_dir, f"{symbol}-footprint-15m-{ymd}.parquet")
            if os.path.exists(cache_file):
                try:
                    return pd.read_parquet(cache_file)
                except Exception:
                    pass
            
            url = f"https://data.binance.vision/data/futures/um/daily/aggTrades/{symbol}/{symbol}-aggTrades-{ymd}.zip"
            data = self._fetch_url(url)
            if not data:
                return None
            
            try:
                zf = zipfile.ZipFile(io.BytesIO(data))
                raw_text = zf.read(zf.namelist()[0]).decode('utf-8')
                
                # agg_trade_id, price, quantity, first_trade_id, last_trade_id, transact_time, is_buyer_maker
                df = pd.read_csv(io.StringIO(raw_text), header=None, names=[
                    "agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id", "transact_time", "is_buyer_maker"
                ], dtype=str)
                
                # For safety, if there's a header row inadvertently present
                df = df[pd.to_numeric(df['transact_time'], errors='coerce').notnull()]
                
                df["transact_time"] = df["transact_time"].astype(np.int64)
                df["quantity"] = df["quantity"].astype(np.float64)
                
                # Normalize is_buyer_maker to boolean due to mixed types (str 'True' vs bool True)
                is_bm = df["is_buyer_maker"].astype(str).str.lower().isin(["true", "1", "t", "yes", "y"])
                
                # is_buyer_maker == True -> TAKER SELL. False -> TAKER BUY.
                df["taker_buy"] = (~is_bm).astype(int)
                df["taker_sell"] = is_bm.astype(int)
                
                df["taker_buy_vol"] = df["quantity"] * df["taker_buy"]
                df["taker_sell_vol"] = df["quantity"] * df["taker_sell"]
                
                # Align timestamps to 15m boundary
                df["open_time_ms"] = (df["transact_time"] // 900000) * 900000
                
                # Compute real POC: bin prices
                df["price"] = df["price"].astype(np.float64)
                df["price_bin"] = (df["price"] / bin_step).round() * bin_step
                
                grouped = df.groupby("open_time_ms").agg(
                    total_vol_coin=pd.NamedAgg(column="quantity", aggfunc="sum"),
                    max_single_trade_vol=pd.NamedAgg(column="quantity", aggfunc="max"),
                    taker_buy_vol_coin=pd.NamedAgg(column="taker_buy_vol", aggfunc="sum"),
                    taker_sell_vol_coin=pd.NamedAgg(column="taker_sell_vol", aggfunc="sum"),
                    taker_buy_count=pd.NamedAgg(column="taker_buy", aggfunc="sum"),
                    taker_sell_count=pd.NamedAgg(column="taker_sell", aggfunc="sum")
                ).reset_index()
                
                # Real POC per 15m bar: price_bin with max volume
                poc_df = df.groupby(["open_time_ms", "price_bin"])["quantity"].sum().reset_index()
                poc_df = poc_df.loc[poc_df.groupby("open_time_ms")["quantity"].idxmax()][["open_time_ms", "price_bin"]]
                poc_df.rename(columns={"price_bin": "real_poc"}, inplace=True)
                grouped = grouped.merge(poc_df, on="open_time_ms", how="left")
                
                grouped.to_parquet(cache_file, index=False)
                return grouped
            except Exception as e:
                print(f"[WARN] Error processing {symbol} {ymd}: {e}")
                return None

        dfs = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_date = {executor.submit(_process_daily_ticks, d): d for d in all_dates}
            for future in as_completed(future_to_date):
                res = future.result()
                if res is not None and not res.empty:
                    dfs.append(res)
                    
        if not dfs:
            print(f"[WARN] No footprint data loaded for {symbol}.")
            return pd.DataFrame()
            
        master = pd.concat(dfs, ignore_index=True)
        master.drop_duplicates(subset=["open_time_ms"], inplace=True)
        master.sort_values("open_time_ms", inplace=True)
        master.reset_index(drop=True, inplace=True)
        print(f"[FOOTPRINT] Total footprint rows loaded for {symbol}: {len(master):,}")
        return master
