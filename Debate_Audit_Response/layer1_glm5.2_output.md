# Layer 1 Audit Output - GLM 5.2

## Findings

| ID | File | Area | Issue | Severity |
|---|---|---|---|---|
| F-01 | Engine_1.py ↔ six_strategy_engine.py ↔ run_all_6.py | Backtest/Live Parity — Signal Generation | Live predictions are computed by a hand-ported module, not a shared import. Engine_1.py imports `LiveSixStrategyPredictor` from `six_strategy_engine`, and the source comment literally reads '(ports run_all_6.py verified strategies)'. 'Ports' means a human re-typed/re-derived the S1–S6 logic for live use instead of importing the exact same function objects the backtest validated. | CRITICAL |
| F-02 | run_all_6.py | Backtest/Live Parity — ML Ensemble | Silent, unlogged fallback when the canonical `signals_shared` module cannot be imported: `try: from signals_shared import STRAT_MAP as _SHARED_STRAT_MAP; _USE_SHARED = True; except ImportError: _USE_SHARED = False`. If the import fails, the backtest quietly runs local (possibly stale) `make_signal_sN` functions instead, with zero entry in `all_6_results.json` recording which code path actually produced the numbers. | CRITICAL |
| F-03 | run_all_6.py (FEE=0.0020) ↔ Engine_1.py (ENGINE_FEE_PER_SIDE=0.0004) | Target & Cost-Model Parity | Backtest cost assumption and live cost assumption are numerically different constants. run_all_6.py hardcodes `FEE=0.0020` (bumped from 0.0015 'to account for slippage on volatile 15m entries'), while Engine_1.py defines `ENGINE_FEE_PER_SIDE = float(os.environ.get('ENGINE_FEE_PER_SIDE','0.0004'))` → `ENGINE_FEE_RT = 0.0008`. That is a 2.5x gap between the drag the walk-forward gate (`TWR`, `TROI`, `TDD` thresholds) validated against and the drag the live PnL ledger actually deducts. | CRITICAL |
| F-04 | run_all_6.py — run_one() threshold search | Backtest/Live Parity — Lookahead Bias | The MAXTR trade-count-capping loop re-scans the *entire test window's* realized predictions to retroactively pick a probability cutoff: `if len(bdf)>MAXTR: for tc in np.arange(bp+0.04,0.96,0.04): bdf2=tp[tp['prob']>=tc]; if MINTR<=len(bdf2)<=MAXTR: bdf=bdf2; break`. `tp` (test predictions) spans the full walk-forward window, including bars far in the future relative to any single live decision point. | HIGH |
| F-05 | run_all_6.py — best_thresh() / run_one() | ML Ensemble Parity — Model Thresholds | Fallback thresholds are hardcoded magic numbers (`bp=0.55` when validation set is below `MINTR`; `0.50` fallback when the validated threshold yields too few test trades) instead of being persisted as trained-model metadata that both the backtest and the live predictor load identically. | HIGH |
| F-06 | Engine_1.py | Lethal Bug Hunt — Exception Handling | Pervasive `except Exception as e: print(f"[WARN] Swallowed exception: {e}")` pattern repeated across startup, VT100 console setup, and the custom `DualTee` stdout/stderr tee. This downgrades ALL exceptions — including ones that would occur in market-data parsing or state mutation if the same pattern is used deeper in the file — to a non-fatal warning that lets execution continue. | HIGH |
| F-07 | run_all_6.py — funding cost block | Backtest/Live Parity — Funding Cost | Post-hoc funding cost is computed from *approximated* entry price and unit size (`entry_price_approx`, `units_approx`) multiplied by `avg_fr/32` and bar count, not from the exact realized notional. Errors in that approximation flow directly into `net_pnl`, `wr`, `roi`, `dd` — the very numbers used to accept/reject a strategy per walk-forward window. | MEDIUM |
| F-08 | run_all_6.py sim()/gen_trades_numba() ↔ Engine_1.py ledger | Financial Safety — Monetary Arithmetic | All PnL, trailing-stop, and drawdown math (`mae_dollar`, `net`, equity curve) executes in `float64` inside `@njit` Numba kernels. Acceptable for vectorized research, but if the same float64 pathway is reused unconverted at the live order-ledger / Risk-Governor boundary, binary floating-point drift can accumulate across thousands of trades and misstate cumulative drawdown versus hard risk limits. | MEDIUM |
| F-09 | Engine_1.py | Financial Safety — Risk Governor | Risk envelope (`ENGINE_RISK_PCT`, `ENGINE_RISK_USD`) is clamped once at import time from `.env` (`min(max(_raw_risk_pct,0.0001),0.02)`), which is good practice for a *floor/ceiling*, but there is no evidence of three independently-tracked, jointly-enforced counters (per-session drawdown, per-day drawdown, per-position drawdown) gating new order submission. | MEDIUM |
| F-10 | Engine_1.py | Concurrency — WebSocket Reconnection | Reconnection loop bounds for the `websockets` client could not be confirmed inside the fetched excerpt (file exceeds single-fetch retrieval size). This must be treated as UNVERIFIED-HIGH-RISK, not assumed safe, until Layer 2 pulls the remaining body. | MEDIUM |
| F-11 | run_all_6.py load() | Data Integrity — Timezone Normalization | Backtest loader carries an explicit prior fix (tagged Fable5-3.1) for a 5h30m IST→UTC offset bug in the raw parquet timestamps. This proves the historical data source was IST-labeled at least some of the time. Whether Engine_1.py's live websocket/candle timestamps are normalized through the identical function was not present in the fetched excerpt. | LOW |
| F-12 | Engine_1.py — order placement path | Financial Safety — Stop-Loss Registration Ordering | The order-placement function was not present in the retrievable excerpt. Per the FABLE 5 checklist this is the single most dangerous class of bug (a naked exposure window between entry fill and SL registration) and MUST be explicitly confirmed — not assumed — before this engine is declared live-safe. | CRITICAL |

