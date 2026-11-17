"""Reproducible experiment execution with immutable trial receipts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from pydantic import Field

from myquant.contracts import StrictContract
from myquant.registry import append_trial, read_and_verify


class TrialSpec(StrictContract):
    trial_id: str = Field(min_length=5, pattern=r"^T[0-9]{4,}$")
    hypothesis_id: str = Field(pattern=r"^H[0-9]{4,}$")
    description: str = Field(min_length=8)
    seed: int = Field(ge=0)
    data_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_revision: str = Field(min_length=7)
    parameters: dict[str, Any] = Field(default_factory=dict)


class TrialReceipt(StrictContract):
    trial_id: str
    hypothesis_id: str
    status: str
    spec_fingerprint: str
    record_hash: str
    metrics: dict[str, Any] = Field(default_factory=dict)


Experiment = Callable[[TrialSpec], Mapping[str, Any]]


class ExperimentRunner:
    """Execute one registered trial and record success or failure.

    This runner does not fit models or decide whether an experiment is valid.
    It provides deterministic input identity and an append-only execution
    receipt. Statistical acceptance remains a separate research step.
    """

    def __init__(self, ledger_path: str | Path) -> None:
        self.ledger_path = Path(ledger_path)

    def run(self, spec: TrialSpec, experiment: Experiment) -> TrialReceipt:
        existing = read_and_verify(self.ledger_path)
        if any(record["trial_id"] == spec.trial_id for record in existing):
            raise FileExistsError(f"trial_id already exists: {spec.trial_id}")

        serialized_spec = spec.model_dump(mode="json")
        canonical_spec = _canonical_json(serialized_spec)
        spec_fingerprint = hashlib.sha256(canonical_spec).hexdigest()

        try:
            raw_metrics = experiment(spec)
            metrics = _normalize_json(dict(raw_metrics))
        except Exception as exc:
            failure_record = {
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
            status="completed",
            spec_fingerprint=spec_fingerprint,
            record_hash=record_hash,
            metrics=metrics,
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
