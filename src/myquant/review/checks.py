"""Adversarial review checks (Stage 6d).

Each check is a pure function over records already loaded from disk: it
returns a verdict plus located evidence and never writes anything. A
check that cannot be performed returns UNVERIFIED with the reason — it
never reports PASS on the absence of a problem.

Conventions the checks rely on (each stated where it is used):
- The primary test of a trial is the first entry of its recorded Holm
  family (``metrics["holm"][0]``). This holds for all 12 completed
  trials in the lab; the verdict check verifies the family exists and
  the report check independently confirms the primary test's identity
  from the report tables.
- Trial IDs form a contiguous sequence from T0001, except T0003, which
  is reserved for the preregistered H0003 forward test (study 002) and
  has not run yet.
- The known failed trials are T0006, T0008 and T0014; each must be
  present in its study's ledger with status "failed".
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from myquant.canonical import canonical_json
from myquant.contracts import MultiplicityCorrection, Observation
from myquant.experiments import ExperimentRunner, TrialSpec
from myquant.hypotheses import (
    HypothesisRegistry,
    HypothesisSpec,
    HypothesisState,
)
from myquant.registry import GENESIS_HASH, read_and_verify
from myquant.review.models import CheckResult, ReviewVerdict
from myquant.review.tables import (
    BOOT_CI_FIELD,
    HOLM_FIELD,
    WINDOW_N_FIELD,
    ReportRule,
    find_table,
    parse_boot_ci,
    parse_markdown_tables,
    parse_report_number,
    parse_window_n,
)
from myquant.stats import adjust_pvalues

# Trial IDs the lab reserves or has recorded as failed. Sources: the H0003
# forward test is preregistered in study 002 (trial T0003, not yet run);
# T0006/T0008/T0014 are the failed attempts recorded in studies 004/005/007.
RESERVED_TRIAL_IDS: frozenset[str] = frozenset({"T0003"})
KNOWN_FAILED_TRIAL_IDS: frozenset[str] = frozenset({"T0006", "T0008", "T0014"})

# Recomputation tolerances. Adjusted p-values are recomputed with the
# repo's own adjustment function, so agreement should be at float-noise
# level; 1e-9 leaves ample room for it and no room for a changed digit.
ADJUSTED_P_TOLERANCE = 1e-9
RAW_P_TOLERANCE = 1e-12


def _pass(check_id: str, subject: str, summary: str, *evidence: str) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        subject=subject,
        verdict=ReviewVerdict.PASS,
        summary=summary,
        evidence=evidence,
    )


def _fail(check_id: str, subject: str, summary: str, *evidence: str) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        subject=subject,
        verdict=ReviewVerdict.FAIL,
        summary=summary,
        evidence=evidence,
    )


def _unverified(
    check_id: str, subject: str, summary: str, *evidence: str
) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        subject=subject,
        verdict=ReviewVerdict.UNVERIFIED,
        summary=summary,
        evidence=evidence,
    )


def _note(check_id: str, subject: str, summary: str, *evidence: str) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        subject=subject,
        verdict=ReviewVerdict.NOTE,
        summary=summary,
        evidence=evidence,
    )


def check_ledger_chain(ledger_path: Path, label: str) -> CheckResult:
    """Verify a study ledger's hash chain (tamper detection).

    Reuses the repo's own read_and_verify; it does not reimplement the
    hash logic. A missing ledger file is a FAIL: every study with trials
    must have one.
    """
    if not ledger_path.exists():
        return _fail(
            "ledger_chain",
            label,
            "ledger file absent",
            f"{label}: expected a trials ledger, none exists",
        )
    try:
        records = read_and_verify(ledger_path)
    except (ValueError, KeyError, TypeError) as exc:
        return _fail(
            "ledger_chain",
            label,
            f"hash chain verification failed: {exc}",
            f"{label}: {exc}",
        )
    latest = records[-1]["record_hash"][:12] if records else GENESIS_HASH[:12]
    return _pass(
        "ledger_chain",
        label,
        f"hash chain intact ({len(records)} record(s))",
        f"{label}: {len(records)} record(s), latest record hash {latest}...",
    )


def check_ledger_anchor(ledger_path: Path, label: str) -> CheckResult:
    """Verify a study ledger against its anchor file (truncation detection).

    The hash chain cannot detect deleted trailing records; only the
    anchor can. A study without an anchor file is UNVERIFIED here — the
    chain may be intact, but truncation cannot be ruled out.
    """
    anchor_path = Path(str(ledger_path) + ".anchor")
    if not anchor_path.exists():
        return _unverified(
            "ledger_anchor",
            label,
            "no anchor file; truncation undetectable",
            f"{label}: {anchor_path.name} absent, the chain verifies "
            "tampering only",
        )
    try:
        records = read_and_verify(ledger_path, anchor_path=anchor_path)
    except (ValueError, FileNotFoundError) as exc:
        return _fail(
            "ledger_anchor",
            label,
            f"ledger does not match its anchor: {exc}",
            f"{label}: {exc}",
        )
    return _pass(
        "ledger_anchor",
        label,
        f"ledger matches its anchor ({len(records)} record(s))",
        f"{label}: anchor record count and latest hash agree",
    )


def check_registry_events(registry_root: Path, label: str) -> CheckResult:
    """Verify a study registry's lifecycle-event chain and transitions.

    Replays the event log through the repo's own read_events, which
    verifies the hash chain, the legality of every state transition and
    the integrity of every referenced registration.
    """
    if not registry_root.exists():
        return _unverified(
            "registry_events",
            label,
            "registry directory absent",
            f"{label}: no hypotheses registry to verify",
        )
    registry = HypothesisRegistry(registry_root)
    try:
        events = registry.read_events()
    except (ValueError, FileNotFoundError) as exc:
        return _fail(
            "registry_events",
            label,
            f"event log verification failed: {exc}",
            f"{label}: {exc}",
        )
    return _pass(
        "registry_events",
        label,
        f"event chain intact ({len(events)} event(s))",
        f"{label}: {len(events)} lifecycle event(s), all transitions legal",
    )


def _recompute_spec_fingerprint(spec: dict[str, Any]) -> str:
    """Recompute a trial record's spec fingerprint from its stored spec."""
    payload = {key: value for key, value in spec.items() if key != "trial_id"}
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def check_prereg_binding(
    record: dict[str, Any],
    registry: HypothesisRegistry | None,
    label: str,
) -> CheckResult:
    """Verify a trial is bound to its preregistration.

    Four bindings, all re-derived from the stored records: the
    registration exists and verifies (hash + spec fingerprint); the
    trial's hypothesis fingerprint equals the registered spec
    fingerprint; the trial's research plan matches the registered spec
    field for field (via the runner's own matcher, so the reviewer
    applies exactly the definition of "matches" the runner enforces);
    and the record's spec fingerprint matches the stored spec.
    Applies to completed and failed trials alike — a failed trial still
    carries a bound spec.
    """
    trial_id = str(record.get("trial_id", label))
    result = record.get("result") or {}
    spec_dict = result.get("spec") or {}
    hypothesis_id = str(spec_dict.get("hypothesis_id", record.get("hypothesis_id", "?")))
    version = spec_dict.get("hypothesis_version")
    if registry is None or not isinstance(version, int):
        return _unverified(
            "prereg_binding",
            trial_id,
            "cannot bind trial: registry or version unavailable",
            f"{trial_id}: registry={'absent' if registry is None else 'present'}, "
            f"hypothesis_version={version!r}",
        )
    try:
        registration = registry.get(hypothesis_id, version=version)
    except (ValueError, FileNotFoundError) as exc:
        return _fail(
            "prereg_binding",
            trial_id,
            f"registration does not verify: {exc}",
            f"{trial_id}: {hypothesis_id} v{version}: {exc}",
        )
    stored_fingerprint = str(spec_dict.get("hypothesis_fingerprint", ""))
    if stored_fingerprint != registration.spec_fingerprint:
        return _fail(
            "prereg_binding",
            trial_id,
            "trial hypothesis fingerprint does not match preregistration",
            f"{trial_id}: trial fingerprint {stored_fingerprint[:12]}..., "
            f"registered {registration.spec_fingerprint[:12]}...",
        )
    try:
        trial_spec = TrialSpec.model_validate(spec_dict)
    except ValueError as exc:
        return _fail(
            "prereg_binding",
            trial_id,
            f"stored trial spec does not validate: {exc}",
            f"{trial_id}: {exc}",
        )
    try:
        ExperimentRunner._assert_trial_matches_registration(
            trial_spec, registration.spec
        )
    except PermissionError as exc:
        return _fail(
            "prereg_binding",
            trial_id,
            "trial research plan differs from preregistration",
            f"{trial_id}: {exc}",
        )
    recorded = str(result.get("spec_fingerprint", ""))
    recomputed = _recompute_spec_fingerprint(spec_dict)
    if recorded != recomputed:
        return _fail(
            "prereg_binding",
            trial_id,
            "record spec fingerprint does not match the stored spec",
            f"{trial_id}: recorded {recorded[:12]}..., "
            f"recomputed {recomputed[:12]}...",
        )
    return _pass(
        "prereg_binding",
        trial_id,
        f"bound to {hypothesis_id} v{version} (fingerprint, plan, spec hash)",
        f"{trial_id}: fingerprint {stored_fingerprint[:12]}..., "
        f"spec hash {recorded[:12]}...",
    )


