from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.evidence import (
    CandidateEvidence,
    EvidenceBuilder,
    EvidenceLink,
    EvidencePackage,
    EvidenceType,
    EventStore,
)


def event(event_id, *, timestamp="2026-10-08T10:00:00+00:00", service="api", line=None):
    """Canonical LogEvent-shaped fixture without importing Member 1's module."""
    if line is None:
        try:
            line = int(event_id.removeprefix("E"))
        except (AttributeError, ValueError):
            line = 1
    return SimpleNamespace(
        event_id=event_id,
        timestamp_iso=timestamp,
        severity="ERROR",
        service=service,
        message=f"message for {event_id}",
        template=f"template-{event_id}",
        source_file="incident.log",
        line_number=line,
    )


def link(source, target, *, candidate, evidence_type=EvidenceType.TEMPORAL,
         polarity="supporting", score=0.9, relation="precedes", reason=None, metadata=None):
    values = {
        "source_event_id": source,
        "target_event_id": target,
        "evidence_type": evidence_type,
        "polarity": polarity,
        "score": score,
        "relation": relation,
        "reason": reason,
        "metadata": metadata or {},
    }
    values["candidate_event_id"] = candidate
    return EvidenceLink(**values)


def make_builder(*ids):
    return EvidenceBuilder(EventStore([event(event_id) for event_id in ids]))


def test_event_store_preserves_traceable_ids_and_safe_snapshot():
    store = EventStore([event("E01")])
    snapshot = store.require("E01")
    assert snapshot.event_id == "E01"
    assert snapshot.timestamp_iso == "2026-10-08T10:00:00+00:00"
    assert snapshot.service == "api"
    assert snapshot.message == "message for E01"
    assert not hasattr(snapshot, "raw_message")


def test_event_store_rejects_duplicate_ids():
    with pytest.raises(ValueError, match="Duplicate event_id: E01"):
        EventStore([event("E01"), event("E01")])


def test_event_store_rejects_unknown_event_id():
    store = EventStore([event("E01")])
    with pytest.raises(KeyError, match="Unknown event_id: E99"):
        store.require("E99")


def test_event_store_snapshot_is_immutable():
    snapshot = EventStore([event("E01")]).require("E01")
    with pytest.raises(ValidationError):
        snapshot.event_id = "E99"


def test_event_store_rejects_malformed_timestamp():
    with pytest.raises(ValidationError, match="ISO-8601"):
        EventStore([event("E01", timestamp="yesterday")])
    with pytest.raises(ValidationError, match="ISO-8601"):
        EventStore([event("E01", timestamp="2026-10-08")])


def test_event_store_rejects_timestamp_without_utc_offset():
    with pytest.raises(ValidationError, match="UTC offset"):
        EventStore([event("E01", timestamp="2026-10-08T10:00:00")])


def test_event_store_rejects_boolean_line_number():
    with pytest.raises(ValueError, match="non-integer line_number"):
        EventStore([event("E01", line=True)])


def test_event_store_rejects_blank_or_padded_ids():
    with pytest.raises(ValueError, match="non-empty event_id"):
        EventStore([event("   ")])
    with pytest.raises(ValueError, match="leading or trailing whitespace"):
        EventStore([event(" E01 ")])


def test_builder_keeps_support_and_contradiction_explicit_and_preserves_direction():
    builder = make_builder("E01", "E02", "E03")
    links = [
        link("E01", "E02", candidate="E02", score=0.90, relation="precedes"),
        link("E03", "E02", candidate="E02", evidence_type=EvidenceType.SEMANTIC,
             polarity="contradicting", score=0.70, relation="conflicting_pattern"),
    ]
    result = builder.build_candidate("E02", links, severity_score=0.80)
    assert result.supporting_events == ("E01",)
    assert result.contradicting_events == ("E03",)
    assert result.temporal_score == 0.90
    assert result.semantic_score is None
    assert result.severity_score == 0.80
    assert result.contradiction_score == 0.70
    assert result.evidence_items[0].source_event_id == "E01"
    assert result.evidence_items[0].target_event_id == "E02"


def test_link_polarity_is_scoped_to_candidate_not_both_endpoints():
    builder = make_builder("E01", "E02")
    # The caller must explicitly say polarity is being evaluated for E02.
    relation = link("E01", "E02", candidate="E02")
    target_result = builder.build_candidate("E02", [relation])
    source_result = builder.build_candidate("E01", [relation])
    assert target_result.supporting_events == ("E01",)
    assert source_result.supporting_events == ()
    assert source_result.evidence_items == ()


def test_source_endpoint_can_be_candidate_when_explicitly_selected():
    builder = make_builder("E01", "E02")
    relation = link("E01", "E02", candidate="E01", relation="precedes")
    result = builder.build_candidate("E01", [relation])
    assert result.supporting_events == ("E02",)
    assert result.evidence_items[0].event_id == "E02"
    assert result.evidence_items[0].source_event_id == "E01"
    assert result.evidence_items[0].target_event_id == "E02"


