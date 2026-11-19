"""Statistical decision-record builder (Stage 2B).

Generates one structured record per lab conclusion: a record for each
of the 6 SUPPORTED edges and a rejection record for each of the 15
rejected primary hypotheses. Records live in
``research/decision-records/records/`` as ``DR-<id>.json``.

Deterministic and offline: reads only committed local files (the
market graph registry, trial ledgers, the Stage 2B audit summary),
never the network and never market data. Every number in every record
is read programmatically from those files; the only hand-written
content is the correspondence (which edge/hypothesis each record
covers), the conclusion-scope sentences, and the qualitative
limitations — all verified against the registry/ledgers at run time,
and all numbers cross-checked by ``tests/test_decision_records.py``,
which re-reads each committed record against its trial ledger
independently of this builder.

Usage (from the repo root):

    .venv/bin/python research/decision-records/build_decision_records.py

Re-running reproduces all records byte-identically (no timestamps).
Requires ``research/statistical-audit-2b/summary.json`` to exist: the
lab-wide Holm/BH values and the power juxtaposition in each record's
``audit_notes`` come from the audit summary, so the audit generator
must run first (it already has, in Stage 2B).

Record schema (v1):

- identity: record_id, record_type, edge/hypothesis/trial ids,
  hypothesis version, preregistration fingerprint, ledger path and
  test key, trial record hash, study, report path;
- conclusion + conclusion_scope: what was decided, and the exact
  scope of the decision (a secondary supported edge does not make its
  hypothesis supported; a rejection is about the preregistered effect
  at the preregistered threshold, not a claim that no effect exists);
- evidence: the primary test record (type-specific fields), the full
  Holm family, the verdict criteria, holdout OOS values, the cost
  gate, the sample window, and (for supported edges) the lab-wide
  Holm/BH outcomes from the audit;
- limitations: qualitative design limits (no numbers — numbers live
  in evidence);
- audit_notes: the lab-wide reading and the power juxtaposition,
  computed from the audit summary.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "research" / "graph" / "registry.json"
AUDIT_SUMMARY_PATH = (
    REPO_ROOT / "research" / "statistical-audit-2b" / "summary.json"
)
DEFAULT_OUT_DIR = REPO_ROOT / "research" / "decision-records" / "records"

SCHEMA_VERSION = 1

# --- Correspondence (identifiers only; numbers come from ledgers) ---
# trial_id -> (primary edge_id, hypothesis_id). Verified against the
# registry at run time. (Same mapping as audit.py's PRIMARY_EDGES; both
# are verified against the registry, so a mismatch aborts loudly.)
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
    "T0020": ("E0044", "H0017"),
    "T0021": ("E0045", "H0018"),
}

# The 6 supported edges (from the registry) and the 15 rejected primary
# hypotheses (trial_id, hypothesis_id). Both lists are verified against
# the registry/ledgers at run time.
SUPPORTED_EDGE_IDS = ("E0023", "E0026", "E0030", "E0031", "E0032", "E0033")
REJECTED_HYPOTHESES = (
    ("T0001", "H0001"),
    ("T0002", "H0002"),
    ("T0004", "H0004"),
    ("T0005", "H0005"),
    ("T0007", "H0006"),
    ("T0010", "H0007"),
    ("T0009", "H0008"),
    ("T0011", "H0009"),
    ("T0015", "H0012"),
    ("T0016", "H0013"),
    ("T0017", "H0014"),
    ("T0018", "H0015"),
    ("T0019", "H0016"),
    ("T0020", "H0017"),
    ("T0021", "H0018"),
)

# Ledger test fields copied into evidence, per test type. Only fields
# present and non-None in the ledger record are copied.
TEST_FIELDS: dict[str, tuple[str, ...]] = {
    "lead_lag": (
        "coefficient",
        "standard_error",
        "t_statistic",
        "p_value",
        "partial_r_squared",
        "observations",
    ),
    "cross_section": (
        "coefficient",
        "standard_error",
        "t_statistic",
        "p_value",
        "r_squared",
        "observations",
    ),
    "event_study": (
        "coefficient",
        "standardized_mean_car",
        "standard_error",
        "t_statistic",
        "p_value",
        "observations",
        "direction",
    ),
    "mean_comparison": (
        "coefficient",
        "effect_ratio",
        "mean_window",
        "mean_nonwindow",
        "window_observations",
        "nonwindow_observations",
        "standard_error",
        "t_statistic",
        "p_value",
        "bootstrap_ci_lower",
        "bootstrap_ci_upper",
    ),
}

# Qualitative limitations per record (no numbers — numbers live in
# evidence). Keyed by record id.
LIMITATIONS: dict[str, tuple[str, ...]] = {
    "DR-E0023": (
        "TYVIX is Treasury-futures price volatility, not the MOVE "
        "yield-volatility index; the substitution is documented in the "
        "study report.",
        "The sample ends with the TYVIX series (see evidence.sample); "
        "the post-2020 hiking cycle is not covered.",
        "A significant CAR is an event response, not a tradable signal.",
    ),
    "DR-E0026": (
        "Partly mechanical by the definition of BAA10Y (see audit_notes): "
        "the slope is (beta_BAA - 1) by construction, not a clean "
        "transmission estimate.",
        "The hypothesis H0008 itself was REJECTED on its primary test; "
        "this edge is a secondary finding within the family.",
    ),
    "DR-E0030": (
        "A level effect on known event days, not a forecast or a trading "
        "signal; no surprise measure exists (release-day effect, not "
        "surprise effect).",
        "Bootstrap-marginal: the block-bootstrap interval just includes "
        "zero (see evidence and audit_notes).",
    ),
    "DR-E0031": (
        "A level effect on known event days, not a forecast or a trading "
        "signal; no surprise measure exists (release-day effect, not "
        "surprise effect).",
    ),
    "DR-E0032": (
        "The sample ends with the TYVIX series (see evidence.sample); "
        "the post-2020 hiking cycle is not covered.",
        "The FRED publication lag was verified for the present only and "
        "is assumed constant over the historical sample.",
        "A significant CAR is an event response, not a tradable signal.",
    ),
    "DR-E0033": (
        "The sample ends with the TYVIX series (see evidence.sample); "
        "the post-2020 hiking cycle is not covered.",
        "The FRED publication lag was verified for the present only and "
        "is assumed constant over the historical sample.",
        "The lagged VIX CAR is significant only because the lagged window "
        "excludes the day-+1 rebound (see the study report); the "
        "unlagged VIX CAR was not significant.",
    ),
    "DR-H0001": (
        "The primary test is daily frequency; the 1H robustness leg is "
        "also null (see evidence.family_tests).",
        "Same-day comovement is strong (see the study report "
        "descriptives); the rejection is about overnight carryover, not "
        "about same-day transmission.",
    ),
    "DR-H0002": (
        "The regime rule is trailing-volatility based; other regime "
        "definitions were not tested.",
        "The low-volatility subsample is a subset of the daily panel; "
        "power there is lower than in the full sample.",
    ),
    "DR-H0004": (
        "TYVIX substitutes for MOVE (price volatility vs yield "
        "volatility); the substitution is documented in the study report.",
        "The sample ends with the TYVIX series; the post-2020 hiking "
        "cycle is not covered.",
    ),
    "DR-H0005": (
        "The expiry window is a proxy for dealer-hedging intensity, not "
        "a measure of dealer gamma; no dealer-position data exists in "
        "the public sources used.",
        "The expiry calendar is rule-constructed (last Friday of month); "
        "a historical rule change cannot be ruled out from public data.",
    ),
    "DR-H0006": (
        "The point estimate is zero but the confidence interval is wide "
        "(see evidence); a moderate effect is not disproven, only "
        "unsupported by this sample.",
        "Same expiry-window proxy limitation as H0005.",
    ),
    "DR-H0007": (
        "DGS10 is a proxy for the policy surprise; no free "
        "fed-funds-futures surprise series exists.",
        "FRED publication lag was not modelled in this study; study 007 "
        "closed that limitation.",
    ),
    "DR-H0008": (
        "DGS10 is a proxy for the policy surprise; no free "
        "fed-funds-futures surprise series exists.",
        "Split-half replication failed: both halves have the wrong sign.",
    ),
    "DR-H0009": (
        "The union window mixes FOMC and CPI days, whose interactions "
        "have opposite signs (see the study report descriptives); the "
        "union primary is an exact zero by cancellation.",
        "Release-day effect, not surprise effect: no consensus data was "
        "used.",
    ),
    "DR-H0012": (
        "The CPI step changes only on release days, so the effective "
        "sample is much smaller than the daily row count.",
        "CPIAUCSL is current vintage, not as-released values; the "
        "release-day subsample is hypothesis-generating only.",
    ),
    "DR-H0013": (
        "The 2-trading-day BAA10Y publication lag was verified only at "
        "fetch time and is assumed constant over the historical sample; "
        "FRED's posting schedule may have changed over 2003-2026.",
        "FRED revisions are unmodelled; the trial uses the current "
        "vintage, not as-first-posted values.",
        "Same-day comovement is strong (see the study report "
        "descriptives); the rejection is about next-day carryover, not "
        "about same-day transmission.",
        "The reverse placebo (SPX->BAA10Y) is nominally significant but "
        "descriptive only, not in the test family.",
    ),
    "DR-H0014": (
        "TYVIX was discontinued in 2020-05; the sample is "
        "historical-only (2003-2020) and says nothing about the "
        "post-2020 regime.",
        "The 2-trading-day BAA10Y publication lag was verified only at "
        "fetch time and is assumed constant over the historical sample; "
        "FRED's posting schedule may have changed over 2003-2020.",
        "FRED revisions are unmodelled; the trial uses the current "
        "vintage, not as-first-posted values.",
        "Same-day comovement is positive (see the study report "
        "descriptives); the rejection is about next-day carryover, not "
        "about same-day transmission.",
        "The informational gross sign-rule edge is positive but "
        "descriptive only, on an untradable index, and not a verdict "
        "criterion.",
    ),
    "DR-H0015": (
        "The 2-trading-day BAA10Y publication lag was verified only at "
        "fetch time and is assumed constant over the historical sample; "
        "FRED's posting schedule may have changed over 2003-2026.",
        "FRED revisions are unmodelled; the trial uses the current "
        "vintage, not as-first-posted values.",
        "Same-day comovement is positive (see the study report "
        "descriptives); the rejection is about next-day carryover, not "
        "about same-day transmission.",
        "The informational gross sign-rule edge is positive but its "
        "confidence interval includes zero; it is descriptive only, on "
        "an untradable index, and not a verdict criterion.",
    ),
    "DR-H0016": (
        "The 2-trading-day BAA10Y publication lag was verified only at "
        "fetch time and is assumed constant over the historical sample; "
        "FRED's posting schedule may have changed over 2003-2026.",
        "FRED revisions are unmodelled; the trial uses the current "
        "vintage, not as-first-posted values.",
        "Same-day comovement is positive (see the study report "
        "descriptives); the rejection is about next-day carryover, not "
        "about same-day transmission.",
        "The informational gross sign-rule edge is positive but its "
        "confidence interval includes zero; it is descriptive only, on "
        "an untradable index, and not a verdict criterion.",
        "The holdout out-of-sample incremental R-squared passes its "
        "criterion by a hair (+0.000024, an MSE difference of 9.7e-08); "
        "the verdict rests on the two decisive criteria, which fail by "
        "orders of magnitude.",
    ),
    "DR-H0017": (
        "The 2-trading-day BAA10Y publication lag was verified only at "
        "fetch time and is assumed constant over the historical sample; "
        "FRED's posting schedule may have changed over 2003-2026.",
        "FRED revisions are unmodelled; the trial uses the current "
        "vintage, not as-first-posted values.",
        "BAA10Y contains minus DGS10 by definition, so the predictor "
        "contains the target's own lag-2 change and the same-day "
        "correlation (-0.3863) is mechanical, not evidence of "
        "transmission; the baseline's lag-2 guard blocks the channel "
        "and the rejection is of the guarded test.",
        "The informational gross sign-rule edge is negative and its "
        "confidence interval includes zero; it is descriptive only, on "
        "a non-tradable yield, and not a verdict criterion.",
        "The reverse placebo is nominally significant (p=0.0194) but "
        "descriptive only, below the 0.005 threshold, and itself "
        "mechanically confounded (its target contains minus DGS10).",
    ),
    "DR-H0018": (
        "The daily DVOL value is the 16:00 UTC snapshot (close of the "
        "hourly DVOL row timestamped 15:00 UTC); a different snapshot "
        "time would give a different panel, and this study's numbers "
        "speak only to the preregistered convention.",
        "Same-day comovement is strongly negative (-0.2691: the "
        "leverage effect is contemporaneous); the rejection is about "
        "next-day carryover, not about same-day transmission.",
        "The informational gross sign-rule edge is positive but its "
        "confidence interval includes zero; it is descriptive only, on "
        "an untradable index, and not a verdict criterion.",
        "The reverse placebo is nominally significant (p=0.0317) but "
        "descriptive only, below the 0.005 threshold and the MDE.",
        "The amplitude check (|BTC return| -> next-day DVOL change) "
        "is nominally significant (p=6.6e-06, partial R-squared "
        "0.00993) but was preregistered as descriptive only, has the "
        "opposite sign to the naive amplitude story, and is "
        "consistent with DVOL level mean-reversion; it was not "
        "promoted and enters no verdict.",
        "The sample (n=2065) gives an MDE of 0.003787, nearly 3x the "
        "BAA10Y studies' MDE; the null rules out effects at or above "
        "that bound, not smaller ones.",
    ),
}


# ---------------------------------------------------------------------------
# Loading helpers
# ---------------------------------------------------------------------------


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


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


def study_of(edge: dict) -> str:
    return edge["ledger_path"].split("/")[1]


# ---------------------------------------------------------------------------
# Evidence extraction
# ---------------------------------------------------------------------------


def extract_test_evidence(
    trial: dict,
    edge: dict,
    holm_by_test: dict[str, dict],
) -> dict:
    """The evidence block for one edge's ledger test record."""
    test_key = edge["ledger_test_key"]
    tests = trial["result"]["metrics"]["tests"]
    if test_key not in tests:
        raise ValueError(f"test {test_key} not found in trial {edge['trial_id']}")
    test = tests[test_key]
    fields = TEST_FIELDS[edge["test_type"]]
    evidence: dict = {
        "test_key": test_key,
        "test_type": edge["test_type"],
    }
    for field in fields:
        if field in test and test[field] is not None:
            evidence[field] = test[field]
    # Within-study Holm adjusted p from the ledger's holm list,
    # cross-checked against the registry edge value.
    if test_key not in holm_by_test:
        raise ValueError(
            f"test {test_key} has no Holm entry in trial {edge['trial_id']}"
        )
    ledger_holm = float(holm_by_test[test_key]["adjusted_p_value"])
    registry_holm = float(edge["holm_adjusted_p_value"])
    if abs(ledger_holm - registry_holm) > 1e-12:
        raise ValueError(
            f"{edge['edge_id']}: ledger Holm {ledger_holm} != registry "
            f"Holm {registry_holm}"
        )
    evidence["within_study_holm_adjusted_p_value"] = ledger_holm
    evidence["within_study_holm_reject"] = bool(holm_by_test[test_key]["reject"])
    return evidence


