import sys; sys.path.insert(0,'/home/user/Engine_1_arena_PR')
from risk_config import RSK, MAX_NOTIONAL, FEE_RT
ENGINE_RISK_USD=20.0; TOTAL_FRICTION=FEE_RT+0.0004
print("== POSITION SIZING PARITY ==")
print(f"{'symbol':<9}{'entry':>10}{'atr':>10}{'BT units':>14}{'LIVE units':>14}{'err %':>9}")
cases=[("BTCUSDT",60000.0,350.0),("ETHUSDT",3000.0,22.0),("SOLUSDT",150.0,2.1),
       ("DOGEUSDT",0.16,0.0021),("XRPUSDT",0.52,0.006),("BTC-tight",60000.0,40.0)]
for s,entry,atr in cases:
    bt  = min(RSK/atr, MAX_NOTIONAL/entry)
    eff = atr + entry*TOTAL_FRICTION
    lv  = ENGINE_RISK_USD/eff
    if lv*entry > MAX_NOTIONAL: lv = MAX_NOTIONAL/entry
    print(f"{s:<9}{entry:>10.4f}{atr:>10.4f}{bt:>14.4f}{lv:>14.4f}{(lv/bt-1)*100:>8.2f}%")
