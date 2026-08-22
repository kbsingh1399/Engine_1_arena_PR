import sys; sys.path.insert(0,'/home/user/Engine_1_arena_PR')
import numpy as np, pandas as pd, importlib.util, types

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); sys.modules[name]=m
    spec.loader.exec_module(m); return m

# stub numba/lightgbm-free import of run_all_6 featurize by extracting it
import re
src = open('run_all_6.py').read()
# strip the numba + lgb imports by executing only needed pieces
ns = {'np':np, 'pd':pd}
exec("import numpy as np\nimport pandas as pd\nfrom signals_shared import atr\n", ns)
zs_src = re.search(r"^def zs\(.*?\n", src, re.M).group(0)
feat_src = re.search(r"^def featurize\(df,br=None\):.*?\n    return df\n", src, re.M|re.S).group(0)
exec(zs_src, ns); exec(feat_src, ns)
bt_featurize = ns['featurize']

sse = load('sse_stub', 'six_strategy_engine.py')
live_featurize = sse.featurize

rng = np.random.default_rng(7)
n = 1500
idx = pd.date_range('2024-01-01', periods=n, freq='15min')
close = 60000*np.exp(np.cumsum(rng.normal(0,0.002,n)))
df = pd.DataFrame({
  'Open': close*(1+rng.normal(0,0.0005,n)), 'High': close*(1+abs(rng.normal(0,0.002,n))),
  'Low': close*(1-abs(rng.normal(0,0.002,n))), 'Close': close,
  'Volume': abs(rng.normal(1e6,2e5,n)), 'CVD': np.cumsum(rng.normal(0,100,n)),
  'Agg. Liq Long': abs(rng.normal(1e4,3e3,n)), 'Agg. Liq Short': abs(rng.normal(1e4,3e3,n)),
  'Agg. OI': abs(rng.normal(1e8,1e6,n)), 'Agg. Funding Rate': rng.normal(0,1e-4,n),
  'Long/Short Ratio (Account)': abs(rng.normal(1,0.1,n)),
  'Buy Qty': abs(rng.normal(500,50,n)), 'Sell Qty': abs(rng.normal(500,50,n)),
}, index=idx)

a = bt_featurize(df.copy()); b = live_featurize(df.copy())
ca, cb = set(a.columns), set(b.columns)
print("ONLY IN BACKTEST featurize:", sorted(ca-cb))
print("ONLY IN LIVE     featurize:", sorted(cb-ca))
common = sorted(ca & cb)
diffs=[]
for c in common:
    if pd.api.types.is_numeric_dtype(a[c]) and pd.api.types.is_numeric_dtype(b[c]):
        d = np.nanmax(np.abs(a[c].values.astype(float)-b[c].values.astype(float)))
        if d > 1e-9: diffs.append((c, d))
print("NUMERIC DIVERGENCE in shared cols:", diffs if diffs else "none")

d = np.abs(a['rsi'].values-b['rsi'].values)
print("rsi rows differing:", int((d>1e-9).sum()), "of", len(d), "| indices:", np.flatnonzero(d>1e-9)[:10])
print("backtest rsi[0]=", a['rsi'].iloc[0], " live rsi[0]=", b['rsi'].iloc[0])
