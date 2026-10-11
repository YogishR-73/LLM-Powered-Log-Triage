"""Deterministic evidence package construction.

This module does not call an LLM, infer causality, select root-cause candidates,
or derive a polarity. It validates and packages explicit upstream evidence.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from typing import Any

from .event_store import EventStore
from .schemas import (
    CandidateEvidence,
    EvidenceItem,
    EvidenceLink,
    EvidencePackage,
    EvidenceType,
)


class EvidenceBuilder:
    """Build traceable evidence packages without modifying upstream artifacts."""

    def __init__(self, event_store: EventStore):
        self._event_store = event_store

    def build_candidate(
        self,
        candidate_event_id: str,
        evidence_links: Iterable[EvidenceLink | Mapping[str, Any]],
        *,
        severity_score: float | None = None,
    ) -> CandidateEvidence:
        """Build evidence for one explicitly selected candidate.

        A link is relevant only when its explicitly supplied ``candidate_event_id``
        matches this candidate. The builder never infers the candidate from edge
        direction. Every relevant link's endpoints must exist in the event store.
        Exact duplicate links are deduplicated so
        repeated upstream records cannot artificially inflate the evidence list.
        """
        candidate = self._event_store.require(candidate_event_id)
        severity_score = self._validate_optional_score(severity_score, "severity_score")

        unique_items: dict[str, EvidenceItem] = {}
        for raw_link in evidence_links:
            link = self._coerce_link(raw_link)
            if link.candidate_event_id != candidate_event_id:
                continue

            # The schema guarantees the candidate is exactly one endpoint.
            related_event_id = self._related_event_id(link, candidate_event_id)
            self._event_store.require(link.source_event_id)
            self._event_store.require(link.target_event_id)

            item = EvidenceItem(
                candidate_event_id=candidate_event_id,
                event_id=related_event_id,
                source_event_id=link.source_event_id,
                target_event_id=link.target_event_id,
                evidence_type=link.evidence_type,
                polarity=link.polarity,
                score=link.score,
                relation=link.relation,
                reason=link.reason,
                metadata=link.metadata,
            )
            key = self._canonical_json(item.model_dump(mode="json"))
            unique_items.setdefault(key, item)

        relevant_items = sorted(unique_items.values(), key=self._item_sort_key)
        supporting_events = sorted(
            {item.event_id for item in relevant_items if item.polarity == "supporting"}
        )
        contradicting_events = sorted(
            {item.event_id for item in relevant_items if item.polarity == "contradicting"}
        )

        return CandidateEvidence(
            candidate_event_id=candidate_event_id,
            candidate=candidate,
            supporting_events=supporting_events,
            contradicting_events=contradicting_events,
            evidence_items=relevant_items,
            temporal_score=self._max_score(
                relevant_items, EvidenceType.TEMPORAL, "supporting"
            ),
            semantic_score=self._max_score(
                relevant_items, EvidenceType.SEMANTIC, "supporting"
            ),
            dependency_score=self._max_score(
                relevant_items, EvidenceType.DEPENDENCY, "supporting"
            ),
            severity_score=severity_score,
            contradiction_score=self._max_score_any_polarity(
                relevant_items, "contradicting"
            ),
        )

    def build_package(
        self,
        incident_id: str,
        candidate_event_ids: Iterable[str],
        evidence_links: Iterable[EvidenceLink | Mapping[str, Any]],
        *,
        severity_scores: Mapping[str, float] | None = None,
    ) -> EvidencePackage:
        """Build evidence for explicitly selected candidates in stable input order."""
        candidate_ids: list[str] = []
        seen: set[str] = set()
        for candidate_event_id in candidate_event_ids:
            if not isinstance(candidate_event_id, str) or not candidate_event_id.strip():
                raise ValueError("candidate_event_ids must contain non-empty strings")
            if candidate_event_id != candidate_event_id.strip():
                raise ValueError("candidate_event_ids must not have surrounding whitespace")
            if candidate_event_id not in seen:
                seen.add(candidate_event_id)
                candidate_ids.append(candidate_event_id)

        links = list(evidence_links)
        score_map = severity_scores if severity_scores is not None else {}
        candidates = [
            self.build_candidate(
                candidate_event_id,
                links,
                severity_score=score_map.get(candidate_event_id),
            )
            for candidate_event_id in candidate_ids
        ]
        return EvidencePackage(incident_id=incident_id, candidates=candidates)

    @staticmethod
    def _coerce_link(link: EvidenceLink | Mapping[str, Any]) -> EvidenceLink:
        if isinstance(link, EvidenceLink):
            return link
        if isinstance(link, Mapping):
            return EvidenceLink.model_validate(link)
        raise TypeError(f"Unsupported evidence link type: {type(link).__name__}")

    @staticmethod
    def _related_event_id(link: EvidenceLink, candidate_event_id: str) -> str:
        if link.candidate_event_id != candidate_event_id:
            raise ValueError("Evidence link is not scoped to this candidate")
        if link.source_event_id == candidate_event_id:
            return link.target_event_id
        if link.target_event_id == candidate_event_id:
            return link.source_event_id
        # EvidenceLink validation should make this unreachable; keep the boundary safe.
        raise ValueError("candidate_event_id must be one endpoint of the evidence link")

    @staticmethod
    def _validate_optional_score(value: float | None, field_name: str) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{field_name} must be a finite number between 0 and 1")
        score = float(value)
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise ValueError(f"{field_name} must be a finite number between 0 and 1")
        return score

    @staticmethod
    def _canonical_json(value: Any) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

    @classmethod
    def _item_sort_key(cls, item: EvidenceItem) -> tuple[Any, ...]:
        return (
            0 if item.polarity == "supporting" else 1,
            item.evidence_type.value,
            -item.score,
            item.event_id,
            item.source_event_id,
            item.target_event_id,
            item.relation,
            item.reason or "",
            cls._canonical_json(item.metadata),
        )

    @staticmethod
    def _max_score(
        items: Iterable[EvidenceItem],
        evidence_type: EvidenceType,
        polarity: str,
    ) -> float | None:
        scores = [
            item.score
            for item in items
            if item.evidence_type == evidence_type and item.polarity == polarity
        ]
        return max(scores) if scores else None

    @staticmethod
    def _max_score_any_polarity(
        items: Iterable[EvidenceItem], polarity: str
    ) -> float | None:
        scores = [item.score for item in items if item.polarity == polarity]
        return max(scores) if scores else None
