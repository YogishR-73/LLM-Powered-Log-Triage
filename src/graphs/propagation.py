"""Dependency-directed candidate propagation reasoning."""
from __future__ import annotations

import math
from typing import Any

import networkx as nx


def _validated_delta(value: Any, source: Any, target: Any) -> float | None:
    if value is None:
        return None
    error = f"invalid time_delta_seconds on temporal edge {source!r} -> {target!r}"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(error)
    try:
        normalized = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(error) from exc
    if not math.isfinite(normalized) or normalized < 0:
        raise ValueError(error)
    return normalized


class PropagationAnalyzer:
    """Find temporal event edges consistent with service dependency paths.

    Dependency edges use consumer -> provider. A possible causal propagation path
    therefore travels provider -> consumer, opposite to dependency-edge direction.
    These are candidates, not definitive causal claims.
    """
    def __init__(self, temporal_graph: nx.DiGraph, dependency_graph: nx.DiGraph) -> None:
        self.temporal_graph = temporal_graph
        self.dependency_graph = dependency_graph

    def find_propagation_paths(self, max_hops: int = 5) -> list[dict[str, Any]]:
        if isinstance(max_hops, bool) or not isinstance(max_hops, int) or max_hops < 1:
            raise ValueError("max_hops must be a positive integer")
        if not self.temporal_graph.is_directed():
            raise ValueError("temporal_graph must be a directed graph")
        if not self.dependency_graph.is_directed():
            raise ValueError("dependency_graph must be a directed graph")

        # Validate every supplied delta up front, including edges that ultimately
        # do not qualify as propagation candidates.
        deltas = {
            (u, v): _validated_delta(data.get("time_delta_seconds"), u, v)
            for u, v, data in self.temporal_graph.edges(data=True)
        }

        paths: list[dict[str, Any]] = []
        for source_event, target_event, temporal_data in self.temporal_graph.edges(data=True):
            source_service = self.temporal_graph.nodes[source_event].get("service")
            target_service = self.temporal_graph.nodes[target_event].get("service")
            if not isinstance(source_service, str) or not source_service.strip():
                continue
            if not isinstance(target_service, str) or not target_service.strip() or source_service == target_service:
                continue
            if temporal_data.get("same_incident_window") is False:
                continue
            if source_service not in self.dependency_graph or target_service not in self.dependency_graph:
                continue
            try:
                consumer_to_provider = nx.shortest_path(
                    self.dependency_graph, source=target_service, target=source_service
                )
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue
            hop_count = len(consumer_to_provider) - 1
            if hop_count < 1 or hop_count > max_hops:
                continue
            dependency_path = list(reversed(consumer_to_provider))
            dependency_edges = [
                self.dependency_graph.get_edge_data(consumer, provider, default={}) or {}
                for consumer, provider in zip(consumer_to_provider, consumer_to_provider[1:])
            ]
            delta = deltas[(source_event, target_event)]
            paths.append({
                "source_event": source_event, "target_event": target_event,
                "source_service": source_service, "target_service": target_service,
                "time_delta_seconds": delta,
                "temporal_proximity": 1.0 / (1.0 + delta) if delta is not None else 0.0,
                "same_incident_window": temporal_data.get("same_incident_window"),
                "relationship_type": "candidate_dependency_propagation",
                "dependency_direction": "dependency_to_dependent",
                "hop_count": hop_count, "dependency_distance": hop_count,
                "dependency_path": dependency_path,
                "dependency_provenance": [
                    {"consumer": c, "provider": p, **data}
                    for (c, p), data in zip(
                        zip(consumer_to_provider, consumer_to_provider[1:]), dependency_edges
                    )
                ],
                "graph_source": "temporal_graph+configured_dependency_graph",
            })
        return paths
