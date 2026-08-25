#!/usr/bin/env python3
"""
================================================================================
BINANCE MULTI-ASSET MATRIX LIVE TERMINAL MONITOR (EXCEL TABULAR GRID FORMAT)
================================================================================
Implements the exact multi-asset comparative matrix table requested by user:
- Columns: Parameter | BTC | ETH | XRP | SOL | BNB | DOGE | ADA | TRX | LINK (Tab 1)
           or AVAX | SUI | NEAR | DOT | LTC | BCH | APT | OP | ARB (Tab 2)
- Rows: Volume, RSI, Price, CVD, Funding, OI, Long/Short, Footprint Delta, POC, etc.
================================================================================
"""

import sys
import os
import time
import json
import math
import asyncio
import aiohttp
import websockets
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from collections import deque

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding="utf-8")
os.system("")  # Initialize Windows ANSI VT processing

try:
    _term_w = os.get_terminal_size().columns
except Exception:
    _term_w = 200

RICH_CONSOLE = Console(highlight=False, width=max(_term_w, 180))

TAB1_SYMBOLS = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT", "ADAUSDT", "TRXUSDT", "LINKUSDT"]
TAB2_SYMBOLS = ["AVAXUSDT", "SUIUSDT", "NEARUSDT", "DOTUSDT", "LTCUSDT", "BCHUSDT", "APTUSDT", "OPUSDT", "ARBUSDT"]
ALL_SYMBOLS  = TAB1_SYMBOLS + TAB2_SYMBOLS

# CLI Argument parsing
TARGET_TAB = "ALL"
SELECTED_SYMBOLS = ALL_SYMBOLS

for i, arg in enumerate(sys.argv):
    if arg in ("--tab", "-t") and i + 1 < len(sys.argv):
        t_val = sys.argv[i+1]
        if t_val == "1":
            TARGET_TAB = 1
            SELECTED_SYMBOLS = TAB1_SYMBOLS
        elif t_val == "2":
            TARGET_TAB = 2
            SELECTED_SYMBOLS = TAB2_SYMBOLS
        else:
            TARGET_TAB = "ALL"
            SELECTED_SYMBOLS = ALL_SYMBOLS
    elif arg in ("--symbols", "-s") and i + 1 < len(sys.argv):
        raw_syms = sys.argv[i+1].split(",")
        SELECTED_SYMBOLS = [s.strip().upper() if s.strip().upper().endswith("USDT") else f"{s.strip().upper()}USDT" for s in raw_syms if s.strip()]

def get_base_asset(symbol: str) -> str:
    return symbol[:-4] if symbol.endswith("USDT") else symbol

def get_merge_level(symbol: str) -> float:
    s = symbol.upper()
    if s.startswith("BTC"): return 25.0
    elif s.startswith("ETH"): return 1.0
    elif any(s.startswith(x) for x in ["SOL", "BNB", "BCH", "AVAX", "LTC", "APT", "LINK"]): return 0.1
    elif any(s.startswith(x) for x in ["DOT", "NEAR", "SUI", "OP", "ARB"]): return 0.01
    else: return 0.0001


def fmt_price(p: float) -> str:
    if p >= 1000:
        return f"${p:,.0f}"
    elif p >= 10:
        return f"${p:.1f}"
    elif p >= 1:
        return f"${p:.2f}"
    elif p >= 0.01:
        return f"${p:.3f}"
    else:
        return f"${p:.4f}"


def fmt_ema_pair(e8: float, e21: float) -> str:
    if e8 >= 1000:
        return f"{e8/1e3:.1f}k/{e21/1e3:.1f}k"
    elif e8 >= 10:
        return f"{e8:.0f}/{e21:.0f}"
    elif e8 >= 1:
        return f"{e8:.2f}/{e21:.2f}"
    else:
        return f"{e8:.3f}/{e21:.3f}"


def fmt_compact(v: float) -> str:
    if abs(v) >= 1e9:
        return f"{v/1e9:+.1f}B"
    elif abs(v) >= 1e6:
        return f"{v/1e6:+.1f}M"
    elif abs(v) >= 1e3:
        return f"{v/1e3:+.1f}K"
    elif abs(v) >= 10:
        return f"{v:+.1f}"
    elif abs(v) >= 1:
        return f"{v:+.2f}"
    elif abs(v) > 0:
        return f"{v:+.4f}"
    else:
        return "0.0"


