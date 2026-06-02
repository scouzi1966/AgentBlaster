from __future__ import annotations

import httpx

import agentblaster.adapters as adapters_module
from agentblaster.adapters import (
    AnthropicCompatibleAdapter,
    LMStudioNativeAdapter,
    OllamaNativeAdapter,
    OpenAICompatibleAdapter,
    OpenAIResponsesAdapter,
    adapter_for,
    extract_openai_tool_names,
    httpx_verify_config,
)
from agentblaster.constants import SMOKE_SENTINEL_MAX_TOKENS, SMOKE_SENTINEL_PROMPT, SMOKE_SENTINEL_SYSTEM_PROMPT
from agentblaster.models import ApiContract, BenchmarkCase, ProviderConfig, SecretRef
from agentblaster.secrets import EnvironmentSecretStore, SecretResolver


def test_httpx_verify_config_reflects_provider_tls_settings(tmp_path) -> None:
    secure = ProviderConfig(name="secure", contract=ApiContract.OPENAI, base_url="https://example.com/v1")
    insecure = ProviderConfig(
        name="insecure",
        contract=ApiContract.OPENAI,
        base_url="https://example.com/v1",
        tls_verify=False,
    )
    ca_bundle = tmp_path / "enterprise-ca.pem"
    custom_ca = ProviderConfig(
        name="custom-ca",
        contract=ApiContract.OPENAI,
        base_url="https://example.com/v1",
        ca_bundle=ca_bundle,
    )

    assert httpx_verify_config(secure) is True
    assert httpx_verify_config(insecure) is False
    assert httpx_verify_config(custom_ca) == str(ca_bundle)


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


def test_probe_failure_messages_redact_secret_echoes(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_TEST_KEY", "sk-secret-that-should-not-leak-1234567890")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            text="denied Authorization: Bearer sk-secret-that-should-not-leak-1234567890",
            headers={"content-type": "text/plain"},
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

    assert result.ok is False
    assert "sk-secret" not in result.message
    assert "Bearer [REDACTED]" in result.message


def test_openai_chat_completion_preserves_safe_http_metadata_for_json_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "agentblaster-ok"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            },
            headers={
                "content-type": "application/problem+json; charset=utf-8",
                "x-request-id": "req_123",
                "authorization": "Bearer should-not-render",
            },
        )

    provider = ProviderConfig(name="openai-like", contract=ApiContract.OPENAI, base_url="https://example.com/v1")
    adapter = OpenAICompatibleAdapter(provider, client=httpx.Client(transport=httpx.MockTransport(handler)))

    response = adapter.smoke_chat("qwen-test")

    assert response.raw["usage"]["prompt_tokens"] == 5
    assert response.raw["agentblaster_http"]["status_code"] == 200
    assert response.raw["agentblaster_http"]["content_type"] == "application/problem+json; charset=utf-8"
    assert response.raw["agentblaster_http"]["headers"] == {"x-request-id": "req_123"}


def test_openai_chat_completion_preserves_redacted_non_json_error_metadata() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            502,
            text="upstream gateway failed with token sk-should-not-render",
            headers={
                "content-type": "text/plain",
                "retry-after": "2",
                "set-cookie": "session=should-not-render",
            },
        )

    provider = ProviderConfig(name="openai-like", contract=ApiContract.OPENAI, base_url="https://example.com/v1")
    adapter = OpenAICompatibleAdapter(provider, client=httpx.Client(transport=httpx.MockTransport(handler)))
    case = BenchmarkCase(id="errorcase", title="error case", prompt="hello")

    response = adapter.chat_completion("qwen-test", case)

    assert response.status_code == 502
    assert response.raw["agentblaster_non_json_response"] is True
    assert response.raw["agentblaster_http"]["status_code"] == 502
    assert response.raw["agentblaster_http"]["headers"] == {"retry-after": "2"}
    assert "sk-should-not-render" not in response.raw["agentblaster_body_preview"]
    assert "set-cookie" not in response.raw["agentblaster_http"]["headers"]


def test_openai_chat_completion_sends_tools_and_response_format() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json_loads_request(request)
        assert request.extensions["timeout"]["read"] == 12.5
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
        timeout_seconds=12.5,
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
    assert response.tool_calls[0].arguments == {}


