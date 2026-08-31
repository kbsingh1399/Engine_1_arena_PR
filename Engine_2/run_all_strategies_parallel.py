#!/usr/bin/env python3 -u
"""
================================================================================
ENGINE 2: PARALLEL MULTI-STRATEGY OOS HARNESS (S1, S2, S3, S8, S15)
================================================================================
Executes all 5 production strategies in parallel processes with real-time tracking
and generates a consolidated cross-strategy 20/20 OOS summary report.
================================================================================
"""

import os
import sys
import subprocess
import time
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
STRATEGIES = [
    ("S1_Liquidation_Cascade", os.path.join(ROOT_DIR, "s1_liquidation_cascade.py"), os.path.join(ROOT_DIR, "results_s1", "s1_status.json")),
    ("S2_CVD_Momentum", os.path.join(ROOT_DIR, "s2_cvd_momentum.py"), os.path.join(ROOT_DIR, "results_s2", "s2_status.json")),
    ("S3_Macro_Trend_Follow", os.path.join(ROOT_DIR, "s3_macro_trend_follow.py"), os.path.join(ROOT_DIR, "results_s3", "s3_status.json")),
    ("S8_Hybrid_Whale_CVD", os.path.join(ROOT_DIR, "s8_hybrid_whale_cvd.py"), os.path.join(ROOT_DIR, "results_s8", "s8_status.json")),
    ("S15_VWAP_Profile_Conviction", os.path.join(ROOT_DIR, "s15_vwap_profile_conviction.py"), os.path.join(ROOT_DIR, "results_s15_vwap_profile", "s15_status.json"))
]

def run_strategy(name, script_path):
    t0 = time.time()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Launching strategy: {name} ({os.path.basename(script_path)})", flush=True)
    res = subprocess.run([sys.executable, script_path], capture_output=True, text=True, encoding="utf-8", errors="replace")
    elapsed = time.time() - t0
    success = (res.returncode == 0)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {'✅' if success else '❌'} Finished {name} in {elapsed:.1f}s (Exit code: {res.returncode})", flush=True)
    return name, script_path, success, res.stdout, res.stderr, elapsed

def main():
    print("=" * 80)
    print("ENGINE 2: PARALLEL MULTI-STRATEGY 20-WINDOW OOS EXECUTION HARNESS")
    print(f"Time: {datetime.utcnow().isoformat()}Z | Python: {sys.executable}")
    print("=" * 80)
    
    t0_all = time.time()
    
    # Run strategies in parallel (up to 4 concurrent processes)
    max_workers = min(len(STRATEGIES), 4)
    results = {}
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(run_strategy, name, path): name for name, path, _ in STRATEGIES}
        for fut in as_completed(futures):
            name, path, success, stdout, stderr, elapsed = fut.result()
            results[name] = {"success": success, "elapsed": elapsed, "stdout": stdout, "stderr": stderr}
            
    print("\n" + "=" * 80)
    print("🏆 FINAL CONSOLIDATED 20/20 OOS PORTFOLIO SUMMARY")
    print("=" * 80)
    
    table_rows = []
    for name, script_path, status_path in STRATEGIES:
        passes = 0
        total_w = 20
        avg_roi = 0.0
        min_roi = 0.0
        max_dd = 0.0
        avg_wr = 0.0
        total_tr = 0
        
        if os.path.exists(status_path):
            try:
                with open(status_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    passes = sum(1 for w in data if "PASS" in str(w.get("status", "")).upper() or "✅" in str(w.get("status", "")))
                    total_w = len(data)
                    rois = [float(w.get("roi_pct", 0.0)) for w in data]
                    dds = [float(w.get("max_dd_pct", 0.0)) for w in data]
                    wrs = [float(w.get("win_rate_pct", 0.0)) for w in data]
                    total_tr = sum(int(w.get("trades", 0)) for w in data)
                    if rois:
                        avg_roi = sum(rois) / len(rois)
                        min_roi = min(rois)
                    if dds:
                        max_dd = max(dds)
                    if wrs:
                        avg_wr = sum(wrs) / len(wrs)
            except Exception as e:
                pass
                
        status_icon = "✅ 100% PASS" if passes == 20 else f"⚠️ {passes}/{total_w}"
        print(f"{name:<20} | {status_icon} ({passes:2d}/20) | Avg ROI: {avg_roi:+6.2f}% | Min ROI: {min_roi:+6.2f}% | Max DD: {max_dd:5.2f}% | Avg WR: {avg_wr:5.1f}% | Trades: {total_tr:3d}")
        
    print("=" * 80)
    print(f"Total Parallel Suite Execution Completed in {time.time() - t0_all:.1f}s.")

if __name__ == "__main__":
    main()
