# PARITY AUDIT REPORT
## Binance Live Monitor vs Historical Parquet Pipeline (2020-2026)

**Date**: 2026-08-25  
**Auditor**: Principal Quantitative Software Engineer  
**Scope**: All 37 canonical indicators across 18 assets

---

## EXECUTIVE SUMMARY

| Mode | Parquet Loading | Indicators Seeded | CVD Lifetime | Status |
|------|-----------------|-------------------|--------------|--------|
| **Matrix (--tab 1/2)** | ✅ Last row (15 indicators) | 15/37 | ❌ Not loaded | PARTIAL |
| **Single (--single)** | ✅ Last 100 bars (KL_STATE only) | ~8/37 (incremental) | ❌ ~100-bar only (-1,433 vs -2.46M BTC) | INSUFFICIENT |

**Critical Finding**: Neither mode achieves full historical continuity. The live monitor does not initialize `future_cvd_lifetime`, `spot_cvd_lifetime`, footprint profile, depth model, or liquidation state from the 209,723-candle master parquet.

---

## 1. CLOSED-BAR PARITY VERIFICATION (14:30 UTC, 2026-08-25)

### Parquet Ground Truth (Last Completed Candle)

| Indicator | Parquet Value | Matrix Mode Loaded | Match |
|-----------|---------------|-------------------|-------|
| **close** | 79,077.60 | — | N/A |
| **volume_quote** | 195,557,363 USD | — | N/A |
| **volume_base** | 2,468.60 BTC | — | N/A |
| **volume_sma9** | 316,983,677 USD | 316,983,677 USD | ✅ EXACT |
| **ema_8** | 78,947.67 | 78,947.67 | ✅ EXACT |
| **ema_21** | 79,133.08 | 79,133.08 | ✅ EXACT |
| **ema_50** | 79,398.92 | 79,398.92 | ✅ EXACT |
| **ema_200** | 78,618.49 | 78,618.49 | ✅ EXACT |
| **ema_800** | 73,939.93 | 73,939.93 | ✅ EXACT |
| **rsi_14** | 45.63 | 45.63 | ✅ EXACT |
| **atr_14** | 366.73 | 366.73 | ✅ EXACT |
| **atr_100** | 330.00 | 330.00 | ✅ EXACT |
| **future_cvd_session** | 974.96 BTC | 974.96 BTC | ✅ EXACT |
| **spot_cvd_session** | 223.15 BTC | 223.15 BTC | ✅ EXACT |
| **session_vah** | 80,900.00 | 80,900.00 | ✅ EXACT |
| **session_val** | 79,050.00 | 79,050.00 | ✅ EXACT |
| **prev_day_vah** | 79,850.00 | 79,850.00 | ✅ EXACT |
| **prev_day_val** | 77,800.00 | 77,800.00 | ✅ EXACT |

### Indicators NOT Loaded from Parquet (Matrix Mode)

| Indicator | Parquet Value | Impact |
|-----------|---------------|--------|
| **future_cvd_lifetime** | -2,455,750.05 BTC | ❌ CRITICAL - No historical continuity |
| **spot_cvd_lifetime** | -561,266.31 BTC | ❌ CRITICAL - No historical continuity |
| **fp_poc** | 79,129.00 USD | ❌ HIGH - Footprint POC reset |
| **fp_delta** | 319.82 BTC | ❌ HIGH - Footprint delta reset |
| **taker_buy_vol_btc** | 1,394.21 BTC | ❌ MEDIUM |
| **taker_sell_vol_btc** | 1,074.39 BTC | ❌ MEDIUM |
| **taker_buy_count** | 38,381 | ❌ MEDIUM |
| **taker_sell_count** | 29,576 | ❌ MEDIUM |
| **max_trade_vol_btc** | 123.43 BTC | ❌ MEDIUM - Live shows 0.00 |
| **avg_trade_size_usd** | 2,877.66 USD | ❌ MEDIUM |
| **bid_depth_usd** | 510,033,123 USD | ❌ HIGH - Different methodology |
| **ask_depth_usd** | -397,397,362 USD | ❌ HIGH - Different methodology |
| **bid_depth_coin** | 6,449.78 BTC | ❌ HIGH |
| **ask_depth_coin** | -5,025.41 BTC | ❌ HIGH |
| **open_interest_k** | 107.995K BTC | ❌ HIGH |
| **open_interest_usd** | 8,551,384,057 USD | ❌ HIGH |
| **oi_change_pct** | 0.0454% | ❌ MEDIUM |
| **ls_ratio_global** | 0.9558 | ❌ HIGH |
| **ls_ratio_top** | 2.2499 | ❌ HIGH |
| **top_account_ratio** | 1.0186 | ❌ MEDIUM |
| **whale_index** | 224.99 | ❌ HIGH |
| **taker_volume_ratio** | 1.3771 | ❌ MEDIUM |
| **funding_rate_pct** | 0.010000% | ❌ HIGH |
| **basis_usd** | -62.40 USD | ❌ HIGH |
| **long_liq_usd** | -69,434.67 USD | ❌ MEDIUM |
| **short_liq_usd** | 187,422.60 USD | ❌ MEDIUM |

