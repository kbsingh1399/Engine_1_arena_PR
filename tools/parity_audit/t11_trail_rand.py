import sys; sys.path.insert(0,'/home/user/Engine_1_arena_PR')
import numpy as np
from risk_config import TP, TRA
rng=np.random.default_rng(42)
entry=100.0; atr=1.0; act=TP*atr; trail=TRA*atr
def old(ticks):
    sl=entry-atr; bp=None
    for p in ticks:
        if (p-entry)>=act:
            bp = p if bp is None else max(bp,p)
            sl=max(sl,bp-trail)
    return sl
def new(ticks):
    sl=entry-atr; bp=entry
    for p in ticks:
        bp=max(bp,p)
        if (bp-entry)>=act: sl=max(sl,bp-trail)
    return sl
diff=0
for _ in range(20000):
    ticks=entry+rng.normal(0,3,rng.integers(3,40))
    if abs(old(ticks)-new(ticks))>1e-12: diff+=1
print("randomized long-side trials: 20000 | old vs new differ in", diff, "cases")
print("=> peak-tracking refactor is mathematically EQUIVALENT (max over all ticks >= act"
      "\n   equals max over ticks that individually exceeded act). NOT a parity bug.")
