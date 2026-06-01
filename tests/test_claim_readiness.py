from __future__ import annotations

import json
from zipfile import ZIP_DEFLATED, ZipFile

from typer.testing import CliRunner

from agentblaster.claim_readiness import build_claim_readiness, format_claim_readiness, write_claim_readiness_json
from agentblaster.cli import app


def _write_json(path, payload) -> None:
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _scorecard_review_summary() -> dict:
    return {
        "schema_version": "agentblaster-matrix-scorecard-v1",
        "matrix": "qwen-gemma-local",
        "completed_runs": 2,
        "total_runs": 2,
        "failed_runs": 0,
        "entry_count": 2,
        "result_artifacts_loaded": 2,
        "total_cases": 10,
        "passed_cases": 10,
        "failed_cases": 0,
        "pass_rate_percent": 100.0,
        "invalid_tool_call_count": 0,
        "tool_parser_repair_cases": 2,
        "tool_parser_repairs_valid": 2,
        "tool_parser_repair_valid_rate_percent": 100.0,
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
                "invalid_tool_call_count": 0,
                "tool_parser_repair_cases": 2,
                "tool_parser_repairs_valid": 2,
                "tool_parser_repair_valid_rate_percent": 100.0,
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
                "invalid_tool_call_count": 0,
                "tool_parser_repair_cases": 2,
                "tool_parser_repairs_valid": 2,
                "tool_parser_repair_valid_rate_percent": 100.0,
            }
        ],
        "judge_rubric_cases": 2,
        "judge_verdicts_valid": 2,
        "failure_class_summary": [],
        "tool_loop_stop_summary": [{"stop_reason": "final_response", "count": 2}],
        "telemetry_quality_summary": {
            "quality_counts": {"native": 3, "measured": 9},
            "guidance_counts": {},
            "entries_with_advisory_quality": 0,
            "entries_with_unknown_quality": 0,
            "entries_with_comparison_guidance": 0,
        },
        "concurrency_evidence": {
            "schema_version": "agentblaster.scorecard-concurrency-evidence.v1",
            "entry_count": 2,
            "artifact_loaded_count": 2,
            "concurrency_levels": [1, 4],
            "multi_level": True,
            "max_concurrency": 4,
            "max_avg_queue_ms": 0.0,
            "max_avg_rate_limit_wait_ms": 0.0,
            "guidance": "concurrency-evidence-ready-when-release-gates-pass",
            "highest_queue_wait_entries": [],
            "highest_rate_limit_wait_entries": [],
        },
    }


def _benchmark_readiness_review_summary() -> dict:
    return {
        "schema_version": "agentblaster.benchmark-readiness.v1",
        "provider": "afm",
        "suite": "agentic-local",
        "model": "mlx-community/Qwen3.6-27B",
        "ready": True,
        "strict_unknown": True,
        "policy_ok": True,
        "suite_compatible": True,
        "contract_checks_planned": 5,
        "contract_capabilities_directly_checked": 3,
        "contract_capabilities_proxy_checked": 1,
        "contract_capabilities_not_covered": 1,
        "metric_coverage_score": 0.95,
        "provider_auth_writable_backends": 1,
        "provider_auth_plaintext_fallbacks": 1,
        "provider_auth_prewrite_policy_guards_recommended": 1,
        "blocking_findings": 0,
        "warnings": 1,
        "provider_auth_posture": [
            {
                "provider": "afm",
                "api_key_ref_kind": "dotenv",
                "api_key_ref_configured": True,
                "api_key_ref_writable_backend": True,
                "api_key_ref_plaintext_fallback": True,
                "prewrite_policy_guard_recommended": True,
            }
        ],
    }


def _normalized_telemetry_review_summary() -> dict:
    return {
        "schema_version": "agentblaster.normalized-telemetry.v1",
        "contract": "openai",
        "native_adapter": "afm-mlx",
        "stats_profile": "afm-mlx-openai-compatible",
        "populated_field_count": 9,
        "missing_field_count": 6,
        "publication_grade_field_count": 8,
        "advisory_field_count": 0,
        "raw_provenance_field_count": 0,
        "comparison_guidance": "publication-grade-for-present-fields-when-run-telemetry-audit-passes",
        "quality_counts": {"native": 9},
        "stats_requires_labeling": False,
        "stats_guidance": "stats-fields-ready-for-like-for-like-comparison",
        "stats_publication_grade_fields": [
            "ttft_ms",
            "prompt_eval_ms",
            "decode_ms",
            "tokens_per_second_prefill",
            "tokens_per_second_decode",
            "cached_input_tokens",
        ],
        "stats_advisory_fields": [],
        "missing_stats_fields": [],
    }


def test_claim_readiness_surfaces_provider_audit_security_posture(tmp_path) -> None:
    provider_audit = tmp_path / "provider-audit.json"
    _write_json(
        provider_audit,
        {
            "schema_version": "agentblaster.provider-audit.v1",
            "total_providers": 1,
            "remote_providers": 1,
            "policy_ok": 1,
            "errors": 0,
            "warnings": 1,
            "policy_controls": {"allow_remote_providers": True},
            "secret_backend_posture": {
                "env_reference_portable": True,
                "keyring_optional": True,
                "keyring_dependency_available": True,
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
                    "api_key_ref_kind": "keyring",
                    "api_key_ref_configured": True,
                    "api_key_ref_writable_backend": True,
                    "api_key_ref_plaintext_fallback": False,
                    "keyring_backend_required": True,
                    "keyring_dependency_available": True,
                    "prewrite_policy_guard_recommended": True,
                    "findings": [
                        {"severity": "warning", "code": "remote_without_rate_limits", "message": "do not copy"}
                    ],
                }
            ],
            "security_notes": ["does not resolve secrets"],
        },
    )

    report = build_claim_readiness(name="provider-security", provider_audits=[provider_audit])
    formatted = format_claim_readiness(report)

    summary = report["evidence"]["provider_audit_summaries"][0]
    assert summary["schema_version"] == "agentblaster.provider-audit.v1"
    assert summary["warning_count"] == 1
    assert summary["writable_secret_backend_count"] == 1
    assert summary["keyring_required_provider_count"] == 1
    assert summary["secret_backend_posture"]["keyring_optional"] is True
    assert summary["provider_auth_posture"][0]["api_key_ref_kind"] == "keyring"
    assert "remote_without_rate_limits" in summary["finding_codes"]
    assert "do not copy" not in json.dumps(summary)
    assert "provider_audits: provider-audit.json=remote:1,errors:0,warnings:1,writable:1,plaintext:0" in formatted


def _write_release_bundle(
    path,
    *,
    ok: bool = True,
    publication_review: bool = False,
    publication_brief_review: bool = False,
    matrix_scorecard_review: bool = True,
    selftest_review: bool = True,
    sdlc_validation_manifest_review: bool = False,
    benchmark_readiness_review: bool = True,
    benchmark_readiness_ready: bool = True,
    implementation_status_review: bool = False,
    implementation_status_ready: bool = True,
    campaign_preflight_review: bool = False,
    normalized_telemetry_review: bool = True,
) -> None:
    manifest = {
        "schema": "agentblaster.release-qualification-bundle",
        "schema_version": 1,
        "ok": ok,
        "artifact_status": {"pass": 1} if ok else {"fail": 1},
    }
    artifacts = []
    if publication_review:
        artifacts.append(
            {
            "category": "publication",
            "archive_path": "publication/run.agentblaster-publication.zip",
            "status": "review",
            "review_summary": {
                "schema_version": "agentblaster.publication-bundle.v1",
                "run_id": "run-release",
                "artifact_count": 4,
                "artifacts": ["summary.json", "publication.json", "report-card.svg", "integrity.json"],
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
        )
    if publication_brief_review:
        artifacts.append(
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
            }
        )
    if matrix_scorecard_review:
        artifacts.append(
            {
                "category": "reports/matrix-scorecard",
                "archive_path": "reports/matrix-scorecard/qwen-gemma-matrix-scorecard.json",
                "status": "pass",
                "review_summary": _scorecard_review_summary(),
            }
        )
    if selftest_review:
        artifacts.append(
            {
                "category": "selftest",
                "archive_path": "selftest/selftest-report.json",
                "status": "pass",
                "review_summary": {
                    "schema_version": "agentblaster.selftest-report.v1",
                    "run_id": "selftest_20260531T000000Z",
                    "tier": "normal",
                    "ok": True,
                    "exit_code": 0,
                    "duration_ms": 1000.0,
                    "marker_expression": "not remote and not slow and not gui",
                    "junit_xml_present": True,
                },
            }
        )
    if sdlc_validation_manifest_review:
        artifacts.append(
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
            }
        )
    if benchmark_readiness_review:
        readiness_summary = _benchmark_readiness_review_summary()
        readiness_summary["ready"] = benchmark_readiness_ready
        readiness_summary["blocking_findings"] = 0 if benchmark_readiness_ready else 1
        artifacts.append(
            {
                "category": "readiness/benchmark",
                "archive_path": "readiness/benchmark/afm-readiness.json",
                "status": "pass" if benchmark_readiness_ready else "review",
                "review_summary": readiness_summary,
            }
        )
    if normalized_telemetry_review:
        artifacts.append(
            {
                "category": "metrics/normalized-telemetry",
                "archive_path": "metrics/normalized-telemetry/afm-normalized-telemetry.json",
                "status": "review",
                "review_summary": _normalized_telemetry_review_summary(),
            }
        )
    if implementation_status_review:
        artifacts.append(
            {
                "category": "readiness/implementation",
                "archive_path": "readiness/implementation/implementation-status.json",
                "status": "pass" if implementation_status_ready else "fail",
                "review_summary": {
                    "schema_version": "agentblaster.implementation-status.v1",
                    "status": "implementation-ready-for-validation"
                    if implementation_status_ready
                    else "implementation-incomplete",
                    "implemented_areas": 8 if implementation_status_ready else 7,
                    "partial_areas": 0,
                    "missing_areas": 0 if implementation_status_ready else 1,
                    "harness_engineering_case_count": 4,
                    "stats_profile_count": 8,
                    "shareable_summary_only": True,
                },
            }
        )
    if campaign_preflight_review:
        artifacts.append(
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
            }
        )
    if artifacts:
        manifest["artifacts"] = artifacts
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True) + "\n")


