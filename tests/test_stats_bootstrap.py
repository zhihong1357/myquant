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
