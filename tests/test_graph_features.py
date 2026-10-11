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