def test_builder_does_not_invent_contradiction_from_absence_of_support():
    result = make_builder("E01", "E02").build_candidate("E02", [])
    assert result.supporting_events == ()
    assert result.contradicting_events == ()
    assert result.temporal_score is None
    assert result.contradiction_score is None


def test_builder_ignores_links_unrelated_to_candidate():
    builder = make_builder("E01", "E02", "E03")
    unrelated = link("E01", "E02", candidate="E02", evidence_type=EvidenceType.DEPENDENCY,
                     relation="depends_on")
    result = builder.build_candidate("E03", [unrelated])
    assert result.evidence_items == ()


def test_builder_rejects_links_to_unknown_related_events():
    builder = make_builder("E01")
    bad_link = link("E01", "E99", candidate="E01", relation="precedes")
    with pytest.raises(KeyError, match="Unknown event_id: E99"):
        builder.build_candidate("E01", [bad_link])


def test_builder_uses_maximum_support_score_per_evidence_type():
    builder = make_builder("E01", "E02", "E03")
    links = [
        link("E01", "E03", candidate="E03", evidence_type=EvidenceType.SEMANTIC,
             score=0.50, relation="similar_template"),
        link("E02", "E03", candidate="E03", evidence_type=EvidenceType.SEMANTIC,
             score=0.80, relation="similar_template"),
    ]
    result = builder.build_candidate("E03", links)
    assert result.semantic_score == 0.80
    assert result.supporting_events == ("E01", "E02")


def test_package_deduplicates_candidate_ids_and_keeps_candidate_relative_evidence():
    builder = make_builder("E01", "E02", "E03")
    link_dict = {
        "source_event_id": "E01",
        "target_event_id": "E02",
        "candidate_event_id": "E02",
        "evidence_type": "temporal",
        "polarity": "supporting",
        "score": 0.9,
        "relation": "precedes",
    }
    package = builder.build_package("INC-001", ["E02", "E01", "E02"], [link_dict])
    assert package.incident_id == "INC-001"
    assert [c.candidate_event_id for c in package.candidates] == ["E02", "E01"]
    assert package.candidates[0].supporting_events == ("E01",)
    assert package.candidates[1].supporting_events == ()


def test_duplicate_exact_links_are_deduplicated():
    builder = make_builder("E01", "E02")
    evidence_link = link("E01", "E02", candidate="E02")
    result = builder.build_candidate("E02", [evidence_link, evidence_link])
    assert len(result.evidence_items) == 1


def test_output_is_deterministic_when_link_order_changes():
    builder = make_builder("E01", "E02", "E03")
    links = [
        link("E01", "E03", candidate="E03", score=0.7, relation="r1", reason="z"),
        link("E02", "E03", candidate="E03", score=0.8, relation="r2", reason="a"),
    ]
    first = builder.build_candidate("E03", links).model_dump_json()
    second = builder.build_candidate("E03", list(reversed(links))).model_dump_json()
    assert first == second


def test_evidence_link_rejects_out_of_range_nan_and_infinite_scores():
    for bad_score in (1.01, -0.01, float("nan"), float("inf"), True, "0.9"):
        with pytest.raises(ValidationError):
            link("E01", "E02", candidate="E02", score=bad_score)


def test_evidence_link_rejects_self_links_and_candidate_not_in_endpoints():
    with pytest.raises(ValidationError, match="must differ"):
        link("E01", "E01", candidate="E01")
    with pytest.raises(ValidationError, match="must match source_event_id"):
        link("E01", "E02", candidate="E03")


def test_evidence_link_requires_explicit_candidate_scope():
    with pytest.raises(ValidationError):
        EvidenceLink(
            source_event_id="E01",
            target_event_id="E02",
            evidence_type=EvidenceType.TEMPORAL,
            polarity="supporting",
            score=0.9,
            relation="precedes",
        )


def test_evidence_link_rejects_non_json_metadata():
    with pytest.raises(ValidationError, match="JSON-serializable"):
        link("E01", "E02", candidate="E02", metadata={"bad": object()})


def test_evidence_link_detaches_metadata_from_caller_mutations():
    metadata = {"path": {"hops": ["a", "b"]}}
    item = link("E01", "E02", candidate="E02", metadata=metadata)
    metadata["path"]["hops"].append("mutated")
    assert item.metadata == {"path": {"hops": ["a", "b"]}}


def test_schema_rejects_candidate_snapshot_mismatch():
    snapshot = EventStore([event("E01")]).require("E01")
    with pytest.raises(ValidationError, match="must equal candidate.event_id"):
        CandidateEvidence(candidate_event_id="E02", candidate=snapshot)


def test_schema_rejects_inconsistent_summary_fields():
    store = EventStore([event("E01"), event("E02")])
    evidence_link = link("E01", "E02", candidate="E02")
    result = EvidenceBuilder(store).build_candidate("E02", [evidence_link])
    data = result.model_dump()
    data["supporting_events"] = []
    with pytest.raises(ValidationError, match="supporting_events must match"):
        CandidateEvidence.model_validate(data)


