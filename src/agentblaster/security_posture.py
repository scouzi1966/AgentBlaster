from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentblaster.errors import ConfigError
from agentblaster.policy import SecurityPolicy, load_policy, policy_control_summary
from agentblaster.secrets import secret_backend_posture


SECURITY_POSTURE_SCHEMA_VERSION = "agentblaster.security-posture.v1"
PROVIDER_AUDIT_SCHEMA_VERSION = "agentblaster.provider-audit.v1"
REDACTION_SCAN_SCHEMA_VERSION = "agentblaster.redaction-scan.v1"

UNSAFE_SECURITY_FLAGS = (
    "contains_raw_provider_payloads",
    "contains_raw_traces",
    "contains_secrets",
    "contains_api_keys",
    "stores_raw_secrets",
    "reads_keyring_values",
    "resolves_secret_references",
)

REVIEW_SECURITY_FLAGS = (
    "contacts_providers",
    "dispatches_requests",
    "includes_prompts",
    "includes_raw_provider_payloads",
)


def build_security_posture_report(
    *,
    name: str,
    policy_path: Path | None = None,
    provider_audits: list[Path] | None = None,
    redaction_scans: list[Path] | None = None,
    review_artifacts: list[Path] | None = None,
) -> dict[str, Any]:
    """Build a static enterprise security posture report without resolving secrets."""
    policy = load_policy(policy_path)
    policy_summary = policy_control_summary(policy, name="security-posture-policy")
    provider_summaries = [
        _provider_audit_summary(_load_json_artifact(path, expected_schema=PROVIDER_AUDIT_SCHEMA_VERSION), path)
        for path in provider_audits or []
    ]
    redaction_summaries = [
        _redaction_scan_summary(_load_json_artifact(path, expected_schema=REDACTION_SCAN_SCHEMA_VERSION), path)
        for path in redaction_scans or []
    ]
    artifact_summaries = [_review_artifact_summary(_load_json_artifact(path), path) for path in review_artifacts or []]
    findings = _findings(
        policy=policy,
        policy_summary=policy_summary,
        provider_summaries=provider_summaries,
        redaction_summaries=redaction_summaries,
        artifact_summaries=artifact_summaries,
    )
    blockers = [finding for finding in findings if finding["severity"] == "blocker"]
    warnings = [finding for finding in findings if finding["severity"] == "warning"]
    status = "ready" if not blockers else "review-required"
    source_artifacts = []
    if policy_path is not None:
        source_artifacts.append(_artifact_ref("policy", policy_path))
    source_artifacts.extend(_artifact_ref("provider_audit", path) for path in provider_audits or [])
    source_artifacts.extend(_artifact_ref("redaction_scan", path) for path in redaction_scans or [])
    source_artifacts.extend(_artifact_ref("review_artifact", path) for path in review_artifacts or [])
    return {
        "schema_version": SECURITY_POSTURE_SCHEMA_VERSION,
        "name": _safe_name(name),
        "status": status,
        "ready": status == "ready",
        "summary": {
            "blockers": len(blockers),
            "warnings": len(warnings),
            "provider_audit_count": len(provider_summaries),
            "redaction_scan_count": len(redaction_summaries),
            "review_artifact_count": len(artifact_summaries),
            "provider_count": sum(_int(item.get("total_providers")) for item in provider_summaries),
            "remote_provider_count": sum(_int(item.get("remote_providers")) for item in provider_summaries),
            "redaction_finding_count": sum(_int(item.get("finding_count")) for item in redaction_summaries),
            "unsafe_review_artifact_count": len([item for item in artifact_summaries if item.get("unsafe_security_flags")]),
        },
        "policy": policy_summary,
        "secret_backend_posture": secret_backend_posture(),
        "provider_audits": provider_summaries,
        "redaction_scans": redaction_summaries,
        "review_artifacts": artifact_summaries,
        "findings": findings,
        "recommendations": _recommendations(blockers, warnings, policy, provider_summaries, redaction_summaries, artifact_summaries),
        "security": {
            "source_artifact_count": len(source_artifacts),
            "source_artifacts": source_artifacts,
            "contains_raw_provider_payloads": False,
            "contains_raw_traces": False,
            "contains_secrets": False,
            "stores_raw_secrets": False,
            "reads_keyring_values": False,
            "resolves_secret_references": False,
            "contacts_providers": False,
            "dispatches_requests": False,
            "path_policy": "Input paths are reduced to relative artifact names or basenames for absolute/parent-relative paths.",
            "notes": [
                "Security posture is static and does not dispatch providers, resolve secrets, read keyring values, or inspect environment variable values.",
                "Provider audit inputs summarize secret reference kinds only; raw secret names and values are excluded.",
                "Redaction scan inputs report finding pattern names and locations only; matched values are not copied.",
                "Review artifact inputs are summarized by schema and boolean security flags only.",
            ],
        },
    }


