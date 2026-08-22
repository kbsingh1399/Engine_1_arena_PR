# LIVE ENGINE PARITY AUDIT — `run_all_6.py` vs `Engine_1.py`

**Verdict: LIVE PARITY NOT VERIFIED (before this patch).** 7 material divergences found, all now corrected.
Every claim below is backed by a runnable harness in `tools/parity_audit/`.

---

## 0. Two premises in the brief did not hold

**0.1 — `MIN_PROB_THRESHOLD` and `VALIDATION_WR_BUFFER = 5.0` do not exist.**
```
$ grep -rn "MIN_PROB_THRESHOLD\|VALIDATION_WR_BUFFER" .      # no matches
$ git log --all -S "MIN_PROB_THRESHOLD"                       # no commit ever
```
`risk_config.py` defines `TWR=40.0, TROI=20.0, TDD=30.0, MINTR=6, TP=5.0, TRA=0.8, MAXTR=50`.
There is no fixed 0.55 floor: the backtest grid floor is **0.51** (`np.arange(0.51,0.92,0.02)`), and
`0.55` appears only as an *uncalibrated live default*. There is no ±5.0 WR buffer; the gate is `wr > TWR`.
I audited against the constants that actually exist.

**0.2 — The backtest is 119/120, not 120/120.** `all_6_results.json` on `main`:
```
S1 20/20   S2 20/20   S3 19/20  <-- W1 FAIL   S4 20/20   S5 20/20   S6 20/20
S3 W1: wr=40.0, threshold=0.51, tr=50  ->  passed=False   (gate is wr>40, 40.0 is not >40)
```
This is the same failure as `fable_5_s3_w1_fix_prompt.md`. `main` was never fixed. The live engine is
therefore being aligned to a baseline with one known-failing window — worth resolving separately.

---

## 1. Discrepancies found

### D1 — Position sizing was 7.9%–64.3% below the backtest *(CRITICAL)*
`sim()` sizes `u = min(RSK/sd, MAX_NOTIONAL/entry)` with `sd = atr`, raw. `trigger_entry` padded the
denominator with friction before dividing:
```python
TOTAL_FRICTION = ENGINE_FEE_RT + 0.0004          # 0.0012
effective_stop_dist = stop_dist + entry_price*TOTAL_FRICTION
units = risk_capital / effective_stop_dist
```
`tools/parity_audit/t3_sizing.py`:
| symbol | entry | atr | backtest units | live units | error |
|---|---|---|---|---|---|
| BTCUSDT | 60000 | 350 | 0.0571 | 0.0474 | **−17.06%** |
| ETHUSDT | 3000 | 22 | 0.9091 | 0.7812 | −14.06% |
| SOLUSDT | 150 | 2.1 | 9.5238 | 8.7719 | −7.89% |
| BTC (tight ATR) | 60000 | 40 | 0.5000 | 0.1786 | **−64.29%** |

Fees are already subtracted from PnL; charging them again in the size double-counts, and the error is
ATR-dependent, so realized R per trade no longer equals the validated 1R. Also, the live path keyed off
the broker-adjusted `stop_dist`, not the entry ATR. **Fixed** — plus an `ATR_EPSILON` guard (the old
`atr>0` admitted the `1e-6` sentinel and would size `RSK/1e-6`) and a boot-time 1R drift guard.

### D2 — The broker re-sized every order, overriding the tracker *(CRITICAL)*
`binance_broker.execute_trade` independently recomputed `qty` from the same padded stop, so the lot sent
to Binance differed from the `units` the tracker recorded. Every PnL, `live_pnl_usd`, and open-stop-risk
figure derived from `units` was wrong. **Fixed** — the broker now honours caller-supplied `units`.

### D3 — Strategy-key mismatch made the six-strategy path dead code *(FATAL)*
`six_strategy_engine.py` did `from signals_shared import STRAT_MAP as SIGNAL_FUNCS` — keyed by **long**
names — but every consumer assumes **short** keys. `tools/parity_audit/t2_keys.py`:
```
load_models() looked for : six_strategy_models/S1_Liquidation_BTCUSDT.pkl   (never written)
train_six_strategy writes: six_strategy_models/S1_BTCUSDT.pkl
STRATEGY_NAMES['S1_Liquidation'] -> KeyError                                 <-- FATAL
```
Result: 0 models load → every symbol returns `NO_MODEL`, and any signal that got through raised
`KeyError` inside the swallowing `try/except`. **Fixed** by re-keying to short keys + boot assertions.

