import os, glob, sys
import pandas as pd
import numpy as np

sys.path.append('Engine_2/quant_research')
from run_s1_test import load_s1_trades, fast_portfolio_backtest_numba
import lightgbm as lgb

fcols = ['direction', 'fund_z', 'basis_z', 'ls_ratio_top', 'rsi_14', 'btc_macro_trend']
df_all = load_s1_trades(fcols)

# Check distribution of r_multiples across all trades
print("Total trades in pool:", len(df_all))
r_vals = df_all['r_multiple'].to_numpy()
print(f"Trades with R >= 4.5R: {(r_vals >= 4.5).sum()} ({(r_vals >= 4.5).mean()*100:.1f}%)")
print(f"Trades with 2.0R <= R < 4.5R: {((r_vals >= 2.0) & (r_vals < 4.5)).sum()} ({((r_vals >= 2.0) & (r_vals < 4.5)).mean()*100:.1f}%)")
print(f"Trades with 0.0R <= R < 2.0R: {((r_vals >= 0.0) & (r_vals < 2.0)).sum()} ({((r_vals >= 0.0) & (r_vals < 2.0)).mean()*100:.1f}%)")
print(f"Trades with R < 0.0R: {(r_vals < 0.0).sum()} ({(r_vals < 0.0).mean()*100:.1f}%)")
