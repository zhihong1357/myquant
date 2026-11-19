"""Tests for the adversarial reviewer (Stage 6d). All offline, zero network.

Two kinds of fixture: the lab's real records (read-only) and
adversarial fixtures built in tmp dirs. Adversarial ledgers are built
with the repo's own append_trial, so each fixture's hash chain is valid
and exactly one violation is present — except the tampered-ledger
fixture, whose record is mutated without re-chaining.
"""

from __future__ import annotations

import copy
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from myquant.canonical import canonical_json
from myquant.hypotheses import HypothesisRegistry, HypothesisSpec
from myquant.registry import append_trial, read_and_verify, write_anchor
from myquant.review import (
    REPORT_RULES,
    STUDY_REPORTS,
    ReviewVerdict,
    check_hypothesis_state,
    check_ledger_anchor,
    check_ledger_chain,
    check_multiple_testing,
    check_pit,
    check_prereg_binding,
    check_registry_events,
    check_report_ledger,
    check_trial_sequence,
    check_verdict_consistency,
    load_audit_mde_entries,
    power_note,
    render_json,
    render_markdown,
    review_lab,
    review_study,
)
from myquant.review.tables import (
    ReportRule,
    find_table,
    parse_boot_ci,
    parse_markdown_tables,
    parse_report_number,
    parse_window_n,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
REVIEWED_AT = datetime(2026, 11, 19, 7, 30, tzinfo=UTC)

STUDY_SLUGS = (
    "btc-eth-001",
    "lowvol-002",
    "move-vix-003",
    "options-expiry-004",
    "fomc-event-study-005",
    "macro-windows-006",
    "publication-lag-007",
    "credit-spread-spx-008",
    "credit-spread-tyvix-009",
    "credit-spread-vix-010",
    "credit-spread-vxn-011",
    "credit-spread-dgs10-012",
    "btc-dvol-013",
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _real_records(slug: str) -> list[dict[str, Any]]:
    return read_and_verify(REPO_ROOT / "research" / slug / "trials.jsonl")


def _real_record(slug: str, trial_id: str) -> dict[str, Any]:
    for record in _real_records(slug):
        if record["trial_id"] == trial_id:
            return copy.deepcopy(record)
    raise AssertionError(f"{trial_id} not found in {slug}")


def _real_spec(slug: str, hypothesis_id: str, version: int = 1) -> HypothesisSpec:
    registry = HypothesisRegistry(REPO_ROOT / "research" / slug / "hypotheses")
    return registry.get(hypothesis_id, version=version).spec


def _fixture_registry(tmp_path: Path) -> HypothesisRegistry:
    """A tmp registry holding the real H0001 v1 registration."""
    registry = HypothesisRegistry(tmp_path / "hypotheses")
    registry.register(_real_spec("btc-eth-001", "H0001"))
    return registry


def _write_ledger(tmp_path: Path, record: dict[str, Any]) -> Path:
    """Write one record to a tmp ledger with a valid hash chain."""
    ledger = tmp_path / "trials.jsonl"
    append_trial(
        ledger,
        trial_id=str(record["trial_id"]),
        hypothesis_id=str(record["hypothesis_id"]),
        status=str(record["status"]),
        result=copy.deepcopy(record["result"]),
    )
    return ledger


def _observation_row(
    event_time: str, available_at: str, ingested_at: str
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "instrument_id": "BTC-USDT-SWAP",
        "venue": "OKX",
        "event_time": event_time,
        "available_at": available_at,
        "ingested_at": ingested_at,
        "field": "close",
        "value": 90000.0,
        "unit": "USDT",
        "source_id": "okx",
        "source_version": 1,
        "revision": 1,
    }


def _write_pit_batch(
    cache_root: Path, slug: str, rows: list[dict[str, Any]]
) -> None:
    directory = cache_root / slug
    directory.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, directory / "batch.parquet")


# ---------------------------------------------------------------------------
# Table parsing
# ---------------------------------------------------------------------------


def test_parse_report_number_plain_decimal() -> None:
    parsed = parse_report_number("0.0252")
    assert parsed is not None
    value, tolerance = parsed
    assert value == pytest.approx(0.0252)
    assert tolerance == pytest.approx(0.5e-4 + 1e-12)


def test_parse_report_number_unicode_minus_and_plus() -> None:
    parsed = parse_report_number("−0.0093")
    assert parsed is not None and parsed[0] == pytest.approx(-0.0093)
    parsed = parse_report_number("+0.0003")
    assert parsed is not None and parsed[0] == pytest.approx(0.0003)
    parsed = parse_report_number("1,414")
    assert parsed is not None and parsed[0] == 1414.0


def test_parse_report_number_scientific_notation() -> None:
    parsed = parse_report_number("5.201e-09")
    assert parsed is not None
    value, tolerance = parsed
    assert value == pytest.approx(5.201e-09)
    assert tolerance == pytest.approx(0.5e-3 * 1e-9 + 1e-12)


def test_parse_report_number_missing_markers() -> None:
    assert parse_report_number("—") is None
    assert parse_report_number("--") is None
    assert parse_report_number("**yes**") is None
    assert parse_report_number("no") is None


def test_parse_window_n() -> None:
    assert parse_window_n("2,125 (280 / 1,845)") == (2125, 280, 1845)
    assert parse_window_n("not a count") is None


def test_parse_boot_ci() -> None:
    parsed = parse_boot_ci("[−0.00686, +0.00518]")
    assert parsed is not None
    (lower, _), (upper, _) = parsed
    assert lower == pytest.approx(-0.00686)
    assert upper == pytest.approx(0.00518)
    assert parse_boot_ci("no brackets") is None


def test_parse_markdown_tables_and_find() -> None:
    text = (
        "# Title\n\n"
        "| test | n | coef |\n"
        "| --- | --- | --- |\n"
        "| (a) row | 10 | 0.5 |\n\n"
        "| other | x |\n"
        "| --- | --- |\n"
        "| y | 1 |\n"
    )
    tables = parse_markdown_tables(text)
    assert len(tables) == 2
    table = find_table(tables, ("coef",))
    assert table is not None
    assert table.headers == ("test", "n", "coef")
    assert table.rows[0] == ("(a) row", "10", "0.5")
    assert find_table(tables, ("absent",)) is None


def test_report_rules_cover_all_studies() -> None:
    assert set(REPORT_RULES) == set(STUDY_SLUGS)
    total = sum(len(rules) for rules in REPORT_RULES.values())
    assert total == 78


# ---------------------------------------------------------------------------
# Ledger chain and anchor
# ---------------------------------------------------------------------------


def test_ledger_chain_passes_on_real_ledgers() -> None:
    for slug in STUDY_SLUGS:
        result = check_ledger_chain(
            REPO_ROOT / "research" / slug / "trials.jsonl",
            f"research/{slug}/trials.jsonl",
        )
        assert result.verdict is ReviewVerdict.PASS, slug


def test_ledger_chain_fails_on_missing_file(tmp_path: Path) -> None:
    result = check_ledger_chain(tmp_path / "trials.jsonl", "missing")
    assert result.verdict is ReviewVerdict.FAIL
    assert "absent" in result.summary


def test_ledger_chain_fails_on_tampered_record(tmp_path: Path) -> None:
    # Adversarial fixture 1: a record mutated without re-chaining.
    ledger = _write_ledger(tmp_path, _real_record("btc-eth-001", "T0001"))
    record = json.loads(ledger.read_text().splitlines()[0])
    record["result"]["metrics"]["tests"]["daily_btc_eth"]["coefficient"] = 9.99
    ledger.write_bytes(canonical_json(record) + b"\n")
    result = check_ledger_chain(ledger, "tampered")
    assert result.verdict is ReviewVerdict.FAIL
    assert "hash" in result.summary.lower()


def test_ledger_anchor_passes_on_real_ledgers() -> None:
    for slug in STUDY_SLUGS:
        if slug == "fomc-event-study-005":
            continue  # study 005 has no anchor file; covered below
        result = check_ledger_anchor(
            REPO_ROOT / "research" / slug / "trials.jsonl",
            f"research/{slug}/trials.jsonl",
        )
        assert result.verdict is ReviewVerdict.PASS, slug


def test_ledger_anchor_unverified_without_anchor_file() -> None:
    result = check_ledger_anchor(
        REPO_ROOT / "research/fomc-event-study-005/trials.jsonl",
        "research/fomc-event-study-005/trials.jsonl",
    )
    assert result.verdict is ReviewVerdict.UNVERIFIED
    assert "truncation" in result.summary


def test_ledger_anchor_fails_on_mismatch(tmp_path: Path) -> None:
    ledger = _write_ledger(tmp_path, _real_record("btc-eth-001", "T0001"))
    write_anchor(ledger)
    # Append a second record: the anchor now describes a shorter ledger.
    append_trial(
        ledger,
        trial_id="T0099",
        hypothesis_id="H0001",
        status="failed",
        result={"schema_version": 1, "error": "fixture"},
    )
    result = check_ledger_anchor(ledger, "truncated")
    assert result.verdict is ReviewVerdict.FAIL


# ---------------------------------------------------------------------------
# Registry events
# ---------------------------------------------------------------------------


def test_registry_events_pass_on_real_registries() -> None:
    for slug in STUDY_SLUGS:
        result = check_registry_events(
            REPO_ROOT / "research" / slug / "hypotheses",
            f"research/{slug}/hypotheses",
        )
        assert result.verdict is ReviewVerdict.PASS, slug


def test_registry_events_unverified_when_absent(tmp_path: Path) -> None:
    result = check_registry_events(tmp_path / "hypotheses", "missing")
    assert result.verdict is ReviewVerdict.UNVERIFIED


def test_registry_events_fail_on_tampered_log(tmp_path: Path) -> None:
    target = tmp_path / "hypotheses"
    shutil.copytree(REPO_ROOT / "research/btc-eth-001/hypotheses", target)
    events_path = target / "hypothesis-events.jsonl"
    lines = events_path.read_text().splitlines()
    event = json.loads(lines[0])
    event["event_type"] = "tampered"
    lines[0] = json.dumps(event)
    events_path.write_text("\n".join(lines) + "\n")
    result = check_registry_events(target, "tampered")
    assert result.verdict is ReviewVerdict.FAIL


# ---------------------------------------------------------------------------
# Preregistration binding
# ---------------------------------------------------------------------------


def test_prereg_binding_passes_on_clean_fixture(tmp_path: Path) -> None:
    registry = _fixture_registry(tmp_path)
    record = _real_record("btc-eth-001", "T0001")
    result = check_prereg_binding(record, registry, "T0001")
    assert result.verdict is ReviewVerdict.PASS


def test_prereg_binding_passes_on_all_real_trials() -> None:
    for slug in STUDY_SLUGS:
        registry = HypothesisRegistry(REPO_ROOT / "research" / slug / "hypotheses")
        for record in _real_records(slug):
            result = check_prereg_binding(record, registry, str(record["trial_id"]))
            assert result.verdict is ReviewVerdict.PASS, (
                slug,
                record["trial_id"],
                result.summary,
            )


def test_prereg_binding_fails_on_fingerprint_mismatch(tmp_path: Path) -> None:
    # Adversarial fixture 2: the trial's fingerprint does not match the
    # preregistration. The ledger is re-chained, so only this check fails.
    registry = _fixture_registry(tmp_path)
    record = _real_record("btc-eth-001", "T0001")
    record["result"]["spec"]["hypothesis_fingerprint"] = "0" * 64
    result = check_prereg_binding(record, registry, "T0001")
    assert result.verdict is ReviewVerdict.FAIL
    assert "fingerprint" in result.summary


def test_prereg_binding_fails_on_plan_mismatch(tmp_path: Path) -> None:
    registry = _fixture_registry(tmp_path)
    record = _real_record("btc-eth-001", "T0001")
    record["result"]["spec"]["seed"] = 43  # preregistered seed is 42
    result = check_prereg_binding(record, registry, "T0001")
    assert result.verdict is ReviewVerdict.FAIL
    assert "research plan" in result.summary


def test_prereg_binding_unverified_without_registry() -> None:
    record = _real_record("btc-eth-001", "T0001")
    result = check_prereg_binding(record, None, "T0001")
    assert result.verdict is ReviewVerdict.UNVERIFIED


# ---------------------------------------------------------------------------
# Multiple testing
# ---------------------------------------------------------------------------


def test_multiple_testing_passes_on_all_completed_trials() -> None:
    for slug in STUDY_SLUGS:
        for record in _real_records(slug):
            if record["status"] != "completed":
                continue
            spec = _real_spec(
                slug,
                str(record["result"]["spec"]["hypothesis_id"]),
                int(record["result"]["spec"]["hypothesis_version"]),
            )
            result = check_multiple_testing(record, spec, str(record["trial_id"]))
            assert result.verdict is ReviewVerdict.PASS, (
                slug,
                record["trial_id"],
                result.summary,
            )


def test_multiple_testing_fails_on_wrong_adjusted_p() -> None:
    # Adversarial fixture 3: one adjusted p-value changed by a digit.
    record = _real_record("btc-eth-001", "T0001")
    record["result"]["metrics"]["holm"][0]["adjusted_p_value"] = 0.5
    spec = _real_spec("btc-eth-001", "H0001")
    result = check_multiple_testing(record, spec, "T0001")
    assert result.verdict is ReviewVerdict.FAIL
    assert "adjusted p-value" in result.summary
    assert "daily_btc_eth" in result.evidence[0]


def test_multiple_testing_fails_on_family_size_mismatch() -> None:
    record = _real_record("btc-eth-001", "T0001")
    spec = _real_spec("btc-eth-001", "H0001").model_copy(
        update={"planned_test_count": 4}
    )
    result = check_multiple_testing(record, spec, "T0001")
    assert result.verdict is ReviewVerdict.FAIL
    assert "family size" in result.summary


def test_multiple_testing_fails_on_raw_p_mismatch() -> None:
    record = _real_record("btc-eth-001", "T0001")
    record["result"]["metrics"]["holm"][0]["raw_p_value"] = 0.5
    spec = _real_spec("btc-eth-001", "H0001")
    result = check_multiple_testing(record, spec, "T0001")
    assert result.verdict is ReviewVerdict.FAIL
    assert "raw p-value" in result.summary


def test_multiple_testing_unverified_without_spec() -> None:
    record = _real_record("btc-eth-001", "T0001")
    result = check_multiple_testing(record, None, "T0001")
    assert result.verdict is ReviewVerdict.UNVERIFIED


# ---------------------------------------------------------------------------
# Verdict consistency
# ---------------------------------------------------------------------------


def test_verdict_consistency_passes_on_all_completed_trials() -> None:
    for slug in STUDY_SLUGS:
        for record in _real_records(slug):
            if record["status"] != "completed":
                continue
            spec = _real_spec(
                slug,
                str(record["result"]["spec"]["hypothesis_id"]),
                int(record["result"]["spec"]["hypothesis_version"]),
            )
            result = check_verdict_consistency(record, spec, str(record["trial_id"]))
            assert result.verdict is ReviewVerdict.PASS, (
                slug,
                record["trial_id"],
                result.summary,
            )


def test_verdict_consistency_fails_on_flipped_supported_flag() -> None:
    # Adversarial fixture 4: the verdict flag contradicts the criteria.
    record = _real_record("btc-eth-001", "T0001")
    record["result"]["metrics"]["verdict"]["supported"] = True
    spec = _real_spec("btc-eth-001", "H0001")
    result = check_verdict_consistency(record, spec, "T0001")
    assert result.verdict is ReviewVerdict.FAIL
    assert "contradicts the recorded criteria" in result.summary


def test_verdict_consistency_fails_on_flipped_effect_criterion() -> None:
    # Flip only the effect criterion: the conjunction still holds
    # (the other criteria stay false, so supported stays false), but
    # the criterion value contradicts the recorded partial R².
    record = _real_record("btc-eth-001", "T0001")
    criteria = record["result"]["metrics"]["verdict"]["criteria"]
    criteria["primary_partial_r_squared_at_least_0.005"] = True
    spec = _real_spec("btc-eth-001", "H0001")
    result = check_verdict_consistency(record, spec, "T0001")
    assert result.verdict is ReviewVerdict.FAIL
    assert "effect-criterion" in result.summary


def test_verdict_consistency_unverified_without_verdict() -> None:
    record = _real_record("btc-eth-001", "T0001")
    del record["result"]["metrics"]["verdict"]
    spec = _real_spec("btc-eth-001", "H0001")
    result = check_verdict_consistency(record, spec, "T0001")
    assert result.verdict is ReviewVerdict.UNVERIFIED


# ---------------------------------------------------------------------------
# Hypothesis state
# ---------------------------------------------------------------------------


def test_hypothesis_state_passes_on_real_registries() -> None:
    registry = HypothesisRegistry(REPO_ROOT / "research/btc-eth-001/hypotheses")
    result = check_hypothesis_state(registry, "H0001", 1, False, "btc-eth-001")
    assert result.verdict is ReviewVerdict.PASS
    registry = HypothesisRegistry(REPO_ROOT / "research/macro-windows-006/hypotheses")
    result = check_hypothesis_state(registry, "H0010", 1, True, "macro-windows-006")
    assert result.verdict is ReviewVerdict.PASS


def test_hypothesis_state_fails_on_mismatch() -> None:
    registry = HypothesisRegistry(REPO_ROOT / "research/btc-eth-001/hypotheses")
    result = check_hypothesis_state(registry, "H0001", 1, True, "btc-eth-001")
    assert result.verdict is ReviewVerdict.FAIL
    assert "contradicts the trial verdict" in result.summary


def test_hypothesis_state_unverified_without_registry() -> None:
    result = check_hypothesis_state(None, "H0001", 1, False, "missing")
    assert result.verdict is ReviewVerdict.UNVERIFIED


# ---------------------------------------------------------------------------
# Trial sequence
# ---------------------------------------------------------------------------


def _all_lab_records() -> dict[str, list[dict[str, Any]]]:
    return {slug: _real_records(slug) for slug in STUDY_SLUGS}


def test_trial_sequence_passes_on_real_lab() -> None:
    # T0003 is reserved for the H0003 forward test and must not be
    # misreported as missing.
    result = check_trial_sequence(_all_lab_records())
    assert result.verdict is ReviewVerdict.PASS
    assert "T0003 reserved" in result.summary


def test_trial_sequence_fails_on_deleted_failed_trial() -> None:
    # Adversarial fixture 6: the failed trial T0006 deleted from its ledger.
    records = _all_lab_records()
    records["options-expiry-004"] = [
        record
        for record in records["options-expiry-004"]
        if record["trial_id"] != "T0006"
    ]
    result = check_trial_sequence(records)
    assert result.verdict is ReviewVerdict.FAIL
    assert "T0006" in result.summary


def test_trial_sequence_fails_on_duplicate() -> None:
    records = _all_lab_records()
    records["lowvol-002"] = records["lowvol-002"] + [_real_record("btc-eth-001", "T0001")]
    result = check_trial_sequence(records)
    assert result.verdict is ReviewVerdict.FAIL
    assert "duplicate" in result.summary


# ---------------------------------------------------------------------------
# Report-ledger consistency
# ---------------------------------------------------------------------------


def test_report_ledger_passes_on_clean_studies() -> None:
    for slug in ("btc-eth-001", "lowvol-002", "fomc-event-study-005", "macro-windows-006"):
        text = (REPO_ROOT / STUDY_REPORTS[slug]).read_text(encoding="utf-8")
        result = check_report_ledger(
            text,
            _real_records(slug),
            REPORT_RULES[slug],
            slug,
        )
        assert result.verdict is ReviewVerdict.PASS, (slug, result.summary)


def test_report_ledger_fails_on_study_003_incr_column() -> None:
    # Regression test for the reviewer's first-run finding: study 003's
    # "incr R²" column once duplicated partial R² in three rows (daily,
    # weekly, weekly no-factor). The reports are fixed now, so re-introduce
    # the old wrong values into a copy and assert the check still catches
    # exactly that discrepancy class.
    text = (
        REPO_ROOT / "docs/studies/move-vix-transmission-003.md"
    ).read_text(encoding="utf-8")
    changed = (
        text.replace("0.000035 | 0.000034", "0.000035 | 0.000035")
        .replace("0.0000086 | 0.0000083", "0.0000086 | 0.0000086")
        .replace("0.0000086 | 0.0000084", "0.0000086 | 0.0000086")
    )
    assert changed != text
    result = check_report_ledger(
        changed,
        _real_records("move-vix-003"),
        REPORT_RULES["move-vix-003"],
        "move-vix-003",
    )
    assert result.verdict is ReviewVerdict.FAIL
    assert "3 report row(s)" in result.summary
    assert all("incr R²" in item for item in result.evidence)


def test_report_ledger_fails_on_study_004_ci_and_study_007_se() -> None:
    # Regression tests for the reviewer's first-run findings (one
    # last-digit transcription slip each). The reports are fixed now, so
    # re-introduce the old wrong values into copies and assert the check
    # still catches them.
    text = (
        REPO_ROOT / "docs/studies/options-expiry-004.md"
    ).read_text(encoding="utf-8")
    changed = text.replace("+0.00517]", "+0.00518]")
    assert changed != text
    result = check_report_ledger(
        changed,
        _real_records("options-expiry-004"),
        REPORT_RULES["options-expiry-004"],
        "options-expiry-004",
    )
    assert result.verdict is ReviewVerdict.FAIL
    assert "95% boot CI" in result.evidence[0]

    text = (
        REPO_ROOT / "docs/studies/publication-lag-007.md"
    ).read_text(encoding="utf-8")
    changed = text.replace("0.785382", "0.785383")
    assert changed != text
    result = check_report_ledger(
        changed,
        _real_records("publication-lag-007"),
        REPORT_RULES["publication-lag-007"],
        "publication-lag-007",
    )
    assert result.verdict is ReviewVerdict.FAIL
    assert "SE" in result.evidence[0]


def test_report_ledger_fails_on_changed_number() -> None:
    text = (
        REPO_ROOT / "docs/studies/btc-eth-transmission-001.md"
    ).read_text(encoding="utf-8")
    row = "| (a) daily BTC→ETH, SOL control | 1,414 | 0.0252 |"
    assert row in text
    changed = text.replace(row, "| (a) daily BTC→ETH, SOL control | 1,414 | 0.0253 |")
    result = check_report_ledger(
        changed, _real_records("btc-eth-001"), REPORT_RULES["btc-eth-001"], "btc-eth-001"
    )
    assert result.verdict is ReviewVerdict.FAIL
    assert "coef" in result.evidence[0]


def test_report_ledger_unverified_when_row_unlocatable() -> None:
    rules = (
        ReportRule(
            trial_id="T0001",
            test_name="daily_btc_eth",
            table_headers=("coef",),
            row_label=r"a row that does not exist",
            columns=(("coef", "coefficient"),),
        ),
    )
    text = (
        REPO_ROOT / "docs/studies/btc-eth-transmission-001.md"
    ).read_text(encoding="utf-8")
    result = check_report_ledger(
        text, _real_records("btc-eth-001"), rules, "btc-eth-001"
    )
    assert result.verdict is ReviewVerdict.UNVERIFIED
    assert "no row matching" in result.evidence[0]


def test_report_ledger_unverified_when_report_absent() -> None:
    result = check_report_ledger(
        None, _real_records("btc-eth-001"), REPORT_RULES["btc-eth-001"], "btc-eth-001"
    )
    assert result.verdict is ReviewVerdict.UNVERIFIED


# ---------------------------------------------------------------------------
# PIT spot-check
# ---------------------------------------------------------------------------


def test_pit_unverified_when_no_data_retained(tmp_path: Path) -> None:
    result = check_pit(tmp_path, "btc-eth-001", "btc-eth-001")
    assert result.verdict is ReviewVerdict.UNVERIFIED
    assert "no PIT parquet" in result.summary


def test_pit_passes_on_clean_synthetic_panel(tmp_path: Path) -> None:
    _write_pit_batch(
        tmp_path,
        "fixture",
        [
            _observation_row(
                "2026-01-01T16:00:00Z", "2026-01-01T16:00:00Z", "2026-01-01T16:00:01Z"
            ),
            _observation_row(
                "2026-01-02T16:00:00Z", "2026-01-02T16:00:00Z", "2026-01-02T16:00:01Z"
            ),
        ],
    )
    result = check_pit(tmp_path, "fixture", "fixture")
    assert result.verdict is ReviewVerdict.PASS
    assert "2 retained observation(s)" in result.summary


def test_pit_fails_on_available_before_event(tmp_path: Path) -> None:
    # Adversarial fixture 5: available_at one day before event_time.
    _write_pit_batch(
        tmp_path,
        "fixture",
        [
            _observation_row(
                "2026-01-02T16:00:00Z", "2026-01-01T16:00:00Z", "2026-01-02T16:00:01Z"
            ),
        ],
    )
    result = check_pit(tmp_path, "fixture", "fixture")
    assert result.verdict is ReviewVerdict.FAIL
    assert "available_at < event_time" in result.summary
    assert "2026-01-02" in result.evidence[0]


def test_pit_fails_on_unreadable_batch(tmp_path: Path) -> None:
    directory = tmp_path / "fixture"
    directory.mkdir(parents=True)
    (directory / "batch.parquet").write_bytes(b"not parquet")
    result = check_pit(tmp_path, "fixture", "fixture")
    assert result.verdict is ReviewVerdict.FAIL
    assert "unreadable" in result.summary


# ---------------------------------------------------------------------------
# Power note (informational)
# ---------------------------------------------------------------------------


def test_power_note_never_fails() -> None:
    entries = load_audit_mde_entries(REPO_ROOT / "research/statistical-audit-2b/summary.json")
    assert set(entries) == {
        "T0001",
        "T0002",
        "T0004",
        "T0005",
        "T0007",
        "T0009",
        "T0010",
        "T0011",
        "T0012",
        "T0013",
        "T0015",
        "T0016",
        "T0017",
        "T0018",
        "T0019",
        "T0020",
        "T0021",
    }
    result = power_note("T0001", entries["T0001"], "btc-eth-001")
    assert result.verdict is ReviewVerdict.NOTE
    assert "MDE partial R²" in result.evidence[0]
    result = power_note("T0099", (), "unknown")
    assert result.verdict is ReviewVerdict.NOTE
    assert "no MDE entry" in result.summary


# ---------------------------------------------------------------------------
# Runner: per-study and full-lab review
# ---------------------------------------------------------------------------


def test_review_study_001_counts() -> None:
    review = review_study(REPO_ROOT, "btc-eth-001")
    assert review.counts == {"pass": 8, "fail": 0, "unverified": 1, "note": 0}
    assert review.checks[0].check_id == "ledger_chain"


def test_review_lab_counts_pin_current_lab_state() -> None:
    # Pins the lab state at delivery time: 129 pass, 0 fail, 8 unverified
    # (7 PIT caches not retained + study 005's missing anchor), 17 notes.
    # Studies 008, 009, 010, 011, 012 and 013 are the only studies whose
    # PIT caches are retained locally, so their pit_spot_checks pass
    # where the other seven are unverified.
    # The reviewer's first run found 3 genuine report-ledger
    # discrepancies (studies 003/004/007); they were confirmed against
    # the ledgers and fixed in the same delivery, so the current state
    # is clean — update this test if a future review finds a new FAIL.
    review = review_lab(REPO_ROOT, REVIEWED_AT)
    assert review.counts == {"pass": 129, "fail": 0, "unverified": 8, "note": 17}
    failing = [
        (study.study, check.subject)
        for study in review.studies
        for check in study.checks
        if check.verdict is ReviewVerdict.FAIL
    ]
    assert failing == []
    assert review.lab_checks[0].verdict is ReviewVerdict.PASS


def test_review_is_deterministic_for_one_timestamp() -> None:
    first = review_lab(REPO_ROOT, REVIEWED_AT)
    second = review_lab(REPO_ROOT, REVIEWED_AT)
    assert render_json(first) == render_json(second)
    assert render_markdown(first) == render_markdown(second)
    first_study = review_study(REPO_ROOT, "btc-eth-001")
    second_study = review_study(REPO_ROOT, "btc-eth-001")
    assert first_study.checks == second_study.checks


def test_review_markdown_summarizes_verdicts() -> None:
    review = review_lab(REPO_ROOT, REVIEWED_AT)
    text = render_markdown(review)
    assert "## Summary" in text
    assert "- FAIL: 0" in text
    assert "UNVERIFIED" in text
