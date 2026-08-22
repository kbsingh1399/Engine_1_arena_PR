

# 🛡️ Layer 2 Defense Audit Report

## 1. Verified True Positives
The following Layer 1 findings are directly supported by the fetched source code.

1. **Fee model mismatch is real (BT-01 / F-03) — TRUE POSITIVE**
- `run_all_6.py` sets:
```python
CAP=5000; RSK=20; FEE=0.0020; ...
Engine_1.py sets:
Python

ENGINE_FEE_PER_SIDE = float(os.environ.get("ENGINE_FEE_PER_SIDE", "0.0004"))
ENGINE_FEE_RT = ENGINE_FEE_PER_SIDE * 2  # 0.08% round-trip
This is a structural mismatch between backtest fee/slippage assumptions and live ledger fee assumptions.
Silent fallback to local strategy definitions exists (F-02) — TRUE POSITIVE
run_all_6.py:
Python

try:
    from signals_shared import STRAT_MAP as _SHARED_STRAT_MAP
    _USE_SHARED = True
except ImportError:
    _USE_SHARED = False
...
if _USE_SHARED:
    STRATS = list(_SHARED_STRAT_MAP.items())
else:
    STRATS=[ ... make_signal_s1..s6 ... ]
If signals_shared import fails, it silently runs local copies; no explicit hard-fail.
S2 is not CVD-momentum logic despite name (BT-03) — TRUE POSITIVE
run_all_6.py:
Python

def make_signal_s2(df):
    """S2: Deep Pure Trend (Replaced CVD logic)"""
    ...
    out[(mc>0)&(p8<-0.20)]=1
    out[(mc<0)&(p8>0.20)]=-1
This uses mc + p8, not CVD variables.
Funding sign bug from abs() exists (BT-02) — TRUE POSITIVE
run_all_6.py:
Python

funding_cost = abs(avg_fr) / 32.0 * entry_price_approx * units_approx * funding_bars
The use of abs(avg_fr) removes funding direction, confirming the Layer 1 concern.
Backtest fill/exit model is deterministic and idealized (BT-06) — TRUE POSITIVE
run_all_6.py:
Python

entry=o[i+1] if i+1<n else c[i]
...
if dr==1:
    if l[j]<=cs: ep=cs; ... break
...
if dr==-1:
    if h[j]>=cs: ep=cs; ... break
Next-bar-open entries plus exact stop trigger conditions are deterministic and do not model execution microstructure.
Validation threshold tuning without holdout is present (BT-05/F-05 core) — TRUE POSITIVE
run_all_6.py:
Python

bp=best_thresh(vp)  # threshold chosen on validation
...
tp=pred(m,fcs,tdf); bdf=tp[tp['prob']>=bp].copy()
There is no second unseen holdout stage before applying the threshold.
Potential lookahead via test-window trade-count capping loop exists (F-04) — TRUE POSITIVE
run_all_6.py:
Python

if len(bdf)>MAXTR:
    for tc in np.arange(bp+0.04,0.96,0.04):
        bdf2=tp[tp['prob']>=tc]
        if MINTR<=len(bdf2)<=MAXTR: bdf=bdf2.copy(); bp=tc; break
The threshold is adjusted using full test-window prediction distribution (tp), which is non-causal for live deployment.
Broad swallowed exception pattern in Engine_1 startup/logging exists (F-06 / LV-03 partial) — TRUE POSITIVE
Engine_1.py repeatedly uses:
Python

except Exception as e:
    print(f"[WARN] Swallowed exception: {e}")
Verified in stdout/stderr reconfigure, VT processing setup, DualTee.write/flush/close, memory helper.
Float-based monetary config in Engine_1 and fastmath float kernels in backtest exist (F-08 / LV-02 partial) — TRUE POSITIVE
Engine_1.py:
Python

ENGINE_RISK_USD = max(float(...), 1.0)
ENGINE_FEE_PER_SIDE = float(...)
run_all_6.py:
Python

@njit(fastmath=True,nogil=True)
def sim(...)
@njit(fastmath=True,nogil=True)
def gen_trades_numba(...)
Float-heavy arithmetic is confirmed.
Live engine uses a separate module instead of importing run_all directly (F-01 core) — TRUE POSITIVE
Engine_1.py:
Python

# Six Strategy Engine (ports run_all_6.py verified strategies)
from six_strategy_engine import LiveSixStrategyPredictor, STRATEGY_NAMES as SIX_STRAT_NAMES
This confirms architectural indirection (live path is a different module).
IST handling logic duplication inside run_all_6.py is present (F-11 partial) — TRUE POSITIVE
run_all_6.py has near-duplicate IST strip/offset blocks for summary and footprint timestamps:
Python

raw_ts = df[tc].astype(str).str.replace(" IST", "", regex=False)
...
df["ts"] = df["ts"] - pd.Timedelta(hours=5, minutes=30)
...
raw_tsf = df_f[tcf].astype(str).str.replace(" IST", "", regex=False)
...
df_f["ts"] = df_f["ts"] - pd.Timedelta(hours=5, minutes=30)
2. False Positives & Hallucinations
The following Layer 1 claims are not provable from the fetched code, or overstate certainty.

LV-01 / F-12 style stop-loss failure claims tied to BROKER_SYNC exits — NOT VERIFIED (thus overclaimed)
Layer 1 presents specific ledger examples (ADAUSDT trade, exact prices, % loss, BROKER_SYNC reason), but these data points are not present in either fetched Engine_1.py excerpt or run_all_6.py.
The fetched Engine_1.py content is truncated before order/position reconciliation paths; therefore “VERIFIED” is not supportable from current evidence.
LV-04 asymmetric exec_sl/exec_tp tick-rounding — NOT VERIFIED
No visible exec_sl, exec_tp, or rounding code in the fetched Engine_1.py excerpt.
Cannot confirm or refute with source evidence available.
LV-05 dual PnL accounting (live_pnl_* vs pnl_*) — NOT VERIFIED
No such symbols appear in fetched excerpt.
The claim may be true, but it is unproven from retrieved code.
LV-06 governor cooldown disabled (0.0) and strategy mismatch as an active bug — PARTIAL/OVERSTATED
ACTIVE_STRATEGY = os.environ.get("ACTIVE_STRATEGY", "ml_alpha_squeezer") is visible.
But no visible governor cooldown variable or enforcement branch in fetched excerpt.
Therefore the cooldown-disabled conclusion is unverified.
F-09 “no three-counter risk governor” as a confirmed vulnerability — NOT VERIFIED
The relevant governor implementation is outside retrieved excerpt.
Absence of evidence in partial fetch is not evidence of absence.
F-10 websocket reconnection unbounded — NOT VERIFIED
import websockets is visible, but no reconnection loop was retrieved.
Should be marked “needs verification,” not “vulnerable confirmed.”
F-07 “unit mismatch between backtest and live sizing” as confirmed — PARTIAL
Backtest funding uses units_approx = RSK / atr_entry (confirmed).
Live sizing logic is not visible in fetched Engine_1.py excerpt.
Cross-engine mismatch remains speculative without live-side sizing code.
LV-07 “ATR/SL/TP constants are consistent” marked VERIFIED — OVERCLAIMED
run_all_6.py constants are visible (TP=5.0, stop based on ATR in sim).
Equivalent live constants/logic were not visible in fetched Engine_1.py excerpt.
So this is not fully verifiable as “VERIFIED”.
F-01 wording that live bypasses Engine_1 entirely (as stated in prompt context) — FALSE framing
Source shows Engine_1.py is the orchestrator importing six_strategy_engine.
It is not bypassed; rather, it delegates strategy prediction to another module.
The real issue is parity drift risk, not “Engine_1 bypassed entirely.”
3. Defense Summary
Confirmed severe breaks: fee-model divergence, thresholding logic risks (including test-window trade-cap adjustment), funding sign bug (abs(fr)), S2 name/logic mismatch, deterministic fill assumptions, and extensive swallowed exceptions in visible live startup/logging code.
Major overclaims in Layer 1: several “VERIFIED” live-ledger assertions (BROKER_SYNC stop-loss failure mechanics, SL/TP rounding asymmetry, dual-PnL bookkeeping, cooldown disabled behavior) are not evidenced in the fetched source segments and were asserted with stronger certainty than the code access supports.
What Layer 3 must patch first:
Unify fee/slippage constants across backtest and live.
Remove abs() from funding and apply signed funding logic.
Eliminate non-causal threshold adjustments on test windows.
Enforce hard-fail behavior for capital-path exceptions.
Complete full-file verification of Engine_1 order lifecycle and broker sync before any production claim of stop-loss safety.


