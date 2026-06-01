from __future__ import annotations

import json

from agentblaster.implementation_status import (
    build_implementation_status,
    format_implementation_status,
    write_implementation_status,
)


def test_implementation_status_reports_static_project_inventory() -> None:
    report = build_implementation_status(project_root=None)
    rendered = format_implementation_status(report)

    assert report["schema_version"] == "agentblaster.implementation-status.v1"
    assert report["validation"]["tests_run_by_this_command"] is False
    assert report["suite_inventory"]["built_in_suite_count"] >= 1
    assert {"smoke", "agentic-tool-loop", "agent-fanout", "cancellation"} <= set(
        report["suite_inventory"]["built_in_suites"]
    )
    assert report["suite_inventory"]["harness_engineering_suite_present"] is True
    assert report["suite_inventory"]["tool_parser_repair_suite_present"] is True
    assert {
        "harness-contract-streaming-sentinel",
        "harness-metamorphic-equivalent-wrapper",
        "harness-cache-replay-static-prefix",
        "harness-judge-rubric-json",
    } <= set(report["suite_inventory"]["harness_engineering_cases"])
    assert {
        "parser-required-api-envelope",
        "parser-react-xml-boundary",
    } <= set(report["suite_inventory"]["tool_parser_repair_cases"])
    assert report["requirements_inventory"]["target_engines"]["count"] >= 8
    assert report["requirements_inventory"]["target_engines"]["representative_agent_profiles"] == [
        "opencode",
        "openclaw",
        "hermes",
        "pi",
    ]
    assert "mcp-fixtures" in report["requirements_inventory"]["target_engines"]["standard_workflow_surfaces"]
    assert "native_metrics_policy" in report["requirements_inventory"]["target_engines"]["standardization_fields"]
    assert "large repeated system prompts" in report["requirements_inventory"]["target_engines"]["standard_prefill_challenges"]
    assert "agent fan-out bursts" in report["requirements_inventory"]["target_engines"]["standard_concurrency_challenges"]
    assert {"openai", "openai-responses", "anthropic", "native"} <= set(
        report["requirements_inventory"]["provider_contracts"]["contracts"]
    )
    assert report["requirements_inventory"]["provider_contracts"]["provider_audit_schema"] == "agentblaster.provider-audit.v1"
    assert report["requirements_inventory"]["provider_contracts"]["provider_audit_redaction_safe"] is True
    assert report["requirements_inventory"]["model_targets"]["initial_targets_present"] is True
    assert {"qwen3.6-27b-dense", "gemma-4-31b-dense"} <= set(
        report["requirements_inventory"]["model_targets"]["initial_targets"]
    )
    assert {"opencode", "openclaw", "hermes", "pi"} <= {
        profile["id"] for profile in report["requirements_inventory"]["agentic_workflows"]["profiles"]
    }
    assert {"prefill", "concurrency", "contract-fuzz", "tool-parser-repair", "metamorphic", "cache-replay", "skills", "emerging-workflows", "judge-rubric"} <= {
        profile["name"] for profile in report["requirements_inventory"]["harness_engineering"]["profiles"]
    }
    assert report["requirements_inventory"]["harness_engineering"]["built_in_suite_present"] is True
    assert report["requirements_inventory"]["harness_engineering"]["tool_parser_repair_suite_present"] is True
    assert report["requirements_inventory"]["harness_engineering"]["tool_parser_repair_case_count"] == 2
    assert {
        "harness-contract-streaming-sentinel",
        "harness-metamorphic-equivalent-wrapper",
        "harness-cache-replay-static-prefix",
        "harness-judge-rubric-json",
    } <= set(report["requirements_inventory"]["harness_engineering"]["built_in_cases"])
    assert {
        "parser-required-api-envelope",
        "parser-react-xml-boundary",
    } <= set(report["requirements_inventory"]["harness_engineering"]["tool_parser_repair_cases"])
    assert "tool_parser_repair_required" in report["requirements_inventory"]["harness_engineering"][
        "tool_parser_repair_metrics"
    ]
    stats = report["requirements_inventory"]["stats_comparability"]
    assert stats["stats_comparability_schema"] == "agentblaster.stats-comparability.v1"
    assert {
        "afm-mlx-openai-compatible",
        "mlx-lm-openai-compatible",
        "rapid-mlx-openai-compatible",
        "omlx-openai-compatible",
    } <= set(stats["profiles"])
    assert {
        "afm-mlx-openai-compatible",
        "mlx-lm-openai-compatible",
        "rapid-mlx-openai-compatible",
        "omlx-openai-compatible",
    } <= set(stats["mlx_openai_wrapper_metric_profiles"])
    assert {"prompt_eval_ms", "tokens_per_second_decode", "cached_input_tokens"} <= set(stats["field_semantics"])
    assert stats["publication_requires_labels_for_non_native_stats"] is True
    assert stats["redaction_safe"]["contains_raw_provider_payloads"] is False
    capability_preflight = report["requirements_inventory"]["capability_preflight"]
    assert {"judge_rubric", "prompt_caching", "structured_output"} <= {
        item["key"] for item in capability_preflight["standard_capabilities"]
    }
    assert capability_preflight["campaign_preflight_exports_requirements"] is True
    assert capability_preflight["dry_run_exports_case_surfaces"] is True
    assert capability_preflight["generated_harness_requirements"]["judge_rubric"] == [
        "structured_output",
        "judge_rubric",
    ]
    assert capability_preflight["generated_harness_requirements"]["tool-parser-repair"] == [
        "tool_calling",
        "tool_parser_repair",
    ]
    assert "allowed_secret_ref_prefixes" in report["requirements_inventory"]["enterprise_controls"][
        "secret_reference_policy_fields"
    ]
    assert set(report["requirements_inventory"]["enterprise_controls"]["secret_backends"]) == {
        "env",
        "keyring",
        "dotenv",
    }
    assert report["requirements_inventory"]["enterprise_controls"]["keyring_optional"] is True
    guards = report["requirements_inventory"]["enterprise_controls"]["credential_storage_guards"]
    assert "raw API-key entry is limited to optional keyring-backed auth setup or explicit plaintext dotenv fallback" in guards
    assert "plaintext dotenv fallback requires an explicit high-friction flag and is policy-controllable" in guards
    lifecycle_cleanup = report["requirements_inventory"]["enterprise_controls"]["lifecycle_cleanup"]
    assert {"raw", "reports", "exports", "caches", "temp", "bundles", "all_artifacts"} <= set(
        lifecycle_cleanup["manual_selectors"]
    )
    assert lifecycle_cleanup["manual_dry_run_default"] is True
    assert {"manual_cleanup_planned", "manual_cleanup_executed"} <= set(lifecycle_cleanup["manual_audit_events"])
    assert lifecycle_cleanup["manual_output_schema"] == "agentblaster.cleanup-plan.v1"
    assert lifecycle_cleanup["cleanup_reports_direct_publication_safe"] is False
    assert lifecycle_cleanup["cleanup_evidence_index_summary_publication_safe"] is True
    assert lifecycle_cleanup["require_audit_log_option"] is True
    assert lifecycle_cleanup["policy_enforced_audit_log_field"] == "require_cleanup_audit_log"
    assert "require_cleanup_audit_log" in report["requirements_inventory"]["enterprise_controls"][
        "lifecycle_policy_fields"
    ]
    assert lifecycle_cleanup["dry_run_retention_planning"] is True
    assert lifecycle_cleanup["retention_output_schema"] == "agentblaster.retention-cleanup.v1"
    assert {"retention_cleanup_planned", "retention_cleanup_executed"} <= set(
        lifecycle_cleanup["retention_audit_events"]
    )
    assert "cache" in lifecycle_cleanup["cache_artifact_dirs"]
    assert "tmp" in lifecycle_cleanup["temp_artifact_dirs"]
    assert "publication-bundles" in lifecycle_cleanup["bundle_artifact_dirs"]
    assert "*.agentblaster-publication.zip" in lifecycle_cleanup["bundle_artifact_patterns"]
    assert report["requirements_inventory"]["selftest_harness"]["chrome_codex_gate_present"] is True
    assert report["requirements_inventory"]["selftest_harness"]["report_schema"] == "agentblaster.selftest-report.v1"
    assert (
        report["requirements_inventory"]["selftest_harness"]["validation_manifest_schema"]
        == "agentblaster.sdlc-validation-manifest.v1"
    )
    assert "claim readiness gate" in report["requirements_inventory"]["selftest_harness"]["release_evidence_consumers"]
    assert "final archival release bundle" in report["requirements_inventory"]["selftest_harness"]["release_evidence_consumers"]
    assert "release qualification bundle" in report["requirements_inventory"]["selftest_harness"][
        "sdlc_validation_manifest_consumers"
    ]
    assert "claim readiness via release bundle" in report["requirements_inventory"]["selftest_harness"][
        "sdlc_validation_manifest_consumers"
    ]
    assert "env" in report["requirements_inventory"]["selftest_harness"]["excluded_from_release_summaries"]
    publication = report["requirements_inventory"]["publication_governance"]
    assert publication["manifest_schema"] == "agentblaster.publication-bundle.v1"
    assert publication["manifest_name"] == "publication-bundle-manifest.json"
    assert publication["media_kit_schema"] == "agentblaster.media-kit.v1"
    assert publication["matrix_manifest_schema"] == "agentblaster.matrix-publication-bundle.v1"
    assert publication["matrix_manifest_name"] == "matrix-publication-bundle-manifest.json"
    assert publication["matrix_accepted_bundle_suffix"] == ".agentblaster-matrix-publication.zip"
    assert "media_kit" in publication["required_manifest_blocks"]
    assert {"matrix", "media_kit", "security"} <= set(publication["matrix_required_manifest_blocks"])
    assert {"missing_recommended_assets", "asset_roles"} <= set(publication["media_kit_summary_fields"])
    assert {"ready", "review-required", "blocked"} <= set(publication["readiness_statuses"])
    assert {
        "contains_raw_secrets",
        "contains_raw_provider_payloads",
        "contains_results_jsonl",
    } <= set(publication["security_flags"])
    assert "contains_per_run_raw_traces" in publication["matrix_security_flags"]
    assert "missing recommended media-kit assets" in publication["publication_review_conditions"]
    assert "missing recommended media-kit assets" in publication["matrix_review_conditions"]
    assert "per-run raw traces present" in publication["matrix_release_blocking_conditions"]
    assert {
        "matrix publication-bundle packaging",
        "release qualification bundle",
        "claim readiness gate",
        "dashboard review artifacts",
        "evidence index",
        "artifact schema registry",
        "selftest report summaries",
        "benchmark readiness summaries",
        "publication brief summaries",
        "SDLC validation manifest summaries",
        "final archival release bundle",
    } <= set(publication["redaction_safe_summary_consumers"])
    assert publication["claim_artifact_schema"] == "agentblaster.publication-brief.v1"
    assert {"claim readiness report", "publication brief", "SDLC validation manifest", "matrix publication bundle"} <= set(
        publication["final_archival_bundle_inputs"]
    )
    assert any(area["id"] == "security-governance" for area in report["areas"])
    assert any(area["id"] == "release-automation" for area in report["areas"])
    security = next(area for area in report["areas"] if area["id"] == "security-governance")
    assert "src/agentblaster/cleanup.py" in security["required_files"]
    assert "docs/retention.md" in security["required_files"]
    reporting = next(area for area in report["areas"] if area["id"] == "reporting-publication")
    assert "docs/failure-taxonomy.md" in reporting["required_files"]
    assert "src/agentblaster/publication_brief.py" in reporting["required_files"]
    assert "src/agentblaster/metric_coverage.py" in reporting["required_files"]
    assert "src/agentblaster/telemetry.py" in reporting["required_files"]
    release = next(area for area in report["areas"] if area["id"] == "release-automation")
    assert "src/agentblaster/campaign.py" in release["required_files"]
    assert "src/agentblaster/release_qualification.py" in release["required_files"]
    assert "AgentBlaster implementation status" in rendered
    assert "requirements_inventory:" in rendered
    assert "harness_engineering_cases:" in rendered
    assert "tool_parser_repair_cases:" in rendered
    assert "stats_profiles:" in rendered
    assert "stats_metric_providers:" in rendered
    assert "standard_capabilities:" in rendered
    assert "selftest_report_schema: agentblaster.selftest-report.v1" in rendered
    assert "publication_governance_surfaces:" in rendered
    assert "lifecycle_cleanup_selectors:" in rendered
    assert "next_step:" in rendered


