"""
Triple-Barrier Method & Meta-Labeling Engine
Based on Marcos López de Prado, "Advances in Financial Machine Learning", Chapters 3 & 4.
Aligns multi-horizon trade path labeling with asymmetric profit-taking, stop-losses, and vertical timeouts.
"""

import numpy as np
import pandas as pd
from numba import njit


@njit
def compute_triple_barrier_events(
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    signal_indices: np.ndarray,
    signal_directions: np.ndarray,  # +1 for Long, -1 for Short
    pt_multipliers: np.ndarray,      # Target distance in dollars (e.g. 5 * ATR)
    sl_multipliers: np.ndarray,      # Stop distance in dollars (e.g. 1 * ATR)
    max_holding_bars: int = 96       # 96 * 15m = 24 hours vertical barrier
) -> tuple:
    """
    Numba-accelerated zero-lookahead Triple Barrier path simulator.
    
    Returns:
        labels: 1 if hit PT first, 0 if hit SL first or timed out with negative return
        returns: Realized trade return
        holding_bars: Duration of the trade in bars
    """
    n_signals = len(signal_indices)
    labels = np.zeros(n_signals, dtype=np.int8)
    returns = np.zeros(n_signals, dtype=np.float64)
    holding_bars = np.zeros(n_signals, dtype=np.int32)
    n_bars = len(closes)
    
    for idx in range(n_signals):
        bar_idx = signal_indices[idx]
        direction = signal_directions[idx]
        
        # Entry at next bar open to prevent seam exploits
        if bar_idx + 1 >= n_bars:
            continue
            
        entry_idx = bar_idx + 1
        entry_price = opens[entry_idx]
        pt_dist = pt_multipliers[idx]
        sl_dist = sl_multipliers[idx]
        
        if direction == 1:
            tp_price = entry_price + pt_dist
            sl_price = entry_price - sl_dist
        else:
            tp_price = entry_price - pt_dist
            sl_price = entry_price + sl_dist
            
        end_idx = min(entry_idx + max_holding_bars, n_bars)
        exit_price = closes[end_idx - 1]
        bars_held = end_idx - entry_idx
        trade_label = 0
        
        for t in range(entry_idx, end_idx):
            h = highs[t]
            l = lows[t]
            
            if direction == 1:
                # Check stop first (conservative assumption)
                if l <= sl_price:
                    exit_price = sl_price
                    bars_held = t - entry_idx + 1
                    trade_label = 0
                    break
                elif h >= tp_price:
                    exit_price = tp_price
                    bars_held = t - entry_idx + 1
                    trade_label = 1
                    break
            else:
                if h >= sl_price:
                    exit_price = sl_price
                    bars_held = t - entry_idx + 1
                    trade_label = 0
                    break
                elif l <= tp_price:
                    exit_price = tp_price
                    bars_held = t - entry_idx + 1
                    trade_label = 1
                    break
                    
        pnl = (exit_price - entry_price) / entry_price * direction
        labels[idx] = trade_label
        returns[idx] = pnl
        holding_bars[idx] = bars_held
        
    return labels, returns, holding_bars


def build_meta_dataset(
    df: pd.DataFrame,
    primary_signals: pd.Series,  # Series of +1, -1, 0
    atr_series: pd.Series,
    pt_r_multiple: float = 5.0,
    sl_r_multiple: float = 1.0,
    max_holding_bars: int = 96
) -> tuple[pd.DataFrame, pd.Series]:
    """
    Constructs a meta-labeling training dataset for a secondary classifier.
    
    Args:
        df: DataFrame with OHLCV features
        primary_signals: Output of Stage 1 model (signals != 0)
        atr_series: Rolling ATR series
        pt_r_multiple: Take profit multiple (e.g. 5.0 for 5R)
        sl_r_multiple: Stop loss multiple (e.g. 1.0 for 1R)
        max_holding_bars: Maximum vertical barrier duration
        
    Returns:
        X_meta: Feature matrix aligned to signal timestamps
        y_meta: Binary labels (1 = Success / Take Profit, 0 = Loss / Timeout)
    """
    valid_mask = (primary_signals != 0).values
    signal_indices = np.where(valid_mask)[0]
    
    if len(signal_indices) == 0:
        return pd.DataFrame(), pd.Series(dtype=np.int8)
        
    signal_directions = primary_signals.values[signal_indices]
    atrs = atr_series.values[signal_indices]
    
    pt_dist = atrs * pt_r_multiple
    sl_dist = atrs * sl_r_multiple
    
    labels, returns, holding_bars = compute_triple_barrier_events(
        df['open'].values,
        df['high'].values,
        df['low'].values,
        df['close'].values,
        signal_indices,
        signal_directions,
        pt_dist,
        sl_dist,
        max_holding_bars=max_holding_bars
    )
    
    meta_df = df.iloc[signal_indices].copy()
    meta_df['primary_signal'] = signal_directions
    meta_df['trade_return'] = returns
    meta_df['holding_bars'] = holding_bars
    
    y_meta = pd.Series(labels, index=meta_df.index, name="meta_label")
    return meta_df, y_meta
