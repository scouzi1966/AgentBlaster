from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentblaster.capabilities import check_suite_compatibility
from agentblaster.contract_check import provider_contract_plan
from agentblaster.metric_coverage import metric_coverage_for_provider
from agentblaster.models import ProviderConfig, SuiteDefinition
from agentblaster.policy import SecurityPolicy
from agentblaster.provider_audit import audit_providers

READINESS_SCHEMA_VERSION = "agentblaster.benchmark-readiness.v1"


def build_readiness_dossier(
    *,
    provider: ProviderConfig,
    suite: SuiteDefinition,
    policy: SecurityPolicy,
    model: str | None = None,
    strict_unknown: bool = False,
) -> dict[str, Any]:
    """Build a no-network benchmark readiness dossier for one provider and suite."""
    provider_audit = audit_providers([provider], policy).model_dump(mode="json")
    capability_report = check_suite_compatibility(provider, suite, strict_unknown=strict_unknown).model_dump(mode="json")
    contract_plan = provider_contract_plan(provider, model=model)
    metric_coverage = metric_coverage_for_provider(provider)
    provider_auth_posture = _provider_auth_posture(provider_audit)
    secret_backend_posture = _compact_secret_backend_posture(provider_audit.get("secret_backend_posture"))
    blocking_findings = _blocking_findings(provider_audit, capability_report, contract_plan)
    contract_capability_evidence = contract_plan.get("capability_evidence", {})
    warnings = _warnings(provider_audit, capability_report, metric_coverage, contract_plan)
    return {
        "schema_version": READINESS_SCHEMA_VERSION,
        "provider": provider.name,
        "suite": suite.name,
        "model": model or provider.default_model or "<required>",
        "ready": not blocking_findings,
        "strict_unknown": strict_unknown,
        "summary": {
            "policy_ok": provider_audit["policy_ok"] == provider_audit["total_providers"] and provider_audit["errors"] == 0,
            "suite_compatible": capability_report["compatible"],
            "contract_checks_planned": contract_plan["summary"]["planned"],
            "contract_capabilities_directly_checked": len(
                contract_capability_evidence.get("directly_checked", [])
                if isinstance(contract_capability_evidence.get("directly_checked"), list)
                else []
            ),
            "contract_capabilities_proxy_checked": len(
                contract_capability_evidence.get("proxy_checked", [])
                if isinstance(contract_capability_evidence.get("proxy_checked"), list)
                else []
            ),
            "contract_capabilities_not_covered": len(
                contract_capability_evidence.get("not_covered", [])
                if isinstance(contract_capability_evidence.get("not_covered"), list)
                else []
            ),
            "metric_coverage_score": metric_coverage["summary"]["coverage_score"],
            "provider_auth_writable_backends": sum(1 for item in provider_auth_posture if item["api_key_ref_writable_backend"]),
            "provider_auth_plaintext_fallbacks": sum(1 for item in provider_auth_posture if item["api_key_ref_plaintext_fallback"]),
            "provider_auth_prewrite_policy_guards_recommended": sum(
                1 for item in provider_auth_posture if item["prewrite_policy_guard_recommended"]
            ),
            "provider_auth_keyring_required": sum(
                1 for entry in provider_audit["providers"] if entry.get("keyring_backend_required")
            ),
            "keyring_dependency_available": secret_backend_posture.get("keyring_dependency_available"),
            "blocking_findings": len(blocking_findings),
            "warnings": len(warnings),
        },
        "blocking_findings": blocking_findings,
        "warnings": warnings,
        "provider_auth_posture": provider_auth_posture,
        "secret_backend_posture": secret_backend_posture,
        "provider_audit": provider_audit,
        "suite_capabilities": capability_report,
        "contract_plan": contract_plan,
        "contract_capability_evidence": contract_capability_evidence,
        "metric_coverage": metric_coverage,
        "security_notes": [
            "Readiness dossier is static and does not contact endpoints, resolve secrets, or read raw traces.",
            "Contract checks are planned only; use providers contract-check --execute explicitly for live checks.",
            "Remote execution remains governed by policy and explicit allow-remote flags on execution commands.",
        ],
    }


