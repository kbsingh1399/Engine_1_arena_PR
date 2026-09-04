"""
================================================================================
S1 LIQUIDATION-CASCADE ABSORPTION STRATEGY — ENGINE 2 PRODUCTION MODULE
================================================================================
Institutional microstructure strategy for 18 Binance USDT-M perpetuals on 15m bars.

Two sleeves under ONE causal configuration (no window-keyed logic of any kind):

  SLEEVE A — "S1 Cascade Absorption" (repository-faithful)
    Long confluence (AGENTS.md / ACTIVE_CONTEXT.md invariant):
      long_liq_zs > 1.8  AND  zc_div > 0.8  AND  dSpot > 0  AND  dFutures < 0
      AND RSI14 < 40  AND  VWAP_Z < -0.5  AND  dOI(6) < 0   (OKF decoupling)
    Short mirror on short-liquidation cascades.

  SLEEVE B — "Deep-Discount Cascade Composite" (best honest edge found)
    Deep discount to EMA200 (close < 0.85 x EMA200) OR OI-flush cascade
    (dOI(6) < -3% AND ret(6h) < -4%, Giagkiozis & Sa'id 2024) WITH a
    stabilization/reclaim bar. This is the only family with positive net
    expectancy under full mandate frictions (see STRATEGY_SPEC.md evidence).

EXECUTION INTEGRITY CONTRACT (FABLE5 Part 14):
  * Signals computed at bar t close -> fill at bar t+1 open (+10 bps slip + 8 bps fee).
  * Favorable stop ratchets triggered on bar j arm strictly on bar j+1.
  * Bar-j exit tests use the stop armed at j-1; stop fills at min(open, stop) with
    15 bps slippage + 8 bps fee (gap-through-stop modeled).
  * Profit objective: minimum +5.0R; at +5.0R a trailing stop activates
    (trail = peak - 1.0R, locking >= +4.0R). No profit cap above 5R.
  * Mark-to-market equity and drawdown tracked bar-by-bar across the whole window.
  * Risk governor: $5,000 capital, $25 base risk, $50 house-money risk (net profit
    > $50), $15 defense risk (DD > 2.5%), 4.5% hard drawdown halt on NEW entries,
    max 2 concurrent positions, notional <= 4x equity.
  * Windows start flat (72h causal purge enforced by construction) and all
    positions are force-closed at window end with full frictions.

Author: Engine 2 quantitative desk (Arena session 2026-09-05).
================================================================================
"""

from __future__ import annotations

import os
import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# Universe & data
# --------------------------------------------------------------------------- #
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "binance_backtesting_data")

# Canonical 18 assets present in the repository pipeline
# (Engine_2/run_historical_pipeline.py::ENGINE_1_CRYPTO_SYMBOLS).
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "LINKUSDT", "SUIUSDT", "NEARUSDT", "APTUSDT",
    "DOTUSDT", "LTCUSDT", "BCHUSDT", "TRXUSDT", "OPUSDT", "ARBUSDT",
]

RAW_COLS = [
    "open_time_ms", "open", "high", "low", "close", "volume_quote",
    "rsi_14", "atr_14", "ema_200",
    "future_cvd_15m", "spot_cvd_15m",
    "open_interest_usd", "long_liq_usd", "short_liq_usd",
    "funding_rate_pct", "basis_usd",
]

