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
    blocking_findings = _blocking_findings(provider_audit, capability_report, contract_plan)
    warnings = _warnings(provider_audit, capability_report, metric_coverage)
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
            "metric_coverage_score": metric_coverage["summary"]["coverage_score"],
            "blocking_findings": len(blocking_findings),
            "warnings": len(warnings),
        },
        "blocking_findings": blocking_findings,
        "warnings": warnings,
        "provider_audit": provider_audit,
        "suite_capabilities": capability_report,
        "contract_plan": contract_plan,
        "metric_coverage": metric_coverage,
        "security_notes": [
            "Readiness dossier is static and does not contact endpoints, resolve secrets, or read raw traces.",
            "Contract checks are planned only; use providers contract-check --execute explicitly for live checks.",
            "Remote execution remains governed by policy and explicit allow-remote flags on execution commands.",
        ],
    }


def write_readiness_json(report: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "
", encoding="utf-8")
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
    return "
".join(lines) + "
"


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
) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    for entry in provider_audit["providers"]:
        for finding in entry["findings"]:
            if finding["severity"] == "warning":
                warnings.append({"source": "provider_audit", "code": finding["code"], "message": finding["message"]})
    if not capability_report["strict_unknown"]:
        for finding in capability_report["unknown"]:
            warnings.append({"source": "suite_capabilities", "code": f"unknown_{finding['key']}", "message": finding["message"]})
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
