"""Map a Stage 6a preregistration draft onto a scaffold spec.

A planner draft (``research/planner-6a/templates/*.json``) is one input
to the scaffold: it already knows the pair, the suggested test type and
frequency, the lab threshold, the estimated joint sample, and the
templated research question and hypotheses. This module maps those
known fields onto a :class:`StudySpec` and leaves everything else TODO.

Deliberately not automated: the draft's ``source_versions`` are
descriptive strings ("FRED BAA10Y (...), fredgraph CSV, no key"), not
source ids, so the researcher supplies ``source_ids`` explicitly; the
mapping never guesses an id from prose. Likewise the calendar ids and
the trial id are researcher decisions, not draft fields. Draft fields
marked ``"TODO"`` map to ``None`` and come back as ``"TODO"`` in the
generated ``design.json`` and draft — never silently filled.
"""

from __future__ import annotations

from typing import Any

from myquant.graph import EdgeTestType
from myquant.scaffolding.spec import ScaffoldFrequency, StudySpec

#: Draft fields whose literal "TODO" value means "unknown".
_SCALAR_DRAFT_FIELDS = (
    "research_question",
    "null_hypothesis",
    "alternative_hypothesis",
    "target_definition",
    "primary_metric",
    "missing_data_policy",
)


def _draft_text(draft: dict[str, Any], field: str) -> str | None:
    """A draft text field: the value, or None when it is TODO."""
    value = draft.get(field)
    if value is None or value == "TODO":
        return None
    if not isinstance(value, str):
        raise ValueError(f"planner draft field {field!r} must be a string")
    return value


def _draft_strings(draft: dict[str, Any], field: str) -> tuple[str, ...]:
    """A draft string-list field, preserved verbatim (TODOs included)."""
    value = draft.get(field)
    if value is None:
        return ()
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        raise ValueError(f"planner draft field {field!r} must be a string list")
    return tuple(value)


