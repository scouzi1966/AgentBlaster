from __future__ import annotations

import json
from zipfile import ZipFile

import pytest
from typer.testing import CliRunner

from agentblaster.cli import app
from agentblaster.errors import ConfigError
from agentblaster.release_qualification import create_release_qualification_bundle


def _write_publication_bundle(
    path,
    *,
    status: str = "ready",
    contains_results_jsonl: bool = False,
    missing_media_assets: list[str] | None = None,
) -> None:
    missing_media_assets = missing_media_assets or []
    payload = {
        "schema_version": "agentblaster.publication-bundle.v1",
        "run_id": "run-review",
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
        "publication_readiness": {
            "schema_version": "agentblaster.publication-readiness.v1",
            "status": status,
            "ready_for_external_publication": status == "ready",
            "ready_for_internal_review": status != "blocked",
            "blocker_count": 1 if status == "blocked" else 0,
            "warning_count": 1 if status == "review-required" else 0,
        },
        "security": {
            "contains_raw_secrets": False,
            "contains_raw_provider_payloads": False,
            "contains_results_jsonl": contains_results_jsonl,
        },
    }
    with ZipFile(path, "w") as archive:
        archive.writestr("publication-bundle-manifest.json", json.dumps(payload, sort_keys=True) + "\n")


def _write_matrix_publication_bundle(path, *, contains_results_jsonl: bool = False) -> None:
    stem = "qwen-gemma"
    payload = {
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
                "pass_rate_percent": 100,
                "avg_latency_ms": 100,
                "avg_decode_tokens_per_second": 42,
                "judge_rubric_cases": 2,
                "judge_verdicts_valid": 2,
                "invalid_tool_call_count": 0,
                "tool_parser_repair_cases": 0,
                "tool_parser_repairs_valid": 0,
                "tool_parser_repair_valid_rate_percent": None,
                "invalid_tool_call_count": 0,
                "tool_parser_repair_cases": 0,
                "tool_parser_repairs_valid": 0,
                "tool_parser_repair_valid_rate_percent": None,
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
                "pass_rate_percent": 100,
                "avg_latency_ms": 100,
                "avg_decode_tokens_per_second": 42,
                "judge_rubric_cases": 2,
                "judge_verdicts_valid": 2,
                "invalid_tool_call_count": 0,
                "tool_parser_repair_cases": 0,
                "tool_parser_repairs_valid": 0,
                "tool_parser_repair_valid_rate_percent": None,
                "invalid_tool_call_count": 0,
                "tool_parser_repair_cases": 0,
                "tool_parser_repairs_valid": 0,
                "tool_parser_repair_valid_rate_percent": None,
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
            "missing_recommended_assets": [],
            "recommended_sets": [{"name": "corporate-review-packet", "available": True}],
            "assets": [
                {"artifact": f"{stem}-matrix-scorecard.json", "role": "structured-scorecard", "media_type": "application/json", "present": True},
                {"artifact": f"{stem}-matrix-scorecard.pdf", "role": "executive-scorecard", "media_type": "application/pdf", "present": True},
                {"artifact": f"{stem}-matrix-scorecard.svg", "role": "scorecard-card-vector", "media_type": "image/svg+xml", "present": True},
            ],
        },
        "security": {
            "contains_raw_secrets": False,
            "contains_raw_provider_payloads": False,
            "contains_results_jsonl": contains_results_jsonl,
            "contains_per_run_raw_traces": False,
        },
    }
    with ZipFile(path, "w") as archive:
        archive.writestr("matrix-publication-bundle-manifest.json", json.dumps(payload, sort_keys=True) + "\n")


