from datetime import UTC, datetime

import numpy as np
import pytest

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
