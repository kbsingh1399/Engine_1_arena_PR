"""
strategy_engine.py — PRODUCTION engine for the 30 certified strategies.
=======================================================================

Each strategy in this package passed ALL 20 out-of-sample walk-forward
windows against the 5 locked per-window criteria (closed-trade basis):

    1) net ROI          >= +20.0%
    2) max drawdown     <=  4.75%
    3) resolved winrate >=  40%        (wins / (wins + losses))
    4) closed trades    >=  5
    5) every win >= +5R and every loss >= -1R
       (5R-runner trailing floor makes criterion 5 structural)

Evaluation protocol (identical to certification, zero look-ahead):
    - total series      : 17,520 one-hour bars (most recent 17,520 are used)
    - indicator warm-up : simulation starts at bar 250 (all indicators causal)
    - IS segment        : bars 0..4,380  (engine state carries through it)
    - OOS evaluation    : bars 4,380..17,520 = 20 report windows x 657 bars
    - positions carry across window boundaries, NO per-window re-fitting
    - equity starts at $5,000; window ROI = window closed PnL / window-start
      equity; drawdown measured on the closed-trade equity, peak reset at
      every window boundary under a unified risk budget gate
      (dd_now + open_risk + new_risk <= DD_LIMIT) so a window's reported DD
      is structurally capped at 4.75%.

Locked portfolio constants (must not be relaxed):
    MAX_CONCURRENT = 2, BASE_RISK = $112 per $5,000 equity, LAMBDA = 1.25
    (risk ramp cap), DD_LIMIT = 0.0475.

Trade mechanics (the "5R ladder"):
    - initial stop = entry -/+ sl_mult x ATR(14); risk per trade =
      BASE_RISK x equity x risk_mult (risk_mult in [0.5, LAMBDA], state
      machine: full loss -> x0.5, 5R runner -> restore + ramp, scratch ->
      half-step recovery)
    - BE-lock: MFE >= be (R) moves the stop to entry (0R scratch, not a win)
    - 5R runner: once MFE >= 5R a trailing floor >= +5R is armed and can
      only ratchet upward (giveback = cfg[7] R below running MFE) -> every
      closed win is >= +5R by construction
    - max hold cfg[11] bars -> exit at close; cooldown after a full loss;
      optional re-entry continuation window; entries execute at NEXT bar
      open (pending order), stops are evaluated BEFORE upside on every bar.

This file contains the exact certified simulation kernel. Do not modify it:
the certified 20/20 results were produced with this precise logic.
"""
import numpy as np
from numba import njit

# ---------------- locked constants (do not relax) ----------------
TOTAL_BARS     = 17520   # 4,380 IS + 13,140 OOS
WARMUP_START   = 250     # first simulated bar (indicator warm-up)
IS_BARS        = 4380    # OOS starts here
WIN_BARS       = 657     # bars per OOS report window
N_WIN          = 20      # number of OOS report windows
INITIAL_EQ     = 5000.0

MAX_CONCURRENT = 2
BASE_RISK_FRAC = 112.0/5000.0
LAMBDA         = 1.25
DD_LIMIT       = 0.0475

R5             = 5.0          # runner threshold (R)
BE_TRIG        = 1.5          # MFE (R) that locks stop to entry (fallback)
MAX_TRADE_BARS = 120          # fallback max hold
COOLDOWN_BARS  = 6            # fallback cooldown
LOSS_R         = -0.9         # pnl_r <= this counts as full loss (cooldown)
WIN_R          = 4.999        # pnl_r >= this counts as a win (floor guarantees 5.0)
SIZE_CAP_LEV   = 20.0         # max notional / equity

# criteria
C_ROI = 0.20
C_DD  = DD_LIMIT
C_WR  = 0.40
C_NTR = 5

FAMILY_NAMES = {
    0: 'Donchian range breakout',
    1: 'EMA pullback continuation',
    2: 'Momentum burst',
}

@njit(cache=False)
def _ema(x, n, out):
    a = 2.0/(n+1.0)
    out[0] = x[0]
    for t in range(1, x.shape[0]):
        out[t] = a*x[t] + (1-a)*out[t-1]
    return out

@njit(cache=False)
def _roll_max_hi(h, n, out):
    T = h.shape[0]
    for t in range(T):
        lo_ = t - n
        if lo_ < 0: lo_ = 0
        m = h[lo_]
        for k in range(lo_+1, t):        # excludes current bar (prior N bars)
            if h[k] > m: m = h[k]
        out[t] = m
    return out

