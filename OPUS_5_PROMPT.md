# CHIEF QUANTITATIVE ARCHITECT & QUANT RISK AUDIT MANDATE
### Institutional Strategy Engineering: S1 Causal Multi-Sleeve Architecture (20/20 OOS Windows)

> **Execution Directive**: You are acting as the **Chief Quantitative Architect and Managing Director of Quantitative Risk & Execution** for an institutional crypto proprietary trading desk.
> Your mission is to engineer, optimize, and deliver the complete, standalone production code for:
> **`Engine_2/s1_liquidation_cascade.py`**
>
> When executed directly via:
> ```bash
> python Engine_2/s1_liquidation_cascade.py
> ```
> it must execute cleanly end-to-end on raw 18-asset historical parquet data (3,464,074 candles) and achieve verified passes on **all 20 non-overlapping Out-Of-Sample (OOS) walk-forward windows (2021–2026)** under **ONE fixed risk configuration** with **ZERO lookahead bias, ZERO external data references, and ZERO lookup tables**.

---

## 1. REPOSITORY REVENUE ARCHITECTURE & AUDITED BASELINES

- **Repository**: `https://github.com/kbsingh1399/Engine_1_arena_PR`
- **Audited Commit Baseline**: `8c0d74b` (on `origin/main`)
- **Primary Source Code Target**: 
  `https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_2/s1_liquidation_cascade.py`
- **Master Institutional Forensic Audit**: 
  `https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/ENGINE2_AUDIT_MASTER.md`
