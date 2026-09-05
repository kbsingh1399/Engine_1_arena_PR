"""
run_expanding_walkforward_ml.py - Expanding Walk-Forward ML Training Engine across 20 OOS Regimes.

Strict Quantitative Directive:
For every OOS Window k (W01 to W20):
1. In-Sample Training: The model is trained exclusively on all historical data strictly PRIOR to Window k:
   t_train <= t_start(k) - 72 hours (Purged Embargo Boundary).
2. Model Training: LightGBM / GBDT fits on accumulated history with class-balanced weighting.
3. Causal Probability Calibration: The decision threshold P* is calibrated strictly on in-sample quantiles (e.g. 85th percentile).
4. Out-of-Sample Testing: The freshly trained model is evaluated on unseen Window k.
5. Microstructure Trailing Ratchet & Risk Governor: Evaluates PnL, Win Rate, Drawdown, and gate criteria.
"""

from __future__ import annotations
import sys
import time
from pathlib import Path
from typing import Dict, List, Any
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import roc_auc_score

# Add local path
sys.path.insert(0, str(Path(__file__).parent))

from trend_orderflow_features import extract_trend_orderflow_features, generate_trend_triple_barrier_labels, FEATURE_COLUMNS
from s3_symmetric_orderflow_trend import simulate_symmetric_trade, INITIAL_CAPITAL, BASE_RISK, HOUSE_MONEY_RISK, DEFENSE_RISK, DRAWDOWN_LIMIT_PCT, MAX_CONCURRENT_POSITIONS
from test_trend_20_regimes import bounds_ms, WINDOWS

PURGE_MS = 72 * 3600 * 1000  # 72 hours purge boundary

def prepare_master_data(symbols=None) -> Dict[str, pd.DataFrame]:
    data_dir = Path(r"c:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\Engine_2\binance_backtesting_data")
    if symbols is None:
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "BNBUSDT", "NEARUSDT"]

    print(f"Pre-processing feature matrices and causal labels for {len(symbols)} symbols...")
    symbol_data = {}
    for sym in symbols:
        p_file = data_dir / f"{sym}_15m_master_2020_2026.parquet"
        if not p_file.exists():
            continue
        raw_df = pd.read_parquet(p_file)
        feats = extract_trend_orderflow_features(raw_df)
        labels = generate_trend_triple_barrier_labels(feats, r_target=2.0, r_stop=1.0, atr_mult=1.2, max_horizon_bars=28)
        feats["target"] = labels
        symbol_data[sym] = feats
        print(f"  --> {sym}: {len(feats):,} bars loaded (2020-2026).")
    return symbol_data

