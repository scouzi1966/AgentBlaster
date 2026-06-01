from __future__ import annotations

import json
import builtins
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zipfile import ZipFile

from typer.testing import CliRunner

from agentblaster.cli import app
from agentblaster.models import ApiContract, RawTraceMode, RetentionPolicy, RunManifest


def test_cli_adds_and_lists_provider(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path))
    runner = CliRunner()
    audit_path = tmp_path / "provider-audit.jsonl"
    ca_bundle = tmp_path / "corp-ca.pem"

    add_result = runner.invoke(
        app,
        [
            "providers",
            "add",
            "--name",
            "openai",
            "--contract",
            "openai",
            "--base-url",
            "https://api.openai.com/v1",
            "--api-key-env",
            "OPENAI_API_KEY",
            "--model-revision",
            "rev-1",
            "--model-architecture",
            "qwen3-dense",
            "--quantization",
            "mlx-f16",
            "--context-length",
            "32768",
            "--metrics-url",
            "https://metrics.example.com/metrics",
            "--ca-bundle",
            str(ca_bundle),
            "--remote",
            "--include-provider-audit",
            "--audit-log",
            str(audit_path),
        ],
    )
    assert add_result.exit_code == 0, add_result.output
    audit_event = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit_event["event"] == "provider_created"
    assert audit_event["provider"] == "openai"
    assert audit_event["api_key_ref"] == "env:OPENAI_API_KEY"
    assert audit_event["tls_verify"] is True
    assert audit_event["ca_bundle"] == str(ca_bundle)
    assert "sk-" not in audit_path.read_text(encoding="utf-8")

    list_result = runner.invoke(app, ["providers", "list"])

    assert list_result.exit_code == 0, list_result.output
    assert "openai\topenai\thttps://api.openai.com/v1" in list_result.output
    assert "secret=env:OPENAI_API_KEY" in list_result.output

    show_result = runner.invoke(app, ["providers", "show", "openai"])
    assert show_result.exit_code == 0, show_result.output
    assert "model_revision: rev-1" in show_result.output
    assert "model_architecture: qwen3-dense" in show_result.output
    assert "quantization: mlx-f16" in show_result.output
    assert "context_length: 32768" in show_result.output
    assert "metrics_url: https://metrics.example.com/metrics" in show_result.output
    assert "tls_verify: true" in show_result.output
    assert f"ca_bundle: {ca_bundle}" in show_result.output


def test_cli_provider_add_accepts_safe_headers_and_native_adapter(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path))
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "providers",
            "add",
            "--name",
            "lm-studio-anthropic",
            "--contract",
            "anthropic",
            "--base-url",
            "http://127.0.0.1:1234/v1",
            "--header",
            "anthropic-version=2023-06-01",
            "--native-adapter",
            "lm-studio",
        ],
    )

    assert result.exit_code == 0, result.output
    show_result = runner.invoke(app, ["providers", "show", "lm-studio-anthropic"])
    assert show_result.exit_code == 0, show_result.output
    assert "contract: anthropic" in show_result.output
    assert "native_adapter: lm-studio" in show_result.output


