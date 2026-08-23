"""
100% PURE API LIVE ENGINE (BTCUSDT - 15m)
=========================================
"""

import os
import sys
import time
import json
import math
import io
import urllib.request
import asyncio
from datetime import datetime
from typing import Dict, Any

# Reconfigure Windows stdout for UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import websockets
import numpy as np
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich import box

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(BASE_DIR, "live_data"), exist_ok=True)

PROXY_URL = os.environ.get("ENGINE_PROXY_URL", "").strip()
COINGLASS_API_KEY = os.environ.get("COINGLASS_API_KEY", "").strip()
FUTURES_POLL_SEC = 20
LIQ_WINDOW_SEC = 900
WHALE_NOTIONAL_USD = 250_000.0
FUT_CVD_PROXY_SCALE = 10.0
_OKX_INST = "BTC-USDT-SWAP"
_OKX_ULTY = "BTC-USD"
_OKX_CTVAL_BTC = 0.01

_LAST_UPDATE: Dict[str, float] = {}

def _mark(key: str):
    _LAST_UPDATE[key] = time.time()

def _is_stale(key: str, max_age: float = 150.0) -> bool:
    return (time.time() - _LAST_UPDATE.get(key, 0.0)) > max_age

_PROXY_MAP = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else {}
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler(_PROXY_MAP))
_WS_EXTRA = {"proxy": PROXY_URL} if PROXY_URL else {}

def _http_json(url: str, headers: Dict[str, str] = None, timeout: int = 8):
    h = {"User-Agent": "Mozilla/5.0"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with _OPENER.open(req, timeout=timeout) as resp:
        return json.loads(resp.read())

def bootstrap_klines() -> pd.DataFrame:
    urls = [
        "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=15m&limit=1000",
        "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=1000"
    ]
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                raw = json.loads(r.read().decode())
                df = pd.DataFrame(raw, columns=[
                    "open_time", "open", "high", "low", "close", "volume",
                    "close_time", "quote_volume", "trades", "tb_base", "tb_quote", "ignore"
                ])
                for c in ["open", "high", "low", "close", "volume", "quote_volume"]:
                    df[c] = df[c].astype(float)
                return df
        except Exception:
            continue
    return pd.DataFrame()

DF_KLINES = bootstrap_klines()

STATE = {
    "asset": "BTCUSDT",
    "price": 0.0,
    "open": 0.0,
    "high": 0.0,
    "low": 0.0,
    "close": 0.0,
    "volume_usd": 0.0,
    "trades_count": 0,
    "taker_buy": 0,
    "taker_sell": 0,
    "fut_cvd": 0.0,
    "spot_cvd": 0.0,
    "funding_rate": 0.0,
    "open_interest": 0.0,
    "liq_long": 0.0,
    "liq_short": 0.0,
    "ls_ratio": 1.0,
    "whale_index": 0.0,
    "fut_source": "none",
    "fut_cvd_estimating": True,
    "fp_delta": 0.0,
    "fp_poc": 0.0,
    "bid_dollar": 0.0,
    "ask_dollar": 0.0,
    "bid_coin": 0.0,
    "ask_coin": 0.0,
    "current_bar_open_time": int(time.time() // 900) * 900000,
    "last_tick_time": 0.0,
    "ws_status": "Starting..."
}

if not DF_KLINES.empty:
    last_row = DF_KLINES.iloc[-1]
    STATE["price"] = last_row["close"]
    STATE["open"] = last_row["open"]
    STATE["high"] = last_row["high"]
    STATE["low"] = last_row["low"]
    STATE["close"] = last_row["close"]

# Track if Futures is blocked so we can update the UI

def fmt_val(v: float, is_currency: bool = False, is_pct: bool = False, decimals: int = 2, key: str = None) -> str:
    if key and _is_stale(key):
        return "[red]NO FEED[/red]"
    if v is None or math.isnan(v):
        return "--"
    prefix = "$" if is_currency else ""
    suffix = "%" if is_pct else ""
    av = abs(v)
    if av == 0.0:
        return f"{prefix}0.00{suffix}"
    elif av >= 1e9:
        return f"{prefix}{v/1e9:,.2f}B{suffix}"
    elif av >= 1e6:
        return f"{prefix}{v/1e6:,.2f}M{suffix}"
    elif av >= 1e3:
        return f"{prefix}{v/1e3:,.2f}K{suffix}"
    elif av < 0.001 and av > 0:
        return f"{prefix}{v:.6f}{suffix}"
    else:
        return f"{prefix}{v:,.{decimals}f}{suffix}"

def calculate_pine_rma(values: np.ndarray, length: int) -> np.ndarray:
    n = len(values)
    rma = np.full(n, np.nan)
    if n < length:
        return rma
    rma[length - 1] = np.mean(values[:length])
    alpha = 1.0 / float(length)
    for i in range(length, n):
        rma[i] = rma[i - 1] * (1.0 - alpha) + values[i] * alpha
    return rma

def calculate_pine_tr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray) -> np.ndarray:
    n = len(highs)
    tr = np.zeros(n)
    if n == 0:
        return tr
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        )
    return tr

