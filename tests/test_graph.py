"""Tests for the market graph and edge registry (src/myquant/graph.py).

Unit tests use small synthetic registries. Builder tests (traceability
against the real trial ledgers, determinism, committed-registry drift)
live further down this file and run the builder from research/graph/.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from myquant.graph import (
    CandidateRecord,
    CostGateRecord,
    CostGateVerdict,
    EdgeRecord,
    EdgeStatus,
    EdgeTestType,
    ForwardSampleRecord,
    GraphRegistry,
    MarketGraph,
    NodeRecord,
    SampleRecord,
    build_candidates,
    compute_content_hash,
    render_mermaid,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILDER = REPO_ROOT / "research" / "graph" / "build_graph.py"
REGISTRY_PATH = REPO_ROOT / "research" / "graph" / "registry.json"

T0 = datetime(2023, 1, 2, 16, tzinfo=UTC)
T1 = datetime(2026, 11, 16, 16, tzinfo=UTC)


def make_node(instrument_id: str, short_label: str, asset_class: str = "crypto"):
    return NodeRecord(
        instrument_id=instrument_id,
        short_label=short_label,
        name=f"{short_label} instrument",
        asset_class=asset_class,
        instrument_type="perpetual",
        calendar_id="crypto-24-7",
        studies=("btc-eth-001",),
    )


def make_edge(edge_id: str, source: str, target: str, **overrides):
    values = {
        "edge_id": edge_id,
        "status": EdgeStatus.REJECTED,
        "source_instrument": source,
        "target_instrument": target,
        "frequency": "daily",
        "lag_steps": 1,
        "condition": None,
        "method": "partial lead-lag OLS, lag 1, Newey-West HAC",
        "common_factor_control": "SOL[t] log return",
        "data_sources": ("okx-public@v1",),
        "hypothesis_id": "H0001",
        "hypothesis_version": 1,
        "trial_id": "T0001",
        "preregistration_fingerprint": "ab" * 32,
        "trial_record_hash": "cd" * 32,
        "report_path": "docs/studies/btc-eth-transmission-001.md",
        "ledger_path": "research/btc-eth-001/trials.jsonl",
        "ledger_test_key": "daily_btc_eth",
        "coefficient": 0.0252,
        "standard_error": 0.0697,
        "t_statistic": 0.36,
        "p_value": 0.718,
        "holm_adjusted_p_value": 1.0,
        "partial_r_squared": 0.00011,
        "incremental_r_squared": 0.00011,
        "observations": 1414,
        "sample": SampleRecord(
            first=T0, last=T1, panel_rows=1415, observations=1414
        ),
        "holdout_oos_incremental_r_squared": -0.00095,
        "holdout_oos_note": "Holdout window only.",
        "cost_gate": CostGateRecord(
            verdict=CostGateVerdict.FAIL,
            net_daily_edge=-0.00087,
            gross_daily_edge=-0.0004,
            bootstrap_p_value=0.657,
            ci_lower=-0.0044,
            ci_upper=0.0028,
            days=318,
            note="Sign rule on holdout OOS forecasts.",
        ),
        "cost_gate_note": None,
        "forward_sample": None,
        "verdict_summary": "Hypothesis H0001 REJECTED (trial T0001).",
        "notes": (),
    }
    values.update(overrides)
    return EdgeRecord(**values)


def make_registry(nodes, edges, candidates=(), provenance=()):
    content_hash = compute_content_hash(
        schema_version=1,
        nodes=nodes,
        edges=edges,
        candidates=candidates,
        provenance=provenance,
    )
    return GraphRegistry(
        schema_version=1,
        nodes=nodes,
        edges=edges,
        candidates=candidates,
        provenance=provenance,
        content_hash=content_hash,
    )


def make_three_node_graph():
    nodes = (
        make_node("crypto:btc-usdt-perp", "BTC"),
        make_node("crypto:eth-usdt-perp", "ETH"),
        make_node("crypto:sol-usdt-perp", "SOL"),
    )
    edges = (
        make_edge("E0001", "crypto:btc-usdt-perp", "crypto:eth-usdt-perp"),
    )
    candidates = build_candidates(nodes, edges)
    return make_registry(nodes, edges, candidates)


# --- Edge record shape validation ---


def test_tested_edge_requires_full_statistics():
    with pytest.raises(ValidationError, match="full test statistics"):
        make_edge(
            "E0001",
            "crypto:btc-usdt-perp",
            "crypto:eth-usdt-perp",
            coefficient=None,
        )


def test_tested_edge_requires_trial():
    with pytest.raises(ValidationError, match="needs a trial"):
        make_edge(
            "E0001",
            "crypto:btc-usdt-perp",
            "crypto:eth-usdt-perp",
            trial_id=None,
        )


def test_edge_cannot_point_at_itself():
    with pytest.raises(ValidationError, match="cannot point at its own"):
        make_edge(
            "E0001", "crypto:btc-usdt-perp", "crypto:btc-usdt-perp"
        )


def test_lead_lag_edge_requires_lag_steps():
    with pytest.raises(ValidationError, match="needs lag_steps"):
        make_edge(
            "E0001",
            "crypto:btc-usdt-perp",
            "crypto:eth-usdt-perp",
            lag_steps=None,
        )


def test_mean_comparison_edge_is_a_self_loop_without_lag_or_partial_r2():
    edge = make_edge(
        "E0017",
        "crypto:btc-usdt-perp",
        "crypto:btc-usdt-perp",
        test_type=EdgeTestType.MEAN_COMPARISON,
        lag_steps=None,
        partial_r_squared=None,
        incremental_r_squared=None,
        method="mean abs log-return comparison, OLS + HAC",
        common_factor_control=None,
        holdout_oos_incremental_r_squared=None,
        holdout_oos_note="No OOS score: level comparison, not a forecast.",
        cost_gate=None,
        cost_gate_note="No cost gate: level comparison, not a forecast.",
    )
    assert edge.test_type is EdgeTestType.MEAN_COMPARISON
    assert edge.lag_steps is None
    assert edge.partial_r_squared is None


def test_mean_comparison_edge_rejects_a_lag():
    with pytest.raises(ValidationError, match="has no lag"):
        make_edge(
            "E0017",
            "crypto:btc-usdt-perp",
            "crypto:btc-usdt-perp",
            test_type=EdgeTestType.MEAN_COMPARISON,
            lag_steps=1,
            partial_r_squared=None,
            incremental_r_squared=None,
        )


def test_mean_comparison_edge_rejects_partial_r_squared():
    with pytest.raises(ValidationError, match="must not carry lead-lag"):
        make_edge(
            "E0017",
            "crypto:btc-usdt-perp",
            "crypto:btc-usdt-perp",
            test_type=EdgeTestType.MEAN_COMPARISON,
            lag_steps=None,
            partial_r_squared=0.001,
            incremental_r_squared=None,
        )


def test_mean_comparison_edge_must_be_a_self_loop():
    with pytest.raises(ValidationError, match="must be a self-loop"):
        make_edge(
            "E0017",
            "crypto:btc-usdt-perp",
            "crypto:eth-usdt-perp",
            test_type=EdgeTestType.MEAN_COMPARISON,
            lag_steps=None,
            partial_r_squared=None,
            incremental_r_squared=None,
        )


def test_mermaid_labels_mean_comparison_edges_as_self_loops():
    nodes = (
        make_node("crypto:btc-usdt-perp", "BTC"),
        make_node("crypto:eth-usdt-perp", "ETH"),
    )
    edge = make_edge(
        "E0017",
        "crypto:btc-usdt-perp",
        "crypto:btc-usdt-perp",
        test_type=EdgeTestType.MEAN_COMPARISON,
        lag_steps=None,
        partial_r_squared=None,
        incremental_r_squared=None,
        coefficient=0.0012,
        method="mean abs log-return comparison, OLS + HAC",
        common_factor_control=None,
        holdout_oos_incremental_r_squared=None,
        holdout_oos_note="No OOS score.",
        cost_gate=None,
        cost_gate_note="No cost gate.",
    )
    registry = make_registry(nodes, (edge,), build_candidates(nodes, (edge,)))
    rendered = render_mermaid(registry)
    assert "BTC -->|E0017 daily, mean abs-return diff +0.0012" in rendered
    assert "BTC -->|E0017" in rendered


def test_event_study_edge_is_a_self_loop_without_lag_or_partial_r2():
    edge = make_edge(
        "E0019",
        "index:vix",
        "index:vix",
        test_type=EdgeTestType.EVENT_STUDY,
        lag_steps=None,
        partial_r_squared=None,
        incremental_r_squared=None,
        method="constant-mean event study, CAR[0,+1], cluster inference",
        common_factor_control=None,
        holdout_oos_incremental_r_squared=None,
        holdout_oos_note="No OOS score: event study, not a forecast.",
        cost_gate=None,
        cost_gate_note="No cost gate: event study, not a forecast.",
    )
    assert edge.test_type is EdgeTestType.EVENT_STUDY
    assert edge.lag_steps is None
    assert edge.partial_r_squared is None


def test_event_study_edge_rejects_a_lag():
    with pytest.raises(ValidationError, match="has no lag"):
        make_edge(
            "E0019",
            "index:vix",
            "index:vix",
            test_type=EdgeTestType.EVENT_STUDY,
            lag_steps=1,
            partial_r_squared=None,
            incremental_r_squared=None,
        )


def test_event_study_edge_rejects_partial_r_squared():
    with pytest.raises(ValidationError, match="must not carry lead-lag"):
        make_edge(
            "E0019",
            "index:vix",
            "index:vix",
            test_type=EdgeTestType.EVENT_STUDY,
            lag_steps=None,
            partial_r_squared=0.001,
            incremental_r_squared=None,
        )


def test_event_study_edge_must_be_a_self_loop():
    with pytest.raises(ValidationError, match="must be a self-loop"):
        make_edge(
            "E0019",
            "index:vix",
            "index:tyvix",
            test_type=EdgeTestType.EVENT_STUDY,
            lag_steps=None,
            partial_r_squared=None,
            incremental_r_squared=None,
        )


def test_cross_section_edge_is_directed_without_lag_or_partial_r2():
    edge = make_edge(
        "E0024",
        "rates:us-10y-yield",
        "index:sp500",
        test_type=EdgeTestType.CROSS_SECTION,
        lag_steps=None,
        partial_r_squared=None,
        incremental_r_squared=None,
        method="cross-event OLS of SPX CAR on DGS10 CAR, HC0 standard errors",
        common_factor_control=None,
        holdout_oos_incremental_r_squared=None,
        holdout_oos_note="No OOS score: event study, not a forecast.",
        cost_gate=None,
        cost_gate_note="No cost gate: event study, not a forecast.",
    )
    assert edge.test_type is EdgeTestType.CROSS_SECTION
    assert edge.lag_steps is None
    assert edge.partial_r_squared is None


def test_cross_section_edge_rejects_a_lag():
    with pytest.raises(ValidationError, match="has no lag"):
        make_edge(
            "E0024",
            "rates:us-10y-yield",
            "index:sp500",
            test_type=EdgeTestType.CROSS_SECTION,
            lag_steps=1,
            partial_r_squared=None,
            incremental_r_squared=None,
        )


def test_cross_section_edge_rejects_partial_r_squared():
    with pytest.raises(ValidationError, match="must not carry lead-lag"):
        make_edge(
            "E0024",
            "rates:us-10y-yield",
            "index:sp500",
            test_type=EdgeTestType.CROSS_SECTION,
            lag_steps=None,
            partial_r_squared=0.05,
            incremental_r_squared=None,
        )


def test_cross_section_edge_rejects_a_self_loop():
    with pytest.raises(ValidationError, match="cannot point at its own"):
        make_edge(
            "E0024",
            "index:sp500",
            "index:sp500",
            test_type=EdgeTestType.CROSS_SECTION,
            lag_steps=None,
            partial_r_squared=None,
            incremental_r_squared=None,
        )


def test_mermaid_labels_event_study_and_cross_section_edges():
    nodes = (
        make_node("index:vix", "VIX"),
        make_node("rates:us-10y-yield", "DGS10"),
        make_node("index:sp500", "SPX"),
    )
    event_edge = make_edge(
        "E0019",
        "index:vix",
        "index:vix",
        test_type=EdgeTestType.EVENT_STUDY,
        lag_steps=None,
        partial_r_squared=None,
        incremental_r_squared=None,
        coefficient=-0.03,
        method="constant-mean event study",
        common_factor_control=None,
        holdout_oos_incremental_r_squared=None,
        holdout_oos_note="No OOS score.",
        cost_gate=None,
        cost_gate_note="No cost gate.",
    )
    cross_edge = make_edge(
        "E0024",
        "rates:us-10y-yield",
        "index:sp500",
        test_type=EdgeTestType.CROSS_SECTION,
        lag_steps=None,
        partial_r_squared=None,
        incremental_r_squared=None,
        coefficient=-0.5,
        method="cross-event OLS, HC0",
        common_factor_control=None,
        holdout_oos_incremental_r_squared=None,
        holdout_oos_note="No OOS score.",
        cost_gate=None,
        cost_gate_note="No cost gate.",
    )
    edges = (event_edge, cross_edge)
    registry = make_registry(nodes, edges, build_candidates(nodes, edges))
    rendered = render_mermaid(registry)
    assert "VIX -->|E0019 daily, mean CAR -0.0300" in rendered
    assert "DGS10 -->|E0024 daily, cross-event slope -0.5000" in rendered


def test_edges_by_filters_on_test_type():
    nodes = (
        make_node("crypto:btc-usdt-perp", "BTC"),
        make_node("crypto:eth-usdt-perp", "ETH"),
    )
    lead_lag = make_edge(
        "E0001", "crypto:btc-usdt-perp", "crypto:eth-usdt-perp"
    )
    mean_comparison = make_edge(
        "E0017",
        "crypto:btc-usdt-perp",
        "crypto:btc-usdt-perp",
        test_type=EdgeTestType.MEAN_COMPARISON,
        lag_steps=None,
        partial_r_squared=None,
        incremental_r_squared=None,
    )
    edges = (lead_lag, mean_comparison)
    registry = make_registry(nodes, edges, build_candidates(nodes, edges))
    graph = MarketGraph(registry)
    assert graph.edges_by(test_type=EdgeTestType.MEAN_COMPARISON) == (
        mean_comparison,
    )
    assert graph.edges_by(test_type=EdgeTestType.LEAD_LAG) == (lead_lag,)


def test_pending_edge_shape():
    edge = make_edge(
        "E0011",
        "crypto:btc-usdt-perp",
        "crypto:eth-usdt-perp",
        status=EdgeStatus.PENDING,
        trial_id=None,
        trial_record_hash=None,
        coefficient=None,
        standard_error=None,
        t_statistic=None,
        p_value=None,
        holm_adjusted_p_value=None,
        partial_r_squared=None,
        incremental_r_squared=None,
        observations=None,
        sample=None,
        holdout_oos_incremental_r_squared=None,
        holdout_oos_note="No trial has run; no OOS score exists.",
        cost_gate=None,
        cost_gate_note="No cost gate: the forward sample is too small.",
        forward_sample=ForwardSampleRecord(
            minimum_lowvol_rows=60,
            observed_lowvol_rows=0,
            forward_rows=0,
            checked_at=datetime(2026, 11, 18, 1, 35, 34, tzinfo=UTC),
            window_start=datetime(2026, 11, 18, 16, tzinfo=UTC),
            window_end=datetime(2027, 3, 31, 16, tzinfo=UTC),
            ready=False,
        ),
        hypothesis_id="H0003",
        verdict_summary="Hypothesis H0003 REGISTERED; trial pending.",
    )
    assert edge.status is EdgeStatus.PENDING
    assert edge.forward_sample is not None
    assert edge.forward_sample.observed_lowvol_rows == 0


def test_pending_edge_rejects_statistics():
    with pytest.raises(ValidationError, match="no test statistics"):
        make_edge(
            "E0011",
            "crypto:btc-usdt-perp",
            "crypto:eth-usdt-perp",
            status=EdgeStatus.PENDING,
            trial_id=None,
            trial_record_hash=None,
            forward_sample=ForwardSampleRecord(
                minimum_lowvol_rows=60,
                observed_lowvol_rows=0,
                forward_rows=0,
                checked_at=datetime(2026, 11, 18, 1, 35, 34, tzinfo=UTC),
                window_start=datetime(2026, 11, 18, 16, tzinfo=UTC),
                window_end=datetime(2027, 3, 31, 16, tzinfo=UTC),
                ready=False,
            ),
        )


def test_descriptive_edge_has_no_holm_p_value():
    with pytest.raises(ValidationError, match="no Holm-adjusted p-value"):
        make_edge(
            "E0013",
            "index:vix",
            "index:tyvix",
            status=EdgeStatus.DESCRIPTIVE,
        )
    edge = make_edge(
        "E0013",
        "index:vix",
        "index:tyvix",
        status=EdgeStatus.DESCRIPTIVE,
        holm_adjusted_p_value=None,
        hypothesis_id="H0004",
        trial_id="T0004",
    )
    assert edge.status is EdgeStatus.DESCRIPTIVE


# --- Candidate generation ---


def test_candidates_cover_every_untested_pair():
    nodes = (
        make_node("crypto:btc-usdt-perp", "BTC"),
        make_node("crypto:eth-usdt-perp", "ETH"),
        make_node("crypto:sol-usdt-perp", "SOL"),
    )
    edges = (
        make_edge("E0001", "crypto:btc-usdt-perp", "crypto:eth-usdt-perp"),
    )
    candidates = build_candidates(nodes, edges)
    pairs = {(c.source_instrument, c.target_instrument) for c in candidates}
    # 3 nodes -> 6 directed pairs; 1 tested, 5 candidates.
    assert len(candidates) == 5
    assert ("crypto:btc-usdt-perp", "crypto:eth-usdt-perp") not in pairs
    assert ("crypto:eth-usdt-perp", "crypto:btc-usdt-perp") in pairs
    assert all(c.related_descriptive is None for c in candidates)


def test_descriptive_pairs_stay_candidates():
    nodes = (
        make_node("index:vix", "VIX", asset_class="volatility"),
        make_node("index:tyvix", "TYVIX", asset_class="volatility"),
    )
    descriptive = make_edge(
        "E0013",
        "index:vix",
        "index:tyvix",
        status=EdgeStatus.DESCRIPTIVE,
        holm_adjusted_p_value=None,
        hypothesis_id="H0004",
        trial_id="T0004",
    )
    candidates = build_candidates(
        nodes,
        (descriptive,),
        descriptive_notes={
            ("index:vix", "index:tyvix"): "Descriptive reverse placebo (E0013).",
        },
    )
    assert len(candidates) == 2
    by_pair = {
        (c.source_instrument, c.target_instrument): c for c in candidates
    }
    assert (
        by_pair[("index:vix", "index:tyvix")].related_descriptive
        == "Descriptive reverse placebo (E0013)."
    )
    assert by_pair[("index:tyvix", "index:vix")].related_descriptive is None


def test_pending_pairs_are_not_candidates():
    nodes = (
        make_node("crypto:btc-usdt-perp", "BTC"),
        make_node("crypto:eth-usdt-perp", "ETH"),
    )
    pending = make_edge(
        "E0011",
        "crypto:btc-usdt-perp",
        "crypto:eth-usdt-perp",
        status=EdgeStatus.PENDING,
        trial_id=None,
        trial_record_hash=None,
        coefficient=None,
        standard_error=None,
        t_statistic=None,
        p_value=None,
        holm_adjusted_p_value=None,
        partial_r_squared=None,
        incremental_r_squared=None,
        observations=None,
        sample=None,
        holdout_oos_incremental_r_squared=None,
        holdout_oos_note=None,
        cost_gate=None,
        cost_gate_note=None,
        forward_sample=ForwardSampleRecord(
            minimum_lowvol_rows=60,
            observed_lowvol_rows=0,
            forward_rows=0,
            checked_at=datetime(2026, 11, 18, 1, 35, 34, tzinfo=UTC),
            window_start=datetime(2026, 11, 18, 16, tzinfo=UTC),
            window_end=datetime(2027, 3, 31, 16, tzinfo=UTC),
            ready=False,
        ),
        hypothesis_id="H0003",
    )
    candidates = build_candidates(nodes, (pending,))
    assert len(candidates) == 1
    assert candidates[0].source_instrument == "crypto:eth-usdt-perp"


# --- Registry integrity ---


def test_registry_rejects_unknown_edge_endpoint():
    nodes = (make_node("crypto:btc-usdt-perp", "BTC"),)
    edges = (
        make_edge("E0001", "crypto:btc-usdt-perp", "crypto:eth-usdt-perp"),
    )
    with pytest.raises(ValidationError, match="unknown target node"):
        make_registry(nodes, edges)


def test_registry_rejects_candidate_covering_tested_pair():
    registry = make_three_node_graph()
    bad = CandidateRecord(
        source_instrument="crypto:btc-usdt-perp",
        target_instrument="crypto:eth-usdt-perp",
        note="No test registered.",
    )
    with pytest.raises(ValidationError, match="duplicates a tested"):
        make_registry(
            registry.nodes,
            registry.edges,
            (*registry.candidates, bad),
        )


def test_registry_rejects_tampered_content():
    registry = make_three_node_graph()
    raw = json.loads(registry.model_dump_json())
    raw["edges"][0]["coefficient"] = 0.9999
    with pytest.raises(ValidationError, match="content hash mismatch"):
        GraphRegistry.model_validate(raw)


def test_registry_round_trips_through_json():
    registry = make_three_node_graph()
    restored = GraphRegistry.model_validate_json(registry.model_dump_json())
    assert restored == registry


# --- Query interface ---


def test_market_graph_queries():
    registry = make_three_node_graph()
    graph = MarketGraph(registry)
    assert graph.summary() == {
        "nodes": 3,
        "edges": 1,
        "candidates": 5,
        "edges_supported": 0,
        "edges_rejected": 1,
        "edges_pending": 0,
        "edges_descriptive": 0,
    }
    assert len(graph.edges_by(source="crypto:btc-usdt-perp")) == 1
    assert len(graph.edges_by(target="crypto:btc-usdt-perp")) == 0
    assert len(graph.edges_by(status=EdgeStatus.REJECTED)) == 1
    assert len(graph.edges_by(status=EdgeStatus.SUPPORTED)) == 0
    assert len(graph.edges_by(frequency="hourly")) == 0
    assert len(
        graph.edge_between("crypto:btc-usdt-perp", "crypto:eth-usdt-perp")
    ) == 1
    assert len(graph.edge_between("crypto:eth-usdt-perp", "crypto:sol-usdt-perp")) == 0
    assert len(graph.untested_candidates(source="crypto:eth-usdt-perp")) == 2
    assert graph.tested_pairs() == {
        ("crypto:btc-usdt-perp", "crypto:eth-usdt-perp")
    }


# --- Mermaid rendering ---


def test_render_mermaid_marks_statuses():
    nodes = (
        make_node("crypto:btc-usdt-perp", "BTC"),
        make_node("crypto:eth-usdt-perp", "ETH"),
        make_node("index:vix", "VIX", asset_class="volatility"),
        make_node("index:tyvix", "TYVIX", asset_class="volatility"),
    )
    tested = make_edge(
        "E0001", "crypto:btc-usdt-perp", "crypto:eth-usdt-perp"
    )
    pending = make_edge(
        "E0011",
        "crypto:btc-usdt-perp",
        "crypto:eth-usdt-perp",
        status=EdgeStatus.PENDING,
        trial_id=None,
        trial_record_hash=None,
        coefficient=None,
        standard_error=None,
        t_statistic=None,
        p_value=None,
        holm_adjusted_p_value=None,
        partial_r_squared=None,
        incremental_r_squared=None,
        observations=None,
        sample=None,
        holdout_oos_incremental_r_squared=None,
        holdout_oos_note=None,
        cost_gate=None,
        cost_gate_note=None,
        forward_sample=ForwardSampleRecord(
            minimum_lowvol_rows=60,
            observed_lowvol_rows=0,
            forward_rows=0,
            checked_at=datetime(2026, 11, 18, 1, 35, 34, tzinfo=UTC),
            window_start=datetime(2026, 11, 18, 16, tzinfo=UTC),
            window_end=datetime(2027, 3, 31, 16, tzinfo=UTC),
            ready=False,
        ),
        hypothesis_id="H0003",
    )
    descriptive = make_edge(
        "E0013",
        "index:vix",
        "index:tyvix",
        status=EdgeStatus.DESCRIPTIVE,
        holm_adjusted_p_value=None,
        hypothesis_id="H0004",
        trial_id="T0004",
    )
    edges = (tested, pending, descriptive)
    registry = make_registry(nodes, edges, build_candidates(nodes, edges))
    text = render_mermaid(registry)
    assert text.startswith("flowchart LR\n")
    assert "subgraph crypto[Crypto perpetuals]" in text
    assert "subgraph volatility[Volatility indices]" in text
    # Tested edges are solid arrows; pending and descriptive are dashed.
    assert "BTC -->|E0001 daily, coef +0.0252, Holm p 1.000, REJECTED| ETH" in text
    assert "BTC -.->|E0011 daily low-vol, H0003 PENDING, 0/60| ETH" in text
    assert "VIX -.->|E0013 daily, coef +0.0252, DESCRIPTIVE, no verdict| TYVIX" in text
# --- Builder: determinism, traceability, committed-registry drift ---


def run_builder(tmp_path: Path) -> tuple[Path, Path]:
    """Run the builder into tmp_path; returns (registry path, doc path)."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    registry_out = tmp_path / "registry.json"
    doc_out = tmp_path / "market-graph.md"
    doc_out.write_text(
        (REPO_ROOT / "docs" / "market-graph.md").read_text(), encoding="utf-8"
    )
    result = subprocess.run(
        [
            sys.executable,
            str(BUILDER),
            "--repo-root",
            str(REPO_ROOT),
            "--registry-out",
            str(registry_out),
            "--doc-out",
            str(doc_out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return registry_out, doc_out


def test_builder_is_deterministic(tmp_path: Path):
    first_registry, first_doc = run_builder(tmp_path / "a")
    second_registry, second_doc = run_builder(tmp_path / "b")
    assert first_registry.read_bytes() == second_registry.read_bytes()
    assert first_doc.read_bytes() == second_doc.read_bytes()


def test_builder_output_matches_committed_registry(tmp_path: Path):
    if not REGISTRY_PATH.exists():
        pytest.skip("committed registry not generated yet")
    built_registry, _ = run_builder(tmp_path)
    assert built_registry.read_bytes() == REGISTRY_PATH.read_bytes()


def test_every_holm_family_test_has_an_edge(tmp_path: Path):
    built_registry, _ = run_builder(tmp_path)
    graph = MarketGraph.from_file(built_registry)
    for study, ledger in (
        ("btc-eth-001", "research/btc-eth-001/trials.jsonl"),
        ("lowvol-002", "research/lowvol-002/trials.jsonl"),
        ("move-vix-003", "research/move-vix-003/trials.jsonl"),
        ("options-expiry-004", "research/options-expiry-004/trials.jsonl"),
        ("fomc-event-study-005", "research/fomc-event-study-005/trials.jsonl"),
        ("macro-windows-006", "research/macro-windows-006/trials.jsonl"),
        ("publication-lag-007", "research/publication-lag-007/trials.jsonl"),
    ):
        # A ledger may hold more than one trial (study 004 has T0005 and
        # T0007; study 006 has T0011 and T0012); failed trials carry no
        # metrics and are skipped.
        lines = (REPO_ROOT / ledger).read_text().splitlines()
        for line in lines:
            trial = json.loads(line)
            if trial["status"] != "completed":
                continue
            family = {
                entry["test"] for entry in trial["result"]["metrics"]["holm"]
            }
            registered = {
                edge.ledger_test_key
                for edge in graph.edges
                if edge.status in {EdgeStatus.REJECTED, EdgeStatus.SUPPORTED}
                and edge.trial_id == trial["trial_id"]
            }
            assert family == registered, (study, trial["trial_id"])


def test_edge_numbers_match_the_trial_ledger(tmp_path: Path):
    built_registry, _ = run_builder(tmp_path)
    graph = MarketGraph.from_file(built_registry)
    trials: dict[str, dict] = {}
    for ledger in (
        "research/btc-eth-001/trials.jsonl",
        "research/lowvol-002/trials.jsonl",
        "research/move-vix-003/trials.jsonl",
        "research/options-expiry-004/trials.jsonl",
        "research/fomc-event-study-005/trials.jsonl",
        "research/macro-windows-006/trials.jsonl",
        "research/publication-lag-007/trials.jsonl",
    ):
        # Keyed by trial id: a ledger may hold more than one trial.
        for line in (REPO_ROOT / ledger).read_text().splitlines():
            trial = json.loads(line)
            if trial["status"] == "completed":
                trials[trial["trial_id"]] = trial
    for edge in graph.edges:
        if edge.status not in {EdgeStatus.REJECTED, EdgeStatus.SUPPORTED}:
            continue
        trial = trials[edge.trial_id]
        metrics = trial["result"]["metrics"]
        test_key = edge.ledger_test_key
        assert test_key is not None
        test = metrics["tests"][test_key]
        assert edge.trial_record_hash == trial["record_hash"]
        assert edge.coefficient == test["coefficient"]
        assert edge.standard_error == test["standard_error"]
        assert edge.t_statistic == test["t_statistic"]
        assert edge.p_value == test["p_value"]
        assert edge.partial_r_squared == test["partial_r_squared"]
        assert edge.incremental_r_squared == test["incremental_r_squared"]
        assert edge.observations == test["observations"]
        holm = {
            entry["test"]: entry["adjusted_p_value"]
            for entry in metrics["holm"]
        }
        assert edge.holm_adjusted_p_value == holm[test_key]


def test_real_graph_summary(tmp_path: Path):
    built_registry, _ = run_builder(tmp_path)
    graph = MarketGraph.from_file(built_registry)
    assert graph.summary() == {
        "nodes": 12,
        "edges": 39,
        "candidates": 123,
        "edges_supported": 6,
        "edges_rejected": 30,
        "edges_pending": 1,
        "edges_descriptive": 2,
    }
    assert graph.tested_pairs() == {
        ("crypto:btc-usdt-perp", "crypto:eth-usdt-perp"),
        ("crypto:btc-usdt-perp", "crypto:sol-usdt-perp"),
        ("crypto:btc-usdt-perp", "crypto:btc-usdt-perp"),
        ("crypto:eth-usdt-perp", "crypto:eth-usdt-perp"),
        ("index:tyvix", "index:vix"),
        ("index:tyvix", "index:vxn"),
        ("index:vix", "index:vix"),
        ("index:sp500", "index:sp500"),
        ("rates:us-10y-yield", "rates:us-10y-yield"),
        ("credit:baa-10y-spread", "credit:baa-10y-spread"),
        ("index:tyvix", "index:tyvix"),
        ("rates:us-10y-yield", "index:sp500"),
        ("rates:us-10y-yield", "index:vix"),
        ("rates:us-10y-yield", "credit:baa-10y-spread"),
        ("macro:cpi-mom", "index:sp500"),
        ("macro:cpi-mom", "crypto:btc-usdt-perp"),
    }
    # The supported edges: the TYVIX event-window CAR (E0023) and the
    # BAA10Y cross-event slope (E0026), both secondary tests whose
    # hypotheses were rejected on their primary tests; the macro-window
    # mean |log return| comparisons for BTC (E0030) and ETH (E0031),
    # study 006's H0010 family — the lab's first supported hypothesis;
    # and the lagged TYVIX event-window CAR (E0032, study 007's H0011
    # primary — the lab's second supported hypothesis) plus the lagged
    # VIX event-window CAR (E0033, significant under the lag because
    # the day +1 rebound drops out of the lagged window).
    assert {
        edge.edge_id
        for edge in graph.edges_by(status=EdgeStatus.SUPPORTED)
    } == {"E0023", "E0026", "E0030", "E0031", "E0032", "E0033"}
    # The reverse-placebo pair stays an untested candidate, with its
    # descriptive check noted.
    vix_tyvix = graph.untested_candidates(
        source="index:vix", target="index:tyvix"
    )
    assert len(vix_tyvix) == 1
    assert vix_tyvix[0].related_descriptive is not None
    assert "E0013" in vix_tyvix[0].related_descriptive


def test_mean_comparison_edges_are_self_loops_without_lead_lag_stats(
    tmp_path: Path,
):
    built_registry, _ = run_builder(tmp_path)
    graph = MarketGraph.from_file(built_registry)
    mean_edges = graph.edges_by(test_type=EdgeTestType.MEAN_COMPARISON)
    assert {edge.edge_id for edge in mean_edges} == {
        "E0017",
        "E0018",
        "E0030",
        "E0031",
    }
    for edge in mean_edges:
        # A level test compares one instrument against itself; it carries
        # no lag, no partial R-squared, no OOS score and no cost gate.
        assert edge.source_instrument == edge.target_instrument
        assert edge.lag_steps is None
        assert edge.partial_r_squared is None
        assert edge.incremental_r_squared is None
        assert edge.holdout_oos_incremental_r_squared is None
        assert edge.cost_gate is None
        assert "level comparison" in (edge.holdout_oos_note or "")
        assert "level comparison" in (edge.cost_gate_note or "")
    # Mean-comparison self-loops do not create candidates: candidates
    # are directed pairs between distinct instruments only.
    assert all(
        candidate.source_instrument != candidate.target_instrument
        for candidate in graph.untested_candidates()
    )


def test_event_study_and_cross_section_edges_carry_no_lead_lag_stats(
    tmp_path: Path,
):
    built_registry, _ = run_builder(tmp_path)
    graph = MarketGraph.from_file(built_registry)
    event_edges = graph.edges_by(test_type=EdgeTestType.EVENT_STUDY)
    assert {edge.edge_id for edge in event_edges} == {
        "E0019",
        "E0020",
        "E0021",
        "E0022",
        "E0023",
        "E0032",
        "E0033",
        "E0034",
        "E0035",
        "E0036",
    }
    for edge in event_edges:
        # An event-window mean-CAR test compares one instrument against
        # itself; it carries no lag, no partial R-squared, no OOS score
        # and no cost gate. The effect size (standardized mean CAR)
        # lives in the verdict text, not in a lead-lag statistic.
        assert edge.source_instrument == edge.target_instrument
        assert edge.lag_steps is None
        assert edge.partial_r_squared is None
        assert edge.incremental_r_squared is None
        assert edge.holdout_oos_incremental_r_squared is None
        assert edge.cost_gate is None
        assert "event study" in (edge.holdout_oos_note or "")
        assert "event study" in (edge.cost_gate_note or "")
        assert "standardized mean CAR" in edge.verdict_summary
    cross_edges = graph.edges_by(test_type=EdgeTestType.CROSS_SECTION)
    assert {edge.edge_id for edge in cross_edges} == {
        "E0024",
        "E0025",
        "E0026",
    }
    for edge in cross_edges:
        # A cross-event regression is directed (one instrument's CAR on
        # another's) but contemporaneous: both CARs cover the same event
        # window, so there is no lag. The cross-section R-squared lives
        # in the verdict text, not in a lead-lag statistic.
        assert edge.source_instrument != edge.target_instrument
        assert edge.lag_steps is None
        assert edge.partial_r_squared is None
        assert edge.incremental_r_squared is None
        assert edge.holdout_oos_incremental_r_squared is None
        assert edge.cost_gate is None
        assert "event study" in (edge.holdout_oos_note or "")
        assert "event study" in (edge.cost_gate_note or "")
        assert "R²" in edge.verdict_summary
    # The primary cross-section verdict carries the split-half result.
    primary = next(edge for edge in cross_edges if edge.edge_id == "E0024")
    assert "split-half replication failed" in primary.verdict_summary
    # Event-study self-loops do not create candidates either.
    assert all(
        candidate.source_instrument != candidate.target_instrument
        for candidate in graph.untested_candidates()
    )


def test_pending_edge_sample_comes_from_the_sample_check(tmp_path: Path):
    built_registry, _ = run_builder(tmp_path)
    graph = MarketGraph.from_file(built_registry)
    pending = graph.edges_by(status=EdgeStatus.PENDING)
    assert len(pending) == 1
    edge = pending[0]
    assert edge.hypothesis_id == "H0003"
    assert edge.forward_sample is not None
    check = json.loads(
        (REPO_ROOT / "research" / "lowvol-002" / "h0003-sample-check.json")
        .read_text()
    )
    assert (
        edge.forward_sample.observed_lowvol_rows
        == check["lowvol_forward_rows"]
        == 0
    )
    assert (
        edge.forward_sample.minimum_lowvol_rows
        == check["minimum_lowvol_rows"]
        == 60
    )
    assert edge.forward_sample.ready is False
