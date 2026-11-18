"""Tests for risk model and exposure aggregation (offline)."""

import math

import numpy as np
import pytest

from myquant.portfolio.risk import (
    aggregate_exposure,
    historical_var_es,
    ledoit_wolf_covariance,
    portfolio_volatility,
    sample_covariance,
)


def test_aggregate_exposure_long_short_mixed():
    snapshot = aggregate_exposure(
        {
            "crypto:btc-usdt-perp": (10.0, 90_000.0, 0.01),
            "crypto:eth-usdt-perp": (-50.0, 3_000.0, 0.1),
            "crypto:sol-usdt-perp": (0.0, 150.0, 1.0),
        },
        equity=20_000.0,
    )
    # BTC: 10 x 90,000 x 0.01 = 9,000 long. ETH: -50 x 3,000 x 0.1 = -15,000.
    assert snapshot.long_notional == pytest.approx(9_000.0)
    assert snapshot.short_notional == pytest.approx(15_000.0)
    assert snapshot.net_notional == pytest.approx(-6_000.0)
    assert snapshot.gross_notional == pytest.approx(24_000.0)
    assert snapshot.max_single_share == pytest.approx(15_000.0 / 24_000.0)
    assert snapshot.leverage == pytest.approx(24_000.0 / 20_000.0)
    assert snapshot.positions[0].instrument_id == "crypto:btc-usdt-perp"
    assert snapshot.positions[1].notional == pytest.approx(-15_000.0)


def test_aggregate_exposure_flat_and_nonpositive_equity():
    snapshot = aggregate_exposure({}, equity=10_000.0)
    assert snapshot.gross_notional == 0.0
    assert snapshot.max_single_share == 0.0
    assert snapshot.leverage == 0.0
    snapshot_zero_equity = aggregate_exposure(
        {"crypto:btc-usdt-perp": (10.0, 90_000.0, 0.01)}, equity=0.0
    )
    # Leverage is undefined on non-positive equity: None, not infinity.
    assert snapshot_zero_equity.leverage is None
    with pytest.raises(ValueError, match="mark price must be positive"):
        aggregate_exposure(
            {"crypto:btc-usdt-perp": (10.0, 0.0, 0.01)}, equity=10_000.0
        )


def test_sample_covariance_hand_computed():
    # Two series with known covariance: x = (1, -1, 1, -1), y = (1, 1, -1, -1)
    # (scaled by 0.01). Means are 0; var(x) = var(y) = 0.0001 (ddof=1:
    # sum of squares 4e-4 / 3); cov(x, y) = 0.
    returns = np.array(
        [
            [0.01, 0.01],
            [-0.01, 0.01],
            [0.01, -0.01],
            [-0.01, -0.01],
        ]
    )
    cov = sample_covariance(returns)
    assert cov.shape == (2, 2)
    assert cov[0, 0] == pytest.approx(0.0001 * 4 / 3)
    assert cov[1, 1] == pytest.approx(0.0001 * 4 / 3)
    assert cov[0, 1] == pytest.approx(0.0)
    # Perfectly correlated pair: cov = var.
    returns2 = np.array([[0.01, 0.02], [-0.01, -0.02], [0.02, 0.04]])
    cov2 = sample_covariance(returns2)
    assert cov2[0, 1] == pytest.approx(
        math.sqrt(cov2[0, 0] * cov2[1, 1]), rel=1e-9
    )


def test_sample_covariance_rejects_bad_input():
    with pytest.raises(ValueError, match="two-dimensional"):
        sample_covariance(np.array([0.01, -0.01]))
    with pytest.raises(ValueError, match="at least two"):
        sample_covariance(np.array([[0.01, 0.02]]))
    with pytest.raises(ValueError, match="finite"):
        sample_covariance(np.array([[0.01, float("nan")], [0.02, 0.01]]))