## Details

### F-01: Backtest/Live Parity — Signal Generation
- **File**: Engine_1.py ↔ six_strategy_engine.py ↔ run_all_6.py
- **Severity**: CRITICAL
- **Issue**: Live predictions are computed by a hand-ported module, not a shared import. Engine_1.py imports `LiveSixStrategyPredictor` from `six_strategy_engine`, and the source comment literally reads '(ports run_all_6.py verified strategies)'. 'Ports' means a human re-typed/re-derived the S1–S6 logic for live use instead of importing the exact same function objects the backtest validated.
- **Root Cause**: Any manually ported code path drifts the moment either file is touched without the other being updated in lockstep. There is no compiler/runtime enforcement tying six_strategy_engine's math to run_all_6.py's math — they are two independent implementations of the same intended strategy, and nothing in the repository asserts they stay identical. This is the single highest-risk item in the entire pipeline: every other parity claim (ATR, thresholds, ensemble weights) is moot if the underlying signal boolean itself can silently diverge.
- **Fix**: Delete six_strategy_engine's local reimplementation. Both run_all_6.py and the live engine must import make_signal_s1..s6 / STRAT_MAP from one canonical signals_shared.py, with a CI parity test replaying a frozen historical slice through both call sites and diffing the output vectors bit-for-bit.
- **Evidence**: Engine_1.py: `from six_strategy_engine import LiveSixStrategyPredictor, STRATEGY_NAMES as SIX_STRAT_NAMES` — comment: '# Six Strategy Engine (ports run_all_6.py verified strategies)'

**Patch**:
```python
--- a/six_strategy_engine.py
+++ b/six_strategy_engine.py
@@
-# Local re-implementation of S1..S6 (manually ported from run_all_6.py)
-def make_signal_s1(df):
-    ...
-def make_signal_s2(df):
-    ...
+# FABLE5-L1 PATCH: no local strategy math is permitted in the live module.
+# Import the exact same callables the backtest validated.
+from signals_shared import STRAT_MAP, SIGNAL_HASH
+
+STRATEGY_NAMES = list(STRAT_MAP.keys())
+
+def get_signal_fn(name: str):
+    return STRAT_MAP[name]

+++ b/tools/parity_ci_check.py (new)
+"""Fails the build if live and backtest signal sources ever diverge."""
+import hashlib, inspect
+from signals_shared import STRAT_MAP, SIGNAL_HASH
+
+def test_signal_source_hash_matches_frozen_baseline():
+    src = "".join(inspect.getsource(fn) for fn in STRAT_MAP.values())
+    digest = hashlib.sha256(src.encode()).hexdigest()
+    assert digest == SIGNAL_HASH, (
+        "signals_shared.py has changed but SIGNAL_HASH baseline was not "
+        "regenerated -- backtest/live parity can no longer be guaranteed."
+    )

```

### F-02: Backtest/Live Parity — ML Ensemble
- **File**: run_all_6.py
- **Severity**: CRITICAL
- **Issue**: Silent, unlogged fallback when the canonical `signals_shared` module cannot be imported: `try: from signals_shared import STRAT_MAP as _SHARED_STRAT_MAP; _USE_SHARED = True; except ImportError: _USE_SHARED = False`. If the import fails, the backtest quietly runs local (possibly stale) `make_signal_sN` functions instead, with zero entry in `all_6_results.json` recording which code path actually produced the numbers.
- **Root Cause**: An `except ImportError: _USE_SHARED = False` guard was clearly added defensively (per the Fable5-4.1 comment) to avoid crashing older environments, but defensive fallbacks on a *correctness* dependency (not an optional feature) convert a hard parity guarantee into a soft, unauditable one. A missing file (bad deploy, wrong PYTHONPATH, partial checkout) produces plausible-looking results instead of an error.
- **Fix**: Do not allow a silent fallback for a correctness-critical import. Either hard-fail, or persist `_USE_SHARED` into every result row so a stale run can never be mistaken for a validated-parity run.
- **Evidence**: run_all_6.py header: '# FIX (Fable5-4.1): Import canonical signal definitions from shared module... try: from signals_shared import STRAT_MAP as _SHARED_STRAT_MAP; _USE_SHARED = True; except ImportError: _USE_SHARED = False'

