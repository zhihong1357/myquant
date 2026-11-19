"""Tests for study 012 (BAA10Y -> DGS10, H0017/T0020).

All offline: synthetic business-day data, no network, no dependence on
the gitignored fetch cache. The synthetic panel mirrors the real study's
shape (three instruments, US-equity closes at 21:00 UTC, weekend gaps,
full window 2003-01-02 to the fetch date — DGS10 is still published, so
unlike study 009 there is no truncation) so the tests exercise the same
code paths the trial ran on real data:

- panel construction: diff-then-join row counts, the full window, and
  the PIT semantics of the lagged predictors (the BAA10Y change ending
  two trading days before the decision close; the SPX change over the
  decision day itself, knowable at the close because Yahoo posts the
  same evening; the DGS10 guard change at the predictor's value date);
- trial logic: the partial test, walk-forward OOS evaluation, the
  informational cost assessment (gross edge only, no costs, in bp/day)
  and the three-criterion verdict, on a planted effect (verdict
  SUPPORTED) and on pure noise (verdict REJECTED);
- the mechanical guard: on synthetic data where the target's changes
  are autocorrelated and BAA10Y is built as BAA minus DGS10 (the true
  construction), the regression WITHOUT the lag-2 guard shows spurious
  incremental explanatory power and WITH the guard it disappears;
- scaffold/registration regression: the preregister script is
  idempotent for the v2 amendment, and the committed H0017 v2
  fingerprint re-derives from the design in a clean directory.

The planted-effect/noise fixtures use an independent mean-reverting
BAA10Y level (011-style): they test trial logic, not the mechanical
construction. The guard test has its own fixture where BAA10Y is
built as BAA minus DGS10, so the predictor literally contains minus
the target's own lag-2 change.
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
STUDY_DIR = REPO_ROOT / "research" / "credit-spread-dgs10-012"

# A synthetic panel + lagged frame + hand-computed truth series.
SyntheticData = tuple[
    SynchronizedPanel, pd.DataFrame, dict[str, np.ndarray]
]

BAA10Y = "credit:baa-10y-spread"
DGS10 = "rates:us-10y-yield"
SPX = "index:sp500"

# The committed H0017 fingerprints (from the study report); the
# idempotency test re-derives the v2 fingerprint from the design in a
# clean directory.
H0017_V1_FINGERPRINT = (
    "6422913462650bd997d4a221b9cd1c9f529a1c0993ee18bdaf224f8cfdc2cfca"
)
H0017_V2_FINGERPRINT = (
    "dd5e04a370da48c0185eedb78990dea2164d44f1097db646d5e9764a1e9eed2a"
)

# The real study's window: DGS10 is still published, so the sample runs
# to the fetch date (the FRED legs bind one trading day behind it).
WINDOW_START = "2003-01-02"
WINDOW_END = "2026-11-18"

# The guard fixture's window: shorter, so the random-walk DGS10 level
# stays positive for the panel builder (which requires strictly
# positive levels). 4,170 frame rows is plenty for the partial-R^2
# estimates to be precise.
GUARD_WINDOW_END = "2018-12-31"


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _observations_from_levels(
    levels: dict[str, tuple[np.ndarray, str]],
    event_times: list[datetime],
    ingested_at: datetime,
) -> list[Observation]:
    observations: list[Observation] = []
    for instrument, (values, source_id) in levels.items():
        for event_time, value in zip(event_times, values, strict=True):
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
    return observations


def _synthetic_series(
    *,
    seed: int,
    beta: float,
) -> tuple[list[Observation], dict[str, np.ndarray], list[datetime]]:
    """Synthetic closes on the real study's business-day calendar.

    BAA10Y is a mean-reverting spread level (changes ~3bp std); SPX is
    a mean-reverting log level (changes ~1% std); DGS10 level changes
    follow ``beta * baa_change[k-3] + noise`` in return-row
    coordinates, so the planted effect sits exactly on the trial's
    alignment (the lagged BAA10Y change at frame row j predicts the
    DGS10 change at frame row j+1). ``beta=0`` is the pure-noise
    case. DGS10 noise std 5.68bp matches the real series' daily
    change std. The DGS10 level is a random walk, shifted up by a
    constant so it stays positive for the panel builder — a constant
    shift does not change the changes, so the hand-computed truth
    still matches exactly.
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

    dgs_chg = np.empty(n_returns)
    noise = rng.normal(0.0, 5.68, size=n_returns)
    for k in range(n_returns):
        dgs_chg[k] = noise[k] + (beta * baa_chg[k - 3] if k >= 3 else 0.0)
    dgs_levels = 4.0 + np.concatenate([[0.0], np.cumsum(dgs_chg)]) / 100.0
    dgs_levels = dgs_levels - dgs_levels.min() + 1.0  # positivity shift

    ingested_at = datetime(2026, 11, 19, 15, 39, tzinfo=UTC)
    observations = _observations_from_levels(
        {
            BAA10Y: (baa_levels, "fred"),
            DGS10: (dgs_levels, "fred"),
            SPX: (np.exp(spx_log), "yahoo-finance"),
        },
        event_times,
        ingested_at,
    )
    truth = {
        "baa_chg": baa_chg,
        "spx_logchg": spx_logchg,
        "dgs_chg": dgs_chg,
    }
    return observations, truth, event_times