# --------------------------------------------------------------------------- #
# Single invariant configuration (identical for all 20 OOS windows)
# --------------------------------------------------------------------------- #
CFG = {
    # -- Sleeve A thresholds (repository invariants) --
    "A_LIQ_Z": 1.8,
    "A_ZC_DIV": 0.8,
    "A_RSI_MAX_LONG": 40.0,
    "A_RSI_MIN_SHORT": 60.0,
    "A_VWAP_Z_LONG": -0.5,
    "A_VWAP_Z_SHORT": 0.5,
    "A_LIQ_FRESH_BARS": 3,
    # -- Sleeve B thresholds (calibrated on pre-2021 in-sample data only) --
    "B_DISCOUNT": 0.85,        # close < 0.85 * EMA200
    "B_FLUSH_OI": -0.03,       # 6-bar OI change < -3%
    "B_FLUSH_RET": -0.04,      # 6-bar return < -4%
    "B_STAB_BARS": 8,          # discount/flush must have printed within 8 bars
    # -- shared filters --
    "COOLDOWN": 16,            # min bars between entries on one symbol
    # -- trade geometry (wide, friction-aware stops) --
    "S_ATR": 3.0,              # stop distance = 3 x ATR14 at signal bar
    "MAX_HOLD_BARS": 400,      # vertical barrier (~100 hours)
    # -- exit ladder: ratchets armed next bar; 5R trail mandate on top --
    "RUNGS": [(0.8, 0.15), (1.5, 0.80), (2.5, 1.50), (3.5, 2.50), (4.5, 3.50)],
    "TRAIL_TRIGGER_R": 5.0,    # minimum profit objective (mandate)
    "TRAIL_GIVEBACK_R": 1.0,   # trail = peak - 1.0R (locks >= 4.0R)
    "PROG_BARS": 24,           # stale-exit horizon
    "MIN_PROG_R": 0.25,        # required MFE by PROG_BARS else market exit
    # -- risk governor (repo invariants) --
    "CAPITAL": 5000.0,
    "BASE_RISK": 25.0,
    "HOUSE_RISK": 50.0,
    "HOUSE_PROFIT": 50.0,
    "DEFENSE_RISK": 15.0,
    "DEFENSE_DD": 0.025,
    "HARD_DD": 0.045,
    "MAX_CONCURRENT": 2,
    "MAX_NOTIONAL_LEV": 4.0,
    # -- frictions (mandate) --
    "FEE_BPS": 8.0,
    "SLIP_ENTRY_BPS": 10.0,
    "SLIP_STOP_BPS": 15.0,
    # -- Sleeve B-META (Lopez de Prado meta-labeling, causal walk-forward) --
    "META_THRESHOLD": 0.60,      # fixed for all windows (sensitivity reported)
    "META_LGB_PARAMS": dict(n_estimators=250, learning_rate=0.03, num_leaves=15,
                            min_child_samples=40, subsample=0.8, subsample_freq=1,
                            colsample_bytree=0.8, random_state=7, n_jobs=1,
                            verbose=-1),
}

# Meta-label feature vector (causal state at the signal bar).
META_FEATS = [
    "liq_l_zs", "liq_s_zs", "zc_div", "vwap_z", "rsi", "oi_d6", "ret6", "ret24",
    "atr_pct", "vol_z", "funding", "basis_pct", "ema200_dist", "z1",
    "btc_z1", "btc_ret24", "btc_atr_pct", "hour", "dow", "dir",
]


