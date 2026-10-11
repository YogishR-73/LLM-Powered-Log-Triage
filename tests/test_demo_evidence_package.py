import json
from pathlib import Path

from examples.demo_evidence_package import build_demo_package
from src.evidence import EvidencePackage


def test_demo_builds_valid_serializable_evidence_package():
    package = build_demo_package()
    encoded = package.model_dump_json()
    restored = EvidencePackage.model_validate_json(encoded)

    assert restored.incident_id == "SYNTHETIC-INCIDENT-001"
    assert len(restored.candidates) == 2

    database = next(c for c in restored.candidates if c.candidate.service == "database")
    checkout = next(c for c in restored.candidates if c.candidate.service == "checkout")

    # Candidate-relative evidence: same dependency relation can support one
    # candidate and contradict another because polarity is explicitly scoped.
    assert database.candidate_event_id != checkout.candidate_event_id
    assert database.supporting_events == ("evt_0000000000000003",)
    assert database.contradicting_events == ("evt_0000000000000002",)
    assert database.dependency_score == 0.91
    assert database.contradiction_score == 0.62

    assert checkout.supporting_events == ("evt_0000000000000004",)
    assert checkout.contradicting_events == ("evt_0000000000000001",)
    assert checkout.temporal_score == 0.88
    assert checkout.contradiction_score == 0.91


def test_demo_is_deterministic():
    first = build_demo_package().model_dump_json()
    second = build_demo_package().model_dump_json()
    assert first == second


def test_checked_in_sample_matches_demo_output():
    sample_path = Path(__file__).resolve().parents[1] / "examples" / "sample_evidence_package.json"
    checked_in_sample = json.loads(sample_path.read_text(encoding="utf-8"))
    generated_sample = json.loads(build_demo_package().model_dump_json(indent=2))
    assert checked_in_sample == generated_sample
