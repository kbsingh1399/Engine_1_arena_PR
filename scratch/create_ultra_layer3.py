import json

prompt = """# LAYER 3: SUPREME JUDGE (VERDICT & SYNTHESIS ROUND)

You are the Supreme Judge in a multi-agent adversarial audit of `Engine_1.py`.
Two elite defenders (Flash 3.7 & Qwen 3.8) have cross-examined a Layer 1 Attack Report. 

As the Orchestrator, I have analyzed their 1500-line JSON reports and synthesized the exact state of the debate below to save your context window.

Your objective is to output the final JSON patch array fixing the confirmed bugs. 

## 1. UNANIMOUSLY CONFIRMED BUGS (Patch Required)
Both defenders agreed these are real, critical bugs. Provide a unified patch for these:
*   **A-2 (Z-Score Warmup):** Live 5s rows pollute the 15m Z-score normalization window. CVD baselines reset on reload. (Fix: Diff session-relative CVD, only admit closed 15m bars to `_zscore`).
*   **A-3 (Indicator Latency):** 150+ features are rebuilt on every tick. (Fix: Gate `featurize()` and EMA updates to closed-bar boundaries, cache per bar timestamp).
*   **B-1 (Sync Order Blocking):** GTX-LIMIT fallback uses synchronous REST (`urllib.request`) inside the asyncio WS loop. (Fix: Offload exit-checks and broker I/O to a dedicated `asyncio.Queue` worker).
*   **B-2 (Orphaned Tasks):** `asyncio.create_task(run_drift_detector())` lacks strong references. (Fix: Add a task registry with `add_done_callback` to prevent GC).
*   **C-1 (Partial Fills):** GTX limit partial fills are followed by a naked MARKET sweep of the full quantity, double-filling. (Fix: Reconcile filled qty via GET /order, compute VWAP, sweep only the residual).
*   **C-2 (Ghost Positions):** Orders fully rejected by Binance still consume local risk budgets. (Fix: Book trades only on confirmed fill, rollback reservations on rejection).
*   **C-3 (Rate Limits):** No exponential backoff for HTTP 429/418. (Fix: Parse `Retry-After`, apply exponential backoff + jitter).
*   **C-4 (Stale Limit Price):** GTX limit placed at stale signal price. (Fix: Price the sweep from `bookTicker` mid ± collar, not the lagged `aggTrade` price).
*   **D-1 (REST/WS Duplicate Seam):** WebSocket reconnects inject duplicate candles overlapping the REST poll. (Fix: Track candle open_time high-watermark, deduplicate overlaps).
*   **D-4 (Timestamp Monotonicity):** 15-minute rollover uses `!=` instead of `<`. Replayed ticks clear accumulators. (Fix: Ignore backward-time ticks, strictly use `<` for rollover).

## 2. DISPUTED BUGS (Judge Must Resolve)
The defenders disagreed on these. Review and decide whether to patch:
*   **A-1 (CVD Rollover Float Math):** Flash claims `math.isclose()` is used on float timestamps for 15m rollovers, causing precision misses. Qwen claims this is a hallucination; the engine uses exact integer division (`evt_time // 900000`). Judge: Check the code. If Qwen is right, drop this.
*   **B-3 (Inline Persistence Blocking):** Flash flags a blocking Database write. Qwen rejects it, stating no DB exists, but admits JSON/openpyxl file I/O blocks the thread. Judge: Patch the file I/O blocking using `asyncio.to_thread`.
*   **D-5 (Reconnect State Flush):** Flash claims flushing deque on WS reconnect destroys 800 bars of historical data. Qwen argues we MUST flush derived accumulators and mark snapshots stale, or replayed `forceOrder` history will double-count. Judge: Resolve the architectural tradeoff.

## 3. UNANIMOUSLY REJECTED (Do Not Patch)
*   **D-2 & D-3:** Attacks on `deque(maxlen=1200)` memory safety were unanimously debunked as fundamentally misunderstanding Python GC semantics.

---

**Output Requirement:**
Output ONLY a JSON array containing the final, unified patches for the confirmed and resolved bugs. 
Format:
[
  {
    "file": "Engine_1.py",
    "diffCode": "unified diff patch"
  }
]
"""

with open('layer_3_synthesis_prompt.md', 'w', encoding='utf-8') as f:
    f.write(prompt)
print("Updated to ultra-condensed orchestrator format.")
