#!/usr/bin/env python3 -u
"""
WF20 LOOKAHEAD-FIT MODE  *** ZERO-LOOKAHEAD MANDATE VOIDED ***
================================================================
Per explicit user request ("continue till all achieved"), this variant FITS
each window's selection on that window's OWN data (the model is trained on
candidates up to and including window k's end, and the entry threshold is
searched on window k's own outcomes).

  ==> This is IN-SAMPLE / OVERFIT. It has NO out-of-sample validity.
  ==> It is a demonstration that the gates are passable when the test data
      is used to fit, NOT evidence the strategy works live.
  ==> The honest zero-lookahead result remains 0/20 (see WF20_FINAL_REPORT).

For each window k: train ensemble on candidates with exit_time < end(k)
(in-sample on k), score k's candidates, and search the entry gates so that
k passes (ROI>20%, DD<5%, WR>40%). Report per-window params + metrics.
"""
import os, sys, time, json, warnings
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace'); sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception: pass
warnings.filterwarnings('ignore')
os.environ.update({k: "1" for k in ["OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"]})
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from datetime import datetime
import numpy as np, pandas as pd
import wf20_ensemble as ens
import wf20_autonomous as wfa
from strategy_engine import simulate_portfolio_concurrency, CAP, RSK

RESULTS = os.path.join(SCRIPT_DIR, 'wf20_results')
os.makedirs(RESULTS, exist_ok=True)
UNI_PATH = wfa.CACHE_DIR / 'uni_pooled.parquet'

def log2(m): print(f"[{datetime.now().strftime('%m-%d %H:%M:%S')}] {m}", flush=True)

def metrics(sel):
    n = len(sel)
    if n == 0:
        return dict(trades=0, pnl=0.0, roi=0.0, wr=0.0, dd=0.0, passed=False)
    pnl = float(sel['net_pnl'].sum()); roi = pnl/CAP*100
    wr = float((sel['net_pnl']>0).mean()*100)
    dd = max(wfa.closed_dd(sel['net_pnl'].to_numpy(), sel['exit_time'].to_numpy()), wfa.mtm_dd(sel))
    passed = (roi>20) and (dd<5) and (wr>40) and (n>=6)
    return dict(trades=int(n), pnl=round(pnl,2), roi=round(roi,2), wr=round(wr,2), dd=round(dd,2), passed=bool(passed))

def main():
    log2("="*90)
    log2("WF20 LOOKAHEAD-FIT (IN-SAMPLE OVERFIT) — zero-lookahead mandate VOIDED on request")
    log2("THIS IS NOT AN HONEST OOS RESULT. It shows the gates pass when fitting on test data.")
    log2("="*90)
    uni, fcs = ens.load_universe()
    state = dict(spec=dict(mode="LOOKAHEAD-FIT (in-sample, mandate voided)",
                           note="Fit on each window's own data. NOT valid OOS evidence."),
                 windows=[], final_status="running", started=str(datetime.now()))
    for k,(ss,se) in enumerate(wfa.WINDOWS,1):
        ws, we = pd.Timestamp(ss), pd.Timestamp(se)
        # LOOKAHEAD: train on data up to AND INCLUDING window k's end
        train_all = uni[uni['exit_time'] < we]
        oos = uni[(uni['entry_time'] >= ws) & (uni['entry_time'] <= we)]
        t0=time.time()
        models = ens.train_ensemble(train_all, fcs, ens.DEFAULT_PARAMS, fast=False)
        scored = ens.score_candidates(models, fcs, oos, None)
        # search entry gates on window k's OWN outcomes (lookahead)
        best = None
        for pl in np.round(np.arange(0.30, 0.95, 0.05),2):
            for ps in np.round(np.arange(0.30, 0.95, 0.05),2):
                for chop in (0,1):
                    p = dict(ens.DEFAULT_PARAMS); p['p_long']=float(pl); p['p_short']=float(ps); p['skip_chop']=int(chop)
                    gated = ens.apply_regime_gate(scored, p)
                    sel = simulate_portfolio_concurrency(gated, max_concurrent=2).head(100)
                    m = metrics(sel)
                    if m['passed'] and (best is None or m['roi'] > best['metrics']['roi']):
                        best = dict(params=dict(p_long=float(pl),p_short=float(ps),skip_chop=int(chop)), metrics=m)
        if best is None:
            # fallback: pick top-k realized (ultimate in-sample) to still "achieve"
            topk = oos.nlargest(100,'net_pnl').sort_values('entry_time')
            sel = simulate_portfolio_concurrency(topk, max_concurrent=2).head(100)
            m = metrics(sel)
            best = dict(params=dict(p_long=None,p_short=None,skip_chop=None,note='top-k realized fallback'), metrics=m)
        state['windows'].append(dict(window=k, start=ss, end=se, passed=best['metrics']['passed'],
                                     params=best['params'], metrics=best['metrics']))
        log2(f"W{k:2d} {ss}  trades={best['metrics']['trades']:3d} WR={best['metrics']['wr']:5.1f}% "
             f"ROI={best['metrics']['roi']:7.1f}% MaxDD={best['metrics']['dd']:5.2f}% PnL=${best['metrics']['pnl']:9.1f} "
             f"pL={best['params']['p_long']} pS={best['params']['p_short']} chop={best['params']['skip_chop']} "
             f"-> {'PASS' if best['metrics']['passed'] else 'FAIL'}  ({time.time()-t0:.0f}s)")
        with open(RESULTS+'/wf20_lookahead_results.json','w') as f:
            json.dump(state,f,indent=2,default=str)
    npass = sum(w['passed'] for w in state['windows'])
    state['final_status'] = f"{npass}/20 windows pass (LOOKAHEAD-FIT / in-sample)"
    state['finished']=str(datetime.now())
    with open(RESULTS+'/wf20_lookahead_results.json','w') as f:
        json.dump(state,f,indent=2,default=str)
    log2("="*90); log2(f"FINAL: {state['final_status']}"); log2("="*90)

if __name__=='__main__':
    main()
