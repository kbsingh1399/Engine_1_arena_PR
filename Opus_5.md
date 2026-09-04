**## Audit Provenance and a Preliminary Note on Artifact Integrity**



**I retrieved and read the following at `main` (tree SHA `a4292b06`): `s1\_liquidation\_cascade.py`, `run\_live\_terminal.py`, `verification/patch\_existing\_parquets.py`, the Arena.ai review, and the remediation blueprint. Two disclosures before I render judgment, because an auditor who overstates coverage is worse than useless.**



**First, `binance\_live\_monitor.py` is 162,201 bytes. GitHub's raw endpoint served me the first \~36KB and then failed with gzip decoding errors on subsequent range requests; jsDelivr mirrored the same truncation. I therefore audited the module's architecture, its full 37-indicator specification block, its dataclass/quality contracts, its global initialization path, and its symbol-resolution logic in full, but I did not read the WebSocket supervisor bodies or the CDP bridge internals. Where my Domain 1 findings depend on unread code I say so explicitly. Nothing below is inferred from the docstring alone where the docstring is the only evidence.**



**Second, and more consequentially: `s1\_liquidation\_cascade.py` at HEAD is under 20KB, and I read approximately the first 79% of it — through the top of `run\_all\_20\_windows`. The tail (roughly the last 140 lines, containing the per-window execution body and the region Arena cited as lines 796–860) was not retrievable. Arena reviewed a 902-line version at `41c027b`; the file is now materially shorter, which is consistent with the fallback loop having been excised. \*\*I cannot confirm that, and you should not let anyone tell you it is confirmed until someone reads those lines.\*\* That is audit item zero.**



**What I \*can\* confirm from the bytes I did read is damaging enough.**



**---**



**## Domain 0: The Remediation Plan Was Not Applied**



**Your brief states that you "purged all lookup tables, removed the OOS fallback loops, and enforced a clean, causal 30-day In-Sample Macro Regime selection," and that the honest result was 1/20. The code at HEAD does not reflect that work.**



**`WINDOW\_CONFIGURATIONS` is still present, still keyed on window index, still carrying all 100 constants. I read all twenty entries — window 3 still has its anomalous `120.0` house trigger, windows 7, 16 and 19 still carry the `0.44` thresholds. It is not dead code: `needed\_archetypes = set(cfg\[0] for cfg in WINDOW\_CONFIGURATIONS.values())` is what drives archetype extraction. Module 1 of your own blueprint mandates deleting this dictionary. It is intact.**



**The MAE lookahead clamp is intact. `mae\_dollar = units \* maes\[i]` is still assigned to `open\_mae\_dollars\[p]` \*\*at entry time\*\*, where `maes\[i]` is the full-life adverse excursion returned by `simulate\_single\_trade\_path`. The drawdown governor then computes `drawdown\_budget = peak\_capital \* dd\_limit - closed\_drawdown - open\_mae`. The position sizer is consuming the future. Module 3 mandated replacing this with bar-by-bar unrealized PnL. It was not done.**



**The Target Lock is intact at `if (capital - initial\_capital) >= 1010.0 and trades\_executed >= 5 and active\_count == 0: break`.**



**And the slippage engine does not exist. `FEE\_RATE = 0.0008` is applied as `fee = (entry\_val + exit\_val) \* (fee\_rate / 2.0)` and nothing else. Entry fills are `next\_opens\[idx]` unmodified — no 10bps adjustment. Stop fills are `exit\_price = cur\_stop` exactly — no 15bps adjustment. \*\*The "Execution Frictions: 10 bps taker entry slippage, 15 bps stop slippage" line in your mandate is not implemented in the code you asked me to audit.\*\* Module 4 was not done.**



**So the empirical ground truth you have presented me — the 1/20 honest pass rate, the +52.51% Window 02 — was produced by a script that is either not in this repository or not at this commit. I will treat those numbers as \*reported\* rather than \*verified\*, and I will note that they were produced under a still-frictionless, still-lookahead-clamped simulator. \*\*The honest number is therefore not 1/20. It is worse than 1/20, and Window 02's +52.51% is inflated by an unknown amount.\*\***



**---**



**## Domain 1: Microstructure Alpha and the Execution Bridge**



**### 1.1 The intra-bar path simulator books the favorable ordering**



**This is my most material independent finding, and it contradicts Arena's credit that "adverse-first intra-bar evaluation... \[is] respected." It is not. Inside `simulate\_single\_trade\_path`, for a long:**



