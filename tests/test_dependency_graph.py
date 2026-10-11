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