def _holm_family(record: dict[str, Any]) -> list[dict[str, Any]] | None:
    metrics = (record.get("result") or {}).get("metrics") or {}
    family = metrics.get("holm")
    return family if isinstance(family, list) else None


def check_multiple_testing(
    record: dict[str, Any],
    spec: HypothesisSpec | None,
    label: str,
) -> CheckResult:
    """Recompute a trial's multiple-testing adjustment from its raw p-values.

    Uses the repo's own adjust_pvalues with the method and error rate
    from the preregistered spec. Checks three things: the recorded
    family has exactly the planned test count; every recorded raw
    p-value matches the corresponding test's p-value in the metrics;
    and every recorded adjusted p-value (and reject flag) matches the
    recomputation within 1e-9.
    """
    trial_id = str(record.get("trial_id", label))
    if spec is None:
        return _unverified(
            "multiple_testing",
            trial_id,
            "cannot recompute: preregistered spec unavailable",
            f"{trial_id}: no spec to take the method and error rate from",
        )
    family = _holm_family(record)
    if family is None:
        return _unverified(
            "multiple_testing",
            trial_id,
            "no Holm family recorded in the trial metrics",
            f"{trial_id}: metrics has no 'holm' list",
        )
    if len(family) != spec.planned_test_count:
        return _fail(
            "multiple_testing",
            trial_id,
            "recorded family size differs from the planned test count",
            f"{trial_id}: family has {len(family)} test(s), "
            f"spec plans {spec.planned_test_count}",
        )
    metrics = (record.get("result") or {}).get("metrics") or {}
    tests = metrics.get("tests") or {}
    raw_values: list[float] = []
    for entry in family:
        name = str(entry.get("test", "?"))
        test = tests.get(name)
        if not isinstance(test, dict) or "p_value" not in test:
            return _fail(
                "multiple_testing",
                trial_id,
                f"family test {name!r} has no recorded test result",
                f"{trial_id}: 'holm' lists {name!r}, metrics['tests'] lacks it",
            )
        recorded_raw = entry.get("raw_p_value")
        test_p = test["p_value"]
        if (
            not isinstance(recorded_raw, (int, float))
            or not isinstance(test_p, (int, float))
            or abs(float(recorded_raw) - float(test_p)) > RAW_P_TOLERANCE
        ):
            return _fail(
                "multiple_testing",
                trial_id,
                f"recorded raw p-value for {name!r} disagrees with the test result",
                f"{trial_id}: holm raw p {recorded_raw!r}, "
                f"tests[{name!r}].p_value {test_p!r}",
            )
        raw_values.append(float(recorded_raw))
    recomputed = adjust_pvalues(
        raw_values,
        method=MultiplicityCorrection(spec.multiple_testing_method),
        target_error_rate=spec.target_error_rate,
    )
    for entry, adjusted in zip(family, recomputed, strict=True):
        name = str(entry.get("test", "?"))
        recorded_adj = entry.get("adjusted_p_value")
        if (
            not isinstance(recorded_adj, (int, float))
            or abs(float(recorded_adj) - adjusted.adjusted_p_value)
            > ADJUSTED_P_TOLERANCE
        ):
            return _fail(
                "multiple_testing",
                trial_id,
                f"adjusted p-value for {name!r} does not recompute",
                f"{trial_id} {name}: recorded {recorded_adj!r}, recomputed "
                f"{adjusted.adjusted_p_value!r} "
                f"({spec.multiple_testing_method.value}, "
                f"alpha={spec.target_error_rate})",
            )
        if entry.get("reject") != adjusted.reject:
            return _fail(
                "multiple_testing",
                trial_id,
                f"reject flag for {name!r} does not recompute",
                f"{trial_id} {name}: recorded reject {entry.get('reject')!r}, "
                f"recomputed {adjusted.reject!r}",
            )
    return _pass(
        "multiple_testing",
        trial_id,
        f"{spec.multiple_testing_method.value} adjustment recomputes "
        f"({len(family)} test(s), family size matches plan)",
        f"{trial_id}: {len(family)} adjusted p-value(s) and reject flag(s) agree",
    )