def test_cli_doctor_reports_static_environment_readiness(tmp_path) -> None:
    runner = CliRunner()
    output = tmp_path / "doctor.json"
    home = tmp_path / "config"

    result = runner.invoke(
        app,
        [
            "doctor",
            "--home",
            str(home),
            "--output-json",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "AgentBlaster environment readiness" in result.output
    assert str(output) in result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "agentblaster.environment-readiness.v1"
    assert payload["config"]["home"] == str(home)
    assert payload["config"]["providers_path"] == str(home / "providers.json")
    assert any(check["id"] == "runtime-dependencies" for check in payload["checks"])


def test_cli_implementation_status_writes_static_inventory(tmp_path) -> None:
    runner = CliRunner()
    output = tmp_path / "implementation-status.json"

    result = runner.invoke(
        app,
        [
            "implementation-status",
            "--project-root",
            ".",
            "--output-json",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "AgentBlaster implementation status" in result.output
    assert str(output) in result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "agentblaster.implementation-status.v1"
    assert payload["validation"]["tests_run_by_this_command"] is False
    assert any(area["id"] == "dashboard" for area in payload["areas"])


def test_cli_catalog_artifact_schemas_writes_registry(tmp_path) -> None:
    runner = CliRunner()
    output = tmp_path / "artifact-schemas.json"

    result = runner.invoke(
        app,
        [
            "catalog",
            "artifact-schemas",
            "--format",
            "json",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert str(output) in result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "agentblaster.artifact-schema-registry.v1"
    assert any(artifact["id"] == "lifecycle-events" for artifact in payload["artifacts"])


def test_cli_evidence_index_writes_compact_review_artifact(tmp_path) -> None:
    runner = CliRunner()
    matrix_gate = tmp_path / "matrix-gate.json"
    advisory = tmp_path / "engine-advisory.json"
    suite_audit = tmp_path / "suite-audit.json"
    metric_coverage = tmp_path / "metric-coverage.json"
    matrix_pressure = tmp_path / "matrix-pressure.json"
    matrix_scorecard = tmp_path / "matrix-scorecard.json"
    contract_matrix = tmp_path / "provider-contract-matrix.json"
    publication_bundle = tmp_path / "run.agentblaster-publication.zip"
    release_bundle = tmp_path / "release.agentblaster-release-qualification.zip"
    output = tmp_path / "evidence-index.json"
    matrix_gate.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.matrix-gate.v1",
                "ok": False,
                "matrix_name": "qwen-gemma",
                "pass_rate_percent": 96.0,
                "failure_class_summary": [{"failure_class": "engine_protocol_bug", "count": 1}],
                "findings": [],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    advisory.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.engine-improvement-advisory.v1",
                "engine": "afm",
                "summary": {"priority_count": 1, "highest_priority": 1, "no_dispatch": True},
                "priorities": [
                    {
                        "priority": 1,
                        "area": "contract-conformance",
                        "reason": "not copied into evidence index",
                        "aligned_artifacts_or_suites": ["providers contract-check"],
                    }
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    suite_audit.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.suite-audit.v1",
                "suite": "agentic-local",
                "total_cases": 4,
                "provenance_counts": {"synthetic_representative": 4},
                "risk_counts": {"medium": 4},
                "dataset_hygiene": {"duplicate_fingerprint_count": 1},
                "findings": [
                    {"severity": "warning", "case_id": "case-a,case-b", "code": "duplicate_case_fingerprint", "message": "not copied"}
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    metric_coverage.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.metric-coverage.v1",
                "provider": {"name": "afm", "contract": "openai", "native_adapter": None},
                "summary": {
                    "field_count": 24,
                    "counts": {"native": 3, "measured": 9, "inferred": 1, "conditional": 2, "unavailable": 9},
                    "coverage_score": 0.55,
                },
                "comparability": {
                    "publication_grade_group_count": 1,
                    "advisory_group_count": 1,
                    "partial_group_count": 2,
                    "unavailable_group_count": 0,
                    "publication_grade_groups": ["agent_protocol_behavior"],
                    "review_required_groups": ["timing_and_throughput", "token_and_cache_accounting"],
                },
                "fields": [],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    matrix_pressure.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.matrix-pressure-audit.v1",
                "matrix": "qwen-gemma",
                "run_count": 2,
                "engines": ["afm", "lm-studio"],
                "models": ["qwen3.6-27b-dense"],
                "suites": ["prefill", "agentic-tool-loop"],
                "concurrency_levels": [1, 4],
                "totals": {
                    "case_count": 8,
                    "scheduled_prompt_tokens": 12000,
                    "concurrent_window_prompt_tokens": 6000,
                    "prefill_pressure_score": 44,
                    "concurrency_weighted_pressure_score": 176,
                    "shared_static_prefix_groups": 3,
                    "shared_static_prefix_tokens": 9000,
                    "shared_static_reuse_tokens": 6400,
                },
                "highest_pressure_runs": [
                    {
                        "index": 2,
                        "engine": "afm",
                        "model": "qwen3.6-27b-dense",
                        "suite": "prefill",
                        "concurrency": 4,
                        "prefill_pressure_level": "high",
                        "concurrent_window_prompt_tokens": 6000,
                        "concurrency_weighted_pressure_score": 176,
                        "shared_static_reuse_tokens": 6400,
                        "largest_cases": [{"case_id": "not copied"}],
                    }
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    matrix_scorecard.write_text(
        json.dumps(
            {
                "report_type": "agentblaster-matrix-scorecard-v1",
                "matrix": {"name": "qwen-gemma", "completed_runs": 2, "total_runs": 2, "failed_runs": 0},
                "scorecard": {
                    "entry_count": 2,
                    "result_artifacts_loaded": 2,
                    "total_cases": 10,
                    "passed_cases": 10,
                    "failed_cases": 0,
                    "pass_rate_percent": 100.0,
                    "telemetry_quality_summary": {
                        "quality_counts": {"native": 3, "measured": 9, "inferred": 1},
                        "entries_with_advisory_quality": 1,
                    },
                    "concurrency_evidence": {
                        "schema_version": "agentblaster.scorecard-concurrency-evidence.v1",
                        "concurrency_levels": [1, 4],
                        "max_concurrency": 4,
                        "max_avg_queue_ms": 12.0,
                        "guidance": "review-queue-and-rate-limit-pressure-before-publication",
                        "highest_queue_wait_entries": [
                            {
                                "engine": "afm",
                                "provider": "afm",
                                "model": "qwen3.6-27b-dense",
                                "suite": "prefill",
                                "run_id": "afm-c4",
                                "concurrency": 4,
                                "rank_metric": "avg_queue_ms",
                                "rank_value": 12.0,
                                "avg_queue_ms": 12.0,
                            }
                        ],
                    },
                },
                "entries": [{"run_id": "not-copied", "raw_response_path": "raw/not-copied.response.json"}],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    contract_matrix.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.provider-contract-matrix.v1",
                "ok": True,
                "mode": "executed",
                "matrix": {"name": "qwen-gemma", "target_count": 2},
                "summary": {"planned_checks": 10, "passed_checks": 10, "failed_checks": 0, "skipped_checks": 0},
                "capability_evidence": {
                    "directly_checked": ["streaming", "structured_output", "tool_calling"],
                    "proxy_checked_counts": {"judge_rubric": 2},
                    "not_covered_counts": {"prompt_caching": 1},
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    with ZipFile(publication_bundle, "w") as archive:
        archive.writestr(
            "publication-bundle-manifest.json",
            json.dumps(
                {
                    "schema_version": "agentblaster.publication-bundle.v1",
                    "run_id": "run-review",
                    "artifact_count": 4,
                    "artifacts": ["summary.json", "publication.json", "report-card.svg", "integrity.json"],
                    "media_kit": {
                        "schema_version": "agentblaster.media-kit.v1",
                        "asset_count": 4,
                        "missing_recommended_assets": [],
                        "recommended_sets": [{"name": "corporate-review-packet", "available": True}],
                        "assets": [
                            {"artifact": "publication.json", "role": "structured-run-evidence", "media_type": "application/json", "present": True},
                            {"artifact": "report-card.svg", "role": "social-card-vector", "media_type": "image/svg+xml", "present": True},
                        ],
                    },
                    "publication_readiness": {
                        "schema_version": "agentblaster.publication-readiness.v1",
                        "status": "review-required",
                        "ready_for_external_publication": False,
                        "ready_for_internal_review": True,
                        "blocker_count": 0,
                        "warning_count": 1,
                    },
                    "security": {
                        "contains_raw_secrets": False,
                        "contains_raw_provider_payloads": False,
                        "contains_results_jsonl": False,
                    },
                },
                sort_keys=True,
            )
            + "\n",
        )
    with ZipFile(release_bundle, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "schema": "agentblaster.release-qualification-bundle",
                    "schema_version": 1,
                    "ok": True,
                    "artifact_status": {"review": 2},
                    "artifacts": [
                        {
                            "category": "publication",
                            "archive_path": "publication/run.agentblaster-publication.zip",
                            "status": "review",
                            "review_summary": {
                                "schema_version": "agentblaster.publication-bundle.v1",
                                "run_id": "run-release",
                                "artifact_count": 4,
                                "artifacts": ["summary.json", "publication.json", "report-card.svg", "integrity.json"],
                                "media_kit": {
                                    "schema_version": "agentblaster.media-kit.v1",
                                    "asset_count": 4,
                                    "missing_recommended_assets": [],
                                    "recommended_sets": [{"name": "corporate-review-packet", "available": True}],
                                    "assets": [
                                        {"artifact": "publication.json", "role": "structured-run-evidence", "media_type": "application/json", "present": True},
                                        {"artifact": "report-card.svg", "role": "social-card-vector", "media_type": "image/svg+xml", "present": True},
                                    ],
                                },
                                "publication_readiness": {
                                    "schema_version": "agentblaster.publication-readiness.v1",
                                    "status": "review-required",
                                    "ready_for_external_publication": False,
                                    "ready_for_internal_review": True,
                                    "blocker_count": 0,
                                    "warning_count": 1,
                                },
                                "security": {
                                    "contains_raw_secrets": False,
                                    "contains_raw_provider_payloads": False,
                                    "contains_results_jsonl": False,
                                },
                            },
                        }
                        ,
                        {
                            "category": "audits/provider-contract-matrix",
                            "archive_path": "audits/provider-contract-matrix/provider-contract-matrix.json",
                            "status": "pass",
                            "review_summary": {
                                "schema_version": "agentblaster.provider-contract-matrix.v1",
                                "mode": "executed",
                                "ok": True,
                                "matrix": "qwen-gemma",
                                "target_count": 2,
                                "checks": {"planned_checks": 10, "passed_checks": 10, "failed_checks": 0, "skipped_checks": 0},
                                "capability_evidence": {
                                    "directly_checked": ["streaming", "structured_output", "tool_calling"],
                                    "proxy_checked_counts": {"judge_rubric": 2},
                                    "not_covered_counts": {"prompt_caching": 1},
                                },
                            },
                        },
                        {
                            "category": "audits/matrix-pressure",
                            "archive_path": "audits/matrix-pressure/matrix-pressure.json",
                            "status": "review",
                            "review_summary": {
                                "schema_version": "agentblaster.matrix-pressure-audit.v1",
                                "matrix": "qwen-gemma",
                                "run_count": 2,
                                "case_count": 8,
                                "scheduled_prompt_tokens": 12000,
                                "concurrent_window_prompt_tokens": 6000,
                                "prefill_pressure_score": 44,
                                "concurrency_weighted_pressure_score": 176,
                                "shared_static_prefix_groups": 3,
                                "shared_static_prefix_tokens": 9000,
                                "shared_static_reuse_tokens": 6400,
                                "engines": ["afm", "lm-studio"],
                                "models": ["qwen3.6-27b-dense"],
                                "suites": ["prefill", "agentic-tool-loop"],
                                "concurrency_levels": [1, 4],
                                "highest_pressure_runs": [
                                    {
                                        "index": 2,
                                        "engine": "afm",
                                        "model": "qwen3.6-27b-dense",
                                        "suite": "prefill",
                                        "concurrency": 4,
                                        "prefill_pressure_level": "high",
                                        "concurrent_window_prompt_tokens": 6000,
                                        "concurrency_weighted_pressure_score": 176,
                                        "shared_static_reuse_tokens": 6400,
                                    }
                                ],
                            },
                        },
                        {
                            "category": "reports/matrix-scorecard",
                            "archive_path": "reports/matrix-scorecard/matrix-scorecard.json",
                            "status": "pass",
                            "review_summary": {
                                "schema_version": "agentblaster-matrix-scorecard-v1",
                                "matrix": "qwen-gemma",
                                "completed_runs": 2,
                                "total_runs": 2,
                                "failed_runs": 0,
                                "entry_count": 2,
                                "result_artifacts_loaded": 2,
                                "total_cases": 10,
                                "passed_cases": 10,
                                "failed_cases": 0,
                                "pass_rate_percent": 100.0,
                                "telemetry_quality_summary": {
                                    "quality_counts": {"native": 3, "measured": 9, "inferred": 1},
                                    "entries_with_advisory_quality": 1,
                                },
                                "concurrency_evidence": {
                                    "concurrency_levels": [1, 4],
                                    "max_concurrency": 4,
                                    "max_avg_queue_ms": 12.0,
                                    "guidance": "review-queue-and-rate-limit-pressure-before-publication",
                                },
                            },
                        },
                        {
                            "category": "readiness/campaign-preflight",
                            "archive_path": "readiness/campaign-preflight/campaign-preflight-manifest.json",
                            "status": "review",
                            "review_summary": {
                                "schema_version": "agentblaster.campaign-preflight-bundle.v1",
                                "review_summary_schema_version": "agentblaster.campaign-preflight-review-summary.v1",
                                "matrix_count": 1,
                                "run_count": 2,
                                "total_cases": 8,
                                "includes_provider_audit": False,
                                "includes_benchmark_readiness": True,
                                "benchmark_readiness_report_count": 1,
                                "contains_local_paths": False,
                                "external_publication_safe": True,
                            },
                        },
                    ],
                },
                sort_keys=True,
            )
            + "\n",
        )

    result = runner.invoke(
        app,
        [
            "evidence",
            "index",
            "--name",
            "afm-release",
            "--artifact",
            str(matrix_gate),
            "--artifact",
            str(advisory),
            "--artifact",
            str(suite_audit),
            "--artifact",
            str(metric_coverage),
            "--artifact",
            str(publication_bundle),
            "--artifact",
            str(release_bundle),
            "--artifact",
            str(contract_matrix),
            "--artifact",
            str(matrix_pressure),
            "--artifact",
            str(matrix_scorecard),
            "--output-json",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "AgentBlaster evidence index" in result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "agentblaster.evidence-index.v1"
    assert payload["status_counts"] == {"fail": 1, "pass": 3, "review": 5}
    assert payload["readiness"] == {
        "ready": False,
        "state": "blocked",
        "blocking_artifact_count": 1,
        "review_artifact_count": 5,
        "blocking_statuses": ["fail"],
        "review_statuses": ["review"],
        "guidance": "Resolve failing or unreadable evidence artifacts before publication or release qualification.",
    }
    assert payload["artifacts"][0]["review_summary"]["failure_class_summary"] == [
        {"failure_class": "engine_protocol_bug", "count": 1}
    ]
    assert payload["artifacts"][1]["review_summary"]["top_priorities"][0]["area"] == "contract-conformance"
    assert payload["artifacts"][2]["review_summary"]["suite"] == "agentic-local"
    assert payload["artifacts"][2]["review_summary"]["duplicate_fingerprint_count"] == 1
    assert payload["artifacts"][3]["review_summary"]["provider"] == "afm"
    assert payload["artifacts"][3]["review_summary"]["review_required_groups"] == [
        "timing_and_throughput",
        "token_and_cache_accounting",
    ]
    assert payload["artifacts"][4]["schema"] == "agentblaster.publication-bundle.v1"
    assert payload["artifacts"][4]["status"] == "review"
    assert payload["artifacts"][4]["status_source"] == "publication-manifest.publication_readiness.status"
    assert payload["artifacts"][4]["review_summary"]["run_id"] == "run-review"
    assert payload["artifacts"][4]["review_summary"]["publication_readiness"]["status"] == "review-required"
    assert payload["artifacts"][4]["review_summary"]["security"]["contains_results_jsonl"] is False
    assert payload["artifacts"][5]["schema"] == "agentblaster.release-qualification-bundle"
    assert payload["artifacts"][5]["status"] == "pass"
    assert payload["artifacts"][5]["review_summaries"][0]["category"] == "publication"
    assert payload["artifacts"][5]["review_summaries"][0]["run_id"] == "run-release"
    assert payload["artifacts"][5]["review_summaries"][0]["publication_readiness"]["status"] == "review-required"
    assert payload["artifacts"][5]["review_summaries"][0]["security"]["contains_results_jsonl"] is False
    assert payload["artifacts"][5]["review_summaries"][1]["category"] == "audits/provider-contract-matrix"
    assert payload["artifacts"][5]["review_summaries"][1]["capability_evidence"]["not_covered_counts"] == {
        "prompt_caching": 1
    }
    assert payload["artifacts"][5]["review_summaries"][2]["category"] == "audits/matrix-pressure"
    assert payload["artifacts"][5]["review_summaries"][2]["shared_static_reuse_tokens"] == 6400
    assert payload["artifacts"][5]["review_summaries"][3]["category"] == "reports/matrix-scorecard"
    assert payload["artifacts"][5]["review_summaries"][3]["telemetry_quality_summary"]["quality_counts"] == {
        "inferred": 1,
        "measured": 9,
        "native": 3,
    }
    assert payload["artifacts"][5]["review_summaries"][4]["category"] == "readiness/campaign-preflight"
    assert payload["artifacts"][5]["review_summaries"][4]["matrix_count"] == 1
    assert payload["artifacts"][5]["review_summaries"][4]["contains_local_paths"] is False
    assert payload["artifacts"][5]["review_summaries"][4]["external_publication_safe"] is True
    assert payload["artifacts"][6]["schema"] == "agentblaster.provider-contract-matrix.v1"
    assert payload["artifacts"][6]["review_summary"]["capability_evidence"]["proxy_checked_counts"] == {
        "judge_rubric": 2
    }
    assert payload["artifacts"][7]["schema"] == "agentblaster.matrix-pressure-audit.v1"
    assert payload["artifacts"][7]["review_summary"]["shared_static_reuse_tokens"] == 6400
    assert "largest_cases" not in json.dumps(payload["artifacts"][7]["review_summary"])
    assert payload["artifacts"][8]["schema"] == "agentblaster-matrix-scorecard-v1"
    assert payload["artifacts"][8]["review_summary"]["concurrency_evidence"]["concurrency_levels"] == [1, 4]
    assert "raw_response_path" not in json.dumps(payload["artifacts"][8]["review_summary"])
    assert "not copied into evidence index" not in json.dumps(payload)


def test_cli_adds_provider_from_preset(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path))
    runner = CliRunner()

    presets_result = runner.invoke(app, ["providers", "presets"])
    assert presets_result.exit_code == 0, presets_result.output
    assert "afm\topenai\thttp://127.0.0.1:9999/v1" in presets_result.output
    assert "openai\topenai\thttps://api.openai.com/v1\tremote=true\tsecret=env:OPENAI_API_KEY" in presets_result.output
    assert "anthropic\tanthropic\thttps://api.anthropic.com/v1\tremote=true\tsecret=env:ANTHROPIC_API_KEY" in presets_result.output

    add_result = runner.invoke(app, ["providers", "add-preset", "--preset", "afm"])
    assert add_result.exit_code == 0, add_result.output

    list_result = runner.invoke(app, ["providers", "list"])
    assert list_result.exit_code == 0, list_result.output
    assert "afm\topenai\thttp://127.0.0.1:9999/v1" in list_result.output


def test_cli_engines_onboarding_writes_static_artifact(tmp_path) -> None:
    runner = CliRunner()
    output = tmp_path / "local-engine-onboarding.json"

    result = runner.invoke(
        app,
        [
            "engines",
            "onboarding",
            "--engines",
            "afm,lm-studio",
            "--model",
            "model-test",
            "--format",
            "json",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert str(output) in result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "agentblaster.local-engine-onboarding.v1"
    assert payload["engine_count"] == 2
    assert {entry["engine"] for entry in payload["engines"]} == {"afm", "lm-studio"}


def test_cli_adds_remote_cloud_provider_from_preset_with_env_ref(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path))
    runner = CliRunner()

    add_result = runner.invoke(app, ["providers", "add-preset", "--preset", "anthropic"])
    assert add_result.exit_code == 0, add_result.output

    show_result = runner.invoke(app, ["providers", "show", "anthropic"])

    assert show_result.exit_code == 0, show_result.output
    assert "contract: anthropic" in show_result.output
    assert "base_url: https://api.anthropic.com/v1" in show_result.output
    assert "remote: true" in show_result.output
    assert "api_key_ref: env:ANTHROPIC_API_KEY" in show_result.output


def test_cli_adds_remote_cloud_provider_from_preset_with_env_override(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path))
    runner = CliRunner()

    add_result = runner.invoke(
        app,
        [
            "providers",
            "add-preset",
            "--preset",
            "openai",
            "--name",
            "openai-workspace",
            "--api-key-env",
            "WORKSPACE_OPENAI_KEY",
        ],
    )
    assert add_result.exit_code == 0, add_result.output

    show_result = runner.invoke(app, ["providers", "show", "openai-workspace"])

    assert show_result.exit_code == 0, show_result.output
    assert "api_key_ref: env:WORKSPACE_OPENAI_KEY" in show_result.output


def test_cli_provider_capability_declarations_drive_preflight(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path))
    runner = CliRunner()

    add_result = runner.invoke(app, ["providers", "add-preset", "--preset", "afm"])
    assert add_result.exit_code == 0, add_result.output

    strict_before = runner.invoke(
        app,
        ["providers", "check-suite", "--provider", "afm", "--suite", "toolcall", "--strict-unknown"],
    )
    assert strict_before.exit_code == 0
    assert "compatible: true" in strict_before.output

    enable_result = runner.invoke(
        app,
        ["providers", "capabilities", "enable", "--provider", "afm", "--capability", "tool_calling"],
    )
    assert enable_result.exit_code == 0, enable_result.output

    list_result = runner.invoke(app, ["providers", "capabilities", "list", "--provider", "afm"])
    assert list_result.exit_code == 0, list_result.output
    assert "tool_calling\ttrue" in list_result.output

    show_result = runner.invoke(app, ["providers", "show", "afm"])
    assert show_result.exit_code == 0, show_result.output
    assert "- tool_calling: true" in show_result.output

    strict_after = runner.invoke(
        app,
        ["providers", "check-suite", "--provider", "afm", "--suite", "toolcall", "--strict-unknown"],
    )
    assert strict_after.exit_code == 0, strict_after.output
    assert "compatible: true" in strict_after.output

    disable_result = runner.invoke(
        app,
        ["providers", "capabilities", "disable", "--provider", "afm", "--capability", "tool_calling"],
    )
    assert disable_result.exit_code == 0, disable_result.output

    missing_after = runner.invoke(app, ["providers", "check-suite", "--provider", "afm", "--suite", "toolcall"])
    assert missing_after.exit_code == 1
    assert "provider does not support tool_calling" in missing_after.output

    clear_result = runner.invoke(
        app,
        ["providers", "capabilities", "clear", "--provider", "afm", "--capability", "tool_calling"],
    )
    assert clear_result.exit_code == 0, clear_result.output

    list_after_clear = runner.invoke(app, ["providers", "capabilities", "list", "--provider", "afm"])
    assert list_after_clear.exit_code == 0, list_after_clear.output
    assert "- tool_calling\tAPI-native tool/function-call envelope support" in list_after_clear.output


def test_cli_matrix_gate_can_include_failure_class_summary_without_thresholds(tmp_path) -> None:
    runner = CliRunner()
    results_dir = tmp_path / "runs" / "run-a"
    results_dir.mkdir(parents=True)
    (results_dir / "results.jsonl").write_text(
        '{"ok": false, "failure_class": "engine_protocol_bug"}\n',
        encoding="utf-8",
    )
    summary_path = tmp_path / "matrix-summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "matrix_name": "release-matrix",
                "matrix_path": "examples/matrices/release.yaml",
                "created_at": "2026-05-31T00:00:00Z",
                "total_runs": 1,
                "attempted_runs": 1,
                "completed_runs": 1,
                "failed_runs": 0,
                "runs": [
                    {
                        "index": 1,
                        "engine": "afm",
                        "provider": "afm",
                        "model": "qwen-test",
                        "suite": "toolcall",
                        "run_id": "run-a",
                        "ok": True,
                        "total_cases": 1,
                        "passed": 0,
                        "failed": 1,
                        "concurrency": 1,
                        "results_path": "runs/run-a/results.jsonl",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output_json = tmp_path / "matrix-gate.json"

    result = runner.invoke(
        app,
        [
            "matrix",
            "gate",
            str(summary_path),
            "--include-failure-class-summary",
            "--output-json",
            str(output_json),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "failure_classes: engine_protocol_bug=1" in result.output
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["failure_class_summary"] == [
        {"failure_class": "engine_protocol_bug", "count": 1},
    ]
    assert payload["failure_class_artifacts_missing"] == 0


def test_cli_provider_capability_rejects_unknown_key(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path))
    runner = CliRunner()

    add_result = runner.invoke(app, ["providers", "add-preset", "--preset", "afm"])
    assert add_result.exit_code == 0, add_result.output

    result = runner.invoke(
        app,
        ["providers", "capabilities", "enable", "--provider", "afm", "--capability", "made_up"],
    )

    assert result.exit_code != 0
    assert "unknown capability" in result.output


def test_cli_auth_test_resolves_env_secret(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    runner = CliRunner()

    runner.invoke(
        app,
        [
            "providers",
            "add",
            "--name",
            "openai",
            "--contract",
            "openai",
            "--base-url",
            "https://api.openai.com/v1",
            "--api-key-env",
            "OPENAI_API_KEY",
        ],
    )
    result = runner.invoke(app, ["providers", "auth", "test", "--provider", "openai"])

    assert result.exit_code == 0, result.output
    assert "secret reference resolves for openai" in result.output


def test_cli_auth_set_can_configure_portable_env_ref(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path))
    runner = CliRunner()
    audit_path = tmp_path / "auth-audit.jsonl"

    add_result = runner.invoke(
        app,
        [
            "providers",
            "add",
            "--name",
            "openai",
            "--contract",
            "openai",
            "--base-url",
            "https://api.openai.com/v1",
        ],
    )
    assert add_result.exit_code == 0, add_result.output

    set_result = runner.invoke(
        app,
        [
            "providers",
            "auth",
            "set",
            "--provider",
            "openai",
            "--api-key-env",
            "OPENAI_API_KEY",
            "--audit-log",
            str(audit_path),
        ],
    )
    assert set_result.exit_code == 0, set_result.output
    assert "stored env secret reference for openai" in set_result.output

    show_result = runner.invoke(app, ["providers", "show", "openai"])
    assert show_result.exit_code == 0, show_result.output
    assert "api_key_ref: env:OPENAI_API_KEY" in show_result.output

    status_result = runner.invoke(app, ["providers", "auth", "status", "--provider", "openai"])
    assert status_result.exit_code == 0, status_result.output
    assert "api_key_ref: env:OPENAI_API_KEY" in status_result.output
    assert "configured: true" in status_result.output
    assert "resolves: false" in status_result.output

    clear_result = runner.invoke(
        app,
        ["providers", "auth", "clear", "--provider", "openai", "--audit-log", str(audit_path)],
    )
    assert clear_result.exit_code == 0, clear_result.output
    assert "cleared auth reference for openai" in clear_result.output
    cleared_show_result = runner.invoke(app, ["providers", "show", "openai"])
    assert cleared_show_result.exit_code == 0, cleared_show_result.output
    assert "api_key_ref: none" in cleared_show_result.output
    audit_events = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert [event["event"] for event in audit_events] == [
        "provider_auth_ref_changed",
        "provider_auth_ref_cleared",
    ]
    assert audit_events[0]["api_key_ref"] == "env:OPENAI_API_KEY"
    assert audit_events[1]["previous_api_key_ref"] == "env:OPENAI_API_KEY"


def test_cli_auth_set_can_store_keyring_ref_from_stdin(monkeypatch, tmp_path) -> None:
    class FakeKeyring:
        values: dict[tuple[str, str], str] = {}

        @classmethod
        def set_password(cls, service: str, username: str, password: str) -> None:
            cls.values[(service, username)] = password

        @classmethod
        def get_password(cls, service: str, username: str) -> str | None:
            return cls.values.get((service, username))

        @classmethod
        def delete_password(cls, service: str, username: str) -> None:
            cls.values.pop((service, username), None)

    monkeypatch.setitem(sys.modules, "keyring", FakeKeyring)
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path))
    runner = CliRunner()

    add_result = runner.invoke(
        app,
        [
            "providers",
            "add",
            "--name",
            "openai",
            "--contract",
            "openai",
            "--base-url",
            "https://api.openai.com/v1",
        ],
    )
    assert add_result.exit_code == 0, add_result.output

    set_result = runner.invoke(
        app,
        ["providers", "auth", "set", "--provider", "openai", "--api-key-stdin"],
        input="super-secret\n",
    )
    assert set_result.exit_code == 0, set_result.output
    assert "stored keyring secret reference for openai" in set_result.output
    assert "super-secret" not in set_result.output

    test_result = runner.invoke(app, ["providers", "auth", "test", "--provider", "openai"])
    assert test_result.exit_code == 0, test_result.output
    assert "secret reference resolves for openai" in test_result.output

    status_result = runner.invoke(app, ["providers", "auth", "status", "--provider", "openai"])
    assert status_result.exit_code == 0, status_result.output
    assert "api_key_ref: keyring:openai:api_key" in status_result.output
    assert "kind: keyring" in status_result.output
    assert "resolves: true" in status_result.output

    clear_result = runner.invoke(app, ["providers", "auth", "clear", "--provider", "openai", "--delete-secret"])
    assert clear_result.exit_code == 0, clear_result.output
    assert "cleared auth reference and deleted keyring secret for openai" in clear_result.output
    assert FakeKeyring.values == {}
    show_result = runner.invoke(app, ["providers", "show", "openai"])
    assert show_result.exit_code == 0, show_result.output
    assert "api_key_ref: none" in show_result.output


def test_cli_auth_set_can_store_explicit_dotenv_fallback_from_stdin(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "home"))
    runner = CliRunner()
    dotenv_path = tmp_path / "dev.env"
    audit_path = tmp_path / "auth-audit.jsonl"

    add_result = runner.invoke(
        app,
        [
            "providers",
            "add",
            "--name",
            "openai",
            "--contract",
            "openai",
            "--base-url",
            "https://api.openai.com/v1",
        ],
    )
    assert add_result.exit_code == 0, add_result.output

    set_result = runner.invoke(
        app,
        [
            "providers",
            "auth",
            "set",
            "--provider",
            "openai",
            "--api-key-dotenv-file",
            str(dotenv_path),
            "--allow-plaintext-secret-file",
            "--audit-log",
            str(audit_path),
        ],
        input="super-secret\n",
    )
    assert set_result.exit_code == 0, set_result.output
    assert "WARNING: stored plaintext .env secret fallback for openai" in set_result.output
    assert "stored dotenv secret reference for openai" in set_result.output
    assert "super-secret" not in set_result.output

    show_result = runner.invoke(app, ["providers", "show", "openai"])
    assert show_result.exit_code == 0, show_result.output
    assert "api_key_ref: dotenv:AGENTBLASTER_OPENAI_API_KEY@<redacted-path>" in show_result.output
    assert str(dotenv_path) not in show_result.output

    test_result = runner.invoke(app, ["providers", "auth", "test", "--provider", "openai"])
    assert test_result.exit_code == 0, test_result.output
    assert "secret reference resolves for openai" in test_result.output

    status_result = runner.invoke(app, ["providers", "auth", "status", "--provider", "openai"])
    assert status_result.exit_code == 0, status_result.output
    assert "kind: dotenv" in status_result.output
    assert "resolves: true" in status_result.output
    assert "AGENTBLASTER_OPENAI_API_KEY=super-secret" in dotenv_path.read_text(encoding="utf-8")

    clear_result = runner.invoke(app, ["providers", "auth", "clear", "--provider", "openai", "--delete-secret"])
    assert clear_result.exit_code == 0, clear_result.output
    assert "cleared auth reference and deleted dotenv secret for openai" in clear_result.output
    assert "super-secret" not in dotenv_path.read_text(encoding="utf-8")

    audit_events = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert audit_events[0]["api_key_ref"] == "dotenv:AGENTBLASTER_OPENAI_API_KEY@<redacted-path>"
    assert audit_events[0]["api_key_ref_path_redacted"] is True
    assert audit_events[0]["plaintext_secret_file"] == "<redacted-path>"
    assert audit_events[0]["plaintext_secret_file_name"] == "dev.env"
    assert audit_events[0]["ref_kind"] == "dotenv"
    assert audit_events[0]["stored_dotenv_secret"] is True
    assert audit_events[0]["plaintext_secret_warning"] is True
    assert str(dotenv_path) not in audit_path.read_text(encoding="utf-8")


def test_cli_auth_set_does_not_write_dotenv_secret_when_policy_blocks_backend(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "home"))
    runner = CliRunner()
    dotenv_path = tmp_path / "dev.env"
    audit_path = tmp_path / "auth-audit.jsonl"
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text("allowed_secret_ref_kinds:\n  - env\n  - keyring\n", encoding="utf-8")

    add_result = runner.invoke(
        app,
        [
            "providers",
            "add",
            "--name",
            "openai",
            "--contract",
            "openai",
            "--base-url",
            "https://api.openai.com/v1",
        ],
    )
    assert add_result.exit_code == 0, add_result.output

    set_result = runner.invoke(
        app,
        [
            "providers",
            "auth",
            "set",
            "--provider",
            "openai",
            "--api-key-dotenv-file",
            str(dotenv_path),
            "--allow-plaintext-secret-file",
            "--policy",
            str(policy_path),
            "--audit-log",
            str(audit_path),
        ],
        input="super-secret\n",
    )
    show_result = runner.invoke(app, ["providers", "show", "openai"])
    audit = json.loads(audit_path.read_text(encoding="utf-8").splitlines()[0])

    assert set_result.exit_code != 0
    assert "provider auth secret storage blocked by policy" in set_result.output
    assert not dotenv_path.exists()
    assert "api_key_ref: none" in show_result.output
    assert audit["event"] == "provider_auth_ref_rejected"
    assert audit["stored_dotenv_secret"] is False
    assert audit["policy_ok"] is False
    assert "super-secret" not in json.dumps(audit)


def test_cli_auth_set_rejects_ambiguous_secret_sources(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path))
    runner = CliRunner()

    add_result = runner.invoke(
        app,
        [
            "providers",
            "add",
            "--name",
            "openai",
            "--contract",
            "openai",
            "--base-url",
            "https://api.openai.com/v1",
        ],
    )
    assert add_result.exit_code == 0, add_result.output

    result = runner.invoke(
        app,
        [
            "providers",
            "auth",
            "set",
            "--provider",
            "openai",
            "--api-key-stdin",
            "--api-key-env",
            "OPENAI_API_KEY",
        ],
        input="secret\n",
    )

    assert result.exit_code != 0
    assert "choose only one" in result.output

    dotenv_path = tmp_path / "dev.env"
    missing_ack_result = runner.invoke(
        app,
        [
            "providers",
            "auth",
            "set",
            "--provider",
            "openai",
            "--api-key-dotenv-file",
            str(dotenv_path),
        ],
        input="secret\n",
    )

    assert missing_ack_result.exit_code != 0
    assert "--api-key-dotenv-file requires --allow-plaintext-secret-file" in missing_ack_result.output

    ambiguous_dotenv_result = runner.invoke(
        app,
        [
            "providers",
            "auth",
            "set",
            "--provider",
            "openai",
            "--api-key-env",
            "OPENAI_API_KEY",
            "--api-key-dotenv-file",
            str(dotenv_path),
            "--allow-plaintext-secret-file",
        ],
        input="secret\n",
    )

    assert ambiguous_dotenv_result.exit_code != 0
    assert "choose only one" in ambiguous_dotenv_result.output


def test_cli_validate_case_accepts_suite_file(tmp_path) -> None:
    path = tmp_path / "suite.yaml"
    path.write_text(
        """
name: local-smoke
description: Local smoke suite
cases:
  - id: case-one
    title: Case one
    prompt: "Reply with exactly: agentblaster-ok"
    expected_substring: agentblaster-ok
""",
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(app, ["validate-case", str(path)])

    assert result.exit_code == 0, result.output
    assert "valid suite local-smoke with 1 case(s)" in result.output


def test_cli_suite_requirements_reports_required_capabilities() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["suite-requirements", "--suite", "trace-replay"])

    assert result.exit_code == 0, result.output
    assert "chat\tcases=trace-replay-tool-result-summary" in result.output
    assert "trace_replay\tcases=trace-replay-tool-result-summary" in result.output
    assert "tool_calling\tcases=trace-replay-tool-result-summary" in result.output


def test_cli_provider_check_suite_reports_compatibility_and_writes_json(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    runner = CliRunner()
    output = tmp_path / "compatibility.json"

    add_result = runner.invoke(app, ["providers", "add-preset", "--preset", "openai"])
    assert add_result.exit_code == 0, add_result.output

    result = runner.invoke(
        app,
        [
            "providers",
            "check-suite",
            "--provider",
            "openai",
            "--suite",
            "toolcall",
            "--output-json",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "compatible: true" in result.output
    assert "tool_calling" in result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["provider"] == "openai"
    assert payload["suite"] == "toolcall"
    assert payload["compatible"] is True


def test_cli_provider_check_suite_fails_on_missing_capability(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    runner = CliRunner()

    add_result = runner.invoke(app, ["providers", "add-preset", "--preset", "anthropic"])
    assert add_result.exit_code == 0, add_result.output

    result = runner.invoke(app, ["providers", "check-suite", "--provider", "anthropic", "--suite", "structured"])

    assert result.exit_code == 1
    assert "compatible: false" in result.output
    assert "structured_output" in result.output


def test_cli_provider_check_suite_can_fail_on_unknown_capability(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    runner = CliRunner()

    add_result = runner.invoke(app, ["providers", "add-preset", "--preset", "afm"])
    assert add_result.exit_code == 0, add_result.output

    result = runner.invoke(
        app,
        ["providers", "check-suite", "--provider", "afm", "--suite", "toolcall", "--strict-unknown"],
    )

    assert result.exit_code == 0
    assert "compatible: true" in result.output


def test_cli_run_preflight_blocks_provider_with_missing_capability(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    runner = CliRunner()

    add_result = runner.invoke(app, ["providers", "add-preset", "--preset", "anthropic"])
    assert add_result.exit_code == 0, add_result.output

    result = runner.invoke(
        app,
        [
            "run",
            "--engine",
            "anthropic",
            "--suite",
            "structured",
            "--model",
            "claude-test",
            "--no-raw-traces",
        ],
    )

    assert result.exit_code != 0
    assert "structured_output" in result.output
    assert not (tmp_path / "runs").exists()


def test_cli_run_preflight_can_block_unknown_capabilities_in_strict_mode(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    runner = CliRunner()

    add_result = runner.invoke(app, ["providers", "add-preset", "--preset", "afm"])
    assert add_result.exit_code == 0, add_result.output

    result = runner.invoke(
        app,
        [
            "run",
            "--engine",
            "afm",
            "--suite",
            "toolcall",
            "--model",
            "qwen-test",
            "--strict-unknown-capabilities",
            "--no-raw-traces",
        ],
    )

    assert result.exit_code == 0


def test_cli_run_dry_run_plans_without_writing_run_artifacts(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    runner = CliRunner()
    plan_path = tmp_path / "plan.json"

    add_result = runner.invoke(app, ["providers", "add-preset", "--preset", "afm"])
    assert add_result.exit_code == 0, add_result.output

    result = runner.invoke(
        app,
        [
            "run",
            "--engine",
            "afm",
            "--suite",
            "smoke",
            "--model",
            "qwen-test",
            "--dry-run",
            "--plan-json",
            str(plan_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "dry_run: true" in result.output
    assert "provider: afm" in result.output
    assert "estimated_prompt_tokens:" in result.output
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    assert payload["dry_run"] is True
    assert payload["provider"] == "afm"
    assert payload["suite"] == "smoke"
    assert payload["total_cases"] == 1
    assert not (tmp_path / "runs").exists()


def test_cli_matrix_dry_run_writes_plan_list(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    runner = CliRunner()
    matrix_path = tmp_path / "matrix.yaml"
    plan_path = tmp_path / "matrix-plan.json"
    matrix_path.write_text(
        """
name: dry-run-matrix
runs:
  - engine: afm
    suite: smoke
    model: qwen-test
    no_raw_traces: true
""",
        encoding="utf-8",
    )

    add_result = runner.invoke(app, ["providers", "add-preset", "--preset", "afm"])
    assert add_result.exit_code == 0, add_result.output

    result = runner.invoke(
        app,
        ["run", "--matrix", str(matrix_path), "--dry-run", "--plan-json", str(plan_path)],
    )

    assert result.exit_code == 0, result.output
    assert "matrix: dry-run-matrix" in result.output
    assert "plan afm smoke qwen-test" in result.output
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    assert payload[0]["provider"] == "afm"
    assert payload[0]["suite"] == "smoke"


def test_cli_dashboard_blocks_non_loopback_without_opt_in(tmp_path) -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["dashboard", "--runs", str(tmp_path), "--host", "0.0.0.0"])

    assert result.exit_code != 0
    assert "loopback" in result.output

    auth_result = runner.invoke(
        app,
        ["dashboard", "--runs", str(tmp_path), "--host", "0.0.0.0", "--allow-non-loopback"],
    )
    assert auth_result.exit_code != 0
    assert "requires token authentication" in auth_result.output


def test_cli_dashboard_policy_blocks_auth_disabled_and_audits(tmp_path) -> None:
    runner = CliRunner()
    policy_path = tmp_path / "agentblaster.policy.yaml"
    audit_path = tmp_path / "dashboard-audit.jsonl"
    policy_path.write_text(
        """
require_dashboard_auth: true
allowed_dashboard_hosts:
  - 127.0.0.1
allowed_dashboard_ports:
  - 8765
""",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "dashboard",
            "--runs",
            str(tmp_path),
            "--policy",
            str(policy_path),
            "--audit-log",
            str(audit_path),
        ],
    )

    assert result.exit_code != 0
    assert "authentication is required by policy" in result.output
    audit_event = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit_event["event"] == "policy_violation"
    assert audit_event["surface"] == "dashboard"
    assert audit_event["reason"] == "dashboard authentication is required by policy"


def test_cli_cleanup_expired_dry_run_and_execute(tmp_path) -> None:
    runner = CliRunner()
    run_dir = tmp_path / "runs" / "run_expired"
    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True)
    (raw_dir / "case.response.json").write_text("{}", encoding="utf-8")
    manifest = RunManifest(
        run_id="run_expired",
        suite="smoke",
        provider="local",
        contract=ApiContract.OPENAI,
        model="qwen-test",
        raw_trace_mode=RawTraceMode.REDACTED,
        created_at="2026-04-01T00:00:00+00:00",
        retention_policy=RetentionPolicy(retain_days=0, raw_trace_retain_days=0),
    )
    (run_dir / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    plan_path = tmp_path / "cleanup-plan.json"
    audit_path = tmp_path / "cleanup-audit.jsonl"
    policy_path = tmp_path / "agentblaster.policy.yaml"
    policy_path.write_text("require_cleanup_audit_log: true\n", encoding="utf-8")

    plan_result = runner.invoke(
        app,
        [
            "cleanup-expired",
            "--runs",
            str(tmp_path / "runs"),
            "--output-json",
            str(plan_path),
            "--audit-log",
            str(audit_path),
        ],
    )

    assert plan_result.exit_code == 0, plan_result.output
    assert "run\trun_expired" in plan_result.output
    assert run_dir.exists()
    plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan_payload["schema_version"] == "agentblaster.retention-cleanup.v1"
    assert plan_payload["report_type"] == "retention_cleanup_plan"
    assert plan_payload["execute"] is False
    assert plan_payload["security"]["contacts_providers"] is False
    assert plan_payload["security"]["contains_local_paths"] is True
    assert plan_payload["security"]["direct_publication_safe"] is False
    assert plan_payload["security"]["audit_log_required"] is False
    assert plan_payload["actions"][0]["action"] == "run"

    missing_audit_result = runner.invoke(
        app,
        ["cleanup-expired", "--runs", str(tmp_path / "runs"), "--require-audit-log"],
    )

    assert missing_audit_result.exit_code != 0
    assert "--require-audit-log requires --audit-log" in missing_audit_result.output

    policy_missing_audit_result = runner.invoke(
        app,
        ["cleanup-expired", "--runs", str(tmp_path / "runs"), "--policy", str(policy_path)],
    )

    assert policy_missing_audit_result.exit_code != 0
    assert "--require-audit-log requires --audit-log" in policy_missing_audit_result.output

    policy_plan_path = tmp_path / "cleanup-policy-plan.json"
    policy_plan_result = runner.invoke(
        app,
        [
            "cleanup-expired",
            "--runs",
            str(tmp_path / "runs"),
            "--policy",
            str(policy_path),
            "--audit-log",
            str(audit_path),
            "--output-json",
            str(policy_plan_path),
        ],
    )

    assert policy_plan_result.exit_code == 0, policy_plan_result.output
    policy_plan_payload = json.loads(policy_plan_path.read_text(encoding="utf-8"))
    assert policy_plan_payload["security"]["audit_log_required"] is True

    execute_result = runner.invoke(app, ["cleanup-expired", "--runs", str(tmp_path / "runs"), "--execute"])

    assert execute_result.exit_code == 0, execute_result.output
    assert not run_dir.exists()
    assert "retention_cleanup_planned" in audit_path.read_text(encoding="utf-8")


def test_cli_cleanup_defaults_to_plan_and_requires_execute_to_delete(tmp_path) -> None:
    runner = CliRunner()
    run_dir = tmp_path / "runs" / "run_manual"
    raw_dir = run_dir / "raw"
    cache_dir = run_dir / "cache"
    raw_dir.mkdir(parents=True)
    cache_dir.mkdir()
    (raw_dir / "case.response.json").write_text("{}", encoding="utf-8")
    (cache_dir / "prefill.bin").write_text("cache", encoding="utf-8")
    (run_dir / "report.html").write_text("<html></html>", encoding="utf-8")
    plan_path = tmp_path / "manual-cleanup-plan.json"
    audit_path = tmp_path / "manual-cleanup-audit.jsonl"
    policy_path = tmp_path / "agentblaster.policy.yaml"
    policy_path.write_text("require_cleanup_audit_log: true\n", encoding="utf-8")

    plan_result = runner.invoke(
        app,
        [
            "cleanup",
            str(run_dir),
            "--raw",
            "--reports",
            "--caches",
            "--output-json",
            str(plan_path),
            "--audit-log",
            str(audit_path),
        ],
    )

    assert plan_result.exit_code == 0, plan_result.output
    assert "would-remove" in plan_result.output
    assert raw_dir.exists()
    assert cache_dir.exists()
    plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan_payload["schema_version"] == "agentblaster.cleanup-plan.v1"
    assert plan_payload["report_type"] == "manual_cleanup_plan"
    assert plan_payload["execute"] is False
    assert plan_payload["security"]["contains_raw_provider_payloads"] is False
    assert plan_payload["security"]["reads_keyring_values"] is False
    assert plan_payload["security"]["contains_local_paths"] is True
    assert plan_payload["security"]["direct_publication_safe"] is False
    assert plan_payload["security"]["audit_log_required"] is False
    assert str(raw_dir) in plan_payload["paths"]
    assert "manual_cleanup_planned" in audit_path.read_text(encoding="utf-8")

    missing_audit_result = runner.invoke(app, ["cleanup", str(run_dir), "--raw", "--require-audit-log"])

    assert missing_audit_result.exit_code != 0
    assert "--require-audit-log requires --audit-log" in missing_audit_result.output

    policy_missing_audit_result = runner.invoke(app, ["cleanup", str(run_dir), "--raw", "--policy", str(policy_path)])

    assert policy_missing_audit_result.exit_code != 0
    assert "--require-audit-log requires --audit-log" in policy_missing_audit_result.output

    policy_plan_path = tmp_path / "manual-cleanup-policy-plan.json"
    policy_plan_result = runner.invoke(
        app,
        [
            "cleanup",
            str(run_dir),
            "--raw",
            "--policy",
            str(policy_path),
            "--audit-log",
            str(audit_path),
            "--output-json",
            str(policy_plan_path),
        ],
    )

    assert policy_plan_result.exit_code == 0, policy_plan_result.output
    policy_plan_payload = json.loads(policy_plan_path.read_text(encoding="utf-8"))
    assert policy_plan_payload["security"]["audit_log_required"] is True

    execute_result = runner.invoke(app, ["cleanup", str(run_dir), "--raw", "--reports", "--caches", "--execute"])

    assert execute_result.exit_code == 0, execute_result.output
    assert "removed" in execute_result.output
    assert not raw_dir.exists()
    assert not cache_dir.exists()
    assert not (run_dir / "report.html").exists()


def test_cli_quality_tiers_and_commands_are_reportable() -> None:
    runner = CliRunner()

    tiers_result = runner.invoke(app, ["quality", "tiers"])
    command_result = runner.invoke(app, ["quality", "command", "normal"])

    assert tiers_result.exit_code == 0, tiers_result.output
    assert "normal\tci\tnot remote and not slow and not gui" in tiers_result.output
    assert "gui\topt-in\tgui" in tiers_result.output
    assert command_result.exit_code == 0, command_result.output
    assert 'pytest -q -m "not remote and not slow and not gui"' in command_result.output


def test_cli_quality_chrome_checklist_can_write_markdown(tmp_path) -> None:
    runner = CliRunner()
    output = tmp_path / "chrome-checklist.md"

    result = runner.invoke(app, ["quality", "chrome-checklist", "--output", str(output)])

    assert result.exit_code == 0, result.output
    text = output.read_text(encoding="utf-8")
    assert "AgentBlaster Chrome GUI Validation Checklist" in text
    assert "Codex Chrome plugin" in text
    assert "chrome-redaction-check" in text


def test_cli_quality_validation_manifest_can_write_json(tmp_path) -> None:
    runner = CliRunner()
    output = tmp_path / "sdlc-validation-manifest.json"

    result = runner.invoke(app, ["quality", "validation-manifest", "--output", str(output)])

    assert result.exit_code == 0, result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "agentblaster.sdlc-validation-manifest.v1"
    assert payload["gui"]["chrome_tool"] == "Codex Chrome plugin"
    assert payload["security"]["runs_tests"] is False


def test_cli_harness_profiles_and_generate_write_suite(tmp_path) -> None:
    runner = CliRunner()
    output = tmp_path / "generated-harness.yaml"
    review_output = tmp_path / "generated-harness-review.json"

    profiles_result = runner.invoke(app, ["harness", "profiles"])
    generate_result = runner.invoke(
        app,
        [
            "harness",
            "generate",
            "--profile",
            "contract-fuzz",
            "--suite",
            "smoke",
            "--repeats",
            "1",
            "--seed",
            "5",
            "--output",
            str(output),
        ],
    )
    review_result = runner.invoke(
        app,
        [
            "harness",
            "review",
            "--suite-file",
            str(output),
            "--output-json",
            str(review_output),
        ],
    )

    assert profiles_result.exit_code == 0, profiles_result.output
    assert "contract-fuzz" in profiles_result.output
    assert "cancellation" in profiles_result.output
    assert "emerging-workflows" in profiles_result.output
    assert "judge-rubric" in profiles_result.output
    assert generate_result.exit_code == 0, generate_result.output
    assert review_result.exit_code == 0, review_result.output
    text = output.read_text(encoding="utf-8")
    review = json.loads(review_output.read_text(encoding="utf-8"))
    assert "smoke-contract-fuzz-harness" in text
    assert "protocol-smoke-chat-stream-contract-01" in text
    assert "protocol-smoke-chat-json-contract-01" in text
    assert "protocol-smoke-chat-tool-contract-01" in text
    assert review["schema_version"] == "agentblaster.harness-review.v1"
    assert review["review"]["calibration_required_before_release_gate"] is True
    assert "AgentBlaster harness review" in review_result.output


def test_cli_model_targets_and_matrix_generation(tmp_path) -> None:
    runner = CliRunner()
    output = tmp_path / "model-matrix.yaml"

    targets_result = runner.invoke(app, ["models", "targets"])
    show_result = runner.invoke(app, ["models", "show", "qwen3.6-27b-dense"])
    matrix_result = runner.invoke(
        app,
        [
            "models",
            "matrix",
            "--providers",
            "afm,lm-studio",
            "--targets",
            "qwen3.6-27b-dense,gemma-4-31b-dense",
            "--suite",
            "trace-replay",
            "--concurrency",
            "2",
            "--output",
            str(output),
        ],
    )

    assert targets_result.exit_code == 0, targets_result.output
    assert "qwen3.6-27b-dense" in targets_result.output
    assert "gemma-4-31b-dense" in targets_result.output
    assert "model_id,revision,architecture,quantization,tokenizer,chat_template,context_length" in targets_result.output
    assert show_result.exit_code == 0, show_result.output
    assert "architecture: qwen3.6-dense" in show_result.output
    assert "comparison_group: qwen3.6-27b-dense" in show_result.output
    assert (
        "required_release_metadata: model_id, revision, architecture, quantization, tokenizer, chat_template, context_length"
        in show_result.output
    )
    assert "publication_guidance:" in show_result.output
    assert "separate primary charts" in show_result.output
    assert matrix_result.exit_code == 0, matrix_result.output

    text = output.read_text(encoding="utf-8")
    assert "suite: trace-replay" in text
    assert "engine: afm" in text
    assert "engine: lm-studio" in text
    assert "architecture: qwen3.6-dense" in text
    assert "architecture: gemma-4-dense" in text


def test_cli_run_smoke_writes_artifacts(monkeypatch, tmp_path) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            content_length = int(self.headers.get("content-length", "0"))
            if content_length:
                self.rfile.read(content_length)
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "choices": [{"message": {"content": "agentblaster-ok"}}],
                        "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
                    }
                ).encode()
            )

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
        runner = CliRunner()
        base_url = f"http://127.0.0.1:{server.server_address[1]}/v1"

        add_result = runner.invoke(
            app,
            [
                "providers",
                "add",
                "--name",
                "local-openai",
                "--contract",
                "openai",
                "--base-url",
                base_url,
            ],
        )
        assert add_result.exit_code == 0, add_result.output

        run_result = runner.invoke(
            app,
            [
                "run",
                "--suite",
                "smoke",
                "--engine",
                "local-openai",
                "--model",
                "qwen-test",
                "--output-dir",
                str(tmp_path / "runs"),
                "--no-raw-traces",
            ],
        )

        assert run_result.exit_code == 0, run_result.output
        assert "ok: true" in run_result.output
        assert "total_cases: 1" in run_result.output
        assert "run_id:" in run_result.output
        assert list((tmp_path / "runs").glob("*/results.jsonl"))
    finally:
        server.shutdown()


def test_cli_run_suite_file(monkeypatch, tmp_path) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            content_length = int(self.headers.get("content-length", "0"))
            if content_length:
                self.rfile.read(content_length)
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "choices": [{"message": {"content": "agentblaster-ok"}}],
                        "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
                    }
                ).encode()
            )

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

    suite_file = tmp_path / "suite.yaml"
    suite_file.write_text(
        """
name: custom-smoke
description: Custom smoke suite
cases:
  - id: custom-case
    title: Custom case
    prompt: "Reply with exactly: agentblaster-ok"
    expected_substring: agentblaster-ok
""",
        encoding="utf-8",
    )
    summary_path = tmp_path / "matrix-summary.json"
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
        runner = CliRunner()
        base_url = f"http://127.0.0.1:{server.server_address[1]}/v1"
        runner.invoke(
            app,
            [
                "providers",
                "add",
                "--name",
                "local-openai",
                "--contract",
                "openai",
                "--base-url",
                base_url,
            ],
        )

        result = runner.invoke(
            app,
            [
                "run",
                "--suite-file",
                str(suite_file),
                "--engine",
                "local-openai",
                "--model",
                "qwen-test",
                "--output-dir",
                str(tmp_path / "runs"),
                "--no-raw-traces",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "suite: custom-smoke" in result.output
        assert list((tmp_path / "runs").glob("*/summary.json"))
    finally:
        server.shutdown()


def test_cli_run_matrix(monkeypatch, tmp_path) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            content_length = int(self.headers.get("content-length", "0"))
            if content_length:
                self.rfile.read(content_length)
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "choices": [{"message": {"content": "agentblaster-ok"}}],
                        "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
                    }
                ).encode()
            )

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

    matrix_path = tmp_path / "matrix.yaml"
    summary_path = tmp_path / "matrix-summary.json"
    matrix_path.write_text(
        """
name: test-matrix
runs:
  - engine: local-openai
    suite: smoke
    model: qwen-test
    no_raw_traces: true
""",
        encoding="utf-8",
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
        runner = CliRunner()
        base_url = f"http://127.0.0.1:{server.server_address[1]}/v1"
        runner.invoke(
            app,
            [
                "providers",
                "add",
                "--name",
                "local-openai",
                "--contract",
                "openai",
                "--base-url",
                base_url,
            ],
        )

        result = runner.invoke(
            app,
            [
                "run",
                "--matrix",
                str(matrix_path),
                "--output-dir",
                str(tmp_path / "runs"),
                "--matrix-summary-json",
                str(summary_path),
            ],
        )

        assert result.exit_code == 0, result.output
        assert "matrix: test-matrix" in result.output
        assert "[1/1]" in result.output
        assert f"matrix_summary_json: {summary_path}" in result.output
        assert list((tmp_path / "runs").glob("*/summary.json"))
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == 1
        assert payload["matrix_name"] == "test-matrix"
        assert payload["total_runs"] == 1
        assert payload["completed_runs"] == 1
        assert payload["failed_runs"] == 0
        assert payload["runs"][0]["engine"] == "local-openai"
        assert payload["runs"][0]["provider"] == "local-openai"
        assert payload["runs"][0]["model"] == "qwen-test"
        assert payload["runs"][0]["suite"] == "smoke"
        assert payload["runs"][0]["ok"] is True
        assert payload["runs"][0]["total_cases"] == 1
        assert Path(payload["runs"][0]["summary_path"]).name == "summary.json"
        assert (summary_path.parent / payload["runs"][0]["results_path"]).exists()
        assert (summary_path.parent / payload["runs"][0]["manifest_path"]).exists()
        assert (summary_path.parent / payload["runs"][0]["summary_path"]).exists()
        report_dir = tmp_path / "matrix-reports"
        matrix_report_result = runner.invoke(
            app,
            [
                "matrix",
                "report",
                str(summary_path),
                "--format",
                "html,json",
                "--output-dir",
                str(report_dir),
                "--audit-log",
                str(tmp_path / "matrix-report-audit.jsonl"),
            ],
        )
        assert matrix_report_result.exit_code == 0, matrix_report_result.output
        assert str(report_dir / "matrix-summary-matrix-report.html") in matrix_report_result.output
        assert (report_dir / "matrix-summary-matrix-report.json").exists()
        matrix_audit = json.loads((tmp_path / "matrix-report-audit.jsonl").read_text(encoding="utf-8"))
        assert matrix_audit["event"] == "matrix_report_exported"
        assert matrix_audit["summary_json"] == str(summary_path)
    finally:
        server.shutdown()


def test_cli_run_offline_blocks_remote_provider(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    runner = CliRunner()

    add_result = runner.invoke(
        app,
        [
            "providers",
            "add",
            "--name",
            "openai",
            "--contract",
            "openai",
            "--base-url",
            "https://api.openai.com/v1",
            "--remote",
        ],
    )
    assert add_result.exit_code == 0, add_result.output

    result = runner.invoke(
        app,
        [
            "run",
            "--suite",
            "smoke",
            "--engine",
            "openai",
            "--model",
            "qwen-test",
            "--offline",
        ],
    )

    assert result.exit_code != 0
    assert "remote providers are disabled" in result.output


def test_cli_report_generates_html_json_and_audit(monkeypatch, tmp_path) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            content_length = int(self.headers.get("content-length", "0"))
            if content_length:
                self.rfile.read(content_length)
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "choices": [{"message": {"content": "agentblaster-ok"}}],
                        "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
                    }
                ).encode()
            )

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
        runner = CliRunner()
        base_url = f"http://127.0.0.1:{server.server_address[1]}/v1"
        runner.invoke(
            app,
            [
                "providers",
                "add",
                "--name",
                "local-openai",
                "--contract",
                "openai",
                "--base-url",
                base_url,
            ],
        )
        run_result = runner.invoke(
            app,
            [
                "run",
                "--suite",
                "smoke",
                "--engine",
                "local-openai",
                "--model",
                "qwen-test",
                "--output-dir",
                str(tmp_path / "runs"),
                "--no-raw-traces",
                "--audit-log",
                str(tmp_path / "audit.jsonl"),
                "--retention-classification",
                "confidential",
                "--retention-days",
                "30",
                "--raw-trace-retention-days",
                "7",
                "--retention-note",
                "delete raw traces first",
            ],
        )
        assert run_result.exit_code == 0, run_result.output
        run_dir = next((tmp_path / "runs").glob("*"))
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["retention_policy"]["classification"] == "confidential"
        assert manifest["retention_policy"]["retain_days"] == 30
        assert manifest["retention_policy"]["raw_trace_retain_days"] == 7
        assert manifest["retention_policy"]["notes"] == ["delete raw traces first"]

        report_result = runner.invoke(
            app,
            [
                "report",
                str(run_dir),
                "--format",
                "html,json,publication,card,pdf",
                "--audit-log",
                str(tmp_path / "control-audit.jsonl"),
            ],
        )

        assert report_result.exit_code == 0, report_result.output
        assert (run_dir / "report.html").exists()
        assert (run_dir / "summary.json").exists()
        assert "run_completed" in (tmp_path / "audit.jsonl").read_text(encoding="utf-8")

        export_result = runner.invoke(
            app,
            ["export", str(run_dir), "--format", "jsonl,csv", "--audit-log", str(tmp_path / "control-audit.jsonl")],
        )
        assert export_result.exit_code == 0, export_result.output
        assert (run_dir / "exports" / "results.jsonl").exists()
        assert (run_dir / "exports" / "results.csv").exists()

        compare_result = runner.invoke(app, ["compare", str(run_dir), str(run_dir)])
        assert compare_result.exit_code == 0, compare_result.output
        assert "avg_latency_ms" in compare_result.output

        verify_result = runner.invoke(app, ["verify", str(run_dir)])
        assert verify_result.exit_code == 0, verify_result.output
        assert "ok: true" in verify_result.output

        monkeypatch.setenv("AGENTBLASTER_SIGNING_KEY", "test-signing-secret")
        sign_result = runner.invoke(
            app,
            ["sign", str(run_dir), "--key-env", "AGENTBLASTER_SIGNING_KEY", "--key-id", "test-key"],
        )
        assert sign_result.exit_code == 0, sign_result.output
        assert "signature.json" in sign_result.output
        signature_result = runner.invoke(
            app,
            ["verify-signature", str(run_dir), "--key-env", "AGENTBLASTER_SIGNING_KEY"],
        )
        assert signature_result.exit_code == 0, signature_result.output
        assert "signature_ok: true" in signature_result.output
        assert "test-signing-secret" not in signature_result.output

        publication_bundle_result = runner.invoke(
            app,
            [
                "publication-bundle",
                str(run_dir),
                "--output-dir",
                str(tmp_path / "publication-bundles"),
                "--audit-log",
                str(tmp_path / "control-audit.jsonl"),
            ],
        )
        assert publication_bundle_result.exit_code == 0, publication_bundle_result.output
        assert "agentblaster-publication.zip" in publication_bundle_result.output
        publication_bundle_path = next((tmp_path / "publication-bundles").glob("*.agentblaster-publication.zip"))
        with ZipFile(publication_bundle_path) as archive:
            bundle_manifest = json.loads(archive.read("publication-bundle-manifest.json").decode("utf-8"))
        assert bundle_manifest["schema_version"] == "agentblaster.publication-bundle.v1"
        assert bundle_manifest["publication_readiness"]["schema_version"] == "agentblaster.publication-readiness.v1"
        assert bundle_manifest["security"]["contains_results_jsonl"] is False
        assert "results.jsonl" not in bundle_manifest["artifacts"]

        bundle_result = runner.invoke(app, ["bundle", str(run_dir), "--output-dir", str(tmp_path / "bundles")])
        assert bundle_result.exit_code == 0, bundle_result.output
        assert "agentblaster.zip" in bundle_result.output

        cleanup_result = runner.invoke(app, ["cleanup", str(run_dir), "--raw", "--reports", "--exports", "--execute"])
        assert cleanup_result.exit_code == 0, cleanup_result.output
        assert not (run_dir / "exports").exists()
        assert not (run_dir / "summary.json").exists()
        control_audit = (tmp_path / "control-audit.jsonl").read_text(encoding="utf-8")
        assert "report_exported" in control_audit
        assert "results_exported" in control_audit

        original_import = builtins.__import__

        def fail_pyarrow_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "pyarrow" or name.startswith("pyarrow."):
                raise ImportError("forced missing pyarrow")
            return original_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", fail_pyarrow_import)
        parquet_result = runner.invoke(app, ["export", str(run_dir), "--format", "parquet"])
        assert parquet_result.exit_code != 0
        assert "parquet export requires optional dependency" in parquet_result.output
        assert "publication_bundle_created" in control_audit
    finally:
        server.shutdown()


def test_cli_selftest_dry_run_renders_tier_command() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["selftest", "--tier", "security", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "tier: security" in result.output
    assert "marker: security" in result.output
    assert "PYTHONPATH=src pytest -q -m security" in result.output


def test_cli_selftest_gui_dry_run_renders_chrome_options() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["selftest", "gui", "--browser", "chrome", "--headed", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "tier: gui" in result.output
    assert "browser: chrome" in result.output
    assert "headed: true" in result.output
    assert "AGENTBLASTER_GUI_BROWSER=chrome" in result.output
    assert "AGENTBLASTER_GUI_HEADED=1" in result.output


def test_cli_selftest_dry_run_renders_stable_run_id(tmp_path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "selftest",
            "--tier",
            "normal",
            "--dry-run",
            "--report-dir",
            str(tmp_path / "selftest"),
            "--run-id",
            "campaign-selftest",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "run_id: campaign-selftest" in result.output
    assert f"report_dir: {tmp_path / 'selftest'}" in result.output


def test_cli_selftest_report_generates_requested_formats(tmp_path) -> None:
    run_dir = tmp_path / "selftest_20260531T000000Z"
    run_dir.mkdir()
    (run_dir / "selftest.json").write_text(
        json.dumps(
            {
                "run_id": "selftest_20260531T000000Z",
                "tier": "normal",
                "marker_expression": "not remote and not slow and not gui",
                "command": 'PYTHONPATH=src pytest -q -m "not remote and not slow and not gui"',
                "started_at": "2026-05-31T00:00:00+00:00",
                "completed_at": "2026-05-31T00:00:01+00:00",
                "duration_ms": 1000.0,
                "exit_code": 0,
                "ok": True,
            }
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(app, ["selftest", "report", "--run", str(run_dir), "--format", "html,json,junit"])

    assert result.exit_code == 0, result.output
    assert str(run_dir / "selftest-report.html") in result.output
    assert str(run_dir / "selftest-report.json") in result.output
    assert str(run_dir / "selftest-report.junit.xml") in result.output
    payload = json.loads((run_dir / "selftest-report.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "agentblaster.selftest-report.v1"


def test_cli_release_provenance_writes_redaction_safe_artifact(tmp_path) -> None:
    runner = CliRunner()
    output = tmp_path / "release-provenance.json"
    audit_log = tmp_path / "audit.jsonl"

    result = runner.invoke(
        app,
        [
            "release",
            "provenance",
            "--output",
            str(output),
            "--audit-log",
            str(audit_log),
        ],
    )

    assert result.exit_code == 0, result.output
    assert str(output) in result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == "agentblaster.release-provenance"
    assert payload["project"]["name"] == "agentblaster"
    assert "typer>=0.12" in payload["dependencies"]["declared_runtime"]
    assert payload["dependencies"]["installed"] == []
    assert "release_provenance_created" in audit_log.read_text(encoding="utf-8")


def test_cli_run_matrix_continue_on_error_writes_failed_entry(tmp_path) -> None:
    runner = CliRunner()
    matrix_path = tmp_path / "matrix.yaml"
    summary_path = tmp_path / "matrix-summary.json"
    matrix_path.write_text(
        """
name: partial-matrix
runs:
  - engine: missing-provider
    suite: smoke
    model: qwen-test
""".lstrip(),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "run",
            "--matrix",
            str(matrix_path),
            "--continue-on-error",
            "--matrix-summary-json",
            str(summary_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "failed missing-provider smoke" in result.output
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["continue_on_error"] is True
    assert payload["total_runs"] == 1
    assert payload["attempted_runs"] == 1
    assert payload["completed_runs"] == 0
    assert payload["failed_runs"] == 1
    assert payload["runs"][0]["ok"] is False
    assert payload["runs"][0]["run_id"] is None
    assert payload["runs"][0]["summary_path"] is None
    assert payload["runs"][0]["error_type"] == "ConfigError"


def test_cli_run_matrix_policy_blocks_aggregate_limits(tmp_path) -> None:
    runner = CliRunner()
    matrix_path = tmp_path / "matrix.yaml"
    policy_path = tmp_path / "agentblaster.policy.yaml"
    audit_path = tmp_path / "audit.jsonl"
    matrix_path.write_text(
        """
name: aggregate-policy-matrix
runs:
  - engine: missing-provider-a
    suite: smoke
    model: qwen-test
  - engine: missing-provider-b
    suite: smoke
    model: gemma-test
""".lstrip(),
        encoding="utf-8",
    )
    policy_path.write_text("max_matrix_runs: 1\nmax_matrix_total_cases: 10\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "run",
            "--matrix",
            str(matrix_path),
            "--policy",
            str(policy_path),
            "--audit-log",
            str(audit_path),
        ],
    )

    assert result.exit_code != 0
    assert "max_matrix_runs" in result.output
    audit_text = audit_path.read_text(encoding="utf-8")
    assert "matrix_policy_evaluation" in audit_text
    assert "policy_violation" in audit_text


def test_cli_catalog_commands_list_bundled_capability_surfaces(tmp_path) -> None:
    runner = CliRunner()

    tools_result = runner.invoke(app, ["catalog", "simulated-tools"])
    mcp_output = tmp_path / "mcp-catalog.json"
    mcp_result = runner.invoke(app, ["catalog", "mcp-profiles", "--output-json", str(mcp_output)])
    lcp_output = tmp_path / "lcp-catalog.json"
    lcp_result = runner.invoke(app, ["catalog", "lcp-profiles", "--output-json", str(lcp_output)])
    skills_result = runner.invoke(app, ["catalog", "skills"])

    assert tools_result.exit_code == 0, tools_result.output
    assert "search_docs" in tools_result.output
    assert "without touching the host filesystem" in tools_result.output
    assert mcp_result.exit_code == 0, mcp_result.output
    mcp_payload = json.loads(mcp_output.read_text(encoding="utf-8"))
    assert mcp_payload["catalog"] == "agentblaster.mcp-profiles"
    assert any(item["name"] == "fixture-mcp" for item in mcp_payload["items"])
    assert all(item["host_execution"] is False for item in mcp_payload["items"])
    assert all(item["deterministic_result_support"] is True for item in mcp_payload["items"])
    assert lcp_result.exit_code == 0, lcp_result.output
    lcp_payload = json.loads(lcp_output.read_text(encoding="utf-8"))
    assert lcp_payload["catalog"] == "agentblaster.lcp-profiles"
    assert any(item["name"] == "wide-lcp-context" for item in lcp_payload["items"])
    assert all(item["host_execution"] is False for item in lcp_payload["items"])
    assert skills_result.exit_code == 0, skills_result.output
    assert "safe-tool-replay" in skills_result.output
    assert "large-prefix-diagnostic" in skills_result.output


def test_cli_suite_audit_reports_static_governance_summary(tmp_path) -> None:
    runner = CliRunner()
    suite_path = tmp_path / "audit-suite.yaml"
    output_json = tmp_path / "suite-audit.json"
    suite_path.write_text(
        """
name: audit-suite
description: Audit suite
cases:
  - id: external-case
    title: External case
    prompt: Use the deterministic fixture tool.
    provenance: public_benchmark_adapted
    risk_level: high
    simulated_tools:
      - search_docs
""".lstrip(),
        encoding="utf-8",
    )

    text_result = runner.invoke(app, ["suite-audit", "--suite-file", str(suite_path)])
    json_result = runner.invoke(app, ["suite-audit", "--suite-file", str(suite_path), "--output-json", str(output_json)])

    assert text_result.exit_code == 0, text_result.output
    assert "suite: audit-suite" in text_result.output
    assert "missing_source_url" in text_result.output
    assert "high_risk_case" in text_result.output
    assert json_result.exit_code == 0, json_result.output
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["suite"] == "audit-suite"
    assert payload["capability_surfaces"]["simulated_tools"] == ["search_docs"]
    assert {finding["code"] for finding in payload["findings"]} == {
        "missing_source_url",
        "missing_license",
        "high_risk_case",
    }


def test_cli_run_matrix_policy_blocks_aggregate_estimated_cost(monkeypatch, tmp_path) -> None:
    from agentblaster.config import ProviderStore
    from agentblaster.models import ProviderConfig

    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "home"))
    ProviderStore().upsert(
        ProviderConfig(
            name="costly-local",
            contract=ApiContract.OPENAI,
            base_url="http://127.0.0.1:9999/v1",
            default_model="qwen-test",
            cost_model={"input_usd_per_1m_tokens": 1_000_000.0, "output_usd_per_1m_tokens": 1_000_000.0},
        )
    )
    matrix_path = tmp_path / "matrix.yaml"
    policy_path = tmp_path / "agentblaster.policy.yaml"
    audit_path = tmp_path / "audit.jsonl"
    matrix_path.write_text(
        """
name: costly-matrix
runs:
  - engine: costly-local
    suite: smoke
""".lstrip(),
        encoding="utf-8",
    )
    policy_path.write_text("max_estimated_matrix_cost_usd: 0.01\n", encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "run",
            "--matrix",
            str(matrix_path),
            "--policy",
            str(policy_path),
            "--audit-log",
            str(audit_path),
        ],
    )

    assert result.exit_code != 0
    assert "max_estimated_matrix_cost_usd" in result.output
    audit_text = audit_path.read_text(encoding="utf-8")
    assert "matrix_policy_evaluation" in audit_text
    assert "estimated_cost_usd" in audit_text
    assert "policy_violation" in audit_text


def test_cli_provider_cost_model_lifecycle(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "home"))
    runner = CliRunner()
    audit_path = tmp_path / "cost-audit.jsonl"

    add_result = runner.invoke(
        app,
        [
            "providers",
            "add",
            "--name",
            "gateway",
            "--contract",
            "openai",
            "--base-url",
            "https://gateway.example.com/v1",
            "--remote",
        ],
    )
    set_result = runner.invoke(
        app,
        [
            "providers",
            "cost",
            "set",
            "--provider",
            "gateway",
            "--input-usd-per-1m-tokens",
            "3.0",
            "--output-usd-per-1m-tokens",
            "12.0",
            "--cached-input-usd-per-1m-tokens",
            "0.3",
            "--cache-write-usd-per-1m-tokens",
            "3.75",
            "--request-usd",
            "0.001",
            "--audit-log",
            str(audit_path),
        ],
    )
    show_result = runner.invoke(app, ["providers", "cost", "show", "--provider", "gateway"])
    provider_show_result = runner.invoke(app, ["providers", "show", "gateway"])
    clear_result = runner.invoke(
        app,
        ["providers", "cost", "clear", "--provider", "gateway", "--audit-log", str(audit_path)],
    )
    show_after_clear = runner.invoke(app, ["providers", "cost", "show", "--provider", "gateway"])

    assert add_result.exit_code == 0, add_result.output
    assert set_result.exit_code == 0, set_result.output
    assert "stored cost model for gateway" in set_result.output
    assert show_result.exit_code == 0, show_result.output
    assert "input_usd_per_1m_tokens: 3.0" in show_result.output
    assert "output_usd_per_1m_tokens: 12.0" in show_result.output
    assert "request_usd: 0.001" in show_result.output
    assert provider_show_result.exit_code == 0, provider_show_result.output
    assert "cost_model: configured" in provider_show_result.output
    assert clear_result.exit_code == 0, clear_result.output
    assert "cleared cost model for gateway" in clear_result.output
    assert show_after_clear.exit_code == 0, show_after_clear.output
    assert "cost_model: none for gateway" in show_after_clear.output
    audit_events = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert [event["event"] for event in audit_events] == [
        "provider_cost_model_changed",
        "provider_cost_model_cleared",
    ]


def test_cli_provider_rate_limits_lifecycle(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "home"))
    runner = CliRunner()
    audit_path = tmp_path / "rate-limit-audit.jsonl"

    add_result = runner.invoke(
        app,
        [
            "providers",
            "add",
            "--name",
            "gateway",
            "--contract",
            "openai",
            "--base-url",
            "https://gateway.example.com/v1",
            "--remote",
        ],
    )
    set_result = runner.invoke(
        app,
        [
            "providers",
            "rate-limits",
            "set",
            "--provider",
            "gateway",
            "--max-concurrency",
            "2",
            "--requests-per-minute",
            "60",
            "--requests-per-second",
            "1",
            "--audit-log",
            str(audit_path),
        ],
    )
    show_result = runner.invoke(app, ["providers", "rate-limits", "show", "--provider", "gateway"])
    provider_show_result = runner.invoke(app, ["providers", "show", "gateway"])
    clear_result = runner.invoke(
        app,
        ["providers", "rate-limits", "clear", "--provider", "gateway", "--audit-log", str(audit_path)],
    )
    show_after_clear = runner.invoke(app, ["providers", "rate-limits", "show", "--provider", "gateway"])

    assert add_result.exit_code == 0, add_result.output
    assert set_result.exit_code == 0, set_result.output
    assert "stored rate limits for gateway" in set_result.output
    assert show_result.exit_code == 0, show_result.output
    assert "max_concurrency: 2" in show_result.output
    assert "requests_per_minute: 60.0" in show_result.output
    assert "requests_per_second: 1.0" in show_result.output
    assert provider_show_result.exit_code == 0, provider_show_result.output
    assert "rate_limits: configured" in provider_show_result.output
    assert clear_result.exit_code == 0, clear_result.output
    assert "cleared rate limits for gateway" in clear_result.output
    assert show_after_clear.exit_code == 0, show_after_clear.output
    assert "rate_limits: none for gateway" in show_after_clear.output
    audit_events = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert [event["event"] for event in audit_events] == [
        "provider_rate_limits_changed",
        "provider_rate_limits_cleared",
    ]


def test_cli_evidence_bundle_writes_static_governance_zip(tmp_path) -> None:
    runner = CliRunner()
    suite_path = tmp_path / "suite.yaml"
    policy_path = tmp_path / "agentblaster.policy.yaml"
    output_dir = tmp_path / "evidence"
    audit_path = tmp_path / "evidence-audit.jsonl"
    suite_path.write_text(
        """
name: cli-evidence-suite
description: CLI evidence suite
cases:
  - id: cli-evidence-case
    title: CLI evidence case
    prompt: "Reply with exactly: agentblaster-ok"
""".lstrip(),
        encoding="utf-8",
    )
    policy_path.write_text("allow_remote_providers: false\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "evidence",
            "bundle",
            "--suite-file",
            str(suite_path),
            "--policy",
            str(policy_path),
            "--include-provider-audit",
            "--output-dir",
            str(output_dir),
            "--audit-log",
            str(audit_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "cli-evidence-suite.agentblaster-evidence.zip" in result.output
    assert (output_dir / "cli-evidence-suite.agentblaster-evidence.zip").exists()
    audit_event = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit_event["event"] == "evidence_bundle_created"
    assert audit_event["policy"] == str(policy_path)
    assert audit_event["include_provider_audit"] is True


def test_cli_policy_validate_writes_normalized_json(tmp_path) -> None:
    runner = CliRunner()
    policy_path = tmp_path / "agentblaster.policy.yaml"
    output_json = tmp_path / "policy.json"
    policy_path.write_text(
        "allow_remote_providers: false\nallowed_secret_ref_kinds:\n  - env\nmax_concurrency: 4\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["policy", "validate", str(policy_path), "--output-json", str(output_json)])

    assert result.exit_code == 0, result.output
    assert "valid: true" in result.output
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["allow_remote_providers"] is False
    assert payload["allowed_secret_ref_kinds"] == ["env"]
    assert payload["max_concurrency"] == 4


def test_cli_providers_audit_outputs_redacted_policy_findings(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "home"))
    runner = CliRunner()
    policy_path = tmp_path / "agentblaster.policy.yaml"
    output_json = tmp_path / "provider-audit.json"
    policy_path.write_text(
        "\n".join(
            [
                "allow_remote_providers: true",
                "require_api_key_for_remote_providers: true",
                "require_cleanup_audit_log: true",
                "allowed_secret_ref_kinds:",
                "  - env",
                "",
            ]
        ),
        encoding="utf-8",
    )

    add_result = runner.invoke(
        app,
        [
            "providers",
            "add",
            "--name",
            "remote-gateway",
            "--contract",
            "openai",
            "--base-url",
            "https://gateway.example.com/v1",
            "--remote",
        ],
    )
    audit_result = runner.invoke(
        app,
        ["providers", "audit", "--policy", str(policy_path), "--output-json", str(output_json)],
    )

    assert add_result.exit_code == 0, add_result.output
    assert audit_result.exit_code == 0, audit_result.output
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "agentblaster.provider-audit.v1"
    assert payload["total_providers"] == 1
    assert payload["remote_providers"] == 1
    assert payload["policy_ok"] == 0
    assert payload["policy_controls"]["require_cleanup_audit_log"] is True
    assert payload["secret_backend_posture"]["env_reference_portable"] is True
    assert payload["secret_backend_posture"]["keyring_optional"] is True
    assert isinstance(payload["secret_backend_posture"]["keyring_dependency_available"], bool)
    assert "require_cleanup_audit_log: true" in audit_result.output
    assert "keyring_dependency_available:" in audit_result.output
    provider = payload["providers"][0]
    assert provider["name"] == "remote-gateway"
    assert provider["api_key_ref_kind"] is None
    assert provider["api_key_ref_configured"] is False
    assert provider["api_key_ref_writable_backend"] is False
    assert provider["keyring_backend_required"] is False
    assert provider["keyring_dependency_available"] is None
    assert provider["prewrite_policy_guard_recommended"] is False
    assert any(finding["code"] == "policy_violation" for finding in provider["findings"])
    assert any(finding["code"] == "remote_without_cost_model" for finding in provider["findings"])
    assert "OPENAI_API_KEY" not in output_json.read_text(encoding="utf-8")


def test_cli_provider_audit_flags_plaintext_dotenv_secret_backend(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "home"))
    output_json = tmp_path / "provider-audit.json"
    dotenv_path = tmp_path / "dev.env"
    runner = CliRunner()

    add_result = runner.invoke(
        app,
        [
            "providers",
            "add",
            "--name",
            "remote-gateway",
            "--contract",
            "openai",
            "--base-url",
            "https://gateway.example.com/v1",
            "--remote",
        ],
    )
    auth_result = runner.invoke(
        app,
        [
            "providers",
            "auth",
            "set",
            "--provider",
            "remote-gateway",
            "--api-key-dotenv-file",
            str(dotenv_path),
            "--allow-plaintext-secret-file",
        ],
        input="super-secret\n",
    )
    audit_result = runner.invoke(app, ["providers", "audit", "--output-json", str(output_json)])

    assert add_result.exit_code == 0, add_result.output
    assert auth_result.exit_code == 0, auth_result.output
    assert audit_result.exit_code == 0, audit_result.output
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "agentblaster.provider-audit.v1"
    provider = payload["providers"][0]
    assert provider["api_key_ref_kind"] == "dotenv"
    assert provider["api_key_ref_writable_backend"] is True
    assert provider["api_key_ref_plaintext_fallback"] is True
    assert provider["keyring_backend_required"] is False
    assert provider["prewrite_policy_guard_recommended"] is True
    assert any(finding["code"] == "plaintext_dotenv_secret_backend" for finding in provider["findings"])
    assert "super-secret" not in output_json.read_text(encoding="utf-8")


def test_cli_compare_gate_fails_regression_and_writes_json(tmp_path) -> None:
    from agentblaster.models import BenchmarkResult

    def write_run(path: Path, run_id: str, latency_ms: float) -> None:
        path.mkdir()
        manifest = RunManifest(
            run_id=run_id,
            suite="smoke",
            provider="afm",
            contract=ApiContract.OPENAI,
            model="qwen-test",
            raw_trace_mode=RawTraceMode.OFF,
            created_at="2026-05-31T00:00:00Z",
            case_count=1,
        )
        result = BenchmarkResult(
            run_id=run_id,
            case_id="case-one",
            suite="smoke",
            provider="afm",
            contract=ApiContract.OPENAI,
            model="qwen-test",
            ok=True,
            latency_ms=latency_ms,
            message="ok",
        )
        (path / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
        (path / "results.jsonl").write_text(result.model_dump_json() + "\n", encoding="utf-8")

    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    output = tmp_path / "gate.json"
    write_run(baseline, "baseline", 100.0)
    write_run(candidate, "candidate", 130.0)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "compare-gate",
            str(baseline),
            str(candidate),
            "--max-avg-latency-regression-pct",
            "20",
            "--output-json",
            str(output),
        ],
    )

    assert result.exit_code == 1
    assert "ok: false" in result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "agentblaster.comparison-gate.v1"
    assert payload["ok"] is False
    assert payload["findings"][0]["metric"] == "avg_latency_ms"


def test_cli_matrix_gate_allows_final_response_tool_loop_stop_reason(tmp_path) -> None:
    runner = CliRunner()
    results_dir = tmp_path / "runs" / "agentic-loop"
    results_dir.mkdir(parents=True)
    (results_dir / "results.jsonl").write_text(
        (
            '{"ok": true, "tool_loop_enabled": true, "tool_loop_rounds": 2, '
            '"tool_loop_tool_call_count": 1, "tool_loop_max_tool_calls": 2, '
            '"tool_loop_stop_reason": "final_response"}\n'
            '{"ok": true, "tool_loop_enabled": true, "tool_loop_rounds": 2, '
            '"tool_loop_tool_call_count": 1, "tool_loop_max_tool_calls": 2, '
            '"tool_loop_stop_reason": "final_response"}\n'
        ),
        encoding="utf-8",
    )
    summary_path = tmp_path / "matrix-summary.json"
    output_json = tmp_path / "matrix-gate.json"
    summary_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "matrix_name": "agentic-tool-loop-release",
                "matrix_path": "examples/matrices/agentic-tool-loop.yaml",
                "created_at": "2026-05-31T00:00:00Z",
                "total_runs": 1,
                "attempted_runs": 1,
                "completed_runs": 1,
                "failed_runs": 0,
                "runs": [
                    {
                        "index": 1,
                        "engine": "afm",
                        "provider": "afm",
                        "model": "qwen-test",
                        "suite": "agentic-tool-loop",
                        "run_id": "agentic-loop",
                        "ok": True,
                        "total_cases": 2,
                        "passed": 2,
                        "failed": 0,
                        "concurrency": 1,
                        "results_path": "runs/agentic-loop/results.jsonl",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "matrix",
            "gate",
            str(summary_path),
            "--max-tool-loop-stop-reason",
            "max_tool_calls_reached=0",
            "--output-json",
            str(output_json),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "tool_loop_stop_reasons: final_response=2" in result.output
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["tool_loop_stop_summary"] == [{"stop_reason": "final_response", "count": 2}]
    assert payload["thresholds"]["max_tool_loop_stop_reason.max_tool_calls_reached"] == 0
    assert payload["findings"] == []


def test_cli_matrix_gate_fails_thresholds_and_writes_json(tmp_path) -> None:
    summary_path = tmp_path / "matrix-summary.json"
    output = tmp_path / "matrix-gate.json"
    summary_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "matrix_name": "release-matrix",
                "matrix_path": "examples/matrices/release.yaml",
                "created_at": "2026-05-31T00:00:00Z",
                "total_runs": 1,
                "attempted_runs": 1,
                "completed_runs": 1,
                "failed_runs": 1,
                "runs": [
                    {
                        "index": 1,
                        "engine": "afm",
                        "provider": "afm",
                        "model": "qwen-test",
                        "suite": "smoke",
                        "run_id": "run-a",
                        "ok": False,
                        "total_cases": 10,
                        "passed": 8,
                        "failed": 2,
                        "concurrency": 1,
                        "results_path": "runs/run-a/results.jsonl",
                        "manifest_path": "runs/run-a/manifest.json",
                        "summary_path": "runs/run-a/summary.json",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "matrix",
            "gate",
            str(summary_path),
            "--max-failed-runs",
            "0",
            "--min-case-pass-rate",
            "90",
            "--output-json",
            str(output),
        ],
    )

    assert result.exit_code == 1
    assert "ok: false" in result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert {finding["metric"] for finding in payload["findings"]} == {"failed_runs", "case_pass_rate"}


def test_cli_matrix_gate_fails_failure_class_threshold(tmp_path) -> None:
    results_dir = tmp_path / "runs" / "run-a"
    results_dir.mkdir(parents=True)
    (results_dir / "results.jsonl").write_text(
        '{"ok": false, "failure_class": "engine_protocol_bug"}\n',
        encoding="utf-8",
    )
    summary_path = tmp_path / "matrix-summary.json"
    output = tmp_path / "matrix-gate.json"
    summary_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "matrix_name": "release-matrix",
                "matrix_path": "examples/matrices/release.yaml",
                "created_at": "2026-05-31T00:00:00Z",
                "total_runs": 1,
                "attempted_runs": 1,
                "completed_runs": 1,
                "failed_runs": 0,
                "runs": [
                    {
                        "index": 1,
                        "engine": "afm",
                        "provider": "afm",
                        "model": "qwen-test",
                        "suite": "toolcall",
                        "run_id": "run-a",
                        "ok": True,
                        "total_cases": 1,
                        "passed": 0,
                        "failed": 1,
                        "concurrency": 1,
                        "results_path": "runs/run-a/results.jsonl",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "matrix",
            "gate",
            str(summary_path),
            "--max-failure-class",
            "engine_protocol_bug=0",
            "--output-json",
            str(output),
        ],
    )

    assert result.exit_code == 1
    assert "failure_classes: engine_protocol_bug=1" in result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["failure_class_summary"] == [{"failure_class": "engine_protocol_bug", "count": 1}]
    assert payload["findings"][0]["metric"] == "failure_class.engine_protocol_bug"


def test_cli_matrix_gate_fails_tool_loop_stop_reason_threshold(tmp_path) -> None:
    results_dir = tmp_path / "runs" / "run-a"
    results_dir.mkdir(parents=True)
    (results_dir / "results.jsonl").write_text(
        (
            '{"ok": false, "tool_loop_enabled": true, "tool_loop_rounds": 2, '
            '"tool_loop_tool_call_count": 2, "tool_loop_max_tool_calls": 2, '
            '"tool_loop_stop_reason": "max_tool_calls_reached"}\n'
        ),
        encoding="utf-8",
    )
    summary_path = tmp_path / "matrix-summary.json"
    output = tmp_path / "matrix-gate.json"
    summary_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "matrix_name": "release-matrix",
                "matrix_path": "examples/matrices/release.yaml",
                "created_at": "2026-05-31T00:00:00Z",
                "total_runs": 1,
                "attempted_runs": 1,
                "completed_runs": 1,
                "failed_runs": 0,
                "runs": [
                    {
                        "index": 1,
                        "engine": "afm",
                        "provider": "afm",
                        "model": "qwen-test",
                        "suite": "tool-loop",
                        "run_id": "run-a",
                        "ok": True,
                        "total_cases": 1,
                        "passed": 0,
                        "failed": 1,
                        "concurrency": 1,
                        "results_path": "runs/run-a/results.jsonl",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "matrix",
            "gate",
            str(summary_path),
            "--max-tool-loop-stop-reason",
            "max_tool_calls_reached=0",
            "--output-json",
            str(output),
        ],
    )

    assert result.exit_code == 1
    assert "tool_loop_stop_reasons: max_tool_calls_reached=1" in result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["tool_loop_stop_summary"] == [{"stop_reason": "max_tool_calls_reached", "count": 1}]
    assert payload["findings"][0]["metric"] == "tool_loop_stop_reason.max_tool_calls_reached"


def test_cli_matrix_gate_fails_judge_verdict_threshold(tmp_path) -> None:
    results_dir = tmp_path / "runs" / "run-a"
    results_dir.mkdir(parents=True)
    (results_dir / "results.jsonl").write_text(
        '{"ok": true, "judge_verdict_valid": true}\n'
        '{"ok": false, "judge_verdict_valid": false}\n',
        encoding="utf-8",
    )
    summary_path = tmp_path / "matrix-summary.json"
    output = tmp_path / "matrix-gate.json"
    summary_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "matrix_name": "release-matrix",
                "matrix_path": "examples/matrices/release.yaml",
                "created_at": "2026-05-31T00:00:00Z",
                "total_runs": 1,
                "attempted_runs": 1,
                "completed_runs": 1,
                "failed_runs": 0,
                "runs": [
                    {
                        "index": 1,
                        "engine": "afm",
                        "provider": "afm",
                        "model": "qwen-test",
                        "suite": "judge-rubric",
                        "run_id": "run-a",
                        "ok": True,
                        "total_cases": 2,
                        "passed": 1,
                        "failed": 1,
                        "concurrency": 1,
                        "results_path": "runs/run-a/results.jsonl",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "matrix",
            "gate",
            str(summary_path),
            "--min-judge-verdict-valid-rate",
            "75",
            "--output-json",
            str(output),
        ],
    )

    assert result.exit_code == 1
    assert "judge_verdicts_valid: 1/2" in result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["judge_rubric_cases"] == 2
    assert payload["judge_verdicts_valid"] == 1
    assert payload["judge_verdict_valid_rate_percent"] == 50.0
    assert payload["findings"][0]["metric"] == "judge_verdict_valid_rate"


def test_cli_matrix_gate_fails_tool_parser_repair_thresholds(tmp_path) -> None:
    results_dir = tmp_path / "runs" / "run-a"
    results_dir.mkdir(parents=True)
    (results_dir / "results.jsonl").write_text(
        '{"ok": true, "invalid_tool_call_count": 0, "tool_parser_repair_valid": true}\n'
        '{"ok": false, "invalid_tool_call_count": 1, "tool_parser_repair_valid": false}\n',
        encoding="utf-8",
    )
    summary_path = tmp_path / "matrix-summary.json"
    output = tmp_path / "matrix-gate.json"
    summary_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "matrix_name": "release-matrix",
                "matrix_path": "examples/matrices/release.yaml",
                "created_at": "2026-05-31T00:00:00Z",
                "total_runs": 1,
                "attempted_runs": 1,
                "completed_runs": 1,
                "failed_runs": 0,
                "runs": [
                    {
                        "index": 1,
                        "engine": "afm",
                        "provider": "afm",
                        "model": "qwen-test",
                        "suite": "tool-parser-repair",
                        "run_id": "run-a",
                        "ok": True,
                        "total_cases": 2,
                        "passed": 1,
                        "failed": 1,
                        "concurrency": 1,
                        "results_path": "runs/run-a/results.jsonl",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "matrix",
            "gate",
            str(summary_path),
            "--max-invalid-tool-calls",
            "0",
            "--min-tool-parser-repair-valid-rate",
            "75",
            "--output-json",
            str(output),
        ],
    )

    assert result.exit_code == 1
    assert "invalid_tool_call_count: 1" in result.output
    assert "tool_parser_repairs_valid: 1/2" in result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["invalid_tool_call_count"] == 1
    assert payload["tool_parser_repair_cases"] == 2
    assert payload["tool_parser_repairs_valid"] == 1
    assert payload["tool_parser_repair_valid_rate_percent"] == 50.0
    assert {finding["metric"] for finding in payload["findings"]} == {
        "invalid_tool_calls",
        "tool_parser_repair_valid_rate",
    }


def test_cli_release_qualification_bundle_writes_package_and_audit(tmp_path) -> None:
    runner = CliRunner()
    evidence = tmp_path / "suite.agentblaster-evidence.zip"
    matrix_gate = tmp_path / "matrix-gate.json"
    matrix_scorecard = tmp_path / "matrix-scorecard.json"
    implementation_status = tmp_path / "implementation-status.json"
    campaign_preflight = tmp_path / "campaign-preflight-manifest.json"
    harness_review = tmp_path / "harness-review.json"
    output_dir = tmp_path / "release-bundles"
    audit_path = tmp_path / "release-audit.jsonl"
    evidence.write_bytes(b"zip-data")
    matrix_gate.write_text('{"ok": true}\n', encoding="utf-8")
    matrix_scorecard.write_text(
        json.dumps(
            {
                "report_type": "agentblaster-matrix-scorecard-v1",
                "matrix": {"name": "qwen-gemma", "completed_runs": 1, "total_runs": 1, "failed_runs": 0},
                "scorecard": {
                    "entry_count": 1,
                    "result_artifacts_loaded": 1,
                    "total_cases": 1,
                    "passed_cases": 1,
                    "failed_cases": 0,
                    "pass_rate_percent": 100.0,
                    "telemetry_quality_summary": {"quality_counts": {"measured": 1}},
                    "concurrency_evidence": {"concurrency_levels": [1], "max_concurrency": 1},
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    harness_review.write_text('{"schema_version": "agentblaster.harness-review.v1"}\n', encoding="utf-8")
    implementation_status.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.implementation-status.v1",
                "status": "implementation-ready-for-validation",
                "implemented_areas": 9,
                "partial_areas": 0,
                "missing_areas": 0,
                "suite_inventory": {"built_in_suite_count": 8, "harness_engineering_cases": []},
                "requirements_inventory": {},
                "validation": {"tests_run_by_this_command": False},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    campaign_preflight.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.campaign-preflight-bundle.v1",
                "matrix_count": 1,
                "artifact_count": 2,
                "includes_provider_audit": False,
                "includes_benchmark_readiness": True,
                "benchmark_readiness": {
                    "artifact_path": "readiness/benchmark-readiness-index.json",
                    "report_count": 1,
                },
                "review_summary": {
                    "schema_version": "agentblaster.campaign-preflight-review-summary.v1",
                    "matrix_count": 1,
                    "run_count": 1,
                    "total_cases": 1,
                    "includes_provider_audit": False,
                    "includes_benchmark_readiness": True,
                    "benchmark_readiness_report_count": 1,
                    "security": {
                        "contains_local_paths": False,
                        "contains_raw_secrets": False,
                        "contains_raw_provider_payloads": False,
                        "contains_raw_traces": False,
                        "external_publication_safe": True,
                    },
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "release",
            "qualification-bundle",
            "--name",
            "afm-release",
            "--output-dir",
            str(output_dir),
            "--evidence-bundle",
            str(evidence),
            "--matrix-gate",
            str(matrix_gate),
            "--matrix-scorecard",
            str(matrix_scorecard),
            "--implementation-status",
            str(implementation_status),
            "--campaign-preflight-manifest",
            str(campaign_preflight),
            "--harness-review",
            str(harness_review),
            "--audit-log",
            str(audit_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "afm-release.agentblaster-release-qualification.zip" in result.output
    assert (output_dir / "afm-release.agentblaster-release-qualification.zip").exists()
    audit_event = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit_event["event"] == "release_qualification_bundle_created"
    assert audit_event["name"] == "afm-release"
    assert audit_event["matrix_scorecards"] == [str(matrix_scorecard)]
    assert audit_event["implementation_status_reports"] == [str(implementation_status)]
    assert audit_event["campaign_preflight_manifests"] == [str(campaign_preflight)]
    assert audit_event["harness_reviews"] == [str(harness_review)]


def test_cli_release_packaging_readiness_writes_report_and_can_fail(tmp_path) -> None:
    runner = CliRunner()
    output = tmp_path / "packaging-readiness.json"
    audit_path = tmp_path / "packaging-audit.jsonl"

    result = runner.invoke(
        app,
        [
            "release",
            "packaging-readiness",
            "--project-root",
            ".",
            "--output-json",
            str(output),
            "--audit-log",
            str(audit_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "AgentBlaster packaging readiness" in result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert payload["schema"] == "agentblaster.packaging-readiness"
    assert "checks" in payload
    assert audit["event"] == "packaging_readiness_created"
    assert audit["artifact"] == str(output)

    bad_root = tmp_path / "bad-project"
    bad_root.mkdir()
    (bad_root / "pyproject.toml").write_text(
        """
[project]
name = "agentblaster"
version = "0.1.0"

[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    fail_result = runner.invoke(
        app,
        [
            "release",
            "packaging-readiness",
            "--project-root",
            str(bad_root),
            "--fail-on-gaps",
        ],
    )

    assert fail_result.exit_code == 1
    assert "ok: false" in fail_result.output
    assert "FAIL required-project-fields" in fail_result.output


def test_cli_security_scan_fails_without_printing_secret(tmp_path) -> None:
    runner = CliRunner()
    artifact = tmp_path / "publication.json"
    output = tmp_path / "redaction-scan.json"
    artifact.write_text('{"api_key":"sk-testsecretvalue123456789"}\n', encoding="utf-8")

    result = runner.invoke(app, ["security", "scan", str(artifact), "--output-json", str(output)])

    assert result.exit_code == 1
    assert "ok: false" in result.output
    assert "openai_api_key" in result.output
    assert "sk-testsecretvalue" not in result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert payload["findings"][0]["pattern"] == "openai_api_key"
    assert "sk-testsecretvalue" not in output.read_text(encoding="utf-8")


def test_cli_policy_template_and_controls(tmp_path) -> None:
    runner = CliRunner()
    policy = tmp_path / "agentblaster.policy.yaml"
    template_json = tmp_path / "enterprise-policy-template.json"
    controls_json = tmp_path / "policy-control-summary.json"

    template_result = runner.invoke(
        app,
        [
            "policy",
            "template",
            "--profile",
            "local",
            "--output",
            str(policy),
            "--output-json",
            str(template_json),
        ],
    )
    controls_result = runner.invoke(
        app,
        [
            "policy",
            "controls",
            str(policy),
            "--name",
            "local-campaign",
            "--output-json",
            str(controls_json),
        ],
    )

    assert template_result.exit_code == 0, template_result.output
    assert policy.exists()
    assert template_json.exists()
    assert "allowed_secret_ref_kinds" in policy.read_text(encoding="utf-8")
    assert controls_result.exit_code == 0, controls_result.output
    assert "enterprise_ready: true" in controls_result.output
    assert controls_json.exists()
