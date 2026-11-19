"""Run trial T0021 for hypothesis H0018 v1 (BTC -> BTC_DVOL transmission).

Run after preregistration and fetching, from the repo root, with a clean
worktree (the trial records the HEAD commit as its code revision):

    .venv/bin/python research/btc-dvol-013/run_trial.py

The trial binds the preregistered H0018 v1 spec, the fetch manifest's
SHA-256 as the data fingerprint, and a canonical-JSON hash of the
analysis configuration. It executes the six-step thesis flow in one
trial:

1. naive lead-lag scan (descriptive, lags 0-5, unlagged changes);
2. synchronized daily panel (no forward filling): BTC and ETH daily
   log returns (OKX 1D candles, bars open 16:00 UTC) and the BTC_DVOL
   daily log change (the 16:00 UTC snapshot — the close of the
   Deribit hourly DVOL row timestamped 15:00 UTC — aligned to the
   OKX bar grid). Diff-then-join: changes are computed per series on
   its own dates first, then joined. There is no FRED-style
   publication lag: BTC prices and the DVOL index are both real-time,
   so the predictor is the BTC return over the bar opening at t
   (knowable at the 16:00 UTC decision close) forecasting the DVOL
   change over the bar opening at t+1;
3. the preregistered single-test primary (partial lead-lag, lag 1 in
   regression terms: the predictor available at close t forecasts the
   DVOL change over t+1), plus the no-factor upper-bound control.
   The baseline controls for the target's own lag-1 change (the DVOL
   change over the bar opening at t — a real-time index value,
   knowable at the decision close, so no source-lag concession is
   needed) and the ETH common-factor control (lag 0);
4. descriptive only: the same-bar (naive) alignment — the lookahead
   version, quantifying what ignoring the lag would buy (here the
   naive alignment measures lag-1 vs lag-0, not a publication-lag
   effect, since both legs are real-time) — the reverse placebo
   (BTC_DVOL->BTC), sub-period stability (yearly blocks, preregistered),
   and the amplitude check (|BTC return| -> next-day DVOL change,
   descriptive, not in the test family);
5. purged walk-forward out-of-sample evaluation, scored in full and
   on the preregistered holdout window only;
6. informational cost assessment (study 003's precedent for a
   non-tradable target): the gross sign-rule edge on holdout OOS
   augmented forecasts, no costs applied, in log-change units per
   day, with a block-bootstrap CI. BTC_DVOL is an index and is not
   directly tradable; the tradable proxy would be a Deribit BTC
   options straddle, but Deribit's public API returns no_data for
   BTC option chart data (verified 2026-11-19) and expired listings
   return only the most recent batch, so no clean straddle cost
   series exists; the assessment carries no verdict weight.

The verdict covers the three preregistered acceptance criteria
(study 003's three — the cost gate is informational here, not a
criterion). The runner records the trial (including failures) in the
hash-chained ledger trials.jsonl; it does not decide acceptance.

The sample is the full DVOL window (2021-03-24 to the fetch date):
n is about 2,065, far smaller than the BAA10Y studies' 5,957, so the
MDE is about 0.0038 rather than 0.0013 — see the report for the
power boundary.

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
)

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "btc-dvol-013"

HYPOTHESIS_ID = "H0018"
HYPOTHESIS_VERSION = 1
TRIAL_ID = "T0021"

BTC = "crypto:btc-usdt-perp"
BTC_DVOL = "index:btc-dvol"
ETH = "crypto:eth-usdt-perp"
DAILY_INSTRUMENTS = (BTC, BTC_DVOL, ETH)

# No cost constants: the cost gate is informational only (study 003's
# precedent for a non-tradable target — BTC_DVOL is an index; the
# tradable proxy would be a Deribit BTC options straddle, but
# Deribit's public API returns no_data for BTC option chart data
# (verified 2026-11-19) and expired listings return only the most
# recent batch, so no clean straddle cost series exists). The trial
# reports the gross sign-rule edge in log-change units per day with a
# block-bootstrap CI.


def load_panels() -> tuple[SynchronizedPanel, list[Observation], dict[str, Any]]:
    """Load the daily panel and the raw observations from the PIT store.

    No bar_seconds: crypto trades 24/7, so returns are per-calendar-day
    log changes on the 16:00 UTC bar grid (study 001's convention).
    The scaffold used to generate bar_seconds=86400, which would
    invalidate every Monday return; that bug was fixed in PR #28 and
    the generated file now passes bar_seconds=None. (The panel's log
    returns are the analysis variables for all three legs: BTC and
    ETH log returns, and the BTC_DVOL log change — DVOL is an index
    level like VIX, so its log change is the target.)
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


def build_frame(panel: SynchronizedPanel) -> pd.DataFrame:
    """The regression frame: daily log changes, diff-then-join.

    No lagged-changes module is needed here: unlike the BAA10Y
    studies, there is no publication lag — BTC prices and the DVOL
    index are both real-time, so the predictor is the BTC log return
    over the bar opening at t (knowable at the 16:00 UTC decision
    close) and the target is the DVOL log change over the bar opening
    at t+1. The frame index is the panel return index itself; the
    one-step alignment is done by partial_lead_lag (lag_steps=1) and
    by the walk-forward's target/predictor split.
    """
    frame = pd.DataFrame(index=panel.returns.index)
    frame["btc"] = panel.returns[BTC]
    frame["dvol"] = panel.returns[BTC_DVOL]
    frame["eth"] = panel.returns[ETH]
    return frame


def analysis_config(spec: HypothesisSpec) -> dict[str, Any]:
    """The exact analysis configuration, hashed as the config fingerprint."""
    return {
        "fixed_parameters": list(spec.fixed_parameters),
        "test_family": ["daily_btc_dvol"],
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
        "trial_script": "research/btc-dvol-013/run_trial.py",
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
            "BTC->BTC_DVOL transmission: lagged BTC-return partial "
            "lead-lag with an ETH common-factor control, purged "
            "walk-forward OOS evaluation, amplitude and reverse "
            "descriptives, and an informational gross sign-rule edge "
            "in log-change units per day (no cost gate: BTC_DVOL is "
            "an index and no clean straddle cost series exists)"
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
    """Purged walk-forward OOS evaluation of the BTC->BTC_DVOL model.

    Regression row j uses predictors known at day j's close (the BTC
    log return over the bar opening at j, the ETH log return over the
    same bar, and the DVOL log change over the same bar) to forecast
    the DVOL log change over the bar opening at j+1. Label ends are
    the exact next-row event times, so the 24/7 calendar is handled
    exactly (every day is a trading day here).
    """
    btc = frame["btc"].to_numpy(dtype=float)
    eth = frame["eth"].to_numpy(dtype=float)
    dvol = frame["dvol"].to_numpy(dtype=float)
    target = dvol[1:]
    predictors = {
        "target_lag": dvol[:-1],
        "eth": eth[:-1],
        "btc": btc[:-1],
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
                "eth": predictors["eth"][train],
            },
        )
        augmented_fit = ols_fit(
            target[train],
            {name: values[train] for name, values in predictors.items()},
        )
        baseline_forecasts[test] = _ols_predict(
            base_fit,
            {name: values[test] for name, values in predictors.items() if name != "btc"},
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
    while positioned), in log-change units per day on the DVOL log
    change itself. No costs are applied: BTC_DVOL is an index and is
    not directly tradable, and the tradable proxy (a Deribit BTC
    options straddle) has no clean free cost series — Deribit's
    public API returns no_data for BTC option chart data (verified
    2026-11-19) and expired listings return only the most recent
    batch. The gross edge is an upper bound on any tradable edge, not
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
        "units": "log-change units per day",
        "note": (
            "Informational only: no costs applied. BTC_DVOL is an "
            "index and is not directly tradable; the tradable proxy "
            "(a Deribit BTC options straddle) has no clean free cost "
            "series — Deribit's public API returns no_data for BTC "
            "option chart data (verified 2026-11-19) and expired "
            "listings return only the most recent batch. Not a "
            "verdict criterion."
        ),
    }


