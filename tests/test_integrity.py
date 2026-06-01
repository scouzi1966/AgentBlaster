from __future__ import annotations

import pytest

from agentblaster.errors import ConfigError
from agentblaster.integrity import (
    SIGNATURE_FILENAME,
    sha256_file,
    sign_run_integrity,
    verify_run_integrity,
    verify_run_signature,
)
from agentblaster.models import RunIntegrityManifest


def test_verify_run_integrity_accepts_matching_artifacts(tmp_path) -> None:
    run_dir = tmp_path / "run_test"
    run_dir.mkdir()
    manifest_path = run_dir / "manifest.json"
    results_path = run_dir / "results.jsonl"
    manifest_path.write_text('{"run_id":"run_test"}\n', encoding="utf-8")
    results_path.write_text('{"ok":true}\n', encoding="utf-8")
    integrity = RunIntegrityManifest(
        run_id="run_test",
        created_at="2026-05-31T00:00:00Z",
        artifacts={
            "manifest.json": sha256_file(manifest_path),
            "results.jsonl": sha256_file(results_path),
        },
    )
    (run_dir / "integrity.json").write_text(integrity.model_dump_json(), encoding="utf-8")

    result = verify_run_integrity(run_dir)

    assert result.ok is True
    assert result.checked == 2
    assert result.missing == []
    assert result.changed == []


def test_verify_run_integrity_detects_changed_missing_and_extra_artifacts(tmp_path) -> None:
    run_dir = tmp_path / "run_test"
    run_dir.mkdir()
    manifest_path = run_dir / "manifest.json"
    results_path = run_dir / "results.jsonl"
    manifest_path.write_text('{"run_id":"run_test"}\n', encoding="utf-8")
    results_path.write_text('{"ok":true}\n', encoding="utf-8")
    integrity = RunIntegrityManifest(
        run_id="run_test",
        created_at="2026-05-31T00:00:00Z",
        artifacts={
            "manifest.json": sha256_file(manifest_path),
            "results.jsonl": sha256_file(results_path),
            "summary.json": "0" * 64,
        },
    )
    (run_dir / "integrity.json").write_text(integrity.model_dump_json(), encoding="utf-8")
    manifest_path.write_text('{"run_id":"tampered"}\n', encoding="utf-8")
    (run_dir / "notes.txt").write_text("operator note\n", encoding="utf-8")

    result = verify_run_integrity(run_dir, allow_extra=False)

    assert result.ok is False
    assert result.changed == ["manifest.json"]
    assert result.missing == ["summary.json"]
    assert result.extra == ["notes.txt"]


def test_verify_run_integrity_requires_manifest(tmp_path) -> None:
    with pytest.raises(ConfigError, match="missing integrity manifest"):
        verify_run_integrity(tmp_path)


def test_verify_run_integrity_rejects_unsafe_artifact_paths(tmp_path) -> None:
    run_dir = tmp_path / "run_test"
    run_dir.mkdir()
    integrity = RunIntegrityManifest(
        run_id="run_test",
        created_at="2026-05-31T00:00:00Z",
        artifacts={"../outside.txt": "0" * 64},
    )
    (run_dir / "integrity.json").write_text(integrity.model_dump_json(), encoding="utf-8")

    with pytest.raises(ConfigError, match="unsafe artifact path"):
        verify_run_integrity(run_dir)


def test_sign_and_verify_run_integrity_signature(tmp_path) -> None:
    run_dir = tmp_path / "run_test"
    run_dir.mkdir()
    manifest_path = run_dir / "manifest.json"
    results_path = run_dir / "results.jsonl"
    manifest_path.write_text('{"run_id":"run_test"}\n', encoding="utf-8")
    results_path.write_text('{"ok":true}\n', encoding="utf-8")
    integrity = RunIntegrityManifest(
        run_id="run_test",
        created_at="2026-05-31T00:00:00Z",
        artifacts={
            "manifest.json": sha256_file(manifest_path),
            "results.jsonl": sha256_file(results_path),
        },
    )
    (run_dir / "integrity.json").write_text(integrity.model_dump_json(), encoding="utf-8")

    signature_path = sign_run_integrity(run_dir, key="signing-secret", key_id="ci-key")
    result = verify_run_signature(run_dir, key="signing-secret")
    strict_result = verify_run_signature(run_dir, key="signing-secret", allow_extra=False)

    assert signature_path == run_dir / SIGNATURE_FILENAME
    assert result.ok is True
    assert result.signature_ok is True
    assert result.integrity_ok is True
    assert result.key_id == "ci-key"
    assert strict_result.ok is True

    wrong_key_result = verify_run_signature(run_dir, key="wrong-secret")

    assert wrong_key_result.ok is False
    assert wrong_key_result.signature_ok is False
    assert wrong_key_result.integrity_ok is True
