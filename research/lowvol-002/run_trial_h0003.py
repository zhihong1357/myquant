"""Run trial T0003 for hypothesis H0003 (forward low-volatility test).

Run only when check_h0003_sample.py reports the forward sample ready,
after refreshing the OKX cache, from the repo root, with a clean
worktree (the trial records the HEAD commit as its code revision):

    .venv/bin/python research/btc-eth-001/fetch_data.py
    .venv/bin/python research/lowvol-002/check_h0003_sample.py
    .venv/bin/python research/lowvol-002/run_trial_h0003.py

The trial binds the preregistered H0003 v1 spec, study 001's manifest
SHA-256 as the data fingerprint, and a canonical-JSON hash of the
analysis configuration. It tests the original BTC→ETH daily pair on
forward rows only (decision time on or after 2026-11-18T16:00Z and
before 2027-03-31T16:00Z): the interaction test plus the
low-volatility-subsample test, Holm family of 2.

The sample-size gate runs BEFORE any test statistic is computed and
before the trial is recorded: with fewer than 60 low-volatility forward
rows the script prints a message and exits without touching the ledger
or the hypothesis state.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
from myquant.stats import adjust_pvalues
from myquant.studies.panel import SynchronizedPanel, build_synchronized_panel
from myquant.studies.regime import (
    classify_low_volatility,
    nested_lead_lag_test,
)

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
OKX_CACHE_ROOT = REPO_ROOT / "data" / "cache" / "btc-eth-001"
STUDY_001_ROOT = REPO_ROOT / "research" / "btc-eth-001"

HYPOTHESIS_ID = "H0003"
HYPOTHESIS_VERSION = 1
TRIAL_ID = "T0003"

BTC = "crypto:btc-usdt-perp"
ETH = "crypto:eth-usdt-perp"
SOL = "crypto:sol-usdt-perp"
INSTRUMENTS = (BTC, ETH, SOL)


def load_daily_panel() -> tuple[SynchronizedPanel, dict[str, Any]]:
    """Load the OKX daily panel from study 001's (refreshed) cache."""
    manifest_path = STUDY_001_ROOT / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    decision_time = datetime.fromisoformat(manifest["fetched_at"])
    if decision_time.tzinfo is None:
        decision_time = decision_time.replace(tzinfo=UTC)
    source_registry = SourceRegistry(ROOT / "sources")
    store = ParquetPITStore(OKX_CACHE_ROOT / "pit-1d", source_registry)
    panel = build_synchronized_panel(
        store.query_as_of(
            decision_time,
            instrument_ids=set(INSTRUMENTS),
            fields={"close"},
        ),
        instruments=INSTRUMENTS,
        bar_seconds=86_400,
    )
    return panel, {
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "fetched_at": manifest["fetched_at"],
    }


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
    Mirrors run_trial.py; the two trial scripts are intentionally
    self-contained so either can run on its own.
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


