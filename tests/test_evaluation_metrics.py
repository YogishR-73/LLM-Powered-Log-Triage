from __future__ import annotations

import math

import pytest

from evaluation.metrics import (
    clustering_quality,
    event_reference_integrity,
    evidence_package_integrity,
    latency_summary_ms,
    package_validity_summary,
    ranked_root_cause_metrics,
)
from src.evidence import EvidenceBuilder, EvidenceLink, EventStore, EvidenceType


def test_clustering_quality_perfect_partition() -> None:
    result = clustering_quality(
        ["A", "A", "B", "B"],
        ["cluster-1", "cluster-1", "cluster-2", "cluster-2"],
    )
    assert result["n_events"] == 4
    assert result["n_labels"] == 2
    assert result["n_clusters"] == 2
    assert result["adjusted_rand_index"] == pytest.approx(1.0)
    assert result["normalized_mutual_info"] == pytest.approx(1.0)
    assert result["purity"] == pytest.approx(1.0)


def test_clustering_quality_empty_is_explicitly_unavailable() -> None:
    result = clustering_quality([], [])
    assert result["n_events"] == 0
    assert result["adjusted_rand_index"] is None


def test_clustering_quality_rejects_mismatched_or_blank_labels() -> None:
    with pytest.raises(ValueError, match="equal length"):
        clustering_quality(["A"], ["c1", "c2"])
    with pytest.raises(ValueError, match="non-blank"):
        clustering_quality([""], ["c1"])


def test_noise_coverage_is_not_hidden_by_purity() -> None:
    result = clustering_quality(["A", "B", "B"], ["noise", "x", "x"])
    assert result["noise_coverage"] == pytest.approx(2 / 3)
    assert result["purity_excluding_noise"] == pytest.approx(1.0)


def test_event_reference_integrity_reports_unknown_ids_and_denominator() -> None:
    result = event_reference_integrity(["e1", "e2", "missing", ""], ["e1", "e2"])
    assert result["n_references"] == 4
    assert result["n_valid_references"] == 2
    assert result["n_invalid_references"] == 2
    assert result["valid_event_reference_rate"] == pytest.approx(0.5)
    assert "missing" in result["unknown_or_invalid_event_ids"]


def test_package_validity_summary() -> None:
    assert package_validity_summary([True, False, True]) == {
        "n_packages_evaluated": 3,
        "n_valid_packages": 2,
        "n_invalid_packages": 1,
        "valid_package_rate": pytest.approx(2 / 3),
    }
    with pytest.raises(TypeError, match="must be bool"):
        package_validity_summary([1])  # type: ignore[list-item]


def test_evidence_package_integrity_checks_existing_event_ids() -> None:
    events = [
        {"event_id": "evt_0000000000000001", "timestamp_iso": "2026-10-11T10:00:00+00:00", "severity": "ERROR", "service": "db", "message": "pool exhausted"},
        {"event_id": "evt_0000000000000002", "timestamp_iso": "2026-10-11T10:00:01+00:00", "severity": "ERROR", "service": "api", "message": "request timeout"},
    ]
    store = EventStore(events)
    builder = EvidenceBuilder(store)
    link = EvidenceLink(
        source_event_id="evt_0000000000000001",
        target_event_id="evt_0000000000000002",
        candidate_event_id="evt_0000000000000002",
        evidence_type=EvidenceType.DEPENDENCY,
        polarity="supporting",
        score=0.8,
        relation="database_precedes_api_symptom",
    )
    package = builder.build_package("incident-1", ["evt_0000000000000002"], [link])
    result = evidence_package_integrity([package], {event["event_id"] for event in events})
    assert result["n_schema_valid_packages"] == 1
    assert result["schema_valid_package_rate"] == 1.0
    assert result["package_store_reference_rate"] == 1.0
    assert result["event_references"]["valid_event_reference_rate"] == 1.0
    assert result["n_relationship_records"] == 1


def test_evidence_package_integrity_rejects_schema_invalid_package_and_unknown_ids() -> None:
    bad = {"incident_id": "incident-1", "candidates": [{"candidate_event_id": "unknown"}]}
    result = evidence_package_integrity([bad], {"known"})
    assert result["n_schema_invalid_packages"] == 1
    assert result["schema_valid_package_rate"] == 0.0