def write_readiness_json(report: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def format_readiness_report(report: dict[str, Any]) -> str:
    lines = [
        "AgentBlaster benchmark readiness dossier",
        f"provider: {report['provider']}",
        f"suite: {report['suite']}",
        f"model: {report['model']}",
        f"ready: {str(report['ready']).lower()}",
        f"strict_unknown: {str(report['strict_unknown']).lower()}",
        "summary:",
    ]
    for key, value in report["summary"].items():
        lines.append(f"- {key}: {value}")
    lines.append("blocking_findings:")
    if not report["blocking_findings"]:
        lines.append("- none")
    else:
        for finding in report["blocking_findings"]:
            lines.append(f"- {finding['source']}:{finding['code']} {finding['message']}")
    lines.append("warnings:")
    if not report["warnings"]:
        lines.append("- none")
    else:
        for warning in report["warnings"]:
            lines.append(f"- {warning['source']}:{warning['code']} {warning['message']}")
    lines.append("provider_auth_posture:")
    auth_posture = report.get("provider_auth_posture", [])
    if not auth_posture:
        lines.append("- none")
    else:
        for posture in auth_posture:
            lines.append(
                f"- {posture['provider']}: "
                f"secret={posture['api_key_ref_kind'] or 'none'} "
                f"configured={_bool_text(posture['api_key_ref_configured'])} "
                f"writable={_bool_text(posture['api_key_ref_writable_backend'])} "
                f"plaintext={_bool_text(posture['api_key_ref_plaintext_fallback'])} "
                f"prewrite_policy_guard_recommended={_bool_text(posture['prewrite_policy_guard_recommended'])}"
            )
    secret_backend = report.get("secret_backend_posture") if isinstance(report.get("secret_backend_posture"), dict) else {}
    lines.append("secret_backend_posture:")
    if secret_backend:
        lines.append(f"- keyring_optional: {_bool_text(bool(secret_backend.get('keyring_optional')))}")
        lines.append(
            f"- keyring_dependency_available: {_bool_text(bool(secret_backend.get('keyring_dependency_available')))}"
        )
        lines.append(f"- recommended_enterprise_backends: {','.join(secret_backend.get('recommended_enterprise_backends', []) or [])}")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _provider_auth_posture(provider_audit: dict[str, Any]) -> list[dict[str, Any]]:
    posture: list[dict[str, Any]] = []
    for entry in provider_audit["providers"]:
        posture.append(
            {
                "provider": entry["name"],
                "api_key_ref_kind": entry["api_key_ref_kind"],
                "api_key_ref_configured": entry["api_key_ref_configured"],
                "api_key_ref_writable_backend": entry["api_key_ref_writable_backend"],
                "api_key_ref_plaintext_fallback": entry["api_key_ref_plaintext_fallback"],
                "prewrite_policy_guard_recommended": entry["prewrite_policy_guard_recommended"],
            }
        )
    return posture


def _compact_secret_backend_posture(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    supported = value.get("supported_secret_ref_kinds") if isinstance(value.get("supported_secret_ref_kinds"), list) else []
    recommended = (
        value.get("recommended_enterprise_backends") if isinstance(value.get("recommended_enterprise_backends"), list) else []
    )
    return {
        "env_reference_portable": bool(value.get("env_reference_portable")),
        "keyring_optional": bool(value.get("keyring_optional")),
        "keyring_dependency_available": bool(value.get("keyring_dependency_available")),
        "dotenv_plaintext_fallback_supported": bool(value.get("dotenv_plaintext_fallback_supported")),
        "dotenv_plaintext_fallback_enterprise_default": bool(value.get("dotenv_plaintext_fallback_enterprise_default")),
        "supported_secret_ref_kinds": [str(item) for item in supported[:6]],
        "recommended_enterprise_backends": [str(item) for item in recommended[:6]],
    }


def _bool_text(value: bool) -> str:
    return str(value).lower()


def _blocking_findings(
    provider_audit: dict[str, Any],
    capability_report: dict[str, Any],
    contract_plan: dict[str, Any],
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for entry in provider_audit["providers"]:
        for finding in entry["findings"]:
            if finding["severity"] == "error":
                findings.append({"source": "provider_audit", "code": finding["code"], "message": finding["message"]})
    for finding in capability_report["missing"]:
        findings.append({"source": "suite_capabilities", "code": f"missing_{finding['key']}", "message": finding["message"]})
    if capability_report["strict_unknown"]:
        for finding in capability_report["unknown"]:
            findings.append({"source": "suite_capabilities", "code": f"unknown_{finding['key']}", "message": finding["message"]})
    if contract_plan["model"] == "<required>":
        findings.append({"source": "contract_plan", "code": "model_required", "message": "model is required before executing contract or benchmark checks"})
    return findings


def _warnings(
    provider_audit: dict[str, Any],
    capability_report: dict[str, Any],
    metric_coverage: dict[str, Any],
    contract_plan: dict[str, Any],
) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    for entry in provider_audit["providers"]:
        for finding in entry["findings"]:
            if finding["severity"] == "warning":
                warnings.append({"source": "provider_audit", "code": finding["code"], "message": finding["message"]})
    if not capability_report["strict_unknown"]:
        for finding in capability_report["unknown"]:
            warnings.append({"source": "suite_capabilities", "code": f"unknown_{finding['key']}", "message": finding["message"]})
    capability_evidence = contract_plan.get("capability_evidence") if isinstance(contract_plan.get("capability_evidence"), dict) else {}
    not_covered = capability_evidence.get("not_covered") if isinstance(capability_evidence.get("not_covered"), list) else []
    for item in not_covered:
        if isinstance(item, dict) and item.get("capability"):
            capability = str(item["capability"])
            warnings.append(
                {
                    "source": "contract_capability_evidence",
                    "code": f"not_covered_{capability}",
                    "message": f"contract-check planning does not prove capability: {capability}",
                }
            )
    unavailable = [field["field"] for field in metric_coverage["fields"] if field["status"] == "unavailable"]
    if unavailable:
        warnings.append(
            {
                "source": "metric_coverage",
                "code": "unavailable_metrics",
                "message": "unavailable normalized metrics: " + ", ".join(sorted(unavailable)[:12]),
            }
        )
    return warnings
