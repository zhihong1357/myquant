"""Family-wise and false-discovery multiple-testing corrections."""

from __future__ import annotations

from collections.abc import Iterable
from math import isfinite

import numpy as np
from numpy.typing import NDArray
from pydantic import Field

from myquant.contracts import StrictContract
from myquant.hypotheses import MultiplicityCorrection


class AdjustedPValue(StrictContract):
    original_index: int = Field(ge=0)
    raw_p_value: float = Field(ge=0, le=1)
    adjusted_p_value: float = Field(ge=0, le=1)
    reject: bool
    method: MultiplicityCorrection
    target_error_rate: float = Field(gt=0, lt=1)


def adjust_pvalues(
    p_values: Iterable[float],
    *,
    method: MultiplicityCorrection,
    target_error_rate: float = 0.05,
) -> tuple[AdjustedPValue, ...]:
    """Adjust a predeclared family of p-values and preserve input order.

    Bonferroni and Holm control family-wise error rate (FWER). Benjamini-
    Hochberg controls false discovery rate (FDR) under its dependence
    assumptions. The function does not define the testing family: callers
    must include every planned test in that family, not only attractive
    results. NONE is permitted only for a single planned test.
    """
    values: NDArray[np.float64] = np.asarray(tuple(p_values), dtype=np.float64)
    if values.ndim != 1:
        raise ValueError("p_values must be a one-dimensional sequence")
    if values.size == 0:
        raise ValueError("p_values must not be empty")
    if not np.isfinite(values).all():
        raise ValueError("p_values must be finite")
    if ((values < 0.0) | (values > 1.0)).any():
        raise ValueError("p_values must lie in the closed interval [0, 1]")
    if not isfinite(target_error_rate) or not 0.0 < target_error_rate < 1.0:
        raise ValueError("target_error_rate must be between zero and one")
    if not isinstance(method, MultiplicityCorrection):
        raise TypeError("method must be a MultiplicityCorrection value")
    if method == MultiplicityCorrection.NONE and values.size != 1:
        raise ValueError("NONE correction is only valid for a single planned test")

    count = int(values.size)
    order = np.argsort(values, kind="stable")
    sorted_values: NDArray[np.float64] = values[order]
    sorted_adjusted: NDArray[np.float64] = sorted_values.copy()

    if method == MultiplicityCorrection.NONE:
    elif method == MultiplicityCorrection.BONFERRONI:
        sorted_adjusted = np.minimum(1.0, sorted_values * count)
    elif method == MultiplicityCorrection.HOLM:
        multipliers = count - np.arange(count)
        raw_adjusted: NDArray[np.float64] = np.asarray(
            sorted_values * multipliers,
            dtype=np.float64,
        )
        sorted_adjusted = np.minimum(
            1.0,
            np.maximum.accumulate(raw_adjusted),
        )
    elif method == MultiplicityCorrection.BENJAMINI_HOCHBERG:
        ranks = np.arange(1, count + 1)
        raw_adjusted = np.asarray(
            sorted_values * count / ranks,
            dtype=np.float64,
        )
        sorted_adjusted = np.minimum(
            1.0,
            np.minimum.accumulate(raw_adjusted[::-1])[::-1],
        )
    else:
        raise ValueError(f"unsupported multiple-testing method: {method}")

    adjusted = np.empty(count, dtype=float)
    adjusted[order] = sorted_adjusted
    return tuple(
        AdjustedPValue(
            original_index=index,
            raw_p_value=float(values[index]),
            adjusted_p_value=float(adjusted[index]),
            reject=bool(adjusted[index] <= target_error_rate),
            method=method,
            target_error_rate=target_error_rate,
        )
        for index in range(count)
    )