def test_candidate_schema_rejects_duplicate_evidence_records():
    builder = make_builder("E01", "E02")
    evidence_link = link("E01", "E02", candidate="E02")
    result = builder.build_candidate("E02", [evidence_link])
    data = result.model_dump()
    data["evidence_items"] = data["evidence_items"] * 2
    with pytest.raises(ValidationError, match="exact duplicate records"):
        CandidateEvidence.model_validate(data)


def test_package_rejects_duplicate_candidate_ids():
    snapshot = EventStore([event("E01")]).require("E01")
    candidate = CandidateEvidence(candidate_event_id="E01", candidate=snapshot)
    with pytest.raises(ValidationError, match="must be unique"):
        EvidencePackage(incident_id="INC-1", candidates=[candidate, candidate])


def test_package_json_round_trip():
    builder = make_builder("E01", "E02")
    package = builder.build_package("INC-1", ["E02"], [link("E01", "E02", candidate="E02")])
    restored = EvidencePackage.model_validate_json(package.model_dump_json())
    assert restored == package


def test_candidate_evidence_collections_are_immutable():
    result = make_builder("E01", "E02").build_candidate(
        "E02",
        [link("E01", "E02", candidate="E02")],
    )

    with pytest.raises(AttributeError):
        result.supporting_events.clear()

    with pytest.raises(AttributeError):
        result.evidence_items.append(result.evidence_items[0])

    with pytest.raises(ValidationError):
        result.supporting_events = ()


def test_evidence_package_candidates_are_immutable():
    package = make_builder("E01").build_package("INC-1", ["E01"], [])

    with pytest.raises(AttributeError):
        package.candidates.append(package.candidates[0])

    with pytest.raises(ValidationError):
        package.candidates = ()


def test_event_store_loads_member1_events_jsonl(tmp_path):
    import json
    path = tmp_path / "events.jsonl"
    record = {
        "event_id": "evt_0123456789abcdef",
        "timestamp_iso": "2026-10-08T10:00:00+00:00",
        "severity": "ERROR",
        "service": "checkout",
        "message": "checkout request timed out",
        "template": None,
        "source_file": "checkout.log",
        "line_number": 17,
        "raw": "raw sensitive content should not be copied",
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    store = EventStore.from_jsonl(path)
    snapshot = store.require(record["event_id"])
    assert snapshot.service == "checkout"
    assert not hasattr(snapshot, "raw")


def test_event_store_jsonl_rejects_malformed_line(tmp_path):
    path = tmp_path / "events.jsonl"
    first_record = '{"event_id": "E01", "message": "valid event", "timestamp_iso": "2026-10-08T10:00:00+00:00"}'
    path.write_text(first_record + "\nnot-json\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"Invalid JSONL record at .*events.jsonl:2:"):
        EventStore.from_jsonl(path)


def test_evidence_metadata_is_deeply_immutable_and_still_json_serializable():
    builder = make_builder("E01", "E02")
    metadata = {"path": {"hops": ["api", "database"]}}
    evidence_link = link("E01", "E02", candidate="E02", metadata=metadata)
    metadata["path"]["hops"].append("mutated-external")
    assert evidence_link.metadata["path"]["hops"] == ["api", "database"]
    with pytest.raises(TypeError, match="immutable"):
        evidence_link.metadata["new_key"] = "mutated"
    with pytest.raises(TypeError, match="immutable"):
        evidence_link.metadata["path"]["hops"].append("mutated-in-place")
    item_json = evidence_link.model_dump_json()
    assert '"hops":["api","database"]' in item_json
    # Immutable metadata remains compatible with Pydantic's deep-copy API.
    assert evidence_link.model_copy(deep=True).model_dump_json() == item_json
    result = builder.build_candidate("E02", [evidence_link])
    assert result.evidence_items[0].metadata["path"]["hops"] == ["api", "database"]


def test_event_store_jsonl_reports_schema_error_with_line_number(tmp_path):
    import json

    path = tmp_path / "events.jsonl"
    valid = {
        "event_id": "E01",
        "timestamp_iso": "2026-10-08T10:00:00+00:00",
        "service": "checkout",
        "severity": "ERROR",
        "message": "checkout timed out",
    }
    invalid = {"event_id": "E02", "service": "checkout"}  # Missing message.
    path.write_text(
        json.dumps(valid) + "\n" + json.dumps(invalid) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"Invalid event at .*events.jsonl:2:.*message"):
        EventStore.from_jsonl(path)


def test_event_store_jsonl_duplicate_id_error_has_line_number(tmp_path):
    import json

    path = tmp_path / "events.jsonl"
    record = {
        "event_id": "E01",
        "timestamp_iso": "2026-10-08T10:00:00+00:00",
        "service": "checkout",
        "severity": "ERROR",
        "message": "checkout timed out",
    }
    path.write_text(
        json.dumps(record) + "\n" + json.dumps(record) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"Duplicate event_id 'E01' at .*events.jsonl:2"):
        EventStore.from_jsonl(path)
