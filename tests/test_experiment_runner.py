from __future__ import annotations

import argparse
import json
from pathlib import Path

from experiments.run_experiments import run_experiment
from experiments.verify_run_artifacts import verify_run_dir


def test_runner_records_reproducibility_and_no_unmeasured_rca_claims(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "run"
    args = argparse.Namespace(
        input=root / "data" / "synthetic_review1_incident.log",
        out=output,
        config=None,
        labels=None,
        label_line_column="line_number",
        label_column="event_id",
        source_name="synthetic-review1-fixture",
        dataset_name="synthetic-review1-fixture",
        dataset_version="1",
        dataset_source="repository-local synthetic fixture",
        dataset_license="synthetic; not a public dataset",
        dataset_split="smoke-test-only",
    )
    result = run_experiment(args)
    saved = json.loads((output / "experiment_manifest.json").read_text(encoding="utf-8"))
    assert result["dataset"]["input_sha256"]
    assert saved["pipeline_manifest"]["ingest"]["accounting_ok"] is True
    assert saved["pipeline_manifest"]["ingest"]["n_events"] == 10
    assert saved["pipeline_manifest"]["ingest"]["n_failures"] == 0
    assert saved["evaluation"] is None
    assert saved["measured_metrics_available"]["rca_ranking"] is False
    assert saved["measured_metrics_available"]["llm_tokens_and_cost"] is False
    for artifact_name, digest in saved["artifacts"].items():
        import hashlib
        hasher = hashlib.sha256((output / artifact_name).read_bytes()).hexdigest()
        assert hasher == digest
    verification = verify_run_dir(output)
    assert verification["ok"] is True
    assert verification["n_hashes_checked"] > 0


def test_evidence_evaluation_runner_reports_synthetic_package_integrity(tmp_path: Path) -> None:
    from examples.demo_evidence_package import build_demo_package
    from experiments.evaluate_evidence_package import evaluate_files

    package_path = tmp_path / "package.json"
    package_path.write_text(build_demo_package().model_dump_json(indent=2), encoding="utf-8")
    events_path = Path(__file__).resolve().parents[1] / "data" / "synthetic_evidence_events.jsonl"
    result = evaluate_files(package_path, events_path)
    assert result["metrics"]["n_packages_evaluated"] == 1
    assert result["metrics"]["schema_valid_package_rate"] == 1.0
    assert result["metrics"]["event_references"]["valid_event_reference_rate"] == 1.0
    assert result["metrics"]["n_relationship_records"] == 4
