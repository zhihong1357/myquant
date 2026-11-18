"""Tests for the Deflated Sharpe Ratio and PBO overfitting diagnostics.

DSR expectations use realistic per-period Sharpe ratios (a daily Sharpe
of 0.06 is about 0.95 annualized); a per-period Sharpe of 1.0 would be an
annualized Sharpe near 16 and sits far outside the informative range.
PBO scenarios are synthetic strategy-return matrices with known ground
truth: a persistent edge (clean), pure noise, and sign-flipping edges
(overfit). All random draws use fixed seeds.
"""

import numpy as np
import pytest

from myquant.stats.overfitting import (
    deflated_sharpe_ratio,
    deflated_sharpe_ratio_from_returns,
    expected_max_sharpe,
    probability_of_backtest_overfitting,
    sharpe_ratio,
    sharpe_ratio_variance,
)

TWO_SIDED_95 = 1.959963984540054


def test_sharpe_ratio_matches_mean_over_sd():
    returns = np.array([0.01, -0.02, 0.03, 0.00, 0.02])
    expected = float(np.mean(returns) / np.std(returns, ddof=1))
    assert sharpe_ratio(returns) == pytest.approx(expected)


def test_sharpe_ratio_rejects_zero_variance_and_short_series():
    with pytest.raises(ValueError, match="zero-variance"):
        sharpe_ratio([0.01, 0.01, 0.01])
    with pytest.raises(ValueError, match="at least two"):
        sharpe_ratio([0.01])


def test_sharpe_variance_gaussian_case():
    # Gaussian returns: Var = (1 + SR^2/2) / (T - 1).
    assert sharpe_ratio_variance(0.0, 252) == pytest.approx(1.0 / 251)
    assert sharpe_ratio_variance(0.1, 101) == pytest.approx((1.0 + 0.005) / 100)


def test_sharpe_variance_skew_and_kurtosis_terms():
    base = sharpe_ratio_variance(0.1, 101)
    # Positive skew with a positive Sharpe lowers the variance.
    assert sharpe_ratio_variance(0.1, 101, skewness=1.0) < base
    # Positive excess kurtosis raises it.
    assert sharpe_ratio_variance(0.1, 101, excess_kurtosis=3.0) > base


def test_expected_max_sharpe_no_selection_is_zero():
    assert expected_max_sharpe(252, 1) == 0.0
    assert expected_max_sharpe(252, 10) == pytest.approx(0.09938776349367455)


def test_expected_max_sharpe_grows_with_trials_and_shrinks_with_sample():
    assert expected_max_sharpe(252, 100) > expected_max_sharpe(252, 10)
    assert expected_max_sharpe(252, 10) > expected_max_sharpe(1000, 10)


def test_dsr_zero_sharpe_no_selection_is_one_half():
    result = deflated_sharpe_ratio(0.0, 252, 1)
    assert result.deflated_sharpe_ratio == pytest.approx(0.5)
    assert result.expected_max_sharpe == 0.0


def test_dsr_hand_computed_value():
    # SR = 0.06/day, T = 252, N = 10, Gaussian returns:
    # E[max] = 0.09939, Var = (1 + 0.5*0.06^2)/251, DSR = Phi((0.06-0.09939)/sd).
    result = deflated_sharpe_ratio(0.06, 252, 10)
    assert result.expected_max_sharpe == pytest.approx(0.09938776349367455)
    assert result.sharpe_variance == pytest.approx((1.0 + 0.5 * 0.06**2) / 251)
    assert result.deflated_sharpe_ratio == pytest.approx(0.2667, abs=0.001)


def test_dsr_monotone_in_sharpe_trials_and_sample():
    assert (
        deflated_sharpe_ratio(0.12, 252, 10).deflated_sharpe_ratio
        > deflated_sharpe_ratio(0.06, 252, 10).deflated_sharpe_ratio
    )
    assert (
        deflated_sharpe_ratio(0.06, 252, 100).deflated_sharpe_ratio
        < deflated_sharpe_ratio(0.06, 252, 10).deflated_sharpe_ratio
    )
    assert (
        deflated_sharpe_ratio(0.06, 1000, 10).deflated_sharpe_ratio
        > deflated_sharpe_ratio(0.06, 252, 10).deflated_sharpe_ratio
    )


def test_dsr_negative_sharpe_below_one_half():
    assert deflated_sharpe_ratio(-0.05, 252, 10).deflated_sharpe_ratio < 0.5


def test_dsr_positive_skew_raises_dsr_when_sharpe_exceeds_null_max():
    # Positive skew shrinks Var[SR-hat], which moves the DSR away from
    # 0.5 in the direction of (SR-hat - E[max]): up when the observed
    # Sharpe is above the null maximum, down when it is below it.
    plain = deflated_sharpe_ratio(0.2, 252, 10)
    skewed = deflated_sharpe_ratio(0.2, 252, 10, skewness=1.0)
    assert skewed.deflated_sharpe_ratio > plain.deflated_sharpe_ratio
    assert plain.deflated_sharpe_ratio > 0.5


