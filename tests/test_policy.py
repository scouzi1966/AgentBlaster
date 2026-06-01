from __future__ import annotations

import pytest

from agentblaster.errors import PolicyError
from agentblaster.models import ApiContract, BenchmarkCase, ProviderConfig, RawTraceMode, SuiteDefinition
from agentblaster.policy import (
    SecurityPolicy,
    enterprise_policy_template,
    enterprise_policy_template_yaml,
    enforce_dashboard_policy,
    enforce_matrix_policy,
    enforce_provider_policy,
    estimate_case_prompt_tokens,
    load_policy,
    offline_policy,
    policy_control_summary,
)


def test_policy_blocks_unlisted_provider() -> None:
    provider = ProviderConfig(name="openai", contract=ApiContract.OPENAI, base_url="https://api.openai.com/v1")
    policy = SecurityPolicy(allowed_providers={"afm"})

    with pytest.raises(PolicyError, match="provider is not allowed"):
        enforce_provider_policy(provider, policy, raw_trace_mode=RawTraceMode.REDACTED)


def test_offline_policy_blocks_remote_provider() -> None:
    provider = ProviderConfig(
        name="openai",
        contract=ApiContract.OPENAI,
        base_url="https://api.openai.com/v1",
        remote=True,
    )

    with pytest.raises(PolicyError, match="remote providers are disabled"):
        enforce_provider_policy(provider, offline_policy(), raw_trace_mode=RawTraceMode.REDACTED)


def test_policy_blocks_unlisted_host() -> None:
    provider = ProviderConfig(name="openai", contract=ApiContract.OPENAI, base_url="https://api.openai.com/v1")
    policy = SecurityPolicy(allowed_base_url_hosts={"gateway.example.com"})

    with pytest.raises(PolicyError, match="base URL host is not allowed"):
        enforce_provider_policy(provider, policy, raw_trace_mode=RawTraceMode.REDACTED)


def test_policy_blocks_non_loopback_http_provider_urls_by_default() -> None:
    provider = ProviderConfig(
        name="internal-gateway",
        contract=ApiContract.OPENAI,
        base_url="http://gateway.example.com/v1",
        api_key_ref={"kind": "env", "name": "GATEWAY_API_KEY"},
    )

    with pytest.raises(PolicyError, match="non-loopback HTTP provider base URLs"):
        enforce_provider_policy(provider, SecurityPolicy(), raw_trace_mode=RawTraceMode.REDACTED)

    enforce_provider_policy(
        provider,
        SecurityPolicy(allow_non_loopback_http_provider_urls=True),
        raw_trace_mode=RawTraceMode.REDACTED,
    )


def test_policy_blocks_insecure_tls_by_default() -> None:
    provider = ProviderConfig(
        name="openai",
        contract=ApiContract.OPENAI,
        base_url="https://api.openai.com/v1",
        tls_verify=False,
    )

    with pytest.raises(PolicyError, match="insecure TLS"):
        enforce_provider_policy(provider, SecurityPolicy(), raw_trace_mode=RawTraceMode.REDACTED)

    enforce_provider_policy(
        provider,
        SecurityPolicy(allow_insecure_tls=True),
        raw_trace_mode=RawTraceMode.REDACTED,
    )


def test_policy_allows_loopback_metrics_url_by_default() -> None:
    provider = ProviderConfig(
        name="local",
        contract=ApiContract.OPENAI,
        base_url="http://127.0.0.1:9999/v1",
        metrics_url="http://127.0.0.1:9999/metrics",
    )

    enforce_provider_policy(provider, SecurityPolicy(), raw_trace_mode=RawTraceMode.REDACTED)


def test_policy_blocks_remote_metrics_url_without_allowlist() -> None:
    provider = ProviderConfig(
        name="local",
        contract=ApiContract.OPENAI,
        base_url="http://127.0.0.1:9999/v1",
        metrics_url="https://metrics.example.com/metrics",
    )

    with pytest.raises(PolicyError, match="metrics URL host must be loopback"):
        enforce_provider_policy(provider, SecurityPolicy(), raw_trace_mode=RawTraceMode.REDACTED)


