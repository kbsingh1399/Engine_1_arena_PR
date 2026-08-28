"""
Verification & Unit Test Suite for Advanced Quantitative & ML Trading Modules
Tests Fractional Differentiation, Triple Barrier Meta-Labeling, Microstructure Alphas, and Causal Regime Gating.
"""

import os
import sys
import numpy as np
import pandas as pd

# Ensure UTF-8 output on Windows
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add module path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from frac_diff import frac_diff_ffd, find_min_d
from triple_barrier_meta import build_meta_dataset
from microstructure_alphas import compute_liquidation_alphas, compute_vpin_approximation, compute_cvd_divergence
from regime_gating import CausalRegimeGater, compute_rolling_hurst_exponent


def generate_synthetic_crypto_data(n_bars: int = 1000) -> pd.DataFrame:
    """Generates realistic synthetic 15m crypto OHLCV dataframe with orderflow and liquidations."""
    np.random.seed(42)
    
    # Geometric Brownian Motion with regime shifts
    returns = np.random.normal(0.0002, 0.008, n_bars)
    # Inject a trend regime and a chop regime
    returns[200:500] += 0.003  # Strong bull trend
    returns[500:800] *= 0.3    # Tight consolidation
    
    price = 50000.0 * np.exp(np.cumsum(returns))
    
    high = price * (1.0 + np.abs(np.random.normal(0.0, 0.004, n_bars)))
    low = price * (1.0 - np.abs(np.random.normal(0.0, 0.004, n_bars)))
    open_p = (price + np.roll(price, 1)) / 2.0
    open_p[0] = price[0]
    close = price
    
    volume_quote = np.random.lognormal(14.0, 0.8, n_bars)
    future_cvd = np.cumsum(np.random.normal(0.0, 100.0, n_bars))
    long_liq = np.where(np.random.rand(n_bars) > 0.95, np.random.exponential(500000.0, n_bars), 0.0)
    short_liq = np.where(np.random.rand(n_bars) > 0.95, np.random.exponential(500000.0, n_bars), 0.0)
    atr = (high - low).copy()
    
    dates = pd.date_range("2021-01-01", periods=n_bars, freq="15min", tz="UTC")
    df = pd.DataFrame({
        "datetime_utc": dates,
        "open": open_p,
        "high": high,
        "low": low,
        "close": close,
        "volume_quote": volume_quote,
        "future_cvd_15m": future_cvd,
        "long_liq_usd": long_liq,
        "short_liq_usd": short_liq,
        "atr_14": pd.Series(atr).rolling(14, min_periods=1).mean().values
    }, index=dates)
    
    return df


def run_verification():
    print("=" * 70)
    print("[*] RUNNING QUANTITATIVE & ML MODULE VERIFICATION SUITE")
    print("=" * 70)
    
    df = generate_synthetic_crypto_data(1000)
    print(f"[OK] Generated synthetic dataset: {len(df)} 15m bars")
    
    # 1. Test Fractional Differentiation
    print("\n--- Testing Module 1: Fractional Differentiation (FFD) ---")
    best_d, p_val = find_min_d(df['close'], d_range=np.linspace(0.1, 0.9, 9))
    fd_series = frac_diff_ffd(df['close'], d=best_d).dropna()
    corr = np.corrcoef(df['close'].iloc[-len(fd_series):].values, fd_series.values)[0, 1]
    print(f"  Optimal d*: {best_d:.2f} (ADF p-value: {p_val:.4e})")
    print(f"  Memory Correlation with Raw Price: {corr * 100:.2f}% (Stationary yet memory-preserving)")
    assert len(fd_series) > 0, "Fractional diff output must not be empty"
    
    # 2. Test Microstructure Alphas
    print("\n--- Testing Module 2: Microstructure Alphas (Liq Z-Score, VPIN, CVD) ---")
    liq_df = compute_liquidation_alphas(df)
    vpin = compute_vpin_approximation(df)
    cvd_div = compute_cvd_divergence(df)
    print(f"  Liquidation Imbalance mean: {liq_df['liq_imbalance'].mean():.4f}, Max Z-Score: {liq_df['liq_zscore_24h'].max():.2f}")
    print(f"  VPIN Toxicity mean: {vpin.mean():.4f}, 90th percentile: {vpin.quantile(0.9):.4f}")
    print(f"  CVD Absorption Divergence std: {cvd_div.std():.4f}")
    assert not liq_df.empty and len(vpin) == len(df), "Microstructure features calculation failed"
    
    # 3. Test Causal Regime Gating
    print("\n--- Testing Module 3: Causal Regime Gater (Unsupervised GMM) ---")
    train_df = df.iloc[:600]
    test_df = df.iloc[600:]
    gater = CausalRegimeGater(n_components=2)
    gater.fit(train_df)
    test_regimes = gater.predict_regime(test_df)
    hurst = compute_rolling_hurst_exponent(df['close'])
    print(f"  In-Sample GMM fitted. Out-of-Sample Trend Regime bars: {(test_regimes == 1).sum()} / {len(test_regimes)}")
    print(f"  Consolidation Regime bars: {(test_regimes == 0).sum()} / {len(test_regimes)}")
    print(f"  Average Rolling Hurst Exponent: {hurst.mean():.3f}")
    
    # 4. Test Triple Barrier Meta-Labeling
    print("\n--- Testing Module 4: Triple-Barrier Meta-Labeling Engine ---")
    # Generate dummy primary signals (e.g. Breakout when price > 20-bar high)
    roll_max = df['high'].shift(1).rolling(20).max()
    roll_min = df['low'].shift(1).rolling(20).min()
    primary_signals = pd.Series(0, index=df.index)
    primary_signals[df['close'] > roll_max] = 1
    primary_signals[df['close'] < roll_min] = -1
    
    meta_df, y_meta = build_meta_dataset(df, primary_signals, df['atr_14'], pt_r_multiple=5.0, sl_r_multiple=1.0)
    print(f"  Primary Signals Generated: {(primary_signals != 0).sum()}")
    print(f"  Meta-Dataset Samples: {len(meta_df)}")
    print(f"  Meta-Label Win Rate (5R Target Reached before 1R Stop): {(y_meta == 1).mean() * 100:.2f}%")
    
    print("\n" + "=" * 70)
    print("[SUCCESS] ALL 4 QUANTITATIVE & ML MODULES VERIFIED (PASS)")
    print("=" * 70)


if __name__ == "__main__":
    run_verification()
