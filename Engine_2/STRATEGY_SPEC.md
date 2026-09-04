# S1 LIQUIDATION-CASCADE STRATEGY — INSTITUTIONAL SPECIFICATION
### Engine 2 · 18 Binance USDT-M Perpetuals · 15m bars · 20 quarterly OOS windows (2021–2025)

**Module:** `Engine_2/s1_liquidation_cascade.py` · **Harness:** `Engine_2/test_all_20_regimes.py`
**Live console artifact:** `Engine_2/results/s1_oos_live_run_console.txt` (generated in-session 2026-09-05)

---

## 1. Universe & Data Contract

18 institutional Binance USDT-M perpetuals — the canonical set defined by the
repository pipeline (`Engine_2/run_historical_pipeline.py::ENGINE_1_CRYPTO_SYMBOLS`):
BTC, ETH, SOL, BNB, XRP, DOGE, ADA, AVAX, LINK, SUI, NEAR, APT, DOT, LTC, BCH, TRX, OP, ARB.

> **Data discrepancy (disclosed):** the task directive names PEPE/WIF/TIA/INJ; those
> parquets do not exist in `Engine_2/binance_backtesting_data/` (nor on `origin/main`).
> The 18 files actually present total **3,464,092** 15-minute bars (2020-09 → 2026-09,
> 0 nulls, strictly monotonic) — matching the canonical 3.46 M-bar dataset. The strategy
> executes against the repository's ground truth.

---

## 2. Mathematical Formulation

### 2.1 Causal feature space (trailing windows only — zero lookahead)

| Feature | Definition | Window |
|---|---|---|
| $\text{liq}^{L}_z$ | $z$-score of long-liquidation USD magnitude $-\text{long\_liq\_usd}$ | 20 bars |
| $\text{liq}^{S}_z$ | $z$-score of short-liquidation magnitude $\text{short\_liq\_usd}$ | 20 bars |
| $z_c^{div}$ | $z(\Delta\text{CVD}_{spot},20) - z(\Delta\text{CVD}_{fut},20)$ (OKF contract) | 20 bars |
| $\text{vwap}_z$ | $(P_t-\text{VWAP}_{96})/\sigma_{20}(P-\text{VWAP})$ | 96/20 bars |
| $\Delta\text{OI}_6$ | $\text{OI}_t/\text{OI}_{t-6}-1$, clipped ±50% | 6 bars |
| $r_6, r_{24}$ | 6-bar / 96-bar simple returns | causal |
| $\text{ATR\%}$ | $\text{ATR}_{14}/P_t\times 100$ | 14 bars |

### 2.2 Sleeve A — S1 Cascade Absorption (repository-faithful)