def family_tests_evidence(
    trial: dict,
    edges_by_test_key: dict[str, dict],
) -> list[dict]:
    """Every Holm-family test of the trial, with its edge id."""
    holm = trial["result"]["metrics"]["holm"]
    rows = []
    for entry in holm:
        test_key = entry["test"]
        if test_key not in edges_by_test_key:
            raise ValueError(
                f"family test {test_key} of trial {trial['trial_id']} "
                "has no registry edge"
            )
        rows.append(
            {
                "edge_id": edges_by_test_key[test_key]["edge_id"],
                "test_key": test_key,
                "raw_p_value": float(entry["raw_p_value"]),
                "holm_adjusted_p_value": float(entry["adjusted_p_value"]),
                "reject": bool(entry["reject"]),
            }
        )
    return sorted(rows, key=lambda row: row["edge_id"])


def holdout_evidence(trial: dict) -> dict | None:
    """Holdout OOS values from the trial's walk-forward section."""
    walk_forward = trial["result"]["metrics"].get("walk_forward")
    if not walk_forward:
        return None
    values = {
        key: value
        for key, value in walk_forward.items()
        if "oos" in key and not isinstance(value, list)
    }
    return values or None


def cost_gate_evidence(trial: dict) -> dict | None:
    """Cost-gate block from the trial metrics, if the trial has one."""
    metrics = trial["result"]["metrics"]
    for key in ("cost_gate", "cost_gate_informational"):
        if key in metrics:
            return {"kind": key, **metrics[key]}
    return None


