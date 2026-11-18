"""Renderers for the files the scaffold generates.

Every renderer is a pure function of a :class:`StudySpec` (plus, for
source stubs, the 6b registry metadata): no clocks, no network, no
mutable defaults. The generator sorts the file list and writes JSON
with sorted keys, so the same spec always produces byte-identical
output.

Generated Python files use distinctive ``__TOKEN__`` placeholders
replaced with ``str.replace`` — never ``str.format`` — so the braces in
the generated code survive untouched.

The generated files follow one rule throughout: the scaffold wires
structure and never designs. Anything a researcher must decide is a
literal ``"TODO"`` in a JSON file or a ``TODO`` comment / raised
``NotImplementedError`` in a Python file, and the generated
``preregister.py`` refuses to register until every TODO is resolved.
"""

from __future__ import annotations

import json
import textwrap
from urllib.parse import quote

from myquant.scaffolding.spec import TODO, StudySpec

#: Test-type label used in the generated README and report.
_TEST_TYPE_LABELS = {
    "lead_lag": "lead-lag transmission",
    "mean_comparison": "mean comparison (window level)",
    "event_study": "event study",
    "cross_section": "cross-sectional regression",
}

#: Venue string per source id (the venue recorded on observations).
_SOURCE_VENUES = {
    "okx-public": "okx",
    "deribit": "deribit",
    "fred": "fred",
    "yahoo-finance": "yahoo",
    "fiscaldata": "fiscaldata",
    "federalreserve": "federalreserve",
    "bls": "bls",
    "hyperliquid": "hyperliquid",
}

#: Catalog metadata key that identifies an instrument's venue id,
#: per source id. The generated fetch skeleton reads this key from
#: the instrument stub; an instrument with no known key (or several)
#: is refused, not guessed.
_SOURCE_METADATA_KEYS = {
    "okx-public": "okx_inst_id",
    "deribit": "deribit_currency",
    "fred": "fred_series",
    "yahoo-finance": "yahoo_symbol",
    "hyperliquid": "hyperliquid_coin",
}

#: Sources with no adapter fetch helper in the repo. The generated
#: fetch skeleton raises NotImplementedError for them, pointing at
#: the study that fetched that source by hand.
_UNIMPLEMENTED_SOURCES = {
    "fiscaldata": "study 006 (research/macro-windows-006/fetch_data.py)",
    "federalreserve": "study 005 (research/fomc-event-study-005/fetch_data.py)",
    "bls": "study 006 (research/macro-windows-006/fetch_data.py)",
}


def dumps_json(value: object) -> str:
    """Canonical JSON for generated files: sorted keys, 2-space indent."""
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def render_literal(value: tuple[str, ...] | dict[str, str]) -> str:
    """A Python literal for a generated file, kept within 100 columns.

    Short values render on one line; long ones render one item per
    line so the generated file passes the repo's ruff line-length
    rule without the researcher reformatting it.
    """
    one_line = repr(value)
    if len(one_line) <= 76:
        return one_line
    if isinstance(value, tuple):
        items = "".join(f"    {item!r},\n" for item in value)
        return f"(\n{items})"
    items = "".join(f"    {key!r}: {item!r},\n" for key, item in value.items())
    return f"{{\n{items}}}"


def test_type_label(spec: StudySpec) -> str:
    """Human-readable label for the spec's test type."""
    return _TEST_TYPE_LABELS[spec.test_type.value]


def quoted_catalog_key(key: str) -> str:
    """The on-disk directory name for a catalog key (matches MarketCatalog)."""
    return quote(key, safe="")


def render_design_json(spec: StudySpec) -> str:
    """The design document the generated preregister.py reads.

    Filled fields come from the spec (or, for the purge gap, from the
    spec horizon: the purge gap equals the horizon, the minimum the
    validator allows — the researcher may raise it, never lower it).
    Every other design decision is a literal "TODO" until the
    researcher fills it in. The generated preregister.py scans this
    file first and refuses to register while any TODO remains.
    """
    design: dict[str, object] = {
        "study_number": spec.study_number,
        "slug": spec.slug,
        "design_note": (
            "Fill every TODO, then run preregister.py. "
            "Nothing in this file is registered until that script "
            "succeeds; the scaffold chose none of these values."
        ),
        "hypothesis_id": spec.hypothesis_id,
        "title": TODO,
        "trial_id": spec.trial_id if spec.trial_id is not None else TODO,
        "research_question": spec.research_question or TODO,
        "mechanism": TODO,
        "null_hypothesis": spec.null_hypothesis or TODO,
        "alternative_hypothesis": spec.alternative_hypothesis or TODO,
        "source_instrument": spec.source_instrument,
        "target_instrument": spec.target_instrument,
        "universe": list(spec.universe),
        "target_definition": spec.target_definition or TODO,
        "observation_frequency": spec.frequency.value,
        "horizon_seconds": spec.horizon_seconds,
        "test_type": spec.test_type.value,
        "model_definition": (
            list(spec.model_definition) if spec.model_definition else [TODO]
        ),
        "feature_set": [TODO],
        "fixed_parameters": [TODO],
        "source_versions": [f"{source_id}@v1" for source_id in spec.source_ids],
        "train_window": {"start": TODO, "end": TODO},
        "validation_window": {"start": TODO, "end": TODO},
        "holdout_window": {"start": TODO, "end": TODO},
        "purge_gap_seconds": spec.horizon_seconds,
        "purge_gap_note": (
            "The purge gap equals the horizon (the minimum the "
            "validator allows). Raise it if the design needs a "
            "longer embargo; never lower it."
        ),
        "minimum_train_observations": TODO,
        "minimum_validation_observations": TODO,
        "minimum_holdout_observations": TODO,
        "minimum_effect_size": spec.minimum_effect_size,
        "primary_metric": spec.primary_metric or TODO,
        "expected_direction": TODO,
        "benchmark": TODO,
        "cost_model": TODO,
        "cost_assumptions": [TODO],
        "multiple_testing_method": spec.multiple_testing_method or TODO,
        "multiple_testing_family": TODO,
        "planned_test_count": TODO,
        "target_error_rate": (
            spec.target_error_rate
            if spec.target_error_rate is not None
            else TODO
        ),
        "missing_data_policy": spec.missing_data_policy or TODO,
        "known_confounders": [TODO],
        "exclusions": [TODO],
        "random_seed": TODO,
        "acceptance_criteria": list(spec.acceptance_criteria),
        "rejection_criteria": (
            list(spec.rejection_criteria) if spec.rejection_criteria else [TODO]
        ),
    }
    return dumps_json(design)


def render_draft_json(spec: StudySpec) -> str:
    """The planner-draft-format JSON parked under hypotheses/registrations/.

    It mirrors the 6a draft format key for key, with the spec's known
    fields filled and every design field TODO. The hypothesis registry
    only globs ``v*.json`` under a registration directory, so this
    ``draft.json`` is invisible to it: it is a parked draft, not a
    registration.
    """
    draft: dict[str, object] = {
        "schema_version": 1,
        "draft": True,
        "draft_note": (
            "DRAFT generated by the Stage 6c scaffold from the study "
            "spec. Not a registration: the hypothesis registry only "
            "reads v*.json files. Fill the TODOs, then run "
            "preregister.py to register."
        ),
        "planner_rank": spec.planner_rank,
        "planner_total_score": spec.planner_total_score,
        "suggested_test_reason": spec.suggested_test_reason,
        "adjacent_supported_edges": list(spec.adjacent_supported_edges),
        "decision_records": list(spec.decision_records),
        "planner_notes": list(spec.planner_notes),
        "title": TODO,
        "hypothesis_id": spec.hypothesis_id,
        "research_question": spec.research_question or TODO,
        "mechanism": TODO,
        "null_hypothesis": spec.null_hypothesis or TODO,
        "alternative_hypothesis": spec.alternative_hypothesis or TODO,
        "universe": list(spec.universe),
        "target_definition": spec.target_definition or TODO,
        "observation_frequency": spec.frequency.value,
        "horizon_seconds": spec.horizon_seconds,
        "suggested_test_type": spec.test_type.value,
        "model_definition": (
            list(spec.model_definition) if spec.model_definition else [TODO]
        ),
        "feature_set": [TODO],
        "fixed_parameters": [TODO],
        "source_versions": [f"{source_id}@v1" for source_id in spec.source_ids],
        "sample_period": {
            "estimated_joint_rows": spec.estimated_joint_rows,
            "estimated_joint_rows_basis": spec.estimated_joint_rows_basis,
            "note": (
                "Planner estimate only (pro-rata by days or calendar "
                "count). Verify the actual joint count from the "
                "fetched panel before registering."
            ),
        },
        "train_window": {"start": TODO, "end": TODO},
        "validation_window": {"start": TODO, "end": TODO},
        "holdout_window": {"start": TODO, "end": TODO},
        "purge_gap_seconds": spec.horizon_seconds,
        "minimum_train_observations": TODO,
        "minimum_validation_observations": TODO,
        "minimum_holdout_observations": TODO,
        "minimum_effect_size": spec.minimum_effect_size,
        "primary_metric": spec.primary_metric or TODO,
        "expected_direction": TODO,
        "benchmark": TODO,
        "cost_model": TODO,
        "cost_assumptions": [TODO],
        "multiple_testing_method": spec.multiple_testing_method or TODO,
        "multiple_testing_family": TODO,
        "planned_test_count": TODO,
        "target_error_rate": (
            spec.target_error_rate
            if spec.target_error_rate is not None
            else TODO
        ),
        "missing_data_policy": spec.missing_data_policy or TODO,
        "known_confounders": [TODO],
        "exclusions": [TODO],
        "random_seed": TODO,
        "acceptance_criteria": list(spec.acceptance_criteria),
        "rejection_criteria": (
            list(spec.rejection_criteria) if spec.rejection_criteria else [TODO]
        ),
    }
    return dumps_json(draft)


