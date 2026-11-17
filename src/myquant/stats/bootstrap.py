"""Circular moving-block bootstrap for dependent time-series observations."""

from __future__ import annotations

from collections.abc import Iterable
from math import isfinite

import numpy as np
from pydantic import Field

from myquant.contracts import StrictContract


class BootstrapInterval(StrictContract):
    point_estimate: float
    lower_bound: float
    upper_bound: float
    confidence_level: float = Field(gt=0, lt=1)
    observations: int = Field(ge=2)
    block_length: int = Field(ge=1)
    resamples: int = Field(ge=100)
    seed: int = Field(ge=0)


class BootstrapMeanTest(StrictContract):
    sample_mean: float
    null_mean: float
    p_value: float = Field(ge=0, le=1)
    observations: int = Field(ge=2)
    block_length: int = Field(ge=1)
    resamples: int = Field(ge=100)
    seed: int = Field(ge=0)


def _finite_sample(values: Iterable[float]) -> np.ndarray:
    sample = np.asarray(tuple(values), dtype=float)
    if sample.ndim != 1:
        raise ValueError("bootstrap input must be a one-dimensional sequence")
    if sample.size < 2:
        raise ValueError("bootstrap requires at least two observations")
    if not np.isfinite(sample).all():
        raise ValueError("bootstrap input must contain only finite observations")
    return sample


def _validate_bootstrap_settings(
    *,
    sample_size: int,
    block_length: int,
    resamples: int,
    seed: int,
) -> None:
    if block_length < 1 or block_length > sample_size:
        raise ValueError("block_length must be between 1 and the sample size")
    if resamples < 100:
        raise ValueError("resamples must be at least 100")
    if seed < 0:
        raise ValueError("seed must be non-negative")


def _circular_block_means(
    sample: np.ndarray,
    *,
    block_length: int,
    resamples: int,
    seed: int,
) -> np.ndarray:
    """Draw circular blocks jointly in time order and return bootstrap means."""
    size = sample.size
    blocks_per_sample = (size + block_length - 1) // block_length
    offsets = np.arange(block_length)
    rng = np.random.default_rng(seed)
    means = np.empty(resamples, dtype=float)

    for replicate in range(resamples):
        starts = rng.integers(0, size, size=blocks_per_sample)
        indices = (starts[:, None] + offsets[None, :]) % size
        selected = sample[indices.ravel()[:size]]
        means[replicate] = float(np.mean(selected))
    return means


def block_bootstrap_mean_ci(
    values: Iterable[float],
    *,
    block_length: int,
    resamples: int = 2_000,
    confidence_level: float = 0.95,
    seed: int = 42,
) -> BootstrapInterval:
    """Estimate a percentile confidence interval for the sample mean.

    Circular moving blocks preserve local serial dependence within sampled
    blocks. The method is approximate and sensitive to block length; callers
    should report block-length sensitivity rather than treating one interval
    as definitive evidence.
    """
    sample = _finite_sample(values)
    _validate_bootstrap_settings(
        sample_size=sample.size,
        block_length=block_length,
        resamples=resamples,
        seed=seed,
    )
    if not isfinite(confidence_level) or not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be between zero and one")

    bootstrap_means = _circular_block_means(
        sample,
        block_length=block_length,
        resamples=resamples,
        seed=seed,
    )
    tail_probability = (1.0 - confidence_level) / 2.0
    lower, upper = np.quantile(
        bootstrap_means,
        [tail_probability, 1.0 - tail_probability],
    )
    return BootstrapInterval(
        point_estimate=float(np.mean(sample)),
        lower_bound=float(lower),
        upper_bound=float(upper),
        confidence_level=confidence_level,
        observations=int(sample.size),
        block_length=block_length,
        resamples=resamples,
        seed=seed,
    )


def block_bootstrap_mean_test(
    values: Iterable[float],
    *,
    null_mean: float = 0.0,
    block_length: int,
    resamples: int = 2_000,
    seed: int = 42,
) -> BootstrapMeanTest:
    """Run a two-sided block-bootstrap test of H0: mean(values) = null_mean.

    The observed series is centered and shifted to the null mean before block
    resampling. The finite-resample p-value uses the +1 correction. This is a
    basic dependent-data test, not a substitute for a study-specific null,
    studentization, covariate adjustment or multiple-testing correction.
    """
    sample = _finite_sample(values)
    _validate_bootstrap_settings(
        sample_size=sample.size,
        block_length=block_length,
        resamples=resamples,
        seed=seed,
    )
    if not isfinite(null_mean):
        raise ValueError("null_mean must be finite")

    observed_mean = float(np.mean(sample))
    null_sample = sample - observed_mean + null_mean
    null_bootstrap_means = _circular_block_means(
        null_sample,
        block_length=block_length,
        resamples=resamples,
        seed=seed,
    )
    observed_distance = abs(observed_mean - null_mean)
    bootstrap_distances = np.abs(null_bootstrap_means - null_mean)
    exceedances = int(np.count_nonzero(bootstrap_distances >= observed_distance))
    p_value = (exceedances + 1) / (resamples + 1)

    return BootstrapMeanTest(
        sample_mean=observed_mean,
        null_mean=float(null_mean),
        p_value=float(p_value),
        observations=int(sample.size),
        block_length=block_length,
        resamples=resamples,
        seed=seed,
    )
