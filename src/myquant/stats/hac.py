"""Newey-West heteroskedasticity- and autocorrelation-consistent inference."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from math import erfc, isfinite, sqrt
from numbers import Integral
from typing import cast

import numpy as np
from numpy.typing import NDArray
from pydantic import Field

from myquant.contracts import StrictContract
from myquant.stats.regression import OLSResult, ols_fit, prepare_regression


class HACCoefficient(StrictContract):
    name: str
    estimate: float
    standard_error: float | None
    t_statistic: float | None
    p_value: float | None


class HACResult(StrictContract):
    """OLS estimates with Bartlett-kernel Newey-West covariance and inference.

    P-values use the two-sided asymptotic standard-normal reference distribution.
    """

    ols: OLSResult
    observations: int = Field(ge=2)
    max_lag: int = Field(ge=0)
    kernel: str = "bartlett"
    small_sample_correction: bool
    reference_distribution: str = "standard_normal"
    covariance_matrix: tuple[tuple[float, ...], ...]
    coefficients: tuple[HACCoefficient, ...]


def newey_west_hac(
    target: Iterable[float],
    predictors: Mapping[str, Iterable[float]],
    *,
    max_lag: int,
    include_intercept: bool = True,
    small_sample_correction: bool = False,
) -> HACResult:
    """Fit OLS and estimate its covariance with a Bartlett Newey-West HAC kernel.

    max_lag is the largest residual autocovariance lag included. It must be
    selected before inspecting results and should be subjected to sensitivity
    analysis. A zero lag is the heteroskedasticity-consistent HC0 covariance.
    """
    if isinstance(max_lag, bool) or not isinstance(max_lag, Integral):
        raise TypeError("max_lag must be an integer")
    if max_lag < 0:
        raise ValueError("max_lag must be non-negative")
    if not isinstance(small_sample_correction, bool):
        raise TypeError("small_sample_correction must be a boolean")

    target_values, design, _, coefficient_names = prepare_regression(
        target,
        predictors,
        include_intercept=include_intercept,
    )
    observations = int(target_values.size)
    if max_lag >= observations:
        raise ValueError("max_lag must be smaller than the sample size")

    fitted = ols_fit(
        target_values,
        predictors,
        include_intercept=include_intercept,
    )
    residuals = np.asarray(fitted.residuals, dtype=np.float64)
    scores = cast(NDArray[np.float64], design * residuals[:, None])
    meat = cast(NDArray[np.float64], scores.T @ scores)

    for lag in range(1, int(max_lag) + 1):
        weight = 1.0 - lag / (int(max_lag) + 1.0)
        cross_product = cast(
            NDArray[np.float64],
            scores[lag:].T @ scores[:-lag],
        )
        meat = meat + weight * (cross_product + cross_product.T)

    gram = cast(NDArray[np.float64], design.T @ design)
    # Solve for the sandwich covariance without forming the explicit
    # inverse: solve() is more accurate than inv() for ill-conditioned
    # designs. With B = (X'X)^-1 and symmetric meat M, the covariance is
    # B M B = (B (B M)^T)^T, computed here with two triangular solves.
    left = np.linalg.solve(gram, meat)
    covariance = cast(
        NDArray[np.float64],
        np.linalg.solve(gram, left.T).T,
    )
    if small_sample_correction:
        covariance = covariance * (
            observations / fitted.degrees_of_freedom
        )

    if not np.isfinite(covariance).all():
        raise ArithmeticError("HAC covariance calculation produced non-finite values")
    covariance = (covariance + covariance.T) / 2.0
    diagonal_scale = max(1.0, float(np.max(np.abs(np.diag(covariance)))))
    coefficient_results: list[HACCoefficient] = []

    for index, name in enumerate(coefficient_names):
        variance = float(covariance[index, index])
        if variance < -1e-12 * diagonal_scale:
            raise ArithmeticError("HAC covariance has a materially negative variance")
        standard_error = sqrt(max(0.0, variance))
        estimate = fitted.coefficients[index]
        if standard_error == 0.0:
            t_statistic: float | None = None
            p_value: float | None = None
        else:
            statistic = estimate / standard_error
            t_statistic = float(statistic)
            p_value = float(erfc(abs(statistic) / sqrt(2.0)))

        if not isfinite(standard_error):
            raise ArithmeticError("HAC standard error is non-finite")
        coefficient_results.append(
            HACCoefficient(
                name=name,
                estimate=estimate,
                standard_error=standard_error,
                t_statistic=t_statistic,
                p_value=p_value,
            )
        )

    matrix = tuple(
        tuple(float(value) for value in row)
        for row in covariance
    )
    return HACResult(
        ols=fitted,
        observations=observations,
        max_lag=int(max_lag),
        small_sample_correction=small_sample_correction,
        covariance_matrix=matrix,
        coefficients=tuple(coefficient_results),
    )
