"""Stage 6a hypothesis-planner validation: rank the real registry.

Run from the repo root:

    .venv/bin/python research/planner-6a/validate_planner.py

Offline and deterministic. Loads the market-graph registry, the
decision records, the Stage 2B audit summary, the FOMC calendar and
the verified data-availability config; cross-checks the planner's
MDE formulas against the audit's own table; ranks all 123
candidates under the default weights and under two alternative
weightings; and writes:

- ``research/planner-6a/ranking.json`` — the full default-weight
  ranking (ranked, excluded, unrankable), byte-identical on re-runs.
- ``research/planner-6a/validation_report.md`` — the shortlist,
  sensitivity analysis, mechanism distribution and limitations
  (reproduced except the timestamp line).
- ``research/planner-6a/templates/`` — preregistration drafts for
  the top-10 pairs (drafts only; nothing is registered).

The ranking is a heuristic sorting device, not evidence: the report
says so, shows the tie structure that dominates the top-10, and
shows how the shortlist moves (or does not move) under other
weights.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from myquant.planner import (  # noqa: E402
    PlannerConfig,
    PlannerWeights,
    RankingResult,
    generate_prereg_draft,
    load_planner_inputs,
    mde_cross_check,
    rank_candidates,
)

WEIGHT_SETS = {
    "default (adjacency 0.4 / data 0.3 / power 0.3)": PlannerWeights(
        adjacency=0.4, data=0.3, power=0.3
    ),
    "adjacency-heavy (0.6 / 0.2 / 0.2)": PlannerWeights(
        adjacency=0.6, data=0.2, power=0.2
    ),
    "power-heavy (0.2 / 0.2 / 0.6)": PlannerWeights(
        adjacency=0.2, data=0.2, power=0.6
    ),
}

SHORTLIST_SIZE = 10


def _pair(candidate) -> str:
    return f"{candidate.source_instrument} -> {candidate.target_instrument}"


def _fmt(value: float | None, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def _template_filename(candidate) -> str:
    def _clean(instrument_id: str) -> str:
        return instrument_id.replace(":", "-")

    return (
        f"{_clean(candidate.source_instrument)}"
        f"__{_clean(candidate.target_instrument)}.json"
    )


def _ranking_lines(result: RankingResult) -> list[str]:
    lines = [
        "| Rank | Pair | Test | Score | Adj | Data | Power | Joint n | MDE | Mechanism |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for candidate in result.ranked:
        lines.append(
            f"| {candidate.rank} | {_pair(candidate)} | "
            f"{candidate.test_type.value} ({candidate.frequency}) | "
            f"{candidate.total:.2f} | {candidate.adjacency:.1f} | "
            f"{candidate.data:.1f} | "
            f"{_fmt(candidate.power, 1)} | "
            f"{candidate.joint_n if candidate.joint_n is not None else 'n/a'} | "
            f"{_fmt(candidate.mde, 5)} | {candidate.mechanism.value} |"
        )
    return lines


def main() -> None:
    ran_at = datetime.now(UTC)
    inputs = load_planner_inputs(REPO_ROOT)
    audit_summary = json.loads(
        (REPO_ROOT / "research/statistical-audit-2b/summary.json").read_text()
    )
    checks = mde_cross_check(audit_summary)
    failed = [c for c in checks if not c.passed]
    if failed:
        raise AssertionError(
            "MDE cross-check failed: "
            + "; ".join(
                f"{c.label}: audit {c.audit_value} vs recomputed "
                f"{c.recomputed_value}"
                for c in failed
            )
        )

    results: dict[str, RankingResult] = {}
    for label, weights in WEIGHT_SETS.items():
        config = PlannerConfig(weights=weights)
        results[label] = rank_candidates(
            inputs.candidates,
            inputs.tested_edges,
            inputs.availability,
            inputs.fomc_statement_dates,
            inputs.decision_records,
            config,
        )
    default_label = next(iter(WEIGHT_SETS))
    default = results[default_label]
    top10 = default.ranked[:SHORTLIST_SIZE]
    top10_pairs = {_pair(c) for c in top10}

    # Sensitivity: how the top-10 moves under other weights.
    sensitivity: list[dict[str, object]] = []
    for label, result in results.items():
        pairs = {_pair(c) for c in result.ranked[:SHORTLIST_SIZE]}
        sensitivity.append(
            {
                "label": label,
                "top10": sorted(pairs),
                "intersection_with_default": len(pairs & top10_pairs),
                "entered": sorted(pairs - top10_pairs),
                "left": sorted(top10_pairs - pairs),
            }
        )

    # Mechanism distribution: top-10 vs all ranked.
    all_mechanisms = Counter(c.mechanism.value for c in default.ranked)
    top_mechanisms = Counter(c.mechanism.value for c in top10)

    # Score-tier structure under the default weights.
    tiers = Counter(c.total for c in default.ranked)

    # Preregistration drafts for the top-10.
    templates_dir = ROOT / "templates"
    templates_dir.mkdir(exist_ok=True)
    for stale in templates_dir.glob("*.json"):
        stale.unlink()
    template_files: list[str] = []
    for candidate in top10:
        draft = generate_prereg_draft(
            candidate, inputs.availability, inputs.short_labels
        )
        filename = _template_filename(candidate)
        (templates_dir / filename).write_text(
            json.dumps(draft, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        template_files.append(filename)

    # Full ranking JSON (deterministic: no timestamps inside).
    ranking_path = ROOT / "ranking.json"
    ranking_path.write_text(
        default.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )

    lines: list[str] = [
        "# Stage 6a hypothesis-planner validation report",
        "",
        f"- Validated at: {ran_at.isoformat()}",
        "- Offline and deterministic: fixed inputs, no network, no "
        "clock reads inside the scoring. Re-running reproduces "
        "`ranking.json` byte-identically and this report except "
        "this timestamp line.",
        f"- Registry: {inputs.node_count} nodes, {inputs.edge_count} "
        f"edges, {len(inputs.candidates)} "
        "candidates; content hash "
        f"`{inputs.registry_content_hash[:12]}...`",
        "- Availability: 12 nodes, all verified from study "
        "manifests (see `data_availability.json`); no unknown nodes.",
        "",
        "## What the planner is (and is not)",
        "",
        "The planner sorts untested pairs by three explicit "
        "components — adjacency to supported edges, data "
        "availability, power feasibility — under declared weights. "
        "It does not predict which hypothesis will be supported: "
        "adjacency is a graph fact, not evidence, and the ranking "
        "is a heuristic. The top-10 below is the first ten pairs "
        "in (source, target) order among the pairs tied at the top "
        "score — read it as 'these pass every stated screen', not "
        "as 'these are the ten most promising hypotheses'.",
        "",
        "## MDE cross-check (planner formulas vs the Stage 2B audit)",
        "",
        "Every audit MDE entry recomputed from its sample size with "
        "the planner's formulas (same analytic functions):",
        "",
    ]
    for check in checks:
        lines.append(
            f"- PASS: {check.label}: audit {check.audit_value:.6g}, "
            f"recomputed {check.recomputed_value:.6g}"
        )
    lines += [
        "",
        "## Ranking summary (default weights)",
        "",
        f"- Candidates: {default.total_candidates}",
        f"- Ranked: {len(default.ranked)}",
        f"- Excluded by the anti-retest guard: {len(default.excluded)}",
        f"- Unrankable: {len(default.unrankable)}",
        "",
        "Score tiers (default weights): "
        + ", ".join(
            f"{total:.2f} x {count}"
            for total, count in sorted(tiers.items(), reverse=True)
        )
        + ".",
        "",
        f"The top tier holds {tiers.get(1.0, 0)} pairs at 1.00: every "
        "component saturated (adjacent to a supported edge, both "
        "panels verified, MDE below the lab threshold). The top-10 "
        "is the first ten of that tier in lexicographic order — "
        "the tie, not the weights, decides it.",
        "",
        "## Top-10 shortlist",
        "",
    ]
    for candidate in top10:
        records = (
            ", ".join(candidate.decision_records)
            if candidate.decision_records
            else "none"
        )
        adjacent = (
            ", ".join(candidate.adjacent_supported_edges)
            if candidate.adjacent_supported_edges
            else "none"
        )
        lines += [
            f"### {candidate.rank}. {_pair(candidate)}",
            "",
            f"- Suggested test: {candidate.test_type.value} "
            f"({candidate.frequency}), mechanism "
            f"{candidate.mechanism.value}. {candidate.suggestion_reason}",
            f"- Score: {candidate.total:.2f} (adjacency "
            f"{candidate.adjacency:.1f}, data {candidate.data:.1f}, "
            f"power {_fmt(candidate.power, 1)})",
            f"- Joint n (estimated): {candidate.joint_n} — "
            f"{candidate.joint_n_basis}",
            f"- MDE: {_fmt(candidate.mde, 5)} "
            f"({candidate.mde_measure}, threshold "
            f"{candidate.mde_threshold})",
            f"- Adjacent supported edges: {adjacent}; decision "
            f"records: {records}",
            f"- Preregistration draft: `templates/"
            f"{_template_filename(candidate)}`",
            "",
        ]
    lines += [
        "## Excluded (anti-retest guard)",
        "",
    ]
    if default.excluded:
        for candidate in default.excluded:
            lines.append(
                f"- {_pair(candidate)}: {candidate.reason} "
                f"({candidate.edge_id})"
            )
    else:
        lines += [
            "None. The guard cannot fire on the current registry: "
            "candidates are by construction pairs with no tested "
            "edge, so no candidate matches a tested (pair, test "
            "type, condition). The guard is a safety net for future "
            "registries and manually supplied candidate lists; it "
            "is enforced in code and tested on synthetic inputs "
            "(`tests/test_planner.py`).",
        ]
    lines += [
        "",
        "## Unrankable",
        "",
    ]
    for candidate in default.unrankable:
        lines.append(f"- {_pair(candidate)}: {candidate.reason}")
    all_tyvix = all(
        "index:tyvix" in (c.source_instrument, c.target_instrument)
        for c in default.unrankable
    )
    if all_tyvix:
        unrankable_note = (
            f"All {len(default.unrankable)} unrankable pairs are TYVIX "
            "against post-2020-only nodes (crypto perpetuals, DVOL, "
            "CPI): the TYVIX panel ends 2020-05-15 (discontinued) "
            "while the crypto/DVOL/CPI panels start in 2021 — there "
            "is no overlapping window to test on. TYVIX cannot be "
            "extended. VXN was re-fetched past 2020 (see "
            "`vxn_refresh.json`); its 12 pairs moved from unrankable "
            "to ranked."
        )
    else:
        unrankable_note = (
            f"{len(default.unrankable)} pairs are unrankable; see the "
            "list above for the per-pair reasons."
        )
    lines += [
        "",
        unrankable_note,
        "",
        "## Weight sensitivity",
        "",
    ]
    for entry in sensitivity:
        lines += [
            f"### {entry['label']}",
            "",
            f"- Top-10 intersection with default: "
            f"{entry['intersection_with_default']}/10",
            f"- Entered the top-10: "
            f"{', '.join(entry['entered']) if entry['entered'] else 'none'}",
            f"- Left the top-10: "
            f"{', '.join(entry['left']) if entry['left'] else 'none'}",
            "",
        ]
    top_tier_count = tiers.get(1.0, 0)
    invariant = all(
        entry["intersection_with_default"] == SHORTLIST_SIZE
        for entry in sensitivity
    )
    if invariant:
        sensitivity_conclusion = (
            "Conclusion: the top-10 is weight-invariant in this run. "
            f"The {top_tier_count} pairs in the top tier saturate all "
            "three components, so they score 1.00 under any weights, "
            "and the top-10 is the same lexicographic slice of that "
            "tier under every weighting. The weights only reorder the "
            "lower tiers (under adjacency-heavy weights the "
            "adjacency-1/power-0 tier outranks the "
            "adjacency-0.5/power-1 tier; under power-heavy weights "
            "it is the other way round). The ranking's discriminating "
            "power is limited by its coarse components — a finer "
            "power component (e.g. a continuous MDE margin) would be "
            f"needed to break the {top_tier_count}-way tie, and that "
            "is a design decision for a later planner version, not "
            "something to smuggle in here."
        )
    else:
        sensitivity_conclusion = (
            "Conclusion: the top-10 is not weight-invariant in this "
            "run (see the intersections above). The top tier holds "
            f"only {top_tier_count} pairs at 1.00, so the lower tiers "
            "— which the weights reorder — fill the rest of the "
            "shortlist."
        )
    cross = [
        c for c in default.ranked if c.mechanism.value == "cross-section"
    ]
    cross_threshold = cross[0].mde_threshold if cross else 0.05
    cross_top = [c for c in cross if c.total == 1.0]
    cross_rest = [c for c in cross if c.total != 1.0]

    def _mde_text(pairs) -> str:
        distinct = sorted(
            {(c.joint_n, c.mde) for c in pairs if c.joint_n and c.mde}
        )
        return ", ".join(f"MDE {mde:.4f} at {n} events" for n, mde in distinct)

    vol_level_note = (
        "Vol-level, event-response and regime-conditional labels do "
        "not occur among candidates: level and event-response tests "
        "are self-loops (never candidates) and regime-conditional "
        "designs are follow-ups, not first tests."
    )
    if cross_top and cross_rest:
        top_text = "; ".join(
            f"{_pair(c)} (rank {c.rank}, {c.joint_n} events, "
            f"MDE {c.mde:.4f})"
            for c in cross_top
        )
        rest_lo = min(c.rank for c in cross_rest)
        rest_hi = max(c.rank for c in cross_rest)
        cross_note = (
            f"Cross-section pairs ({len(cross)}, all DGS10-sourced): "
            f"{len(cross_top)} "
            f"{'reaches' if len(cross_top) == 1 else 'reach'} "
            f"the top tier — {top_text} — "
            f"while the other {len(cross_rest)} sit at ranks "
            f"{rest_lo}–{rest_hi} with power 0 "
            f"({_mde_text(cross_rest)}, vs the {cross_threshold} "
            f"threshold). {vol_level_note}"
        )
    elif cross:
        lo = min(c.rank for c in cross)
        hi = max(c.rank for c in cross)
        cross_note = (
            f"Cross-section pairs ({len(cross)}, all DGS10-sourced) "
            f"sit at ranks {lo}–{hi}: their power component is 0 at "
            "every available event count "
            f"({_mde_text(cross)}, vs the {cross_threshold} "
            f"threshold), so they cannot reach the top tier. "
            f"{vol_level_note}"
        )
    else:
        cross_note = (
            "No cross-section pairs among the ranked candidates. "
            f"{vol_level_note}"
        )
    lines += [
        sensitivity_conclusion,
        "",
        "## Mechanism distribution",
        "",
        "- All ranked pairs: "
        + ", ".join(
            f"{label} {count}" for label, count in all_mechanisms.most_common()
        )
        + ".",
        "- Top-10: "
        + ", ".join(
            f"{label} {count}" for label, count in top_mechanisms.most_common()
        )
        + ".",
        "",
        cross_note,
        "",
        "## Full ranking (default weights)",
        "",
    ]
    lines += _ranking_lines(default)
    lines += [
        "",
        "## Limitations",
        "",
        f"- The ranking is a heuristic with coarse components: "
        f"{top_tier_count} pairs tie at the top score, so the top-10 "
        "is decided by the lexicographic tie-break, not by any "
        "discriminating evidence. Do not read it as a prediction.",
        "- Joint sample sizes are estimates (pro-rata by days from "
        "the verified per-node panels), not verified joint counts. "
        "The true joint row count must be confirmed when the study "
        "panel is built; the preregistration drafts mark it TODO.",
        "- The power component uses the analytic normal-approximation "
        "MDE at 80% power, α = 0.05, and ignores HAC/autocorrelation "
        "adjustments that would raise the true MDE (the audit's own "
        "caveat: the lead-lag MDE at n = 1,414 is essentially the "
        "lab's 0.005 threshold). A pair scored power 1 is "
        "'detectable in principle', not 'powered in practice'.",
        "- CPI-as-source pairs use daily rows for the MDE, matching "
        "the H0012 audit treatment; the effective sample size is 69 "
        "distinct step values, so their power scores are optimistic. "
        "Each such draft carries the caveat.",
        "- Event counts for cross-section designs are statement "
        "counts in the overlap window after an 84-calendar-day "
        "warm-up approximating the 60-trading-day estimation "
        "window; events dropped for data gaps (e.g. the 2004-11-10 "
        "DGS10 gap in study 005) are not subtracted.",
        "- VXN was re-fetched past 2020-05-15 (see "
        "`vxn_refresh.json`); its 12 pairs moved from unrankable to "
        "ranked. TYVIX cannot be extended (discontinued).",
        "- The planner knows nothing about economics: it cannot tell "
        "a plausible mechanism from a spurious pair, and it does not "
        "try. The mechanism label is a classification of the "
        "suggested design, not a judgement about the market.",
        "",
    ]
    report_path = ROOT / "validation_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"ranking written: {ranking_path}")
    print(f"report written: {report_path}")
    print(f"templates written: {len(template_files)} in {templates_dir}")
    print(
        f"ranked {len(default.ranked)}, excluded {len(default.excluded)}, "
        f"unrankable {len(default.unrankable)}; "
        f"MDE cross-checks passed: {len(checks)}/{len(checks)}"
    )


if __name__ == "__main__":
    main()
