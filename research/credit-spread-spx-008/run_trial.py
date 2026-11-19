"""Run trial T0016 for hypothesis H0013 (BAA10Y -> SPX transmission).

Run after preregistration and fetching, from the repo root, with a clean
worktree (the trial records the HEAD commit as its code revision):

    .venv/bin/python research/credit-spread-spx-008/run_trial.py

The trial binds the preregistered H0013 v1 spec, the fetch manifest's
SHA-256 as the data fingerprint, and a canonical-JSON hash of the
analysis configuration. It executes the six-step thesis flow in one
trial:

1. naive lead-lag scan (descriptive, lags 0-5, unlagged changes);
2. synchronized daily panel (no forward filling) plus the
   publication-lag transforms: the BAA10Y predictor is the level
   change in basis points lagged 2 trading days by availability, the
   VIX control is the log change lagged 1 trading day, both via the
   study-007 lagged-changes module (diff-then-join, shift between
   diff and join);
3. the preregistered single-test primary (partial lead-lag, lag 1 in
   regression terms: the predictor available at close t forecasts the
   SPX return over t+1), plus the no-factor upper-bound control;
4. descriptive only: the unlagged (naive) alignment — the lookahead
   version, quantifying what ignoring the publication lag would buy
   — the reverse placebo (SPX->BAA10Y) and sub-period stability;
5. purged walk-forward out-of-sample evaluation, scored in full and
   on the preregistered holdout window only;
6. cost gate: sign rule on holdout OOS augmented forecasts against
   the preregistered SPY spread assumption (1bp per side, round trip
   2bp per flip), with a block-bootstrap CI on the net daily edge.

The verdict covers the four preregistered acceptance criteria
(study 001's four). The runner records the trial (including failures)
in the hash-chained ledger trials.jsonl; it does not decide
acceptance.

Scaffold note: the 6c scaffold generated a minimal run_trial.py that
wired only the primary test and a two-criterion verdict, passed
``bar_seconds=86400`` to the panel builder (wrong for US trading days
with weekend gaps — it would invalidate every Monday return), and
left the walk-forward evaluation and the cost gate as
NotImplementedError stubs. This file replaces that skeleton with the
full study-001/003 pipeline; see the study report's scaffold-feedback
section.
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
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "credit-spread-spx-008"

HYPOTHESIS_ID = "H0013"
HYPOTHESIS_VERSION = 1
TRIAL_ID = "T0016"

BAA10Y = "credit:baa-10y-spread"
SPX = "index:sp500"
VIX = "index:vix"
DAILY_INSTRUMENTS = (BAA10Y, SPX, VIX)

# Preregistered cost assumption: SPY bid-ask spread 1bp per side
# (conservative — realised SPY spreads are about 0.1-0.2bp).
SPREAD_PER_SIDE = 0.0001
ROUND_TRIP_COST = 0.0002


def load_panels() -> tuple[SynchronizedPanel, list[Observation], dict[str, Any]]:
    """Load the daily panel and the raw observations from the PIT store.

    No bar_seconds: US trading days have weekend gaps, so returns are
    per-trading-day log returns (study 003's convention). The
    scaffold's bar_seconds=86400 would invalidate every Monday return.
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
    vix_lag_steps: int,
) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    """The regression frame: lagged predictors + SPX returns.

    The truncated index drops the first max(lag) panel rows (no lagged
    BAA10Y change exists there). The BAA10Y predictor is the level
    change in basis points lagged ``baa_lag_steps`` positions; the VIX
    control is the log change lagged ``vix_lag_steps`` positions; SPX
    comes from the panel's own returns on the truncated index. The
    unlagged BAA10Y change (for the naive descriptive) is computed on
    the same index.
    """
    max_lag = max(baa_lag_steps, vix_lag_steps)
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
    vix_lagged = lagged_changes_on_index(
        observations,
        instruments=(VIX,),
        index=index,
        lag_steps=vix_lag_steps,
        transform="log",
    )
    baa_naive = level_changes_on_index(
        observations,
        instruments=(BAA10Y,),
        index=index,
        scale=100.0,
    )
    frame["baa_lagged"] = baa_lagged[BAA10Y]
    frame["vix_lagged"] = vix_lagged[VIX]
    frame["baa_naive"] = baa_naive[BAA10Y]
    frame["spx"] = panel.returns.loc[index, SPX]
    return frame, index