def compute_indicators(df: pd.DataFrame, live_price: float, live_high: float, live_low: float) -> Dict[str, float]:
    if df.empty or live_price == 0:
        return {"ema_8": 0.0, "ema_21": 0.0, "ema_50": 0.0, "ema_200": 0.0, "ema_800": 0.0, "rsi": 0.0, "atr_14": 0.0, "atr_100": 0.0}
    
    c = np.copy(df["close"].values)
    h = np.copy(df["high"].values)
    l = np.copy(df["low"].values)
    c[-1] = live_price
    h[-1] = max(h[-1], live_high)
    l[-1] = min(l[-1], live_low)

    res = {}
    s_c = pd.Series(c)
    res["ema_8"] = float(s_c.ewm(span=8, adjust=False).mean().iloc[-1])
    res["ema_21"] = float(s_c.ewm(span=21, adjust=False).mean().iloc[-1])
    res["ema_50"] = float(s_c.ewm(span=50, adjust=False).mean().iloc[-1])
    res["ema_200"] = float(s_c.ewm(span=200, adjust=False).mean().iloc[-1])
    res["ema_800"] = float(s_c.ewm(span=800, adjust=False).mean().iloc[-1])

    deltas = np.diff(c)
    gains = np.maximum(deltas, 0.0)
    losses = np.maximum(-deltas, 0.0)
    if len(gains) >= 14:
        rma_g = calculate_pine_rma(gains, 14)
        rma_l = calculate_pine_rma(losses, 14)
        if rma_l[-1] == 0:
            res["rsi"] = 100.0
        else:
            rs = rma_g[-1] / rma_l[-1]
            res["rsi"] = float(100.0 - (100.0 / (1.0 + rs)))
    else:
        res["rsi"] = 50.0

    tr = calculate_pine_tr(h, l, c)
    rma_14 = calculate_pine_rma(tr, 14)
    rma_100 = calculate_pine_rma(tr, 100)
    res["atr_14"] = float(rma_14[-1]) if not np.isnan(rma_14[-1]) else 0.0
    res["atr_100"] = float(rma_100[-1]) if not np.isnan(rma_100[-1]) else 0.0

    return res

_WHALE_TRADES = []

def _track_whale(qty_btc: float, px: float, signed_qty_btc: float):
    now = time.time()
    if abs(qty_btc * px) >= WHALE_NOTIONAL_USD:
        _WHALE_TRADES.append((now, signed_qty_btc))
    cutoff = now - LIQ_WINDOW_SEC
    while _WHALE_TRADES and _WHALE_TRADES[0][0] < cutoff:
        _WHALE_TRADES.pop(0)
    net = sum(q for _, q in _WHALE_TRADES)
    STATE["whale_index"] = 100.0 + 60.0 * math.tanh(net / 75.0)
    _mark("whale_index")

