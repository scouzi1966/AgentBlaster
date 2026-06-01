from __future__ import annotations

import json
from zipfile import ZipFile

import pytest

from agentblaster.bundle import create_matrix_publication_bundle, create_publication_bundle, create_replay_bundle
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
            "report.pdf": "%PDF-1.4\n",
            "report-card.svg": "<svg></svg>",
            "report-card.png": "\x89PNG\n",
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
        assert "report.pdf" in names
        assert "report-card.svg" in names
        assert "report-card.png" in names
        assert "signature.json" in names
        assert "integrity.json" in names
        assert "manifest.json" in names
        assert "results.jsonl" not in names
        assert "raw/case.response.json" not in names
        bundle_manifest = json.loads(archive.read("publication-bundle-manifest.json").decode("utf-8"))
        assert bundle_manifest["integrity"]["signature_manifest_present"] is True
        assert bundle_manifest["integrity"]["signature_key_id"] == "test"
        assert bundle_manifest["integrity"]["signature_manifest_matches_integrity"] is True
        assert bundle_manifest["integrity"]["unsigned_publication_artifacts"] == []
        assert bundle_manifest["media_kit"]["schema_version"] == "agentblaster.media-kit.v1"
        assert bundle_manifest["media_kit"]["missing_recommended_assets"] == []
        assert "media-post-packet" in {item["name"] for item in bundle_manifest["media_kit"]["recommended_sets"]}
        media_assets = {item["artifact"]: item for item in bundle_manifest["media_kit"]["assets"]}
        assert media_assets["report.pdf"]["role"] == "executive-summary"
        assert media_assets["report-card.svg"]["dimensions"] == "1200x630"


def test_create_publication_bundle_requires_publication_manifest(tmp_path) -> None:
    run_dir = _write_verified_run(tmp_path)

    with pytest.raises(ConfigError, match="publication.json"):
        create_publication_bundle(run_dir)


def test_create_publication_bundle_rejects_stale_signature_manifest(tmp_path) -> None:
    run_dir = _write_verified_run(
        tmp_path,
        extra_artifacts={
            "publication.json": "{}\n",
            "summary.json": "{}\n",
        },
    )
    sign_run_integrity(run_dir, key="signing-secret", key_id="test")
    (run_dir / "summary.json").write_text('{"changed":true}\n', encoding="utf-8")
    integrity = RunIntegrityManifest(
        run_id="run_test",
        created_at="2026-05-31T00:00:00Z",
        artifacts={
            "manifest.json": sha256_file(run_dir / "manifest.json"),
            "results.jsonl": sha256_file(run_dir / "results.jsonl"),
            "publication.json": sha256_file(run_dir / "publication.json"),
            "summary.json": sha256_file(run_dir / "summary.json"),
        },
    )
    (run_dir / "integrity.json").write_text(integrity.model_dump_json(), encoding="utf-8")

    with pytest.raises(ConfigError, match="signature manifest does not match integrity manifest"):
        create_publication_bundle(run_dir)


