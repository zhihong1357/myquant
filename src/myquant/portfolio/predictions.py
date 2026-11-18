"""Unified prediction contract across horizons (Stage 5a).

One typed contract for any forecast a future strategy or study wants
to register, score or consume — across instruments, horizons and
targets. The contract carries no model and produces no prediction:
it is the envelope a prediction travels in, with the point-in-time
(PIT) semantics the architecture requires.

Definitions:

- ``event_time`` is the start of the forecast window: the time the
  prediction is *about* (the last data time the forecast conditions
  on). ``target_time`` (derived) is ``event_time + horizon``: the
  end of the window the target is measured over.
- ``available_at`` is when the prediction becomes usable. It must be
  at or after ``event_time``: a prediction cannot be usable before
  the data it conditions on exists. PIT eligibility is governed by
  ``available_at <= decision_time`` — a prediction is usable at a
  decision time only if it was available then. See
  :func:`available_predictions` and :func:`require_available`.
- ``target`` is what is predicted, with an explicit definition per
  value (see :class:`PredictionTarget`).
- ``horizon`` is the forecast window as a :class:`timedelta`
  (positive). Common horizons render as ``1H`` / ``1D`` / ``7D`` via
  :func:`horizon_label`.
- ``value`` is the point prediction. Its allowed range depends on
  the target (see :class:`PredictionTarget`): a direction must be
  -1, 0 or +1; an absolute return or a volatility must be
  non-negative.
- Uncertainty is optional and explicit: either a standard deviation
  (``uncertainty_std``, the standard deviation of the predicted
  value, >= 0) or an interval (``uncertainty_interval``, a
  ``(lower, upper)`` pair with lower <= upper). At most one may be
  set; neither is a confidence level unless the caller says so.
- ``model_id`` / ``model_version`` / ``feature_version`` identify
  the producer. They are labels, not quality claims.

The fixture generator (:func:`make_lag_return_fixture`) exists only
so tests and framework validation have mechanical predictions to
work with. It predicts "next period's return equals last period's
return" — a naive fixture, not a strategy and not an alpha claim.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from math import isfinite

from pydantic import Field, model_validator

from myquant.contracts import StrictContract, require_utc


class PredictionTarget(StrEnum):
    """What a prediction predicts. Each value has a fixed definition.

    LOG_RETURN: the log return of the instrument's price over
        [event_time, event_time + horizon].
    ABS_LOG_RETURN: the absolute value of that log return (>= 0).
    DIRECTION: the sign of that log return: -1 (down), 0 (flat) or
        +1 (up). Flat means exactly zero; a thresholded direction is
        a different target and must be defined as one.
    REALIZED_VOLATILITY: the realized volatility (standard deviation
        of log returns, per horizon unit) over the window (>= 0).
        The annualization, if any, is the caller's to state.
    """

    LOG_RETURN = "log_return"
    ABS_LOG_RETURN = "abs_log_return"
    DIRECTION = "direction"
    REALIZED_VOLATILITY = "realized_volatility"


class Prediction(StrictContract):
    """One forecast under the unified contract."""

    prediction_id: str = Field(min_length=1)
    instrument_id: str = Field(min_length=1)
    target: PredictionTarget
    horizon: timedelta
    event_time: datetime
    available_at: datetime
    value: float = Field(allow_inf_nan=False)
    uncertainty_std: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    uncertainty_interval: tuple[float, float] | None = Field(default=None)
    model_id: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    feature_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_prediction(self) -> Prediction:
        event = require_utc(self.event_time)
        available = require_utc(self.available_at)
        if self.horizon <= timedelta(0):
            raise ValueError("horizon must be positive")
        if available < event:
            raise ValueError("available_at cannot precede event_time")
        if self.target is PredictionTarget.DIRECTION and self.value not in (-1.0, 0.0, 1.0):
            raise ValueError("direction predictions must be -1, 0 or +1")
        if self.target in (
            PredictionTarget.ABS_LOG_RETURN,
            PredictionTarget.REALIZED_VOLATILITY,
        ) and self.value < 0:
            raise ValueError(f"{self.target.value} predictions must be non-negative")
        if self.uncertainty_std is not None and self.uncertainty_interval is not None:
            raise ValueError(
                "at most one of uncertainty_std and uncertainty_interval may be set"
            )
        if self.uncertainty_interval is not None:
            lower, upper = self.uncertainty_interval
            if not (isfinite(lower) and isfinite(upper)):
                raise ValueError("uncertainty_interval must be finite")
            if not (lower <= upper):
                raise ValueError("uncertainty_interval must satisfy lower <= upper")
        object.__setattr__(self, "event_time", event)
        object.__setattr__(self, "available_at", available)
        return self

    @property
    def target_time(self) -> datetime:
        """End of the forecast window: event_time + horizon."""
        return self.event_time + self.horizon


def horizon_label(horizon: timedelta) -> str:
    """Short label for common horizons (1H, 1D, 7D); else ISO-ish text."""
    seconds = horizon.total_seconds()
    if seconds == int(seconds) and int(seconds) % 86_400 == 0:
        return f"{int(seconds) // 86_400}D"
    if seconds == int(seconds) and int(seconds) % 3_600 == 0:
        return f"{int(seconds) // 3_600}H"
    if seconds == int(seconds) and int(seconds) % 60 == 0:
        return f"{int(seconds) // 60}m"
    return f"{seconds}s"


def is_available(prediction: Prediction, decision_time: datetime) -> bool:
    """Whether a prediction was knowable at a decision timestamp."""
    return prediction.available_at <= require_utc(decision_time)


def require_available(prediction: Prediction, decision_time: datetime) -> Prediction:
    """Return the prediction if available at decision_time, else raise.

    The strict query: a consumer that must not see the future calls
    this and gets an error instead of a leaked prediction.
    """
    decision = require_utc(decision_time)
    if prediction.available_at > decision:
        raise ValueError(
            f"prediction {prediction.prediction_id} is not available at "
            f"{decision.isoformat()} (available_at "
            f"{prediction.available_at.isoformat()})"
        )
    return prediction


def available_predictions(
    predictions: tuple[Prediction, ...] | list[Prediction],
    decision_time: datetime,
) -> tuple[Prediction, ...]:
    """The subset of predictions available at a decision timestamp."""
    decision = require_utc(decision_time)
    return tuple(
        prediction for prediction in predictions if prediction.available_at <= decision
    )


def make_lag_return_fixture(
    returns: tuple[tuple[datetime, float], ...] | list[tuple[datetime, float]],
    *,
    instrument_id: str,
    horizon: timedelta,
    target: PredictionTarget = PredictionTarget.LOG_RETURN,
    model_id: str = "fixture-lag-return",
    model_version: str = "1",
    feature_version: str = "fixture-1",
) -> tuple[Prediction, ...]:
    """Mechanical fixture predictions: next return equals last return.

    Takes ``(bar_close_time, log_return)`` pairs in ascending time
    order and emits one prediction per bar (except the last): the
    prediction at bar ``i``'s close forecasts bar ``i + 1``'s return
    as equal to bar ``i``'s return. ``event_time`` and
    ``available_at`` are both the bar close: the fixture is knowable
    at the close, and it conditions only on data available then.

    This is a test/validation fixture, not a strategy: it encodes no
    market view and its accuracy (or lack of it) says nothing about
    any real model. ``target`` may be LOG_RETURN or ABS_LOG_RETURN;
    other targets are rejected rather than silently reinterpreted.
    """
    if target not in (PredictionTarget.LOG_RETURN, PredictionTarget.ABS_LOG_RETURN):
        raise ValueError(
            "the lag-return fixture only supports log_return and "
            f"abs_log_return targets, not {target!r}"
        )
    ordered = sorted(returns, key=lambda item: item[0])
    for _, value in ordered:
        if not isfinite(value):
            raise ValueError("fixture returns must be finite")
    predictions: list[Prediction] = []
    for index in range(len(ordered) - 1):
        close_time, last_return = ordered[index]
        value = last_return if target is PredictionTarget.LOG_RETURN else abs(last_return)
        predictions.append(
            Prediction(
                prediction_id=f"{model_id}-{index}",
                instrument_id=instrument_id,
                target=target,
                horizon=horizon,
                event_time=close_time,
                available_at=close_time,
                value=value,
                model_id=model_id,
                model_version=model_version,
                feature_version=feature_version,
            )
        )
    return tuple(predictions)
