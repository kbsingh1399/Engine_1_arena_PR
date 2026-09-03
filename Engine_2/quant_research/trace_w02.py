import os, sys
import pandas as pd
import numpy as np

sys.path.append('Engine_2/quant_research')
from run_s1_test import load_s1_trades
import lightgbm as lgb

fcols = ['direction', 'fund_z', 'basis_z', 'ls_ratio_top', 'rsi_14', 'btc_macro_trend']
df_all = load_s1_trades(fcols)

t_start = pd.Timestamp('2021-09-15', tz='UTC')
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
sub_df = df_oos.iloc[selected_indices].copy()

capital = 5000.0
peak_capital = 5000.0
base_risk = 55.0
max_house_risk = 260.0
min_defense_risk = 15.0
dd_limit = 0.042

print("\nW02 Trade-by-Trade Progression:")
for idx, r in sub_df.iterrows():
    realized_pnl = capital - 5000.0
    closed_drawdown = max(0.0, peak_capital - capital)
    drawdown_budget = max(0.0, peak_capital * dd_limit - closed_drawdown)
    target_risk = max(min_defense_risk, base_risk + 0.85 * realized_pnl if realized_pnl > 0 else base_risk * max(0.0, 1.0 - abs(realized_pnl)/190.0))
    cur_risk = max(min_defense_risk, min(target_risk, drawdown_budget / 1.15))
    
    stop_dist = max(2.0 * r['atr'], r['entry_price'] * 0.0065)
    units = cur_risk / stop_dist
    gross_pnl = (r['exit_price'] - r['entry_price']) * units if r['direction'] == 1 else (r['entry_price'] - r['exit_price']) * units
    fee = (r['entry_price'] + r['exit_price']) * units * 0.00045
    net_pnl = gross_pnl - fee
    capital += net_pnl
    if capital > peak_capital: peak_capital = capital
    dd_pct = (peak_capital - capital) / peak_capital * 100.0
    print("Sym=%-8s R=%+5.2fR Risk=$%5.1f NetPnL=$%+6.1f Cap=$%6.1f DD=%4.2f%%" % (
        r['symbol'], r['r_multiple'], cur_risk, net_pnl, capital, dd_pct
    ))

print("Final ROI: %+.2f%%" % ((capital - 5000.0) / 5000.0 * 100.0))
