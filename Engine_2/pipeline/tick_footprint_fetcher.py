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

# Canonical Footprint Price Bin Step per Symbol (Normalized to ~3-6 bps of nominal price)
SYMBOL_BIN_STEPS = {
    "BTCUSDT": 25.0,
    "ETHUSDT": 1.0,
    "BNBUSDT": 0.20,
    "SOLUSDT": 0.10,
    "BCHUSDT": 0.10,
    "LTCUSDT": 0.05,
    "AVAXUSDT": 0.02,
    "LINKUSDT": 0.01,
    "APTUSDT": 0.005,
    "NEARUSDT": 0.002,
    "DOTUSDT": 0.002,
    "SUIUSDT": 0.001,
    "OPUSDT": 0.001,
    "ARBUSDT": 0.0005,
    "XRPUSDT": 0.0005,
    "ADAUSDT": 0.0002,
    "DOGEUSDT": 0.0001,
    "TRXUSDT": 0.0001,
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

    def fetch_footprint(self, symbol: str = "BTCUSDT", start_date: str = "2026-08-20", return_ladder: bool = False):
        print(f"[FOOTPRINT] Fetching daily aggTrades for {symbol} from {start_date} and aggregating to 15m footprint (return_ladder={return_ladder})...")
        now = datetime.now(timezone.utc)
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        day_diff = (now - start_dt).days
        all_dates = [(start_dt + pd.Timedelta(days=i)).strftime("%Y-%m-%d") for i in range(day_diff + 1)]

        bin_step = SYMBOL_BIN_STEPS.get(symbol, 0.001)

        def _process_daily_ticks(ymd: str):
            cache_file = os.path.join(self.fp_dir, f"{symbol}-footprint-15m-{ymd}.parquet")
            ladder_cache_file = os.path.join(self.fp_dir, f"{symbol}-ladder-15m-{ymd}.parquet")
            if os.path.exists(cache_file):
                try:
                    c_df = pd.read_parquet(cache_file)
                    l_df = pd.read_parquet(ladder_cache_file) if os.path.exists(ladder_cache_file) else pd.DataFrame()
                    return c_df, l_df
                except Exception:
                    pass
            
            url = f"https://data.binance.vision/data/futures/um/daily/aggTrades/{symbol}/{symbol}-aggTrades-{ymd}.zip"
            data = self._fetch_url(url)
            if not data:
                return None, None
            
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
                
                # Compute real POC & granular price bins
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
                poc_max = poc_df.loc[poc_df.groupby("open_time_ms")["quantity"].idxmax()][["open_time_ms", "price_bin", "quantity"]]
                poc_max.rename(columns={"price_bin": "real_poc", "quantity": "poc_volume"}, inplace=True)
                grouped = grouped.merge(poc_max, on="open_time_ms", how="left")
                
                # Compute POC Volume Ratio
                grouped["poc_vol_ratio"] = np.round(grouped["poc_volume"] / np.maximum(grouped["total_vol_coin"], 1e-6), 4)
                
                # Compute Stacked Imbalances & Wick Absorptions per 15m candle
                # Aggregate Buy and Sell per Price Bin
                ladder = df.groupby(["open_time_ms", "price_bin"]).agg(
                    b_vol=pd.NamedAgg(column="taker_buy_vol", aggfunc="sum"),
                    s_vol=pd.NamedAgg(column="taker_sell_vol", aggfunc="sum")
                ).reset_index()
                
                # Diagonal imbalance ratio >= 3.0
                ladder["buy_imbalance"] = (ladder["b_vol"] >= 3.0 * np.maximum(ladder["s_vol"], 1e-4)).astype(int)
                ladder["sell_imbalance"] = (ladder["s_vol"] >= 3.0 * np.maximum(ladder["b_vol"], 1e-4)).astype(int)
                
                imbalances = ladder.groupby("open_time_ms").agg(
                    stacked_buy_imbalances=pd.NamedAgg(column="buy_imbalance", aggfunc="sum"),
                    stacked_sell_imbalances=pd.NamedAgg(column="sell_imbalance", aggfunc="sum")
                ).reset_index()
                
                grouped = grouped.merge(imbalances, on="open_time_ms", how="left")
                grouped.drop(columns=["poc_volume"], inplace=True, errors="ignore")
                
                # Format detailed ladder for Table 2
                ladder_export = ladder.copy()
                ladder_export.rename(columns={
                    "b_vol": "ask_vol_coin",
                    "s_vol": "bid_vol_coin",
                    "buy_imbalance": "is_buy_imbalance",
                    "sell_imbalance": "is_sell_imbalance"
                }, inplace=True)
                ladder_export["net_delta_coin"] = ladder_export["ask_vol_coin"] - ladder_export["bid_vol_coin"]
                ladder_export = ladder_export.merge(poc_max[["open_time_ms", "real_poc"]], on="open_time_ms", how="left")
                ladder_export["is_poc"] = (ladder_export["price_bin"] == ladder_export["real_poc"]).astype(int)
                ladder_export.drop(columns=["real_poc"], inplace=True, errors="ignore")
                ladder_export = ladder_export[[
                    "open_time_ms", "price_bin", "bid_vol_coin", "ask_vol_coin", "net_delta_coin",
                    "is_buy_imbalance", "is_sell_imbalance", "is_poc"
                ]]
                
                grouped.to_parquet(cache_file, index=False)
                ladder_cache_file = os.path.join(self.fp_dir, f"{symbol}-ladder-15m-{ymd}.parquet")
                ladder_export.to_parquet(ladder_cache_file, index=False)
                return grouped, ladder_export
            except Exception as e:
                print(f"[WARN] Error processing {symbol} {ymd}: {e}")
                return None, None

        dfs_summary = []
        dfs_ladder = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_date = {executor.submit(_process_daily_ticks, d): d for d in all_dates}
            for future in as_completed(future_to_date):
                res = future.result()
                if res is None:
                    continue
                if isinstance(res, tuple):
                    sum_df, lad_df = res
                else:
                    sum_df, lad_df = res, None
                if sum_df is not None and not sum_df.empty:
                    dfs_summary.append(sum_df)
                if lad_df is not None and not lad_df.empty:
                    dfs_ladder.append(lad_df)
                    
        if not dfs_summary:
            print(f"[WARN] No footprint data loaded for {symbol}.")
            if return_ladder:
                return pd.DataFrame(), pd.DataFrame()
            return pd.DataFrame()
            
        master_summary = pd.concat(dfs_summary, ignore_index=True)
        master_summary.drop_duplicates(subset=["open_time_ms"], inplace=True)
        master_summary.sort_values("open_time_ms", inplace=True)
        master_summary.reset_index(drop=True, inplace=True)
        print(f"[FOOTPRINT] Total footprint candle rows loaded for {symbol}: {len(master_summary):,}")

        if return_ladder and dfs_ladder:
            master_ladder = pd.concat(dfs_ladder, ignore_index=True)
            master_ladder.drop_duplicates(subset=["open_time_ms", "price_bin"], inplace=True)
            master_ladder.sort_values(["open_time_ms", "price_bin"], inplace=True)
            master_ladder.reset_index(drop=True, inplace=True)
            print(f"[FOOTPRINT] Total footprint ladder rungs loaded for {symbol}: {len(master_ladder):,}")
            return master_summary, master_ladder
        elif return_ladder:
            return master_summary, pd.DataFrame()
            
        return master_summary

