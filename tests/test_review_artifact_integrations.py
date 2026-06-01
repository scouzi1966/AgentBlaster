from __future__ import annotations

import json
from zipfile import ZipFile

from agentblaster.claim_readiness import build_claim_readiness
from agentblaster.dashboard import _json_review_summary
from agentblaster.evidence_index import build_evidence_index
from agentblaster.release_qualification import create_release_qualification_bundle


def test_release_qualification_bundle_carries_protocol_workflow_and_security_posture(tmp_path) -> None:
    protocol = _write_protocol_repair(tmp_path)
    workflow = _write_workflow_readiness(tmp_path)
    security = _write_security_posture(tmp_path)

    bundle = create_release_qualification_bundle(
        name="release",
        output_dir=tmp_path,
        protocol_repair_postures=[protocol],
        workflow_readiness_reports=[workflow],
        security_postures=[security],
    )

    with ZipFile(bundle) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))

    categories = {artifact["category"] for artifact in manifest["artifacts"]}
    assert "publication/protocol-repair" in categories
    assert "readiness/workflow" in categories
    assert "security/posture" in categories
    summaries = {artifact["category"]: artifact["review_summary"] for artifact in manifest["artifacts"]}
    assert summaries["publication/protocol-repair"]["scorecard_tool_parser_repair_cases"] == 2
    assert summaries["readiness/workflow"]["covered_required_surface_count"] == 10
    assert summaries["security/posture"]["blockers"] == 0


def test_claim_readiness_collects_protocol_workflow_and_security_posture(tmp_path) -> None:
    protocol = _write_protocol_repair(tmp_path)
    workflow = _write_workflow_readiness(tmp_path)
    security = _write_security_posture(tmp_path)

    report = build_claim_readiness(
        name="claim",
        protocol_repair_postures=[protocol],
        workflow_readiness_reports=[workflow],
        security_postures=[security],
    )

    evidence = report["evidence"]
    assert evidence["protocol_repair_posture_summaries"][0]["scorecard_tool_parser_repair_cases"] == 2
    assert evidence["workflow_readiness_summaries"][0]["gap_count"] == 0
    assert evidence["security_posture_summaries"][0]["redaction_finding_count"] == 0


def test_evidence_index_and_dashboard_summarize_protocol_workflow_and_security_posture(tmp_path) -> None:
    protocol = _write_protocol_repair(tmp_path)
    workflow = _write_workflow_readiness(tmp_path)
    security = _write_security_posture(tmp_path)

    index = build_evidence_index(name="index", artifacts=[protocol, workflow, security])
    summaries = {artifact["schema"]: artifact["review_summary"] for artifact in index["artifacts"]}
    assert summaries["agentblaster.protocol-repair-posture.v1"]["matrix_gate_tool_parser_repair_cases"] == 2
    assert summaries["agentblaster.workflow-readiness.v1"]["required_surface_count"] == 10
    assert summaries["agentblaster.security-posture.v1"]["provider_audit_count"] == 1

    dashboard_protocol = _json_review_summary(protocol, max_bytes=1_000_000)
    dashboard_workflow = _json_review_summary(workflow, max_bytes=1_000_000)
    dashboard_security = _json_review_summary(security, max_bytes=1_000_000)
    assert dashboard_protocol["protocol_repair_posture_summaries"][0]["scorecard_tool_parser_repair_cases"] == 2
    assert dashboard_workflow["workflow_readiness_summaries"][0]["gap_count"] == 0
    assert dashboard_security["security_posture_summaries"][0]["blockers"] == 0


def _write_protocol_repair(tmp_path):
    path = tmp_path / "protocol-repair.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.protocol-repair-posture.v1",
                "name": "protocol",
                "status": "ready",
                "ready": True,
                "scorecard_summary": {
                    "source_count": 1,
                    "invalid_tool_call_count": 0,
                    "tool_parser_repair_cases": 2,
                    "tool_parser_repairs_valid": 2,
                    "tool_parser_repair_valid_rate_percent": 100.0,
                },
                "matrix_gate_summary": {
                    "source_count": 1,
                    "invalid_tool_call_count": 0,
                    "tool_parser_repair_cases": 2,
                    "tool_parser_repairs_valid": 2,
                    "tool_parser_repair_valid_rate_percent": 100.0,
                    "tool_parser_repair_artifacts_missing": 0,
                },
                "disclosures": [],
                "recommendations": [],
                "security": {
                    "contains_raw_provider_payloads": False,
                    "contains_raw_traces": False,
                    "contains_secrets": False,
                    "stores_raw_secrets": False,
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _write_workflow_readiness(tmp_path):
    path = tmp_path / "workflow-readiness.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.workflow-readiness.v1",
                "name": "workflow",
                "status": "ready",
                "ready": True,
                "required_surfaces": [
                    "tool-calling",
                    "tool-loop",
                    "structured-output",
                    "concurrency",
                    "prefill-cache",
                    "mcp",
                    "lcp",
                    "skills",
                    "cancellation",
                    "harness-engineering",
                ],
                "summary": {
                    "source_count": 1,
                    "case_count": 10,
                    "required_surface_count": 10,
                    "covered_required_surface_count": 10,
                    "gap_count": 0,
                    "max_concurrency": 4,
                    "concurrency_levels": [1, 4],
                },
                "coverage": [],
                "gaps": [],
                "security": {
                    "contains_raw_provider_payloads": False,
                    "contains_raw_traces": False,
                    "contains_secrets": False,
                    "contacts_providers": False,
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _write_security_posture(tmp_path):
    path = tmp_path / "security-posture.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.security-posture.v1",
                "name": "security",
                "status": "ready",
                "ready": True,
                "summary": {
                    "blockers": 0,
                    "warnings": 0,
                    "provider_audit_count": 1,
                    "redaction_scan_count": 1,
                    "review_artifact_count": 2,
                    "redaction_finding_count": 0,
                    "unsafe_review_artifact_count": 0,
                },
                "secret_backend_posture": {
                    "keyring_optional": True,
                    "keyring_dependency_available": False,
                },
                "provider_audits": [],
                "redaction_scans": [],
                "review_artifacts": [],
                "findings": [],
                "recommendations": [],
                "security": {
                    "contains_raw_provider_payloads": False,
                    "contains_raw_traces": False,
                    "contains_secrets": False,
                    "stores_raw_secrets": False,
                    "reads_keyring_values": False,
                    "resolves_secret_references": False,
                    "contacts_providers": False,
                    "dispatches_requests": False,
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path