def analysis_config(spec: HypothesisSpec) -> dict[str, Any]:
    """The exact analysis configuration, hashed as the config fingerprint."""
    return {
        "fixed_parameters": list(spec.fixed_parameters),
        "test_family": [
            "forward_btc_eth_interaction",
            "forward_btc_eth_lowvol",
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
        "trial_script": "research/lowvol-002/run_trial_h0003.py",
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
            "Forward low-volatility BTC→ETH daily transmission: "
            "interaction and low-volatility-subsample tests on bars "
            "observed after preregistration"
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
    forward_rows: pd.DataFrame,
    spec: HypothesisSpec,
) -> Any:
    """Build the trial callback closing over the forward rows."""

    def experiment(trial_spec: TrialSpec) -> dict[str, Any]:
        params = {item.name: item.value for item in trial_spec.parameters}
        max_hac_lag = int(params["daily_max_hac_lag"])
        target = forward_rows["target_next"].to_numpy(dtype=float)
        base = {
            "target_lag": forward_rows["target_lag"].to_numpy(dtype=float),
            "factor": forward_rows["factor"].to_numpy(dtype=float),
            "btc": forward_rows["btc"].to_numpy(dtype=float),
        }
        interaction = nested_lead_lag_test(
            target,
            base,
            {"interaction": forward_rows["interaction"].to_numpy(dtype=float)},
            effect_name="interaction",
            max_hac_lag=max_hac_lag,
        )
        lowvol_rows = forward_rows[forward_rows["lowvol"]]
        subsample = nested_lead_lag_test(
            lowvol_rows["target_next"].to_numpy(dtype=float),
            {
                "target_lag": lowvol_rows["target_lag"].to_numpy(dtype=float),
                "factor": lowvol_rows["factor"].to_numpy(dtype=float),
            },
            {"source": lowvol_rows["btc"].to_numpy(dtype=float)},
            effect_name="source",
            max_hac_lag=max_hac_lag,
        )
        if interaction.p_value is None or subsample.p_value is None:
            raise ValueError("HAC p-value is unavailable; cannot form the test family")
        adjusted = adjust_pvalues(
            [interaction.p_value, subsample.p_value],
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
                ("forward_btc_eth_interaction", "forward_btc_eth_lowvol"),
                adjusted,
                strict=True,
            )
        ]

        def test_metrics(result: Any) -> dict[str, Any]:
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

        criteria = {
            "holm_adjusted_interaction_p_below_0.05": bool(
                holm[0]["adjusted_p_value"] < 0.05
            ),
            "interaction_partial_r_squared_at_least_0.005": bool(
                interaction.partial_r_squared is not None
                and interaction.partial_r_squared >= spec.minimum_effect_size
            ),
        }
        return {
            "forward_rows": int(forward_rows.shape[0]),
            "lowvol_forward_rows": int(lowvol_rows.shape[0]),
            "first_forward_bar": forward_rows.index[0].isoformat(),
            "last_forward_bar": forward_rows.index[-1].isoformat(),
            "tests": {
                "forward_btc_eth_interaction": test_metrics(interaction),
                "forward_btc_eth_lowvol": test_metrics(subsample),
            },
            "holm": holm,
            "verdict": {
                "criteria": criteria,
                "supported": bool(all(criteria.values())),
            },
        }

    return experiment


def main() -> None:
    registry = HypothesisRegistry(ROOT / "hypotheses")
    registration = registry.get(HYPOTHESIS_ID, version=HYPOTHESIS_VERSION)
    spec = registration.spec
    params = {
        item.split("=", maxsplit=1)[0]: item.split("=", maxsplit=1)[1]
        for item in spec.fixed_parameters
    }
    forward_start = datetime.fromisoformat(params["forward_window_start"])
    minimum_lowvol_rows = int(params["minimum_lowvol_rows"])
    code_revision = git_head_revision(REPO_ROOT)
    if code_revision is None:
        raise RuntimeError("could not determine the git HEAD revision")
    panel, manifest_info = load_daily_panel()
    print(
        f"daily panel: {panel.row_count} rows, "
        f"{panel.first_time.date()} to {panel.last_time.date()}"
    )
    regime = classify_low_volatility(
        panel.returns[ETH],
        rv_window=int(params["rv_window_days"]),
        median_window=int(params["daily_median_window"]),
    )
    rows = build_regression_rows(
        panel.returns,
        target=ETH,
        factor=SOL,
        is_low_vol=regime.is_low_vol,
    )
    forward_rows = rows[
        (rows.index >= forward_start)
        & (rows.index < spec.holdout_window.end)
    ]
    lowvol_forward_rows = int(forward_rows["lowvol"].sum())
    print(
        f"forward rows: {len(forward_rows)}, low-volatility forward rows: "
        f"{lowvol_forward_rows} / {minimum_lowvol_rows}"
    )
    # Sample-size gate: refuse before any test statistic is computed and
    # before the trial is recorded.
    if lowvol_forward_rows < minimum_lowvol_rows:
        print(
            "H0003 forward sample is not ready yet; no trial is recorded. "
            "Re-run check_h0003_sample.py later."
        )
        return
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
        build_experiment(forward_rows, spec),
    )
    print(f"trial {receipt.trial_id} completed: record {receipt.record_hash}")
    metrics = receipt.metrics
    interaction = metrics["tests"]["forward_btc_eth_interaction"]
    print(
        f"interaction: coefficient {interaction['coefficient']:.6f}, "
        f"p {interaction['p_value']:.4g}, "
        f"partial R2 {interaction['partial_r_squared']}"
    )
    print(f"holm: {metrics['holm']}")
    print(f"verdict supported: {metrics['verdict']['supported']}")


if __name__ == "__main__":
    main()