**```python**

**adverse = max(0.0, entry\_price - lows\[j])**

**if adverse > mae: mae = adverse**

**if highs\[j] > best\_price:**

&#x20;   **best\_price = highs\[j]**

&#x20;   **gain = best\_price - entry\_price**

&#x20;   **if gain >= 5.0 \* stop\_dist:  cur\_stop = best\_price - 0.8\*stop\_dist**

&#x20;   **elif gain >= 3.8 \* stop\_dist: cur\_stop = entry\_price + 2.0\*stop\_dist**

&#x20;   **elif gain >= 2.5 \* stop\_dist: cur\_stop = entry\_price + 0.5\*stop\_dist**

**if lows\[j] <= cur\_stop:**

&#x20;   **exit\_price = cur\_stop**

**```**



**MAE is recorded adverse-first, which is correct for sizing. But the trailing ratchet then consumes `highs\[j]` and \*raises the stop\*, and the stop check on the very next line evaluates `lows\[j]` — \*\*the same bar's low against a stop level that was just lifted using the same bar's high.\*\* A single 15-minute bar that runs +5R and then fully reverses is booked as an exit at `best\_price − 0.8×stop\_dist`, i.e. roughly +4.2R. In reality you have no idea whether the high preceded the low, and in a liquidation flush the reversal is precisely what happens inside one bar.**



**The damage compounds three ways. It inflates `r\_multiple`. It inflates the label, because `lb = 1.0 if r\_mult > 0.0` — so LightGBM is trained on optimistically-signed outcomes, meaning the model's `probs\[i]` are miscalibrated in the same direction as the bias, and `probs\[i]` feeds the risk multiplier `prob\_mult = 1.0 + max(0.0, (probs\[i]-0.50)\*1.5)`. And it inflates win rate directly against your ≥40% gate. This bug is largest on high-range bars, which is to say it is largest exactly in the cascade regime that constitutes the entire claimed edge. A conservative fix is to require that no favorable ratchet computed from bar \*j\*'s extreme may be used to exit within bar \*j\*; ratchets take effect from \*j+1\*. I would expect that single change to move win rate and mean R materially, and I would want the delta measured and published before anything else is discussed.**



**### 1.2 `atr` is not ATR, and the stop floor is 3.25× too tight**



**`df\['atr'] = (df\['high'] - df\['low']).rolling(14, min\_periods=1).mean()`. That is a 14-bar mean of the intrabar range. True Range is `max(H−L, |H−C\_prev|, |L−C\_prev|)`; Wilder's ATR is an RMA of that. The implementation \*\*discards both gap terms\*\* — the only terms that carry overnight and cascade gap information. It is a downward-biased volatility estimate whose bias is maximal in gapping markets.**



**This estimate then sets position size: `stop\_dist = max(atrs\[i], entry\_prices\[i]\*0.002)` and `units = cur\_risk / stop\_dist`. Understating volatility mechanically oversizes every position. Arena flagged that the code's 20bps floor contradicts a spec calling for `max(2.0×ATR14, Entry×0.0065)`; I confirm the code says `0.002`, not `0.0065`, and that `atrs\[i]` is passed raw with no `2.0` multiplier anywhere in `gen\_symbol\_trades`. So the live stop is somewhere between one-third and one-sixth of the specified distance, and units are correspondingly 3–6× the specified size. That is the real explanation for how a $5,000 account reaches +20% monthly, and it is also the mechanism by which the 4.5% clamp will be blown through in production.**



**### 1.3 Stop fills assume no gap through the level**



**`exit\_price = cur\_stop` when `lows\[j] <= cur\_stop`. If a bar's low is 60bps through the stop, the backtest still fills \*at\* the stop. For a strategy whose thesis is "enter during a violent liquidation flush," this assumption is inverted relative to reality: the stop-out path is precisely the path with gap risk. The correct convention is `exit\_price = min(cur\_stop, opens\[j])` for longs, further degraded by a depth-conditional slippage term. Combined with 1.1 and 1.2, the simulator is optimistic on the entry price, the stop distance, the stop fill, and the intra-bar ordering. These errors are not independent and they do not offset.**



**### 1.4 The core S1 trigger cannot be reproduced live — this is the feature drift you asked about**



**You asked whether there is mathematical desynchronization between live features and the training feature vectors. Yes, and it is disqualifying in three specific places.**



**\*\*Liquidation z-scores.\*\* `long\_liq\_zscore` and `short\_liq\_zscore` are the primary triggers for `A8\_LiqExtreme` and `N2\_LiqCascadeFlush`, and they gate `A2\_DeepSqueeze`. Historically they are 96-bar rolling z-scores of `long\_liq\_usd` / `short\_liq\_usd` from your parquet, which is built from an aggregated liquidation source. Live, indicators 9 and 10 are sourced from Binance's `forceOrder` stream. That stream is \*\*throttled to roughly one order per second per symbol\*\* — it publishes a sampled subset of liquidation events, not the full tape. The undercount is not constant; it is worst during cascades, when hundreds of liquidations arrive per second. So the live `long\_liq\_zscore` is computed from a series whose relationship to the training series degrades monotonically with cascade intensity. The feature is most wrong exactly when the strategy depends on it most. No amount of code hygiene fixes this: it requires either an aggregated liquidation feed (CoinGlass API, not the CDP scrape) or retraining the historical features on throttled-equivalent Binance `forceOrder` history so that train and live are the same estimator.**



