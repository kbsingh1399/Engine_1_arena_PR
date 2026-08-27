import sys
from pathlib import Path

import pandas as pd

ENGINE_DIR = Path(__file__).resolve().parents[1] / "Engine_2"
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

from strategy_engine import (  # noqa: E402
    DRAWDOWN_RISK_LIMIT,
    HOUSE_MONEY_RISK_MAX,
    HOUSE_MONEY_RISK_MIN,
    HOUSE_SHIELD_RISK,
    RECON_RISK,
    add_causal_regime_features,
    simulate_dynamic_risk,
)


def _trades(r_multiples, mae_dollars=None, overlapping=False):
    mae_dollars = mae_dollars or [35.0] * len(r_multiples)
    rows = []
    for index, (r_multiple, mae_dollar) in enumerate(
        zip(r_multiples, mae_dollars)
    ):
        spacing = 1 if overlapping else 2
        entry = pd.Timestamp("2020-01-01") + pd.Timedelta(days=index * spacing)
        exit_time = entry + pd.Timedelta(days=2 if overlapping else 1)
        rows.append(
            {
                "entry_time": entry,
                "exit_time": exit_time,
                "r_multiple": r_multiple,
                "net_pnl": r_multiple * 35.0,
                "mae_dollar": mae_dollar,
            }
        )
    return pd.DataFrame(rows)


def test_dual_shield_escalator_and_sticky_house_shield():
    # The first win creates house money, the house loss changes only the next
    # entry to the $45 shield, and no later outcome can resize an earlier entry.
    trades = _trades([5.0, -0.1, 1.0])
    _, _, _, max_dd, executed = simulate_dynamic_risk(trades)

    assert executed.iloc[0]["trade_risk"] == RECON_RISK
    assert HOUSE_MONEY_RISK_MIN <= executed.iloc[1]["trade_risk"] <= HOUSE_MONEY_RISK_MAX
    assert executed.iloc[2]["trade_risk"] == HOUSE_SHIELD_RISK
    assert executed["risk_mode"].tolist() == ["recon", "house", "house-shield"]
    assert max_dd < 4.0


def test_target_lock_waits_for_six_completed_trades_and_no_open_positions():
    trades = _trades([1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 10.0, 1.0])
    _, roi, wr, _, executed = simulate_dynamic_risk(trades)

    assert roi > 20.0
    assert wr > 40.0
    assert len(executed) == 7


def test_allocator_does_not_use_unsettled_profit_for_house_money():
    trades = _trades([5.0, 1.0], overlapping=True)
    _, _, _, _, executed = simulate_dynamic_risk(trades)

    # The first trade has not exited when the second entry is sized.
    assert executed["trade_risk"].tolist() == [RECON_RISK, RECON_RISK]


def test_allocator_reserves_mae_inside_drawdown_budget():
    trades = _trades([-1.0], mae_dollars=[350.0])
    _, _, _, max_dd, executed = simulate_dynamic_risk(trades)

    assert max_dd <= DRAWDOWN_RISK_LIMIT * 100.0 + 1e-9
    assert executed.iloc[0]["mae_dollar"] <= 5000.0 * DRAWDOWN_RISK_LIMIT + 1e-9


def test_regime_features_are_causal_at_each_decision_bar():
    close = pd.Series(100.0 + pd.RangeIndex(900).to_numpy(dtype=float))
    frame = pd.DataFrame(
        {
            "Close": close,
            "atr": 1.0,
            "ef": close,
            "es": close - 1.0,
        }
    )
    changed = frame.copy()
    changed.loc[700:, "Close"] = 10_000.0

    original_features = add_causal_regime_features(frame.copy())
    changed_features = add_causal_regime_features(changed)
    for column in (
        "realized_vol_short",
        "realized_vol_long",
        "vol_ratio",
        "trend_strength",
        "regime",
    ):
        pd.testing.assert_series_equal(
            original_features.loc[:699, column],
            changed_features.loc[:699, column],
            check_names=False,
        )


def test_runner_has_no_fail_fast_environment_escape_hatch():
    for runner in (
        Path(__file__).resolve().parents[1] / "run_all_6.py",
        Path(__file__).resolve().parents[1] / "Engine_2" / "run_all_6.py",
    ):
        source = runner.read_text(encoding="utf-8")
        assert "NO_FAIL_FAST" not in source
        assert "if not passed:" in source