def fmt_vol(v: float) -> str:
    if v >= 1e9: return f"${v/1e9:.1f}B"
    elif v >= 1e6: return f"${v/1e6:.1f}M"
    elif v >= 1e3: return f"${v/1e3:.0f}K"
    else: return f"${v:.0f}"


# ==============================================================================
# SECTION 1: PER-ASSET STATE CONTAINER
# ==============================================================================

@dataclass
class AssetState:
    symbol: str
    base_asset: str = ""
    price: float = 0.0
    spot_price: float = 0.0
    basis: float = 0.0
    quote_vol_15m: float = 0.0
    base_vol_15m: float = 0.0
    vol_sma9: float = 0.0
    rsi: float = 50.0
    atr14: float = 0.0
    atr100: float = 0.0
    fut_cvd: float = 0.0
    fut_buy_15m: float = 0.0
    fut_sell_15m: float = 0.0
    spot_cvd: float = 0.0
    spot_buy_15m: float = 0.0
    spot_sell_15m: float = 0.0
    alt_flow: float = 0.0
    avg_trade_usd: float = 0.0
    funding_rate: float = 0.0
    oi_k: str = "N/A"
    oi_usd: float = 0.0
    oi_chg_pct: float = 0.0
    ls_ratio_global: float = 1.0
    ls_ratio_top: float = 1.0
    whale_index: str = "100.0"
    long_liq_15m: float = 0.0
    short_liq_15m: float = 0.0
    cascade_bias: str = "⚪ Neutral"
    fp_delta: float = 0.0
    fp_poc: float = 0.0
    session_vah: float = 0.0
    session_val: float = 0.0
    prev_day_vah: float = 0.0
    prev_day_val: float = 0.0
    bid_depth_1pct: float = 0.0
    ask_depth_1pct: float = 0.0
    depth_ratio: float = 1.0
    ema8: float = 0.0
    ema21: float = 0.0
    ema200: float = 0.0
    last_update_ts: float = 0.0

    def __post_init__(self):
        self.base_asset = get_base_asset(self.symbol)


ASSET_STATES: Dict[str, AssetState] = {sym: AssetState(symbol=sym) for sym in SELECTED_SYMBOLS}
HTTP_SESSION: Optional[aiohttp.ClientSession] = None


# ==============================================================================
# SECTION 2: FAST ASYNC FETCH & BOOTSTRAP
# ==============================================================================

async def fetch_json(url: str) -> Any:
    global HTTP_SESSION
    if HTTP_SESSION is None or HTTP_SESSION.closed:
        HTTP_SESSION = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5.0))
    try:
        async with HTTP_SESSION.get(url) as resp:
            if resp.status == 200:
                return await resp.json()
    except Exception:
        pass
    return None


def calculate_wilder_rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(0.0, diff))
        losses.append(max(0.0, -diff))
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    
    if avg_loss == 0.0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def calculate_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(closes)):
        h, l, prev_c = highs[i], lows[i], closes[i-1]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
    if not trs:
        return 0.0
    atr = sum(trs[:period]) / period
    for i in range(period, len(trs)):
        atr = (atr * (period - 1) + trs[i]) / period
    return atr


def calculate_ema(closes: List[float], period: int) -> float:
    if not closes: return 0.0
    if len(closes) < period:
        return sum(closes) / len(closes)
    k = 2.0 / (period + 1)
    ema = sum(closes[:period]) / period
    for price in closes[period:]:
        ema = price * k + ema * (1 - k)
    return ema


