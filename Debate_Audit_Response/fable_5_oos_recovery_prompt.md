# OOS Window Recovery: Drawdown & Zero-ATR Optimization

You are an expert quantitative developer and ML engineer. We are running a 20-window walk-forward backtest for a live trading engine with a strict maximum drawdown constraint of 30.0% (`TDD = 30.0`).

**Important Context:** We have just pushed all our latest local files to the GitHub repository. Please start by reading the entire repository to get the hang of everything (especially `run_all_6.py`, `risk_config.py`, and `sim()` logic) before answering.

Our strategy `S1_Liquidation` recently failed Window 17 strictly due to massive Drawdown (146.8%) and reported a mathematically impossible PnL, because of a near-zero ATR division bug in our sizing logic.

Here is the log for the failed window before the fix:
```text
  W17/20: 2025-05-14->2025-06-14
    Val:1045->th=0.79
    Tr=22 Wn=18 WR=81.8% PnL=$573,094 ROI=11461.9% DD=146.8% MtM-DD=3727.4%
    ABORT! FAILED Window 17
```

### What We Have Patched Locally
1. **Zero-ATR Position Sizing Bug**: We patched `sim()` in `run_all_6.py` with `if atr < 1e-6: return 0.0...` to prevent infinite unit sizing on dead candles.
2. **Validation DD Constraint**: We updated `best_thresh` to explicitly enforce `if wr>0 and roi>0 and dd<TDD:` so the ML threshold optimizer penalizes any threshold that yields >30% DD on the validation set.

### Your Absolute Mandate
You are operating in Agentic Mode. Your goal is to guarantee that **ALL 6 STRATEGIES** pass **ALL 20 OOS WINDOWS** under the new `0.08%` RT fee structure. 

1. **Relentless Execution:** Do NOT stop iterating, testing, and modifying the codebase until you have run the tests against the data in the `backtesting_data` folder and verified that 100% of the windows pass for 100% of the strategies.
2. **Strict Integrity:** 
   - **No Hallucinations:** Do not guess the results. Run the actual code against the actual Parquet files in `backtesting_data`.
   - **No Bias or Future Peeking:** Do not curve-fit, overfit, or introduce any look-ahead bias (future leakage) into the Walk-Forward process to artificially pass the windows. 
3. **Execution Plan:** 
   - Analyze if our local patches are sufficient to guarantee survival. 
   - If a strategy fails any window, rewrite the ML features, threshold logic, or position sizing in `run_all_6.py` to fix it. 
   - Output the finalized, battle-tested Python code patches directly once you have mathematically proven they pass.
