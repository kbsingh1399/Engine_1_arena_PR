# 🛡️ Layer 2 Defense Audit Report

**Scope & method.** Every Layer 1 finding (GLM 5.2: F-01…F-12; Sonnet 5: LV-01…LV-07, BT-01…BT-06, U-01…U-10) was re-litigated against primary sources fetched directly from the repository: `run_all_6.py` (root, 22,921 bytes — **retrieved in full**), `Engine_1.py` (264,003 bytes — first ~210 lines retrievable; deep body exceeds single-fetch window, same constraint both Layer 1 models hit), `colab_strategies/run_all_6.py` (original "MASTER RUNNER"), `six_strategy_engine.py` (root — the module `Engine_1.py` actually imports), `live_unified_predictor.py` (second, legacy live lineage), `signals_shared.py`, `patch_engine.py`, `drift_dryrun.py`, and the live ledger `Engine_1_trade_logs.json` (empirical ground truth). Verdict up front: **neither Layer 1 report contains a fabricated finding** — every claim maps to real code or real ledger data — but **five claims are mechanically wrong or materially overstated**, and cross-validation uncovered **three new divergences more severe than anything Layer 1 flagged**, including one that falsifies the repo's own `parity_test_results.json` (174/174, divergence 0.0) artifact.

---

## 1. Verified True Positives

### TP-1 — F-03 (GLM) / BT-01 (Sonnet): Fee-model parity break, 2.5×. **VERIFIED — triply corroborated, including by the live ledger.**

Backtest (root `run_all_6.py`, verified verbatim):
```python
CAP=5000; RSK=20; FEE=0.0020; TWR=40; TROI=20; TDD=30; ...
# FEE CHANGE: 0.0015 -> 0.0020 (realistic slippage on 15m entries in volatile crypto)
```
Live config (`Engine_1.py`, header section ≈ lines 178–180 of the retrievable window):
```python
ENGINE_FEE_PER_SIDE = float(os.environ.get("ENGINE_FEE_PER_SIDE", "0.0004"))  # 0.04% per side
ENGINE_FEE_RT = ENGINE_FEE_PER_SIDE * 2  # 0.08% round-trip
```
Live simulator (`six_strategy_engine.py`, the module Engine_1 imports):
```python
FEE_PCT = 2 * float(os.environ.get("ENGINE_FEE_PER_SIDE", "0.0004"))  # Round-trip fee
...
fees = units * entry * FEE_PCT / 2.0 + units * abs(ep) * FEE_PCT / 2.0
```
**Ledger proof** (`Engine_1_trade_logs.json`): three trades closed by `BROKER_SYNC` at *exactly the entry price* book precisely −0.08% RT — e.g. ADAUSDT short, entry 0.1744 / exit 0.1744, `pnl_usd: -4.01496704` on notional 28,777 × 0.1744 = $5,018.7 → 0.0800% exactly; `pnl_pct: -0.07999999999999999`. The walk-forward gates (`TWR=40, TROI=20, TDD=30`) were validated under 0.20% RT drag; live executes at 0.08% RT. **0.20 / 0.08 = 2.5×, confirmed.** One correction to both reports: the skew makes live *cheaper* than the backtest assumed (live PnL is not under-attributed by fees); the damage is that every validated threshold and expectancy figure is calibrated to a cost regime that does not exist live. Parity verdict stands.

### TP-2 — F-01 (GLM): Live engine trades from a manually-ported duplicate, not a shared import. **VERIFIED — and ESCALATED: the port demonstrably diverges from every backtest version in the repo.**

`Engine_1.py` (retrievable header, ≈ line 108):
```python
# Six Strategy Engine (ports run_all_6.py verified strategies)
from six_strategy_engine import LiveSixStrategyPredictor, STRATEGY_NAMES as SIX_STRAT_NAMES
```
`six_strategy_engine.py` self-describes as a port: *"Ports the exact logic from colab_strategies/run_all_6.py into a live streaming predictor"*, and its sim block is labelled *"Numba Trade Simulation (exact copy from run_all_6.py)"*. **Both claims are falsified by the source:**