def test_openai_chat_completion_replays_explicit_trace_messages() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json_loads_request(request)
        assert [message["role"] for message in payload["messages"]] == [
            "system",
            "user",
            "assistant",
            "tool",
            "user",
        ]
        assert payload["messages"][2]["tool_calls"][0]["function"]["name"] == "read_file_fixture"
        assert payload["messages"][3]["tool_call_id"] == "call_read_app"
        assert "fallback prompt" not in str(payload["messages"])
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "agentblaster-ok"}}]},
            headers={"content-type": "application/json"},
        )

    provider = ProviderConfig(name="openai-like", contract=ApiContract.OPENAI, base_url="https://example.com/v1")
    adapter = OpenAICompatibleAdapter(provider, client=httpx.Client(transport=httpx.MockTransport(handler)))
    case = trace_replay_case()

    response = adapter.chat_completion("qwen-test", case)

    assert response.text == "agentblaster-ok"


def test_openai_chat_completion_preserves_injected_system_prompt_for_trace_messages() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json_loads_request(request)
        assert [message["role"] for message in payload["messages"]] == [
            "system",
            "system",
            "user",
            "assistant",
            "tool",
            "user",
        ]
        assert payload["messages"][0]["content"] == "Injected skill and LCP prefix."
        assert payload["messages"][1]["content"] == "Trace policy."
        assert "fallback prompt" not in str(payload["messages"])
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "agentblaster-ok"}}]},
            headers={"content-type": "application/json"},
        )

    provider = ProviderConfig(name="openai-like", contract=ApiContract.OPENAI, base_url="https://example.com/v1")
    adapter = OpenAICompatibleAdapter(provider, client=httpx.Client(transport=httpx.MockTransport(handler)))
    case = trace_replay_case().model_copy(update={"system_prompt": "Injected skill and LCP prefix."})

    response = adapter.chat_completion("qwen-test", case)

    assert response.text == "agentblaster-ok"


def test_openai_chat_completion_streams_text_and_ttft() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json_loads_request(request)
        assert payload["stream"] is True
        body = "\n".join(
            [
                'data: {"choices":[{"delta":{"role":"assistant"}}]}',
                'data: {"choices":[{"delta":{"content":"agent"}}]}',
                'data: {"choices":[{"delta":{"content":"blaster-ok"}}]}',
                "data: [DONE]",
                "",
            ]
        )
        return httpx.Response(
            200,
            content=body.encode("utf-8"),
            headers={"content-type": "text/event-stream"},
        )

    provider = ProviderConfig(name="openai-like", contract=ApiContract.OPENAI, base_url="https://example.com/v1")
    adapter = OpenAICompatibleAdapter(provider, client=httpx.Client(transport=httpx.MockTransport(handler)))
    case = BenchmarkCase(
        id="streamcase",
        title="stream case",
        prompt="Stream response",
        expected_substring="agentblaster-ok",
        streaming=True,
    )

    response = adapter.chat_completion("qwen-test", case)

    assert response.streaming is True
    assert response.text == "agentblaster-ok"
    assert response.ttft_ms is not None
    assert response.raw["stream"] is True
    assert len(response.raw["events"]) == 3


def test_openai_chat_completion_stream_can_cancel(monkeypatch) -> None:
    ticks = iter([0.0, 0.0, 0.02, 0.02, 0.02])

    def fake_perf_counter() -> float:
        return next(ticks, 0.02)

    monkeypatch.setattr(adapters_module, "perf_counter", fake_perf_counter)

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json_loads_request(request)
        assert payload["stream"] is True
        body = "\n".join(
            [
                'data: {"choices":[{"delta":{"role":"assistant"}}]}',
                'data: {"choices":[{"delta":{"content":"partial"}}]}',
                'data: {"choices":[{"delta":{"content":"should-not-be-required"}}]}',
                "data: [DONE]",
                "",
            ]
        )
        return httpx.Response(200, content=body.encode("utf-8"), headers={"content-type": "text/event-stream"})

    provider = ProviderConfig(name="openai-like", contract=ApiContract.OPENAI, base_url="https://example.com/v1")
    adapter = OpenAICompatibleAdapter(provider, client=httpx.Client(transport=httpx.MockTransport(handler)))
    case = BenchmarkCase(
        id="cancel-stream",
        title="cancel stream",
        prompt="Stream until canceled.",
        streaming=True,
        cancel_after_ms=10,
    )

    response = adapter.chat_completion("qwen-test", case)

    assert response.streaming is True
    assert response.canceled is True
    assert response.cancellation_latency_ms == 20.0
    assert response.raw["agentblaster_cancelled"] is True
    assert response.raw["cancel_after_ms"] == 10
    assert response.text == "partial"


