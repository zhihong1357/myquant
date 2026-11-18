"""Backtest-overfitting diagnostics: Deflated Sharpe Ratio and PBO.

Two diagnostics from Bailey, Borwein, López de Prado and Zhu, for the
question "how much of this backtest's Sharpe ratio is selection bias?"

**Deflated Sharpe Ratio (DSR)** — Bailey & López de Prado (2014), "The
Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest
Overfitting and Non-Normality", *Journal of Portfolio Management* 40(5).
Given an observed Sharpe ratio SR̂ estimated from T observations, with
return skewness γ₃ and excess kurtosis κ, after selecting the best of N
independent trials:

    Var[SR̂] = (1 + ½·SR̂² − γ₃·SR̂ + (κ/4)·SR̂²) / (T − 1)

    E[max SR̂ | H₀] = √Var₀ · ((1−γ)·Φ⁻¹(1 − 1/N) + γ·Φ⁻¹(1 − 1/(N·e)))

with γ = 0.5772156649 (Euler–Mascheroni) and Var₀ = 1/(T−1) (the
variance of SR̂ under the null SR = 0). Then

    DSR = Φ( (SR̂ − E[max SR̂ | H₀]) / √Var[SR̂] ).

DSR is a probability in [0, 1]: the probability that the true Sharpe
ratio is positive, after deflating the observed Sharpe for the
selection over N trials and for non-normality. Bailey & López de Prado
suggest DSR ≥ 0.95 as the threshold for claiming skill. DSR is a
diagnostic, not a proof: it assumes the N trials are independent (or
that N is the *effective* number of independent trials), that returns
are stationary, and that the normal approximation to the distribution
of SR̂ holds. The Sharpe ratio and T must use consistent units (a
per-period Sharpe with T in periods, or an annualized Sharpe with T in
years). With N = 1 there is no selection, so E[max SR̂ | H₀] = 0.

**Probability of Backtest Overfitting (PBO)** — Bailey, Borwein, López
de Prado & Zhu (2014/2017), "The Probability of Backtest Overfitting",
*Journal of Computational Finance* 20(5). Combinatorially Symmetric
Cross-Validation (CSCV): split the sample into S contiguous groups (S
even); for each of the C(S, S/2) ways to choose half the groups as
in-sample (IS) and the rest as out-of-sample (OOS), select the strategy
with the best IS Sharpe ratio and record its OOS rank ω among the N
strategies (ω = rank/(N+1), so ω = 0.5 is the OOS median). Then

    PBO = P[ω < 0.5] = the fraction of splits where the IS-optimal
    strategy ranks below the OOS median.

PBO near 0 means the IS-optimal strategy reliably stays good OOS (a
persistent edge); PBO near 0.5 is what pure noise produces (the
IS-optimal strategy's OOS rank is uniform); PBO near 1 means the
IS-optimal strategy systematically underperforms OOS (the IS edge
reverses — the signature of overfitting). PBO measures the *procedure*
(select-the-best on this data), not any single strategy, and it assumes
the strategy set and the CSCV splits are fixed before looking at OOS
results. Strategy performance is the per-period Sharpe ratio
(mean / sample standard deviation, ddof=1) computed from group-level
sufficient statistics, so all C(S, S/2) splits are cheap even for
S = 16 (12,870 splits); when the split count exceeds
``max_combinations``, a uniform random subset of distinct splits is
used instead (fixed seed, so results are deterministic).

Neither diagnostic proves the absence of overfitting. A low PBO or a
high DSR says the observed edge survives *these* corrections; a
misspecified trial count, non-stationary returns, or a strategy set
that was itself chosen after seeing the data can still mislead.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterable
from math import comb as binomial_coefficient
from math import e as EULER_NUMBER
from math import isfinite, sqrt

import numpy as np
from numpy.typing import NDArray
from pydantic import Field

from myquant.contracts import StrictContract
from myquant.stats._normal import normal_cdf, normal_ppf
from myquant.stats._validation import finite_numeric_array

#: Euler–Mascheroni constant, used in the expected-maximum-Sharpe formula.
EULER_MASCHERONI = 0.5772156649015329

#: Default cap on CSCV combinations; above it a random subset is used.
DEFAULT_MAX_COMBINATIONS = 2_000


class DeflatedSharpeResult(StrictContract):
    """Deflated Sharpe Ratio and its components."""

    sharpe_ratio: float = Field(allow_inf_nan=False)
    observations: int = Field(ge=2)
    trials: int = Field(ge=1)
    skewness: float = Field(allow_inf_nan=False)
    excess_kurtosis: float = Field(allow_inf_nan=False)
    sharpe_variance: float = Field(ge=0, allow_inf_nan=False)
    expected_max_sharpe: float = Field(ge=0, allow_inf_nan=False)
    deflated_sharpe_ratio: float = Field(ge=0, le=1)


class PBOResult(StrictContract):
    """Probability of Backtest Overfitting from CSCV splits."""

    pbo: float = Field(ge=0, le=1)
    combinations: int = Field(ge=1)
    combinations_total: int = Field(ge=1)
    combinations_sampled: bool
    groups: int = Field(ge=2)
    strategies: int = Field(ge=2)
    observations: int = Field(ge=4)
    mean_relative_rank: float = Field(ge=0, le=1)
    median_relative_rank: float = Field(ge=0, le=1)
    seed: int = Field(ge=0)


def sharpe_ratio(returns: Iterable[float]) -> float:
    """Per-period Sharpe ratio (mean / sample standard deviation, ddof=1).

    No annualization is applied: callers annualize by scaling
    consistently with the observation count they pass to DSR.
    A zero-variance series has no defined Sharpe ratio and is rejected.
    """
    values = finite_numeric_array(returns, name="returns")
    if values.size < 2:
        raise ValueError("sharpe_ratio requires at least two observations")
    scale = float(np.std(values, ddof=1))
    if scale == 0.0:
        raise ValueError("sharpe_ratio is undefined for a zero-variance series")
    return float(np.mean(values) / scale)


def _sample_moments(values: NDArray[np.float64]) -> tuple[float, float]:
    """Fisher skewness and excess kurtosis from population central moments."""
    centered = values - float(np.mean(values))
    m2 = float(np.mean(centered**2))
    if m2 == 0.0:
        raise ValueError("moments are undefined for a zero-variance series")
    m3 = float(np.mean(centered**3))
    m4 = float(np.mean(centered**4))
    skewness = m3 / m2**1.5
    excess_kurtosis = m4 / (m2 * m2) - 3.0
    return skewness, excess_kurtosis


def sharpe_ratio_variance(
    sharpe: float,
    observations: int,
    *,
    skewness: float = 0.0,
    excess_kurtosis: float = 0.0,
) -> float:
    """Variance of the estimated Sharpe ratio (Bailey & López de Prado).

    Var[SR̂] = (1 + ½·SR̂² − γ₃·SR̂ + (κ/4)·SR̂²) / (T − 1), with γ₃ the
    return skewness and κ the excess kurtosis. Defaults of zero skew and
    zero excess kurtosis recover the Gaussian case.
    """
    estimate = float(sharpe)
    if not isfinite(estimate):
        raise ValueError("sharpe must be finite")
    if not isinstance(observations, int) or isinstance(observations, bool):
        raise TypeError("observations must be an integer")
    if observations < 2:
        raise ValueError("observations must be at least 2")
    skew = float(skewness)
    kurt = float(excess_kurtosis)
    if not isfinite(skew) or not isfinite(kurt):
        raise ValueError("skewness and excess_kurtosis must be finite")
    variance = (
        1.0
        + 0.5 * estimate * estimate
        - skew * estimate
        + 0.25 * kurt * estimate * estimate
    ) / (observations - 1)
    if variance < 0.0:
        # A large negative skew term can make the approximation negative
        # for extreme inputs; the variance of an estimator cannot be
        # negative, so floor at zero rather than returning nonsense.
        return 0.0
    return float(variance)


def expected_max_sharpe(observations: int, trials: int) -> float:
    """Expected maximum Sharpe under H₀ (SR = 0) across ``trials`` trials.

    E[max SR̂] = √(1/(T−1)) · ((1−γ)·Φ⁻¹(1 − 1/N) + γ·Φ⁻¹(1 − 1/(N·e))).
    With a single trial there is no selection, so the expectation is 0.
    """
    if not isinstance(observations, int) or isinstance(observations, bool):
        raise TypeError("observations must be an integer")
    if not isinstance(trials, int) or isinstance(trials, bool):
        raise TypeError("trials must be an integer")
    if observations < 2:
        raise ValueError("observations must be at least 2")
    if trials < 1:
        raise ValueError("trials must be at least 1")
    if trials == 1:
        return 0.0
    gamma = EULER_MASCHERONI
    quantile = (1.0 - gamma) * normal_ppf(
        1.0 - 1.0 / trials
    ) + gamma * normal_ppf(1.0 - 1.0 / (trials * EULER_NUMBER))
    return float(quantile / sqrt(observations - 1))


def deflated_sharpe_ratio(
    sharpe: float,
    observations: int,
    trials: int,
    *,
    skewness: float = 0.0,
    excess_kurtosis: float = 0.0,
) -> DeflatedSharpeResult:
    """Deflated Sharpe Ratio for an observed Sharpe after N-trial selection.

    DSR = Φ((SR̂ − E[max SR̂ | H₀]) / √Var[SR̂]). See the module docstring
    for the formula, its sources and its assumptions. A DSR above 0.95 is
    the threshold Bailey & López de Prado suggest for claiming skill; a
    DSR below 0.5 means the observed Sharpe is below what selection alone
    would produce under the null.
    """
    variance = sharpe_ratio_variance(
        sharpe,
        observations,
        skewness=skewness,
        excess_kurtosis=excess_kurtosis,
    )
    expected_max = expected_max_sharpe(observations, trials)
    estimate = float(sharpe)
    if variance == 0.0:
        # Degenerate variance (only reachable with extreme skew/kurtosis
        # inputs): the DSR collapses to a step at the expected maximum.
        dsr = 1.0 if estimate > expected_max else 0.0
    else:
        dsr = normal_cdf((estimate - expected_max) / sqrt(variance))
    return DeflatedSharpeResult(
        sharpe_ratio=estimate,
        observations=int(observations),
        trials=int(trials),
        skewness=float(skewness),
        excess_kurtosis=float(excess_kurtosis),
        sharpe_variance=variance,
        expected_max_sharpe=expected_max,
        deflated_sharpe_ratio=float(dsr),
    )


def deflated_sharpe_ratio_from_returns(
    returns: Iterable[float],
    trials: int,
) -> DeflatedSharpeResult:
    """DSR from a return series: Sharpe, skew and kurtosis are estimated.

    The Sharpe ratio is the per-period ratio (mean / sample sd, ddof=1)
    and T is the number of observations, so the units are consistent.
    """
    values = finite_numeric_array(returns, name="returns")
    if values.size < 2:
        raise ValueError("at least two return observations are required")
    estimate = sharpe_ratio(values)
    skewness, excess_kurtosis = _sample_moments(values)
    return deflated_sharpe_ratio(
        estimate,
        int(values.size),
        trials,
        skewness=skewness,
        excess_kurtosis=excess_kurtosis,
    )


def _group_sharpes(
    group_sums: NDArray[np.float64],
    group_sumsq: NDArray[np.float64],
    group_counts: NDArray[np.float64],
    selected: NDArray[np.bool_],
) -> NDArray[np.float64]:
    """Per-strategy Sharpe ratios over the selected groups.

    Computed from group sufficient statistics (sum, sum of squares,
    count), so each CSCV split costs one small vector reduction rather
    than a pass over the raw rows. A zero-variance half is +inf for a
    positive mean, -inf for a negative mean, 0.0 for a zero mean.
    """
    counts = group_counts[selected].sum()
    totals = group_sums[selected].sum(axis=0)
    totals_sq = group_sumsq[selected].sum(axis=0)
    means = totals / counts
    variances = (totals_sq - counts * means * means) / (counts - 1.0)
    sharpes = np.empty_like(means)
    positive = variances > 0.0
    sharpes[positive] = means[positive] / np.sqrt(variances[positive])
    degenerate = ~positive
    sharpes[degenerate] = np.where(
        means[degenerate] > 0.0,
        np.inf,
        np.where(means[degenerate] < 0.0, -np.inf, 0.0),
    )
    return sharpes


#: Hard cap on enumerating every CSCV split; above it the caller must
#: sample (``max_combinations``) instead of asking for all splits.
_MAX_ENUMERATED_SPLITS = 100_000


def _cscv_split_masks(
    n_groups: int,
    max_combinations: int | None,
    seed: int,
) -> tuple[tuple[int, ...], ...]:
    """IS group-index tuples for CSCV: all C(S, S/2), or a sampled subset."""
    half = n_groups // 2
    total = binomial_coefficient(n_groups, half)
    if max_combinations is None:
        if total > _MAX_ENUMERATED_SPLITS:
            raise ValueError(
                f"CSCV has {total} splits for {n_groups} groups; set "
                "max_combinations to sample a subset instead of enumerating all"
            )
        return tuple(itertools.combinations(range(n_groups), half))
    if max_combinations < 1:
        raise ValueError("max_combinations must be at least 1")
    if total <= max_combinations:
        return tuple(itertools.combinations(range(n_groups), half))
    # Sample distinct splits by drawing random halves; with total >> max
    # collisions are rare, and the loop is bounded.
    rng = np.random.default_rng(seed)
    chosen: set[tuple[int, ...]] = set()
    attempts = 0
    while len(chosen) < max_combinations:
        attempts += 1
        if attempts > 100 * max_combinations:
            raise RuntimeError("could not sample distinct CSCV splits")
        draw = tuple(sorted(rng.choice(n_groups, size=half, replace=False).tolist()))
        chosen.add(draw)
    return tuple(sorted(chosen))


def probability_of_backtest_overfitting(
    returns: Iterable[Iterable[float]],
    *,
    n_groups: int = 16,
    max_combinations: int | None = DEFAULT_MAX_COMBINATIONS,
    seed: int = 42,
) -> PBOResult:
    """Probability of Backtest Overfitting via CSCV (Bailey et al.).

    ``returns`` is a (T, N) array: rows are time periods, columns are
    strategies. Rows are split into ``n_groups`` contiguous groups; each
    CSCV split takes half the groups in-sample and the rest out-of-sample,
    selects the best IS Sharpe ratio, and records that strategy's OOS
    rank ω = rank/(N+1). PBO is the fraction of splits with ω < 0.5.
    """
    matrix = np.asarray(returns, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("returns must be a two-dimensional (T, N) array")
    if not np.isfinite(matrix).all():
        raise ValueError("returns must contain only finite values")
    observations, strategies = matrix.shape
    if strategies < 2:
        raise ValueError("PBO requires at least two strategies")
    if observations < 4:
        raise ValueError("PBO requires at least four observations")
    if (
        not isinstance(n_groups, int)
        or isinstance(n_groups, bool)
        or n_groups < 2
        or n_groups % 2 != 0
    ):
        raise ValueError("n_groups must be an even integer of at least 2")
    if n_groups > observations:
        raise ValueError("n_groups must not exceed the number of observations")
    if seed < 0:
        raise ValueError("seed must be non-negative")
    if max_combinations is not None and (
        not isinstance(max_combinations, int)
        or isinstance(max_combinations, bool)
        or max_combinations < 1
    ):
        raise ValueError("max_combinations must be a positive integer or None")

    # Contiguous groups (np.array_split sizes differ by at most one row).
    boundaries = np.array_split(np.arange(observations), n_groups)
    group_sums = np.empty((n_groups, strategies), dtype=float)
    group_sumsq = np.empty((n_groups, strategies), dtype=float)
    group_counts = np.empty(n_groups, dtype=float)
    for group, rows in enumerate(boundaries):
        block = matrix[rows]
        group_sums[group] = block.sum(axis=0)
        group_sumsq[group] = (block * block).sum(axis=0)
        group_counts[group] = float(len(rows))
    if group_counts.min() < 1:
        raise ValueError("each CSCV group needs at least one observation")
    half_rows = float(np.sort(group_counts)[: n_groups // 2].sum())
    if half_rows < 2:
        raise ValueError("each CSCV half needs at least two observations")

    splits = _cscv_split_masks(n_groups, max_combinations, seed)
    total_splits = binomial_coefficient(n_groups, n_groups // 2)
    relative_ranks = np.empty(len(splits), dtype=float)
    for position, in_sample in enumerate(splits):
        mask = np.zeros(n_groups, dtype=bool)
        mask[list(in_sample)] = True
        is_sharpes = _group_sharpes(group_sums, group_sumsq, group_counts, mask)
        best = int(np.argmax(is_sharpes))
        oos_sharpes = _group_sharpes(group_sums, group_sumsq, group_counts, ~mask)
        # Ascending rank (1 = worst OOS Sharpe); ties break by strategy
        # index through the stable sort, so the rank is deterministic.
        order = np.argsort(oos_sharpes, kind="stable")
        rank = int(np.where(order == best)[0][0]) + 1
        relative_ranks[position] = rank / (strategies + 1)

    return PBOResult(
        pbo=float(np.mean(relative_ranks < 0.5)),
        combinations=len(splits),
        combinations_total=total_splits,
        combinations_sampled=len(splits) < total_splits,
        groups=n_groups,
        strategies=strategies,
        observations=observations,
        mean_relative_rank=float(np.mean(relative_ranks)),
        median_relative_rank=float(np.median(relative_ranks)),
        seed=seed,
    )