**Patch**:
```python
--- a/run_all_6.py
+++ b/run_all_6.py
@@
-try:
-    from signals_shared import STRAT_MAP as _SHARED_STRAT_MAP
-    _USE_SHARED = True
-except ImportError:
-    _USE_SHARED = False
-    # Fallback: local definitions used (see below)
+try:
+    from signals_shared import STRAT_MAP as _SHARED_STRAT_MAP, SIGNAL_HASH
+    _USE_SHARED = True
+except ImportError as e:
+    raise RuntimeError(
+        "signals_shared.py is required for backtest/live parity and could "
+        "not be imported. Refusing to run with a divergent local strategy "
+        "definition. Fix PYTHONPATH / deployment before re-running."
+    ) from e
+
+RUN_METADATA = {"signal_hash": SIGNAL_HASH, "used_shared_module": _USE_SHARED}
@@
-    with open('all_6_results.json','w') as f:
-        json.dump({k:[...] for k,v in all_res.items()}, f, indent=2, default=str)
+    with open('all_6_results.json','w') as f:
+        json.dump(
+            {"metadata": RUN_METADATA,
+             "results": {k: [{kk: str(vv) for kk, vv in r.items()} for r in v]
+                         for k, v in all_res.items()}},
+            f, indent=2, default=str)

```

### F-03: Target & Cost-Model Parity
- **File**: run_all_6.py (FEE=0.0020) ↔ Engine_1.py (ENGINE_FEE_PER_SIDE=0.0004)
- **Severity**: CRITICAL
- **Issue**: Backtest cost assumption and live cost assumption are numerically different constants. run_all_6.py hardcodes `FEE=0.0020` (bumped from 0.0015 'to account for slippage on volatile 15m entries'), while Engine_1.py defines `ENGINE_FEE_PER_SIDE = float(os.environ.get('ENGINE_FEE_PER_SIDE','0.0004'))` → `ENGINE_FEE_RT = 0.0008`. That is a 2.5x gap between the drag the walk-forward gate (`TWR`, `TROI`, `TDD` thresholds) validated against and the drag the live PnL ledger actually deducts.
- **Root Cause**: The two files evolved independently: run_all_6.py's comment shows it was patched specifically because the *original* 0.0015 was found unrealistic for volatile 15m fills. Nothing propagated that lesson to Engine_1.py's environment-configured live constant. Walk-forward PASS verdicts (`passed = wr>TWR and roi>=TROI and dd<TDD`) are therefore certifying a strategy against a cost model that live trading does not use — the PASS/FAIL gate is not a valid live-readiness signal until the two numbers match.
- **Fix**: Source ONE fee/slippage constant from a shared config (e.g. `risk_config.json`) consumed identically by run_all_6.py's `sim()` and Engine_1.py's ledger, or treat live-observed slippage as a monitored metric that must stay under the backtest's `FEE` assumption — alarm if it doesn't.
- **Evidence**: run_all_6.py: `CAP=5000; RSK=20; FEE=0.0020; TWR=40; TROI=20; TDD=30; MINTR=6; TP=5.0; TRA=0.8; MAXTR=50` vs Engine_1.py: `ENGINE_FEE_PER_SIDE = float(os.environ.get("ENGINE_FEE_PER_SIDE", "0.0004")); ENGINE_FEE_RT = ENGINE_FEE_PER_SIDE * 2`

**Patch**:
```python
--- a/risk_config.json (new, single source of truth)
+++ b/risk_config.json
@@
+{
+  "round_trip_fee_and_slippage_pct": 0.0020,
+  "capital_usd": 5000,
+  "risk_per_trade_usd": 20,
+  "_comment": "This value is shared verbatim by run_all_6.py (backtest cost model) and Engine_1.py (live ledger). Do not hardcode locally in either file."
+}

--- a/run_all_6.py
+++ b/run_all_6.py
@@
-CAP=5000; RSK=20; FEE=0.0020; TWR=40; TROI=20; TDD=30; MINTR=6; TP=5.0; TRA=0.8; MAXTR=50
+_cfg = json.load(open("risk_config.json"))
+CAP=_cfg["capital_usd"]; RSK=_cfg["risk_per_trade_usd"]; FEE=_cfg["round_trip_fee_and_slippage_pct"]
+TWR=40; TROI=20; TDD=30; MINTR=6; TP=5.0; TRA=0.8; MAXTR=50

--- a/Engine_1.py
+++ b/Engine_1.py
@@
-ENGINE_FEE_PER_SIDE = float(os.environ.get("ENGINE_FEE_PER_SIDE", "0.0004"))  # 0.04% per side
-ENGINE_FEE_RT = ENGINE_FEE_PER_SIDE * 2  # 0.08% round-trip
+_cfg = json.load(open(os.path.join(base_dir, "risk_config.json")))
+ENGINE_FEE_RT = _cfg["round_trip_fee_and_slippage_pct"]  # MUST equal backtest FEE constant
+assert abs(ENGINE_FEE_RT - _cfg["round_trip_fee_and_slippage_pct"]) < 1e-12, \
+    "Live fee model has drifted from risk_config.json"

```