async def bootstrap_single_asset(sym: str) -> None:
    """Fetches full historical context + derivatives positioning for one symbol."""
    state = ASSET_STATES.get(sym)
    if not state: return

    # 1. Fetch 500 15m klines from Binance Futures
    k_url = f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}&interval=15m&limit=500"
    spot_k_url = f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=15m&limit=1"
    oi_url = f"https://fapi.binance.com/fapi/v1/openInterest?symbol={sym}"
    prem_url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={sym}"
    ratio_g_url = f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={sym}&period=15m&limit=1"
    ratio_t_url = f"https://fapi.binance.com/futures/data/topLongShortPositionRatio?symbol={sym}&period=15m&limit=1"
    depth_url = f"https://fapi.binance.com/fapi/v1/depth?symbol={sym}&limit=100"

    k_data, spot_k_data, oi_data, prem_data, rg_data, rt_data, depth_data = await asyncio.gather(
        fetch_json(k_url),
        fetch_json(spot_k_url),
        fetch_json(oi_url),
        fetch_json(prem_url),
        fetch_json(ratio_g_url),
        fetch_json(ratio_t_url),
        fetch_json(depth_url),
        return_exceptions=True
    )

    if isinstance(k_data, list) and len(k_data) > 0:
        closes = [float(k[4]) for k in k_data]
        highs = [float(k[2]) for k in k_data]
        lows = [float(k[3]) for k in k_data]
        vols = [float(k[7]) for k in k_data]  # Quote volume ($)
        base_vols = [float(k[5]) for k in k_data]
        taker_buys = [float(k[9]) for k in k_data]
        taker_sells = [base_vols[i] - taker_buys[i] for i in range(len(base_vols))]

        state.price = closes[-1]
        state.quote_vol_15m = vols[-1]
        state.base_vol_15m = base_vols[-1]
        state.fut_buy_15m = taker_buys[-1]
        state.fut_sell_15m = taker_sells[-1]
        state.fp_delta = state.fut_buy_15m - state.fut_sell_15m

        # Indicators
        state.rsi = calculate_wilder_rsi(closes, 14)
        state.atr14 = calculate_atr(highs, lows, closes, 14)
        state.atr100 = calculate_atr(highs, lows, closes, 100)
        state.vol_sma9 = sum(vols[-9:]) / min(len(vols), 9) if vols else 0.0
        state.ema8 = calculate_ema(closes, 8)
        state.ema21 = calculate_ema(closes, 21)
        state.ema200 = calculate_ema(closes, 200)

        # Footprint POC approximation from recent candle
        state.fp_poc = round(state.price / get_merge_level(sym)) * get_merge_level(sym)
        state.session_vah = max(highs[-32:]) if len(highs) >= 32 else max(highs)
        state.session_val = min(lows[-32:]) if len(lows) >= 32 else min(lows)
        state.prev_day_vah = max(highs[-96:-32]) if len(highs) >= 96 else state.session_vah
        state.prev_day_val = min(lows[-96:-32]) if len(lows) >= 96 else state.session_val

        # Cumulative CVD estimation
        state.fut_cvd = sum([taker_buys[i] - taker_sells[i] for i in range(len(taker_buys))])

    if isinstance(spot_k_data, list) and len(spot_k_data) > 0:
        state.spot_price = float(spot_k_data[-1][4])
        state.basis = state.price - state.spot_price
        spot_base = float(spot_k_data[-1][5])
        spot_tb = float(spot_k_data[-1][9])
        state.spot_buy_15m = spot_tb
        state.spot_sell_15m = spot_base - spot_tb
        state.spot_cvd = spot_tb - state.spot_sell_15m

    if isinstance(prem_data, dict):
        state.funding_rate = float(prem_data.get("lastFundingRate", 0.0)) * 100.0

    if isinstance(oi_data, dict):
        oi_coin = float(oi_data.get("openInterest", 0.0))
        state.oi_usd = oi_coin * state.price
        state.oi_k = f"${state.oi_usd/1e6:.0f}M" if state.oi_usd >= 1e6 else f"${state.oi_usd/1e3:.0f}K"

    if isinstance(rg_data, list) and len(rg_data) > 0:
        state.ls_ratio_global = float(rg_data[0].get("longShortRatio", 1.0))

    if isinstance(rt_data, list) and len(rt_data) > 0:
        raw_r = float(rt_data[0].get("longShortRatio", 1.0))
        state.ls_ratio_top = raw_r
        state.whale_index = f"{raw_r * 100.0:.1f}"

    if isinstance(depth_data, dict):
        bids = depth_data.get("bids", [])
        asks = depth_data.get("asks", [])
        curr_p = state.price or 1.0
        bid_usd = sum([float(b[0]) * float(b[1]) for b in bids if float(b[0]) >= curr_p * 0.99])
        ask_usd = sum([float(a[0]) * float(a[1]) for a in asks if float(a[0]) <= curr_p * 1.01])
        state.bid_depth_1pct = bid_usd
        state.ask_depth_1pct = ask_usd
        state.depth_ratio = (bid_usd / ask_usd) if ask_usd > 0 else 1.0

    state.last_update_ts = time.time()


# ==============================================================================
# SECTION 3: TABULAR MATRIX RENDERER (EXCEL FORMAT)
# ==============================================================================

