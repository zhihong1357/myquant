import numpy as np
import pytest

from myquant.stats.bootstrap import (
    block_bootstrap_mean_ci,
    block_bootstrap_mean_test,
)


def test_block_bootstrap_interval_is_reproducible_and_contains_estimate():
    rng = np.random.default_rng(12)
    values = rng.normal(0.2, 1.0, 500)
    first = block_bootstrap_mean_ci(
        values,
        block_length=8,
        resamples=500,
        confidence_level=0.95,
        seed=91,
    )
    second = block_bootstrap_mean_ci(
        values,
        block_length=8,
        resamples=500,
        confidence_level=0.95,
        seed=91,
    )

    assert first == second
    assert first.lower_bound <= first.point_estimate <= first.upper_bound
    assert first.observations == 500
    assert first.block_length == 8


def test_block_bootstrap_mean_test_rejects_clear_nonzero_mean():
    rng = np.random.default_rng(5)
    values = 0.25 + rng.normal(0.0, 0.15, 600)
    result = block_bootstrap_mean_test(
        values,
        null_mean=0.0,
        block_length=10,
        resamples=999,
        seed=44,
    )
    assert result.sample_mean > 0.2
    assert result.p_value < 0.01


def test_block_bootstrap_mean_test_does_not_find_signal_in_centered_noise():
    rng = np.random.default_rng(6)
    innovations = rng.normal(0.0, 1.0, 1_500)
    values = np.zeros(1_500)
    for index in range(1, len(values)):
        values[index] = 0.65 * values[index - 1] + innovations[index]
    values -= values.mean()

    result = block_bootstrap_mean_test(
        values,
        null_mean=0.0,
        block_length=20,
        resamples=999,
        seed=22,
    )
    assert result.p_value > 0.05


def test_bootstrap_rejects_invalid_inputs_and_settings():
    with pytest.raises(ValueError, match="at least two"):
        block_bootstrap_mean_ci([1.0], block_length=1)
    with pytest.raises(ValueError, match="finite"):
        block_bootstrap_mean_ci([1.0, np.nan, 2.0], block_length=1)
    with pytest.raises(ValueError, match="block_length"):
        block_bootstrap_mean_ci([1.0, 2.0, 3.0], block_length=4)
    with pytest.raises(ValueError, match="at least 100"):
        block_bootstrap_mean_ci([1.0, 2.0, 3.0], block_length=1, resamples=99)
    with pytest.raises(ValueError, match="null_mean"):
        block_bootstrap_mean_test(
            [1.0, 2.0, 3.0],
            null_mean=float("nan"),
            block_length=1,
        )


def test_bootstrap_rejects_block_length_at_or_near_sample_size():
    # With block_length == n every resample is a cyclic shift of the whole
    # sample, so the bootstrap distribution degenerates to a point: the
    # interval collapses and the mean test always returns the minimum
    # p-value. The same failure appears as block_length approaches n, so
    # block lengths above half the sample size are rejected outright.
    rng = np.random.default_rng(5)
    values = rng.normal(0.5, 1.0, 200)

    with pytest.raises(ValueError, match="half the sample size"):
        block_bootstrap_mean_ci(values, block_length=200, resamples=100, seed=1)
    with pytest.raises(ValueError, match="half the sample size"):
        block_bootstrap_mean_ci(values, block_length=199, resamples=100, seed=1)
    with pytest.raises(ValueError, match="half the sample size"):
        block_bootstrap_mean_ci(values, block_length=101, resamples=100, seed=1)
    with pytest.raises(ValueError, match="half the sample size"):
        block_bootstrap_mean_test(
            values,
            null_mean=0.0,
            block_length=200,
            resamples=100,
            seed=1,
        )


def test_bootstrap_accepts_block_length_at_half_sample_size():
    rng = np.random.default_rng(5)
    values = rng.normal(0.5, 1.0, 200)
    result = block_bootstrap_mean_ci(
        values,
        block_length=100,
        resamples=100,
        seed=1,
    )
    assert result.block_length == 100
    assert result.lower_bound < result.upper_bound


def _bootstrap_coverage(*, correlated: bool, repetitions: int = 100) -> float:
    covered = 0
    for repetition in range(repetitions):
        rng = np.random.default_rng(1000 + repetition)
        if correlated:
            size = 300
            innovations = rng.normal(0.0, 1.0, size)
            values = np.zeros(size)
            for index in range(1, size):
                values[index] = 0.6 * values[index - 1] + innovations[index]
            values = values / np.sqrt(1.0 / (1.0 - 0.6**2))
            block_length = 10
        else:
            values = rng.normal(0.0, 1.0, 200)
            block_length = 5
        interval = block_bootstrap_mean_ci(
            values,
            block_length=block_length,
            resamples=500,
            seed=repetition,
        )
        if interval.lower_bound <= 0.0 <= interval.upper_bound:
            covered += 1
    return covered / repetitions


def test_block_bootstrap_interval_coverage_is_calibrated():
    # A 95% interval should cover the true mean (0 here) in about 95% of
    # repeated samples. Fixed seeds keep the test deterministic; the
    # bounds allow Monte Carlo noise (std ~= 0.022 over 100 repetitions)
    # while catching gross miscalibration such as a degenerate resampling
    # distribution, which would cover at a rate near zero.
    assert 0.85 <= _bootstrap_coverage(correlated=False) <= 1.0
    assert 0.85 <= _bootstrap_coverage(correlated=True) <= 1.0