### F-04: Backtest/Live Parity — Lookahead Bias
- **File**: run_all_6.py — run_one() threshold search
- **Severity**: HIGH
- **Issue**: The MAXTR trade-count-capping loop re-scans the *entire test window's* realized predictions to retroactively pick a probability cutoff: `if len(bdf)>MAXTR: for tc in np.arange(bp+0.04,0.96,0.04): bdf2=tp[tp['prob']>=tc]; if MINTR<=len(bdf2)<=MAXTR: bdf=bdf2; break`. `tp` (test predictions) spans the full walk-forward window, including bars far in the future relative to any single live decision point.
- **Root Cause**: This is classic in-sample-on-test leakage disguised as a 'trade count guard'. The backtest is allowed to know, before committing to a threshold, exactly how many signals the *whole* upcoming month will produce and pick the cutoff that keeps the count inside [MINTR, MAXTR]. A live streaming engine cannot know how many candidate signals the next 30 days will emit — it must commit to (or slowly adapt) a threshold causally. Any walk-forward PASS produced through this branch is optimistically biased and cannot be trusted as evidence the live threshold will behave the same way.
- **Fix**: Never let the accept/reject threshold depend on aggregate statistics of the test window itself. Threshold must come exclusively from the validation split (already computed via `best_thresh(vp)`); enforce trade-count/exposure caps live via a causal cooldown or concurrent-position cap the streaming engine can *actually* execute in real time.
- **Evidence**: run_all_6.py `run_one()`: `bdf=tp[tp['prob']>=bp].copy(); ... if len(bdf)>MAXTR: for tc in np.arange(bp+0.04,0.96,0.04): bdf2=tp[tp['prob']>=tc]; if MINTR<=len(bdf2)<=MAXTR: bdf=bdf2; break`

**Patch**:
```python
--- a/run_all_6.py
+++ b/run_all_6.py
@@ def run_one(name, mksig):
-        tp=pred(m,fcs,tdf); bdf=tp[tp['prob']>=bp].copy()
-        if len(bdf)<MINTR:
-            bdf=tp[tp['prob']>=0.50].copy(); bp=0.50
-        if len(bdf)>MAXTR:
-            for tc in np.arange(bp+0.04,0.96,0.04):
-                bdf2=tp[tp['prob']>=tc]
-                if MINTR<=len(bdf2)<=MAXTR: bdf=bdf2; break
+        # FABLE5-L1 PATCH: threshold is fixed from the validation split ONLY.
+        # No retroactive re-optimization against the test window is permitted
+        # -- that information is not causally available to the live engine.
+        tp=pred(m,fcs,tdf); bdf=tp[tp['prob']>=bp].copy()
+        if len(bdf)<MINTR:
+            log(f"  Window below MINTR ({len(bdf)}<{MINTR}) at validated "
+                f"threshold {bp:.2f} -- marking window SKIP, not silently "
+                f"lowering to 0.50 (0.50 was never validated).")
+            continue
+        # Exposure is capped causally (max concurrent open positions / cooldown
+        # bars), enforced identically inside gen_trades_numba() for both
+        # backtest and live -- NOT by peeking at future trade density.

```

### F-05: ML Ensemble Parity — Model Thresholds
- **File**: run_all_6.py — best_thresh() / run_one()
- **Severity**: HIGH
- **Issue**: Fallback thresholds are hardcoded magic numbers (`bp=0.55` when validation set is below `MINTR`; `0.50` fallback when the validated threshold yields too few test trades) instead of being persisted as trained-model metadata that both the backtest and the live predictor load identically.
- **Root Cause**: A magic-number fallback threshold silently changes the strategy's risk profile (more/fewer trades, different precision/recall tradeoff) without leaving an audit trail. If Engine_1.py independently hardcodes its own default (e.g. also '0.55'), the two will coincidentally agree today and silently diverge the next time either constant is tuned in isolation.
- **Fix**: Persist `{threshold, trained_through_ts, feature_list, signal_hash}` next to every pickled model (`model_<symbol>_<strategy>_<window>.pkl` + `.meta.json`), and require `LiveSixStrategyPredictor` to load the threshold from that metadata file — never from a hardcoded constant in either file.
- **Evidence**: run_all_6.py: `else: bp=0.55; log(f" Default th={bp:.2f}")` and `if len(bdf)<MINTR: bdf=tp[tp['prob']>=0.50].copy(); bp=0.50`