def _write_publication_bundle(
    path,
    *,
    status: str = "ready",
    contains_results_jsonl: bool = False,
    missing_media_assets: list[str] | None = None,
) -> None:
    missing_media_assets = missing_media_assets or []
    readiness = {
        "schema_version": "agentblaster.publication-readiness.v1",
        "status": status,
        "ready_for_external_publication": status == "ready",
        "ready_for_internal_review": status != "blocked",
        "blocker_count": 1 if status == "blocked" else 0,
        "warning_count": 1 if status == "review-required" else 0,
    }
    manifest = {
        "schema_version": "agentblaster.publication-bundle.v1",
        "run_id": "run-123",
        "artifact_count": 4,
        "artifacts": ["summary.json", "publication.json", "report-card.svg", "integrity.json"],
        "media_kit": {
            "schema_version": "agentblaster.media-kit.v1",
            "asset_count": 4,
            "missing_recommended_assets": missing_media_assets,
            "recommended_sets": [{"name": "corporate-review-packet", "available": not missing_media_assets}],
            "assets": [
                {"artifact": "publication.json", "role": "structured-run-evidence", "media_type": "application/json", "present": True},
                {"artifact": "report-card.svg", "role": "social-card-vector", "media_type": "image/svg+xml", "present": True},
            ],
        },
        "publication_readiness": readiness,
        "security": {
            "contains_raw_secrets": False,
            "contains_raw_provider_payloads": False,
            "contains_results_jsonl": contains_results_jsonl,
        },
    }
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("publication-bundle-manifest.json", json.dumps(manifest, sort_keys=True) + "\n")


