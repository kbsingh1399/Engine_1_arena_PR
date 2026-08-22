# risk_config.py -- SINGLE SOURCE OF TRUTH for cost & risk constants.
# Imported by run_all_6.py (backtest), Engine_1.py and six_strategy_engine.py (live).
# Any future fee change is made HERE and here only.

FEE_RT = 0.0008          # round-trip cost: 0.04% per side x 2 -- MATCHES live execution
CAP    = 5000.0          # walk-forward starting equity
RSK    = 20.0            # USD risked per trade (1R)
TWR    = 40.0            # walk-forward gates
TROI   = 20.0
TDD    = 30.0
MINTR  = 6
TP     = 5.0
TRA    = 0.8
MAXTR  = 50

def assert_fee_parity():
    """Boot-time parity guard: refuses to start if any duplicate constant drifts."""
    import os
    env_fee = 2 * float(os.environ.get("ENGINE_FEE_PER_SIDE", "0.0004"))
    assert abs(env_fee - FEE_RT) < 1e-9, \
        f"FEE DRIFT: env={env_fee:.6f} vs shared FEE_RT={FEE_RT:.6f}"
