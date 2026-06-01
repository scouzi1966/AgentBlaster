from __future__ import annotations

import json

from typer.testing import CliRunner

from agentblaster.cli import app
from agentblaster.security_posture import build_security_posture_report, format_security_posture_report


def test_security_posture_summarizes_policy_provider_redaction_and_artifacts(tmp_path) -> None:
    policy = _write_policy(tmp_path)
    provider_audit = _write_provider_audit(tmp_path)
    redaction_scan = _write_redaction_scan(tmp_path, ok=True)
    review_artifact = _write_review_artifact(tmp_path, unsafe=False)

    report = build_security_posture_report(
        name="security",
        policy_path=policy,
        provider_audits=[provider_audit],
        redaction_scans=[redaction_scan],
        review_artifacts=[review_artifact],
    )

    assert report["schema_version"] == "agentblaster.security-posture.v1"
    assert report["ready"] is True
    assert report["summary"]["blockers"] == 0
    assert report["summary"]["provider_audit_count"] == 1
    assert report["summary"]["redaction_scan_count"] == 1
    assert report["summary"]["review_artifact_count"] == 1
    assert report["provider_audits"][0]["remote_providers"] == 1
    assert report["redaction_scans"][0]["finding_count"] == 0
    assert report["security"]["resolves_secret_references"] is False
    markdown = format_security_posture_report(report)
    assert "AgentBlaster Security Posture" in markdown
    assert "Keyring optional" in markdown


def test_security_posture_blocks_on_redaction_and_unsafe_artifacts(tmp_path) -> None:
    policy = _write_policy(tmp_path)
    provider_audit = _write_provider_audit(tmp_path)
    redaction_scan = _write_redaction_scan(tmp_path, ok=False)
    review_artifact = _write_review_artifact(tmp_path, unsafe=True)

    report = build_security_posture_report(
        name="security",
        policy_path=policy,
        provider_audits=[provider_audit],
        redaction_scans=[redaction_scan],
        review_artifacts=[review_artifact],
    )

    assert report["ready"] is False
    assert report["status"] == "review-required"
    assert {finding["code"] for finding in report["findings"]} >= {
        "redaction_findings",
        "unsafe_review_artifact",
    }


def test_security_posture_cli_writes_json_and_markdown(tmp_path) -> None:
    policy = _write_policy(tmp_path)
    provider_audit = _write_provider_audit(tmp_path)
    redaction_scan = _write_redaction_scan(tmp_path, ok=True)
    review_artifact = _write_review_artifact(tmp_path, unsafe=False)
    output_json = tmp_path / "security-posture.json"
    output_md = tmp_path / "security-posture.md"

    result = CliRunner().invoke(
        app,
        [
            "security",
            "posture",
            "--name",
            "security",
            "--policy",
            str(policy),
            "--provider-audit",
            str(provider_audit),
            "--redaction-scan",
            str(redaction_scan),
            "--review-artifact",
            str(review_artifact),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ],
    )

    assert result.exit_code == 0, result.output
    assert str(output_json) in result.output
    assert str(output_md) in result.output
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "agentblaster.security-posture.v1"
    assert payload["ready"] is True
    assert "AgentBlaster Security Posture" in output_md.read_text(encoding="utf-8")


def _write_policy(tmp_path):
    path = tmp_path / "agentblaster.policy.yaml"
    path.write_text(
        """
allowed_providers:
  - openai-compatible-remote
allowed_base_url_hosts:
  - gateway.example.com
allowed_metrics_url_hosts:
  - gateway.example.com
allowed_secret_ref_kinds:
  - env
  - keyring
allowed_secret_ref_prefixes:
  - OPENAI_
  - ANTHROPIC_
allow_remote_providers: true
require_api_key_for_remote_providers: true
require_cost_model_for_remote_providers: true
require_rate_limits_for_remote_providers: true
allow_non_loopback_http_provider_urls: false
allow_non_loopback_http_metrics_urls: false
allow_full_raw_traces: false
allow_insecure_tls: false
allow_high_risk_cases: false
require_dashboard_auth: true
require_cleanup_audit_log: true
max_concurrency: 8
max_matrix_runs: 25
max_matrix_total_cases: 2500
max_output_tokens: 4096
max_timeout_seconds: 600
max_estimated_matrix_cost_usd: 25.0
""".lstrip(),
        encoding="utf-8",
    )
    return path


def _write_provider_audit(tmp_path):
    path = tmp_path / "provider-audit.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.provider-audit.v1",
                "total_providers": 1,
                "remote_providers": 1,
                "policy_ok": 1,
                "errors": 0,
                "warnings": 0,
                "policy_controls": {
                    "allow_remote_providers": True,
                    "allow_full_raw_traces": False,
                    "require_api_key_for_remote_providers": True,
                    "require_cost_model_for_remote_providers": True,
                    "require_rate_limits_for_remote_providers": True,
                    "require_dashboard_auth": True,
                    "require_cleanup_audit_log": True,
                },
                "secret_backend_posture": {
                    "env_reference_supported": True,
                    "keyring_optional": True,
                    "keyring_dependency_available": False,
                    "dotenv_plaintext_fallback_supported": True,
                    "dotenv_plaintext_fallback_enterprise_default": False,
                },
                "providers": [
                    {
                        "name": "openai-compatible-remote",
                        "contract": "openai",
                        "base_url_host": "gateway.example.com",
                        "remote": True,
                        "api_key_ref_kind": "env",
                        "api_key_ref_configured": True,
                        "api_key_ref_writable_backend": False,
                        "api_key_ref_plaintext_fallback": False,
                        "keyring_backend_required": False,
                        "keyring_dependency_available": None,
                        "prewrite_policy_guard_recommended": False,
                        "metrics_url_host": "gateway.example.com",
                        "tls_verify": True,
                        "ca_bundle_configured": False,
                        "cost_model_configured": True,
                        "rate_limits_configured": True,
                        "capabilities_declared": ["streaming", "tool_calling"],
                        "policy_ok": True,
                        "findings": [],
                    }
                ],
                "security_notes": [],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _write_redaction_scan(tmp_path, *, ok: bool):
    path = tmp_path / "redaction-scan.json"
    findings = [] if ok else [{"path": "publication.json", "entry": None, "line": 1, "pattern": "openai_api_key", "message": "secret-like pattern detected; matched value suppressed"}]
    path.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.redaction-scan.v1",
                "ok": ok,
                "total_paths": 1,
                "scanned_items": 1,
                "skipped_items": 0,
                "findings": findings,
                "security_notes": [],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _write_review_artifact(tmp_path, *, unsafe: bool):
    path = tmp_path / "workflow-readiness.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.workflow-readiness.v1",
                "name": "workflow-readiness",
                "security": {
                    "contains_raw_provider_payloads": unsafe,
                    "contains_raw_traces": False,
                    "contains_secrets": False,
                    "stores_raw_secrets": False,
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
