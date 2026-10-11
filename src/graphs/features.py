"""Extract temporal, dependency-structure, and propagation features for RCA."""
from __future__ import annotations
from typing import Any
import networkx as nx


def extract_temporal_features(graph: nx.DiGraph) -> list[dict[str, Any]]:
    features = []
    for source, target, data in graph.edges(data=True):
        delta = data.get("time_delta_seconds")
        proximity = 1.0 / (1.0 + delta) if isinstance(delta, (int, float)) and not isinstance(delta, bool) and delta >= 0 else 0.0
        features.append({
            "source_event": source, "target_event": target,
            "time_delta_seconds": delta, "temporal_proximity": proximity,
            "same_incident_window": data.get("same_incident_window"),
            "temporal_order": data.get("temporal_order", "before"),
            "relationship_type": data.get("relationship_type", data.get("relationship")),
            "candidate_predecessor": source, "candidate_successor": target,
        })
    return features


def extract_dependency_features(graph: nx.DiGraph) -> dict[str, dict[str, Any]]:
    """For consumer->provider edges, providers are dependencies; reverse edges are dependents."""
    features = {}
    for service in graph.nodes:
        providers = list(graph.successors(service))
        dependents = list(graph.predecessors(service))
        features[service] = {
            # Preserve legacy degree names (in/out degree) while adding explicit
            # semantic names to remove ambiguity under consumer->provider edges.
            "upstream_count": graph.in_degree(service), "downstream_count": graph.out_degree(service),
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
        delta = path.get("time_delta_seconds")
        features.append({
            "source_event": path.get("source_event"), "target_event": path.get("target_event"),
            "source_service": path["source_service"], "target_service": path["target_service"],
            "propagation_delay_seconds": delta,
            "temporal_proximity": 1.0 / (1.0 + delta) if isinstance(delta, (int, float)) and delta >= 0 else 0.0,
            "hop_count": path.get("hop_count", 0),
            "dependency_distance": path.get("dependency_distance", path.get("hop_count", 0)),
            "dependency_direction": path.get("dependency_direction", "dependency_to_dependent"),
            "dependency_path": path.get("dependency_path", []),
            "same_incident_window": path.get("same_incident_window"),
            "graph_source": path.get("graph_source", "temporal_graph+configured_dependency_graph"),
            "dependency_provenance": path.get("dependency_provenance", []),
        })
    return features
