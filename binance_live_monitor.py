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
import os
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
os.system("") # Enable ANSI / VT100 escape sequences on Windows console


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

# ─── V3 Atomic Immutable Snapshots ───────────────────────────────────────────
@dataclass(frozen=True)
class OBSnapshot:
    quality: DataQuality
    ready: bool
    stream_type: str
    bids: Dict[float, float]
    asks: Dict[float, float]

@dataclass(frozen=True)
class LiqSnapshot:
    quality: DataQuality
    long_usd: float
    short_usd: float

@dataclass(frozen=True)
class AggTradeSnapshot:
    quality: DataQuality
    session_cvd: float
    fp_delta: float
    fp_poc: Optional[float]

@dataclass(frozen=True)
class SpotAggTradeSnapshot:
    quality: DataQuality
    session_cvd: float

@dataclass(frozen=True)
class KlineSnapshot:
    quality: DataQuality
    ready: bool
    close: float
    volume: float
    quote_volume: float
    volume_sma9: Optional[float]
    taker_buy: float
    taker_sell: float
    ema8: Optional[float]
    ema21: Optional[float]
    ema50: Optional[float]
    ema200: Optional[float]
    ema800: Optional[float]
    atr14: Optional[float]
    atr100: Optional[float]
    rsi: Optional[float]

@dataclass(frozen=True)
class MarkPriceSnapshot:
    quality: DataQuality
    mark_price: float
    index_price: float
    funding_rate: float

@dataclass(frozen=True)
class RestSnapshot:
    oi_k: Optional[float]
    ls_ratio: Optional[float]
    whale: str
    usdc_tb: float
    usdc_ts: float
    coinm_tb: float
    coinm_ts: float


# ─── Token Bucket Rate Limiter ────────────────────────────────────────────────
class TokenBucket:
    def __init__(self, capacity, fill_rate):
        self.capacity = capacity
        self.fill_rate = fill_rate
        self.tokens = capacity
        self.last_fill = time.monotonic()
        self.lock = asyncio.Lock()

    async def consume(self, tokens=1):
        """Acquire without ever sleeping while holding the shared limiter lock."""
        while True:
            async with self.lock:
                now = time.monotonic()
                self.tokens = min(
                    self.capacity, self.tokens + (now - self.last_fill) * self.fill_rate
                )
                self.last_fill = now
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return
                wait_seconds = (tokens - self.tokens) / self.fill_rate
            # Holding this lock during sleep serializes every REST caller.
            await asyncio.sleep(wait_seconds)


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
    """Live Orderbook depth tracking with proper Binance sequence bridge rules."""
    def __init__(self, symbol, stream_type):
        self.symbol = symbol
        self.stream_type = stream_type  # "f" or "d"
        self.bids = {}
        self.asks = {}
        self.last_update_id = 0
        self.ready = False
        self.quality = DataQuality.UNAVAILABLE
        self._buffer = []
        self._lock = asyncio.Lock()

    async def sync_snapshot(self):
        base = "https://fapi.binance.com/fapi/v1/depth" if self.stream_type == "f" else "https://dapi.binance.com/dapi/v1/depth"
        async with self._lock:
            self.quality = DataQuality.RECOVERING
            self.ready = False
        
        url = f"{base}?symbol={self.symbol.upper()}&limit=1000"
        weight = 20 if self.stream_type == "f" else 10
        data = await async_fetch(url, weight=weight)
        
        async with self._lock:
            self.last_update_id = data["lastUpdateId"]
            self.bids = {float(p): float(q) for p, q in data["bids"] if float(q) > 0}
            self.asks = {float(p): float(q) for p, q in data["asks"] if float(q) > 0}

            replayed = 0
            for ev in self._buffer:
                u = ev["u"]
                U = ev.get("U", 0)
                pu = ev.get("pu", 0)
                if u <= self.last_update_id:
                    continue
                if (U <= self.last_update_id + 1 <= u) or (pu == self.last_update_id):
                    self._apply_updates(ev)
                    replayed += 1

            self._buffer.clear()
            self.ready = True
            self.quality = DataQuality.CANONICAL

    def _apply_updates(self, ev):
        for px_s, qty_s in ev.get("b", []):
            px, qty = float(px_s), float(qty_s)
            if qty == 0: self.bids.pop(px, None)
            else: self.bids[px] = qty
        for px_s, qty_s in ev.get("a", []):
            px, qty = float(px_s), float(qty_s)
            if qty == 0: self.asks.pop(px, None)
            else: self.asks[px] = qty
        self.last_update_id = ev["u"]

    async def handle_event(self, ev):
        async with self._lock:
            if not self.ready:
                self._buffer.append(ev)
                if len(self._buffer) > 1000:
                    self._buffer.pop(0)
            else:
                u, pu, U = ev["u"], ev["pu"], ev["U"]
                if u <= self.last_update_id:
                    return
                if pu != self.last_update_id:
                    # Bridge rule for first stream event if buffer was empty
                    if U <= self.last_update_id + 1 and u >= self.last_update_id + 1:
                        self._apply_updates(ev)
                        return
                    self.quality = DataQuality.STALE
                    self.ready = False
                    return
                
                self._apply_updates(ev)

    @property
    def snapshot(self) -> OBSnapshot:
        return OBSnapshot(
            quality=self.quality,
            ready=self.ready,
            stream_type=self.stream_type,
            bids=self.bids.copy(),
            asks=self.asks.copy()
        )

