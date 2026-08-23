"""
CANONICAL MARKET-DATA SERVICE v2
27 indicators via strict Binance APIs.

Improvements over v1:
- True Footprint Delta: aggTrade WebSocket classifies every tick as bid/ask hit
- Running session CVD: accumulated from aggTrade (not windowed REST sum)
- kline_15m WebSocket: live bar updates + incremental EMA/RSI/ATR (no REST re-fetch)
- COIN-M OI added for complete open interest
"""

import asyncio
import json
import sys
import time
import urllib.request
import websockets
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

sys.stdout.reconfigure(encoding="utf-8")


# ─── Data Quality ─────────────────────────────────────────────────────────────
class DataQuality(Enum):
    CANONICAL  = "CANONICAL"
    PARTIAL    = "PARTIAL"
    STALE      = "STALE"
    UNAVAILABLE= "UNAVAILABLE"
    RECOVERING = "RECOVERING"


@dataclass
class FeatureValue:
    value: Any
    quality: DataQuality
    timestamp_ms: int


@dataclass
class FeatureSnapshot:
    sequence_id: int
    receive_timestamp_ms: int
    features: Dict[str, FeatureValue]


# ─── Token Bucket Rate Limiter ────────────────────────────────────────────────
class TokenBucket:
    def __init__(self, capacity, fill_rate):
        self.capacity = capacity
        self.fill_rate = fill_rate
        self.tokens = capacity
        self.last_fill = time.time()
        self.lock = asyncio.Lock()

    async def consume(self, tokens=1):
        async with self.lock:
            now = time.time()
            self.tokens = min(self.capacity, self.tokens + (now - self.last_fill) * self.fill_rate)
            self.last_fill = now
            if self.tokens < tokens:
                await asyncio.sleep((tokens - self.tokens) / self.fill_rate)
                self.tokens = 0
            else:
                self.tokens -= tokens


_rest_bucket = TokenBucket(capacity=200, fill_rate=20)


async def async_fetch(url, timeout=5, weight=1):
    await _rest_bucket.consume(weight)
    loop = asyncio.get_running_loop()
    def _fetch():
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode())
    return await loop.run_in_executor(None, _fetch)


# ─── Orderbook ────────────────────────────────────────────────────────────────
class FuturesDepthBook:
    """Sequence-correct local orderbook with snapshot+diff and self-heal."""
    def __init__(self, symbol, stream_type):
        self.symbol = symbol.lower()
        self.stream_type = stream_type          # "f" = USDT-M/USDC-M, "d" = COIN-M
        self.bids: Dict[float, float] = {}
        self.asks: Dict[float, float] = {}
        self.last_update_id = 0
        self.ready = False
        self.quality = DataQuality.UNAVAILABLE
        self._buffer = []
        self._lock = asyncio.Lock()

    async def sync_snapshot(self):
        self.quality = DataQuality.RECOVERING
        self.ready = False
        self._buffer.clear()
        base = "https://fapi.binance.com/fapi/v1/depth" if self.stream_type == "f" else "https://dapi.binance.com/dapi/v1/depth"
        snap = await async_fetch(f"{base}?symbol={self.symbol.upper()}&limit=1000", weight=10)
        async with self._lock:
            self.bids = {float(p): float(q) for p, q in snap["bids"] if float(q) > 0}
            self.asks = {float(p): float(q) for p, q in snap["asks"] if float(q) > 0}
            self.last_update_id = snap["lastUpdateId"]
            self.ready = True
            self.quality = DataQuality.CANONICAL
            for ev in self._buffer:
                self._apply(ev, buffered=True)
            self._buffer.clear()

    def _apply(self, ev, buffered=False):
        u, pu = ev["u"], ev["pu"]
        if u <= self.last_update_id:
            return
        if not buffered and pu != self.last_update_id:
            self.quality = DataQuality.STALE
            self.ready = False
            return
        for px_s, qty_s in ev.get("b", []):
            px, qty = float(px_s), float(qty_s)
            if qty == 0: self.bids.pop(px, None)
            else: self.bids[px] = qty
        for px_s, qty_s in ev.get("a", []):
            px, qty = float(px_s), float(qty_s)
            if qty == 0: self.asks.pop(px, None)
            else: self.asks[px] = qty
        self.last_update_id = u

    async def handle_event(self, ev):
        async with self._lock:
            if not self.ready:
                self._buffer.append(ev)
                if len(self._buffer) > 100:
                    self._buffer.pop(0)
            else:
                self._apply(ev)

    def depth_within_pct(self, price, pct=0.01):
        if not self.ready or not price:
            return 0.0, 0.0, 0.0, 0.0
        lo, hi = price * (1 - pct), price * (1 + pct)
        bc = ac = bd = ad = 0.0
        coinm = self.stream_type == "d"
        for px, qty in self.bids.items():
            if px >= lo:
                q = (qty * 100 / px) if coinm else qty
                bc += q; bd += (qty * 100) if coinm else (px * q)
        for px, qty in self.asks.items():
            if px <= hi:
                q = (qty * 100 / px) if coinm else qty
                ac += q; ad += (qty * 100) if coinm else (px * q)
        return bc, ac, bd, ad