def test_create_matrix_publication_bundle_contains_only_matrix_artifacts(tmp_path) -> None:
    summary = tmp_path / "qwen-gemma-matrix-summary.json"
    summary.write_text('{"matrix_name":"qwen-gemma"}\n', encoding="utf-8")
    scorecard_payload = {
        "scorecard": {
            "engine_targets": [
                {
                    "id": "afm-mlx",
                    "display_name": "AFM MLX",
                    "primary_scoring_contract": "openai-chat-completions",
                    "ignored_detail": "not promoted",
                },
                {
                    "id": "ollama-mlx",
                    "display_name": "Ollama MLX",
                    "primary_scoring_contract": "openai-chat-completions",
                },
            ]
        },
        "architecture_summary": [
            {
                "model_architecture": "qwen3.6-dense",
                "runs": 2,
                "completed_runs": 2,
                "failed_runs": 0,
                "result_artifacts_loaded": 2,
                "total_cases": 10,
                "passed": 10,
                "failed": 0,
                "pass_rate_percent": 100.0,
                "avg_latency_ms": 100.0,
                "avg_decode_tokens_per_second": 42.0,
                "judge_rubric_cases": 2,
                "judge_verdicts_valid": 2,
            }
        ],
        "quantization_summary": [
            {
                "quantization": "mlx-f16",
                "runs": 2,
                "completed_runs": 2,
                "failed_runs": 0,
                "result_artifacts_loaded": 2,
                "total_cases": 10,
                "passed": 10,
                "failed": 0,
                "pass_rate_percent": 100.0,
                "avg_latency_ms": 100.0,
                "avg_decode_tokens_per_second": 42.0,
                "judge_rubric_cases": 2,
                "judge_verdicts_valid": 2,
            }
        ],
    }
    for name, content in {
        "qwen-gemma-matrix-summary-matrix-report.json": "{}\n",
        "qwen-gemma-matrix-summary-matrix-report.html": "<html></html>",
        "qwen-gemma-matrix-summary-matrix-report.pdf": "%PDF-1.4\n",
        "qwen-gemma-matrix-summary-matrix-scorecard.json": json.dumps(scorecard_payload) + "\n",
        "qwen-gemma-matrix-summary-matrix-scorecard.svg": "<svg></svg>",
        "qwen-gemma-matrix-summary-matrix-scorecard.png": "\x89PNG\n",
        "qwen-gemma-matrix-summary-matrix-scorecard.pdf": "%PDF-1.4\n",
        "results.jsonl": '{"raw":"not bundled"}\n',
    }.items():
        (tmp_path / name).write_text(content, encoding="utf-8")

    bundle_path = create_matrix_publication_bundle(summary, output_dir=tmp_path / "bundles")

    assert bundle_path.name == "qwen-gemma-matrix-summary.agentblaster-matrix-publication.zip"
    with ZipFile(bundle_path) as archive:
        names = archive.namelist()
        assert names == sorted(names)
        assert "qwen-gemma-matrix-summary.json" in names
        assert "qwen-gemma-matrix-summary-matrix-report.json" in names
        assert "qwen-gemma-matrix-summary-matrix-report.pdf" in names
        assert "qwen-gemma-matrix-summary-matrix-scorecard.json" in names
        assert "qwen-gemma-matrix-summary-matrix-scorecard.svg" in names
        assert "qwen-gemma-matrix-summary-matrix-scorecard.png" in names
        assert "qwen-gemma-matrix-summary-matrix-scorecard.pdf" in names
        assert "matrix-publication-bundle-manifest.json" in names
        bundle_manifest = json.loads(archive.read("matrix-publication-bundle-manifest.json").decode("utf-8"))
        assert bundle_manifest["schema_version"] == "agentblaster.matrix-publication-bundle.v1"
        assert bundle_manifest["engine_targets"] == [
            {
                "id": "afm-mlx",
                "display_name": "AFM MLX",
                "primary_scoring_contract": "openai-chat-completions",
            },
            {
                "id": "ollama-mlx",
                "display_name": "Ollama MLX",
                "primary_scoring_contract": "openai-chat-completions",
            },
        ]
        assert bundle_manifest["architecture_summary"][0]["model_architecture"] == "qwen3.6-dense"
        assert bundle_manifest["quantization_summary"][0]["quantization"] == "mlx-f16"
        assert bundle_manifest["security"]["contains_results_jsonl"] is False
        assert bundle_manifest["media_kit"]["schema_version"] == "agentblaster.media-kit.v1"
        assert bundle_manifest["media_kit"]["missing_recommended_assets"] == []
        media_assets = {item["artifact"]: item for item in bundle_manifest["media_kit"]["assets"]}
        assert media_assets["qwen-gemma-matrix-summary-matrix-scorecard.svg"]["role"] == "scorecard-card-vector"
        assert media_assets["qwen-gemma-matrix-summary-matrix-scorecard.pdf"]["role"] == "executive-scorecard"
        assert "results.jsonl" not in names
        for info in archive.infolist():
            assert info.date_time == (1980, 1, 1, 0, 0, 0)


def test_create_matrix_publication_bundle_requires_scorecard_json(tmp_path) -> None:
    summary = tmp_path / "matrix-summary.json"
    summary.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="matrix scorecard JSON"):
        create_matrix_publication_bundle(summary)


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
