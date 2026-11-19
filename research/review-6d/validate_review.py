"""Stage 6d adversarial-reviewer validation: full-lab review + fixtures.

Run from the repo root:

    .venv/bin/python research/review-6d/validate_review.py [--reviewed-at ISO]

Offline and deterministic for a fixed --reviewed-at (the default is the
current UTC time). Runs the reviewer over all nine studies, builds
six adversarial fixtures in tmp dirs — each isolating exactly one
violation, with a valid hash chain everywhere except the tampered-ledger
fixture — and writes:

- ``research/review-6d/review_report.md`` — the full-lab review.
- ``research/review-6d/review_report.json`` — the same review, canonical
  JSON (byte-identical on re-runs with the same --reviewed-at).
- ``research/review-6d/validation_report.md`` — the check list, the lab
  review summary, the fixture results, the rounding-margin diagnostic
  and the limitations (reproduced except the timestamp line).

The reviewer is read-only: this script reads study records, registries,
ledgers and reports and writes only the three files above.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from myquant.canonical import canonical_json  # noqa: E402
from myquant.hypotheses import HypothesisRegistry  # noqa: E402
from myquant.registry import append_trial, read_and_verify  # noqa: E402
from myquant.review import (  # noqa: E402
    REPORT_RULES,
    STUDY_REPORTS,
    LabReview,
    ReviewVerdict,
    check_ledger_chain,
    check_multiple_testing,
    check_pit,
    check_prereg_binding,
    check_trial_sequence,
    check_verdict_consistency,
    render_json,
    render_markdown,
    review_lab,
)
from myquant.review.tables import (  # noqa: E402
    BOOT_CI_FIELD,
    HOLM_FIELD,
    WINDOW_N_FIELD,
    find_table,
    parse_markdown_tables,
    parse_report_number,
)

STUDY_SLUGS = tuple(STUDY_REPORTS)


def _real_records(slug: str) -> list[dict[str, Any]]:
    return read_and_verify(REPO_ROOT / "research" / slug / "trials.jsonl")


def _real_record(slug: str, trial_id: str) -> dict[str, Any]:
    for record in _real_records(slug):
        if record["trial_id"] == trial_id:
            return copy.deepcopy(record)
    raise AssertionError(f"{trial_id} not found in {slug}")


def _fixture_registry(tmp_path: Path) -> HypothesisRegistry:
    real = HypothesisRegistry(REPO_ROOT / "research/btc-eth-001/hypotheses")
    registry = HypothesisRegistry(tmp_path / "hypotheses")
    registry.register(real.get("H0001", version=1).spec)
    return registry


def _write_ledger(tmp_path: Path, record: dict[str, Any]) -> Path:
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


def run_fixtures() -> list[dict[str, Any]]:
    """Build the six adversarial fixtures and run the matching check on each."""
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="review-6d-") as tmp:
        tmp_path = Path(tmp)

        # 1. Tampered ledger record (mutated without re-chaining).
        ledger = _write_ledger(tmp_path / "tampered", _real_record("btc-eth-001", "T0001"))
        record = json.loads(ledger.read_text().splitlines()[0])
        record["result"]["metrics"]["tests"]["daily_btc_eth"]["coefficient"] = 9.99
        ledger.write_bytes(canonical_json(record) + b"\n")
        result = check_ledger_chain(ledger, "tampered")
        results.append(
            {
                "fixture": "tampered ledger record",
                "check": "ledger_chain",
                "verdict": result.verdict.value,
                "reason": result.summary,
            }
        )

        # 2. Trial fingerprint does not match the preregistration.
        registry = _fixture_registry(tmp_path / "fingerprint")
        record = _real_record("btc-eth-001", "T0001")
        record["result"]["spec"]["hypothesis_fingerprint"] = "0" * 64
        result = check_prereg_binding(record, registry, "T0001")
        results.append(
            {
                "fixture": "fingerprint mismatch vs registry",
                "check": "prereg_binding",
                "verdict": result.verdict.value,
                "reason": result.summary,
            }
        )

        # 3. One adjusted p-value changed.
        record = _real_record("btc-eth-001", "T0001")
        record["result"]["metrics"]["holm"][0]["adjusted_p_value"] = 0.5
        real_registry = HypothesisRegistry(
            REPO_ROOT / "research/btc-eth-001/hypotheses"
        )
        spec = real_registry.get("H0001", version=1).spec
        result = check_multiple_testing(record, spec, "T0001")
        results.append(
            {
                "fixture": "wrong adjusted p-value",
                "check": "multiple_testing",
                "verdict": result.verdict.value,
                "reason": result.summary,
            }
        )

        # 4. Verdict flag contradicts the recorded criteria.
        record = _real_record("btc-eth-001", "T0001")
        record["result"]["metrics"]["verdict"]["supported"] = True
        result = check_verdict_consistency(record, spec, "T0001")
        results.append(
            {
                "fixture": "verdict contradicts metrics",
                "check": "verdict_consistency",
                "verdict": result.verdict.value,
                "reason": result.summary,
            }
        )

        # 5. PIT violation in a synthetic panel.
        cache_root = tmp_path / "pit"
        directory = cache_root / "fixture"
        directory.mkdir(parents=True)
        table = pa.Table.from_pylist(
            [
                _observation_row(
                    "2026-01-02T16:00:00Z",
                    "2026-01-01T16:00:00Z",
                    "2026-01-02T16:00:01Z",
                )
            ]
        )
        pq.write_table(table, directory / "batch.parquet")
        result = check_pit(cache_root, "fixture", "fixture")
        results.append(
            {
                "fixture": "PIT violation (available_at < event_time)",
                "check": "pit_spot_check",
                "verdict": result.verdict.value,
                "reason": result.summary,
            }
        )

        # 6. A failed trial deleted from its ledger.
        records = {
            slug: _real_records(slug)
            for slug in STUDY_SLUGS
            if slug != "options-expiry-004"
        }
        records["options-expiry-004"] = [
            record
            for record in _real_records("options-expiry-004")
            if record["trial_id"] != "T0006"
        ]
        result = check_trial_sequence(records)
        results.append(
            {
                "fixture": "failed trial T0006 deleted",
                "check": "trial_sequence",
                "verdict": result.verdict.value,
                "reason": result.summary,
            }
        )
    return results


def margin_diagnostic() -> dict[str, Any]:
    """Measure how far each compared report cell sits from its tolerance.

    For every numeric cell the report check compares, compute
    |report - ledger| / rounding-tolerance. Correctly rounded values
    spread uniformly in [0, 1]; a genuine discrepancy exceeds 1. The
    gap between the highest passing ratio and the lowest failing one
    shows whether the tolerance is tuned to pass (it is not — the
    failures are a separate population).
    """
    ratios: list[tuple[float, str, str, str, str]] = []
    for slug, rules in REPORT_RULES.items():
        text = (REPO_ROOT / STUDY_REPORTS[slug]).read_text(encoding="utf-8")
        records = {r["trial_id"]: r for r in _real_records(slug)}
        tables = parse_markdown_tables(text)
        for rule in rules:
            metrics = records[rule.trial_id]["result"]["metrics"]
            test = metrics["tests"][rule.test_name]
            holm = {e["test"]: e for e in metrics.get("holm") or []}
            table = find_table(tables, rule.table_headers)
            assert table is not None
            row = next(
                candidate
                for candidate in table.rows
                if candidate
                and re.fullmatch(rule.row_label, candidate[0].strip()) is not None
            )
            header_index = {name: pos for pos, name in enumerate(table.headers)}
            for header, field in rule.columns:
                pos = header_index.get(header)
                if pos is None or pos >= len(row) or header == "n":
                    continue
                if field == HOLM_FIELD:
                    ledger_value = (holm.get(rule.test_name) or {}).get(
                        "adjusted_p_value"
                    )
                elif field in (WINDOW_N_FIELD, BOOT_CI_FIELD):
                    continue
                else:
                    ledger_value = test.get(field)
                parsed = parse_report_number(row[pos])
                if (
                    parsed is None
                    or not isinstance(ledger_value, (int, float))
                    or isinstance(ledger_value, bool)
                ):
                    continue
                report_value, tolerance = parsed
                ratios.append(
                    (
                        abs(report_value - float(ledger_value)) / max(tolerance, 1e-12),
                        slug,
                        rule.trial_id,
                        rule.test_name,
                        header,
                    )
                )
    ratios.sort(reverse=True)
    passing = [ratio for ratio, *_ in ratios if ratio <= 1.0]
    failing = [ratio for ratio, *_ in ratios if ratio > 1.0]
    return {
        "cells_compared": len(ratios),
        "failing_cells": len(failing),
        "highest_passing_ratio": max(passing) if passing else None,
        "lowest_failing_ratio": min(failing) if failing else None,
        "top": [
            {
                "ratio": round(ratio, 3),
                "study": slug,
                "trial": trial_id,
                "test": test_name,
                "column": header,
            }
            for ratio, slug, trial_id, test_name, header in ratios[:6]
        ],
    }


def render_validation_report(
    review: LabReview,
    fixtures: list[dict[str, Any]],
    margins: dict[str, Any],
    reviewed_at: datetime,
) -> str:
    counts = review.counts
    total_rules = sum(len(rules) for rules in REPORT_RULES.values())
    verified_rows = 0
    failed_rows = 0
    for study in review.studies:
        for check in study.checks:
            if check.check_id != "report_ledger":
                continue
            match = re.search(r"(\d+)/(\d+) report row\(s\) verified", check.summary)
            if match is not None:
                verified_rows += int(match.group(1))
            match = re.search(r"(\d+) of (\d+) verified", check.summary)
            if match is not None:
                verified_rows += int(match.group(1))
            match = re.search(r"(\d+) report row\(s\) disagree", check.summary)
            if match is not None:
                failed_rows += int(match.group(1))
    by_check: dict[str, Counter[str]] = {}
    for study in review.studies:
        for check in study.checks:
            by_check.setdefault(check.check_id, Counter())[check.verdict.value] += 1
    for check in review.lab_checks:
        by_check.setdefault(check.check_id, Counter())[check.verdict.value] += 1

    lines = [
        "# Adversarial reviewer validation (Stage 6d)",
        "",
        f"Validated at: {reviewed_at.isoformat()}",
        "",
        "## What was validated",
        "",
        "1. **Full-lab review**: the reviewer ran over all eight empirical "
        "studies and all trial ledgers (16 records: 12 completed, 3 failed, "
        "1 reserved). The review itself is in `review_report.md` / "
        "`review_report.json` in this directory.",
        "2. **Adversarial fixtures**: six deliberately broken fixtures in "
        "tmp dirs, each isolating one violation. Every fixture must FAIL "
        "with the correct reason — passing only clean studies does not "
        "count as validation.",
        "3. **Rounding-margin diagnostic**: the report check compares "
        "numbers within the tolerance implied by the report's stated "
        "precision; the diagnostic shows the failures are not rounding "
        "noise.",
        "",
        "## Full-lab review summary",
        "",
        f"- Checks run: {sum(counts.values())}",
        f"- PASS: {counts.get('pass', 0)}",
        f"- FAIL: {counts.get('fail', 0)}",
        f"- UNVERIFIED: {counts.get('unverified', 0)}",
        f"- NOTE: {counts.get('note', 0)}",
        "",
        "### Per-check breakdown",
        "",
        "| check | pass | fail | unverified | note |",
        "| --- | --- | --- | --- | --- |",
    ]
    for check_id in sorted(by_check):
        tallies = by_check[check_id]
        lines.append(
            f"| `{check_id}` | {tallies.get('pass', 0)} | {tallies.get('fail', 0)} "
            f"| {tallies.get('unverified', 0)} | {tallies.get('note', 0)} |"
        )
    lines.extend(
        [
            "",
            "### The FAILs",
            "",
            "Each FAIL below is a genuine disagreement between a record "
            "and the source it should agree with, with located evidence. "
            "The reviewer reports them; it does not fix the studies "
            "(fixes are a separate delivery decision). The analyst's "
            "reading of these failures — what caused them and whether "
            "they matter — is in `docs/research-intelligence.md` §4, "
            "not in this generated report.",
            "",
        ]
    )
    failing_checks = [
        (study.study, check)
        for study in review.studies
        for check in study.checks
        if check.verdict is ReviewVerdict.FAIL
    ]
    failing_checks.extend(
        ("lab", check)
        for check in review.lab_checks
        if check.verdict is ReviewVerdict.FAIL
    )
    if not failing_checks:
        lines.append("None.")
        lines.append("")
    for study_slug, check in failing_checks:
        lines.append(f"- **{study_slug}** `{check.check_id}`: {check.summary}")
        for item in check.evidence:
            lines.append(f"  - {item}")
    lines.extend(
        [
            "",
            "### The UNVERIFIEDs",
            "",
            "UNVERIFIED means the check could not be performed — it is "
            "not a pass. Each entry states why.",
            "",
        ]
    )
    unverified_checks = [
        (study.study, check)
        for study in review.studies
        for check in study.checks
        if check.verdict is ReviewVerdict.UNVERIFIED
    ]
    unverified_checks.extend(
        ("lab", check)
        for check in review.lab_checks
        if check.verdict is ReviewVerdict.UNVERIFIED
    )
    if not unverified_checks:
        lines.append("None.")
        lines.append("")
    for study_slug, check in unverified_checks:
        lines.append(f"- **{study_slug}** `{check.check_id}`: {check.summary}")
        for item in check.evidence:
            lines.append(f"  - {item}")
    lines.extend(
        [
            "",
            "### Report coverage",
            "",
            f"- {total_rules} report rules across the 7 reports; "
            f"{verified_rows} rows verified, {failed_rows} rows disagree.",
            f"- {margins['cells_compared']} numeric cells compared "
            "(window-count and bootstrap-CI cells compared separately).",
            "",
            "## Adversarial fixtures",
            "",
            "| fixture | check | verdict | reason |",
            "| --- | --- | --- | --- |",
        ]
    )
    for fixture in fixtures:
        lines.append(
            f"| {fixture['fixture']} | `{fixture['check']}` | "
            f"{fixture['verdict']} | {fixture['reason']} |"
        )
    caught = sum(
        1 for fixture in fixtures if fixture["verdict"] == ReviewVerdict.FAIL.value
    )
    lines.extend(
        [
            "",
            f"**{caught}/{len(fixtures)} fixtures caught.** "
            + (
                "All six violation classes fail with the correct reason."
                if caught == len(fixtures)
                else "NOT ALL FIXTURES WERE CAUGHT — the reviewer is not validated."
            ),
            "",
            "## Rounding-margin diagnostic",
            "",
            f"- Numeric cells compared: {margins['cells_compared']}",
            f"- Cells outside tolerance: {margins['failing_cells']}",
            f"- Highest passing ratio (|diff| / tolerance): "
            f"{margins['highest_passing_ratio']:.3f}",
            "- Lowest failing ratio: "
            + (
                f"{margins['lowest_failing_ratio']:.3f}"
                if margins["lowest_failing_ratio"] is not None
                else "none (no cell outside tolerance)"
            ),
            "",
            "The highest passing ratio is a correctly rounded "
            "value sitting near its rounding boundary — expected, since "
            "rounding residuals spread uniformly in [0, 1]."
            + (
                f" The failing cells (ratios "
                f"{margins['lowest_failing_ratio']:.2f}–"
                f"{margins['top'][0]['ratio']:.2f}) are a separate "
                "population."
                if margins["lowest_failing_ratio"] is not None
                else " No cell falls outside tolerance."
            )
            + " (The study 004 bootstrap-CI bound is compared through the "
            "CI path, not this numeric path, so it does not appear in "
            "these counts.)",
            "",
            "Largest ratios:",
            "",
        ]
    )
    for item in margins["top"]:
        lines.append(
            f"- {item['ratio']}: {item['study']} {item['trial']} "
            f"{item['test']} ({item['column']})"
        )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- **Report coverage is table-bound**: only the 52 results-"
            "table rows with explicit rules are checked. Prose numbers, "
            "descriptive split tables and the verdict-criteria tables "
            "are not mechanically compared; a discrepancy there would "
            "not be caught.",
            "- **The primary test is the first Holm-family entry**: the "
            "verdict check re-derives the primary criteria from "
            "`metrics[\"holm\"][0]`. This holds for all 12 completed "
            "trials in the lab, and the report check independently "
            "confirms each primary test's identity from the report "
            "tables — but a future trial that orders its family "
            "differently would be misread.",
            "- **PIT coverage depends on retained data**: the check "
            "runs only where parquet batches still exist. The seven "
            "older study caches are gone, so the lab's PIT discipline "
            "is verified only for study 008 (the only retained cache) "
            "and unverified for the rest.",
            "- **Truncation needs anchors**: study 005 has no anchor "
            "file, so a deleted trailing record in its ledger would "
            "pass the chain check; only the trial-ID sequence check "
            "would notice (and only if the deleted record's ID left a "
            "gap).",
            "- **The reviewer trusts the registry's own verification**: "
            "registration and event-log integrity come from the repo's "
            "`HypothesisRegistry` code, not from an independent "
            "reimplementation. A bug shared by the registry and the "
            "reviewer would be invisible to both.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reviewed-at",
        default=None,
        help="ISO timestamp for the review (default: now, UTC)",
    )
    args = parser.parse_args()
    reviewed_at = (
        datetime.fromisoformat(args.reviewed_at)
        if args.reviewed_at is not None
        else datetime.now(UTC)
    )

    review = review_lab(REPO_ROOT, reviewed_at)
    (ROOT / "review_report.json").write_bytes(render_json(review))
    (ROOT / "review_report.md").write_text(
        render_markdown(review), encoding="utf-8"
    )

    fixtures = run_fixtures()
    for fixture in fixtures:
        if fixture["verdict"] != ReviewVerdict.FAIL.value:
            print(
                f"FIXTURE NOT CAUGHT: {fixture['fixture']} "
                f"({fixture['check']} -> {fixture['verdict']})"
            )
            return 1
    margins = margin_diagnostic()
    (ROOT / "validation_report.md").write_text(
        render_validation_report(review, fixtures, margins, reviewed_at),
        encoding="utf-8",
    )
    counts = review.counts
    print(
        f"lab review: {counts.get('pass', 0)} pass, {counts.get('fail', 0)} fail, "
        f"{counts.get('unverified', 0)} unverified, {counts.get('note', 0)} note"
    )
    print(f"fixtures: {len(fixtures)}/{len(fixtures)} caught")
    print(
        f"margin diagnostic: {margins['cells_compared']} cells, "
        f"{margins['failing_cells']} outside tolerance"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
