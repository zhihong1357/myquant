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
    EdgeTestType,
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
    # Underscores, not spaces or hyphens: short labels double as Mermaid
    # node ids, which must be alphanumeric plus underscores.
    "index:btc-dvol": "BTC_DVOL",
    "index:eth-dvol": "ETH_DVOL",
    "macro:cpi-mom": "CPI_MoM",
}


@dataclass(frozen=True)
class EdgeSpec:
    """Declares which ledger test becomes which edge.

    Only correspondence metadata lives here (source/target, frequency,
    condition, method, control). All statistics are read from the ledger.
    """

    edge_id: str
    study: str
    trial_id: str
    ledger_test_key: str | None  # None for the pending + descriptive edges
    source: str
    target: str
    frequency: str
    condition: str | None
    method: str
    control: str | None
    is_primary: bool
    panel_key: str  # daily | hourly | weekly | hyperliquid
    test_type: EdgeTestType = EdgeTestType.LEAD_LAG
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
        trial_id="T0001",
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
        trial_id="T0001",
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
        trial_id="T0001",
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
        trial_id="T0002",
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
        trial_id="T0002",
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
        trial_id="T0002",
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
        trial_id="T0002",
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
        trial_id="T0004",
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
        trial_id="T0004",
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
        trial_id="T0004",
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
    # Study 004 (H0005, T0005): 3-test Holm family. Expiry window = OKX
    # bar-open dates T-3..T for monthly expiry T (last Friday of the
    # month, settlement 08:00 UTC); the window indicator is known at the
    # bar's open because the calendar is public in advance.
    EdgeSpec(
        edge_id="E0014",
        study="options-expiry-004",
        trial_id="T0005",
        ledger_test_key="daily_btc_eth_interaction",
        source="crypto:btc-usdt-perp",
        target="crypto:eth-usdt-perp",
        frequency="daily",
        condition=(
            "expiry-window interaction: BTC[t] x window[t], window = "
            "bar-open dates T-3..T (PIT-correct)"
        ),
        method=(
            "interaction OLS (BTC[t] x window[t]), Newey-West HAC "
            "(max lag 5 daily)"
        ),
        control="SOL[t] log return",
        is_primary=True,
        panel_key="daily",
    ),
    EdgeSpec(
        edge_id="E0015",
        study="options-expiry-004",
        trial_id="T0005",
        ledger_test_key="daily_btc_eth_window",
        source="crypto:btc-usdt-perp",
        target="crypto:eth-usdt-perp",
        frequency="daily",
        condition=(
            "expiry-window subsample only (bar-open dates T-3..T)"
        ),
        method=(
            "partial lead-lag OLS on expiry-window rows only, "
            "Newey-West HAC (max lag 5 daily)"
        ),
        control="SOL[t] log return",
        is_primary=False,
        panel_key="daily",
    ),
    EdgeSpec(
        edge_id="E0016",
        study="options-expiry-004",
        trial_id="T0005",
        ledger_test_key="hourly_btc_eth_interaction",
        source="crypto:btc-usdt-perp",
        target="crypto:eth-usdt-perp",
        frequency="hourly",
        condition=(
            "expiry-window interaction: BTC[t] x window[t], window = "
            "bar-open dates T-3..T (PIT-correct)"
        ),
        method=(
            "interaction OLS (BTC[t] x window[t]), Newey-West HAC "
            "(max lag 12 hourly)"
        ),
        control="SOL[t] log return",
        is_primary=False,
        panel_key="hourly",
        notes=("Predeclared 1H robustness test.",),
    ),
    # Study 004 (H0006, T0007): 2-test Holm family. Mean-comparison
    # edges: within-instrument level tests (window vs non-window mean
    # daily |log return|), NOT transmission edges. Self-loops by
    # construction; no lag, no partial R-squared, no OOS or cost gate.
    EdgeSpec(
        edge_id="E0017",
        study="options-expiry-004",
        trial_id="T0007",
        ledger_test_key="btc_mean_abs_return_comparison",
        source="crypto:btc-usdt-perp",
        target="crypto:btc-usdt-perp",
        frequency="daily",
        condition=(
            "expiry-window days vs non-window days (mean daily "
            "|log return|); window = bar-open dates T-3..T"
        ),
        method=(
            "mean comparison by OLS of |log return| on the window "
            "indicator, Newey-West HAC (max lag 10); block-bootstrap "
            "CI for the mean difference"
        ),
        control=None,
        is_primary=True,
        panel_key="daily",
        test_type=EdgeTestType.MEAN_COMPARISON,
        notes=(
            "Mean-comparison edge, not a transmission edge: it tests "
            "whether BTC realized volatility differs inside the expiry "
            "window. Effect size is the window/non-window mean |log "
            "return| ratio (threshold 1.15).",
        ),
    ),
    EdgeSpec(
        edge_id="E0018",
        study="options-expiry-004",
        trial_id="T0007",
        ledger_test_key="eth_mean_abs_return_comparison",
        source="crypto:eth-usdt-perp",
        target="crypto:eth-usdt-perp",
        frequency="daily",
        condition=(
            "expiry-window days vs non-window days (mean daily "
            "|log return|); window = bar-open dates T-3..T"
        ),
        method=(
            "mean comparison by OLS of |log return| on the window "
            "indicator, Newey-West HAC (max lag 10); block-bootstrap "
            "CI for the mean difference"
        ),
        control=None,
        is_primary=False,
        panel_key="daily",
        test_type=EdgeTestType.MEAN_COMPARISON,
        notes=(
            "Mean-comparison edge, not a transmission edge: it tests "
            "whether ETH realized volatility differs inside the expiry "
            "window.",
        ),
    ),
    # Study 005 (H0007, T0010): 5-test Holm family. Event-study edges:
    # within-instrument mean-CAR tests around scheduled FOMC statement
    # days, NOT transmission edges. Self-loops by construction; no lag,
    # no partial R-squared, no OOS or cost gate. Trial T0008 (the first
    # H0007 attempt) failed on an over-strict cycle-boundary guard
    # before any results were computed; the corrected rerun is T0010.
    EdgeSpec(
        edge_id="E0019",
        study="fomc-event-study-005",
        trial_id="T0010",
        ledger_test_key="vix_car",
        source="index:vix",
        target="index:vix",
        frequency="daily",
        condition=(
            "scheduled FOMC statement days (t=0); event window [0,+1]; "
            "n = 135 events"
        ),
        method=(
            "constant-mean event study on log changes, CAR[0,+1], "
            "cluster-based normal inference (estimation window [-60,-11])"
        ),
        control=None,
        is_primary=True,
        panel_key="daily",
        test_type=EdgeTestType.EVENT_STUDY,
        notes=(
            "Primary test of H0007: the post-announcement volatility "
            "drop for equity vol. The TYVIX leg (E0023) rejected "
            "strongly; the VIX drop is much weaker.",
        ),
    ),
    EdgeSpec(
        edge_id="E0020",
        study="fomc-event-study-005",
        trial_id="T0010",
        ledger_test_key="spx_car",
        source="index:sp500",
        target="index:sp500",
        frequency="daily",
        condition=(
            "scheduled FOMC statement days (t=0); event window [0,+1]; "
            "n = 135 events"
        ),
        method=(
            "constant-mean event study on log changes, CAR[0,+1], "
            "cluster-based normal inference (estimation window [-60,-11])"
        ),
        control=None,
        is_primary=False,
        panel_key="daily",
        test_type=EdgeTestType.EVENT_STUDY,
    ),
    EdgeSpec(
        edge_id="E0021",
        study="fomc-event-study-005",
        trial_id="T0010",
        ledger_test_key="dgs10_car",
        source="rates:us-10y-yield",
        target="rates:us-10y-yield",
        frequency="daily",
        condition=(
            "scheduled FOMC statement days (t=0); event window [0,+1]; "
            "n = 135 events"
        ),
        method=(
            "constant-mean event study on level changes (bp), "
            "CAR[0,+1], cluster-based normal inference (estimation "
            "window [-60,-11])"
        ),
        control=None,
        is_primary=False,
        panel_key="daily",
        test_type=EdgeTestType.EVENT_STUDY,
        notes=("CAR in basis points of the 10-year yield level change.",),
    ),
    EdgeSpec(
        edge_id="E0022",
        study="fomc-event-study-005",
        trial_id="T0010",
        ledger_test_key="baa10y_car",
        source="credit:baa-10y-spread",
        target="credit:baa-10y-spread",
        frequency="daily",
        condition=(
            "scheduled FOMC statement days (t=0); event window [0,+1]; "
            "n = 135 events"
        ),
        method=(
            "constant-mean event study on level changes (bp), "
            "CAR[0,+1], cluster-based normal inference (estimation "
            "window [-60,-11])"
        ),
        control=None,
        is_primary=False,
        panel_key="daily",
        test_type=EdgeTestType.EVENT_STUDY,
        notes=("CAR in basis points of the BAA-10Y spread level change.",),
    ),
    EdgeSpec(
        edge_id="E0023",
        study="fomc-event-study-005",
        trial_id="T0010",
        ledger_test_key="tyvix_car",
        source="index:tyvix",
        target="index:tyvix",
        frequency="daily",
        condition=(
            "scheduled FOMC statement days (t=0); event window [0,+1]; "
            "n = 135 events"
        ),
        method=(
            "constant-mean event study on log changes, CAR[0,+1], "
            "cluster-based normal inference (estimation window [-60,-11])"
        ),
        control=None,
        is_primary=False,
        panel_key="daily",
        test_type=EdgeTestType.EVENT_STUDY,
        notes=(
            "Rates implied volatility falls sharply after FOMC "
            "statements; the effect is present in all three "
            "policy-cycle splits (descriptive).",
        ),
    ),
    # Study 005 (H0008, T0009): 3-test Holm family. Cross-section
    # edges: contemporaneous cross-event regressions (target CAR on
    # DGS10 CAR, one observation per FOMC event). Directed, but the
    # two CARs are measured over the same event window, so there is no
    # lag and no lead-lag claim; no partial R-squared, no OOS or cost
    # gate (the cross-section R-squared goes in the verdict text).
    EdgeSpec(
        edge_id="E0024",
        study="fomc-event-study-005",
        trial_id="T0009",
        ledger_test_key="spx_on_dgs10",
        source="rates:us-10y-yield",
        target="index:sp500",
        frequency="daily",
        condition=(
            "one observation per scheduled FOMC event (n = 135); CARs "
            "over the same [0,+1] window"
        ),
        method=(
            "cross-event OLS of SPX CAR[0,+1] on DGS10 CAR[0,+1], "
            "HC0 standard errors (Newey-West max lag 0)"
        ),
        control=None,
        is_primary=True,
        panel_key="daily",
        test_type=EdgeTestType.CROSS_SECTION,
        notes=(
            "Primary test of H0008. The DGS10 CAR is a proxy for the "
            "policy surprise, not the surprise itself: no free federal "
            "funds futures surprise series exists.",
            "Split-half replication (chronological, 67/68 events) is a "
            "verdict criterion; both halves' slopes were positive.",
        ),
    ),
    EdgeSpec(
        edge_id="E0025",
        study="fomc-event-study-005",
        trial_id="T0009",
        ledger_test_key="vix_on_dgs10",
        source="rates:us-10y-yield",
        target="index:vix",
        frequency="daily",
        condition=(
            "one observation per scheduled FOMC event (n = 135); CARs "
            "over the same [0,+1] window"
        ),
        method=(
            "cross-event OLS of VIX CAR[0,+1] on DGS10 CAR[0,+1], "
            "HC0 standard errors (Newey-West max lag 0)"
        ),
        control=None,
        is_primary=False,
        panel_key="daily",
        test_type=EdgeTestType.CROSS_SECTION,
    ),
    EdgeSpec(
        edge_id="E0026",
        study="fomc-event-study-005",
        trial_id="T0009",
        ledger_test_key="baa10y_on_dgs10",
        source="rates:us-10y-yield",
        target="credit:baa-10y-spread",
        frequency="daily",
        condition=(
            "one observation per scheduled FOMC event (n = 135); CARs "
            "over the same [0,+1] window"
        ),
        method=(
            "cross-event OLS of BAA10Y CAR[0,+1] on DGS10 CAR[0,+1], "
            "HC0 standard errors (Newey-West max lag 0)"
        ),
        control=None,
        is_primary=False,
        panel_key="daily",
        test_type=EdgeTestType.CROSS_SECTION,
        notes=(
            "BAA10Y contains -DGS10 by definition (spread = BAA yield "
            "minus 10-year yield), so the slope is (beta_BAA - 1): BAA "
            "yields move about 72% as much as Treasury yields in the "
            "event window. The slope and R-squared are not comparable "
            "to a clean two-asset transmission test.",
        ),
    ),
    # Study 006 (H0009, T0011): 3-test Holm family. Macro window = union
    # of FOMC statement days and CPI release days, one OKX daily bar
    # per event: the CPI window bar opened the day before the release
    # date (08:30 ET is always before the 16:00 UTC bar open); the FOMC
    # window bar opened on the statement day itself (14:00 ET is always
    # after it). Both offsets are DST-independent. The window indicator
    # is known at the bar's open because the schedules are public in
    # advance; the release content (surprise) is not measured.
    EdgeSpec(
        edge_id="E0027",
        study="macro-windows-006",
        trial_id="T0011",
        ledger_test_key="daily_btc_eth_interaction",
        source="crypto:btc-usdt-perp",
        target="crypto:eth-usdt-perp",
        frequency="daily",
        condition=(
            "macro-window interaction: BTC[t] x window[t], window = "
            "FOMC statement days + CPI release days, one OKX daily bar "
            "per event (PIT-correct)"
        ),
        method=(
            "interaction OLS (BTC[t] x window[t]), Newey-West HAC "
            "(max lag 5 daily)"
        ),
        control="SOL[t] log return",
        is_primary=True,
        panel_key="daily",
    ),
    EdgeSpec(
        edge_id="E0028",
        study="macro-windows-006",
        trial_id="T0011",
        ledger_test_key="daily_btc_eth_window",
        source="crypto:btc-usdt-perp",
        target="crypto:eth-usdt-perp",
        frequency="daily",
        condition=(
            "macro-window subsample only (FOMC statement days + CPI "
            "release days)"
        ),
        method=(
            "partial lead-lag OLS on macro-window rows only, "
            "Newey-West HAC (max lag 5 daily)"
        ),
        control="SOL[t] log return",
        is_primary=False,
        panel_key="daily",
    ),
    EdgeSpec(
        edge_id="E0029",
        study="macro-windows-006",
        trial_id="T0011",
        ledger_test_key="hourly_btc_eth_interaction",
        source="crypto:btc-usdt-perp",
        target="crypto:eth-usdt-perp",
        frequency="hourly",
        condition=(
            "macro-window interaction: BTC[t] x window[t], window = "
            "FOMC statement days + CPI release days, one OKX daily bar "
            "per event (PIT-correct)"
        ),
        method=(
            "interaction OLS (BTC[t] x window[t]), Newey-West HAC "
            "(max lag 12 hourly)"
        ),
        control="SOL[t] log return",
        is_primary=False,
        panel_key="hourly",
        notes=("Predeclared 1H robustness test.",),
    ),
    # Study 006 (H0010, T0012): 2-test Holm family. Mean-comparison
    # edges: within-instrument level tests (window vs non-window mean
    # daily |log return|), NOT transmission edges. Self-loops by
    # construction; no lag, no partial R-squared, no OOS or cost gate.
    # The first SUPPORTED mean-comparison edges in the graph.
    EdgeSpec(
        edge_id="E0030",
        study="macro-windows-006",
        trial_id="T0012",
        ledger_test_key="btc_mean_abs_return_comparison",
        source="crypto:btc-usdt-perp",
        target="crypto:btc-usdt-perp",
        frequency="daily",
        condition=(
            "macro-window days vs non-window days (mean daily "
            "|log return|); window = FOMC statement days + CPI release "
            "days"
        ),
        method=(
            "mean comparison by OLS of |log return| on the window "
            "indicator, Newey-West HAC (max lag 10); block-bootstrap "
            "CI for the mean difference"
        ),
        control=None,
        is_primary=True,
        panel_key="daily",
        test_type=EdgeTestType.MEAN_COMPARISON,
        notes=(
            "Mean-comparison edge, not a transmission edge: it tests "
            "whether BTC realized volatility differs inside the macro "
            "window. Effect size is the window/non-window mean |log "
            "return| ratio (threshold 1.15).",
        ),
    ),
    EdgeSpec(
        edge_id="E0031",
        study="macro-windows-006",
        trial_id="T0012",
        ledger_test_key="eth_mean_abs_return_comparison",
        source="crypto:eth-usdt-perp",
        target="crypto:eth-usdt-perp",
        frequency="daily",
        condition=(
            "macro-window days vs non-window days (mean daily "
            "|log return|); window = FOMC statement days + CPI release "
            "days"
        ),
        method=(
            "mean comparison by OLS of |log return| on the window "
            "indicator, Newey-West HAC (max lag 10); block-bootstrap "
            "CI for the mean difference"
        ),
        control=None,
        is_primary=False,
        panel_key="daily",
        test_type=EdgeTestType.MEAN_COMPARISON,
        notes=(
            "Mean-comparison edge, not a transmission edge: it tests "
            "whether ETH realized volatility differs inside the macro "
            "window.",
        ),
    ),
    # Study 007 (H0011, T0013): 5-test Holm family. Study 005's event
    # study re-run with every FRED leg lagged one trading day (FRED
    # posts day-t values the next business day, verified before
    # preregistration): the lagged [0,+1] window in availability terms
    # covers reference-date changes [-1,0]. Yahoo SPX is not shifted
    # and enters as an unlagged control that reproduces study 005
    # exactly. The lagged TYVIX response survives (primary, SUPPORTED);
    # the lagged VIX response is significant too, because the day +1
    # rebound drops out of the lagged window.
    EdgeSpec(
        edge_id="E0032",
        study="publication-lag-007",
        trial_id="T0013",
        ledger_test_key="tyvix_lagged_car",
        source="index:tyvix",
        target="index:tyvix",
        frequency="daily",
        condition=(
            "scheduled FOMC statement days (t=0); lagged event window "
            "[0,+1] in availability terms (reference-date changes "
            "[-1,0]); FRED legs lagged one trading day; n = 135 events"
        ),
        method=(
            "constant-mean event study on lagged log changes, "
            "CAR[0,+1], cluster-based normal inference (estimation "
            "window [-60,-11])"
        ),
        control=None,
        is_primary=True,
        panel_key="daily",
        test_type=EdgeTestType.EVENT_STUDY,
        notes=(
            "Primary test of H0011. The TYVIX drop is concentrated on "
            "day 0 (descriptive per-day AR: day 0 -0.0336, day +1 "
            "-0.0045), so the lagged window keeps most of the effect.",
        ),
    ),
    EdgeSpec(
        edge_id="E0033",
        study="publication-lag-007",
        trial_id="T0013",
        ledger_test_key="vix_lagged_car",
        source="index:vix",
        target="index:vix",
        frequency="daily",
        condition=(
            "scheduled FOMC statement days (t=0); lagged event window "
            "[0,+1] in availability terms (reference-date changes "
            "[-1,0]); FRED legs lagged one trading day; n = 135 events"
        ),
        method=(
            "constant-mean event study on lagged log changes, "
            "CAR[0,+1], cluster-based normal inference (estimation "
            "window [-60,-11])"
        ),
        control=None,
        is_primary=False,
        panel_key="daily",
        test_type=EdgeTestType.EVENT_STUDY,
        notes=(
            "Significant under the lag while the unlagged VIX test was "
            "not (study 005: Holm p = 0.160): the day +1 rebound "
            "(+0.0098) drops out of the lagged window, leaving the day "
            "0 drop (-0.0254) alone.",
        ),
    ),
    EdgeSpec(
        edge_id="E0034",
        study="publication-lag-007",
        trial_id="T0013",
        ledger_test_key="dgs10_lagged_car",
        source="rates:us-10y-yield",
        target="rates:us-10y-yield",
        frequency="daily",
        condition=(
            "scheduled FOMC statement days (t=0); lagged event window "
            "[0,+1] in availability terms (reference-date changes "
            "[-1,0]); FRED legs lagged one trading day; n = 135 events"
        ),
        method=(
            "constant-mean event study on lagged level changes (bp), "
            "CAR[0,+1], cluster-based normal inference (estimation "
            "window [-60,-11])"
        ),
        control=None,
        is_primary=False,
        panel_key="daily",
        test_type=EdgeTestType.EVENT_STUDY,
        notes=("CAR in basis points of the 10-year yield level change.",),
    ),
    EdgeSpec(
        edge_id="E0035",
        study="publication-lag-007",
        trial_id="T0013",
        ledger_test_key="baa10y_lagged_car",
        source="credit:baa-10y-spread",
        target="credit:baa-10y-spread",
        frequency="daily",
        condition=(
            "scheduled FOMC statement days (t=0); lagged event window "
            "[0,+1] in availability terms (reference-date changes "
            "[-1,0]); FRED legs lagged one trading day; n = 135 events"
        ),
        method=(
            "constant-mean event study on lagged level changes (bp), "
            "CAR[0,+1], cluster-based normal inference (estimation "
            "window [-60,-11])"
        ),
        control=None,
        is_primary=False,
        panel_key="daily",
        test_type=EdgeTestType.EVENT_STUDY,
        notes=("CAR in basis points of the BAA-10Y spread level change.",),
    ),
    EdgeSpec(
        edge_id="E0036",
        study="publication-lag-007",
        trial_id="T0013",
        ledger_test_key="spx_car",
        source="index:sp500",
        target="index:sp500",
        frequency="daily",
        condition=(
            "scheduled FOMC statement days (t=0); event window [0,+1]; "
            "n = 135 events"
        ),
        method=(
            "constant-mean event study on log changes, CAR[0,+1], "
            "cluster-based normal inference (estimation window [-60,-11])"
        ),
        control=None,
        is_primary=False,
        panel_key="daily",
        test_type=EdgeTestType.EVENT_STUDY,
        notes=(
            "Unlagged control (Yahoo SPX is not shifted): reproduces "
            "study 005's SPX CAR exactly (+0.000669, p = 0.634), as "
            "the trial's machinery guard requires.",
        ),
    ),
    # Study 007 (H0012, T0015): 3-test Holm family. The latest
    # published CPI month-on-month value (FRED CPIAUCSL, aligned by
    # release date as a step function) predicts next-day returns. The
    # step takes only 69 distinct values over 2021-2026 (one per
    # release); the 1,468 daily rows are not the effective sample size.
    # The predictor is the published MoM level, not a surprise (no
    # consensus data). T0014 is absent by design: the first H0012
    # attempt ran as T0014 and failed inside the experiment on the
    # skipped-release guard (it checked the out-of-sample November
    # 2026 release, whose MoM is undefined only because the value is
    # not published yet); the corrected rerun is T0015.
    EdgeSpec(
        edge_id="E0037",
        study="publication-lag-007",
        trial_id="T0015",
        ledger_test_key="spx_daily",
        source="macro:cpi-mom",
        target="index:sp500",
        frequency="daily",
        condition=(
            "CPI step predictor (latest published MoM, release-day "
            "aligned); next-day SPX return"
        ),
        method=(
            "partial lead-lag OLS, lag 1, Newey-West HAC "
            "(max lag 21 daily)"
        ),
        control="SPX[t] log return",
        is_primary=True,
        panel_key="daily",
        notes=(
            "Primary test of H0012. HAC max lag 21 is preregistered: "
            "the step predictor's run length is about 21 trading days.",
            "The step takes only 69 distinct values over 2021-2026; "
            "the 1,468 daily rows are not the effective sample size.",
        ),
    ),
    EdgeSpec(
        edge_id="E0038",
        study="publication-lag-007",
        trial_id="T0015",
        ledger_test_key="spx_release_day",
        source="macro:cpi-mom",
        target="index:sp500",
        frequency="daily",
        condition=(
            "CPI step predictor, release-day subsample only (n = 70 "
            "fresh-information rows)"
        ),
        method=(
            "partial lead-lag OLS on release-day rows only, "
            "Newey-West HAC (max lag 5 daily)"
        ),
        control="SPX[t] log return",
        is_primary=False,
        panel_key="daily",
        notes=(
            "Closest read in the family (raw p = 0.018, Holm p = "
            "0.053, partial R² 0.060) but it does not survive the "
            "family correction; recorded as hypothesis-generating only.",
        ),
    ),
    EdgeSpec(
        edge_id="E0039",
        study="publication-lag-007",
        trial_id="T0015",
        ledger_test_key="btc_daily",
        source="macro:cpi-mom",
        target="crypto:btc-usdt-perp",
        frequency="daily",
        condition=(
            "CPI step predictor evaluated at each OKX bar's close date "
            "(open date + 1 day); next-day BTC return"
        ),
        method=(
            "partial lead-lag OLS, lag 1, Newey-West HAC "
            "(max lag 21 daily)"
        ),
        control="BTC[t] log return",
        is_primary=False,
        panel_key="btc_daily",
        notes=("Predeclared BTC robustness test.",),
    ),
    # Study 008 (H0013, T0016): 1-test Holm family. The predictor is
    # the BAA10Y level change in basis points lagged 2 trading days by
    # availability (the latest change available at the decision close,
    # under the verified 2-trading-day BAA10Y posting lag); the VIX
    # control carries the standard 1-trading-day FRED lag. The naive
    # (unlagged, lookahead) alignment is also null, so the publication
    # lag is not what killed the effect. First real use of the 6c
    # scaffold; see the study report's scaffold-feedback section.
    EdgeSpec(
        edge_id="E0040",
        study="credit-spread-spx-008",
        trial_id="T0016",
        ledger_test_key="daily_baa10y_spx",
        source="credit:baa-10y-spread",
        target="index:sp500",
        frequency="daily",
        condition=(
            "predictor is the BAA10Y bp change lagged 2 trading days "
            "by availability (latest available at the decision close); "
            "next-day SPX return"
        ),
        method=PARTIAL_LEAD_LAG_DAILY,
        control="lagged VIX[t] log change (1-trading-day FRED lag)",
        is_primary=True,
        panel_key="daily",
        notes=(
            "Planner rank-1 candidate pair (6a, total score 1.00). "
            "Primary coefficient +1.80e-05 per bp, wrong sign vs the "
            "preregistered negative expectation; partial R² 2.19e-05.",
            "The reverse placebo (SPX->BAA10Y) is nominally significant "
            "but descriptive only, not in the family.",
        ),
    ),
    # Study 009 (H0014, T0017): 1-test Holm family. The predictor is
    # the BAA10Y level change in basis points lagged 2 trading days by
    # availability (the latest change available at the decision close,
    # under the verified 2-trading-day BAA10Y posting lag); the VIX
    # control carries the standard 1-trading-day FRED lag. The target
    # is the TYVIX daily log change. The naive (unlagged, lookahead)
    # alignment is also null, so the publication lag is not what killed
    # the effect. TYVIX was discontinued on 2020-05-15, so the sample
    # is historical-only (2003-2020). Second real use of the 6c
    # scaffold; see the study report's scaffold-feedback section.
    EdgeSpec(
        edge_id="E0041",
        study="credit-spread-tyvix-009",
        trial_id="T0017",
        ledger_test_key="daily_baa10y_tyvix",
        source="credit:baa-10y-spread",
        target="index:tyvix",
        frequency="daily",
        condition=(
            "predictor is the BAA10Y bp change lagged 2 trading days "
            "by availability (latest available at the decision close); "
            "next-day TYVIX log change"
        ),
        method=PARTIAL_LEAD_LAG_DAILY,
        control="lagged VIX[t] log change (1-trading-day FRED lag)",
        is_primary=True,
        panel_key="daily",
        notes=(
            "Planner rank-1 candidate pair (6a, total score 1.00). "
            "Primary coefficient -0.000126 per bp, wrong sign vs the "
            "preregistered positive expectation; partial R² 6.10e-05.",
            "TYVIX discontinued 2020-05-15; the sample is "
            "historical-only (2003-2020). The reverse placebo "
            "(TYVIX->BAA10Y) is not significant and descriptive only, "
            "not in the family.",
        ),
    ),
    # Study 010 (H0015, T0018): 1-test Holm family. The predictor is
    # the BAA10Y level change in basis points lagged 2 trading days by
    # availability (the latest change available at the decision close,
    # under the verified 2-trading-day BAA10Y posting lag); the SPX
    # control carries no lag (Yahoo posts the close the same evening,
    # so SPX[t] is knowable at the decision close — study 003's
    # factor-alignment precedent). The target is the VIX daily log
    # change. The naive (unlagged, lookahead) alignment is also null,
    # so the publication lag is not what killed the effect. VIX is
    # still published, so unlike study 009 the sample is the full
    # window (2003-2026). Third real use of the 6c scaffold; see the
    # study report's scaffold-feedback section.
    EdgeSpec(
        edge_id="E0042",
        study="credit-spread-vix-010",
        trial_id="T0018",
        ledger_test_key="daily_baa10y_vix",
        source="credit:baa-10y-spread",
        target="index:vix",
        frequency="daily",
        condition=(
            "predictor is the BAA10Y bp change lagged 2 trading days "
            "by availability (latest available at the decision close); "
            "next-day VIX log change"
        ),
        method=PARTIAL_LEAD_LAG_DAILY,
        control="SPX[t] log return (Yahoo posts the close the same evening)",
        is_primary=True,
        panel_key="daily",
        notes=(
            "Planner rank-1 candidate pair (6a, total score 1.00). "
            "Primary coefficient -0.000063 per bp, wrong sign vs the "
            "preregistered positive expectation; partial R² 6.55e-06.",
            "Full window (2003-2026): VIX is still published. The "
            "reverse placebo (VIX->BAA10Y) is not significant and "
            "descriptive only, not in the family.",
        ),
    ),
    # Study 011 (H0016, T0019): 1-test Holm family. The predictor is
    # the BAA10Y level change in basis points lagged 2 trading days by
    # availability (the latest change available at the decision close,
    # under the verified 2-trading-day BAA10Y posting lag); the SPX
    # control carries no lag (Yahoo posts the close the same evening,
    # so SPX[t] is knowable at the decision close — study 003's
    # factor-alignment precedent). The target is the VXN daily log
    # change. The naive (unlagged, lookahead) alignment is also null,
    # so the publication lag is not what killed the effect. First study
    # to use the refreshed VXN panel (PR #25, VXNCLS to 2026-11-17);
    # full window (2003-2026). Fourth real use of the 6c scaffold; see
    # the study report's scaffold-feedback section.
    EdgeSpec(
        edge_id="E0043",
        study="credit-spread-vxn-011",
        trial_id="T0019",
        ledger_test_key="daily_baa10y_vxn",
        source="credit:baa-10y-spread",
        target="index:vxn",
        frequency="daily",
        condition=(
            "predictor is the BAA10Y bp change lagged 2 trading days "
            "by availability (latest available at the decision close); "
            "next-day VXN log change"
        ),
        method=PARTIAL_LEAD_LAG_DAILY,
        control="SPX[t] log return (Yahoo posts the close the same evening)",
        is_primary=True,
        panel_key="daily",
        notes=(
            "Planner rank-1 candidate pair (6a, total score 1.00). "
            "Primary coefficient -0.000097 per bp, wrong sign vs the "
            "preregistered positive expectation; partial R² 2.29e-05.",
            "Full window (2003-2026): first study on the refreshed "
            "VXN panel (PR #25). The reverse placebo (VXN->BAA10Y) "
            "is not significant and descriptive only, not in the "
            "family.",
        ),
    ),
    # Study 012 (H0017, T0020): 1-test Holm family. The predictor is
    # the BAA10Y level change in basis points lagged 2 trading days by
    # availability (the latest change available at the decision close,
    # under the verified 2-trading-day BAA10Y posting lag); the SPX
    # control carries no lag (Yahoo posts the close the same evening,
    # so SPX[t] is knowable at the decision close — study 003's
    # factor-alignment precedent). The target is the DGS10 daily
    # LEVEL change in basis points, not the log change — a yield has
    # no meaningful log return. Mechanical confound (same class as
    # E0026's caveat): BAA10Y = BAA − DGS10 by definition, so the
    # predictor contains minus the target's own lag-2 change, and the
    # mechanical sign coincides with the preregistered negative
    # direction. The baseline therefore controls for the target's own
    # lag-2 change as a PIT-clean mechanical guard (retained in the
    # no-factor bound). The naive (unlagged, lookahead) alignment is
    # also null, so the publication lag is not what killed the effect.
    # Full window (2003-2026). Fifth real use of the 6c scaffold; see
    # the study report's scaffold-feedback section. H0017 was amended
    # pre-trial from v1 to v2 (FRED BAA is monthly only, so the
    # decomposition leg derives ΔBAA from the identity instead).
    EdgeSpec(
        edge_id="E0044",
        study="credit-spread-dgs10-012",
        trial_id="T0020",
        ledger_test_key="daily_baa10y_dgs10",
        source="credit:baa-10y-spread",
        target="rates:us-10y-yield",
        frequency="daily",
        condition=(
            "predictor is the BAA10Y bp change lagged 2 trading days "
            "by availability (latest available at the decision close); "
            "next-day DGS10 level change in bp; baseline controls for "
            "the target's own lag-2 change as a mechanical guard"
        ),
        method=PARTIAL_LEAD_LAG_DAILY,
        control=(
            "SPX[t] log return (Yahoo posts the close the same evening) "
            "+ DGS10 lag-2 change (mechanical guard)"
        ),
        is_primary=True,
        panel_key="daily",
        notes=(
            "Planner rank-1 candidate pair (6a, total score 1.00). "
            "Primary coefficient -0.049085 per bp, preregistered "
            "negative sign, p=0.1819; partial R² 0.000576.",
            "Mechanical caveat: BAA10Y contains minus DGS10 by "
            "definition, so the predictor contains the target's own "
            "lag-2 change; the baseline's lag-2 guard blocks the "
            "channel (predictor-guard correlation -0.3869; DGS10 "
            "change autocorrelations lag-1 -0.0118, lag-2 -0.0503). "
            "The reverse placebo (DGS10->BAA10Y) is nominally "
            "significant (p=0.0194) but descriptive only, below the "
            "0.005 threshold, and itself mechanically confounded.",
        ),
    ),
    # Study 013 (H0018, T0021): 1-test Holm family. The predictor is
    # the BTC daily log return (OKX BTC-USDT-SWAP 1D, bars open 16:00
    # UTC), lag-1; the ETH control carries no lag (same bar as the
    # predictor). The target is the BTC_DVOL daily log change, where
    # the daily DVOL value is the 16:00 UTC snapshot (the close of
    # the Deribit hourly DVOL row timestamped 15:00 UTC), aligned to
    # the OKX bar grid — the daily DVOL endpoint timestamps points at
    # 00:00 UTC, which would leave an 8-hour overlap between the
    # predictor and target windows. There is no FRED-style
    # publication lag: both legs are real-time. The same-bar (naive)
    # alignment is also null, so the lag is not what killed the
    # effect. The amplitude check (|BTC| -> DVOL) is nominally
    # significant (p=6.6e-06, partial R² 0.00993) but with a NEGATIVE
    # coefficient and descriptive only — consistent with DVOL level
    # mean-reversion, not a leverage channel; not promoted. First
    # DVOL study; first fully crypto-native panel (24/7 calendar).
    # Sixth real use of the 6c scaffold; see the study report's
    # scaffold-feedback section.
    EdgeSpec(
        edge_id="E0045",
        study="btc-dvol-013",
        trial_id="T0021",
        ledger_test_key="daily_btc_dvol",
        source="crypto:btc-usdt-perp",
        target="index:btc-dvol",
        frequency="daily",
        condition=(
            "predictor is the BTC daily log return lag-1 (no "
            "publication lag — both legs real-time); next-day "
            "BTC_DVOL log change (16:00 UTC snapshot)"
        ),
        method=PARTIAL_LEAD_LAG_DAILY,
        control="ETH[t] log return (same bar as the predictor)",
        is_primary=True,
        panel_key="daily",
        notes=(
            "Planner rank-1 candidate pair (6a, total score 1.00). "
            "Primary coefficient +0.100154 per unit log return, "
            "wrong sign vs the preregistered negative leverage-effect "
            "expectation, p=0.2269; partial R² 0.001195.",
            "Same-bar correlation -0.2691 (the leverage effect is "
            "contemporaneous); lag-1 correlation +0.0270 (null). "
            "The reverse placebo (BTC_DVOL->BTC) is nominally "
            "significant (p=0.0317) but descriptive only, below the "
            "0.005 threshold and the MDE (0.003787).",
        ),
    ),
)

