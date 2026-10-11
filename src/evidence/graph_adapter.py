"""Adapters from upstream directed graphs to explicit EvidenceLinks.

Graph structure alone does not determine evidence polarity. Each annotation
must name the candidate event, polarity, and score explicitly. The adapter
checks that the annotated relation exists, preserves direction, and attaches
only a small set of useful graph attributes.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
import math
from typing import Any, Protocol

from .schemas import EvidenceLink, EvidenceType


class DirectedGraphLike(Protocol):
    nodes: Any
    edges: Any

    def is_directed(self) -> bool: ...

    def has_edge(self, u: Any, v: Any) -> bool: ...

    def get_edge_data(self, u: Any, v: Any, default: Any = None) -> Any: ...


_ALLOWED_ANNOTATION_KEYS = {
    "source_event_id",
    "target_event_id",
    "candidate_event_id",
    "polarity",
    "score",
    "reason",
    "metadata",
}


def _annotation(raw: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("Evidence annotation must be a mapping/object")
    unknown = set(raw) - _ALLOWED_ANNOTATION_KEYS
    if unknown:
        names = ", ".join(sorted(str(name) for name in unknown))
        raise ValueError(f"Unknown evidence annotation field(s): {names}")
    required = {
        "source_event_id",
        "target_event_id",
        "candidate_event_id",
        "polarity",
        "score",
    }
    missing = required - set(raw)
    if missing:
        names = ", ".join(sorted(missing))
        raise ValueError(f"Missing evidence annotation field(s): {names}")
    return dict(raw)


def _metadata_copy(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("evidence annotation metadata must be a JSON object")
    return dict(value)




def _require_directed_graph(graph: DirectedGraphLike, graph_name: str) -> None:
    """Reject graph inputs whose edge direction cannot be trusted."""
    is_directed = getattr(graph, "is_directed", None)
    if not callable(is_directed) or not is_directed():
        raise ValueError(f"{graph_name} must be a directed graph")


def _validate_time_delta(value: Any) -> float:
    """Validate and normalize a temporal edge delta as a finite float."""
    error = "time_delta_seconds must be a finite non-negative number"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(error)

    # math.isfinite(value) can itself raise OverflowError for huge Python ints.
    # Convert under an exception boundary, then validate the normalized float.
    try:
        normalized = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(error) from exc

    if not math.isfinite(normalized) or normalized < 0:
        raise ValueError(error)
    return normalized


def _set_graph_metadata(
    metadata: dict[str, Any], values: Mapping[str, Any]
) -> None:
    """Set authoritative graph-derived fields and reject conflicting overrides."""
    for key, graph_value in values.items():
        if key in metadata and metadata[key] != graph_value:
            raise ValueError(
                f"Evidence annotation metadata field {key!r} conflicts with graph data"
            )
        metadata[key] = graph_value


def temporal_links_from_graph(
    temporal_graph: DirectedGraphLike,
    annotations: Iterable[Mapping[str, Any]],
) -> list[EvidenceLink]:
    """Convert explicitly annotated directed temporal edges.

    Reversed edges are not silently considered equivalent. ``polarity`` remains
    relative to the candidate named by the annotation, not to the edge source.
    """
    _require_directed_graph(temporal_graph, "temporal_graph")
    result: list[EvidenceLink] = []
    for raw in annotations:
        ann = _annotation(raw)
        source = ann["source_event_id"]
        target = ann["target_event_id"]
        if not temporal_graph.has_edge(source, target):
            raise ValueError(
                f"Annotated temporal edge does not exist: {source!r} -> {target!r}"
            )
        edge = temporal_graph.get_edge_data(source, target, default={}) or {}
        metadata = _metadata_copy(ann.get("metadata"))
        graph_metadata: dict[str, Any] = {}
        # Validate any provided delta as well as the graph's authoritative value.
        if "time_delta_seconds" in metadata:
            metadata["time_delta_seconds"] = _validate_time_delta(
                metadata["time_delta_seconds"]
            )
        if edge.get("time_delta_seconds") is not None:
            graph_metadata["time_delta_seconds"] = _validate_time_delta(
                edge["time_delta_seconds"]
            )
        if edge.get("relationship") is not None:
            graph_metadata["graph_relationship"] = str(edge["relationship"])
        _set_graph_metadata(metadata, graph_metadata)
        result.append(
            EvidenceLink(
                source_event_id=source,
                target_event_id=target,
                candidate_event_id=ann["candidate_event_id"],
                evidence_type=EvidenceType.TEMPORAL,
                polarity=ann["polarity"],
                score=ann["score"],
                relation=str(edge.get("relationship") or "temporal_relationship"),
                reason=ann.get("reason"),
                metadata=metadata,
            )
        )
    return result


def dependency_links_from_graphs(
    temporal_graph: DirectedGraphLike,
    dependency_graph: DirectedGraphLike,
    annotations: Iterable[Mapping[str, Any]],
) -> list[EvidenceLink]:
    """Convert explicitly annotated event pairs connected by a service dependency.

    The service graph convention is ``consumer -> dependency`` (for example,
    ``checkout -> database``). The output event edge is normalized to that same
    direction regardless of input endpoint order. Polarity is never inferred.
    """
    _require_directed_graph(temporal_graph, "temporal_graph")
    _require_directed_graph(dependency_graph, "dependency_graph")
    result: list[EvidenceLink] = []
    for raw in annotations:
        ann = _annotation(raw)
        event_a = ann["source_event_id"]
        event_b = ann["target_event_id"]
        try:
            node_a = temporal_graph.nodes[event_a]
            node_b = temporal_graph.nodes[event_b]
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError(
                "Dependency annotation references an unknown event pair: "
                f"{event_a!r}, {event_b!r}"
            ) from exc

        service_a = node_a.get("service")
        service_b = node_b.get("service")
        if not isinstance(service_a, str) or not service_a.strip():
            raise ValueError(f"Event {event_a!r} has no usable service attribute")
        if not isinstance(service_b, str) or not service_b.strip():
            raise ValueError(f"Event {event_b!r} has no usable service attribute")
        if service_a == service_b:
            raise ValueError(
                "Dependency evidence requires distinct services; both events use "
                f"{service_a!r}"
            )

        a_depends_on_b = dependency_graph.has_edge(service_a, service_b)
        b_depends_on_a = dependency_graph.has_edge(service_b, service_a)
        if not a_depends_on_b and not b_depends_on_a:
            raise ValueError(
                f"No service dependency exists between {service_a!r} and {service_b!r}"
            )
        if a_depends_on_b and b_depends_on_a:
            raise ValueError(
                f"Bidirectional service dependency between {service_a!r} and "
                f"{service_b!r} is ambiguous; annotate each direction separately"
            )

        if a_depends_on_b:
            source_event_id, target_event_id = event_a, event_b
            source_service, target_service = service_a, service_b
            edge_data = dependency_graph.get_edge_data(
                service_a, service_b, default={}
            ) or {}
        else:
            source_event_id, target_event_id = event_b, event_a
            source_service, target_service = service_b, service_a
            edge_data = dependency_graph.get_edge_data(
                service_b, service_a, default={}
            ) or {}

        metadata = _metadata_copy(ann.get("metadata"))
        graph_metadata = {
            "source_service": source_service,
            "dependency_service": target_service,
            "dependency_direction": "source_service_depends_on_target_service",
        }
        if edge_data.get("relationship") is not None:
            graph_metadata["graph_relationship"] = str(edge_data["relationship"])
        _set_graph_metadata(metadata, graph_metadata)

        result.append(
            EvidenceLink(
                source_event_id=source_event_id,
                target_event_id=target_event_id,
                candidate_event_id=ann["candidate_event_id"],
                evidence_type=EvidenceType.DEPENDENCY,
                polarity=ann["polarity"],
                score=ann["score"],
                relation=str(edge_data.get("relationship") or "service_dependency"),
                reason=ann.get("reason"),
                metadata=metadata,
            )
        )
    return result
