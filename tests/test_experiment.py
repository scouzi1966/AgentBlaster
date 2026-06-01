from __future__ import annotations

import json

from typer.testing import CliRunner

from agentblaster.cli import app
from agentblaster.experiment import build_experiment_manifest, evaluate_experiment_manifest


def test_experiment_manifest_records_scope_gates_and_publication_rules() -> None:
    manifest = build_experiment_manifest(
        name="qwen-gemma-local",
        objective="Compare local AFM and LM Studio behavior for Qwen/Gemma agentic suites.",
        providers=["afm", "lm-studio"],
        targets=["qwen3.6-27b-dense", "gemma-4-31b-dense"],
        suites=["trace-replay", "prefill"],
        min_case_pass_rate=97.5,
    )

    assert manifest["schema_version"] == "agentblaster.experiment-manifest.v1"
    assert manifest["security"]["contacts_providers"] is False
    assert manifest["acceptance_gates"]["min_case_pass_rate"] == 97.5
    assert manifest["publication_rules"]["cite_metric_coverage"] is True
    assert len(manifest["suggested_artifacts"]["readiness_dossiers"]) == 8


def test_experiment_gate_flags_missing_policy_when_required() -> None:
    manifest = build_experiment_manifest(
        name="local",
        objective="Compare local benchmark readiness before running.",
        providers=["afm"],
        targets=["qwen3.6-27b-dense"],
        suites=["smoke"],
    )

    report = evaluate_experiment_manifest(manifest, require_policy=True)

    assert report["passed"] is False
    assert {finding["code"] for finding in report["findings"]} == {"missing_policy"}


def test_cli_experiment_manifest_and_gate(tmp_path) -> None:
    runner = CliRunner()
    manifest_path = tmp_path / "experiment.json"
    gate_path = tmp_path / "experiment-gate.json"

    manifest_result = runner.invoke(
        app,
        [
            "experiment",
            "manifest",
            "--name",
            "qwen-gemma-local",
            "--objective",
            "Compare local provider behavior for Qwen and Gemma agentic runs.",
            "--providers",
            "afm,lm-studio",
            "--targets",
            "qwen3.6-27b-dense,gemma-4-31b-dense",
            "--suites",
            "trace-replay,prefill",
            "--policy",
            "agentblaster.policy.yaml",
            "--output",
            str(manifest_path),
        ],
    )
    gate_result = runner.invoke(
        app,
        ["experiment", "gate", str(manifest_path), "--require-policy", "--output-json", str(gate_path)],
    )

    assert manifest_result.exit_code == 0, manifest_result.output
    assert manifest_path.exists()
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["name"] == "qwen-gemma-local"
    assert gate_result.exit_code == 0, gate_result.output
    assert "passed: true" in gate_result.output
    assert gate_path.exists()