def _write_matrix_publication_bundle(path, *, missing_assets: list[str] | None = None) -> None:
    missing = missing_assets or []
    stem = "qwen-gemma"
    manifest = {
        "schema_version": "agentblaster.matrix-publication-bundle.v1",
        "matrix": {
            "artifact_stem": stem,
            "summary_artifact": f"{stem}.json",
            "scorecard_artifact": f"{stem}-matrix-scorecard.json",
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
        "artifact_count": 4,
        "artifacts": [
            f"{stem}.json",
            f"{stem}-matrix-scorecard.json",
            f"{stem}-matrix-scorecard.pdf",
            f"{stem}-matrix-scorecard.svg",
        ],
        "media_kit": {
            "schema_version": "agentblaster.media-kit.v1",
            "asset_count": 4,
            "missing_recommended_assets": missing,
            "recommended_sets": [{"name": "corporate-review-packet", "available": not missing}],
            "assets": [
                {"artifact": f"{stem}-matrix-scorecard.json", "role": "structured-scorecard", "media_type": "application/json", "present": True},
                {"artifact": f"{stem}-matrix-scorecard.pdf", "role": "executive-scorecard", "media_type": "application/pdf", "present": True},
                {"artifact": f"{stem}-matrix-scorecard.svg", "role": "scorecard-card-vector", "media_type": "image/svg+xml", "present": True},
            ],
        },
        "security": {
            "contains_raw_secrets": False,
            "contains_raw_provider_payloads": False,
            "contains_results_jsonl": False,
            "contains_per_run_raw_traces": False,
        },
    }
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("matrix-publication-bundle-manifest.json", json.dumps(manifest, sort_keys=True) + "\n")


def test_claim_readiness_summarizes_implementation_status_without_local_paths(tmp_path) -> None:
    implementation_status = tmp_path / "implementation-status.json"
    _write_json(
        implementation_status,
        {
            "schema_version": "agentblaster.implementation-status.v1",
            "status": "implementation-ready-for-validation",
            "implemented_areas": 9,
            "partial_areas": 0,
            "missing_areas": 0,
            "project_root": "/private/worktrees/AgentBlaster",
            "areas": [{"id": "cli-core", "evidence": ["/private/worktrees/AgentBlaster/src/agentblaster/cli.py"]}],
            "suite_inventory": {
                "built_in_suite_count": 8,
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
                "enterprise_controls": {"keyring_optional": True, "secret_backends": ["env", "keyring", "dotenv"]},
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
        },
    )

    report = build_claim_readiness(name="implementation-review", implementation_status_reports=[implementation_status])
    rendered = format_claim_readiness(report)

    summary = report["evidence"]["implementation_status_summaries"][0]
    assert summary["schema_version"] == "agentblaster.implementation-status.v1"
    assert summary["implementation_status"] == "implementation-ready-for-validation"
    assert summary["missing_areas"] == 0
    assert summary["harness_engineering_case_count"] == 4
    assert summary["stats_profile_count"] == 8
    assert summary["shareable_summary_only"] is True
    assert "implementation_status:" in rendered
    assert "/private/worktrees" not in json.dumps(summary)


def test_claim_readiness_blocks_incomplete_embedded_implementation_status(tmp_path) -> None:
    release_bundle = tmp_path / "claim.agentblaster-release-qualification.zip"
    _write_release_bundle(
        release_bundle,
        implementation_status_review=True,
        implementation_status_ready=False,
    )

    report = build_claim_readiness(name="implementation-review", release_qualification_bundle=release_bundle)

    release_check = next(check for check in report["checks"] if check["category"] == "release_qualification_bundle")
    assert release_check["ok"] is False
    assert (
        release_check["message"]
        == "release qualification bundle contains implementation status that is not ready for validation"
    )
    summary = release_check["implementation_status_summaries"][0]
    assert summary["missing_areas"] == 1
    assert summary["status"] == "implementation-incomplete"
    assert summary["implementation_status"] == "implementation-incomplete"


def _write_artifacts(tmp_path):
    artifacts = {
        "experiment_manifest": tmp_path / "experiment.json",
        "experiment_gate": tmp_path / "experiment-gate.json",
        "provider_contract_check": tmp_path / "provider-contract-check.json",
        "provider_contract_matrix": tmp_path / "provider-contract-matrix.json",
        "matrix_gate": tmp_path / "matrix-gate.json",
        "telemetry_audit": tmp_path / "telemetry-audit.json",
        "matrix_pressure": tmp_path / "matrix-pressure.json",
        "matrix_saturation": tmp_path / "matrix-saturation.json",
        "matrix_scorecard": tmp_path / "matrix-scorecard.json",
        "release_provenance": tmp_path / "release-provenance.json",
        "redaction_scan": tmp_path / "redaction-scan.json",
        "release_bundle": tmp_path / "claim.agentblaster-release-qualification.zip",
        "publication_bundle": tmp_path / "run.agentblaster-publication.zip",
        "matrix_publication_bundle": tmp_path / "qwen-gemma.agentblaster-matrix-publication.zip",
        "harness_review": tmp_path / "harness-review.json",
        "engine_advisory": tmp_path / "engine-advisory.json",
        "evidence_index": tmp_path / "evidence-index.json",
        "suite_audit": tmp_path / "suite-audit.json",
        "metric_coverage": tmp_path / "metric-coverage.json",
        "normalized_telemetry": tmp_path / "normalized-telemetry.json",
        "selftest_report": tmp_path / "selftest-report.json",
        "benchmark_readiness": tmp_path / "benchmark-readiness.json",
        "campaign_preflight_manifest": tmp_path / "campaign-preflight" / "manifest.json",
    }
    _write_json(artifacts["experiment_manifest"], {"schema_version": "agentblaster.experiment-manifest.v1"})
    _write_json(artifacts["experiment_gate"], {"schema_version": "agentblaster.experiment-gate.v1", "passed": True})
    _write_json(
        artifacts["provider_contract_check"],
        {
            "schema_version": "agentblaster.provider-contract-check.v1",
            "ok": True,
            "capability_evidence": {
                "directly_checked": ["streaming", "structured_output", "tool_calling"],
                "proxy_checked": [{"capability": "judge_rubric", "covered_by": "structured_output"}],
                "not_covered": [],
            },
        },
    )
    _write_json(
        artifacts["provider_contract_matrix"],
        {
            "schema_version": "agentblaster.provider-contract-matrix.v1",
            "ok": True,
            "capability_evidence": {
                "directly_checked": ["streaming", "structured_output", "tool_calling"],
                "proxy_checked_counts": {"judge_rubric": 2},
                "not_covered_counts": {"prompt_caching": 1},
            },
        },
    )
    _write_json(
        artifacts["matrix_gate"],
        {
            "schema_version": "agentblaster.matrix-gate.v1",
            "ok": True,
            "failure_class_summary": [{"failure_class": "model_quality", "count": 2}],
            "failure_class_artifacts_missing": 0,
            "tool_loop_stop_summary": [{"stop_reason": "completed", "count": 3}],
            "tool_loop_artifacts_missing": 0,
            "judge_rubric_cases": 2,
            "judge_verdicts_valid": 2,
            "judge_verdict_valid_rate_percent": 100.0,
            "judge_verdict_artifacts_missing": 0,
            "invalid_tool_call_count": 0,
            "tool_parser_repair_cases": 2,
            "tool_parser_repairs_valid": 2,
            "tool_parser_repair_valid_rate_percent": 100.0,
            "tool_parser_repair_artifacts_missing": 0,
            "findings": [],
        },
    )
    _write_json(
        artifacts["telemetry_audit"],
        {
            "schema_version": "agentblaster.telemetry-audit.v1",
            "summary": {"comparable_core_ok": True},
        },
    )
    _write_json(artifacts["matrix_pressure"], {"schema_version": "agentblaster.matrix-pressure-audit.v1"})
    _write_json(artifacts["matrix_saturation"], {"schema_version": "agentblaster.matrix-saturation.v1", "ok": True})
    _write_json(
        artifacts["matrix_scorecard"],
        {
            "report_type": "agentblaster-matrix-scorecard-v1",
            "matrix": {
                "name": "qwen-gemma-local",
                "completed_runs": 2,
                "total_runs": 2,
                "failed_runs": 0,
            },
            "scorecard": {
                "entry_count": 2,
                "result_artifacts_loaded": 2,
                "total_cases": 10,
                "passed_cases": 10,
                "failed_cases": 0,
                "pass_rate_percent": 100.0,
                "invalid_tool_call_count": 0,
                "tool_parser_repair_cases": 2,
                "tool_parser_repairs_valid": 2,
                "tool_parser_repair_valid_rate_percent": 100.0,
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
                        "invalid_tool_call_count": 0,
                        "tool_parser_repair_cases": 2,
                        "tool_parser_repairs_valid": 2,
                        "tool_parser_repair_valid_rate_percent": 100.0,
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
                        "invalid_tool_call_count": 0,
                        "tool_parser_repair_cases": 2,
                        "tool_parser_repairs_valid": 2,
                        "tool_parser_repair_valid_rate_percent": 100.0,
                    }
                ],
                "judge_rubric_cases": 2,
                "judge_verdicts_valid": 2,
                "failure_class_summary": [],
                "tool_loop_stop_summary": [{"stop_reason": "final_response", "count": 2}],
                "telemetry_quality_summary": {
                    "quality_counts": {"native": 3, "measured": 9},
                    "guidance_counts": {},
                    "entries_with_advisory_quality": 0,
                    "entries_with_unknown_quality": 0,
                    "entries_with_comparison_guidance": 0,
                },
                "concurrency_evidence": {
                    "schema_version": "agentblaster.scorecard-concurrency-evidence.v1",
                    "entry_count": 2,
                    "artifact_loaded_count": 2,
                    "concurrency_levels": [1, 4],
                    "multi_level": True,
                    "max_concurrency": 4,
                    "max_avg_queue_ms": 0.0,
                    "max_avg_rate_limit_wait_ms": 0.0,
                    "guidance": "concurrency-evidence-ready-when-release-gates-pass",
                    "highest_queue_wait_entries": [],
                    "highest_rate_limit_wait_entries": [],
                },
            },
            "entries": [{"run_id": "not-copied", "raw_response_path": "raw/not-copied.response.json"}],
        },
    )
    _write_json(artifacts["release_provenance"], {"schema": "agentblaster.release-provenance", "schema_version": 1})
    _write_json(
        artifacts["redaction_scan"],
        {
            "schema_version": "agentblaster.redaction-scan.v1",
            "ok": True,
            "total_paths": 1,
            "scanned_items": 12,
            "skipped_items": 1,
            "findings": [],
            "security_notes": ["matched values suppressed"],
        },
    )
    _write_json(
        artifacts["harness_review"],
        {
            "schema_version": "agentblaster.harness-review.v1",
            "suite": {"name": "harness-orchestration", "case_count": 4},
            "generated": True,
            "generator": {"profile": "orchestration"},
            "surface_counts": {"multi_tool_catalog_cases": 4, "tool_loop_cases": 4},
            "assertion_counts": {"tool_name": 4},
            "review": {
                "status": "calibration-required",
                "human_review_required": True,
                "calibration_required_before_release_gate": True,
            },
        },
    )
    _write_json(
        artifacts["engine_advisory"],
        {
            "schema_version": "agentblaster.engine-improvement-advisory.v1",
            "engine": "afm",
            "summary": {"priority_count": 2, "highest_priority": 1, "no_dispatch": True},
            "priorities": [
                {
                    "priority": 1,
                    "area": "contract-conformance",
                    "reason": "not copied into claim readiness evidence",
                    "aligned_artifacts_or_suites": ["providers contract-check"],
                },
                {
                    "priority": 2,
                    "area": "harness-calibration",
                    "reason": "not copied into claim readiness evidence",
                    "aligned_artifacts_or_suites": ["harness review"],
                },
            ],
        },
    )
    _write_json(
        artifacts["evidence_index"],
        {
            "schema_version": "agentblaster.evidence-index.v1",
            "name": "afm-release",
            "artifact_count": 2,
            "status_counts": {"review": 2},
            "readiness": {
                "ready": False,
                "state": "review-required",
                "blocking_artifact_count": 0,
                "review_artifact_count": 2,
                "blocking_statuses": [],
                "review_statuses": ["review"],
            },
            "cleanup_evidence": {
                "artifact_count": 1,
                "manual_report_count": 0,
                "retention_report_count": 1,
                "planned_report_count": 1,
                "executed_report_count": 0,
                "audit_log_required_count": 1,
                "contains_local_paths": True,
                "direct_publication_safe": False,
                "shareable_summary_only": True,
            },
            "artifacts": [],
            "security": {"includes_raw_results": False},
        },
    )
    _write_json(
        artifacts["suite_audit"],
        {
            "schema_version": "agentblaster.suite-audit.v1",
            "suite": "agentic-local",
            "description": "Agentic local workflow suite.",
            "total_cases": 4,
            "provenance_counts": {"synthetic_representative": 4},
            "risk_counts": {"medium": 4},
            "scenario_counts": {"tool-loop": 4},
            "capability_surfaces": {"tool_schema_names": ["lookup_fixture"]},
            "dataset_hygiene": {"duplicate_fingerprint_count": 0},
            "findings": [],
            "security_notes": [],
        },
    )
    _write_json(
        artifacts["metric_coverage"],
        {
            "schema_version": "agentblaster.metric-coverage.v1",
            "provider": {"name": "afm", "contract": "openai", "native_adapter": None},
            "summary": {
                "field_count": 24,
                "counts": {"native": 12, "measured": 12, "inferred": 0, "conditional": 0, "unavailable": 0},
                "coverage_score": 0.95,
            },
            "comparability": {
                "publication_grade_group_count": 4,
                "advisory_group_count": 0,
                "partial_group_count": 0,
                "unavailable_group_count": 0,
                "publication_grade_groups": [
                    "timing_and_throughput",
                    "token_and_cache_accounting",
                    "agent_protocol_behavior",
                    "telemetry_provenance",
                ],
                "review_required_groups": [],
            },
            "fields": [],
        },
    )
    _write_json(
        artifacts["normalized_telemetry"],
        {
            "schema_version": "agentblaster.normalized-telemetry.v1",
            "contract": "openai",
            "native_adapter": "afm-mlx",
            "stats_profile": "afm-mlx-openai-compatible",
            "values": {
                "input_tokens": 100,
                "output_tokens": 20,
                "total_tokens": 120,
                "cached_input_tokens": 80,
                "ttft_ms": 42.0,
                "prompt_eval_ms": 120.0,
                "decode_ms": 210.0,
                "tokens_per_second_prefill": 833.3,
                "tokens_per_second_decode": 95.2,
                "raw_usage": {"provider_payload": "not copied into claim readiness evidence"},
                "raw_stats": {"provider_stats": "not copied into claim readiness evidence"},
            },
            "sources": {
                "input_tokens": "usage.prompt_tokens",
                "output_tokens": "usage.completion_tokens",
                "prompt_eval_ms": "stats.prompt_eval_ms",
                "decode_ms": "stats.decode_ms",
            },
            "quality": {
                "input_tokens": "native",
                "output_tokens": "native",
                "total_tokens": "native",
                "cached_input_tokens": "native",
                "ttft_ms": "measured",
                "prompt_eval_ms": "native",
                "decode_ms": "native",
                "tokens_per_second_prefill": "native",
                "tokens_per_second_decode": "native",
            },
            "comparison_readiness": {
                "publication_grade_field_count": 8,
                "advisory_field_count": 0,
                "raw_provenance_field_count": 0,
                "guidance": "publication-grade-for-present-fields-when-run-telemetry-audit-passes",
            },
            "stats_comparability": {
                "requires_labeling": False,
                "guidance": "stats-fields-ready-for-like-for-like-comparison",
                "publication_grade_fields": [
                    "ttft_ms",
                    "prompt_eval_ms",
                    "decode_ms",
                    "tokens_per_second_prefill",
                    "tokens_per_second_decode",
                    "cached_input_tokens",
                ],
                "advisory_fields": [],
                "missing_stats_fields": [],
            },
            "missing": ["queue_ms", "rate_limit_wait_ms"],
        },
    )
    _write_json(
        artifacts["selftest_report"],
        {
            "schema_version": "agentblaster.selftest-report.v1",
            "run_id": "selftest_20260531T000000Z",
            "tier": "normal",
            "marker_expression": "not remote and not slow and not gui",
            "duration_ms": 1000.0,
            "exit_code": 0,
            "ok": True,
            "junit_xml": "normal.junit.xml",
            "command": "not copied into claim readiness evidence",
            "env": {"AGENTBLASTER_INTERNAL_VALUE": "not copied into claim readiness evidence"},
        },
    )
    _write_json(
        artifacts["benchmark_readiness"],
        {
            **_benchmark_readiness_review_summary(),
            "summary": {
                "policy_ok": True,
                "suite_compatible": True,
                "contract_checks_planned": 5,
                "contract_capabilities_directly_checked": 3,
                "contract_capabilities_proxy_checked": 1,
                "contract_capabilities_not_covered": 1,
                "metric_coverage_score": 0.95,
                "provider_auth_writable_backends": 1,
                "provider_auth_plaintext_fallbacks": 1,
                "provider_auth_prewrite_policy_guards_recommended": 1,
                "blocking_findings": 0,
                "warnings": 1,
            },
        },
    )
    preflight_dir = artifacts["campaign_preflight_manifest"].parent
    (preflight_dir / "readiness").mkdir(parents=True)
    _write_json(
        preflight_dir / "readiness" / "benchmark-readiness-index.json",
        {
            "schema_version": "agentblaster.campaign-preflight-benchmark-readiness-index.v1",
            "report_count": 1,
            "reports": [_benchmark_readiness_review_summary()],
            "security": {
                "contacts_providers": False,
                "resolves_secrets": False,
                "reads_keyring_values": False,
                "contains_raw_secrets": False,
                "contains_raw_provider_payloads": False,
                "contains_raw_traces": False,
            },
        },
    )
    _write_json(
        artifacts["campaign_preflight_manifest"],
        {
            "schema_version": "agentblaster.campaign-preflight-bundle.v1",
            "matrix_count": 1,
            "artifact_count": 1,
            "includes_benchmark_readiness": True,
            "benchmark_readiness": {
                "artifact_path": "readiness/benchmark-readiness-index.json",
                "report_count": 1,
            },
            "review_summary": {
                "schema_version": "agentblaster.campaign-preflight-review-summary.v1",
                "matrix_count": 1,
                "run_count": 1,
                "total_cases": 4,
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
                "reads_keyring_values": False,
                "contains_raw_secrets": False,
                "contains_raw_provider_payloads": False,
                "contains_raw_traces": False,
            },
        },
    )
    _write_release_bundle(artifacts["release_bundle"])
    _write_publication_bundle(artifacts["publication_bundle"])
    _write_matrix_publication_bundle(artifacts["matrix_publication_bundle"])
    return artifacts


