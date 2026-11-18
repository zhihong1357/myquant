"""Run trial T0004 for hypothesis H0004 v2 (rates vol -> equity vol).

Run after preregistration (v2 amendment) and fetching, from the repo
root, with a clean worktree (the trial records the HEAD commit as its
code revision):

    .venv/bin/python research/move-vix-003/run_trial.py

The trial binds the preregistered H0004 v2 spec, the fetch manifest's
SHA-256 as the data fingerprint, and a canonical-JSON hash of the
analysis configuration. It executes the six-step thesis flow in one
trial:

1. naive lead-lag scan (descriptive, lags 0-5);
2. synchronized daily panel (no forward filling) plus a Friday-close
   weekly resample;
3. partial lead-lag tests with the same-day SPX factor control, plus
   no-factor upper-bound controls;
4. weekly robustness test with the same control structure;
5. purged walk-forward out-of-sample evaluation, scored in full and on
   the preregistered holdout window only;
6. cost gate (INFORMATIONAL): gross sign-rule edge on holdout OOS
   augmented forecasts with a block-bootstrap CI. No costs are applied:
   volatility indices are not tradable and VIX futures roll costs
   cannot be measured from free data, so this is not a verdict
   criterion; the holdout OOS incremental R-squared carries the
   economic weight.

Descriptives (not in the test family): the reverse placebo
(VIX->TYVIX), sub-period stability of the primary coefficient, the
rolling-percentile check of the thesis's MOVE-99th / VXN-34th claim,
the trailing-z-score robustness, and the factor-timing sensitivity
(primary test with the SPX factor measured on the target day, which is
not forecastable). The runner records the trial (including failures)
in the hash-chained ledger trials.jsonl; it does not decide
acceptance.
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
    lead_lag_scan,
    ols_fit,
    partial_lead_lag,
    purged_walk_forward_split_report,
)
from myquant.studies.panel import SynchronizedPanel, build_synchronized_panel

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "move-vix-003"

HYPOTHESIS_ID = "H0004"
HYPOTHESIS_VERSION = 2
TRIAL_ID = "T0004"

TYVIX = "index:tyvix"
VIX = "index:vix"
VXN = "index:vxn"
SPX = "index:sp500"
DGS10 = "rates:us-10y-yield"
BAA10Y = "credit:baa-10y-spread"
DAILY_INSTRUMENTS = (TYVIX, VIX, VXN, SPX, DGS10, BAA10Y)

# Preregistered sub-periods (calendar-year ranges, 21:00 UTC closes).
SUBPERIODS: tuple[tuple[str, datetime, datetime], ...] = (
    (
        "2003-2007",
        datetime(2003, 1, 1, 21, 0, tzinfo=UTC),
        datetime(2008, 1, 1, 21, 0, tzinfo=UTC),
    ),
    (
        "2008-2012",
        datetime(2008, 1, 1, 21, 0, tzinfo=UTC),
        datetime(2013, 1, 1, 21, 0, tzinfo=UTC),
    ),
    (
        "2013-2017",
        datetime(2013, 1, 1, 21, 0, tzinfo=UTC),
        datetime(2018, 1, 1, 21, 0, tzinfo=UTC),
    ),
    (
        "2018-2020",
        datetime(2018, 1, 1, 21, 0, tzinfo=UTC),
        datetime(2021, 1, 1, 21, 0, tzinfo=UTC),
    ),
)


def load_panels() -> tuple[SynchronizedPanel, dict[str, Any]]:
    """Load the daily panel from the local PIT store."""
    manifest_path = ROOT / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    decision_time = datetime.fromisoformat(manifest["fetched_at"])
    if decision_time.tzinfo is None:
        decision_time = decision_time.replace(tzinfo=UTC)

    source_registry = SourceRegistry(ROOT / "sources")
    daily_store = ParquetPITStore(CACHE_ROOT / "pit-1d", source_registry)
    daily = build_synchronized_panel(
        daily_store.query_as_of(
            decision_time,
            instrument_ids=set(DAILY_INSTRUMENTS),
            fields={"close"},
        ),
        instruments=DAILY_INSTRUMENTS,
    )
    manifest_info = {
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "fetched_at": manifest["fetched_at"],
    }
    return daily, manifest_info


def weekly_log_changes(daily_closes: pd.DataFrame) -> pd.DataFrame:
    """Friday-close to Friday-close log changes.

    Each week takes its last trading day's close (Friday, or Thursday
    when Friday is a holiday). Returns are week-over-week log changes.
    The resample labels bins at Friday 00:00 UTC; the index is shifted
    to 21:00 UTC to keep the daily close-time convention.
    """
    weekly_closes = daily_closes.resample("W-FRI").last()
    weekly_closes.index = weekly_closes.index + pd.Timedelta(hours=21)
    changes = np.log(weekly_closes).diff().dropna(how="any")
    return changes


def analysis_config(spec: HypothesisSpec) -> dict[str, Any]:
    """The exact analysis configuration, hashed as the config fingerprint."""
    return {
        "fixed_parameters": list(spec.fixed_parameters),
        "test_family": [
            "daily_tyvix_vix",
            "daily_tyvix_vxn",
            "weekly_tyvix_vix",
        ],
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
        "trial_script": "research/move-vix-003/run_trial.py",
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
            "TYVIX->VIX/VXN transmission: partial lead-lag family, purged "
            "walk-forward OOS evaluation and informational cost assessment"
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
    factor_name: str | None,
    factor: np.ndarray | None,
    max_hac_lag: int,
) -> dict[str, Any]:
    """One partial lead-lag test; returns JSON-safe metrics."""
    factors = None if factor is None else {factor_name: factor}
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
    returns: pd.DataFrame,
    *,
    initial_train_size: int,
    test_size: int,
    embargo_days: int,
    holdout_start: datetime,
) -> dict[str, Any]:
    """Purged walk-forward OOS evaluation of the TYVIX->VIX augmented model.

    Regression row j uses predictors known at day j's close to forecast
    the VIX log change over day j+1, which is known at day j+1's close.
    Label ends are the exact next-row event times, so weekends and
    holidays are handled exactly (a Friday row's label ends Monday).
    """
    tyvix = returns[TYVIX].to_numpy(dtype=float)
    vix = returns[VIX].to_numpy(dtype=float)
    spx = returns[SPX].to_numpy(dtype=float)
    target = vix[1:]
    predictors = {
        "target_lag": vix[:-1],
        "spx": spx[:-1],
        "tyvix": tyvix[:-1],
    }
    decision_times = [item.to_pydatetime() for item in returns.index[:-1]]
    label_ends = [item.to_pydatetime() for item in returns.index[1:]]
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
                "spx": predictors["spx"][train],
            },
        )
        augmented_fit = ols_fit(
            target[train],
            {name: values[train] for name, values in predictors.items()},
        )
        baseline_forecasts[test] = _ols_predict(
            base_fit,
            {name: values[test] for name, values in predictors.items() if name != "tyvix"},
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
    while positioned). No costs are applied: volatility indices are not
    tradable, VIX exposure requires VIX futures, and futures roll costs
    cannot be measured from free data (Yahoo VX=F returns no data). The
    gross edge is an upper bound on any tradable edge, not a verdict
    criterion.
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
            "Informational only: no costs applied. Volatility indices "
            "are not tradable; VIX futures roll costs are unmeasurable "
            "from free data. Not a verdict criterion."
        ),
    }


def run_subperiod_stability(
    returns: pd.DataFrame,
    *,
    max_hac_lag: int,
) -> dict[str, Any]:
    """Descriptive primary-test coefficient by preregistered sub-period.

    Each sub-period slices the daily log-change series to its date range
    and re-runs the primary partial lead-lag test. Coefficients and
    partial R-squared only — no p-values, not in the test family.
    """
    index = returns.index
    tyvix = returns[TYVIX].to_numpy(dtype=float)
    vix = returns[VIX].to_numpy(dtype=float)
    spx = returns[SPX].to_numpy(dtype=float)
    subperiods: dict[str, Any] = {}
    for label, start, end in SUBPERIODS:
        mask = (index >= start) & (index < end)
        result = partial_lead_lag(
            tyvix[mask],
            vix[mask],
            lag_steps=1,
            common_factors={"spx": spx[mask]},
            max_hac_lag=max_hac_lag,
        )
        subperiods[label] = {
            "observations": result.observations,
            "coefficient": result.source_effect.estimate,
            "standard_error": result.source_effect.standard_error,
            "partial_r_squared": result.partial_r_squared,
        }
    return subperiods


def _trailing_percentile(values: pd.Series, window: int) -> pd.Series:
    """Trailing percentile rank of each value within its own window.

    The percentile is the share of the previous window-1 values strictly
    below the current value (point-in-time: only past values are used).
    """
    return values.rolling(window).apply(
        lambda w: float((w[:-1] < w[-1]).mean()),
        raw=True,
    )


def run_percentile_descriptive(
    closes: pd.DataFrame,
    returns: pd.DataFrame,
    *,
    window: int,
) -> dict[str, Any]:
    """Descriptive check of the thesis's MOVE-99th / VXN-34th claim.

    Trailing 252-day percentile ranks of TYVIX and VXN levels: how often
    is rates volatility near its trailing high while equity volatility
    sits near its trailing middle, and what happened to VIX next?
    Means only — no p-values, not in the test family.
    """
    tyvix_pct = _trailing_percentile(closes[TYVIX], window)
    vxn_pct = _trailing_percentile(closes[VXN], window)
    vix_ret = returns[VIX]
    frame = pd.DataFrame(
        {
            "tyvix_pct": tyvix_pct,
            "vxn_pct": vxn_pct,
            "vix_next_1d": vix_ret.shift(-1),
            "vix_next_5d": vix_ret.rolling(5).sum().shift(-5),
        }
    ).dropna()
    summaries: dict[str, Any] = {
        "window_days": window,
        "rows": int(frame.shape[0]),
    }
    for label, tyvix_min, vxn_max in (
        ("broad_tyvix99_vxn50", 0.99, 0.50),
        ("strict_tyvix99_vxn34", 0.99, 0.34),
    ):
        subset = frame[
            (frame["tyvix_pct"] >= tyvix_min) & (frame["vxn_pct"] <= vxn_max)
        ]
        summaries[label] = {
            "days": int(subset.shape[0]),
            "share_of_sample": (
                float(subset.shape[0] / frame.shape[0]) if frame.shape[0] else 0.0
            ),
            "mean_vix_next_1d": (
                float(subset["vix_next_1d"].mean()) if not subset.empty else None
            ),
            "mean_vix_next_5d": (
                float(subset["vix_next_5d"].mean()) if not subset.empty else None
            ),
        }
    summaries["percentile_correlation"] = float(
        frame["tyvix_pct"].corr(frame["vxn_pct"])
    )
    return summaries


def _zscore_trailing(values: pd.Series, window: int) -> pd.Series:
    """Trailing z-score using the strictly-prior window (PIT-correct)."""
    mean_prev = values.rolling(window).mean().shift(1)
    std_prev = values.rolling(window).std().shift(1)
    return (values - mean_prev) / std_prev


def run_zscore_sensitivity(
    returns: pd.DataFrame,
    *,
    window: int,
    max_hac_lag: int,
) -> dict[str, Any]:
    """Descriptive primary test on trailing-z-scored log changes.

    Each log-change series is standardized by its trailing 252-day mean
    and standard deviation (strictly prior window). Not in the family.
    """
    frame = pd.DataFrame(
        {
            "tyvix": _zscore_trailing(returns[TYVIX], window),
            "vix": _zscore_trailing(returns[VIX], window),
            "spx": _zscore_trailing(returns[SPX], window),
        }
    ).dropna()
    return _partial_test(
        frame["tyvix"].to_numpy(dtype=float),
        frame["vix"].to_numpy(dtype=float),
        factor_name="spx",
        factor=frame["spx"].to_numpy(dtype=float),
        max_hac_lag=max_hac_lag,
    )


def run_factor_timing_sensitivity(
    returns: pd.DataFrame,
    *,
    max_hac_lag: int,
) -> dict[str, Any]:
    """Descriptive primary test with the SPX factor on the target day.

    The factor is SPX[t+1] (same day as the VIX move being predicted),
    aligned by truncating the arrays: source/target run over t = 0..n-2
    and the factor over t+1 = 1..n-1, so partial_lead_lag pairs
    (TYVIX[t], VIX[t+1], SPX[t+1]). The t+1 control is NOT forecastable
    — this is an explanatory decomposition, not a forecast — and is not
    in the test family.
    """
    tyvix = returns[TYVIX].to_numpy(dtype=float)
    vix = returns[VIX].to_numpy(dtype=float)
    spx = returns[SPX].to_numpy(dtype=float)
    return _partial_test(
        tyvix[:-1],
        vix[:-1],
        factor_name="spx_next",
        factor=spx[1:],
        max_hac_lag=max_hac_lag,
    )


def build_experiment(
    daily: SynchronizedPanel,
    spec: HypothesisSpec,
) -> Any:
    """Build the trial callback closing over the loaded panel."""

    def experiment(trial_spec: TrialSpec) -> dict[str, Any]:
        params = {item.name: item.value for item in trial_spec.parameters}
        daily_max_hac_lag = int(params["daily_max_hac_lag"])
        weekly_max_hac_lag = int(params["weekly_max_hac_lag"])
        bootstrap_block_length = int(params["bootstrap_block_length"])
        bootstrap_resamples = int(params["bootstrap_resamples"])
        bootstrap_seed = int(params["bootstrap_seed"])
        walk_forward_initial_train = int(params["walk_forward_initial_train"])
        walk_forward_test_size = int(params["walk_forward_test_size"])
        walk_forward_embargo_days = int(params["walk_forward_embargo_days"])
        percentile_window = int(params["percentile_window_days"])
        zscore_window = int(params["zscore_window_days"])

        daily_returns = daily.returns
        daily_closes = daily.closes
        weekly_changes = weekly_log_changes(
            daily_closes[[TYVIX, VIX, SPX]]
        )
        tyvix_d = daily_returns[TYVIX].to_numpy(dtype=float)
        vix_d = daily_returns[VIX].to_numpy(dtype=float)
        vxn_d = daily_returns[VXN].to_numpy(dtype=float)
        spx_d = daily_returns[SPX].to_numpy(dtype=float)
        tyvix_w = weekly_changes[TYVIX].to_numpy(dtype=float)
        vix_w = weekly_changes[VIX].to_numpy(dtype=float)
        spx_w = weekly_changes[SPX].to_numpy(dtype=float)

        # Step 1: naive scan (descriptive).
        scan = lead_lag_scan(tyvix_d, vix_d, lag_steps=(0, 1, 2, 3, 4, 5))

        # Steps 3-4: the preregistered three-test family, plus no-factor
        # upper-bound controls.
        primary = _partial_test(
            tyvix_d,
            vix_d,
            factor_name="spx",
            factor=spx_d,
            max_hac_lag=daily_max_hac_lag,
        )
        primary_no_factor = _partial_test(
            tyvix_d,
            vix_d,
            factor_name=None,
            factor=None,
            max_hac_lag=daily_max_hac_lag,
        )
        secondary = _partial_test(
            tyvix_d,
            vxn_d,
            factor_name="spx",
            factor=spx_d,
            max_hac_lag=daily_max_hac_lag,
        )
        secondary_no_factor = _partial_test(
            tyvix_d,
            vxn_d,
            factor_name=None,
            factor=None,
            max_hac_lag=daily_max_hac_lag,
        )
        robustness = _partial_test(
            tyvix_w,
            vix_w,
            factor_name="spx",
            factor=spx_w,
            max_hac_lag=weekly_max_hac_lag,
        )
        robustness_no_factor = _partial_test(
            tyvix_w,
            vix_w,
            factor_name=None,
            factor=None,
            max_hac_lag=weekly_max_hac_lag,
        )
        adjusted = adjust_pvalues(
            [primary["p_value"], secondary["p_value"], robustness["p_value"]],
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
            for name, item in zip(
                ("daily_tyvix_vix", "daily_tyvix_vxn", "weekly_tyvix_vix"),
                adjusted,
                strict=True,
            )
        ]

        # Step 5: purged walk-forward OOS evaluation.
        walk_forward = run_walk_forward(
            daily_returns,
            initial_train_size=walk_forward_initial_train,
            test_size=walk_forward_test_size,
            embargo_days=walk_forward_embargo_days,
            holdout_start=spec.holdout_window.start,
        )
        holdout_oos_r2 = walk_forward["holdout_oos_incremental_r_squared"]

        # Step 6: informational cost assessment on holdout OOS forecasts.
        cost_gate = run_cost_gate_informational(
            walk_forward["holdout_forecasts"],
            walk_forward["holdout_actuals"],
            block_length=bootstrap_block_length,
            resamples=bootstrap_resamples,
            seed=bootstrap_seed,
        )

        # Descriptives (not in the test family).
        reverse_placebo = _partial_test(
            vix_d,
            tyvix_d,
            factor_name="spx",
            factor=spx_d,
            max_hac_lag=daily_max_hac_lag,
        )
        subperiods = run_subperiod_stability(
            daily_returns,
            max_hac_lag=daily_max_hac_lag,
        )
        percentiles = run_percentile_descriptive(
            daily_closes,
            daily_returns,
            window=percentile_window,
        )
        zscore = run_zscore_sensitivity(
            daily_returns,
            window=zscore_window,
            max_hac_lag=daily_max_hac_lag,
        )
        factor_timing = run_factor_timing_sensitivity(
            daily_returns,
            max_hac_lag=daily_max_hac_lag,
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
        metrics: dict[str, Any] = {
            "panel": {
                "daily_rows": int(daily_returns.shape[0]),
                "daily_first": daily_returns.index[0].isoformat(),
                "daily_last": daily_returns.index[-1].isoformat(),
                "daily_dropped_close_rows": daily.dropped_close_rows,
                "daily_dropped_return_rows": daily.dropped_return_rows,
                "weekly_rows": int(weekly_changes.shape[0]),
                "weekly_first": weekly_changes.index[0].isoformat(),
                "weekly_last": weekly_changes.index[-1].isoformat(),
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
                "daily_tyvix_vix": primary,
                "daily_tyvix_vix_no_factor": primary_no_factor,
                "daily_tyvix_vxn": secondary,
                "daily_tyvix_vxn_no_factor": secondary_no_factor,
                "weekly_tyvix_vix": robustness,
                "weekly_tyvix_vix_no_factor": robustness_no_factor,
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
            "reverse_placebo": reverse_placebo,
            "subperiod_stability": subperiods,
            "percentile_descriptive": percentiles,
            "zscore_sensitivity": zscore,
            "factor_timing_sensitivity": factor_timing,
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
    daily, manifest_info = load_panels()
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
        build_experiment(daily, spec),
    )
    print(f"trial {receipt.trial_id} completed: record {receipt.record_hash}")
    metrics = receipt.metrics
    primary = metrics["tests"]["daily_tyvix_vix"]
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
    print(f"verdict supported: {metrics['verdict']['supported']}")


if __name__ == "__main__":
    main()
