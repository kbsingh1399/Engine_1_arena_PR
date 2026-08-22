#!/usr/bin/env python3
"""Fail unless a run_all_6 result contains 6 x 20 strict OOS passes."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from risk_config import MINTR, TDD, TROI, TWR  # noqa: E402
from signals_shared import SIX_STRAT_NAMES  # noqa: E402


def verify(path: Path) -> None:
    results = json.loads(path.read_text())
    if list(results) != SIX_STRAT_NAMES:
        raise AssertionError(f"strategy set/order mismatch: {list(results)}")

    total = 0
    for strategy in SIX_STRAT_NAMES:
        windows = results[strategy]
        if len(windows) != 20:
            raise AssertionError(f"{strategy}: expected 20 windows, got {len(windows)}")
        if [int(row["w"]) for row in windows] != list(range(1, 21)):
            raise AssertionError(f"{strategy}: window IDs are not exactly 1..20")

        for row in windows:
            total += 1
            values = {key: float(row[key]) for key in ("wr", "roi", "dd", "mtm_dd")}
            if not all(math.isfinite(value) for value in values.values()):
                raise AssertionError(f"{strategy} W{row['w']}: non-finite metric {values}")
            actual = (
                int(row["tr"]) >= MINTR
                and values["wr"] > TWR
                and values["roi"] >= TROI
                and max(values["dd"], values["mtm_dd"]) < TDD
            )
            if row.get("passed") is not True or row.get("verdict") != "PASS" or not actual:
                raise AssertionError(f"{strategy} W{row['w']}: failed strict gates: {row}")

    print(f"PASS: {total}/{len(SIX_STRAT_NAMES) * 20} OOS windows satisfy all strict gates")


if __name__ == "__main__":
    verify(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "all_6_results.json")
