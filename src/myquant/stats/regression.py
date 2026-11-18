"""Deterministic ordinary least-squares regression primitives."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from math import isfinite
from typing import cast

import numpy as np
from numpy.typing import NDArray
from pydantic import Field

from myquant.contracts import StrictContract
from myquant.stats._validation import finite_numeric_array


class OLSResult(StrictContract):
    """OLS estimates and row-aligned fitted values/residuals."""

    observations: int = Field(ge=1)
    predictor_names: tuple[str, ...]
    coefficient_names: tuple[str, ...]
    coefficients: tuple[float, ...]
    intercept: float | None
    fitted_values: tuple[float, ...]
    residuals: tuple[float, ...]
    sum_squared_residuals: float = Field(ge=0, allow_inf_nan=False)
    r_squared: float = Field(allow_inf_nan=False)
    adjusted_r_squared: float | None = Field(default=None, allow_inf_nan=False)
    rank: int = Field(ge=1)
    degrees_of_freedom: int = Field(ge=0)
    condition_number: float = Field(
        ge=1,
        allow_inf_nan=False,
        description=(
            "2-norm condition number of the design matrix; large values "
            "indicate near-collinear predictors with unstable coefficients."
        ),
    )


def _finite_vector(values: Iterable[float], *, name: str) -> NDArray[np.float64]:
    result = finite_numeric_array(values, name=name)
    if result.size == 0:
        raise ValueError(f"{name} must not be empty")
    return result


def prepare_regression(
    target: Iterable[float],
    predictors: Mapping[str, Iterable[float]],
    *,
    include_intercept: bool,
) -> tuple[
    NDArray[np.float64],
    NDArray[np.float64],
    tuple[str, ...],
    tuple[str, ...],
]:
    """Validate regression inputs and build the target vector and design matrix.

    Shared by `ols_fit` and the Newey-West HAC estimator so both agree on
    input validation, predictor ordering and the design matrix.
    """
    if not isinstance(include_intercept, bool):
        raise TypeError("include_intercept must be a boolean")

    target_values = _finite_vector(target, name="target")
    predictor_items = tuple(predictors.items())
    names: list[str] = []
    columns: list[NDArray[np.float64]] = []

    for name, values in predictor_items:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("predictor names must be non-empty strings")
        if name == "intercept":
            raise ValueError("'intercept' is a reserved predictor name")
        if name in names:
            raise ValueError(f"predictor names must be unique: {name}")
        column = _finite_vector(values, name=f"predictor '{name}'")
        if column.size != target_values.size:
            raise ValueError(f"predictor '{name}' must match target length")
        names.append(name)
        columns.append(column)

    if not columns and not include_intercept:
        raise ValueError("at least one predictor is required without an intercept")

    if columns:
        predictor_matrix = cast(
            NDArray[np.float64],
            np.column_stack(columns),
        )
    else:
        predictor_matrix = np.empty((target_values.size, 0), dtype=np.float64)

    if include_intercept:
        design = np.column_stack(
            (np.ones(target_values.size, dtype=np.float64), predictor_matrix)
        )
        coefficient_names = ("intercept", *names)
    else:
        design = predictor_matrix
        coefficient_names = tuple(names)

    if target_values.size <= design.shape[1]:
        raise ValueError(
            "observations must exceed the number of fitted coefficients"
        )

    return (
        target_values,
        design,
        tuple(names),
        tuple(coefficient_names),
    )


def ols_fit(
    target: Iterable[float],
    predictors: Mapping[str, Iterable[float]],
    *,
    include_intercept: bool = True,
) -> OLSResult:
    """Fit a full-rank OLS model with explicit, ordered predictor names.

    Inputs are already aligned observations. This function does not join,
    resample, fill, lag, standardize, or infer point-in-time availability.

    The result reports the design matrix's 2-norm condition number. A
    large condition number means the predictors are nearly collinear and
    the coefficient estimates are unstable, even though the design is
    technically full rank.
    """
    target_values, design, predictor_names, coefficient_names = (
        prepare_regression(
            target,
            predictors,
            include_intercept=include_intercept,
        )
    )
    coefficients, _, rank, _ = np.linalg.lstsq(
        design,
        target_values,
        rcond=None,
    )
    if int(rank) != design.shape[1]:
        raise ValueError("design matrix is rank-deficient; predictors are collinear")

    fitted = design @ coefficients
    residuals = target_values - fitted
    residual_sum_squares = float(residuals @ residuals)

    if include_intercept:
        centered = target_values - float(np.mean(target_values))
        total_sum_squares = float(centered @ centered)
    else:
        total_sum_squares = float(target_values @ target_values)

    if total_sum_squares <= np.finfo(np.float64).eps:
        r_squared = 1.0 if residual_sum_squares <= np.finfo(np.float64).eps else 0.0
    else:
        r_squared = 1.0 - residual_sum_squares / total_sum_squares

    degrees_of_freedom = int(target_values.size - design.shape[1])
    adjusted_r_squared: float | None = None
    if include_intercept:
        adjusted_r_squared = 1.0 - (
            (1.0 - r_squared)
            * (target_values.size - 1)
            / degrees_of_freedom
        )

    values = tuple(float(value) for value in coefficients)
    intercept = values[0] if include_intercept else None
    if not isfinite(residual_sum_squares) or not isfinite(r_squared):
        raise ArithmeticError("OLS calculation produced a non-finite result")
    condition_number = float(np.linalg.cond(design))
    if not isfinite(condition_number):
        raise ArithmeticError("design matrix condition number is non-finite")

    return OLSResult(
        observations=int(target_values.size),
        predictor_names=predictor_names,
        coefficient_names=coefficient_names,
        coefficients=values,
        intercept=intercept,
        fitted_values=tuple(float(value) for value in fitted),
        residuals=tuple(float(value) for value in residuals),
        sum_squared_residuals=max(0.0, residual_sum_squares),
        r_squared=float(r_squared),
        adjusted_r_squared=(
            None if adjusted_r_squared is None else float(adjusted_r_squared)
        ),
        rank=int(rank),
        degrees_of_freedom=degrees_of_freedom,
        condition_number=condition_number,
    )