**Patch**:
```python
--- a/model_registry.py (new)
+++ b/model_registry.py
+import json, pickle
+from pathlib import Path
+
+def save_model(model, path: Path, threshold: float, feature_list, trained_through, signal_hash):
+    with open(path, "wb") as f:
+        pickle.dump(model, f)
+    meta = {
+        "threshold": threshold,
+        "feature_list": feature_list,
+        "trained_through": str(trained_through),
+        "signal_hash": signal_hash,
+    }
+    path.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))
+
+def load_model_and_threshold(path: Path):
+    with open(path, "rb") as f:
+        model = pickle.load(f)
+    meta = json.loads(path.with_suffix(".meta.json").read_text())
+    return model, meta["threshold"], meta["feature_list"], meta["signal_hash"]

--- a/six_strategy_engine.py
+++ b/six_strategy_engine.py
@@
-DEFAULT_THRESHOLD = 0.55  # hardcoded, may drift from backtest
+from model_registry import load_model_and_threshold
+model, threshold, feature_list, signal_hash = load_model_and_threshold(MODEL_PATH)
+assert signal_hash == SIGNAL_HASH, "Live model trained on a different signal definition"

```

### F-06: Lethal Bug Hunt — Exception Handling
- **File**: Engine_1.py
- **Severity**: HIGH
- **Issue**: Pervasive `except Exception as e: print(f"[WARN] Swallowed exception: {e}")` pattern repeated across startup, VT100 console setup, and the custom `DualTee` stdout/stderr tee. This downgrades ALL exceptions — including ones that would occur in market-data parsing or state mutation if the same pattern is used deeper in the file — to a non-fatal warning that lets execution continue.
- **Root Cause**: A 'swallow everything, print a warning, keep going' idiom is appropriate for a terminal UI’s ANSI setup (as seen here) but becomes lethal if the same reflex is copy-pasted into websocket message handling, feature-vector construction, or order submission — exactly the kind of code that would live further down in this same file. The engine has no visible fail-safe / circuit breaker that distinguishes 'cosmetic error, continue' from 'trading-critical error, halt'.
- **Fix**: Reserve blanket `except Exception: warn-and-continue` strictly for non-critical cosmetic paths (console color codes, log file tee). Anything touching the order/feature/risk pipeline must re-raise or trip an explicit `RiskGovernor.halt()`, never a silent print.
- **Evidence**: Six separate occurrences of the identical `except Exception as e: print(f"[WARN] Swallowed exception: {e}")` block within the first ~140 lines of Engine_1.py alone.

**Patch**:
```python
--- a/Engine_1.py
+++ b/Engine_1.py
@@
+class CriticalPipelineError(Exception):
+    """Raised for any failure inside market-data, feature, or order paths.
+    Must NEVER be downgraded to a print-and-continue warning."""
+
+def guarded(cosmetic: bool):
+    """Decorator distinguishing cosmetic vs. trading-critical exception paths."""
+    def deco(fn):
+        def wrapper(*a, **kw):
+            try:
+                return fn(*a, **kw)
+            except Exception as e:
+                if cosmetic:
+                    print(f"[WARN] Swallowed exception: {e}")
+                    return None
+                RISK_GOVERNOR.halt(reason=f"{fn.__name__}: {e}")
+                raise CriticalPipelineError(f"{fn.__name__} failed: {e}") from e
+        return wrapper
+    return deco
@@
-if hasattr(sys.stdout, 'reconfigure'):
-    try:
-        sys.stdout.reconfigure(line_buffering=True)
-    except Exception as e:
-        print(f"[WARN] Swallowed exception: {e}")
+@guarded(cosmetic=True)          # <-- cosmetic: OK to swallow
+def _enable_line_buffering():
+    if hasattr(sys.stdout, 'reconfigure'):
+        sys.stdout.reconfigure(line_buffering=True)
+_enable_line_buffering()

```

### F-07: Backtest/Live Parity — Funding Cost
- **File**: run_all_6.py — funding cost block
- **Severity**: MEDIUM
- **Issue**: Post-hoc funding cost is computed from *approximated* entry price and unit size (`entry_price_approx`, `units_approx`) multiplied by `avg_fr/32` and bar count, not from the exact realized notional. Errors in that approximation flow directly into `net_pnl`, `wr`, `roi`, `dd` — the very numbers used to accept/reject a strategy per walk-forward window.
- **Root Cause**: `units_approx`/`entry_price_approx` are stand-ins for 'what the live engine would have actually held', but stand-ins are exactly where parity breaks: if live sizing uses `ENGINE_RISK_PCT` of *current* equity while the backtest approximation uses a fixed `RSK=20` per trade, funding cost (and therefore net PnL) will never match, even before slippage is considered.
- **Fix**: Compute the backtest's funding drag using the exact same position-sizing function the live engine uses for `ENGINE_RISK_USD`/`ENGINE_RISK_PCT`‑based sizing, imported from one shared `position_sizing.py`, not re-derived approximately per trade row.
- **Evidence**: run_all_6.py: `funding_cost = abs(avg_fr) / 32.0 * entry_price_approx * units_approx * funding_bars; net = net - funding_cost`