# ---------------------------------------------------------------------------
# Audit notes (computed from the Stage 2B audit summary)
# ---------------------------------------------------------------------------


def lab_wide_note(audit_row: dict, family_size: int) -> str:
    """Lab-wide reading for one supported edge, from the audit summary."""
    return (
        f"Lab-wide family correction ({family_size} tested edges): Holm adjusted p "
        f"{audit_row['holm_adjusted_p_value']:.4g} "
        f"({'significant' if audit_row['holm_significant'] else 'not significant'}), "
        f"BH adjusted p {audit_row['bh_adjusted_p_value']:.4g} "
        f"({'significant' if audit_row['bh_significant'] else 'not significant'}). "
        f"This is a post-hoc second-layer reading; it does not change the "
        f"within-study verdict."
    )


def power_note_for_edge(audit_summary: dict, edge_id: str) -> str | None:
    """Power juxtaposition for one edge, from the audit summary's tables."""
    power = audit_summary["power"]
    for row in power["event_study_car"]:
        if row["edge_id"] == edge_id:
            observed = abs(row["observed_standardized_mean_car"])
            mde = row["mde_standardized_mean_car"]
            return (
                f"Power: |observed standardized mean CAR| "
                f"{observed:.4f} vs MDE {mde:.4f} at n="
                f"{row['observations']} (80% power, alpha 0.05, "
                f"one-sided) — the effect sits "
                f"{'above' if observed >= mde else 'below'} the "
                f"detection limit of the design."
            )
    for row in power["mean_comparison"]:
        if row["edge_id"] == edge_id:
            return (
                f"Power: observed Cohen's d {row['observed_cohens_d']:.4f} "
                f"vs MDE {row['mde_cohens_d']:.4f}, observed mean ratio "
                f"{row['observed_mean_ratio']:.4f} vs MDE "
                f"{row['mde_mean_ratio']:.4f} "
                f"(n={row['window_observations']}/"
                f"{row['nonwindow_observations']}, 80% power, alpha 0.05)."
            )
    return None