**\*\*CVD.\*\* The model consumes `zs(spot\_cvd\_15m, 4/10/96)` — rolling z-scores of a \*level\* series that your pipeline maintains as a lifetime roll-forward cumulative. Live, the module exposes `session\_cvd` and `cvd\_24h`, plus a manually-injected `CVD\_OFFSET` persisted to `.okf/cvd\_anchor.json` and applied to make the display agree with CoinGlass. Three distinct objects. A rolling z-score of a non-stationary cumulative sum is dominated by the local drift of the level, so changing the anchor changes the rolling mean, which changes the z-score, which changes the signal. A session-anchored CVD that resets and a lifetime cumulative CVD do not produce the same `zc4`/`zc20` distribution, and `zc\_rel\_btc = zc20 − zb20` compounds the error across two assets. Additionally: any hand-set `CVD\_OFFSET` is a human-in-the-loop parameter sitting upstream of a live trading signal. That is an operational control failure independent of the math.**



**\*\*Open interest and funding.\*\* Live indicator 8 is "Total aggregated Open Interest (USDT-M + USDC-M + COIN-M)"; live indicator 7 is an "Open Interest weighted funding rate." The historical features `open\_interest\_usd`, `oi\_change\_pct`, `zoi`, `oid`, `fr`, `zfr` are single-venue USDT-M quantities. Aggregating three margin types changes the level, the variance, and therefore every z-score and every percentage-change derivative built on it. `oicc = sign(oid) \* sign(spot\_cvd\_delta)` is a sign-agreement feature — it will flip on a definitional change alone.**



**Beyond these three, note the asymmetry of scope: the live module computes footprint POC, session and prior-day VAH/VAL, ±1% bid/ask depth in both dollars and coins, whale index, basis, max trade size and alt taker flow — \*\*none of which appear in S1's 36-column feature list.\*\* Conversely S1 requires `ls\_ratio\_global`, `rsi\_14`, `volume\_quote` and the liquidation series under exactly their historical definitions. You have built a rich telemetry display and a separate model, and no one has written the contract that maps one onto the other. There is no shared feature-computation library. That is the architectural defect: \*\*the same indicator is implemented twice, in two languages of intent, and nothing tests that they agree.\*\***



**### 1.5 The live monitor is single-asset; the strategy is eighteen-asset**



**`ACTIVE\_SYMBOL = "BTCUSDT"` is a module-level global. `BASE\_ASSET`, `QUOTE\_ASSET`, `LOWER\_SYM`, `LOWER\_BASE` and `get\_merge\_level()` all derive from it at import time. The docstring says "tracks 37 canonical microstructure and technical indicators for BTCUSDT." Meanwhile `run\_live\_terminal.py`'s docstring advertises a "real-time 18-asset multi-stream matrix terminal," and S1 trades 18 symbols with `MAX\_CONCURRENT = 2` cross-sectional selection. Unless the unread 126KB contains a multi-symbol supervisor that overrides these globals — possible, and I flag it as an open item — \*\*the ingestion layer cannot feed the strategy's universe.\*\* Cross-sectional archetype ranking across 18 assets is unimplementable on a single-symbol feed, and `zc\_rel\_btc` requires two simultaneous symbol states at minimum.**



**### 1.6 The entrypoint's CLI contract is fiction**



**`run\_live\_terminal.py` parses `--single`, `--symbol`, `--target-dir` and `--once`, then calls `live\_main()` \*\*with no arguments\*\*. None of the parsed values are passed. `binance\_live\_monitor.py` independently re-scrapes `sys.argv` at import for `--symbol`/`-s`, so that one flag works by coincidence; `--once` and `--single` are silently discarded, which means your headless CI path (`--once`) does not do what its help string says and any test built on it is not testing what you think. Separately, `--skip-sync` is declared `action="store\_true", default=True` — permanently True — and is never read anywhere. `parse\_known\_args` swallows typos without error. A flag that silently does nothing in a trading entrypoint is how a production incident starts.**



**Related: `binance\_live\_monitor.py` performs `sys.stdout.reconfigure()`, `os.system("")`, terminal sizing, argv parsing and anchor-file I/O \*\*at module import\*\*. You cannot import this module into a strategy process without it mutating global interpreter and console state. It is not embeddable and not unit-testable in its current form.**



**### 1.7 Silent asset-dropping in the data loader**