def test_optuna_search_space_and_causal_s1_filter():
    from strategy_engine import OPTUNA_DEFAULTS, apply_signal_hyperparameters

    assert OPTUNA_DEFAULTS['pullback_threshold'] == 0.12
    assert 0.05 <= OPTUNA_DEFAULTS['cvd_momentum'] <= 0.25
    assert 1.0 <= OPTUNA_DEFAULTS['liquidation_multiplier'] <= 2.0
    assert 0.50 <= OPTUNA_DEFAULTS['probability_threshold'] <= 0.85
    assert 3 <= OPTUNA_DEFAULTS['tree_depth'] <= 6
    assert 0.01 <= OPTUNA_DEFAULTS['learning_rate'] <= 0.08

    candidates = pd.DataFrame(
        [
            {
                'direction': 1,
                'p8': -0.20,
                'zc20': 0.15,
                'liq_long_ratio': 1.0,
                'liq_short_ratio': 1.0,
            },
            {
                'direction': 1,
                'p8': -0.04,
                'zc20': 0.01,
                'liq_long_ratio': 1.0,
                'liq_short_ratio': 1.0,
            },
        ]
    )
    selected = apply_signal_hyperparameters(
        candidates,
        'S1_Liquidation',
        {
            'pullback_threshold': 0.12,
            'cvd_momentum': 0.10,
            'liquidation_multiplier': 1.20,
        },
    )
    assert len(selected) == 1


def test_sparse_history_uses_cold_start_calibration_marker():
    from strategy_engine import calibrate_in_sample_threshold

    timestamps = pd.date_range("2020-01-01", periods=10, freq="15min")
    sparse = pd.DataFrame(
        {'entry_time': timestamps, 'exit_time': timestamps + pd.Timedelta(minutes=15)}
    )
    model, features, threshold, params = calibrate_in_sample_threshold(
        sparse, pd.Timestamp("2020-01-02"), "S1_Liquidation", return_params=True
    )

    assert model is None
    assert features is None
    assert threshold == 0.55
    assert params['cold_start'] is True


def test_cold_start_rule_uses_current_bar_confirmation_only():
    from strategy_engine import apply_cold_start_rule

    timestamp = pd.Timestamp("2020-01-01")
    candidates = pd.DataFrame(
        [
            {
                'entry_time': timestamp,
                'direction': 1,
                'p8': -0.20,
                'bsr': 0.60,
                'zc20': 0.10,
                'vr5': 1.0,
                'liq_long_ratio': 1.1,
                'liq_short_ratio': 1.0,
            },
            {
                'entry_time': timestamp + pd.Timedelta(minutes=15),
                'direction': 1,
                'p8': -0.04,
                'bsr': 0.49,
                'zc20': 0.01,
                'vr5': 1.0,
                'liq_long_ratio': 1.0,
                'liq_short_ratio': 1.0,
            },
        ]
    )

    selected = apply_cold_start_rule(candidates, 'S1_Liquidation')
    assert len(selected) == 1
    assert selected.iloc[0]['direction'] == 1


def test_cold_start_conviction_is_causal_and_sorted_within_timestamp():
    from strategy_engine import apply_cold_start_rule

    timestamp = pd.Timestamp("2020-01-01")
    candidates = pd.DataFrame(
        [
            {'entry_time': timestamp, 'direction': 1, 'p8': -0.20, 'bsr': 0.60, 'zc20': 0.10, 'vr5': 1.0},
            {'entry_time': timestamp, 'direction': 1, 'p8': -0.40, 'bsr': 0.60, 'zc20': 0.20, 'vr5': 1.0},
            {'entry_time': timestamp, 'direction': 1, 'p8': -0.10, 'bsr': 0.60, 'zc20': 0.30, 'vr5': 1.0},
        ]
    )

    selected = apply_cold_start_rule(candidates, 'S1_Liquidation')
    assert selected['conviction'].round(6).tolist() == [0.60, 0.40, 0.30]


def test_same_timestamp_entries_use_conviction_and_keep_slots_occupied():
    from strategy_engine import simulate_portfolio_concurrency

    timestamp = pd.Timestamp("2020-01-01")
    trades = pd.DataFrame(
        [
            {"entry_time": timestamp, "exit_time": timestamp, "route_score": 0.1},
            {"entry_time": timestamp, "exit_time": timestamp, "route_score": 0.9},
            {"entry_time": timestamp, "exit_time": timestamp, "route_score": 0.8},
        ]
    )

    selected = simulate_portfolio_concurrency(trades, max_concurrent=2)
    assert selected["route_score"].tolist() == [0.9, 0.8]
