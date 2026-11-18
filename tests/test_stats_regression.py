import numpy as np
import pytest

from myquant.stats.regression import ols_fit


def test_ols_recovers_known_coefficients_and_reports_fit_statistics():
    rng = np.random.default_rng(123)
    first = rng.normal(size=500)
    second = rng.normal(size=500)
    target = 1.25 + 2.0 * first - 0.75 * second

    result = ols_fit(
        target,
        {"first": first, "second": second},
    )

    assert result.coefficient_names == ("intercept", "first", "second")
    assert result.intercept == pytest.approx(1.25)
    assert result.coefficients[1] == pytest.approx(2.0)
    assert result.coefficients[2] == pytest.approx(-0.75)
    assert result.r_squared == pytest.approx(1.0)
    assert result.adjusted_r_squared == pytest.approx(1.0)
    assert result.degrees_of_freedom == 497
    assert max(abs(value) for value in result.residuals) < 1e-12


def test_ols_supports_a_model_without_an_intercept():
    x = np.linspace(-2.0, 2.0, 100)
    result = ols_fit(3.0 * x, {"x": x}, include_intercept=False)

    assert result.intercept is None
    assert result.coefficient_names == ("x",)
    assert result.coefficients[0] == pytest.approx(3.0)
    assert result.adjusted_r_squared is None


def test_ols_rejects_misaligned_nonfinite_and_rank_deficient_inputs():
    x = np.arange(20, dtype=float)
    with pytest.raises(ValueError, match="match target length"):
        ols_fit(x, {"short": x[:-1]})
    with pytest.raises(ValueError, match="finite"):
        ols_fit(x, {"bad": np.where(x == 3.0, np.nan, x)})
    with pytest.raises(ValueError, match="rank-deficient"):
        ols_fit(x, {"x": x, "duplicate": 2.0 * x})


def test_ols_rejects_undersized_and_invalid_designs():
    with pytest.raises(ValueError, match="exceed"):
        ols_fit([1.0, 2.0], {"x": [1.0, 2.0]})
    with pytest.raises(ValueError, match="at least one predictor"):
        ols_fit([1.0, 2.0, 3.0], {}, include_intercept=False)
    with pytest.raises(ValueError, match="reserved"):
        ols_fit([1.0, 2.0, 3.0], {"intercept": [1.0, 2.0, 3.0]})


def test_ols_rejects_string_and_boolean_inputs():
    x = [1.0, 2.0, 3.0, 4.0]
    with pytest.raises(TypeError, match="numeric values"):
        ols_fit(["1.0", "2.0", "3.0", "4.0"], {"x": x})
    with pytest.raises(TypeError, match="numeric values"):
        ols_fit(x, {"x": [True, False, True, False]})
    with pytest.raises(TypeError, match="numeric values"):
        ols_fit(x, {"x": np.array([True, False, True, False])})


def test_ols_matches_hand_computed_small_sample_values():
    # Exact hand computation: x = 0..3, y = 2,4,5,8 gives slope 1.9,
    # intercept 1.9, residuals (0.1, 0.2, -0.7, 0.4), RSS 0.7,
    # R^2 = 361/375 and adjusted R^2 = 0.944.
    result = ols_fit([2.0, 4.0, 5.0, 8.0], {"x": [0.0, 1.0, 2.0, 3.0]})

    assert result.coefficients == pytest.approx((1.9, 1.9), abs=1e-12)
    assert result.residuals == pytest.approx((0.1, 0.2, -0.7, 0.4), abs=1e-12)
    assert result.sum_squared_residuals == pytest.approx(0.7, abs=1e-12)
    assert result.r_squared == pytest.approx(361 / 375, abs=1e-12)
    assert result.adjusted_r_squared == pytest.approx(0.944, abs=1e-12)
    assert result.degrees_of_freedom == 2


def test_ols_reports_condition_number_for_near_collinear_design():
    rng = np.random.default_rng(7)
    x = rng.normal(size=200)
    clean = ols_fit(2.0 * x, {"x": x})
    assert clean.condition_number >= 1.0
    assert clean.condition_number < 10.0

    near_duplicate = x + rng.normal(scale=1e-8, size=200)
    target = 1.0 + 2.0 * x + 0.5 * near_duplicate
    result = ols_fit(target, {"x": x, "near_duplicate": near_duplicate})
    assert result.condition_number > 1e6
