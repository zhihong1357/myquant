"""Render the lab status report from a Catalog (Stage 6e).

Two renderings of the same content: a markdown report for reading and
a JSON report for machines. Both are derived from the catalog — no
number is typed in. The report states only what the records say: it
draws no new conclusions and never presents a supported edge as a
tradeable signal.
"""

from __future__ import annotations

import json
from typing import Any

from myquant.librarian.models import Catalog


def fmt_num(value: float | None) -> str:
    """Format a number for the markdown tables (6 significant digits).

    Six digits, not four: an effect ratio of 1.00006 must not render
    as "1".
    """
    if value is None:
        return "—"
    return f"{value:.6g}"


def _short_labels(catalog: Catalog) -> dict[str, str]:
    return {n.instrument_id: n.short_label for n in catalog.nodes}


def _pair(
    labels: dict[str, str], source: str, target: str
) -> str:
    return f"{labels.get(source, source)}→{labels.get(target, target)}"


def _tier(score: float | None) -> str:
    if score is None:
        return "—"
    return f"{score:.2f}"


def report_data(catalog: Catalog) -> dict[str, Any]:
    """The report content as structured data (the JSON rendering)."""
    labels = _short_labels(catalog)
    completed = [t for t in catalog.trials if t.status == "completed"]
    failed = [t for t in catalog.trials if t.status == "failed"]
    supported = [e for e in catalog.edges if e.status == "supported"]
    ranked = [c for c in catalog.candidates if c.ranked]
    unrankable = [c for c in catalog.candidates if not c.ranked]
    tiers: dict[str, int] = {}
    for candidate in ranked:
        tiers[_tier(candidate.total_score)] = (
            tiers.get(_tier(candidate.total_score), 0) + 1
        )
    stale_panels = [p for p in catalog.panels if p.status != "fresh"]
    pending_items = _pending_items(catalog)
    return {
        "generated_at": catalog.generated_at.isoformat(),
        "schema_version": catalog.schema_version,
        "source_files": list(catalog.source_files),
        "counts": dict(catalog.counts),
        "studies": [
            {
                "study": t.study,
                "trial_id": t.trial_id,
                "hypothesis_id": t.hypothesis_id,
                "supported": t.supported,
                "primary_test": t.primary_test,
                "primary_test_type": t.primary_test_type,
                "primary_effect_label": t.primary_effect_label,
                "primary_effect_value": t.primary_effect_value,
                "secondary_effect_label": t.secondary_effect_label,
                "secondary_effect_value": t.secondary_effect_value,
                "primary_adjusted_p_value": t.primary_adjusted_p_value,
                "primary_raw_p_value": t.primary_raw_p_value,
                "observations": t.observations,
            }
            for t in completed
        ],
        "failed_trials": [
            {
                "trial_id": t.trial_id,
                "study": t.study,
                "hypothesis_id": t.hypothesis_id,
                "failure_reason": t.failure_reason,
            }
            for t in failed
        ],
        "studies_open": [s.slug for s in catalog.studies if s.status == "open"],
        "graph": {
            "nodes": len(catalog.nodes),
            "edges_total": len(catalog.edges),
            "edges_by_status": {
                status: sum(
                    1 for e in catalog.edges if e.status == status
                )
                for status in ("supported", "rejected", "pending", "descriptive")
            },
            "supported_edges": [
                {
                    "edge_id": e.edge_id,
                    "pair": _pair(labels, e.source_instrument, e.target_instrument),
                    "hypothesis_id": e.hypothesis_id,
                    "trial_id": e.trial_id,
                    "holm_significant": e.holm_significant,
                    "bh_significant": e.bh_significant,
                    "audit_caveat": e.audit_caveat,
                    "decision_record_id": e.decision_record_id,
                }
                for e in supported
            ],
        },
        "audit": (
            {
                "family_size": catalog.audit.family_size,
                "supported_total": catalog.audit.supported_total,
                "holm_survivors": catalog.audit.holm_survivors,
                "bh_survivors": catalog.audit.bh_survivors,
            }
            if catalog.audit
            else None
        ),
        "candidates": {
            "total": len(catalog.candidates),
            "ranked": len(ranked),
            "unrankable": len(unrankable),
            "tiers": tiers,
            "top_10": [
                {
                    "rank": c.rank,
                    "pair": _pair(
                        labels, c.source_instrument, c.target_instrument
                    ),
                    "total_score": c.total_score,
                    "mechanism": c.mechanism,
                    "test_type": c.test_type,
                }
                for c in ranked[:10]
            ],
        },
        "freshness": {
            "probed_at": catalog.evidence_probed_at,
            "sources": [
                {
                    "source_id": s.source_id,
                    "probe_kind": s.probe_kind,
                    "probe_pass": s.probe_pass,
                    "probe_skip": s.probe_skip,
                    "probe_fail": s.probe_fail,
                    "quirks": s.quirks,
                    "recorded_only": s.recorded_only,
                    "last_verified": s.last_verified,
                }
                for s in catalog.sources
            ],
            "panels_fresh": sum(
                1 for p in catalog.panels if p.status == "fresh"
            ),
            "panels_stale": len(stale_panels),
            "stale_panels": [
                {
                    "instrument_id": p.instrument_id,
                    "source_id": p.source_id,
                    "panel_last": p.panel_last,
                    "expected_latest": p.expected_latest,
                    "days_behind": p.days_behind,
                }
                for p in stale_panels
            ],
            "post_probe_updates": [
                {
                    "instrument_id": u.instrument_id,
                    "note": u.note,
                    "source_file": u.source_file,
                }
                for u in catalog.post_probe_updates
            ],
        },
        "review": (
            {
                "reviewed_at": catalog.review.reviewed_at,
                "counts": dict(catalog.review.counts),
                "unverified_items": list(catalog.review.unverified_items),
            }
            if catalog.review
            else None
        ),
        "pending_items": pending_items,
        "integrity": {
            "broken_links": [
                {
                    "referrer": b.referrer,
                    "kind": b.kind,
                    "referenced": b.referenced,
                    "reason": b.reason,
                }
                for b in catalog.broken_links
            ],
            "missing_optional": [
                {"path": m.path, "reason": m.reason}
                for m in catalog.missing_optional
            ],
        },
    }