# The primary effect criterion key, e.g. "primary_partial_r_squared_at_least_0.005"
# or "primary_standardized_mean_car_at_most_minus_0.3". One regex with a
# longest-first alternation so "partial_r_squared" is never misread as
# "r_squared" (a substring match would make every lead-lag trial
# ambiguous). The captured field name is also the ledger test field.
_EFFECT_CRITERION_RE = re.compile(
    r"(?:^|_)(partial_r_squared|r_squared|standardized_mean_car|effect_ratio)"
    r"_(at_least|at_most_minus)_([0-9.]+)$"
)
_P_CRITERION_RE = re.compile(r"holm_adjusted.*_p_below_([0-9.]+)$")


def _primary_test_name(record: dict[str, Any]) -> str | None:
    family = _holm_family(record)
    if not family:
        return None
    return str(family[0].get("test", "")) or None


def check_verdict_consistency(
    record: dict[str, Any],
    spec: HypothesisSpec | None,
    label: str,
) -> CheckResult:
    """Re-derive a trial's verdict from its recorded metrics and spec.

    Three derivations: the recorded ``supported`` flag must equal the
    conjunction of the recorded criteria; the Holm-adjusted primary
    p-value criterion must match the recomputed comparison against the
    preregistered error rate; and the primary effect criterion must
    match the recomputed comparison of the primary test's effect
    against the preregistered minimum effect size. Other criteria
    (walk-forward OOS, cost gate, split-half) are covered by the
    conjunction check as recorded values, not re-derived here. A
    verdict whose primary-criterion keys do not match the known
    patterns is UNVERIFIED for the unmatchable part, not failed.
    """
    trial_id = str(record.get("trial_id", label))
    metrics = (record.get("result") or {}).get("metrics") or {}
    verdict = metrics.get("verdict")
    if not isinstance(verdict, dict):
        return _unverified(
            "verdict_consistency",
            trial_id,
            "no verdict recorded in the trial metrics",
            f"{trial_id}: metrics has no 'verdict' object",
        )
    supported = verdict.get("supported")
    criteria = verdict.get("criteria")
    if not isinstance(supported, bool) or not isinstance(criteria, dict):
        return _unverified(
            "verdict_consistency",
            trial_id,
            "verdict lacks a boolean 'supported' flag or a criteria map",
            f"{trial_id}: supported={supported!r}, criteria type "
            f"{type(criteria).__name__}",
        )
    if supported != all(bool(value) for value in criteria.values()):
        return _fail(
            "verdict_consistency",
            trial_id,
            "recorded 'supported' flag contradicts the recorded criteria",
            f"{trial_id}: supported={supported}, criteria={dict(criteria)}",
        )
    if spec is None:
        return _unverified(
            "verdict_consistency",
            trial_id,
            "conjunction holds; primary criteria not re-derived (no spec)",
            f"{trial_id}: supported={supported} equals the conjunction of "
            f"{len(criteria)} criteria; spec unavailable",
        )
    primary = _primary_test_name(record)
    family = _holm_family(record)
    if primary is None or not family:
        return _unverified(
            "verdict_consistency",
            trial_id,
            "conjunction holds; primary test not identifiable (no Holm family)",
            f"{trial_id}: supported={supported} equals the conjunction of "
            f"{len(criteria)} criteria; no primary test to re-derive from",
        )
    derived: list[str] = [
        f"supported={supported} equals the conjunction of {len(criteria)} criteria"
    ]
    p_keys = [
        key for key in criteria if _P_CRITERION_RE.fullmatch(str(key)) is not None
    ]
    if len(p_keys) == 1:
        key = p_keys[0]
        p_match = _P_CRITERION_RE.fullmatch(key)
        assert p_match is not None  # guaranteed by the filter above
        threshold = float(p_match.group(1))
        adjusted = family[0].get("adjusted_p_value")
        if threshold != spec.target_error_rate:
            return _fail(
                "verdict_consistency",
                trial_id,
                "p-criterion threshold in the verdict key differs from the spec",
                f"{trial_id}: criterion {key!r} uses {threshold}, spec "
                f"target_error_rate={spec.target_error_rate}",
            )
        if not isinstance(adjusted, (int, float)):
            return _unverified(
                "verdict_consistency",
                trial_id,
                "primary adjusted p-value not recorded as a number",
                f"{trial_id}: holm[0].adjusted_p_value={adjusted!r}",
            )
        expected = bool(adjusted < spec.target_error_rate)
        if bool(criteria[key]) != expected:
            return _fail(
                "verdict_consistency",
                trial_id,
                "p-criterion value contradicts the recorded adjusted p-value",
                f"{trial_id}: criterion {key!r}={criteria[key]!r}, "
                f"adjusted p={adjusted} < {spec.target_error_rate} is {expected}",
            )
        derived.append(f"{key}={criteria[key]} (adjusted p {adjusted})")
    elif len(p_keys) > 1:
        return _unverified(
            "verdict_consistency",
            trial_id,
            "ambiguous p-criterion keys; cannot identify the primary one",
            f"{trial_id}: p-criterion keys {p_keys}",
        )
    effect_keys: list[tuple[str, str, str, float]] = []
    for key in criteria:
        match = _EFFECT_CRITERION_RE.search(str(key))
        if match is not None:
            field, direction_word, threshold_text = match.groups()
            direction = ">=" if direction_word == "at_least" else "<="
            effect_keys.append((str(key), field, direction, float(threshold_text)))
    if len(effect_keys) == 1:
        key, field, direction, threshold = effect_keys[0]
        tests = metrics.get("tests") or {}
        test = tests.get(primary) or {}
        value = test.get(field)
        if threshold != spec.minimum_effect_size:
            return _fail(
                "verdict_consistency",
                trial_id,
                "effect-criterion threshold in the verdict key differs from the spec",
                f"{trial_id}: criterion {key!r} uses {threshold}, spec "
                f"minimum_effect_size={spec.minimum_effect_size}",
            )
        if not isinstance(value, (int, float)):
            return _unverified(
                "verdict_consistency",
                trial_id,
                "primary effect value not recorded as a number",
                f"{trial_id}: tests[{primary!r}][{field!r}]={value!r}",
            )
        if direction == ">=":
            expected = bool(value >= threshold)
            comparison = f"{value} >= {threshold}"
        else:
            expected = bool(value <= -threshold)
            comparison = f"{value} <= -{threshold}"
        if bool(criteria[key]) != expected:
            return _fail(
                "verdict_consistency",
                trial_id,
                "effect-criterion value contradicts the recorded effect",
                f"{trial_id}: criterion {key!r}={criteria[key]!r}, "
                f"{field} {comparison} is {expected}",
            )
        derived.append(f"{key}={criteria[key]} ({field} {comparison})")
    elif len(effect_keys) > 1:
        return _unverified(
            "verdict_consistency",
            trial_id,
            "ambiguous effect-criterion keys; cannot identify the primary one",
            f"{trial_id}: effect-criterion keys {[item[0] for item in effect_keys]}",
        )
    return _pass(
        "verdict_consistency",
        trial_id,
        f"verdict re-derives from metrics and spec (primary test {primary})",
        f"{trial_id}: " + "; ".join(derived),
    )


