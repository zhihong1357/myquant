"""Minimum detectable effects (MDE) for the lab's three main designs.

The MDE is the smallest true effect a design can detect with a given
power (default 80%) at a given significance level (default α = 0.05).
It is a property of the *design* — sample size, noise level, test
direction — not an observed conclusion. An observed effect below the
MDE is not evidence that no effect exists; it means the design would
reliably detect only effects at least that large.

All formulas use the normal approximation to the noncentral t
distribution: for a two-sided test at level α with power 1−β, the
required noncentrality is λ = z_{1−α/2} + z_{1−β} (2.80 at α = 0.05,
power 0.80); for a one-sided test, λ = z_{1−α} + z_{1−β} (2.49). The
normal approximation is accurate at the lab's sample sizes (n ≥ 100);
at small n it slightly understates the MDE, which is why the lead-lag
MDE is also checked by simulation
(:func:`simulate_lead_lag_power`).

Designs and their MDE measures:

- **Lead-lag OLS** (studies 001/002/003/004/006/007): the partial R²
  of the source in the augmented regression. For a single-coefficient
  F-test, partial R² = t²/(t² + df), so with t = λ and df ≈ n,
  MDE(R²_partial) = λ²/(λ² + n). The coefficient MDE is λ × SE(β̂).
- **Event-study CAR** (studies 005/007): the standardized mean CAR
  (mean CAR divided by the cross-sectional standard deviation of CARs).
  For a one-sample mean of n events, MDE = λ/√n. The lab's primary
  CAR tests are one-sided (direction "less"), so the one-sided λ
  applies; pass ``one_sided=False`` for a two-sided variant.
- **Mean comparison** (studies 004/006): Cohen's d between two groups,
  MDE(d) = λ·√(1/n₁ + 1/n₂). The effect-ratio form used by the lab
  (window mean / non-window mean) follows as 1 + λ·SE(diff)/mean_base.

Juxtaposing an MDE with an observed effect answers "was this design
capable of detecting an effect of the observed size?" — not "is the
effect real?". A significant result below the MDE is possible (the
significance threshold is z_{1−α/2} = 1.96, below λ = 2.80); it
simply means the study was underpowered for an effect of that size
and the estimate is likely inflated by selection (the "winner's
curse" — a significant estimate from an underpowered design tends to
exaggerate the true effect).
"""

from __future__ import annotations

from math import isfinite, sqrt

from pydantic import Field

from myquant.contracts import StrictContract
from myquant.stats._normal import normal_ppf
from myquant.stats.lead_lag import partial_lead_lag
from myquant.synthetic import SyntheticScenario, make_transmission_panel


class MinimumDetectableEffect(StrictContract):
    """Analytic minimum detectable effect for one design and measure."""

    design: str
    effect_measure: str
    minimum_detectable_effect: float = Field(ge=0, allow_inf_nan=False)
    alpha: float = Field(gt=0, lt=1)
    power: float = Field(gt=0, lt=1)
    one_sided: bool
    noncentrality: float = Field(gt=0, allow_inf_nan=False)
    sample_size: int = Field(ge=1)
    group_size_2: int | None = Field(default=None, ge=1)


class SimulatedPowerResult(StrictContract):
    """Empirical power of the lead-lag test at a given true coefficient."""

    replications: int = Field(ge=1)
    observations: int = Field(ge=100)
    beta: float = Field(allow_inf_nan=False)
    max_hac_lag: int = Field(ge=0)
    alpha: float = Field(gt=0, lt=1)
    rejections: int = Field(ge=0)
    empirical_power: float = Field(ge=0, le=1)
    monte_carlo_se: float = Field(ge=0)
    seed: int = Field(ge=0)