# --------------------------------------------------------------------------- #
# Causal feature engineering (trailing windows only — zero lookahead)
# --------------------------------------------------------------------------- #
def _roll_z(x: pd.Series, n: int) -> pd.Series:
    m = x.rolling(n, min_periods=n).mean()
    s = x.rolling(n, min_periods=n).std(ddof=0)
    return (x - m) / s.replace(0.0, np.nan)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """All features use trailing windows; nothing references future bars."""
    out = pd.DataFrame(index=df.index)
    out["ts"] = df["open_time_ms"].astype(np.int64)
    for c in ("open", "high", "low", "close"):
        out[c] = df[c].astype(np.float64)
    out["atr"] = df["atr_14"].astype(np.float64)
    out["rsi"] = df["rsi_14"].astype(np.float64)
    out["ema200"] = df["ema_200"].astype(np.float64)

    liq_l = (-df["long_liq_usd"]).clip(lower=0.0)
    liq_s = df["short_liq_usd"].clip(lower=0.0)
    out["liq_l_zs"] = _roll_z(liq_l, 20)
    out["liq_s_zs"] = _roll_z(liq_s, 20)

    z_spot = _roll_z(df["spot_cvd_15m"], 20)
    z_fut = _roll_z(df["future_cvd_15m"], 20)
    out["zc_div"] = z_spot - z_fut
    out["d_spot"] = df["spot_cvd_15m"]
    out["d_fut"] = df["future_cvd_15m"]

    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    v = df["volume_quote"]
    vwap = (tp * v).rolling(96, min_periods=96).sum() / v.rolling(96, min_periods=96).sum().replace(0.0, np.nan)
    dev = df["close"] - vwap
    out["vwap_z"] = dev / dev.rolling(20, min_periods=20).std(ddof=0).replace(0.0, np.nan)

    oi = df["open_interest_usd"].replace(0.0, np.nan)
    out["oi_d6"] = (oi / oi.shift(6) - 1.0).clip(-0.5, 0.5).fillna(0.0)
    out["ret6"] = df["close"] / df["close"].shift(6) - 1.0

    # meta-label context features (all causal)
    out["ret24"] = df["close"] / df["close"].shift(96) - 1.0
    out["atr_pct"] = out["atr"] / out["close"] * 100.0
    out["vol_z"] = _roll_z(df["volume_quote"], 96)
    out["funding"] = df["funding_rate_pct"]
    out["basis_pct"] = (df["basis_usd"] / df["close"] * 100.0).clip(-3, 3)
    out["ema200_dist"] = out["close"] / out["ema200"] - 1.0
    ret1 = df["close"] / df["close"].shift(1) - 1.0
    out["z1"] = ((ret1 - ret1.rolling(96, min_periods=96).mean())
                 / ret1.rolling(96, min_periods=96).std(ddof=0))
    dt = pd.to_datetime(out["ts"], unit="ms")
    out["hour"] = dt.dt.hour.astype(float)
    out["dow"] = dt.dt.dayofweek.astype(float)
    return out


def load_universe(data_dir: str = DATA_DIR) -> dict:
    feats = {}
    for s in SYMBOLS:
        path = os.path.join(data_dir, f"{s}_15m_master_2020_2026.parquet")
        df = pd.read_parquet(path, columns=RAW_COLS).sort_values("open_time_ms")
        feats[s] = build_features(df.reset_index(drop=True))
    return feats


