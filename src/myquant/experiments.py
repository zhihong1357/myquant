"""Reproducible experiment execution bound to preregistered hypotheses."""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from collections.abc import Callable, Mapping
from decimal import Decimal, InvalidOperation
from math import isfinite
from pathlib import Path
from typing import Annotated, Any

import numpy as np
from pydantic import Field, model_validator

from myquant.canonical import canonical_json
from myquant.contracts import StrictContract
from myquant.hypotheses import (
    ExpectedDirection,
    HypothesisRegistry,
    HypothesisSpec,
)
from myquant.registry import append_trial, read_and_verify

logger = logging.getLogger(__name__)


class TrialParameter(StrictContract):
    """One immutable scalar experiment parameter."""

    name: str = Field(min_length=1)
    value: str | int | bool | Annotated[float, Field(allow_inf_nan=False)]

    @model_validator(mode="after")
    def validate_value(self) -> TrialParameter:
        if isinstance(self.value, float) and not isfinite(self.value):
            raise ValueError("trial parameter values must be finite")
        return self


class TrialSpec(StrictContract):
    """One executable trial bound to a preregistered hypothesis version.

    data_fingerprint, config_fingerprint and code_revision are caller
    attestations, not verified facts: the runner checks only their format
    and binds them to the trial record. It cannot prove that the data,
    configuration or code actually used match the supplied values. Use
    git_head_revision() to fill code_revision from a real checkout, and
    compute data/config fingerprints from the exact inputs used.
    """

    trial_id: str = Field(min_length=5, pattern=r"^T[0-9]{4,}$")
    hypothesis_id: str = Field(pattern=r"^H[0-9]{4,}$")
    hypothesis_version: int = Field(ge=1)
    hypothesis_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    description: str = Field(min_length=8)

    seed: int = Field(ge=0)
    data_fingerprint: str = Field(
        pattern=r"^[0-9a-f]{64}$",
        description="SHA-256 of the exact input data (caller attestation).",
    )
    config_fingerprint: str = Field(
        pattern=r"^[0-9a-f]{64}$",
        description="SHA-256 of the exact configuration (caller attestation).",
    )
    code_revision: str = Field(
        min_length=7,
        description="VCS revision of the executed code (caller attestation).",
    )

    universe: tuple[str, ...] = Field(min_length=1)
    observation_frequency: str = Field(min_length=2)
    horizon_seconds: int = Field(gt=0)
    target_definition: str = Field(min_length=12)
    source_versions: tuple[str, ...] = Field(min_length=1)
    feature_set: tuple[str, ...] = Field(min_length=1)
    model_definition: tuple[str, ...] = Field(min_length=1)
    benchmark: str = Field(min_length=5)
    cost_model: str = Field(min_length=5)
    primary_metric: str = Field(min_length=5)
    expected_direction: ExpectedDirection

    parameters: tuple[TrialParameter, ...] = ()

    @model_validator(mode="after")
    def validate_parameters(self) -> TrialSpec:
        names = [parameter.name for parameter in self.parameters]
        if len(set(names)) != len(names):
            raise ValueError("trial parameter names must be unique")
        object.__setattr__(
            self,
            "parameters",
            tuple(sorted(self.parameters, key=lambda parameter: parameter.name)),
        )
        for field_name in (
            "universe",
            "source_versions",
            "feature_set",
            "model_definition",
        ):
            values = getattr(self, field_name)
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} entries must be unique")
        return self


class TrialReceipt(StrictContract):
    trial_id: str
    hypothesis_id: str
    hypothesis_version: int
    hypothesis_fingerprint: str
    status: str
    spec_fingerprint: str
    record_hash: str
    metrics: dict[str, Any] = Field(default_factory=dict)


Experiment = Callable[[TrialSpec], Mapping[str, Any]]


def git_head_revision(repo_path: str | Path | None = None) -> str | None:
    """Return the HEAD commit SHA of a local git repository, or None.

    This is a read-only local lookup (``git rev-parse HEAD``) with no
    network access. It returns None when the path is not inside a git
    repository, when git is unavailable, or when the command fails or
    times out. Callers may pass the result as a trial's code_revision;
    the runner never calls this itself, so trials remain reproducible
    outside a git checkout. A dirty worktree is NOT detected: the
    returned SHA identifies the last commit, not the exact working files.
    """
    command = ["git", "rev-parse", "HEAD"]
    if repo_path is not None:
        command = ["git", "-C", str(repo_path), "rev-parse", "HEAD"]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    revision = completed.stdout.strip()
    if len(revision) != 40 or any(
        char not in "0123456789abcdef" for char in revision
    ):
        return None
    return revision


