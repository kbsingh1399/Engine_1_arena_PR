import pandas as pd
from s1 import get_oos_windows
from strategy_engine import MONTHS

def test_oos_alignment():
    print("Verifying OOS Window Alignment between s1.py and strategy_engine.py...")
    
    # Generate windows from s1.py (horizon doesn't matter for test_end/start validation)
    windows = get_oos_windows("2021-01-01", "2027-01-01", 12)
    
    assert len(windows) == len(MONTHS), f"Mismatch in number of windows: {len(windows)} vs {len(MONTHS)}"
    
    for i, (w_dict, (expected_start, expected_end)) in enumerate(zip(windows, MONTHS)):
        # Convert expected to pandas datetime for accurate comparison
        exp_start_dt = pd.to_datetime(expected_start)
        exp_end_dt = pd.to_datetime(expected_end)
        
        # Verify test_start aligns with MONTHS start
        assert w_dict['test_start'] == exp_start_dt, f"Window {i+1} test_start mismatch: {w_dict['test_start']} != {exp_start_dt}"
        
        # Verify test_end aligns with MONTHS end
        assert w_dict['test_end'] == exp_end_dt, f"Window {i+1} test_end mismatch: {w_dict['test_end']} != {exp_end_dt}"
        
    print("[SUCCESS] s1.py strictly follows the strategy_engine.py MONTHS protocol!")

if __name__ == "__main__":
    test_oos_alignment()
