"""Run trial T0007 for hypothesis H0006 (expiry-window volatility level).

Run after preregistration and fetching, from the repo root, with a clean
worktree (the trial records the HEAD commit as its code revision):

    .venv/bin/python research/options-expiry-004/run_trial_h0006.py

Trial numbering note: the first H0006 attempt ran as T0006 and failed
inside the experiment (a weights bug in the bootstrap series: the
weights omitted the sample-size factor, so the bootstrap point estimate
did not match the OLS coefficient and the trial's own guard raised).
The failure is recorded in the hash-chained ledger (T0006, status
failed) and the trial id is therefore taken; this corrected rerun uses
T0007. The bug was in the bootstrap interval's weights only — the HAC
inference and the effect ratio were unaffected — and the guard that
caught it is retained below.

The trial binds the preregistered H0006 v1 spec, this study's fetch
manifest SHA-256 as the data fingerprint, and a canonical-JSON hash of
the analysis configuration. It executes the preregistered two-test
family:

- (a) BTC: mean daily |log return| on expiry-window days vs
  non-window days.
- (b) ETH: the same comparison.

Inference: OLS of |log return| on the window indicator with Newey-West
HAC standard errors (max lag 10; absolute returns are more persistent
than returns). The block-bootstrap interval (block 10, 2000 resamples,
seed 42) for the window-minus-non-window mean difference is computed on
the weighted series whose mean is the difference of means. Effect size:
the ratio of window to non-window mean |log return|, threshold 1.15.

There is no walk-forward evaluation and no cost gate: H0006 is a
volatility-level comparison, not a forecast. The mean comparison uses
all daily rows in the sample period (train + validation + holdout); the
windows define the sample period, not a train/test split for this
hypothesis. The runner records the trial (including failures) in the
hash-chained ledger trials.jsonl; it does not decide acceptance.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
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
    adjust_pvalues,
    block_bootstrap_mean_ci,
    newey_west_hac,
    ols_fit,
)
from myquant.studies.expiry import (
    expiry_window_indicator,
    monthly_expiries,
    quarterly_window_indicator,
)
from myquant.studies.panel import SynchronizedPanel, build_synchronized_panel

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "options-expiry-004"

HYPOTHESIS_ID = "H0006"
HYPOTHESIS_VERSION = 1
TRIAL_ID = "T0007"

BTC = "crypto:btc-usdt-perp"
ETH = "crypto:eth-usdt-perp"
SOL = "crypto:sol-usdt-perp"
INSTRUMENTS = (BTC, ETH, SOL)


def load_panels() -> tuple[SynchronizedPanel, dict[str, Any]]:
    """Load the OKX daily panel."""
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
            instrument_ids=set(INSTRUMENTS),
            fields={"close"},
        ),
        instruments=INSTRUMENTS,
        bar_seconds=86_400,
    )
    manifest_info = {
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "fetched_at": manifest["fetched_at"],
    }
    return daily, manifest_info


def analysis_config(spec: HypothesisSpec) -> dict[str, Any]:
    """The exact analysis configuration, hashed as the config fingerprint."""
    return {
        "fixed_parameters": list(spec.fixed_parameters),
        "test_family": [
            "btc_mean_abs_return_comparison",
            "eth_mean_abs_return_comparison",
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
        "trial_script": "research/options-expiry-004/run_trial_h0006.py",
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
            "Expiry-window realized-volatility level: BTC/ETH mean "
            "daily |log return| on window vs non-window days, HAC "
            "inference and block-bootstrap interval"
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


def _mean_comparison_test(
    abs_returns: np.ndarray,
    is_window: np.ndarray,
    *,
    hac_max_lag: int,
    bootstrap_block_length: int,
    bootstrap_resamples: int,
    bootstrap_seed: int,
) -> dict[str, Any]:
    """Mean |log return| comparison: window vs non-window days.

    The p-value comes from OLS of |r| on the window indicator with
    Newey-West HAC standard errors. The block-bootstrap interval for the
    mean difference is computed on the weighted series whose mean is the
    difference of means: weights N/n_window on window rows and
    -N/n_nonwindow on non-window rows, where N is the total row count
    (the N factor is essential — with weights 1/n_window the series mean
    would be the difference divided by N). partial_r_squared is None: this
    is a mean comparison, not a nested lead-lag test; the window
    indicator's OLS R-squared is reported separately as window_r_squared
    and must not be read as a lead-lag partial R-squared.
    """
    window = np.asarray(is_window, dtype=bool)
    values = np.asarray(abs_returns, dtype=float)
    n_window = int(window.sum())
    n_nonwindow = int((~window).sum())
    mean_window = float(np.mean(values[window]))
    mean_nonwindow = float(np.mean(values[~window]))
    hac = newey_west_hac(
        values,
        {"window": window.astype(float)},
        max_lag=hac_max_lag,
    )
    effect = next(
        coefficient
        for coefficient in hac.coefficients
        if coefficient.name == "window"
    )
    if effect.p_value is None or effect.standard_error is None:
        raise ValueError("HAC inference is unavailable for the window effect")
    fit = ols_fit(values, {"window": window.astype(float)})
    n_total = int(values.size)
    weights = np.where(window, n_total / n_window, -n_total / n_nonwindow)
    weighted = weights * values
    interval = block_bootstrap_mean_ci(
        weighted,
        block_length=bootstrap_block_length,
        resamples=bootstrap_resamples,
        seed=bootstrap_seed,
    )
    # The OLS coefficient and the weighted-series mean are the same
    # quantity (difference of group means); a mismatch means a wiring bug.
    if abs(interval.point_estimate - effect.estimate) > 1e-9:
        raise ValueError(
            "bootstrap point estimate does not match the OLS coefficient: "
            f"{interval.point_estimate} vs {effect.estimate}"
        )
    return {
        "observations": int(values.size),
        "window_observations": n_window,
        "nonwindow_observations": n_nonwindow,
        "coefficient": effect.estimate,
        "standard_error": effect.standard_error,
        "t_statistic": effect.t_statistic,
        "p_value": effect.p_value,
        "partial_r_squared": None,
        "incremental_r_squared": None,
        "window_r_squared": fit.r_squared,
        "mean_window": mean_window,
        "mean_nonwindow": mean_nonwindow,
        "effect_ratio": mean_window / mean_nonwindow,
        "bootstrap_ci_lower": interval.lower_bound,
        "bootstrap_ci_upper": interval.upper_bound,
        "bootstrap_block_length": bootstrap_block_length,
        "bootstrap_resamples": bootstrap_resamples,
        "bootstrap_seed": bootstrap_seed,
    }


def _descriptive_ratio(
    abs_returns: np.ndarray,
    is_window: np.ndarray,
) -> dict[str, Any]:
    """Group means and ratio for a descriptive split: no p-values."""
    window = np.asarray(is_window, dtype=bool)
    values = np.asarray(abs_returns, dtype=float)
    mean_window = float(np.mean(values[window]))
    mean_nonwindow = float(np.mean(values[~window]))
    return {
        "observations": int(values.size),
        "window_observations": int(window.sum()),
        "nonwindow_observations": int((~window).sum()),
        "mean_window": mean_window,
        "mean_nonwindow": mean_nonwindow,
        "effect_ratio": mean_window / mean_nonwindow,
    }


def run_descriptive_splits(
    daily_returns: pd.DataFrame,
    *,
    expiries: tuple,
    window_days_before: int,
    window_days_after: int,
    wide_days_before: int,
    wide_days_after: int,
) -> dict[str, Any]:
    """Descriptive splits: wide window, quarterly, subperiods.

    Group means and ratios only; no p-values anywhere here: these splits
    are descriptive, not in the test family.
    """
    wide_flags = expiry_window_indicator(
        daily_returns.index,
        expiries,
        days_before=wide_days_before,
        days_after=wide_days_after,
    ).to_numpy(dtype=bool)
    quarterly_flags = quarterly_window_indicator(
        daily_returns.index,
        expiries,
        days_before=window_days_before,
        days_after=window_days_after,
    ).to_numpy(dtype=bool)
    full_flags = expiry_window_indicator(
        daily_returns.index,
        expiries,
        days_before=window_days_before,
        days_after=window_days_after,
    ).to_numpy(dtype=bool)
    monthly_only_flags = full_flags & ~quarterly_flags
    early_mask = daily_returns.index < datetime(2023, 1, 1, tzinfo=UTC)
    splits: dict[str, Any] = {}
    for label, instrument in (("btc", BTC), ("eth", ETH)):
        abs_values = np.abs(
            daily_returns[instrument].to_numpy(dtype=float)
        )
        splits[f"{label}_wide_window"] = _descriptive_ratio(
            abs_values, wide_flags
        )
        splits[f"{label}_quarterly_window"] = _descriptive_ratio(
            abs_values, quarterly_flags
        )
        splits[f"{label}_monthly_only_window"] = _descriptive_ratio(
            abs_values, monthly_only_flags
        )
        splits[f"{label}_subperiod_2021_2022"] = _descriptive_ratio(
            abs_values[early_mask], full_flags[early_mask]
        )
        splits[f"{label}_subperiod_2023_2026"] = _descriptive_ratio(
            abs_values[~early_mask], full_flags[~early_mask]
        )
    return splits


def build_experiment(
    daily: SynchronizedPanel,
    spec: HypothesisSpec,
) -> Any:
    """Build the trial callback closing over the loaded panel."""

    def experiment(trial_spec: TrialSpec) -> dict[str, Any]:
        params = {item.name: item.value for item in trial_spec.parameters}
        window_days_before = int(params["window_days_before"])
        window_days_after = int(params["window_days_after"])
        wide_days_before = int(params["wide_window_days_before"])
        wide_days_after = int(params["wide_window_days_after"])
        effect_ratio_threshold = float(params["effect_ratio_threshold"])
        hac_max_lag = int(params["abs_return_hac_max_lag"])
        bootstrap_block_length = int(params["bootstrap_block_length"])
        bootstrap_resamples = int(params["bootstrap_resamples"])
        bootstrap_seed = int(params["bootstrap_seed"])

        daily_returns = daily.returns
        expiries = monthly_expiries(
            daily_returns.index[0].date(), daily_returns.index[-1].date()
        )
        flags = expiry_window_indicator(
            daily_returns.index,
            expiries,
            days_before=window_days_before,
            days_after=window_days_after,
        ).to_numpy(dtype=bool)

        # The preregistered two-test family.
        btc = _mean_comparison_test(
            np.abs(daily_returns[BTC].to_numpy(dtype=float)),
            flags,
            hac_max_lag=hac_max_lag,
            bootstrap_block_length=bootstrap_block_length,
            bootstrap_resamples=bootstrap_resamples,
            bootstrap_seed=bootstrap_seed,
        )
        eth = _mean_comparison_test(
            np.abs(daily_returns[ETH].to_numpy(dtype=float)),
            flags,
            hac_max_lag=hac_max_lag,
            bootstrap_block_length=bootstrap_block_length,
            bootstrap_resamples=bootstrap_resamples,
            bootstrap_seed=bootstrap_seed,
        )
        adjusted = adjust_pvalues(
            [btc["p_value"], eth["p_value"]],
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
                    "btc_mean_abs_return_comparison",
                    "eth_mean_abs_return_comparison",
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
        )

        # Verdict against the preregistered acceptance criteria.
        btc_adjusted_p = holm[0]["adjusted_p_value"]
        btc_ratio = btc["effect_ratio"]
        criteria = {
            "holm_adjusted_btc_p_below_0.05": bool(btc_adjusted_p < 0.05),
            "btc_effect_ratio_at_least_1.15": bool(
                btc_ratio >= effect_ratio_threshold
            ),
        }
        metrics: dict[str, Any] = {
            "panel": {
                "daily_rows": int(daily_returns.shape[0]),
                "daily_first": daily_returns.index[0].isoformat(),
                "daily_last": daily_returns.index[-1].isoformat(),
                "daily_dropped_close_rows": daily.dropped_close_rows,
                "daily_dropped_return_rows": daily.dropped_return_rows,
            },
            "window": {
                "monthly_expiries": len(expiries),
                "quarterly_expiries": sum(
                    event.is_quarterly for event in expiries
                ),
                "first_expiry": expiries[0].expiry_date.isoformat(),
                "last_expiry": expiries[-1].expiry_date.isoformat(),
                "daily_rows": int(daily_returns.shape[0]),
                "daily_window_rows": int(flags.sum()),
                "daily_nonwindow_rows": int((~flags).sum()),
            },
            "tests": {
                "btc_mean_abs_return_comparison": btc,
                "eth_mean_abs_return_comparison": eth,
            },
            "holm": holm,
            "descriptive_splits": descriptive,
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
        build_experiment(daily, spec),
    )
    print(f"trial {receipt.trial_id} completed: record {receipt.record_hash}")
    metrics = receipt.metrics
    btc = metrics["tests"]["btc_mean_abs_return_comparison"]
    print(
        f"BTC: mean diff {btc['coefficient']:.6f}, "
        f"p {btc['p_value']:.4g}, "
        f"ratio {btc['effect_ratio']:.4f}, "
        f"CI [{btc['bootstrap_ci_lower']:.6f}, {btc['bootstrap_ci_upper']:.6f}]"
    )
    print(f"holm: {metrics['holm']}")
    print(f"descriptive splits: {metrics['descriptive_splits']}")
    print(f"verdict supported: {metrics['verdict']['supported']}")


if __name__ == "__main__":
    main()
