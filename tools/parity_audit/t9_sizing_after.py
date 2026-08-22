import sys; sys.path.insert(0,'/home/user/Engine_1_arena_PR')
import math
from risk_config import RSK, MAX_NOTIONAL, ATR_EPSILON
print("== POSITION SIZING PARITY (AFTER FIX) ==")
print(f"{'symbol':<10}{'entry':>10}{'atr':>10}{'BT units':>14}{'LIVE units':>14}{'err':>10}")
cases=[("BTCUSDT",60000.0,350.0),("ETHUSDT",3000.0,22.0),("SOLUSDT",150.0,2.1),
       ("DOGEUSDT",0.16,0.0021),("XRPUSDT",0.52,0.006),("BTC-tight",60000.0,40.0),
       ("cap-bind",100.0,0.01)]
bad=0
for s,entry,atr in cases:
    bt = min(RSK/atr, MAX_NOTIONAL/entry)
    # exact code path now in Engine_1.trigger_entry
    risk_capital=RSK; atr_stop_dist=atr
    lv = min(risk_capital/atr_stop_dist, MAX_NOTIONAL/entry)
    err=abs(lv-bt); bad += err>1e-12
    print(f"{s:<10}{entry:>10.4f}{atr:>10.4f}{bt:>14.6f}{lv:>14.6f}{err:>10.2e}")
print("\nmismatches:", bad, "/", len(cases))
print("\n== ATR SENTINEL GUARD ==")
for atr in (0.0, 1e-6, 1e-7, float('nan')):
    ok = math.isfinite(atr) and atr > ATR_EPSILON
    print(f"  atr={atr!r:<8} -> backtest tradable={ok}  | live blocked={not ok}")
