"""Tests for forward shadow evaluation (offline, deterministic)."""

import math
from datetime import UTC, datetime, timedelta

import pytest

from myquant.portfolio.predictions import (
    Prediction,
    PredictionTarget,
    make_lag_return_fixture,
)
from myquant.portfolio.shadow import (
    IN_FIT_WINDOW,
    NOT_YET_DUE,
    OUTCOME_MISSING,
    score_predictions,
    shadow_ledger_json,
)

T0 = datetime(2026, 1, 1, 16, 0, tzinfo=UTC)
DAY = timedelta(days=1)
INST = "synthetic:test"


def _prediction(index, value, *, target=PredictionTarget.LOG_RETURN, event_time=None):
    when = T0 + index * DAY if event_time is None else event_time
    return Prediction(
        prediction_id=f"p{index}",
        instrument_id=INST,
        target=target,
        horizon=DAY,
        event_time=when,
        available_at=when,
        value=value,
        model_id="m1",
        model_version="1",
        feature_version="f1",
    )


def _provider(outcomes):
    """Outcome provider keyed by (instrument, event_time)."""

    def provider(prediction):
        return outcomes.get((prediction.instrument_id, prediction.event_time))

    return provider


def _outcomes(values):
    return {(INST, T0 + i * DAY): v for i, v in enumerate(values)}


def test_not_yet_due_is_unscored_and_provider_not_queried():
    queried = []
    outcomes = _outcomes([0.01, 0.02, 0.03])

    def provider(prediction):
        queried.append(prediction.prediction_id)
        return outcomes.get((prediction.instrument_id, prediction.event_time))

    predictions = [_prediction(i, 0.0) for i in range(3)]
    # Scored at T0 + 2 days: only the first prediction's window closed.
    evaluation = score_predictions(
        predictions, provider, scored_at=T0 + 2 * DAY
    )
    assert evaluation.n_scored == 1
    assert evaluation.n_unscored == 2
    assert evaluation.unscored_counts == {NOT_YET_DUE: 2}
    # The provider is only queried for due predictions.
    assert queried == ["p0"]
    assert evaluation.predictions[0].scored is True
    assert evaluation.predictions[1].unscored_reason == NOT_YET_DUE


def test_scoring_exactly_at_target_time_is_refused():
    outcomes = _outcomes([0.01])
    evaluation = score_predictions(
        [_prediction(0, 0.0)], _provider(outcomes), scored_at=T0 + DAY
    )
    assert evaluation.n_scored == 0
    assert evaluation.predictions[0].unscored_reason == NOT_YET_DUE


def test_missing_outcome_is_unscored_not_zero():
    outcomes = _outcomes([0.01])  # only the first outcome exists
    predictions = [_prediction(0, 0.0), _prediction(1, 0.0)]
    evaluation = score_predictions(
        predictions, _provider(outcomes), scored_at=T0 + 10 * DAY
    )
    assert evaluation.n_scored == 1
    assert evaluation.predictions[1].unscored_reason == OUTCOME_MISSING
    assert evaluation.predictions[1].error is None
    metric = evaluation.metrics[0]
    assert metric.n_scored == 1
    assert metric.mse == pytest.approx(0.01**2)


def test_fit_window_refuses_in_sample_predictions():
    outcomes = _outcomes([0.01, 0.02, 0.03, 0.04])
    predictions = [_prediction(i, 0.0) for i in range(4)]
    evaluation = score_predictions(
        predictions,
        _provider(outcomes),
        scored_at=T0 + 10 * DAY,
        fit_window=(T0 + DAY, T0 + 3 * DAY),
    )
    # Predictions at T0+1d and T0+2d are inside [start, end); T0+3d is out.
    reasons = [r.unscored_reason for r in evaluation.predictions]
    assert reasons == [None, IN_FIT_WINDOW, IN_FIT_WINDOW, None]
    assert evaluation.n_scored == 2
    assert evaluation.unscored_counts == {IN_FIT_WINDOW: 2}