def check_hypothesis_state(
    registry: HypothesisRegistry | None,
    hypothesis_id: str,
    version: int,
    expected_supported: bool,
    label: str,
) -> CheckResult:
    """Verify a tested hypothesis's lifecycle state matches its verdict.

    A hypothesis whose latest completed trial supported it must be in
    state SUPPORTED; one whose trial rejected it must be REJECTED.
    Terminal states are the lab's own record of the outcome — a trial
    verdict that never reached the registry is an unclosed loop.
    """
    subject = f"{hypothesis_id} v{version}"
    if registry is None:
        return _unverified(
            "hypothesis_state",
            subject,
            "cannot check state: registry unavailable",
            f"{label}: no registry to read the state from",
        )
    try:
        state = registry.get_state(hypothesis_id, version)
    except FileNotFoundError as exc:
        return _fail(
            "hypothesis_state",
            subject,
            f"no lifecycle events for the tested hypothesis: {exc}",
            f"{label}: {exc}",
        )
    expected = (
        HypothesisState.SUPPORTED if expected_supported else HypothesisState.REJECTED
    )
    if state != expected:
        return _fail(
            "hypothesis_state",
            subject,
            f"lifecycle state {state.value} contradicts the trial verdict",
            f"{label}: latest completed trial supported={expected_supported}, "
            f"registry state is {state.value}, expected {expected.value}",
        )
    return _pass(
        "hypothesis_state",
        subject,
        f"lifecycle state {state.value} matches the trial verdict",
        f"{label}: supported={expected_supported}, state={state.value}",
    )


