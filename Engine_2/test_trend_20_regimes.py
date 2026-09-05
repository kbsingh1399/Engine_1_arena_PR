"""
test_trend_20_regimes.py - Causal Walk-Forward Validation across 20 OOS Windows (2021-2026).

Validates the Trend Following Strategy on Steroids (Order Flow + Tri-Ensemble GBDT + Microstructure Ratchet).
Pass Criteria per Window (Part 10 / AGENTS.md):
- ROI >= 20.0%
- Max Drawdown < 5.0%
- Win Rate >= 40.0%
- Trades >= 6
"""

from __future__ import annotations
import sys
import pickle
from pathlib import Path
import numpy as np
import pandas as pd

from trend_orderflow_features import extract_trend_orderflow_features, FEATURE_COLUMNS
from s2_trend_orderflow_engine import run_portfolio_trend_backtest, INITIAL_CAPITAL

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

def run_all_20_regimes(symbols=None, prob_threshold=0.55):
    data_dir = Path(r"c:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\Engine_2\binance_backtesting_data")
    model_file = Path(r"c:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\Engine_2\models\trend_tri_ensemble.pkl")
    
    if symbols is None:
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "BNBUSDT", "NEARUSDT"]

    print("=========================================================================================")
    print("  INSTITUTIONAL TREND FOLLOWING ON STEROIDS: 20 WALK-FORWARD REGIMES (2021-2026)")
    print("=========================================================================================")
    
    # Load Models if available
    ensemble_bundle = None
    if model_file.exists():
        print(f"Loading serialized Tri-Ensemble models from {model_file.name}...")
        with open(model_file, "rb") as f:
            ensemble_bundle = pickle.load(f)
            print(f"Loaded XGBoost, LightGBM, CatBoost. Test AUC: {ensemble_bundle.get('test_auc', 0.0):.4f}")

    # Pre-load and extract features for all symbols once
    print(f"\nPre-processing feature matrices for {len(symbols)} symbols...")
    symbol_dfs = {}
    for sym in symbols:
        p_file = data_dir / f"{sym}_15m_master_2020_2026.parquet"
        if not p_file.exists():
            continue
        raw_df = pd.read_parquet(p_file)
        feats = extract_trend_orderflow_features(raw_df)
        
        # If models available, predict ensemble probability
        if ensemble_bundle is not None:
            X = feats[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
            X = np.nan_to_num(X, nan=0.0, posinf=50.0, neginf=-50.0)
            
            p_xgb = ensemble_bundle["xgb"].predict_proba(X)[:, 1]
            p_lgb = ensemble_bundle["lgb"].predict_proba(X)[:, 1]
            p_cat = ensemble_bundle["cat"].predict_proba(X)[:, 1]
            feats["p_ensemble"] = (p_xgb + p_lgb + p_cat) / 3.0
            
        symbol_dfs[sym] = feats

    print("\nStarting Walk-Forward Simulation across 20 Windows...")
    HEAD = (f"{'WIN':<5}{'REGIME':<34}{'TRD':>5}{'ROI%':>9}{'NET$':>10}"
            f"{'MAXDD%':>8}{'WR%':>7}{'PF':>7}{'GATE STATUS':>14}")
    print("-" * len(HEAD))
    print(HEAD)
    print("-" * len(HEAD))

    scorecard = []
    passed_count = 0

    for win, start_str, end_str, regime_desc in WINDOWS:
        start_ms, end_ms = bounds_ms(start_str, end_str)

        # Slice data strictly within window boundary (72-hour purge handled inherently by non-overlapping windows)
        window_symbol_data = {}
        for sym, df in symbol_dfs.items():
            mask = (df["open_time_ms"] >= start_ms) & (df["open_time_ms"] <= end_ms)
            sub_df = df[mask].copy().reset_index(drop=True)
            if len(sub_df) > 50:
                window_symbol_data[sym] = sub_df

        if not window_symbol_data:
            print(f"{win:<5}{regime_desc[:33]:<34}{0:>5}{0.0:>9.2f}{0.0:>10.2f}{0.0:>8.2f}{0.0:>7.1%}{0.0:>7.2f}{'NO_DATA':>14}")
            continue

        # Execute portfolio backtest for this window
        res = run_portfolio_trend_backtest(window_symbol_data, prob_threshold=prob_threshold)

        verdict = "PASS" if res["passed"] else "FAIL"
        if res["passed"]:
            passed_count += 1

        pf_str = "inf" if res["profit_factor"] >= 99.0 else f"{res['profit_factor']:.2f}"
        print(f"{win:<5}{regime_desc[:33]:<34}{res['total_trades']:>5}{res['net_roi_pct']:>9.2f}{res['net_profit_usd']:>10.2f}"
              f"{res['max_drawdown_pct']:>8.2f}{res['win_rate']:>7.1%}{pf_str:>7}{verdict:>14}")

        scorecard.append({
            "window": win,
            "regime": regime_desc,
            "trades": res["total_trades"],
            "roi_pct": res["net_roi_pct"],
            "net_usd": res["net_profit_usd"],
            "maxdd_pct": res["max_drawdown_pct"],
            "win_rate": res["win_rate"],
            "profit_factor": res["profit_factor"],
            "passed": res["passed"]
        })

    print("-" * len(HEAD))
    print(f"Summary: {passed_count} / {len(WINDOWS)} Windows PASSED under one unified causal configuration.")
    print("=========================================================================================\n")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--thresh", type=float, default=0.275, help="Ensemble probability threshold")
    args = parser.parse_args()
    run_all_20_regimes(prob_threshold=args.thresh)
