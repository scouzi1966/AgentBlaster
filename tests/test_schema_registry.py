from __future__ import annotations

import json

from agentblaster.schema_registry import (
    artifact_schema_registry,
    artifact_schema_registry_json,
    format_artifact_schema_registry_markdown,
)


def test_artifact_schema_registry_documents_core_artifacts() -> None:
    registry = artifact_schema_registry()
    artifacts = {artifact["id"]: artifact for artifact in registry["artifacts"]}

    assert registry["schema_version"] == "agentblaster.artifact-schema-registry.v1"
    assert {"run-manifest", "normalized-results", "normalized-response-telemetry", "local-engine-onboarding", "lifecycle-events", "cleanup-plan", "retention-cleanup", "redaction-scan", "provider-audit", "suite-audit", "benchmark-readiness", "benchmark-readiness-input-list", "campaign-preflight-bundle", "provider-contract-surface", "matrix-execution-summary", "matrix-gate", "matrix-report", "matrix-scorecard", "matrix-publication-bundle", "matrix-publication-bundle-manifest", "publication-report", "publication-brief", "publication-bundle", "publication-bundle-manifest", "release-provenance", "release-sbom", "enterprise-policy-template", "policy-control-summary", "sdlc-validation-manifest", "implementation-status", "harness-review", "suite-calibration-report", "engine-improvement-advisory", "evidence-index", "metric-coverage"} <= set(artifacts)
    assert artifacts["run-manifest"]["publication_safe"] is True
    assert artifacts["matrix-gate"]["schema_version"] == "agentblaster.matrix-gate.v1"
    assert "schema_version" in artifacts["matrix-gate"]["required_fields"]
    assert "failure_class_summary" in artifacts["matrix-gate"]["required_fields"]
    assert artifacts["engine-improvement-advisory"]["schema_version"] == "agentblaster.engine-improvement-advisory.v1"
    assert "release qualification" in artifacts["engine-improvement-advisory"]["consumed_by"]
    assert artifacts["evidence-index"]["schema_version"] == "agentblaster.evidence-index.v1"
    assert artifacts["evidence-index"]["publication_safe"] is True
    assert "cleanup_evidence" in artifacts["evidence-index"]["required_fields"]
    assert artifacts["suite-audit"]["schema_version"] == "agentblaster.suite-audit.v1"
    assert "dataset_hygiene" in artifacts["suite-audit"]["required_fields"]
    assert artifacts["suite-calibration-report"]["schema_version"] == "agentblaster.suite-calibration-report.v1"
    assert "claim readiness" in artifacts["suite-calibration-report"]["consumed_by"]
    assert artifacts["metric-coverage"]["schema_version"] == "agentblaster.metric-coverage.v1"
    assert "comparability" in artifacts["metric-coverage"]["required_fields"]
    assert "claim_contract" in artifacts["metric-coverage"]["required_fields"]
    assert artifacts["normalized-response-telemetry"]["schema_version"] == "agentblaster.normalized-telemetry.v1"
    assert "stats_comparability" in artifacts["normalized-response-telemetry"]["required_fields"]
    assert "release qualification" in artifacts["normalized-response-telemetry"]["consumed_by"]
    assert "evidence index" in artifacts["normalized-response-telemetry"]["consumed_by"]
    assert "dashboard review artifacts" in artifacts["normalized-response-telemetry"]["consumed_by"]
    assert artifacts["local-engine-onboarding"]["schema_version"] == "agentblaster.local-engine-onboarding.v1"
    assert "standardization" in artifacts["local-engine-onboarding"]["required_fields"]
    assert artifacts["local-engine-onboarding"]["publication_safe"] is True
    assert artifacts["local-engine-onboarding"]["contains_secrets"] is False
    assert artifacts["benchmark-readiness"]["schema_version"] == "agentblaster.benchmark-readiness.v1"
    assert "provider_auth_posture" in artifacts["benchmark-readiness"]["required_fields"]
    assert "secret_backend_posture" in artifacts["benchmark-readiness"]["required_fields"]
    assert "campaign preflight" in artifacts["benchmark-readiness"]["consumed_by"]
    assert "claim readiness" in artifacts["benchmark-readiness"]["consumed_by"]
    assert artifacts["benchmark-readiness-input-list"]["schema_version"] == "agentblaster.benchmark-readiness-input-list.v1"
    assert "agentblaster evidence campaign-preflight --benchmark-readiness-list" in artifacts["benchmark-readiness-input-list"]["consumed_by"]
    assert "claim readiness" in artifacts["campaign-preflight-bundle"]["consumed_by"]
    assert "release qualification" in artifacts["campaign-preflight-bundle"]["consumed_by"]
    assert "dashboard review artifacts" in artifacts["campaign-preflight-bundle"]["consumed_by"]
    assert artifacts["provider-contract-surface"]["schema_version"] == "agentblaster.provider-contract-surface.v1"
    assert "request_features" in artifacts["provider-contract-surface"]["required_fields"]
    assert artifacts["provider-contract-surface"]["contains_raw_provider_payloads"] is False
    assert artifacts["publication-brief"]["schema_version"] == "agentblaster.publication-brief.v1"
    assert "recommended_language" in artifacts["publication-brief"]["required_fields"]
    assert "media_kit" in artifacts["publication-brief"]["required_fields"]
    assert artifacts["publication-brief"]["publication_safe"] is True
    assert "release qualification" in artifacts["publication-brief"]["consumed_by"]
    assert "claim readiness via release bundle" in artifacts["publication-brief"]["consumed_by"]
    assert "evidence index" in artifacts["publication-brief"]["consumed_by"]
    assert "dashboard review artifacts" in artifacts["publication-brief"]["consumed_by"]
    assert artifacts["enterprise-policy-template"]["schema_version"] == "agentblaster.enterprise-policy-template.v1"
    assert artifacts["enterprise-policy-template"]["contains_secrets"] is False
    assert artifacts["policy-control-summary"]["schema_version"] == "agentblaster.policy-control-summary.v1"
    assert "blockers" in artifacts["policy-control-summary"]["required_fields"]
    assert artifacts["sdlc-validation-manifest"]["schema_version"] == "agentblaster.sdlc-validation-manifest.v1"
    assert "release_evidence" in artifacts["sdlc-validation-manifest"]["required_fields"]
    assert artifacts["sdlc-validation-manifest"]["contains_secrets"] is False
    assert "release qualification" in artifacts["sdlc-validation-manifest"]["consumed_by"]
    assert "claim readiness via release bundle" in artifacts["sdlc-validation-manifest"]["consumed_by"]
    assert "evidence index" in artifacts["sdlc-validation-manifest"]["consumed_by"]
    assert "dashboard review artifacts" in artifacts["sdlc-validation-manifest"]["consumed_by"]
    assert "evidence" in artifacts["claim-readiness"]["required_fields"]
    assert artifacts["publication-bundle"]["schema_version"] == "agentblaster.publication-bundle.zip"
    assert "publication-bundle-manifest.json" in artifacts["publication-bundle"]["required_fields"]
    assert artifacts["publication-bundle-manifest"]["schema_version"] == "agentblaster.publication-bundle.v1"
    assert artifacts["publication-bundle-manifest"]["contains_raw_provider_payloads"] is False
    assert "media_kit" in artifacts["publication-bundle-manifest"]["required_fields"]
    assert "integrity" in artifacts["publication-bundle-manifest"]["required_fields"]
    assert "security" in artifacts["publication-bundle-manifest"]["required_fields"]
    assert artifacts["matrix-publication-bundle"]["schema_version"] == "agentblaster-matrix-publication.zip"
    assert "matrix-publication-bundle-manifest.json" in artifacts["matrix-publication-bundle"]["required_fields"]
    assert "claim readiness" in artifacts["matrix-publication-bundle"]["consumed_by"]
    assert "evidence index" in artifacts["matrix-publication-bundle-manifest"]["consumed_by"]
    assert artifacts["matrix-publication-bundle-manifest"]["schema_version"] == "agentblaster.matrix-publication-bundle.v1"
    assert "media_kit" in artifacts["matrix-publication-bundle-manifest"]["required_fields"]
    assert artifacts["matrix-publication-bundle-manifest"]["publication_safe"] is True
    assert artifacts["release-provenance"]["schema_version"] == "agentblaster.release-provenance"
    assert artifacts["release-provenance"]["publication_safe"] is True
    assert "sbom" in artifacts["release-provenance"]["required_fields"]
    assert "claim readiness" in artifacts["release-provenance"]["consumed_by"]
    assert artifacts["release-sbom"]["schema_version"] == "agentblaster.sbom.v1"
    assert artifacts["release-sbom"]["contains_secrets"] is False
    assert "security" in artifacts["release-sbom"]["required_fields"]
    assert "supply-chain review" in artifacts["release-sbom"]["consumed_by"]
    assert artifacts["raw-response"]["contains_raw_provider_payloads"] is True
    assert artifacts["raw-response"]["publication_safe"] is False
    assert artifacts["cleanup-plan"]["schema_version"] == "agentblaster.cleanup-plan.v1"
    assert artifacts["cleanup-plan"]["publication_safe"] is False
    assert artifacts["cleanup-plan"]["contains_secrets"] is False
    assert "security" in artifacts["cleanup-plan"]["required_fields"]
    assert artifacts["retention-cleanup"]["schema_version"] == "agentblaster.retention-cleanup.v1"
    assert artifacts["retention-cleanup"]["publication_safe"] is False
    assert artifacts["retention-cleanup"]["contains_raw_provider_payloads"] is False
    assert "actions" in artifacts["retention-cleanup"]["required_fields"]
    assert artifacts["redaction-scan"]["schema_version"] == "agentblaster.redaction-scan.v1"
    assert artifacts["redaction-scan"]["publication_safe"] is True
    assert "findings" in artifacts["redaction-scan"]["required_fields"]
    assert "claim readiness" in artifacts["redaction-scan"]["consumed_by"]
    assert artifacts["provider-audit"]["schema_version"] == "agentblaster.provider-audit.v1"
    assert artifacts["provider-audit"]["publication_safe"] is True
    assert artifacts["provider-audit"]["contains_secrets"] is False
    assert "providers" in artifacts["provider-audit"]["required_fields"]
    assert "release qualification" in artifacts["provider-audit"]["consumed_by"]
    assert "claim readiness" in artifacts["provider-audit"]["consumed_by"]
    assert "secret_backend_posture" in artifacts["provider-audit"]["required_fields"]
    assert "evidence index" in artifacts["provider-audit"]["consumed_by"]
    assert "dashboard review artifacts" in artifacts["provider-audit"]["consumed_by"]
    assert "corporate security review" in artifacts["provider-audit"]["consumed_by"]
    assert artifacts["readiness-artifacts"]["contains_secrets"] is False
    assert artifacts["readiness-artifacts"]["publication_safe"] is False
    assert artifacts["implementation-status"]["schema_version"] == "agentblaster.implementation-status.v1"
    assert artifacts["implementation-status"]["publication_safe"] is False
    assert artifacts["implementation-status"]["contains_raw_provider_payloads"] is False
    assert artifacts["implementation-status"]["contains_secrets"] is False
    assert "suite_inventory" in artifacts["implementation-status"]["required_fields"]
    assert "requirements_inventory" in artifacts["implementation-status"]["required_fields"]
    assert "campaign preflight" in artifacts["implementation-status"]["consumed_by"]
    assert "evidence index" in artifacts["implementation-status"]["consumed_by"]
    assert "dashboard review artifacts" in artifacts["implementation-status"]["consumed_by"]
    assert any("Raw reports can include local project-root" in note for note in artifacts["implementation-status"]["notes"])
    assert any("stats-comparability/metric-coverage" in note for note in artifacts["implementation-status"]["notes"])
    assert artifacts["campaign-preflight-bundle"]["publication_safe"] is False
    assert any("local output" in note for note in artifacts["campaign-preflight-bundle"]["notes"])
    assert "schema_version" in json.loads(artifact_schema_registry_json())


def test_artifact_schema_registry_markdown_is_publication_oriented() -> None:
    markdown = format_artifact_schema_registry_markdown()

    assert "# AgentBlaster Artifact Schema Registry" in markdown
    assert "`run-manifest`" in markdown
    assert "`raw-response`" in markdown
    assert "Publication safe" in markdown
