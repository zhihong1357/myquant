"""Validate the Stage 6c scaffold generator (research/scaffold-6c/).

Generates a study scaffold from the planner's top-ranked BAA10Y->SPX
template and checks, in order:

(a) the generated preregister.py refuses while TODOs remain (listing
    exactly what is missing), then registers a legal spec with a
    recorded fingerprint once a minimal design is filled in;
(b) the generated Python files pass ruff and mypy strict — for all
    four test types, not just the lead-lag case;
(c) the same spec generated twice is byte-identical;
(d) the guards refuse (re-generation into an existing directory, an
    unknown source id, an unknown test type);
(e) the generated run_trial.py skeleton runs end to end on a fixed-
    seed synthetic panel and writes a valid ledger entry.

Everything runs in throwaway tmp directories (plus a tmp git repo for
the trial run, since run_trial.py records the HEAD revision). No real
market data is fetched, no real trial is run, and nothing is written
to research/<new study>/ — the only committed outputs are this
script, the report it renders, and an as-generated inspection copy
under research/scaffold-6c/generated/ (TODOs intact).

Run from the repo root:

    .venv/bin/python research/scaffold-6c/validate_scaffold.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from myquant.canonical import canonical_json  # noqa: E402
from myquant.contracts import Observation  # noqa: E402
from myquant.graph import EdgeTestType  # noqa: E402
from myquant.hypotheses import HypothesisRegistry  # noqa: E402
from myquant.pit import ParquetPITStore  # noqa: E402
from myquant.registry import read_and_verify  # noqa: E402
from myquant.scaffolding import (  # noqa: E402
    ScaffoldError,
    StudySpec,
    generate,
    load_source_metadata,
    spec_from_planner_draft,
)
from myquant.sources import SourceRegistry  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent
# Frozen copy of the planner's BAA10Y->SPX template (see
# tests/fixtures/planner-template-baa-spx.json). The live template is
# deleted once its pair is studied (study 008 consumed it).
TEMPLATE_PATH = REPO_ROOT / "tests" / "fixtures" / "planner-template-baa-spx.json"
EVIDENCE_REGISTRY = REPO_ROOT / "research" / "evidence-6b" / "sources.json"

SLUG = "baa-spx-transmission-008"
HYPOTHESIS_ID = "H9001"
TRIAL_ID = "T9001"  # Synthetic wiring-test id; never a lab trial id.
SYNTHETIC_SEED = 1234
SYNTHETIC_BARS = 500

RESULTS: dict[str, Any] = {}


def _load_template() -> dict[str, Any]:
    return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))


def _baa_spx_spec() -> StudySpec:
    return spec_from_planner_draft(
        _load_template(),
        study_number=8,
        slug=SLUG,
        hypothesis_id=HYPOTHESIS_ID,
        source_ids=("fred", "yahoo-finance"),
        calendar_ids=("us-equity",),
        trial_id=TRIAL_ID,
    )


def _other_type_specs() -> list[StudySpec]:
    """One hand-built spec per remaining test type (lint coverage)."""
    return [
        StudySpec(
            study_number=9,
            slug="btc-window-vol-009",
            hypothesis_id="H9002",
            source_instrument="crypto:btc-usdt-perp",
            target_instrument="crypto:btc-usdt-perp",
            test_type=EdgeTestType.MEAN_COMPARISON,
            frequency="1h",
            source_ids=("okx-public",),
            universe=("crypto:btc-usdt-perp",),
            calendar_ids=("crypto-24-7",),
            minimum_effect_size=1.15,
            acceptance_criteria=(
                "window mean at least 1.15x non-window mean",
            ),
        ),
        StudySpec(
            study_number=10,
            slug="dvol-event-study-010",
            hypothesis_id="H9003",
            source_instrument="vol:btc-dvol",
            target_instrument="vol:btc-dvol",
            test_type=EdgeTestType.EVENT_STUDY,
            frequency="monthly",
            source_ids=("deribit", "fred"),
            universe=("vol:btc-dvol", "rates:baa-10y"),
            calendar_ids=("us-equity",),
            minimum_effect_size=0.3,
            acceptance_criteria=("standardized mean CAR clears 0.3",),
        ),
        StudySpec(
            study_number=11,
            slug="cpi-cross-section-011",
            hypothesis_id="H9004",
            source_instrument="rates:dgs10",
            target_instrument="macro:cpi",
            test_type=EdgeTestType.CROSS_SECTION,
            frequency="daily",
            source_ids=("fred", "bls"),
            universe=("rates:dgs10", "macro:cpi"),
            calendar_ids=("us-equity",),
            minimum_effect_size=0.05,
            acceptance_criteria=("cross-section R2 at least 0.05",),
        ),
    ]


def _fill_minimal(study_dir: Path) -> None:
    """Fill the generated scaffold with a minimal wiring design.

    Values mirror the committed study 003/005 contracts where they
    exist. This is a wiring fill for validation only, not a research
    design: the mechanism and cost text say so explicitly.
    """
    design_path = study_dir / "design.json"
    design = json.loads(design_path.read_text(encoding="utf-8"))
    design.update(
        {
            "title": "BAA10Y spread leads S&P 500 daily returns (wiring test)",
            "mechanism": (
                "Wiring-test placeholder: a widening credit spread may "
                "precede equity weakness. Not a research claim."
            ),
            "model_definition": [
                "Partial lead-lag OLS with Newey-West HAC standard errors",
                "Robustness: no-factor control (wiring placeholder)",
            ],
            "acceptance_criteria": [
                "Holm-adjusted primary p-value below 0.05",
                "Primary partial R-squared at least 0.005",
                "Holdout out-of-sample incremental R-squared above 0",
                "Net daily edge after the round-trip taker cost is positive",
            ],
            "rejection_criteria": [
                criterion
                for criterion in design["rejection_criteria"]
                if "TODO" not in criterion
            ]
            or ["Rejected when any acceptance criterion fails"],
            "feature_set": ["baa-10y-spread.close@v1", "sp500.close@v1"],
            "fixed_parameters": ["lag=1", "max_hac_lag=5"],
            "train_window": {
                "start": "2003-01-02T21:00:00+00:00",
                "end": "2019-12-31T21:00:00+00:00",
            },
            "validation_window": {
                "start": "2020-01-02T21:00:00+00:00",
                "end": "2023-12-29T21:00:00+00:00",
            },
            "holdout_window": {
                "start": "2024-01-02T21:00:00+00:00",
                "end": "2026-11-16T21:00:00+00:00",
            },
            "minimum_train_observations": 1000,
            "minimum_validation_observations": 500,
            "minimum_holdout_observations": 500,
            "expected_direction": "two_sided",
            "benchmark": "constant-mean benchmark",
            "cost_model": "OKX VIP0 taker 0.05% per side (wiring placeholder)",
            "cost_assumptions": [
                "Taker fee 0.05% per side (wiring placeholder)."
            ],
            "multiple_testing_family": "primary lead-lag test only",
            "planned_test_count": 1,
            "known_confounders": ["common market factor (wiring placeholder)"],
            "exclusions": ["none (wiring placeholder)"],
            "random_seed": SYNTHETIC_SEED,
        }
    )
    design_path.write_text(
        json.dumps(design, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    fred = json.loads((study_dir / "sources" / "fred" / "v1.json").read_text())
    fred.update(
        {
            "attribution": "Source: Federal Reserve Bank of St. Louis",
            "license_status": "approved",
            "nominal_delay_seconds": 0,
            "permission_basis": (
                "Public economic data published by the Federal Reserve "
                "Bank of St. Louis, free to use with attribution; the "
                "fredgraph.csv endpoint requires no API key. Used for "
                "research only; raw payloads are not redistributed. "
                "FRED terms of use reviewed 2026-11-18. This registry "
                "entry is an explicit research-use assertion, not a "
                "legal determination."
            ),
            "terms_url": (
                "https://fred.stlouisfed.org/docs/api/terms_of_use.html"
            ),
            "timestamp_basis": (
                "Daily closing values dated observation_date; the event "
                "time is the US equity close (16:00 ET) recorded as "
                "21:00 UTC (fixed; DST is not modelled) and "
                "available_at equals the event time. FRED's actual "
                "publication lag is not modelled."
            ),
        }
    )
    (study_dir / "sources" / "fred" / "v1.json").write_text(
        json.dumps(fred, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    yahoo = json.loads(
        (study_dir / "sources" / "yahoo-finance" / "v1.json").read_text()
    )
    yahoo.update(
        {
            "attribution": "Data: Yahoo Finance",
            "license_status": "approved",
            "nominal_delay_seconds": 0,
            "permission_basis": (
                "Public market data served without authentication by "
                "Yahoo's chart endpoint, used for research only; raw "
                "payloads are not redistributed. Yahoo Terms of Service "
                "reviewed 2026-11-18. This registry entry is an explicit "
                "research-use assertion, not a legal determination."
            ),
            "terms_url": (
                "https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html"
            ),
            "timestamp_basis": (
                "Daily bars timestamped at the market open (09:30 ET); "
                "the trading date is derived in America/New_York and "
                "the close is recorded at 21:00 UTC, matching the FRED "
                "convention."
            ),
        }
    )
    (study_dir / "sources" / "yahoo-finance" / "v1.json").write_text(
        json.dumps(yahoo, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (study_dir / "catalog" / "instruments" / "credit%3Abaa-10y-spread" / "v1.json").write_text(
        json.dumps(
            {
                "instrument_id": "credit:baa-10y-spread",
                "asset_class": "credit",
                "instrument_type": "rate",
                "name": (
                    "Moody's Seasoned Baa Corporate Bond Yield Relative "
                    "to 10-Year Treasury (BAA10Y)"
                ),
                "quote_currency": "percent",
                "calendar_id": "us-equity",
                "metadata": {"fred_series": "BAA10Y"},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (study_dir / "catalog" / "instruments" / "index%3Asp500" / "v1.json").write_text(
        json.dumps(
            {
                "instrument_id": "index:sp500",
                "asset_class": "index",
                "instrument_type": "index",
                "name": "S&P 500 Index",
                "quote_currency": "points",
                "calendar_id": "us-equity",
                "metadata": {"yahoo_symbol": "^GSPC"},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (study_dir / "catalog" / "calendars" / "us-equity" / "v1.json").write_text(
        json.dumps(
            {
                "calendar_id": "us-equity",
                "timezone_name": "America/New_York",
                "weekdays": [0, 1, 2, 3, 4],
                "regular_open": "09:30:00",
                "regular_close": "16:00:00",
                "open_day_offset": 0,
                "close_day_offset": 0,
                "holidays": [],
                "early_closes": {},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _check_preregister(study_dir: Path) -> None:
    """(a) The generated preregister refuses, then registers."""
    python = sys.executable
    refused = _run([python, str(study_dir / "preregister.py")], cwd=REPO_ROOT)
    assert refused.returncode == 1, refused.stdout + refused.stderr
    missing = [
        line.strip()[2:]
        for line in refused.stdout.splitlines()
        if line.startswith("  - ")
    ]
    assert "design.json: mechanism" in missing
    assert "design.json: title" in missing
    assert "sources/fred/v1.json: permission_basis" in missing
    assert "design.json: trial_id" not in missing
    RESULTS["todo_items_refused"] = len(missing)

    _fill_minimal(study_dir)
    registered = _run([python, str(study_dir / "preregister.py")], cwd=REPO_ROOT)
    assert registered.returncode == 0, registered.stdout + registered.stderr
    registry = HypothesisRegistry(study_dir / "hypotheses")
    registration = registry.get(HYPOTHESIS_ID, version=1)
    assert registration.version == 1
    fingerprint = hashlib.sha256(
        canonical_json(registration.spec.model_dump(mode="json"))
    ).hexdigest()
    assert fingerprint == registration.spec_fingerprint
    RESULTS["spec_fingerprint"] = registration.spec_fingerprint
    RESULTS["registration_hash"] = registration.registration_hash


def _check_lint(tmp_root: Path, study_dirs: list[Path]) -> None:
    """(b) The generated Python files pass ruff and mypy strict."""
    bin_dir = Path(sys.executable).parent
    python_files = sorted(
        path
        for study_dir in study_dirs
        for path in study_dir.glob("*.py")
    )
    ruff = _run(
        [
            str(bin_dir / "ruff"),
            "check",
            "--config",
            str(REPO_ROOT / "pyproject.toml"),
            *[str(path) for path in python_files],
        ],
        cwd=REPO_ROOT,
    )
    assert ruff.returncode == 0, ruff.stdout + ruff.stderr
    RESULTS["ruff"] = ruff.stdout.strip().splitlines()[-1]
    RESULTS["ruff_files"] = len(python_files)

    # mypy resolves myquant from the source tree (MYPYPATH): the
    # installed package carries no py.typed marker, so a plain mypy
    # run would skip the imports. One study at a time: all four
    # studies share filenames, and mypy rejects duplicate modules.
    env = {**os.environ, "MYPYPATH": str(REPO_ROOT / "src")}
    mypy_results: list[str] = []
    for study_dir in study_dirs:
        files = sorted(study_dir.glob("*.py"))
        mypy = _run(
            [
                str(bin_dir / "mypy"),
                "--strict",
                "--no-incremental",
                "--config-file",
                str(REPO_ROOT / "pyproject.toml"),
                *[str(path) for path in files],
            ],
            cwd=REPO_ROOT,
            env=env,
        )
        assert mypy.returncode == 0, mypy.stdout + mypy.stderr
        mypy_results.append(f"{study_dir.name}: {mypy.stdout.strip()}")
    RESULTS["mypy"] = mypy_results


def _check_determinism(tmp_root: Path, metadata: dict[str, tuple[str, str]]) -> None:
    """(c) The same spec generated twice is byte-identical."""
    spec = _baa_spx_spec()
    known = frozenset(metadata)
    first = generate(
        spec,
        target=tmp_root / "det-a" / "research" / SLUG,
        known_source_ids=known,
        source_metadata=metadata,
        docs_root=tmp_root / "det-a" / "docs" / "studies",
    )
    second = generate(
        spec,
        target=tmp_root / "det-b" / "research" / SLUG,
        known_source_ids=known,
        source_metadata=metadata,
        docs_root=tmp_root / "det-b" / "docs" / "studies",
    )
    assert len(first) == len(second)
    for left, right in zip(first, second, strict=True):
        assert left.read_bytes() == right.read_bytes()
    RESULTS["determinism_files"] = len(first)


def _check_guards(tmp_root: Path, metadata: dict[str, tuple[str, str]]) -> None:
    """(d) The guards refuse instead of guessing."""
    spec = _baa_spx_spec()
    known = frozenset(metadata)
    target = tmp_root / "guard" / "research" / SLUG
    generate(
        spec,
        target=target,
        known_source_ids=known,
        source_metadata=metadata,
        docs_root=tmp_root / "guard" / "docs" / "studies",
    )
    refusals: list[str] = []
    try:
        generate(
            spec,
            target=target,
            known_source_ids=known,
            source_metadata=metadata,
            docs_root=tmp_root / "guard" / "docs" / "studies",
        )
    except ScaffoldError as exc:
        refusals.append(
            "existing directory: "
            + str(exc).replace(str(tmp_root), "<tmp>")
        )
    else:
        raise AssertionError("re-generation into an existing dir was allowed")
    try:
        bad_source_spec = spec_from_planner_draft(
            _load_template(),
            study_number=8,
            slug=SLUG,
            hypothesis_id=HYPOTHESIS_ID,
            source_ids=("fred", "no-such-source"),
            calendar_ids=("us-equity",),
        )
        generate(
            bad_source_spec,
            target=tmp_root / "guard" / "research" / "other-008",
            known_source_ids=known,
            source_metadata=metadata,
            docs_root=tmp_root / "guard" / "docs" / "studies",
        )
    except ScaffoldError as exc:
        refusals.append(f"unknown source id: {exc}")
    else:
        raise AssertionError("unknown source id was allowed")
    bad_draft = _load_template()
    bad_draft["suggested_test_type"] = "granger"
    try:
        spec_from_planner_draft(
            bad_draft,
            study_number=8,
            slug=SLUG,
            hypothesis_id=HYPOTHESIS_ID,
            source_ids=("fred",),
            calendar_ids=("us-equity",),
        )
    except ValueError as exc:
        refusals.append(f"unknown test type: {exc}")
    else:
        raise AssertionError("unknown test type was allowed")
    RESULTS["guard_refusals"] = refusals


def _write_synthetic_panel(repo_root: Path, study_dir: Path) -> None:
    """A fixed-seed synthetic panel (independent random walks).

    available_at equals event_time: a simplified PIT convention for
    wiring only, stated in the report. The numbers claim nothing.
    """
    fetched_at = datetime(2026, 11, 19, 0, 0, tzinfo=UTC)
    rng = np.random.default_rng(SYNTHETIC_SEED)
    n = SYNTHETIC_BARS
    baa_close = 2.0 + np.cumsum(rng.normal(0, 0.02, n))
    spx_close = 5000.0 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    last = datetime(2026, 11, 16, 21, 0, tzinfo=UTC)
    times = [last - timedelta(days=n - 1 - i) for i in range(n)]
    observations: list[Observation] = []
    for event_time, value in zip(times, baa_close, strict=True):
        observations.append(
            Observation(
                instrument_id="credit:baa-10y-spread",
                venue="fred",
                event_time=event_time,
                available_at=event_time,
                ingested_at=fetched_at,
                field="close",
                value=float(value),
                unit="percent",
                source_id="fred",
                source_version=1,
            )
        )
    for event_time, value in zip(times, spx_close, strict=True):
        observations.append(
            Observation(
                instrument_id="index:sp500",
                venue="yahoo",
                event_time=event_time,
                available_at=event_time,
                ingested_at=fetched_at,
                field="close",
                value=float(value),
                unit="points",
                source_id="yahoo-finance",
                source_version=1,
            )
        )
    registry = SourceRegistry(study_dir / "sources")
    store = ParquetPITStore(
        repo_root / "data" / "cache" / SLUG / "pit-1d", registry
    )
    store.write_batch(observations)
    (study_dir / "manifest.json").write_text(
        json.dumps(
            {
                "study": SLUG,
                "fetched_at": fetched_at.isoformat(),
                "note": (
                    f"SYNTHETIC wiring panel (seed {SYNTHETIC_SEED}); "
                    "not real market data."
                ),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _check_wiring(repo_root: Path, study_dir: Path) -> None:
    """(e) The generated run_trial.py runs end to end on synthetic data."""
    _write_synthetic_panel(repo_root, study_dir)
    git = _run(["git", "init", "-q"], cwd=repo_root)
    assert git.returncode == 0, git.stderr
    _run(["git", "add", "-A"], cwd=repo_root)
    committed = _run(
        [
            "git",
            "-c",
            "user.email=wiring@test.invalid",
            "-c",
            "user.name=scaffold-validation",
            "commit",
            "-qm",
            "wiring test scaffold",
        ],
        cwd=repo_root,
    )
    assert committed.returncode == 0, committed.stderr
    trial = _run(
        [sys.executable, str(study_dir / "run_trial.py")], cwd=repo_root
    )
    assert trial.returncode == 0, trial.stdout + trial.stderr
    records = read_and_verify(study_dir / "trials.jsonl")
    assert len(records) == 1
    record = records[0]
    assert record["trial_id"] == TRIAL_ID
    assert record["status"] == "completed"
    metrics = record["result"]["metrics"]
    primary = metrics["tests"]["primary"]
    panel_match = re.search(r"panel: (\d+) rows", trial.stdout)
    assert panel_match is not None, trial.stdout
    RESULTS["wiring"] = {
        "panel_rows": int(panel_match.group(1)),
        "trial_id": record["trial_id"],
        "status": record["status"],
        "record_hash": record["record_hash"],
        "observations": primary["observations"],
        "coefficient": primary["coefficient"],
        "p_value": primary["p_value"],
        "partial_r_squared": primary["partial_r_squared"],
        "verdict_supported": metrics["verdict"]["supported"],
        "stdout": trial.stdout.strip(),
    }


def _write_generated_copy(metadata: dict[str, tuple[str, str]]) -> list[str]:
    """The committed as-generated inspection copy (TODOs intact)."""
    generated_root = HERE / "generated"
    if generated_root.exists():
        shutil.rmtree(generated_root)
    paths = generate(
        _baa_spx_spec(),
        target=generated_root / "research" / SLUG,
        known_source_ids=frozenset(metadata),
        source_metadata=metadata,
        docs_root=generated_root / "docs" / "studies",
    )
    return sorted(str(path.relative_to(generated_root)) for path in paths)


def _render_report(generated_files: list[str]) -> str:
    wiring = RESULTS["wiring"]
    refusals = "\n".join(f"- {item}" for item in RESULTS["guard_refusals"])
    mypy_lines = "\n".join(f"- {line}" for line in RESULTS["mypy"])
    files = "\n".join(f"- `{path}`" for path in generated_files)
    return f"""# Stage 6c validation: the experiment assistant scaffold