def test_claim_readiness_passes_with_required_evidence(tmp_path) -> None:
    artifacts = _write_artifacts(tmp_path)

    report = build_claim_readiness(
        name="qwen-gemma-local",
        experiment_manifest=artifacts["experiment_manifest"],
        experiment_gate=artifacts["experiment_gate"],
        provider_contract_checks=[artifacts["provider_contract_check"]],
        matrix_gates=[artifacts["matrix_gate"]],
        telemetry_audits=[artifacts["telemetry_audit"]],
        matrix_pressure_audits=[artifacts["matrix_pressure"]],
        matrix_saturation_reports=[artifacts["matrix_saturation"]],
        matrix_scorecards=[artifacts["matrix_scorecard"]],
        release_provenance=artifacts["release_provenance"],
        release_qualification_bundle=artifacts["release_bundle"],
        redaction_scan=artifacts["redaction_scan"],
        publication_bundles=[artifacts["publication_bundle"]],
        harness_reviews=[artifacts["harness_review"]],
        engine_advisories=[artifacts["engine_advisory"]],
        evidence_indexes=[artifacts["evidence_index"]],
        suite_audits=[artifacts["suite_audit"]],
        metric_coverage_reports=[artifacts["metric_coverage"]],
        normalized_telemetry_reports=[artifacts["normalized_telemetry"]],
        benchmark_readiness_reports=[artifacts["benchmark_readiness"]],
    )

    assert report["schema_version"] == "agentblaster.claim-readiness.v1"
    assert report["ready"] is True
    assert report["summary"]["blockers"] == 0
    assert report["evidence"]["provider_contract_capability_evidence"]["proxy_checked_counts"] == {
        "judge_rubric": 1
    }
    assert report["evidence"]["matrix_gate_failure_class_summary"] == [
        {"failure_class": "model_quality", "count": 2}
    ]
    assert report["evidence"]["matrix_gate_failure_class_artifacts_missing"] == 0
    assert report["evidence"]["matrix_gate_tool_loop_stop_summary"] == [
        {"stop_reason": "completed", "count": 3}
    ]
    assert report["evidence"]["matrix_gate_tool_loop_artifacts_missing"] == 0
    assert report["evidence"]["matrix_gate_judge_verdict_summary"] == {
        "judge_rubric_cases": 2,
        "judge_verdicts_valid": 2,
        "judge_verdict_valid_rate_percent": 100.0,
    }
    assert report["evidence"]["matrix_gate_judge_verdict_artifacts_missing"] == 0
    assert report["evidence"]["matrix_gate_tool_parser_repair_summary"] == {
        "invalid_tool_call_count": 0,
        "tool_parser_repair_cases": 2,
        "tool_parser_repairs_valid": 2,
        "tool_parser_repair_valid_rate_percent": 100.0,
    }
    assert report["evidence"]["matrix_gate_tool_parser_repair_artifacts_missing"] == 0
    assert report["evidence"]["harness_review_summaries"][0]["generator_profile"] == "orchestration"
    assert report["evidence"]["harness_review_summaries"][0]["calibration_required_before_release_gate"] is True
    assert report["evidence"]["engine_advisory_summaries"][0]["engine"] == "afm"
    assert report["evidence"]["engine_advisory_summaries"][0]["top_priorities"][0]["area"] == "contract-conformance"
    assert "reason" not in report["evidence"]["engine_advisory_summaries"][0]["top_priorities"][0]
    assert report["evidence"]["evidence_index_summaries"][0]["status_counts"] == {"review": 2}
    assert report["evidence"]["evidence_index_summaries"][0]["readiness"]["state"] == "review-required"
    assert report["evidence"]["evidence_index_summaries"][0]["cleanup_evidence"]["audit_log_required_count"] == 1
    assert report["evidence"]["suite_audit_summaries"][0]["suite"] == "agentic-local"
    assert report["evidence"]["suite_audit_summaries"][0]["duplicate_fingerprint_count"] == 0
    assert report["evidence"]["metric_coverage_summaries"][0]["provider"] == "afm"
    assert report["evidence"]["metric_coverage_summaries"][0]["publication_grade_group_count"] == 4
    assert report["evidence"]["redaction_scan_summaries"][0]["schema_version"] == "agentblaster.redaction-scan.v1"
    assert report["evidence"]["redaction_scan_summaries"][0]["scanned_items"] == 12
    assert report["evidence"]["redaction_scan_summaries"][0]["finding_count"] == 0
    assert report["evidence"]["redaction_scan_summaries"][0]["shareable_summary_only"] is True
    assert report["evidence"]["normalized_telemetry_summaries"][0]["stats_profile"] == "afm-mlx-openai-compatible"
    assert report["evidence"]["normalized_telemetry_summaries"][0]["stats_requires_labeling"] is False
    assert report["evidence"]["normalized_telemetry_summaries"][0]["missing_stats_fields"] == []
    assert "provider_payload" not in json.dumps(report["evidence"]["normalized_telemetry_summaries"])
    assert any(
        summary.get("archive_path") == "metrics/normalized-telemetry/afm-normalized-telemetry.json"
        for summary in report["evidence"]["normalized_telemetry_summaries"]
    )
    assert report["evidence"]["publication_bundle_summaries"][0]["run_id"] == "run-123"
    assert report["evidence"]["publication_bundle_summaries"][0]["publication_readiness"]["status"] == "ready"
    assert report["evidence"]["publication_bundle_summaries"][0]["security"]["contains_results_jsonl"] is False
    assert report["evidence"]["matrix_scorecard_summaries"][0]["matrix"] == "qwen-gemma-local"
    assert report["evidence"]["matrix_scorecard_summaries"][0]["engine_targets"] == [
        {"id": "afm-mlx", "display_name": "AFM MLX", "primary_scoring_contract": "openai"}
    ]
    assert report["evidence"]["matrix_scorecard_summaries"][0]["architecture_summary"][0]["model_architecture"] == "qwen3.6-dense"
    assert report["evidence"]["matrix_scorecard_summaries"][0]["quantization_summary"][0]["quantization"] == "mlx-f16"
    assert report["evidence"]["matrix_scorecard_summaries"][0]["invalid_tool_call_count"] == 0
    assert report["evidence"]["matrix_scorecard_summaries"][0]["tool_parser_repair_cases"] == 2
    assert report["evidence"]["matrix_scorecard_summaries"][0]["tool_parser_repairs_valid"] == 2
    assert report["evidence"]["matrix_scorecard_summaries"][0]["tool_parser_repair_valid_rate_percent"] == 100.0
    assert report["evidence"]["matrix_scorecard_summaries"][0]["telemetry_quality_summary"]["quality_counts"] == {
        "measured": 9,
        "native": 3,
    }
    assert report["evidence"]["matrix_scorecard_summaries"][0]["concurrency_evidence"]["concurrency_levels"] == [1, 4]
    assert "raw_response_path" not in json.dumps(report["evidence"]["matrix_scorecard_summaries"])
    assert report["evidence"]["selftest_report_summaries"][0]["tier"] == "normal"
    assert report["evidence"]["selftest_report_summaries"][0]["junit_xml_present"] is True
    assert "AGENTBLASTER_INTERNAL_VALUE" not in json.dumps(report["evidence"]["selftest_report_summaries"])
    assert report["evidence"]["benchmark_readiness_summaries"][0]["provider"] == "afm"
    assert report["evidence"]["benchmark_readiness_summaries"][0]["provider_auth_plaintext_fallbacks"] == 1
    assert report["evidence"]["benchmark_readiness_summaries"][0]["provider_auth_posture"][0][
        "api_key_ref_plaintext_fallback"
    ] is True
    assert any(check["category"] == "harness_reviews[1]" for check in report["checks"])
    formatted = format_claim_readiness(report)
    assert "ready: true" in formatted
    assert "provider_contract_capability_evidence: direct=streaming,structured_output,tool_calling; proxy=judge_rubric=1" in formatted
    assert "matrix_gate_failure_classes: model_quality=2" in formatted
    assert "matrix_gate_tool_loop_stop_reasons: completed=3" in formatted
    assert "benchmark_readiness: afm=ready:true,auth_writable:1,plaintext:1,policy_guards:1" in formatted
    assert "matrix_gate_judge_verdicts: 2/2 valid (100.0%)" in formatted
    assert "matrix_gate_tool_parser_repairs: 2/2 valid (100.0%), invalid_tools=0" in formatted
    assert "harness_reviews: harness-orchestration=calibration-required (orchestration)" in formatted
    assert "engine_advisories: afm: contract-conformance, harness-calibration" in formatted
    assert "evidence_indexes: afm-release: review=2 (review-required)" in formatted
    assert "suite_audits: agentic-local: findings=0, duplicates=0" in formatted
    assert "metric_coverage: afm: score=0.95, review_groups=0" in formatted
    assert "redaction_scan: ok=true,scanned=12,skipped=1,findings=0,patterns=none" in formatted
    assert "normalized_telemetry: afm-mlx-openai-compatible: populated=9,advisory=0,raw_provenance=0,labeling=false" in formatted
    assert "publication_bundles: run-123=ready,missing_media:0" in formatted
    assert "matrix_scorecards: qwen-gemma-local: pass=100" in formatted
    assert "parser_repair=2/2, invalid_tools=0" in formatted
    assert "architectures=qwen3.6-dense, quantization=mlx-f16" in formatted
    assert "selftests: selftest_20260531T000000Z: normal=pass exit=0" in formatted


