"""
Causal Market Regime Gating & Strategy Router
Uses In-Sample Gaussian Mixture Models (GMM) and Rolling Volatility/Entropy features to dynamically route between Momentum and Mean-Reversion execution paths without lookahead.
"""

import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture


class CausalRegimeGater:
    """
    Fits an unsupervised 2-state Gaussian Mixture Model on historical training features,
    then predicts current market regime out-of-sample in a strictly causal rolling manner.
    """
    def __init__(self, n_components: int = 2, random_state: int = 42):
        self.n_components = n_components
        self.random_state = random_state
        self.gmm = GaussianMixture(n_components=n_components, covariance_type='full', random_state=random_state)
        self.is_fitted = False
        self.high_vol_state_idx = 1
        
    def _extract_regime_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Extracts scale-invariant volatility and volume features."""
        feat = pd.DataFrame(index=df.index)
        
        # 1. Volatility Ratio (Short-term ATR vs Long-term ATR)
        if 'atr_14' in df.columns:
            atr = df['atr_14']
        else:
            hl = (df['high'] - df['low']).abs()
            atr = hl.rolling(14, min_periods=1).mean()
            
        long_atr = atr.rolling(96 * 5, min_periods=24).mean().replace(0.0, 1.0)
        feat['vol_ratio'] = (atr / long_atr).clip(0.1, 5.0)
        
        # 2. Parkinson Volatility Proxy (High-Low estimator)
        hl_ratio = np.log(df['high'] / df['low'].replace(0.0, 1e-6))
        parkinson_sq = (hl_ratio ** 2) / (4.0 * np.log(2.0))
        feat['parkinson_vol'] = np.sqrt(parkinson_sq.rolling(24, min_periods=6).mean()).fillna(0.0)
        
        # 3. Volume Quote Z-Score
        if 'volume_quote' in df.columns:
            vol = df['volume_quote']
            vol_mean = vol.rolling(96, min_periods=12).mean()
            vol_std = vol.rolling(96, min_periods=12).std().replace(0.0, 1.0)
            feat['vol_zscore'] = ((vol - vol_mean) / vol_std).clip(-3.0, 5.0).fillna(0.0)
        else:
            feat['vol_zscore'] = 0.0
            
        return feat.fillna(0.0)
        
    def fit(self, df_train: pd.DataFrame) -> "CausalRegimeGater":
        """Fits GMM on In-Sample data only."""
        X_train = self._extract_regime_features(df_train).values
        self.gmm.fit(X_train)
        self.is_fitted = True
        
        # Identify which component corresponds to the high-volatility/trend state
        # The state with higher average vol_ratio is designated as 'trending' (state 1)
        mean_vol_per_state = [self.gmm.means_[i][0] for i in range(self.n_components)]
        self.high_vol_state_idx = int(np.argmax(mean_vol_per_state))
        return self
        
    def predict_regime(self, df: pd.DataFrame) -> pd.Series:
        """
        Predicts binary market regime for each bar:
        1 = Trending / Momentum Active
        0 = Consolidation / Mean-Reversion Active
        """
        if not self.is_fitted:
            # Default heuristic fallback if fit was not called
            feat = self._extract_regime_features(df)
            return (feat['vol_ratio'] >= 0.85).astype(np.int8)
            
        X = self._extract_regime_features(df).values
        raw_states = self.gmm.predict(X)
        regimes = (raw_states == self.high_vol_state_idx).astype(np.int8)
        return pd.Series(regimes, index=df.index, name="market_regime")


def compute_rolling_hurst_exponent(series: pd.Series, max_lag: int = 20) -> pd.Series:
    """
    Computes rolling Hurst exponent approximation to classify persistence vs anti-persistence:
    H > 0.55: Persistent / Trending
    H < 0.45: Mean-Reverting
    0.45 <= H <= 0.55: Random Walk / Noise
    """
    def _calc_hurst(arr):
        if len(arr) < max_lag or np.all(arr == arr[0]):
            return 0.5
        lags = range(2, max_lag)
        tau = [np.std(np.subtract(arr[lag:], arr[:-lag])) for lag in lags]
        valid = [(l, t) for l, t in zip(lags, tau) if t > 1e-8]
        if len(valid) < 3:
            return 0.5
        x_vals = [np.log(v[0]) for v in valid]
        y_vals = [np.log(v[1]) for v in valid]
        poly = np.polyfit(x_vals, y_vals, 1)
        return float(np.clip(poly[0], 0.0, 1.0))
        
    return series.rolling(96, min_periods=48).apply(_calc_hurst, raw=True).fillna(0.5)