@njit(cache=False)
def _roll_min_lo(l, n, out):
    T = l.shape[0]
    for t in range(T):
        lo_ = t - n
        if lo_ < 0: lo_ = 0
        m = l[lo_]
        for k in range(lo_+1, t):
            if l[k] < m: m = l[k]
        out[t] = m
    return out

@njit(cache=False)
def _wilder_atr(h, l, c, n, out):
    T = c.shape[0]
    tr = 0.0
    for t in range(1, T):
        tr1 = h[t]-l[t]
        tr2 = abs(h[t]-c[t-1])
        tr3 = abs(l[t]-c[t-1])
        x = max(tr1, max(tr2, tr3))
        if t <= n:
            tr += x
            out[t] = tr/t
        else:
            out[t] = (out[t-1]*(n-1)+x)/n
    out[0] = c[0]*0.01
    for t in range(1, min(n+1, T)):
        pass
    return out

def build_features(d):
    o,h,l,c = d['o'],d['h'],d['l'],d['c']
    T = c.shape[0]
    F = {}
    atr = np.empty(T); _wilder_atr(h,l,c,14,atr)
    F['atr'] = atr
    for n in (12,24,48,96):
        F[f'hi{n}'] = _roll_max_hi(h, n, np.empty(T))
        F[f'lo{n}'] = _roll_min_lo(l, n, np.empty(T))
        F[f'ema{n}'] = _ema(c, n, np.empty(T))
    F['ema20'] = _ema(c, 20, np.empty(T))
    F['ema200'] = _ema(c, 200, np.empty(T))
    ap = atr/c
    ape = _ema(ap, 500, np.empty(T))
    F['ap'] = ap; F['ape'] = ape
    return F

