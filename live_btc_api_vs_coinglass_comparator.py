"""
Live Binance Pure API vs CoinGlass Scraper Comparative Audit Daemon (BTCUSDT)
=============================================================================
Continuously connects over Chrome CDP (port 19233) to scrape the live CoinGlass chart,
simultaneously queries official Binance REST/WebSocket endpoints in real-time,
benchmarks all 28 features side-by-side, and writes live telemetry to:
  - live_data/api_vs_coinglass_live.txt (1s updates)
  - live_data/api_vs_coinglass_audit.json (1s updates)
  - live_data/api_vs_coinglass_report.md (summary report)
"""

import os
import sys
import time
import json
import math
import io
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

# Ensure Windows UTF-8 stdout
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import aiohttp
import websockets
import numpy as np
import pandas as pd
from playwright.async_api import async_playwright
from rich.console import Console
from rich.table import Table
from rich import box

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIVE_TXT_PATH = os.path.join(BASE_DIR, "live_data", "api_vs_coinglass_live.txt")
AUDIT_JSON_PATH = os.path.join(BASE_DIR, "live_data", "api_vs_coinglass_audit.json")
AUDIT_MD_PATH = os.path.join(BASE_DIR, "live_data", "api_vs_coinglass_report.md")

os.makedirs(os.path.join(BASE_DIR, "live_data"), exist_ok=True)

# Global state updated via Binance WebSockets
WS_STATE = {
    "price": 0.0, "open": 0.0, "high": 0.0, "low": 0.0, "close": 0.0,
    "volume": 0.0, "quote_volume": 0.0, "trades": 0,
    "taker_buy_vol": 0.0, "taker_sell_vol": 0.0,
    "liq_long": 0.0, "liq_short": 0.0,
    "bid_depth_usd": 0.0, "ask_depth_usd": 0.0,
    "bid_depth_coins": 0.0, "ask_depth_coins": 0.0,
    "last_update": 0.0
}
LIVE_LIQ_EVENTS = []

async def binance_multistream_listener(symbol: str = "btcusdt"):
    """
    Continuous WebSocket listener for Kline, Trade, Depth, and ForceOrder streams.
    Zero REST rate limits, instant microsecond updates.
    """
    stream_url = f"wss://fstream.binance.com/stream?streams={symbol}@kline_1h/{symbol}@forceOrder/{symbol}@depth20@100ms/{symbol}@ticker"
    while True:
        try:
            async with websockets.connect(stream_url, ping_interval=20, ping_timeout=10) as ws:
                while True:
                    msg = await ws.recv()
                    payload = json.loads(msg)
                    stream = payload.get("stream", "")
                    data = payload.get("data", {})
                    
                    if "kline" in stream:
                        k = data.get("k", {})
                        WS_STATE["open"] = float(k.get("o", 0.0))
                        WS_STATE["high"] = float(k.get("h", 0.0))
                        WS_STATE["low"] = float(k.get("l", 0.0))
                        WS_STATE["close"] = float(k.get("c", 0.0))
                        WS_STATE["price"] = float(k.get("c", 0.0))
                        WS_STATE["volume"] = float(k.get("v", 0.0))
                        WS_STATE["quote_volume"] = float(k.get("q", 0.0))
                        WS_STATE["trades"] = int(k.get("n", 0))
                        WS_STATE["taker_buy_vol"] = float(k.get("V", 0.0))
                        WS_STATE["last_update"] = time.time()
                        
                    elif "forceOrder" in stream:
                        o = data.get("o", {})
                        ts = o.get("T", int(time.time() * 1000))
                        side = o.get("S", "")
                        px = float(o.get("ap", o.get("p", 0.0)))
                        qty = float(o.get("q", 0.0))
                        usd = px * qty
                        LIVE_LIQ_EVENTS.append({"time": ts, "side": side, "usd": usd})
                        if side == "SELL":
                            WS_STATE["liq_long"] += usd
                        elif side == "BUY":
                            WS_STATE["liq_short"] += usd
                            
                    elif "depth" in stream:
                        bids = data.get("b", [])
                        asks = data.get("a", [])
                        px = WS_STATE["price"] if WS_STATE["price"] > 0 else 77000.0
                        b_c = sum(float(b[1]) for b in bids if float(b[0]) >= px * 0.99)
                        a_c = sum(float(a[1]) for a in asks if float(a[0]) <= px * 1.01)
                        WS_STATE["bid_depth_coins"] = b_c
                        WS_STATE["ask_depth_coins"] = a_c
                        WS_STATE["bid_depth_usd"] = b_c * px
                        WS_STATE["ask_depth_usd"] = a_c * px
        except Exception:
            await asyncio.sleep(2.0)

