#!/usr/bin/env python3
"""
================================================================================
ENGINE 2: PARALLEL MULTI-STRATEGY CONQUEST RUNNER (ALL 9 STRATEGIES)
================================================================================
Concurrent execution of all 9 institutional strategies across 20 OOS windows:
  - S1:  Liquidation Cascade & Absorption
  - S2:  CVD Momentum Breakout
  - S3:  Macro Trend Following
  - S4:  CVD Divergence & Liquidity Squeeze
  - S5:  Liquidity Sweep & Absorption Reversal
  - S6:  Volatility Compression & ATR Breakout
  - S7:  Delta Climax Mean Reversion
  - S8:  Hybrid Whale CVD Absorption
  - S15: VWAP Profile Conviction
================================================================================
"""

import os, sys, time, subprocess
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
from concurrent.futures import ProcessPoolExecutor, as_completed

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

STRATEGY_SCRIPTS = [
    ("S1_Liquidation_Cascade", os.path.join(SCRIPT_DIR, "s1_liquidation_cascade.py")),
    ("S2_CVD_Momentum", os.path.join(SCRIPT_DIR, "s2_cvd_momentum.py")),
    ("S3_Macro_Trend_Follow", os.path.join(SCRIPT_DIR, "s3_macro_trend_follow.py")),
    ("S4_CVD_Divergence_Squeeze", os.path.join(SCRIPT_DIR, "s4_cvd_divergence_squeeze.py")),
    ("S5_Liquidity_Sweep_Reversal", os.path.join(SCRIPT_DIR, "s5_liquidity_sweep_reversal.py")),
    ("S6_Vol_Compression_Breakout", os.path.join(SCRIPT_DIR, "s6_volatility_compression_breakout.py")),
    ("S7_Delta_Climax_MeanRev", os.path.join(SCRIPT_DIR, "s7_delta_climax_mean_reversion.py")),
    ("S8_Hybrid_Whale_CVD", os.path.join(SCRIPT_DIR, "s8_hybrid_whale_cvd.py")),
    ("S15_VWAP_Profile_Conviction", os.path.join(SCRIPT_DIR, "s15_vwap_profile_conviction.py")),
]

def run_single_strategy(name_and_path):
    name, script_path = name_and_path
    if not os.path.exists(script_path):
        return name, -1, f"File not found: {script_path}", 0.0
        
    start_t = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            cwd=SCRIPT_DIR
        )
        elapsed = time.time() - start_t
        return name, proc.returncode, proc.stdout, elapsed
    except Exception as e:
        elapsed = time.time() - start_t
        return name, -1, str(e), elapsed

def main():
    print("=" * 80)
    print("LAUNCHING PARALLEL MULTI-STRATEGY SUITE (9 STRATEGIES x 20 OOS WINDOWS)")
    print(f"Time: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} | Python: {sys.executable}")
    print("=" * 80)
    
    total_start = time.time()
    results = {}
    
    with ProcessPoolExecutor(max_workers=min(len(STRATEGY_SCRIPTS), 6)) as executor:
        futures = {executor.submit(run_single_strategy, item): item[0] for item in STRATEGY_SCRIPTS}
        for future in as_completed(futures):
            name = futures[future]
            try:
                s_name, code, stdout, elapsed = future.result()
                results[s_name] = (code, stdout, elapsed)
                print(f"\n--- Output from {s_name} (Completed in {elapsed:.1f}s) ---\n")
                print(stdout)
            except Exception as exc:
                print(f"[ERROR] Strategy {name} generated an exception: {exc}")

    print("\n" + "=" * 80)
    print("FINAL CONSOLIDATED PARALLEL SUITE EXECUTION")
    print("=" * 80)
    for name, (code, stdout, elapsed) in results.items():
        status = "COMPLETED" if code == 0 else f"FAILED (code {code})"
        print(f"• {name:<28} | {status:<10} | Runtime: {elapsed:.1f}s")
    print("=" * 80)
    print(f"Total Parallel Suite Execution Completed in {time.time() - total_start:.1f}s.\n")

if __name__ == "__main__":
    main()
