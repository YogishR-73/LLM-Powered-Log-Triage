from datetime import datetime
from src.graphs.temporal_graph import TemporalEventGraph
def test_temporal_graph_orders_events_by_timestamp():
    events = [
        {
            "timestamp": datetime(2026, 1, 1, 10, 0, 5),
            "level": "ERROR",
            "service": "payment",
            "message": "Payment failed",
        },
        {
            "timestamp": datetime(2026, 1, 1, 10, 0, 1),
            "level": "ERROR",
            "service": "database",
            "message": "Database timeout",
        },
    ]
    temporal_graph = TemporalEventGraph()
    graph = temporal_graph.build(events)
    assert set(graph.nodes) == {"E0", "E1"}
    edge = next(iter(graph.edges(data=True)))
    assert graph.nodes[edge[0]]["timestamp"] < graph.nodes[edge[1]]["timestamp"]
def test_temporal_graph_calculates_time_delta():
    events = [
        {
            "timestamp": datetime(2026, 1, 1, 10, 0, 0),
            "level": "ERROR",
            "service": "database",
            "message": "Connection timeout",
        },
        {
            "timestamp": datetime(2026, 1, 1, 10, 0, 5),
            "level": "ERROR",
            "service": "payment",
            "message": "Payment failed",
        },
    ]
    temporal_graph = TemporalEventGraph()
    graph = temporal_graph.build(events)
    assert graph["E0"]["E1"]["time_delta_seconds"] == 5.0
    assert graph["E0"]["E1"]["relationship"] == "temporal_precedence"
    assert graph["E0"]["E1"]["candidate_relationship"] is True
def test_temporal_graph_stores_event_metadata():
    events = [
        {
            "timestamp": datetime(2026, 1, 1, 10, 0, 0),
            "level": "ERROR",
            "service": "database",
            "message": "Connection timeout",
        }
    ]
    temporal_graph = TemporalEventGraph()
    graph = temporal_graph.build(events)
    assert graph.nodes["E0"]["service"] == "database"
    assert graph.nodes["E0"]["level"] == "ERROR"
    assert graph.nodes["E0"]["message"] == "Connection timeout"
def test_empty_events_return_empty_graph():
    temporal_graph = TemporalEventGraph()
    graph = temporal_graph.build([])
    assert len(graph.nodes) == 0
    assert len(graph.edges) == 0


def test_temporal_graph_max_gap_prevents_bridging_separate_windows():
    events = [
        {"event_id": "E0", "timestamp": datetime(2026, 1, 1, 10, 0, 0), "service": "api"},
        {"event_id": "E1", "timestamp": datetime(2026, 1, 1, 10, 0, 1), "service": "db"},
        {"event_id": "E2", "timestamp": datetime(2026, 1, 1, 10, 10, 0), "service": "payment"},
    ]
    graph = TemporalEventGraph(max_gap_seconds=5).build(events)
    assert graph.has_edge("E0", "E1")
    assert not graph.has_edge("E1", "E2")


def test_temporal_graph_rejects_duplicate_ids():
    events = [
        {"event_id": "E0", "timestamp": datetime(2026, 1, 1, 10, 0, 0)},
        {"event_id": "E0", "timestamp": datetime(2026, 1, 1, 10, 0, 1)},
    ]
    import pytest
    with pytest.raises(ValueError, match="duplicate event_id"):
        TemporalEventGraph().build(events)



def test_timestamp_iso_is_parsed_and_default_gap_is_sixty_seconds():
    from datetime import timezone
    events = [
        {"event_id": "earlier", "timestamp_iso": "2026-01-01T10:00:00+00:00", "service": "api"},
        {"event_id": "later", "timestamp_iso": "2026-01-01T10:00:30Z", "service": "db"},
        {"event_id": "too_late", "timestamp_iso": "2026-01-01T10:02:00+00:00", "service": "worker"},
    ]
    graph = TemporalEventGraph().build(events)
    assert graph.has_edge("earlier", "later")
    assert not graph.has_edge("later", "too_late")
    assert graph.nodes["earlier"]["timestamp"].tzinfo == timezone.utc


def test_explicit_none_disables_gap_limit_for_one_build():
    events = [
        {"event_id": "a", "timestamp_iso": "2026-01-01T00:00:00+00:00"},
        {"event_id": "b", "timestamp_iso": "2026-01-02T00:00:00+00:00"},
    ]
    assert not TemporalEventGraph().build(events).has_edge("a", "b")
    assert TemporalEventGraph().build(events, max_gap_seconds=None).has_edge("a", "b")


def test_invalid_timestamp_iso_is_rejected():
    import pytest
    with pytest.raises(ValueError, match="invalid timestamp"):
        TemporalEventGraph().build([{"event_id": "bad", "timestamp_iso": "not-a-timestamp"}])


def test_fallback_id_does_not_collide_with_explicit_id():
    events = [
        {"timestamp": datetime(2026, 1, 1, 10, 0, 0)},
        {"event_id": "E0", "timestamp": datetime(2026, 1, 1, 10, 0, 1)},
    ]
    graph = TemporalEventGraph().build(events)
    assert set(graph.nodes) == {"E0_generated", "E0"}
    assert graph.has_edge("E0_generated", "E0")


def test_conflicting_contexts_do_not_create_temporal_edge():
    events = [
        {"event_id": "a", "timestamp": datetime(2026, 1, 1, 10, 0, 0), "trace_id": "trace-a"},
        {"event_id": "b", "timestamp": datetime(2026, 1, 1, 10, 0, 1), "trace_id": "trace-b"},
    ]
    assert not TemporalEventGraph().build(events).has_edge("a", "b")


def test_invalid_gap_configuration_is_rejected():
    import pytest
    for value in (-1, float("nan"), float("inf"), True, 10**10000):
        with pytest.raises(ValueError):
            TemporalEventGraph(max_gap_seconds=value)



def test_timestamp_iso_requires_timezone_offset():
    import pytest
    with pytest.raises(ValueError, match="timestamp_iso must include a UTC offset"):
        TemporalEventGraph().build([
            {"event_id": "naive-iso", "timestamp_iso": "2026-01-01T10:00:00"}
        ])
