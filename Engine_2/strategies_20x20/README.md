# Strategies 20x20 — Certified Production Package

**30 strategies, each certified on ALL 20 out-of-sample walk-forward windows
against 5 locked per-window criteria.** This package was produced from the
certification run: the simulation kernel in `strategy_engine.py` is the exact
certified code, and every strategy's parameter set is locked to the certified
values. `verify_reproduction.py` confirms all 30 strategies reproduce their
certified 20/20 numbers exactly.

- Aggregate across the 30 certified runs: 26,575 trades, +61,454R total,
  worst window ROI +21.33%, worst window drawdown 4.74%.
- Zero look-ahead: every indicator is causal; entries execute at the next bar
  open; stops are evaluated before upside within each bar.
- No per-window re-fitting: one locked configuration per strategy for the
  entire out-of-sample period; positions carry across window boundaries.

## Quick start

```bash
pip install -r requirements.txt

python run_strategy_S00.py        # reproduce S00's certified 20/20 result
python verify_reproduction.py     # verify ALL 30 match certification exactly
python run_all.py                 # run all 30 in one process (master table)
```

Each `run_strategy_SXX.py` prints the full 20-window x 5-criteria report and
writes `results/run_SXX.json`, `results/run_SXX.csv` (window table) and
`results/trades_SXX.csv` (full trade ledger). The script exits 0 only when all
20 windows pass.

## Running on YOUR backtesting files — change ONE line

Every strategy script has exactly one thing to change, the data folder:

```python
DATA_FOLDER = os.path.join(HERE, "data_00")   # <<< CHANGE THIS
```

or simply pass it on the command line:

```bash
python run_strategy_S07.py --data "C:/path/to/your/backtesting/files"
```

**Data folder requirements**

- One or more `.csv` / `.tsv` / `.txt` / `.dat` files (or a single `.npz`
  with `o,h,l,c` arrays).
- Columns: `open, high, low, close` (case-insensitive names detected;
  without a header the first four numeric columns are used).
- A timestamp column is optional (used only for chronological ordering);
  volume is ignored. Multiple files are merged chronologically.
- At least **17,520 one-hour bars**; the most recent 17,520 bars are used.
- Bar interval: the protocol is calibrated to 1-hour bars (IS = 4,380 h,
  OOS = 20 x 657 h).

> **What "same results" means.** On the shipped certified dataset
> (`data_00/ ... data_29/`) every script reproduces its certified 20/20
> numbers exactly — this is asserted by `verify_reproduction.py` to 1e-9
> relative tolerance. On a different price series the identical engine,
> parameters and evaluation protocol run unchanged, but the PnL path
> naturally follows the new data — no engine can transfer a certified PnL
> path to different market data.

## The 5 locked per-window criteria (closed-trade basis)

| # | Criterion | Threshold |
|---|-----------|-----------|
| 1 | Net ROI | >= +20% of window-start equity |
| 2 | Max drawdown | <= 4.75% (peak reset each window, unified risk-budget gate) |
| 3 | Win rate | >= 40% of resolved trades (wins / (wins + losses)) |
| 4 | Closed trades | >= 5 per window |
| 5 | R-multiples | every win >= +5R, every loss >= -1R (5R-runner floor is structural) |

Scratches (closes in `(-0.02R, +5R)`, e.g. break-even locks) count as trades
but not as wins or losses.

## Strategy logic families (cfg[0])

| Family | Entry rule |
|--------|-----------|
| Breakout (0) | close crosses above the prior N-bar high (long) / below the prior N-bar low (short) |
| EMA pullback (1) | EMA20 vs EMA-N regime, pullback below fast EMA then close reclaims both |
| Momentum (2) | k-bar return exceeds m x ATR%(14) |

Every entry additionally runs through the locked risk pipeline: EMA200 regime
filter (if cfg[3]), ATR% volatility band (if cfg[4]), EMA200 proximity guard
(if cfg[8]), EMA20 slope filter (if cfg[10]), cooldown after full losses
(cfg[9]), re-entry continuation window (cfg[13]), and the unified drawdown
gate `dd_now + open_risk + new_risk <= 4.75%`.

## The 14 locked parameters (CONFIG in each script)

| Index | Name | Meaning |
|-------|------|---------|
| 0 | family | 0 breakout / 1 EMA pullback / 2 momentum |
| 1 | n_len | signal lookback in bars |
| 2 | sl_mult | initial stop distance = sl_mult x ATR(14) |
| 3 | use_regime | 1 = EMA200 trend filter on |
| 4 | use_volfilter | 1 = ATR% volatility band filter on |
| 5 | mom_k | momentum lookback bars (family 2) |
| 6 | mom_m | momentum threshold x ATR% (family 2) |
| 7 | giveback | 5R-runner trailing giveback (R below running MFE) |
| 8 | qf | EMA200 proximity guard (x ATR), 0 = off |
| 9 | cd | cooldown bars after a full loss |
| 10 | sf | 1 = EMA20 slope filter on |
| 11 | mb | max holding bars (exit at close) |
| 12 | be | break-even lock trigger (R of MFE) |
| 13 | re | re-entry continuation: 0 off / 1 = 30 bars / 2 = 60 bars |

