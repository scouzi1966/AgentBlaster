from __future__ import annotations

import json
from zipfile import ZipFile

from agentblaster.evidence_index import build_evidence_index


def test_evidence_index_summarizes_provider_audit_without_secret_refs(tmp_path) -> None:
    provider_audit = tmp_path / "provider-audit.json"
    provider_audit.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.provider-audit.v1",
                "total_providers": 1,
                "remote_providers": 1,
                "policy_ok": 0,
                "errors": 1,
                "warnings": 1,
                "policy_controls": {"allow_remote_providers": True, "require_api_key_for_remote_providers": True},
                "secret_backend_posture": {
                    "env_reference_portable": True,
                    "keyring_optional": True,
                    "keyring_dependency_available": False,
                    "dotenv_plaintext_fallback_supported": True,
                    "dotenv_plaintext_fallback_enterprise_default": False,
                    "supported_secret_ref_kinds": ["env", "keyring", "dotenv"],
                    "recommended_enterprise_backends": ["env", "keyring"],
                },
                "providers": [
                    {
                        "name": "remote-openai",
                        "contract": "openai",
                        "base_url_host": "api.example.com",
                        "remote": True,
                        "api_key_ref_kind": "dotenv",
                        "api_key_ref_configured": True,
                        "api_key_ref_writable_backend": True,
                        "api_key_ref_plaintext_fallback": True,
                        "keyring_backend_required": False,
                        "keyring_dependency_available": None,
                        "prewrite_policy_guard_recommended": True,
                        "findings": [
                            {"severity": "error", "code": "policy_violation", "message": "secret name denied"},
                            {"severity": "warning", "code": "plaintext_dotenv_secret_backend", "message": "dev only"},
                        ],
                    }
                ],
                "security_notes": ["no secret values"],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    report = build_evidence_index(name="provider-security", artifacts=[provider_audit])
    entry = report["artifacts"][0]
    summary = entry["review_summary"]

    assert entry["status"] == "fail"
    assert entry["status_source"] == "provider-audit.errors"
    assert summary["schema_version"] == "agentblaster.provider-audit.v1"
    assert summary["error_count"] == 1
    assert summary["plaintext_dotenv_provider_count"] == 1
    assert summary["keyring_required_provider_count"] == 0
    assert summary["secret_backend_posture"]["keyring_dependency_available"] is False
    assert summary["provider_auth_posture"][0]["api_key_ref_kind"] == "dotenv"
    assert "policy_violation" in summary["finding_codes"]
    assert "secret name denied" not in json.dumps(summary)


def test_evidence_index_summarizes_normalized_telemetry_without_raw_stats(tmp_path) -> None:
    telemetry = tmp_path / "provider-normalized-telemetry.json"
    telemetry.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.normalized-telemetry.v1",
                "contract": "openai",
                "native_adapter": "rapid-mlx",
                "stats_profile": "rapid-mlx-openai-compatible",
                "values": {
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "prompt_eval_ms": 500.0,
                    "tokens_per_second_prefill": 200.0,
                    "raw_stats": {"private_provider_debug": "do-not-copy"},
                },
                "sources": {"prompt_eval_ms": "stats/metrics.prefill_seconds"},
                "quality": {
                    "input_tokens": "native",
                    "output_tokens": "native",
                    "prompt_eval_ms": "native",
                    "tokens_per_second_prefill": "inferred",
                    "raw_stats": "raw_provenance",
                },
                "comparison_readiness": {
                    "publication_grade_field_count": 3,
                    "advisory_field_count": 1,
                    "raw_provenance_field_count": 1,
                    "guidance": "label-inferred-or-conditional-fields-before-cross-engine-comparison",
                },
                "stats_comparability": {
                    "requires_labeling": True,
                    "guidance": "publish-native-and-measured-fields-separately-from-inferred-conditional-or-missing-stats",
                    "publication_grade_fields": ["prompt_eval_ms"],
                    "advisory_fields": ["tokens_per_second_prefill"],
                    "missing_stats_fields": ["decode_ms"],
                },
                "missing": ["decode_ms"],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    report = build_evidence_index(name="telemetry-review", artifacts=[telemetry])
    summary = report["artifacts"][0]["review_summary"]

    assert report["artifacts"][0]["status"] == "review"
    assert summary["schema_version"] == "agentblaster.normalized-telemetry.v1"
    assert summary["stats_profile"] == "rapid-mlx-openai-compatible"
    assert summary["advisory_field_count"] == 1
    assert summary["stats_requires_labeling"] is True
    assert summary["stats_advisory_fields"] == ["tokens_per_second_prefill"]
    assert "private_provider_debug" not in json.dumps(summary)
    assert "sources" not in json.dumps(summary)