def render_source_stub(
    source_id: str, metadata: tuple[str, str] | None
) -> str:
    """A source contract stub. Only SourceDefinition fields appear.

    Provider and description come from the 6b registry when the
    generator knows them; everything a researcher must decide is
    TODO, and the license stays "unknown" until the researcher sets
    "approved" with a permission basis. The stub is not a valid
    contract until every TODO is resolved.
    """
    provider, description = metadata if metadata is not None else (TODO, TODO)
    stub: dict[str, object] = {
        "attribution": TODO,
        "description": description,
        "license_status": "unknown",
        "nominal_delay_seconds": TODO,
        "permission_basis": TODO,
        "provider": provider,
        "source_id": source_id,
        "terms_url": TODO,
        "timestamp_basis": TODO,
    }
    return dumps_json(stub)


def render_instrument_stub(instrument_id: str) -> str:
    """An instrument contract stub. Only Instrument fields appear.

    The researcher fills the classification, name, quote currency,
    calendar, and the venue metadata key the fetch skeleton reads
    (``fred_series``, ``yahoo_symbol``, ``okx_inst_id``,
    ``deribit_currency`` or ``hyperliquid_coin``).
    """
    stub: dict[str, object] = {
        "asset_class": TODO,
        "calendar_id": TODO,
        "instrument_id": instrument_id,
        "instrument_type": TODO,
        "metadata": {},
        "name": TODO,
        "quote_currency": TODO,
    }
    return dumps_json(stub)


def render_calendar_stub(calendar_id: str) -> str:
    """A calendar contract stub. Only MarketCalendar fields appear."""
    stub: dict[str, object] = {
        "calendar_id": calendar_id,
        "close_day_offset": TODO,
        "early_closes": {},
        "holidays": [],
        "open_day_offset": TODO,
        "regular_close": TODO,
        "regular_open": TODO,
        "timezone_name": TODO,
        "weekdays": TODO,
    }
    return dumps_json(stub)


def render_readme(spec: StudySpec) -> str:
    """The study README: question, design, data, results — all TODO."""
    universe_lines = "\n".join(f"- `{instrument}`" for instrument in spec.universe)
    source_lines = "\n".join(f"- `{source_id}`" for source_id in spec.source_ids)
    calendar_lines = "\n".join(
        f"- `{calendar_id}`" for calendar_id in spec.calendar_ids
    )
    criteria_lines = "\n".join(
        f"{index + 1}. {criterion}"
        for index, criterion in enumerate(spec.acceptance_criteria)
    )
    planner_block = ""
    if spec.planner_rank is not None:
        planner_block = (
            f"\nPlanner rank: {spec.planner_rank}"
            + (
                f" (total score {spec.planner_total_score:.2f})"
                if spec.planner_total_score is not None
                else ""
            )
            + ".\n"
        )
    return f"""# Study {spec.study_number:03d}: {spec.slug}

TODO: one-paragraph summary of the study once the design is settled.

> Scaffold note: this directory was generated by the Stage 6c
> experiment assistant. The scaffold wires structure; it does not
> design. Nothing here is registered, fetched, or tested until the
> researcher fills the TODOs and runs the scripts below, in order:
>
> 1. Fill `design.json`, the `sources/` stubs, and the `catalog/` stubs.
> 2. Run `preregister.py` — it refuses while any TODO remains.
> 3. Run `fetch_data.py` — it fetches only the registered sample window.
> 4. Fill the design sections of `run_trial.py`, then run it.
>
> The study starts when the hypothesis is registered, not when this
> directory is generated.

## Question

{spec.research_question or "TODO: the research question."}

- Hypothesis: `{spec.hypothesis_id}`
- Test: {test_type_label(spec)} ({spec.test_type.value}), {spec.frequency.value}
- Source: `{spec.source_instrument}`
- Target: `{spec.target_instrument}`
{planner_block}
## Design

TODO: the mechanism, the model, the windows, the benchmark, and the
rejection criteria. The full design lives in `design.json`; this
section is the human-readable summary of it.

Minimum effect size: `{spec.minimum_effect_size}` (from the study
spec — the scaffold wrote it verbatim, it chose nothing).

Acceptance criteria (from the study spec):

{criteria_lines}

## Data

Universe:

{universe_lines}

Sources:

{source_lines}

Calendars:

{calendar_lines}

TODO: the sample window, the per-source quirks found while fetching,
and the freshness of each panel. Fetch conventions: the fetch skeleton
infers each instrument's source from its catalog metadata key
(`fred_series`, `yahoo_symbol`, `okx_inst_id`, `deribit_currency`,
`hyperliquid_coin`); an instrument with no known key — or several —
is refused. Point-in-time correctness is enforced by the PIT store:
observations are usable only after their `available_at`.

## Results

TODO: the trial outcome, once the trial has run. Report effect sizes
and uncertainty, not just p-values. Record failed trials in the ledger
alongside the successful ones.

## Files

- `spec.json` — the scaffold spec this directory was generated from.
- `design.json` — the preregistration design (TODO until filled).
- `preregister.py` — registers the hypothesis (refuses while TODOs remain).
- `fetch_data.py` — fetches the registered sample window.
- `run_trial.py` — runs the trial (design sections marked TODO).
- `sources/`, `catalog/` — contract stubs (TODO until filled).
- `hypotheses/registrations/{spec.hypothesis_id}/draft.json` — the parked
  planner draft. Not a registration.
- `trials.jsonl`, `manifest.json`, `panel-summary.json` — created by
  the fetch and trial scripts, not by the scaffold.
"""


def render_report_template(spec: StudySpec) -> str:
    """The `docs/studies/<slug>.md` report template."""
    return f"""# Study {spec.study_number:03d}: {spec.slug}

TODO: the study report. Write it after the trial runs; do not write
results before the hypothesis is registered.

- Hypothesis: `{spec.hypothesis_id}`
- Test: {test_type_label(spec)} ({spec.test_type.value}), {spec.frequency.value}
- Source: `{spec.source_instrument}`
- Target: `{spec.target_instrument}`
- Minimum effect size: `{spec.minimum_effect_size}`

## Design

TODO: the preregistered design (windows, model, fixed parameters,
acceptance criteria). Link the spec fingerprint once registered.

## Data

TODO: sources, sample window, panel counts, quirks found while
fetching.

## Results

TODO: the primary test, the secondary tests, the holdout evaluation,
the cost gate. Effect sizes and uncertainty, not just p-values.

## Verdict

TODO: SUPPORTED or REJECTED, with the criterion that decided it.

## Limitations

TODO: what this study cannot say.
"""


