# ⚖️ LAYER 3: SUPREME JUDGE — FINAL VERDICT & SYNTHESIS ROUND

**Case:** Multi-agent adversarial audit of `Engine_1.py` and its simulated backtest architecture (`run_all_6.py`).

**Tribunal chain:** Layer 1 Attackers (GLM 5.2 · Sonnet 5) → Layer 2 Defenders (Codex 5.3 · Qwen 3.8) → **Layer 3 Supreme Judge (this verdict).**

**Disposition:** **7 patch orders issued** (5 unanimous confirmations + 2 new Layer 2 discoveries) · **2 claims struck** (LV-04, LV-05) · **prior walk-forward results VOID** pending revalidation.

---

## 1. UNANIMOUSLY CONFIRMED BUGS — PATCH REQUIRED

### 1.1 F-03 / BT-01 — Fee Model Mismatch — live charges 0.08% RT, backtest validates at 0.20% RT (2.5×)

**Severity:** CRITICAL · **Files:** run_all_6.py, Engine_1.py, six_strategy_engine.py

**Ruling.** UNANIMOUSLY CONFIRMED — triply corroborated against source and ledger. Live executes at 0.08% round-trip (ENGINE_FEE_PER_SIDE = 0.0004 × 2); the patched backtest validates at 0.20% RT (FEE = 0.0020, a "slippage" bump). Ledger proof: an ADAUSDT short flattened at entry booked pnl_pct = −0.0799999… — exactly 0.08% RT. The walk-forward gates (TWR/TROI/TDD) were calibrated to a cost regime that does not exist live; every PASS statistic is untrustworthy in production until re-run under one shared constant.

**Rationale.**
- run_all_6.py: FEE = 0.0020 (0.20% RT) vs Engine_1.py: ENGINE_FEE_RT = 0.0004 × 2 (0.08% RT) → 2.5× divergence.
- six_strategy_engine.py holds a THIRD copy of the same constant: FEE_PCT = 2 × env("ENGINE_FEE_PER_SIDE").
- Direction of skew: live is cheaper than assumed — validated thresholds are orphaned from live economics either way.
- The fix is single-sourcing, not re-tuning: one risk_config.py imported by all three modules, with a boot-time parity assert.

**Evidence (buggy code, verbatim):**
_run_all_6.py_
```python
# FEE CHANGE: 0.0015 -> 0.0020 (realistic slippage on 15m entries in volatile crypto)
CAP=5000; RSK=20; FEE=0.0020; TWR=40; TROI=20; TDD=30; MINTR=6; TP=5.0; TRA=0.8; MAXTR=50
```
_Engine_1.py_
```python
ENGINE_FEE_PER_SIDE = float(os.environ.get("ENGINE_FEE_PER_SIDE", "0.0004"))  # 0.04% per side
ENGINE_FEE_RT = ENGINE_FEE_PER_SIDE * 2  # 0.08% round-trip

# six_strategy_engine.py (the port Engine_1 actually trades through):
FEE_PCT = 2 * float(os.environ.get("ENGINE_FEE_PER_SIDE", "0.0004"))  # Round-trip fee
```

**Patch:**
_NEW risk_config.py — risk_config.py — create the single source of truth_
```python
# risk_config.py -- SINGLE SOURCE OF TRUTH for cost & risk constants.
# Imported by run_all_6.py (backtest), Engine_1.py and six_strategy_engine.py (live).
# Any future fee change is made HERE and here only.

FEE_RT = 0.0008          # round-trip cost: 0.04% per side x 2 -- MATCHES live execution
CAP    = 5000.0          # walk-forward starting equity
RSK    = 20.0            # USD risked per trade (1R)
TWR    = 40.0            # walk-forward gates
TROI   = 20.0
TDD    = 30.0
MINTR  = 6
TP     = 5.0
TRA    = 0.8
MAXTR  = 50

def assert_fee_parity():
    """Boot-time parity guard: refuses to start if any duplicate constant drifts."""
    import os
    env_fee = 2 * float(os.environ.get("ENGINE_FEE_PER_SIDE", "0.0004"))
    assert abs(env_fee - FEE_RT) < 1e-9, \
        f"FEE DRIFT: env={env_fee:.6f} vs shared FEE_RT={FEE_RT:.6f}"
```
_run_all_6.py — REPLACE the constant line with a hard import_
```python
from risk_config import FEE_RT as FEE, CAP, RSK, TWR, TROI, TDD, MINTR, TP, TRA, MAXTR

# DELETED: CAP=5000; RSK=20; FEE=0.0020; TWR=40; TROI=20; TDD=30; MINTR=6; TP=5.0; TRA=0.8; MAXTR=50
```
_Engine_1.py + six_strategy_engine.py — REPLACE both local fee derivations_
```python
# Engine_1.py
from risk_config import FEE_RT, assert_fee_parity
ENGINE_FEE_RT = FEE_RT              # was: ENGINE_FEE_PER_SIDE * 2
assert_fee_parity()                 # fail fast at boot on any drift

# six_strategy_engine.py
from risk_config import FEE_RT
FEE_PCT = FEE_RT                    # was: 2 * env("ENGINE_FEE_PER_SIDE")
```
> ⚠️ **REVALIDATION MANDATE — the walk-forward gates were calibrated at 0.20% RT. Re-run all six strategies under FEE_RT = 0.0008 before any PASS is accepted. No exception.**

