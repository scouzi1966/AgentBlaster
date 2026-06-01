from __future__ import annotations

from zipfile import ZipFile

import pytest

from agentblaster.bundle import create_publication_bundle, create_replay_bundle
from agentblaster.errors import ConfigError
from agentblaster.integrity import sha256_file, sign_run_integrity
from agentblaster.models import RunIntegrityManifest


def test_create_replay_bundle_contains_verified_artifacts(tmp_path) -> None:
    run_dir = _write_verified_run(tmp_path)

    bundle_path = create_replay_bundle(run_dir, output_dir=tmp_path / "bundles")

    assert bundle_path.name == "run_test.agentblaster.zip"
    with ZipFile(bundle_path) as archive:
        assert archive.namelist() == ["integrity.json", "manifest.json", "results.jsonl"]
        for info in archive.infolist():
            assert info.date_time == (1980, 1, 1, 0, 0, 0)
        assert archive.read("results.jsonl") == b'{"ok":true}\n'


def test_create_replay_bundle_rejects_tampered_runs(tmp_path) -> None:
    run_dir = _write_verified_run(tmp_path)
    (run_dir / "results.jsonl").write_text('{"ok":false}\n', encoding="utf-8")

    with pytest.raises(ConfigError, match="integrity verification failed"):
        create_replay_bundle(run_dir)


def test_create_replay_bundle_rejects_unsafe_integrity_paths(tmp_path) -> None:
    run_dir = tmp_path / "run_test"
    run_dir.mkdir()
    (run_dir / "manifest.json").write_text('{"run_id":"run_test"}\n', encoding="utf-8")
    integrity = RunIntegrityManifest(
        run_id="run_test",
        created_at="2026-05-31T00:00:00Z",
        artifacts={"../secret.txt": "0" * 64},
    )
    (run_dir / "integrity.json").write_text(integrity.model_dump_json(), encoding="utf-8")

    with pytest.raises(ConfigError, match="unsafe artifact path"):
        create_replay_bundle(run_dir)


def test_create_publication_bundle_contains_only_shareable_artifacts(tmp_path) -> None:
    run_dir = _write_verified_run(
        tmp_path,
        extra_artifacts={
            "suite.json": "{}\n",
            "summary.json": "{}\n",
            "publication.json": "{}\n",
            "report.html": "<html></html>",
            "report.md": "# report\n",
            "report-card.svg": "<svg></svg>",
            "raw/case.response.json": '{"secret":"raw"}\n',
        },
    )
    sign_run_integrity(run_dir, key="signing-secret", key_id="test")

    bundle_path = create_publication_bundle(run_dir, output_dir=tmp_path / "bundles")

    assert bundle_path.name == "run_test.agentblaster-publication.zip"
    with ZipFile(bundle_path) as archive:
        names = archive.namelist()
        assert names == sorted(names)
        assert "publication.json" in names
        assert "report-card.svg" in names
        assert "signature.json" in names
        assert "integrity.json" in names
        assert "manifest.json" in names
        assert "results.jsonl" not in names
        assert "raw/case.response.json" not in names


def test_create_publication_bundle_requires_publication_manifest(tmp_path) -> None:
    run_dir = _write_verified_run(tmp_path)

    with pytest.raises(ConfigError, match="publication.json"):
        create_publication_bundle(run_dir)


def _write_verified_run(tmp_path, extra_artifacts: dict[str, str] | None = None):
    run_dir = tmp_path / "run_test"
    run_dir.mkdir()
    manifest_path = run_dir / "manifest.json"
    results_path = run_dir / "results.jsonl"
    manifest_path.write_text('{"run_id":"run_test"}\n', encoding="utf-8")
    results_path.write_text('{"ok":true}\n', encoding="utf-8")
    artifacts = {
        "manifest.json": sha256_file(manifest_path),
        "results.jsonl": sha256_file(results_path),
    }
    for relative_path, content in (extra_artifacts or {}).items():
        path = run_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        artifacts[relative_path] = sha256_file(path)
    integrity = RunIntegrityManifest(
        run_id="run_test",
        created_at="2026-05-31T00:00:00Z",
        artifacts=artifacts,
    )
    (run_dir / "integrity.json").write_text(integrity.model_dump_json(), encoding="utf-8")
    return run_dir
