"""Reproducible experiment execution bound to preregistered hypotheses."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from pydantic import Field

from myquant.contracts import StrictContract
from myquant.hypotheses import HypothesisRegistry
from myquant.registry import append_trial, read_and_verify


class TrialSpec(StrictContract):
    trial_id: str = Field(min_length=5, pattern=r"^T[0-9]{4,}$")
    hypothesis_id: str = Field(pattern=r"^H[0-9]{4,}$")
    hypothesis_version: int = Field(ge=1)
    hypothesis_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    description: str = Field(min_length=8)

    seed: int = Field(ge=0)
    data_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_revision: str = Field(min_length=7)

    horizon_seconds: int = Field(gt=0)
    source_versions: tuple[str, ...] = Field(min_length=1)
    feature_set: tuple[str, ...] = Field(min_length=1)
    model_definition: tuple[str, ...] = Field(min_length=1)
    benchmark: str = Field(min_length=5)
    cost_model: str = Field(min_length=5)
    primary_metric: str = Field(min_length=5)
    expected_direction: str = Field(min_length=3)

    parameters: dict[str, Any] = Field(default_factory=dict)


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


class ExperimentRunner:
    """Execute one trial only when it matches the registered research plan.

    The preregistered hypothesis version is moved into TESTING before the
    callback is executed. Trial success/failure is appended to the hash-chained
    trial ledger. The runner does not decide statistical acceptance.
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
            _canonical_json(fingerprint_payload)
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
    def _assert_trial_matches_registration(spec: TrialSpec, hypothesis: Any) -> None:
        expected = {
            "horizon_seconds": hypothesis.horizon_seconds,
            "source_versions": hypothesis.source_versions,
            "feature_set": hypothesis.feature_set,
            "model_definition": hypothesis.model_definition,
            "benchmark": hypothesis.benchmark,
            "cost_model": hypothesis.cost_model,
            "primary_metric": hypothesis.primary_metric,
            "expected_direction": hypothesis.expected_direction.value,
            "seed": hypothesis.random_seed,
        }
        actual = {
            "horizon_seconds": spec.horizon_seconds,
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
            name for name, value in expected.items() if actual[name] != value
        ]
        if mismatches:
            joined = ", ".join(mismatches)
            raise PermissionError(
                f"trial does not match preregistered hypothesis fields: {joined}"
            )


def _normalize_json(value: Any) -> Any:
    """Round-trip values through strict JSON to reject NaN, Infinity and objects."""
    return json.loads(_canonical_json(value))


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