#: The generated preregister.py. Tokens are replaced with str.replace
#: (never str.format, so braces in the generated code are safe).
_PREREGISTER_TEMPLATE = '''"""Preregister the hypothesis for study __SLUG__.

Generated by the Stage 6c experiment assistant. The design lives in
``design.json`` next to this script; fill every TODO there (and in the
``sources/`` and ``catalog/`` stubs) before running this script. The
script refuses to register while any TODO remains, and lists exactly
what is missing.

Registration itself goes through the repo's HypothesisRegistry: the
spec is validated, fingerprinted, and written as an immutable v1
snapshot with a hash-chained lifecycle event. This script invents no
registration machinery of its own.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from myquant.canonical import canonical_json
from myquant.catalog import MarketCatalog
from myquant.hypotheses import (
    ExpectedDirection,
    HypothesisRegistry,
    HypothesisSpec,
    MultiplicityCorrection,
    SampleWindow,
)
from myquant.sources import SourceRegistry

ROOT = Path(__file__).resolve().parent
DESIGN_PATH = ROOT / "design.json"

HYPOTHESIS_ID = "__HYPOTHESIS_ID__"
SOURCE_IDS = __SOURCE_IDS__
INSTRUMENT_IDS = __INSTRUMENT_IDS__
CALENDAR_IDS = __CALENDAR_IDS__
#: Contract stub files (relative to the study dir) scanned for TODOs.
STUB_FILES = __STUB_FILES__

#: Design fields preregistration does not need: the trial id is a
#: run_trial concern, not a registration concern, so a TODO trial id
#: does not block registration.
DESIGN_TODO_EXCLUSIONS = frozenset({"trial_id", "design_note", "purge_gap_note"})


def _todo_paths(value: Any, prefix: str) -> list[str]:
    """JSON paths whose string value still contains TODO (sorted)."""
    found: list[str] = []
    if isinstance(value, str) and "TODO" in value:
        found.append(prefix or "<root>")
    elif isinstance(value, dict):
        for key in sorted(value):
            child = f"{prefix}.{key}" if prefix else str(key)
            found.extend(_todo_paths(value[key], child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_todo_paths(item, f"{prefix}[{index}]"))
    return found


def find_todos() -> list[str]:
    """Every unfilled item in design.json and the contract stubs.

    Returns "path: json.path" lines, plus "missing: <path>" for a
    design or stub file that does not exist. An empty list means the
    study is ready to register.
    """
    missing: list[str] = []
    if not DESIGN_PATH.exists():
        return [f"missing: {DESIGN_PATH.relative_to(ROOT)}"]
    design = json.loads(DESIGN_PATH.read_text(encoding="utf-8"))
    if not isinstance(design, dict):
        raise ValueError("design.json must be a JSON object")
    for key in sorted(set(design) - DESIGN_TODO_EXCLUSIONS):
        missing.extend(
            f"design.json: {path}"
            for path in _todo_paths(design[key], str(key))
        )
    for relative in STUB_FILES:
        path = ROOT / relative
        if not path.exists():
            missing.append(f"missing: {relative}")
            continue
        content = json.loads(path.read_text(encoding="utf-8"))
        missing.extend(
            f"{relative}: {found}" for found in _todo_paths(content, "")
        )
    return missing


def _window(value: Any, name: str) -> SampleWindow:
    try:
        start = datetime.fromisoformat(str(value["start"]))
        end = datetime.fromisoformat(str(value["end"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"design {name} must be an object with ISO start/end timestamps"
        ) from exc
    return SampleWindow(start=start, end=end)


def build_spec(design: dict[str, Any]) -> HypothesisSpec:
    """Build the HypothesisSpec from a TODO-free design document."""
    return HypothesisSpec(
        hypothesis_id=design["hypothesis_id"],
        title=design["title"],
        research_question=design["research_question"],
        mechanism=design["mechanism"],
        null_hypothesis=design["null_hypothesis"],
        alternative_hypothesis=design["alternative_hypothesis"],
        universe=tuple(design["universe"]),
        target_definition=design["target_definition"],
        observation_frequency=design["observation_frequency"],
        horizon_seconds=design["horizon_seconds"],
        model_definition=tuple(design["model_definition"]),
        feature_set=tuple(design["feature_set"]),
        fixed_parameters=tuple(design["fixed_parameters"]),
        source_versions=tuple(design["source_versions"]),
        train_window=_window(design["train_window"], "train_window"),
        validation_window=_window(
            design["validation_window"], "validation_window"
        ),
        holdout_window=_window(design["holdout_window"], "holdout_window"),
        purge_gap_seconds=design["purge_gap_seconds"],
        minimum_train_observations=design["minimum_train_observations"],
        minimum_validation_observations=design[
            "minimum_validation_observations"
        ],
        minimum_holdout_observations=design["minimum_holdout_observations"],
        minimum_effect_size=design["minimum_effect_size"],
        primary_metric=design["primary_metric"],
        expected_direction=ExpectedDirection(design["expected_direction"]),
        benchmark=design["benchmark"],
        cost_model=design["cost_model"],
        cost_assumptions=tuple(design["cost_assumptions"]),
        multiple_testing_method=MultiplicityCorrection(
            design["multiple_testing_method"]
        ),
        multiple_testing_family=design["multiple_testing_family"],
        planned_test_count=design["planned_test_count"],
        target_error_rate=design["target_error_rate"],
        missing_data_policy=design["missing_data_policy"],
        known_confounders=tuple(design["known_confounders"]),
        exclusions=tuple(design["exclusions"]),
        random_seed=design["random_seed"],
        acceptance_criteria=tuple(design["acceptance_criteria"]),
        rejection_criteria=tuple(design["rejection_criteria"]),
    )


def validate_stubs() -> None:
    """Load every contract stub through the repo's real validators.

    SourceRegistry.get and MarketCatalog.get_* re-validate the
    contract on read, so a filled stub that violates its schema is
    refused here with the validator's own error. Instrument calendar
    references must resolve to a registered calendar.
    """
    sources = SourceRegistry(ROOT / "sources")
    for source_id in SOURCE_IDS:
        sources.get(source_id, version=1)
    catalog = MarketCatalog(ROOT / "catalog")
    for instrument_id in INSTRUMENT_IDS:
        instrument = catalog.get_instrument(instrument_id, version=1)
        if instrument.calendar_id not in CALENDAR_IDS:
            raise ValueError(
                f"instrument {instrument_id} references calendar "
                f"{instrument.calendar_id!r}, which is not in the study "
                f"calendars {sorted(CALENDAR_IDS)}"
            )
    for calendar_id in CALENDAR_IDS:
        catalog.get_calendar(calendar_id, version=1)


def main() -> None:
    missing = find_todos()
    if missing:
        print("design is incomplete; refusing to register. Missing items:")
        for item in missing:
            print(f"  - {item}")
        raise SystemExit(1)
    design = json.loads(DESIGN_PATH.read_text(encoding="utf-8"))
    validate_stubs()
    spec = build_spec(design)
    registry = HypothesisRegistry(ROOT / "hypotheses")
    registration = registry.register(spec)
    print(f"hypothesis {HYPOTHESIS_ID} registered as v{registration.version}")
    print(f"fingerprint: {registration.spec_fingerprint}")
    print(f"registration hash: {registration.registration_hash}")
    fingerprint = hashlib.sha256(
        canonical_json(spec.model_dump(mode="json"))
    ).hexdigest()
    assert fingerprint == registration.spec_fingerprint


if __name__ == "__main__":
    main()
'''


def render_preregister(spec: StudySpec, stub_files: tuple[str, ...]) -> str:
    """Render the generated preregister.py for a spec."""
    return (
        _PREREGISTER_TEMPLATE.replace("__SLUG__", spec.slug)
        .replace("__HYPOTHESIS_ID__", spec.hypothesis_id)
        .replace("__SOURCE_IDS__", render_literal(tuple(spec.source_ids)))
        .replace("__INSTRUMENT_IDS__", render_literal(tuple(spec.universe)))
        .replace("__CALENDAR_IDS__", render_literal(tuple(spec.calendar_ids)))
        .replace("__STUB_FILES__", render_literal(tuple(stub_files)))
    )


#: OKX bar per scaffold frequency (None = the adapter cannot serve it).
_OKX_BARS = {"daily": "1D", "1h": "1H", "monthly": None}
#: Hyperliquid interval per scaffold frequency.
_HYPERLIQUID_INTERVALS = {"daily": "1d", "1h": "1h", "monthly": None}
#: Adapter module name per source id.
_ADAPTER_MODULES = {
    "okx-public": "okx",
    "deribit": "deribit",
    "fred": "fred",
    "yahoo-finance": "yahoo",
    "hyperliquid": "hyperliquid",
}


def _fetch_function_name(source_id: str) -> str:
    return f"_fetch_{source_id.replace('-', '_')}"


def _fetch_todo_stub(source_id: str, reason: str) -> str:
    lines = textwrap.wrap(reason, width=92)
    docstring = "\n".join(f"    {line}" for line in lines)
    message = "\n".join(f'        "{line} "' for line in lines)
    return f'''def {_fetch_function_name(source_id)}(
    instrument: Instrument,
    *,
    start: datetime,
    end: datetime,
    fetched_at: datetime,
) -> _FetchOutcome:
    """TODO: implement the {source_id} fetch for this study.

{docstring}
    """
    raise NotImplementedError(
        "TODO: {source_id} fetch is not implemented for this study. "
{message}
    )
'''


def _fetch_okx(spec: StudySpec) -> str:
    bar = _OKX_BARS[spec.frequency.value]
    if bar is None:
        return _fetch_todo_stub(
            "okx-public",
            "OKX candles come in fixed bars (1D/1H); monthly bars are "
            "not a native OKX bar, so aggregate daily bars explicitly.",
        )
    return f'''def _fetch_okx_public(
    instrument: Instrument,
    *,
    start: datetime,
    end: datetime,
    fetched_at: datetime,
) -> _FetchOutcome:
    """Fetch confirmed OKX {bar} candles for one instrument."""
    inst_id = _venue_id(instrument, "okx-public")
    result = okx_adapter.fetch_history(
        inst_id,
        "{bar}",
        start=start,
        end=end,
        delay_seconds=0.25,
    )
    pages: list[_Page] = []
    for page in result.pages:
        page_candles = okx_adapter.parse_candles_response(
            page.payload, inst_id=inst_id, bar="{bar}"
        )
        confirmed = [candle for candle in page_candles if candle.confirmed]
        pages.append(
            _Page(
                url=page.url,
                payload=page.payload,
                event_time=confirmed[-1].open_time if confirmed else None,
            )
        )
    observations = okx_adapter.candles_to_observations(
        result.candles,
        instrument_id=instrument.instrument_id,
        venue="okx",
        source_id="okx-public",
        source_version=SOURCE_VERSION,
        ingested_at=fetched_at,
    )
    return _FetchOutcome(
        observations=observations,
        pages=tuple(pages),
        endpoint="https://www.okx.com/api/v5/market/history-candles",
        items=len(result.candles),
        first_event=result.candles[0].open_time if result.candles else None,
        last_event=result.candles[-1].open_time if result.candles else None,
        missing=0,
        fields=("open", "high", "low", "close", "volume"),
    )
'''


def _fetch_fred(spec: StudySpec) -> str:
    if spec.frequency.value != "daily":
        return _fetch_todo_stub(
            "fred",
            "FRED series are dated daily values; the adapter has no "
            "intraday or monthly fetch.",
        )
    return '''def _fetch_fred(
    instrument: Instrument,
    *,
    start: datetime,
    end: datetime,
    fetched_at: datetime,
) -> _FetchOutcome:
    """Fetch one FRED series as dated daily values."""
    series_id = _venue_id(instrument, "fred")
    unit = instrument.quote_currency
    if unit is None:
        raise ValueError(
            f"instrument {instrument.instrument_id} has no quote_currency; "
            "fill the instrument stub"
        )
    series = fred_adapter.fetch_series(
        series_id, start=start.date(), end=end.date()
    )
    # FRED values sit at 21:00 UTC on their date, so the inclusive
    # end date can land past the window end; keep only [start, end).
    observations = [
        observation
        for observation in fred_adapter.series_to_observations(
            series,
            instrument_id=instrument.instrument_id,
            venue="fred",
            source_id="fred",
            source_version=SOURCE_VERSION,
            ingested_at=fetched_at,
            unit=unit,
        )
        if start <= observation.event_time < end
    ]
    return _FetchOutcome(
        observations=observations,
        pages=(
            _Page(
                url=series.url,
                payload=series.payload,
                event_time=observations[-1].event_time
                if observations
                else None,
            ),
        ),
        endpoint="https://fred.stlouisfed.org/graph/fredgraph.csv",
        items=len(series.observations),
        first_event=observations[0].event_time if observations else None,
        last_event=observations[-1].event_time if observations else None,
        missing=series.missing_count,
        fields=("close",),
    )
'''


