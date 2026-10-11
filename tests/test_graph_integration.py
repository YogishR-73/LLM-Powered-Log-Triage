"""Integration contract tests for Member 2 graph modules and Member 1 LogEvent.

The plain-record test always runs when the graph modules are present. The actual
LogEvent test runs in the integrated team repository and skips in Member 2's
isolated branch until Member 1's src.log_intelligence module is available.
"""
from __future__ import annotations

import importlib.util
from datetime import datetime, timezone

import pytest

from src.graphs.dependency_graph import ServiceDependencyGraph
from src.graphs.temporal_graph import TemporalEventGraph
from src.graphs.propagation import PropagationAnalyzer


def _records():
    return [
        {
            "event_id": "E01",
            "timestamp_iso": "2026-10-08T10:00:00+00:00",
            "severity": "ERROR",
            "service": "database",
            "message": "connection pool exhausted",
            "attributes": {"trace_id": "trace-1"},
        },
        {
            "event_id": "E02",
            "timestamp_iso": "2026-10-08T10:00:02+00:00",
            "severity": "ERROR",
            "service": "checkout",
            "message": "checkout timed out",
            "attributes": {"trace_id": "trace-1"},
        },
    ]


def test_graph_modules_integrate_with_canonical_logevent_record_shape():
    records = _records()
    temporal = TemporalEventGraph().build(records)
    dependencies = ServiceDependencyGraph().build([("checkout", "database")])

    assert temporal.has_edge("E01", "E02")
    assert temporal.nodes["E01"]["severity"] == "ERROR"
    assert temporal.nodes["E01"]["timestamp_iso"] == records[0]["timestamp_iso"]
    assert temporal["E01"]["E02"]["same_incident_window"] is True
    assert dependencies.has_edge("checkout", "database")

    paths = PropagationAnalyzer(temporal, dependencies).find_propagation_paths()
    assert len(paths) == 1
    assert paths[0]["dependency_path"] == ["database", "checkout"]
    assert paths[0]["dependency_direction"] == "dependency_to_dependent"


def test_temporal_graph_accepts_actual_member1_logevent_records():
    if importlib.util.find_spec("src.log_intelligence") is None:
        pytest.skip("Member 1 src.log_intelligence is not present in this isolated checkout")

    from src.log_intelligence import LogEvent

    earlier = LogEvent(
        event_id="evt_0123456789abcdef",
        timestamp_iso="2026-10-08T10:00:00+00:00",
        severity="ERROR",
        service="database",
        message="connection pool exhausted",
        raw="2026-10-08T10:00:00Z ERROR database connection pool exhausted",
        parser="generic_iso",
        attributes={"trace_id": "trace-1"},
    )
    later = LogEvent(
        event_id="evt_fedcba9876543210",
        timestamp_iso="2026-10-08T10:00:02+00:00",
        severity="ERROR",
        service="checkout",
        message="checkout timed out",
        raw="2026-10-08T10:00:02Z ERROR checkout timed out",
        parser="generic_iso",
        attributes={"trace_id": "trace-1"},
    )

    temporal = TemporalEventGraph().build([earlier, later])
    dependencies = ServiceDependencyGraph().build([("checkout", "database")])
    assert temporal.has_edge(earlier.event_id, later.event_id)
    assert temporal.nodes[earlier.event_id]["severity"] == "ERROR"
    assert temporal.nodes[earlier.event_id]["timestamp_iso"] == earlier.timestamp_iso
    assert temporal[earlier.event_id][later.event_id]["same_incident_window"] is True
    paths = PropagationAnalyzer(temporal, dependencies).find_propagation_paths()
    assert len(paths) == 1
    assert paths[0]["dependency_path"] == ["database", "checkout"]
