import os, glob
import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import roc_auc_score

DATA_DIR = 'Engine_2/binance_backtesting_data'
files = sorted(glob.glob(os.path.join(DATA_DIR, '*_15m_master_2020_2026.parquet')))

trade_records = []

for f in files[:8]:
    sym = os.path.basename(f).split('_')[0]
    df = pd.read_parquet(f)
    c, o, h, l = df['close'].to_numpy(), df['open'].to_numpy(), df['high'].to_numpy(), df['low'].to_numpy()
    atr = df['atr_14'].to_numpy()
    ema200 = df['ema_200'].to_numpy()
    fund = df['funding_rate_pct'].fillna(0).to_numpy()
    
    s_fund = pd.Series(fund)
    fund_z = ((s_fund - s_fund.rolling(672, min_periods=96).mean()) / s_fund.rolling(672, min_periods=96).std().replace(0, np.nan)).fillna(0).to_numpy()
    basis_bps = ((df['basis_usd'] / df['close']) * 1e4).fillna(0).to_numpy()
    s_basis = pd.Series(basis_bps)
    basis_z = ((s_basis - s_basis.rolling(96, min_periods=24).mean()) / s_basis.rolling(96, min_periods=24).std().replace(0, np.nan)).fillna(0).to_numpy()
    
    long_cond = (c > ema200) & (fund_z < -0.8) & (c > o)
    short_cond = (c < ema200) & (fund_z > 1.2) & (c < o)
    
    for direction, cond in [(1, long_cond), (-1, short_cond)]:
        indices = np.where(cond)[0]
        for idx in indices[::12]:
            if idx + 96 >= len(c) or atr[idx] <= 0: continue
            entry = o[idx + 1]
            stop_dist = 1.5 * atr[idx]
            cur_stop = entry - direction * stop_dist
            mfe = 0.0
            exit_r = None
            
            for k in range(idx + 1, min(idx + 97, len(c))):
                if direction == 1:
                    if l[k] <= cur_stop:
                        exit_r = (cur_stop - entry) / stop_dist
                        break
                    gain = (h[k] - entry) / stop_dist
                    if gain > mfe: mfe = gain
                    if mfe >= 5.0: cur_stop = max(cur_stop, entry + max(5.0, mfe - 1.0) * stop_dist)
                    elif mfe >= 4.0: cur_stop = max(cur_stop, entry + 2.5 * stop_dist)
                    elif mfe >= 2.5: cur_stop = max(cur_stop, entry + 1.2 * stop_dist)
                    elif mfe >= 1.5: cur_stop = max(cur_stop, entry + 0.1 * stop_dist)
                else:
                    if h[k] >= cur_stop:
                        exit_r = (entry - cur_stop) / stop_dist
                        break
                    gain = (entry - l[k]) / stop_dist
                    if gain > mfe: mfe = gain
                    if mfe >= 5.0: cur_stop = min(cur_stop, entry - max(5.0, mfe - 1.0) * stop_dist)
                    elif mfe >= 4.0: cur_stop = min(cur_stop, entry - 2.5 * stop_dist)
                    elif mfe >= 2.5: cur_stop = min(cur_stop, entry - 1.2 * stop_dist)
                    elif mfe >= 1.5: cur_stop = min(cur_stop, entry - 0.1 * stop_dist)
            
            if exit_r is None:
                exit_r = direction * (c[min(idx + 96, len(c)-1)] - entry) / stop_dist
                
            net_r = exit_r - 0.15
            
            trade_records.append({
                'entry_time_ms': df['open_time_ms'].iloc[idx+1],
                'symbol': sym,
                'direction': direction,
                'fund_z': fund_z[idx],
                'basis_z': basis_z[idx],
                'ls_ratio_top': df['ls_ratio_top'].iloc[idx],
                'rsi_14': df['rsi_14'].iloc[idx],
                'atr_ratio': atr[idx] / (df['atr_100'].iloc[idx] + 1e-8),
                'oi_change_pct': df['oi_change_pct'].iloc[idx],
                'taker_volume_ratio': df['taker_volume_ratio'].iloc[idx],
                'net_r': net_r,
                'label': int(net_r > 0)
            })

tdf = pd.DataFrame(trade_records).sort_values('entry_time_ms').reset_index(drop=True)
print("Total trades gathered:", len(tdf), "Overall WinRate:", round(tdf['label'].mean() * 100, 1), "%")

feat_cols = ['direction', 'fund_z', 'basis_z', 'ls_ratio_top', 'rsi_14', 'atr_ratio', 'oi_change_pct', 'taker_volume_ratio']
X = tdf[feat_cols].fillna(0)
y = tdf['label']

tscv = TimeSeriesSplit(n_splits=5)
oof_preds = np.zeros(len(tdf))

for train_idx, val_idx in tscv.split(X):
    clf = lgb.LGBMClassifier(n_estimators=100, max_depth=4, learning_rate=0.03, min_child_samples=30, random_state=42, verbose=-1)
    clf.fit(X.iloc[train_idx], y.iloc[train_idx])
    oof_preds[val_idx] = clf.predict_proba(X.iloc[val_idx])[:, 1]

val_mask = oof_preds > 0
print("OOF AUC:", round(roc_auc_score(y[val_mask], oof_preds[val_mask]), 3))

# Check top deciles
for p_cut in [0.50, 0.70, 0.85, 0.90]:
    q = np.quantile(oof_preds[val_mask], p_cut)
    top_mask = val_mask & (oof_preds >= q)
    sub = tdf.loc[top_mask]
    print(f"Quantile >= {p_cut*100:.0f}%: Count={len(sub)}, WinRate={round(sub['label'].mean()*100, 1)}%, Mean Net R={round(sub['net_r'].mean(), 3)}R, Total R={round(sub['net_r'].sum(), 1)}R")
