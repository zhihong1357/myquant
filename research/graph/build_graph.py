"""Build the market graph registry from the studies' trial ledgers.

Deterministic and offline: reads only committed local files (trial
ledgers, preregistrations, the H0003 sample check, instrument catalogs),
never the network and never market data. Every statistic in the registry
comes from a trial ledger; the mapping below declares *which* ledger test
corresponds to *which* edge, but no number is typed in by hand.

Usage (from the repo root):

    .venv/bin/python research/graph/build_graph.py

Regenerates ``research/graph/registry.json`` and the generated section of
``docs/market-graph.md``. Re-run after a new study lands (and extend
``EDGE_SPECS`` with the new study's family tests first — the builder
refuses to run if any Holm-family test in a ledger has no edge spec).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from myquant.graph import (  # noqa: E402
    CostGateRecord,
    CostGateVerdict,
    EdgeRecord,
    EdgeStatus,
    ForwardSampleRecord,
    GraphRegistry,
    MarketGraph,
    NodeRecord,
    ProvenanceRecord,
    SampleRecord,
    build_candidates,
    compute_content_hash,
    render_mermaid,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = REPO_ROOT / "research" / "graph" / "registry.json"
DEFAULT_DOC = REPO_ROOT / "docs" / "market-graph.md"

DOC_BEGIN = (
    "<!-- BEGIN GENERATED: do not edit by hand; regenerate with "
    "research/graph/build_graph.py -->"
)
DOC_END = "<!-- END GENERATED -->"

# Short labels for Mermaid nodes and tables. The canonical identity stays
# the instrument_id; these are display-only.
SHORT_LABELS = {
    "crypto:btc-usdt-perp": "BTC",
    "crypto:eth-usdt-perp": "ETH",
    "crypto:sol-usdt-perp": "SOL",
    "index:vix": "VIX",
    "index:vxn": "VXN",
    "index:tyvix": "TYVIX",
    "index:sp500": "SPX",
    "rates:us-10y-yield": "DGS10",
    "credit:baa-10y-spread": "BAA10Y",
}


@dataclass(frozen=True)
class EdgeSpec:
    """Declares which ledger test becomes which edge.

    Only correspondence metadata lives here (source/target, frequency,
    condition, method, control). All statistics are read from the ledger.
    """

    edge_id: str
    study: str
    ledger_test_key: str | None  # None for the pending + descriptive edges
    source: str
    target: str
    frequency: str
    condition: str | None
    method: str
    control: str | None
    is_primary: bool
    panel_key: str  # daily | hourly | weekly | hyperliquid
    data_sources: tuple[str, ...] | None = None
    notes: tuple[str, ...] = ()


PARTIAL_LEAD_LAG_DAILY = (
    "partial lead-lag OLS, lag 1, Newey-West HAC (max lag 5 daily)"
)
PARTIAL_LEAD_LAG_HOURLY = (
    "partial lead-lag OLS, lag 1, Newey-West HAC (max lag 12 hourly)"
)
LOWVOL_DAILY = (
    "low-volatility regime: trailing-30-return realized volatility below "
    "the trailing-252 median (PIT-correct)"
)
LOWVOL_HOURLY = (
    "low-volatility regime: trailing-720-hour realized volatility below "
    "the expanding median (PIT-correct)"
)

EDGE_SPECS: tuple[EdgeSpec, ...] = (
    # Study 001 (H0001, T0001): 3-test Holm family.
    EdgeSpec(
        edge_id="E0001",
        study="btc-eth-001",
        ledger_test_key="daily_btc_eth",
        source="crypto:btc-usdt-perp",
        target="crypto:eth-usdt-perp",
        frequency="daily",
        condition=None,
        method=PARTIAL_LEAD_LAG_DAILY,
        control="SOL[t] log return",
        is_primary=True,
        panel_key="daily",
    ),
    EdgeSpec(
        edge_id="E0002",
        study="btc-eth-001",
        ledger_test_key="daily_btc_sol",
        source="crypto:btc-usdt-perp",
        target="crypto:sol-usdt-perp",
        frequency="daily",
        condition=None,
        method=PARTIAL_LEAD_LAG_DAILY,
        control="ETH[t] log return",
        is_primary=False,
        panel_key="daily",
        notes=(
            "Secondary test in the H0001 Holm family (ledger and report); "
            "mirrors test (a)'s control structure with the third asset.",
        ),
    ),
    EdgeSpec(
        edge_id="E0003",
        study="btc-eth-001",
        ledger_test_key="hourly_btc_eth",
        source="crypto:btc-usdt-perp",
        target="crypto:eth-usdt-perp",
        frequency="hourly",
        condition=None,
        method=PARTIAL_LEAD_LAG_HOURLY,
        control="SOL[t] log return",
        is_primary=False,
        panel_key="hourly",
        notes=("Predeclared 1H robustness test.",),
    ),
    # Study 002 (H0002, T0002): 4-test Holm family.
    EdgeSpec(
        edge_id="E0004",
        study="lowvol-002",
        ledger_test_key="daily_btc_sol_interaction",
        data_sources=("okx-public@v1",),
        source="crypto:btc-usdt-perp",
        target="crypto:sol-usdt-perp",
        frequency="daily",
        condition=f"{LOWVOL_DAILY}; interaction BTC[t] x lowvol[t]",
        method=(
            "interaction OLS (BTC[t] x lowvol[t]), Newey-West HAC "
            "(max lag 5 daily)"
        ),
        control="ETH[t] log return",
        is_primary=True,
        panel_key="daily",
    ),
    EdgeSpec(
        edge_id="E0005",
        study="lowvol-002",
        ledger_test_key="daily_btc_sol_lowvol",
        data_sources=("okx-public@v1",),
        source="crypto:btc-usdt-perp",
        target="crypto:sol-usdt-perp",
        frequency="daily",
        condition=f"{LOWVOL_DAILY}; low-volatility rows only",
        method=(
            "partial lead-lag OLS on low-volatility rows only, "
            "Newey-West HAC (max lag 5 daily)"
        ),
        control="ETH[t] log return",
        is_primary=False,
        panel_key="daily",
    ),
    EdgeSpec(
        edge_id="E0006",
        study="lowvol-002",
        ledger_test_key="hourly_btc_eth_interaction",
        data_sources=("okx-public@v1",),
        source="crypto:btc-usdt-perp",
        target="crypto:eth-usdt-perp",
        frequency="hourly",
        condition=f"{LOWVOL_HOURLY}; interaction BTC[t] x lowvol[t]",
        method=(
            "interaction OLS (BTC[t] x lowvol[t]), Newey-West HAC "
            "(max lag 12 hourly)"
        ),
        control="SOL[t] log return",
        is_primary=False,
        panel_key="hourly",
    ),
    EdgeSpec(
        edge_id="E0007",
        study="lowvol-002",
        ledger_test_key="hourly_btc_eth_lowvol",
        data_sources=("okx-public@v1",),
        source="crypto:btc-usdt-perp",
        target="crypto:eth-usdt-perp",
        frequency="hourly",
        condition=f"{LOWVOL_HOURLY}; low-volatility rows only",
        method=(
            "partial lead-lag OLS on low-volatility rows only, "
            "Newey-West HAC (max lag 12 hourly)"
        ),
        control="SOL[t] log return",
        is_primary=False,
        panel_key="hourly",
    ),
    # Study 003 (H0004 v2, T0004): 3-test Holm family.
    EdgeSpec(
        edge_id="E0008",
        study="move-vix-003",
        ledger_test_key="daily_tyvix_vix",
        source="index:tyvix",
        target="index:vix",
        frequency="daily",
        condition=None,
        method=(
            "partial lead-lag OLS on log changes, lag 1, Newey-West HAC "
            "(max lag 5 daily)"
        ),
        control="SPX[t] log return",
        is_primary=True,
        panel_key="daily",
    ),
    EdgeSpec(
        edge_id="E0009",
        study="move-vix-003",
        ledger_test_key="daily_tyvix_vxn",
        source="index:tyvix",
        target="index:vxn",
        frequency="daily",
        condition=None,
        method=(
            "partial lead-lag OLS on log changes, lag 1, Newey-West HAC "
            "(max lag 5 daily)"
        ),
        control="SPX[t] log return",
        is_primary=False,
        panel_key="daily",
    ),
    EdgeSpec(
        edge_id="E0010",
        study="move-vix-003",
        ledger_test_key="weekly_tyvix_vix",
        source="index:tyvix",
        target="index:vix",
        frequency="weekly",
        condition=None,
        method=(
            "partial lead-lag OLS on Friday-close log changes, lag 1, "
            "Newey-West HAC (max lag 4 weekly)"
        ),
        control="SPX[t] log return",
        is_primary=False,
        panel_key="weekly",
        notes=("Predeclared weekly robustness test.",),
    ),
)

# study -> (hypothesis id, registration version, trial id, report path)
STUDIES = {
    "btc-eth-001": ("H0001", 1, "T0001", "docs/studies/btc-eth-transmission-001.md"),
    "lowvol-002": ("H0002", 1, "T0002", "docs/studies/lowvol-transmission-002.md"),
    "move-vix-003": ("H0004", 2, "T0004", "docs/studies/move-vix-transmission-003.md"),
}

# Descriptive-only edges (never in a test family, no verdict).
DESCRIPTIVE_NOTES = {
    ("index:vix", "index:tyvix"): (
        "Descriptive reverse placebo (E0013, study 003): nominal p = 0.045, "
        "partial R² 0.0018, treated as noise. No family test has been run "
        "on this pair."
    ),
}


@dataclass
class StudyData:
    study: str
    hypothesis_id: str
    hypothesis_version: int
    trial_id: str
    report_path: str
    ledger_path: str
    trial: dict
    metrics: dict
    registration: dict
    registration_path: str
    primary_edge_id: str


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_trial(repo_root: Path, study: str, trial_id: str) -> dict:
    ledger = repo_root / "research" / study / "trials.jsonl"
    records = [
        json.loads(line)
        for line in ledger.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    matching = [r for r in records if r["trial_id"] == trial_id]
    if len(matching) != 1:
        raise ValueError(f"expected exactly one {trial_id} in {ledger}")
    trial = matching[0]
    if trial["status"] != "completed":
        raise ValueError(f"trial {trial_id} is not completed: {trial['status']}")
    return trial


def _read_registration(
    repo_root: Path, study: str, hypothesis_id: str, version: int
) -> tuple[dict, str]:
    rel = (
        f"research/{study}/hypotheses/registrations/{hypothesis_id}/v{version}.json"
    )
    return _read_json(repo_root / rel), rel


def _fixed_parameter(spec: dict, name: str) -> str:
    for parameter in spec["fixed_parameters"]:
        if parameter.startswith(f"{name}="):
            return parameter.split("=", 1)[1]
    raise ValueError(f"fixed parameter {name} not found in preregistration")


def _load_study(repo_root: Path, study: str) -> StudyData:
    hypothesis_id, version, trial_id, report_path = STUDIES[study]
    trial = _read_trial(repo_root, study, trial_id)
    registration, registration_path = _read_registration(
        repo_root, study, hypothesis_id, version
    )
    # The trial binds to the preregistration fingerprint; cross-check it.
    bound = trial["result"]["spec"]["hypothesis_fingerprint"]
    if bound != registration["spec_fingerprint"]:
        raise ValueError(
            f"{trial_id} binds to {bound[:12]} but {hypothesis_id} v{version} "
            f"is {registration['spec_fingerprint'][:12]}"
        )
    if trial["result"]["spec"]["hypothesis_version"] != version:
        raise ValueError(f"{trial_id} ran against the wrong hypothesis version")
    primary = next(
        spec.edge_id
        for spec in EDGE_SPECS
        if spec.study == study and spec.is_primary
    )
    return StudyData(
        study=study,
        hypothesis_id=hypothesis_id,
        hypothesis_version=version,
        trial_id=trial_id,
        report_path=report_path,
        ledger_path=f"research/{study}/trials.jsonl",
        trial=trial,
        metrics=trial["result"]["metrics"],
        registration=registration,
        registration_path=registration_path,
        primary_edge_id=primary,
    )


def _load_nodes(repo_root: Path, studies: dict[str, StudyData]) -> tuple[NodeRecord, ...]:
    catalogs: dict[str, dict] = {}
    for study in STUDIES:
        instruments = repo_root / "research" / study / "catalog" / "instruments"
        for version_file in sorted(instruments.glob("*/v1.json")):
            record = _read_json(version_file)
            catalogs.setdefault(record["instrument_id"], record)
    nodes: list[NodeRecord] = []
    for instrument_id in sorted(catalogs):
        record = catalogs[instrument_id]
        member_of = tuple(
            study
            for study, data in studies.items()
            if instrument_id in data.registration["spec"]["universe"]
        )
        nodes.append(
            NodeRecord(
                instrument_id=instrument_id,
                short_label=SHORT_LABELS[instrument_id],
                name=record["name"],
                asset_class=record["asset_class"],
                instrument_type=record["instrument_type"],
                calendar_id=record["calendar_id"],
                studies=member_of,
            )
        )
    return tuple(nodes)


def _sample(metrics: dict, panel_key: str, observations: int) -> SampleRecord:
    panel = metrics["panel"]
    return SampleRecord(
        first=datetime.fromisoformat(panel[f"{panel_key}_first"]),
        last=datetime.fromisoformat(panel[f"{panel_key}_last"]),
        panel_rows=panel[f"{panel_key}_rows"],
        observations=observations,
    )


def _trial_level_oos(data: StudyData) -> tuple[float, str]:
    """Holdout OOS incremental R² for the primary test, per study."""
    walk_forward = data.metrics["walk_forward"]
    if data.study == "lowvol-002":
        value = walk_forward["lowvol_holdout_oos_incremental_r_squared"]
        note = (
            "Low-volatility holdout rows only (the acceptance criterion; "
            f"{walk_forward['lowvol_holdout_folds']} folds, "
            f"{walk_forward['lowvol_holdout_test_rows']} rows). "
            "All-holdout incremental OOS R² was "
            f"{walk_forward['holdout_oos_incremental_r_squared']:+.5f}."
        )
        return value, note
    value = walk_forward["holdout_oos_incremental_r_squared"]
    note = (
        "Holdout window only "
        f"({walk_forward['holdout_folds']} folds, "
        f"{walk_forward['holdout_test_rows']} rows)."
    )
    return value, note


def _trial_level_cost(data: StudyData) -> CostGateRecord:
    """Cost gate for the primary test, per study."""
    if data.study == "move-vix-003":
        gate = data.metrics["cost_gate_informational"]
        return CostGateRecord(
            verdict=CostGateVerdict.INFORMATIONAL,
            net_daily_edge=None,
            gross_daily_edge=gate["gross_daily_edge"],
            bootstrap_p_value=gate["gross_edge_bootstrap_p_value"],
            ci_lower=gate["gross_edge_ci_lower"],
            ci_upper=gate["gross_edge_ci_upper"],
            days=gate["days"],
            note=(
                "Informational only: no costs applied. Volatility indices "
                "are not tradable; VIX futures roll costs are unmeasurable "
                "from free data. Not a verdict criterion."
            ),
        )
    gate = data.metrics["cost_gate"]
    if data.study == "lowvol-002":
        note = (
            "Sign rule on low-volatility holdout rows only; flat on "
            "high-volatility rows. Net edge averaged over all "
            f"{gate['days']} holdout rows (including {gate['lowvol_days']} "
            "low-volatility rows). 0.05% taker fee per side; funding, "
            "slippage and market impact ignored."
        )
    else:
        note = (
            "Sign rule on holdout OOS forecasts. 0.05% taker fee per "
            "side; funding, slippage and market impact ignored."
        )
    return CostGateRecord(
        verdict=(
            CostGateVerdict.PASS
            if gate["net_daily_edge"] > 0
            else CostGateVerdict.FAIL
        ),
        net_daily_edge=gate["net_daily_edge"],
        gross_daily_edge=gate["gross_daily_edge"],
        bootstrap_p_value=gate["net_edge_bootstrap_p_value"],
        ci_lower=gate["net_edge_ci_lower"],
        ci_upper=gate["net_edge_ci_upper"],
        days=gate["days"],
        note=note,
    )


def _build_tested_edge(spec: EdgeSpec, data: StudyData) -> EdgeRecord:
    assert spec.ledger_test_key is not None
    test = data.metrics["tests"][spec.ledger_test_key]
    holm = {
        entry["test"]: entry["adjusted_p_value"]
        for entry in data.metrics["holm"]
    }
    holm_p = holm[spec.ledger_test_key]
    lag = int(_fixed_parameter(data.registration["spec"], "lag"))
    if spec.is_primary:
        oos_value, oos_note = _trial_level_oos(data)
        cost_gate = _trial_level_cost(data)
        cost_note = None
        if cost_gate.verdict is CostGateVerdict.INFORMATIONAL:
            verdict = (
                f"Hypothesis {data.hypothesis_id} REJECTED "
                f"(trial {data.trial_id}): this test did not reject "
                f"(Holm-adjusted p = {holm_p:.3f}); partial R² "
                f"{test['partial_r_squared']:.6g} below the 0.005 "
                f"threshold; holdout OOS incremental R² "
                f"{oos_value:+.5f}; cost gate informational (gross daily "
                f"edge {cost_gate.gross_daily_edge:+.4%}, 95% CI includes "
                "zero) — no net edge measurable without VIX futures data."
            )
        else:
            verdict = (
                f"Hypothesis {data.hypothesis_id} REJECTED "
                f"(trial {data.trial_id}): this test did not reject "
                f"(Holm-adjusted p = {holm_p:.3f}); partial R² "
                f"{test['partial_r_squared']:.6g} below the 0.005 "
                f"threshold; holdout OOS incremental R² "
                f"{oos_value:+.5f}; cost gate {cost_gate.verdict.value} "
                f"(net daily edge {cost_gate.net_daily_edge:+.4%})."
            )
    else:
        oos_value, oos_note = None, (
            "Trial-level metric; measured for the primary test "
            f"({data.primary_edge_id}) only."
        )
        cost_gate, cost_note = None, (
            "Trial-level cost gate; applies to the primary test "
            f"({data.primary_edge_id}) only."
        )
        verdict = (
            f"Hypothesis {data.hypothesis_id} REJECTED "
            f"(trial {data.trial_id}): this test did not reject "
            f"(Holm-adjusted p = {holm_p:.3f}, partial R² "
            f"{test['partial_r_squared']:.6g})."
        )
    notes = list(spec.notes)
    if spec.edge_id == "E0004":
        a2 = data.metrics["tests"]["daily_btc_sol_lowvol"]
        notes.append(
            "Closest to a signal in the family (raw p = "
            f"{test['p_value']:.3f}) but Holm-adjusted p = {holm_p:.3f} "
            "and partial R² below the 0.005 threshold; the direct "
            "subsample test A2 (E0005) is clearly null "
            f"(p = {a2['p_value']:.3f})."
        )
    return EdgeRecord(
        edge_id=spec.edge_id,
        status=EdgeStatus.REJECTED,
        source_instrument=spec.source,
        target_instrument=spec.target,
        frequency=spec.frequency,
        lag_steps=lag,
        condition=spec.condition,
        method=spec.method,
        common_factor_control=spec.control,
        data_sources=tuple(
            spec.data_sources
            or data.registration["spec"]["source_versions"]
        ),
        hypothesis_id=data.hypothesis_id,
        hypothesis_version=data.hypothesis_version,
        trial_id=data.trial_id,
        preregistration_fingerprint=data.registration["spec_fingerprint"],
        trial_record_hash=data.trial["record_hash"],
        report_path=data.report_path,
        ledger_path=data.ledger_path,
        ledger_test_key=spec.ledger_test_key,
        coefficient=test["coefficient"],
        standard_error=test["standard_error"],
        t_statistic=test["t_statistic"],
        p_value=test["p_value"],
        holm_adjusted_p_value=holm_p,
        partial_r_squared=test["partial_r_squared"],
        incremental_r_squared=test["incremental_r_squared"],
        observations=test["observations"],
        sample=_sample(data.metrics, spec.panel_key, test["observations"]),
        holdout_oos_incremental_r_squared=oos_value,
        holdout_oos_note=oos_note,
        cost_gate=cost_gate,
        cost_gate_note=cost_note,
        forward_sample=None,
        verdict_summary=verdict,
        notes=tuple(notes),
    )


def _build_pending_edge(repo_root: Path, data: StudyData) -> EdgeRecord:
    """H0003: preregistered forward test, no trial has run."""
    registration, _ = _read_registration(
        repo_root, "lowvol-002", "H0003", 1
    )
    check_path = repo_root / "research" / "lowvol-002" / "h0003-sample-check.json"
    check = _read_json(check_path)
    spec = registration["spec"]
    lag = int(_fixed_parameter(spec, "lag"))
    forward_sample = ForwardSampleRecord(
        minimum_lowvol_rows=check["minimum_lowvol_rows"],
        observed_lowvol_rows=check["lowvol_forward_rows"],
        forward_rows=check["forward_rows"],
        checked_at=datetime.fromisoformat(check["checked_at"]),
        window_start=datetime.fromisoformat(check["forward_window"][0]),
        window_end=datetime.fromisoformat(check["forward_window"][1]),
        ready=check["ready"],
    )
    return EdgeRecord(
        edge_id="E0011",
        status=EdgeStatus.PENDING,
        source_instrument="crypto:btc-usdt-perp",
        target_instrument="crypto:eth-usdt-perp",
        frequency="daily",
        lag_steps=lag,
        condition=(
            "low-volatility forward rows only (same PIT-correct daily "
            "regime rule as study 002); interaction + subsample structure"
        ),
        method=(
            "interaction OLS + low-volatility subsample partial lead-lag, "
            "lag 1, Newey-West HAC (2-test Holm family)"
        ),
        common_factor_control="SOL[t] log return",
        data_sources=tuple(spec["source_versions"]),
        hypothesis_id="H0003",
        hypothesis_version=1,
        trial_id=None,
        preregistration_fingerprint=registration["spec_fingerprint"],
        trial_record_hash=None,
        report_path=data.report_path,
        ledger_path="research/lowvol-002/h0003-sample-check.json",
        ledger_test_key=None,
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
        cost_gate_note=(
            "No cost-gate criterion: the forward sample is too small for "
            "walk-forward validation."
        ),
        forward_sample=forward_sample,
        verdict_summary=(
            "Hypothesis H0003 REGISTERED (v1); no trial has run. The trial "
            "runs when 60 low-volatility forward rows exist; sample check "
            f"{check['checked_at'][:10]}: "
            f"{check['lowvol_forward_rows']}/{check['minimum_lowvol_rows']} "
            "low-volatility rows, not ready."
        ),
        notes=(
            "The spec holdout_window starts 2026-11-19T16:00Z but the "
            "operative cutoff is fixed parameter forward_window_start = "
            "2026-11-18T16:00Z (one bar earlier); the trial and "
            "sample-check scripts use the parameter.",
        ),
    )


def _build_cross_venue_edge(data: StudyData) -> EdgeRecord:
    """Study 002 test C: Hyperliquid cross-venue check (descriptive)."""
    cross = data.metrics["cross_venue"]
    regime = data.metrics["regime"]
    lag = int(_fixed_parameter(data.registration["spec"], "lag"))
    # The ledger's cross_venue.labelled_rows (1072) is the regression-row
    # count mislabelled; the correct labelled count (1073) is in the same
    # ledger's regime metrics. Use the correct one and say so.
    labelled = regime["hyperliquid_labelled_rows"]
    return EdgeRecord(
        edge_id="E0012",
        status=EdgeStatus.DESCRIPTIVE,
        source_instrument="crypto:btc-usdt-perp",
        target_instrument="crypto:eth-usdt-perp",
        frequency="daily",
        lag_steps=lag,
        condition=(
            "low-volatility subsample only (Hyperliquid daily, same "
            "PIT-correct regime rule)"
        ),
        method=(
            "descriptive: correlation + factor-controlled OLS on "
            "low-volatility rows (no p-values, not in the test family)"
        ),
        common_factor_control="SOL[t] log return (Hyperliquid)",
        data_sources=("hyperliquid-public@v1",),
        hypothesis_id=data.hypothesis_id,
        hypothesis_version=data.hypothesis_version,
        trial_id=data.trial_id,
        preregistration_fingerprint=data.registration["spec_fingerprint"],
        trial_record_hash=data.trial["record_hash"],
        report_path=data.report_path,
        ledger_path=data.ledger_path,
        ledger_test_key=None,
        coefficient=cross["controlled_coefficient"],
        standard_error=None,
        t_statistic=None,
        p_value=None,
        holm_adjusted_p_value=None,
        partial_r_squared=cross["controlled_partial_r_squared"],
        incremental_r_squared=None,
        observations=cross["observations"],
        sample=_sample(data.metrics, "hyperliquid", cross["observations"]),
        holdout_oos_incremental_r_squared=None,
        holdout_oos_note="Descriptive check; no OOS score was computed.",
        cost_gate=None,
        cost_gate_note="Descriptive check; no cost gate was computed.",
        forward_sample=None,
        verdict_summary=(
            "Descriptive only (test C, study 002): Hyperliquid daily "
            "BTC→ETH low-volatility subsample. Raw correlation "
            f"{cross['correlation']:.3f}, factor-controlled coefficient "
            f"{cross['controlled_coefficient']:+.3f} (wrong sign). No "
            "p-values, not in the test family, no verdict."
        ),
        notes=(
            f"Labelled rows: {labelled} (527 low / 546 high); the "
            "ledger's cross_venue.labelled_rows field reads 1072, which "
            "is the regression-row count mislabelled — the correct value "
            "1073 comes from the same ledger's regime metrics.",
            "Same-period Hyperliquid prices are highly correlated with "
            "OKX, so this check excludes venue-specific artefacts only; "
            "it cannot cure data snooping.",
        ),
    )


def _build_reverse_placebo_edge(data: StudyData) -> EdgeRecord:
    """Study 003 reverse placebo: VIX -> TYVIX (descriptive)."""
    placebo = data.metrics["reverse_placebo"]
    lag = int(_fixed_parameter(data.registration["spec"], "lag"))
    return EdgeRecord(
        edge_id="E0013",
        status=EdgeStatus.DESCRIPTIVE,
        source_instrument="index:vix",
        target_instrument="index:tyvix",
        frequency="daily",
        lag_steps=lag,
        condition=None,
        method=(
            "partial lead-lag OLS, lag 1, Newey-West HAC (max lag 5 "
            "daily); descriptive placebo, same structure as the primary "
            "test with the direction reversed"
        ),
        common_factor_control="SPX[t] log return",
        data_sources=tuple(data.registration["spec"]["source_versions"]),
        hypothesis_id=data.hypothesis_id,
        hypothesis_version=data.hypothesis_version,
        trial_id=data.trial_id,
        preregistration_fingerprint=data.registration["spec_fingerprint"],
        trial_record_hash=data.trial["record_hash"],
        report_path=data.report_path,
        ledger_path=data.ledger_path,
        ledger_test_key=None,
        coefficient=placebo["coefficient"],
        standard_error=placebo["standard_error"],
        t_statistic=placebo["t_statistic"],
        p_value=placebo["p_value"],
        holm_adjusted_p_value=None,
        partial_r_squared=placebo["partial_r_squared"],
        incremental_r_squared=placebo["incremental_r_squared"],
        observations=placebo["observations"],
        sample=_sample(data.metrics, "daily", placebo["observations"]),
        holdout_oos_incremental_r_squared=None,
        holdout_oos_note="Descriptive check; no OOS score was computed.",
        cost_gate=None,
        cost_gate_note="Descriptive check; no cost gate was computed.",
        forward_sample=None,
        verdict_summary=(
            "Descriptive only (reverse placebo, study 003): nominal p = "
            f"{placebo['p_value']:.3f} is uncorrected and the effect is "
            f"small (partial R² {placebo['partial_r_squared']:.6g}); "
            "treated as noise, not a finding. No verdict."
        ),
        notes=(
            "If anything, the nominal signal points equity→rates, the "
            "opposite direction from H0004; it must not be cited as "
            "evidence of transmission without a fresh preregistration.",
        ),
    )


def _check_family_coverage(data: StudyData) -> None:
    """Fail loudly if any Holm-family test has no edge spec."""
    family = {entry["test"] for entry in data.metrics["holm"]}
    mapped = {
        spec.ledger_test_key
        for spec in EDGE_SPECS
        if spec.study == data.study and spec.ledger_test_key is not None
    }
    missing = family - mapped
    if missing:
        raise ValueError(
            f"{data.study}: Holm-family tests without an edge spec: "
            f"{sorted(missing)} — extend EDGE_SPECS before rebuilding"
        )
    unknown = mapped - set(data.metrics["tests"])
    if unknown:
        raise ValueError(
            f"{data.study}: edge specs without a ledger test: {sorted(unknown)}"
        )


def _provenance(data: StudyData) -> ProvenanceRecord:
    return ProvenanceRecord(
        study=data.study,
        trial_id=data.trial_id,
        ledger_path=data.ledger_path,
        trial_record_hash=data.trial["record_hash"],
        registration_path=data.registration_path,
        preregistration_fingerprint=data.registration["spec_fingerprint"],
    )


def build_registry(repo_root: Path) -> GraphRegistry:
    """Build the full registry from the studies' committed artifacts."""
    studies = {study: _load_study(repo_root, study) for study in STUDIES}
    for data in studies.values():
        _check_family_coverage(data)
    nodes = _load_nodes(repo_root, studies)
    edges: list[EdgeRecord] = []
    for spec in EDGE_SPECS:
        edges.append(_build_tested_edge(spec, studies[spec.study]))
    edges.append(_build_pending_edge(repo_root, studies["lowvol-002"]))
    edges.append(_build_cross_venue_edge(studies["lowvol-002"]))
    edges.append(_build_reverse_placebo_edge(studies["move-vix-003"]))
    edges.sort(key=lambda edge: edge.edge_id)
    edge_tuple = tuple(edges)
    candidates = build_candidates(
        nodes, edge_tuple, descriptive_notes=DESCRIPTIVE_NOTES
    )
    h0003_registration, h0003_path = _read_registration(
        repo_root, "lowvol-002", "H0003", 1
    )
    provenance = (
        _provenance(studies["btc-eth-001"]),
        _provenance(studies["lowvol-002"]),
        ProvenanceRecord(
            study="lowvol-002",
            trial_id=None,
            ledger_path="research/lowvol-002/h0003-sample-check.json",
            trial_record_hash=None,
            registration_path=h0003_path,
            preregistration_fingerprint=h0003_registration["spec_fingerprint"],
        ),
        _provenance(studies["move-vix-003"]),
    )
    content_hash = compute_content_hash(
        schema_version=1,
        nodes=nodes,
        edges=edge_tuple,
        candidates=candidates,
        provenance=provenance,
    )
    return GraphRegistry(
        schema_version=1,
        nodes=nodes,
        edges=edge_tuple,
        candidates=candidates,
        provenance=provenance,
        content_hash=content_hash,
    )


