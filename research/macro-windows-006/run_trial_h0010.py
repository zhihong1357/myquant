"""Run trial T0012 for hypothesis H0010 (macro-window volatility level).

Run after preregistration and fetching, from the repo root, with a clean
worktree (the trial records the HEAD commit as its code revision):

    .venv/bin/python research/macro-windows-006/run_trial_h0010.py

The trial binds the preregistered H0010 v1 spec, this study's fetch
manifest SHA-256 as the data fingerprint, and a canonical-JSON hash of
the analysis configuration. It executes the preregistered two-test
family, mirroring study 004's H0006 with the macro window in place of
the expiry window:

- (a) BTC: mean daily |log return| on macro-window days vs
  non-window days.
- (b) ETH: the same comparison.

Inference: OLS of |log return| on the window indicator with Newey-West
HAC standard errors (max lag 10; absolute returns are more persistent
than returns). The block-bootstrap interval (block 10, 2000 resamples,
seed 42) for the window-minus-non-window mean difference is computed on
the weighted series whose mean is the difference of means. Effect size:
the ratio of window to non-window mean |log return|, threshold 1.15.

There is no walk-forward evaluation and no cost gate: H0010 is a
volatility-level comparison, not a forecast. The mean comparison uses
all daily rows in the sample period (train + validation + holdout); the
windows define the sample period, not a train/test split for this
hypothesis. Descriptive splits (wide window, FOMC-only vs CPI-only,
auction days, subperiods) carry group means and ratios only, no
p-values. The auction split runs only when the committed auction
calendar is verified; otherwise it is recorded as omitted.

The macro window is the union of FOMC statement days and CPI release
days, one OKX daily bar per event: the CPI window bar opened the day
before the release date (08:30 ET is always before the 16:00 UTC bar
open); the FOMC window bar opened on the statement day itself (14:00
ET is always after it). Both offsets are DST-independent. The runner
records the trial (including failures) in the hash-chained ledger
trials.jsonl; it does not decide acceptance.
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
from myquant.studies.macro import (
    MacroWindow,
    auction_window_bar,
    build_macro_window,
    load_cpi_calendar,
    load_fomc_statement_dates,
    load_verified_auction_dates,
    macro_window_indicator,
    wide_window_dates,
)
from myquant.studies.panel import SynchronizedPanel, build_synchronized_panel

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "macro-windows-006"
STUDY_005_ROOT = REPO_ROOT / "research" / "fomc-event-study-005"

HYPOTHESIS_ID = "H0010"
HYPOTHESIS_VERSION = 1
TRIAL_ID = "T0012"

BTC = "crypto:btc-usdt-perp"
ETH = "crypto:eth-usdt-perp"
SOL = "crypto:sol-usdt-perp"
INSTRUMENTS = (BTC, ETH, SOL)

# Preregistered subperiod split (2021-2023 vs 2024-2026).
SUBPERIOD_CUT = datetime(2024, 1, 1, tzinfo=UTC)


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


def load_macro_calendars() -> tuple[MacroWindow, dict[str, Any]]:
    """Load the committed CPI/FOMC calendars and the auction calendar.

    Returns the macro window plus an auction record: the verified
    auction dates (or None) and a status string explaining whether the
    auction descriptive split can run. The CPI/FOMC calendars are
    preregistered inputs — a load failure here is a hard stop.
    """
    cpi_document = json.loads(
        (ROOT / "cpi_calendar.json").read_text(encoding="utf-8")
    )
    fomc_document = json.loads(
        (STUDY_005_ROOT / "fomc_calendar.json").read_text(encoding="utf-8")
    )
    releases = load_cpi_calendar(cpi_document)
    fomc_dates = load_fomc_statement_dates(fomc_document)
    fomc_sample = tuple(day for day in fomc_dates if 2021 <= day.year <= 2026)
    window = build_macro_window(
        [item.release_date for item in releases], fomc_sample
    )

    auction_path = ROOT / "treasury_auction_calendar.json"
    if not auction_path.exists():
        auction: dict[str, Any] = {
            "dates": None,
            "status": "missing: auction calendar file not present",
        }
        return window, auction
    auction_document = json.loads(auction_path.read_text(encoding="utf-8"))
    verified_dates = load_verified_auction_dates(auction_document)
    if verified_dates is None:
        auction = {
            "dates": None,
            "status": (
                "unverified: the auction calendar's cross-check did not "
                "pass, so the auction descriptive split is omitted"
            ),
        }
        return window, auction
    auction = {
        "dates": tuple(auction_window_bar(day) for day in verified_dates),
        "status": "verified",
    }
    return window, auction


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
        "trial_script": "research/macro-windows-006/run_trial_h0010.py",
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
            "Macro-window realized-volatility level: BTC/ETH mean "
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
    # (This is the guard that caught the T0006 weights bug in study 004.)
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
    window: MacroWindow,
    auction_bars: tuple | None,
    wide_days_before: int,
    wide_days_after: int,
) -> dict[str, Any]:
    """Descriptive splits: wide window, FOMC/CPI, auction, subperiods.

    Group means and ratios only; no p-values anywhere here: these splits
    are descriptive, not in the test family. The auction split runs only
    when the auction calendar is verified; otherwise it is recorded as
    omitted with the reason.
    """
    wide_flags = macro_window_indicator(
        daily_returns.index,
        wide_window_dates(
            window.window_bars,
            days_before=wide_days_before,
            days_after=wide_days_after,
        ),
    ).to_numpy(dtype=bool)
    fomc_flags = macro_window_indicator(
        daily_returns.index, window.fomc_bars
    ).to_numpy(dtype=bool)
    cpi_flags = macro_window_indicator(
        daily_returns.index, window.cpi_bars
    ).to_numpy(dtype=bool)
    full_flags = macro_window_indicator(
        daily_returns.index, window.window_bars
    ).to_numpy(dtype=bool)
    auction_flags = None
    if auction_bars is not None:
        auction_flags = macro_window_indicator(
            daily_returns.index, set(auction_bars)
        ).to_numpy(dtype=bool)
    early_mask = daily_returns.index < SUBPERIOD_CUT
    splits: dict[str, Any] = {}
    for label, instrument in (("btc", BTC), ("eth", ETH)):
        abs_values = np.abs(daily_returns[instrument].to_numpy(dtype=float))
        splits[f"{label}_wide_window"] = _descriptive_ratio(
            abs_values, wide_flags
        )
        splits[f"{label}_fomc_only_window"] = _descriptive_ratio(
            abs_values, fomc_flags
        )
        splits[f"{label}_cpi_only_window"] = _descriptive_ratio(
            abs_values, cpi_flags
        )
        if auction_flags is None:
            splits[f"{label}_auction_window"] = {
                "omitted": True,
                "reason": "auction calendar not verified (see trial auction record)",
            }
        else:
            splits[f"{label}_auction_window"] = _descriptive_ratio(
                abs_values, auction_flags
            )
        splits[f"{label}_subperiod_2021_2023"] = _descriptive_ratio(
            abs_values[early_mask], full_flags[early_mask]
        )
        splits[f"{label}_subperiod_2024_2026"] = _descriptive_ratio(
            abs_values[~early_mask], full_flags[~early_mask]
        )
    return splits


def build_experiment(
    daily: SynchronizedPanel,
    spec: HypothesisSpec,
    window: MacroWindow,
    auction: dict[str, Any],
) -> Any:
    """Build the trial callback closing over the loaded panel."""

    def experiment(trial_spec: TrialSpec) -> dict[str, Any]:
        params = {item.name: item.value for item in trial_spec.parameters}
        wide_days_before = int(params["wide_window_days_before"])
        wide_days_after = int(params["wide_window_days_after"])
        effect_ratio_threshold = float(params["effect_ratio_threshold"])
        hac_max_lag = int(params["abs_return_hac_max_lag"])
        bootstrap_block_length = int(params["bootstrap_block_length"])
        bootstrap_resamples = int(params["bootstrap_resamples"])
        bootstrap_seed = int(params["bootstrap_seed"])

        daily_returns = daily.returns
        flags = macro_window_indicator(
            daily_returns.index, window.window_bars
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
            window=window,
            auction_bars=auction["dates"],
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
                "cpi_window_bars": len(window.cpi_bars),
                "fomc_window_bars": len(window.fomc_bars),
                "window_bars_total": len(window.window_bars),
                "overlap_bars": sorted(
                    item.isoformat() for item in window.overlap_bars
                ),
                "first_window_bar": min(window.window_bars).isoformat(),
                "last_window_bar": max(window.window_bars).isoformat(),
                "daily_rows": int(daily_returns.shape[0]),
                "daily_window_rows": int(flags.sum()),
                "daily_nonwindow_rows": int((~flags).sum()),
            },
            "auction": {
                "status": auction["status"],
                "auction_dates": (
                    len(auction["dates"]) if auction["dates"] is not None else 0
                ),
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
    window, auction = load_macro_calendars()
    print(
        f"macro window: {len(window.window_bars)} bars "
        f"({len(window.cpi_bars)} CPI + {len(window.fomc_bars)} FOMC, "
        f"{len(window.overlap_bars)} overlap)"
    )
    print(f"auction calendar: {auction['status']}")
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
        build_experiment(daily, spec, window, auction),
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
