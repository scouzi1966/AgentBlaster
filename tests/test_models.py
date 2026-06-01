from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentblaster.models import ApiContract, BenchmarkCase, ProviderConfig, SecretRef


def test_provider_accepts_env_secret_reference() -> None:
    provider = ProviderConfig(
        name="openai",
        contract=ApiContract.OPENAI,
        base_url="https://api.openai.com/v1",
        api_key_ref=SecretRef(kind="env", name="OPENAI_API_KEY"),
        metrics_url="https://metrics.example.com/metrics",
        remote=True,
    )

    assert provider.api_key_ref is not None
    assert provider.api_key_ref.display() == "env:OPENAI_API_KEY"
    assert str(provider.metrics_url).rstrip("/") == "https://metrics.example.com/metrics"


def test_provider_rejects_raw_auth_header() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            name="bad",
            contract=ApiContract.OPENAI,
            base_url="https://example.com/v1",
            headers={"Authorization": "Bearer sk-testshouldnotbehere1234567890"},
        )


def test_provider_rejects_metrics_url_with_credentials() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            name="bad-metrics",
            contract=ApiContract.OPENAI,
            base_url="https://example.com/v1",
            metrics_url="https://metrics.example.com/metrics?token=secret",
        )


def test_provider_rejects_base_url_with_credentials() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            name="bad-base",
            contract=ApiContract.OPENAI,
            base_url="https://user:password@example.com/v1",
        )


def test_provider_tls_settings_default_secure_and_reject_conflicts(tmp_path) -> None:
    provider = ProviderConfig(name="secure", contract=ApiContract.OPENAI, base_url="https://example.com/v1")

    assert provider.tls_verify is True
    assert provider.ca_bundle is None

    with pytest.raises(ValidationError, match="ca_bundle requires tls_verify"):
        ProviderConfig(
            name="bad-tls",
            contract=ApiContract.OPENAI,
            base_url="https://example.com/v1",
            tls_verify=False,
            ca_bundle=tmp_path / "ca.pem",
        )


def test_benchmark_case_accepts_prd_metadata_fields() -> None:
    case = BenchmarkCase(
        id="agent-loop",
        title="Agent loop",
        prompt="Use safe tools.",
        scenario="code edit loop",
        provenance="internal_regression",
        source_url="fixture://agentblaster/regressions/agent-loop",
        license="internal",
        risk_level="medium",
        mcp_profile="fixture-mcp",
        skills=["repo-triage"],
        metrics=["ttft_ms", "tokens_per_second_decode"],
        timeout_seconds=45.0,
    )

    assert case.provenance == "internal_regression"
    assert case.scenario == "code edit loop"
    assert case.risk_level == "medium"
    assert case.timeout_seconds == 45.0