def test_ranked_root_cause_metrics_calculation() -> None:
    result = ranked_root_cause_metrics(
        [["db", "api"], ["payment", "db"], []],
        ["db", "db", "api"],
        ks=(1, 3),
    )
    assert result["n_incidents"] == 3
    assert result["top_1_accuracy"] == pytest.approx(1 / 3)
    assert result["top_k_accuracy"]["3"] == pytest.approx(2 / 3)
    assert result["mean_reciprocal_rank"] == pytest.approx(0.5)
    assert result["recall_at_k"]["3"] == pytest.approx(2 / 3)


def test_ranked_root_cause_supports_multiple_valid_root_causes() -> None:
    result = ranked_root_cause_metrics([["api", "db", "queue"]], [["api", "queue"]], ks=(1, 3))
    assert result["top_k_accuracy"]["1"] == 1.0
    assert result["recall_at_k"]["1"] == 0.5
    assert result["recall_at_k"]["3"] == 1.0


@pytest.mark.parametrize(
    "predictions,truth,match",
    [
        ([["api"]], [], "equal length"),
        ([["api", "api"]], ["api"], "duplicate"),
        ([[]], [""], "non-blank"),
        ([["api"]], ["api"], "positive integer"),
    ],
)
def test_ranked_root_cause_rejects_bad_inputs(predictions, truth, match) -> None:
    kwargs = {"ks": (0,)} if match == "positive integer" else {"ks": (1,)}
    with pytest.raises((ValueError, TypeError), match=match):
        ranked_root_cause_metrics(predictions, truth, **kwargs)


def test_empty_ranking_counts_as_miss_not_dropped() -> None:
    result = ranked_root_cause_metrics([[]], ["db"], ks=(1,))
    assert result["n_incidents"] == 1
    assert result["top_1_accuracy"] == 0.0
    assert result["mean_reciprocal_rank"] == 0.0


def test_latency_summary_uses_nearest_rank_p95_and_rejects_nan() -> None:
    result = latency_summary_ms([1, 2, 3, 4, 5])
    assert result["n_samples"] == 5
    assert result["mean_ms"] == pytest.approx(3.0)
    assert result["median_ms"] == pytest.approx(3.0)
    assert result["p95_ms"] == pytest.approx(5.0)
    assert latency_summary_ms([])["p95_ms"] is None
    with pytest.raises(ValueError, match="finite"):
        latency_summary_ms([math.nan])


def test_event_reference_integrity_rejects_single_string_arguments() -> None:
    with pytest.raises(TypeError, match="not a single string"):
        event_reference_integrity("evt_1", ["evt_1"])
    with pytest.raises(TypeError, match="not a single string"):
        event_reference_integrity(["evt_1"], "evt_1")


def test_ranked_root_cause_rejects_ground_truth_string_instead_of_per_incident_sequence() -> None:
    with pytest.raises(TypeError, match="one entry per incident"):
        ranked_root_cause_metrics([["db"]], "db")  # type: ignore[arg-type]


def test_evidence_package_integrity_counts_duplicate_and_unknown_event_refs() -> None:
    # A schema-valid package can still contain event IDs not present in the store;
    # the event-store check is intentionally separate from Pydantic schema validation.
    from src.evidence import CandidateEvidence, EventSnapshot, EvidenceItem, EvidencePackage

    candidate_id = "evt_0000000000000001"
    missing_id = "evt_0000000000000099"
    candidate = EventSnapshot(
        event_id=candidate_id,
        timestamp_iso="2026-10-11T10:00:00+00:00",
        severity="ERROR",
        service="api",
        message="request failed",
    )
    evidence = EvidenceItem(
        candidate_event_id=candidate_id,
        event_id=missing_id,
        source_event_id=candidate_id,
        target_event_id=missing_id,
        evidence_type=EvidenceType.TEMPORAL,
        polarity="supporting",
        score=0.7,
        relation="precedes",
    )
    candidate_evidence = CandidateEvidence(
        candidate_event_id=candidate_id,
        candidate=candidate,
        supporting_events=(missing_id,),
        evidence_items=(evidence,),
        temporal_score=0.7,
    )
    package = EvidencePackage(incident_id="i-1", candidates=(candidate_evidence,))
    result = evidence_package_integrity([package], {candidate_id})
    assert result["schema_valid_package_rate"] == 1.0
    assert result["package_store_reference_rate"] == 0.0
    assert result["event_references"]["valid_event_reference_rate"] < 1.0
    assert missing_id in result["unknown_event_ids"]
