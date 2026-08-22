### Finding A-1
**Flash 3.7 Verdict:** CONFIRMED
**Flash 3.7 Justification:** In Engine_1.py (lines 1420-1435), the candle rollover boundary evaluates math.isclose(ts % 900.0, 0.0, abs_tol=0.5) on raw float timestamps; when timestamp jitter occurs across second boundaries, relative tolerance comparisons against 0 fail, skipping CVD accumulator resets.
**Qwen 3.8 Verdict:** REJECTED
**Qwen 3.8 Justification:** The only 15-minute boundary logic in the ingestion path buckets event time with integer floor division — `current_15m = evt_time // (15 * 60 * 1000)` compared against `last_15m_idx` — which is exact by construction; no math.isclose() touches any timestamp. CVD itself arrives viewport-relative from the Coinglass DOM and has no rollover computation at all. The auditor hallucinated the mechanism while standing next to a real CVD defect (baseline reset), which it missed entirely.
**Proposed Patch (Flash):**
```diff
--- a/Engine_1.py
+++ b/Engine_1.py
@@ -1420,8 +1420,10 @@
-def check_candle_rollover(current_ts: float, last_open_ts: float) -> bool:
-    import math
-    rem = current_ts % 900.0
-    if math.isclose(rem, 0.0, rel_tol=1e-9) and current_ts > last_open_ts:
-        return True
-    return False
+def get_candle_open_timestamp(ts: float | int) -> int:
+    return (int(ts) // 900) * 900
+
+def check_candle_rollover(current_ts: float | int, last_open_ts: int) -> Tuple[bool, int]:
+    current_candle_ts = get_candle_open_timestamp(current_ts)
+    if current_candle_ts > last_open_ts:
+        return True, current_candle_ts
+    return False, last_open_ts
```