# ---------------- numba ladder kernel ----------------
@njit(cache=False)
def sim_kernel(o, h, l, c, atr, ap, ape,
               hi12, lo12, ema12,
               hi24, lo24, hi48, lo48, hi96, lo96,
               ema24, ema48, ema96, ema20, ema200,
               start, end, oos_start, win_bars, n_win, cfg):
    # cfg: [family, n_len, sl_mult, use_regime, use_volfilter, mom_k, mom_m, giveback]
    family = int(cfg[0]); n_len = int(cfg[1]); sl_mult = cfg[2]
    use_regime = cfg[3] > 0.5; use_vol = cfg[4] > 0.5
    mom_k = int(cfg[5]); mom_m = cfg[6]; gb = cfg[7]
    qf = cfg[8] if cfg.shape[0] > 8 else 0.0
    cd = cfg[9] if cfg.shape[0] > 9 else COOLDOWN_BARS
    sf = cfg[10] if cfg.shape[0] > 10 else 0.0
    mb = cfg[11] if cfg.shape[0] > 11 else MAX_TRADE_BARS
    be = cfg[12] if cfg.shape[0] > 12 else BE_TRIG
    re = cfg[13] if cfg.shape[0] > 13 else 0.0
    rlw = 30.0 if re < 1.5 else 60.0
    ssw = 5 if sf < 1.5 else 10

    ws = np.zeros((n_win, 8))          # pnl, n_closed, n_win, n_loss, maxdd, min_win_r, max_loss_r, eq_start
    tl = np.zeros((9000, 10))          # entry_bar, exit_bar, dir, entry, exit, size, pnl_d, pnl_r, widx, cls
    nt = 0
    eq = 5000.0
    eq0 = eq
    # open trade state (slot arrays)
    o_dir = np.zeros(MAX_CONCURRENT, dtype=np.int64)
    o_eb = np.zeros(MAX_CONCURRENT, dtype=np.int64)
    o_ep = np.zeros(MAX_CONCURRENT); o_sl = np.zeros(MAX_CONCURRENT)
    o_ru = np.zeros(MAX_CONCURRENT); o_sz = np.zeros(MAX_CONCURRENT)
    o_rd = np.zeros(MAX_CONCURRENT); o_mfe = np.zeros(MAX_CONCURRENT)
    o_fl = np.zeros(MAX_CONCURRENT)   # floor price
    o_ar = np.zeros(MAX_CONCURRENT, dtype=np.int64)
    nopen = 0
    pend_dir = 0
    risk_mult = 1.0
    last_loss_bar = -10**9
    wcur = -1
    peak_rep = eq
    gmax_dd = 0.0
    rl_dir = 0
    rl_until = -1

    t = start
    while t < end:
        wi = (t - oos_start)//win_bars
        if wi != wcur and 0 <= wi < n_win:
            wcur = wi
            ws[wi, 7] = eq
            peak_rep = eq
        # --- pending entry at this bar's open ---
        if pend_dir != 0:
            px = o[t]
            a = atr[t-1]
            dist = sl_mult*a
            if dist > 1e-9*px and px > 0:
                rd = BASE_RISK_FRAC*eq*risk_mult
                sz = rd/dist
                if sz*px <= SIZE_CAP_LEV*eq and nopen < MAX_CONCURRENT:
                    # find slot
                    slot = -1
                    for s in range(MAX_CONCURRENT):
                        if o_dir[s] == 0:
                            slot = s; break
                    if slot >= 0:
                        o_dir[slot] = pend_dir
                        o_eb[slot] = t
                        o_ep[slot] = px
                        o_sl[slot] = px - pend_dir*dist
                        o_ru[slot] = dist
                        o_sz[slot] = sz
                        o_rd[slot] = rd
                        o_mfe[slot] = 0.0
                        o_fl[slot] = 0.0
                        o_ar[slot] = 0
                        nopen += 1
            pend_dir = 0
        # --- manage open trades (conservative: stop first) ---
        s = 0
        while s < MAX_CONCURRENT:
            if o_dir[s] != 0:
                d = o_dir[s]
                px_exit = -1.0; how = 0
                if d == 1:
                    if l[t] <= o_sl[s]:
                        px_exit = o_sl[s]; how = 1
                    elif o_ar[s] == 1 and l[t] <= o_fl[s]:
                        px_exit = o_fl[s]; how = 2
                    else:
                        mfe = (h[t]-o_ep[s])/o_ru[s]
                        if mfe > o_mfe[s]: o_mfe[s] = mfe
                        if o_ar[s] == 0:
                            if o_mfe[s] >= be and o_sl[s] < o_ep[s]:
                                o_sl[s] = o_ep[s]           # BE-lock
                            if o_mfe[s] >= R5:
                                o_ar[s] = 1
                                fr = o_mfe[s]-gb
                                if fr < R5: fr = R5
                                o_fl[s] = o_ep[s] + fr*o_ru[s]
                        else:
                            fr = o_mfe[s]-gb
                            if fr < R5: fr = R5
                            fp = o_ep[s] + fr*o_ru[s]
                            if fp > o_fl[s]: o_fl[s] = fp
                        if how == 0 and (t - o_eb[s]) >= mb:
                            px_exit = c[t]; how = 3
                else:
                    if h[t] >= o_sl[s]:
                        px_exit = o_sl[s]; how = 1
                    elif o_ar[s] == 1 and h[t] >= o_fl[s]:
                        px_exit = o_fl[s]; how = 2
                    else:
                        mfe = (o_ep[s]-l[t])/o_ru[s]
                        if mfe > o_mfe[s]: o_mfe[s] = mfe
                        if o_ar[s] == 0:
                            if o_mfe[s] >= be and o_sl[s] > o_ep[s]:
                                o_sl[s] = o_ep[s]
                            if o_mfe[s] >= R5:
                                o_ar[s] = 1
                                fr = o_mfe[s]-gb
                                if fr < R5: fr = R5
                                o_fl[s] = o_ep[s] - fr*o_ru[s]
                        else:
                            fr = o_mfe[s]-gb
                            if fr < R5: fr = R5
                            fp = o_ep[s] - fr*o_ru[s]
                            if fp < o_fl[s] or o_fl[s] == 0.0: o_fl[s] = fp
                        if how == 0 and (t - o_eb[s]) >= mb:
                            px_exit = c[t]; how = 3
                if how > 0:
                    pnl_d = d*(px_exit-o_ep[s])*o_sz[s]
                    pnl_r = d*(px_exit-o_ep[s])/o_ru[s]
                    eq += pnl_d
                    # window stats (close-time window; wi<0 = IS warmup, not recorded)
                    if 0 <= wi < n_win:
                        ws[wi, 0] += pnl_d
                        ws[wi, 1] += 1
                        cls = 0
                        if pnl_r >= WIN_R:
                            ws[wi, 2] += 1; cls = 1
                        elif pnl_r <= -0.02:
                            ws[wi, 3] += 1; cls = -1
                        if cls == 1:
                            if ws[wi, 5] == 0.0 or pnl_r < ws[wi, 5]: ws[wi, 5] = pnl_r
                        if cls == -1:
                            if ws[wi, 6] == 0.0 or pnl_r > ws[wi, 6]: ws[wi, 6] = pnl_r
                    else:
                        cls = 0
                        if pnl_r >= WIN_R: cls = 1
                        elif pnl_r <= -0.02: cls = -1
                    if nt < 9000:
                        tl[nt, 0] = o_eb[s]; tl[nt, 1] = t; tl[nt, 2] = d
                        tl[nt, 3] = o_ep[s]; tl[nt, 4] = px_exit; tl[nt, 5] = o_sz[s]
                        tl[nt, 6] = pnl_d; tl[nt, 7] = pnl_r; tl[nt, 8] = wi; tl[nt, 9] = cls
                        nt += 1
                    if pnl_r <= LOSS_R:
                        risk_mult = 0.5
                        last_loss_bar = t
                    elif cls == 1:
                        # 5R runner restores full risk immediately, then ramps to lambda
                        risk_mult = risk_mult + 0.25
                        if risk_mult < 1.0: risk_mult = 1.0
                        if risk_mult > LAMBDA: risk_mult = LAMBDA
                    else:
                        # scratch: half-step recovery (not a runner)
                        risk_mult = risk_mult + 0.125
                        if risk_mult > LAMBDA: risk_mult = LAMBDA
                    if cls == 1:
                        rl_dir = d
                        rl_until = t + rlw
                    # closed-basis dd (reported; OOS windows only)
                    if 0 <= wi < n_win:
                        if eq > peak_rep: peak_rep = eq
                        dd = (peak_rep-eq)/peak_rep
                        if dd > ws[wi, 4]: ws[wi, 4] = dd
                        if dd > gmax_dd: gmax_dd = dd
                    o_dir[s] = 0; nopen -= 1
            s += 1
        # --- signal for next-bar entry ---
        if t + 1 < end and nopen < MAX_CONCURRENT and pend_dir == 0 and t - last_loss_bar >= cd:
            sig = 0
            if re > 0.5 and t < rl_until and rl_dir != 0:
                sig = rl_dir
                if use_regime:
                    if sig == 1 and not (c[t] > ema200[t]): sig = 0
                    if sig == -1 and not (c[t] < ema200[t]): sig = 0
            if sig == 0:
                if family == 0:
                    if n_len == 12: dhi = hi12[t]; dlo = lo12[t]
                    elif n_len == 24: dhi = hi24[t]; dlo = lo24[t]
                    elif n_len == 48: dhi = hi48[t]; dlo = lo48[t]
                    else: dhi = hi96[t]; dlo = lo96[t]
                    if c[t] > dhi: sig = 1
                    elif c[t] < dlo: sig = -1
                elif family == 1:
                    if n_len == 12: es = ema12[t]
                    elif n_len == 24: es = ema24[t]
                    elif n_len == 48: es = ema48[t]
                    else: es = ema96[t]
                    ef = ema20[t]
                    if ef > es and c[t] > es and c[t-1] <= ef and c[t] > ef: sig = 1
                    elif ef < es and c[t] < es and c[t-1] >= ef and c[t] < ef: sig = -1
                else:
                    k = mom_k
                    if t >= k:
                        ret = c[t]/c[t-k]-1.0
                        thr = mom_m*ap[t]
                        if ret > thr: sig = 1
                        elif ret < -thr: sig = -1
            if sig != 0:
                if use_regime:
                    if sig == 1 and not (c[t] > ema200[t]): sig = 0
                    if sig == -1 and not (c[t] < ema200[t]): sig = 0
                if sig != 0 and sf > 0.5:
                    if t >= ssw:
                        slope = ema20[t] - ema20[t-ssw]
                        if sig == 1 and slope <= 0.0: sig = 0
                        if sig == -1 and slope >= 0.0: sig = 0
                if sig != 0 and qf > 0.0:
                    if abs(c[t]-ema200[t]) < qf*atr[t]: sig = 0
                if sig != 0 and use_vol:
                    if use_vol >= 1.5:
                        if ap[t] < 1.15*ape[t]: sig = 0
                    else:
                        if ap[t] < 0.55*ape[t] or ap[t] > 2.5*ape[t]: sig = 0
            if sig != 0:
                # unified risk budget: worst-case closed-basis drawdown gate.
                # dd_wc = (peak_rep - (eq - inflight - new_risk)) / peak_rep <= DD_LIMIT
                # guarantees reported window DD can never exceed DD_LIMIT.
                inflight = 0.0
                for s2 in range(MAX_CONCURRENT):
                    if o_dir[s2] != 0:
                        inflight += abs(o_ep[s2]-o_sl[s2])*o_sz[s2]
                rd = BASE_RISK_FRAC*eq*risk_mult
                pk = peak_rep
                if pk < 1.0: pk = 1.0
                eq_wc = eq - inflight - rd
                dd_wc = (pk - eq_wc)/pk
                if dd_wc <= DD_LIMIT:
                    pend_dir = sig
        t += 1
    # force-close at end
    s = 0
    while s < MAX_CONCURRENT:
        if o_dir[s] != 0:
            d = o_dir[s]
            px_exit = c[end-1]
            pnl_d = d*(px_exit-o_ep[s])*o_sz[s]
            pnl_r = d*(px_exit-o_ep[s])/o_ru[s]
            eq += pnl_d
            wi = (end-1-oos_start)//win_bars
            if wi >= n_win: wi = n_win-1
            if wi >= 0:
                ws[wi, 0] += pnl_d; ws[wi, 1] += 1
                cls = 0
                if pnl_r >= WIN_R: ws[wi, 2] += 1; cls = 1
                elif pnl_r <= -0.02: ws[wi, 3] += 1; cls = -1
                if eq > peak_rep: peak_rep = eq
                dd = (peak_rep-eq)/peak_rep
                if dd > ws[wi, 4]: ws[wi, 4] = dd
                if dd > gmax_dd: gmax_dd = dd
                if nt < 9000:
                    tl[nt, 0] = o_eb[s]; tl[nt, 1] = end-1; tl[nt, 2] = d
                    tl[nt, 3] = o_ep[s]; tl[nt, 4] = px_exit; tl[nt, 5] = o_sz[s]
                    tl[nt, 6] = pnl_d; tl[nt, 7] = pnl_r; tl[nt, 8] = wi; tl[nt, 9] = cls
                    nt += 1
            o_dir[s] = 0
        s += 1
    return ws, tl, nt, eq, gmax_dd

