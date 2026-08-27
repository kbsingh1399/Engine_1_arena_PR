#!/usr/bin/env python3 -u
"""
================================================================================
WF20 CONCEPT SCREEN — multi-concept candidate universe for S1 ensemble
================================================================================
Defines ~17 CAUSAL market-microstructure concepts (all using only current-bar
features), unions their candidate trades (one owner per bar via priority),
simulates each with the canonical $35-1R tiered engine, and prints
per-concept / per-quarter expectancy statistics.

The pooled universe is cached for the ensemble engine (wf20_ensemble.py).
Screening is ANALYTICS ONLY: the ensemble keeps ALL concepts in the universe
and lets per-window in-sample-trained models decide which to trust — so no
design decision uses post-window-1 data.
================================================================================
"""
import os, sys, warnings, gc
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
warnings.filterwarnings('ignore')
os.environ.update({k: "1" for k in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                                    "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"]})
from pathlib import Path
import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import strategy_engine as se
import wf20_autonomous as wf

CACHE = wf.CACHE_DIR

# ── 17 causal concepts; each returns a boolean array (current-bar values) ──
# Signature: fn(st) -> (long_mask, short_mask)
def c_liq_cascade(st):
    pb, lm, zg = 0.12, 1.0, 0.05
    mc, p8, llr, lsr, zc = st['mc'], st['p8'], st['llr'], st['lsr'], st['zc20']
    L = (mc > 0) & (p8 < -pb) & ((llr > lm) | (zc > zg))
    S = (mc < 0) & (p8 > pb) & ((lsr > lm) | (zc < -zg))
    return L, S

def c_liq_extreme(st):
    mc, p8, llr, lsr = st['mc'], st['p8'], st['llr'], st['lsr']
    L = (mc > 0) & (p8 < -0.25) & (llr > 3.0)
    S = (mc < 0) & (p8 > 0.25) & (lsr > 3.0)
    return L, S

def c_funding_squeeze(st):
    zfr, zc10, mc = st['zfr'], st['zc10'], st['mc']
    L = (zfr < -1.5) & (zc10 > 0.3)
    S = (zfr > 1.5) & (zc10 < -0.3)
    return L, S

def c_cvd_divergence(st):
    p21, zc20 = st['p21'], st['zc20']
    L = (p21 < -0.6) & (zc20 > 0.5)
    S = (p21 > 0.6) & (zc20 < -0.5)
    return L, S

def c_oi_surge(st):
    oid, mc, vr5 = st['oid'], st['mc'], st['vr5']
    L = (oid > 0.005) & (mc > 0) & (vr5 > 1.2)
    S = (oid < -0.005) & (mc < 0) & (vr5 > 1.2)
    return L, S

def c_squeeze_breakout(st):
    vr, p8 = st['vr'], st['p8']
    L = (vr < -0.8) & (p8 > 0.5)
    S = (vr < -0.8) & (p8 < -0.5)
    return L, S

def c_deep_pullback(st):
    mc, p50, rsi = st['mc'], st['p50'], st['rsi']
    L = (mc > 0) & (p50 < -1.2) & (rsi < 40)
    S = (mc < 0) & (p50 > 1.2) & (rsi > 60)
    return L, S

def c_flow_imbalance(st):
    fi, vr5 = st['flow_imbalance'], st['vr5']
    L = (fi > 0.5) & (vr5 > 1.5)
    S = (fi < -0.5) & (vr5 > 1.5)
    return L, S

def c_ls_extreme(st):
    zls, mc = st['zls'], st['mc']
    L = (zls < -1.5) & (mc > 0)
    S = (zls > 1.5) & (mc < 0)
    return L, S

def c_trend_mom(st):
    # pullback in strong macro trend + CVD aligned
    mc, p8, zc10 = st['mc'], st['p8'], st['zc10']
    L = (mc > 0) & (p8 < -0.15) & (zc10 > 0.2) & (st['trend_strength'] > 0.8)
    S = (mc < 0) & (p8 > 0.15) & (zc10 < -0.2) & (st['trend_strength'] > 0.8)
    return L, S