def test_openai_chat_completion_streams_tool_call_fragments() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = "\n".join(
            [
                'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"name":"ping_"}}]}}]}',
                'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"name":"agentblaster","arguments":"{\\"target\\":\\"agent"}}]}}]}',
                'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"blaster-ok\\"}"}}]}}]}',
                "data: [DONE]",
                "",
            ]
        )
        return httpx.Response(200, content=body.encode("utf-8"), headers={"content-type": "text/event-stream"})

    provider = ProviderConfig(name="openai-like", contract=ApiContract.OPENAI, base_url="https://example.com/v1")
    adapter = OpenAICompatibleAdapter(provider, client=httpx.Client(transport=httpx.MockTransport(handler)))
    case = BenchmarkCase(
        id="streamtoolcase",
        title="stream tool case",
        prompt="Stream tool",
        expected_tool_name="ping_agentblaster",
        streaming=True,
    )

    response = adapter.chat_completion("qwen-test", case)

    assert response.streaming is True
    assert response.tool_names == ["ping_agentblaster"]
    assert response.tool_calls[0].arguments == {"target": "agentblaster-ok"}


def test_openai_responses_posts_responses_request_and_extracts_output() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == "https://example.com/v1/responses"
        payload = json_loads_request(request)
        assert payload["model"] == "qwen-test"
        assert payload["input"] == "Use tool"
        assert payload["instructions"] == "Be exact"
        assert payload["previous_response_id"] == "resp_previous"
        assert payload["max_output_tokens"] == 64
        assert payload["max_tool_calls"] == 1
        assert payload["text"] == {"format": {"type": "json_object"}}
        assert payload["tools"][0]["name"] == "ping_agentblaster"
        assert payload["tool_choice"] == {"type": "function", "name": "ping_agentblaster"}
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "agentblaster-ok"}],
                    },
                    {
                        "type": "function_call",
                        "name": "ping_agentblaster",
                        "arguments": '{"target":"agentblaster-ok"}',
                    },
                ],
                "usage": {"input_tokens": 9, "output_tokens": 3, "total_tokens": 12},
            },
            headers={"content-type": "application/json"},
        )

    provider = ProviderConfig(
        name="openai-responses-like",
        contract=ApiContract.OPENAI_RESPONSES,
        base_url="https://example.com/v1",
    )
    adapter = OpenAIResponsesAdapter(provider, client=httpx.Client(transport=httpx.MockTransport(handler)))
    case = BenchmarkCase(
        id="responses-toolcase",
        title="responses tool case",
        prompt="Use tool",
        system_prompt="Be exact",
        expected_tool_name="ping_agentblaster",
        response_format={"type": "json_object"},
        previous_response_id="resp_previous",
        max_tool_calls=1,
        max_tokens=64,
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "ping_agentblaster",
                    "parameters": {"type": "object", "properties": {"target": {"type": "string"}}},
                },
            }
        ],
        tool_choice={"type": "function", "function": {"name": "ping_agentblaster"}},
    )

    response = adapter.chat_completion("qwen-test", case)

    assert response.contract == ApiContract.OPENAI_RESPONSES
    assert response.text == "agentblaster-ok"
    assert response.tool_names == ["ping_agentblaster"]
    assert response.tool_calls[0].arguments == {"target": "agentblaster-ok"}


