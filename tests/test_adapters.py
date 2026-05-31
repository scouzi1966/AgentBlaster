from __future__ import annotations

import httpx

from agentblaster.adapters import (
    AnthropicCompatibleAdapter,
    OllamaNativeAdapter,
    OpenAICompatibleAdapter,
    adapter_for,
    extract_openai_tool_names,
)
from agentblaster.models import ApiContract, BenchmarkCase, ProviderConfig, SecretRef
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


def test_openai_chat_completion_sends_tools_and_response_format() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json_loads_request(request)
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["tools"][0]["function"]["name"] == "ping_agentblaster"
        assert payload["tool_choice"]["function"]["name"] == "ping_agentblaster"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "ping_agentblaster", "arguments": "{}"},
                                }
                            ],
                        }
                    }
                ]
            },
            headers={"content-type": "application/json"},
        )

    provider = ProviderConfig(name="openai-like", contract=ApiContract.OPENAI, base_url="https://example.com/v1")
    adapter = OpenAICompatibleAdapter(provider, client=httpx.Client(transport=httpx.MockTransport(handler)))
    case = BenchmarkCase(
        id="toolcase",
        title="tool case",
        prompt="Use tool",
        expected_tool_name="ping_agentblaster",
        response_format={"type": "json_object"},
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "ping_agentblaster",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        tool_choice={"type": "function", "function": {"name": "ping_agentblaster"}},
    )

    response = adapter.chat_completion("qwen-test", case)

    assert response.tool_names == ["ping_agentblaster"]


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


def test_anthropic_chat_completion_converts_openai_tool_schema() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json_loads_request(request)
        assert payload["tools"][0]["name"] == "ping_agentblaster"
        assert payload["tools"][0]["input_schema"]["type"] == "object"
        assert payload["tool_choice"]["name"] == "ping_agentblaster"
        return httpx.Response(
            200,
            json={"content": [{"type": "tool_use", "name": "ping_agentblaster", "input": {}}]},
            headers={"content-type": "application/json"},
        )

    provider = ProviderConfig(name="anthropic-like", contract=ApiContract.ANTHROPIC, base_url="https://example.com/v1")
    adapter = AnthropicCompatibleAdapter(provider, client=httpx.Client(transport=httpx.MockTransport(handler)))
    case = BenchmarkCase(
        id="toolcase",
        title="tool case",
        prompt="Use tool",
        expected_tool_name="ping_agentblaster",
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "ping_agentblaster",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        tool_choice={"type": "function", "function": {"name": "ping_agentblaster"}},
    )

    response = adapter.chat_completion("claude-test", case)

    assert response.tool_names == ["ping_agentblaster"]


def test_extract_openai_tool_names_ignores_malformed_blocks() -> None:
    assert extract_openai_tool_names({"choices": [{"message": {"tool_calls": [{"function": {"name": "x"}}]}}]}) == [
        "x"
    ]
    assert extract_openai_tool_names({"choices": [{"message": {"tool_calls": [{"function": {}}]}}]}) == []


def test_ollama_native_probe_reads_tags() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://example.com/api/tags"
        return httpx.Response(
            200,
            json={"models": [{"name": "qwen-test"}, {"model": "gemma-test"}]},
            headers={"content-type": "application/json"},
        )

    provider = ProviderConfig(
        name="ollama-native",
        contract=ApiContract.NATIVE,
        base_url="http://example.com",
        native_adapter="ollama",
    )
    adapter = OllamaNativeAdapter(provider, client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = adapter.probe()

    assert result.ok is True
    assert result.models == ["qwen-test", "gemma-test"]


def test_ollama_native_chat_posts_api_chat_and_extracts_metrics() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://example.com/api/chat"
        payload = json_loads_request(request)
        assert payload["stream"] is False
        assert payload["options"]["num_predict"] == 16
        assert payload["messages"][0]["content"] == "Reply with exactly: agentblaster-ok"
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": "agentblaster-ok"},
                "prompt_eval_count": 10,
                "prompt_eval_duration": 100_000_000,
                "eval_count": 5,
                "eval_duration": 50_000_000,
                "load_duration": 25_000_000,
            },
            headers={"content-type": "application/json"},
        )

    provider = ProviderConfig(
        name="ollama-native",
        contract=ApiContract.NATIVE,
        base_url="http://example.com",
        native_adapter="ollama",
    )
    adapter = OllamaNativeAdapter(provider, client=httpx.Client(transport=httpx.MockTransport(handler)))

    response = adapter.smoke_chat("qwen-test")

    assert response.status_code == 200
    assert response.text == "agentblaster-ok"
    assert response.raw["eval_count"] == 5


def test_adapter_for_resolves_ollama_native_adapter() -> None:
    provider = ProviderConfig(
        name="ollama-native",
        contract=ApiContract.NATIVE,
        base_url="http://example.com",
        native_adapter="ollama",
    )

    assert isinstance(adapter_for(provider), OllamaNativeAdapter)


def json_loads_request(request: httpx.Request):
    import json

    return json.loads(request.read().decode())
