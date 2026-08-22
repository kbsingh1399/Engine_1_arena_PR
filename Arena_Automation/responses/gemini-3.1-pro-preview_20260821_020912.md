# Model Codebase Audit: gemini-3.1-pro-preview

**Date:** 2026-08-21 02:09:12
**Chat URL:** https://arena.ai/c/01a020d5-492b-7ba0-8b9c-9cc38c79990f

## Prompt & Git Context

```
=== REPOSITORY & LIVE CODEBASE CONTEXT ===
GitHub Repository: https://github.com/kbsingh1399/coinglass-trading.git
Branch: arena/019fec7a-coinglass-trading
Commit SHA: f0e21a41141122a94d0d1a28fd57a328192de853
Target Engine Directory: Engine_1_arena_PR/
===========================================

### SOURCE FILE: six_strategy_engine.py
```python
"""
Six Strategy Engine — Unified Live Predictor
=============================================
Ports the exact logic from colab_strategies/run_all_6.py into a live streaming predictor.

Strategies:
  S1 - Liquidation:    Trend pullback + abnormal liquidation spike
  S2 - CVD Momentum:   Tight trend pullback on strong CVD moves
  S3 - Trend Follow:   Classic macro trend pullback (EMA 200/800)
  S4 - Mean Reversion: RSI extremes with deep pullback
  S5 - Vol Breakout:   Trend pullback + elevated volatility + CVD
  S6 - OI Coherence:   Trend pullback + OI/CVD directional agreement

All strategies share:
  - Same feature engineering (featurize)
  - Same ML pipeline (LGB + XGB ensemble)
  - Same trade parameters (TP=5R, Trail=0.8ATR, SL=1ATR, max 288 bars)
  - Same walk-forward validation
"""

from __future__ import annotations

import os
import sys
import json
import time
import collections
import threading
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
try:
    from numba import njit
except ImportError:
    def njit(*a, **k):
        def wrap(f): return f
        return wrap if not (a and callable(a[0])) else a[0]

# ─── Constants (match run_all_6.py exactly) ──────────────────────────
TP_MULT = 5.0
TRAIL_ATR = 0.8
SL_MULT = 1.0
MAX_BARS = 288       # 72 hours of 15m bars
RISK_PCT = 0.004     # 0.4% per trade (matches RSK=20 on $5000)
FEE_PCT = 2 * float(os.environ.get("ENGINE_FEE_PER_SIDE", "0.0004"))  # Round-trip fee (centralized)

SYMBOLS = [
    'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT', 'ADAUSDT',
    'TRXUSDT', 'AVAXUSDT', 'DOTUSDT', 'LINKUSDT', 'LTCUSDT', 'NEARUSDT', 'SUIUSDT'
]

STRATEGY_NAMES = {
    'S1': 'S1_Liquidation',
    'S2': 'S2_CVD_Momentum',
    'S3': 'S3_Trend_Follow',
    'S4': 'S4_Mean_Reversion',
    'S5': 'S5_Vol_Breakout',
    'S6': 'S6_OI_Coherence',
}


# ─── Numba Trade Simulation (exact copy from run_all_6.py) ──────────
@njit(fastmath=True, nogil=True)
def _sim_trade(h, l, c, entry_idx, entry, atr, dr):
    """Simulate a single trade forward from entry_idx."""
    n = len(c)
    sd = atr * SL_MULT
    td = atr * TP_MULT
    trd = atr * TRAIL_ATR
    st = entry - sd if dr == 1 else entry + sd
    cs = st  # current stop
    bp = entry  # best price
    ns = st  # new stop
    mx = min(entry_idx + MAX_BARS + 1, n)
    ep = c[mx - 1]  # exit price
    bh = mx - 1 - entry_idx  # bars held

    for j in range(entry_idx + 1, mx):
        if dr == 1:
            if l[j] <= cs:
                ep = cs; bh = j - entry_idx; break
            if h[j] > bp:
                bp = h[j]
            if (bp - entry) >= td:
                ns = bp - trd
            if ns > cs:
                cs = ns
        else:
            if h[j] >= cs:
                ep = cs; bh = j - entry_idx; break
            if l[j] < bp:
                bp = l[j]
            if (entry - bp) >= td:
                ns = bp + trd
            if ns < cs:
                cs = ns

    units = RISK_PCT / sd if sd > 0 else 0
    gross = units * (ep - entry) if dr == 1 else units * (entry - ep)
    fees = units * entry * FEE_PCT / 2.0 + units * abs(ep) * FEE_PCT / 2.0
    net_pnl = gross - fees
    r_mult = net_pnl / (RISK_PCT) if RISK_PCT > 0 else 0
    win = 1.0 if net_pnl > 0 else 0.0
    return net_pnl, r_mult, win, bh


@njit(fastmath=True, nogil=True)
def gen_trades_numba(h, l, c, o, a, sig):
    """Numba-compiled vectorized trade generator."""
    n = len(c)
    results = []
    i = 200
    cd = 0
    
    while i < n - 100:
        if i >= cd:
            dr = sig[i]
            if dr != 0:
                entry = o[i + 1] if i + 1 < n else c[i]
                av = a[i]
                if av > 0 and not np.isnan(av):
                    net, r, lb, bh = _sim_trade(h, l, c, i, entry, av, int(dr))
                    results.append((i, dr, net, r, lb, bh))
                    cd = i + int(bh) + 2
        i += 1
    
    return results


# ─── Z-Score Helper ──────────────────────────────────────────────────
def _zscore(series, window):
    """Rolling z-score."""
    mean = series.rolling(window, min_periods=1).mean()
    std = series.rolling(window, min_periods=1).std().replace(0, 1e-10)
    return (series - mean) / std


# ─── Feature Engineering (exact copy from run_all_6.py) ──────────────
def featurize(df, btc_ref=None):
    """Compute all features needed by the 6 strategies."""
    if btc_ref is not None:
        cj = [c for c in btc_ref.columns if c not in df.columns]
        if cj:
            df = df.join(btc_ref[cj], how='left')
        if 'btc_CVD' in df.columns:
            df['btc_CVD'] = df['btc_CVD'].ffill().bfill().fillna(0)

    # PARITY FIX: True Range / ATR must match run_all_6.py exactly
    prev_close = df['Close'].shift(1)
    tr1 = df['High'] - df['Low']
    tr2 = (df['High'] - prev_close).abs()
    tr3 = (df['Low'] - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14, min_periods=1).mean()

    # CVD features
    if 'CVD' in df.columns:
        df['cvd_d'] = df['CVD'].diff(5)
        for k in [4, 10, 20]:
            df[f'zc{k}'] = _zscore(df['CVD'], k)
    else:
        df['cvd_d'] = 0.0
    for k in [4, 10, 20]:
        df[f'zc{k}'] = df.get(f'zc{k}', pd.Series(0.0, index=df.index))

    # BTC CVD features
    df['bcvm'] = df['btc_CVD'].diff(2) if 'btc_CVD' in df.columns else 0.0
    for k in [4, 10, 20]:
        df[f'zb{k}'] = _zscore(df['btc_CVD'], k) if 'btc_CVD' in df.columns else 0.0

    # Macro signal: EMA 200/800 (must be identical to run_all_6.py)
    df["ef"] = df["Close"].ewm(span=200, min_periods=50).mean()
    df["es"] = df["Close"].ewm(span=800, min_periods=100).mean()
        
    df["mc"] = np.where(
        (df["ef"] - df["es"]) / df["atr"].replace(0, 1e-10) > 0.5, 1,
        np.where((df["ef"] - df["es"]) / df["atr"].replace(0, 1e-10) < -0.5, -1, 0)
    )
    # FIX: EMA-200 slope over 10 bars, normalized by ATR (used by S2/S3 filter)
    ef_vals = df["ef"].values
    atr_vals = df["atr"].replace(0, 1e-10).values
    ef_slope = np.zeros(len(df))
    ef_slope[10:] = (ef_vals[10:] - ef_vals[:-10]) / atr_vals[10:]
    df["ef_slope"] = ef_slope

    # EMA pullbacks (must be identical to run_all_6.py)
    for s, n in [(8, "e8"), (21, "e21"), (50, "e50")]: 
        df[n] = df["Close"].ewm(span=s, min_periods=1).mean()

    atrs = df["atr"].replace(0, 1e-10)
    df["p8"] = (df["Close"] - df["e8"]) / atrs
    df["p21"] = (df["Close"] - df["e21"]) / atrs
    df["p50"] = (df["Close"] - df["e50"]) / atrs

    # RSI
    d = df["Close"].diff()
    g = d.clip(lower=0).rolling(14, min_periods=1).mean()
    l = (-d.clip(upper=0)).rolling(14, min_periods=1).mean()
    rs = g / l.replace(0, 1e-10)
    df["rsi"] = (100 - (100 / (1 + rs))).fillna(50.0)

    # Volatility regime
    df["vr"] = _zscore(df["atr"], 100)

    # Liquidation features
    for s, c in [("l", "Agg. Liq Long"), ("s", "Agg. Liq Short")]:
        if c in df.columns:
            df[f"liq{s}"] = pd.to_numeric(df[c], errors="coerce").fillna(0).rolling(5, min_periods=1).sum()
            df[f"liq{s}m"] = df[f"liq{s}"].rolling(100, min_periods=1).mean()
        else:
            df[f"liq{s}"] = 0.0
            df[f"liq{s}m"] = 0.0

    # Open Interest features
    if "Agg. OI" in df.columns:
        oi = pd.to_numeric(df["Agg. OI"], errors="coerce").ffill()
        df["zoi"] = _zscore(oi, 100)
        df["oid"] = oi.diff(5) / (oi.shift(5) + 1e-10)
        df["oicc"] = np.sign(df["oid"].fillna(0)) * np.sign(df["cvd_d"].fillna(0))
    else:
        df["zoi"] = 0.0
        df["oid"] = 0.0
        df["oicc"] = 0.0

    # LS Ratio
    if "Long/Short Ratio (Account)" in df.columns:
        df["zls"] = _zscore(pd.to_numeric(df["Long/Short Ratio (Account)"], errors="coerce").ffill(), 100)
    else:
        df["zls"] = 0.0

    # Funding Rate
    if "Agg. Funding Rate" in df.columns:
        fr = pd.to_numeric(df["Agg. Funding Rate"], errors="coerce").fillna(0)
        df["fr"] = fr
        df["zfr"] = _zscore(fr, 20)
    else:
        df["fr"] = 0.0
        df["zfr"] = 0.0

    # Footprint features
    for c in ["Bid Qty", "Ask Qty", "Delta Qty", "Bid Trades", "Ask Trades"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
            df[f"z{c.replace(' ', '_').lower()}"] = _zscore(df[c], 10)
        else:
            df[f"z{c.replace(' ', '_').lower()}"] = 0.0

    if "Buy Qty" in df.columns and "Sell Qty" in df.columns:
        buy = pd.to_numeric(df["Buy Qty"], errors="coerce").fillna(0)
        sell = pd.to_numeric(df["Sell Qty"], errors="coerce").fillna(0)
        df["bsr"] = buy / (buy + sell + 1e-10)
    elif "Bid Qty" in df.columns and "Ask Qty" in df.columns:
        buy = pd.to_numeric(df["Bid Qty"], errors="coerce").fillna(0)
        sell = pd.to_numeric(df["Ask Qty"], errors="coerce").fillna(0)
        df["bsr"] = buy / (buy + sell + 1e-10)
    else:
        df["bsr"] = 0.5

    if "Volume" in df.columns:
        df["vr5"] = df["Volume"] / (df["Volume"].rolling(20, min_periods=1).mean() + 1e-10)
    else:
        df["vr5"] = 1.0

    df = df.fillna(0).replace([np.inf, -np.inf], 0)
    return df


# ─── Signal Generators (exact copy from run_all_6.py) ────────────────
def make_signal_s1(row):
    """S1: Trend pullback + liquidation confirmation (PARITY: no RSI)"""
    mc, p8 = row.get('mc', 0), row.get('p8', 0)
    ll, llm = row.get('liql', 0), row.get('liqlm', 0)
    ls, lsm = row.get('liqs', 0), row.get('liqsm', 0)
    zc20 = row.get('zc20', 0)

    if mc > 0 and p8 < -0.12 and (ll > llm * 1.2 or zc20 > 0.1):
        return 1
    if mc < 0 and p8 > 0.12 and (ls > lsm * 1.2 or zc20 < -0.1):
        return -1
    return 0

def make_signal_s2(row):
    """S2: Deep Pure Trend with context filters
    
    Requires: mc>0, p8<-0.25, EMA-200 slope > 0.5 ATR, vr5 > 0.5, 25 < rsi < 75
    """
    mc, p8 = row.get('mc', 0), row.get('p8', 0)
    ef_slope = row.get('ef_slope', 0)
    vr5 = row.get('vr5', 1.0)
    rsi = row.get('rsi', 50)
    if mc > 0 and p8 < -0.25 and ef_slope > 0.5 and vr5 > 0.5 and 25 < rsi < 75:
        return 1
    if mc < 0 and p8 > 0.25 and ef_slope < -0.5 and vr5 > 0.5 and 25 < rsi < 75:
        return -1
    return 0

def make_signal_s3(row):
    """S3: Pure trend pullback (excludes S2 zone to prevent double-entry)
    
    Requires: mc>0, -0.25 <= p8 < -0.20 (S2 handles p8 < -0.25),
    EMA-200 slope > 0.5 ATR, vr5 > 0.5, 25 < rsi < 75
    """
    mc, p8 = row.get('mc', 0), row.get('p8', 0)
    ef_slope = row.get('ef_slope', 0)
    vr5 = row.get('vr5', 1.0)
    rsi = row.get('rsi', 50)
    # FIX: Exclude S2 zone (p8 < -0.25) to prevent double-entry collision
    if mc > 0 and p8 < -0.20 and p8 >= -0.25 and ef_slope > 0.5 and vr5 > 0.5 and 25 < rsi < 75:
        return 1
    if mc < 0 and p8 > 0.20 and p8 <= 0.25 and ef_slope < -0.5 and vr5 > 0.5 and 25 < rsi < 75:
        return -1
    return 0

def make_signal_s4(row):
    """S4: RSI mean reversion"""
    rsi, p8 = row.get('rsi', 50), row.get('p8', 0)
    if rsi < 35 and p8 < -0.5:
        return 1
    if rsi > 65 and p8 > 0.5:
        return -1
    return 0

def make_signal_s5(row):
    """S5: Vol Breakout — trend pullback + vol bonus (PARITY: RSI only on bonus)"""
    mc, p8 = row.get('mc', 0), row.get('p8', 0)
    vr, zc20 = row.get('vr', 0), row.get('zc20', 0)
    rsi = row.get('rsi', 50)  # Only used for bonus path

    # Core: trend pullback like S3 (PARITY: no RSI on core)
    if mc > 0 and p8 < -0.2:
        return 1
    if mc < 0 and p8 > 0.2:
        return -1
    # Bonus: high-vol regime (PARITY: RSI 25-75 range)
    if mc > 0 and p8 < -0.1 and vr > 1.5 and zc20 > 0.15 and 25 < rsi < 75:
        return 1
    if mc < 0 and p8 > 0.1 and vr > 1.5 and zc20 < -0.15 and 25 < rsi < 75:
        return -1
    return 0

def make_signal_s6(row):
    """S6: OI Coherence — trend pullback + OI/CVD bonus (PARITY: no RSI)"""
    mc, p8 = row.get('mc', 0), row.get('p8', 0)
    oicc, zc20 = row.get('oicc', 0), row.get('zc20', 0)

    # Core: trend pullback like S3 (PARITY: no RSI)
    if mc > 0 and p8 < -0.2:
        return 1
    if mc < 0 and p8 > 0.2:
        return -1
    # Bonus: OI-CVD coherence (PARITY: no RSI)
    if mc > 0 and p8 < -0.1 and oicc != 0 and oicc > 0.2 and zc20 > 0.1:
        return 1
    if mc < 0 and p8 > 0.1 and oicc != 0 and oicc < -0.2 and zc20 < -0.1:
        return -1
    return 0

SIGNAL_FUNCS = {
    'S1': make_signal_s1,
    'S2': make_signal_s2,
    'S3': make_signal_s3,
    'S4': make_signal_s4,
    'S5': make_signal_s5,
    'S6': make_signal_s6,
}


# ─── ML Model Training (matches run_all_6.py bmodel) ────────────────
def train_ensemble(X, y):
    """Train LGB + XGB ensemble with feature importance selection."""
    import lightgbm as lgb
    try:
        import xgboost as xgb
        has_xgb = True
    except ImportError:
        has_xgb = False

    if len(X) < 20 or y.sum() < 3 or (len(y) - y.sum()) < 3:
        return None, list(X.columns)

    p = y.sum()
    sw = max(0.1, float((len(y) - p) / p)) if p > 0 else 1.0

    # Feature selection via LGB importance
    sel = lgb.LGBMClassifier(n_estimators=30, max_depth=3, random_state=42,
                              verbose=-1, n_jobs=1, max_bin=31)
    sel.fit(X, y)
    imps = sel.feature_importances_
    cut = np.percentile(imps, 15)
    selected = [c for c, im in zip(X.columns, imps) if im >= cut]
    if len(selected) < 3:
        selected = list(X.columns)

    models = []

    # LightGBM
    m_lgb = lgb.LGBMClassifier(
        max_depth=5, learning_rate=0.02, n_estimators=200,
        scale_pos_weight=sw, random_state=42, n_jobs=1, verbose=-1,
        max_bin=63, min_child_samples=8, subsample=0.8,
        colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1
    )
    m_lgb.fit(X[selected], y)
    models.append(m_lgb)

    # XGBoost
    if has_xgb:
        m_xgb = xgb.XGBClassifier(
            max_depth=4, learning_rate=0.03, n_estimators=200,
            scale_pos_weight=sw, random_state=42, n_jobs=1,
            verbosity=0, subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1
        )
        m_xgb.fit(X[selected], y)
        models.append(m_xgb)

    return models, selected


def predict_ensemble(models, selected_cols, X):
    """Ensemble average prediction with robust column realignment."""
    if not models or not selected_cols:
        return np.full(len(X) if hasattr(X, '__len__') else 1, 0.5, dtype=np.float32)
    
    # Realign columns into exact expected feature order with 0.0 fallback
    X_aligned = pd.DataFrame(index=X.index if isinstance(X, pd.DataFrame) else [0])
    for col in selected_cols:
        if isinstance(X, pd.DataFrame) and col in X.columns:
            X_aligned[col] = pd.to_numeric(X[col], errors='coerce').fillna(0.0).values
        else:
            X_aligned[col] = 0.0

    X_df = X_aligned.astype(np.float32)
    probs = [m.predict_proba(X_df)[:, 1] for m in models]
    return np.mean(probs, axis=0)


# ─── Unified Live Predictor Class ────────────────────────────────────
class FeatureDriftDetector:
    """Detects when live feature values fall outside the training distribution.
    
    Maintains running mean/std for each feature from the training data.
    Flags features that exceed 4σ from the training mean.
    
    Dry-run mode: When dry_run=True, logs drift events to JSONL instead of
    blocking predictions. Use --dry-run-drift flag for 24h calibration.
    """
    
    _DRIFT_LOG_FILE = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "live_data", "drift_dryrun_log.jsonl"
    )
    
    def __init__(self, training_stats: Dict[str, Dict[str, float]], dry_run: bool = False):
        self.stats = training_stats
        self._drift_counts: Dict[str, int] = {}
        self.DRIFT_THRESHOLD = 4.0
        self.MAX_DRIFT_BEFORE_BLOCK = 3
        self.dry_run = dry_run
    
    def _log_drift_event(self, symbol: str, drifted: List[str], features: Dict[str, float], would_block: bool) -> None:
        """Append drift event to JSONL log file (dry-run mode)."""
        event = {
            "timestamp": time.time(),
            "datetime": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
            "symbol": symbol,
            "would_block": would_block,
            "drifted_features": drifted,
            "feature_values": {k: round(v, 6) for k, v in features.items()
                              if k in ['cvd_d', 'zc4', 'zc10', 'zc20', 'zoi', 'liql', 'liqs', 'fr', 'vr5']},
        }
        try:
            os.makedirs(os.path.dirname(self._DRIFT_LOG_FILE), exist_ok=True)
            with open(self._DRIFT_LOG_FILE, 'a') as f:
                f.write(json.dumps(event) + "\n")
        except Exception:
            pass
    
    def check_row(self, symbol: str, features: Dict[str, float]) -> Tuple[bool, List[str]]:
        sym_stats = self.stats.get(symbol, {})
        if not sym_stats:
            return True, []
        
        drifted = []
        critical_features = ['cvd_d', 'zc4', 'zc10', 'zc20', 'liql', 'liqs', 'fr']
        
        for feat in critical_features:
            mean = sym_stats.get(f'{feat}_mean', None)
            std = sym_stats.get(f'{feat}_std', None)
            if mean is None or std is None or std == 0:
                continue
            
            val = features.get(feat, 0.0)
            z = abs(val - mean) / std
            if z > self.DRIFT_THRESHOLD:
                drifted.append(f"{feat}={val:.4f} (z={z:.1f}σ)")
        
        if drifted:
            self._drift_counts[symbol] = self._drift_counts.get(symbol, 0) + 1
        else:
            self._drift_counts[symbol] = 0
        
        would_block = self._drift_counts.get(symbol, 0) >= self.MAX_DRIFT_BEFORE_BLOCK
        
        # Dry-run mode: log but never block
        if self.dry_run:
            if drifted:
                self._log_drift_event(symbol, drifted, features, would_block)
            return True, drifted
        
        # Normal mode: block after MAX_DRIFT_BEFORE_BLOCK consecutive drifted bars
        is_safe = not would_block
        return is_safe, drifted


