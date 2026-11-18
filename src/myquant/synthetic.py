"""Deterministic synthetic panels for testing research methods."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from math import isfinite, sqrt

import numpy as np
import pandas as pd

from myquant.contracts import require_utc


class SyntheticScenario(StrEnum):
    NULL = "null"
    SOURCE_LEADS_TARGET = "source_leads_target"
    COMMON_FACTOR = "common_factor"
    REGIME_SHIFT = "regime_shift"
    HEAVY_TAIL_MISSING = "heavy_tail_missing"


def make_transmission_panel(
    *,
    observations: int = 3_000,
    lag_steps: int = 3,
    beta: float = 0.8,
    noise_scale: float = 1.0,
    scenario: SyntheticScenario = SyntheticScenario.SOURCE_LEADS_TARGET,
    seed: int = 42,
    start_time: datetime = datetime(2020, 1, 1, tzinfo=UTC),
    frequency: str = "D",
    missing_rate: float = 0.05,
    tail_degrees_of_freedom: float = 3.0,
) -> pd.DataFrame:
    """Create synthetic source/target data with known causal ground truth.

    The target at row t can depend on source row t-lag_steps, never on a future
    source observation. The common-factor scenario has no direct source-to-
    target causal arrow; both markets load on the same persistent latent factor.

    The heavy-tail-missing scenario keeps the source-leads-target mechanism
    but draws Student-t noise (standardized to unit variance) and then masks
    each observed series independently at random, so `source_value` and
    `target_return` contain NaN. Missingness is an observation process
    applied after the causal mechanism: masked rows still carry the effect
    in the latent series. Callers must handle the NaN explicitly (for
    example by dropping incomplete pairs); nothing here forward-fills.

    Columns `common_factor_truth` and `source_beta_truth` are simulation
    ground truth only. They are not tradable features and must not be passed to
    a model as predictors.
    """
    if observations < 100:
        raise ValueError("observations must be at least 100")
    if lag_steps < 1 or lag_steps >= observations // 4:
        raise ValueError("lag_steps must be positive and less than one quarter of observations")
    if not isfinite(beta):
        raise ValueError("beta must be finite")
    if not isfinite(noise_scale) or noise_scale <= 0:
        raise ValueError("noise_scale must be finite and positive")
    if seed < 0:
        raise ValueError("seed must be non-negative")
    if not isfinite(missing_rate) or not 0.0 <= missing_rate < 1.0:
        raise ValueError("missing_rate must be between zero (inclusive) and one")
    if not isfinite(tail_degrees_of_freedom) or tail_degrees_of_freedom <= 2.0:
        raise ValueError(
            "tail_degrees_of_freedom must exceed 2 so the noise has finite variance"
        )

    start = require_utc(start_time)
    rng = np.random.default_rng(seed)
    source_noise = rng.normal(0.0, 1.0, observations)
    target_noise = rng.normal(0.0, noise_scale, observations)
    common_factor = np.zeros(observations, dtype=float)
    source = source_noise.copy()
    target = target_noise.copy()
    beta_truth = np.zeros(observations, dtype=float)

    if scenario == SyntheticScenario.COMMON_FACTOR:
        factor_innovations = rng.normal(0.0, 1.0, observations)
        # Initialize from the stationary distribution N(0, 1/(1-phi^2)) so
        # the opening rows are already stationary; starting at zero would
        # leave the first dozens of rows under-dispersed relative to the
        # declared AR(1) process.
        common_factor[0] = factor_innovations[0] / np.sqrt(1.0 - 0.85**2)
        for index in range(1, observations):
            common_factor[index] = (
                0.85 * common_factor[index - 1] + factor_innovations[index]
            )
        source = 0.8 * common_factor + 0.6 * source_noise
        target = 0.8 * common_factor + target_noise
    elif scenario in (
        SyntheticScenario.SOURCE_LEADS_TARGET,
        SyntheticScenario.REGIME_SHIFT,
    ):
        if scenario == SyntheticScenario.SOURCE_LEADS_TARGET:
            beta_truth[:] = beta
        else:
            beta_truth[: observations // 2] = beta

        for index in range(lag_steps, observations):
            target[index] += beta_truth[index] * source[index - lag_steps]
    elif scenario == SyntheticScenario.HEAVY_TAIL_MISSING:
        # Student-t noise standardized to unit variance (Var(t_df) =
        # df/(df-2) for df > 2), so beta and noise_scale keep the same
        # meaning as in the Gaussian scenarios while the tails are heavy.
        tail_scale = sqrt(tail_degrees_of_freedom / (tail_degrees_of_freedom - 2.0))
        source = (
            rng.standard_t(tail_degrees_of_freedom, observations) / tail_scale
        )
        target = (
            rng.standard_t(tail_degrees_of_freedom, observations)
            / tail_scale
            * noise_scale
        )
        beta_truth[:] = beta
        for index in range(lag_steps, observations):
            target[index] += beta_truth[index] * source[index - lag_steps]
        # Missingness is applied after the causal mechanism, independently
        # per series (missing completely at random). Masked rows keep their
        # ground truth; only the observed values become NaN.
        source = source.astype(float)
        target = target.astype(float)
        source[rng.random(observations) < missing_rate] = np.nan
        target[rng.random(observations) < missing_rate] = np.nan
    elif scenario != SyntheticScenario.NULL:
        raise ValueError(f"unsupported synthetic scenario: {scenario}")

    timestamps = pd.date_range(
        start=start,
        periods=observations,
        freq=frequency,
    )
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "source_value": source,
            "target_return": target,
            "common_factor_truth": common_factor,
            "source_beta_truth": beta_truth,
            "scenario": scenario.value,
        }
    )