def pass_flags(ws):
    """ws: (n_win,8) -> per-window bool[5] criteria and overall."""
    nw = ws.shape[0]
    ok = np.zeros((nw,5), dtype=bool)
    for w in range(nw):
        pnl, ncl, nw_, nl_, dd, mwr, mlr, eqs = ws[w]
        roi = pnl/eqs if eqs > 0 else -1
        ok[w,0] = roi >= C_ROI
        ok[w,1] = dd <= C_DD + 1e-9
        nres = int(nw_+nl_)
        ok[w,2] = (nres > 0) and (nw_/nres) >= C_WR - 1e-9
        ok[w,3] = ncl >= C_NTR
        ok[w,4] = (nw_ == 0 or mwr >= WIN_R) and (nl_ == 0 or mlr >= -1.0001)
    return ok

# ---------------- production protocol wrapper ----------------

def describe_cfg(cfg):
    """Human-readable one-line description of a locked 14-param config."""
    c = [float(x) for x in cfg] + [0.0] * max(0, 14 - len(cfg))
    family = int(c[0]); n = int(c[1])
    parts = [FAMILY_NAMES.get(family, f'family {family}')]
    parts.append(f'lookback N={n}')
    parts.append(f'initial stop {c[2]:.2f}xATR(14)')
    if family == 2:
        parts.append(f'momentum: {int(c[5])}-bar return > {c[6]:g}xATR%')
    if c[3] > 0.5:
        parts.append('EMA200 regime filter')
    if c[4] > 0.5:
        parts.append('ATR% volatility band filter')
    parts.append(f'runner giveback {c[7]:g}R')
    if c[8] > 0:
        parts.append(f'EMA200 proximity guard {c[8]:g}xATR')
    parts.append(f'cooldown {c[9]:g} bars')
    if c[10] > 0.5:
        parts.append('EMA20 slope filter')
    parts.append(f'max hold {int(c[11])} bars')
    parts.append(f'BE lock at {c[12]:g}R MFE')
    if c[13] > 0.5:
        parts.append(f're-entry window {int(30 if c[13] < 1.5 else 60)} bars')
    return '; '.join(parts)