---

### 1.2 BT-02 — Funding Sign Destroyed by abs() — shorts charged during positive funding

**Severity:** HIGH · **Files:** run_all_6.py

**Ruling.** UNANIMOUSLY CONFIRMED — verified verbatim. The comment states signed intent ("positions pay funding when sign(direction)==sign(funding)"); the code discards the sign with abs(avg_fr). Shorts are charged during positive funding when they should be PAID, converting income into expense and corrupting the label column the classifier trains on.

**Rationale.**
- abs(avg_fr) erases direction: positive funding should DEBIT longs and CREDIT shorts — the code debits both.
- The corrupted net/label columns feed LGBMClassifier training — a correctness bug upstream of every strategy.
- Funding exists only in the root patched runner — the colab copy and the live sim have no funding term at all (parity note below).

**Evidence (buggy code, verbatim):**
_run_all_6.py_
```python
# Funding cost: positions pay funding when sign(direction)==sign(funding)
# Positive funding = longs pay shorts; dr==1 means long
funding_bars = max(0, int(bh))
funding_cost = abs(avg_fr) / 32.0 * entry_price_approx * units_approx * funding_bars
net = net - funding_cost
```

**Patch:**
_run_all_6.py — REPLACE with signed funding (sign follows direction)_
```python
funding_bars = max(0, int(bh))
# SIGNED funding -- the comment always said "pay when sign matches"; the code must obey it.
# avg_fr > 0: longs PAY (cost +), shorts RECEIVE (cost -).
# dr == +1 (long) / -1 (short), so cost = avg_fr * dr is correct by construction.
funding_cost = (avg_fr * dr) / 32.0 * entry_price_approx * units_approx * funding_bars

if abs(funding_cost) > RSK:                                  # anomaly guard
    log(f" WARN funding anomaly on bar {idx}: {funding_cost:.3f} -> clamped")
    funding_cost = math.copysign(RSK, funding_cost)

net = net - funding_cost
```
> ⚠️ **PARITY RULING — a term that exists in only one engine is itself a parity break. Until the shared live sim (six_strategy_engine._sim_trade) implements this identical signed term, funding must be set to 0 in BOTH engines; the fix above is the template the live port must copy verbatim.**

---

### 1.3 F-04 — Retroactive Threshold Tuning — test-window lookahead in the MAXTR loop

**Severity:** HIGH · **Files:** run_all_6.py

**Ruling.** UNANIMOUSLY CONFIRMED. bp is re-selected INSIDE the test window using the trade counts of the full test-window prediction distribution (tp) — information that cannot exist at decision time. The MINTR fallback additionally re-lowers the cutoff to 0.50 to force a pass out of insufficient evidence. Both branches are non-causal and unreproducible in live deployment.

**Rationale.**
- for tc in np.arange(bp+0.04, 0.96, 0.04): re-picks the cutoff from the window's own trade counts — the definition of retroactive tuning.
- bdf2 = tp[tp['prob'] >= tc] uses the entire test-window probability distribution → future information.
- The 0.50 downgrade manufactures a PASS out of insufficient evidence; a window without MINTR trades must FAIL.

**Evidence (buggy code, verbatim):**
_run_all_6.py (walk-forward, inside the test window)_
```python
tp=pred(m,fcs,tdf); bdf=tp[tp['prob']>=bp].copy()
if len(bdf)<MINTR: bdf=tp[tp['prob']>=0.50].copy(); bp=0.50   # retroactive downgrade
if len(bdf)>MAXTR:
    for tc in np.arange(bp+0.04,0.96,0.04):                    # retroactive re-tuning
        bdf2=tp[tp['prob']>=tc]
        if MINTR<=len(bdf2)<=MAXTR: bdf=bdf2.copy(); bp=tc; break
```