# One entry per trial: (trial id, study directory, hypothesis id,
# registration version, report path). A study directory may hold more
# than one trial (study 004 has T0005 and T0007 in one directory;
# study 005 has T0010 and T0009; study 006 has T0011 and T0012).
# T0006 is absent by design: the first H0006 attempt ran as T0006 and
# failed inside the experiment (a bootstrap-weights bug, recorded as a
# failed trial in the ledger); the corrected rerun is T0007. T0008 is
# absent for the same reason: the first H0007 attempt ran as T0008 and
# failed inside the experiment (an over-strict cycle-boundary guard,
# recorded as a failed trial in the ledger); the corrected rerun is
# T0010. T0014 is absent for the same reason: the first H0012 attempt
# ran as T0014 and failed inside the experiment (the skipped-release
# guard checked the out-of-sample November 2026 release, recorded as a
# failed trial in the ledger); the corrected rerun is T0015.
TRIALS: tuple[tuple[str, str, str, int, str], ...] = (
    ("T0001", "btc-eth-001", "H0001", 1, "docs/studies/btc-eth-transmission-001.md"),
    ("T0002", "lowvol-002", "H0002", 1, "docs/studies/lowvol-transmission-002.md"),
    ("T0004", "move-vix-003", "H0004", 2, "docs/studies/move-vix-transmission-003.md"),
    ("T0005", "options-expiry-004", "H0005", 1, "docs/studies/options-expiry-004.md"),
    ("T0007", "options-expiry-004", "H0006", 1, "docs/studies/options-expiry-004.md"),
    ("T0010", "fomc-event-study-005", "H0007", 1, "docs/studies/fomc-event-study-005.md"),
    ("T0009", "fomc-event-study-005", "H0008", 1, "docs/studies/fomc-event-study-005.md"),
    ("T0011", "macro-windows-006", "H0009", 1, "docs/studies/macro-windows-006.md"),
    ("T0012", "macro-windows-006", "H0010", 1, "docs/studies/macro-windows-006.md"),
    ("T0013", "publication-lag-007", "H0011", 1, "docs/studies/publication-lag-007.md"),
    ("T0015", "publication-lag-007", "H0012", 1, "docs/studies/publication-lag-007.md"),
    ("T0016", "credit-spread-spx-008", "H0013", 1, "docs/studies/credit-spread-spx-008.md"),
    ("T0017", "credit-spread-tyvix-009", "H0014", 1, "docs/studies/credit-spread-tyvix-009.md"),
    ("T0018", "credit-spread-vix-010", "H0015", 1, "docs/studies/credit-spread-vix-010.md"),
    ("T0019", "credit-spread-vxn-011", "H0016", 1, "docs/studies/credit-spread-vxn-011.md"),
    ("T0020", "credit-spread-dgs10-012", "H0017", 2, "docs/studies/credit-spread-dgs10-012.md"),
    ("T0021", "btc-dvol-013", "H0018", 1, "docs/studies/btc-dvol-013.md"),
)

