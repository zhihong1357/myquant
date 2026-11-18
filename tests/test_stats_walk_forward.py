import logging
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from myquant.stats.walk_forward import (
    evaluate_walk_forward_forecasts,
    purged_walk_forward_split_report,
    purged_walk_forward_splits,
)


def dated_panel(observations: int = 100):
    decisions = pd.date_range(
        "2024-01-01",
        periods=observations,
        freq="D",
        tz="UTC",
    )
    label_ends = decisions + pd.Timedelta(days=2)
    return decisions, label_ends


def test_purging_and_embargo_remove_the_correct_training_rows():
    decisions, label_ends = dated_panel()

    folds = purged_walk_forward_splits(
        decisions,
        label_ends,
        initial_train_size=40,
        test_size=10,
        embargo=timedelta(days=5),
        minimum_train_size=20,
    )

    first = folds[0]
    assert first.test_indices == tuple(range(40, 50))
    assert first.purged_indices == (38, 39)
    assert first.embargoed_indices == (35, 36, 37)
    assert first.train_indices == tuple(range(35))
    assert first.test_start_time == decisions[40].to_pydatetime()
    assert first.test_last_time == decisions[49].to_pydatetime()

    # All retained training labels end strictly before the held-out window.
    assert all(label_ends[index] < decisions[40] for index in first.train_indices)
    assert all(decisions[index] < decisions[40] - pd.Timedelta(days=5)
               for index in first.train_indices)


def test_walk_forward_windows_are_chronological_disjoint_and_keep_final_partial_test():
    decisions, label_ends = dated_panel(53)

    folds = purged_walk_forward_splits(
        decisions,
        label_ends,
        initial_train_size=40,
        test_size=10,
        minimum_train_size=20,
    )

    assert [fold.test_indices for fold in folds] == [
        tuple(range(40, 50)),
        (50, 51, 52),
    ]
    assert folds[0].test_indices[-1] < folds[1].test_indices[0]
    assert all(fold.train_indices[-1] < fold.test_indices[0] for fold in folds)


def test_max_train_size_limits_candidates_before_purge_and_embargo():
    decisions, label_ends = dated_panel()

    folds = purged_walk_forward_splits(
        decisions,
        label_ends,
        initial_train_size=40,
        test_size=10,
        max_train_size=20,
        embargo=timedelta(days=5),
        minimum_train_size=10,
    )

    first = folds[0]
    assert first.train_indices == tuple(range(20, 35))
    assert first.purged_indices == (38, 39)
    assert first.embargoed_indices == (35, 36, 37)


def test_splitter_rejects_invalid_time_and_window_inputs():
    decisions, label_ends = dated_panel()

    with pytest.raises(ValueError, match="strictly increasing"):
        purged_walk_forward_splits(
            decisions[[1, 0, *range(2, len(decisions))]],
            label_ends,
            initial_train_size=40,
            test_size=10,
            minimum_train_size=20,
        )

    with pytest.raises(ValueError, match="timezone-aware"):
        purged_walk_forward_splits(
            pd.date_range("2024-01-01", periods=100, freq="D"),
            label_ends,
            initial_train_size=40,
            test_size=10,
            minimum_train_size=20,
        )

    invalid_labels = label_ends.copy()
    invalid_labels = invalid_labels.insert(0, decisions[0])
    with pytest.raises(ValueError, match="label_end_times must match"):
        purged_walk_forward_splits(
            decisions,
            invalid_labels,
            initial_train_size=40,
            test_size=10,
            minimum_train_size=20,
        )

    equal_label_end = label_ends.copy()
    equal_label_end = equal_label_end.delete(0).insert(0, decisions[0])
    with pytest.raises(ValueError, match="must be after"):
        purged_walk_forward_splits(
            decisions,
            equal_label_end,
            initial_train_size=40,
            test_size=10,
            minimum_train_size=20,
        )

    with pytest.raises(ValueError, match="prevent overlap"):
        purged_walk_forward_splits(
            decisions,
            label_ends,
            initial_train_size=40,
            test_size=10,
            step_size=5,
            minimum_train_size=20,
        )


