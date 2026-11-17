import numpy as np
import pytest

from myquant.stats.lead_lag import partial_lead_lag
from myquant.stats.regression import ols_fit
from myquant.synthetic import SyntheticScenario, make_transmission_panel


def test_partial_lead_lag_recovers_a_direct_source_effect():
    lag = 4
    panel = make_transmission_panel(
        observations=3_000,
        lag_steps=lag,
        beta=0.8,
        noise_scale=0.2,
        seed=72,
        scenario=SyntheticScenario.SOURCE_LEADS_TARGET,
    )

    result = partial_lead_lag(
        panel["source_value"],
        panel["target_return"],
        lag_steps=lag,
        max_hac_lag=8,
    )

    assert result.source_effect.estimate == pytest.approx(0.8, abs=0.04)
    assert result.source_effect.p_value is not None
    assert result.source_effect.p_value < 1e-8
    assert result.incremental_r_squared > 0.8
    assert result.partial_r_squared is not None
    assert result.partial_r_squared > 0.8
    assert result.observations == 3_000 - lag


def test_common_factor_control_removes_spurious_source_lead():
    lag = 3
    panel = make_transmission_panel(
        observations=4_000,
        lag_steps=lag,
        seed=19,
        scenario=SyntheticScenario.COMMON_FACTOR,
    )

    # The latent factor is exposed here only as a synthetic ground-truth oracle.
    # A live study must use a point-in-time observable proxy, not simulator truth.
    result = partial_lead_lag(
        panel["source_value"],
        panel["target_return"],
        lag_steps=lag,
        common_factors={"known_common_driver": panel["common_factor_truth"]},
        max_hac_lag=10,
    )

    assert abs(result.source_effect.estimate) < 0.08
    assert result.source_effect.p_value is not None
    assert result.source_effect.p_value > 0.05
    assert result.partial_r_squared is not None
    assert result.partial_r_squared < 0.01


def test_null_simulation_does_not_show_a_large_incremental_effect():
    panel = make_transmission_panel(
        observations=2_500,
        lag_steps=5,
        seed=101,
        scenario=SyntheticScenario.NULL,
    )

    result = partial_lead_lag(
        panel["source_value"],
        panel["target_return"],
        lag_steps=5,
        max_hac_lag=8,
    )

    assert abs(result.source_effect.estimate) < 0.08
    assert result.source_effect.p_value is not None
    assert result.source_effect.p_value > 0.05


def test_regime_shift_is_visible_when_effect_is_estimated_by_subperiod():
    lag = 4
    split = 2_000
    panel = make_transmission_panel(
        observations=4_000,
        lag_steps=lag,
        beta=0.9,
        noise_scale=0.2,
        seed=28,
        scenario=SyntheticScenario.REGIME_SHIFT,
    )
    source = panel["source_value"].to_numpy()
    target = panel["target_return"].to_numpy()

    first_regime = ols_fit(
        target[lag:split],
        {"source": source[: split - lag]},
    )
    second_regime = ols_fit(
        target[split:],
        {"source": source[split - lag : 4_000 - lag]},
    )

    assert first_regime.coefficients[1] == pytest.approx(0.9, abs=0.04)
    assert abs(second_regime.coefficients[1]) < 0.03


def test_partial_lead_lag_rejects_future_or_misaligned_inputs():
    source = np.arange(100, dtype=float)
    target = np.arange(100, dtype=float)
    with pytest.raises(ValueError, match="positive integer"):
        partial_lead_lag(source, target, lag_steps=0, max_hac_lag=5)
    with pytest.raises(ValueError, match="equal lengths"):
        partial_lead_lag(source, target[:-1], lag_steps=2, max_hac_lag=5)
    with pytest.raises(ValueError, match="reserved"):
        partial_lead_lag(
            source,
            target,
            lag_steps=2,
            common_factors={"source": source},
            max_hac_lag=5,
        )
    with pytest.raises(ValueError, match="finite"):
        bad_factor = source.copy()
        bad_factor[5] = np.nan
        partial_lead_lag(
            source,
            target,
            lag_steps=2,
            common_factors={"factor": bad_factor},
            max_hac_lag=5,
        )
