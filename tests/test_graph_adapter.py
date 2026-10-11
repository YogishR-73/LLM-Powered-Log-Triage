from __future__ import annotations

import networkx as nx
import pytest
from pydantic import ValidationError

from src.evidence import EvidenceType, dependency_links_from_graphs, temporal_links_from_graph


def annotation(source, target, candidate, *, polarity="supporting", score=0.9, **extra):
    return {
        "source_event_id": source,
        "target_event_id": target,
        "candidate_event_id": candidate,
        "polarity": polarity,
        "score": score,
        **extra,
    }


def test_temporal_adapter_preserves_direction_and_graph_metadata():
    graph = nx.DiGraph()
    graph.add_edge("early", "late", relationship="temporal_precedence", time_delta_seconds=2.5)
    result = temporal_links_from_graph(graph, [annotation("early", "late", "late")])
    assert len(result) == 1
    link = result[0]
    assert link.source_event_id == "early"
    assert link.target_event_id == "late"
    assert link.candidate_event_id == "late"
    assert link.evidence_type == EvidenceType.TEMPORAL
    assert link.relation == "temporal_precedence"
    assert link.metadata["time_delta_seconds"] == 2.5


def test_temporal_adapter_does_not_infer_polarity_and_requires_annotation():
    graph = nx.DiGraph()
    graph.add_edge("early", "late", relationship="temporal_precedence")
    assert temporal_links_from_graph(graph, []) == []
    positive = temporal_links_from_graph(graph, [annotation("early", "late", "late")])[0]
    negative = temporal_links_from_graph(
        graph, [annotation("early", "late", "late", polarity="contradicting", score=0.4)]
    )[0]
    assert positive.polarity == "supporting"
    assert negative.polarity == "contradicting"


def test_temporal_adapter_rejects_nonexistent_or_reversed_edge():
    graph = nx.DiGraph()
    graph.add_edge("early", "late", relationship="temporal_precedence")
    with pytest.raises(ValueError, match="does not exist"):
        temporal_links_from_graph(graph, [annotation("late", "early", "late")])


def test_temporal_adapter_rejects_unknown_annotation_fields():
    graph = nx.DiGraph()
    graph.add_edge("a", "b")
    with pytest.raises(ValueError, match="Unknown evidence annotation"):
        temporal_links_from_graph(graph, [annotation("a", "b", "b", polariy="supporting")])


def test_temporal_adapter_validates_candidate_endpoint_and_score():
    graph = nx.DiGraph()
    graph.add_edge("a", "b")
    with pytest.raises(ValidationError):
        temporal_links_from_graph(graph, [annotation("a", "b", "elsewhere")])
    with pytest.raises(ValidationError):
        temporal_links_from_graph(graph, [annotation("a", "b", "b", score=float("nan"))])


def test_dependency_adapter_preserves_consumer_to_provider_direction():
    events = nx.DiGraph()
    events.add_node("checkout-event", service="checkout")
    events.add_node("db-event", service="database")
    dependencies = nx.DiGraph()
    dependencies.add_edge("checkout", "database", relationship="service_dependency")

    # Supply event IDs in reverse order; adapter normalizes output to the service-edge direction.
    link = dependency_links_from_graphs(
        events, dependencies,
        [annotation("db-event", "checkout-event", "checkout-event")],
    )[0]
    assert link.source_event_id == "checkout-event"
    assert link.target_event_id == "db-event"
    assert link.candidate_event_id == "checkout-event"
    assert link.evidence_type == EvidenceType.DEPENDENCY
    assert link.metadata["source_service"] == "checkout"
    assert link.metadata["dependency_service"] == "database"


def test_dependency_adapter_rejects_unrelated_services():
    events = nx.DiGraph()
    events.add_node("a-event", service="api")
    events.add_node("b-event", service="cache")
    dependencies = nx.DiGraph()
    with pytest.raises(ValueError, match="No service dependency"):
        dependency_links_from_graphs(
            events, dependencies, [annotation("a-event", "b-event", "a-event")]
        )


def test_dependency_adapter_rejects_missing_service_attribute():
    events = nx.DiGraph()
    events.add_node("a-event")
    events.add_node("b-event", service="cache")
    dependencies = nx.DiGraph()
    with pytest.raises(ValueError, match="no usable service"):
        dependency_links_from_graphs(
            events, dependencies, [annotation("a-event", "b-event", "a-event")]
        )


def test_dependency_adapter_rejects_bidirectional_service_edges_as_ambiguous():
    events = nx.DiGraph()
    events.add_node("api-event", service="api")
    events.add_node("db-event", service="database")
    dependencies = nx.DiGraph()
    dependencies.add_edge("api", "database", relationship="service_dependency")
    dependencies.add_edge("database", "api", relationship="service_dependency")
    with pytest.raises(ValueError, match="Bidirectional service dependency"):
        dependency_links_from_graphs(
            events, dependencies, [annotation("api-event", "db-event", "api-event")]
        )


