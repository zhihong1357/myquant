"""Calibration simulations for the lab's testing procedures.

A test that claims a 5% false-positive rate should reject a true null
about 5% of the time, and a 95% confidence interval should cover the
true value about 95% of the time. These simulations check the lab's
procedures against known nulls, using the synthetic factory
(:func:`myquant.synthetic.make_transmission_panel`) where it fits and
direct AR(1) generation where it does not (the factory has no
autocorrelated null scenario). Every simulation is deterministic given
its seed, and every rate is reported with its Monte Carlo standard
error, sqrt(p(1-p)/R), so a deviation from the nominal level can be
judged against simulation noise rather than eyeballed.

Procedures covered:

- **HAC t-test size** — the lead-lag test's Newey-West HAC p-value
  (``partial_lead_lag``) on NULL panels (no source-to-target effect),
  iid and AR(1) with phi = 0.3. The HAC p-value is asymptotic, so the
  question is whether the nominal 5% level holds at the lab's sample
  sizes (n ~ 1,400 daily bars).
- **Block-bootstrap CI coverage** — ``block_bootstrap_mean_ci`` on
  series with known mean zero, iid and AR(1) with phi = 0.3. Block
  bootstrap coverage is approximate and block-length sensitive; a
  shortfall is reported honestly, not hidden.
- **Holm FWER** — ``adjust_pvalues`` with method Holm on families of
  null p-values, independent (uniform) and equicorrelated (Gaussian
  copula, rho = 0.3). Holm controls the family-wise error rate under
  arbitrary dependence, so both variants should stay at or below the
  nominal level; the correlated variant is the informative one for the
  lab, whose tests reuse the same data.

A calibration result describes the *procedure*, not any single study:
a well-calibrated procedure can still produce a false positive on one
real dataset, and a miscalibrated one does not retroactively invalidate
a study's preregistered verdict.
"""

from __future__ import annotations

from math import isfinite, sqrt

import numpy as np
from pydantic import Field

from myquant.contracts import MultiplicityCorrection, StrictContract
from myquant.stats._normal import normal_cdf
from myquant.stats.bootstrap import block_bootstrap_mean_ci
from myquant.stats.lead_lag import partial_lead_lag
from myquant.stats.multiple_testing import adjust_pvalues
from myquant.synthetic import SyntheticScenario, make_transmission_panel


