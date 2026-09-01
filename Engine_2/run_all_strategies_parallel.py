#!/usr/bin/env python3
"""
Parallel Suite Runner for All 9 Production Strategies
Runs S1-S8 and S15 in parallel to validate 20/20 OOS performance
"""

import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

STRATEGIES = [
    ('S1', 's1_liquidation_cascade.py', 'Liquidation Cascade Exhaustion'),
    ('S2', 's2_cvd_momentum.py', 'CVD Momentum Breakout'),
    ('S3', 's3_macro_trend_follow.py', 'Macro Multi-Timeframe Trend'),
    ('S4', 's4_cvd_divergence_squeeze.py', 'CVD Divergence & Squeeze'),
    ('S5', 's5_liquidity_sweep_reversal.py', 'Liquidity Sweep Reversal'),
    ('S6', 's6_volatility_compression_breakout.py', 'Volatility Compression Breakout'),
    ('S7', 's7_delta_climax_mean_reversion.py', 'Delta Climax Mean Reversion'),
    ('S8', 's8_hybrid_whale_cvd.py', 'Hybrid Whale CVD Absorption'),
    ('S15', 's15_vwap_profile_conviction.py', 'VWAP Profile Conviction'),
]

def run_strategy(strategy_id, script_name, description):
    """Run a single strategy and return results"""
    print(f"[{strategy_id}] Starting {description}...")
    
    # Get the directory where this script is located
    script_dir = Path(__file__).parent
    
    try:
        result = subprocess.run(
            [sys.executable, script_name],
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout
            cwd=script_dir  # Run from Engine_2 directory
        )
        
        # Check if strategy passed (look for CONQUERED in stdout)
        passed = 'CONQUERED' in result.stdout and 'ALL 20 WINDOWS PASSED' in result.stdout
        
        return {
            'id': strategy_id,
            'name': description,
            'passed': passed,
            'returncode': result.returncode,
            'output_lines': len(result.stdout.split('\n')) if result.stdout else 0,
            'stderr_lines': len(result.stderr.split('\n')) if result.stderr else 0
        }
        
    except subprocess.TimeoutExpired:
        return {
            'id': strategy_id,
            'name': description,
            'passed': False,
            'returncode': -1,
            'error': 'Timeout (>600s)'
        }
    except Exception as e:
        return {
            'id': strategy_id,
            'name': description,
            'passed': False,
            'returncode': -1,
            'error': str(e)
        }

def main():
    print("="*80)
    print("PARALLEL STRATEGY VALIDATION SUITE")
    print("Running all 9 production strategies...")
    print("="*80)
    print()
    
    # Run strategies in parallel (max 4 concurrent to avoid memory issues)
    results = []
    with ProcessPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(run_strategy, sid, script, desc): sid
            for sid, script, desc in STRATEGIES
        }
        
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            
            status = "✅ PASS" if result['passed'] else "❌ FAIL"
            print(f"[{result['id']}] {status} - {result['name']}")
    
    # Sort results by strategy ID
    results.sort(key=lambda x: int(x['id'][1:]))
    
    # Print summary
    print()
    print("="*80)
    print("VALIDATION SUMMARY")
    print("="*80)
    
    passed_count = sum(1 for r in results if r['passed'])
    total_count = len(results)
    
    for result in results:
        status = "✅" if result['passed'] else "❌"
        error = f" ({result.get('error', 'see logs')})" if not result['passed'] else ""
        print(f"{status} {result['id']:3s} | {result['name']}{error}")
    
    print()
    print(f"Result: {passed_count}/{total_count} strategies passed 20/20 OOS windows")
    
    if passed_count == total_count:
        print()
        print("🎉 ALL STRATEGIES CONQUERED! Production-ready deployment package complete.")
        return 0
    else:
        print()
        print("⚠️  Some strategies failed. Check individual logs for details.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
