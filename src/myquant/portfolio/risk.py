"""Risk model and exposure aggregation (Stage 5a).

Descriptive risk measures for a paper portfolio: exposure
aggregation (net/gross notional, concentration, leverage), a
covariance estimate from historical returns (sample covariance, with
an optional Ledoit–Wolf shrinkage toward a scaled identity), the
implied portfolio volatility, and historical-simulation VaR/ES.

Everything here is descriptive, not predictive: a covariance
estimated from past returns describes past co-movement; a VaR
computed from past returns describes past tail losses. None of it
forecasts anything, and none of it is a trading signal. Callers
must pass synchronized return series (same dates, same order); the
panel construction (per-series diff-then-join, as in the lab's
studies) is the caller's job — see ``docs/portfolio.md``.

Ledoit–Wolf shrinkage follows Ledoit & Wolf (2004), "A
well-conditioned estimator for large-dimensional covariance
matrices", *Journal of Empirical Finance* 11(5): the sample
covariance S (1/T normalization) is shrunk toward the scaled
identity μI with μ = tr(S)/N, at the estimated optimal intensity
δ* = max(0, min((π − ρ)/(T·γ), 1)), where γ = ||S − μI||²_F, π is
the sum of the asymptotic variances of the entries of √T·S, and ρ
is the asymptotic covariance term correcting for the estimated
target scale μ̂. (π and ρ are per-√T quantities, so the factor T
appears explicitly; δ* is O(1/T), as the paper requires.) When
γ = 0 (S is already proportional to the identity) no shrinkage is
needed and δ* = 0.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from pydantic import Field

from myquant.contracts import StrictContract


@dataclass(frozen=True)
class PositionExposure:
    """One instrument's exposure, in contracts and notional."""

    instrument_id: str
    quantity: float  # signed contracts (+ long, - short)
    mark_price: float
    contract_value: float
    notional: float  # signed notional in USDT
    abs_notional: float  # |notional| in USDT


class ExposureSnapshot(StrictContract):
    """Portfolio exposure at one mark time."""

    positions: tuple[PositionExposure, ...] = Field(default=())
    long_notional: float = Field(ge=0, allow_inf_nan=False)
    short_notional: float = Field(ge=0, allow_inf_nan=False)
    net_notional: float = Field(allow_inf_nan=False)
    gross_notional: float = Field(ge=0, allow_inf_nan=False)
    max_single_share: float = Field(ge=0, le=1, allow_inf_nan=False)
    equity: float = Field(allow_inf_nan=False)
    leverage: float | None = Field(default=None, ge=0, allow_inf_nan=False)


def aggregate_exposure(
    positions: dict[str, tuple[float, float, float]],
    *,
    equity: float,
) -> ExposureSnapshot:
    """Aggregate exposures from per-instrument positions.

    ``positions`` maps instrument_id to ``(quantity, mark_price,
    contract_value)``. Long and short notional are summed separately;
    concentration is the largest single instrument's share of gross
    notional; leverage is gross notional / equity, and is ``None``
    when equity is not positive (leverage is undefined on zero or
    negative equity — reported as unknown, not as zero or infinity).
    """
    rows: list[PositionExposure] = []
    for instrument_id in sorted(positions):
        quantity, mark_price, contract_value = positions[instrument_id]
        if mark_price <= 0:
            raise ValueError(f"mark price must be positive for {instrument_id}")
        if contract_value <= 0:
            raise ValueError(f"contract value must be positive for {instrument_id}")
        notional = quantity * mark_price * contract_value
        rows.append(
            PositionExposure(
                instrument_id=instrument_id,
                quantity=quantity,
                mark_price=mark_price,
                contract_value=contract_value,
                notional=notional,
                abs_notional=abs(notional),
            )
        )
    long_notional = sum(row.notional for row in rows if row.notional > 0)
    short_notional = sum(-row.notional for row in rows if row.notional < 0)
    gross = long_notional + short_notional
    net = long_notional - short_notional
    largest = max((row.abs_notional for row in rows), default=0.0)
    max_single_share = largest / gross if gross > 0 else 0.0
    return ExposureSnapshot(
        positions=tuple(rows),
        long_notional=long_notional,
        short_notional=short_notional,
        net_notional=net,
        gross_notional=gross,
        max_single_share=max_single_share,
        equity=equity,
        leverage=(gross / equity) if equity > 0 else None,
    )