def analysis_config(spec: HypothesisSpec) -> dict[str, Any]:
    """The exact analysis configuration, hashed as the config fingerprint."""
    return {
        "fixed_parameters": list(spec.fixed_parameters),
        "test_family": ["daily_baa10y_spx"],
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
        "trial_script": "research/credit-spread-spx-008/run_trial.py",
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
            "BAA10Y->SPX transmission: lagged spread-change partial "
            "lead-lag, purged walk-forward OOS evaluation and SPY "
            "spread cost gate"
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
    factors: dict[str, np.ndarray] | None = None
    if factor is not None and factor_name is not None:
        factors = {factor_name: factor}
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
    """Purged walk-forward OOS evaluation of the BAA10Y->SPX model.

    Regression row j uses predictors known at day j's close (the
    lagged BAA10Y change, the lagged VIX change, SPX's own return) to
    forecast the SPX return over day j+1. Label ends are the exact
    next-row event times, so weekends and holidays are handled exactly
    (a Friday row's label ends Monday).
    """
    baa = frame["baa_lagged"].to_numpy(dtype=float)
    vix = frame["vix_lagged"].to_numpy(dtype=float)
    spx = frame["spx"].to_numpy(dtype=float)
    target = spx[1:]
    predictors = {
        "target_lag": spx[:-1],
        "vix": vix[:-1],
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
                "vix": predictors["vix"][train],
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


def run_cost_gate(
    forecasts: list[float],
    actuals: list[float],
    *,
    block_length: int,
    resamples: int,
    seed: int,
) -> dict[str, Any]:
    """Sign rule on OOS forecasts: 1x SPY, always invested while positioned.

    Entry from flat and final exit cost one spread side each (1bp); a
    direction flip costs a full round trip (2bp). Returns are log
    returns, used as the P&L proxy for a 1x position.
    """
    positions = np.sign(np.asarray(forecasts, dtype=float))
    gross = positions * np.asarray(actuals, dtype=float)
    costs = np.zeros_like(gross)
    previous = 0.0
    flips = 0
    for index, position in enumerate(positions):
        if position == previous:
            continue
        if previous == 0.0 or position == 0.0:
            costs[index] += SPREAD_PER_SIDE
        else:
            costs[index] += ROUND_TRIP_COST
            flips += 1
        previous = float(position)
    if positions[-1] != 0.0:
        costs[-1] += SPREAD_PER_SIDE
    net = gross - costs
    interval = block_bootstrap_mean_ci(
        net,
        block_length=block_length,
        resamples=resamples,
        seed=seed,
    )
    test = block_bootstrap_mean_test(
        net,
        null_mean=0.0,
        block_length=block_length,
        resamples=resamples,
        seed=seed,
    )
    return {
        "days": int(net.size),
        "gross_daily_edge": float(np.mean(gross)),
        "flips": flips,
        "total_cost": float(np.sum(costs)),
        "net_daily_edge": float(np.mean(net)),
        "net_edge_ci_lower": interval.lower_bound,
        "net_edge_ci_upper": interval.upper_bound,
        "net_edge_bootstrap_p_value": test.p_value,
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
    re-runs the primary partial lead-lag test. Coefficients and
    partial R-squared only — no p-values, not in the test family.
    """
    index = frame.index
    baa = frame["baa_lagged"].to_numpy(dtype=float)
    vix = frame["vix_lagged"].to_numpy(dtype=float)
    spx = frame["spx"].to_numpy(dtype=float)
    results: dict[str, Any] = {}
    for label, start, end in subperiods:
        mask = (index >= start) & (index < end)
        result = partial_lead_lag(
            baa[mask],
            spx[mask],
            lag_steps=1,
            common_factors={"vix": vix[mask]},
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
    observations: list[Observation],
    spec: HypothesisSpec,
) -> Any:
    """Build the trial callback closing over the loaded panel."""

    def experiment(trial_spec: TrialSpec) -> dict[str, Any]:
        params = {item.name: item.value for item in trial_spec.parameters}
        baa_lag_steps = int(params["predictor_lag_steps"])
        vix_lag_steps = int(params["control_lag_steps"])
        daily_max_hac_lag = int(params["daily_max_hac_lag"])
        bootstrap_block_length = int(params["bootstrap_block_length"])
        bootstrap_resamples = int(params["bootstrap_resamples"])
        bootstrap_seed = int(params["bootstrap_seed"])
        walk_forward_initial_train = int(params["walk_forward_initial_train"])
        walk_forward_test_size = int(params["walk_forward_test_size"])
        walk_forward_embargo_days = int(params["walk_forward_embargo_days"])
        subperiods = _parse_subperiods(str(params["subperiods"]))

        frame, _index = build_lagged_frame(
            panel,
            observations,
            baa_lag_steps=baa_lag_steps,
            vix_lag_steps=vix_lag_steps,
        )
        baa = frame["baa_lagged"].to_numpy(dtype=float)
        vix = frame["vix_lagged"].to_numpy(dtype=float)
        baa_naive = frame["baa_naive"].to_numpy(dtype=float)
        spx = frame["spx"].to_numpy(dtype=float)

        # Step 1: naive scan (descriptive, unlagged changes).
        scan = lead_lag_scan(baa_naive, spx, lag_steps=(0, 1, 2, 3, 4, 5))

        # Step 3: the preregistered single-test primary, plus the
        # no-factor upper-bound control.
        primary = _partial_test(
            baa,
            spx,
            factor_name="vix",
            factor=vix,
            max_hac_lag=daily_max_hac_lag,
        )
        primary_no_factor = _partial_test(
            baa,
            spx,
            factor_name=None,
            factor=None,
            max_hac_lag=daily_max_hac_lag,
        )
        adjusted = adjust_pvalues(
            [primary["p_value"]],
            method=MultiplicityCorrection.HOLM,
            target_error_rate=spec.target_error_rate,
        )
        holm: list[dict[str, Any]] = [
            {
                "test": "daily_baa10y_spx",
                "raw_p_value": adjusted[0].raw_p_value,
                "adjusted_p_value": adjusted[0].adjusted_p_value,
                "reject": adjusted[0].reject,
            }
        ]

        # Step 4 (descriptive): the naive unlagged alignment (the
        # lookahead version — what ignoring the publication lag would
        # buy) and the reverse placebo (SPX -> BAA10Y).
        naive = _partial_test(
            baa_naive,
            spx,
            factor_name="vix",
            factor=vix,
            max_hac_lag=daily_max_hac_lag,
        )
        reverse = _partial_test(
            spx,
            baa_naive,
            factor_name="vix",
            factor=vix,
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

        # Step 6: cost gate on holdout OOS augmented forecasts.
        cost_gate = run_cost_gate(
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
            "net_daily_edge_after_costs_positive": bool(
                cost_gate["net_daily_edge"] > 0
            ),
        }
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
                "vix_lag_steps": vix_lag_steps,
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
                "daily_baa10y_spx": primary,
                "daily_baa10y_spx_no_factor": primary_no_factor,
                "daily_baa10y_spx_naive": naive,
                "daily_spx_baa10y_reverse": reverse,
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
            "cost_gate": cost_gate,
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
        build_experiment(daily, observations, spec),
    )
    print(f"trial {receipt.trial_id} completed: record {receipt.record_hash}")
    metrics = receipt.metrics
    primary = metrics["tests"]["daily_baa10y_spx"]
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
    print(f"cost gate: {metrics['cost_gate']}")
    print(f"verdict supported: {metrics['verdict']['supported']}")


if __name__ == "__main__":
    main()
