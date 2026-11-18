"""Run trial T0013 for hypothesis H0011 v1 (event-study lag sensitivity).

Run after preregistration and fetching, from the repo root, with a
clean worktree (the trial records the HEAD commit as its code
revision):

    .venv/bin/python research/publication-lag-007/run_trial.py

The trial binds the preregistered H0011 v1 spec, the fetch manifest's
SHA-256 as the data fingerprint, and a canonical-JSON hash of the
analysis configuration. It re-runs study 005's constant-mean event
study with every FRED leg shifted one trading day on the series' own
dates (diff-then-join, with the shift between diff and join), so the
lagged change at availability date t is the original change at the
previous own date; Yahoo SPX is not shifted (market data is knowable
at the close). The lagged panel drops its first return row
(2003-01-03), which has no lagged change.

The lagged [0,+1] window in availability terms covers reference-date
changes [-1,0]: the statement-day change plus the day-before change,
not the day-after change. The verdict question is whether study 005's
TYVIX finding survives that shift — not whether study 005 was wrong:
both alignments are conditionally correct, under different
availability assumptions.

The trial runs:

1. the preregistered five-test Holm family on the lagged [0,+1]
   window (lagged TYVIX CAR < 0 one-sided primary; lagged VIX < 0
   one-sided; lagged DGS10, lagged BAA10Y two-sided; SPX unlagged
   two-sided as an internal correctness control);
2. descriptives (not in the family): the per-day abnormal-return
   decomposition (day -1, 0, +1 contributions, unlagged) and the
   unlagged replication of study 005 on the truncated panel index.

Two machinery guards are enforced inside the experiment and fail the
trial if they break:

- the SPX control must reproduce study 005's SPX CAR exactly
  (+0.000669, p=0.634 — the truncated index cannot change it, since
  the dropped first row is in no included event's estimation window);
- the same 135 events must be included, with the same three excluded
  (2003-01-29, 2003-03-18, 2004-11-10).

There is no walk-forward and no cost gate: an event study measures
announcement responses, not a forecast, so there is no trading rule
to cost. The verdict criteria are the preregistered ones: the
Holm-adjusted lagged TYVIX p-value below 0.05 and the standardized
mean lagged TYVIX CAR at or below -0.3.

Transforms (preregistered): VIX, TYVIX and SPX use log changes;
DGS10 and BAA10Y use level changes in basis points. The FRED legs
are lagged; SPX is not.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from myquant.adapters.fred import DAILY_CLOSE_UTC
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
from myquant.stats.event_study import EventStudyResult
from myquant.studies.event_windows import (
    constant_mean_expected_returns,
    filter_events_to_panel,
    one_sided_normal_p_value,
    run_constant_mean_event_study,
    standardized_mean_car,
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
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "publication-lag-007"
STUDY_005_ROOT = REPO_ROOT / "research" / "fomc-event-study-005"

HYPOTHESIS_ID = "H0011"
HYPOTHESIS_VERSION = 1
TRIAL_ID = "T0013"

VIX = "index:vix"
TYVIX = "index:tyvix"
DGS10 = "rates:us-10y-yield"
SPX = "index:sp500"
BAA10Y = "credit:baa-10y-spread"
MAIN_INSTRUMENTS = (VIX, TYVIX, DGS10, SPX, BAA10Y)
FRED_LOG_LEGS = (VIX, TYVIX)
FRED_BP_LEGS = (DGS10, BAA10Y)
MAIN_SAMPLE_END = date(2020, 5, 15)

# The preregistered five-test family, in preregistered order: the
# primary test first. Directions: "less" is a one-sided test of a
# negative mean CAR; "two-sided" uses the estimator's normal-reference
# two-sided p-value.
FAMILY: tuple[tuple[str, str, str], ...] = (
    ("tyvix_lagged_car", TYVIX, "less"),
    ("vix_lagged_car", VIX, "less"),
    ("dgs10_lagged_car", DGS10, "two-sided"),
    ("baa10y_lagged_car", BAA10Y, "two-sided"),
    ("spx_car", SPX, "two-sided"),
)

# Study 005 (T0010) ledger values, used as machinery guards: the SPX
# control and the unlagged replication must reproduce them exactly.
STUDY_005_SPX_COEF = 0.0006693574991539838
STUDY_005_SPX_P = 0.6342554696490699
STUDY_005_TYVIX_COEF = -0.03811195530617821
STUDY_005_VIX_COEF = -0.015517379813770384
STUDY_005_DGS10_COEF = -0.949925925925926
STUDY_005_BAA10Y_COEF = 0.2717037037037032
STUDY_005_INCLUDED_EVENTS = 135
STUDY_005_EXCLUDED_DATES = (
    date(2003, 1, 29),
    date(2003, 3, 18),
    date(2004, 11, 10),
)
MACHINERY_TOLERANCE = 1e-9


def load_panel() -> tuple[SynchronizedPanel, list[Any], dict[str, str]]:
    """Load the study 005 panel from the local PIT store."""
    manifest_path = ROOT / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    decision_time = datetime.fromisoformat(manifest["fetched_at"])
    if decision_time.tzinfo is None:
        decision_time = decision_time.replace(tzinfo=UTC)

    source_registry = SourceRegistry(ROOT / "sources")
    store = ParquetPITStore(CACHE_ROOT / "pit-1d", source_registry)
    observations = store.query_as_of(
        decision_time,
        instrument_ids=set(MAIN_INSTRUMENTS),
        fields={"close"},
    )
    main_cutoff = datetime.combine(MAIN_SAMPLE_END, DAILY_CLOSE_UTC, tzinfo=UTC)
    main_observations = [
        item for item in observations if item.event_time <= main_cutoff
    ]
    main_panel = build_synchronized_panel(
        main_observations,
        instruments=MAIN_INSTRUMENTS,
    )
    manifest_info = {
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "fetched_at": manifest["fetched_at"],
    }
    return main_panel, main_observations, manifest_info


def load_calendar() -> tuple[pd.Timestamp, ...]:
    """Scheduled statement timestamps (21:00 UTC), reused from study 005."""
    calendar = json.loads(
        (STUDY_005_ROOT / "fomc_calendar.json").read_text(encoding="utf-8")
    )
    return tuple(
        pd.Timestamp(
            datetime.combine(
                date.fromisoformat(meeting["statement_date"]),
                DAILY_CLOSE_UTC,
                tzinfo=UTC,
            )
        )
        for meeting in calendar["scheduled_meetings"]
    )


def build_lagged_transforms(
    panel: SynchronizedPanel,
    observations: list[Any],
    *,
    lag_steps: int,
) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    """Lagged FRED legs plus the unlagged SPX control.

    The lagged panel index drops the first ``lag_steps`` return rows
    (no lagged change exists there). FRED log legs and bp legs are
    computed per series on their own dates, shifted, then aligned;
    SPX comes from the panel's own returns on the truncated index.
    """
    index = lagged_panel_index(panel.returns.index, lag_steps)
    frame = pd.DataFrame(index=index)
    log_lagged = lagged_changes_on_index(
        observations,
        instruments=FRED_LOG_LEGS,
        index=index,
        lag_steps=lag_steps,
        transform="log",
    )
    bp_lagged = lagged_changes_on_index(
        observations,
        instruments=FRED_BP_LEGS,
        index=index,
        lag_steps=lag_steps,
        transform="level",
    )
    for leg in FRED_LOG_LEGS:
        frame[leg] = log_lagged[leg]
    for leg in FRED_BP_LEGS:
        frame[leg] = bp_lagged[leg]
    frame[SPX] = panel.returns.loc[index, SPX]
    return frame, index


def build_unlagged_transforms(
    panel: SynchronizedPanel,
    observations: list[Any],
    index: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Unlagged transforms on the same truncated index (descriptive).

    Replicates study 005 on the truncated index to isolate the
    truncation effect from the lag effect: the numbers must match
    study 005 exactly, since the dropped first row is in no included
    event's estimation window.
    """
    frame = panel.returns.loc[index, [VIX, TYVIX, SPX]].copy()
    bp_changes = level_changes_on_index(
        observations,
        instruments=FRED_BP_LEGS,
        index=index,
    )
    for leg in FRED_BP_LEGS:
        frame[leg] = bp_changes[leg]
    return frame