def render_matrix_table() -> None:
    """
    Renders the exact Excel matrix grid requested by the user:
    - Column 1: Parameter Name
    - Column 2..N: Asset Symbols (all 18 assets side-by-side)
    """
    curr_time = datetime.now().strftime("%H:%M:%S")
    tab_name = f"All {len(SELECTED_SYMBOLS)} Assets"
    
    # Header Banner
    banner = Table.grid(expand=True)
    banner.add_column(justify="left", ratio=1)
    banner.add_column(justify="right", ratio=1)
    banner.add_row(
        f"[bold yellow]⚡ BINANCE ALL-18 ASSET MATRIX TERMINAL[/bold yellow] | [bold cyan]{tab_name}[/bold cyan]",
        f"[cyan]Clock: {curr_time}[/cyan] | Stream: [bold green]CANONICAL LIVE ●[/bold green]"
    )
    RICH_CONSOLE.print(Panel(banner, box=box.ROUNDED, style="bright_blue"))

    # Construct the Master Comparative Matrix Table
    table = Table(box=box.SIMPLE_HEAVY, expand=True, show_header=True, header_style="bold bright_white on blue")
    
    # First Column: Parameter Name
    table.add_column("Parameter", style="bold cyan", min_width=16, no_wrap=True)

    # Columns 2..N: One column per asset symbol
    for sym in SELECTED_SYMBOLS:
        base = get_base_asset(sym)
        table.add_column(f"{base}", justify="right", style="bold white", min_width=6, no_wrap=True)

    # Helper row adder
    def add_metric_row(label: str, getter_func):
        row_vals = [label]
        for sym in SELECTED_SYMBOLS:
            st = ASSET_STATES.get(sym)
            if st and st.price > 0:
                row_vals.append(getter_func(st))
            else:
                row_vals.append("[dim]...[/dim]")
        table.add_row(*row_vals)

    # 1. Price & Basis Section
    add_metric_row("Price ($)", lambda s: f"[bold green]{fmt_price(s.price)}[/bold green]")
    add_metric_row("Basis ($)", lambda s: f"[green]{s.basis:+.2f}[/green]" if s.basis >= 0 else f"[red]{s.basis:+.2f}[/red]")
    
    table.add_section()
    # 2. 15m Microstructure
    add_metric_row("15m Vol ($M)", lambda s: fmt_vol(s.quote_vol_15m))
    add_metric_row("Vol SMA9 ($)", lambda s: fmt_vol(s.vol_sma9))
    add_metric_row("Wilder RSI", lambda s: (
        f"[bold red]{s.rsi:.1f}[/bold red]" if s.rsi >= 70 else (
        f"[bold green]{s.rsi:.1f}[/bold green]" if s.rsi <= 30 else f"[yellow]{s.rsi:.1f}[/yellow]"
    )))
    add_metric_row("ATR (14)", lambda s: f"{s.atr14:.2f}" if s.atr14 >= 1 else f"{s.atr14:.4f}")

    table.add_section()
    # 3. Orderflow & CVD
    add_metric_row("Fut CVD", lambda s: f"[green]{fmt_compact(s.fut_cvd)}[/green]" if s.fut_cvd >= 0 else f"[red]{fmt_compact(s.fut_cvd)}[/red]")
    add_metric_row("15m Delta", lambda s: f"[green]{fmt_compact(s.fp_delta)}[/green]" if s.fp_delta >= 0 else f"[red]{fmt_compact(s.fp_delta)}[/red]")
    add_metric_row("Spot CVD", lambda s: f"[green]{fmt_compact(s.spot_cvd)}[/green]" if s.spot_cvd >= 0 else f"[red]{fmt_compact(s.spot_cvd)}[/red]")

    table.add_section()
    # 4. Derivatives Positioning & Whale Index
    add_metric_row("Funding (%)", lambda s: f"[green]{s.funding_rate:+.3f}%[/green]" if s.funding_rate >= 0 else f"[red]{s.funding_rate:+.3f}%[/red]")
    add_metric_row("Open Int ($)", lambda s: f"{s.oi_k}")
    add_metric_row("Global L/S", lambda s: f"{s.ls_ratio_global:.2f}")
    add_metric_row("Top L/S", lambda s: f"{s.ls_ratio_top:.2f}")
    add_metric_row("Whale Idx", lambda s: f"[bold gold1]{s.whale_index}[/bold gold1]")

    table.add_section()
    # 5. Footprint & Value Area
    add_metric_row("POC ($)", lambda s: fmt_price(s.fp_poc))
    add_metric_row("VAH (70%)", lambda s: fmt_price(s.session_vah))
    add_metric_row("VAL (70%)", lambda s: fmt_price(s.session_val))

    table.add_section()
    # 6. Order Book Depth & EMAs
    add_metric_row("Bid Depth", lambda s: fmt_vol(s.bid_depth_1pct))
    add_metric_row("Ask Depth", lambda s: fmt_vol(s.ask_depth_1pct))
    add_metric_row("Depth Imbal", lambda s: f"[green]{s.depth_ratio:.1f}x[/green]" if s.depth_ratio >= 1.0 else f"[red]{s.depth_ratio:.1f}x[/red]")
    add_metric_row("EMA 8 / 21", lambda s: fmt_ema_pair(s.ema8, s.ema21))

    RICH_CONSOLE.print(table)