Generated by `validate_scaffold.py` at {datetime.now(UTC).isoformat()}.
All checks ran in throwaway tmp directories (plus a tmp git repo for
the trial run). No real market data was fetched, no real trial was
run, and nothing was written to `research/<new study>/`.

## Input

- Planner template: `tests/fixtures/planner-template-baa-spx.json`
  (frozen copy of the planner's BAA10Y->SPX template; the live template
  was deleted once study 008 consumed the pair. Rank 1, total score
  1.00, daily lead-lag, minimum effect size 0.005, estimated joint
  rows 5967, adjacent supported edge E0026).
- Study spec: study 008, slug `{SLUG}`, hypothesis `{HYPOTHESIS_ID}`,
  trial `{TRIAL_ID}` (a synthetic wiring-test id, deliberately never a
  lab trial id — the next real trial id is T0016).
- Sources: `fred`, `yahoo-finance` (both in the 6b registry).
  Calendar: `us-equity`.

## Generated directory (as-generated copy under `generated/`)

{files}

13 files: 6 study files, 1 parked draft, 4 contract stubs, 1 spec,
1 report template. No `trials.jsonl`, no `manifest.json`, no panel —
the scaffold starts nothing.

## (a) Preregistration

- Unfilled scaffold: `preregister.py` exits 1 and lists
  **{RESULTS["todo_items_refused"]} missing items** by JSON path
  (design fields, source/catalog stub fields). The trial id is
  correctly excluded: it is a run concern, not a registration one.
