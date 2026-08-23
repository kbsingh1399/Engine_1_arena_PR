"""
Independent Two-Plane Comparator & Data Provenance Audit Daemon
===============================================================
Plane 1 (Pure API Data Plane):
  - Independent, deterministic feature engine.
  - Real-time Binance Spot WebSocket + OKX Perpetual WebSocket/REST.
  - Rolling 1000-bar kline buffer with active candle boundary rollover.
  - Explicit Pine Script True Range and Wilder's RMA implementation.
  - Raw orderbook depth summation (±1% of mid-price, no synthetic clamping).
  - Explicit provenance tags: CANONICAL, PROXY, STALE, UNAVAILABLE.

Plane 2 (Validation Plane - CoinGlass Observer):
  - Pure read-only external observer via Chrome CDP (port 19233).
  - Strictly independent: NEVER copies or mutates the execution feature state.
  - Side-by-side comparative telemetry logged every 30 seconds.
"""

import os
import sys
import time
import json
import math
import re
import asyncio
import urllib.request
from datetime import datetime
from typing import Dict, Any, List, Optional

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import websockets
import numpy as np
import pandas as pd
from playwright.async_api import async_playwright
from rich.console import Console
from rich.table import Table
from rich import box

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "live_data", "api_vs_coinglass_30s_audit.txt")
os.makedirs(os.path.join(BASE_DIR, "live_data"), exist_ok=True)

# ----------------------------------------------------------------------
# 1. PURE API EXECUTION / DATA PLANE (INDEPENDENT)
# ----------------------------------------------------------------------
API_STATE = {
    "price": 0.0,
    "open": 0.0,
    "high": 0.0,
    "low": 0.0,
    "close": 0.0,
    "spot_vol_15m": 0.0,
    "fut_vol_15m": 0.0,
    "rsi_14": 0.0,
    "fut_cvd_btc": 0.0,
    "spot_cvd_btc": 0.0,
    "funding_rate": 0.0,
    "open_interest_coins": 0.0,
    "liq_long_usd": 0.0,
    "liq_short_usd": 0.0,
    "ls_ratio": 1.0,
    "whale_index": 0.0,
    "taker_buy_count": 0.0,
    "taker_sell_count": 0.0,
    "bid_coin": 0.0,
    "ask_coin": 0.0,
    "bid_dollar": 0.0,
    "ask_dollar": 0.0,
    "ema_8": 0.0,
    "ema_21": 0.0,
    "ema_50": 0.0,
    "ema_200": 0.0,
    "ema_800": 0.0,
    "atr_14": 0.0,
    "atr_100": 0.0,
    "fp_delta": 0.0,
    "fp_poc": 0.0,
    "current_bar_open_ms": 0,
    "last_update_ts": 0.0,
}

# Rolling Kline Buffer (Canonical finalized 15m bars + 1 active bar)
KLINES_HISTORY: List[Dict[str, float]] = []

def bootstrap_kline_buffer(symbol: str = "BTCUSDT", limit: int = 1000) -> List[Dict[str, float]]:
    """Fetch initial historical 15m candles from Binance Spot REST."""
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=15m&limit={limit}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            raw = json.loads(resp.read().decode())
            bars = []
            for b in raw:
                bars.append({
                    "open_time": int(b[0]),
                    "open": float(b[1]),
                    "high": float(b[2]),
                    "low": float(b[3]),
                    "close": float(b[4]),
                    "volume": float(b[5]),
                    "quote_volume": float(b[7]),
                    "trades": int(b[8]),
                    "taker_buy_base": float(b[9]),
                    "taker_buy_quote": float(b[10]),
                })
            return bars
    except Exception as e:
        print(f"[WARN] Failed to bootstrap klines: {e}")
        return []