def test_fit_window_must_be_nonempty():
    with pytest.raises(ValueError, match="fit_window end must be after"):
        score_predictions(
            [_prediction(0, 0.0)],
            _provider(_outcomes([0.01])),
            scored_at=T0 + 10 * DAY,
            fit_window=(T0 + DAY, T0 + DAY),
        )


def test_log_return_metrics_hand_computed():
    # predicted: [0.01, -0.02, 0.03]; outcome: [0.02, -0.01, 0.01]
    # errors: [-0.01, -0.01, 0.02]
    predictions = [_prediction(0, 0.01), _prediction(1, -0.02), _prediction(2, 0.03)]
    outcomes = _outcomes([0.02, -0.01, 0.01])
    evaluation = score_predictions(
        predictions, _provider(outcomes), scored_at=T0 + 10 * DAY
    )
    metric = evaluation.metrics[0]
    assert metric.n_scored == 3
    assert metric.mse == pytest.approx((0.01**2 + 0.01**2 + 0.02**2) / 3)
    assert metric.mae == pytest.approx((0.01 + 0.01 + 0.02) / 3)
    assert metric.bias == pytest.approx((-0.01 - 0.01 + 0.02) / 3)
    # Signs: (+,+), (-,-), (+,+) -> hit rate 1.0.
    assert metric.hit_rate == pytest.approx(1.0)
    # Pearson correlation, hand-computed via the definition.
    px = [0.01, -0.02, 0.03]
    ox = [0.02, -0.01, 0.01]
    mx = sum(px) / 3
    mo = sum(ox) / 3
    cov = sum((a - mx) * (b - mo) for a, b in zip(px, ox, strict=True))
    var_x = sum((a - mx) ** 2 for a in px)
    var_o = sum((b - mo) ** 2 for b in ox)
    assert metric.correlation == pytest.approx(cov / math.sqrt(var_x * var_o))
    # Zero baseline MSE = mean(outcome^2) = (0.0004 + 0.0001 + 0.0001)/3.
    assert metric.zero_baseline_mse == pytest.approx(0.0006 / 3)
    assert metric.skill_vs_zero == pytest.approx(1 - metric.mse / metric.zero_baseline_mse)


def test_negative_skill_when_worse_than_zero():
    # A wild prediction: error 0.10 against outcome 0.01.
    predictions = [_prediction(0, 0.11)]
    outcomes = _outcomes([0.01])
    evaluation = score_predictions(
        predictions, _provider(outcomes), scored_at=T0 + 10 * DAY
    )
    metric = evaluation.metrics[0]
    assert metric.mse == pytest.approx(0.01)
    assert metric.zero_baseline_mse == pytest.approx(0.0001)
    assert metric.skill_vs_zero == pytest.approx(1 - 0.01 / 0.0001)
    assert metric.skill_vs_zero < 0


def test_perfect_oracle_scores_mse_zero_skill_one():
    values = [0.01, -0.02, 0.005, 0.03]
    predictions = [_prediction(i, v) for i, v in enumerate(values)]
    evaluation = score_predictions(
        predictions, _provider(_outcomes(values)), scored_at=T0 + 10 * DAY
    )
    metric = evaluation.metrics[0]
    assert metric.mse == 0.0
    assert metric.mae == 0.0
    assert metric.bias == 0.0
    assert metric.skill_vs_zero == pytest.approx(1.0)
    assert metric.correlation == pytest.approx(1.0)
    assert metric.hit_rate == pytest.approx(1.0)


def test_skill_undefined_when_all_outcomes_are_zero():
    predictions = [_prediction(0, 0.0), _prediction(1, 0.0)]
    outcomes = _outcomes([0.0, 0.0])
    evaluation = score_predictions(
        predictions, _provider(outcomes), scored_at=T0 + 10 * DAY
    )
    metric = evaluation.metrics[0]
    assert metric.zero_baseline_mse == 0.0
    assert metric.skill_vs_zero is None


