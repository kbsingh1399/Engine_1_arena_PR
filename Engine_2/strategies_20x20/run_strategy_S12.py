#!/usr/bin/env python3
# =============================================================================
#  STRATEGY S12 — certified 20/20 OOS walk-forward
# =============================================================================
#  Logic   : EMA pullback continuation; lookback N=24; initial stop 1.60xATR(14); EMA200 regime filter; runner giveback 1.8R; cooldown 6 bars; max hold 160 bars; BE lock at 1.5R MFE; re-entry window 30 bars
#
#  Certified result on the shipped dataset (data_12/):
#     20/20 windows pass | min window ROI +22.11% | max window DD 4.48% | 552 trades | total +2117.5R
#
#  USAGE — the ONLY thing you need to change is the data folder:
#     1) reproduce the certified 20/20 result:
#            python run_strategy_S12.py
#     2) run on YOUR backtesting files:
#            python run_strategy_S12.py --data "path/to/your/backtesting/files"
#        or edit DATA_FOLDER below.
#     The folder must contain CSV/TSV/TXT exports with open/high/low/close
#     columns (timestamp optional, volume ignored) and at least 17,520
#     one-hour bars; the most recent 17,520 bars are used.
# =============================================================================
import os, sys, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from strategy_engine import run_strategy, print_report, save_results, N_WIN
from data_loader import load_folder

DATA_FOLDER = r"C:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\Engine_2\binance_backtesting_data"
                                                  #     backtesting files folder

STRATEGY_NAME = "S12"

# Locked, certified configuration (do not modify — this exact parameter set
# passed all 20 OOS windows x 5 criteria):
#   cfg[0]  family        : 0=Donchian breakout  1=EMA pullback  2=momentum burst
#   cfg[1]  n_len         : signal lookback (bars)
#   cfg[2]  sl_mult       : initial stop distance = sl_mult x ATR(14)
#   cfg[3]  use_regime    : 1 = EMA200 trend filter on
#   cfg[4]  use_volfilter : 1 = ATR% volatility band filter on
#   cfg[5]  mom_k         : momentum lookback in bars (family 2 only)
#   cfg[6]  mom_m         : momentum threshold x ATR% (family 2 only)
#   cfg[7]  giveback      : 5R-runner trailing giveback (R)
#   cfg[8]  qf            : EMA200 proximity guard (xATR), 0 = off
#   cfg[9]  cd            : cooldown bars after a full loss
#   cfg[10] sf            : 1 = EMA20 slope filter on
#   cfg[11] mb            : max holding bars
#   cfg[12] be            : break-even lock trigger (R of MFE)
#   cfg[13] re            : re-entry continuation (0=off 1=30 bars 2=60 bars)
CONFIG = [1.0, 24.0, 1.6, 1.0, 0.0, 24.0, 2.0, 1.8, 0.0, 6.0, 0.0, 160.0, 1.5, 1.0]


def main():
    ap = argparse.ArgumentParser(description="Certified strategy S12 (20/20 OOS)")
    ap.add_argument('--data', default=DATA_FOLDER, help='backtesting files folder')
    ap.add_argument('--out', default=os.path.join(HERE, 'results'), help='output directory')
    ap.add_argument('--no-save', action='store_true', help='do not write result files')
    a = ap.parse_args()

    o, h, l, c = load_folder(a.data)
    res = run_strategy(o, h, l, c, CONFIG, name=STRATEGY_NAME)
    print_report(res, data_folder=a.data)

    if not a.no_save:
        os.makedirs(a.out, exist_ok=True)
        jp = os.path.join(a.out, 'run_S12.json')
        cp = os.path.join(a.out, 'run_S12.csv')
        tp = os.path.join(a.out, 'trades_S12.csv')
        save_results(res, jp, cp, tp)
        print(f" saved: {jp}")
        print(f" saved: {cp}")
        print(f" saved: {tp}")

    return 0 if res['npass'] == N_WIN else 1


if __name__ == '__main__':
    sys.exit(main())
