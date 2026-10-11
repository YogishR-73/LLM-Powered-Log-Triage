"""Evaluate evidence-package schema and event-ID integrity against event JSONL.

Usage:
  python -m experiments.evaluate_evidence_package \
      --package artifacts/package.json \
      --events-jsonl artifacts/events.jsonl \
      --out artifacts/evidence_integrity.json

This checks structural consistency and whether IDs exist. It does not determine
whether the cited events actually support a causal claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.log_intelligence import canonical_json
from evaluation.metrics import evidence_package_integrity


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_jsonl_event_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                raise ValueError(f"blank event JSONL record at line {line_no}")
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid event JSON at line {line_no}") from exc
            if not isinstance(record, Mapping):
                raise ValueError(f"event JSONL line {line_no} must be an object")
            event_id = record.get("event_id")
            if not isinstance(event_id, str) or not event_id.strip() or event_id != event_id.strip():
                raise ValueError(f"invalid event_id at line {line_no}")
            if event_id in ids:
                raise ValueError(f"duplicate event_id at line {line_no}: {event_id}")
            ids.add(event_id)
    return ids


def evaluate_files(package_path: str | Path, events_path: str | Path) -> dict[str, Any]:
    package_file = Path(package_path).resolve()
    events_file = Path(events_path).resolve()
    if not package_file.is_file():
        raise FileNotFoundError(f"package JSON does not exist: {package_file}")
    if not events_file.is_file():
        raise FileNotFoundError(f"events JSONL does not exist: {events_file}")
    try:
        data = json.loads(package_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid package JSON: {exc.msg}") from exc
    packages = data if isinstance(data, list) else [data]
    known_ids = _read_jsonl_event_ids(events_file)
    metrics = evidence_package_integrity(packages, known_ids)
    return {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope_note": "Schema and event-reference integrity only; not evidence truth or RCA accuracy.",
        "inputs": {
            "package_filename": package_file.name,
            "package_sha256": _sha256_file(package_file),
            "events_filename": events_file.name,
            "events_sha256": _sha256_file(events_file),
            "n_known_events": len(known_ids),
        },
        "metrics": metrics,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--events-jsonl", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = evaluate_files(args.package, args.events_jsonl)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(canonical_json(result), encoding="utf-8")
    print(json.dumps({
        "output": str(args.out),
        "n_packages": result["metrics"]["n_packages_evaluated"],
        "schema_valid_package_rate": result["metrics"]["schema_valid_package_rate"],
        "valid_event_reference_rate": result["metrics"]["event_references"]["valid_event_reference_rate"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