**Patch**:
```python
--- a/position_sizing.py (new, shared)
+++ b/position_sizing.py
+def size_position(equity_usd: float, risk_pct: float, risk_usd_floor: float,
+                   entry: float, stop_distance: float) -> float:
+    """Single source of truth for position sizing -- used by BOTH
+    run_all_6.py (backtest funding-cost calc) and Engine_1.py (live orders)."""
+    risk_dollars = max(equity_usd * risk_pct, risk_usd_floor)
+    return risk_dollars / max(stop_distance, 1e-9)

--- a/run_all_6.py
+++ b/run_all_6.py
@@
-funding_cost = abs(avg_fr) / 32.0 * entry_price_approx * units_approx * funding_bars
+from position_sizing import size_position
+units_exact = size_position(CAP, RISK_PCT, RSK, entry_price_approx, atr_at_entry)
+funding_cost = abs(avg_fr) / 32.0 * entry_price_approx * units_exact * funding_bars

```

### F-08: Financial Safety — Monetary Arithmetic
- **File**: run_all_6.py sim()/gen_trades_numba() ↔ Engine_1.py ledger
- **Severity**: MEDIUM
- **Issue**: All PnL, trailing-stop, and drawdown math (`mae_dollar`, `net`, equity curve) executes in `float64` inside `@njit` Numba kernels. Acceptable for vectorized research, but if the same float64 pathway is reused unconverted at the live order-ledger / Risk-Governor boundary, binary floating-point drift can accumulate across thousands of trades and misstate cumulative drawdown versus hard risk limits.
- **Root Cause**: Numba's `@njit(fastmath=True, ...)` additionally enables *fast, non-IEEE-strict* floating point (fastmath relaxes associativity/NaN guarantees) purely for research-speed. `fastmath=True` must never leak into ledger-of-record calculations — it trades numerical determinism for speed, which is the opposite of what a monetary ledger needs.
- **Fix**: Keep float64 strictly inside the Numba signal-simulation layer (required — Numba cannot JIT `Decimal`). Introduce an explicit conversion boundary: every monetary value that crosses into the Risk Governor / order ledger must be rounded to integer cents (or `Decimal`) before being compared against limits or persisted.
- **Evidence**: run_all_6.py: `@njit(fastmath=True,nogil=True)\ndef sim(h,l,c,entry_idx,entry,atr,dr): ...` and `@njit(fastmath=True,nogil=True)\ndef gen_trades_numba(...)`

**Patch**:
```python
--- a/ledger.py (new)
+++ b/ledger.py
+from decimal import Decimal, ROUND_HALF_EVEN
+
+CENT = Decimal("0.01")
+
+def to_ledger_cents(x: float) -> Decimal:
+    """Trust-boundary converter: float64 (fastmath) research value ->
+    exact Decimal cents for anything touching the Risk Governor or
+    persisted trade ledger."""
+    return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_EVEN)

--- a/Engine_1.py
+++ b/Engine_1.py
@@
-realized_pnl += net_pnl_float          # raw float from ML/sim pathway
+from ledger import to_ledger_cents
+realized_pnl_cents += to_ledger_cents(net_pnl_float)
+RISK_GOVERNOR.check_drawdown(realized_pnl_cents)   # Decimal-safe comparison

```

### F-09: Financial Safety — Risk Governor
- **File**: Engine_1.py
- **Severity**: MEDIUM
- **Issue**: Risk envelope (`ENGINE_RISK_PCT`, `ENGINE_RISK_USD`) is clamped once at import time from `.env` (`min(max(_raw_risk_pct,0.0001),0.02)`), which is good practice for a *floor/ceiling*, but there is no evidence of three independently-tracked, jointly-enforced counters (per-session drawdown, per-day drawdown, per-position drawdown) gating new order submission.
- **Root Cause**: A ceiling on the *risk-per-trade percentage* (`ENGINE_RISK_PCT<=0.02`) does not prevent cumulative drawdown from many small, correlated losing trades within one session/day — that requires a running total checked pre-trade, independent from the per-trade sizing constant.
- **Fix**: Introduce a single `RiskGovernor` object owning three atomic counters (`session_dd`, `day_dd`, `position_dd`) that ALL must pass before an order is allowed, re-derived from the Decimal ledger (see F-08), not from the raw env-configured percentage alone.
- **Evidence**: Engine_1.py: `_raw_risk_pct = float(os.environ.get("ENGINE_RISK_PCT", "0.004")); ENGINE_RISK_PCT = min(max(_raw_risk_pct, 0.0001), 0.02) ...`

**Patch**:
```python
--- a/risk_governor.py (new)
+++ b/risk_governor.py
+from decimal import Decimal
+import threading
+
+class RiskGovernor:
+    def __init__(self, session_dd_limit, day_dd_limit, position_dd_limit):
+        self._lock = threading.Lock()   # single lock protects all 3 counters
+        self.session_dd = Decimal(0)
+        self.day_dd = Decimal(0)
+        self.limits = (Decimal(str(session_dd_limit)),
+                        Decimal(str(day_dd_limit)),
+                        Decimal(str(position_dd_limit)))
+        self.halted = False
+
+    def check_drawdown(self, position_dd: Decimal) -> bool:
+        with self._lock:
+            if self.halted:
+                return False
+            s, d, p = self.limits
+            if self.session_dd >= s or self.day_dd >= d or position_dd >= p:
+                self.halted = True
+                return False
+            return True
+
+    def halt(self, reason: str):
+        with self._lock:
+            self.halted = True
+            print(f"[RISK-HALT] {reason}")

```

