"""
Measure Macro Regimes Across All 20 Windows
"""
import sys, os
sys.path.append('Engine_2')
from s1_liquidation_cascade import load_and_preprocess_data, get_oos_windows
import pandas as pd, numpy as np

data = load_and_preprocess_data()
btc = data['BTCUSDT']
windows = get_oos_windows()

print(f"{'Window':<8} {'Start Date':<12} {'End Date':<12} {'BTC Ret%':<10} {'BTC Vol%':<10} {'Macro Regime':<30}")
print("-" * 85)
for idx, w in enumerate(windows, 1):
    # Determine regime using In-Sample training history up to train_end_purged
    t_end_is = w['train_end'] - pd.Timedelta(hours=3)
    t_start_is = t_end_is - pd.Timedelta(days=30)
    
    sub_is = btc[(btc['datetime_utc'] >= t_start_is) & (btc['datetime_utc'] < t_end_is)]
    if len(sub_is) > 0:
        ret = (sub_is['close'].iloc[-1] - sub_is['close'].iloc[0]) / sub_is['close'].iloc[0]
        r15 = sub_is['close'].pct_change().dropna()
        vol = r15.std() * np.sqrt(365 * 96)
        
        if vol > 0.80 and ret < -0.08:
            reg = 'Crash / High-Vol Flush'
        elif vol > 0.80 and ret > 0.08:
            reg = 'Bull Mania / High-Vol Breakout'
        elif ret > 0.08:
            reg = 'Bull Trend / Trend Pullback'
        elif ret < -0.08:
            reg = 'Bear Trend / Bear Rally Short'
        else:
            reg = 'Compression / Range Absorption'
            
        t0_str = w['test_start'].strftime("%Y-%m-%d")
        t1_str = w['test_end'].strftime("%Y-%m-%d")
        print(f"W{idx:02d}     {t0_str:<12} {t1_str:<12} {ret*100:+6.1f}%     {vol*100:5.1f}%     {reg:<30}")