def test_policy_allows_allowlisted_remote_metrics_url() -> None:
    provider = ProviderConfig(
        name="local",
        contract=ApiContract.OPENAI,
        base_url="http://127.0.0.1:9999/v1",
        metrics_url="https://metrics.example.com/metrics",
    )
    policy = SecurityPolicy(allowed_metrics_url_hosts={"metrics.example.com"})

    enforce_provider_policy(provider, policy, raw_trace_mode=RawTraceMode.REDACTED)


def test_policy_blocks_non_loopback_http_metrics_url_even_when_allowlisted() -> None:
    provider = ProviderConfig(
        name="local",
        contract=ApiContract.OPENAI,
        base_url="http://127.0.0.1:9999/v1",
        metrics_url="http://metrics.example.com/metrics",
    )
    policy = SecurityPolicy(allowed_metrics_url_hosts={"metrics.example.com"})

    with pytest.raises(PolicyError, match="non-loopback HTTP metrics URLs"):
        enforce_provider_policy(provider, policy, raw_trace_mode=RawTraceMode.REDACTED)

    enforce_provider_policy(
        provider,
        SecurityPolicy(
            allowed_metrics_url_hosts={"metrics.example.com"},
            allow_non_loopback_http_metrics_urls=True,
        ),
        raw_trace_mode=RawTraceMode.REDACTED,
    )


def test_policy_blocks_disallowed_secret_reference_kind() -> None:
    provider = ProviderConfig(
        name="openai",
        contract=ApiContract.OPENAI,
        base_url="https://api.openai.com/v1",
        api_key_ref={"kind": "keyring", "name": "openai:api_key"},
        remote=True,
    )

    with pytest.raises(PolicyError, match="secret reference kind is not allowed"):
        enforce_provider_policy(
            provider,
            SecurityPolicy(allowed_secret_ref_kinds={"env"}),
            raw_trace_mode=RawTraceMode.REDACTED,
        )


def test_policy_blocks_disallowed_secret_reference_name_without_leaking_name() -> None:
    provider = ProviderConfig(
        name="openai",
        contract=ApiContract.OPENAI,
        base_url="https://api.openai.com/v1",
        api_key_ref={"kind": "env", "name": "WORKSPACE_OPENAI_API_KEY"},
        remote=True,
    )

    with pytest.raises(PolicyError, match="secret reference name is not allowed") as exc:
        enforce_provider_policy(
            provider,
            SecurityPolicy(allowed_secret_ref_names={"CI_OPENAI_API_KEY"}),
            raw_trace_mode=RawTraceMode.REDACTED,
        )
    assert "WORKSPACE_OPENAI_API_KEY" not in str(exc.value)


def test_policy_allows_secret_reference_name_prefixes() -> None:
    provider = ProviderConfig(
        name="openai",
        contract=ApiContract.OPENAI,
        base_url="https://api.openai.com/v1",
        api_key_ref={"kind": "env", "name": "AGENTBLASTER_OPENAI_API_KEY"},
        remote=True,
    )

    enforce_provider_policy(
        provider,
        SecurityPolicy(allowed_secret_ref_prefixes={"AGENTBLASTER_"}),
        raw_trace_mode=RawTraceMode.REDACTED,
    )


def test_policy_requires_api_key_reference_for_remote_provider_when_enabled() -> None:
    provider = ProviderConfig(
        name="remote-compatible",
        contract=ApiContract.OPENAI,
        base_url="https://gateway.example.com/v1",
        remote=True,
    )

    with pytest.raises(PolicyError, match="requires an API key reference"):
        enforce_provider_policy(
            provider,
            SecurityPolicy(require_api_key_for_remote_providers=True),
            raw_trace_mode=RawTraceMode.REDACTED,
        )


def test_policy_requires_remote_cost_model_and_rate_limits_when_enabled() -> None:
    provider = ProviderConfig(
        name="remote-compatible",
        contract=ApiContract.OPENAI,
        base_url="https://gateway.example.com/v1",
        remote=True,
    )

    with pytest.raises(PolicyError, match="requires a cost model"):
        enforce_provider_policy(
            provider,
            SecurityPolicy(require_cost_model_for_remote_providers=True),
            raw_trace_mode=RawTraceMode.REDACTED,
        )

    with pytest.raises(PolicyError, match="requires rate limits"):
        enforce_provider_policy(
            provider,
            SecurityPolicy(require_rate_limits_for_remote_providers=True),
            raw_trace_mode=RawTraceMode.REDACTED,
        )

    enforce_provider_policy(
        provider.model_copy(
            update={
                "cost_model": {"input_usd_per_1m_tokens": 1.0, "output_usd_per_1m_tokens": 2.0},
                "rate_limits": {"max_concurrency": 2, "requests_per_minute": 60},
            }
        ),
        SecurityPolicy(
            require_cost_model_for_remote_providers=True,
            require_rate_limits_for_remote_providers=True,
        ),
        raw_trace_mode=RawTraceMode.REDACTED,
    )