def test_claim_readiness_blocks_missing_required_artifacts(tmp_path) -> None:
    report = build_claim_readiness(name="missing")

    assert report["ready"] is False
    assert report["summary"]["blockers"] >= 1
    assert any(check["category"] == "experiment_manifest" for check in report["checks"])


def test_claim_readiness_blocks_unversioned_redaction_scan(tmp_path) -> None:
    artifacts = _write_artifacts(tmp_path)
    _write_json(artifacts["redaction_scan"], {"ok": True})

    report = build_claim_readiness(
        name="qwen-gemma-local",
        experiment_manifest=artifacts["experiment_manifest"],
        experiment_gate=artifacts["experiment_gate"],
        provider_contract_checks=[artifacts["provider_contract_check"]],
        matrix_gates=[artifacts["matrix_gate"]],
        telemetry_audits=[artifacts["telemetry_audit"]],
        matrix_pressure_audits=[artifacts["matrix_pressure"]],
        matrix_saturation_reports=[artifacts["matrix_saturation"]],
        release_provenance=artifacts["release_provenance"],
        release_qualification_bundle=artifacts["release_bundle"],
        redaction_scan=artifacts["redaction_scan"],
    )

    assert report["ready"] is False
    assert any(
        check["category"] == "redaction_scan"
        and "expected schema agentblaster.redaction-scan.v1" in check["message"]
        for check in report["checks"]
    )


def test_claim_readiness_warns_when_matrix_scorecard_evidence_is_missing(tmp_path) -> None:
    artifacts = _write_artifacts(tmp_path)
    _write_release_bundle(artifacts["release_bundle"], matrix_scorecard_review=False)

    report = build_claim_readiness(
        name="qwen-gemma-local",
        experiment_manifest=artifacts["experiment_manifest"],
        experiment_gate=artifacts["experiment_gate"],
        provider_contract_checks=[artifacts["provider_contract_check"]],
        matrix_gates=[artifacts["matrix_gate"]],
        telemetry_audits=[artifacts["telemetry_audit"]],
        matrix_pressure_audits=[artifacts["matrix_pressure"]],
        matrix_saturation_reports=[artifacts["matrix_saturation"]],
        release_provenance=artifacts["release_provenance"],
        release_qualification_bundle=artifacts["release_bundle"],
        redaction_scan=artifacts["redaction_scan"],
    )

    assert report["ready"] is True
    assert any(
        check["category"] == "matrix_scorecard_evidence"
        and check["severity"] == "warning"
        and check["ok"] is False
        for check in report["checks"]
    )


def test_claim_readiness_warns_on_weak_matrix_scorecard_evidence(tmp_path) -> None:
    artifacts = _write_artifacts(tmp_path)
    _write_json(
        artifacts["matrix_scorecard"],
        {
            "report_type": "agentblaster-matrix-scorecard-v1",
            "matrix": {"name": "qwen-gemma-local", "completed_runs": 1, "total_runs": 1, "failed_runs": 0},
            "scorecard": {
                "entry_count": 1,
                "result_artifacts_loaded": 1,
                "total_cases": 1,
                "passed_cases": 1,
                "failed_cases": 0,
                "pass_rate_percent": 100.0,
                "invalid_tool_call_count": 1,
                "tool_parser_repair_cases": 2,
                "tool_parser_repairs_valid": 1,
                "tool_parser_repair_valid_rate_percent": 50.0,
                "telemetry_quality_summary": {
                    "quality_counts": {"measured": 1, "inferred": 1},
                    "entries_with_advisory_quality": 1,
                },
                "concurrency_evidence": {
                    "concurrency_levels": [1],
                    "max_concurrency": 1,
                    "guidance": "single-concurrency-level-advisory-only",
                },
            },
        },
    )
    _write_release_bundle(artifacts["release_bundle"], matrix_scorecard_review=False)

    report = build_claim_readiness(
        name="qwen-gemma-local",
        experiment_manifest=artifacts["experiment_manifest"],
        experiment_gate=artifacts["experiment_gate"],
        provider_contract_checks=[artifacts["provider_contract_check"]],
        matrix_gates=[artifacts["matrix_gate"]],
        telemetry_audits=[artifacts["telemetry_audit"]],
        matrix_pressure_audits=[artifacts["matrix_pressure"]],
        matrix_saturation_reports=[artifacts["matrix_saturation"]],
        matrix_scorecards=[artifacts["matrix_scorecard"]],
        release_provenance=artifacts["release_provenance"],
        release_qualification_bundle=artifacts["release_bundle"],
        redaction_scan=artifacts["redaction_scan"],
    )

    assert report["ready"] is True
    assert any(check["category"].endswith(".telemetry_quality") for check in report["checks"])
    assert any(check["category"].endswith(".concurrency") for check in report["checks"])
    assert any(check["category"].endswith(".tool_parser_repair") for check in report["checks"])
    assert any(check["category"].endswith(".invalid_tool_calls") for check in report["checks"])


def test_claim_readiness_blocks_release_bundle_with_failed_manifest_status(tmp_path) -> None:
    artifacts = _write_artifacts(tmp_path)
    _write_release_bundle(artifacts["release_bundle"], ok=False)

    report = build_claim_readiness(
        name="qwen-gemma-local",
        experiment_manifest=artifacts["experiment_manifest"],
        experiment_gate=artifacts["experiment_gate"],
        provider_contract_checks=[artifacts["provider_contract_check"]],
        matrix_gates=[artifacts["matrix_gate"]],
        telemetry_audits=[artifacts["telemetry_audit"]],
        matrix_pressure_audits=[artifacts["matrix_pressure"]],
        matrix_saturation_reports=[artifacts["matrix_saturation"]],
        release_provenance=artifacts["release_provenance"],
        release_qualification_bundle=artifacts["release_bundle"],
        redaction_scan=artifacts["redaction_scan"],
    )

    assert report["ready"] is False
    assert any(check["category"] == "release_qualification_bundle" for check in report["checks"])


def test_claim_readiness_blocks_failed_matrix_saturation(tmp_path) -> None:
    artifacts = _write_artifacts(tmp_path)
    _write_json(artifacts["matrix_saturation"], {"schema_version": "agentblaster.matrix-saturation.v1", "ok": False})

    report = build_claim_readiness(
        name="qwen-gemma-local",
        experiment_manifest=artifacts["experiment_manifest"],
        experiment_gate=artifacts["experiment_gate"],
        provider_contract_checks=[artifacts["provider_contract_check"]],
        matrix_gates=[artifacts["matrix_gate"]],
        telemetry_audits=[artifacts["telemetry_audit"]],
        matrix_pressure_audits=[artifacts["matrix_pressure"]],
        matrix_saturation_reports=[artifacts["matrix_saturation"]],
        release_provenance=artifacts["release_provenance"],
        release_qualification_bundle=artifacts["release_bundle"],
        redaction_scan=artifacts["redaction_scan"],
    )

    assert report["ready"] is False
    assert any(check["category"] == "matrix_saturation_reports[1]" for check in report["checks"])


def test_claim_readiness_blocks_unversioned_matrix_gate(tmp_path) -> None:
    artifacts = _write_artifacts(tmp_path)
    _write_json(artifacts["matrix_gate"], {"ok": True})

    report = build_claim_readiness(
        name="qwen-gemma-local",
        experiment_manifest=artifacts["experiment_manifest"],
        experiment_gate=artifacts["experiment_gate"],
        provider_contract_checks=[artifacts["provider_contract_check"]],
        matrix_gates=[artifacts["matrix_gate"]],
        telemetry_audits=[artifacts["telemetry_audit"]],
        matrix_pressure_audits=[artifacts["matrix_pressure"]],
        matrix_saturation_reports=[artifacts["matrix_saturation"]],
        release_provenance=artifacts["release_provenance"],
        release_qualification_bundle=artifacts["release_bundle"],
        redaction_scan=artifacts["redaction_scan"],
    )

    assert report["ready"] is False
    assert any(
        check["category"] == "matrix_gates[1]" and "expected schema agentblaster.matrix-gate.v1" in check["message"]
        for check in report["checks"]
    )