def test_direction_metrics_and_confusion_counts():
    # predicted: [+1, +1, -1, -1, 0]; outcome: [+1, -1, -1, +1, 0]
    # TP=1 (idx 0), FP=1 (idx 1), TN=1 (idx 2), FN=1 (idx 3), zeros: pred 1, out 1.
    predictions = [
        _prediction(i, v, target=PredictionTarget.DIRECTION)
        for i, v in enumerate([1.0, 1.0, -1.0, -1.0, 0.0])
    ]
    outcomes = _outcomes([1.0, -1.0, -1.0, 1.0, 0.0])
    evaluation = score_predictions(
        predictions, _provider(outcomes), scored_at=T0 + 10 * DAY
    )
    metric = evaluation.metrics[0]
    assert metric.target is PredictionTarget.DIRECTION
    assert metric.accuracy == pytest.approx(3 / 5)
    assert metric.confusion is not None
    assert metric.confusion.true_positive == 1
    assert metric.confusion.false_positive == 1
    assert metric.confusion.true_negative == 1
    assert metric.confusion.false_negative == 1
    assert metric.confusion.zeros_predicted == 1
    assert metric.confusion.zeros_outcome == 1
    # MSE on the -1/0/+1 scale: errors [0, 2, 0, -2, 0] -> (0+4+0+4+0)/5.
    assert metric.mse == pytest.approx(8 / 5)
    assert metric.correlation is None
    assert metric.hit_rate is None


def test_abs_log_return_metrics():
    predictions = [
        _prediction(i, v, target=PredictionTarget.ABS_LOG_RETURN)
        for i, v in enumerate([0.01, 0.02])
    ]
    outcomes = _outcomes([0.015, 0.01])
    evaluation = score_predictions(
        predictions, _provider(outcomes), scored_at=T0 + 10 * DAY
    )
    metric = evaluation.metrics[0]
    assert metric.mse == pytest.approx((0.005**2 + 0.01**2) / 2)
    assert metric.mae == pytest.approx((0.005 + 0.01) / 2)
    assert metric.bias == pytest.approx((-0.005 + 0.01) / 2)
    assert metric.correlation is None
    assert metric.hit_rate is None
    assert metric.accuracy is None
    assert metric.confusion is None


def test_named_baseline_skill_on_matched_pairs():
    # Stream: predictions [0.01, -0.02, 0.03]; outcomes [0.02, -0.01, 0.01].
    predictions = [_prediction(0, 0.01), _prediction(1, -0.02), _prediction(2, 0.03)]
    outcomes = _outcomes([0.02, -0.01, 0.01])
    # Baseline "lag": predictions [0.0, 0.02, -0.01] at the same event times.
    lag = [
        Prediction(
            prediction_id=f"lag{i}",
            instrument_id=INST,
            target=PredictionTarget.LOG_RETURN,
            horizon=DAY,
            event_time=T0 + i * DAY,
            available_at=T0 + i * DAY,
            value=v,
            model_id="fixture-lag-return",
            model_version="1",
            feature_version="fixture-1",
        )
        for i, v in enumerate([0.0, 0.02, -0.01])
    ]
    evaluation = score_predictions(
        predictions,
        _provider(outcomes),
        scored_at=T0 + 10 * DAY,
        baselines={"lag": lag},
    )
    metric = evaluation.metrics[0]
    assert len(metric.baselines) == 1
    entry = metric.baselines[0]
    assert entry.name == "lag"
    assert entry.matched_pairs == 3
    # Baseline errors: [-0.02, 0.03, -0.02] -> MSE (0.0004+0.0009+0.0004)/3.
    assert entry.baseline_mse == pytest.approx(0.0017 / 3)
    # Stream MSE on the same pairs: (0.0001+0.0001+0.0004)/3.
    assert entry.skill == pytest.approx(1 - (0.0006 / 3) / (0.0017 / 3))