- Minimal design filled in (values mirror the committed study 003/005
  contracts where they exist; the mechanism and cost text are marked
  as wiring placeholders): `preregister.py` registers `{HYPOTHESIS_ID}`
  as v1 through the repo's `HypothesisRegistry` — real validation,
  real fingerprinting, no scaffold-side machinery.
- Spec fingerprint:
  `{RESULTS["spec_fingerprint"]}`
- Registration hash:
  `{RESULTS["registration_hash"]}`
- The fingerprint was recomputed independently (canonical JSON of the
  registered spec) and matches.

## (b) Lint: the generated code is clean code

- ruff (`ruff check`, repo config): **{RESULTS["ruff"]}**
  ({RESULTS["ruff_files"]} generated Python files across all four test types).
- mypy strict (`MYPYPATH=src`, one study at a time — all four studies
  share filenames, and mypy rejects duplicate modules):

{mypy_lines}

Note: mypy needs `MYPYPATH=src` because the installed `myquant`
package carries no `py.typed` marker; a plain mypy run would skip the
imports instead of checking them. (The repo's own study scripts are
not held to mypy strict — study 001's `run_trial.py` has 2 pre-existing
strict errors under the same invocation. The scaffold holds its
generated code to the stricter bar.)

## (c) Determinism

The same spec generated twice into two tmp directories:
**{RESULTS["determinism_files"]} files, all byte-identical.**