# ─── Orderbook Utilities ──────────────────────────────────────────────────────
def ob_depth_within_pct(snap: OBSnapshot, price: float, pct: float=0.01):
    if not snap.ready or not price:
        return 0.0, 0.0, 0.0, 0.0
    lo, hi = price * (1 - pct), price * (1 + pct)
    bc = ac = bd = ad = 0.0
    coinm = snap.stream_type == "d"
    for px, qty in snap.bids.items():
        if px >= lo:
            q = (qty * 100 / px) if coinm else qty
            bc += q; bd += (qty * 100) if coinm else (px * q)
    for px, qty in snap.asks.items():
        if px <= hi:
            q = (qty * 100 / px) if coinm else qty
            ac += q; ad += (qty * 100) if coinm else (px * q)
    return bc, ac, bd, ad


# ─── Liquidation State ────────────────────────────────────────────────────────
class LiquidationState:
    """Per-candle liq volumes. Resets at every 15m candle boundary (IST/UTC :00, :15, :30, :45)."""
    def __init__(self):
        self.current_candle_ts = 0
        self.long_usd = 0.0
        self.short_usd = 0.0
        self.quality = DataQuality.CANONICAL

    def apply(self, ts_ms, side, notional):
        cts = (ts_ms // 900000) * 900000
        if cts != self.current_candle_ts:
            self.current_candle_ts = cts
            self.long_usd = self.short_usd = 0.0
        if side == "SELL": self.long_usd += notional
        elif side == "BUY": self.short_usd += notional

    @property
    def snapshot(self) -> LiqSnapshot:
        now_cts = (int(time.time() * 1000) // 900000) * 900000
        if self.current_candle_ts != 0 and now_cts != self.current_candle_ts:
            return LiqSnapshot(
                quality=self.quality,
                long_usd=0.0,
                short_usd=0.0
            )
        return LiqSnapshot(
            quality=self.quality,
            long_usd=self.long_usd,
            short_usd=self.short_usd
        )


# ─── Per-bar Volume-at-Price (Footprint POC) ─────────────────────────────────
class VolumeAtPrice:
    """Bounded 15m volume profile keyed by integer price ticks."""
    def __init__(self, tick_size: float = 0.1):
        self.tick_size = tick_size
        self.bar_open_ms = 0
        self._volume_by_tick: Dict[int, float] = {}

    def add(self, bar_open_ms: int, price: float, quantity: float) -> None:
        if bar_open_ms != self.bar_open_ms:
            self.bar_open_ms = bar_open_ms
            self._volume_by_tick.clear()
        tick = round(price / self.tick_size)
        self._volume_by_tick[tick] = self._volume_by_tick.get(tick, 0.0) + quantity

    @property
    def poc(self) -> Optional[float]:
        now_cts = (int(time.time() * 1000) // 900000) * 900000
        if self.bar_open_ms != 0 and now_cts != self.bar_open_ms:
            return None
        if not self._volume_by_tick:
            return None
        tick = max(self._volume_by_tick, key=self._volume_by_tick.__getitem__)
        return tick * self.tick_size


# ─── AggTrade State (True FP Delta + Session CVD) ────────────────────────────
class AggTradeState:
    """
    True Footprint Delta and running session CVD from aggTrade ticks.
    """
    def __init__(self):
        self.current_candle_ts = 0
        self.candle_buy_btc = 0.0
        self.candle_sell_btc = 0.0
        self.session_cvd = 0.0       # BTC, running since service start
        self.quality = DataQuality.PARTIAL
        self.profile = VolumeAtPrice()
        self.last_aggregate_trade_id = None
        self._lock = asyncio.Lock()

    async def apply(self, ts_ms, price_str, qty_str, is_buyer_maker, agg_id=None):
        cts = (ts_ms // 900000) * 900000
        qty = float(qty_str)
        price = float(price_str)
        if KL_STATE.ready:
            await KL_STATE.apply_trade_tick(price, qty)
        async with self._lock:
            if self.current_candle_ts == 0:
                self.current_candle_ts = cts
            elif cts != self.current_candle_ts:
                self.current_candle_ts = cts
                self.candle_buy_btc = self.candle_sell_btc = 0.0
            
            self.quality = DataQuality.CANONICAL
            self.profile.add(cts, price, qty)
            if is_buyer_maker:
                self.candle_sell_btc += qty
                self.session_cvd -= qty
            else:
                self.candle_buy_btc += qty
                self.session_cvd += qty
            if agg_id:
                self.last_aggregate_trade_id = agg_id

    @property
    def fp_delta(self):
        now_cts = (int(time.time() * 1000) // 900000) * 900000
        if self.current_candle_ts != 0 and now_cts != self.current_candle_ts:
            return 0.0
        return self.candle_buy_btc - self.candle_sell_btc

    @property
    def snapshot(self) -> AggTradeSnapshot:
        return AggTradeSnapshot(
            quality=self.quality,
            session_cvd=self.session_cvd,
            fp_delta=self.fp_delta,
            fp_poc=self.profile.poc
        )


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
        self.quote_volume = 0.0
        self.volume_sma9 = None
        self._past_q_vols = []

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
        q_vols = [float(k[7]) for k in klines]
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
            self._past_q_vols = q_vols[:-1]

            self.open   = float(lf[1])
            self.high   = float(lf[2])
            self.low    = float(lf[3])
            self.close  = float(lf[4])
            self.volume = float(lf[5])
            self.quote_volume = float(lf[7])
            self.volume_sma9 = sum(q_vols[-9:]) / 9.0 if len(q_vols) >= 9 else self.quote_volume
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
            self.quote_volume = float(k.get("q", self.volume * self.close))
            self.taker_buy  = float(k.get("V", 0))
            self.taker_sell = self.volume - self.taker_buy

            if is_closed:
                c = self.close
                self._past_q_vols.append(self.quote_volume)
                if len(self._past_q_vols) > 50:
                    self._past_q_vols.pop(0)
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
            
            self.volume_sma9 = (sum(self._past_q_vols[-8:]) + self.quote_volume) / 9.0 if len(self._past_q_vols) >= 8 else self.quote_volume
            self.quality = DataQuality.CANONICAL

    async def apply_trade_tick(self, price: float, qty: float):
        """Ultra-fast sub-millisecond trade tick update for live price and volume."""
        async with self._lock:
            self.close = price
            if price > self.high: self.high = price
            if self.low == 0.0 or price < self.low: self.low = price
            self.volume += qty
            self.quote_volume += price * qty
            if len(self._past_q_vols) >= 8:
                self.volume_sma9 = (sum(self._past_q_vols[-8:]) + self.quote_volume) / 9.0

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

    @property
    def snapshot(self) -> KlineSnapshot:
        return KlineSnapshot(
            quality=self.quality,
            ready=self.ready,
            close=self.close,
            volume=self.volume,
            quote_volume=self.quote_volume,
            volume_sma9=self.volume_sma9,
            taker_buy=self.taker_buy,
            taker_sell=self.taker_sell,
            ema8=self.live_ema(8),
            ema21=self.live_ema(21),
            ema50=self.live_ema(50),
            ema200=self.live_ema(200),
            ema800=self.live_ema(800),
            atr14=self._atr14,
            atr100=self._atr100,
            rsi=self.rsi
        )


# ─── Spot AggTrade State (Running Spot CVD) ──────────────────────────────────
class SpotAggTradeState:
    """
    Running session CVD from spot BTCUSDT aggTrade stream.
    No candle reset — accumulates from service start.
    """
    def __init__(self):
        self.session_cvd = 0.0   # BTC net (buy - sell) since session start
        self.quality = DataQuality.PARTIAL
        self.last_aggregate_trade_id = None
        self._lock = asyncio.Lock()
        self._first_trade_seen = False

    async def apply(self, qty_str, is_buyer_maker, agg_id=None):
        async with self._lock:
            if not self._first_trade_seen:
                self._first_trade_seen = True
                self.quality = DataQuality.CANONICAL
            qty = float(qty_str)
            if is_buyer_maker:
                self.session_cvd -= qty
            else:
                self.session_cvd += qty
            if agg_id:
                self.last_aggregate_trade_id = agg_id

    @property
    def snapshot(self) -> SpotAggTradeSnapshot:
        return SpotAggTradeSnapshot(
            quality=self.quality,
            session_cvd=self.session_cvd
        )


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
            if "p" in d:
                self.mark_price = float(d["p"])
            if "i" in d:
                self.index_price = float(d["i"])
            if "r" in d and d["r"] is not None:
                self.funding_rate = float(d["r"]) * 100.0
            self.quality = DataQuality.CANONICAL

    @property
    def snapshot(self) -> MarkPriceSnapshot:
        return MarkPriceSnapshot(
            quality=self.quality,
            mark_price=self.mark_price,
            index_price=self.index_price,
            funding_rate=self.funding_rate
        )


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
LATEST_SNAPSHOT: Optional[FeatureSnapshot] = None
TERMINAL_PRINT_INTERVAL_SEC = 2


# ─── Stream Supervisor ────────────────────────────────────────────────────────
async def stream_supervisor(url, handler, name, on_connect=None):
    backoff = 1.0
    while True:
        try:
            async with websockets.connect(url, max_size=10*1024*1024) as ws:
                backoff = 1.0
                if on_connect:
                    await on_connect()
                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        await handler(json.loads(raw))
                    except asyncio.TimeoutError:
                        continue
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[WS ERR] {name}: {e}")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)


# ─── Stream Handlers & Starters ───────────────────────────────────────────────
async def _liq_handler(data):
    o = data.get("data", {}).get("o", {}) if "data" in data else data.get("o", {})
    if o:
        LIQ_STATE.apply(
            ts_ms=int(o.get("T", time.time()*1000)),
            side=o.get("S"),
            notional=float(o.get("q", 0)) * float(o.get("p", 0))
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

async def _retry_bootstrap(name, operation):
    """Retry REST bootstrap without letting one blocked endpoint kill the service."""
    delay = 1.0
    while True:
        try:
            return await operation()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[BOOTSTRAP ERR] {name}: {type(exc).__name__}: {exc}; retrying in {delay:.0f}s")
            await asyncio.sleep(delay)
            delay = min(delay * 2.0, 30.0)


async def start_ob_stream(symbol):
    book = OB_STATE[symbol]
    await _retry_bootstrap(f"OB_{symbol}", book.sync_snapshot)
    base = "wss://fstream.binance.com/ws" if book.stream_type == "f" else "wss://dstream.binance.com/ws"
    await stream_supervisor(f"{base}/{symbol}@depth", lambda d: _ob_handler(book, d), f"OB_{symbol}")


async def _agg_handler(data):
    d = data.get("data", data)
    if "p" in d and "q" in d:
        await AGG_STATE.apply(
            ts_ms=int(d.get("T", time.time()*1000)),
            price_str=d.get("p", "0"),
            qty_str=d.get("q","0"),
            is_buyer_maker=d.get("m", False),
            agg_id=d.get("a")
        )

async def _recover_fut_agg():
    last_id = AGG_STATE.last_aggregate_trade_id
    try:
        if AGG_STATE.session_cvd == 0.0:
            fk_data = await async_fetch("https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=15m&limit=850", weight=5)
            if isinstance(fk_data, list):
                AGG_STATE.session_cvd = sum((2.0 * float(k[9]) - float(k[5])) for k in fk_data)
        if last_id:
            url = f"https://fapi.binance.com/fapi/v1/aggTrades?symbol=BTCUSDT&fromId={last_id+1}&limit=1000"
        else:
            url = "https://fapi.binance.com/fapi/v1/aggTrades?symbol=BTCUSDT&limit=1000"
        trades = await async_fetch(url, weight=5)
        if isinstance(trades, list):
            for t in trades:
                await AGG_STATE.apply(
                    ts_ms=int(t["T"]), price_str=t["p"], qty_str=t["q"],
                    is_buyer_maker=t["m"], agg_id=t["a"]
                )
    except Exception:
        pass

async def start_agg_trade_stream():
    """Futures aggTrade: True FP Delta + running futures session CVD."""
    await stream_supervisor(
        "wss://fstream.binance.com/ws/btcusdt@aggTrade",
        _agg_handler, "FutAggTrade",
        on_connect=_recover_fut_agg
    )


async def _spot_agg_handler(data):
    d = data.get("data", data)
    if "q" in d:
        await SPOT_AGG.apply(
            qty_str=d.get("q", "0"),
            is_buyer_maker=d.get("m", False),
            agg_id=d.get("a")
        )

async def _recover_spot_agg():
    last_id = SPOT_AGG.last_aggregate_trade_id
    try:
        if SPOT_AGG.session_cvd == 0.0:
            sk_data = await async_fetch("https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=500", weight=2)
            if isinstance(sk_data, list):
                SPOT_AGG.session_cvd = sum((2.0 * float(k[9]) - float(k[5])) for k in sk_data)
        if last_id:
            url = f"https://api.binance.com/api/v3/aggTrades?symbol=BTCUSDT&fromId={last_id+1}&limit=1000"
        else:
            url = "https://api.binance.com/api/v3/aggTrades?symbol=BTCUSDT&limit=1000"
        trades = await async_fetch(url, weight=1)
        if isinstance(trades, list):
            for t in trades:
                await SPOT_AGG.apply(qty_str=t["q"], is_buyer_maker=t["m"], agg_id=t["a"])
    except Exception:
        pass

async def start_spot_agg_stream():
    """Spot aggTrade: running spot session CVD — replaces 500-bar REST poll."""
    await stream_supervisor(
        "wss://stream.binance.com:9443/ws/btcusdt@aggTrade",
        _spot_agg_handler, "SpotAggTrade",
        on_connect=_recover_spot_agg
    )


async def _kline_handler(data):
    d = data.get("data", data)
    k = d.get("k", d)
    if isinstance(k, dict) and "c" in k:
        await KL_STATE.apply_kline_event(k)

async def start_kline_stream():
    """Seed from REST (1500 bars for exact EMA 800 convergence), then maintain from kline_15m WebSocket."""
    async def seed():
        k1 = await async_fetch(
            "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=15m&limit=1000", weight=5
        )
        if k1:
            first_open_time = int(k1[0][0])
            k0 = await async_fetch(
                f"https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=15m&endTime={first_open_time - 1}&limit=500", weight=5
            )
            klines = (k0 if isinstance(k0, list) else []) + k1
        else:
            klines = k1
        await KL_STATE.seed_from_rest(klines)
    await _retry_bootstrap("Kline15m", seed)
    await stream_supervisor(
        "wss://fstream.binance.com/ws/btcusdt@kline_15m",
        _kline_handler, "Kline15m"
    )

async def _bootstrap_mark_price():
    try:
        d = await async_fetch("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT", weight=1)
        if isinstance(d, dict):
            await MARK_PRICE.apply({
                "p": d.get("markPrice"),
                "i": d.get("indexPrice"),
                "r": d.get("lastFundingRate")
            })
    except Exception:
        pass

async def _mark_price_handler(data):
    d = data.get("data", data)
    await MARK_PRICE.apply(d)

async def start_mark_price_stream():
    """Live Mark Price and Funding Rate (replaces premiumIndex polling)."""
    await stream_supervisor(
        "wss://fstream.binance.com/ws/btcusdt@markPrice@1s",
        _mark_price_handler, "MarkPrice",
        on_connect=_bootstrap_mark_price
    )

# ─── Decoupled REST Pollers ───────────────────────────────────────────────────
class RestCache:
    def __init__(self):
        self.oi_k = None
        self.ls_ratio = None
        self.whale = "N/A"
        self.usdc_tb = 0.0
        self.usdc_ts = 0.0
        self.coinm_tb = 0.0
        self.coinm_ts = 0.0

    @property
    def snapshot(self) -> RestSnapshot:
        return RestSnapshot(
            oi_k=self.oi_k,
            ls_ratio=self.ls_ratio,
            whale=self.whale,
            usdc_tb=self.usdc_tb,
            usdc_ts=self.usdc_ts,
            coinm_tb=self.coinm_tb,
            coinm_ts=self.coinm_ts
        )

REST_CACHE = RestCache()

async def poll_oi_loop():
    while True:
        try:
            close = KL_STATE.close
            oi_t = float((await async_fetch("https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT", weight=1)).get("openInterest", 0))
            oi_c = float((await async_fetch("https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDC", weight=1)).get("openInterest", 0))
            coinm_raw = float((await async_fetch("https://dapi.binance.com/dapi/v1/openInterest?symbol=BTCUSD_PERP", weight=1)).get("openInterest", 0))
            coinm_btc = (coinm_raw * 100.0) / close if close and close > 0 else 0.0
            stable_k = (oi_t + oi_c) / 1e3
            REST_CACHE.oi_k = f"{stable_k:.3f}K"
        except Exception:
            pass
        await asyncio.sleep(3)

async def poll_ratios_loop():
    while True:
        try:
            ls_d = await async_fetch("https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol=BTCUSDT&period=15m&limit=1", weight=2)
            if ls_d: REST_CACHE.ls_ratio = float(ls_d[0]["longShortRatio"])
            
            ta = await async_fetch("https://fapi.binance.com/futures/data/topLongShortAccountRatio?symbol=BTCUSDT&period=15m&limit=1", weight=2)
            if ta:
                whale_val = float(ta[0]['longShortRatio']) * 100.0
                REST_CACHE.whale = f"{whale_val:.4f}"
        except Exception:
            pass
        await asyncio.sleep(15)

async def poll_taker_flow_loop():
    while True:
        try:
            kuc = await async_fetch("https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDC&interval=15m&limit=1", weight=1)
            REST_CACHE.usdc_tb = float(kuc[-1][9])
            REST_CACHE.usdc_ts = float(kuc[-1][5]) - float(kuc[-1][9])
        except Exception: pass
        try:
            kcm = await async_fetch("https://dapi.binance.com/dapi/v1/klines?symbol=BTCUSD_PERP&interval=15m&limit=1", weight=1)
            REST_CACHE.coinm_tb = float(kcm[-1][10])
            REST_CACHE.coinm_ts = float(kcm[-1][7]) - float(kcm[-1][10])
        except Exception: pass
        await asyncio.sleep(10)


# ─── Snapshot Computer ────────────────────────────────────────────────────────
async def compute_snapshot(seq_id):
    try:
        now_ms = int(time.time() * 1000)
        
        # 1. Acquire Immutable Views
        kl_snap = KL_STATE.snapshot
        agg_snap = AGG_STATE.snapshot
        spot_agg_snap = SPOT_AGG.snapshot
        mp_snap = MARK_PRICE.snapshot
        liq_snap = LIQ_STATE.snapshot
        rest_snap = REST_CACHE.snapshot
        ob_snaps = [book.snapshot for book in OB_STATE.values()]

        # 2. Derive Features from Immutable Views
        kq = kl_snap.quality
        close = kl_snap.close

        tb = kl_snap.taker_buy + rest_snap.usdc_tb + rest_snap.coinm_tb
        ts = kl_snap.taker_sell + rest_snap.usdc_ts + rest_snap.coinm_ts

        scvd = spot_agg_snap.session_cvd
        scvd_q = spot_agg_snap.quality

        funding = mp_snap.funding_rate
        basis = mp_snap.mark_price - mp_snap.index_price if mp_snap.index_price > 0 else 0.0
        mp_q = mp_snap.quality

        oi_k = rest_snap.oi_k
        ls_ratio = rest_snap.ls_ratio
        whale = rest_snap.whale

        bc_t = ac_t = bd_t = ad_t = 0.0
        ob_q = DataQuality.CANONICAL
        for ob in ob_snaps:
            if ob.quality != DataQuality.CANONICAL: ob_q = DataQuality.PARTIAL
            bc, ac, bd, ad = ob_depth_within_pct(ob, close)
            bc_t += bc; ac_t += ac; bd_t += bd; ad_t += ad

        def fv(val, q=DataQuality.CANONICAL):
            return FeatureValue(value=val, quality=q, timestamp_ms=now_ms)

        return FeatureSnapshot(
            sequence_id=seq_id,
            receive_timestamp_ms=now_ms,
            features={
                "price":      fv(close, kq),
                "quote_vol":  fv(kl_snap.quote_volume if kl_snap.quote_volume else kl_snap.volume * close, kq),
                "volume_sma9":fv(kl_snap.volume_sma9, kq),
                "rsi":        fv(kl_snap.rsi, kq),
                "future_cvd": fv(agg_snap.session_cvd, agg_snap.quality),
                "spot_cvd":   fv(scvd, scvd_q),
                "funding_pct":fv(funding, mp_q),
                "basis":      fv(basis, mp_q),
                "oi_k":       fv(oi_k),
                "ls_ratio":   fv(ls_ratio),
                "fp_delta":   fv(agg_snap.fp_delta, agg_snap.quality),
                "fp_poc":     fv(agg_snap.fp_poc, agg_snap.quality),
                "long_liq":   fv(liq_snap.long_usd, liq_snap.quality),
                "short_liq":  fv(liq_snap.short_usd, liq_snap.quality),
                "bid_dollar": fv(bd_t, ob_q), "ask_dollar": fv(ad_t, ob_q),
                "bid_coin":   fv(bc_t, ob_q), "ask_coin":   fv(ac_t, ob_q),
                "whale_idx":  fv(whale),
                "taker_buy":  fv(tb), "taker_sell": fv(ts),
                "ema8":  fv(kl_snap.ema8,   kq),
                "ema21": fv(kl_snap.ema21,  kq),
                "ema50": fv(kl_snap.ema50,  kq),
                "ema200":fv(kl_snap.ema200, kq),
                "ema800":fv(kl_snap.ema800, kq),
                "atr14": fv(kl_snap.atr14, kq),
                "atr100":fv(kl_snap.atr100, kq),
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
            global LATEST_SNAPSHOT
            LATEST_SNAPSHOT = snap
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
    return f"  {n:>2}. {label:<14} | {val:<26} {qs:<11}| {note}"


# ─── Terminal Observer (Consumer) ─────────────────────────────────────────────
async def terminal_observer_loop():
    """Human observer only; execution consumers can continue using SNAPSHOT_BUS."""
    is_first = True
    is_interactive = sys.stdout.isatty() and ("--once" not in sys.argv)
    
    while True:
        await asyncio.sleep(TERMINAL_PRINT_INTERVAL_SEC)
        snap = LATEST_SNAPSHOT
        if snap is None:
            if not is_interactive:
                print("[WAITING] No canonical snapshot has been published yet.")
            continue
        f = snap.features
        t = datetime.now().strftime("%H:%M:%S")
        
        lines = []
        lines.append("="*80)
        lines.append("  CANONICAL MARKET-DATA SERVICE v2 — 28 INDICATORS (8 WebSocket streams)")
        lines.append("="*80)
        lines.append(f"[{t}] SEQ:{snap.sequence_id} " + "─"*60)
        lines.append(R(" 1","ASSET",       "BTCUSDT",                              DataQuality.CANONICAL, "Binance Futures"))
        lines.append(R(" 2","PRICE",       f"${f['price'].value:,.1f}",            f['price'].quality))
        bar_vol = f"${f['quote_vol'].value/1e6:.3f}M" if f['quote_vol'].value else "$0.000M"
        sma9 = f"{f['volume_sma9'].value/1e6:.2f}M" if f['volume_sma9'].value else "N/A"
        vol_str = f"{bar_vol} (SMA9:{sma9})"
        lines.append(R(" 3","VOLUME",      vol_str,                                f['quote_vol'].quality, "15m Bar Vol (SMA9)"))
        lines.append(R(" 4","RSI (14)",    f"{f['rsi'].value:.2f}" if f['rsi'].value is not None else "N/A", f['rsi'].quality, "Wilder RSI"))
        lines.append(R(" 5","FUT CVD",     f"{f['future_cvd'].value/1e3:+.3f}K" if f['future_cvd'].value is not None else "N/A", f['future_cvd'].quality, "Aggregated Futures CVD"))
        lines.append(R(" 6","SPOT CVD",    f"{f['spot_cvd'].value/1e3:+.3f}K" if f['spot_cvd'].value is not None else "N/A", f['spot_cvd'].quality, "Aggregated Spot CVD"))
        lines.append(R(" 7","FUNDING %",   f"{f['funding_pct'].value:.6f}" if f['funding_pct'].value is not None else "N/A", f['funding_pct'].quality, "OI-Weighted Rate"))
        lines.append(R(" 8","OPEN INT",    str(f['oi_k'].value) if f['oi_k'].value is not None else "N/A", f['oi_k'].quality, "STABLECOIN-margined"))
        lines.append(R(" 9","LONG LIQ",    _u(f['long_liq'].value),                f['long_liq'].quality, "Symbol Liquidations Long"))
        lines.append(R("10","SHORT LIQ",   _u(f['short_liq'].value),               f['short_liq'].quality, "Symbol Liquidations Short"))
        lines.append(R("11","L/S RATIO",   f"{f['ls_ratio'].value:.4f}" if f['ls_ratio'].value is not None else "N/A", f['ls_ratio'].quality, "Accounts L/S Ratio"))
        lines.append(R("12","FP DELTA",    f"{f['fp_delta'].value:+.4f} BTC" if f['fp_delta'].value is not None else "N/A", f['fp_delta'].quality, "Footprint Delta"))
        lines.append(R("13","FP POC",      f"{f['fp_poc'].value:,.1f}" if f['fp_poc'].value is not None else "N/A", f['fp_poc'].quality, "Volume-At-Price POC"))
        lines.append(R("14","BID DOLLAR",  _u(f['bid_dollar'].value),              f['bid_dollar'].quality, "±1% Futures Depth"))
        lines.append(R("15","ASK DOLLAR",  _u(f['ask_dollar'].value),              f['ask_dollar'].quality, "±1% Futures Depth"))
        lines.append(R("16","BID COIN",    _b(f['bid_coin'].value),                f['bid_coin'].quality, "±1% Futures Depth"))
        lines.append(R("17","ASK COIN",    _b(f['ask_coin'].value),                f['ask_coin'].quality, "±1% Futures Depth"))
        lines.append(R("18","WHALE IDX",   str(f['whale_idx'].value),              f['whale_idx'].quality, "Whale Index (Top Trader)"))
        lines.append(R("19","TAKER BUY",   _b(f['taker_buy'].value),               f['taker_buy'].quality, "Taker Buy Volume"))
        lines.append(R("20","TAKER SELL",  _b(f['taker_sell'].value),              f['taker_sell'].quality, "Taker Sell Volume"))
        lines.append(R("21","EMA 8",       f"{f['ema8'].value:,.1f}" if f['ema8'].value is not None else "N/A",   f['ema8'].quality,  "EMA 8 close"))
        lines.append(R("22","EMA 21",      f"{f['ema21'].value:,.1f}" if f['ema21'].value is not None else "N/A", f['ema21'].quality, "EMA 21 close"))
        lines.append(R("23","EMA 50",      f"{f['ema50'].value:,.1f}" if f['ema50'].value is not None else "N/A", f['ema50'].quality, "EMA 50 close"))
        lines.append(R("24","EMA 200",     f"{f['ema200'].value:,.1f}" if f['ema200'].value is not None else "N/A",f['ema200'].quality,"EMA 200 close"))
        lines.append(R("25","EMA 800",     f"{f['ema800'].value:,.1f}" if f['ema800'].value is not None else "N/A",f['ema800'].quality,"EMA 800 close"))
        lines.append(R("26","ATR 14",      f"{f['atr14'].value:.1f}" if f['atr14'].value is not None else "N/A",  f['atr14'].quality, "ATR 14"))
        lines.append(R("27","ATR 100",     f"{f['atr100'].value:.1f}" if f['atr100'].value is not None else "N/A",f['atr100'].quality, "ATR 100"))
        lines.append(R("28","BASIS",       f"{f['basis'].value:+.2f}" if f['basis'].value is not None else "N/A", f['basis'].quality, "Mark - Index Price"))
        
        if is_interactive:
            prefix = "\033[2J\033[H" if is_first else "\033[H"
            is_first = False
            buf = prefix + "\n".join(line + "\033[K" for line in lines) + "\n"
            sys.stdout.write(buf)
        else:
            sys.stdout.write("\n" + "\n".join(lines) + "\n")
        sys.stdout.flush()
        if "--once" in sys.argv: break


# ─── Entry Point ──────────────────────────────────────────────────────────────
async def run_live_comparison():
    global SNAPSHOT_BUS
    SNAPSHOT_BUS = asyncio.Queue(maxsize=1)

    tasks = []
    if "--once" not in sys.argv:
        print("[INIT] Seeding REST + connecting 8 WebSocket streams...")
        tasks += [
            asyncio.create_task(start_liq_stream()),
            asyncio.create_task(start_ob_stream("btcusdt")),
            asyncio.create_task(start_ob_stream("btcusdc")),
            asyncio.create_task(start_ob_stream("btcusd_perp")),
            asyncio.create_task(start_agg_trade_stream()),
            asyncio.create_task(start_spot_agg_stream()),
            asyncio.create_task(start_kline_stream()),
            asyncio.create_task(start_mark_price_stream()),
            asyncio.create_task(poll_oi_loop()),
            asyncio.create_task(poll_ratios_loop()),
            asyncio.create_task(poll_taker_flow_loop()),
        ]
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