def c_vol_expansion(st):
    # entering vol expansion with direction (regime EXPANSION onset)
    vratio, p8, rsi = st['vol_ratio'], st['p8'], st['rsi']
    L = (vratio > 1.3) & (p8 > 0.2) & (rsi > 50) & (st['mc'] > 0)
    S = (vratio > 1.3) & (p8 < -0.2) & (rsi < 50) & (st['mc'] < 0)
    return L, S

def c_cvd_momentum(st):
    # strong CVD momentum same side as macro trend
    mc, zc10, zc20 = st['mc'], st['zc10'], st['zc20']
    L = (mc > 0) & (zc10 > 1.2) & (zc20 > 0.6)
    S = (mc < 0) & (zc10 < -1.2) & (zc20 < -0.6)
    return L, S

def c_rsi_extreme(st):
    rsi, p8, mc = st['rsi'], st['p8'], st['mc']
    L = (rsi < 30) & (mc > 0) & (p8 < 0)
    S = (rsi > 70) & (mc < 0) & (p8 > 0)
    return L, S

def c_funding_cvd(st):
    # funding + CVD + OI all aligned (crowded positioning unwind setups)
    zfr, zc10, oid = st['zfr'], st['zc10'], st['oid']
    L = (zfr < -0.8) & (zc10 > 0.5) & (oid < 0)
    S = (zfr > 0.8) & (zc10 < -0.5) & (oid > 0)
    return L, S

def c_btc_confirm(st, btc_mc=None):
    # signal only when BTC macro trend agrees (cross-asset confirmation)
    mc, p8, zc = st['mc'], st['p8'], st['zc20']
    if btc_mc is None:
        return (mc > 0) & (p8 < -0.1), (mc < 0) & (p8 > 0.1)
    L = (mc > 0) & (btc_mc > 0) & (p8 < -0.1) & (zc > 0)
    S = (mc < 0) & (btc_mc < 0) & (p8 > 0.1) & (zc < 0)
    return L, S

def c_depth_imbalance(st):
    zb, za = st['zbid_qty'], st['zask_qty']
    diff = zb - za
    L = diff > 1.5
    S = diff < -1.5
    return L, S

# ── multi-timeframe concepts (30-day structure + 15m trigger) ──
def c_mtf_reversion(st):
    # deep 30d value + short-term stabilization
    d30, p8, low, high, r7 = (st['d_ema30d'], st['p8'], st['dist_30d_low'],
                              st['dist_30d_high'], st['ret_7d'])
    L = (d30 < -1.5) & (p8 > -0.1) & (low < 0.3) & (r7 < -0.05)
    S = (d30 > 1.5) & (p8 < 0.1) & (high > -0.3) & (r7 > 0.05)
    return L, S

def c_mtf_trend(st):
    # 30-day trend + 15m pullback in trend direction
    d30, ts_, p8 = st['d_ema30d'], st['trend_strength'], st['p8']
    L = (d30 > 0.5) & (ts_ > 0.5) & (p8 < -0.1)
    S = (d30 < -0.5) & (ts_ > 0.5) & (p8 > 0.1)
    return L, S

def c_range_position(st):
    # compression at 30d range extremes (coil)
    low, high, ar = st['dist_30d_low'], st['dist_30d_high'], st['atr_regime']
    L = (low < 0.2) & (ar < 0.9) & (st['mc'] > 0)
    S = (high > -0.2) & (ar < 0.9) & (st['mc'] < 0)
    return L, S

def c_ema_stack(st):
    # trend-continuation proxy: price above (below) all EMAs, macro aligned,
    # near the short EMA (not extended)
    p8, p50, ms, mc = st['p8'], st['p50'], st['macro_spread'], st['mc']
    L = (mc > 0) & (p8 > 0) & (p50 > 0) & (ms > 0) & (np.abs(p8) < 0.5)
    S = (mc < 0) & (p8 < 0) & (p50 < 0) & (ms < 0) & (np.abs(p8) < 0.5)
    return L, S

