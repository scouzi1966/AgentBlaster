from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from agentblaster import __version__
from agentblaster.agent_profiles import list_agent_profiles
from agentblaster.capabilities import CAPABILITY_DESCRIPTIONS
from agentblaster.cleanup import (
    BUNDLE_ARTIFACT_DIRS,
    BUNDLE_ARTIFACT_PATTERNS,
    CACHE_ARTIFACT_DIRS,
    CLEANUP_PLAN_SCHEMA_VERSION,
    RETENTION_CLEANUP_SCHEMA_VERSION,
    TEMP_ARTIFACT_DIRS,
)
from agentblaster.engine_targets import (
    ENGINE_TARGETS,
    RECOMMENDED_MODEL_TARGETS,
    REPRESENTATIVE_AGENT_PROFILES,
    STANDARD_CONCURRENCY_CHALLENGES,
    STANDARD_PREFILL_CHALLENGES,
    STANDARD_WORKFLOW_SURFACES,
)
from agentblaster.harness import list_harness_profiles
from agentblaster.metric_coverage import metric_coverage_catalog
from agentblaster.model_catalog import MODEL_TARGETS
from agentblaster.policy import SecurityPolicy
from agentblaster.presets import CLOUD_PROVIDER_PRESETS, LOCAL_ENGINE_PRESETS, PROVIDER_PRESETS
from agentblaster.publication_brief import PUBLICATION_BRIEF_SCHEMA_VERSION
from agentblaster.provider_audit import PROVIDER_AUDIT_SCHEMA_VERSION
from agentblaster.quality import SDLC_GATES, SDLC_VALIDATION_MANIFEST_SCHEMA_VERSION, SELFTEST_REPORT_SCHEMA_VERSION, TEST_TIERS
from agentblaster.secrets import KEYRING_SERVICE_NAME
from agentblaster.suites import BUILTIN_SUITES
from agentblaster.telemetry import telemetry_mapping_catalog


IMPLEMENTATION_STATUS_SCHEMA_VERSION = "agentblaster.implementation-status.v1"