def test_claim_readiness_blocks_unversioned_engine_advisory(tmp_path) -> None:
    artifacts = _write_artifacts(tmp_path)
    _write_json(artifacts["engine_advisory"], {"engine": "afm", "summary": {"priority_count": 1}})

    report = build_claim_readiness(
        name="qwen-gemma-local",
        experiment_manifest=artifacts["experiment_manifest"],
        experiment_gate=artifacts["experiment_gate"],
        provider_contract_checks=[artifacts["provider_contract_check"]],
        matrix_gates=[artifacts["matrix_gate"]],
        telemetry_audits=[artifacts["telemetry_audit"]],
        matrix_pressure_audits=[artifacts["matrix_pressure"]],
        matrix_saturation_reports=[artifacts["matrix_saturation"]],
        release_provenance=artifacts["release_provenance"],
        release_qualification_bundle=artifacts["release_bundle"],
        redaction_scan=artifacts["redaction_scan"],
        engine_advisories=[artifacts["engine_advisory"]],
    )

    assert report["ready"] is False
    assert any(
        check["category"] == "engine_advisories[1]" and "expected schema agentblaster.engine-improvement-advisory.v1" in check["message"]
        for check in report["checks"]
    )


def test_claim_readiness_surfaces_failed_matrix_gate_failure_classes(tmp_path) -> None:
    artifacts = _write_artifacts(tmp_path)
    _write_json(
        artifacts["matrix_gate"],
        {
            "schema_version": "agentblaster.matrix-gate.v1",
            "ok": False,
            "failure_class_summary": [{"failure_class": "engine_protocol_bug", "count": 1}],
            "failure_class_artifacts_missing": 1,
            "tool_loop_stop_summary": [{"stop_reason": "max_tool_calls_reached", "count": 1}],
            "tool_loop_artifacts_missing": 1,
            "findings": [
                {
                    "metric": "failure_class.engine_protocol_bug",
                    "actual": 1,
                    "threshold": 0,
                    "message": "engine protocol bugs block publication",
                },
                {
                    "metric": "tool_loop_stop_reason.max_tool_calls_reached",
                    "actual": 1,
                    "threshold": 0,
                    "message": "tool-loop max call stops block publication",
                }
            ],
        },
    )

    report = build_claim_readiness(
        name="qwen-gemma-local",
        experiment_manifest=artifacts["experiment_manifest"],
        experiment_gate=artifacts["experiment_gate"],
        provider_contract_checks=[artifacts["provider_contract_check"]],
        matrix_gates=[artifacts["matrix_gate"]],
        telemetry_audits=[artifacts["telemetry_audit"]],
        matrix_pressure_audits=[artifacts["matrix_pressure"]],
        matrix_saturation_reports=[artifacts["matrix_saturation"]],
        release_provenance=artifacts["release_provenance"],
        release_qualification_bundle=artifacts["release_bundle"],
        redaction_scan=artifacts["redaction_scan"],
    )

    assert report["ready"] is False
    assert report["evidence"]["matrix_gate_failure_class_summary"] == [
        {"failure_class": "engine_protocol_bug", "count": 1}
    ]
    assert report["evidence"]["matrix_gate_failure_class_artifacts_missing"] == 1
    assert report["evidence"]["matrix_gate_tool_loop_stop_summary"] == [
        {"stop_reason": "max_tool_calls_reached", "count": 1}
    ]
    assert report["evidence"]["matrix_gate_tool_loop_artifacts_missing"] == 1
    matrix_gate_check = next(check for check in report["checks"] if check["category"] == "matrix_gates[1]")
    assert matrix_gate_check["schema_version"] == "agentblaster.matrix-gate.v1"
    assert matrix_gate_check["tool_loop_stop_summary"] == [{"stop_reason": "max_tool_calls_reached", "count": 1}]
    assert report["evidence"]["matrix_gate_failure_class_findings"][0]["metric"] == "failure_class.engine_protocol_bug"
    assert "message" not in report["evidence"]["matrix_gate_failure_class_findings"][0]
    assert report["evidence"]["matrix_gate_tool_loop_stop_findings"][0]["metric"] == "tool_loop_stop_reason.max_tool_calls_reached"
    assert report["evidence"]["matrix_gate_tool_loop_stop_findings"][0]["stop_reason"] == "max_tool_calls_reached"
    assert "message" not in report["evidence"]["matrix_gate_tool_loop_stop_findings"][0]
    assert any(check["category"] == "matrix_gates[1]" for check in report["checks"])


def test_claim_readiness_blocks_plan_only_provider_contract_check(tmp_path) -> None:
    artifacts = _write_artifacts(tmp_path)
    _write_json(
        artifacts["provider_contract_check"],
        {"schema_version": "agentblaster.provider-contract-check.v1", "mode": "plan-only", "ok": False},
    )

    report = build_claim_readiness(
        name="qwen-gemma-local",
        experiment_manifest=artifacts["experiment_manifest"],
        experiment_gate=artifacts["experiment_gate"],
        provider_contract_checks=[artifacts["provider_contract_check"]],
        matrix_gates=[artifacts["matrix_gate"]],
        telemetry_audits=[artifacts["telemetry_audit"]],
        matrix_pressure_audits=[artifacts["matrix_pressure"]],
        matrix_saturation_reports=[artifacts["matrix_saturation"]],
        release_provenance=artifacts["release_provenance"],
        release_qualification_bundle=artifacts["release_bundle"],
        redaction_scan=artifacts["redaction_scan"],
    )

    assert report["ready"] is False
    assert any(check["category"] == "provider_contract_checks[1]" for check in report["checks"])


def test_claim_readiness_accepts_provider_contract_matrix_instead_of_individual_checks(tmp_path) -> None:
    artifacts = _write_artifacts(tmp_path)

    report = build_claim_readiness(
        name="qwen-gemma-local",
        experiment_manifest=artifacts["experiment_manifest"],
        experiment_gate=artifacts["experiment_gate"],
        provider_contract_matrices=[artifacts["provider_contract_matrix"]],
        matrix_gates=[artifacts["matrix_gate"]],
        telemetry_audits=[artifacts["telemetry_audit"]],
        matrix_pressure_audits=[artifacts["matrix_pressure"]],
        matrix_saturation_reports=[artifacts["matrix_saturation"]],
        release_provenance=artifacts["release_provenance"],
        release_qualification_bundle=artifacts["release_bundle"],
        redaction_scan=artifacts["redaction_scan"],
    )

    assert report["ready"] is True
    assert any(check["category"] == "provider_contract_matrices[1]" for check in report["checks"])


def test_claim_readiness_accepts_optional_matrix_publication_bundle(tmp_path) -> None:
    artifacts = _write_artifacts(tmp_path)

    report = build_claim_readiness(
        name="qwen-gemma-local",
        experiment_manifest=artifacts["experiment_manifest"],
        experiment_gate=artifacts["experiment_gate"],
        provider_contract_checks=[artifacts["provider_contract_check"]],
        matrix_gates=[artifacts["matrix_gate"]],
        telemetry_audits=[artifacts["telemetry_audit"]],
        matrix_pressure_audits=[artifacts["matrix_pressure"]],
        matrix_saturation_reports=[artifacts["matrix_saturation"]],
        release_provenance=artifacts["release_provenance"],
        release_qualification_bundle=artifacts["release_bundle"],
        redaction_scan=artifacts["redaction_scan"],
        matrix_publication_bundles=[artifacts["matrix_publication_bundle"]],
    )

    assert report["ready"] is True
    assert any(check["category"] == "matrix_publication_bundles[1]" for check in report["checks"])
    assert report["evidence"]["matrix_publication_bundle_summaries"][0]["matrix"]["artifact_stem"] == "qwen-gemma"
    assert report["evidence"]["matrix_publication_bundle_summaries"][0]["engine_targets"] == [
        {"id": "afm-mlx", "display_name": "AFM MLX", "primary_scoring_contract": "openai"}
    ]
    assert report["evidence"]["matrix_publication_bundle_summaries"][0]["architecture_summary"][0]["model_architecture"] == "qwen3.6-dense"
    assert report["evidence"]["matrix_publication_bundle_summaries"][0]["quantization_summary"][0]["quantization"] == "mlx-f16"
    assert report["evidence"]["matrix_publication_bundle_summaries"][0]["security"]["contains_results_jsonl"] is False
    assert (
        "matrix_publication_bundles: qwen-gemma=missing_media:0,targets:afm-mlx,"
        "architectures:qwen3.6-dense,quantization:mlx-f16"
    ) in format_claim_readiness(report)


def test_claim_readiness_blocks_failed_benchmark_readiness(tmp_path) -> None:
    artifacts = _write_artifacts(tmp_path)
    _write_json(
        artifacts["benchmark_readiness"],
        {
            **_benchmark_readiness_review_summary(),
            "ready": False,
            "summary": {
                "provider_auth_writable_backends": 1,
                "provider_auth_plaintext_fallbacks": 1,
                "provider_auth_prewrite_policy_guards_recommended": 1,
                "blocking_findings": 1,
                "warnings": 0,
            },
        },
    )

    report = build_claim_readiness(
        name="qwen-gemma-local",
        experiment_manifest=artifacts["experiment_manifest"],
        experiment_gate=artifacts["experiment_gate"],
        provider_contract_checks=[artifacts["provider_contract_check"]],
        matrix_gates=[artifacts["matrix_gate"]],
        telemetry_audits=[artifacts["telemetry_audit"]],
        matrix_pressure_audits=[artifacts["matrix_pressure"]],
        matrix_saturation_reports=[artifacts["matrix_saturation"]],
        release_provenance=artifacts["release_provenance"],
        release_qualification_bundle=artifacts["release_bundle"],
        redaction_scan=artifacts["redaction_scan"],
        benchmark_readiness_reports=[artifacts["benchmark_readiness"]],
    )

    assert report["ready"] is False
    readiness_check = next(check for check in report["checks"] if check["category"] == "benchmark_readiness_reports[1]")
    assert readiness_check["severity"] == "blocker"
    assert readiness_check["benchmark_readiness_summary"]["provider_auth_plaintext_fallbacks"] == 1