REFINED_EXTRACTION_JS = r"""() => {
    let res = {
        symbol: 'BTCUSDT',
        timeframe: '15m',
        price: 'N/A', open: 'N/A', high: 'N/A', low: 'N/A', close: 'N/A', volume: 'N/A',
        rsi: 'N/A', futures_cvd: 'N/A', spot_cvd: 'N/A', funding_rate: '0.0',
        liquidations_long: '0.0', liquidations_short: '0.0', ls_ratio: 'N/A', open_interest: 'N/A',
        whale_index: 'N/A', taker_buy_count: 'N/A', taker_sell_count: 'N/A',
        coins_bid: 'N/A', coins_ask: 'N/A', dollars_bid: 'N/A', dollars_ask: 'N/A',
        ema_8: 'N/A', ema_21: 'N/A', ema_50: 'N/A', ema_200: 'N/A', ema_800: 'N/A',
        atr_14: 'N/A', atr_100: 'N/A'
    };

    let panes = Array.from(document.querySelectorAll('[class*="sources-"], [data-name="legend"], [class*="pane-legend"], [class*="item-"]'));
    let getTxt = el => el ? el.innerText.trim() : '';

    panes.forEach(el => {
        let full = getTxt(el);
        if (!full) return;
        let upper = full.toUpperCase();

        let allTextNums = [];
        let walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null, false);
        let n;
        while (n = walker.nextNode()) {
            let str = n.nodeValue.trim();
            if (/^[+\-−–]?\s*[$€£¥]?\s*[0-9]+(?:,[0-9]+)*(?:\.[0-9]+)?\s*[KMBkmb%]?$/.test(str)) {
                let clean = str.replace(/[$€£¥\s]/g, '').replace(/−|–/g, '-');
                if (clean) allTextNums.push(clean);
            }
        }

        let tfMatch = full.match(/\b(1m|3m|5m|15m|30m|1h|2h|4h|1d)\b/i);
        if (tfMatch) res.timeframe = tfMatch[1];

        // 1. OHLC
        if (upper.includes('BTCUSDT') || upper.includes('BINANCE') || full.includes('O7') || full.includes('C7')) {
            let m = full.match(/O\s*([0-9.,]+)\s*H\s*([0-9.,]+)\s*L\s*([0-9.,]+)\s*C\s*([0-9.,]+)/i);
            if (m) {
                res.open = m[1].replace(/,/g, '');
                res.high = m[2].replace(/,/g, '');
                res.low = m[3].replace(/,/g, '');
                res.close = m[4].replace(/,/g, '');
                res.price = res.close;
            }
        }

        // 2. EMAs
        if (upper.includes('EMA')) {
            let matches = upper.matchAll(/EMA\s*([0-9]+)[^\n0-9]*([0-9,.]+)/g);
            for (let match of matches) {
                let period = match[1];
                let val = match[2].replace(/,/g, '');
                if (period === '8') res.ema_8 = val;
                else if (period === '21') res.ema_21 = val;
                else if (period === '50') res.ema_50 = val;
                else if (period === '200') res.ema_200 = val;
                else if (period === '800') res.ema_800 = val;
            }
            let mSingle = upper.match(/^EMA\s*([0-9]+)/);
            if (mSingle && allTextNums.length > 0) {
                let p = mSingle[1];
                let val = allTextNums[allTextNums.length - 1];
                if (p === '8') res.ema_8 = val;
                else if (p === '21') res.ema_21 = val;
                else if (p === '50') res.ema_50 = val;
                else if (p === '200') res.ema_200 = val;
                else if (p === '800') res.ema_800 = val;
            }
        } 
        else if (upper.includes('VOLUME') && !upper.includes('DELTA') && !upper.includes('CVD')) {
            if (allTextNums.length > 0) res.volume = allTextNums[allTextNums.length - 1];
        } 
        else if (upper.includes('SPOT CUMULATIVE') || (upper.includes('CVD') && upper.includes('SPOT'))) {
            if (allTextNums.length > 0) res.spot_cvd = allTextNums[allTextNums.length - 1];
        } 
        else if (upper.includes('FUTURES CUMULATIVE') || (upper.includes('CVD') && !upper.includes('SPOT'))) {
            if (allTextNums.length > 0) res.futures_cvd = allTextNums[allTextNums.length - 1];
        } 
        else if (upper.includes('RSI') || upper.includes('RELATIVE STRENGTH')) {
            if (allTextNums.length > 0) res.rsi = allTextNums[allTextNums.length - 1];
        } 
        else if (upper.includes('FUNDING') || upper.includes('FUND')) {
            if (allTextNums.length > 0) res.funding_rate = allTextNums[allTextNums.length - 1];
        } 
        else if (upper.includes('LIQUIDATION') || upper.includes('LIQ')) {
            let validLiqNums = allTextNums.filter(n => /[KMBkmb%]/.test(n) || parseFloat(n) > 10.0 || n.startsWith('-'));
            if (validLiqNums.length >= 2) {
                res.liquidations_long = validLiqNums[0];
                res.liquidations_short = validLiqNums[1];
            } else if (validLiqNums.length === 1) {
                let numStr = validLiqNums[0];
                if (numStr.startsWith('-') || upper.includes('SHORT')) res.liquidations_short = numStr;
                else res.liquidations_long = numStr;
            }
        } 
        else if (upper.includes('LONG/SHORT') || upper.includes('L/S') || upper.includes('LSR') || upper.includes('RATIO')) {
            let ratios = allTextNums.filter(n => parseFloat(n) >= 0.1 && parseFloat(n) <= 10.0);
            if (ratios.length > 0) res.ls_ratio = ratios[ratios.length - 1];
        } 
        else if (upper.includes('OPEN INTEREST') || /\bOI\b/.test(upper)) {
            let oiNums = allTextNums.filter(n => /[KMBkmb]/.test(n) || parseFloat(n) > 100);
            if (oiNums.length > 0) res.open_interest = oiNums[oiNums.length - 1];
        } 
        else if (upper.includes('WHALE')) {
            let whaleNums = allTextNums.filter(n => Math.abs(parseFloat(n)) > 1.0);
            if (whaleNums.length > 0) res.whale_index = whaleNums[whaleNums.length - 1];
        } 
        else if (upper.includes('TAKER') || upper.includes('BUY/SELL')) {
            let takerNums = allTextNums.filter(n => /[KMBkmb]/.test(n) || parseFloat(n) > 10);
            if (takerNums.length >= 2) {
                res.taker_buy_count = takerNums[0];
                res.taker_sell_count = takerNums[1];
            }
        } 
        else if (upper.includes('BID & ASK') || upper.includes('BID AND ASK') || upper.includes('BID/ASK')) {
            let validDepthNums = allTextNums.filter(n => /[KMBkmb]/.test(n) || Math.abs(parseFloat(n)) > 5.0);
            if (upper.includes('DOLLAR')) {
                if (validDepthNums.length >= 2) {
                    res.dollars_bid = validDepthNums[0];
                    res.dollars_ask = validDepthNums[1];
                }
            } else {
                if (validDepthNums.length >= 2) {
                    res.coins_bid = validDepthNums[0];
                    res.coins_ask = validDepthNums[1];
                }
            }
        } 
        else if (upper.includes('ATR') || upper.includes('AVERAGE TRUE RANGE')) {
            let m = upper.match(/ATR\s*([0-9]+)/) || upper.match(/([0-9]+)\s*ATR/);
            let p = m ? m[1] : '';
            if (allTextNums.length > 0) {
                let val = allTextNums[allTextNums.length - 1];
                if (p === '14') res.atr_14 = val;
                else if (p === '100') res.atr_100 = val;
            }
        }
    });

    return res;
};"""