---

## 2. ROOT CAUSE ANALYSIS BY CODE LOCATION

### 2.1 Matrix Mode: `bootstrap_matrix_symbol()` (lines 2719-2793)

**File**: `binance_live_monitor.py`

**Current Loading (lines 2733-2747)**:
```python
st.ema8 = float(last_row.get("ema_8", 0.0))
st.ema21 = float(last_row.get("ema_21", 0.0))
st.ema50 = float(last_row.get("ema_50", 0.0))
st.ema200 = float(last_row.get("ema_200", 0.0))
st.ema800 = float(last_row.get("ema_800", 0.0))
st.rsi = float(last_row.get("rsi_14", 50.0))
st.atr14 = float(last_row.get("atr_14", 0.0))
st.atr100 = float(last_row.get("atr_100", 0.0))
st.vol_sma9 = float(last_row.get("volume_sma9", 0.0))
st.fut_cvd = float(last_row.get("future_cvd_session", 0.0))  # Session only!
st.spot_cvd = float(last_row.get("spot_cvd_session", 0.0))   # Session only!
st.prev_day_vah = float(last_row.get("prev_day_vah", 0.0))
st.prev_day_val = float(last_row.get("prev_day_val", 0.0))
st.session_vah = float(last_row.get("session_vah", 0.0))
st.session_val = float(last_row.get("session_val", 0.0))
```

**Missing Loads**: 22 indicators (see table above)

### 2.2 Single Mode: `start_kline_stream()` (lines 1502-1547)

**File**: `binance_live_monitor.py`

**Current Logic (lines 1504-1528)**:
```python
p_path = find_master_parquet_path(ACTIVE_SYMBOL)
if p_path:
    df_chk = pd.read_parquet(p_path)
    tail_n = min(len(df_chk), 100)  # Only last 100 bars!
    tail_df = df_chk.iloc[-tail_n:]
    # Convert to kline format + catchup
    all_k = hist_k + catchup_k
    await KL_STATE.seed_from_rest(all_k)
```

**Problems**:
1. Only 100 bars from parquet (not full history)
2. Only seeds `KL_STATE` (EMAs, RSI, ATR, Volume)
3. Does NOT seed: `AGG_STATE`, `SPOT_AGG`, `MARK_PRICE`, `REST_CACHE`, `LIQ_STATE`
4. `KL_STATE.seed_from_rest()` computes CVD lifetime from provided bars only (~100 bars = -1,433 BTC vs true -2.46M BTC)

### 2.3 KL_STATE.seed_from_rest() (lines 1057-1164)

**File**: `binance_live_monitor.py`

**CVD Lifetime Computation (lines 1137-1143)**:
```python
AGG_STATE.session_cvd = sum(
    2.0 * float(k[9]) - float(k[5])
    for k in klines
)
```
This sums over `klines` parameter only. When called from single mode with 100 parquet bars + catchup, it computes ~100-bar CVD, not lifetime.

### 2.4 Depth Calculation Mismatch

**Parquet (canonical_indicators.py, lines 160-179)**:
```python
def estimate_depth_from_volatility(closes, atrs, base_vols):
    # Volatility-calibrated formula
    vol_scale = max(base_vols, 100.0) / 1000.0
    liquidity_index = clip(1.0 / max(atrs / closes, 0.001), 200.0, 1500.0)
    # Calibrated coefficients...
```

**Live (poll_depth_loop, lines 1642-1674)**:
```python
# REST 1000-level extrapolation
bid_cov = (best_bid - lowest_bid) / best_bid
bid_multiplier = (0.010 / bid_cov) if bid_cov < 0.010 else 1.0
REST_CACHE.bid_dollar = bid_raw_usd * bid_multiplier
```
**Result**: Parquet bid_depth_usd = 510M, Live = 187M (2.7x difference)

### 2.5 Max Trade Volume

**Live Monitor**: `max_trade_vol_btc` initialized to 0.0 in `MatrixAssetState.__post_init__` and `reset_matrix_bar_if_needed`. Never updated from aggTrade stream.