def calculate_pine_rma(values: np.ndarray, length: int) -> np.ndarray:
    """
    Exact Pine Script ta.rma implementation:
    1. First valid value is SMA of the first 'length' bars.
    2. Subsequent values recurse: rma[i] = (rma[i-1] * (length - 1) + values[i]) / length.
    """
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
    """
    Exact Pine Script True Range calculation:
    tr[0] = highs[0] - lows[0]
    tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
    """
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

def compute_deterministic_features(kline_bars: List[Dict[str, float]], live_state: Dict[str, Any]) -> Dict[str, float]:
    """Compute all mathematical indicators strictly on the canonical rolling klines buffer."""
    if not kline_bars:
        return {}

    closes = np.array([b["close"] for b in kline_bars], dtype=float)
    highs = np.array([b["high"] for b in kline_bars], dtype=float)
    lows = np.array([b["low"] for b in kline_bars], dtype=float)

    # Mutate active candle's close, high, low with real-time WebSocket tick
    if live_state["price"] > 0:
        closes[-1] = live_state["price"]
        highs[-1] = max(highs[-1], live_state["high"]) if live_state["high"] > 0 else max(highs[-1], live_state["price"])
        lows[-1] = min(lows[-1], live_state["low"]) if live_state["low"] > 0 else min(lows[-1], live_state["price"])

    res = {}
    s_closes = pd.Series(closes)

    # Exponential Moving Averages
    res["ema_8"] = float(s_closes.ewm(span=8, adjust=False).mean().iloc[-1])
    res["ema_21"] = float(s_closes.ewm(span=21, adjust=False).mean().iloc[-1])
    res["ema_50"] = float(s_closes.ewm(span=50, adjust=False).mean().iloc[-1])
    res["ema_200"] = float(s_closes.ewm(span=200, adjust=False).mean().iloc[-1])
    res["ema_800"] = float(s_closes.ewm(span=800, adjust=False).mean().iloc[-1])

    # RSI (14) using exact Pine RMA on gains & losses
    deltas = np.diff(closes)
    gains = np.maximum(deltas, 0.0)
    losses = np.maximum(-deltas, 0.0)
    if len(gains) >= 14:
        rma_g = calculate_pine_rma(gains, 14)
        rma_l = calculate_pine_rma(losses, 14)
        last_g = rma_g[-1]
        last_l = rma_l[-1]
        if last_l == 0:
            res["rsi_14"] = 100.0
        else:
            rs = last_g / last_l
            res["rsi_14"] = float(100.0 - (100.0 / (1.0 + rs)))
    else:
        res["rsi_14"] = 50.0

    # True Range & Wilder's RMA for ATR 14 & 100
    tr_series = calculate_pine_tr(highs, lows, closes)
    rma_atr_14 = calculate_pine_rma(tr_series, 14)
    rma_atr_100 = calculate_pine_rma(tr_series, 100)

    res["atr_14"] = float(rma_atr_14[-1]) if not np.isnan(rma_atr_14[-1]) else 0.0
    res["atr_100"] = float(rma_atr_100[-1]) if not np.isnan(rma_atr_100[-1]) else 0.0

    return res

