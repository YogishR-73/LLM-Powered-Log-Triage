"""Validated data contracts for the deterministic evidence layer.
Important: ``polarity`` is always interpreted relative to ``candidate_event_id``.
A directional relation is not, by itself, proof of causation.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EvidenceType(str, Enum):
    """Kind of signal represented by an evidence relationship."""

    TEMPORAL = "temporal"
    SEMANTIC = "semantic"
    DEPENDENCY = "dependency"


def _validate_identifier(value: str, field_name: str) -> str:
    """Reject blank or padded identifiers instead of silently rewriting them."""
    if not value or not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    if value != value.strip():
        raise ValueError(f"{field_name} must not have leading or trailing whitespace")
    return value


class _FrozenDict(dict):
    """A JSON-serializable dict that rejects in-place mutation."""

    @staticmethod
    def _immutable(*args: Any, **kwargs: Any) -> None:
        raise TypeError("evidence metadata is immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable
    __ior__ = _immutable

    def __copy__(self):
        return self

    def __deepcopy__(self, memo: dict[int, Any]):
        memo[id(self)] = self
        return self


class _FrozenList(list):
    """A JSON-serializable list that rejects in-place mutation."""

    @staticmethod
    def _immutable(*args: Any, **kwargs: Any) -> None:
        raise TypeError("evidence metadata is immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    append = _immutable
    clear = _immutable
    extend = _immutable
    insert = _immutable
    pop = _immutable
    remove = _immutable
    reverse = _immutable
    sort = _immutable
    __iadd__ = _immutable
    __imul__ = _immutable

    def __copy__(self):
        return self

    def __deepcopy__(self, memo: dict[int, Any]):
        memo[id(self)] = self
        return self


def _freeze_json(value: Any) -> Any:
    """Recursively freeze JSON containers while preserving JSON serialization."""
    if isinstance(value, dict):
        return _FrozenDict({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return _FrozenList(_freeze_json(item) for item in value)
    return value


def _copy_json_object(value: Any) -> Any:
    """Validate JSON compatibility and make a detached, deterministic copy."""
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("metadata must be a JSON object")
    try:
        encoded = json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        copied = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise ValueError("metadata must contain only JSON-serializable values") from exc
    if not isinstance(copied, dict):  # Defensive; the Mapping check already implies this.
        raise ValueError("metadata must be a JSON object")
    return copied


class EventSnapshot(BaseModel):
    """Small, validated view of an event suitable for evidence references.
    ``message`` and ``template`` may still contain sensitive log content. This
    model is not a redaction boundary; sanitize secrets before constructing it
    if the underlying logs may contain credentials or personal data.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(min_length=1)
    timestamp_iso: str | None = None
    severity: str | None = None
    service: str | None = None
    message: str
    template: str | None = None
    source_file: str | None = None
    line_number: int | None = Field(default=None, ge=1, strict=True)

    @field_validator("event_id")
    @classmethod
    def validate_event_id(cls, value: str) -> str:
        return _validate_identifier(value, "event_id")

    @field_validator("timestamp_iso")
    @classmethod
    def validate_timestamp_iso(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value != value.strip() or not ("T" in value or " " in value):
            raise ValueError("timestamp_iso must be a valid ISO-8601 datetime")
        try:
            # Match Member 1's canonical LogEvent contract: timestamps must be
            # timezone-aware so temporal comparisons never mix local/UTC values.
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("timestamp_iso must be a valid ISO-8601 datetime") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timestamp_iso must include a UTC offset")
        return value


class EvidenceLink(BaseModel):
    """Directional relationship whose polarity is scoped to one candidate.
    ``candidate_event_id`` is required because relation direction varies by
    evidence type. The producer must state which candidate the polarity is
    about; the builder never guesses from source/target direction.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_event_id: str = Field(min_length=1)
    target_event_id: str = Field(min_length=1)
    candidate_event_id: str
    evidence_type: EvidenceType
    polarity: Literal["supporting", "contradicting"]
    score: float = Field(strict=True, ge=0.0, le=1.0, allow_inf_nan=False)
    relation: str = Field(min_length=1)
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_event_id", "target_event_id", "candidate_event_id")
    @classmethod
    def validate_ids(cls, value: str, info: Any) -> str:
        return _validate_identifier(value, info.field_name)

    @field_validator("relation")
    @classmethod
    def validate_relation(cls, value: str) -> str:
        return _validate_identifier(value, "relation")

    @field_validator("metadata", mode="before")
    @classmethod
    def validate_metadata(cls, value: Any) -> dict[str, Any]:
        return _copy_json_object(value)

    @field_validator("metadata", mode="after")
    @classmethod
    def freeze_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _freeze_json(value)

    @model_validator(mode="after")
    def validate_relationship(self) -> "EvidenceLink":
        if self.source_event_id == self.target_event_id:
            raise ValueError("source_event_id and target_event_id must differ")
        if self.candidate_event_id not in {self.source_event_id, self.target_event_id}:
            raise ValueError(
                "candidate_event_id must match source_event_id or target_event_id"
            )
        # Freeze at model-validation time as well as field-validation time.
        # This guarantees that the final value stored by Pydantic is deeply
        # immutable even if a Pydantic version normalizes dict subclasses.
        object.__setattr__(self, "metadata", _freeze_json(self.metadata))
        return self


class EvidenceItem(BaseModel):
    """Validated evidence retained for a single candidate.
    Both endpoints are kept so temporal/dependency direction is not lost when
    the link is converted into an evidence package.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_event_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)  # The endpoint other than the candidate.
    source_event_id: str = Field(min_length=1)
    target_event_id: str = Field(min_length=1)
    evidence_type: EvidenceType
    polarity: Literal["supporting", "contradicting"]
    score: float = Field(strict=True, ge=0.0, le=1.0, allow_inf_nan=False)
    relation: str = Field(min_length=1)
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("candidate_event_id", "event_id", "source_event_id", "target_event_id")
    @classmethod
    def validate_ids(cls, value: str, info: Any) -> str:
        return _validate_identifier(value, info.field_name)

    @field_validator("relation")
    @classmethod
    def validate_relation(cls, value: str) -> str:
        return _validate_identifier(value, "relation")

    @field_validator("metadata", mode="before")
    @classmethod
    def validate_metadata(cls, value: Any) -> dict[str, Any]:
        return _copy_json_object(value)

    @field_validator("metadata", mode="after")
    @classmethod
    def freeze_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _freeze_json(value)

    @model_validator(mode="after")
    def validate_relationship(self) -> "EvidenceItem":
        if self.source_event_id == self.target_event_id:
            raise ValueError("source_event_id and target_event_id must differ")
        if self.candidate_event_id == self.source_event_id:
            expected_related = self.target_event_id
        elif self.candidate_event_id == self.target_event_id:
            expected_related = self.source_event_id
        else:
            raise ValueError(
                "candidate_event_id must match source_event_id or target_event_id"
            )
        if self.event_id != expected_related:
            raise ValueError("event_id must identify the endpoint other than the candidate")
        # Ensure nested dict/list containers remain immutable after validation.
        object.__setattr__(self, "metadata", _freeze_json(self.metadata))
        return self