def test_policy_allows_remote_provider_with_approved_secret_reference_kind() -> None:
    provider = ProviderConfig(
        name="openai",
        contract=ApiContract.OPENAI,
        base_url="https://api.openai.com/v1",
        api_key_ref={"kind": "env", "name": "OPENAI_API_KEY"},
        remote=True,
    )

    enforce_provider_policy(
        provider,
        SecurityPolicy(
            allowed_secret_ref_kinds={"env"},
            require_api_key_for_remote_providers=True,
        ),
        raw_trace_mode=RawTraceMode.REDACTED,
    )


def test_policy_blocks_full_raw_traces_by_default() -> None:
    provider = ProviderConfig(name="local", contract=ApiContract.OPENAI, base_url="http://127.0.0.1:9999/v1")

    with pytest.raises(PolicyError, match="full raw traces"):
        enforce_provider_policy(provider, SecurityPolicy(), raw_trace_mode=RawTraceMode.FULL)


def test_policy_blocks_concurrency_above_limit() -> None:
    provider = ProviderConfig(name="local", contract=ApiContract.OPENAI, base_url="http://127.0.0.1:9999/v1")

    with pytest.raises(PolicyError, match="exceeds policy max_concurrency"):
        enforce_provider_policy(
            provider,
            SecurityPolicy(max_concurrency=2),
            raw_trace_mode=RawTraceMode.OFF,
            concurrency=4,
        )


def test_policy_blocks_concurrency_above_provider_rate_limit() -> None:
    provider = ProviderConfig(
        name="remote",
        contract=ApiContract.OPENAI,
        base_url="https://api.example.com/v1",
        rate_limits={"max_concurrency": 2},
    )

    with pytest.raises(PolicyError, match="provider rate_limits max_concurrency"):
        enforce_provider_policy(
            provider,
            SecurityPolicy(),
            raw_trace_mode=RawTraceMode.OFF,
            concurrency=4,
        )


def test_policy_blocks_suite_above_case_limit() -> None:
    provider = ProviderConfig(name="local", contract=ApiContract.OPENAI, base_url="http://127.0.0.1:9999/v1")
    suite = SuiteDefinition(
        name="suite",
        description="suite",
        cases=[
            BenchmarkCase(id="case-one", title="one", prompt="one"),
            BenchmarkCase(id="case-two", title="two", prompt="two"),
        ],
    )

    with pytest.raises(PolicyError, match="max_cases"):
        enforce_provider_policy(
            provider,
            SecurityPolicy(max_cases=1),
            raw_trace_mode=RawTraceMode.OFF,
            suite=suite,
        )


def test_policy_blocks_case_output_and_timeout_limits() -> None:
    provider = ProviderConfig(name="local", contract=ApiContract.OPENAI, base_url="http://127.0.0.1:9999/v1")
    suite = SuiteDefinition(
        name="suite",
        description="suite",
        cases=[
            BenchmarkCase(id="case-one", title="one", prompt="one", max_tokens=128, timeout_seconds=45.0),
        ],
    )

    with pytest.raises(PolicyError, match="max_output_tokens"):
        enforce_provider_policy(
            provider,
            SecurityPolicy(max_output_tokens=64),
            raw_trace_mode=RawTraceMode.OFF,
            suite=suite,
        )

    with pytest.raises(PolicyError, match="max_timeout_seconds"):
        enforce_provider_policy(
            provider,
            SecurityPolicy(max_timeout_seconds=30.0),
            raw_trace_mode=RawTraceMode.OFF,
            suite=suite,
        )


