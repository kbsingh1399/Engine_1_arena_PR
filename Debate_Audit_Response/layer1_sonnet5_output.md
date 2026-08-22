# Layer 1 Audit Output - Sonnet 5

## Findings

| ID | File | Area | Title | Severity | Status |
|---|---|---|---|---|---|
| LV-01 | Engine_1.py (live ledger) | Backtest↔Live Parity / Financial Safety | BROKER_SYNC realizes losses far beyond the registered stop-loss | CRITICAL | VERIFIED |
| BT-01 | run_all_6.py ↔ Engine_1.py | Target / ATR / Fee Parity | Fee model divergence: backtest ≈0.20% RT vs live 0.08% RT | CRITICAL | VERIFIED |
| BT-02 | run_all_6.py | ML/Financial Integrity | Funding cost uses abs(fr) — both long & short charged identically | HIGH | VERIFIED |
| LV-02 | Engine_1.py (config + ledger) | Financial Safety | Float arithmetic for all monetary & price data | HIGH | VERIFIED |
| LV-03 | Engine_1.py | Lethal Bug Hunt | Blanket 'Swallowed exception' pattern masks critical-path failures | HIGH | INFERRED |
| BT-06 | run_all_6.py | Backtest↔Live Parity | Backtest assumes deterministic next-bar-open fills + exact-ATR SL | HIGH | VERIFIED |
| BT-03 | run_all_6.py | Signal Generation Exactness | Strategy S2 'CVD_Momentum' contains no CVD — pure p8 pullback | MEDIUM | VERIFIED |
| BT-04 | run_all_6.py | ML Integrity | Inf→0 silent replacement + unstable warmup z-scores feed the model | MEDIUM | VERIFIED |
| BT-05 | run_all_6.py | ML Integrity / Risk | Threshold tuned on validation w/o holdout; DD guard masks blow-ups | MEDIUM | VERIFIED |
| LV-04 | Engine_1.py (ledger) | Target / ATR Match | exec_sl/exec_tp tick-rounding is asymmetric vs intended sl/tp | MEDIUM | VERIFIED |
| LV-05 | Engine_1.py (ledger) | Data Integrity | Dual PnL accounting (live_pnl_* vs pnl_* + closing_dispatched) | MEDIUM | INFERRED |
| LV-06 | Engine_1.py (config + meta) | Risk Governor | Governor cooldown disabled (0.0) while losses accrue; default-strategy mismatch | MEDIUM | INFERRED |
| LV-07 | Engine_1.py ↔ run_all_6.py | Target & ATR Match | ATR/SL/TP CONSTANTS are consistent (partial parity pass) | INFO | VERIFIED |

## Root Causes

### LV-01: Stop-loss is advisory, not enforced, on broker synchronization
- **Impact**: Unbounded per-trade loss vs a bounded-loss backtest → realized drawdown will exceed every modeled limit. This is the single reason live results cannot match backtest.
- **Evidence**: 
  - Ledger: ADAUSDT SHORT entry 0.1759, registered sl 0.17664285, sl_dist 0.00074285 (== 1.0×ATR).
  - Exit: exit_price 0.18240, exit_reason 'BROKER_SYNC', pnl_pct −0.6562568703598827, pnl_usd −24.20.
  - 0.1824 is +3.69% adverse from entry — ~9× the 1-ATR stop the simulator would ever allow.
  - Contrast backtest sim(): for a short, loss is capped the instant h[j]>=cs (entry+ATR). Worst case = exactly 1 R minus fee.
- **Reasoning**: 
  - sim() guarantees max loss per trade = u*(entry-cs) = units*ATR ≈ 1R. The walk-forward gates (TDD=30%, dd<100) are calibrated against this bounded-loss assumption. The live 'BROKER_SYNC' path breaks that invariant: on a websocket/broker reconnection the engine appears to flatten at the prevailing mark, which can be arbitrarily far from the stop.
  - A −0.66% move on a 1-ATR-risked short is a ~9R loss. A handful of these in a single session (the ledger shows a cluster of them) will detonate the drawdown limits the backtest 'proved' were safe. The backtest's 20/20 PASS, <2% DD and 58–94% WR are mathematically unattainable if even a small fraction of live exits behave this way.
  - This is the textbook parity leak: the simulator models a stop that is hit; the engine books a stop that is ignored whenever the connection resyncs. The two are not the same strategy.

