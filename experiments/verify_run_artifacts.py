"""Verify artifact hashes recorded by run_manifest.json and experiment_manifest.json.

Usage: python -m experiments.verify_run_artifacts --run-dir artifacts/runs/run-001
The verifier refuses manifest paths that resolve outside the selected run directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_artifact_path(root: Path, name: str) -> Path:
    # Manifests may move between Windows and POSIX systems. Reject absolute
    # paths and traversal in either path syntax, regardless of host OS.
    if not isinstance(name, str) or not name:
        raise ValueError(f"invalid artifact name in manifest: {name!r}")
    windows_path = PureWindowsPath(name)
    posix_path = PurePosixPath(name)
    if (
        Path(name).is_absolute()
        or posix_path.is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or ".." in posix_path.parts
        or ".." in windows_path.parts
    ):
        raise ValueError(f"invalid artifact name in manifest: {name!r}")
    # Treat Windows separators as separators even when verifying on POSIX.
    portable_name = name.replace("\\", "/")
    candidate = (root / portable_name).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"artifact path escapes run directory: {name!r}") from exc
    return candidate


def _read_manifest(path: Path) -> dict[str, Any]:
    """Load a manifest and reject valid JSON values that are not JSON objects."""
    try:
        raw_text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path.name} is not valid UTF-8") from exc
    try:
        value = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name} is not valid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a top-level JSON object")
    return value


def _verify_hash_map(root: Path, hash_map: Any, manifest_name: str) -> list[dict[str, Any]]:
    if not isinstance(hash_map, dict):
        raise ValueError(f"{manifest_name} must contain an artifact hash object")
    checks: list[dict[str, Any]] = []
    for name, expected in sorted(hash_map.items()):
        if not isinstance(expected, str) or len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
            checks.append({"artifact": name, "status": "invalid_expected_hash"})
            continue
        try:
            path = _safe_artifact_path(root, name)
        except ValueError:
            checks.append({"artifact": name, "status": "unsafe_path"})
            continue
        if not path.is_file():
            checks.append({"artifact": name, "status": "missing"})
            continue
        actual = _sha256_file(path)
        checks.append({
            "artifact": name,
            "status": "ok" if actual == expected else "hash_mismatch",
            "expected_sha256": expected,
            "actual_sha256": actual,
        })
    return checks


def verify_run_dir(run_dir: str | Path) -> dict[str, Any]:
    root = Path(run_dir).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"run directory does not exist: {root}")
    checks: list[dict[str, Any]] = []
    run_manifest_path = root / "run_manifest.json"
    if run_manifest_path.is_file():
        run_manifest = _read_manifest(run_manifest_path)
        checks.extend(_verify_hash_map(root, run_manifest.get("artifacts"), "run_manifest.json"))
    else:
        checks.append({"artifact": "run_manifest.json", "status": "missing_manifest"})

    experiment_manifest_path = root / "experiment_manifest.json"
    if experiment_manifest_path.is_file():
        experiment_manifest = _read_manifest(experiment_manifest_path)
        checks.extend(_verify_hash_map(root, experiment_manifest.get("artifacts"), "experiment_manifest.json"))
    else:
        checks.append({"artifact": "experiment_manifest.json", "status": "missing_manifest"})

    failures = [entry for entry in checks if entry["status"] != "ok"]
    return {
        "run_directory": root.name,
        "n_hashes_checked": len(checks),
        "n_hashes_ok": len(checks) - len(failures),
        "n_hash_failures": len(failures),
        "ok": not failures,
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = verify_run_dir(args.run_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
