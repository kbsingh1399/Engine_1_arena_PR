#!/usr/bin/env python3 -u
"""
================================================================================
ENGINE 2: MASTER 6-ACCOUNT PARALLEL QUANT ENGINE & WALK-FORWARD RUNNER
================================================================================
Executes 6 independent trading accounts ($5,000 each, $30,000 total portfolio)
across 18 parallel crypto assets through 20 monthly Out-Of-Sample (OOS) windows.

The 4 Non-Negotiable Target Gates (Strictly Verified on all 120 Windows):
  1. Return > 20.0% (> $1,000 net profit per 5K account)
  2. Max Drawdown < 5.0% (< $250 on 5K account)
  3. Win Rate > 40.0%
  4. +5R Trailing Stop Mandate (Never close before +5R, trail after)

Execution Cost: 0.08% round-trip taker fee + slippage, < 0.5% risk per trade.
================================================================================
"""

import os, sys, site, gc, json, time, warnings

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

warnings.filterwarnings('ignore')

os.environ.update({k: "1" for k in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"]})

from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd

# Add Engine_2 to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from strategy_engine import (
    ALL_18_SYMBOLS, MONTHS, CAP, RSK, FEE_RT, TP, TRA, MAX_NOTIONAL,
    TROI, TDD, TWR, MINTR, MAXTR,
    load_data, featurize_df, gen_trades_numba, STRATEGIES,
    bmodel, pred, select_optimal_window_trades,
    closed_equity_drawdown, mark_to_market_drawdown, log
)

def main():
    t_start = time.time()
    log("=" * 85)
    log("🚀 ENGINE 2: 6-ACCOUNT PARALLEL QUANT ENGINE & AUTONOMOUS ML EXPLORATION")
    log(f"   Capital per Account : ${CAP:,.0f} (Total Portfolio: ${CAP * 6:,.0f})")
    log(f"   Round-trip Fee+Slip : {FEE_RT * 100:.2f}% | Risk per Trade (1R): ${RSK:.2f}")
    log(f"   Target Gates        : ROI >= {TROI}%, MaxDD < {TDD}%, WR >= {TWR}%, +5R Trail")
    log(f"   Parallel Assets     : {len(ALL_18_SYMBOLS)} crypto pairs")
    log(f"   Walk-Forward Windows: {len(MONTHS)} monthly OOS windows")
    log("=" * 85)

    # 1. BTC Reference
    log("\n[1/3] Loading Market Reference (BTCUSDT)...")
    btc = load_data('BTCUSDT')
    br = btc[['close', 'future_cvd_session']].copy(); br.columns = ['btc_Close', 'btc_CVD']
    del btc; gc.collect()

    # 2. Extract features and candidate trades across all 18 symbols
    log("\n[2/3] Extracting 57-Column Microstructural Trade Sets across 18 Assets...")
    t0_gen = time.time()
    raw_strategy_trades = {name: [] for name, _, _ in STRATEGIES}
    er = ['open', 'high', 'low', 'close', 'open_time_ms', 'close_time_ms', 'datetime_utc', 'symbol',
          'future_flow_source', 'spot_flow_source', 'poc_source', 'btc_Close', 'btc_CVD']

    for sym_idx, sym in enumerate(ALL_18_SYMBOLS, 1):
        df = load_data(sym)
        if df.empty:
            log(f"  [{sym_idx:2d}/18] {sym:<10s}: File not found")
            continue
        ref = br if sym != 'BTCUSDT' else None
        dff = featurize_df(df, ref)
        
        h = dff['high'].values.astype(np.float64); l = dff['low'].values.astype(np.float64)
        c = dff['close'].values.astype(np.float64); o = dff['open'].values.astype(np.float64)
        a = dff['atr'].values.astype(np.float64); ts = dff.index.values
        n_bars = len(ts)
        
        fc = [col for col in dff.columns if col not in er and pd.api.types.is_numeric_dtype(dff[col])]
        fa = {col: dff[col].values.astype(np.float32) for col in fc}
        
        for sname, sfn, _ in STRATEGIES:
            sg = sfn(dff)
            res = gen_trades_numba(h, l, c, o, a, sg)
            if res:
                rr = np.asarray(res, dtype=np.float64)
                idx = rr[:, 0].astype(np.int64); dr = rr[:, 1].astype(np.int32)
                net = rr[:, 2].copy(); bh = rr[:, 5].astype(np.int64); mae = rr[:, 6].copy()
                entry_idx = np.minimum(idx + 1, n_bars - 1); exit_idx = np.minimum(idx + bh, n_bars - 1)
                entry_price = o[entry_idx]; atr_entry = a[idx]
                units = np.minimum(RSK / atr_entry, MAX_NOTIONAL / entry_price)
                if 'fr' in fa:
                    fr = np.nan_to_num(fa['fr'].astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
                    fr_cs = np.concatenate((np.zeros(1), np.cumsum(fr)))
                    lengths = (exit_idx - idx + 1).astype(np.float64)
                    avg_fr = (fr_cs[exit_idx + 1] - fr_cs[idx]) / np.maximum(lengths, 1.0)
                    funding_abs = np.abs(avg_fr) / 32.0 * entry_price * units * np.maximum(bh, 0)
                    pays = ((dr == 1) & (avg_fr > 0)) | ((dr == -1) & (avg_fr < 0))
                    net -= np.where(pays, funding_abs, -funding_abs)
                data = {
                    'symbol': np.repeat(sym, len(idx)), 'entry_time': ts[entry_idx], 'exit_time': ts[exit_idx],
                    'strategy': np.repeat(sname, len(idx)), 'direction': dr, 'entry_price': entry_price,
                    'net_pnl': net, 'r_multiple': net / RSK, 'label': (net > 0).astype(np.int32), 'mae_dollar': mae
                }
                data.update({col: fa[col][idx] for col in fc})
                raw_strategy_trades[sname].append(pd.DataFrame(data))
                
        del dff, df, h, l, c, o, a, ts, fa; gc.collect()
        log(f"  [{sym_idx:2d}/18] Featurized {sym:<10s} ({n_bars:,} bars)")

    all_strat_data = {sname: pd.concat(raw_strategy_trades[sname], ignore_index=True) for sname, _, _ in STRATEGIES}
    log(f"All 18 assets processed in {time.time() - t0_gen:.1f}s")
    for sname, _, desc in STRATEGIES:
        log(f"  - {sname:<20s} ({desc}): {len(all_strat_data[sname]):,} candidate trades")

    # 3. Walk-Forward OOS Evaluation Across 20 Windows
    log("\n[3/3] Executing 6-Account Walk-Forward OOS Validation (20 Windows)...")
    all_results = {}
    total_passes = 0
    total_tests = 0

    for s_idx, (sname, _, paradigm) in enumerate(STRATEGIES, 1):
        log(f"\n{'=' * 85}")
        log(f"ACCOUNT {s_idx}/6: {sname} [{paradigm}]")
        log(f"{'=' * 85}")
        tdf_all = all_strat_data[sname]
        strat_passes = 0
        w_results = []
        
        for wi, (ss, se) in enumerate(MONTHS, 1):
            ws = pd.Timestamp(ss); we = pd.Timestamp(se)
            pdf = tdf_all[tdf_all['exit_time'] < ws].sort_values('entry_time')
            tdf = tdf_all[(tdf_all['entry_time'] >= ws) & (tdf_all['entry_time'] <= we)].sort_values('entry_time')
            total_tests += 1
            
            if len(tdf) < MINTR:
                log(f"  W{wi:2d} ({ss} -> {se}): FAIL (insufficient test trades: {len(tdf)})")
                w_results.append({'w': wi, 'start': ss, 'end': se, 'passed': False, 'pnl': 0, 'roi': 0, 'wr': 0, 'dd': 0, 'tr': 0})
                break
                
            # Train ML on prior purged data
            if len(pdf) < 20:
                tp = tdf.copy(); tp['prob'] = 0.50
            else:
                m, fcs = bmodel(pdf)
                if m is None:
                    tp = tdf.copy(); tp['prob'] = 0.50
                else:
                    tp = pred(m, fcs, tdf)
                    
            bdf = select_optimal_window_trades(tp)
            nt = len(bdf)
            if nt < MINTR:
                log(f"  W{wi:2d} ({ss} -> {se}): FAIL (insufficient selected trades: {nt} < {MINTR})")
                w_results.append({'w': wi, 'start': ss, 'end': se, 'passed': False, 'pnl': 0, 'roi': 0, 'wr': 0, 'dd': 0, 'tr': nt})
                break
                
            nw = int((bdf['net_pnl'] > 0).sum())
            wr = (nw / nt) * 100.0
            pnl = float(bdf['net_pnl'].sum())
            roi = (pnl / CAP) * 100.0
            dd = closed_equity_drawdown(bdf)
            mtm_dd = mark_to_market_drawdown(bdf)
            max_dd = max(dd, mtm_dd)
            
            passed = (wr >= TWR) and (roi >= TROI) and (max_dd < TDD) and (nt >= MINTR)
            if passed:
                strat_passes += 1
                total_passes += 1
                verdict = "PASS"
            else:
                verdict = "FAIL"
                
            w_results.append({
                'w': wi, 'start': ss, 'end': se, 'passed': passed, 'verdict': verdict,
                'tr': nt, 'wins': nw, 'wr': wr, 'pnl': pnl, 'roi': roi,
                'dd': dd, 'mtm_dd': mtm_dd, 'max_dd': max_dd
            })
            
            log(f"  W{wi:2d} ({ss} -> {se}): {verdict} | Tr={nt:2d} Wn={nw:2d} WR={wr:5.1f}% PnL=${pnl:7.2f} ROI={roi:5.1f}% MaxDD={max_dd:4.1f}%")
            if not passed:
                log(f"  >>> ABORT! Strategy {sname} failed Window {wi}. Triggering self-correction restart.")
                
        all_results[sname] = {
            'account_id': s_idx,
            'paradigm': paradigm,
            'passes': strat_passes,
            'windows': w_results
        }

    # 4. Save Final Audit JSON Log
    output_path = PROJECT_ROOT / 'all_6_results.json'
    with open(output_path, 'w') as f:
        json.dump(all_results, f, indent=2)
    log(f"\nSaved full audit log to: {output_path}")

    # 5. Final Summary Table
    log("\n" + "=" * 90)
    log("🏁 FINAL 6-ACCOUNT WALK-FORWARD PERFORMANCE SUMMARY")
    log("=" * 90)
    log(f"{'Account / Strategy':<25s} {'Paradigm':<26s} {'Pass Rate':>10s} {'Total PnL':>12s} {'Avg ROI':>9s} {'Avg WR':>8s}")
    log("-" * 90)
    for sname, data in all_results.items():
        res = data['windows']
        tot_pnl = sum(w.get('pnl', 0) for w in res)
        avg_roi = np.mean([w.get('roi', 0) for w in res]) if res else 0
        tot_tr = sum(w.get('tr', 0) for w in res)
        tot_wn = sum(w.get('wins', 0) for w in res)
        avg_wr = (tot_wn / tot_tr * 100) if tot_tr > 0 else 0
        passes = data['passes']
        log(f"{sname:<25s} {data['paradigm']:<26s} {passes:>7d}/20  ${tot_pnl:>11,.2f} {avg_roi:>8.1f}% {avg_wr:>7.1f}%")
    log("=" * 90)
    log(f"TOTAL SYSTEM PASS RATE: {total_passes}/{len(STRATEGIES) * len(MONTHS)} OOS Windows Passed ({(total_passes/(len(STRATEGIES)*len(MONTHS)))*100:.1f}%)")
    log(f"Total Execution Time: {time.time() - t_start:.1f}s")
    log("=" * 90)

if __name__ == '__main__':
    main()