**Patch:**
_run_all_6.py — REPLACE with strictly causal threshold application_
```python
bp=best_thresh(vp)                # bp frozen on the VALIDATION slice -- never touched again
tp=pred(m,fcs,tdf)
bdf=tp[tp['prob']>=bp].copy()      # strictly causal: decision at bar i uses data <= bar i

if len(bdf) < MINTR:
    # NO threshold downgrade. Insufficient evidence => the window FAILS.
    log(f" W{wi+1}: {len(bdf)} trades < MINTR={MINTR} -> FAIL (insufficient evidence)")
    res.append({**win_meta, 'bp': bp, 'passed': False,
                'verdict': 'FAIL:INSUFFICIENT_TRADES'})
    continue

if len(bdf) > MAXTR:
    # Capacity cap applied CHRONOLOGICALLY (first-come, first-served),
    # NEVER by re-sorting on test-window probability. Causal => live-reproducible.
    bdf = bdf.iloc[:MAXTR]

# ... unchanged: win-rate / ROI / MtM-DD computation on bdf ...
```
> ⚠️ **F-05 CLOSURE — persist bp (and a code-path flag) per window in all_6_results.json, so the live engine can load thresholds ONLY from the walk-forward artifact. Live threshold provenance inside six_strategy_engine remains unproven and must be audited against that artifact.**

---

### 1.4 F-06 — Exception Swallowing — silent ledger loss and blind engine boot

**Severity:** HIGH · **Files:** Engine_1.py, patch_engine.py

**Ruling.** UNANIMOUSLY CONFIRMED. The engine header alone carries a dozen "Swallowed exception" print sites; Layer 2 verified patch_engine.py exposes the ledger-of-record writer save_history as except Exception as e: pass. Silent loss of the trade ledger — the audit's own ground truth — and degraded blind boots are both live and undetected under this regime.

**Rationale.**
- A blank pass on save_history means ledger truncation happens silently, mid-capital-activity.
- The startup path swallows boot failures, allowing a degraded engine to trade without anyone knowing.
- Rule adopted by this Court: except Exception: pass is BANNED on order, stop, persistence and boot paths.

**Evidence (buggy code, verbatim):**
_Engine_1.py (repeated ~dozen times) / patch_engine.py (ledger of record)_
```python
# Engine_1.py -- startup & plumbing
except Exception as e:
    print(f"[WARN] Swallowed exception: {e}")

# patch_engine.py -- save_history, the ledger persistence path (quoted by Qwen 3.8)
except Exception as e:
    pass
```

**Patch:**
_NEW engine_components/fail_loud.py — fail_loud.py — the only sanctioned error path for capital code_
```python
# engine_components/fail_loud.py -- used by Engine_1.py and patch_engine.py
import logging
import traceback
from pathlib import Path

log = logging.getLogger("engine.critical")
HALT_FLAG = Path(__file__).resolve().parent.parent / "HALT_FLAG"

def fail_loud(context: str, exc: Exception, halt: bool = True) -> None:
    """Capital paths must NEVER swallow. Log, persist halt, re-raise."""
    log.critical("FATAL [%s] %r\n%s", context, exc, traceback.format_exc())
    if halt:
        HALT_FLAG.write_text(f"{context}: {exc}")
        raise exc
```
_Engine_1.py — REPLACE the swallow-pattern on boot_
```python
# Engine_1.py -- startup path
try:
    ... engine boot ...
except Exception as e:
    fail_loud("engine_startup", e, halt=True)
    # was: print(f"[WARN] Swallowed exception: {e}")
```
_patch_engine.py — REPLACE the blank pass on the ledger write_
```python
# patch_engine.py -- save_history (ledger of record)
def save_history(rows):
    try:
        ... write ledger rows ...
    except Exception as e:
        # was: pass  -- silent ledger loss is now a capital-path violation
        fail_loud("ledger_write", e, halt=True)
```
> ⚠️ **GOVERNOR WIRING — the Risk Governor must read HALT_FLAG and block all new entries while it exists. This couples directly to the BROKER_SYNC halt patch (2.2).**

---

### 1.5 F-01 — Strategy Duplication — live trades a divergent hand-port, backtest silently falls back

**Severity:** CRITICAL · **Files:** Engine_1.py, six_strategy_engine.py, run_all_6.py

**Ruling.** UNANIMOUSLY CONFIRMED and ESCALATED. The live engine imports a hand-ported duplicate (six_strategy_engine) whose sim block is labelled "exact copy from run_all_6.py" — a claim falsified by its own source (different ATR, different fees, extra features, changed generator bounds). Meanwhile run_all_6.py silently falls back to its own local strategy copies when signals_shared is missing. Two engines, four file copies, one supposed strategy.

