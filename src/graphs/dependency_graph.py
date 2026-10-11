"""Directed service dependency graph with explicit provenance metadata."""
from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

import networkx as nx


_RESERVED_EDGE_KEYS = {
    "relationship", "relationship_type", "source", "confidence",
    "observation_count", "dependency_direction", "consumer", "provider",
}


class ServiceDependencyGraph:
    """Build a service graph with edges ``consumer -> provider``.

    Dependency tuples are configured assumptions unless callers explicitly supply
    provenance. Extra mapping fields are kept under ``metadata`` so they cannot
    overwrite authoritative edge fields.
    """
    def __init__(self) -> None:
        self.graph = nx.DiGraph()

    def build(self, dependencies: Iterable[Any]) -> nx.DiGraph:
        self.graph.clear()
        for item in dependencies:
            if isinstance(item, Mapping):
                consumer = item.get("consumer", item.get("service", item.get("source_service")))
                provider = item.get("provider", item.get("dependency", item.get("target_service")))
                source = item.get("source", "configured_dependency_map")
                confidence = item.get("confidence", 1.0)
                observations = item.get("observation_count", 0)
                extra = {
                    k: v for k, v in item.items()
                    if k not in {
                        "consumer", "service", "source_service", "provider", "dependency",
                        "target_service", "source", "confidence", "observation_count",
                    }
                }
            else:
                try:
                    consumer, provider = item
                except (TypeError, ValueError) as exc:
                    raise ValueError("dependencies must be (consumer, provider) pairs or mappings") from exc
                source, confidence, observations, extra = "configured_dependency_map", 1.0, 0, {}

            if not isinstance(consumer, str) or not consumer.strip() or not isinstance(provider, str) or not provider.strip():
                raise ValueError("consumer and provider must be non-blank service names")
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
                raise ValueError("confidence must be a finite number between 0 and 1")
            try:
                confidence_value = float(confidence)
            except (OverflowError, TypeError, ValueError) as exc:
                raise ValueError("confidence must be a finite number between 0 and 1") from exc
            if not math.isfinite(confidence_value) or not 0 <= confidence_value <= 1:
                raise ValueError("confidence must be a finite number between 0 and 1")
            if isinstance(observations, bool) or not isinstance(observations, int) or observations < 0:
                raise ValueError("observation_count must be a non-negative integer")

            # Metadata is namespaced instead of being expanded into the edge kwargs.
            # This avoids TypeError collisions and prevents user data from overriding
            # the graph's canonical relationship/direction/provenance fields.
            metadata = dict(extra)
            for reserved in _RESERVED_EDGE_KEYS & metadata.keys():
                metadata[f"user_{reserved}"] = metadata.pop(reserved)
            edge = {
                "relationship": "service_dependency",
                "relationship_type": "service_dependency",
                "source": str(source),
                "confidence": confidence_value,
                "observation_count": observations,
                "dependency_direction": "consumer_to_provider",
                "consumer": consumer.strip(),
                "provider": provider.strip(),
                "metadata": metadata,
            }
            # Repeated dependency declarations combine metadata without allowing a
            # later record to silently replace direction or provenance fields.
            if self.graph.has_edge(consumer.strip(), provider.strip()):
                existing = self.graph[consumer.strip()][provider.strip()]
                merged = dict(existing.get("metadata", {}))
                merged.update(metadata)
                existing["metadata"] = merged
                existing["confidence"] = max(existing["confidence"], confidence_value)
                existing["observation_count"] += observations
                if source != existing["source"]:
                    sources = set(existing["metadata"].get("additional_sources", []))
                    sources.update([existing["source"], str(source)])
                    existing["metadata"]["additional_sources"] = sorted(sources)
            else:
                self.graph.add_edge(consumer.strip(), provider.strip(), **edge)
        return self.graph

    def get_graph(self) -> nx.DiGraph:
        return self.graph