def _require_int(value: int, name: str, *, minimum: int) -> int:
    """Validate an integer setting (booleans are not accepted as integers)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


class HACSizeResult(StrictContract):
    """Empirical size of the lead-lag HAC t-test under a known null."""

    replications: int = Field(ge=1)
    observations: int = Field(ge=100)
    max_hac_lag: int = Field(ge=0)
    alpha: float = Field(gt=0, lt=1)
    autocorrelation: float = Field(ge=-1, le=1)
    rejections: int = Field(ge=0)
    rejection_rate: float = Field(ge=0, le=1)
    monte_carlo_se: float = Field(ge=0)
    seed: int = Field(ge=0)


class BootstrapCoverageResult(StrictContract):
    """Empirical coverage of the block-bootstrap mean confidence interval."""

    replications: int = Field(ge=1)
    observations: int = Field(ge=2)
    block_length: int = Field(ge=1)
    resamples: int = Field(ge=100)
    confidence_level: float = Field(gt=0, lt=1)
    autocorrelation: float = Field(ge=-1, le=1)
    covered: int = Field(ge=0)
    coverage: float = Field(ge=0, le=1)
    monte_carlo_se: float = Field(ge=0)
    seed: int = Field(ge=0)


class HolmFWERResult(StrictContract):
    """Empirical family-wise error rate of Holm correction on null p-values."""

    replications: int = Field(ge=1)
    family_size: int = Field(ge=1)
    alpha: float = Field(gt=0, lt=1)
    correlation: float = Field(ge=0, le=1)
    families_with_rejection: int = Field(ge=0)
    family_wise_error_rate: float = Field(ge=0, le=1)
    monte_carlo_se: float = Field(ge=0)
    seed: int = Field(ge=0)


def monte_carlo_se(rate: float, replications: int) -> float:
    """Standard error of an estimated rate from ``replications`` Bernoulli draws."""
    if not 0.0 <= rate <= 1.0:
        raise ValueError("rate must be between zero and one")
    if replications < 1:
        raise ValueError("replications must be at least 1")
    return float(sqrt(rate * (1.0 - rate) / replications))


def _ar1_series(rng: np.random.Generator, observations: int, phi: float) -> np.ndarray:
    """Stationary AR(1) series with unit marginal variance."""
    innovations = rng.normal(0.0, 1.0, observations)
    series = np.empty(observations, dtype=float)
    series[0] = innovations[0] / sqrt(1.0 - phi * phi) if abs(phi) < 1.0 else 0.0
    for index in range(1, observations):
        series[index] = phi * series[index - 1] + innovations[index]
    return series


def calibrate_hac_size(
    *,
    replications: int = 500,
    observations: int = 1_414,
    max_hac_lag: int = 5,
    alpha: float = 0.05,
    autocorrelation: float = 0.0,
    seed: int = 2026,
) -> HACSizeResult:
    """Empirical size of the lead-lag HAC test under the null of no effect.

    With ``autocorrelation == 0`` the panels come from the synthetic
    factory's NULL scenario (independent Gaussian source and target).
    With nonzero autocorrelation, source and target are independent
    AR(1) series with the given phi, generated directly (the factory
    has no autocorrelated null scenario). Each replication runs
    ``partial_lead_lag`` at lag 1 and counts a rejection when the
    two-sided HAC p-value is below ``alpha``.
    """
    replications = _require_int(replications, "replications", minimum=1)
    observations = _require_int(observations, "observations", minimum=100)
    max_hac_lag = _require_int(max_hac_lag, "max_hac_lag", minimum=0)
    if not isfinite(alpha) or not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be between zero and one")
    if not isfinite(autocorrelation) or not -1.0 < autocorrelation < 1.0:
        raise ValueError("autocorrelation must be strictly between -1 and 1")
    if seed < 0:
        raise ValueError("seed must be non-negative")

    rejections = 0
    for rep in range(replications):
        if autocorrelation == 0.0:
            panel = make_transmission_panel(
                observations=observations,
                lag_steps=1,
                scenario=SyntheticScenario.NULL,
                seed=seed + rep,
            )
            source = panel["source_value"].to_numpy(dtype=float)
            target = panel["target_return"].to_numpy(dtype=float)
        else:
            rng = np.random.default_rng(seed + rep)
            source = _ar1_series(rng, observations, autocorrelation)
            target = _ar1_series(rng, observations, autocorrelation)
        result = partial_lead_lag(
            source,
            target,
            lag_steps=1,
            max_hac_lag=max_hac_lag,
        )
        p_value = result.source_effect.p_value
        if p_value is not None and p_value < alpha:
            rejections += 1
    rate = rejections / replications
    return HACSizeResult(
        replications=replications,
        observations=observations,
        max_hac_lag=max_hac_lag,
        alpha=alpha,
        autocorrelation=autocorrelation,
        rejections=rejections,
        rejection_rate=rate,
        monte_carlo_se=monte_carlo_se(rate, replications),
        seed=seed,
    )


def calibrate_bootstrap_coverage(
    *,
    replications: int = 200,
    observations: int = 2_125,
    block_length: int = 10,
    resamples: int = 500,
    confidence_level: float = 0.95,
    autocorrelation: float = 0.0,
    seed: int = 2026,
) -> BootstrapCoverageResult:
    """Empirical coverage of the block-bootstrap CI for a known mean of zero.

    Each replication draws a series with true mean zero (iid Gaussian,
    or AR(1) with the given phi) and checks whether the
    ``block_bootstrap_mean_ci`` interval covers zero.
    """
    replications = _require_int(replications, "replications", minimum=1)
    observations = _require_int(observations, "observations", minimum=2)
    block_length = _require_int(block_length, "block_length", minimum=1)
    resamples = _require_int(resamples, "resamples", minimum=100)
    if not isfinite(confidence_level) or not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be between zero and one")
    if not isfinite(autocorrelation) or not -1.0 < autocorrelation < 1.0:
        raise ValueError("autocorrelation must be strictly between -1 and 1")
    if seed < 0:
        raise ValueError("seed must be non-negative")

    covered = 0
    for rep in range(replications):
        rng = np.random.default_rng(seed + rep)
        if autocorrelation == 0.0:
            series = rng.normal(0.0, 1.0, observations)
        else:
            series = _ar1_series(rng, observations, autocorrelation)
        interval = block_bootstrap_mean_ci(
            series,
            block_length=block_length,
            resamples=resamples,
            confidence_level=confidence_level,
            seed=seed + rep,
        )
        if interval.lower_bound <= 0.0 <= interval.upper_bound:
            covered += 1
    coverage = covered / replications
    return BootstrapCoverageResult(
        replications=replications,
        observations=observations,
        block_length=block_length,
        resamples=resamples,
        confidence_level=confidence_level,
        autocorrelation=autocorrelation,
        covered=covered,
        coverage=coverage,
        monte_carlo_se=monte_carlo_se(coverage, replications),
        seed=seed,
    )


def calibrate_holm_fwer(
    *,
    replications: int = 5_000,
    family_size: int = 36,
    alpha: float = 0.05,
    correlation: float = 0.0,
    seed: int = 2026,
) -> HolmFWERResult:
    """Empirical FWER of Holm correction on families of null p-values.

    With ``correlation == 0`` the p-values are independent uniform draws.
    With nonzero correlation they come from a Gaussian copula: equicorrelated
    standard-normal z-scores (common-factor construction) converted to
    two-sided p-values, so the family shares one latent component. FWER is
    the fraction of families with at least one Holm rejection.
    """
    replications = _require_int(replications, "replications", minimum=1)
    family_size = _require_int(family_size, "family_size", minimum=1)
    if not isfinite(alpha) or not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be between zero and one")
    if not isfinite(correlation) or not 0.0 <= correlation < 1.0:
        raise ValueError("correlation must be between zero (inclusive) and one")
    if seed < 0:
        raise ValueError("seed must be non-negative")

    rng = np.random.default_rng(seed)
    families_with_rejection = 0
    for _ in range(replications):
        if correlation == 0.0:
            p_values = rng.uniform(0.0, 1.0, family_size)
        else:
            common = rng.normal(0.0, 1.0)
            idiosyncratic = rng.normal(0.0, 1.0, family_size)
            z_scores = (
                sqrt(correlation) * common
                + sqrt(1.0 - correlation) * idiosyncratic
            )
            p_values = np.array(
                [2.0 * (1.0 - normal_cdf(abs(z))) for z in z_scores], dtype=float
            )
        adjusted = adjust_pvalues(
            p_values,
            method=MultiplicityCorrection.HOLM,
            target_error_rate=alpha,
        )
        if any(entry.reject for entry in adjusted):
            families_with_rejection += 1
    fwer = families_with_rejection / replications
    return HolmFWERResult(
        replications=replications,
        family_size=family_size,
        alpha=alpha,
        correlation=correlation,
        families_with_rejection=families_with_rejection,
        family_wise_error_rate=fwer,
        monte_carlo_se=monte_carlo_se(fwer, replications),
        seed=seed,
    )