**Patch** (Never realize a sync-loss worse than SL ± max-slip - Engine_1.py — exit/reconcile path):
```python
# Hard ceiling: a BROKER_SYNC exit must NEVER be worse than the
# registered stop plus a small, bounded slippage tolerance.
MAX_SLIP_BPS = 10  # 10 bps absolute ceiling; tune to live fill distribution

def _validate_sync_exit(self, trade):
    if trade.exit_reason != "BROKER_SYNC":
        return True  # ordinary SL/TP/trail fills pass through
    if trade.direction == 1:  # long: can never fill below SL - slip
        worst = trade.sl * (1 - MAX_SLIP_BPS / 1e4)
        if trade.exit_price < worst:
            self._halt_and_reconcile(trade)   # do NOT book PnL
            return False
    else:                      # short: can never fill above SL + slip
        worst = trade.sl * (1 + MAX_SLIP_BPS / 1e4)
        if trade.exit_price > worst:
            self._halt_and_reconcile(trade)
            return False
    return True
```

### BT-01: Two independent fee constants diverge by 2.5×
- **Impact**: Backtest expectancy is computed at ~0.20% RT; live is charged at 0.08% RT. Whichever is 'right', the engines disagree, so any edge figure is unreliable and the chosen probability threshold is mis-calibrated.
- **Evidence**: 
  - run_all_6.py: FEE=0.0020; sim(): f=u*entry*FEE/2.0 + u*abs(ep)*FEE/2.0  → round-trip ≈ 0.20% of notional.
  - Engine_1.py: ENGINE_FEE_PER_SIDE=float(0.0004); ENGINE_FEE_RT=ENGINE_FEE_PER_SIDE*2 → 0.08% round-trip.
  - Ledger: BROKER_SYNC round-trip on an exit-at-entry trade books exactly −0.08% (−0.07999999), confirming the live 0.08% rate is the one actually charged.
- **Reasoning**: 
  - The backtest intentionally raised FEE 0.0015→0.0020 'to account for slippage on volatile entries', i.e. ~0.20% round-trip. The live engine charges only 0.08%. On a strategy whose average winner is ~5×ATR against a 1×ATR stop, a 0.12-point swing in round-trip cost materially changes expectancy and the threshold that best_thresh selects.
  - The /2.0 in sim() is the root ambiguity: FEE is simultaneously labelled '0.20%' (round-trip intent) yet applied as a per-side half. A future maintainer will read FEE=0.0020 as 0.20% per-side (0.40% RT) and 'fix' it, silently doubling or halving cost again. There is no single source of truth.

**Patch** (One shared cost module consumed by both engines - risk_config.py (new) — imported by run_all_6.py AND Engine_1.py):
```python
# risk_config.py — SINGLE source of truth for commission+slippage.
# Imported verbatim by run_all_6.py and Engine_1.py so backtest == live.
ROUND_TRIP_FEE = 0.0020          # total both-side cost incl. estimated slippage
FEE_PER_SIDE   = ROUND_TRIP_FEE / 2.0   # 0.0010

# ---- run_all_6.py ----
from risk_config import ROUND_TRIP_FEE, FEE_PER_SIDE
FEE = ROUND_TRIP_FEE
def sim(h,l,c,entry_idx,entry,atr,dr):
    ...
    # full per-side fee on entry and exit  (RT == ROUND_TRIP_FEE exactly)
    f = u*entry*FEE_PER_SIDE + u*abs(ep)*FEE_PER_SIDE
    npnl = g - f

# ---- Engine_1.py ----
from risk_config import ROUND_TRIP_FEE, FEE_PER_SIDE
ENGINE_FEE_PER_SIDE = FEE_PER_SIDE
ENGINE_FEE_RT       = ROUND_TRIP_FEE   # replaces the ad-hoc 0.0004*2
```

### BT-02: Direction-agnostic funding charge biases every funding leg
- **Impact**: Funding-eligible trades are mis-costed in backtest (wrong sign) and un-costed live (absent). Both break parity and bias the label distribution the classifier learns from.
- **Evidence**: 
  - run_one(): funding_cost = abs(avg_fr)/32.0 * entry_price_approx * units_approx * funding_bars.
  - Comment block states the intent: 'positions pay funding when sign(direction)==sign(funding); positive funding = longs pay shorts'.
  - abs(fr) discards sign entirely, so shorts are charged during positive funding (when they should be paid) and vice-versa.