**(a) NEW — ATR definition mismatch (missed by both Layer 1 models; GLM had listed ATR parity as UNVERIFIED).** `six_strategy_engine.py::featurize`:
```python
# PARITY FIX: True Range / ATR must match run_all_6.py exactly
prev_close = df['Close'].shift(1)
tr1 = df['High'] - df['Low']
tr2 = (df['High'] - prev_close).abs()
tr3 = (df['Low'] - prev_close).abs()
tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
df["atr"] = tr.rolling(14, min_periods=1).mean()
```
vs **every** backtest version in the repo — root patched `run_all_6.py` *and* `colab_strategies/run_all_6.py`:
```python
df["atr"]=(df["High"]-df["Low"]).rolling(14,min_periods=1).mean()
```
The comment asserts parity; the code breaks it. True Range ≥ High−Low always, so live ATR is systematically larger → wider live stops (`sl_dist = 1×ATR`), smaller position sizes (`units = RSK/ATR`), and **every ATR-normalized feature fed to the ML ensemble (`p8`, `p21`, `p50`, `mc`) is computed on a different scale than the features the models were trained on**. This alone invalidates backtest→live expectancy before fees are even discussed.

**(b)** The port prices fees from the live env var (`FEE_PCT = 2×ENGINE_FEE_PER_SIDE = 0.0008`), not the backtest constant (`FEE=0.0020` patched / `0.0015` colab) — so even the port's *own* sim disagrees with the walk-forward numbers it claims to replicate. **(c)** The port adds features absent from the backtest (`ef_slope`, "used by S2/S3 filter"), changes generator bounds (`while i < n - 100` vs `while i<n`), drops the funding-cost adjustment and the MAE/MtM-DD accounting the patched runner added, and pads RSI (`fillna(50.0)`). **(d)** Repository forensics confirm the drift culture GLM alleged: there are **four** copies of `run_all_6.py` (root patched 22.9 KB; `colab_strategies/run_all_6.py` 19.6 KB; `colab_strategies/run_all_6_patched.py` 20.7 KB; nested `colab_strategies/colab_strategies/run_all_6.py` 20.9 KB) with differing S2/S3 thresholds (`p8<-0.25` vs `p8<-0.20` vs `p8<-0.10`) and differing fee constants, plus size-divergent duplicate pairs of `binance_broker.py` (root 40,990 B vs `engine_components/` 47,486 B) and `coinglass_scraper.py` (103,427 B vs 99,308 B). F-01 is a true positive and is **under-stated**.

### TP-3 — F-02 (GLM): Silent `signals_shared` ImportError fallback. **VERIFIED verbatim, and the identical anti-pattern is worse in live code.**

Root `run_all_6.py`:
```python
try:
    from signals_shared import STRAT_MAP as _SHARED_STRAT_MAP
    _USE_SHARED = True
except ImportError:
    _USE_SHARED = False  # Fallback: local definitions used (see below)
```
`live_unified_predictor.py` (live lineage, legacy):
```python
try:
    from signals_shared import STRAT_MAP as _LIVE_SIGNAL_MAP
except ImportError:
    _LIVE_SIGNAL_MAP = {}  # Graceful degradation: ML gate still active, signal pre-filter skipped
```
Confirmed: if the import fails, the backtest silently runs possibly-stale local `make_signal_sN` copies, and the live predictor silently drops its signal pre-filter entirely. Also confirmed the second half of F-02: the walk-forward result schema persisted to `all_6_results.json` is `{'w','start','end','tr','wins','wr','pnl','roi','dd','mtm_dd','passed','verdict'}` — **no field records which code path or threshold produced the numbers**.

### TP-4 — LV-01 (Sonnet): `BROKER_SYNC` realizes losses far beyond the registered stop. **VERIFIED at the behavioral level from the live ledger; one overclaim corrected (see §2).**