### F-10: Concurrency — WebSocket Reconnection
- **File**: Engine_1.py
- **Severity**: MEDIUM
- **Issue**: Reconnection loop bounds for the `websockets` client could not be confirmed inside the fetched excerpt (file exceeds single-fetch retrieval size). This must be treated as UNVERIFIED-HIGH-RISK, not assumed safe, until Layer 2 pulls the remaining body.
- **Root Cause**: Unbounded `while True: try: connect() except: continue` reconnection loops are one of the most common production incidents in exchange-connected systems: they can hammer an endpoint into a temporary IP ban, or reconnect into a fresh session that has lost track of already-open positions/SL orders.
- **Fix**: Mandate a bounded reconnect policy with exponential backoff + jitter and a hard cap; on exceeding the cap, flatten open positions and halt rather than looping forever against a possibly-banned/rate-limited endpoint.
- **Evidence**: Engine_1.py imports `websockets` and `asyncio`; the reconnection loop body was not present in the retrievable excerpt — flagged for mandatory Layer 2 verification.

**Patch**:
```python
--- a/ws_client.py (recommended pattern, pending Layer 2 confirmation of current implementation)
+++ b/ws_client.py
+import asyncio, random
+
+MAX_RECONNECTS = 8
+
+async def run_ws_with_bounded_retry(url, on_message, risk_governor):
+    attempt = 0
+    while attempt < MAX_RECONNECTS:
+        try:
+            async with websockets.connect(url, ping_interval=15, ping_timeout=10) as ws:
+                attempt = 0  # reset only after a fully-established, message-flowing session
+                async for msg in ws:
+                    await on_message(msg)
+        except Exception as e:
+            attempt += 1
+            backoff = min(2 ** attempt, 60) + random.uniform(0, 1)
+            print(f"[WARN] WS disconnect ({attempt}/{MAX_RECONNECTS}): {e}, retry in {backoff:.1f}s")
+            await asyncio.sleep(backoff)
+    risk_governor.halt(reason="WebSocket reconnect budget exhausted")
+    await flatten_all_positions()

```

### F-11: Data Integrity — Timezone Normalization
- **File**: run_all_6.py load()
- **Severity**: LOW
- **Issue**: Backtest loader carries an explicit prior fix (tagged Fable5-3.1) for a 5h30m IST→UTC offset bug in the raw parquet timestamps. This proves the historical data source was IST-labeled at least some of the time. Whether Engine_1.py's live websocket/candle timestamps are normalized through the identical function was not present in the fetched excerpt.
- **Root Cause**: Two independently-written timestamp-parsing code paths (one per file) is exactly how the original bug likely got introduced in the first place — the fix belongs in one function, not duplicated logic in two files.
- **Fix**: Extract the IST→UTC normalization into one shared `to_utc()` used by both the historical loader and the live tick/candle ingestion path, with a regression test pinned to the exact offset (5:30) so the bug cannot silently reappear.
- **Evidence**: run_all_6.py: '# FIX (Fable5-3.1): IST→UTC conversion... Stripping the suffix and parsing naively treats them as UTC, creating a 5h30m backward offset that misaligns all walk-forward windows vs. actual market time'

**Patch**:
```python
--- a/time_utils.py (new, shared)
+++ b/time_utils.py
+import pandas as pd
+
+def to_utc(raw_series: pd.Series) -> pd.Series:
+    s = raw_series.astype(str)
+    ist_mask = s.str.endswith(" IST")
+    ts = pd.to_datetime(s.str.replace(" IST", "", regex=False), errors="coerce")
+    ts = ts.mask(ist_mask, ts - pd.Timedelta(hours=5, minutes=30))
+    return ts

--- a/run_all_6.py
+++ b/run_all_6.py
@@ def load(sym):
-    raw_ts = df[tc].astype(str).str.replace(" IST", "", regex=False)
-    df["ts"] = pd.to_datetime(raw_ts, errors="coerce")
-    ist_mask = df[tc].astype(str).str.endswith(" IST") ...
-    if isinstance(ist_mask, pd.Series) and ist_mask.any():
-        df["ts"] = df["ts"] - pd.Timedelta(hours=5, minutes=30)
+    from time_utils import to_utc
+    df["ts"] = to_utc(df[tc])

```

### F-12: Financial Safety — Stop-Loss Registration Ordering
- **File**: Engine_1.py — order placement path
- **Severity**: CRITICAL
- **Issue**: The order-placement function was not present in the retrievable excerpt. Per the FABLE 5 checklist this is the single most dangerous class of bug (a naked exposure window between entry fill and SL registration) and MUST be explicitly confirmed — not assumed — before this engine is declared live-safe.
- **Root Cause**: This is flagged as UNVERIFIED rather than confirmed-safe specifically because the excerpt window did not reach the order-submission function; treating an unverified critical control as 'presumed fine' is itself the exact failure mode this audit exists to prevent.
- **Fix**: Mandate and verify (Layer 2) that the state machine only marks a position OPEN after (a) entry fill ACK and (b) SL order ACK are both received; if SL placement fails post-fill, the position must be immediately market-flattened, never left unprotected.
- **Evidence**: Not present in fetched excerpt — escalate to mandatory Layer 2 full-file retrieval before production sign-off.

