from datetime import UTC, datetime

import numpy as np
import pytest

from myquant.stats.bootstrap import block_bootstrap_mean_ci
from myquant.stats.hac import newey_west_hac
from myquant.synthetic import SyntheticScenario, make_transmission_panel


def test_synthetic_panel_is_reproducible_for_same_seed():
    first = make_transmission_panel(
        observations=500,
        seed=17,
        scenario=SyntheticScenario.SOURCE_LEADS_TARGET,
    )
    second = make_transmission_panel(
        observations=500,
        seed=17,
        scenario=SyntheticScenario.SOURCE_LEADS_TARGET,
    )
    assert first.equals(second)


def test_source_lead_scenario_places_target_effect_at_known_lag():
    lag = 4
    frame = make_transmission_panel(
        observations=2_000,
        lag_steps=lag,
        beta=1.0,
        noise_scale=0.2,
        seed=3,
        scenario=SyntheticScenario.SOURCE_LEADS_TARGET,
    )
    lagged_source = frame["source_value"].shift(lag)
    correlation = lagged_source.corr(frame["target_return"])
    assert correlation > 0.8
    assert np.isnan(lagged_source.iloc[:lag]).all()


def test_null_scenario_has_no_direct_source_effect():
    frame = make_transmission_panel(
        observations=3_000,
        seed=21,
        scenario=SyntheticScenario.NULL,
    )
    correlation = frame["source_value"].corr(frame["target_return"])
    assert abs(correlation) < 0.08
    assert frame["source_beta_truth"].eq(0).all()


def test_common_factor_scenario_exposes_latent_shared_driver():
    frame = make_transmission_panel(
        observations=2_000,
        seed=9,
        scenario=SyntheticScenario.COMMON_FACTOR,
    )
    assert frame["common_factor_truth"].std() > 0
    assert frame["source_value"].corr(frame["common_factor_truth"]) > 0.5
    assert frame["target_return"].corr(frame["common_factor_truth"]) > 0.5
    assert frame["source_beta_truth"].eq(0).all()


def test_common_factor_scenario_starts_from_stationary_distribution():
    frame = make_transmission_panel(
        observations=2_000,
        seed=9,
        scenario=SyntheticScenario.COMMON_FACTOR,
    )
    # The stationary variance of the AR(1) factor (phi=0.85, unit
    # innovations) is 1/(1-0.85^2) ~= 3.60. With a zero start the opening
    # rows would be strongly under-dispersed.
    opening_variance = frame["common_factor_truth"].iloc[:100].var()
    assert 1.5 < opening_variance < 6.5
    assert frame["common_factor_truth"].iloc[0] != 0.0


def test_regime_shift_turns_off_direct_effect_mid_sample():
    frame = make_transmission_panel(
        observations=4_000,
        lag_steps=2,
        beta=1.0,
        noise_scale=0.3,
        seed=12,
        scenario=SyntheticScenario.REGIME_SHIFT,
    )
    midpoint = len(frame) // 2
    first = frame.iloc[:midpoint]
    second = frame.iloc[midpoint:]
    first_corr = first["source_value"].shift(2).corr(first["target_return"])
    second_corr = second["source_value"].shift(2).corr(second["target_return"])
    assert first_corr > 0.7
    assert abs(second_corr) < 0.08


def test_synthetic_generator_rejects_invalid_sizes_and_naive_time():
    with pytest.raises(ValueError, match="at least 100"):
        make_transmission_panel(observations=50)
    with pytest.raises(ValueError, match="positive"):
        make_transmission_panel(observations=200, lag_steps=0)
    with pytest.raises(ValueError, match="timezone-aware"):
        make_transmission_panel(
            observations=200,
            start_time=datetime(2020, 1, 1),
        )


def test_synthetic_panel_uses_utc_aware_timestamps():
    frame = make_transmission_panel(
        observations=100,
        start_time=datetime(2024, 1, 1, tzinfo=UTC),
        frequency="1h",
    )
    assert str(frame["timestamp"].dt.tz) == "UTC"


def test_heavy_tail_missing_scenario_is_reproducible():
    first = make_transmission_panel(
        observations=500,
        seed=17,
        scenario=SyntheticScenario.HEAVY_TAIL_MISSING,
    )
    second = make_transmission_panel(
        observations=500,
        seed=17,
        scenario=SyntheticScenario.HEAVY_TAIL_MISSING,
    )
    assert first.equals(second)


