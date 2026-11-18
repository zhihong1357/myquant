"""Immutable hypothesis preregistration and lifecycle governance."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import Field, model_validator

from myquant.canonical import canonical_json
from myquant.contracts import (
    MultiplicityCorrection,
    StrictContract,
    require_utc,
)
from myquant.files import atomic_replace, create_immutable_file

logger = logging.getLogger(__name__)

__all__ = [
    "ExpectedDirection",
    "HypothesisEvent",
    "HypothesisRegistration",
    "HypothesisRegistry",
    "HypothesisSpec",
    "HypothesisState",
    "MultiplicityCorrection",
    "SampleWindow",
]


class ExpectedDirection(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    TWO_SIDED = "two_sided"


class HypothesisState(StrEnum):
    REGISTERED = "registered"
    TESTING = "testing"
    SUPPORTED = "supported"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"
    RETIRED = "retired"
    SUPERSEDED = "superseded"


class SampleWindow(StrictContract):
    """A half-open UTC interval [start, end)."""

    start: datetime
    end: datetime

    @model_validator(mode="after")
    def validate_window(self) -> SampleWindow:
        start = require_utc(self.start)
        end = require_utc(self.end)
        if end <= start:
            raise ValueError("sample window end must be after start")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        return self


class HypothesisSpec(StrictContract):
    """A complete, predeclared research plan; no mutable dict fields."""

    schema_version: int = Field(default=1, ge=1)
    hypothesis_id: str = Field(pattern=r"^H[0-9]{4,}$")
    title: str = Field(min_length=8)
    research_question: str = Field(min_length=30)
    mechanism: str = Field(min_length=20)
    alternative_hypothesis: str = Field(min_length=20)
    null_hypothesis: str = Field(min_length=20)

    universe: tuple[str, ...] = Field(min_length=1)
    source_versions: tuple[str, ...] = Field(min_length=1)
    observation_frequency: str = Field(min_length=2)
    horizon_seconds: int = Field(gt=0)
    target_definition: str = Field(min_length=12)

    feature_set: tuple[str, ...] = Field(min_length=1)
    model_definition: tuple[str, ...] = Field(min_length=1)
    fixed_parameters: tuple[str, ...] = ()
    benchmark: str = Field(min_length=5)
    cost_model: str = Field(min_length=5)
    cost_assumptions: tuple[str, ...] = Field(min_length=1)

    train_window: SampleWindow
    validation_window: SampleWindow
    holdout_window: SampleWindow
    purge_gap_seconds: int = Field(ge=0)
    minimum_train_observations: int = Field(gt=0)
    minimum_validation_observations: int = Field(gt=0)
    minimum_holdout_observations: int = Field(gt=0)

    primary_metric: str = Field(min_length=5)
    expected_direction: ExpectedDirection
    minimum_effect_size: float = Field(gt=0, allow_inf_nan=False)
    target_error_rate: float = Field(gt=0, lt=1, allow_inf_nan=False)
    multiple_testing_family: str = Field(min_length=5)
    multiple_testing_method: MultiplicityCorrection
    planned_test_count: int = Field(ge=1)

    missing_data_policy: str = Field(min_length=8)
    acceptance_criteria: tuple[str, ...] = Field(min_length=1)
    rejection_criteria: tuple[str, ...] = Field(min_length=1)
    known_confounders: tuple[str, ...] = ()
    exclusions: tuple[str, ...] = ()
    random_seed: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_research_plan(self) -> HypothesisSpec:
        if self.purge_gap_seconds < self.horizon_seconds:
            raise ValueError(
                "purge_gap_seconds must be at least the prediction horizon "
                "to prevent forward-label overlap across sample splits"
            )

        required_validation_start = (
            self.train_window.end + timedelta(seconds=self.purge_gap_seconds)
        )
        if self.validation_window.start < required_validation_start:
            raise ValueError("validation window overlaps the training purge boundary")

        required_holdout_start = (
            self.validation_window.end + timedelta(seconds=self.purge_gap_seconds)
        )
        if self.holdout_window.start < required_holdout_start:
            raise ValueError("holdout window overlaps the validation purge boundary")

        if len(set(self.universe)) != len(self.universe):
            raise ValueError("universe entries must be unique")
        if len(set(self.source_versions)) != len(self.source_versions):
            raise ValueError("source_versions entries must be unique")
        if len(set(self.feature_set)) != len(self.feature_set):
            raise ValueError("feature_set entries must be unique")
        parameter_names: list[str] = []
        for parameter in self.fixed_parameters:
            if "=" not in parameter:
                raise ValueError("fixed_parameters must use the form '<name>=<value>'")
            name, value = parameter.split("=", maxsplit=1)
            if not name.strip() or not value.strip():
                raise ValueError("fixed_parameters require non-empty names and values")
            parameter_names.append(name.strip())
        if len(set(parameter_names)) != len(parameter_names):
            raise ValueError("fixed parameter names must be unique")
        object.__setattr__(
            self,
            "fixed_parameters",
            tuple(sorted(self.fixed_parameters)),
        )

        if len(set(self.model_definition)) != len(self.model_definition):
            raise ValueError("model_definition entries must be unique")
        if len(set(self.acceptance_criteria)) != len(self.acceptance_criteria):
            raise ValueError("acceptance_criteria entries must be unique")
        if len(set(self.rejection_criteria)) != len(self.rejection_criteria):
            raise ValueError("rejection_criteria entries must be unique")

        for source in self.source_versions:
            if not _valid_versioned_identifier(source):
                raise ValueError(
                    "source_versions must use the form '<source_id>@v<positive_integer>'"
                )
        for feature in self.feature_set:
            if not _valid_versioned_identifier(feature):
                raise ValueError(
                    "feature_set entries must use the form '<feature_id>@v<positive_integer>'"
                )

        if self.planned_test_count > 1 and (
            self.multiple_testing_method == MultiplicityCorrection.NONE
        ):
            raise ValueError(
                "multiple planned tests require a predeclared multiple-testing correction"
            )
        return self


class HypothesisRegistration(StrictContract):
    schema_version: int = Field(default=1, ge=1)
    version: int = Field(ge=1)
    registered_at: datetime
    supersedes_version: int | None = Field(default=None, ge=1)
    amendment_reason: str | None = None
    spec: HypothesisSpec
    spec_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    registration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_registration(self) -> HypothesisRegistration:
        object.__setattr__(self, "registered_at", require_utc(self.registered_at))
        if self.supersedes_version is None and self.amendment_reason is not None:
            raise ValueError("amendment_reason requires supersedes_version")
        if self.supersedes_version is not None and not self.amendment_reason:
            raise ValueError("amended registrations require a non-empty amendment_reason")
        if self.supersedes_version is not None and self.supersedes_version >= self.version:
            raise ValueError("supersedes_version must be lower than version")
        return self


class HypothesisEvent(StrictContract):
    hypothesis_id: str
    version: int = Field(ge=1)
    from_state: HypothesisState | None = None
    to_state: HypothesisState
    reason: str = Field(min_length=5)
    recorded_at: datetime
    previous_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    event_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_recorded_at(self) -> HypothesisEvent:
        object.__setattr__(self, "recorded_at", require_utc(self.recorded_at))
        return self


GENESIS_EVENT_HASH = "0" * 64


class HypothesisRegistry:
    """Immutable registration snapshots plus a hash-chained state-event log.

    Amendments are allowed only while the previous version is still REGISTERED,
    before any trial has started. Once a version enters TESTING, its contents
    are frozen permanently; a material change requires a new hypothesis ID.

    This is a local single-writer research registry, not a distributed database.

    Like the trial ledger, the event hash chain detects tampering with
    events that are still present but not deletion of trailing events.
    Use :meth:`write_event_anchor` to publish the latest event hash (and
    event count) to an independent anchor file and pass that file to
    :meth:`read_events` so truncation is detected as a mismatch against
    the anchor. Every operation replays and re-validates the full event
    log, so n events cost O(n^2) time in total.
    """

    _TRANSITIONS: dict[HypothesisState, frozenset[HypothesisState]] = {
        HypothesisState.REGISTERED: frozenset(
            {HypothesisState.TESTING, HypothesisState.RETIRED, HypothesisState.SUPERSEDED}
        ),
        HypothesisState.TESTING: frozenset(
            {
                HypothesisState.SUPPORTED,
                HypothesisState.REJECTED,
                HypothesisState.INCONCLUSIVE,
                HypothesisState.RETIRED,
            }
        ),
        HypothesisState.SUPPORTED: frozenset(),
        HypothesisState.REJECTED: frozenset(),
        HypothesisState.INCONCLUSIVE: frozenset(),
        HypothesisState.RETIRED: frozenset(),
        HypothesisState.SUPERSEDED: frozenset(),
    }

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.registration_root = self.root / "registrations"
        self.events_path = self.root / "hypothesis-events.jsonl"

    def register(
        self,
        spec: HypothesisSpec,
        *,
        amendment_reason: str | None = None,
    ) -> HypothesisRegistration:
        """Register v1 or issue a pre-trial amendment as a new immutable version."""
        # Normalize through validation before anything else: model_copy()
        # bypasses the spec validator, so a spec built that way can carry
        # unsorted fixed_parameters. get() re-validates on read and would
        # then reject the stored fingerprint. Fingerprinting the canonical
        # validated form keeps register/get consistent.
        spec = HypothesisSpec.model_validate(spec.model_dump(mode="json"))
        # Fail closed before creating any new registration if the shared audit
        # log or any previously registered snapshot is corrupt.
        existing_events = self.read_events()
        directory = self.registration_root / spec.hypothesis_id
        existing_versions = self._versions(spec.hypothesis_id)
        registered_event_versions = {
            (event.hypothesis_id, event.version) for event in existing_events
        }
        for existing_version in existing_versions:
            if (spec.hypothesis_id, existing_version) not in registered_event_versions:
                raise ValueError(
                    f"registration v{existing_version} has no lifecycle event; "
                    "use repair_orphan_registration to append the missing "
                    "event with an audit reason"
                )
        serialized_spec = spec.model_dump(mode="json")
        spec_fingerprint = hashlib.sha256(
            canonical_json(serialized_spec)
        ).hexdigest()

        if not existing_versions:
            if amendment_reason is not None:
                raise ValueError(
                    "amendment_reason is only valid when amending an existing version"
                )
            version = 1
            supersedes_version = None
        else:
            latest_version = max(existing_versions)
            latest = self.get(spec.hypothesis_id, version=latest_version)
            current_state = self.get_state(spec.hypothesis_id, latest_version)
            if current_state != HypothesisState.REGISTERED:
                raise PermissionError(
                    "a hypothesis cannot be amended after testing has started; "
                    "create a new hypothesis ID"
                )
            if latest.spec_fingerprint == spec_fingerprint:
                raise ValueError("amendment does not change the preregistered specification")
            if not amendment_reason or len(amendment_reason.strip()) < 10:
                raise ValueError(
                    "a pre-trial amendment requires a reason of at least 10 characters"
                )
            version = latest_version + 1
            supersedes_version = latest.version

        registration_payload: dict[str, Any] = {
            "schema_version": 1,
            "version": version,
            "registered_at": datetime.now(UTC),
            "supersedes_version": supersedes_version,
            "amendment_reason": amendment_reason,
            "spec": serialized_spec,
            "spec_fingerprint": spec_fingerprint,
        }
        draft = HypothesisRegistration(
            **registration_payload,
            registration_hash=GENESIS_EVENT_HASH,
        )
        hash_payload = draft.model_dump(
            mode="json",
            exclude={"registration_hash"},
        )
        registration_hash = hashlib.sha256(
            canonical_json(hash_payload)
        ).hexdigest()
        registration = draft.model_copy(
            update={"registration_hash": registration_hash}
        )

        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"v{version}.json"
        create_immutable_file(
            target,
            canonical_json(registration.model_dump(mode="json")) + b"\n",
        )

        self._append_event(
            hypothesis_id=spec.hypothesis_id,
            version=version,
            from_state=None,
            to_state=HypothesisState.REGISTERED,
            reason=(
                "Initial preregistration."
                if supersedes_version is None
                else f"Pre-trial amendment: {amendment_reason}"
            ),
        )
        if supersedes_version is not None:
            self._append_event(
                hypothesis_id=spec.hypothesis_id,
                version=supersedes_version,
                from_state=HypothesisState.REGISTERED,
                to_state=HypothesisState.SUPERSEDED,
                reason=f"Superseded by version {version}.",
            )
        logger.info(
            "registered hypothesis %s v%s", spec.hypothesis_id, version
        )
        return registration

    def repair_orphan_registration(
        self,
        hypothesis_id: str,
        version: int,
        *,
        reason: str,
    ) -> HypothesisEvent:
        """Append the missing REGISTERED event for a crash-orphaned snapshot.

        `register` writes the immutable snapshot before appending its
        lifecycle event, so a crash between the two steps leaves a snapshot
        with no event. Such an orphan blocks all further registrations for
        the hypothesis. This repair appends the missing event with an
        explicit audit reason; it never modifies the snapshot itself.

        If the orphaned version supersedes an older version, the missing
        SUPERSEDED event for that older version is appended as well, so the
        registry reaches the state `register` would have produced.
        """
        if len(reason.strip()) < 10:
            raise ValueError(
                "orphan repair requires a reason of at least 10 characters"
            )
        registration = self.get(hypothesis_id, version=version)
        events = self.read_events()
        if any(
            event.hypothesis_id == hypothesis_id and event.version == version
            for event in events
        ):
            raise ValueError(
                f"registration v{version} already has lifecycle events; "
                "repair is only for orphaned snapshots"
            )
        supersedes_version = registration.supersedes_version
        if supersedes_version is not None:
            superseded_state = self.get_state(hypothesis_id, supersedes_version)
            if superseded_state != HypothesisState.REGISTERED:
                raise ValueError(
                    f"cannot repair orphan v{version}: superseded version "
                    f"v{supersedes_version} is {superseded_state.value}, "
                    "not REGISTERED"
                )
        event = self._append_event(
            hypothesis_id=hypothesis_id,
            version=version,
            from_state=None,
            to_state=HypothesisState.REGISTERED,
            reason=f"Orphan repair: {reason.strip()}",
        )
        if supersedes_version is not None:
            self._append_event(
                hypothesis_id=hypothesis_id,
                version=supersedes_version,
                from_state=HypothesisState.REGISTERED,
                to_state=HypothesisState.SUPERSEDED,
                reason=f"Superseded by version {version} (orphan repair).",
            )
        logger.warning(
            "repaired orphan registration %s v%s", hypothesis_id, version
        )
        return event

    def get(
        self,
        hypothesis_id: str,
        *,
        version: int | None = None,
    ) -> HypothesisRegistration:
        _validate_hypothesis_id(hypothesis_id)
        selected_version = (
            self.latest_version(hypothesis_id)
            if version is None
            else version
        )
        if selected_version < 1:
            raise ValueError("version must be >= 1")

        path = (
            self.registration_root
            / hypothesis_id
            / f"v{selected_version}.json"
        )
        raw = json.loads(path.read_text(encoding="utf-8"))
        supplied_hash = raw.pop("registration_hash", None)
        actual_hash = hashlib.sha256(canonical_json(raw)).hexdigest()
        if supplied_hash != actual_hash:
            raise ValueError("hypothesis registration integrity check failed")

        registration = HypothesisRegistration.model_validate(
            {**raw, "registration_hash": supplied_hash}
        )
        if registration.spec.hypothesis_id != hypothesis_id:
            raise ValueError("registration hypothesis_id does not match its storage path")
        if registration.version != selected_version:
            raise ValueError("registration version does not match its storage path")

        expected_spec_fingerprint = hashlib.sha256(
            canonical_json(registration.spec.model_dump(mode="json"))
        ).hexdigest()
        if registration.spec_fingerprint != expected_spec_fingerprint:
            raise ValueError("hypothesis spec fingerprint mismatch")
        return registration

    def latest_version(self, hypothesis_id: str) -> int:
        versions = self._versions(hypothesis_id)
        if not versions:
            raise FileNotFoundError(f"hypothesis is not registered: {hypothesis_id}")
        return max(versions)

    def get_state(self, hypothesis_id: str, version: int) -> HypothesisState:
        events = self.read_events()
        matching = [
            event for event in events
            if event.hypothesis_id == hypothesis_id and event.version == version
        ]
        if not matching:
            raise FileNotFoundError(
                f"no lifecycle events found for {hypothesis_id} version {version}"
            )
        return matching[-1].to_state

    def transition(
        self,
        hypothesis_id: str,
        version: int,
        to_state: HypothesisState,
        *,
        reason: str,
    ) -> HypothesisEvent:
        """Apply one legal lifecycle transition; terminal states cannot reopen."""
        latest_version = self.latest_version(hypothesis_id)
        if version != latest_version:
            raise PermissionError("only the latest hypothesis version may change state")
        current_state = self.get_state(hypothesis_id, version)
        allowed = self._TRANSITIONS[current_state]
        if to_state not in allowed:
            raise ValueError(
                f"invalid hypothesis transition: {current_state.value} -> {to_state.value}"
            )
        if len(reason.strip()) < 5:
            raise ValueError("transition reason must contain at least five characters")
        event = self._append_event(
            hypothesis_id=hypothesis_id,
            version=version,
            from_state=current_state,
            to_state=to_state,
            reason=reason,
        )
        logger.info(
            "hypothesis %s v%s: %s -> %s",
            hypothesis_id,
            version,
            current_state.value,
            to_state.value,
        )
        return event

    def assert_runnable(
        self,
        hypothesis_id: str,
        version: int,
        spec_fingerprint: str,
    ) -> HypothesisRegistration:
        """Verify exact preregistered identity and lock it before trial execution."""
        if version != self.latest_version(hypothesis_id):
            raise PermissionError("trial references a superseded hypothesis version")
        registration = self.get(hypothesis_id, version=version)
        if registration.spec_fingerprint != spec_fingerprint:
            raise PermissionError("trial hypothesis fingerprint does not match preregistration")
        state = self.get_state(hypothesis_id, version)
        if state == HypothesisState.REGISTERED:
            self.transition(
                hypothesis_id,
                version,
                HypothesisState.TESTING,
                reason="First experiment execution started.",
            )
        elif state != HypothesisState.TESTING:
            raise PermissionError(
                f"hypothesis is not open for trials (state={state.value})"
            )
        return registration

    def read_events(
        self,
        *,
        anchor_path: str | Path | None = None,
    ) -> list[HypothesisEvent]:
        """Verify the event hash chain and replay legal state transitions.

        Without an anchor this verifies tampering only: a truncated event
        log still verifies. With ``anchor_path``, the event count and
        latest event hash are additionally compared against the anchor, so
        deleting trailing events is detected. A missing or malformed
        anchor file fails closed.
        """
        if not self.events_path.exists():
            events: list[HypothesisEvent] = []
        else:
            events = []
            expected_previous = GENESIS_EVENT_HASH
            states: dict[tuple[str, int], HypothesisState] = {}

            for line_number, raw_line in enumerate(
                self.events_path.read_bytes().splitlines(),
                start=1,
            ):
                if not raw_line:
                    continue
                raw = json.loads(raw_line)
                supplied_hash = raw.pop("event_hash", None)
                if raw.get("previous_hash") != expected_previous:
                    raise ValueError(f"broken hypothesis event chain at line {line_number}")
                actual_hash = hashlib.sha256(canonical_json(raw)).hexdigest()
                if supplied_hash != actual_hash:
                    raise ValueError(f"hypothesis event hash mismatch at line {line_number}")
                event = HypothesisEvent.model_validate(
                    {**raw, "event_hash": supplied_hash}
                )
                registration_path = (
                    self.registration_root
                    / event.hypothesis_id
                    / f"v{event.version}.json"
                )
                if not registration_path.exists():
                    raise ValueError(
                        f"hypothesis event references missing registration "
                        f"{event.hypothesis_id} v{event.version}"
                    )
                self.get(event.hypothesis_id, version=event.version)

                key = (event.hypothesis_id, event.version)
                current_state = states.get(key)
                if event.from_state != current_state:
                    raise ValueError(
                        f"invalid lifecycle history at line {line_number}: "
                        "from_state does not match the prior event"
                    )
                if current_state is None:
                    if event.to_state != HypothesisState.REGISTERED:
                        raise ValueError(
                            f"invalid lifecycle history at line {line_number}: "
                            "first event must register the hypothesis"
                        )
                elif event.to_state not in self._TRANSITIONS[current_state]:
                    raise ValueError(
                        f"invalid lifecycle transition in event log at line {line_number}"
                    )

                states[key] = event.to_state
                events.append(event)
                expected_previous = supplied_hash

        if anchor_path is not None:
            anchor = _read_event_anchor(Path(anchor_path))
            latest_hash = events[-1].event_hash if events else GENESIS_EVENT_HASH
            if (
                anchor["event_count"] != len(events)
                or anchor["latest_event_hash"] != latest_hash
            ):
                raise ValueError(
                    "hypothesis event log does not match its anchor: anchor "
                    f"records {anchor['event_count']} event(s) ending at "
                    f"{anchor['latest_event_hash']}, event log has "
                    f"{len(events)} event(s) ending at {latest_hash}; "
                    "the event log may have been truncated"
                )
        return events

    def write_event_anchor(
        self,
        anchor_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Publish the event log's latest event hash to an anchor file.

        The anchor records the event count and latest event hash. Store it
        somewhere the event-log writer cannot silently rewrite — for
        example, committed to version control or on another machine — and
        pass it to :meth:`read_events` to detect truncation of trailing
        events. The event log is fully verified before the anchor is
        written; a corrupt log produces no anchor. Returns the anchor
        payload. This mirrors :func:`myquant.registry.write_anchor`.
        """
        anchor = (
            Path(anchor_path)
            if anchor_path is not None
            else _default_event_anchor_path(self.events_path)
        )
        events = self.read_events()
        payload: dict[str, Any] = {
            "schema_version": 1,
            "event_file": self.events_path.name,
            "event_count": len(events),
            "latest_event_hash": (
                events[-1].event_hash if events else GENESIS_EVENT_HASH
            ),
            "anchored_at": datetime.now(UTC).isoformat(),
        }
        atomic_replace(anchor, canonical_json(payload) + b"\n")
        return payload

    def _versions(self, hypothesis_id: str) -> list[int]:
        _validate_hypothesis_id(hypothesis_id)
        directory = self.registration_root / hypothesis_id
        if not directory.exists():
            return []
        versions: list[int] = []
        for path in directory.glob("v*.json"):
            suffix = path.stem[1:]
            if suffix.isdigit() and int(suffix) >= 1:
                versions.append(int(suffix))
        return sorted(set(versions))

    def _append_event(
        self,
        *,
        hypothesis_id: str,
        version: int,
        from_state: HypothesisState | None,
        to_state: HypothesisState,
        reason: str,
    ) -> HypothesisEvent:
        events = self.read_events()
        previous_hash = events[-1].event_hash if events else GENESIS_EVENT_HASH
        draft = HypothesisEvent(
            hypothesis_id=hypothesis_id,
            version=version,
            from_state=from_state,
            to_state=to_state,
            reason=reason,
            recorded_at=datetime.now(UTC),
            previous_hash=previous_hash,
            event_hash=GENESIS_EVENT_HASH,
        )
        hash_payload = draft.model_dump(
            mode="json",
            exclude={"event_hash"},
        )
        event_hash = hashlib.sha256(
            canonical_json(hash_payload)
        ).hexdigest()
        event = draft.model_copy(update={"event_hash": event_hash})
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("ab") as stream:
            stream.write(canonical_json(event.model_dump(mode="json")) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        return event

def _default_event_anchor_path(events_path: Path) -> Path:
    return Path(str(events_path) + ".anchor")


def _read_event_anchor(anchor: Path) -> dict[str, Any]:
    # Mirrors myquant.registry._read_anchor with event-log field names.
    if not anchor.exists():
        raise FileNotFoundError(f"anchor file not found: {anchor}")
    try:
        payload = json.loads(anchor.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"anchor file is not valid JSON: {anchor}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError(f"anchor file has an unsupported format: {anchor}")
    event_count = payload.get("event_count")
    latest_hash = payload.get("latest_event_hash")
    if (
        not isinstance(event_count, int)
        or isinstance(event_count, bool)
        or event_count < 0
        or not isinstance(latest_hash, str)
        or len(latest_hash) != 64
        or any(char not in "0123456789abcdef" for char in latest_hash)
    ):
        raise ValueError(f"anchor file contains invalid record data: {anchor}")
    return payload


def _valid_versioned_identifier(value: str) -> bool:
    if "@v" not in value:
        return False
    identifier, version_text = value.rsplit("@v", maxsplit=1)
    if not identifier or not version_text.isdigit():
        return False
    if int(version_text) < 1:
        return False
    return all(char.isalnum() or char in "._:-/" for char in identifier)


def _validate_hypothesis_id(value: str) -> None:
    if len(value) < 5 or value[0] != "H" or not value[1:].isdigit():
        raise ValueError("hypothesis_id must match H followed by at least four digits")
