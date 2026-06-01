from __future__ import annotations

import json
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from agentblaster.errors import PolicyError
from agentblaster.models import ProviderConfig, RawTraceMode
from agentblaster.policy import SecurityPolicy, enforce_provider_policy


class ProviderAuditFinding(BaseModel):
    """Redacted provider governance finding."""

    model_config = ConfigDict(extra="forbid")

    severity: str
    code: str
    message: str


class ProviderAuditEntry(BaseModel):
    """Redacted provider audit entry."""

    model_config = ConfigDict(extra="forbid")

    name: str
    contract: str
    base_url_host: str | None = None
    remote: bool
    api_key_ref_kind: str | None = None
    api_key_ref_configured: bool
    metrics_url_host: str | None = None
    tls_verify: bool
    ca_bundle_configured: bool
    cost_model_configured: bool
    rate_limits_configured: bool
    capabilities_declared: list[str] = Field(default_factory=list)
    policy_ok: bool
    findings: list[ProviderAuditFinding] = Field(default_factory=list)


class ProviderAuditReport(BaseModel):
    """Static redacted provider inventory and policy audit."""

    model_config = ConfigDict(extra="forbid")

    total_providers: int
    remote_providers: int
    policy_ok: int
    errors: int
    warnings: int
    providers: list[ProviderAuditEntry] = Field(default_factory=list)
    security_notes: list[str] = Field(default_factory=list)


def audit_providers(providers: list[ProviderConfig], policy: SecurityPolicy) -> ProviderAuditReport:
    entries = [_audit_provider(provider, policy) for provider in providers]
    return ProviderAuditReport(
        total_providers=len(entries),
        remote_providers=sum(1 for entry in entries if entry.remote),
        policy_ok=sum(1 for entry in entries if entry.policy_ok),
        errors=sum(1 for entry in entries for finding in entry.findings if finding.severity == "error"),
        warnings=sum(1 for entry in entries for finding in entry.findings if finding.severity == "warning"),
        providers=entries,
        security_notes=[
            "Provider audit is static and does not contact endpoints, resolve API keys, read environment variables, or inspect keyring values.",
            "Secret references are reported by backend kind only; raw secret names and values are excluded from JSON output.",
        ],
    )


def format_provider_audit(report: ProviderAuditReport) -> str:
    lines = [
        f"total_providers: {report.total_providers}",
        f"remote_providers: {report.remote_providers}",
        f"policy_ok: {report.policy_ok}/{report.total_providers}",
        f"errors: {report.errors}",
        f"warnings: {report.warnings}",
    ]
    for entry in report.providers:
        status = "ok" if entry.policy_ok else "blocked"
        lines.append(
            f"{entry.name}	{entry.contract}	remote={str(entry.remote).lower()}	"
            f"host={entry.base_url_host or 'none'}	secret={entry.api_key_ref_kind or 'none'}	{status}"
        )
        for finding in entry.findings:
            lines.append(f"{entry.name}	{finding.severity}	{finding.code}	{finding.message}")
    return "\n".join(lines) + "\n"


def provider_audit_json(report: ProviderAuditReport) -> str:
    return json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def _audit_provider(provider: ProviderConfig, policy: SecurityPolicy) -> ProviderAuditEntry:
    findings: list[ProviderAuditFinding] = []
    policy_ok = True
    try:
        enforce_provider_policy(
            provider,
            policy,
            raw_trace_mode=RawTraceMode.REDACTED,
            concurrency=1,
            suite=None,
        )
    except PolicyError as exc:
        policy_ok = False
        findings.append(
            ProviderAuditFinding(
                severity="error",
                code="policy_violation",
                message=str(exc),
            )
        )

    if provider.remote and provider.api_key_ref is None:
        findings.append(
            ProviderAuditFinding(
                severity="warning",
                code="remote_without_api_key_ref",
                message="remote provider has no API-key reference configured",
            )
        )
    if provider.remote and not provider.cost_model:
        findings.append(
            ProviderAuditFinding(
                severity="warning",
                code="remote_without_cost_model",
                message="remote provider has no cost model for budget policy",
            )
        )
    if provider.remote and not provider.rate_limits:
        findings.append(
            ProviderAuditFinding(
                severity="warning",
                code="remote_without_rate_limits",
                message="remote provider has no rate limits for request pacing",
            )
        )
    if not provider.tls_verify:
        findings.append(
            ProviderAuditFinding(
                severity="warning",
                code="insecure_tls",
                message="provider disables TLS verification",
            )
        )

    return ProviderAuditEntry(
        name=provider.name,
        contract=provider.contract.value,
        base_url_host=urlparse(str(provider.base_url)).hostname,
        remote=provider.remote,
        api_key_ref_kind=provider.api_key_ref.kind if provider.api_key_ref else None,
        api_key_ref_configured=provider.api_key_ref is not None,
        metrics_url_host=urlparse(str(provider.metrics_url)).hostname if provider.metrics_url else None,
        tls_verify=provider.tls_verify,
        ca_bundle_configured=provider.ca_bundle is not None,
        cost_model_configured=bool(provider.cost_model),
        rate_limits_configured=bool(provider.rate_limits),
        capabilities_declared=sorted(provider.capabilities),
        policy_ok=policy_ok,
        findings=findings,
    )