**Rationale.**
- six_strategy_engine.py self-describes as a port; its "exact copy" label is disproven by the code it wraps (see finding 2.1).
- try/except ImportError fallback (F-02) silently runs unvalidated local definitions — a hard import must replace it.
- Single-sourcing ruling: BOTH engines import signals_shared.STRAT_MAP; a boot-time parity assert fails the engine rather than degrading.

**Evidence (buggy code, verbatim):**
_Engine_1.py + run_all_6.py_
```python
# Engine_1.py -- live engine delegates to a hand-ported duplicate
# Six Strategy Engine (ports run_all_6.py verified strategies)
from six_strategy_engine import LiveSixStrategyPredictor, STRATEGY_NAMES as SIX_STRAT_NAMES

# run_all_6.py -- silent fallback to local copies
try:
    from signals_shared import STRAT_MAP as _SHARED_STRAT_MAP
    _USE_SHARED = True
except ImportError:
    _USE_SHARED = False        # silently trades unvalidated local copies (F-02)
```

**Patch:**
_Engine_1.py — REPLACE the duplicate-module import; add boot-time parity guard_
```python
# Engine_1.py -- single-sourced live strategies
from signals_shared import STRAT_MAP, SIX_STRAT_NAMES

# Hard parity guard at boot (fails the engine; never degrades silently):
assert list(STRAT_MAP) == list(SIX_STRAT_NAMES), \
    "STRAT_MAP drifted from live strategy names -- refusing to start"

# DELETED: from six_strategy_engine import LiveSixStrategyPredictor, ...
# (six_strategy_engine's private S1..S6 copies are removed in the same commit)
```
_run_all_6.py — REPLACE the try/except fallback with a hard import_
```python
# run_all_6.py -- ImportError at boot == loud failure (F-02 resolved)
from signals_shared import STRAT_MAP

# DELETED: the try/except ImportError block AND the entire local
# make_signal_s1..s6 fallback definitions below it.
```
> ⚠️ **SCOPE — delete the vestigial inline strategy branches in live_unified_predictor.py in the same commit. Duplication is the vulnerability; one module per strategy, everywhere.**

---

## 2. NEW LAYER 2 DISCOVERIES (QWEN 3.8) — PATCH REQUIRED

### 2.1 NEW · QWEN 3.8 — ATR Math Divergence — live True-Range vs backtest (High − Low) scales every feature

**Severity:** CRITICAL · **Files:** six_strategy_engine.py, run_all_6.py, signals_shared.py

**Ruling.** NEW — discovered by Qwen 3.8, missed by both Layer 1 models. The live port computes True-Range ATR (including previous-close gaps) while every backtest version uses (High − Low). True Range ≥ High−Low pointwise, so live ATR is systematically larger → wider live stops, smaller position size, and every ATR-normalized feature (p8, p21, p50, mc) is computed on a different scale than the training data. Backtest→live expectancy is invalid before fees are even discussed.

**Rationale.**
- TR ≥ (H−L) always → live stops wider and units = RSK/ATR smaller than modeled.
- p8/p21/p50/mc are normalized by ATR and feed the ML ensemble → full distributional shift on live inputs.
- The live comment claims parity ("must match run_all_6.py exactly") — the code breaks the contract.
- The repo's 174/174 parity artifact (divergence 0.0) is falsified by this finding and must be archived as invalid.

**Evidence (buggy code, verbatim):**
_six_strategy_engine.py (live featurize) vs run_all_6.py (backtest featurize)_
```python
# six_strategy_engine.py -- LIVE (comment asserts parity; code breaks it)
prev_close = df['Close'].shift(1)
tr1 = df['High'] - df['Low']
tr2 = (df['High'] - prev_close).abs()
tr3 = (df['Low'] - prev_close).abs()
tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
df["atr"] = tr.rolling(14, min_periods=1).mean()

# run_all_6.py -- BACKTEST (every version in the repo)
df["atr"]=(df["High"]-df["Low"]).rolling(14,min_periods=1).mean()
```

