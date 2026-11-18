"""Run trial T0015 for hypothesis H0012 v1 (CPI transmission).

Run after preregistration and fetching, from the repo root, with a
clean worktree (the trial records the HEAD commit as its code
revision):

    .venv/bin/python research/publication-lag-007/run_trial_h0012.py

Trial T0014 (the first attempt) failed inside the experiment on the
skipped-release guard: the guard checked all 71 calendar releases,
including the out-of-sample November 2026 release (2026-12-10),
whose MoM is undefined only because the value is not published yet
at fetch time — not a data error. No T0014 results were computed or
recorded. The guard now checks in-sample releases only (release date
on or before the sample end 2026-11-18), and the trial re-runs here
as T0015 (trial IDs are unique per attempt).

The trial binds the preregistered H0012 v1 spec, the fetch manifest's
SHA-256 as the data fingerprint, and a canonical-JSON hash of the
analysis configuration. It tests whether the latest published CPI
month-on-month value (FRED CPIAUCSL, aligned by release date as a
step function) predicts next-day returns:

1. the preregistered three-test Holm family: (A) CPI step -> next-day
   SPX return (daily, HAC max lag 21); (B) the same on release-day
   rows only (HAC max lag 5); (C) CPI step -> next-day BTC return
   (daily, HAC max lag 21);
2. a purged walk-forward out-of-sample evaluation of the A model
   (initial train 365 days, test 90 days, 1-day embargo), scored on
   holdout rows (decision times from 2025-01-02);
3. an informational cost gate (study 003's treatment): the gross
   sign-rule edge on holdout OOS forecasts, no costs applied — the
   S&P 500 index is not directly tradable and no free SPX futures or
   ETF price series is used, so the cost gate is not a verdict
   criterion;
4. descriptives (not in the family): the same three regressions with
   the naive reference-month-aligned CPI predictor (the month's value
   treated as known during the month, 2-6 weeks of lookahead), to
   quantify the lookahead bias. Coefficients and partial R-squared
   only — no p-values, following the repo's descriptive convention.

Timing conventions (preregistered): the step is evaluated at each
bar's close date. For SPX the close date is the trading date (a
release on D at 08:30 ET is knowable at the 16:00 ET close, so
release-day rows carry the fresh print). For OKX daily bars (open
16:00 UTC) the close date is the open date plus one day. Regression
row j predicts the target return over bar j+1 from predictors known
at bar j's close (the CPI step at bar j's close date and the target's
own lagged return).

Effective-sample caveat (preregistered): the step predictor takes
only about 70 distinct values over 2021-2026 (one per release); the
roughly 1,460 daily regression rows are NOT the effective sample
size. The release-day subsample test (B) is the cleaner read.

One machinery guard is enforced inside the experiment: the only
release without a usable MoM must be the November 2025 CPI (released
2025-12-18), whose base month October 2025 was never published. Any
other skipped release would indicate a calendar or data error.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from myquant.canonical import canonical_json
from myquant.contracts import MultiplicityCorrection
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
    ols_fit,
    purged_walk_forward_split_report,
)
from myquant.studies.macro import CPIRelease, load_cpi_calendar
from myquant.studies.panel import SynchronizedPanel, build_synchronized_panel
from myquant.studies.publication_lag import (
    build_cpi_naive_function,
    build_cpi_step_function,
    cpi_mom_log_changes,
    cpi_release_day_flags,
    cpi_releases_without_mom,
)
from myquant.studies.regime import NestedLeadLagTest, nested_lead_lag_test

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "publication-lag-007"
STUDY_006_ROOT = REPO_ROOT / "research" / "macro-windows-006"

HYPOTHESIS_ID = "H0012"
HYPOTHESIS_VERSION = 1
TRIAL_ID = "T0015"

SPX = "index:sp500"
BTC = "crypto:btc-usdt-perp"
CPI = "macro:cpi-mom"

SPX_START = datetime(2021, 1, 4, 21, 0, tzinfo=UTC)
SAMPLE_END = datetime(2026, 11, 18, 21, 0, tzinfo=UTC)
SAMPLE_END_DATE = date(2026, 11, 18)

# The only in-sample release without a usable MoM: the November 2025
# CPI (released 2025-12-18), whose base month October 2025 was never
# published. Enforced as a machinery guard inside the experiment.
# The out-of-sample November 2026 release (2026-12-10) also has no
# usable MoM — its value is not published yet at fetch time — and is
# excluded from the guard by the in-sample cutoff.
EXPECTED_SKIPPED_REFERENCE_MONTHS = ("2025-11",)

# The preregistered three-test family, in preregistered order: the
# primary test first.
FAMILY: tuple[str, ...] = (
    "spx_daily",
    "spx_release_day",
    "btc_daily",
)


def load_data() -> tuple[
    SynchronizedPanel,
    SynchronizedPanel,
    pd.Series,
    tuple[CPIRelease, ...],
    dict[str, str],
]:
    """Load the SPX and BTC panels, CPI levels and the CPI calendar."""
    manifest_path = ROOT / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    decision_time = datetime.fromisoformat(manifest["fetched_at"])
    if decision_time.tzinfo is None:
        decision_time = decision_time.replace(tzinfo=UTC)

    source_registry = SourceRegistry(ROOT / "sources")
    store = ParquetPITStore(CACHE_ROOT / "pit-1d", source_registry)
    okx_store = ParquetPITStore(CACHE_ROOT / "pit-okx-1d", source_registry)
    observations = store.query_as_of(
        decision_time,
        instrument_ids={SPX, CPI},
        fields={"close"},
    )
    spx_observations = [
        item
        for item in observations
        if item.instrument_id == SPX
        and SPX_START <= item.event_time <= SAMPLE_END
    ]
    spx_panel = build_synchronized_panel(
        spx_observations,
        instruments=(SPX,),
        field="close",
    )
    cpi_observations = [
        item for item in observations if item.instrument_id == CPI
    ]
    cpi_levels = pd.Series(
        {item.event_time: item.value for item in cpi_observations},
        dtype="float64",
    )
    cpi_levels.index = pd.DatetimeIndex(cpi_levels.index, tz="UTC")
    cpi_levels = cpi_levels.sort_index()
    btc_observations = okx_store.query_as_of(decision_time)
    btc_panel = build_synchronized_panel(
        btc_observations,
        instruments=(BTC,),
        field="close",
    )
    cpi_document = json.loads(
        (STUDY_006_ROOT / "cpi_calendar.json").read_text(encoding="utf-8")
    )
    releases = load_cpi_calendar(cpi_document)
    manifest_info = {
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "fetched_at": manifest["fetched_at"],
    }
    return spx_panel, btc_panel, cpi_levels, releases, manifest_info


def build_spx_rows(
    returns: pd.Series,
    step: pd.Series,
    naive: pd.Series,
    release_flags: pd.Series,
) -> pd.DataFrame:
    """SPX regression rows: row j predicts the return over bar j+1.

    Predictors known at bar j's close: the CPI step at close date j
    and SPX's own lagged return (the return over bar j). Rows before
    the first release (undefined step) are dropped.
    """
    values = returns.to_numpy(dtype=float)
    rows = pd.DataFrame(
        {
            "target_next": values[1:],
            "target_lag": values[:-1],
            "cpi_step": step.reindex(returns.index[:-1]).to_numpy(dtype=float),
            "cpi_naive": naive.reindex(returns.index[:-1]).to_numpy(dtype=float),
            "release_day": release_flags.reindex(returns.index[:-1]).to_numpy(
                dtype=bool
            ),
        },
        index=returns.index[:-1],
    )
    return rows.dropna(subset=["cpi_step"])


def build_btc_rows(
    returns: pd.Series,
    step: pd.Series,
    naive: pd.Series,
) -> pd.DataFrame:
    """BTC regression rows: the step is evaluated at each bar's close date.

    OKX daily bars open at 16:00 UTC; a bar's close date is its open
    date plus one day. A CPI release at 08:30 ET on date D is knowable
    at any close on D, so the step for bar j is the step at bar j's
    close date (open date + 1).
    """
    close_dates = returns.index + pd.Timedelta(days=1)
    values = returns.to_numpy(dtype=float)
    rows = pd.DataFrame(
        {
            "target_next": values[1:],
            "target_lag": values[:-1],
            "cpi_step": step.reindex(close_dates[:-1]).to_numpy(dtype=float),
            "cpi_naive": naive.reindex(close_dates[:-1]).to_numpy(dtype=float),
        },
        index=returns.index[:-1],
    )
    return rows.dropna(subset=["cpi_step"])


def _test_metrics(result: NestedLeadLagTest) -> dict[str, Any]:
    if result.p_value is None:
        raise ValueError("HAC p-value is unavailable; cannot form the test family")
    return {
        "observations": result.observations,
        "coefficient": result.coefficient,
        "standard_error": result.standard_error,
        "t_statistic": result.t_statistic,
        "p_value": result.p_value,
        "partial_r_squared": result.partial_r_squared,
        "incremental_r_squared": result.incremental_r_squared,
        "base_r_squared": result.base_r_squared,
        "augmented_r_squared": result.augmented_r_squared,
    }


def _descriptive_metrics(result: NestedLeadLagTest) -> dict[str, Any]:
    """Descriptive regression metrics: no p-values (repo convention)."""
    return {
        "observations": result.observations,
        "coefficient": result.coefficient,
        "standard_error": result.standard_error,
        "partial_r_squared": result.partial_r_squared,
        "incremental_r_squared": result.incremental_r_squared,
        "base_r_squared": result.base_r_squared,
        "augmented_r_squared": result.augmented_r_squared,
    }


def _lead_lag_test(
    rows: pd.DataFrame,
    *,
    predictor: str,
    max_hac_lag: int,
) -> NestedLeadLagTest:
    return nested_lead_lag_test(
        rows["target_next"].to_numpy(dtype=float),
        {"target_lag": rows["target_lag"].to_numpy(dtype=float)},
        {predictor: rows[predictor].to_numpy(dtype=float)},
        effect_name=predictor,
        max_hac_lag=max_hac_lag,
    )


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
    rows: pd.DataFrame,
    *,
    initial_train_size: int,
    test_size: int,
    embargo_days: int,
    holdout_start: datetime,
) -> dict[str, Any]:
    """Purged walk-forward OOS evaluation of the A model (SPX daily).

    Base model: SPX own lag only. Augmented model: base + CPI step.
    Regression row j uses predictors known at bar j's close to
    forecast the SPX return over bar j+1, known at bar j+1's close —
    one day after the decision time. Hence label_end = decision_time
    + 1 day. Scoring is reported on all test rows and on holdout test
    rows (the preregistered acceptance criterion).
    """
    target = rows["target_next"].to_numpy(dtype=float)
    predictors = {
        "target_lag": rows["target_lag"].to_numpy(dtype=float),
        "cpi_step": rows["cpi_step"].to_numpy(dtype=float),
    }
    decision_times = [item.to_pydatetime() for item in rows.index]
    label_ends = [item + timedelta(days=1) for item in decision_times]
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
            {"target_lag": predictors["target_lag"][train]},
        )
        augmented_fit = ols_fit(
            target[train],
            {name: values[train] for name, values in predictors.items()},
        )
        baseline_forecasts[test] = _ols_predict(
            base_fit,
            {"target_lag": predictors["target_lag"][test]},
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

    def restricted_folds(
        predicate: Any,
    ) -> list[WalkForwardFold]:
        restricted: list[WalkForwardFold] = []
        for fold in folds:
            kept = tuple(
                index for index in fold.test_indices if predicate(index)
            )
            if not kept:
                continue
            restricted.append(
                WalkForwardFold(
                    fold_number=fold.fold_number,
                    train_indices=fold.train_indices,
                    test_indices=kept,
                    purged_indices=fold.purged_indices,
                    embargoed_indices=fold.embargoed_indices,
                    test_start_time=decision_times[kept[0]],
                    test_last_time=decision_times[kept[-1]],
                )
            )
        return restricted

    holdout_folds = restricted_folds(
        lambda index: decision_times[index] >= holdout_start
    )
    holdout_evaluation = evaluate_walk_forward_forecasts(
        target,
        baseline_forecasts,
        augmented_forecasts,
        folds=holdout_folds,
    )
    holdout_test_rows = [
        index for fold in holdout_folds for index in fold.test_indices
    ]
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
    while positioned). No costs are applied: the S&P 500 index is not
    directly tradable and no free SPX futures or ETF price series is
    used in this study. The gross edge is an upper bound on any
    tradable edge, not a verdict criterion.
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
        "note": (
            "Informational only: no costs applied. The S&P 500 index is "
            "not directly tradable and no free SPX futures or ETF price "
            "series is used. Not a verdict criterion."
        ),
    }


def analysis_config(spec: HypothesisSpec) -> dict[str, Any]:
    """The exact analysis configuration, hashed as the config fingerprint."""
    return {
        "fixed_parameters": list(spec.fixed_parameters),
        "test_family": list(FAMILY),
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
        "trial_script": "research/publication-lag-007/run_trial_h0012.py",
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
            "Release-day-aligned CPI transmission: the latest published "
            "CPI MoM (step function) predicts next-day SPX returns "
            "(daily and release-day subsample) and next-day BTC returns"
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


def build_experiment(
    spx_panel: SynchronizedPanel,
    btc_panel: SynchronizedPanel,
    cpi_levels: pd.Series,
    releases: tuple[CPIRelease, ...],
    spec: HypothesisSpec,
) -> Any:
    """Build the trial callback closing over the loaded panels."""

    def experiment(trial_spec: TrialSpec) -> dict[str, Any]:
        params = {item.name: item.value for item in trial_spec.parameters}
        daily_max_hac_lag = int(params["daily_max_hac_lag"])
        subsample_max_hac_lag = int(params["subsample_max_hac_lag"])
        btc_max_hac_lag = int(params["btc_max_hac_lag"])
        walk_forward_initial_train = int(params["walk_forward_initial_train"])
        walk_forward_test_size = int(params["walk_forward_test_size"])
        walk_forward_embargo_days = int(params["walk_forward_embargo_days"])
        bootstrap_block_length = int(params["bootstrap_block_length"])
        bootstrap_resamples = int(params["bootstrap_resamples"])
        bootstrap_seed = int(params["bootstrap_seed"])

        mom_changes = cpi_mom_log_changes(cpi_levels)

        # Machinery guard: the only in-sample release without a usable
        # MoM is the November 2025 CPI (base month October 2025 never
        # published). Any other in-sample skipped release is a data
        # error. The out-of-sample November 2026 release (2026-12-10)
        # has no usable MoM either — its value is not published yet at
        # fetch time — and is excluded from the guard by the cutoff.
        in_sample_releases = tuple(
            item for item in releases if item.release_date <= SAMPLE_END_DATE
        )
        skipped = cpi_releases_without_mom(in_sample_releases, mom_changes)
        skipped_months = tuple(item.reference_month for item in skipped)
        if skipped_months != EXPECTED_SKIPPED_REFERENCE_MONTHS:
            raise ValueError(
                f"in-sample releases without a usable MoM: {skipped_months}, "
                f"expected {EXPECTED_SKIPPED_REFERENCE_MONTHS}"
            )
        out_of_sample_skipped = cpi_releases_without_mom(
            tuple(
                item
                for item in releases
                if item.release_date > SAMPLE_END_DATE
            ),
            mom_changes,
        )

        spx_returns = spx_panel.returns[SPX]
        spx_step = build_cpi_step_function(
            releases, mom_changes, spx_returns.index
        )
        spx_naive = build_cpi_naive_function(mom_changes, spx_returns.index)
        release_flags = cpi_release_day_flags(
            spx_returns.index,
            [item.release_date for item in releases],
        )
        spx_rows = build_spx_rows(
            spx_returns, spx_step, spx_naive, release_flags
        )
        spx_release_rows = spx_rows[spx_rows["release_day"]]

        btc_returns = btc_panel.returns[BTC]
        btc_close_dates = btc_returns.index + pd.Timedelta(days=1)
        btc_step = build_cpi_step_function(
            releases, mom_changes, btc_close_dates
        )
        btc_naive = build_cpi_naive_function(mom_changes, btc_close_dates)
        btc_rows = build_btc_rows(btc_returns, btc_step, btc_naive)

        # The preregistered three-test Holm family.
        tests: dict[str, Any] = {
            "spx_daily": _test_metrics(
                _lead_lag_test(
                    spx_rows,
                    predictor="cpi_step",
                    max_hac_lag=daily_max_hac_lag,
                )
            ),
            "spx_release_day": _test_metrics(
                _lead_lag_test(
                    spx_release_rows,
                    predictor="cpi_step",
                    max_hac_lag=subsample_max_hac_lag,
                )
            ),
            "btc_daily": _test_metrics(
                _lead_lag_test(
                    btc_rows,
                    predictor="cpi_step",
                    max_hac_lag=btc_max_hac_lag,
                )
            ),
        }
        adjusted = adjust_pvalues(
            [tests[name]["p_value"] for name in FAMILY],
            method=MultiplicityCorrection.HOLM,
            target_error_rate=spec.target_error_rate,
        )
        holm = [
            {
                "test": name,
                "raw_p_value": item.raw_p_value,
                "adjusted_p_value": item.adjusted_p_value,
                "reject": item.reject,
            }
            for name, item in zip(FAMILY, adjusted, strict=True)
        ]

        # Walk-forward OOS evaluation of the A model (SPX daily).
        walk_forward = run_walk_forward(
            spx_rows,
            initial_train_size=walk_forward_initial_train,
            test_size=walk_forward_test_size,
            embargo_days=walk_forward_embargo_days,
            holdout_start=spec.holdout_window.start,
        )
        cost_gate = run_cost_gate_informational(
            walk_forward["holdout_forecasts"],
            walk_forward["holdout_actuals"],
            block_length=bootstrap_block_length,
            resamples=bootstrap_resamples,
            seed=bootstrap_seed,
        )

        # Descriptive: naive reference-month alignment (lookahead).
        spx_naive_rows = spx_rows.dropna(subset=["cpi_naive"])
        spx_naive_release_rows = spx_naive_rows[spx_naive_rows["release_day"]]
        btc_naive_rows = btc_rows.dropna(subset=["cpi_naive"])
        descriptive_naive = {
            "spx_daily": _descriptive_metrics(
                _lead_lag_test(
                    spx_naive_rows,
                    predictor="cpi_naive",
                    max_hac_lag=daily_max_hac_lag,
                )
            ),
            "spx_release_day": _descriptive_metrics(
                _lead_lag_test(
                    spx_naive_release_rows,
                    predictor="cpi_naive",
                    max_hac_lag=subsample_max_hac_lag,
                )
            ),
            "btc_daily": _descriptive_metrics(
                _lead_lag_test(
                    btc_naive_rows,
                    predictor="cpi_naive",
                    max_hac_lag=btc_max_hac_lag,
                )
            ),
            "note": (
                "Naive reference-month alignment: the reference month's "
                "MoM treated as known during the month (2-6 weeks of "
                "lookahead). Descriptive only, not in the test family; "
                "coefficients and partial R-squared only, no p-values. "
                "Rows in October-November 2025 have no naive value "
                "(their reference months' MoM is undefined) and are "
                "dropped."
            ),
        }

        # Verdict against the preregistered acceptance criteria.
        primary = tests["spx_daily"]
        primary_adjusted_p = holm[0]["adjusted_p_value"]
        criteria = {
            "holm_adjusted_primary_p_below_0.05": bool(primary_adjusted_p < 0.05),
            "primary_partial_r_squared_at_least_0.005": bool(
                primary["partial_r_squared"] is not None
                and primary["partial_r_squared"] >= 0.005
            ),
            "holdout_oos_incremental_r_squared_above_0": bool(
                walk_forward["holdout_oos_incremental_r_squared"] > 0
            ),
        }
        metrics: dict[str, Any] = {
            "panel": {
                "daily_rows": int(spx_panel.row_count),
                "daily_first": spx_panel.first_time.isoformat(),
                "daily_last": spx_panel.last_time.isoformat(),
                "daily_dropped_close_rows": spx_panel.dropped_close_rows,
                "daily_dropped_return_rows": spx_panel.dropped_return_rows,
                "daily_regression_rows": int(spx_rows.shape[0]),
                "daily_regression_first": spx_rows.index[0].isoformat(),
                "daily_regression_last": spx_rows.index[-1].isoformat(),
                "daily_dropped_rows_before_first_release": int(
                    spx_panel.row_count - 1 - spx_rows.shape[0]
                ),
                "btc_daily_rows": int(btc_panel.row_count),
                "btc_daily_first": btc_panel.first_time.isoformat(),
                "btc_daily_last": btc_panel.last_time.isoformat(),
                "btc_daily_dropped_close_rows": btc_panel.dropped_close_rows,
                "btc_daily_dropped_return_rows": (
                    btc_panel.dropped_return_rows
                ),
                "btc_daily_regression_rows": int(btc_rows.shape[0]),
                "btc_daily_regression_first": btc_rows.index[0].isoformat(),
                "btc_daily_regression_last": btc_rows.index[-1].isoformat(),
                "cpi_distinct_step_values": int(
                    spx_step.dropna().nunique()
                ),
                "cpi_releases_in_sample": int(
                    sum(
                        1
                        for item in releases
                        if date(2021, 1, 13)
                        <= item.release_date
                        <= date(2026, 11, 10)
                    )
                ),
                "release_day_rows": int(spx_release_rows.shape[0]),
                "skipped_releases_without_mom": [
                    {
                        "reference_month": item.reference_month,
                        "release_date": item.release_date.isoformat(),
                    }
                    for item in skipped
                ],
                "out_of_sample_skipped_releases_without_mom": [
                    {
                        "reference_month": item.reference_month,
                        "release_date": item.release_date.isoformat(),
                    }
                    for item in out_of_sample_skipped
                ],
            },
            "tests": tests,
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
            "descriptive_naive": descriptive_naive,
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
    spx_panel, btc_panel, cpi_levels, releases, manifest_info = load_data()
    print(
        f"SPX panel: {spx_panel.row_count} return rows, "
        f"{spx_panel.first_time.date()} to {spx_panel.last_time.date()}"
    )
    print(
        f"BTC panel: {btc_panel.row_count} return rows, "
        f"{btc_panel.first_time.date()} to {btc_panel.last_time.date()}"
    )
    print(
        f"CPI levels: {len(cpi_levels)} monthly rows, "
        f"{cpi_levels.index[0].date()} to {cpi_levels.index[-1].date()}"
    )
    print(f"CPI calendar: {len(releases)} releases")
    trial_spec = build_trial_spec(
        spec,
        hypothesis_fingerprint=registration.spec_fingerprint,
        data_fingerprint=manifest_info["manifest_sha256"],
        code_revision=code_revision,
    )
    runner = ExperimentRunner(ROOT / "trials.jsonl", registry)
    receipt = runner.run(
        trial_spec,
        build_experiment(spx_panel, btc_panel, cpi_levels, releases, spec),
    )
    print(f"trial {receipt.trial_id} completed: record {receipt.record_hash}")
    metrics = receipt.metrics
    primary = metrics["tests"]["spx_daily"]
    print(
        f"primary (CPI step -> next-day SPX): coef {primary['coefficient']:.6f}, "
        f"partial R2 {primary['partial_r_squared']:.6f}, "
        f"p {primary['p_value']:.4g}"
    )
    print(f"holm: {metrics['holm']}")
    print(
        "holdout OOS incremental R2: "
        f"{metrics['walk_forward']['holdout_oos_incremental_r_squared']:.6f}"
    )
    print(f"verdict supported: {metrics['verdict']['supported']}")


if __name__ == "__main__":
    main()
