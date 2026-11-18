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


# Golden standard errors from statsmodels 0.15.0 OLS(cov_type="HAC",
# use_correction=False) on the fixed dataset below (seed 7, n=300, AR(1)
# errors with rho=0.6). Generated during the 2026-11-18 review; myquant
# matches statsmodels to about 2e-15, so the 1e-12 tolerance below guards
# the formula without being brittle to floating-point reassociation.
HAC_GOLDEN_STANDARD_ERRORS = {
    0: (0.07592208073261744, 0.08451649157738123, 0.08680154589662513),
    5: (0.13157878460550934, 0.08124011229245301, 0.08465833557002045),
    12: (0.14639646646016755, 0.07849443268060807, 0.08516405194803897),
}


def _hac_golden_data():
    rng = np.random.default_rng(7)
    observations = 300
    x1 = rng.normal(size=observations)
    x2 = rng.normal(size=observations)
    innovations = rng.normal(size=observations)
    errors = np.zeros(observations)
    for index in range(1, observations):
        errors[index] = 0.6 * errors[index - 1] + innovations[index]
    target = 1.0 + 0.5 * x1 - 0.3 * x2 + errors
    return target, {"x1": x1, "x2": x2}


def test_newey_west_matches_statsmodels_golden_standard_errors():
    target, predictors = _hac_golden_data()
    for max_lag, expected in HAC_GOLDEN_STANDARD_ERRORS.items():
        result = newey_west_hac(target, predictors, max_lag=max_lag)
        actual = tuple(
            coefficient.standard_error for coefficient in result.coefficients
        )
        np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=0.0)


def test_newey_west_small_sample_correction_scales_by_n_over_dof():
    target, predictors = _hac_golden_data()
    plain = newey_west_hac(target, predictors, max_lag=5)
    corrected = newey_west_hac(
        target,
        predictors,
        max_lag=5,
        small_sample_correction=True,
    )
    ratio = np.asarray(corrected.covariance_matrix) / np.asarray(
        plain.covariance_matrix
    )
    np.testing.assert_allclose(ratio, 300 / 297, rtol=1e-12)