**Patch:**
_signals_shared.py — ADD the canonical ATR — the only definition in the codebase_
```python
# signals_shared.py -- canonical True-Range ATR
def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """True-Range ATR. THE ONLY ATR definition in the codebase."""
    prev_close = df["Close"].shift(1)
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev_close).abs(),
        (df["Low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=1).mean()
```
_run_all_6.py — REPLACE the (High − Low) computation_
```python
# run_all_6.py -- featurize()
from signals_shared import atr
...
df["atr"] = atr(df)
# DELETED: df["atr"]=(df["High"]-df["Low"]).rolling(14,min_periods=1).mean()
```
_six_strategy_engine.py — REPLACE the local True-Range block (delete it entirely)_
```python
# six_strategy_engine.py -- featurize()
from signals_shared import atr
...
df["atr"] = atr(df)
# DELETED: the six-line local True-Range block (prev_close/tr1/tr2/tr3/tr/rolling)
```
> ⚠️ **REVALIDATION MANDATE — True-Range is adopted as canonical (choice of definition is secondary to singularity). Every walk-forward result predating this patch is VOID until regenerated, because backtest ATR, stops and p-features all shift scale.**

---

### 2.2 NEW · QWEN 3.8 — BROKER_SYNC Unbounded Loss — reconciliation realized 8.75× the modeled 1-ATR stop

**Severity:** CRITICAL · **Files:** Engine_1.py, Engine_1_trade_logs.json

**Ruling.** NEW — empirically proven by Qwen 3.8 against the ledger: a trade passed through its registered stop and was flattened by BROKER_SYNC at ≈8.75× the intended 1-ATR loss. The modeled worst case is 1R; reconciliation realized 8.75R. Other ledger rows exit exactly at exec_sl — so stops sometimes exist and sometimes do not. Whatever the code-level cause (stop never ACKed, or sync racing the stop), the failure mode is unbounded loss on the path designed to define risk.

**Rationale.**
- Ledger row: BROKER_SYNC exit ≈ 8.75× the registered 1-ATR stop distance — the tail is unbounded, not just wider.
- Reconciliation must PROVE broker-side stop existence before flattening; a missing stop ⇒ flatten AND halt the governor.
- Hard loss invariant before any ledger write: realized ≥ −(1R + fees + 1 tick), else reject the row and halt.
- Entry-commit rule (F-12/U-07): a fill is not "committed" until the broker ACKs the protective stop.

**Evidence (buggy code, verbatim):**
_Engine_1_trade_logs.json (ledger ground truth) + patch_engine.py_
```python
# Ledger evidence quoted by Qwen 3.8:
#   trade exited reason="BROKER_SYNC" at ~8.75x the registered 1-ATR stop loss
#   while other rows exit exactly at exec_sl (e.g. 0.175 == exec_sl 0.175),
#   proving stops are sometimes placed/honored and sometimes not.
#
# patch_engine.py -- the persistence writer behind that ledger:
#   except Exception as e:
#       pass
```

**Patch:**
_Engine_1.py — Engine1TradeTracker.reconcile_open_trade — REPLACE the flatten routine_
```python
# Engine_1.py -- Engine1TradeTracker reconciliation. REPLACE the flatten routine.

def reconcile_open_trade(self, trade: dict) -> None:
    """BROKER_SYNC path. Modeled worst case is 1R; the ledger must never exceed it."""
    stop_id = trade.get("broker_stop_id")

    if not stop_id:
        # Stop was never ACKed by the broker -- the protection never existed.
        self.flatten(trade, reason="BROKER_SYNC_NO_STOP_ACK")
        self.governor.halt("stop_never_registered")       # HALT: block all new entries
        log.critical("SYNC: flattened with NO broker stop ack trade=%s", trade["id"])
        return

    try:
        stop = self.broker.get_order(stop_id)             # verify server-side existence
    except Exception as e:
        fail_loud("broker_stop_query", e, halt=True)

    if stop is None or stop.get("status") not in ("NEW", "WORKING"):
        # Registered stop missing server-side -> modeled protection does not exist.
        self.flatten(trade, reason="BROKER_SYNC_STOP_MISSING")
        self.governor.halt("stop_missing")
        return

    self.flatten(trade, reason="BROKER_SYNC")

    # HARD LOSS INVARIANT -- enforced BEFORE any ledger row is written:
    one_r    = trade["units"] * trade["atr_at_entry"]     # 1R == 1 ATR (ledger-proven)
    realized = trade["pnl_usd"]
    if realized < -(one_r + trade["fees_usd"] + trade["tick_value"]):
        reject_ledger_row(trade, "sync_loss_breach")      # never write a silent breach
        self.governor.halt("sync_loss_breach")            # an 8.75x event MUST halt the engine
        log.critical("SYNC LOSS BREACH trade=%s realized=%.4f one_r=%.4f",
                     trade["id"], realized, one_r)
```
> ⚠️ **ENTRY-COMMIT RULE (closes F-12/U-07) — place the protective stop BEFORE the entry fill, require a broker ACK on both, and refuse to mark the position "committed" until both ACKs exist. This makes the residual UNVERIFIED code-level ordering question moot: no stop ACK ⇒ no committed position ⇒ no unbounded path.**