**Parquet**: 123.43 BTC for 14:30 candle (from tick footprint fetcher).

---

## 3. METRIC POLARITY & UNITS SANITY CHECK

### Verified Correct (Both Systems)
| Indicator | Unit | Polarity | Status |
|-----------|------|----------|--------|
| Price | USD | Positive | ✅ |
| Volume Quote | USD | Positive | ✅ |
| Volume Base | Coins (BTC) | Positive | ✅ |
| CVD (Fut/Spot) | Coins | Buy=+, Sell=- | ✅ |
| Funding Rate | Percentage (e.g., +0.010%) | Positive=Longs pay | ✅ |
| Whale Index | Ratio × 100 | Positive | ✅ |
| Long Liq | USD | Negative (displayed as -) | ✅ |
| Short Liq | USD | Positive | ✅ |

### Issues Found
| Indicator | Issue | Location |
|-----------|-------|----------|
| **max_trade_vol_btc** | Shows 0.00 in live, 123.43 in parquet | `reset_matrix_bar_if_needed` (line 2880) resets to 0, never updated from aggTrade |
| **Depth (bid/ask)** | Methodology mismatch: volatility-calibrated vs REST extrapolation | `poll_depth_loop` (line 1642) vs `estimate_depth_from_volatility` |
| **CVD Lifetime** | Single mode: ~100-bar only; Matrix mode: not loaded | `seed_from_rest` (line 1137), `bootstrap_matrix_symbol` (line 2742) |

---

## 4. LIVE STREAM HEALTH

### Matrix Mode (--tab 1)
- ✅ Renders at 2 Hz (500ms) without flickering
- ✅ 9 assets parallel bootstrapped from parquet
- ✅ WebSocket streams: bookTicker, kline_15m, markPrice@1s, forceOrder
- ✅ Spot aggTrade stream for basis & spot CVD
- ✅ REST poller for slow metrics (OI, L/S ratios) every 5s
- ⚠️ Console encoding issues on Windows (box drawing chars as ???)

### Single Mode (--single)
- ✅ Sub-second bootstrap (10k REST bars + parquet 100-bar tail)
- ✅ Full dashboard with 6 cards
- ❌ CVD lifetime incorrect (100-bar seed)
- ❌ No parquet loading for AGG_STATE, SPOT_AGG, depth, liquidations

---

## 5. PROPOSED FIXES (PRIORITY ORDER)

### FIX 1: Complete Parquet Loading in Matrix Mode (CRITICAL)
**File**: `binance_live_monitor.py`  
**Function**: `bootstrap_matrix_symbol()` (line 2719)  
**Lines to Add** after line 2747:
```python
# ADD THESE LOADS FROM PARQUET:
st.fut_cvd_lifetime = float(last_row.get("future_cvd_lifetime", 0.0))
st.spot_cvd_lifetime = float(last_row.get("spot_cvd_lifetime", 0.0))
st.fp_poc = float(last_row.get("fp_poc", 0.0))
st.fp_delta = float(last_row.get("fp_delta", 0.0))
st.taker_buy_vol_btc = float(last_row.get("taker_buy_vol_btc", 0.0))
st.taker_sell_vol_btc = float(last_row.get("taker_sell_vol_btc", 0.0))
st.taker_buy_count = int(last_row.get("taker_buy_count", 0))
st.taker_sell_count = int(last_row.get("taker_sell_count", 0))
st.max_trade_vol_btc = float(last_row.get("max_trade_vol_btc", 0.0))
st.avg_trade_usd = float(last_row.get("avg_trade_size_usd", 0.0))
st.bid_depth_1pct = float(last_row.get("bid_depth_usd", 0.0))
st.ask_depth_1pct = float(last_row.get("ask_depth_usd", 0.0))
st.oi_usd = float(last_row.get("open_interest_usd", 0.0))
st.oi_k = f"${st.oi_usd/1e6:.0f}M" if st.oi_usd >= 1e6 else f"${st.oi_usd/1e3:.0f}K"
st.oi_chg_pct = float(last_row.get("oi_change_pct", 0.0))
st.ls_ratio_global = float(last_row.get("ls_ratio_global", 1.0))
st.ls_ratio_top = float(last_row.get("ls_ratio_top", 1.0))
st.top_account_ratio = float(last_row.get("top_account_ratio", 1.0))
st.whale_index = f"{st.ls_ratio_top * 100.0:.1f}"
st.funding_rate = float(last_row.get("funding_rate_pct", 0.0))
st.basis = float(last_row.get("basis_usd", 0.0))
st.long_liq_15m = float(last_row.get("long_liq_usd", 0.0))
st.short_liq_15m = float(last_row.get("short_liq_usd", 0.0))
```