def test_ledoit_wolf_matches_hand_computed_delta():
    """Delta re-derived from the paper's formulas with explicit loops."""
    rng = np.random.default_rng(7)
    factor = rng.normal(0, 0.02, 60)
    returns = np.column_stack(
        [
            factor * 0.8 + rng.normal(0, 0.01, 60),
            factor * 0.5 + rng.normal(0, 0.015, 60),
            rng.normal(0, 0.02, 60),
        ]
    )
    result = ledoit_wolf_covariance(returns)
    T, N = returns.shape
    means = [float(np.mean(returns[:, i])) for i in range(N)]
    # Sample covariance, 1/T normalization, explicit loops.
    sample = [[0.0] * N for _ in range(N)]
    for i in range(N):
        for j in range(N):
            sample[i][j] = sum(
                (returns[t, i] - means[i]) * (returns[t, j] - means[j])
                for t in range(T)
            ) / T
    mu = sum(sample[i][i] for i in range(N)) / N
    gamma = sum(
        (sample[i][j] - (mu if i == j else 0.0)) ** 2
        for i in range(N)
        for j in range(N)
    )
    pi_mat = [[0.0] * N for _ in range(N)]
    pi = 0.0
    for i in range(N):
        for j in range(N):
            pi_mat[i][j] = sum(
                (
                    (returns[t, i] - means[i]) * (returns[t, j] - means[j])
                    - sample[i][j]
                )
                ** 2
                for t in range(T)
            ) / T
            pi += pi_mat[i][j]
    rho = sum(pi_mat[i][i] for i in range(N))
    for i in range(N):
        for j in range(N):
            if i == j:
                continue
            corr = sample[i][j] / math.sqrt(sample[i][i] * sample[j][j])
            rho += 0.5 * corr * math.sqrt(pi_mat[i][i] * pi_mat[j][j])
    expected_delta = max(0.0, min((pi - rho) / (T * gamma), 1.0))
    assert result.shrinkage == pytest.approx(expected_delta, rel=1e-9)
    assert result.shrinkage_target_scale == pytest.approx(mu, rel=1e-9)
    # The shrunk matrix is the stated convex combination.
    expected = (1 - expected_delta) * np.array(sample) + expected_delta * mu * np.eye(N)
    np.testing.assert_allclose(result.covariance, expected, rtol=1e-9)
    # Shrinkage falls with T (same data-generating process, more data).
    rng2 = np.random.default_rng(11)
    factor2 = rng2.normal(0, 0.02, 1000)
    returns2 = np.column_stack(
        [
            factor2 * 0.8 + rng2.normal(0, 0.01, 1000),
            factor2 * 0.5 + rng2.normal(0, 0.015, 1000),
            rng2.normal(0, 0.02, 1000),
        ]
    )
    assert ledoit_wolf_covariance(returns2).shrinkage < result.shrinkage


def test_ledoit_wolf_identity_covariance_needs_no_shrinkage():
    rng = np.random.default_rng(1)
    returns = rng.normal(0, 0.01, (200, 3))
    result = ledoit_wolf_covariance(returns)
    assert 0.0 <= result.shrinkage <= 1.0
    # The shrunk matrix stays symmetric positive semi-definite.
    assert np.allclose(result.covariance, result.covariance.T)
    assert np.all(np.linalg.eigvalsh(result.covariance) >= -1e-15)


def test_portfolio_volatility():
    cov = np.array([[0.0004, 0.0001], [0.0001, 0.0009]])
    # Equal weights: var = 0.25*(0.0004 + 0.0009 + 2*0.0001) = 0.000375.
    assert portfolio_volatility(np.array([0.5, 0.5]), cov) == pytest.approx(
        math.sqrt(0.000375)
    )
    assert portfolio_volatility(np.array([1.0, 0.0]), cov) == pytest.approx(0.02)
    with pytest.raises(ValueError, match="dimensions do not match"):
        portfolio_volatility(np.array([1.0, 0.0, 0.0]), cov)


def test_historical_var_es_hand_computed():
    returns = np.array([-0.05, -0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03])
    result = historical_var_es(returns, confidence=0.75)
    # 25th percentile of the sorted returns, linear interpolation:
    # sorted = [-0.05, -0.03, -0.02, -0.01, 0, 0.01, 0.02, 0.03];
    # index (8-1)*0.25 = 1.75 -> -0.03 + 0.75*(-0.02 + 0.03) = -0.0225.
    assert result.var == pytest.approx(0.0225)
    # Tail: returns <= -0.0225 are -0.05 and -0.03; ES = mean loss 0.04.
    assert result.expected_shortfall == pytest.approx(0.04)
    assert result.observations == 8
    assert result.confidence == 0.75


def test_historical_var_es_all_gains_floors_at_zero():
    result = historical_var_es(np.array([0.01, 0.02, 0.03]), confidence=0.95)
    assert result.var == 0.0
    assert result.expected_shortfall == 0.0
    with pytest.raises(ValueError, match="confidence"):
        historical_var_es(np.array([0.01]), confidence=1.0)
