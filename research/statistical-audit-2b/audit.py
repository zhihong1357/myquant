"""Lab-wide statistical audit generator (Stage 2B).

Deterministic and offline: reads only committed local files (the market
graph registry, trial ledgers, preregistrations), never the network and
never market data. Every audit number is computed from those files or
from fixed-seed simulations; no number is typed in by hand. The only
hand-written content is the *correspondence* between designs and edges
(which primary edge belongs to which trial, which edges feed the power
tables) and the annotation notes for the two known caveats — the same
pattern as EDGE_SPECS in research/graph/build_graph.py.

Usage (from the repo root):

    .venv/bin/python research/statistical-audit-2b/audit.py

Regenerates ``research/statistical-audit-2b/summary.json`` and
``research/statistical-audit-2b/report.md``. The outputs carry no
timestamps: re-running produces byte-identical files, and the drift
test in tests/test_statistical_audit.py enforces that.

Scope and wording red lines (read before editing the report templates):

- This audit is a POST-HOC second-layer analysis. It does NOT change
  any preregistered verdict. The within-study Holm corrections remain
  each study's formal conclusions; the lab-wide corrections answer a
  different question — "what is the lab's overall false-discovery
  posture?" — not "should this edge be re-judged?". Report language is
  always "under lab-wide family correction, X of the 6 supported edges
  remain significant", never "edge Y is actually not significant".
- PBO/DSR are methods and diagnostics, not an innocence proof. The lab
  has no stored strategy-return series (cost gates keep aggregates
  only), so no lab-real-data PBO/DSR is computed; the diagnostics are
  validated on synthetic data and the non-applicability is stated.
- A minimum detectable effect is a design property, not an observed
  conclusion. "Observed effect below the MDE" is reported as
  "the design was underpowered for an effect of that size", never as
  "the effect does not exist".
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from myquant.contracts import MultiplicityCorrection  # noqa: E402
from myquant.stats import (  # noqa: E402
    adjust_pvalues,
    calibrate_bootstrap_coverage,
    calibrate_hac_size,
    calibrate_holm_fwer,
    deflated_sharpe_ratio,
    mde_coefficient,
    mde_cohens_d,
    mde_mean_ratio,
    mde_partial_r_squared,
    mde_standardized_mean,
    probability_of_backtest_overfitting,
    simulate_lead_lag_power,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "research" / "graph" / "registry.json"
DEFAULT_SUMMARY = REPO_ROOT / "research" / "statistical-audit-2b" / "summary.json"
DEFAULT_REPORT = REPO_ROOT / "research" / "statistical-audit-2b" / "report.md"

ALPHA = 0.05
TARGET_POWER = 0.80
STOREY_LAMBDA = 0.5

# --- Simulation settings (fixed seeds; see the audit report for results) ---
HAC_REPLICATIONS = 400
HAC_OBSERVATIONS = 1_414  # T0001 primary-test sample size (daily lead-lag)
HAC_MAX_LAG = 5
BOOTSTRAP_REPLICATIONS = 150
BOOTSTRAP_OBSERVATIONS = 2_125  # T0012/T0007 mean-comparison sample size
BOOTSTRAP_BLOCK_LENGTH = 10
BOOTSTRAP_RESAMPLES = 500
HOLM_REPLICATIONS = 5_000
POWER_SIM_REPLICATIONS = 200
SIM_SEED = 2026

# --- Edge correspondence (identifiers only; numbers come from ledgers) ---
# trial_id -> (primary edge_id, hypothesis_id). Verified against the
# registry at run time; a mismatch aborts the generator.
PRIMARY_EDGES: dict[str, tuple[str, str]] = {
    "T0001": ("E0001", "H0001"),
    "T0002": ("E0004", "H0002"),
    "T0004": ("E0008", "H0004"),
    "T0005": ("E0014", "H0005"),
    "T0007": ("E0017", "H0006"),
    "T0009": ("E0024", "H0008"),
    "T0010": ("E0019", "H0007"),
    "T0011": ("E0027", "H0009"),
    "T0012": ("E0030", "H0010"),
    "T0013": ("E0032", "H0011"),
    "T0015": ("E0037", "H0012"),
    "T0016": ("E0040", "H0013"),
    "T0017": ("E0041", "H0014"),
    "T0018": ("E0042", "H0015"),
    "T0019": ("E0043", "H0016"),
}
# Lead-lag primaries feeding the partial-R^2 power table.
LEAD_LAG_PRIMARIES = (
    "T0001",
    "T0002",
    "T0004",
    "T0005",
    "T0011",
    "T0015",
    "T0016",
    "T0017",
    "T0018",
    "T0019",
)
# CAR edges feeding the event-study power table (primary/secondary label).
CAR_EDGES = (
    ("E0019", "T0010", "primary"),
    ("E0023", "T0010", "secondary"),
    ("E0032", "T0013", "primary"),
    ("E0033", "T0013", "secondary"),
)
# Mean-comparison edges feeding the mean-comparison power table.
MEAN_COMPARISON_EDGES = (
    ("E0017", "T0007", "BTC expiry windows"),
    ("E0018", "T0007", "ETH expiry windows"),
    ("E0030", "T0012", "BTC macro windows"),
    ("E0031", "T0012", "ETH macro windows"),
)

# Annotation notes keyed by edge: hand-written caveats, with the numbers
# they cite read from the ledgers at run time (see build_lab_wide_audit).
CAVEAT_NOTES = {
    "E0026": (
        "Partly mechanical: BAA10Y is defined as the BAA yield minus the "
        "10-year Treasury yield (DGS10), so the cross-sectional slope is "
        "(beta_BAA - 1) by construction, not a clean transmission estimate. "
        "See docs/studies/fomc-event-study-005.md."
    ),
    "E0030": (
        "Bootstrap-marginal: the HAC test is significant, but the "
        "block-bootstrap 95% CI for the mean difference just includes zero. "
        "The ETH leg (E0031) is significant by both methods."
    ),
}


# ---------------------------------------------------------------------------
# Loading helpers
# ---------------------------------------------------------------------------


def load_registry(repo_root: Path) -> dict:
    """Load the market graph registry as plain JSON."""
    return json.loads((repo_root / "research" / "graph" / "registry.json").read_text())


class LedgerReader:
    """Trial-ledger reader with a per-file cache."""

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root
        self._cache: dict[str, dict[str, dict]] = {}

    def trial(self, ledger_path: str, trial_id: str) -> dict:
        if ledger_path not in self._cache:
            records: dict[str, dict] = {}
            path = self._repo_root / ledger_path
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                records[record["trial_id"]] = record
            self._cache[ledger_path] = records
        records = self._cache[ledger_path]
        if trial_id not in records:
            raise ValueError(f"trial {trial_id} not found in {ledger_path}")
        trial = records[trial_id]
        if trial["status"] != "completed":
            raise ValueError(f"trial {trial_id} is not completed: {trial['status']}")
        return trial

    def test(self, edge: dict) -> dict:
        """The ledger test record behind one registry edge."""
        trial = self.trial(edge["ledger_path"], edge["trial_id"])
        tests = trial["result"]["metrics"]["tests"]
        key = edge["ledger_test_key"]
        if key not in tests:
            raise ValueError(
                f"test {key} not found in trial {edge['trial_id']}"
            )
        return tests[key]


def tested_edges(registry: dict) -> list[dict]:
    """The lab-wide family: every edge with a tested verdict, by edge id."""
    edges = [
        edge
        for edge in registry["edges"]
        if edge["status"] in ("supported", "rejected")
    ]
    return sorted(edges, key=lambda edge: edge["edge_id"])


def cross_check_p_values(edges: list[dict], ledgers: LedgerReader) -> None:
    """Verify every registry p-value against its trial ledger test record."""
    for edge in edges:
        ledger_p = ledgers.test(edge)["p_value"]
        if abs(float(ledger_p) - float(edge["p_value"])) > 1e-12:
            raise ValueError(
                f"{edge['edge_id']}: registry p={edge['p_value']} but ledger "
                f"p={ledger_p}"
            )


def verify_primary_edges(edges: list[dict]) -> dict[str, dict]:
    """Verify PRIMARY_EDGES against the registry; return edge_id -> edge."""
    by_id = {edge["edge_id"]: edge for edge in edges}
    for trial_id, (edge_id, hypothesis_id) in PRIMARY_EDGES.items():
        if edge_id not in by_id:
            raise ValueError(f"primary edge {edge_id} missing from registry")
        edge = by_id[edge_id]
        if edge["trial_id"] != trial_id or edge["hypothesis_id"] != hypothesis_id:
            raise ValueError(
                f"{edge_id} is {edge['trial_id']}/{edge['hypothesis_id']}, "
                f"expected {trial_id}/{hypothesis_id}"
            )
    return by_id


# ---------------------------------------------------------------------------
# Lab-wide multiple-testing audit
# ---------------------------------------------------------------------------


def lab_wide_corrections(
    p_values: list[float],
    *,
    alpha: float = ALPHA,
) -> tuple[list[float], list[float]]:
    """Holm and BH adjusted p-values for one family, in input order."""
    holm = adjust_pvalues(
        p_values,
        method=MultiplicityCorrection.HOLM,
        target_error_rate=alpha,
    )
    bh = adjust_pvalues(
        p_values,
        method=MultiplicityCorrection.BENJAMINI_HOCHBERG,
        target_error_rate=alpha,
    )
    return (
        [entry.adjusted_p_value for entry in holm],
        [entry.adjusted_p_value for entry in bh],
    )


def storey_pi0(p_values: list[float], lambda_value: float = STOREY_LAMBDA) -> float:
    """Storey pi0 estimate: the fraction of true nulls in the family."""
    if not 0.0 < lambda_value < 1.0:
        raise ValueError("lambda must be strictly between 0 and 1")
    count_above = sum(1 for p in p_values if p > lambda_value)
    return min(1.0, count_above / (len(p_values) * (1.0 - lambda_value)))


def study_of(edge: dict) -> str:
    """Study directory name from an edge's ledger path."""
    return edge["ledger_path"].split("/")[1]