def test_adapter_rejects_non_object_metadata():
    temporal = nx.DiGraph()
    temporal.add_edge("a", "b", relationship="temporal_precedence")
    with pytest.raises(ValueError, match="metadata must be a JSON object"):
        temporal_links_from_graph(
            temporal,
            [annotation("a", "b", "b", metadata=["not", "an", "object"])],
        )


def test_dependency_adapter_rejects_same_service_event_pair():
    events = nx.DiGraph()
    events.add_node("e1", service="api")
    events.add_node("e2", service="api")
    dependencies = nx.DiGraph()
    dependencies.add_edge("api", "api", relationship="service_dependency")
    with pytest.raises(ValueError, match="requires distinct services"):
        dependency_links_from_graphs(
            events, dependencies, [annotation("e1", "e2", "e1")]
        )


def test_temporal_adapter_rejects_annotation_metadata_conflicting_with_graph():
    graph = nx.DiGraph()
    graph.add_edge("early", "late", relationship="temporal_precedence", time_delta_seconds=2.5)
    with pytest.raises(ValueError, match="conflicts with graph data"):
        temporal_links_from_graph(
            graph,
            [annotation("early", "late", "late", metadata={"time_delta_seconds": 99.0})],
        )


def test_adapter_rejects_non_mapping_annotation_cleanly():
    graph = nx.DiGraph()
    with pytest.raises(ValueError, match="must be a mapping/object"):
        temporal_links_from_graph(graph, [None])


def test_dependency_adapter_rejects_metadata_that_disagrees_with_dependency_graph():
    events = nx.DiGraph()
    events.add_node("checkout-event", service="checkout")
    events.add_node("db-event", service="database")
    dependencies = nx.DiGraph()
    dependencies.add_edge("checkout", "database", relationship="service_dependency")

    with pytest.raises(ValueError, match="source_service.*conflicts with graph data"):
        dependency_links_from_graphs(
            events,
            dependencies,
            [annotation(
                "checkout-event",
                "db-event",
                "db-event",
                metadata={"source_service": "payment"},
            )],
        )


def test_temporal_adapter_rejects_invalid_graph_time_deltas():
    for bad_delta in (-1.0, float("nan"), float("inf"), True, "1.0"):
        graph = nx.DiGraph()
        graph.add_edge("early", "late", time_delta_seconds=bad_delta)
        with pytest.raises(ValueError, match="time_delta_seconds must be a finite non-negative number"):
            temporal_links_from_graph(graph, [annotation("early", "late", "late")])

def test_temporal_adapter_rejects_invalid_annotated_time_delta():
    graph = nx.DiGraph()
    graph.add_edge("early", "late")
    with pytest.raises(ValueError, match="time_delta_seconds must be a finite non-negative number"):
        temporal_links_from_graph(
            graph,
            [annotation("early", "late", "late", metadata={"time_delta_seconds": -0.1})],
        )


def test_temporal_adapter_rejects_undirected_graph():
    graph = nx.Graph()
    graph.add_edge("early", "late", time_delta_seconds=1.0)

    with pytest.raises(ValueError, match="temporal_graph must be a directed graph"):
        temporal_links_from_graph(graph, [annotation("early", "late", "late")])


def test_dependency_adapter_rejects_undirected_event_graph():
    events = nx.Graph()
    events.add_node("checkout-event", service="checkout")
    events.add_node("db-event", service="database")
    dependencies = nx.DiGraph()
    dependencies.add_edge("checkout", "database")

    with pytest.raises(ValueError, match="temporal_graph must be a directed graph"):
        dependency_links_from_graphs(
            events, dependencies, [annotation("checkout-event", "db-event", "db-event")]
        )


def test_dependency_adapter_rejects_undirected_service_graph():
    events = nx.DiGraph()
    events.add_node("checkout-event", service="checkout")
    events.add_node("db-event", service="database")
    dependencies = nx.Graph()
    dependencies.add_edge("checkout", "database")

    with pytest.raises(ValueError, match="dependency_graph must be a directed graph"):
        dependency_links_from_graphs(
            events, dependencies, [annotation("checkout-event", "db-event", "db-event")]
        )


def test_temporal_adapter_rejects_integer_time_delta_too_large_for_float():
    graph = nx.DiGraph()
    graph.add_edge("early", "late", time_delta_seconds=10**1000)

    with pytest.raises(
        ValueError,
        match="time_delta_seconds must be a finite non-negative number",
    ):
        temporal_links_from_graph(graph, [annotation("early", "late", "late")])
