"""Directed service dependency graph with explicit provenance metadata."""
from __future__ import annotations
from typing import Any, Iterable, Mapping
import networkx as nx


class ServiceDependencyGraph:
    """Build a service graph with edges ``consumer -> provider``.

    Dependency tuples are configured assumptions unless callers explicitly supply
    provenance. They are not automatically discovered from log adjacency.
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
                extra = {k: v for k, v in item.items() if k not in {
                    "consumer", "service", "source_service", "provider", "dependency",
                    "target_service", "source", "confidence", "observation_count"}}
            else:
                try:
                    consumer, provider = item
                except (TypeError, ValueError) as exc:
                    raise ValueError("dependencies must be (consumer, provider) pairs or mappings") from exc
                source, confidence, observations, extra = "configured_dependency_map", 1.0, 0, {}
            if not isinstance(consumer, str) or not consumer.strip() or not isinstance(provider, str) or not provider.strip():
                raise ValueError("consumer and provider must be non-blank service names")
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
                raise ValueError("confidence must be between 0 and 1")
            if isinstance(observations, bool) or not isinstance(observations, int) or observations < 0:
                raise ValueError("observation_count must be a non-negative integer")
            self.graph.add_edge(
                consumer, provider, relationship="service_dependency",
                relationship_type="service_dependency", source=str(source),
                confidence=float(confidence), observation_count=observations,
                dependency_direction="consumer_to_provider", **extra,
            )
        return self.graph

    def get_graph(self) -> nx.DiGraph:
        return self.graph