# --------------------------------------------------------------------------- #
# Signal generation — one causal rule-set for every window
# --------------------------------------------------------------------------- #
def signals(f: pd.DataFrame, c: dict, sleeve: str):
    """Return (direction array, score array) for the requested sleeve."""
    n = len(f)
    dirn = np.zeros(n, dtype=np.int8)
    score = np.full(n, -np.inf)

    if sleeve == "A":
        fresh_l = f.liq_l_zs.rolling(c["A_LIQ_FRESH_BARS"], min_periods=1).max() > c["A_LIQ_Z"]
        fresh_s = f.liq_s_zs.rolling(c["A_LIQ_FRESH_BARS"], min_periods=1).max() > c["A_LIQ_Z"]
        long_m = (fresh_l & (f.zc_div > c["A_ZC_DIV"]) & (f.d_spot > 0) & (f.d_fut < 0)
                  & (f.rsi < c["A_RSI_MAX_LONG"]) & (f.vwap_z < c["A_VWAP_Z_LONG"])
                  & (f.oi_d6 < 0))
        short_m = (fresh_s & (f.zc_div < -c["A_ZC_DIV"]) & (f.d_spot < 0) & (f.d_fut > 0)
                   & (f.rsi > c["A_RSI_MIN_SHORT"]) & (f.vwap_z > c["A_VWAP_Z_SHORT"])
                   & (f.oi_d6 > 0))
    elif sleeve == "B":
        discount = f.close < f.ema200 * c["B_DISCOUNT"]
        flush_l = (f.oi_d6 < c["B_FLUSH_OI"]) & (f.ret6 < c["B_FLUSH_RET"])
        flush_s = (f.oi_d6 > -c["B_FLUSH_OI"]) & (f.ret6 > -c["B_FLUSH_RET"])
        rec_l = (discount | flush_l).rolling(c["B_STAB_BARS"], min_periods=1).max().shift(1).fillna(0).astype(bool)
        rec_s = ((f.close > f.ema200 * (2 - c["B_DISCOUNT"])) | flush_s).rolling(
            c["B_STAB_BARS"], min_periods=1).max().shift(1).fillna(0).astype(bool)
        long_m = rec_l & (f.close > f.open) & (f.close > f.close.shift(1))
        short_m = rec_s & (f.close < f.open) & (f.close < f.close.shift(1))
    else:
        raise ValueError(f"unknown sleeve {sleeve}")

    long_m = long_m.fillna(False)
    short_m = short_m.fillna(False) & ~long_m

    sc = (f.liq_l_zs.fillna(0).abs() + f.liq_s_zs.fillna(0).abs()
          + f.zc_div.fillna(0).abs() + (f.ema200 / f.close - 1).fillna(0).abs())

    def dedup(mask):
        idx = np.where(mask.values)[0]
        keep, last = [], -10 ** 9
        for i in idx:
            if i - last >= c["COOLDOWN"]:
                keep.append(i)
                last = i
        out = np.zeros(n, dtype=bool)
        out[keep] = True
        return out

    L = dedup(long_m)
    S_ = dedup(short_m) & ~L
    dirn[L] = 1
    dirn[S_] = -1
    score = np.where(dirn != 0, sc.values, -np.inf)
    return dirn, score


# --------------------------------------------------------------------------- #
# Exact single-trade engine (used for meta-label generation; mirrors the
# portfolio simulator's bar-sequencing: j+1 ratchets, gap-through stops)
# --------------------------------------------------------------------------- #
def _sim_trade(f: pd.DataFrame, i: int, dr: int, c: dict):
    """Simulate one trade from signal bar i (entry next open). Returns R or None."""
    hi = f.high.values
    lo = f.low.values
    op = f.open.values
    cl = f.close.values
    atr = f.atr.values[i]
    n = len(f)
    j0 = i + 1
    if j0 >= n or not np.isfinite(atr) or atr <= 0:
        return None
    fee = c["FEE_BPS"] / 1e4
    se = c["SLIP_ENTRY_BPS"] / 1e4
    sx = c["SLIP_STOP_BPS"] / 1e4
    entry = op[j0] * (1 + dr * (se + fee))
    R = c["S_ATR"] * atr
    if R <= 0:
        return None
    stop = entry - dr * R
    fr_r = (2 * fee + se + sx) * op[j0] / R
    mfe = 0.0
    armed = -1.0
    pending_exit = False
    age = 0
    end = min(n, j0 + c["MAX_HOLD_BARS"])
    for j in range(j0, end):
        o, h, l = op[j], hi[j], lo[j]
        if pending_exit:
            return ((o * (1 - dr * (sx + fee)) - entry) * dr) / R - fr_r
        hit = (l <= stop) if dr > 0 else (h >= stop)
        if hit:
            fill = min(o, stop) if dr > 0 else max(o, stop)
            return ((fill * (1 - dr * (sx + fee)) - entry) * dr) / R - fr_r
        mfe = max(mfe, ((h - entry) * dr) / R)
        new = armed
        for trig, lock in c["RUNGS"]:
            if mfe >= trig and lock > new:
                new = lock
        if mfe >= c["TRAIL_TRIGGER_R"]:
            new = max(new, mfe - c["TRAIL_GIVEBACK_R"])
        if new != armed:
            armed = new
            cand = entry + dr * armed * R
            stop = max(stop, cand) if dr > 0 else min(stop, cand)
        age += 1
        if age >= c["PROG_BARS"] and mfe < c["MIN_PROG_R"]:
            pending_exit = True
    return ((cl[end - 1] * (1 - dr * (sx + fee)) - entry) * dr) / R - fr_r


