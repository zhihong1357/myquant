"""Tests for calibration simulations.

These are fast smoke tests with small replication counts and loose
range assertions: the authoritative calibration numbers (larger
replication counts, reported with Monte Carlo standard errors) are
produced by the Stage 2B audit generator, not by these tests.
Determinism (same seed, same result) is asserted exactly.
"""

import pytest

from myquant.stats.calibration import (
    calibrate_bootstrap_coverage,
    calibrate_hac_size,
    calibrate_holm_fwer,
    monte_carlo_se,
)


def test_monte_carlo_se():
    assert monte_carlo_se(0.05, 500) == pytest.approx((0.05 * 0.95 / 500) ** 0.5)
    assert monte_carlo_se(0.0, 100) == 0.0
    with pytest.raises(ValueError):
        monte_carlo_se(1.5, 100)
    with pytest.raises(ValueError):
        monte_carlo_se(0.05, 0)


def test_calibrate_hac_size_runs_and_is_deterministic():
    first = calibrate_hac_size(replications=20, observations=200, seed=5)
    second = calibrate_hac_size(replications=20, observations=200, seed=5)
    assert first == second
    assert first.replications == 20
    assert first.observations == 200
    assert 0.0 <= first.rejection_rate <= 0.3
    assert first.rejections == int(round(first.rejection_rate * 20))


def test_calibrate_hac_size_ar1_variant_runs():
    result = calibrate_hac_size(
        replications=20, observations=200, autocorrelation=0.3, seed=5
    )
    assert 0.0 <= result.rejection_rate <= 0.3
    assert result.autocorrelation == 0.3


def test_calibrate_hac_size_validation():
    with pytest.raises(ValueError, match="at least 1"):
        calibrate_hac_size(replications=0)
    with pytest.raises(ValueError, match="alpha"):
        calibrate_hac_size(alpha=1.5)
    with pytest.raises(ValueError, match="autocorrelation"):
        calibrate_hac_size(autocorrelation=1.0)


def test_calibrate_bootstrap_coverage_runs_and_is_deterministic():
    first = calibrate_bootstrap_coverage(
        replications=20, observations=200, block_length=5, resamples=100, seed=5
    )
    second = calibrate_bootstrap_coverage(
        replications=20, observations=200, block_length=5, resamples=100, seed=5
    )
    assert first == second
    assert 0.7 <= first.coverage <= 1.0
    assert first.covered == int(round(first.coverage * 20))


def test_calibrate_bootstrap_coverage_ar1_variant_runs():
    result = calibrate_bootstrap_coverage(
        replications=20,
        observations=200,
        block_length=5,
        resamples=100,
        autocorrelation=0.3,
        seed=5,
    )
    assert 0.5 <= result.coverage <= 1.0


def test_calibrate_holm_fwer_runs_and_is_deterministic():
    first = calibrate_holm_fwer(replications=500, family_size=10, seed=5)
    second = calibrate_holm_fwer(replications=500, family_size=10, seed=5)
    assert first == second
    # Nominal level is 0.05; with 500 reps the MC standard error is
    # about 0.01, so 0.10 is a loose upper bound, not a tight claim.
    assert first.family_wise_error_rate <= 0.10
    assert first.families_with_rejection == int(
        round(first.family_wise_error_rate * 500)
    )


def test_calibrate_holm_fwer_correlated_variant_runs():
    result = calibrate_holm_fwer(
        replications=500, family_size=10, correlation=0.3, seed=5
    )
    assert result.family_wise_error_rate <= 0.10
    assert result.correlation == 0.3