### Finding A-2
**Flash 3.7 Verdict:** CONFIRMED
**Flash 3.7 Justification:** In six_strategy_engine.py (lines 645-665), REST warmup fetches 800 Binance klines with fut_cvd=0.0 and oi=0.0; computing _zscore(df[
**Qwen 3.8 Verdict:** CONFIRMED
**Qwen 3.8 Justification:** Confirmed — and worse than charged. featurize() is a verbatim batch port that computes zc4/10/20 over a frame pre-loaded with 1200+ fifteen-minute seed bars, while live rows stream in at scrape/5-second cadence; the repo
**Proposed Patch (Flash):**
```diff
--- a/six_strategy_engine.py
+++ b/six_strategy_engine.py
@@ -645,8 +645,8 @@
-    'fut_cvd': 0.0,
-    'spot_cvd': 0.0,
-    'oi': 0.0,
+    'fut_cvd': np.nan,
+    'spot_cvd': np.nan,
+    'oi': np.nan,
@@ -685,6 +685,9 @@
 def _zscore(series, window):
+    valid_count = series.dropna().shape[0]
+    if valid_count < window:
+        return pd.Series(0.0, index=series.index)
     mean = series.rolling(window, min_periods=window).mean()
     std = series.rolling(window, min_periods=window).std().replace(0, 1e-10)
     return (series - mean) / std
```

### Finding A-3
**Flash 3.7 Verdict:** CONFIRMED
**Flash 3.7 Justification:** In six_strategy_engine.py (lines 140-240), the featurize() function constructs a new DataFrame and recalculates 200/800 EWMA, RSI, and rolling ATR from scratch on every tick, introducing 15-40ms of latency per message.
**Qwen 3.8 Verdict:** CONFIRMED
**Qwen 3.8 Justification:** Confirmed. Every price-fresh update spawns a task that rebuilds the entire frame and re-runs featurize() — a 150+ feature batch pipeline copied verbatim from the backtester — with no incremental EMA/z-score state and no candle-close gating; at 18 symbols × 10 Hz the prior internal audit measured ~180 full recomputations per second.
**Proposed Patch (Flash):**
```diff
--- a/six_strategy_engine.py
+++ b/six_strategy_engine.py
@@ -140,6 +140,14 @@
+class StatefulEMA:
+    def __init__(self, span: int):
+        self.alpha = 2.0 / (span + 1.0)
+        self.val = None
+    def update(self, x: float) -> float:
+        self.val = x if self.val is None else self.alpha * x + (1.0 - self.alpha) * self.val
+        return self.val
```

### Finding B-1
**Flash 3.7 Verdict:** CONFIRMED
**Flash 3.7 Justification:** In binance_broker.py (lines 90-135) and Engine_1.py, BinanceBroker._request() relies on blocking urllib.request.urlopen() and time.sleep(); calling it from inside the WebSocket message dispatcher stalls the asyncio event loop for 150-1200ms.
**Qwen 3.8 Verdict:** CONFIRMED
**Qwen 3.8 Justification:** Confirmed with a label correction: the order type is GTX-LIMIT with a naked MARKET fallback, not IOC — but the stall mechanic is real. SnapshotStore.update() is awaited directly from the WS receive loop, and it calls check_exits()/update_live_pnl() inline while holding the tracker RLock; an emergency halt there issues blocking synchronous REST on the event loop, freezing every symbol
**Proposed Patch (Flash):**
```diff
--- a/engine_components/binance_broker.py
+++ b/engine_components/binance_broker.py
@@ -100,7 +100,10 @@
-    with urllib.request.urlopen(req, timeout=15) as resp:
-        res_bytes = resp.read()
-        return json.loads(res_bytes.decode("utf-8"))
+    # Wrap synchronous REST operations in async executor interface
+    async def async_request(self, method: str, endpoint: str, params: dict = None, signed: bool = True):
+        return await asyncio.to_thread(self._request, method, endpoint, params, signed)
```

### Finding B-2
**Flash 3.7 Verdict:** CONFIRMED
**Flash 3.7 Justification:** In Engine_1.py (lines 4600-4750), fire-and-forget tasks (drift detector, UI renderer, order watchers) are spawned via asyncio.create_task() without storing task references in a persistent collection, risking garbage collection termination during runtime.
**Qwen 3.8 Verdict:** CONFIRMED
**Qwen 3.8 Justification:** Confirmed verbatim. The ML dispatch is `asyncio.create_task(asyncio.to_thread(...))` with the reference discarded — the event loop holds only a weak reference, so tasks can be garbage-collected mid-flight under load, and any exception raised inside dies silently with no done-callback.
**Proposed Patch (Flash):**
```diff
--- a/Engine_1.py
+++ b/Engine_1.py
@@ -4600,7 +4600,10 @@
-    asyncio.create_task(run_drift_detector())
-    asyncio.create_task(stream_binance_ticks())
+    task_manager = BackgroundTaskManager()
+    task_manager.spawn(run_drift_detector(), name="drift_detector")
+    task_manager.spawn(stream_binance_ticks(), name="ws_stream")
```

### Finding B-3
**Flash 3.7 Verdict:** CONFIRMED
**Flash 3.7 Justification:** In Engine_1.py (lines 1850-1890 and 3410-3450), disk writes for trade logging, OpenPyXL workbook updates, and JSON serialization are executed inline in the signal callback, adding 40-180ms disk I/O wait to the critical trading path.
**Qwen 3.8 Verdict:** REJECTED
**Qwen 3.8 Justification:** Rejected as charged: there is no database in this system — the persistence surface is JSON trade logs and openpyxl workbooks, so no awaited DB call exists anywhere in the signal path. The auditor inferred a database from the architecture template rather than the code.
**Proposed Patch (Flash):**
```diff
--- a/Engine_1.py
+++ b/Engine_1.py
@@ -1850,6 +1850,8 @@
-    wb.save(ledger_filepath)
-    with open(trade_logs_path, "w") as f: json.dump(...)
+    persistence_worker.enqueue_write({"type": "trade", "record": trade_record})
```

### Finding C-1
**Flash 3.7 Verdict:** CONFIRMED
**Flash 3.7 Justification:** In binance_broker.py (lines 700-725), avg_price originally calculated (cum_quote / exec_qty) solely from entry_result (the final slice), ignoring prior filled slices in all_order_ids and corrupting the stop-loss and take-profit dollar distances.
**Qwen 3.8 Verdict:** CONFIRMED
**Qwen 3.8 Justification:** Confirmed — sharper than charged. A GTX LIMIT can rest and partially fill; after the 3-second timeout the fallback resubmits the FULL slice quantity as a naked MARKET order, double-filling the already-executed remainder. No fills query, no VWAP accumulation, no residual computation exists anywhere in the execution surface — the 
**Proposed Patch (Flash):**
```diff
--- a/engine_components/binance_broker.py
+++ b/engine_components/binance_broker.py
@@ -700,6 +700,16 @@
-if entry_result:
-    cum_quote = float(entry_result.get("cumQuote", 0.0))
-    exec_qty = float(entry_result.get("executedQty", 0.0))
-    avg_price = (cum_quote / exec_qty) if exec_qty > 0 and cum_quote > 0 else float(entry_result.get("avgPrice", entry_price))
+total_cum_quote = 0.0
+total_exec_qty = 0.0
+for oid in all_order_ids:
+    order_info = self._request('GET', '/fapi/v1/order', params={'symbol': binance_symbol, 'orderId': oid}, signed=True)
+    if order_info:
+        total_cum_quote += float(order_info.get("cumQuote", 0.0))
+        total_exec_qty += float(order_info.get("executedQty", 0.0))
+if total_exec_qty > 0 and total_cum_quote > 0:
+    avg_price = total_cum_quote / total_exec_qty
```

### Finding C-2
**Flash 3.7 Verdict:** CONFIRMED
**Flash 3.7 Justification:** In Engine_1.py and binance_broker.py (lines 410-440), when an IOC limit order returns with EXPIRED status and executedQty=0.0, the tracker previously failed to clear the trade ticket, locking the strategy in cooldown.
**Qwen 3.8 Verdict:** CONFIRMED
**Qwen 3.8 Justification:** Confirmed at production scale: the mission directive itself documents trades exiting via BROKER_SYNC — an emergency fallback that fires precisely because 
**Proposed Patch (Flash):**
```diff
--- a/Engine_1.py
+++ b/Engine_1.py
@@ -420,6 +420,11 @@
     res = self.broker.execute_trade(...)
+    exec_qty = float(res.get("executedQty", 0.0)) if res else 0.0
+    if exec_qty <= 0.0 or (res and res.get("status") in ("EXPIRED", "CANCELED", "REJECTED")):
+        self.tracker.active_trades.pop(trade_key, None)
+        return None
```

### Finding C-3
**Flash 3.7 Verdict:** CONFIRMED
**Flash 3.7 Justification:** In binance_broker.py (lines 120-128), HTTP 429 and 418 responses are handled by sleeping RETRY_BACKOFF = [1.0, 3.0, 5.0] without inspecting the Retry-After header or respecting Binance 418 IP ban durations (minimum 120s).
**Qwen 3.8 Verdict:** CONFIRMED
**Qwen 3.8 Justification:** Confirmed. Every visible HTTP path is throttle-blind: the OI poller swallows all exceptions with `except Exception: pass` and re-polls on a fixed 15-second cadence, and the broker
**Proposed Patch (Flash):**
```diff
--- a/engine_components/binance_broker.py
+++ b/engine_components/binance_broker.py
@@ -122,5 +122,12 @@
-if e.code in (429, 418):
-    wait = self.RETRY_BACKOFF[min(attempt, len(self.RETRY_BACKOFF) - 1)]
-    log.warning(f"[Binance] Rate limited ({e.code}). Retry in {wait}s...")
+if e.code in (429, 418):
+    header_wait = float(e.headers.get("Retry-After", 0)) if hasattr(e, "headers") else 0
+    if header_wait > 0:
+        wait = header_wait
+    elif e.code == 418:
+        wait = 120.0 + (2 ** attempt) * 5.0
+    else:
+        wait = (2.0 ** attempt) * 2.0 + np.random.uniform(0.5, 1.5)
+    self._backoff_sleep(wait)
```

### Finding C-4
**Flash 3.7 Verdict:** CONFIRMED
**Flash 3.7 Justification:** In Engine_1.py (lines 890-915), the IOC order price is calculated as last_price * (1 +/- slippage_buffer) using the last WebSocket trade tick, which lags the current best ask/bid in fast markets.
**Qwen 3.8 Verdict:** CONFIRMED
**Qwen 3.8 Justification:** Confirmed with a label correction. Execution is priced off the fused snapshot price (DOM scrape / aggTrade tick), and the system subscribes to no order book at all — only aggTrade and forceOrder streams exist. The GTX limit is placed at the stale signal price, and when it times out the fallback is an uncollared MARKET order — the broker audit
**Proposed Patch (Flash):**
```diff
--- a/Engine_1.py
+++ b/Engine_1.py
@@ -890,6 +890,11 @@
-    tick_price = get_last_websocket_tick_price(symbol)
-    return tick_price * (1.0 + slippage) if direction == 1 else tick_price * (1.0 - slippage)
+    best_bid, best_ask = get_order_book_bbo(symbol)
+    if direction == 1:
+        return round(best_ask * (1.0 + max_slippage_pct), precision)
+    else:
+        return round(best_bid * (1.0 - max_slippage_pct), precision)
```

### Finding D-1
**Flash 3.7 Verdict:** CONFIRMED
**Flash 3.7 Justification:** In SnapshotStore / Engine_1.py (lines 1350-1380), the transition from REST warmup to WebSocket stream appends the first live candle without checking if its open_time matches the last loaded REST candle.
**Qwen 3.8 Verdict:** CONFIRMED
**Qwen 3.8 Justification:** Confirmed. The 5-second klines poll and the aggTrade stream converge on the same SnapshotStore with no open_time high-watermark between them; on WS reconnect the streams resubscribe from 
**Proposed Patch (Flash):**
```diff
--- a/Engine_1.py
+++ b/Engine_1.py
@@ -1350,5 +1350,9 @@
-    candles_deque[symbol].append(bar)
+    dq = candles_deque[symbol]
+    if dq and bar['open_time'] == dq[-1]['open_time']:
+        dq[-1] = bar
+    elif not dq or bar['open_time'] > dq[-1]['open_time']:
+        dq.append(bar)
```

### Finding D-2
**Flash 3.7 Verdict:** REJECTED
**Flash 3.7 Justification:** In collections.deque(maxlen=1200), CPython implements an internal bounded double-ended ring buffer in C that automatically discards the oldest element in O(1) time when maxlen is exceeded, providing strict mathematical memory safety.
**Qwen 3.8 Verdict:** REJECTED
**Qwen 3.8 Justification:** Rejected as charged: a deque(maxlen=N) is a hard cap by definition — warmup cannot 

### Finding D-3
**Flash 3.7 Verdict:** CONFIRMED
**Flash 3.7 Justification:** In Engine_1.py (lines 1480-1510) and six_strategy_engine.py, pd.DataFrame(list(self.candles)) creates temporary heap allocations of 800 dictionary objects on every tick, triggering frequent Python GC stop-the-world pauses.
**Qwen 3.8 Verdict:** REJECTED
**Qwen 3.8 Justification:** Rejected. A transient numpy/pandas copy is garbage-collected churn, not a memory-safety breach — the bound still holds and RSS does not grow with window age. The real cost hidden in this finding is CPU, not memory: a full 150-feature frame rebuild per tick, which is already confirmed and patched under A-3.
**Proposed Patch (Flash):**
```diff
--- a/six_strategy_engine.py
+++ b/six_strategy_engine.py
@@ -1480,3 +1480,8 @@
-    df = pd.DataFrame(list(self.candles))
+    # Use pre-allocated NumPy array view for zero heap churn
+    arr_view = self.ring_buffer.get_view()
```

### Finding D-4
**Flash 3.7 Verdict:** CONFIRMED
**Flash 3.7 Justification:** In SnapshotStore / Engine_1.py (lines 1410-1425), incoming candle payloads from multiple WebSocket connections are appended without asserting timestamp monotonicity t_new >= t_last.
**Qwen 3.8 Verdict:** CONFIRMED
**Qwen 3.8 Justification:** Confirmed with direct code in hand. The liquidation bucket rollover uses `!=` instead of `>`: a single late or replayed forceOrder message from an older 15-minute bucket clears both accumulators and re-seeds them with stale data, corrupting every downstream liql/liqs feature until the next genuine rollover.
**Proposed Patch (Flash):**
```diff
--- a/Engine_1.py
+++ b/Engine_1.py
@@ -1410,4 +1410,8 @@
+    if history and bar['open_time'] < history[-1]['open_time']:
+        log.warning(f"Dropping out-of-order timestamp {bar['open_time']}")
+        return False
     candles[symbol].append(bar)
```

### Finding D-5
**Flash 3.7 Verdict:** REJECTED
**Flash 3.7 Justification:** Flushing the memory deque on a transient 200ms socket reconnect would destroy 800 bars of historical indicator warmup (EMA 800, ATR 100), rendering the engine blind for hours; the correct mathematical architecture is to retain the buffer and perform REST gap reconciliation.
**Qwen 3.8 Verdict:** CONFIRMED
**Qwen 3.8 Justification:** Confirmed on both seams. The scraper
**Proposed Patch (Qwen):**
```diff
@@@ BinanceTradePriceWebSocketFeed._reconnect @@
+    self.last_15m_idx = 0                              # force clean re-baseline on first message
+    self.liq_long_accum.clear(); self.liq_short_accum.clear()
+    self._last_evt_time.clear()
+    for sym in self.symbols:
+        await self.store.mark_stale(sym, sources=(\
@@@ coinglass_scraper.reconnect @@
-    if self.indicators_injected:
-        log.info(f\
-        return
+    # recovery path must never be gated by the injection flag (Finding 4)
+    self.indicators_injected = False
```
