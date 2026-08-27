import sys
from pathlib import Path
import pandas as pd
import numpy as np

ENGINE_DIR = Path('Engine_2')
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

from strategy_engine import (
    ALL_18_SYMBOLS, MONTHS, CAP, RSK, FEE_RT, TP, TRA, MAX_NOTIONAL,
    load_symbol_data, featurize_microstructure, make_signal_s1,
    sim_tiered, simulate_portfolio_concurrency, simulate_dynamic_risk
)

# Load BTC
btc = load_symbol_data('BTCUSDT')
br = featurize_microstructure(btc)

all_s1 = []
er = ['ts', 'Open', 'High', 'Low', 'Close', 'Volume', 'Trades', 'btc_Close', 'btc_CVD']

for sym in ALL_18_SYMBOLS:
    df = load_symbol_data(sym)
    if df is None: continue
    ref = br if sym != 'BTCUSDT' else None
    dff = featurize_microstructure(df, ref)
    
    h = dff['High'].values.astype(np.float64); l = dff['Low'].values.astype(np.float64)
    c = dff['Close'].values.astype(np.float64); o = dff['Open'].values.astype(np.float64)
    a = dff['atr'].values.astype(np.float64); ts = dff.index.values
    n_bars = len(ts)
    
    fc = [col for col in dff.columns if col not in er and pd.api.types.is_numeric_dtype(dff[col])]
    fa = {col: dff[col].values.astype(np.float32) for col in fc}
    
    # Custom tight filter test
    mc = dff['mc'].values; p8 = dff['p8'].values
    ll = dff['liql'].values; ls = dff['liqs'].values
    llm = dff['liqlm'].values; lsm = dff['liqsm'].values
    zc20 = dff['zc20'].values
    
    # Let's test various pullback and liquidation multipliers
    for p8_th in [0.15, 0.20, 0.25]:
        for liq_mult in [1.2, 1.5, 1.8]:
            sg = np.zeros(n_bars, dtype=np.int32)
            mask_l = (mc > 0) & (p8 < -p8_th) & ((ll > llm * liq_mult) | (zc20 > 0.15))
            mask_s = (mc < 0) & (p8 > p8_th) & ((ls > lsm * liq_mult) | (zc20 < -0.15))
            sg[mask_l] = 1; sg[mask_s] = -1
            
            # gen trades
            trades = []
            cd = 0
            for i in range(1, n_bars - 289):
                if i < cd or sg[i] == 0: continue
                ep_val, pnl, r_mult, bh, mae = sim_tiered(h, l, c, i + 1, o[i + 1], a[i], sg[i])
                if bh > 0:
                    cd = i + bh + 1
                    trades.append((i, sg[i], pnl, r_mult, bh, mae))
            
            if trades:
                rr = np.asarray(trades, dtype=np.float64)
                idx = rr[:, 0].astype(np.int64); dr = rr[:, 1].astype(np.int32)
                r_mult = rr[:, 3].copy(); bh = rr[:, 4].astype(np.int64); mae = rr[:, 5].copy()
                entry_idx = np.minimum(idx + 1, n_bars - 1); exit_idx = np.minimum(idx + bh, n_bars - 1)
                entry_price = o[entry_idx]
                
                # window 1 check
                w1_s = pd.Timestamp('2020-09-15'); w1_e = pd.Timestamp('2020-10-15')
                t_df = pd.DataFrame({
                    'symbol': sym, 'entry_time': ts[entry_idx], 'exit_time': ts[exit_idx],
                    'direction': dr, 'entry_price': entry_price, 'r_multiple': r_mult,
                    'mae_dollar': mae * (entry_price / a[idx]) * RSK, # approximate mae
                    'net_pnl': r_mult * RSK
                })
                w1_trades = t_df[(t_df['entry_time'] >= w1_s) & (t_df['entry_time'] <= w1_e)]
                if len(w1_trades) > 0:
                    all_s1.append((p8_th, liq_mult, w1_trades))

print(f"Total parameter combinations evaluated: {len(all_s1)}")