def power_note_for_trial(audit_summary: dict, trial_id: str) -> str | None:
    """Power juxtaposition for one trial's primary test."""
    power = audit_summary["power"]
    for row in power["lead_lag_partial_r_squared"]:
        if row["trial_id"] == trial_id:
            return (
                f"Power: observed partial R^2 "
                f"{row['observed_partial_r_squared']:.5f} vs MDE "
                f"{row['mde_partial_r_squared']:.5f} at n="
                f"{row['observations']} (80% power, alpha 0.05) — the "
                f"design was underpowered for an effect of the observed "
                f"size; the null result rules out large effects, not "
                f"small ones."
            )
    cross = power["cross_section_r_squared"]
    if cross["trial_id"] == trial_id:
        return (
            f"Power: observed R^2 {cross['observed_r_squared']:.4f} vs "
            f"MDE {cross['mde_r_squared']:.4f} at n="
            f"{cross['observations']} (80% power, alpha 0.05)."
        )
    return None


# ---------------------------------------------------------------------------
# Record builders
# ---------------------------------------------------------------------------


def base_record(
    record_id: str,
    record_type: str,
    edge: dict,
    trial: dict,
) -> dict:
    """Identity block shared by both record types."""
    return {
        "schema_version": SCHEMA_VERSION,
        "record_id": record_id,
        "record_type": record_type,
        "hypothesis_id": edge["hypothesis_id"],
        "hypothesis_version": edge["hypothesis_version"],
        "trial_id": edge["trial_id"],
        "preregistration_fingerprint": edge["preregistration_fingerprint"],
        "ledger_path": edge["ledger_path"],
        "trial_record_hash": edge["trial_record_hash"],
        "study": study_of(edge),
        "report_path": edge["report_path"],
    }


