"""Tests for the constant-mean event-study helpers (synthetic panels)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from myquant.studies.event_windows import (
    constant_mean_expected_returns,
    filter_events_to_panel,
    one_sided_normal_p_value,
    run_constant_mean_event_study,
    standardized_mean_car,
)

INDEX = pd.date_range("2020-01-01", periods=200, freq="D", tz="UTC")


def _series(values: np.ndarray) -> pd.Series:
    return pd.Series(values, index=INDEX, name="returns")


def test_filter_events_excludes_incomplete_windows() -> None:
    events = [
        INDEX[10],  # estimation window [-60,-11] does not fit
        INDEX[100],  # fits
        INDEX[199],  # event window [0,+1] does not fit
        INDEX[150] + pd.Timedelta(hours=1),  # not in the index
    ]
    included, excluded = filter_events_to_panel(
        INDEX,
        events,
        estimation_start_steps=60,
        estimation_end_steps=11,
        pre_event_steps=0,
        post_event_steps=1,
    )
    assert included == (INDEX[100],)
    assert len(excluded) == 3
    reasons = [item["reason"] for item in excluded]
    assert any("estimation window" in reason for reason in reasons)
    assert any("past the panel end" in reason for reason in reasons)
    assert any("not present" in reason for reason in reasons)


def test_filter_events_rejects_bad_window_parameters() -> None:
    with pytest.raises(ValueError, match="must exceed"):
        filter_events_to_panel(
            INDEX,
            [INDEX[100]],
            estimation_start_steps=11,
            estimation_end_steps=60,
            pre_event_steps=0,
            post_event_steps=1,
        )
    with pytest.raises(ValueError, match="at least 1"):
        filter_events_to_panel(
            INDEX,
            [INDEX[100]],
            estimation_start_steps=60,
            estimation_end_steps=0,
            pre_event_steps=0,
            post_event_steps=1,
        )


def test_expected_returns_carry_estimation_means_on_window_days() -> None:
    rng = np.random.default_rng(7)
    values = rng.normal(0.01, 0.02, size=200)
    returns = _series(values)
    events = [INDEX[100], INDEX[150]]
    expected = constant_mean_expected_returns(
        returns,
        events,
        estimation_start_steps=60,
        estimation_end_steps=11,
        pre_event_steps=0,
        post_event_steps=1,
    )
    # Estimation window [-60,-11] is positions 40..89 for the first event.
    assert expected.iloc[100] == pytest.approx(float(np.mean(values[40:90])))
    assert expected.iloc[101] == pytest.approx(float(np.mean(values[40:90])))
    # Estimation window for the second event is positions 90..139.
    assert expected.iloc[150] == pytest.approx(float(np.mean(values[90:140])))
    assert expected.iloc[151] == pytest.approx(float(np.mean(values[90:140])))
    # Off-window days carry the 0.0 fill (never summed by the estimator).
    assert expected.iloc[0] == 0.0
    assert expected.iloc[120] == 0.0


def test_expected_returns_reject_overlapping_windows() -> None:
    values = np.zeros(200)
    returns = _series(values)
    with pytest.raises(ValueError, match="overlap"):
        constant_mean_expected_returns(
            returns,
            [INDEX[100], INDEX[101]],
            estimation_start_steps=60,
            estimation_end_steps=11,
            pre_event_steps=0,
            post_event_steps=1,
        )


def test_constant_mean_event_study_recovers_a_known_shift() -> None:
    # Zero-mean noise plus a -0.05 shift on every event window [0,+1].
    rng = np.random.default_rng(11)
    values = rng.normal(0.0, 0.01, size=200)
    events = [INDEX[100], INDEX[130], INDEX[160], INDEX[190]]
    for event in events:
        position = INDEX.get_loc(event)
        values[position : position + 2] += -0.05
    returns = _series(values)
    result = run_constant_mean_event_study(
        returns,
        events,
        estimation_start_steps=60,
        estimation_end_steps=11,
        pre_event_steps=0,
        post_event_steps=1,
    )
    assert result.event_count == 4
    assert result.cluster_count == 4  # no overlaps: one cluster per event
    # Each CAR is about -0.10 (two days at -0.05) minus a near-zero mean.
    assert result.mean_cluster_car == pytest.approx(-0.10, abs=0.01)
    assert result.z_statistic is not None and result.z_statistic < -5
    assert result.two_sided_p_value is not None
    assert result.two_sided_p_value < 1e-6
    assert standardized_mean_car(result) < -1.0


def test_constant_mean_event_study_with_flat_series() -> None:
    # No shift: CARs are zero, the z-statistic is unavailable (SE = 0).
    values = np.zeros(200)
    returns = _series(values)
    result = run_constant_mean_event_study(
        returns,
        [INDEX[100], INDEX[150]],
        estimation_start_steps=60,
        estimation_end_steps=11,
        pre_event_steps=0,
        post_event_steps=1,
    )
    assert result.mean_cluster_car == 0.0
    assert result.cluster_standard_error == 0.0
    assert result.z_statistic is None
    assert result.two_sided_p_value is None
    assert standardized_mean_car(result) == 0.0


def test_one_sided_normal_p_value() -> None:
    assert one_sided_normal_p_value(0.0, direction="less") == pytest.approx(0.5)
    assert one_sided_normal_p_value(0.0, direction="greater") == pytest.approx(
        0.5
    )
    assert one_sided_normal_p_value(1.96, direction="less") == pytest.approx(
        0.975, abs=0.001
    )
    assert one_sided_normal_p_value(1.96, direction="greater") == pytest.approx(
        0.025, abs=0.001
    )
    assert one_sided_normal_p_value(-1.96, direction="less") == pytest.approx(
        0.025, abs=0.001
    )
    with pytest.raises(ValueError, match="direction must be"):
        one_sided_normal_p_value(0.0, direction="two-sided")