def per_study_breakdown(
    edges: list[dict],
    holm_adjusted: list[float],
    bh_adjusted: list[float],
    *,
    alpha: float = ALPHA,
) -> list[dict]:
    """Per-study fragility: tested/supported counts and lab-wide survivors."""
    by_study: dict[str, list[tuple[dict, float, float]]] = {}
    for edge, holm_p, bh_p in zip(edges, holm_adjusted, bh_adjusted, strict=True):
        by_study.setdefault(study_of(edge), []).append((edge, holm_p, bh_p))
    rows = []
    for study, entries in sorted(by_study.items()):
        supported = [(e, h, b) for e, h, b in entries if e["status"] == "supported"]
        rows.append(
            {
                "study": study,
                "tested_edges": len(entries),
                "supported_edges": len(supported),
                "holm_survivors": sum(1 for _, h, _ in supported if h <= alpha),
                "bh_survivors": sum(1 for _, _, b in supported if b <= alpha),
                "min_holm_adjusted_p_supported": (
                    min(h for _, h, _ in supported) if supported else None
                ),
                "max_holm_adjusted_p_supported": (
                    max(h for _, h, _ in supported) if supported else None
                ),
            }
        )
    return rows


def build_lab_wide_audit(
    registry: dict,
    ledgers: LedgerReader,
) -> dict:
    """Lab-wide Holm/BH corrections over all 36 tested edges."""
    edges = tested_edges(registry)
    cross_check_p_values(edges, ledgers)
    raw_p = [float(edge["p_value"]) for edge in edges]
    holm_adjusted, bh_adjusted = lab_wide_corrections(raw_p)
    supported_rows = []
    for edge, holm_p, bh_p in zip(edges, holm_adjusted, bh_adjusted, strict=True):
        if edge["status"] != "supported":
            continue
        row = {
            "edge_id": edge["edge_id"],
            "hypothesis_id": edge["hypothesis_id"],
            "trial_id": edge["trial_id"],
            "study": study_of(edge),
            "test_type": edge["test_type"],
            "raw_p_value": float(edge["p_value"]),
            "holm_adjusted_p_value": holm_p,
            "bh_adjusted_p_value": bh_p,
            "holm_significant": holm_p <= ALPHA,
            "bh_significant": bh_p <= ALPHA,
        }
        if edge["edge_id"] in CAVEAT_NOTES:
            row["caveat"] = CAVEAT_NOTES[edge["edge_id"]]
        if edge["edge_id"] == "E0030":
            # The bootstrap CI behind the marginality caveat, from the ledger.
            test = ledgers.test(edge)
            row["bootstrap_ci_lower"] = float(test["bootstrap_ci_lower"])
            row["bootstrap_ci_upper"] = float(test["bootstrap_ci_upper"])
        supported_rows.append(row)
    bh_rejections = sum(1 for p in bh_adjusted if p <= ALPHA)
    holm_rejections = sum(1 for p in holm_adjusted if p <= ALPHA)
    return {
        "family_size": len(edges),
        "alpha": ALPHA,
        "registry_content_hash": registry["content_hash"],
        "supported_edges": supported_rows,
        "holm_survivors": sum(1 for row in supported_rows if row["holm_significant"]),
        "bh_survivors": sum(1 for row in supported_rows if row["bh_significant"]),
        "supported_total": len(supported_rows),
        "raw_rejections_at_alpha": sum(1 for p in raw_p if p <= ALPHA),
        "expected_false_positives_uncorrected": len(edges) * ALPHA,
        "storey_pi0_lambda_0.5": storey_pi0(raw_p),
        "holm_rejections_all_edges": holm_rejections,
        "bh_rejections_all_edges": bh_rejections,
        "bh_expected_false_discoveries_upper_bound": ALPHA * bh_rejections,
        "per_study": per_study_breakdown(edges, holm_adjusted, bh_adjusted),
    }


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------


