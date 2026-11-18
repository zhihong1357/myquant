"""Standard-normal CDF and quantile functions (no SciPy dependency).

The kernel depends only on NumPy, pandas, pydantic and pyarrow, so the
normal quantile function is implemented here from Peter J. Acklam's
rational approximation (relative error below 1.15e-9) followed by one
Halley refinement step against the erf-based CDF, which brings the
result to near machine precision. The CDF itself is ``0.5 * erfc(-x /
sqrt(2))``, the same form the HAC and event-study modules already use.
"""

from __future__ import annotations

from math import erfc, exp, isfinite, log, pi, sqrt

# Acklam's coefficients for the inverse normal CDF.
_A = (
    -3.969683028665376e01,
    2.209460984245205e02,
    -2.759285104469687e02,
    1.383577518672690e02,
    -3.066479806614716e01,
    2.506628277459239e00,
)
_B = (
    -5.447609879822406e01,
    1.615858368580409e02,
    -1.556989798598866e02,
    6.680131188771972e01,
    -1.328068155288572e01,
)
_C = (
    -7.784894002430293e-03,
    -3.223964580411365e-01,
    -2.400758277161838e00,
    -2.549732539343734e00,
    4.374664141464968e00,
    2.938163982698783e00,
)
_D = (
    7.784695709041462e-03,
    3.224671290700398e-01,
    2.445134137142996e00,
    3.754408661907416e00,
)
_P_LOW = 0.02425
_P_HIGH = 1.0 - _P_LOW


def normal_cdf(x: float) -> float:
    """Standard-normal cumulative distribution function."""
    value = float(x)
    if not isfinite(value):
        raise ValueError("normal_cdf requires a finite input")
    return 0.5 * erfc(-value / sqrt(2.0))


def _acklam_ppf(probability: float) -> float:
    """Acklam's rational approximation to the normal quantile."""
    if probability < _P_LOW:
        q = sqrt(-2.0 * log(probability))
        numerator = (
            ((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]
        )
        denominator = (((( _D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0)
        return numerator / denominator
    if probability <= _P_HIGH:
        q = probability - 0.5
        r = q * q
        numerator = (
            (((((_A[0] * r + _A[1]) * r + _A[2]) * r + _A[3]) * r + _A[4]) * r + _A[5])
            * q
        )
        denominator = (
            ((((_B[0] * r + _B[1]) * r + _B[2]) * r + _B[3]) * r + _B[4]) * r + 1.0
        )
        return numerator / denominator
    q = sqrt(-2.0 * log(1.0 - probability))
    numerator = (
        ((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]
    )
    denominator = (((( _D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0)
    return -numerator / denominator


def normal_ppf(probability: float) -> float:
    """Standard-normal quantile function (inverse CDF).

    Acklam's approximation refined by one Halley step, accurate to
    near machine precision for probabilities strictly inside (0, 1).
    The endpoints are rejected: the quantile is infinite there, and a
    caller that needs a tail probability should pass an interior value.
    """
    p = float(probability)
    if not isfinite(p) or not 0.0 < p < 1.0:
        raise ValueError("normal_ppf requires a probability strictly between 0 and 1")
    x = _acklam_ppf(p)
    # One Halley refinement step against the erf-based CDF.
    error = normal_cdf(x) - p
    density_factor = sqrt(2.0 * pi) * exp(0.5 * x * x)
    u = error * density_factor
    return x - u / (1.0 + 0.5 * x * u)


def normal_sf(x: float) -> float:
    """Standard-normal survival function (1 - CDF), accurate in the tail."""
    value = float(x)
    if not isfinite(value):
        raise ValueError("normal_sf requires a finite input")
    return 0.5 * erfc(value / sqrt(2.0))


def normal_two_sided_p_value(z_statistic: float) -> float:
    """Two-sided p-value for a standard-normal test statistic."""
    value = float(z_statistic)
    if not isfinite(value):
        raise ValueError("normal_two_sided_p_value requires a finite statistic")
    return float(erfc(abs(value) / sqrt(2.0)))


def normal_pdf(x: float) -> float:
    """Standard-normal probability density function."""
    value = float(x)
    if not isfinite(value):
        raise ValueError("normal_pdf requires a finite input")
    return exp(-0.5 * value * value) / sqrt(2.0 * pi)


# Re-export erf for callers that already import the normal helpers.
__all__ = [
    "normal_cdf",
    "normal_pdf",
    "normal_ppf",
    "normal_sf",
    "normal_two_sided_p_value",
]