def test_policy_blocks_estimated_prompt_tokens() -> None:
    provider = ProviderConfig(name="local", contract=ApiContract.OPENAI, base_url="http://127.0.0.1:9999/v1")
    suite = SuiteDefinition(
        name="suite",
        description="suite",
        cases=[
            BenchmarkCase(id="case-one", title="one", prompt="x" * 200),
        ],
    )

    with pytest.raises(PolicyError, match="max_prompt_tokens"):
        enforce_provider_policy(
            provider,
            SecurityPolicy(max_prompt_tokens=10),
            raw_trace_mode=RawTraceMode.OFF,
            suite=suite,
        )


def test_policy_blocks_estimated_run_cost_above_limit() -> None:
    provider = ProviderConfig(
        name="openai",
        contract=ApiContract.OPENAI,
        base_url="https://api.openai.com/v1",
        remote=True,
        cost_model={"input_usd_per_1m_tokens": 1000.0, "output_usd_per_1m_tokens": 1000.0},
    )
    suite = SuiteDefinition(
        name="suite",
        description="suite",
        cases=[
            BenchmarkCase(id="case-one", title="one", prompt="x" * 400, max_tokens=100),
        ],
    )

    with pytest.raises(PolicyError, match="max_estimated_run_cost_usd"):
        enforce_provider_policy(
            provider,
            SecurityPolicy(max_estimated_run_cost_usd=0.01),
            raw_trace_mode=RawTraceMode.OFF,
            suite=suite,
        )


def test_dashboard_policy_blocks_unlisted_host_and_port() -> None:
    with pytest.raises(PolicyError, match="dashboard host is not allowed"):
        enforce_dashboard_policy(
            SecurityPolicy(allowed_dashboard_hosts={"localhost"}),
            host="127.0.0.1",
            port=8765,
            allow_non_loopback=False,
            auth_configured=False,
        )

    with pytest.raises(PolicyError, match="dashboard port is not allowed"):
        enforce_dashboard_policy(
            SecurityPolicy(allowed_dashboard_ports={8765}),
            host="localhost",
            port=9000,
            allow_non_loopback=False,
            auth_configured=False,
        )


def test_dashboard_policy_can_require_auth_on_loopback() -> None:
    with pytest.raises(PolicyError, match="authentication is required"):
        enforce_dashboard_policy(
            SecurityPolicy(require_dashboard_auth=True),
            host="127.0.0.1",
            port=8765,
            allow_non_loopback=False,
            auth_configured=False,
        )

    enforce_dashboard_policy(
        SecurityPolicy(require_dashboard_auth=True),
        host="127.0.0.1",
        port=8765,
        allow_non_loopback=False,
        auth_configured=True,
    )


def test_dashboard_policy_requires_policy_and_cli_opt_in_for_non_loopback() -> None:
    with pytest.raises(PolicyError, match="non-loopback dashboard binding is disabled"):
        enforce_dashboard_policy(
            SecurityPolicy(),
            host="0.0.0.0",
            port=8765,
            allow_non_loopback=True,
            auth_configured=True,
        )

    with pytest.raises(PolicyError, match="explicit CLI opt-in"):
        enforce_dashboard_policy(
            SecurityPolicy(allow_dashboard_non_loopback=True),
            host="0.0.0.0",
            port=8765,
            allow_non_loopback=False,
            auth_configured=True,
        )

    enforce_dashboard_policy(
        SecurityPolicy(allow_dashboard_non_loopback=True, require_dashboard_auth=True),
        host="0.0.0.0",
        port=8765,
        allow_non_loopback=True,
        auth_configured=True,
    )


def test_policy_requires_cost_model_when_cost_ceiling_is_enabled() -> None:
    provider = ProviderConfig(name="openai", contract=ApiContract.OPENAI, base_url="https://api.openai.com/v1")
    suite = SuiteDefinition(
        name="suite",
        description="suite",
        cases=[BenchmarkCase(id="case-one", title="one", prompt="one")],
    )

    with pytest.raises(PolicyError, match="cost_model"):
        enforce_provider_policy(
            provider,
            SecurityPolicy(max_estimated_case_cost_usd=0.01),
            raw_trace_mode=RawTraceMode.OFF,
            suite=suite,
        )


def test_estimate_case_prompt_tokens_includes_mcp_and_tool_schemas() -> None:
    plain_case = BenchmarkCase(id="plain", title="plain", prompt="hello")
    mcp_case = BenchmarkCase(id="mcp", title="mcp", prompt="hello", mcp_profile="wide-mcp-32")
    skill_case = BenchmarkCase(
        id="skill",
        title="skill",
        prompt="hello",
        skills=["large-prefix-diagnostic"],
    )

    assert estimate_case_prompt_tokens(mcp_case) > estimate_case_prompt_tokens(plain_case)
    assert estimate_case_prompt_tokens(skill_case) > estimate_case_prompt_tokens(plain_case)


