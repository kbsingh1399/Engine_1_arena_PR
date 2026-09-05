"""
test_symmetric_20_regimes.py - Walk-Forward Evaluation of Symmetric Order Flow Trend Strategy across 20 Regimes.
"""

from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

# Add local path
sys.path.insert(0, str(Path(__file__).parent))

from s3_symmetric_orderflow_trend import run_symmetric_portfolio_backtest
from test_trend_20_regimes import bounds_ms, WINDOWS

def run_symmetric_all_20_regimes(symbols=None):
    data_dir = Path(r"c:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\Engine_2\binance_backtesting_data")
    if symbols is None:
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "BNBUSDT", "NEARUSDT"]

    print("=========================================================================================")
    print("  SYMMETRIC ORDER FLOW TREND ENGINE (130 QUANT VIDEO SYNTHESIS): 20 REGIMES (2021-2026)")
    print("=========================================================================================")

    print(f"Pre-loading master parquets for {len(symbols)} symbols...")
    symbol_dfs = {}
    for sym in symbols:
        p_file = data_dir / f"{sym}_15m_master_2020_2026.parquet"
        if not p_file.exists():
            continue
        df = pd.read_parquet(p_file)
        symbol_dfs[sym] = df

    HEAD = (f"{'WIN':<5}{'REGIME':<34}{'TRD':>5}{'ROI%':>9}{'NET USD':>10}"
            f"{'MAXDD%':>8}{'WR%':>7}{'PF':>7}{'GATE STATUS':>14}")
    print("-" * len(HEAD))
    print(HEAD)
    print("-" * len(HEAD))

    passed_count = 0
    total_net_usd = 0.0

    for win, start_str, end_str, regime_desc in WINDOWS:
        start_ms, end_ms = bounds_ms(start_str, end_str)

        window_data = {}
        for sym, df in symbol_dfs.items():
            mask = (df["open_time_ms"] >= start_ms) & (df["open_time_ms"] <= end_ms)
            sub_df = df[mask].copy().reset_index(drop=True)
            if len(sub_df) > 50:
                window_data[sym] = sub_df

        if not window_data:
            print(f"{win:<5}{regime_desc[:33]:<34}{0:>5}{0.0:>9.2f}{0.0:>10.2f}{0.0:>8.2f}{0.0:>7.1%}{0.0:>7.2f}{'NO_DATA':>14}")
            continue

        res = run_symmetric_portfolio_backtest(window_data)

        verdict = "PASS" if res["passed"] else "FAIL"
        if res["passed"]:
            passed_count += 1
        total_net_usd += res["net_profit_usd"]

        pf_str = "inf" if res["profit_factor"] >= 99.0 else f"{res['profit_factor']:.2f}"
        print(f"{win:<5}{regime_desc[:33]:<34}{res['total_trades']:>5}{res['net_roi_pct']:>9.2f}{res['net_profit_usd']:>10.2f}"
              f"{res['max_drawdown_pct']:>8.2f}{res['win_rate']:>7.1%}{pf_str:>7}{verdict:>14}")

    print("-" * len(HEAD))
    print(f"Summary: {passed_count} / {len(WINDOWS)} Windows PASSED | Total Net Profit: {total_net_usd:.2f} USD")
    print("=========================================================================================\n")

if __name__ == "__main__":
    run_symmetric_all_20_regimes()