class CandidateEvidence(BaseModel):
    """All traceable evidence collected for one explicitly selected candidate.

    The model and its collection fields are immutable so the summary lists cannot
    drift out of sync with ``evidence_items`` after validation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_event_id: str = Field(min_length=1)
    candidate: EventSnapshot
    supporting_events: tuple[str, ...] = Field(default_factory=tuple)
    contradicting_events: tuple[str, ...] = Field(default_factory=tuple)
    evidence_items: tuple[EvidenceItem, ...] = Field(default_factory=tuple)

    temporal_score: float | None = Field(default=None, strict=True, ge=0.0, le=1.0, allow_inf_nan=False)
    semantic_score: float | None = Field(default=None, strict=True, ge=0.0, le=1.0, allow_inf_nan=False)
    dependency_score: float | None = Field(default=None, strict=True, ge=0.0, le=1.0, allow_inf_nan=False)
    severity_score: float | None = Field(default=None, strict=True, ge=0.0, le=1.0, allow_inf_nan=False)
    contradiction_score: float | None = Field(default=None, strict=True, ge=0.0, le=1.0, allow_inf_nan=False)

    @field_validator("candidate_event_id")
    @classmethod
    def validate_candidate_id(cls, value: str) -> str:
        return _validate_identifier(value, "candidate_event_id")

    @model_validator(mode="after")
    def validate_summary_fields(self) -> "CandidateEvidence":
        if self.candidate_event_id != self.candidate.event_id:
            raise ValueError("candidate_event_id must equal candidate.event_id")
        if any(item.candidate_event_id != self.candidate_event_id for item in self.evidence_items):
            raise ValueError("every evidence item must belong to candidate_event_id")

        fingerprints = [
            json.dumps(
                item.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            for item in self.evidence_items
        ]
        if len(fingerprints) != len(set(fingerprints)):
            raise ValueError("evidence_items must not contain exact duplicate records")

        expected_support = tuple(
            sorted(
                {item.event_id for item in self.evidence_items if item.polarity == "supporting"}
            )
        )
        expected_contradiction = tuple(
            sorted(
                {item.event_id for item in self.evidence_items if item.polarity == "contradicting"}
            )
        )
        if self.supporting_events != expected_support:
            raise ValueError("supporting_events must match supporting evidence_items")
        if self.contradicting_events != expected_contradiction:
            raise ValueError("contradicting_events must match contradicting evidence_items")

        expected_scores = {
            "temporal_score": self._max_score(EvidenceType.TEMPORAL, "supporting"),
            "semantic_score": self._max_score(EvidenceType.SEMANTIC, "supporting"),
            "dependency_score": self._max_score(EvidenceType.DEPENDENCY, "supporting"),
            "contradiction_score": self._max_score_any_polarity("contradicting"),
        }
        for field_name, expected in expected_scores.items():
            if getattr(self, field_name) != expected:
                raise ValueError(f"{field_name} must match the scores in evidence_items")
        return self

    def _max_score(self, evidence_type: EvidenceType, polarity: str) -> float | None:
        scores = [
            item.score
            for item in self.evidence_items
            if item.evidence_type == evidence_type and item.polarity == polarity
        ]
        return max(scores) if scores else None

    def _max_score_any_polarity(self, polarity: str) -> float | None:
        scores = [item.score for item in self.evidence_items if item.polarity == polarity]
        return max(scores) if scores else None


class EvidencePackage(BaseModel):
    """Incident-level evidence package passed to downstream RCA stages.

    The candidate collection is a tuple so a validated package cannot be changed
    in place after construction.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    incident_id: str = Field(min_length=1)
    candidates: tuple[CandidateEvidence, ...] = Field(default_factory=tuple)

    @field_validator("incident_id")
    @classmethod
    def validate_incident_id(cls, value: str) -> str:
        return _validate_identifier(value, "incident_id")

    @model_validator(mode="after")
    def reject_duplicate_candidates(self) -> "EvidencePackage":
        ids = [candidate.candidate_event_id for candidate in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate_event_id values must be unique within an evidence package")
        return self
