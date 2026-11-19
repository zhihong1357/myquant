"""Tests for the Stage 2B statistical decision records.

Two independent verifications:

- Drift test: run the builder into tmp_path and compare all 15 records
  byte-for-byte with the committed files.
- Ledger-consistency test: re-read every committed record's key numbers
  (p-value, effect size, n, verdict criteria, fingerprint, trial hash)
  against its trial ledger and the registry, without running the
  builder. This catches a builder bug that writes wrong numbers
  deterministically, which the drift test alone would miss.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILDER = REPO_ROOT / "research" / "decision-records" / "build_decision_records.py"
RECORDS_DIR = REPO_ROOT / "research" / "decision-records" / "records"
REGISTRY_PATH = REPO_ROOT / "research" / "graph" / "registry.json"
AUDIT_SUMMARY_PATH = (
    REPO_ROOT / "research" / "statistical-audit-2b" / "summary.json"
)

EXPECTED_RECORD_IDS = {
    "DR-E0023",
    "DR-E0026",
    "DR-E0030",
    "DR-E0031",
    "DR-E0032",
    "DR-E0033",
    "DR-H0001",
    "DR-H0002",
    "DR-H0004",
    "DR-H0005",
    "DR-H0006",
    "DR-H0007",
    "DR-H0008",
    "DR-H0009",
    "DR-H0012",
    "DR-H0013",
    "DR-H0014",
}

# Numeric fields that must match the ledger test record exactly, per type.
NUMERIC_FIELDS = {
    "lead_lag": (
        "coefficient",
        "standard_error",
        "t_statistic",
        "p_value",
        "partial_r_squared",
        "observations",
    ),
    "cross_section": (
        "coefficient",
        "standard_error",
        "t_statistic",
        "p_value",
        "r_squared",
        "observations",
    ),
    "event_study": (
        "coefficient",
        "standardized_mean_car",
        "standard_error",
        "t_statistic",
        "p_value",
        "observations",
    ),
    "mean_comparison": (
        "coefficient",
        "effect_ratio",
        "mean_window",
        "mean_nonwindow",
        "window_observations",
        "nonwindow_observations",
        "standard_error",
        "t_statistic",
        "p_value",
        "bootstrap_ci_lower",
        "bootstrap_ci_upper",
    ),
}


def load_trial(ledger_path: str, trial_id: str) -> dict:
    for line in (REPO_ROOT / ledger_path).read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record["trial_id"] == trial_id:
            return record
    raise AssertionError(f"trial {trial_id} not found in {ledger_path}")


def test_expected_record_set_exists():
    actual = {path.stem for path in RECORDS_DIR.glob("DR-*.json")}
    assert actual == EXPECTED_RECORD_IDS


def test_builder_output_matches_committed_records(tmp_path: Path):
    out_dir = tmp_path / "records"
    result = subprocess.run(
        [
            sys.executable,
            str(BUILDER),
            "--repo-root",
            str(REPO_ROOT),
            "--out-dir",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    built = {path.name for path in out_dir.glob("DR-*.json")}
    committed = {path.name for path in RECORDS_DIR.glob("DR-*.json")}
    assert built == committed
    for name in sorted(committed):
        assert (out_dir / name).read_bytes() == (RECORDS_DIR / name).read_bytes()


def test_records_match_ledgers_and_registry():
    registry = json.loads(REGISTRY_PATH.read_text())
    edges_by_id = {edge["edge_id"]: edge for edge in registry["edges"]}
    audit_summary = json.loads(AUDIT_SUMMARY_PATH.read_text())
    audit_rows = {
        row["edge_id"]: row
        for row in audit_summary["lab_wide_audit"]["supported_edges"]
    }
    for path in sorted(RECORDS_DIR.glob("DR-*.json")):
        record = json.loads(path.read_text())
        assert record["schema_version"] == 1
        assert record["record_id"] == path.stem
        trial = load_trial(record["ledger_path"], record["trial_id"])
        assert trial["status"] == "completed"
        # Identity bindings: fingerprint and trial hash.
        assert (
            trial["result"]["spec"]["hypothesis_fingerprint"]
            == record["preregistration_fingerprint"]
        )
        assert trial["record_hash"] == record["trial_record_hash"]
        assert trial["hypothesis_id"] == record["hypothesis_id"]
        # Verdict: conclusion and criteria match the ledger exactly.
        verdict = trial["result"]["metrics"]["verdict"]
        assert record["evidence"]["verdict_supported"] == verdict["supported"]
        assert record["evidence"]["verdict_criteria"] == verdict["criteria"]
        if record["record_type"] == "rejected_hypothesis":
            assert record["conclusion"] == "REJECTED"
            assert not verdict["supported"]
        else:
            # A supported edge may belong to a rejected hypothesis
            # (secondary edge); the record's conclusion is about the edge.
            assert record["conclusion"] == "SUPPORTED"
            edge = edges_by_id[record["edge_id"]]
            assert edge["status"] == "supported"
        # Primary test numbers match the ledger test record exactly.
        primary = record["evidence"]["primary_test"]
        ledger_test = trial["result"]["metrics"]["tests"][primary["test_key"]]
        for field in NUMERIC_FIELDS[primary["test_type"]]:
            if field in ledger_test and ledger_test[field] is not None:
                assert primary[field] == ledger_test[field], (
                    f"{record['record_id']} {field}: "
                    f"{primary[field]} != {ledger_test[field]}"
                )
        # Within-study Holm adjusted p matches the ledger's holm list.
        holm_entry = next(
            entry
            for entry in trial["result"]["metrics"]["holm"]
            if entry["test"] == primary["test_key"]
        )
        assert (
            primary["within_study_holm_adjusted_p_value"]
            == holm_entry["adjusted_p_value"]
        )
        assert primary["within_study_holm_reject"] == holm_entry["reject"]
        # Family tests match the ledger's holm list exactly.
        family = record["evidence"]["family_tests"]
        assert {row["test_key"] for row in family} == {
            entry["test"] for entry in trial["result"]["metrics"]["holm"]
        }
        for row in family:
            entry = next(
                e
                for e in trial["result"]["metrics"]["holm"]
                if e["test"] == row["test_key"]
            )
            assert row["raw_p_value"] == entry["raw_p_value"]
            assert row["holm_adjusted_p_value"] == entry["adjusted_p_value"]
            assert row["reject"] == entry["reject"]
        # Holdout OOS and cost gate match the ledger where present.
        walk_forward = trial["result"]["metrics"].get("walk_forward")
        if walk_forward:
            for key, value in record["evidence"]["holdout_oos"].items():
                assert walk_forward[key] == value
        cost_gate = record["evidence"]["cost_gate"]
        if cost_gate is not None:
            ledger_cost = trial["result"]["metrics"][cost_gate["kind"]]
            for key, value in cost_gate.items():
                if key != "kind":
                    assert ledger_cost[key] == value
        # Supported edges: lab-wide values match the audit summary.
        if record["record_type"] == "supported_edge":
            lab_wide = record["evidence"]["lab_wide"]
            audit_row = audit_rows[record["edge_id"]]
            assert (
                lab_wide["holm_adjusted_p_value"]
                == audit_row["holm_adjusted_p_value"]
            )
            assert lab_wide["bh_adjusted_p_value"] == audit_row["bh_adjusted_p_value"]
            assert lab_wide["holm_significant"] == audit_row["holm_significant"]
            assert lab_wide["bh_significant"] == audit_row["bh_significant"]
        # Every record carries limitations and audit notes.
        assert record["limitations"], record["record_id"]
        assert record["audit_notes"], record["record_id"]