def run_expanding_walkforward():
    symbol_data = prepare_master_data()

    print("\n=========================================================================================")
    print("  EXPANDING WALK-FORWARD ML ENGINE: RE-TRAINING ON ALL PRIOR DATA BEFORE EACH WINDOW")
    print("=========================================================================================")

    HEAD = (f"{'WIN':<5}{'REGIME':<34}{'TRD':>5}{'ROI%':>9}{'NET USD':>10}"
            f"{'MAXDD%':>8}{'WR%':>7}{'PF':>7}{'TRAIN SAMPLES':>15}{'GATE':>8}")
    print("-" * len(HEAD))
    print(HEAD)
    print("-" * len(HEAD))

    passed_count = 0
    total_net_usd = 0.0

    for w_idx, (win, start_str, end_str, regime_desc) in enumerate(WINDOWS):
        start_ms, end_ms = bounds_ms(start_str, end_str)
        purge_boundary_ms = start_ms - PURGE_MS

        # 1. Assemble In-Sample Training Set (STRICTLY CAUSAL: all data before start_ms - 72h)
        train_dfs = []
        for sym, df in symbol_data.items():
            train_mask = (df["open_time_ms"] <= purge_boundary_ms)
            sub = df[train_mask]
            if len(sub) > 500:
                train_dfs.append(sub)

        if not train_dfs or sum(len(d) for d in train_dfs) < 1000:
            print(f"{win:<5}{regime_desc[:33]:<34}{0:>5}{0.0:>9.2f}{0.0:>10.2f}{0.0:>8.2f}{0.0:>7.1%}{0.0:>7.2f}{'INSUFFICIENT_IS':>15}{'SKIP':>8}")
            continue

        master_train = pd.concat(train_dfs, ignore_index=True)
        
        # Filter candidate setups in training to avoid learning idle chop
        cand_train_mask = (
            ((master_train["ema8_ema21_spread"] > 0) & (master_train["dist_to_ema21"] >= -1.5) & (master_train["dist_to_ema21"] <= 2.0)) |
            ((master_train["ema8_ema21_spread"] < 0) & (master_train["dist_to_ema21"] >= -2.0) & (master_train["dist_to_ema21"] <= 1.5))
        ) & (master_train["volume_to_sma"] > 1.2)
        
        cand_train = master_train[cand_train_mask].dropna(subset=FEATURE_COLUMNS + ["target"])
        n_train = len(cand_train)

        # 2. Train Fresh LightGBM Model on Entire Prior In-Sample History
        X_tr = cand_train[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
        y_tr = cand_train["target"].to_numpy(dtype=int)

        model = lgb.LGBMClassifier(
            n_estimators=180,
            max_depth=5,
            learning_rate=0.04,
            subsample=0.8,
            colsample_bytree=0.75,
            random_state=42,
            class_weight="balanced",
            verbose=-1
        )
        model.fit(X_tr, y_tr)

        # In-sample probability calibration (determine 85th percentile threshold strictly from IS predictions)
        p_is = model.predict_proba(X_tr)[:, 1]
        p_thresh = float(np.percentile(p_is, 85))  # Top 15% in-sample conviction

        # 3. Assemble Out-of-Sample Window Data
        oos_candidates = []
        for sym, df in symbol_data.items():
            oos_mask = (df["open_time_ms"] >= start_ms) & (df["open_time_ms"] <= end_ms)
            oos_df = df[oos_mask].copy().reset_index(drop=True)
            if len(oos_df) < 50:
                continue

            X_oos = oos_df[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
            X_oos = np.nan_to_num(X_oos, nan=0.0, posinf=50.0, neginf=-50.0)
            oos_df["prob"] = model.predict_proba(X_oos)[:, 1]

            # Signal triggers
            c = oos_df["close"].to_numpy()
            h = oos_df["high"].to_numpy()
            l = oos_df["low"].to_numpy()
            atr = oos_df["atr"].to_numpy()
            times = oos_df["open_time_ms"].to_numpy()
            probs = oos_df["prob"].to_numpy()
            vol_sma = oos_df["volume_to_sma"].to_numpy()
            spread_8_21 = oos_df["ema8_ema21_spread"].to_numpy()
            spread_21_50 = oos_df["ema21_ema50_spread"].to_numpy()

            # Long condition: Bull alignment + high conviction + volume
            long_cond = (spread_8_21 > 0) & (spread_21_50 > -0.05) & (probs >= p_thresh) & (vol_sma > 1.2)
            # Short condition: Bear alignment + high conviction + volume
            short_cond = (spread_8_21 < 0) & (spread_21_50 < 0.05) & (probs >= p_thresh) & (vol_sma > 1.2)

            for idx in np.where(long_cond)[0]:
                if 20 < idx < len(oos_df) - 30:
                    oos_candidates.append({
                        "symbol": sym, "idx": idx, "direction": 1,
                        "time_ms": times[idx], "close": c[idx], "atr": atr[idx],
                        "stop_ref": l[idx], "df": oos_df
                    })

            for idx in np.where(short_cond)[0]:
                if 20 < idx < len(oos_df) - 30:
                    oos_candidates.append({
                        "symbol": sym, "idx": idx, "direction": -1,
                        "time_ms": times[idx], "close": c[idx], "atr": atr[idx],
                        "stop_ref": h[idx], "df": oos_df
                    })

        # Sort OOS candidates chronologically
        oos_candidates.sort(key=lambda x: x["time_ms"])

        # 4. Simulate Portfolio Execution for Window k
        capital = INITIAL_CAPITAL
        peak_capital = INITIAL_CAPITAL
        active_positions: List[Dict[str, Any]] = []
        closed_trades: List[Dict[str, Any]] = []
        circuit_breaker = False

        for cand in oos_candidates:
            curr_time = cand["time_ms"]
            active_positions = [p for p in active_positions if p["exit_time"] > curr_time]

            if circuit_breaker or len(active_positions) >= MAX_CONCURRENT_POSITIONS:
                continue

            current_dd = (peak_capital - capital) / peak_capital
            if current_dd >= DRAWDOWN_LIMIT_PCT:
                circuit_breaker = True
                continue

            if any(p["symbol"] == cand["symbol"] for p in active_positions):
                continue

            net_profit = capital - INITIAL_CAPITAL
            risk_usd = HOUSE_MONEY_RISK if net_profit >= 50.0 else (DEFENSE_RISK if current_dd >= 0.025 else BASE_RISK)

            if cand["direction"] == 1:
                init_stop = cand["stop_ref"] - 1.2 * cand["atr"]
                if init_stop >= cand["close"]:
                    init_stop = cand["close"] - 1.5 * cand["atr"]
            else:
                init_stop = cand["stop_ref"] + 1.2 * cand["atr"]
                if init_stop <= cand["close"]:
                    init_stop = cand["close"] + 1.5 * cand["atr"]

            res = simulate_symmetric_trade(
                df=cand["df"],
                entry_idx=cand["idx"],
                direction=cand["direction"],
                entry_price=cand["close"],
                initial_stop=init_stop,
                atr_val=cand["atr"],
                risk_usd=risk_usd,
                max_hold_bars=32
            )
            res["symbol"] = cand["symbol"]
            active_positions.append(res)
            closed_trades.append(res)

            capital += res["net_pnl"]
            peak_capital = max(peak_capital, capital)

        # Performance Metrics
        n_tr = len(closed_trades)
        if n_tr == 0:
            print(f"{win:<5}{regime_desc[:33]:<34}{0:>5}{0.0:>9.2f}{0.0:>10.2f}{0.0:>8.2f}{0.0:>7.1%}{0.0:>7.2f}{n_train:>15,}{'FAIL':>8}")
            continue

        wins = [t for t in closed_trades if t["is_win"]]
        losses = [t for t in closed_trades if not t["is_win"]]
        wr = len(wins) / n_tr
        net_usd = capital - INITIAL_CAPITAL
        roi_pct = (net_usd / INITIAL_CAPITAL) * 100.0
        tot_gain = sum(t["net_pnl"] for t in wins)
        tot_loss = abs(sum(t["net_pnl"] for t in losses))
        pf = (tot_gain / tot_loss) if tot_loss > 0 else 99.0

        # Drawdown calculation
        eq = INITIAL_CAPITAL
        pk = INITIAL_CAPITAL
        m_dd = 0.0
        for t in closed_trades:
            eq += t["net_pnl"]
            pk = max(pk, eq)
            m_dd = max(m_dd, pk - eq)
        maxdd_pct = (m_dd / pk) * 100.0

        passed = (roi_pct >= 20.0) and (maxdd_pct < 5.0) and (wr >= 0.40) and (n_tr >= 6)
        if passed:
            passed_count += 1
        total_net_usd += net_usd

        pf_str = "inf" if pf >= 99.0 else f"{pf:.2f}"
        verdict = "PASS" if passed else "FAIL"

        print(f"{win:<5}{regime_desc[:33]:<34}{n_tr:>5}{roi_pct:>9.2f}{net_usd:>10.2f}{maxdd_pct:>8.2f}{wr:>7.1%}{pf_str:>7}{n_train:>15,}{verdict:>8}")

    print("-" * len(HEAD))
    print(f"Summary: {passed_count} / {len(WINDOWS)} Windows PASSED | Total Net Profit: {total_net_usd:.2f} USD")
    print("=========================================================================================\n")

if __name__ == "__main__":
    run_expanding_walkforward()