def test_claim_readiness_blocks_release_bundle_failed_benchmark_readiness(tmp_path) -> None:
    artifacts = _write_artifacts(tmp_path)
    _write_release_bundle(artifacts["release_bundle"], benchmark_readiness_ready=False)

    report = build_claim_readiness(
        name="qwen-gemma-local",
        experiment_manifest=artifacts["experiment_manifest"],
        experiment_gate=artifacts["experiment_gate"],
        provider_contract_checks=[artifacts["provider_contract_check"]],
        matrix_gates=[artifacts["matrix_gate"]],
        telemetry_audits=[artifacts["telemetry_audit"]],
        matrix_pressure_audits=[artifacts["matrix_pressure"]],
        matrix_saturation_reports=[artifacts["matrix_saturation"]],
        release_provenance=artifacts["release_provenance"],
        release_qualification_bundle=artifacts["release_bundle"],
        redaction_scan=artifacts["redaction_scan"],
    )

    assert report["ready"] is False
    release_check = next(check for check in report["checks"] if check["category"] == "release_qualification_bundle")
    assert release_check["message"] == "release qualification bundle contains benchmark readiness that is not true"
    assert release_check["benchmark_readiness_summaries"][0]["ready"] is False


def test_claim_readiness_warns_on_normalized_telemetry_labeling(tmp_path) -> None:
    artifacts = _write_artifacts(tmp_path)
    _write_json(
        artifacts["normalized_telemetry"],
        {
            "schema_version": "agentblaster.normalized-telemetry.v1",
            "contract": "openai",
            "native_adapter": "rapid-mlx",
            "stats_profile": "rapid-mlx-openai-compatible",
            "values": {
                "input_tokens": 100,
                "output_tokens": 20,
                "tokens_per_second_decode": 90.0,
                "raw_stats": {"not": "copied"},
            },
            "sources": {"tokens_per_second_decode": "stats.tokens_per_second"},
            "quality": {
                "input_tokens": "native",
                "output_tokens": "native",
                "tokens_per_second_decode": "conditional",
                "raw_stats": "raw_provenance",
            },
            "comparison_readiness": {
                "publication_grade_field_count": 2,
                "advisory_field_count": 1,
                "raw_provenance_field_count": 1,
                "guidance": "label-inferred-or-conditional-fields-before-cross-engine-comparison",
            },
            "stats_comparability": {
                "requires_labeling": True,
                "guidance": "publish-native-and-measured-fields-separately-from-inferred-conditional-or-missing-stats",
                "publication_grade_fields": [],
                "advisory_fields": ["tokens_per_second_decode"],
                "missing_stats_fields": ["prompt_eval_ms", "decode_ms"],
            },
            "missing": ["prompt_eval_ms", "decode_ms"],
        },
    )

    report = build_claim_readiness(
        name="qwen-gemma-local",
        experiment_manifest=artifacts["experiment_manifest"],
        experiment_gate=artifacts["experiment_gate"],
        provider_contract_checks=[artifacts["provider_contract_check"]],
        matrix_gates=[artifacts["matrix_gate"]],
        telemetry_audits=[artifacts["telemetry_audit"]],
        normalized_telemetry_reports=[artifacts["normalized_telemetry"]],
        matrix_pressure_audits=[artifacts["matrix_pressure"]],
        matrix_saturation_reports=[artifacts["matrix_saturation"]],
        release_provenance=artifacts["release_provenance"],
        release_qualification_bundle=artifacts["release_bundle"],
        redaction_scan=artifacts["redaction_scan"],
    )

    assert report["ready"] is True
    assert any(
        check["category"] == "normalized_telemetry[1].stats_comparability"
        and check["severity"] == "warning"
        and check["ok"] is False
        for check in report["checks"]
    )
    summary = report["evidence"]["normalized_telemetry_summaries"][0]
    assert summary["stats_requires_labeling"] is True
    assert summary["missing_stats_fields"] == ["prompt_eval_ms", "decode_ms"]
    assert "raw_stats" not in json.dumps(summary)


def test_claim_readiness_surfaces_campaign_preflight_benchmark_readiness(tmp_path) -> None:
    artifacts = _write_artifacts(tmp_path)
    _write_release_bundle(
        artifacts["release_bundle"],
        benchmark_readiness_review=False,
        campaign_preflight_review=True,
    )

    report = build_claim_readiness(
        name="qwen-gemma-local",
        experiment_manifest=artifacts["experiment_manifest"],
        experiment_gate=artifacts["experiment_gate"],
        provider_contract_checks=[artifacts["provider_contract_check"]],
        matrix_gates=[artifacts["matrix_gate"]],
        telemetry_audits=[artifacts["telemetry_audit"]],
        matrix_pressure_audits=[artifacts["matrix_pressure"]],
        matrix_saturation_reports=[artifacts["matrix_saturation"]],
        release_provenance=artifacts["release_provenance"],
        release_qualification_bundle=artifacts["release_bundle"],
        redaction_scan=artifacts["redaction_scan"],
        campaign_preflight_manifest=artifacts["campaign_preflight_manifest"],
    )

    assert report["ready"] is True
    assert report["evidence"]["benchmark_readiness_summaries"][0]["provider"] == "afm"
    assert report["evidence"]["benchmark_readiness_summaries"][0]["provider_auth_plaintext_fallbacks"] == 1
    preflight_check = next(check for check in report["checks"] if check["category"] == "campaign_preflight_manifest")
    assert preflight_check["benchmark_readiness_summaries"][0]["provider_auth_writable_backends"] == 1
    assert preflight_check["campaign_preflight_summary"]["contains_local_paths"] is False
    assert preflight_check["campaign_preflight_summary"]["external_publication_safe"] is True
    assert preflight_check["path"] == "manifest.json"
    assert preflight_check["path_redacted"] is True
    assert any(
        summary.get("archive_path") == "readiness/campaign-preflight/campaign-preflight-manifest.json"
        and summary.get("external_publication_safe") is True
        for summary in report["evidence"]["campaign_preflight_summaries"]
    )
    assert str(tmp_path) not in json.dumps(report["checks"])
    formatted = format_claim_readiness(report)
    assert "campaign_preflight:" in formatted
    assert "external_safe=true" in formatted
    assert "local_paths=false" in formatted


def test_claim_readiness_blocks_campaign_preflight_failed_benchmark_readiness(tmp_path) -> None:
    artifacts = _write_artifacts(tmp_path)
    index_path = artifacts["campaign_preflight_manifest"].parent / "readiness" / "benchmark-readiness-index.json"
    failed_summary = _benchmark_readiness_review_summary()
    failed_summary["ready"] = False
    failed_summary["blocking_findings"] = 1
    _write_json(
        index_path,
        {
            "schema_version": "agentblaster.campaign-preflight-benchmark-readiness-index.v1",
            "report_count": 1,
            "reports": [failed_summary],
        },
    )

    report = build_claim_readiness(
        name="qwen-gemma-local",
        experiment_manifest=artifacts["experiment_manifest"],
        experiment_gate=artifacts["experiment_gate"],
        provider_contract_checks=[artifacts["provider_contract_check"]],
        matrix_gates=[artifacts["matrix_gate"]],
        telemetry_audits=[artifacts["telemetry_audit"]],
        matrix_pressure_audits=[artifacts["matrix_pressure"]],
        matrix_saturation_reports=[artifacts["matrix_saturation"]],
        release_provenance=artifacts["release_provenance"],
        release_qualification_bundle=artifacts["release_bundle"],
        redaction_scan=artifacts["redaction_scan"],
        campaign_preflight_manifest=artifacts["campaign_preflight_manifest"],
    )

    assert report["ready"] is False
    preflight_check = next(check for check in report["checks"] if check["category"] == "campaign_preflight_manifest")
    assert preflight_check["message"] == "campaign preflight benchmark readiness is not true"
    assert preflight_check["benchmark_readiness_summaries"][0]["ready"] is False


def test_claim_readiness_surfaces_publication_bundle_review_status(tmp_path) -> None:
    artifacts = _write_artifacts(tmp_path)
    _write_publication_bundle(artifacts["publication_bundle"], status="review-required")

    report = build_claim_readiness(
        name="qwen-gemma-local",
        experiment_manifest=artifacts["experiment_manifest"],
        experiment_gate=artifacts["experiment_gate"],
        provider_contract_checks=[artifacts["provider_contract_check"]],
        matrix_gates=[artifacts["matrix_gate"]],
        telemetry_audits=[artifacts["telemetry_audit"]],
        matrix_pressure_audits=[artifacts["matrix_pressure"]],
        matrix_saturation_reports=[artifacts["matrix_saturation"]],
        release_provenance=artifacts["release_provenance"],
        release_qualification_bundle=artifacts["release_bundle"],
        redaction_scan=artifacts["redaction_scan"],
        publication_bundles=[artifacts["publication_bundle"]],
    )

    assert report["ready"] is True
    assert report["summary"]["warnings"] == 1
    publication_check = next(check for check in report["checks"] if check["category"] == "publication_bundles[1]")
    assert publication_check["severity"] == "warning"
    assert publication_check["message"] == "publication readiness requires review"
    assert report["evidence"]["publication_bundle_summaries"][0]["publication_readiness"]["status"] == "review-required"