def noncentrality(alpha: float = 0.05, power: float = 0.80, *, one_sided: bool = False) -> float:
    """Noncentrality λ a test statistic needs for the given power.

    Two-sided: λ = z_{1−α/2} + z_power. One-sided: λ = z_{1−α} + z_power.
    """
    if not isfinite(alpha) or not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be between zero and one")
    if not isfinite(power) or not 0.0 < power < 1.0:
        raise ValueError("power must be between zero and one")
    critical = normal_ppf(1.0 - alpha) if one_sided else normal_ppf(1.0 - alpha / 2.0)
    return float(critical + normal_ppf(power))


def mde_partial_r_squared(
    observations: int,
    *,
    alpha: float = 0.05,
    power: float = 0.80,
) -> MinimumDetectableEffect:
    """MDE for the lead-lag partial R²: λ²/(λ² + n)."""
    if isinstance(observations, bool) or not isinstance(observations, int):
        raise TypeError("observations must be an integer")
    if observations < 1:
        raise ValueError("observations must be at least 1")
    value = noncentrality(alpha, power)
    mde = value * value / (value * value + observations)
    return MinimumDetectableEffect(
        design="lead_lag_ols",
        effect_measure="partial_r_squared",
        minimum_detectable_effect=float(mde),
        alpha=alpha,
        power=power,
        one_sided=False,
        noncentrality=value,
        sample_size=observations,
    )


def mde_coefficient(
    standard_error: float,
    *,
    alpha: float = 0.05,
    power: float = 0.80,
    one_sided: bool = False,
    sample_size: int = 1,
) -> MinimumDetectableEffect:
    """MDE for a regression coefficient: λ × SE(β̂)."""
    if not isfinite(standard_error) or standard_error <= 0.0:
        raise ValueError("standard_error must be finite and positive")
    if isinstance(sample_size, bool) or not isinstance(sample_size, int):
        raise TypeError("sample_size must be an integer")
    if sample_size < 1:
        raise ValueError("sample_size must be at least 1")
    value = noncentrality(alpha, power, one_sided=one_sided)
    return MinimumDetectableEffect(
        design="regression_coefficient",
        effect_measure="coefficient",
        minimum_detectable_effect=float(value * standard_error),
        alpha=alpha,
        power=power,
        one_sided=one_sided,
        noncentrality=value,
        sample_size=sample_size,
    )


def mde_standardized_mean(
    observations: int,
    *,
    alpha: float = 0.05,
    power: float = 0.80,
    one_sided: bool = True,
) -> MinimumDetectableEffect:
    """MDE for a standardized one-sample mean (e.g. standardized CAR): λ/√n.

    One-sided by default because the lab's primary CAR tests are
    one-sided (direction "less").
    """
    if isinstance(observations, bool) or not isinstance(observations, int):
        raise TypeError("observations must be an integer")
    if observations < 1:
        raise ValueError("observations must be at least 1")
    value = noncentrality(alpha, power, one_sided=one_sided)
    return MinimumDetectableEffect(
        design="event_study_car",
        effect_measure="standardized_mean_car",
        minimum_detectable_effect=float(value / sqrt(observations)),
        alpha=alpha,
        power=power,
        one_sided=one_sided,
        noncentrality=value,
        sample_size=observations,
    )


def mde_cohens_d(
    group_size_1: int,
    group_size_2: int,
    *,
    alpha: float = 0.05,
    power: float = 0.80,
) -> MinimumDetectableEffect:
    """MDE for Cohen's d between two groups: λ·√(1/n₁ + 1/n₂)."""
    for name, size in (("group_size_1", group_size_1), ("group_size_2", group_size_2)):
        if isinstance(size, bool) or not isinstance(size, int):
            raise TypeError(f"{name} must be an integer")
        if size < 1:
            raise ValueError(f"{name} must be at least 1")
    value = noncentrality(alpha, power)
    mde = value * sqrt(1.0 / group_size_1 + 1.0 / group_size_2)
    return MinimumDetectableEffect(
        design="mean_comparison",
        effect_measure="cohens_d",
        minimum_detectable_effect=float(mde),
        alpha=alpha,
        power=power,
        one_sided=False,
        noncentrality=value,
        sample_size=group_size_1,
        group_size_2=group_size_2,
    )