- **Reasoning**: 
  - Funding is a signed cash flow. With abs(), the model adds a cost to both longs and shorts proportional to |fr|, which is neither the long side nor the short side — it is a fabricated always-cost. For a mean-reversion book that is frequently short into positive funding (collecting), this converts income into expense and depresses backtest PnL, distorting label generation and threshold selection.
  - It is also a backtest-only adjustment: the live ledger shows no funding line item at all, so the two engines disagree on whether funding even exists.

**Patch** (Signed funding over the holding window - run_all_6.py — trade loop):
```python
if 'fr' in fa and fa['fr'][idx] != 0.0:
    # RAW signed sum of funding across the bars actually held.
    signed_fr = float(np.sum(fa['fr'][max(0, idx):xi+1]))
    atr_entry = float(fa['atr'][idx]) if 'atr' in fa else 1.0
    entry_price = float(dff['Close'].values[idx])
    units = RSK / atr_entry if atr_entry > 0 else 0.0
    bars = max(0, int(bh))
    # cost > 0 = money out. Long (dr=1) pays when fr>0; short (dr=-1)
    # receives when fr>0  =>  signed cost == dr * signed_fr.
    funding_cost = (dr * signed_fr / 32.0) * entry_price * units * bars
    net = net - funding_cost
    r  = net / RSK
    lb = 1.0 if net > 0 else 0.0
```

### LV-02: Binary64 float carries every dollar and every price
- **Impact**: Equity drift, unreliable equality checks in the governor, and PnL that never ties out to the broker — a silent, compounding reconciliation leak.
- **Evidence**: 
  - Config: ENGINE_RISK_USD=max(float(...),1.0); ENGINE_FEE_PER_SIDE=float(...).
  - Ledger: entry_price 0.1744, units 28777.0, live_pnl_usd −11.75439999999952, pnl_usd −4.01496704.
  - −11.75439999999952 is a float-accumulation artifact (trailing 99999952), not a real dollar value.
- **Reasoning**: 
  - 0.1 is not representable in binary64, so summing fills/fees accumulates error. Over thousands of trades and reconciliation passes, the book's internal equity drifts from the broker's equity. When the Risk Governor compares 'current equity == daily_start_capital' or threshold-tests PnL, two floats that 'should' be equal are not, producing skipped cooldowns or phantom breaches.
  - The checklist explicitly forbids float arithmetic on monetary data; the codebase violates it end-to-end.

**Patch** (Decimal for all money; tick-quantize prices - Engine_1.py — money helpers):
```python
from decimal import Decimal, ROUND_HALF_UP, getcontext
getcontext().prec = 28

def D(x) -> Decimal:
    # ALWAYS construct Decimal from a string, never from a float.
    return Decimal(str(x))

def q(price: Decimal, tick: str) -> Decimal:
    return price.quantize(D(tick), rounding=ROUND_HALF_UP)

# Realized PnL — no float anywhere in the chain:
#   pnl = units * (exit - entry) - fees   (all Decimal)
#   pnl = q(pnl, TICK) for the instrument
# Float is permitted ONLY for read-only display / charting.
```

### LV-03: 'Swallowed exception' is a culture, not a one-off — capital paths inherit it
- **Impact**: Failures on the most safety-critical code paths become invisible. Until every capital-path try/except is reviewed, no live behavior can be trusted.
- **Evidence**: 
  - DualTee.write/flush/close, sys.reconfigure, get_process_memory_usage all wrap broad 'except Exception as e: print("[WARN] Swallowed exception")'.
  - The unread 6,500-line core (order placement, SL registration, websocket dispatch) is authored in the same hand and idiom.
- **Reasoning**: 
  - Swallowing on a log-tee is harmless; swallowing on 'register stop loss' or 'send closing order' is catastrophic — the engine proceeds as if the operation succeeded. Because the pattern is pervasive in the readable portion, the prior probability that it recurs in the capital-handling portion is high and must be assumed until disproven.
  - This is why LV-01 can happen silently: a stop that failed to register (exception swallowed) leaves a position naked, and the later BROKER_SYNC realizes the unbounded loss.

