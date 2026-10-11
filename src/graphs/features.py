"""Extract temporal, dependency-structure, and propagation features for RCA."""
from __future__ import annotations

import math
from typing import Any

import networkx as nx


def _require_directed(graph: nx.Graph, name: str) -> None:
    if not graph.is_directed():
        raise ValueError(f"{name} must be a directed graph")


def _validated_delta(value: Any, *, field: str = "time_delta_seconds") -> float | None:
    if value is None:
        return None
    error = f"{field} must be a finite non-negative number"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(error)
    try:
        normalized = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(error) from exc
    if not math.isfinite(normalized) or normalized < 0:
        raise ValueError(error)
    return normalized


def _proximity(delta: float | None) -> float:
    return 1.0 / (1.0 + delta) if delta is not None else 0.0


def extract_temporal_features(graph: nx.DiGraph) -> list[dict[str, Any]]:
    _require_directed(graph, "temporal graph")
    features = []
    for source, target, data in graph.edges(data=True):
        delta = _validated_delta(data.get("time_delta_seconds"))
        features.append({
            "source_event": source, "target_event": target,
            "time_delta_seconds": delta, "temporal_proximity": _proximity(delta),
            "same_incident_window": data.get("same_incident_window"),
            "temporal_order": data.get("temporal_order", "before"),
            "relationship_type": data.get("relationship_type", data.get("relationship")),
            "candidate_predecessor": source, "candidate_successor": target,
        })
    return features


def extract_dependency_features(graph: nx.DiGraph) -> dict[str, dict[str, Any]]:
    """For consumer->provider edges, providers are dependencies; reverse edges are dependents."""
    _require_directed(graph, "dependency graph")
    features = {}
    for service in graph.nodes:
        providers = list(graph.successors(service))
        dependents = list(graph.predecessors(service))
        features[service] = {
            "upstream_count": graph.in_degree(service),
            "downstream_count": graph.out_degree(service),
            "provider_count": len(providers), "dependent_count": len(dependents),
            "providers": providers, "dependents": dependents,
            "dependency_direction": "consumer_to_provider",
            "downstream_service_count": len(dependents),
            "upstream_service_count": len(providers),
            "affected_service_count": len(nx.descendants(graph.reverse(copy=False), service)),
        }
    return features


def extract_propagation_features(propagation_paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
    features = []
    for path in propagation_paths:
        delta = _validated_delta(path.get("time_delta_seconds"))
        features.append({
            "source_event": path.get("source_event"), "target_event": path.get("target_event"),
            "source_service": path["source_service"], "target_service": path["target_service"],
            "propagation_delay_seconds": delta,
            "temporal_proximity": _proximity(delta),
            "hop_count": path.get("hop_count", 0),
            "dependency_distance": path.get("dependency_distance", path.get("hop_count", 0)),
            "dependency_direction": path.get("dependency_direction", "dependency_to_dependent"),
            "dependency_path": path.get("dependency_path", []),
            "same_incident_window": path.get("same_incident_window"),
            "graph_source": path.get("graph_source", "temporal_graph+configured_dependency_graph"),
            "dependency_provenance": path.get("dependency_provenance", []),
        })
    return features