def test_evidence_index_summarizes_implementation_status_without_local_paths(tmp_path) -> None:
    implementation_status = tmp_path / "implementation-status.json"
    implementation_status.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.implementation-status.v1",
                "generated_at": "2026-06-01T00:00:00Z",
                "project_root": "/private/worktrees/AgentBlaster",
                "status": "implementation-ready-for-validation",
                "implemented_areas": 9,
                "partial_areas": 0,
                "missing_areas": 0,
                "areas": [
                    {
                        "id": "reporting-publication",
                        "evidence": ["/private/worktrees/AgentBlaster/src/agentblaster/reports.py"],
                    }
                ],
                "suite_inventory": {
                    "built_in_suite_count": 8,
                    "built_in_suites": ["smoke", "harness-engineering"],
                    "harness_engineering_suite_present": True,
                    "harness_engineering_cases": [
                        "harness-contract-streaming-sentinel",
                        "harness-metamorphic-equivalent-wrapper",
                        "harness-cache-replay-static-prefix",
                        "harness-judge-rubric-json",
                    ],
                },
                "requirements_inventory": {
                    "target_engines": {"count": 12},
                    "provider_contracts": {"preset_count": 10},
                    "model_targets": {"catalog_count": 2, "initial_targets_present": True},
                    "agentic_workflows": {"profile_count": 4},
                    "harness_engineering": {"profile_count": 6},
                    "stats_comparability": {
                        "profile_count": 8,
                        "metric_provider_count": 11,
                        "publication_requires_labels_for_non_native_stats": True,
                    },
                    "enterprise_controls": {
                        "keyring_optional": True,
                        "secret_backends": ["env", "keyring", "dotenv"],
                    },
                    "publication_governance": {
                        "redaction_safe_summary_consumers": ["release qualification", "claim readiness"],
                    },
                    "selftest_harness": {
                        "report_schema": "agentblaster.selftest-report.v1",
                        "chrome_codex_gate_present": True,
                    },
                },
                "validation": {
                    "tests_run_by_this_command": False,
                    "required_next_step": "Run explicit validation/selftest before claiming completion or release readiness.",
                },
                "security_notes": ["does not contact providers"],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    report = build_evidence_index(name="implementation-review", artifacts=[implementation_status])

    summary = report["artifacts"][0]["review_summary"]
    assert summary["schema_version"] == "agentblaster.implementation-status.v1"
    assert summary["status"] == "implementation-ready-for-validation"
    assert summary["implementation_status"] == "implementation-ready-for-validation"
    assert summary["harness_engineering_case_count"] == 4
    assert summary["stats_profile_count"] == 8
    assert summary["stats_metric_provider_count"] == 11
    assert summary["stats_publication_requires_labels"] is True
    assert summary["keyring_optional"] is True
    assert summary["secret_backends"] == ["env", "keyring", "dotenv"]
    assert summary["chrome_codex_gate_present"] is True
    assert summary["tests_run_by_this_command"] is False
    assert summary["shareable_summary_only"] is True
    assert "/private/worktrees" not in json.dumps(summary)