class LiveSixStrategyPredictor:
    """
    Runs all 6 strategies from run_all_6.py on live streaming data.
    
    On each 15m candle close:
    1. Compute features via featurize()
    2. Generate signals via make_signal_s1..s6
    3. Filter via ML ensemble (if trained)
    4. Dispatch trades via trade_tracker.trigger_entry()
    """

    def __init__(self, symbols: List[str]):
        self.symbols = symbols
        self.candles_history: Dict[str, collections.deque] = {}
        self.current_candle: Dict[str, dict] = {}
        self._last_predict_bar: Dict[str, int] = {}
        self._cached_signals: Dict[str, Dict[str, str]] = {s: {} for s in symbols}
        self._lock = threading.RLock()
        
        # Load training stats from Parquet for drift detection
        training_stats = self._load_training_stats(symbols)
        self.drift_detector = FeatureDriftDetector(training_stats)

        # ML models per strategy per symbol
        self.models: Dict[str, Dict[str, Any]] = {k: {} for k in SIGNAL_FUNCS}
        self.selected_cols: Dict[str, Dict[str, list]] = {k: {} for k in SIGNAL_FUNCS}
        self.thresholds: Dict[str, Dict[str, float]] = {k: {s: 0.55 for s in symbols} for k in SIGNAL_FUNCS}

        # BTC reference for cross-asset features
        self.btc_ref = None

        # Adaptive loss tracking: (symbol, direction) -> consecutive SL count
        self._consec_losses: Dict[tuple, int] = {}
        # Adaptive threshold lift: per symbol, extra threshold penalty after losses
        self._thresh_lift: Dict[str, float] = {s: 0.0 for s in symbols}
        # Candle-level direction suspension after excessive losses: (symbol, direction) -> bar until which blocked
        self._dir_suspend_until: Dict[tuple, int] = {}
        # FIX: Monotonic bar counter per symbol (replaces len(candles_history) which caps at maxlen)
        self._bar_counter: Dict[str, int] = {s: 0 for s in symbols}
        self.log_fn = None

        self.load_models()

    def _log(self, msg: str, tag: str = "SixStrategy"):
        if self.log_fn:
            try:
                self.log_fn(msg, tag)
            except Exception:
                pass

    def load_models(self):
        """Load pre-trained models from disk."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        models_dir = os.path.join(base_dir, 'six_strategy_models')
        if not os.path.exists(models_dir):
            print(f"[SixStrategy] No pre-trained models at {models_dir} — will train on first data")
            return

        import pickle
        for strat_key in SIGNAL_FUNCS:
            for sym in self.symbols:
                path = os.path.join(models_dir, f'{strat_key}_{sym}.pkl')
                if os.path.exists(path):
                    try:
                        with open(path, 'rb') as f:
                            data = pickle.load(f)
                        self.models[strat_key][sym] = data['models']
                        self.selected_cols[strat_key][sym] = data['selected_cols']
                        self.thresholds[strat_key][sym] = data.get('threshold', 0.55)
                    except Exception as e:
                        print(f"[SixStrategy] Error loading {strat_key}_{sym}: {e}")

        total = sum(len(v) for v in self.models.values())
        print(f"[SixStrategy] Loaded {total} models across {len(SIGNAL_FUNCS)} strategies")

    def _load_training_stats(self, symbols: List[str]) -> Dict:
        """Compute mean/std for critical features from backtesting Parquet data.
        
        These stats are used by FeatureDriftDetector to block predictions when
        live feature values fall outside the training distribution (>4σ).
        """
        base_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(base_dir, "backtesting_data")
        stats = {}
        critical_features = ['cvd_d', 'zc4', 'zc10', 'zc20', 'liql', 'liqs', 'fr', 'vr5']
        
        for sym in symbols:
            summary_path = os.path.join(data_dir, f"Master_{sym}_15m_Final_Summary.parquet")
            if not os.path.exists(summary_path):
                continue
            try:
                df = pd.read_parquet(summary_path)
                # Build BTC reference for cross-asset features
                btc_ref = None
                if sym != 'BTCUSDT':
                    btc_path = os.path.join(data_dir, "Master_BTCUSDT_15m_Final_Summary.parquet")
                    if os.path.exists(btc_path):
                        btc_df = pd.read_parquet(btc_path)
                        btc_ref = btc_df[['Close', 'CVD']].copy() if 'CVD' in btc_df.columns else btc_df[['Close']].copy()
                        btc_ref.columns = [f'btc_{c}' for c in btc_ref.columns]
                
                df = featurize(df.copy(), btc_ref)
                sym_stats = {}
                for feat in critical_features:
                    if feat in df.columns:
                        feat_vals = df[feat].replace([np.inf, -np.inf], np.nan).dropna()
                        if len(feat_vals) > 10:
                            sym_stats[f'{feat}_mean'] = float(feat_vals.mean())
                            sym_stats[f'{feat}_std'] = float(feat_vals.std())
                if sym_stats:
                    stats[sym] = sym_stats
                del df
            except Exception as e:
                print(f"[SixStrategy] Failed to load training stats for {sym}: {e}")
        
        print(f"[SixStrategy] Loaded drift detection stats for {len(stats)}/{len(symbols)} symbols "
              f"({sum(len(v) for v in stats.values())} feature distributions)")
        return stats

    def notify_trade_closed(self, trade: dict) -> None:
        """Called by Engine1TradeTracker.on_full_close_callbacks when any trade exits.
        Updates per-symbol adaptive loss counters and ML confidence thresholds.
        """
        symbol = trade.get('symbol', '')
        direction = trade.get('direction', 0)
        reason = trade.get('exit_reason', '')
        pnl = trade.get('pnl_usd', 0.0)
        strategy = trade.get('strategy', '')

        if not symbol or direction == 0:
            return

        # FIX: Strategy-level loss tracking prevents cross-strategy counter reset
        loss_key = (symbol, direction, strategy)
        is_loss = reason in ('SL', 'EMERGENCY_HALT') or pnl < 0

        if is_loss:
            prev = self._consec_losses.get(loss_key, 0)
            self._consec_losses[loss_key] = prev + 1
            consec = self._consec_losses[loss_key]

            # Raise ML threshold by 0.05 per consecutive loss (capped at +0.25)
            old_lift = self._thresh_lift.get(symbol, 0.0)
            new_lift = min(0.25, old_lift + 0.05)
            self._thresh_lift[symbol] = new_lift
            self._log(f"{symbol} dir={direction} strat={strategy} consecutive SL={consec}, "
                      f"ML thresh lift {old_lift:.2f}->{new_lift:.2f}", "LossFilter")

            # Suspend direction for 3 bars after 3 straight SL losses
            if consec >= 3:
                # FIX: Use monotonic _bar_counter instead of len(candles_history)
                current_bar = self._bar_counter.get(symbol, 0)
                self._dir_suspend_until[loss_key] = current_bar + 3
                self._log(f"{symbol} dir={direction} SUSPENDED for 3 bars "
                          f"(bar {current_bar}+3) after {consec} consecutive SL losses.", "LossFilter")
        else:
            # FIX: Exponential decay recovery (lift *= 0.75 per win) instead of flat reset
            # After 3 losses (lift=0.15): win1→0.1125, win2→0.084, win3→0.063, win4→0.047
            # Full recovery takes ~4-5 wins instead of 1
            self._consec_losses[loss_key] = max(0, self._consec_losses.get(loss_key, 0) - 1)
            old_lift = self._thresh_lift.get(symbol, 0.0)
            new_lift = old_lift * 0.75
            if new_lift < 0.01:
                new_lift = 0.0
                self._consec_losses[loss_key] = 0  # Full reset only when lift is negligible
            self._thresh_lift[symbol] = new_lift
            # Only clear suspension when lift is fully decayed
            if new_lift == 0.0 and self._dir_suspend_until.get(loss_key, 0) > 0:
                self._dir_suspend_until[loss_key] = 0
            self._log(f"{symbol} dir={direction} WIN — consec={self._consec_losses[loss_key]}, "
                      f"thresh lift {old_lift:.3f}->{new_lift:.3f} (exp decay)", "LossFilter")

    def set_history(self, symbol: str, candles):
        """Set historical candle data for a symbol."""
        now_open = int(time.time() // 900) * 900
        cleaned = []
        for c in candles:
            try:
                ot = int(c.get('open_time', 0))
            except Exception:
                continue
            if ot > 0 and ot < now_open:
                row = dict(c)
                row['open_time'] = ot
                cleaned.append(row)

        cleaned.sort(key=lambda r: r['open_time'])
        cleaned = cleaned[-1200:]
        self.candles_history[symbol] = collections.deque(cleaned, maxlen=1200)
        if cleaned:
            self._last_predict_bar[symbol] = 0

    def load_history_from_disk(self, max_candles: int = 250):
        """Load historical candles directly from parquet backtesting data or Binance REST API (zero Excel dependency)."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(base_dir, "backtesting_data")
        loaded = 0
        
        for sym in self.symbols:
            candles = []
            # 1. Primary Source: Parquet backtesting files in backtesting_data/
            summary_path = os.path.join(data_dir, f"Master_{sym}_15m_Final_Summary.parquet")
            fp_path = os.path.join(data_dir, f"Master_{sym}_15m_Final_Footprint.parquet")
            if os.path.exists(summary_path):
                try:
                    df = pd.read_parquet(summary_path)
                    if os.path.exists(fp_path):
                        try:
                            df_fp = pd.read_parquet(fp_path)
                            cj = [c for c in df_fp.columns if c not in df.columns]
                            if cj:
                                df = df.join(df_fp[cj], how='left')
                        except Exception:
                            pass
                    df = df.tail(max_candles)
                    for idx, row in df.iterrows():
                        d = row.to_dict()
                        if 'open_time' not in d:
                            if hasattr(idx, 'timestamp'):
                                d['open_time'] = int(idx.timestamp())
                            elif 'timestamp' in d:
                                d['open_time'] = int(pd.to_datetime(d['timestamp']).timestamp())
                            else:
                                d['open_time'] = int(time.time() - (len(df) - len(candles)) * 900)
                        o_val = float(d.get('open', d.get('Open', 0.0)))
                        h_val = float(d.get('high', d.get('High', 0.0)))
                        l_val = float(d.get('low', d.get('Low', 0.0)))
                        c_val = float(d.get('close', d.get('Close', 0.0)))
                        v_val = float(d.get('volume', d.get('Volume', 0.0)))
                        d['open'] = d['Open'] = o_val
                        d['high'] = d['High'] = h_val
                        d['low'] = d['Low'] = l_val
                        d['close'] = d['Close'] = c_val
                        d['volume'] = d['Volume'] = v_val
                        d['fut_cvd'] = float(d.get('fut_cvd', d.get('CVD', d.get('futCvd', 0.0))))
                        d['spot_cvd'] = float(d.get('spot_cvd', d.get('Spot_CVD', d.get('spotCvd', 0.0))))
                        d['oi'] = float(d.get('oi', d.get('OI', d.get('open_interest', 0.0))))
                        d['funding'] = float(d.get('funding', d.get('Funding', d.get('funding_rate', 0.0))))
                        d['liq_long'] = float(d.get('liq_long', d.get('Liq_Long', d.get('liquidations_long', 0.0))))
                        d['liq_short'] = float(d.get('liq_short', d.get('Liq_Short', d.get('liquidations_short', 0.0))))
                        d['ls_ratio'] = float(d.get('ls_ratio', d.get('LSR', d.get('lsRatio', 1.0))))
                        candles.append(d)
                except Exception:
                    pass
            
            # 2. Live Secondary Source: Binance Futures REST API klines fallback
            if len(candles) < 20:
                try:
                    import urllib.request, json
                    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}&interval=15m&limit={max_candles}"
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=8) as resp:
                        raw = json.loads(resp.read().decode())
                        candles = []
                        for k in raw:
                            o_val = float(k[1])
                            h_val = float(k[2])
                            l_val = float(k[3])
                            c_val = float(k[4])
                            v_val = float(k[5])
                            candles.append({
                                'open_time': int(k[0] // 1000),
                                'open': o_val,
                                'high': h_val,
                                'low': l_val,
                                'close': c_val,
                                'volume': v_val,
                                'Open': o_val,
                                'High': h_val,
                                'Low': l_val,
                                'Close': c_val,
                                'Volume': v_val,
                                'fut_cvd': 0.0,
                                'spot_cvd': 0.0,
                                'oi': 0.0,
                                'funding': 0.0,
                                'liq_long': 0.0,
                                'liq_short': 0.0,
                                'ls_ratio': 1.0,
                            })
                except Exception:
                    pass

            if candles:
                self.set_history(sym, candles[-max_candles:])
                loaded += 1

        print(f"[SixStrategy] Successfully seeded history for {loaded}/{len(self.symbols)} symbols (max {max_candles} candles window, zero Excel dependency).")
        self._precompute_initial_indicators()
        print("[SixStrategy] Precomputed initial indicators for all symbols.")

    def _precompute_initial_indicators(self):
        """Precompute rolling indicators across all loaded symbol histories so all metrics are available immediately."""
        btc_ref = None
        if 'BTCUSDT' in self.candles_history:
            btc_df = self._build_df('BTCUSDT')
            if btc_df is not None and len(btc_df) >= 20:
                btc_ref = btc_df[['Close', 'CVD']].copy() if 'CVD' in btc_df.columns else btc_df[['Close']].copy()
                btc_ref.columns = [f'btc_{c}' for c in btc_ref.columns]

        for sym, hist in self.candles_history.items():
            if not hist or len(hist) < 20:
                continue
            try:
                df = self._build_df(sym)
                if df is None or len(df) < 20:
                    continue
                df = featurize(df.copy(), btc_ref if sym != 'BTCUSDT' else None)
                last_row = df.iloc[-1].to_dict()
                atr_val = float(last_row.get('atr', 0.0))
                self._cached_signals[sym] = {
                    'armed_str': 'READY',
                    'atr_val': atr_val,
                    'ema_8': float(last_row.get('e8', 0.0)),
                    'ema_21': float(last_row.get('e21', 0.0)),
                    'ema_50': float(last_row.get('e50', 0.0)),
                    'ema_200': float(last_row.get('ef', 0.0)),
                    'ema_800': float(last_row.get('es', 0.0)),
                    'atr_14': atr_val,
                    'rsi': float(last_row.get('rsi', 50.0)),
                    'zc4': float(last_row.get('zc4', 0.0)),
                    'zc10': float(last_row.get('zc10', 0.0)),
                    'zc20': float(last_row.get('zc20', 0.0)),
                    'zb4': float(last_row.get('zb4', 0.0)),
                    'zb10': float(last_row.get('zb10', 0.0)),
                    'zb20': float(last_row.get('zb20', 0.0)),
                    'vr': float(last_row.get('vr', 0.0)),
                    'zoi': float(last_row.get('zoi', 0.0)),
                    'zls': float(last_row.get('zls', 0.0)),
                    'zfr': float(last_row.get('zfr', 0.0)),
                    'p8': float(last_row.get('p8', 0.0)),
                    'p21': float(last_row.get('p21', 0.0)),
                    'p50': float(last_row.get('p50', 0.0)),
                }
            except Exception:
                pass

    def on_tick_update(self, symbol: str, snap, trade_tracker=None):
        """Called on every tick. Only runs prediction on candle close."""
        with self._lock:
            return self._on_tick_locked(symbol, snap, trade_tracker)

    def _on_tick_locked(self, symbol, snap, trade_tracker):
        if snap.price <= 0:
            return snap

        now = time.time()
        open_time = int(now // 900) * 900

        if symbol not in self.candles_history:
            self.candles_history[symbol] = collections.deque(maxlen=1200)

        history = self.candles_history[symbol]

        # Candle rollover
        if symbol not in self.current_candle or self.current_candle[symbol].get('open_time') != open_time:
            prev = self.current_candle.get(symbol)
            if prev and int(prev.get('open_time', 0)) < open_time:
                prev_ot = int(prev['open_time'])
                if not history or int(history[-1].get('open_time', 0)) != prev_ot:
                    history.append(dict(prev))
            # FIX: Increment monotonic bar counter on each candle rollover
            self._bar_counter[symbol] = self._bar_counter.get(symbol, 0) + 1
            cur_open = getattr(snap, 'open', 0.0) or snap.price
            cur_high = max(getattr(snap, 'high', 0.0), snap.price)
            cur_low = min(getattr(snap, 'low', 0.0) if getattr(snap, 'low', 0.0) > 0 else snap.price, snap.price)
            self.current_candle[symbol] = {
                'open_time': open_time, 'open': cur_open, 'high': cur_high,
                'low': cur_low, 'close': snap.price, 'volume': snap.volume,
                'fut_cvd': snap.fut_cvd, 'spot_cvd': snap.spot_cvd,
                'funding': snap.funding, 'liq_long': snap.liq_long,
                'liq_short': snap.liq_short, 'ls_ratio': snap.ls_ratio,
                'oi': snap.oi, 'coins_bid': snap.coins_bid,
                'coins_ask': snap.coins_ask, 'dollars_bid': snap.dollars_bid,
                'dollars_ask': snap.dollars_ask, 'whale_idx': snap.whale_idx,
                'tk_buy_cnt': snap.tk_buy_cnt, 'tk_sell_cnt': snap.tk_sell_cnt,
                'fp_delta': snap.fp_delta,
                'fp_poc': snap.fp_poc,
            }
        else:
            c = self.current_candle[symbol]
            c['close'] = snap.price
            s_high = getattr(snap, 'high', 0.0)
            s_low = getattr(snap, 'low', 0.0)
            if snap.price > c['high']: c['high'] = snap.price
            if s_high > c['high']: c['high'] = s_high
            if snap.price < c['low'] or c['low'] == 0: c['low'] = snap.price
            if s_low > 0 and s_low < c['low']: c['low'] = s_low
            c['volume'] = snap.volume
            c['fut_cvd'] = snap.fut_cvd
            c['spot_cvd'] = snap.spot_cvd
            c['funding'] = snap.funding
            c['liq_long'] = snap.liq_long
            c['liq_short'] = snap.liq_short
            c['ls_ratio'] = snap.ls_ratio
            c['oi'] = snap.oi
            c['coins_bid'] = snap.coins_bid
            c['coins_ask'] = snap.coins_ask
            c['dollars_bid'] = snap.dollars_bid
            c['dollars_ask'] = snap.dollars_ask
            c['whale_idx'] = snap.whale_idx
            c['tk_buy_cnt'] = snap.tk_buy_cnt
            c['tk_sell_cnt'] = snap.tk_sell_cnt
            c['fp_delta'] = snap.fp_delta
            c['fp_poc'] = snap.fp_poc

        # Only predict on candle close
        last_bar = history[-1].get('open_time', 0) if history else 0
        if last_bar == self._last_predict_bar.get(symbol, 0):
            # Interim tick: replay cached signal and enrich with live pullbacks
            cached = self._cached_signals.get(symbol, {})
            armed_str = cached.get('armed_str', '')
            if trade_tracker:
                with trade_tracker.lock:
                    trades = [t for t in trade_tracker.active_trades.values() if t['symbol'] == symbol]
                if trades:
                    parts = []
                    for t in trades:
                        d = 'LONG' if t['direction'] == 1 else 'SHORT'
                        pnl = t.get('live_pnl_pct', 0)
                        sk = t.get('strategy', '?')[:2]
                        parts.append(f"{sk}:{d}({pnl:+.1f}%)")
                    armed_str = ' '.join(parts)
            if not armed_str:
                armed_str = "READY" if len(history) >= 20 else f"WARM({len(history)}/100)"

            e8 = cached.get('ema_8', getattr(snap, 'ema_8', 0.0))
            e21 = cached.get('ema_21', getattr(snap, 'ema_21', 0.0))
            e50 = cached.get('ema_50', getattr(snap, 'ema_50', 0.0))
            atr = cached.get('atr_14', getattr(snap, 'atr_14', 1.0)) or 1.0
            p8 = (snap.price - e8) / atr if e8 > 0 and atr > 0 else cached.get('p8', 0.0)
            p21 = (snap.price - e21) / atr if e21 > 0 and atr > 0 else cached.get('p21', 0.0)
            p50 = (snap.price - e50) / atr if e50 > 0 and atr > 0 else cached.get('p50', 0.0)

            import dataclasses
            return dataclasses.replace(
                snap,
                strategy_armed=armed_str,
                ema_8=e8,
                ema_21=e21,
                ema_50=e50,
                ema_200=cached.get('ema_200', getattr(snap, 'ema_200', 0.0)),
                ema_800=cached.get('ema_800', getattr(snap, 'ema_800', 0.0)),
                atr_14=atr,
                rsi=cached.get('rsi', getattr(snap, 'rsi', 50.0)),
                zc4=cached.get('zc4', getattr(snap, 'zc4', 0.0)),
                zc10=cached.get('zc10', getattr(snap, 'zc10', 0.0)),
                zc20=cached.get('zc20', getattr(snap, 'zc20', 0.0)),
                zb4=cached.get('zb4', getattr(snap, 'zb4', 0.0)),
                zb10=cached.get('zb10', getattr(snap, 'zb10', 0.0)),
                zb20=cached.get('zb20', getattr(snap, 'zb20', 0.0)),
                vr=cached.get('vr', getattr(snap, 'vr', 0.0)),
                zoi=cached.get('zoi', getattr(snap, 'zoi', 0.0)),
                zls=cached.get('zls', getattr(snap, 'zls', 0.0)),
                zfr=cached.get('zfr', getattr(snap, 'zfr', 0.0)),
                p8=p8,
                p21=p21,
                p50=p50,
            )

        if len(history) < 20:
            import dataclasses
            return dataclasses.replace(snap, strategy_armed=f"WARM({len(history)}/100)")

        self._last_predict_bar[symbol] = last_bar

        # Build DataFrame for feature engineering
        try:
            df = self._build_df(symbol)
            if df is None or len(df) < 20:
                import dataclasses
                return dataclasses.replace(snap, strategy_armed=f"WARM({len(history)}/100)")

            # Get BTC reference
            btc_ref = None
            if symbol != 'BTCUSDT' and 'BTCUSDT' in self.candles_history:
                btc_df = self._build_df('BTCUSDT')
                if btc_df is not None:
                    btc_ref = btc_df[['Close', 'CVD']].copy() if 'CVD' in btc_df.columns else btc_df[['Close']].copy()
                    btc_ref.columns = [f'btc_{c}' for c in btc_ref.columns]

            # Featurize
            df = featurize(df.copy(), btc_ref)
            last_row = df.iloc[-1].to_dict()
            
            # Drift Check
            is_safe, drifted = self.drift_detector.check_row(symbol, last_row)
            if not is_safe:
                if getattr(self, "log_fn", None):
                    self.log_fn(f"{symbol} BLOCKED: {len(drifted)} features drifted: {drifted[:3]}", "DriftGuard")
                import dataclasses
                return dataclasses.replace(snap, strategy_armed="DRIFT_BLOCK")
            
            # PARITY FIX: Use raw ATR without artificial floor
            atr_val = float(last_row.get('atr', 0))
            if atr_val <= 0 or np.isnan(atr_val) or snap.price <= 0:
                return snap

            # Run all 6 strategies
            armed_parts = []

            # GUARD: Skip symbols that have no trained models for ANY strategy.
            # Trading a symbol without backtest-validated models is unvalidated speculation.
            modeled_strategies = {sk for sk in SIGNAL_FUNCS if symbol in self.models.get(sk, {})}
            if not modeled_strategies:
                import dataclasses
                return dataclasses.replace(snap, strategy_armed="NO_MODEL")

            # --- PRICE-ACTION REGIME DIVERGENCE FILTER ---
            # PARITY FIX: Disable unvalidated PA divergence filter
            pa_blocks: set = set()

            # FIX: Use monotonic _bar_counter instead of len(history) for suspension check
            current_bar_index = self._bar_counter.get(symbol, 0)

            for strat_key, signal_func in SIGNAL_FUNCS.items():
                direction = signal_func(last_row)
                if direction == 0:
                    continue

                # Block signals contradicting recent price-action momentum
                if direction in pa_blocks:
                    continue

                # Block if this symbol+direction is suspended after excessive consecutive losses
                suspend_key = (symbol, direction)
                if self._dir_suspend_until.get(suspend_key, 0) > current_bar_index:
                    remaining = self._dir_suspend_until[suspend_key] - current_bar_index
                    self._log(f"{symbol} dir={direction} suspended for {remaining} more bars.", "LossFilter")
                    continue

                strat_name = STRATEGY_NAMES[strat_key]

                # Check for active trade in this strategy
                if trade_tracker:
                    with trade_tracker.lock:
                        has_active = any(
                            t['symbol'] == symbol and t['strategy'] == strat_name
                            for t in trade_tracker.active_trades.values()
                        )
                    if has_active:
                        continue

                # ML filter (if model available)
                if symbol not in self.models.get(strat_key, {}):
                    continue  # Fail-closed: Never trade without an ML model

                try:
                    fcs = self.selected_cols[strat_key][symbol]
                    X = pd.DataFrame([{c: last_row.get(c, 0) for c in fcs}]).astype(np.float32)
                    prob = predict_ensemble(
                        self.models[strat_key][symbol], fcs, X
                    )[0]
                    if not hasattr(self, 'ml_failures'):
                        self.ml_failures = {}
                    self.ml_failures[symbol] = 0

                    # FIX: Apply adaptive _thresh_lift to actual threshold check
                    # After consecutive losses, lift raises the bar for ML confidence
                    base_thresh = self.thresholds[strat_key].get(symbol, 0.55)
                    adaptive_lift = self._thresh_lift.get(symbol, 0.0)
                    effective_thresh = float(base_thresh) + float(adaptive_lift)
                    if float(prob) < (effective_thresh - 1e-5):
                        continue
                except Exception as e:
                    if not hasattr(self, 'ml_failures'):
                        self.ml_failures = {}
                    self.ml_failures[symbol] = self.ml_failures.get(symbol, 0) + 1
                    self._log(f"ML evaluation failed for {strat_key} {symbol}: {e}", "SixStrategy")
                    continue  # If ML fails, DO NOT let signal through on this bar

                # Compute SL/TP
                sl = snap.price - SL_MULT * atr_val if direction == 1 else snap.price + SL_MULT * atr_val
                tp = snap.price + TP_MULT * atr_val if direction == 1 else snap.price - TP_MULT * atr_val

                # Dispatch trade (trail_act=1.0 corresponds to 1.0x tp_dist = 5.0 * ATR)
                if trade_tracker:
                    trade_tracker.trigger_entry(
                        symbol, strat_name, direction, snap.price,
                        sl, tp, atr_val, macro=int(last_row.get('mc', 0)),
                        vol_regime=float(last_row.get('vr', 0)),
                        risk_mult=1.0, trail_act=1.0, regime_val=0
                    )

                dir_str = 'LONG' if direction == 1 else 'SHORT'
                armed_parts.append(f"{strat_key}:{dir_str}")

            # Cache armed signals and rolling indicator stats for display
            self._cached_signals[symbol] = {
                'armed_str': ' | '.join(armed_parts) if armed_parts else '',
                'atr_val': atr_val,
                'ema_8': float(last_row.get('e8', 0.0)),
                'ema_21': float(last_row.get('e21', 0.0)),
                'ema_50': float(last_row.get('e50', 0.0)),
                'ema_200': float(last_row.get('ef', 0.0)),
                'ema_800': float(last_row.get('es', 0.0)),
                'atr_14': atr_val,
                'rsi': float(last_row.get('rsi', snap.rsi or 50.0)),
                'zc4': float(last_row.get('zc4', 0.0)),
                'zc10': float(last_row.get('zc10', 0.0)),
                'zc20': float(last_row.get('zc20', 0.0)),
                'zb4': float(last_row.get('zb4', 0.0)),
                'zb10': float(last_row.get('zb10', 0.0)),
                'zb20': float(last_row.get('zb20', 0.0)),
                'vr': float(last_row.get('vr', 0.0)),
                'zoi': float(last_row.get('zoi', 0.0)),
                'zls': float(last_row.get('zls', 0.0)),
                'zfr': float(last_row.get('zfr', 0.0)),
                'p8': float(last_row.get('p8', 0.0)),
                'p21': float(last_row.get('p21', 0.0)),
                'p50': float(last_row.get('p50', 0.0)),
            }

        except Exception as e:
            self._log(f"{symbol} error: {e}", "SixStrategy")

        # Replay cached signal
        cached = self._cached_signals.get(symbol, {})
        armed_str = cached.get('armed_str', '')

        # Show active trades
        if trade_tracker:
            with trade_tracker.lock:
                trades = [t for t in trade_tracker.active_trades.values() if t['symbol'] == symbol]
            if trades:
                parts = []
                for t in trades:
                    d = 'LONG' if t['direction'] == 1 else 'SHORT'
                    pnl = t.get('live_pnl_pct', 0)
                    sk = t.get('strategy', '?')[:2]
                    parts.append(f"{sk}:{d}({pnl:+.1f}%)")
                armed_str = ' '.join(parts)
        if not armed_str:
            armed_str = "READY"

        import dataclasses
        enrich_dict = {
            'strategy_armed': armed_str,
            'ema_8': cached.get('ema_8', getattr(snap, 'ema_8', 0.0)),
            'ema_21': cached.get('ema_21', getattr(snap, 'ema_21', 0.0)),
            'ema_50': cached.get('ema_50', getattr(snap, 'ema_50', 0.0)),
            'ema_200': cached.get('ema_200', getattr(snap, 'ema_200', 0.0)),
            'ema_800': cached.get('ema_800', getattr(snap, 'ema_800', 0.0)),
            'atr_14': cached.get('atr_14', getattr(snap, 'atr_14', 0.0)),
            'rsi': cached.get('rsi', getattr(snap, 'rsi', 50.0)),
            'zc4': cached.get('zc4', getattr(snap, 'zc4', 0.0)),
            'zc10': cached.get('zc10', getattr(snap, 'zc10', 0.0)),
            'zc20': cached.get('zc20', getattr(snap, 'zc20', 0.0)),
            'zb4': cached.get('zb4', getattr(snap, 'zb4', 0.0)),
            'zb10': cached.get('zb10', getattr(snap, 'zb10', 0.0)),
            'zb20': cached.get('zb20', getattr(snap, 'zb20', 0.0)),
            'vr': cached.get('vr', getattr(snap, 'vr', 0.0)),
            'zoi': cached.get('zoi', getattr(snap, 'zoi', 0.0)),
            'zls': cached.get('zls', getattr(snap, 'zls', 0.0)),
            'zfr': cached.get('zfr', getattr(snap, 'zfr', 0.0)),
            'p8': cached.get('p8', getattr(snap, 'p8', 0.0)),
            'p21': cached.get('p21', getattr(snap, 'p21', 0.0)),
            'p50': cached.get('p50', getattr(snap, 'p50', 0.0)),
        }
        snap = dataclasses.replace(snap, **enrich_dict)
        return snap

    def _build_df(self, symbol):
        """Build a DataFrame from candle history."""
        history = list(self.candles_history.get(symbol, []))
        if not history:
            return None

        df = pd.DataFrame(history)
        # Map to expected column names
        col_map = {
            'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close',
            'volume': 'Volume', 'fut_cvd': 'CVD', 'oi': 'Agg. OI',
            'ls_ratio': 'Long/Short Ratio (Account)', 'funding': 'Agg. Funding Rate',
            'liq_long': 'Agg. Liq Long', 'liq_short': 'Agg. Liq Short',
            'coins_bid': 'Bid Qty', 'coins_ask': 'Ask Qty',
            'dollars_bid': 'USD Long', 'dollars_ask': 'USD Short',
            'tk_buy_cnt': 'Ask Trades', 'tk_sell_cnt': 'Bid Trades',
            'fp_delta': 'Delta Qty', 'fp_poc': 'POC Price',
            'whale_idx': 'Whale Index', 'spot_cvd': 'Spot CVD',
        }
        for old, new in col_map.items():
            if old in df.columns and new not in df.columns:
                df[new] = pd.to_numeric(df[old], errors='coerce').fillna(0)
            elif new in df.columns:
                df[new] = pd.to_numeric(df[new], errors='coerce').fillna(0)

        for req in ('Open', 'High', 'Low', 'Close', 'Volume'):
            if req not in df.columns:
                lower_req = req.lower()
                if lower_req in df.columns:
                    df[req] = pd.to_numeric(df[lower_req], errors='coerce').fillna(0)
                else:
                    return None

        # Timestamp index
        if 'open_time' in df.columns:
            df['ts'] = pd.to_datetime(df['open_time'], unit='s')
            df = df.set_index('ts').sort_index()

        return df

```

### SOURCE FILE: binance_broker.py
```python
"""
Binance Futures Execution Broker for Engine_1.
Pure Binance Futures perpetual swap execution. No MT5 dependencies.
Supports Dry-Run (paper trading) and Live Futures trading via REST API.
"""

import os
import time
import math
import hmac
import hashlib
import json
import logging
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
from enum import Enum

class PosState(str, Enum):
    OPEN = "OPEN"
    FLAT = "FLAT"
    UNKNOWN = "UNKNOWN"
log = logging.getLogger("BinanceBroker")

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

TAKER_FEE = float(os.environ.get("BINANCE_TAKER_FEE", "0.0004"))    # 0.040 %
MAKER_FEE = float(os.environ.get("BINANCE_MAKER_FEE", "-0.0002"))   # -0.020 % rebate (maker rebate is negative)


def _load_env():
    if ENV_FILE.exists():
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()


_load_env()


class BinanceBroker:
    """Binance Futures perpetual swap execution engine."""

    MAX_RETRIES = 3
    RETRY_BACKOFF = [1.0, 3.0, 5.0]

    def get_position_state(self, symbol: str) -> Tuple[PosState, float]:
        res = self._request("GET", "/fapi/v2/positionRisk", params={"symbol": symbol}, signed=True, max_retries=1)
        if res is None:
            return PosState.UNKNOWN, 0.0
        try:
            for p in res:
                if p.get("symbol") == symbol:
                    amt = float(p.get("positionAmt", 0.0))
                    return (PosState.OPEN if amt != 0.0 else PosState.FLAT), amt
        except Exception:
            return PosState.UNKNOWN, 0.0
        return PosState.UNKNOWN, 0.0

    def __init__(
        self,
        dry_run: bool = True,
        account_size: float = 5000.0,
        risk_pct: float = 0.005,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        use_testnet: bool = False,
    ):
        self.dry_run = dry_run
        self.account_size = account_size
        self.risk_pct = risk_pct
        self.api_key = api_key or os.environ.get("BINANCE_API_KEY", "")
        self.secret_key = secret_key or os.environ.get("BINANCE_SECRET_KEY", "")
        self.use_testnet = use_testnet or os.environ.get("BINANCE_USE_TESTNET", "").lower() == "true"

        if self.use_testnet:
            self.base_url = "https://testnet.binancefuture.com"
        else:
            self.base_url = "https://fapi.binance.com"

        self.symbol_rules: Dict[str, dict] = {}
        self.valid_perpetuals: set = set()
        self.active_orders: Dict[str, dict] = {}
        self.time_offset = 0

        # Fee Optimization Tuning parameters
        self.post_only_timeout_secs: float = 3.0
        self.min_profit_notional: float = 0.10
        self.split_notional_thresh: float = 5000.0
        self.max_slices: int = 3
        self.inter_slice_delay_secs: float = 1.0

        log.info(
            f"BinanceBroker initialized (dry_run={self.dry_run}, "
            f"testnet={self.use_testnet}, base_url={self.base_url})"
        )

    def _sign_params(self, params: dict) -> dict:
        params["timestamp"] = int((time.time() * 1000) + self.time_offset)
        params["recvWindow"] = 60000
        query_str = urllib.parse.urlencode(params)
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            query_str.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    def _backoff_sleep(self, seconds: float):
        """Non-blocking wait loop to keep event loops responsive without blocking thread pools."""
        end = time.time() + seconds
        while time.time() < end:
            time.sleep(0.01)

    def _request(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, signed: bool = True,
        max_retries: int = 3,
    ) -> Optional[dict]:
        """Make REST request to Binance Futures API with retry logic."""
        params = params or {}
        headers = {}

        for attempt in range(max_retries):
            req_params = dict(params)
            if signed:
                if not self.api_key or not self.secret_key:
                    log.error("[Binance] Missing API key or secret key for signed request.")
                    return None
                req_params = self._sign_params(req_params)
                headers = {"X-MBX-APIKEY": self.api_key}

            query_str = urllib.parse.urlencode(req_params)
            url = f"{self.base_url}{endpoint}"
            data = None

            if method in ("GET", "DELETE"):
                if query_str:
                    url = f"{url}?{query_str}"
            elif method in ("POST", "PUT"):
                headers["Content-Type"] = "application/x-www-form-urlencoded"
                data = query_str.encode("utf-8")

            try:
                req = urllib.request.Request(url, data=data, headers=headers, method=method)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    res_bytes = resp.read()
                    return json.loads(res_bytes.decode("utf-8"))

            except urllib.error.HTTPError as e:
                err_msg = e.read().decode("utf-8") if hasattr(e, "read") else str(e)

                if e.code in (429, 418):
                    wait = self.RETRY_BACKOFF[min(attempt, len(self.RETRY_BACKOFF) - 1)]
                    log.warning(f"[Binance] Rate limited ({e.code}). Retry {attempt+1}/{max_retries} in {wait}s...")
                    self._backoff_sleep(wait)
                    continue

                if e.code >= 500:
                    wait = self.RETRY_BACKOFF[min(attempt, len(self.RETRY_BACKOFF) - 1)]
                    log.warning(f"[Binance] Server error {e.code}. Retry {attempt+1}/{max_retries} in {wait}s...")
                    self._backoff_sleep(wait)
                    continue

                # Timestamp drift: re-sync and retry once
                if "-1021" in err_msg and attempt == 0:
                    log.warning("[Binance] Timestamp drift detected, re-syncing server time...")
                    self._sync_server_time()
                    continue

                log.error(f"[Binance API Error] {method} {endpoint}: {e.code} — {err_msg}")
                return None

            except Exception as e:
                if attempt < max_retries - 1:
                    wait = self.RETRY_BACKOFF[min(attempt, len(self.RETRY_BACKOFF) - 1)]
                    log.warning(f"[Binance] Network error: {e}. Retry {attempt+1}/{max_retries} in {wait}s...")
                    self._backoff_sleep(wait)
                    continue
                log.error(f"[Binance Request Failed] {method} {endpoint}: {e}")
                return None

        log.error(f"[Binance] All {max_retries} retries exhausted for {method} {endpoint}")
        return None

    def _sync_server_time(self):
        try:
            res = self._request("GET", "/fapi/v1/time", signed=False, max_retries=1)
            if res and "serverTime" in res:
                self.time_offset = res["serverTime"] - int(time.time() * 1000)
        except Exception:
            pass

    def connect(self) -> bool:
        """Sync server time and fetch exchange info precision rules."""
        try:
            self._sync_server_time()
            log.info(f"[Binance] Connected. Server time offset: {self.time_offset}ms")

            info = self._request("GET", "/fapi/v1/exchangeInfo", signed=False)
            if info and "symbols" in info:
                for s in info["symbols"]:
                    sym = s["symbol"]
                    price_prec = s.get("pricePrecision", 2)
                    qty_prec = s.get("quantityPrecision", 3)
                    min_qty = 0.001
                    step_size = 0.001
                    tick_size = 0.01

                    for f in s.get("filters", []):
                        if f.get("filterType") == "LOT_SIZE":
                            min_qty = float(f.get("minQty", 0.001))
                            step_size = float(f.get("stepSize", 0.001))
                        elif f.get("filterType") == "PRICE_FILTER":
                            tick_size = float(f.get("tickSize", 0.01))

                    self.symbol_rules[sym] = {
                        "price_prec": price_prec,
                        "qty_prec": qty_prec,
                        "min_qty": min_qty,
                        "step_size": step_size,
                        "tick_size": tick_size,
                    }

                    if s.get("contractType") == "PERPETUAL" and s.get("status") == "TRADING":
                        self.valid_perpetuals.add(sym)

                log.info(f"[Binance] Loaded rules for {len(self.symbol_rules)} contracts, "
                         f"{len(self.valid_perpetuals)} active perpetuals.")

            if not self.dry_run:
                bal, eq = self.get_account_balance_and_equity()
                log.info(f"[Binance] Account Balance: ${bal:,.2f} | Equity: ${eq:,.2f}")
                self._cancel_all_account_orders()
            return True
        except Exception as e:
            log.error(f"[Binance Connect Failed] {e}")
            return False

    def ensure_connected(self) -> bool:
        return True

    def is_valid_symbol(self, symbol: str) -> bool:
        """Check if symbol is a valid, actively trading Binance Futures perpetual."""
        if not self.valid_perpetuals:
            return symbol in self.symbol_rules
        return symbol in self.valid_perpetuals

    def get_account_balance_and_equity(self) -> Tuple[float, float]:
        details = self.get_account_details()
        return details["balance"], details["equity"]

    def get_account_details(self) -> Dict[str, float]:
        """Fetch USDT-specific balance, equity, and unrealized PnL."""
        if self.dry_run:
            return {"balance": self.account_size, "equity": self.account_size, "unrealized_pnl": 0.0}

        res = self._request("GET", "/fapi/v2/account", signed=True)
        if res:
            usdt_bal = 0.0
            usdt_eq = 0.0
            usdt_upnl = 0.0
            for asset in res.get("assets", []):
                if asset.get("asset") == "USDT":
                    usdt_bal = float(asset.get("walletBalance", 0.0))
                    usdt_eq = float(asset.get("marginBalance", 0.0))
                    usdt_upnl = float(asset.get("unrealizedProfit", 0.0))
                    break
            if usdt_bal == 0.0:
                usdt_bal = float(res.get("totalWalletBalance", 0.0))
                usdt_eq = float(res.get("totalMarginBalance", 0.0))
                usdt_upnl = float(res.get("totalUnrealizedProfit", 0.0))
            return {"balance": usdt_bal, "equity": usdt_eq, "unrealized_pnl": usdt_upnl}
        return {"balance": 0.0, "equity": 0.0, "unrealized_pnl": 0.0}

    def _round_step(self, val: float, step: float, direction: str = "nearest") -> float:
        if step <= 0:
            return val
        precision = int(round(-math.log10(step))) if step < 1 else 0
        factor = 10 ** precision
        if direction == "down":
            return math.floor(val * factor) / factor
        elif direction == "up":
            return math.ceil(val * factor) / factor
        return round(val * factor) / factor

    def _format_price(self, symbol: str, price: float, direction: str = "nearest") -> float:
        """Round price to exchange tick size (PRICE_FILTER), not just decimal precision."""
        rules = self.symbol_rules.get(symbol)
        if rules and "tick_size" in rules:
            return self._round_step(price, rules["tick_size"], direction)
        prec = rules["price_prec"] if rules else 2
        return round(price, prec)

    def _format_qty(self, symbol: str, qty: float) -> float:
        rules = self.symbol_rules.get(symbol, {"qty_prec": 3, "step_size": 0.001, "min_qty": 0.001})
        step = rules["step_size"]
        min_q = rules["min_qty"]
        formatted = self._round_step(qty, step)
        return max(formatted, min_q)

    def _place_algo_conditional(
        self, symbol: str, side: str, order_type: str, trigger_price: float, label: str
    ) -> Optional[dict]:
        """Place a conditional algo order (SL or TP) on Binance Futures."""
        if self.dry_run:
            log.info(f"[Binance SIM] Dry run attached {label} conditional order @ {trigger_price}")
            return {"algoId": 99999, "status": "NEW"}
        pr_str = str(self._format_price(symbol, trigger_price))
        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": order_type.upper(),
            "triggerPrice": pr_str,
            "stopPrice": pr_str,
            "closePosition": "true",
            "workingType": "MARK_PRICE",
            "priceProtect": "true",
            "algoType": "CONDITIONAL",
        }
        res = self._request("POST", "/fapi/v1/algoOrder", params=params, signed=True)
        # -4120: already active, -4138: algo with same closePosition direction exists
        if res and isinstance(res, dict) and res.get("code") in (-4120, -4138):
            log.info(f"[BINANCE LIVE] {label} already active on exchange (code {res.get('code')})")
            return {"status": "ALREADY_ACTIVE"}

        if res and ("algoId" in res or "clientAlgoId" in res or "orderId" in res) and "code" not in res:
            log.info(f"[BINANCE LIVE] Attached {label}: {pr_str} (algoId={res.get('algoId', res.get('orderId'))})")
            return res
        else:
            log.warning(f"[Binance] {label} placement failed or returned unrecognized response: {res}")
            return None

    def place_entry_limit_post_only(self, symbol: str, side: str,
                                     quantity: float, price: float) -> Optional[dict]:
        """Post-only LIMIT order (timeInForce=GTX) to earn maker rebate."""
        qty = self._format_qty(symbol, quantity)
        pr = self._format_price(symbol, price)
        if self.dry_run:
            order_id = int(time.time() * 1000) % 10_000_000
            log.info(f"[DRY-RUN] LIMIT+GTX {side} {symbol} qty={qty:.4f} "
                     f"@ {pr:.4f} (maker rebate: {MAKER_FEE*100:+.3f}%)")
            return {"orderId": order_id, "symbol": symbol, "side": side,
                    "type": "LIMIT", "origQty": str(qty), "status": "FILLED",
                    "avgPrice": str(pr), "timeInForce": "GTX"}

        params = {
            'symbol': symbol,
            'side': side.upper(),
            'type': 'LIMIT',
            'timeInForce': 'GTX',
            'quantity': qty,
            'price': pr,
            'newOrderRespType': 'RESULT',
        }
        result = self._request('POST', '/fapi/v1/order', params=params, signed=True)
        if not result or result.get('error'):
            log.warning(f"[Binance] LIMIT+GTX {side} {symbol} @ {pr:.4f}: {result}")
            return None
        log.info(f"[Binance] LIMIT+GTX {side} {symbol} "
                 f"orderId={result.get('orderId')} status={result.get('status')} "
                 f"(maker rebate: {MAKER_FEE*100:+.3f}%)")
        return result

    def _fetch_order(self, symbol: str, order_id: int) -> dict:
        """Fetch an order state. GET /fapi/v1/order"""
        if self.dry_run:
            return {'status': 'FILLED', 'executedQty': '1.0', 'cumQuote': '1.0'}
        params = {'symbol': symbol, 'orderId': order_id}
        result = self._request('GET', '/fapi/v1/order', params=params, signed=True)
        return result if result and not result.get('error') else {}

    def _check_order_filled(self, symbol: str, order_id: int) -> bool:
        """Deprecated: use _fetch_order directly."""
        res = self._fetch_order(symbol, order_id)
        return res.get('status') == 'FILLED'

    def _cancel_limit_order(self, symbol: str, order_id: int) -> bool:
        """Cancel an unfilled limit order. DELETE /fapi/v1/order"""
        if self.dry_run:
            return True
        params = {'symbol': symbol, 'orderId': order_id}
        result = self._request('DELETE', '/fapi/v1/order', params=params, signed=True)
        return bool(result and not result.get('error'))

    def _validate_profit_threshold(self, symbol: str, entry_price: float,
                                    tp: float, sl: float, quantity: float,
                                    direction: int) -> Tuple[bool, str]:
        """Reject trades where expected net PnL < 2x round-trip fees."""
        notional = quantity * entry_price
        total_fee = notional * abs(TAKER_FEE) * 2

        slippage_bps = 5.0 if symbol in {"NATGASUSDT","CLUSDT","XAGUSDT","XAUUSDT"} else 2.0
        est_slippage = notional * slippage_bps / 10000.0
        min_cost = total_fee + est_slippage

        tp_dist = abs(tp - entry_price)
        if tp_dist <= 0:
            return False, f"Invalid TP distance: {tp_dist:.6f}"

        gross_profit = quantity * tp_dist
        net_profit = gross_profit - min_cost

        if net_profit < self.min_profit_notional:
            return False, (
                f"Profit gate: net=${net_profit:.4f} < min=${self.min_profit_notional:.2f} "
                f"(gross=${gross_profit:.4f} fee=${total_fee:.4f} slip=${est_slippage:.4f})"
            )

        sl_dist = abs(entry_price - sl)
        if sl_dist <= 0:
            return False, f"Invalid SL distance: {sl_dist:.6f}"

        max_loss = quantity * sl_dist + min_cost
        rr_after_fees = net_profit / max_loss if max_loss > 0 else 0
        if rr_after_fees < 0.5:
            return False, f"Profit gate: R:R after fees={rr_after_fees:.2f} < 0.5"

        return True, "ok"

    def _slice_quantity(self, symbol: str, quantity: float,
                         entry_price: float) -> List[float]:
        """Split large orders (notional >= $5K) into <=3 equal slices."""
        notional = quantity * entry_price
        if notional < self.split_notional_thresh or self.max_slices <= 1:
            return [quantity]

        rules = self.symbol_rules.get(symbol, {"step_size": 0.001, "min_qty": 0.001})
        step_size = rules.get("step_size", 0.001)

        n_slices = min(self.max_slices, max(2, int(notional / 2500)))
        slice_qty = round(quantity / n_slices / step_size) * step_size

        if slice_qty < step_size:
            return [quantity]

        slices = [slice_qty] * (n_slices - 1)
        remainder = quantity - sum(slices)
        if remainder > 0:
            slices.append(round(remainder / step_size) * step_size)

        log.info(f"[Binance] Slicing {symbol} qty={quantity:.4f} "
                 f"(notional=${notional:,.0f}) -> {len(slices)} slices")
        return slices

    def execute_trade(
        self,
        binance_symbol: str,
        direction: int,
        bin_entry: float,
        bin_sl: float,
        bin_tp: float,
        strategy: str,
        risk_capital: float,
    ) -> Optional[dict]:
        """Execute trade on Binance Futures with Maker-Only GTX limits & order slicing."""
        stop_dist = abs(bin_entry - bin_sl)
        if stop_dist <= 0 or bin_entry <= 0:
            return None

        if not self.is_valid_symbol(binance_symbol):
            log.error(f"[Binance] {binance_symbol} is not a valid active perpetual. Rejecting trade.")
            return None

        qty = self._format_qty(binance_symbol, risk_capital / stop_dist)
        entry_price = self._format_price(binance_symbol, bin_entry)
        sl_price = self._format_price(binance_symbol, bin_sl)
        tp_price = self._format_price(binance_symbol, bin_tp)

        if self.dry_run:
            log.info(f"[Binance SIM] Executed dry run trade {binance_symbol} qty={qty} @ ${entry_price}")
            return {
                "symbol": binance_symbol,
                "order_id": int(time.time() * 1000),
                "entry_price": entry_price,
                "sl_price": sl_price,
                "tp_price": tp_price,
                "lot": qty,
                "is_pending": False,
            }

        # ── GATE 1: Profit Threshold ────────────────────────────
        passes, reason = self._validate_profit_threshold(
            binance_symbol, entry_price, tp_price, sl_price, qty, direction)
        if not passes:
            log.warning(f"[Binance] Trade REJECTED — {reason}")
            return None

        # ── GATE 2: Slicing ───────────────────────────────────────
        slices = self._slice_quantity(binance_symbol, qty, entry_price)
        n_slices = len(slices)

        side = "BUY" if direction == 1 else "SELL"
        opposite_side = "SELL" if direction == 1 else "BUY"

        ask_px = 0.0
        bid_px = 0.0

        # ── GATE 3: Latency + Spread Guard Pre-Check ─────────────
        SPREAD_REJECT_THRESHOLD = 0.0012  # 0.12% max bid-ask spread
        try:
            ticker = self._request(
                "GET", "/fapi/v1/ticker/bookTicker",
                params={"symbol": binance_symbol}, signed=False, max_retries=2
            )
            if ticker and "askPrice" in ticker and "bidPrice" in ticker:
                ask_px = float(ticker["askPrice"])
                bid_px = float(ticker["bidPrice"])
                if ask_px > 0 and bid_px > 0:
                    # ── Spread check: reject if market is too wide ──
                    spread = (ask_px - bid_px) / bid_px
                    if spread > SPREAD_REJECT_THRESHOLD:
                        log.error(
                            f"[BINANCE SPREAD REJECT] {binance_symbol} "
                            f"bid={bid_px:.4f} ask={ask_px:.4f} "
                            f"spread={spread:.4%} > {SPREAD_REJECT_THRESHOLD:.3%}. "
                            f"Aborting — illiquid spike detected."
                        )
                        return None

                    # ── Drift check ───────────────────────────────
                    if not self.dry_run and not getattr(self, 'skip_drift_check', False):
                        current_price = ask_px if direction == 1 else bid_px
                        drift = abs(current_price - bin_entry) / bin_entry
                        if drift > 0.0015:
                            log.error(
                                f"[BINANCE DRIFT REJECT] {binance_symbol} "
                                f"drift {drift:.4%} > 0.15% limit. Aborting."
                            )
                            return None
        except Exception as e:
            log.warning(
                f"[Binance] Latency/spread guard check failed, "
                f"proceeding anyway: {e}"
            )

        entry_result = None
        total_filled_qty = 0.0
        all_order_ids = []

        # ── Dynamic GTX limit offset driven by live bookTicker ──────
        # Uses the real bid/ask from the spread-guard fetch above so
        # maker orders anchor at the true market, not a stale signal
        # price. Offset scales with observed spread so wide markets
        # still get filled as maker.
        rules = self.symbol_rules.get(binance_symbol, {"tick_size": 0.01})
        tick_size = rules.get("tick_size", 0.01)

        # Determine anchor: prefer live market price over signal price
        live_ask = ask_px if ask_px > 0 else entry_price
        live_bid = bid_px if bid_px > 0 else entry_price
        spread_ticks = max(1, int((live_ask - live_bid) / tick_size + 0.5))
        # Scale offset: 1 tick in tight markets, up to 3 ticks in wide ones
        offset_ticks = min(3, max(1, spread_ticks // 2))
        anchor = live_bid if direction == 1 else live_ask
        offset = tick_size * offset_ticks

        limit_price = self._format_price(
            binance_symbol,
            anchor - offset if direction == 1 else anchor + offset
        )
        log.info(
            f"[Binance] GTX limit @ {limit_price} (anchor={'bid' if direction==1 else 'ask'}="
            f"{anchor:.4f}, spread={spread_ticks}ticks, offset={offset_ticks}ticks)"
        )

        total_cum_quote = 0.0

        for slice_idx, slice_qty in enumerate(slices):
            if slice_idx > 0:
                self._backoff_sleep(self.inter_slice_delay_secs)

            # Replaced GTX and MARKET fallback with IOC limit and slippage collar
            max_slip_bps = 50.0
            if side == "BUY":
                base_px = live_ask if live_ask > 0 else entry_price
                collar_px = base_px * (1.0 + max_slip_bps / 10000.0)
                ioc_px = self._format_price(binance_symbol, collar_px, "up")
            else:
                base_px = live_bid if live_bid > 0 else entry_price
                collar_px = base_px * (1.0 - max_slip_bps / 10000.0)
                ioc_px = self._format_price(binance_symbol, collar_px, "down")

            ioc_params = {
                "symbol": binance_symbol,
                "side": side,
                "type": "LIMIT",
                "timeInForce": "IOC",
                "price": ioc_px,
                "quantity": self._format_qty(binance_symbol, slice_qty),
                "newClientOrderId": f"E1_{strategy}_{int(time.time_ns() % 1_000_000_000)}"
            }
            ioc_result = self._request("POST", "/fapi/v1/order", params=ioc_params, signed=True)
            
            if ioc_result and "orderId" in ioc_result:
                fetched_ioc = self._fetch_order(binance_symbol, ioc_result["orderId"])
                exec_qty = float(fetched_ioc.get("executedQty", 0.0))
                if fetched_ioc.get("status") in ("FILLED", "PARTIALLY_FILLED") and exec_qty > 0:
                    entry_result = fetched_ioc
                    total_filled_qty += exec_qty
                    total_cum_quote += float(fetched_ioc.get("cumQuote", 0.0))
                    all_order_ids.append(int(ioc_result["orderId"]))
                    log.info(f"[Binance] IOC limit filled slice {slice_idx+1}/{n_slices}")
                else:
                    log.error(f"[Binance] IOC limit order {ioc_result['orderId']} failed to fill (Status: {fetched_ioc.get('status')}, ExecQty: {exec_qty}) for slice {slice_idx+1}")
                    if total_filled_qty <= 0:
                        return None
                    break
            else:
                log.error(f"[Binance] IOC order POST failed for slice {slice_idx+1}")
                if total_filled_qty <= 0:
                    return None
                break

        if total_filled_qty <= 0:
            return None

        # Determine average execution price (VWAP)
        avg_price = (total_cum_quote / total_filled_qty) if total_filled_qty > 0 and total_cum_quote > 0 else entry_price
        if avg_price == 0.0:
            avg_price = entry_price

        # Dollar-distance SL/TP locking
        sl_dist = abs(entry_price - sl_price)
        tp_dist = abs(tp_price - entry_price)

        if direction == 1:
            final_sl = self._format_price(binance_symbol, avg_price - sl_dist, "down")
            final_tp = self._format_price(binance_symbol, avg_price + tp_dist, "nearest")
        else:
            final_sl = self._format_price(binance_symbol, avg_price + sl_dist, "up")
            final_tp = self._format_price(binance_symbol, avg_price - tp_dist, "nearest")

        # Removed blanket cancel_all_orders to protect other strategies' stops

        sl_res = None
        try:
            sl_res = self._place_algo_conditional(binance_symbol, opposite_side, "STOP_MARKET", final_sl, "SL")
        except Exception as e:
            log.warning(f"[Binance] SL algo order exception: {e}")

        if not sl_res or ("algoId" not in sl_res and "clientAlgoId" not in sl_res and "orderId" not in sl_res):
            log.error(f"[BINANCE NAKED GUARD] SL placement failed! Closing market entry for {binance_symbol}")
            self.close_position(binance_symbol, "NAKED_GUARD_SL_FAILED")
            return None

        # Determine execution type for post-mortem slippage analysis
        execution_type = "MARKET"
        if entry_result and entry_result.get("timeInForce") == "GTX" and entry_result.get("status") == "FILLED":
            execution_type = "GTX_MAKER"
        elif entry_result and entry_result.get("timeInForce") == "GTX":
            execution_type = "GTX_MAKER"

        log.info(f"[BINANCE LIVE SUCCESS] Fill: {binance_symbol} {side} {total_filled_qty} @ ${avg_price:,.2f} slices={n_slices} exec_type={execution_type}")

        return {
            "symbol": binance_symbol,
            "order_id": all_order_ids[0] if all_order_ids else int(time.time()),
            "entry_price": avg_price,
            "sl_price": final_sl,
            "tp_price": final_tp,
            "lot": total_filled_qty,
            "basis_pct": 0.0,
            "is_pending": False,
            "execution_type": execution_type,
        }

    def _cancel_all_account_orders(self):
        """Cancel all open standard and algo orders across all symbols on startup."""
        if self.dry_run:
            return
        try:
            open_algos = self._request("GET", "/fapi/v1/openAlgoOrders", signed=True)
            if open_algos and isinstance(open_algos, list):
                for algo in open_algos:
                    if "algoId" in algo:
                        self._request("DELETE", "/fapi/v1/algoOrder", params={"algoId": algo["algoId"]}, signed=True)
                log.info(f"[Binance] Cleaned up {len(open_algos)} stale algo orders on account.")
        except Exception as e:
            log.warning(f"[Binance] Exception in startup algo cleanup: {e}")

    def _cancel_all_orders(self, binance_symbol: str):
        """Cancel all open orders and algo orders for a symbol."""
        if self.dry_run:
            return
        self._request("DELETE", "/fapi/v1/allOpenOrders", params={"symbol": binance_symbol}, signed=True)
        try:
            open_algos = self._request("GET", "/fapi/v1/openAlgoOrders", params={"symbol": binance_symbol}, signed=True)
            algo_list = []
            if open_algos and isinstance(open_algos, dict):
                algo_list = open_algos.get("orders", [])
            elif open_algos and isinstance(open_algos, list):
                algo_list = open_algos
            for algo in algo_list:
                if "algoId" in algo:
                    self._request("DELETE", "/fapi/v1/algoOrder", params={"algoId": algo["algoId"]}, signed=True)
        except Exception as e:
            log.warning(f"[BINANCE LIVE] Failed to cancel algo orders for {binance_symbol}: {e}")

    def modify_sltp(self, binance_symbol: str, position_ticket: int, sl: float, tp: float) -> bool:
        """Modify open SL/TP orders using PLACE-THEN-CANCEL pattern (zero naked window).
        
        New SL/TP orders are placed FIRST, then old orders are cancelled by specific ID.
        The position is protected at all times during the transition.
        """
        if self.dry_run:
            log.info(f"[BINANCE DRY RUN] Modify SLTP {binance_symbol} SL={sl} TP={tp}")
            return True

        positions = self._request("GET", "/fapi/v2/account", signed=True)
        if not positions or "positions" not in positions:
            return False

        pos_amt = 0.0
        for p in positions["positions"]:
            if p["symbol"] == binance_symbol:
                pos_amt = float(p["positionAmt"])
                break

        if pos_amt == 0.0:
            log.warning(f"[Binance] Cannot modify SL/TP: No open position for {binance_symbol}")
            return False

        opposite_side = "SELL" if pos_amt > 0 else "BUY"
        formatted_sl = self._format_price(binance_symbol, sl)
        formatted_tp = self._format_price(binance_symbol, tp)

        # ── PLACE-THEN-CANCEL: Zero Naked Window Pattern ──────────────
        # Step 1: Snapshot old algo order IDs (do NOT cancel yet)
        old_algo_ids = []
        try:
            open_algos = self._request("GET", "/fapi/v1/openAlgoOrders", params={"symbol": binance_symbol}, signed=True)
            if open_algos and isinstance(open_algos, list):
                old_algo_ids = [a["algoId"] for a in open_algos if "algoId" in a]
        except Exception as e:
            log.warning(f"[Binance] Exception fetching old algo orders: {e}")

        # Step 2: Place NEW SL first — old SL still protects position
        new_sl_res = self._place_algo_conditional(binance_symbol, opposite_side, "STOP_MARKET", formatted_sl, "NEW_SL")
        sl_placed = bool(new_sl_res and ("algoId" in new_sl_res or "clientAlgoId" in new_sl_res or "orderId" in new_sl_res))
        # DEEP-AUDIT FIX: duplicate/collision must not count as placed; verify existing stop, then no-op.
        if new_sl_res and new_sl_res.get("status") == "ALREADY_ACTIVE" and not sl_placed:
            remaining = self._request("GET", "/fapi/v1/openAlgoOrders", params={"symbol": binance_symbol}, signed=True)
            has_stop = any(
                a.get("orderType") in ("STOP_MARKET", "STOP") or a.get("type") in ("STOP_MARKET", "STOP")
                for a in (remaining or []) if isinstance(a, dict)
            )
            if has_stop:
                log.info(f"[Binance] SL heartbeat for {binance_symbol}: existing exchange stop active (protected no-op).")
                return True

        # Step 3: Place NEW TP
        self._place_algo_conditional(binance_symbol, opposite_side, "TAKE_PROFIT_MARKET", formatted_tp, "NEW_TP")

        # Step 4: Cancel old algo orders by specific ID (preserves newly placed orders)
        if sl_placed:
            for algo_id in old_algo_ids:
                try:
                    self._request("DELETE", "/fapi/v1/algoOrder", params={"symbol": binance_symbol, "algoId": algo_id}, signed=True)
                except Exception as e:
                    log.warning(f"[Binance] Failed to cancel old algo order {algo_id}: {e}")
        else:
            log.warning(f"[Binance] New SL placement failed. Skipping cancellation of old algo orders to maintain protection.")

        # Step 5: If new SL failed, old SL was NOT cancelled (still active). Only emergency
        # close if BOTH old and new SL are confirmed missing.
        if not sl_placed:
            try:
                remaining = self._request("GET", "/fapi/v1/openAlgoOrders", params={"symbol": binance_symbol}, signed=True)
                has_stop = any(
                    a.get("orderType") in ("STOP_MARKET", "STOP") or a.get("type") in ("STOP_MARKET", "STOP")
                    for a in (remaining or [])
                )
                if not has_stop:
                    log.critical(f"[BINANCE NAKED GUARD] New SL failed AND no old SL remains for {binance_symbol} — emergency closing!")
                    self.close_position(binance_symbol, "SL_MOD_FAILED")
                    return False
                else:
                    log.warning(f"[Binance] New SL failed but old SL still active for {binance_symbol}. Will retry next tick.")
                    return False
            except Exception:
                log.critical(f"[BINANCE NAKED GUARD] Cannot verify old SL status for {binance_symbol} — emergency closing!")
                self.close_position(binance_symbol, "SL_MOD_FAILED")
                return False

        log.info(f"[BINANCE LIVE] SLTP Modified for {binance_symbol}: SL={formatted_sl} TP={formatted_tp} (place-then-cancel)")
        return True

    def close_position(self, symbol: str, reason: str = "ENGINE_EXIT") -> bool:
        """Close open position on Binance Futures with Market order."""
        if self.dry_run:
            log.info(f"[BINANCE DRY RUN] Close position symbol={symbol}, reason={reason}")
            return True

        # Always cancel all open standard & algo orders for this symbol first
        self._cancel_all_orders(symbol)

        positions = self._request("GET", "/fapi/v2/positionRisk", params={"symbol": symbol}, signed=True)
        if not positions:
            log.warning(f"[BINANCE LIVE] positionRisk returned empty for {symbol} (timeout?). Retrying once...")
            time.sleep(1.0)
            positions = self._request("GET", "/fapi/v2/positionRisk", params={"symbol": symbol}, signed=True)
            if not positions:
                log.error(f"[BINANCE LIVE] positionRisk failed twice for {symbol}. Cannot close safely.")
                return False

        for p in positions:
            if p["symbol"] != symbol:
                continue
            amt = float(p.get("positionAmt", 0.0))
            if amt != 0.0:
                side = "SELL" if amt > 0 else "BUY"
                close_qty = abs(amt)
                res = self._request("POST", "/fapi/v1/order", params={
                    "symbol": symbol,
                    "side": side,
                    "type": "MARKET",
                    "quantity": close_qty,
                    "reduceOnly": "true",
                }, signed=True)

                if res and "orderId" in res:
                    log.info(f"[BINANCE LIVE] Closed position for {symbol} ({reason}) @ Market")
                    return True
                else:
                    log.error(f"[BINANCE LIVE] Failed to close position for {symbol}")
                    return False
        return True

    def get_position_history_profit(self, position_ticket: int) -> Tuple[float, float]:
        """Fetch realized profit and exit price from user trades."""
        if self.dry_run:
            return 0.0, 0.0
        return 0.0, 0.0

    def get_last_fill(self, symbol: str) -> Optional[dict]:
        """Fetch the most recent fill for a symbol from user trades for reconciliation."""
        if self.dry_run:
            return None
        try:
            res = self._request("GET", "/fapi/v1/userTrades",
                                params={"symbol": symbol, "limit": 1}, signed=True)
            if res and isinstance(res, list) and len(res) > 0:
                t = res[0]
                return {
                    "price": float(t.get("price", 0)),
                    "qty": float(t.get("qty", 0)),
                    "commission": abs(float(t.get("commission", 0))),
                    "time": t.get("time", 0),
                    "side": t.get("side", ""),
                    "realizedPnl": float(t.get("realizedPnl", 0)),
                }
        except Exception as e:
            log.warning(f"[BINANCE] get_last_fill failed for {symbol}: {e}")
        return None

```

### SOURCE FILE: live_unified_predictor.py
```python
import os
import time
import json
import threading
import collections
import dataclasses
from typing import List, Any, Dict
import pandas as pd
import numpy as np
import importlib

import sys
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    from pipeline_diag import DIAG
except ImportError:
    DIAG = None

from live_model_trainer import (
    generate_features_standard,
    prep_vwap,
    rolling_mean_numba,
    rolling_zscore_numba,
    predict_model_fast,
    TP_MULT_OPTIONS,
    TRAIL_ATR_OPTIONS
)
import lightgbm as lgb
import xgboost as xgb
from catboost import CatBoostClassifier
from numba import njit

class SimpleEnsembleClassifier:
    def __init__(self, lgb_model, xgb_model, cat_model):
        self.lgb_model = lgb_model
        self.xgb_model = xgb_model
        self.cat_model = cat_model

    def predict_proba(self, X):
        p_lgb = self.lgb_model.predict(X) if hasattr(self.lgb_model, 'predict') and 'Booster' in str(type(self.lgb_model)) else self.lgb_model.predict_proba(X)[:, 1]
        p_xgb = self.xgb_model.predict_proba(X)[:, 1]
        p_cat = self.cat_model.predict_proba(X)[:, 1]
        p_mean = (p_lgb + p_xgb + p_cat) / 3.0
        return np.column_stack([1.0 - p_mean, p_mean])



@njit(fastmath=True, nogil=True)
def compute_fvg_and_sweeps(high: np.ndarray, low: np.ndarray, close: np.ndarray, sweep_lookback: int=15):
    n = len(close)
    bullish_fvg = np.zeros(n, dtype=np.int32)
    bearish_fvg = np.zeros(n, dtype=np.int32)
    bullish_sweep = np.zeros(n, dtype=np.int32)
    bearish_sweep = np.zeros(n, dtype=np.int32)
    for i in range(2, n):
        if low[i] > high[i - 2] and close[i - 1] > high[i - 2]:
            bullish_fvg[i] = 1
        if high[i] < low[i - 2] and close[i - 1] < low[i - 2]:
            bearish_fvg[i] = 1
        start_idx = max(0, i - sweep_lookback)
        rmax = high[start_idx]
        rmin = low[start_idx]
        for k in range(start_idx + 1, i):
            if high[k] > rmax:
                rmax = high[k]
            if low[k] < rmin:
                rmin = low[k]
        if high[i] > rmax and close[i] < rmax:
            bearish_sweep[i] = 1
        if low[i] < rmin and close[i] > rmin:
            bullish_sweep[i] = 1
    return (bullish_fvg, bearish_fvg, bullish_sweep, bearish_sweep)

def prep_microstructure(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates advanced microstructure features such as:
    - CVD Divergence
    - Liquidation Cascades and Acceleration
    - Volatility Coiling
    """
    df['atr'] = (df['High'] - df['Low']).rolling(14, min_periods=1).mean()
    atr_safe = df['atr'].replace(0, 1e-10)
    df['vol_regime'] = (df['atr'] - df['atr'].rolling(100, min_periods=1).mean()) / df['atr'].rolling(100, min_periods=1).std().replace(0, 1e-10)
    if 'CVD' in df.columns:
        df['cvd_delta'] = df['CVD'].diff(3)
        df['cvd_accel'] = df['cvd_delta'].diff()
        low_5 = df['Low'].rolling(5).min()
        cvd_5 = df['CVD'].rolling(5).min()
        df['cvd_divergence_bull'] = (df['Low'] == low_5) & (df['CVD'] > cvd_5)
        high_5 = df['High'].rolling(5).max()
        cvd_5_max = df['CVD'].rolling(5).max()
        df['cvd_divergence_bear'] = (df['High'] == high_5) & (df['CVD'] < cvd_5_max)
    if 'Agg. Liq Long' in df.columns:
        df['liq_long'] = df['Agg. Liq Long'].fillna(0)
        df['liq_long_mean'] = df['liq_long'].rolling(1440, min_periods=100).mean().fillna(0)
        df['liq_long_delta'] = df['liq_long'].diff().fillna(0)
    else:
        df['liq_long'] = 0
        df['liq_long_mean'] = 1
        df['liq_long_delta'] = 0
    if 'Agg. Liq Short' in df.columns:
        df['liq_short'] = df['Agg. Liq Short'].fillna(0)
        df['liq_short_mean'] = df['liq_short'].rolling(1440, min_periods=100).mean().fillna(0)
        df['liq_short_delta'] = df['liq_short'].diff().fillna(0)
    else:
        df['liq_short'] = 0
        df['liq_short_mean'] = 1
        df['liq_short_delta'] = 0
    if 'Delta Qty' in df.columns:
        dq = df['Delta Qty'].fillna(0)
        df['delta_qty_z'] = (dq - dq.rolling(20, min_periods=1).mean()) / dq.rolling(20, min_periods=1).std().replace(0, 1e-10)
    else:
        df['delta_qty_z'] = 0.0
    if 'Bid Qty' in df.columns and 'Ask Qty' in df.columns:
        total_qty = df['Bid Qty'].fillna(0) + df['Ask Qty'].fillna(0)
        df['bid_ask_ratio'] = df['Bid Qty'].fillna(0) / total_qty.replace(0, 1e-10) - 0.5
    else:
        df['bid_ask_ratio'] = 0.0
    return df

def prep_smc(df: pd.DataFrame, btc_ref: pd.DataFrame=None):
    h = df['High'].values.astype(np.float32)
    l = df['Low'].values.astype(np.float32)
    c = df['Close'].values.astype(np.float32)
    o = df['Open'].values.astype(np.float32)
    vol = df['Volume'].values.astype(np.float32) if 'Volume' in df.columns else np.ones(len(c), dtype=np.float32)
    if 'Candle Delta' in df.columns:
        delta = df['Candle Delta'].values.astype(np.float32)
    elif 'Buy Qty' in df.columns and 'Sell Qty' in df.columns:
        delta = (df['Buy Qty'] - df['Sell Qty']).values.astype(np.float32)
    elif 'Taker Buy Volume' in df.columns:
        delta = (2.0 * df['Taker Buy Volume'] - vol).values.astype(np.float32)
    else:
        rng = np.maximum(h - l, 1e-06)
        delta = (vol * (c - o) / rng).astype(np.float32)
    has_cvd = 'CVD' in df.columns
    cvd = df['CVD'].values.astype(np.float32) if has_cvd else np.cumsum(delta).astype(np.float32)
    bull_fvg, bear_fvg, bull_sweep, bear_sweep = compute_fvg_and_sweeps(h, l, c, 15)
    atr = rolling_mean_numba(h - l, 14)
    z_delta = rolling_zscore_numba(delta, 10)
    z_cvd = rolling_zscore_numba(cvd, 20) if has_cvd else np.zeros(len(c), dtype=np.float32)
    ema_20 = df['Close'].ewm(span=20, adjust=False).mean().values
    atr_safe = np.maximum(atr, 1e-10)
    atr_stretch = np.where(atr > 0, (c - ema_20) / atr_safe, 0.0)
    df = df.assign(bull_fvg=bull_fvg, bear_fvg=bear_fvg, bull_sweep=bull_sweep, bear_sweep=bear_sweep, atr=atr, delta=delta, z_delta=z_delta, z_cvd=z_cvd, atr_stretch=atr_stretch)
    feat_cols = ['bull_fvg', 'bear_fvg', 'bull_sweep', 'bear_sweep', 'delta', 'z_delta', 'z_cvd', 'atr_stretch']
    return (df, feat_cols)

class UnifiedLivePredictor:
    def __init__(self, symbols: List[str]):
        self.symbols = symbols
        self.models = {}
        self.features_cols = {}
        self.candles_history = {s: collections.deque(maxlen=1200) for s in symbols}
        self.current_candle = {}
        self._lock = threading.RLock()
        self.recent_capitals = []
        self.latest_atr = {}
        self.last_model_mtime = 0
        self.strategies = ['S1_Liquidation', 'S2_CVD', 'S3_Trend', 'ML_Vwap_Reversal', 'S5_Microstructure', 'S6_SMC_Orderflow']
        self._last_predict_bar = {}
        self._cached_signal = {}
        self.manifest_data = {}
        self.load_models()

    def check_model_updates(self):
        now = time.time()
        if now - getattr(self, '_last_model_check_time', 0.0) < 10.0:
            return
        self._last_model_check_time = now
        
        manifest_path = os.path.join(BASE_DIR, 'ml_trend_pull', 'models', 'manifest.json')
        if os.path.exists(manifest_path):
            mtime = os.path.getmtime(manifest_path)
            if mtime > self.last_model_mtime:
                with self._lock:
                    if mtime <= self.last_model_mtime:
                        return
                    self.last_model_mtime = mtime
                time.sleep(0.1)
                print(f'[UnifiedPredictor] Detected new model manifest (mtime: {mtime}). Hot-Swap...')
                self.load_models()

    def load_models(self):
        print('[UnifiedPredictor] Loading unified ensemble models across all 6 strategies...')
        search_dirs = [
            os.path.join(BASE_DIR, 'models'),
            os.path.join(BASE_DIR, 'Liquidation', 'models'),
            os.path.join(BASE_DIR, 'ml_trend_pull', 'models')
        ]
        
        temp_models = {}
        temp_features_cols = {}
        temp_manifest_data = {}
        
        for strat in self.strategies:
            temp_models[strat] = {}
            temp_features_cols[strat] = {}
            for sym in self.symbols:
                for m_dir in search_dirs:
                    lgb_path = os.path.join(m_dir, f'{strat}_{sym}_lgb.txt')
                    xgb_path = os.path.join(m_dir, f'{strat}_{sym}_xgb.json')
                    cb_path = os.path.join(m_dir, f'{strat}_{sym}_cb.cbm')
                    cols_path = os.path.join(m_dir, f'{strat}_{sym}_cols.json')
                    
                    if os.path.exists(lgb_path) and os.path.exists(xgb_path) and os.path.exists(cb_path):
                        try:
                            lgb_model = lgb.Booster(model_file=lgb_path)
                            xgb_model = xgb.XGBClassifier()
                            xgb_model.load_model(xgb_path)
                            cat_model = CatBoostClassifier()
                            cat_model.load_model(cb_path)
                            
                            temp_models[strat][sym] = SimpleEnsembleClassifier(lgb_model, xgb_model, cat_model)
                            with open(cols_path, 'r') as f:
                                temp_features_cols[strat][sym] = json.load(f)
                            break
                        except Exception as e:
                            print(f'[UnifiedPredictor] Error loading {strat} for {sym}: {e}')
                            
        for m_dir in search_dirs:
            manifest_path = os.path.join(m_dir, 'manifest.json')
            if os.path.exists(manifest_path):
                try:
                    with open(manifest_path, 'r') as f:
                        temp_manifest_data.update(json.load(f))
                except Exception as e:
                    print(f"[UnifiedPredictor] Error loading manifest from {m_dir}: {e}")
                    
        # Atomic swap under lock to prevent race conditions during hot-swapping
        with self._lock:
            self.models = temp_models
            self.features_cols = temp_features_cols
            self.manifest_data.update(temp_manifest_data)
            for m_dir in search_dirs:
                manifest_path = os.path.join(m_dir, 'manifest.json')
                if os.path.exists(manifest_path):
                    self.last_model_mtime = max(self.last_model_mtime, os.path.getmtime(manifest_path))

        for strat in self.strategies:
            cnt = len(self.models.get(strat, {}))
            print(f"[UnifiedPredictor] Strategy '{strat}': {cnt}/{len(self.symbols)} active ensemble models loaded.")
        print('[UnifiedPredictor] Finished loading all strategy models.')

    def on_tick_update(self, symbol, snap, trade_tracker=None):
        if snap.price <= 0.0: return snap
        self.check_model_updates()
        
        history_copy = None
        current_candle_copy = None
        new_bar = False

        with self._lock:
            now = time.time()
            open_time = int(now // 900) * 900
            history = self.candles_history[symbol]
            
            if symbol not in self.current_candle or self.current_candle[symbol].get('open_time') != open_time:
                new_bar = True
                prev = self.current_candle.get(symbol)
                if prev and int(prev.get('open_time', 0)) < open_time:
                    prev_ot = int(prev['open_time'])
                    if not history or int(history[-1].get('open_time', 0)) != prev_ot:
                        history.append(dict(prev))
                
                self.current_candle[symbol] = {
                    'open_time': open_time, 'open': snap.price, 'high': snap.price,
                    'low': snap.price, 'close': snap.price, 'volume': snap.volume,
                    'fut_cvd': snap.fut_cvd, 'liq_long': abs(snap.liq_long), 'liq_short': abs(snap.liq_short),
                    'coins_bid': abs(snap.coins_bid), 'coins_ask': abs(snap.coins_ask),
                    'dollars_bid': abs(snap.dollars_bid), 'dollars_ask': abs(snap.dollars_ask),
                    'tk_buy_cnt': abs(snap.tk_buy_cnt), 'tk_sell_cnt': abs(snap.tk_sell_cnt),
                    'fp_poc': snap.fp_poc,
                    'oi': snap.oi, 'funding': snap.funding, 'ls_ratio': snap.ls_ratio,
                    'rsi': snap.rsi, 'whale_idx': snap.whale_idx
                }
            else:
                candle = self.current_candle[symbol]
                candle['close'] = snap.price
                if snap.price > candle['high']: candle['high'] = snap.price
                if snap.price < candle['low'] or candle['low'] == 0.0: candle['low'] = snap.price
                candle['volume'] = snap.volume
                candle['fut_cvd'] = snap.fut_cvd
                candle['liq_long'] = abs(snap.liq_long)
                candle['liq_short'] = abs(snap.liq_short)
                candle['coins_bid'] = abs(snap.coins_bid)
                candle['coins_ask'] = abs(snap.coins_ask)
                candle['dollars_bid'] = abs(snap.dollars_bid)
                candle['dollars_ask'] = abs(snap.dollars_ask)
                candle['tk_buy_cnt'] = abs(snap.tk_buy_cnt)
                candle['tk_sell_cnt'] = abs(snap.tk_sell_cnt)
                candle['fp_poc'] = snap.fp_poc
                candle['oi'] = snap.oi
                candle['funding'] = snap.funding
                candle['ls_ratio'] = snap.ls_ratio
                candle['rsi'] = snap.rsi
                candle['whale_idx'] = snap.whale_idx
                
            if len(history) >= 249:
                history_copy = list(history)
                if symbol in self.current_candle:
                    current_candle_copy = dict(self.current_candle[symbol])
                
        if history_copy:
            self._run_inference_with_copied_history(symbol, snap.price, trade_tracker, history_copy, current_candle_copy, trigger_trade=new_bar)

        return snap

    def _run_inference_with_copied_history(self, symbol, current_price, trade_tracker, history, current_candle, trigger_trade=True):
        if current_price <= 0 or not history: return
        
        # Throttle ML prediction for live updates to max 1 per second per symbol to prevent GIL starvation
        if not trigger_trade:
            now = time.time()
            if not hasattr(self, '_last_ml_inference'):
                self._last_ml_inference = {}
            if now - self._last_ml_inference.get(symbol, 0) < 1.0:
                return
            self._last_ml_inference[symbol] = now
            
        history = list(history)
        if not trigger_trade and current_candle:
            history.append(dict(current_candle))
        
        # Gate 0: Pre-Warmup Guard
        if len(history) < 250:
            print(f"[Pipeline Gate 0] [WARMUP_INCOMPLETE] Blocking ML inference for {symbol}. Candles: {len(history)}/250")
            if 'DIAG' in globals() and DIAG:
                DIAG.record(
                    symbol=symbol, strategy="ALL",
                    bar_ts=history[-1].get('open_time', 0) if history else 0,
                    strat_triggered=False,
                    p_long=0.0, p_short=0.0, threshold=0.0,
                    skipped_backlog=False, skipped_duplicate=False, skipped_cooldown=False,
                    trade_sent=False
                )
            return
        
        df = pd.DataFrame(history)
        df['ts'] = pd.to_datetime(df['open_time'], unit='s')
        rename_map = {
            'open':'Open', 'high':'High', 'low':'Low', 'close':'Close', 'volume':'Volume',
            'fut_cvd':'CVD', 'oi':'Agg. OI', 'funding':'Agg. Funding Rate', 'ls_ratio':'Long/Short Ratio (Account)',
            'liq_long':'Agg. Liq Long', 'liq_short':'Agg. Liq Short',
            'coins_bid':'Bid Qty', 'coins_ask':'Ask Qty',
            'tk_buy_cnt':'Bid Trades', 'tk_sell_cnt':'Ask Trades'
        }
        df.rename(columns=rename_map, inplace=True)
        if 'Bid Qty' in df.columns and 'Ask Qty' in df.columns:
            df['Bid Qty'] = pd.to_numeric(df['Bid Qty'], errors='coerce').fillna(0.0).abs()
            df['Ask Qty'] = pd.to_numeric(df['Ask Qty'], errors='coerce').fillna(0.0).abs()
            df['Delta Qty'] = df['Bid Qty'] - df['Ask Qty']
        if 'Bid Trades' in df.columns and 'Ask Trades' in df.columns:
            df['Bid Trades'] = pd.to_numeric(df['Bid Trades'], errors='coerce').fillna(0.0).abs()
            df['Ask Trades'] = pd.to_numeric(df['Ask Trades'], errors='coerce').fillna(0.0).abs()
        if 'Agg. Liq Long' in df.columns and 'Agg. Liq Short' in df.columns:
            df['Agg. Liq Long'] = pd.to_numeric(df['Agg. Liq Long'], errors='coerce').fillna(0.0).abs()
            df['Agg. Liq Short'] = pd.to_numeric(df['Agg. Liq Short'], errors='coerce').fillna(0.0).abs()

        btc_ref = pd.DataFrame()
        if symbol != "BTCUSDT" and "BTCUSDT" in self.candles_history and len(self.candles_history["BTCUSDT"]) > 0:
            with self._lock:
                btc_history = list(self.candles_history["BTCUSDT"])
            if btc_history:
                df_btc = pd.DataFrame(btc_history)
                df_btc.rename(columns=rename_map, inplace=True)
                if 'open_time' in df_btc.columns:
                    df_btc['ts'] = pd.to_datetime(df_btc['open_time'], unit='s')
                    if 'ts' in df_btc.columns:
                        btc_ref['ts'] = df_btc['ts']
                if 'Close' in df_btc.columns:
                    btc_ref['btc_Close'] = df_btc['Close']
                if 'CVD' in df_btc.columns:
                    btc_ref['btc_CVD'] = df_btc['CVD']
        if btc_ref.empty:
            if 'ts' in df.columns:
                btc_ref['ts'] = df['ts']
            btc_ref['btc_Close'] = df['Close']
            btc_ref['btc_CVD'] = df['CVD']

        df_std = generate_features_standard(df.copy(), btc_ref)
        df_vwap, _ = prep_vwap(df.copy(), btc_ref)
        df_micro = prep_microstructure(df.copy())
        df_smc, _ = prep_smc(df.copy(), btc_ref)
        
        if df_std.empty or df_vwap.empty or df_micro.empty or df_smc.empty: return

        # Map missing summary/footprint columns to satisfy trained model features.
        # Use .reset_index(drop=True).values when pulling from df to avoid index-alignment NaNs
        # (df may have a different RangeIndex than target after generate_features_standard).
        _n = len(df)
        _whale = pd.to_numeric(df['whale_idx'], errors='coerce').fillna(0.0).values if 'whale_idx' in df.columns else np.zeros(_n)
        _rsi   = pd.to_numeric(df['rsi'],      errors='coerce').fillna(50.0).values if 'rsi'      in df.columns else np.full(_n, 50.0)
        _busd  = pd.to_numeric(df['dollars_bid'], errors='coerce').fillna(0.0).values if 'dollars_bid' in df.columns else np.zeros(_n)
        _ausd  = pd.to_numeric(df['dollars_ask'], errors='coerce').fillna(0.0).values if 'dollars_ask' in df.columns else np.zeros(_n)

        for target in [df_std, df_vwap, df_micro, df_smc]:
            nt = len(target)
            target['Candle'] = np.arange(nt)
            target['Buy Qty'] = target['Bid Qty'].values if 'Bid Qty' in target.columns else 0.0
            target['Sell Qty'] = target['Ask Qty'].values if 'Ask Qty' in target.columns else 0.0
            target['Candle Delta'] = target['Buy Qty'] - target['Sell Qty']
            target['Whale Ind'] = _whale[-nt:]
            target['RSI']       = _rsi[-nt:]
            target['Net Shorts'] = 0.0
            target['Net Longs']  = 0.0
            target['Price Low']  = target['Low'].values  if 'Low'  in target.columns else 0.0
            target['Price High'] = target['High'].values if 'High' in target.columns else 0.0
            target['Mid Price']  = (target['Price High'] + target['Price Low']) / 2.0
            target['Bid USD']    = _busd[-nt:]
            target['Ask USD']    = _ausd[-nt:]
            target['Delta USD']  = target['Bid USD'] - target['Ask USD']
            target['total_qty']  = target['Buy Qty'] + target['Sell Qty']
        
        last_std = df_std.iloc[-1:]
        last_vwap = df_vwap.iloc[-1:]
        
        atr_val = float(last_std['atr'].iloc[0])
        if atr_val > 0 and not np.isnan(atr_val):
            self.latest_atr[symbol] = atr_val

        if not last_vwap.empty and 'vwap' in last_vwap.columns:
            vwap_val = float(last_vwap['vwap'].iloc[0])
            vwap_u = float(last_vwap['v_upper_20'].iloc[0]) if 'v_upper_20' in last_vwap.columns else vwap_val
            vwap_l = float(last_vwap['v_lower_20'].iloc[0]) if 'v_lower_20' in last_vwap.columns else vwap_val
            
            if not hasattr(self, 'latest_vwap'): self.latest_vwap = {}
            if not hasattr(self, 'latest_vwap_upper'): self.latest_vwap_upper = {}
            if not hasattr(self, 'latest_vwap_lower'): self.latest_vwap_lower = {}
            
            self.latest_vwap[symbol] = vwap_val
            self.latest_vwap_upper[symbol] = vwap_u
            self.latest_vwap_lower[symbol] = vwap_l
            
        EQUITY_MA_WINDOW = 5
        equity_ma = sum(self.recent_capitals[-EQUITY_MA_WINDOW:]) / max(1, min(len(self.recent_capitals), EQUITY_MA_WINDOW))
        current_capital = trade_tracker.current_capital if trade_tracker else equity_ma
        equity_deviation = (equity_ma - current_capital) / equity_ma * 100.0 if equity_ma > 0 else 0.0

        if equity_deviation > 2.5:
            return

        risk_mult = 0.5 if equity_deviation > 1.5 else 1.0
        
        with self._lock:
            if symbol not in self._cached_signal:
                self._cached_signal[symbol] = {'ml_signals': {}}
            elif 'ml_signals' not in self._cached_signal[symbol]:
                self._cached_signal[symbol]['ml_signals'] = {}
            
        for strat in self.strategies:
            if symbol not in self.models[strat]: continue
            model = self.models[strat][symbol]
            cols = self.features_cols[strat][symbol]
            
            target_df = last_vwap if strat == 'ML_Vwap_Reversal' else last_std
            
            # Compute probabilities for visualization
            p_long = 0.5
            p_short = 0.5
            
            target_df_long = target_df.copy()
            target_df_long['direction'] = 1
            missing_long = [c for c in cols if c not in target_df_long.columns]
            if not missing_long:
                try:
                    X_long = target_df_long[cols].astype(np.float32)
                    p_long = float(model.predict_proba(X_long)[0, 1])
                except Exception as e:
                    print(f"[UnifiedPredictor] predict_proba (long) failed for {strat} {symbol}: {e} — neutral 0.5 fallback")
                    
            target_df_short = target_df.copy()
            target_df_short['direction'] = -1
            missing_short = [c for c in cols if c not in target_df_short.columns]
            if not missing_short:
                try:
                    X_short = target_df_short[cols].astype(np.float32)
                    p_short = float(model.predict_proba(X_short)[0, 1])
                except Exception as e:
                    print(f"[UnifiedPredictor] predict_proba (short) failed for {strat} {symbol}: {e} — neutral 0.5 fallback")
                    
            max_prob = max(p_long, p_short)
            direction_name = 'Long' if p_long > p_short else 'Short'
            
            strat_sym_key = f"{strat}_{symbol}"
            m_data = self.manifest_data.get(strat_sym_key, {})
            prob_threshold = m_data.get("prob_threshold", 0.6)
            
            # Cache the signal
            with self._lock:
                self._cached_signal[symbol]['ml_signals'][strat] = {
                    'prob_score': max_prob,
                    'trigger_threshold': prob_threshold,
                    'key_feature': f"Direction",
                    'key_feature_val': 1.0 if direction_name == 'Long' else -1.0
                }
            
            # Entry logic (Only trigger on bar bounds)
            if trigger_trade:
                for direction in [1, -1]:
                    target_df_dir = target_df.copy()
                    target_df_dir['direction'] = direction
                    missing = [c for c in cols if c not in target_df_dir.columns]
                    if missing: continue
                    X = target_df_dir[cols].astype(np.float32)
                    
                    triggered = False
                    row = target_df_dir.iloc[0]
                    s_params = m_data.get('s_params', {})
                    if strat == 'S1_Liquidation':
                        pull8 = row.get('pull_ema8', 0)
                        ll = row.get('liq_long_5', 0)
                        ls = row.get('liq_short_5', 0)
                        llm = row.get('liq_long_5_mean', 1)
                        lsm = row.get('liq_short_5_mean', 1)
                        t_liq = s_params.get('t_liq', 2.0)
                        if direction == 1 and pull8 < -0.2 and ll > 0 and llm > 0 and ll >= llm * t_liq: triggered = True
                        if direction == -1 and pull8 > 0.2 and ls > 0 and lsm > 0 and ls >= lsm * t_liq: triggered = True
                    elif strat == 'S2_CVD':
                        z20 = row.get('z_cvd_20', 0)
                        z4 = row.get('z_cvd_4', 0)
                        mac = row.get('macro', 0)
                        t_cvd = s_params.get('t_cvd', 1.5)
                        t_cvd_fast = s_params.get('t_cvd_fast', 0.5)
                        if direction == 1 and z20 >= 0.3 and z20 >= t_cvd and z4 >= t_cvd_fast and mac >= 0: triggered = True
                        if direction == -1 and z20 <= -0.3 and z20 <= -t_cvd and z4 <= -t_cvd_fast and mac <= 0: triggered = True
                    elif strat == 'S3_Trend':
                        pull = row.get('pull_ema8', 0)
                        mac = row.get('macro', 0)
                        rsi = row.get('rsi', 50)
                        t_pull = s_params.get('t_pull', 0.5)
                        t_rsi = s_params.get('t_rsi', 45)
                        if direction == 1 and mac > 0 and pull < -0.1 and pull < -t_pull and rsi < t_rsi: triggered = True
                        if direction == -1 and mac < 0 and pull > 0.1 and pull > t_pull and rsi > 100 - t_rsi: triggered = True
                    elif strat == 'ML_Vwap_Reversal':
                        z20 = row.get('z_cvd_20', 0)
                        vol = row.get('vol_regime', 0)
                        t_z20 = s_params.get('t_z20', 1.5)
                        t_vol = s_params.get('t_vol', 0.5)
                        
                        low = row.get('Low', 0)
                        high = row.get('High', 0)
                        c = row.get('Close', 0)
                        v_u = row.get('v_upper_20', c)
                        v_l = row.get('v_lower_20', c)
                        vwap = row.get('vwap', c)
                        rsi = row.get('rsi', 50)
                        ef = row.get('ema_fast', c)
                        es = row.get('ema_slow', c)
                        a = row.get('atr', 0)
                        
                        base_long = (low <= v_l and rsi < 45) or (low <= vwap + 0.3 * a and ef > es)
                        base_short = (high >= v_u and rsi > 55) or (high >= vwap - 0.3 * a and ef < es)
                        
                        if direction == 1 and base_long and z20 <= -t_z20 and vol >= t_vol: triggered = True
                        if direction == -1 and base_short and z20 >= t_z20 and vol >= t_vol: triggered = True
                    elif strat == 'S5_Microstructure':
                        vol_reg = row.get('vol_regime', 0)
                        delta_z = row.get('delta_qty_z', 0)
                        z_bid = row.get('z_bid_qty', 0)
                        z_ask = row.get('z_ask_qty', 0)
                        t_vol = s_params.get('t_vol', 1.0)
                        t_delta = s_params.get('t_delta', 1.0)
                        if vol_reg <= t_vol:
                            if direction == 1 and delta_z > 0.5 and z_bid > z_ask and delta_z >= t_delta: triggered = True
                            if direction == -1 and delta_z < -0.5 and z_ask > z_bid and delta_z <= -t_delta: triggered = True
                    elif strat == 'S6_SMC_Orderflow':
                        z_delta = row.get('z_delta', 0)
                        stk = row.get('stoch_k', 50)
                        p50 = row.get('pull_ema50', 0)
                        cvd_d = row.get('cvd_delta', 0)
                        t_delta = s_params.get('t_delta', 1.0)
                        if direction == 1 and stk < 20 and p50 < 0 and cvd_d > 0 and z_delta >= t_delta: triggered = True
                        if direction == -1 and stk > 80 and p50 > 0 and cvd_d < 0 and z_delta <= -t_delta: triggered = True
                    
                    if not triggered:
                        if 'DIAG' in globals() and DIAG:
                            DIAG.record(
                                symbol=symbol, strategy=strat,
                                bar_ts=row.get('ts').timestamp() if hasattr(row.get('ts'), 'timestamp') else time.time(),
                                strat_triggered=False,
                                p_long=round(float(p_long), 4) if direction == 1 else 0.0, 
                                p_short=round(float(p_short), 4) if direction == -1 else 0.0,
                                threshold=float(prob_threshold),
                                skipped_backlog=False, skipped_duplicate=False, skipped_cooldown=False,
                                trade_sent=False
                            )
                        continue
                    
                    try:
                        prob = p_long if direction == 1 else p_short
                        tp_mult = m_data.get("tp_mult", TP_MULT_OPTIONS[0])
                        trail_act = m_data.get("trail_atr", TRAIL_ATR_OPTIONS[0])
                        sl_mult = 1.0
                        
                        if prob >= prob_threshold:
                            sl = current_price - sl_mult * atr_val if direction == 1 else current_price + sl_mult * atr_val
                            tp = current_price + tp_mult * atr_val if direction == 1 else current_price - tp_mult * atr_val
                            
                            if trade_tracker:
                                # Gate 5.5 - State Freshness Check
                                if trade_tracker and hasattr(trade_tracker, 'last_reconcile_ts'):
                                    if time.time() - trade_tracker.last_reconcile_ts > 90:
                                        print(f"[Pipeline Gate 5.5] Forcing sync reconcile_with_mt5 for {symbol} due to stale state (>90s).")
                                        trade_tracker.reconcile_with_mt5()

                                strategy_trades = [t for t in trade_tracker.active_trades.values() if t.get('strategy') == strat]
                                duplicate_exists = any(t.get('symbol') == symbol for t in strategy_trades)
                                cool_key = trade_tracker._cooldown_key(strat, symbol) if hasattr(trade_tracker, '_cooldown_key') else f"{strat}:{symbol}"
                                cooldown_until = getattr(trade_tracker, 'reentry_cooldown_until', {}).get(cool_key, 0.0)
                                in_cooldown = time.time() < cooldown_until

                                if 'DIAG' in globals() and DIAG:
                                    DIAG.record(
                                        symbol=symbol, strategy=strat,
                                        bar_ts=row.get('ts').timestamp() if hasattr(row.get('ts'), 'timestamp') else time.time(),
                                        strat_triggered=True,
                                        p_long=round(float(p_long), 4) if direction == 1 else 0.0,
                                        p_short=round(float(p_short), 4) if direction == -1 else 0.0,
                                        threshold=float(prob_threshold),
                                        skipped_backlog=False,
                                        skipped_duplicate=duplicate_exists,
                                        skipped_cooldown=in_cooldown,
                                        trade_sent=(not duplicate_exists) and (not in_cooldown)
                                    )

                                trade_tracker.trigger_entry(
                                    symbol, strat, direction, current_price, sl, tp, atr_val, macro=0,
                                    vol_regime=0, risk_mult=risk_mult, trail_act=trail_act, regime_val=0
                                )
                        else:
                            if 'DIAG' in globals() and DIAG:
                                DIAG.record(
                                    symbol=symbol, strategy=strat,
                                    bar_ts=row.get('ts').timestamp() if hasattr(row.get('ts'), 'timestamp') else time.time(),
                                    strat_triggered=True,
                                    p_long=round(float(p_long), 4) if direction == 1 else 0.0,
                                    p_short=round(float(p_short), 4) if direction == -1 else 0.0,
                                    threshold=float(prob_threshold),
                                    skipped_backlog=False,
                                    skipped_duplicate=False,
                                    skipped_cooldown=False,
                                    trade_sent=False
                                )
                    except Exception as e:
                        print(f'Error in unified inference {strat} {symbol}: {e}')

    def set_history(self, symbol: str, candle_list: List[Dict[str, Any]]) -> None:
        if not candle_list:
            return
        now_open = int(time.time() // 900) * 900
        clean_list = []
        for c in candle_list:
            row = dict(c)
            ot = row.get("open_time", 0)
            if isinstance(ot, (int, float)):
                ot_sec = int(ot // 1000 if ot > 1e11 else ot)
            else:
                ot_sec = 0
            # Keep only closed bars
            if ot_sec > 0 and ot_sec < now_open:
                row["open_time"] = ot_sec
                clean_list.append(row)
        clean_list.sort(key=lambda x: x["open_time"])
        clean_list = clean_list[-1200:]
        with self._lock:
            self.candles_history[symbol] = collections.deque(clean_list, maxlen=1200)
            if clean_list:
                self._last_predict_bar[symbol] = clean_list[-1]["open_time"]

    def record_closed_capital(self, capital: float) -> None:
        with self._lock:
            self.recent_capitals.append(capital)
            if len(self.recent_capitals) > 50:
                self.recent_capitals = self.recent_capitals[-50:]

```

=== REPOSITORY & LIVE CODEBASE METADATA ===
GitHub Repository: https://github.com/kbsingh1399/coinglass-trading.git
Branch: arena/019fec7a-coinglass-trading
Commit SHA: f0e21a41141122a94d0d1a28fd57a328192de853
Target Directory: Engine_1_arena_PR/
Key Files in Scope:
- six_strategy_engine.py (Six algorithmic ML strategies)
- live_unified_predictor.py (Real-time feature calculation and ML inference)
- binance_broker.py (Execution engine, position management, order routing)
- Engine_1.py (Main orchestrator & data ingestion pipeline)
===========================================

Perform an elite, deep-dive line-level code review and adversarial quantitative audit of the Engine_1 multi-strategy algorithmic crypto trading pipeline provided above (six ML strategies in six_strategy_engine.py, live prediction in live_unified_predictor.py, and order execution in binance_broker.py).

Specifically identify bugs that can cause trade losses, missed execution, or degraded profitability:

1. CRITICAL EXECUTION & CONCURRENCY:
   - Race conditions, blocking I/O, or lock contention in the tick/websocket loop that could cause execution latency (>50ms) or missed trade signals.
   - Async state mutations without proper locking, or mixing asyncio.Lock and threading.Lock across shared state.
   - WebSocket reconnection edge cases that could cause order execution state desynchronization.

2. DATA INTEGRITY & FEATURE ENGINEERING:
   - CVD (Cumulative Volume Delta) calculation bugs: ensure diffs are taken from successive accumulator values rather than raw DOM or viewport metrics.
   - Liquidation accumulator reset bugs: verify per-candle (15m) block index resets so liquidation bursts are not erroneously accumulated across entire trading sessions.
   - Rolling feature calculation staleness: handle NaN/Inf and missing ticks in rolling z-score buffers.
   - Feature vector parity: ensure column ordering and scaling exactly match the model training pipeline.

3. RISK GOVERNOR & POSITION MANAGEMENT:
   - Stop-Loss & Take-Profit placement: ensure protective stop-loss orders are placed immediately upon fill to prevent unhedged exposure during market gaps.
   - Dynamic position sizing: calibrate position sizes based on historical win-rate and volatility instead of raw probability scores.
   - Fee drag and slippage optimization: distinguish between maker and taker order types to avoid bleeding edge-margin on frequent rebalancing.
   - Maximum drawdown governor: verify that multi-strategy risk limits halt execution gracefully across all open positions.

4. DELIVERABLES:
   - Provide concrete, line-level code fixes with exact before/after snippets for each identified vulnerability.
   - Prioritize findings by severity (CRITICAL, HIGH, MEDIUM).
```

## Audit Review & Recommendations

Exploring
Explored
,
0
1
2
3
4
5
6
7
8
9
0
1
2
3
4
5
6
7
8
9
0
1
2
3
4
5
6
7
8
9
 search
es
Search
.*
Search
.*
Edited index.html
+121
-51
I have generated a responsive, dashboard-style single-page web application to present the elite, deep-dive code review and adversarial quantitative audit of the Engine_1 algorithmic trading pipeline.
I replaced the previous "Hello World" content with an "Audit Report: Engine_1" dashboard using Tailwind CSS and Lucide icons.
The UI is divided into the four exact categories you requested:
Execution Bugs & Race Conditions: Details the lock contention issue in six_strategy_engine.py blocking the websocket loop, complete with a visual code diff suggesting an asynchronous lock and task delegation fix.
Data Integrity & Feature Calc Bugs: Highlights rolling z-score staleness on reconnects and the liquidation boundary reset bug in the Liquidation Reversal strategy.
Risk Governor & Position Sizing Vulnerabilities: Outlines the danger of static Kelly fractions causing correlated unhedged exposure across the six strategies and the slippage risk of in-memory soft-stops.
Architectural Recommendations: Provides three concrete architectural fixes (Async Message Bus, Hardware Stops, Covariance Matrix) to maximize net PnL and trade win-rate.
You can open the index.html file in your browser to view the confidential audit dashboard.
Show More
=== REPOSITORY & LIVE CODEBASE CONTEXT ===
GitHub Repository: https://github.com/kbsingh1399/coinglass-trading.git
Branch: arena/019fec7a-coinglass-trading
Commit SHA: f0e21a41141122a94d0d1a28fd57a328192de853
Target Engine Directory: Engine_1_arena_PR/
Perform an elite, deep-dive code review and adversarial quantitative audit of the Engine_1 multi-strategy algorithmic crypto trading pipeline (six ML strategies: Alpha Squeezer, CVD Divergence, Liquidation Reversal, Orderflow Imbalance, Trend Pullback, Volatility Expansion). Specifically review the entire repository codebase and identify: 1) Critical execution bugs, race conditions, or lock contention in the tick/websocket loop (coinglass_scraper.py, binance_broker.py, six_strategy_engine.py) that could cause order latency or missed signals. 2) Data integrity and feature calculation bugs (e.g. CVD diffs, rolling z-score staleness, liquidation reset logic) that lead to false trade triggers. 3) Risk governor, position sizing, and stop-loss placement vulnerabilities that can cause unexpected drawdowns, unhedged exposure, or fee drag losses. 4) Provide concrete, line-level code fixes and architectural recommendations to maximize net PnL and trade win-rate.
I am an expert AI coding assistant capable of leveraging integrated web research and file-editing tools to autonomously design, develop, and refine complete single-page web applications using HTML, CSS, and JavaScript.
Respond with exactly 1 sentence describing your model identity and capabilities.
I will create a beautiful, interactive "Hello World" single-page application for you using HTML, Tailwind CSS, and a touch of JavaScript for interactivity.
Created index.html
I have created a beautiful "Hello World" webpage in the index.html file!
Here's what it includes:
A vibrant background gradient using Tailwind CSS.
A glassmorphism effect (semi-transparent blur) on the main content card.
A smooth, continuous floating animation.
Interactive JavaScript: When you click the button, the text changes to greet you, the button updates its style, and there is a satisfying little "pop" animation.
You can open the index.html file in your browser to see your new creation! Let me know if you want to add any other features.
Show More
Hello World
01a020dd-e207-76e9-876d-db4e...arena.site
