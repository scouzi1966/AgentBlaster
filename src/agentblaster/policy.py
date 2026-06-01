from __future__ import annotations

import json
from ipaddress import ip_address
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from agentblaster.costs import estimate_costs
from agentblaster.errors import ConfigError, PolicyError
from agentblaster.lcp import lcp_profile_text
from agentblaster.mcp import mcp_profile_tool_schemas
from agentblaster.models import BenchmarkCase, ProviderConfig, RawTraceMode, SecretRef, SuiteDefinition
from agentblaster.rate_limits import rate_limit_max_concurrency
from agentblaster.skills import skill_prefix
from agentblaster.toolsim import simulated_tool_schemas


ENTERPRISE_POLICY_TEMPLATE_SCHEMA_VERSION = "agentblaster.enterprise-policy-template.v1"
POLICY_CONTROL_SUMMARY_SCHEMA_VERSION = "agentblaster.policy-control-summary.v1"


class SecurityPolicy(BaseModel):
    """Enterprise policy controls enforced before benchmark execution."""

    model_config = ConfigDict(extra="forbid")

    allowed_providers: set[str] | None = None
    allowed_base_url_hosts: set[str] | None = None
    allowed_metrics_url_hosts: set[str] | None = None
    allowed_secret_ref_kinds: set[Literal["env", "keyring", "dotenv"]] | None = None
    allowed_secret_ref_names: set[str] | None = None
    allowed_secret_ref_prefixes: set[str] | None = None
    allow_remote_providers: bool = True
    require_api_key_for_remote_providers: bool = False
    require_cost_model_for_remote_providers: bool = False
    require_rate_limits_for_remote_providers: bool = False
    allow_non_loopback_http_provider_urls: bool = False
    allow_non_loopback_http_metrics_urls: bool = False
    allow_full_raw_traces: bool = False
    allow_insecure_tls: bool = False
    allow_tool_schemas: bool = True
    allowed_tool_names: set[str] | None = None
    allow_simulated_tools: bool = True
    allowed_simulated_tools: set[str] | None = None
    allow_mcp_profiles: bool = True
    allowed_mcp_profiles: set[str] | None = None
    allow_lcp_profiles: bool = True
    allowed_lcp_profiles: set[str] | None = None
    allow_skills: bool = True
    allowed_skills: set[str] | None = None
    require_max_tool_calls_for_tool_cases: bool = False
    max_tool_calls_per_case: int | None = Field(default=None, ge=1)
    allowed_case_provenance: set[str] | None = None
    allowed_case_risk_levels: set[Literal["low", "medium", "high"]] | None = None
    allow_high_risk_cases: bool = True
    require_source_url_for_external_cases: bool = False
    require_license_for_external_cases: bool = False
    max_prompt_tokens: int | None = Field(default=None, ge=1)
    max_concurrency: int | None = Field(default=None, ge=1)
    max_cases: int | None = Field(default=None, ge=1)
    max_matrix_runs: int | None = Field(default=None, ge=1)
    max_matrix_total_cases: int | None = Field(default=None, ge=1)
    max_output_tokens: int | None = Field(default=None, ge=1)
    max_timeout_seconds: float | None = Field(default=None, gt=0.0)
    max_estimated_case_cost_usd: float | None = Field(default=None, ge=0.0)
    max_estimated_run_cost_usd: float | None = Field(default=None, ge=0.0)
    max_estimated_matrix_cost_usd: float | None = Field(default=None, ge=0.0)
    allowed_dashboard_hosts: set[str] | None = None
    allowed_dashboard_ports: set[int] | None = None
    allow_dashboard_non_loopback: bool = False
    require_dashboard_auth: bool = False
    require_cleanup_audit_log: bool = False

    @field_validator("allowed_secret_ref_names", "allowed_secret_ref_prefixes")
    @classmethod
    def reject_empty_secret_ref_policy_values(cls, value: set[str] | None) -> set[str] | None:
        if value is not None and any(not item for item in value):
            raise ValueError("secret reference policy names and prefixes must be non-empty")
        return value