**Patch** (Fail loud on capital paths; scope everything else - Engine_1.py — order / SL paths):
```python
class StopLossRegistrationError(RuntimeError):
    pass

def register_stop_loss(self, trade):
    sl = self.compute_sl(trade)            # Decimal
    ok = self.broker.place_stop(trade.id, sl)
    if not ok:
        # NEVER swallow. A naked position is the worst possible state.
        raise StopLossRegistrationError(
            f"SL registration failed for {trade.id} — order NOT placed")
    trade.sl_registered_at = time.time()
    trade.sl_state = "REGISTERED"

# Place SL BEFORE the entry is considered filled:
def on_fill(self, trade):
    self.register_stop_loss(trade)         # raises if it cannot
    trade.status = "OPEN"                  # only now is it really open
```

### BT-06: Zero-slippage backtest cannot reproduce live fills
- **Impact**: Backtest is structurally optimistic. Without a slippage term, 'parity' is impossible by construction, independent of any coding bug.
- **Evidence**: 
  - gen_trades_numba: entry=o[i+1] (deterministic next open).
  - sim(): long SL triggers at the first bar where l[j]<=cs — filled exactly at cs, no gap, no slip.
  - Live fills diverge (exec_entry vs intended; BROKER_SYNC gaps). The backtest has no parameter to express any of it.
- **Reasoning**: 
  - The simulator is a frictionless idealization. Every backtest metric (WR, DD, ROI, the chosen probability threshold) is conditioned on fills that never slip. The moment live adds slippage — especially on the volatile entries the patched runner was built for — expectancy compresses and the threshold that passed walk-forward no longer clears fees.
  - This is why a 76% WR / +2000% ROI backtest can coexist with a ledger full of losses: the model was never shown the cost structure it actually trades against.

**Patch** (Adverse slippage in sim() (mirror live fills) - run_all_6.py — sim()):
```python
from risk_config import ROUND_TRIP_FEE, FEE_PER_SIDE
SLIP = 0.0005   # 5 bps adverse per side — calibrate to live fill log

def sim(h,l,c,entry_idx,entry,atr,dr):
    n=len(c); sd=atr; td=5.0*atr; trd=0.8*atr
    # apply adverse slippage at BOTH entry and the SL fill
    entry_eff = entry*(1+SLIP) if dr==1 else entry*(1-SLIP)
    st = entry_eff - sd if dr==1 else entry_eff + sd
    cs=st; bp=entry_eff; ns=st
    mx=min(entry_idx+288+1,n); ep=c[mx-1]; bh=mx-1-entry_idx
    mae=0.0
    for j in range(entry_idx+1,mx):
        if dr==1:
            ae=entry_eff-l[j]
            if ae>mae: mae=ae
            if l[j]<=cs:                            # SL fill slips adverse
                ep=cs*(1-SLIP); bh=j-entry_idx; break
            if h[j]>bp: bp=h[j]
            if (bp-entry_eff)>=td: ns=bp-trd
            if ns>cs: cs=ns
        else:
            ae=h[j]-entry_eff
            if ae>mae: mae=ae
            if h[j]>=cs:
                ep=cs*(1+SLIP); bh=j-entry_idx; break
            if l[j]<bp: bp=l[j]
            if (entry_eff-bp)>=td: ns=bp+trd
            if ns<cs: cs=ns
    u=RSK/sd
    g=u*(ep-entry_eff) if dr==1 else u*(entry_eff-ep)
    f=u*entry_eff*FEE_PER_SIDE + u*abs(ep)*FEE_PER_SIDE
    return g-f, (g-f)/RSK, 1.0 if g-f>0 else 0.0, bh, u*mae
```

### BT-04: Model ingests zeroed-out infinities and warmup noise
- **Impact**: Degenerate features at exactly the moments the strategy is meant to trade. Expectancy and threshold are computed on partially-fabricated inputs.
- **Evidence**: 
  - featurize() terminates with: df=df.fillna(0).replace([np.inf,-np.inf],0).
  - zs(): (s-s.rolling(w,min_periods=1).mean())/s.rolling(w,min_periods=1).std().replace(0,1e-10). At w=1 the std is NaN.
