"""Run trial T0009 for hypothesis H0008 v1 (cross-event transmission).

Run after preregistration and fetching, from the repo root, with a
clean worktree (the trial records the HEAD commit as its code
revision):

    .venv/bin/python research/fomc-event-study-005/run_trial_h0008.py

The trial binds the preregistered H0008 v1 spec, the fetch manifest's
SHA-256 as the data fingerprint, and a canonical-JSON hash of the
analysis configuration. It first recomputes the per-event CARs for
DGS10, SPX, VIX and BAA10Y with the same constant-mean event-study
estimator and window as trial T0008 (independently, from the same
panels), then runs the preregistered three-test Holm family of
cross-event OLS regressions (target-leg CAR on DGS10 CAR, one
observation per FOMC event, heteroskedasticity-consistent HC0
standard errors via the repo's Newey-West estimator at max_lag=0):

1. primary: SPX CAR on DGS10 CAR, slope < 0 (one-sided);
2. VIX CAR on DGS10 CAR, slope != 0 (two-sided);
3. BAA10Y CAR on DGS10 CAR, slope != 0 (two-sided).

The verdict criteria are the preregistered ones: the Holm-adjusted
primary p-value below 0.05, the primary R-squared at or above 0.05,
and split-half replication (events ordered chronologically, first
half = first floor(n/2) events; both halves' slopes negative with
one-sided HC0 p < 0.05).

Descriptives (not in the family): the same cross-section on the
extended sample (2003-2026, four legs) and on the wide window
[-1,+1] (the study's preregistered descriptive window, fixed in
H0007's spec).

The DGS10 event-window move is only a proxy for the policy surprise,
not the surprise itself: no free federal funds futures surprise
series exists, so this trial tests cross-sectional association
between the rate leg and the other legs, not a causal surprise
effect. There is no walk-forward and no cost gate: an event study
measures announcement responses, not a forecast.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np
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
from myquant.stats import adjust_pvalues, newey_west_hac
from myquant.stats.event_study import EventStudyResult
from myquant.studies.event_windows import (
    filter_events_to_panel,
    one_sided_normal_p_value,
    run_constant_mean_event_study,
)
from myquant.studies.panel import (
    SynchronizedPanel,
    build_synchronized_panel,
    level_changes_on_index,
)

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "fomc-event-study-005"

HYPOTHESIS_ID = "H0008"
HYPOTHESIS_VERSION = 1
TRIAL_ID = "T0009"

VIX = "index:vix"
TYVIX = "index:tyvix"
DGS10 = "rates:us-10y-yield"
SPX = "index:sp500"
BAA10Y = "credit:baa-10y-spread"
MAIN_INSTRUMENTS = (VIX, TYVIX, DGS10, SPX, BAA10Y)
EXTENDED_INSTRUMENTS = (VIX, DGS10, SPX, BAA10Y)
LOG_CHANGE_LEGS = (VIX, SPX)
BP_CHANGE_LEGS = (DGS10, BAA10Y)
CROSS_SECTION_LEGS = (DGS10, SPX, VIX, BAA10Y)
MAIN_SAMPLE_END = date(2020, 5, 15)

# The study's preregistered descriptive window ([-1,+1], fixed in
# H0007's spec); the H0008 family uses the main window [0,+1] only.
WIDE_PRE_STEPS = 1
WIDE_POST_STEPS = 1

# The preregistered three-test family, in preregistered order: the
# primary test first. Directions: "less" is a one-sided test of a
# negative slope; "two-sided" uses the HAC two-sided p-value.
FAMILY: tuple[tuple[str, str, str], ...] = (
    ("spx_on_dgs10", SPX, "less"),
    ("vix_on_dgs10", VIX, "two-sided"),
    ("baa10y_on_dgs10", BAA10Y, "two-sided"),
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


def load_calendar() -> tuple[pd.Timestamp, ...]:
    """Scheduled statement timestamps (21:00 UTC)."""
    calendar = json.loads((ROOT / "fomc_calendar.json").read_text(encoding="utf-8"))
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


def build_transforms(
    panel: SynchronizedPanel,
    observations: list[Any],
) -> pd.DataFrame:
    """Preregistered per-leg transforms on the panel's return index.

    Log changes for VIX and SPX come from the synchronized panel
    (diff-then-join inside the builder); level changes in basis points
    for DGS10 and BAA10Y are computed per series on their own dates
    and then aligned to the same index. TYVIX is not a cross-section
    leg and is never used here.
    """
    frame = panel.returns.loc[:, list(LOG_CHANGE_LEGS)].copy()
    bp_changes = level_changes_on_index(
        observations,
        instruments=BP_CHANGE_LEGS,
        index=panel.returns.index,
    )
    for leg in BP_CHANGE_LEGS:
        frame[leg] = bp_changes[leg]
    return frame


def compute_car_frame(
    transforms: pd.DataFrame,
    events: tuple[pd.Timestamp, ...],
    *,
    estimation_start_steps: int,
    estimation_end_steps: int,
    pre_event_steps: int,
    post_event_steps: int,
) -> tuple[pd.DataFrame, dict[str, EventStudyResult]]:
    """Per-event CARs for the cross-section legs on one window."""
    results: dict[str, EventStudyResult] = {}
    for leg in CROSS_SECTION_LEGS:
        results[leg] = run_constant_mean_event_study(
            transforms[leg],
            events,
            estimation_start_steps=estimation_start_steps,
            estimation_end_steps=estimation_end_steps,
            pre_event_steps=pre_event_steps,
            post_event_steps=post_event_steps,
        )
    frame = pd.DataFrame(
        {
            leg: {
                event.event_time: event.cumulative_abnormal_return
                for event in results[leg].events
            }
            for leg in CROSS_SECTION_LEGS
        }
    )
    return frame, results


def cross_section_fit(
    target_cars: np.ndarray,
    dgs10_cars: np.ndarray,
    *,
    direction: str,
    max_lag: int,
) -> dict[str, Any]:
    """One cross-event OLS: target CAR on DGS10 CAR, HC0 standard errors.

    ``max_lag=0`` makes the repo's Newey-West estimator return the
    heteroskedasticity-consistent HC0 covariance. The one-sided
    p-value uses the preregistered normal-reference derivation Phi(t)
    for the "less" direction.
    """
    result = newey_west_hac(
        target_cars,
        {"dgs10_car": dgs10_cars},
        max_lag=max_lag,
    )
    slope = next(
        coef for coef in result.coefficients if coef.name == "dgs10_car"
    )
    intercept = next(
        coef for coef in result.coefficients if coef.name == "intercept"
    )
    if slope.standard_error is None or slope.t_statistic is None:
        raise ValueError("HAC inference is unavailable for the slope")
    if direction == "less":
        p_value = one_sided_normal_p_value(slope.t_statistic, direction="less")
    elif direction == "two-sided":
        if slope.p_value is None:
            raise ValueError("two-sided p-value is unavailable")
        p_value = slope.p_value
    else:
        raise ValueError(f"unknown direction: {direction!r}")
    return {
        "observations": result.observations,
        "coefficient": slope.estimate,
        "standard_error": slope.standard_error,
        "t_statistic": slope.t_statistic,
        "p_value": p_value,
        "partial_r_squared": None,
        "incremental_r_squared": None,
        "r_squared": result.ols.r_squared,
        "intercept": intercept.estimate,
        "direction": direction,
    }


def split_half_replication(
    target_cars: np.ndarray,
    dgs10_cars: np.ndarray,
    *,
    max_lag: int,
) -> dict[str, Any]:
    """Chronological split-half replication of the primary slope.

    First half = first floor(n/2) events (chronological order);
    second half = the rest. Replication requires both halves' slopes
    negative with one-sided HC0 p < 0.05.
    """
    n_events = target_cars.shape[0]
    split = n_events // 2
    halves: dict[str, Any] = {}
    for label, target, predictor in (
        ("first_half", target_cars[:split], dgs10_cars[:split]),
        ("second_half", target_cars[split:], dgs10_cars[split:]),
    ):
        halves[label] = cross_section_fit(
            target,
            predictor,
            direction="less",
            max_lag=max_lag,
        )
    replicated = bool(
        halves["first_half"]["coefficient"] < 0
        and halves["first_half"]["p_value"] < 0.05
        and halves["second_half"]["coefficient"] < 0
        and halves["second_half"]["p_value"] < 0.05
    )
    return {
        "split_index": split,
        "first_half_events": split,
        "second_half_events": n_events - split,
        "first_half": halves["first_half"],
        "second_half": halves["second_half"],
        "replicated": replicated,
    }


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
        "trial_script": "research/fomc-event-study-005/run_trial_h0008.py",
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
            "FOMC cross-event transmission: target-leg CARs on DGS10 CAR "
            "across scheduled FOMC meetings (cross-section OLS, HC0)"
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
        max_lag = int(params["cross_section_max_lag"])
        r_squared_threshold = float(params["r_squared_threshold"])

        main_transforms = build_transforms(
            main_panel,
            main_observations,
        )
        extended_transforms = build_transforms(
            extended_panel,
            all_observations,
        )

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
        car_frame, _ = compute_car_frame(
            main_transforms,
            included,
            estimation_start_steps=estimation_start,
            estimation_end_steps=estimation_end,
            pre_event_steps=pre_steps,
            post_event_steps=post_steps,
        )
        dgs10_cars = car_frame[DGS10].to_numpy(dtype=float)

        # The preregistered three-test family.
        tests: dict[str, Any] = {}
        for test_name, leg, direction in FAMILY:
            tests[test_name] = cross_section_fit(
                car_frame[leg].to_numpy(dtype=float),
                dgs10_cars,
                direction=direction,
                max_lag=max_lag,
            )
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

        # Split-half replication of the primary slope.
        split_half = split_half_replication(
            car_frame[SPX].to_numpy(dtype=float),
            dgs10_cars,
            max_lag=max_lag,
        )

        # Descriptive: the cross-section on the extended sample.
        ext_included, ext_excluded = filter_events_to_panel(
            extended_panel.returns.index,
            statements,
            estimation_start_steps=estimation_start,
            estimation_end_steps=estimation_end,
            pre_event_steps=pre_steps,
            post_event_steps=post_steps,
        )
        ext_car_frame, _ = compute_car_frame(
            extended_transforms,
            ext_included,
            estimation_start_steps=estimation_start,
            estimation_end_steps=estimation_end,
            pre_event_steps=pre_steps,
            post_event_steps=post_steps,
        )
        ext_dgs10 = ext_car_frame[DGS10].to_numpy(dtype=float)
        extended: dict[str, Any] = {}
        for test_name, leg, direction in FAMILY:
            extended[test_name] = cross_section_fit(
                ext_car_frame[leg].to_numpy(dtype=float),
                ext_dgs10,
                direction=direction,
                max_lag=max_lag,
            )
        extended["events_included"] = len(ext_included)
        extended["events_excluded"] = [dict(item) for item in ext_excluded]

        # Descriptive: the cross-section on the wide window [-1,+1].
        wide_included, wide_excluded = filter_events_to_panel(
            main_panel.returns.index,
            main_events,
            estimation_start_steps=estimation_start,
            estimation_end_steps=estimation_end,
            pre_event_steps=WIDE_PRE_STEPS,
            post_event_steps=WIDE_POST_STEPS,
        )
        wide_car_frame, _ = compute_car_frame(
            main_transforms,
            wide_included,
            estimation_start_steps=estimation_start,
            estimation_end_steps=estimation_end,
            pre_event_steps=WIDE_PRE_STEPS,
            post_event_steps=WIDE_POST_STEPS,
        )
        wide_dgs10 = wide_car_frame[DGS10].to_numpy(dtype=float)
        wide_window: dict[str, Any] = {}
        for test_name, leg, direction in FAMILY:
            wide_window[test_name] = cross_section_fit(
                wide_car_frame[leg].to_numpy(dtype=float),
                wide_dgs10,
                direction=direction,
                max_lag=max_lag,
            )
        wide_window["events_included"] = len(wide_included)
        wide_window["events_excluded"] = [dict(item) for item in wide_excluded]

        # Per-event CARs on the main window (the primary data of the
        # cross-section analysis).
        event_cars = [
            {
                "event_time": timestamp.isoformat(),
                **{
                    leg: float(car_frame.loc[timestamp, leg])
                    for leg in CROSS_SECTION_LEGS
                },
            }
            for timestamp in car_frame.index
        ]
        car_summary = {
            leg: {
                "mean_car": float(car_frame[leg].mean()),
                "std_car": float(car_frame[leg].std(ddof=1)),
                "min_car": float(car_frame[leg].min()),
                "max_car": float(car_frame[leg].max()),
                "events": int(car_frame.shape[0]),
            }
            for leg in CROSS_SECTION_LEGS
        }

        # Verdict against the preregistered acceptance criteria.
        primary = tests["spx_on_dgs10"]
        primary_adjusted_p = holm[0]["adjusted_p_value"]
        criteria = {
            "holm_adjusted_primary_p_below_0.05": bool(primary_adjusted_p < 0.05),
            "primary_r_squared_at_least_0.05": bool(
                primary["r_squared"] >= r_squared_threshold
            ),
            "split_half_replicated": bool(split_half["replicated"]),
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
            "car_summary": car_summary,
            "tests": tests,
            "holm": holm,
            "split_half": split_half,
            "descriptive_extended": extended,
            "descriptive_wide_window": wide_window,
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
    primary = metrics["tests"]["spx_on_dgs10"]
    print(
        f"primary (SPX on DGS10): slope {primary['coefficient']:.6f}, "
        f"R2 {primary['r_squared']:.4f}, p {primary['p_value']:.4g}"
    )
    print(f"holm: {metrics['holm']}")
    print(f"split-half replicated: {metrics['split_half']['replicated']}")
    print(f"events included: {metrics['events']['included']}")
    print(f"verdict supported: {metrics['verdict']['supported']}")


if __name__ == "__main__":
    main()