---

## 3. UNANIMOUSLY REJECTED — DO NOT PATCH

### LV-04 — Asymmetric SL/TP Tick Rounding (systematic adverse drag)

**Layer 1 claim.** Sonnet 5 claimed exec_sl/exec_tp tick rounding is asymmetric — SL always rounds away from entry, TP always rounds toward entry — producing systematic adverse drag on every trade.

**Disposition: REJECTED.** REJECTED — mechanism disproven by the ledger. The quantization is standard nearest-tick rounding and its direction varies trade-to-trade: ADA short #5 SL rounds TIGHTER (favorable), SUI short #4 TP rounds LOOSER (favorable), etc. Sonnet extrapolated a systematic skew from a single trade where both deltas happened to be adverse. The actual process is unbiased ±0.5-tick noise.

**Ledger evidence:**
- ADA #1 SHORT: SL 0.17488571 → 0.1749 (adverse) · TP 0.17197143 → 0.1720 (adverse) — the single trade the claim was built on.
- ADA #5 SHORT: SL 0.17664286 → 0.1766 (TIGHTER — favorable) · TP 0.17218571 → 0.1722 (adverse).
- ADA #3 SHORT: SL 0.17495714 → 0.1750 (adverse) · TP 0.17161429 → 0.1716 (LOOSER — favorable).
- SUI #4 SHORT: SL 0.65481429 → 0.6548 (favorable) · TP 0.64452857 → 0.6445 (favorable).
- TRX #6 LONG: SL 0.33163540 → 0.33163 (adverse) · TP 0.33400714 → 0.33401 (favorable).

> 🚫 **No patch is issued.** Any PR carrying a "fix" for these claims must be reverted.

---

### LV-05 — Dual PnL Accounting / Double-Counting (live_pnl_* vs pnl_*)

**Layer 1 claim.** Sonnet 5 claimed the ledger's twin PnL fields (live_pnl_usd vs pnl_usd, plus closing_dispatched) imply double-counting of PnL on the capital books.

**Disposition: REJECTED.** REJECTED — misread of the schema. live_pnl_usd is the last observed unrealized mark-to-market snapshot while the trade is open; pnl_usd is the realized PnL at close; closing_dispatched is a close-dispatch flag present only on broker-ACKed SL exits and absent on BROKER_SYNC closes. No double-counting is evidenced anywhere in the ledger. Sonnet itself labelled this INFERRED — it must not survive to Layer 3 as a finding.

**Ledger evidence:**
- live_pnl_usd −11.75 on the final tick vs realized pnl_usd −4.01 at reconciliation — a snapshot, not a second book.
- closing_dispatched: true appears ONLY on broker-acknowledged SL exits; absent on BROKER_SYNC closes.
- Carried as a SCHEMA NOTE (float residue on live_pnl_usd belongs to the Decimal-at-the-Governor work item) — not a patch.

> 🚫 **No patch is issued.** Any PR carrying a "fix" for these claims must be reverted.

---

## 4. FULL PATCH BUNDLE — SINGLE APPLICATION ORDER

Apply in order: `risk_config.py` (new) → `fail_loud.py` (new) → `signals_shared.py` (ATR) → `run_all_6.py` → `Engine_1.py` → `six_strategy_engine.py` → `patch_engine.py`.

### 4.1 NEW FILE: risk_config.py

```python
# risk_config.py -- SINGLE SOURCE OF TRUTH for cost & risk constants.
# Imported by run_all_6.py (backtest), Engine_1.py and six_strategy_engine.py (live).
# Any future fee change is made HERE and here only.

FEE_RT = 0.0008          # round-trip cost: 0.04% per side x 2 -- MATCHES live execution
CAP    = 5000.0          # walk-forward starting equity
RSK    = 20.0            # USD risked per trade (1R)
TWR    = 40.0            # walk-forward gates
TROI   = 20.0
TDD    = 30.0
MINTR  = 6
TP     = 5.0
TRA    = 0.8
MAXTR  = 50

def assert_fee_parity():
    """Boot-time parity guard: refuses to start if any duplicate constant drifts."""
    import os
    env_fee = 2 * float(os.environ.get("ENGINE_FEE_PER_SIDE", "0.0004"))
    assert abs(env_fee - FEE_RT) < 1e-9, \
        f"FEE DRIFT: env={env_fee:.6f} vs shared FEE_RT={FEE_RT:.6f}"
```

### 4.2 NEW FILE: engine_components/fail_loud.py