class ExperimentRunner:
    """Execute one trial only when it matches the registered research plan.

    The preregistered hypothesis version is moved into TESTING before the
    callback is executed. Trial success/failure is appended to the hash-chained
    trial ledger. The runner does not decide statistical acceptance.

    Fingerprints and code revisions recorded with a trial are caller
    attestations: the runner verifies their format and binds them to the
    receipt, but it cannot verify that they describe the data, config or
    code actually used.
    """

    def __init__(
        self,
        ledger_path: str | Path,
        hypothesis_registry: HypothesisRegistry,
    ) -> None:
        self.ledger_path = Path(ledger_path)
        self.hypothesis_registry = hypothesis_registry

    def run(self, spec: TrialSpec, experiment: Experiment) -> TrialReceipt:
        existing = read_and_verify(self.ledger_path)
        if any(record["trial_id"] == spec.trial_id for record in existing):
            raise FileExistsError(f"trial_id already exists: {spec.trial_id}")

        registration = self.hypothesis_registry.get(
            spec.hypothesis_id,
            version=spec.hypothesis_version,
        )
        self._assert_trial_matches_registration(spec, registration.spec)

        serialized_spec = spec.model_dump(mode="json")
        fingerprint_payload = {
            key: value
            for key, value in serialized_spec.items()
            if key != "trial_id"
        }
        spec_fingerprint = hashlib.sha256(
            canonical_json(fingerprint_payload)
        ).hexdigest()

        self.hypothesis_registry.assert_runnable(
            spec.hypothesis_id,
            spec.hypothesis_version,
            spec.hypothesis_fingerprint,
        )

        try:
            raw_metrics = experiment(spec)
            metrics = _normalize_json(dict(raw_metrics))
        except Exception as exc:
            failure_record = {
                "schema_version": 1,
                "spec": serialized_spec,
                "spec_fingerprint": spec_fingerprint,
                "error_type": type(exc).__name__,
                "error": str(exc)[:2_000],
            }
            append_trial(
                self.ledger_path,
                trial_id=spec.trial_id,
                hypothesis_id=spec.hypothesis_id,
                status="failed",
                result=failure_record,
            )
            logger.warning(
                "trial %s for %s v%s failed: %s: %s",
                spec.trial_id,
                spec.hypothesis_id,
                spec.hypothesis_version,
                type(exc).__name__,
                exc,
            )
            raise

        result = {
            "schema_version": 1,
            "spec": serialized_spec,
            "spec_fingerprint": spec_fingerprint,
            "metrics": metrics,
        }
        record_hash = append_trial(
            self.ledger_path,
            trial_id=spec.trial_id,
            hypothesis_id=spec.hypothesis_id,
            status="completed",
            result=result,
        )
        logger.info(
            "trial %s for %s v%s completed (record %s)",
            spec.trial_id,
            spec.hypothesis_id,
            spec.hypothesis_version,
            record_hash[:12],
        )
        return TrialReceipt(
            trial_id=spec.trial_id,
            hypothesis_id=spec.hypothesis_id,
            hypothesis_version=spec.hypothesis_version,
            hypothesis_fingerprint=spec.hypothesis_fingerprint,
            status="completed",
            spec_fingerprint=spec_fingerprint,
            record_hash=record_hash,
            metrics=metrics,
        )

    @staticmethod
    def _assert_trial_matches_registration(
        spec: TrialSpec,
        hypothesis: HypothesisSpec,
    ) -> None:
        """Reject trials whose research plan differs from the preregistration.

        Fixed parameters compare numerically when both sides parse as
        numbers (1 matches 1.0, 0.5 matches "0.50"); booleans compare as
        the literal strings "true"/"false" and never match a number. Every
        mismatch is reported with its expected and actual values.
        """
        expected = {
            "universe": hypothesis.universe,
            "observation_frequency": hypothesis.observation_frequency,
            "horizon_seconds": hypothesis.horizon_seconds,
            "target_definition": hypothesis.target_definition,
            "source_versions": hypothesis.source_versions,
            "feature_set": hypothesis.feature_set,
            "model_definition": hypothesis.model_definition,
            "benchmark": hypothesis.benchmark,
            "cost_model": hypothesis.cost_model,
            "primary_metric": hypothesis.primary_metric,
            "expected_direction": hypothesis.expected_direction,
            "seed": hypothesis.random_seed,
        }
        actual = {
            "universe": spec.universe,
            "observation_frequency": spec.observation_frequency,
            "horizon_seconds": spec.horizon_seconds,
            "target_definition": spec.target_definition,
            "source_versions": spec.source_versions,
            "feature_set": spec.feature_set,
            "model_definition": spec.model_definition,
            "benchmark": spec.benchmark,
            "cost_model": spec.cost_model,
            "primary_metric": spec.primary_metric,
            "expected_direction": spec.expected_direction,
            "seed": spec.seed,
        }
        mismatches = [
            f"{name}: expected {_short_repr(value)}, "
            f"trial has {_short_repr(actual[name])}"
            for name, value in expected.items()
            if actual[name] != value
        ]
        mismatches.extend(
            _parameter_mismatches(
                _parse_fixed_parameters(hypothesis.fixed_parameters),
                {parameter.name: parameter.value for parameter in spec.parameters},
            )
        )
        if mismatches:
            raise PermissionError(
                "trial does not match preregistered hypothesis fields: "
                + "; ".join(mismatches)
            )


