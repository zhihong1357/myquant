"""Tests for minimum-detectable-effect formulas and the power simulation.

Analytic expectations are hand-computed from lambda = z(0.975) + z(0.8)
= 2.801585218112969 (two-sided) and lambda = z(0.95) + z(0.8) =
2.486474860524387 (one-sided).
"""

import pytest

from myquant.stats.power import (
    mde_coefficient,
    mde_cohens_d,
    mde_mean_ratio,
    mde_partial_r_squared,
    mde_standardized_mean,
    noncentrality,
    simulate_lead_lag_power,
)

LAMBDA_TWO_SIDED = 2.801585218112969
LAMBDA_ONE_SIDED = 2.486474860524387


def test_noncentrality_known_values():
    assert noncentrality(0.05, 0.80) == pytest.approx(LAMBDA_TWO_SIDED)
    assert noncentrality(0.05, 0.80, one_sided=True) == pytest.approx(LAMBDA_ONE_SIDED)
    assert noncentrality(0.05, 0.80, one_sided=True) < noncentrality(0.05, 0.80)
    assert noncentrality(0.05, 0.90) > noncentrality(0.05, 0.80)
    with pytest.raises(ValueError):
        noncentrality(0.0, 0.80)


def test_mde_partial_r_squared_known_value():
    result = mde_partial_r_squared(1414)
    expected = LAMBDA_TWO_SIDED**2 / (LAMBDA_TWO_SIDED**2 + 1414)
    assert result.minimum_detectable_effect == pytest.approx(expected)
    assert result.minimum_detectable_effect == pytest.approx(0.00552, abs=1e-5)
    # The lab's 0.005 partial-R^2 threshold sits just below the MDE at
    # the daily lead-lag sample size: the threshold is essentially the
    # detection limit of the design.
    assert result.minimum_detectable_effect > 0.005
    # Larger samples detect smaller effects.
    assert mde_partial_r_squared(5000).minimum_detectable_effect < expected


def test_mde_coefficient_scales_with_standard_error():
    result = mde_coefficient(0.0697, sample_size=1414)
    assert result.minimum_detectable_effect == pytest.approx(
        LAMBDA_TWO_SIDED * 0.0697
    )
    assert mde_coefficient(0.1394, sample_size=1414).minimum_detectable_effect == (
        pytest.approx(2.0 * result.minimum_detectable_effect)
    )


def test_mde_standardized_mean_one_sided_default():
    result = mde_standardized_mean(135)
    assert result.one_sided is True
    assert result.minimum_detectable_effect == pytest.approx(
        LAMBDA_ONE_SIDED / 135**0.5
    )
    assert result.minimum_detectable_effect == pytest.approx(0.2140, abs=1e-4)
    two_sided = mde_standardized_mean(135, one_sided=False)
    assert two_sided.minimum_detectable_effect == pytest.approx(
        LAMBDA_TWO_SIDED / 135**0.5
    )
    assert two_sided.minimum_detectable_effect > result.minimum_detectable_effect


def test_mde_cohens_d_known_value():
    result = mde_cohens_d(116, 2009)
    expected = LAMBDA_TWO_SIDED * (1.0 / 116 + 1.0 / 2009) ** 0.5
    assert result.minimum_detectable_effect == pytest.approx(expected)
    assert result.minimum_detectable_effect == pytest.approx(0.2675, abs=1e-4)
    # Balanced groups of the same total size detect smaller effects.
    assert mde_cohens_d(1062, 1063).minimum_detectable_effect < expected


def test_mde_mean_ratio_known_value():
    result = mde_mean_ratio(0.01960942, 0.00190182, sample_size=2125)
    expected = 1.0 + LAMBDA_TWO_SIDED * 0.00190182 / 0.01960942
    assert result.minimum_detectable_effect == pytest.approx(expected)
    assert result.minimum_detectable_effect == pytest.approx(1.2717, abs=1e-4)


def test_mde_validation():
    with pytest.raises(ValueError):
        mde_partial_r_squared(0)
    with pytest.raises(ValueError):
        mde_coefficient(0.0)
    with pytest.raises(ValueError):
        mde_cohens_d(0, 100)
    with pytest.raises(ValueError):
        mde_mean_ratio(0.0, 0.01)


def test_simulate_lead_lag_power_null_is_size():
    # At beta = 0 the rejection rate is the test's size, nominally 0.05.
    # 50 reps is noisy (MC se ~0.03), so the bound is loose.
    result = simulate_lead_lag_power(
        replications=50, observations=500, beta=0.0, seed=9
    )
    assert 0.0 <= result.empirical_power <= 0.2
    assert result.rejections == int(round(result.empirical_power * 50))


def test_simulate_lead_lag_power_large_effect_is_detected():
    # beta = 0.3 at n = 500 is far above the MDE (~0.125): power ~ 1.
    result = simulate_lead_lag_power(
        replications=50, observations=500, beta=0.3, seed=9
    )
    assert result.empirical_power >= 0.9


def test_simulate_lead_lag_power_is_deterministic():
    first = simulate_lead_lag_power(replications=20, observations=200, beta=0.1, seed=3)
    second = simulate_lead_lag_power(
        replications=20, observations=200, beta=0.1, seed=3
    )
    assert first == second