CONCEPTS = [
    ('liq_cascade', c_liq_cascade), ('liq_extreme', c_liq_extreme),
    ('funding_squeeze', c_funding_squeeze), ('cvd_divergence', c_cvd_divergence),
    ('oi_surge', c_oi_surge), ('squeeze_breakout', c_squeeze_breakout),
    ('deep_pullback', c_deep_pullback), ('flow_imbalance', c_flow_imbalance),
    ('ls_extreme', c_ls_extreme), ('trend_mom', c_trend_mom),
    ('vol_expansion', c_vol_expansion), ('cvd_momentum', c_cvd_momentum),
    ('rsi_extreme', c_rsi_extreme), ('funding_cvd', c_funding_cvd),
    ('btc_confirm', c_btc_confirm), ('depth_imbalance', c_depth_imbalance),
    ('mtf_reversion', c_mtf_reversion), ('mtf_trend', c_mtf_trend),
    ('range_position', c_range_position),
    ('ema_stack', c_ema_stack),
]


MTF_COLS = ['d_ema30d', 'mom_30d', 'dist_30d_high', 'dist_30d_low',
            'atr_regime', 'ret_7d']


def mtf_frame(o, h, l, c, atr, ts):
    """Multi-timeframe causal features (30d = 2880 x 15m bars)."""
    p = pd.Series(c)
    a = pd.Series(atr)
    out = pd.DataFrame(index=pd.DatetimeIndex(ts))
    out['d_ema30d'] = (p - p.ewm(span=2880, min_periods=576).mean()) / a
    out['mom_30d'] = p / p.shift(2880) - 1.0
    out['dist_30d_high'] = (p - pd.Series(h).rolling(2880, min_periods=288).max()) / a
    out['dist_30d_low'] = (p - pd.Series(l).rolling(2880, min_periods=288).min()) / a
    out['atr_regime'] = a / a.rolling(2880, min_periods=288).mean()
    out['ret_7d'] = p / p.shift(672) - 1.0
    return out.replace([np.inf, -np.inf], 0.0).fillna(0.0)


def build_pooled_universe(sym_states, btc_mc_by_symbol):
    rows = []
    for sym, st in sym_states.items():
        n = len(st['mc'])
        # Full feature accessor: all 35 causal features + raw OHLC/atr
        f = {col: st['feats'][:, j] for j, col in enumerate(st['fcs'])}
        f.update({'o': st['o'], 'h': st['h'], 'l': st['l'], 'c': st['c'],
                  'atr': st['atr'], 'mc': st['mc'], 'p8': st['p8'],
                  'llr': st['llr'], 'lsr': st['lsr'], 'zc20': st['zc20']})
        mtf = mtf_frame(st['o'], st['h'], st['l'], st['c'], st['atr'], st['ts'])
        for col in MTF_COLS:
            f[col] = mtf[col].to_numpy(np.float32)
        L = np.zeros(n, bool); S = np.zeros(n, bool)
        owner_l = np.full(n, -1, np.int8); owner_s = np.full(n, -1, np.int8)
        btc_mc_aligned = btc_mc_by_symbol['all'].reindex(
            pd.DatetimeIndex(st['ts'])).ffill().fillna(0).to_numpy()
        active = []
        for ci, (name, fn) in enumerate(CONCEPTS):
            try:
                if name == 'btc_confirm':
                    ll, ss = fn(f, btc_mc_aligned)
                else:
                    ll, ss = fn(f)
            except Exception as e:
                print(f'  !! concept {name} FAILED: {type(e).__name__}: {e}')
                continue
            ll = np.asarray(ll, bool); ss = np.asarray(ss, bool)
            active.append((name, int(ll.sum()), int(ss.sum())))
            new_l = ll & (owner_l < 0)
            new_s = ss & (owner_s < 0)
            owner_l[new_l] = ci; owner_s[new_s] = ci
            L |= new_l; S |= new_s
        zeros = [nm for nm, nl, ns in active if nl + ns == 0]
        if zeros:
            print(f'  {sym}: ZERO-COUNT concepts: {zeros}', flush=True)
        else:
            print(f'  {sym}: all {len(active)} concepts active '
                  f'(total L={int(L.sum())} S={int(S.sum())})', flush=True)
        sig = np.zeros(n, np.int32)
        cown = np.full(n, -1, np.int8)
        sig[L] = 1; cown[L] = owner_l[L]
        ss_ = S & ~L
        sig[ss_] = -1; cown[ss_] = owner_s[ss_]
        h, l, c, o, a, ts = st['h'], st['l'], st['c'], st['o'], st['atr'], st['ts']
        res = se.gen_trades_tiered(h, l, c, o, a, sig)
        if not res:
            continue
        rr = np.asarray(res, dtype=np.float64)
        idx = rr[:, 0].astype(np.int64)
        entry_idx = np.minimum(idx + 1, n - 1)
        exit_idx = np.minimum(idx + 1 + rr[:, 5].astype(np.int64), n - 1)
        rec = pd.DataFrame({
            'symbol': np.repeat(sym, len(idx)),
            'entry_time': ts[entry_idx], 'exit_time': ts[exit_idx],
            'direction': rr[:, 1].astype(np.int32),
            'net_pnl': rr[:, 2], 'r_multiple': rr[:, 3],
            'label': rr[:, 4].astype(np.int32),
            'mae_dollar': np.clip(rr[:, 6], 0.0, wf.RSK * 1.2),
            'concept': cown[idx].astype(np.int32),
            'concept_name': np.array([CONCEPTS[int(c)][0] for c in cown[idx]]),
        })
        for j, col in enumerate(st['fcs']):
            rec[col] = st['feats'][idx, j]
        for col in MTF_COLS:
            rec[col] = mtf[col].to_numpy(np.float32)[idx]
        rows.append(rec)
    uni = pd.concat(rows, ignore_index=True).replace([np.inf, -np.inf], 0.0).fillna(0.0)
    return uni