def _fetch_yahoo(spec: StudySpec) -> str:
    if spec.frequency.value != "daily":
        return _fetch_todo_stub(
            "yahoo-finance",
            "The Yahoo adapter fetches daily bars only; intraday or "
            "monthly panels need a different fetch.",
        )
    return '''def _fetch_yahoo_finance(
    instrument: Instrument,
    *,
    start: datetime,
    end: datetime,
    fetched_at: datetime,
) -> _FetchOutcome:
    """Fetch daily Yahoo bars for one instrument."""
    symbol = _venue_id(instrument, "yahoo-finance")
    unit = instrument.quote_currency
    if unit is None:
        raise ValueError(
            f"instrument {instrument.instrument_id} has no quote_currency; "
            "fill the instrument stub"
        )
    chart = yahoo_adapter.fetch_chart(
        symbol, start=start.date(), end=end.date()
    )
    # Yahoo bars sit at 21:00 UTC on their date, so the inclusive
    # end date can land past the window end; keep only [start, end).
    observations = [
        observation
        for observation in yahoo_adapter.chart_to_observations(
            chart,
            instrument_id=instrument.instrument_id,
            venue="yahoo",
            source_id="yahoo-finance",
            source_version=SOURCE_VERSION,
            ingested_at=fetched_at,
            unit=unit,
        )
        if start <= observation.event_time < end
    ]
    return _FetchOutcome(
        observations=observations,
        pages=(
            _Page(
                url=chart.url,
                payload=chart.payload,
                event_time=observations[-1].event_time
                if observations
                else None,
            ),
        ),
        endpoint="https://query2.finance.yahoo.com/v8/finance/chart",
        items=len(chart.bars),
        first_event=observations[0].event_time if observations else None,
        last_event=observations[-1].event_time if observations else None,
        missing=chart.missing_count,
        fields=("close",),
    )
'''


def _fetch_deribit(spec: StudySpec) -> str:
    if spec.frequency.value != "daily":
        return _fetch_todo_stub(
            "deribit",
            "The Deribit adapter fetches daily DVOL points only "
            "(resolution 86400 s).",
        )
    return '''def _fetch_deribit(
    instrument: Instrument,
    *,
    start: datetime,
    end: datetime,
    fetched_at: datetime,
) -> _FetchOutcome:
    """Fetch daily Deribit DVOL points for one instrument."""
    currency = _venue_id(instrument, "deribit")
    result = deribit_adapter.fetch_volatility_index(
        currency, start=start, end=end, resolution_seconds=86_400
    )
    observations = deribit_adapter.dvol_to_observations(
        result.points,
        instrument_id=instrument.instrument_id,
        venue="deribit",
        source_id="deribit",
        source_version=SOURCE_VERSION,
        ingested_at=fetched_at,
    )
    return _FetchOutcome(
        observations=observations,
        pages=tuple(
            _Page(url=page.url, payload=page.payload, event_time=None)
            for page in result.pages
        ),
        endpoint="https://www.deribit.com/api/v2/public/get_volatility_index_data",
        items=len(result.points),
        first_event=observations[0].event_time if observations else None,
        last_event=observations[-1].event_time if observations else None,
        missing=0,
        fields=("close",),
    )
'''


def _fetch_hyperliquid(spec: StudySpec) -> str:
    interval = _HYPERLIQUID_INTERVALS[spec.frequency.value]
    if interval is None:
        return _fetch_todo_stub(
            "hyperliquid",
            "Hyperliquid candles come in fixed intervals (1d/1h); "
            "monthly candles are not a native interval, so aggregate "
            "daily candles explicitly.",
        )
    return f'''def _fetch_hyperliquid(
    instrument: Instrument,
    *,
    start: datetime,
    end: datetime,
    fetched_at: datetime,
) -> _FetchOutcome:
    """Fetch closed, traded Hyperliquid {interval} candles."""
    coin = _venue_id(instrument, "hyperliquid")
    result = hyperliquid_adapter.fetch_candles(
        coin,
        "{interval}",
        start=start,
        end=end,
        as_of=fetched_at,
    )
    observations = hyperliquid_adapter.candles_to_observations(
        result.candles,
        instrument_id=instrument.instrument_id,
        venue="hyperliquid",
        source_id="hyperliquid",
        source_version=SOURCE_VERSION,
        ingested_at=fetched_at,
        as_of=fetched_at,
    )
    return _FetchOutcome(
        observations=observations,
        pages=tuple(
            _Page(
                url="https://api.hyperliquid.xyz/info "
                "(POST candleSnapshot)",
                payload=page.payload,
                event_time=None,
            )
            for page in result.pages
        ),
        endpoint="https://api.hyperliquid.xyz/info",
        items=len(result.candles),
        first_event=result.candles[0].open_time if result.candles else None,
        last_event=result.candles[-1].open_time if result.candles else None,
        missing=result.excluded_unclosed + result.excluded_zero_trade,
        fields=("open", "high", "low", "close", "volume"),
    )
'''


#: Fetcher builders for sources with an adapter fetch helper.
_FETCHER_BUILDERS = {
    "okx-public": _fetch_okx,
    "fred": _fetch_fred,
    "yahoo-finance": _fetch_yahoo,
    "deribit": _fetch_deribit,
    "hyperliquid": _fetch_hyperliquid,
}


_FETCH_TEMPLATE = '''"""Fetch the registered sample window for study __SLUG__.

Generated by the Stage 6c experiment assistant. Run after
preregistration, from the repo root:

    .venv/bin/python research/__SLUG__/fetch_data.py

The sample window comes from the registered spec: [train start,
holdout end). Raw response pages go to the gitignored cache under
data/cache/__SLUG__/raw/ (content-addressed RawStore); parsed
observations go to data/cache/__SLUG__/__PIT_STORE_NAME__/
(ParquetPITStore). Only the manifest (endpoints, parameters, date
ranges, payload SHA-256) and the panel summary (counts only, no raw
prices) are written into this research directory for commit. Raw
payloads and parquet never leave the local cache.

Each instrument's source is inferred from its catalog metadata key
(see SOURCE_METADATA_KEYS): an instrument with no known key — or
several — is refused, not guessed. Sources without an adapter fetch
helper (see TODO_SOURCES) fail fast before any fetch: implement the
marked fetcher first.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__ADAPTER_IMPORTS__
from myquant.catalog import MarketCatalog
from myquant.contracts import Observation
from myquant.hypotheses import HypothesisRegistry
from myquant.market import Instrument
from myquant.pit import ParquetPITStore
from myquant.quality import SeriesKey, inspect_observations
from myquant.raw import RawStore
from myquant.sources import SourceRegistry

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "__SLUG__"

HYPOTHESIS_ID = "__HYPOTHESIS_ID__"
SOURCE_IDS = __SOURCE_IDS__
INSTRUMENT_IDS = __INSTRUMENT_IDS__
SOURCE_VERSION = 1
PIT_STORE_NAME = "__PIT_STORE_NAME__"

#: Venue recorded on observations, per source id.
SOURCE_VENUES = __SOURCE_VENUES__
#: Catalog metadata key holding the venue identifier, per source id.
SOURCE_METADATA_KEYS = __SOURCE_METADATA_KEYS__
#: Sources with no implemented fetcher in this skeleton.
TODO_SOURCES = __TODO_SOURCES__


@dataclass(frozen=True)
class _Page:
    """One raw response page kept for provenance."""

    url: str
    payload: bytes
    event_time: datetime | None


@dataclass(frozen=True)
class _FetchOutcome:
    """What one per-instrument fetch produced."""

    observations: list[Observation]
    pages: tuple[_Page, ...]
    endpoint: str
    items: int
    first_event: datetime | None
    last_event: datetime | None
    missing: int
    fields: tuple[str, ...]


def _venue_id(instrument: Instrument, source_id: str) -> str:
    """The venue identifier for an instrument, from its catalog metadata."""
    key = SOURCE_METADATA_KEYS[source_id]
    value = instrument.metadata.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(
            f"instrument {instrument.instrument_id} has no catalog metadata "
            f"key {key!r} for source {source_id!r}; fill the instrument stub"
        )
    return value


def _source_for_instrument(instrument: Instrument) -> str:
    """Infer an instrument's source from its catalog metadata keys.

    Exactly one known key must be present. None means the instrument
    stub is unfilled; several means the mapping is ambiguous. Both
    are refused — the scaffold never guesses which source an
    instrument comes from.
    """
    matches = [
        source_id
        for source_id, key in SOURCE_METADATA_KEYS.items()
        if instrument.metadata.get(key)
    ]
    if not matches:
        raise ValueError(
            f"instrument {instrument.instrument_id} has no known venue "
            f"metadata key (expected one of "
            f"{sorted(SOURCE_METADATA_KEYS.values())}); fill the stub"
        )
    if len(matches) > 1:
        raise ValueError(
            f"instrument {instrument.instrument_id} matches several sources "
            f"{sorted(matches)}; leave exactly one venue metadata key"
        )
    return matches[0]


__FETCHERS__

FETCHERS: dict[str, Callable[..., _FetchOutcome]] = __FETCHERS_MAP__


def _fetch_one(
    instrument_id: str,
    start: datetime,
    end: datetime,
    *,
    catalog: MarketCatalog,
    raw_store: RawStore,
    pit_store: ParquetPITStore,
    fetched_at: datetime,
) -> dict[str, Any]:
    instrument = catalog.get_instrument(instrument_id, version=1)
    source_id = _source_for_instrument(instrument)
    if source_id not in SOURCE_IDS:
        raise ValueError(
            f"instrument {instrument_id} maps to source {source_id!r}, "
            f"which is not in the study sources {sorted(SOURCE_IDS)}"
        )
    outcome = FETCHERS[source_id](
        instrument, start=start, end=end, fetched_at=fetched_at
    )
    page_entries: list[dict[str, str]] = []
    for page in outcome.pages:
        record = raw_store.put(
            page.payload,
            source_id=source_id,
            available_at=fetched_at,
            content_type="application/json",
            source_version=SOURCE_VERSION,
            event_time=page.event_time,
            ingested_at=fetched_at,
        )
        page_entries.append(
            {
                "url": page.url,
                "payload_sha256": record.payload_sha256,
                "record_id": record.record_id,
            }
        )
    parquet_path = pit_store.write_batch(outcome.observations)
    return {
        "instrument_id": instrument_id,
        "source_id": source_id,
        "venue": SOURCE_VENUES[source_id],
        "venue_id": _venue_id(instrument, source_id),
        "endpoint": outcome.endpoint,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "items": outcome.items,
        "first_event": (
            outcome.first_event.isoformat() if outcome.first_event else None
        ),
        "last_event": (
            outcome.last_event.isoformat() if outcome.last_event else None
        ),
        "missing": outcome.missing,
        "fields": list(outcome.fields),
        "pages": page_entries,
        "pit_store": PIT_STORE_NAME,
        "pit_parquet": parquet_path.name,
        "pit_parquet_sha256": parquet_path.stem,
        "observation_rows": len(outcome.observations),
    }


def main() -> None:
    if TODO_SOURCES:
        raise NotImplementedError(
            "TODO: these sources have no implemented fetcher in this "
            f"skeleton: {sorted(TODO_SOURCES)}. Implement the marked "
            "fetch functions before fetching."
        )
    registry = HypothesisRegistry(ROOT / "hypotheses")
    spec = registry.get(HYPOTHESIS_ID, version=1).spec
    start = spec.train_window.start
    end = spec.holdout_window.end
    if end <= start:
        raise ValueError("registered sample window is empty")

    fetched_at = datetime.now(UTC)
    raw_store = RawStore(CACHE_ROOT / "raw")
    source_registry = SourceRegistry(ROOT / "sources")
    for source_id in SOURCE_IDS:
        source_registry.require_research_permission(
            source_id, version=SOURCE_VERSION
        )
    pit_store = ParquetPITStore(CACHE_ROOT / PIT_STORE_NAME, source_registry)
    catalog = MarketCatalog(ROOT / "catalog")

    fetches: list[dict[str, Any]] = []
    for instrument_id in INSTRUMENT_IDS:
        entry = _fetch_one(
            instrument_id,
            start,
            end,
            catalog=catalog,
            raw_store=raw_store,
            pit_store=pit_store,
            fetched_at=fetched_at,
        )
        fetches.append(entry)
        print(
            f"{instrument_id} ({entry['source_id']}): {entry['items']} items, "
            f"{entry['observation_rows']} observations, "
            f"{entry['missing']} missing, {len(entry['pages'])} pages"
        )

    observations = pit_store.query_as_of(fetched_at)
    expected_series: set[SeriesKey] = {
        (
            entry["instrument_id"],
            entry["venue"],
            field,
            entry["source_id"],
            SOURCE_VERSION,
        )
        for entry in fetches
        for field in entry["fields"]
    }
    report = inspect_observations(
        observations, expected_series=expected_series
    )
    quality = {
        "row_count": report.row_count,
        "unique_series_count": report.unique_series_count,
        "unique_instrument_count": report.unique_instrument_count,
        "event_time_min": (
            report.event_time_min.isoformat() if report.event_time_min else None
        ),
        "event_time_max": (
            report.event_time_max.isoformat() if report.event_time_max else None
        ),
        "missing_expected_series": list(report.missing_expected_series),
        "issues": [
            {
                "code": issue.code,
                "severity": issue.severity.value,
                "message": issue.message,
                "count": issue.count,
            }
            for issue in report.issues
        ],
    }
    manifest = {
        "study": "__SLUG__",
        "fetched_at": fetched_at.isoformat(),
        "cache_root": "data/cache/__SLUG__",
        "source_ids": list(SOURCE_IDS),
        "source_version": SOURCE_VERSION,
        "fetches": fetches,
        "quality": quality,
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\\n").encode()
    manifest_path = ROOT / "manifest.json"
    manifest_path.write_bytes(manifest_bytes)
    print(f"manifest written: {manifest_path}")
    print(f"manifest sha256: {hashlib.sha256(manifest_bytes).hexdigest()}")
    summary = {
        "study": "__SLUG__",
        "fetched_at": fetched_at.isoformat(),
        "panels": [
            {
                "instrument_id": entry["instrument_id"],
                "source_id": entry["source_id"],
                "items": entry["items"],
                "observation_rows": entry["observation_rows"],
                "missing": entry["missing"],
                "first_event": entry["first_event"],
                "last_event": entry["last_event"],
            }
            for entry in fetches
        ],
        "quality_row_count": quality["row_count"],
        "quality_issues": quality["issues"],
    }
    summary_path = ROOT / "panel-summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\\n",
        encoding="utf-8",
    )
    print(f"panel summary written: {summary_path}")


if __name__ == "__main__":
    main()
'''


