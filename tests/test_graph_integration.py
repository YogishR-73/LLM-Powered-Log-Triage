"""Contract test against Member 2's graph classes when they are in the checkout.

Skip only if the upstream modules are absent. Import errors from present modules
are not caught, so broken integration is visible to CI.
"""
from __future__ import annotations

import importlib.util
from datetime import datetime, timezone

import pytest

if (
    importlib.util.find_spec("src.graphs") is None
    or importlib.util.find_spec("src.graphs.temporal_graph") is None
    or importlib.util.find_spec("src.graphs.dependency_graph") is None
):
    pytest.skip("Member 2 graph modules are not present in this checkout", allow_module_level=True)

from src.graphs.dependency_graph import ServiceDependencyGraph
from src.graphs.temporal_graph import TemporalEventGraph
from src.evidence import dependency_links_from_graphs, temporal_links_from_graph


def test_evidence_adapters_accept_member2_graph_outputs():
    records = [
        {
            "event_id": "E01",
            "timestamp": datetime(2026, 10, 8, 10, 0, 0, tzinfo=timezone.utc),
            "service": "database",
            "level": "ERROR",
            "message": "connection pool exhausted",
        },
        {
            "event_id": "E02",
            "timestamp": datetime(2026, 10, 8, 10, 0, 1, tzinfo=timezone.utc),
            "service": "checkout",
            "level": "ERROR",
            "message": "checkout timed out",
        },
    ]
    temporal = TemporalEventGraph().build(records)
    dependencies = ServiceDependencyGraph().build([("checkout", "database")])

    temporal_links = temporal_links_from_graph(temporal, [{
        "source_event_id": "E01",
        "target_event_id": "E02",
        "candidate_event_id": "E02",
        "polarity": "supporting",
        "score": 0.9,
        "reason": "Explicit integration-test annotation",
    }])
    dependency_links = dependency_links_from_graphs(temporal, dependencies, [{
        "source_event_id": "E02",
        "target_event_id": "E01",
        "candidate_event_id": "E02",
        "polarity": "supporting",
        "score": 0.9,
        "reason": "Explicit integration-test annotation",
    }])

    assert temporal_links[0].source_event_id == "E01"
    assert temporal_links[0].target_event_id == "E02"
    assert dependency_links[0].source_event_id == "E02"
    assert dependency_links[0].target_event_id == "E01"
    assert dependency_links[0].metadata["source_service"] == "checkout"
    assert dependency_links[0].metadata["dependency_service"] == "database"