IMPLEMENTATION_AREAS: tuple[dict[str, Any], ...] = (
    {
        "id": "prd-and-scope",
        "title": "PRD and product scope",
        "required_files": ["docs/prd.md"],
        "summary": "Product requirements, MVP scope, architecture notes, and long-term benchmark direction.",
    },
    {
        "id": "cli-core",
        "title": "CLI benchmark core",
        "required_files": [
            "src/agentblaster/cli.py",
            "src/agentblaster/runner.py",
            "src/agentblaster/suites.py",
            "src/agentblaster/planning.py",
        ],
        "summary": "Suite execution, dry-run planning, run artifacts, summaries, and command-line control plane.",
    },
    {
        "id": "provider-contracts",
        "title": "Provider contracts and adapters",
        "required_files": [
            "src/agentblaster/adapters.py",
            "src/agentblaster/contract_check.py",
            "src/agentblaster/presets.py",
            "docs/providers.md",
        ],
        "summary": "OpenAI Chat, OpenAI Responses, Anthropic Messages, Ollama native, LM Studio native, presets, and contract checks.",
    },
    {
        "id": "agentic-workloads",
        "title": "Agentic workload coverage",
        "required_files": [
            "src/agentblaster/suites.py",
            "src/agentblaster/agent_profiles.py",
            "src/agentblaster/harness.py",
            "src/agentblaster/engine_onboarding.py",
            "src/agentblaster/engine_advisory.py",
            "src/agentblaster/campaign_preflight.py",
            "docs/harness.md",
            "docs/agent-fanout.md",
            "examples/matrices/qwen-gemma-stress.yaml",
            "examples/README.md",
            "campaigns/qwen-gemma-local/README.md",
            "campaigns/qwen-gemma-local/campaign-handoff.json",
        ],
        "summary": "Tool calling, structured output, trace replay, bounded tool loops, fan-out, prefill/cache, cancellation, LCP, MCP fixtures, skill prefixes, and generated harness profiles.",
    },
    {
        "id": "dashboard",
        "title": "Dashboard and GUI surface",
        "required_files": [
            "src/agentblaster/dashboard.py",
            "docs/dashboard.md",
            "tests/gui",
        ],
        "summary": "No-JavaScript dashboard, provider setup, run-plan preview, launch, reports, catalogs, lifecycle events, and GUI test surfaces.",
    },
    {
        "id": "security-governance",
        "title": "Security and enterprise governance",
        "required_files": [
            "src/agentblaster/policy.py",
            "src/agentblaster/secrets.py",
            "src/agentblaster/redaction.py",
            "src/agentblaster/redaction_scan.py",
            "src/agentblaster/audit.py",
            "src/agentblaster/cleanup.py",
            "docs/security-policy.md",
            "docs/retention.md",
            "agentblaster.policy.example.yaml",
        ],
        "summary": "Policy gates, remote/offline controls, secret references, redaction, audit logs, retention, integrity, signatures, and artifact scans.",
    },
    {
        "id": "reporting-publication",
        "title": "Reporting and publication artifacts",
        "required_files": [
            "src/agentblaster/reports.py",
            "src/agentblaster/exports.py",
            "src/agentblaster/bundle.py",
            "src/agentblaster/publication_brief.py",
            "src/agentblaster/schema_registry.py",
            "src/agentblaster/matrix_pressure.py",
            "src/agentblaster/metric_coverage.py",
            "src/agentblaster/telemetry.py",
            "docs/reporting.md",
            "docs/failure-taxonomy.md",
            "docs/reproducibility.md",
            "docs/artifact-schemas.md",
            "docs/evidence-bundles.md",
        ],
        "summary": "HTML/Markdown/JSON/publication/SVG reports, exports, bundles, matrix reports, scorecards, stats-comparability guidance, metric coverage, and reproducibility artifacts.",
    },
    {
        "id": "testing-harness",
        "title": "AgentBlaster app testing harness",
        "required_files": [
            "src/agentblaster/quality.py",
            "tests",
            "docs/testing.md",
        ],
        "summary": "SDLC test tiers, selftest planning/execution, GUI plans, Chrome/Codex checklist, fixtures, and static workflow expectations.",
    },
    {
        "id": "release-automation",
        "title": "Packaging and release automation",
        "required_files": [
            "pyproject.toml",
            "src/agentblaster/campaign.py",
            "src/agentblaster/release.py",
            "src/agentblaster/release_qualification.py",
            "src/agentblaster/claim_readiness.py",
            ".github/workflows/ci.yml",
            ".github/workflows/publish.yml",
            "docs/release-qualification.md",
        ],
        "summary": "Package metadata, static readiness, release provenance, release qualification bundles, CI, package build workflow, and redaction scans.",
    },
)


def build_implementation_status(*, project_root: Path | None = None) -> dict[str, Any]:
    root = (project_root or Path.cwd()).resolve()
    areas = [_area_status(root, area) for area in IMPLEMENTATION_AREAS]
    implemented = sum(1 for area in areas if area["status"] == "implemented")
    partial = sum(1 for area in areas if area["status"] == "partial")
    missing = sum(1 for area in areas if area["status"] == "missing")
    return {
        "schema_version": IMPLEMENTATION_STATUS_SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "agentblaster_version": __version__,
        "project_root": str(root),
        "status": "implementation-ready-for-validation" if missing == 0 else "implementation-incomplete",
        "implemented_areas": implemented,
        "partial_areas": partial,
        "missing_areas": missing,
        "areas": areas,
        "suite_inventory": {
            "built_in_suite_count": len(BUILTIN_SUITES),
            "built_in_suites": sorted(BUILTIN_SUITES),
            "harness_engineering_suite_present": "harness-engineering" in BUILTIN_SUITES,
            "harness_engineering_cases": _suite_case_ids("harness-engineering"),
            "tool_parser_repair_suite_present": "tool-parser-repair" in BUILTIN_SUITES,
            "tool_parser_repair_cases": _suite_case_ids("tool-parser-repair"),
        },
        "requirements_inventory": _requirements_inventory(),
        "validation": {
            "tests_run_by_this_command": False,
            "required_next_step": "Run explicit validation/selftest before claiming completion or release readiness.",
            "suggested_commands": [
                "agentblaster doctor --output-json reports/environment-readiness.json --fail-on-required-gaps",
                "agentblaster selftest --tier normal --report-dir test-reports/selftest",
                "agentblaster release packaging-readiness --output-json reports/packaging-readiness.json --fail-on-gaps",
            ],
        },
        "security_notes": [
            "Implementation status checks file presence and static inventories only.",
            "It does not contact providers, resolve secrets, inspect keyring values, read dotenv secret files, read run artifacts, or execute tests.",
            "Requirement inventory is derived from static catalogs, presets, policy fields, and SDLC gate definitions.",
        ],
    }