def render_fetch(spec: StudySpec) -> str:
    """Render the generated fetch_data.py for a spec."""
    adapter_imports: list[str] = []
    fetchers: list[str] = []
    todo_sources: list[str] = []
    for source_id in sorted(spec.source_ids):
        builder = _FETCHER_BUILDERS.get(source_id)
        if builder is not None:
            fetcher = builder(spec)
            fetchers.append(fetcher)
            # A frequency the adapter cannot serve is a TODO fetcher:
            # no adapter import (it would be unused) and the source
            # joins TODO_SOURCES so main() fails fast.
            if "TODO: implement" in fetcher:
                todo_sources.append(source_id)
            else:
                module = _ADAPTER_MODULES[source_id]
                adapter_imports.append(
                    f"from myquant.adapters import {module} as {module}_adapter"
                )
        else:
            pointer = _UNIMPLEMENTED_SOURCES.get(
                source_id, "the study that fetched that source by hand"
            )
            fetchers.append(
                _fetch_todo_stub(
                    source_id,
                    f"There is no adapter fetch helper for {source_id}; "
                    f"see {pointer}.",
                )
            )
            todo_sources.append(source_id)
    fetchers_map = {
        source_id: _fetch_function_name(source_id)
        for source_id in sorted(spec.source_ids)
    }
    venues = {
        source_id: _SOURCE_VENUES[source_id]
        for source_id in sorted(spec.source_ids)
    }
    metadata_keys = {
        source_id: _SOURCE_METADATA_KEYS[source_id]
        for source_id in sorted(spec.source_ids)
        if source_id in _SOURCE_METADATA_KEYS
    }
    return (
        _FETCH_TEMPLATE.replace("__SLUG__", spec.slug)
        .replace("__HYPOTHESIS_ID__", spec.hypothesis_id)
        .replace("__PIT_STORE_NAME__", f"pit-{spec.pit_store_suffix}")
        .replace("__SOURCE_IDS__", render_literal(tuple(spec.source_ids)))
        .replace("__INSTRUMENT_IDS__", render_literal(tuple(spec.universe)))
        .replace(
            "__ADAPTER_IMPORTS__\n",
            "\n".join(adapter_imports) + "\n" if adapter_imports else "",
        )
        .replace("__SOURCE_VENUES__", render_literal(venues))
        .replace("__SOURCE_METADATA_KEYS__", render_literal(metadata_keys))
        .replace("__TODO_SOURCES__", render_literal(tuple(sorted(todo_sources))))
        .replace("__FETCHERS__", "\n\n".join(fetchers))
        .replace(
            "__FETCHERS_MAP__",
            "{\n"
            + "".join(
                f'    "{source_id}": {name},\n'
                for source_id, name in sorted(fetchers_map.items())
            )
            + "}",
        )
    )


#: Required fixed parameters per test type (read from the registered
#: spec; the generated run_trial.py fails fast when one is missing,
#: before any trial is recorded).
_REQUIRED_PARAMETERS = {
    "lead_lag": ("lag", "max_hac_lag"),
    "mean_comparison": (
        "hac_max_lag",
        "bootstrap_block_length",
        "bootstrap_resamples",
        "bootstrap_seed",
    ),
    "event_study": (
        "estimation_start_steps",
        "estimation_end_steps",
        "event_pre_steps",
        "event_post_steps",
    ),
    "cross_section": ("max_hac_lag",),
}

#: Stats imports per test type (the generated import block).
_STATS_IMPORTS = {
    "lead_lag": (
        "from myquant.stats import adjust_pvalues, partial_lead_lag"
    ),
    "mean_comparison": (
        "from myquant.stats import (\n"
        "    adjust_pvalues,\n"
        "    block_bootstrap_mean_ci,\n"
        "    newey_west_hac,\n"
        "    ols_fit,\n"
        ")"
    ),
    "event_study": "from myquant.stats import adjust_pvalues",
    "cross_section": (
        "from myquant.stats import adjust_pvalues, newey_west_hac"
    ),
}

#: Extra imports per test type (event-window helpers).
_EXTRA_IMPORTS = {
    "lead_lag": "",
    "mean_comparison": "",
    "event_study": (
        "from myquant.studies.event_windows import (\n"
        "    filter_events_to_panel,\n"
        "    one_sided_normal_p_value,\n"
        "    run_constant_mean_event_study,\n"
        "    standardized_mean_car,\n"
        ")"
    ),
    "cross_section": (
        "from myquant.studies.event_windows import one_sided_normal_p_value"
    ),
}

#: Trial descriptions per test type.
_TRIAL_DESCRIPTIONS = {
    "lead_lag": "lead-lag transmission: partial lead-lag primary test",
    "mean_comparison": "mean comparison: window vs non-window level test",
    "event_study": "event study: constant-mean CAR primary test",
    "cross_section": "cross-sectional regression: CAR-on-CAR primary test",
}