### D4 — Threshold gate did not match the backtest
`run_all_6` applies one fixed threshold: `tp[tp['prob'] >= bp]`. Live had two deviations:
`prob < (effective_thresh - 1e-5)` admitted trades the backtest rejects, and `_thresh_lift` (+0.05/loss,
capped +0.25) rejected trades the backtest takes. **Fixed** — exact `>=`, lift now opt-in.

### D5 — Deployed threshold disagreed with the walk-forward threshold on 12/12 trials *(CRITICAL)*
`train_six_strategy.best_thresh` diverged on five axes: grid floor `0.50` vs `0.51`; count window
`[MINTR, ∞)` vs `[MINTR*2, MAXTR]` with no rank fallback; `wr>=TWR` vs strict `wr>TWR`; closed-equity DD
vs `max(closed, mark-to-market)`; and — most seriously — `net_pnl` is a **fraction of CAP** here
(`_sim_trade` returns `RISK_PCT`-scaled PnL) but **USD** in the backtest, so ROI/DD were ~5000× too small
and `dd<TDD` could never bind (`t6_ddgate.py`: 4.885% vs 0.00105%). `t5_thresh.py`: **12/12 mismatch
before, 0/12 after.**

### D6 — Blocked models were deployed with an uncalibrated gate
When no threshold passed, the trainer fell back to `0.55` and saved a live model; `load_models` also
defaulted `threshold` to `0.55` and registered `models=None`. Both now fail closed.

### D7 — `_dir_suspend_until` key-shape mismatch (dead safety filter)
Written as `(symbol, direction, strategy)`, read as `(symbol, direction)` — the lookup always missed, so
the loss-suspension never fired. Live-only filter, but a silently dead one. **Fixed.**

---

## 2. Modules verified as ALREADY at parity

- **Signal generation** — both `run_all_6.py` and the live path import `signals_shared.STRAT_MAP`; single
  source of truth, no duplicated formulas. All 6 verified identical.
- **`featurize`** — `t1_featurize.py`: identical outputs on all shared columns except `rsi` at **bar 0
  only** (backtest `0.0`, live `50.0`), a warmup artifact at an index no trade can use (`gen_trades`
  starts at `i=200`). Live adds 6 extra columns (`ef_slope`, `z*_qty`…) that no signal reads.
- **`sim()` math** — `t4_sim.py`: `net`, `bh`, and `R` match to machine precision across randomized paths
  (live returns PnL as a fraction of CAP; identical after ×CAP). 5R arm / 0.8R trail / 288-bar timeout /
  no hard TP all confirmed, on both exchange and local sides.
- **Cooldown vs `bh`** — `t7_cooldown.py`: backtest `cd = i+bh+2` ⇒ exactly 2 bars after exit,
  independent of `bh`; live uses a flat 1800 s from exit = 2 × 15 m. **Exact match.**
- **Fee constant** — `FEE_RT=0.0008` shared via `risk_config`, enforced by `assert_fee_parity()`.

---

## 3. Residual risks (not code parity, but they will break live results)

1. **S3 W1 still fails** — the live engine is being aligned to a 119/120 baseline.
2. **`six_strategy_models/` does not exist in the repo** and `backtesting_data/` is absent, so I could not
   execute `run_all_6.py` end-to-end here. D3 means **no model has ever loaded**, so any prior "live
   parity" observation was of a path that never traded. Re-run `train_six_strategy.py` after this patch.
3. **Live entry fills at `snap.price` (current tick); the backtest enters at `o[i+1]`** (next bar's open).
   Structural simulation-vs-reality gap, not fixable by code alone — worth quantifying.
4. **Broker `_validate_profit_threshold`** can reject trades the backtest takes (R:R < 0.5 after fees).
   It is bypassed when `tp=None`, but is live-only logic with no backtest counterpart.
5. **Live-only governors with no backtest equivalent** — correlation cap (3 same-direction), 4% portfolio
   stop-risk cap, daily/total DD guardrails, consecutive-loss breaker, drift detector, Ruflo gate. Each
   can only *reduce* trades vs the backtest. Intentional as risk control, but they mean live trade counts
   will be a subset of simulated ones.

---

## 4. Files changed

| File | Change |
|---|---|
| `Engine_1.py` | Parity sizing, ATR/1R guards, `PARITY_TP`/`PARITY_TRA`, forwards `units` |
| `engine_components/binance_broker.py` | Honours caller `units`; no re-derivation |
| `six_strategy_engine.py` | Key re-map + assertions, fail-closed loading, exact threshold, ATR sentinel, suspend key |
| `train_six_strategy.py` | `best_thresh` ported byte-for-byte; USD normalization; no silent 0.55 |
| `tools/parity_audit/` | 9 reproducible harnesses (new) |

Run `python tools/parity_audit/final_verify.py` → **18/18 checks pass**.