def build_supported_edge_record(
    edge: dict,
    trial: dict,
    edges_by_test_key: dict[str, dict],
    audit_row: dict,
    audit_summary: dict,
    is_primary: bool,
    hypothesis_supported: bool,
) -> dict:
    record_id = f"DR-{edge['edge_id']}"
    record = base_record(record_id, "supported_edge", edge, trial)
    record["edge_id"] = edge["edge_id"]
    record["ledger_test_key"] = edge["ledger_test_key"]
    record["conclusion"] = "SUPPORTED"
    if is_primary:
        record["conclusion_scope"] = (
            "Primary edge of a SUPPORTED hypothesis: the hypothesis "
            "verdict was decided by this test."
        )
    elif hypothesis_supported:
        record["conclusion_scope"] = (
            "Secondary edge of a SUPPORTED hypothesis: significant within "
            "the study's preregistered Holm family."
        )
    else:
        record["conclusion_scope"] = (
            "Secondary edge within its study's preregistered Holm family. "
            "The hypothesis itself was REJECTED on its primary test; this "
            "record covers only this edge, which was significant within "
            "the family."
        )
    metrics = trial["result"]["metrics"]
    holm_by_test = {entry["test"]: entry for entry in metrics["holm"]}
    evidence = {
        "primary_test": extract_test_evidence(trial, edge, holm_by_test),
        "family_tests": family_tests_evidence(trial, edges_by_test_key),
        "verdict_criteria": dict(metrics["verdict"]["criteria"]),
        "verdict_supported": bool(metrics["verdict"]["supported"]),
        "holdout_oos": holdout_evidence(trial),
        "cost_gate": cost_gate_evidence(trial),
        "sample": dict(edge["sample"]) if edge.get("sample") else None,
        "lab_wide": {
            "family_size": audit_summary["lab_wide_audit"]["family_size"],
            "holm_adjusted_p_value": audit_row["holm_adjusted_p_value"],
            "bh_adjusted_p_value": audit_row["bh_adjusted_p_value"],
            "holm_significant": audit_row["holm_significant"],
            "bh_significant": audit_row["bh_significant"],
        },
    }
    record["evidence"] = evidence
    record["limitations"] = list(LIMITATIONS[record_id])
    notes = [
        lab_wide_note(audit_row, audit_summary["lab_wide_audit"]["family_size"])
    ]
    if "caveat" in audit_row:
        notes.append(f"Known caveat (from the study report): {audit_row['caveat']}")
    power_note = power_note_for_edge(audit_summary, edge["edge_id"])
    if power_note:
        notes.append(power_note)
    record["audit_notes"] = notes
    return record