def _lead_lag_fragments() -> dict[str, str]:
    return {
        "design_hooks": '''def _control_id() -> str | None:
    """The common-factor control: the third universe instrument, if any.

    Convention, not a finding: when the universe holds a third
    instrument, the primary test controls for it (study 001 used SOL
    as the common-factor control for BTC/ETH). With a two-instrument
    universe there is no control. Change this function if the design
    needs a different control structure.
    """
    return UNIVERSE[2] if len(UNIVERSE) > 2 else None
''',
        "primary_test": '''def _primary_test(
    panel: SynchronizedPanel,
    spec: HypothesisSpec,
    params: dict[str, str | int | float],
) -> dict[str, Any]:
    """The primary partial lead-lag test, from the registered design."""
    lag_steps = _required_int(params, "lag")
    max_hac_lag = _required_int(params, "max_hac_lag")
    source = panel.returns[SOURCE].to_numpy(dtype=float)
    target = panel.returns[TARGET].to_numpy(dtype=float)
    control_id = _control_id()
    factors = (
        None
        if control_id is None
        else {"control": panel.returns[control_id].to_numpy(dtype=float)}
    )
    result = partial_lead_lag(
        source,
        target,
        lag_steps=lag_steps,
        common_factors=factors,
        max_hac_lag=max_hac_lag,
    )
    effect = result.source_effect
    if effect.p_value is None:
        raise ValueError(
            "HAC p-value is unavailable; cannot form the test family"
        )
    return {
        "observations": result.observations,
        "coefficient": effect.estimate,
        "standard_error": effect.standard_error,
        "t_statistic": effect.t_statistic,
        "p_value": effect.p_value,
        "partial_r_squared": result.partial_r_squared,
        "incremental_r_squared": result.incremental_r_squared,
        "base_r_squared": result.base_model.r_squared,
        "augmented_r_squared": result.augmented_model.r_squared,
        "control_instrument": control_id,
    }
''',
        "verdict": '''def _verdict(
    primary: dict[str, Any],
    adjusted_p_value: float,
    spec: HypothesisSpec,
) -> dict[str, Any]:
    """The primary-criterion verdict (effect size + adjusted p-value).

    This verdict covers the primary criterion only. The remaining
    acceptance criteria need the walk-forward OOS evaluation and the
    cost gate (TODO sections below, not wired into this pipeline).
    """
    partial_r2 = primary["partial_r_squared"]
    effect_ok = partial_r2 is not None and (
        partial_r2 >= spec.minimum_effect_size
    )
    p_ok = adjusted_p_value < spec.target_error_rate
    return {
        "supported": bool(effect_ok and p_ok),
        "criteria": {
            "partial_r_squared_at_least_threshold": bool(effect_ok),
            "adjusted_p_below_target": bool(p_ok),
        },
        "threshold": spec.minimum_effect_size,
        "note": (
            "primary criterion only; walk-forward OOS and cost gate "
            "are TODO sections, not evaluated"
        ),
    }
''',
        "print_summary": '''    print(
        f"primary: coefficient {primary['coefficient']:.6f}, "
        f"p {primary['p_value']:.4g}, "
        f"partial R2 {primary['partial_r_squared']}"
    )''',
    }


def _mean_comparison_fragments() -> dict[str, str]:
    return {
        "design_hooks": '''def condition_mask(returns: pd.DataFrame) -> np.ndarray:
    """TODO: the window indicator for the mean comparison.

    Return a boolean array aligned with ``returns`` (one entry per
    return row): True for window rows, False otherwise. The window
    definition is a research design decision — the calendar, the
    window width, and the bar-alignment convention (which bar carries
    an event that falls between closes) all belong here, preregistered
    in design.json before the trial runs.
    """
    raise NotImplementedError(
        "TODO: define condition_mask for this study's window"
    )
''',
        "primary_test": '''def _primary_test(
    panel: SynchronizedPanel,
    spec: HypothesisSpec,
    params: dict[str, str | int | float],
) -> dict[str, Any]:
    """Mean |log return| comparison: window vs non-window rows.

    The p-value comes from OLS of |r| on the window indicator with
    Newey-West HAC standard errors. The block-bootstrap interval for
    the mean difference is computed on the weighted series whose mean
    is the difference of means: weights N/n_window on window rows and
    -N/n_nonwindow on non-window rows, where N is the total row count
    (the N factor is essential — with weights 1/n_window the series
    mean would be the difference divided by N). partial_r_squared is
    None: this is a mean comparison, not a nested lead-lag test; the
    window indicator's OLS R-squared is reported separately as
    window_r_squared and must not be read as a lead-lag partial
    R-squared.

    TODO: for level series (rates, spreads) replace log returns with
    level changes before taking absolute values.
    """
    hac_max_lag = _required_int(params, "hac_max_lag")
    bootstrap_block_length = _required_int(params, "bootstrap_block_length")
    bootstrap_resamples = _required_int(params, "bootstrap_resamples")
    bootstrap_seed = _required_int(params, "bootstrap_seed")
    values = panel.returns[TARGET].abs().to_numpy(dtype=float)
    window = np.asarray(condition_mask(panel.returns), dtype=bool)
    if window.shape != values.shape:
        raise ValueError(
            "condition_mask must return one entry per return row: "
            f"{window.shape} vs {values.shape}"
        )
    n_window = int(window.sum())
    n_nonwindow = int((~window).sum())
    if n_window == 0 or n_nonwindow == 0:
        raise ValueError("window and non-window groups must both be non-empty")
    mean_window = float(np.mean(values[window]))
    mean_nonwindow = float(np.mean(values[~window]))
    if mean_nonwindow == 0:
        raise ValueError("non-window mean is zero; the ratio is undefined")
    hac = newey_west_hac(
        values,
        {"window": window.astype(float)},
        max_lag=hac_max_lag,
    )
    effect = next(
        coefficient
        for coefficient in hac.coefficients
        if coefficient.name == "window"
    )
    if effect.p_value is None or effect.standard_error is None:
        raise ValueError("HAC inference is unavailable for the window effect")
    fit = ols_fit(values, {"window": window.astype(float)})
    n_total = int(values.size)
    weights = np.where(window, n_total / n_window, -n_total / n_nonwindow)
    weighted = weights * values
    interval = block_bootstrap_mean_ci(
        weighted,
        block_length=bootstrap_block_length,
        resamples=bootstrap_resamples,
        seed=bootstrap_seed,
    )
    # The OLS coefficient and the weighted-series mean are the same
    # quantity (difference of group means); a mismatch means a wiring
    # bug. (This is the guard that caught the T0006 weights bug in
    # study 004.)
    if abs(interval.point_estimate - effect.estimate) > 1e-9:
        raise ValueError(
            "bootstrap point estimate does not match the OLS coefficient: "
            f"{interval.point_estimate} vs {effect.estimate}"
        )
    return {
        "observations": int(values.size),
        "window_observations": n_window,
        "nonwindow_observations": n_nonwindow,
        "coefficient": effect.estimate,
        "standard_error": effect.standard_error,
        "t_statistic": effect.t_statistic,
        "p_value": effect.p_value,
        "partial_r_squared": None,
        "incremental_r_squared": None,
        "window_r_squared": fit.r_squared,
        "mean_window": mean_window,
        "mean_nonwindow": mean_nonwindow,
        "effect_ratio": mean_window / mean_nonwindow,
        "bootstrap_ci_lower": interval.lower_bound,
        "bootstrap_ci_upper": interval.upper_bound,
        "bootstrap_block_length": bootstrap_block_length,
        "bootstrap_resamples": bootstrap_resamples,
        "bootstrap_seed": bootstrap_seed,
    }
''',
        "verdict": '''def _verdict(
    primary: dict[str, Any],
    adjusted_p_value: float,
    spec: HypothesisSpec,
) -> dict[str, Any]:
    """The primary-criterion verdict (effect ratio + adjusted p-value).

    This verdict covers the primary criterion only. The remaining
    acceptance criteria need the walk-forward OOS evaluation and the
    cost gate (TODO sections below, not wired into this pipeline).
    """
    effect_ok = primary["effect_ratio"] >= spec.minimum_effect_size
    p_ok = adjusted_p_value < spec.target_error_rate
    return {
        "supported": bool(effect_ok and p_ok),
        "criteria": {
            "effect_ratio_at_least_threshold": bool(effect_ok),
            "adjusted_p_below_target": bool(p_ok),
        },
        "threshold": spec.minimum_effect_size,
        "note": (
            "primary criterion only; walk-forward OOS and cost gate "
            "are TODO sections, not evaluated"
        ),
    }
''',
        "print_summary": '''    print(
        f"primary: window mean {primary['mean_window']:.6f}, "
        f"non-window mean {primary['mean_nonwindow']:.6f}, "
        f"ratio {primary['effect_ratio']:.4f}, p {primary['p_value']:.4g}"
    )''',
    }