def build_meta_events(universe: dict, sleeve: str = "B", c: dict = CFG) -> pd.DataFrame:
    """Label every sleeve candidate event with its exact triple-barrier R outcome."""
    btc = universe["BTCUSDT"]
    btc_map = {int(t): (z, r, a) for t, z, r, a in zip(
        btc.ts.values, btc.z1.fillna(0).values, btc.ret24.fillna(0).values,
        btc.atr_pct.fillna(0).values)}
    rows = []
    per_bar = [k for k in META_FEATS if k not in ("dir", "btc_z1", "btc_ret24", "btc_atr_pct")]
    for s, f in universe.items():
        dirn, _ = signals(f, c, sleeve)
        for i in np.where(dirn != 0)[0]:
            r = _sim_trade(f, i, int(dirn[i]), c)
            if r is None or not np.isfinite(r):
                continue
            row = {k: float(f[k].values[i]) for k in per_bar}
            bz, br, ba = btc_map.get(int(f.ts.values[i]), (0.0, 0.0, 0.0))
            row["btc_z1"], row["btc_ret24"], row["btc_atr_pct"] = bz, br, ba
            row["dir"] = int(dirn[i])
            row["y"] = 1 if r > 0 else 0
            row["R"] = float(r)
            row["ts"] = int(f.ts.values[i])
            row["sym"] = s
            rows.append(row)
    return pd.DataFrame(rows)


def train_meta_model(events: pd.DataFrame, t_purge_ms: int, c: dict = CFG):
    """Train the meta-labeler ONLY on events strictly before the purge boundary."""
    import lightgbm as lgb
    tr = events[events.ts < t_purge_ms]
    if len(tr) < 100:
        return None
    model = lgb.LGBMClassifier(**c["META_LGB_PARAMS"])
    model.fit(tr[META_FEATS].fillna(0).values, tr.y.values)
    return model


def meta_mask_for_window(universe: dict, model, t0_ms: int, t1_ms: int,
                         sleeve: str = "B", c: dict = CFG):
    """Predict p* for every candidate signal in the window; keep p* >= threshold.
    Returns {symbol: boolean mask aligned to the symbol's window slice} (or None
    for symbols with no model decision)."""
    if model is None:
        return None
    btc = universe["BTCUSDT"]
    btc_map = {int(t): (z, r, a) for t, z, r, a in zip(
        btc.ts.values, btc.z1.fillna(0).values, btc.ret24.fillna(0).values,
        btc.atr_pct.fillna(0).values)}
    masks = {}
    for s, f in universe.items():
        m = (f.ts.values >= t0_ms) & (f.ts.values < t1_ms)
        if not m.any():
            continue
        sl = f.loc[m].reset_index(drop=True)
        dirn, _ = signals(sl, c, sleeve)
        keep = np.zeros(len(sl), dtype=bool)
        p_arr = np.full(len(sl), -np.inf)
        idx = np.where(dirn != 0)[0]
        per_bar = [k for k in META_FEATS if k not in ("dir", "btc_z1", "btc_ret24", "btc_atr_pct")]
        if len(idx):
            X = []
            for i in idx:
                row = {k: float(sl[k].values[i]) for k in per_bar}
                bz, br, ba = btc_map.get(int(sl.ts.values[i]), (0.0, 0.0, 0.0))
                row["btc_z1"], row["btc_ret24"], row["btc_atr_pct"] = bz, br, ba
                row["dir"] = int(dirn[i])
                X.append([row[k] for k in META_FEATS])
            p = model.predict_proba(np.array(X, dtype=float))[:, 1]
            keep[idx[p >= c["META_THRESHOLD"]]] = True
            p_arr[idx] = p
        masks[s] = (keep, p_arr)
    return masks