- **Reasoning**: 
  - An infinite z-score (a genuine outlier — exactly what a breakout strategy hunts for) is silently rewritten to 0, i.e. 'perfectly average'. The classifier then sees a calm market where there was an extreme one. Combined with min_periods=1 producing NaN-derived 0s in the first ~bars, the early feature rows are fabrications, not measurements.
  - The model is trained and infers on data that has been dishonestly sanitized, so its probability output — and the threshold gating trades — rests on corrupted inputs.

**Patch** (Clip, assert finite, drop warmup, gate inference - run_all_6.py — featurize() + inference):
```python
ZCLIP = 8.0
# 1) bound z/distance features instead of zeroing extremes
for col in df.columns:
    if col[0] in ("z", "p") or col.startswith("vr"):
        df[col] = df[col].clip(-ZCLIP, ZCLIP)

# 2) hard assertion: NO non-finite value may reach the model
num = df.select_dtypes("number")
assert not num.isin([np.inf, -np.inf]).any().any(), "inf in features"
assert not num.isna().any().any(), "NaN in features"
df = df.fillna(0)

# 3) drop the warmup window where rolling stats are undefined
df = df.iloc[200:].copy()

# 4) inference-time gate (live mirror):
def safe_predict(model, X):
    if not np.isfinite(X.to_numpy()).all():
        raise FeatureValidationError("non-finite feature vector — refuse inference")
    return model.predict_proba(X)[:, 1]
```

### BT-05: Threshold selection overfits and the DD guard hides ruin
- **Impact**: Overstated robustness. The walk-forward 'proof' is weaker than it reports, so live deployment rests on exaggerated statistics.
- **Evidence**: 
  - best_thresh(): loops p in arange(0.50,0.92,0.02), scores roi*(wr/100)/max(dd,0.1)*log1p(n), keeps the best — all on the validation set vdf.
  - Drawdown: dd=((eq.cummax()-eq)/eq.cummax()*100).max(); gate is dd<100, which still 'passes' an equity curve that has lost everything then recovered.
- **Reasoning**: 
  - Choosing the threshold on the same rows used to score it is in-sample optimization; the selected threshold is optimistic and will not generalize. Separately, dd<100 permits a curve that touches −∞ in float terms only because cummax stays positive — a window can be a near-total wipeout and still register dd<100 and PASS.
  - Both inflate the pass rate. The committed 20/20 PASS, sub-2% DD results are consistent with an over-fit, under-stressed harness rather than a robust edge.

**Patch** (Holdout threshold + ruin-aware DD - run_all_6.py — best_thresh() & window gate):
```python
# split validation into choose-set and holdout-set
vp_choose, vp_hold = np.array_split(vdf.sort_values('entry_time'), 2)

def best_thresh(pdf):
    best=None; best_score=-1e9
    for p in np.arange(0.50,0.92,0.02):
        c=pdf[pdf['prob']>=p]; n=len(c)
        if n<MINTR: continue
        nw=(c['net_pnl']>0).sum(); wr=(nw/n)*100
        pnl=c['net_pnl'].sum(); roi=(pnl/CAP)*100
        eq=(CAP+c['net_pnl'].cumsum())
        # ruin-aware DD: equity must never go <= 0
        if (eq<=0).any(): continue
        dd=((eq.cummax()-eq)/eq.cummax()*100).max()
        if wr>0 and roi>-20:
            score=roi*(wr/100)/max(dd,0.1)*np.log1p(n)
            if score>best_score: best=p; best_score=score
    return best if best is not None else 0.55

bp = best_thresh(pred(m,fcs,vp_choose))
# RE-VALIDATE the chosen bp on the unseen holdout before accepting it
hp = pred(m,fcs,vp_hold)[pred(m,fcs,vp_hold)['prob']>=bp]
assert win_rate(hp) >= 0.5*TWR/100, "threshold fails holdout — reject window"
```

### BT-03: S2 advertises CVD but trades a price pullback
- **Impact**: Misleading strategy identity → wrong attribution of live PnL and a latent parity break if the label is ever 'fixed' to match its name.
- **Evidence**: 
  - Header docstring: '1. S2 now requires CVD momentum confirmation'.
  - make_signal_s2 docstring: 'S2: Deep Pure Trend (Replaced CVD logic)'.
  - make_signal_s2 body: out[(mc>0)&(p8<-0.20)]=1 — no CVD, no momentum term.
