from __future__ import annotations

import httpx

from agentblaster.adapters import AnthropicCompatibleAdapter, OpenAICompatibleAdapter
from agentblaster.models import ApiContract, ProviderConfig, SecretRef
from agentblaster.secrets import EnvironmentSecretStore, SecretResolver


def test_openai_probe_normalizes_model_list_and_uses_bearer_auth(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_TEST_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={"data": [{"id": "qwen-test"}, {"id": "gemma-test"}]},
            headers={"content-type": "application/json"},
        )

    provider = ProviderConfig(
        name="openai-like",
        contract=ApiContract.OPENAI,
        base_url="https://example.com/v1",
        api_key_ref=SecretRef(kind="env", name="OPENAI_TEST_KEY"),
        remote=True,
    )
    adapter = OpenAICompatibleAdapter(
        provider,
        secrets=SecretResolver([EnvironmentSecretStore()]),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = adapter.probe()

    assert result.ok is True
    assert result.models == ["qwen-test", "gemma-test"]


def test_anthropic_probe_uses_x_api_key(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_TEST_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-api-key"] == "test-key"
        assert request.headers["anthropic-version"] == "2023-06-01"
        return httpx.Response(200, json={"data": [{"id": "claude-test"}]}, headers={"content-type": "application/json"})

    provider = ProviderConfig(
        name="anthropic-like",
        contract=ApiContract.ANTHROPIC,
        base_url="https://example.com/v1",
        api_key_ref=SecretRef(kind="env", name="ANTHROPIC_TEST_KEY"),
        remote=True,
    )
    adapter = AnthropicCompatibleAdapter(
        provider,
        secrets=SecretResolver([EnvironmentSecretStore()]),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = adapter.probe()

    assert result.ok is True
    assert result.models == ["claude-test"]