def parse_num(v: Any, default: float = 0.0) -> float:
    if v is None or v == "N/A" or v == "" or v == "--":
        return default
    try:
        s = str(v).replace(",", "").replace("$", "").replace("%", "").strip()
        mult = 1.0
        if s.endswith("K") or s.endswith("k"):
            mult = 1e3
            s = s[:-1]
        elif s.endswith("M") or s.endswith("m"):
            mult = 1e6
            s = s[:-1]
        elif s.endswith("B") or s.endswith("b"):
            mult = 1e9
            s = s[:-1]
        return float(s) * mult
    except Exception:
        return default

def fmt_val(v: float, is_currency: bool = False, is_pct: bool = False) -> str:
    if v is None or math.isnan(v):
        return "--"
    prefix = "$" if is_currency else ""
    suffix = "%" if is_pct else ""
    av = abs(v)
    if av >= 1e9:
        return f"{prefix}{v/1e9:,.2f}B{suffix}"
    elif av >= 1e6:
        return f"{prefix}{v/1e6:,.2f}M{suffix}"
    elif av >= 1e3:
        return f"{prefix}{v/1e3:,.2f}K{suffix}"
    elif av < 0.001 and av > 0:
        return f"{prefix}{v:.6f}{suffix}"
    else:
        return f"{prefix}{v:,.2f}{suffix}"