def load_policy(path: Path | None) -> SecurityPolicy:
    if path is None:
        return SecurityPolicy()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return SecurityPolicy.model_validate(data)
    except (OSError, ValidationError, yaml.YAMLError) as exc:
        raise ConfigError(f"invalid policy file at {path}: {exc}") from exc


def enterprise_policy_template(*, profile: Literal["local", "remote-gateway"] = "local") -> dict[str, Any]:
    """Return a redaction-safe corporate baseline policy template."""

    remote_enabled = profile == "remote-gateway"
    policy = SecurityPolicy(
        allowed_providers={
            "afm",
            "mlx-lm",
            "ollama",
            "ollama-native",
            "lm-studio",
            "lm-studio-responses",
            "lm-studio-native",
            "omlx",
            "rapid-mlx",
            "vllm-mlx",
            "openai-compatible-remote",
            "anthropic-compatible-remote",
        },
        allowed_base_url_hosts={"127.0.0.1", "localhost"} if not remote_enabled else {"127.0.0.1", "localhost", "gateway.example.com"},
        allowed_metrics_url_hosts={"127.0.0.1", "localhost"},
        allowed_secret_ref_kinds={"env", "keyring"},
        allowed_secret_ref_prefixes={"AGENTBLASTER_", "OPENAI_", "ANTHROPIC_", "WORKSPACE_", "afm:", "lm-studio:", "openai", "anthropic"},
        allow_remote_providers=remote_enabled,
        require_api_key_for_remote_providers=True,
        require_cost_model_for_remote_providers=True,
        require_rate_limits_for_remote_providers=True,
        allow_non_loopback_http_provider_urls=False,
        allow_non_loopback_http_metrics_urls=False,
        allow_full_raw_traces=False,
        allow_insecure_tls=False,
        allow_tool_schemas=True,
        allow_simulated_tools=True,
        allowed_simulated_tools={"search_docs", "read_file_fixture", "shell_fixture", "browser_fetch_fixture", "mcp_echo"},
        allow_mcp_profiles=True,
        allowed_mcp_profiles={"fixture-mcp", "wide-mcp-32"},
        allow_lcp_profiles=True,
        allowed_lcp_profiles={"fixture-lcp", "wide-lcp-context"},
        allow_skills=True,
        allowed_skills={"repo-triage", "safe-tool-replay", "agent-planning", "large-prefix-diagnostic"},
        require_max_tool_calls_for_tool_cases=True,
        max_tool_calls_per_case=8,
        allowed_case_provenance={
            "synthetic_representative",
            "internal_regression",
            "customer_trace_sanitized",
            "primary_source",
            "public_benchmark_adapted",
        },
        allowed_case_risk_levels={"low", "medium"},
        allow_high_risk_cases=False,
        require_source_url_for_external_cases=True,
        require_license_for_external_cases=True,
        max_concurrency=8,
        max_cases=500,
        max_matrix_runs=25,
        max_matrix_total_cases=2500,
        max_output_tokens=4096,
        max_timeout_seconds=600,
        max_estimated_matrix_cost_usd=25.0 if remote_enabled else None,
        allowed_dashboard_hosts={"127.0.0.1", "localhost"},
        allowed_dashboard_ports={8765},
        allow_dashboard_non_loopback=False,
        require_dashboard_auth=True,
        require_cleanup_audit_log=True,
    )
    return {
        "schema_version": ENTERPRISE_POLICY_TEMPLATE_SCHEMA_VERSION,
        "profile": profile,
        "policy": policy.model_dump(mode="json", exclude_none=True),
        "review_notes": [
            "Template stores only policy controls, never API-key values.",
            "Keyring/Apple Keychain is optional; env references remain the portable enterprise baseline.",
            "Dotenv plaintext fallback is intentionally excluded from the enterprise baseline.",
            "Replace gateway.example.com with approved corporate API gateway hosts before enabling remote providers.",
        ],
    }


def enterprise_policy_template_yaml(*, profile: Literal["local", "remote-gateway"] = "local") -> str:
    return yaml.safe_dump(enterprise_policy_template(profile=profile)["policy"], sort_keys=True)