def test_estimate_case_prompt_tokens_includes_trace_messages() -> None:
    plain_case = BenchmarkCase(id="plain", title="plain", prompt="hello")
    trace_case = BenchmarkCase(
        id="trace",
        title="trace",
        prompt="hello",
        messages=[
            {"role": "system", "content": "Trace policy."},
            {"role": "user", "content": "Read fixture context."},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "read_file_fixture", "arguments": '{"path":"/repo/src/app.py"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "agentblaster-ok"},
        ],
    )

    assert estimate_case_prompt_tokens(trace_case) > estimate_case_prompt_tokens(plain_case)


def test_load_policy_from_yaml(tmp_path) -> None:
    path = tmp_path / "agentblaster.policy.yaml"
    path.write_text(
        """
allowed_providers:
  - afm
allowed_base_url_hosts:
  - 127.0.0.1
allowed_metrics_url_hosts:
  - 127.0.0.1
allowed_secret_ref_names:
  - CI_OPENAI_API_KEY
allowed_secret_ref_prefixes:
  - AGENTBLASTER_
allow_remote_providers: false
require_cost_model_for_remote_providers: true
require_rate_limits_for_remote_providers: true
allow_non_loopback_http_provider_urls: true
allow_non_loopback_http_metrics_urls: true
allow_full_raw_traces: false
allow_insecure_tls: true
max_cases: 5
max_output_tokens: 128
max_timeout_seconds: 60
max_estimated_run_cost_usd: 0.25
""",
        encoding="utf-8",
    )

    policy = load_policy(path)

    assert policy.allowed_providers == {"afm"}
    assert policy.allowed_base_url_hosts == {"127.0.0.1"}
    assert policy.allowed_metrics_url_hosts == {"127.0.0.1"}
    assert policy.allowed_secret_ref_names == {"CI_OPENAI_API_KEY"}
    assert policy.allowed_secret_ref_prefixes == {"AGENTBLASTER_"}
    assert policy.allow_remote_providers is False
    assert policy.require_cost_model_for_remote_providers is True
    assert policy.require_rate_limits_for_remote_providers is True
    assert policy.allow_non_loopback_http_provider_urls is True
    assert policy.allow_non_loopback_http_metrics_urls is True
    assert policy.allow_insecure_tls is True
    assert policy.max_cases == 5
    assert policy.max_output_tokens == 128
    assert policy.max_timeout_seconds == 60
    assert policy.max_estimated_run_cost_usd == 0.25


def test_enterprise_policy_template_excludes_plaintext_secret_backends() -> None:
    payload = enterprise_policy_template(profile="remote-gateway")
    policy = payload["policy"]

    assert payload["schema_version"] == "agentblaster.enterprise-policy-template.v1"
    assert payload["profile"] == "remote-gateway"
    assert policy["allow_remote_providers"] is True
    assert policy["require_api_key_for_remote_providers"] is True
    assert policy["require_cost_model_for_remote_providers"] is True
    assert policy["require_rate_limits_for_remote_providers"] is True
    assert "dotenv" not in policy["allowed_secret_ref_kinds"]
    assert "gateway.example.com" in policy["allowed_base_url_hosts"]
    assert "allowed_secret_ref_kinds" in enterprise_policy_template_yaml(profile="local")


def test_policy_control_summary_flags_enterprise_blockers() -> None:
    summary = policy_control_summary(
        SecurityPolicy(
            allow_remote_providers=True,
            require_api_key_for_remote_providers=False,
            allow_full_raw_traces=True,
            allow_insecure_tls=True,
            require_dashboard_auth=False,
            allowed_secret_ref_kinds={"env", "dotenv"},
        ),
        name="unsafe",
    )

    assert summary["schema_version"] == "agentblaster.policy-control-summary.v1"
    assert summary["enterprise_ready"] is False
    assert "remote providers allowed without API-key requirement" in summary["blockers"]
    assert "full raw traces allowed" in summary["blockers"]
    assert "plaintext dotenv secret backend allowed" in summary["blockers"]
    assert summary["security"]["contains_secrets"] is False


