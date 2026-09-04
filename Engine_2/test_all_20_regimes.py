"""
Test Dynamic Macro-Regime Conditioned Walk-Forward Across All 20 Windows
- Zero WINDOW_CONFIGURATIONS lookup table
- Zero runtime OOS fallback loops
- Causal 30-day In-Sample macro regime classification
- Top-K conviction ranking (K=8)
- Real slippage (10 bps entry, 15 bps exit) + 0.08% fees
- Strict adverse-first intra-bar execution
"""
import sys, os, json, time
sys.path.append('Engine_2')
from s1_liquidation_cascade import (
    load_and_preprocess_data, ARCHETYPE_FUNCTIONS, extract_archetype_dataset, 
    get_oos_windows, fast_portfolio_backtest_numba, REGIME_ARCHETYPE_MAP,
    classify_macro_regime_causal
)
import pandas as pd, numpy as np, lightgbm as lgb

feature_cols = [
    'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
    'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
    'liq_imbalance', 'liq_vol_ratio', 'liq_long_ratio', 'liq_short_ratio', 'liq_zscore_24h',
    'long_liq_zscore', 'short_liq_zscore', 'oi_flush', 'zoi', 'oid', 'oicc', 'fr', 'zfr', 'zls',
    'macro_spread', 'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'trend_strength', 'regime',
    'vwap_zscore', 'vwap_dev_pct'
]

data = load_and_preprocess_data()
btc = data['BTCUSDT']
windows = get_oos_windows()

# Pre-extract required unique archetypes
needed_archetypes = list(set(REGIME_ARCHETYPE_MAP.values()))
archetype_datasets = {}
print(f"Pre-extracting {len(needed_archetypes)} regime archetypes...")
for name in needed_archetypes:
    archetype_datasets[name] = extract_archetype_dataset(data, ARCHETYPE_FUNCTIONS[name], feature_cols)
    print(f"  {name}: {len(archetype_datasets[name]):,} trades")

print("\n" + "="*85)
print("RUNNING STRICT CAUSAL MACRO-REGIME WALK-FORWARD (ZERO SNOOPING / NO OOS LOOPS)")
print("="*85)
print(f"{'Win':<4} {'Test Period':<23} {'Regime':<28} {'Arch':<20} {'Pool':<6} {'Trades':<7} {'WR%':<7} {'ROI%':<8} {'MaxDD%':<8} {'Status':<6}")
print("-" * 125)

all_results = []
passed_count = 0

for idx, w in enumerate(windows, 1):
    test_start = w['test_start']
    test_end = w['test_end']
    train_start = w['train_start']
    train_end_purged = w['train_end'] - pd.Timedelta(hours=3)
    
    # 1. Objective In-Sample Regime Classification
    regime = classify_macro_regime_causal(btc, train_end_purged)
        
    arch_name = REGIME_ARCHETYPE_MAP[regime]
    df_arch = archetype_datasets[arch_name]
    
    # 2. Strict Causal Partitioning (purge gap enforced)
    df_is = df_arch[(df_arch['entry_time'] >= train_start) & (df_arch['exit_time'] < train_end_purged)].copy()
    df_oos = df_arch[(df_arch['entry_time'] >= test_start) & (df_arch['entry_time'] < test_end)].copy()
    period_str = f"{test_start.strftime('%Y-%m-%d')}~{test_end.strftime('%m-%d')}"

    # Guard: too few IS trades to train
    p_tr_check = int(df_is['label'].sum()) if len(df_is) > 0 else 0
    if len(df_is) < 20 or p_tr_check < 5:
        print(f"W{idx:02d} {period_str:<23} {regime:<28} {arch_name:<20} {len(df_oos):<6} {'—':<7} {'—':>5}%  {'—':>7}%  {'—':>6}%  SKIP   [IS={len(df_is)} pos={p_tr_check}]")
        all_results.append({"window": idx, "regime": regime, "archetype": arch_name, "trades": 0, "win_rate": 0.0, "roi": 0.0, "max_dd": 0.0, "passed": False})
        continue

    # Guard: too few OOS candidates
    if len(df_oos) < 6:
        print(f"W{idx:02d} {period_str:<23} {regime:<28} {arch_name:<20} {len(df_oos):<6} {'—':<7} {'—':>5}%  {'—':>7}%  {'—':>6}%  SKIP   [OOS pool={len(df_oos)} < 6]")
        all_results.append({"window": idx, "regime": regime, "archetype": arch_name, "trades": 0, "win_rate": 0.0, "roi": 0.0, "max_dd": 0.0, "passed": False})
        continue

    fcols = [c for c in feature_cols if c in df_is.columns]
    X_tr = df_is[fcols].fillna(0.0).to_numpy(np.float32)
    y_tr = df_is['label'].to_numpy(np.int32)
    p_tr = int(y_tr.sum())
    sw = max(0.1, float((len(y_tr) - p_tr) / p_tr)) if p_tr > 0 else 1.0

    model = lgb.LGBMClassifier(
        max_depth=3, learning_rate=0.02, n_estimators=200,
        min_child_samples=30, reg_alpha=0.05, reg_lambda=0.05,
        scale_pos_weight=sw, random_state=42, verbose=-1, n_jobs=2
    )
    model.fit(X_tr, y_tr)
    
    # 3. OOS Execution — Top-K conviction selection (K=20 for statistical significance)
    X_oos = df_oos[fcols].fillna(0.0).to_numpy(np.float32)
    pool_size = len(X_oos)
    p_oos = model.predict_proba(X_oos)[:, 1].astype(np.float64)

    k = min(20, len(p_oos))
    idx_top = np.argsort(-p_oos)[:k]
    mask = np.zeros(len(p_oos), dtype=np.bool_)
    mask[idx_top] = True
    
    sub_et = df_oos['entry_time'].values.astype(np.int64)[mask]
    sub_xt = df_oos['exit_time'].values.astype(np.int64)[mask]
    sub_ep = df_oos['entry_price'].values.astype(np.float64)[mask]
    sub_xp = df_oos['exit_price'].values.astype(np.float64)[mask]
    sub_atr = df_oos['atr'].values.astype(np.float64)[mask]
    sub_mae = df_oos['mae'].values.astype(np.float64)[mask]
    sub_dr = df_oos['direction'].values.astype(np.int8)[mask]
    
    roi, dd, wr, tr = fast_portfolio_backtest_numba(
        sub_et, sub_xt, sub_ep, sub_xp, sub_atr, sub_mae, sub_dr, p_oos[mask],
        initial_capital=10000.0,
        base_risk=75.0, house_risk=300.0, house_trigger=300.0,
        fee_rate=0.0008, max_concurrent=2, leverage=10.0, max_notional=50000.0,
        dd_limit=0.045
    )
    
    passed = (roi >= 0.20) and (dd <= 0.05) and (wr >= 0.40) and (tr >= 6)
    if passed: passed_count += 1
    status_str = "PASS" if passed else "FAIL"
    print(f"W{idx:02d} {period_str:<23} {regime:<28} {arch_name:<20} {pool_size:<6} {tr:<7} {wr*100:5.1f}% {roi*100:+6.1f}% {dd*100:5.2f}% {status_str:<6}")
    all_results.append({
        "window": idx,
        "regime": regime,
        "archetype": arch_name,
        "trades": tr,
        "win_rate": wr,
        "roi": roi,
        "max_dd": dd,
        "passed": passed
    })

print("-" * 125)
print(f"FINAL RESULT: {passed_count}/20 Windows Passed ({passed_count/20*100:.1f}%) under zero-snooping macro regime conditioning.")