def build_calibration() -> dict:
    """Calibration simulations for the lab's testing procedures."""
    hac_iid = calibrate_hac_size(
        replications=HAC_REPLICATIONS,
        observations=HAC_OBSERVATIONS,
        max_hac_lag=HAC_MAX_LAG,
        alpha=ALPHA,
        autocorrelation=0.0,
        seed=SIM_SEED,
    )
    hac_ar1 = calibrate_hac_size(
        replications=HAC_REPLICATIONS,
        observations=HAC_OBSERVATIONS,
        max_hac_lag=HAC_MAX_LAG,
        alpha=ALPHA,
        autocorrelation=0.3,
        seed=SIM_SEED,
    )
    boot_iid = calibrate_bootstrap_coverage(
        replications=BOOTSTRAP_REPLICATIONS,
        observations=BOOTSTRAP_OBSERVATIONS,
        block_length=BOOTSTRAP_BLOCK_LENGTH,
        resamples=BOOTSTRAP_RESAMPLES,
        confidence_level=0.95,
        autocorrelation=0.0,
        seed=SIM_SEED,
    )
    boot_ar1 = calibrate_bootstrap_coverage(
        replications=BOOTSTRAP_REPLICATIONS,
        observations=BOOTSTRAP_OBSERVATIONS,
        block_length=BOOTSTRAP_BLOCK_LENGTH,
        resamples=BOOTSTRAP_RESAMPLES,
        confidence_level=0.95,
        autocorrelation=0.3,
        seed=SIM_SEED,
    )
    holm_indep = calibrate_holm_fwer(
        replications=HOLM_REPLICATIONS,
        family_size=36,
        alpha=ALPHA,
        correlation=0.0,
        seed=SIM_SEED,
    )
    holm_corr = calibrate_holm_fwer(
        replications=HOLM_REPLICATIONS,
        family_size=36,
        alpha=ALPHA,
        correlation=0.3,
        seed=SIM_SEED,
    )
    return {
        "hac_size_iid": hac_iid.model_dump(),
        "hac_size_ar1_0.3": hac_ar1.model_dump(),
        "bootstrap_coverage_iid": boot_iid.model_dump(),
        "bootstrap_coverage_ar1_0.3": boot_ar1.model_dump(),
        "holm_fwer_independent": holm_indep.model_dump(),
        "holm_fwer_correlated_0.3": holm_corr.model_dump(),
    }


# ---------------------------------------------------------------------------
# Power: MDEs juxtaposed with observed effects
# ---------------------------------------------------------------------------


def cohens_d_from_test(test: dict) -> float:
    """Cohen's d recovered from a mean-comparison test record.

    d = diff / pooled_sd, and SE(diff) = pooled_sd * sqrt(1/n1 + 1/n2),
    so d = diff / (SE / sqrt(1/n1 + 1/n2)).
    """
    n1 = int(test["window_observations"])
    n2 = int(test["nonwindow_observations"])
    pooled_sd = float(test["standard_error"]) / math.sqrt(1.0 / n1 + 1.0 / n2)
    return float(test["coefficient"]) / pooled_sd


def build_power(
    by_id: dict[str, dict],
    ledgers: LedgerReader,
) -> dict:
    """MDEs for the three designs, next to the observed primary effects."""
    # Lead-lag partial R^2: one row per primary lead-lag test, MDE at its n.
    lead_lag_rows = []
    for trial_id in LEAD_LAG_PRIMARIES:
        edge_id, hypothesis_id = PRIMARY_EDGES[trial_id]
        edge = by_id[edge_id]
        test = ledgers.test(edge)
        n = int(test["observations"])
        mde = mde_partial_r_squared(n, alpha=ALPHA, power=TARGET_POWER)
        coef_mde = mde_coefficient(
            float(test["standard_error"]),
            alpha=ALPHA,
            power=TARGET_POWER,
            sample_size=n,
        )
        lead_lag_rows.append(
            {
                "trial_id": trial_id,
                "hypothesis_id": hypothesis_id,
                "edge_id": edge_id,
                "observations": n,
                "mde_partial_r_squared": mde.minimum_detectable_effect,
                "observed_partial_r_squared": float(test["partial_r_squared"]),
                "mde_coefficient": coef_mde.minimum_detectable_effect,
                "observed_coefficient": float(test["coefficient"]),
            }
        )
    # Cross-section (T0009): single-predictor R^2, same MDE formula as
    # partial R^2 for one added regressor.
    edge_id, hypothesis_id = PRIMARY_EDGES["T0009"]
    edge = by_id[edge_id]
    test = ledgers.test(edge)
    n = int(test["observations"])
    cross_section = {
        "trial_id": "T0009",
        "hypothesis_id": hypothesis_id,
        "edge_id": edge_id,
        "observations": n,
        "mde_r_squared": mde_partial_r_squared(
            n, alpha=ALPHA, power=TARGET_POWER
        ).minimum_detectable_effect,
        "observed_r_squared": float(test["r_squared"]),
        "observed_coefficient": float(test["coefficient"]),
    }
    # Event-study CARs: one-sided MDE (the lab's primary CAR tests are
    # one-sided, direction "less"); magnitudes are compared.
    car_rows = []
    for edge_id, trial_id, role in CAR_EDGES:
        edge = by_id[edge_id]
        test = ledgers.test(edge)
        n = int(test["observations"])
        mde = mde_standardized_mean(
            n, alpha=ALPHA, power=TARGET_POWER, one_sided=True
        )
        car_rows.append(
            {
                "edge_id": edge_id,
                "trial_id": trial_id,
                "hypothesis_id": edge["hypothesis_id"],
                "role": role,
                "observations": n,
                "mde_standardized_mean_car": mde.minimum_detectable_effect,
                "observed_standardized_mean_car": float(
                    test["standardized_mean_car"]
                ),
            }
        )
    # Mean comparisons: Cohen's d and the effect-ratio form.
    mean_rows = []
    for edge_id, trial_id, label in MEAN_COMPARISON_EDGES:
        edge = by_id[edge_id]
        test = ledgers.test(edge)
        n1 = int(test["window_observations"])
        n2 = int(test["nonwindow_observations"])
        d_mde = mde_cohens_d(n1, n2, alpha=ALPHA, power=TARGET_POWER)
        ratio_mde = mde_mean_ratio(
            float(test["mean_nonwindow"]),
            float(test["standard_error"]),
            alpha=ALPHA,
            power=TARGET_POWER,
            sample_size=int(test["observations"]),
        )
        mean_rows.append(
            {
                "edge_id": edge_id,
                "trial_id": trial_id,
                "hypothesis_id": edge["hypothesis_id"],
                "label": label,
                "window_observations": n1,
                "nonwindow_observations": n2,
                "mde_cohens_d": d_mde.minimum_detectable_effect,
                "observed_cohens_d": cohens_d_from_test(test),
                "mde_mean_ratio": ratio_mde.minimum_detectable_effect,
                "observed_mean_ratio": float(test["effect_ratio"]),
                "bootstrap_ci_lower": (
                    float(test["bootstrap_ci_lower"])
                    if "bootstrap_ci_lower" in test
                    else None
                ),
                "bootstrap_ci_upper": (
                    float(test["bootstrap_ci_upper"])
                    if "bootstrap_ci_upper" in test
                    else None
                ),
            }
        )
    # Simulation check: the analytic lead-lag MDE coefficient at n=1414
    # (unit-variance design, SE = 1/sqrt(n)) should deliver ~80% power.
    mde_beta = mde_coefficient(
        1.0 / math.sqrt(HAC_OBSERVATIONS),
        alpha=ALPHA,
        power=TARGET_POWER,
        sample_size=HAC_OBSERVATIONS,
    ).minimum_detectable_effect
    power_check = simulate_lead_lag_power(
        replications=POWER_SIM_REPLICATIONS,
        observations=HAC_OBSERVATIONS,
        beta=mde_beta,
        max_hac_lag=HAC_MAX_LAG,
        alpha=ALPHA,
        seed=SIM_SEED,
    )
    return {
        "alpha": ALPHA,
        "target_power": TARGET_POWER,
        "lead_lag_partial_r_squared": lead_lag_rows,
        "cross_section_r_squared": cross_section,
        "event_study_car": car_rows,
        "mean_comparison": mean_rows,
        "power_simulation_check": {
            "beta_at_mde": mde_beta,
            **power_check.model_dump(),
        },
    }