def _parse_fixed_parameters(parameters: tuple[str, ...]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in parameters:
        name, value = item.split("=", maxsplit=1)
        parsed[name.strip()] = value.strip()
    return parsed


def _parameter_value(value: str | int | float | bool) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _numeric_equal(left: str, right: str) -> bool:
    """Compare two strings as exact decimal numbers, if both parse."""
    try:
        return Decimal(left) == Decimal(right)
    except InvalidOperation:
        return False


def _values_match(expected: str, actual: str | int | float | bool) -> bool:
    """Compare a preregistered parameter value with a trial value.

    Booleans compare as the literal strings "true"/"false" and never match
    a number. When both sides parse as decimal numbers they compare by
    numeric value, so 1 matches 1.0, 0.5 matches "0.50" and 0.001 matches
    "1e-3". Anything else compares as exact strings.
    """
    if isinstance(actual, bool):
        return ("true" if actual else "false") == expected
    if isinstance(actual, str) and actual == expected:
        return True
    return _numeric_equal(expected, str(actual))


def _short_repr(value: Any, *, limit: int = 120) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _parameter_mismatches(
    expected: dict[str, str],
    actual: dict[str, str | int | float | bool],
) -> list[str]:
    """Describe every fixed-parameter difference with expected/actual values."""
    details: list[str] = []
    for name in sorted(set(expected) | set(actual)):
        if name not in actual:
            details.append(
                f"parameters: '{name}' is preregistered as "
                f"'{expected[name]}' but missing from the trial"
            )
        elif name not in expected:
            details.append(
                f"parameters: '{name}' is not preregistered "
                f"(trial has '{_parameter_value(actual[name])}')"
            )
        elif not _values_match(expected[name], actual[name]):
            details.append(
                f"parameters: '{name}' expected '{expected[name]}' "
                f"but trial has '{_parameter_value(actual[name])}'"
            )
    return details


def _to_jsonable(value: Any) -> Any:
    """Convert numpy scalars and arrays to plain Python values.

    Metrics computed with numpy are ordinary numbers, not experiment
    failures: np.integer becomes int, np.floating becomes float, np.bool_
    becomes bool and ndarrays become nested lists. Anything else passes
    through unchanged for the strict JSON round-trip to accept or reject.
    """
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        return _to_jsonable(value.tolist())
    if isinstance(value, Mapping):
        return {
            _to_jsonable(key): _to_jsonable(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    return value


def _normalize_json(value: Any) -> Any:
    """Round-trip values through strict JSON to reject NaN, Infinity and objects."""
    return json.loads(canonical_json(_to_jsonable(value)))
