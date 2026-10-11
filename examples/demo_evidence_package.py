"""Run a deterministic synthetic evidence-package demo, not a research result.

Run from the repository root with::

    python -m examples.demo_evidence_package
    python -m examples.demo_evidence_package --output outputs/demo/evidence_package.json

All polarities and scores below are manually authored synthetic annotations.
They are demonstration inputs, not model predictions or measured results.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import networkx as nx

from src.evidence import (
    EvidenceBuilder,
    EventStore,
    dependency_links_from_graphs,
    temporal_links_from_graph,
)


TIMES = {
    "db_error": "2026-10-08T10:00:00+00:00",
    "health_probe": "2026-10-08T10:00:01+00:00",
    "checkout_timeout": "2026-10-08T10:00:02+00:00",
    "payment_failure": "2026-10-08T10:00:03+00:00",
}


def build_demo_package():
    """Build example evidence for two possible root-cause event candidates.

    Candidate E01 is a database pool-exhaustion error. Candidate E03 is a
    checkout timeout. E04 is treated as an observed downstream symptom, not a
    root-cause candidate. The annotations are illustrative and intentionally
    do not claim to establish the real cause.
    """
    ids = {
        "db_error": "evt_0000000000000001",
        "health_probe": "evt_0000000000000002",
        "checkout_timeout": "evt_0000000000000003",
        "payment_failure": "evt_0000000000000004",
    }
    details = {
        "db_error": ("database", "ERROR", "connection pool exhausted"),
        "health_probe": ("database", "INFO", "database health probe succeeded"),
        "checkout_timeout": ("checkout", "ERROR", "checkout request timed out"),
        "payment_failure": ("payment", "ERROR", "payment failed after checkout timeout"),
    }

    records = []
    for line_number, name in enumerate(TIMES, start=1):
        service, severity, message = details[name]
        records.append(
            {
                "event_id": ids[name],
                "timestamp_iso": TIMES[name],
                "severity": severity,
                "service": service,
                "message": message,
                "template": message,
                "source_file": "synthetic_incident.log",
                "line_number": line_number,
            }
        )
    store = EventStore(records)

    # The temporal graph points from earlier to later events. The service
    # dependency graph points from consumer to provider (checkout -> database).
    temporal = nx.DiGraph()
    for name, (service, severity, message) in details.items():
        temporal.add_node(
            ids[name],
            timestamp=TIMES[name],
            service=service,
            level=severity,
            message=message,
        )
    temporal.add_edge(
        ids["db_error"], ids["health_probe"],
        time_delta_seconds=1.0, relationship="temporal_precedence",
    )
    temporal.add_edge(
        ids["health_probe"], ids["checkout_timeout"],
        time_delta_seconds=1.0, relationship="temporal_precedence",
    )
    temporal.add_edge(
        ids["checkout_timeout"], ids["payment_failure"],
        time_delta_seconds=1.0, relationship="temporal_precedence",
    )

    dependencies = nx.DiGraph()
    dependencies.add_edge("checkout", "database", relationship="service_dependency")
    dependencies.add_edge("payment", "checkout", relationship="service_dependency")

    temporal_links = temporal_links_from_graph(
        temporal,
        [
            {
                "source_event_id": ids["db_error"],
                "target_event_id": ids["health_probe"],
                "candidate_event_id": ids["db_error"],
                "polarity": "contradicting",
                "score": 0.62,
                "reason": (
                    "The database health probe succeeded immediately after the "
                    "pool-exhaustion error. This is counterevidence to a sustained "
                    "database-unavailable hypothesis, though it does not rule out "
                    "an intermittent database problem."
                ),
            },
            {
                "source_event_id": ids["checkout_timeout"],
                "target_event_id": ids["payment_failure"],
                "candidate_event_id": ids["checkout_timeout"],
                "polarity": "supporting",
                "score": 0.88,
                "reason": (
                    "The checkout timeout precedes the payment failure, whose "
                    "message explicitly reports failure after the timeout."
                ),
            },
        ],
    )

    dependency_annotations = [
        {
            "source_event_id": ids["checkout_timeout"],
            "target_event_id": ids["db_error"],
            "candidate_event_id": ids["db_error"],
            "polarity": "supporting",
            "score": 0.91,
            "reason": (
                "The checkout service depends on the database, and the database "
                "logged pool exhaustion before the checkout timeout. This supports "
                "the database error as an upstream-cause candidate in this synthetic case."
            ),
        },
        {
            "source_event_id": ids["checkout_timeout"],
            "target_event_id": ids["db_error"],
            "candidate_event_id": ids["checkout_timeout"],
            "polarity": "contradicting",
            "score": 0.91,
            "reason": (
                "The database pool-exhaustion error occurs in a service that the "
                "checkout service depends on, making the checkout timeout less "
                "plausible as the initiating root-cause event."
            ),
        },
    ]
    dependency_links = dependency_links_from_graphs(
        temporal, dependencies, dependency_annotations
    )

    builder = EvidenceBuilder(store)
    return builder.build_package(
        incident_id="SYNTHETIC-INCIDENT-001",
        candidate_event_ids=[ids["db_error"], ids["checkout_timeout"]],
        evidence_links=[*temporal_links, *dependency_links],
        severity_scores={
            ids["db_error"]: 0.95,
            ids["checkout_timeout"]: 0.85,
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/demo/evidence_package.json"),
        help="Path for the serialized package (default: outputs/demo/evidence_package.json)",
    )
    args = parser.parse_args()
    package = build_demo_package()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(package.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"Wrote synthetic evidence package: {args.output}")
    print(
        f"Candidates: {len(package.candidates)}; evidence items: "
        f"{sum(len(candidate.evidence_items) for candidate in package.candidates)}"
    )
    print("DEMO ONLY: these synthetic annotations are not measured RCA results.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