def policy_control_summary(policy: SecurityPolicy, *, name: str = "policy") -> dict[str, Any]:
    """Return a compact review artifact for enterprise policy posture."""

    controls = {
        "provider_allowlist": policy.allowed_providers is not None,
        "provider_host_allowlist": policy.allowed_base_url_hosts is not None,
        "metrics_host_allowlist": policy.allowed_metrics_url_hosts is not None,
        "remote_providers_allowed": policy.allow_remote_providers,
        "remote_api_key_required": policy.require_api_key_for_remote_providers,
        "remote_cost_model_required": policy.require_cost_model_for_remote_providers,
        "remote_rate_limits_required": policy.require_rate_limits_for_remote_providers,
        "non_loopback_http_provider_urls_allowed": policy.allow_non_loopback_http_provider_urls,
        "non_loopback_http_metrics_urls_allowed": policy.allow_non_loopback_http_metrics_urls,
        "insecure_tls_allowed": policy.allow_insecure_tls,
        "full_raw_traces_allowed": policy.allow_full_raw_traces,
        "secret_backend_restricted": policy.allowed_secret_ref_kinds is not None,
        "secret_name_restricted": policy.allowed_secret_ref_names is not None or policy.allowed_secret_ref_prefixes is not None,
        "dashboard_auth_required": policy.require_dashboard_auth,
        "dashboard_non_loopback_allowed": policy.allow_dashboard_non_loopback,
        "cleanup_audit_log_required": policy.require_cleanup_audit_log,
        "suite_capability_surfaces_restricted": any(
            value is not None
            for value in (
                policy.allowed_tool_names,
                policy.allowed_simulated_tools,
                policy.allowed_mcp_profiles,
                policy.allowed_lcp_profiles,
                policy.allowed_skills,
            )
        ),
        "tool_call_bounds_required": policy.require_max_tool_calls_for_tool_cases or policy.max_tool_calls_per_case is not None,
        "case_governance_restricted": any(
            value is not None
            for value in (
                policy.allowed_case_provenance,
                policy.allowed_case_risk_levels,
            )
        )
        or not policy.allow_high_risk_cases
        or policy.require_source_url_for_external_cases
        or policy.require_license_for_external_cases,
        "cost_ceilings_configured": any(
            value is not None
            for value in (
                policy.max_estimated_case_cost_usd,
                policy.max_estimated_run_cost_usd,
                policy.max_estimated_matrix_cost_usd,
            )
        ),
        "scale_ceilings_configured": any(
            value is not None
            for value in (
                policy.max_prompt_tokens,
                policy.max_concurrency,
                policy.max_cases,
                policy.max_matrix_runs,
                policy.max_matrix_total_cases,
                policy.max_output_tokens,
                policy.max_timeout_seconds,
            )
        ),
    }
    blockers = [
        name
        for name, unsafe in {
            "remote providers allowed without API-key requirement": policy.allow_remote_providers and not policy.require_api_key_for_remote_providers,
            "remote providers allowed without cost-model requirement": policy.allow_remote_providers and not policy.require_cost_model_for_remote_providers,
            "remote providers allowed without rate-limit requirement": policy.allow_remote_providers and not policy.require_rate_limits_for_remote_providers,
            "non-loopback HTTP provider URLs allowed": policy.allow_non_loopback_http_provider_urls,
            "non-loopback HTTP metrics URLs allowed": policy.allow_non_loopback_http_metrics_urls,
            "insecure TLS allowed": policy.allow_insecure_tls,
            "full raw traces allowed": policy.allow_full_raw_traces,
            "dashboard auth not required": not policy.require_dashboard_auth,
            "cleanup audit log not required": not policy.require_cleanup_audit_log,
            "plaintext dotenv secret backend allowed": policy.allowed_secret_ref_kinds is not None and "dotenv" in policy.allowed_secret_ref_kinds,
            "high-risk cases allowed": policy.allow_high_risk_cases,
        }.items()
        if unsafe
    ]
    warnings = [
        name
        for name, weak in {
            "provider allowlist not configured": policy.allowed_providers is None,
            "provider host allowlist not configured": policy.allowed_base_url_hosts is None,
            "metrics host allowlist not configured": policy.allowed_metrics_url_hosts is None,
            "secret backend restriction not configured": policy.allowed_secret_ref_kinds is None,
            "secret name/prefix restriction not configured": policy.allowed_secret_ref_names is None and policy.allowed_secret_ref_prefixes is None,
            "cost ceilings not configured": not controls["cost_ceilings_configured"],
            "scale ceilings not configured": not controls["scale_ceilings_configured"],
            "suite capability surface allowlists not configured": not controls["suite_capability_surfaces_restricted"],
        }.items()
        if weak
    ]
    return {
        "schema_version": POLICY_CONTROL_SUMMARY_SCHEMA_VERSION,
        "name": name,
        "enterprise_ready": not blockers,
        "summary": {
            "control_count": len(controls),
            "enabled_controls": sum(1 for value in controls.values() if value),
            "blockers": len(blockers),
            "warnings": len(warnings),
        },
        "controls": controls,
        "blockers": blockers,
        "warnings": warnings,
        "security": {
            "contains_secrets": False,
            "contains_raw_provider_payloads": False,
            "resolves_secret_references": False,
            "contacts_providers": False,
        },
    }


