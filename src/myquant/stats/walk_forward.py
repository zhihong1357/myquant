"""Purged chronological walk-forward splitting and out-of-sample forecast scoring."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime, timedelta
from math import isfinite
from numbers import Integral

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from pydantic import Field, model_validator

from myquant.contracts import StrictContract, require_utc
from myquant.stats._validation import numeric_array

logger = logging.getLogger(__name__)


class WalkForwardFold(StrictContract):
    """One chronological train/test fold with auditable removed sample indices."""

    fold_number: int = Field(ge=1)
    train_indices: tuple[int, ...] = Field(min_length=1)
    test_indices: tuple[int, ...] = Field(min_length=1)
    purged_indices: tuple[int, ...] = ()
    embargoed_indices: tuple[int, ...] = ()
    test_start_time: datetime
    test_last_time: datetime

    @model_validator(mode="after")
    def validate_fold(self) -> WalkForwardFold:
        for name in (
            "train_indices",
            "test_indices",
            "purged_indices",
            "embargoed_indices",
        ):
            values = getattr(self, name)
            if any(isinstance(value, bool) or value < 0 for value in values):
                raise ValueError(f"{name} must contain non-negative integer indices")
            if tuple(sorted(set(values))) != values:
                raise ValueError(f"{name} must be sorted and contain unique indices")

        if self.train_indices[-1] >= self.test_indices[0]:
            raise ValueError("training observations must precede the test window")
        if set(self.train_indices).intersection(self.test_indices):
            raise ValueError("training and test indices must not overlap")
        if set(self.purged_indices).intersection(self.embargoed_indices):
            raise ValueError("purged and embargoed indices must not overlap")
        if set(self.train_indices).intersection(
            (*self.purged_indices, *self.embargoed_indices)
        ):
            raise ValueError("removed indices must not remain in the training set")

        start = require_utc(self.test_start_time)
        last = require_utc(self.test_last_time)
        if last < start:
            raise ValueError("test_last_time must not precede test_start_time")
        object.__setattr__(self, "test_start_time", start)
        object.__setattr__(self, "test_last_time", last)
        return self


class SkippedWalkForwardFold(StrictContract):
    """A test window dropped because too few training rows survived purging."""

    fold_number: int = Field(ge=1)
    test_start_time: datetime
    test_last_time: datetime
    training_observations: int = Field(ge=0)
    minimum_train_size: int = Field(ge=1)
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_skipped_fold(self) -> SkippedWalkForwardFold:
        start = require_utc(self.test_start_time)
        last = require_utc(self.test_last_time)
        if last < start:
            raise ValueError("test_last_time must not precede test_start_time")
        object.__setattr__(self, "test_start_time", start)
        object.__setattr__(self, "test_last_time", last)
        return self


class WalkForwardSplitReport(StrictContract):
    """Usable folds plus an audit record of every skipped test window."""

    folds: tuple[WalkForwardFold, ...] = Field(min_length=1)
    skipped_folds: tuple[SkippedWalkForwardFold, ...] = ()


class FoldForecastMetrics(StrictContract):
    """Paired forecast error metrics for one held-out test window."""

    fold_number: int = Field(ge=1)
    observations: int = Field(ge=1)
    baseline_mse: float = Field(ge=0, allow_inf_nan=False)
    augmented_mse: float = Field(ge=0, allow_inf_nan=False)
    incremental_oos_r_squared: float | None = Field(
        default=None,
        allow_inf_nan=False,
    )


class WalkForwardEvaluation(StrictContract):
    """Aggregate paired out-of-sample forecast performance across folds."""

    fold_metrics: tuple[FoldForecastMetrics, ...] = Field(min_length=1)
    observations: int = Field(ge=1)
    baseline_mse: float = Field(ge=0, allow_inf_nan=False)
    augmented_mse: float = Field(ge=0, allow_inf_nan=False)
    incremental_oos_r_squared: float | None = Field(
        default=None,
        allow_inf_nan=False,
    )


def _decision_index(values: Iterable[datetime]) -> pd.DatetimeIndex:
    try:
        index = pd.DatetimeIndex(tuple(values))
    except (TypeError, ValueError) as exc:
        raise TypeError("decision_times must contain datetime values") from exc
    if index.tz is None:
        raise ValueError("decision_times must be timezone-aware")
    if index.hasnans:
        raise ValueError("decision_times must not contain NaT")
    if not index.is_monotonic_increasing or not index.is_unique:
        raise ValueError(
            "decision_times must be strictly increasing and contain unique timestamps"
        )
    return index


def _label_end_index(
    values: Iterable[datetime],
    *,
    expected_size: int,
) -> pd.DatetimeIndex:
    try:
        index = pd.DatetimeIndex(tuple(values))
    except (TypeError, ValueError) as exc:
        raise TypeError("label_end_times must contain datetime values") from exc
    if index.tz is None:
        raise ValueError("label_end_times must be timezone-aware")
    if index.hasnans:
        raise ValueError("label_end_times must not contain NaT")
    if index.size != expected_size:
        raise ValueError("label_end_times must match decision_times length")
    return index


def _positive_integer(value: int, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be an integer")
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return int(value)


def purged_walk_forward_split_report(
    decision_times: Iterable[datetime],
    label_end_times: Iterable[datetime],
    *,
    initial_train_size: int,
    test_size: int,
    step_size: int | None = None,
    max_train_size: int | None = None,
    embargo: timedelta = timedelta(0),
    minimum_train_size: int = 30,
) -> WalkForwardSplitReport:
    """Build disjoint forward test windows and purge overlapping training labels.

    Each label is assumed to cover the closed time interval from its decision
    timestamp through its label end timestamp. For a test window beginning at
    T, a candidate training row is purged when label_end_time >= T. Equality
    is conservatively treated as overlap.

    The optional embargo is an additional pre-test time gap: after label
    purging, any remaining training row with decision_time >= T - embargo is
    removed. This is the forward-only walk-forward interpretation; no future
    observations are ever admitted into a fold's training set.

    step_size must be at least test_size, so held-out test windows cannot
    overlap. A final shorter test window is retained. When max_train_size is
    supplied, only the most recent candidate training observations are
    considered before purging and embargo are applied.

    A test window whose training set falls below minimum_train_size after
    purging and embargo is skipped, not fatal: the remaining folds are
    still returned, the skipped window is recorded in the report with its
    reason, and a warning is logged. Only when every test window is
    skipped does the function raise. Fold numbers are never renumbered,
    so a fold's number always identifies its test window.

    This splitter handles label-window overlap only. Callers must separately
    enforce point-in-time availability for every feature, source revision and
    model-selection decision.
    """
    decisions = _decision_index(decision_times)
    label_ends = _label_end_index(
        label_end_times,
        expected_size=decisions.size,
    )
    if decisions.size < 2:
        raise ValueError("at least two observations are required")
    if (label_ends <= decisions).any():
        raise ValueError("each label end time must be after its decision time")

    initial_size = _positive_integer(initial_train_size, name="initial_train_size")
    held_out_size = _positive_integer(test_size, name="test_size")
    advance = (
        held_out_size
        if step_size is None
        else _positive_integer(step_size, name="step_size")
    )
    minimum_size = _positive_integer(
        minimum_train_size,
        name="minimum_train_size",
    )
    if initial_size < minimum_size:
        raise ValueError("initial_train_size must be at least minimum_train_size")
    if advance < held_out_size:
        raise ValueError("step_size must be at least test_size to prevent overlap")

    train_limit: int | None = None
    if max_train_size is not None:
        train_limit = _positive_integer(max_train_size, name="max_train_size")
        if train_limit < minimum_size:
            raise ValueError("max_train_size must be at least minimum_train_size")

    if not isinstance(embargo, timedelta):
        raise TypeError("embargo must be a datetime.timedelta")
    embargo_delta = pd.Timedelta(embargo)
    if pd.isna(embargo_delta) or embargo_delta < pd.Timedelta(0):
        raise ValueError("embargo must be finite and non-negative")

    folds: list[WalkForwardFold] = []
    skipped: list[SkippedWalkForwardFold] = []
    fold_number = 1
    for test_start in range(initial_size, decisions.size, advance):
        test_stop = min(test_start + held_out_size, decisions.size)
        test_start_time = decisions[test_start]
        candidate_start = (
            0
            if train_limit is None
            else max(0, test_start - train_limit)
        )
        candidates = list(range(candidate_start, test_start))

        purged = [
            index
            for index in candidates
            if label_ends[index] >= test_start_time
        ]
        purged_set = set(purged)
        after_purge = [
            index for index in candidates if index not in purged_set
        ]

        embargo_cutoff = test_start_time - embargo_delta
        embargoed = [
            index
            for index in after_purge
            if decisions[index] >= embargo_cutoff
        ]
        embargoed_set = set(embargoed)
        training = [
            index for index in after_purge if index not in embargoed_set
        ]

        if len(training) < minimum_size:
            skipped.append(
                SkippedWalkForwardFold(
                    fold_number=fold_number,
                    test_start_time=decisions[test_start].to_pydatetime(),
                    test_last_time=decisions[test_stop - 1].to_pydatetime(),
                    training_observations=len(training),
                    minimum_train_size=minimum_size,
                    reason=(
                        f"only {len(training)} training observations remain "
                        f"after purging and embargo; minimum is {minimum_size}"
                    ),
                )
            )
            logger.warning(
                "skipping walk-forward fold %s: %s",
                fold_number,
                skipped[-1].reason,
            )
        else:
            folds.append(
                WalkForwardFold(
                    fold_number=fold_number,
                    train_indices=tuple(training),
                    test_indices=tuple(range(test_start, test_stop)),
                    purged_indices=tuple(purged),
                    embargoed_indices=tuple(embargoed),
                    test_start_time=decisions[test_start].to_pydatetime(),
                    test_last_time=decisions[test_stop - 1].to_pydatetime(),
                )
            )
        fold_number += 1

    if not folds:
        if skipped:
            raise ValueError(
                "no test fold can be formed from the supplied sample: "
                f"{len(skipped)} test window(s) were skipped; the first "
                f"was skipped because {skipped[0].reason}"
            )
        raise ValueError("no test fold can be formed from the supplied sample")
    return WalkForwardSplitReport(
        folds=tuple(folds),
        skipped_folds=tuple(skipped),
    )


def purged_walk_forward_splits(
    decision_times: Iterable[datetime],
    label_end_times: Iterable[datetime],
    *,
    initial_train_size: int,
    test_size: int,
    step_size: int | None = None,
    max_train_size: int | None = None,
    embargo: timedelta = timedelta(0),
    minimum_train_size: int = 30,
) -> tuple[WalkForwardFold, ...]:
    """Build purged walk-forward folds; see purged_walk_forward_split_report.

    Returns only the usable folds. Test windows whose training set falls
    below minimum_train_size after purging and embargo are skipped; use
    purged_walk_forward_split_report for the audit record of skipped
    windows.
    """
    return purged_walk_forward_split_report(
        decision_times,
        label_end_times,
        initial_train_size=initial_train_size,
        test_size=test_size,
        step_size=step_size,
        max_train_size=max_train_size,
        embargo=embargo,
        minimum_train_size=minimum_train_size,
    ).folds


def _prediction_vector(
    values: Iterable[float],
    *,
    name: str,
    expected_size: int,
) -> NDArray[np.float64]:
    # NaN is allowed here: forecasts outside the held-out rows are ignored,
    # and finiteness is enforced per test row during scoring.
    result = numeric_array(values, name=name)
    if result.size != expected_size:
        raise ValueError(f"{name} must be one-dimensional and match actual length")
    return result


def evaluate_walk_forward_forecasts(
    actual: Iterable[float],
    baseline_forecasts: Iterable[float],
    augmented_forecasts: Iterable[float],
    *,
    folds: Iterable[WalkForwardFold],
) -> WalkForwardEvaluation:
    """Score paired forecasts only on held-out test rows from supplied folds.

    The baseline may be a persistence forecast or a preregistered base model;
    augmented forecasts must be generated without fitting on their test rows.
    The reported incremental OOS R-squared is 1 - SSE_augmented / SSE_baseline.
    It can be negative. A value of zero means no improvement over the baseline,
    and a positive value means lower squared error than the baseline.

    This function does not train models, select hyperparameters, enforce feature
    availability, or correct for multiple testing. Those obligations belong to
    the fold-specific training pipeline and preregistered research protocol.
    """
    actual_raw = tuple(actual)
    actual_values = _prediction_vector(
        actual_raw,
        name="actual",
        expected_size=len(actual_raw),
    )
    baseline_values = _prediction_vector(
        baseline_forecasts,
        name="baseline_forecasts",
        expected_size=actual_values.size,
    )
    augmented_values = _prediction_vector(
        augmented_forecasts,
        name="augmented_forecasts",
        expected_size=actual_values.size,
    )

    selected_folds = tuple(folds)
    if not selected_folds:
        raise ValueError("at least one fold is required")

    selected_indices: list[int] = []
    fold_metrics: list[FoldForecastMetrics] = []
    previous_test_end = -1
    for fold in selected_folds:
        indices = fold.test_indices
        if indices[0] <= previous_test_end:
            raise ValueError("fold test windows must be chronological and non-overlapping")
        previous_test_end = indices[-1]
        if any(index >= actual_values.size for index in indices):
            raise ValueError("fold test index is outside the forecast arrays")
        selected_indices.extend(indices)

        index_array = np.asarray(indices, dtype=np.intp)
        y = actual_values[index_array]
        baseline = baseline_values[index_array]
        augmented = augmented_values[index_array]
        if not (
            np.isfinite(y).all()
            and np.isfinite(baseline).all()
            and np.isfinite(augmented).all()
        ):
            raise ValueError("actual values and test forecasts must be finite")

        baseline_sse = float(np.sum((y - baseline) ** 2))
        augmented_sse = float(np.sum((y - augmented) ** 2))
        fold_r_squared = (
            None
            if baseline_sse == 0.0
            else 1.0 - augmented_sse / baseline_sse
        )
        fold_metrics.append(
            FoldForecastMetrics(
                fold_number=fold.fold_number,
                observations=len(indices),
                baseline_mse=baseline_sse / len(indices),
                augmented_mse=augmented_sse / len(indices),
                incremental_oos_r_squared=fold_r_squared,
            )
        )

    total_indices = np.asarray(selected_indices, dtype=np.intp)
    total_actual = actual_values[total_indices]
    total_baseline = baseline_values[total_indices]
    total_augmented = augmented_values[total_indices]
    baseline_sse_total = float(np.sum((total_actual - total_baseline) ** 2))
    augmented_sse_total = float(np.sum((total_actual - total_augmented) ** 2))
    if not isfinite(baseline_sse_total) or not isfinite(augmented_sse_total):
        raise ArithmeticError("forecast scoring produced non-finite squared errors")

    total_observations = int(total_indices.size)
    return WalkForwardEvaluation(
        fold_metrics=tuple(fold_metrics),
        observations=total_observations,
        baseline_mse=baseline_sse_total / total_observations,
        augmented_mse=augmented_sse_total / total_observations,
        incremental_oos_r_squared=(
            None
            if baseline_sse_total == 0.0
            else 1.0 - augmented_sse_total / baseline_sse_total
        ),
    )