def _policy_test_provider() -> ProviderConfig:
    return ProviderConfig(name="local", contract=ApiContract.OPENAI, base_url="http://127.0.0.1:9999/v1")


def _suite_with_case(case: BenchmarkCase) -> SuiteDefinition:
    return SuiteDefinition(name="suite", description="suite", cases=[case])


def test_policy_blocks_tool_schemas_when_disabled_or_unlisted() -> None:
    case = BenchmarkCase(
        id="tool-policy-case",
        title="tool policy case",
        prompt="Use the offered tool.",
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "read_repository",
                    "description": "Read repository metadata from a benchmark fixture.",
                    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                },
            }
        ],
    )

    with pytest.raises(PolicyError, match="tool schemas are disabled"):
        enforce_provider_policy(
            _policy_test_provider(),
            SecurityPolicy(allow_tool_schemas=False),
            raw_trace_mode=RawTraceMode.OFF,
            suite=_suite_with_case(case),
        )

    with pytest.raises(PolicyError, match="tool schema not allowed"):
        enforce_provider_policy(
            _policy_test_provider(),
            SecurityPolicy(allowed_tool_names={"search_docs"}),
            raw_trace_mode=RawTraceMode.OFF,
            suite=_suite_with_case(case),
        )


def test_policy_blocks_unnamed_tool_schema_when_tool_allowlist_is_enabled() -> None:
    case = BenchmarkCase(
        id="unnamed-tool-policy-case",
        title="unnamed tool policy case",
        prompt="Use the offered tool.",
        tools=[{"type": "function", "function": {"parameters": {"type": "object"}}}],
    )

    with pytest.raises(PolicyError, match="unnamed tool schema"):
        enforce_provider_policy(
            _policy_test_provider(),
            SecurityPolicy(allowed_tool_names={"search_docs"}),
            raw_trace_mode=RawTraceMode.OFF,
            suite=_suite_with_case(case),
        )


def test_policy_blocks_simulated_tools_when_disabled_or_unlisted() -> None:
    case = BenchmarkCase(
        id="simulated-tool-policy-case",
        title="simulated tool policy case",
        prompt="Use the deterministic fixture tool.",
        simulated_tools=["search_docs"],
    )

    with pytest.raises(PolicyError, match="simulated tools are disabled"):
        enforce_provider_policy(
            _policy_test_provider(),
            SecurityPolicy(allow_simulated_tools=False),
            raw_trace_mode=RawTraceMode.OFF,
            suite=_suite_with_case(case),
        )

    with pytest.raises(PolicyError, match="simulated tool not allowed"):
        enforce_provider_policy(
            _policy_test_provider(),
            SecurityPolicy(allowed_simulated_tools={"read_file_fixture"}),
            raw_trace_mode=RawTraceMode.OFF,
            suite=_suite_with_case(case),
        )


def test_policy_blocks_mcp_profiles_when_disabled_or_unlisted() -> None:
    case = BenchmarkCase(
        id="mcp-policy-case",
        title="mcp policy case",
        prompt="Use the deterministic MCP fixture profile.",
        mcp_profile="fixture-mcp",
    )

    with pytest.raises(PolicyError, match="MCP profiles are disabled"):
        enforce_provider_policy(
            _policy_test_provider(),
            SecurityPolicy(allow_mcp_profiles=False),
            raw_trace_mode=RawTraceMode.OFF,
            suite=_suite_with_case(case),
        )

    with pytest.raises(PolicyError, match="MCP profile not allowed"):
        enforce_provider_policy(
            _policy_test_provider(),
            SecurityPolicy(allowed_mcp_profiles={"wide-mcp-32"}),
            raw_trace_mode=RawTraceMode.OFF,
            suite=_suite_with_case(case),
        )


def test_policy_blocks_skills_when_disabled_or_unlisted() -> None:
    case = BenchmarkCase(
        id="skill-policy-case",
        title="skill policy case",
        prompt="Use the requested skill pack.",
        skills=["safe-tool-replay"],
    )

    with pytest.raises(PolicyError, match="skills are disabled"):
        enforce_provider_policy(
            _policy_test_provider(),
            SecurityPolicy(allow_skills=False),
            raw_trace_mode=RawTraceMode.OFF,
            suite=_suite_with_case(case),
        )

    with pytest.raises(PolicyError, match="skill not allowed"):
        enforce_provider_policy(
            _policy_test_provider(),
            SecurityPolicy(allowed_skills={"repo-triage"}),
            raw_trace_mode=RawTraceMode.OFF,
            suite=_suite_with_case(case),
        )


