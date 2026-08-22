import sys; sys.path.insert(0,'/home/user/Engine_1_arena_PR')
import inspect, importlib.util
from risk_config import RSK, MAX_NOTIONAL, ATR_EPSILON, TP, TRA
spec=importlib.util.spec_from_file_location('bb','engine_components/binance_broker.py')
print("== FINAL VERIFICATION ==")
src=open('Engine_1.py').read(); bsrc=open('engine_components/binance_broker.py').read()
sse=open('six_strategy_engine.py').read(); tr=open('train_six_strategy.py').read()
checks=[
 ("Engine_1 sizing == min(RSK/atr, MAXN/entry)", "min(risk_capital / atr_stop_dist, PARITY_MAX_NOTIONAL / entry_price)" in src),
 ("Engine_1 friction padding removed", "effective_stop_dist" not in src),
 ("Engine_1 ATR_EPSILON guard", "atr_stop_dist <= ATR_EPSILON" in src),
 ("Engine_1 1R drift guard", "RISK DRIFT" in src),
 ("Engine_1 trail uses PARITY_TP/TRA", "PARITY_TP * entry_atr" in src and "PARITY_TRA * entry_atr" in src),
 ("Broker honours caller units", "if units is not None and units > 0" in bsrc),
 ("Broker friction re-derive removed", "TOTAL_FRICTION = 0.0012" not in bsrc),
 ("SIGNAL_FUNCS re-keyed to short keys", "for short_key, long_name in STRATEGY_NAMES.items()" in sse),
 ("load_models fails closed on blocked", "BLOCKED / no validated threshold" in sse),
 ("adaptive lift default OFF", 'ENGINE_ADAPTIVE_LIFT", "0"' in sse),
 ("threshold epsilon slack removed", "effective_thresh - 1e-5" not in sse),
 ("suspend_key is 3-tuple", "(symbol, direction, strat_name)" in sse),
 ("live ATR sentinel guard", "atr_val <= ATR_EPSILON" in sse),
 ("trainer grid starts 0.51", "np.arange(0.51,0.92,0.02)" in tr),
 ("trainer uses MAXTR window", "MINTR*2,MAXTR" in tr),
 ("trainer strict wr>TWR", "wr>TWR and roi>0 and dd<TDD" in tr),
 ("trainer USD normalization", "pnl=pnl*CAP" in tr),
 ("trainer no silent 0.55 fallback", "return best if best is not None else 0.55" not in tr),
]
bad=0
for n,ok in checks:
    print(f"  [{'PASS' if ok else 'FAIL'}] {n}"); bad += not ok
print(f"\n{len(checks)-bad}/{len(checks)} checks passed")