def write_implementation_status(output: Path, *, project_root: Path | None = None) -> Path:
    payload = build_implementation_status(project_root=project_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def format_implementation_status(report: dict[str, Any]) -> str:
    lines = [
        "AgentBlaster implementation status",
        f"status: {report['status']}",
        f"implemented_areas: {report['implemented_areas']}",
        f"partial_areas: {report['partial_areas']}",
        f"missing_areas: {report['missing_areas']}",
        f"built_in_suites: {report['suite_inventory']['built_in_suite_count']}",
        "areas:",
    ]
    for area in report["areas"]:
        lines.append(f"- {area['status'].upper()} {area['id']}: {area['title']}")
    lines.append(f"next_step: {report['validation']['required_next_step']}")
    requirements = report.get("requirements_inventory", {})
    if requirements:
        lines.extend(
            [
                "requirements_inventory:",
                f"- target_engines: {requirements['target_engines']['count']}",
                f"- provider_presets: {requirements['provider_contracts']['preset_count']}",
                f"- model_targets: {requirements['model_targets']['catalog_count']}",
                f"- agent_profiles: {requirements['agentic_workflows']['profile_count']}",
                f"- harness_profiles: {requirements['harness_engineering']['profile_count']}",
                f"- harness_engineering_cases: {requirements['harness_engineering']['built_in_case_count']}",
                f"- tool_parser_repair_cases: {requirements['harness_engineering']['tool_parser_repair_case_count']}",
                f"- stats_profiles: {requirements['stats_comparability']['profile_count']}",
                f"- stats_metric_providers: {requirements['stats_comparability']['metric_provider_count']}",
                f"- standard_capabilities: {requirements['capability_preflight']['standard_capability_count']}",
                f"- sdlc_gates: {requirements['selftest_harness']['sdlc_gate_count']}",
                f"- selftest_report_schema: {requirements['selftest_harness']['report_schema']}",
                f"- publication_governance_surfaces: {len(requirements['publication_governance']['redaction_safe_summary_consumers'])}",
                f"- lifecycle_cleanup_selectors: {len(requirements['enterprise_controls']['lifecycle_cleanup']['manual_selectors'])}",
            ]
        )
    return "\n".join(lines) + "\n"


def _area_status(root: Path, area: dict[str, Any]) -> dict[str, Any]:
    required_files = [str(path) for path in area["required_files"]]
    evidence = []
    missing = []
    for relative_path in required_files:
        path = root / relative_path
        if path.exists():
            evidence.append(relative_path)
        else:
            missing.append(relative_path)
    if not missing:
        status = "implemented"
    elif evidence:
        status = "partial"
    else:
        status = "missing"
    return {
        "id": area["id"],
        "title": area["title"],
        "summary": area["summary"],
        "status": status,
        "required_files": required_files,
        "evidence": evidence,
        "missing": missing,
    }


def _requirements_inventory() -> dict[str, Any]:
    agent_profiles = list_agent_profiles()
    harness_profiles = list_harness_profiles()
    policy_fields = SecurityPolicy.model_fields
    harness_suite_cases = _suite_case_ids("harness-engineering")
    return {
        "target_engines": {
            "count": len(ENGINE_TARGETS),
            "ids": [target.id for target in ENGINE_TARGETS],
            "provider_presets": sorted({preset for target in ENGINE_TARGETS for preset in target.provider_presets}),
            "contracts": sorted({contract for target in ENGINE_TARGETS for contract in target.contracts}),
            "representative_agent_profiles": list(REPRESENTATIVE_AGENT_PROFILES),
            "standard_workflow_surfaces": list(STANDARD_WORKFLOW_SURFACES),
            "standardization_fields": [
                "primary_scoring_contract",
                "contract_priority",
                "workflow_surfaces",
                "representative_agent_profiles",
                "prefill_challenges",
                "concurrency_challenges",
                "stats_claim_policy",
                "native_telemetry_profiles",
                "native_metrics_policy",
            ],
            "standard_prefill_challenges": list(STANDARD_PREFILL_CHALLENGES),
            "standard_concurrency_challenges": list(STANDARD_CONCURRENCY_CHALLENGES),
        },
        "provider_contracts": {
            "preset_count": len(PROVIDER_PRESETS),
            "local_preset_count": len(LOCAL_ENGINE_PRESETS),
            "remote_preset_count": len(CLOUD_PROVIDER_PRESETS),
            "contracts": sorted({preset.contract.value for preset in PROVIDER_PRESETS.values()}),
            "local_presets": sorted(LOCAL_ENGINE_PRESETS),
            "remote_presets": sorted(CLOUD_PROVIDER_PRESETS),
            "provider_audit_schema": PROVIDER_AUDIT_SCHEMA_VERSION,
            "provider_audit_redaction_safe": True,
        },
        "model_targets": {
            "catalog_count": len(MODEL_TARGETS),
            "catalog_targets": sorted(MODEL_TARGETS),
            "initial_targets": list(RECOMMENDED_MODEL_TARGETS),
            "initial_targets_present": all(target in MODEL_TARGETS for target in RECOMMENDED_MODEL_TARGETS),
            "initial_target_defaults": {
                target: MODEL_TARGETS[target].default_model
                for target in RECOMMENDED_MODEL_TARGETS
                if target in MODEL_TARGETS
            },
            "initial_target_comparison_groups": {
                target: MODEL_TARGETS[target].comparison_group
                for target in RECOMMENDED_MODEL_TARGETS
                if target in MODEL_TARGETS
            },
            "initial_target_required_release_metadata": {
                target: list(MODEL_TARGETS[target].required_release_metadata)
                for target in RECOMMENDED_MODEL_TARGETS
                if target in MODEL_TARGETS
            },
            "initial_target_publication_guidance": {
                target: list(MODEL_TARGETS[target].publication_guidance)
                for target in RECOMMENDED_MODEL_TARGETS
                if target in MODEL_TARGETS
            },
            "representative_agent_profiles": list(REPRESENTATIVE_AGENT_PROFILES),
            "standard_workflow_surfaces": list(STANDARD_WORKFLOW_SURFACES),
            "standardization_fields": [
                "primary_scoring_contract",
                "contract_priority",
                "workflow_surfaces",
                "representative_agent_profiles",
                "prefill_challenges",
                "concurrency_challenges",
                "stats_claim_policy",
                "native_telemetry_profiles",
                "native_metrics_policy",
                "security_boundary",
            ],
            "standard_prefill_challenges": list(STANDARD_PREFILL_CHALLENGES),
            "standard_concurrency_challenges": list(STANDARD_CONCURRENCY_CHALLENGES),
        },
        "agentic_workflows": {
            "profile_count": len(agent_profiles),
            "profiles": [
                {
                    "id": profile.id,
                    "display_name": profile.display_name,
                    "representative_features": list(profile.representative_features),
                }
                for profile in agent_profiles
            ],
        },
        "harness_engineering": {
            "profile_count": len(harness_profiles),
            "profiles": [{"name": profile.name, "purpose": profile.purpose} for profile in harness_profiles],
            "built_in_suite_present": "harness-engineering" in BUILTIN_SUITES,
            "built_in_case_count": len(harness_suite_cases),
            "built_in_cases": harness_suite_cases,
            "tool_parser_repair_suite_present": "tool-parser-repair" in BUILTIN_SUITES,
            "tool_parser_repair_case_count": len(_suite_case_ids("tool-parser-repair")),
            "tool_parser_repair_cases": _suite_case_ids("tool-parser-repair"),
            "tool_parser_repair_metrics": [
                "tool_calls_valid",
                "invalid_tool_call_count",
                "tool_parser_repair_required",
            ],
            "intent": "Exercise emerging harness-engineering concerns such as streaming sentinels, metamorphic wrappers, cache replay, skill-prefix routing, mixed MCP/LCP/skills/tool-loop stacks, and judge-rubric JSON across local and remote engines.",
        },
        "stats_comparability": _stats_comparability_inventory(),
        "capability_preflight": {
            "standard_capability_count": len(CAPABILITY_DESCRIPTIONS),
            "standard_capabilities": [
                {"key": key, "description": CAPABILITY_DESCRIPTIONS[key]} for key in sorted(CAPABILITY_DESCRIPTIONS)
            ],
            "campaign_preflight_exports_requirements": True,
            "dry_run_exports_case_surfaces": True,
            "generated_harness_requirements": {
                "judge_rubric": ["structured_output", "judge_rubric"],
                "cache_replay": ["prompt_caching"],
                "orchestration": ["tool_calling", "tool_loop"],
                "tool-parser-repair": ["tool_calling", "tool_parser_repair"],
                "emerging-workflows": ["tool_calling", "tool_loop", "prompt_caching", "mcp", "lcp", "skills"],
                "cancellation": ["streaming", "cancellation"],
            },
            "contract_inference_notes": [
                "Anthropic Messages providers require explicit structured_output declaration for OpenAI-style response_format or judge-rubric cases.",
                "Prompt caching is inferred for remote Anthropic providers and unknown for local Anthropic-compatible providers until declared.",
                "Unknown local capabilities are allowed by default and become blockers only under strict_unknown capability gates.",
            ],
        },
        "enterprise_controls": {
            "secret_backends": [
                "env",
                "keyring",
                "dotenv",
            ],
            "keyring_optional": True,
            "keyring_service_name": KEYRING_SERVICE_NAME,
            "credential_storage_guards": [
                "provider configs store api_key_ref metadata only",
                "environment secrets are read-only inside AgentBlaster",
                "raw API-key entry is limited to optional keyring-backed auth setup or explicit plaintext dotenv fallback",
                "plaintext dotenv fallback requires an explicit high-friction flag and is policy-controllable",
                "provider audits, readiness dossiers, and dashboard setup-status expose static secret_backend_posture without reading secret values",
                "secret deletion is explicit and never applies to environment variables",
            ],
            "provider_endpoint_policy_fields": _present_policy_fields(
                policy_fields,
                [
                    "allowed_providers",
                    "allowed_base_url_hosts",
                    "allowed_metrics_url_hosts",
                    "allow_remote_providers",
                    "allow_non_loopback_http_provider_urls",
                    "allow_non_loopback_http_metrics_urls",
                    "allow_insecure_tls",
                ],
            ),
            "secret_reference_policy_fields": _present_policy_fields(
                policy_fields,
                [
                    "allowed_secret_ref_kinds",
                    "allowed_secret_ref_names",
                    "allowed_secret_ref_prefixes",
                    "require_api_key_for_remote_providers",
                ],
            ),
            "cost_and_concurrency_policy_fields": _present_policy_fields(
                policy_fields,
                [
                    "require_cost_model_for_remote_providers",
                    "require_rate_limits_for_remote_providers",
                    "max_concurrency",
                    "max_matrix_runs",
                    "max_matrix_total_cases",
                    "max_estimated_case_cost_usd",
                    "max_estimated_run_cost_usd",
                    "max_estimated_matrix_cost_usd",
                ],
            ),
            "suite_surface_policy_fields": _present_policy_fields(
                policy_fields,
                [
                    "allow_tool_schemas",
                    "allowed_tool_names",
                    "allow_simulated_tools",
                    "allowed_simulated_tools",
                    "allow_mcp_profiles",
                    "allowed_mcp_profiles",
                    "allow_lcp_profiles",
                    "allowed_lcp_profiles",
                    "allow_skills",
                    "allowed_skills",
                    "allowed_case_provenance",
                    "allowed_case_risk_levels",
                ],
            ),
            "dashboard_policy_fields": _present_policy_fields(
                policy_fields,
                [
                    "allowed_dashboard_hosts",
                    "allowed_dashboard_ports",
                    "allow_dashboard_non_loopback",
                    "require_dashboard_auth",
                ],
            ),
            "lifecycle_policy_fields": _present_policy_fields(
                policy_fields,
                [
                    "require_cleanup_audit_log",
                ],
            ),
            "lifecycle_cleanup": {
                "manual_selectors": [
                    "raw",
                    "reports",
                    "exports",
                    "caches",
                    "temp",
                    "bundles",
                    "all_artifacts",
                ],
                "manual_dry_run_default": True,
                "manual_audit_events": [
                    "manual_cleanup_planned",
                    "manual_cleanup_executed",
                ],
                "manual_output_schema": CLEANUP_PLAN_SCHEMA_VERSION,
                "cleanup_reports_direct_publication_safe": False,
                "cleanup_evidence_index_summary_publication_safe": True,
                "require_audit_log_option": True,
                "policy_enforced_audit_log_field": "require_cleanup_audit_log",
                "dry_run_retention_planning": True,
                "retention_output_schema": RETENTION_CLEANUP_SCHEMA_VERSION,
                "retention_audit_events": [
                    "retention_cleanup_planned",
                    "retention_cleanup_executed",
                ],
                "expired_cleanup_actions": [
                    "raw",
                    "run",
                ],
                "cache_artifact_dirs": list(CACHE_ARTIFACT_DIRS),
                "temp_artifact_dirs": list(TEMP_ARTIFACT_DIRS),
                "bundle_artifact_dirs": list(BUNDLE_ARTIFACT_DIRS),
                "bundle_artifact_patterns": list(BUNDLE_ARTIFACT_PATTERNS),
                "manual_selector_scope": "known generated artifacts inside the selected run directory only",
            },
        },
        "selftest_harness": {
            "test_tier_count": len(TEST_TIERS),
            "test_tiers": [tier.name for tier in TEST_TIERS],
            "sdlc_gate_count": len(SDLC_GATES),
            "required_sdlc_gates": [gate.id for gate in SDLC_GATES if gate.required],
            "optional_sdlc_gates": [gate.id for gate in SDLC_GATES if not gate.required],
            "chrome_codex_gate_present": any(gate.id == "chrome-codex-review" for gate in SDLC_GATES),
            "report_schema": SELFTEST_REPORT_SCHEMA_VERSION,
            "validation_manifest_schema": SDLC_VALIDATION_MANIFEST_SCHEMA_VERSION,
            "release_evidence_consumers": [
                "release qualification bundle",
                "claim readiness gate",
                "dashboard review artifacts",
                "evidence index",
                "artifact schema registry",
                "campaign runbook static evidence",
                "final archival release bundle",
            ],
            "sdlc_validation_manifest_consumers": [
                "release qualification bundle",
                "claim readiness via release bundle",
                "dashboard review artifacts",
                "evidence index",
                "artifact schema registry",
                "operator handoff",
                "corporate review",
            ],
            "redaction_safe_summary_fields": [
                "run_id",
                "tier",
                "ok",
                "exit_code",
                "duration_ms",
                "browser",
                "headed",
                "marker_expression",
                "junit_xml_present",
            ],
            "excluded_from_release_summaries": [
                "command",
                "env",
                "raw test output",
            ],
        },
        "publication_governance": {
            "manifest_schema": "agentblaster.publication-bundle.v1",
            "manifest_name": "publication-bundle-manifest.json",
            "media_kit_schema": "agentblaster.media-kit.v1",
            "accepted_bundle_suffix": ".agentblaster-publication.zip",
            "matrix_manifest_schema": "agentblaster.matrix-publication-bundle.v1",
            "matrix_manifest_name": "matrix-publication-bundle-manifest.json",
            "matrix_accepted_bundle_suffix": ".agentblaster-matrix-publication.zip",
            "required_manifest_blocks": [
                "artifacts",
                "media_kit",
                "publication_readiness",
                "security",
            ],
            "matrix_required_manifest_blocks": [
                "artifacts",
                "matrix",
                "media_kit",
                "security",
            ],
            "media_kit_summary_fields": [
                "schema_version",
                "asset_count",
                "missing_recommended_assets",
                "available_recommended_sets",
                "asset_roles",
            ],
            "readiness_statuses": [
                "ready",
                "review-required",
                "blocked",
            ],
            "security_flags": [
                "contains_raw_secrets",
                "contains_raw_provider_payloads",
                "contains_results_jsonl",
            ],
            "matrix_security_flags": [
                "contains_raw_secrets",
                "contains_raw_provider_payloads",
                "contains_results_jsonl",
                "contains_per_run_raw_traces",
            ],
            "release_blocking_conditions": [
                "manifest missing or unreadable",
                "manifest schema mismatch",
                "publication readiness blocked",
                "raw secrets present",
                "raw provider payloads present",
                "results.jsonl present",
            ],
            "publication_review_conditions": [
                "publication readiness review-required",
                "missing recommended media-kit assets",
                "media-kit schema missing or mismatched",
            ],
            "matrix_release_blocking_conditions": [
                "matrix publication manifest missing or unreadable",
                "matrix publication manifest schema mismatch",
                "raw secrets present",
                "raw provider payloads present",
                "results.jsonl present",
                "per-run raw traces present",
            ],
            "matrix_review_conditions": [
                "missing recommended media-kit assets",
                "media-kit schema missing or mismatched",
            ],
            "redaction_safe_summary_consumers": [
                "publication-bundle packaging",
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
            ],
            "claim_artifact_schema": PUBLICATION_BRIEF_SCHEMA_VERSION,
            "final_archival_bundle_inputs": [
                "claim readiness report",
                "publication brief",
                "SDLC validation manifest",
                "release provenance",
                "evidence index",
                "matrix scorecard",
                "run publication bundle",
                "matrix publication bundle",
            ],
        },
    }


def _suite_case_ids(suite_name: str) -> list[str]:
    suite = BUILTIN_SUITES.get(suite_name)
    if suite is None:
        return []
    return [str(getattr(case, "id", case)) for case in getattr(suite, "cases", ())]


def _stats_comparability_inventory() -> dict[str, Any]:
    telemetry_catalog = telemetry_mapping_catalog()
    metric_catalog = metric_coverage_catalog()
    mappings = telemetry_catalog.get("mappings", [])
    stats_catalog = telemetry_catalog.get("stats_comparability", {})
    metric_providers = [
        provider_report.get("provider", {}).get("name")
        for provider_report in metric_catalog.get("providers", [])
        if provider_report.get("provider", {}).get("name")
    ]
    profiles = sorted({mapping.get("profile") for mapping in mappings if mapping.get("profile")})
    guidance_profiles = sorted(stats_catalog.get("profile_guidance", {}))
    return {
        "telemetry_catalog_schema": telemetry_catalog.get("schema_version"),
        "stats_comparability_schema": stats_catalog.get("schema_version"),
        "metric_coverage_catalog_schema": metric_catalog.get("schema_version"),
        "profile_count": len(profiles),
        "profiles": profiles,
        "guidance_profile_count": len(guidance_profiles),
        "guidance_profiles": guidance_profiles,
        "field_semantics": sorted(stats_catalog.get("field_semantics", {})),
        "publication_grade_qualities": list(stats_catalog.get("publication_grade_qualities", [])),
        "advisory_qualities": list(stats_catalog.get("advisory_qualities", [])),
        "metric_provider_count": len(metric_providers),
        "metric_providers": metric_providers,
        "mlx_openai_wrapper_metric_profiles": sorted(
            name
            for name in metric_providers
            if name
            in {
                "afm-mlx-openai-compatible",
                "mlx-lm-openai-compatible",
                "rapid-mlx-openai-compatible",
                "omlx-openai-compatible",
            }
        ),
        "publication_requires_labels_for_non_native_stats": True,
        "redaction_safe": stats_catalog.get("security", {}),
    }


def _present_policy_fields(policy_fields: dict[str, Any], names: list[str]) -> list[str]:
    return [name for name in names if name in policy_fields]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