def check_trial_sequence(
    records_by_study: dict[str, list[dict[str, Any]]],
) -> CheckResult:
    """Verify the lab-wide trial ID sequence has no silent gaps.

    Trial IDs must form a contiguous sequence from T0001, except the
    reserved T0003 (preregistered H0003 forward test, not yet run), and
    the known failed trials must each be present with status "failed".
    A deleted failure record is exactly what this check is for: the hash
    chain cannot catch a deleted record that was never anchored, but the
    sequence can.
    """
    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for _study, records in sorted(records_by_study.items()):
        for record in records:
            trial_id = str(record.get("trial_id", "?"))
            if trial_id in seen:
                duplicates.append(trial_id)
            seen[trial_id] = str(record.get("status", "?"))
    if duplicates:
        return _fail(
            "trial_sequence",
            "lab",
            f"duplicate trial ID(s): {', '.join(sorted(set(duplicates)))}",
            f"lab: trial IDs appear in more than one ledger: "
            f"{', '.join(sorted(set(duplicates)))}",
        )
    numbers = sorted(
        int(trial_id[1:])
        for trial_id in seen
        if trial_id.startswith("T") and trial_id[1:].isdigit()
    )
    if not numbers:
        return _unverified(
            "trial_sequence",
            "lab",
            "no trial records found in any study ledger",
            "lab: nothing to sequence-check",
        )
    expected = {
        f"T{number:04d}" for number in range(1, max(numbers) + 1)
    } - RESERVED_TRIAL_IDS
    missing = sorted(expected - set(seen))
    if missing:
        return _fail(
            "trial_sequence",
            "lab",
            f"trial ID(s) missing from the ledgers: {', '.join(missing)}",
            f"lab: expected {sorted(expected)}, recorded {sorted(seen)}; "
            f"reserved (allowed): {sorted(RESERVED_TRIAL_IDS)}",
        )
    for failed_id in sorted(KNOWN_FAILED_TRIAL_IDS):
        status = seen.get(failed_id)
        if status is None:
            return _fail(
                "trial_sequence",
                "lab",
                f"known failed trial {failed_id} is absent from the ledgers",
                f"lab: {failed_id} must be recorded with status 'failed'",
            )
        if status != "failed":
            return _fail(
                "trial_sequence",
                "lab",
                f"known failed trial {failed_id} has status {status!r}, not 'failed'",
                f"lab: {failed_id} status is {status!r}",
            )
    return _pass(
        "trial_sequence",
        "lab",
        f"sequence T0001..T{max(numbers):04d} complete "
        f"({len(seen)} trial(s), T0003 reserved, "
        f"{len(KNOWN_FAILED_TRIAL_IDS)} failed trial(s) recorded)",
        f"lab: {len(seen)} trial(s); reserved: T0003; "
        f"failed: {', '.join(sorted(KNOWN_FAILED_TRIAL_IDS))}",
    )