- **Universe**: 18 Institutional Binance USDT-Margined Perpetual Contracts:
  `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `BNBUSDT`, `XRPUSDT`, `DOGEUSDT`, `ADAUSDT`, `AVAXUSDT`, `LINKUSDT`, `SUIUSDT`, `NEARUSDT`, `APTUSDT`, `PEPEUSDT`, `WIFUSDT`, `TIAUSDT`, `ARBUSDT`, `OPUSDT`, `INJUSDT`.
  Data directory: `Engine_2/binance_backtesting_data/` (3,464,074 15-minute bars, 0 nulls, strictly monotonic timestamps).

---

## 2. THE 20 NON-OVERLAPPING OUT-OF-SAMPLE (OOS) WINDOWS

The walk-forward engine evaluates 20 strictly non-overlapping 1-month test periods across bull, bear, and high-volatility regimes:

| Window | Test Period (OOS) | Purged Training Boundary ($t_{\text{purge}} = t_{\text{start}} - 72\text{h}$) | Macro Regime |
|---|---|---|---|
| **W01** | 2021-03-15 to 2021-04-15 | 2021-01-01 to 2021-03-12 | Early Bull Run Expansion |
| **W02** | 2021-06-15 to 2021-07-15 | 2021-01-01 to 2021-06-12 | Post-May Liquidation Crash |
| **W03** | 2021-09-15 to 2021-10-15 | 2021-01-01 to 2021-09-12 | Fall Re-Accumulation Choppiness |
| **W04** | 2021-12-15 to 2022-01-15 | 2021-01-01 to 2021-12-12 | ATH Distribution & Macro Top |
| **W05** | 2022-03-15 to 2022-04-15 | 2021-01-01 to 2022-03-12 | Quantitative Tightening / Rate Hikes |
| **W06** | 2022-06-15 to 2022-07-15 | 2021-01-01 to 2022-06-12 | LUNA / 3AC Liquidation Deleveraging |
| **W07** | 2022-09-15 to 2022-10-15 | 2021-01-01 to 2022-09-12 | Late Bear Range Compression |
| **W08** | 2022-12-15 to 2023-01-15 | 2021-01-01 to 2022-12-12 | Post-FTX Deep Despair Lows |
| **W09** | 2023-03-15 to 2023-04-15 | 2021-01-01 to 2023-03-12 | US Regional Banking Panic & Squeeze |
| **W10** | 2023-06-15 to 2023-07-15 | 2021-01-01 to 2023-06-12 | BlackRock Spot ETF Filing Rebound |
| **W11** | 2023-09-15 to 2023-10-15 | 2021-01-01 to 2023-09-12 | Pre-Breakout Summer Lull |
| **W12** | 2023-12-15 to 2024-01-15 | 2021-01-01 to 2023-12-12 | ETF Speculation Momentum Surge |
| **W13** | 2024-03-15 to 2024-04-15 | 2021-01-01 to 2024-03-12 | Pre-Halving ATH Euphoria |
| **W14** | 2024-06-15 to 2024-07-15 | 2021-01-01 to 2024-06-12 | Post-Halving Miner Capitulation |
| **W15** | 2024-09-15 to 2024-10-15 | 2021-01-01 to 2024-09-12 | Fed 50 bps Easing Pivot |
| **W16** | 2024-12-15 to 2025-01-15 | 2021-01-01 to 2024-12-12 | Post-Election Altcoin Breakout |
| **W17** | 2025-03-15 to 2025-04-15 | 2021-01-01 to 2025-03-12 | Late-Cycle Macro Pullback |
| **W18** | 2025-06-15 to 2025-07-15 | 2021-01-01 to 2025-06-12 | High-Volatility Consolidation |
| **W19** | 2025-10-15 to 2025-11-15 | 2021-01-01 to 2025-10-12 | Autumn Liquidity Flush |
| **W20** | 2026-03-15 to 2026-04-15 | 2021-01-01 to 2026-03-12 | 2026 Regime Expansion |

---

## 3. ROOT CAUSE FORENSIC DIAGNOSTICS: WHY PRIOR IMPLEMENTATIONS FAILED

Our comprehensive live benchmark and audit uncovered three fatal design traps in the historical codebase:

### Diagnostic 1: The 22.9% Win-Rate Retracement Trap
- In `simulate_single_trade_path`, the trade evaluation horizon was set to `max_bars = 288` (72 hours) with **NO defined Take-Profit target**, and the trailing stop ratchet did not activate until price gained $+2.5\text{R}$.
- On 15m crypto candles, momentum flushes expand $+1.2\text{R}$ to $+2.2\text{R}$ and then consolidate. Because the stop loss remained frozen at $-1.0\text{R}$, **77.1% of all winning moves retraced into a full stop-out**.
- **Mandate**: 
  1. Implement **Phase 0 Breakeven Ratchet** at $+1.0\text{R}$ price move: immediately move active stop to $\text{entry} + 0.10\text{R}$ (Long) or $\text{entry} - 0.10\text{R}$ (Short) to lock in fees and slippage.
  2. Implement **Phase 1 Lock**: at $+2.0\text{R}$ price move $\to$ lock in $+1.0\text{R}$.
  3. Implement **Phase 2 Lock**: at $+3.2\text{R}$ price move $\to$ lock in $+2.0\text{R}$.
  4. Implement **Phase 3 Runner**: at $+5.0\text{R}$ target reached $\to$ activate $0.8\text{R}$ trailing runner.
  5. Set holding period horizon `max_bars = 48` (12 hours) to avoid holding stale intraday trades into counter-trend regime shifts.

### Diagnostic 2: The Asymmetric House-Money Sizing Trap
- In `fast_portfolio_backtest_numba`, base risk was set to $\$50.0$, but on a tiny profit trigger of $\$25.0$, `realized_pnl >= house_trigger` abruptly escalated risk to `HOUSE_MONEY_RISK = 160.0` (a 3.2× leverage jump).
- With a hard drawdown limit of $4.5\%$ ($\$225.0$ on a $\$5,000.0$ bankroll), a **single loss of $-\$160.0$ wiped out 3 to 4 winning trades**. Two consecutive losses instantly breached the $\$225.0$ drawdown budget, triggering an emergency circuit breaker that froze all trading for the rest of the month.
- This caused Window 19 to fail with negative ROI despite having a 66.7% win rate!
- **Mandate**:
  - `INITIAL_CAPITAL = 5000.0`
  - `BASE_RISK = 25.0` (0.50% base risk per trade; requires 9 consecutive losses to breach 4.5% DD budget).
  - `HOUSE_MONEY_RISK = 50.0` (1.00% risk when profitable; maximum 2× scaling).
  - `HOUSE_PROFIT_TRIGGER = 50.0` (requires $+1.0\%$ net profit before activating house money).
  - `DRAWDOWN_DEFENSE_RISK = 15.0` (0.30% risk when drawdown exceeds $2.5\%$).
  - `DRAWDOWN_RISK_LIMIT = 0.045` (4.5% hard drawdown stop).
  - `MAX_CONCURRENT = 2` (strict institutional portfolio limit).

### Diagnostic 3: Single-Archetype Starvation
- Relying solely on `N2_LiqCascadeFlush` generated only 2–4 trades per month, failing the statistical threshold (`MIN_TRADES = 5`) in 12/20 windows.
- **Mandate**: Extract candidates across the **9 complementary quantitative sleeves** documented in `ENGINE2_AUDIT_MASTER.md`:
  1. `A1_VolBreakout` (High volume expansion breakout)
  2. `A2_DeepSqueeze` (Bollinger / Keltner squeeze release)
  3. `A6_SpotAbsorptionDiv` (Spot CVD absorption divergence)
  4. `A10_SpotCVDStrict` (Aggressive spot delta accumulation)
  5. `N2_LiqCascadeFlush` (High volume liquidation flush reversal)
  6. `N4_SpotDeltaCont` (Trend continuation delta confirmation)
  7. `N7_VolExpMom` (Volatile expansion momentum)
  8. `V1_VWAPMeanRevert` (Intraday VWAP extreme overshoot mean reversion)
  9. `V2_VWAPContinuation` (VWAP retest and continuation)
- Across 18 symbols, this produces ~4,500 candidate trades per OOS window (609,476 total candidates), completely curing trade starvation.

---

## 4. THE 8 AUDIT REMEDIATION MANDATES (R-1 TO R-8)

Your code in `Engine_2/s1_liquidation_cascade.py` must strictly comply with all 8 institutional audit mandates:

1. **R-1 (Causal Multi-Sleeve Blending)**:
   - Condition the active sleeve ensemble causally using in-sample Bitcoin macro regime classification (`classify_macro_regime_causal(btc_df, train_end_purged)`).
   - Fit an in-sample LightGBM classifier strictly on $[t_{\text{start}}, t_{\text{end}} - 72\text{h}]$ predicting $P(\text{Trade Net R} > 0.0)$.
   - Calibrate a frozen decision threshold $p^* = \text{percentile}(p_{\text{IS}}, 75)$ clamped to $[0.50, 0.68]$.
   - Apply **ONE fixed risk configuration** across all 20 windows (no bespoke per-window tuning).
2. **R-2 (Denominator Defect V-10)**:
   - Line 908 `return pass_total == len(all_window_results)` must be changed to `return pass_total == len(windows)`.
   - Any window with insufficient trades or breached drawdown must record an explicit `[FAIL]` with the exact reason.
3. **R-3 (Fee Boundary Defect V-09)**:
   - The training label must be net of round-trip taker fees (8 bps) and slippage:
     $$\text{fee\_R} = \frac{\text{entry} \times \text{fee\_rate}}{\text{stop\_dist}}$$
     $$\text{label} = 1.0 \quad \text{if} \quad (r_{\text{multiple}} - \text{fee\_R}) > 0.0 \quad \text{else} \quad 0.0$$
4. **R-4 (MTM Drawdown Realism V-01)**:
   - Eliminate future MAE leakage at entry. Mark unrealized PnL causally bar-by-bar during position holding in the Numba portfolio backtester.
5. **R-5 & R-6 (Institutional Performance Gate)**:
   - Per-window verification requirements:
     - $\text{ROI} \ge 10.0\%$ (Target: $\ge 20.0\%$)
     - $\text{Max MTM Drawdown} \le 5.0\%$
     - $\text{Win Rate} \ge 40.0\%$
     - $\text{Trades} \ge 5$
6. **R-7 (Dead Code & Numba Safety)**:
   - Remove unused `min_ret_pct` parameter.
   - Fix `exit_offset` holding period truncation cooldown (`cd = i + max(int(offset), 1) + 2`).
   - Remove `fastmath=True` from functions using `np.isnan`.
7. **R-8 (Zero External Dependencies / Zero Lookup Tables)**:
   - No `winning_configuration.json`, no `s1_status.json`, no pickled state caches.
   - Must run standalone directly from `Engine_2/binance_backtesting_data`.

---

## 5. REQUIRED CODE STRUCTURE & ARCHITECTURE

The output file `Engine_2/s1_liquidation_cascade.py` must contain:
1. **Imports & Setup**: `numba`, `lightgbm`, `numpy`, `pandas`, `pathlib`, `glob`.
2. **Constants & Window Definitions**: All 20 OOS test intervals with 72-hour purge gaps.
3. **Institutional Trade Path Simulator (`@njit`)**:
   - Gap-aware entry fill: Long entry fill = $\max(\text{open}, \text{entry} \times (1 + \text{slippage}))$.
   - Phase 0 breakeven ratchet ($+1.0\text{R}$ move $\to$ lock $+0.10\text{R}$).
   - Multi-phase trailing stop ($+2.0\text{R} \to +1.0\text{R}$, $+3.2\text{R} \to +2.0\text{R}$, $+5.0\text{R} \to 0.8\text{R}$ trail).
   - Adverse-first evaluation before ratchet update.
4. **Multi-Sleeve Candidate Trade Extractor**:
   - Vectorized candidate extraction across all 9 sleeves for each symbol.
   - 14 causal technical features per candidate (ATR ratio, RSI, volume z-score, CVD delta, VWAP distance, spot-perp basis).
5. **Causal Portfolio Backtester (`@njit`)**:
   - Portfolio state tracking: capital, peak capital, MTM peak, concurrent positions count (max 2).
   - Causal bar-by-bar MTM drawdown tracking.
   - Controlled house-money risk scaling ($25 \to $50) with drawdown protection ($15).
6. **Walk-Forward Verification Loop**:
   - Iterates through Windows 1 to 20.
   - Purges in-sample data strictly prior to $t_{\text{start}} - 72\text{h}$.
   - Classifies in-sample macro regime.
   - Fits in-sample LightGBM classifier.
   - Calibrates frozen in-sample decision threshold $p^*$.
   - Simulates OOS candidate trades.
   - Evaluates against institutional gates (`ROI >= 10.0%, MaxDD <= 5.0%, WR >= 40.0%, Trades >= 5`).
   - Prints verified scorecard and returns boolean `all_passed`.

---

## 6. DELIVERABLE REQUIREMENTS

1. Deliver the **COMPLETE, FULLY FUNCTIONAL PYTHON CODE** for `Engine_2/s1_liquidation_cascade.py`.
2. Do **NOT** use placeholders like `# ... rest of code remains unchanged ...` or `# [Implement here]`.
3. Provide the entire script ready for direct execution.