def enforce_provider_policy(
    provider: ProviderConfig,
    policy: SecurityPolicy,
    *,
    raw_trace_mode: RawTraceMode,
    concurrency: int = 1,
    suite: SuiteDefinition | None = None,
) -> None:
    if policy.allowed_providers is not None and provider.name not in policy.allowed_providers:
        raise PolicyError(f"provider is not allowed by policy: {provider.name}")

    if provider.remote and not policy.allow_remote_providers:
        raise PolicyError(f"remote providers are disabled by policy: {provider.name}")

    if provider.remote and policy.require_api_key_for_remote_providers and provider.api_key_ref is None:
        raise PolicyError(f"remote provider requires an API key reference by policy: {provider.name}")

    if provider.remote and policy.require_cost_model_for_remote_providers and not provider.cost_model:
        raise PolicyError(f"remote provider requires a cost model by policy: {provider.name}")

    if provider.remote and policy.require_rate_limits_for_remote_providers and not provider.rate_limits:
        raise PolicyError(f"remote provider requires rate limits by policy: {provider.name}")

    if provider.api_key_ref is not None and policy.allowed_secret_ref_kinds is not None:
        if provider.api_key_ref.kind not in policy.allowed_secret_ref_kinds:
            raise PolicyError(
                f"secret reference kind is not allowed by policy for provider {provider.name}: "
                f"{provider.api_key_ref.kind}"
            )

    if provider.api_key_ref is not None and not _secret_ref_name_allowed(provider.api_key_ref, policy):
        raise PolicyError(f"secret reference name is not allowed by policy for provider {provider.name}")

    if not provider.tls_verify and not policy.allow_insecure_tls:
        raise PolicyError(f"insecure TLS is disabled by policy: {provider.name}")

    parsed_base_url = urlparse(str(provider.base_url))
    host = parsed_base_url.hostname
    if policy.allowed_base_url_hosts is not None and host not in policy.allowed_base_url_hosts:
        raise PolicyError(f"base URL host is not allowed by policy: {host}")
    if (
        parsed_base_url.scheme == "http"
        and host is not None
        and not _is_loopback_host(host)
        and not policy.allow_non_loopback_http_provider_urls
    ):
        raise PolicyError(f"non-loopback HTTP provider base URLs are disabled by policy: {host}")

    parsed_metrics_url = urlparse(str(provider.metrics_url)) if provider.metrics_url is not None else None
    metrics_host = parsed_metrics_url.hostname if parsed_metrics_url is not None else None
    if metrics_host is not None:
        if policy.allowed_metrics_url_hosts is not None:
            if metrics_host not in policy.allowed_metrics_url_hosts:
                raise PolicyError(f"metrics URL host is not allowed by policy: {metrics_host}")
        elif not _is_loopback_host(metrics_host):
            raise PolicyError(f"metrics URL host must be loopback or explicitly allowlisted by policy: {metrics_host}")
        if (
            parsed_metrics_url is not None
            and parsed_metrics_url.scheme == "http"
            and not _is_loopback_host(metrics_host)
            and not policy.allow_non_loopback_http_metrics_urls
        ):
            raise PolicyError(f"non-loopback HTTP metrics URLs are disabled by policy: {metrics_host}")

    if raw_trace_mode is RawTraceMode.FULL and not policy.allow_full_raw_traces:
        raise PolicyError("full raw traces are disabled by policy")

    if policy.max_concurrency is not None and concurrency > policy.max_concurrency:
        raise PolicyError(f"concurrency {concurrency} exceeds policy max_concurrency {policy.max_concurrency}")

    provider_max_concurrency = rate_limit_max_concurrency(provider.rate_limits)
    if provider_max_concurrency is not None and concurrency > provider_max_concurrency:
        raise PolicyError(
            f"concurrency {concurrency} exceeds provider rate_limits max_concurrency {provider_max_concurrency}"
        )

    if suite is not None:
        enforce_suite_policy(provider, policy, suite)


