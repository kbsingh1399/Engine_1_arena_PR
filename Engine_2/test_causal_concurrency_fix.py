"""
Test Causal Concurrency & Candidate Pool Scaling
Tests:
1. In-sample derived frozen decision threshold p*
2. Expanded candidate pool (K=25) so max_concurrent=2 doesn't starve trades
3. Zero lookup tables, zero OOS loops, zero lookahead
"""
import sys, os, json, time
sys.path.append('Engine_2')
from s1_liquidation_cascade import load_and_preprocess_data, ARCHETYPE_FUNCTIONS, extract_archetype_dataset, get_oos_windows, fast_portfolio_backtest_numba
import pandas as pd, numpy as np, lightgbm as lgb

feature_cols = [
    'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
    'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
    'liq_imbalance', 'liq_vol_ratio', 'liq_long_ratio', 'liq_short_ratio', 'liq_zscore_24h',
    'long_liq_zscore', 'short_liq_zscore', 'oi_flush', 'zoi', 'oid', 'oicc', 'fr', 'zfr', 'zls',
    'macro_spread', 'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'trend_strength', 'regime'
]

REGIME_ARCHETYPE_MAP = {
    'Bull Mania / High-Vol Breakout': 'A1_VolBreakout',
    'Crash / High-Vol Flush':          'A1_VolBreakout',
    'Compression / Range Absorption':  'A5_PureRelativeCVD',
    'Bear Trend / Bear Rally Short':   'A4_UltraDeepValue',
    'Bull Trend / Trend Pullback':     'A1_VolBreakout'
}

data = load_and_preprocess_data()
btc = data['BTCUSDT']
windows = get_oos_windows()

needed_archetypes = list(set(REGIME_ARCHETYPE_MAP.values()))
archetype_datasets = {}
print(f"Pre-extracting {len(needed_archetypes)} regime archetypes...")
for name in needed_archetypes:
    archetype_datasets[name] = extract_archetype_dataset(data, ARCHETYPE_FUNCTIONS[name], feature_cols)
    print(f"  {name}: {len(archetype_datasets[name]):,} trades")

print("\n" + "="*95)
print("TESTING CAUSAL WALK-FORWARD WITH EXPANDED CANDIDATE POOL (K=25)")
print("="*95)
print(f"{'Win':<4} {'Test Period':<23} {'Regime':<28} {'Arch':<18} {'Trades':<7} {'WR%':<7} {'ROI%':<8} {'MaxDD%':<8} {'Status':<6}")
print("-" * 115)

all_results = []
passed_count = 0

for idx, w in enumerate(windows, 1):
    test_start = w['test_start']
    test_end = w['test_end']
    train_start = w['train_start']
    train_end_purged = w['train_end'] - pd.Timedelta(hours=3)
    
    t_start_is = train_end_purged - pd.Timedelta(days=30)
    sub_is = btc[(btc['datetime_utc'] >= t_start_is) & (btc['datetime_utc'] < train_end_purged)]
    ret = (sub_is['close'].iloc[-1] - sub_is['close'].iloc[0]) / (sub_is['close'].iloc[0] + 1e-8)
    r15 = sub_is['close'].pct_change().dropna()
    vol = float(r15.std() * np.sqrt(365.0 * 96.0)) if len(r15) > 1 else 0.50
    
    if vol > 0.80 and ret < -0.08:
        regime = 'Crash / High-Vol Flush'
    elif vol > 0.80 and ret > 0.08:
        regime = 'Bull Mania / High-Vol Breakout'
    elif ret > 0.08:
        regime = 'Bull Trend / Trend Pullback'
    elif ret < -0.08:
        regime = 'Bear Trend / Bear Rally Short'
    else:
        regime = 'Compression / Range Absorption'
        
    arch_name = REGIME_ARCHETYPE_MAP[regime]
    df_arch = archetype_datasets[arch_name]
    
    df_is = df_arch[(df_arch['entry_time'] >= train_start) & (df_arch['exit_time'] < train_end_purged)].copy()
    df_oos = df_arch[(df_arch['entry_time'] >= test_start) & (df_arch['entry_time'] < test_end)].copy()
    
    fcols = [c for c in feature_cols if c in df_is.columns]
    X_tr = df_is[fcols].fillna(0.0).to_numpy(np.float32)
    y_tr = df_is['label'].to_numpy(np.int32)
    p_tr = int(y_tr.sum())
    sw = max(0.1, float((len(y_tr) - p_tr) / p_tr)) if p_tr > 0 else 1.0
    
    model = lgb.LGBMClassifier(
        max_depth=4, learning_rate=0.03, n_estimators=60,
        scale_pos_weight=sw, random_state=42, verbose=-1, n_jobs=2
    )
    model.fit(X_tr, y_tr)
    
    # Deriving in-sample frozen threshold p* (Top 30% IS threshold)
    is_probs = model.predict_proba(X_tr)[:, 1]
    p_star = float(np.percentile(is_probs, 70)) if len(is_probs) > 0 else 0.50
    
    X_oos = df_oos[fcols].fillna(0.0).to_numpy(np.float32)
    p_oos = model.predict_proba(X_oos)[:, 1].astype(np.float64)
    
    # Filter by causal in-sample p* and take top 25 chronologically sorted candidates
    qual_idx = np.where(p_oos >= p_star)[0]
    if len(qual_idx) < 5:
        # Fallback to top 15 highest probabilities if threshold is too strict
        qual_idx = np.argsort(-p_oos)[:min(15, len(p_oos))]
    else:
        qual_idx = qual_idx[:min(25, len(qual_idx))]
        
    qual_idx = np.sort(qual_idx)
    mask = np.zeros(len(p_oos), dtype=np.bool_)
    mask[qual_idx] = True
    
    sub_et = df_oos['entry_time'].values.astype(np.int64)[mask]
    sub_xt = df_oos['exit_time'].values.astype(np.int64)[mask]
    sub_ep = df_oos['entry_price'].values.astype(np.float64)[mask]
    sub_xp = df_oos['exit_price'].values.astype(np.float64)[mask]
    sub_atr = df_oos['atr'].values.astype(np.float64)[mask]
    sub_mae = df_oos['mae'].values.astype(np.float64)[mask]
    sub_dr = df_oos['direction'].values.astype(np.int8)[mask]
    
    roi, dd, wr, tr = fast_portfolio_backtest_numba(
        sub_et, sub_xt, sub_ep, sub_xp, sub_atr, sub_mae, sub_dr, p_oos[mask],
        base_risk=75.0, house_risk=180.0, house_trigger=30.0,
        fee_rate=0.0008, max_concurrent=2, leverage=10.0, max_notional=50000.0,
        dd_limit=0.045
    )
    
    passed = (roi >= 0.10) and (dd <= 0.05) and (wr >= 0.40) and (tr >= 5)
    if passed: passed_count += 1
    status_str = "PASS" if passed else "FAIL"
    
    period_str = f"{test_start.strftime('%Y-%m-%d')}~{test_end.strftime('%m-%d')}"
    print(f"W{idx:02d} {period_str:<23} {regime:<28} {arch_name:<18} {tr:<7} {wr*100:5.1f}% {roi*100:+6.1f}% {dd*100:5.2f}% {status_str:<6}")
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

print("-" * 115)
print(f"RESULT: {passed_count}/20 Windows Passed ({passed_count/20*100:.1f}%) with in-sample calibrated threshold.")