**`load\_and\_preprocess\_data` wraps each file in `try/except Exception` and on failure logs `"Skipping {f} due to read error"` and continues. Now consider `df\['rsi'] = df.get('rsi\_14', 50.0).fillna(50.0)`. If `rsi\_14` is absent, `DataFrame.get` returns the \*scalar\* `50.0`, and `float.fillna` raises `AttributeError`. Same pattern at `spot\_cvd = df.get('spot\_cvd\_15m', 0.0)` followed by `spot\_cvd.diff()`. So a schema regression on any single column does not fail loudly — \*\*it silently removes that asset from the universe\*\*, and the backtest proceeds to report a full result computed on a smaller, unannounced universe. Combined with `if not files: return {}` returning an empty dict rather than raising, this loader can produce a "successful" run on a partial or empty universe. Every one of these paths must become a hard `raise`, with the realized symbol list and row counts written into the results manifest and asserted against expectation.**



**### 1.8 The parquet "verifier" is a mutator**



**`patch\_existing\_parquets.py` is named as a verifier in your brief and treated as an integrity control. It is not a verifier; it rewrites all eighteen files \*\*in place, with no backup, no checksum, no schema assertion and no idempotency guard\*\*. Substantively:**



**`df\[c].replace(\[np.inf, -np.inf], 0.0)` across every numeric column converts undefined values into a \*meaningful\* value. In `oi\_change\_pct`, an infinity is generated by a zero prior-OI denominator — i.e. OI going from nothing to something, which is a genuine regime event. Recoding that as `0.0` asserts "no change." That fabricated zero then propagates into `oi\_flush = oi\_change\_pct.clip(upper=0)` and into `zoi`. NaN, not zero, is the correct encoding, with an explicit availability mask.**



**`is\_synthetic = np.where(volume\_base == 0.0, 1, 0)` conflates exchange downtime with genuinely zero-volume bars, and `metrics\_available = where(open\_interest\_usd > 0, 1, 0)` marks bars with no OI data. Both are then \*\*never used\*\*: neither column appears in S1's feature list, in any signal mask, or in any filter. The engine trades synthetic bars and bars with no OI metrics as if they were clean observations. Building a data-quality flag and not gating on it is worse than not building it, because it creates the documentary appearance of a control that does not exist.**



**### 1.9 Live execution risk when S1 submits taker orders into a flush**



**Taking your question directly, and assuming the fills problem in 1.2–1.3 is fixed: the dominant risks are adverse selection, queue-position collapse, and rate-limit denial at precisely the wrong moment.**



**The adverse selection is structural and Arena stated it correctly, so I will sharpen it rather than repeat it. Your fills partition into two populations. Orders that fill instantly at a tight touch are the ones where the cascade had already exhausted and liquidity had returned — those are the \*good\* signals and you get a \*good\* price, but they are also the trades where the remaining move is smallest because the dislocation is gone. Orders that fill only after walking the book are the ones where the cascade is still running — you receive a 40–100bps worse price \*and\* a position facing continued forced selling. A flat 8bps roundtrip prices both identically. The correct model is a depth-weighted walk of the live L2 with a conditional gap term, and it must be estimated from your own ±1% depth telemetry, which the monitor already collects and the backtest ignores.**



**Queue and latency: `MAX\_CONCURRENT = 2` with cross-sectional signals means the engine may fire two symbols within one bar. If the signal loop is synchronous with rendering — plausible given the Rich-based single-process design — order submission contends with terminal repaint and CDP polling. During a cascade the aggTrade stream rate rises by one to two orders of magnitude, so any unbounded `asyncio` queue between ingestion and signal evaluation grows, and your signal is evaluated against a state snapshot that is seconds stale. In a flush, seconds are entire percentage points. You need bounded queues with explicit drop-oldest semantics on the tick path, a monotonic staleness check that vetoes order submission when `receive\_timestamp\_ms` lags wall clock beyond a hard threshold, and the `DataQuality` enum you already defined enforced as a \*\*submission precondition\*\* rather than a display colour.**



**Rate limits: Binance USDT-M enforces both weight-based and order-count limits, and during extreme volatility the venue has historically degraded — elevated latency, rejected orders, and in past events suspended some functionality. Your strategy's arrival process is maximally bursty and correlated across all 18 symbols, since cascades are market-wide. So the moment you most want to submit 2 orders plus 2 stop orders plus cancels is the moment you are most likely to receive `-1003` or a timeout. Two consequences: reduce-only stop orders must be resting at the venue from the instant of fill (never held client-side, or a disconnect leaves you naked at 10x), and you need an idempotent order-state reconciler using `newClientOrderId` so a timed-out submission is never blindly retried into a double position.**



**Finally, at 10x with `MAX\_NOTIONAL = 50000` on a $5,000 account, liquidation price sits close enough to the stop that a gap through the stop during a cascade can hit venue liquidation before your stop fills. That is an unmodeled terminal risk: the backtest's worst case is 1R, the venue's worst case is the account.**



**---**



**## Domain 2: Mathematical Feasibility of the 20/20 Mandate**



**\*\*No. Not by a single directional strategy, not by any strategy, and the impossibility is provable from the constraint set rather than from empirical humility.\*\***



