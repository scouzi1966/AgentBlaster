from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agentblaster.campaign import campaign_plan_preview, create_campaign_plan
from agentblaster.cli import app


def test_default_campaign_suites_cover_core_local_agentic_stress_axes(tmp_path) -> None:
    preview = campaign_plan_preview(output_dir=tmp_path / "preview")

    assert {
        "smoke",
        "structured",
        "toolcall",
        "toolsim",
        "trace-replay",
        "agentic-tool-loop",
        "agent-fanout",
        "prefill",
        "cache-control",
        "cancellation",
        "lcp-context",
    }.issubset(set(preview["suites"]))
    assert "agentic-tool-loop" in preview["write_command"][preview["write_command"].index("--suites") + 1]
    assert "agent-fanout" in preview["write_command"][preview["write_command"].index("--suites") + 1]
    assert "cancellation" in preview["write_command"][preview["write_command"].index("--suites") + 1]


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
    assert manifest["readiness_commands"][0]["output"].endswith("-readiness.json")
    assert len(manifest["publication_artifacts"]["benchmark_readiness_reports"]) == 12
    readiness_inputs = plan.report_dir / "benchmark-readiness-inputs.txt"
    assert manifest["readiness_input_list_path"] == str(readiness_inputs)
    assert readiness_inputs.read_text(encoding="utf-8").splitlines() == [
        Path(path).relative_to(plan.report_dir).as_posix()
        for path in manifest["publication_artifacts"]["benchmark_readiness_reports"]
    ]
    assert (plan.report_dir / "readiness").is_dir()
    assert "suite: lcp-context" in matrix_text
    assert "agentblaster matrix scorecard" in runbook
    assert "--format html,md,json,card,png,pdf" in runbook
    assert "agentblaster matrix publication-bundle" in runbook
    assert "agentblaster matrix contract-checks" in runbook
    assert "provider_contract_matrix" in manifest["publication_artifacts"]
    assert manifest["publication_artifacts"]["provider_audit"] == str(plan.report_dir / "provider-audit.json")
    assert "matrix_publication_bundle" in manifest["publication_artifacts"]
    assert "matrix_scorecard_json" in manifest["publication_artifacts"]
    assert "matrix_scorecard_png" in manifest["publication_artifacts"]
    assert "matrix_pressure_audit" in manifest["publication_artifacts"]
    assert "matrix_saturation_report" in manifest["publication_artifacts"]
    assert manifest["publication_artifacts"]["implementation_status"] == str(
        plan.report_dir / "implementation-status.json"
    )
    assert "evidence_index" in manifest["publication_artifacts"]
    assert manifest["publication_artifacts"]["selftest_report"] == str(
        plan.report_dir / "selftest" / "qwen-gemma-campaign-selftest" / "selftest-report.json"
    )
    assert manifest["publication_artifacts"]["sdlc_validation_manifest"] == str(
        plan.report_dir / "sdlc-validation-manifest.json"
    )
    assert manifest["publication_artifacts"]["retention_cleanup_plan"] == str(
        plan.report_dir / "qwen-gemma-campaign-retention-cleanup-plan.json"
    )
    assert manifest["publication_artifacts"]["manual_cleanup_plan_template"] == str(
        plan.report_dir / "qwen-gemma-campaign-manual-cleanup-plan.json"
    )
    assert "experiment_manifest" in manifest["publication_artifacts"]
    assert "experiment_gate" in manifest["publication_artifacts"]
    assert manifest["publication_artifacts"]["metric_coverage_reports"] == [
        str(plan.report_dir / "afm-metric-coverage.json"),
        str(plan.report_dir / "lm-studio-metric-coverage.json"),
    ]
    assert manifest["publication_artifacts"]["engine_advisories"] == [
        str(plan.report_dir / "afm-improvement-plan.json"),
        str(plan.report_dir / "lm-studio-improvement-plan.json"),
    ]
    assert manifest["publication_artifacts"]["suite_audits"] == [
        str(plan.report_dir / "smoke-suite-audit.json"),
        str(plan.report_dir / "trace-replay-suite-audit.json"),
        str(plan.report_dir / "lcp-context-suite-audit.json"),
    ]
    assert manifest["publication_artifacts"]["harness_reviews"] == [
        str(plan.report_dir / "smoke-harness-review.json"),
        str(plan.report_dir / "trace-replay-harness-review.json"),
        str(plan.report_dir / "lcp-context-harness-review.json"),
    ]
    assert manifest["publication_artifacts"]["suite_calibration_templates"] == [
        str(plan.report_dir / "smoke-calibration.json"),
        str(plan.report_dir / "trace-replay-calibration.json"),
        str(plan.report_dir / "lcp-context-calibration.json"),
    ]
    assert manifest["publication_artifacts"]["suite_calibration_reports"] == [
        str(plan.report_dir / "smoke-calibration-report.json"),
        str(plan.report_dir / "trace-replay-calibration-report.json"),
        str(plan.report_dir / "lcp-context-calibration-report.json"),
    ]
    assert "release_qualification_bundle" in manifest["publication_artifacts"]
    assert "claim_readiness" in manifest["publication_artifacts"]
    assert manifest["publication_artifacts"]["publication_brief_json"] == str(
        plan.report_dir / "qwen-gemma-campaign-publication-brief.json"
    )
    assert manifest["publication_artifacts"]["publication_brief_md"] == str(
        plan.report_dir / "qwen-gemma-campaign-publication-brief.md"
    )
    assert manifest["publication_artifacts"]["publication_archive_bundle"] == str(
        plan.report_dir / "release-bundles" / "qwen-gemma-campaign-publication.agentblaster-release-qualification.zip"
    )
    assert "benchmark_readiness_reports" in manifest["publication_artifacts"]
    assert manifest["publication_artifacts"]["benchmark_readiness_input_list"] == str(readiness_inputs)
    assert manifest["publication_artifacts"]["campaign_preflight_manifest"] == str(
        plan.report_dir / "campaign-preflight" / "manifest.json"
    )
    assert manifest["campaign_preflight_command"] == [
        "agentblaster",
        "evidence",
        "campaign-preflight",
        "--matrix",
        str(plan.matrix_path),
        "--policy",
        "agentblaster.policy.yaml",
        "--benchmark-readiness-list",
        str(readiness_inputs),
        "--output-dir",
        str(plan.report_dir / "campaign-preflight"),
    ]
    assert "contract_execute" in manifest["matrix_commands"]
    assert manifest["publication_commands"]["experiment_manifest"] == [
        "agentblaster",
        "experiment",
        "manifest",
        "--name",
        "qwen-gemma-campaign",
        "--objective",
        "Compare afm, lm-studio across qwen3.6-27b-dense, gemma-4-31b-dense on smoke, trace-replay, lcp-context.",
        "--providers",
        "afm,lm-studio",
        "--targets",
        "qwen3.6-27b-dense,gemma-4-31b-dense",
        "--suites",
        "smoke,trace-replay,lcp-context",
        "--policy",
        "agentblaster.policy.yaml",
        "--matrix",
        str(plan.matrix_path),
        "--output",
        str(plan.report_dir / "qwen-gemma-campaign-experiment.json"),
    ]
    assert manifest["publication_commands"]["experiment_gate"] == [
        "agentblaster",
        "experiment",
        "gate",
        str(plan.report_dir / "qwen-gemma-campaign-experiment.json"),
        "--require-policy",
        "--output-json",
        str(plan.report_dir / "qwen-gemma-campaign-experiment-gate.json"),
    ]
    assert manifest["publication_commands"]["matrix_pressure_audit"] == [
        "agentblaster",
        "matrix",
        "pressure-audit",
        str(plan.matrix_path),
        "--output-json",
        str(plan.report_dir / "qwen-gemma-campaign-matrix-pressure.json"),
    ]
    assert manifest["publication_commands"]["matrix_saturation_report"] == [
        "agentblaster",
        "matrix",
        "saturation-report",
        str(plan.report_dir / "qwen-gemma-campaign-matrix-summary.json"),
        "--output-json",
        str(plan.report_dir / "qwen-gemma-campaign-matrix-saturation.json"),
    ]
    assert manifest["publication_commands"]["metric_coverage"][0] == [
        "agentblaster",
        "providers",
        "metric-coverage",
        "--provider",
        "afm",
        "--output-json",
        str(plan.report_dir / "afm-metric-coverage.json"),
    ]
    assert manifest["publication_commands"]["selftest"] == [
        "agentblaster",
        "selftest",
        "--tier",
        "normal",
        "--report-dir",
        str(plan.report_dir / "selftest"),
        "--run-id",
        "qwen-gemma-campaign-selftest",
    ]
    assert manifest["publication_commands"]["selftest_report"] == [
        "agentblaster",
        "selftest",
        "report",
        "--run",
        "qwen-gemma-campaign-selftest",
        "--base-dir",
        str(plan.report_dir / "selftest"),
        "--format",
        "html,json,junit",
    ]
    assert manifest["publication_commands"]["sdlc_validation_manifest"] == [
        "agentblaster",
        "quality",
        "validation-manifest",
        "--format",
        "json",
        "--output",
        str(plan.report_dir / "sdlc-validation-manifest.json"),
        "--name",
        "qwen-gemma-campaign",
    ]
    assert manifest["publication_commands"]["retention_cleanup_plan"] == [
        "agentblaster",
        "cleanup-expired",
        "--runs",
        "runs",
        "--policy",
        "agentblaster.policy.yaml",
        "--output-json",
        str(plan.report_dir / "qwen-gemma-campaign-retention-cleanup-plan.json"),
        "--audit-log",
        str(plan.report_dir / "qwen-gemma-campaign-cleanup-audit.jsonl"),
        "--require-audit-log",
    ]
    assert manifest["publication_commands"]["manual_cleanup_plan_template"] == [
        "agentblaster",
        "cleanup",
        "runs/<run-id>",
        "--raw",
        "--reports",
        "--exports",
        "--caches",
        "--temp",
        "--bundles",
        "--policy",
        "agentblaster.policy.yaml",
        "--output-json",
        str(plan.report_dir / "qwen-gemma-campaign-manual-cleanup-plan.json"),
        "--audit-log",
        str(plan.report_dir / "qwen-gemma-campaign-cleanup-audit.jsonl"),
        "--require-audit-log",
    ]
    assert manifest["publication_commands"]["suite_audits"] == [
        [
            "agentblaster",
            "suite-audit",
            "--suite",
            "smoke",
            "--output-json",
            str(plan.report_dir / "smoke-suite-audit.json"),
        ],
        [
            "agentblaster",
            "suite-audit",
            "--suite",
            "trace-replay",
            "--output-json",
            str(plan.report_dir / "trace-replay-suite-audit.json"),
        ],
        [
            "agentblaster",
            "suite-audit",
            "--suite",
            "lcp-context",
            "--output-json",
            str(plan.report_dir / "lcp-context-suite-audit.json"),
        ],
    ]
    assert manifest["publication_commands"]["harness_reviews"] == [
        [
            "agentblaster",
            "harness",
            "review",
            "--suite",
            "smoke",
            "--output-json",
            str(plan.report_dir / "smoke-harness-review.json"),
        ],
        [
            "agentblaster",
            "harness",
            "review",
            "--suite",
            "trace-replay",
            "--output-json",
            str(plan.report_dir / "trace-replay-harness-review.json"),
        ],
        [
            "agentblaster",
            "harness",
            "review",
            "--suite",
            "lcp-context",
            "--output-json",
            str(plan.report_dir / "lcp-context-harness-review.json"),
        ],
    ]
    assert manifest["publication_commands"]["suite_calibration_templates"][0] == [
        "agentblaster",
        "suite-calibration",
        "--suite",
        "smoke",
        "--template-output",
        str(plan.report_dir / "smoke-calibration.json"),
    ]
    assert manifest["publication_commands"]["suite_calibration_reports"][0] == [
        "agentblaster",
        "suite-calibration",
        "--suite",
        "smoke",
        "--calibration",
        str(plan.report_dir / "smoke-calibration.json"),
        "--output-json",
        str(plan.report_dir / "smoke-calibration-report.json"),
    ]
    assert manifest["publication_commands"]["engine_advisories"][0] == [
        "agentblaster",
        "engines",
        "improvement-plan",
        "--engine",
        "afm",
        "--pressure-audit",
        str(plan.report_dir / "qwen-gemma-campaign-matrix-pressure.json"),
        "--matrix-saturation-report",
        str(plan.report_dir / "qwen-gemma-campaign-matrix-saturation.json"),
        "--provider-contract-matrix",
        str(plan.report_dir / "qwen-gemma-campaign-provider-contract-matrix.json"),
        "--matrix-gate",
        str(plan.report_dir / "qwen-gemma-campaign-matrix-gate.json"),
        "--harness-review",
        str(plan.report_dir / "smoke-harness-review.json"),
        "--harness-review",
        str(plan.report_dir / "trace-replay-harness-review.json"),
        "--harness-review",
        str(plan.report_dir / "lcp-context-harness-review.json"),
        "--metric-coverage",
        str(plan.report_dir / "afm-metric-coverage.json"),
        "--metric-coverage",
        str(plan.report_dir / "lm-studio-metric-coverage.json"),
        "--output-json",
        str(plan.report_dir / "afm-improvement-plan.json"),
    ]
    assert manifest["publication_commands"]["evidence_index"] == [
        "agentblaster",
        "evidence",
        "index",
        "--name",
        "qwen-gemma-campaign",
        "--artifact",
        str(plan.report_dir / "qwen-gemma-campaign-experiment-gate.json"),
        "--artifact",
        str(plan.report_dir / "provider-audit.json"),
        "--artifact",
        str(plan.report_dir / "qwen-gemma-campaign-provider-contract-matrix.json"),
        "--artifact",
        str(plan.report_dir / "qwen-gemma-campaign-matrix-gate.json"),
        "--artifact",
        str(plan.report_dir / "qwen-gemma-campaign-matrix-summary-matrix-scorecard.json"),
        "--artifact",
        str(plan.report_dir / "qwen-gemma-campaign-matrix-pressure.json"),
        "--artifact",
        str(plan.report_dir / "qwen-gemma-campaign-matrix-saturation.json"),
        "--artifact",
        str(plan.report_dir / "campaign-preflight" / "manifest.json"),
        "--artifact",
        str(plan.report_dir / "campaign-preflight" / "readiness" / "benchmark-readiness-index.json"),
        "--artifact",
        str(plan.report_dir / "release-provenance.json"),
        "--artifact",
        str(plan.report_dir / "qwen-gemma-campaign-retention-cleanup-plan.json"),
        "--artifact",
        str(plan.report_dir / "selftest" / "qwen-gemma-campaign-selftest" / "selftest-report.json"),
        "--artifact",
        str(plan.report_dir / "sdlc-validation-manifest.json"),
        "--artifact",
        str(plan.report_dir / "smoke-suite-audit.json"),
        "--artifact",
        str(plan.report_dir / "trace-replay-suite-audit.json"),
        "--artifact",
        str(plan.report_dir / "lcp-context-suite-audit.json"),
        "--artifact",
        str(plan.report_dir / "smoke-harness-review.json"),
        "--artifact",
        str(plan.report_dir / "trace-replay-harness-review.json"),
        "--artifact",
        str(plan.report_dir / "lcp-context-harness-review.json"),
        "--artifact",
        str(plan.report_dir / "smoke-calibration-report.json"),
        "--artifact",
        str(plan.report_dir / "trace-replay-calibration-report.json"),
        "--artifact",
        str(plan.report_dir / "lcp-context-calibration-report.json"),
        "--artifact",
        str(plan.report_dir / "afm-metric-coverage.json"),
        "--artifact",
        str(plan.report_dir / "lm-studio-metric-coverage.json"),
        "--artifact",
        str(plan.report_dir / "afm-improvement-plan.json"),
        "--artifact",
        str(plan.report_dir / "lm-studio-improvement-plan.json"),
        "--output-json",
        str(plan.report_dir / "qwen-gemma-campaign-evidence-index.json"),
    ]
    assert manifest["publication_commands"]["qualification_bundle"] == [
        "agentblaster",
        "release",
        "qualification-bundle",
        "--name",
        "qwen-gemma-campaign",
        "--provider-audit",
        str(plan.report_dir / "provider-audit.json"),
        "--provider-contract-matrix",
        str(plan.report_dir / "qwen-gemma-campaign-provider-contract-matrix.json"),
        "--matrix-gate",
        str(plan.report_dir / "qwen-gemma-campaign-matrix-gate.json"),
        "--matrix-scorecard",
        str(plan.report_dir / "qwen-gemma-campaign-matrix-summary-matrix-scorecard.json"),
        "--matrix-pressure-audit",
        str(plan.report_dir / "qwen-gemma-campaign-matrix-pressure.json"),
        "--matrix-saturation-report",
        str(plan.report_dir / "qwen-gemma-campaign-matrix-saturation.json"),
        "--implementation-status",
        str(plan.report_dir / "implementation-status.json"),
        "--campaign-preflight-manifest",
        str(plan.report_dir / "campaign-preflight" / "manifest.json"),
        "--benchmark-readiness-list",
        str(readiness_inputs),
        "--release-provenance",
        str(plan.report_dir / "release-provenance.json"),
        "--evidence-index",
        str(plan.report_dir / "qwen-gemma-campaign-evidence-index.json"),
        "--suite-audit",
        str(plan.report_dir / "smoke-suite-audit.json"),
        "--suite-audit",
        str(plan.report_dir / "trace-replay-suite-audit.json"),
        "--suite-audit",
        str(plan.report_dir / "lcp-context-suite-audit.json"),
        "--harness-review",
        str(plan.report_dir / "smoke-harness-review.json"),
        "--harness-review",
        str(plan.report_dir / "trace-replay-harness-review.json"),
        "--harness-review",
        str(plan.report_dir / "lcp-context-harness-review.json"),
        "--suite-calibration-report",
        str(plan.report_dir / "smoke-calibration-report.json"),
        "--suite-calibration-report",
        str(plan.report_dir / "trace-replay-calibration-report.json"),
        "--suite-calibration-report",
        str(plan.report_dir / "lcp-context-calibration-report.json"),
        "--metric-coverage",
        str(plan.report_dir / "afm-metric-coverage.json"),
        "--metric-coverage",
        str(plan.report_dir / "lm-studio-metric-coverage.json"),
        "--engine-advisory",
        str(plan.report_dir / "afm-improvement-plan.json"),
        "--engine-advisory",
        str(plan.report_dir / "lm-studio-improvement-plan.json"),
        "--selftest-report",
        str(plan.report_dir / "selftest" / "qwen-gemma-campaign-selftest" / "selftest-report.json"),
        "--sdlc-validation-manifest",
        str(plan.report_dir / "sdlc-validation-manifest.json"),
        "--matrix-publication-bundle",
        str(plan.report_dir / "publication-bundles" / "qwen-gemma-campaign-matrix-summary.agentblaster-matrix-publication.zip"),
        "--output-dir",
        str(plan.report_dir / "release-bundles"),
    ]
    assert manifest["publication_commands"]["claim_readiness"][-2:] == [
        "--output-json",
        str(plan.report_dir / "qwen-gemma-campaign-claim-readiness.json"),
    ]
    assert "--experiment-manifest" in manifest["publication_commands"]["claim_readiness"]
    assert "--experiment-gate" in manifest["publication_commands"]["claim_readiness"]
    assert "--provider-audit" in manifest["publication_commands"]["claim_readiness"]
    assert str(plan.report_dir / "provider-audit.json") in manifest["publication_commands"]["claim_readiness"]
    assert "--matrix-pressure-audit" in manifest["publication_commands"]["claim_readiness"]
    assert "--matrix-saturation-report" in manifest["publication_commands"]["claim_readiness"]
    assert "--implementation-status" in manifest["publication_commands"]["claim_readiness"]
    assert "--evidence-index" in manifest["publication_commands"]["claim_readiness"]
    assert "--suite-audit" in manifest["publication_commands"]["claim_readiness"]
    assert "--harness-review" in manifest["publication_commands"]["claim_readiness"]
    assert "--suite-calibration-report" in manifest["publication_commands"]["claim_readiness"]
    assert "--metric-coverage" in manifest["publication_commands"]["claim_readiness"]
    assert "--engine-advisory" in manifest["publication_commands"]["claim_readiness"]
    assert "--selftest-report" in manifest["publication_commands"]["claim_readiness"]
    assert manifest["publication_commands"]["publication_brief"] == [
        "agentblaster",
        "release",
        "publication-brief",
        "--name",
        "qwen-gemma-campaign",
        "--claim-readiness",
        str(plan.report_dir / "qwen-gemma-campaign-claim-readiness.json"),
        "--matrix-scorecard",
        str(plan.report_dir / "qwen-gemma-campaign-matrix-summary-matrix-scorecard.json"),
        "--release-provenance",
        str(plan.report_dir / "release-provenance.json"),
        "--evidence-index",
        str(plan.report_dir / "qwen-gemma-campaign-evidence-index.json"),
        "--output-json",
        str(plan.report_dir / "qwen-gemma-campaign-publication-brief.json"),
        "--output-md",
        str(plan.report_dir / "qwen-gemma-campaign-publication-brief.md"),
    ]
    archive_command = manifest["publication_commands"]["publication_archive_bundle"]
    assert archive_command[:5] == [
        "agentblaster",
        "release",
        "qualification-bundle",
        "--name",
        "qwen-gemma-campaign-publication",
    ]
    assert "--claim-readiness" in archive_command
    assert str(plan.report_dir / "qwen-gemma-campaign-claim-readiness.json") in archive_command
    assert "--provider-audit" in archive_command
    assert str(plan.report_dir / "provider-audit.json") in archive_command
    assert "--publication-brief" in archive_command
    assert str(plan.report_dir / "qwen-gemma-campaign-publication-brief.json") in archive_command
    assert "--sdlc-validation-manifest" in archive_command
    assert str(plan.report_dir / "sdlc-validation-manifest.json") in archive_command
    assert "publication_bundle" in manifest["matrix_commands"]
    assert "max_tool_calls_reached=0" in " ".join(manifest["matrix_commands"]["gate"])
    assert "--max-tool-loop-stop-reason max_tool_calls_reached=0" in runbook
    assert "publication_artifacts.implementation_status" in runbook
    assert "publication_artifacts.provider_audit" in runbook
    assert "publication_artifacts.benchmark_readiness_reports" in runbook
    assert "publication_artifacts.benchmark_readiness_input_list" in runbook
    assert "--benchmark-readiness-list" in runbook
    assert "benchmark-readiness-inputs.txt" in runbook
    assert "publication_artifacts.campaign_preflight_manifest" in runbook
    assert "agentblaster evidence campaign-preflight" in runbook
    assert "Publication evidence skeleton" in runbook
    assert "agentblaster experiment manifest" in runbook
    assert "agentblaster experiment gate" in runbook
    assert "agentblaster matrix pressure-audit" in runbook
    assert "agentblaster matrix saturation-report" in runbook
    assert "agentblaster providers metric-coverage" in runbook
    assert "agentblaster suite-audit" in runbook
    assert "agentblaster harness review" in runbook
    assert "agentblaster suite-calibration" in runbook
    assert "Failed calibration reports block release-gate qualification" in runbook
    assert "agentblaster selftest --tier normal" in runbook
    assert "agentblaster selftest report" in runbook
    assert "agentblaster quality validation-manifest" in runbook
    assert "agentblaster cleanup-expired --runs runs" in runbook
    assert "--require-audit-log" in runbook
    assert "runs/<run-id>" in runbook
    assert "lifecycle cleanup evidence" in runbook
    assert "agentblaster engines improvement-plan" in runbook
    assert "agentblaster evidence index" in runbook
    assert "agentblaster release qualification-bundle" in runbook
    assert "agentblaster release claim-readiness" in runbook
    assert "agentblaster release publication-brief" in runbook
    assert "final archival release bundle" in runbook
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


def test_campaign_plan_omits_experiment_policy_gate_when_policy_is_not_configured(tmp_path) -> None:
    plan = create_campaign_plan(
        tmp_path,
        providers=["afm"],
        targets=["qwen3.6-27b-dense"],
        suites=["smoke"],
        name="no-policy-campaign",
    )

    manifest = json.loads(plan.manifest_path.read_text(encoding="utf-8"))

    assert "--policy" not in manifest["publication_commands"]["experiment_manifest"]
    assert "--require-policy" not in manifest["publication_commands"]["experiment_gate"]
    assert "--no-require-policy" not in manifest["publication_commands"]["experiment_gate"]


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