def test_openai_responses_streams_text_usage_status_and_tool_arguments() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json_loads_request(request)
        assert payload["stream"] is True
        assert payload["tools"][0]["name"] == "ping_agentblaster"
        body = responses_sse(
            [
                {
                    "type": "response.created",
                    "response": {"id": "resp_test", "status": "in_progress"},
                },
                {
                    "type": "response.output_text.delta",
                    "item_id": "msg_1",
                    "output_index": 0,
                    "content_index": 0,
                    "delta": "agent",
                },
                {
                    "type": "response.output_text.delta",
                    "item_id": "msg_1",
                    "output_index": 0,
                    "content_index": 0,
                    "delta": "blaster-ok",
                },
                {
                    "type": "response.output_item.added",
                    "item_id": "fc_1",
                    "output_index": 1,
                    "item": {"type": "function_call", "name": "ping_agentblaster", "arguments": ""},
                },
                {
                    "type": "response.function_call_arguments.delta",
                    "item_id": "fc_1",
                    "output_index": 1,
                    "delta": '{"target":"agent',
                },
                {
                    "type": "response.function_call_arguments.delta",
                    "item_id": "fc_1",
                    "output_index": 1,
                    "delta": 'blaster-ok"}',
                },
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp_test",
                        "status": "completed",
                        "usage": {"input_tokens": 11, "output_tokens": 5, "total_tokens": 16},
                    },
                },
            ]
        )
        return httpx.Response(200, content=body.encode("utf-8"), headers={"content-type": "text/event-stream"})

    provider = ProviderConfig(
        name="openai-responses-like",
        contract=ApiContract.OPENAI_RESPONSES,
        base_url="https://example.com/v1",
    )
    adapter = OpenAIResponsesAdapter(provider, client=httpx.Client(transport=httpx.MockTransport(handler)))
    case = BenchmarkCase(
        id="responses-stream",
        title="responses stream",
        prompt="Stream response",
        expected_tool_name="ping_agentblaster",
        streaming=True,
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "ping_agentblaster",
                    "parameters": {"type": "object", "properties": {"target": {"type": "string"}}},
                },
            }
        ],
    )

    response = adapter.chat_completion("qwen-test", case)

    assert response.contract == ApiContract.OPENAI_RESPONSES
    assert response.streaming is True
    assert response.text == "agentblaster-ok"
    assert response.ttft_ms is not None
    assert response.tool_names == ["ping_agentblaster"]
    assert response.tool_calls[0].arguments == {"target": "agentblaster-ok"}
    assert response.raw["usage"]["input_tokens"] == 11
    assert response.raw["usage"]["output_tokens"] == 5
    assert response.raw["status"] == "completed"


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
    assert response.tool_calls[0].arguments == {}


def test_anthropic_chat_completion_replays_explicit_trace_messages() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json_loads_request(request)
        assert payload["system"] == "Trace policy."
        assert [message["role"] for message in payload["messages"]] == ["user", "assistant", "user", "user"]
        assert payload["messages"][1]["content"][0]["type"] == "tool_use"
        assert payload["messages"][1]["content"][0]["name"] == "read_file_fixture"
        assert payload["messages"][1]["content"][0]["input"] == {"path": "/repo/src/app.py"}
        assert payload["messages"][2]["content"][0]["type"] == "tool_result"
        assert payload["messages"][2]["content"][0]["tool_use_id"] == "call_read_app"
        return httpx.Response(
            200,
            json={"content": [{"type": "text", "text": "agentblaster-ok"}]},
            headers={"content-type": "application/json"},
        )

    provider = ProviderConfig(name="anthropic-like", contract=ApiContract.ANTHROPIC, base_url="https://example.com/v1")
    adapter = AnthropicCompatibleAdapter(provider, client=httpx.Client(transport=httpx.MockTransport(handler)))
    case = trace_replay_case()

    response = adapter.chat_completion("claude-test", case)

    assert response.text == "agentblaster-ok"


def test_anthropic_chat_completion_streams_text_usage_and_stop_reason() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json_loads_request(request)
        assert payload["stream"] is True
        body = anthropic_sse(
            [
                {
                    "type": "message_start",
                    "message": {
                        "id": "msg_test",
                        "type": "message",
                        "role": "assistant",
                        "content": [],
                        "model": "claude-test",
                        "stop_reason": None,
                        "usage": {"input_tokens": 7, "output_tokens": 1},
                    },
                },
                {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
                {"type": "ping"},
                {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "agent"}},
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "blaster-ok"},
                },
                {"type": "content_block_stop", "index": 0},
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {"output_tokens": 3},
                },
                {"type": "message_stop"},
            ]
        )
        return httpx.Response(200, content=body.encode("utf-8"), headers={"content-type": "text/event-stream"})

    provider = ProviderConfig(name="anthropic-like", contract=ApiContract.ANTHROPIC, base_url="https://example.com/v1")
    adapter = AnthropicCompatibleAdapter(provider, client=httpx.Client(transport=httpx.MockTransport(handler)))
    case = BenchmarkCase(
        id="anthropicstream",
        title="Anthropic stream",
        prompt="Stream response",
        expected_substring="agentblaster-ok",
        streaming=True,
    )

    response = adapter.chat_completion("claude-test", case)

    assert response.streaming is True
    assert response.text == "agentblaster-ok"
    assert response.ttft_ms is not None
    assert response.raw["stream"] is True
    assert response.raw["usage"]["input_tokens"] == 7
    assert response.raw["usage"]["output_tokens"] == 3
    assert response.raw["stop_reason"] == "end_turn"


