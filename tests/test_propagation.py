from datetime import datetime
import networkx as nx
from src.graphs.propagation import PropagationAnalyzer
def test_propagation_is_detected_between_dependent_services():
    temporal_graph = nx.DiGraph()
    temporal_graph.add_node(
        "E0",
        timestamp=datetime(2026, 1, 1, 10, 0, 0),
        service="database",
        level="ERROR",
        message="Database timeout",
    )
    temporal_graph.add_node(
        "E1",
        timestamp=datetime(2026, 1, 1, 10, 0, 3),
        service="payment",
        level="ERROR",
        message="Payment failed",
    )
    temporal_graph.add_edge(
        "E0",
        "E1",
        time_delta_seconds=3.0,
        relationship="temporal_precedence",
    )
    dependency_graph = nx.DiGraph()
    dependency_graph.add_edge(
        "payment",
        "database",
        relationship="service_dependency",
    )
    analyzer = PropagationAnalyzer(
        temporal_graph,
        dependency_graph,
    )
    paths = analyzer.find_propagation_paths()
    assert len(paths) == 1
    assert paths[0]["source_event"] == "E0"
    assert paths[0]["target_event"] == "E1"
    assert paths[0]["source_service"] == "database"
    assert paths[0]["target_service"] == "payment"
    assert paths[0]["time_delta_seconds"] == 3.0
def test_propagation_is_not_detected_without_dependency():
    temporal_graph = nx.DiGraph()
    temporal_graph.add_node(
        "E0",
        service="database",
    )
    temporal_graph.add_node(
        "E1",
        service="payment",
    )
    temporal_graph.add_edge(
        "E0",
        "E1",
        time_delta_seconds=3.0,
    )
    dependency_graph = nx.DiGraph()
    analyzer = PropagationAnalyzer(
        temporal_graph,
        dependency_graph,
    )
    paths = analyzer.find_propagation_paths()
    assert paths == []
def test_same_service_events_are_not_propagation():
    temporal_graph = nx.DiGraph()
    temporal_graph.add_node(
        "E0",
        service="database",
    )
    temporal_graph.add_node(
        "E1",
        service="database",
    )
    temporal_graph.add_edge(
        "E0",
        "E1",
        time_delta_seconds=2.0,
    )
    dependency_graph = nx.DiGraph()
    dependency_graph.add_edge(
        "database",
        "database",
    )
    analyzer = PropagationAnalyzer(
        temporal_graph,
        dependency_graph,
    )
    paths = analyzer.find_propagation_paths()
    assert paths == []


def test_reverse_dependency_direction_is_not_treated_as_propagation():
    temporal = nx.DiGraph()
    temporal.add_node("E0", service="payment")
    temporal.add_node("E1", service="database")
    temporal.add_edge("E0", "E1", time_delta_seconds=1.0)
    dependencies = nx.DiGraph()
    dependencies.add_edge("payment", "database")
    assert PropagationAnalyzer(temporal, dependencies).find_propagation_paths() == []


def test_max_hops_limits_actual_dependency_path_length():
    temporal = nx.DiGraph()
    temporal.add_node("E0", service="database")
    temporal.add_node("E1", service="api")
    temporal.add_edge("E0", "E1", time_delta_seconds=2.0)
    dependencies = nx.DiGraph()
    dependencies.add_edges_from([
        ("api", "payment"),
        ("payment", "database"),
    ])
    analyzer = PropagationAnalyzer(temporal, dependencies)
    assert analyzer.find_propagation_paths(max_hops=1) == []
    paths = analyzer.find_propagation_paths(max_hops=2)
    assert len(paths) == 1
    assert paths[0]["hop_count"] == 2
    assert paths[0]["dependency_path"] == ["database", "payment", "api"]