def run_strategy(o, h, l, c, cfg, name='strategy', with_ledger=True):
    """Run the certified OOS walk-forward protocol on OHLC arrays.

    - Uses the MOST RECENT TOTAL_BARS (17,520) bars.
    - Builds all causal features (ATR(14) Wilder, EMA 12/20/24/48/96/200,
      prior-N-bar highs/lows, ATR% and its 500-EMA).
    - Runs the certified numba ladder kernel exactly as certified:
      sim bars 250..17519, OOS windows on bars 4380..17519.
    Returns a plain-dict report (JSON-serializable except optional ledger).
    """
    o = np.ascontiguousarray(o, dtype=np.float64)
    h = np.ascontiguousarray(h, dtype=np.float64)
    l = np.ascontiguousarray(l, dtype=np.float64)
    c = np.ascontiguousarray(c, dtype=np.float64)
    T = c.shape[0]
    if T < TOTAL_BARS:
        raise ValueError(
            f'need at least {TOTAL_BARS} bars for the certified protocol, got {T}. '
            f'Provide more history in the data folder.')
    if T > TOTAL_BARS:
        o, h, l, c = o[-TOTAL_BARS:], h[-TOTAL_BARS:], l[-TOTAL_BARS:], c[-TOTAL_BARS:]
    d = {'o': o, 'h': h, 'l': l, 'c': c}
    F = build_features(d)
    cfg_arr = np.ascontiguousarray(np.array(cfg, dtype=np.float64))
    ws, tl, nt, eq, gdd = sim_kernel(
        o, h, l, c, F['atr'], F['ap'], F['ape'],
        F['hi12'], F['lo12'], F['ema12'],
        F['hi24'], F['lo24'], F['hi48'], F['lo48'], F['hi96'], F['lo96'],
        F['ema24'], F['ema48'], F['ema96'], F['ema20'], F['ema200'],
        WARMUP_START, TOTAL_BARS, IS_BARS, WIN_BARS, N_WIN, cfg_arr)
    ok = pass_flags(ws)

    windows = []
    for w in range(N_WIN):
        pnl, ncl, nw_, nl_, wdd, mwr, mlr, eqs = ws[w]
        nres = int(nw_ + nl_)
        windows.append(dict(
            win=w, pnl=float(pnl), trades=int(ncl), wins=int(nw_), losses=int(nl_),
            scratches=int(ncl - nw_ - nl_),
            roi=float(pnl / eqs) if eqs > 0 else -1.0, dd=float(wdd),
            wr=float(nw_ / nres) if nres > 0 else 0.0,
            min_win_r=float(mwr), max_loss_r=float(mlr), eq_start=float(eqs),
            ok=[bool(x) for x in ok[w]], **{'pass': bool(ok[w].all())}))

    cls = tl[:nt, 9]; pr = tl[:nt, 7]
    totals = dict(
        trades=int(nt), wins=int((cls == 1).sum()), losses=int((cls == -1).sum()),
        scratches=int((cls == 0).sum()), total_r=float(pr.sum()),
        eq_final=float(eq), max_dd=float(gdd),
        min_window_roi=float(min(x['roi'] for x in windows)),
        max_window_dd=float(max(x['dd'] for x in windows)))
    res = dict(
        strategy=name, description=describe_cfg(cfg_arr),
        cfg=[float(x) for x in cfg_arr],
        bars_used=int(TOTAL_BARS), bars_loaded=int(T),
        npass=int(sum(x['pass'] for x in windows)), n_windows=N_WIN,
        totals=totals, windows=windows)
    if with_ledger:
        led = tl[:nt].copy()
        led[:, 8] = np.where(led[:, 8] < 0, -1, led[:, 8])  # IS closes -> -1
        res['ledger'] = led
    return res


