"""
Fractional Differentiation for Financial Time Series
Based on Marcos López de Prado, "Advances in Financial Machine Learning", Chapter 5.
Preserves memory and long-range cointegration while achieving stationarity.
"""

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller


def get_weights_ffd(d: float, thres: float = 1e-4, max_lags: int = 2000) -> np.ndarray:
    """
    Generate memory-efficient weights for fractional differentiation using fixed-width window (FFD).
    
    Args:
        d: Fractional differentiation degree (0.0 to 1.0)
        thres: Threshold weight magnitude below which weights are dropped
        max_lags: Maximum lookback length
        
    Returns:
        np.ndarray: Array of weights [w_0, w_1, ..., w_k]
    """
    w = [1.0]
    k = 1
    while k < max_lags:
        w_k = -w[-1] / k * (d - k + 1)
        if abs(w_k) < thres:
            break
        w.append(w_k)
        k += 1
    return np.array(w[::-1])  # Reversed for convolution


def frac_diff_ffd(series: pd.Series, d: float, thres: float = 1e-4) -> pd.Series:
    """
    Applies Fractional Differentiation using Fixed-Width Window (FFD) to a pandas Series.
    
    Args:
        series: Pandas series of prices (e.g., Close)
        d: Fractional differentiation degree
        thres: Weight cutoff threshold
        
    Returns:
        pd.Series: Fractionally differentiated stationary series with preserved index
    """
    weights = get_weights_ffd(d, thres=thres)
    width = len(weights) - 1
    
    values = series.values
    output = np.full(len(values), np.nan, dtype=np.float64)
    
    for i in range(width, len(values)):
        window = values[i - width : i + 1]
        if not np.any(np.isnan(window)):
            output[i] = np.dot(weights, window)
            
    return pd.Series(output, index=series.index, name=f"{series.name}_fracdiff_{d:.2f}")


def find_min_d(series: pd.Series, d_range: np.ndarray = np.linspace(0.05, 0.95, 19), p_val_threshold: float = 0.05) -> tuple:
    """
    Performs grid search to find the minimum d* that passes the Augmented Dickey-Fuller (ADF) test.
    
    Args:
        series: Price series to test
        d_range: Grid of d values to evaluate
        p_val_threshold: Target ADF p-value (typically 0.05 for 95% confidence)
        
    Returns:
        tuple[float, float]: (optimal_d, p_value)
    """
    clean_series = series.dropna()
    best_d = 1.0
    best_pval = 1.0
    
    for d in d_range:
        fd_series = frac_diff_ffd(clean_series, d).dropna()
        if len(fd_series) < 50:
            continue
        adf_res = adfuller(fd_series.values, maxlag=1, regression='c', autolag=None)
        p_val = adf_res[1]
        if p_val < p_val_threshold:
            best_d = float(d)
            best_pval = float(p_val)
            break
            
    return best_d, best_pval