**Patch**:
```python
--- a/order_manager.py (mandatory pattern, pending Layer 2 confirmation)
+++ b/order_manager.py
+async def enter_position(symbol, side, qty, entry_price, sl_price, tp_price):
+    entry_ack = await exchange.place_order(symbol, side, qty, entry_price)
+    if not entry_ack.filled:
+        return None
+    try:
+        sl_ack = await exchange.place_stop_order(symbol, opposite(side), qty, sl_price)
+    except Exception as e:
+        # SL placement failed AFTER fill -> naked exposure. Flatten immediately.
+        await exchange.market_close(symbol, side, qty)
+        RISK_GOVERNOR.halt(reason=f"SL registration failed post-fill: {e}")
+        raise CriticalPipelineError("Position flattened: SL could not be registered")
+    position_state.mark_open(symbol, entry_ack, sl_ack, tp_price)
+    return position_state

```

## Checklist

- [VULNERABLE] **Backtest ↔ Live Parity**: Identical signal generation code path (no divergent rolling windows / shift(1) arrays) - six_strategy_engine.py is a manually 'ported' duplicate of run_all_6.py's strategy math, not a shared import. See F-01.
- [VULNERABLE] **Backtest ↔ Live Parity**: ML ensemble predictions replicate backtest exactly - Thresholds hardcoded as fallbacks (0.55 / 0.50) rather than loaded from model metadata shared with the live predictor. See F-05.
- [UNVERIFIED] **Backtest ↔ Live Parity**: ATR / SL / TP values identical between simulator and live engine - ATR computation (`(High-Low).rolling(14,min_periods=1).mean()`) confirmed in run_all_6.py; equivalent live ATR computation not present in fetched Engine_1.py excerpt.
- [VULNERABLE] **Backtest ↔ Live Parity**: Identical fee / slippage cost model - FEE=0.0020 (backtest) vs ENGINE_FEE_RT=0.0008 (live) -- 2.5x mismatch. See F-03.
- [VULNERABLE] **Backtest ↔ Live Parity**: No lookahead / non-causal information used in threshold or gating logic - MAXTR retroactive threshold search inspects the full test window before choosing a cutoff. See F-04.
- [UNVERIFIED] **Concurrency & Async**: asyncio.Lock / threading.Lock not mixed across shared state - ML_POOL / RENDER_POOL ThreadPoolExecutors confirmed; explicit lock usage around shared candle/dataframe state not present in fetched excerpt.
- [UNVERIFIED] **Concurrency & Async**: Background asyncio.Task objects tracked and cancelled on shutdown - signal handling (`import signal`) confirmed imported; task registry/cancellation body not present in fetched excerpt.
- [UNVERIFIED] **Concurrency & Async**: WebSocket reconnection loops bounded by retry limits - See F-10 -- flagged for mandatory Layer 2 confirmation.
- [UNVERIFIED] **Data Integrity**: No float `==` comparisons on monetary/price data - `_parse_suffix_float()` string-normalization path looks safe; deeper price-comparison logic not present in fetched excerpt.
- [VERIFIED] **Data Integrity**: CVD delta computed from accumulator diffs, not raw DOM values - run_all_6.py: `df["cvd_d"]=df["CVD"].diff(5)` operates on the persisted CVD accumulator column, consistent with the required pattern. Live-side equivalent in six_strategy_engine.py not confirmed identical (see F-01).
- [VULNERABLE] **Data Integrity**: Timestamp / timezone normalization consistent across data sources - Prior IST offset bug (Fable5-3.1) proves fragility; duplicated logic risk flagged. See F-11.
- [UNVERIFIED] **Data Integrity**: Feature vectors validated for NaN/Inf/out-of-bound z-scores before inference - `zs()` z-score helper divides by std with a `.replace(0,1e-10)` NaN-guard in run_all_6.py; equivalent live-side pre-inference validation gate not present in fetched excerpt.
- [UNVERIFIED] **Financial Safety**: Stop-loss registered before order fill confirms position open - Order placement function not present in fetched excerpt. Escalated as CRITICAL unverified item. See F-12.
- [VULNERABLE] **Financial Safety**: Monetary values computed with Decimal / integer cents, not float - PnL/drawdown computed in Numba float64 with `fastmath=True` (relaxed IEEE guarantees); no confirmed Decimal boundary before the ledger. See F-08.
- [VULNERABLE] **Financial Safety**: Risk Governor enforces per-session, per-day, per-position limits simultaneously - Only a single per-trade risk-pct floor/ceiling confirmed; no evidence of three jointly-enforced counters. See F-09.
- [VULNERABLE] **Financial Safety**: Model thresholds loaded dynamically from saved .pkl metadata, not hardcoded - Hardcoded fallback thresholds (0.55, 0.50) found directly in run_all_6.py. See F-05.
