"""Tests for the research librarian (Stage 6e). All offline, zero network.

Two kinds of fixture: the lab's real records (read-only) and broken
copies built in tmp dirs (a copied research/ + docs/ tree with one
record damaged). Number-derivation tests read the raw ledgers with
plain json and compare against the catalog — no expected number is
typed in by hand.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from myquant.librarian import (
    AvailabilityRef,
    TemplateRef,
    build_catalog,
    check_audit_links,
    check_availability_links,
    check_candidate_links,
    check_decision_record_links,
    check_edge_links,
    check_hypothesis_trials,
    check_review_links,
    check_source_used_by,
    check_study_reports,
    check_template_links,
    check_trial_sequence,
    fmt_num,
    render_catalog_json,
    render_lab_report_json,
    render_lab_report_markdown,
)
from myquant.librarian.models import (
    CandidateEntry,
    DecisionRecordEntry,
    EdgeEntry,
    HypothesisEntry,
    StudyEntry,
    TrialEntry,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILDER = REPO_ROOT / "research" / "library-6e" / "build_library.py"
LIBRARY_DIR = REPO_ROOT / "research" / "library-6e"
GENERATED_AT = datetime(2026, 11, 19, tzinfo=UTC)

# Primary-effect fields by test type, stated here independently of the
# librarian's own mapping (same convention: the first Holm-family entry
# is the primary test).
EFFECT_FIELDS: dict[str, tuple[str, str | None]] = {
    "lead_lag": ("coefficient", "partial_r_squared"),
    "event_study": ("standardized_mean_car", "coefficient"),
    "cross_section": ("coefficient", "r_squared"),
    "mean_comparison": ("effect_ratio", None),
}


def _catalog():
    return build_catalog(REPO_ROOT, GENERATED_AT)


def _copy_lab(tmp_path: Path) -> Path:
    """Copy the data the librarian reads into a tmp repo root."""
    root = tmp_path / "repo"
    shutil.copytree(REPO_ROOT / "research", root / "research")
    shutil.copytree(REPO_ROOT / "docs", root / "docs")
    return root


def _trial_entry(
    trial_id: str, test_keys: tuple[str, ...] = ()
) -> TrialEntry:
    return TrialEntry(
        trial_id=trial_id,
        study="btc-eth-001",
        hypothesis_id="H0001",
        status="completed",
        record_hash="a" * 64,
        recorded_at="2026-11-18T00:00:00+00:00",
        test_keys=test_keys,
    )


def _edge_entry(
    edge_id: str = "E0001",
    trial_id: str | None = "T0001",
    test_key: str | None = "daily_btc_eth",
    status: str = "rejected",
) -> EdgeEntry:
    return EdgeEntry(
        edge_id=edge_id,
        source_instrument="crypto:btc-usdt-perp",
        target_instrument="crypto:eth-usdt-perp",
        status=status,
        hypothesis_id="H0001",
        trial_id=trial_id,
        ledger_test_key=test_key,
        test_type="lead_lag",
        report_path="docs/studies/btc-eth-transmission-001.md",
        ledger_path="research/btc-eth-001/trials.jsonl",
    )


# --- Counts on the real records ----------------------------------------


def test_catalog_counts_match_known_lab_state() -> None:
    catalog = _catalog()
    assert catalog.counts == {
        "studies": 12,
        "hypotheses": 17,
        "hypothesis_versions": 19,
        "trials_total": 19,
        "trials_completed": 16,
        "trials_failed": 3,
        "trials_reserved": 1,
        "nodes": 12,
        "edges_total": 44,
        "edges_supported": 6,
        "edges_rejected": 35,
        "edges_pending": 1,
        "edges_descriptive": 2,
        "decision_records": 20,
        "candidates_total": 118,
        "candidates_ranked": 106,
        "candidates_unrankable": 12,
        "templates": 10,
        "sources": 8,
        "panels": 12,
        "broken_links": 0,
        "missing_optional": 1,
    }


def test_catalog_trials_and_reservation() -> None:
    catalog = _catalog()
    assert catalog.reserved_trial_ids == ("T0003",)
    failed = [t.trial_id for t in catalog.trials if t.status == "failed"]
    assert failed == ["T0006", "T0008", "T0014"]
    for trial in catalog.trials:
        if trial.status == "failed":
            assert trial.supported is None
            assert trial.primary_test is None
            assert trial.failure_reason
        else:
            assert trial.primary_test is not None
            assert trial.primary_effect_value is not None
            assert trial.primary_adjusted_p_value is not None
            assert trial.observations is not None


def test_catalog_hypotheses_and_states() -> None:
    catalog = _catalog()
    by_id = {h.hypothesis_id: h for h in catalog.hypotheses}
    assert by_id["H0003"].latest_state == "registered"
    assert by_id["H0003"].trials == ()
    assert by_id["H0003"].edges == ("E0011",)
    assert by_id["H0004"].latest_state == "rejected"
    assert len(by_id["H0004"].versions) == 2
    assert by_id["H0010"].latest_state == "supported"
    assert by_id["H0011"].latest_state == "supported"
    supported = [
        h.hypothesis_id
        for h in catalog.hypotheses
        if h.latest_state == "supported"
    ]
    assert supported == ["H0010", "H0011"]


def test_catalog_studies_open_and_closed() -> None:
    catalog = _catalog()
    by_slug = {s.slug: s for s in catalog.studies}
    assert by_slug["lowvol-002"].status == "open"
    assert all(
        s.status == "closed"
        for s in catalog.studies
        if s.slug != "lowvol-002"
    )
    for study in catalog.studies:
        assert study.report_exists, study.slug
    assert by_slug["fomc-event-study-005"].anchor_present is False
    assert all(
        s.anchor_present for s in catalog.studies if s.slug != "fomc-event-study-005"
    )


def test_catalog_edges_link_to_decision_records_and_audit() -> None:
    catalog = _catalog()
    by_id = {e.edge_id: e for e in catalog.edges}
    assert by_id["E0023"].decision_record_id == "DR-E0023"
    assert by_id["E0001"].decision_record_id == "DR-H0001"
    assert by_id["E0023"].holm_significant is True
    assert by_id["E0023"].bh_significant is True
    assert by_id["E0030"].holm_significant is False
    assert by_id["E0030"].bh_significant is False
    assert by_id["E0031"].holm_significant is False
    assert by_id["E0031"].bh_significant is True
    # E0033 flipped out of the Holm survivor set when the family grew
    # to 38 (Holm p 0.04971 -> 0.05117); at family 41 its Holm p is
    # 0.05556 and it still survives under BH (BH p 0.01499).
    assert by_id["E0033"].holm_significant is False
    assert by_id["E0033"].bh_significant is True
    assert by_id["E0026"].audit_caveat is not None
    assert "mechanical" in by_id["E0026"].audit_caveat
    assert catalog.audit is not None
    assert catalog.audit.family_size == 41
    assert catalog.audit.holm_survivors == 3
    assert catalog.audit.bh_survivors == 5


def test_pending_edge_carries_forward_sample() -> None:
    catalog = _catalog()
    pending = [e for e in catalog.edges if e.status == "pending"]
    assert [e.edge_id for e in pending] == ["E0011"]
    sample = pending[0].forward_sample
    assert sample is not None
    assert sample.observed_lowvol_rows == 0
    assert sample.minimum_lowvol_rows == 60
    assert sample.ready is False


def test_catalog_candidates_and_templates() -> None:
    catalog = _catalog()
    ranked = [c for c in catalog.candidates if c.ranked]
    assert [c.rank for c in ranked[:10]] == list(range(1, 11))
    assert all(c.has_template for c in ranked[:10])
    assert not any(c.has_template for c in ranked[10:])
    unrankable = [c for c in catalog.candidates if not c.ranked]
    assert len(unrankable) == 12
    assert all("index:tyvix" in (c.source_instrument, c.target_instrument) for c in unrankable)
    tiers = {}
    for candidate in ranked:
        tiers[candidate.total_score] = tiers.get(candidate.total_score, 0) + 1
    assert tiers == {1.0: 30, 0.8: 9, 0.7: 47, 0.6: 2, 0.5: 18}


def test_catalog_sources_and_panels() -> None:
    catalog = _catalog()
    by_id = {s.source_id: s for s in catalog.sources}
    assert by_id["bls"].probe_kind == "manual-only"
    assert by_id["bls"].probe_skip == 1
    assert by_id["fred"].probe_pass == 13
    total_quirks = sum(s.quirks for s in catalog.sources)
    assert total_quirks == 41
    total_recorded_only = sum(s.recorded_only for s in catalog.sources)
    assert total_recorded_only == 33
    fresh = [p for p in catalog.panels if p.status == "fresh"]
    stale = [p for p in catalog.panels if p.status != "fresh"]
    assert len(fresh) == 5
    assert len(stale) == 7
    vxn = next(p for p in catalog.panels if p.instrument_id == "index:vxn")
    assert vxn.days_behind == 2377
    assert catalog.evidence_probed_at.startswith("2026-11-18T21:45")
    assert len(catalog.post_probe_updates) == 1
    assert catalog.post_probe_updates[0].instrument_id == "index:vxn"
    assert "2026-11-17" in catalog.post_probe_updates[0].note


def test_catalog_review_summary_quoted() -> None:
    catalog = _catalog()
    assert catalog.review is not None
    assert catalog.review.counts == {
        "fail": 0,
        "note": 16,
        "pass": 120,
        "unverified": 8,
    }
    assert len(catalog.review.unverified_items) == 8
    assert catalog.review.reviewed_at == "2026-11-19T15:50:38.164512Z"


# --- Integrity: the real lab has no broken links ------------------------


def test_no_broken_links_on_real_lab() -> None:
    catalog = _catalog()
    assert catalog.broken_links == ()


def test_missing_optional_is_only_the_study_005_anchor() -> None:
    catalog = _catalog()
    assert [m.path for m in catalog.missing_optional] == [
        "research/fomc-event-study-005/trials.jsonl.anchor"
    ]


# --- Number derivation: catalog vs raw ledgers --------------------------


def test_trial_numbers_derive_from_raw_ledgers() -> None:
    """Re-derive every completed trial's primary numbers from the raw
    ledger files (plain json, no librarian code) and compare."""
    catalog = _catalog()
    registry = json.loads(
        (REPO_ROOT / "research" / "graph" / "registry.json").read_text()
    )
    test_types = {
        (e["trial_id"], e["ledger_test_key"]): e["test_type"]
        for e in registry["edges"]
        if e.get("trial_id") and e.get("ledger_test_key")
    }
    checked = 0
    for trial in catalog.trials:
        if trial.status != "completed":
            continue
        ledger = (
            REPO_ROOT / "research" / trial.study / "trials.jsonl"
        ).read_text()
        record = next(
            json.loads(line)
            for line in ledger.splitlines()
            if json.loads(line)["trial_id"] == trial.trial_id
        )
        metrics = record["result"]["metrics"]
        primary = metrics["holm"][0]
        test_type = test_types[(trial.trial_id, primary["test"])]
        effect_field, secondary_field = EFFECT_FIELDS[test_type]
        test = metrics["tests"][primary["test"]]
        assert trial.primary_test == primary["test"]
        assert trial.primary_test_type == test_type
        assert trial.primary_effect_value == test[effect_field]
        assert trial.primary_adjusted_p_value == primary["adjusted_p_value"]
        assert trial.primary_raw_p_value == primary["raw_p_value"]
        assert trial.observations == test["observations"]
        assert trial.supported == metrics["verdict"]["supported"]
        if secondary_field is not None:
            assert trial.secondary_effect_value == test[secondary_field]
        checked += 1
    assert checked == 16


def test_fmt_num_keeps_significant_digits() -> None:
    assert fmt_num(None) == "—"
    assert fmt_num(1.0000634084216993) == "1.00006"
    assert fmt_num(1.0) == "1"
    assert fmt_num(5.201439834401356e-09) == "5.20144e-09"


# --- Determinism and drift ----------------------------------------------


def test_build_is_deterministic_for_one_timestamp() -> None:
    first = build_catalog(REPO_ROOT, GENERATED_AT)
    second = build_catalog(REPO_ROOT, GENERATED_AT)
    assert render_catalog_json(first) == render_catalog_json(second)
    assert render_lab_report_json(first) == render_lab_report_json(second)
    assert render_lab_report_markdown(first) == render_lab_report_markdown(second)


def _run_builder(out_dir: Path, generated_at: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            sys.executable,
            str(BUILDER),
            "--repo-root",
            str(REPO_ROOT),
            "--generated-at",
            generated_at,
            "--out-dir",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_builder_is_deterministic(tmp_path: Path) -> None:
    _run_builder(tmp_path / "a", "2026-11-19T00:00:00+00:00")
    _run_builder(tmp_path / "b", "2026-11-19T00:00:00+00:00")
    for name in ("catalog.json", "lab_report.md", "lab_report.json"):
        assert (tmp_path / "a" / name).read_bytes() == (
            tmp_path / "b" / name
        ).read_bytes()


def test_committed_artifacts_match_fresh_rebuild(tmp_path: Path) -> None:
    """Drift test: the committed artifacts must equal a fresh rebuild
    with the committed timestamp."""
    committed = json.loads(
        (LIBRARY_DIR / "catalog.json").read_text(encoding="utf-8")
    )
    _run_builder(tmp_path, committed["generated_at"])
    for name in ("catalog.json", "lab_report.md", "lab_report.json"):
        assert (tmp_path / name).read_bytes() == (
            LIBRARY_DIR / name
        ).read_bytes(), name


def test_lab_report_markdown_states_zero_broken_links() -> None:
    catalog = _catalog()
    text = render_lab_report_markdown(catalog)
    assert "0 broken links" in text
    assert "## Studies" in text
    assert "## Graph" in text
    assert "## Candidate queue" in text
    assert "## Data freshness" in text
    assert "## Review status (6d, quoted)" in text
    assert "## Pending items" in text
    assert "## Integrity" in text
    assert "## Sources" in text
    assert "T0003" in text
    assert "H0003" in text
    assert "not a tradeable signal" in text


# --- Integrity checks: synthetic unit tests ------------------------------


def test_edge_link_fails_when_trial_deleted() -> None:
    edge = _edge_entry()
    broken = check_edge_links(
        (edge,), (), (), ("crypto:btc-usdt-perp", "crypto:eth-usdt-perp"), REPO_ROOT
    )
    kinds = {b.kind for b in broken}
    assert "edge_trial" in kinds
    assert "edge_hypothesis" in kinds


def test_edge_link_fails_when_test_key_missing() -> None:
    edge = _edge_entry()
    trial = _trial_entry("T0001", test_keys=("daily_btc_sol",))
    broken = check_edge_links(
        (edge,),
        (trial,),
        (HypothesisEntry(hypothesis_id="H0001", study="btc-eth-001", latest_state="rejected"),),
        ("crypto:btc-usdt-perp", "crypto:eth-usdt-perp"),
        REPO_ROOT,
    )
    assert [b.kind for b in broken] == ["edge_test_key"]


def test_pending_and_descriptive_edges_need_no_test_key() -> None:
    pending = _edge_entry(
        edge_id="E0011", trial_id=None, test_key=None, status="pending"
    )
    descriptive = _edge_entry(
        edge_id="E0013", trial_id="T0001", test_key=None, status="descriptive"
    )
    broken = check_edge_links(
        (pending, descriptive),
        (_trial_entry("T0001"),),
        (HypothesisEntry(hypothesis_id="H0001", study="btc-eth-001", latest_state="rejected"),),
        ("crypto:btc-usdt-perp", "crypto:eth-usdt-perp"),
        REPO_ROOT,
    )
    assert broken == []


def test_decision_record_link_fails_on_wrong_edge_id() -> None:
    record = DecisionRecordEntry(
        record_id="DR-E9999",
        record_type="edge",
        study="btc-eth-001",
        hypothesis_id="H0001",
        edge_id="E9999",
        conclusion="SUPPORTED",
        trial_id="T0001",
        report_path="docs/studies/btc-eth-transmission-001.md",
        ledger_path="research/btc-eth-001/trials.jsonl",
    )
    broken = check_decision_record_links(
        (record,),
        (_edge_entry(),),
        (HypothesisEntry(hypothesis_id="H0001", study="btc-eth-001", latest_state="rejected"),),
        (_trial_entry("T0001"),),
        (StudyEntry(slug="btc-eth-001"),),
        REPO_ROOT,
    )
    assert [b.kind for b in broken] == ["record_edge"]
    assert broken[0].referenced == "E9999"


def test_template_link_fails_on_rank_mismatch() -> None:
    candidate = CandidateEntry(
        source_instrument="credit:baa-10y-spread",
        target_instrument="index:sp500",
        ranked=True,
        rank=1,
    )
    template = TemplateRef(
        source_instrument="credit:baa-10y-spread",
        target_instrument="index:sp500",
        rank=2,
        filename="credit-baa-10y-spread__index-sp500.json",
    )
    broken = check_template_links((template,), (candidate,))
    assert [b.kind for b in broken] == ["template_rank"]


def test_candidate_link_fails_when_not_in_registry() -> None:
    candidate = CandidateEntry(
        source_instrument="credit:baa-10y-spread",
        target_instrument="index:sp500",
        ranked=True,
        rank=1,
    )
    broken = check_candidate_links(
        (candidate,),
        (("crypto:btc-usdt-perp", "crypto:eth-usdt-perp"),),
        ("credit:baa-10y-spread", "index:sp500"),
    )
    assert [b.kind for b in broken] == ["candidate_registry"]


def test_trial_sequence_flags_unreserved_gap() -> None:
    trials = (_trial_entry("T0001"), _trial_entry("T0003"))
    broken = check_trial_sequence(trials, ())
    assert [b.referenced for b in broken] == ["T0002"]
    assert check_trial_sequence(trials, ("T0002",)) == []


def test_hypothesis_without_trial_needs_pending_edge_or_open_state() -> None:
    orphan = HypothesisEntry(
        hypothesis_id="H0099", study="btc-eth-001", latest_state="rejected"
    )
    broken = check_hypothesis_trials((orphan,), ())
    assert [b.kind for b in broken] == ["hypothesis_no_trial"]
    pending_edge = _edge_entry(
        edge_id="E0099", trial_id=None, test_key=None, status="pending"
    )
    pending_edge = pending_edge.model_copy(
        update={"hypothesis_id": "H0099"}
    )
    assert check_hypothesis_trials((orphan,), (pending_edge,)) == []
    open_hyp = orphan.model_copy(update={"latest_state": "registered"})
    assert check_hypothesis_trials((open_hyp,), ()) == []


def test_review_link_flags_uncovered_study() -> None:
    studies = (
        StudyEntry(slug="btc-eth-001"),
        StudyEntry(slug="lowvol-002"),
    )
    broken = check_review_links(("btc-eth-001",), studies)
    assert [(b.kind, b.referenced) for b in broken] == [
        ("review_coverage", "lowvol-002")
    ]
    broken = check_review_links(("btc-eth-001", "no-such-study"), studies)
    assert ("review_study", "no-such-study") in [
        (b.kind, b.referenced) for b in broken
    ]


def test_audit_link_flags_unknown_edge() -> None:
    broken = check_audit_links(("E9999",), (_edge_entry(),))
    assert [b.kind for b in broken] == ["audit_edge"]


def test_availability_link_flags_missing_file_and_node() -> None:
    ref = AvailabilityRef(
        instrument_id="index:nope",
        verified_by_paths=("research/nope/panel-summary.json",),
    )
    broken = check_availability_links(
        (ref,), ("crypto:btc-usdt-perp",), REPO_ROOT
    )
    assert {b.kind for b in broken} == {
        "availability_node",
        "availability_source",
    }


def test_source_used_by_flags_unknown_directory() -> None:
    broken = check_source_used_by(
        (("okx-public", "no-such-study"),), REPO_ROOT
    )
    assert [b.kind for b in broken] == ["source_used_by"]
    assert check_source_used_by(
        (("okx-public", "btc-eth-001"),), REPO_ROOT
    ) == []
    # Annotations after the slug are not part of the directory name.
    assert check_source_used_by(
        (("hyperliquid", "lowvol-002 (preparation only)"),), REPO_ROOT
    ) == []


def test_study_report_flags_missing_report() -> None:
    broken = check_study_reports(
        (StudyEntry(slug="btc-eth-001", report_path=None),)
    )
    assert [b.kind for b in broken] == ["study_report"]
    broken = check_study_reports(
        (
            StudyEntry(
                slug="btc-eth-001",
                report_path="docs/studies/no-such-report.md",
                report_exists=False,
            ),
        )
    )
    assert [b.kind for b in broken] == ["study_report"]


# --- Integrity checks: broken copies of the real lab --------------------


def test_broken_copy_deleted_trial_record(tmp_path: Path) -> None:
    root = _copy_lab(tmp_path)
    ledger = root / "research" / "btc-eth-001" / "trials.jsonl"
    lines = ledger.read_text().splitlines()
    assert len(lines) == 1  # study 001 has a single trial record
    ledger.write_text("", encoding="utf-8")
    catalog = build_catalog(root, GENERATED_AT)
    kinds = {(b.kind, b.referenced) for b in catalog.broken_links}
    assert ("edge_trial", "T0001") in kinds
    assert ("record_trial", "T0001") in kinds
    assert ("trial_gap", "T0001") in kinds


def test_broken_copy_wrong_decision_record_edge(tmp_path: Path) -> None:
    root = _copy_lab(tmp_path)
    path = root / "research" / "decision-records" / "records" / "DR-E0023.json"
    data = json.loads(path.read_text())
    data["edge_id"] = "E9999"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    catalog = build_catalog(root, GENERATED_AT)
    matches = [
        b
        for b in catalog.broken_links
        if b.kind == "record_edge" and b.referenced == "E9999"
    ]
    assert len(matches) == 1
    assert matches[0].referrer == "decision record DR-E0023"


def test_missing_optional_file_does_not_crash_build(tmp_path: Path) -> None:
    root = _copy_lab(tmp_path)
    (root / "research" / "lowvol-002" / "panel-summary.json").unlink()
    (root / "research" / "lowvol-002" / "manifest.json").unlink()
    catalog = build_catalog(root, GENERATED_AT)
    missing = {m.path for m in catalog.missing_optional}
    assert "research/lowvol-002/panel-summary.json" in missing
    assert "research/lowvol-002/manifest.json" in missing
    assert catalog.counts["studies"] == 12
    study = next(s for s in catalog.studies if s.slug == "lowvol-002")
    assert study.panel_summary_present is False
    assert study.manifest_present is False
