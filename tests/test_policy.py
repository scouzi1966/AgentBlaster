from __future__ import annotations

import pytest

from agentblaster.errors import PolicyError
from agentblaster.models import ApiContract, ProviderConfig, RawTraceMode
from agentblaster.policy import SecurityPolicy, enforce_provider_policy, load_policy, offline_policy


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


def test_load_policy_from_yaml(tmp_path) -> None:
    path = tmp_path / "agentblaster.policy.yaml"
    path.write_text(
        """
allowed_providers:
  - afm
allowed_base_url_hosts:
  - 127.0.0.1
allow_remote_providers: false
allow_full_raw_traces: false
""",
        encoding="utf-8",
    )

    policy = load_policy(path)

    assert policy.allowed_providers == {"afm"}
    assert policy.allowed_base_url_hosts == {"127.0.0.1"}
    assert policy.allow_remote_providers is False