STUDY_DIRS: tuple[str, ...] = tuple(
    dict.fromkeys(study for _, study, _, _, _ in TRIALS)
)

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


def _load_trial(
    repo_root: Path,
    trial_id: str,
    study: str,
    hypothesis_id: str,
    version: int,
    report_path: str,
) -> StudyData:
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
        if spec.trial_id == trial_id and spec.is_primary
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


def _load_nodes(
    repo_root: Path, trials: dict[str, StudyData]
) -> tuple[NodeRecord, ...]:
    catalogs: dict[str, dict] = {}
    for study in STUDY_DIRS:
        instruments = repo_root / "research" / study / "catalog" / "instruments"
        for version_file in sorted(instruments.glob("*/v1.json")):
            record = _read_json(version_file)
            catalogs.setdefault(record["instrument_id"], record)
    nodes: list[NodeRecord] = []
    for instrument_id in sorted(catalogs):
        record = catalogs[instrument_id]
        member_of = tuple(
            sorted(
                {
                    data.study
                    for data in trials.values()
                    if instrument_id in data.registration["spec"]["universe"]
                }
            )
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
    """Holdout OOS incremental R² for the primary test, per trial."""
    if "walk_forward" not in data.metrics:
        raise ValueError(
            f"trial {data.trial_id} has no walk-forward evaluation; "
            "its primary edge cannot carry an OOS score"
        )
    walk_forward = data.metrics["walk_forward"]
    if data.trial_id == "T0002":
        value = walk_forward["lowvol_holdout_oos_incremental_r_squared"]
        note = (
            "Low-volatility holdout rows only (the acceptance criterion; "
            f"{walk_forward['lowvol_holdout_folds']} folds, "
            f"{walk_forward['lowvol_holdout_test_rows']} rows). "
            "All-holdout incremental OOS R² was "
            f"{walk_forward['holdout_oos_incremental_r_squared']:+.5f}."
        )
        return value, note
    if data.trial_id == "T0005":
        value = walk_forward["window_holdout_oos_incremental_r_squared"]
        note = (
            "Expiry-window holdout rows only (the acceptance criterion; "
            f"{walk_forward['window_holdout_folds']} folds, "
            f"{walk_forward['window_holdout_test_rows']} rows). "
            "All-holdout incremental OOS R² was "
            f"{walk_forward['holdout_oos_incremental_r_squared']:+.5f}."
        )
        return value, note
    if data.trial_id == "T0011":
        value = walk_forward["window_holdout_oos_incremental_r_squared"]
        note = (
            "Macro-window holdout rows only (the acceptance criterion; "
            f"{walk_forward['window_holdout_folds']} folds, "
            f"{walk_forward['window_holdout_test_rows']} rows). "
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
    """Cost gate for the primary test, per trial."""
    if data.trial_id == "T0004":
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
    if data.trial_id == "T0015":
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
                "Informational only: no costs applied. The S&P 500 index "
                "is not directly tradable and no free SPX futures or ETF "
                "price series is used. Not a verdict criterion."
            ),
        )
    if data.trial_id == "T0017":
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
                "Informational only: no costs applied. TYVIX is not "
                "tradable; no listed TYVIX futures exist and no clean "
                "free cost series is available. Not a verdict criterion."
            ),
        )
    if data.trial_id == "T0018":
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
                "Informational only: no costs applied. VIX is not "
                "tradable; VIX futures roll costs are unmeasurable "
                "from free data (Yahoo VX=F returns no data). Not a "
                "verdict criterion."
            ),
        )
    if data.trial_id == "T0019":
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
                "Informational only: no costs applied. VXN is not "
                "tradable; VXN futures (VN) existed historically on "
                "CFE but are not currently listed, and no free VXN "
                "futures price series exists (Yahoo VN=F returns no "
                "data). Not a verdict criterion."
            ),
        )
    if data.trial_id == "T0020":
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
                "Informational only: no costs applied. DGS10 is a "
                "yield and is not directly tradable; free proxy series "
                "exist (Yahoo ZN=F and IEF) but the DV01/duration "
                "conversion and futures roll handling are not modelled, "
                "so no clean cost measurement is available. Gross edge "
                "in basis points per day. Not a verdict criterion."
            ),
        )
    if data.trial_id == "T0021":
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
                "Informational only: no costs applied. BTC_DVOL is an "
                "index and is not directly tradable; the tradable "
                "proxy (a Deribit BTC options straddle) has no clean "
                "free cost series — Deribit's public API returns "
                "no_data for BTC option chart data and expired "
                "listings return only the most recent batch. Gross "
                "edge in log-change units per day. Not a verdict "
                "criterion."
            ),
        )
    gate = data.metrics["cost_gate"]
    if data.trial_id == "T0002":
        note = (
            "Sign rule on low-volatility holdout rows only; flat on "
            "high-volatility rows. Net edge averaged over all "
            f"{gate['days']} holdout rows (including {gate['lowvol_days']} "
            "low-volatility rows). 0.05% taker fee per side; funding, "
            "slippage and market impact ignored."
        )
    elif data.trial_id == "T0005":
        note = (
            "Sign rule on expiry-window holdout rows only; flat on "
            "non-window rows. Net edge averaged over all "
            f"{gate['days']} holdout rows (including {gate['window_days']} "
            "expiry-window rows). 0.05% taker fee per side; funding, "
            "slippage and market impact ignored."
        )
    elif data.trial_id == "T0011":
        note = (
            "Sign rule on macro-window holdout rows only; flat on "
            "non-window rows. Net edge averaged over all "
            f"{gate['days']} holdout rows (including {gate['window_days']} "
            "macro-window rows). 0.05% taker fee per side; funding, "
            "slippage and market impact ignored."
        )
    elif data.trial_id == "T0016":
        note = (
            "Sign rule on holdout OOS forecasts. SPY bid-ask spread "
            "1bp per side (2bp round trip per flip); slippage and "
            "market impact ignored."
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


def _holm_entry(data: StudyData, test_key: str) -> dict:
    for entry in data.metrics["holm"]:
        if entry["test"] == test_key:
            return entry
    raise ValueError(f"trial {data.trial_id} has no Holm entry for {test_key}")


def _lead_lag_primary_verdict(
    data: StudyData,
    test: dict,
    holm_p: float,
    oos_value: float,
    cost_gate: CostGateRecord,
    *,
    supported: bool,
) -> str:
    """Verdict text for a lead-lag primary edge, from the actual numbers.

    The rejected wording reproduces the established sentences exactly
    when the facts match (test did not reject, partial R² below
    threshold); each clause is conditional so the text stays factual
    when only some criteria fail.
    """
    verdict = "SUPPORTED" if supported else "REJECTED"
    if holm_p < 0.05:
        p_part = f"this test rejected (Holm-adjusted p = {holm_p:.3f})"
    else:
        p_part = f"this test did not reject (Holm-adjusted p = {holm_p:.3f})"
    partial_r2 = test["partial_r_squared"]
    if partial_r2 is not None and partial_r2 >= 0.005:
        r2_part = f"partial R² {partial_r2:.6g} at or above the 0.005 threshold"
    elif partial_r2 is None:
        r2_part = "partial R² unavailable"
    else:
        r2_part = f"partial R² {partial_r2:.6g} below the 0.005 threshold"
    oos_part = f"holdout OOS incremental R² {oos_value:+.5f}"
    if cost_gate.verdict is CostGateVerdict.INFORMATIONAL:
        if data.trial_id == "T0004":
            return (
                f"Hypothesis {data.hypothesis_id} {verdict} "
                f"(trial {data.trial_id}): {p_part}; {r2_part}; {oos_part}; "
                "cost gate informational (gross daily "
                f"edge {cost_gate.gross_daily_edge:+.4%}, 95% CI includes "
                "zero) — no net edge measurable without VIX futures data."
            )
        ci_includes_zero = (
            cost_gate.ci_lower is not None
            and cost_gate.ci_upper is not None
            and cost_gate.ci_lower <= 0.0 <= cost_gate.ci_upper
        )
        ci_part = (
            "95% CI includes zero" if ci_includes_zero else "95% CI excludes zero"
        )
        if data.trial_id == "T0017":
            return (
                f"Hypothesis {data.hypothesis_id} {verdict} "
                f"(trial {data.trial_id}): {p_part}; {r2_part}; {oos_part}; "
                "cost gate informational (gross daily "
                f"edge {cost_gate.gross_daily_edge:+.4%}, {ci_part}) — no "
                "net edge measurable: TYVIX is not tradable and no "
                "listed TYVIX futures exist."
            )
        if data.trial_id == "T0018":
            return (
                f"Hypothesis {data.hypothesis_id} {verdict} "
                f"(trial {data.trial_id}): {p_part}; {r2_part}; {oos_part}; "
                "cost gate informational (gross daily "
                f"edge {cost_gate.gross_daily_edge:+.4%}, {ci_part}) — no "
                "net edge measurable: VIX is not tradable and no free "
                "VIX futures series exists."
            )
        if data.trial_id == "T0019":
            return (
                f"Hypothesis {data.hypothesis_id} {verdict} "
                f"(trial {data.trial_id}): {p_part}; {r2_part}; {oos_part}; "
                "cost gate informational (gross daily "
                f"edge {cost_gate.gross_daily_edge:+.4%}, {ci_part}) — no "
                "net edge measurable: VXN is not tradable; VXN futures "
                "(VN) existed historically on CFE but are not currently "
                "listed, and no free VXN futures price series exists."
            )
        if data.trial_id == "T0020":
            return (
                f"Hypothesis {data.hypothesis_id} {verdict} "
                f"(trial {data.trial_id}): {p_part}; {r2_part}; {oos_part}; "
                "cost gate informational (gross daily "
                f"edge {cost_gate.gross_daily_edge:+.4%}, {ci_part}) — no "
                "net edge measurable: DGS10 is a yield and is not "
                "directly tradable; the DV01/duration conversion and "
                "futures roll handling are not modelled."
            )
        if data.trial_id == "T0021":
            return (
                f"Hypothesis {data.hypothesis_id} {verdict} "
                f"(trial {data.trial_id}): {p_part}; {r2_part}; {oos_part}; "
                "cost gate informational (gross daily "
                f"edge {cost_gate.gross_daily_edge:+.4%}, {ci_part}) — no "
                "net edge measurable: BTC_DVOL is not tradable and no "
                "clean straddle cost series exists (Deribit's public "
                "API returns no_data for BTC option chart data)."
            )
        return (
            f"Hypothesis {data.hypothesis_id} {verdict} "
            f"(trial {data.trial_id}): {p_part}; {r2_part}; {oos_part}; "
            "cost gate informational (gross daily "
            f"edge {cost_gate.gross_daily_edge:+.4%}, {ci_part}) — no net "
            "edge measurable without a tradable SPX price series."
        )
    return (
        f"Hypothesis {data.hypothesis_id} {verdict} "
        f"(trial {data.trial_id}): {p_part}; {r2_part}; {oos_part}; "
        f"cost gate {cost_gate.verdict.value} "
        f"(net daily edge {cost_gate.net_daily_edge:+.4%})."
    )


def _lead_lag_secondary_verdict(
    data: StudyData,
    test: dict,
    holm_p: float,
    *,
    hypothesis_supported: bool,
    test_rejected: bool,
) -> str:
    """Verdict text for a lead-lag secondary edge.

    When the hypothesis was rejected and the test did not reject, this
    reproduces the established sentence exactly. Otherwise the text
    separates the test outcome from the hypothesis verdict (decided by
    the primary test).
    """
    hypothesis_verdict = "SUPPORTED" if hypothesis_supported else "REJECTED"
    if not hypothesis_supported and not test_rejected:
        return (
            f"Hypothesis {data.hypothesis_id} REJECTED "
            f"(trial {data.trial_id}): this test did not reject "
            f"(Holm-adjusted p = {holm_p:.3f}, partial R² "
            f"{test['partial_r_squared']:.6g})."
        )
    if test_rejected:
        test_part = (
            f"this test rejected (Holm-adjusted p = {holm_p:.3f}, "
            f"partial R² {test['partial_r_squared']:.6g})"
        )
    else:
        test_part = (
            f"this secondary test did not reject "
            f"(Holm-adjusted p = {holm_p:.3f}, partial R² "
            f"{test['partial_r_squared']:.6g})"
        )
    return (
        f"Hypothesis {data.hypothesis_id} {hypothesis_verdict} "
        f"(trial {data.trial_id}): {test_part}; the hypothesis verdict "
        f"is decided by the primary test ({data.primary_edge_id})."
    )


def _mean_comparison_primary_verdict(
    data: StudyData,
    test: dict,
    holm_p: float,
    threshold: float,
    *,
    supported: bool,
) -> str:
    """Verdict text for a mean-comparison primary edge.

    No OOS or cost-gate clause: a level comparison is not a forecast.
    The effect size is the window/non-window mean |log return| ratio.
    """
    verdict = "SUPPORTED" if supported else "REJECTED"
    if holm_p < 0.05:
        p_part = f"this test rejected (Holm-adjusted p = {holm_p:.3f})"
    else:
        p_part = f"this test did not reject (Holm-adjusted p = {holm_p:.3f})"
    ratio = test["effect_ratio"]
    if ratio >= threshold:
        ratio_part = (
            f"window/non-window mean |log return| ratio {ratio:.4f} "
            f"at or above the {threshold:.2f} threshold"
        )
    else:
        ratio_part = (
            f"window/non-window mean |log return| ratio {ratio:.4f} "
            f"below the {threshold:.2f} threshold"
        )
    return (
        f"Hypothesis {data.hypothesis_id} {verdict} "
        f"(trial {data.trial_id}): {p_part}; {ratio_part}; mean "
        f"difference {test['coefficient']:+.6f} (95% block-bootstrap CI "
        f"[{test['bootstrap_ci_lower']:+.6f}, "
        f"{test['bootstrap_ci_upper']:+.6f}]). No OOS or cost-gate "
        "criterion: level comparison, not a forecast."
    )


def _mean_comparison_secondary_verdict(
    data: StudyData,
    test: dict,
    holm_p: float,
    *,
    hypothesis_supported: bool,
    test_rejected: bool,
) -> str:
    """Verdict text for a mean-comparison secondary edge."""
    hypothesis_verdict = "SUPPORTED" if hypothesis_supported else "REJECTED"
    ratio_part = (
        f"window/non-window mean |log return| ratio "
        f"{test['effect_ratio']:.4f}"
    )
    if test_rejected:
        test_part = f"this test rejected (Holm-adjusted p = {holm_p:.3f})"
    else:
        test_part = f"this test did not reject (Holm-adjusted p = {holm_p:.3f})"
    if not hypothesis_supported and not test_rejected:
        return (
            f"Hypothesis {data.hypothesis_id} REJECTED "
            f"(trial {data.trial_id}): {test_part}; {ratio_part}."
        )
    return (
        f"Hypothesis {data.hypothesis_id} {hypothesis_verdict} "
        f"(trial {data.trial_id}): {test_part}; {ratio_part}; the "
        "hypothesis verdict is decided by the primary test "
        f"({data.primary_edge_id})."
    )


def _event_study_primary_verdict(
    data: StudyData,
    test: dict,
    holm_p: float,
    threshold: float,
    *,
    supported: bool,
) -> str:
    """Verdict text for an event-study primary edge.

    No OOS or cost-gate clause: an event study is not a forecast. The
    effect size is the standardized mean CAR (threshold 0.3, negative
    direction for the volatility legs).
    """
    verdict = "SUPPORTED" if supported else "REJECTED"
    if holm_p < 0.05:
        p_part = f"this test rejected (Holm-adjusted p = {holm_p:.3f})"
    else:
        p_part = f"this test did not reject (Holm-adjusted p = {holm_p:.3f})"
    std_car = test["standardized_mean_car"]
    if std_car <= -threshold:
        effect_part = (
            f"standardized mean CAR {std_car:.4f} at or below "
            f"the -{threshold:.2f} threshold"
        )
    else:
        effect_part = (
            f"standardized mean CAR {std_car:.4f} above "
            f"the -{threshold:.2f} threshold"
        )
    return (
        f"Hypothesis {data.hypothesis_id} {verdict} "
        f"(trial {data.trial_id}): {p_part}; {effect_part}; mean CAR "
        f"{test['coefficient']:+.6f} over [0,+1] (n = "
        f"{test['observations']} events). No OOS or cost-gate "
        "criterion: event study, not a forecast."
    )


def _event_study_secondary_verdict(
    data: StudyData,
    test: dict,
    holm_p: float,
    *,
    hypothesis_supported: bool,
    test_rejected: bool,
) -> str:
    """Verdict text for an event-study secondary edge."""
    hypothesis_verdict = "SUPPORTED" if hypothesis_supported else "REJECTED"
    effect_part = (
        f"standardized mean CAR {test['standardized_mean_car']:.4f}"
    )
    if test_rejected:
        test_part = f"this test rejected (Holm-adjusted p = {holm_p:.3f})"
    else:
        test_part = f"this test did not reject (Holm-adjusted p = {holm_p:.3f})"
    if not hypothesis_supported and not test_rejected:
        return (
            f"Hypothesis {data.hypothesis_id} REJECTED "
            f"(trial {data.trial_id}): {test_part}; {effect_part}."
        )
    return (
        f"Hypothesis {data.hypothesis_id} {hypothesis_verdict} "
        f"(trial {data.trial_id}): {test_part}; {effect_part}; the "
        "hypothesis verdict is decided by the primary test "
        f"({data.primary_edge_id})."
    )


def _cross_section_primary_verdict(
    data: StudyData,
    test: dict,
    holm_p: float,
    threshold: float,
    split_half: dict,
    *,
    supported: bool,
) -> str:
    """Verdict text for a cross-section primary edge.

    No OOS or cost-gate clause: an event study is not a forecast. The
    effect size is the cross-event R-squared; the split-half
    replication is the out-of-sample-style criterion.
    """
    verdict = "SUPPORTED" if supported else "REJECTED"
    if holm_p < 0.05:
        p_part = f"this test rejected (Holm-adjusted p = {holm_p:.3f})"
    else:
        p_part = f"this test did not reject (Holm-adjusted p = {holm_p:.3f})"
    r_squared = test["r_squared"]
    if r_squared >= threshold:
        r2_part = f"R² {r_squared:.4f} at or above the {threshold:.2f} threshold"
    else:
        r2_part = f"R² {r_squared:.4f} below the {threshold:.2f} threshold"
    first = split_half["first_half"]
    second = split_half["second_half"]
    if split_half["replicated"]:
        split_part = (
            "split-half replication passed (both halves' slopes "
            f"negative and significant: {first['coefficient']:+.6f}, "
            f"{second['coefficient']:+.6f})"
        )
    else:
        split_part = (
            "split-half replication failed (first-half slope "
            f"{first['coefficient']:+.6f}, second-half slope "
            f"{second['coefficient']:+.6f})"
        )
    return (
        f"Hypothesis {data.hypothesis_id} {verdict} "
        f"(trial {data.trial_id}): {p_part}; {r2_part}; {split_part}. "
        "No OOS or cost-gate criterion: event study, not a forecast."
    )


def _cross_section_secondary_verdict(
    data: StudyData,
    test: dict,
    holm_p: float,
    *,
    hypothesis_supported: bool,
    test_rejected: bool,
) -> str:
    """Verdict text for a cross-section secondary edge."""
    hypothesis_verdict = "SUPPORTED" if hypothesis_supported else "REJECTED"
    effect_part = f"R² {test['r_squared']:.4f}"
    if test_rejected:
        test_part = f"this test rejected (Holm-adjusted p = {holm_p:.3f})"
    else:
        test_part = f"this test did not reject (Holm-adjusted p = {holm_p:.3f})"
    if not hypothesis_supported and not test_rejected:
        return (
            f"Hypothesis {data.hypothesis_id} REJECTED "
            f"(trial {data.trial_id}): {test_part}; {effect_part}."
        )
    return (
        f"Hypothesis {data.hypothesis_id} {hypothesis_verdict} "
        f"(trial {data.trial_id}): {test_part}; {effect_part}; the "
        "hypothesis verdict is decided by the primary test "
        f"({data.primary_edge_id})."
    )


def _build_tested_edge(spec: EdgeSpec, data: StudyData) -> EdgeRecord:
    assert spec.ledger_test_key is not None
    test = data.metrics["tests"][spec.ledger_test_key]
    holm_entry = _holm_entry(data, spec.ledger_test_key)
    holm_p = holm_entry["adjusted_p_value"]
    hypothesis_supported = bool(data.metrics["verdict"]["supported"])
    test_rejected = bool(holm_entry["reject"])
    is_mean_comparison = spec.test_type is EdgeTestType.MEAN_COMPARISON
    is_event_study = spec.test_type is EdgeTestType.EVENT_STUDY
    is_cross_section = spec.test_type is EdgeTestType.CROSS_SECTION
    # Mean comparisons, event studies and cross-section regressions are
    # not forecasts: no lag, no OOS score, no cost gate.
    is_level_test = is_mean_comparison or is_event_study or is_cross_section
    lag = (
        None
        if is_level_test
        else int(_fixed_parameter(data.registration["spec"], "lag"))
    )
    if spec.is_primary:
        status = (
            EdgeStatus.SUPPORTED if hypothesis_supported else EdgeStatus.REJECTED
        )
        if is_mean_comparison:
            oos_value, oos_note = None, (
                "No OOS score: level comparison, not a forecast."
            )
            cost_gate, cost_note = None, (
                f"No cost gate: {data.hypothesis_id} is a volatility-level "
                "comparison, not a forecast; there is no trading rule to cost."
            )
            threshold = float(
                _fixed_parameter(
                    data.registration["spec"], "effect_ratio_threshold"
                )
            )
            verdict = _mean_comparison_primary_verdict(
                data, test, holm_p, threshold, supported=hypothesis_supported
            )
        elif is_event_study:
            oos_value, oos_note = None, (
                "No OOS score: event study, not a forecast."
            )
            cost_gate, cost_note = None, (
                f"No cost gate: {data.hypothesis_id} is an event study, "
                "not a forecast; there is no trading rule to cost."
            )
            threshold = float(
                _fixed_parameter(
                    data.registration["spec"], "standardized_effect_threshold"
                )
            )
            verdict = _event_study_primary_verdict(
                data, test, holm_p, threshold, supported=hypothesis_supported
            )
        elif is_cross_section:
            oos_value, oos_note = None, (
                "No OOS score: event study, not a forecast."
            )
            cost_gate, cost_note = None, (
                f"No cost gate: {data.hypothesis_id} is an event study, "
                "not a forecast; there is no trading rule to cost."
            )
            threshold = float(
                _fixed_parameter(data.registration["spec"], "r_squared_threshold")
            )
            verdict = _cross_section_primary_verdict(
                data,
                test,
                holm_p,
                threshold,
                data.metrics["split_half"],
                supported=hypothesis_supported,
            )
        else:
            oos_value, oos_note = _trial_level_oos(data)
            cost_gate = _trial_level_cost(data)
            cost_note = None
            verdict = _lead_lag_primary_verdict(
                data, test, holm_p, oos_value, cost_gate,
                supported=hypothesis_supported,
            )
    else:
        status = EdgeStatus.SUPPORTED if test_rejected else EdgeStatus.REJECTED
        if is_mean_comparison:
            # Level comparisons have no OOS score or cost gate at all, so
            # the generic "measured for the primary test only" notes would
            # mislead: the primary has none either.
            oos_value, oos_note = None, (
                "No OOS score: level comparison, not a forecast."
            )
            cost_gate, cost_note = None, (
                f"No cost gate: {data.hypothesis_id} is a volatility-level "
                "comparison, not a forecast; there is no trading rule to cost."
            )
        elif is_level_test:
            # Event studies and cross-section regressions have no OOS
            # score or cost gate at all, for the same reason.
            oos_value, oos_note = None, (
                "No OOS score: event study, not a forecast."
            )
            cost_gate, cost_note = None, (
                f"No cost gate: {data.hypothesis_id} is an event study, "
                "not a forecast; there is no trading rule to cost."
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
        if is_mean_comparison:
            verdict = _mean_comparison_secondary_verdict(
                data, test, holm_p,
                hypothesis_supported=hypothesis_supported,
                test_rejected=test_rejected,
            )
        elif is_event_study:
            verdict = _event_study_secondary_verdict(
                data, test, holm_p,
                hypothesis_supported=hypothesis_supported,
                test_rejected=test_rejected,
            )
        elif is_cross_section:
            verdict = _cross_section_secondary_verdict(
                data, test, holm_p,
                hypothesis_supported=hypothesis_supported,
                test_rejected=test_rejected,
            )
        else:
            verdict = _lead_lag_secondary_verdict(
                data, test, holm_p,
                hypothesis_supported=hypothesis_supported,
                test_rejected=test_rejected,
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
        status=status,
        test_type=spec.test_type,
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
        if spec.trial_id == data.trial_id and spec.ledger_test_key is not None
    }
    missing = family - mapped
    if missing:
        raise ValueError(
            f"{data.trial_id}: Holm-family tests without an edge spec: "
            f"{sorted(missing)} — extend EDGE_SPECS before rebuilding"
        )
    unknown = mapped - set(data.metrics["tests"])
    if unknown:
        raise ValueError(
            f"{data.trial_id}: edge specs without a ledger test: {sorted(unknown)}"
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
    trials = {
        trial_id: _load_trial(
            repo_root, trial_id, study, hypothesis_id, version, report_path
        )
        for trial_id, study, hypothesis_id, version, report_path in TRIALS
    }
    for data in trials.values():
        _check_family_coverage(data)
    nodes = _load_nodes(repo_root, trials)
    edges: list[EdgeRecord] = []
    for spec in EDGE_SPECS:
        edges.append(_build_tested_edge(spec, trials[spec.trial_id]))
    edges.append(_build_pending_edge(repo_root, trials["T0002"]))
    edges.append(_build_cross_venue_edge(trials["T0002"]))
    edges.append(_build_reverse_placebo_edge(trials["T0004"]))
    edges.sort(key=lambda edge: edge.edge_id)
    edge_tuple = tuple(edges)
    candidates = build_candidates(
        nodes, edge_tuple, descriptive_notes=DESCRIPTIVE_NOTES
    )
    h0003_registration, h0003_path = _read_registration(
        repo_root, "lowvol-002", "H0003", 1
    )
    provenance = (
        _provenance(trials["T0001"]),
        _provenance(trials["T0002"]),
        ProvenanceRecord(
            study="lowvol-002",
            trial_id=None,
            ledger_path="research/lowvol-002/h0003-sample-check.json",
            trial_record_hash=None,
            registration_path=h0003_path,
            preregistration_fingerprint=h0003_registration["spec_fingerprint"],
        ),
        _provenance(trials["T0004"]),
        _provenance(trials["T0005"]),
        _provenance(trials["T0007"]),
        _provenance(trials["T0010"]),
        _provenance(trials["T0009"]),
        _provenance(trials["T0011"]),
        _provenance(trials["T0012"]),
        _provenance(trials["T0013"]),
        _provenance(trials["T0015"]),
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
    if edge.test_type is EdgeTestType.EVENT_STUDY:
        if "lagged" in edge.condition:
            return "FOMC event window (lagged)"
        return "FOMC event window"
    if edge.test_type is EdgeTestType.CROSS_SECTION:
        return "FOMC cross-event"
    if edge.test_type is EdgeTestType.MEAN_COMPARISON:
        if "macro" in edge.condition:
            return "macro window (mean |r|)"
        return "expiry window (mean |r|)"
    if "cpi step" in edge.condition.lower():
        if "release-day subsample" in edge.condition:
            return "CPI step (release-day)"
        return "CPI step"
    if "macro" in edge.condition:
        if "interaction" in edge.condition:
            return "macro-window interaction"
        if "subsample" in edge.condition:
            return "macro-window subsample"
        return "macro window"
    if "expiry" in edge.condition:
        if "interaction" in edge.condition:
            return "expiry-window interaction"
        if "subsample" in edge.condition:
            return "expiry-window subsample"
        return "expiry window"
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
    n_studies = len(
        {
            entry.study
            for entry in registry.provenance
            if entry.trial_id is not None
        }
    )
    n_tested = summary["edges_rejected"] + summary["edges_supported"]
    n_mean = sum(
        1
        for edge in registry.edges
        if edge.test_type is EdgeTestType.MEAN_COMPARISON
        and edge.status in {EdgeStatus.SUPPORTED, EdgeStatus.REJECTED}
    )
    n_event = sum(
        1
        for edge in registry.edges
        if edge.test_type is EdgeTestType.EVENT_STUDY
        and edge.status in {EdgeStatus.SUPPORTED, EdgeStatus.REJECTED}
    )
    n_cross = sum(
        1
        for edge in registry.edges
        if edge.test_type is EdgeTestType.CROSS_SECTION
        and edge.status in {EdgeStatus.SUPPORTED, EdgeStatus.REJECTED}
    )
    if summary["edges_supported"] == 0:
        null_sentence = (
            f"**Every tested edge so far is a null.** All {n_tested} "
            f"family tests across {n_studies} studies failed to reject: "
            "no lag-1 transmission was found in any tested configuration"
        )
        if n_mean:
            plural = "comparisons were" if n_mean > 1 else "comparison was"
            null_sentence += (
                f", and the {n_mean} expiry-window volatility-level "
                f"{plural} null too"
            )
        if n_event:
            null_sentence += (
                f", and the {n_event} FOMC event-window CAR tests "
                "were null too"
            )
        if n_cross:
            null_sentence += (
                f", and the {n_cross} cross-event slope tests "
                "were null too"
            )
        null_sentence += (
            ". That is the graph's most important information right now "
            "— it records where effects were looked for and not found, "
            "which is what stops the next study from re-testing the "
            "same edges."
        )
    else:
        null_sentence = (
            f"**{summary['edges_supported']} of {n_tested} tested edges "
            "rejected their null.** The supported edges are the graph's "
            "live findings; every other tested edge is a null that stops "
            "the next study from re-testing the same configuration."
        )
    lines.append(null_sentence)
    lines.append("")
    lines.append("### Edges")
    lines.append("")
    lines.append(
        "| Edge | Source → Target | Freq | Type | Condition | Hypothesis / trial "
        "| Coef | Holm p | Partial R² | Holdout OOS R² | Status |"
    )
    lines.append(
        "| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |"
    )
    labels = {node.instrument_id: node.short_label for node in registry.nodes}
    type_labels = {
        EdgeTestType.LEAD_LAG: "lead-lag",
        EdgeTestType.MEAN_COMPARISON: "mean-comp",
        EdgeTestType.EVENT_STUDY: "event-study",
        EdgeTestType.CROSS_SECTION: "cross-sect",
    }
    for edge in registry.edges:
        pair = f"{labels[edge.source_instrument]} → {labels[edge.target_instrument]}"
        trial = edge.trial_id or "—"
        type_label = type_labels[edge.test_type]
        lines.append(
            f"| {edge.edge_id} | {pair} | {edge.frequency} | {type_label} | "
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
        "Holm-adjusted p-value (tested edges) and status. "
        "Mean-comparison and event-study edges are self-loops labelled "
        "with the mean difference and the mean CAR respectively; they "
        "are within-instrument level tests, not transmission claims. "
        "Cross-section edges are directed but contemporaneous (both "
        "CARs over the same event window), not lead-lag claims."
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