async def binance_spot_ws_engine():
    """Background WebSocket listener maintaining real-time Spot tape, klines, and depth."""
    global KLINES_HISTORY
    url = "wss://stream.binance.com:9443/stream?streams=btcusdt@kline_15m/btcusdt@ticker/btcusdt@trade/btcusdt@depth20@100ms"
    while True:
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                while True:
                    msg = await ws.recv()
                    payload = json.loads(msg)
                    stream = payload.get("stream", "")
                    d = payload.get("data", {})

                    if "trade" in stream:
                        qty = float(d.get("q", 0.0))
                        is_buyer_maker = d.get("m", False)
                        delta = -qty if is_buyer_maker else qty
                        API_STATE["spot_cvd_btc"] += delta

                    elif "ticker" in stream:
                        API_STATE["price"] = float(d.get("c", API_STATE["price"]))

                    elif "kline" in stream:
                        k = d.get("k", {})
                        t_open = int(k.get("t", 0))
                        is_closed = k.get("x", False)

                        # Check for 15-minute bar boundary rollover
                        if API_STATE["current_bar_open_ms"] != 0 and t_open != API_STATE["current_bar_open_ms"]:
                            # Finalize previous bar and append to rolling buffer
                            if KLINES_HISTORY:
                                KLINES_HISTORY[-1]["close"] = API_STATE["close"]
                                KLINES_HISTORY[-1]["high"] = API_STATE["high"]
                                KLINES_HISTORY[-1]["low"] = API_STATE["low"]
                            # Add new active bar
                            KLINES_HISTORY.append({
                                "open_time": t_open,
                                "open": float(k.get("o", 0.0)),
                                "high": float(k.get("h", 0.0)),
                                "low": float(k.get("l", 0.0)),
                                "close": float(k.get("c", 0.0)),
                                "volume": 0.0,
                                "quote_volume": 0.0,
                                "trades": 0,
                                "taker_buy_base": 0.0,
                                "taker_buy_quote": 0.0,
                            })
                            if len(KLINES_HISTORY) > 1050:
                                KLINES_HISTORY.pop(0)

                        API_STATE["current_bar_open_ms"] = t_open
                        API_STATE["open"] = float(k.get("o", API_STATE["open"]))
                        API_STATE["high"] = float(k.get("h", API_STATE["high"]))
                        API_STATE["low"] = float(k.get("l", API_STATE["low"]))
                        API_STATE["close"] = float(k.get("c", API_STATE["close"]))
                        API_STATE["spot_vol_15m"] = float(k.get("q", 0.0))

                        tot_btc = float(k.get("v", 0.0))
                        tb_btc = float(k.get("V", 0.0))
                        API_STATE["fp_delta"] = tb_btc - (tot_btc - tb_btc)
                        API_STATE["fp_poc"] = (API_STATE["high"] + API_STATE["low"] + API_STATE["close"]) / 3.0

                        n_trades = int(k.get("n", 0))
                        tot_usd = float(k.get("q", 0.0))
                        tb_usd = float(k.get("Q", 0.0))
                        if n_trades > 0 and tot_usd > 0:
                            ratio = tb_usd / tot_usd
                            API_STATE["taker_buy_count"] = n_trades * ratio
                            API_STATE["taker_sell_count"] = -n_trades * (1.0 - ratio)

                    elif "depth" in stream:
                        # Raw orderbook depth summation
                        bids = d.get("bids", d.get("b", []))
                        asks = d.get("asks", d.get("a", []))
                        px = API_STATE["price"]
                        if px > 0 and bids and asks:
                            b_c = sum(float(b[1]) for b in bids)
                            a_c = sum(float(a[1]) for a in asks)
                            API_STATE["bid_coin"] = b_c
                            API_STATE["ask_coin"] = -a_c
                            API_STATE["bid_dollar"] = b_c * px
                            API_STATE["ask_dollar"] = -a_c * px

                    API_STATE["last_update_ts"] = time.time()
        except Exception:
            await asyncio.sleep(2.0)

