"""Tests for the Stage 6c experiment assistant (scaffold generator).

All tests are offline. The planner-input tests read one real 6a
template draft (read-only); the generation tests write into tmp
directories; the wiring test runs a generated run_trial.py against a
fixed-seed synthetic panel and checks the ledger — the numbers claim
nothing, they only prove the skeleton is wired.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from myquant.canonical import canonical_json
from myquant.contracts import Observation
from myquant.graph import EdgeTestType
from myquant.hypotheses import HypothesisRegistry
from myquant.market import Instrument
from myquant.pit import ParquetPITStore
from myquant.registry import read_and_verify
from myquant.scaffolding import (
    ScaffoldError,
    StudySpec,
    generate,
    load_source_metadata,
    spec_from_planner_draft,
)
from myquant.sources import SourceRegistry

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = (
    REPO_ROOT
    / "research"
    / "planner-6a"
    / "templates"
    / "credit-baa-10y-spread__index-sp500.json"
)
EVIDENCE_REGISTRY = REPO_ROOT / "research" / "evidence-6b" / "sources.json"

KNOWN_SOURCES = frozenset(
    {
        "okx-public",
        "deribit",
        "fred",
        "yahoo-finance",
        "fiscaldata",
        "federalreserve",
        "bls",
        "hyperliquid",
    }
)


def _load_template() -> dict[str, Any]:
    return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))


def _baa_spx_spec(**overrides: Any) -> StudySpec:
    """The BAA10Y->SPX spec from the real planner template."""
    kwargs: dict[str, Any] = {
        "study_number": 8,
        "slug": "baa-spx-transmission-008",
        "hypothesis_id": "H9001",
        "source_ids": ("fred", "yahoo-finance"),
        "calendar_ids": ("us-equity",),
        "trial_id": "T9001",
    }
    kwargs.update(overrides)
    return spec_from_planner_draft(_load_template(), **kwargs)


def _generate(
    spec: StudySpec, tmp_path: Path, **kwargs: Any
) -> tuple[Path, list[Path]]:
    target = tmp_path / "research" / spec.slug
    kwargs.setdefault(
        "source_metadata", load_source_metadata(EVIDENCE_REGISTRY)
    )
    paths = generate(
        spec,
        target=target,
        known_source_ids=KNOWN_SOURCES,
        docs_root=tmp_path / "docs" / "studies",
        **kwargs,
    )
    return target, paths


def _load_module(path: Path, name: str) -> ModuleType:
    """Import a generated script file as a module."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _fill_minimal(study_dir: Path) -> None:
    """Fill a generated BAA10Y->SPX scaffold with a minimal valid design.

    Values mirror the committed study 003/005 contracts where they
    exist. This is a wiring fill for tests, not a research design.
    """
    design_path = study_dir / "design.json"
    design = json.loads(design_path.read_text(encoding="utf-8"))
    design.update(
        {
            "title": "BAA10Y spread leads S&P 500 daily returns",
            "mechanism": (
                "Wiring-test placeholder: a widening credit spread may "
                "precede equity weakness."
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
                "Rejected when any acceptance criterion fails"
            ],
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
            "cost_model": "OKX VIP0 taker 0.05% per side",
            "cost_assumptions": ["Taker fee 0.05% per side."],
            "multiple_testing_family": "primary lead-lag test only",
            "planned_test_count": 1,
            "known_confounders": ["common market factor"],
            "exclusions": ["none"],
            "random_seed": 1234,
        }
    )
    design_path.write_text(
        json.dumps(design, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for source_id, attribution in (
        ("fred", "Source: Federal Reserve Bank of St. Louis"),
        ("yahoo-finance", "Data: Yahoo Finance"),
    ):
        stub_path = study_dir / "sources" / source_id / "v1.json"
        stub = json.loads(stub_path.read_text(encoding="utf-8"))
        stub.update(
            {
                "attribution": attribution,
                "license_status": "approved",
                "nominal_delay_seconds": 0,
                "permission_basis": "Public data, research use only.",
                "terms_url": "https://example.invalid/terms",
                "timestamp_basis": "Daily values at 21:00 UTC.",
            }
        )
        stub_path.write_text(
            json.dumps(stub, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    (study_dir / "catalog" / "instruments" / "credit%3Abaa-10y-spread").mkdir(
        parents=True, exist_ok=True
    )
    (study_dir / "catalog" / "instruments" / "credit%3Abaa-10y-spread" / "v1.json").write_text(
        json.dumps(
            {
                "instrument_id": "credit:baa-10y-spread",
                "asset_class": "credit",
                "instrument_type": "rate",
                "name": "BAA10Y spread",
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


# --- Spec validation ---


def test_spec_rejects_missing_required_field() -> None:
    with pytest.raises(ValidationError):
        StudySpec(
            study_number=8,
            slug="baa-spx-transmission-008",
            hypothesis_id="H9001",
            source_instrument="credit:baa-10y-spread",
            target_instrument="index:sp500",
            test_type=EdgeTestType.LEAD_LAG,
            frequency="daily",
            # source_ids omitted
            universe=("credit:baa-10y-spread", "index:sp500"),
            calendar_ids=("us-equity",),
            minimum_effect_size=0.005,
            acceptance_criteria=("primary p below 0.05",),
        )


def test_spec_rejects_unknown_test_type() -> None:
    with pytest.raises(ValidationError):
        StudySpec(
            study_number=8,
            slug="baa-spx-transmission-008",
            hypothesis_id="H9001",
            source_instrument="credit:baa-10y-spread",
            target_instrument="index:sp500",
            test_type="granger",  # type: ignore[arg-type]
            frequency="daily",
            source_ids=("fred",),
            universe=("credit:baa-10y-spread", "index:sp500"),
            calendar_ids=("us-equity",),
            minimum_effect_size=0.005,
            acceptance_criteria=("primary p below 0.05",),
        )


def test_spec_rejects_bad_slug_and_number() -> None:
    base: dict[str, Any] = {
        "study_number": 8,
        "slug": "baa-spx-transmission-008",
        "hypothesis_id": "H9001",
        "source_instrument": "credit:baa-10y-spread",
        "target_instrument": "index:sp500",
        "test_type": EdgeTestType.LEAD_LAG,
        "frequency": "daily",
        "source_ids": ("fred",),
        "universe": ("credit:baa-10y-spread", "index:sp500"),
        "calendar_ids": ("us-equity",),
        "minimum_effect_size": 0.005,
        "acceptance_criteria": ("primary p below 0.05",),
    }
    with pytest.raises(ValidationError):
        StudySpec(**{**base, "slug": "baa-spx-transmission-009"})
    with pytest.raises(ValidationError):
        StudySpec(**{**base, "slug": "BAA-spx-008"})
    with pytest.raises(ValidationError):
        StudySpec(**{**base, "study_number": 0})
    with pytest.raises(ValidationError):
        StudySpec(**{**base, "study_number": 1000})
    with pytest.raises(ValidationError):
        StudySpec(**{**base, "hypothesis_id": "H13"})


def test_spec_rejects_mismatched_pair_for_test_type() -> None:
    base: dict[str, Any] = {
        "study_number": 8,
        "slug": "baa-spx-transmission-008",
        "hypothesis_id": "H9001",
        "frequency": "daily",
        "source_ids": ("fred",),
        "calendar_ids": ("us-equity",),
        "minimum_effect_size": 0.005,
        "acceptance_criteria": ("primary p below 0.05",),
    }
    # lead-lag needs two distinct instruments.
    with pytest.raises(ValidationError):
        StudySpec(
            **base,
            source_instrument="index:sp500",
            target_instrument="index:sp500",
            test_type=EdgeTestType.LEAD_LAG,
            universe=("index:sp500",),
        )
    # mean comparison needs a self-loop.
    with pytest.raises(ValidationError):
        StudySpec(
            **base,
            source_instrument="credit:baa-10y-spread",
            target_instrument="index:sp500",
            test_type=EdgeTestType.MEAN_COMPARISON,
            universe=("credit:baa-10y-spread", "index:sp500"),
        )


def test_spec_rejects_duplicates_and_bad_ids() -> None:
    base: dict[str, Any] = {
        "study_number": 8,
        "slug": "baa-spx-transmission-008",
        "hypothesis_id": "H9001",
        "source_instrument": "credit:baa-10y-spread",
        "target_instrument": "index:sp500",
        "test_type": EdgeTestType.LEAD_LAG,
        "frequency": "daily",
        "source_ids": ("fred", "yahoo-finance"),
        "universe": ("credit:baa-10y-spread", "index:sp500"),
        "calendar_ids": ("us-equity",),
        "minimum_effect_size": 0.005,
        "acceptance_criteria": ("primary p below 0.05",),
    }
    with pytest.raises(ValidationError):
        StudySpec(**{**base, "source_ids": ("fred", "fred")})
    with pytest.raises(ValidationError):
        StudySpec(**{**base, "universe": ("credit:baa-10y-spread",)})
    with pytest.raises(ValidationError):
        StudySpec(**{**base, "minimum_effect_size": 0})
    with pytest.raises(ValidationError):
        StudySpec(
            **{
                **base,
                "universe": ("credit:baa-10y-spread", "Index:SP500"),
                "target_instrument": "Index:SP500",
            }
        )
    with pytest.raises(ValidationError):
        StudySpec(**{**base, "calendar_ids": ("US-Equity",)})


# --- Planner input ---


def test_planner_draft_maps_known_fields_and_keeps_todos() -> None:
    spec = _baa_spx_spec()
    assert spec.source_instrument == "credit:baa-10y-spread"
    assert spec.target_instrument == "index:sp500"
    assert spec.test_type == EdgeTestType.LEAD_LAG
    assert spec.frequency.value == "daily"
    assert spec.minimum_effect_size == 0.005
    assert spec.planner_rank == 1
    assert spec.planner_total_score == 1.0
    assert spec.estimated_joint_rows == 5967
    assert spec.adjacent_supported_edges == ("E0026",)
    assert spec.decision_records == ("DR-E0026",)
    # TODO fields stay TODO (None on the spec), never silently filled.
    assert spec.research_question is not None
    assert spec.model_definition[1].startswith("TODO")
    assert "TODO" in spec.acceptance_criteria[3]


def test_planner_draft_rejects_bad_input() -> None:
    draft = _load_template()
    with pytest.raises(ValueError, match="draft=true"):
        spec_from_planner_draft(
            {**draft, "draft": False},
            study_number=8,
            slug="baa-spx-transmission-008",
            hypothesis_id="H9001",
            source_ids=("fred",),
            calendar_ids=("us-equity",),
        )
    with pytest.raises(ValueError, match="unknown suggested test type"):
        spec_from_planner_draft(
            {**draft, "suggested_test_type": "granger"},
            study_number=8,
            slug="baa-spx-transmission-008",
            hypothesis_id="H9001",
            source_ids=("fred",),
            calendar_ids=("us-equity",),
        )
    with pytest.raises(ValueError, match="two-instrument list"):
        spec_from_planner_draft(
            {**draft, "universe": ["credit:baa-10y-spread"]},
            study_number=8,
            slug="baa-spx-transmission-008",
            hypothesis_id="H9001",
            source_ids=("fred",),
            calendar_ids=("us-equity",),
        )


# --- Generation: determinism, guards, structure ---


def test_generation_is_deterministic(tmp_path: Path) -> None:
    spec = _baa_spx_spec()
    _, first = _generate(spec, tmp_path / "a")
    _, second = _generate(spec, tmp_path / "b")
    assert [p.name for p in first] == [p.name for p in second]
    assert len(first) == len(second) == 13
    for left, right in zip(first, second, strict=True):
        assert left.read_bytes() == right.read_bytes()


def test_generation_guards(tmp_path: Path) -> None:
    spec = _baa_spx_spec()
    target, _ = _generate(spec, tmp_path)
    with pytest.raises(ScaffoldError, match="already exists"):
        generate(
            spec,
            target=target,
            known_source_ids=KNOWN_SOURCES,
            docs_root=tmp_path / "docs" / "studies",
        )
    with pytest.raises(ScaffoldError, match="unknown source"):
        generate(
            _baa_spx_spec(source_ids=("fred", "no-such-source")),
            target=tmp_path / "research" / "other-study-008",
            known_source_ids=KNOWN_SOURCES,
            docs_root=tmp_path / "docs" / "studies",
        )
    with pytest.raises(ScaffoldError, match="directly under research"):
        generate(
            spec,
            target=tmp_path / "elsewhere" / spec.slug,
            known_source_ids=KNOWN_SOURCES,
            docs_root=tmp_path / "docs" / "studies",
        )


def test_generation_report_guard(tmp_path: Path) -> None:
    spec = _baa_spx_spec()
    docs_root = tmp_path / "docs" / "studies"
    docs_root.mkdir(parents=True)
    (docs_root / f"{spec.slug}.md").write_text("existing report\n")
    with pytest.raises(ScaffoldError, match="report already exists"):
        generate(
            spec,
            target=tmp_path / "research" / spec.slug,
            known_source_ids=KNOWN_SOURCES,
            docs_root=docs_root,
        )


def test_generation_structure_complete(tmp_path: Path) -> None:
    spec = _baa_spx_spec()
    target, paths = _generate(spec, tmp_path)
    expected = {
        "README.md",
        "spec.json",
        "design.json",
        "preregister.py",
        "fetch_data.py",
        "run_trial.py",
        "hypotheses/registrations/H9001/draft.json",
        "sources/fred/v1.json",
        "sources/yahoo-finance/v1.json",
        "catalog/instruments/credit%3Abaa-10y-spread/v1.json",
        "catalog/instruments/index%3Asp500/v1.json",
        "catalog/calendars/us-equity/v1.json",
    }
    found = {
        str(path.relative_to(target))
        for path in paths
        if path.is_relative_to(target)
    }
    assert found == expected
    assert (tmp_path / "docs" / "studies" / f"{spec.slug}.md").exists()
    # The scaffold starts nothing: no ledger, no manifest, no panel.
    assert not (target / "trials.jsonl").exists()
    assert not (target / "manifest.json").exists()
    # The draft is parked, not registered: the registry sees no versions.
    registry = HypothesisRegistry(target / "hypotheses")
    assert registry._versions("H9001") == []


def test_generated_python_files_compile_and_carry_todos(
    tmp_path: Path,
) -> None:
    spec = _baa_spx_spec()
    target, _ = _generate(spec, tmp_path)
    for name in ("preregister.py", "fetch_data.py", "run_trial.py"):
        source = (target / name).read_text(encoding="utf-8")
        compile(source, str(target / name), "exec")
    run_trial = (target / "run_trial.py").read_text(encoding="utf-8")
    assert "TODO: the purged walk-forward" in run_trial
    assert "TODO: the cost gate" in run_trial
    design = json.loads((target / "design.json").read_text(encoding="utf-8"))
    assert design["mechanism"] == "TODO"
    assert design["title"] == "TODO"
    draft = json.loads(
        (
            target / "hypotheses" / "registrations" / "H9001" / "draft.json"
        ).read_text(encoding="utf-8")
    )
    assert draft["draft"] is True
    assert draft["model_definition"][1].startswith("TODO")


def test_source_metadata_loader() -> None:
    metadata = load_source_metadata(EVIDENCE_REGISTRY)
    assert len(metadata) == 8
    assert metadata["fred"][0] == "Federal Reserve Bank of St. Louis (FRED)"
    assert set(metadata) == KNOWN_SOURCES


# --- Generated preregister ---


def test_generated_preregister_refuses_then_registers(
    tmp_path: Path,
) -> None:
    spec = _baa_spx_spec()
    target, _ = _generate(spec, tmp_path)
    module = _load_module(target / "preregister.py", "scaffold_preregister")
    missing = module.find_todos()
    assert missing
    assert "design.json: mechanism" in missing
    assert "design.json: title" in missing
    assert "design.json: train_window.start" in missing
    assert "sources/fred/v1.json: permission_basis" in missing
    assert "design.json: trial_id" not in missing

    _fill_minimal(target)
    assert module.find_todos() == []
    module.main()
    registry = HypothesisRegistry(target / "hypotheses")
    registration = registry.get("H9001", version=1)
    assert registration.version == 1
    fingerprint = hashlib.sha256(
        canonical_json(registration.spec.model_dump(mode="json"))
    ).hexdigest()
    assert fingerprint == registration.spec_fingerprint


# --- Generated fetch skeleton ---


def test_generated_fetch_source_inference(tmp_path: Path) -> None:
    spec = _baa_spx_spec()
    target, _ = _generate(spec, tmp_path)
    module = _load_module(target / "fetch_data.py", "scaffold_fetch")
    fred_instrument = Instrument(
        instrument_id="credit:baa-10y-spread",
        asset_class="credit",
        instrument_type="rate",
        name="BAA10Y spread",
        quote_currency="percent",
        calendar_id="us-equity",
        metadata={"fred_series": "BAA10Y"},
    )
    assert module._source_for_instrument(fred_instrument) == "fred"
    ambiguous = Instrument(
        instrument_id="credit:baa-10y-spread",
        asset_class="credit",
        instrument_type="rate",
        name="BAA10Y spread",
        quote_currency="percent",
        calendar_id="us-equity",
        metadata={"fred_series": "BAA10Y", "yahoo_symbol": "^GSPC"},
    )
    with pytest.raises(ValueError, match="several sources"):
        module._source_for_instrument(ambiguous)
    unknown = Instrument(
        instrument_id="credit:baa-10y-spread",
        asset_class="credit",
        instrument_type="rate",
        name="BAA10Y spread",
        quote_currency="percent",
        calendar_id="us-equity",
        metadata={},
    )
    with pytest.raises(ValueError, match="no known venue"):
        module._source_for_instrument(unknown)


def test_generated_fetch_fails_fast_on_todo_source(tmp_path: Path) -> None:
    spec = StudySpec(
        study_number=11,
        slug="cpi-cross-section-011",
        hypothesis_id="H0016",
        source_instrument="rates:dgs10",
        target_instrument="macro:cpi",
        test_type=EdgeTestType.CROSS_SECTION,
        frequency="daily",
        source_ids=("fred", "bls"),
        universe=("rates:dgs10", "macro:cpi"),
        calendar_ids=("us-equity",),
        minimum_effect_size=0.05,
        acceptance_criteria=("cross-section R2 at least 0.05",),
    )
    target, _ = _generate(spec, tmp_path)
    module = _load_module(target / "fetch_data.py", "scaffold_fetch_bls")
    assert module.TODO_SOURCES == ("bls",)
    with pytest.raises(NotImplementedError, match="no implemented fetcher"):
        module.main()


# --- Synthetic wiring ---


def test_generated_run_trial_wiring(tmp_path: Path, monkeypatch: Any) -> None:
    spec = _baa_spx_spec()
    study_dir, _ = _generate(spec, tmp_path)
    _fill_minimal(study_dir)
    preregister = _load_module(
        study_dir / "preregister.py", "scaffold_preregister_wiring"
    )
    preregister.main()

    # Fixed-seed synthetic panel: independent random walks, 100 daily bars.
    fetched_at = datetime(2026, 11, 19, 0, 0, tzinfo=UTC)
    rng = np.random.default_rng(7)
    n = 100
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
        tmp_path / "data" / "cache" / spec.slug / "pit-1d", registry
    )
    store.write_batch(observations)
    (study_dir / "manifest.json").write_text(
        json.dumps(
            {
                "study": spec.slug,
                "fetched_at": fetched_at.isoformat(),
                "note": "SYNTHETIC wiring panel (seed 7); not real data.",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    run_trial = _load_module(study_dir / "run_trial.py", "scaffold_run_trial")
    monkeypatch.setattr(
        run_trial, "git_head_revision", lambda root: "test-revision"
    )
    run_trial.main()

    records = read_and_verify(study_dir / "trials.jsonl")
    assert len(records) == 1
    record = records[0]
    assert record["trial_id"] == "T9001"
    assert record["status"] == "completed"
    metrics = record["result"]["metrics"]
    assert metrics["tests"]["primary"]["observations"] == 98
    assert metrics["verdict"]["supported"] is False
