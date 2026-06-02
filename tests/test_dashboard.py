from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
import pytest

from agentblaster.config import ProviderStore
from agentblaster.dashboard import (
    assert_dashboard_bind_allowed,
    clear_dashboard_provider_auth,
    dashboard_artifact_path,
    configure_dashboard_provider_auth,
    configure_dashboard_provider_profile,
    dashboard_campaign_preview,
    dashboard_catalog_index,
    dashboard_engine_targets,
    dashboard_local_engine_onboarding,
    dashboard_run_payload,
    dashboard_run_events,
    dashboard_run_plan,
    dashboard_model_targets,
    dashboard_providers,
    dashboard_review_artifact_payload,
    dashboard_review_artifacts,
    dashboard_setup_status,
    dashboard_suites,
    dashboard_telemetry_mappings,
    dashboard_workflow_surfaces,
    launch_dashboard_run,
    list_dashboard_runs,
    make_dashboard_handler,
    render_dashboard_html,
)
from agentblaster.errors import ConfigError
from agentblaster.models import ApiContract, BenchmarkResult, ModelMetadata, ProviderConfig, RawTraceMode, RunManifest, SecretRef
from agentblaster.policy import SecurityPolicy


def _write_release_qualification_zip(
    path,
    *,
    ok: bool = True,
    matrix_gate_review: bool = False,
    harness_review: bool = False,
    suite_audit_review: bool = False,
    metric_coverage_review: bool = False,
    matrix_pressure_review: bool = False,
    provider_contract_review: bool = False,
    publication_review: bool = False,
    publication_brief_review: bool = False,
    selftest_review: bool = False,
    sdlc_validation_manifest_review: bool = False,
    benchmark_readiness_review: bool = False,
    implementation_status_review: bool = False,
    campaign_preflight_review: bool = False,
) -> None:
    manifest = {
        "schema": "agentblaster.release-qualification-bundle",
        "schema_version": 1,
        "ok": ok,
        "artifact_status": {"pass": 1} if ok else {"fail": 1},
    }
    artifacts = []
    if matrix_gate_review:
        artifacts.append(
            {
                "category": "gates/matrix",
                "archive_path": "gates/matrix/qwen-gemma-matrix-gate.json",
                "status": "pass",
                "review_summary": {
                    "schema_version": "agentblaster.matrix-gate.v1",
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
                },
            }
        )
    if harness_review:
        artifacts.append(
            {
                "category": "harness/review",
                "archive_path": "harness/review/harness-orchestration-review.json",
                "status": "review",
                "review_summary": {
                    "schema_version": "agentblaster.harness-review.v1",
                    "suite_name": "harness-orchestration",
                    "case_count": 4,
                    "generated": True,
                    "generator_profile": "orchestration",
                    "review_status": "calibration-required",
                    "human_review_required": True,
                    "calibration_required_before_release_gate": True,
                    "surface_counts": {"multi_tool_catalog_cases": 4, "tool_loop_cases": 4},
                    "assertion_counts": {"tool_name": 4},
                },
            }
        )
    if suite_audit_review:
        artifacts.append(
            {
                "category": "governance/suite-audit",
                "archive_path": "governance/suite-audit/agentic-local-suite-audit.json",
                "status": "review",
                "review_summary": {
                    "schema_version": "agentblaster.suite-audit.v1",
                    "suite": "agentic-local",
                    "total_cases": 4,
                    "finding_count": 1,
                    "finding_codes": ["duplicate_case_fingerprint"],
                    "provenance_counts": {"synthetic_representative": 4},
                    "risk_counts": {"medium": 4},
                    "duplicate_fingerprint_count": 1,
                },
            }
        )
    if metric_coverage_review:
        artifacts.append(
            {
                "category": "metrics/coverage",
                "archive_path": "metrics/coverage/afm-metric-coverage.json",
                "status": "review",
                "review_summary": {
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
                },
            }
        )
    if matrix_pressure_review:
        artifacts.append(
            {
                "category": "audits/matrix-pressure",
                "archive_path": "audits/matrix-pressure/qwen-gemma-pressure.json",
                "status": "review",
                "review_summary": {
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
                },
            }
        )
    if provider_contract_review:
        artifacts.append(
            {
                "category": "audits/provider-contract-matrix",
                "archive_path": "audits/provider-contract-matrix/provider-contract-matrix.json",
                "status": "pass",
                "review_summary": {
                    "schema_version": "agentblaster.provider-contract-matrix.v1",
                    "mode": "executed",
                    "ok": True,
                    "matrix": "qwen-gemma-local",
                    "target_count": 2,
                    "checks": {"planned_checks": 10, "passed_checks": 10, "failed_checks": 0, "skipped_checks": 0},
                    "capability_evidence": {
                        "directly_checked": ["streaming", "structured_output", "tool_calling"],
                        "proxy_checked_counts": {"judge_rubric": 2},
                        "not_covered_counts": {"prompt_caching": 1},
                    },
                },
            }
        )
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
        artifacts.append(
            {
                "category": "readiness/benchmark",
                "archive_path": "readiness/benchmark/afm-readiness.json",
                "status": "pass",
                "review_summary": {
                    "schema_version": "agentblaster.benchmark-readiness.v1",
                    "provider": "afm",
                    "suite": "agentic-local",
                    "model": "mlx-community/Qwen3.6-27B",
                    "ready": True,
                    "strict_unknown": True,
                    "policy_ok": True,
                    "suite_compatible": True,
                    "contract_checks_planned": 5,
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
                },
            }
        )
    if implementation_status_review:
        artifacts.append(
            {
                "category": "readiness/implementation",
                "archive_path": "readiness/implementation/implementation-status.json",
                "status": "pass",
                "review_summary": {
                    "schema_version": "agentblaster.implementation-status.v1",
                    "status": "implementation-ready-for-validation",
                    "implemented_areas": 9,
                    "partial_areas": 0,
                    "missing_areas": 0,
                    "built_in_suite_count": 8,
                    "harness_engineering_suite_present": True,
                    "harness_engineering_cases": [
                        "harness-contract-streaming-sentinel",
                        "harness-metamorphic-equivalent-wrapper",
                        "harness-cache-replay-static-prefix",
                        "harness-judge-rubric-json",
                    ],
                    "stats_profile_count": 8,
                    "stats_metric_provider_count": 11,
                    "keyring_optional": True,
                    "secret_backends": ["env", "keyring", "dotenv"],
                    "chrome_codex_gate_present": True,
                    "tests_run_by_this_command": False,
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


def test_dashboard_lists_runs_with_normalized_metrics(tmp_path) -> None:
    _write_run(tmp_path, run_id="run_test", ok=True)

    runs = list_dashboard_runs(tmp_path)

    assert runs == [
        {
            "run_id": "run_test",
            "suite": "smoke",
            "provider": "local",
            "contract": "openai",
            "model": "qwen-test",
            "model_metadata": {
                "revision": "rev-1",
                "architecture": "qwen3-dense",
                "quantization": "mlx-f16",
                "tokenizer": None,
                "chat_template": None,
                "context_length": 32768,
            },
            "provider_metadata": {
                "base_url": "http://127.0.0.1:9999/v1",
                "base_url_host": "127.0.0.1",
                "remote": False,
                "native_adapter": None,
                "adapter_name": "openai-chat-completions",
                "adapter_version": "agentblaster-adapter-v1",
                "capabilities": {"streaming": True},
                "metrics_url_host": None,
                "tls_verify": True,
                "ca_bundle": None,
            },
            "created_at": "2026-05-31T00:00:00Z",
            "raw_trace_mode": "redacted",
            "retention_policy": {
                "classification": "internal",
                "retain_days": None,
                "raw_trace_retain_days": None,
                "notes": [],
            },
            "concurrency": 2,
            "suite_sha256": "abc123def4567890",
            "suite_snapshot_path": "suite.json",
            "suite_provenance": {
                "origin": "builtin",
                "source_suite": None,
                "generator": None,
                "generator_profile": None,
                "generator_seed": None,
                "generator_repeats": None,
                "primary_source": "AgentBlaster",
                "source_url": None,
                "license": "MIT",
                "risk_labels": [],
                "notes": [],
            },
            "metrics_artifacts": ["metrics/prometheus-summary.json"],
            "total_cases": 1,
            "passed": 1,
            "failed": 0,
            "ok": True,
            "duration_ms": 2000.0,
            "requests_per_second": 0.5,
            "total_cost_usd": 0.000111,
            "avg_queue_ms": 3.0,
            "avg_rate_limit_wait_ms": 2.0,
            "avg_latency_ms": 10.0,
            "avg_ttft_ms": 200.0,
            "avg_decode_tokens_per_second": 25.0,
            "artifacts": [],
        }
    ]


def test_dashboard_html_is_redacted_and_chrome_testable(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    ProviderStore().upsert(
        ProviderConfig(
            name="remote-openai",
            contract=ApiContract.OPENAI,
            base_url="https://api.openai.com/v1",
            remote=True,
            tls_verify=False,
        )
    )
    run_dir = _write_run(tmp_path, run_id="run_test", ok=True)
    _write_run(tmp_path, run_id="run_full_trace", ok=True, raw_trace_mode=RawTraceMode.FULL)
    raw_dir = run_dir / "raw"
    raw_dir.mkdir()
    (raw_dir / "case-one.response.json").write_text(
        json.dumps({"headers": {"Authorization": "Bearer should-not-render"}}),
        encoding="utf-8",
    )
    (run_dir / "report.html").write_text("<html>report</html>", encoding="utf-8")
    (run_dir / "report.pdf").write_bytes(b"%PDF-1.4\n")
    (run_dir / "publication.json").write_text("{}", encoding="utf-8")
    (run_dir / "report-card.svg").write_text("<svg></svg>", encoding="utf-8")
    (run_dir / "report-card.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    metrics_dir = run_dir / "metrics"
    metrics_dir.mkdir()
    (metrics_dir / "prometheus-summary.json").write_text("{}", encoding="utf-8")
    release_bundles = tmp_path / "release-bundles"
    release_bundles.mkdir()
    selftest_dir = tmp_path / "test-reports" / "selftest"
    selftest_dir.mkdir(parents=True)
    _write_release_qualification_zip(
        release_bundles / "claim.agentblaster-release-qualification.zip",
        matrix_gate_review=True,
    )

    html = render_dashboard_html(tmp_path, auth_required=True)

    assert "AgentBlaster" in html
    assert 'data-testid="auth-status"' in html
    assert 'data-testid="security-posture-panel"' in html
    assert 'data-testid="posture-auth"' in html
    assert 'data-testid="posture-remote-providers"' in html
    assert "Remote providers" in html
    assert "Remote launch remains blocked unless explicitly allowed." in html
    assert 'data-testid="posture-tls"' in html
    assert "One or more providers disable certificate verification." in html
    assert 'data-testid="posture-raw-traces"' in html
    assert "Full raw trace runs exist" in html
    assert 'data-testid="posture-artifacts"' in html
    assert "allowlisted" in html
    assert 'data-testid="launch-form"' in html
    assert 'data-testid="run-plan-submit"' in html
    assert 'data-testid="provider-setup-panel"' in html
    assert 'data-testid="provider-setup-form"' in html
    assert 'data-testid="provider-setup-base-url-input"' in html
    assert 'data-testid="provider-auth-panel"' in html
    assert 'data-testid="provider-auth-form"' in html
    assert 'data-testid="provider-auth-posture"' in html
    assert 'data-testid="provider-auth-api-key-input"' in html
    assert 'data-testid="catalog-panel"' in html
    assert 'data-testid="catalog-link"' in html
    assert '/catalog/engine-targets' in html
    assert '/catalog/models' in html
    assert '/catalog/workflow-surfaces' in html
    assert 'data-testid="review-artifacts-panel"' in html
    assert 'data-testid="review-artifacts-table"' in html
    assert "qwen-gemma-local: model_quality=2" in html
    assert "tool loops: completed=3" in html
    assert '/api/engine-targets' in html
    assert '/api/models' in html
    assert '/api/workflow-surfaces' in html
    assert '/api/telemetry-mappings' in html
    assert '/api/review-artifacts' in html
    assert '/api/campaign-preview' in html
    assert '/api/setup-status' in html
    assert '/api/run-plan' in html
    assert '/api/runs' in html
    assert 'data-testid="provider-select"' in html
    assert 'data-testid="suite-select"' in html
    assert 'data-testid="capability-preflight-select"' in html
    assert 'data-testid="strict-unknown-capabilities-input"' in html
    assert 'data-testid="runs-table"' in html
    assert 'data-run-id="run_test"' in html
    assert 'data-testid="report-artifact-link"' in html
    assert 'data-testid="report-generate-form"' in html
    assert "/runs/run_test/artifacts/report.html" in html
    assert "/runs/run_test/artifacts/report.pdf" in html
    assert "/runs/run_test/artifacts/publication.json" in html
    assert "/runs/run_test/artifacts/report-card.svg" in html
    assert "/runs/run_test/artifacts/report-card.png" in html
    assert "/runs/run_test/artifacts/metrics%2Fprometheus-summary.json" in html
    assert "builtin" in html
    assert "abc123def456" in html
    assert "qwen3-dense / mlx-f16 / ctx 32768" in html
    assert "openai-chat-completions / agentblaster-adapter-v1" in html
    assert "127.0.0.1 / local / tls=verify" in html
    assert "Bearer should-not-render" not in html
    assert "case-one.response.json" not in html


def test_dashboard_run_payload_returns_manifest_summary_and_results(tmp_path) -> None:
    _write_run(tmp_path, run_id="run_test", ok=False)

    payload = dashboard_run_payload(tmp_path, "run_test")

    assert payload["manifest"]["run_id"] == "run_test"
    assert payload["manifest"]["suite_sha256"] == "abc123def4567890"
    assert payload["manifest"]["suite_provenance"]["origin"] == "builtin"
    assert payload["summary"]["failed"] == 1
    assert payload["results"][0]["case_id"] == "case-one"
    assert payload["results"][0]["failure_class"] == "model_quality"


def test_dashboard_run_events_returns_redacted_lifecycle_timeline(tmp_path) -> None:
    run_dir = _write_run(tmp_path, run_id="run_test", ok=True)
    (run_dir / "events.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "schema": "agentblaster-run-event-v1",
                        "event": "run_started",
                        "run_id": "run_test",
                        "provider": "local",
                    }
                ),
                json.dumps(
                    {
                        "schema": "agentblaster-run-event-v1",
                        "event": "case_completed",
                        "case_id": "case-one",
                        "ok": True,
                        "Authorization": "Bearer should-not-render",
                        "body_preview": "sk-should-not-render-123456789",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = dashboard_run_events(tmp_path, "run_test")
    serialized = json.dumps(payload)

    assert payload["schema_version"] == "agentblaster.dashboard-run-events.v1"
    assert payload["run_id"] == "run_test"
    assert payload["events_path"] == "events.jsonl"
    assert payload["event_count"] == 2
    assert payload["events"][0]["event"] == "run_started"
    assert payload["events"][1]["event"] == "case_completed"
    assert "Bearer should-not-render" not in serialized
    assert "sk-should-not-render" not in serialized


def test_dashboard_provider_profile_setup_is_redacted_and_audited(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    audit_log = tmp_path / "provider-audit.jsonl"

    provider = configure_dashboard_provider_profile(
        {
            "name": "remote-openai",
            "contract": "openai",
            "base_url": "https://api.openai.com/v1",
            "default_model": "gpt-test",
            "remote": True,
            "api_key_env": "OPENAI_API_KEY",
        },
        audit_log=audit_log,
    )
    serialized = json.dumps({"provider": provider, "providers": dashboard_providers()})
    audit = json.loads(audit_log.read_text(encoding="utf-8").splitlines()[0])
    stored = ProviderStore().get("remote-openai")

    assert provider["name"] == "remote-openai"
    assert provider["contract"] == "openai"
    assert provider["remote"] is True
    assert provider["api_key_ref"] == "env:OPENAI_API_KEY"
    assert stored.api_key_ref is not None
    assert stored.api_key_ref.kind == "env"
    assert audit["event"] == "provider_created"
    assert audit["source"] == "dashboard"
    assert audit["api_key_ref"] == "env:OPENAI_API_KEY"
    assert "sk-" not in serialized
    assert "Bearer " not in serialized
    assert "Authorization" not in serialized


def test_dashboard_provider_profile_policy_review_is_static_and_redacted(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    audit_log = tmp_path / "provider-audit.jsonl"

    provider = configure_dashboard_provider_profile(
        {
            "name": "remote-openai",
            "contract": "openai",
            "base_url": "https://api.openai.com/v1",
            "remote": True,
            "api_key_env": "OPENAI_API_KEY",
        },
        audit_log=audit_log,
        policy=SecurityPolicy(allow_remote_providers=False),
    )
    audit = json.loads(audit_log.read_text(encoding="utf-8").splitlines()[0])
    serialized = json.dumps({"provider": provider, "audit": audit})

    assert provider["policy_review"]["ok"] is False
    assert provider["policy_review"]["status"] == "blocked"
    assert provider["policy_review"]["contacts_provider"] is False
    assert provider["policy_review"]["resolves_secrets"] is False
    assert "remote providers are disabled by policy" in provider["policy_review"]["findings"][0]["message"]
    assert audit["policy_ok"] is False
    assert audit["policy_finding_count"] == 1
    assert "sk-" not in serialized
    assert "Bearer " not in serialized
    assert "Authorization" not in serialized


def test_dashboard_provider_auth_setup_is_reference_only(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("AGENTBLASTER_REMOTE_KEY", "sk-should-not-render")
    audit_log = tmp_path / "audit.jsonl"
    ProviderStore().upsert(
        ProviderConfig(
            name="remote-openai",
            contract=ApiContract.OPENAI,
            base_url="https://api.openai.com/v1",
            remote=True,
        )
    )

    auth = configure_dashboard_provider_auth(
        "remote-openai",
        {"method": "env", "env_var": "AGENTBLASTER_REMOTE_KEY"},
        audit_log=audit_log,
    )
    serialized = json.dumps({"auth": auth, "providers": dashboard_providers()})
    audit = json.loads(audit_log.read_text(encoding="utf-8").splitlines()[0])
    stored = ProviderStore().get("remote-openai")

    assert auth["provider"] == "remote-openai"
    assert auth["secret_backend"] == "env"
    assert auth["stored_secret"] is False
    assert auth["resolves"] is True
    assert stored.api_key_ref is not None
    assert stored.api_key_ref.kind == "env"
    assert stored.api_key_ref.name == "AGENTBLASTER_REMOTE_KEY"
    assert audit["event"] == "provider_auth_ref_changed"
    assert audit["source"] == "dashboard"
    assert audit["provider"] == "remote-openai"
    assert audit["api_key_ref"] == "env:AGENTBLASTER_REMOTE_KEY"
    assert "AGENTBLASTER_REMOTE_KEY" in serialized
    assert "sk-should-not-render" not in serialized
    assert "sk-should-not-render" not in json.dumps(audit)


def test_dashboard_provider_auth_policy_review_does_not_leak_secret_ref_name(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    audit_log = tmp_path / "audit.jsonl"
    ProviderStore().upsert(
        ProviderConfig(
            name="remote-openai",
            contract=ApiContract.OPENAI,
            base_url="https://api.openai.com/v1",
            remote=True,
        )
    )

    auth = configure_dashboard_provider_auth(
        "remote-openai",
        {"method": "env", "env_var": "WORKSPACE_OPENAI_SECRET_NAME"},
        audit_log=audit_log,
        policy=SecurityPolicy(allow_remote_providers=True, allowed_secret_ref_kinds={"keyring"}),
    )
    audit = json.loads(audit_log.read_text(encoding="utf-8").splitlines()[0])
    serialized = json.dumps({"auth": auth, "audit": audit})

    assert auth["policy_review"]["ok"] is False
    assert auth["policy_review"]["contacts_provider"] is False
    assert auth["policy_review"]["resolves_secrets"] is False
    assert "secret reference kind is not allowed" in auth["policy_review"]["findings"][0]["message"]
    assert audit["policy_ok"] is False
    assert "WORKSPACE_OPENAI_SECRET_NAME" in auth["api_key_ref"]
    assert "WORKSPACE_OPENAI_SECRET_NAME" not in json.dumps(auth["policy_review"])
    assert "sk-" not in serialized
    assert "Bearer " not in serialized


def test_dashboard_provider_env_auth_rejects_raw_api_key_payload(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    ProviderStore().upsert(
        ProviderConfig(
            name="remote-openai",
            contract=ApiContract.OPENAI,
            base_url="https://api.openai.com/v1",
            remote=True,
        )
    )

    with pytest.raises(ConfigError, match="env auth setup must not include raw API-key material"):
        configure_dashboard_provider_auth(
            "remote-openai",
            {"method": "env", "env_var": "AGENTBLASTER_REMOTE_KEY", "api_key": "sk-should-be-keyring-only"},
        )


def test_dashboard_provider_auth_can_store_explicit_dotenv_fallback(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    audit_log = tmp_path / "audit.jsonl"
    dotenv_path = tmp_path / "dev.env"
    ProviderStore().upsert(
        ProviderConfig(
            name="remote-openai",
            contract=ApiContract.OPENAI,
            base_url="https://api.openai.com/v1",
            remote=True,
        )
    )

    auth = configure_dashboard_provider_auth(
        "remote-openai",
        {
            "method": "dotenv",
            "api_key": "sk-dashboard-dotenv-secret",
            "dotenv_file": str(dotenv_path),
            "dotenv_var": "AGENTBLASTER_REMOTE_KEY",
            "allow_plaintext_secret_file": True,
        },
        audit_log=audit_log,
    )
    clear = clear_dashboard_provider_auth("remote-openai", delete_secret=True, audit_log=audit_log)
    serialized = json.dumps({"auth": auth, "clear": clear, "audit": audit_log.read_text(encoding="utf-8")})

    assert auth["secret_backend"] == "dotenv"
    assert auth["stored_secret"] is True
    assert auth["resolves"] is True
    assert auth["plaintext_secret_warning"] is True
    assert auth["api_key_ref"] == "dotenv:AGENTBLASTER_REMOTE_KEY@<redacted-path>"
    assert auth["api_key_ref_path_redacted"] is True
    assert clear["deleted_secret"] is True
    assert clear["previous_api_key_ref"] == "dotenv:AGENTBLASTER_REMOTE_KEY@<redacted-path>"
    assert clear["previous_api_key_ref_path_redacted"] is True
    assert "sk-dashboard-dotenv-secret" not in serialized
    assert str(dotenv_path) not in serialized
    assert "AGENTBLASTER_REMOTE_KEY=" not in dotenv_path.read_text(encoding="utf-8")


def test_dashboard_provider_auth_does_not_write_dotenv_secret_when_policy_blocks_backend(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    audit_log = tmp_path / "audit.jsonl"
    dotenv_path = tmp_path / "dev.env"
    ProviderStore().upsert(
        ProviderConfig(
            name="remote-openai",
            contract=ApiContract.OPENAI,
            base_url="https://api.openai.com/v1",
            remote=True,
        )
    )

    with pytest.raises(ConfigError, match="provider auth secret storage blocked by policy"):
        configure_dashboard_provider_auth(
            "remote-openai",
            {
                "method": "dotenv",
                "api_key": "sk-dashboard-dotenv-secret",
                "dotenv_file": str(dotenv_path),
                "dotenv_var": "AGENTBLASTER_REMOTE_KEY",
                "allow_plaintext_secret_file": True,
            },
            audit_log=audit_log,
            policy=SecurityPolicy(allow_remote_providers=True, allowed_secret_ref_kinds={"env", "keyring"}),
        )
    stored = ProviderStore().get("remote-openai")
    audit = json.loads(audit_log.read_text(encoding="utf-8").splitlines()[0])

    assert stored.api_key_ref is None
    assert not dotenv_path.exists()
    assert audit["event"] == "provider_auth_ref_rejected"
    assert audit["stored_secret"] is False
    assert audit["policy_ok"] is False
    assert "sk-dashboard-dotenv-secret" not in json.dumps(audit)


def test_dashboard_provider_and_suite_discovery_is_redacted(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    ProviderStore().upsert(
        ProviderConfig(
            name="local-openai",
            contract=ApiContract.OPENAI,
            base_url="http://127.0.0.1:9999/v1",
            model_metadata=ModelMetadata(architecture="qwen3-dense", quantization="mlx-f16"),
        )
    )

    providers = dashboard_providers()
    suites = dashboard_suites()

    assert providers[0]["name"] == "local-openai"
    assert providers[0]["api_key_ref"] is None
    assert "metrics_url" in providers[0]
    assert providers[0]["tls_verify"] is True
    assert providers[0]["ca_bundle"] is None
    assert providers[0]["model_metadata"]["architecture"] == "qwen3-dense"
    assert any(suite["name"] == "smoke" and "provenance" in suite for suite in suites)


def test_dashboard_planning_catalog_payloads_are_static_and_redaction_safe() -> None:
    models = dashboard_model_targets()
    engine_targets = dashboard_engine_targets()
    local_onboarding = dashboard_local_engine_onboarding()
    workflows = dashboard_workflow_surfaces()
    telemetry = dashboard_telemetry_mappings()
    setup_status = dashboard_setup_status()
    index = dashboard_catalog_index()
    serialized = json.dumps({
        "models": models,
        "engine_targets": engine_targets,
        "local_onboarding": local_onboarding,
        "workflows": workflows,
        "telemetry": telemetry,
        "setup_status": setup_status,
        "index": index,
    })

    assert models["schema_version"] == "agentblaster.dashboard-model-targets.v1"
    assert {target["id"] for target in models["model_targets"]} >= {"qwen3.6-27b-dense", "gemma-4-31b-dense"}
    assert engine_targets["schema_version"] == "agentblaster.engine-target-catalog.v1"
    assert local_onboarding["schema_version"] == "agentblaster.local-engine-onboarding.v1"
    assert local_onboarding["safety"]["contacts_providers"] is False
    assert any(
        engine["engine"] == "afm" and engine["engine_target"]["id"] == "afm-mlx"
        for engine in local_onboarding["engines"]
    )
    assert telemetry["stats_comparability"]["schema_version"] == "agentblaster.stats-comparability.v1"
    assert "afm-mlx-openai-compatible" in telemetry["stats_comparability"]["profile_guidance"]
    afm_target = next(target for target in engine_targets["targets"] if target["id"] == "afm-mlx")
    assert afm_target["standardization"]["primary_scoring_contract"] == "openai"
    assert "harness-engineering" in afm_target["standardization"]["workflow_surfaces"]
    assert "large repeated system prompts" in afm_target["standardization"]["prefill_challenges"]
    assert setup_status["auth_setup"]["security"]["provider_config_stores_secret_values"] is False
    assert setup_status["auth_setup"]["security"]["setup_status_reads_secret_values"] is False
    assert setup_status["auth_setup"]["security"]["raw_api_keys_echoed"] is False
    assert setup_status["secret_backend_posture"]["keyring_optional"] is True
    assert isinstance(setup_status["secret_backend_posture"]["keyring_dependency_available"], bool)
    assert {"env", "keyring", "dotenv"} == {
        method["method"] for method in setup_status["auth_setup"]["methods"]
    }
    env_method = next(method for method in setup_status["auth_setup"]["methods"] if method["method"] == "env")
    keyring_method = next(method for method in setup_status["auth_setup"]["methods"] if method["method"] == "keyring")
    dotenv_method = next(method for method in setup_status["auth_setup"]["methods"] if method["method"] == "dotenv")
    assert env_method["accepts_raw_api_key"] is False
    assert keyring_method["stores_secret"] is True
    assert dotenv_method["plaintext_fallback"] is True
    restricted_setup = dashboard_setup_status(policy=SecurityPolicy(allowed_secret_ref_kinds={"keyring"}))
    assert restricted_setup["auth_setup"]["policy_configured"] is True
    assert {
        method["method"]
        for method in restricted_setup["auth_setup"]["methods"]
        if method["blocked_by_policy"]
    } == {"env", "dotenv"}
    assert any(catalog["id"] == "review-artifacts" for catalog in index["catalogs"])
    assert any(target["id"] == "afm-mlx" for target in engine_targets["targets"])
    assert workflows["schema_version"] == "agentblaster.workflow-surface-catalog.v1"
    assert telemetry["schema_version"] == "agentblaster.telemetry-mapping-catalog.v1"
    assert setup_status["schema_version"] == "agentblaster.dashboard-setup-status.v1"
    assert "providers" in setup_status["summary"]
    assert setup_status["policy_controls"]["require_cleanup_audit_log"] is False
    policy_setup_status = dashboard_setup_status(policy=SecurityPolicy(require_cleanup_audit_log=True))
    assert policy_setup_status["policy_controls"]["require_cleanup_audit_log"] is True
    assert any(catalog["id"] == "engine-targets" for catalog in index["catalogs"])
    assert any(catalog["id"] == "local-engine-onboarding" for catalog in index["catalogs"])
    assert any(catalog["id"] == "setup-status" for catalog in index["catalogs"])
    assert any(catalog["id"] == "run-plan" and catalog["href"] == "/api/run-plan" for catalog in index["catalogs"])
    assert any(catalog["id"] == "run-launch" and catalog["href"] == "/api/runs" for catalog in index["catalogs"])
    assert "sk-" not in serialized
    assert "Bearer " not in serialized
    assert "Authorization" not in serialized


def test_dashboard_review_artifacts_indexes_static_evidence_without_raw_contents(tmp_path) -> None:
    reports = tmp_path / "reports"
    publication_bundles = tmp_path / "publication-bundles"
    release_bundles = tmp_path / "release-bundles"
    campaign_preflight_readiness = tmp_path / "campaign-preflight" / "qwen-gemma-local" / "readiness"
    selftest_dir = tmp_path / "test-reports" / "selftest"
    raw_dir = reports / "raw"
    reports.mkdir()
    publication_bundles.mkdir()
    release_bundles.mkdir()
    campaign_preflight_readiness.mkdir(parents=True)
    selftest_dir.mkdir(parents=True)
    raw_dir.mkdir()
    (campaign_preflight_readiness.parent / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.campaign-preflight-bundle.v1",
                "output_dir": str(tmp_path / "campaign-preflight" / "qwen-gemma-local"),
                "matrix_count": 1,
                "artifact_count": 2,
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
                "includes_provider_audit": False,
                "includes_benchmark_readiness": True,
                "benchmark_readiness": {
                    "artifact_path": "readiness/benchmark-readiness-index.json",
                    "report_count": 1,
                },
                "review_summary": {
                    "schema_version": "agentblaster.campaign-preflight-review-summary.v1",
                    "matrix_count": 1,
                    "run_count": 2,
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
                    "contains_local_paths": False,
                    "external_publication_safe": True,
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (reports / "claim-readiness.json").write_text(
        json.dumps({"schema_version": "agentblaster.claim-readiness.v1", "ready": True, "secret": "sk-should-not-render-123456789"}),
        encoding="utf-8",
    )
    (reports / "telemetry-audit.json").write_text(
        json.dumps({"schema_version": "agentblaster.telemetry-audit.v1", "summary": {"comparable_core_ok": False}}),
        encoding="utf-8",
    )
    (reports / "comparison.json").write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.comparison.v1",
                "run_count": 1,
                "rows": [
                    {
                        "run_id": "run_a",
                        "suite": "smoke",
                        "provider": "afm",
                        "model": "qwen",
                        "total_cases": 1,
                        "passed": 1,
                        "failed": 0,
                        "pass_rate": 100.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (reports / "provider-normalized-telemetry.json").write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.normalized-telemetry.v1",
                "contract": "openai",
                "native_adapter": "rapid-mlx",
                "stats_profile": "rapid-mlx-openai-compatible",
                "values": {
                    "input_tokens": 100,
                    "prompt_eval_ms": 500.0,
                    "raw_usage": {"private_provider_usage": "do-not-copy"},
                    "raw_stats": {"private_provider_debug": "do-not-copy"},
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
        ),
        encoding="utf-8",
    )
    (reports / "provider-contract-matrix.json").write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.provider-contract-matrix.v1",
                "ok": False,
                "mode": "executed",
                "matrix": {"name": "qwen-gemma-local", "target_count": 2},
                "summary": {"planned_checks": 10, "passed_checks": 9, "failed_checks": 1, "skipped_checks": 0},
                "capability_evidence": {
                    "directly_checked": ["streaming", "structured_output", "tool_calling"],
                    "proxy_checked_counts": {"judge_rubric": 2},
                    "not_covered_counts": {"prompt_caching": 1},
                },
            }
        ),
        encoding="utf-8",
    )
    (reports / "matrix-saturation.json").write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.matrix-saturation.v1",
                "ok": True,
                "matrix": {"name": "qwen-gemma-local"},
                "summary": {"entry_count": 2, "group_count": 1, "result_artifacts_loaded": 2, "max_concurrency": 4},
                "concurrency_evidence": {
                    "multi_level_group_count": 1,
                    "concurrency_levels": [1, 4],
                    "max_concurrency": 4,
                    "max_avg_queue_ms": 80.0,
                    "queue_wait_finding_count": 1,
                    "guidance": "review-scheduler-queueing-and-provider-pacing-before-publication",
                },
            }
        ),
        encoding="utf-8",
    )
    (reports / "qwen-gemma-matrix-scorecard.json").write_text(
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
                                "model": "qwen3.6-27b-dense",
                                "suite": "prefill",
                                "run_id": "run-afm",
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
                "entries": [
                    {"run_id": "not-copied", "raw_response_path": "raw/not-copied.response.json"}
                ],
                "security": {"contains_raw_provider_payloads": False, "contains_raw_secrets": False},
            }
        ),
        encoding="utf-8",
    )
    (reports / "qwen-gemma-matrix-gate.json").write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.matrix-gate.v1",
                "matrix_name": "qwen-gemma-local",
                "ok": False,
                "pass_rate_percent": 96.0,
                "failure_class_summary": [{"failure_class": "engine_protocol_bug", "count": 1}],
                "tool_loop_stop_summary": [{"stop_reason": "max_tool_calls_reached", "count": 1}],
                "tool_loop_artifacts_missing": 0,
                "invalid_tool_call_count": 1,
                "tool_parser_repair_cases": 2,
                "tool_parser_repairs_valid": 1,
                "tool_parser_repair_valid_rate_percent": 50.0,
                "tool_parser_repair_artifacts_missing": 0,
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
                        "metric": "invalid_tool_calls",
                        "actual": 1,
                        "threshold": 0,
                        "message": "invalid tool-call gate failed",
                    },
                    {
                        "metric": "tool_parser_repair_valid_rate",
                        "actual": 50.0,
                        "threshold": 100.0,
                        "message": "parser repair gate failed",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (reports / "stale-matrix-gate.json").write_text(
        json.dumps(
            {
                "matrix_name": "stale-matrix",
                "ok": True,
                "pass_rate_percent": 100.0,
                "failure_class_summary": [],
                "findings": [],
            }
        ),
        encoding="utf-8",
    )
    (reports / "harness-review.json").write_text(
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
            }
        ),
        encoding="utf-8",
    )
    (reports / "engine-advisory.json").write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.engine-improvement-advisory.v1",
                "engine": "afm",
                "summary": {"priority_count": 2, "highest_priority": 1, "no_dispatch": True},
                "priorities": [
                    {
                        "priority": 1,
                        "area": "contract-conformance",
                        "reason": "not copied into review summaries",
                        "aligned_artifacts_or_suites": ["providers contract-check"],
                    },
                    {
                        "priority": 2,
                        "area": "harness-calibration",
                        "reason": "not copied into review summaries",
                        "aligned_artifacts_or_suites": ["harness review"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (reports / "evidence-index.json").write_text(
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
            }
        ),
        encoding="utf-8",
    )
    (reports / "retention-cleanup-plan.json").write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.retention-cleanup.v1",
                "report_type": "retention_cleanup_plan",
                "generated_at": "2026-06-01T00:00:00Z",
                "runs_dir": "/private/agentblaster/runs",
                "execute": False,
                "action_count": 2,
                "actions": [
                    {"action": "raw", "run_id": "run-a", "run_dir": "/private/agentblaster/runs/run-a"},
                    {"action": "run", "run_id": "run-b", "run_dir": "/private/agentblaster/runs/run-b"},
                ],
                "security": {
                    "contains_raw_secrets": False,
                    "contains_raw_provider_payloads": False,
                    "reads_keyring_values": False,
                    "contacts_providers": False,
                    "contains_local_paths": True,
                    "direct_publication_safe": False,
                    "audit_log_required": True,
                },
            }
        ),
        encoding="utf-8",
    )
    (reports / "suite-audit.json").write_text(
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
                    {"severity": "warning", "case_id": "case-a,case-b", "code": "duplicate_case_fingerprint", "message": "not rendered"}
                ],
                "security_notes": [],
            }
        ),
        encoding="utf-8",
    )
    (reports / "metric-coverage.json").write_text(
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
            }
        ),
        encoding="utf-8",
    )
    (reports / "matrix-pressure.json").write_text(
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
                        "largest_cases": [{"case_id": "not-rendered"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (reports / "benchmark-readiness.json").write_text(
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
        ),
        encoding="utf-8",
    )
    (campaign_preflight_readiness / "benchmark-readiness-index.json").write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.campaign-preflight-benchmark-readiness-index.v1",
                "report_count": 1,
                "reports": [
                    {
                        "source_path": "reports/afm-trace-readiness.json",
                        "source_sha256": "abc123",
                        "schema_version": "agentblaster.benchmark-readiness.v1",
                        "provider": "afm",
                        "suite": "trace-replay",
                        "model": "mlx-community/Qwen3.6-27B",
                        "ready": True,
                        "strict_unknown": True,
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
                ],
                "security": {
                    "contacts_providers": False,
                    "resolves_secrets": False,
                    "reads_keyring_values": False,
                    "contains_raw_secrets": False,
                    "contains_raw_provider_payloads": False,
                    "contains_raw_traces": False,
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    with ZipFile(publication_bundles / "qwen-gemma.agentblaster-matrix-publication.zip", "w") as archive:
        archive.writestr(
            "matrix-publication-bundle-manifest.json",
            json.dumps(
                {
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
                    "artifacts": [
                        "qwen-gemma.json",
                        "qwen-gemma-matrix-scorecard.json",
                        "qwen-gemma-matrix-scorecard.svg",
                    ],
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
                },
                sort_keys=True,
            )
            + "\n",
        )
    with ZipFile(publication_bundles / "run.agentblaster-publication.zip", "w") as archive:
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
                }
            )
            + "\n",
        )
    _write_release_qualification_zip(
        release_bundles / "claim.agentblaster-release-qualification.zip",
        matrix_gate_review=True,
        harness_review=True,
        suite_audit_review=True,
        metric_coverage_review=True,
        matrix_pressure_review=True,
        provider_contract_review=True,
        publication_review=True,
        publication_brief_review=True,
        selftest_review=True,
        sdlc_validation_manifest_review=True,
        benchmark_readiness_review=True,
        implementation_status_review=True,
        campaign_preflight_review=True,
    )
    (raw_dir / "case.response.json").write_text('{"raw": true}', encoding="utf-8")
    (reports / "results.jsonl").write_text("{}\n", encoding="utf-8")
    (selftest_dir / "selftest-report.json").write_text(
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
                "command": "not copied into dashboard review summaries",
                "env": {"AGENTBLASTER_INTERNAL_VALUE": "not copied into dashboard review summaries"},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = dashboard_review_artifacts(tmp_path)
    serialized = json.dumps(payload)
    artifacts = {artifact["path"]: artifact for artifact in payload["artifacts"]}

    assert payload["schema_version"] == "agentblaster.dashboard-review-artifacts.v1"
    assert payload["project_root"] == "<redacted>"
    assert payload["project_root_redacted"] is True
    assert str(tmp_path) not in json.dumps({key: value for key, value in payload.items() if key != "artifacts"})
    assert "reports/claim-readiness.json" in artifacts
    assert "test-reports/selftest/selftest-report.json" in artifacts
    assert artifacts["test-reports/selftest/selftest-report.json"]["schema"] == "agentblaster.selftest-report.v1"
    assert artifacts["test-reports/selftest/selftest-report.json"]["selftest_report_summaries"][0]["tier"] == "normal"
    assert "AGENTBLASTER_INTERNAL_VALUE" not in json.dumps(
        artifacts["test-reports/selftest/selftest-report.json"]["selftest_report_summaries"]
    )
    assert artifacts["reports/benchmark-readiness.json"]["schema"] == "agentblaster.benchmark-readiness.v1"
    assert artifacts["reports/benchmark-readiness.json"]["benchmark_readiness_summaries"][0]["provider"] == "afm"
    assert artifacts["reports/benchmark-readiness.json"]["benchmark_readiness_summaries"][0][
        "provider_auth_plaintext_fallbacks"
    ] == 1
    assert artifacts["campaign-preflight/qwen-gemma-local/readiness/benchmark-readiness-index.json"][
        "schema"
    ] == "agentblaster.campaign-preflight-benchmark-readiness-index.v1"
    assert artifacts["campaign-preflight/qwen-gemma-local/readiness/benchmark-readiness-index.json"]["status"] == "pass"
    assert artifacts["campaign-preflight/qwen-gemma-local/readiness/benchmark-readiness-index.json"][
        "benchmark_readiness_summaries"
    ][0]["suite"] == "trace-replay"
    assert artifacts["campaign-preflight/qwen-gemma-local/readiness/benchmark-readiness-index.json"][
        "benchmark_readiness_summaries"
    ][0]["provider_auth_plaintext_fallbacks"] == 1
    assert artifacts["campaign-preflight/qwen-gemma-local/manifest.json"]["schema"] == "agentblaster.campaign-preflight-bundle.v1"
    assert artifacts["campaign-preflight/qwen-gemma-local/manifest.json"]["status"] == "review"
    assert artifacts["campaign-preflight/qwen-gemma-local/manifest.json"]["campaign_preflight_summaries"][0][
        "contains_local_paths"
    ] is False
    assert artifacts["campaign-preflight/qwen-gemma-local/manifest.json"]["campaign_preflight_summaries"][0][
        "external_publication_safe"
    ] is True
    assert str(tmp_path) not in json.dumps(
        artifacts["campaign-preflight/qwen-gemma-local/manifest.json"]["campaign_preflight_summaries"]
    )
    assert artifacts["reports/claim-readiness.json"]["status"] == "pass"
    assert artifacts["reports/claim-readiness.json"]["href"] == "/api/review-artifacts/reports%2Fclaim-readiness.json"
    assert artifacts["reports/telemetry-audit.json"]["status"] == "review"
    assert artifacts["reports/comparison.json"]["status"] == "informational"
    assert artifacts["reports/comparison.json"]["schema"] == "agentblaster.comparison.v1"
    assert artifacts["reports/provider-normalized-telemetry.json"]["status"] == "review"
    assert artifacts["reports/provider-normalized-telemetry.json"]["normalized_telemetry_summaries"][0][
        "stats_profile"
    ] == "rapid-mlx-openai-compatible"
    assert artifacts["reports/provider-normalized-telemetry.json"]["normalized_telemetry_summaries"][0][
        "raw_provenance_field_count"
    ] == 2
    assert "private_provider_debug" not in json.dumps(
        artifacts["reports/provider-normalized-telemetry.json"]["normalized_telemetry_summaries"]
    )
    assert artifacts["reports/provider-contract-matrix.json"]["status"] == "fail"
    assert artifacts["reports/provider-contract-matrix.json"]["schema"] == "agentblaster.provider-contract-matrix.v1"
    assert artifacts["reports/provider-contract-matrix.json"]["provider_contract_summaries"][0][
        "capability_evidence"
    ]["directly_checked"] == ["streaming", "structured_output", "tool_calling"]
    assert artifacts["reports/provider-contract-matrix.json"]["provider_contract_summaries"][0][
        "capability_evidence"
    ]["proxy_checked_counts"] == {"judge_rubric": 2}
    assert artifacts["reports/provider-contract-matrix.json"]["provider_contract_summaries"][0][
        "capability_evidence"
    ]["not_covered_counts"] == {"prompt_caching": 1}
    assert "judge_rubric" in json.dumps(artifacts["reports/provider-contract-matrix.json"])
    assert artifacts["reports/matrix-saturation.json"]["status"] == "pass"
    assert artifacts["reports/matrix-saturation.json"]["schema"] == "agentblaster.matrix-saturation.v1"
    assert artifacts["reports/matrix-saturation.json"]["matrix_saturation_summaries"][0]["max_avg_queue_ms"] == 80
    assert artifacts["reports/matrix-saturation.json"]["matrix_saturation_summaries"][0]["guidance"] == "review-scheduler-queueing-and-provider-pacing-before-publication"
    assert artifacts["reports/qwen-gemma-matrix-scorecard.json"]["status"] == "pass"
    assert artifacts["reports/qwen-gemma-matrix-scorecard.json"]["schema"] == "agentblaster-matrix-scorecard-v1"
    assert artifacts["reports/qwen-gemma-matrix-scorecard.json"]["matrix_scorecard_summaries"][0]["matrix"] == "qwen-gemma-local"
    assert artifacts["reports/qwen-gemma-matrix-scorecard.json"]["matrix_scorecard_summaries"][0][
        "engine_targets"
    ] == [{"id": "afm-mlx", "display_name": "AFM MLX", "primary_scoring_contract": "openai"}]
    assert artifacts["reports/qwen-gemma-matrix-scorecard.json"]["matrix_scorecard_summaries"][0][
        "architecture_summary"
    ][0]["model_architecture"] == "qwen3.6-dense"
    assert artifacts["reports/qwen-gemma-matrix-scorecard.json"]["matrix_scorecard_summaries"][0][
        "quantization_summary"
    ][0]["quantization"] == "mlx-f16"
    assert artifacts["reports/qwen-gemma-matrix-scorecard.json"]["matrix_scorecard_summaries"][0][
        "telemetry_quality_summary"
    ]["quality_counts"] == {"inferred": 1, "measured": 9, "native": 3}
    assert artifacts["reports/qwen-gemma-matrix-scorecard.json"]["matrix_scorecard_summaries"][0][
        "stats_comparability_summary"
    ]["profile_counts"] == {"afm-mlx-openai-compatible": 1}
    assert artifacts["reports/qwen-gemma-matrix-scorecard.json"]["matrix_scorecard_summaries"][0][
        "concurrency_evidence"
    ]["concurrency_levels"] == [1, 4]
    assert artifacts["reports/qwen-gemma-matrix-scorecard.json"]["matrix_scorecard_summaries"][0][
        "concurrency_evidence"
    ]["highest_queue_wait_entries"][0]["engine"] == "afm"
    assert "raw_response_path" not in json.dumps(
        artifacts["reports/qwen-gemma-matrix-scorecard.json"]["matrix_scorecard_summaries"]
    )
    assert artifacts["reports/qwen-gemma-matrix-gate.json"]["status"] == "fail"
    assert artifacts["reports/qwen-gemma-matrix-gate.json"]["matrix_gate_review_summaries"] == [
        {
            "archive_path": "qwen-gemma-local",
            "schema_version": "agentblaster.matrix-gate.v1",
            "status": "fail",
            "matrix_name": "qwen-gemma-local",
            "pass_rate_percent": 96.0,
            "failure_class_summary": [{"failure_class": "engine_protocol_bug", "count": 1}],
            "tool_loop_stop_summary": [{"stop_reason": "max_tool_calls_reached", "count": 1}],
            "tool_loop_artifacts_missing": 0,
            "invalid_tool_call_count": 1,
            "tool_parser_repair_cases": 2,
            "tool_parser_repairs_valid": 1,
            "tool_parser_repair_valid_rate_percent": 50.0,
            "tool_parser_repair_artifacts_missing": 0,
            "failure_class_gate_count": 1,
            "failure_class_gate_findings": [
                {
                    "metric": "failure_class.engine_protocol_bug",
                    "failure_class": "engine_protocol_bug",
                    "actual": 1,
                    "threshold": 0,
                }
            ],
            "tool_loop_stop_gate_count": 1,
            "tool_loop_stop_gate_findings": [
                {
                    "metric": "tool_loop_stop_reason.max_tool_calls_reached",
                    "stop_reason": "max_tool_calls_reached",
                    "actual": 1,
                    "threshold": 0,
                }
            ],
            "tool_parser_repair_gate_count": 2,
            "tool_parser_repair_gate_findings": [
                {
                    "metric": "invalid_tool_calls",
                    "actual": 1,
                    "threshold": 0,
                },
                {
                    "metric": "tool_parser_repair_valid_rate",
                    "actual": 50.0,
                    "threshold": 100.0,
                },
            ],
        }
    ]
    assert "engine protocol bug gate failed" not in json.dumps(
        artifacts["reports/qwen-gemma-matrix-gate.json"]["matrix_gate_review_summaries"]
    )
    assert "tool-loop gate failed" not in json.dumps(
        artifacts["reports/qwen-gemma-matrix-gate.json"]["matrix_gate_review_summaries"]
    )
    assert "parser repair gate failed" not in json.dumps(
        artifacts["reports/qwen-gemma-matrix-gate.json"]["matrix_gate_review_summaries"]
    )
    assert artifacts["reports/stale-matrix-gate.json"]["status"] == "invalid-schema"
    assert artifacts["reports/stale-matrix-gate.json"]["expected_schema"] == "agentblaster.matrix-gate.v1"
    assert artifacts["reports/harness-review.json"]["status"] == "review"
    assert artifacts["reports/harness-review.json"]["schema"] == "agentblaster.harness-review.v1"
    assert artifacts["reports/harness-review.json"]["harness_review_summaries"][0]["generator_profile"] == "orchestration"
    assert artifacts["reports/harness-review.json"]["harness_review_summaries"][0]["surface_counts"] == {
        "multi_tool_catalog_cases": 4,
        "tool_loop_cases": 4,
    }
    assert artifacts["reports/engine-advisory.json"]["status"] == "review"
    assert artifacts["reports/engine-advisory.json"]["engine_advisory_summaries"][0]["engine"] == "afm"
    assert artifacts["reports/engine-advisory.json"]["engine_advisory_summaries"][0]["top_priorities"][0]["area"] == "contract-conformance"
    assert "reason" not in artifacts["reports/engine-advisory.json"]["engine_advisory_summaries"][0]["top_priorities"][0]
    assert artifacts["reports/evidence-index.json"]["status"] == "review"
    assert artifacts["reports/evidence-index.json"]["evidence_index_summaries"][0]["status_counts"] == {
        "fail": 1,
        "review": 1,
    }
    assert artifacts["reports/evidence-index.json"]["evidence_index_summaries"][0]["readiness"]["state"] == "blocked"
    assert artifacts["reports/evidence-index.json"]["evidence_index_summaries"][0]["cleanup_evidence"][
        "audit_log_required_count"
    ] == 1
    assert artifacts["reports/retention-cleanup-plan.json"]["status"] == "review"
    assert artifacts["reports/retention-cleanup-plan.json"]["cleanup_report_summaries"][0]["action_types"] == [
        "raw",
        "run",
    ]
    assert artifacts["reports/retention-cleanup-plan.json"]["cleanup_report_summaries"][0][
        "audit_log_required"
    ] is True
    assert "/private/agentblaster/runs" not in json.dumps(
        artifacts["reports/retention-cleanup-plan.json"]["cleanup_report_summaries"]
    )
    assert artifacts["reports/suite-audit.json"]["status"] == "review"
    assert artifacts["reports/suite-audit.json"]["suite_audit_summaries"][0]["suite"] == "agentic-local"
    assert artifacts["reports/suite-audit.json"]["suite_audit_summaries"][0]["duplicate_fingerprint_count"] == 1
    assert artifacts["reports/metric-coverage.json"]["status"] == "review"
    assert artifacts["reports/metric-coverage.json"]["metric_coverage_summaries"][0]["provider"] == "afm"
    assert artifacts["reports/metric-coverage.json"]["metric_coverage_summaries"][0]["review_required_groups"] == [
        "timing_and_throughput",
        "token_and_cache_accounting",
    ]
    assert artifacts["reports/matrix-pressure.json"]["status"] == "review"
    assert artifacts["reports/matrix-pressure.json"]["schema"] == "agentblaster.matrix-pressure-audit.v1"
    assert artifacts["reports/matrix-pressure.json"]["matrix_pressure_summaries"][0]["shared_static_reuse_tokens"] == 6400
    assert artifacts["reports/matrix-pressure.json"]["matrix_pressure_summaries"][0][
        "concurrency_weighted_pressure_score"
    ] == 176
    assert "largest_cases" not in json.dumps(artifacts["reports/matrix-pressure.json"]["matrix_pressure_summaries"])
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["schema"] == "agentblaster.release-qualification-bundle"
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["status"] == "pass"
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["provider_contract_summaries"][0][
        "capability_evidence"
    ]["directly_checked"] == ["streaming", "structured_output", "tool_calling"]
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["provider_contract_summaries"][0][
        "capability_evidence"
    ]["not_covered_counts"] == {"prompt_caching": 1}
    assert "provider_contract_summaries" in json.dumps(
        artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]
    )
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["status_source"] == "manifest.ok"
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["matrix_gate_review_summaries"] == [
        {
            "archive_path": "gates/matrix/qwen-gemma-matrix-gate.json",
            "schema_version": "agentblaster.matrix-gate.v1",
            "status": "pass",
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
        }
    ]
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["harness_review_summaries"][0]["suite_name"] == "harness-orchestration"
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["harness_review_summaries"][0]["calibration_required_before_release_gate"] is True
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["suite_audit_summaries"][0]["suite"] == "agentic-local"
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["suite_audit_summaries"][0]["finding_count"] == 1
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["metric_coverage_summaries"][0]["provider"] == "afm"
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["metric_coverage_summaries"][0]["coverage_score"] == 0.55
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["matrix_pressure_summaries"][0][
        "matrix"
    ] == "qwen-gemma-local"
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["matrix_pressure_summaries"][0][
        "shared_static_reuse_tokens"
    ] == 6400
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["publication_bundle_summaries"][0]["run_id"] == "run-release"
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["publication_bundle_summaries"][0]["publication_readiness"]["status"] == "review-required"
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["publication_bundle_summaries"][0]["security"]["contains_results_jsonl"] is False
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["publication_brief_summaries"][0]["name"] == "afm-release"
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["publication_brief_summaries"][0]["claim_warnings"] == 1
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["publication_brief_summaries"][0]["engine_targets"] == [
        {"id": "afm-mlx", "display_name": "AFM MLX", "primary_scoring_contract": "openai"}
    ]
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["publication_brief_summaries"][0][
        "architecture_summary"
    ][0]["model_architecture"] == "qwen3.6-dense"
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["publication_brief_summaries"][0][
        "quantization_summary"
    ][0]["quantization"] == "mlx-f16"
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["selftest_report_summaries"][0]["tier"] == "normal"
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["selftest_report_summaries"][0]["junit_xml_present"] is True
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["sdlc_validation_manifest_summaries"][0]["chrome_validation_step_count"] == 9
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["sdlc_validation_manifest_summaries"][0]["expected_artifact_count"] == 4
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["benchmark_readiness_summaries"][0][
        "provider_auth_posture"
    ][0]["api_key_ref_plaintext_fallback"] is True
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["implementation_status_summaries"][0][
        "missing_areas"
    ] == 0
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["implementation_status_summaries"][0][
        "harness_engineering_case_count"
    ] == 4
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["implementation_status_summaries"][0][
        "stats_profile_count"
    ] == 8
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["campaign_preflight_summaries"][0][
        "archive_path"
    ] == "readiness/campaign-preflight/campaign-preflight-manifest.json"
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["campaign_preflight_summaries"][0][
        "contains_local_paths"
    ] is False
    assert artifacts["release-bundles/claim.agentblaster-release-qualification.zip"]["campaign_preflight_summaries"][0][
        "external_publication_safe"
    ] is True
    assert artifacts["publication-bundles/run.agentblaster-publication.zip"]["schema"] == "agentblaster.publication-bundle.v1"
    assert artifacts["publication-bundles/run.agentblaster-publication.zip"]["status"] == "review"
    assert artifacts["publication-bundles/run.agentblaster-publication.zip"]["status_source"] == "publication-manifest.publication_readiness.status"
    assert artifacts["publication-bundles/run.agentblaster-publication.zip"]["publication_bundle_summaries"][0]["run_id"] == "run-review"
    assert artifacts["publication-bundles/run.agentblaster-publication.zip"]["publication_bundle_summaries"][0]["publication_readiness"]["status"] == "review-required"
    assert artifacts["publication-bundles/run.agentblaster-publication.zip"]["publication_bundle_summaries"][0]["security"]["contains_results_jsonl"] is False
    assert artifacts["publication-bundles/qwen-gemma.agentblaster-matrix-publication.zip"]["schema"] == "agentblaster.matrix-publication-bundle.v1"
    assert artifacts["publication-bundles/qwen-gemma.agentblaster-matrix-publication.zip"]["status"] == "pass"
    assert artifacts["publication-bundles/qwen-gemma.agentblaster-matrix-publication.zip"]["matrix_publication_bundle_summaries"][0]["matrix"]["artifact_stem"] == "qwen-gemma"
    assert artifacts["publication-bundles/qwen-gemma.agentblaster-matrix-publication.zip"]["matrix_publication_bundle_summaries"][0]["engine_targets"] == [
        {"id": "afm-mlx", "display_name": "AFM MLX", "primary_scoring_contract": "openai"}
    ]
    assert artifacts["publication-bundles/qwen-gemma.agentblaster-matrix-publication.zip"]["matrix_publication_bundle_summaries"][0]["architecture_summary"][0]["model_architecture"] == "qwen3.6-dense"
    assert artifacts["publication-bundles/qwen-gemma.agentblaster-matrix-publication.zip"]["matrix_publication_bundle_summaries"][0]["quantization_summary"][0]["quantization"] == "mlx-f16"
    assert "raw/case.response.json" not in serialized
    assert "results.jsonl" not in serialized
    assert "sk-should-not-render" not in serialized

    detail = dashboard_review_artifact_payload(tmp_path, "reports/claim-readiness.json")
    detail_serialized = json.dumps(detail)

    assert detail["schema_version"] == "agentblaster.dashboard-review-artifact-detail.v1"
    assert detail["artifact"]["path"] == "reports/claim-readiness.json"
    assert detail["payload"]["schema_version"] == "agentblaster.claim-readiness.v1"
    assert "sk-should-not-render" not in detail_serialized
    telemetry_detail = dashboard_review_artifact_payload(tmp_path, "reports/provider-normalized-telemetry.json")
    telemetry_detail_serialized = json.dumps(telemetry_detail)
    assert telemetry_detail["payload"]["redacted_for_dashboard_detail"] is True
    assert telemetry_detail["payload"]["normalized_telemetry_summaries"][0]["stats_requires_labeling"] is True
    assert "private_provider_debug" not in telemetry_detail_serialized
    assert "private_provider_usage" not in telemetry_detail_serialized
    assert "sources" not in telemetry_detail_serialized
    preflight_detail = dashboard_review_artifact_payload(
        tmp_path,
        "campaign-preflight/qwen-gemma-local/manifest.json",
    )
    preflight_detail_serialized = json.dumps(preflight_detail)
    assert preflight_detail["payload"]["redacted_for_dashboard_detail"] is True
    assert preflight_detail["payload"]["campaign_preflight_summaries"][0]["contains_local_paths"] is False
    assert str(tmp_path) not in preflight_detail_serialized
    assert "dry_run_command" not in preflight_detail_serialized


def test_dashboard_review_artifacts_summarizes_publication_brief_and_sdlc_manifest(tmp_path) -> None:
    reports = tmp_path / "reports"
    test_reports = tmp_path / "test-reports"
    reports.mkdir()
    test_reports.mkdir()
    (reports / "publication-brief.json").write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.publication-brief.v1",
                "name": "qwen-gemma-release-brief",
                "ready": False,
                "claim_readiness": {"checks": 6, "blockers": 1, "warnings": 2},
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
    (test_reports / "sdlc-validation-manifest.json").write_text(
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

    payload = dashboard_review_artifacts(tmp_path)
    artifacts = {artifact["path"]: artifact for artifact in payload["artifacts"]}

    publication = artifacts["reports/publication-brief.json"]
    assert publication["status"] == "review"
    assert publication["status_source"] == "publication-brief.ready"
    assert publication["publication_brief_summaries"][0]["proof_point_count"] == 2
    assert publication["publication_brief_summaries"][0]["claim_blockers"] == 1
    assert publication["publication_brief_summaries"][0]["engine_targets"] == [
        {"id": "afm-mlx", "display_name": "AFM MLX", "primary_scoring_contract": "openai"}
    ]
    assert publication["publication_brief_summaries"][0]["architecture_summary"][0]["model_architecture"] == "qwen3.6-dense"
    assert publication["publication_brief_summaries"][0]["quantization_summary"][0]["quantization"] == "mlx-f16"
    assert publication["publication_brief_summaries"][0]["contains_secrets"] is False
    sdlc = artifacts["test-reports/sdlc-validation-manifest.json"]
    assert sdlc["status"] == "review"
    assert sdlc["status_source"] == "sdlc-validation-manifest.static"
    assert sdlc["sdlc_validation_manifest_summaries"][0]["chrome_flow_count"] == 2
    assert sdlc["sdlc_validation_manifest_summaries"][0]["expected_artifact_count"] == 2
    assert "sk-" not in json.dumps(payload)
    publication_detail = dashboard_review_artifact_payload(tmp_path, "reports/publication-brief.json")
    publication_detail_serialized = json.dumps(publication_detail)
    assert publication_detail["payload"]["redacted_for_dashboard_detail"] is True
    assert publication_detail["payload"]["publication_brief_summaries"][0]["proof_point_count"] == 2
    assert publication_detail["payload"]["security"]["includes_proof_point_text"] is False
    assert "tool loops complete" not in publication_detail_serialized
    sdlc_detail = dashboard_review_artifact_payload(tmp_path, "test-reports/sdlc-validation-manifest.json")
    sdlc_detail_serialized = json.dumps(sdlc_detail)
    assert sdlc_detail["payload"]["redacted_for_dashboard_detail"] is True
    assert sdlc_detail["payload"]["sdlc_validation_manifest_summaries"][0]["chrome_validation_step_count"] == 9
    assert sdlc_detail["payload"]["security"]["includes_raw_test_logs"] is False
    assert "review-artifacts-panel" not in sdlc_detail_serialized


def test_dashboard_review_artifacts_summarizes_provider_audit_without_secret_refs(tmp_path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "provider-audit.json").write_text(
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
                            {
                                "severity": "warning",
                                "code": "remote_without_rate_limits",
                                "message": "rate limits missing for keyring:remote-openai:api_key",
                            }
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

    payload = dashboard_review_artifacts(tmp_path)
    artifact = {item["path"]: item for item in payload["artifacts"]}["reports/provider-audit.json"]
    detail = dashboard_review_artifact_payload(tmp_path, "reports/provider-audit.json")
    serialized_detail = json.dumps(detail)

    assert artifact["status"] == "review"
    assert artifact["provider_audit_summaries"][0]["warning_count"] == 1
    assert artifact["provider_audit_summaries"][0]["keyring_required_provider_count"] == 1
    assert artifact["provider_audit_summaries"][0]["secret_backend_posture"]["keyring_optional"] is True
    assert artifact["provider_audit_summaries"][0]["provider_auth_posture"][0]["api_key_ref_kind"] == "keyring"
    assert detail["payload"]["redacted_for_dashboard_detail"] is True
    assert detail["payload"]["provider_audit_summaries"][0]["finding_codes"] == ["remote_without_rate_limits"]
    assert "remote-openai:api_key" not in serialized_detail


def test_dashboard_review_artifact_payload_blocks_raw_and_zip_artifacts(tmp_path) -> None:
    reports = tmp_path / "reports"
    release_bundles = tmp_path / "release-bundles"
    raw_dir = reports / "raw"
    raw_dir.mkdir(parents=True)
    release_bundles.mkdir()
    (raw_dir / "case.response.json").write_text("{}", encoding="utf-8")
    (reports / "results.jsonl").write_text("{}\n", encoding="utf-8")
    _write_release_qualification_zip(release_bundles / "claim.agentblaster-release-qualification.zip")

    with pytest.raises(ConfigError):
        dashboard_review_artifact_payload(tmp_path, "reports/raw/case.response.json")
    with pytest.raises(ConfigError):
        dashboard_review_artifact_payload(tmp_path, "reports/results.jsonl")
    with pytest.raises(ConfigError):
        dashboard_review_artifact_payload(tmp_path, "release-bundles/claim.agentblaster-release-qualification.zip")


def test_dashboard_campaign_preview_is_static_and_redaction_safe() -> None:
    preview = dashboard_campaign_preview(
        {
            "providers": ["afm,lm-studio"],
            "targets": ["qwen3.6-27b-dense"],
            "suites": ["smoke,lcp-context"],
            "concurrency": ["2"],
            "output_dir": ["campaigns/local"],
        }
    )
    serialized = json.dumps(preview)

    assert preview["schema_version"] == "agentblaster.campaign-preview.v1"
    assert preview["providers"] == ["afm", "lm-studio"]
    assert preview["suites"] == ["smoke", "lcp-context"]
    assert preview["matrix_run_count"] == 4
    assert preview["safety"]["preview_only"] is True
    assert preview["safety"]["writes_files"] is False
    assert preview["safety"]["contacts_providers"] is False
    assert preview["write_command"][:3] == ["agentblaster", "models", "campaign-plan"]
    assert "sk-" not in serialized
    assert "Bearer " not in serialized
    assert "Authorization" not in serialized


def test_dashboard_run_plan_preview_is_no_dispatch_and_redaction_safe(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("AGENTBLASTER_REMOTE_KEY", "sk-runplan-should-not-render")
    audit_log = tmp_path / "run-plan-audit.jsonl"
    ProviderStore().upsert(
        ProviderConfig(
            name="local-openai",
            contract=ApiContract.OPENAI,
            base_url="http://127.0.0.1:9999/v1",
            default_model="qwen-default",
            api_key_ref=SecretRef(kind="env", name="AGENTBLASTER_REMOTE_KEY"),
        )
    )

    preview = dashboard_run_plan(
        {
            "provider": "local-openai",
            "suite": "smoke",
            "concurrency": 2,
            "no_raw_traces": True,
            "capability_preflight": True,
        },
        audit_log=audit_log,
    )
    audit = json.loads(audit_log.read_text(encoding="utf-8").splitlines()[0])
    serialized = json.dumps({"preview": preview, "audit": audit})

    assert preview["schema_version"] == "agentblaster.dashboard-run-plan.v1"
    assert preview["safety"]["preview_only"] is True
    assert preview["safety"]["dispatches_requests"] is False
    assert preview["safety"]["contacts_provider"] is False
    assert preview["safety"]["resolves_secrets"] is False
    assert preview["safety"]["writes_run_artifacts"] is False
    assert preview["safety"]["capability_preflight"] is True
    assert preview["safety"]["strict_unknown_capabilities"] is False
    assert preview["safety"]["capability_compatible"] is True
    assert preview["safety"]["capability_missing"] == []
    assert preview["safety"]["capability_unknown"] == []
    assert preview["plan"]["dry_run"] is True
    assert preview["plan"]["provider"] == "local-openai"
    assert preview["plan"]["model"] == "qwen-default"
    assert preview["plan"]["raw_trace_mode"] == "off"
    assert preview["plan"]["concurrency"] == 2
    assert preview["plan"]["total_cases"] == 1
    assert preview["plan"]["cases"][0]["capability_surfaces"] == []
    assert audit["event"] == "run_plan_previewed"
    assert audit["source"] == "dashboard"
    assert audit["dispatches_requests"] is False
    assert audit["writes_run_artifacts"] is False
    assert "sk-runplan-should-not-render" not in serialized
    assert "AGENTBLASTER_REMOTE_KEY" not in serialized
    assert "Authorization" not in serialized


def test_dashboard_run_plan_uses_configured_enterprise_policy(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    ProviderStore().upsert(
        ProviderConfig(
            name="remote-openai",
            contract=ApiContract.OPENAI,
            base_url="https://api.openai.com/v1",
            default_model="gpt-test",
            api_key_ref=SecretRef(kind="env", name="OPENAI_API_KEY"),
            remote=True,
        )
    )

    with pytest.raises(ConfigError, match="remote providers are disabled by policy"):
        dashboard_run_plan(
            {
                "provider": "remote-openai",
                "suite": "smoke",
                "model": "gpt-test",
                "allow_remote": True,
                "no_raw_traces": True,
            },
            policy=SecurityPolicy(allow_remote_providers=False),
        )


def test_dashboard_http_run_plan_uses_handler_policy(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    ProviderStore().upsert(
        ProviderConfig(
            name="remote-openai",
            contract=ApiContract.OPENAI,
            base_url="https://api.openai.com/v1",
            default_model="gpt-test",
            api_key_ref=SecretRef(kind="env", name="OPENAI_API_KEY"),
            remote=True,
        )
    )
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        make_dashboard_handler(tmp_path, policy=SecurityPolicy(allow_remote_providers=False)),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        response = httpx.post(
            f"{base_url}/api/run-plan",
            json={
                "provider": "remote-openai",
                "suite": "smoke",
                "model": "gpt-test",
                "allow_remote": True,
                "no_raw_traces": True,
            },
            timeout=2.0,
        )

        assert response.status_code == 400
        assert "remote providers are disabled by policy" in response.json()["error"]
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_http_handler_serves_html_api_and_report_artifacts(tmp_path) -> None:
    run_dir = _write_run(tmp_path, run_id="run_test", ok=True)
    (run_dir / "report-card.svg").write_text("<svg>card</svg>", encoding="utf-8")
    (run_dir / "report-card.png").write_bytes(b"\x89PNG\r\n\x1a\ncard")
    metrics_dir = run_dir / "metrics"
    metrics_dir.mkdir()
    (metrics_dir / "prometheus-summary.json").write_text(
        '{"format":"agentblaster-prometheus-summary-v1"}',
        encoding="utf-8",
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_dashboard_handler(tmp_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        html_response = httpx.get(base_url, timeout=2.0)
        api_response = httpx.get(f"{base_url}/api/runs", timeout=2.0)
        run_response = httpx.get(f"{base_url}/api/runs/run_test", timeout=2.0)
        generated_response = httpx.post(
            f"{base_url}/api/runs/run_test/reports",
            json={"formats": ["html", "publication", "card", "pdf"]},
            timeout=2.0,
        )
        form_generate_response = httpx.post(
            f"{base_url}/runs/run_test/reports",
            data={"formats": "md,json"},
            timeout=2.0,
        )
        artifact_response = httpx.get(f"{base_url}/runs/run_test/artifacts/report-card.svg", timeout=2.0)
        png_response = httpx.get(f"{base_url}/runs/run_test/artifacts/report-card.png", timeout=2.0)
        pdf_response = httpx.get(f"{base_url}/runs/run_test/artifacts/report.pdf", timeout=2.0)
        metrics_response = httpx.get(
            f"{base_url}/runs/run_test/artifacts/metrics%2Fprometheus-summary.json",
            timeout=2.0,
        )
        blocked_response = httpx.get(f"{base_url}/runs/run_test/artifacts/manifest.json", timeout=2.0)

        assert html_response.status_code == 200
        assert html_response.headers["x-content-type-options"] == "nosniff"
        assert "form-action 'self'" in html_response.headers["content-security-policy"]
        assert api_response.json()["runs"][0]["run_id"] == "run_test"
        assert api_response.json()["runs"][0]["artifacts"][0]["name"] == "report-card.svg"
        assert run_response.json()["summary"]["passed"] == 1
        assert generated_response.status_code == 201
        assert generated_response.json()["reports"]["run_id"] == "run_test"
        assert any(item["name"] == "report.html" for item in generated_response.json()["reports"]["generated"])
        assert any(item["name"] == "report.pdf" for item in generated_response.json()["reports"]["generated"])
        assert form_generate_response.status_code == 303
        assert form_generate_response.headers["location"] == "/?reports=run_test"
        assert artifact_response.status_code == 200
        assert artifact_response.headers["content-type"].startswith("image/svg+xml")
        assert "card" in artifact_response.text
        assert png_response.status_code == 200
        assert png_response.headers["content-type"].startswith("image/png")
        assert png_response.content.startswith(b"\x89PNG")
        assert pdf_response.status_code == 200
        assert pdf_response.headers["content-type"].startswith("application/pdf")
        assert pdf_response.content.startswith(b"%PDF-1.4")
        assert metrics_response.status_code == 200
        assert metrics_response.json()["format"] == "agentblaster-prometheus-summary-v1"
        assert blocked_response.status_code == 404
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_http_handler_serves_planning_catalog_apis(tmp_path) -> None:
    _write_run(tmp_path, run_id="run_test", ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_dashboard_handler(tmp_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        catalogs = httpx.get(f"{base_url}/api/catalogs", timeout=2.0)
        models = httpx.get(f"{base_url}/api/models", timeout=2.0)
        engine_targets = httpx.get(f"{base_url}/api/engine-targets", timeout=2.0)
        local_onboarding = httpx.get(f"{base_url}/api/local-engine-onboarding", timeout=2.0)
        workflows = httpx.get(f"{base_url}/api/workflow-surfaces", timeout=2.0)
        telemetry = httpx.get(f"{base_url}/api/telemetry-mappings", timeout=2.0)
        setup_status = httpx.get(f"{base_url}/api/setup-status", timeout=2.0)
        run_plan_endpoint = httpx.get(f"{base_url}/api/run-plan", timeout=2.0)
        campaign = httpx.get(f"{base_url}/api/campaign-preview?providers=afm&targets=qwen3.6-27b-dense&suites=smoke,lcp-context", timeout=2.0)
        models_page = httpx.get(f"{base_url}/catalog/models", timeout=2.0)

        assert catalogs.status_code == 200
        assert any(item["href"] == "/api/engine-targets" for item in catalogs.json()["catalogs"])
        assert any(item["href"] == "/api/local-engine-onboarding" for item in catalogs.json()["catalogs"])
        assert models.json()["schema_version"] == "agentblaster.dashboard-model-targets.v1"
        assert engine_targets.json()["schema_version"] == "agentblaster.engine-target-catalog.v1"
        assert local_onboarding.json()["schema_version"] == "agentblaster.local-engine-onboarding.v1"
        assert workflows.json()["schema_version"] == "agentblaster.workflow-surface-catalog.v1"
        assert telemetry.json()["schema_version"] == "agentblaster.telemetry-mapping-catalog.v1"
        assert setup_status.json()["schema_version"] == "agentblaster.dashboard-setup-status.v1"
        assert run_plan_endpoint.json()["schema_version"] == "agentblaster.dashboard-run-plan-endpoint.v1"
        assert run_plan_endpoint.json()["method"] == "POST"
        assert campaign.json()["schema_version"] == "agentblaster.campaign-preview.v1"
        assert campaign.json()["matrix_run_count"] == 2
        assert models_page.status_code == 200
        assert models_page.headers["content-type"].startswith("text/html")
        assert "AgentBlaster Catalog - Models" in models_page.text
        assert "Open JSON API" in models_page.text
        assert "/api/models" in models_page.text
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_http_handler_supports_token_auth_for_browser_and_api(tmp_path) -> None:
    _write_run(tmp_path, run_id="run_test", ok=True)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        make_dashboard_handler(tmp_path, auth_token="dashboard-secret-token"),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        unauthenticated_html = httpx.get(base_url, timeout=2.0)
        login_response = httpx.get(f"{base_url}/login", timeout=2.0)
        unauthenticated_api = httpx.get(f"{base_url}/api/runs", timeout=2.0)
        bad_login = httpx.post(f"{base_url}/login", data={"token": "wrong-token"}, timeout=2.0)
        bearer_response = httpx.get(
            f"{base_url}/api/runs",
            headers={"authorization": "Bearer dashboard-secret-token"},
            timeout=2.0,
        )
        browser = httpx.Client(base_url=base_url, follow_redirects=False)
        good_login = browser.post("/login", data={"token": "dashboard-secret-token"}, timeout=2.0)
        cookie_html = browser.get("/", timeout=2.0)
        logout = browser.get("/logout", timeout=2.0)

        assert unauthenticated_html.status_code == 303
        assert unauthenticated_html.headers["location"] == "/login"
        assert login_response.status_code == 200
        assert 'data-testid="dashboard-login"' in login_response.text
        assert unauthenticated_api.status_code == 401
        assert unauthenticated_api.headers["www-authenticate"] == 'Bearer realm="AgentBlaster Dashboard"'
        assert bad_login.status_code == 401
        assert "wrong-token" not in bad_login.text
        assert bearer_response.status_code == 200
        assert bearer_response.json()["runs"][0]["run_id"] == "run_test"
        assert good_login.status_code == 303
        assert "agentblaster_dashboard=" in good_login.headers["set-cookie"]
        assert "dashboard-secret-token" not in good_login.headers["set-cookie"]
        assert cookie_html.status_code == 200
        assert 'data-testid="auth-status"' in cookie_html.text
        assert logout.status_code == 303
        browser.close()
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_http_handler_configures_provider_profile_without_secret_values(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    audit_log = tmp_path / "provider-http-audit.jsonl"
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        make_dashboard_handler(tmp_path, audit_log=audit_log, policy=SecurityPolicy(allow_remote_providers=False)),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        response = httpx.post(
            f"{base_url}/api/providers",
            json={
                "name": "remote-anthropic",
                "contract": "anthropic",
                "base_url": "https://api.anthropic.com",
                "default_model": "claude-test",
                "remote": True,
                "api_key_env": "ANTHROPIC_API_KEY",
            },
            timeout=2.0,
        )
        providers = httpx.get(f"{base_url}/api/providers", timeout=2.0)
        audit = json.loads(audit_log.read_text(encoding="utf-8").splitlines()[0])
        serialized = json.dumps({"response": response.json(), "providers": providers.json(), "audit": audit})

        assert response.status_code == 201
        assert response.json()["provider"]["name"] == "remote-anthropic"
        assert response.json()["provider"]["policy_review"]["ok"] is False
        assert providers.json()["providers"][0]["api_key_ref"] == "env:ANTHROPIC_API_KEY"
        assert audit["event"] == "provider_created"
        assert audit["source"] == "dashboard"
        assert audit["policy_ok"] is False
        assert "sk-" not in serialized
        assert "Bearer " not in serialized
        assert "Authorization" not in serialized
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_http_handler_configures_provider_auth_without_echoing_secret(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("AGENTBLASTER_REMOTE_KEY", "sk-http-should-not-render")
    audit_log = tmp_path / "dashboard-audit.jsonl"
    ProviderStore().upsert(
        ProviderConfig(
            name="remote-openai",
            contract=ApiContract.OPENAI,
            base_url="https://api.openai.com/v1",
            remote=True,
        )
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_dashboard_handler(tmp_path, audit_log=audit_log))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        response = httpx.post(
            f"{base_url}/api/providers/remote-openai/auth",
            json={"method": "env", "env_var": "AGENTBLASTER_REMOTE_KEY"},
            timeout=2.0,
        )
        providers = httpx.get(f"{base_url}/api/providers", timeout=2.0)
        serialized = json.dumps({"auth": response.json(), "providers": providers.json()})
        audit = json.loads(audit_log.read_text(encoding="utf-8").splitlines()[0])

        assert response.status_code == 201
        assert response.json()["auth"]["secret_backend"] == "env"
        assert response.json()["auth"]["stored_secret"] is False
        assert providers.json()["providers"][0]["api_key_ref"] is not None
        assert audit["event"] == "provider_auth_ref_changed"
        assert audit["source"] == "dashboard"
        assert audit["provider"] == "remote-openai"
        assert "AGENTBLASTER_REMOTE_KEY" in serialized
        assert "sk-http-should-not-render" not in serialized
        assert "sk-http-should-not-render" not in json.dumps(audit)
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_http_handler_stores_and_clears_keyring_auth_without_echoing_secret(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    audit_log = tmp_path / "dashboard-audit.jsonl"

    class FakeKeyring:
        values: dict[tuple[str, str], str] = {}

        @classmethod
        def get_password(cls, service: str, name: str) -> str | None:
            return cls.values.get((service, name))

        @classmethod
        def set_password(cls, service: str, name: str, value: str) -> None:
            cls.values[(service, name)] = value

        @classmethod
        def delete_password(cls, service: str, name: str) -> None:
            cls.values.pop((service, name), None)

    monkeypatch.setitem(sys.modules, "keyring", FakeKeyring)
    ProviderStore().upsert(
        ProviderConfig(
            name="remote-openai",
            contract=ApiContract.OPENAI,
            base_url="https://api.openai.com/v1",
            remote=True,
        )
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_dashboard_handler(tmp_path, audit_log=audit_log))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        set_response = httpx.post(
            f"{base_url}/api/providers/remote-openai/auth",
            json={"method": "keyring", "api_key": "sk-dashboard-keyring-secret"},
            timeout=2.0,
        )
        providers_after_set = httpx.get(f"{base_url}/api/providers", timeout=2.0)
        clear_response = httpx.delete(f"{base_url}/api/providers/remote-openai/auth?delete_secret=true", timeout=2.0)
        providers_after_clear = httpx.get(f"{base_url}/api/providers", timeout=2.0)
        audit_text = audit_log.read_text(encoding="utf-8")
        serialized = json.dumps(
            {
                "set": set_response.json(),
                "providers_after_set": providers_after_set.json(),
                "clear": clear_response.json(),
                "providers_after_clear": providers_after_clear.json(),
                "audit": audit_text,
            }
        )

        assert set_response.status_code == 201
        assert set_response.json()["auth"]["api_key_ref"] == "keyring:remote-openai:api_key"
        assert set_response.json()["auth"]["secret_backend"] == "keyring"
        assert set_response.json()["auth"]["stored_secret"] is True
        assert providers_after_set.json()["providers"][0]["api_key_ref"] == "keyring:remote-openai:api_key"
        assert clear_response.status_code == 200
        assert clear_response.json()["auth"]["previous_api_key_ref"] == "keyring:remote-openai:api_key"
        assert clear_response.json()["auth"]["deleted_secret"] is True
        assert providers_after_clear.json()["providers"][0]["api_key_ref"] is None
        assert FakeKeyring.values == {}
        assert "sk-dashboard-keyring-secret" not in serialized
        assert "Authorization" not in serialized
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_http_handler_serves_run_plan_without_launching(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    ProviderStore().upsert(
        ProviderConfig(
            name="local-openai",
            contract=ApiContract.OPENAI,
            base_url="http://127.0.0.1:9999/v1",
            default_model="qwen-default",
        )
    )
    runs_dir = tmp_path / "runs"
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_dashboard_handler(runs_dir))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        response = httpx.post(
            f"{base_url}/api/run-plan",
            json={
                "provider": "local-openai",
                "suite": "smoke",
                "concurrency": 1,
                "no_raw_traces": True,
            },
            timeout=2.0,
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["schema_version"] == "agentblaster.dashboard-run-plan.v1"
        assert payload["safety"]["dispatches_requests"] is False
        assert payload["safety"]["writes_run_artifacts"] is False
        assert payload["plan"]["provider"] == "local-openai"
        assert payload["plan"]["total_cases"] == 1
        assert not list(runs_dir.glob("*/results.jsonl"))

        form_response = httpx.post(
            f"{base_url}/run-plan",
            data={
                "provider": "local-openai",
                "suite": "smoke",
                "model": "qwen-default",
                "raw_traces": "off",
                "concurrency": "1",
            },
            timeout=2.0,
        )

        assert form_response.status_code == 200
        assert 'data-testid="run-plan-panel"' in form_response.text
        assert 'data-testid="run-plan-safety"' in form_response.text
        assert "Capability surfaces" in form_response.text
        assert ">none</td>" in form_response.text
        assert "dispatches_requests" in form_response.text
        assert not list(runs_dir.glob("*/results.jsonl"))
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_artifact_path_allows_only_report_artifacts(tmp_path) -> None:
    run_dir = _write_run(tmp_path, run_id="run_test", ok=True)
    (run_dir / "publication.json").write_text("{}", encoding="utf-8")
    (run_dir / "report.pdf").write_bytes(b"%PDF-1.4\n")
    metrics_dir = run_dir / "metrics"
    metrics_dir.mkdir()
    (metrics_dir / "prometheus-summary.json").write_text("{}", encoding="utf-8")

    assert dashboard_artifact_path(tmp_path, "run_test", "publication.json") == run_dir / "publication.json"
    assert dashboard_artifact_path(tmp_path, "run_test", "report.pdf") == run_dir / "report.pdf"
    assert (
        dashboard_artifact_path(tmp_path, "run_test", "metrics/prometheus-summary.json")
        == run_dir / "metrics/prometheus-summary.json"
    )
    with pytest.raises(ConfigError, match="unknown dashboard artifact"):
        dashboard_artifact_path(tmp_path, "run_test", "manifest.json")


def test_dashboard_http_handler_can_launch_local_run(monkeypatch, tmp_path) -> None:
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
                        "choices": [{"message": {"content": "agentblaster-ok"}, "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
                    }
                ).encode()
            )

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

    provider_server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    provider_thread = threading.Thread(target=provider_server.serve_forever, daemon=True)
    provider_thread.start()
    dashboard_server = None
    audit_log = tmp_path / "dashboard-launch-audit.jsonl"

    try:
        monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
        ProviderStore().upsert(
            ProviderConfig(
                name="local-openai",
                contract=ApiContract.OPENAI,
                base_url=f"http://127.0.0.1:{provider_server.server_address[1]}/v1",
            )
        )
        runs_dir = tmp_path / "runs"
        dashboard_server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            make_dashboard_handler(runs_dir, audit_log=audit_log),
        )
        dashboard_thread = threading.Thread(target=dashboard_server.serve_forever, daemon=True)
        dashboard_thread.start()
        base_url = f"http://127.0.0.1:{dashboard_server.server_address[1]}"

        response = httpx.post(
            f"{base_url}/api/runs",
            json={
                "provider": "local-openai",
                "suite": "smoke",
                "model": "qwen-test",
                "no_raw_traces": True,
            },
            timeout=3.0,
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["schema_version"] == "agentblaster.dashboard-run-launch.v1"
        assert payload["safety"]["preview_only"] is False
        assert payload["safety"]["dispatches_requests"] is True
        assert payload["safety"]["contacts_provider"] is True
        assert payload["safety"]["writes_run_artifacts"] is True
        assert payload["safety"]["policy_enforced"] is True
        assert payload["safety"]["capability_preflight"] is True
        assert payload["artifacts"]["events"] == "events.jsonl"
        assert payload["artifacts"]["integrity"] == "integrity.json"
        assert payload["summary"]["provider"] == "local-openai"
        assert payload["summary"]["passed"] == 1
        assert list(runs_dir.glob("*/results.jsonl"))
        audit_events = [json.loads(line)["event"] for line in audit_log.read_text(encoding="utf-8").splitlines()]
        assert audit_events[:3] == [
            "dashboard_capability_preflight",
            "dashboard_run_launch_requested",
            "dashboard_run_launched",
        ]

        form_response = httpx.post(
            f"{base_url}/launch",
            data={
                "provider": "local-openai",
                "suite": "smoke",
                "model": "qwen-test",
                "raw_traces": "off",
                "concurrency": "1",
                "capability_preflight": "true",
            },
            timeout=3.0,
        )

        assert form_response.status_code == 303
        assert form_response.headers["location"].startswith("/?launched=run_")
    finally:
        provider_server.shutdown()
        provider_server.server_close()
        if dashboard_server is not None:
            dashboard_server.shutdown()
            dashboard_server.server_close()


def test_dashboard_launch_blocks_incompatible_capability_preflight(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    ProviderStore().upsert(
        ProviderConfig(
            name="local-openai",
            contract=ApiContract.OPENAI,
            base_url="http://127.0.0.1:9999/v1",
            default_model="qwen-default",
        )
    )

    with pytest.raises(ConfigError):
        launch_dashboard_run(
            tmp_path / "runs",
            {
                "provider": "local-openai",
                "suite": "cancellation",
                "model": "qwen-default",
                "no_raw_traces": True,
                "capability_preflight": True,
                "strict_unknown_capabilities": True,
            },
        )

    assert not list((tmp_path / "runs").glob("*/results.jsonl"))


def test_dashboard_blocks_non_loopback_bind_without_opt_in() -> None:
    with pytest.raises(ConfigError, match="loopback"):
        assert_dashboard_bind_allowed("0.0.0.0")

    with pytest.raises(ConfigError, match="authentication"):
        assert_dashboard_bind_allowed("0.0.0.0", allow_non_loopback=True)

    assert_dashboard_bind_allowed("0.0.0.0", allow_non_loopback=True, auth_configured=True)


def _write_run(tmp_path, *, run_id: str, ok: bool, raw_trace_mode: RawTraceMode = RawTraceMode.REDACTED):
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    manifest = RunManifest(
        run_id=run_id,
        suite="smoke",
        provider="local",
        contract=ApiContract.OPENAI,
        model="qwen-test",
        raw_trace_mode=raw_trace_mode,
        created_at="2026-05-31T00:00:00Z",
        case_count=1,
        concurrency=2,
        suite_sha256="abc123def4567890",
        suite_snapshot_path="suite.json",
        suite_provenance={
            "origin": "builtin",
            "primary_source": "AgentBlaster",
            "license": "MIT",
        },
        provider_metadata={
            "base_url": "http://127.0.0.1:9999/v1",
            "base_url_host": "127.0.0.1",
            "remote": False,
            "adapter_name": "openai-chat-completions",
            "adapter_version": "agentblaster-adapter-v1",
            "capabilities": {"streaming": True},
        },
        metrics_artifacts=["metrics/prometheus-summary.json"],
        model_metadata=ModelMetadata(
            revision="rev-1",
            architecture="qwen3-dense",
            quantization="mlx-f16",
            context_length=32768,
        ),
    )
    result = BenchmarkResult(
        run_id=run_id,
        case_id="case-one",
        suite="smoke",
        provider="local",
        contract=ApiContract.OPENAI,
        model="qwen-test",
        ok=ok,
        request_started_at="2026-05-31T00:00:00+00:00",
        request_completed_at="2026-05-31T00:00:02+00:00",
        queue_ms=3.0,
        rate_limit_wait_ms=2.0,
        latency_ms=10.0,
        ttft_ms=200.0,
        total_cost_usd=0.000111,
        input_tokens=2,
        output_tokens=1,
        total_tokens=3,
        tokens_per_second_decode=25.0,
        failure_class=None if ok else "model_quality",
        message="ok" if ok else "missing expected substring",
        raw_response_path="raw/case-one.response.json",
    )
    (run_dir / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    (run_dir / "results.jsonl").write_text(result.model_dump_json() + "\n", encoding="utf-8")
    return run_dir