**Start with the arithmetic of the mandate itself. +20% net monthly on $5,000 is +$1,000. At `BASE\_RISK = 75.0` (1.5%), that is \*\*+13.3R net per month from 5–7 trades.\*\* With six trades at your 40% minimum win rate — 2.4 winners, 3.6 losers at −1R — the average winner must return `(13.3 + 3.6) / 2.4 ≈ 7.0R`. A 7R average winner, net of frictions, is not a thing that exists in 15-minute crypto mean-reversion at any consistency.**



**The engine's actual escape hatch is the risk ladder, and this is where the mandate self-destructs. `HOUSE\_MONEY\_RISK = 220.0` on $5,000 is \*\*4.4% of capital risked on one trade against a 4.5% drawdown ceiling.\*\* At $220 risk you need only `13.3 × 75/220 ≈ 4.5R` net for the month — achievable-looking, which is exactly why the ladder exists. But a \*single\* full stop-out at house size consumes 98% of the entire monthly drawdown budget. The return constraint and the drawdown constraint are therefore not jointly satisfiable by any sizing policy: the size required to earn 20% is the size at which one loss ends the month. The `drawdown\_budget / 1.2` clamp papers over this by refusing the position, which is why, as Arena observed, the elaborate ladder is largely inert — and the windows where it is \*not\* inert are the windows that pass. The mandate is not a performance target. It is a specification of a strategy that must never take a full loss.**



**Now the probability of surviving 20 windows honestly. If per-window pass probability is `p` and windows were independent, `P(20/20) = p^20`. To have even a coin-flip chance you need `p = 0.5^(1/20) = 0.966`. \*\*Every single month must pass with 96.6% probability.\*\* Binomial noise alone forbids this. At six trades and a true 40% win rate, `P(≥2 wins) = 0.767`. At a true 70% win rate — far above anything credible after fixing §1.1 — `P(≥4 of 6) = 0.744`. Both are far below 0.966, and these bound only the win-rate gate, before you require +13.3R \*and\* DD<4.5% \*and\* ≥5 trades simultaneously. At your reported `p = 0.05`, `p^20 ≈ 10^-26`.**



**Two corrections make the picture worse, not better. First, the windows are \*\*not independent\*\*: training is 18 months, the grid advances 3 months, so consecutive in-sample sets overlap by 15 months — 83%. Your effective independent sample is perhaps five to seven regime observations, not twenty. This cuts both ways honestly: it means `p^20` overstates the difficulty of a \*fitted\* 20/20, and it means twenty windows carry far less evidentiary weight than twenty independent trials would. Second, and more damning for the framing: `OOS\_MONTHS` samples \*\*20 months out of the 61 in the stated span, on a 3-month cadence, with two slots (2025-09-15 and 2025-12-15) skipped.\*\* Two-thirds of the timeline is never tested. This is not walk-forward validation; it is a sampled grid with 41 unobserved months, and Arena's observation that both skipped slots follow passing windows is a serious integrity flag that remains unresolved at HEAD.**



**Convert the mandate to portfolio terms for the investment committee. 20% monthly compounds to `1.2^12 − 1 = +791%` annually against a 5% maximum drawdown — a Calmar ratio near 158 and an implied Sharpe in the range of 10 to 15 sustained over five years. For calibration: Medallion's widely-cited long-run figures are roughly 66% gross and 39% net annualized, at an estimated Sharpe near 2, achieved by an organization with thousands of weakly-correlated signals, proprietary execution and decades of infrastructure. The best crypto quant books run Sharpe 2–4. \*\*You are proposing a Sharpe an order of magnitude beyond the best documented result in the history of the industry, from one directional archetype on 15-minute bars.\*\* When a backtest reports that, the correct prior is not "we found something extraordinary." It is "we have found a bug," and in this codebase §1.1, §1.2, §1.3 and the intact MAE clamp are four sufficient candidates.**



**On Window 02's +52.51% at 80% win rate: that is 5 trades. The 95% Clopper–Pearson interval on 4-of-5 runs roughly \[28%, 99%]. It is one draw from a fat-tailed distribution in June–July 2021, the highest-realized-volatility regime in the sample. I do not doubt that liquidation-exhaustion carries genuine edge in violent flushes — the microstructure logic is sound and the phenomenon is real. \*\*I doubt entirely that 5 trades in the single most favorable month in five years measures its magnitude\*\*, particularly when the simulator producing that number contains a favorable intra-bar ordering bias that is maximal in high-range bars.**



**One further point the committee must hear: the repository contains `s6\_volatility\_compression\_breakout.py`, `s7\_delta\_climax\_mean\_reversion.py`, `s8\_hybrid\_whale\_cvd.py`, `s9\_vwap\_profile\_conviction.py` and their siblings. If each was independently searched against the same 20/20 gate on the same twenty windows, the family-wise error rate is enormous and the "winning" strategy is a selection artifact of the family, not of any individual file. \*\*Whatever multiple-comparison accounting you apply to S1 must be applied across all nine.\*\***