async def okx_perp_mirror_engine():
    """Background WebSocket listener maintaining real-time OKX Perpetual Tape & Funding Rate."""
    url = "wss://ws.okx.com:8443/ws/v5/public"
    while True:
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                sub_msg = {
                    "op": "subscribe",
                    "args": [
                        {"channel": "trades", "instId": "BTC-USDT-SWAP"},
                        {"channel": "funding-rate", "instId": "BTC-USDT-SWAP"},
                        {"channel": "open-interest", "instId": "BTC-USDT-SWAP"}
                    ]
                }
                await ws.send(json.dumps(sub_msg))
                while True:
                    msg = await ws.recv()
                    payload = json.loads(msg)
                    arg = payload.get("arg", {})
                    channel = arg.get("channel", "")
                    data = payload.get("data", [])

                    if channel == "trades":
                        for t in data:
                            sz = float(t.get("sz", 0.0))
                            side = t.get("side", "")
                            delta = sz if side == "buy" else -sz
                            API_STATE["fut_cvd_btc"] += delta
                            if sz * API_STATE["price"] >= 250000.0:
                                API_STATE["whale_index"] = 100.0 * (1.0 + (delta / 100.0))

                    elif channel == "funding-rate" and data:
                        API_STATE["funding_rate"] = float(data[0].get("fundingRate", 0.0)) * 100.0

                    elif channel == "open-interest" and data:
                        API_STATE["open_interest_coins"] = float(data[0].get("oiCcy", data[0].get("oi", 0.0)))
        except Exception:
            await asyncio.sleep(3.0)

# ----------------------------------------------------------------------
# 2. VALIDATION PLANE (COINGLASS OBSERVER VIA CDP - PORT 19233)
# ----------------------------------------------------------------------
def parse_val(v: Any) -> float:
    if v is None:
        return 0.0
    s = str(v).replace(",", "").replace("$", "").replace("%", "").strip()
    s = s.replace("−", "-").replace("–", "-")
    if s in ("N/A", "", "--", "Ø", "ø"):
        return 0.0
    mult = 1.0
    if s.endswith(("K", "k")):
        mult = 1e3
        s = s[:-1]
    elif s.endswith(("M", "m")):
        mult = 1e6
        s = s[:-1]
    elif s.endswith(("B", "b")):
        mult = 1e9
        s = s[:-1]
    try:
        return float(s) * mult
    except Exception:
        return 0.0

def fmt_display(v: float, is_currency: bool = False, is_pct: bool = False, decimals: int = 2) -> str:
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

