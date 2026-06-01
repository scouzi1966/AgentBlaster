from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer

import httpx

from agentblaster.mock_provider import MockProviderSettings, make_mock_provider_handler


def test_mock_provider_serves_openai_chat_models_and_metrics() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_mock_provider_handler())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}/v1"
        models = httpx.get(f"{base_url}/models", timeout=2.0)
        chat = httpx.post(
            f"{base_url}/chat/completions",
            json={
                "model": "agentblaster-mock-qwen3.6-27b-dense",
                "messages": [{"role": "user", "content": "Reply with exactly: agentblaster-ok"}],
                "max_tokens": 16,
            },
            timeout=2.0,
        )
        metrics = httpx.get(f"http://127.0.0.1:{server.server_address[1]}/metrics", timeout=2.0)

        assert models.status_code == 200
        assert models.json()["data"][0]["id"].startswith("agentblaster-mock")
        assert chat.status_code == 200
        assert chat.json()["choices"][0]["message"]["content"] == "agentblaster-ok"
        assert chat.json()["usage"]["total_tokens"] >= 1
        assert "agentblaster_mock_requests_total" in metrics.text
    finally:
        server.shutdown()
        server.server_close()


def test_mock_provider_serves_tool_calls_responses_and_anthropic_messages() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_mock_provider_handler())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}/v1"
        tool_schema = {"type": "function", "function": {"name": "ping_agentblaster", "parameters": {"type": "object"}}}
        chat = httpx.post(
            f"{base_url}/chat/completions",
            json={
                "model": "agentblaster-mock-qwen3.6-27b-dense",
                "messages": [{"role": "user", "content": "Call ping_agentblaster with target set to marker-1."}],
                "tools": [tool_schema],
                "tool_choice": {"type": "function", "function": {"name": "ping_agentblaster"}},
            },
            timeout=2.0,
        )
        responses = httpx.post(
            f"{base_url}/responses",
            json={
                "model": "agentblaster-mock-qwen3.6-27b-dense",
                "input": "Call ping_agentblaster with target set to marker-2.",
                "tools": [{"type": "function", "name": "ping_agentblaster", "parameters": {"type": "object"}}],
                "tool_choice": {"type": "function", "name": "ping_agentblaster"},
            },
            timeout=2.0,
        )
        anthropic = httpx.post(
            f"{base_url}/messages",
            json={
                "model": "agentblaster-mock-qwen3.6-27b-dense",
                "messages": [{"role": "user", "content": "Call ping_agentblaster with target set to marker-3."}],
                "tools": [{"name": "ping_agentblaster", "input_schema": {"type": "object"}}],
                "tool_choice": {"type": "tool", "name": "ping_agentblaster"},
            },
            timeout=2.0,
        )
        route_chat = httpx.post(
            f"{base_url}/chat/completions",
            json={
                "model": "agentblaster-mock-qwen3.6-27b-dense",
                "messages": [
                    {"role": "user", "content": "Use route_agentblaster_task with route_id set to agentblaster-route-loop-final."}
                ],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "route_agentblaster_task",
                            "parameters": {
                                "type": "object",
                                "properties": {"route_id": {"type": "string"}},
                                "required": ["route_id"],
                            },
                        },
                    }
                ],
            },
            timeout=2.0,
        )
        mcp_chat = httpx.post(
            f"{base_url}/chat/completions",
            json={
                "model": "agentblaster-mock-qwen3.6-27b-dense",
                "messages": [
                    {"role": "user", "content": "Call mcp_fixture_read_resource with uri fixture://mcp/resource/status."}
                ],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "mcp_fixture_read_resource",
                            "parameters": {
                                "type": "object",
                                "properties": {"uri": {"type": "string"}},
                                "required": ["uri"],
                            },
                        },
                    }
                ],
            },
            timeout=2.0,
        )

        assert chat.json()["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "ping_agentblaster"
        assert json.loads(chat.json()["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"])["target"] == "marker-1"
        assert responses.json()["output"][1]["name"] == "ping_agentblaster"
        assert json.loads(responses.json()["output"][1]["arguments"])["target"] == "marker-2"
        assert anthropic.json()["content"][1]["type"] == "tool_use"
        assert anthropic.json()["content"][1]["input"]["target"] == "marker-3"
        route_args = json.loads(route_chat.json()["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"])
        assert route_args == {"confidence": "high", "route_id": "agentblaster-route-loop-final"}
        mcp_args = json.loads(mcp_chat.json()["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"])
        assert mcp_args == {"uri": "fixture://mcp/resource/status"}
    finally:
        server.shutdown()
        server.server_close()


def test_mock_provider_can_require_auth_for_contract_tests() -> None:
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        make_mock_provider_handler(MockProviderSettings(require_auth=True)),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}/v1"
        missing = httpx.get(f"{base_url}/models", timeout=2.0)
        present = httpx.get(f"{base_url}/models", headers={"authorization": "Bearer test"}, timeout=2.0)

        assert missing.status_code == 401
        assert present.status_code == 200
    finally:
        server.shutdown()
        server.server_close()