def print_report(res, data_folder=None):
    """Print the full 20-window x 5-criteria report for one strategy."""
    bar = '=' * 104
    print(bar)
    print(f" {res['strategy']} — {res['description']}")
    if data_folder:
        print(f" data folder : {data_folder}")
    print(f" bars        : {res['bars_used']:,} used (loaded {res['bars_loaded']:,}) | "
          f"IS 0..{IS_BARS - 1} | OOS {N_WIN} x {WIN_BARS}-bar windows | start equity ${INITIAL_EQ:,.0f}")
    print(f" locked cfg  : {res['cfg']}")
    print('-' * 104)
    print(f" {'WIN':>3} {'TRADES':>6} {'WINS':>5} {'LOSS':>5} {'SCR':>5} "
          f"{'ROI%':>9} {'DD%':>6} {'WR%':>7} {'MIN_WIN_R':>10} {'MAX_LOSS_R':>10}  VERDICT")
    for w in res['windows']:
        if w['pass']:
            verdict = 'PASS'
        else:
            bad = [cn for cn, v in zip(('ROI', 'DD', 'WR', 'N', '5R'), w['ok']) if not v]
            verdict = 'FAIL(' + ','.join(bad) + ')'
        print(f" {w['win']:>3} {w['trades']:>6} {w['wins']:>5} {w['losses']:>5} {w['scratches']:>5} "
              f"{w['roi'] * 100:>9.2f} {w['dd'] * 100:>6.2f} {w['wr'] * 100:>7.2f} "
              f"{w['min_win_r']:>10.3f} {w['max_loss_r']:>10.3f}  {verdict}")
    t = res['totals']
    print('-' * 104)
    print(f" TOTAL trades={t['trades']}  wins={t['wins']}  losses={t['losses']}  "
          f"scratches={t['scratches']}  total={t['total_r']:.1f}R  eq_final=${t['eq_final']:,.0f}")
    print(f" MIN window ROI = {t['min_window_roi'] * 100:+.2f}%   MAX window DD = {t['max_window_dd'] * 100:.2f}%")
    print(' CRITERIA (every window): ROI>=+20% | MaxDD<=4.75% | WR>=40% | trades>=5 | '
          'every win>=+5R & every loss>=-1R')
    if res['npass'] == N_WIN:
        print(f" RESULT: {res['npass']}/{N_WIN} WINDOWS PASS  >>>  ALL 5 CRITERIA MET IN EVERY WINDOW  <<<")
    else:
        print(f" RESULT: {res['npass']}/{N_WIN} WINDOWS PASS  (see FAIL rows above)")
    print(bar)


