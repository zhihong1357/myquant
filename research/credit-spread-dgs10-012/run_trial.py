"""Run trial T0020 for hypothesis H0017 v2 (BAA10Y -> DGS10 transmission).

Run after preregistration and fetching, from the repo root, with a clean
worktree (the trial records the HEAD commit as its code revision):

    .venv/bin/python research/credit-spread-dgs10-012/run_trial.py

The trial binds the preregistered H0017 v2 spec, the fetch manifest's
SHA-256 as the data fingerprint, and a canonical-JSON hash of the
analysis configuration. It executes the six-step thesis flow in one
trial:

1. naive lead-lag scan (descriptive, lags 0-5, unlagged changes);
2. synchronized daily panel (no forward filling) plus the
   publication-lag transforms: the BAA10Y predictor is the level
   change in basis points lagged 2 trading days by availability, the
   SPX control is the log change unlagged (Yahoo posts the close the
   same evening, so SPX[t] is knowable at the decision close — study
   003's factor-alignment precedent), both via the study-007
   lagged-changes module (diff-then-join, shift between diff and
   join). The target is the DGS10 level change in basis points (a
   yield has no meaningful log return);
3. the preregistered single-test primary (partial lead-lag, lag 1 in
   regression terms: the predictor available at close t forecasts the
   DGS10 change over t+1), plus the no-factor upper-bound control.
   The baseline controls for the target's own lag-1 change, the
   target's own lag-2 change (the mechanical guard — BAA10Y is BAA
   minus DGS10 by definition, so the lag-2 predictor contains minus
   the target's own lag-2 change) and the SPX control; the guard is
   retained in the no-factor bound, where "no-factor" means no SPX,
   not no guard;
4. descriptive only: the unlagged (naive) alignment — the lookahead
   version, quantifying what ignoring the publication lag would buy
   — the reverse placebo (DGS10->BAA10Y, itself mechanically
   confounded — see the report), sub-period stability, and the
   decomposition checks (predictor-guard correlation, the lagged-BAA
   supplementary regression with the BAA change derived from the
   identity ΔBAA = ΔBAA10Y + ΔDGS10, and the DGS10 change
   autocorrelations);
5. purged walk-forward out-of-sample evaluation, scored in full and
   on the preregistered holdout window only;
6. informational cost assessment (study 003's precedent for a
   non-tradable target): the gross sign-rule edge on holdout OOS
   augmented forecasts, no costs applied, in basis points per day,
   with a block-bootstrap CI. DGS10 is a yield and is not directly
   tradable; free proxy series exist (Yahoo ZN=F and IEF both return
   data, verified 2026-11-19) but converting a yield-change signal
   into a futures or ETF position requires a DV01/duration conversion
   and futures roll handling that this study does not model, so no
   clean cost measurement is available; the assessment carries
   no verdict weight.

The verdict covers the three preregistered acceptance criteria
(study 003's three — the cost gate is informational here, not a
criterion). The runner records the trial (including failures) in the
hash-chained ledger trials.jsonl; it does not decide acceptance.

The sample is the full window (2003-01-02 to the fetch date): DGS10 is
still published, so unlike study 009 there is no truncation.

Scaffold note: the 6c scaffold generated a minimal run_trial.py that
wired only the primary test and a two-criterion verdict, and left the
walk-forward evaluation and the cost gate as NotImplementedError
stubs. This file replaces that skeleton with the full study-001/003
pipeline; see the study report's scaffold-feedback section. (The
scaffold's old bar_seconds=86400 bug is fixed — the generated file
now passes bar_seconds=None — so this file keeps no bar_seconds at
all, per the study-003 convention.)
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from myquant.canonical import canonical_json
from myquant.contracts import MultiplicityCorrection, Observation
from myquant.experiments import (
    ExperimentRunner,
    TrialParameter,
    TrialSpec,
    git_head_revision,
)
from myquant.hypotheses import HypothesisRegistry, HypothesisSpec
from myquant.pit import ParquetPITStore
from myquant.sources import SourceRegistry
from myquant.stats import (
    WalkForwardFold,
    adjust_pvalues,
    block_bootstrap_mean_ci,
    block_bootstrap_mean_test,
    evaluate_walk_forward_forecasts,
    lead_lag_scan,
    ols_fit,
    partial_lead_lag,
    purged_walk_forward_split_report,
)
from myquant.studies.panel import (
    SynchronizedPanel,
    build_synchronized_panel,
    level_changes_on_index,
)
from myquant.studies.publication_lag import (
    lagged_changes_on_index,
    lagged_panel_index,
)

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "credit-spread-dgs10-012"

HYPOTHESIS_ID = "H0017"
HYPOTHESIS_VERSION = 2
TRIAL_ID = "T0020"

BAA10Y = "credit:baa-10y-spread"
DGS10 = "rates:us-10y-yield"
SPX = "index:sp500"
DAILY_INSTRUMENTS = (BAA10Y, DGS10, SPX)

# No cost constants: the cost gate is informational only (study 003's
# precedent for a non-tradable target — DGS10 is a yield; free proxy
# series exist (Yahoo ZN=F and IEF) but the DV01/duration conversion
# and futures roll handling are not modelled, so no clean cost can be
# measured). The trial reports the gross sign-rule edge in basis
# points per day with a block-bootstrap CI.


def load_panels() -> tuple[SynchronizedPanel, list[Observation], dict[str, Any]]:
    """Load the daily panel and the raw observations from the PIT store.

    No bar_seconds: US trading days have weekend gaps, so returns are
    per-trading-day log returns (study 003's convention). The
    scaffold used to generate bar_seconds=86400, which would
    invalidate every Monday return; that bug was fixed in PR #28 and
    the generated file now passes bar_seconds=None. (The panel's log
    returns are used only for the synchronized index and the SPX
    control; the BAA10Y predictor and the DGS10 target are level
    changes in basis points, computed from the observations.)
    """
    manifest_path = ROOT / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    decision_time = datetime.fromisoformat(manifest["fetched_at"])
    if decision_time.tzinfo is None:
        decision_time = decision_time.replace(tzinfo=UTC)

    source_registry = SourceRegistry(ROOT / "sources")
    daily_store = ParquetPITStore(CACHE_ROOT / "pit-1d", source_registry)
    observations = daily_store.query_as_of(
        decision_time,
        instrument_ids=set(DAILY_INSTRUMENTS),
        fields={"close"},
    )
    daily = build_synchronized_panel(
        observations,
        instruments=DAILY_INSTRUMENTS,
    )
    manifest_info = {
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "fetched_at": manifest["fetched_at"],
    }
    return daily, observations, manifest_info


def build_lagged_frame(
    panel: SynchronizedPanel,
    observations: list[Observation],
    *,
    baa_lag_steps: int,
    spx_lag_steps: int,
    guard_lag_steps: int,
) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    """The regression frame: lagged predictors + DGS10 level changes.

    The truncated index drops the first max(lag) panel rows (no lagged
    BAA10Y change exists there). The BAA10Y predictor is the level
    change in basis points lagged ``baa_lag_steps`` positions; the
    SPX control is the log change lagged ``spx_lag_steps`` positions
    (0: the change over the decision day itself, knowable at the close
    because Yahoo posts the same evening); the guard is the DGS10
    level change in basis points lagged ``guard_lag_steps`` positions
    (the target's own change at the predictor's value date — the
    mechanical guard); the target is the DGS10 level change in basis
    points on the frame index itself. The unlagged BAA10Y change (for
    the naive descriptive) is computed on the same index. The derived
    BAA change (for the decomposition check) is the identity
    ΔBAA = ΔBAA10Y + ΔDGS10 at the predictor's value date.
    """
    max_lag = max(baa_lag_steps, spx_lag_steps, guard_lag_steps)
    index = lagged_panel_index(panel.returns.index, max_lag)
    frame = pd.DataFrame(index=index)
    baa_lagged = lagged_changes_on_index(
        observations,
        instruments=(BAA10Y,),
        index=index,
        lag_steps=baa_lag_steps,
        transform="level",
        scale=100.0,
    )
    spx_lagged = lagged_changes_on_index(
        observations,
        instruments=(SPX,),
        index=index,
        lag_steps=spx_lag_steps,
        transform="log",
    )
    dgs10_guard = lagged_changes_on_index(
        observations,
        instruments=(DGS10,),
        index=index,
        lag_steps=guard_lag_steps,
        transform="level",
        scale=100.0,
    )
    baa_naive = level_changes_on_index(
        observations,
        instruments=(BAA10Y,),
        index=index,
        scale=100.0,
    )
    dgs10 = level_changes_on_index(
        observations,
        instruments=(DGS10,),
        index=index,
        scale=100.0,
    )
    frame["baa_lagged"] = baa_lagged[BAA10Y]
    frame["spx_lagged"] = spx_lagged[SPX]
    frame["dgs10_guard"] = dgs10_guard[DGS10]
    frame["baa_naive"] = baa_naive[BAA10Y]
    frame["dgs10"] = dgs10[DGS10]
    # The derived BAA change at the predictor's value date, from the
    # identity ΔBAA = ΔBAA10Y + ΔDGS10 (both in basis points). FRED
    # publishes BAA monthly only, so no daily BAA series exists to
    # fetch (H0017 v2 amendment); the identity is exact wherever both
    # legs' changes span the same interval, which holds on every
    # frame row (both changes end on panel return rows — see the
    # alignment diagnostic in the trial metrics).
    frame["baa_derived"] = frame["baa_lagged"] + frame["dgs10_guard"]
    return frame, index


def _guard_alignment_rows(
    observations: list[Observation],
    index: pd.DatetimeIndex,
    *,
    lag_steps: int,
) -> int:
    """Frame rows where the guard's value date differs from the predictor's.

    The study-007 lagged-changes module shifts each series on its own
    dates, so the predictor's value date (the 2nd previous BAA10Y
    date) and the guard's value date (the 2nd previous DGS10 date)
    can differ on rows following a date where exactly one leg is
    missing. On those rows the guard is off by one day and the
    mechanical channel is not exactly blocked. The count is a
    diagnostic: a handful of rows out of ~6,000 is negligible, but
    it is recorded rather than assumed.
    """
    own_dates: dict[str, pd.DatetimeIndex] = {}
    for instrument_id in (BAA10Y, DGS10):
        times = sorted(
            {
                item.event_time
                for item in observations
                if item.instrument_id == instrument_id and item.field == "close"
            }
        )
        own_dates[instrument_id] = pd.DatetimeIndex(times, tz="UTC")
    misaligned = 0
    for timestamp in index:
        baa_pos = own_dates[BAA10Y].get_loc(timestamp)
        dgs10_pos = own_dates[DGS10].get_loc(timestamp)
        baa_value_date = own_dates[BAA10Y][baa_pos - lag_steps]
        dgs10_value_date = own_dates[DGS10][dgs10_pos - lag_steps]
        if baa_value_date != dgs10_value_date:
            misaligned += 1
    return misaligned


def analysis_config(spec: HypothesisSpec) -> dict[str, Any]:
    """The exact analysis configuration, hashed as the config fingerprint."""
    return {
        "fixed_parameters": list(spec.fixed_parameters),
        "test_family": ["daily_baa10y_dgs10"],
        "multiple_testing_method": spec.multiple_testing_method.value,
        "target_error_rate": spec.target_error_rate,
        "train_window": [
            spec.train_window.start.isoformat(),
            spec.train_window.end.isoformat(),
        ],
        "validation_window": [
            spec.validation_window.start.isoformat(),
            spec.validation_window.end.isoformat(),
        ],
        "holdout_window": [
            spec.holdout_window.start.isoformat(),
            spec.holdout_window.end.isoformat(),
        ],
        "cost_model": spec.cost_model,
        "trial_script": "research/credit-spread-dgs10-012/run_trial.py",
    }


def build_trial_spec(
    spec: HypothesisSpec,
    *,
    hypothesis_fingerprint: str,
    data_fingerprint: str,
    code_revision: str,
) -> TrialSpec:
    config_fingerprint = hashlib.sha256(
        canonical_json(analysis_config(spec))
    ).hexdigest()
    parameters = tuple(
        TrialParameter(name=name, value=value)
        for name, value in (
            item.split("=", maxsplit=1) for item in spec.fixed_parameters
        )
    )
    return TrialSpec(
        trial_id=TRIAL_ID,
        hypothesis_id=HYPOTHESIS_ID,
        hypothesis_version=HYPOTHESIS_VERSION,
        hypothesis_fingerprint=hypothesis_fingerprint,
        description=(
            "BAA10Y->DGS10 transmission: lagged spread-change partial "
            "lead-lag with a lag-2 mechanical guard, purged "
            "walk-forward OOS evaluation, decomposition checks and an "
            "informational gross sign-rule edge in bp/day (no cost "
            "gate: DGS10 is a yield and the DV01/roll mapping is not "
            "modelled)"
        ),
        seed=spec.random_seed,
        data_fingerprint=data_fingerprint,
        config_fingerprint=config_fingerprint,
        code_revision=code_revision,
        universe=spec.universe,
        observation_frequency=spec.observation_frequency,
        horizon_seconds=spec.horizon_seconds,
        target_definition=spec.target_definition,
        source_versions=spec.source_versions,
        feature_set=spec.feature_set,
        model_definition=spec.model_definition,
        benchmark=spec.benchmark,
        cost_model=spec.cost_model,
        primary_metric=spec.primary_metric,
        expected_direction=spec.expected_direction,
        parameters=parameters,
    )


def _partial_test(
    source: np.ndarray,
    target: np.ndarray,
    *,
    factors: dict[str, np.ndarray] | None,
    max_hac_lag: int,
) -> dict[str, Any]:
    """One partial lead-lag test; returns JSON-safe metrics."""
    result = partial_lead_lag(
        source,
        target,
        lag_steps=1,
        common_factors=factors,
        max_hac_lag=max_hac_lag,
    )
    effect = result.source_effect
    if effect.p_value is None:
        raise ValueError("HAC p-value is unavailable; cannot form the test family")
    return {
        "observations": result.observations,
        "coefficient": effect.estimate,
        "standard_error": effect.standard_error,
        "t_statistic": effect.t_statistic,
        "p_value": effect.p_value,
        "partial_r_squared": result.partial_r_squared,
        "incremental_r_squared": result.incremental_r_squared,
        "base_r_squared": result.base_model.r_squared,
        "augmented_r_squared": result.augmented_model.r_squared,
    }


def _ols_predict(
    fit: Any,
    predictors: dict[str, np.ndarray],
) -> np.ndarray:
    """Predict from an OLSResult: coefficients[0] is the intercept."""
    prediction = np.full(
        next(iter(predictors.values())).shape,
        fit.intercept if fit.intercept is not None else 0.0,
        dtype=float,
    )
    for offset, name in enumerate(fit.predictor_names):
        prediction = prediction + fit.coefficients[offset + 1] * predictors[name]
    return prediction


def run_walk_forward(
    frame: pd.DataFrame,
    *,
    initial_train_size: int,
    test_size: int,
    embargo_days: int,
    holdout_start: datetime,
) -> dict[str, Any]:
    """Purged walk-forward OOS evaluation of the BAA10Y->DGS10 model.

    Regression row j uses predictors known at day j's close (the
    lagged BAA10Y change, the SPX change over day j, DGS10's own
    change over day j and its lag-2 change) to forecast the DGS10
    change over day j+1. Label ends are the exact next-row event
    times, so weekends and holidays are handled exactly (a Friday
    row's label ends Monday).
    """
    baa = frame["baa_lagged"].to_numpy(dtype=float)
    spx = frame["spx_lagged"].to_numpy(dtype=float)
    guard = frame["dgs10_guard"].to_numpy(dtype=float)
    dgs10 = frame["dgs10"].to_numpy(dtype=float)
    target = dgs10[1:]
    predictors = {
        "target_lag": dgs10[:-1],
        "target_lag2": guard[:-1],
        "spx": spx[:-1],
        "baa": baa[:-1],
    }
    decision_times = [item.to_pydatetime() for item in frame.index[:-1]]
    label_ends = [item.to_pydatetime() for item in frame.index[1:]]
    report = purged_walk_forward_split_report(
        decision_times,
        label_ends,
        initial_train_size=initial_train_size,
        test_size=test_size,
        embargo=timedelta(days=embargo_days),
        minimum_train_size=30,
    )
    folds = report.folds
    baseline_forecasts = np.full(target.shape, np.nan)
    augmented_forecasts = np.full(target.shape, np.nan)
    for fold in folds:
        train = np.asarray(fold.train_indices, dtype=np.intp)
        test = np.asarray(fold.test_indices, dtype=np.intp)
        base_fit = ols_fit(
            target[train],
            {
                "target_lag": predictors["target_lag"][train],
                "target_lag2": predictors["target_lag2"][train],
                "spx": predictors["spx"][train],
            },
        )
        augmented_fit = ols_fit(
            target[train],
            {name: values[train] for name, values in predictors.items()},
        )
        baseline_forecasts[test] = _ols_predict(
            base_fit,
            {name: values[test] for name, values in predictors.items() if name != "baa"},
        )
        augmented_forecasts[test] = _ols_predict(
            augmented_fit,
            {name: values[test] for name, values in predictors.items()},
        )
    evaluation = evaluate_walk_forward_forecasts(
        target,
        baseline_forecasts,
        augmented_forecasts,
        folds=folds,
    )

    # Holdout-only scoring: restrict each fold's test rows to the
    # preregistered holdout window; training sets are unchanged.
    holdout_folds: list[WalkForwardFold] = []
    for fold in folds:
        restricted = tuple(
            index
            for index in fold.test_indices
            if decision_times[index] >= holdout_start
        )
        if not restricted:
            continue
        holdout_folds.append(
            WalkForwardFold(
                fold_number=fold.fold_number,
                train_indices=fold.train_indices,
                test_indices=restricted,
                purged_indices=fold.purged_indices,
                embargoed_indices=fold.embargoed_indices,
                test_start_time=decision_times[restricted[0]],
                test_last_time=decision_times[restricted[-1]],
            )
        )
    holdout_evaluation = evaluate_walk_forward_forecasts(
        target,
        baseline_forecasts,
        augmented_forecasts,
        folds=holdout_folds,
    )
    holdout_test_rows = [index for fold in holdout_folds for index in fold.test_indices]
    return {
        "folds": len(folds),
        "skipped_folds": len(report.skipped_folds),
        "test_rows": int(evaluation.observations),
        "all_oos_incremental_r_squared": evaluation.incremental_oos_r_squared,
        "all_baseline_mse": evaluation.baseline_mse,
        "all_augmented_mse": evaluation.augmented_mse,
        "holdout_folds": len(holdout_folds),
        "holdout_test_rows": len(holdout_test_rows),
        "holdout_oos_incremental_r_squared": (
            holdout_evaluation.incremental_oos_r_squared
        ),
        "holdout_baseline_mse": holdout_evaluation.baseline_mse,
        "holdout_augmented_mse": holdout_evaluation.augmented_mse,
        "fold_metrics": [
            {
                "fold": metric.fold_number,
                "observations": metric.observations,
                "incremental_oos_r_squared": metric.incremental_oos_r_squared,
            }
            for metric in evaluation.fold_metrics
        ],
        "holdout_test_indices": holdout_test_rows,
        "holdout_forecasts": [
            float(augmented_forecasts[index]) for index in holdout_test_rows
        ],
        "holdout_actuals": [float(target[index]) for index in holdout_test_rows],
    }


def run_cost_gate_informational(
    forecasts: list[float],
    actuals: list[float],
    *,
    block_length: int,
    resamples: int,
    seed: int,
) -> dict[str, Any]:
    """INFORMATIONAL cost assessment: gross sign-rule edge, no costs.

    Sign rule on holdout OOS augmented forecasts (1x, always invested
    while positioned), in basis points per day on the DGS10 change
    itself. No costs are applied: DGS10 is a yield and is not
    directly tradable, and converting a yield-change signal into a
    futures or ETF position requires a DV01/duration conversion and
    futures roll handling that this study does not model (free proxy
    series exist — Yahoo ZN=F and IEF both return data, verified
    2026-11-19 — but no clean cost measurement follows from them).
    The gross edge is an upper bound on any tradable edge, not
    a verdict criterion (study 003's precedent).
    """
    positions = np.sign(np.asarray(forecasts, dtype=float))
    actuals_array = np.asarray(actuals, dtype=float)
    gross = positions * actuals_array
    nonzero = actuals_array != 0.0
    sign_accuracy = (
        float(np.mean(positions[nonzero] == np.sign(actuals_array[nonzero])))
        if nonzero.any()
        else None
    )
    interval = block_bootstrap_mean_ci(
        gross,
        block_length=block_length,
        resamples=resamples,
        seed=seed,
    )
    test = block_bootstrap_mean_test(
        gross,
        null_mean=0.0,
        block_length=block_length,
        resamples=resamples,
        seed=seed,
    )
    return {
        "days": int(gross.size),
        "gross_daily_edge": float(np.mean(gross)),
        "gross_edge_ci_lower": interval.lower_bound,
        "gross_edge_ci_upper": interval.upper_bound,
        "gross_edge_bootstrap_p_value": test.p_value,
        "sign_accuracy": sign_accuracy,
        "costs_applied": 0.0,
        "units": "basis points per day",
        "note": (
            "Informational only: no costs applied. DGS10 is a yield "
            "and is not directly tradable; free proxy series exist "
            "(Yahoo ZN=F and IEF) but the DV01/duration conversion "
            "and futures roll handling are not modelled, so no clean "
            "cost measurement is available. Not a verdict criterion."
        ),
    }


def _parse_subperiods(raw: str) -> tuple[tuple[str, datetime, datetime], ...]:
    """Parse 'YYYY-YYYY,...' into half-open [Jan 1, Jan 1) ranges."""
    subperiods: list[tuple[str, datetime, datetime]] = []
    for label in raw.split(","):
        start_year, end_year = label.split("-")
        start = datetime(int(start_year), 1, 1, 21, 0, tzinfo=UTC)
        end = datetime(int(end_year) + 1, 1, 1, 21, 0, tzinfo=UTC)
        subperiods.append((label, start, end))
    return tuple(subperiods)


def run_subperiod_stability(
    frame: pd.DataFrame,
    *,
    subperiods: tuple[tuple[str, datetime, datetime], ...],
    max_hac_lag: int,
) -> dict[str, Any]:
    """Descriptive primary-test coefficient by preregistered sub-period.

    Each sub-period slices the regression frame to its date range and
    re-runs the primary partial lead-lag test (SPX factor plus the
    lag-2 guard). Coefficients and partial R-squared only — no
    p-values, not in the test family.
    """
    index = frame.index
    baa = frame["baa_lagged"].to_numpy(dtype=float)
    spx = frame["spx_lagged"].to_numpy(dtype=float)
    guard = frame["dgs10_guard"].to_numpy(dtype=float)
    dgs10 = frame["dgs10"].to_numpy(dtype=float)
    results: dict[str, Any] = {}
    for label, start, end in subperiods:
        mask = (index >= start) & (index < end)
        result = partial_lead_lag(
            baa[mask],
            dgs10[mask],
            lag_steps=1,
            common_factors={"spx": spx[mask], "dgs10_lag2": guard[mask]},
            max_hac_lag=max_hac_lag,
        )
        results[label] = {
            "observations": result.observations,
            "coefficient": result.source_effect.estimate,
            "standard_error": result.source_effect.standard_error,
            "partial_r_squared": result.partial_r_squared,
        }
    return results


def run_decomposition(
    frame: pd.DataFrame,
    *,
    max_hac_lag: int,
) -> dict[str, Any]:
    """Descriptive decomposition of the mechanical confound.

    (1) The correlation between the predictor (lagged ΔBAA10Y) and
    the guard (the target's own lag-2 change) quantifies the
    mechanical component's size: the predictor contains minus the
    guard by construction. (2) The lagged-ΔBAA supplementary
    regression tests the non-mechanical component directly, with the
    BAA change derived from the identity ΔBAA = ΔBAA10Y + ΔDGS10
    (FRED publishes BAA monthly only — H0017 v2 amendment). Given
    the guard, it is a restatement of the primary test, not
    independent evidence: the ΔDGS10 component of the derived
    predictor is already controlled, so the coefficient, t-statistic
    and partial R-squared should match the primary's. (3) The DGS10
    change autocorrelations at lags 1 and 2 measure the channel
    through which the mechanical effect would operate.
    """
    baa = frame["baa_lagged"].to_numpy(dtype=float)
    spx = frame["spx_lagged"].to_numpy(dtype=float)
    guard = frame["dgs10_guard"].to_numpy(dtype=float)
    dgs10 = frame["dgs10"].to_numpy(dtype=float)
    baa_derived = frame["baa_derived"].to_numpy(dtype=float)
    predictor_guard_correlation = float(np.corrcoef(baa, guard)[0, 1])
    baa_test = _partial_test(
        baa_derived,
        dgs10,
        factors={"spx": spx, "dgs10_lag2": guard},
        max_hac_lag=max_hac_lag,
    )
    autocorrelations = {
        f"lag_{lag}": float(np.corrcoef(dgs10[:-lag], dgs10[lag:])[0, 1])
        for lag in (1, 2)
    }
    return {
        "predictor_guard_correlation": predictor_guard_correlation,
        "predictor_guard_observations": int(baa.size),
        "lagged_baa_regression": baa_test,
        "dgs10_change_autocorrelations": autocorrelations,
    }


def build_experiment(
    panel: SynchronizedPanel,
    observations: list[Observation],
    spec: HypothesisSpec,
) -> Any:
    """Build the trial callback closing over the loaded panel."""

    def experiment(trial_spec: TrialSpec) -> dict[str, Any]:
        params = {item.name: item.value for item in trial_spec.parameters}
        baa_lag_steps = int(params["predictor_lag_steps"])
        spx_lag_steps = int(params["control_lag_steps"])
        guard_lag_steps = int(params["guard_lag_steps"])
        daily_max_hac_lag = int(params["daily_max_hac_lag"])
        bootstrap_block_length = int(params["bootstrap_block_length"])
        bootstrap_resamples = int(params["bootstrap_resamples"])
        bootstrap_seed = int(params["bootstrap_seed"])
        walk_forward_initial_train = int(params["walk_forward_initial_train"])
        walk_forward_test_size = int(params["walk_forward_test_size"])
        walk_forward_embargo_days = int(params["walk_forward_embargo_days"])
        subperiods = _parse_subperiods(str(params["subperiods"]))

        frame, index = build_lagged_frame(
            panel,
            observations,
            baa_lag_steps=baa_lag_steps,
            spx_lag_steps=spx_lag_steps,
            guard_lag_steps=guard_lag_steps,
        )
        baa = frame["baa_lagged"].to_numpy(dtype=float)
        spx = frame["spx_lagged"].to_numpy(dtype=float)
        guard = frame["dgs10_guard"].to_numpy(dtype=float)
        baa_naive = frame["baa_naive"].to_numpy(dtype=float)
        dgs10 = frame["dgs10"].to_numpy(dtype=float)

        # Step 1: naive scan (descriptive, unlagged changes).
        scan = lead_lag_scan(baa_naive, dgs10, lag_steps=(0, 1, 2, 3, 4, 5))

        # Step 3: the preregistered single-test primary (SPX factor
        # plus the lag-2 guard), plus the no-factor upper-bound
        # control (the guard is retained — "no-factor" means no SPX,
        # not no guard).
        primary = _partial_test(
            baa,
            dgs10,
            factors={"spx": spx, "dgs10_lag2": guard},
            max_hac_lag=daily_max_hac_lag,
        )
        primary_no_factor = _partial_test(
            baa,
            dgs10,
            factors={"dgs10_lag2": guard},
            max_hac_lag=daily_max_hac_lag,
        )
        adjusted = adjust_pvalues(
            [primary["p_value"]],
            method=MultiplicityCorrection.HOLM,
            target_error_rate=spec.target_error_rate,
        )
        holm: list[dict[str, Any]] = [
            {
                "test": "daily_baa10y_dgs10",
                "raw_p_value": adjusted[0].raw_p_value,
                "adjusted_p_value": adjusted[0].adjusted_p_value,
                "reject": adjusted[0].reject,
            }
        ]

        # Step 4 (descriptive): the naive unlagged alignment (the
        # lookahead version — what ignoring the publication lag would
        # buy; the guard is retained for a like-for-like base, though
        # it is redundant there because the naive predictor's DGS10
        # component is at t and the lag-1 own-history term already
        # covers it), the reverse placebo (DGS10 -> BAA10Y — no guard:
        # the guard has no meaning for the reverse direction, and the
        # reverse test is itself mechanically confounded, see the
        # report), sub-period stability and the decomposition checks.
        naive = _partial_test(
            baa_naive,
            dgs10,
            factors={"spx": spx, "dgs10_lag2": guard},
            max_hac_lag=daily_max_hac_lag,
        )
        reverse = _partial_test(
            dgs10,
            baa_naive,
            factors={"spx": spx},
            max_hac_lag=daily_max_hac_lag,
        )
        subperiods_result = run_subperiod_stability(
            frame,
            subperiods=subperiods,
            max_hac_lag=daily_max_hac_lag,
        )
        decomposition = run_decomposition(
            frame,
            max_hac_lag=daily_max_hac_lag,
        )
        guard_misaligned_rows = _guard_alignment_rows(
            observations,
            index,
            lag_steps=guard_lag_steps,
        )

        # Step 5: purged walk-forward OOS evaluation.
        walk_forward = run_walk_forward(
            frame,
            initial_train_size=walk_forward_initial_train,
            test_size=walk_forward_test_size,
            embargo_days=walk_forward_embargo_days,
            holdout_start=spec.holdout_window.start,
        )
        holdout_oos_r2 = walk_forward["holdout_oos_incremental_r_squared"]

        # Step 6: informational cost assessment on holdout OOS
        # augmented forecasts (gross sign-rule edge in bp/day, no
        # costs — DGS10 is a yield and the DV01/roll mapping is not
        # modelled; study 003's precedent, not a verdict criterion).
        cost_gate = run_cost_gate_informational(
            walk_forward["holdout_forecasts"],
            walk_forward["holdout_actuals"],
            block_length=bootstrap_block_length,
            resamples=bootstrap_resamples,
            seed=bootstrap_seed,
        )

        # Verdict against the preregistered acceptance criteria.
        primary_adjusted_p = holm[0]["adjusted_p_value"]
        primary_partial_r2 = primary["partial_r_squared"]
        criteria = {
            "holm_adjusted_primary_p_below_0.05": bool(primary_adjusted_p < 0.05),
            "primary_partial_r_squared_at_least_0.005": bool(
                primary_partial_r2 is not None
                and primary_partial_r2 >= spec.minimum_effect_size
            ),
            "holdout_oos_incremental_r_squared_above_0": bool(
                holdout_oos_r2 is not None and holdout_oos_r2 > 0
            ),
        }
        # The cost gate is informational only (study 003's precedent):
        # it carries no verdict weight and is recorded under
        # cost_gate_informational, not in the criteria above.
        metrics: dict[str, Any] = {
            "panel": {
                "daily_rows": int(panel.returns.shape[0]),
                "daily_first": panel.returns.index[0].isoformat(),
                "daily_last": panel.returns.index[-1].isoformat(),
                "daily_dropped_close_rows": panel.dropped_close_rows,
                "daily_dropped_return_rows": panel.dropped_return_rows,
                "frame_rows": int(frame.shape[0]),
                "frame_first": frame.index[0].isoformat(),
                "frame_last": frame.index[-1].isoformat(),
                "baa_lag_steps": baa_lag_steps,
                "spx_lag_steps": spx_lag_steps,
                "guard_lag_steps": guard_lag_steps,
                "guard_misaligned_rows": guard_misaligned_rows,
            },
            "naive_scan": [
                {
                    "lag_steps": item.lag_steps,
                    "observations": item.observations,
                    "correlation": item.correlation,
                }
                for item in scan
            ],
            "tests": {
                "daily_baa10y_dgs10": primary,
                "daily_baa10y_dgs10_no_factor": primary_no_factor,
                "daily_baa10y_dgs10_naive": naive,
                "daily_dgs10_baa10y_reverse": reverse,
                "daily_baa_dgs10_decomposition": decomposition[
                    "lagged_baa_regression"
                ],
            },
            "holm": holm,
            "walk_forward": {
                key: value
                for key, value in walk_forward.items()
                if key
                not in (
                    "holdout_test_indices",
                    "holdout_forecasts",
                    "holdout_actuals",
                )
            },
            "cost_gate_informational": cost_gate,
            "subperiod_stability": subperiods_result,
            "decomposition": {
                "predictor_guard_correlation": decomposition[
                    "predictor_guard_correlation"
                ],
                "predictor_guard_observations": decomposition[
                    "predictor_guard_observations"
                ],
                "dgs10_change_autocorrelations": decomposition[
                    "dgs10_change_autocorrelations"
                ],
            },
            "verdict": {
                "criteria": criteria,
                "supported": bool(all(criteria.values())),
            },
        }
        return metrics

    return experiment


def main() -> None:
    registry = HypothesisRegistry(ROOT / "hypotheses")
    registration = registry.get(HYPOTHESIS_ID, version=HYPOTHESIS_VERSION)
    spec = registration.spec
    code_revision = git_head_revision(REPO_ROOT)
    if code_revision is None:
        raise RuntimeError("could not determine the git HEAD revision")
    daily, observations, manifest_info = load_panels()
    print(
        f"daily panel: {daily.row_count} rows, "
        f"{daily.first_time.date()} to {daily.last_time.date()}, "
        f"{daily.dropped_return_rows} dropped return rows"
    )
    trial_spec = build_trial_spec(
        spec,
        hypothesis_fingerprint=registration.spec_fingerprint,
        data_fingerprint=manifest_info["manifest_sha256"],
        code_revision=code_revision,
    )
    runner = ExperimentRunner(ROOT / "trials.jsonl", registry)
    receipt = runner.run(
        trial_spec,
        build_experiment(daily, observations, spec),
    )
    print(f"trial {receipt.trial_id} completed: record {receipt.record_hash}")
    metrics = receipt.metrics
    primary = metrics["tests"]["daily_baa10y_dgs10"]
    print(
        f"primary: coefficient {primary['coefficient']:.6f}, "
        f"p {primary['p_value']:.4g}, "
        f"partial R2 {primary['partial_r_squared']}"
    )
    print(f"holm: {metrics['holm']}")
    print(
        "holdout OOS incremental R2: "
        f"{metrics['walk_forward']['holdout_oos_incremental_r_squared']}"
    )
    print(f"cost gate (informational): {metrics['cost_gate_informational']}")
    print(f"decomposition: {metrics['decomposition']}")
    print(
        "guard misaligned rows: "
        f"{metrics['panel']['guard_misaligned_rows']} of "
        f"{metrics['panel']['frame_rows']}"
    )
    print(f"verdict supported: {metrics['verdict']['supported']}")


if __name__ == "__main__":
    main()
