"""Drift and alpha-decay monitoring for scored prediction streams (Stage 5b).

Given a stream of scored predictions (see :mod:`myquant.portfolio.shadow`),
this module answers two forward-looking questions: is the stream's
performance changing over time, and is the outcome distribution
drifting? Everything here is a monitor, not a verdict: thresholds
produce *flags* (prompts to look), never conclusions, and every
estimate that can carry uncertainty does.

Components:

- **Rolling performance.** Expanding and fixed rolling windows over
  per-prediction errors: rolling MSE, rolling skill (against a
  baseline's errors on the same windows), rolling hit rate. A window
  that is not yet full returns ``None`` — an incomplete window is
  missing data, not a shorter window.
- **Distribution drift (PSI).** The population stability index
  between a reference window and a recent window, on equal-frequency
  bins from the reference sample's quantiles. PSI = sum over bins of
  (actual - expected) * ln(actual / expected), with shares floored
  at a small epsilon (default 1e-4) so empty bins contribute a finite
  amount instead of exploding. Out-of-range values are assigned to
  the outermost bins. The 0.1 / 0.25 cutoffs in the documentation
  are conventional detection thresholds, not significance levels.
- **Window shift.** Recent-vs-reference mean difference with a HAC
  standard error (an indicator regression through the kernel's
  Newey-West estimator) and a volatility ratio with a circular-block
  bootstrap interval (same resampling scheme as the kernel's block
  bootstrap, applied to the log volatility ratio).
- **Decay estimation.** A linear trend on the rolling skill series
  (OLS + HAC standard error). Only if the slope is significantly
  negative is an exponential decay fitted (skill_t = a * exp(-lambda
  * t) + c, by grid search over the half-life), and only if that fit
  is good enough is a half-life reported — with a residual
  block-bootstrap interval, an R-squared, and a stability flag. A
  non-significant trend or a poor exponential fit reports "not
  detected" instead of a number. The half-life is a fragile
  estimate: it is never reported as a bare point estimate.
- **Alerts.** Configurable rules (consecutive rolling windows with
  skill below a threshold; PSI above a threshold) that emit flags
  carrying the trigger time, value and threshold.

No SciPy: inference reuses the lab's own statistical kernel
(Newey-West HAC, OLS) and NumPy. There is no KS test in this
module: the PSI and window-shift checks cover distribution drift,
and a KS statistic would add a second, overlapping detector.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite, log

import numpy as np
from numpy.typing import NDArray
from pydantic import Field

from myquant.contracts import StrictContract
from myquant.stats.hac import newey_west_hac

#: Default epsilon for PSI shares: empty bins contribute a finite
#: amount instead of an infinite one.
PSI_EPSILON = 1e-4

#: Conventional PSI detection thresholds (not significance levels).
PSI_WARNING = 0.1
PSI_ALARM = 0.25


def _finite_array(values: Iterable[float], *, name: str) -> NDArray[np.float64]:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1:
        raise ValueError(f"{name} must be a one-dimensional sequence")
    if array.size and not np.isfinite(array).all():
        raise ValueError(f"{name} must contain only finite values")
    return array


def _validate_window(window: int, *, name: str = "window") -> None:
    if not isinstance(window, int) or isinstance(window, bool) or window < 1:
        raise ValueError(f"{name} must be a positive integer")


# ---------------------------------------------------------------------------
# Rolling performance
# ---------------------------------------------------------------------------


def rolling_mean(
    values: Iterable[float], *, window: int
) -> tuple[float | None, ...]:
    """Rolling mean over a fixed window; ``None`` while the window is incomplete."""
    _validate_window(window)
    array = _finite_array(values, name="values")
    if array.size == 0:
        return ()
    if array.size < window:
        return tuple(None for _ in range(array.size))
    cumsum = np.concatenate(([0.0], np.cumsum(array)))
    means = (cumsum[window:] - cumsum[:-window]) / window
    return tuple(None for _ in range(window - 1)) + tuple(float(v) for v in means)


def expanding_mean(values: Iterable[float]) -> tuple[float, ...]:
    """Expanding (cumulative) mean from the first observation."""
    array = _finite_array(values, name="values")
    if array.size == 0:
        return ()
    return tuple(
        float(v) for v in np.cumsum(array) / np.arange(1, array.size + 1)
    )


def rolling_mse(
    errors: Iterable[float], *, window: int
) -> tuple[float | None, ...]:
    """Rolling mean squared error over a fixed window."""
    _validate_window(window)
    array = _finite_array(errors, name="errors")
    return rolling_mean(array**2, window=window)


def rolling_skill(
    errors: Iterable[float],
    baseline_errors: Iterable[float],
    *,
    window: int,
) -> tuple[float | None, ...]:
    """Rolling skill = 1 - rolling MSE / rolling baseline MSE.

    ``None`` while the window is incomplete or where the baseline
    MSE in the window is zero (skill undefined there).
    """
    _validate_window(window)
    stream = _finite_array(errors, name="errors")
    baseline = _finite_array(baseline_errors, name="baseline_errors")
    if stream.size != baseline.size:
        raise ValueError("errors and baseline_errors must have the same length")
    stream_mse = rolling_mse(stream, window=window)
    baseline_mse = rolling_mse(baseline, window=window)
    result: list[float | None] = []
    for stream_value, baseline_value in zip(stream_mse, baseline_mse, strict=True):
        if stream_value is None or baseline_value is None or baseline_value == 0.0:
            result.append(None)
        else:
            result.append(float(1.0 - stream_value / baseline_value))
    return tuple(result)


def rolling_hit_rate(
    predicted: Iterable[float],
    outcome: Iterable[float],
    *,
    window: int,
) -> tuple[float | None, ...]:
    """Rolling direction hit rate (sign agreement, sign(0) = 0)."""
    _validate_window(window)
    pred = _finite_array(predicted, name="predicted")
    out = _finite_array(outcome, name="outcome")
    if pred.size != out.size:
        raise ValueError("predicted and outcome must have the same length")
    hits = (np.sign(pred) == np.sign(out)).astype(float)
    return rolling_mean(hits, window=window)


# ---------------------------------------------------------------------------
# Population stability index
# ---------------------------------------------------------------------------


class PSIBin(StrictContract):
    """One PSI bin: edges, shares, and its contribution to the index."""

    lower: float = Field(allow_inf_nan=False)
    upper: float = Field(allow_inf_nan=False)
    expected_share: float = Field(ge=0, le=1, allow_inf_nan=False)
    actual_share: float = Field(ge=0, le=1, allow_inf_nan=False)
    contribution: float = Field(allow_inf_nan=False)


class PSIResult(StrictContract):
    """Population stability index between a reference and a recent sample."""

    psi: float = Field(ge=0, allow_inf_nan=False)
    bins: tuple[PSIBin, ...]
    n_bins: int = Field(ge=1)
    reference_n: int = Field(ge=1)
    current_n: int = Field(ge=1)
    epsilon: float = Field(gt=0, allow_inf_nan=False)


def population_stability_index(
    reference: Iterable[float],
    current: Iterable[float],
    *,
    bins: int = 10,
    epsilon: float = PSI_EPSILON,
) -> PSIResult:
    """PSI between a reference window and a recent window.

    Bins are equal-frequency on the reference sample: interior edges
    are the reference quantiles at k/bins. Values outside the
    reference range fall into the outermost bins. Shares are floored
    at ``epsilon`` before the log, so an empty bin contributes a
    finite amount. Duplicate quantile edges (tied reference values)
    are merged, so the actual bin count may be below ``bins``.
    """
    if not isinstance(bins, int) or isinstance(bins, bool) or bins < 2:
        raise ValueError("bins must be an integer of at least 2")
    if not isfinite(epsilon) or epsilon <= 0.0 or epsilon >= 1.0:
        raise ValueError("epsilon must be strictly between 0 and 1")
    ref = _finite_array(reference, name="reference")
    cur = _finite_array(current, name="current")
    if ref.size == 0 or cur.size == 0:
        raise ValueError("reference and current must both be non-empty")
    if float(np.min(ref)) == float(np.max(ref)):
        raise ValueError("reference sample has no variation; PSI is undefined")
    interior = np.quantile(ref, np.linspace(0.0, 1.0, bins + 1)[1:-1])
    edges = np.unique(interior)
    n_bins = int(edges.size + 1)

    def _shares(sample: NDArray[np.float64]) -> NDArray[np.float64]:
        indices = np.searchsorted(edges, sample, side="right")
        counts = np.bincount(indices, minlength=n_bins).astype(float)
        return counts / sample.size

    expected = _shares(ref)
    actual = _shares(cur)
    floored_expected = np.maximum(expected, epsilon)
    floored_actual = np.maximum(actual, epsilon)
    contributions = (floored_actual - floored_expected) * np.log(
        floored_actual / floored_expected
    )
    lower_edges = np.concatenate(([float(np.min(ref))], edges))
    upper_edges = np.concatenate((edges, [float(np.max(ref))]))
    bin_records = tuple(
        PSIBin(
            lower=float(lower_edges[i]),
            upper=float(upper_edges[i]),
            expected_share=float(expected[i]),
            actual_share=float(actual[i]),
            contribution=float(contributions[i]),
        )
        for i in range(n_bins)
    )
    return PSIResult(
        psi=float(np.sum(contributions)),
        bins=bin_records,
        n_bins=n_bins,
        reference_n=int(ref.size),
        current_n=int(cur.size),
        epsilon=float(epsilon),
    )


# ---------------------------------------------------------------------------
# Window shift: mean difference (HAC) and volatility ratio (block bootstrap)
# ---------------------------------------------------------------------------


class WindowShiftResult(StrictContract):
    """Recent-vs-reference shift: mean difference and volatility ratio."""

    reference_n: int = Field(ge=2)
    current_n: int = Field(ge=2)
    reference_mean: float = Field(allow_inf_nan=False)
    current_mean: float = Field(allow_inf_nan=False)
    mean_difference: float = Field(allow_inf_nan=False)
    mean_difference_se: float | None = Field(default=None, allow_inf_nan=False)
    mean_difference_p_value: float | None = Field(
        default=None, ge=0, le=1, allow_inf_nan=False
    )
    reference_std: float = Field(ge=0, allow_inf_nan=False)
    current_std: float = Field(ge=0, allow_inf_nan=False)
    volatility_ratio: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    volatility_ratio_ci_low: float | None = Field(
        default=None, ge=0, allow_inf_nan=False
    )
    volatility_ratio_ci_high: float | None = Field(
        default=None, ge=0, allow_inf_nan=False
    )
    max_lag: int = Field(ge=0)
    bootstrap_block_length: int = Field(ge=1)
    bootstrap_resamples: int = Field(ge=0)
    bootstrap_seed: int = Field(ge=0)


def _circular_block_resample(
    sample: NDArray[np.float64],
    *,
    block_length: int,
    rng: np.random.Generator,
) -> NDArray[np.float64]:
    """One circular-block resample, same scheme as the kernel bootstrap."""
    size = sample.size
    blocks = (size + block_length - 1) // block_length
    starts = rng.integers(0, size, size=blocks)
    indices = (starts[:, None] + np.arange(block_length)[None, :]) % size
    resampled: NDArray[np.float64] = np.asarray(
        sample[indices.ravel()[:size]], dtype=np.float64
    )
    return resampled


def window_shift(
    reference: Iterable[float],
    current: Iterable[float],
    *,
    max_lag: int,
    block_length: int = 5,
    resamples: int = 2_000,
    seed: int = 42,
) -> WindowShiftResult:
    """Compare a recent window against a reference window.

    The mean difference comes from an indicator regression (0 for
    reference, 1 for current) with a Newey-West HAC standard error
    from the kernel. The volatility ratio is the ratio of sample
    standard deviations, with a percentile interval from a
    circular-block bootstrap of the log ratio (fixed seed, so
    deterministic). The interval is ``None`` when either sample is
    too short for the block bootstrap or too few replicates are
    usable.
    """
    ref = _finite_array(reference, name="reference")
    cur = _finite_array(current, name="current")
    if ref.size < 2 or cur.size < 2:
        raise ValueError("reference and current each need at least two observations")
    if not isinstance(max_lag, int) or isinstance(max_lag, bool) or max_lag < 0:
        raise ValueError("max_lag must be a non-negative integer")
    if max_lag >= ref.size + cur.size:
        raise ValueError("max_lag must be smaller than the combined sample size")
    if not isinstance(block_length, int) or isinstance(block_length, bool):
        raise ValueError("block_length must be an integer")
    max_block = max(1, min(ref.size, cur.size) // 2)
    if block_length < 1 or block_length > max_block:
        raise ValueError(
            f"block_length must be between 1 and {max_block} "
            f"(half the smaller sample size); got {block_length}"
        )
    if resamples < 0:
        raise ValueError("resamples must be non-negative")
    if seed < 0:
        raise ValueError("seed must be non-negative")

    stacked = np.concatenate([ref, cur])
    indicator = np.concatenate(
        [np.zeros(ref.size), np.ones(cur.size)]
    )
    hac = newey_west_hac(
        stacked, {"current": indicator}, max_lag=max_lag
    )
    indicator_coef = next(c for c in hac.coefficients if c.name == "current")
    ref_std = float(np.std(ref, ddof=1))
    cur_std = float(np.std(cur, ddof=1))
    ratio: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    if ref_std > 0.0 and cur_std > 0.0 and resamples > 0:
        rng = np.random.default_rng(seed)
        log_ratios: list[float] = []
        for _ in range(resamples):
            ref_star = _circular_block_resample(ref, block_length=block_length, rng=rng)
            cur_star = _circular_block_resample(cur, block_length=block_length, rng=rng)
            ref_std_star = float(np.std(ref_star, ddof=1))
            cur_std_star = float(np.std(cur_star, ddof=1))
            if ref_std_star > 0.0 and cur_std_star > 0.0:
                log_ratios.append(log(cur_std_star / ref_std_star))
        ratio = float(cur_std / ref_std)
        if len(log_ratios) >= 10:
            low, high = np.quantile(np.array(log_ratios), [0.025, 0.975])
            ci_low, ci_high = float(np.exp(low)), float(np.exp(high))
    elif ref_std > 0.0 and cur_std > 0.0:
        ratio = float(cur_std / ref_std)
    return WindowShiftResult(
        reference_n=int(ref.size),
        current_n=int(cur.size),
        reference_mean=float(np.mean(ref)),
        current_mean=float(np.mean(cur)),
        mean_difference=float(np.mean(cur) - np.mean(ref)),
        mean_difference_se=indicator_coef.standard_error,
        mean_difference_p_value=indicator_coef.p_value,
        reference_std=ref_std,
        current_std=cur_std,
        volatility_ratio=ratio,
        volatility_ratio_ci_low=ci_low,
        volatility_ratio_ci_high=ci_high,
        max_lag=int(max_lag),
        bootstrap_block_length=int(block_length),
        bootstrap_resamples=int(resamples),
        bootstrap_seed=int(seed),
    )


# ---------------------------------------------------------------------------
# Trend and decay estimation
# ---------------------------------------------------------------------------


class TrendResult(StrictContract):
    """Linear trend on a series (OLS + HAC standard error on the slope)."""

    slope: float = Field(allow_inf_nan=False)
    slope_se: float | None = Field(default=None, allow_inf_nan=False)
    slope_t: float | None = Field(default=None, allow_inf_nan=False)
    slope_p_value: float | None = Field(
        default=None, ge=0, le=1, allow_inf_nan=False
    )
    intercept: float = Field(allow_inf_nan=False)
    n: int = Field(ge=3)
    max_lag: int = Field(ge=0)


def fit_trend(
    values: Iterable[float], *, max_lag: int
) -> TrendResult:
    """Fit a linear trend (value ~ time index) with a HAC slope standard error.

    ``max_lag`` is the Newey-West lag: for a rolling-window series it
    should cover the overlap the window induces (window - 1 is the
    natural choice). It must be chosen before inspecting the result.
    """
    array = _finite_array(values, name="values")
    if array.size < 3:
        raise ValueError("a trend fit needs at least three observations")
    if not isinstance(max_lag, int) or isinstance(max_lag, bool) or max_lag < 0:
        raise ValueError("max_lag must be a non-negative integer")
    if max_lag >= array.size:
        raise ValueError("max_lag must be smaller than the sample size")
    time_index = np.arange(array.size, dtype=float)
    hac = newey_west_hac(array, {"t": time_index}, max_lag=max_lag)
    slope_coef = next(c for c in hac.coefficients if c.name == "t")
    intercept_coef = next(c for c in hac.coefficients if c.name == "intercept")
    return TrendResult(
        slope=float(slope_coef.estimate),
        slope_se=slope_coef.standard_error,
        slope_t=slope_coef.t_statistic,
        slope_p_value=slope_coef.p_value,
        intercept=float(intercept_coef.estimate),
        n=int(array.size),
        max_lag=int(max_lag),
    )


@dataclass(frozen=True)
class _ExponentialFit:
    half_life: float
    amplitude: float
    offset: float
    sse: float
    r_squared: float
    fitted: NDArray[np.float64]


def _fit_exponential_grid(
    design: NDArray[np.float64],
    values: NDArray[np.float64],
    half_lives: NDArray[np.float64],
) -> _ExponentialFit | None:
    """Best fit of value = a * exp(-lambda * t) + c over a half-life grid.

    ``design`` is exp(-lambda * t) for every grid half-life (columns).
    The two-parameter OLS per grid point is solved in closed form,
    vectorized over the grid. Only decaying fits (a > 0) are valid.
    """
    n = values.size
    s_x = design.sum(axis=0)
    s_xx = (design * design).sum(axis=0)
    s_y = float(values.sum())
    s_xy = design.T @ values
    s_yy = float(values @ values)
    det = n * s_xx - s_x**2
    scale = np.maximum(n * s_xx, 1e-300)
    well_conditioned = det > 1e-10 * scale
    safe_det = np.where(well_conditioned, det, 1.0)
    amplitude = (n * s_xy - s_x * s_y) / safe_det
    offset = (s_y - amplitude * s_x) / n
    sse = s_yy - amplitude * s_xy - offset * s_y
    valid = well_conditioned & (amplitude > 0.0) & np.isfinite(sse)
    if not np.any(valid):
        return None
    masked_sse = np.where(valid, np.maximum(sse, 0.0), np.inf)
    best = int(np.argmin(masked_sse))
    total_ss = s_yy - n * (s_y / n) ** 2
    if total_ss <= 0.0:
        r_squared = 1.0 if masked_sse[best] <= 0.0 else 0.0
    else:
        r_squared = 1.0 - float(masked_sse[best]) / float(total_ss)
    fitted = amplitude[best] * design[:, best] + offset[best]
    return _ExponentialFit(
        half_life=float(half_lives[best]),
        amplitude=float(amplitude[best]),
        offset=float(offset[best]),
        sse=float(masked_sse[best]),
        r_squared=float(r_squared),
        fitted=fitted,
    )


class DecayEstimate(StrictContract):
    """The result of a decay check on a rolling-skill series.

    ``detected`` is False unless the linear trend is significantly
    negative AND a decaying exponential fits well enough. A detected
    half-life always carries its bootstrap interval, the fit
    R-squared, and a stability flag; it is never a bare point
    estimate. ``stable`` is False when the fit is weak, the interval
    is wide relative to the estimate, or the estimate sits at the
    edge of the search grid.
    """

    detected: bool
    reason: str
    slope: float = Field(allow_inf_nan=False)
    slope_p_value: float | None = Field(
        default=None, ge=0, le=1, allow_inf_nan=False
    )
    half_life: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    half_life_ci_low: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    half_life_ci_high: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    fit_r_squared: float | None = Field(default=None, allow_inf_nan=False)
    stable: bool = False
    n: int = Field(ge=3)


def estimate_decay(
    skill: Iterable[float],
    *,
    max_lag: int,
    min_half_life: float = 5.0,
    max_half_life: float | None = None,
    grid_points: int = 80,
    significance_level: float = 0.05,
    min_fit_r_squared: float = 0.25,
    seed: int = 42,
    resamples: int = 500,
    bootstrap_block_length: int | None = None,
) -> DecayEstimate:
    """Check a rolling-skill series for exponential decay and estimate its half-life.

    Step 1 fits a linear trend (HAC). A non-negative or non-significant
    slope reports "not detected". Step 2 fits skill_t = a *
    exp(-lambda * t) + c by grid search over the half-life; a poor
    fit (R-squared below ``min_fit_r_squared``) or a non-decaying
    best fit also reports "not detected". Step 3, only for a detected
    decay, builds a residual circular-block bootstrap interval for
    the half-life (fixed seed, deterministic).
    """
    array = _finite_array(skill, name="skill")
    if array.size < 3:
        raise ValueError("a decay estimate needs at least three observations")
    if min_half_life <= 0.0 or not isfinite(min_half_life):
        raise ValueError("min_half_life must be positive and finite")
    ceiling = float(max_half_life) if max_half_life is not None else 10.0 * array.size
    if not isfinite(ceiling) or ceiling <= min_half_life:
        raise ValueError("max_half_life must exceed min_half_life")
    if grid_points < 2:
        raise ValueError("grid_points must be at least 2")
    if not 0.0 < significance_level < 1.0:
        raise ValueError("significance_level must be strictly between 0 and 1")
    if resamples < 0:
        raise ValueError("resamples must be non-negative")
    if seed < 0:
        raise ValueError("seed must be non-negative")
    block_length = (
        int(bootstrap_block_length)
        if bootstrap_block_length is not None
        else max(1, array.size // 10)
    )
    if block_length < 1 or block_length > max(1, array.size // 2):
        raise ValueError(
            "bootstrap_block_length must be between 1 and half the sample size"
        )

    trend = fit_trend(array, max_lag=max_lag)
    if trend.slope >= 0.0 or trend.slope_p_value is None:
        return DecayEstimate(
            detected=False,
            reason="no negative trend (slope is non-negative or untestable)",
            slope=trend.slope,
            slope_p_value=trend.slope_p_value,
            stable=False,
            n=int(array.size),
        )
    if trend.slope_p_value >= significance_level:
        return DecayEstimate(
            detected=False,
            reason=(
                f"negative trend is not significant "
                f"(HAC p = {trend.slope_p_value:.4g} >= {significance_level})"
            ),
            slope=trend.slope,
            slope_p_value=trend.slope_p_value,
            stable=False,
            n=int(array.size),
        )
    time_index = np.arange(array.size, dtype=float)
    half_lives = np.exp(
        np.linspace(log(min_half_life), log(ceiling), grid_points)
    )
    design = np.exp(-np.outer(time_index, np.log(2.0) / half_lives))
    fit = _fit_exponential_grid(design, array, half_lives)
    if fit is None:
        return DecayEstimate(
            detected=False,
            reason="no decaying exponential fits the series",
            slope=trend.slope,
            slope_p_value=trend.slope_p_value,
            stable=False,
            n=int(array.size),
        )
    if fit.r_squared < min_fit_r_squared:
        return DecayEstimate(
            detected=False,
            reason=(
                f"exponential fit too poor "
                f"(R-squared {fit.r_squared:.3f} below {min_fit_r_squared})"
            ),
            slope=trend.slope,
            slope_p_value=trend.slope_p_value,
            fit_r_squared=fit.r_squared,
            stable=False,
            n=int(array.size),
        )
    ci_low: float | None = None
    ci_high: float | None = None
    if resamples > 0:
        residuals = array - fit.fitted
        rng = np.random.default_rng(seed)
        estimates: list[float] = []
        for _ in range(resamples):
            boot_residuals = _circular_block_resample(
                residuals, block_length=block_length, rng=rng
            )
            refit = _fit_exponential_grid(design, fit.fitted + boot_residuals, half_lives)
            if refit is not None:
                estimates.append(refit.half_life)
        if len(estimates) >= 10:
            low, high = np.quantile(np.array(estimates), [0.025, 0.975])
            ci_low, ci_high = float(low), float(high)
    at_edge = fit.half_life <= min_half_life * 1.05 or fit.half_life >= ceiling * 0.95
    wide_interval = (
        ci_low is None
        or ci_high is None
        or (ci_high - ci_low) / fit.half_life > 1.0
    )
    stable = bool(
        fit.r_squared >= 0.5 and not at_edge and not wide_interval
    )
    return DecayEstimate(
        detected=True,
        reason=(
            "significant negative trend with a decaying exponential fit"
            + (" (estimate unstable: see interval and R-squared)" if not stable else "")
        ),
        slope=trend.slope,
        slope_p_value=trend.slope_p_value,
        half_life=fit.half_life,
        half_life_ci_low=ci_low,
        half_life_ci_high=ci_high,
        fit_r_squared=fit.r_squared,
        stable=stable,
        n=int(array.size),
    )


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


class AlertConfig(StrictContract):
    """Thresholds for drift flags. Flags are prompts, not conclusions."""

    skill_below_zero_windows: int = Field(default=3, ge=1)
    skill_threshold: float = Field(default=0.0)
    psi_threshold: float = Field(default=PSI_ALARM, gt=0)


class DriftFlag(StrictContract):
    """One drift flag: what tripped, when, at what value, against what threshold."""

    flag_type: str
    triggered_at: datetime | None = Field(default=None)
    value: float = Field(allow_inf_nan=False)
    threshold: float = Field(allow_inf_nan=False)
    detail: str


def check_alerts(
    skill_windows: Sequence[tuple[datetime | None, float | None]],
    psi_windows: Sequence[tuple[datetime | None, float | None]],
    *,
    config: AlertConfig | None = None,
) -> tuple[DriftFlag, ...]:
    """Apply the alert rules to rolling-skill and PSI window series.

    Each window is (window_end_time, value); a ``None`` value means
    the window was incomplete and breaks a skill run without
    flagging. One flag is emitted per run of
    ``skill_below_zero_windows`` consecutive rolling windows below
    the skill threshold (at the window where the run first reaches
    the count), and one flag per PSI window above the PSI threshold.
    Flags are returned in time order (unknown times last).
    """
    settings = config or AlertConfig()
    flags: list[DriftFlag] = []
    run_length = 0
    for when, value in skill_windows:
        if value is None or value >= settings.skill_threshold:
            run_length = 0
            continue
        run_length += 1
        if run_length == settings.skill_below_zero_windows:
            flags.append(
                DriftFlag(
                    flag_type="skill_below_zero",
                    triggered_at=when,
                    value=float(value),
                    threshold=float(settings.skill_threshold),
                    detail=(
                        f"{run_length} consecutive rolling windows with skill "
                        f"below {settings.skill_threshold}"
                    ),
                )
            )
    for when, value in psi_windows:
        if value is None or value <= settings.psi_threshold:
            continue
        flags.append(
            DriftFlag(
                flag_type="psi_high",
                triggered_at=when,
                value=float(value),
                threshold=float(settings.psi_threshold),
                detail=f"PSI {value:.3f} above threshold {settings.psi_threshold}",
            )
        )
    earliest = datetime.min.replace(tzinfo=UTC)
    return tuple(
        sorted(
            flags,
            key=lambda f: (
                f.triggered_at is None,
                f.triggered_at or earliest,
                f.flag_type,
            ),
        )
    )
