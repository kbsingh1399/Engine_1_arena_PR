"""
================================================================================
TEST ALL 20 REGIMES — SEQUENTIAL OOS WALK-FORWARD EVALUATION HARNESS
================================================================================
Evaluates the S1 Liquidation-Cascade strategy (both sleeves) across the 20
canonical quarterly OOS windows (2021-2025) with the 72-hour causal purge gap.

Pass criteria per window (institutional gates):
  1. Net ROI            > 20.0 %
  2. Max Drawdown       <  5.0 %   (bar-by-bar mark-to-market equity)
  3. Win Rate           > 40.0 %
  4. Min 5R objective with 5R trailing stop  (enforced in strategy geometry)
  5. Trade count        >= 5

Integrity:
  * One invariant configuration for all windows (no lookup tables, no w_idx
    branching, no in-run OOS parameter search).
  * Every window runs its FULL quarter (no early termination on profit).
  * Windows start flat (stronger than the 72h purge) and force-close at the
    final bar with full frictions.
  * All metrics are computed live in this run and printed to console.

Usage:  python Engine_2/test_all_20_regimes.py [--sleeve A|B|both] [--csv out.csv]
================================================================================
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import numpy as np
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import s1_liquidation_cascade as s1  # noqa: E402

# --------------------------------------------------------------------------- #
# The 20 canonical OOS windows (quarterly, 2021-2025)
# --------------------------------------------------------------------------- #
OOS_WINDOWS = [
    ("W01", "2021-01-01", "2021-04-01", "Q1 2021 - Early Bull Expansion"),
    ("W02", "2021-04-01", "2021-07-01", "Q2 2021 - Post-May-2021 Crash Rebound"),
    ("W03", "2021-07-01", "2021-10-01", "Q3 2021 - Mid-Bull Consolidation"),
    ("W04", "2021-10-01", "2022-01-01", "Q4 2021 - ATH Distribution & Blow-off"),
    ("W05", "2022-01-01", "2022-04-01", "Q1 2022 - Macro Top Breakdown"),
    ("W06", "2022-04-01", "2022-07-01", "Q2 2022 - LUNA / 3AC Contagion Crash"),
    ("W07", "2022-07-01", "2022-10-01", "Q3 2022 - Bear Market Chop"),
    ("W08", "2022-10-01", "2023-01-01", "Q4 2022 - FTX Insolvency Capitulation"),
    ("W09", "2023-01-01", "2023-04-01", "Q1 2023 - Early Rebound Cycle"),
    ("W10", "2023-04-01", "2023-07-01", "Q2 2023 - Spring Consolidation"),
    ("W11", "2023-07-01", "2023-10-01", "Q3 2023 - Summer Liquidity Vacuum"),
    ("W12", "2023-10-01", "2024-01-01", "Q4 2023 - Pre-ETF Expansion"),
    ("W13", "2024-01-01", "2024-04-01", "Q1 2024 - Spot ETF Inflow Impulse"),
    ("W14", "2024-04-01", "2024-07-01", "Q2 2024 - Post-Halving Volatility"),
    ("W15", "2024-07-01", "2024-10-01", "Q3 2024 - Summer Rangebound Drift"),
    ("W16", "2024-10-01", "2025-01-01", "Q4 2024 - Post-Election Breakout"),
    ("W17", "2025-01-01", "2025-04-01", "Q1 2025 - High-Beta Altcoin Cycle"),
    ("W18", "2025-04-01", "2025-07-01", "Q2 2025 - Macro Liquidity Compression"),
    ("W19", "2025-07-01", "2025-10-01", "Q3 2025 - Structural Redistribution"),
    ("W20", "2025-10-01", "2026-01-01", "Q4 2025 - Post-Oct-2025 Flash Cascade Era"),
]

PASS_ROI = 20.0      # %
PASS_MAXDD = 5.0     # %
PASS_WR = 40.0       # %
PASS_TRADES = 5
PURGE_HOURS = 72


def run_sleeve(universe, sleeve, verbose=True, meta_events=None):
    rows = []
    for name, d0, d1, label in OOS_WINDOWS:
        t0 = int(pd.Timestamp(d0, tz="UTC").timestamp() * 1000)
        t1 = int(pd.Timestamp(d1, tz="UTC").timestamp() * 1000)
        meta_masks = None
        if sleeve == "B_META":
            model = s1.train_meta_model(meta_events, t0 - PURGE_HOURS * 3600 * 1000)
            if model is None:
                print(f"  {name}: insufficient pre-window training events — skipped")
                continue
            meta_masks = s1.meta_mask_for_window(universe, model, t0, t1, sleeve="B")
        r = s1.simulate_window(universe, t0, t1,
                               "B" if sleeve == "B_META" else sleeve,
                               meta_masks=meta_masks)
        ok = (r["roi"] * 100 > PASS_ROI and r["max_dd"] * 100 < PASS_MAXDD
              and r["wr"] * 100 > PASS_WR and r["n"] >= PASS_TRADES)
        row = {
            "Window": name, "Period": label,
            "ROI %": round(r["roi"] * 100, 2),
            "MaxDD %": round(r["max_dd"] * 100, 2),
            "WinRate %": round(r["wr"] * 100, 1),
            "Trades": r["n"],
            "PF": round(r["pf"], 2) if np.isfinite(r["pf"]) else float("inf"),
            "NetR": round(sum(t["r"] for t in r["trades"]), 2),
            "RESULT": "PASS" if ok else "FAIL",
        }
        rows.append(row)
        if verbose:
            print(f"  {name} [{label}]:  ROI {row['ROI %']:>7.2f}% | MaxDD {row['MaxDD %']:>5.2f}% | "
                  f"WR {row['WinRate %']:>5.1f}% | Trades {row['Trades']:>3d} | "
                  f"PF {row['PF']:>6.2f} | NetR {row['NetR']:>7.2f} | {row['RESULT']}")
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleeve", default="all", choices=["A", "B", "B_META", "all"])
    ap.add_argument("--csv", default=None)
    args = ap.parse_args()

    print("=" * 110)
    print("ENGINE 2 - S1 LIQUIDATION CASCADE STRATEGY - 20 OOS WINDOW WALK-FORWARD EVALUATION")
    print(f"Universe: {len(s1.SYMBOLS)} Binance USDT-M perpetuals | 15m bars | "
          f"frictions: {s1.CFG['FEE_BPS']:.0f} bps fee, "
          f"{s1.CFG['SLIP_ENTRY_BPS']:.0f} bps entry slip, "
          f"{s1.CFG['SLIP_STOP_BPS']:.0f} bps stop slip")
    print(f"Risk governor: capital ${s1.CFG['CAPITAL']:,.0f} | base risk ${s1.CFG['BASE_RISK']:.0f} | "
          f"house ${s1.CFG['HOUSE_RISK']:.0f} | defense ${s1.CFG['DEFENSE_RISK']:.0f} | "
          f"max {s1.CFG['MAX_CONCURRENT']} concurrent | hard DD {s1.CFG['HARD_DD']*100:.1f}%")
    print(f"Exit mandate: min +{s1.CFG['TRAIL_TRIGGER_R']:.0f}R objective, "
          f"trail {s1.CFG['TRAIL_TRIGGER_R']:.0f}R-{s1.CFG['TRAIL_GIVEBACK_R']:.0f}R | "
          f"purge {PURGE_HOURS}h | windows start flat | full-quarter evaluation")
    print("=" * 110)

    t0 = time.time()
    print("[1/3] Building causal features for the 18-asset universe ...")
    universe = s1.load_universe()
    print(f"      done in {time.time()-t0:.1f}s "
          f"({sum(len(v) for v in universe.values()):,} symbol-bars)")

    sleeves = ["A", "B", "B_META"] if args.sleeve == "all" else [args.sleeve]
    names = {"A": "SLEEVE A - S1 Cascade Absorption (repository-faithful confluence)",
             "B": "SLEEVE B - Deep-Discount Cascade Composite (rule-based best edge)",
             "B_META": "SLEEVE B-META - Meta-Labeled Composite (LightGBM, causal walk-forward)"}

    meta_events = None
    if "B_META" in sleeves:
        print("[2/3] Building meta-label training events (exact triple-barrier labels) ...")
        meta_events = s1.build_meta_events(universe, sleeve="B")
        print(f"      {len(meta_events):,} labeled events "
              f"(base rate {meta_events.y.mean()*100:.1f}% positive)")

    results = {}
    for sleeve in sleeves:
        print("-" * 110)
        print(f"[3/3] {names[sleeve]}")
        print("-" * 110)
        df = run_sleeve(universe, sleeve, meta_events=meta_events)
        results[sleeve] = df
        n_pass = int((df["RESULT"] == "PASS").sum())
        print("-" * 110)
        print(df.to_string(index=False))
        print("-" * 110)
        print(f"TOTAL: {n_pass}/20 windows PASS "
              f"(gates: ROI>{PASS_ROI}%, MaxDD<{PASS_MAXDD}%, WR>{PASS_WR}%, trades>={PASS_TRADES})")
        print(f"Aggregate: ROI sum {df['ROI %'].sum():.2f}% | median MaxDD {df['MaxDD %'].median():.2f}% | "
              f"median WR {df['WinRate %'].median():.1f}% | total trades {df['Trades'].sum()}")
        print()

    if args.csv:
        out = pd.concat([d.assign(sleeve=k) for k, d in results.items()])
        out.to_csv(args.csv, index=False)
        print(f"Saved per-window results to {args.csv}")
    print(f"[harness complete in {time.time()-t0:.1f}s]")


if __name__ == "__main__":
    main()