def main():
    import time
    t0 = time.time()
    print('building symbol states (cached) ...', flush=True)
    btc = se.load_symbol_data('BTCUSDT')
    br = btc[['Close', 'CVD']].copy(); br.columns = ['btc_Close', 'btc_CVD']
    # BTC macro direction per bar, aligned per symbol (causal: value at bar t uses data <= t)
    e50 = btc['Close'].ewm(span=50, min_periods=10).mean()
    e200 = btc['Close'].ewm(span=200, min_periods=20).mean()
    btc_mc_series = pd.Series(np.where(e50 > e200, 1, -1), index=btc.index)
    sym_states = {}
    for sym in se.ALL_18_SYMBOLS:
        st = wf.build_symbol_state(sym, br)
        if st is not None:
            sym_states[sym] = st
    del btc, br
    print(f'states ready in {time.time()-t0:.0f}s', flush=True)

    print('building pooled concept universe ...', flush=True)
    uni = build_pooled_universe(sym_states, {'all': btc_mc_series})
    uni.to_parquet(CACHE / 'uni_pooled.parquet')
    print(f'universe: {len(uni):,} candidate trades across {uni["concept"].nunique()} concepts '
          f'({time.time()-t0:.0f}s)', flush=True)
    print('base: WR', round(uni['label'].mean() * 100, 1), '%  avgR', round(uni['r_multiple'].mean(), 3))

    uni['q'] = pd.to_datetime(uni['entry_time']).dt.to_period('Q')
    quarters = [f'{y}Q{q}' for y in range(2021, 2026) for q in range(1, 5)]

    print('\n================ PER-CONCEPT (full 2021-2025) ================')
    sub = uni[(uni['entry_time'] >= '2021-01-01') & (uni['entry_time'] < '2026-01-01')]
    g = sub.groupby('concept_name').agg(n=('label', 'size'), WR=('label', 'mean'),
                                        avgR=('r_multiple', 'mean'))
    g = g.sort_values('avgR', ascending=False)
    print((g * 100).round(1).to_string(), '\n')

    print('================ PER-QUARTER POOLED (2021-2025) ================')
    g2 = sub.groupby('q').agg(n=('label', 'size'), WR=('label', 'mean'),
                              avgR=('r_multiple', 'mean'))
    print(g2.round(3).to_string(), '\n')

    print('================ PER-CONCEPT x QUARTER avgR (2021-2025) ================')
    piv = sub.pivot_table(index='concept_name', columns='q', values='r_multiple', aggfunc='mean')
    print(piv.round(3).to_string(), '\n')

    print(f'DONE in {time.time()-t0:.0f}s')


if __name__ == '__main__':
    main()