def enforce_suite_policy(provider: ProviderConfig, policy: SecurityPolicy, suite: SuiteDefinition) -> None:
    if policy.max_cases is not None and len(suite.cases) > policy.max_cases:
        raise PolicyError(f"suite has {len(suite.cases)} cases, exceeding policy max_cases {policy.max_cases}")

    estimated_run_cost = 0.0
    saw_estimated_cost = False
    for case in suite.cases:
        enforce_case_governance_policy(policy, case)
        enforce_case_capability_policy(policy, case)
        estimated_prompt_tokens = estimate_case_prompt_tokens(case)
        if policy.max_prompt_tokens is not None and estimated_prompt_tokens > policy.max_prompt_tokens:
            raise PolicyError(
                f"case {case.id} estimated prompt tokens {estimated_prompt_tokens} "
                f"exceed policy max_prompt_tokens {policy.max_prompt_tokens}"
            )
        if policy.max_output_tokens is not None and case.max_tokens > policy.max_output_tokens:
            raise PolicyError(
                f"case {case.id} max_tokens {case.max_tokens} exceeds policy max_output_tokens {policy.max_output_tokens}"
            )
        if policy.max_timeout_seconds is not None and case.timeout_seconds > policy.max_timeout_seconds:
            raise PolicyError(
                f"case {case.id} timeout_seconds {case.timeout_seconds} "
                f"exceeds policy max_timeout_seconds {policy.max_timeout_seconds}"
            )

        if policy.max_estimated_case_cost_usd is not None or policy.max_estimated_run_cost_usd is not None:
            if not provider.cost_model:
                raise PolicyError("policy cost ceilings require provider.cost_model")
            case_cost = estimate_costs(
                provider.cost_model,
                input_tokens=estimated_prompt_tokens,
                output_tokens=case.max_tokens,
            )["total_cost_usd"]
            if case_cost is None:
                raise PolicyError("policy cost ceilings require input/output rates in provider.cost_model")
            saw_estimated_cost = True
            estimated_run_cost += case_cost
            if policy.max_estimated_case_cost_usd is not None and case_cost > policy.max_estimated_case_cost_usd:
                raise PolicyError(
                    f"case {case.id} estimated cost ${case_cost:.9f} "
                    f"exceeds policy max_estimated_case_cost_usd ${policy.max_estimated_case_cost_usd:.9f}"
                )

    if (
        policy.max_estimated_run_cost_usd is not None
        and saw_estimated_cost
        and estimated_run_cost > policy.max_estimated_run_cost_usd
    ):
        raise PolicyError(
            f"suite estimated cost ${estimated_run_cost:.9f} "
            f"exceeds policy max_estimated_run_cost_usd ${policy.max_estimated_run_cost_usd:.9f}"
        )


def _secret_ref_name_allowed(ref: SecretRef, policy: SecurityPolicy) -> bool:
    names = policy.allowed_secret_ref_names
    prefixes = policy.allowed_secret_ref_prefixes
    if names is None and prefixes is None:
        return True
    if names is not None and ref.name in names:
        return True
    if prefixes is not None and any(ref.name.startswith(prefix) for prefix in prefixes):
        return True
    return False


