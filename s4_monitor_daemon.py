"""
15-Minute Health & Status Monitor Daemon for Strategy S4 (RSI Extreme Mean Reversion)
Monitors Engine_2/results_s4 status, verifies all 20 OOS windows, and logs health reports.
"""

import os
import sys
import time
import json
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATUS_FILE = os.path.join(SCRIPT_DIR, "Engine_2", "results_s4", "s4_status.json")
WINNING_FILE = os.path.join(SCRIPT_DIR, "Engine_2", "results_s4", "winning_configuration.json")
LOG_FILE = os.path.join(SCRIPT_DIR, "Engine_2", "results_s4", "monitor_health.log")

def log_msg(msg):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def check_status():
    log_msg("🔍 [15-MIN HEALTH CHECK] Starting Strategy S4 (RSI Mean Reversion) heartbeat inspection...")
    
    if not os.path.exists(STATUS_FILE):
        log_msg("⚠️ S4 Status file not found yet.")
        return False
        
    try:
        with open(STATUS_FILE, "r") as f:
            records = json.load(f)
            
        passed_count = sum(1 for r in records if "PASS" in r.get("status", ""))
        total_count = len(records)
        
        log_msg(f"📊 S4 Progress: {passed_count}/{total_count} windows passed.")
        
        for r in records:
            w = r.get('window')
            tr = r.get('trades')
            wr = r.get('win_rate_pct')
            roi = r.get('roi_pct')
            dd = r.get('max_dd_pct')
            st = r.get('status')
            arch = r.get('archetype', 'N/A')
            log_msg(f"   Window {w:02d}: Trades={tr:2d}, WR={wr:5.1f}%, ROI={roi:6.2f}%, MaxDD={dd:5.2f}% [{arch}] -> {st}")
            
        if passed_count == 20:
            log_msg("🏆 ALL 20 WINDOWS FOR STRATEGY S4 VERIFIED AND PASSING CONCURRENTLY! SYSTEM HEALTH: EXCELLENT.")
        return passed_count == 20
    except Exception as e:
        log_msg(f"❌ Error reading S4 status: {e}")
        return False

def main():
    log_msg("🚀 S4 15-Minute Health Monitor Daemon Initialized.")
    # Run immediate check
    check_status()
    
    # 15-minute interval loop (900 seconds)
    interval_seconds = 900
    while True:
        log_msg(f"💤 Sleeping for {interval_seconds // 60} minutes until next heartbeat...")
        time.sleep(interval_seconds)
        check_status()

if __name__ == "__main__":
    main()
