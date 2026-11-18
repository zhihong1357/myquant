"""Run trial T0010 for hypothesis H0007 v1 (FOMC event response).

Run after preregistration and fetching, from the repo root, with a
clean worktree (the trial records the HEAD commit as its code
revision):

    .venv/bin/python research/fomc-event-study-005/run_trial.py

Trial T0008 (the first attempt) failed inside the experiment on an
over-strict cycle-boundary guard that required every preregistered
cycle boundary to be a scheduled statement day; the guard caught a
one-day transcription error in the v1 spec (cycle_hiking_2 starts
2015-12-17, but the December 2015 meeting was December 15-16). No
T0008 results were computed or recorded. The guard was corrected to
match the spec — the ranges are calendar periods, executed exactly
as preregistered — and the trial re-runs here as T0010 (trial IDs
are unique per attempt). The transcription error and its consequence
(the December 2015 meeting falls in the "unchanged" descriptive
bucket) are disclosed in the study report.

The trial binds the preregistered H0007 v1 spec, the fetch manifest's
SHA-256 as the data fingerprint, and a canonical-JSON hash of the
analysis configuration. It runs the repo's event-study estimator
(``myquant.stats.event_study.event_study``) with a constant-mean
benchmark (each event's expected change is the mean observed change
over its own estimation window [-60,-11]) on the five legs of the
FOMC event study:

1. the preregistered five-test Holm family on the main window [0,+1]
   (VIX CAR < 0 one-sided primary; SPX, DGS10, BAA10Y two-sided;
   TYVIX < 0 one-sided);
2. descriptives (not in the family): the wide window [-1,+1] on the
   main sample, the four non-TYVIX legs on the extended sample
   (2003-2026), and the hiking/cutting/unchanged cycle splits (no
   p-values).

There is no walk-forward and no cost gate: an event study measures
announcement responses, not a forecast, so there is no trading rule
to cost. The verdict criteria are the preregistered ones: the
Holm-adjusted primary p-value below 0.05 and the standardized mean
VIX CAR at or below -0.3.

Transforms (preregistered): VIX, TYVIX and SPX use log changes;
DGS10 and BAA10Y use level changes in basis points. Both are computed
diff-then-join: each series is differenced on its own dates before
alignment to the panel's return index, so a partial holiday in one
leg cannot corrupt another leg's one-day change.
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

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "fomc-event-study-005"

HYPOTHESIS_ID = "H0007"
HYPOTHESIS_VERSION = 1
TRIAL_ID = "T0010"

VIX = "index:vix"
TYVIX = "index:tyvix"
DGS10 = "rates:us-10y-yield"
SPX = "index:sp500"
BAA10Y = "credit:baa-10y-spread"
MAIN_INSTRUMENTS = (VIX, TYVIX, DGS10, SPX, BAA10Y)
EXTENDED_INSTRUMENTS = (VIX, DGS10, SPX, BAA10Y)
LOG_CHANGE_LEGS = (VIX, TYVIX, SPX)
BP_CHANGE_LEGS = (DGS10, BAA10Y)
MAIN_SAMPLE_END = date(2020, 5, 15)

# The preregistered five-test family, in preregistered order: the
# primary test first. Directions: "less" is a one-sided test of a
# negative mean CAR; "two-sided" uses the estimator's normal-reference
# two-sided p-value.
FAMILY: tuple[tuple[str, str, str], ...] = (
    ("vix_car", VIX, "less"),
    ("spx_car", SPX, "two-sided"),
    ("dgs10_car", DGS10, "two-sided"),
    ("baa10y_car", BAA10Y, "two-sided"),
    ("tyvix_car", TYVIX, "less"),
)

CYCLE_KEYS = (
    "cycle_hiking_1",
    "cycle_hiking_2",
    "cycle_cutting_1",
    "cycle_cutting_2",
)


def load_panels() -> tuple[
    SynchronizedPanel,
    SynchronizedPanel,
    list[Any],
    list[Any],
    dict[str, str],
]:
    """Load the main and extended panels from the local PIT store."""
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
    extended_panel = build_synchronized_panel(
        observations,
        instruments=EXTENDED_INSTRUMENTS,
    )
    manifest_info = {
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "fetched_at": manifest["fetched_at"],
    }
    return (
        main_panel,
        extended_panel,
        main_observations,
        observations,
        manifest_info,
    )


def load_calendar() -> tuple[tuple[pd.Timestamp, ...], list[dict[str, Any]]]:
    """Scheduled statement timestamps (21:00 UTC) and the excluded list."""
    calendar = json.loads((ROOT / "fomc_calendar.json").read_text(encoding="utf-8"))
    statements = tuple(
        pd.Timestamp(
            datetime.combine(
                date.fromisoformat(meeting["statement_date"]),
                DAILY_CLOSE_UTC,
                tzinfo=UTC,
            )
        )
        for meeting in calendar["scheduled_meetings"]
    )
    return statements, list(calendar["excluded_meetings"])


def build_transforms(
    panel: SynchronizedPanel,
    observations: list[Any],
    *,
    include_tyvix: bool,
) -> pd.DataFrame:
    """Preregistered per-leg transforms on the panel's return index.

    Log changes for VIX, TYVIX and SPX come from the synchronized
    panel (diff-then-join inside the builder); level changes in basis
    points for DGS10 and BAA10Y are computed per series on their own
    dates and then aligned to the same index.
    """
    log_legs = tuple(
        leg for leg in LOG_CHANGE_LEGS if include_tyvix or leg != TYVIX
    )
    frame = panel.returns.loc[:, list(log_legs)].copy()
    bp_changes = level_changes_on_index(
        observations,
        instruments=BP_CHANGE_LEGS,
        index=panel.returns.index,
    )
    for leg in BP_CHANGE_LEGS:
        frame[leg] = bp_changes[leg]
    return frame


def event_test_metrics(
    result: EventStudyResult,
    *,
    direction: str,
) -> dict[str, Any]:
    """One family test's metrics from an event-study result.

    The coefficient is the mean CAR across events (log points for the
    log-change legs, basis points for the rate legs); the standard
    error and z-statistic are the estimator's cluster-based ones.
    One-sided p-values use the preregistered normal-reference
    derivation Phi(z) for the "less" direction.
    """
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


def parse_cycle_ranges(params: dict[str, str]) -> dict[str, tuple[date, date]]:
    """Preregistered policy-cycle ranges, keyed by parameter name."""
    ranges: dict[str, tuple[date, date]] = {}
    for key in CYCLE_KEYS:
        start_text, end_text = params[key].split(":", maxsplit=1)
        ranges[key] = (
            date.fromisoformat(start_text),
            date.fromisoformat(end_text),
        )
    return ranges


def cycle_label(
    statement_date: date,
    ranges: dict[str, tuple[date, date]],
) -> str:
    """Which preregistered policy cycle an event date falls in."""
    for key, (start, end) in ranges.items():
        if start <= statement_date <= end:
            return "hiking" if "hiking" in key else "cutting"
    return "unchanged"


def check_cycle_ranges(ranges: dict[str, tuple[date, date]]) -> None:
    """Structural validation of the preregistered cycle ranges.

    The ranges are calendar periods, executed exactly as preregistered:
    an event is hiking/cutting if its statement date falls inside one
    of the ranges, unchanged otherwise. The ranges must be non-empty
    and the hiking and cutting ranges must not overlap (an event must
    have exactly one label).

    Known transcription error in the v1 spec (disclosed in the study
    report): cycle_hiking_2 starts 2015-12-17, but the December 2015
    meeting was December 15-16, so the inaugural hike meeting
    (2015-12-16) falls in the "unchanged" bucket. The ranges are
    executed as written because the preregistration is immutable and
    the registry forbids amending a hypothesis once testing has
    started; the split is descriptive only (no p-values, not in the
    family), so no verdict is affected.
    """
    seen: list[tuple[date, date, str]] = []
    for key, (start, end) in ranges.items():
        if start > end:
            raise ValueError(f"cycle range {key} is empty: {start} to {end}")
        label = "hiking" if "hiking" in key else "cutting"
        for other_start, other_end, other_label in seen:
            if other_label == label:
                continue
            if start <= other_end and other_start <= end:
                raise ValueError(
                    f"cycle ranges overlap: {key} ({start} to {end}) "
                    f"vs {other_label} ({other_start} to {other_end})"
                )
        seen.append((start, end, label))


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
        "trial_script": "research/fomc-event-study-005/run_trial.py",
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
            "FOMC event response: constant-mean CARs on [0,+1] for VIX, "
            "SPX, DGS10, BAA10Y and TYVIX across scheduled FOMC meetings"
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
    extended_panel: SynchronizedPanel,
    main_observations: list[Any],
    all_observations: list[Any],
    statements: tuple[pd.Timestamp, ...],
    spec: HypothesisSpec,
) -> Any:
    """Build the trial callback closing over the loaded panels."""

    def experiment(trial_spec: TrialSpec) -> dict[str, Any]:
        params = {item.name: item.value for item in trial_spec.parameters}
        estimation_start = int(params["estimation_start_steps"])
        estimation_end = int(params["estimation_end_steps"])
        pre_steps = int(params["event_pre_steps"])
        post_steps = int(params["event_post_steps"])
        wide_pre_steps = int(params["wide_event_pre_steps"])
        wide_post_steps = int(params["wide_event_post_steps"])
        effect_threshold = float(params["standardized_effect_threshold"])

        main_transforms = build_transforms(
            main_panel,
            main_observations,
            include_tyvix=True,
        )
        extended_transforms = build_transforms(
            extended_panel,
            all_observations,
            include_tyvix=False,
        )

        # The main-sample events are the scheduled statements up to the
        # main sample end (2020-05-15); later statements belong to the
        # extended sample only.
        main_cutoff = pd.Timestamp(
            datetime.combine(MAIN_SAMPLE_END, DAILY_CLOSE_UTC, tzinfo=UTC)
        )
        main_events = tuple(
            event for event in statements if event <= main_cutoff
        )
        included, excluded = filter_events_to_panel(
            main_panel.returns.index,
            main_events,
            estimation_start_steps=estimation_start,
            estimation_end_steps=estimation_end,
            pre_event_steps=pre_steps,
            post_event_steps=post_steps,
        )

        # The preregistered five-test family on the main window.
        results: dict[str, EventStudyResult] = {}
        tests: dict[str, Any] = {}
        for test_name, leg, direction in FAMILY:
            result = run_constant_mean_event_study(
                main_transforms[leg],
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

        # Descriptive: the wide window [-1,+1] on the main sample.
        wide_included, wide_excluded = filter_events_to_panel(
            main_panel.returns.index,
            main_events,
            estimation_start_steps=estimation_start,
            estimation_end_steps=estimation_end,
            pre_event_steps=wide_pre_steps,
            post_event_steps=wide_post_steps,
        )
        wide_window: dict[str, Any] = {}
        for test_name, leg, direction in FAMILY:
            result = run_constant_mean_event_study(
                main_transforms[leg],
                wide_included,
                estimation_start_steps=estimation_start,
                estimation_end_steps=estimation_end,
                pre_event_steps=wide_pre_steps,
                post_event_steps=wide_post_steps,
            )
            wide_window[test_name] = event_test_metrics(result, direction=direction)
        wide_window["events_included"] = len(wide_included)
        wide_window["events_excluded"] = [
            dict(item) for item in wide_excluded
        ]

        # Descriptive: the four non-TYVIX legs on the extended sample.
        ext_included, ext_excluded = filter_events_to_panel(
            extended_panel.returns.index,
            statements,
            estimation_start_steps=estimation_start,
            estimation_end_steps=estimation_end,
            pre_event_steps=pre_steps,
            post_event_steps=post_steps,
        )
        extended: dict[str, Any] = {}
        for test_name, leg, direction in FAMILY:
            if leg == TYVIX:
                continue
            result = run_constant_mean_event_study(
                extended_transforms[leg],
                ext_included,
                estimation_start_steps=estimation_start,
                estimation_end_steps=estimation_end,
                pre_event_steps=pre_steps,
                post_event_steps=post_steps,
            )
            extended[test_name] = event_test_metrics(result, direction=direction)
        extended["events_included"] = len(ext_included)
        extended["events_excluded"] = [dict(item) for item in ext_excluded]

        # Descriptive: policy-cycle splits on the main window, no p-values.
        ranges = parse_cycle_ranges(params)
        check_cycle_ranges(ranges)
        cycles: dict[str, Any] = {}
        for label in ("hiking", "cutting", "unchanged"):
            cycle_events = tuple(
                event
                for event in included
                if cycle_label(event.date(), ranges) == label
            )
            entry: dict[str, Any] = {"events": len(cycle_events)}
            if len(cycle_events) >= 2:
                for _, leg, _ in FAMILY:
                    result = run_constant_mean_event_study(
                        main_transforms[leg],
                        cycle_events,
                        estimation_start_steps=estimation_start,
                        estimation_end_steps=estimation_end,
                        pre_event_steps=pre_steps,
                        post_event_steps=post_steps,
                    )
                    entry[leg] = {
                        "mean_car": result.mean_cluster_car,
                        "standardized_mean_car": standardized_mean_car(result),
                        "cluster_count": result.cluster_count,
                    }
            cycles[label] = entry

        # Per-event CARs on the main window (the primary data of the
        # study; the cross-section trial recomputes them independently).
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
        primary = tests["vix_car"]
        primary_adjusted_p = holm[0]["adjusted_p_value"]
        criteria = {
            "holm_adjusted_primary_p_below_0.05": bool(primary_adjusted_p < 0.05),
            "primary_standardized_mean_car_at_most_minus_0.3": bool(
                primary["standardized_mean_car"] <= -effect_threshold
            ),
        }
        metrics: dict[str, Any] = {
            "panel": {
                "daily_rows": int(main_panel.returns.shape[0]),
                "daily_first": main_panel.returns.index[0].isoformat(),
                "daily_last": main_panel.returns.index[-1].isoformat(),
                "daily_dropped_close_rows": main_panel.dropped_close_rows,
                "daily_dropped_return_rows": main_panel.dropped_return_rows,
                "extended_rows": int(extended_panel.returns.shape[0]),
                "extended_first": extended_panel.returns.index[0].isoformat(),
                "extended_last": extended_panel.returns.index[-1].isoformat(),
                "extended_dropped_close_rows": extended_panel.dropped_close_rows,
                "extended_dropped_return_rows": (
                    extended_panel.dropped_return_rows
                ),
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
            "descriptive_wide_window": wide_window,
            "descriptive_extended": extended,
            "descriptive_cycles": cycles,
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
    main_panel, extended_panel, main_obs, all_obs, manifest_info = load_panels()
    print(
        f"main panel: {main_panel.row_count} rows, "
        f"{main_panel.first_time.date()} to {main_panel.last_time.date()}, "
        f"{main_panel.dropped_return_rows} dropped return rows"
    )
    print(
        f"extended panel: {extended_panel.row_count} rows, "
        f"{extended_panel.first_time.date()} to {extended_panel.last_time.date()}, "
        f"{extended_panel.dropped_return_rows} dropped return rows"
    )
    statements, excluded_meetings = load_calendar()
    print(
        f"calendar: {len(statements)} scheduled statements, "
        f"{len(excluded_meetings)} excluded meetings"
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
        build_experiment(
            main_panel,
            extended_panel,
            main_obs,
            all_obs,
            statements,
            spec,
        ),
    )
    print(f"trial {receipt.trial_id} completed: record {receipt.record_hash}")
    metrics = receipt.metrics
    primary = metrics["tests"]["vix_car"]
    print(
        f"primary (VIX CAR): mean {primary['coefficient']:.6f}, "
        f"standardized {primary['standardized_mean_car']:.4f}, "
        f"p {primary['p_value']:.4g}"
    )
    print(f"holm: {metrics['holm']}")
    print(f"events included: {metrics['events']['included']}")
    print(f"verdict supported: {metrics['verdict']['supported']}")


if __name__ == "__main__":
    main()