def test_implementation_status_marks_missing_files_on_partial_project(tmp_path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "prd.md").write_text("# PRD\n", encoding="utf-8")

    report = build_implementation_status(project_root=tmp_path)

    assert report["status"] == "implementation-incomplete"
    assert report["missing_areas"] > 0
    cli_area = next(area for area in report["areas"] if area["id"] == "cli-core")
    assert cli_area["status"] == "missing"
    prd_area = next(area for area in report["areas"] if area["id"] == "prd-and-scope")
    assert prd_area["status"] == "implemented"


def test_write_implementation_status_outputs_json(tmp_path) -> None:
    output = tmp_path / "reports" / "implementation-status.json"

    path = write_implementation_status(output, project_root=None)

    assert path == output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "agentblaster.implementation-status.v1"
    assert payload["requirements_inventory"]["selftest_harness"]["sdlc_gate_count"] >= 1
    assert payload["security_notes"]


def test_implementation_status_exports_model_comparison_contract(tmp_path) -> None:
    report = build_implementation_status(project_root=tmp_path)
    model_targets = report["requirements_inventory"]["model_targets"]

    assert model_targets["initial_target_comparison_groups"]["qwen3.6-27b-dense"] == "qwen3.6-27b-dense"
    assert model_targets["initial_target_comparison_groups"]["gemma-4-31b-dense"] == "gemma-4-31b-dense"
    assert "quantization" in model_targets["initial_target_required_release_metadata"]["qwen3.6-27b-dense"]
    assert "revision" in model_targets["initial_target_required_release_metadata"]["gemma-4-31b-dense"]
    assert any(
        "separate primary charts" in item
        for item in model_targets["initial_target_publication_guidance"]["qwen3.6-27b-dense"]
    )