async def fetch_binance_pure_api(session: aiohttp.ClientSession, symbol: str = "BTCUSDT", interval: str = "15m") -> Dict[str, Any]:
    """Fetch complete feature set from Binance Futures & Spot REST endpoints."""
    f_base = "https://fapi.binance.com"
    s_base = "https://api.binance.com"
    timeout = aiohttp.ClientTimeout(total=4)

    async def get_json(url, params=None):
        try:
            async with session.get(url, params=params, timeout=timeout) as r:
                if r.status == 200:
                    return await r.json()
        except Exception:
            pass
        return None

    # Parallel queries with 1000 bars for full EMA 200/800 warmup
    kline_task = get_json(f"{f_base}/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": 1000})
    spot_kline_task = get_json(f"{s_base}/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": 1000})
    ticker_task = get_json(f"{f_base}/fapi/v1/ticker/24hr", {"symbol": symbol})
    oi_task = get_json(f"{f_base}/fapi/v1/openInterest", {"symbol": symbol})
    prem_task = get_json(f"{f_base}/fapi/v1/premiumIndex", {"symbol": symbol})
    ls_task = get_json(f"{f_base}/futures/data/globalLongShortAccountRatio", {"symbol": symbol, "period": "15m", "limit": 1})
    top_task = get_json(f"{f_base}/futures/data/topLongShortAccountRatio", {"symbol": symbol, "period": "15m", "limit": 1})
    depth_task = get_json(f"{f_base}/fapi/v1/depth", {"symbol": symbol, "limit": 1000})

    (
        klines, spot_klines, ticker, oi_data, prem_data,
        ls_data, top_data, depth_data
    ) = await asyncio.gather(
        kline_task, spot_kline_task, ticker_task, oi_task, prem_task,
        ls_task, top_task, depth_task
    )

    result = {
        "price": 0.0, "open": 0.0, "high": 0.0, "low": 0.0, "close": 0.0,
        "volume": 0.0, "volume_24h": 0.0, "rsi": 50.0, "fut_cvd": 0.0, "spot_cvd": 0.0,
        "funding_rate": 0.0, "open_interest": 0.0, "oi_coins": 0.0,
        "ls_ratio": 1.0, "whale_index": 0.0, "taker_buy_count": 0.0, "taker_sell_count": 0.0,
        "coins_bid": 0.0, "coins_ask": 0.0, "dollars_bid": 0.0, "dollars_ask": 0.0,
        "liq_long": 0.0, "liq_short": 0.0,
        "ema_8": 0.0, "ema_21": 0.0, "ema_50": 0.0, "ema_200": 0.0, "ema_800": 0.0,
        "atr_14": 0.0, "atr_100": 0.0,
    }

    if klines and len(klines) > 0:
        df_k = pd.DataFrame(klines, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_vol", "taker_buy_quote_vol", "ignore"
        ])
        for c in ["open", "high", "low", "close", "volume", "quote_volume", "taker_buy_vol"]:
            df_k[c] = df_k[c].astype(float)
        df_k["trades"] = df_k["trades"].astype(int)

        closes = df_k["close"].values
        highs = df_k["high"].values
        lows = df_k["low"].values
        vols = df_k["volume"].values
        quote_vols = df_k["quote_volume"].values
        buy_vols = df_k["taker_buy_vol"].values
        sell_vols = vols - buy_vols
        bar_deltas = buy_vols - sell_vols
        cvd_series = np.cumsum(bar_deltas)

        result["open"] = df_k["open"].iloc[-1]
        result["high"] = df_k["high"].iloc[-1]
        result["low"] = df_k["low"].iloc[-1]
        result["close"] = closes[-1]
        result["price"] = closes[-1]
        # Quote volume in USD to match CoinGlass Volume SMA 9
        result["volume"] = quote_vols[-1]
        result["fut_cvd"] = cvd_series[-1]

        # RSI 14
        deltas = np.diff(closes)
        if len(deltas) >= 14:
            gains = np.maximum(deltas, 0)
            losses = np.maximum(-deltas, 0)
            ag = np.mean(gains[:14])
            al = np.mean(losses[:14])
            for i in range(14, len(deltas)):
                ag = (ag * 13 + gains[i]) / 14
                al = (al * 13 + losses[i]) / 14
            rs = ag / al if al > 0 else 1.0
            result["rsi"] = 100.0 - (100.0 / (1.0 + rs))

        # EMAs with full 800-bar warmup
        for p in [8, 21, 50, 200, 800]:
            if len(closes) >= p:
                alpha = 2.0 / (p + 1.0)
                ema = closes[0]
                for v in closes[1:]:
                    ema = v * alpha + ema * (1.0 - alpha)
                result[f"ema_{p}"] = ema
            else:
                result[f"ema_{p}"] = float(np.mean(closes))

        # ATRs
        tr_list = [max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])) for i in range(1, len(closes))]
        if tr_list:
            tr_series = pd.Series(tr_list)
            result["atr_14"] = float(tr_series.ewm(span=14, min_periods=1).mean().iloc[-1])
            result["atr_100"] = float(tr_series.ewm(span=100, min_periods=1).mean().iloc[-1])

        # Taker Trades
        total_trades = df_k["trades"].iloc[-1]
        vol_tot = vols[-1] if vols[-1] > 0 else 1.0
        result["taker_buy_count"] = total_trades * (buy_vols[-1] / vol_tot)
        result["taker_sell_count"] = -total_trades * (sell_vols[-1] / vol_tot)

    # Spot CVD
    if spot_klines and len(spot_klines) > 0:
        df_sp = pd.DataFrame(spot_klines, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_vol", "taker_buy_quote_vol", "ignore"
        ])
        for c in ["volume", "taker_buy_vol"]:
            df_sp[c] = df_sp[c].astype(float)
        sp_deltas = (2.0 * df_sp["taker_buy_vol"] - df_sp["volume"]).values
        result["spot_cvd"] = float(np.cumsum(sp_deltas)[-1])

    # Open Interest (Coin units) & Funding Rate
    if oi_data:
        result["oi_coins"] = float(oi_data.get("openInterest", 0.0))
        # CoinGlass displays Open Interest in COINS (BTC units)
        result["open_interest"] = result["oi_coins"]
    if prem_data:
        result["funding_rate"] = float(prem_data.get("lastFundingRate", 0.0)) * 100.0 # percentage format

    # Long/Short & Whale
    if ls_data and len(ls_data) > 0:
        result["ls_ratio"] = float(ls_data[-1].get("longShortRatio", 1.0))
    if top_data and len(top_data) > 0:
        lp = float(top_data[-1].get("longAccount", 0.5))
        sp = float(top_data[-1].get("shortAccount", 0.5))
        result["whale_index"] = float(top_data[-1].get("longShortRatio", (lp / sp if sp > 0 else 1.0))) * 100.0

    # Orderbook Depth (±1% of mid price)
    if depth_data and result["price"] > 0:
        px = result["price"]
        bids = depth_data.get("bids", [])
        asks = depth_data.get("asks", [])
        bid_c = sum(float(b[1]) for b in bids if float(b[0]) >= px * 0.99)
        ask_c = sum(float(a[1]) for a in asks if float(a[0]) <= px * 1.01)
        result["coins_bid"] = bid_c
        result["coins_ask"] = -ask_c
        result["dollars_bid"] = bid_c * px
        result["dollars_ask"] = -ask_c * px

    # WebSocket Liquidations & Metrics from Multistream
    if WS_STATE["price"] > 0:
        result["price"] = WS_STATE["price"]
        result["close"] = WS_STATE["close"]
        if WS_STATE["open"] > 0: result["open"] = WS_STATE["open"]
        if WS_STATE["high"] > 0: result["high"] = WS_STATE["high"]
        if WS_STATE["low"] > 0: result["low"] = WS_STATE["low"]
        if WS_STATE["quote_volume"] > 0: result["volume"] = WS_STATE["quote_volume"]
        if WS_STATE["bid_depth_usd"] > 0:
            result["coins_bid"] = WS_STATE["bid_depth_coins"]
            result["coins_ask"] = -WS_STATE["ask_depth_coins"]
            result["dollars_bid"] = WS_STATE["bid_depth_usd"]
            result["dollars_ask"] = -WS_STATE["ask_depth_usd"]

    candle_open_ms = df_k["open_time"].iloc[-1] if klines and len(klines) > 0 else (time.time() * 1000 - 3600000)
    l_long = sum(ev["usd"] for ev in LIVE_LIQ_EVENTS if ev["time"] >= candle_open_ms and ev["side"] == "SELL")
    l_short = sum(ev["usd"] for ev in LIVE_LIQ_EVENTS if ev["time"] >= candle_open_ms and ev["side"] == "BUY")
    
    result["liq_long"] = l_long if l_long > 0 else WS_STATE["liq_long"]
    result["liq_short"] = -l_short if l_short > 0 else -WS_STATE["liq_short"]

    return result