**### The Capacity Objection, Which Alone Ends the $10M Discussion**



**The engine is parameterized for a $5,000 account: `$75` base risk, `$220` house risk, `$50,000` notional ceiling. At $10M you need roughly 2,000× the notional, but `MAX\_NOTIONAL = 50000.0` is a hard clamp inside the sizer — \*\*the engine as written cannot deploy $10M at all.\*\* Removing the clamp does not solve it. The strategy fades liquidation cascades in 18 alt perpetuals, several of them (SUI, APT, OP, ARB, NEAR) with order books thin enough that institutional size \*becomes\* the cascade. At 10x on a $10M book you are submitting $100M notional taker flow into books that have just lost their depth. Your market impact would exceed the entire modeled edge, and you would be the exit liquidity for the very liquidations you are trying to fade. Any honest capacity study on this archetype lands in the single-digit millions of notional at most, concentrated in BTC and ETH.**



**---**



**## Domain 3: What Would Actually Be Required**



**### 3.1 The mandate must be reformulated first, because it is internally contradictory**



**You asked whether the engine should sit in cash during low-volatility compression. It should — and the moment you concede that, \*\*the 20/20 mandate is dead by construction\*\*, because a flat month returns 0%, which fails a ≥20% monthly gate. You cannot simultaneously hold "20% every calendar month" and "deploy only in verified cascade regimes." One of them has to go, and it is not the regime gate.**



**Replace the monthly gate with the objective a real allocator underwrites: a rolling 12-month Sharpe or Calmar target, a hard maximum-drawdown covenant, and a \*conditional\* return expectation stated per regime — e.g. "in verified cascade regimes, target 8–15% monthly at 3% DD; in compression regimes, target 0% and preserve capital." Then measure the \*\*unconditional\*\* annualized figure that policy produces. My honest expectation for a well-built version of this archetype: 25–60% annualized, Sharpe 1.5–2.5, 12–20% peak-to-trough drawdown, in the low single-digit millions of capacity. That is a genuinely excellent crypto strategy and it is fundable. The 791%/5%DD specification is not fundable because it is not real.**



**### 3.2 Multi-sleeve ensemble — correct, with a caveat**



**Yes, and your proposed decomposition is well-chosen because the sleeves are structurally rather than incidentally uncorrelated. S1 (liquidation exhaustion) is short-horizon, long-volatility, and earns in dislocation. S2 (trend momentum) is medium-horizon and earns in sustained directional regimes where S1 gets chopped. S3 (basis/funding carry) is the important one for your problem: it is capacity-rich, low-drawdown, and it earns \*precisely in the calm compression months where S1's pass rate collapses to zero\*. Realistically funding carry on liquid perps delivers something like 8–20% annualized with modest volatility and occasional sharp basis-unwind gaps — nowhere near 20% monthly, but it converts a flat month into a positive one and it smooths the equity curve that the drawdown covenant is measured against.**



**The caveat: \*\*correlation must be measured on realized sleeve PnL, not asserted from thesis.\*\* All three sleeves are short crypto tail risk in the deep tail — a cascade that liquidates longs also blows out basis and reverses trend simultaneously. Estimate the correlation matrix in the tail (exceedance correlation, or conditional on the worst decile of BTC returns), not at the mean, and allocate on that. Also do not compute the ensemble by aggregating the \*existing\* nine backtests: each carries the selection bias described above, and averaging biased sleeves produces a biased portfolio with a deceptively smooth curve.**



**### 3.3 Regime gating — correct, and it must be causal and pre-registered**



**Gate on a small number of pre-committed, causally-computable regime variables — realized-vol ratio (you have `vol\_ratio`), aggregate liquidation intensity, funding dispersion, and cross-asset correlation. Two hard rules. The gate thresholds are fitted \*\*in-sample only\*\* and frozen before any OOS evaluation; the current `regime` construction with hardcoded `0.40` and `1.15` cutoffs has no documented provenance, and unprovenanced constants are how `WINDOW\_CONFIGURATIONS` happened. And the gate must be \*hysteretic\* — separate entry and exit thresholds — or you will flicker in and out of deployment on noise and pay the frictions of both states.**



**Also: cash is not free optionality on a levered perp book. Sitting flat means the sleeve's contribution to the annualized figure is zero in those months, and it means your capital sits as exchange collateral bearing counterparty risk. Price that.**



**### 3.4 Order-book microstructure additions**



**Concretely, in the order I would build them:**



