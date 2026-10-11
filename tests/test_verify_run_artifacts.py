from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from experiments.verify_run_artifacts import main as verify_main, verify_run_dir


def _write_manifest(path: Path, artifacts: dict[str, str] | list | None = None) -> None:
    payload = {"schema_version": 1, "artifacts": artifacts if artifacts is not None else {}}
    path.write_text(json.dumps(payload), encoding="utf-8")


def _valid_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    artifact = run_dir / "events.jsonl"
    artifact.write_text('{"event_id":"evt_1"}\n', encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    _write_manifest(run_dir / "run_manifest.json", {"events.jsonl": digest})
    _write_manifest(run_dir / "experiment_manifest.json", {"events.jsonl": digest})
    return run_dir


def test_verifier_accepts_valid_manifests_and_hashes(tmp_path: Path) -> None:
    result = verify_run_dir(_valid_run_dir(tmp_path))
    assert result["ok"] is True
    assert result["n_hashes_checked"] == 2
    assert result["n_hashes_ok"] == 2


def test_verifier_reports_hash_mismatch(tmp_path: Path) -> None:
    run_dir = _valid_run_dir(tmp_path)
    (run_dir / "events.jsonl").write_text("changed\n", encoding="utf-8")

    result = verify_run_dir(run_dir)

    assert result["ok"] is False
    assert result["n_hash_failures"] == 2
    assert {item["status"] for item in result["checks"]} == {"hash_mismatch"}


def test_verifier_reports_missing_artifact(tmp_path: Path) -> None:
    run_dir = _valid_run_dir(tmp_path)
    _write_manifest(run_dir / "run_manifest.json", {"missing.json": "a" * 64})

    result = verify_run_dir(run_dir)

    assert result["ok"] is False
    assert any(item["status"] == "missing" for item in result["checks"])


def test_verifier_reports_unsafe_parent_path(tmp_path: Path) -> None:
    run_dir = _valid_run_dir(tmp_path)
    _write_manifest(run_dir / "run_manifest.json", {"../outside.txt": "a" * 64})

    result = verify_run_dir(run_dir)

    assert result["ok"] is False
    assert any(item["status"] == "unsafe_path" for item in result["checks"])


def test_verifier_rejects_absolute_artifact_path(tmp_path: Path) -> None:
    run_dir = _valid_run_dir(tmp_path)
    outside = (tmp_path / "outside.txt").resolve()
    _write_manifest(run_dir / "run_manifest.json", {str(outside): "a" * 64})

    result = verify_run_dir(run_dir)

    assert result["ok"] is False
    assert any(item["status"] == "unsafe_path" for item in result["checks"])


@pytest.mark.parametrize("manifest_name", ["run_manifest.json", "experiment_manifest.json"])
@pytest.mark.parametrize("manifest_text", ["{not json", "[]", "null", '"manifest"', "42"])
def test_verifier_rejects_malformed_or_non_object_manifest(
    tmp_path: Path, manifest_name: str, manifest_text: str
) -> None:
    run_dir = _valid_run_dir(tmp_path)
    (run_dir / manifest_name).write_text(manifest_text, encoding="utf-8")

    with pytest.raises(ValueError, match=manifest_name):
        verify_run_dir(run_dir)


def test_verifier_rejects_non_object_artifacts_field(tmp_path: Path) -> None:
    run_dir = _valid_run_dir(tmp_path)
    (run_dir / "run_manifest.json").write_text(
        json.dumps({"schema_version": 1, "artifacts": ["events.jsonl"]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="artifact hash object"):
        verify_run_dir(run_dir)


def test_verifier_rejects_non_utf8_manifest(tmp_path: Path) -> None:
    run_dir = _valid_run_dir(tmp_path)
    (run_dir / "experiment_manifest.json").write_bytes(b"\xff\xfe")

    with pytest.raises(ValueError, match="experiment_manifest.json.*UTF-8"):
        verify_run_dir(run_dir)


@pytest.mark.parametrize("unsafe_name", ["../outside.txt", r"..\outside.txt", r"C:\temp\outside.txt", r"\\server\share\outside.txt"])
def test_verifier_rejects_cross_platform_unsafe_paths(tmp_path: Path, unsafe_name: str) -> None:
    run_dir = _valid_run_dir(tmp_path)
    _write_manifest(run_dir / "run_manifest.json", {unsafe_name: "a" * 64})

    result = verify_run_dir(run_dir)

    assert result["ok"] is False
    assert any(item["status"] == "unsafe_path" for item in result["checks"])


def test_verifier_cli_reports_valid_json_with_wrong_top_level_type_cleanly(
    tmp_path: Path, capsys
) -> None:
    run_dir = _valid_run_dir(tmp_path)
    (run_dir / "experiment_manifest.json").write_text("[]", encoding="utf-8")

    with pytest.raises(SystemExit) as exit_info:
        verify_main(["--run-dir", str(run_dir)])

    assert exit_info.value.code == 2
    captured = capsys.readouterr()
    assert "experiment_manifest.json must contain a top-level JSON object" in captured.err
    assert "AttributeError" not in captured.err
    assert "Traceback" not in captured.err
