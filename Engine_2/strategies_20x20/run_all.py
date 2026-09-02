#!/usr/bin/env python3
"""Run ALL 30 certified strategies in one process.

    python run_all.py                 # shipped certified data folders
    python run_all.py --data-root R   # use <R>/data_S00 ... <R>/data_S29
    python run_all.py --full          # print the full 20-window report each

Exit code 0 iff every strategy passes 20/20 windows.
"""
import os, sys, json, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from strategy_engine import run_strategy, print_report, N_WIN
from data_loader import load_folder


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', default=os.path.abspath(os.path.join(HERE, "..", "binance_backtesting_data")),
                    help='path to backtesting data folder (default: binance_backtesting_data)')
    ap.add_argument('--data-root', default=None,
                    help='root folder containing data_S00 ... data_S29')
    ap.add_argument('--full', action='store_true', help='full per-window report')
    ap.add_argument('--out', default=os.path.join(HERE, 'results'))
    a = ap.parse_args()

    cert = json.load(open(os.path.join(HERE, 'certified_results.json')))
    rows = []
    for st in cert['strategies']:
        if a.data_root:
            folder = os.path.join(a.data_root, st['data_folder'])
        elif a.data:
            folder = a.data
        else:
            folder = os.path.join(HERE, st['data_folder'])
        o, h, l, c = load_folder(folder, verbose=False)
        res = run_strategy(o, h, l, c, st['cfg'], name=st['name'])
        rows.append(res)
        t = res['totals']
        verdict = 'PASS' if res['npass'] == N_WIN else 'FAIL'
        print(f"{st['name']}  {verdict}  {res['npass']}/{N_WIN} windows | "
              f"trades={t['trades']:5d} | min ROI {t['min_window_roi']*100:+7.2f}% | "
              f"max DD {t['max_window_dd']*100:5.2f}% | total {t['total_r']:+9.1f}R",
              flush=True)
        if a.full:
            print_report(res, data_folder=folder)

    npass_all = sum(1 for r in rows if r['npass'] == N_WIN)
    print('=' * 100)
    print(f"MASTER RESULT: {npass_all}/30 strategies pass 20/20 OOS windows x 5 criteria")
    print('=' * 100)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, 'all_results.json'), 'w') as f:
        json.dump([{k: v for k, v in r.items() if k != 'ledger'} for r in rows], f, indent=1)
    return 0 if npass_all == 30 else 1


if __name__ == '__main__':
    sys.exit(main())