# ==============================================================================
# SECTION 4: MULTI-STREAM WEBSOCKET ENGINE
# ==============================================================================

async def start_combined_futures_ws() -> None:
    """Streams combined aggTrades + liquidations for all selected assets."""
    streams = [f"{sym.lower()}@aggTrade" for sym in SELECTED_SYMBOLS]
    streams.append("!forceOrder@arr")
    streams.append("!markPrice@arr@1s")
    stream_url = f"wss://fstream.binance.com/stream?streams={'/'.join(streams)}"

    while True:
        try:
            async with websockets.connect(stream_url, ping_interval=20, max_size=10_000_000) as ws:
                async for raw_msg in ws:
                    msg = json.loads(raw_msg)
                    stream = msg.get("stream", "")
                    data = msg.get("data", {})
                    
                    if "@aggTrade" in stream:
                        sym = data.get("s", "").upper()
                        st = ASSET_STATES.get(sym)
                        if st:
                            px = float(data.get("p", 0.0))
                            qty = float(data.get("q", 0.0))
                            is_maker = data.get("m", False)
                            st.price = px
                            if not is_maker:
                                st.fut_buy_15m += qty
                                st.fut_cvd += qty
                            else:
                                st.fut_sell_15m += qty
                                st.fut_cvd -= qty
                            st.fp_delta = st.fut_buy_15m - st.fut_sell_15m

                    elif stream == "!markPrice@arr@1s":
                        if isinstance(data, list):
                            for item in data:
                                sym = item.get("s", "").upper()
                                st = ASSET_STATES.get(sym)
                                if st:
                                    st.funding_rate = float(item.get("r", 0.0)) * 100.0

                    elif stream == "!forceOrder@arr":
                        order = data.get("o", {})
                        sym = order.get("s", "").upper()
                        st = ASSET_STATES.get(sym)
                        if st:
                            side = order.get("S", "")
                            orig_qty = float(order.get("q", 0.0))
                            price = float(order.get("p", 0.0))
                            usd = orig_qty * price
                            if side == "SELL":
                                st.long_liq_15m += usd
                            else:
                                st.short_liq_15m += usd
        except Exception:
            await asyncio.sleep(2)


async def background_rest_poller() -> None:
    """Continuously refreshes klines, OI, and Long/Short ratios in parallel."""
    while True:
        tasks = [bootstrap_single_asset(sym) for sym in SELECTED_SYMBOLS]
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(15.0)


async def terminal_matrix_loop() -> None:
    """Renders the matrix table continuously with flicker-free in-place redraw."""
    is_interactive = sys.stdout.isatty() and ("--once" not in sys.argv)
    first_frame = True

    while True:
        if "--once" not in sys.argv:
            await asyncio.sleep(1.0)
        
        if is_interactive:
            if first_frame:
                sys.stdout.write("\033[2J\033[H")
                first_frame = False
            else:
                sys.stdout.write("\033[H")
            sys.stdout.flush()

        render_matrix_table()

        if "--once" in sys.argv:
            break


# ==============================================================================
# SECTION 5: MAIN RUNNER
# ==============================================================================

async def main():
    # 1. Bootstrap all symbols concurrently
    print(f"[INIT] Bootstrapping {len(SELECTED_SYMBOLS)} symbols across Binance REST & WebSockets...")
    tasks = [bootstrap_single_asset(sym) for sym in SELECTED_SYMBOLS]
    await asyncio.gather(*tasks, return_exceptions=True)

    if "--once" in sys.argv:
        render_matrix_table()
        if HTTP_SESSION and not HTTP_SESSION.closed:
            await HTTP_SESSION.close()
        return

    # 2. Spawn concurrent background loops
    asyncio.create_task(start_combined_futures_ws())
    asyncio.create_task(background_rest_poller())
    await terminal_matrix_loop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n[STOPPED] Matrix Monitor exited cleanly.")
