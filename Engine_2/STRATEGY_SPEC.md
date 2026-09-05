# 🏛️ INSTITUTIONAL QUANTITATIVE STRATEGY SPECIFICATION & ARCHITECTURAL CONTRACT (ENGINE 2)
# VERSION: 2.0 (DYNAMIC STRATEGY POOL & CAUSAL IN-SAMPLE REGIME ALLOCATION)
# DATASET: 18 Institutional Binance USDT-M Perpetuals (3,464,074 15m Bars) in `Engine_2/binance_backtesting_data/`
# RIGOR: Strict FABLE 5 Zero-Lookahead Protocols, Numba JIT Accelerated Execution, & VIP0 Friction Realism

---

## 1. ARCHITECTURAL OVERVIEW & PIVOT RATIONALE

Systematic crypto trading models operating across macro market cycles face extreme non-stationarity. A static strategy optimized for bull market impulse runs (e.g. 2021 Post-Halving) experiences structural degradation in low-volatility liquidity voids (2022 Post-Contagion Dead Drift) or high-frequency liquidation cascades (Luna/FTX).

Engine 2 adopts a **Dynamic Strategy Pool ($\mathcal{S}$)** coupled with a **Causal In-Sample Regime-Adaptive Selector**:
- **Strategy Pool ($\mathcal{S}$)**: An orthogonal library of 100+ quantitative alpha strategies grounded in 10 market physics families.
- **Causal In-Sample Allocation Engine**: Prior to each Out-Of-Sample (OOS) quarterly window $k$, the selector evaluates all strategies across in-sample lookback data ($t < t_{\text{start}, k} - 72\text{h}$) under full VIP0 transaction costs.
- **Dynamic Parallel Deployment**: The top $M$ non-correlated strategies ($2 \le M \le 5$) exhibiting positive expectancy and low drawdown are activated in parallel for Window $k$.
- **Shared Portfolio Risk Governor**: Concurrent positions across all active sleeves share a unified $5,000 risk budget with a $4.5\%$ hard equity circuit breaker.

---

## 2. THE 18-ASSET MASTER PARQUET UNIVERSE & SCHEMA