def _pending_items(catalog: Catalog) -> list[str]:
    """Pending items, each grounded in a record already in the catalog."""
    labels = _short_labels(catalog)
    items: list[str] = []
    for edge in catalog.edges:
        if edge.status == "pending":
            detail = ""
            if edge.forward_sample is not None:
                sample = edge.forward_sample
                detail = (
                    f"; {sample.observed_lowvol_rows}/"
                    f"{sample.minimum_lowvol_rows} low-vol rows observed, "
                    f"{'ready' if sample.ready else 'not ready'} "
                    f"(window {sample.window_start} to "
                    f"{sample.window_end})"
                )
            items.append(
                f"Forward test pending: hypothesis {edge.hypothesis_id} "
                f"(edge {edge.edge_id}, "
                f"{_pair(labels, edge.source_instrument, edge.target_instrument)}"
                f"); no trial run yet{detail}"
                + (
                    f"; sample check at {edge.ledger_path}"
                    if edge.ledger_path
                    else ""
                )
            )
    for trial_id in catalog.reserved_trial_ids:
        items.append(
            f"Trial id {trial_id} is reserved (sequence gap with a "
            f"recorded reservation); no ledger record exists yet"
        )
    unrankable = [c for c in catalog.candidates if not c.ranked]
    if unrankable:
        pairs = ", ".join(
            sorted(
                _pair(labels, c.source_instrument, c.target_instrument)
                for c in unrankable
            )
        )
        items.append(
            f"{len(unrankable)} candidate pairs unrankable "
            f"(no overlapping panel window): {pairs}"
        )
    for missing in catalog.missing_optional:
        if missing.path.endswith(".anchor"):
            items.append(
                f"Missing ledger anchor: {missing.path} — {missing.reason}"
            )
    if catalog.review:
        pit_missing = [
            item
            for item in catalog.review.unverified_items
            if "pit_spot_check" in item
        ]
        if pit_missing:
            items.append(
                f"PIT discipline unverified for {len(pit_missing)} "
                f"studies (no PIT parquet retained locally) — see "
                f"Review status"
            )
    return items


def render_lab_report_json(catalog: Catalog) -> bytes:
    """Render the JSON lab report (sorted keys, indented, deterministic)."""
    data = report_data(catalog)
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
    return (text + "\n").encode("utf-8")


