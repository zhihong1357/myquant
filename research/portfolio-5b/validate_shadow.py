"""Stage 5b shadow-evaluation validation: synthetic streams + real panel.

Run from the repo root:

    .venv/bin/python research/portfolio-5b/validate_shadow.py

Offline and deterministic (fixed seeds throughout). Scores four
synthetic prediction streams with known ground truth plus the 5a
lag-return fixture on the real 5a daily panel, runs the drift
monitors on the decaying and regime-break streams, and writes
``research/portfolio-5b/validation_report.md`` and the
deterministic scored-predictions ledger
``research/portfolio-5b/shadow_ledger.jsonl``. Re-running reproduces
both files byte-identically except the report's "Validated at" line.

The synthetic streams are framework checks, not strategies, and the
real-panel lag-fixture scores are framework validation, not strategy
performance: no performance claim, no alpha, no Sharpe is made or
implied anywhere in the output.

Stream designs (all on a daily grid from 2026-01-01T16:00Z, 1D
horizon; outcomes are log returns over [event_time, target_time]):

- oracle: predictions equal the realized values exactly (n = 200).
  Mechanical check: MSE must be 0 and skill vs zero must be 1.
- noise: predictions are small-amplitude independent noise
  (0.1 x N(0, 0.02), n = 500). Null check: skill near 0 and hit
  rate near 0.5. The amplitude is small on purpose: a same-scale
  independent predictor would score skill near -1 against the zero
  baseline (it adds pure variance without signal), so the null
  stream is deliberately weak. Both skills are reported.
- decay: predictions = beta_t * outcome + noise, with beta_t =
  0.4 * 0.5**(t / 100) (true half-life 100 predictions) and noise
  N(0, 0.2 * 0.02), n = 1000. The drift monitor must detect a
  negative trend and estimate a half-life within a factor of two
  of the truth. beta_0 is deliberately moderate: the rolling skill
  is approximately 2*beta_t minus a constant, so the skill curve is
  approximately a single exponential; a large beta_0 would make
  the skill curve a sum of two exponentials (2*beta - beta^2) and
  bias a single-exponential fit. The rolling skill for the decay
  analysis uses the zero baseline (a fixed reference; the lag
  baseline's own noise adds variance without signal) with a
  40-prediction window: a 20-prediction window leaves the rolling
  skill too noisy for the half-life to be identified, which is
  itself a finding about the framework's data requirements. The
  series is long (10 half-lives) so the decay is fully observed.
- break: outcomes N(0, 0.02) for the first 250 predictions, then
  N(0.03, 0.04) (a 1.5-sigma mean shift plus doubled volatility),
  n = 500; predictions are the lag fixture. PSI on 100-outcome
  windows must first flag on the window that contains the break.

The real-panel stream reuses the 5a daily panel (49 confirmed OKX
1D bars per instrument, 2026-09-30T16:00Z to 2026-11-18T16:00Z)
from the 5a cache; no data is fetched and no cache is modified.
The lag fixture emits 47 predictions per instrument per target
(log_return and abs_log_return); all are scored at 2026-11-19T16:00Z.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
sys.path.insert(0, str(REPO_ROOT / "research" / "portfolio-5a"))

from validate_portfolio import _load_panel  # noqa: E402

from myquant.portfolio.drift import (  # noqa: E402
    AlertConfig,
    check_alerts,
    estimate_decay,
    population_stability_index,
    rolling_skill,
    window_shift,
)
from myquant.portfolio.predictions import (  # noqa: E402
    Prediction,
    PredictionTarget,
    make_lag_return_fixture,
)
from myquant.portfolio.shadow import (  # noqa: E402
    ShadowEvaluation,
    score_predictions,
    shadow_ledger_json,
)

T0 = datetime(2026, 1, 1, 16, 0, tzinfo=UTC)
DAY = timedelta(days=1)
HOUR = timedelta(hours=1)
SIGMA = 0.02
SYNTH_INSTRUMENT = "synthetic:stream"
REAL_SCORED_AT = datetime(2026, 11, 19, 16, 0, tzinfo=UTC)

# Fixed seeds, one per random draw, documented in the report.
SEEDS = {
    "oracle_outcomes": 101,
    "noise_outcomes": 202,
    "noise_predictions": 203,
    "decay_outcomes": 303,
    "decay_noise": 304,
    "break_before": 404,
    "break_after": 405,
    "decay_bootstrap": 505,
    "shift_bootstrap": 606,
}

# Mechanical-check tolerances (documented in the report).
NOISE_SKILL_TOLERANCE = 0.15
NOISE_HIT_RATE_BAND = (0.45, 0.55)
NOISE_ACCURACY_BAND = (0.42, 0.58)
DECAY_HALF_LIFE_BAND = (50.0, 200.0)
ROLLING_WINDOW = 40


def _grid(n: int) -> list[datetime]:
    return [T0 + i * DAY for i in range(n)]


def _predictions(
    values: list[float],
    times: list[datetime],
    *,
    target: PredictionTarget,
    model_id: str,
    instrument_id: str = SYNTH_INSTRUMENT,
) -> list[Prediction]:
    return [
        Prediction(
            prediction_id=f"{model_id}-{i}",
            instrument_id=instrument_id,
            target=target,
            horizon=DAY,
            event_time=t,
            available_at=t,
            value=v,
            model_id=model_id,
            model_version="1",
            feature_version="synthetic-1",
        )
        for i, (t, v) in enumerate(zip(times, values, strict=True))
    ]


def _provider(returns: dict[datetime, float]):
    """Outcome provider from a return series keyed by event_time.

    LOG_RETURN returns the return; ABS_LOG_RETURN its absolute
    value; DIRECTION its sign. Other targets return None (no
    outcome defined for them here).
    """

    def provider(prediction: Prediction) -> float | None:
        value = returns.get(prediction.event_time)
        if value is None:
            return None
        if prediction.target is PredictionTarget.LOG_RETURN:
            return value
        if prediction.target is PredictionTarget.ABS_LOG_RETURN:
            return abs(value)
        if prediction.target is PredictionTarget.DIRECTION:
            return float(np.sign(value))
        return None

    return provider


def _lag_fixture(times: list[datetime], returns: list[float]) -> tuple[Prediction, ...]:
    """Lag-return fixture predictions for a synthetic return series.

    ``returns[i]`` is the return over [times[i], times[i] + 1d], so
    the bar closing at times[i] (i >= 1) has return returns[i - 1]:
    those are the (close_time, return) pairs the fixture consumes.
    """
    pairs = [(times[i], returns[i - 1]) for i in range(1, len(times))]
    return make_lag_return_fixture(
        pairs, instrument_id=SYNTH_INSTRUMENT, horizon=DAY
    )


def _check(condition: bool, message: str) -> str:
    """Record a mechanical check; raise if it fails so a re-run fails loudly."""
    if not condition:
        raise AssertionError(f"validation check failed: {message}")
    return f"PASS: {message}"


def _fmt(value: float, digits: int = 4) -> str:
    return f"{value:.{digits}f}"


def _metric_row(evaluation: ShadowEvaluation) -> list[str]:
    lines = []
    for metric in evaluation.metrics:
        lines.append(
            f"- {metric.target.value}: n={metric.n_scored}, "
            f"MSE={_fmt(metric.mse, 6)}, MAE={_fmt(metric.mae, 6)}, "
            f"bias={_fmt(metric.bias, 6)}"
        )
        if metric.correlation is not None:
            lines.append(f"  - correlation={_fmt(metric.correlation)}")
        if metric.hit_rate is not None:
            lines.append(f"  - hit_rate={_fmt(metric.hit_rate)}")
        if metric.accuracy is not None:
            lines.append(f"  - accuracy={_fmt(metric.accuracy)}")
        if metric.confusion is not None:
            c = metric.confusion
            lines.append(
                f"  - confusion: TP={c.true_positive} FP={c.false_positive} "
                f"TN={c.true_negative} FN={c.false_negative} "
                f"zeros_predicted={c.zeros_predicted} "
                f"zeros_outcome={c.zeros_outcome}"
            )
        skill = (
            _fmt(metric.skill_vs_zero)
            if metric.skill_vs_zero is not None
            else "undefined"
        )
        lines.append(
            f"  - zero baseline MSE={_fmt(metric.zero_baseline_mse, 6)}, "
            f"skill_vs_zero={skill}"
        )
        for baseline in metric.baselines:
            bskill = (
                _fmt(baseline.skill)
                if baseline.skill is not None
                else "undefined"
            )
            bmse = (
                _fmt(baseline.baseline_mse, 6)
                if baseline.baseline_mse is not None
                else "n/a"
            )
            lines.append(
                f"  - baseline '{baseline.name}': matched={baseline.matched_pairs}, "
                f"MSE={bmse}, skill={bskill}"
            )
    return lines


def _run_oracle() -> tuple[ShadowEvaluation, ShadowEvaluation, list[str]]:
    """Oracle stream: predictions equal outcomes (log_return + direction)."""
    rng = np.random.default_rng(SEEDS["oracle_outcomes"])
    n = 200
    times = _grid(n)
    returns = [float(v) for v in rng.normal(0.0, SIGMA, n)]
    by_time = dict(zip(times, returns, strict=True))
    scored_at = times[-1] + DAY + HOUR
    stream = _predictions(returns, times, target=PredictionTarget.LOG_RETURN, model_id="oracle")
    lag = _lag_fixture(times, returns)
    evaluation = score_predictions(
        stream, _provider(by_time), scored_at=scored_at, baselines={"lag": lag}
    )
    direction = _predictions(
        [float(np.sign(v)) for v in returns],
        times,
        target=PredictionTarget.DIRECTION,
        model_id="oracle-direction",
    )
    direction_eval = score_predictions(
        direction, _provider(by_time), scored_at=scored_at
    )
    metric = evaluation.metrics[0]
    dmetric = direction_eval.metrics[0]
    checks = [
        _check(metric.mse == 0.0, "oracle MSE is exactly 0"),
        _check(metric.skill_vs_zero == 1.0, "oracle skill vs zero is exactly 1"),
        _check(metric.hit_rate == 1.0, "oracle hit rate is exactly 1"),
        _check(metric.correlation == 1.0, "oracle correlation is exactly 1"),
        _check(dmetric.accuracy == 1.0, "oracle direction accuracy is exactly 1"),
        _check(evaluation.n_unscored == 0, "oracle stream has no unscored predictions"),
    ]
    return evaluation, direction_eval, checks


def _run_noise() -> tuple[ShadowEvaluation, ShadowEvaluation, list[str]]:
    """Noise stream: small-amplitude independent predictions (log_return + direction)."""
    rng_out = np.random.default_rng(SEEDS["noise_outcomes"])
    rng_pred = np.random.default_rng(SEEDS["noise_predictions"])
    n = 500
    times = _grid(n)
    returns = [float(v) for v in rng_out.normal(0.0, SIGMA, n)]
    predictions = [float(v) for v in rng_pred.normal(0.0, 0.1 * SIGMA, n)]
    by_time = dict(zip(times, returns, strict=True))
    scored_at = times[-1] + DAY + HOUR
    stream = _predictions(
        predictions, times, target=PredictionTarget.LOG_RETURN, model_id="noise"
    )
    lag = _lag_fixture(times, returns)
    evaluation = score_predictions(
        stream, _provider(by_time), scored_at=scored_at, baselines={"lag": lag}
    )
    direction = _predictions(
        [float(np.sign(v)) for v in rng_pred.normal(0.0, SIGMA, n)],
        times,
        target=PredictionTarget.DIRECTION,
        model_id="noise-direction",
    )
    direction_eval = score_predictions(
        direction, _provider(by_time), scored_at=scored_at
    )
    metric = evaluation.metrics[0]
    dmetric = direction_eval.metrics[0]
    checks = [
        _check(
            metric.skill_vs_zero is not None
            and abs(metric.skill_vs_zero) < NOISE_SKILL_TOLERANCE,
            f"noise skill vs zero within +/-{NOISE_SKILL_TOLERANCE} "
            f"(got {metric.skill_vs_zero:.4f})",
        ),
        _check(
            metric.hit_rate is not None
            and NOISE_HIT_RATE_BAND[0] <= metric.hit_rate <= NOISE_HIT_RATE_BAND[1],
            f"noise hit rate within {NOISE_HIT_RATE_BAND} (got {metric.hit_rate:.4f})",
        ),
        _check(
            dmetric.accuracy is not None
            and NOISE_ACCURACY_BAND[0] <= dmetric.accuracy <= NOISE_ACCURACY_BAND[1],
            f"noise direction accuracy within {NOISE_ACCURACY_BAND} "
            f"(got {dmetric.accuracy:.4f})",
        ),
    ]
    return evaluation, direction_eval, checks


def _run_decay() -> tuple[ShadowEvaluation, dict, list[str]]:
    """Decaying-signal stream: beta decays exponentially (true half-life 100)."""
    rng_out = np.random.default_rng(SEEDS["decay_outcomes"])
    rng_noise = np.random.default_rng(SEEDS["decay_noise"])
    n = 1000
    true_half_life = 100.0
    beta0 = 0.4
    times = _grid(n)
    returns = [float(v) for v in rng_out.normal(0.0, SIGMA, n)]
    noise = [float(v) for v in rng_noise.normal(0.0, 0.2 * SIGMA, n)]
    betas = [beta0 * 0.5 ** (t / true_half_life) for t in range(n)]
    predictions = [b * r + e for b, r, e in zip(betas, returns, noise, strict=True)]
    by_time = dict(zip(times, returns, strict=True))
    scored_at = times[-1] + DAY + HOUR
    stream = _predictions(
        predictions, times, target=PredictionTarget.LOG_RETURN, model_id="decay"
    )
    lag = _lag_fixture(times, returns)
    evaluation = score_predictions(
        stream, _provider(by_time), scored_at=scored_at, baselines={"lag": lag}
    )
    # Rolling skill for the drift analysis comes from the scored
    # ledger itself (stream errors vs the zero baseline's errors),
    # against the fixed zero reference.
    scored = [r for r in evaluation.predictions if r.scored]
    stream_errors = [r.error for r in scored if r.error is not None]
    zero_errors = [-r.outcome for r in scored if r.outcome is not None]
    scored_times = [r.event_time for r in scored]
    skill_series = rolling_skill(stream_errors, zero_errors, window=ROLLING_WINDOW)
    defined = [(t, s) for t, s in zip(scored_times, skill_series, strict=True) if s is not None]
    defined_times = [t for t, _ in defined]
    defined_skill = [s for _, s in defined]
    decay = estimate_decay(
        defined_skill,
        max_lag=ROLLING_WINDOW - 1,
        seed=SEEDS["decay_bootstrap"],
        resamples=500,
        bootstrap_block_length=ROLLING_WINDOW,
    )
    flags = check_alerts(
        [(t, s) for t, s in zip(scored_times, skill_series, strict=True)],
        [],
        config=AlertConfig(),
    )
    skill_flags = [f for f in flags if f.flag_type == "skill_below_zero"]
    checks = [
        _check(decay.detected, "decay detected (significant negative trend, good fit)"),
        _check(
            decay.half_life is not None
            and DECAY_HALF_LIFE_BAND[0] <= decay.half_life <= DECAY_HALF_LIFE_BAND[1],
            f"estimated half-life within {DECAY_HALF_LIFE_BAND} of truth 100 "
            f"(got {decay.half_life:.1f})",
        ),
        _check(len(skill_flags) >= 1, "at least one skill_below_zero flag fires"),
    ]
    detail = {
        "n": n,
        "true_half_life": true_half_life,
        "beta0": beta0,
        "noise_scale": 0.2,
        "decay": decay,
        "n_rolling": len(defined_skill),
        "first_skill": defined_skill[0],
        "last_skill": defined_skill[-1],
        "skill_flags": skill_flags,
        "first_flag_time": skill_flags[0].triggered_at if skill_flags else None,
        "first_flag_index": (
            defined_times.index(skill_flags[0].triggered_at) if skill_flags else None
        ),
    }
    return evaluation, detail, checks


def _run_break() -> tuple[ShadowEvaluation, dict, list[str]]:
    """Regime-break stream: outcomes jump at index 250; PSI must flag it."""
    rng_before = np.random.default_rng(SEEDS["break_before"])
    rng_after = np.random.default_rng(SEEDS["break_after"])
    n = 500
    break_index = 250
    times = _grid(n)
    returns = [float(v) for v in rng_before.normal(0.0, SIGMA, break_index)]
    returns += [float(v) for v in rng_after.normal(0.03, 2 * SIGMA, n - break_index)]
    by_time = dict(zip(times, returns, strict=True))
    scored_at = times[-1] + DAY + HOUR
    stream = make_lag_return_fixture(
        [(times[i], returns[i - 1]) for i in range(1, n)],
        instrument_id=SYNTH_INSTRUMENT,
        horizon=DAY,
    )
    evaluation = score_predictions(stream, _provider(by_time), scored_at=scored_at)
    reference = returns[:100]
    window_size = 100
    psi_windows: list[tuple[datetime, float]] = []
    for start in range(0, n, window_size):
        window = returns[start : start + window_size]
        psi = population_stability_index(reference, window, bins=10).psi
        psi_windows.append((times[min(start + window_size - 1, n - 1)], psi))
    flags = check_alerts(
        [],
        [(t, p) for t, p in psi_windows],
        config=AlertConfig(),
    )
    psi_flags = [f for f in flags if f.flag_type == "psi_high"]
    break_time = times[break_index]
    # The first window containing post-break data ends at times[299]
    # (window [200:300]); the flag must fire there, not before.
    expected_first_flag_time = times[299]
    checks = [
        _check(len(psi_flags) >= 1, "at least one PSI flag fires after the break"),
        _check(
            psi_flags[0].triggered_at == expected_first_flag_time,
            f"first PSI flag at the first window containing post-break data "
            f"({expected_first_flag_time.isoformat()}); "
            f"break at index {break_index} ({break_time.isoformat()})",
        ),
    ]
    shift = window_shift(
        reference,
        returns[250:350],
        max_lag=5,
        block_length=5,
        resamples=2000,
        seed=SEEDS["shift_bootstrap"],
    )
    checks.append(
        _check(
            shift.mean_difference > 0.02 and (shift.mean_difference_p_value or 1.0) < 0.01,
            f"window shift detects the mean jump "
            f"(diff {shift.mean_difference:.4f}, p {shift.mean_difference_p_value:.4g})",
        )
    )
    checks.append(
        _check(
            shift.volatility_ratio is not None
            and 1.5 < shift.volatility_ratio < 2.5,
            f"volatility ratio near 2 (got {shift.volatility_ratio:.3f})",
        )
    )
    detail = {
        "break_index": break_index,
        "break_time": break_time,
        "psi_windows": psi_windows,
        "psi_flags": psi_flags,
        "shift": shift,
    }
    return evaluation, detail, checks


def _run_real() -> tuple[dict[str, ShadowEvaluation], list[str]]:
    """Real panel: the 5a lag fixture scored forward (framework check only)."""
    panels, _, _ = _load_panel()
    evaluations: dict[str, ShadowEvaluation] = {}
    checks: list[str] = []
    for inst_id in sorted(panels):
        candles = panels[inst_id]
        closes = [c.close for c in candles]
        close_times = [c.close_time for c in candles]
        returns = [
            (close_times[i], math.log(closes[i] / closes[i - 1]))
            for i in range(1, len(closes))
        ]
        by_time = {t: r for t, r in returns}
        for target in (PredictionTarget.LOG_RETURN, PredictionTarget.ABS_LOG_RETURN):
            fixture = make_lag_return_fixture(
                returns, instrument_id=inst_id, horizon=DAY, target=target
            )

            def provider(prediction: Prediction, _by_time=by_time) -> float | None:
                value = _by_time.get(prediction.event_time + DAY)
                if value is None:
                    return None
                if prediction.target is PredictionTarget.ABS_LOG_RETURN:
                    return abs(value)
                return value

            evaluation = score_predictions(
                fixture, provider, scored_at=REAL_SCORED_AT
            )
            evaluations[f"{inst_id}:{target.value}"] = evaluation
            checks.append(
                _check(
                    evaluation.n_scored == 47 and evaluation.n_unscored == 0,
                    f"{inst_id} {target.value}: all 47 fixture predictions scored",
                )
            )
    return evaluations, checks


def main() -> None:
    ran_at = datetime.now(UTC)
    oracle_eval, oracle_dir_eval, oracle_checks = _run_oracle()
    noise_eval, noise_dir_eval, noise_checks = _run_noise()
    decay_eval, decay_detail, decay_checks = _run_decay()
    break_eval, break_detail, break_checks = _run_break()
    real_evals, real_checks = _run_real()

    ledgers: list[tuple[str, ShadowEvaluation]] = [
        ("oracle", oracle_eval),
        ("oracle-direction", oracle_dir_eval),
        ("noise", noise_eval),
        ("noise-direction", noise_dir_eval),
        ("decay", decay_eval),
        ("break", break_eval),
    ]
    ledgers += [(f"real-{name}", ev) for name, ev in sorted(real_evals.items())]
    ledger_lines: list[str] = []
    for stream_name, evaluation in ledgers:
        for line in shadow_ledger_json(evaluation).splitlines():
            ledger_lines.append(
                json.dumps(
                    {"stream": stream_name, "record": json.loads(line)},
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
    ledger_path = ROOT / "shadow_ledger.jsonl"
    ledger_path.write_text("\n".join(ledger_lines) + "\n", encoding="utf-8")

    lines: list[str] = [
        "# Stage 5b shadow-evaluation validation report",
        "",
        f"- Validated at: {ran_at.isoformat()}",
        "- Offline and deterministic: fixed seeds, no network, no clock reads "
        "inside the scoring (scored_at is an input). Re-running reproduces "
        "this report except this timestamp line, and the ledger byte-identically.",
        "- Synthetic grid: daily from 2026-01-01T16:00Z, 1D horizon, "
        "outcomes are log returns over [event_time, target_time].",
        f"- Seeds: {json.dumps(SEEDS, sort_keys=True)}.",
        "",
        "## Oracle stream (perfect foresight)",
        "",
        "- Design: predictions equal realized values exactly, n = 200, "
        "outcomes N(0, 0.02). A mechanical check on the scoring machinery.",
        "- Log-return metrics:",
    ]
    lines += _metric_row(oracle_eval)
    lines += ["- Direction metrics:"]
    lines += _metric_row(oracle_dir_eval)
    lines += ["- Checks:"] + [f"  - {c}" for c in oracle_checks]
    lines += [
        "",
        "## Noise stream (no signal)",
        "",
        "- Design: predictions are small-amplitude independent noise "
        "(0.1 x N(0, 0.02)), n = 500. A same-scale independent predictor "
        "would score skill near -1 against the zero baseline (pure added "
        "variance), so the null stream is deliberately weak; the check is "
        "that a signal-free stream scores near zero skill and near-chance "
        "hit rate.",
        "- Log-return metrics:",
    ]
    lines += _metric_row(noise_eval)
    lines += ["- Direction metrics:"]
    lines += _metric_row(noise_dir_eval)
    noise_lag_skill = noise_eval.metrics[0].baselines[0].skill
    lines += [
        f"- Note: skill vs the lag baseline is {noise_lag_skill:.4f} here — "
        "the lag fixture is a weak baseline on iid returns (MSE near 2*sigma^2), "
        "so beating it says little; the zero baseline is the meaningful "
        "reference for a no-signal stream.",
        "- Checks:",
    ]
    lines += [f"  - {c}" for c in noise_checks]
    decay = decay_detail["decay"]
    lines += [
        "",
        "## Decaying-signal stream",
        "",
        f"- Design: prediction = beta_t * outcome + noise, beta_t = "
        f"{decay_detail['beta0']} * 0.5**(t / {decay_detail['true_half_life']:.0f}), "
        f"noise N(0, {decay_detail['noise_scale']} * 0.02), "
        f"n = {decay_detail['n']}. True half-life: "
        f"{decay_detail['true_half_life']:.0f} predictions. Rolling skill "
        f"uses the zero baseline with a {ROLLING_WINDOW}-prediction window.",
        "- Log-return metrics:",
    ]
    lines += _metric_row(decay_eval)
    ci = (
        f"[{decay.half_life_ci_low:.1f}, {decay.half_life_ci_high:.1f}]"
        if decay.half_life_ci_low is not None and decay.half_life_ci_high is not None
        else "n/a"
    )
    first_flag_time = decay_detail["first_flag_time"]
    first_flag_str = first_flag_time.isoformat() if first_flag_time else "n/a"
    lines += [
        f"- Rolling skill (window {ROLLING_WINDOW}, {decay_detail['n_rolling']} "
        f"defined windows): first {decay_detail['first_skill']:.3f}, "
        f"last {decay_detail['last_skill']:.3f}.",
        f"- Trend: slope {decay.slope:.6f} per prediction, HAC p-value "
        f"{decay.slope_p_value:.4g} (max_lag {ROLLING_WINDOW - 1}).",
        f"- Decay estimate: detected={decay.detected}, half-life "
        f"{decay.half_life:.1f} predictions (truth 100), 95% interval {ci}, "
        f"fit R-squared {decay.fit_r_squared:.3f}, stable={decay.stable}.",
        f"- Skill flags: {len(decay_detail['skill_flags'])} "
        f"(first at {first_flag_str}, "
        f"rolling-window index {decay_detail['first_flag_index']}).",
        "- Checks:",
    ]
    lines += [f"  - {c}" for c in decay_checks]
    shift = break_detail["shift"]
    lines += [
        "",
        "## Regime-break stream",
        "",
        f"- Design: outcomes N(0, 0.02) for indices 0-249, then N(0.03, 0.04) "
        f"from index 250 (break at {break_detail['break_time'].isoformat()}); "
        f"n = 500; predictions are the lag fixture.",
        "- Log-return metrics:",
    ]
    lines += _metric_row(break_eval)
    lines += [
        "- PSI (reference = outcomes 0-99, 100-outcome windows, 10 bins):",
    ]
    for when, psi in break_detail["psi_windows"]:
        lines.append(f"  - window ending {when.isoformat()}: PSI {psi:.3f}")
    first_psi_flag = break_detail["psi_flags"][0] if break_detail["psi_flags"] else None
    first_psi_str = (
        first_psi_flag.triggered_at.isoformat()
        if first_psi_flag and first_psi_flag.triggered_at
        else "n/a"
    )
    first_psi_value = first_psi_flag.value if first_psi_flag else float("nan")
    lines += [
        f"- PSI flags: {len(break_detail['psi_flags'])} "
        f"(first at {first_psi_str}, value {first_psi_value:.3f}); "
        f"the break sits inside "
        f"the window ending {break_detail['psi_windows'][2][0].isoformat()}.",
        f"- Note: the last fully pre-break window reads PSI "
        f"{break_detail['psi_windows'][1][1]:.3f}, close to the 0.25 alarm — "
        "sampling noise at this window size (100 outcomes, 10 bins), not a "
        "missed break. The threshold's noise floor is part of why a flag is "
        "a prompt, not a conclusion.",
        f"- Window shift (reference 0-99 vs current 250-349): mean difference "
        f"{shift.mean_difference:.4f} (HAC SE {shift.mean_difference_se:.4f}, "
        f"p {shift.mean_difference_p_value:.4g}), volatility ratio "
        f"{shift.volatility_ratio:.3f} "
        f"(95% interval [{shift.volatility_ratio_ci_low:.3f}, "
        f"{shift.volatility_ratio_ci_high:.3f}]).",
        "- Checks:",
    ]
    lines += [f"  - {c}" for c in break_checks]
    lines += [
        "",
        "## Real panel: lag-return fixture (framework check, not a strategy)",
        "",
        "- Panel: 5a daily panel, 49 confirmed OKX 1D bars per instrument "
        "(2026-09-30T16:00Z to 2026-11-18T16:00Z); 47 fixture predictions per "
        "instrument per target, scored at 2026-11-19T16:00Z. The fixture is "
        "naive by construction (next return = last return).",
    ]
    for name in sorted(real_evals):
        lines.append(f"- {name}:")
        lines += [f"  {row}" for row in _metric_row(real_evals[name])]
    abs_skills = [
        ev.metrics[0].skill_vs_zero
        for name, ev in real_evals.items()
        if name.endswith(":abs_log_return") and ev.metrics[0].skill_vs_zero is not None
    ]
    log_skills = [
        ev.metrics[0].skill_vs_zero
        for name, ev in real_evals.items()
        if name.endswith(":log_return") and ev.metrics[0].skill_vs_zero is not None
    ]
    lines += [
        f"- Summary: log_return skill vs zero ranges "
        f"{min(log_skills):.2f} to {max(log_skills):.2f} across instruments "
        f"(poor, as expected for near-unpredictable daily returns); "
        f"abs_log_return skill vs zero ranges {min(abs_skills):.2f} to "
        f"{max(abs_skills):.2f} (positive, reflecting volatility clustering "
        f"in |returns|, not any trading edge). With 47 predictions over "
        f"seven weeks, nothing is claimed from either.",
    ]
    lines += ["- Checks:"] + [f"  - {c}" for c in real_checks]
    lines += [
        "",
        "## Ledger",
        "",
        f"- `shadow_ledger.jsonl`: {len(ledger_lines)} scored-prediction records "
        "across all streams (one JSON object per line, with a stream label), "
        "deterministic: re-running reproduces the file byte-identically.",
        "",
        "## Limitations",
        "",
        "- The synthetic streams use Gaussian returns and a daily grid; they "
        "validate the machinery, not any market behaviour.",
        "- The decay half-life is a fragile estimate: it is reported with its "
        "bootstrap interval, fit R-squared and stability flag, and the "
        "rolling window smooths the decay (the estimate is a property of "
        "the rolling series, not of the underlying signal directly).",
        "- PSI thresholds (0.1 / 0.25) are conventional detection cutoffs, "
        "not significance levels; a flag is a prompt to look, not a "
        "conclusion that the distribution changed.",
        "- The real-panel check covers 47 predictions per instrument over "
        "seven weeks: far too few to say anything about the fixture, and "
        "nothing is claimed from it.",
        "- No KS test is implemented: PSI plus the window shift cover "
        "distribution drift, and a second overlapping detector was not added.",
        "",
    ]
    report_path = ROOT / "validation_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"validation report written: {report_path}")
    print(f"ledger written: {ledger_path} ({len(ledger_lines)} records)")
    for check in (
        oracle_checks + noise_checks + decay_checks + break_checks + real_checks
    ):
        print(f"  {check}")


if __name__ == "__main__":
    main()