def _compare_cell(
    rule: ReportRule,
    header: str,
    cell: str,
    ledger_value: Any,
) -> tuple[bool, str] | None:
    """Compare one report cell against its ledger value within rounding.

    Returns None when the comparison cannot be made (a non-numeric
    report cell such as "—", or a non-numeric ledger value such as a
    null partial R²) — the column is skipped, not failed.
    """
    parsed = parse_report_number(cell)
    if parsed is None:
        return None
    report_value, tolerance = parsed
    if not isinstance(ledger_value, (int, float)) or isinstance(ledger_value, bool):
        return None
    if header == "n":
        match = int(report_value) == int(ledger_value)
        detail = (
            f"{header}: report {int(report_value)} vs ledger {int(ledger_value)}"
        )
        return match, detail
    match = abs(report_value - float(ledger_value)) <= tolerance
    detail = (
        f"{header}: report {report_value} vs ledger {float(ledger_value)} "
        f"(tolerance {tolerance:.2g})"
    )
    return match, detail


def _compare_window_n(
    rule: ReportRule, cell: str, test: dict[str, Any]
) -> tuple[bool, str] | None:
    """Compare a 'total (window / non-window)' cell; None if unparsable."""
    parsed = parse_window_n(cell)
    if parsed is None:
        return None
    total, window, nonwindow = parsed
    ledger = (
        test.get("observations"),
        test.get("window_observations"),
        test.get("nonwindow_observations"),
    )
    match = (total, window, nonwindow) == ledger
    return match, (
        f"n (window / non-window): report {parsed} vs ledger {ledger}"
    )


def _compare_boot_ci(
    rule: ReportRule, cell: str, test: dict[str, Any]
) -> tuple[bool, str] | None:
    """Compare a '[lower, upper]' CI cell; None if unparsable/non-numeric."""
    parsed = parse_boot_ci(cell)
    if parsed is None:
        return None
    (lower_value, lower_tol), (upper_value, upper_tol) = parsed
    lower = test.get("bootstrap_ci_lower")
    upper = test.get("bootstrap_ci_upper")
    if not isinstance(lower, (int, float)) or not isinstance(upper, (int, float)):
        return None
    match = (
        abs(lower_value - float(lower)) <= lower_tol
        and abs(upper_value - float(upper)) <= upper_tol
    )
    return match, (
        f"95% boot CI: report [{lower_value}, {upper_value}] vs ledger "
        f"[{lower}, {upper}]"
    )