Risk model (locked): start equity $5,000, risk per trade = $112 per $5,000
equity scaled by a state machine (full loss -> x0.5, 5R runner -> restore and
ramp toward LAMBDA = 1.25, scratch -> half-step recovery), max 2 concurrent
positions, position size = risk / stop distance.

## Certified results — all 30 strategies

| Strategy | Family | N | Trades | Min window ROI | Max window DD | Total R | Pass |
|----------|--------|---|--------|----------------|---------------|---------|------|
| S00 | Momentum | 24 | 705 | +22.70% | 4.48% | +2174R | 20/20 |
| S01 | Momentum | 96 | 1372 | +21.33% | 4.16% | +2140R | 20/20 |
| S02 | Breakout | 96 | 658 | +24.78% | 4.73% | +2131R | 20/20 |
| S03 | Breakout | 24 | 1704 | +22.38% | 4.43% | +1981R | 20/20 |
| S04 | Breakout | 48 | 561 | +24.33% | 4.63% | +1667R | 20/20 |
| S05 | Breakout | 24 | 772 | +25.86% | 4.71% | +2516R | 20/20 |
| S06 | Momentum | 24 | 1190 | +24.42% | 4.16% | +1812R | 20/20 |
| S07 | Momentum | 24 | 531 | +28.52% | 4.33% | +2257R | 20/20 |
| S08 | Momentum | 24 | 620 | +21.39% | 4.68% | +1964R | 20/20 |
| S09 | Breakout | 48 | 1273 | +44.34% | 4.43% | +2207R | 20/20 |
| S10 | Momentum | 24 | 594 | +54.41% | 4.70% | +2387R | 20/20 |
| S11 | Breakout | 96 | 453 | +23.49% | 4.48% | +1404R | 20/20 |
| S12 | EMA pullback | 24 | 552 | +22.11% | 4.48% | +2118R | 20/20 |
| S13 | EMA pullback | 24 | 412 | +30.91% | 4.73% | +1438R | 20/20 |
| S14 | Momentum | 12 | 942 | +41.86% | 4.48% | +2510R | 20/20 |
| S15 | Momentum | 24 | 558 | +33.21% | 4.48% | +2009R | 20/20 |
| S16 | Breakout | 24 | 1382 | +80.64% | 4.16% | +2408R | 20/20 |
| S17 | Breakout | 96 | 452 | +23.99% | 4.74% | +1685R | 20/20 |
| S18 | Breakout | 96 | 711 | +26.60% | 4.16% | +2601R | 20/20 |
| S19 | Breakout | 48 | 1617 | +22.67% | 4.43% | +1938R | 20/20 |
| S20 | Breakout | 48 | 739 | +38.79% | 4.43% | +2064R | 20/20 |
| S21 | Breakout | 48 | 938 | +22.40% | 4.43% | +2470R | 20/20 |
| S22 | Breakout | 36 | 622 | +21.45% | 4.71% | +2166R | 20/20 |
| S23 | Breakout | 24 | 594 | +67.07% | 4.69% | +2789R | 20/20 |
| S24 | Momentum | 24 | 1321 | +34.85% | 4.43% | +1535R | 20/20 |
| S25 | Breakout | 36 | 730 | +28.25% | 4.71% | +2247R | 20/20 |
| S26 | Breakout | 24 | 1979 | +25.10% | 4.16% | +2214R | 20/20 |
| S27 | Momentum | 24 | 752 | +56.30% | 4.43% | +1701R | 20/20 |
| S28 | Breakout | 48 | 1021 | +34.96% | 4.43% | +1752R | 20/20 |
| S29 | Momentum | 12 | 820 | +26.32% | 3.89% | +1168R | 20/20 |

## Package layout

```
strategies_20x20/
├── README.md                  <- this file
├── requirements.txt           <- numpy, numba
├── strategy_engine.py         <- certified engine (kernel verbatim; do not modify)
├── data_loader.py             <- backtesting-files folder loader
├── certified_results.json     <- certification numbers (used by the verifier)
├── run_strategy_S00.py ... run_strategy_S29.py   <- one script per strategy
├── data_00/ ... data_29/      <- certified dataset per strategy (CSV)
├── run_all.py                 <- all 30 in one process, master table
├── verify_reproduction.py     <- re-runs all 30 and asserts exact reproduction
└── results/                   <- written by the scripts (JSON/CSV/ledger)
```

First run compiles the numba kernel (a few seconds); subsequent strategies in
the same process reuse it.