def _event_study_fragments() -> dict[str, str]:
    return {
        "design_hooks": '''def load_events() -> tuple[pd.Timestamp, ...]:
    """TODO: the event dates for this study.

    Return the t=0 timestamps (one per event), each present in the
    panel index. The calendar, the event definition, and the
    bar-alignment convention (which bar carries an event that falls
    between closes) are research design decisions — preregister them
    in design.json and load them from a committed calendar file.
    """
    raise NotImplementedError("TODO: define load_events for this study")
''',
        "primary_test": '''def _primary_test(
    panel: SynchronizedPanel,
    spec: HypothesisSpec,
    params: dict[str, str | int | float],
) -> dict[str, Any]:
    """The primary constant-mean event study, from the registered design.

    TODO: for level series (rates, spreads) replace log returns with
    level changes before running the event study.
    """
    estimation_start_steps = _required_int(params, "estimation_start_steps")
    estimation_end_steps = _required_int(params, "estimation_end_steps")
    pre_event_steps = _required_int(params, "event_pre_steps")
    post_event_steps = _required_int(params, "event_post_steps")
    returns = panel.returns[TARGET]
    events, excluded = filter_events_to_panel(
        returns.index,
        load_events(),
        estimation_start_steps=estimation_start_steps,
        estimation_end_steps=estimation_end_steps,
        pre_event_steps=pre_event_steps,
        post_event_steps=post_event_steps,
    )
    if not events:
        raise ValueError(
            "no events fall inside the panel with full estimation and "
            f"event windows ({len(excluded)} excluded)"
        )
    result = run_constant_mean_event_study(
        returns,
        events,
        estimation_start_steps=estimation_start_steps,
        estimation_end_steps=estimation_end_steps,
        pre_event_steps=pre_event_steps,
        post_event_steps=post_event_steps,
    )
    if result.z_statistic is None:
        raise ValueError("event-study z-statistic is unavailable")
    if spec.expected_direction == ExpectedDirection.NEGATIVE:
        p_value = one_sided_normal_p_value(
            result.z_statistic, direction="less"
        )
    elif spec.expected_direction == ExpectedDirection.POSITIVE:
        p_value = one_sided_normal_p_value(
            result.z_statistic, direction="greater"
        )
    else:
        if result.two_sided_p_value is None:
            raise ValueError("event-study two-sided p-value is unavailable")
        p_value = result.two_sided_p_value
    return {
        "observations": result.event_count,
        "cluster_count": result.cluster_count,
        "mean_car": result.mean_cluster_car,
        "standard_error": result.cluster_standard_error,
        "z_statistic": result.z_statistic,
        "p_value": p_value,
        "standardized_mean_car": standardized_mean_car(result),
        "excluded_events": list(excluded),
    }
''',
        "verdict": '''def _verdict(
    primary: dict[str, Any],
    adjusted_p_value: float,
    spec: HypothesisSpec,
) -> dict[str, Any]:
    """The primary-criterion verdict (standardized CAR + adjusted p).

    The effect must clear the threshold in the preregistered
    direction (negative, positive, or either for a two-sided test).
    This verdict covers the primary criterion only. The remaining
    acceptance criteria need the walk-forward OOS evaluation and the
    cost gate (TODO sections below, not wired into this pipeline).
    """
    standardized = primary["standardized_mean_car"]
    if spec.expected_direction == ExpectedDirection.NEGATIVE:
        effect_ok = standardized <= -spec.minimum_effect_size
    elif spec.expected_direction == ExpectedDirection.POSITIVE:
        effect_ok = standardized >= spec.minimum_effect_size
    else:
        effect_ok = abs(standardized) >= spec.minimum_effect_size
    p_ok = adjusted_p_value < spec.target_error_rate
    return {
        "supported": bool(effect_ok and p_ok),
        "criteria": {
            "standardized_car_clears_threshold_in_direction": bool(effect_ok),
            "adjusted_p_below_target": bool(p_ok),
        },
        "threshold": spec.minimum_effect_size,
        "note": (
            "primary criterion only; walk-forward OOS and cost gate "
            "are TODO sections, not evaluated"
        ),
    }
''',
        "print_summary": '''    print(
        f"primary: mean CAR {primary['mean_car']:.6f}, "
        f"standardized {primary['standardized_mean_car']:.4f}, "
        f"p {primary['p_value']:.4g}"
    )''',
    }


def _cross_section_fragments() -> dict[str, str]:
    return {
        "design_hooks": '''def load_event_cars() -> tuple[np.ndarray, np.ndarray]:
    """TODO: the per-event CARs for the cross-sectional regression.

    Return (target_cars, source_cars): one cumulative abnormal return
    per event for the target instrument and for the source instrument,
    aligned event by event. Computing the CARs is a research design
    decision — run the constant-mean event study per leg (see study
    005) and load the results from a committed file.
    """
    raise NotImplementedError(
        "TODO: define load_event_cars for this study"
    )
''',
        "primary_test": '''def _primary_test(
    panel: SynchronizedPanel,
    spec: HypothesisSpec,
    params: dict[str, str | int | float],
) -> dict[str, Any]:
    """The primary cross-event OLS: target CAR on source CAR.

    The panel is not used directly: the regression runs on the
    per-event CARs from load_event_cars(). Standard errors are
    Newey-West HAC (max_lag=0 gives the heteroskedasticity-consistent
    HC0 covariance). The one-sided p-value follows the preregistered
    direction; a two-sided test uses the HAC two-sided p-value.
    """
    max_hac_lag = _required_int(params, "max_hac_lag")
    target_cars, source_cars = load_event_cars()
    if target_cars.shape != source_cars.shape:
        raise ValueError(
            "target and source CAR arrays must have the same shape: "
            f"{target_cars.shape} vs {source_cars.shape}"
        )
    result = newey_west_hac(
        target_cars,
        {"source_car": source_cars},
        max_lag=max_hac_lag,
    )
    slope = next(
        coefficient
        for coefficient in result.coefficients
        if coefficient.name == "source_car"
    )
    intercept = next(
        coefficient
        for coefficient in result.coefficients
        if coefficient.name == "intercept"
    )
    if slope.standard_error is None or slope.t_statistic is None:
        raise ValueError("HAC inference is unavailable for the slope")
    if spec.expected_direction == ExpectedDirection.NEGATIVE:
        p_value = one_sided_normal_p_value(
            slope.t_statistic, direction="less"
        )
    elif spec.expected_direction == ExpectedDirection.POSITIVE:
        p_value = one_sided_normal_p_value(
            slope.t_statistic, direction="greater"
        )
    else:
        if slope.p_value is None:
            raise ValueError("two-sided p-value is unavailable")
        p_value = slope.p_value
    return {
        "observations": result.observations,
        "coefficient": slope.estimate,
        "standard_error": slope.standard_error,
        "t_statistic": slope.t_statistic,
        "p_value": p_value,
        "partial_r_squared": None,
        "incremental_r_squared": None,
        "r_squared": result.ols.r_squared,
        "intercept": intercept.estimate,
    }
''',
        "verdict": '''def _verdict(
    primary: dict[str, Any],
    adjusted_p_value: float,
    spec: HypothesisSpec,
) -> dict[str, Any]:
    """The primary-criterion verdict (R-squared + adjusted p-value).

    This verdict covers the primary criterion only. The remaining
    acceptance criteria need the walk-forward OOS evaluation and the
    cost gate (TODO sections below, not wired into this pipeline).
    """
    effect_ok = primary["r_squared"] >= spec.minimum_effect_size
    p_ok = adjusted_p_value < spec.target_error_rate
    return {
        "supported": bool(effect_ok and p_ok),
        "criteria": {
            "r_squared_at_least_threshold": bool(effect_ok),
            "adjusted_p_below_target": bool(p_ok),
        },
        "threshold": spec.minimum_effect_size,
        "note": (
            "primary criterion only; walk-forward OOS and cost gate "
            "are TODO sections, not evaluated"
        ),
    }
''',
        "print_summary": '''    print(
        f"primary: slope {primary['coefficient']:.6f}, "
        f"R2 {primary['r_squared']:.4f}, p {primary['p_value']:.4g}"
    )''',
    }


#: Fragment builders per test type.
_RUN_TRIAL_FRAGMENTS = {
    "lead_lag": _lead_lag_fragments,
    "mean_comparison": _mean_comparison_fragments,
    "event_study": _event_study_fragments,
    "cross_section": _cross_section_fragments,
}