def check_report_ledger(
    report_text: str | None,
    records: list[dict[str, Any]],
    rules: tuple[ReportRule, ...],
    label: str,
) -> CheckResult:
    """Verify a study report's headline table numbers against its ledger.

    Each rule locates one results-table row by its label and compares
    the numeric columns against the ledger test record within the
    rounding tolerance implied by the report's stated precision. A rule
    whose table or row cannot be located is UNVERIFIED (reported as
    such); a rule whose numbers disagree is FAIL. PASS requires at
    least one rule verified and none failed.
    """
    if report_text is None:
        return _unverified(
            "report_ledger",
            label,
            "report file absent",
            f"{label}: no report text to check",
        )
    if not rules:
        return _unverified(
            "report_ledger",
            label,
            "no report rules defined for this study",
            f"{label}: nothing to check",
        )
    by_trial = {str(r.get("trial_id", "?")): r for r in records}
    tables = parse_markdown_tables(report_text)
    verified = 0
    unverified: list[str] = []
    failures: list[str] = []
    details: list[str] = []
    for rule in rules:
        record = by_trial.get(rule.trial_id)
        if record is None:
            unverified.append(
                f"{rule.trial_id} {rule.test_name}: trial not in the ledger"
            )
            continue
        metrics = (record.get("result") or {}).get("metrics") or {}
        tests = metrics.get("tests") or {}
        test = tests.get(rule.test_name)
        if not isinstance(test, dict):
            unverified.append(
                f"{rule.trial_id} {rule.test_name}: test not in the ledger metrics"
            )
            continue
        table = find_table(tables, rule.table_headers)
        if table is None:
            unverified.append(
                f"{rule.trial_id} {rule.test_name}: no table with headers "
                f"{list(rule.table_headers)} in the report"
            )
            continue
        row = next(
            (
                candidate
                for candidate in table.rows
                if candidate
                and re.fullmatch(rule.row_label, candidate[0].strip()) is not None
            ),
            None,
        )
        if row is None:
            unverified.append(
                f"{rule.trial_id} {rule.test_name}: no row matching "
                f"{rule.row_label!r} in the results table"
            )
            continue
        holm = {
            str(entry.get("test", "")): entry
            for entry in (metrics.get("holm") or [])
            if isinstance(entry, dict)
        }
        header_index = {name: pos for pos, name in enumerate(table.headers)}
        checked = 0
        rule_failures: list[str] = []
        for header, field in rule.columns:
            pos = header_index.get(header)
            if pos is None or pos >= len(row):
                continue
            cell = row[pos]
            if field == HOLM_FIELD:
                entry = holm.get(rule.test_name) or {}
                comparison = _compare_cell(
                    rule, header, cell, entry.get("adjusted_p_value")
                )
            elif field == WINDOW_N_FIELD:
                comparison = _compare_window_n(rule, cell, test)
            elif field == BOOT_CI_FIELD:
                comparison = _compare_boot_ci(rule, cell, test)
            else:
                comparison = _compare_cell(rule, header, cell, test.get(field))
            if comparison is None:
                continue
            match, detail = comparison
            checked += 1
            if not match:
                rule_failures.append(detail)
        if rule_failures:
            failures.append(
                f"{rule.trial_id} {rule.test_name}: " + "; ".join(rule_failures)
            )
        elif checked == 0:
            unverified.append(
                f"{rule.trial_id} {rule.test_name}: row found but no numeric "
                "columns could be compared"
            )
        else:
            verified += 1
            details.append(
                f"{rule.trial_id} {rule.test_name}: {checked} column(s) match"
            )
    if failures:
        return _fail(
            "report_ledger",
            label,
            f"{len(failures)} report row(s) disagree with the ledger; "
            f"{verified} of {len(rules)} verified",
            *failures,
        )
    if verified == 0:
        return _unverified(
            "report_ledger",
            label,
            "no report row could be verified against the ledger",
            *unverified,
        )
    summary = f"{verified}/{len(rules)} report row(s) verified against the ledger"
    if unverified:
        summary += f"; {len(unverified)} row(s) unverifiable"
    return _pass("report_ledger", label, summary, *(details + unverified))


