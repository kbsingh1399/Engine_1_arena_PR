import sys; sys.path.insert(0,'/home/user/Engine_1_arena_PR')
import numpy as np, pandas as pd, re
from risk_config import *
src=open('run_all_6.py').read()
ns={'np':np,'pd':pd}
exec("from risk_config import *\n",ns)
for fn in ['closed_equity_drawdown','mark_to_market_drawdown','best_thresh']:
    m=re.search(r"^def %s\(.*?(?=^def |\Z)"%fn, src, re.M|re.S); exec(m.group(0), ns)
bt_best=ns['best_thresh']

ts=open('train_six_strategy.py').read()
ns2={'np':np,'pd':pd}
exec("from risk_config import FEE_RT as FEE, CAP, RSK, TWR, TDD, MINTR, MAXTR\n",ns2)
exec(re.search(r"^def best_thresh\(.*?(?=^def |\Z)", ts, re.M|re.S).group(0), ns2)
live_best=ns2['best_thresh']

rng=np.random.default_rng(3)
print("== THRESHOLD CALIBRATION PARITY (backtest best_thresh vs live/train best_thresh) ==")
print(f"{'trial':>6}{'n':>5}{'BACKTEST th':>14}{'LIVE th':>10}{'match':>8}")
mism=0
for t in range(12):
    n=rng.integers(40,140)
    prob=np.clip(rng.beta(2,2,n),0.01,0.99)
    pnl=np.where(rng.random(n)<prob, rng.normal(60,25,n), -rng.normal(22,4,n))
    df=pd.DataFrame({'prob':prob,'net_pnl':pnl,
        'entry_time':pd.date_range('2024-01-01',periods=n,freq='6h'),
        'exit_time':pd.date_range('2024-01-01 03:00',periods=n,freq='6h'),
        'mae_dollar':np.abs(rng.normal(12,5,n))})
    b=bt_best(df.copy()); l=live_best(df.copy())
    ok = (b==l)
    mism += (not ok)
    print(f"{t:>6}{n:>5}{str(b):>14}{l:>10.2f}{'OK' if ok else 'MISMATCH':>8}")
print(f"\nmismatches: {mism}/12")
print("\nBACKTEST grid  :", "np.arange(0.51,0.92,0.02) -> min", round(float(np.arange(0.51,0.92,0.02).min()),2),
      "| count window [MINTR*2, MAXTR] =", [MINTR*2, MAXTR], "| gate wr>TWR strictly")
print("LIVE/train grid:", "np.arange(0.50,0.92,0.02) -> min", round(float(np.arange(0.50,0.92,0.02).min()),2),
      "| count window [MINTR, inf) =", [MINTR,'inf'], "| gate wr>=TWR | fallback 0.55 when None")