- **Reasoning**: 
  - Telemetry and logs route these trades as 'S2_CVD_Momentum', so an operator reading live output believes a CVD-confirmed regime is trading. The logic is actually identical-in-spirit to S3 (a price pullback), differing only by the p8 threshold (−0.20 vs −0.10). Two 'different' strategies that share a family are easy to confuse during incident triage.
  - If a future fix 'restores' CVD to match the name, S2's historical performance and live behavior change silently — a parity hazard hidden behind a misleading label.

**Patch** (Make the label honest (or honor it) - run_all_6.py — make_signal_s2):
```python
# Option A (recommended now): rename to match what it does.
STRATS = [
    ("S2_Deep_Trend", make_signal_s2),   # was "S2_CVD_Momentum"
    ...
]

# Option B (if CVD momentum is genuinely wanted): honor the name.
def make_signal_s2(df):
    """S2: trend pullback CONFIRMED by CVD momentum (zc20)."""
    out=np.zeros(len(df),dtype=np.int32)
    mc=df.get("mc",pd.Series(0,index=df.index)).values
    p8=df.get("p8",pd.Series(0,index=df.index)).values
    zc20=df.get("zc20",pd.Series(0,index=df.index)).values
    out[(mc>0)&(p8<-0.20)&(zc20>0.15)]=1
    out[(mc<0)&(p8>0.20)&(zc20<-0.15)]=-1
    return out
```

### LV-04: Tick rounding leaks basis points every trade
- **Impact**: Small but systematic expectancy drag and a parity gap between modeled and executed SL/TP.
- **Evidence**: 
  - ADAUSDT SHORT: intended sl 0.17488571 → exec_sl 0.1749 (looser by 1.4e-6).
  - intended tp 0.17197143 → exec_tp 0.172 (tighter by 2.9e-5).
  - For a short, looser SL = larger loss; tighter TP = smaller win — both adverse.
- **Reasoning**: 
  - The backtest floats carry full precision (entry−ATR), but the broker only accepts tick-quantized prices. The live rounding direction is not symmetric: SL rounds away from entry, TP rounds toward entry. Over a book of thousands of trades this is a systematic adverse drag the backtest does not model, on top of BT-01/BT-06.

**Patch** (Symmetric, logged tick rounding - Engine_1.py — SL/TP quantization):
```python
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
def D(x): return Decimal(str(x))

def quantize_sltp(entry, sl, tp, dr, tick):
    """SL always away from entry (looser), TP always toward entry (tighter).
       Both deltas are logged so the backtest can replicate the effect."""
    t = D(tick)
    e = D(entry)
    if dr == 1:  # long: SL below, TP above
        sl_q = (D(sl)).quantize(t, ROUND_FLOOR)
        tp_q = (D(tp)).quantize(t, ROUND_CEILING)
    else:        # short: SL above, TP below
        sl_q = (D(sl)).quantize(t, ROUND_CEILING)
        tp_q = (D(tp)).quantize(t, ROUND_FLOOR)
    return sl_q, tp_q, {
        "sl_delta": float(D(sl) - sl_q),
        "tp_delta": float(tp_q - tp_q),
    }  # ship delta to the ledger; feed it back into sim()
```

## Unverifiable Items

### U-01: Are asyncio.Lock and threading.Lock mixed over the same shared state?
- **Category**: Concurrency & Async
- **Risk**: HIGH
- **Why**: The file imports both asyncio and threading and runs ML_POOL/RENDER_POOL (threads) inside an asyncio loop. If a threading.Lock guards state also touched under an asyncio.Lock (or vice-versa), a thread can block the event loop or deadlock. The execution core where this matters is unreadable.
- **Grep**: `grep -nE 'asyncio\.Lock|threading\.Lock|RLock|self\._?lock' Engine_1.py`

