from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from agentblaster.campaign import campaign_plan_preview, create_campaign_plan
from agentblaster.cli import app


def test_campaign_plan_generates_multi_suite_matrix_manifest_and_runbook(tmp_path) -> None:
    plan = create_campaign_plan(
        tmp_path,
        providers=["afm", "lm-studio"],
        targets=["qwen3.6-27b-dense", "gemma-4-31b-dense"],
        suites=["smoke", "trace-replay", "lcp-context"],
        policy="agentblaster.policy.yaml",
        name="qwen-gemma-campaign",
    )

    manifest = json.loads(plan.manifest_path.read_text(encoding="utf-8"))
    matrix_text = plan.matrix_path.read_text(encoding="utf-8")
    runbook = plan.runbook_path.read_text(encoding="utf-8")

    assert manifest["schema_version"] == "agentblaster.campaign-plan.v1"
    assert manifest["matrix_run_count"] == 12
    assert manifest["safety"]["contacts_providers"] is False
    assert manifest["safety"]["raw_traces_disabled_in_matrix"] is True
    assert len(manifest["readiness_commands"]) == 12
    assert (plan.report_dir / "readiness").is_dir()
    assert "suite: lcp-context" in matrix_text
    assert "agentblaster matrix scorecard" in runbook
    assert "--offline --continue-on-error" in runbook


def test_campaign_plan_preview_is_no_write_and_executable_as_plan_command(tmp_path) -> None:
    output_dir = tmp_path / "preview-only"

    preview = campaign_plan_preview(
        output_dir=output_dir,
        providers=["afm"],
        targets=["qwen3.6-27b-dense"],
        suites=["smoke"],
        concurrency=2,
    )

    assert preview["schema_version"] == "agentblaster.campaign-preview.v1"
    assert preview["matrix_run_count"] == 1
    assert preview["concurrency"] == 2
    assert preview["safety"]["preview_only"] is True
    assert preview["safety"]["writes_files"] is False
    assert preview["write_command"][:3] == ["agentblaster", "models", "campaign-plan"]
    assert str(output_dir) in preview["write_command"]
    assert not output_dir.exists()


def test_campaign_plan_refuses_to_overwrite_unknown_entries(tmp_path) -> None:
    (tmp_path / "keep.txt").write_text("do not touch", encoding="utf-8")

    with pytest.raises(ValueError, match="non-campaign entries"):
        create_campaign_plan(tmp_path)


def test_cli_campaign_plan_writes_expected_artifacts(tmp_path) -> None:
    output_dir = tmp_path / "campaign"
    result = CliRunner().invoke(
        app,
        [
            "models",
            "campaign-plan",
            "--output-dir",
            str(output_dir),
            "--providers",
            "afm",
            "--targets",
            "qwen3.6-27b-dense",
            "--suites",
            "smoke,lcp-context",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "manifest:" in result.output
    assert (output_dir / "campaign-plan.json").exists()
    assert (output_dir / "RUNBOOK.md").exists()
    assert any((output_dir / "matrices").iterdir())
