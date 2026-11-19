"""Tests for study 010 (BAA10Y -> VIX, H0015/T0018).

All offline: synthetic business-day data, no network, no dependence on
the gitignored fetch cache. The synthetic panel mirrors the real study's
shape (three instruments, US-equity closes at 21:00 UTC, weekend gaps,
full window 2003-01-02 to the fetch date — VIX is still published, so
unlike study 009 there is no truncation) so the tests exercise the same
code paths the trial ran on real data:

- panel construction: diff-then-join row counts, the full window, and
  the PIT semantics of the lagged predictors (the BAA10Y change ending
  two trading days before the decision close; the SPX change over the
  decision day itself, knowable at the close because Yahoo posts the
  same evening);
- trial logic: the partial test, walk-forward OOS evaluation, the
  informational cost assessment (gross edge only, no costs) and the
  three-criterion verdict, on a planted effect (verdict SUPPORTED)
  and on pure noise (verdict REJECTED);
- scaffold/registration regression: the preregister script is
  idempotent, and the committed H0015 v1 fingerprint re-derives from
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
STUDY_DIR = REPO_ROOT / "research" / "credit-spread-vix-010"

# A synthetic panel + lagged frame + hand-computed truth series.
SyntheticData = tuple[
    SynchronizedPanel, pd.DataFrame, dict[str, np.ndarray]
]

BAA10Y = "credit:baa-10y-spread"
VIX = "index:vix"
SPX = "index:sp500"

# The committed H0015 v1 fingerprint (from the study report); the
# idempotency test re-derives it from the design in a clean directory.
H0015_FINGERPRINT = (
    "eb8b21955fcf8ece287a15372b6ee845297a47d348325f5eae2bc728a1f001cf"
)

# The real study's window: VIX is still published, so the sample runs
# to the fetch date (the FRED legs bind one trading day behind it).
WINDOW_START = "2003-01-02"
WINDOW_END = "2026-11-18"


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

    BAA10Y is a mean-reverting spread level (changes ~3bp std); SPX is
    a mean-reverting log level (changes ~1% std); VIX log changes
    follow ``beta * baa_change[k-3] + noise`` in return-row
    coordinates, so the planted effect sits exactly on the trial's
    alignment (the lagged BAA10Y change at frame row j predicts the
    VIX log change at frame row j+1). ``beta=0`` is the pure-noise
    case. VIX noise std 0.0738 matches the real series' daily
    log-change std.
    """
    dates = pd.bdate_range(WINDOW_START, WINDOW_END)
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

    spx_log = np.empty(n_closes)
    spx_log[0] = math.log(4000.0)
    for i in range(1, n_closes):
        change = -0.01 * (spx_log[i - 1] - math.log(4000.0)) + rng.normal(0.0, 0.01)
        spx_log[i] = spx_log[i - 1] + change
    spx_logchg = np.diff(spx_log)

    vix_ret = np.empty(n_returns)
    noise = rng.normal(0.0, 0.0738, size=n_returns)
    for k in range(n_returns):
        vix_ret[k] = noise[k] + (beta * baa_chg[k - 3] if k >= 3 else 0.0)
    vix_levels = 20.0 * np.exp(np.concatenate([[0.0], np.cumsum(vix_ret)]))

    ingested_at = datetime(2026, 11, 19, 2, 53, tzinfo=UTC)
    observations: list[Observation] = []
    for instrument, levels, source_id in (
        (BAA10Y, baa_levels, "fred"),
        (VIX, vix_levels, "fred"),
        (SPX, np.exp(spx_log), "yahoo-finance"),
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
        "spx_logchg": spx_logchg,
        "vix_ret": vix_ret,
    }
    return observations, truth, event_times


@pytest.fixture(scope="module")
def run_trial() -> ModuleType:
    return _load_module(STUDY_DIR / "run_trial.py", "study_010_run_trial")


@pytest.fixture(scope="module")
def effect_data(run_trial: ModuleType) -> SyntheticData:
    observations, truth, _ = _synthetic_series(seed=7, beta=0.008)
    panel = build_synchronized_panel(
        observations, instruments=(BAA10Y, VIX, SPX)
    )
    frame, _ = run_trial.build_lagged_frame(
        panel, observations, baa_lag_steps=2, spx_lag_steps=0
    )
    return panel, frame, truth