### U-02: Are background asyncio.Task objects stored and cancelled on shutdown?
- **Category**: Concurrency & Async
- **Risk**: HIGH
- **Why**: create_task() without keeping a reference is collected mid-flight; tasks that are never awaited/cancelled leak across restarts and can fire stale orders after shutdown. The reader never reached the task-spawning code.
- **Grep**: `grep -nE 'asyncio\.create_task|ensure_future|\.cancel\(\)|_tasks|task\.done' Engine_1.py`

### U-03: Are websocket reconnection loops bounded by a retry limit?
- **Category**: Concurrency & Async
- **Risk**: HIGH
- **Why**: An unbounded 'while True: reconnect' on a downed endpoint burns CPU/CPU and can re-fire signals on every reconnect. The WS layer (~mid-file) was not retrievable.
- **Grep**: `grep -nE 'while True|async for|websockets\.connect|reconnect|backoff|max_retries|sleep\(' Engine_1.py`

### U-04: Is CVD delta computed from accumulator diffs, not viewport-relative DOM?
- **Category**: Data Integrity
- **Risk**: HIGH
- **Why**: CVD must be the running sum of (market buys − market sells). If live diffs a DOM snapshot, the 'CVD' fed to zc4/10/20 has no relation to the backtest's CVD — a silent parity break in every CVD-touching strategy (S1/S2/S5/S6).
- **Grep**: `grep -nE 'cvd|CVD|cumulative|delta|_prev_cvd|order_?book|bids|asks' Engine_1.py`

### U-05: Are liquidations accumulated per 15-min block (idx reset) correctly?
- **Category**: Data Integrity
- **Risk**: MEDIUM
- **Why**: Backtest sums liq over rolling(5) of per-candle Agg. Liq. Live must reset its 15-min bucket the same way; a never-reset accumulator or a viewport-relative sum diverges from backtest liql/liqlm and breaks S1.
- **Grep**: `grep -nE 'liq|liquidat|15m|candle_idx|reset|rolling|cumsum' Engine_1.py`

### U-06: Are feature vectors validated for NaN/Inf/OOB z-scores before inference?
- **Category**: ML Integrity
- **Risk**: HIGH
- **Why**: BT-04 proves the backtest sanitizes (badly). The live predictor (six_strategy_engine, imported but unreadable) must gate inference identically; an unvalidated vector yields a plausible-but-wrong probability that still trades.
- **Grep**: `grep -nE 'isnan|isinf|isfinite|clip|predict_proba|feature_vector|LiveSix' Engine_1.py six_strategy_engine.py`

### U-07: Is a stop-loss registered BEFORE the order is treated as filled?
- **Category**: Financial Safety
- **Risk**: CRITICAL
- **Why**: LV-01/03 strongly suggest a fill can be acknowledged before/without a confirmed stop. The exact ordering lives in the unread order/fill handler and must be confirmed line-by-line.
- **Grep**: `grep -nE 'place_order|stop|sl|on_fill|fill|NEW_ORDER|REGISTERED' Engine_1.py`

### U-08: Does the Risk Governor enforce session + day + per-position limits simultaneously?
- **Category**: Financial Safety
- **Risk**: HIGH
- **Why**: LV-06 shows the cooldown field is 0.0 (inactive). Whether session/day/per-position limits compound correctly — and whether a breach actually halts new entries — could not be verified.
- **Grep**: `grep -nE 'drawdown|max_dd|daily|session|per_position|consecutive|cooldown|governor|halt' Engine_1.py`

### U-09: Are model thresholds loaded from saved .pkl metadata, not hardcoded?
- **Category**: ML Integrity
- **Risk**: MEDIUM
- **Why**: Backtest derives bp via best_thresh() per window. If live hardcodes 0.50/0.55 it ignores the validated threshold and trades a different strategy than backtest 'proved'.
- **Grep**: `grep -nE '\.pkl|joblib|pickle|load|threshold|0\.5[05]?|best_thresh' Engine_1.py six_strategy_engine.py`

### U-10: Are floats ever compared with == on price/monetary data?
- **Category**: Data Integrity
- **Risk**: MEDIUM
- **Why**: LV-02 shows everything is float. Any 'if pnl == 0' or 'if price == sl' equality is non-deterministic and will skip/trigger logic at random — directly enabled by the float-arithmetic finding.
- **Grep**: `grep -nE '== *\d|!= *\d|price ==|== *price|pnl ==|== 0\.0' Engine_1.py`