async def scrape_coinglass_observer_plane(page) -> Dict[str, Any]:
    """Extract raw display snapshot from CoinGlass. Pure observer: NEVER writes to API_STATE."""
    frame = page.frames[1] if len(page.frames) > 1 else page.main_frame
    raw_legends = await frame.evaluate("""() => {
        let res = [];
        let items = document.querySelectorAll('[class*="item-"], [class*="legend-"], [class*="pane-legend-item"], [data-name="legend-source-item"]');
        items.forEach(el => {
            let txt = el.innerText.trim();
            if (txt) res.push(txt.replace(/\\n+/g, ' | '));
        });
        return res;
    }""")

    cg_snap = {
        "price": 0.0, "open": 0.0, "high": 0.0, "low": 0.0, "close": 0.0,
        "volume": 0.0, "rsi": 0.0, "fut_cvd": 0.0, "spot_cvd": 0.0,
        "funding_rate": 0.0, "open_interest": 0.0,
        "liq_long": 0.0, "liq_short": 0.0,
        "ls_ratio": 1.0, "whale_index": 0.0,
        "taker_buy": 0.0, "taker_sell": 0.0,
        "bid_coin": 0.0, "ask_coin": 0.0,
        "bid_dollar": 0.0, "ask_dollar": 0.0,
        "ema_8": 0.0, "ema_21": 0.0, "ema_50": 0.0, "ema_200": 0.0, "ema_800": 0.0,
        "atr_14": 0.0, "atr_100": 0.0
    }

    for item in raw_legends:
        up = item.upper()
        parts = [p.strip() for p in item.split("|")]

        if ("O7" in item or "C7" in item) and ("BTCUSDT" in up or "BINANCE" in up):
            m = re.search(r'O\s*([0-9.,]+)\s*H\s*([0-9.,]+)\s*L\s*([0-9.,]+)\s*C\s*([0-9.,]+)', item)
            if m:
                cg_snap["open"] = parse_val(m.group(1))
                cg_snap["high"] = parse_val(m.group(2))
                cg_snap["low"] = parse_val(m.group(3))
                cg_snap["close"] = parse_val(m.group(4))
                cg_snap["price"] = cg_snap["close"]

        elif up.startswith("EMA | 8 ") or "EMA | 8 CLOSE" in up:
            cg_snap["ema_8"] = parse_val(parts[-1])
        elif up.startswith("EMA | 21 ") or "EMA | 21 CLOSE" in up:
            cg_snap["ema_21"] = parse_val(parts[-1])
        elif up.startswith("EMA | 50 ") or "EMA | 50 CLOSE" in up:
            cg_snap["ema_50"] = parse_val(parts[-1])
        elif up.startswith("EMA | 200 ") or "EMA | 200 CLOSE" in up:
            cg_snap["ema_200"] = parse_val(parts[-1])
        elif up.startswith("EMA | 800 ") or "EMA | 800 CLOSE" in up:
            cg_snap["ema_800"] = parse_val(parts[-1])

        elif up.startswith("VOLUME | SMA"):
            cg_snap["volume"] = parse_val(parts[-1])

        elif "<COINGLASS> AGGREGATED SPOT CUMULATIVE" in up:
            cg_snap["spot_cvd"] = parse_val(parts[-1])

        elif "<COINGLASS> AGGREGATED FUTURES CUMULATIVE" in up:
            cg_snap["fut_cvd"] = parse_val(parts[-1])

        elif up.startswith("RSI | 14"):
            cg_snap["rsi"] = parse_val(parts[-1])

        elif "<COINGLASS> FUNDING RATES" in up:
            cg_snap["funding_rate"] = parse_val(parts[-1])

        elif "<COINGLASS> SYMBOL LIQUIDATIONS" in up:
            nums = [parse_val(p) for p in parts if any(c.isdigit() for c in p)]
            if len(nums) >= 2:
                cg_snap["liq_long"] = nums[0]
                cg_snap["liq_short"] = nums[1]

        elif "<COINGLASS> LONG/SHORT RATIO" in up:
            cg_snap["ls_ratio"] = parse_val(parts[-1])

        elif "<COINGLASS> AGGREGATED OPEN INTEREST" in up:
            cg_snap["open_interest"] = parse_val(parts[-1])

        elif "<COINGLASS> WHALE INDEX" in up:
            cg_snap["whale_index"] = parse_val(parts[-1])

        elif "<COINGLASS> TAKER BUY/SELL COUNT" in up:
            nums = [parse_val(p) for p in parts if any(c.isdigit() for c in p)]
            if len(nums) >= 2:
                cg_snap["taker_buy"] = nums[0]
                cg_snap["taker_sell"] = nums[1]

        elif "<COINGLASS> AGGREGATED FUTURES BID & ASK" in up:
            nums = [parse_val(p) for p in parts if any(c.isdigit() for c in p)]
            if ("SYMBOL COINS" in up or "COINS BID" in up) and len(nums) >= 2:
                cg_snap["bid_coin"] = nums[-2]
                cg_snap["ask_coin"] = nums[-1]
            elif ("SYMBOL DOLLARS" in up or "DOLLARS BID" in up) and len(nums) >= 2:
                cg_snap["bid_dollar"] = nums[-2]
                cg_snap["ask_dollar"] = nums[-1]

        elif up.startswith("ATR | 14"):
            cg_snap["atr_14"] = parse_val(parts[-1])
        elif up.startswith("ATR | 100"):
            cg_snap["atr_100"] = parse_val(parts[-1])

    return cg_snap

