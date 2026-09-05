"""
Institutional Multi-Strategy Quant Suite — Engine 2
====================================================
Five causal long-side microstructure strategies on 18 Binance USDT-M perpetuals,
executed under ONE shared portfolio risk governor (MAX_CONCURRENT = 2).

Causality contract (FABLE5 Part 14):
  * Every feature is a backward-looking rolling or session-reset operator.
  * No parameter, threshold or branch is keyed on window index.
  * Trailing ratchets are computed from bar j and take effect on bar j+1 only.
  * Drawdown is mark-to-market, evaluated bar-by-bar, never from future trade MAE.
  * Frictions: 8 bps taker fee per fill, 10 bps entry slip, 15 bps adverse-exit slip.
  * No early termination on reaching a profit target.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from numba import njit

# ---------------------------------------------------------------------------
# 1. INVARIANTS  (single global configuration — identical for all 20 windows)
# ---------------------------------------------------------------------------

_local_data = Path(__file__).resolve().parent / "binance_backtesting_data"
_repo_data = Path(r"c:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\Engine_2\binance_backtesting_data")
DATA_DIR = _local_data if _local_data.exists() else _repo_data
BAR_MS = 900_000  # 15 minutes

UNIVERSE_CORE = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "LINKUSDT", "SUIUSDT", "NEARUSDT", "APTUSDT",
    "PEPEUSDT", "WIFUSDT", "TIAUSDT", "ARBUSDT", "OPUSDT", "INJUSDT",
]
UNIVERSE_EXTENDED = UNIVERSE_CORE + ["BCHUSDT", "DOTUSDT", "LTCUSDT", "TRXUSDT"]

STRATEGY_NAMES = {
    1: "S1_LiquidationCascadeRebound",
    2: "S2_CvdDivergenceBasisSnapback",
    3: "S3_FootprintAbsorptionFlush",
    4: "S4_FundingSqueezeCarry",
    5: "S5_VwapOvershootReplenish",
}

EXIT_REASONS = {
    0: "STOP", 1: "TARGET", 2: "TIME_STOP",
    3: "FUNDING_HARD_EXIT", 4: "CIRCUIT_BREAKER", 5: "WINDOW_END",
}


@dataclass(frozen=True)
class RiskConfig:
    """Portfolio risk governor — AGENTS.md Part 2 §5 / KB Node 10."""
    initial_capital: float = 5_000.0
    base_risk: float = 25.0            # 0.50 %
    house_money_risk: float = 50.0     # 1.00 %, unlocked at +$50 realised
    drawdown_defense_risk: float = 15.0  # 0.30 %
    house_money_threshold: float = 50.0
    drawdown_defense_threshold: float = 0.025  # 2.5 % MTM drawdown
    drawdown_risk_limit: float = 0.045         # 4.5 % hard circuit breaker
    max_concurrent: int = 2
    max_notional_mult: float = 3.0     # exchange leverage sanity cap on equity


@dataclass(frozen=True)
class FrictionConfig:
    """Binance VIP0 realistic execution frictions."""
    taker_fee: float = 0.0008       # 8 bps per fill, charged on entry AND exit
    slip_entry: float = 0.0010      # 10 bps
    slip_stop: float = 0.0015       # 15 bps
    slip_market_exit: float = 0.0015  # 15 bps on time-stop / breaker exits


@dataclass(frozen=True)
class RatchetConfig:
    """4-tier anti-retracement ratchet — KB Node 7 (purges the 5.0R trap)."""
    arm_tier0: float = 0.80   # at +0.80R ...
    lock_tier0: float = 0.15  # ... stop -> entry + 0.15R
    arm_tier1: float = 1.50   # at +1.50R ...
    lock_tier1: float = 0.80  # ... stop -> entry + 0.80R
    time_stop_bars: int = 24  # Snell stopping horizon (6 h)
    time_stop_r: float = 0.20  # must have reached >= +0.20R MFE by then
    min_stop_frac: float = 0.0015  # stop must clear round-trip friction
    pending_life_bars: int = 4     # S3 stop-buy validity


@dataclass(frozen=True)
class SignalConfig:
    """
    Strategy thresholds, verbatim from the Section 4 contract.
    These are CONSTANTS, not per-window variables. There is no w_idx anywhere.
    """
    # --- shared feature windows
    z_window: int = 20
    long_window: int = 96      # 24 h of 15m bars

    # --- S1
    s1_liq_z: float = 1.8
    s1_oi_change: float = -0.8
    s1_taker_sell_mult: float = 2.0
    s1_wick_frac: float = 0.35
    s1_stop_atr: float = 0.20
    s1_target_r: float = 2.2

    # --- S2
    s2_zc_div: float = 1.0
    s2_basis_frac: float = -0.0005
    s2_vwap_z: float = -0.8
    s2_rsi: float = 42.0
    s2_stop_atr: float = 1.5
    s2_target_r_lo: float = 1.2
    s2_target_r_hi: float = 2.0

    # --- S3
    s3_delta_mult: float = 1.8
    s3_close_pos: float = 0.50
    s3_poc_pos: float = 0.30
    s3_depth_mult: float = 1.5
    s3_stop_atr: float = 0.05
    s3_target_r: float = 2.5

    # --- S4
    s4_funding: float = -0.03
    s4_ls_global: float = 0.85
    s4_top_account: float = 0.90
    s4_stop_atr: float = 1.2
    s4_target_r: float = 1.8

    # --- S5
    s5_vwap_z: float = -2.0
    s5_depth_repl: float = 0.35
    s5_rsi: float = 30.0
    s5_whale_index: float = 1.2
    s5_trade_size_mult: float = 1.5
    s5_stop_atr: float = 1.5
    s5_target_r_lo: float = 1.0
    s5_target_r_hi: float = 2.5


RISK = RiskConfig()
FRICTION = FrictionConfig()
RATCHET = RatchetConfig()
SIGCFG = SignalConfig()


# ---------------------------------------------------------------------------
# 2. CAUSAL FEATURE ENGINE (vectorised, strictly backward-looking)
# ---------------------------------------------------------------------------

def _series(df: pd.DataFrame, name: str, default: float = 0.0) -> pd.Series:
    """Schema-tolerant column access. Missing metric -> neutral constant."""
    if name in df.columns:
        return pd.to_numeric(df[name], errors="coerce").astype("float64")
    return pd.Series(np.full(len(df), default, dtype="float64"), index=df.index)


def _roll_z(s: pd.Series, w: int) -> pd.Series:
    m = s.rolling(w, min_periods=w).mean()
    sd = s.rolling(w, min_periods=w).std(ddof=0)
    return ((s - m) / sd.where(sd > 1e-12)).replace([np.inf, -np.inf], 0.0).fillna(0.0)


def build_features(df: pd.DataFrame, cfg: SignalConfig = SIGCFG) -> pd.DataFrame:
    """
    Derive every engineered feature the 5 strategies consume.

    CAUSALITY PROOF: only .rolling(), .diff(), .shift(+n>0) and UTC-day
    groupby-cumsum are used. No .expanding().mean() over the full sample, no
    centred windows, no global normalisation. Therefore
        build_features(full_history).loc[window] == build_features(window_slice)
    for every row with sufficient warmup, which is what licenses the
    compute-once / slice-many pattern used by the harness.
    """
    f = pd.DataFrame(index=df.index)
    f["open_time_ms"] = df["open_time_ms"].astype("int64")
    o, h, l, c = (_series(df, k) for k in ("open", "high", "low", "close"))
    f["open"], f["high"], f["low"], f["close"] = o, h, l, c

    rng = (h - l).where((h - l) > 1e-12)
    atr14 = _series(df, "atr_14").replace(0.0, np.nan)
    atr14 = atr14.fillna((h - l).rolling(14, min_periods=14).mean())
    f["atr_14"] = atr14
    f["rsi_14"] = _series(df, "rsi_14", 50.0)
    f["ema_8"] = _series(df, "ema_8").replace(0.0, np.nan).fillna(
        c.ewm(span=8, adjust=False).mean())

    # --- Session VWAP anchored at 00:00 UTC (KB Node 3) -------------------
    vol = _series(df, "volume_base").replace(0.0, np.nan)
    tp = (h + l + c) / 3.0
    day = (f["open_time_ms"] // 86_400_000).astype("int64")
    pv = (tp * vol).groupby(day).cumsum()
    cv = vol.groupby(day).cumsum()
    vwap = (pv / cv.where(cv > 1e-12)).fillna(c)
    f["vwap"] = vwap
    dev = c - vwap
    dev_sd = dev.rolling(cfg.z_window, min_periods=cfg.z_window).std(ddof=0)
    f["vwap_z"] = (dev / dev_sd.where(dev_sd > 1e-12)).fillna(0.0)

    # --- S1: liquidation cascade exhaustion -------------------------------
    f["long_liq_zs"] = _roll_z(_series(df, "long_liq_usd"), cfg.z_window)
    f["oi_change_pct"] = _series(df, "oi_change_pct")
    vol_sma9 = _series(df, "volume_sma9").replace(0.0, np.nan).fillna(
        vol.rolling(9, min_periods=9).mean())
    taker_sell = _series(df, "taker_sell_vol_btc")
    f["taker_sell_ratio"] = (taker_sell / vol_sma9.where(vol_sma9 > 1e-12)).fillna(0.0)
    f["lower_wick_frac"] = ((np.minimum(o, c) - l) / rng).fillna(0.0)
    f["fp_delta"] = _series(df, "fp_delta")

    # --- S2: spot/futures CVD divergence + basis --------------------------
    fut_life, spot_life = _series(df, "future_cvd_lifetime"), _series(df, "spot_cvd_lifetime")
    d_fut = fut_life.diff() if fut_life.abs().sum() > 0 else _series(df, "future_cvd_15m")
    d_spot = spot_life.diff() if spot_life.abs().sum() > 0 else _series(df, "spot_cvd_15m")
    f["d_fut"], f["d_spot"] = d_fut.fillna(0.0), d_spot.fillna(0.0)
    f["zc_div"] = 0.5 * (_roll_z(f["d_spot"], cfg.z_window) - _roll_z(f["d_fut"], cfg.z_window))
    f["basis_usd"] = _series(df, "basis_usd")

    # --- S3: footprint absorption ----------------------------------------
    f["fp_abs_mean"] = f["fp_delta"].abs().rolling(
        cfg.long_window, min_periods=cfg.long_window).mean()
    f["close_pos"] = ((c - l) / rng).fillna(0.5)
    f["fp_stacked_buy_imb"] = _series(df, "fp_stacked_buy_imb")
    poc = _series(df, "fp_poc").replace(0.0, np.nan)
    f["poc_pos"] = ((poc - l) / rng).fillna(0.5)
    bid_d, ask_d = _series(df, "bid_depth_usd"), _series(df, "ask_depth_usd")
    f["depth_ratio"] = (bid_d / ask_d.where(ask_d > 1e-12)).fillna(1.0)

    # --- S4: funding squeeze ---------------------------------------------
    f["funding_rate_pct"] = _series(df, "funding_rate_pct")
    f["ls_ratio_global"] = _series(df, "ls_ratio_global", 1.0)
    f["top_account_ratio"] = _series(df, "top_account_ratio", 1.0)
    minute = ((f["open_time_ms"] // 60_000) % 1440).astype("int64")
    f["minute_utc"] = minute
    in_pre = ((minute >= 390) & (minute <= 465)) | \
             ((minute >= 870) & (minute <= 945)) | \
             ((minute >= 1350) & (minute <= 1425))
    f["funding_window"] = in_pre
    nxt = np.where(minute < 480, 480, np.where(minute < 960, 960, 1440))
    f["bars_to_settle"] = np.ceil((nxt - minute) / 15.0).astype("int64") + 1

    # --- S5: VWAP overshoot + book replenishment -------------------------
    f["bid_repl"] = bid_d.pct_change().replace([np.inf, -np.inf], 0.0).fillna(0.0)
    f["whale_index"] = _series(df, "whale_index")
    ats = _series(df, "avg_trade_size_usd")
    ats_mean = ats.rolling(cfg.long_window, min_periods=cfg.long_window).mean()
    f["ats_ratio"] = (ats / ats_mean.where(ats_mean > 1e-12)).fillna(0.0)
    f["session_val"] = _series(df, "session_val")

    f["warm"] = f["fp_abs_mean"].notna() & f["atr_14"].notna() & (f["atr_14"] > 0)
    return f


# ---------------------------------------------------------------------------
# 3. STRATEGY SIGNAL CONTRACTS
#    Each returns (fire, mode, trigger, stop, target_r, rank, hard_bars).
#    mode 0 = market-on-signal-close, mode 1 = resting stop-buy above trigger.
# ---------------------------------------------------------------------------

def _blank(n: int):
    return (np.zeros(n, bool), np.zeros(n, np.int8), np.zeros(n), np.zeros(n),
            np.zeros(n), np.full(n, -1e9), np.zeros(n, np.int64))


def strategy_signals(f: pd.DataFrame, sid: int, cfg: SignalConfig = SIGCFG):
    n = len(f)
    fire, mode, trig, stop, tgt, rank, hardb = _blank(n)
    c, h, l = f["close"].to_numpy(), f["high"].to_numpy(), f["low"].to_numpy()
    atr = f["atr_14"].to_numpy()
    warm = f["warm"].to_numpy()

    if sid == 1:
        reversal = (f["lower_wick_frac"].to_numpy() >= cfg.s1_wick_frac) | \
                   (f["fp_delta"].to_numpy() > 0.0)
        ok = (warm
              & (f["long_liq_zs"].to_numpy() > cfg.s1_liq_z)
              & (f["oi_change_pct"].to_numpy() < cfg.s1_oi_change)
              & (f["taker_sell_ratio"].to_numpy() > cfg.s1_taker_sell_mult)
              & reversal)
        fire = ok
        stop = l - cfg.s1_stop_atr * atr
        tgt = np.full(n, cfg.s1_target_r)
        rank = f["long_liq_zs"].to_numpy() - cfg.s1_liq_z

    elif sid == 2:
        ok = (warm
              & (f["d_fut"].to_numpy() < 0.0) & (f["d_spot"].to_numpy() > 0.0)
              & (f["zc_div"].to_numpy() > cfg.s2_zc_div)
              & (f["basis_usd"].to_numpy() < cfg.s2_basis_frac * c)
              & (f["vwap_z"].to_numpy() < cfg.s2_vwap_z)
              & (f["rsi_14"].to_numpy() < cfg.s2_rsi))
        fire = ok
        stop = c - cfg.s2_stop_atr * atr
        with np.errstate(divide="ignore", invalid="ignore"):
            r_vwap = (f["vwap"].to_numpy() - c) / np.maximum(c - stop, 1e-12)
        tgt = np.clip(np.nan_to_num(r_vwap), cfg.s2_target_r_lo, cfg.s2_target_r_hi)
        rank = f["zc_div"].to_numpy() - cfg.s2_zc_div

    elif sid == 3:
        cluster = (f["fp_stacked_buy_imb"].to_numpy() >= 1.0) | \
                  (f["poc_pos"].to_numpy() < cfg.s3_poc_pos)
        ok = (warm
              & (f["fp_delta"].to_numpy() < -cfg.s3_delta_mult * f["fp_abs_mean"].to_numpy())
              & (f["close_pos"].to_numpy() >= cfg.s3_close_pos)
              & cluster
              & (f["depth_ratio"].to_numpy() > cfg.s3_depth_mult))
        fire = ok
        mode = np.ones(n, np.int8)
        trig = h.copy()
        stop = l - cfg.s3_stop_atr * atr
        tgt = np.full(n, cfg.s3_target_r)
        denom = np.maximum(f["fp_abs_mean"].to_numpy(), 1e-12)
        rank = np.abs(f["fp_delta"].to_numpy()) / denom - cfg.s3_delta_mult

    elif sid == 4:
        ok = (warm
              & (f["funding_rate_pct"].to_numpy() < cfg.s4_funding)
              & f["funding_window"].to_numpy()
              & (f["ls_ratio_global"].to_numpy() < cfg.s4_ls_global)
              & (f["top_account_ratio"].to_numpy() < cfg.s4_top_account)
              & (c > f["ema_8"].to_numpy()))
        fire = ok
        stop = c - cfg.s4_stop_atr * atr
        tgt = np.full(n, cfg.s4_target_r)
        hardb = f["bars_to_settle"].to_numpy().astype(np.int64)
        rank = cfg.s4_funding - f["funding_rate_pct"].to_numpy()

    elif sid == 5:
        dislocated = (f["vwap_z"].to_numpy() < cfg.s5_vwap_z) | \
                     ((f["session_val"].to_numpy() > 0) & (c < f["session_val"].to_numpy()))
        whale = (f["whale_index"].to_numpy() > cfg.s5_whale_index) | \
                (f["ats_ratio"].to_numpy() > cfg.s5_trade_size_mult)
        turn = c > f["open"].to_numpy()
        ok = (warm & dislocated
              & (f["bid_repl"].to_numpy() > cfg.s5_depth_repl)
              & (f["rsi_14"].to_numpy() < cfg.s5_rsi)
              & whale & turn)
        fire = ok
        stop = c - cfg.s5_stop_atr * atr
        with np.errstate(divide="ignore", invalid="ignore"):
            r_vwap = (f["vwap"].to_numpy() - c) / np.maximum(c - stop, 1e-12)
        tgt = np.clip(np.nan_to_num(r_vwap), cfg.s5_target_r_lo, cfg.s5_target_r_hi)
        rank = -(f["vwap_z"].to_numpy()) + cfg.s5_vwap_z

    else:
        raise ValueError(f"unknown strategy id {sid}")

    fire = fire & np.isfinite(stop) & (stop > 0) & (stop < c)
    rank = np.where(fire, np.nan_to_num(rank, nan=0.0), -1e9)
    return fire, mode, trig, stop, tgt, rank, hardb


# ---------------------------------------------------------------------------
# 4. @njit PORTFOLIO TRADE-PATH SIMULATOR
# ---------------------------------------------------------------------------

@njit(cache=True, fastmath=True)
def simulate_portfolio(
    op, hi, lo, cl, valid,
    sig, mode, trig, stp, tgtr, rank, hardb,
    initial_capital, base_risk, house_risk, def_risk,
    house_thr, dd_def_thr, dd_limit, max_conc, max_notional_mult,
    fee, slip_in, slip_stop, slip_mkt,
    arm0, lock0, arm1, lock1, ts_bars, ts_r, min_stop_frac, pend_life,
    max_trades,
):
    """
    Cross-sectional, time-aligned portfolio simulation.

    Strict per-bar ordering (this ordering IS the causality guarantee):
      (1) resolve exits on OPEN positions using the stop/target set at bar j-1
      (2) update ratchets from bar j's high  -> effective bar j+1 ONLY
      (3) mark equity to market on bar j close, update peak / drawdown
      (4) trip circuit breaker if MTM drawdown >= dd_limit
      (5) fill resting stop-buys, then admit new signals from bar j close
    A position opened at bar j close is never path-evaluated inside bar j.
    """
    T, S = op.shape
    MAXP = 16

    p_act = np.zeros(MAXP, np.uint8)
    p_sym = np.zeros(MAXP, np.int64)
    p_str = np.zeros(MAXP, np.int64)
    p_ent = np.zeros(MAXP, np.float64)
    p_stp = np.zeros(MAXP, np.float64)
    p_tgt = np.zeros(MAXP, np.float64)
    p_qty = np.zeros(MAXP, np.float64)
    p_rr = np.zeros(MAXP, np.float64)
    p_eb = np.zeros(MAXP, np.int64)
    p_mr = np.zeros(MAXP, np.float64)
    p_hb = np.zeros(MAXP, np.int64)
    p_rk = np.zeros(MAXP, np.float64)

    sym_busy = np.zeros(S, np.uint8)
    pd_act = np.zeros(S, np.uint8)
    pd_str = np.zeros(S, np.int64)
    pd_trg = np.zeros(S, np.float64)
    pd_stp = np.zeros(S, np.float64)
    pd_tgt = np.zeros(S, np.float64)
    pd_exp = np.zeros(S, np.int64)
    pd_hb = np.zeros(S, np.int64)
    pd_rk = np.zeros(S, np.float64)

    last_cl = np.zeros(S, np.float64)
    has_cl = np.zeros(S, np.uint8)

    t_sym = np.zeros(max_trades, np.int64)
    t_str = np.zeros(max_trades, np.int64)
    t_eb = np.zeros(max_trades, np.int64)
    t_xb = np.zeros(max_trades, np.int64)
    t_ent = np.zeros(max_trades, np.float64)
    t_ext = np.zeros(max_trades, np.float64)
    t_qty = np.zeros(max_trades, np.float64)
    t_pnl = np.zeros(max_trades, np.float64)
    t_r = np.zeros(max_trades, np.float64)
    t_rsn = np.zeros(max_trades, np.int64)
    t_rsk = np.zeros(max_trades, np.float64)

    eq_curve = np.zeros(T, np.float64)
    dd_curve = np.zeros(T, np.float64)

    realized = initial_capital
    peak = initial_capital
    halted = 0
    n_tr = 0

    for t in range(T):
        # ---- (1) exits on existing positions, (2) ratchet for j+1 --------
        for k in range(MAXP):
            if p_act[k] == 0:
                continue
            s = p_sym[k]
            if valid[t, s] == 0:
                continue
            o_, h_, l_, c_ = op[t, s], hi[t, s], lo[t, s], cl[t, s]

            px = 0.0
            rsn = -1
            if o_ <= p_stp[k]:
                px = o_ * (1.0 - slip_stop); rsn = 0
            elif o_ >= p_tgt[k]:
                px = o_; rsn = 1
            elif l_ <= p_stp[k]:
                px = p_stp[k] * (1.0 - slip_stop); rsn = 0
            elif h_ >= p_tgt[k]:
                px = p_tgt[k]; rsn = 1

            r_bar = (h_ - p_ent[k]) / p_rr[k]
            if r_bar > p_mr[k]:
                p_mr[k] = r_bar

            if rsn < 0:
                held = t - p_eb[k]
                if p_hb[k] > 0 and held >= p_hb[k]:
                    px = c_ * (1.0 - slip_mkt); rsn = 3
                elif held >= ts_bars and p_mr[k] < ts_r:
                    px = c_ * (1.0 - slip_mkt); rsn = 2

            if rsn >= 0:
                gross = p_qty[k] * (px - p_ent[k])
                fees = p_qty[k] * (p_ent[k] + px) * fee
                pnl = gross - fees
                realized += pnl
                if n_tr < max_trades:
                    t_sym[n_tr] = s; t_str[n_tr] = p_str[k]
                    t_eb[n_tr] = p_eb[k]; t_xb[n_tr] = t
                    t_ent[n_tr] = p_ent[k]; t_ext[n_tr] = px
                    t_qty[n_tr] = p_qty[k]; t_pnl[n_tr] = pnl
                    t_r[n_tr] = pnl / p_rk[k] if p_rk[k] > 0 else 0.0
                    t_rsn[n_tr] = rsn; t_rsk[n_tr] = p_rk[k]
                    n_tr += 1
                p_act[k] = 0
                sym_busy[s] = 0
                continue

            # ratchet computed from bar t, ARMED FOR BAR t+1 (never reused above)
            if p_mr[k] >= arm1:
                cand = p_ent[k] + lock1 * p_rr[k]
                if cand > p_stp[k]:
                    p_stp[k] = cand
            elif p_mr[k] >= arm0:
                cand = p_ent[k] + lock0 * p_rr[k]
                if cand > p_stp[k]:
                    p_stp[k] = cand

        # ---- (3) mark-to-market equity -----------------------------------
        for s in range(S):
            if valid[t, s] == 1:
                last_cl[s] = cl[t, s]; has_cl[s] = 1
        unreal = 0.0
        for k in range(MAXP):
            if p_act[k] == 1 and has_cl[p_sym[k]] == 1:
                unreal += p_qty[k] * (last_cl[p_sym[k]] - p_ent[k])
        equity = realized + unreal
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak if peak > 0 else 0.0
        eq_curve[t] = equity
        dd_curve[t] = dd

        # ---- (4) hard circuit breaker ------------------------------------
        if halted == 0 and dd >= dd_limit:
            for k in range(MAXP):
                if p_act[k] == 0:
                    continue
                s = p_sym[k]
                if has_cl[s] == 0:
                    p_act[k] = 0; sym_busy[s] = 0; continue
                px = last_cl[s] * (1.0 - slip_mkt)
                gross = p_qty[k] * (px - p_ent[k])
                fees = p_qty[k] * (p_ent[k] + px) * fee
                pnl = gross - fees
                realized += pnl
                if n_tr < max_trades:
                    t_sym[n_tr] = s; t_str[n_tr] = p_str[k]
                    t_eb[n_tr] = p_eb[k]; t_xb[n_tr] = t
                    t_ent[n_tr] = p_ent[k]; t_ext[n_tr] = px
                    t_qty[n_tr] = p_qty[k]; t_pnl[n_tr] = pnl
                    t_r[n_tr] = pnl / p_rk[k] if p_rk[k] > 0 else 0.0
                    t_rsn[n_tr] = 4; t_rsk[n_tr] = p_rk[k]
                    n_tr += 1
                p_act[k] = 0; sym_busy[s] = 0
            halted = 1
            eq_curve[t] = realized

        if halted == 1:
            for s in range(S):
                pd_act[s] = 0
            continue

        # ---- risk tier (causal: realised P&L + current MTM drawdown) -----
        n_open = 0
        for k in range(MAXP):
            if p_act[k] == 1:
                n_open += 1
        free = max_conc - n_open
        if free <= 0:
            continue

        if dd > dd_def_thr:
            risk_dollars = def_risk
        elif (realized - initial_capital) >= house_thr:
            risk_dollars = house_risk
        else:
            risk_dollars = base_risk

        # ---- (5a) resting stop-buy fills (S3) ----------------------------
        for s in range(S):
            if free <= 0:
                break
            if pd_act[s] == 0:
                continue
            if t > pd_exp[s]:
                pd_act[s] = 0; continue
            if valid[t, s] == 0 or sym_busy[s] == 1:
                continue
            if hi[t, s] < pd_trg[s]:
                continue
            raw = op[t, s] if op[t, s] > pd_trg[s] else pd_trg[s]
            ent = raw * (1.0 + slip_in)
            sl = pd_stp[s]
            if sl <= 0.0 or (ent - sl) / ent < min_stop_frac:
                pd_act[s] = 0; continue
            rr = ent - sl
            qty = risk_dollars / rr
            cap = max_notional_mult * equity / ent
            if qty > cap:
                qty = cap
            for k in range(MAXP):
                if p_act[k] == 0:
                    p_act[k] = 1; p_sym[k] = s; p_str[k] = pd_str[s]
                    p_ent[k] = ent; p_stp[k] = sl
                    p_tgt[k] = ent + pd_tgt[s] * rr
                    p_qty[k] = qty; p_rr[k] = rr; p_eb[k] = t
                    p_mr[k] = 0.0; p_hb[k] = pd_hb[s]
                    p_rk[k] = qty * rr
                    break
            sym_busy[s] = 1; pd_act[s] = 0; free -= 1

        # ---- (5b) new signals at bar t close, ranked ---------------------
        while free > 0:
            best, best_rk = -1, -1e18
            for s in range(S):
                if sig[t, s] == 0 or valid[t, s] == 0 or sym_busy[s] == 1:
                    continue
                if rank[t, s] > best_rk:
                    best_rk = rank[t, s]; best = s
            if best < 0:
                break
            s = best
            sym_busy[s] = 1  # consumed this bar either way

            if mode[t, s] == 1:
                pd_act[s] = 1; pd_str[s] = sig[t, s]
                pd_trg[s] = trig[t, s]; pd_stp[s] = stp[t, s]
                pd_tgt[s] = tgtr[t, s]; pd_exp[s] = t + pend_life
                pd_hb[s] = hardb[t, s]; pd_rk[s] = rank[t, s]
                sym_busy[s] = 0
                continue

            ent = cl[t, s] * (1.0 + slip_in)
            sl = stp[t, s]
            if sl <= 0.0 or (ent - sl) / ent < min_stop_frac:
                sym_busy[s] = 0
                continue
            rr = ent - sl
            qty = risk_dollars / rr
            cap = max_notional_mult * equity / ent
            if qty > cap:
                qty = cap
            for k in range(MAXP):
                if p_act[k] == 0:
                    p_act[k] = 1; p_sym[k] = s; p_str[k] = sig[t, s]
                    p_ent[k] = ent; p_stp[k] = sl
                    p_tgt[k] = ent + tgtr[t, s] * rr
                    p_qty[k] = qty; p_rr[k] = rr; p_eb[k] = t
                    p_mr[k] = 0.0; p_hb[k] = hardb[t, s]
                    p_rk[k] = qty * rr
                    break
            free -= 1

    # ---- forced flat at window end (no lookahead: last available close) --
    for k in range(MAXP):
        if p_act[k] == 0:
            continue
        s = p_sym[k]
        if has_cl[s] == 0:
            p_act[k] = 0; continue
        px = last_cl[s] * (1.0 - slip_mkt)
        gross = p_qty[k] * (px - p_ent[k])
        fees = p_qty[k] * (p_ent[k] + px) * fee
        pnl = gross - fees
        realized += pnl
        if n_tr < max_trades:
            t_sym[n_tr] = s; t_str[n_tr] = p_str[k]
            t_eb[n_tr] = p_eb[k]; t_xb[n_tr] = T - 1
            t_ent[n_tr] = p_ent[k]; t_ext[n_tr] = px
            t_qty[n_tr] = p_qty[k]; t_pnl[n_tr] = pnl
            t_r[n_tr] = pnl / p_rk[k] if p_rk[k] > 0 else 0.0
            t_rsn[n_tr] = 5; t_rsk[n_tr] = p_rk[k]
            n_tr += 1
        p_act[k] = 0
    if T > 0:
        eq_curve[T - 1] = realized

    return (n_tr, halted, realized, eq_curve, dd_curve,
            t_sym, t_str, t_eb, t_xb, t_ent, t_ext, t_qty, t_pnl, t_r, t_rsn, t_rsk)


# ---------------------------------------------------------------------------
# 5. DATA LAYER + MATRIX ASSEMBLY
# ---------------------------------------------------------------------------

class DataStore:
    """Loads each master parquet once, computes causal features once, caches."""

    def __init__(self, symbols, data_dir: Path = DATA_DIR, verbose: bool = True):
        self.data_dir = Path(data_dir)
        self.verbose = verbose
        self.features: dict[str, pd.DataFrame] = {}
        self.symbols: list[str] = []
        for sym in symbols:
            path = self.data_dir / f"{sym}_15m_master_2020_2026.parquet"
            if not path.exists():
                if verbose:
                    print(f"  [skip] {sym}: {path.name} not found")
                continue
            df = pd.read_parquet(path)
            df = df.sort_values("open_time_ms").drop_duplicates("open_time_ms")
            df = df.reset_index(drop=True)
            f = build_features(df)
            self.features[sym] = f
            self.symbols.append(sym)
            if verbose:
                print(f"  [load] {sym:10s} bars={len(f):>7,}")
        if not self.symbols:
            raise FileNotFoundError(f"no master parquet files found in {self.data_dir}")

    def signal_cache(self, sid: int) -> dict[str, tuple]:
        if not hasattr(self, "_sig"):
            self._sig = {}
        if sid not in self._sig:
            self._sig[sid] = {s: strategy_signals(self.features[s], sid)
                              for s in self.symbols}
        return self._sig[sid]


def assemble_window(store: DataStore, start_ms: int, end_ms: int, strategy_ids):
    """
    Build the time-aligned cross-sectional matrices for one OOS window.
    Grid is the canonical 15m lattice; missing symbol bars are masked invalid.
    """
    grid = np.arange(start_ms, end_ms + BAR_MS, BAR_MS, dtype=np.int64)
    T, S = len(grid), len(store.symbols)
    gi = {v: i for i, v in enumerate(grid)}

    op = np.zeros((T, S)); hi = np.zeros((T, S))
    lo = np.zeros((T, S)); cl = np.zeros((T, S))
    valid = np.zeros((T, S), np.uint8)
    sig = np.zeros((T, S), np.int64); mode = np.zeros((T, S), np.int8)
    trig = np.zeros((T, S)); stp = np.zeros((T, S))
    tgtr = np.zeros((T, S)); rank = np.full((T, S), -1e9)
    hardb = np.zeros((T, S), np.int64)

    caches = {sid: store.signal_cache(sid) for sid in strategy_ids}

    for j, sym in enumerate(store.symbols):
        f = store.features[sym]
        tms = f["open_time_ms"].to_numpy()
        m = (tms >= start_ms) & (tms <= end_ms)
        if not m.any():
            continue
        rows = np.nonzero(m)[0]
        tix = np.array([gi[v] for v in tms[rows]], dtype=np.int64)

        op[tix, j] = f["open"].to_numpy()[rows]
        hi[tix, j] = f["high"].to_numpy()[rows]
        lo[tix, j] = f["low"].to_numpy()[rows]
        cl[tix, j] = f["close"].to_numpy()[rows]
        valid[tix, j] = 1

        for sid in strategy_ids:
            fire, md, tg, sl, tr, rk, hb = caches[sid][sym]
            sel = rows[fire[rows]]
            if sel.size == 0:
                continue
            k = np.array([gi[v] for v in tms[sel]], dtype=np.int64)
            better = rk[sel] > rank[k, j]
            k, sel = k[better], sel[better]
            if k.size == 0:
                continue
            sig[k, j] = sid; mode[k, j] = md[sel]
            trig[k, j] = tg[sel]; stp[k, j] = sl[sel]
            tgtr[k, j] = tr[sel]; rank[k, j] = rk[sel]
            hardb[k, j] = hb[sel]

    bad = ~np.isfinite(op) | ~np.isfinite(hi) | ~np.isfinite(lo) | ~np.isfinite(cl)
    valid[bad] = 0
    for a in (op, hi, lo, cl, trig, stp, tgtr, rank):
        np.nan_to_num(a, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
    sig[valid == 0] = 0
    return grid, op, hi, lo, cl, valid, sig, mode, trig, stp, tgtr, rank, hardb


# ---------------------------------------------------------------------------
# 6. WINDOW RUNNER + METRICS
# ---------------------------------------------------------------------------

def run_window(store: DataStore, start_ms: int, end_ms: int, strategy_ids,
               risk: RiskConfig = RISK, friction: FrictionConfig = FRICTION,
               ratchet: RatchetConfig = RATCHET):
    grid, op, hi, lo, cl, valid, sig, mode, trig, stp, tgtr, rank, hardb = \
        assemble_window(store, start_ms, end_ms, strategy_ids)

    (n_tr, halted, final_eq, eq, ddc, t_sym, t_str, t_eb, t_xb,
     t_ent, t_ext, t_qty, t_pnl, t_r, t_rsn, t_rsk) = simulate_portfolio(
        op, hi, lo, cl, valid, sig, mode, trig, stp, tgtr, rank, hardb,
        risk.initial_capital, risk.base_risk, risk.house_money_risk,
        risk.drawdown_defense_risk, risk.house_money_threshold,
        risk.drawdown_defense_threshold, risk.drawdown_risk_limit,
        risk.max_concurrent, risk.max_notional_mult,
        friction.taker_fee, friction.slip_entry, friction.slip_stop,
        friction.slip_market_exit,
        ratchet.arm_tier0, ratchet.lock_tier0, ratchet.arm_tier1, ratchet.lock_tier1,
        ratchet.time_stop_bars, ratchet.time_stop_r, ratchet.min_stop_frac,
        ratchet.pending_life_bars, 50_000,
    )

    trades = pd.DataFrame({
        "symbol": [store.symbols[i] for i in t_sym[:n_tr]],
        "strategy": [STRATEGY_NAMES[i] for i in t_str[:n_tr]],
        "strategy_id": t_str[:n_tr],
        "entry_time_utc": pd.to_datetime(grid[t_eb[:n_tr]], unit="ms", utc=True),
        "exit_time_utc": pd.to_datetime(grid[t_xb[:n_tr]], unit="ms", utc=True),
        "bars_held": t_xb[:n_tr] - t_eb[:n_tr],
        "entry_px": t_ent[:n_tr], "exit_px": t_ext[:n_tr],
        "qty": t_qty[:n_tr], "risk_usd": t_rsk[:n_tr],
        "pnl_usd": t_pnl[:n_tr], "r_multiple": t_r[:n_tr],
        "exit_reason": [EXIT_REASONS[i] for i in t_rsn[:n_tr]],
    }).sort_values("exit_time_utc").reset_index(drop=True)

    metrics = compute_metrics(trades, eq, ddc, bool(halted), risk.initial_capital)
    return trades, metrics, pd.DataFrame({
        "time_utc": pd.to_datetime(grid, unit="ms", utc=True),
        "equity": eq, "drawdown": ddc,
    })


def compute_metrics(trades: pd.DataFrame, eq: np.ndarray, ddc: np.ndarray,
                    halted: bool, initial: float) -> dict:
    n = len(trades)
    final = float(eq[-1]) if len(eq) else initial
    wins = trades.loc[trades["pnl_usd"] > 0, "pnl_usd"]
    losses = trades.loc[trades["pnl_usd"] <= 0, "pnl_usd"]
    gross_w, gross_l = float(wins.sum()), float(-losses.sum())
    return {
        "trades": n,
        "roi_pct": 100.0 * (final - initial) / initial,
        "net_pnl": final - initial,
        "final_equity": final,
        "max_dd_pct": 100.0 * float(ddc.max()) if len(ddc) else 0.0,
        "win_rate_pct": 100.0 * len(wins) / n if n else 0.0,
        "profit_factor": gross_w / gross_l if gross_l > 1e-9 else (np.inf if gross_w > 0 else 0.0),
        "avg_r": float(trades["r_multiple"].mean()) if n else 0.0,
        "expectancy_usd": float(trades["pnl_usd"].mean()) if n else 0.0,
        "avg_bars_held": float(trades["bars_held"].mean()) if n else 0.0,
        "circuit_breaker": halted,
    }


def evaluate_gates(m: dict, min_roi: float = 10.0, max_dd: float = 5.0,
                   min_wr: float = 40.0, min_trades: int = 6) -> tuple[bool, str]:
    """Section 6.1 pass gates. Returns (passed, first_failure_reason)."""
    if m["circuit_breaker"]:
        return False, "CIRCUIT_BREAKER_TRIPPED"
    if m["trades"] < min_trades:
        return False, f"TRADES<{min_trades}"
    if m["max_dd_pct"] > max_dd:
        return False, f"MAXDD>{max_dd}%"
    if m["win_rate_pct"] < min_wr:
        return False, f"WR<{min_wr}%"
    if m["roi_pct"] < min_roi:
        return False, f"ROI<{min_roi}%"
    return True, "PASS"
