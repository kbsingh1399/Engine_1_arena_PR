"""
Master walk-forward validation harness — all 5 strategies x 20 OOS quarters.

  python test_all_20_regimes.py                     # S1..S5 individually + ENSEMBLE
  python test_all_20_regimes.py --sleeves 1 3 5     # subset
  python test_all_20_regimes.py --extended          # 22-asset universe
  python test_all_20_regimes.py --fail-fast         # AGENTS.md Part 10 halt protocol
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from quant_strategy_suite import (
    DataStore, RISK, STRATEGY_NAMES, UNIVERSE_CORE, UNIVERSE_EXTENDED,
    evaluate_gates, run_window,
)

PURGE_HOURS = 72  # t_purge = t_start - 72h (Section 5 / KB Node 8)

WINDOWS = [
    ("W01", "2021-01-01", "2021-03-31", "Post-Halving Bull Expansion"),
    ("W02", "2021-04-01", "2021-06-30", "Historic May 2021 $10B Cascades"),
    ("W03", "2021-07-01", "2021-09-30", "Summer Chop & Liquidity Drain"),
    ("W04", "2021-10-01", "2021-12-31", "BTC 69k ATH Blow-Off"),
    ("W05", "2022-01-01", "2022-03-31", "Fed Hawkish Bear Pivot"),
    ("W06", "2022-04-01", "2022-06-30", "Luna/Terra Death Spiral"),
    ("W07", "2022-07-01", "2022-09-30", "Post-Contagion Dead Drift"),
    ("W08", "2022-10-01", "2022-12-31", "FTX Collapse & Liquidity Void"),
    ("W09", "2023-01-01", "2023-03-31", "SVB Bank Run & Short Squeeze"),
    ("W10", "2023-04-01", "2023-06-30", "SEC Regulatory Crackdown Chop"),
    ("W11", "2023-07-01", "2023-09-30", "August 17 Flash Cascade"),
    ("W12", "2023-10-01", "2023-12-31", "Spot ETF Speculation Rally"),
    ("W13", "2024-01-01", "2024-03-31", "Spot ETF Inflow Explosion"),
    ("W14", "2024-04-01", "2024-06-30", "Bitcoin Halving Chop & Bleed"),
    ("W15", "2024-07-01", "2024-09-30", "Yen Carry Trade Unwind Panic"),
    ("W16", "2024-10-01", "2024-12-31", "US Election Liquidity Expansion"),
    ("W17", "2025-01-01", "2025-03-31", "Altcoin Season Rotation"),
    ("W18", "2025-04-01", "2025-06-30", "Macro De-Risking Volatility"),
    ("W19", "2025-07-01", "2025-09-30", "Autumn Leverage Flush"),
    ("W20", "2025-10-01", "2025-12-31", "2025 Year-End Macro Regime"),
]


def bounds_ms(start: str, end: str) -> tuple[int, int]:
    s = pd.Timestamp(start, tz="UTC")
    e = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(minutes=15)
    return int(s.value // 1_000_000), int(e.value // 1_000_000)


HEAD = (f"{'WIN':<5}{'REGIME':<34}{'TRD':>5}{'ROI%':>9}{'NET$':>10}"
        f"{'MAXDD%':>8}{'WR%':>7}{'PF':>7}{'AVG R':>7}{'GATE':>22}")


def row(win: str, regime: str, m: dict, verdict: str) -> str:
    pf = "inf" if m["profit_factor"] == float("inf") else f"{m['profit_factor']:.2f}"
    return (f"{win:<5}{regime[:33]:<34}{m['trades']:>5}{m['roi_pct']:>9.2f}"
            f"{m['net_pnl']:>10.2f}{m['max_dd_pct']:>8.2f}{m['win_rate_pct']:>7.1f}"
            f"{pf:>7}{m['avg_r']:>7.2f}{verdict:>22}")


def run_sleeve(store: DataStore, label: str, sids: list[int], fail_fast: bool):
    print("\n" + "=" * 122)
    print(f"SLEEVE: {label}   |   strategies = {[STRATEGY_NAMES[i] for i in sids]}")
    print(f"capital=${RISK.initial_capital:,.0f}  base_risk=${RISK.base_risk:.0f}  "
          f"house=${RISK.house_money_risk:.0f}  defense=${RISK.drawdown_defense_risk:.0f}  "
          f"breaker={RISK.drawdown_risk_limit:.1%}  max_concurrent={RISK.max_concurrent}")
    print("=" * 122)
    print(HEAD)
    print("-" * 122)

    rows, all_trades, halted_at = [], [], None
    for win, s, e, regime in WINDOWS:
        s_ms, e_ms = bounds_ms(s, e)
        purge_ms = s_ms - PURGE_HOURS * 3_600_000  # documented; no IS fit occurs
        trades, m, _ = run_window(store, s_ms, e_ms, sids)
        ok, why = evaluate_gates(m)
        print(row(win, regime, m, ("PASS" if ok else f"FAIL:{why}")))
        rec = {"sleeve": label, "window": win, "start": s, "end": e,
               "regime": regime, "t_purge_ms": purge_ms, "passed": ok,
               "gate": why, **m}
        rows.append(rec)
        if len(trades):
            trades = trades.assign(sleeve=label, window=win)
            all_trades.append(trades)
        if fail_fast and not ok:
            halted_at = win
            print(f"\n  >>> PART 10 FAIL-FAST HALT at {win} ({why}). "
                  f"Re-optimise causally on data before {s} and re-run.")
            break

    print("-" * 122)
    df = pd.DataFrame(rows)
    if len(df):
        npass = int(df["passed"].sum())
        print(f"SUMMARY {label}: {npass}/{len(df)} windows passed | "
              f"median ROI {df['roi_pct'].median():.2f}% | "
              f"worst MaxDD {df['max_dd_pct'].max():.2f}% | "
              f"total trades {int(df['trades'].sum())} | "
              f"breakers {int(df['circuit_breaker'].sum())}"
              + (f" | HALTED @ {halted_at}" if halted_at else ""))
    return df, (pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleeves", nargs="*", type=int, default=[1, 2, 3, 4, 5])
    ap.add_argument("--no-ensemble", action="store_true")
    ap.add_argument("--extended", action="store_true")
    ap.add_argument("--fail-fast", action="store_true")
    ap.add_argument("--out", default="results_walkforward")
    args = ap.parse_args()

    out = Path(__file__).resolve().parent / args.out
    out.mkdir(exist_ok=True)

    print("Loading 15m master parquets and computing causal features (once)...")
    store = DataStore(UNIVERSE_EXTENDED if args.extended else UNIVERSE_CORE)
    print(f"Universe: {len(store.symbols)} symbols\n")

    sleeves = [(STRATEGY_NAMES[i], [i]) for i in args.sleeves]
    if not args.no_ensemble and len(args.sleeves) > 1:
        sleeves.append(("ENSEMBLE_S1-S5_SHARED_GOVERNOR", sorted(args.sleeves)))

    scores, trades = [], []
    for label, sids in sleeves:
        sc, tr = run_sleeve(store, label, sids, args.fail_fast)
        scores.append(sc)
        if len(tr):
            trades.append(tr)

    sc = pd.concat(scores, ignore_index=True)
    sc.to_csv(out / "scorecard_all_sleeves_20_windows.csv", index=False)
    if trades:
        pd.concat(trades, ignore_index=True).to_csv(out / "trade_ledger.csv", index=False)

    print("\n" + "=" * 122)
    print("CROSS-SLEEVE PASS MATRIX (Section 6.1 gates)")
    print("=" * 122)
    piv = sc.pivot_table(index="window", columns="sleeve", values="passed", aggfunc="first")
    print(piv.replace({True: "PASS", False: "fail"}).fillna("-").to_string())
    print(f"\nArtifacts -> {out}")
    print("All metrics above were produced live in this run. No cached JSON was read.")


if __name__ == "__main__":
    main()
