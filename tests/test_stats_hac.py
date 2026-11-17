import numpy as np
import pytest

from myquant.stats.hac import newey_west_hac


def test_newey_west_returns_symmetric_covariance_and_coefficient_inference():
    rng = np.random.default_rng(91)
    observations = 2_000
    x = rng.normal(size=observations)
    innovations = rng.normal(size=observations)
    errors = np.zeros(observations)
    for index in range(1, observations):
        errors[index] = 0.7 * errors[index - 1] + innovations[index]
    target = 0.4 + 0.8 * x + errors

    result = newey_west_hac(
        target,
        {"x": x},
        max_lag=12,
        small_sample_correction=True,
    )

    assert result.kernel == "bartlett"
    assert result.reference_distribution == "standard_normal"
    assert result.small_sample_correction is True
    assert result.ols.coefficients[1] == pytest.approx(0.8, abs=0.08)
    assert result.coefficients[1].name == "x"
    assert result.coefficients[1].standard_error is not None
    assert result.coefficients[1].standard_error > 0.0
    assert result.coefficients[1].p_value is not None
    assert result.coefficients[1].p_value < 0.001
    np.testing.assert_allclose(
        np.asarray(result.covariance_matrix),
        np.asarray(result.covariance_matrix).T,
        atol=1e-12,
    )


def test_zero_hac_lag_is_supported():
    x = np.linspace(-1.0, 1.0, 100)
    target = 2.0 + 0.5 * x + np.sin(np.arange(100, dtype=float))

    result = newey_west_hac(target, {"x": x}, max_lag=0)

    assert result.max_lag == 0
    assert len(result.coefficients) == 2
    assert result.coefficients[1].standard_error is not None


def test_newey_west_rejects_invalid_bandwidths_and_settings():
    x = np.arange(20, dtype=float)
    with pytest.raises(ValueError, match="non-negative"):
        newey_west_hac(x, {"x": x}, max_lag=-1)
    with pytest.raises(TypeError, match="integer"):
        newey_west_hac(x, {"x": x}, max_lag=True)
    with pytest.raises(ValueError, match="smaller than"):
        newey_west_hac(x, {"x": x}, max_lag=20)
    with pytest.raises(TypeError, match="boolean"):
        newey_west_hac(
            x,
            {"x": x},
            max_lag=2,
            small_sample_correction=1,  # type: ignore[arg-type]
        )