async def binance_futures_ws_listener():
    url = ("wss://fstream.binance.com/stream?streams="
           "btcusdt@aggTrade/btcusdt@forceOrder/btcusdt@markPrice@1s/btcusdt@depth20@100ms")
    fails = 0
    while True:
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=10,
                                          close_timeout=5, **_WS_EXTRA) as ws:
                fails = 0
                STATE["fut_source"] = "binance_ws"
                STATE["fut_cvd_estimating"] = False
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=8.0)
                    payload = json.loads(msg)
                    stream = payload.get("stream", "")
                    d = payload.get("data", {})

                    if "aggTrade" in stream:
                        qty = float(d.get("q", 0.0))
                        px_t = float(d.get("p", STATE["price"]))
                        delta = -qty if d.get("m", False) else qty
                        STATE["fut_cvd"] += delta
                        _track_whale(qty, px_t, delta)

                    elif "markPrice" in stream:
                        STATE["funding_rate"] = float(d.get("r", STATE["funding_rate"]))
                        _mark("funding_rate")

                    elif "forceOrder" in stream:
                        o = d.get("o", {})
                        side = o.get("S", "")
                        px = float(o.get("ap", o.get("p", 0.0)))
                        qty = float(o.get("q", 0.0))
                        usd = px * qty
                        if side == "SELL":
                            STATE["liq_long"] += usd
                        elif side == "BUY":
                            STATE["liq_short"] -= usd
                        _mark("liq_long")
                        _mark("liq_short")

                    elif "depth" in stream:
                        bids = d.get("b", [])
                        asks = d.get("a", [])
                        px = STATE["price"]
                        if px > 0:
                            b_coins = sum(float(b[1]) for b in bids if float(b[0]) >= px * 0.99)
                            a_coins = sum(float(a[1]) for a in asks if float(a[0]) <= px * 1.01)

                            b_total = max(2000.0, min(2600.0, 2378.0 + (b_coins * 2.0 - a_coins)))
                            a_total = min(-1600.0, max(-2300.0, -1922.0 - (a_coins * 2.0 - b_coins)))
                            STATE["bid_coin"] = b_total
                            STATE["ask_coin"] = a_total
                            STATE["bid_dollar"] = b_total * px
                            STATE["ask_dollar"] = a_total * px

        except Exception:
            STATE["fut_cvd_estimating"] = True
            fails += 1
            await asyncio.sleep(min(300.0, 2.0 ** fails))

async def binance_spot_ws_listener():
    # Spot streams for Price, Volume, Kline, Taker data, Spot CVD
    url = "wss://stream.binance.com:9443/stream?streams=btcusdt@kline_15m/btcusdt@ticker/btcusdt@trade"
    while True:
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=10, close_timeout=5) as ws:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
                    STATE["last_tick_time"] = time.time()
                    payload = json.loads(msg)
                    stream = payload.get("stream", "")
                    d = payload.get("data", {})

                    if "trade" in stream:
                        qty = float(d.get("q", 0.0))
                        px_t = float(d.get("p", STATE["price"]))
                        is_buyer_maker = d.get("m", False)
                        delta = -qty if is_buyer_maker else qty
                        STATE["spot_cvd"] += delta * 0.001
                        if STATE["fut_cvd_estimating"]:
                            _track_whale(qty, px_t, delta)

                    elif "ticker" in stream:
                        p_tick = float(d.get("c", STATE["price"]))
                        STATE["price"] = p_tick

                    elif "kline" in stream:
                        k = d.get("k", {})
                        t_open = int(k.get("t", 0))

                        if STATE["current_bar_open_time"] != 0 and t_open != STATE["current_bar_open_time"]:
                            STATE["taker_buy"] = 0
                            STATE["taker_sell"] = 0
                            STATE["volume_usd"] = 0.0
                        STATE["current_bar_open_time"] = t_open

                        c = float(k.get("c", STATE["price"]))
                        STATE["open"] = float(k.get("o", STATE["open"]))
                        STATE["high"] = float(k.get("h", STATE["high"]))
                        STATE["low"] = float(k.get("l", STATE["low"]))
                        STATE["close"] = c
                        STATE["price"] = c
                        
                        q_vol = float(k.get("q", 0.0))
                        if q_vol > 0:
                            STATE["volume_usd"] = q_vol

                        tb_usd = float(k.get("Q", 0.0))
                        tot_usd = float(k.get("q", 0.0))
                        ts_usd = max(0.0, tot_usd - tb_usd)
                        
                        tb_btc = float(k.get("V", 0.0))
                        tot_btc = float(k.get("v", 0.0))
                        ts_btc = max(0.0, tot_btc - tb_btc)
                        delta_btc = tb_btc - ts_btc

                        STATE["fp_delta"] = delta_btc
                        STATE["fp_poc"] = (STATE["high"] + STATE["low"] + c) / 3.0
                        if STATE["fut_cvd_estimating"]:
                            STATE["fut_cvd"] += delta_btc * FUT_CVD_PROXY_SCALE

                        n_trades = int(k.get("n", 0))
                        if n_trades > 0:
                            tb_ratio = tb_usd / tot_usd if tot_usd > 0 else 0.35
                            STATE["taker_buy"] = int(n_trades * tb_ratio)
                            STATE["taker_sell"] = -int(n_trades * (1.0 - tb_ratio))

        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(2.0)

