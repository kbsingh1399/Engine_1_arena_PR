import os
import glob
import time
import pandas as pd
import numpy as np
from datetime import datetime
from dateutil.relativedelta import relativedelta
from fast_backtest_numba import fast_portfolio_backtest_numba
from extract_cache import featurize_df, get_btc_ref, gen_symbol_trades, DATA_DIR

CACHE_DIR = "/tmp/s2_cache"

def extract_and_save_novel():
    btc_ref = get_btc_ref()
    files = sorted(glob.glob(os.path.join(DATA_DIR, "*_15m_master_*.parquet")))
    dfs = {os.path.basename(f).split('_')[0]: featurize_df(f, btc_ref) for f in files}
    print("Featurized all datasets.")
    
    feature_cols = [
        'direction', 'cvd_divergence', 'spot_cvd_delta', 'future_cvd_delta', 'spot_cvd_accel',
        'zc4', 'zc10', 'zc20', 'zb20', 'zb4', 'zc_rel_btc', 'zc4_rel_btc',
        'liq_imbalance', 'liq_vol_ratio', 'liq_long_ratio', 'liq_short_ratio', 'liq_zscore_24h',
        'long_liq_zscore', 'short_liq_zscore', 'oi_flush', 'zoi', 'oid', 'oicc', 'fr', 'zfr', 'zls',
        'macro_spread', 'mc', 'p8', 'p21', 'p50', 'p200', 'rsi', 'vol_ratio', 'trend_strength', 'regime'
    ]
    
    novel_archetypes = [
        # N1: Trend Momentum Inflow
        ("N1_TrendInflow", lambda df: (
            ((df['mc'] > 0) & (df['p8'] < -0.06) & (df['zc4'] > 0.0)),
            ((df['mc'] < 0) & (df['p8'] > 0.06) & (df['zc4'] < 0.0))
        )),
        # N2: Liquidation Cascade Flush + RSI Divergence
        ("N2_LiqCascadeFlush", lambda df: (
            ((df['long_liq_zscore'] > 1.2) & (df['rsi'] < 36)),
            ((df['short_liq_zscore'] > 1.2) & (df['rsi'] > 64))
        )),
        # N3: Moderate Value Pullback
        ("N3_ModValuePullback", lambda df: (
            ((df['mc'] > 0) & (df['p8'] < -0.16) & (df['rsi'] < 42)),
            ((df['mc'] < 0) & (df['p8'] > 0.16) & (df['rsi'] > 58))
        )),
        # N4: Pure Spot CVD Delta Continuation
        ("N4_SpotDeltaCont", lambda df: (
            ((df['spot_cvd_delta'] > 0) & (df['p8'] < -0.08) & (df['p200'] > -0.2)),
            ((df['spot_cvd_delta'] < 0) & (df['p8'] > 0.08) & (df['p200'] < 0.2))
        )),
        # N5: Funding Rate Mean Reversion
        ("N5_FundingReversion", lambda df: (
            ((df['zfr'] < -0.6) & (df['p8'] < -0.15)),
            ((df['zfr'] > 0.6) & (df['p8'] > 0.15))
        )),
        # N6: Relative BTC Strength Pulse
        ("N6_RelBTCPulse", lambda df: (
            ((df['zc_rel_btc'] > 0.1) & (df['p8'] < -0.08)),
            ((df['zc_rel_btc'] < -0.1) & (df['p8'] > 0.08))
        )),
        # N7: Volatility Expansion Momentum
        ("N7_VolExpMom", lambda df: (
            ((df['vol_ratio'] > 1.05) & (df['mc'] > 0) & (df['p8'] < -0.08)),
            ((df['vol_ratio'] > 1.05) & (df['mc'] < 0) & (df['p8'] > 0.08))
        )),
        # N8: Deep Squeeze Wide
        ("N8_DeepSqueezeWide", lambda df: (
            ((df['mc'] > 0) & (df['p8'] < -0.18) & (df['zc20'] > df['zb20'] - 0.10)) | ((df['long_liq_zscore'] > 1.5) & (df['rsi'] < 38)),
            ((df['mc'] < 0) & (df['p8'] > 0.18) & (df['zc20'] < df['zb20'] + 0.10)) | ((df['short_liq_zscore'] > 1.5) & (df['rsi'] > 62))
        )),
    ]
    
    for name, sig_fn in novel_archetypes:
        t0 = time.time()
        trades_list = []
        for sym, df in dfs.items():
            mask_l, mask_s = sig_fn(df)
            sig = np.zeros(len(df), dtype=np.int8)
            sig[mask_l] = 1
            sig[mask_s] = -1
            
            highs = df['high'].to_numpy(dtype=np.float64)
            lows = df['low'].to_numpy(dtype=np.float64)
            closes = df['close'].to_numpy(dtype=np.float64)
            next_opens = df['next_open'].to_numpy(dtype=np.float64)
            atrs = df['atr'].to_numpy(dtype=np.float64)
            datetimes = df['datetime_utc'].to_numpy()
            
            res = gen_symbol_trades(highs, lows, closes, next_opens, atrs, sig)
            feat_dict = {c: df[c].to_numpy(dtype=np.float32) for c in feature_cols if c in df.columns}
            
            n = len(df)
            for idx, dr, ep, r_mult, lb, offset, mae in res:
                t = {
                    'symbol': sym, 'entry_time': datetimes[idx], 'exit_time': datetimes[min(int(idx)+int(offset), n-1)],
                    'direction': int(dr), 'entry_price': next_opens[idx], 'exit_price': ep,
                    'atr': atrs[idx], 'mae': mae, 'r_multiple': r_mult, 'label': int(lb)
                }
                for col, arr in feat_dict.items(): t[col] = float(arr[idx])
                trades_list.append(t)
                
        df_a = pd.DataFrame(trades_list)
        df_a['entry_time'] = pd.to_datetime(df_a['entry_time'], utc=True)
        df_a['exit_time'] = pd.to_datetime(df_a['exit_time'], utc=True)
        df_a = df_a.sort_values('entry_time').reset_index(drop=True)
        save_path = os.path.join(CACHE_DIR, f"{name}.parquet")
        df_a.to_parquet(save_path)
        print(f"Saved {name}: {len(df_a):,} trades in {time.time()-t0:.1f}s.")

if __name__ == "__main__":
    extract_and_save_novel()