## (d) Guards

All three refusals fired, nothing written:

{refusals}

## (e) Synthetic wiring run

The generated `run_trial.py` ran end to end in a tmp git repo against
a fixed-seed synthetic panel:

- Synthetic data: seed {SYNTHETIC_SEED}, {SYNTHETIC_BARS} daily bars per
  instrument, independent random walks (no transmission by
  construction), closes only, `available_at` = `event_time`
  (simplified PIT for wiring only).
- Panel: {wiring["panel_rows"]} return rows (500 closes, 1 dropped first
  return row).
- Trial `{wiring["trial_id"]}` completed: ledger record
  `{wiring["record_hash"]}`, verified with `read_and_verify`
  (1 record, hash chain intact).
- Primary test: {wiring["observations"]} observations, coefficient
  {wiring["coefficient"]:.6f}, p {wiring["p_value"]:.4g}, partial R²
  {wiring["partial_r_squared"]:.6f}; verdict supported:
  **{wiring["verdict_supported"]}**.

Conclusion: **the wiring works** (read panel → run kernel → write
ledger). The numbers claim nothing — independent random walks have no
transmission by construction, and a verdict of False on synthetic
noise is the expected outcome, not a finding.

## Limitations

- One test type (lead-lag) was wired end to end. The other three
  types (mean comparison, event study, cross-section) were generated
  and lint-checked, but their design hooks (`condition_mask`,
  `load_events`, `load_event_cars`) raise `NotImplementedError` until
  a researcher defines them — no wiring run exists for them yet.
