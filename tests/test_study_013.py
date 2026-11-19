"""Tests for study 013 (BTC -> BTC_DVOL, H0018/T0021).

All offline: synthetic 24/7 calendar data, no network, no dependence
on the gitignored fetch cache. The synthetic panel mirrors the real
study's shape (three instruments on consecutive calendar days at
16:00 UTC, BTC/ETH closes from 2021-03-01, DVOL snapshots from
2021-03-24) so the tests exercise the same code paths the trial ran
on real data:

- panel construction: diff-then-join row counts (2,066 return rows,
  22 dropped close rows, 23 dropped return rows), the DVOL 16:00 UTC
  snapshot convention (observation event_time = snapshot minus one
  day, available_at = snapshot time), PIT semantics of the frame
  (the BTC return over the bar opening at t predicts the DVOL change
  from snapshot t to snapshot t+1, both knowable at the 16:00 UTC
  decision close), and weekend returns (crypto is 24/7 — no weekend
  gaps, no bar_seconds filter);
- trial logic: the partial test, walk-forward OOS evaluation, the
  informational cost assessment (gross edge only, no costs, in
  log-change units per day) and the three-criterion verdict, on a
  planted leverage effect (verdict SUPPORTED) and on pure noise
  (verdict REJECTED);
- scaffold/registration regression: the preregister script is
  idempotent, and the committed H0018 v1 fingerprint re-derives from
  the design in a clean directory.

The planted effect is a leverage effect: the DVOL log change over
the bar opening at t+1 follows ``beta * btc_log_return[t]`` with
beta = -0.6 (a BTC fall predicts a next-day DVOL rise), on top of
noise with the real series' daily change std (4.46%). ``beta=0`` is
the pure-noise case. The ETH control is correlated with BTC (0.7
weight) so the partial test exercises the common-factor absorption.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import shutil
import sys
from datetime import UTC, datetime, timedelta
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
STUDY_DIR = REPO_ROOT / "research" / "btc-dvol-013"

# A synthetic panel + frame + hand-computed truth series.
SyntheticData = tuple[SynchronizedPanel, pd.DataFrame, dict[str, np.ndarray]]

BTC = "crypto:btc-usdt-perp"
BTC_DVOL = "index:btc-dvol"
ETH = "crypto:eth-usdt-perp"

# The committed H0018 v1 fingerprint (from the study report); the
# idempotency test re-derives it from the design in a clean directory.
H0018_V1_FINGERPRINT = (
    "463f8e79462335dbc872cb86b2e33b9972ad3b2407beeae0ef1479bd84c674c1"
)

# The real study's window: BTC/ETH closes from 2021-03-01 (last
# confirmed bar opens 2026-11-18 — the fetch ran before the bar
# opening 2026-11-19 closed), DVOL snapshots from 2021-03-24
# through the fetch date 2026-11-19.
CLOSE_START = "2021-03-01"
CLOSE_END = "2026-11-18"
SNAPSHOT_START = "2021-03-24"
SNAPSHOT_END = "2026-11-19"

# Panel return row k (event_time SNAPSHOT_START + k days) pairs the
# BTC log return at btc_logchg index SNAPSHOT_OFFSET + k with the DVOL
# change log(snapshot[k+1] / snapshot[k]).
SNAPSHOT_OFFSET = 22  # 2021-03-01 -> 2021-03-24 is 23 closes, 22 returns


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
) -> tuple[list[Observation], dict[str, np.ndarray]]:
    """Synthetic closes on the real study's 24/7 calendar.

    BTC log levels are mean-reverting (changes ~2.8% std, the real
    series' daily return std); ETH changes are 0.7 * BTC change plus
    independent noise (a crypto common factor); the DVOL snapshot log
    changes follow ``beta * btc_logchg[k-1] + noise`` in panel-row
    coordinates, so the planted effect sits exactly on the trial's
    alignment (the BTC return over the bar opening at t predicts the
    DVOL change from snapshot t to snapshot t+1). ``beta=0`` is the
    pure-noise case. DVOL noise std 4.46% matches the real series'
    daily change std. DVOL observations carry the snapshot value at
    event_time = snapshot minus one day, available_at = snapshot time
    — the study's preregistered snapshot convention.
    """
    close_dates = pd.date_range(CLOSE_START, CLOSE_END, freq="D")
    close_times = [
        datetime(d.year, d.month, d.day, 16, 0, tzinfo=UTC) for d in close_dates
    ]
    n_closes = len(close_dates)
    rng = np.random.default_rng(seed)

    btc_log = np.empty(n_closes)
    btc_log[0] = math.log(50000.0)
    for i in range(1, n_closes):
        btc_log[i] = (
            btc_log[i - 1]
            - 0.01 * (btc_log[i - 1] - math.log(50000.0))
            + rng.normal(0.0, 0.028)
        )
    btc_logchg = np.diff(btc_log)

    eth_logchg = 0.7 * btc_logchg + 0.7 * rng.normal(0.0, 0.028, size=n_closes - 1)
    eth_log = np.concatenate(
        [[math.log(3000.0)], math.log(3000.0) + np.cumsum(eth_logchg)]
    )

    snap_dates = pd.date_range(SNAPSHOT_START, SNAPSHOT_END, freq="D")
    snap_times = [
        datetime(d.year, d.month, d.day, 16, 0, tzinfo=UTC) for d in snap_dates
    ]
    n_snaps = len(snap_dates)
    dvol_chg = np.empty(n_snaps - 1)
    noise = rng.normal(0.0, 0.0446, size=n_snaps - 1)
    for k in range(n_snaps - 1):
        dvol_chg[k] = noise[k] + (
            beta * btc_logchg[SNAPSHOT_OFFSET + k - 1] if k >= 1 else 0.0
        )
    dvol_snap_log = np.concatenate(
        [[math.log(80.0)], math.log(80.0) + np.cumsum(dvol_chg)]
    )

    ingested_at = datetime(2026, 11, 21, 0, 0, tzinfo=UTC)
    observations: list[Observation] = []
    for instrument, levels, source_id in (
        (BTC, np.exp(btc_log), "okx-public"),
        (ETH, np.exp(eth_log), "okx-public"),
    ):
        for event_time, value in zip(close_times, levels, strict=True):
            observations.append(
                Observation(
                    instrument_id=instrument,
                    venue="synthetic",
                    event_time=event_time,
                    available_at=event_time + timedelta(days=1),
                    ingested_at=ingested_at,
                    field="close",
                    value=float(value),
                    unit="synthetic",
                    source_id=source_id,
                    source_version=1,
                )
            )
    for snap_time, snap_log in zip(snap_times, dvol_snap_log, strict=True):
        observations.append(
            Observation(
                instrument_id=BTC_DVOL,
                venue="synthetic",
                event_time=snap_time - timedelta(days=1),
                available_at=snap_time,
                ingested_at=ingested_at,
                field="close",
                value=float(math.exp(snap_log)),
                unit="synthetic",
                source_id="deribit",
                source_version=1,
            )
        )
    truth = {
        "btc_logchg": btc_logchg,
        "eth_logchg": eth_logchg,
        "dvol_chg": dvol_chg,
        "dvol_snap_log": dvol_snap_log,
    }
    return observations, truth


@pytest.fixture(scope="module")
def run_trial() -> ModuleType:
    return _load_module(STUDY_DIR / "run_trial.py", "study_013_run_trial")


def _build_data(
    run_trial: ModuleType, *, seed: int, beta: float
) -> SyntheticData:
    observations, truth = _synthetic_series(seed=seed, beta=beta)
    panel = build_synchronized_panel(
        observations, instruments=(BTC, BTC_DVOL, ETH)
    )
    frame = run_trial.build_frame(panel)
    return panel, frame, truth


@pytest.fixture(scope="module")
def effect_data(run_trial: ModuleType) -> SyntheticData:
    return _build_data(run_trial, seed=7, beta=-0.6)


@pytest.fixture(scope="module")
def noise_data(run_trial: ModuleType) -> SyntheticData:
    return _build_data(run_trial, seed=11, beta=0.0)


# --- Panel construction: diff-then-join, snapshot convention, PIT ---


def test_panel_diff_then_join_row_counts(effect_data: SyntheticData) -> None:
    panel, _, _ = effect_data
    # BTC/ETH closes run 2021-03-01 -> 2026-11-18 (2,089 each); DVOL
    # levels run 2021-03-23 -> 2026-11-18 (2,067). The synchronized
    # close panel is the intersection (2,067 rows); 22 close rows drop
    # (2021-03-01 -> 2021-03-22, pre-DVOL). Returns are computed
    # per-series first, then joined: 2,066 return rows, 23 dropped
    # (the first NaN return row plus the 22 pre-DVOL rows).
    assert panel.row_count == 2066
    assert panel.dropped_close_rows == 22
    assert panel.dropped_return_rows == 23
    assert panel.returns.index[0] == pd.Timestamp("2021-03-24 16:00:00+00:00")
    assert panel.returns.index[-1] == pd.Timestamp("2026-11-18 16:00:00+00:00")


def test_panel_real_counts_pinned() -> None:
    """The committed ledger and panel summary pin the real panel.

    The synthetic fixture above reproduces the real panel's shape
    exactly (2,066 return rows, 22/23 dropped); this test pins the
    real numbers themselves so a regeneration that changed them would
    fail loudly.
    """
    records = [
        json.loads(line)
        for line in (STUDY_DIR / "trials.jsonl").read_text().splitlines()
    ]
    assert len(records) == 1
    panel = records[0]["result"]["metrics"]["panel"]
    assert panel["daily_rows"] == 2066
    assert panel["frame_rows"] == 2066
    assert panel["daily_dropped_close_rows"] == 22
    assert panel["daily_dropped_return_rows"] == 23
    assert panel["daily_first"] == "2021-03-24T16:00:00+00:00"
    assert panel["daily_last"] == "2026-11-18T16:00:00+00:00"
    assert panel["predictor_lag_steps"] == 1
    assert panel["control_lag_steps"] == 0
    summary = json.loads((STUDY_DIR / "panel-summary.json").read_text())
    assert summary["dvol_panel"]["hourly_points"] == 49601
    assert summary["dvol_panel"]["snapshots"] == 2067
    assert summary["dvol_panel"]["missing_snapshots"] == 0
    assert summary["dvol_panel"]["first_snapshot"] == "2021-03-24T16:00:00+00:00"
    assert summary["dvol_panel"]["last_snapshot"] == "2026-11-19T16:00:00+00:00"
    assert summary["quality_row_count"]["pit-1d"] == 22957
    okx = {entry["instrument_id"]: entry for entry in summary["okx_panels"]}
    assert okx[BTC]["candles"] == 2089
    assert okx[ETH]["candles"] == 2089
    assert okx[BTC]["missing_bars"] == 0
    assert okx[ETH]["missing_bars"] == 0


def test_dvol_snapshot_convention() -> None:
    """The DVOL observation carries the snapshot at event_time + 1 day.

    The preregistered convention: the daily DVOL value is the 16:00
    UTC snapshot (close of the hourly DVOL row timestamped 15:00
    UTC). The observation's event_time is the snapshot minus one day
    (matching the OKX candle convention, where event_time is the bar
    open and the close value is the price at bar close) and its
    available_at is the snapshot time itself. The first snapshot is
    2021-03-24T16:00Z, so the first DVOL observation sits at
    2021-03-23T16:00Z and the first DVOL return at 2021-03-24T16:00Z.
    """
    observations, truth = _synthetic_series(seed=7, beta=-0.6)
    dvol_obs = [o for o in observations if o.instrument_id == BTC_DVOL]
    assert len(dvol_obs) == 2067
    first = dvol_obs[0]
    assert first.event_time == datetime(2021, 3, 23, 16, 0, tzinfo=UTC)
    assert first.available_at == datetime(2021, 3, 24, 16, 0, tzinfo=UTC)
    assert first.value == pytest.approx(math.exp(truth["dvol_snap_log"][0]))
    last = dvol_obs[-1]
    assert last.event_time == datetime(2026, 11, 18, 16, 0, tzinfo=UTC)
    assert last.available_at == datetime(2026, 11, 19, 16, 0, tzinfo=UTC)
    assert last.value == pytest.approx(math.exp(truth["dvol_snap_log"][-1]))
    # Every DVOL observation is available exactly one day after its
    # event_time, and the event times are consecutive calendar days.
    for obs in dvol_obs:
        assert obs.available_at - obs.event_time == timedelta(days=1)
    event_times = [o.event_time for o in dvol_obs]
    assert event_times == sorted(event_times)
    assert (event_times[-1] - event_times[0]).days == len(event_times) - 1


def test_frame_pit_semantics(effect_data: SyntheticData) -> None:
    """Frame row j pairs the BTC return over bar j with the DVOL change
    from snapshot j to snapshot j+1 — both knowable at the 16:00 UTC
    decision close of day j+1. All three columns are hand-computed
    from the synthetic levels.
    """
    panel, frame, truth = effect_data
    assert len(frame) == len(panel.returns) == 2066
    assert frame.isna().sum().sum() == 0
    assert list(frame.columns) == ["btc", "dvol", "eth"]
    for j in (0, 1, 100, 1000, 2000, len(frame) - 1):
        assert frame["btc"].iloc[j] == pytest.approx(
            truth["btc_logchg"][SNAPSHOT_OFFSET + j]
        )
        assert frame["dvol"].iloc[j] == pytest.approx(truth["dvol_chg"][j])
        assert frame["eth"].iloc[j] == pytest.approx(
            truth["eth_logchg"][SNAPSHOT_OFFSET + j]
        )
    assert frame.index[0] == pd.Timestamp("2021-03-24 16:00:00+00:00")
    assert frame.index[-1] == pd.Timestamp("2026-11-18 16:00:00+00:00")


def test_panel_keeps_weekend_returns(effect_data: SyntheticData) -> None:
    """Crypto is 24/7: Saturday and Sunday rows are ordinary rows.

    Unlike the US-equity studies, there are no weekend gaps to drop
    and no bar_seconds filter to misfire — every calendar day in the
    window is a return row, weekends included.
    """
    panel, _, _ = effect_data
    weekend = [
        ts for ts in panel.returns.index if ts.weekday() in (5, 6)
    ]
    assert len(weekend) > 500
    assert panel.returns.loc[weekend].notna().all().all()
    # The return index is exactly the consecutive calendar days.
    assert (panel.returns.index[-1] - panel.returns.index[0]).days == (
        len(panel.returns) - 1
    )


# --- Trial logic: partial test, walk-forward, cost gate, verdict ---


def test_partial_test_detects_planted_effect(
    effect_data: SyntheticData, run_trial: ModuleType
) -> None:
    _, frame, _ = effect_data
    result = run_trial._partial_test(
        frame["btc"].to_numpy(dtype=float),
        frame["dvol"].to_numpy(dtype=float),
        factors={"eth": frame["eth"].to_numpy(dtype=float)},
        max_hac_lag=5,
    )
    assert result["coefficient"] == pytest.approx(-0.6, abs=0.1)
    assert result["p_value"] < 1e-10
    assert result["partial_r_squared"] > 0.005


def test_partial_test_null_on_noise(noise_data: SyntheticData, run_trial: ModuleType) -> None:
    _, frame, _ = noise_data
    result = run_trial._partial_test(
        frame["btc"].to_numpy(dtype=float),
        frame["dvol"].to_numpy(dtype=float),
        factors={"eth": frame["eth"].to_numpy(dtype=float)},
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
        holdout_start=datetime(2025, 1, 2, 16, 0, tzinfo=UTC),
    )
    assert result["folds"] == 9
    assert result["skipped_folds"] == 0
    assert result["holdout_oos_incremental_r_squared"] > 0.03
    assert result["all_oos_incremental_r_squared"] > 0.03


def test_cost_gate_informational_applies_no_costs(run_trial: ModuleType) -> None:
    """Hand-computed sign-rule case: gross edge only, zero costs.

    BTC_DVOL is an index and is not directly tradable, and no clean
    free cost series exists for a straddle proxy, so the study-003
    precedent applies: the assessment reports the gross edge in
    log-change units per day and the sign accuracy, applies no costs,
    and carries no verdict weight.
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
    assert result["units"] == "log-change units per day"
    assert "net_daily_edge" not in result
    assert result["gross_edge_ci_lower"] <= result["gross_daily_edge"]
    assert result["gross_daily_edge"] <= result["gross_edge_ci_upper"]
    assert 0.0 <= result["gross_edge_bootstrap_p_value"] <= 1.0


def _run_experiment(
    run_trial: ModuleType,
    panel: SynchronizedPanel,
) -> dict[str, Any]:
    registry = HypothesisRegistry(STUDY_DIR / "hypotheses")
    registration = registry.get("H0018", version=1)
    trial_spec = run_trial.build_trial_spec(
        registration.spec,
        hypothesis_fingerprint=registration.spec_fingerprint,
        data_fingerprint="0" * 64,
        code_revision="test000",
    )
    experiment = run_trial.build_experiment(panel, registration.spec)
    metrics: dict[str, Any] = experiment(trial_spec)
    return metrics


def test_verdict_supported_on_planted_effect(
    effect_data: SyntheticData, run_trial: ModuleType
) -> None:
    panel, _, _ = effect_data
    metrics = _run_experiment(run_trial, panel)
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
    metrics = _run_experiment(run_trial, panel)
    assert metrics["verdict"]["criteria"][
        "holm_adjusted_primary_p_below_0.05"
    ] is False
    assert metrics["verdict"]["criteria"][
        "primary_partial_r_squared_at_least_0.005"
    ] is False
    assert metrics["verdict"]["supported"] is False


# --- Registration: fingerprint and preregister idempotency ---


def test_registered_h0018_fingerprint_recomputes() -> None:
    registry = HypothesisRegistry(STUDY_DIR / "hypotheses")
    registration = registry.get("H0018", version=1)
    fingerprint = hashlib.sha256(
        canonical_json(registration.spec.model_dump(mode="json"))
    ).hexdigest()
    assert fingerprint == registration.spec_fingerprint == H0018_V1_FINGERPRINT
    params = dict(
        item.split("=", maxsplit=1)
        for item in registration.spec.fixed_parameters
    )
    assert params["predictor_lag_steps"] == "1"
    assert params["control_lag_steps"] == "0"
    assert params["predictor_transform"] == "log-change"
    assert params["control_transform"] == "log-change"
    assert params["target_transform"] == "log-change"
    assert params["dvol_snapshot"] == (
        "16:00 UTC (close of the hourly DVOL row timestamped 15:00 UTC)"
    )
    assert params["sample_start"] == "2021-03-24"
    assert params["sample_end"] == "2026-11-20"
    assert registration.spec.expected_direction == "negative"
    assert registration.spec.planned_test_count == 1
    assert list(registration.spec.universe) == [BTC, BTC_DVOL, ETH]


def test_preregister_is_idempotent(tmp_path: Path) -> None:
    """Re-running preregister.py leaves an existing registration untouched.

    Regression guard for the scaffold's non-idempotent preregister
    (first real use found re-running would attempt a duplicate
    registration). Copies the study directory, resets it to the
    pre-registration state (no H0018 registration, empty event
    chain), then runs main() twice: the first run registers H0018
    v1, the second leaves the registration and the event chain
    byte-identical, and the fingerprint re-derives to the committed
    v1 value.
    """
    target = tmp_path / "btc-dvol-013"
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
    shutil.rmtree(target / "hypotheses" / "registrations" / "H0018")
    events_path = target / "hypotheses" / "hypothesis-events.jsonl"
    events_path.write_text("")
    module = _load_module(target / "preregister.py", "study_013_preregister")
    assert module.find_todos() == []
    module.main()
    registration_path = (
        target / "hypotheses" / "registrations" / "H0018" / "v1.json"
    )
    first_registration = registration_path.read_bytes()
    first_events = events_path.read_bytes()
    registration = json.loads(first_registration)
    assert registration["spec_fingerprint"] == H0018_V1_FINGERPRINT
    module.main()
    assert registration_path.read_bytes() == first_registration
    assert events_path.read_bytes() == first_events
