"""Tests for drift and alpha-decay monitoring (offline, deterministic)."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from myquant.portfolio.drift import (
    AlertConfig,
    check_alerts,
    estimate_decay,
    expanding_mean,
    fit_trend,
    population_stability_index,
    rolling_hit_rate,
    rolling_mean,
    rolling_mse,
    rolling_skill,
    window_shift,
)

T0 = datetime(2026, 1, 1, 16, 0, tzinfo=UTC)
DAY = timedelta(days=1)


def test_rolling_mean_hand_computed_and_incomplete_windows():
    assert rolling_mean([1.0, 2.0, 3.0, 4.0], window=2) == (
        None,
        1.5,
        2.5,
        3.5,
    )
    assert rolling_mean([1.0, 2.0], window=5) == (None, None)
    assert rolling_mean([], window=3) == ()
    with pytest.raises(ValueError, match="positive integer"):
        rolling_mean([1.0], window=0)


def test_expanding_mean_hand_computed():
    assert expanding_mean([1.0, 2.0, 3.0, 4.0]) == (1.0, 1.5, 2.0, 2.5)
    assert expanding_mean([]) == ()


def test_rolling_mse_hand_computed():
    # errors [1, -2, 3]: squared [1, 4, 9]; window 2 -> [None, 2.5, 6.5].
    assert rolling_mse([1.0, -2.0, 3.0], window=2) == (
        None,
        pytest.approx(2.5),
        pytest.approx(6.5),
    )


def test_rolling_skill_hand_computed_and_zero_baseline():
    errors = [0.1, 0.2, 0.1, 0.2]
    baseline = [0.2, 0.2, 0.2, 0.2]
    # Window 2: stream MSE [0.025, 0.025, 0.025]; baseline MSE 0.04 throughout.
    skill = rolling_skill(errors, baseline, window=2)
    assert skill[0] is None
    assert skill[1] == pytest.approx(1 - 0.025 / 0.04)
    # Zero baseline MSE in a window -> skill undefined there.
    skill_zero = rolling_skill([0.1, 0.2], [0.0, 0.0], window=2)
    assert skill_zero == (None, None)
    with pytest.raises(ValueError, match="same length"):
        rolling_skill([0.1], [0.1, 0.2], window=1)


def test_rolling_hit_rate_hand_computed():
    predicted = [0.1, -0.1, 0.1, 0.0]
    outcome = [0.2, 0.1, -0.1, 0.0]
    # Hits: [True, False, False, True]; window 2 -> [None, 0.5, 0.0, 0.5].
    assert rolling_hit_rate(predicted, outcome, window=2) == (
        None,
        pytest.approx(0.5),
        pytest.approx(0.0),
        pytest.approx(0.5),
    )


def test_psi_identical_samples_is_zero():
    rng = np.random.default_rng(7)
    sample = list(rng.normal(0.0, 1.0, 500))
    result = population_stability_index(sample, sample, bins=10)
    assert result.psi == pytest.approx(0.0)
    assert result.n_bins == 10
    assert result.reference_n == 500
    assert result.current_n == 500


def test_psi_shifted_distribution_is_large():
    rng = np.random.default_rng(11)
    reference = list(rng.normal(0.0, 1.0, 1000))
    current = list(rng.normal(2.0, 1.0, 1000))
    result = population_stability_index(reference, current, bins=10)
    assert result.psi > 1.0
    # A mild shift stays small.
    mild = list(rng.normal(0.1, 1.0, 1000))
    assert population_stability_index(reference, mild, bins=10).psi < 0.1


def test_psi_empty_bins_stay_finite():
    rng = np.random.default_rng(13)
    reference = list(rng.normal(0.0, 1.0, 500))
    # Every current value lands in the top bin: most bins are empty.
    current = [5.0] * 100
    result = population_stability_index(reference, current, bins=10)
    assert np.isfinite(result.psi)
    assert result.psi > 0.0


def test_psi_degenerate_reference_raises():
    with pytest.raises(ValueError, match="no variation"):
        population_stability_index([1.0, 1.0, 1.0], [1.0, 2.0])


def test_window_shift_mean_difference_and_vol_ratio():
    rng = np.random.default_rng(17)
    reference = list(rng.normal(0.0, 1.0, 200))
    current = list(rng.normal(1.0, 2.0, 200))
    result = window_shift(
        reference, current, max_lag=5, block_length=5, resamples=200, seed=3
    )
    assert result.mean_difference == pytest.approx(
        float(np.mean(current) - np.mean(reference))
    )
    assert result.mean_difference_se is not None
    assert result.mean_difference_p_value is not None
    assert result.mean_difference_p_value < 0.001
    assert result.volatility_ratio == pytest.approx(
        float(np.std(current, ddof=1) / np.std(reference, ddof=1)), rel=1e-9
    )
    assert result.volatility_ratio_ci_low is not None
    assert result.volatility_ratio_ci_high is not None
    assert result.volatility_ratio_ci_low < result.volatility_ratio
    assert result.volatility_ratio < result.volatility_ratio_ci_high
    assert 1.5 < result.volatility_ratio < 2.5


def test_window_shift_is_deterministic():
    rng = np.random.default_rng(19)
    reference = list(rng.normal(0.0, 1.0, 100))
    current = list(rng.normal(0.2, 1.0, 100))
    first = window_shift(reference, current, max_lag=3, resamples=100, seed=5)
    second = window_shift(reference, current, max_lag=3, resamples=100, seed=5)
    assert first == second


def test_fit_trend_recovers_a_line():
    rng = np.random.default_rng(41)
    values = [1.0 + 2.0 * t + float(rng.normal(0.0, 0.1)) for t in range(50)]
    result = fit_trend(values, max_lag=0)
    assert result.slope == pytest.approx(2.0, abs=0.05)
    assert result.intercept == pytest.approx(1.0, abs=0.1)
    assert result.n == 50
    assert result.slope_p_value is not None
    assert result.slope_p_value < 0.001


def test_fit_trend_perfect_line_returns_exact_coefficients():
    # A degenerate case: zero residuals leave only floating-point
    # residue in the HAC covariance, so no assertion is made about
    # the standard error or p-value — only that the fit itself is
    # exact and does not raise.
    values = [1.0 + 2.0 * t for t in range(20)]
    result = fit_trend(values, max_lag=0)
    assert result.slope == pytest.approx(2.0)
    assert result.intercept == pytest.approx(1.0)


def test_fit_trend_constant_series_has_zero_slope():
    # Degenerate case again: the slope is zero up to floating-point
    # residue; the HAC p-value on a constant series is numerical
    # noise and is not asserted.
    result = fit_trend([1.0] * 10, max_lag=0)
    assert abs(result.slope) < 1e-10


def test_estimate_decay_recovers_known_half_life():
    rng = np.random.default_rng(23)
    n = 200
    truth = 50.0
    skill = [
        0.8 * 0.5 ** (t / truth) + float(rng.normal(0.0, 0.02)) for t in range(n)
    ]
    estimate = estimate_decay(
        skill, max_lag=5, resamples=100, seed=7, bootstrap_block_length=5
    )
    assert estimate.detected is True
    assert estimate.half_life is not None
    assert 25.0 < estimate.half_life < 100.0
    assert estimate.half_life_ci_low is not None
    assert estimate.half_life_ci_high is not None
    # The grid is discrete, so the point estimate may coincide with
    # an interval endpoint; containment is inclusive.
    assert estimate.half_life_ci_low <= estimate.half_life <= estimate.half_life_ci_high
    assert estimate.fit_r_squared is not None
    assert estimate.fit_r_squared > 0.5


def test_estimate_decay_flat_series_not_detected():
    rng = np.random.default_rng(29)
    skill = [float(rng.normal(0.0, 0.05)) for _ in range(100)]
    estimate = estimate_decay(skill, max_lag=5, resamples=50, seed=7)
    assert estimate.detected is False
    assert estimate.half_life is None
    assert "not significant" in estimate.reason or "no negative trend" in estimate.reason


def test_estimate_decay_increasing_series_not_detected():
    skill = [0.01 * t for t in range(50)]
    estimate = estimate_decay(skill, max_lag=0, resamples=0)
    assert estimate.detected is False
    assert estimate.half_life is None


def test_estimate_decay_noisy_negative_trend_not_detected():
    # A negative trend buried in heavy noise: the exponential fit is poor.
    rng = np.random.default_rng(31)
    skill = [1.0 - 0.002 * t + float(rng.normal(0.0, 0.5)) for t in range(100)]
    estimate = estimate_decay(skill, max_lag=5, resamples=50, seed=7)
    assert estimate.detected is False
    assert estimate.half_life is None


def test_estimate_decay_is_deterministic():
    rng = np.random.default_rng(37)
    skill = [0.8 * 0.5 ** (t / 40.0) + float(rng.normal(0.0, 0.02)) for t in range(100)]
    first = estimate_decay(skill, max_lag=5, resamples=50, seed=7)
    second = estimate_decay(skill, max_lag=5, resamples=50, seed=7)
    assert first == second


def test_check_alerts_skill_runs_and_psi_flags():
    times = [T0 + i * DAY for i in range(8)]
    skill_windows = [
        (times[0], 0.1),
        (times[1], -0.1),
        (times[2], -0.2),
        (times[3], -0.1),  # third consecutive below zero -> flag here
        (times[4], -0.3),  # fourth in the same run -> no second flag
        (times[5], 0.2),  # run breaks
        (times[6], -0.1),
        (times[7], -0.2),  # only two in the new run -> no flag
    ]
    psi_windows = [
        (times[0], 0.05),
        (times[1], 0.30),  # above 0.25 -> flag
        (times[2], 0.10),
    ]
    flags = check_alerts(skill_windows, psi_windows)
    assert len(flags) == 2
    assert flags[0].flag_type == "psi_high"
    assert flags[0].triggered_at == times[1]
    assert flags[0].value == pytest.approx(0.30)
    assert flags[1].flag_type == "skill_below_zero"
    assert flags[1].triggered_at == times[3]
    assert flags[1].value == pytest.approx(-0.1)


def test_check_alerts_none_values_break_runs_without_flagging():
    times = [T0 + i * DAY for i in range(4)]
    skill_windows = [
        (times[0], -0.1),
        (times[1], None),  # incomplete window breaks the run
        (times[2], -0.2),
        (times[3], -0.1),
    ]
    assert check_alerts(skill_windows, []) == ()


def test_check_alerts_custom_config():
    times = [T0 + i * DAY for i in range(3)]
    skill_windows = [(times[i], -0.1) for i in range(3)]
    config = AlertConfig(skill_below_zero_windows=2, psi_threshold=0.5)
    flags = check_alerts(skill_windows, [(times[0], 0.4)], config=config)
    assert len(flags) == 1
    assert flags[0].flag_type == "skill_below_zero"
    assert flags[0].triggered_at == times[1]