def mde_mean_ratio(
    mean_baseline: float,
    standard_error_of_difference: float,
    *,
    alpha: float = 0.05,
    power: float = 0.80,
    sample_size: int = 1,
) -> MinimumDetectableEffect:
    """MDE for a mean ratio (window mean / non-window mean): 1 + λ·SE/mean.

    The baseline mean and the standard error of the difference are
    design inputs (the noise scale); callers supply them from the
    design's variance estimates and label them as such.
    """
    if not isfinite(mean_baseline) or mean_baseline <= 0.0:
        raise ValueError("mean_baseline must be finite and positive")
    if not isfinite(standard_error_of_difference) or standard_error_of_difference <= 0.0:
        raise ValueError("standard_error_of_difference must be finite and positive")
    if isinstance(sample_size, bool) or not isinstance(sample_size, int):
        raise TypeError("sample_size must be an integer")
    if sample_size < 1:
        raise ValueError("sample_size must be at least 1")
    value = noncentrality(alpha, power)
    mde = 1.0 + value * standard_error_of_difference / mean_baseline
    return MinimumDetectableEffect(
        design="mean_comparison",
        effect_measure="mean_ratio",
        minimum_detectable_effect=float(mde),
        alpha=alpha,
        power=power,
        one_sided=False,
        noncentrality=value,
        sample_size=sample_size,
    )


def simulate_lead_lag_power(
    *,
    replications: int = 200,
    observations: int = 1_414,
    beta: float,
    max_hac_lag: int = 5,
    alpha: float = 0.05,
    seed: int = 2026,
) -> SimulatedPowerResult:
    """Empirical power of the lead-lag test at a known true coefficient.

    Panels come from the synthetic factory's SOURCE_LEADS_TARGET
    scenario (target[t] = beta · source[t−1] + noise, unit variances).
    Running this at beta equal to the analytic MDE coefficient checks
    whether the analytic MDE delivers the claimed power; the normal
    approximation is expected to be close at n ~ 1,400.
    """
    if isinstance(replications, bool) or not isinstance(replications, int):
        raise TypeError("replications must be an integer")
    if replications < 1:
        raise ValueError("replications must be at least 1")
    if isinstance(observations, bool) or not isinstance(observations, int):
        raise TypeError("observations must be an integer")
    if observations < 100:
        raise ValueError("observations must be at least 100")
    if not isfinite(beta):
        raise ValueError("beta must be finite")
    if isinstance(max_hac_lag, bool) or not isinstance(max_hac_lag, int):
        raise TypeError("max_hac_lag must be an integer")
    if max_hac_lag < 0:
        raise ValueError("max_hac_lag must be non-negative")
    if not isfinite(alpha) or not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be between zero and one")
    if seed < 0:
        raise ValueError("seed must be non-negative")

    rejections = 0
    for rep in range(replications):
        panel = make_transmission_panel(
            observations=observations,
            lag_steps=1,
            beta=beta,
            scenario=SyntheticScenario.SOURCE_LEADS_TARGET,
            seed=seed + rep,
        )
        result = partial_lead_lag(
            panel["source_value"].to_numpy(dtype=float),
            panel["target_return"].to_numpy(dtype=float),
            lag_steps=1,
            max_hac_lag=max_hac_lag,
        )
        p_value = result.source_effect.p_value
        if p_value is not None and p_value < alpha:
            rejections += 1
    empirical_power = rejections / replications
    return SimulatedPowerResult(
        replications=replications,
        observations=observations,
        beta=float(beta),
        max_hac_lag=max_hac_lag,
        alpha=alpha,
        rejections=rejections,
        empirical_power=empirical_power,
        monte_carlo_se=float(
            sqrt(empirical_power * (1.0 - empirical_power) / replications)
        ),
        seed=seed,
    )
