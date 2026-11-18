"""Run trial T0002 for hypothesis H0002 (low-volatility transmission).

Run after preregistration and fetching, from the repo root, with a clean
worktree (the trial records the HEAD commit as its code revision):

    .venv/bin/python research/lowvol-002/run_trial.py

The trial binds the preregistered H0002 v1 spec, this study's fetch
manifest SHA-256 as the data fingerprint (the manifest embeds the OKX
input state from study 001's cache), and a canonical-JSON hash of the
analysis configuration. It executes the preregistered four-test family:

- A1 (primary): daily BTC→SOL interaction test — SOL[t+1] on SOL[t],
  ETH[t] (factor), BTC[t] and BTC[t]×lowvol[t], HAC standard errors,
  testing the interaction coefficient.
- A2: daily BTC→SOL partial lead-lag on low-volatility rows only.
- B1: 1H BTC→ETH interaction test (SOL factor control).
- B2: 1H BTC→ETH partial lead-lag on low-volatility rows only.

Plus the preregistered regime-aware purged walk-forward evaluation
(low-volatility holdout rows only), the cost gate (positions only on
low-volatility holdout rows), and the Hyperliquid cross-venue check
(descriptive only, not in the test family).

Regime labels are PIT-correct (trailing/expanding medians over strictly
prior realized volatility); see myquant.studies.regime. The runner
records the trial (including failures) in the hash-chained ledger
trials.jsonl; it does not decide acceptance.
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
from myquant.studies.panel import SynchronizedPanel, build_synchronized_panel
from myquant.studies.regime import (
    NestedLeadLagTest,
    classify_low_volatility,
    nested_lead_lag_test,
)

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
OKX_CACHE_ROOT = REPO_ROOT / "data" / "cache" / "btc-eth-001"
HL_CACHE_ROOT = REPO_ROOT / "data" / "cache" / "lowvol-002"

HYPOTHESIS_ID = "H0002"
HYPOTHESIS_VERSION = 1
TRIAL_ID = "T0002"

BTC = "crypto:btc-usdt-perp"
ETH = "crypto:eth-usdt-perp"
SOL = "crypto:sol-usdt-perp"
INSTRUMENTS = (BTC, ETH, SOL)

# Preregistered cost assumption: OKX VIP0 taker 0.05% per side.
TAKER_FEE_PER_SIDE = 0.0005
ROUND_TRIP_COST = 0.001


def load_panels() -> tuple[SynchronizedPanel, SynchronizedPanel, SynchronizedPanel, dict[str, Any]]:
    """Load the OKX daily/1H panels and the Hyperliquid daily panel."""
    manifest_path = ROOT / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    decision_time = datetime.fromisoformat(manifest["fetched_at"])
    if decision_time.tzinfo is None:
        decision_time = decision_time.replace(tzinfo=UTC)

    source_registry = SourceRegistry(ROOT / "sources")
    daily_store = ParquetPITStore(OKX_CACHE_ROOT / "pit-1d", source_registry)
    hourly_store = ParquetPITStore(OKX_CACHE_ROOT / "pit-1h", source_registry)
    hl_store = ParquetPITStore(HL_CACHE_ROOT / "pit-1d-hl", source_registry)
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
    hyperliquid = build_synchronized_panel(
        hl_store.query_as_of(
            decision_time,
            instrument_ids=set(INSTRUMENTS),
            fields={"close"},
        ),
        instruments=INSTRUMENTS,
        bar_seconds=86_400,
    )
    manifest_info = {
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "fetched_at": manifest["fetched_at"],
        "okx_manifest_sha256": manifest["okx_inputs"]["manifest_sha256"],
    }
    return daily, hourly, hyperliquid, manifest_info


def analysis_config(spec: HypothesisSpec) -> dict[str, Any]:
    """The exact analysis configuration, hashed as the config fingerprint."""
    return {
        "fixed_parameters": list(spec.fixed_parameters),
        "test_family": [
            "daily_btc_sol_interaction",
            "daily_btc_sol_lowvol",
            "hourly_btc_eth_interaction",
            "hourly_btc_eth_lowvol",
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
        "trial_script": "research/lowvol-002/run_trial.py",
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
            "Low-volatility regime-conditional BTC transmission: daily "
            "BTC→SOL and 1H BTC→ETH interaction and subsample tests, "
            "regime-aware purged walk-forward OOS evaluation and taker-cost gate"
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
    is_low_vol: pd.Series,
) -> pd.DataFrame:
    """Align one-bar-ahead regression rows and attach regime labels.

    Row j predicts the target return over bar j+1 from predictors known
    at bar j's close (target, factor and source returns over bar j, plus
    the regime label for bar j). Rows without a regime label are dropped.
    """
    target_values = returns[target].to_numpy(dtype=float)
    factor_values = returns[factor].to_numpy(dtype=float)
    source_values = returns[BTC].to_numpy(dtype=float)
    labels = is_low_vol.reindex(returns.index[:-1])
    rows = pd.DataFrame(
        {
            "target_next": target_values[1:],
            "target_lag": target_values[:-1],
            "factor": factor_values[:-1],
            "btc": source_values[:-1],
            "lowvol": labels.to_numpy(dtype=float),
        },
        index=returns.index[:-1],
    )
    rows = rows.dropna(subset=["lowvol"])
    rows["lowvol"] = rows["lowvol"].astype(bool)
    rows["interaction"] = rows["btc"] * rows["lowvol"].astype(float)
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
    """A1/B1: test the BTC×lowvol interaction over the full labelled rows."""
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
    """A2/B2: partial lead-lag on low-volatility rows only."""
    lowvol_rows = rows[rows["lowvol"]]
    base: dict[str, np.ndarray] = {
        "target_lag": lowvol_rows["target_lag"].to_numpy(dtype=float),
    }
    if with_factor:
        base["factor"] = lowvol_rows["factor"].to_numpy(dtype=float)
    result = nested_lead_lag_test(
        lowvol_rows["target_next"].to_numpy(dtype=float),
        base,
        {"source": lowvol_rows["btc"].to_numpy(dtype=float)},
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
    """Regime-aware purged walk-forward OOS evaluation of the A1 model.

    Base model: target lag + factor + BTC (no interaction). Augmented
    model: base + BTC×lowvol. Regression row j uses predictors known at
    bar j's close to forecast the target return over bar j+1, known at
    bar j+1's close — two days after row j's bar open. Hence label_end =
    decision_time + 2 days. Scoring is reported on all test rows, on
    holdout test rows, and on low-volatility holdout test rows (the
    preregistered acceptance criterion).
    """
    target = rows["target_next"].to_numpy(dtype=float)
    predictors = {
        "target_lag": rows["target_lag"].to_numpy(dtype=float),
        "factor": rows["factor"].to_numpy(dtype=float),
        "btc": rows["btc"].to_numpy(dtype=float),
        "interaction": rows["interaction"].to_numpy(dtype=float),
    }
    lowvol = rows["lowvol"].to_numpy(dtype=bool)
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
    lowvol_holdout_folds = restricted_folds(
        lambda index: decision_times[index] >= holdout_start and lowvol[index]
    )
    lowvol_holdout_evaluation = evaluate_walk_forward_forecasts(
        target,
        baseline_forecasts,
        augmented_forecasts,
        folds=lowvol_holdout_folds,
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
        "lowvol_holdout_folds": len(lowvol_holdout_folds),
        "lowvol_holdout_test_rows": int(
            lowvol_holdout_evaluation.observations
        ),
        "lowvol_holdout_oos_incremental_r_squared": (
            lowvol_holdout_evaluation.incremental_oos_r_squared
        ),
        "lowvol_holdout_baseline_mse": lowvol_holdout_evaluation.baseline_mse,
        "lowvol_holdout_augmented_mse": lowvol_holdout_evaluation.augmented_mse,
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
        "holdout_lowvol": [bool(lowvol[index]) for index in holdout_test_rows],
    }


def run_cost_gate(
    forecasts: list[float],
    actuals: list[float],
    lowvol: list[bool],
    *,
    block_length: int,
    resamples: int,
    seed: int,
) -> dict[str, Any]:
    """Sign rule on OOS forecasts, positioned on low-volatility rows only.

    1x, flat on high-volatility rows. Entry from flat and final exit cost
    one taker side each (0.05%); a direction flip costs a full round trip
    (0.10%). Returns are log returns, used as the P&L proxy for a 1x
    position. The net daily edge is averaged over all holdout test rows,
    including flat high-volatility rows.
    """
    positions = np.where(
        np.asarray(lowvol, dtype=bool),
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
        "lowvol_days": int(np.count_nonzero(lowvol)),
        "gross_daily_edge": float(np.mean(gross)),
        "flips": flips,
        "total_cost": float(np.sum(costs)),
        "net_daily_edge": float(np.mean(net)),
        "net_edge_ci_lower": interval.lower_bound,
        "net_edge_ci_upper": interval.upper_bound,
        "net_edge_bootstrap_p_value": test.p_value,
    }


def run_cross_venue_check(
    returns: pd.DataFrame,
    *,
    is_low_vol: pd.Series,
) -> dict[str, Any]:
    """Descriptive Hyperliquid BTC→ETH low-volatility subsample check.

    Reports the correlation, OLS slope, R-squared and factor-controlled
    coefficient on low-volatility rows only. No p-values are reported:
    this check is descriptive, is not in the test family, and same-period
    Hyperliquid prices are highly correlated with OKX prices, so it
    cannot serve as independent evidence.
    """
    rows = build_regression_rows(
        returns, target=ETH, factor=SOL, is_low_vol=is_low_vol
    )
    lowvol_rows = rows[rows["lowvol"]]
    source = lowvol_rows["btc"].to_numpy(dtype=float)
    target = lowvol_rows["target_next"].to_numpy(dtype=float)
    fit = ols_fit(target, {"btc": source})
    controlled = nested_lead_lag_test(
        target,
        {
            "target_lag": lowvol_rows["target_lag"].to_numpy(dtype=float),
            "factor": lowvol_rows["factor"].to_numpy(dtype=float),
        },
        {"source": source},
        effect_name="source",
        max_hac_lag=5,
    )
    return {
        "observations": int(source.size),
        "correlation": float(np.corrcoef(source, target)[0, 1]),
        "ols_slope": fit.coefficients[1],
        "ols_r_squared": fit.r_squared,
        "controlled_coefficient": controlled.coefficient,
        "controlled_partial_r_squared": controlled.partial_r_squared,
        "labelled_rows": int(rows.shape[0]),
        "lowvol_rows": int(lowvol_rows.shape[0]),
    }


def build_experiment(
    daily: SynchronizedPanel,
    hourly: SynchronizedPanel,
    hyperliquid: SynchronizedPanel,
    spec: HypothesisSpec,
) -> Any:
    """Build the trial callback closing over the loaded panels."""

    def experiment(trial_spec: TrialSpec) -> dict[str, Any]:
        params = {item.name: item.value for item in trial_spec.parameters}
        daily_max_hac_lag = int(params["daily_max_hac_lag"])
        hourly_max_hac_lag = int(params["hourly_max_hac_lag"])
        bootstrap_block_length = int(params["bootstrap_block_length"])
        bootstrap_resamples = int(params["bootstrap_resamples"])
        bootstrap_seed = int(params["bootstrap_seed"])
        walk_forward_initial_train = int(params["walk_forward_initial_train"])
        walk_forward_test_size = int(params["walk_forward_test_size"])
        walk_forward_embargo_days = int(params["walk_forward_embargo_days"])
        hourly_holdout_start = datetime.fromisoformat(
            params["hourly_holdout_start"]
        )

        daily_returns = daily.returns
        hourly_returns = hourly.returns
        hl_returns = hyperliquid.returns

        # PIT-correct regime labels: daily from SOL returns (test A
        # target), 1H from ETH returns (test B target), Hyperliquid from
        # ETH returns (test C target).
        daily_regime = classify_low_volatility(
            daily_returns[SOL],
            rv_window=int(params["rv_window_days"]),
            median_window=int(params["daily_median_window"]),
        )
        hourly_regime = classify_low_volatility(
            hourly_returns[ETH],
            rv_window=int(params["rv_window_hours"]),
            min_prior_values=int(params["hourly_median_min_prior"]),
        )
        hl_regime = classify_low_volatility(
            hl_returns[ETH],
            rv_window=int(params["rv_window_days"]),
            median_window=int(params["daily_median_window"]),
        )

        daily_rows = build_regression_rows(
            daily_returns,
            target=SOL,
            factor=ETH,
            is_low_vol=daily_regime.is_low_vol,
        )
        hourly_rows = build_regression_rows(
            hourly_returns,
            target=ETH,
            factor=SOL,
            is_low_vol=hourly_regime.is_low_vol,
        )

        # The preregistered four-test family, plus no-factor upper-bound
        # controls (not in the family).
        a1 = _interaction_test(
            daily_rows, with_factor=True, max_hac_lag=daily_max_hac_lag
        )
        a1_no_factor = _interaction_test(
            daily_rows, with_factor=False, max_hac_lag=daily_max_hac_lag
        )
        a2 = _subsample_test(
            daily_rows, with_factor=True, max_hac_lag=daily_max_hac_lag
        )
        a2_no_factor = _subsample_test(
            daily_rows, with_factor=False, max_hac_lag=daily_max_hac_lag
        )
        b1 = _interaction_test(
            hourly_rows, with_factor=True, max_hac_lag=hourly_max_hac_lag
        )
        b1_no_factor = _interaction_test(
            hourly_rows, with_factor=False, max_hac_lag=hourly_max_hac_lag
        )
        b2 = _subsample_test(
            hourly_rows, with_factor=True, max_hac_lag=hourly_max_hac_lag
        )
        b2_no_factor = _subsample_test(
            hourly_rows, with_factor=False, max_hac_lag=hourly_max_hac_lag
        )
        adjusted = adjust_pvalues(
            [a1["p_value"], a2["p_value"], b1["p_value"], b2["p_value"]],
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
                    "daily_btc_sol_interaction",
                    "daily_btc_sol_lowvol",
                    "hourly_btc_eth_interaction",
                    "hourly_btc_eth_lowvol",
                ),
                adjusted,
                strict=True,
            )
        ]

        # Descriptive 1H stability: B1 on each half of the preregistered
        # 1H split. Coefficients and partial R-squared only, no p-values.
        first_half = hourly_rows[hourly_rows.index < hourly_holdout_start]
        second_half = hourly_rows[hourly_rows.index >= hourly_holdout_start]
        stability = {}
        for label, subset in (
            ("first_60_days", first_half),
            ("last_30_days", second_half),
        ):
            result = _interaction_test(
                subset, with_factor=True, max_hac_lag=hourly_max_hac_lag
            )
            stability[label] = {
                "observations": result["observations"],
                "coefficient": result["coefficient"],
                "partial_r_squared": result["partial_r_squared"],
            }

        # Regime-aware purged walk-forward OOS evaluation (daily A1 model).
        walk_forward = run_walk_forward(
            daily_rows,
            initial_train_size=walk_forward_initial_train,
            test_size=walk_forward_test_size,
            embargo_days=walk_forward_embargo_days,
            holdout_start=spec.holdout_window.start,
        )
        lowvol_holdout_oos_r2 = walk_forward[
            "lowvol_holdout_oos_incremental_r_squared"
        ]

        # Cost gate on holdout OOS augmented forecasts.
        cost_gate = run_cost_gate(
            walk_forward["holdout_forecasts"],
            walk_forward["holdout_actuals"],
            walk_forward["holdout_lowvol"],
            block_length=bootstrap_block_length,
            resamples=bootstrap_resamples,
            seed=bootstrap_seed,
        )

        # Descriptive Hyperliquid cross-venue check.
        cross_venue = run_cross_venue_check(
            hl_returns,
            is_low_vol=hl_regime.is_low_vol,
        )

        # Verdict against the preregistered acceptance criteria.
        a1_adjusted_p = holm[0]["adjusted_p_value"]
        a1_partial_r2 = a1["partial_r_squared"]
        criteria = {
            "holm_adjusted_a1_p_below_0.05": bool(a1_adjusted_p < 0.05),
            "a1_partial_r_squared_at_least_0.005": bool(
                a1_partial_r2 is not None
                and a1_partial_r2 >= spec.minimum_effect_size
            ),
            "lowvol_holdout_oos_incremental_r_squared_above_0": bool(
                lowvol_holdout_oos_r2 is not None and lowvol_holdout_oos_r2 > 0
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
                "hyperliquid_rows": int(hl_returns.shape[0]),
                "hyperliquid_first": hl_returns.index[0].isoformat(),
                "hyperliquid_last": hl_returns.index[-1].isoformat(),
                "hyperliquid_dropped_close_rows": hyperliquid.dropped_close_rows,
                "hyperliquid_dropped_return_rows": (
                    hyperliquid.dropped_return_rows
                ),
            },
            "regime": {
                "daily_excluded_rows": daily_regime.excluded_rows,
                "daily_labelled_rows": daily_regime.labelled_rows,
                "daily_lowvol_rows": daily_regime.low_vol_rows,
                "daily_highvol_rows": daily_regime.high_vol_rows,
                "daily_regression_rows": int(daily_rows.shape[0]),
                "hourly_excluded_rows": hourly_regime.excluded_rows,
                "hourly_labelled_rows": hourly_regime.labelled_rows,
                "hourly_lowvol_rows": hourly_regime.low_vol_rows,
                "hourly_highvol_rows": hourly_regime.high_vol_rows,
                "hourly_regression_rows": int(hourly_rows.shape[0]),
                "hyperliquid_excluded_rows": hl_regime.excluded_rows,
                "hyperliquid_labelled_rows": hl_regime.labelled_rows,
                "hyperliquid_lowvol_rows": hl_regime.low_vol_rows,
                "hyperliquid_highvol_rows": hl_regime.high_vol_rows,
            },
            "tests": {
                "daily_btc_sol_interaction": a1,
                "daily_btc_sol_interaction_no_factor": a1_no_factor,
                "daily_btc_sol_lowvol": a2,
                "daily_btc_sol_lowvol_no_factor": a2_no_factor,
                "hourly_btc_eth_interaction": b1,
                "hourly_btc_eth_interaction_no_factor": b1_no_factor,
                "hourly_btc_eth_lowvol": b2,
                "hourly_btc_eth_lowvol_no_factor": b2_no_factor,
            },
            "holm": holm,
            "hourly_stability": stability,
            "walk_forward": {
                key: value
                for key, value in walk_forward.items()
                if key
                not in (
                    "holdout_test_indices",
                    "holdout_forecasts",
                    "holdout_actuals",
                    "holdout_lowvol",
                )
            },
            "cost_gate": cost_gate,
            "cross_venue": cross_venue,
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
    daily, hourly, hyperliquid, manifest_info = load_panels()
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
        f"hyperliquid panel: {hyperliquid.row_count} rows, "
        f"{hyperliquid.first_time.date()} to {hyperliquid.last_time.date()}, "
        f"{hyperliquid.dropped_return_rows} dropped return rows"
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
        build_experiment(daily, hourly, hyperliquid, spec),
    )
    print(f"trial {receipt.trial_id} completed: record {receipt.record_hash}")
    metrics = receipt.metrics
    a1 = metrics["tests"]["daily_btc_sol_interaction"]
    print(
        f"A1: coefficient {a1['coefficient']:.6f}, "
        f"p {a1['p_value']:.4g}, "
        f"partial R2 {a1['partial_r_squared']}"
    )
    print(f"holm: {metrics['holm']}")
    print(
        "low-vol holdout OOS incremental R2: "
        f"{metrics['walk_forward']['lowvol_holdout_oos_incremental_r_squared']}"
    )
    print(f"cost gate: {metrics['cost_gate']}")
    print(f"cross-venue: {metrics['cross_venue']}")
    print(f"verdict supported: {metrics['verdict']['supported']}")


if __name__ == "__main__":
    main()
