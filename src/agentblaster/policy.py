from __future__ import annotations

import json
from ipaddress import ip_address
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agentblaster.costs import estimate_costs
from agentblaster.errors import ConfigError, PolicyError
from agentblaster.lcp import lcp_profile_text
from agentblaster.mcp import mcp_profile_tool_schemas
from agentblaster.models import BenchmarkCase, ProviderConfig, RawTraceMode, SuiteDefinition
from agentblaster.rate_limits import rate_limit_max_concurrency
from agentblaster.skills import skill_prefix
from agentblaster.toolsim import simulated_tool_schemas


class SecurityPolicy(BaseModel):
    """Enterprise policy controls enforced before benchmark execution."""

    model_config = ConfigDict(extra="forbid")

    allowed_providers: set[str] | None = None
    allowed_base_url_hosts: set[str] | None = None
    allowed_metrics_url_hosts: set[str] | None = None
    allowed_secret_ref_kinds: set[Literal["env", "keyring"]] | None = None
    allow_remote_providers: bool = True
    require_api_key_for_remote_providers: bool = False
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


def load_policy(path: Path | None) -> SecurityPolicy:
    if path is None:
        return SecurityPolicy()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return SecurityPolicy.model_validate(data)
    except (OSError, ValidationError, yaml.YAMLError) as exc:
        raise ConfigError(f"invalid policy file at {path}: {exc}") from exc


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

    if provider.api_key_ref is not None and policy.allowed_secret_ref_kinds is not None:
        if provider.api_key_ref.kind not in policy.allowed_secret_ref_kinds:
            raise PolicyError(
                f"secret reference kind is not allowed by policy for provider {provider.name}: "
                f"{provider.api_key_ref.kind}"
            )

    if not provider.tls_verify and not policy.allow_insecure_tls:
        raise PolicyError(f"insecure TLS is disabled by policy: {provider.name}")

    host = urlparse(str(provider.base_url)).hostname
    if policy.allowed_base_url_hosts is not None and host not in policy.allowed_base_url_hosts:
        raise PolicyError(f"base URL host is not allowed by policy: {host}")

    metrics_host = urlparse(str(provider.metrics_url)).hostname if provider.metrics_url is not None else None
    if metrics_host is not None:
        if policy.allowed_metrics_url_hosts is not None:
            if metrics_host not in policy.allowed_metrics_url_hosts:
                raise PolicyError(f"metrics URL host is not allowed by policy: {metrics_host}")
        elif not _is_loopback_host(metrics_host):
            raise PolicyError(f"metrics URL host must be loopback or explicitly allowlisted by policy: {metrics_host}")

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