def enforce_matrix_policy(
    policy: SecurityPolicy,
    *,
    matrix_name: str,
    total_runs: int,
    total_cases: int,
    estimated_cost_usd: float | None = None,
) -> None:
    if policy.max_matrix_runs is not None and total_runs > policy.max_matrix_runs:
        raise PolicyError(
            f"matrix {matrix_name} has {total_runs} runs, "
            f"exceeding policy max_matrix_runs {policy.max_matrix_runs}"
        )

    if policy.max_matrix_total_cases is not None and total_cases > policy.max_matrix_total_cases:
        raise PolicyError(
            f"matrix {matrix_name} has {total_cases} total cases, "
            f"exceeding policy max_matrix_total_cases {policy.max_matrix_total_cases}"
        )

    if (
        policy.max_estimated_matrix_cost_usd is not None
        and estimated_cost_usd is not None
        and estimated_cost_usd > policy.max_estimated_matrix_cost_usd
    ):
        raise PolicyError(
            f"matrix {matrix_name} estimated cost ${estimated_cost_usd:.9f} "
            f"exceeds policy max_estimated_matrix_cost_usd ${policy.max_estimated_matrix_cost_usd:.9f}"
        )


def enforce_case_governance_policy(policy: SecurityPolicy, case: BenchmarkCase) -> None:
    if policy.allowed_case_provenance is not None and case.provenance not in policy.allowed_case_provenance:
        raise PolicyError(f"case {case.id} provenance is not allowed by policy: {case.provenance}")

    if policy.allowed_case_risk_levels is not None and case.risk_level not in policy.allowed_case_risk_levels:
        raise PolicyError(f"case {case.id} risk level is not allowed by policy: {case.risk_level}")

    if case.risk_level == "high" and not policy.allow_high_risk_cases:
        raise PolicyError(f"case {case.id} is high risk, but high-risk cases are disabled by policy")

    if case.provenance in {"primary_source", "public_benchmark_adapted"}:
        if policy.require_source_url_for_external_cases and not case.source_url:
            raise PolicyError(f"case {case.id} requires source_url by policy")
        if policy.require_license_for_external_cases and not case.license:
            raise PolicyError(f"case {case.id} requires license by policy")


def enforce_case_capability_policy(policy: SecurityPolicy, case: BenchmarkCase) -> None:
    """Enforce suite-supplied capability surfaces before any provider dispatch."""

    has_tool_surface = bool(case.tools or case.simulated_tools or case.mcp_profile)

    if case.tools:
        if not policy.allow_tool_schemas:
            raise PolicyError(f"case {case.id} uses tool schemas, but tool schemas are disabled by policy")
        if policy.allowed_tool_names is not None:
            for tool in case.tools:
                tool_name = _tool_schema_name(tool)
                if tool_name is None:
                    raise PolicyError(
                        f"case {case.id} includes an unnamed tool schema, "
                        "but policy allowed_tool_names requires named tools"
                    )
                if tool_name not in policy.allowed_tool_names:
                    raise PolicyError(f"case {case.id} uses tool schema not allowed by policy: {tool_name}")

    if case.simulated_tools:
        if not policy.allow_simulated_tools:
            raise PolicyError(
                f"case {case.id} uses simulated tools, but simulated tools are disabled by policy"
            )
        if policy.allowed_simulated_tools is not None:
            for tool_name in case.simulated_tools:
                if tool_name not in policy.allowed_simulated_tools:
                    raise PolicyError(f"case {case.id} uses simulated tool not allowed by policy: {tool_name}")

    if case.mcp_profile is not None:
        if not policy.allow_mcp_profiles:
            raise PolicyError(f"case {case.id} uses MCP profile {case.mcp_profile}, but MCP profiles are disabled")
        if policy.allowed_mcp_profiles is not None and case.mcp_profile not in policy.allowed_mcp_profiles:
            raise PolicyError(f"case {case.id} uses MCP profile not allowed by policy: {case.mcp_profile}")

    if case.lcp_profile is not None:
        if not policy.allow_lcp_profiles:
            raise PolicyError(f"case {case.id} uses LCP profile {case.lcp_profile}, but LCP profiles are disabled")
        if policy.allowed_lcp_profiles is not None and case.lcp_profile not in policy.allowed_lcp_profiles:
            raise PolicyError(f"case {case.id} uses LCP profile not allowed by policy: {case.lcp_profile}")

    if case.skills:
        if not policy.allow_skills:
            raise PolicyError(f"case {case.id} uses skills, but skills are disabled by policy")
        if policy.allowed_skills is not None:
            for skill_name in case.skills:
                if skill_name not in policy.allowed_skills:
                    raise PolicyError(f"case {case.id} uses skill not allowed by policy: {skill_name}")

    if has_tool_surface and policy.require_max_tool_calls_for_tool_cases and case.max_tool_calls is None:
        raise PolicyError(f"case {case.id} uses tool surfaces but does not declare max_tool_calls")

    if (
        policy.max_tool_calls_per_case is not None
        and case.max_tool_calls is not None
        and case.max_tool_calls > policy.max_tool_calls_per_case
    ):
        raise PolicyError(
            f"case {case.id} max_tool_calls {case.max_tool_calls} "
            f"exceeds policy max_tool_calls_per_case {policy.max_tool_calls_per_case}"
        )