def write_security_posture_json(report: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def write_security_posture_markdown(report: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(format_security_posture_report(report), encoding="utf-8")
    return output


def format_security_posture_report(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    policy = report.get("policy") if isinstance(report.get("policy"), dict) else {}
    policy_summary = policy.get("summary") if isinstance(policy.get("summary"), dict) else {}
    secret_posture = report.get("secret_backend_posture") if isinstance(report.get("secret_backend_posture"), dict) else {}
    lines = [
        "# AgentBlaster Security Posture",
        "",
        "## Summary",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Name | `{_markdown_cell(report.get('name'))}` |",
        f"| Status | `{_markdown_cell(report.get('status'))}` |",
        f"| Ready | `{str(report.get('ready')).lower()}` |",
        f"| Blockers | `{summary.get('blockers', 0)}` |",
        f"| Warnings | `{summary.get('warnings', 0)}` |",
        f"| Provider audits | `{summary.get('provider_audit_count', 0)}` |",
        f"| Redaction scans | `{summary.get('redaction_scan_count', 0)}` |",
        f"| Review artifacts | `{summary.get('review_artifact_count', 0)}` |",
        f"| Redaction findings | `{summary.get('redaction_finding_count', 0)}` |",
        f"| Unsafe review artifacts | `{summary.get('unsafe_review_artifact_count', 0)}` |",
        f"| Policy controls enabled | `{policy_summary.get('enabled_controls', 0)}/{policy_summary.get('control_count', 0)}` |",
        f"| Keyring optional | `{str(secret_posture.get('keyring_optional', True)).lower()}` |",
        f"| Keyring dependency available | `{str(secret_posture.get('keyring_dependency_available', False)).lower()}` |",
        "",
        "## Findings",
        "",
    ]
    findings = report.get("findings") if isinstance(report.get("findings"), list) else []
    if findings:
        lines.extend(
            [
                "| Severity | Code | Message |",
                "| --- | --- | --- |",
            ]
        )
        for finding in findings:
            if isinstance(finding, dict):
                lines.append(
                    "| "
                    f"`{_markdown_cell(finding.get('severity'))}` | "
                    f"`{_markdown_cell(finding.get('code'))}` | "
                    f"{_markdown_cell(finding.get('message'))} |"
                )
    else:
        lines.append("No security posture findings were generated.")
    lines.extend(["", "## Provider Audits", ""])
    provider_audits = report.get("provider_audits") if isinstance(report.get("provider_audits"), list) else []
    if provider_audits:
        lines.extend(
            [
                "| Artifact | Providers | Remote | Policy OK | Errors | Warnings | Plaintext fallback | Insecure TLS |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for item in provider_audits:
            if isinstance(item, dict):
                lines.append(
                    "| "
                    f"{_markdown_cell(item.get('artifact', {}).get('name') if isinstance(item.get('artifact'), dict) else item.get('artifact'))} | "
                    f"{item.get('total_providers', 0)} | "
                    f"{item.get('remote_providers', 0)} | "
                    f"{item.get('policy_ok', 0)} | "
                    f"{item.get('errors', 0)} | "
                    f"{item.get('warnings', 0)} | "
                    f"{item.get('plaintext_fallback_count', 0)} | "
                    f"{item.get('insecure_tls_count', 0)} |"
                )
    else:
        lines.append("No provider audit artifact supplied.")
    lines.extend(["", "## Redaction Scans", ""])
    redaction_scans = report.get("redaction_scans") if isinstance(report.get("redaction_scans"), list) else []
    if redaction_scans:
        lines.extend(
            [
                "| Artifact | OK | Findings | Scanned items | Skipped items | Patterns |",
                "| --- | --- | ---: | ---: | ---: | --- |",
            ]
        )
        for item in redaction_scans:
            if isinstance(item, dict):
                lines.append(
                    "| "
                    f"{_markdown_cell(item.get('artifact', {}).get('name') if isinstance(item.get('artifact'), dict) else item.get('artifact'))} | "
                    f"`{str(item.get('ok')).lower()}` | "
                    f"{item.get('finding_count', 0)} | "
                    f"{item.get('scanned_items', 0)} | "
                    f"{item.get('skipped_items', 0)} | "
                    f"{_join_or_none(item.get('patterns', []))} |"
                )
    else:
        lines.append("No redaction scan artifact supplied.")
    lines.extend(["", "## Recommendations", ""])
    lines.extend(f"- {_markdown_cell(item)}" for item in report.get("recommendations", []) or ["No recommendations generated."])
    lines.extend(
        [
            "",
            "## Security Boundary",
            "",
            "- This report does not contact providers, resolve API keys, inspect keyring values, or read environment variable values.",
            "- Provider audit inputs summarize secret reference kinds only.",
            "- Redaction scan inputs copy finding metadata only, not matched values.",
            "- Review artifacts are summarized by schema and boolean security flags only.",
            "",
        ]
    )
    return "\n".join(lines)


def _provider_audit_summary(payload: dict[str, Any], path: Path) -> dict[str, Any]:
    providers = payload.get("providers") if isinstance(payload.get("providers"), list) else []
    plaintext = 0
    insecure_tls = 0
    missing_api_key_refs = 0
    keyring_required = 0
    for provider in providers:
        if not isinstance(provider, dict):
            continue
        plaintext += 1 if provider.get("api_key_ref_plaintext_fallback") is True else 0
        insecure_tls += 1 if provider.get("tls_verify") is False else 0
        missing_api_key_refs += 1 if provider.get("remote") is True and provider.get("api_key_ref_configured") is not True else 0
        keyring_required += 1 if provider.get("keyring_backend_required") is True else 0
    return {
        "artifact": _artifact_ref("provider_audit", path),
        "schema_version": _safe_text(payload.get("schema_version")),
        "total_providers": _int(payload.get("total_providers")),
        "remote_providers": _int(payload.get("remote_providers")),
        "policy_ok": _int(payload.get("policy_ok")),
        "errors": _int(payload.get("errors")),
        "warnings": _int(payload.get("warnings")),
        "plaintext_fallback_count": plaintext,
        "insecure_tls_count": insecure_tls,
        "remote_without_api_key_ref_count": missing_api_key_refs,
        "keyring_required_count": keyring_required,
    }


def _redaction_scan_summary(payload: dict[str, Any], path: Path) -> dict[str, Any]:
    findings = payload.get("findings") if isinstance(payload.get("findings"), list) else []
    patterns = sorted(
        {
            str(finding.get("pattern"))
            for finding in findings
            if isinstance(finding, dict) and finding.get("pattern")
        }
    )
    return {
        "artifact": _artifact_ref("redaction_scan", path),
        "schema_version": _safe_text(payload.get("schema_version")),
        "ok": payload.get("ok") is True,
        "total_paths": _int(payload.get("total_paths")),
        "scanned_items": _int(payload.get("scanned_items")),
        "skipped_items": _int(payload.get("skipped_items")),
        "finding_count": len([item for item in findings if isinstance(item, dict)]),
        "patterns": patterns,
    }


def _review_artifact_summary(payload: dict[str, Any], path: Path) -> dict[str, Any]:
    security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    flags = {**{key: security.get(key) for key in security}, **{key: safety.get(key) for key in safety}}
    unsafe_flags = sorted(flag for flag in UNSAFE_SECURITY_FLAGS if flags.get(flag) is True)
    review_flags = sorted(flag for flag in REVIEW_SECURITY_FLAGS if flags.get(flag) is True)
    schema = _safe_text(payload.get("schema_version") or payload.get("schema") or payload.get("report_type") or "unknown")
    return {
        "artifact": _artifact_ref("review_artifact", path),
        "schema": schema,
        "unsafe_security_flags": unsafe_flags,
        "review_security_flags": review_flags,
        "declares_security_boundary": bool(security or safety),
    }


def _findings(
    *,
    policy: SecurityPolicy,
    policy_summary: dict[str, Any],
    provider_summaries: list[dict[str, Any]],
    redaction_summaries: list[dict[str, Any]],
    artifact_summaries: list[dict[str, Any]],
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for blocker in policy_summary.get("blockers", []):
        findings.append(
            {
                "severity": "blocker",
                "code": "policy_blocker",
                "message": str(blocker),
            }
        )
    for warning in policy_summary.get("warnings", []):
        findings.append(
            {
                "severity": "warning",
                "code": "policy_warning",
                "message": str(warning),
            }
        )
    if not provider_summaries:
        findings.append(
            {
                "severity": "warning",
                "code": "provider_audit_missing",
                "message": "No provider audit artifact was supplied for enterprise security posture.",
            }
        )
    for summary in provider_summaries:
        artifact_name = summary["artifact"]["name"]
        if _int(summary.get("errors")):
            findings.append(
                {
                    "severity": "blocker",
                    "code": "provider_audit_errors",
                    "message": f"{artifact_name} reports {_int(summary.get('errors'))} provider policy error(s).",
                }
            )
        if _int(summary.get("plaintext_fallback_count")):
            findings.append(
                {
                    "severity": "warning",
                    "code": "plaintext_secret_backend",
                    "message": f"{artifact_name} reports {_int(summary.get('plaintext_fallback_count'))} provider(s) using dotenv plaintext fallback.",
                }
            )
        if _int(summary.get("insecure_tls_count")):
            findings.append(
                {
                    "severity": "warning" if policy.allow_insecure_tls else "blocker",
                    "code": "insecure_tls",
                    "message": f"{artifact_name} reports {_int(summary.get('insecure_tls_count'))} provider(s) with TLS verification disabled.",
                }
            )
    if not redaction_summaries:
        findings.append(
            {
                "severity": "warning",
                "code": "redaction_scan_missing",
                "message": "No redaction scan artifact was supplied for shareable outputs.",
            }
        )
    for summary in redaction_summaries:
        if summary.get("ok") is not True:
            findings.append(
                {
                    "severity": "blocker",
                    "code": "redaction_findings",
                    "message": f"{summary['artifact']['name']} reports {_int(summary.get('finding_count'))} redaction finding(s).",
                }
            )
    for summary in artifact_summaries:
        if summary.get("unsafe_security_flags"):
            findings.append(
                {
                    "severity": "blocker",
                    "code": "unsafe_review_artifact",
                    "message": f"{summary['artifact']['name']} declares unsafe security flags: {', '.join(summary['unsafe_security_flags'])}.",
                }
            )
        if summary.get("review_security_flags"):
            findings.append(
                {
                    "severity": "warning",
                    "code": "review_artifact_operational_scope",
                    "message": f"{summary['artifact']['name']} declares operational review flags: {', '.join(summary['review_security_flags'])}.",
                }
            )
        if not summary.get("declares_security_boundary"):
            findings.append(
                {
                    "severity": "warning",
                    "code": "security_boundary_missing",
                    "message": f"{summary['artifact']['name']} does not declare a security or safety boundary block.",
                }
            )
    return findings


def _recommendations(
    blockers: list[dict[str, str]],
    warnings: list[dict[str, str]],
    policy: SecurityPolicy,
    provider_summaries: list[dict[str, Any]],
    redaction_summaries: list[dict[str, Any]],
    artifact_summaries: list[dict[str, Any]],
) -> list[str]:
    if not blockers and not warnings:
        return [
            "Use this security-posture artifact as corporate signoff evidence for benchmark setup and shareable outputs.",
            "Keep provider audits and redaction scans attached to release qualification and claim-readiness evidence.",
        ]
    recommendations: list[str] = []
    codes = {finding["code"] for finding in blockers + warnings}
    if "policy_blocker" in codes or "policy_warning" in codes:
        recommendations.append("Start from `agentblaster policy template --profile local` or `--profile remote-gateway`, then review host, secret, dashboard, cleanup, cost, and scale controls.")
    if "provider_audit_missing" in codes:
        recommendations.append("Generate `agentblaster providers audit --output-json reports/provider-audit.json` before external review.")
    if "redaction_scan_missing" in codes:
        recommendations.append("Run `agentblaster security scan` over publication, release, and dashboard review artifacts before sharing.")
    if "redaction_findings" in codes:
        recommendations.append("Regenerate or sanitize shareable artifacts until redaction scans report zero findings.")
    if "provider_audit_errors" in codes:
        recommendations.append("Resolve provider policy errors, especially remote API-key references, host allowlists, rate limits, cost models, and TLS posture.")
    if "plaintext_secret_backend" in codes or (policy.allowed_secret_ref_kinds is not None and "dotenv" in policy.allowed_secret_ref_kinds):
        recommendations.append("Use environment references or optional keyring/Apple Keychain for enterprise API-key storage; reserve dotenv fallback for approved local development only.")
    if "unsafe_review_artifact" in codes:
        recommendations.append("Do not publish artifacts that declare raw traces, raw provider payloads, secrets, API keys, or raw secret storage.")
    if not provider_summaries:
        recommendations.append("Attach provider audit evidence so reviewers can confirm API-key reference and remote-provider policy posture without reading secrets.")
    if not redaction_summaries:
        recommendations.append("Attach redaction scan evidence for every shareable publication or release bundle.")
    if not artifact_summaries:
        recommendations.append("Attach key shareable review artifacts so their declared security boundaries are summarized in one place.")
    return recommendations


def _load_json_artifact(path: Path | None, *, expected_schema: str | None = None) -> dict[str, Any]:
    if path is None:
        raise ConfigError("missing JSON artifact path")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"cannot read JSON artifact {path.name}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON artifact {path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConfigError(f"JSON artifact {path.name} must contain an object")
    if expected_schema:
        schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema"), payload.get("report_type")) if value}
        if expected_schema not in schema_values:
            raise ConfigError(f"JSON artifact {path.name} must use schema {expected_schema}")
    return payload


def _artifact_ref(kind: str, path: Path) -> dict[str, str]:
    path = path.expanduser()
    safe_name = path.name if path.is_absolute() or ".." in path.parts else str(path)
    return {"kind": kind, "name": safe_name}


def _safe_name(value: Any) -> str:
    return (_safe_text(value) or "security-posture")[:160]


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\0", "").strip()[:240]


def _markdown_cell(value: Any) -> str:
    return _safe_text(value).replace("|", "\\|") or "n/a"


def _join_or_none(values: Any) -> str:
    if not isinstance(values, list) or not values:
        return "none"
    return ", ".join(_safe_text(item) for item in values)


def _int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0