def _parse_subperiods(raw: str) -> tuple[tuple[str, datetime, datetime], ...]:
    """Parse 'YYYY-YYYY,...' into half-open [Jan 1, Jan 1) ranges.

    Boundaries at 16:00 UTC (the OKX bar grid), not 21:00 UTC as in
    the FRED studies: the frame index is the 16:00 UTC bar-open grid.
    """
    subperiods: list[tuple[str, datetime, datetime]] = []
    for label in raw.split(","):
        start_year, end_year = label.split("-")
        start = datetime(int(start_year), 1, 1, 16, 0, tzinfo=UTC)
        end = datetime(int(end_year) + 1, 1, 1, 16, 0, tzinfo=UTC)
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
    re-runs the primary partial lead-lag test (ETH factor). The last
    row of each slice is dropped by the lag alignment inside
    partial_lead_lag, so every counted row has both its decision date
    and its target date inside the block. Coefficients and partial
    R-squared only — no p-values, not in the test family.
    """
    index = frame.index
    btc = frame["btc"].to_numpy(dtype=float)
    eth = frame["eth"].to_numpy(dtype=float)
    dvol = frame["dvol"].to_numpy(dtype=float)
    results: dict[str, Any] = {}
    for label, start, end in subperiods:
        mask = (index >= start) & (index < end)
        result = partial_lead_lag(
            btc[mask],
            dvol[mask],
            lag_steps=1,
            common_factors={"eth": eth[mask]},
            max_hac_lag=max_hac_lag,
        )
        results[label] = {
            "observations": result.observations,
            "coefficient": result.source_effect.estimate,
            "standard_error": result.source_effect.standard_error,
            "partial_r_squared": result.partial_r_squared,
        }
    return results


def build_experiment(
    panel: SynchronizedPanel,
    spec: HypothesisSpec,
) -> Any:
    """Build the trial callback closing over the loaded panel."""

    def experiment(trial_spec: TrialSpec) -> dict[str, Any]:
        params = {item.name: item.value for item in trial_spec.parameters}
        predictor_lag_steps = int(params["predictor_lag_steps"])
        control_lag_steps = int(params["control_lag_steps"])
        daily_max_hac_lag = int(params["daily_max_hac_lag"])
        bootstrap_block_length = int(params["bootstrap_block_length"])
        bootstrap_resamples = int(params["bootstrap_resamples"])
        bootstrap_seed = int(params["bootstrap_seed"])
        walk_forward_initial_train = int(params["walk_forward_initial_train"])
        walk_forward_test_size = int(params["walk_forward_test_size"])
        walk_forward_embargo_days = int(params["walk_forward_embargo_days"])
        subperiods = _parse_subperiods(str(params["subperiods"]))

        frame = build_frame(panel)
        btc = frame["btc"].to_numpy(dtype=float)
        eth = frame["eth"].to_numpy(dtype=float)
        dvol = frame["dvol"].to_numpy(dtype=float)

        # Step 1: naive scan (descriptive, unlagged changes). Lag 1
        # is the tradeable PIT-correct alignment here (no publication
        # lag — both legs real-time).
        scan = lead_lag_scan(btc, dvol, lag_steps=(0, 1, 2, 3, 4, 5))

        # Step 3: the preregistered single-test primary (ETH factor),
        # plus the no-factor upper-bound control.
        primary = _partial_test(
            btc,
            dvol,
            factors={"eth": eth},
            max_hac_lag=daily_max_hac_lag,
        )
        primary_no_factor = _partial_test(
            btc,
            dvol,
            factors=None,
            max_hac_lag=daily_max_hac_lag,
        )
        adjusted = adjust_pvalues(
            [primary["p_value"]],
            method=MultiplicityCorrection.HOLM,
            target_error_rate=spec.target_error_rate,
        )
        holm: list[dict[str, Any]] = [
            {
                "test": "daily_btc_dvol",
                "raw_p_value": adjusted[0].raw_p_value,
                "adjusted_p_value": adjusted[0].adjusted_p_value,
                "reject": adjusted[0].reject,
            }
        ]

        # Step 4 (descriptive): the same-bar (naive) alignment — the
        # lookahead version, quantifying what ignoring the lag would
        # buy. Both legs are real-time, so the naive alignment here
        # measures lag-1 vs lag-0, not a publication-lag effect. The
        # truncated arrays pair BTC[t+1] with DVOL[t+1] (same bar),
        # with the own-history DVOL[t] and the contemporaneous ETH
        # factor ETH[t+1]; the reverse placebo (BTC_DVOL->BTC);
        # sub-period stability; and the amplitude check (|BTC
        # return| -> next-day DVOL change, descriptive, not in the
        # test family).
        naive = _partial_test(
            btc[1:],
            dvol[:-1],
            factors={"eth": eth[1:]},
            max_hac_lag=daily_max_hac_lag,
        )
        reverse = _partial_test(
            dvol,
            btc,
            factors={"eth": eth},
            max_hac_lag=daily_max_hac_lag,
        )
        amplitude = _partial_test(
            np.abs(btc),
            dvol,
            factors={"eth": eth},
            max_hac_lag=daily_max_hac_lag,
        )
        subperiods_result = run_subperiod_stability(
            frame,
            subperiods=subperiods,
            max_hac_lag=daily_max_hac_lag,
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
        # augmented forecasts (gross sign-rule edge in log-change
        # units per day, no costs — BTC_DVOL is an index and no clean
        # straddle cost series exists; study 003's precedent, not a
        # verdict criterion).
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
                "predictor_lag_steps": predictor_lag_steps,
                "control_lag_steps": control_lag_steps,
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
                "daily_btc_dvol": primary,
                "daily_btc_dvol_no_factor": primary_no_factor,
                "daily_btc_dvol_naive": naive,
                "daily_dvol_btc_reverse": reverse,
                "daily_btc_abs_dvol_amplitude": amplitude,
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
        build_experiment(daily, spec),
    )
    print(f"trial {receipt.trial_id} completed: record {receipt.record_hash}")
    metrics = receipt.metrics
    primary = metrics["tests"]["daily_btc_dvol"]
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