def enforce_dashboard_policy(
    policy: SecurityPolicy,
    *,
    host: str,
    port: int,
    allow_non_loopback: bool,
    auth_configured: bool,
) -> None:
    normalized_host = _normalize_host(host)
    if policy.allowed_dashboard_hosts is not None and normalized_host not in {
        _normalize_host(allowed_host) for allowed_host in policy.allowed_dashboard_hosts
    }:
        raise PolicyError(f"dashboard host is not allowed by policy: {normalized_host}")

    if policy.allowed_dashboard_ports is not None and port not in policy.allowed_dashboard_ports:
        raise PolicyError(f"dashboard port is not allowed by policy: {port}")

    if policy.require_dashboard_auth and not auth_configured:
        raise PolicyError("dashboard authentication is required by policy")

    if not _is_loopback_host(host):
        if not policy.allow_dashboard_non_loopback:
            raise PolicyError("non-loopback dashboard binding is disabled by policy")
        if not allow_non_loopback:
            raise PolicyError("non-loopback dashboard binding requires explicit CLI opt-in")


def estimate_case_prompt_tokens(case: BenchmarkCase) -> int:
    parts: list[str] = []
    if case.system_prompt:
        parts.append(case.system_prompt)
    if case.cache_control:
        parts.append(json.dumps(case.cache_control, sort_keys=True, separators=(",", ":")))
    parts.append(case.prompt)
    if case.messages:
        parts.append(
            json.dumps(
                [message.model_dump(mode="json", exclude_none=True) for message in case.messages],
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    tools = list(case.tools)
    if case.simulated_tools:
        tools.extend(simulated_tool_schemas(case.simulated_tools))
    if case.mcp_profile:
        tools.extend(mcp_profile_tool_schemas(case.mcp_profile))
    if case.lcp_profile:
        parts.append(lcp_profile_text(case.lcp_profile))
    if tools:
        parts.append(json.dumps(tools, sort_keys=True, separators=(",", ":")))
    if case.skills:
        parts.append(skill_prefix(case.skills))
    text = "\n".join(parts)
    return max(1, (len(text) + 3) // 4)


def offline_policy() -> SecurityPolicy:
    return SecurityPolicy(allow_remote_providers=False)


def _is_loopback_host(host: str) -> bool:
    normalized = _normalize_host(host)
    if normalized == "localhost":
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def _normalize_host(host: str) -> str:
    return host.strip().lower().strip("[]")


def _tool_schema_name(tool: dict[str, Any]) -> str | None:
    function = tool.get("function")
    if isinstance(function, dict):
        name = function.get("name")
        if isinstance(name, str) and name:
            return name
    name = tool.get("name")
    if isinstance(name, str) and name:
        return name
    return None