# ─── Liquidation State ────────────────────────────────────────────────────────
class LiquidationState:
    """Per-candle liq volumes. PARTIAL until a full 15m boundary is crossed."""
    def __init__(self):
        self.current_candle_ts = 0
        self.long_usd = 0.0
        self.short_usd = 0.0
        self.quality = DataQuality.PARTIAL

    def apply(self, ts_ms, side, notional):
        cts = (ts_ms // 900000) * 900000
        if cts != self.current_candle_ts:
            if self.current_candle_ts != 0:
                self.quality = DataQuality.CANONICAL
            self.current_candle_ts = cts
            self.long_usd = self.short_usd = 0.0
        if side == "SELL": self.long_usd += notional
        elif side == "BUY": self.short_usd += notional


# ─── AggTrade State (True FP Delta + Session CVD) ────────────────────────────
class AggTradeState:
    """
    True Footprint Delta and running session CVD from aggTrade ticks.

    is_buyer_maker=True  → buyer is passive (limit order hit by seller) → taker SELL
    is_buyer_maker=False → seller is passive (limit order hit by buyer) → taker BUY
    """
    def __init__(self):
        self.current_candle_ts = 0
        self.candle_buy_btc = 0.0
        self.candle_sell_btc = 0.0
        self.session_cvd = 0.0       # BTC, running since service start
        self.quality = DataQuality.PARTIAL  # PARTIAL until first full candle seen
        self._lock = asyncio.Lock()

    async def apply(self, ts_ms, qty_str, is_buyer_maker):
        cts = (ts_ms // 900000) * 900000
        async with self._lock:
            if cts != self.current_candle_ts:
                if self.current_candle_ts != 0:
                    self.quality = DataQuality.CANONICAL
                self.current_candle_ts = cts
                self.candle_buy_btc = self.candle_sell_btc = 0.0
            qty = float(qty_str)
            if is_buyer_maker:
                self.candle_sell_btc += qty
                self.session_cvd -= qty
            else:
                self.candle_buy_btc += qty
                self.session_cvd += qty

    @property
    def fp_delta(self):
        return self.candle_buy_btc - self.candle_sell_btc


# ─── Kline State (Live Bar + Incremental EMA/RSI/ATR) ────────────────────────
class KlineState:
    """
    Seeded from 1000-bar REST on startup, then updated from kline_15m WebSocket.
    - EMAs updated O(1) on each closed bar
    - RSI (Wilder) updated O(1) on each closed bar
    - ATR updated O(1) on each closed bar
    """
    def __init__(self):
        self.ready = False
        self.quality = DataQuality.UNAVAILABLE
        self._lock = asyncio.Lock()

        # Live bar
        self.open = self.high = self.low = self.close = 0.0
        self.volume = self.taker_buy = self.taker_sell = 0.0

        # Incremental EMA seeds (on closed bars only)
        self._ema = {p: None for p in [8, 21, 50, 200, 800]}

        # Incremental ATR
        self._atr14 = self._atr100 = None
        self._prev_close = None

        # Incremental RSI (Wilder)
        self._avg_gain = self._avg_loss = None
        self._rsi_prev_close = None

    async def seed_from_rest(self, klines):
        """Bootstrap all incremental state from 1000-bar REST response."""
        cls = [float(k[4]) for k in klines]
        his = [float(k[2]) for k in klines]
        los = [float(k[3]) for k in klines]
        closed = cls[:-1]   # All bars except the current open one

        # EMA
        def _ema(cs, p):
            if len(cs) < p: return None
            k = 2.0 / (p + 1)
            e = sum(cs[:p]) / p
            for c in cs[p:]: e = c * k + e * (1 - k)
            return e

        emas = {p: _ema(closed, p) for p in [8, 21, 50, 200, 800]}

        # ATR
        trs = [max(his[i]-los[i], abs(his[i]-cls[i-1]), abs(los[i]-cls[i-1]))
               for i in range(1, len(cls)-1)]   # closed bars only
        def _rma(trs, p):
            if len(trs) < p: return None
            a = sum(trs[:p]) / p
            for t in trs[p:]: a = (a * (p-1) + t) / p
            return a
        atr14 = _rma(trs, 14)
        atr100 = _rma(trs, 100)

        # RSI Wilder
        diffs = [closed[i] - closed[i-1] for i in range(1, len(closed))]
        gains = [max(d, 0.0) for d in diffs]
        losses = [max(-d, 0.0) for d in diffs]
        avg_g = avg_l = None
        if len(gains) >= 14:
            avg_g = sum(gains[:14]) / 14
            avg_l = sum(losses[:14]) / 14
            for i in range(14, len(gains)):
                avg_g = (avg_g * 13 + gains[i]) / 14
                avg_l = (avg_l * 13 + losses[i]) / 14

        lf = klines[-1]
        async with self._lock:
            self._ema = emas
            self._atr14 = atr14
            self._atr100 = atr100
            self._prev_close = closed[-1] if closed else None
            self._avg_gain = avg_g
            self._avg_loss = avg_l
            self._rsi_prev_close = closed[-1] if closed else None

            self.open   = float(lf[1])
            self.high   = float(lf[2])
            self.low    = float(lf[3])
            self.close  = float(lf[4])
            self.volume = float(lf[5])
            self.taker_buy  = float(lf[9])
            self.taker_sell = float(lf[5]) - float(lf[9])

            self.ready = True
            self.quality = DataQuality.CANONICAL

    async def apply_kline_event(self, k):
        is_closed = k.get("x", False)
        async with self._lock:
            self.open   = float(k["o"])
            self.high   = float(k["h"])
            self.low    = float(k["l"])
            self.close  = float(k["c"])
            self.volume = float(k["v"])
            self.taker_buy  = float(k.get("V", 0))
            self.taker_sell = self.volume - self.taker_buy

            if is_closed:
                c = self.close
                # Update EMAs
                for p in [8, 21, 50, 200, 800]:
                    cur = self._ema[p]
                    if cur is not None:
                        kf = 2.0 / (p + 1)
                        self._ema[p] = c * kf + cur * (1 - kf)
                # Update ATR
                if self._prev_close is not None:
                    tr = max(self.high - self.low,
                             abs(self.high - self._prev_close),
                             abs(self.low - self._prev_close))
                    if self._atr14 is not None:
                        self._atr14 = (self._atr14 * 13 + tr) / 14
                    if self._atr100 is not None:
                        self._atr100 = (self._atr100 * 99 + tr) / 100
                # Update RSI
                if self._rsi_prev_close is not None and self._avg_gain is not None:
                    d = c - self._rsi_prev_close
                    self._avg_gain = (self._avg_gain * 13 + max(d, 0.0)) / 14
                    self._avg_loss = (self._avg_loss * 13 + max(-d, 0.0)) / 14
                self._prev_close = c
                self._rsi_prev_close = c
            self.quality = DataQuality.CANONICAL

    def live_ema(self, p):
        """EMA incorporating current open bar's close (not yet committed)."""
        seed = self._ema[p]
        if seed is None: return None
        kf = 2.0 / (p + 1)
        return self.close * kf + seed * (1 - kf)

    @property
    def rsi(self):
        if self._avg_gain is None: return None
        # Live RSI: incorporate current bar delta
        if self._rsi_prev_close is not None:
            d = self.close - self._rsi_prev_close
            ag = (self._avg_gain * 13 + max(d, 0.0)) / 14
            al = (self._avg_loss * 13 + max(-d, 0.0)) / 14
            return 100.0 - 100.0 / (1 + ag / al) if al > 0 else 100.0
        al = self._avg_loss
        return 100.0 - 100.0 / (1 + self._avg_gain / al) if al > 0 else 100.0


# ─── Spot AggTrade State (Running Spot CVD) ──────────────────────────────────
class SpotAggTradeState:
    """
    Running session CVD from spot BTCUSDT aggTrade stream.
    No candle reset — accumulates from service start.
    """
    def __init__(self):
        self.session_cvd = 0.0   # BTC net (buy - sell) since session start
        self.quality = DataQuality.PARTIAL
        self._lock = asyncio.Lock()
        self._first_trade_seen = False

    async def apply(self, qty_str, is_buyer_maker):
        async with self._lock:
            if not self._first_trade_seen:
                self._first_trade_seen = True
                self.quality = DataQuality.CANONICAL
            qty = float(qty_str)
            if is_buyer_maker:
                self.session_cvd -= qty
            else:
                self.session_cvd += qty


# ─── Mark Price State (Funding & Basis) ───────────────────────────────────────
class MarkPriceState:
    """Live mark price, index price, and funding rate."""
    def __init__(self):
        self.mark_price = 0.0
        self.index_price = 0.0
        self.funding_rate = 0.0
        self.quality = DataQuality.PARTIAL
        self._lock = asyncio.Lock()
        
    async def apply(self, d):
        async with self._lock:
            self.mark_price = float(d.get("p", 0))
            self.index_price = float(d.get("i", 0))
            self.funding_rate = float(d.get("r", 0)) * 100.0  # Convert to percent
            self.quality = DataQuality.CANONICAL


# ─── Global State ─────────────────────────────────────────────────────────────
OB_STATE = {
    "btcusdt":   FuturesDepthBook("btcusdt",   "f"),
    "btcusdc":   FuturesDepthBook("btcusdc",   "f"),
    "btcusd_perp": FuturesDepthBook("btcusd_perp", "d"),
}
LIQ_STATE    = LiquidationState()
AGG_STATE    = AggTradeState()
SPOT_AGG     = SpotAggTradeState()
MARK_PRICE   = MarkPriceState()
KL_STATE     = KlineState()
SNAPSHOT_BUS: Optional[asyncio.Queue] = None


# ─── Stream Supervisor ────────────────────────────────────────────────────────
async def stream_supervisor(url, handler, name):
    backoff = 1.0
    while True:
        try:
            async with websockets.connect(url, max_size=10*1024*1024) as ws:
                backoff = 1.0
                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        await handler(json.loads(raw))
                    except asyncio.TimeoutError:
                        continue
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)


# ─── Stream Handlers & Starters ───────────────────────────────────────────────
async def _liq_handler(data):
    o = data.get("data", {}).get("o", {})
    if o:
        LIQ_STATE.apply(
            ts_ms=int(o.get("T", time.time()*1000)),
            side=o.get("S"),
            notional=float(o.get("q",0)) * float(o.get("p",0))
        )

async def start_liq_stream():
    await stream_supervisor(
        "wss://fstream.binance.com/stream?streams=btcusdt@forceOrder/btcusdc@forceOrder",
        _liq_handler, "LiqStream"
    )


async def _ob_handler(book, data):
    await book.handle_event(data)
    if book.quality == DataQuality.STALE:
        await book.sync_snapshot()

async def start_ob_stream(symbol):
    book = OB_STATE[symbol]
    await book.sync_snapshot()
    base = "wss://fstream.binance.com/ws" if book.stream_type == "f" else "wss://dstream.binance.com/ws"
    await stream_supervisor(f"{base}/{symbol}@depth", lambda d: _ob_handler(book, d), f"OB_{symbol}")


async def _agg_handler(data):
    d = data.get("data", data)
    await AGG_STATE.apply(
        ts_ms=int(d.get("T", time.time()*1000)),
        qty_str=d.get("q","0"),
        is_buyer_maker=d.get("m", False)
    )

async def start_agg_trade_stream():
    """Futures aggTrade: True FP Delta + running futures session CVD."""
    await stream_supervisor(
        "wss://fstream.binance.com/stream?streams=btcusdt@aggTrade",
        _agg_handler, "FutAggTrade"
    )


async def _spot_agg_handler(data):
    d = data.get("data", data)
    await SPOT_AGG.apply(
        qty_str=d.get("q", "0"),
        is_buyer_maker=d.get("m", False)
    )

async def start_spot_agg_stream():
    """Spot aggTrade: running spot session CVD — replaces 500-bar REST poll."""
    await stream_supervisor(
        "wss://stream.binance.com:9443/stream?streams=btcusdt@aggTrade",
        _spot_agg_handler, "SpotAggTrade"
    )


async def _kline_handler(data):
    d = data.get("data", data)
    k = d.get("k", {})
    if k:
        await KL_STATE.apply_kline_event(k)

async def start_kline_stream():
    """Seed from REST, then maintain from kline_15m WebSocket."""
    klines = await async_fetch(
        "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=15m&limit=1000", weight=5
    )
    await KL_STATE.seed_from_rest(klines)
    await stream_supervisor(
        "wss://fstream.binance.com/stream?streams=btcusdt@kline_15m",
        _kline_handler, "Kline15m"
    )

async def _mark_price_handler(data):
    d = data.get("data", data)
    await MARK_PRICE.apply(d)

async def start_mark_price_stream():
    """Live Mark Price and Funding Rate (replaces premiumIndex polling)."""
    await stream_supervisor(
        "wss://fstream.binance.com/stream?streams=btcusdt@markPrice",
        _mark_price_handler, "MarkPrice"
    )


# ─── Snapshot Computer ────────────────────────────────────────────────────────
async def compute_snapshot(seq_id):
    try:
        now_ms = int(time.time() * 1000)
        kq = KL_STATE.quality
        close = KL_STATE.close

        # Taker buy/sell: USDT-M from live kline + USDC-M + COIN-M via REST
        tb = KL_STATE.taker_buy
        ts = KL_STATE.taker_sell
        try:
            kuc = await async_fetch("https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDC&interval=15m&limit=1", weight=1)
            tb += float(kuc[-1][9]); ts += float(kuc[-1][5]) - float(kuc[-1][9])
        except Exception: pass
        try:
            kcm = await async_fetch("https://dapi.binance.com/dapi/v1/klines?symbol=BTCUSD_PERP&interval=15m&limit=1", weight=1)
            tb += float(kcm[-1][10]); ts += float(kcm[-1][7]) - float(kcm[-1][10])
        except Exception: pass

        # Spot CVD — running session total from spot aggTrade WebSocket
        scvd = SPOT_AGG.session_cvd
        scvd_q = SPOT_AGG.quality

        # Funding & Basis (from markPrice WS)
        funding = MARK_PRICE.funding_rate
        basis = MARK_PRICE.mark_price - MARK_PRICE.index_price if MARK_PRICE.index_price > 0 else 0.0
        mp_q = MARK_PRICE.quality

        # OI: USDT-M (BTC) + USDC-M (BTC) + COIN-M (contracts×$100÷price = BTC)
        oi_k = 0.0
        try:
            oi_t = float((await async_fetch("https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT", weight=1)).get("openInterest", 0))
            oi_c = float((await async_fetch("https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDC", weight=1)).get("openInterest", 0))
            coinm_raw = float((await async_fetch("https://dapi.binance.com/dapi/v1/openInterest?symbol=BTCUSD_PERP", weight=1)).get("openInterest", 0))
            # COIN-M openInterest = number of contracts; 1 contract = $100 USD
            coinm_btc = (coinm_raw * 100.0) / close if close > 0 else 0.0
            oi_k = (oi_t + oi_c + coinm_btc) / 1e3
        except Exception: pass

        # L/S ratio
        ls_ratio = None
        try:
            ls_d = await async_fetch("https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol=BTCUSDT&period=15m&limit=1", weight=2)
            ls_ratio = float(ls_d[0]["longShortRatio"]) if ls_d else None
        except Exception: pass

        # Whale index
        whale = "N/A"
        try:
            tp = await async_fetch("https://fapi.binance.com/futures/data/topLongShortPositionRatio?symbol=BTCUSDT&period=15m&limit=1", weight=2)
            ta = await async_fetch("https://fapi.binance.com/futures/data/topLongShortAccountRatio?symbol=BTCUSDT&period=15m&limit=1", weight=2)
            if tp and ta:
                whale = f"Pos:{tp[0]['longShortRatio']} Acc:{ta[0]['longShortRatio']}"
        except Exception: pass

        # Orderbook depth
        bc_t = ac_t = bd_t = ad_t = 0.0
        ob_q = DataQuality.CANONICAL
        for book in OB_STATE.values():
            if book.quality != DataQuality.CANONICAL: ob_q = DataQuality.PARTIAL
            bc, ac, bd, ad = book.depth_within_pct(close)
            bc_t += bc; ac_t += ac; bd_t += bd; ad_t += ad

        def fv(val, q=DataQuality.CANONICAL):
            return FeatureValue(value=val, quality=q, timestamp_ms=now_ms)

        return FeatureSnapshot(
            sequence_id=seq_id,
            receive_timestamp_ms=now_ms,
            features={
                "price":      fv(close, kq),
                "quote_vol":  fv(KL_STATE.volume * close, kq),
                "rsi":        fv(KL_STATE.rsi, kq),
                "future_cvd": fv(AGG_STATE.session_cvd, AGG_STATE.quality),
                "spot_cvd":   fv(scvd, scvd_q),
                "funding_pct":fv(funding, mp_q),
                "basis":      fv(basis, mp_q),
                "oi_k":       fv(oi_k),
                "ls_ratio":   fv(ls_ratio),
                "fp_delta":   fv(AGG_STATE.fp_delta, AGG_STATE.quality),
                "fp_poc":     fv((KL_STATE.high + KL_STATE.low) / 2, kq),
                "long_liq":   fv(LIQ_STATE.long_usd, LIQ_STATE.quality),
                "short_liq":  fv(LIQ_STATE.short_usd, LIQ_STATE.quality),
                "bid_dollar": fv(bd_t, ob_q), "ask_dollar": fv(ad_t, ob_q),
                "bid_coin":   fv(bc_t, ob_q), "ask_coin":   fv(ac_t, ob_q),
                "whale_idx":  fv(whale),
                "taker_buy":  fv(tb), "taker_sell": fv(ts),
                "ema8":  fv(KL_STATE.live_ema(8),   kq),
                "ema21": fv(KL_STATE.live_ema(21),  kq),
                "ema50": fv(KL_STATE.live_ema(50),  kq),
                "ema200":fv(KL_STATE.live_ema(200), kq),
                "ema800":fv(KL_STATE.live_ema(800), kq),
                "atr14": fv(KL_STATE._atr14, kq),
                "atr100":fv(KL_STATE._atr100, kq),
            }
        )
    except Exception as e:
        return str(e)


# ─── Market Data Loop (Publisher) ─────────────────────────────────────────────
async def market_data_loop():
    while not KL_STATE.ready:
        await asyncio.sleep(0.5)
    seq_id = 1
    while True:
        snap = await compute_snapshot(seq_id)
        if isinstance(snap, FeatureSnapshot):
            if SNAPSHOT_BUS.full():
                SNAPSHOT_BUS.get_nowait()
            SNAPSHOT_BUS.put_nowait(snap)
            seq_id += 1
        else:
            print(f"[ERR] {snap}")
        await asyncio.sleep(2)


# ─── Formatters ───────────────────────────────────────────────────────────────
def _u(v):
    if v is None: return "N/A"
    a = abs(v)
    if a>=1e6: return f"${a/1e6:.3f}M"
    if a>=1e3: return f"${a/1e3:.2f}K"
    return f"${a:.2f}"

def _b(v):
    if v is None: return "N/A"
    a = abs(v)
    if a>=1e3: return f"{a/1e3:.2f}K"
    return f"{a:.4f}"

def R(n, label, val, q, note=""):
    qs = f"[{q.value}]" if q != DataQuality.CANONICAL else ""
    return f"  {n:>2}. {label:<14} | {val:<18} {qs:<11}| {note}"


# ─── Terminal Observer (Consumer) ─────────────────────────────────────────────
async def terminal_observer_loop():
    while True:
        snap = await SNAPSHOT_BUS.get()
        f = snap.features
        t = datetime.now().strftime("%H:%M:%S")
        print(f"\n[{t}] SEQ:{snap.sequence_id} " + "─"*60)
        print(R(" 1","ASSET",       "BTCUSDT",                              DataQuality.CANONICAL, "Binance Futures"))
        print(R(" 2","PRICE",       f"${f['price'].value:,.2f}",            f['price'].quality))
        print(R(" 3","VOLUME USDT", f"${f['quote_vol'].value:,.0f}",        f['quote_vol'].quality))
        print(R(" 4","RSI (14)",    f"{f['rsi'].value:.2f}" if f['rsi'].value is not None else "N/A", f['rsi'].quality, "Wilder incremental WS"))
        print(R(" 5","FUT CVD",     f"{f['future_cvd'].value:+.4f} BTC" if f['future_cvd'].value is not None else "N/A", f['future_cvd'].quality, "aggTrade session sum"))
        print(R(" 6","SPOT CVD",    f"{f['spot_cvd'].value/1e3:.3f}K" if f['spot_cvd'].value is not None else "N/A", f['spot_cvd'].quality))
        print(R(" 7","FUNDING %",   f"{f['funding_pct'].value:.6f}" if f['funding_pct'].value is not None else "N/A", f['funding_pct'].quality, "Premium Index Rate"))
        print(R(" 8","OPEN INT",    f"{f['oi_k'].value:.3f}K" if f['oi_k'].value is not None else "N/A", f['oi_k'].quality, "USDT+USDC+COIN-M"))
        print(R(" 9","LONG LIQ",    _u(f['long_liq'].value),                f['long_liq'].quality, "WebSocket stream"))
        print(R("10","SHORT LIQ",   _u(f['short_liq'].value),               f['short_liq'].quality, "WebSocket stream"))
        print(R("11","L/S RATIO",   f"{f['ls_ratio'].value:.4f}" if f['ls_ratio'].value is not None else "N/A", f['ls_ratio'].quality, "Global Account Ratio"))
        print(R("12","FP DELTA",    f"{f['fp_delta'].value:+.4f} BTC" if f['fp_delta'].value is not None else "N/A", f['fp_delta'].quality, "True aggTrade bid/ask"))
        print(R("13","FP POC",      f"{f['fp_poc'].value:,.2f}",            f['fp_poc'].quality, "(H+L)/2 cur bar"))
        print(R("14","BID DOLLAR",  _u(f['bid_dollar'].value),              f['bid_dollar'].quality, "±1% all books"))
        print(R("15","ASK DOLLAR",  _u(f['ask_dollar'].value),              f['ask_dollar'].quality, "±1% all books"))
        print(R("16","BID COIN",    _b(f['bid_coin'].value),                f['bid_coin'].quality, "±1% all books"))
        print(R("17","ASK COIN",    _b(f['ask_coin'].value),                f['ask_coin'].quality, "±1% all books"))
        print(R("18","WHALE IDX",   str(f['whale_idx'].value),              f['whale_idx'].quality, "Top Trader Ratios"))
        print(R("19","TAKER BUY",   _b(f['taker_buy'].value),               f['taker_buy'].quality, "All pairs partial-bar"))
        print(R("20","TAKER SELL",  _b(f['taker_sell'].value),              f['taker_sell'].quality, "All pairs partial-bar"))
        print(R("21","EMA 8",       f"{f['ema8'].value:,.2f}" if f['ema8'].value is not None else "N/A",   f['ema8'].quality,  "Live WS incremental"))
        print(R("22","EMA 21",      f"{f['ema21'].value:,.2f}" if f['ema21'].value is not None else "N/A", f['ema21'].quality, "Live WS incremental"))
        print(R("23","EMA 50",      f"{f['ema50'].value:,.2f}" if f['ema50'].value is not None else "N/A", f['ema50'].quality, "Live WS incremental"))
        print(R("24","EMA 200",     f"{f['ema200'].value:,.2f}" if f['ema200'].value is not None else "N/A",f['ema200'].quality,"Live WS incremental"))
        print(R("25","EMA 800",     f"{f['ema800'].value:,.2f}" if f['ema800'].value is not None else "N/A",f['ema800'].quality,"Live WS incremental"))
        print(R("26","ATR 14",      f"{f['atr14'].value:.4f}" if f['atr14'].value is not None else "N/A",  f['atr14'].quality))
        print(R("27","ATR 100",     f"{f['atr100'].value:.4f}" if f['atr100'].value is not None else "N/A",f['atr100'].quality))
        print(R("28","BASIS",       f"{f['basis'].value:+.2f}" if f['basis'].value is not None else "N/A", f['basis'].quality, "Mark Price - Index Price"))
        sys.stdout.flush()
        if "--once" in sys.argv: break


# ─── Entry Point ──────────────────────────────────────────────────────────────
async def run_live_comparison():
    global SNAPSHOT_BUS
    SNAPSHOT_BUS = asyncio.Queue(maxsize=1)

    print("="*80)
    print("  CANONICAL MARKET-DATA SERVICE v2 — 28 INDICATORS (8 WebSocket streams)")
    print("="*80)

    tasks = []
    if "--once" not in sys.argv:
        tasks += [
            asyncio.create_task(start_liq_stream()),
            asyncio.create_task(start_ob_stream("btcusdt")),
            asyncio.create_task(start_ob_stream("btcusdc")),
            asyncio.create_task(start_ob_stream("btcusd_perp")),
            asyncio.create_task(start_agg_trade_stream()),
            asyncio.create_task(start_spot_agg_stream()),
            asyncio.create_task(start_kline_stream()),
            asyncio.create_task(start_mark_price_stream()),
        ]
        print("[INIT] Seeding REST + connecting 8 WebSocket streams...")
        await asyncio.sleep(4)   # Let OB snapshots seed
    else:
        klines = await async_fetch("https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=15m&limit=1000", weight=5)
        await KL_STATE.seed_from_rest(klines)

    tasks += [
        asyncio.create_task(market_data_loop()),
        asyncio.create_task(terminal_observer_loop()),
    ]
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    try:
        asyncio.run(run_live_comparison())
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n[STOPPED] Service exited cleanly.")
