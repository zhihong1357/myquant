"""Run trial T0005 for hypothesis H0005 (expiry-window transmission).

Run after preregistration and fetching, from the repo root, with a clean
worktree (the trial records the HEAD commit as its code revision):

    .venv/bin/python research/options-expiry-004/run_trial.py

The trial binds the preregistered H0005 v1 spec, this study's fetch
manifest SHA-256 as the data fingerprint, and a canonical-JSON hash of
the analysis configuration. It executes the preregistered three-test
family:

- A (primary): daily BTC→ETH interaction test — ETH[t+1] on ETH[t],
  SOL[t] (factor), BTC[t] and BTC[t]×window[t], HAC standard errors,
  testing the interaction coefficient.
- B: daily BTC→ETH partial lead-lag on expiry-window rows only.
- C: 1H BTC→ETH interaction test (SOL factor control).

Plus the preregistered window-aware purged walk-forward evaluation
(expiry-window holdout rows only), the cost gate (positions only on
expiry-window holdout rows), and descriptive checks (wide window,
quarterly-vs-monthly, subperiod splits, DVOL around expiry — none in
the test family, no p-values).

The expiry window for monthly expiry T (last Friday of the month,
settlement 08:00 UTC) is the set of bar-open dates in [T-3, T]. The
window indicator is known at the bar's open because the expiry calendar
is public in advance (point-in-time correct). The runner records the
trial (including failures) in the hash-chained ledger trials.jsonl; it
does not decide acceptance.
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
    ols_fit,
    purged_walk_forward_split_report,
)
from myquant.studies.expiry import (
    expiry_window_indicator,
    monthly_expiries,
    quarterly_window_indicator,
)
from myquant.studies.panel import SynchronizedPanel, build_synchronized_panel
from myquant.studies.regime import NestedLeadLagTest, nested_lead_lag_test

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "options-expiry-004"

HYPOTHESIS_ID = "H0005"
HYPOTHESIS_VERSION = 1
TRIAL_ID = "T0005"

BTC = "crypto:btc-usdt-perp"
ETH = "crypto:eth-usdt-perp"
SOL = "crypto:sol-usdt-perp"
INSTRUMENTS = (BTC, ETH, SOL)
BTC_DVOL = "index:btc-dvol"
ETH_DVOL = "index:eth-dvol"
DVOL_INSTRUMENTS = (BTC_DVOL, ETH_DVOL)

# Preregistered cost assumption: OKX VIP0 taker 0.05% per side.
TAKER_FEE_PER_SIDE = 0.0005
ROUND_TRIP_COST = 0.001


def load_panels() -> tuple[
    SynchronizedPanel, SynchronizedPanel, SynchronizedPanel, dict[str, Any]
]:
    """Load the OKX daily/1H panels and the DVOL daily panel."""
    manifest_path = ROOT / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    decision_time = datetime.fromisoformat(manifest["fetched_at"])
    if decision_time.tzinfo is None:
        decision_time = decision_time.replace(tzinfo=UTC)

    source_registry = SourceRegistry(ROOT / "sources")
    daily_store = ParquetPITStore(CACHE_ROOT / "pit-1d", source_registry)
    hourly_store = ParquetPITStore(CACHE_ROOT / "pit-1h", source_registry)
    dvol_store = ParquetPITStore(CACHE_ROOT / "pit-dvol", source_registry)
    daily = build_synchronized_panel(
        daily_store.query_as_of(
            decision_time,
            instrument_ids=set(INSTRUMENTS),
            fields={"close"},
        ),
        instruments=INSTRUMENTS,
        bar_seconds=86_400,
    )
    hourly = build_synchronized_panel(
        hourly_store.query_as_of(
            decision_time,
            instrument_ids=set(INSTRUMENTS),
            fields={"close"},
        ),
        instruments=INSTRUMENTS,
        bar_seconds=3_600,
    )
    dvol = build_synchronized_panel(
        dvol_store.query_as_of(
            decision_time,
            instrument_ids=set(DVOL_INSTRUMENTS),
            fields={"close"},
        ),
        instruments=DVOL_INSTRUMENTS,
        bar_seconds=86_400,
    )
    manifest_info = {
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "fetched_at": manifest["fetched_at"],
    }
    return daily, hourly, dvol, manifest_info


def analysis_config(spec: HypothesisSpec) -> dict[str, Any]:
    """The exact analysis configuration, hashed as the config fingerprint."""
    return {
        "fixed_parameters": list(spec.fixed_parameters),
        "test_family": [
            "daily_btc_eth_interaction",
            "daily_btc_eth_window",
            "hourly_btc_eth_interaction",
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
        "trial_script": "research/options-expiry-004/run_trial.py",
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
            "Expiry-window BTC→ETH transmission: daily interaction and "
            "window-subsample tests, 1H interaction test, window-aware "
            "purged walk-forward OOS evaluation and taker-cost gate"
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


def build_regression_rows(
    returns: pd.DataFrame,
    *,
    target: str,
    factor: str,
    is_window: pd.Series,
) -> pd.DataFrame:
    """Align one-bar-ahead regression rows and attach window flags.

    Row j predicts the target return over bar j+1 from predictors known
    at bar j's close (target, factor and source returns over bar j, plus
    the window flag for bar j, which is known at bar j's open because
    the expiry calendar is public in advance).
    """
    target_values = returns[target].to_numpy(dtype=float)
    factor_values = returns[factor].to_numpy(dtype=float)
    source_values = returns[BTC].to_numpy(dtype=float)
    flags = is_window.reindex(returns.index[:-1])
    rows = pd.DataFrame(
        {
            "target_next": target_values[1:],
            "target_lag": target_values[:-1],
            "factor": factor_values[:-1],
            "btc": source_values[:-1],
            "window": flags.to_numpy(dtype=float),
        },
        index=returns.index[:-1],
    )
    rows = rows.dropna(subset=["window"])
    rows["window"] = rows["window"].astype(bool)
    rows["interaction"] = rows["btc"] * rows["window"].astype(float)
    return rows


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


def _interaction_test(
    rows: pd.DataFrame,
    *,
    with_factor: bool,
    max_hac_lag: int,
) -> dict[str, Any]:
    """A/C: test the BTC×window interaction over all rows."""
    base: dict[str, np.ndarray] = {
        "target_lag": rows["target_lag"].to_numpy(dtype=float),
        "btc": rows["btc"].to_numpy(dtype=float),
    }
    if with_factor:
        base["factor"] = rows["factor"].to_numpy(dtype=float)
    result = nested_lead_lag_test(
        rows["target_next"].to_numpy(dtype=float),
        base,
        {"interaction": rows["interaction"].to_numpy(dtype=float)},
        effect_name="interaction",
        max_hac_lag=max_hac_lag,
    )
    return _test_metrics(result)


def _subsample_test(
    rows: pd.DataFrame,
    *,
    with_factor: bool,
    max_hac_lag: int,
) -> dict[str, Any]:
    """B: partial lead-lag on expiry-window rows only."""
    window_rows = rows[rows["window"]]
    base: dict[str, np.ndarray] = {
        "target_lag": window_rows["target_lag"].to_numpy(dtype=float),
    }
    if with_factor:
        base["factor"] = window_rows["factor"].to_numpy(dtype=float)
    result = nested_lead_lag_test(
        window_rows["target_next"].to_numpy(dtype=float),
        base,
        {"source": window_rows["btc"].to_numpy(dtype=float)},
        effect_name="source",
        max_hac_lag=max_hac_lag,
    )
    return _test_metrics(result)


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
    """Window-aware purged walk-forward OOS evaluation of the A model.

    Base model: target lag + factor + BTC (no interaction). Augmented
    model: base + BTC×window. Regression row j uses predictors known at
    bar j's close to forecast the target return over bar j+1, known at
    bar j+1's close — two days after row j's bar open. Hence label_end =
    decision_time + 2 days. Scoring is reported on all test rows, on
    holdout test rows, and on expiry-window holdout test rows (the
    preregistered acceptance criterion).
    """
    target = rows["target_next"].to_numpy(dtype=float)
    predictors = {
        "target_lag": rows["target_lag"].to_numpy(dtype=float),
        "factor": rows["factor"].to_numpy(dtype=float),
        "btc": rows["btc"].to_numpy(dtype=float),
        "interaction": rows["interaction"].to_numpy(dtype=float),
    }
    window = rows["window"].to_numpy(dtype=bool)
    decision_times = [item.to_pydatetime() for item in rows.index]
    label_ends = [item + timedelta(days=2) for item in decision_times]
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
                name: values[train]
                for name, values in predictors.items()
                if name != "interaction"
            },
        )
        augmented_fit = ols_fit(
            target[train],
            {name: values[train] for name, values in predictors.items()},
        )
        baseline_forecasts[test] = _ols_predict(
            base_fit,
            {
                name: values[test]
                for name, values in predictors.items()
                if name != "interaction"
            },
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
    window_holdout_folds = restricted_folds(
        lambda index: decision_times[index] >= holdout_start and window[index]
    )
    window_holdout_evaluation = evaluate_walk_forward_forecasts(
        target,
        baseline_forecasts,
        augmented_forecasts,
        folds=window_holdout_folds,
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
        "window_holdout_folds": len(window_holdout_folds),
        "window_holdout_test_rows": int(
            window_holdout_evaluation.observations
        ),
        "window_holdout_oos_incremental_r_squared": (
            window_holdout_evaluation.incremental_oos_r_squared
        ),
        "window_holdout_baseline_mse": window_holdout_evaluation.baseline_mse,
        "window_holdout_augmented_mse": window_holdout_evaluation.augmented_mse,
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
        "holdout_window": [bool(window[index]) for index in holdout_test_rows],
    }


def run_cost_gate(
    forecasts: list[float],
    actuals: list[float],
    window: list[bool],
    *,
    block_length: int,
    resamples: int,
    seed: int,
) -> dict[str, Any]:
    """Sign rule on OOS forecasts, positioned on window rows only.

    1x, flat on non-window rows. Entry from flat and final exit cost
    one taker side each (0.05%); a direction flip costs a full round trip
    (0.10%). Returns are log returns, used as the P&L proxy for a 1x
    position. The net daily edge is averaged over all holdout test rows,
    including flat non-window rows.
    """
    positions = np.where(
        np.asarray(window, dtype=bool),
        np.sign(np.asarray(forecasts, dtype=float)),
        0.0,
    )
    gross = positions * np.asarray(actuals, dtype=float)
    costs = np.zeros_like(gross)
    previous = 0.0
    flips = 0
    for index, position in enumerate(positions):
        if position == previous:
            continue
        if previous == 0.0 or position == 0.0:
            costs[index] += TAKER_FEE_PER_SIDE
        else:
            costs[index] += ROUND_TRIP_COST
            flips += 1
        previous = float(position)
    if positions[-1] != 0.0:
        costs[-1] += TAKER_FEE_PER_SIDE
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
        "window_days": int(np.count_nonzero(window)),
        "gross_daily_edge": float(np.mean(gross)),
        "flips": flips,
        "total_cost": float(np.sum(costs)),
        "net_daily_edge": float(np.mean(net)),
        "net_edge_ci_lower": interval.lower_bound,
        "net_edge_ci_upper": interval.upper_bound,
        "net_edge_bootstrap_p_value": test.p_value,
    }


def _descriptive_interaction(
    rows: pd.DataFrame,
    *,
    max_hac_lag: int,
) -> dict[str, Any]:
    """Interaction test for a descriptive split: no p-values.

    Coefficients and partial R-squared only; descriptive splits are not
    in the test family and must not be read as additional tests.
    """
    result = _interaction_test(rows, with_factor=True, max_hac_lag=max_hac_lag)
    return {
        "observations": result["observations"],
        "coefficient": result["coefficient"],
        "partial_r_squared": result["partial_r_squared"],
    }


def run_descriptive_splits(
    daily_returns: pd.DataFrame,
    *,
    expiries: tuple,
    window_days_before: int,
    window_days_after: int,
    wide_days_before: int,
    wide_days_after: int,
    daily_max_hac_lag: int,
) -> dict[str, Any]:
    """Descriptive splits: wide window, quarterly, subperiods.

    No p-values anywhere here: these splits are descriptive, not in the
    test family.
    """
    wide_flags = expiry_window_indicator(
        daily_returns.index,
        expiries,
        days_before=wide_days_before,
        days_after=wide_days_after,
    )
    wide_rows = build_regression_rows(
        daily_returns, target=ETH, factor=SOL, is_window=wide_flags
    )
    quarterly_flags = quarterly_window_indicator(
        daily_returns.index,
        expiries,
        days_before=window_days_before,
        days_after=window_days_after,
    )
    quarterly_rows = build_regression_rows(
        daily_returns, target=ETH, factor=SOL, is_window=quarterly_flags
    )
    # Non-quarterly monthly windows: window rows that are not quarterly.
    full_flags = expiry_window_indicator(
        daily_returns.index,
        expiries,
        days_before=window_days_before,
        days_after=window_days_after,
    )
    monthly_flags = full_flags & ~quarterly_flags
    monthly_rows = build_regression_rows(
        daily_returns, target=ETH, factor=SOL, is_window=monthly_flags
    )
    base_rows = build_regression_rows(
        daily_returns, target=ETH, factor=SOL, is_window=full_flags
    )
    early = base_rows[base_rows.index < datetime(2023, 1, 1, tzinfo=UTC)]
    late = base_rows[base_rows.index >= datetime(2023, 1, 1, tzinfo=UTC)]
    return {
        "wide_window": _descriptive_interaction(
            wide_rows, max_hac_lag=daily_max_hac_lag
        ),
        "wide_window_rows": int(wide_rows["window"].sum()),
        "quarterly_window": _descriptive_interaction(
            quarterly_rows, max_hac_lag=daily_max_hac_lag
        ),
        "quarterly_window_rows": int(quarterly_rows["window"].sum()),
        "monthly_only_window": _descriptive_interaction(
            monthly_rows, max_hac_lag=daily_max_hac_lag
        ),
        "monthly_only_window_rows": int(monthly_rows["window"].sum()),
        "subperiod_2021_2022": _descriptive_interaction(
            early, max_hac_lag=daily_max_hac_lag
        ),
        "subperiod_2023_2026": _descriptive_interaction(
            late, max_hac_lag=daily_max_hac_lag
        ),
    }


def run_dvol_descriptive(
    dvol: SynchronizedPanel,
    *,
    expiries: tuple,
    window_days_before: int,
    window_days_after: int,
) -> dict[str, Any]:
    """Descriptive DVOL around expiry: levels, changes, day-offset profile.

    DVOL daily points sit on a 00:00 UTC grid; they are aligned to the
    expiry calendar by calendar date. No p-values: DVOL is descriptive
    only, not in the test family. Levels and log-changes are aligned by
    index (the returns frame drops the first row, so positional masks
    would misalign).
    """
    closes = dvol.closes
    log_changes = dvol.returns
    level_flags = expiry_window_indicator(
        closes.index,
        expiries,
        days_before=window_days_before,
        days_after=window_days_after,
    )
    change_flags = expiry_window_indicator(
        log_changes.index,
        expiries,
        days_before=window_days_before,
        days_after=window_days_after,
    )
    per_instrument: dict[str, Any] = {}
    for instrument in DVOL_INSTRUMENTS:
        levels = closes[instrument]
        changes = log_changes[instrument]
        per_instrument[instrument] = {
            "points": int(levels.size),
            "mean_level_window": float(levels[level_flags].mean()),
            "mean_level_nonwindow": float(levels[~level_flags].mean()),
            "mean_log_change_window": float(changes[change_flags].mean()),
            "mean_log_change_nonwindow": float(changes[~change_flags].mean()),
        }
    # Day-offset profile: mean DVOL log-change by days from the nearest
    # expiry (offset 0 = expiry day), BTC only, offsets -5..+1.
    expiry_dates = {event.expiry_date for event in expiries}
    profile: dict[str, Any] = {}
    dates = [ts.date() for ts in log_changes.index]
    btc_changes = log_changes[BTC_DVOL].to_numpy(dtype=float)
    for offset in range(-5, 2):
        mask = np.array(
            [
                (item - timedelta(days=offset)) in expiry_dates
                for item in dates
            ],
            dtype=bool,
        )
        profile[f"t{offset:+d}"] = {
            "observations": int(mask.sum()),
            "mean_log_change": (
                float(np.mean(btc_changes[mask])) if mask.any() else None
            ),
        }
    return {
        "instruments": per_instrument,
        "btc_day_offset_profile": profile,
        "window_points": int(level_flags.sum()),
        "nonwindow_points": int((~level_flags).sum()),
        "first_point": closes.index[0].isoformat(),
        "last_point": closes.index[-1].isoformat(),
    }


def build_experiment(
    daily: SynchronizedPanel,
    hourly: SynchronizedPanel,
    dvol: SynchronizedPanel,
    spec: HypothesisSpec,
) -> Any:
    """Build the trial callback closing over the loaded panels."""

    def experiment(trial_spec: TrialSpec) -> dict[str, Any]:
        params = {item.name: item.value for item in trial_spec.parameters}
        daily_max_hac_lag = int(params["daily_max_hac_lag"])
        hourly_max_hac_lag = int(params["hourly_max_hac_lag"])
        window_days_before = int(params["window_days_before"])
        window_days_after = int(params["window_days_after"])
        wide_days_before = int(params["wide_window_days_before"])
        wide_days_after = int(params["wide_window_days_after"])
        bootstrap_block_length = int(params["bootstrap_block_length"])
        bootstrap_resamples = int(params["bootstrap_resamples"])
        bootstrap_seed = int(params["bootstrap_seed"])
        walk_forward_initial_train = int(params["walk_forward_initial_train"])
        walk_forward_test_size = int(params["walk_forward_test_size"])
        walk_forward_embargo_days = int(params["walk_forward_embargo_days"])

        daily_returns = daily.returns
        hourly_returns = hourly.returns

        # Rule-constructed expiry calendar over the daily panel range;
        # the same expiries serve the 1H panel (a subset of the range).
        expiries = monthly_expiries(
            daily_returns.index[0].date(), daily_returns.index[-1].date()
        )
        daily_flags = expiry_window_indicator(
            daily_returns.index,
            expiries,
            days_before=window_days_before,
            days_after=window_days_after,
        )
        hourly_flags = expiry_window_indicator(
            hourly_returns.index,
            expiries,
            days_before=window_days_before,
            days_after=window_days_after,
        )
        daily_rows = build_regression_rows(
            daily_returns, target=ETH, factor=SOL, is_window=daily_flags
        )
        hourly_rows = build_regression_rows(
            hourly_returns, target=ETH, factor=SOL, is_window=hourly_flags
        )

        # The preregistered three-test family, plus no-factor upper-bound
        # controls (not in the family).
        a = _interaction_test(
            daily_rows, with_factor=True, max_hac_lag=daily_max_hac_lag
        )
        a_no_factor = _interaction_test(
            daily_rows, with_factor=False, max_hac_lag=daily_max_hac_lag
        )
        b = _subsample_test(
            daily_rows, with_factor=True, max_hac_lag=daily_max_hac_lag
        )
        b_no_factor = _subsample_test(
            daily_rows, with_factor=False, max_hac_lag=daily_max_hac_lag
        )
        c = _interaction_test(
            hourly_rows, with_factor=True, max_hac_lag=hourly_max_hac_lag
        )
        c_no_factor = _interaction_test(
            hourly_rows, with_factor=False, max_hac_lag=hourly_max_hac_lag
        )
        adjusted = adjust_pvalues(
            [a["p_value"], b["p_value"], c["p_value"]],
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
                (
                    "daily_btc_eth_interaction",
                    "daily_btc_eth_window",
                    "hourly_btc_eth_interaction",
                ),
                adjusted,
                strict=True,
            )
        ]

        # Descriptive splits (not in the test family).
        descriptive = run_descriptive_splits(
            daily_returns,
            expiries=expiries,
            window_days_before=window_days_before,
            window_days_after=window_days_after,
            wide_days_before=wide_days_before,
            wide_days_after=wide_days_after,
            daily_max_hac_lag=daily_max_hac_lag,
        )
        dvol_descriptive = run_dvol_descriptive(
            dvol,
            expiries=expiries,
            window_days_before=window_days_before,
            window_days_after=window_days_after,
        )

        # Window-aware purged walk-forward OOS evaluation (daily A model).
        walk_forward = run_walk_forward(
            daily_rows,
            initial_train_size=walk_forward_initial_train,
            test_size=walk_forward_test_size,
            embargo_days=walk_forward_embargo_days,
            holdout_start=spec.holdout_window.start,
        )
        window_holdout_oos_r2 = walk_forward[
            "window_holdout_oos_incremental_r_squared"
        ]

        # Cost gate on holdout OOS augmented forecasts.
        cost_gate = run_cost_gate(
            walk_forward["holdout_forecasts"],
            walk_forward["holdout_actuals"],
            walk_forward["holdout_window"],
            block_length=bootstrap_block_length,
            resamples=bootstrap_resamples,
            seed=bootstrap_seed,
        )

        # Verdict against the preregistered acceptance criteria.
        a_adjusted_p = holm[0]["adjusted_p_value"]
        a_partial_r2 = a["partial_r_squared"]
        criteria = {
            "holm_adjusted_a_p_below_0.05": bool(a_adjusted_p < 0.05),
            "a_partial_r_squared_at_least_0.005": bool(
                a_partial_r2 is not None
                and a_partial_r2 >= spec.minimum_effect_size
            ),
            "window_holdout_oos_incremental_r_squared_above_0": bool(
                window_holdout_oos_r2 is not None and window_holdout_oos_r2 > 0
            ),
            "net_daily_edge_after_costs_positive": bool(
                cost_gate["net_daily_edge"] > 0
            ),
        }
        metrics: dict[str, Any] = {
            "panel": {
                "daily_rows": int(daily_returns.shape[0]),
                "daily_first": daily_returns.index[0].isoformat(),
                "daily_last": daily_returns.index[-1].isoformat(),
                "daily_dropped_close_rows": daily.dropped_close_rows,
                "daily_dropped_return_rows": daily.dropped_return_rows,
                "hourly_rows": int(hourly_returns.shape[0]),
                "hourly_first": hourly_returns.index[0].isoformat(),
                "hourly_last": hourly_returns.index[-1].isoformat(),
                "hourly_dropped_close_rows": hourly.dropped_close_rows,
                "hourly_dropped_return_rows": hourly.dropped_return_rows,
                "dvol_rows": int(dvol.returns.shape[0]),
                "dvol_first": dvol.returns.index[0].isoformat(),
                "dvol_last": dvol.returns.index[-1].isoformat(),
                "dvol_dropped_close_rows": dvol.dropped_close_rows,
                "dvol_dropped_return_rows": dvol.dropped_return_rows,
            },
            "window": {
                "monthly_expiries": len(expiries),
                "quarterly_expiries": sum(
                    event.is_quarterly for event in expiries
                ),
                "first_expiry": expiries[0].expiry_date.isoformat(),
                "last_expiry": expiries[-1].expiry_date.isoformat(),
                "daily_regression_rows": int(daily_rows.shape[0]),
                "daily_window_rows": int(daily_rows["window"].sum()),
                "daily_nonwindow_rows": int((~daily_rows["window"]).sum()),
                "hourly_regression_rows": int(hourly_rows.shape[0]),
                "hourly_window_rows": int(hourly_rows["window"].sum()),
                "hourly_nonwindow_rows": int((~hourly_rows["window"]).sum()),
            },
            "tests": {
                "daily_btc_eth_interaction": a,
                "daily_btc_eth_interaction_no_factor": a_no_factor,
                "daily_btc_eth_window": b,
                "daily_btc_eth_window_no_factor": b_no_factor,
                "hourly_btc_eth_interaction": c,
                "hourly_btc_eth_interaction_no_factor": c_no_factor,
            },
            "holm": holm,
            "descriptive_splits": descriptive,
            "dvol_descriptive": dvol_descriptive,
            "walk_forward": {
                key: value
                for key, value in walk_forward.items()
                if key
                not in (
                    "holdout_test_indices",
                    "holdout_forecasts",
                    "holdout_actuals",
                    "holdout_window",
                )
            },
            "cost_gate": cost_gate,
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
    daily, hourly, dvol, manifest_info = load_panels()
    print(
        f"daily panel: {daily.row_count} rows, "
        f"{daily.first_time.date()} to {daily.last_time.date()}, "
        f"{daily.dropped_return_rows} dropped return rows"
    )
    print(
        f"hourly panel: {hourly.row_count} rows, "
        f"{hourly.first_time} to {hourly.last_time}, "
        f"{hourly.dropped_return_rows} dropped return rows"
    )
    print(
        f"dvol panel: {dvol.row_count} rows, "
        f"{dvol.first_time.date()} to {dvol.last_time.date()}, "
        f"{dvol.dropped_return_rows} dropped return rows"
    )
    print(f"data fingerprint: {manifest_info['manifest_sha256']}")
    trial_spec = build_trial_spec(
        spec,
        hypothesis_fingerprint=registration.spec_fingerprint,
        data_fingerprint=manifest_info["manifest_sha256"],
        code_revision=code_revision,
    )
    runner = ExperimentRunner(ROOT / "trials.jsonl", registry)
    receipt = runner.run(
        trial_spec,
        build_experiment(daily, hourly, dvol, spec),
    )
    print(f"trial {receipt.trial_id} completed: record {receipt.record_hash}")
    metrics = receipt.metrics
    a = metrics["tests"]["daily_btc_eth_interaction"]
    print(
        f"A: coefficient {a['coefficient']:.6f}, "
        f"p {a['p_value']:.4g}, "
        f"partial R2 {a['partial_r_squared']}"
    )
    print(f"holm: {metrics['holm']}")
    print(
        "window holdout OOS incremental R2: "
        f"{metrics['walk_forward']['window_holdout_oos_incremental_r_squared']}"
    )
    print(f"cost gate: {metrics['cost_gate']}")
    print(f"descriptive splits: {metrics['descriptive_splits']}")
    print(f"dvol descriptive: {metrics['dvol_descriptive']}")
    print(f"verdict supported: {metrics['verdict']['supported']}")


if __name__ == "__main__":
    main()