def _validate_returns(returns: NDArray[np.float64]) -> NDArray[np.float64]:
    matrix = np.asarray(returns, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("returns must be a two-dimensional (T, N) array")
    if matrix.shape[0] < 2:
        raise ValueError("at least two return observations are required")
    if not np.isfinite(matrix).all():
        raise ValueError("returns must contain only finite values")
    return matrix


def sample_covariance(
    returns: NDArray[np.float64],
    *,
    ddof: int = 1,
) -> NDArray[np.float64]:
    """Sample covariance of synchronized return series (columns)."""
    matrix = _validate_returns(returns)
    if ddof < 0 or ddof >= matrix.shape[0]:
        raise ValueError("ddof must be between 0 and T - 1")
    centered = matrix - matrix.mean(axis=0)
    result: NDArray[np.float64] = np.asarray(
        (centered.T @ centered) / (matrix.shape[0] - ddof), dtype=np.float64
    )
    return result


@dataclass(frozen=True)
class ShrunkCovariance:
    """Ledoit–Wolf shrunk covariance and its shrinkage intensity."""

    covariance: NDArray[np.float64]
    sample_covariance: NDArray[np.float64]
    shrinkage: float  # delta* in [0, 1]
    shrinkage_target_scale: float  # mu = tr(S) / N
    observations: int
    variables: int


def ledoit_wolf_covariance(
    returns: NDArray[np.float64],
) -> ShrunkCovariance:
    """Ledoit–Wolf (2004) shrunk covariance, scaled-identity target.

    The sample covariance uses the paper's 1/T normalization. The
    shrinkage target is μI with μ = tr(S)/N; the intensity is
    δ* = max(0, min((π − ρ)/(T·γ), 1)), where π and ρ are the
    asymptotic (per-√T) variance/covariance sums, so the factor T
    appears explicitly. The shrunk matrix is (1 − δ*)·S + δ*·μI.
    """
    matrix = _validate_returns(returns)
    observations, variables = matrix.shape
    centered = matrix - matrix.mean(axis=0)
    sample = (centered.T @ centered) / observations
    mu = float(np.trace(sample) / variables)

    # gamma: squared Frobenius distance from the sample covariance to
    # the target.
    gamma = float(np.sum((sample - mu * np.eye(variables)) ** 2))
    if gamma == 0.0:
        # S is already proportional to the identity: no shrinkage.
        return ShrunkCovariance(
            covariance=sample.copy(),
            sample_covariance=sample,
            shrinkage=0.0,
            shrinkage_target_scale=mu,
            observations=observations,
            variables=variables,
        )

    # pi_ij: (1/T) * sum_t [(x_ti - xbar_i)(x_tj - xbar_j) - s_ij]^2,
    # computed as the mean over t of the squared demeaned outer
    # products minus the sample covariance.
    outer = np.einsum("ti,tj->tij", centered, centered)
    pi_matrix = np.mean((outer - sample) ** 2, axis=0)
    pi = float(np.sum(pi_matrix))

    # rho: sum_i pi_ii + sum_{i != j} (r_ij / 2) * sqrt(pi_ii * pi_jj),
    # with r_ij the sample correlation.
    variances = np.diag(sample)
    rho = float(np.sum(np.diag(pi_matrix)))
    for i in range(variables):
        for j in range(variables):
            if i == j or variances[i] <= 0 or variances[j] <= 0:
                continue
            corr = sample[i, j] / np.sqrt(variances[i] * variances[j])
            rho += 0.5 * corr * np.sqrt(pi_matrix[i, i] * pi_matrix[j, j])

    delta = max(0.0, min((pi - rho) / (observations * gamma), 1.0))
    shrunk = (1.0 - delta) * sample + delta * mu * np.eye(variables)
    return ShrunkCovariance(
        covariance=shrunk,
        sample_covariance=sample,
        shrinkage=float(delta),
        shrinkage_target_scale=mu,
        observations=observations,
        variables=variables,
    )


def portfolio_volatility(
    weights: NDArray[np.float64],
    covariance: NDArray[np.float64],
) -> float:
    """Portfolio volatility sqrt(w' Σ w) for one weight vector."""
    weights_arr = np.asarray(weights, dtype=float)
    cov = np.asarray(covariance, dtype=float)
    if weights_arr.ndim != 1:
        raise ValueError("weights must be a one-dimensional array")
    if cov.ndim != 2 or cov.shape[0] != cov.shape[1]:
        raise ValueError("covariance must be a square matrix")
    if weights_arr.shape[0] != cov.shape[0]:
        raise ValueError("weights and covariance dimensions do not match")
    if not np.isfinite(weights_arr).all() or not np.isfinite(cov).all():
        raise ValueError("weights and covariance must contain only finite values")
    variance = float(weights_arr @ cov @ weights_arr)
    if variance < 0:
        # Negative variance from numerical noise on a near-singular
        # matrix: floor at zero rather than returning NaN.
        variance = 0.0
    return float(np.sqrt(variance))


class HistoricalVarEs(StrictContract):
    """Historical-simulation VaR and expected shortfall, one window."""

    confidence: float = Field(gt=0, lt=1, allow_inf_nan=False)
    observations: int = Field(ge=1)
    var: float = Field(ge=0, allow_inf_nan=False)
    expected_shortfall: float = Field(ge=0, allow_inf_nan=False)


def historical_var_es(
    returns: NDArray[np.float64],
    *,
    confidence: float = 0.95,
) -> HistoricalVarEs:
    """Historical-simulation VaR/ES on a return series (losses positive).

    VaR is the (1 − confidence) quantile of returns, negated (a loss
    is positive); ES is the mean loss beyond VaR. Quantiles use
    linear interpolation (numpy's default). Both are floored at zero:
    a positive tail quantile means no loss at that confidence. Both
    are measured on the supplied window only — the window is the
    caller's choice and must be stated wherever the numbers are
    reported.
    """
    series = np.asarray(returns, dtype=float).reshape(-1)
    if series.size < 1:
        raise ValueError("at least one return observation is required")
    if not np.isfinite(series).all():
        raise ValueError("returns must contain only finite values")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be strictly between 0 and 1")
    var = float(-np.quantile(series, 1.0 - confidence))
    tail = series[series <= np.quantile(series, 1.0 - confidence)]
    expected_shortfall = float(-np.mean(tail)) if tail.size else var
    return HistoricalVarEs(
        confidence=confidence,
        observations=int(series.size),
        var=max(var, 0.0),
        expected_shortfall=max(expected_shortfall, 0.0),
    )