def test_anthropic_chat_completion_streams_tool_use_json_fragments() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json_loads_request(request)
        assert payload["stream"] is True
        assert payload["tools"][0]["name"] == "ping_agentblaster"
        assert payload["tool_choice"]["name"] == "ping_agentblaster"
        body = anthropic_sse(
            [
                {
                    "type": "message_start",
                    "message": {
                        "id": "msg_test",
                        "type": "message",
                        "role": "assistant",
                        "content": [],
                        "model": "claude-test",
                        "stop_reason": None,
                        "usage": {"input_tokens": 9, "output_tokens": 1},
                    },
                },
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {
                        "type": "tool_use",
                        "id": "toolu_test",
                        "name": "ping_agentblaster",
                        "input": {},
                    },
                },
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "input_json_delta", "partial_json": '{"target":'},
                },
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "input_json_delta", "partial_json": ' "agent'},
                },
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "input_json_delta", "partial_json": 'blaster-ok"}'},
                },
                {"type": "content_block_stop", "index": 0},
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "tool_use", "stop_sequence": None},
                    "usage": {"output_tokens": 8},
                },
                {"type": "message_stop"},
            ]
        )
        return httpx.Response(200, content=body.encode("utf-8"), headers={"content-type": "text/event-stream"})

    provider = ProviderConfig(name="anthropic-like", contract=ApiContract.ANTHROPIC, base_url="https://example.com/v1")
    adapter = AnthropicCompatibleAdapter(provider, client=httpx.Client(transport=httpx.MockTransport(handler)))
    case = BenchmarkCase(
        id="anthropicstreamtool",
        title="Anthropic stream tool",
        prompt="Use tool",
        expected_tool_name="ping_agentblaster",
        streaming=True,
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "ping_agentblaster",
                    "parameters": {"type": "object", "properties": {"target": {"type": "string"}}},
                },
            }
        ],
        tool_choice={"type": "function", "function": {"name": "ping_agentblaster"}},
    )

    response = adapter.chat_completion("claude-test", case)

    assert response.streaming is True
    assert response.tool_names == ["ping_agentblaster"]
    assert response.tool_calls[0].arguments == {"target": "agentblaster-ok"}
    assert response.raw["usage"]["input_tokens"] == 9
    assert response.raw["usage"]["output_tokens"] == 8
    assert response.raw["stop_reason"] == "tool_use"


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
        assert payload["options"]["num_predict"] == SMOKE_SENTINEL_MAX_TOKENS
        assert payload["messages"][0]["content"] == SMOKE_SENTINEL_SYSTEM_PROMPT
        assert payload["messages"][1]["content"] == SMOKE_SENTINEL_PROMPT
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