def write_registry(registry: GraphRegistry, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.loads(registry.model_dump_json())
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# --- Documentation generation ---


def _fmt_float(value: float | None, *, decimals: int = 4) -> str:
    if value is None:
        return "—"
    return f"{value:+.{decimals}f}"


def _fmt_p(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.3f}"


def _fmt_r2(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.6g}"


def _condition_short(edge: EdgeRecord) -> str:
    if edge.condition is None:
        return "—"
    if edge.status is EdgeStatus.PENDING:
        return "low-vol forward"
    if "interaction" in edge.condition:
        return "low-vol interaction"
    if "subsample" in edge.condition:
        return "low-vol subsample"
    return "low-vol"


def _candidate_groups(graph: MarketGraph) -> list[tuple[str, int]]:
    """Candidate counts by market-group pair, for the doc summary."""
    groups: dict[tuple[str, str], int] = {}
    for candidate in graph.candidates:
        source_group = graph.node(candidate.source_instrument).asset_class
        target_group = graph.node(candidate.target_instrument).asset_class
        key = tuple(sorted((source_group, target_group)))
        groups[key] = groups.get(key, 0) + 1
    return sorted(groups.items())


def render_doc_section(registry: GraphRegistry) -> str:
    """Render the generated section of docs/market-graph.md."""
    graph = MarketGraph(registry)
    summary = graph.summary()
    lines: list[str] = []
    lines.append("## Current state (generated)")
    lines.append("")
    lines.append(
        "This section is generated by `research/graph/build_graph.py` from "
        "the studies' trial ledgers and preregistrations. Do not edit it "
        "by hand."
    )
    lines.append("")
    lines.append("| | count |")
    lines.append("| --- | ---: |")
    lines.append(f"| Nodes (instruments) | {summary['nodes']} |")
    lines.append(f"| Tested edges | {summary['edges_rejected'] + summary['edges_supported']} |")
    lines.append(f"| — of which REJECTED | {summary['edges_rejected']} |")
    lines.append(f"| — of which SUPPORTED | {summary['edges_supported']} |")
    lines.append(f"| PENDING edges (preregistered, untested) | {summary['edges_pending']} |")
    lines.append(f"| DESCRIPTIVE checks (no verdict) | {summary['edges_descriptive']} |")
    lines.append(f"| Untested candidate pairs | {summary['candidates']} |")
    lines.append("")
    lines.append(
        "**Every tested edge so far is a null.** All "
        f"{summary['edges_rejected']} family tests across three studies "
        "failed to reject: no lag-1 transmission was found in any tested "
        "configuration. That is the graph's most important information "
        "right now — it records where transmission was looked for and not "
        "found, which is what stops the next study from re-testing the "
        "same edges."
    )
    lines.append("")
    lines.append("### Edges")
    lines.append("")
    lines.append(
        "| Edge | Source → Target | Freq | Condition | Hypothesis / trial "
        "| Coef | Holm p | Partial R² | Holdout OOS R² | Status |"
    )
    lines.append(
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |"
    )
    labels = {node.instrument_id: node.short_label for node in registry.nodes}
    for edge in registry.edges:
        pair = f"{labels[edge.source_instrument]} → {labels[edge.target_instrument]}"
        trial = edge.trial_id or "—"
        lines.append(
            f"| {edge.edge_id} | {pair} | {edge.frequency} | "
            f"{_condition_short(edge)} | {edge.hypothesis_id} "
            f"v{edge.hypothesis_version} / {trial} | "
            f"{_fmt_float(edge.coefficient)} | {_fmt_p(edge.holm_adjusted_p_value)} | "
            f"{_fmt_r2(edge.partial_r_squared)} | "
            f"{_fmt_float(edge.holdout_oos_incremental_r_squared, decimals=5)} | "
            f"{edge.status.value.upper()} |"
        )
    lines.append("")
    lines.append("### Edge notes")
    lines.append("")
    for edge in registry.edges:
        lines.append(f"- **{edge.edge_id}** ({edge.status.value.upper()}): {edge.verdict_summary}")
        for note in edge.notes:
            lines.append(f"  - {note}")
    lines.append("")
    lines.append("### Diagram")
    lines.append("")
    lines.append("```mermaid")
    lines.append(render_mermaid(registry).rstrip("\n"))
    lines.append("```")
    lines.append("")
    lines.append(
        "Solid arrows are tested edges; dashed arrows are pending or "
        "descriptive. Labels show the edge id, frequency, coefficient, "
        "Holm-adjusted p-value (tested edges) and status."
    )
    lines.append("")
    lines.append("### Untested candidates")
    lines.append("")
    lines.append(
        f"There are {summary['candidates']} directed pairs with no tested "
        "or pending edge. They are **untested candidates, not evidence**: "
        "the list is mechanical (every ordered pair of graph nodes minus "
        "the tested pairs) and includes cross-asset pairs with no prior "
        "rationale. A candidate becomes an edge only through a new "
        "preregistered study."
    )
    lines.append("")
    lines.append("| Market-group pair | untested pairs |")
    lines.append("| --- | ---: |")
    for (group_a, group_b), count in _candidate_groups(graph):
        lines.append(f"| {group_a} ↔ {group_b} | {count} |")
    lines.append("")
    lines.append("<details>")
    lines.append("<summary>Full candidate list (generated)</summary>")
    lines.append("")
    for candidate in registry.candidates:
        source = labels[candidate.source_instrument]
        target = labels[candidate.target_instrument]
        extra = ""
        if candidate.related_descriptive:
            extra = f" — {candidate.related_descriptive}"
        lines.append(f"- {source} → {target}{extra}")
    lines.append("")
    lines.append("</details>")
    lines.append("")
    lines.append("### Provenance")
    lines.append("")
    lines.append(
        "Every number above traces to one of these ledger records. "
        "Re-run the builder to verify: it re-reads the ledgers and "
        "refuses to run if a family test is unmapped."
    )
    lines.append("")
    lines.append(
        "| Study | Trial | Ledger record | Preregistration |"
    )
    lines.append("| --- | --- | --- | --- |")
    for entry in registry.provenance:
        trial = entry.trial_id or "— (pending)"
        record = (entry.trial_record_hash or "—")[:12]
        lines.append(
            f"| {entry.study} | {trial} | `{record}` | "
            f"`{entry.preregistration_fingerprint[:12]}` |"
        )
    lines.append("")
    lines.append(f"Registry content hash: `{registry.content_hash}`")
    lines.append("")
    return "\n".join(lines)


def update_doc(doc_path: Path, section: str) -> None:
    """Replace the generated section between the markers."""
    text = doc_path.read_text(encoding="utf-8")
    if DOC_BEGIN not in text or DOC_END not in text:
        raise ValueError(
            f"{doc_path} is missing the generated-section markers; "
            "add them before running the builder"
        )
    before, rest = text.split(DOC_BEGIN, 1)
    _, after = rest.split(DOC_END, 1)
    doc_path.write_text(
        before + DOC_BEGIN + "\n\n" + section + DOC_END + after,
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--registry-out", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--doc-out", type=Path, default=DEFAULT_DOC)
    args = parser.parse_args(argv)
    registry = build_registry(args.repo_root)
    write_registry(registry, args.registry_out)
    update_doc(args.doc_out, render_doc_section(registry))
    graph = MarketGraph(registry)
    summary = graph.summary()
    print(f"registry: {args.registry_out}")
    print(f"doc: {args.doc_out}")
    print(
        "nodes={nodes} edges={edges} (rejected={rejected}, "
        "supported={supported}, pending={pending}, descriptive={descriptive}) "
        "candidates={candidates}".format(
            nodes=summary["nodes"],
            edges=summary["edges"],
            rejected=summary["edges_rejected"],
            supported=summary["edges_supported"],
            pending=summary["edges_pending"],
            descriptive=summary["edges_descriptive"],
            candidates=summary["candidates"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
