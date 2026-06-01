from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from agentblaster.benchmark_kit import create_benchmark_kit
from agentblaster.cli import app


def test_benchmark_kit_generates_matrix_manifest_and_runbook(tmp_path) -> None:
    kit = create_benchmark_kit(
        tmp_path,
        providers=["afm", "lm-studio"],
        targets=["qwen3.6-27b-dense", "gemma-4-31b-dense"],
        suite="trace-replay",
        policy="agentblaster.policy.yaml",
    )

    manifest = json.loads(kit.manifest_path.read_text(encoding="utf-8"))
    matrix_text = kit.matrix_path.read_text(encoding="utf-8")
    runbook = kit.runbook_path.read_text(encoding="utf-8")

    assert manifest["schema_version"] == "agentblaster.benchmark-kit.v1"
    assert manifest["suite"] == "trace-replay"
    assert manifest["providers"] == ["afm", "lm-studio"]
    assert manifest["targets"] == ["qwen3.6-27b-dense", "gemma-4-31b-dense"]
    assert manifest["safety"]["contacts_providers"] is False
    assert len(manifest["readiness_commands"]) == 4
    assert "engine: afm" in matrix_text
    assert "model: mlx-community/Qwen3.6-27B" in matrix_text
    assert "model: google/gemma-4-31b" in matrix_text
    assert "agentblaster providers readiness --provider afm" in runbook
    assert "agentblaster matrix contract-checks" in runbook
    assert "agentblaster matrix scorecard" in runbook
    assert "agentblaster matrix publication-bundle" in runbook
    assert "contract_execute" in manifest["matrix_commands"]
    assert "publication_bundle" in manifest["matrix_commands"]
    assert "--max-tool-loop-stop-reason max_tool_calls_reached=0" in runbook
    assert "--max-invalid-tool-calls 0" in runbook
    assert "--min-tool-parser-repair-valid-rate 100" in runbook
    assert "max_tool_calls_reached=0" in " ".join(manifest["matrix_commands"]["gate"])
    assert "--max-invalid-tool-calls" in manifest["matrix_commands"]["gate"]
    assert "--min-tool-parser-repair-valid-rate" in manifest["matrix_commands"]["gate"]
    assert "--offline --continue-on-error" in runbook


def test_benchmark_kit_refuses_to_overwrite_unknown_entries(tmp_path) -> None:
    (tmp_path / "keep.txt").write_text("do not touch", encoding="utf-8")

    with pytest.raises(ValueError, match="non-kit entries"):
        create_benchmark_kit(tmp_path)


def test_cli_benchmark_kit_writes_expected_artifacts(tmp_path) -> None:
    runner = CliRunner()
    output_dir = tmp_path / "kit"

    result = runner.invoke(
        app,
        [
            "models",
            "benchmark-kit",
            "--output-dir",
            str(output_dir),
            "--providers",
            "afm",
            "--targets",
            "qwen3.6-27b-dense",
            "--suite",
            "smoke",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "manifest:" in result.output
    assert (output_dir / "benchmark-kit.json").exists()
    assert (output_dir / "RUNBOOK.md").exists()
    assert any((output_dir / "matrices").iterdir())