```python
# engine_components/fail_loud.py -- used by Engine_1.py and patch_engine.py
import logging
import traceback
from pathlib import Path

log = logging.getLogger("engine.critical")
HALT_FLAG = Path(__file__).resolve().parent.parent / "HALT_FLAG"

def fail_loud(context: str, exc: Exception, halt: bool = True) -> None:
    """Capital paths must NEVER swallow. Log, persist halt, re-raise."""
    log.critical("FATAL [%s] %r\n%s", context, exc, traceback.format_exc())
    if halt:
        HALT_FLAG.write_text(f"{context}: {exc}")
        raise exc
```

### 4.3 signals_shared.py — canonical ATR

```python
# signals_shared.py -- canonical True-Range ATR
def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """True-Range ATR. THE ONLY ATR definition in the codebase."""
    prev_close = df["Close"].shift(1)
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev_close).abs(),
        (df["Low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=1).mean()
```

### 4.4 run_all_6.py — all replacements

_REPLACE the constant line with a hard import_
```python
from risk_config import FEE_RT as FEE, CAP, RSK, TWR, TROI, TDD, MINTR, TP, TRA, MAXTR

# DELETED: CAP=5000; RSK=20; FEE=0.0020; TWR=40; TROI=20; TDD=30; MINTR=6; TP=5.0; TRA=0.8; MAXTR=50
```
_REPLACE with signed funding (sign follows direction)_
```python
funding_bars = max(0, int(bh))
# SIGNED funding -- the comment always said "pay when sign matches"; the code must obey it.
# avg_fr > 0: longs PAY (cost +), shorts RECEIVE (cost -).
# dr == +1 (long) / -1 (short), so cost = avg_fr * dr is correct by construction.
funding_cost = (avg_fr * dr) / 32.0 * entry_price_approx * units_approx * funding_bars

if abs(funding_cost) > RSK:                                  # anomaly guard
    log(f" WARN funding anomaly on bar {idx}: {funding_cost:.3f} -> clamped")
    funding_cost = math.copysign(RSK, funding_cost)

net = net - funding_cost
```
_REPLACE with strictly causal threshold application_
```python
bp=best_thresh(vp)                # bp frozen on the VALIDATION slice -- never touched again
tp=pred(m,fcs,tdf)
bdf=tp[tp['prob']>=bp].copy()      # strictly causal: decision at bar i uses data <= bar i

if len(bdf) < MINTR:
    # NO threshold downgrade. Insufficient evidence => the window FAILS.
    log(f" W{wi+1}: {len(bdf)} trades < MINTR={MINTR} -> FAIL (insufficient evidence)")
    res.append({**win_meta, 'bp': bp, 'passed': False,
                'verdict': 'FAIL:INSUFFICIENT_TRADES'})
    continue

if len(bdf) > MAXTR:
    # Capacity cap applied CHRONOLOGICALLY (first-come, first-served),
    # NEVER by re-sorting on test-window probability. Causal => live-reproducible.
    bdf = bdf.iloc[:MAXTR]

# ... unchanged: win-rate / ROI / MtM-DD computation on bdf ...
```
_REPLACE the try/except fallback with a hard import_
```python
# run_all_6.py -- ImportError at boot == loud failure (F-02 resolved)
from signals_shared import STRAT_MAP

# DELETED: the try/except ImportError block AND the entire local
# make_signal_s1..s6 fallback definitions below it.
```
_REPLACE the (High − Low) computation_
```python
# run_all_6.py -- featurize()
from signals_shared import atr
...
df["atr"] = atr(df)
# DELETED: df["atr"]=(df["High"]-df["Low"]).rolling(14,min_periods=1).mean()
```

### 4.5 Engine_1.py — all replacements

