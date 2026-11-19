"""Tests for the Stage 6a hypothesis planner.

Most tests run on a hand-built synthetic graph (small node set,
known edges, known panels) with hand-computed expectations — the
planner core takes plain inputs precisely so the guard and the
scoring are testable without a strict registry (which would reject
a candidate duplicating a tested pair). A few tests load the real
registry read-only to guard the loader and the real ranking.

Synthetic graph (all panels daily unless noted):

- a, b, g, h: 2010-01-01 -> 2024-12-31, 3000 rows.
- c: 2020-01-01 -> 2024-12-31, 1000 rows.
- d: 2024-01-01 -> 2024-12-31, 200 rows.
- e: no panel record (unknown).
- f: panel verified unavailable.

Tested edges: E0001 a->b lead_lag unconditional SUPPORTED;
E0002 b->c lead_lag unconditional REJECTED; E0003 a->d lead_lag
conditional REJECTED; E0004 c->d lead_lag unconditional
DESCRIPTIVE (ignored by guard and tiers); E0005 b->g lead_lag
unconditional REJECTED; E0006 a->h lead_lag unconditional
REJECTED. Tiers: a, b = 1.0; c, d, g, h = 0.5 (adjacent to a/b);
e, f = 0.

Joint n (pro-rata): a/b/g/h pairs 3000 (power 1); a/c pairs 1000
(power 0); a/d, c/d pairs 200 (power 0).
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from myquant.graph import EdgeStatus, EdgeTestType
from myquant.planner import (
    TODO,
    AvailabilityConfig,
    CandidatePair,
    PanelAvailability,
    PanelStatus,
    PlannerConfig,
    PlannerWeights,
    TestedEdge,
    adjacency_tiers,
    apply_guard,
    data_component,
    estimate_joint_n,
    generate_prereg_draft,
    load_planner_inputs,
    mde_cross_check,
    power_component,
    rank_candidates,
    suggest_test,
)
from myquant.planner.scoring import MechanismLabel

REPO_ROOT = Path(__file__).resolve().parents[1]


def _panel(
    instrument_id: str,
    first: str,
    last: str,
    rows: int,
    *,
    status: PanelStatus = PanelStatus.AVAILABLE,
) -> PanelAvailability:
    return PanelAvailability(
        instrument_id=instrument_id,
        status=status,
        source="synthetic",
        first=date.fromisoformat(first) if status is PanelStatus.AVAILABLE else None,
        last=date.fromisoformat(last) if status is PanelStatus.AVAILABLE else None,
        rows=rows if status is PanelStatus.AVAILABLE else 0,
        verified_by="synthetic test fixture",
    )


def _availability() -> AvailabilityConfig:
    return AvailabilityConfig(
        panels=(
            _panel("a", "2010-01-01", "2024-12-31", 3000),
            _panel("b", "2010-01-01", "2024-12-31", 3000),
            _panel("c", "2020-01-01", "2024-12-31", 1000),
            _panel("d", "2024-01-01", "2024-12-31", 200),
            _panel("f", "2010-01-01", "2024-12-31", 0, status=PanelStatus.UNAVAILABLE),
            _panel("g", "2010-01-01", "2024-12-31", 3000),
            _panel("h", "2010-01-01", "2024-12-31", 3000),
        )
    )


def _tested_edges() -> tuple[TestedEdge, ...]:
    def edge(
        edge_id: str,
        source: str,
        target: str,
        condition: str | None,
        status: EdgeStatus,
    ) -> TestedEdge:
        return TestedEdge(
            edge_id=edge_id,
            source_instrument=source,
            target_instrument=target,
            test_type=EdgeTestType.LEAD_LAG,
            condition=condition,
            status=status,
        )

    return (
        edge("E0001", "a", "b", None, EdgeStatus.SUPPORTED),
        edge("E0002", "b", "c", None, EdgeStatus.REJECTED),
        edge("E0003", "a", "d", "some condition", EdgeStatus.REJECTED),
        edge("E0004", "c", "d", None, EdgeStatus.DESCRIPTIVE),
        edge("E0005", "b", "g", None, EdgeStatus.REJECTED),
        edge("E0006", "a", "h", None, EdgeStatus.REJECTED),
    )


def _candidates() -> tuple[CandidatePair, ...]:
    pairs = [
        ("b", "a"),
        ("a", "f"),
        ("f", "a"),
        ("g", "h"),
        ("h", "g"),
        ("a", "c"),
        ("c", "a"),
        ("c", "b"),
        ("d", "a"),
        ("c", "d"),
        ("d", "c"),
        ("a", "d"),
        ("a", "b"),
        ("b", "c"),
        ("a", "e"),
        ("e", "a"),
    ]
    return tuple(
        CandidatePair(source_instrument=s, target_instrument=t) for s, t in pairs
    )


def _rank(config: PlannerConfig | None = None):
    return rank_candidates(
        _candidates(),
        _tested_edges(),
        _availability(),
        (),
        {"E0001": "DR-E0001"},
        config,
    )


def test_suggest_test_mapping() -> None:
    assert suggest_test("x", "macro:cpi-mom").frequency == "monthly"
    assert suggest_test("x", "macro:cpi-mom").test_type is EdgeTestType.LEAD_LAG
    cross = suggest_test("rates:us-10y-yield", "index:tyvix")
    assert cross.test_type is EdgeTestType.CROSS_SECTION
    assert cross.mechanism is MechanismLabel.CROSS_SECTION
    default = suggest_test("a", "b")
    assert default.test_type is EdgeTestType.LEAD_LAG
    assert default.frequency == "daily"
    assert default.mechanism is MechanismLabel.TRANSMISSION


def test_adjacency_tiers() -> None:
    tiers, supported = adjacency_tiers(_tested_edges())
    assert tiers["a"] == 1.0
    assert tiers["b"] == 1.0
    assert tiers["c"] == 0.5
    assert tiers["d"] == 0.5
    assert tiers["g"] == 0.5
    assert tiers["h"] == 0.5
    assert "e" not in tiers
    assert supported["a"] == ("E0001",)
    assert supported["b"] == ("E0001",)


def test_adjacency_tier_values_are_configurable() -> None:
    """The tier values in PlannerConfig reach the ranking.

    Regression test: the config declared adjacency_tier_direct /
    adjacency_tier_one_hop but rank_candidates ignored them and
    the tiers were hard-coded 1.0 / 0.5.
    """
    tiers, _ = adjacency_tiers(_tested_edges(), direct=1.0, one_hop=0.25)
    assert tiers["a"] == 1.0
    assert tiers["c"] == 0.25
    default = _rank()
    one_hop = next(c for c in default.ranked if c.adjacency == 0.5)
    custom = _rank(PlannerConfig(adjacency_tier_one_hop=0.25))
    match = next(
        c
        for c in custom.ranked
        if (c.source_instrument, c.target_instrument)
        == (one_hop.source_instrument, one_hop.target_instrument)
    )
    assert match.adjacency == 0.25
    assert match.total < one_hop.total


def test_data_component() -> None:
    available = _panel("a", "2010-01-01", "2024-12-31", 3000)
    unavailable = _panel(
        "f", "2010-01-01", "2024-12-31", 0, status=PanelStatus.UNAVAILABLE
    )
    assert data_component(available, available) == 1.0
    assert data_component(available, unavailable) == 0.5
    assert data_component(unavailable, unavailable) == 0.0


def test_power_component_thresholds() -> None:
    config = PlannerConfig()
    lead_lag = config.threshold_for(EdgeTestType.LEAD_LAG)
    assert lead_lag is not None
    # Audit value at n = 1414 is 0.005520192649316948 (summary.json).
    score, mde, _ = power_component(EdgeTestType.LEAD_LAG, 1414, lead_lag)
    assert score == 0.0
    assert mde is not None and abs(mde - 0.005520192649316948) < 1e-12
    score, mde, _ = power_component(EdgeTestType.LEAD_LAG, 3000, lead_lag)
    assert score == 1.0
    assert mde is not None and mde < 0.005
    cross = config.threshold_for(EdgeTestType.CROSS_SECTION)
    assert cross is not None
    # Audit value at n = 135 is 0.054945336280868076 (summary.json).
    score, mde, _ = power_component(EdgeTestType.CROSS_SECTION, 135, cross)
    assert score == 0.0
    assert mde is not None and abs(mde - 0.054945336280868076) < 1e-12
    score, _, _ = power_component(EdgeTestType.CROSS_SECTION, 200, cross)
    assert score == 1.0
    event = config.threshold_for(EdgeTestType.EVENT_STUDY)
    assert event is not None
    score, mde, _ = power_component(EdgeTestType.EVENT_STUDY, 135, event)
    assert score == 1.0
    assert mde is not None and abs(mde - 0.21400168279054138) < 1e-12
    score, _, _ = power_component(EdgeTestType.EVENT_STUDY, 45, event)
    assert score == 0.0
    mean = config.threshold_for(EdgeTestType.MEAN_COMPARISON)
    score, mde, note = power_component(
        EdgeTestType.MEAN_COMPARISON, 1000, mean
    )
    assert score is None and mde is None
    assert note is not None and "group sizes" in note
    score, mde, _ = power_component(EdgeTestType.LEAD_LAG, 3000, None)
    assert score is None and mde is None


def test_guard_exact_retest_excluded() -> None:
    outcome = apply_guard("a", "b", EdgeTestType.LEAD_LAG, _tested_edges())
    assert outcome.excluded and not outcome.downgraded
    assert outcome.edge_id == "E0001"
    assert outcome.reason is not None and "E0001" in outcome.reason
    outcome = apply_guard("b", "c", EdgeTestType.LEAD_LAG, _tested_edges())
    assert outcome.excluded and outcome.edge_id == "E0002"


def test_guard_different_setting_downgraded() -> None:
    outcome = apply_guard("a", "d", EdgeTestType.LEAD_LAG, _tested_edges())
    assert not outcome.excluded and outcome.downgraded
    assert outcome.edge_id == "E0003"
    assert outcome.reason is not None and "different setting" in outcome.reason
    # Descriptive edges never trigger the guard.
    outcome = apply_guard("c", "d", EdgeTestType.LEAD_LAG, _tested_edges())
    assert not outcome.excluded and not outcome.downgraded
    # A supported edge on the same pair under a different test type
    # neither excludes nor downgrades (follow-up, not a re-test).
    outcome = apply_guard("a", "b", EdgeTestType.CROSS_SECTION, _tested_edges())
    assert not outcome.excluded and not outcome.downgraded


def test_ranking_hand_computed() -> None:
    result = _rank()
    assert result.total_candidates == 16
    assert len(result.ranked) == 12
    assert len(result.excluded) == 2
    assert len(result.unrankable) == 2
    order = [
        (c.source_instrument, c.target_instrument, c.total) for c in result.ranked
    ]
    assert order == [
        ("b", "a", 1.0),
        ("g", "h", 0.8),
        ("h", "g", 0.8),
        ("a", "f", 0.7857142857),
        ("f", "a", 0.7857142857),
        ("a", "c", 0.7),
        ("c", "a", 0.7),
        ("c", "b", 0.7),
        ("d", "a", 0.7),
        ("c", "d", 0.5),
        ("d", "c", 0.5),
        ("a", "d", 0.35),
    ]
    assert [c.rank for c in result.ranked] == list(range(1, 13))
    # Tie-break is lexicographic within equal scores.
    assert result.ranked[1].source_instrument == "g"
    assert result.ranked[5].source_instrument == "a"
    # Downgrade: a->d keeps half of 0.7 and carries the reason.
    downgraded = result.ranked[-1]
    assert downgraded.downgraded
    assert downgraded.downgrade_reason is not None
    assert "E0003" in downgraded.downgrade_reason
    # Power-None pairs renormalize instead of scoring 0.
    f_pair = result.ranked[3]
    assert f_pair.power is None
    assert f_pair.joint_n is None
    assert f_pair.data == 0.5
    # Supported-edge adjacency cites the decision record.
    top = result.ranked[0]
    assert top.adjacent_supported_edges == ("E0001",)
    assert top.decision_records == ("DR-E0001",)
    # Excluded and unrankable lists carry reasons.
    assert {c.edge_id for c in result.excluded} == {"E0001", "E0002"}
    assert all("unknown" in c.reason for c in result.unrankable)
    assert {c.source_instrument for c in result.unrankable} == {"a", "e"}


def test_unknown_data_unrankable() -> None:
    result = rank_candidates(
        (CandidatePair(source_instrument="a", target_instrument="zzz"),),
        _tested_edges(),
        _availability(),
        (),
        {},
    )
    assert len(result.ranked) == 0
    assert len(result.unrankable) == 1
    assert "zzz" in result.unrankable[0].reason


def test_zero_overlap_unrankable() -> None:
    availability = AvailabilityConfig(
        panels=(
            _panel("a", "2010-01-01", "2010-12-31", 300),
            _panel("b", "2020-01-01", "2020-12-31", 300),
        )
    )
    result = rank_candidates(
        (CandidatePair(source_instrument="a", target_instrument="b"),),
        (),
        availability,
        (),
        {},
    )
    assert len(result.ranked) == 0
    assert len(result.unrankable) == 1
    assert "no overlapping panel window" in result.unrankable[0].reason


def test_weight_sensitivity_changes_top3() -> None:
    default = _rank()
    heavy = _rank(
        PlannerConfig(
            weights=PlannerWeights(adjacency=0.6, data=0.2, power=0.2)
        )
    )
    default_top3 = [
        (c.source_instrument, c.target_instrument)
        for c in default.ranked[:3]
    ]
    heavy_top3 = [
        (c.source_instrument, c.target_instrument) for c in heavy.ranked[:3]
    ]
    assert default_top3 == [("b", "a"), ("g", "h"), ("h", "g")]
    assert heavy_top3 == [("b", "a"), ("a", "f"), ("f", "a")]
    assert default_top3 != heavy_top3
    # And the flip is the documented one: adjacency-1/power-0 pairs
    # outrank adjacency-0.5/power-1 pairs under adjacency-heavy weights.
    heavy_scores = {
        (c.source_instrument, c.target_instrument): c.total
        for c in heavy.ranked
    }
    assert heavy_scores[("a", "c")] == 0.8
    assert heavy_scores[("g", "h")] == 0.7


def test_ranking_deterministic() -> None:
    first = _rank().model_dump_json()
    second = _rank().model_dump_json()
    assert first == second


def test_weights_must_sum_to_one() -> None:
    with pytest.raises(ValueError, match="sum to 1.0"):
        PlannerWeights(adjacency=0.5, data=0.5, power=0.5)


def test_estimate_joint_n_cross_section_warmup() -> None:
    availability = AvailabilityConfig(
        panels=(
            _panel("rates:us-10y-yield", "2010-01-01", "2024-12-31", 3000),
            _panel("index:tyvix", "2010-01-01", "2020-12-31", 2000),
        )
    )
    fomc = (
        date(2010, 1, 27),  # inside the warm-up: excluded
        date(2015, 1, 28),
        date(2016, 1, 27),
        date(2020, 12, 31),  # event window needs 2021-01-01: excluded
        date(2021, 1, 27),  # past the target panel: excluded
    )
    suggested = suggest_test("rates:us-10y-yield", "index:tyvix")
    n, basis = estimate_joint_n(
        availability.panel("rates:us-10y-yield"),
        availability.panel("index:tyvix"),
        suggested,
        fomc,
        event_warmup_days=84,
    )
    assert n == 2
    assert "warm-up" in basis


def test_estimate_joint_n_cpi_step_and_monthly() -> None:
    cpi = PanelAvailability(
        instrument_id="macro:cpi-mom",
        source="synthetic",
        first=date(2020, 11, 1),
        last=date(2024, 10, 1),
        rows=48,
        verified_by="synthetic test fixture",
        step_start=date(2021, 1, 13),
    )
    from myquant.planner.config import PanelCalendar

    cpi = cpi.model_copy(update={"calendar": PanelCalendar.MONTHLY})
    target = _panel("x", "2020-01-01", "2024-12-31", 1000)
    suggested = suggest_test("macro:cpi-mom", "x")
    assert suggested.frequency == "daily"
    n, _ = estimate_joint_n(cpi, target, suggested, (), event_warmup_days=84)
    # Target rows from the first release (2021-01-13) to panel end:
    # 1000 * 1449/1827 = 793.
    assert n == 793
    suggested_monthly = suggest_test("x", "macro:cpi-mom")
    assert suggested_monthly.frequency == "monthly"
    n, _ = estimate_joint_n(
        target, cpi, suggested_monthly, (), event_warmup_days=84
    )
    # Months 2020-11..2024-10 = 48.
    assert n == 48


def test_template_known_fields_and_todos(tmp_path: Path) -> None:
    result = _rank()
    top = result.ranked[0]
    draft = generate_prereg_draft(top, _availability())
    assert draft["draft"] is True
    assert draft["hypothesis_id"] == TODO
    assert draft["mechanism"] == TODO
    assert draft["benchmark"] == TODO
    assert draft["universe"] == ["b", "a"]
    assert draft["minimum_effect_size"] == 0.005
    assert draft["suggested_test_type"] == "lead_lag"
    assert draft["sample_period"]["estimated_joint_rows"] == 3000
    assert draft["adjacent_supported_edges"] == ["E0001"]
    assert draft["decision_records"] == ["DR-E0001"]
    assert "b" in draft["research_question"]
    # Cross-section draft uses the CAR criteria.
    availability = AvailabilityConfig(
        panels=(
            _panel("rates:us-10y-yield", "2010-01-01", "2024-12-31", 3000),
            _panel("index:tyvix", "2010-01-01", "2020-12-31", 2000),
        )
    )
    cross = rank_candidates(
        (CandidatePair(
            source_instrument="rates:us-10y-yield",
            target_instrument="index:tyvix",
        ),),
        (),
        availability,
        (date(2015, 1, 28), date(2016, 1, 27)),
        {},
    ).ranked[0]
    draft = generate_prereg_draft(cross, availability)
    assert draft["suggested_test_type"] == "cross_section"
    assert draft["minimum_effect_size"] == 0.05
    assert any("R-squared at least 0.05" in c for c in draft["acceptance_criteria"])


def test_template_generation_does_not_touch_registry(tmp_path: Path) -> None:
    registry_path = REPO_ROOT / "research/graph/registry.json"
    before = hashlib.sha256(registry_path.read_bytes()).hexdigest()
    result = _rank()
    draft_path = tmp_path / "draft.json"
    draft_path.write_text(
        json.dumps(
            generate_prereg_draft(result.ranked[0], _availability()),
            indent=2,
            sort_keys=True,
        )
    )
    after = hashlib.sha256(registry_path.read_bytes()).hexdigest()
    assert before == after
    assert draft_path.exists()


def test_loader_real_registry() -> None:
    inputs = load_planner_inputs(REPO_ROOT)
    assert len(inputs.candidates) == 120
    assert len(inputs.tested_edges) == 42
    assert inputs.node_count == 12
    assert len(inputs.fomc_statement_dates) == 199
    assert set(inputs.decision_records) == {
        "E0023",
        "E0026",
        "E0030",
        "E0031",
        "E0032",
        "E0033",
    }
    assert inputs.decision_records["E0030"] == "DR-E0030"


def test_mde_cross_check_real_audit() -> None:
    summary = json.loads(
        (REPO_ROOT / "research/statistical-audit-2b/summary.json").read_text()
    )
    checks = mde_cross_check(summary)
    assert len(checks) == 18
    assert all(check.passed for check in checks)


def test_real_ranking_counts_and_top() -> None:
    inputs = load_planner_inputs(REPO_ROOT)
    result = rank_candidates(
        inputs.candidates,
        inputs.tested_edges,
        inputs.availability,
        inputs.fomc_statement_dates,
        inputs.decision_records,
    )
    assert len(result.ranked) == 108
    assert len(result.excluded) == 0
    assert len(result.unrankable) == 12
    top = result.ranked[0]
    assert top.source_instrument == "credit:baa-10y-spread"
    assert top.target_instrument == "index:vxn"
    assert top.total == 1.0
    # Every unrankable pair involves TYVIX (discontinued 2020-05-15)
    # against a post-2020-only node. VXN was re-fetched past 2020
    # (see research/planner-6a/vxn_refresh.json); its 12 pairs are
    # ranked now.
    assert all(
        c.source_instrument == "index:tyvix"
        or c.target_instrument == "index:tyvix"
        for c in result.unrankable
    )
    # The top tier is a 32-way tie at 1.00.
    assert sum(1 for c in result.ranked if c.total == 1.0) == 32
    # Cross-section pairs: 7, all DGS10-sourced. One reaches the top
    # tier — DGS10->VXN, whose overlap window now runs to 2026 (188
    # FOMC events, MDE below the 0.05 threshold); the other six have
    # power 0.
    cross = [c for c in result.ranked if c.test_type is EdgeTestType.CROSS_SECTION]
    assert len(cross) == 7
    powered = [c for c in cross if c.power == 1.0]
    assert len(powered) == 1
    assert powered[0].source_instrument == "rates:us-10y-yield"
    assert powered[0].target_instrument == "index:vxn"
    assert powered[0].total == 1.0
    assert powered[0].joint_n == 188
    assert all(
        c.power == 0.0
        for c in cross
        if (c.source_instrument, c.target_instrument)
        != ("rates:us-10y-yield", "index:vxn")
    )
    # The 12 recovered VXN pairs are all ranked, all with power 0:
    # the daily pairs' joint-n estimates (1,422-1,470) sit just
    # under the sample size the 0.005 lead-lag threshold needs
    # (MDEs 0.00531-0.00549); the monthly VXN->CPI pair has 72
    # months (MDE 0.0983).
    post_2020 = {
        "crypto:btc-usdt-perp",
        "crypto:eth-usdt-perp",
        "crypto:sol-usdt-perp",
        "index:btc-dvol",
        "index:eth-dvol",
        "macro:cpi-mom",
    }
    recovered = [
        c
        for c in result.ranked
        if "index:vxn" in (c.source_instrument, c.target_instrument)
        and (
            c.source_instrument in post_2020
            or c.target_instrument in post_2020
        )
    ]
    assert len(recovered) == 12
    assert all(c.power == 0.0 for c in recovered)


def test_vxn_availability_matches_refresh_manifest() -> None:
    """The VXN availability node agrees with the refresh manifest.

    The refresh script writes both files; this test guards against
    a hand edit drifting one away from the other. Offline: it reads
    committed files only.
    """
    planner_dir = REPO_ROOT / "research" / "planner-6a"
    manifest = json.loads((planner_dir / "vxn_refresh.json").read_text())
    availability = json.loads(
        (planner_dir / "data_availability.json").read_text()
    )
    vxn = next(
        p
        for p in availability["panels"]
        if p["instrument_id"] == "index:vxn"
    )
    full = manifest["full_series"]
    assert vxn["rows"] == full["rows"]
    assert vxn["first"] == full["first_date"]
    assert vxn["last"] == full["last_date"]
    assert "vxn_refresh.json" in vxn["verified_by"]
    # The overlap segment of the new pull matches the study-003
    # manifest aggregates exactly (aggregate-level check; see the
    # refresh manifest for the method and its limitation).
    assert manifest["overlap_check"]["matches_study_003_manifest"] is True
    assert manifest["overlap_check"]["rows"] == 4372
    assert manifest["overlap_check"]["missing_values"] == 161