def test_dsr_from_returns_matches_direct_call():
    rng = np.random.default_rng(11)
    returns = rng.normal(0.001, 0.02, 500)
    from_series = deflated_sharpe_ratio_from_returns(returns, 10)
    centered = returns - returns.mean()
    m2 = float(np.mean(centered**2))
    skew = float(np.mean(centered**3)) / m2**1.5
    kurt = float(np.mean(centered**4)) / m2**2 - 3.0
    direct = deflated_sharpe_ratio(
        float(returns.mean() / returns.std(ddof=1)),
        500,
        10,
        skewness=skew,
        excess_kurtosis=kurt,
    )
    assert from_series.deflated_sharpe_ratio == direct.deflated_sharpe_ratio
    assert from_series.sharpe_ratio == direct.sharpe_ratio


def test_dsr_validation():
    with pytest.raises(ValueError, match="at least 2"):
        deflated_sharpe_ratio(0.06, 1, 10)
    with pytest.raises(ValueError, match="at least 1"):
        deflated_sharpe_ratio(0.06, 252, 0)
    with pytest.raises(ValueError, match="zero-variance"):
        deflated_sharpe_ratio_from_returns([0.01, 0.01, 0.01], 5)


def _clean_matrix(seed: int = 7) -> np.ndarray:
    """One strategy with a persistent edge; the rest are noise."""
    rng = np.random.default_rng(seed)
    matrix = rng.normal(0.0, 1.0, (800, 16))
    matrix[:, 0] += 0.5
    return matrix


def _noise_matrix(seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(0.0, 1.0, (800, 16))


def _overfit_matrix(seed: int = 1) -> np.ndarray:
    """Each strategy is good on exactly half the groups, bad on the rest.

    A strategy that looks best in-sample has its good groups inside the
    in-sample half by construction, so its out-of-sample groups are the
    bad ones: the IS-optimal strategy systematically ranks low OOS.
    """
    rng = np.random.default_rng(seed)
    matrix = rng.normal(0.0, 1.0, (800, 16))
    rows = np.array_split(np.arange(800), 8)
    for strategy in range(16):
        plus = rng.choice(8, size=4, replace=False)
        pattern = np.full(8, -1.0)
        pattern[plus] = 1.0
        for group in range(8):
            matrix[rows[group], strategy] += pattern[group]
    return matrix


def test_pbo_clean_persistent_edge_is_near_zero():
    result = probability_of_backtest_overfitting(
        _clean_matrix(), n_groups=8, max_combinations=None, seed=1
    )
    assert result.pbo < 0.1
    assert result.combinations == 70
    assert result.combinations_total == 70
    assert not result.combinations_sampled
    assert result.mean_relative_rank > 0.9


def test_pbo_pure_noise_is_near_one_half():
    # S=16 (12,870 splits): split-level ranks are correlated, so the
    # small-split estimate is noisy; the full split set is stable.
    result = probability_of_backtest_overfitting(
        _noise_matrix(), n_groups=16, max_combinations=None, seed=1
    )
    assert 0.35 < result.pbo < 0.65
    assert result.combinations == 12_870
    assert result.mean_relative_rank == pytest.approx(0.5, abs=0.1)


def test_pbo_sign_flipping_edges_is_near_one():
    result = probability_of_backtest_overfitting(
        _overfit_matrix(), n_groups=8, max_combinations=None, seed=1
    )
    assert result.pbo > 0.9
    assert result.mean_relative_rank < 0.2


def test_pbo_sampling_is_deterministic_and_capped():
    matrix = _noise_matrix()
    first = probability_of_backtest_overfitting(
        matrix, n_groups=16, max_combinations=500, seed=3
    )
    second = probability_of_backtest_overfitting(
        matrix, n_groups=16, max_combinations=500, seed=3
    )
    assert first == second
    assert first.combinations == 500
    assert first.combinations_sampled
    assert first.combinations_total == 12_870


def test_pbo_validation():
    matrix = _noise_matrix()
    with pytest.raises(ValueError, match="two-dimensional"):
        probability_of_backtest_overfitting([0.1, 0.2, 0.3])
    with pytest.raises(ValueError, match="at least two strategies"):
        probability_of_backtest_overfitting(np.zeros((10, 1)))
    with pytest.raises(ValueError, match="even integer"):
        probability_of_backtest_overfitting(matrix, n_groups=7)
    with pytest.raises(ValueError, match="finite"):
        bad = matrix.copy()
        bad[0, 0] = np.nan
        probability_of_backtest_overfitting(bad)