def spec_from_planner_draft(
    draft: dict[str, Any],
    *,
    study_number: int,
    slug: str,
    hypothesis_id: str,
    source_ids: tuple[str, ...],
    calendar_ids: tuple[str, ...],
    trial_id: str | None = None,
) -> StudySpec:
    """Build a StudySpec from a 6a preregistration draft.

    The draft is validated before anything is mapped: it must be a
    draft (``draft: true``, schema version 1), its suggested test
    type must be one the scaffold knows, its universe must hold
    exactly the source and target instruments, and its frequency and
    effect-size threshold must be present. Anything else is refused,
    not defaulted.
    """
    if not isinstance(draft, dict):
        raise ValueError("planner draft must be a JSON object")
    if draft.get("schema_version") != 1:
        raise ValueError("planner draft schema_version must be 1")
    if draft.get("draft") is not True:
        raise ValueError("planner draft must have draft=true")

    test_type_raw = draft.get("suggested_test_type")
    if not isinstance(test_type_raw, str):
        raise ValueError(
            "planner draft suggested_test_type must be a string"
        )
    try:
        test_type = EdgeTestType(test_type_raw)
    except ValueError as exc:
        raise ValueError(
            f"unknown suggested test type in planner draft: {test_type_raw!r}"
        ) from exc
    frequency_raw = draft.get("observation_frequency")
    if not isinstance(frequency_raw, str):
        raise ValueError(
            "planner draft observation_frequency must be a string"
        )
    try:
        frequency = ScaffoldFrequency(frequency_raw)
    except ValueError as exc:
        raise ValueError(
            f"unknown observation frequency in planner draft: {frequency_raw!r}"
        ) from exc
    universe = draft.get("universe")
    if (
        not isinstance(universe, list)
        or len(universe) != 2
        or not all(isinstance(item, str) and item for item in universe)
    ):
        raise ValueError(
            "planner draft universe must be a two-instrument list "
            "[source, target]"
        )
    minimum_effect_size = draft.get("minimum_effect_size")
    if not isinstance(minimum_effect_size, (int, float)) or isinstance(
        minimum_effect_size, bool
    ):
        raise ValueError("planner draft minimum_effect_size must be a number")
    acceptance_criteria = _draft_strings(draft, "acceptance_criteria")
    if not acceptance_criteria:
        raise ValueError("planner draft acceptance_criteria must not be empty")

    sample_period = draft.get("sample_period")
    estimated_joint_rows: int | None = None
    estimated_joint_rows_basis: str | None = None
    if sample_period is not None:
        if not isinstance(sample_period, dict):
            raise ValueError("planner draft sample_period must be an object")
        rows = sample_period.get("estimated_joint_rows")
        if rows is not None:
            if not isinstance(rows, int) or isinstance(rows, bool) or rows < 0:
                raise ValueError(
                    "planner draft estimated_joint_rows must be a "
                    "non-negative integer"
                )
            estimated_joint_rows = rows
        basis = sample_period.get("estimated_joint_rows_basis")
        if basis is not None:
            if not isinstance(basis, str):
                raise ValueError(
                    "planner draft estimated_joint_rows_basis must be a string"
                )
            estimated_joint_rows_basis = basis

    planner_rank = draft.get("planner_rank")
    if planner_rank is not None and (
        not isinstance(planner_rank, int)
        or isinstance(planner_rank, bool)
        or planner_rank < 1
    ):
        raise ValueError("planner draft planner_rank must be a positive integer")
    planner_total_score = draft.get("planner_total_score")
    if planner_total_score is not None and not isinstance(
        planner_total_score, (int, float)
    ):
        raise ValueError("planner draft planner_total_score must be a number")
    suggested_test_reason = draft.get("suggested_test_reason")
    if suggested_test_reason is not None and not isinstance(
        suggested_test_reason, str
    ):
        raise ValueError("planner draft suggested_test_reason must be a string")
    multiple_testing_method = draft.get("multiple_testing_method")
    if multiple_testing_method is not None and not isinstance(
        multiple_testing_method, str
    ):
        raise ValueError("planner draft multiple_testing_method must be a string")
    target_error_rate = draft.get("target_error_rate")
    if target_error_rate is not None and not isinstance(
        target_error_rate, (int, float)
    ):
        raise ValueError("planner draft target_error_rate must be a number")

    return StudySpec(
        study_number=study_number,
        slug=slug,
        hypothesis_id=hypothesis_id,
        trial_id=trial_id,
        source_instrument=universe[0],
        target_instrument=universe[1],
        test_type=test_type,
        frequency=frequency,
        source_ids=source_ids,
        universe=tuple(universe),
        calendar_ids=calendar_ids,
        minimum_effect_size=float(minimum_effect_size),
        acceptance_criteria=acceptance_criteria,
        research_question=_draft_text(draft, "research_question"),
        null_hypothesis=_draft_text(draft, "null_hypothesis"),
        alternative_hypothesis=_draft_text(draft, "alternative_hypothesis"),
        target_definition=_draft_text(draft, "target_definition"),
        primary_metric=_draft_text(draft, "primary_metric"),
        model_definition=_draft_strings(draft, "model_definition"),
        rejection_criteria=_draft_strings(draft, "rejection_criteria"),
        missing_data_policy=_draft_text(draft, "missing_data_policy"),
        multiple_testing_method=multiple_testing_method,
        target_error_rate=(
            float(target_error_rate)
            if target_error_rate is not None
            else None
        ),
        planner_rank=planner_rank,
        planner_total_score=(
            float(planner_total_score)
            if planner_total_score is not None
            else None
        ),
        suggested_test_reason=suggested_test_reason,
        adjacent_supported_edges=_draft_strings(
            draft, "adjacent_supported_edges"
        ),
        decision_records=_draft_strings(draft, "decision_records"),
        estimated_joint_rows=estimated_joint_rows,
        estimated_joint_rows_basis=estimated_joint_rows_basis,
        planner_notes=_draft_strings(draft, "planner_notes"),
    )