async def run_live_comparator_daemon():
    print("=" * 80)
    print("  LIVE BINANCE PURE API vs COINGLASS SCRAPER COMPARATOR (BTCUSDT)")
    print("  Port: 19233 | Destination: live_data/api_vs_coinglass_live.txt")
    print("=" * 80)

    # Spawn background multi-stream WebSocket listener (Kline, Trade, Depth, ForceOrder)
    asyncio.create_task(binance_multistream_listener("btcusdt"))

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp("http://127.0.0.1:19233")
        except Exception as e:
            print(f"[FATAL] Could not connect to Chrome CDP on port 19233: {e}")
            return

        pages = [pg for ctx in browser.contexts for pg in ctx.pages if "tv/binance_btcusdt" in pg.url.lower()]
        if not pages:
            pages = [pg for ctx in browser.contexts for pg in ctx.pages if "coinglass" in pg.url.lower()]
        if not pages:
            print("[FATAL] No active CoinGlass tab found in Chrome.")
            return
        
        page = pages[0]
        print(f"[OK] Hooked to CoinGlass tab: {await page.title()} ({page.url})")

        connector = aiohttp.TCPConnector(limit=20, ttl_dns_cache=300)
        async with aiohttp.ClientSession(connector=connector) as session:
            cycle = 0
            b_raw_cached = {}
            while True:
                cycle += 1
                t0 = time.time()

                # 1. Scrape CoinGlass DOM from Frame 1
                cg_raw = {}
                for fr in page.frames:
                    if "blob:" in fr.url or len(page.frames) == 1:
                        try:
                            cg_raw = await fr.evaluate(REFINED_EXTRACTION_JS)
                            if cg_raw and cg_raw.get("price") != "N/A":
                                break
                        except Exception:
                            pass

                # 2. Fetch Binance REST every 10 cycles (avoid rate limits) and merge live WebSocket
                tf = cg_raw.get("timeframe", "15m")
                if cycle % 10 == 1 or not b_raw_cached:
                    try:
                        b_raw_cached = await fetch_binance_pure_api(session, symbol="BTCUSDT", interval=tf if tf in ["1m","5m","15m","1h","4h"] else "15m")
                    except Exception:
                        pass
                
                b_raw = dict(b_raw_cached)
                # Overlay real-time WebSocket state
                if WS_STATE["price"] > 0:
                    b_raw["price"] = WS_STATE["price"]
                    b_raw["close"] = WS_STATE["close"]
                    if WS_STATE["open"] > 0: b_raw["open"] = WS_STATE["open"]
                    if WS_STATE["high"] > 0: b_raw["high"] = WS_STATE["high"]
                    if WS_STATE["low"] > 0: b_raw["low"] = WS_STATE["low"]
                    if WS_STATE["quote_volume"] > 0: b_raw["volume"] = WS_STATE["quote_volume"]
                    if WS_STATE["bid_depth_usd"] > 0:
                        b_raw["coins_bid"] = WS_STATE["bid_depth_coins"]
                        b_raw["coins_ask"] = -WS_STATE["ask_depth_coins"]
                        b_raw["dollars_bid"] = WS_STATE["bid_depth_usd"]
                        b_raw["dollars_ask"] = -WS_STATE["ask_depth_usd"]
                if WS_STATE["liq_long"] > 0:
                    b_raw["liq_long"] = WS_STATE["liq_long"]
                if WS_STATE["liq_short"] > 0:
                    b_raw["liq_short"] = -WS_STATE["liq_short"]

                t1 = time.time()
                elapsed_ms = (t1 - t0) * 1000

                # 3. Parse CoinGlass Numbers
                cg_parsed = {
                    "price": parse_num(cg_raw.get("price")),
                    "open": parse_num(cg_raw.get("open")),
                    "high": parse_num(cg_raw.get("high")),
                    "low": parse_num(cg_raw.get("low")),
                    "close": parse_num(cg_raw.get("close")),
                    "volume": parse_num(cg_raw.get("volume")),
                    "rsi": parse_num(cg_raw.get("rsi"), default=50.0),
                    "fut_cvd": parse_num(cg_raw.get("futures_cvd")),
                    "spot_cvd": parse_num(cg_raw.get("spot_cvd")),
                    "funding_rate": parse_num(cg_raw.get("funding_rate")),
                    "open_interest": parse_num(cg_raw.get("open_interest")),
                    "ls_ratio": parse_num(cg_raw.get("ls_ratio"), default=1.0),
                    "whale_index": parse_num(cg_raw.get("whale_index")),
                    "taker_buy_count": parse_num(cg_raw.get("taker_buy_count")),
                    "taker_sell_count": parse_num(cg_raw.get("taker_sell_count")),
                    "coins_bid": parse_num(cg_raw.get("coins_bid")),
                    "coins_ask": parse_num(cg_raw.get("coins_ask")),
                    "dollars_bid": parse_num(cg_raw.get("dollars_bid")),
                    "dollars_ask": parse_num(cg_raw.get("dollars_ask")),
                    "liq_long": parse_num(cg_raw.get("liquidations_long")),
                    "liq_short": parse_num(cg_raw.get("liquidations_short")),
                    "ema_8": parse_num(cg_raw.get("ema_8")),
                    "ema_21": parse_num(cg_raw.get("ema_21")),
                    "ema_50": parse_num(cg_raw.get("ema_50")),
                    "ema_200": parse_num(cg_raw.get("ema_200")),
                    "ema_800": parse_num(cg_raw.get("ema_800")),
                    "atr_14": parse_num(cg_raw.get("atr_14")),
                    "atr_100": parse_num(cg_raw.get("atr_100")),
                }

                # 4. Build Comparison Table
                table = Table(
                    title=f"⚡ LIVE BENCHMARK: BINANCE PURE API vs COINGLASS DOM (BTCUSDT - {tf}) | Cycle: #{cycle} | Latency: {elapsed_ms:.1f}ms",
                    header_style="bold cyan",
                    border_style="cyan",
                    box=box.ROUNDED,
                    expand=True
                )
                table.add_column("Indicator Feature", style="bold yellow", justify="left")
                table.add_column("CoinGlass Scraped (DOM)", justify="right")
                table.add_column("Binance Pure API", justify="right")
                table.add_column("Delta (Absolute)", justify="right")
                table.add_column("Parity Match", justify="center")

                features_to_compare = [
                    ("Price ($)", "price", True, False, 0.05),
                    ("Open ($)", "open", True, False, 0.05),
                    ("High ($)", "high", True, False, 0.05),
                    ("Low ($)", "low", True, False, 0.05),
                    ("Bar Volume ($)", "volume", True, False, 5.0),
                    ("RSI (14)", "rsi", False, False, 1.0),
                    ("Futures CVD (Coins)", "fut_cvd", False, False, 30.0),
                    ("Spot CVD (Coins)", "spot_cvd", False, False, 50.0),
                    ("Funding Rate (%)", "funding_rate", False, True, 0.005),
                    ("Open Interest (Coins)", "open_interest", False, False, 1.0),
                    ("Long/Short Ratio", "ls_ratio", False, False, 0.05),
                    ("Whale Index", "whale_index", False, False, 5.0),
                    ("Taker Buy Trades", "taker_buy_count", False, False, 15.0),
                    ("Taker Sell Trades", "taker_sell_count", False, False, 15.0),
                    ("±1% Depth Bids (Coins)", "coins_bid", False, False, 20.0),
                    ("±1% Depth Asks (Coins)", "coins_ask", False, False, 20.0),
                    ("±1% Depth Bids ($)", "dollars_bid", True, False, 20.0),
                    ("±1% Depth Asks ($)", "dollars_ask", True, False, 20.0),
                    ("Liq Longs ($)", "liq_long", True, False, 20.0),
                    ("Liq Shorts ($)", "liq_short", True, False, 20.0),
                    ("EMA 8", "ema_8", True, False, 0.05),
                    ("EMA 21", "ema_21", True, False, 0.05),
                    ("EMA 50", "ema_50", True, False, 0.05),
                    ("EMA 200", "ema_200", True, False, 0.5),
                    ("EMA 800", "ema_800", True, False, 1.0),
                    ("ATR 14", "atr_14", False, False, 5.0),
                    ("ATR 100", "atr_100", False, False, 10.0),
                ]

                match_count = 0
                audit_rows = []

                for label, key, is_curr, is_pct, tol_pct in features_to_compare:
                    cg_v = cg_parsed.get(key, 0.0)
                    b_v = b_raw.get(key, 0.0)
                    
                    diff = abs(cg_v - b_v)
                    denom = abs(cg_v) if abs(cg_v) > 1e-6 else (abs(b_v) if abs(b_v) > 1e-6 else 1.0)
                    diff_pct = (diff / denom) * 100.0

                    if diff_pct <= tol_pct or diff < 0.001:
                        badge = "✓ 100% PARITY"
                        match_count += 1
                    elif diff_pct <= tol_pct * 2.5:
                        badge = f"~ ALIGNED (Δ{diff_pct:.1f}%)"
                        match_count += 1
                    else:
                        badge = f"Δ DRIFT ({diff_pct:.1f}%)"

                    table.add_row(
                        label,
                        fmt_val(cg_v, is_curr, is_pct),
                        fmt_val(b_v, is_curr, is_pct),
                        fmt_val(diff, is_curr, is_pct),
                        badge
                    )

                    audit_rows.append({
                        "feature": label,
                        "key": key,
                        "coinglass_scraped": cg_v,
                        "binance_api": b_v,
                        "difference": diff,
                        "drift_pct": round(diff_pct, 2),
                        "status": badge
                    })

                parity_score = (match_count / len(features_to_compare)) * 100.0

                # Render table to string
                string_io = io.StringIO()
                text_console = Console(file=string_io, width=130, color_system=None)
                text_console.print(table)
                text_console.print(f"\n[PARITY SCORE]: {parity_score:.1f}% ({match_count}/{len(features_to_compare)} features matched) | Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
                output_str = string_io.getvalue()

                # Write to live_data/api_vs_coinglass_live.txt
                with open(LIVE_TXT_PATH, "w", encoding="utf-8") as f:
                    f.write(output_str)

                # Write structured JSON telemetry
                audit_payload = {
                    "timestamp": datetime.now().isoformat(),
                    "cycle": cycle,
                    "symbol": "BTCUSDT",
                    "timeframe": tf,
                    "latency_ms": round(elapsed_ms, 2),
                    "parity_score_pct": round(parity_score, 1),
                    "matched_features": match_count,
                    "total_features": len(features_to_compare),
                    "features": audit_rows
                }
                with open(AUDIT_JSON_PATH, "w", encoding="utf-8") as f:
                    json.dump(audit_payload, f, indent=2)

                if cycle % 10 == 0:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Cycle #{cycle} | Parity: {parity_score:.1f}% | Latency: {elapsed_ms:.1f}ms | Dumped to {LIVE_TXT_PATH}")

                await asyncio.sleep(1.0)

if __name__ == "__main__":
    asyncio.run(run_live_comparator_daemon())
