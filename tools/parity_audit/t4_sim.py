import sys; sys.path.insert(0,'/home/user/Engine_1_arena_PR')
import numpy as np, importlib.util, re
from risk_config import *
# backtest sim (strip njit)
src=open('run_all_6.py').read()
sim_src=re.search(r"^@njit\(nogil=True\)\ndef sim\(.*?\n    return npnl,r,lb,bh,mae_dollar\n", src, re.M|re.S).group(0).replace("@njit(nogil=True)\n","")
ns={'np':np}
exec("from risk_config import *\nfrom risk_config import FEE_RT as FEE\n", ns); exec(sim_src, ns); bt_sim=ns['sim']
spec=importlib.util.spec_from_file_location('sse','six_strategy_engine.py')
sse=importlib.util.module_from_spec(spec); sys.modules['sse']=sse; spec.loader.exec_module(sse)

rng=np.random.default_rng(11); n=400
print("== sim() PARITY: run_all_6.sim vs six_strategy_engine._sim_trade ==")
print(f"{'#':>3}{'dir':>5}{'BT net':>12}{'LIVE net':>12}{'LIVE*5000':>12}{'BT bh':>7}{'LV bh':>7}{'BT R':>9}{'LV R':>9}")
for k in range(6):
    c=100*np.exp(np.cumsum(rng.normal(0,0.004,n)))
    h=c*(1+abs(rng.normal(0,0.003,n))); l=c*(1-abs(rng.normal(0,0.003,n)))
    e=float(c[0]); a=float(np.mean(h-l)); d=1 if k%2==0 else -1
    b=bt_sim(h,l,c,0,e,a,d); v=sse._sim_trade(h,l,c,0,e,a,d)
    print(f"{k:>3}{d:>5}{b[0]:>12.4f}{v[0]:>12.6f}{v[0]*5000:>12.4f}{b[3]:>7.0f}{v[3]:>7.0f}{b[1]:>9.4f}{v[1]:>9.4f}")
print("\nNOTE: LIVE _sim_trade returns 4 values, BT sim returns 5 (mae_dollar missing):",
      len(v), "vs", len(b))