_REPLACE both local fee derivations_
```python
# Engine_1.py
from risk_config import FEE_RT, assert_fee_parity
ENGINE_FEE_RT = FEE_RT              # was: ENGINE_FEE_PER_SIDE * 2
assert_fee_parity()                 # fail fast at boot on any drift

# six_strategy_engine.py
from risk_config import FEE_RT
FEE_PCT = FEE_RT                    # was: 2 * env("ENGINE_FEE_PER_SIDE")
```
_REPLACE the swallow-pattern on boot_
```python
# Engine_1.py -- startup path
try:
    ... engine boot ...
except Exception as e:
    fail_loud("engine_startup", e, halt=True)
    # was: print(f"[WARN] Swallowed exception: {e}")
```
_REPLACE the duplicate-module import; add boot-time parity guard_
```python
# Engine_1.py -- single-sourced live strategies
from signals_shared import STRAT_MAP, SIX_STRAT_NAMES

# Hard parity guard at boot (fails the engine; never degrades silently):
assert list(STRAT_MAP) == list(SIX_STRAT_NAMES), \
    "STRAT_MAP drifted from live strategy names -- refusing to start"

# DELETED: from six_strategy_engine import LiveSixStrategyPredictor, ...
# (six_strategy_engine's private S1..S6 copies are removed in the same commit)
```
_Engine1TradeTracker.reconcile_open_trade — REPLACE the flatten routine_
```python
# Engine_1.py -- Engine1TradeTracker reconciliation. REPLACE the flatten routine.

def reconcile_open_trade(self, trade: dict) -> None:
    """BROKER_SYNC path. Modeled worst case is 1R; the ledger must never exceed it."""
    stop_id = trade.get("broker_stop_id")

    if not stop_id:
        # Stop was never ACKed by the broker -- the protection never existed.
        self.flatten(trade, reason="BROKER_SYNC_NO_STOP_ACK")
        self.governor.halt("stop_never_registered")       # HALT: block all new entries
        log.critical("SYNC: flattened with NO broker stop ack trade=%s", trade["id"])
        return

    try:
        stop = self.broker.get_order(stop_id)             # verify server-side existence
    except Exception as e:
        fail_loud("broker_stop_query", e, halt=True)

    if stop is None or stop.get("status") not in ("NEW", "WORKING"):
        # Registered stop missing server-side -> modeled protection does not exist.
        self.flatten(trade, reason="BROKER_SYNC_STOP_MISSING")
        self.governor.halt("stop_missing")
        return

    self.flatten(trade, reason="BROKER_SYNC")

    # HARD LOSS INVARIANT -- enforced BEFORE any ledger row is written:
    one_r    = trade["units"] * trade["atr_at_entry"]     # 1R == 1 ATR (ledger-proven)
    realized = trade["pnl_usd"]
    if realized < -(one_r + trade["fees_usd"] + trade["tick_value"]):
        reject_ledger_row(trade, "sync_loss_breach")      # never write a silent breach
        self.governor.halt("sync_loss_breach")            # an 8.75x event MUST halt the engine
        log.critical("SYNC LOSS BREACH trade=%s realized=%.4f one_r=%.4f",
                     trade["id"], realized, one_r)
```

### 4.6 six_strategy_engine.py + patch_engine.py — all replacements

_patch_engine.py — REPLACE the blank pass on the ledger write_
```python
# patch_engine.py -- save_history (ledger of record)
def save_history(rows):
    try:
        ... write ledger rows ...
    except Exception as e:
        # was: pass  -- silent ledger loss is now a capital-path violation
        fail_loud("ledger_write", e, halt=True)
```
_six_strategy_engine.py — REPLACE the local True-Range block (delete it entirely)_
```python
# six_strategy_engine.py -- featurize()
from signals_shared import atr
...
df["atr"] = atr(df)
# DELETED: the six-line local True-Range block (prev_close/tr1/tr2/tr3/tr/rolling)
```

---

## 5. REVALIDATION MANDATE

1. Apply patches 1.1 → 2.2 in order; delete duplicated modules in the same commit (risk_config.py and fail_loud.py are NEW files).
2. Re-run the full 20-window walk-forward under FEE_RT = 0.0008, True-Range ATR, signed funding, and frozen out-of-sample thresholds.
3. Regenerate the parity test comparing the ACTUAL live path (signals_shared + shared sim) against run_all_6.py on identical data; archive the 174/174 artifact as invalid.
4. Re-enable fail-fast window abort (no silent PASS accumulation) and persist bp per window in all_6_results.json.
5. Only after 1–4: re-certify deployment or hold live capital.

---

## 6. ADJOURNED ITEMS (unverifiable at Layer 2 — carried forward, NOT cleared)

- **F-10 / U-03** — WebSocket reconnect bounds — unbounded retry loop unverifiable beyond the retrievable header.
- **U-01 / U-02** — Lock mixing & task cancellation discipline — code lives in the unretrievable Engine1TradeTracker body.
- **U-10** — Float equality on price comparisons — needs full-file access to confirm or strike.
- **F-12 / U-07** — Code-level stop-registration ordering — now MOOTED by the ACK-before-commit rule in patch 2.2.
- **TP-16** — trail_act == 1.0 on every ledger row vs td = TP*atr (5-ATR) activation in the backtest — resolve semantics against the sim.

---

_Court is adjourned. The system under audit is NOT deployable as validated until the mandate above is discharged._ ⚖️