`Engine_1_trade_logs.json`, trade `S4_Mean_Reversion_ADAUSDT_SHORT_1787063402160750200` — every figure Sonnet cited reproduces exactly:
```json
"entry_price": 0.1759, "sl": 0.17664285714285716, "exec_sl": 0.1766,
"atr": 0.0007428571428571423, "sl_dist": 0.0007428571428571562, "units": 20965.0,
"exit_price": 0.18240000000000003, "exit_reason": "BROKER_SYNC",
"pnl_usd": -24.20107008, "pnl_pct": -0.6562568703598827
```
Adverse excursion 0.1824/0.1759−1 = **+3.70% = 8.75× the 1-ATR stop** (Sonnet's "~9×" ✓). A stop registered at 0.1766 implies max loss ≈ units×(sl−entry) ≈ −$15.6; realized −$24.20 is ~1.55× the theoretical worst case. Backtest `sim()` caps a short the instant `h[j] >= cs` — this outcome is unreachable in the validated model. Corroborating context in the same ledger: other trades *do* exit at their stops (`S1_Liquidation_ADAUSDT...1932` exits at 0.175 == `exec_sl` 0.175; SUIUSDT exits 0.6549 vs `exec_sl` 0.6548), so stops are sometimes placed and honored — the precise code-level failure (stop never reached the exchange, vs. reconciliation racing the stop) lives in the unretrievable `Engine1TradeTracker` body, but the **unbounded-loss failure mode is empirically real**. Also relevant: `patch_engine.py` exposes the tracker's `save_history` writer as `except Exception as e: pass` — the ledger-of-record persistence path swallows all exceptions, the exact idiom Sonnet's LV-03 warned about, now verified on a capital-adjacent path rather than merely inferred.

### TP-5 — BT-02 (Sonnet): Funding charged with `abs(fr)`. **VERIFIED verbatim.**

Root `run_all_6.py`:
```python
# Funding cost: positions pay funding when sign(direction)==sign(funding)
# Positive funding = longs pay shorts; dr==1 means long
funding_bars = max(0, int(bh))
funding_cost = abs(avg_fr) / 32.0 * entry_price_approx * units_approx * funding_bars
net = net - funding_cost
```
The comment states signed intent; the code discards sign — shorts are charged during positive funding when they should be paid, converting income into expense and corrupting the `label` column the classifier trains on. Additionally confirmed: funding exists **only** in the root patched runner — `colab_strategies/run_all_6.py` has no funding term, `six_strategy_engine.py::_sim_trade` has none, and the live ledger has no funding field — so the engines disagree on whether funding exists at all. F-07 (GLM) is also corroborated in part: the funding line uses `units_approx`/`entry_price_approx` while `sim()` uses exact `u=RSK/atr` and `entry` — two sizing sources in one file.

### TP-6 — BT-03 (Sonnet): S2 "CVD_Momentum" contains no CVD. **Fact VERIFIED across all three signal versions — severity reclassified (see §2).**

Root patched `run_all_6.py`:
```python
def make_signal_s2(df):
    """S2: Deep Pure Trend (Replaced CVD logic)
    Now: extremely deep trend pullback (p8 < -0.20) to offset fee"""
    ...
    out[(mc>0)&(p8<-0.20)]=1
    out[(mc<0)&(p8>0.20)]=-1
```
Identical structure in `signals_shared.py` (`p8 < -0.20`, docstring: *"No extra CVD requirement — deep pullback IS the signal"*) and in the colab original (`p8 < -0.25`, docstring *"CVD Momentum — trend pullback with tighter threshold"* — still no CVD). S2 **never** contained CVD in any version. Meanwhile the patched runner's own header changelog asserts *"1. S2 now requires CVD momentum confirmation (was identical to S3)"* and its `__main__` logs *"S2 now uses CVD momentum"* — **both statements are false against the code in the same file**.

### TP-7 — F-04 (GLM): MAXTR retroactive threshold re-selection on the test window. **VERIFIED verbatim; severity recalibrated CRITICAL→HIGH (see §2).**

```python
tp=pred(m,fcs,tdf); bdf=tp[tp['prob']>=bp].copy()
...
if len(bdf)>MAXTR:
    for tc in np.arange(bp+0.04,0.96,0.04):
        bdf2=tp[tp['prob']>=tc]
        if MINTR<=len(bdf2)<=MAXTR:
            bdf=bdf2.copy(); bp=tc; break
```
`tdf` is the test window; the cutoff is re-picked using realized test-window trade counts, then statistics are computed on the selected subset. Confirmed non-causal information use and a procedure the live engine cannot replicate.

### TP-8 — F-05 (GLM) / U-09: Hardcoded threshold fallbacks. **VERIFIED in backtest; live side split by lineage.**

```python
else: bp=0.55; log(f" Default th={bp:.2f}")          # validation data insufficient
if not pt: bdf=tdf.copy(); bdf['prob']=0.50; bp=0.50 # no prior data at all
if m is None: bdf=tdf.copy(); bdf['prob']=0.50; bp=0.50
```
All three fallbacks confirmed verbatim, and per TP-3 the persisted results cannot tell which windows traded on a validated `bp` vs. a default. Mitigating evidence found: `live_unified_predictor.py` loads per-symbol `prob_threshold` from model manifests and **refuses to trade when absent** (*"No manifest threshold — SKIPPING (never trade on default)"*) — but that is the legacy lineage. Threshold sourcing inside `six_strategy_engine.py` (the lineage actually trading live capital — see TP-11) sits beyond the retrieval window: **UNVERIFIED for the live path**.

### TP-9 — F-06 (GLM) / LV-03 (Sonnet): Blanket exception swallowing. **VERIFIED — ≥6 occurrences in Engine_1.py's first ~140 lines as GLM claimed, and now confirmed on the ledger-write path.**_1.py` header: `except Exception as e: print(f"[WARN] Swallowed exception: {e}")` wraps stdout/stderr reconfigure, Windows VT100 setup, both `DualTee.write` branches, `DualTee.flush`, `DualTee.close`, UTF-8 reconfigure, and `get_process_memory_usage`. `patch_engine.py` (the script that hot-patched the live engine) installs a background ledger writer whose entire body ends in bare `except Exception as e: pass` — a failed write of `Engine_1_trade_logs.json` is invisible. `drift_dryrun.py` likewise: `except Exception: pass  # Never let logging crash the engine`. The pattern is pervasive exactly as both reports alleged; LV-03's escalation from "INFERRED" to verified-on-persistence-path is justified.

### TP-10 — F-08 (GLM) / LV-02 (Sonnet): float64/`fastmath` carries all monetary math. **VERIFIED with ledger artifacts.**

Both engines: `@njit(fastmath=True,nogil=True)` on `sim`/`gen_trades_numba` and on the port's `_sim_trade`. The ledger is littered with binary64 residue: `live_pnl_usd: -11.75439999999952`, `-13.047500000000012`, `-1.1284800000000845`, `pnl_usd: -19.297774399999724`, `exit_price: 0.18240000000000003`. Sonnet's cited artifact reproduces exactly. `__meta__.daily_start_capital: 3679.34251735` (float, ~26% below the CAP=5000 origin) is compared against floats elsewhere in the governor logic. No Decimal/cents boundary exists anywhere in the retrieved code.

### TP-11 — F-09/LV-06/U-08: Risk governor — no evidence of jointly-enforced counters; cooldown demonstrably inert. **VERIFIED as stated.**

`Engine_1.py`: `ENGINE_RISK_PCT = min(max(_raw_risk_pct, 0.0001), 0.02)` — a single per-trade clamp at import time. Ledger `__meta__`:
```json
"consecutive_losses": 2, "consecutive_loss_cooldown_until": 0.0
```
Two consecutive losses with the cooldown epoch at 0.0 — the cooldown mechanism exists as a field and is observably doing nothing. No session/day/per-position counters found in any retrieved file. (Partial mitigation exists only in the *legacy* lineage: `live_unified_predictor.py` halves risk above 1.5% equity deviation and pauses above 2.5%.)

### TP-12 — BT-04 (Sonnet): Inf→0 sanitization + warmup z-scores. **VERIFIED, with a bounding note.**

`featurize` in all versions ends `df=df.fillna(0).replace([np.inf,-np.inf],0)`; `zs()` divides by `std().replace(0,1e-10)` with `min_periods=1` (window-1 std is NaN → features zeroed, not NaN-propagated). Genuine outliers are rewritten to "exactly average" before training and inference. Bounding note: `gen_trades_numba` starts at `i=200`, so the worst warmup rows never generate trades — the live damage is the inf-clipping, not the first-bar NaNs. Severity MEDIUM stands.

### TP-13 — BT-05 (Sonnet): Threshold scoring guard masks ruin; no holdout. **VERIFIED.**

`best_thresh` scans `np.arange(0.50,0.92,0.02)` on the 30-day validation slice with `score=roi*(wr/100)/max(dd,0.1)*np.log1p(n)` guarded only by `if wr>0 and roi>-20 and dd<100` — a 99.9% drawdown candidate remains eligible, and a 1-trade/1-win window scores `wr=100`. Causality note for the record: `best_thresh` itself runs on pre-window data (`entry_time < ws`) — it is *not* the lookahead item; F-04's MAXTR loop is. Additionally confirmed: the patched runner **commented out** the fail-fast abort (`# if not passed: break`) that the colab original enforces (`if not passed and nt > 0: break`), so "PW/20 PASSED" summaries now include strategies that failed windows.

### TP-14 — BT-06 (Sonnet): Deterministic, frictionless fills. **VERIFIED.** `entry=o[i+1]` (next-bar open, exact), SL/TP fill at exact stop price (`ep=cs`), no gap or slippage term in any version. HIGH stands: parity with live fills is impossible by construction.

### TP-15 — F-11 (GLM): Timezone-normalization fragility. **VERIFIED as a risk; the patched runner is fixed, the colab lineage is not.** Root `run_all_6.py::load` contains the full IST→UTC correction (subtract 5h30 when the `" IST"` suffix is present) for both summary and footprint frames. `colab_strategies/run_all_6.py::load` still does naive `str.replace(" IST","")` with **no offset correction** — the original Fable5-3.1 bug is alive in the colab copy. The duplication risk GLM flagged is demonstrated, not hypothetical.

### TP-16 — LV-07 (Sonnet): SL/TP/ATR constants consistent (INFO pass). **VERIFIED — but the verdict is incomplete.** Ledger confirms `sl_dist == atr` to the last digit on every trade, `intended_tp_dist == 5×atr` exactly (matches `TP=5.0`), `trail_buf 0.8` == `TRA=0.8`. However every trade also carries `"trail_act": 1.0`. In the backtest, trailing engages only after a **5-ATR** excursion (`if (bp-entry)>=td: ns=bp-trd` with `td=TP*atr`). If live `trail_act=1.0` means trail activation at 1×ATR, live tightens stops 5× earlier than the validated model — a parity break hiding inside an INFO-pass finding. Semantics not resolvable from the ledger alone: **flag for Layer 3**.

### TP-17 — F-12/U-07 (stop-loss registration ordering). **Behaviorally VERIFIED as a live failure mode** (TP-4: a trade passed through its registered stop and was flattened 8.75 ATR away by `BROKER_SYNC`), code-level ordering **UNVERIFIED** — the fill/SL handler sits in the unretrievable `Engine1TradeTracker` body, as both Layer 1 reports correctly disclosed.

---

## 2. False Positives & Hallucinations

No outright hallucinations were found — every Layer 1 claim corresponds to real code or real ledger data. The following are **mechanically incorrect, overstated, or unproven as framed**, and must not enter Layer 3 as stated:

### FP-1 — LV-04 (Sonnet): "exec_sl/exec_tp tick-rounding is asymmetric … SL rounds away from entry, TP rounds toward entry … both adverse." **Mechanism DISPROVEN.**

The rounding is standard nearest-tick quantization, and its direction varies trade-to-trade. Evidence from the ledger (ADA tick 0.0001; TRX tick 0.00001):

| Trade | Side | Intended SL → exec | Effect | Intended TP → exec | Effect |
|---|---|---|---|---|---|
| S4 ADA #1 | SHORT | 0.17488571 → 0.1749 | looser (adverse) | 0.17197143 → 0.1720 | tighter (adverse) |
| S4 ADA #5 | SHORT | 0.17664286 → 0.1766 | **tighter (favorable)** | 0.17218571 → 0.1722 | tighter (adverse) |
| S1 ADA #3 | SHORT | 0.17495714 → 0.1750 | looser (adverse) | 0.17161429 → 0.1716 | **looser (favorable)** |
| S4 SUI #4 | SHORT | 0.65481429 → 0.6548 | **tighter (favorable)** | 0.64452857 → 0.6445 | **looser (favorable)** |
| S2 TRX #6 | LONG | 0.33163540 → 0.33163 | looser (adverse) | 0.33400714 → 0.33401 | **looser (favorable)** |

Sonnet extrapolated a "systematic adverse drag" from a single trade where both deltas happened to be adverse. The actual process is unbiased ±0.5-tick noise. **What survives:** the backtest trades unquantized prices and live trades quantized ones — a real but symmetric parity gap. Magnitude is not uniformly trivial (half a tick ≈ 10% of a 1-ATR stop on the ADA trades), so keep it on the patch list as *model quantization in `sim()`*, but strike the "asymmetric leakage" characterization and its MEDIUM severity → **LOW-MEDIUM**.

### FP-2 — LV-05 (Sonnet): "Dual PnL accounting (live_pnl_* vs pnl_* + closing_dispatched)" as an accounting risk. **Unproven; misread of the schema.** The ledger fields are a mark-to-market snapshot vs. realized-at-close: `live_pnl_usd` is the last observed unrealized P&L while the trade was open (e.g. −11.75 at the final tick before reconciliation), `pnl_usd` is the realized close P&L (−4.01 on the exit-at-entry sync). `closing_dispatched: true` appears only on broker-acknowledged `SL` exits and is absent on `BROKER_SYNC` closes — a close-dispatch flag, not a second book. **No double-counting is evidenced anywhere in the ledger.** Sonnet honestly labelled this INFERRED; it must not be inherited by Layer 3 as a finding. The float residue on `live_pnl_usd` is real but belongs to LV-02. **Strike; reclassify to schema-note.**

### FP-3 — BT-03 severity framing (Sonnet) & GLM's implied treatment: "S2 trades a different strategy than its name" as a *signal-correctness/parity* bug. **Overstated.** The fact (no CVD in S2) is true, but: (a) `signals_shared.py` — the module designated as the single source of truth — defines S2 identically (pure `p8<-0.20`) and openly documents *"No extra CVD requirement — deep pullback IS the signal"*; (b) S2 is p8-only in **all four** runner copies, so backtest and intended-live agree on what is traded; (c) the strategy was *validated* as a deep-pullback strategy. The genuine defect is narrower andSharper than Sonnet framed it: **the file's own changelog line ("S2 now requires CVD momentum confirmation") and runtime log line ("S2 now uses CVD momentum") are false statements in the audited artifact**, and the `S2_CVD_Momentum` label corrupts P&L attribution (the ledger books deep-pullback trades under a CVD banner). Reclassify from "signal integrity MEDIUM" to **documentation/attribution defect, LOW-MEDIUM**.

### FP-4 — LV-01 framing (Sonnet): "This is the single reason live results cannot match backtest." **False as stated.** Cross-validation established at least five independent, concurrently-active parity breaks: TR-vs-HL ATR (TP-2a, biases every feature *and* every stop), fee regime (TP-1), deterministic fills (TP-14), threshold provenance (TP-8), and funding existence (TP-5). LV-01 is the most *violent* break (unbounded tail loss) but demonstrably not the only one. Layer 3 must not sequence patches around a single-cause narrative.

### FP-5 — F-04 severity (GLM): "CRITICAL — lookahead bias … retroactively pick a probability cutoff." **Mechanism true, severity overstated.** The MAXTR loop optimizes only for a *trade-count* band (`MINTR<=len(bdf2)<=MAXTR`), not for P&L, win rate, or ROI — it is count-based selection on test-window information, not outcome-based peeking. Real, live-unreplicable, and biasing (reported stats are computed on the post-selection subset), but categorically milder than P&L-optimized threshold search. **Reclassify CRITICAL → HIGH.**

### FP-6 — The repository's own parity artifact: `parity_test_results.json`. **STRUCK DOWN as assurance.** 
```json
{ "total_checks": 174, "passed": 174, "failed": 0, "max_divergence": 0.0, "tolerance": 0.01, "failures": [] }
```
Neither Layer 1 report cited it, but it is the natural counter-evidence to F-01 and must be adjudicated. It fails on three counts: **(a)** No script in the retrieved tree (root, `engine_components/`, `colab_strategies/`, `.agents/scripts/`) writes `parity_test_results.json` — provenance unknown; the repo's `verify_all.py` is an unrelated web-app toolkit (OWASP/SEO/Lighthouse). **(b)** 174 checks = 6 strategies × 29 features with `max_divergence: 0.0` is *provably incompatible* with the demonstrated state of the code: any test comparing `six_strategy_engine.featurize` (True-Range ATR, TP-2a) against `run_all_6.featurize` (High−Low ATR) on identical data **cannot** return 0.0 divergence on `atr`, `p8`, `p21`, `p50`, or `mc`. **(c)** `signals_shared.py`'s own header documents that all six live signal branches previously diverged (`S1 live: p8 < -0.20 … llm*2.0 vs backtest llm*1.2`; `S2/S5/S6: entirely different formulas`) — and in `live_unified_predictor.py` the claimed fix is decorative: `_LIVE_SIGNAL_MAP` is imported but the entry gates still run inline branches with exactly the divergent constants the docstring says were eliminated (`pull8 < -0.2 and ll >= llm * t_liq`, `t_liq` default 2.0). The artifact is either stale, self-referential, or measures a pair that excludes the live execution path. **It carries zero exculpatory weight.**

### Unverifiable — carried forward, not cleared
`Engine_1.py` beyond ~line 210 of 264 KB remains unretrievable by any available channel (raw fetch window, GitHub API, Sourcegraph unindexed). Therefore: F-10/U-03 (bounded WS reconnect), U-01/U-02 (lock mixing, task cancellation), U-10 (float `==` on prices), and the code-level SL-registration ordering (F-12/U-07) remain **UNVERIFIED-HIGH-RISK**, exactly as both Layer 1 models disclosed. Likewise the second half of `six_strategy_engine.py` (its private S1–S6 copies, threshold source, predictor class) — Layer 3 must treat live-path threshold provenance as unproven, not as cleared.

---

## 3. Defense Summary

**Verdict.** The Layer 1 attack survives defense: of 30+ distinct claims, zero are fabricated, 20+ are verified verbatim or behaviorally (several with ledger-grade empirical proof), five are overstated in mechanism or severity (FP-1…FP-5), and three new divergences were discovered that raise, not lower, the assessed risk (True-Range-vs-High−Low ATR across the live/backtest boundary; four drifting `run_all_6.py` copies with contradictory constants; a parity-test artifact that cannot be genuine). The system under audit is **not deployable as validated**: the walk-forward statistics describe a different machine than the one holding live capital — different volatility measure, different cost model, different fill model, different (or default) thresholds, a funding term that exists only in backtest, and a reconciliation path empirically shown to realize 8.75× the modeled worst-case loss. Equity evidence: `daily_start_capital` 3,679.34 vs. the 5,000 base, with the loss-cooldown inert (`0.0`) while `consecutive_losses: 2`.

**Mandatory Layer 3 patches, in precedence order:**
1. **BROKER_SYNC loss capping (LV-01, behavioral TP):** reconciliation must verify the broker-side stop's existence/ACK before any market flatten; if the stop is missing post-fill, flatten *and* halt the governor — realized loss must never exceed 1R + costs. This is the only item where tail risk is unbounded.
2. **Single ATR/feature source (new, TP-2a):** delete the port's True-Range block; both engines must import one `featurize` (and one `sim`) from a shared module. Re-run walk-forward under whichever definition is chosen — current results are orphaned from the live math either way.
3. **One cost model (F-03/BT-01):** a shared `risk_config.py` exporting one round-trip constant; `run_all_6.py`, `six_strategy_engine.py`, and `Engine_1.py` all import it; signed funding (BT-02) replaces `abs(avg_fr)` and must exist in both engines or neither.
4. **Signal single-sourcing (F-01/BT-03):** `six_strategy_engine` must consume `signals_shared.STRAT_MAP` (no local copies, no silent ImportError fallback — F-02); delete the vestigial inline branches in `live_unified_predictor.py`; either rename S2 or restore CVD logic; strike the false changelog/log lines.
5. **Threshold provenance (F-04/F-05):** persist `bp` and code-path flag per window in `all_6_results.json`; live loads thresholds only from the walk-forward artifact; remove the count-based MAXTR re-selection or move it inside the validation window; re-enable fail-fast window abort.
6. **Ledger integrity (LV-02/LV-03):** Decimal/integer-cents boundary at the Risk Governor; no `fastmath` value touches money; `except Exception: pass` is banned on order/SL/persistence paths (fail-loud + halt).
7. **Governor activation (F-09/LV-06):** non-zero loss cooldown, session/day/position counters jointly gating entries, halt-on-breach.
8. **Fill realism (BT-06) + quantization (FP-1 residual):** slippage term and tick quantization in `sim()`; resolve `trail_act` semantics (TP-16) against `td=TP*atr` activation.
9. **Regenerate a genuine parity test** comparing the *actual* live path (`six_strategy_engine` + `signals_shared`) against `run_all_6.py` on identical data, `atr` included; archive the current 174/174 artifact as invalid.
10. **Deduplicate:** collapse four `run_all_6.py` copies and the divergent `binance_broker.py`/`coinglass_scraper.py` pairs; one importer per module.

**Open items for Layer 3 to resolve with full-file access:** WS reconnect bounds (F-10/U-03), lock discipline and task cancellation (U-01/U-02), SL-registration ordering in code (F-12/U-07), live CVD/liq accumulation semantics vs. scraper (U-04/U-05), float-equality usage (U-10), and `six_strategy_engine` threshold sourcing. These were unverifiable at Layer 2 for retrieval reasons, not cleared.