import sys
from pathlib import Path

import numpy as np
import pandas as pd

ENGINE_DIR = Path(__file__).resolve().parents[1] / "Engine_2"
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

from strategy_engine import (  # noqa: E402
    MONTHS,
    TIER1_LOCK_R,
    TIER2_LOCK_R,
    purged_time_split,
    sim_tiered,
)


def test_stage1_schedule_has_twenty_supplied_windows():
    assert len(MONTHS) == 20
    assert MONTHS[0] == ("2021-03-15", "2021-04-15")
    assert MONTHS[-1] == ("2026-03-15", "2026-04-15")


def test_purged_split_removes_overlapping_labels_and_embargo():
    events = pd.DataFrame(
        {
            "entry_time": pd.to_datetime(
                ["2021-01-01", "2021-01-02", "2021-01-04", "2021-01-05"]
            ),
            "exit_time": pd.to_datetime(
                ["2021-01-02", "2021-01-04", "2021-01-05", "2021-01-06"]
            ),
        }
    )
    train, validation = purged_time_split(
        events, "2021-01-04", "2021-01-07", embargo_hours=24
    )

    assert train["entry_time"].dt.strftime("%Y-%m-%d").tolist() == ["2021-01-01"]
    assert validation["entry_time"].dt.strftime("%Y-%m-%d").tolist() == ["2021-01-04", "2021-01-05"]
    assert train["exit_time"].max() < pd.Timestamp("2021-01-03")


def test_fee_protective_profit_tiers_and_five_r_runner():
    tier1 = sim_tiered(
        np.array([100.0, 102.0, 101.1]),
        np.array([100.0, 101.5, 101.1]),
        np.array([100.0, 101.5, 101.1]),
        0,
        100.0,
        1.0,
        1,
    )
    tier2 = sim_tiered(
        np.array([100.0, 103.0, 101.9]),
        np.array([100.0, 102.5, 101.9]),
        np.array([100.0, 102.5, 101.9]),
        0,
        100.0,
        1.0,
        1,
    )
    runner = sim_tiered(
        np.array([100.0, 105.5, 104.6]),
        np.array([100.0, 105.0, 104.6]),
        np.array([100.0, 105.0, 104.6]),
        0,
        100.0,
        1.0,
        1,
    )

    assert tier1[1] > TIER1_LOCK_R - 0.1
    assert tier2[1] > TIER2_LOCK_R - 0.1
    assert runner[1] > 4.5