def _guard_series(
    *,
    seed: int,
) -> tuple[SynchronizedPanel, pd.DataFrame]:
    """Synthetic panel with autocorrelated DGS10 changes and the true
    BAA10Y construction (BAA10Y = BAA yield minus DGS10), no planted
    effect. DGS10 changes are AR(2) (phi1 = phi2 = 0.4), so the target
    has lag-3 autocorrelation (0.52) beyond what the lag-1 own-history
    control captures — the channel the lag-2 guard exists to block.
    The AR(2) coefficients are a stress case, far stronger than the
    real DGS10 autocorrelations (-0.0118 / -0.0503); the test proves
    the guard mechanism, not the real magnitude.
    """
    dates = pd.bdate_range(WINDOW_START, GUARD_WINDOW_END)
    event_times = [
        datetime(d.year, d.month, d.day, 21, 0, tzinfo=UTC) for d in dates
    ]
    n_closes = len(dates)
    n_returns = n_closes - 1
    rng = np.random.default_rng(seed)

    dgs_chg = np.zeros(n_returns + 10)
    eps = rng.normal(0.0, 1.0, n_returns + 10)
    for k in range(2, n_returns + 10):
        dgs_chg[k] = 0.4 * dgs_chg[k - 1] + 0.4 * dgs_chg[k - 2] + eps[k]
    dgs_chg = dgs_chg[10:] / dgs_chg[10:].std() * 2.0  # 2bp std
    dgs_levels = 4.0 + np.concatenate([[0.0], np.cumsum(dgs_chg)]) / 100.0

    baa_yield = np.empty(n_closes)
    baa_yield[0] = 9.0
    for i in range(1, n_closes):
        change = -0.01 * (baa_yield[i - 1] - 9.0) + rng.normal(0.0, 0.01)
        baa_yield[i] = baa_yield[i - 1] + change
    # BAA10Y = BAA - DGS10, the true construction: the predictor
    # literally contains minus the target's own change.
    baa_levels = baa_yield - dgs_levels

    spx_log = np.empty(n_closes)
    spx_log[0] = math.log(4000.0)
    for i in range(1, n_closes):
        change = -0.01 * (spx_log[i - 1] - math.log(4000.0)) + rng.normal(0.0, 0.01)
        spx_log[i] = spx_log[i - 1] + change

    ingested_at = datetime(2026, 11, 19, 15, 39, tzinfo=UTC)
    observations = _observations_from_levels(
        {
            BAA10Y: (baa_levels, "fred"),
            DGS10: (dgs_levels, "fred"),
            SPX: (np.exp(spx_log), "yahoo-finance"),
        },
        event_times,
        ingested_at,
    )
    panel = build_synchronized_panel(
        observations, instruments=(BAA10Y, DGS10, SPX)
    )
    run_trial = _load_module(STUDY_DIR / "run_trial.py", "study_012_run_trial_guard")
    frame, _ = run_trial.build_lagged_frame(
        panel, observations, baa_lag_steps=2, spx_lag_steps=0, guard_lag_steps=2
    )
    return panel, frame


@pytest.fixture(scope="module")
def run_trial() -> ModuleType:
    return _load_module(STUDY_DIR / "run_trial.py", "study_012_run_trial")


@pytest.fixture(scope="module")
def effect_data(run_trial: ModuleType) -> SyntheticData:
    observations, truth, _ = _synthetic_series(seed=7, beta=0.8)
    panel = build_synchronized_panel(
        observations, instruments=(BAA10Y, DGS10, SPX)
    )
    frame, _ = run_trial.build_lagged_frame(
        panel, observations, baa_lag_steps=2, spx_lag_steps=0, guard_lag_steps=2
    )
    return panel, frame, truth