def test_splitter_skips_folds_with_too_little_training_and_reports_them(caplog):
    decisions, label_ends = dated_panel()

    with caplog.at_level(logging.WARNING, logger="myquant.stats.walk_forward"):
        report = purged_walk_forward_split_report(
            decisions,
            label_ends,
            initial_train_size=40,
            test_size=10,
            embargo=timedelta(days=30),
            minimum_train_size=20,
        )

    # The first fold keeps only 10 training rows after the 30-day embargo,
    # so it is skipped; later folds have enough history and are kept with
    # their original fold numbers.
    assert len(report.skipped_folds) == 1
    skipped = report.skipped_folds[0]
    assert skipped.fold_number == 1
    assert skipped.training_observations == 10
    assert skipped.minimum_train_size == 20
    assert "after purging and embargo" in skipped.reason
    assert [fold.fold_number for fold in report.folds] == [2, 3, 4, 5, 6]
    assert any(
        "skipping walk-forward fold 1" in record.message
        for record in caplog.records
    )

    # The convenience wrapper returns the same usable folds.
    folds = purged_walk_forward_splits(
        decisions,
        label_ends,
        initial_train_size=40,
        test_size=10,
        embargo=timedelta(days=30),
        minimum_train_size=20,
    )
    assert folds == report.folds


def test_splitter_raises_when_every_fold_is_skipped():
    decisions, label_ends = dated_panel()
    with pytest.raises(ValueError, match="no test fold can be formed"):
        purged_walk_forward_splits(
            decisions,
            label_ends,
            initial_train_size=40,
            test_size=10,
            embargo=timedelta(days=365),
            minimum_train_size=20,
        )


def test_oos_evaluation_scores_only_test_rows_and_aggregates_paired_errors():
    decisions, label_ends = dated_panel()
    folds = purged_walk_forward_splits(
        decisions,
        label_ends,
        initial_train_size=40,
        test_size=10,
        minimum_train_size=20,
    )

    rng = np.random.default_rng(123)
    actual = rng.normal(size=len(decisions))
    baseline = np.full(len(decisions), np.nan)
    augmented = np.full(len(decisions), np.nan)
    for fold in folds:
        indices = np.asarray(fold.test_indices, dtype=np.intp)
        noise = rng.normal(size=indices.size)
        baseline[indices] = actual[indices] + noise
        augmented[indices] = actual[indices] + 0.4 * noise

    result = evaluate_walk_forward_forecasts(
        actual,
        baseline,
        augmented,
        folds=folds,
    )

    assert result.observations == sum(len(fold.test_indices) for fold in folds)
    assert result.incremental_oos_r_squared == pytest.approx(0.84)
    assert result.augmented_mse < result.baseline_mse
    assert len(result.fold_metrics) == len(folds)


def test_oos_score_can_be_negative_and_is_undefined_for_zero_baseline_error():
    decisions, label_ends = dated_panel()
    folds = purged_walk_forward_splits(
        decisions,
        label_ends,
        initial_train_size=40,
        test_size=10,
        minimum_train_size=20,
    )
    actual = np.arange(len(decisions), dtype=float)
    baseline = actual.copy()
    augmented = actual.copy()
    test_indices = np.asarray(folds[0].test_indices, dtype=np.intp)
    augmented[test_indices] += 1.0

    perfect_baseline = evaluate_walk_forward_forecasts(
        actual,
        baseline,
        augmented,
        folds=(folds[0],),
    )
    assert perfect_baseline.incremental_oos_r_squared is None

    baseline[test_indices] = actual[test_indices] + 1.0
    augmented[test_indices] = actual[test_indices] + 2.0
    worse_model = evaluate_walk_forward_forecasts(
        actual,
        baseline,
        augmented,
        folds=(folds[0],),
    )
    assert worse_model.incremental_oos_r_squared == pytest.approx(-3.0)


def test_oos_evaluation_rejects_missing_test_predictions_and_overlapping_folds():
    decisions, label_ends = dated_panel()
    folds = purged_walk_forward_splits(
        decisions,
        label_ends,
        initial_train_size=40,
        test_size=10,
        minimum_train_size=20,
    )
    actual = np.ones(len(decisions), dtype=float)
    baseline = np.ones(len(decisions), dtype=float)
    augmented = np.ones(len(decisions), dtype=float)
    baseline[40] = np.nan

    with pytest.raises(ValueError, match="must be finite"):
        evaluate_walk_forward_forecasts(
            actual,
            baseline,
            augmented,
            folds=(folds[0],),
        )

    with pytest.raises(ValueError, match="match actual length"):
        evaluate_walk_forward_forecasts(
            actual,
            np.ones(len(decisions) - 1),
            augmented,
            folds=(folds[0],),
        )

    overlapping = folds[0].model_copy(
        update={"test_indices": tuple(range(45, 55))}
    )
    with pytest.raises(ValueError, match="non-overlapping"):
        evaluate_walk_forward_forecasts(
            actual,
            np.ones(len(decisions)),
            np.ones(len(decisions)),
            folds=(folds[0], overlapping),
        )