def test_release_qualification_bundle_packages_provider_audit_as_compact_summary(tmp_path) -> None:
    provider_audit = tmp_path / "provider-audit.json"
    provider_audit.write_text(
        json.dumps(
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
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    bundle = create_release_qualification_bundle(
        name="provider-security",
        output_dir=tmp_path / "release-bundles",
        provider_audits=[provider_audit],
    )

    with ZipFile(bundle) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        archived = json.loads(archive.read("security/provider-audit/provider-audit.json"))
    artifact = manifest["artifacts"][0]
    assert artifact["category"] == "security/provider-audit"
    assert artifact["schema"] == "agentblaster.provider-audit.v1"
    assert artifact["review_summary"]["warning_count"] == 1
    assert artifact["review_summary"]["keyring_required_provider_count"] == 1
    assert artifact["review_summary"]["secret_backend_posture"]["keyring_dependency_available"] is True
    assert artifact["review_summary"]["provider_auth_posture"][0]["api_key_ref_kind"] == "keyring"
    assert archived["redacted_for_release_qualification"] is True
    assert "do not copy" not in json.dumps(artifact["review_summary"])
    assert "do not copy" not in json.dumps(archived)


def test_create_release_qualification_bundle_packages_allowed_artifacts(tmp_path) -> None:
    evidence = tmp_path / "suite.agentblaster-evidence.zip"
    contract_check = tmp_path / "provider-contract-check.json"
    contract_matrix = tmp_path / "provider-contract-matrix.json"
    matrix_gate = tmp_path / "matrix-gate.json"
    comparison_gate = tmp_path / "comparison-gate.json"
    telemetry_audit = tmp_path / "telemetry-audit.json"
    matrix_pressure = tmp_path / "matrix-pressure.json"
    matrix_saturation = tmp_path / "matrix-saturation.json"
    matrix_scorecard = tmp_path / "matrix-scorecard.json"
    implementation_status = tmp_path / "implementation-status.json"
    campaign_preflight = tmp_path / "campaign-preflight-manifest.json"
    benchmark_readiness = tmp_path / "benchmark-readiness.json"
    claim_readiness = tmp_path / "claim-readiness.json"
    engine_advisory = tmp_path / "engine-advisory.json"
    evidence_index = tmp_path / "evidence-index.json"
    suite_audit = tmp_path / "suite-audit.json"
    metric_coverage = tmp_path / "metric-coverage.json"
    normalized_telemetry = tmp_path / "normalized-telemetry.json"
    provenance = tmp_path / "release-provenance.json"
    publication = tmp_path / "run.agentblaster-publication.zip"
    publication_brief = tmp_path / "publication-brief.json"
    matrix_publication = tmp_path / "qwen-gemma.agentblaster-matrix-publication.zip"
    harness_review = tmp_path / "harness-review.json"
    selftest = tmp_path / "selftest-report.json"
    sdlc_validation_manifest = tmp_path / "sdlc-validation-manifest.json"
    for path in [evidence]:
        path.write_bytes(b"zip-data")
    _write_matrix_publication_bundle(matrix_publication)
    _write_publication_bundle(publication)
    for path in [comparison_gate, telemetry_audit, claim_readiness, provenance]:
        path.write_text('{"ok": true}\n', encoding="utf-8")
    publication_brief.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.publication-brief.v1",
                "name": "afm-release",
                "ready": True,
                "claim_readiness": {"checks": 8, "blockers": 0, "warnings": 1},
                "proof_points": [{"claim": "not copied into release bundle"}],
                "disclosures": [{"detail": "not copied into release bundle"}],
                "recommended_language": {"headline": "not copied into release bundle"},
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
                    "source_artifact_count": 4,
                    "contains_raw_provider_payloads": False,
                    "contains_secrets": False,
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    sdlc_validation_manifest.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.sdlc-validation-manifest.v1",
                "name": "/private/worktrees/AgentBlaster/sdlc-validation-manifest.json",
                "summary": {
                    "tier_count": 4,
                    "required_gate_count": 7,
                    "blocking_gate_count": 3,
                    "chrome_flow_count": 2,
                    "chrome_validation_step_count": 9,
                },
                "gui": {
                    "chrome_tool": "Codex Chrome plugin",
                    "fixture_command": "not copied into release bundle",
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
    selftest.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.selftest-report.v1",
                "run_id": "selftest_20260531T000000Z",
                "tier": "normal",
                "marker_expression": "not remote and not slow and not gui",
                "duration_ms": 1000.0,
                "exit_code": 0,
                "ok": True,
                "junit_xml": "normal.junit.xml",
                "command": "not copied into review summary",
                "env": {"AGENTBLASTER_INTERNAL_VALUE": "not copied into review summary"},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    benchmark_readiness.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.benchmark-readiness.v1",
                "provider": "afm",
                "suite": "agentic-local",
                "model": "mlx-community/Qwen3.6-27B",
                "ready": True,
                "strict_unknown": True,
                "summary": {
                    "policy_ok": True,
                    "suite_compatible": True,
                    "contract_checks_planned": 5,
                    "contract_capabilities_directly_checked": 3,
                    "contract_capabilities_proxy_checked": 1,
                    "contract_capabilities_not_covered": 1,
                    "metric_coverage_score": 0.55,
                    "provider_auth_writable_backends": 1,
                    "provider_auth_plaintext_fallbacks": 1,
                    "provider_auth_prewrite_policy_guards_recommended": 1,
                    "blocking_findings": 0,
                    "warnings": 1,
                },
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
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    implementation_status.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.implementation-status.v1",
                "status": "implementation-ready-for-validation",
                "implemented_areas": 9,
                "partial_areas": 0,
                "missing_areas": 0,
                "project_root": "/private/worktrees/AgentBlaster",
                "areas": [{"id": "reporting-publication", "evidence": ["/private/worktrees/AgentBlaster/src/agentblaster/reports.py"]}],
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
    campaign_preflight.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.campaign-preflight-bundle.v1",
                "output_dir": "/private/campaign-preflight/qwen-gemma-local",
                "matrix_count": 1,
                "artifact_count": 4,
                "includes_provider_audit": False,
                "includes_benchmark_readiness": True,
                "benchmark_readiness": {
                    "artifact_path": "/private/worktrees/AgentBlaster/campaign-preflight/readiness/benchmark-readiness-index.json",
                    "report_count": 1,
                },
                "matrices": [
                    {
                        "matrix": "qwen-gemma-local",
                        "matrix_path": "/private/worktrees/AgentBlaster/campaigns/qwen-gemma-local.yaml",
                        "dry_run_command": [
                            "agentblaster",
                            "run",
                            "--matrix",
                            "/private/worktrees/AgentBlaster/campaigns/qwen-gemma-local.yaml",
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
                    "reads_keyring_values": False,
                    "contains_raw_secrets": False,
                    "contains_raw_provider_payloads": False,
                    "contains_raw_traces": False,
                    "contains_local_paths": True,
                    "external_publication_safe": False,
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    matrix_saturation.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.matrix-saturation.v1",
                "ok": True,
                "matrix": {"name": "qwen-gemma-local"},
                "summary": {
                    "entry_count": 2,
                    "group_count": 1,
                    "result_artifacts_loaded": 2,
                    "result_artifacts_missing": 0,
                    "max_concurrency": 4,
                },
                "concurrency_evidence": {
                    "multi_level_group_count": 1,
                    "concurrency_levels": [1, 4],
                    "max_concurrency": 4,
                    "max_avg_queue_ms": 80.0,
                    "max_avg_rate_limit_wait_ms": 55.0,
                    "queue_wait_finding_count": 1,
                    "rate_limit_wait_finding_count": 1,
                    "guidance": "review-scheduler-queueing-and-provider-pacing-before-publication",
                    "highest_queue_wait_entries": [
                        {
                            "group_id": "afm/afm/qwen-test/prefill",
                            "run_id": "afm-c4",
                            "engine": "afm",
                            "provider": "afm",
                            "model": "qwen-test",
                            "suite": "prefill",
                            "concurrency": 4,
                            "rank_metric": "avg_queue_ms",
                            "rank_value": 80.0,
                            "avg_queue_ms": 80.0,
                            "avg_rate_limit_wait_ms": 55.0,
                        }
                    ],
                },
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
                    "engine_targets": [
                        {"id": "afm-mlx", "display_name": "AFM MLX", "primary_scoring_contract": "openai"}
                    ],
                    "judge_rubric_cases": 2,
                    "judge_verdicts_valid": 2,
                    "failure_class_summary": [],
                    "tool_loop_stop_summary": [{"stop_reason": "final_response", "count": 2}],
                    "telemetry_quality_summary": {
                        "quality_counts": {"native": 3, "measured": 9, "inferred": 1},
                        "guidance_counts": {
                            "label-inferred-or-conditional-fields-before-cross-engine-comparison": 1
                        },
                        "entries_with_advisory_quality": 1,
                        "entries_with_unknown_quality": 0,
                        "entries_with_comparison_guidance": 1,
                    },
                    "stats_comparability_summary": {
                        "schema_version": "agentblaster.scorecard-stats-comparability.v1",
                        "profile_counts": {"afm-mlx-openai-compatible": 1},
                        "guidance_counts": {
                            "publish-native-and-measured-fields-separately-from-inferred-conditional-or-missing-stats": 1
                        },
                        "entries_requiring_labeling": 1,
                    },
                    "concurrency_evidence": {
                        "schema_version": "agentblaster.scorecard-concurrency-evidence.v1",
                        "entry_count": 2,
                        "artifact_loaded_count": 2,
                        "concurrency_levels": [1, 4],
                        "multi_level": True,
                        "max_concurrency": 4,
                        "max_avg_queue_ms": 12.0,
                        "max_avg_rate_limit_wait_ms": 3.0,
                        "guidance": "review-queue-and-rate-limit-pressure-before-publication",
                        "highest_queue_wait_entries": [
                            {
                                "engine": "afm",
                                "provider": "afm",
                                "model": "qwen-test",
                                "suite": "prefill",
                                "run_id": "afm-c4",
                                "concurrency": 4,
                                "rank_metric": "avg_queue_ms",
                                "rank_value": 12.0,
                                "avg_queue_ms": 12.0,
                                "avg_rate_limit_wait_ms": 3.0,
                            }
                        ],
                    },
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
                "entries": [{"run_id": "not-copied", "raw_response_path": "raw/not-copied.response.json"}],
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
                "matrix": "qwen-gemma-local",
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
                        "largest_cases": [{"case_id": "not-copied"}],
                    }
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    contract_check.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.provider-contract-check.v1",
                "ok": True,
                "mode": "executed",
                "provider": {"name": "afm", "contract": "openai"},
                "model": "qwen-test",
                "summary": {"planned": 5, "passed": 5, "failed": 0, "skipped": 0},
                "capability_evidence": {
                    "directly_checked": ["streaming", "structured_output", "tool_calling"],
                    "proxy_checked": [{"capability": "judge_rubric", "covered_by": "structured_output"}],
                    "not_covered": [],
                },
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
                "matrix": {"name": "qwen-gemma-local", "target_count": 2},
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
    engine_advisory.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.engine-improvement-advisory.v1",
                "engine": "afm",
                "summary": {"priority_count": 2, "highest_priority": 1, "no_dispatch": True},
                "priorities": [
                    {
                        "priority": 1,
                        "area": "contract-conformance",
                        "reason": "not copied into release review summary",
                        "aligned_artifacts_or_suites": ["providers contract-check", "matrix contract-checks"],
                    },
                    {
                        "priority": 2,
                        "area": "harness-calibration",
                        "reason": "not copied into release review summary",
                        "aligned_artifacts_or_suites": ["harness review", "suite-calibration"],
                    },
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    evidence_index.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.evidence-index.v1",
                "name": "afm-release",
                "artifact_count": 2,
                "status_counts": {"fail": 1, "review": 1},
                "readiness": {
                    "ready": False,
                    "state": "blocked",
                    "blocking_artifact_count": 1,
                    "review_artifact_count": 1,
                    "blocking_statuses": ["fail"],
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
                "description": "Agentic local workflow suite.",
                "total_cases": 4,
                "provenance_counts": {"synthetic_representative": 4},
                "risk_counts": {"medium": 4},
                "scenario_counts": {"tool-loop": 4},
                "capability_surfaces": {"tool_schema_names": ["lookup_fixture"]},
                "dataset_hygiene": {"duplicate_fingerprint_count": 1},
                "findings": [
                    {"severity": "warning", "case_id": "case-a,case-b", "code": "duplicate_case_fingerprint", "message": "not copied"}
                ],
                "security_notes": [],
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
    normalized_telemetry.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.normalized-telemetry.v1",
                "contract": "openai",
                "native_adapter": "rapid-mlx",
                "stats_profile": "rapid-mlx-openai-compatible",
                "values": {
                    "input_tokens": 100,
                    "prompt_eval_ms": 500.0,
                    "raw_usage": {"private_provider_usage": "not copied into release bundle"},
                    "raw_stats": {"private_provider_debug": "not copied into release bundle"},
                },
                "sources": {"prompt_eval_ms": "stats/metrics.prefill_seconds"},
                "quality": {
                    "input_tokens": "native",
                    "prompt_eval_ms": "native",
                    "raw_usage": "raw_provenance",
                    "raw_stats": "raw_provenance",
                },
                "comparison_readiness": {
                    "publication_grade_field_count": 2,
                    "advisory_field_count": 0,
                    "raw_provenance_field_count": 2,
                    "guidance": "publication-grade-for-present-fields-when-run-telemetry-audit-passes",
                },
                "stats_comparability": {
                    "requires_labeling": True,
                    "guidance": "publish-native-and-measured-fields-separately-from-inferred-conditional-or-missing-stats",
                    "publication_grade_fields": ["prompt_eval_ms"],
                    "advisory_fields": [],
                    "missing_stats_fields": ["decode_ms"],
                },
                "missing": ["decode_ms"],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    matrix_gate.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.matrix-gate.v1",
                "ok": True,
                "matrix_name": "qwen-gemma-local",
                "pass_rate_percent": 98.0,
                "failure_class_summary": [{"failure_class": "model_quality", "count": 2}],
                "failure_class_artifacts_missing": 0,
                "tool_loop_stop_summary": [{"stop_reason": "completed", "count": 3}],
                "tool_loop_artifacts_missing": 0,
                "invalid_tool_call_count": 0,
                "tool_parser_repair_cases": 2,
                "tool_parser_repairs_valid": 2,
                "tool_parser_repair_valid_rate_percent": 100.0,
                "tool_parser_repair_artifacts_missing": 0,
                "findings": [],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    harness_review.write_text(
        json.dumps(
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
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    output = create_release_qualification_bundle(
        name="afm-release",
        output_dir=tmp_path / "release-bundles",
        evidence_bundles=[evidence],
        provider_contract_checks=[contract_check],
        provider_contract_matrices=[contract_matrix],
        comparison_gates=[comparison_gate],
        matrix_gates=[matrix_gate],
        telemetry_audits=[telemetry_audit],
        matrix_pressure_audits=[matrix_pressure],
        matrix_saturation_reports=[matrix_saturation],
        matrix_scorecards=[matrix_scorecard],
        implementation_status_reports=[implementation_status],
        campaign_preflight_manifests=[campaign_preflight],
        benchmark_readiness_reports=[benchmark_readiness],
        claim_readiness_reports=[claim_readiness],
        engine_advisories=[engine_advisory],
        evidence_indexes=[evidence_index],
        suite_audits=[suite_audit],
        metric_coverage_reports=[metric_coverage],
        normalized_telemetry_reports=[normalized_telemetry],
        release_provenance=provenance,
        publication_bundles=[publication],
        publication_briefs=[publication_brief],
        matrix_publication_bundles=[matrix_publication],
        harness_reviews=[harness_review],
        selftest_reports=[selftest],
        sdlc_validation_manifests=[sdlc_validation_manifest],
    )

    assert output.name == "afm-release.agentblaster-release-qualification.zip"
    with ZipFile(output) as archive:
        names = sorted(archive.namelist())
        assert names == [
            "advisory/engine/engine-advisory.json",
            "audits/matrix-pressure/matrix-pressure.json",
            "audits/matrix-saturation/matrix-saturation.json",
            "audits/provider-contract-matrix/provider-contract-matrix.json",
            "audits/provider-contract/provider-contract-check.json",
            "audits/telemetry/telemetry-audit.json",
            "evidence/index/evidence-index.json",
            "evidence/suite.agentblaster-evidence.zip",
            "gates/comparison/comparison-gate.json",
            "gates/matrix/matrix-gate.json",
            "governance/suite-audit/suite-audit.json",
            "harness/review/harness-review.json",
            "manifest.json",
            "metrics/coverage/metric-coverage.json",
            "metrics/normalized-telemetry/normalized-telemetry.json",
            "publication/brief/publication-brief.json",
            "publication/matrix/qwen-gemma.agentblaster-matrix-publication.zip",
            "publication/run.agentblaster-publication.zip",
            "readiness/benchmark/benchmark-readiness.json",
            "readiness/campaign-preflight/campaign-preflight-manifest.json",
            "readiness/claim/claim-readiness.json",
            "readiness/implementation/implementation-status.json",
            "release/release-provenance.json",
            "reports/matrix-scorecard/matrix-scorecard.json",
            "selftest/selftest-report.json",
            "selftest/validation-manifest/sdlc-validation-manifest.json",
        ]
        manifest = json.loads(archive.read("manifest.json"))
        archived_implementation_status = json.loads(
            archive.read("readiness/implementation/implementation-status.json")
        )
        archived_campaign_preflight = json.loads(
            archive.read("readiness/campaign-preflight/campaign-preflight-manifest.json")
        )
        archived_normalized_telemetry = json.loads(
            archive.read("metrics/normalized-telemetry/normalized-telemetry.json")
        )
        archived_publication_brief = json.loads(archive.read("publication/brief/publication-brief.json"))
        archived_sdlc_validation_manifest = json.loads(
            archive.read("selftest/validation-manifest/sdlc-validation-manifest.json")
        )
    assert manifest["schema"] == "agentblaster.release-qualification-bundle"
    assert manifest["ok"] is True
    assert manifest["artifact_count"] == 25
    assert manifest["artifact_status"]["pass"] == 15
    assert manifest["artifact_status"]["not-opened"] == 1
    assert manifest["artifact_status"]["review"] == 9
    assert "fail" in manifest["blocking_statuses"]
    assert manifest["security"]["contains_raw_traces"] is False
    manifest_artifacts = {artifact["archive_path"]: artifact for artifact in manifest["artifacts"]}
    assert manifest_artifacts["audits/provider-contract-matrix/provider-contract-matrix.json"]["status"] == "pass"
    assert manifest_artifacts["audits/provider-contract/provider-contract-check.json"]["review_summary"][
        "capability_evidence"
    ]["proxy_checked_counts"] == {"judge_rubric": 1}
    assert manifest_artifacts["audits/provider-contract-matrix/provider-contract-matrix.json"]["review_summary"][
        "capability_evidence"
    ]["not_covered_counts"] == {"prompt_caching": 1}
    assert manifest_artifacts["selftest/selftest-report.json"]["schema"] == "agentblaster.selftest-report.v1"
    assert manifest_artifacts["selftest/selftest-report.json"]["review_summary"]["tier"] == "normal"
    assert manifest_artifacts["selftest/selftest-report.json"]["review_summary"]["junit_xml_present"] is True
    assert "AGENTBLASTER_INTERNAL_VALUE" not in json.dumps(manifest_artifacts["selftest/selftest-report.json"]["review_summary"])
    assert manifest_artifacts["readiness/benchmark/benchmark-readiness.json"]["schema"] == "agentblaster.benchmark-readiness.v1"
    assert manifest_artifacts["readiness/benchmark/benchmark-readiness.json"]["review_summary"][
        "provider_auth_plaintext_fallbacks"
    ] == 1
    assert manifest_artifacts["readiness/benchmark/benchmark-readiness.json"]["review_summary"]["provider_auth_posture"] == [
        {
            "provider": "afm",
            "api_key_ref_kind": "dotenv",
            "api_key_ref_configured": True,
            "api_key_ref_writable_backend": True,
            "api_key_ref_plaintext_fallback": True,
            "prewrite_policy_guard_recommended": True,
        }
    ]
    assert manifest_artifacts["readiness/implementation/implementation-status.json"]["schema"] == "agentblaster.implementation-status.v1"
    assert manifest_artifacts["readiness/implementation/implementation-status.json"]["source_path"] == "implementation-status.json"
    assert manifest_artifacts["readiness/implementation/implementation-status.json"]["source_path_redacted"] is True
    assert manifest_artifacts["readiness/implementation/implementation-status.json"]["status"] == "pass"
    assert manifest_artifacts["readiness/implementation/implementation-status.json"]["review_summary"][
        "implementation_status"
    ] == "implementation-ready-for-validation"
    assert manifest_artifacts["readiness/implementation/implementation-status.json"]["review_summary"]["missing_areas"] == 0
    assert manifest_artifacts["readiness/implementation/implementation-status.json"]["review_summary"]["harness_engineering_case_count"] == 4
    assert manifest_artifacts["readiness/implementation/implementation-status.json"]["review_summary"]["stats_profile_count"] == 8
    assert "private/worktrees" not in json.dumps(
        manifest_artifacts["readiness/implementation/implementation-status.json"]["review_summary"]
    )
    assert archived_implementation_status["project_root"] == "<redacted>"
    assert archived_implementation_status["project_root_redacted"] is True
    assert archived_implementation_status["areas"][0]["evidence"] == ["<redacted-path>"]
    assert "private/worktrees" not in json.dumps(archived_implementation_status)
    campaign_preflight_summary = manifest_artifacts[
        "readiness/campaign-preflight/campaign-preflight-manifest.json"
    ]["review_summary"]
    assert campaign_preflight_summary["schema_version"] == "agentblaster.campaign-preflight-bundle.v1"
    assert campaign_preflight_summary["run_count"] == 2
    assert campaign_preflight_summary["total_cases"] == 8
    assert campaign_preflight_summary["contains_local_paths"] is False
    assert campaign_preflight_summary["external_publication_safe"] is True
    assert archived_campaign_preflight["redacted_for_release_qualification"] is True
    assert archived_campaign_preflight["benchmark_readiness"]["artifact_path"] == "<redacted-path>"
    assert archived_campaign_preflight["security"]["contains_local_paths"] is False
    assert "private/worktrees" not in json.dumps(archived_campaign_preflight)
    assert manifest_artifacts["gates/matrix/matrix-gate.json"]["schema"] == "agentblaster.matrix-gate.v1"
    assert manifest_artifacts["gates/matrix/matrix-gate.json"]["review_summary"] == {
        "schema_version": "agentblaster.matrix-gate.v1",
        "failure_class_summary": [{"failure_class": "model_quality", "count": 2}],
        "failure_class_artifacts_missing": 0,
        "tool_loop_stop_summary": [{"stop_reason": "completed", "count": 3}],
        "tool_loop_artifacts_missing": 0,
        "invalid_tool_call_count": 0,
        "tool_parser_repair_cases": 2,
        "tool_parser_repairs_valid": 2,
        "tool_parser_repair_valid_rate_percent": 100.0,
        "matrix_name": "qwen-gemma-local",
        "pass_rate_percent": 98.0,
    }
    assert manifest_artifacts["evidence/suite.agentblaster-evidence.zip"]["schema"] == "agentblaster.evidence-bundle"
    assert manifest_artifacts["publication/run.agentblaster-publication.zip"]["schema"] == "agentblaster.publication-bundle"
    assert manifest_artifacts["publication/run.agentblaster-publication.zip"]["manifest_schema"] == "agentblaster.publication-bundle.v1"
    assert manifest_artifacts["publication/run.agentblaster-publication.zip"]["status"] == "pass"
    assert manifest_artifacts["publication/run.agentblaster-publication.zip"]["status_source"] == "publication-manifest.publication_readiness.status"
    assert manifest_artifacts["publication/run.agentblaster-publication.zip"]["review_summary"] == {
        "schema_version": "agentblaster.publication-bundle.v1",
        "run_id": "run-review",
        "artifact_count": 4,
        "artifacts": ["summary.json", "publication.json", "report-card.svg", "integrity.json"],
        "media_kit": {
            "schema_version": "agentblaster.media-kit.v1",
            "asset_count": 4,
            "missing_recommended_assets": [],
            "available_recommended_sets": ["corporate-review-packet"],
            "asset_roles": [
                {
                    "artifact": "publication.json",
                    "role": "structured-run-evidence",
                    "media_type": "application/json",
                    "present": True,
                },
                {
                    "artifact": "report-card.svg",
                    "role": "social-card-vector",
                    "media_type": "image/svg+xml",
                    "present": True,
                },
            ],
        },
        "publication_readiness": {
            "schema_version": "agentblaster.publication-readiness.v1",
            "status": "ready",
            "ready_for_external_publication": True,
            "ready_for_internal_review": True,
            "blocker_count": 0,
            "warning_count": 0,
        },
        "security": {
            "contains_raw_secrets": False,
            "contains_raw_provider_payloads": False,
            "contains_results_jsonl": False,
        },
    }
    assert manifest_artifacts["publication/brief/publication-brief.json"]["schema"] == "agentblaster.publication-brief.v1"
    assert manifest_artifacts["publication/brief/publication-brief.json"]["status"] == "pass"
    assert manifest_artifacts["publication/brief/publication-brief.json"]["review_summary"] == {
        "schema_version": "agentblaster.publication-brief.v1",
        "status": "pass",
        "name": "afm-release",
        "ready": True,
        "source_artifact_count": 4,
        "proof_point_count": 1,
        "disclosure_count": 1,
        "matrix_scorecard_count": 1,
        "engine_targets": [
            {"id": "afm-mlx", "display_name": "AFM MLX", "primary_scoring_contract": "openai"}
        ],
        "architecture_summary": [
            {
                "model_architecture": "qwen3.6-dense",
                "runs": 2,
                "failed_runs": 0,
                "completed_runs": 2,
                "result_artifacts_loaded": 2,
                "total_cases": 10,
                "passed": 10,
                "failed": 0,
                "pass_rate_percent": 100,
                "avg_latency_ms": 100,
                "avg_decode_tokens_per_second": 42,
                "judge_rubric_cases": 2,
                "judge_verdicts_valid": 2,
                "invalid_tool_call_count": 0,
                "tool_parser_repair_cases": 0,
                "tool_parser_repairs_valid": 0,
                "tool_parser_repair_valid_rate_percent": None,
            }
        ],
        "quantization_summary": [
            {
                "quantization": "mlx-f16",
                "runs": 2,
                "failed_runs": 0,
                "completed_runs": 2,
                "result_artifacts_loaded": 2,
                "total_cases": 10,
                "passed": 10,
                "failed": 0,
                "pass_rate_percent": 100,
                "avg_latency_ms": 100,
                "avg_decode_tokens_per_second": 42,
                "judge_rubric_cases": 2,
                "judge_verdicts_valid": 2,
                "invalid_tool_call_count": 0,
                "tool_parser_repair_cases": 0,
                "tool_parser_repairs_valid": 0,
                "tool_parser_repair_valid_rate_percent": None,
            }
        ],
        "claim_checks": 8,
        "claim_blockers": 0,
        "claim_warnings": 1,
        "contains_raw_provider_payloads": False,
        "contains_secrets": False,
        "shareable_summary_only": True,
    }
    assert archived_publication_brief["redacted_for_release_qualification"] is True
    assert archived_publication_brief["security"]["includes_proof_point_text"] is False
    assert archived_publication_brief["security"]["includes_recommended_language"] is False
    assert "not copied into release bundle" not in json.dumps(archived_publication_brief)
    assert manifest_artifacts["publication/matrix/qwen-gemma.agentblaster-matrix-publication.zip"]["schema"] == "agentblaster.matrix-publication-bundle"
    assert manifest_artifacts["publication/matrix/qwen-gemma.agentblaster-matrix-publication.zip"]["status"] == "pass"
    assert manifest_artifacts["publication/matrix/qwen-gemma.agentblaster-matrix-publication.zip"]["review_summary"]["media_kit"]["missing_recommended_assets"] == []
    assert manifest_artifacts["publication/run.agentblaster-publication.zip"]["review_summary"]["media_kit"]["missing_recommended_assets"] == []
    assert manifest_artifacts["harness/review/harness-review.json"]["schema"] == "agentblaster.harness-review.v1"
    assert manifest_artifacts["harness/review/harness-review.json"]["review_summary"]["generator_profile"] == "orchestration"
    assert manifest_artifacts["harness/review/harness-review.json"]["review_summary"]["calibration_required_before_release_gate"] is True
    assert manifest_artifacts["harness/review/harness-review.json"]["review_summary"]["surface_counts"] == {
        "multi_tool_catalog_cases": 4,
        "tool_loop_cases": 4,
    }
    assert manifest_artifacts["advisory/engine/engine-advisory.json"]["review_summary"]["engine"] == "afm"
    assert manifest_artifacts["advisory/engine/engine-advisory.json"]["review_summary"]["priority_count"] == 2
    assert manifest_artifacts["advisory/engine/engine-advisory.json"]["review_summary"]["top_priorities"][0] == {
        "priority": 1,
        "area": "contract-conformance",
        "aligned_artifacts_or_suites": ["providers contract-check", "matrix contract-checks"],
    }
    assert "reason" not in manifest_artifacts["advisory/engine/engine-advisory.json"]["review_summary"]["top_priorities"][0]
    assert manifest_artifacts["evidence/index/evidence-index.json"]["schema"] == "agentblaster.evidence-index.v1"
    assert manifest_artifacts["evidence/index/evidence-index.json"]["review_summary"] == {
        "schema_version": "agentblaster.evidence-index.v1",
        "name": "afm-release",
        "artifact_count": 2,
        "status_counts": {"fail": 1, "review": 1},
        "readiness": {
            "ready": False,
            "state": "blocked",
            "blocking_artifact_count": 1,
            "review_artifact_count": 1,
            "blocking_statuses": ["fail"],
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
    }
    assert manifest_artifacts["governance/suite-audit/suite-audit.json"]["schema"] == "agentblaster.suite-audit.v1"
    assert manifest_artifacts["governance/suite-audit/suite-audit.json"]["review_summary"] == {
        "schema_version": "agentblaster.suite-audit.v1",
        "suite": "agentic-local",
        "total_cases": 4,
        "finding_count": 1,
        "finding_codes": ["duplicate_case_fingerprint"],
        "provenance_counts": {"synthetic_representative": 4},
        "risk_counts": {"medium": 4},
        "duplicate_fingerprint_count": 1,
    }
    assert manifest_artifacts["metrics/coverage/metric-coverage.json"]["schema"] == "agentblaster.metric-coverage.v1"
    assert manifest_artifacts["metrics/coverage/metric-coverage.json"]["review_summary"] == {
        "schema_version": "agentblaster.metric-coverage.v1",
        "provider": "afm",
        "contract": "openai",
        "native_adapter": None,
        "coverage_score": 0.55,
        "field_count": 24,
        "counts": {"native": 3, "measured": 9, "inferred": 1, "conditional": 2, "unavailable": 9},
        "publication_grade_group_count": 1,
        "advisory_group_count": 1,
        "partial_group_count": 2,
        "unavailable_group_count": 0,
        "publication_grade_groups": ["agent_protocol_behavior"],
        "review_required_groups": ["timing_and_throughput", "token_and_cache_accounting"],
        "claim_contract": {
            "schema_version": None,
            "primary_score_policy": None,
            "leaderboard_eligible_groups": [],
            "disclosure_required_groups": [],
            "claim_status_counts": {},
        },
    }
    assert manifest_artifacts["metrics/normalized-telemetry/normalized-telemetry.json"]["schema"] == "agentblaster.normalized-telemetry.v1"
    assert manifest_artifacts["metrics/normalized-telemetry/normalized-telemetry.json"]["status"] == "review"
    assert manifest_artifacts["metrics/normalized-telemetry/normalized-telemetry.json"]["review_summary"] == {
        "schema_version": "agentblaster.normalized-telemetry.v1",
        "contract": "openai",
        "native_adapter": "rapid-mlx",
        "stats_profile": "rapid-mlx-openai-compatible",
        "populated_field_count": 2,
        "missing_field_count": 1,
        "publication_grade_field_count": 2,
        "advisory_field_count": 0,
        "raw_provenance_field_count": 2,
        "comparison_guidance": "publication-grade-for-present-fields-when-run-telemetry-audit-passes",
        "quality_counts": {"native": 2, "raw_provenance": 2},
        "stats_requires_labeling": True,
        "stats_guidance": "publish-native-and-measured-fields-separately-from-inferred-conditional-or-missing-stats",
        "stats_publication_grade_fields": ["prompt_eval_ms"],
        "stats_advisory_fields": [],
        "missing_stats_fields": ["decode_ms"],
    }
    assert archived_normalized_telemetry["redacted_for_release_qualification"] is True
    assert archived_normalized_telemetry["review_summary"]["stats_profile"] == "rapid-mlx-openai-compatible"
    assert archived_normalized_telemetry["security"]["includes_raw_usage"] is False
    assert archived_normalized_telemetry["security"]["includes_raw_stats"] is False
    assert archived_normalized_telemetry["security"]["includes_source_maps"] is False
    assert "not copied into release bundle" not in json.dumps(archived_normalized_telemetry)
    assert "sources" not in json.dumps(archived_normalized_telemetry)
    sdlc_archive_path = "selftest/validation-manifest/sdlc-validation-manifest.json"
    assert manifest_artifacts[sdlc_archive_path]["schema"] == "agentblaster.sdlc-validation-manifest.v1"
    assert manifest_artifacts[sdlc_archive_path]["status"] == "review"
    assert manifest_artifacts[sdlc_archive_path]["review_summary"]["name"] == "sdlc-validation-manifest.json"
    assert manifest_artifacts[sdlc_archive_path]["review_summary"]["chrome_validation_step_count"] == 9
    assert manifest_artifacts[sdlc_archive_path]["review_summary"]["expected_artifact_count"] == 2
    assert archived_sdlc_validation_manifest["redacted_for_release_qualification"] is True
    assert archived_sdlc_validation_manifest["security"]["includes_command_output"] is False
    assert "not copied into release bundle" not in json.dumps(archived_sdlc_validation_manifest)
    assert "private/worktrees" not in json.dumps(archived_sdlc_validation_manifest)
    assert manifest_artifacts["audits/matrix-pressure/matrix-pressure.json"]["schema"] == "agentblaster.matrix-pressure-audit.v1"
    assert manifest_artifacts["audits/matrix-pressure/matrix-pressure.json"]["status"] == "review"
    assert manifest_artifacts["audits/matrix-pressure/matrix-pressure.json"]["review_summary"] == {
        "schema_version": "agentblaster.matrix-pressure-audit.v1",
        "matrix": "qwen-gemma-local",
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
    }
    assert "largest_cases" not in json.dumps(manifest_artifacts["audits/matrix-pressure/matrix-pressure.json"]["review_summary"])
    saturation_summary = manifest_artifacts["audits/matrix-saturation/matrix-saturation.json"]["review_summary"]
    assert saturation_summary["schema_version"] == "agentblaster.matrix-saturation.v1"
    assert saturation_summary["matrix"] == "qwen-gemma-local"
    assert saturation_summary["max_concurrency"] == 4
    assert saturation_summary["multi_level_group_count"] == 1
    assert saturation_summary["max_avg_queue_ms"] == 80
    assert saturation_summary["queue_wait_finding_count"] == 1
    assert saturation_summary["highest_queue_wait_entries"][0]["run_id"] == "afm-c4"
    scorecard_summary = manifest_artifacts["reports/matrix-scorecard/matrix-scorecard.json"]["review_summary"]
    assert scorecard_summary["schema_version"] == "agentblaster-matrix-scorecard-v1"
    assert scorecard_summary["matrix"] == "qwen-gemma-local"
    assert scorecard_summary["pass_rate_percent"] == 100
    assert scorecard_summary["invalid_tool_call_count"] == 0
    assert scorecard_summary["tool_parser_repair_cases"] == 0
    assert scorecard_summary["tool_parser_repairs_valid"] == 0
    assert scorecard_summary["tool_parser_repair_valid_rate_percent"] is None
    assert scorecard_summary["engine_targets"] == [
        {"id": "afm-mlx", "display_name": "AFM MLX", "primary_scoring_contract": "openai"}
    ]
    assert scorecard_summary["architecture_summary"][0]["model_architecture"] == "qwen3.6-dense"
    assert scorecard_summary["architecture_summary"][0]["tool_parser_repair_cases"] == 0
    assert scorecard_summary["quantization_summary"][0]["quantization"] == "mlx-f16"
    assert scorecard_summary["quantization_summary"][0]["tool_parser_repair_cases"] == 0
    assert scorecard_summary["telemetry_quality_summary"]["quality_counts"] == {
        "inferred": 1,
        "measured": 9,
        "native": 3,
    }
    assert scorecard_summary["stats_comparability_summary"]["profile_counts"] == {"afm-mlx-openai-compatible": 1}
    assert scorecard_summary["concurrency_evidence"]["concurrency_levels"] == [1, 4]
    assert scorecard_summary["concurrency_evidence"]["highest_queue_wait_entries"][0]["run_id"] == "afm-c4"
    assert "raw_response_path" not in json.dumps(scorecard_summary)
    matrix_publication_summary = manifest_artifacts[
        "publication/matrix/qwen-gemma.agentblaster-matrix-publication.zip"
    ]["review_summary"]
    assert matrix_publication_summary["engine_targets"] == [
        {"id": "afm-mlx", "display_name": "AFM MLX", "primary_scoring_contract": "openai"}
    ]
    assert matrix_publication_summary["architecture_summary"][0]["model_architecture"] == "qwen3.6-dense"
    assert matrix_publication_summary["quantization_summary"][0]["quantization"] == "mlx-f16"


def test_create_release_qualification_bundle_rejects_raw_results(tmp_path) -> None:
    raw_results = tmp_path / "results.jsonl"
    raw_results.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="raw run artifacts are not allowed"):
        create_release_qualification_bundle(
            name="bad-release",
            output_dir=tmp_path / "release-bundles",
            matrix_gates=[raw_results],
        )


def test_release_qualification_bundle_blocks_unsafe_publication_bundle(tmp_path) -> None:
    publication = tmp_path / "run.agentblaster-publication.zip"
    _write_publication_bundle(publication, contains_results_jsonl=True)

    output = create_release_qualification_bundle(
        name="unsafe-publication",
        output_dir=tmp_path / "release-bundles",
        publication_bundles=[publication],
    )

    with ZipFile(output) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    artifact = manifest["artifacts"][0]
    assert manifest["ok"] is False
    assert manifest["artifact_status"]["fail"] == 1
    assert artifact["status"] == "fail"
    assert artifact["status_source"] == "publication-manifest.security"
    assert artifact["review_summary"]["security"]["contains_results_jsonl"] is True


def test_release_qualification_bundle_reviews_publication_bundle_missing_media_assets(tmp_path) -> None:
    publication = tmp_path / "run.agentblaster-publication.zip"
    _write_publication_bundle(publication, missing_media_assets=["report.pdf"])

    output = create_release_qualification_bundle(
        name="media-review",
        output_dir=tmp_path / "release-bundles",
        publication_bundles=[publication],
    )

    with ZipFile(output) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    artifact = manifest["artifacts"][0]
    assert manifest["ok"] is True
    assert artifact["status"] == "review"
    assert artifact["status_source"] == "publication-manifest.media_kit.missing_recommended_assets"
    assert artifact["review_summary"]["media_kit"]["missing_recommended_assets"] == ["report.pdf"]


def test_release_qualification_bundle_marks_failed_evidence_not_ok(tmp_path) -> None:
    matrix_gate = tmp_path / "matrix-gate.json"
    matrix_gate.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.matrix-gate.v1",
                "ok": False,
                "failure_class_summary": [{"failure_class": "engine_protocol_bug", "count": 1}],
                "failure_class_artifacts_missing": 1,
                "tool_loop_stop_summary": [{"stop_reason": "max_tool_calls_reached", "count": 1}],
                "tool_loop_artifacts_missing": 1,
                "judge_rubric_cases": 2,
                "judge_verdicts_valid": 1,
                "judge_verdict_valid_rate_percent": 50.0,
                "judge_verdict_artifacts_missing": 1,
                "invalid_tool_call_count": 1,
                "tool_parser_repair_cases": 2,
                "tool_parser_repairs_valid": 1,
                "tool_parser_repair_valid_rate_percent": 50.0,
                "tool_parser_repair_artifacts_missing": 1,
                "findings": [
                    {
                        "metric": "failure_class.engine_protocol_bug",
                        "actual": 1,
                        "threshold": 0,
                        "message": "engine protocol bug gate failed",
                    },
                    {
                        "metric": "tool_loop_stop_reason.max_tool_calls_reached",
                        "actual": 1,
                        "threshold": 0,
                        "message": "tool-loop gate failed",
                    },
                    {
                        "metric": "judge_verdict_valid_rate",
                        "actual": 50.0,
                        "threshold": 95.0,
                        "message": "judge verdict gate failed",
                    },
                    {
                        "metric": "invalid_tool_calls",
                        "actual": 1,
                        "threshold": 0,
                        "message": "invalid tool call gate failed",
                    },
                    {
                        "metric": "tool_parser_repair_valid_rate",
                        "actual": 50.0,
                        "threshold": 95.0,
                        "message": "tool parser repair gate failed",
                    },
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    output = create_release_qualification_bundle(
        name="failed-release",
        output_dir=tmp_path / "release-bundles",
        matrix_gates=[matrix_gate],
    )

    with ZipFile(output) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["ok"] is False
    assert manifest["artifact_status"]["fail"] == 1
    artifact = manifest["artifacts"][0]
    assert artifact["review_summary"]["failure_class_summary"] == [
        {"failure_class": "engine_protocol_bug", "count": 1}
    ]
    assert artifact["review_summary"]["schema_version"] == "agentblaster.matrix-gate.v1"
    assert artifact["review_summary"]["failure_class_artifacts_missing"] == 1
    assert artifact["review_summary"]["tool_loop_stop_summary"] == [
        {"stop_reason": "max_tool_calls_reached", "count": 1}
    ]
    assert artifact["review_summary"]["tool_loop_artifacts_missing"] == 1
    assert artifact["review_summary"]["failure_class_gate_count"] == 1
    assert artifact["review_summary"]["failure_class_gate_findings"][0]["metric"] == "failure_class.engine_protocol_bug"
    assert "message" not in artifact["review_summary"]["failure_class_gate_findings"][0]
    assert artifact["review_summary"]["tool_loop_stop_gate_count"] == 1
    assert artifact["review_summary"]["tool_loop_stop_gate_findings"][0]["metric"] == "tool_loop_stop_reason.max_tool_calls_reached"
    assert artifact["review_summary"]["tool_loop_stop_gate_findings"][0]["stop_reason"] == "max_tool_calls_reached"
    assert "message" not in artifact["review_summary"]["tool_loop_stop_gate_findings"][0]
    assert artifact["review_summary"]["judge_rubric_cases"] == 2
    assert artifact["review_summary"]["judge_verdicts_valid"] == 1
    assert artifact["review_summary"]["judge_verdict_valid_rate_percent"] == 50.0
    assert artifact["review_summary"]["judge_verdict_artifacts_missing"] == 1
    assert artifact["review_summary"]["judge_verdict_gate_count"] == 1
    assert artifact["review_summary"]["judge_verdict_gate_findings"][0]["metric"] == "judge_verdict_valid_rate"
    assert "message" not in artifact["review_summary"]["judge_verdict_gate_findings"][0]
    assert artifact["review_summary"]["invalid_tool_call_count"] == 1
    assert artifact["review_summary"]["tool_parser_repair_cases"] == 2
    assert artifact["review_summary"]["tool_parser_repairs_valid"] == 1
    assert artifact["review_summary"]["tool_parser_repair_valid_rate_percent"] == 50.0
    assert artifact["review_summary"]["tool_parser_repair_artifacts_missing"] == 1
    assert artifact["review_summary"]["tool_parser_repair_gate_count"] == 2
    assert {
        finding["metric"] for finding in artifact["review_summary"]["tool_parser_repair_gate_findings"]
    } == {"invalid_tool_calls", "tool_parser_repair_valid_rate"}
    assert "message" not in artifact["review_summary"]["tool_parser_repair_gate_findings"][0]


def test_release_qualification_bundle_blocks_unversioned_matrix_gate(tmp_path) -> None:
    matrix_gate = tmp_path / "matrix-gate.json"
    matrix_gate.write_text('{"ok": true}\n', encoding="utf-8")

    output = create_release_qualification_bundle(
        name="invalid-matrix-gate-release",
        output_dir=tmp_path / "release-bundles",
        matrix_gates=[matrix_gate],
    )

    with ZipFile(output) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["ok"] is False
    assert manifest["artifact_status"]["invalid-schema"] == 1
    artifact = manifest["artifacts"][0]
    assert artifact["status"] == "invalid-schema"
    assert artifact["expected_schema"] == "agentblaster.matrix-gate.v1"


def test_cli_release_qualification_accepts_audit_artifacts(tmp_path) -> None:
    telemetry_audit = tmp_path / "telemetry-audit.json"
    contract_check = tmp_path / "provider-contract-check.json"
    matrix_pressure = tmp_path / "matrix-pressure.json"
    matrix_saturation = tmp_path / "matrix-saturation.json"
    engine_advisory = tmp_path / "engine-advisory.json"
    suite_audit = tmp_path / "suite-audit.json"
    metric_coverage = tmp_path / "metric-coverage.json"
    normalized_telemetry = tmp_path / "normalized-telemetry.json"
    benchmark_readiness = tmp_path / "benchmark-readiness.json"
    publication_brief = tmp_path / "publication-brief.json"
    sdlc_validation_manifest = tmp_path / "sdlc-validation-manifest.json"
    benchmark_readiness_list = tmp_path / "benchmark-readiness-inputs.txt"
    telemetry_audit.write_text('{"schema_version": "agentblaster.telemetry-audit.v1"}\n', encoding="utf-8")
    contract_check.write_text('{"schema_version": "agentblaster.provider-contract-check.v1", "ok": true}\n', encoding="utf-8")
    matrix_pressure.write_text('{"schema_version": "agentblaster.matrix-pressure-audit.v1"}\n', encoding="utf-8")
    matrix_saturation.write_text('{"schema_version": "agentblaster.matrix-saturation.v1"}\n', encoding="utf-8")
    engine_advisory.write_text('{"schema_version": "agentblaster.engine-improvement-advisory.v1"}\n', encoding="utf-8")
    suite_audit.write_text('{"schema_version": "agentblaster.suite-audit.v1", "suite": "smoke", "total_cases": 1, "findings": []}\n', encoding="utf-8")
    metric_coverage.write_text('{"schema_version": "agentblaster.metric-coverage.v1", "provider": {"name": "afm"}, "summary": {}, "comparability": {}}\n', encoding="utf-8")
    normalized_telemetry.write_text('{"schema_version": "agentblaster.normalized-telemetry.v1", "contract": "openai", "stats_profile": "generic-openai-chat", "values": {}, "quality": {}, "comparison_readiness": {}, "stats_comparability": {}, "missing": []}\n', encoding="utf-8")
    benchmark_readiness.write_text('{"schema_version": "agentblaster.benchmark-readiness.v1", "provider": "afm", "suite": "smoke", "model": "qwen", "ready": true, "summary": {"provider_auth_writable_backends": 0, "provider_auth_plaintext_fallbacks": 0, "provider_auth_prewrite_policy_guards_recommended": 0}, "provider_auth_posture": []}\n', encoding="utf-8")
    publication_brief.write_text('{"schema_version": "agentblaster.publication-brief.v1", "name": "audit-release", "ready": true, "claim_readiness": {"checks": 1, "blockers": 0, "warnings": 0}, "proof_points": [], "disclosures": [], "matrix_scorecards": [], "security": {"source_artifact_count": 1, "contains_raw_provider_payloads": false, "contains_secrets": false}}\n', encoding="utf-8")
    sdlc_validation_manifest.write_text('{"schema_version": "agentblaster.sdlc-validation-manifest.v1", "name": "audit-release-sdlc", "summary": {"tier_count": 1, "required_gate_count": 1, "blocking_gate_count": 1, "chrome_flow_count": 0, "chrome_validation_step_count": 0}, "gui": {"stable_selectors": [], "api_surfaces": []}, "release_evidence": {"expected_artifacts": []}, "security": {"runs_tests": false, "contacts_providers": false, "contains_raw_provider_payloads": false, "contains_secrets": false}}\n', encoding="utf-8")
    benchmark_readiness_list.write_text(f"# generated campaign readiness inputs\n{benchmark_readiness.name}\n", encoding="utf-8")
    output_dir = tmp_path / "release-bundles"

    result = CliRunner().invoke(
        app,
        [
            "release",
            "qualification-bundle",
            "--name",
            "audit-release",
            "--telemetry-audit",
            str(telemetry_audit),
            "--provider-contract-check",
            str(contract_check),
            "--matrix-pressure-audit",
            str(matrix_pressure),
            "--matrix-saturation-report",
            str(matrix_saturation),
            "--engine-advisory",
            str(engine_advisory),
            "--suite-audit",
            str(suite_audit),
            "--metric-coverage",
            str(metric_coverage),
            "--normalized-telemetry",
            str(normalized_telemetry),
            "--benchmark-readiness-list",
            str(benchmark_readiness_list),
            "--publication-brief",
            str(publication_brief),
            "--sdlc-validation-manifest",
            str(sdlc_validation_manifest),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "audit-release.agentblaster-release-qualification.zip" in result.output