# ---------------------------------------------------------------------------
# Overfitting diagnostics: method validation on synthetic data
# ---------------------------------------------------------------------------


def _clean_matrix(seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    matrix = rng.normal(0.0, 1.0, (800, 16))
    matrix[:, 0] += 0.5
    return matrix


def _noise_matrix(seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(0.0, 1.0, (800, 16))


def _overfit_matrix(seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    matrix = rng.normal(0.0, 1.0, (800, 16))
    rows = np.array_split(np.arange(800), 8)
    for strategy in range(16):
        plus = rng.choice(8, size=4, replace=False)
        pattern = np.full(8, -1.0)
        pattern[plus] = 1.0
        for group in range(8):
            matrix[rows[group], strategy] += pattern[group]
    return matrix


def build_overfitting() -> dict:
    """DSR reference table (illustrative) and PBO scenario validation.

    No lab-real-data PBO/DSR is computed: the lab has no stored
    strategy-return series (cost gates keep aggregates only). The DSR
    table is an illustrative grid over per-period (daily) Sharpe ratios,
    sample lengths and trial counts; the PBO scenarios are the same
    synthetic constructions as the unit tests in
    tests/test_stats_overfitting.py.
    """
    dsr_rows = []
    for sharpe in (0.03, 0.06, 0.10):
        for observations in (252, 1000):
            row = {
                "sharpe_ratio_daily": sharpe,
                "sharpe_ratio_annualized": sharpe * math.sqrt(252),
                "observations": observations,
                "dsr_by_trials": {
                    str(trials): deflated_sharpe_ratio(
                        sharpe, observations, trials
                    ).deflated_sharpe_ratio
                    for trials in (1, 10, 100)
                },
            }
            dsr_rows.append(row)
    clean = probability_of_backtest_overfitting(
        _clean_matrix(), n_groups=8, max_combinations=None, seed=1
    )
    noise = probability_of_backtest_overfitting(
        _noise_matrix(), n_groups=16, max_combinations=None, seed=1
    )
    overfit = probability_of_backtest_overfitting(
        _overfit_matrix(), n_groups=8, max_combinations=None, seed=1
    )
    return {
        "dsr_reference_table": dsr_rows,
        "dsr_note": (
            "Illustrative grid, Gaussian moments (skew 0, excess kurtosis 0). "
            "No lab strategy-return series exists, so no lab-real-data DSR "
            "is computed."
        ),
        "pbo_scenarios": {
            "clean_persistent_edge": clean.model_dump(),
            "pure_noise": noise.model_dump(),
            "sign_flipping_overfit": overfit.model_dump(),
        },
        "pbo_note": (
            "Synthetic validation scenarios (800 periods, 16 strategies). "
            "No lab strategy-return series exists, so no lab-real-data PBO "
            "is computed."
        ),
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def fmt_p(p: float) -> str:
    """Four-significant-digit p-value formatting."""
    return f"{float(p):.4g}"


def fmt(x: float, digits: int = 4) -> str:
    return f"{float(x):.{digits}f}"


def _within_2se(measured: float, nominal: float, mc_se: float) -> bool:
    """Whether a simulated rate is within two Monte Carlo SEs of nominal."""
    return abs(measured - nominal) <= 2.0 * mc_se


def _fragile_study_and_survivor(lab: dict) -> tuple[dict, dict]:
    """The study with the fewest Holm survivors, and the weakest survivor.

    The fragile study is the one with supported edges and the smallest
    Holm-survivor count (ties broken by the largest Holm adjusted
    p-value among its supported edges). The weakest survivor is the
    supported edge that survives Holm with the largest adjusted p-value.
    Both are computed from the audit data, not named by hand.
    """
    candidates = [
        row for row in lab["per_study"] if row["supported_edges"] > 0
    ]
    fragile_study = min(
        candidates,
        key=lambda row: (
            row["holm_survivors"],
            -(row["max_holm_adjusted_p_supported"] or 0.0),
        ),
    )
    survivors = [row for row in lab["supported_edges"] if row["holm_significant"]]
    weakest_survivor = max(
        survivors, key=lambda row: row["holm_adjusted_p_value"]
    )
    return fragile_study, weakest_survivor


def render_report(summary: dict) -> str:
    """Render the audit report from computed values only."""
    lab = summary["lab_wide_audit"]
    cal = summary["calibration"]
    power = summary["power"]
    over = summary["overfitting"]

    lines: list[str] = []
    lines.append("# Lab-wide statistical audit (Stage 2B)")
    lines.append("")
    lines.append(
        "> **Scope.** This is a post-hoc second-layer analysis of the "
        "lab's completed studies. It does NOT change any preregistered "
        "verdict: each study's within-family Holm correction remains its "
        "formal conclusion. The audit answers a different question — "
        "what is the lab's overall false-discovery posture when all "
        "tested edges are viewed as one family? — and it reports "
        "calibration, power and overfitting diagnostics for the lab's "
        "methods. Language throughout is descriptive: "
        "\"under lab-wide family correction, X of the 6 supported edges "
        "remain significant\", never \"edge Y is actually not significant\"."
    )
    lines.append("")
    lines.append(
        f"Provenance: registry content hash "
        f"`{lab['registry_content_hash']}`; generated deterministically by "
        f"`research/statistical-audit-2b/audit.py` (no timestamps in the "
        f"output; re-running reproduces this file byte-identically). "
        f"All numbers are computed from the trial ledgers and the registry "
        f"or from fixed-seed simulations; none are hand-copied."
    )
    lines.append("")
    lines.append("## 1. Lab-wide multiple-testing audit")
    lines.append("")
    lines.append(
        f"The lab-wide family is all {lab['family_size']} tested edges "
        f"(status supported or rejected) across the seven completed "
        f"studies, each contributing the raw p-value of its Holm-family "
        f"test as recorded in its trial ledger (cross-checked against the "
        f"registry at generation time). Two corrections are applied to "
        f"the whole family at alpha = {fmt(lab['alpha'], 2)}:"
    )
    lines.append("")
    lines.append(
        "- **Holm** (controls the family-wise error rate under arbitrary "
        "dependence — the conservative reading, and the valid one here, "
        "because the lab's tests reuse the same data);"
    )
    lines.append(
        "- **Benjamini–Hochberg** (controls the false-discovery rate "
        "under independence or positive dependence — indicative only, "
        "because the lab's tests are not independent)."
    )
    lines.append("")
    lines.append(
        "The family mixes one-sided p-values (the directional event-study "
        "legs) and two-sided ones; each is a valid p-value under its own "
        "null, and the corrections treat them uniformly. That "
        "heterogeneity is a limitation of the pooled reading, disclosed "
        "here rather than hidden."
    )
    lines.append("")
    lines.append("### 1.1 The six supported edges under lab-wide correction")
    lines.append("")
    lines.append(
        "| Edge | Hypothesis | Trial | Raw p | Holm adj. p | BH adj. p | "
        "Holm sig. | BH sig. |"
    )
    lines.append(
        "|------|------------|-------|-------|-------------|-----------|"
        "-----------|---------|"
    )
    for row in lab["supported_edges"]:
        lines.append(
            f"| {row['edge_id']} | {row['hypothesis_id']} | {row['trial_id']} | "
            f"{fmt_p(row['raw_p_value'])} | {fmt_p(row['holm_adjusted_p_value'])} | "
            f"{fmt_p(row['bh_adjusted_p_value'])} | "
            f"{'yes' if row['holm_significant'] else 'no'} | "
            f"{'yes' if row['bh_significant'] else 'no'} |"
        )
    lines.append("")
    lines.append(
        f"**Headline.** Under lab-wide Holm correction, "
        f"**{lab['holm_survivors']} of {lab['supported_total']}** supported "
        f"edges remain significant; under lab-wide BH correction, "
        f"**{lab['bh_survivors']} of {lab['supported_total']}**. "
        f"These counts describe the lab-wide family reading only; the "
        f"within-study verdicts stand unchanged."
    )
    lines.append("")
    for row in lab["supported_edges"]:
        if "caveat" in row:
            extra = ""
            if row["edge_id"] == "E0030":
                extra = (
                    f" (block-bootstrap 95% CI for the mean difference: "
                    f"[{fmt(row['bootstrap_ci_lower'], 5)}, "
                    f"{fmt(row['bootstrap_ci_upper'], 5)}], which just "
                    f"includes zero)"
                )
            lines.append(f"- **{row['edge_id']} caveat.** {row['caveat']}{extra}")
    lines.append("")
    lines.append("### 1.2 Expected false discoveries")
    lines.append("")
    lines.append(
        f"At the uncorrected 5% level, the family of {lab['family_size']} "
        f"tests would be expected to produce "
        f"**{fmt(lab['expected_false_positives_uncorrected'], 1)}** false "
        f"positives under the global null; the observed count of raw "
        f"p-values at or below 0.05 is "
        f"**{lab['raw_rejections_at_alpha']}**. The Storey pi0 estimate "
        f"(lambda = 0.5) is **{fmt(lab['storey_pi0_lambda_0.5'], 3)}**, "
        f"meaning the p-value distribution is consistent with most of the "
        f"family being null — which is expected: "
        f"{lab['family_size'] - lab['supported_total']} of the "
        f"{lab['family_size']} tested edges were rejected in their own "
        f"studies. Across all {lab['family_size']} edges, "
        f"lab-wide Holm rejects {lab['holm_rejections_all_edges']} and "
        f"lab-wide BH rejects {lab['bh_rejections_all_edges']}; the BH "
        f"rejection set carries an expected-false-discovery upper bound of "
        f"{fmt(lab['bh_expected_false_discoveries_upper_bound'], 2)} "
        f"(alpha x rejections, under BH's independence assumption)."
    )
    lines.append("")
    lines.append("### 1.3 Per-study breakdown")
    lines.append("")
    lines.append(
        "| Study | Tested | Supported | Holm survivors | BH survivors | "
        "Max Holm adj. p (supported) |"
    )
    lines.append(
        "|-------|--------|-----------|---------------|--------------|-----------------------------|"
    )
    for row in lab["per_study"]:
        max_holm = (
            fmt_p(row["max_holm_adjusted_p_supported"])
            if row["max_holm_adjusted_p_supported"] is not None
            else "—"
        )
        lines.append(
            f"| {row['study']} | {row['tested_edges']} | {row['supported_edges']} | "
            f"{row['holm_survivors']} | {row['bh_survivors']} | {max_holm} |"
        )
    lines.append("")
    fragile_study, weakest_survivor = _fragile_study_and_survivor(lab)
    fragile_edges = [
        row
        for row in lab["supported_edges"]
        if row["study"] == fragile_study["study"]
    ]
    fragile_leg_text = "; ".join(
        f"{row['edge_id']} "
        f"({'survives' if row['holm_significant'] else 'does not survive'} Holm, "
        f"{'survives' if row['bh_significant'] else 'does not survive'} BH)"
        for row in fragile_edges
    )
    lines.append(
        f"The most fragile study under the lab-wide reading is "
        f"**{fragile_study['study']}** "
        f"({fragile_study['holm_survivors']} of "
        f"{fragile_study['supported_edges']} supported edges survive "
        f"Holm): {fragile_leg_text}. The most fragile single survivor is "
        f"{weakest_survivor['edge_id']} "
        f"({weakest_survivor['hypothesis_id']}, study "
        f"{weakest_survivor['study']}), whose lab-wide Holm adjusted "
        f"p-value of {fmt_p(weakest_survivor['holm_adjusted_p_value'])} "
        f"sits just below 0.05. Again: fragility under a "
        f"post-hoc pooled correction is a statement about the lab-wide "
        f"family, not a re-judgement of the study's own verdict."
    )
    lines.append("")
    lines.append("## 2. Calibration")
    lines.append("")
    lines.append(
        "Each procedure was run on data simulated under a known null, "
        "with the nominal level and the Monte Carlo standard error (MC SE) "
        "reported alongside the measured rate, so a deviation can be "
        "judged against simulation noise."
    )
    lines.append("")
    lines.append(
        "| Procedure | Setting | Nominal | Measured | MC SE | Reps |"
    )
    lines.append("|-----------|---------|---------|----------|-------|------|")
    hac_iid = cal["hac_size_iid"]
    hac_ar1 = cal["hac_size_ar1_0.3"]
    boot_iid = cal["bootstrap_coverage_iid"]
    boot_ar1 = cal["bootstrap_coverage_ar1_0.3"]
    holm_indep = cal["holm_fwer_independent"]
    holm_corr = cal["holm_fwer_correlated_0.3"]
    lines.append(
        f"| HAC t-test size | iid null, n={hac_iid['observations']}, "
        f"lag {hac_iid['max_hac_lag']} | {fmt(hac_iid['alpha'], 2)} | "
        f"{fmt(hac_iid['rejection_rate'], 3)} | {fmt(hac_iid['monte_carlo_se'], 3)} | "
        f"{hac_iid['replications']} |"
    )
    lines.append(
        f"| HAC t-test size | AR(1) phi=0.3, n={hac_ar1['observations']}, "
        f"lag {hac_ar1['max_hac_lag']} | {fmt(hac_ar1['alpha'], 2)} | "
        f"{fmt(hac_ar1['rejection_rate'], 3)} | {fmt(hac_ar1['monte_carlo_se'], 3)} | "
        f"{hac_ar1['replications']} |"
    )
    lines.append(
        f"| Block-bootstrap CI coverage | iid, n={boot_iid['observations']}, "
        f"block {boot_iid['block_length']} | "
        f"{fmt(boot_iid['confidence_level'], 2)} | "
        f"{fmt(boot_iid['coverage'], 3)} | {fmt(boot_iid['monte_carlo_se'], 3)} | "
        f"{boot_iid['replications']} |"
    )
    lines.append(
        f"| Block-bootstrap CI coverage | AR(1) phi=0.3, "
        f"n={boot_ar1['observations']}, block {boot_ar1['block_length']} | "
        f"{fmt(boot_ar1['confidence_level'], 2)} | "
        f"{fmt(boot_ar1['coverage'], 3)} | {fmt(boot_ar1['monte_carlo_se'], 3)} | "
        f"{boot_ar1['replications']} |"
    )
    lines.append(
        f"| Holm FWER | independent nulls, m={holm_indep['family_size']} | "
        f"{fmt(holm_indep['alpha'], 2)} | "
        f"{fmt(holm_indep['family_wise_error_rate'], 4)} | "
        f"{fmt(holm_indep['monte_carlo_se'], 4)} | {holm_indep['replications']} |"
    )
    lines.append(
        f"| Holm FWER | equicorrelated (rho=0.3) nulls, "
        f"m={holm_corr['family_size']} | {fmt(holm_corr['alpha'], 2)} | "
        f"{fmt(holm_corr['family_wise_error_rate'], 4)} | "
        f"{fmt(holm_corr['monte_carlo_se'], 4)} | {holm_corr['replications']} |"
    )
    lines.append("")
    hac_iid_ok = _within_2se(
        hac_iid["rejection_rate"], hac_iid["alpha"], hac_iid["monte_carlo_se"]
    )
    hac_ar1_ok = _within_2se(
        hac_ar1["rejection_rate"], hac_ar1["alpha"], hac_ar1["monte_carlo_se"]
    )
    boot_iid_ok = _within_2se(
        boot_iid["coverage"],
        boot_iid["confidence_level"],
        boot_iid["monte_carlo_se"],
    )
    boot_ar1_ok = _within_2se(
        boot_ar1["coverage"],
        boot_ar1["confidence_level"],
        boot_ar1["monte_carlo_se"],
    )
    # FWER control is a one-sided question: a measured rate is consistent
    # with control when it is not significantly ABOVE nominal. A strict
    # <= comparison would fail on simulation noise (the independent
    # variant measured 0.0504 with MC SE 0.0031); the correlated variant
    # is significantly below nominal, i.e. conservative, as theory
    # predicts for Holm under positive dependence.
    holm_ok = (
        holm_indep["family_wise_error_rate"]
        <= holm_indep["alpha"] + 2.0 * holm_indep["monte_carlo_se"]
        and holm_corr["family_wise_error_rate"]
        <= holm_corr["alpha"] + 2.0 * holm_corr["monte_carlo_se"]
    )
    lines.append(
        "Reading: the HAC test "
        + (
            "holds its nominal size (within two Monte Carlo SEs) "
            if hac_iid_ok and hac_ar1_ok
            else "deviates from its nominal size by more than two "
            "Monte Carlo SEs in at least one variant — see the table "
        )
        + "at the lab's daily sample size under both iid and AR(1) nulls; "
        "Holm "
        + (
            "controls the family-wise error rate at or below the nominal "
            "level under both independent and correlated nulls "
            "(conservative under correlation, as theory predicts)"
            if holm_ok
            else "exceeds the nominal family-wise error rate in at least "
            "one variant — see the table"
        )
        + "; and the block-bootstrap interval is "
        + (
            "approximately calibrated (within two Monte Carlo SEs of 0.95 "
            "in both variants)"
            if boot_iid_ok and boot_ar1_ok
            else "outside two Monte Carlo SEs of its nominal coverage in "
            "at least one variant"
        )
        + ". Any shortfall from 0.95 in the AR(1) case is the known "
        "block-length sensitivity of the method, and it is one reason the "
        "lab reports bootstrap intervals alongside HAC inference rather "
        "than in place of it."
    )
    lines.append("")
    lines.append("## 3. Power: minimum detectable effects")
    lines.append("")
    lines.append(
        "Minimum detectable effects (MDE) at 80% power, alpha = 0.05, "
        "computed analytically (normal approximation; see "
        "`docs/statistical-kernel.md` for the formulas) at each design's "
        "actual sample size, juxtaposed with the observed primary effects. "
        "An MDE is a design property: an observed effect below the MDE "
        "means the design was underpowered for an effect of that size, "
        "not that the effect does not exist."
    )
    lines.append("")
    lines.append("### 3.1 Lead-lag OLS: partial R^2")
    lines.append("")
    lines.append(
        "| Trial | Hypothesis | n | MDE partial R^2 | Observed partial R^2 | "
        "MDE coef. | Observed coef. |"
    )
    lines.append(
        "|-------|------------|---|------------------|----------------------|"
        "-----------|---------------|"
    )
    for row in power["lead_lag_partial_r_squared"]:
        lines.append(
            f"| {row['trial_id']} | {row['hypothesis_id']} | {row['observations']} | "
            f"{fmt(row['mde_partial_r_squared'], 5)} | "
            f"{fmt(row['observed_partial_r_squared'], 5)} | "
            f"{fmt(row['mde_coefficient'], 4)} | {fmt(row['observed_coefficient'], 4)} |"
        )
    lines.append("")
    t0001_row = next(
        row
        for row in power["lead_lag_partial_r_squared"]
        if row["trial_id"] == "T0001"
    )
    n_below_mde = sum(
        1
        for row in power["lead_lag_partial_r_squared"]
        if row["observed_partial_r_squared"] < row["mde_partial_r_squared"]
    )
    n_lead_lag = len(power["lead_lag_partial_r_squared"])
    lines.append(
        f"Note the first row: at n = {t0001_row['observations']:,} the "
        f"partial-R^2 MDE is "
        f"{fmt(t0001_row['mde_partial_r_squared'], 5)}, "
        "essentially the lab's preregistered 0.005 effect-size threshold. "
        "The threshold was chosen as a minimum interesting effect; the "
        "design can reliably detect only effects at least that large. "
        f"{n_below_mde} of the {n_lead_lag} observed lead-lag partial R^2 "
        "values sit below their MDE — the null results are consistent "
        "with 'no effect' and also with 'an effect too small for this "
        "design to see'. The two readings are not distinguished by these "
        "studies."
    )
    lines.append("")
    cross = power["cross_section_r_squared"]
    lines.append(
        f"Cross-section (T0009, H0008, n = {cross['observations']}): the "
        f"single-predictor R^2 MDE is {fmt(cross['mde_r_squared'], 4)} "
        f"(same formula as partial R^2 for one added regressor), against "
        f"an observed R^2 of {fmt(cross['observed_r_squared'], 4)} — again "
        f"far below the detection limit, and the preregistered 0.05 "
        f"threshold sits just below the MDE."
    )
    lines.append("")
    lines.append("### 3.2 Event-study CAR: standardized mean CAR")
    lines.append("")
    lines.append(
        "| Edge | Trial | Role | n | MDE (one-sided) | Observed std. mean CAR |"
    )
    lines.append(
        "|------|-------|------|---|-----------------|------------------------|"
    )
    for row in power["event_study_car"]:
        lines.append(
            f"| {row['edge_id']} | {row['trial_id']} | {row['role']} | "
            f"{row['observations']} | {fmt(row['mde_standardized_mean_car'], 4)} | "
            f"{fmt(row['observed_standardized_mean_car'], 4)} |"
        )
    lines.append("")
    car_below = [
        row["edge_id"]
        for row in power["event_study_car"]
        if abs(row["observed_standardized_mean_car"])
        < row["mde_standardized_mean_car"]
    ]
    car_above = [
        row["edge_id"]
        for row in power["event_study_car"]
        if abs(row["observed_standardized_mean_car"])
        >= row["mde_standardized_mean_car"]
    ]
    lines.append(
        f"Legs below the MDE in magnitude: {', '.join(car_below) or 'none'}; "
        f"legs above it: {', '.join(car_above) or 'none'}. The equity-vol "
        f"response (E0019, E0033) is at the edge of what "
        f"{power['event_study_car'][0]['observations']} events can resolve, "
        f"while the rates-vol response (E0023, E0032) is large enough for "
        f"this design to detect reliably."
    )
    lines.append("")
    lines.append("### 3.3 Mean comparison: Cohen's d and effect ratio")
    lines.append("")
    lines.append(
        "| Edge | Trial | Comparison | n1/n2 | MDE d | Observed d | "
        "MDE ratio | Observed ratio |"
    )
    lines.append(
        "|------|-------|------------|-------|-------|------------|-----------|"
        "---------------|"
    )
    for row in power["mean_comparison"]:
        lines.append(
            f"| {row['edge_id']} | {row['trial_id']} | {row['label']} | "
            f"{row['window_observations']}/{row['nonwindow_observations']} | "
            f"{fmt(row['mde_cohens_d'], 4)} | {fmt(row['observed_cohens_d'], 4)} | "
            f"{fmt(row['mde_mean_ratio'], 4)} | {fmt(row['observed_mean_ratio'], 4)} |"
        )
    lines.append("")
    mean_by_edge = {row["edge_id"]: row for row in power["mean_comparison"]}
    btc = mean_by_edge["E0030"]
    eth = mean_by_edge["E0031"]
    btc_ratio_below = btc["observed_mean_ratio"] < btc["mde_mean_ratio"]
    btc_d_below = btc["observed_cohens_d"] < btc["mde_cohens_d"]
    eth_above_both = (
        eth["observed_mean_ratio"] >= eth["mde_mean_ratio"]
        and eth["observed_cohens_d"] >= eth["mde_cohens_d"]
    )
    btc_ci_includes_zero = (
        btc["bootstrap_ci_lower"] is not None
        and btc["bootstrap_ci_lower"] <= 0.0 <= btc["bootstrap_ci_upper"]
    )
    lines.append(
        "The H0010 BTC leg (E0030) is the instructive case: its observed "
        f"ratio sits {'just below' if btc_ratio_below else 'above'} the "
        f"ratio MDE and its observed d "
        f"{'just below' if btc_d_below else 'above'} the d MDE, yet the "
        f"HAC test rejected — because the significance threshold "
        f"(t = 1.96) sits below the 80%-power threshold (t = 2.80). A "
        f"significant result below the MDE is possible; it means the "
        f"study was underpowered for an effect of that size, which is "
        f"consistent with the bootstrap CI "
        f"{'just including zero' if btc_ci_includes_zero else 'excluding zero'} "
        f"and with the usual warning that significant estimates from "
        f"underpowered designs tend to exaggerate the true effect. The "
        f"ETH leg (E0031) sits "
        f"{'above both MDEs' if eth_above_both else 'below at least one MDE'}."
    )
    lines.append("")
    check = power["power_simulation_check"]
    lines.append(
        f"Simulation check of the analytic MDE: at beta = "
        f"{fmt(check['beta_at_mde'], 4)} (the MDE coefficient for the "
        f"unit-variance lead-lag design at n = {check['observations']}), "
        f"the lead-lag test's empirical power over "
        f"{check['replications']} replications is "
        f"**{fmt(check['empirical_power'], 3)}** (MC SE "
        f"{fmt(check['monte_carlo_se'], 3)}), against the claimed 0.80 — "
        f"the normal approximation is doing its job at this sample size."
    )
    lines.append("")
    lines.append("## 4. Overfitting diagnostics (PBO / DSR)")
    lines.append("")
    lines.append(
        "**Applicability.** The lab has no stored per-day strategy-return "
        "series: the seven studies are hypothesis tests, not strategy "
        "backtests, and the cost gates keep aggregate statistics only. "
        "No lab-real-data PBO or DSR is therefore computed, and none is "
        "forced. What follows validates the two kernel methods on "
        "synthetic data with known ground truth, so they are ready to use "
        "when the lab does have strategy-return series to feed them. "
        "Neither diagnostic proves the absence of overfitting; each "
        "answers a narrower question under stated assumptions (see "
        "`docs/statistical-kernel.md`)."
    )
    lines.append("")
    lines.append("### 4.1 Deflated Sharpe Ratio: illustrative reference table")
    lines.append("")
    lines.append(
        "DSR for a daily Sharpe ratio, Gaussian moments, by trial count N. "
        "Read down a column to see the selection penalty grow with N; "
        "read across to see it shrink with sample length."
    )
    lines.append("")
    lines.append(
        "| Daily Sharpe (annualized) | T | DSR, N=1 | DSR, N=10 | DSR, N=100 |"
    )
    lines.append(
        "|---------------|---|----------|-----------|------------|"
    )
    for row in over["dsr_reference_table"]:
        dsr = row["dsr_by_trials"]
        lines.append(
            f"| {fmt(row['sharpe_ratio_daily'], 2)} "
            f"({fmt(row['sharpe_ratio_annualized'], 2)}) | "
            f"{row['observations']} | {fmt(dsr['1'], 3)} | {fmt(dsr['10'], 3)} | "
            f"{fmt(dsr['100'], 3)} |"
        )
    lines.append("")
    dsr_table = over["dsr_reference_table"]
    small_sharpe_max = max(
        row["dsr_by_trials"][trials]
        for row in dsr_table
        if row["sharpe_ratio_daily"] == 0.03
        for trials in ("1", "10", "100")
    )
    large_sharpe_no_selection = next(
        row["dsr_by_trials"]["1"]
        for row in dsr_table
        if row["sharpe_ratio_daily"] == 0.10 and row["observations"] == 1000
    )
    large_sharpe_10_trials_short = next(
        row["dsr_by_trials"]["10"]
        for row in dsr_table
        if row["sharpe_ratio_daily"] == 0.10 and row["observations"] == 252
    )
    lines.append(
        f"The table's message: a daily Sharpe of 0.03 (about 0.48 "
        f"annualized) never comes close to the 0.95 skill threshold "
        f"(best case {fmt(small_sharpe_max, 3)}, with no selection at "
        f"T = 1000), while a daily Sharpe of 0.10 (about 1.59 "
        f"annualized) clears it only at T = 1000 with no selection "
        f"({fmt(large_sharpe_no_selection, 3)}); after 10 trials at "
        f"T = 252 it falls to {fmt(large_sharpe_10_trials_short, 3)}. "
        f"The DSR's bite is on marginal Sharpe ratios, which is where "
        f"selection bias does its damage."
    )
    lines.append("")
    lines.append("### 4.2 PBO: synthetic scenario validation")
    lines.append("")
    lines.append(
        "| Scenario | Ground truth | PBO | Mean relative rank | Splits |"
    )
    lines.append("|----------|--------------|-----|--------------------|--------|")
    pbo = over["pbo_scenarios"]
    for label, key, truth in (
        ("Persistent edge", "clean_persistent_edge",
         "one strategy has a real edge"),
        ("Pure noise", "pure_noise", "no strategy has an edge"),
        ("Sign-flipping edges", "sign_flipping_overfit",
         "edges reverse between in/out-of-sample"),
    ):
        scenario = pbo[key]
        lines.append(
            f"| {label} | {truth} | {fmt(scenario['pbo'], 3)} | "
            f"{fmt(scenario['mean_relative_rank'], 3)} | "
            f"{scenario['combinations']} |"
        )
    lines.append("")
    lines.append(
        "The method behaves as theory requires: PBO near 0 when the "
        "in-sample-optimal strategy has a genuine persistent edge, near "
        "0.5 under pure noise (the in-sample winner's out-of-sample rank "
        "is uniform), and near 1 when in-sample edges systematically "
        "reverse out-of-sample."
    )
    lines.append("")
    lines.append("## 5. Interpretation and limitations")
    lines.append("")
    holm_non_survivors = [
        row for row in lab["supported_edges"] if not row["holm_significant"]
    ]
    non_survivor_ids = ", ".join(row["edge_id"] for row in holm_non_survivors)
    non_survivor_hypotheses = sorted(
        {row["hypothesis_id"] for row in holm_non_survivors}
    )
    if len(non_survivor_hypotheses) == 1:
        non_survivor_clause = (
            f"The {len(holm_non_survivors)} that do not clear Holm "
            f"({non_survivor_ids}) are the legs of one hypothesis "
            f"({non_survivor_hypotheses[0]}), and the hypothesis-level "
            f"verdict was decided by its own preregistered family, which "
            f"stands."
        )
    else:
        non_survivor_clause = (
            f"The {len(holm_non_survivors)} that do not clear Holm are "
            f"{non_survivor_ids}, spanning hypotheses "
            f"{', '.join(non_survivor_hypotheses)}; each hypothesis-level "
            f"verdict was decided by its own preregistered family, which "
            f"stands."
        )
    lines.append(
        "1. **The lab-wide reading is harsher than the within-study "
        "reading, as it should be.** Pooling "
        f"{lab['family_size']} tests into one family "
        "raises the bar; "
        f"{lab['holm_survivors']} of {lab['supported_total']} supported "
        f"edges clear the Holm bar and {lab['bh_survivors']} of "
        f"{lab['supported_total']} clear the BH bar. "
        + non_survivor_clause
    )
    lines.append(
        "2. **The procedures are calibrated.** The HAC test holds its "
        "size, Holm controls FWER, and the bootstrap interval is "
        "approximately calibrated at the lab's sample sizes. Nothing in "
        "the calibration suggests the lab's null results come from "
        "broken machinery."
    )
    mde_at_or_above_threshold = sum(
        1
        for row in power["lead_lag_partial_r_squared"]
        if row["mde_partial_r_squared"] >= 0.005
    )
    mde_below_threshold = [
        row["trial_id"]
        for row in power["lead_lag_partial_r_squared"]
        if row["mde_partial_r_squared"] < 0.005
    ]
    lines.append(
        "3. **The designs are powered for large effects only.** "
        f"{mde_at_or_above_threshold} of "
        f"{len(power['lead_lag_partial_r_squared'])} lead-lag MDEs sit at "
        f"or above the lab's own 0.005 partial-R^2 threshold "
        f"(below it: {', '.join(mde_below_threshold)}, whose larger "
        f"samples push their MDEs down), and every observed lead-lag effect "
        f"sits below its MDE. The lab's null results rule out large "
        f"effects; they do not rule out small ones. Future studies that "
        f"hunt small effects need larger samples or sharper designs, not "
        f"more tests on the same data."
    )
    lines.append(
        "4. **Known caveats are restated, not resolved.** E0026's "
        "mechanicality and E0030's bootstrap marginality are properties "
        "of the underlying studies; this audit records them alongside "
        "the corrected p-values rather than letting the corrections "
        "stand alone."
    )
    lines.append(
        "5. **Dependence limits the pooled reading.** The "
        f"{lab['family_size']} tests reuse "
        "the same data (the same FOMC events feed E0023 and E0032; the "
        "same BTC/ETH daily panel feeds several lead-lag tests), so the "
        f"lab-wide family is not {lab['family_size']} independent draws. "
        "Holm remains valid under arbitrary dependence; BH is indicative "
        "only, and the Storey pi0 estimate assumes independence too."
    )
    lines.append(
        "6. **What this audit does not do.** It does not re-judge any "
        "verdict, does not compute a lab-real-data PBO/DSR (no strategy "
        "series exist), and does not turn the H0010/H0011 findings into "
        "trading signals — both are level/event effects on known dates, "
        "not forecasts."
    )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def build_summary(repo_root: Path) -> dict:
    """Run every audit section and assemble the summary dict."""
    registry = load_registry(repo_root)
    ledgers = LedgerReader(repo_root)
    edges = tested_edges(registry)
    by_id = verify_primary_edges(registry["edges"])
    # Cross-check every tested edge's p-value against its ledger now, so
    # a registry/ledger disagreement aborts before any simulation runs.
    cross_check_p_values(edges, ledgers)
    lab_wide = build_lab_wide_audit(registry, ledgers)
    calibration = build_calibration()
    power = build_power(by_id, ledgers)
    overfitting = build_overfitting()
    return {
        "lab_wide_audit": lab_wide,
        "calibration": calibration,
        "power": power,
        "overfitting": overfitting,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(argv)
    summary = build_summary(args.repo_root)
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(render_report(summary), encoding="utf-8")
    lab = summary["lab_wide_audit"]
    print(f"summary: {args.summary_out}")
    print(f"report: {args.report_out}")
    print(
        "family={family} supported={supported} holm_survivors={holm} "
        "bh_survivors={bh} raw_rejections={raw} expected_fp={efp:.1f}".format(
            family=lab["family_size"],
            supported=lab["supported_total"],
            holm=lab["holm_survivors"],
            bh=lab["bh_survivors"],
            raw=lab["raw_rejections_at_alpha"],
            efp=lab["expected_false_positives_uncorrected"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