**The single highest-value change is \*\*inverting the execution style\*\*. S1's thesis is that a cascade has \*exhausted\* and is being \*absorbed\*. Absorption means resting bids are eating aggressive sells. The correct way to express that is to \*be\* the resting bid — post-only limit orders staged into the flush at estimated absorption levels — not to cross a widened spread with a taker order. This flips the sign of your spread cost from paying to earning, and it converts the adverse-selection asymmetry in §1.9 from a tax into a filter: in a cascade that has genuinely exhausted, your limit fills; in one still running, you get filled and immediately stopped, which is a real cost that must be modeled, but you no longer pay 40–100bps of walk-the-book on every entry. Model both variants explicitly and require the passive variant to be the production path, with taker permitted only as a hedged exit.**



**Then, as hard preconditions on submission: a \*\*touch-width veto\*\* (abort if the spread exceeds, say, its rolling 95th percentile for that symbol — you cannot fade a cascade you cannot price); an \*\*L2 imbalance confirmation\*\* requiring bid depth within the fade direction to be building rather than evaporating over the last several hundred milliseconds, computed from your existing ±1% depth telemetry (a static imbalance snapshot is nearly useless here — the \*derivative\* is the absorption signal); a \*\*depth-sufficiency check\*\* requiring the intended notional to be some small fraction of resting depth inside your maximum tolerable impact band; and a \*\*staleness veto\*\* keyed on the `DataQuality` enum plus a wall-clock lag bound.**



**For execution mechanics at any real size: participation-capped slicing with iceberg/hidden quantity, a hard per-symbol notional cap derived from that symbol's measured depth rather than a global `MAX\_NOTIONAL`, exchange-resident reduce-only stops placed atomically with fill, and a global kill-switch on realized-slippage-versus-model breaching a threshold. That last item is the one people skip and the one that saves the account: \*\*if realized slippage exceeds modeled slippage by more than a set multiple over a rolling window, the system stops trading and pages a human\*\*, because that condition means your cost model has decoupled from the market and every subsequent sizing decision is wrong.**



**Finally, gap risk cannot be managed by stop placement alone at 10x. Size against a gap-adjusted stop — `max(2×true\_ATR, 65bps, k × empirical cascade-gap quantile)` — cap \*\*aggregate\*\* open risk against the drawdown budget rather than sizing each position independently against the full budget, and reduce leverage. 10x on alt perps with venue liquidation close to your stop is not a risk-managed position; it is a bet that the gap does not happen on your trade.**



**---**



**## Domain 4: Investment Committee Recommendation**



**### Verdict: \*\*REJECT.\*\***



**Not conditional. Reject, at this commit, with a defined path to re-review.**



**I want to be precise about why, because the reason is not that the strategy lost money and not that the team lacks ability. The data pipeline is real, the eighteen-asset reconstruction is real, the microstructure thesis is real, the purge discipline and next-bar-open convention were implemented correctly, and the live telemetry module is a genuinely substantial piece of engineering. The team that built this can build institutional infrastructure. I would not say that about most of what crosses this desk.**



**I am rejecting on three grounds, in descending order of severity.**



**\*\*First, the audit trail is not intelligible.\*\* Two external reviews identified four fatal flaws. A detailed remediation blueprint was written committing to fix all four. At HEAD, `WINDOW\_CONFIGURATIONS` is intact, the MAE lookahead clamp is intact, the Target Lock is intact, and the slippage engine does not exist — while the brief presented to me asserts all of this was purged and quotes performance figures produced under the purged version. Either the remediated code is not in this repository, or the reported 1/20 and the +52.51% did not come from this code. \*\*Both possibilities mean the numbers in front of the committee cannot be traced to an executable artifact.\*\* That is a process failure, and process failures are the only category of finding I treat as automatically disqualifying, because every other finding is only as reliable as the process that surfaced it. No allocation can be underwritten against untraceable telemetry.**



**\*\*Second, the simulator remains optimistic in at least four independent, non-offsetting ways\*\* — the intra-bar favorable-ordering bias in the trailing-stop ratchet, the non-gap-aware pseudo-ATR feeding position size, the 20bps stop floor against a 65bps spec, and stop fills booked exactly at the stop level with zero gap slippage — every one of which is largest in the high-volatility cascade regime that constitutes the entire claimed edge. The honest performance of this archetype has not yet been measured. It is not 1/20; 1/20 is an upper bound.**



**\*\*Third, the mandate itself is mathematically incoherent\*\*, per Domain 2, and the system cannot deploy the proposed capital in any case — `MAX\_NOTIONAL = 50000` is a hard clamp, and the underlying archetype's true capacity in these instruments is three orders of magnitude below $10M. A strategy calibrated on $75 of risk per trade is not a candidate for a $10M allocation regardless of its Sharpe. Continuing to pursue 20%-every-month is the root cause of every methodological failure in this repository: the lookup table, the fallback loop, the Target Lock and the per-window Top-K patches are all rational responses to an impossible objective. \*\*Fix the objective and the overfitting pressure disappears.\*\***



**### Mandated Three-Phase Roadmap**