def test_baseline_with_no_matches_is_reported_not_hidden():
    predictions = [_prediction(0, 0.01)]
    outcomes = _outcomes([0.02])
    # Baseline prediction at a different event time: no match.
    lag = [_prediction(5, 0.0)]
    evaluation = score_predictions(
        predictions,
        _provider(outcomes),
        scored_at=T0 + 10 * DAY,
        baselines={"lag": lag},
    )
    entry = evaluation.metrics[0].baselines[0]
    assert entry.matched_pairs == 0
    assert entry.baseline_mse is None
    assert entry.skill is None


def test_lag_fixture_baseline_via_make_lag_return_fixture():
    # Returns at bar closes; the fixture predicts next = last.
    returns = [(T0 + i * DAY, v) for i, v in enumerate([0.01, -0.02, 0.03, 0.01])]
    fixture = make_lag_return_fixture(returns, instrument_id=INST, horizon=DAY)
    assert len(fixture) == 3
    assert [p.value for p in fixture] == [0.01, -0.02, 0.03]
    # The outcome at each event time is the *next* return (what the
    # prediction at that close actually forecasts).
    outcomes = {(INST, T0 + i * DAY): v for i, v in enumerate([-0.02, 0.03, 0.01])}
    oracle = [_prediction(i, v) for i, v in enumerate([-0.02, 0.03, 0.01])]
    evaluation = score_predictions(
        oracle,
        _provider(outcomes),
        scored_at=T0 + 10 * DAY,
        baselines={"lag": fixture},
    )
    metric = evaluation.metrics[0]
    assert metric.mse == 0.0
    entry = metric.baselines[0]
    assert entry.name == "lag"
    assert entry.matched_pairs == 3
    # Lag errors: [0.01-(-0.02), -0.02-0.03, 0.03-0.01] = [0.03, -0.05, 0.02].
    assert entry.baseline_mse == pytest.approx((0.0009 + 0.0025 + 0.0004) / 3)
    assert entry.skill == pytest.approx(1.0)


def test_duplicate_scored_keys_with_baselines_raise():
    predictions = [_prediction(0, 0.01), _prediction(0, 0.02)]
    # Same event time, different ids: duplicate (instrument, event_time, target).
    predictions[1] = Prediction(
        **{**predictions[1].model_dump(), "prediction_id": "p0b"}
    )
    outcomes = _outcomes([0.01])
    with pytest.raises(ValueError, match="duplicate scored"):
        score_predictions(
            predictions,
            _provider(outcomes),
            scored_at=T0 + 10 * DAY,
            baselines={"lag": [_prediction(0, 0.0)]},
        )


def test_ledger_json_is_deterministic():
    predictions = [_prediction(i, v) for i, v in enumerate([0.01, -0.02])]
    outcomes = _outcomes([0.02, -0.01])
    first = score_predictions(
        predictions, _provider(outcomes), scored_at=T0 + 10 * DAY
    )
    second = score_predictions(
        predictions, _provider(outcomes), scored_at=T0 + 10 * DAY
    )
    assert shadow_ledger_json(first) == shadow_ledger_json(second)
    lines = shadow_ledger_json(first).strip().split("\n")
    assert len(lines) == 2
    import json

    record = json.loads(lines[0])
    assert record["prediction_id"] == "p0"
    assert record["scored"] is True
    assert record["outcome"] == pytest.approx(0.02)
    assert record["error"] == pytest.approx(-0.01)


def test_empty_stream_scores_nothing():
    evaluation = score_predictions(
        [], _provider({}), scored_at=T0 + 10 * DAY
    )
    assert evaluation.n_total == 0
    assert evaluation.n_scored == 0
    assert evaluation.metrics == ()
    assert shadow_ledger_json(evaluation) == ""