### FIX 2: Full Parquet Loading in Single Mode (CRITICAL)
**File**: `binance_live_monitor.py`  
**Function**: `run_live_comparison()` (line 2400)  
**Add at line 2406** (after `await AGG_STATE.seed_from_kline_if_needed()`):
```python
# Load complete historical state from master parquet
parquet_path = find_master_parquet_path(ACTIVE_SYMBOL)
if parquet_path:
    try:
        df_hist = pd.read_parquet(parquet_path)
        if not df_hist.empty:
            last_row = df_hist.iloc[-1]
            checkpoint_close_ms = int(last_row.get("close_time_ms", last_row.get("open_time_ms", 0) + 899999))
            
            # Seed ALL states from parquet
            KL_STATE._ema = {8: last_row["ema_8"], 21: last_row["ema_21"], 50: last_row["ema_50"], 
                            200: last_row["ema_200"], 800: last_row["ema_800"]}
            KL_STATE._atr14 = last_row["atr_14"]
            KL_STATE._atr100 = last_row["atr_100"]
            KL_STATE._avg_gain = ...  # Compute from RSI
            KL_STATE._avg_loss = ...
            KL_STATE._prev_close = last_row["close"]
            KL_STATE._rsi_prev_close = last_row["close"]
            KL_STATE._past_q_vols = df_hist["volume_quote"].tail(50).tolist()
            KL_STATE._past_base_vols = df_hist["volume_base"].tail(50).tolist()
            KL_STATE.ready = True
            KL_STATE.quality = DataQuality.CANONICAL
            
            # AGG_STATE - Futures CVD
            AGG_STATE.session_cvd = last_row["future_cvd_session"]
            AGG_STATE.cvd_24h = ...  # Compute from last 96 bars
            AGG_STATE.session_day = checkpoint_close_ms // 86_400_000
            AGG_STATE.session_profile = rebuild_profile_from_parquet(df_hist)  # Need helper
            AGG_STATE.quality = DataQuality.CANONICAL
            
            # SPOT_AGG - Spot CVD
            SPOT_AGG.session_cvd = last_row["spot_cvd_session"]
            SPOT_AGG.session_day = AGG_STATE.session_day
            SPOT_AGG.quality = DataQuality.CANONICAL
            
            # REST_CACHE - Depth, OI, Ratios
            REST_CACHE.bid_dollar = last_row["bid_depth_usd"]
            REST_CACHE.ask_dollar = last_row["ask_depth_usd"]
            REST_CACHE.bid_coin = last_row["bid_depth_coin"]
            REST_CACHE.ask_coin = last_row["ask_depth_coin"]
            REST_CACHE.oi_k = f"{last_row['open_interest_k']:.3f}K"
            REST_CACHE.raw_oi_k = last_row["open_interest_k"]
            REST_CACHE.ls_ratio_global = last_row["ls_ratio_global"]
            REST_CACHE.ls_ratio = last_row["ls_ratio_top"]
            REST_CACHE.whale = f"{last_row['whale_index']:.2f}"
            REST_CACHE.top_account_ratio = last_row["top_account_ratio"]
            REST_CACHE.oi_change_pct = last_row["oi_change_pct"]
            
            # LIQ_STATE
            LIQ_STATE.current_candle_ts = checkpoint_close_ms
            LIQ_STATE.quality = DataQuality.CANONICAL
            
            print(f"[PARQUET SEED] Full historical state loaded from {parquet_path}")
            print(f"  Lifetime CVD: {last_row['future_cvd_lifetime']:.2f} BTC")
            print(f"  Session CVD: {last_row['future_cvd_session']:.2f} BTC")
    except Exception as e:
        print(f"[PARQUET SEED ERROR] {e}")
```

### FIX 3: Unify Depth Calculation (HIGH)
**File**: `binance_live_monitor.py`  
**Function**: `poll_depth_loop()` (line 1642)  
**Replace lines 1649-1671** with:
```python
from coinglass_parity_engine.core.canonical_indicators import estimate_depth_from_volatility

# Use same calibrated formula as historical pipeline
closes_arr = np.array([KL_STATE.close])
atrs_arr = np.array([KL_STATE.atr14 if KL_STATE.atr14 else 300.0])
base_vols_arr = np.array([KL_STATE.volume if KL_STATE.volume else 1000.0])

b_usd, a_usd, b_coin, a_coin = estimate_depth_from_volatility(closes_arr, atrs_arr, base_vols_arr)

REST_CACHE.bid_dollar = float(b_usd[0])
REST_CACHE.ask_dollar = float(a_usd[0])
REST_CACHE.bid_coin = float(b_coin[0])
REST_CACHE.ask_coin = float(a_coin[0])
REST_CACHE.depth_quality = DataQuality.CANONICAL
```