**\*\*Phase 1 — Establish Ground Truth (6–8 weeks). Gate: an honest number exists, whatever it is.\*\***



**Freeze and tag the current commit as the historical record. Delete `WINDOW\_CONFIGURATIONS` and every per-window branch. Fix one archetype, one selection rule (a single K for all windows), one risk ladder, chosen by an in-sample-only procedure whose code is committed and whose output is a written pre-registration. Restore `OOS\_MONTHS` to a complete, unskipped grid — I want all 61 months, not 20, since the parquets support it and there is no reason to leave two-thirds of the timeline unexamined. Remove the Target Lock and report untruncated equity curves. Then fix the simulator: ratchets computed from bar \*j\* may not exit within bar \*j\*; replace pseudo-ATR with Wilder ATR on true range; stop fills at `min(stop, open)` degraded by a depth-conditional slippage term; replace the precomputed `maes\[i]` clamp with running bar-by-bar unrealized PnL; implement the 10/15bps frictions the mandate already claims and treat them as a floor, not an estimate. Convert every silent `except` in the data loader to a hard failure and assert the realized universe. Rewrite the parquet script to verify rather than mutate — NaN plus an availability mask instead of `inf → 0.0`, no in-place writes without checksummed backups — and make the strategy actually gate on `is\_synthetic` and `metrics\_available`.**



**Publish the resulting curve with no gates and no pass/fail language: annualized return, Sharpe, Sortino, maximum drawdown, deflated Sharpe accounting for the number of configurations examined across all nine strategy files, and a per-regime conditional decomposition. \*\*A 1/20 result under honest accounting is a successful Phase 1.\*\* The deliverable is a trustworthy measurement, not a passing grade.**



**\*\*Phase 2 — Rebuild the Architecture Around the Real Objective (3–4 months). Gate: train/live parity is proven, not asserted.\*\***



**Reformulate the mandate per §3.1 and get committee sign-off on the new objective before further engineering, so that no one is again incentivized to search the test set. Extract a \*\*single shared feature-computation library\*\* used identically by the backtest and the live path — this is the most important structural change in the entire roadmap. Then prove parity empirically: run the live ingestor in shadow mode alongside a replay of the historical pipeline over the same interval and require every model input to agree within a tight, pre-declared tolerance, with the test in CI. Resolve the three specific desynchronizations in §1.4 — move liquidations to an aggregated feed or retrain on throttled-equivalent history, eliminate the manual `CVD\_OFFSET` and define one canonical CVD anchoring convention, and reconcile OI and funding aggregation scope. Extend the ingestor to genuine multi-symbol operation, remove all module-level import side effects, and fix the entrypoint so declared flags do what they claim. Build the passive-execution path and the L2 preconditions from §3.4, with a slippage model estimated from your own depth telemetry. Stand up S2 and S3 as independent sleeves under the same honest protocol and estimate the tail-conditional correlation matrix. Run a proper capacity study per symbol.**



**\*\*Phase 3 — Prove It Forward With Real Money, Small (6 months minimum, non-negotiable). Gate: live tracks shadow.\*\***



**$100K–$250K of firm capital at reduced leverage. Six months of continuous forward operation with daily reconciliation of realized versus modeled slippage, fill rates, feature-parity drift and PnL attribution by sleeve. Hard covenants: automatic de-risking at a pre-declared drawdown, the slippage-decoupling kill-switch, and a full stop on any feature-parity breach. No parameter changes during the period; a change resets the clock. The single acceptance criterion is that \*\*live results fall inside the confidence interval the shadow backtest predicted\*\* — not that live results are good. A strategy that predicts +3% and delivers +2.5% has demonstrated a validated model. A strategy that predicts +20% and delivers +30% has demonstrated nothing except that you still cannot forecast your own system.**



**Scale to institutional size only after Phase 3 clears, and only up to the notional the Phase 2 capacity study supports — which on current evidence will be materially less than $10M for this archetype, and will require the multi-sleeve portfolio to justify a larger number.**



**---**



**### Two Closing Notes for the Committee**



**The most valuable artifact in this repository is the Arena review, and the second most valuable is the remediation blueprint. A team that commissions adversarial review, publishes the finding that its headline result was a test-set search, and writes down the fix is a team operating with more integrity than most. \*\*The failure here is not intellectual dishonesty; it is that an impossible mandate was allowed to stand, and the blueprint was never executed.\*\* Those are both correctable, and correcting them is what Phase 1 is for.**



**And the open item I could not close: someone needs to read the final \~140 lines of `s1\_liquidation\_cascade.py` and confirm whether the OOS fallback loop still executes. If it does, every number this engine has ever produced is a test-set search result and Phase 1 begins from zero. I was unable to retrieve those bytes through three separate transports, and I am not willing to guess at their contents. Treat that as the first task, before anything else on this roadmap.**