def test_lmstudio_native_probe_reads_v1_models() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://example.com/api/v1/models"
        return httpx.Response(
            200,
            json={
                "models": [
                    {"key": "google/gemma-4-31b"},
                    {"id": "loaded-instance"},
                    {"model": "legacy-shape"},
                ]
            },
            headers={"content-type": "application/json"},
        )

    provider = ProviderConfig(
        name="lm-studio-native",
        contract=ApiContract.NATIVE,
        base_url="http://example.com",
        native_adapter="lm-studio",
    )
    adapter = LMStudioNativeAdapter(provider, client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = adapter.probe()

    assert result.ok is True
    assert result.models == ["google/gemma-4-31b", "loaded-instance", "legacy-shape"]


def test_lmstudio_native_chat_posts_v1_chat_and_extracts_stats() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://example.com/api/v1/chat"
        payload = json_loads_request(request)
        assert payload["model"] == "qwen-test"
        assert payload["input"] == "Reply with exactly: agentblaster-ok"
        assert payload["system_prompt"] == "Be exact"
        assert payload["stream"] is False
        assert payload["store"] is False
        assert payload["max_output_tokens"] == 16
        return httpx.Response(
            200,
            json={
                "model_instance_id": "qwen-test",
                "output": [
                    {"type": "reasoning", "content": "thinking"},
                    {"type": "message", "content": "agentblaster-ok"},
                    {"type": "tool_call", "tool": "browser_navigate", "arguments": {}},
                ],
                "stats": {
                    "input_tokens": 10,
                    "total_output_tokens": 5,
                    "tokens_per_second": 25.0,
                    "time_to_first_token_seconds": 0.2,
                    "model_load_time_seconds": 1.5,
                },
            },
            headers={"content-type": "application/json"},
        )

    provider = ProviderConfig(
        name="lm-studio-native",
        contract=ApiContract.NATIVE,
        base_url="http://example.com",
        native_adapter="lm-studio",
    )
    adapter = LMStudioNativeAdapter(provider, client=httpx.Client(transport=httpx.MockTransport(handler)))
    case = BenchmarkCase(
        id="lmstudio",
        title="LM Studio",
        prompt="Reply with exactly: agentblaster-ok",
        system_prompt="Be exact",
        max_tokens=16,
    )

    response = adapter.chat_completion("qwen-test", case)

    assert response.status_code == 200
    assert response.text == "agentblaster-ok"
    assert response.tool_names == ["browser_navigate"]
    assert response.tool_calls[0].arguments == {}
    assert response.raw["stats"]["tokens_per_second"] == 25.0


def test_adapter_for_resolves_ollama_native_adapter() -> None:
    provider = ProviderConfig(
        name="ollama-native",
        contract=ApiContract.NATIVE,
        base_url="http://example.com",
        native_adapter="ollama",
    )

    assert isinstance(adapter_for(provider), OllamaNativeAdapter)


def test_adapter_for_resolves_openai_responses_adapter() -> None:
    provider = ProviderConfig(
        name="openai-responses-like",
        contract=ApiContract.OPENAI_RESPONSES,
        base_url="http://example.com/v1",
    )

    assert isinstance(adapter_for(provider), OpenAIResponsesAdapter)


def test_adapter_for_preserves_injected_http_client() -> None:
    provider = ProviderConfig(
        name="openai-injected-client",
        contract=ApiContract.OPENAI,
        base_url="http://example.com/v1",
    )
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"data": []})))

    adapter = adapter_for(provider, client=client)

    assert isinstance(adapter, OpenAICompatibleAdapter)
    assert adapter.client is client


def test_adapter_for_resolves_lmstudio_native_adapter() -> None:
    provider = ProviderConfig(
        name="lm-studio-native",
        contract=ApiContract.NATIVE,
        base_url="http://example.com",
        native_adapter="lm-studio",
    )

    assert isinstance(adapter_for(provider), LMStudioNativeAdapter)


def json_loads_request(request: httpx.Request):
    import json

    return json.loads(request.read().decode())


def anthropic_sse(events: list[dict]) -> str:
    import json

    lines: list[str] = []
    for event in events:
        lines.append(f"event: {event['type']}")
        lines.append(f"data: {json.dumps(event)}")
        lines.append("")
    return "\n".join(lines)


def responses_sse(events: list[dict]) -> str:
    import json

    lines: list[str] = []
    for event in events:
        lines.append(f"event: {event['type']}")
        lines.append(f"data: {json.dumps(event)}")
        lines.append("")
    lines.append("data: [DONE]")
    lines.append("")
    return "\n".join(lines)


def trace_replay_case() -> BenchmarkCase:
    return BenchmarkCase(
        id="tracecase",
        title="trace case",
        prompt="fallback prompt",
        messages=[
            {"role": "system", "content": "Trace policy."},
            {"role": "user", "content": "Read /repo/src/app.py."},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_read_app",
                        "type": "function",
                        "function": {"name": "read_file_fixture", "arguments": '{"path":"/repo/src/app.py"}'},
                    }
                ],
            },
            {
                "role": "tool",
                "name": "read_file_fixture",
                "tool_call_id": "call_read_app",
                "content": '{"content":"agentblaster-ok"}',
            },
            {"role": "user", "content": "What string was returned?"},
        ],
        expected_substring="agentblaster-ok",
    )