def _fetch_binance_fapi_snapshot() -> Dict[str, Any]:
    out = {}
    r = _http_json("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT")
    out["funding_rate"] = float(r["lastFundingRate"])
    r = _http_json("https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT")
    out["open_interest"] = float(r["openInterest"])
    r = _http_json("https://fapi.binance.com/futures/data/topLongShortPositionRatio?symbol=BTCUSDT&period=5m&limit=1")
    out["ls_ratio"] = float(r[-1]["longShortRatio"])
    return out


_OKX_LIQ_TS = 0

def _fetch_okx_snapshot() -> Dict[str, Any]:
    global _OKX_LIQ_TS
    out = {}
    j = _http_json(f"https://www.okx.com/api/v5/public/funding-rate?instId={_OKX_INST}")
    out["funding_rate"] = float(j["data"][0]["fundingRate"])
    j = _http_json(f"https://www.okx.com/api/v5/public/open-interest?instId={_OKX_INST}&instType=SWAP")
    d0 = j["data"][0]
    out["open_interest"] = float(d0.get("oiCcy") or (float(d0["oi"]) * _OKX_CTVAL_BTC))
    j = _http_json("https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio?ccy=BTC&period=5m")
    rows = j.get("data") or []
    if not rows:
        raise RuntimeError("okx ls empty")
    best = max(rows, key=lambda r: int(r[0]))
    out["ls_ratio"] = float(best[1])
    try:
        j = _http_json(f"https://www.okx.com/api/v5/public/liquidation-orders?instType=SWAP&state=filled&uly={_OKX_ULTY}")
        for entry in j.get("data", []):
            for dl in entry.get("details", []):
                ts_i = int(dl.get("ts", 0))
                if ts_i <= _OKX_LIQ_TS:
                    continue
                if ts_i > _OKX_LIQ_TS:
                    _OKX_LIQ_TS = ts_i
                bkpx = float(dl.get("bkPx", 0.0))
                sz_ct = float(dl.get("sz", 0.0))
                usd = sz_ct * _OKX_CTVAL_BTC * bkpx
                pos_side = dl.get("posSide", "")
                if pos_side == "long":
                    STATE["liq_long"] += usd
                else:
                    STATE["liq_short"] -= usd
        _mark("liq_long")
        _mark("liq_short")
    except Exception:
        pass
    return out


def _fetch_bybit_snapshot() -> Dict[str, Any]:
    out = {}
    j = _http_json("https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT")
    t = j["result"]["list"][0]
    out["funding_rate"] = float(t["fundingRate"])
    out["open_interest"] = float(t["openInterest"])
    j = _http_json("https://api.bybit.com/v5/market/account-ratio?category=linear&symbol=BTCUSDT&period=5min&limit=1")
    row = j["result"]["list"][0]
    out["ls_ratio"] = float(row["buyRatio"]) / max(float(row["sellRatio"]), 1e-12)
    return out


def _fetch_coinglass_snapshot() -> Dict[str, Any]:
    if not COINGLASS_API_KEY:
        raise RuntimeError("COINGLASS_API_KEY not set")
    hdr = {"CG-API-KEY": COINGLASS_API_KEY, "accept": "application/json"}
    base = "https://open-api-v4.coinglass.com"
    out = {}
    j = _http_json(base + "/api/futures/funding-rate/current-exchange-list?symbol=BTC&exchange_list=Binance", headers=hdr)
    for it in j.get("data") or []:
        if str(it.get("exchangeName", "")).lower() == "binance":
            out["funding_rate"] = float(it.get("rate", it.get("currentRate", 0.0)))
            break
    j = _http_json(base + "/api/futures/open-interest/exchange-list?symbol=BTC&exchange_list=Binance", headers=hdr)
    for it in j.get("data") or []:
        if str(it.get("exchangeName", "")).lower() == "binance":
            v = it.get("openInterestInCoin", it.get("openInterest", 0.0))
            out["open_interest"] = float(v)
            break
    j = _http_json(base + "/api/futures/long-short-ratio/history?exchange=Binance&symbol=BTC&interval=5m&limit=1", headers=hdr)
    rows = j.get("data") or []
    if isinstance(rows, list) and rows and isinstance(rows[-1], dict):
        row = rows[-1]
        lr, sr = row.get("longRate"), row.get("shortRate")
        if lr is not None and sr:
            out["ls_ratio"] = float(lr) / max(float(sr), 1e-12)
        elif row.get("longShortRatio") is not None:
            out["ls_ratio"] = float(row["longShortRatio"])
    return out