def event_test_metrics(
    result: EventStudyResult,
    *,
    direction: str,
) -> dict[str, Any]:
    """One family test's metrics from an event-study result."""
    if result.z_statistic is None or result.cluster_standard_error is None:
        raise ValueError("event-study inference is unavailable (fewer than 2 clusters)")
    if direction == "less":
        p_value = one_sided_normal_p_value(result.z_statistic, direction="less")
    elif direction == "two-sided":
        if result.two_sided_p_value is None:
            raise ValueError("two-sided p-value is unavailable")
        p_value = result.two_sided_p_value
    else:
        raise ValueError(f"unknown direction: {direction!r}")
    return {
        "observations": result.event_count,
        "coefficient": result.mean_cluster_car,
        "standard_error": result.cluster_standard_error,
        "t_statistic": result.z_statistic,
        "p_value": p_value,
        "partial_r_squared": None,
        "incremental_r_squared": None,
        "standardized_mean_car": standardized_mean_car(result),
        "cluster_count": result.cluster_count,
        "direction": direction,
    }


def per_day_ar_decomposition(
    transforms: pd.DataFrame,
    included: tuple[pd.Timestamp, ...],
    *,
    estimation_start_steps: int,
    estimation_end_steps: int,
) -> dict[str, Any]:
    """Mean abnormal return on days -1, 0 and +1 (unlagged, descriptive).

    AR = observed change minus the constant-mean expected change over
    the event's own estimation window. The lagged CAR[0,+1] is
    approximately the sum of the day -1 and day 0 mean ARs (the
    estimation window also shifts by one day, so the match is
    approximate, not exact); reporting the three days shows where the
    lagged effect comes from.
    """
    positions = {
        timestamp: position
        for position, timestamp in enumerate(transforms.index)
    }
    decomposition: dict[str, Any] = {}
    for leg in MAIN_INSTRUMENTS:
        expected = constant_mean_expected_returns(
            transforms[leg],
            included,
            estimation_start_steps=estimation_start_steps,
            estimation_end_steps=estimation_end_steps,
            pre_event_steps=1,
            post_event_steps=1,
        )
        abnormal = transforms[leg] - expected
        day_values: dict[str, list[float]] = {"-1": [], "0": [], "+1": []}
        for event in included:
            position = positions[event]
            for offset, key in ((-1, "-1"), (0, "0"), (1, "+1")):
                day_values[key].append(float(abnormal.iloc[position + offset]))
        decomposition[leg] = {
            "events": len(included),
            **{
                f"mean_ar_day_{key}": float(pd.Series(values).mean())
                for key, values in day_values.items()
            },
            "mean_ar_day_minus1_plus_day0": float(
                pd.Series(day_values["-1"]).mean()
                + pd.Series(day_values["0"]).mean()
            ),
        }
    return decomposition


