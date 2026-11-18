"""Shared numeric-input validation for statistical primitives."""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast

import numpy as np
from numpy.typing import NDArray


def numeric_array(values: Iterable[float], *, name: str) -> NDArray[np.float64]:
    """Convert a one-dimensional sequence to a float64 array.

    String, bytes and boolean elements are rejected instead of silently
    converted: "1.5" must not become 1.5 and True must not become 1.0.
    NaN and Infinity are allowed here; use finite_numeric_array when the
    caller requires finite values.
    """
    items = tuple(values)
    for item in items:
        if isinstance(item, (str, bytes, bool, np.bool_)):
            raise TypeError(
                f"{name} must contain numeric values, not {type(item).__name__}"
            )
    try:
        result = np.asarray(items, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{name} must contain numeric values") from exc
    if result.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    return cast(NDArray[np.float64], result)


def finite_numeric_array(
    values: Iterable[float],
    *,
    name: str,
) -> NDArray[np.float64]:
    """Convert a sequence to a float64 array of finite values only."""
    result = numeric_array(values, name=name)
    if not np.isfinite(result).all():
        raise ValueError(f"{name} must contain only finite values")
    return result
