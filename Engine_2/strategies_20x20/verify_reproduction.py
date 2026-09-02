#!/usr/bin/env python3
"""Verify that this package reproduces the certified 20/20 results exactly.

Re-runs every strategy on its shipped certified data folder and compares
against certified_results.json (numbers from the certification audit):
    - per-window ROI / DD / win-rate / min-win-R / max-loss-R (rel tol 1e-9)
    - trade / win / loss / scratch counts (exact)
    - total R, final equity, global max DD (rel tol 1e-9)

    python verify_reproduction.py
Exit code 0 iff ALL 30 strategies match the certification exactly.
"""
import os, sys, json, math

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from strategy_engine import run_strategy, N_WIN
from data_loader import load_folder

REL = 1e-9
ABS = 1e-12


def close(a, b):
    return math.isclose(a, b, rel_tol=REL, abs_tol=ABS)


def main():
    cert = json.load(open(os.path.join(HERE, 'certified_results.json')))
    n_ok = 0
    for st in cert['strategies']:
        ref = st
        folder = os.path.join(HERE, ref['data_folder'])
        o, h, l, c = load_folder(folder, verbose=False)
        res = run_strategy(o, h, l, c, ref['cfg'], name=ref['name'])
        problems = []
        if res['npass'] != ref['npass'] or res['npass'] != N_WIN:
            problems.append(f"npass {res['npass']} != {ref['npass']}")
        for key in ('trades', 'wins', 'losses', 'scratches'):
            if res['totals'][key] != ref['totals'][key]:
                problems.append(f"{key} {res['totals'][key]} != {ref['totals'][key]}")
        for key in ('total_r',):
            if not close(res['totals'][key], ref['totals'][key]):
                problems.append(f"{key} {res['totals'][key]!r} != {ref['totals'][key]!r}")
        for key in ('eq_final', 'max_dd', 'min_window_roi', 'max_window_dd'):
            if not close(res['totals'][key], ref[key]):
                problems.append(f"{key} {res['totals'][key]!r} != {ref[key]!r}")
        if len(res['windows']) != len(ref['windows']):
            problems.append('window count mismatch')
        else:
            for wn, rn in zip(res['windows'], ref['windows']):
                for key in ('roi', 'dd', 'wr', 'min_win_r', 'max_loss_r'):
                    if not close(wn[key], rn[key]):
                        problems.append(f"w{wn['win']}.{key} {wn[key]!r} != {rn[key]!r}")
                for key in ('trades', 'wins', 'losses'):
                    if wn[key] != rn[key]:
                        problems.append(f"w{wn['win']}.{key} {wn[key]} != {rn[key]}")
        if problems:
            print(f"{ref['name']}  MISMATCH: {'; '.join(problems[:4])}")
        else:
            t = res['totals']
            print(f"{ref['name']}  VERIFIED  20/20 windows | trades={t['trades']} | "
                  f"min ROI {t['min_window_roi']*100:+.2f}% | max DD {t['max_window_dd']*100:.2f}% "
                  f"| all metrics match certification", flush=True)
            n_ok += 1
    print('=' * 100)
    if n_ok == 30:
        print('REPRODUCTION VERIFIED: all 30 strategies reproduce their certified '
              '20/20 results exactly.')
    else:
        print(f'REPRODUCTION FAILED: {30 - n_ok} strategy/ies deviate from certification.')
    print('=' * 100)
    return 0 if n_ok == 30 else 1


if __name__ == '__main__':
    sys.exit(main())
