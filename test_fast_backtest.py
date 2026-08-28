import time
import pandas as pd
import numpy as np
from fast_backtest_numba import fast_portfolio_backtest_numba

# Generate dummy trades
np.random.seed(42)
n = 100
entry_times = np.arange(1000, 1000 + n * 15, 15, dtype=np.int64)
exit_times = entry_times + np.random.randint(15, 120, size=n, dtype=np.int64)
entry_prices = np.random.uniform(50, 100, size=n).astype(np.float64)
exit_prices = entry_prices * (1.0 + np.random.uniform(-0.02, 0.04, size=n))
atrs = (entry_prices * 0.01).astype(np.float64)
maes = (atrs * 0.5).astype(np.float64)
directions = np.random.choice([1, -1], size=n).astype(np.int8)
probs = np.random.uniform(0.5, 0.8, size=n).astype(np.float64)

# Warm up numba
fast_portfolio_backtest_numba(
    entry_times, exit_times, entry_prices, exit_prices, atrs, maes, directions, probs
)

t0 = time.time()
for _ in range(10000):
    roi, dd, wr, tr = fast_portfolio_backtest_numba(
        entry_times, exit_times, entry_prices, exit_prices, atrs, maes, directions, probs
    )
el = time.time() - t0
print(f"10,000 backtests completed in {el:.3f}s ({el/10000*1e6:.1f} microseconds per backtest)!")
print(f"Sample Result: ROI={roi*100:.2f}%, DD={dd*100:.2f}%, WR={wr*100:.1f}%, Trades={tr}")
