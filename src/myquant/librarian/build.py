"""Build the unified lab catalog from committed records (Stage 6e).

The builder is read-only: it scans registrations, trial ledgers, the
graph registry, decision records, planner output, the evidence
registry, the 6d review report and the 2B audit summary, and assembles
a Catalog. Every number is read from a record; nothing is transcribed
by hand. Missing *required* files are an error (a catalog without the
graph registry would be meaningless); missing *optional* files (ledger
anchors, manifests, panel summaries) are recorded in
`missing_optional` and the build continues.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from myquant.hypotheses import HypothesisRegistry
from myquant.librarian import integrity
from myquant.librarian.models import (
    AuditSummary,
    BrokenLink,
    CandidateEntry,
    Catalog,
    DecisionRecordEntry,
    EdgeEntry,
    ForwardSampleEntry,
    HypothesisEntry,
    HypothesisVersionEntry,
    MissingOptional,
    NodeEntry,
    PanelEntry,
    PostProbeUpdate,
    ReviewSummary,
    SourceEntry,
    StudyEntry,
    TrialEntry,
)

REGISTRY_PATH = "research/graph/registry.json"
RANKING_PATH = "research/planner-6a/ranking.json"
AVAILABILITY_PATH = "research/planner-6a/data_availability.json"
TEMPLATES_DIR = "research/planner-6a/templates"
DECISION_RECORDS_DIR = "research/decision-records/records"
SOURCES_PATH = "research/evidence-6b/sources.json"
EVIDENCE_REPORT_PATH = "research/evidence-6b/evidence_report.json"
PANEL_FRESHNESS_PATH = "research/evidence-6b/panel_freshness.json"
REVIEW_REPORT_PATH = "research/review-6d/review_report.json"
AUDIT_SUMMARY_PATH = "research/statistical-audit-2b/summary.json"
VXN_REFRESH_PATH = "research/planner-6a/vxn_refresh.json"

# Effect extraction by test type: (effect field, effect label,
# secondary field, secondary label). The primary test is the first
# entry of the trial's recorded Holm family.
EFFECT_FIELDS: dict[str, tuple[str, str, str | None, str | None]] = {
    "lead_lag": ("coefficient", "coef", "partial_r_squared", "partial R²"),
    "event_study": (
        "standardized_mean_car",
        "std mean CAR",
        "coefficient",
        "mean CAR",
    ),
    "cross_section": ("coefficient", "slope", "r_squared", "R²"),
    "mean_comparison": ("effect_ratio", "effect ratio", None, None),
}

PATH_TOKEN = re.compile(r"(research/[A-Za-z0-9_./-]+\.json)")


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return data


def _read_json_lines(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


class _Builder:
    """Assembles a Catalog, tracking every source file read."""

    def __init__(self, repo_root: Path, generated_at: datetime) -> None:
        self.repo_root = repo_root
        self.generated_at = generated_at
        self.source_files: set[str] = set()
        self.missing_optional: list[MissingOptional] = []
        self.broken_links: list[BrokenLink] = []

    def _rel(self, path: Path) -> str:
        return path.relative_to(self.repo_root).as_posix()

    def _load_json(self, rel_path: str) -> dict[str, Any]:
        path = self.repo_root / rel_path
        self.source_files.add(rel_path)
        return _read_json(path)

    def _load_json_optional(self, rel_path: str) -> dict[str, Any] | None:
        path = self.repo_root / rel_path
        if not path.is_file():
            return None
        self.source_files.add(rel_path)
        return _read_json(path)

    def _note_missing(self, rel_path: str, reason: str) -> None:
        self.missing_optional.append(
            MissingOptional(path=rel_path, reason=reason)
        )

    # -- studies, hypotheses, trials -----------------------------------

    def _study_slugs(self) -> list[str]:
        slugs = sorted(
            p.parent.name
            for p in (self.repo_root / "research").glob("*/trials.jsonl")
        )
        return slugs

    def _load_trials(
        self, slug: str
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Load one study's ledger records (unparseable lines are
        recorded as broken links, not fatal)."""
        rel_path = f"research/{slug}/trials.jsonl"
        path = self.repo_root / rel_path
        self.source_files.add(rel_path)
        records: list[dict[str, Any]] = []
        unparseable: list[str] = []
        with path.open(encoding="utf-8") as handle:
            for lineno, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    unparseable.append(f"line {lineno}")
        for location in unparseable:
            self.broken_links.append(
                BrokenLink(
                    referrer=f"study {slug}",
                    kind="ledger_unparseable",
                    referenced=f"{rel_path}:{location}",
                    reason="ledger line is not valid JSON",
                )
            )
        return records, unparseable

    def _load_hypotheses(self, slug: str) -> list[HypothesisEntry]:
        registrations_root = self.repo_root / "research" / slug / "hypotheses"
        versions_root = registrations_root / "registrations"
        entries: list[HypothesisEntry] = []
        if not versions_root.is_dir():
            self._note_missing(
                self._rel(versions_root),
                f"study {slug} has no registrations directory",
            )
            return entries
        registry: HypothesisRegistry | None = None
        try:
            registry = HypothesisRegistry(registrations_root)
        except (OSError, ValueError):
            registry = None
        events_path = registrations_root / "hypothesis-events.jsonl"
        if events_path.is_file():
            # get_state reads the event log; track it as a source file.
            self.source_files.add(self._rel(events_path))
        for hyp_dir in sorted(versions_root.iterdir()):
            if not hyp_dir.is_dir():
                continue
            hypothesis_id = hyp_dir.name
            versions: list[HypothesisVersionEntry] = []
            for version_file in sorted(hyp_dir.glob("v*.json")):
                rel_path = self._rel(version_file)
                self.source_files.add(rel_path)
                try:
                    data = _read_json(version_file)
                except (json.JSONDecodeError, ValueError):
                    self.broken_links.append(
                        BrokenLink(
                            referrer=f"hypothesis {hypothesis_id}",
                            kind="registration_unparseable",
                            referenced=rel_path,
                            reason="registration file is not valid JSON",
                        )
                    )
                    continue
                version = _as_int(data.get("version"))
                if version is None:
                    version = int(version_file.stem[1:])
                state = "unknown"
                if registry is not None:
                    try:
                        state = registry.get_state(
                            hypothesis_id, version
                        ).value
                    except FileNotFoundError:
                        self._note_missing(
                            f"research/{slug}/hypotheses/"
                            "hypothesis-events.jsonl",
                            f"no lifecycle events for {hypothesis_id} "
                            f"v{version}",
                        )
                versions.append(
                    HypothesisVersionEntry(
                        version=version,
                        spec_fingerprint=str(
                            data.get("spec_fingerprint", "")
                        ),
                        registration_hash=str(
                            data.get("registration_hash", "")
                        ),
                        registered_at=str(data.get("registered_at", "")),
                        state=state,
                    )
                )
            versions.sort(key=lambda v: v.version)
            latest_state = versions[-1].state if versions else "unknown"
            entries.append(
                HypothesisEntry(
                    hypothesis_id=hypothesis_id,
                    study=slug,
                    versions=tuple(versions),
                    latest_state=latest_state,
                )
            )
        return entries

    def _trial_entry(
        self,
        record: dict[str, Any],
        slug: str,
        test_types: dict[tuple[str, str], str],
    ) -> TrialEntry:
        trial_id = str(record.get("trial_id", ""))
        status = str(record.get("status", ""))
        result = record.get("result") or {}
        metrics = result.get("metrics") or {}
        tests = metrics.get("tests") or {}
        test_keys = tuple(sorted(tests.keys()))
        if status != "completed":
            return TrialEntry(
                trial_id=trial_id,
                study=slug,
                hypothesis_id=str(record.get("hypothesis_id", "")),
                status=status,
                record_hash=str(record.get("record_hash", "")),
                recorded_at=str(record.get("recorded_at", "")),
                failure_reason=str(result.get("error", "")) or None,
                test_keys=test_keys,
            )
        holm = metrics.get("holm") or []
        primary = holm[0] if holm else {}
        primary_test = str(primary.get("test", "")) or None
        test_record = tests.get(primary_test, {}) if primary_test else {}
        test_type = (
            test_types.get((trial_id, primary_test))
            if primary_test
            else None
        )
        effect_field, effect_label, secondary_field, secondary_label = (
            EFFECT_FIELDS.get(test_type or "", ("coefficient", "coef", None, None))
        )
        verdict = metrics.get("verdict") or {}
        return TrialEntry(
            trial_id=trial_id,
            study=slug,
            hypothesis_id=str(record.get("hypothesis_id", "")),
            status=status,
            supported=(
                bool(verdict["supported"])
                if isinstance(verdict.get("supported"), bool)
                else None
            ),
            primary_test=primary_test,
            primary_test_type=test_type,
            primary_effect_label=effect_label,
            primary_effect_value=_as_float(test_record.get(effect_field)),
            secondary_effect_label=secondary_label,
            secondary_effect_value=(
                _as_float(test_record.get(secondary_field))
                if secondary_field
                else None
            ),
            primary_adjusted_p_value=_as_float(
                primary.get("adjusted_p_value")
            ),
            primary_raw_p_value=_as_float(primary.get("raw_p_value")),
            observations=_as_int(test_record.get("observations")),
            record_hash=str(record.get("record_hash", "")),
            recorded_at=str(record.get("recorded_at", "")),
            test_keys=test_keys,
        )

    # -- graph, planner, evidence, review, audit ------------------------

    def build(self) -> Catalog:
        registry = self._load_json(REGISTRY_PATH)
        ranking = self._load_json(RANKING_PATH)
        availability = self._load_json(AVAILABILITY_PATH)
        sources_data = self._load_json(SOURCES_PATH)
        evidence_report = self._load_json(EVIDENCE_REPORT_PATH)
        freshness = self._load_json(PANEL_FRESHNESS_PATH)
        review_data = self._load_json(REVIEW_REPORT_PATH)
        audit_data = self._load_json(AUDIT_SUMMARY_PATH)

        nodes = tuple(
            NodeEntry(
                instrument_id=str(n.get("instrument_id", "")),
                short_label=str(n.get("short_label", "")),
                name=str(n.get("name", "")),
                asset_class=str(n.get("asset_class", "")),
            )
            for n in sorted(
                registry.get("nodes", []),
                key=lambda n: str(n.get("instrument_id", "")),
            )
        )
        node_ids = tuple(n.instrument_id for n in nodes)
        test_types: dict[tuple[str, str], str] = {}
        for edge in registry.get("edges", []):
            trial_id = edge.get("trial_id")
            test_key = edge.get("ledger_test_key")
            test_type = edge.get("test_type")
            if trial_id and test_key and test_type:
                test_types[(str(trial_id), str(test_key))] = str(test_type)

        # Studies, hypotheses, trials.
        slugs = self._study_slugs()
        raw_trials: dict[str, list[dict[str, Any]]] = {}
        trial_entries: list[TrialEntry] = []
        hypothesis_entries: list[HypothesisEntry] = []
        for slug in slugs:
            records, _ = self._load_trials(slug)
            raw_trials[slug] = records
            trial_entries.extend(
                self._trial_entry(r, slug, test_types) for r in records
            )
            hypothesis_entries.extend(self._load_hypotheses(slug))
        trial_entries.sort(key=lambda t: t.trial_id)
        hypothesis_entries.sort(key=lambda h: h.hypothesis_id)

        trials_by_hypothesis: dict[str, list[str]] = {}
        for trial in trial_entries:
            trials_by_hypothesis.setdefault(trial.hypothesis_id, []).append(
                trial.trial_id
            )
        hypothesis_entries = [
            h.model_copy(
                update={
                    "trials": tuple(sorted(trials_by_hypothesis.get(h.hypothesis_id, [])))
                }
            )
            for h in hypothesis_entries
        ]

        # Decision records.
        records_dir = self.repo_root / DECISION_RECORDS_DIR
        decision_entries: list[DecisionRecordEntry] = []
        for record_file in sorted(records_dir.glob("DR-*.json")):
            rel_path = self._rel(record_file)
            self.source_files.add(rel_path)
            data = _read_json(record_file)
            edge_id = data.get("edge_id") or data.get("primary_edge_id")
            decision_entries.append(
                DecisionRecordEntry(
                    record_id=str(data.get("record_id", record_file.stem)),
                    record_type=str(data.get("record_type", "")),
                    study=str(data.get("study", "")),
                    hypothesis_id=str(data.get("hypothesis_id", "")),
                    edge_id=str(edge_id) if edge_id else None,
                    conclusion=str(data.get("conclusion", "")),
                    trial_id=str(data.get("trial_id", "")),
                    report_path=str(data.get("report_path", "")),
                    ledger_path=str(data.get("ledger_path", "")),
                )
            )
        decision_entries.sort(key=lambda r: r.record_id)
        record_by_edge = {
            r.edge_id: r.record_id for r in decision_entries if r.edge_id
        }
        records_by_hypothesis: dict[str, list[str]] = {}
        for record in decision_entries:
            records_by_hypothesis.setdefault(record.hypothesis_id, []).append(
                record.record_id
            )
        hypothesis_entries = [
            h.model_copy(
                update={
                    "decision_records": tuple(
                        sorted(records_by_hypothesis.get(h.hypothesis_id, []))
                    )
                }
            )
            for h in hypothesis_entries
        ]

        # Edges, with audit survival and decision-record links.
        audit = audit_data.get("lab_wide_audit", {})
        audit_edges = {
            e.get("edge_id"): e for e in audit.get("supported_edges", [])
        }
        edge_entries: list[EdgeEntry] = []
        edges_by_hypothesis: dict[str, list[str]] = {}
        for edge in registry.get("edges", []):
            edge_id = str(edge.get("edge_id", ""))
            audit_entry = audit_edges.get(edge_id, {})
            forward = edge.get("forward_sample")
            forward_entry = None
            if isinstance(forward, dict):
                forward_entry = ForwardSampleEntry(
                    checked_at=str(forward.get("checked_at", "")),
                    forward_rows=int(forward.get("forward_rows", 0) or 0),
                    minimum_lowvol_rows=int(
                        forward.get("minimum_lowvol_rows", 0) or 0
                    ),
                    observed_lowvol_rows=int(
                        forward.get("observed_lowvol_rows", 0) or 0
                    ),
                    ready=bool(forward.get("ready", False)),
                    window_start=str(forward.get("window_start", "")),
                    window_end=str(forward.get("window_end", "")),
                )
            edge_entries.append(
                EdgeEntry(
                    edge_id=edge_id,
                    source_instrument=str(edge.get("source_instrument", "")),
                    target_instrument=str(edge.get("target_instrument", "")),
                    status=str(edge.get("status", "")),
                    hypothesis_id=(
                        str(edge["hypothesis_id"])
                        if edge.get("hypothesis_id")
                        else None
                    ),
                    trial_id=(
                        str(edge["trial_id"]) if edge.get("trial_id") else None
                    ),
                    ledger_test_key=(
                        str(edge["ledger_test_key"])
                        if edge.get("ledger_test_key")
                        else None
                    ),
                    test_type=(
                        str(edge["test_type"]) if edge.get("test_type") else None
                    ),
                    report_path=(
                        str(edge["report_path"])
                        if edge.get("report_path")
                        else None
                    ),
                    ledger_path=(
                        str(edge["ledger_path"])
                        if edge.get("ledger_path")
                        else None
                    ),
                    decision_record_id=record_by_edge.get(edge_id),
                    holm_significant=(
                        bool(audit_entry["holm_significant"])
                        if isinstance(
                            audit_entry.get("holm_significant"), bool
                        )
                        else None
                    ),
                    bh_significant=(
                        bool(audit_entry["bh_significant"])
                        if isinstance(audit_entry.get("bh_significant"), bool)
                        else None
                    ),
                    audit_caveat=(
                        str(audit_entry["caveat"])
                        if audit_entry.get("caveat")
                        else None
                    ),
                    forward_sample=forward_entry,
                )
            )
            if edge.get("hypothesis_id"):
                edges_by_hypothesis.setdefault(
                    str(edge["hypothesis_id"]), []
                ).append(edge_id)
        edge_entries.sort(key=lambda e: e.edge_id)
        hypothesis_entries = [
            h.model_copy(
                update={
                    "edges": tuple(sorted(edges_by_hypothesis.get(h.hypothesis_id, [])))
                }
            )
            for h in hypothesis_entries
        ]

        # Studies, with report paths derived from the graph edges.
        report_paths: dict[str, set[str]] = {}
        for edge in edge_entries:
            if edge.ledger_path and edge.report_path:
                parts = edge.ledger_path.split("/")
                if len(parts) >= 2 and parts[0] == "research":
                    report_paths.setdefault(parts[1], set()).add(edge.report_path)
        study_entries: list[StudyEntry] = []
        for slug in slugs:
            paths = report_paths.get(slug, set())
            report_path: str | None = None
            if len(paths) == 1:
                report_path = next(iter(paths))
            elif len(paths) > 1:
                report_path = sorted(paths)[0]
                self.broken_links.append(
                    BrokenLink(
                        referrer=f"study {slug}",
                        kind="study_report_conflict",
                        referenced=", ".join(sorted(paths)),
                        reason="graph edges disagree on the study report",
                    )
                )
            trials_for_study = tuple(
                sorted(
                    t.trial_id for t in trial_entries if t.study == slug
                )
            )
            hyps_for_study = tuple(
                sorted(
                    h.hypothesis_id
                    for h in hypothesis_entries
                    if h.study == slug
                )
            )
            anchor = self.repo_root / "research" / slug / "trials.jsonl.anchor"
            manifest = self.repo_root / "research" / slug / "manifest.json"
            panel_summary = (
                self.repo_root / "research" / slug / "panel-summary.json"
            )
            if not anchor.is_file():
                self._note_missing(
                    f"research/{slug}/trials.jsonl.anchor",
                    "ledger anchor absent; truncation undetectable",
                )
            if not manifest.is_file():
                self._note_missing(
                    f"research/{slug}/manifest.json",
                    "fetch manifest absent",
                )
            if not panel_summary.is_file():
                self._note_missing(
                    f"research/{slug}/panel-summary.json",
                    "panel summary absent",
                )
            status = (
                "open"
                if any(
                    h.latest_state in ("registered", "testing")
                    for h in hypothesis_entries
                    if h.study == slug
                )
                else "closed"
            )
            study_entries.append(
                StudyEntry(
                    slug=slug,
                    report_path=report_path,
                    report_exists=(
                        (self.repo_root / report_path).is_file()
                        if report_path
                        else False
                    ),
                    hypotheses=hyps_for_study,
                    trials=trials_for_study,
                    anchor_present=anchor.is_file(),
                    manifest_present=manifest.is_file(),
                    panel_summary_present=panel_summary.is_file(),
                    status=status,
                )
            )

        # Candidates from the planner ranking.
        templates_dir = self.repo_root / TEMPLATES_DIR

        def _template_exists(source: str, target: str) -> bool:
            # Template filenames use the instrument ids with ":" -> "-".
            name = (
                f"{source.replace(':', '-')}__"
                f"{target.replace(':', '-')}.json"
            )
            return (templates_dir / name).is_file()

        candidate_entries: list[CandidateEntry] = []
        for row in ranking.get("ranked", []):
            source = str(row.get("source_instrument", ""))
            target = str(row.get("target_instrument", ""))
            candidate_entries.append(
                CandidateEntry(
                    source_instrument=source,
                    target_instrument=target,
                    ranked=True,
                    rank=_as_int(row.get("rank")),
                    total_score=_as_float(row.get("total")),
                    mechanism=(
                        str(row["mechanism"]) if row.get("mechanism") else None
                    ),
                    test_type=(
                        str(row["test_type"]) if row.get("test_type") else None
                    ),
                    has_template=_template_exists(source, target),
                )
            )
        for row in ranking.get("unrankable", []):
            source = str(row.get("source_instrument", ""))
            target = str(row.get("target_instrument", ""))
            candidate_entries.append(
                CandidateEntry(
                    source_instrument=source,
                    target_instrument=target,
                    ranked=False,
                    unrankable_reason=(
                        str(row["reason"]) if row.get("reason") else None
                    ),
                    has_template=_template_exists(source, target),
                )
            )
        candidate_entries.sort(
            key=lambda c: (
                c.rank is None,
                c.rank or 0,
                c.source_instrument,
                c.target_instrument,
            )
        )

        # Sources and panels from the evidence registry.
        probe_by_source: dict[str, dict[str, Any]] = {
            s.get("source_id", ""): s
            for s in evidence_report.get("sources", [])
        }
        recorded_only_counts: dict[str, int] = {}
        for entry in evidence_report.get("recorded_only", []):
            source_id = str(entry.get("source_id", ""))
            recorded_only_counts[source_id] = (
                recorded_only_counts.get(source_id, 0) + 1
            )
        source_entries: list[SourceEntry] = []
        for source in sources_data.get("sources", []):
            source_id = str(source.get("source_id", ""))
            probe = probe_by_source.get(source_id, {})
            checks = probe.get("checks", [])
            source_entries.append(
                SourceEntry(
                    source_id=source_id,
                    provider=str(source.get("provider", "")),
                    quirks=len(source.get("quirks", [])),
                    recorded_only=recorded_only_counts.get(source_id, 0),
                    probe_kind=str(source.get("probe_kind", "")),
                    probe_pass=sum(
                        1 for c in checks if c.get("status") == "pass"
                    ),
                    probe_skip=sum(
                        1 for c in checks if c.get("status") == "skip"
                    ),
                    probe_fail=sum(
                        1 for c in checks if c.get("status") == "fail"
                    ),
                    last_verified=(
                        str(source["last_verified"])
                        if source.get("last_verified")
                        else None
                    ),
                    used_by=tuple(
                        str(u) for u in source.get("used_by", [])
                    ),
                )
            )
        source_entries.sort(key=lambda s: s.source_id)
        freshness_by_instrument = {
            p.get("instrument_id", ""): p
            for p in freshness.get("panels", [])
        }
        panel_entries: list[PanelEntry] = []
        for panel in evidence_report.get("panels", []):
            instrument_id = str(panel.get("instrument_id", ""))
            definition = freshness_by_instrument.get(instrument_id, {})
            panel_entries.append(
                PanelEntry(
                    instrument_id=instrument_id,
                    source_id=str(panel.get("source_id", "")),
                    status=str(panel.get("status", "")),
                    panel_last=(
                        str(panel["panel_last"])
                        if panel.get("panel_last")
                        else None
                    ),
                    expected_latest=(
                        str(panel["expected_latest"])
                        if panel.get("expected_latest")
                        else None
                    ),
                    days_behind=_as_int(panel.get("days_behind")),
                    lag_kind=(
                        str(definition["lag_kind"])
                        if definition.get("lag_kind")
                        else None
                    ),
                    latest_from=(
                        str(definition["latest_from"])
                        if definition.get("latest_from")
                        else None
                    ),
                )
            )
        panel_entries.sort(key=lambda p: p.instrument_id)

        # Review and audit summaries, quoted not recomputed.
        unverified_items: list[str] = []
        per_study_counts: dict[str, dict[str, int]] = {}
        for study in review_data.get("studies", []):
            slug = str(study.get("study", ""))
            per_study_counts[slug] = {
                str(k): int(v) for k, v in study.get("counts", {}).items()
            }
            for check in study.get("checks", []):
                if check.get("verdict") == "unverified":
                    unverified_items.append(
                        f"{slug}: {check.get('check_id', '')} — "
                        f"{check.get('summary', '')}"
                    )
        review = ReviewSummary(
            reviewed_at=str(review_data.get("reviewed_at", "")),
            counts={
                str(k): int(v)
                for k, v in review_data.get("counts", {}).items()
            },
            per_study_counts=per_study_counts,
            unverified_items=tuple(sorted(unverified_items)),
        )
        audit_summary = AuditSummary(
            family_size=int(audit.get("family_size", 0)),
            supported_total=int(audit.get("supported_total", 0)),
            holm_survivors=int(audit.get("holm_survivors", 0)),
            bh_survivors=int(audit.get("bh_survivors", 0)),
            registry_content_hash=str(audit.get("registry_content_hash", "")),
        )

        # Reserved trial ids: gaps in the T0001.. sequence that have a
        # recorded basis — a hypothesis with no trial yet whose pending
        # edge names it as the test to come. The lab numbers a
        # hypothesis's first trial after the hypothesis (T0001 ran
        # H0001, T0002 ran H0002, ...), so the pending hypothesis's
        # number is the reserved trial number. A gap with no such basis
        # is not reserved; the integrity check flags it.
        pending_hypotheses = {
            e.hypothesis_id
            for e in edge_entries
            if e.status == "pending" and e.hypothesis_id
        }
        reserved_numbers = {
            int(h.hypothesis_id[1:])
            for h in hypothesis_entries
            if not h.trials
            and h.hypothesis_id in pending_hypotheses
            and h.hypothesis_id[1:].isdigit()
        }
        numbers = sorted(
            int(t.trial_id[1:])
            for t in trial_entries
            if t.trial_id.startswith("T") and t.trial_id[1:].isdigit()
        )
        present = set(numbers)
        reserved = tuple(
            f"T{n:04d}"
            for n in range(1, (max(numbers) + 1) if numbers else 1)
            if n not in present and n in reserved_numbers
        )

        # Post-probe data updates (currently: the VXN re-fetch).
        post_probe: list[PostProbeUpdate] = []
        refresh = self._load_json_optional(VXN_REFRESH_PATH)
        if refresh is not None:
            full = refresh.get("full_series", {})
            post_probe.append(
                PostProbeUpdate(
                    instrument_id=str(
                        refresh.get("instrument_id", "index:vxn")
                    ),
                    note=(
                        f"Re-fetched past 2020-05-15 after the probe: "
                        f"full series {full.get('first_date')} to "
                        f"{full.get('last_date')} "
                        f"({full.get('rows')} rows, "
                        f"{full.get('missing_values')} missing)"
                    ),
                    source_file=VXN_REFRESH_PATH,
                )
            )

        catalog = Catalog(
            generated_at=self.generated_at,
            source_files=tuple(sorted(self.source_files)),
            studies=tuple(study_entries),
            hypotheses=tuple(hypothesis_entries),
            trials=tuple(trial_entries),
            reserved_trial_ids=reserved,
            nodes=nodes,
            edges=tuple(edge_entries),
            decision_records=tuple(decision_entries),
            candidates=tuple(candidate_entries),
            sources=tuple(source_entries),
            panels=tuple(panel_entries),
            review=review,
            audit=audit_summary,
            evidence_probed_at=str(evidence_report.get("probed_at", "")),
            post_probe_updates=tuple(post_probe),
            missing_optional=tuple(
                sorted(self.missing_optional, key=lambda m: m.path)
            ),
        )

        # Integrity checks.
        templates: list[integrity.TemplateRef] = []
        for template_file in sorted(templates_dir.glob("*.json")):
            self.source_files.add(self._rel(template_file))
            try:
                template = _read_json(template_file)
            except (json.JSONDecodeError, ValueError):
                self.broken_links.append(
                    BrokenLink(
                        referrer="planner templates",
                        kind="template_unparseable",
                        referenced=self._rel(template_file),
                        reason="template file is not valid JSON",
                    )
                )
                continue
            universe = template.get("universe", [])
            if len(universe) == 2:
                templates.append(
                    integrity.TemplateRef(
                        source_instrument=str(universe[0]),
                        target_instrument=str(universe[1]),
                        rank=_as_int(template.get("planner_rank")),
                        filename=template_file.name,
                    )
                )
        availability_refs = tuple(
            integrity.AvailabilityRef(
                instrument_id=str(p.get("instrument_id", "")),
                verified_by_paths=tuple(
                    sorted(
                        set(
                            PATH_TOKEN.findall(
                                str(p.get("verified_by", ""))
                            )
                        )
                    )
                ),
            )
            for p in availability.get("panels", [])
        )
        registry_candidates = tuple(
            (
                str(c.get("source_instrument", "")),
                str(c.get("target_instrument", "")),
            )
            for c in registry.get("candidates", [])
        )
        used_by = tuple(
            (s.source_id, entry)
            for s in source_entries
            for entry in s.used_by
        )
        checks = [
            integrity.check_edge_links(
                catalog.edges,
                catalog.trials,
                catalog.hypotheses,
                node_ids,
                self.repo_root,
            ),
            integrity.check_candidate_links(
                catalog.candidates, registry_candidates, node_ids
            ),
            integrity.check_decision_record_links(
                catalog.decision_records,
                catalog.edges,
                catalog.hypotheses,
                catalog.trials,
                catalog.studies,
                self.repo_root,
            ),
            integrity.check_template_links(
                tuple(templates), catalog.candidates
            ),
            integrity.check_review_links(
                tuple(sorted(per_study_counts.keys())), catalog.studies
            ),
            integrity.check_audit_links(
                tuple(sorted(audit_edges.keys())), catalog.edges
            ),
            integrity.check_availability_links(
                availability_refs, node_ids, self.repo_root
            ),
            integrity.check_source_used_by(used_by, self.repo_root),
            integrity.check_trial_sequence(catalog.trials, reserved),
            integrity.check_hypothesis_trials(
                catalog.hypotheses, catalog.edges
            ),
            integrity.check_study_reports(catalog.studies),
        ]
        for found in checks:
            self.broken_links.extend(found)
        broken = tuple(
            sorted(
                self.broken_links,
                key=lambda b: (b.referrer, b.kind, b.referenced),
            )
        )

        counts = {
            "studies": len(catalog.studies),
            "hypotheses": len(catalog.hypotheses),
            "hypothesis_versions": sum(
                len(h.versions) for h in catalog.hypotheses
            ),
            "trials_total": len(catalog.trials),
            "trials_completed": sum(
                1 for t in catalog.trials if t.status == "completed"
            ),
            "trials_failed": sum(
                1 for t in catalog.trials if t.status == "failed"
            ),
            "trials_reserved": len(reserved),
            "nodes": len(catalog.nodes),
            "edges_total": len(catalog.edges),
            "edges_supported": sum(
                1 for e in catalog.edges if e.status == "supported"
            ),
            "edges_rejected": sum(
                1 for e in catalog.edges if e.status == "rejected"
            ),
            "edges_pending": sum(
                1 for e in catalog.edges if e.status == "pending"
            ),
            "edges_descriptive": sum(
                1 for e in catalog.edges if e.status == "descriptive"
            ),
            "decision_records": len(catalog.decision_records),
            "candidates_total": len(catalog.candidates),
            "candidates_ranked": sum(
                1 for c in catalog.candidates if c.ranked
            ),
            "candidates_unrankable": sum(
                1 for c in catalog.candidates if not c.ranked
            ),
            "templates": len(templates),
            "sources": len(catalog.sources),
            "panels": len(catalog.panels),
            "broken_links": len(broken),
            "missing_optional": len(catalog.missing_optional),
        }
        return catalog.model_copy(
            update={
                "source_files": tuple(sorted(self.source_files)),
                "broken_links": broken,
                "counts": counts,
            }
        )


def build_catalog(repo_root: Path, generated_at: datetime) -> Catalog:
    """Build the unified catalog for the repo at `repo_root`."""
    return _Builder(repo_root, generated_at).build()
