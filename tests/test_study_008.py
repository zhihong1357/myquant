"""Tests for study 008 (BAA10Y -> SPX, H0013/T0016).

All offline: synthetic business-day data, no network, no dependence on
the gitignored fetch cache. The synthetic panel mirrors the real study's
shape (three instruments, US-equity closes at 21:00 UTC, weekend gaps)
so the tests exercise the same code paths the trial ran on real data:

- panel construction: diff-then-join row counts and the PIT semantics
  of the lagged predictors (the BAA10Y change ending two trading days
  before the decision close);
- trial logic: the partial test, walk-forward OOS evaluation, cost gate
  and the four-criterion verdict, on a planted effect (verdict
  SUPPORTED) and on pure noise (verdict REJECTED);
- scaffold/registration regression: the preregister script is
  idempotent, and the committed H0013 v1 fingerprint re-derives from
  the design in a clean directory.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd
import pytest

from myquant.canonical import canonical_json
from myquant.contracts import Observation
from myquant.hypotheses import HypothesisRegistry
from myquant.studies.panel import SynchronizedPanel, build_synchronized_panel

REPO_ROOT = Path(__file__).resolve().parents[1]
STUDY_DIR = REPO_ROOT / "research" / "credit-spread-spx-008"

# A synthetic panel + lagged frame + hand-computed truth series.
SyntheticData = tuple[
    SynchronizedPanel, pd.DataFrame, dict[str, np.ndarray]
]

BAA10Y = "credit:baa-10y-spread"
SPX = "index:sp500"
VIX = "index:vix"

# The committed H0013 v1 fingerprint (from the study report); the
# idempotency test re-derives it from the design in a clean directory.
H0013_FINGERPRINT = (
    "e7f98ea75dd4c2a9b545e71b3f2fd0c9dd1d8dcef42add42987dd1d44861a39a"
)


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _synthetic_series(
    *,
    seed: int,
    beta: float,
) -> tuple[list[Observation], dict[str, np.ndarray], list[datetime]]:
    """Synthetic closes on the real study's business-day calendar.

    BAA10Y is a mean-reverting spread level (changes ~3bp std); VIX is
    a mean-reverting log level; SPX log returns follow
    ``beta * baa_change[k-3] + noise`` in return-row coordinates, so
    the planted effect sits exactly on the trial's alignment (the
    lagged BAA10Y change at frame row j predicts the SPX return at
    frame row j+1). ``beta=0`` is the pure-noise case.
    """
    dates = pd.bdate_range("2003-01-02", "2026-11-17")
    event_times = [
        datetime(d.year, d.month, d.day, 21, 0, tzinfo=UTC) for d in dates
    ]
    n_closes = len(dates)
    n_returns = n_closes - 1
    rng = np.random.default_rng(seed)

    baa_levels = np.empty(n_closes)
    baa_levels[0] = 3.0
    for i in range(1, n_closes):
        change = -0.01 * (baa_levels[i - 1] - 3.0) + rng.normal(0.0, 0.03)
        baa_levels[i] = baa_levels[i - 1] + change
    baa_chg = np.diff(baa_levels) * 100.0  # bp, return-row coordinates

    vix_log = np.empty(n_closes)
    vix_log[0] = math.log(20.0)
    for i in range(1, n_closes):
        change = -0.01 * (vix_log[i - 1] - math.log(20.0)) + rng.normal(0.0, 0.05)
        vix_log[i] = vix_log[i - 1] + change
    vix_logchg = np.diff(vix_log)

    spx_ret = np.empty(n_returns)
    noise = rng.normal(0.0, 0.0117, size=n_returns)
    for k in range(n_returns):
        spx_ret[k] = noise[k] + (beta * baa_chg[k - 3] if k >= 3 else 0.0)
    spx_levels = 1000.0 * np.exp(np.concatenate([[0.0], np.cumsum(spx_ret)]))

    ingested_at = datetime(2026, 11, 19, 0, 25, tzinfo=UTC)
    observations: list[Observation] = []
    for instrument, levels, source_id in (
        (BAA10Y, baa_levels, "fred"),
        (SPX, spx_levels, "yahoo-finance"),
        (VIX, np.exp(vix_log), "fred"),
    ):
        for event_time, value in zip(event_times, levels, strict=True):
            observations.append(
                Observation(
                    instrument_id=instrument,
                    venue="synthetic",
                    event_time=event_time,
                    available_at=event_time,
                    ingested_at=ingested_at,
                    field="close",
                    value=float(value),
                    unit="synthetic",
                    source_id=source_id,
                    source_version=1,
                )
            )
    truth = {
        "baa_chg": baa_chg,
        "vix_logchg": vix_logchg,
        "spx_ret": spx_ret,
    }
    return observations, truth, event_times


@pytest.fixture(scope="module")
def run_trial() -> ModuleType:
    return _load_module(STUDY_DIR / "run_trial.py", "study_008_run_trial")


@pytest.fixture(scope="module")
def effect_data(run_trial: ModuleType) -> SyntheticData:
    observations, truth, _ = _synthetic_series(seed=7, beta=-0.002)
    panel = build_synchronized_panel(
        observations, instruments=(BAA10Y, SPX, VIX)
    )
    frame, _ = run_trial.build_lagged_frame(
        panel, observations, baa_lag_steps=2, vix_lag_steps=1
    )
    return panel, frame, truth


@pytest.fixture(scope="module")
def noise_data(run_trial: ModuleType) -> SyntheticData:
    observations, truth, _ = _synthetic_series(seed=11, beta=0.0)
    panel = build_synchronized_panel(
        observations, instruments=(BAA10Y, SPX, VIX)
    )
    frame, _ = run_trial.build_lagged_frame(
        panel, observations, baa_lag_steps=2, vix_lag_steps=1
    )
    return panel, frame, truth


# --- Panel construction: diff-then-join and PIT semantics ---


def test_panel_diff_then_join_row_counts(effect_data: SyntheticData) -> None:
    panel, _, _ = effect_data
    # One close per business day; the first return row is dropped (no
    # prior close). No missing values, so no other rows drop.
    n_closes = len(pd.bdate_range("2003-01-02", "2026-11-17"))
    assert panel.row_count == n_closes - 1
    assert panel.dropped_close_rows == 0
    assert panel.dropped_return_rows == 1
    assert panel.returns.index[0] == pd.Timestamp("2003-01-03 21:00:00+00:00")
    assert panel.returns.index[-1] == pd.Timestamp("2026-11-17 21:00:00+00:00")


def test_panel_keeps_monday_returns(effect_data: SyntheticData) -> None:
    """Weekend gaps must not invalidate Monday returns.

    Regression guard for the scaffold's bar_seconds=86400 bug: with a
    one-day bar filter, every Monday/post-holiday return would drop
    (~30% of rows). The real study omits bar_seconds; Mondays stay.
    """
    panel, _, _ = effect_data
    mondays = [ts for ts in panel.returns.index if ts.weekday() == 0]
    assert len(mondays) > 1000
    assert panel.returns.loc[mondays].notna().all().all()


def test_frame_pit_semantics(effect_data: SyntheticData) -> None:
    """The lagged predictors carry only information available at the close.

    Frame row j (return index j+2) pairs the BAA10Y change ending two
    trading days earlier (return index j), the VIX log change ending
    one trading day earlier (return index j+1), and the SPX return of
    the row itself — all hand-computed from the synthetic closes.
    """
    panel, frame, truth = effect_data
    assert len(frame) == len(panel.returns) - 2
    assert frame.isna().sum().sum() == 0
    for j in (0, 1, 100, 1000, 3000, len(frame) - 1):
        assert frame["baa_lagged"].iloc[j] == pytest.approx(truth["baa_chg"][j])
        assert frame["vix_lagged"].iloc[j] == pytest.approx(
            truth["vix_logchg"][j + 1]
        )
        assert frame["baa_naive"].iloc[j] == pytest.approx(truth["baa_chg"][j + 2])
        assert frame["spx"].iloc[j] == pytest.approx(truth["spx_ret"][j + 2])
    # The predictor's value date is two trading days before the frame
    # date: the first frame row is 2003-01-07 and its predictor is the
    # change ending 2003-01-03.
    assert frame.index[0] == pd.Timestamp("2003-01-07 21:00:00+00:00")


# --- Trial logic: partial test, walk-forward, cost gate, verdict ---


def test_partial_test_detects_planted_effect(
    effect_data: SyntheticData, run_trial: ModuleType
) -> None:
    _, frame, _ = effect_data
    result = run_trial._partial_test(
        frame["baa_lagged"].to_numpy(dtype=float),
        frame["spx"].to_numpy(dtype=float),
        factor_name="vix",
        factor=frame["vix_lagged"].to_numpy(dtype=float),
        max_hac_lag=5,
    )
    assert result["coefficient"] == pytest.approx(-0.002, abs=0.0002)
    assert result["p_value"] < 1e-10
    assert result["partial_r_squared"] > 0.005


def test_partial_test_null_on_noise(noise_data: SyntheticData, run_trial: ModuleType) -> None:
    _, frame, _ = noise_data
    result = run_trial._partial_test(
        frame["baa_lagged"].to_numpy(dtype=float),
        frame["spx"].to_numpy(dtype=float),
        factor_name="vix",
        factor=frame["vix_lagged"].to_numpy(dtype=float),
        max_hac_lag=5,
    )
    assert result["p_value"] > 0.05
    assert result["partial_r_squared"] < 0.005


def test_walk_forward_positive_on_planted_effect(
    effect_data: SyntheticData, run_trial: ModuleType
) -> None:
    _, frame, _ = effect_data
    result = run_trial.run_walk_forward(
        frame,
        initial_train_size=1000,
        test_size=126,
        embargo_days=1,
        holdout_start=datetime(2024, 1, 2, 21, 0, tzinfo=UTC),
    )
    assert result["folds"] > 30
    assert result["skipped_folds"] == 0
    assert result["holdout_oos_incremental_r_squared"] > 0.05
    assert result["all_oos_incremental_r_squared"] > 0.05


def test_cost_gate_arithmetic(run_trial: ModuleType) -> None:
    """Hand-computed sign-rule case: entry, flip, exit costs."""
    forecasts = [0.01, -0.01, -0.01, 0.01]
    actuals = [0.02, 0.01, -0.01, 0.03]
    result = run_trial.run_cost_gate(
        forecasts, actuals, block_length=2, resamples=100, seed=42
    )
    # Positions +1, -1, -1, +1. Gross: +0.02 -0.01 +0.01 +0.03 = 0.05.
    # Costs: entry 1bp, flip 2bp, flip 2bp, final exit 1bp = 6bp.
    assert result["days"] == 4
    assert result["flips"] == 2
    assert result["gross_daily_edge"] == pytest.approx(0.05 / 4)
    assert result["total_cost"] == pytest.approx(0.0006)
    assert result["net_daily_edge"] == pytest.approx((0.05 - 0.0006) / 4)


def _run_experiment(
    run_trial: ModuleType,
    panel: SynchronizedPanel,
    observations: list[Observation],
) -> dict[str, Any]:
    registry = HypothesisRegistry(STUDY_DIR / "hypotheses")
    registration = registry.get("H0013", version=1)
    trial_spec = run_trial.build_trial_spec(
        registration.spec,
        hypothesis_fingerprint=registration.spec_fingerprint,
        data_fingerprint="0" * 64,
        code_revision="test000",
    )
    experiment = run_trial.build_experiment(panel, observations, registration.spec)
    metrics: dict[str, Any] = experiment(trial_spec)
    return metrics


def test_verdict_supported_on_planted_effect(
    effect_data: SyntheticData, run_trial: ModuleType
) -> None:
    panel, _, _ = effect_data
    observations, _, _ = _synthetic_series(seed=7, beta=-0.002)
    metrics = _run_experiment(run_trial, panel, observations)
    assert metrics["verdict"]["criteria"] == {
        "holm_adjusted_primary_p_below_0.05": True,
        "primary_partial_r_squared_at_least_0.005": True,
        "holdout_oos_incremental_r_squared_above_0": True,
        "net_daily_edge_after_costs_positive": True,
    }
    assert metrics["verdict"]["supported"] is True


def test_verdict_rejected_on_noise(noise_data: SyntheticData, run_trial: ModuleType) -> None:
    panel, _, _ = noise_data
    observations, _, _ = _synthetic_series(seed=11, beta=0.0)
    metrics = _run_experiment(run_trial, panel, observations)
    assert metrics["verdict"]["criteria"][
        "holm_adjusted_primary_p_below_0.05"
    ] is False
    assert metrics["verdict"]["criteria"][
        "primary_partial_r_squared_at_least_0.005"
    ] is False
    assert metrics["verdict"]["supported"] is False


# --- Registration: fingerprint and preregister idempotency ---


def test_registered_h0013_fingerprint_recomputes() -> None:
    registry = HypothesisRegistry(STUDY_DIR / "hypotheses")
    registration = registry.get("H0013", version=1)
    fingerprint = hashlib.sha256(
        canonical_json(registration.spec.model_dump(mode="json"))
    ).hexdigest()
    assert fingerprint == registration.spec_fingerprint == H0013_FINGERPRINT
    params = dict(
        item.split("=", maxsplit=1)
        for item in registration.spec.fixed_parameters
    )
    assert params["predictor_lag_steps"] == "2"
    assert params["control_lag_steps"] == "1"
    assert params["predictor_transform"] == "level-change-bp"
    assert registration.spec.expected_direction == "negative"
    assert registration.spec.planned_test_count == 1


def test_preregister_is_idempotent(tmp_path: Path) -> None:
    """Re-running preregister.py leaves an existing registration untouched.

    Regression guard for the scaffold's non-idempotent preregister
    (first real use found re-running would attempt a duplicate
    registration). Copies the study directory, registers fresh, then
    re-runs: the registration and the event chain must be byte-identical,
    and the fingerprint must re-derive to the committed value.
    """
    target = tmp_path / "credit-spread-spx-008"
    shutil.copytree(
        STUDY_DIR,
        target,
        ignore=shutil.ignore_patterns(
            "trials.jsonl*",
            "manifest.json",
            "panel-summary.json",
            "__pycache__",
        ),
    )
    (target / "hypotheses" / "registrations" / "H0013" / "v1.json").unlink()
    (target / "hypotheses" / "hypothesis-events.jsonl").unlink()
    module = _load_module(target / "preregister.py", "study_008_preregister")
    assert module.find_todos() == []
    module.main()
    registration_path = (
        target / "hypotheses" / "registrations" / "H0013" / "v1.json"
    )
    events_path = target / "hypotheses" / "hypothesis-events.jsonl"
    first_registration = registration_path.read_bytes()
    first_events = events_path.read_bytes()
    registration = json.loads(first_registration)
    assert registration["spec_fingerprint"] == H0013_FINGERPRINT
    module.main()
    assert registration_path.read_bytes() == first_registration
    assert events_path.read_bytes() == first_events
