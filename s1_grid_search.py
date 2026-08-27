import sys
from pathlib import Path
import pandas as pd
import numpy as np

ENGINE_DIR = Path('Engine_2')
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

from strategy_engine import (
    ALL_18_SYMBOLS, MONTHS, CAP, RSK, FEE_RT, TP, TRA, MAX_NOTIONAL,
    load_symbol_data, featurize_microstructure,
    sim_tiered, simulate_portfolio_concurrency, simulate_dynamic_risk
)

btc = load_symbol_data('BTCUSDT')
br = featurize_microstructure(btc)

all_dfs = {}
for sym in ALL_18_SYMBOLS:
    df = load_symbol_data(sym)
    if df is not None:
        ref = br if sym != 'BTCUSDT' else None
        all_dfs[sym] = featurize_microstructure(df, ref)

print(f"Loaded {len(all_dfs)} symbols.")

w1_s = pd.Timestamp('2020-09-15')
w1_e = pd.Timestamp('2020-10-15')

results = []
for p8_th in [0.08, 0.12, 0.16, 0.20, 0.24]:
    for zc_th in [0.05, 0.10, 0.15, 0.20]:
        for liq_m in [1.0, 1.2, 1.5, 2.0]:
            trade_list = []
            for sym, dff in all_dfs.items():
                h = dff['High'].values.astype(np.float64); l = dff['Low'].values.astype(np.float64)
                c = dff['Close'].values.astype(np.float64); o = dff['Open'].values.astype(np.float64)
                a = dff['atr'].values.astype(np.float64); ts = dff.index.values
                n_bars = len(ts)
                
                mc = dff['mc'].values; p8 = dff['p8'].values
                ll = dff['liql'].values; ls = dff['liqs'].values
                llm = dff['liqlm'].values; lsm = dff['liqsm'].values
                zc20 = dff['zc20'].values
                
                sg = np.zeros(n_bars, dtype=np.int32)
                mask_l = (mc > 0) & (p8 < -p8_th) & ((ll > llm * liq_m) | (zc20 > zc_th))
                mask_s = (mc < 0) & (p8 > p8_th) & ((ls > lsm * liq_m) | (zc20 < -zc_th))
                sg[mask_l] = 1; sg[mask_s] = -1
                
                cd = 0
                for i in range(1, n_bars - 289):
                    if i < cd or sg[i] == 0: continue
                    ep_val, pnl, r_mult, bh, mae = sim_tiered(h, l, c, i + 1, o[i + 1], a[i], sg[i])
                    if bh > 0:
                        cd = i + int(bh) + 1
                        e_idx = int(min(i + 1, n_bars - 1))
                        ex_idx = int(min(i + int(bh), n_bars - 1))
                        if ts[e_idx] >= w1_s and ts[e_idx] <= w1_e:
                            trade_list.append({
                                'symbol': sym, 'entry_time': ts[e_idx], 'exit_time': ts[ex_idx],
                                'r_multiple': float(r_mult), 'net_pnl': float(r_mult * RSK),
                                'mae_dollar': float(mae * (o[e_idx] / a[i]) * RSK)
                            })
            if len(trade_list) >= 6:
                tdf = pd.DataFrame(trade_list).sort_values('entry_time')
                conc = simulate_portfolio_concurrency(tdf, max_concurrent=2)
                if len(conc) >= 6:
                    pnl, roi, wr, max_dd, executed = simulate_dynamic_risk(conc, cap=CAP)
                    results.append((p8_th, zc_th, liq_m, len(conc), wr, roi, max_dd))

results_df = pd.DataFrame(results, columns=['p8', 'zc', 'liq_m', 'trades', 'wr', 'roi', 'max_dd'])
results_df = results_df.sort_values('roi', ascending=False)
print("\nTop 10 configurations for S1 on Window 1:")
print(results_df.head(10).to_string(index=False))

passed_df = results_df[(results_df['roi'] > 20.0) & (results_df['max_dd'] < 5.0) & (results_df['wr'] > 40.0) & (results_df['trades'] >= 6)]
print(f"\nConfigurations passing ALL 4 GATES on Window 1: {len(passed_df)}")
if len(passed_df) > 0:
    print(passed_df.head(10).to_string(index=False))