_RUN_TRIAL_TEMPLATE = '''"""Run trial __TRIAL_ID__ for hypothesis __HYPOTHESIS_ID__.

Test: __TEST_TYPE_LABEL__.

Generated by the Stage 6c experiment assistant. Run after
preregistration and fetching, from the repo root, with a clean
worktree (the trial records the HEAD commit as its code revision):

    .venv/bin/python research/__SLUG__/run_trial.py

The trial binds the preregistered spec, the fetch manifest's SHA-256
as the data fingerprint, and a canonical-JSON hash of the analysis
configuration. This skeleton wires the minimal pipeline: load the
panel, run the primary test, adjust the (single-test) family, and
record the verdict. The design sections are marked TODO:

- the primary test's design hooks (__DESIGN_HOOK_NAMES__) raise
  NotImplementedError until the researcher defines them;
- the walk-forward out-of-sample evaluation and the cost gate are
  stub functions below, not wired into the pipeline.

The verdict covers the primary criterion only. Do not claim the
acceptance criteria are evaluated until the TODO sections are
implemented and wired in. The runner records the trial (including
failures) in the hash-chained ledger trials.jsonl; it does not
decide acceptance.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__NUMPY_IMPORT____PANDAS_IMPORT__
from myquant.canonical import canonical_json
from myquant.experiments import (
    ExperimentRunner,
    TrialParameter,
    TrialSpec,
    git_head_revision,
)
from myquant.hypotheses import __HYPOTHESES_IMPORT__
from myquant.pit import ParquetPITStore
from myquant.sources import SourceRegistry
__STATS_IMPORT__
__EXTRA_IMPORT__
from myquant.studies.panel import SynchronizedPanel, build_synchronized_panel

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "__SLUG__"

HYPOTHESIS_ID = "__HYPOTHESIS_ID__"
HYPOTHESIS_VERSION = 1
TRIAL_ID = "__TRIAL_ID__"

SOURCE = "__SOURCE__"
TARGET = "__TARGET__"
UNIVERSE = __UNIVERSE__
PIT_STORE_NAME = "__PIT_STORE_NAME__"
BAR_SECONDS = __BAR_SECONDS__

#: Fixed parameters the primary test reads from the registered spec.
#: main() fails fast when one is missing, before any trial is recorded.
REQUIRED_PARAMETERS = __REQUIRED_PARAMETERS__


def load_panel() -> tuple[SynchronizedPanel, dict[str, Any]]:
    """Load the synchronized panel from the local PIT store."""
    manifest_path = ROOT / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    decision_time = datetime.fromisoformat(manifest["fetched_at"])
    if decision_time.tzinfo is None:
        decision_time = decision_time.replace(tzinfo=UTC)

    source_registry = SourceRegistry(ROOT / "sources")
    store = ParquetPITStore(CACHE_ROOT / PIT_STORE_NAME, source_registry)
    panel = build_synchronized_panel(
        store.query_as_of(
            decision_time,
            instrument_ids=set(UNIVERSE),
            fields={"close"},
        ),
        instruments=UNIVERSE,
        bar_seconds=BAR_SECONDS,
    )
    manifest_info = {
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "fetched_at": manifest["fetched_at"],
    }
    return panel, manifest_info


def analysis_config(spec: HypothesisSpec) -> dict[str, Any]:
    """The exact analysis configuration, hashed as the config fingerprint."""
    return {
        "fixed_parameters": list(spec.fixed_parameters),
        "test_family": ["primary"],
        "multiple_testing_method": spec.multiple_testing_method.value,
        "target_error_rate": spec.target_error_rate,
        "train_window": [
            spec.train_window.start.isoformat(),
            spec.train_window.end.isoformat(),
        ],
        "validation_window": [
            spec.validation_window.start.isoformat(),
            spec.validation_window.end.isoformat(),
        ],
        "holdout_window": [
            spec.holdout_window.start.isoformat(),
            spec.holdout_window.end.isoformat(),
        ],
        "cost_model": spec.cost_model,
        "trial_script": "research/__SLUG__/run_trial.py",
    }


def build_trial_spec(
    spec: HypothesisSpec,
    *,
    hypothesis_fingerprint: str,
    data_fingerprint: str,
    code_revision: str,
) -> TrialSpec:
    config_fingerprint = hashlib.sha256(
        canonical_json(analysis_config(spec))
    ).hexdigest()
    parameters = tuple(
        TrialParameter(name=name, value=value)
        for name, value in (
            item.split("=", maxsplit=1) for item in spec.fixed_parameters
        )
    )
    return TrialSpec(
        trial_id=TRIAL_ID,
        hypothesis_id=HYPOTHESIS_ID,
        hypothesis_version=HYPOTHESIS_VERSION,
        hypothesis_fingerprint=hypothesis_fingerprint,
        description="__DESCRIPTION__",
        seed=spec.random_seed,
        data_fingerprint=data_fingerprint,
        config_fingerprint=config_fingerprint,
        code_revision=code_revision,
        universe=spec.universe,
        observation_frequency=spec.observation_frequency,
        horizon_seconds=spec.horizon_seconds,
        target_definition=spec.target_definition,
        source_versions=spec.source_versions,
        feature_set=spec.feature_set,
        model_definition=spec.model_definition,
        benchmark=spec.benchmark,
        cost_model=spec.cost_model,
        primary_metric=spec.primary_metric,
        expected_direction=spec.expected_direction,
        parameters=parameters,
    )


def _parameters(spec: HypothesisSpec) -> dict[str, str]:
    """The registered fixed parameters, as a name -> value map."""
    return dict(
        item.split("=", maxsplit=1) for item in spec.fixed_parameters
    )


def _required_int(params: dict[str, str | int | float], name: str) -> int:
    """One required integer fixed parameter, with a clear error.

    Values come from the trial spec's parameters, which may be strings
    (from "name=value" fixed parameters) or numbers. A non-integer
    float is refused rather than truncated.
    """
    if name not in params:
        raise ValueError(
            f"fixed parameter {name!r} is required by the primary test; "
            "add it to design.json before registering"
        )
    value = params[name]
    if isinstance(value, bool) or (
        isinstance(value, float) and not value.is_integer()
    ):
        raise ValueError(
            f"fixed parameter {name!r} must be an integer: {value!r}"
        )
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"fixed parameter {name!r} must be an integer: {value!r}"
        ) from exc


__DESIGN_HOOKS__
__PRIMARY_TEST__
__VERDICT__

def run_walk_forward_oos(
    panel: SynchronizedPanel, spec: HypothesisSpec
) -> dict[str, Any]:
    """TODO: the purged walk-forward out-of-sample evaluation.

    Mirror study 001's run_walk_forward: expanding windows, a purged
    embargo between train and test, scored in full and on the
    preregistered holdout window only. Wire its result into the
    experiment metrics before claiming the acceptance criteria are
    evaluated.
    """
    raise NotImplementedError(
        "TODO: walk-forward OOS evaluation not implemented"
    )


def run_cost_gate(
    panel: SynchronizedPanel, spec: HypothesisSpec
) -> dict[str, Any]:
    """TODO: the cost gate from the preregistered cost model.

    Apply the preregistered cost assumptions to the holdout OOS
    forecasts (or the study's decision rule) and report the net edge
    with a block-bootstrap interval. Wire its result into the
    experiment metrics before claiming the acceptance criteria are
    evaluated.
    """
    raise NotImplementedError("TODO: cost gate not implemented")


def build_experiment(
    panel: SynchronizedPanel, spec: HypothesisSpec
) -> Callable[[TrialSpec], dict[str, Any]]:
    """The experiment closure the runner executes and records."""

    def experiment(trial_spec: TrialSpec) -> dict[str, Any]:
        params = {item.name: item.value for item in trial_spec.parameters}
        primary = _primary_test(panel, spec, params)
        adjusted = adjust_pvalues(
            [primary["p_value"]],
            method=spec.multiple_testing_method,
            target_error_rate=spec.target_error_rate,
        )
        multiple_testing = {
            "method": spec.multiple_testing_method.value,
            "tests": [
                {
                    "test": "primary",
                    "raw_p_value": adjusted[0].raw_p_value,
                    "adjusted_p_value": adjusted[0].adjusted_p_value,
                    "reject": adjusted[0].reject,
                }
            ],
        }
        verdict = _verdict(primary, adjusted[0].adjusted_p_value, spec)
        return {
            "tests": {"primary": primary},
            "multiple_testing": multiple_testing,
            "verdict": verdict,
        }

    return experiment


def main() -> None:
    if TRIAL_ID == "TODO":
        raise ValueError(
            "TRIAL_ID is TODO: fill the trial id in the study spec and "
            "regenerate the scaffold, or set TRIAL_ID in this file"
        )
    registry = HypothesisRegistry(ROOT / "hypotheses")
    registration = registry.get(HYPOTHESIS_ID, version=HYPOTHESIS_VERSION)
    spec = registration.spec
    params = _parameters(spec)
    missing = [name for name in REQUIRED_PARAMETERS if name not in params]
    if missing:
        raise ValueError(
            "fixed parameters required by the primary test are missing "
            f"from the registered spec: {missing}; amend the "
            "preregistration before testing"
        )
    code_revision = git_head_revision(REPO_ROOT)
    if code_revision is None:
        raise RuntimeError("could not determine the git HEAD revision")
    panel, manifest_info = load_panel()
    print(
        f"panel: {panel.row_count} rows, "
        f"{panel.first_time} to {panel.last_time}, "
        f"{panel.dropped_return_rows} dropped return rows"
    )
    trial_spec = build_trial_spec(
        spec,
        hypothesis_fingerprint=registration.spec_fingerprint,
        data_fingerprint=manifest_info["manifest_sha256"],
        code_revision=code_revision,
    )
    runner = ExperimentRunner(ROOT / "trials.jsonl", registry)
    receipt = runner.run(
        trial_spec,
        build_experiment(panel, spec),
    )
    print(f"trial {receipt.trial_id} completed: record {receipt.record_hash}")
    metrics = receipt.metrics
    primary = metrics["tests"]["primary"]
__PRINT_SUMMARY__
    print(f"multiple testing: {metrics['multiple_testing']}")
    print(f"verdict supported: {metrics['verdict']['supported']}")


if __name__ == "__main__":
    main()
'''


#: Design-hook names per test type (named in the docstring).
_DESIGN_HOOK_NAMES = {
    "lead_lag": "_control_id",
    "mean_comparison": "condition_mask",
    "event_study": "load_events",
    "cross_section": "load_event_cars",
}


def render_run_trial(spec: StudySpec) -> str:
    """Render the generated run_trial.py for a spec."""
    test_type = spec.test_type.value
    fragments = _RUN_TRIAL_FRAGMENTS[test_type]()
    hypotheses_import = "HypothesisRegistry, HypothesisSpec"
    if test_type in ("event_study", "cross_section"):
        hypotheses_import = (
            "(\n    ExpectedDirection,\n    HypothesisRegistry,"
            "\n    HypothesisSpec,\n)"
        )
    extra_import = _EXTRA_IMPORTS[test_type]
    return (
        _RUN_TRIAL_TEMPLATE.replace("__SLUG__", spec.slug)
        .replace("__HYPOTHESIS_ID__", spec.hypothesis_id)
        .replace(
            "__TRIAL_ID__",
            spec.trial_id if spec.trial_id is not None else TODO,
        )
        .replace("__TEST_TYPE_LABEL__", test_type_label(spec))
        .replace("__DESCRIPTION__", _TRIAL_DESCRIPTIONS[test_type])
        .replace("__DESIGN_HOOK_NAMES__", _DESIGN_HOOK_NAMES[test_type])
        .replace("__SOURCE__", spec.source_instrument)
        .replace("__TARGET__", spec.target_instrument)
        .replace("__UNIVERSE__", render_literal(tuple(spec.universe)))
        .replace("__PIT_STORE_NAME__", f"pit-{spec.pit_store_suffix}")
        .replace(
            "__BAR_SECONDS__",
            str(spec.bar_seconds) if spec.bar_seconds is not None else "None",
        )
        .replace(
            "__NUMPY_IMPORT____PANDAS_IMPORT__\n",
            (
                (
                    "import numpy as np\n"
                    if test_type in ("mean_comparison", "cross_section")
                    else ""
                )
                + (
                    "import pandas as pd\n"
                    if test_type in ("mean_comparison", "event_study")
                    else ""
                )
                + "\n"
            )
            if test_type in ("mean_comparison", "event_study", "cross_section")
            else "",
        )
        .replace("__HYPOTHESES_IMPORT__", hypotheses_import)
        .replace("__STATS_IMPORT__", _STATS_IMPORTS[test_type])
        .replace(
            "__EXTRA_IMPORT__\n",
            extra_import + "\n" if extra_import else "",
        )
        .replace(
            "__REQUIRED_PARAMETERS__",
            render_literal(_REQUIRED_PARAMETERS[test_type]),
        )
        .replace("__DESIGN_HOOKS__", fragments["design_hooks"])
        .replace("__PRIMARY_TEST__", fragments["primary_test"])
        .replace("__VERDICT__", fragments["verdict"])
        .replace("__PRINT_SUMMARY__", fragments["print_summary"])
    )
