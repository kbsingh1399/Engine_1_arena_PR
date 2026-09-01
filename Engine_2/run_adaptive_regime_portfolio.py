#!/usr/bin/env python3
"""
Regime-Adaptive Meta-Engine
Dynamically selects the best strategy based on current market regime
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

class RegimeDetector:
    """Detects current market regime using volatility and trend metrics"""
    
    def __init__(self):
        self.regimes = {
            'TRENDING_UP': ['S2', 'S3', 'S8'],
            'TRENDING_DOWN': ['S2', 'S3', 'S8'],
            'RANGING': ['S1', 'S4', 'S6', 'S15'],
            'HIGH_VOLATILITY': ['S1', 'S5', 'S7'],
            'LOW_VOLATILITY': ['S4', 'S6', 'S15'],
            'LIQUIDATION_EVENT': ['S1', 'S5'],
            'MEAN_REVERSION': ['S7', 'S15']
        }
    
    def detect_regime(self, df_recent):
        """
        Detect current market regime from recent price data
        
        Args:
            df_recent: DataFrame with recent bars (last 96 bars = 24 hours)
        
        Returns:
            regime: str - detected regime
            confidence: float - confidence score (0-1)
        """
        if len(df_recent) < 96:
            return 'UNKNOWN', 0.0
        
        # Calculate metrics
        closes = df_recent['close'].values
        highs = df_recent['high'].values
        lows = df_recent['low'].values
        
        # Trend strength (EMA slope)
        ema_20 = pd.Series(closes).ewm(span=20).mean().values
        trend_strength = (ema_20[-1] - ema_20[-20]) / ema_20[-20]
        
        # Volatility (ATR / price)
        atr = np.mean(highs[-20:] - lows[-20:])
        volatility = atr / closes[-1]
        
        # Volume profile (if available)
        if 'volume' in df_recent.columns:
            vol_ratio = df_recent['volume'].iloc[-20:].mean() / df_recent['volume'].mean()
        else:
            vol_ratio = 1.0
        
        # Regime detection logic
        if abs(trend_strength) > 0.05:
            if trend_strength > 0:
                regime = 'TRENDING_UP'
                confidence = min(abs(trend_strength) / 0.1, 1.0)
            else:
                regime = 'TRENDING_DOWN'
                confidence = min(abs(trend_strength) / 0.1, 1.0)
        elif volatility > 0.03:
            regime = 'HIGH_VOLATILITY'
            confidence = min(volatility / 0.05, 1.0)
        elif volatility < 0.01:
            regime = 'LOW_VOLATILITY'
            confidence = 1.0 - (volatility / 0.01)
        else:
            regime = 'RANGING'
            confidence = 0.7
        
        # Check for liquidation events (if liquidation data available)
        if 'long_liq_usd' in df_recent.columns:
            liq_spike = df_recent['long_liq_usd'].iloc[-5:].sum() / df_recent['long_liq_usd'].mean()
            if liq_spike > 3.0:
                regime = 'LIQUIDATION_EVENT'
                confidence = min(liq_spike / 5.0, 1.0)
        
        return regime, confidence
    
    def get_recommended_strategies(self, regime):
        """Get list of recommended strategies for a given regime"""
        return self.regimes.get(regime, ['S2', 'S8'])  # Default to proven strategies


class MetaEngine:
    """Regime-Adaptive Meta-Engine that orchestrates multiple strategies"""
    
    def __init__(self):
        self.regime_detector = RegimeDetector()
        self.results_dir = Path('Engine_2')
        self.strategy_status = {}
        self.load_strategy_status()
    
    def load_strategy_status(self):
        """Load status of all strategies from their result files"""
        strategy_files = {
            'S1': 'results_s1_liquidation/s1_status.json',
            'S2': 'results_s2/s2_status.json',
            'S3': 'results_s3_macro_trend/s3_status.json',
            'S4': 'results_s4_cvd_divergence_squeeze/s4_status.json',
            'S5': 'results_s5_liquidity_sweep/s5_status.json',
            'S6': 'results_s6_volatility_compression/s6_status.json',
            'S7': 'results_s7_delta_climax/s7_status.json',
            'S8': 'results_s8_hybrid/s2_status.json',
            'S15': 'results_s15_vwap_profile/s15_status.json'
        }
        
        for strategy_id, status_file in strategy_files.items():
            status_path = self.results_dir / status_file
            if status_path.exists():
                with open(status_path) as f:
                    data = json.load(f)
                    passed = sum(1 for w in data if 'PASS' in w.get('status', ''))
                    self.strategy_status[strategy_id] = {
                        'passed_windows': passed,
                        'total_windows': 20,
                        'fully_passed': passed == 20
                    }
            else:
                self.strategy_status[strategy_id] = {
                    'passed_windows': 0,
                    'total_windows': 20,
                    'fully_passed': False
                }
    
    def recommend_strategies(self, df_recent):
        """
        Recommend best strategies for current market conditions
        
        Args:
            df_recent: DataFrame with recent market data
        
        Returns:
            recommendations: list of (strategy_id, score, reason)
        """
        regime, confidence = self.regime_detector.detect_regime(df_recent)
        recommended = self.regime_detector.get_recommended_strategies(regime)
        
        # Score strategies based on regime fit and historical performance
        recommendations = []
        for strategy_id in recommended:
            status = self.strategy_status.get(strategy_id, {})
            
            if not status.get('fully_passed', False):
                continue
            
            # Score = regime confidence * historical pass rate
            pass_rate = status['passed_windows'] / status['total_windows']
            score = confidence * pass_rate
            
            recommendations.append((strategy_id, score, f"{regime} regime ({confidence:.0%} confidence)"))
        
        # Sort by score descending
        recommendations.sort(key=lambda x: x[1], reverse=True)
        
        return recommendations
    
    def generate_report(self, df_recent=None):
        """Generate comprehensive meta-engine report"""
        report = []
        report.append("="*80)
        report.append("REGIME-ADAPTIVE META-ENGINE REPORT")
        report.append("="*80)
        report.append("")
        
        # Strategy status
        report.append("STRATEGY STATUS:")
        report.append("-" * 80)
        for strategy_id in sorted(self.strategy_status.keys(), key=lambda x: int(x[1:])):
            status = self.strategy_status[strategy_id]
            checkmark = "✅" if status['fully_passed'] else "❌"
            report.append(f"{checkmark} {strategy_id:3s} | {status['passed_windows']:2d}/20 windows passed")
        
        report.append("")
        
        # Regime detection (if data provided)
        if df_recent is not None:
            regime, confidence = self.regime_detector.detect_regime(df_recent)
            report.append(f"CURRENT REGIME: {regime} ({confidence:.0%} confidence)")
            report.append("")
            
            recommendations = self.recommend_strategies(df_recent)
            report.append("RECOMMENDED STRATEGIES:")
            report.append("-" * 80)
            for strategy_id, score, reason in recommendations[:3]:
                report.append(f"  {strategy_id:3s} | Score: {score:.2f} | {reason}")
        
        report.append("")
        report.append("="*80)
        
        return "\n".join(report)


def main():
    """Main entry point"""
    print("Initializing Regime-Adaptive Meta-Engine...")
    meta_engine = MetaEngine()
    
    # Generate report (without live data for now)
    report = meta_engine.generate_report()
    print(report)
    
    # Save report
    with open('Engine_2/meta_engine_report.txt', 'w') as f:
        f.write(report)
    
    print("\nReport saved to Engine_2/meta_engine_report.txt")


if __name__ == '__main__':
    main()
