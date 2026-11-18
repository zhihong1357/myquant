import numpy as np
import pandas as pd
import pytest

from myquant.stats.event_study import event_study


def _series(values: list[float]) -> pd.Series:
    index = pd.date_range("2024-01-01", periods=len(values), freq="D", tz="UTC")
    return pd.Series(values, index=index, dtype=float)


def test_event_study_calculates_car_against_zero_benchmark():
    returns = _series([0.0, 0.01, 0.02, 0.0, -0.01, 0.03, 0.0, 0.0, 0.01, 0.0])
    events = [returns.index[2], returns.index[7]]
    result = event_study(
        returns, events, pre_event_steps=1, post_event_steps=1
    )
    assert result.event_count == 2
    assert result.cluster_count == 2
    assert result.events[0].cumulative_abnormal_return == pytest.approx(0.03)
    assert result.events[1].cumulative_abnormal_return == pytest.approx(0.01)
    assert result.mean_cluster_car == pytest.approx(0.02)
    assert result.two_sided_p_value is not None


def test_overlapping_windows_are_one_inference_cluster():
    returns = _series([0.0, 0.01, 0.02, 0.03, 0.0, 0.0, 0.01, 0.0, 0.0, 0.0])
    result = event_study(
        returns,
        [returns.index[2], returns.index[3], returns.index[7]],
        pre_event_steps=1,
        post_event_steps=1,
    )
    assert result.event_count == 3
    assert result.cluster_count == 2
    assert [item.cluster_id for item in result.events] == [0, 0, 1]
    assert result.clusters[0].event_count == 2


def test_expected_returns_are_subtracted_before_car():
    returns = _series([0.02, 0.03, 0.04, 0.02, 0.03, 0.04, 0.02, 0.03])
    expected = _series([0.01] * 8)
    result = event_study(
        returns, [returns.index[2], returns.index[6]],
        pre_event_steps=0, post_event_steps=1,
        expected_returns=expected,
    )
    # Window is [pos - pre, pos + post] inclusive, abnormal = observed - expected
    # per observation: event 0 -> (0.04-0.01) + (0.02-0.01) = 0.04;
    # event 1 -> (0.02-0.01) + (0.03-0.01) = 0.03.
    assert result.events[0].cumulative_abnormal_return == pytest.approx(0.04)
    assert result.events[1].cumulative_abnormal_return == pytest.approx(0.03)


def test_event_study_omits_inference_for_one_cluster():
    returns = _series([0.0, 0.01, 0.02, 0.03, 0.0, 0.0])
    result = event_study(
        returns, [returns.index[2], returns.index[3]],
        pre_event_steps=1, post_event_steps=1,
    )
    assert result.cluster_count == 1
    assert result.cluster_standard_error is None
    assert result.two_sided_p_value is None


def test_event_study_rejects_invalid_time_and_missing_values():
    returns = _series([0.0, 0.01, np.nan, 0.03, 0.0, 0.0])
    with pytest.raises(ValueError, match="finite"):
        event_study(returns, [returns.index[2]], pre_event_steps=0, post_event_steps=0)

    complete = _series([0.0, 0.01, 0.02, 0.03, 0.0, 0.0])
    with pytest.raises(ValueError, match="timezone-aware"):
        event_study(
            complete, [pd.Timestamp("2024-01-03")],
            pre_event_steps=0, post_event_steps=0,
        )
    with pytest.raises(ValueError, match="fit completely"):
        event_study(
            complete, [complete.index[0]],
            pre_event_steps=1, post_event_steps=0,
        )


def test_event_study_requires_exact_expected_return_alignment():
    returns = _series([0.0, 0.01, 0.02, 0.03, 0.0, 0.0])
    expected = _series([0.0] * 5)
    with pytest.raises(ValueError, match="exactly match"):
        event_study(
            returns, [returns.index[2]],
            pre_event_steps=0, post_event_steps=0,
            expected_returns=expected,
        )
