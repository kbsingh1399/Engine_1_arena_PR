import os, sys
import pandas as pd
import numpy as np

sys.path.append(os.path.join(os.getcwd(), "Engine_2"))
from run_optimal_regime_matrix import (
    load_s1_trades, load_s8_trades, load_s2_trades, load_s15_trades,
    load_s4_trades, load_s5_trades, load_s6_trades, load_s7_trades, load_s3_trades,
    get_oos_windows
)

def inspect_all_strategies_in_windows(target_windows=[1, 3, 4, 6, 14, 17]):
    strat_loaders = {
        'S1_Cascade': load_s1_trades,
        'S8_WhaleCVD': load_s8_trades,
        'S2_CVDMom': load_s2_trades,
        'S15_VWAPProfile': load_s15_trades,
        'S4_CVDDivergence': load_s4_trades,
        'S5_LiqSweep': load_s5_trades,
        'S6_VolCompression': load_s6_trades,
        'S7_MeanReversion': load_s7_trades,
        'S3_TrendFollow': load_s3_trades
    }
    
    strategies = {s_name: loader(['direction', 'btc_trend']) for s_name, loader in strat_loaders.items()}
    windows = get_oos_windows(num_windows=20)
    
    for w_idx in target_windows:
        w = windows[w_idx - 1]
        t_start = w['test_start']
        t_end = w['test_end']
        print(f"\n==================== Window W{w_idx:02d} ({t_start.strftime('%Y-%m-%d')} to {t_end.strftime('%Y-%m-%d')}) ====================")
        
        for s_name, df_s in strategies.items():
            if df_s.empty: continue
            df_oos = df_s[(df_s['entry_time'] >= t_start) & (df_s['entry_time'] < t_end)].copy()
            if len(df_oos) == 0: continue
            
            stop_dist = np.maximum(2.0 * df_oos['atr'].values, df_oos['entry_price'].values * 0.0065)
            r_mults = np.where(
                df_oos['direction'].values == 1,
                (df_oos['exit_price'].values - df_oos['entry_price'].values) / stop_dist,
                (df_oos['entry_price'].values - df_oos['exit_price'].values) / stop_dist
            )
            
            wins = (r_mults > 0).sum()
            total = len(r_mults)
            wr = wins / total * 100
            runners_3r = (r_mults >= 2.8).sum()
            runners_5r = (r_mults >= 4.5).sum()
            avg_r = np.mean(r_mults)
            total_r = np.sum(r_mults)
            max_r = np.max(r_mults)
            
            print(f"  {s_name:<20} Total={total:4d} | WR={wr:5.1f}% | >=3R={runners_3r:2d} | >=5R={runners_5r:2d} | MaxR={max_r:+5.2f}R | SumR={total_r:+6.1f}R | AvgR={avg_r:+5.2f}R")

if __name__ == "__main__":
    inspect_all_strategies_in_windows()