# --------------------------------------------------------------------------- #
# Event-driven portfolio simulator (per OOS window)
# --------------------------------------------------------------------------- #
def simulate_window(universe: dict, t0_ms: int, t1_ms: int, sleeve: str,
                    c: dict = CFG, collect: bool = True, meta_masks: dict = None) -> dict:
    fee = c["FEE_BPS"] / 1e4
    slip_e = c["SLIP_ENTRY_BPS"] / 1e4
    slip_x = c["SLIP_STOP_BPS"] / 1e4
    cap = c["CAPITAL"]

    w = {}
    grid_set = set()
    for s, f in universe.items():
        m = (f.ts.values >= t0_ms) & (f.ts.values < t1_ms)
        if not m.any():
            continue
        sl = f.loc[m].reset_index(drop=True)
        dirn, sc = signals(sl, c, sleeve)
        if meta_masks is not None and s in meta_masks and meta_masks[s] is not None:
            mk, p_arr = meta_masks[s]
            if len(mk) == len(dirn):
                dirn = np.where(mk, dirn, 0)
                sc = np.where(np.isfinite(p_arr) & mk, p_arr, sc)
        w[s] = {"f": sl, "dirn": dirn, "sc": sc,
                "idx": {int(t): i for i, t in enumerate(sl.ts.values)},
                "_last_entry_i": -10 ** 9}
        grid_set.update(w[s]["idx"].keys())
    grid = np.array(sorted(grid_set), dtype=np.int64)
    if len(grid) == 0:
        return dict(roi=0.0, max_dd=0.0, n=0, wr=0.0, pf=0.0, trades=[],
                    equity=cap, halted=False)

    realized = 0.0
    eq_peak = cap
    max_dd = 0.0
    positions = []
    trades = []
    pending = []
    halted = False

    def governor_risk() -> float:
        dd = (eq_peak - (cap + realized)) / cap
        if dd > c["DEFENSE_DD"]:
            return c["DEFENSE_RISK"]
        if realized > c["HOUSE_PROFIT"]:
            return c["HOUSE_RISK"]
        return c["BASE_RISK"]

    def close_position(p, px_gross, reason, t):
        nonlocal realized
        exit_net = px_gross * (1 - p["dir"] * (slip_x + fee))
        pnl = (exit_net - p["entry"]) * p["qty"] * p["dir"]
        realized += pnl
        if collect:
            trades.append({"sym": p["sym"], "dir": p["dir"], "t_in": p["t_in"],
                           "t_out": int(t), "pnl": pnl, "r": pnl / p["risk_usd"],
                           "risk": p["risk_usd"], "reason": reason,
                           "hold_bars": p["age"], "mfe_r": p["mfe"]})

    for gi, g in enumerate(grid):
        gg = int(g)
        # ---- 1. manage open positions (stop armed at previous bar) ----
        for p in list(positions):
            i = w[p["sym"]]["idx"].get(gg)
            if i is None:
                continue
            f = w[p["sym"]]["f"]
            o, h, l = f.open.values[i], f.high.values[i], f.low.values[i]
            if p["pending_exit"]:
                close_position(p, o, "time", gg)
                positions.remove(p)
                continue
            hit = (l <= p["stop"]) if p["dir"] > 0 else (h >= p["stop"])
            if hit:
                fill = min(o, p["stop"]) if p["dir"] > 0 else max(o, p["stop"])
                close_position(p, fill, "stop", gg)
                positions.remove(p)
                continue
            fav = ((h - p["entry"]) / p["r_unit"] if p["dir"] > 0
                   else (p["entry"] - l) / p["r_unit"])
            p["mfe"] = max(p["mfe"], fav)
            new_stop = p["stop"]
            for trig, lock in c["RUNGS"]:
                if p["mfe"] >= trig:
                    cand = p["entry"] + p["dir"] * lock * p["r_unit"]
                    new_stop = max(new_stop, cand) if p["dir"] > 0 else min(new_stop, cand)
            if p["mfe"] >= c["TRAIL_TRIGGER_R"]:  # 5R mandate trail
                ext = h if p["dir"] > 0 else l
                cand = ext - p["dir"] * c["TRAIL_GIVEBACK_R"] * p["r_unit"]
                new_stop = max(new_stop, cand) if p["dir"] > 0 else min(new_stop, cand)
            p["stop"] = new_stop              # armed for bar j+1
            p["age"] += 1
            if p["age"] >= c["PROG_BARS"] and p["mfe"] < c["MIN_PROG_R"]:
                p["pending_exit"] = True      # stale-exit at next bar open

        # ---- 2. fill pending signals from the previous bar's close ----
        if pending and not halted:
            if (eq_peak - (cap + realized)) / cap >= c["HARD_DD"]:
                halted = True   # risk halt: no NEW entries; exits continue
            else:
                pending.sort(key=lambda x: -x[0])
                for score, s, dr in pending:
                    if len(positions) >= c["MAX_CONCURRENT"]:
                        break
                    i = w[s]["idx"].get(gg)
                    if i is None:
                        continue
                    f = w[s]["f"]
                    o, atr = f.open.values[i], f.atr.values[i]
                    if not np.isfinite(atr) or atr <= 0:
                        continue
                    dist = c["S_ATR"] * atr
                    entry = o * (1 + dr * (slip_e + fee))
                    risk_usd = governor_risk()
                    qty = risk_usd / dist
                    notional = qty * entry
                    max_not = c["MAX_NOTIONAL_LEV"] * (cap + realized)
                    if notional > max_not:
                        qty = max_not / entry
                        risk_usd = qty * dist
                    positions.append({"sym": s, "dir": dr, "t_in": gg, "entry": entry,
                                      "qty": qty, "risk_usd": risk_usd, "r_unit": dist,
                                      "stop": entry - dr * dist, "mfe": 0.0, "age": 0,
                                      "pending_exit": False})
                    w[s]["_last_entry_i"] = i
        pending = []

        # ---- 3. bar-by-bar mark-to-market equity & drawdown ----
        eq = cap + realized
        for p in positions:
            i = w[p["sym"]]["idx"].get(gg)
            if i is None:
                continue
            cl = w[p["sym"]]["f"].close.values[i]
            eq += (cl * (1 - p["dir"] * (slip_x + fee)) - p["entry"]) * p["qty"] * p["dir"]
        eq_peak = max(eq_peak, eq)
        max_dd = max(max_dd, (eq_peak - eq) / cap)

        # ---- 4. queue new signals for the next bar ----
        if gi < len(grid) - 1 and not halted:
            for s, wb in w.items():
                i = wb["idx"].get(gg)
                if i is None:
                    continue
                dr = wb["dirn"][i]
                if dr != 0 and np.isfinite(wb["sc"][i]):
                    if i - wb["_last_entry_i"] >= c["COOLDOWN"]:
                        pending.append((float(wb["sc"][i]), s, int(dr)))

    # ---- 5. force-close everything at window end (72h purge boundary) ----
    g_last = int(grid[-1])
    for p in positions:
        close_position(p, w[p["sym"]]["f"].close.values[w[p["sym"]]["idx"][g_last]],
                       "eow", g_last)

    n = len(trades)
    wins = [t for t in trades if t["pnl"] > 0]
    gw = sum(t["pnl"] for t in wins)
    gl = -sum(t["pnl"] for t in trades if t["pnl"] <= 0)
    return dict(roi=realized / cap, max_dd=max_dd, n=n,
                wr=len(wins) / n if n else 0.0,
                pf=gw / gl if gl > 0 else (float("inf") if gw > 0 else 0.0),
                trades=trades, equity=cap + realized, halted=halted)


__version__ = "1.0.0"