def build_rejected_hypothesis_record(
    edge: dict,
    trial: dict,
    edges_by_test_key: dict[str, dict],
    audit_summary: dict,
) -> dict:
    record_id = f"DR-{edge['hypothesis_id']}"
    record = base_record(record_id, "rejected_hypothesis", edge, trial)
    record["primary_edge_id"] = edge["edge_id"]
    record["ledger_test_key"] = edge["ledger_test_key"]
    record["conclusion"] = "REJECTED"
    failed = [
        name
        for name, passed in trial["result"]["metrics"]["verdict"]["criteria"].items()
        if not passed
    ]
    record["conclusion_scope"] = (
        "Primary test failed its preregistered criteria "
        f"({len(failed)} of "
        f"{len(trial['result']['metrics']['verdict']['criteria'])} failed; "
        "see evidence.verdict_criteria). The rejection is about the "
        "preregistered effect at the preregistered threshold, not a claim "
        "that no effect of any size exists."
    )
    metrics = trial["result"]["metrics"]
    holm_by_test = {entry["test"]: entry for entry in metrics["holm"]}
    record["evidence"] = {
        "primary_test": extract_test_evidence(trial, edge, holm_by_test),
        "family_tests": family_tests_evidence(trial, edges_by_test_key),
        "verdict_criteria": dict(metrics["verdict"]["criteria"]),
        "verdict_supported": bool(metrics["verdict"]["supported"]),
        "holdout_oos": holdout_evidence(trial),
        "cost_gate": cost_gate_evidence(trial),
        "sample": dict(edge["sample"]) if edge.get("sample") else None,
    }
    record["limitations"] = list(LIMITATIONS[record_id])
    notes: list[str] = []
    power_note = power_note_for_trial(audit_summary, edge["trial_id"])
    if power_note is None:
        power_note = power_note_for_edge(audit_summary, edge["edge_id"])
    if power_note:
        notes.append(power_note)
    if not notes:
        notes.append(
            "No power juxtaposition in the audit summary covers this "
            "trial's primary design."
        )
    record["audit_notes"] = notes
    return record


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def build_records(repo_root: Path) -> dict[str, dict]:
    """Build all 17 decision records; returns record_id -> record."""
    registry = load_json(repo_root / "research" / "graph" / "registry.json")
    audit_summary = load_json(
        repo_root / "research" / "statistical-audit-2b" / "summary.json"
    )
    ledgers = LedgerReader(repo_root)
    edges = registry["edges"]
    by_id = {edge["edge_id"]: edge for edge in edges}
    by_trial: dict[str, dict[str, dict]] = {}
    for edge in edges:
        by_trial.setdefault(edge["trial_id"], {})[edge["ledger_test_key"]] = edge

    # Verify the correspondence tables against the registry.
    for trial_id, (edge_id, hypothesis_id) in PRIMARY_EDGES.items():
        edge = by_id.get(edge_id)
        if edge is None:
            raise ValueError(f"primary edge {edge_id} missing from registry")
        if edge["trial_id"] != trial_id or edge["hypothesis_id"] != hypothesis_id:
            raise ValueError(
                f"{edge_id} is {edge['trial_id']}/{edge['hypothesis_id']}, "
                f"expected {trial_id}/{hypothesis_id}"
            )
    for edge_id in SUPPORTED_EDGE_IDS:
        edge = by_id.get(edge_id)
        if edge is None or edge["status"] != "supported":
            raise ValueError(f"supported edge {edge_id} missing or not supported")
    audit_rows = {
        row["edge_id"]: row
        for row in audit_summary["lab_wide_audit"]["supported_edges"]
    }
    if set(audit_rows) != set(SUPPORTED_EDGE_IDS):
        raise ValueError("audit summary supported edges != SUPPORTED_EDGE_IDS")

    records: dict[str, dict] = {}
    for edge_id in SUPPORTED_EDGE_IDS:
        edge = by_id[edge_id]
        trial = ledgers.trial(edge["ledger_path"], edge["trial_id"])
        primary_edge_id, _ = PRIMARY_EDGES[edge["trial_id"]]
        is_primary = edge_id == primary_edge_id
        hypothesis_supported = bool(
            trial["result"]["metrics"]["verdict"]["supported"]
        )
        record = build_supported_edge_record(
            edge,
            trial,
            by_trial[edge["trial_id"]],
            audit_rows[edge_id],
            audit_summary,
            is_primary,
            hypothesis_supported,
        )
        records[record["record_id"]] = record
    for trial_id, hypothesis_id in REJECTED_HYPOTHESES:
        edge_id, expected_hypothesis = PRIMARY_EDGES[trial_id]
        if expected_hypothesis != hypothesis_id:
            raise ValueError(
                f"{trial_id} primary is {expected_hypothesis}, "
                f"expected {hypothesis_id}"
            )
        edge = by_id[edge_id]
        trial = ledgers.trial(edge["ledger_path"], trial_id)
        if trial["result"]["metrics"]["verdict"]["supported"]:
            raise ValueError(f"trial {trial_id} is supported, not rejected")
        record = build_rejected_hypothesis_record(
            edge,
            trial,
            by_trial[trial_id],
            audit_summary,
        )
        records[record["record_id"]] = record
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)
    records = build_records(args.repo_root)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for record_id in sorted(records):
        path = args.out_dir / f"{record_id}.json"
        path.write_text(
            json.dumps(records[record_id], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(f"records: {len(records)} written to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