@pytest.fixture(scope="module")
def noise_data(run_trial: ModuleType) -> SyntheticData:
    observations, truth, _ = _synthetic_series(seed=11, beta=0.0)
    panel = build_synchronized_panel(
        observations, instruments=(BAA10Y, VIX, SPX)
    )
    frame, _ = run_trial.build_lagged_frame(
        panel, observations, baa_lag_steps=2, spx_lag_steps=0
    )
    return panel, frame, truth


# --- Panel construction: diff-then-join, full window, PIT semantics ---


def test_panel_diff_then_join_row_counts(effect_data: SyntheticData) -> None:
    panel, _, _ = effect_data
    # One close per business day; the first return row is dropped (no
    # prior close). No missing values, so no other rows drop.
    n_closes = len(pd.bdate_range(WINDOW_START, WINDOW_END))
    assert panel.row_count == n_closes - 1
    assert panel.dropped_close_rows == 0
    assert panel.dropped_return_rows == 1
    assert panel.returns.index[0] == pd.Timestamp("2003-01-03 21:00:00+00:00")
    assert panel.returns.index[-1] == pd.Timestamp("2026-11-18 21:00:00+00:00")


def test_panel_runs_the_full_window(
    effect_data: SyntheticData,
) -> None:
    """The window ends at the fetch date, not at a discontinuation.

    Unlike study 009 (TYVIX ended 2020-05-15), VIX is still published,
    so the real study's sample runs to the fetch date; the FRED legs
    bind one trading day behind it (last panel row 2026-11-17) while
    the SPX leg reaches 2026-11-18. The committed panel summary pins
    the real panel's endpoints and counts.
    """
    panel, frame, _ = effect_data
    assert panel.returns.index[-1] == pd.Timestamp("2026-11-18 21:00:00+00:00")
    assert frame.index[-1] == pd.Timestamp("2026-11-18 21:00:00+00:00")
    summary = json.loads((STUDY_DIR / "panel-summary.json").read_text())
    assert summary["panel"]["return_rows"] == 5960
    assert summary["panel"]["close_rows"] == 5961
    assert summary["panel"]["dropped_close_rows"] == 88
    assert summary["panel"]["dropped_return_rows"] == 89
    assert summary["panel"]["first_return_time"] == "2003-01-03T21:00:00+00:00"
    assert summary["panel"]["last_return_time"] == "2026-11-17T21:00:00+00:00"
    per_instrument = {
        entry["instrument_id"]: entry["items"]
        for entry in summary["panels"]
    }
    assert per_instrument == {
        BAA10Y: 5968,
        VIX: 6042,
        SPX: 6009,
    }


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
    trading days earlier (return index j), the SPX log change over the
    decision day itself (return index j+2 — Yahoo posts the close the
    same evening, so it is knowable at the close), and the VIX log
    change of the row itself — all hand-computed from the synthetic
    closes.
    """
    panel, frame, truth = effect_data
    assert len(frame) == len(panel.returns) - 2
    assert frame.isna().sum().sum() == 0
    for j in (0, 1, 100, 1000, 3000, len(frame) - 1):
        assert frame["baa_lagged"].iloc[j] == pytest.approx(truth["baa_chg"][j])
        assert frame["spx_lagged"].iloc[j] == pytest.approx(
            truth["spx_logchg"][j + 2]
        )
        assert frame["baa_naive"].iloc[j] == pytest.approx(truth["baa_chg"][j + 2])
        assert frame["vix"].iloc[j] == pytest.approx(truth["vix_ret"][j + 2])
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
        frame["vix"].to_numpy(dtype=float),
        factor_name="spx",
        factor=frame["spx_lagged"].to_numpy(dtype=float),
        max_hac_lag=5,
    )
    assert result["coefficient"] == pytest.approx(0.008, abs=0.001)
    assert result["p_value"] < 1e-10
    assert result["partial_r_squared"] > 0.005


def test_partial_test_null_on_noise(noise_data: SyntheticData, run_trial: ModuleType) -> None:
    _, frame, _ = noise_data
    result = run_trial._partial_test(
        frame["baa_lagged"].to_numpy(dtype=float),
        frame["vix"].to_numpy(dtype=float),
        factor_name="spx",
        factor=frame["spx_lagged"].to_numpy(dtype=float),
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
    assert result["folds"] > 20
    assert result["skipped_folds"] == 0
    assert result["holdout_oos_incremental_r_squared"] > 0.03
    assert result["all_oos_incremental_r_squared"] > 0.03


def test_cost_gate_informational_applies_no_costs(run_trial: ModuleType) -> None:
    """Hand-computed sign-rule case: gross edge only, zero costs.

    VIX is not tradable, so the study-003 precedent applies: the
    assessment reports the gross edge and the sign accuracy, applies
    no costs, and carries no verdict weight.
    """
    forecasts = [0.01, -0.01, -0.01, 0.01]
    actuals = [0.02, 0.01, -0.01, 0.03]
    result = run_trial.run_cost_gate_informational(
        forecasts, actuals, block_length=2, resamples=100, seed=42
    )
    # Positions +1, -1, -1, +1. Gross: +0.02 -0.01 +0.01 +0.03 = 0.05.
    # Sign accuracy: 3 of 4 (the second forecast misses the sign).
    assert result["days"] == 4
    assert result["gross_daily_edge"] == pytest.approx(0.05 / 4)
    assert result["costs_applied"] == 0.0
    assert result["sign_accuracy"] == pytest.approx(0.75)
    assert "net_daily_edge" not in result
    assert result["gross_edge_ci_lower"] <= result["gross_daily_edge"]
    assert result["gross_daily_edge"] <= result["gross_edge_ci_upper"]
    assert 0.0 <= result["gross_edge_bootstrap_p_value"] <= 1.0


def _run_experiment(
    run_trial: ModuleType,
    panel: SynchronizedPanel,
    observations: list[Observation],
) -> dict[str, Any]:
    registry = HypothesisRegistry(STUDY_DIR / "hypotheses")
    registration = registry.get("H0015", version=1)
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
    observations, _, _ = _synthetic_series(seed=7, beta=0.008)
    metrics = _run_experiment(run_trial, panel, observations)
    assert metrics["verdict"]["criteria"] == {
        "holm_adjusted_primary_p_below_0.05": True,
        "primary_partial_r_squared_at_least_0.005": True,
        "holdout_oos_incremental_r_squared_above_0": True,
    }
    assert metrics["verdict"]["supported"] is True
    # The informational cost assessment is reported but is not a
    # verdict criterion.
    assert "cost_gate_informational" in metrics
    assert "cost_gate" not in metrics


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


def test_registered_h0015_fingerprint_recomputes() -> None:
    registry = HypothesisRegistry(STUDY_DIR / "hypotheses")
    registration = registry.get("H0015", version=1)
    fingerprint = hashlib.sha256(
        canonical_json(registration.spec.model_dump(mode="json"))
    ).hexdigest()
    assert fingerprint == registration.spec_fingerprint == H0015_FINGERPRINT
    params = dict(
        item.split("=", maxsplit=1)
        for item in registration.spec.fixed_parameters
    )
    assert params["predictor_lag_steps"] == "2"
    assert params["control_lag_steps"] == "0"
    assert params["predictor_transform"] == "level-change-bp"
    assert params["control_transform"] == "log-change"
    assert params["target_transform"] == "log-change"
    assert params["sample_start"] == "2003-01-02"
    assert params["sample_end"] == "2026-11-19"
    assert registration.spec.expected_direction == "positive"
    assert registration.spec.planned_test_count == 1


def test_preregister_is_idempotent(tmp_path: Path) -> None:
    """Re-running preregister.py leaves an existing registration untouched.

    Regression guard for the scaffold's non-idempotent preregister
    (first real use found re-running would attempt a duplicate
    registration). Copies the study directory, registers fresh, then
    re-runs: the registration and the event chain must be byte-identical,
    and the fingerprint must re-derive to the committed value.
    """
    target = tmp_path / "credit-spread-vix-010"
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
    (target / "hypotheses" / "registrations" / "H0015" / "v1.json").unlink()
    (target / "hypotheses" / "hypothesis-events.jsonl").unlink()
    module = _load_module(target / "preregister.py", "study_010_preregister")
    assert module.find_todos() == []
    module.main()
    registration_path = (
        target / "hypotheses" / "registrations" / "H0015" / "v1.json"
    )
    events_path = target / "hypotheses" / "hypothesis-events.jsonl"
    first_registration = registration_path.read_bytes()
    first_events = events_path.read_bytes()
    registration = json.loads(first_registration)
    assert registration["spec_fingerprint"] == H0015_FINGERPRINT
    module.main()
    assert registration_path.read_bytes() == first_registration
    assert events_path.read_bytes() == first_events