@pytest.fixture(scope="module")
def noise_data(run_trial: ModuleType) -> SyntheticData:
    observations, truth, _ = _synthetic_series(seed=11, beta=0.0)
    panel = build_synchronized_panel(
        observations, instruments=(BAA10Y, DGS10, SPX)
    )
    frame, _ = run_trial.build_lagged_frame(
        panel, observations, baa_lag_steps=2, spx_lag_steps=0, guard_lag_steps=2
    )
    return panel, frame, truth


@pytest.fixture(scope="module")
def guard_data() -> tuple[SynchronizedPanel, pd.DataFrame]:
    return _guard_series(seed=123)


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

    Unlike study 009 (TYVIX ended 2020-05-15), DGS10 is still
    published, so the real study's sample runs to the fetch date; the
    FRED legs bind one trading day behind it (last panel row
    2026-11-17) while the SPX leg reaches 2026-11-18. The committed
    panel summary pins the real panel's endpoints and counts.
    """
    panel, frame, _ = effect_data
    assert panel.returns.index[-1] == pd.Timestamp("2026-11-18 21:00:00+00:00")
    assert frame.index[-1] == pd.Timestamp("2026-11-18 21:00:00+00:00")
    summary = json.loads((STUDY_DIR / "panel-summary.json").read_text())
    assert summary["panel"]["return_rows"] == 5960
    assert summary["panel"]["close_rows"] == 5961
    assert summary["panel"]["dropped_close_rows"] == 58
    assert summary["panel"]["dropped_return_rows"] == 59
    assert summary["panel"]["first_return_time"] == "2003-01-03T21:00:00+00:00"
    assert summary["panel"]["last_return_time"] == "2026-11-17T21:00:00+00:00"
    per_instrument = {
        entry["instrument_id"]: entry["items"]
        for entry in summary["panels"]
    }
    assert per_instrument == {
        BAA10Y: 5968,
        DGS10: 5973,
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
    same evening, so it is knowable at the close), the DGS10 guard
    change at the predictor's value date (return index j), and the
    DGS10 change of the row itself — all hand-computed from the
    synthetic closes. The derived BAA change is the identity
    ΔBAA = ΔBAA10Y + ΔDGS10 at the predictor's value date.
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
        assert frame["dgs10"].iloc[j] == pytest.approx(truth["dgs_chg"][j + 2])
        assert frame["dgs10_guard"].iloc[j] == pytest.approx(truth["dgs_chg"][j])
        assert frame["baa_derived"].iloc[j] == pytest.approx(
            truth["baa_chg"][j] + truth["dgs_chg"][j]
        )
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
        frame["dgs10"].to_numpy(dtype=float),
        factors={
            "spx": frame["spx_lagged"].to_numpy(dtype=float),
            "guard": frame["dgs10_guard"].to_numpy(dtype=float),
        },
        max_hac_lag=5,
    )
    assert result["coefficient"] == pytest.approx(0.8, abs=0.1)
    assert result["p_value"] < 1e-10
    assert result["partial_r_squared"] > 0.005


def test_partial_test_null_on_noise(noise_data: SyntheticData, run_trial: ModuleType) -> None:
    _, frame, _ = noise_data
    result = run_trial._partial_test(
        frame["baa_lagged"].to_numpy(dtype=float),
        frame["dgs10"].to_numpy(dtype=float),
        factors={
            "spx": frame["spx_lagged"].to_numpy(dtype=float),
            "guard": frame["dgs10_guard"].to_numpy(dtype=float),
        },
        max_hac_lag=5,
    )
    assert result["p_value"] > 0.05
    assert result["partial_r_squared"] < 0.005


def test_mechanical_guard_removes_spurious_effect(
    guard_data: tuple[SynchronizedPanel, pd.DataFrame],
    run_trial: ModuleType,
) -> None:
    """The lag-2 guard blocks the mechanical channel.

    The fixture has no planted effect: BAA10Y is built as BAA minus
    DGS10, so the predictor contains minus the target's own lag-2
    change, and the target's changes are AR(2) — the lag-3
    autocorrelation (0.52) survives the lag-1 own-history control, so
    the unguarded regression "finds" transmission that is purely
    mechanical (partial R² above the 0.005 threshold, highly
    significant, negative coefficient — the mechanical sign). Adding
    the guard — the target's own change at the predictor's value date
    — removes it: the partial R² collapses below the threshold and the
    p-value rises above 0.05. The guard is what stands between this
    study and a false positive.
    """
    _, frame = guard_data
    source = frame["baa_lagged"].to_numpy(dtype=float)
    target = frame["dgs10"].to_numpy(dtype=float)
    spx = frame["spx_lagged"].to_numpy(dtype=float)
    guard = frame["dgs10_guard"].to_numpy(dtype=float)
    unguarded = run_trial._partial_test(
        source, target, factors={"spx": spx}, max_hac_lag=5
    )
    assert unguarded["coefficient"] < 0.0  # the mechanical sign
    assert unguarded["p_value"] < 0.05
    assert unguarded["partial_r_squared"] > 0.005
    guarded = run_trial._partial_test(
        source, target, factors={"spx": spx, "guard": guard}, max_hac_lag=5
    )
    assert guarded["p_value"] > 0.05
    assert guarded["partial_r_squared"] < 0.005


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

    DGS10 is a yield and is not directly tradable, so the study-003
    precedent applies: the assessment reports the gross edge in basis
    points per day and the sign accuracy, applies no costs, and
    carries no verdict weight.
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
    assert result["units"] == "basis points per day"
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
    registration = registry.get("H0017", version=2)
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
    observations, _, _ = _synthetic_series(seed=7, beta=0.8)
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


def test_registered_h0017_v2_fingerprint_recomputes() -> None:
    registry = HypothesisRegistry(STUDY_DIR / "hypotheses")
    registration = registry.get("H0017", version=2)
    fingerprint = hashlib.sha256(
        canonical_json(registration.spec.model_dump(mode="json"))
    ).hexdigest()
    assert fingerprint == registration.spec_fingerprint == H0017_V2_FINGERPRINT
    params = dict(
        item.split("=", maxsplit=1)
        for item in registration.spec.fixed_parameters
    )
    assert params["predictor_lag_steps"] == "2"
    assert params["control_lag_steps"] == "0"
    assert params["guard_lag_steps"] == "2"
    assert params["predictor_transform"] == "level-change-bp"
    assert params["control_transform"] == "log-change"
    assert params["target_transform"] == "level-change-bp"
    assert params["sample_start"] == "2003-01-02"
    assert params["sample_end"] == "2026-11-19"
    assert registration.spec.expected_direction == "negative"
    assert registration.spec.planned_test_count == 1
    # V1 is still registered and untouched; the v2 amendment dropped
    # the BAA fetch leg (FRED BAA is monthly only), so the v2 universe
    # has three instruments where v1 had four.
    v1 = registry.get("H0017", version=1)
    assert v1.spec_fingerprint == H0017_V1_FINGERPRINT
    assert list(v1.spec.universe) == [
        "credit:baa-10y-spread",
        "rates:us-10y-yield",
        "index:sp500",
        "credit:baa-yield",
    ]
    assert list(registration.spec.universe) == [
        "credit:baa-10y-spread",
        "rates:us-10y-yield",
        "index:sp500",
    ]


def test_preregister_is_idempotent(tmp_path: Path) -> None:
    """Re-running preregister.py leaves an existing registration untouched.

    Regression guard for the scaffold's non-idempotent preregister
    (first real use found re-running would attempt a duplicate
    registration). Copies the study directory, resets it to the
    pre-amendment state (v1 registered, v2 absent, the event chain
    truncated to the v1 registration event), then runs main() twice:
    the first run registers the v2 amendment, the second leaves the
    registration and the event chain byte-identical, and the
    fingerprint re-derives to the committed v2 value.
    """
    target = tmp_path / "credit-spread-dgs10-012"
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
    (target / "hypotheses" / "registrations" / "H0017" / "v2.json").unlink()
    events_path = target / "hypotheses" / "hypothesis-events.jsonl"
    first_event = events_path.read_text().splitlines()[0]
    events_path.write_text(first_event + "\n")
    module = _load_module(target / "preregister.py", "study_012_preregister")
    assert module.find_todos() == []
    module.main()
    registration_path = (
        target / "hypotheses" / "registrations" / "H0017" / "v2.json"
    )
    first_registration = registration_path.read_bytes()
    first_events = events_path.read_bytes()
    registration = json.loads(first_registration)
    assert registration["spec_fingerprint"] == H0017_V2_FINGERPRINT
    module.main()
    assert registration_path.read_bytes() == first_registration
    assert events_path.read_bytes() == first_events
