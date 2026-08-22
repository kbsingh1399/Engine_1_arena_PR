import sys; sys.path.insert(0,'/home/user/Engine_1_arena_PR')
from signals_shared import STRAT_MAP
import importlib.util
spec = importlib.util.spec_from_file_location('sse','six_strategy_engine.py')
sse = importlib.util.module_from_spec(spec); sys.modules['sse']=sse; spec.loader.exec_module(sse)

SIGNAL_FUNCS = sse.SIGNAL_FUNCS
STRATEGY_NAMES = sse.STRATEGY_NAMES
print("SIGNAL_FUNCS keys (iterated as strat_key):", list(SIGNAL_FUNCS.keys()))
print("STRATEGY_NAMES keys                      :", list(STRATEGY_NAMES.keys()))
print()
print("A) load_models() would look for these files:")
for k in SIGNAL_FUNCS: print("     six_strategy_models/%s_BTCUSDT.pkl" % k)
print("B) train_six_strategy.py actually WRITES these files:")
import re
src=open('train_six_strategy.py').read()
print("     six_strategy_models/S1_BTCUSDT.pkl ... S6_BTCUSDT.pkl   (keys %s)" %
      re.findall(r"'(S\d)':\s*STRAT_MAP", src))
print()
print("C) STRATEGY_NAMES[strat_key] inside the signal loop:")
for k in SIGNAL_FUNCS:
    try:
        print("     STRATEGY_NAMES[%r] -> %r" % (k, STRATEGY_NAMES[k]))
    except KeyError as e:
        print("     STRATEGY_NAMES[%r] -> KeyError %s   <-- FATAL" % (k, e))
    break
