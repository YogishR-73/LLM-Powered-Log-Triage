"""Run the existing log-intelligence pipeline with a reproducibility manifest.

Example:
    python -m experiments.run_experiments \
      --input data/your-dataset.log --out artifacts/runs/run-001 \
      --dataset-name your-dataset --dataset-version v1 \
      --dataset-source https://example.org/dataset --dataset-license "see source"

This wraps the implemented log/event/clustering pipeline. It does not run an LLM
or measure RCA ranking; those metrics require a later prediction stage and labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import os
import platform
import subprocess
import sys
import math
import time
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

import numpy as np
import sklearn
import yaml

from src.log_intelligence import PipelineConfig, canonical_json, run_pipeline


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()



def _normalise_distribution_name(name: str) -> str:
    """Normalise distribution names for stable metadata keys."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _installed_distributions() -> dict[str, str]:
    """Return all installed distribution versions visible to this interpreter."""
    installed: dict[str, str] = {}
    for distribution in importlib_metadata.distributions():
        name = distribution.metadata.get("Name")
        version = distribution.version
        if name and version:
            installed[_normalise_distribution_name(name)] = version
    return dict(sorted(installed.items()))


def _dependency_provenance(repo_root: Path) -> dict[str, Any]:
    """Record requirements/lockfile hashes and clarify the environment snapshot."""
    requirements_path = repo_root / "requirements.txt"
    lock_candidates = (
        "requirements.lock",
        "requirements-lock.txt",
        "constraints.txt",
        "constraints/requirements.txt",
        "poetry.lock",
        "uv.lock",
        "Pipfile.lock",
        "conda-lock.yml",
    )
    lockfiles = []
    for relative_name in lock_candidates:
        path = repo_root / relative_name
        if path.is_file():
            lockfiles.append({"path": relative_name, "sha256": _sha256_file(path)})

    distributions = _installed_distributions()
    distribution_payload = json.dumps(
        distributions, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return {
        "requirements_file": {
            "path": "requirements.txt",
            "present": requirements_path.is_file(),
            "sha256": _sha256_file(requirements_path) if requirements_path.is_file() else None,
            "meaning": "Hash identifies the repository's declared requirement ranges; it is not a resolved lockfile.",
        },
        "lockfiles": lockfiles,
        "lockfile_found": bool(lockfiles),
        "installed_distributions_scope": (
            "All Python distributions visible to importlib.metadata in the active interpreter. "
            "This may include unrelated environment packages and is an environment snapshot, not a lockfile."
        ),
        "installed_distributions": distributions,
        "installed_distributions_sha256": hashlib.sha256(distribution_payload).hexdigest(),
        "versions_captured": sorted(distributions),
    }



def _semantic_clustering_available(evaluation: Any) -> bool:
    """Require successful evaluation and complete finite numeric metrics."""
    if not isinstance(evaluation, dict) or evaluation.get("status") != "completed":
        return False

    clustering = evaluation.get("clustering")
    if not isinstance(clustering, dict):
        return False

    expected_metrics = (
        "adjusted_rand_index",
        "normalized_mutual_info",
        "homogeneity",
        "completeness",
        "v_measure",
        "purity",
    )

    for metric in expected_metrics:
        value = clustering.get(metric)

        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False

        try:
            numeric_value = float(value)
        except (OverflowError, ValueError):
            return False

        if not math.isfinite(numeric_value):
            return False

    return True


def _git_commit(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    return result.stdout.strip() or None


def _load_config(path: Path | None) -> PipelineConfig:
    if path is None:
        return PipelineConfig()
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML config {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("config file must contain a YAML object")
    return PipelineConfig.model_validate(raw)


def run_experiment(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    input_path = args.input.resolve()
    out_dir = args.out.resolve()
    config_path = args.config.resolve() if args.config else None
    labels_path = args.labels.resolve() if args.labels else None

    if not input_path.is_file():
        raise FileNotFoundError(f"input log file does not exist: {input_path}")
    if labels_path is not None and not labels_path.is_file():
        raise FileNotFoundError(f"labels CSV does not exist: {labels_path}")
    if config_path is not None and not config_path.is_file():
        raise FileNotFoundError(f"config YAML does not exist: {config_path}")
    if not args.dataset_name.strip() or not args.dataset_version.strip() or not args.dataset_source.strip():
        raise ValueError("dataset name, version, and source must be non-blank")

    config = _load_config(config_path)
    t0 = time.perf_counter()
    pipeline_manifest = run_pipeline(
        input_path,
        out_dir,
        config,
        labels_path=labels_path,
        label_line_column=args.label_line_column,
        label_column=args.label_column,
        source_name=args.source_name,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    
	
    eval_path = out_dir / "evaluation.json"
    evaluation: dict[str, Any] | None = None
    if eval_path.is_file():
        evaluation = json.loads(eval_path.read_text(encoding="utf-8"))
        if isinstance(evaluation, dict) and "status" not in evaluation:
            evaluation = {
                **evaluation,
                "status": "completed",
            }



    experiment = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment_status": "completed_pipeline_run",
        "scope_note": (
            "This run measures ingestion/event extraction/clustering only. "
            "It does not claim RCA performance unless separately implemented and evaluated."
        ),
        "dataset": {
            "name": args.dataset_name,
            "version": args.dataset_version,
            "source_url": args.dataset_source,
            "license_or_terms": args.dataset_license or "not recorded; verify before reuse",
            "split": args.dataset_split,
            "input_filename": input_path.name,
            "input_sha256": _sha256_file(input_path),
            "labels_filename": labels_path.name if labels_path else None,
            "labels_sha256": _sha256_file(labels_path) if labels_path else None,
        },
        "repository": {
            "git_commit": _git_commit(repo_root),
            "python_version": platform.python_version(),
            "platform": platform.platform(),
        },
        "configuration": {
            "config_sha256": pipeline_manifest["config_sha256"],
            "config": config.model_dump(mode="json"),
            "config_file_sha256": _sha256_file(config_path) if config_path else None,
            "embedding_seed": config.embedding.seed,
            "clustering_seed": config.clustering.seed,
            "embedding_backend": config.embedding.backend,
            "embedding_model": config.embedding.model_name if config.embedding.backend == "sentence_transformer" else None,
            "embedding_model_revision": config.embedding.model_revision if config.embedding.backend == "sentence_transformer" else None,
        },
        "environment": {
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
            "python_executable_basename": Path(sys.executable).name,
            "os_name": os.name,
        },
        "dependency_provenance": _dependency_provenance(repo_root),
        "runtime": {"pipeline_wall_time_ms": round(elapsed_ms, 3)},
        "pipeline_manifest": pipeline_manifest,
        "evaluation": evaluation,
        "measured_metrics_available": {
            "ingestion_accounting": True,
            "semantic_clustering": _semantic_clustering_available(evaluation),
            "evidence_integrity": False,
            "rca_ranking": False,
            "llm_tokens_and_cost": False,
        },
        "not_evaluated_reasons": [
            "Evidence metrics require evidence-package outputs to be passed through evaluation.evidence_package_integrity.",
            "RCA ranking requires actual ranked predictions and incident-level root-cause labels.",
            "Token usage and API cost require an implemented LLM stage with provider usage metadata.",
        ],
        "artifacts": {
            file.name: _sha256_file(file)
            for file in sorted(out_dir.iterdir())
            if file.is_file() and file.name != "experiment_manifest.json"
        },
    }
    (out_dir / "experiment_manifest.json").write_text(
        canonical_json(experiment), encoding="utf-8"
    )
    return experiment


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Raw text log file")
    parser.add_argument("--out", type=Path, required=True, help="Run output directory")
    parser.add_argument("--dataset-name", required=True)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--dataset-source", required=True, help="Official dataset/release URL")
    parser.add_argument("--dataset-license", default=None)
    parser.add_argument("--dataset-split", default="unspecified")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--label-line-column", default="line_number")
    parser.add_argument("--label-column", default="event_id")
    parser.add_argument("--source-name", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run_experiment(args)
    except (FileNotFoundError, ValueError, OSError, RuntimeError) as exc:
        parser.exit(2, f"error: {exc}\n")
    ingest = result["pipeline_manifest"]["ingest"]
    print(
        f"status=completed_pipeline_run events={ingest['n_events']} "
        f"failures={ingest['n_failures']} runtime_ms={result['runtime']['pipeline_wall_time_ms']:.3f}"
    )
    print(f"experiment_manifest={args.out.resolve() / 'experiment_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
