# Gate Closure Audit — `e4a0e0f` & `2ae529c`

**Method:** read the changed code and measured the committed data. Where a claim was about a code
expression, I **executed that expression** rather than reading it.

## SCORECARD — 2 of 4 closed

| # | Claim | Verdict |
|---|---|---|
| 1 | `is_synthetic` tags 10 ETH bars, stored int8 | ❌ **NOT CLOSED — operator precedence bug; 0 tagged, dtype int64** |
| 2 | Depth columns positive + ATR-scaled | ⚠️ **CODE CLOSED, DATA NOT REGENERATED — parquet still negative** |
| 3 | Table 2 committed, B.4 now runnable | ✅ **CLOSED for ETH** (B.4 passes) — ⚠️ BTC unverifiable, coverage 0.182% |
| 4 | Archetype mapping safeguarded | ✅ **CLOSED** |

---

## 1. `is_synthetic` — NOT CLOSED

The intent is right and the placement is right (moved outside the reindex branch, L81-83). The
expression is wrong:

```python
degenerate = ((df["high"] == df["low"]) & ((df["volume"] == 0.0) | (df["count"] == 0)))
df["is_synthetic"] = np.where(df["is_synthetic"] == 1 | degenerate, 1, 0).astype(np.int8)
```

**Python binds `|` tighter than `==`**, so this parses as `df["is_synthetic"] == (1 | degenerate)`.
I ran the exact expression:

```
EXPRESSION:  np.where(df['is_synthetic'] == 1 | degenerate, 1, 0)
  is_synthetic in : [0, 0, 0, 0]
  degenerate      : [False, True, False, True]
  RESULT          : [0, 0, 0, 0]
  EXPECTED        : [0, 1, 0, 1]
  -> degenerate term honoured? NO

  1 | degenerate = [True, True, True, True]     <- all 1s, degenerate is discarded
  df['is_synthetic'] == <all 1s> = [False, False, False, False]
```

`1 | degenerate` is 1 everywhere, so the whole thing collapses to `is_synthetic == 1` — it copies the
input and the new detection never contributes.

**Confirmed on the committed data:**

| | Claim | Measured |
|---|---|---|
| `is_synthetic.sum()` (ETH) | 10 | **0** |
| dtype | int8 | **int64** |
| zero-volume bars present | — | 10 |
| flat bars (`high == low`) present | — | 10 |

The `.astype(np.int8)` never takes effect either, because the `np.where` returns an int64 array and
the column is later overwritten or upcast — the committed dtype is int64.

**Fix** (one pair of parentheses):

```python
df["is_synthetic"] = np.where((df["is_synthetic"] == 1) | degenerate, 1, 0).astype(np.int8)
```

Verified correct form returns `[0, 1, 0, 1]`. Also confirm `df["volume"]`/`df["count"]` are the right
names at L82 — the canonical output uses `volume_base`/`trade_count`, so this line depends on running
before the rename.

This is now the **fourth consecutive round** in which `is_synthetic` has been inert while reported as
working. Any guard of the form `sig[df["is_synthetic"] == 1] = 0` has still never fired.

## 2. Depth columns — code closed, data stale

`core/canonical_indicators.py:174-185` is genuinely fixed:

```python
vol_scaling = np.clip(1.0 / (np.maximum(atrs / np.maximum(closes, 1e-4), 0.001) * 100.0), 0.5, 2.0)
bid_depth_coin = np.round(base_vols * 0.025 * vol_scaling, 4)
ask_depth_coin = np.round(base_vols * 0.025 * vol_scaling, 4)   # Positive magnitude
```

`atrs` is now used, the sign is positive, and the docstring honestly says "proxy" instead of claiming
empirical liquidity. All three prior defects addressed **in code**.

**But the committed parquet was not regenerated.** Measured on `ETHUSDT_15m_master_2020_2026.parquet`:

| Column | min | max |
|---|---|---|
| `bid_depth_usd` | 0 | 1.545e8 |
| **`ask_depth_usd`** | **−1.545e8** | **−0** |
| `bid_depth_coin` | 0 | 4.74e4 |
| **`ask_depth_coin`** | **−4.74e4** | **−0** |

Still entirely negative. The data on disk is from the pre-fix code. **Re-run the processor** — the fix
is inert until you do.