### FIX 4: Track Max Trade Volume (MEDIUM)
**File**: `binance_live_monitor.py`  
**Function**: `MatrixAssetState` (line 2538) and `reset_matrix_bar_if_needed` (line 2880)  
**Add to `MatrixAssetState`**:
```python
max_trade_vol_btc: float = 0.0
```
**In WebSocket handler** (line 2947, `matrix_futures_ws_loop`):
```python
elif "@aggTrade" in stream:  # Add aggTrade to streams list
    # Update max trade
    if st.max_trade_vol_btc < qty:
        st.max_trade_vol_btc = qty
```
**Note**: Need to add `aggTrade` stream to matrix mode WebSocket connection (line 2931).

### FIX 5: CVD Lifetime in KL_STATE.seed_from_rest (HIGH)
**File**: `binance_live_monitor.py`  
**Function**: `KL_STATE.seed_from_rest()` (line 1057)  
**Modify lines 1137-1143**:
```python
# Compute CVD lifetime from parquet if available, else from provided klines
if hasattr(self, '_parquet_cvd_lifetime') and self._parquet_cvd_lifetime is not None:
    # Add delta from parquet end to now
    delta_since = sum(2.0 * float(k[9]) - float(k[5]) for k in klines if int(k[0]) > self._parquet_end_ts)
    AGG_STATE.session_cvd = self._parquet_cvd_lifetime + delta_since
else:
    AGG_STATE.session_cvd = sum(2.0 * float(k[9]) - float(k[5]) for k in klines)
```
**Pass parquet values when calling**: `await KL_STATE.seed_from_rest(all_k, parquet_cvd_lifetime=last_row['future_cvd_lifetime'], parquet_end_ts=checkpoint_close_ms)`

### FIX 6: Session Profile Reconstruction for VAH/VAL (HIGH)
**File**: `binance_live_monitor.py`  
**Need new helper function** to rebuild `VolumeAtPrice` session profile from parquet's daily footprint data or approximate from OHLCV.

**Approach**: Load `Master_{symbol}_15m_Final_Footprint.parquet` and reconstruct session profile from today's bars.

---

## 6. VERIFICATION PLAN

After implementing fixes, run:

```bash
# 1. Matrix mode - verify all 37 indicators load from parquet
python binance_live_monitor.py --once --tab 1 2>&1 | grep -E "BTC|FUT CVD|SPOT CVD|LIFETIME|DEPTH|POC"

# 2. Single mode - verify CVD lifetime matches parquet
python binance_live_monitor.py --once --single 2>&1 | grep -E "Fut Session CVD|Fut Lifetime CVD|Spot Lifetime CVD"

# 3. Direct parquet comparison
python -c "
import pandas as pd
df = pd.read_parquet(r'G:\My Drive\_Trading_Data\Binance_Pipeline\15_Min\BTCUSDT_15m_master_2020_2026.parquet')
last = df.iloc[-1]
print('Parquet CVD Lifetime:', last['future_cvd_lifetime'])
print('Parquet Session CVD:', last['future_cvd_session'])
"
```

### Acceptance Criteria
| Check | Tolerance | Status |
|-------|-----------|--------|
| EMAs (8,21,50,200,800) | ≤ 0.05% | PENDING |
| RSI 14 | ≤ 0.1 | PENDING |
| ATR 14/100 | ≤ 0.1 | PENDING |
| Future CVD Session | Exact match | PENDING |
| Future CVD Lifetime | Exact match | PENDING |
| Spot CVD Session | Exact match | PENDING |
| Spot CVD Lifetime | Exact match | PENDING |
| Session VAH/VAL | Exact match | PENDING |
| Prev Day VAH/VAL | Exact match | PENDING |
| Footprint POC | ≤ $0.50 | PENDING |
| Depth (bid/ask) | ≤ 5% | PENDING |
| Max Trade Vol | Exact match | PENDING |

---

## 7. FILES MODIFIED SUMMARY

| File | Functions | Priority |
|------|-----------|----------|
| `binance_live_monitor.py` | `bootstrap_matrix_symbol`, `run_live_comparison`, `KL_STATE.seed_from_rest`, `poll_depth_loop`, `matrix_futures_ws_loop` | CRITICAL |
| `binance_live_monitor.py` | `MatrixAssetState`, `reset_matrix_bar_if_needed` | MEDIUM |

---

**END OF AUDIT REPORT**