def _excess_kurtosis(values: np.ndarray) -> float:
    clean = values[~np.isnan(values)]
    centered = clean - clean.mean()
    return float(np.mean(centered**4) / np.mean(centered**2) ** 2 - 3.0)


def test_heavy_tail_missing_scenario_has_heavy_tails_and_random_gaps():
    frame = make_transmission_panel(
        observations=3_000,
        seed=42,
        scenario=SyntheticScenario.HEAVY_TAIL_MISSING,
    )
    source = frame["source_value"].to_numpy(dtype=float)
    target = frame["target_return"].to_numpy(dtype=float)

    # Gaussian noise has excess kurtosis ~0 and P(|x| > 3) ~= 0.0027; the
    # standardized t(3) noise here is far heavier on both measures.
    assert _excess_kurtosis(source) > 1.0
    assert float(np.nanmean(np.abs(source) > 3)) > 0.005
    # About 5% of each observed series is missing (binomial std ~0.004).
    assert 0.02 < float(np.isnan(source).mean()) < 0.08
    assert 0.02 < float(np.isnan(target).mean()) < 0.08
    # Ground truth survives masking: the effect is still declared per row.
    assert frame["source_beta_truth"].eq(0.8).all()


def test_heavy_tail_missing_scenario_keeps_lead_lag_effect_after_dropna():
    frame = make_transmission_panel(
        observations=2_000,
        lag_steps=3,
        beta=1.0,
        noise_scale=0.2,
        seed=3,
        scenario=SyntheticScenario.HEAVY_TAIL_MISSING,
    )
    paired = frame[["source_value", "target_return"]].copy()
    paired["source_value"] = paired["source_value"].shift(3)
    paired = paired.dropna()
    correlation = paired["source_value"].corr(paired["target_return"])
    assert correlation > 0.7


def test_heavy_tail_missing_scenario_rejects_bad_stress_settings():
    with pytest.raises(ValueError, match="missing_rate"):
        make_transmission_panel(
            observations=200,
            scenario=SyntheticScenario.HEAVY_TAIL_MISSING,
            missing_rate=1.0,
        )
    with pytest.raises(ValueError, match="missing_rate"):
        make_transmission_panel(
            observations=200,
            scenario=SyntheticScenario.HEAVY_TAIL_MISSING,
            missing_rate=-0.1,
        )
    with pytest.raises(ValueError, match="tail_degrees_of_freedom"):
        make_transmission_panel(
            observations=200,
            scenario=SyntheticScenario.HEAVY_TAIL_MISSING,
            tail_degrees_of_freedom=2.0,
        )


def test_bootstrap_interval_stays_calibrated_under_heavy_tails():
    # Measured during development: 38/40 intervals cover the true mean 0
    # (0.95), so the block bootstrap holds up under t(3) tails. The band
    # allows Monte Carlo noise (std ~= 0.034 over 40 repetitions) while
    # catching gross miscalibration.
    covered = 0
    repetitions = 40
    for repetition in range(repetitions):
        frame = make_transmission_panel(
            observations=3_000,
            seed=2000 + repetition,
            scenario=SyntheticScenario.HEAVY_TAIL_MISSING,
        )
        values = frame["target_return"].dropna().to_numpy(dtype=float)
        interval = block_bootstrap_mean_ci(
            values,
            block_length=5,
            resamples=500,
            seed=repetition,
        )
        if interval.lower_bound <= 0.0 <= interval.upper_bound:
            covered += 1
    assert 0.85 <= covered / repetitions <= 1.0


def test_hac_recovers_lead_lag_slope_under_heavy_tails_and_gaps():
    frame = make_transmission_panel(
        observations=3_000,
        lag_steps=3,
        beta=0.8,
        seed=11,
        scenario=SyntheticScenario.HEAVY_TAIL_MISSING,
    )
    paired = frame[["source_value", "target_return"]].copy()
    paired["source_value"] = paired["source_value"].shift(3)
    paired = paired.dropna()
    result = newey_west_hac(
        paired["target_return"].to_numpy(dtype=float),
        {"lagged_source": paired["source_value"].to_numpy(dtype=float)},
        max_lag=5,
    )
    slope = result.coefficients[1]
    assert slope.estimate == pytest.approx(0.8, abs=0.1)
    assert slope.standard_error is not None
    assert slope.standard_error > 0.0
    assert slope.p_value is not None
    assert slope.p_value < 0.01