- The synthetic panel is Gaussian daily noise with a simplified PIT
  convention; it validates machinery, not market behaviour.
- The fetch skeleton was not run against live endpoints in this
  validation (no real data was fetched by design). Its per-source
  fetchers mirror the adapters' real APIs and the fetch flows of
  studies 001/003/005, but the first real fetch of a scaffolded study
  is still untested ground.
- The minimal design fill is a wiring placeholder, not a research
  design: no hypothesis was registered in the lab, no trial id was
  consumed, and the H9001/T9001 identifiers in this validation must
  not be confused with lab records.
- Re-running this script reproduces the report except for three
  values that embed wall-clock time by design: the report timestamp,
  the registration hash (`registered_at`), and the ledger record hash
  (`recorded_at`). The spec fingerprint, the wiring numbers, and the
  generated files are byte-stable across runs.
"""


def main() -> None:
    metadata = load_source_metadata(EVIDENCE_REGISTRY)
    generated_files = _write_generated_copy(metadata)
    RESULTS["generated_files"] = generated_files
    with tempfile.TemporaryDirectory(prefix="scaffold-6c-") as tmp:
        tmp_root = Path(tmp)
        repo_root = tmp_root / "repo"
        study_dir = repo_root / "research" / SLUG
        generate(
            _baa_spx_spec(),
            target=study_dir,
            known_source_ids=frozenset(metadata),
            source_metadata=metadata,
            docs_root=repo_root / "docs" / "studies",
        )
        study_dirs = [study_dir]
        for other in _other_type_specs():
            other_dir = repo_root / "research" / other.slug
            generate(
                other,
                target=other_dir,
                known_source_ids=frozenset(metadata),
                source_metadata=metadata,
                docs_root=repo_root / "docs" / "studies",
            )
            study_dirs.append(other_dir)
        _check_preregister(study_dir)
        _check_lint(tmp_root, study_dirs)
        _check_determinism(tmp_root, metadata)
        _check_guards(tmp_root, metadata)
        _check_wiring(repo_root, study_dir)
    report = _render_report(generated_files)
    (HERE / "validation_report.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