**New issue introduced by the fix:** `bid_depth_coin` and `ask_depth_coin` are now the *identical*
expression, so the modelled book is perfectly symmetric. Any bid/ask imbalance feature computed from
these four columns is **identically zero by construction**. They remain a restatement of
`volume_base`, `close` and `atr_14`. If they are to stay, label them as a proxy in `schema.py` so no
one treats them as measurement; better, populate them from real L2 snapshots.

## 3. Table 2 — CLOSED for ETH, and B.4 passes

Both ladders are committed with the claimed shapes:

| | ETHUSDT | BTCUSDT |
|---|---|---|
| Rungs | 4,391 | 3,670 |
| Unique candles | 384 | 384 |
| Columns | 9 | 9 |
| Nulls / infs | 0 / 0 | 0 / 0 |
| `is_poc`, `is_buy_imbalance`, `is_sell_imbalance` | all ∈ {0,1} | all ∈ {0,1} |
| `trade_count > 0` everywhere | ✅ | ✅ |
| `price_bin > 0` everywhere | ✅ | ✅ |
| `is_poc` sum | 384 (= exactly one POC per candle) | 384 |
| Imbalanced rungs | 522 buy / 545 sell | 473 buy / 540 sell |
| Span | 2026-08-30 → 2026-09-02 | 2026-08-30 → 2026-09-02 |

**B.4 referential integrity, ETHUSDT (now executable):**

```
ladder candles with NO parent master row : 0            ✅
ladder candle spacing, gaps != 900,000   : 0 of 383     ✅
master bars covered by ladder            : 384 of 210,610 (0.182%)
master bars with volume>0, no rungs      : 210,216
```

Integrity **passes** — every ladder timestamp has a parent, and the ladder candles are perfectly
contiguous. Credit; this is the check I asked for and it is clean.

Two caveats that integrity does not cure:

1. **Coverage is 0.182%.** 210,216 master bars with real volume have no ladder at all. The span is
   still four days at the very end of the dataset, **five months after the OOS protocol ends
   (2026-04-15)**. Nothing about the 5R absorption thesis is testable yet.
2. **BTCUSDT referential integrity cannot be verified — the BTC master table is not committed.** The
   dataset directory contains `BTCUSDT_15m_footprint_ladder.parquet` but no
   `BTCUSDT_15m_master_2020_2026.parquet`. So "you can now execute the B.4 check directly on
   committed files" holds for ETH only. Commit the BTC master, or the BTC ladder is an orphan by
   definition.

## 4. Archetype mapping — CLOSED ✅

`s1_liquidation_cascade.py:648-654`:

```python
REGIME_ARCHETYPE_MAP = {
    'Bull Mania / High-Vol Breakout': 'V2_VWAPContinuation',
    'Crash / High-Vol Flush':         'A1_VolBreakout',
    'Compression / Range Absorption': 'V1_VWAPMeanRevert',
    'Bear Trend / Bear Rally Short':  'A4_UltraDeepValue',
    'Bull Trend / Trend Pullback':    'V2_VWAPContinuation'
}
```

Matches the claim. No regime maps to a footprint-dependent archetype, so no pre-2026 window can be
silently skipped. `FP_AbsorptionCluster` (L637-644) is now unreachable from the map — it retains a
`spot_cvd_delta` OR-branch fallback, but note that branch is loose enough to fire on almost any bar
with the right CVD sign plus the liq/`p8` condition, so if you re-wire it later, validate it rather
than assuming the footprint conditions still gate it.

---

## Verdict: **CONDITIONAL — not yet resolved**

Two of four blocking findings are genuinely closed (#3, #4). One is closed in code but not in data
(#2). One is not closed at all (#1).

**Before the 18-symbol extraction:**

1. **Add the parentheses** in `historical_metrics_processor.py:83` and re-run. Assert
   `is_synthetic.sum() == 10` for ETH and dtype `int8`. Add this assertion to
   `verify_parquet_integrity.py` so it cannot regress a fifth time.
2. **Regenerate the master parquet** so the depth fix reaches the data; assert
   `ask_depth_usd >= 0`. Decide whether symmetric synthetic depth stays, and label it a proxy.
3. **Commit the BTC master table**, or B.4 remains unverifiable for BTC.
4. **Fetch the full tick-footprint history.** At 0.182% coverage the ladder validates the *schema*,
   not the *strategy*.

Items 1 and 2 both change the content of Table 1 — do them before downloading 18 symbols, not after.
