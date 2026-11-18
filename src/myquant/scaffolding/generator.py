"""Generate one standard study directory from a StudySpec.

The generator is deliberately strict: it refuses rather than guesses.
The target directory must not exist, the study must live directly
under ``research/``, the report path must not exist, and every source
id in the spec must be in the caller-supplied ``known_source_ids`` —
the generator takes no defaults for what counts as a known source.
``load_source_metadata`` builds the known-source mapping from the
Stage 6b evidence registry; callers that already know their sources
may pass their own mapping instead.

Output is deterministic: the same spec, the same known sources, and
the same source metadata always produce byte-identical files. No
generation timestamps are written anywhere; JSON is dumped with
sorted keys; files are written in sorted path order.
"""

from __future__ import annotations

from pathlib import Path

from myquant.evidence.registry import load_registry
from myquant.files import write_new_file
from myquant.scaffolding.spec import ScaffoldError, StudySpec
from myquant.scaffolding.templates import (
    dumps_json,
    quoted_catalog_key,
    render_calendar_stub,
    render_design_json,
    render_draft_json,
    render_fetch,
    render_instrument_stub,
    render_preregister,
    render_readme,
    render_report_template,
    render_run_trial,
    render_source_stub,
)


def load_source_metadata(
    registry_path: str | Path,
) -> dict[str, tuple[str, str]]:
    """Known sources from the Stage 6b evidence registry.

    Returns {source_id: (provider, description)} for every source in
    the registry, in registry order. The provider and description are
    the verified 6b records; the generator copies them into the
    source stubs verbatim.
    """
    registry = load_registry(Path(registry_path))
    return {
        source.source_id: (source.provider, source.description)
        for source in registry.sources
    }


def _stub_file_list(spec: StudySpec) -> tuple[str, ...]:
    """Contract stub paths (relative to the study dir), sorted."""
    files = [
        f"sources/{source_id}/v1.json" for source_id in spec.source_ids
    ]
    files.extend(
        f"catalog/instruments/{quoted_catalog_key(instrument_id)}/v1.json"
        for instrument_id in spec.universe
    )
    files.extend(
        f"catalog/calendars/{quoted_catalog_key(calendar_id)}/v1.json"
        for calendar_id in spec.calendar_ids
    )
    return tuple(sorted(files))


def generate(
    spec: StudySpec,
    *,
    target: str | Path,
    known_source_ids: frozenset[str] | set[str],
    source_metadata: dict[str, tuple[str, str]] | None = None,
    docs_root: str | Path | None = None,
) -> list[Path]:
    """Generate the study directory for a spec; return written paths.

    ``target`` is the study directory (``research/<slug>/``); the
    report goes to ``docs/studies/<slug>.md`` (or ``docs_root`` when
    given, for tests and validation). Raises :class:`ScaffoldError`
    and writes nothing when a guard trips: an unknown source id, an
    existing target directory, an existing report, or a target that
    does not sit directly under ``research/``.
    """
    target_path = Path(target)
    if target_path.parent.name != "research":
        raise ScaffoldError(
            f"study directory must sit directly under research/: {target_path}"
        )
    unknown_sources = sorted(set(spec.source_ids) - set(known_source_ids))
    if unknown_sources:
        raise ScaffoldError(
            f"unknown source id(s): {unknown_sources}; the scaffold only "
            "generates stubs for sources in the known-source mapping"
        )
    if target_path.exists():
        raise ScaffoldError(
            f"target directory already exists; refusing to overwrite: "
            f"{target_path}"
        )
    docs_root_path = (
        Path(docs_root)
        if docs_root is not None
        else target_path.parent.parent / "docs" / "studies"
    )
    report_path = docs_root_path / f"{spec.slug}.md"
    if report_path.exists():
        raise ScaffoldError(
            f"report already exists; refusing to overwrite: {report_path}"
        )

    metadata = source_metadata if source_metadata is not None else {}
    stub_files = _stub_file_list(spec)
    contents: dict[Path, str] = {
        target_path / "README.md": render_readme(spec),
        target_path / "spec.json": dumps_json(spec.model_dump(mode="json")),
        target_path / "design.json": render_design_json(spec),
        target_path / "preregister.py": render_preregister(spec, stub_files),
        target_path / "fetch_data.py": render_fetch(spec),
        target_path / "run_trial.py": render_run_trial(spec),
        target_path
        / "hypotheses"
        / "registrations"
        / spec.hypothesis_id
        / "draft.json": render_draft_json(spec),
        report_path: render_report_template(spec),
    }
    for source_id in spec.source_ids:
        contents[target_path / "sources" / source_id / "v1.json"] = (
            render_source_stub(source_id, metadata.get(source_id))
        )
    for instrument_id in spec.universe:
        contents[
            target_path
            / "catalog"
            / "instruments"
            / quoted_catalog_key(instrument_id)
            / "v1.json"
        ] = render_instrument_stub(instrument_id)
    for calendar_id in spec.calendar_ids:
        contents[
            target_path
            / "catalog"
            / "calendars"
            / quoted_catalog_key(calendar_id)
            / "v1.json"
        ] = render_calendar_stub(calendar_id)

    written: list[Path] = []
    for path in sorted(contents):
        write_new_file(path, contents[path].encode("utf-8"))
        written.append(path)
    return written