def test_claim_readiness_surfaces_publication_bundle_missing_media_assets(tmp_path) -> None:
    artifacts = _write_artifacts(tmp_path)
    _write_publication_bundle(artifacts["publication_bundle"], missing_media_assets=["report.pdf"])

    report = build_claim_readiness(
        name="qwen-gemma-local",
        experiment_manifest=artifacts["experiment_manifest"],
        experiment_gate=artifacts["experiment_gate"],
        provider_contract_checks=[artifacts["provider_contract_check"]],
        matrix_gates=[artifacts["matrix_gate"]],
        telemetry_audits=[artifacts["telemetry_audit"]],
        matrix_pressure_audits=[artifacts["matrix_pressure"]],
        matrix_saturation_reports=[artifacts["matrix_saturation"]],
        release_provenance=artifacts["release_provenance"],
        release_qualification_bundle=artifacts["release_bundle"],
        redaction_scan=artifacts["redaction_scan"],
        publication_bundles=[artifacts["publication_bundle"]],
    )

    assert report["ready"] is True
    publication_check = next(check for check in report["checks"] if check["category"] == "publication_bundles[1]")
    assert publication_check["severity"] == "warning"
    assert publication_check["message"] == "publication media kit requires review: media_kit.missing_recommended_assets"
    assert report["evidence"]["publication_bundle_summaries"][0]["media_kit"]["missing_recommended_assets"] == ["report.pdf"]
    assert "publication_bundles: run-123=ready,missing_media:1" in format_claim_readiness(report)


def test_claim_readiness_surfaces_release_bundle_publication_summary(tmp_path) -> None:
    artifacts = _write_artifacts(tmp_path)
    _write_release_bundle(
        artifacts["release_bundle"],
        publication_review=True,
        publication_brief_review=True,
        sdlc_validation_manifest_review=True,
    )

    report = build_claim_readiness(
        name="qwen-gemma-local",
        experiment_manifest=artifacts["experiment_manifest"],
        experiment_gate=artifacts["experiment_gate"],
        provider_contract_checks=[artifacts["provider_contract_check"]],
        matrix_gates=[artifacts["matrix_gate"]],
        telemetry_audits=[artifacts["telemetry_audit"]],
        matrix_pressure_audits=[artifacts["matrix_pressure"]],
        matrix_saturation_reports=[artifacts["matrix_saturation"]],
        release_provenance=artifacts["release_provenance"],
        release_qualification_bundle=artifacts["release_bundle"],
        redaction_scan=artifacts["redaction_scan"],
    )

    assert report["ready"] is True
    assert report["evidence"]["publication_bundle_summaries"][0]["run_id"] == "run-release"
    assert report["evidence"]["publication_bundle_summaries"][0]["archive_path"] == "publication/run.agentblaster-publication.zip"
    assert report["evidence"]["publication_bundle_summaries"][0]["publication_readiness"]["status"] == "review-required"
    assert report["evidence"]["publication_bundle_summaries"][0]["security"]["contains_results_jsonl"] is False
    assert report["evidence"]["publication_brief_summaries"][0]["name"] == "afm-release"
    assert report["evidence"]["publication_brief_summaries"][0]["claim_warnings"] == 1
    assert report["evidence"]["publication_brief_summaries"][0]["engine_targets"] == [
        {"id": "afm-mlx", "display_name": "AFM MLX", "primary_scoring_contract": "openai"}
    ]
    assert report["evidence"]["publication_brief_summaries"][0]["architecture_summary"][0]["model_architecture"] == "qwen3.6-dense"
    assert report["evidence"]["publication_brief_summaries"][0]["quantization_summary"][0]["quantization"] == "mlx-f16"
    assert report["evidence"]["benchmark_readiness_summaries"][0]["archive_path"] == "readiness/benchmark/afm-readiness.json"
    assert report["evidence"]["benchmark_readiness_summaries"][0]["provider_auth_writable_backends"] == 1
    assert report["evidence"]["normalized_telemetry_summaries"][0]["archive_path"] == "metrics/normalized-telemetry/afm-normalized-telemetry.json"
    assert report["evidence"]["normalized_telemetry_summaries"][0]["stats_profile"] == "afm-mlx-openai-compatible"
    assert report["evidence"]["sdlc_validation_manifest_summaries"][0]["archive_path"] == "selftest/sdlc-validation-manifest.json"
    assert report["evidence"]["sdlc_validation_manifest_summaries"][0]["chrome_validation_step_count"] == 9
    release_check = next(check for check in report["checks"] if check["category"] == "release_qualification_bundle")
    assert release_check["publication_bundle_summaries"][0]["run_id"] == "run-release"
    assert release_check["publication_brief_summaries"][0]["ready"] is True
    assert release_check["publication_brief_summaries"][0]["engine_targets"] == [
        {"id": "afm-mlx", "display_name": "AFM MLX", "primary_scoring_contract": "openai"}
    ]
    assert release_check["publication_brief_summaries"][0]["architecture_summary"][0]["model_architecture"] == "qwen3.6-dense"
    assert release_check["publication_brief_summaries"][0]["quantization_summary"][0]["quantization"] == "mlx-f16"
    assert release_check["benchmark_readiness_summaries"][0]["provider"] == "afm"
    assert release_check["sdlc_validation_manifest_summaries"][0]["expected_artifact_count"] == 4
    assert release_check["normalized_telemetry_summaries"][0]["stats_requires_labeling"] is False
    assert "publication_bundles: run-release=review-required,missing_media:0" in format_claim_readiness(report)
    assert "publication_briefs: afm-release: ready=true,blockers=0,warnings=1,targets:afm-mlx" in format_claim_readiness(report)
    assert "sdlc_validation: sdlc-validation-manifest.json: gates=7,chrome_steps=9,expected_artifacts=4" in format_claim_readiness(report)


def test_claim_readiness_blocks_unsafe_publication_bundle_manifest(tmp_path) -> None:
    artifacts = _write_artifacts(tmp_path)
    _write_publication_bundle(artifacts["publication_bundle"], contains_results_jsonl=True)

    report = build_claim_readiness(
        name="qwen-gemma-local",
        experiment_manifest=artifacts["experiment_manifest"],
        experiment_gate=artifacts["experiment_gate"],
        provider_contract_checks=[artifacts["provider_contract_check"]],
        matrix_gates=[artifacts["matrix_gate"]],
        telemetry_audits=[artifacts["telemetry_audit"]],
        matrix_pressure_audits=[artifacts["matrix_pressure"]],
        matrix_saturation_reports=[artifacts["matrix_saturation"]],
        release_provenance=artifacts["release_provenance"],
        release_qualification_bundle=artifacts["release_bundle"],
        redaction_scan=artifacts["redaction_scan"],
        publication_bundles=[artifacts["publication_bundle"]],
    )

    assert report["ready"] is False
    publication_check = next(check for check in report["checks"] if check["category"] == "publication_bundles[1]")
    assert publication_check["severity"] == "blocker"
    assert publication_check["message"] == "publication bundle manifest reports unsafe content"


def test_write_claim_readiness_json(tmp_path) -> None:
    artifacts = _write_artifacts(tmp_path)
    output = tmp_path / "claim-readiness.json"

    report = build_claim_readiness(
        name="qwen-gemma-local",
        experiment_manifest=artifacts["experiment_manifest"],
        experiment_gate=artifacts["experiment_gate"],
        provider_contract_checks=[artifacts["provider_contract_check"]],
        matrix_gates=[artifacts["matrix_gate"]],
        telemetry_audits=[artifacts["telemetry_audit"]],
        matrix_pressure_audits=[artifacts["matrix_pressure"]],
        matrix_saturation_reports=[artifacts["matrix_saturation"]],
        release_provenance=artifacts["release_provenance"],
        release_qualification_bundle=artifacts["release_bundle"],
        redaction_scan=artifacts["redaction_scan"],
    )
    write_claim_readiness_json(report, output)

    assert json.loads(output.read_text(encoding="utf-8"))["ready"] is True


def test_cli_release_claim_readiness_writes_report(tmp_path) -> None:
    artifacts = _write_artifacts(tmp_path)
    benchmark_readiness_list = tmp_path / "benchmark-readiness-inputs.txt"
    benchmark_readiness_list.write_text(
        f"# generated campaign readiness inputs\n{artifacts['benchmark_readiness'].name}\n",
        encoding="utf-8",
    )
    output = tmp_path / "claim-readiness.json"

    result = CliRunner().invoke(
        app,
        [
            "release",
            "claim-readiness",
            "--name",
            "qwen-gemma-local",
            "--experiment-manifest",
            str(artifacts["experiment_manifest"]),
            "--experiment-gate",
            str(artifacts["experiment_gate"]),
            "--provider-contract-check",
            str(artifacts["provider_contract_check"]),
            "--matrix-gate",
            str(artifacts["matrix_gate"]),
            "--telemetry-audit",
            str(artifacts["telemetry_audit"]),
            "--matrix-pressure-audit",
            str(artifacts["matrix_pressure"]),
            "--matrix-saturation-report",
            str(artifacts["matrix_saturation"]),
            "--matrix-scorecard",
            str(artifacts["matrix_scorecard"]),
            "--release-provenance",
            str(artifacts["release_provenance"]),
            "--release-qualification-bundle",
            str(artifacts["release_bundle"]),
            "--redaction-scan",
            str(artifacts["redaction_scan"]),
            "--publication-bundle",
            str(artifacts["publication_bundle"]),
            "--harness-review",
            str(artifacts["harness_review"]),
            "--engine-advisory",
            str(artifacts["engine_advisory"]),
            "--evidence-index",
            str(artifacts["evidence_index"]),
            "--suite-audit",
            str(artifacts["suite_audit"]),
            "--metric-coverage",
            str(artifacts["metric_coverage"]),
            "--normalized-telemetry",
            str(artifacts["normalized_telemetry"]),
            "--selftest-report",
            str(artifacts["selftest_report"]),
            "--benchmark-readiness-list",
            str(benchmark_readiness_list),
            "--output-json",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "AgentBlaster claim readiness" in result.output
    assert output.exists()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["evidence"]["selftest_report_summaries"][0]["tier"] == "normal"
    assert payload["evidence"]["benchmark_readiness_summaries"][0]["provider_auth_plaintext_fallbacks"] == 1
    assert payload["evidence"]["normalized_telemetry_summaries"][0]["stats_profile"] == "afm-mlx-openai-compatible"
