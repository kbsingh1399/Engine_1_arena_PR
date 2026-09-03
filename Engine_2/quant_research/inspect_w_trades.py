import os, glob, sys
import pandas as pd
import numpy as np

sys.path.append('Engine_2/quant_research')
from run_s1_test import load_s1_trades, fast_portfolio_backtest_numba
import lightgbm as lgb

fcols = ['direction', 'fund_z', 'basis_z', 'ls_ratio_top', 'rsi_14', 'btc_macro_trend']
df_all = load_s1_trades(fcols)

for w_idx, t_start_str in [(2, '2021-09-15'), (6, '2022-09-15')]:
    t_start = pd.Timestamp(t_start_str, tz='UTC')
    t_end = t_start + pd.DateOffset(months=1)
    is_start = t_start - pd.DateOffset(months=18)
    is_end = t_start - pd.Timedelta(hours=3)
    
    df_is = df_all[(df_all['entry_time'] >= is_start) & (df_all['exit_time'] < is_end)]
    df_oos = df_all[(df_all['entry_time'] >= t_start) & (df_all['entry_time'] < t_end)].copy()
    
    X_is = df_is[fcols].fillna(0.0)
    y_is = df_is['label'].to_numpy(dtype=np.int32)
    
    model = lgb.LGBMClassifier(n_estimators=100, max_depth=4, learning_rate=0.03, min_child_samples=20, random_state=42, verbose=-1)
    model.fit(X_is, y_is)
    
    X_oos = df_oos[fcols].fillna(0.0)
    probs_oos = model.predict_proba(X_oos)[:, 1]
    
    sorted_indices = np.argsort(-probs_oos)
    candidate_indices = sorted_indices[:min(len(sorted_indices), 14)]
    selected_indices = np.sort(candidate_indices)
    
    sub_df = df_oos.iloc[selected_indices]
    print(f"\n=== WINDOW W{w_idx:02d} ({t_start_str}) ===")
    for idx, row in sub_df.iterrows():
        print(f"Sym={row['symbol']:<8} Dir={row['direction']:>2} R={row['r_multiple']:>+6.2f}R Label={row['label']} Entry={str(row['entry_time'])[:16]} Exit={str(row['exit_time'])[:16]}")
