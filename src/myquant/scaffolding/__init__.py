"""The experiment assistant (Stage 6c): study scaffold generator.

Given a :class:`StudySpec`, generate one standard study directory —
README, design, preregister/fetch/run_trial skeletons, contract
stubs, a parked planner draft, and a report template. The scaffold
wires structure and never designs: thresholds and criteria come from
the spec, everything else stays TODO until the researcher fills it.
"""

from myquant.scaffolding.generator import generate, load_source_metadata
from myquant.scaffolding.planner import spec_from_planner_draft
from myquant.scaffolding.spec import (
    TODO,
    ScaffoldError,
    ScaffoldFrequency,
    StudySpec,
)

__all__ = [
    "TODO",
    "ScaffoldError",
    "ScaffoldFrequency",
    "StudySpec",
    "generate",
    "load_source_metadata",
    "spec_from_planner_draft",
]
