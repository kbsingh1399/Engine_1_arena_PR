import sys; sys.path.insert(0,'/home/user/Engine_1_arena_PR')
import numpy as np, importlib.util, re
from risk_config import CAP, RSK, TDD
src=open('run_all_6.py').read()
ns={'np':np}
exec("from risk_config import *\nfrom risk_config import FEE_RT as FEE\n",ns)
exec(re.search(r"^@njit\(nogil=True\)\ndef sim\(.*?\n    return npnl,r,lb,bh,mae_dollar\n",src,re.M|re.S).group(0).replace("@njit(nogil=True)\n",""),ns)
bt_sim=ns['sim']
spec=importlib.util.spec_from_file_location('sse','six_strategy_engine.py')
sse=importlib.util.module_from_spec(spec); sys.modules['sse']=sse; spec.loader.exec_module(sse)

rng=np.random.default_rng(5); n=400
bt_pnls=[]; lv_pnls=[]
for k in range(60):
    c=100*np.exp(np.cumsum(rng.normal(0,0.004,n)))
    h=c*(1+abs(rng.normal(0,0.003,n))); l=c*(1-abs(rng.normal(0,0.003,n)))
    e=float(c[0]); a=float(np.mean(h-l)); d=1 if k%2==0 else -1
    bt_pnls.append(bt_sim(h,l,c,0,e,a,d)[0]); lv_pnls.append(sse._sim_trade(h,l,c,0,e,a,d)[0])
bt=np.array(bt_pnls); lv=np.array(lv_pnls)
def dd(p):
    eq=CAP+np.cumsum(p); return float(((np.maximum.accumulate(eq)-eq)/np.maximum.accumulate(eq)*100).max())
print("== train_six_strategy.best_thresh DD/ROI GATE SCALING ==")
print(f"units of net_pnl  -> backtest: USD  |  live _sim_trade: FRACTION of CAP (x{CAP:.0f} smaller)")
print(f"sum(net_pnl)      -> backtest ${bt.sum():.2f}   live {lv.sum():.6f}")
print(f"roi=(tp/CAP)*100  -> backtest {bt.sum()/CAP*100:.3f}%   live {lv.sum()/CAP*100:.8f}%")
print(f"dd gate value     -> backtest {dd(bt):.4f}%   live {dd(lv):.10f}%   (TDD={TDD})")
print(f"=> live dd is ~{dd(bt)/max(dd(lv),1e-12):.0f}x too small: 'dd<TDD' can never bind.")