def render_lab_report_markdown(catalog: Catalog) -> str:
    """Render the markdown lab status report."""
    data = report_data(catalog)
    lines: list[str] = []
    lines.extend(
        [
            "# MyQuant lab status report",
            "",
            f"Generated at: {catalog.generated_at.isoformat()}",
            "",
            "Read-only report generated from the lab's committed records "
            "by the research librarian (Stage 6e). Every number below is "
            "derived by reading a record — nothing is transcribed by "
            "hand. The report states what the records say; it draws no "
            "new conclusions, and a supported edge is a statistical "
            "result, not a tradeable signal.",
            "",
            "## Studies",
            "",
            "One row per completed trial. The primary test is the first "
            "entry of the trial's recorded Holm family; the effect, "
            "adjusted p-value and sample size come from the trial ledger.",
            "",
            "| study | trial | hypothesis | verdict | primary test | "
            "effect | adj p | n |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in data["studies"]:
        effect = row["primary_effect_value"]
        effect_text = (
            f"{row['primary_effect_label']} {fmt_num(effect)}"
            if row["primary_effect_label"]
            else fmt_num(effect)
        )
        if row["secondary_effect_value"] is not None:
            effect_text += (
                f" ({row['secondary_effect_label']} "
                f"{fmt_num(row['secondary_effect_value'])})"
            )
        lines.append(
            f"| {row['study']} | {row['trial_id']} | {row['hypothesis_id']} | "
            f"{'SUPPORTED' if row['supported'] else 'REJECTED'} | "
            f"{row['primary_test']} | {effect_text} | "
            f"{fmt_num(row['primary_adjusted_p_value'])} | "
            f"{row['observations'] if row['observations'] is not None else '—'} |"
        )
    lines.append("")
    if data["failed_trials"]:
        lines.append(
            "Failed trials (recorded in the ledgers, no metrics):"
        )
        lines.append("")
        for row in data["failed_trials"]:
            lines.append(
                f"- {row['trial_id']} ({row['study']}, "
                f"{row['hypothesis_id']}): {row['failure_reason']}"
            )
        lines.append("")
    if data["studies_open"]:
        lines.append(
            f"Open studies (a hypothesis still registered/testing): "
            f"{', '.join(data['studies_open'])}."
        )
        lines.append("")
    graph = data["graph"]
    lines.extend(
        [
            "## Graph",
            "",
            f"{graph['nodes']} nodes, {graph['edges_total']} edges: "
            + ", ".join(
                f"{count} {status}"
                for status, count in graph["edges_by_status"].items()
            )
            + ".",
            "",
            "Supported edges (within-study verdicts; the lab-wide audit "
            "columns are quoted from the 2B audit summary, not "
            "recomputed):",
            "",
            "| edge | pair | hypothesis | trial | Holm survives | "
            "BH survives |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for edge in graph["supported_edges"]:
        lines.append(
            f"| {edge['edge_id']} | {edge['pair']} | "
            f"{edge['hypothesis_id']} | {edge['trial_id']} | "
            f"{_yes_no(edge['holm_significant'])} | "
            f"{_yes_no(edge['bh_significant'])} |"
        )
    lines.append("")
    for edge in graph["supported_edges"]:
        if edge["audit_caveat"]:
            lines.append(f"- {edge['edge_id']}: {edge['audit_caveat']}")
    if any(e["audit_caveat"] for e in graph["supported_edges"]):
        lines.append("")
    if data["audit"]:
        lines.append(
            f"Lab-wide audit (2B): family of "
            f"{data['audit']['family_size']} tested edges; "
            f"{data['audit']['holm_survivors']} of "
            f"{data['audit']['supported_total']} supported edges survive "
            f"Holm, {data['audit']['bh_survivors']} survive BH. This is "
            f"a post-hoc second-layer reading; it does not change any "
            f"within-study verdict."
        )
        lines.append("")
    candidates = data["candidates"]
    lines.extend(
        [
            "## Candidate queue",
            "",
            f"{candidates['total']} untested candidate pairs: "
            f"{candidates['ranked']} ranked, "
            f"{candidates['unrankable']} unrankable. Score tiers: "
            + ", ".join(
                f"{tier} × {count}"
                for tier, count in sorted(
                    candidates["tiers"].items(), reverse=True
                )
            )
            + ".",
            "",
            "Top 10 (the ranking is a heuristic; the top tier is a tie "
            "broken lexicographically — see the planner report):",
            "",
            "| rank | pair | score | mechanism | test |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in candidates["top_10"]:
        lines.append(
            f"| {row['rank']} | {row['pair']} | "
            f"{_tier(row['total_score'])} | {row['mechanism']} | "
            f"{row['test_type']} |"
        )
    lines.append("")
    freshness = data["freshness"]
    lines.extend(
        [
            "## Data freshness",
            "",
            "Probe-time snapshot from the 6b evidence report "
            f"(probed {freshness['probed_at']}); panel freshness is "
            "judged against what each source serves, not against today.",
            "",
            "| source | probe | pass | skip | fail | quirks | "
            "recorded-only | last verified |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for source in freshness["sources"]:
        lines.append(
            f"| {source['source_id']} | {source['probe_kind']} | "
            f"{source['probe_pass']} | {source['probe_skip']} | "
            f"{source['probe_fail']} | {source['quirks']} | "
            f"{source['recorded_only']} | "
            f"{source['last_verified'] or '—'} |"
        )
    lines.append("")
    lines.append(
        f"Panels: {freshness['panels_fresh']} fresh, "
        f"{freshness['panels_stale']} stale at probe time."
    )
    if freshness["stale_panels"]:
        lines.append("")
        for panel in freshness["stale_panels"]:
            days = panel["days_behind"]
            behind = (
                f"{days} day{'s' if days != 1 else ''} behind"
                if days is not None
                else "behind"
            )
            lines.append(
                f"- {panel['instrument_id']} ({panel['source_id']}): "
                f"panel last {panel['panel_last']}, expected "
                f"{panel['expected_latest']}, {behind}"
            )
    lines.append("")
    for update in freshness["post_probe_updates"]:
        lines.append(
            f"Update after the probe: {update['instrument_id']} — "
            f"{update['note']} (see `{update['source_file']}`)."
        )
    if freshness["post_probe_updates"]:
        lines.append("")
    review = data["review"]
    if review:
        ordered = [
            (verdict, review["counts"].get(verdict, 0))
            for verdict in ("pass", "fail", "unverified", "note")
        ]
        lines.extend(
            [
                "## Review status (6d, quoted)",
                "",
                f"Full-lab review at {review['reviewed_at']}: "
                + ", ".join(f"{count} {verdict}" for verdict, count in ordered)
                + ".",
                "",
            ]
        )
        if review["unverified_items"]:
            lines.append("Unverified items (not passes):")
            lines.append("")
            for item in review["unverified_items"]:
                lines.append(f"- {item}")
            lines.append("")
    lines.extend(
        [
            "## Pending items",
            "",
        ]
    )
    if data["pending_items"]:
        for item in data["pending_items"]:
            lines.append(f"- {item}")
    else:
        lines.append("None recorded.")
    lines.append("")
    integrity_data = data["integrity"]
    lines.extend(
        [
            "## Integrity",
            "",
        ]
    )
    if integrity_data["broken_links"]:
        lines.append(
            f"{len(integrity_data['broken_links'])} broken link(s):"
        )
        lines.append("")
        for link in integrity_data["broken_links"]:
            lines.append(
                f"- {link['referrer']} → {link['referenced']} "
                f"({link['kind']}): {link['reason']}"
            )
    else:
        lines.append(
            "0 broken links — every cross-reference resolves "
            "(edges, candidates, decision records, templates, review, "
            "audit, availability, sources, trial sequence)."
        )
    lines.append("")
    if integrity_data["missing_optional"]:
        lines.append("Missing optional files (recorded, not failures):")
        lines.append("")
        for missing in integrity_data["missing_optional"]:
            lines.append(f"- `{missing['path']}` — {missing['reason']}")
        lines.append("")
    lines.extend(
        [
            "## Sources",
            "",
            "Files read to build this report (repo-relative paths):",
            "",
        ]
    )
    for path in data["source_files"]:
        lines.append(f"- `{path}`")
    lines.append("")
    return "\n".join(lines)


def _yes_no(value: bool | None) -> str:
    if value is None:
        return "—"
    return "yes" if value else "no"


def render_catalog_json(catalog: Catalog) -> bytes:
    """Render the catalog JSON (sorted keys, indented, deterministic)."""
    data = catalog.model_dump(mode="json")
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
    return (text + "\n").encode("utf-8")
