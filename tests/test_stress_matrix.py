from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from agentblaster.cli import app
from agentblaster.errors import ConfigError
from agentblaster.stress_matrix import generate_stress_matrix, stress_matrix_summary, stress_matrix_to_yaml


def test_generate_stress_matrix_crosses_providers_targets_suites_and_concurrency() -> None:
    matrix = generate_stress_matrix(
        providers=["afm", "lm-studio"],
        target_ids=["qwen3.6-27b-dense", "gemma-4-31b-dense"],
        suites=["prefill", "trace-replay"],
        concurrency_levels=[1, 4],
    )

    assert matrix.name == "stress-afm-lm-studio-qwen3.6-27b-dense-gemma-4-31b-dense-prefill-trace-replay-c1-4"
    assert len(matrix.runs) == 16
    assert {run.concurrency for run in matrix.runs} == {1, 4}
    assert {run.suite for run in matrix.runs} == {"prefill", "trace-replay"}
    assert all(run.no_raw_traces is True for run in matrix.runs)
    assert any(run.model_metadata.architecture == "qwen3.6-dense" for run in matrix.runs)
    assert "tokens" not in stress_matrix_to_yaml(matrix).lower()


def test_generate_stress_matrix_rejects_invalid_concurrency() -> None:
    with pytest.raises(ConfigError, match=">= 1"):
        generate_stress_matrix(
            providers=["afm"],
            target_ids=["qwen3.6-27b-dense"],
            concurrency_levels=[0],
        )


def test_default_stress_matrix_includes_harness_engineering() -> None:
    matrix = generate_stress_matrix(
        providers=["afm"],
        target_ids=["qwen3.6-27b-dense"],
        concurrency_levels=[1],
    )

    assert {run.suite for run in matrix.runs} == {
        "agentic-tool-loop",
        "agent-fanout",
        "prefill",
        "harness-engineering",
        "trace-replay",
    }


def test_stress_matrix_summary_is_redaction_safe() -> None:
    matrix = generate_stress_matrix(
        providers=["afm"],
        target_ids=["qwen3.6-27b-dense"],
        suites=["prefill"],
        concurrency_levels=[1, 2],
    )
    summary = stress_matrix_summary(matrix)

    assert summary["schema_version"] == "agentblaster.stress-matrix-summary.v1"
    assert summary["total_runs"] == 2
    assert summary["raw_traces_disabled"] is True


def test_cli_stress_matrix_writes_yaml_and_summary(tmp_path) -> None:
    runner = CliRunner()
    output = tmp_path / "stress.yaml"
    summary = tmp_path / "stress-summary.json"

    result = runner.invoke(
        app,
        [
            "models",
            "stress-matrix",
            "--providers",
            "afm",
            "--targets",
            "qwen3.6-27b-dense",
            "--suites",
            "prefill",
            "--concurrency-levels",
            "1,2",
            "--output",
            str(output),
            "--summary-json",
            str(summary),
        ],
    )

    assert result.exit_code == 0, result.output
    assert output.exists()
    assert summary.exists()
    assert "concurrency: 2" in output.read_text(encoding="utf-8")
    assert json.loads(summary.read_text(encoding="utf-8"))["total_runs"] == 2
