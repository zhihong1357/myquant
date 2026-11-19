"""Tests for the Stage 2B lab-wide statistical audit generator.

Two kinds of test live here:

- Pure-function tests on the generator's correction logic, loaded from
  the script with importlib (the script is not a package module).
  These use small fixture p-value lists with hand-computed Holm/BH
  expectations.
- A drift test that runs the full generator into tmp_path (about 25 s:
  the calibration and power simulations use fixed seeds) and compares
  both outputs byte-for-byte with the committed files, plus a
  headline-consistency test that re-reads the committed summary and
  checks its key counts against the registry.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_SCRIPT = REPO_ROOT / "research" / "statistical-audit-2b" / "audit.py"
SUMMARY_PATH = REPO_ROOT / "research" / "statistical-audit-2b" / "summary.json"
REPORT_PATH = REPO_ROOT / "research" / "statistical-audit-2b" / "report.md"
REGISTRY_PATH = REPO_ROOT / "research" / "graph" / "registry.json"


def load_audit_module():
    spec = importlib.util.spec_from_file_location(
        "statistical_audit_2b", AUDIT_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lab_wide_corrections_fixture():
    audit = load_audit_module()
    # Hand-computed Holm/BH for p = (0.001, 0.01, 0.02, 0.04, 0.5), m = 5.
    # Holm: sorted p (0.001, 0.01, 0.02, 0.04, 0.5) x (5, 4, 3, 2, 1)
    #   = (0.005, 0.04, 0.06, 0.08, 0.5), running max -> same.
    # BH: sorted p x m/rank = (0.005, 0.025, 0.0333, 0.05, 0.5), running
    #   min from the largest -> (0.005, 0.025, 0.0333, 0.05, 0.5).
    holm, bh = audit.lab_wide_corrections([0.001, 0.01, 0.02, 0.04, 0.5])
    assert holm == pytest.approx([0.005, 0.04, 0.06, 0.08, 0.5])
    assert bh == pytest.approx([0.005, 0.025, 0.03333333333333333, 0.05, 0.5])


def test_lab_wide_corrections_preserve_input_order():
    audit = load_audit_module()
    holm, bh = audit.lab_wide_corrections([0.5, 0.001, 0.04])
    # Sorted p = (0.001, 0.04, 0.5); Holm = (0.003, 0.08, 0.5);
    # BH = (0.003, 0.06, 0.5). Input order restored.
    assert holm == pytest.approx([0.5, 0.003, 0.08])
    assert bh == pytest.approx([0.5, 0.003, 0.06])


def test_storey_pi0_fixture():
    audit = load_audit_module()
    # Half the p-values above 0.5 -> pi0 = 5 / (10 * 0.5) = 1.0.
    p_values = [0.01, 0.02, 0.03, 0.04, 0.05, 0.6, 0.7, 0.8, 0.9, 0.95]
    assert audit.storey_pi0(p_values) == pytest.approx(1.0)
    # Two above 0.5 -> pi0 = 2 / 5 = 0.4.
    p_values = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.6, 0.7]
    assert audit.storey_pi0(p_values) == pytest.approx(0.4)
    with pytest.raises(ValueError):
        audit.storey_pi0([0.1, 0.2], lambda_value=1.0)


def test_per_study_breakdown_fixture():
    audit = load_audit_module()
    edges = [
        {
            "edge_id": "E0001",
            "status": "rejected",
            "ledger_path": "research/study-a/trials.jsonl",
        },
        {
            "edge_id": "E0002",
            "status": "supported",
            "ledger_path": "research/study-a/trials.jsonl",
        },
        {
            "edge_id": "E0003",
            "status": "supported",
            "ledger_path": "research/study-b/trials.jsonl",
        },
    ]
    rows = audit.per_study_breakdown(
        edges, [0.9, 0.04, 0.2], [0.9, 0.03, 0.15]
    )
    by_study = {row["study"]: row for row in rows}
    assert by_study["study-a"]["tested_edges"] == 2
    assert by_study["study-a"]["supported_edges"] == 1
    assert by_study["study-a"]["holm_survivors"] == 1
    assert by_study["study-a"]["bh_survivors"] == 1
    assert by_study["study-b"]["holm_survivors"] == 0
    assert by_study["study-b"]["bh_survivors"] == 0
    assert by_study["study-b"]["max_holm_adjusted_p_supported"] == pytest.approx(0.2)


def run_audit(tmp_path: Path) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    summary_out = tmp_path / "summary.json"
    report_out = tmp_path / "report.md"
    result = subprocess.run(
        [
            sys.executable,
            str(AUDIT_SCRIPT),
            "--repo-root",
            str(REPO_ROOT),
            "--summary-out",
            str(summary_out),
            "--report-out",
            str(report_out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return summary_out, report_out


def test_audit_output_matches_committed_files(tmp_path: Path):
    if not SUMMARY_PATH.exists() or not REPORT_PATH.exists():
        pytest.skip("committed audit outputs not generated yet")
    summary_out, report_out = run_audit(tmp_path)
    assert summary_out.read_bytes() == SUMMARY_PATH.read_bytes()
    assert report_out.read_bytes() == REPORT_PATH.read_bytes()


def test_audit_summary_headlines_match_registry():
    if not SUMMARY_PATH.exists():
        pytest.skip("committed audit outputs not generated yet")
    summary = json.loads(SUMMARY_PATH.read_text())
    registry = json.loads(REGISTRY_PATH.read_text())
    lab = summary["lab_wide_audit"]
    tested = [
        edge
        for edge in registry["edges"]
        if edge["status"] in ("supported", "rejected")
    ]
    supported = [edge for edge in tested if edge["status"] == "supported"]
    assert lab["family_size"] == len(tested) == 41
    assert lab["supported_total"] == len(supported) == 6
    assert lab["registry_content_hash"] == registry["content_hash"]
    # The summary's supported-edge rows must be exactly the registry's
    # supported edges, with matching raw p-values.
    by_id = {row["edge_id"]: row for row in lab["supported_edges"]}
    assert set(by_id) == {edge["edge_id"] for edge in supported}
    for edge in supported:
        assert by_id[edge["edge_id"]]["raw_p_value"] == edge["p_value"]
    # Headline counts are internally consistent.
    assert lab["holm_survivors"] == sum(
        1 for row in lab["supported_edges"] if row["holm_significant"]
    )
    assert lab["bh_survivors"] == sum(
        1 for row in lab["supported_edges"] if row["bh_significant"]
    )
    assert lab["expected_false_positives_uncorrected"] == pytest.approx(
        lab["family_size"] * lab["alpha"]
    )
    # The report must carry the scope disclaimer and the headline counts.
    report = REPORT_PATH.read_text()
    assert "does NOT change any preregistered verdict" in report
    assert f"**{lab['holm_survivors']} of {lab['supported_total']}**" in report
    assert f"**{lab['bh_survivors']} of {lab['supported_total']}**" in report