def test_evidence_index_summarizes_campaign_preflight_manifest_without_local_paths(tmp_path) -> None:
    manifest = tmp_path / "campaign-preflight" / "qwen-gemma-local" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.campaign-preflight-bundle.v1",
                "output_dir": str(tmp_path / "campaign-preflight" / "qwen-gemma-local"),
                "matrix_count": 1,
                "artifact_count": 4,
                "includes_provider_audit": False,
                "includes_benchmark_readiness": True,
                "benchmark_readiness": {
                    "artifact_path": "readiness/benchmark-readiness-index.json",
                    "report_count": 1,
                },
                "matrices": [
                    {
                        "matrix": "qwen-gemma-local",
                        "matrix_path": str(tmp_path / "matrices" / "qwen-gemma-local.yaml"),
                        "dry_run_command": [
                            "agentblaster",
                            "run",
                            "--matrix",
                            str(tmp_path / "matrices" / "qwen-gemma-local.yaml"),
                        ],
                    }
                ],
                "review_summary": {
                    "schema_version": "agentblaster.campaign-preflight-review-summary.v1",
                    "matrix_count": 1,
                    "run_count": 2,
                    "total_cases": 8,
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
                "security": {
                    "contacts_providers": False,
                    "resolves_secrets": False,
                    "contains_local_paths": True,
                    "external_publication_safe": False,
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    report = build_evidence_index(name="campaign-review", artifacts=[manifest])

    entry = report["artifacts"][0]
    summary = entry["review_summary"]
    assert report["security"]["redacts_artifact_paths"] is True
    assert entry["path"] == "manifest.json"
    assert entry["path_redacted"] is True
    assert entry["schema"] == "agentblaster.campaign-preflight-bundle.v1"
    assert entry["status"] == "review"
    assert summary["schema_version"] == "agentblaster.campaign-preflight-bundle.v1"
    assert summary["review_summary_schema_version"] == "agentblaster.campaign-preflight-review-summary.v1"
    assert summary["matrix_count"] == 1
    assert summary["run_count"] == 2
    assert summary["total_cases"] == 8
    assert summary["benchmark_readiness_report_count"] == 1
    assert summary["contains_local_paths"] is False
    assert summary["external_publication_safe"] is True
    assert str(tmp_path) not in json.dumps(entry)


def test_evidence_index_summarizes_cleanup_reports_without_paths(tmp_path) -> None:
    manual_cleanup = tmp_path / "manual-cleanup-plan.json"
    retention_cleanup = tmp_path / "retention-cleanup-plan.json"
    manual_cleanup.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.cleanup-plan.v1",
                "report_type": "manual_cleanup_plan",
                "generated_at": "2026-06-01T00:00:00Z",
                "run_dir": "/private/runs/run-1",
                "execute": False,
                "selectors": {
                    "raw": True,
                    "reports": True,
                    "exports": False,
                    "caches": True,
                    "temp": False,
                    "bundles": True,
                    "all_artifacts": False,
                },
                "action_count": 4,
                "paths": [
                    "/private/runs/run-1/raw",
                    "/private/runs/run-1/cache",
                ],
                "security": {
                    "contains_raw_secrets": False,
                    "contains_raw_provider_payloads": False,
                    "reads_keyring_values": False,
                    "contacts_providers": False,
                    "dry_run_default": True,
                    "contains_local_paths": True,
                    "direct_publication_safe": False,
                    "audit_log_required": True,
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    retention_cleanup.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.retention-cleanup.v1",
                "report_type": "retention_cleanup_plan",
                "generated_at": "2026-06-01T00:00:00Z",
                "runs_dir": "/private/runs",
                "execute": False,
                "action_count": 2,
                "actions": [
                    {"action": "raw", "run_id": "run-a"},
                    {"action": "run", "run_id": "run-b"},
                ],
                "security": {
                    "contains_raw_secrets": False,
                    "contains_raw_provider_payloads": False,
                    "reads_keyring_values": False,
                    "contacts_providers": False,
                    "dry_run_default": True,
                    "contains_local_paths": True,
                    "direct_publication_safe": False,
                    "audit_log_required": True,
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    report = build_evidence_index(name="cleanup-review", artifacts=[manual_cleanup, retention_cleanup])

    assert report["status_counts"] == {"review": 2}
    assert report["cleanup_evidence"] == {
        "artifact_count": 2,
        "manual_report_count": 1,
        "retention_report_count": 1,
        "planned_report_count": 2,
        "executed_report_count": 0,
        "audit_log_required_count": 2,
        "contains_local_paths": True,
        "direct_publication_safe": False,
        "shareable_summary_only": True,
    }
    summaries = [artifact["review_summary"] for artifact in report["artifacts"]]
    assert summaries[0]["schema_version"] == "agentblaster.cleanup-plan.v1"
    assert summaries[0]["selector_count"] == 4
    assert summaries[0]["contains_raw_provider_payloads"] is False
    assert summaries[0]["contains_local_paths"] is True
    assert summaries[0]["direct_publication_safe"] is False
    assert summaries[0]["audit_log_required"] is True
    assert summaries[1]["schema_version"] == "agentblaster.retention-cleanup.v1"
    assert summaries[1]["action_types"] == ["raw", "run"]
    assert summaries[1]["audit_log_required"] is True
    assert "/private/runs/run-1/raw" not in json.dumps(summaries)


def test_evidence_index_summarizes_publication_brief_and_sdlc_manifest(tmp_path) -> None:
    publication_brief = tmp_path / "publication-brief.json"
    sdlc_manifest = tmp_path / "sdlc-validation-manifest.json"
    publication_brief.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.publication-brief.v1",
                "name": "qwen-gemma-release-brief",
                "ready": True,
                "claim_readiness": {"checks": 8, "blockers": 0, "warnings": 1},
                "proof_points": [{"claim": "tool loops complete"}, {"claim": "prefill pressure measured"}],
                "disclosures": [{"kind": "stats-labeling"}],
                "matrix_scorecards": [{"matrix": "qwen-gemma-local"}],
                "engine_targets": [
                    {"id": "afm-mlx", "display_name": "AFM MLX", "primary_scoring_contract": "openai"}
                ],
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
                "security": {
                    "source_artifact_count": 5,
                    "contains_raw_provider_payloads": False,
                    "contains_secrets": False,
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    sdlc_manifest.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.sdlc-validation-manifest.v1",
                "name": "local-dev-validation",
                "summary": {
                    "tier_count": 4,
                    "required_gate_count": 7,
                    "blocking_gate_count": 3,
                    "chrome_flow_count": 2,
                    "chrome_validation_step_count": 9,
                },
                "gui": {
                    "chrome_tool": "Chrome Codes plugin",
                    "stable_selectors": ["review-artifacts-panel", "review-artifacts-table"],
                    "api_surfaces": ["/api/review-artifacts", "/api/review-artifacts/<path>"],
                },
                "release_evidence": {
                    "expected_artifacts": ["selftest-report.json", "publication-brief.json"],
                },
                "security": {
                    "runs_tests": False,
                    "contacts_providers": False,
                    "contains_raw_provider_payloads": False,
                    "contains_secrets": False,
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    report = build_evidence_index(name="release-handoff", artifacts=[publication_brief, sdlc_manifest])
    artifacts = {artifact["schema"]: artifact for artifact in report["artifacts"]}

    publication = artifacts["agentblaster.publication-brief.v1"]
    assert publication["status"] == "pass"
    assert publication["status_source"] == "publication-brief.ready"
    assert publication["review_summary"]["proof_point_count"] == 2
    assert publication["review_summary"]["claim_warnings"] == 1
    assert publication["review_summary"]["engine_targets"] == [
        {"id": "afm-mlx", "display_name": "AFM MLX", "primary_scoring_contract": "openai"}
    ]
    assert publication["review_summary"]["architecture_summary"][0]["model_architecture"] == "qwen3.6-dense"
    assert publication["review_summary"]["quantization_summary"][0]["quantization"] == "mlx-f16"
    assert publication["review_summary"]["shareable_summary_only"] is True
    sdlc = artifacts["agentblaster.sdlc-validation-manifest.v1"]
    assert sdlc["status"] == "review"
    assert sdlc["status_source"] == "sdlc-validation-manifest.static"
    assert sdlc["review_summary"]["chrome_validation_step_count"] == 9
    assert sdlc["review_summary"]["expected_artifact_count"] == 2
    assert sdlc["review_summary"]["contains_raw_provider_payloads"] is False
    assert "sk-" not in json.dumps(report)


def test_evidence_index_summarizes_release_embedded_publication_brief_and_sdlc_manifest(tmp_path) -> None:
    bundle = tmp_path / "release.agentblaster-release-qualification.zip"
    manifest = {
        "schema": "agentblaster.release-qualification-bundle",
        "schema_version": 1,
        "ok": True,
        "artifact_status": {"pass": 1, "review": 1},
        "artifacts": [
            {
                "category": "publication/brief",
                "archive_path": "publication/brief/publication-brief.json",
                "status": "pass",
                "review_summary": {
                    "schema_version": "agentblaster.publication-brief.v1",
                    "name": "afm-release",
                    "ready": True,
                    "status": "pass",
                    "source_artifact_count": 4,
                    "proof_point_count": 2,
                    "disclosure_count": 1,
                    "matrix_scorecard_count": 1,
                    "engine_targets": [
                        {"id": "afm-mlx", "display_name": "AFM MLX", "primary_scoring_contract": "openai"}
                    ],
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
                    "claim_checks": 8,
                    "claim_blockers": 0,
                    "claim_warnings": 1,
                    "contains_raw_provider_payloads": False,
                    "contains_secrets": False,
                    "shareable_summary_only": True,
                },
            },
            {
                "category": "selftest/validation-manifest",
                "archive_path": "selftest/sdlc-validation-manifest.json",
                "status": "review",
                "review_summary": {
                    "schema_version": "agentblaster.sdlc-validation-manifest.v1",
                    "name": "sdlc-validation-manifest.json",
                    "status": "review",
                    "tier_count": 4,
                    "required_gate_count": 7,
                    "blocking_gate_count": 3,
                    "chrome_flow_count": 2,
                    "chrome_validation_step_count": 9,
                    "chrome_tool": "Codex Chrome plugin",
                    "stable_selector_count": 2,
                    "api_surface_count": 2,
                    "expected_artifact_count": 4,
                    "runs_tests": False,
                    "contacts_providers": False,
                    "contains_raw_provider_payloads": False,
                    "contains_secrets": False,
                    "shareable_summary_only": True,
                },
            },
        ],
    }
    with ZipFile(bundle, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True) + "\n")

    report = build_evidence_index(name="release-review", artifacts=[bundle])
    summaries = report["artifacts"][0]["review_summaries"]

    publication = next(summary for summary in summaries if summary["category"] == "publication/brief")
    assert publication["proof_point_count"] == 2
    assert publication["claim_warnings"] == 1
    sdlc = next(summary for summary in summaries if summary["category"] == "selftest/validation-manifest")
    assert sdlc["chrome_validation_step_count"] == 9
    assert sdlc["expected_artifact_count"] == 4
    assert "not copied" not in json.dumps(report)


def test_evidence_index_summarizes_matrix_scorecard_model_family_rollups(tmp_path) -> None:
    scorecard = tmp_path / "qwen-gemma-matrix-scorecard.json"
    scorecard.write_text(
        json.dumps(
            {
                "report_type": "agentblaster-matrix-scorecard-v1",
                "matrix": {"name": "qwen-gemma-local", "completed_runs": 2, "total_runs": 2, "failed_runs": 0},
                "scorecard": {
                    "entry_count": 2,
                    "result_artifacts_loaded": 2,
                    "total_cases": 10,
                    "passed_cases": 10,
                    "failed_cases": 0,
                    "pass_rate_percent": 100.0,
                    "engine_targets": [
                        {"id": "afm-mlx", "display_name": "AFM MLX", "primary_scoring_contract": "openai"}
                    ],
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
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    report = build_evidence_index(name="matrix-scorecard", artifacts=[scorecard])
    entry = report["artifacts"][0]

    assert entry["status"] == "pass"
    assert entry["review_summary"]["engine_targets"][0]["id"] == "afm-mlx"
    assert entry["review_summary"]["architecture_summary"][0]["model_architecture"] == "qwen3.6-dense"
    assert entry["review_summary"]["quantization_summary"][0]["quantization"] == "mlx-f16"


def test_evidence_index_summarizes_matrix_publication_bundle_manifest(tmp_path) -> None:
    bundle = tmp_path / "qwen-gemma.agentblaster-matrix-publication.zip"
    manifest = {
        "schema_version": "agentblaster.matrix-publication-bundle.v1",
        "matrix": {
            "artifact_stem": "qwen-gemma",
            "summary_artifact": "qwen-gemma.json",
            "scorecard_artifact": "qwen-gemma-matrix-scorecard.json",
        },
        "engine_targets": [
            {"id": "afm-mlx", "display_name": "AFM MLX", "primary_scoring_contract": "openai"},
        ],
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
        "artifact_count": 3,
        "artifacts": ["qwen-gemma.json", "qwen-gemma-matrix-scorecard.json", "qwen-gemma-matrix-scorecard.svg"],
        "media_kit": {
            "schema_version": "agentblaster.media-kit.v1",
            "asset_count": 3,
            "missing_recommended_assets": [],
            "recommended_sets": [{"name": "media-post-packet", "available": True}],
            "assets": [
                {
                    "artifact": "qwen-gemma-matrix-scorecard.svg",
                    "role": "scorecard-card-vector",
                    "media_type": "image/svg+xml",
                    "present": True,
                }
            ],
        },
        "security": {
            "contains_raw_secrets": False,
            "contains_raw_provider_payloads": False,
            "contains_results_jsonl": False,
            "contains_per_run_raw_traces": False,
        },
    }
    with ZipFile(bundle, "w") as archive:
        archive.writestr("matrix-publication-bundle-manifest.json", json.dumps(manifest, sort_keys=True) + "\n")

    report = build_evidence_index(name="matrix-publication", artifacts=[bundle])
    entry = report["artifacts"][0]

    assert entry["schema"] == "agentblaster.matrix-publication-bundle.v1"
    assert entry["status"] == "pass"
    assert entry["review_summary"]["matrix"]["artifact_stem"] == "qwen-gemma"
    assert entry["review_summary"]["engine_targets"] == [
        {"id": "afm-mlx", "display_name": "AFM MLX", "primary_scoring_contract": "openai"}
    ]
    assert entry["review_summary"]["architecture_summary"][0]["model_architecture"] == "qwen3.6-dense"
    assert entry["review_summary"]["quantization_summary"][0]["quantization"] == "mlx-f16"
    assert entry["review_summary"]["media_kit"]["missing_recommended_assets"] == []
    assert entry["review_summary"]["security"]["contains_results_jsonl"] is False