def test_policy_allows_approved_capability_surfaces() -> None:
    case = BenchmarkCase(
        id="approved-capability-policy-case",
        title="approved capability policy case",
        prompt="Use approved deterministic capability surfaces.",
        tools=[{"type": "function", "function": {"name": "case_tool", "parameters": {"type": "object"}}}],
        simulated_tools=["search_docs"],
        mcp_profile="fixture-mcp",
        skills=["safe-tool-replay"],
    )

    enforce_provider_policy(
        _policy_test_provider(),
        SecurityPolicy(
            allowed_tool_names={"case_tool"},
            allowed_simulated_tools={"search_docs"},
            allowed_mcp_profiles={"fixture-mcp"},
            allowed_skills={"safe-tool-replay"},
        ),
        raw_trace_mode=RawTraceMode.OFF,
        suite=_suite_with_case(case),
    )


def test_policy_requires_tool_cases_to_declare_max_tool_calls_when_enabled() -> None:
    case = BenchmarkCase(
        id="unbounded-tool-case",
        title="unbounded tool case",
        prompt="Use the deterministic fixture tool.",
        simulated_tools=["search_docs"],
    )

    with pytest.raises(PolicyError, match="does not declare max_tool_calls"):
        enforce_provider_policy(
            _policy_test_provider(),
            SecurityPolicy(require_max_tool_calls_for_tool_cases=True),
            raw_trace_mode=RawTraceMode.OFF,
            suite=_suite_with_case(case),
        )


def test_policy_blocks_tool_case_above_max_tool_call_limit() -> None:
    case = BenchmarkCase(
        id="tool-loop-case",
        title="tool loop case",
        prompt="Use bounded deterministic tool calls.",
        simulated_tools=["search_docs"],
        max_tool_calls=9,
    )

    with pytest.raises(PolicyError, match="max_tool_calls_per_case"):
        enforce_provider_policy(
            _policy_test_provider(),
            SecurityPolicy(max_tool_calls_per_case=8),
            raw_trace_mode=RawTraceMode.OFF,
            suite=_suite_with_case(case),
        )


def test_policy_allows_tool_case_with_approved_tool_call_bound() -> None:
    case = BenchmarkCase(
        id="bounded-tool-case",
        title="bounded tool case",
        prompt="Use bounded deterministic tool calls.",
        simulated_tools=["search_docs"],
        max_tool_calls=2,
    )

    enforce_provider_policy(
        _policy_test_provider(),
        SecurityPolicy(require_max_tool_calls_for_tool_cases=True, max_tool_calls_per_case=8),
        raw_trace_mode=RawTraceMode.OFF,
        suite=_suite_with_case(case),
    )


def test_policy_blocks_matrix_above_aggregate_limits() -> None:
    with pytest.raises(PolicyError, match="max_matrix_runs"):
        enforce_matrix_policy(
            SecurityPolicy(max_matrix_runs=1),
            matrix_name="too-large",
            total_runs=2,
            total_cases=2,
        )

    with pytest.raises(PolicyError, match="max_matrix_total_cases"):
        enforce_matrix_policy(
            SecurityPolicy(max_matrix_total_cases=2),
            matrix_name="too-many-cases",
            total_runs=1,
            total_cases=3,
        )


def test_policy_allows_matrix_within_aggregate_limits() -> None:
    enforce_matrix_policy(
        SecurityPolicy(max_matrix_runs=2, max_matrix_total_cases=4),
        matrix_name="approved-matrix",
        total_runs=2,
        total_cases=4,
    )


def test_policy_blocks_matrix_above_estimated_cost_limit() -> None:
    with pytest.raises(PolicyError, match="max_estimated_matrix_cost_usd"):
        enforce_matrix_policy(
            SecurityPolicy(max_estimated_matrix_cost_usd=0.01),
            matrix_name="costly-matrix",
            total_runs=2,
            total_cases=2,
            estimated_cost_usd=0.02,
        )


