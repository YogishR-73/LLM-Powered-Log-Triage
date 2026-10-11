from src.graphs.dependency_graph import ServiceDependencyGraph
def test_dependency_graph_creates_service_dependencies():
    dependencies = [
        ("api", "payment"),
        ("payment", "database"),
    ]
    dependency_graph = ServiceDependencyGraph()
    graph = dependency_graph.build(dependencies)
    assert graph.has_edge("api", "payment")
    assert graph.has_edge("payment", "database")
def test_dependency_graph_stores_relationship():
    dependencies = [
        ("payment", "database"),
    ]
    dependency_graph = ServiceDependencyGraph()
    graph = dependency_graph.build(dependencies)
    assert (
        graph["payment"]["database"]["relationship"]
        == "service_dependency"
    )
def test_dependency_graph_handles_empty_dependencies():
    dependency_graph = ServiceDependencyGraph()
    graph = dependency_graph.build([])
    assert len(graph.nodes) == 0
    assert len(graph.edges) == 0
def test_dependency_graph_handles_multiple_dependencies():
    dependencies = [
        ("api", "database"),
        ("api", "redis"),
        ("payment", "database"),
    ]
    dependency_graph = ServiceDependencyGraph()
    graph = dependency_graph.build(dependencies)
    assert graph.out_degree("api") == 2
    assert graph.has_edge("api", "database")
    assert graph.has_edge("api", "redis")
    assert graph.has_edge("payment", "database")



def test_reserved_metadata_keys_cannot_override_dependency_direction():
    graph = ServiceDependencyGraph().build([{
        "consumer": "checkout",
        "provider": "database",
        "relationship": "malicious_override",
        "relationship_type": "other",
        "dependency_direction": "provider_to_consumer",
        "source": "architecture_config",
        "confidence": 0.8,
        "observation_count": 2,
        "custom_tag": "reviewed",
    }])
    edge = graph["checkout"]["database"]
    assert edge["relationship"] == "service_dependency"
    assert edge["relationship_type"] == "service_dependency"
    assert edge["dependency_direction"] == "consumer_to_provider"
    assert edge["consumer"] == "checkout"
    assert edge["provider"] == "database"
    assert edge["source"] == "architecture_config"
    assert edge["metadata"]["user_relationship"] == "malicious_override"
    assert edge["metadata"]["user_dependency_direction"] == "provider_to_consumer"
    assert edge["metadata"]["custom_tag"] == "reviewed"


def test_dependency_mapping_direction_fields_are_explicit():
    graph = ServiceDependencyGraph().build([{"consumer": "api", "provider": "cache"}])
    edge = graph["api"]["cache"]
    assert edge["consumer"] == "api"
    assert edge["provider"] == "cache"
    assert edge["dependency_direction"] == "consumer_to_provider"