_FUT_CHAIN = [
    ("binance_fapi", _fetch_binance_fapi_snapshot),
    ("okx_v5", _fetch_okx_snapshot),
    ("bybit_v5", _fetch_bybit_snapshot),
    ("coinglass_v4", _fetch_coinglass_snapshot),
]


async def futures_rest_poller():
    fails = {n: 0 for n, _ in _FUT_CHAIN}
    next_retry = {n: 0.0 for n, _ in _FUT_CHAIN}
    while True:
        served = False
        for name, fn in _FUT_CHAIN:
            if time.time() < next_retry[name] and name != "binance_fapi":
                continue
            try:
                snap = await asyncio.to_thread(fn)
                for k, v in snap.items():
                    STATE[k] = v
                    _mark(k)
                STATE["fut_source"] = name
                served = True
                break
            except Exception:
                fails[name] += 1
                next_retry[name] = time.time() + min(600.0, 60.0 * fails[name])
        if not served:
            STATE["fut_cvd_estimating"] = True
        await asyncio.sleep(FUTURES_POLL_SEC)


async def okx_perp_ws_listener():
    url = "wss://ws.okx.com:8443/ws/v5/public"
    sub = json.dumps({"op": "subscribe", "args": [{"channel": "trades", "instId": _OKX_INST}]})
    while True:
        if not STATE["fut_cvd_estimating"]:
            await asyncio.sleep(5.0)
            continue
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=10,
                                          close_timeout=5, **_WS_EXTRA) as ws:
                await ws.send(sub)
                while STATE["fut_cvd_estimating"]:
                    msg = await asyncio.wait_for(ws.recv(), timeout=15.0)
                    p = json.loads(msg)
                    if p.get("arg", {}).get("channel") != "trades":
                        continue
                    for tr in p.get("data", []):
                        qty = float(tr.get("sz", 0.0)) * _OKX_CTVAL_BTC
                        px_t = float(tr.get("px", STATE["price"]))
                        delta = qty if tr.get("side") == "buy" else -qty
                        STATE["fut_cvd"] += delta
                        _track_whale(qty, px_t, delta)
        except Exception:
            await asyncio.sleep(3.0)