def check_pit(cache_root: Path, study_slug: str, label: str) -> CheckResult:
    """Spot-check point-in-time discipline in a study's retained PIT data.

    Reads every retained parquet batch under the study's cache
    directory and verifies available_at >= event_time for every
    observation. Scoped to historical market-data observations: the
    lab's PIT stores hold no forecasts, for which an earlier
    available_at is legitimate. No retained PIT data means
    UNVERIFIED, not PASS — the check cannot run on data that is gone.
    """
    study_cache = cache_root / study_slug
    batches = sorted(study_cache.rglob("*.parquet")) if study_cache.exists() else []
    if not batches:
        return _unverified(
            "pit_spot_check",
            label,
            "no PIT parquet retained locally for this study",
            f"{label}: data/cache/{study_slug}/ holds no *.parquet batches",
        )
    checked = 0
    violations: list[str] = []
    for batch in batches:
        try:
            table = pq.read_table(batch)
        except Exception as exc:  # any read failure is evidence, not a crash
            return _fail(
                "pit_spot_check",
                label,
                f"PIT batch unreadable: {batch.name}: {exc}",
                f"{label}: {batch.name}: {exc}",
            )
        for row in table.to_pylist():
            try:
                observation = Observation.model_validate(row)
            except ValueError as exc:
                return _fail(
                    "pit_spot_check",
                    label,
                    f"PIT batch row does not validate as an observation: {exc}",
                    f"{label}: {batch.name}: {exc}",
                )
            checked += 1
            if observation.available_at < observation.event_time:
                violations.append(
                    f"{observation.instrument_id} {observation.field} "
                    f"event {observation.event_time.isoformat()} "
                    f"available {observation.available_at.isoformat()}"
                )
                if len(violations) >= 3:
                    break
        if len(violations) >= 3:
            break
    if violations:
        return _fail(
            "pit_spot_check",
            label,
            f"{len(violations)} observation(s) with available_at < event_time "
            f"(showing first {len(violations)})",
            *[f"{label}: {violation}" for violation in violations],
        )
    return _pass(
        "pit_spot_check",
        label,
        f"available_at >= event_time for all {checked} retained observation(s)",
        f"{label}: {checked} observation(s) in {len(batches)} batch(es)",
    )


def power_note(
    trial_id: str,
    entries: tuple[dict[str, Any], ...],
    label: str,
) -> CheckResult:
    """Annotate a trial's primary test with its 2B-audit MDE (informational).

    This never fails: an underpowered null is a recorded limitation of
    the 2B audit, not a defect in the trial. The note restates the
    audit's numbers so the review report carries them next to the trial.
    """
    if not entries:
        return _note(
            "power_note",
            trial_id,
            "no MDE entry for this trial in the 2B audit summary",
            f"{label}: trial {trial_id} has no power-section entry",
        )
    lines: list[str] = []
    for entry in entries:
        edge = str(entry.get("edge_id", "?"))
        observations = entry.get("observations")
        if "mde_partial_r_squared" in entry:
            mde = entry["mde_partial_r_squared"]
            observed = entry.get("observed_partial_r_squared")
            powered = (
                isinstance(observed, (int, float))
                and isinstance(mde, (int, float))
                and observed >= mde
            )
            lines.append(
                f"{edge}: lead-lag n={observations}, MDE partial R²={mde}, "
                f"observed={observed} ({'above' if powered else 'below'} MDE)"
            )
        elif "mde_standardized_mean_car" in entry:
            mde = entry["mde_standardized_mean_car"]
            observed = entry.get("observed_standardized_mean_car")
            powered = (
                isinstance(observed, (int, float))
                and isinstance(mde, (int, float))
                and abs(observed) >= mde
            )
            lines.append(
                f"{edge}: event-study n={observations}, MDE std. mean CAR={mde}, "
                f"observed={observed} ({'above' if powered else 'below'} MDE)"
            )
        elif "mde_r_squared" in entry:
            mde = entry["mde_r_squared"]
            observed = entry.get("observed_r_squared")
            powered = (
                isinstance(observed, (int, float))
                and isinstance(mde, (int, float))
                and observed >= mde
            )
            lines.append(
                f"{edge}: cross-section n={observations}, MDE R²={mde}, "
                f"observed={observed} ({'above' if powered else 'below'} MDE)"
            )
        elif "mde_cohens_d" in entry:
            label_text = str(entry.get("label", edge))
            mde = entry["mde_cohens_d"]
            observed = entry.get("observed_cohens_d")
            powered = (
                isinstance(observed, (int, float))
                and isinstance(mde, (int, float))
                and abs(observed) >= mde
            )
            lines.append(
                f"{edge} ({label_text}): mean comparison "
                f"n={entry.get('window_observations')}/"
                f"{entry.get('nonwindow_observations')}, MDE Cohen's d={mde}, "
                f"observed={observed} ({'above' if powered else 'below'} MDE)"
            )
    noun = "entry" if len(entries) == 1 else "entries"
    return _note(
        "power_note",
        trial_id,
        f"MDE annotation from the 2B audit ({len(entries)} {noun})",
        *lines,
    )