### 2.1 Asset Universe:
`BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `BNBUSDT`, `XRPUSDT`, `DOGEUSDT`, `ADAUSDT`, `AVAXUSDT`, `LINKUSDT`, `SUIUSDT`, `NEARUSDT`, `APTUSDT`, `PEPEUSDT`, `WIFUSDT`, `TIAUSDT`, `ARBUSDT`, `OPUSDT`, `INJUSDT` (Extended: `BCHUSDT`, `DOTUSDT`, `LTCUSDT`, `TRXUSDT`).

### 2.2 Schema Features (62 Verified Master Columns):
- **OHLCV Price Action**: `open`, `high`, `low`, `close`, `volume_base`, `volume_quote`, `volume_sma9`, `trade_count`.
- **Order Flow & CVD**: `future_cvd_15m`, `future_cvd_session`, `spot_cvd_15m`, `spot_cvd_session`, `taker_buy_vol_btc`, `taker_sell_vol_btc`, `taker_volume_ratio`.
- **Derivatives Metrics**: `funding_rate_pct`, `basis_usd`, `open_interest_usd`, `oi_change_pct`, `long_liq_usd`, `short_liq_usd`, `ls_ratio_global`, `top_account_ratio`, `whale_index`.
- **Footprint & Order Book Depth**: `fp_delta`, `fp_poc`, `fp_poc_vol_ratio`, `fp_stacked_buy_imb`, `fp_stacked_sell_imb`, `session_vah`, `session_val`, `bid_depth_usd`, `ask_depth_usd`.
- **Technical Baselines**: `rsi_14`, `atr_14`, `atr_100`, `ema_8`, `ema_21`, `ema_50`, `ema_200`, `ema_800`.

---

## 3. CAUSAL IN-SAMPLE SELECTOR MATHEMATICS

### 3.1 Lookback Boundary & Purge Isolation
For Out-Of-Sample Window $k$ with start timestamp $t_{\text{start}, k}$:
$$\mathcal{T}_{\text{IS}, k} = \left[ t_{\text{start}, k} - T_{\text{lookback}}, \quad t_{\text{start}, k} - 72\text{h} \right]$$
where $T_{\text{lookback}} = 90\text{ days}$. The $72\text{h}$ trade resolution purge buffer ensures zero lookahead leakage.

### 3.2 Strategy Fitness Function $\mathcal{M}(S_i)$
$$\mathcal{M}(S_i) = \text{Expectancy}_{\$}(S_i) \times \min\left(\frac{N_{\text{trades}}}{6}, 1.5\right) \times \left(1.0 - \frac{\text{MaxDD}_{\%}}{4.5\%}\right) \times \mathbf{1}_{\{\text{WR} \ge 35\%, \; \text{MaxDD} < 4.5\%, \; N \ge 4\}}$$
Strategies with negative expectancy, insufficient trades ($N < 4$), or drawdown exceeding $4.5\%$ receive $\mathcal{M}(S_i) \le 0$ and are excluded.

---

## 4. THE 10 ALPHA STRATEGY FAMILIES

1. **Family 1: Forced Liquidation Cascades** (S01–S10) — Kou jump-diffusion exhaustion, spot absorption of liquidation order flows.
2. **Family 2: CVD & Order Flow Divergences** (S11–S20) — Spot-Futures cumulative volume delta decoupling, passive limit absorption.
3. **Family 3: Footprint Microstructure** (S21–S30) — Stacked buy/sell imbalances, POC migration, unfinished auction sweeps.
4. **Family 4: Derivatives Dislocation & Funding Carry** (S31–S40) — 8-hour funding pre-settlement squeezes, basis contango/backwardation snapbacks.
5. **Family 5: Auction Market Theory & Value Area** (S41–S50) — Value Area High/Low rejection, 80% rule traversal, naked POC magnetics.
6. **Family 6: Volatility Expansion & Anchored VWAP** (S51–S60) — 2-sigma AVWAP reversion, ATR squeeze breakouts, CUSUM structural breaks.
7. **Family 7: Momentum & Market Structure** (S61–S70) — Triple EMA ribbons, market structure breaks (MSB), order block retests.
8. **Family 8: Mean Reversion & Exhaustion** (S71–S80) — RSI stochastic dislocations, whale volume absorption, asymmetric wick reclaims.
9. **Family 9: Cross-Asset Lead-Lag & Dispersion** (S81–S90) — BTC momentum propagation, altcoin beta rotation, synchronized liquidation rebounds.
10. **Family 10: Macro Regimes & Session Overlaps** (S91–S100) — London-NY overlap sweeps, Asia range raids, regime-adaptive meta-controller.

---

## 5. MICROSTRUCTURE EXIT RATCHET & FRICTIONS

### 5.1 4-Tier Dynamic Ratchet:
- **Tier 0 (Breakeven Lock)**: When $P_{\text{high}} \ge \text{Entry} + 0.80\text{R} \implies \text{Stop} \leftarrow \text{Entry} + 0.15\text{R}$.
- **Tier 1 (Profit Lock)**: When $P_{\text{high}} \ge \text{Entry} + 1.50\text{R} \implies \text{Stop} \leftarrow \text{Entry} + 0.80\text{R}$.
- **Target Exit**: Limit take-profit at $+2.0\text{R} \dots +2.5\text{R}$.
- **Time Decay Stop**: If trade does not achieve $\ge +0.20\text{R}$ within 24 bars ($6\text{h}$), exit at market.

### 5.2 Realistic Frictions:
- **Taker Fee**: $8\text{ bps}$ ($0.08\%$) per fill.
- **Entry Slippage**: $10\text{ bps}$ ($0.10\%$).
- **Stop Slippage**: $15\text{ bps}$ ($0.15\%$).
- **Causal Arming**: Trailing ratchets take effect on bar $j+1$ after trigger condition is met at bar $j$.

---

## 6. PORTFOLIO RISK GOVERNOR

- `INITIAL_CAPITAL = 5000.0`
- `BASE_RISK = 25.0` ($0.50\%$ base risk per trade)
- `HOUSE_MONEY_RISK = 50.0` ($1.00\%$ max risk when cumulative net profit $\ge \$50.0$)
- `DRAWDOWN_DEFENSE_RISK = 15.0` ($0.30\%$ defensive risk when drawdown $\ge 2.5\%$)
- `DRAWDOWN_RISK_LIMIT = 0.045` ($4.5\%$ / $\$225.0$ hard emergency circuit breaker)
- `MAX_CONCURRENT = 2` (Maximum 2 open positions across all strategies and symbols simultaneously).