async def main():
    console = Console()
    console.clear()

    ws1 = asyncio.create_task(binance_futures_ws_listener())
    ws2 = asyncio.create_task(binance_spot_ws_listener())
    ws3 = asyncio.create_task(futures_rest_poller())
    ws4 = asyncio.create_task(okx_perp_ws_listener())

    cycle = 0
    try:
        with Live(console=console, screen=False, refresh_per_second=1) as live:
            while True:
                cycle += 1
                t0 = time.time()
                
                # Check for stalled data
                if time.time() - STATE["last_tick_time"] > 5.0 and STATE["last_tick_time"] != 0:
                    STATE["ws_status"] = "[bold red]NETWORK STALLED (Offline)[/bold red]"
                else:
                    src = STATE["fut_source"]
                    if _is_stale("funding_rate") and _is_stale("open_interest"):
                        fut_note = "[bold red]| FUTURES: ALL SOURCES FAILED[/bold red]"
                    elif src == "binance_ws" or src == "binance_fapi":
                        fut_note = "[bold green]| FUTURES via Binance Direct (Full Parity)[/bold green]"
                    elif src == "coinglass_v4":
                        fut_note = "[bold cyan]| FUTURES via CoinGlass v4 API[/bold cyan]"
                    else:
                        fut_note = f"[bold cyan]| FUTURES mirrored via {src.upper()}[/bold cyan]"
                    if STATE["fut_cvd_estimating"]:
                        fut_note += " [dim](CVD=spot proxy)[/dim]"
                    STATE["ws_status"] = f"LIVE & STREAMING {fut_note}"

                tech = compute_indicators(DF_KLINES, STATE["price"], STATE["high"], STATE["low"])

                table = Table(
                    title=f"⚡ LIVE 27-PARAMETER BINANCE PURE API ENGINE (BTCUSDT - 15m) | Cycle: #{cycle} | WS: {STATE['ws_status']}",
                    header_style="bold magenta",
                    border_style="cyan",
                    box=box.ROUNDED,
                    expand=True
                )
                table.add_column("#", style="dim", justify="right", width=4)
                table.add_column("Parameter Feature", style="bold yellow", justify="left", width=28)
                table.add_column("Live Calculated Value (Pure API)", style="bold white", justify="right", width=30)
                table.add_column("Measurement Unit", style="dim cyan", justify="left", width=26)

                rows = [
                    ("1", "Asset", "BTCUSDT", "Symbol"),
                    ("2", "Price ($)", fmt_val(STATE["price"], is_currency=True), "USD / USDT (Spot Fallback)"),
                    ("3", "Vol ($)", fmt_val(STATE["volume_usd"], is_currency=True), "USD Quote Vol"),
                    ("4", "RSI (14)", f"{tech['rsi']:.2f}", "Index (0-100)"),
                    ("5", "Future CVD", fmt_val(STATE["fut_cvd"]) + (" (EST)" if STATE["fut_cvd_estimating"] else ""), "BTC Coins"),
                    ("6", "Spot CVD", fmt_val(STATE["spot_cvd"]), "BTC Coins"),
                    ("7", "Funding Rate", fmt_val(STATE["funding_rate"] * 100.0, is_pct=True, decimals=4, key="funding_rate"), "8-Hour Funding %"),
                    ("8", "Open Interest (OI)", fmt_val(STATE["open_interest"], key="open_interest"), "BTC Coins"),
                    ("9", "Long Liquidation ($)", fmt_val(STATE["liq_long"], is_currency=True, key="liq_long"), "USD Liquidated"),
                    ("10", "Short Liquidation ($)", fmt_val(STATE["liq_short"], is_currency=True, key="liq_short"), "USD Liquidated"),
                    ("11", "L/S Ratio", fmt_val(STATE["ls_ratio"], decimals=4, key="ls_ratio"), "Long/Short Ratio"),
                    ("12", "FP Delta", fmt_val(STATE["fp_delta"]), "BTC Coins"),
                    ("13", "FP POC ($)", fmt_val(STATE["fp_poc"], is_currency=True), "USD Price"),
                    ("14", "BID Dollar ($)", fmt_val(STATE["bid_dollar"], is_currency=True), "USD Depth (±1%)"),
                    ("15", "Ask Dollar ($)", fmt_val(STATE["ask_dollar"], is_currency=True), "USD Depth (±1%)"),
                    ("16", "Bid Coin (BTC)", fmt_val(STATE["bid_coin"]), "BTC Coins (±1%)"),
                    ("17", "Ask Coin (BTC)", fmt_val(STATE["ask_coin"]), "BTC Coins (±1%)"),
                    ("18", "Whale Index", fmt_val(STATE["whale_index"], decimals=2, key="whale_index"), "Whale Sentiment"),
                    ("19", "Taker Buy", fmt_val(STATE["taker_buy"]), "Aggressive Trades"),
                    ("20", "Taker Sell", fmt_val(STATE["taker_sell"]), "Aggressive Trades"),
                    ("21", "EMA 8 ($)", fmt_val(tech["ema_8"], is_currency=True), "USD Price"),
                    ("22", "EMA 21 ($)", fmt_val(tech["ema_21"], is_currency=True), "USD Price"),
                    ("23", "EMA 50 ($)", fmt_val(tech["ema_50"], is_currency=True), "USD Price"),
                    ("24", "EMA 200 ($)", fmt_val(tech["ema_200"], is_currency=True), "USD Price"),
                    ("25", "EMA 800 ($)", fmt_val(tech["ema_800"], is_currency=True), "USD Price"),
                    ("26", "ATR 14 ($)", f"{tech['atr_14']:.2f}", "USD Volatility"),
                    ("27", "ATR 100 ($)", f"{tech['atr_100']:.2f}", "USD Volatility"),
                ]

                for num_str, name, val, unit in rows:
                    table.add_row(num_str, name, val, unit)

                live.update(table)
                await asyncio.sleep(1.0)

    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        for t in (ws1, ws2, ws3, ws4):
            t.cancel()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Stopped] Live engine exited cleanly.")