def analysis_config(spec: HypothesisSpec) -> dict[str, Any]:
    """The exact analysis configuration, hashed as the config fingerprint."""
    return {
        "fixed_parameters": list(spec.fixed_parameters),
        "test_family": [name for name, _, _ in FAMILY],
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
        "trial_script": "research/publication-lag-007/run_trial.py",
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
            "FOMC event response under a one-day FRED publication lag: "
            "lagged CARs on [0,+1] for TYVIX, VIX, DGS10 and BAA10Y, "
            "with the SPX CAR unlagged as a control"
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
    main_panel: SynchronizedPanel,
    main_observations: list[Any],
    statements: tuple[pd.Timestamp, ...],
    spec: HypothesisSpec,
) -> Any:
    """Build the trial callback closing over the loaded panel."""

    def experiment(trial_spec: TrialSpec) -> dict[str, Any]:
        params = {item.name: item.value for item in trial_spec.parameters}
        estimation_start = int(params["estimation_start_steps"])
        estimation_end = int(params["estimation_end_steps"])
        pre_steps = int(params["event_pre_steps"])
        post_steps = int(params["event_post_steps"])
        lag_steps = int(params["lag_steps"])
        effect_threshold = float(params["standardized_effect_threshold"])

        lagged_transforms, lagged_index = build_lagged_transforms(
            main_panel,
            main_observations,
            lag_steps=lag_steps,
        )
        unlagged_transforms = build_unlagged_transforms(
            main_panel,
            main_observations,
            lagged_index,
        )

        main_cutoff = pd.Timestamp(
            datetime.combine(MAIN_SAMPLE_END, DAILY_CLOSE_UTC, tzinfo=UTC)
        )
        main_events = tuple(
            event for event in statements if event <= main_cutoff
        )
        included, excluded = filter_events_to_panel(
            lagged_index,
            main_events,
            estimation_start_steps=estimation_start,
            estimation_end_steps=estimation_end,
            pre_event_steps=pre_steps,
            post_event_steps=post_steps,
        )

        # Machinery guard 1: the same event set as study 005.
        excluded_dates = tuple(
            sorted(pd.Timestamp(item["event"]).date() for item in excluded)
        )
        if len(included) != STUDY_005_INCLUDED_EVENTS:
            raise ValueError(
                f"included events: {len(included)}, expected "
                f"{STUDY_005_INCLUDED_EVENTS} (study 005)"
            )
        if excluded_dates != tuple(sorted(STUDY_005_EXCLUDED_DATES)):
            raise ValueError(
                f"excluded events: {excluded_dates}, expected "
                f"{tuple(sorted(STUDY_005_EXCLUDED_DATES))} (study 005)"
            )

        # The preregistered five-test family on the lagged window.
        results: dict[str, EventStudyResult] = {}
        tests: dict[str, Any] = {}
        for test_name, leg, direction in FAMILY:
            result = run_constant_mean_event_study(
                lagged_transforms[leg],
                included,
                estimation_start_steps=estimation_start,
                estimation_end_steps=estimation_end,
                pre_event_steps=pre_steps,
                post_event_steps=post_steps,
            )
            results[leg] = result
            tests[test_name] = event_test_metrics(result, direction=direction)
        adjusted = adjust_pvalues(
            [tests[name]["p_value"] for name, _, _ in FAMILY],
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
            for (name, _, _), item in zip(FAMILY, adjusted, strict=True)
        ]

        # Machinery guard 2: the SPX control reproduces study 005.
        spx_test = tests["spx_car"]
        if abs(spx_test["coefficient"] - STUDY_005_SPX_COEF) > MACHINERY_TOLERANCE:
            raise ValueError(
                "SPX control does not reproduce study 005: coefficient "
                f"{spx_test['coefficient']}, expected {STUDY_005_SPX_COEF}"
            )
        if abs(spx_test["p_value"] - STUDY_005_SPX_P) > MACHINERY_TOLERANCE:
            raise ValueError(
                "SPX control does not reproduce study 005: p-value "
                f"{spx_test['p_value']}, expected {STUDY_005_SPX_P}"
            )

        # Descriptive: unlagged replication on the truncated index.
        replication: dict[str, Any] = {}
        expected_coefs = {
            TYVIX: STUDY_005_TYVIX_COEF,
            VIX: STUDY_005_VIX_COEF,
            DGS10: STUDY_005_DGS10_COEF,
            BAA10Y: STUDY_005_BAA10Y_COEF,
            SPX: STUDY_005_SPX_COEF,
        }
        for test_name, leg, direction in FAMILY:
            result = run_constant_mean_event_study(
                unlagged_transforms[leg],
                included,
                estimation_start_steps=estimation_start,
                estimation_end_steps=estimation_end,
                pre_event_steps=pre_steps,
                post_event_steps=post_steps,
            )
            metrics = event_test_metrics(result, direction=direction)
            if abs(metrics["coefficient"] - expected_coefs[leg]) > MACHINERY_TOLERANCE:
                raise ValueError(
                    f"unlagged replication does not reproduce study 005 "
                    f"for {leg}: coefficient {metrics['coefficient']}, "
                    f"expected {expected_coefs[leg]}"
                )
            replication[test_name] = metrics

        # Descriptive: per-day abnormal-return decomposition (unlagged).
        decomposition = per_day_ar_decomposition(
            unlagged_transforms,
            included,
            estimation_start_steps=estimation_start,
            estimation_end_steps=estimation_end,
        )

        # Per-event CARs on the lagged window (the primary data).
        car_frame = pd.DataFrame(
            {
                leg: {
                    event.event_time: event.cumulative_abnormal_return
                    for event in results[leg].events
                }
                for _, leg, _ in FAMILY
            }
        )
        event_cars = [
            {
                "event_time": timestamp.isoformat(),
                **{
                    leg: float(car_frame.loc[timestamp, leg])
                    for _, leg, _ in FAMILY
                },
            }
            for timestamp in car_frame.index
        ]

        # Verdict against the preregistered acceptance criteria.
        primary = tests["tyvix_lagged_car"]
        primary_adjusted_p = holm[0]["adjusted_p_value"]
        criteria = {
            "holm_adjusted_primary_p_below_0.05": bool(primary_adjusted_p < 0.05),
            "primary_standardized_mean_car_at_most_minus_0.3": bool(
                primary["standardized_mean_car"] <= -effect_threshold
            ),
        }
        metrics: dict[str, Any] = {
            "panel": {
                "daily_rows": int(lagged_index.shape[0]),
                "daily_first": lagged_index[0].isoformat(),
                "daily_last": lagged_index[-1].isoformat(),
                "daily_dropped_close_rows": main_panel.dropped_close_rows,
                "daily_dropped_return_rows": main_panel.dropped_return_rows,
                "unlagged_daily_rows": int(main_panel.returns.shape[0]),
                "unlagged_daily_first": main_panel.returns.index[0].isoformat(),
                "unlagged_daily_last": main_panel.returns.index[-1].isoformat(),
            },
            "events": {
                "scheduled_statements_total": len(statements),
                "main_sample_statements": len(main_events),
                "included": len(included),
                "excluded": [dict(item) for item in excluded],
                "first_included": included[0].isoformat(),
                "last_included": included[-1].isoformat(),
            },
            "tests": tests,
            "holm": holm,
            "descriptive_per_day_ar": decomposition,
            "descriptive_unlagged_replication": replication,
            "event_cars": event_cars,
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
    main_panel, main_obs, manifest_info = load_panel()
    print(
        f"main panel: {main_panel.row_count} rows, "
        f"{main_panel.first_time.date()} to {main_panel.last_time.date()}, "
        f"{main_panel.dropped_return_rows} dropped return rows"
    )
    statements = load_calendar()
    print(f"calendar: {len(statements)} scheduled statements")
    trial_spec = build_trial_spec(
        spec,
        hypothesis_fingerprint=registration.spec_fingerprint,
        data_fingerprint=manifest_info["manifest_sha256"],
        code_revision=code_revision,
    )
    runner = ExperimentRunner(ROOT / "trials.jsonl", registry)
    receipt = runner.run(
        trial_spec,
        build_experiment(main_panel, main_obs, statements, spec),
    )
    print(f"trial {receipt.trial_id} completed: record {receipt.record_hash}")
    metrics = receipt.metrics
    primary = metrics["tests"]["tyvix_lagged_car"]
    print(
        f"primary (lagged TYVIX CAR): mean {primary['coefficient']:.6f}, "
        f"standardized {primary['standardized_mean_car']:.4f}, "
        f"p {primary['p_value']:.4g}"
    )
    print(f"holm: {metrics['holm']}")
    print(f"events included: {metrics['events']['included']}")
    print(f"verdict supported: {metrics['verdict']['supported']}")


if __name__ == "__main__":
    main()
