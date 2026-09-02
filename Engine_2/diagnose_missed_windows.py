import os
import sys
import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta

from run_optimal_regime_matrix import (
    load_s1_trades, load_s2_trades, load_s3_trades, load_s4_trades,
    load_s5_trades, load_s6_trades, load_s7_trades, load_s8_trades, load_s15_trades,
    get_oos_windows
)

windows = get_oos_windows()
target_indices = [1, 3, 4, 10, 14, 17]

print(f"Diagnosing missed windows: {target_indices}")
for win_dict in windows:
    if win_dict['idx'] not in target_indices:
        continue
    w_idx = win_dict['idx']
    t_start = win_dict['test_start']
    t_end = win_dict['test_end']
    print(f"\n================ Window W{w_idx:02d} ({t_start.strftime('%Y-%m-%d')} to {t_end.strftime('%Y-%m-%d')}) ================")
    
    # Check S1, S5, S8, S15
    for s_name, loader in [('S1', load_s1_trades), ('S5', load_s5_trades), ('S8', load_s8_trades), ('S15', load_s15_trades)]:
        fcols = ['direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
                 'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
                 'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'btc_trend']
        df = loader(fcols)
        sub = df[(df['entry_time'] >= t_start) & (df['entry_time'] <= t_end)]
        if sub.empty:
            continue
        print(f"  {s_name}: {len(sub)} total trades | WR: {(sub['r_multiple'] > 0).mean()*100:.1f}% | Avg R: {sub['r_multiple'].mean():.2f}R | Max R: {sub['r_multiple'].max():.2f}R | Min R: {sub['r_multiple'].min():.2f}R")
        top_trades = sub.sort_values('r_multiple', ascending=False).head(5)
        for _, tr in top_trades.iterrows():
            print(f"     sym: {tr['symbol']:<10} entry: {tr['entry_time']} dir: {tr['direction']:+d} R: {tr['r_multiple']:+5.2f}R")
