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
    assert saved["measured_metrics_available"]["semantic_clustering"] is False
    assert saved["measured_metrics_available"]["rca_ranking"] is False
    assert saved["measured_metrics_available"]["llm_tokens_and_cost"] is False
    provenance = saved["dependency_provenance"]
    assert provenance["requirements_file"]["present"] is True
    assert len(provenance["requirements_file"]["sha256"]) == 64
    assert "scikit-learn" in provenance["installed_distributions"]
    assert provenance["installed_distributions_sha256"]
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


def test_semantic_clustering_availability_requires_success_status_and_metrics() -> None:
    from experiments.run_experiments import _semantic_clustering_available

    metrics = {
        "adjusted_rand_index": 0.7,
        "normalized_mutual_info": 0.8,
        "homogeneity": 0.75,
        "completeness": 0.76,
        "v_measure": 0.755,
        "purity": 0.9,
    }

    assert (
        _semantic_clustering_available(
            {"status": "completed", "clustering": metrics}
        )
        is True
    )
    assert (
        _semantic_clustering_available(
            {"status": "skipped", "clustering": metrics}
        )
        is False
    )
    assert (
        _semantic_clustering_available(
            {"status": "running", "clustering": metrics}
        )
        is False
    )
    assert _semantic_clustering_available({"clustering": metrics}) is False

    assert (
        _semantic_clustering_available(
            {
                "status": "completed",
                "clustering": {"adjusted_rand_index": 0.7},
            }
        )
        is False
    )

    invalid = {**metrics, "purity": None}
    assert (
        _semantic_clustering_available(
            {"status": "completed", "clustering": invalid}
        )
        is False
    )

    # Extremely large integers must be rejected without raising an exception.
    oversized_integer = {**metrics, "purity": 10**1000}
    assert (
        _semantic_clustering_available(
            {"status": "completed", "clustering": oversized_integer}
        )
        is False
    )


def test_runner_marks_semantic_clustering_available_only_for_successful_labelled_evaluation(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[1]
    labels_path = tmp_path / "labels.csv"
    labels_path.write_text(
        "line_number,event_id\n" + "\n".join(f"{line},group_{(line - 1) // 2}" for line in range(1, 11)) + "\n",
        encoding="utf-8",
    )
    args = argparse.Namespace(
        input=root / "data" / "synthetic_review1_incident.log",
        out=tmp_path / "labelled_run",
        config=None,
        labels=labels_path,
        label_line_column="line_number",
        label_column="event_id",
        source_name="synthetic-labelled-fixture",
        dataset_name="synthetic-labelled-fixture",
        dataset_version="1",
        dataset_source="repository-local synthetic fixture with test-only labels",
        dataset_license="synthetic; test-only labels",
        dataset_split="unit-test-only",
    )

    result = run_experiment(args)

    assert result["evaluation"]["status"] == "completed"
    assert result["measured_metrics_available"]["semantic_clustering"] is True
    assert "adjusted_rand_index" in result["evaluation"]["clustering"]
    assert "normalized_mutual_info" in result["evaluation"]["clustering"]


def test_runner_reports_malformed_yaml_config_as_cli_error(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from experiments.run_experiments import main

    root = Path(__file__).resolve().parents[1]
    input_path = root / "data" / "synthetic_review1_incident.log"
    config_path = tmp_path / "broken.yaml"
    config_path.write_text("embedding: [unterminated\n", encoding="utf-8")
    output_path = tmp_path / "out"
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_experiments",
            "--input", str(input_path),
            "--out", str(output_path),
            "--dataset-name", "test",
            "--dataset-version", "1",
            "--dataset-source", "local-test",
            "--config", str(config_path),
        ],
    )

    try:
        main()
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("malformed YAML should fail with CLI exit code 2")

    captured = capsys.readouterr()
    assert "invalid YAML config" in captured.err
    assert not output_path.exists()