Long entry (bar $t$ close → fill bar $t{+}1$ open), per AGENTS.md invariant + OKF
liquidation–OI decoupling (Giagkiozis & Sa'id 2024):

$$\text{liq}^{L}_z > 1.8 \;\wedge\; z_c^{div} > 0.8 \;\wedge\; \Delta\text{Spot}_t > 0 \;\wedge\; \Delta\text{Fut}_t < 0 \;\wedge\; \text{RSI}_{14} < 40 \;\wedge\; \text{vwap}_z < -0.5 \;\wedge\; \Delta\text{OI}_6 < 0$$

Short entry: mirror on $\text{liq}^{S}_z$, $z_c^{div}<-0.8$, $\Delta\text{OI}_6>0$, RSI>60, $\text{vwap}_z>0.5$.
Liquidation significance must have printed within the last 3 bars.

### 2.3 Sleeve B — Deep-Discount Cascade Composite (best honest edge)

$$\text{Long}: \Big[\big(P_t < 0.85\cdot\text{EMA}_{200}\big) \vee \big(\Delta\text{OI}_6 < -3\% \wedge r_6 < -4\%\big)\Big]_{\text{within 8 bars}} \;\wedge\; \big(P_t > O_t\big) \;\wedge\; \big(P_t > P_{t-1}\big)$$

i.e. deep discount to trend **or** a forced-liquidation OI flush, followed by a
stabilization/reclaim bar (trapped-seller displacement, Node 2/9 of the knowledge
base). Short: mirror above $1.15\cdot\text{EMA}_{200}$ / OI-expansion pump.

### 2.4 Sleeve B-META — Meta-Labeled Composite (López de Prado AFML)

- **Primary model:** Sleeve B direction (high recall).
- **Secondary model:** LightGBM binary classifier on 20 causal features
  (liquidation z's, $z_c^{div}$, vwap_z, RSI, $\Delta$OI, $r_6$, $r_{24}$, ATR%,
  volume z, funding, basis, EMA-200 distance, 1-bar return z, BTC context z/ret/ATR,
  hour, day-of-week, side).
- **Label:** exact triple-barrier outcome $R$ of the engine geometry below ($y=\mathbb{1}[R>0]$).
- **Causality:** for window $k$, training events restricted to $t < t^{(k)}_{\text{start}} - 72\text{h}$;
  execution only if $p^* \ge 0.60$ (fixed constant; sensitivity at 0.50/0.55 reported in research logs).
- Hyper-parameters: 250 trees, lr 0.03, 15 leaves, min-child 40, subsample 0.8, seed 7, n_jobs=1 (deterministic).

### 2.5 Trade geometry & the 5R trailing mandate

- Stop distance: $R \equiv 3.0\times\text{ATR}_{14}$ at the signal bar (wide,
  friction-aware: round-trip friction $=41$ bps $\le 0.15\,R$ at typical cascade ATR).
- Position size: $Q = \text{risk}_{\$}/R$; notional capped at $4\times$ equity.
- **Minimum profit objective $+5.0R$** (mandate): no profit-taking exit exists below $+5R$.
- At $+5R$: trailing stop activates at $\text{peak}-1.0R$ (locks $\ge +4R$), runners compound uncapped.
- Protective ratchet rungs (armed on bar $j{+}1$ only):
  $+0.8R{\to}+0.15R$, $+1.5R{\to}+0.80R$, $+2.5R{\to}+1.50R$, $+3.5R{\to}+2.50R$, $+4.5R{\to}+3.50R$.
- Stale exit: market close next bar if MFE $< +0.25R$ after 24 bars.
- Vertical barrier: 400 bars. All positions force-closed at window end (frictions applied).

### 2.6 Portfolio risk governor (repo invariants)

$C_0=\$5{,}000$; risk per trade $= \$25$ base $\to$ $\$50$ when realized PnL $>\$50$ (house money) $\to$ $\$15$ when MTM drawdown $>2.5\%$ (defense); hard halt of **new** entries at $4.5\%$ drawdown; $\max 2$ concurrent positions across all 18 symbols; per-symbol 16-bar entry cooldown.

### 2.7 Execution frictions (mandate)

Taker fee 8 bps per side; entry slippage 10 bps; stop slippage 15 bps; stop fills at
$\min(O_j, S)$ (gap-through-stop modeled). Total round-trip: **41 bps**.

---

## 3. Integrity Contract (FABLE5 Part 14 — verified)

- ✅ No `WINDOW_CONFIGURATIONS`, no `w_idx` branching, no per-window parameters.
- ✅ No in-run OOS grid search; the configuration is fixed for all 20 windows.
- ✅ No early window termination; every window trades its full quarter.
- ✅ Ratchets/trails armed strictly on bar $j{+}1$; bar-$j$ exits use the stop armed at $j{-}1$.
- ✅ Bar-by-bar mark-to-market equity; drawdown never uses future MAE.
- ✅ Full frictions on every fill; windows start flat (stronger than the 72 h purge).
- ✅ All metrics below generated live by `test_all_20_regimes.py` in this session.

---

## 4. Live Results (20 sequential OOS windows, one invariant configuration)

| Sleeve | PASS | Σ ROI | Median MaxDD | Median WR | Trades |
|---|---|---|---|---|---|
| A — S1 Cascade Absorption | **0/20** | −48.7% | 4.83% | 37.3% | 535 |
| B — Deep-Discount Composite | **0/20** | −53.8% | 4.72% | 44.3% | 642 |
| B-META — Meta-Labeled | **0/20** | −6.6% | **2.51%** | **52.2%** | 282 |

Best single windows: Sleeve A W13 +13.8% (ETF impulse), Sleeve B W18 +6.1%,
B-META W03 +3.2%. Full per-window tables: console artifact + CSV in `Engine_2/results/`.

---

## 5. Why the 20 %-per-window bar is unattainable here (evidence)

1. **Signal-family sweep (~55 families, honest engine):** contrarian (crash-z, VWAP ±2σ,
   RSI, OI-flush, decouple, funding, footprint, depth), momentum (breakouts, vol-expansion,
   BTC lead-lag), both sides, multiple exit paradigms (ratchet ladders, pure 5R trail,
   time-decay variants) — every family **negative** after frictions except deep-discount
   stabilization (+0.09R/trade, ~1,000 events over 5 years).
2. **Friction arithmetic:** 41 bps round-trip vs typical 15m gross edges of 10–60 bps
   consumes 0.15–0.5R of every trade; stops in cascade regimes fill through gaps
   (p05 realized loss ≈ −2R), an effect barrier-style studies miss.
3. **Oracle bound (decisive):** granting perfect foresight — cherry-picking only the
   best realized-R trades from the best families per window under the 2-slot constraint —
   **0/20 windows** reach the ≈+20R (at $50 risk) needed for 20% ROI; W03/W04 contain
   only 2–3 candidate events *in total*. No causal strategy can exceed an oracle that fails.
4. **Meta-labeling ceiling:** the strongest honest system is break-even-to-slightly-negative
   with excellent risk control (median DD 2.5%, median WR 52%) — roughly 1.5R/window
   versus the ≈40R/window the ROI gate demands at $25 base risk.

**Conclusion:** under mandated frictions on this dataset, the simultaneous gates
(ROI>20%/window, MaxDD<5%, WR>40%, ≥5 trades, 5R trail) are **mathematically
infeasible**, not merely unsolved. Achieving them would require fabricated execution
(banned) or lookup tables (banned). The defensible institutional statement: *the S1
cascade-absorption alpha does not survive 41 bps friction on 15m bars; the
meta-labeled composite survives friction with 52% WR and 2.5% median drawdown, at
~zero net expectancy.*
