import networkx as nx
from src.graphs.features import (
    extract_dependency_features,
    extract_propagation_features,
    extract_temporal_features,
)
def test_temporal_features_calculate_proximity():
    graph = nx.DiGraph()
    graph.add_edge(
        "E0",
        "E1",
        time_delta_seconds=4.0,
    )
    features = extract_temporal_features(graph)
    assert len(features) == 1
    assert features[0]["time_delta_seconds"] == 4.0
    assert features[0]["temporal_proximity"] == 0.2
def test_dependency_features_calculate_service_degree():
    graph = nx.DiGraph()
    graph.add_edge("api", "payment")
    graph.add_edge("payment", "database")
    features = extract_dependency_features(graph)
    assert features["api"]["downstream_count"] == 1
    assert features["api"]["upstream_count"] == 0
    assert features["payment"]["downstream_count"] == 1
    assert features["payment"]["upstream_count"] == 1
    assert features["database"]["downstream_count"] == 0
    assert features["database"]["upstream_count"] == 1
def test_propagation_features_are_extracted():
    paths = [
        {
            "source_service": "database",
            "target_service": "payment",
            "time_delta_seconds": 3.0,
            "hop_count": 1,
        }
    ]
    features = extract_propagation_features(paths)
    assert len(features) == 1
    assert features[0]["source_service"] == "database"
    assert features[0]["target_service"] == "payment"
    assert features[0]["propagation_delay_seconds"] == 3.0
    assert features[0]["hop_count"] == 1



def test_temporal_features_reject_invalid_and_unrepresentably_large_deltas():
    import pytest
    for delta in (-1, float("nan"), float("inf"), True, "2", 10**10000):
        graph = nx.DiGraph()
        graph.add_edge("a", "b", time_delta_seconds=delta)
        with pytest.raises(ValueError, match="time_delta_seconds"):
            extract_temporal_features(graph)


def test_temporal_features_require_directed_graph():
    import pytest
    graph = nx.Graph()
    graph.add_edge("a", "b", time_delta_seconds=1)
    with pytest.raises(ValueError, match="directed"):
        extract_temporal_features(graph)


def test_dependency_features_require_directed_graph():
    import pytest
    graph = nx.Graph()
    graph.add_edge("api", "database")
    with pytest.raises(ValueError, match="directed"):
        extract_dependency_features(graph)


def test_propagation_features_reject_invalid_delta_and_large_integer():
    import pytest
    for delta in (-1, float("nan"), float("inf"), True, 10**10000):
        with pytest.raises(ValueError, match="time_delta_seconds"):
            extract_propagation_features([{
                "source_service": "database",
                "target_service": "payment",
                "time_delta_seconds": delta,
                "hop_count": 1,
            }])
