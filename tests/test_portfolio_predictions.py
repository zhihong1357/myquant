"""Tests for the unified prediction contract (offline)."""

from datetime import UTC, datetime, timedelta

import pytest

from myquant.portfolio.predictions import (
    Prediction,
    PredictionTarget,
    available_predictions,
    horizon_label,
    is_available,
    make_lag_return_fixture,
    require_available,
)

T0 = datetime(2026, 11, 18, 16, 0, tzinfo=UTC)


def _prediction(**overrides):
    fields = {
        "prediction_id": "p1",
        "instrument_id": "crypto:btc-usdt-perp",
        "target": PredictionTarget.LOG_RETURN,
        "horizon": timedelta(days=1),
        "event_time": T0,
        "available_at": T0,
        "value": 0.01,
        "model_id": "m1",
        "model_version": "1",
        "feature_version": "f1",
    }
    fields.update(overrides)
    return Prediction(**fields)


def test_valid_prediction_and_target_time():
    prediction = _prediction()
    assert prediction.target_time == T0 + timedelta(days=1)
    assert prediction.value == 0.01


def test_available_at_cannot_precede_event_time():
    with pytest.raises(ValueError, match="available_at cannot precede"):
        _prediction(available_at=T0 - timedelta(seconds=1))


def test_horizon_must_be_positive():
    with pytest.raises(ValueError, match="horizon must be positive"):
        _prediction(horizon=timedelta(0))
    with pytest.raises(ValueError, match="horizon must be positive"):
        _prediction(horizon=timedelta(days=-1))


def test_direction_value_must_be_minus_one_zero_or_one():
    for value in (-1.0, 0.0, 1.0):
        assert _prediction(target=PredictionTarget.DIRECTION, value=value).value == value
    with pytest.raises(ValueError, match="direction predictions"):
        _prediction(target=PredictionTarget.DIRECTION, value=0.5)


def test_abs_return_and_volatility_must_be_non_negative():
    _prediction(target=PredictionTarget.ABS_LOG_RETURN, value=0.0)
    _prediction(target=PredictionTarget.REALIZED_VOLATILITY, value=0.02)
    with pytest.raises(ValueError, match="must be non-negative"):
        _prediction(target=PredictionTarget.ABS_LOG_RETURN, value=-0.01)
    with pytest.raises(ValueError, match="must be non-negative"):
        _prediction(target=PredictionTarget.REALIZED_VOLATILITY, value=-0.01)


def test_at_most_one_uncertainty_representation():
    _prediction(uncertainty_std=0.02)
    _prediction(uncertainty_interval=(-0.01, 0.03))
    with pytest.raises(ValueError, match="at most one"):
        _prediction(uncertainty_std=0.02, uncertainty_interval=(-0.01, 0.03))
    with pytest.raises(ValueError, match="lower <= upper"):
        _prediction(uncertainty_interval=(0.03, -0.01))


def test_horizon_label():
    assert horizon_label(timedelta(hours=1)) == "1H"
    assert horizon_label(timedelta(days=1)) == "1D"
    assert horizon_label(timedelta(days=7)) == "7D"
    assert horizon_label(timedelta(minutes=5)) == "5m"
    assert horizon_label(timedelta(hours=4)) == "4H"


def test_pit_availability_and_strict_query():
    prediction = _prediction(available_at=T0 + timedelta(hours=2))
    assert is_available(prediction, T0 + timedelta(hours=2)) is True
    assert is_available(prediction, T0 + timedelta(hours=1)) is False
    # The strict query refuses a prediction that is not yet available.
    with pytest.raises(ValueError, match="not available at"):
        require_available(prediction, T0 + timedelta(hours=1))
    assert require_available(prediction, T0 + timedelta(hours=2)) is prediction


def test_available_predictions_filters_by_decision_time():
    early = _prediction(prediction_id="early", available_at=T0)
    late = _prediction(prediction_id="late", available_at=T0 + timedelta(days=1))
    assert available_predictions((early, late), T0) == (early,)
    assert available_predictions((early, late), T0 + timedelta(days=1)) == (
        early,
        late,
    )


def test_lag_return_fixture():
    bars = (
        (datetime(2026, 11, 16, 16, 0, tzinfo=UTC), 0.01),
        (datetime(2026, 11, 17, 16, 0, tzinfo=UTC), -0.02),
        (datetime(2026, 11, 18, 16, 0, tzinfo=UTC), 0.005),
    )
    predictions = make_lag_return_fixture(
        bars,
        instrument_id="crypto:btc-usdt-perp",
        horizon=timedelta(days=1),
    )
    # One prediction per bar except the last; value = that bar's return.
    assert len(predictions) == 2
    assert predictions[0].value == 0.01
    assert predictions[0].event_time == datetime(2026, 11, 16, 16, 0, tzinfo=UTC)
    assert predictions[0].available_at == predictions[0].event_time
    assert predictions[0].target_time == datetime(2026, 11, 17, 16, 0, tzinfo=UTC)
    assert predictions[1].value == -0.02
    assert predictions[0].model_id == "fixture-lag-return"


def test_lag_return_fixture_abs_target_and_rejections():
    bars = (
        (datetime(2026, 11, 16, 16, 0, tzinfo=UTC), -0.02),
        (datetime(2026, 11, 17, 16, 0, tzinfo=UTC), 0.005),
    )
    predictions = make_lag_return_fixture(
        bars,
        instrument_id="crypto:btc-usdt-perp",
        horizon=timedelta(days=1),
        target=PredictionTarget.ABS_LOG_RETURN,
    )
    assert predictions[0].value == 0.02
    with pytest.raises(ValueError, match="only supports log_return"):
        make_lag_return_fixture(
            bars,
            instrument_id="crypto:btc-usdt-perp",
            horizon=timedelta(days=1),
            target=PredictionTarget.DIRECTION,
        )
    with pytest.raises(ValueError, match="must be finite"):
        make_lag_return_fixture(
            (
                (datetime(2026, 11, 16, 16, 0, tzinfo=UTC), float("nan")),
                (datetime(2026, 11, 17, 16, 0, tzinfo=UTC), 0.005),
            ),
            instrument_id="crypto:btc-usdt-perp",
            horizon=timedelta(days=1),
        )