def test_policy_allows_matrix_within_estimated_cost_limit() -> None:
    enforce_matrix_policy(
        SecurityPolicy(max_estimated_matrix_cost_usd=0.03),
        matrix_name="approved-cost-matrix",
        total_runs=2,
        total_cases=2,
        estimated_cost_usd=0.02,
    )


def test_policy_blocks_external_cases_missing_required_source_or_license() -> None:
    case = BenchmarkCase(
        id="external-governance-case",
        title="external governance case",
        prompt="Answer from an adapted public benchmark case.",
        provenance="public_benchmark_adapted",
    )

    with pytest.raises(PolicyError, match="requires source_url"):
        enforce_provider_policy(
            _policy_test_provider(),
            SecurityPolicy(require_source_url_for_external_cases=True),
            raw_trace_mode=RawTraceMode.OFF,
            suite=_suite_with_case(case),
        )

    with pytest.raises(PolicyError, match="requires license"):
        enforce_provider_policy(
            _policy_test_provider(),
            SecurityPolicy(require_license_for_external_cases=True),
            raw_trace_mode=RawTraceMode.OFF,
            suite=_suite_with_case(case),
        )


def test_policy_allows_external_cases_with_required_source_and_license() -> None:
    case = BenchmarkCase(
        id="reviewed-external-case",
        title="reviewed external case",
        prompt="Answer from a reviewed adapted public benchmark case.",
        provenance="public_benchmark_adapted",
        source_url="https://example.test/benchmark-case",
        license="CC-BY-4.0",
    )

    enforce_provider_policy(
        _policy_test_provider(),
        SecurityPolicy(
            require_source_url_for_external_cases=True,
            require_license_for_external_cases=True,
        ),
        raw_trace_mode=RawTraceMode.OFF,
        suite=_suite_with_case(case),
    )


def test_policy_blocks_unapproved_case_provenance_and_risk() -> None:
    high_risk_case = BenchmarkCase(
        id="high-risk-case",
        title="high risk case",
        prompt="Handle sensitive workflow content.",
        risk_level="high",
    )
    external_case = BenchmarkCase(
        id="primary-source-case",
        title="primary source case",
        prompt="Answer from a primary-source case.",
        provenance="primary_source",
        source_url="https://example.test/source",
        license="MIT",
    )

    with pytest.raises(PolicyError, match="high-risk cases are disabled"):
        enforce_provider_policy(
            _policy_test_provider(),
            SecurityPolicy(allow_high_risk_cases=False),
            raw_trace_mode=RawTraceMode.OFF,
            suite=_suite_with_case(high_risk_case),
        )

    with pytest.raises(PolicyError, match="risk level is not allowed"):
        enforce_provider_policy(
            _policy_test_provider(),
            SecurityPolicy(allowed_case_risk_levels={"low", "medium"}),
            raw_trace_mode=RawTraceMode.OFF,
            suite=_suite_with_case(high_risk_case),
        )

    with pytest.raises(PolicyError, match="provenance is not allowed"):
        enforce_provider_policy(
            _policy_test_provider(),
            SecurityPolicy(allowed_case_provenance={"synthetic_representative", "internal_regression"}),
            raw_trace_mode=RawTraceMode.OFF,
            suite=_suite_with_case(external_case),
        )

def test_policy_blocks_disallowed_lcp_profile() -> None:
    provider = ProviderConfig(name="local", contract=ApiContract.OPENAI, base_url="http://127.0.0.1:9999/v1")
    suite = SuiteDefinition(
        name="suite",
        description="suite",
        cases=[BenchmarkCase(id="case-one", title="one", prompt="one", lcp_profile="fixture-lcp")],
    )

    with pytest.raises(PolicyError, match="LCP profiles are disabled"):
        enforce_provider_policy(provider, SecurityPolicy(allow_lcp_profiles=False), raw_trace_mode=RawTraceMode.OFF, suite=suite)

    with pytest.raises(PolicyError, match="LCP profile not allowed"):
        enforce_provider_policy(
            provider,
            SecurityPolicy(allowed_lcp_profiles={"wide-lcp-context"}),
            raw_trace_mode=RawTraceMode.OFF,
            suite=suite,
        )

    enforce_provider_policy(
        provider,
        SecurityPolicy(allowed_lcp_profiles={"fixture-lcp"}),
        raw_trace_mode=RawTraceMode.OFF,
        suite=suite,
    )