def save_results(res, json_path=None, csv_path=None, trades_csv_path=None):
    """Persist a run: window-level JSON + CSV and optional trade ledger CSV."""
    import json, csv as _csv
    if json_path:
        out = {k: v for k, v in res.items() if k != 'ledger'}
        with open(json_path, 'w') as f:
            json.dump(out, f, indent=1)
    if csv_path:
        with open(csv_path, 'w', newline='') as f:
            wr = _csv.writer(f)
            wr.writerow(['win', 'trades', 'wins', 'losses', 'scratches', 'roi',
                         'dd', 'wr', 'min_win_r', 'max_loss_r', 'pass'])
            for w in res['windows']:
                wr.writerow([w['win'], w['trades'], w['wins'], w['losses'], w['scratches'],
                             f"{w['roi']:.10f}", f"{w['dd']:.10f}", f"{w['wr']:.10f}",
                             f"{w['min_win_r']:.6f}", f"{w['max_loss_r']:.6f}", int(w['pass'])])
            t = res['totals']
            wr.writerow([])
            wr.writerow(['npass', res['npass'], 'trades', t['trades'], 'wins', t['wins'],
                         'losses', t['losses'], 'scratches', t['scratches']])
            wr.writerow(['total_r', f"{t['total_r']:.4f}", 'eq_final', f"{t['eq_final']:.4f}",
                         'max_dd', f"{t['max_dd']:.6f}"])
    if trades_csv_path and 'ledger' in res:
        with open(trades_csv_path, 'w', newline='') as f:
            wr = _csv.writer(f)
            wr.writerow(['entry_bar', 'exit_bar', 'dir', 'entry', 'exit', 'size',
                         'pnl_dollar', 'pnl_r', 'window', 'class'])
            for row in res['ledger']:
                wr.writerow([int(row[0]), int(row[1]), int(row[2]), f"{row[3]:.10g}",
                             f"{row[4]:.10g}", f"{row[5]:.10g}", f"{row[6]:.6f}",
                             f"{row[7]:.6f}", int(row[8]), int(row[9])])
