import numpy as np
import pytest

from myquant.stats.lead_lag import lead_lag_scan
from myquant.synthetic import SyntheticScenario, make_transmission_panel


def test_scan_recovers_known_source_to_target_lag():
    lag = 5
    panel = make_transmission_panel(
        observations=3_000,
        lag_steps=lag,
        beta=0.9,
        noise_scale=0.2,
        seed=314,
        scenario=SyntheticScenario.SOURCE_LEADS_TARGET,
    )
    result = lead_lag_scan(
        panel["source_value"],
        panel["target_return"],
        lag_steps=(0, 2, 5, 8),
        minimum_observations=100,
    )
    by_lag = {item.lag_steps: item for item in result}

    assert by_lag[5].correlation is not None
    assert by_lag[5].correlation > 0.9
    assert by_lag[0].correlation is not None
    assert abs(by_lag[0].correlation) < 0.08
    assert by_lag[5].observations == 3_000 - 5


def test_scan_is_descriptive_and_detects_shared_factor_correlation():
    panel = make_transmission_panel(
        observations=2_000,
        seed=9,
        scenario=SyntheticScenario.COMMON_FACTOR,
    )
    result = lead_lag_scan(
        panel["source_value"],
        panel["target_return"],
        lag_steps=(0, 1, 2),
        minimum_observations=100,
    )
    assert result[0].correlation is not None
    assert result[0].correlation > 0.5
    # A contemporaneous association alone does not identify a causal arrow.


def test_scan_returns_undefined_when_sample_or_variance_is_insufficient():
    result = lead_lag_scan(
        [1.0, 2.0, 3.0, 4.0],
        [2.0, 1.0, 2.0, 1.0],
        lag_steps=(0, 2),
        minimum_observations=4,
    )
    assert result[0].correlation is not None
    assert result[1].observations == 2
    assert result[1].correlation is None

    constant = lead_lag_scan(
        [1.0] * 40,
        np.arange(40, dtype=float),
        lag_steps=(0,),
        minimum_observations=10,
    )
    assert constant[0].correlation is None


def test_scan_rejects_unsynchronized_or_invalid_inputs():
    with pytest.raises(ValueError, match="equal lengths"):
        lead_lag_scan([1.0, 2.0], [1.0], lag_steps=(0,))
    with pytest.raises(ValueError, match="finite"):
        lead_lag_scan([1.0, np.nan, 3.0], [1.0, 2.0, 3.0], lag_steps=(0,))
    with pytest.raises(ValueError, match="non-negative"):
        lead_lag_scan([1.0] * 40, [2.0] * 40, lag_steps=(-1,))
    with pytest.raises(ValueError, match="smaller than"):
        lead_lag_scan([1.0, 2.0], [2.0, 1.0], lag_steps=(2,))
    with pytest.raises(ValueError, match="unique"):
        lead_lag_scan([1.0] * 40, [2.0] * 40, lag_steps=(1, 1))


def test_scan_requires_a_minimum_sample_size():
    with pytest.raises(ValueError, match="at least 3"):
        lead_lag_scan([1.0] * 40, [2.0] * 40, lag_steps=(0,), minimum_observations=2)


def test_scan_accepts_numpy_integer_lags():
    panel = make_transmission_panel(
        observations=500,
        lag_steps=3,
        beta=0.8,
        noise_scale=0.2,
        seed=37,
    )
    result = lead_lag_scan(
        panel["source_value"],
        panel["target_return"],
        lag_steps=(np.int64(3),),
    )
    assert result[0].lag_steps == 3
    assert result[0].correlation is not None
    assert result[0].correlation > 0.9
