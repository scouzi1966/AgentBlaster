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


def test_openai_smoke_chat_posts_chat_completion(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_TEST_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == "https://example.com/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"
        payload = request.read().decode()
        assert "qwen-test" in payload
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "agentblaster-ok"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            },
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

    response = adapter.smoke_chat("qwen-test")

    assert response.status_code == 200
    assert response.text == "agentblaster-ok"


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


def test_anthropic_smoke_chat_posts_messages(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_TEST_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == "https://example.com/v1/messages"
        assert request.headers["x-api-key"] == "test-key"
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "agentblaster-ok"}],
                "usage": {"input_tokens": 7, "output_tokens": 2},
            },
            headers={"content-type": "application/json"},
        )

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

    response = adapter.smoke_chat("claude-test")

    assert response.status_code == 200
    assert response.text == "agentblaster-ok"
