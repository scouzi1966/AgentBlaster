from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from agentblaster.models import (
    ApiContract,
    BenchmarkResult,
    ModelMetadata,
    ProviderRunMetadata,
    RawTraceMode,
    RetentionPolicy,
    RunManifest,
    SuiteDefinition,
    SuiteProvenance,
)

DASHBOARD_FIXTURE_PROFILE = "deterministic-redacted"
DASHBOARD_FIXTURE_RUN_IDS = ("run_dashboard_fixture_pass", "run_dashboard_fixture_fail")
DASHBOARD_FIXTURE_EVIDENCE_DIRS = ("campaign-preflight", "release-bundles", "test-reports")


@dataclass(frozen=True)
class DashboardFixture:
    profile: str
    runs_dir: Path
    manifest_path: Path
    run_ids: tuple[str, ...]
    artifact_paths: tuple[Path, ...]


def write_dashboard_fixture(
    output_dir: Path,
    *,
    profile: str = DASHBOARD_FIXTURE_PROFILE,
    overwrite: bool = False,
) -> DashboardFixture:
    """Write deterministic, redaction-safe dashboard runs for GUI selftests."""
    if profile != DASHBOARD_FIXTURE_PROFILE:
        raise ValueError(f"unknown dashboard fixture profile: {profile}")
    output_dir = output_dir.expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    _prepare_output_dir(output_dir, overwrite=overwrite)

    artifact_paths: list[Path] = []
    artifact_paths.extend(_write_fixture_run(output_dir, run_id="run_dashboard_fixture_pass", ok=True))
    artifact_paths.extend(_write_fixture_run(output_dir, run_id="run_dashboard_fixture_fail", ok=False))
    artifact_paths.extend(_write_fixture_campaign_preflight(output_dir))
    artifact_paths.append(_write_fixture_release_bundle(output_dir))
    artifact_paths.append(_write_fixture_selftest_report(output_dir))
    manifest_path = output_dir / "dashboard-fixture.json"
    manifest = {
        "schema_version": "agentblaster.dashboard-fixture.v1",
        "profile": profile,
        "runs_dir": str(output_dir),
        "run_ids": list(DASHBOARD_FIXTURE_RUN_IDS),
        "contains_real_secrets": False,
        "contains_remote_calls": False,
        "raw_trace_mode": "redacted",
        "intended_for": ["dashboard gui tests", "Chrome/Codex validation", "Playwright fixtures"],
        "review_artifact_dirs": list(DASHBOARD_FIXTURE_EVIDENCE_DIRS),
        "safety_notes": [
            "Fixture artifacts use mock local provider metadata only.",
            "No API keys or Authorization header values are stored.",
            "Raw response examples contain only redacted placeholders.",
            "Direct selftest reports include compact SDLC status metadata only.",
            "Campaign preflight fixtures include a compact no-local-path manifest review summary plus benchmark readiness summaries only.",
            "Release qualification fixture bundles include compact matrix-gate, campaign-preflight, selftest, harness-review, engine-advisory, evidence-index readiness/cleanup, suite-audit, and metric-coverage summaries only.",
        ],
        "artifact_count": len(artifact_paths),
        "artifact_sha256": {
            path.relative_to(output_dir).as_posix(): _sha256_file(path)
            for path in sorted(artifact_paths)
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    artifact_paths.append(manifest_path)
    return DashboardFixture(
        profile=profile,
        runs_dir=output_dir,
        manifest_path=manifest_path,
        run_ids=DASHBOARD_FIXTURE_RUN_IDS,
        artifact_paths=tuple(artifact_paths),
    )


def _prepare_output_dir(output_dir: Path, *, overwrite: bool) -> None:
    existing_fixture_paths = [output_dir / run_id for run_id in DASHBOARD_FIXTURE_RUN_IDS]
    existing_evidence_paths = [output_dir / directory for directory in DASHBOARD_FIXTURE_EVIDENCE_DIRS]
    existing_manifest = output_dir / "dashboard-fixture.json"
    existing_known = [path for path in [*existing_fixture_paths, *existing_evidence_paths, existing_manifest] if path.exists()]
    known_names = {*DASHBOARD_FIXTURE_RUN_IDS, *DASHBOARD_FIXTURE_EVIDENCE_DIRS, "dashboard-fixture.json"}
    unknown_entries = [path for path in output_dir.iterdir() if path.name not in known_names]
    if unknown_entries:
        names = ", ".join(sorted(path.name for path in unknown_entries[:5]))
        raise ValueError(f"dashboard fixture output directory contains non-fixture entries: {names}")
    if existing_known and not overwrite:
        raise ValueError("dashboard fixture output already exists; pass --overwrite to replace known fixture artifacts")
    if overwrite:
        for path in existing_fixture_paths:
            if path.exists():
                shutil.rmtree(path)
        for path in existing_evidence_paths:
            if path.exists():
                shutil.rmtree(path)
        if existing_manifest.exists():
            existing_manifest.unlink()


def _write_fixture_run(output_dir: Path, *, run_id: str, ok: bool) -> list[Path]:
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    suite = _fixture_suite()
    manifest = _fixture_manifest(run_id=run_id, suite=suite, ok=ok)
    result = _fixture_result(run_id=run_id, ok=ok)

    written: list[Path] = []
    written.append(_write_json(run_dir / "manifest.json", manifest.model_dump(mode="json")))
    written.append(_write_json(run_dir / "suite.json", suite.model_dump(mode="json")))
    written.append(_write_jsonl(run_dir / "results.jsonl", [result.model_dump(mode="json")]))
    written.append(_write_json(run_dir / "summary.json", _summary_payload(run_id=run_id, ok=ok)))
    written.extend(_write_report_artifacts(run_dir, run_id=run_id, ok=ok))
    raw_dir = run_dir / "raw"
    raw_dir.mkdir(exist_ok=True)
    written.append(
        _write_json(
            raw_dir / "fixture-case.response.json",
            {
                "fixture": True,
                "headers": {"Authorization": "Bearer [REDACTED]"},
                "body": {"message": result.message, "api_key": "[REDACTED]"},
            },
        )
    )
    written.append(_write_json(run_dir / "integrity.json", _integrity_payload(run_dir, written)))
    return written


def _write_fixture_campaign_preflight(output_dir: Path) -> list[Path]:
    preflight_dir = output_dir / "campaign-preflight" / "qwen-gemma-local"
    manifest = _write_json(
        preflight_dir / "manifest.json",
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
                "run_count": 2,
                "total_cases": 2,
                "matrices": [
                    {
                        "matrix": "qwen-gemma-local",
                        "artifact_path": "matrices/001-qwen-gemma-local-inventory.json",
                        "pressure_artifact_path": "pressure/001-qwen-gemma-local-pressure.json",
                        "run_count": 2,
                        "total_cases": 2,
                    }
                ],
                "includes_provider_audit": False,
                "includes_benchmark_readiness": True,
                "benchmark_readiness_report_count": 1,
                "security": {
                    "contains_local_paths": False,
                    "contains_raw_secrets": False,
                    "contains_raw_provider_payloads": False,
                    "contains_raw_traces": False,
                    "external_publication_safe": True,
                    "notes": "Dashboard fixture manifest review summary only; local paths and dry-run commands are excluded.",
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
    )
    report = {
        "source_path": "reports/afm-trace-readiness.json",
        "source_name": "afm-trace-readiness.json",
        "source_path_redacted": True,
        "source_sha256": _sha256_json(_fixture_benchmark_readiness_report()),
        "schema_version": "agentblaster.benchmark-readiness.v1",
        "provider": "afm",
        "suite": "trace-replay",
        "model": "mlx-community/Qwen3.6-27B",
        "ready": True,
        "strict_unknown": True,
        "policy_ok": True,
        "suite_compatible": True,
        "contract_checks_planned": 8,
        "contract_capabilities_directly_checked": 4,
        "contract_capabilities_proxy_checked": 1,
        "contract_capabilities_not_covered": 1,
        "metric_coverage_score": 0.78,
        "provider_auth_writable_backends": 1,
        "provider_auth_plaintext_fallbacks": 0,
        "provider_auth_prewrite_policy_guards_recommended": 0,
        "blocking_findings": 0,
        "warnings": 1,
        "provider_auth_posture": [
            {
                "provider": "afm",
                "api_key_ref_kind": "keyring",
                "api_key_ref_configured": True,
                "api_key_ref_writable_backend": True,
                "api_key_ref_plaintext_fallback": False,
                "prewrite_policy_guard_recommended": False,
            }
        ],
    }
    readiness_index = _write_json(
        output_dir / "campaign-preflight" / "qwen-gemma-local" / "readiness" / "benchmark-readiness-index.json",
        {
            "schema_version": "agentblaster.campaign-preflight-benchmark-readiness-index.v1",
            "report_count": 1,
            "reports": [report],
            "security": {
                "contacts_providers": False,
                "resolves_secrets": False,
                "reads_keyring_values": False,
                "contains_raw_secrets": False,
                "contains_raw_provider_payloads": False,
                "contains_raw_traces": False,
                "notes": "Contains compact summaries from benchmark readiness dossiers only; raw provider configs, API keys, prompts, traces, and endpoint payloads are excluded.",
            },
        },
    )
    return [manifest, readiness_index]


def _fixture_benchmark_readiness_report() -> dict[str, Any]:
    return {
        "schema_version": "agentblaster.benchmark-readiness.v1",
        "provider": "afm",
        "suite": "trace-replay",
        "model": "mlx-community/Qwen3.6-27B",
        "ready": True,
        "strict_unknown": True,
        "summary": {
            "policy_ok": True,
            "suite_compatible": True,
            "contract_checks_planned": 8,
            "contract_capabilities_directly_checked": 4,
            "contract_capabilities_proxy_checked": 1,
            "contract_capabilities_not_covered": 1,
            "metric_coverage_score": 0.78,
            "provider_auth_writable_backends": 1,
            "provider_auth_plaintext_fallbacks": 0,
            "provider_auth_prewrite_policy_guards_recommended": 0,
            "blocking_findings": 0,
            "warnings": 1,
        },
        "provider_auth_posture": [
            {
                "provider": "afm",
                "api_key_ref_kind": "keyring",
                "api_key_ref_configured": True,
                "api_key_ref_writable_backend": True,
                "api_key_ref_plaintext_fallback": False,
                "prewrite_policy_guard_recommended": False,
            }
        ],
    }


def _fixture_manifest(*, run_id: str, suite: SuiteDefinition, ok: bool) -> RunManifest:
    return RunManifest(
        run_id=run_id,
        suite=suite.name,
        provider="mock-local-dashboard",
        contract=ApiContract.OPENAI,
        model="fixture-qwen3.6-27b-dense",
        raw_trace_mode=RawTraceMode.REDACTED,
        created_at="2026-05-31T00:00:00Z" if ok else "2026-05-31T00:01:00Z",
        case_count=1,
        concurrency=1,
        suite_sha256=_sha256_json(suite.model_dump(mode="json")),
        case_sha256={case.id: _sha256_json(case.model_dump(mode="json")) for case in suite.cases},
        suite_snapshot_path="suite.json",
        suite_provenance=suite.provenance,
        metrics_artifacts=["metrics/prometheus-summary.json"],
        provider_metadata=ProviderRunMetadata(
            base_url="http://127.0.0.1:9999/v1",
            base_url_host="127.0.0.1",
            remote=False,
            native_adapter=None,
            adapter_name="mock-dashboard-fixture",
            adapter_version="agentblaster-fixture-v1",
            capabilities={"streaming": True, "tool_calling": True, "structured_output": True},
            metrics_url_host=None,
            tls_verify=True,
            ca_bundle=None,
        ),
        model_metadata=ModelMetadata(
            revision="fixture-revision",
            architecture="qwen3.6-dense",
            quantization="mock-f16",
            context_length=32768,
        ),
        retention_policy=RetentionPolicy(
            classification="internal",
            retain_days=7,
            raw_trace_retain_days=1,
            notes=["Generated dashboard GUI fixture; safe for local selftests."],
        ),
    )


def _fixture_suite() -> SuiteDefinition:
    return SuiteDefinition(
        name="dashboard-fixture",
        description="Deterministic redacted dashboard GUI fixture suite.",
        provenance=SuiteProvenance(
            origin="internal_regression",
            primary_source="AgentBlaster",
            license="MIT",
            risk_labels=["fixture", "redacted", "gui-selftest"],
            notes=["Generated by agentblaster fixtures for dashboard validation."],
        ),
        cases=[
            {
                "id": "fixture-case",
                "title": "Dashboard fixture case",
                "prompt": "Reply with exactly: agentblaster-fixture-ok",
                "expected_substring": "agentblaster-fixture-ok",
                "metrics": ["latency_ms", "ttft_ms", "tokens_per_second_decode"],
                "tags": ["fixture", "dashboard", "gui"],
                "risk_level": "low",
                "provenance": "internal_regression",
                "license": "MIT",
            }
        ],
    )


def _fixture_result(*, run_id: str, ok: bool) -> BenchmarkResult:
    return BenchmarkResult(
        run_id=run_id,
        case_id="fixture-case",
        case_title="Dashboard fixture case",
        scenario="dashboard-gui-fixture",
        case_tags=["fixture", "dashboard", "gui"],
        case_provenance="internal_regression",
        case_risk_level="low",
        case_license="MIT",
        suite="dashboard-fixture",
        provider="mock-local-dashboard",
        contract=ApiContract.OPENAI,
        model="fixture-qwen3.6-27b-dense",
        ok=ok,
        provider_endpoint_host="127.0.0.1",
        provider_remote=False,
        adapter_name="mock-dashboard-fixture",
        adapter_version="agentblaster-fixture-v1",
        status_code=200 if ok else 200,
        request_started_at="2026-05-31T00:00:00Z",
        request_completed_at="2026-05-31T00:00:02Z" if ok else "2026-05-31T00:00:03Z",
        queue_ms=0.0,
        rate_limit_wait_ms=0.0,
        latency_ms=120.0 if ok else 180.0,
        input_tokens=128,
        output_tokens=12 if ok else 8,
        total_tokens=140 if ok else 136,
        cached_input_tokens=64,
        cache_write_tokens=64,
        cache_hit_ratio=0.5,
        total_cost_usd=0.0,
        ttft_ms=45.0 if ok else 60.0,
        prompt_eval_ms=30.0,
        decode_ms=70.0 if ok else 100.0,
        tokens_per_second_prefill=4266.667,
        tokens_per_second_decode=171.429 if ok else 80.0,
        raw_usage={"prompt_tokens": 128, "completion_tokens": 12 if ok else 8, "total_tokens": 140 if ok else 136},
        raw_stats={"fixture": True, "redacted": True},
        tool_calls_requested=0,
        tool_calls_emitted=0,
        tool_calls_valid=0,
        structured_output_valid=True,
        finish_reason="stop",
        failure_class=None if ok else "model_quality",
        message="agentblaster-fixture-ok" if ok else "fixture failure: expected marker missing",
        raw_response_path="raw/fixture-case.response.json",
    )


def _summary_payload(*, run_id: str, ok: bool) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "total_cases": 1,
        "passed": 1 if ok else 0,
        "failed": 0 if ok else 1,
        "duration_ms": 2000.0 if ok else 3000.0,
        "requests_per_second": 0.5 if ok else 0.333,
        "fixture": True,
        "redacted": True,
    }


def _write_fixture_release_bundle(output_dir: Path) -> Path:
    bundle_dir = output_dir / "release-bundles"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    output = bundle_dir / "dashboard-fixture.agentblaster-release-qualification.zip"
    manifest = {
        "schema": "agentblaster.release-qualification-bundle",
        "schema_version": 1,
        "name": "dashboard-fixture",
        "ok": True,
        "artifact_count": 10,
        "artifact_status": {"pass": 4, "review": 6},
        "artifacts": [
            {
                "category": "gates/matrix",
                "archive_path": "gates/matrix/dashboard-fixture-matrix-gate.json",
                "schema": "agentblaster.matrix-gate.v1",
                "status": "pass",
                "status_source": "ok",
                "review_summary": {
                    "schema_version": "agentblaster.matrix-gate.v1",
                    "matrix_name": "dashboard-fixture",
                    "pass_rate_percent": 50.0,
                    "failure_class_summary": [{"failure_class": "model_quality", "count": 1}],
                    "failure_class_artifacts_missing": 0,
                    "tool_loop_stop_summary": [{"stop_reason": "final_response", "count": 2}],
                    "tool_loop_artifacts_missing": 0,
                    "invalid_tool_call_count": 1,
                    "tool_parser_repair_cases": 2,
                    "tool_parser_repairs_valid": 1,
                    "tool_parser_repair_valid_rate_percent": 50.0,
                    "tool_parser_repair_artifacts_missing": 0,
                },
            },
            {
                "category": "audits/provider-contract-matrix",
                "archive_path": "audits/provider-contract-matrix/dashboard-fixture-provider-contract-matrix.json",
                "schema": "agentblaster.provider-contract-matrix.v1",
                "status": "pass",
                "status_source": "ok",
                "review_summary": {
                    "schema_version": "agentblaster.provider-contract-matrix.v1",
                    "mode": "executed",
                    "ok": True,
                    "matrix": "dashboard-fixture",
                    "target_count": 1,
                    "checks": {
                        "planned_checks": 5,
                        "passed_checks": 5,
                        "failed_checks": 0,
                        "skipped_checks": 0,
                    },
                    "capability_evidence": {
                        "directly_checked": ["streaming", "structured_output", "tool_calling"],
                        "proxy_checked_counts": {"judge_rubric": 1},
                        "not_covered_counts": {"prompt_caching": 1},
                    },
                },
            },
            {
                "category": "selftest",
                "archive_path": "selftest/dashboard-fixture-selftest-report.json",
                "schema": "agentblaster.selftest-report.v1",
                "status": "pass",
                "status_source": "selftest.ok",
                "review_summary": {
                    "schema_version": "agentblaster.selftest-report.v1",
                    "run_id": "selftest_dashboard_fixture",
                    "tier": "gui",
                    "ok": True,
                    "exit_code": 0,
                    "duration_ms": 1000.0,
                    "browser": "chromium",
                    "headed": False,
                    "marker_expression": "gui",
                    "junit_xml_present": True,
                },
            },
            {
                "category": "readiness/implementation",
                "archive_path": "readiness/implementation/dashboard-fixture-implementation-status.json",
                "schema": "agentblaster.implementation-status.v1",
                "status": "pass",
                "status_source": "implementation-status.status",
                "review_summary": {
                    "schema_version": "agentblaster.implementation-status.v1",
                    "status": "implementation-ready-for-validation",
                    "implemented_areas": 9,
                    "partial_areas": 0,
                    "missing_areas": 0,
                    "built_in_suite_count": 8,
                    "harness_engineering_suite_present": True,
                    "harness_engineering_case_count": 4,
                    "stats_profile_count": 8,
                    "stats_metric_provider_count": 11,
                    "keyring_optional": True,
                    "secret_backends": ["env", "keyring", "dotenv"],
                    "chrome_codex_gate_present": True,
                    "tests_run_by_this_command": False,
                    "shareable_summary_only": True,
                },
            },
            {
                "category": "readiness/campaign-preflight",
                "archive_path": "readiness/campaign-preflight/dashboard-fixture-campaign-preflight-manifest.json",
                "schema": "agentblaster.campaign-preflight-bundle.v1",
                "status": "review",
                "status_source": "review.status",
                "review_summary": {
                    "schema_version": "agentblaster.campaign-preflight-bundle.v1",
                    "review_summary_schema_version": "agentblaster.campaign-preflight-review-summary.v1",
                    "matrix_count": 1,
                    "run_count": 2,
                    "total_cases": 2,
                    "includes_provider_audit": False,
                    "includes_benchmark_readiness": True,
                    "benchmark_readiness_report_count": 1,
                    "contains_local_paths": False,
                    "external_publication_safe": True,
                },
            },
            {
                "category": "harness/review",
                "archive_path": "harness/review/dashboard-fixture-harness-review.json",
                "schema": "agentblaster.harness-review.v1",
                "status": "review",
                "status_source": "review.status",
                "review_summary": {
                    "schema_version": "agentblaster.harness-review.v1",
                    "suite_name": "dashboard-fixture-orchestration",
                    "case_count": 4,
                    "generated": True,
                    "generator_profile": "orchestration",
                    "review_status": "calibration-required",
                    "human_review_required": True,
                    "calibration_required_before_release_gate": True,
                    "surface_counts": {
                        "multi_tool_catalog_cases": 4,
                        "tool_loop_cases": 4,
                    },
                    "assertion_counts": {"tool_name": 4},
                },
            },
            {
                "category": "advisory/engine",
                "archive_path": "advisory/engine/dashboard-fixture-engine-advisory.json",
                "schema": "agentblaster.engine-improvement-advisory.v1",
                "status": "review",
                "status_source": "review.status",
                "review_summary": {
                    "schema_version": "agentblaster.engine-improvement-advisory.v1",
                    "engine": "afm",
                    "priority_count": 3,
                    "highest_priority": 1,
                    "no_dispatch": True,
                    "top_priorities": [
                        {
                            "priority": 1,
                            "area": "contract-conformance",
                            "aligned_artifacts_or_suites": ["provider contract checks", "matrix contract-checks"],
                        },
                        {
                            "priority": 2,
                            "area": "harness-calibration",
                            "aligned_artifacts_or_suites": ["harness review", "suite-calibration"],
                        },
                        {
                            "priority": 1,
                            "area": "agentic-protocol-repair",
                            "aligned_artifacts_or_suites": ["matrix gate", "tool-parser-repair suite"],
                        },
                    ],
                },
            },
            {
                "category": "evidence/index",
                "archive_path": "evidence/index/dashboard-fixture-evidence-index.json",
                "schema": "agentblaster.evidence-index.v1",
                "status": "review",
                "status_source": "schema.review",
                "review_summary": {
                    "schema_version": "agentblaster.evidence-index.v1",
                    "name": "dashboard-fixture",
                    "artifact_count": 4,
                    "status_counts": {"fail": 1, "pass": 2, "review": 1},
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
                },
            },
            {
                "category": "governance/suite-audit",
                "archive_path": "governance/suite-audit/dashboard-fixture-suite-audit.json",
                "schema": "agentblaster.suite-audit.v1",
                "status": "review",
                "status_source": "review.status",
                "review_summary": {
                    "schema_version": "agentblaster.suite-audit.v1",
                    "suite": "dashboard-fixture",
                    "total_cases": 2,
                    "finding_count": 1,
                    "finding_codes": ["duplicate_case_fingerprint"],
                    "provenance_counts": {"internal_regression": 2},
                    "risk_counts": {"low": 2},
                    "duplicate_fingerprint_count": 1,
                },
            },
            {
                "category": "metrics/coverage",
                "archive_path": "metrics/coverage/dashboard-fixture-metric-coverage.json",
                "schema": "agentblaster.metric-coverage.v1",
                "status": "review",
                "status_source": "review.status",
                "review_summary": {
                    "schema_version": "agentblaster.metric-coverage.v1",
                    "provider": "mock-local-dashboard",
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
            },
        ],
        "security": {
            "contains_raw_secrets": False,
            "contains_raw_provider_payloads": False,
            "contains_raw_traces": False,
            "contains_results_jsonl": False,
            "fixture": True,
        },
    }
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return output


def _write_fixture_selftest_report(output_dir: Path) -> Path:
    return _write_json(
        output_dir / "test-reports" / "selftest" / "selftest-report.json",
        {
            "schema_version": "agentblaster.selftest-report.v1",
            "run_id": "selftest_dashboard_fixture",
            "tier": "gui",
            "marker_expression": "gui",
            "command": "not copied into dashboard review summaries",
            "env": {"AGENTBLASTER_INTERNAL_VALUE": "not copied into dashboard review summaries"},
            "browser": "chromium",
            "headed": False,
            "duration_ms": 1000.0,
            "exit_code": 0,
            "ok": True,
            "junit_xml": "gui.junit.xml",
        },
    )


def _write_report_artifacts(run_dir: Path, *, run_id: str, ok: bool) -> list[Path]:
    metrics_dir = run_dir / "metrics"
    metrics_dir.mkdir(exist_ok=True)
    status = "pass" if ok else "fail"
    paths = [
        _write_text(
            run_dir / "report.html",
            (
                "<!doctype html><html><body><h1>AgentBlaster fixture report</h1>"
                f"<p>run: {run_id}</p><p>status: {status}</p><p>redacted: true</p></body></html>\n"
            ),
        ),
        _write_text(
            run_dir / "report.md",
            f"# AgentBlaster fixture report\n\n- run: `{run_id}`\n- status: `{status}`\n- redacted: true\n",
        ),
        _write_json(run_dir / "publication.json", {"run_id": run_id, "status": status, "redacted": True, "fixture": True}),
        _write_text(run_dir / "report.pdf", "%PDF-1.4\n% AgentBlaster dashboard fixture\n"),
        _write_text(
            run_dir / "report-card.svg",
            (
                '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="320">'
                f'<text x="32" y="80">AgentBlaster {status} fixture</text>'
                f'<text x="32" y="130">{run_id}</text></svg>\n'
            ),
        ),
        _write_bytes(run_dir / "report-card.png", b"\x89PNG\r\n\x1a\nagentblaster-fixture\n"),
        _write_json(
            metrics_dir / "prometheus-summary.json",
            {"format": "agentblaster-prometheus-summary-v1", "fixture": True, "redacted": True, "run_id": run_id},
        ),
    ]
    return paths


def _integrity_payload(run_dir: Path, written: list[Path]) -> dict[str, Any]:
    return {
        "schema_version": "agentblaster.fixture-integrity.v1",
        "artifact_sha256": {
            path.relative_to(run_dir).as_posix(): _sha256_file(path)
            for path in sorted(written)
            if path.exists()
        },
    }


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    return path


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _write_bytes(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