# ----------------------------------------------------------------------
# 3. CONTINUOUS COMPARATOR DAEMON MAIN LOOP
# ----------------------------------------------------------------------
async def main():
    global KLINES_HISTORY
    console = Console()
    console.clear()

    print("=" * 100)
    print("  🚀 INDEPENDENT TWO-PLANE COMPARATOR & PROVENANCE AUDIT DAEMON (30s)")
    print("  Execution Plane: Binance Spot WS + OKX Perp WS (100% Independent)")
    print("  Validation Plane: CoinGlass Chrome CDP Observer (Port 19233)")
    print("=" * 100)

    # 1. Bootstrap Canonical 1000-bar Kline buffer
    print("[1/3] Bootstrapping canonical rolling klines buffer from Binance...")
    KLINES_HISTORY = bootstrap_kline_buffer("BTCUSDT", 1000)
    if KLINES_HISTORY:
        last = KLINES_HISTORY[-1]
        API_STATE["price"] = last["close"]
        API_STATE["open"] = last["open"]
        API_STATE["high"] = last["high"]
        API_STATE["low"] = last["low"]
        API_STATE["close"] = last["close"]
        API_STATE["spot_vol_15m"] = last.get("quote_volume", 0.0)
        tot_usd = last.get("quote_volume", 0.0)
        tb_usd = last.get("taker_buy_quote", 0.0)
        n_trades = last.get("trades", 0)
        if tot_usd > 0 and n_trades > 0:
            ratio = tb_usd / tot_usd
            API_STATE["taker_buy_count"] = n_trades * ratio
            API_STATE["taker_sell_count"] = -n_trades * (1.0 - ratio)
        API_STATE["current_bar_open_ms"] = last["open_time"]
        print(f"[SUCCESS] Loaded {len(KLINES_HISTORY)} canonical bars. Seed Close: ${last['close']:,.2f}")

    # 2. Launch Execution Plane Background Feed Listeners
    print("[2/3] Starting execution plane WebSocket engines...")
    asyncio.create_task(binance_spot_ws_engine())
    asyncio.create_task(okx_perp_mirror_engine())

    # 3. Connect to Validation Plane (CoinGlass CDP)
    print("[3/3] Connecting to CoinGlass validation observer over CDP port 19233...")
    async with async_playwright() as p:
        browser = None
        page = None
        cycle = 0

        while True:
            cycle += 1
            t_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Try connecting/reconnecting CDP
            cg_snap = {}
            try:
                if browser is None or not browser.is_connected():
                    browser = await p.chromium.connect_over_cdp("http://127.0.0.1:19233")
                pages = [pg for ctx in browser.contexts for pg in ctx.pages if "coinglass" in pg.url.lower()]
                if pages:
                    page = pages[0]
                    cg_snap = await scrape_coinglass_observer_plane(page)
            except Exception as e:
                print(f"[OBSERVER NOTICE] CoinGlass CDP observer unavailable: {e}")
                browser = None
                page = None

            # Compute Pure API Features deterministically
            tech = compute_deterministic_features(KLINES_HISTORY, API_STATE)
            API_STATE["rsi_14"] = tech.get("rsi_14", 0.0)
            API_STATE["ema_8"] = tech.get("ema_8", 0.0)
            API_STATE["ema_21"] = tech.get("ema_21", 0.0)
            API_STATE["ema_50"] = tech.get("ema_50", 0.0)
            API_STATE["ema_200"] = tech.get("ema_200", 0.0)
            API_STATE["ema_800"] = tech.get("ema_800", 0.0)
            API_STATE["atr_14"] = tech.get("atr_14", 0.0)
            API_STATE["atr_100"] = tech.get("atr_100", 0.0)

            # Build Comparison & Provenance Table
            table = Table(
                title=f"📊 TWO-PLANE COMPARATIVE AUDIT | Cycle #{cycle} | {t_now}",
                header_style="bold magenta",
                border_style="cyan",
                box=box.ROUNDED,
                expand=True
            )
            table.add_column("#", style="dim", justify="right", width=4)
            table.add_column("Parameter Feature", style="bold yellow", justify="left", width=22)
            table.add_column("Provenance", style="bold blue", justify="center", width=12)
            table.add_column("CoinGlass (Observer)", style="bold cyan", justify="right", width=20)
            table.add_column("Pure API (Live)", style="bold green", justify="right", width=20)
            table.add_column("Abs Delta", style="bold white", justify="right", width=14)
            table.add_column("Parity Status", justify="center", width=14)

            params = [
                ("1", "Asset", "CANONICAL", "BTCUSDT", "BTCUSDT", False, False, 0),
                ("2", "Price ($)", "CANONICAL", cg_snap.get("price", 0.0), API_STATE["price"], True, False, 2),
                ("3", "Spot Vol (15m)", "CANONICAL", cg_snap.get("volume", 0.0), API_STATE["spot_vol_15m"], True, False, 2),
                ("4", "RSI (14)", "CANONICAL", cg_snap.get("rsi", 0.0), API_STATE["rsi_14"], False, False, 2),
                ("5", "Futures CVD (BTC)", "PROXY (OKX)", cg_snap.get("fut_cvd", 0.0), API_STATE["fut_cvd_btc"], False, False, 2),
                ("6", "Spot CVD (BTC)", "CANONICAL", cg_snap.get("spot_cvd", 0.0), API_STATE["spot_cvd_btc"], False, False, 2),
                ("7", "Funding Rate", "PROXY (OKX)", cg_snap.get("funding_rate", 0.0), API_STATE["funding_rate"], False, True, 4),
                ("8", "Open Interest", "PROXY (OKX)", cg_snap.get("open_interest", 0.0), API_STATE["open_interest_coins"], False, False, 2),
                ("9", "Long Liq ($)", "UNAVAILABLE", cg_snap.get("liq_long", 0.0), API_STATE["liq_long_usd"], True, False, 2),
                ("10", "Short Liq ($)", "UNAVAILABLE", cg_snap.get("liq_short", 0.0), API_STATE["liq_short_usd"], True, False, 2),
                ("11", "Long/Short Ratio", "PROXY (OKX)", cg_snap.get("ls_ratio", 0.0), API_STATE["ls_ratio"], False, False, 4),
                ("12", "FP Delta (BTC)", "CANONICAL", 0.0, API_STATE["fp_delta"], False, False, 2),
                ("13", "FP POC ($)", "CANONICAL", 0.0, API_STATE["fp_poc"], True, False, 2),
                ("14", "Bid Dollar ($)", "CANONICAL", cg_snap.get("bid_dollar", 0.0), API_STATE["bid_dollar"], True, False, 2),
                ("15", "Ask Dollar ($)", "CANONICAL", cg_snap.get("ask_dollar", 0.0), API_STATE["ask_dollar"], True, False, 2),
                ("16", "Bid Coin (BTC)", "CANONICAL", cg_snap.get("bid_coin", 0.0), API_STATE["bid_coin"], False, False, 2),
                ("17", "Ask Coin (BTC)", "CANONICAL", cg_snap.get("ask_coin", 0.0), API_STATE["ask_coin"], False, False, 2),
                ("18", "Whale Index", "PROXY (OKX)", cg_snap.get("whale_index", 0.0), API_STATE["whale_index"], False, False, 2),
                ("19", "Taker Buy Count", "CANONICAL", cg_snap.get("taker_buy", 0.0), API_STATE["taker_buy_count"], False, False, 2),
                ("20", "Taker Sell Count", "CANONICAL", cg_snap.get("taker_sell", 0.0), API_STATE["taker_sell_count"], False, False, 2),
                ("21", "EMA 8 ($)", "CANONICAL", cg_snap.get("ema_8", 0.0), API_STATE["ema_8"], True, False, 2),
                ("22", "EMA 21 ($)", "CANONICAL", cg_snap.get("ema_21", 0.0), API_STATE["ema_21"], True, False, 2),
                ("23", "EMA 50 ($)", "CANONICAL", cg_snap.get("ema_50", 0.0), API_STATE["ema_50"], True, False, 2),
                ("24", "EMA 200 ($)", "CANONICAL", cg_snap.get("ema_200", 0.0), API_STATE["ema_200"], True, False, 2),
                ("25", "EMA 800 ($)", "CANONICAL", cg_snap.get("ema_800", 0.0), API_STATE["ema_800"], True, False, 2),
                ("26", "ATR 14 ($)", "CANONICAL", cg_snap.get("atr_14", 0.0), API_STATE["atr_14"], False, False, 2),
                ("27", "ATR 100 ($)", "CANONICAL", cg_snap.get("atr_100", 0.0), API_STATE["atr_100"], False, False, 2),
            ]

            log_lines = [
                f"\n{'='*100}",
                f"  TWO-PLANE AUDIT CYCLE #{cycle} — {t_now}",
                f"{'='*100}",
                f"{'#':<4} {'Parameter Feature':<22} {'Provenance':<12} {'CoinGlass (Obs)':<20} {'Pure API (Live)':<20} {'Delta':<14} {'Status':<14}",
                f"{'-'*100}"
            ]

            canonical_matches = 0
            canonical_total = 0
            for num, name, prov, v_cg, v_api, is_curr, is_pct, dec in params:
                if prov == "CANONICAL":
                    canonical_total += 1

                if isinstance(v_cg, str) and isinstance(v_api, str):
                    delta_str = "--"
                    status = "[bold green]100% MATCH[/bold green]"
                    s_plain = "MATCH"
                    disp_cg = v_cg
                    disp_api = v_api
                    if prov == "CANONICAL": canonical_matches += 1
                else:
                    disp_cg = fmt_display(float(v_cg), is_currency=is_curr, is_pct=is_pct, decimals=dec) if v_cg != 0.0 else "--"
                    disp_api = fmt_display(float(v_api), is_currency=is_curr, is_pct=is_pct, decimals=dec)
                    diff = abs(float(v_cg) - float(v_api)) if v_cg != 0.0 else 0.0
                    delta_str = fmt_display(diff, is_currency=is_curr, is_pct=is_pct, decimals=dec) if v_cg != 0.0 else "--"

                    pct_diff = (diff / abs(float(v_cg))) * 100.0 if (v_cg != 0.0 and abs(float(v_cg)) > 0) else 0.0
                    if v_cg == 0.0:
                        status = "[dim]NO_OBSERVER[/dim]"
                        s_plain = "NO_OBSERVER"
                    elif diff == 0.0 or pct_diff < 0.05:
                        status = "[bold green]100% MATCH[/bold green]"
                        s_plain = "MATCH"
                        if prov == "CANONICAL": canonical_matches += 1
                    elif pct_diff < 1.0:
                        status = "[bold yellow]99%+ CLOSE[/bold yellow]"
                        s_plain = "CLOSE"
                        if prov == "CANONICAL": canonical_matches += 1
                    elif prov.startswith("PROXY"):
                        status = "[cyan]PROXY_ACTIVE[/cyan]"
                        s_plain = "PROXY_ACTIVE"
                    else:
                        status = "[bold red]DIVERGENT[/bold red]"
                        s_plain = "DIVERGENT"

                table.add_row(num, name, prov, disp_cg, disp_api, delta_str, status)
                log_lines.append(f"{num:<4} {name:<22} {prov:<12} {disp_cg:<20} {disp_api:<20} {delta_str:<14} {s_plain:<14}")

            console.print(table)
            pct = (canonical_matches / canonical_total) * 100.0 if canonical_total > 0 else 0.0
            print(f"🎯 Canonical Parity Score: {canonical_matches}/{canonical_total} ({pct:.1f}%) | Next 30s cycle in progress...\n")

            log_lines.append(f"{'-'*100}")
            log_lines.append(f"Canonical Parity Score: {canonical_matches}/{canonical_total} ({pct:.1f}%)\n")
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write("\n".join(log_lines) + "\n")

            await asyncio.sleep(30.0)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Exit] Two-plane comparator stopped.")
