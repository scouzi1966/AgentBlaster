from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

MOCK_MODELS = (
    "agentblaster-mock-qwen3.6-27b-dense",
    "agentblaster-mock-gemma-4-31b-dense",
)


@dataclass(frozen=True)
class MockProviderSettings:
    profile: str = "deterministic"
    latency_ms: int = 0
    require_auth: bool = False


def make_mock_provider_handler(settings: MockProviderSettings | None = None) -> type[BaseHTTPRequestHandler]:
    active_settings = settings or MockProviderSettings()

    class MockProviderHandler(BaseHTTPRequestHandler):
        server_version = "AgentBlasterMockProvider/1.0"

        def do_GET(self) -> None:  # noqa: N802
            _sleep(active_settings.latency_ms)
            path = _normalized_path(self.path)
            if _auth_missing(self, active_settings):
                self._json(HTTPStatus.UNAUTHORIZED, {"error": {"message": "missing bearer token", "type": "auth_error"}})
                return
            if path.endswith("/models"):
                self._json(
                    HTTPStatus.OK,
                    {
                        "object": "list",
                        "data": [{"id": model, "object": "model", "owned_by": "agentblaster"} for model in MOCK_MODELS],
                    },
                )
                return
            if path.endswith("/metrics") or path == "/metrics":
                self._text(
                    HTTPStatus.OK,
                    "agentblaster_mock_requests_total 1\nagentblaster_mock_ttft_ms 12\n",
                    content_type="text/plain; version=0.0.4; charset=utf-8",
                )
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": {"message": f"unknown mock endpoint: {path}"}})

        def do_POST(self) -> None:  # noqa: N802
            _sleep(active_settings.latency_ms)
            path = _normalized_path(self.path)
            if _auth_missing(self, active_settings):
                self._json(HTTPStatus.UNAUTHORIZED, {"error": {"message": "missing bearer token", "type": "auth_error"}})
                return
            payload = self._read_json()
            if path.endswith("/chat/completions"):
                self._openai_chat(payload)
                return
            if path.endswith("/responses"):
                self._openai_responses(payload)
                return
            if path.endswith("/messages"):
                self._anthropic_messages(payload)
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": {"message": f"unknown mock endpoint: {path}"}})

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

        def _openai_chat(self, payload: dict[str, Any]) -> None:
            text = _deterministic_text(payload)
            tool_name = _requested_tool_name(payload)
            if payload.get("stream"):
                if tool_name:
                    tool_arguments = json.dumps(_tool_arguments(payload, tool_name))
                    events = [
                        {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_mock", "type": "function", "function": {"name": tool_name}}]}}]},
                        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": tool_arguments}}]}}]},
                    ]
                else:
                    midpoint = max(len(text) // 2, 1)
                    events = [
                        {"choices": [{"delta": {"role": "assistant"}}]},
                        {"choices": [{"delta": {"content": text[:midpoint]}}]},
                        {"choices": [{"delta": {"content": text[midpoint:]}}]},
                    ]
                self._sse(events)
                return
            message: dict[str, Any] = {"role": "assistant", "content": text}
            finish_reason = "stop"
            if tool_name:
                message["content"] = None
                message["tool_calls"] = [
                    {
                        "id": "call_mock",
                        "type": "function",
                        "function": {"name": tool_name, "arguments": json.dumps(_tool_arguments(payload, tool_name))},
                    }
                ]
                finish_reason = "tool_calls"
            self._json(
                HTTPStatus.OK,
                {
                    "id": "chatcmpl_agentblaster_mock",
                    "object": "chat.completion",
                    "model": payload.get("model") or MOCK_MODELS[0],
                    "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
                    "usage": _usage(payload, output_text=text),
                    "agentblaster_mock": {"profile": active_settings.profile, "redacted": True},
                },
            )

        def _openai_responses(self, payload: dict[str, Any]) -> None:
            text = _deterministic_text(payload)
            tool_name = _requested_tool_name(payload)
            if payload.get("stream"):
                events: list[dict[str, Any]] = [
                    {"type": "response.created", "response": {"id": "resp_agentblaster_mock", "status": "in_progress"}},
                    {"type": "response.output_text.delta", "item_id": "msg_mock", "output_index": 0, "content_index": 0, "delta": text},
                ]
                if tool_name:
                    events.extend(
                        [
                            {
                                "type": "response.output_item.added",
                                "item_id": "fc_mock",
                                "output_index": 1,
                                "item": {"type": "function_call", "name": tool_name, "arguments": ""},
                            },
                            {
                                "type": "response.function_call_arguments.delta",
                                "item_id": "fc_mock",
                                "output_index": 1,
                                "delta": json.dumps(_tool_arguments(payload, tool_name)),
                            },
                        ]
                    )
                events.append(
                    {
                        "type": "response.completed",
                        "response": {"id": "resp_agentblaster_mock", "status": "completed", "usage": _responses_usage(payload, text)},
                    }
                )
                self._sse(events)
                return
            output: list[dict[str, Any]] = [
                {"type": "message", "content": [{"type": "output_text", "text": text}]},
            ]
            if tool_name:
                output.append(
                    {
                        "type": "function_call",
                        "call_id": "call_mock",
                        "name": tool_name,
                        "arguments": json.dumps(_tool_arguments(payload, tool_name)),
                    }
                )
            self._json(
                HTTPStatus.OK,
                {
                    "id": "resp_agentblaster_mock",
                    "object": "response",
                    "status": "completed",
                    "model": payload.get("model") or MOCK_MODELS[0],
                    "output": output,
                    "usage": _responses_usage(payload, text),
                    "agentblaster_mock": {"profile": active_settings.profile, "redacted": True},
                },
            )

        def _anthropic_messages(self, payload: dict[str, Any]) -> None:
            text = _deterministic_text(payload)
            tool_name = _requested_tool_name(payload)
            if payload.get("stream"):
                self._sse(_anthropic_stream_events(payload, text=text, tool_name=tool_name))
                return
            content: list[dict[str, Any]] = [{"type": "text", "text": text}]
            stop_reason = "end_turn"
            if tool_name:
                content.append(
                    {
                        "type": "tool_use",
                        "id": "toolu_mock",
                        "name": tool_name,
                        "input": _tool_arguments(payload, tool_name),
                    }
                )
                stop_reason = "tool_use"
            self._json(
                HTTPStatus.OK,
                {
                    "id": "msg_agentblaster_mock",
                    "type": "message",
                    "role": "assistant",
                    "model": payload.get("model") or MOCK_MODELS[0],
                    "content": content,
                    "stop_reason": stop_reason,
                    "usage": {"input_tokens": _estimated_tokens(payload), "output_tokens": max(len(text.split()), 1)},
                    "agentblaster_mock": {"profile": active_settings.profile, "redacted": True},
                },
            )

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("content-length", "0") or "0")
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}

        def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
            self.send_response(int(status))
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.send_header("x-agentblaster-mock", active_settings.profile)
            self.end_headers()
            self.wfile.write(body)

        def _text(self, status: HTTPStatus, body_text: str, *, content_type: str) -> None:
            body = body_text.encode("utf-8")
            self.send_response(int(status))
            self.send_header("content-type", content_type)
            self.send_header("content-length", str(len(body)))
            self.send_header("x-agentblaster-mock", active_settings.profile)
            self.end_headers()
            self.wfile.write(body)

        def _sse(self, events: list[dict[str, Any]]) -> None:
            lines = [f"data: {json.dumps(event, sort_keys=True)}\n\n" for event in events]
            lines.append("data: [DONE]\n\n")
            body = "".join(lines).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("content-type", "text/event-stream; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.send_header("cache-control", "no-cache")
            self.send_header("x-agentblaster-mock", active_settings.profile)
            self.end_headers()
            self.wfile.write(body)

    return MockProviderHandler


def serve_mock_provider(*, host: str, port: int, settings: MockProviderSettings | None = None) -> None:
    server = ThreadingHTTPServer((host, port), make_mock_provider_handler(settings))
    try:
        server.serve_forever()
    finally:
        server.server_close()


def _anthropic_stream_events(payload: dict[str, Any], *, text: str, tool_name: str | None) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = [
        {
            "type": "message_start",
            "message": {"id": "msg_agentblaster_mock", "type": "message", "role": "assistant", "content": []},
        },
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}},
        {"type": "content_block_stop", "index": 0},
    ]
    if tool_name:
        events.extend(
            [
                {
                    "type": "content_block_start",
                    "index": 1,
                    "content_block": {"type": "tool_use", "id": "toolu_mock", "name": tool_name, "input": {}},
                },
                {
                    "type": "content_block_delta",
                    "index": 1,
                    "delta": {"type": "input_json_delta", "partial_json": json.dumps(_tool_arguments(payload, tool_name))},
                },
                {"type": "content_block_stop", "index": 1},
            ]
        )
    events.extend(
        [
            {
                "type": "message_delta",
                "delta": {"stop_reason": "tool_use" if tool_name else "end_turn"},
                "usage": {"output_tokens": max(len(text.split()), 1)},
            },
            {"type": "message_stop"},
        ]
    )
    return events


def _normalized_path(raw_path: str) -> str:
    path = urlparse(raw_path).path.rstrip("/")
    return path or "/"


def _sleep(latency_ms: int) -> None:
    if latency_ms > 0:
        time.sleep(latency_ms / 1000)


def _auth_missing(handler: BaseHTTPRequestHandler, settings: MockProviderSettings) -> bool:
    if not settings.require_auth:
        return False
    return not handler.headers.get("authorization") and not handler.headers.get("x-api-key")


def _deterministic_text(payload: dict[str, Any]) -> str:
    if _wants_json(payload):
        return json.dumps({"status": "agentblaster-ok", "marker": _target_marker(payload)}, sort_keys=True)
    prompt_text = _payload_text(payload)
    exact = _extract_exact_reply(prompt_text)
    if exact:
        return exact
    if "agentblaster-ok" in prompt_text:
        return "agentblaster-ok"
    marker = _target_marker(payload)
    if marker:
        return marker
    return "agentblaster-ok"


def _payload_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("prompt", "input", "instructions", "system"):
        value = payload.get(key)
        if isinstance(value, str):
            parts.append(value)
    messages = payload.get("messages")
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text") or block.get("content")
                        if isinstance(text, str):
                            parts.append(text)
    input_value = payload.get("input")
    if isinstance(input_value, list):
        for item in input_value:
            if isinstance(item, dict):
                content = item.get("content")
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and isinstance(block.get("text"), str):
                            parts.append(block["text"])
    return "\n".join(parts)


def _extract_exact_reply(text: str) -> str | None:
    match = re.search(r"Reply with exactly:\s*([^\n]+)", text)
    if not match:
        return None
    return match.group(1).strip().strip('"`')


def _requested_tool_name(payload: dict[str, Any]) -> str | None:
    prompt_text = _payload_text(payload)
    if _payload_has_tool_result(payload) and "agentblaster-loop-boundary-repeat" not in prompt_text:
        return None
    tool_choice = payload.get("tool_choice")
    if isinstance(tool_choice, dict):
        function = tool_choice.get("function")
        if isinstance(function, dict) and function.get("name"):
            return str(function["name"])
        if tool_choice.get("name"):
            return str(tool_choice["name"])
    tools = payload.get("tools")
    if isinstance(tools, list) and tools:
        first = tools[0]
        if isinstance(first, dict):
            function = first.get("function")
            if isinstance(function, dict) and function.get("name"):
                return str(function["name"])
            if first.get("name"):
                return str(first["name"])
    return None


def _tool_arguments(payload: dict[str, Any], tool_name: str) -> dict[str, Any]:
    if tool_name == "ping_agentblaster":
        return {"target": _target_marker(payload)}
    if tool_name == "route_agentblaster_task":
        return {"route_id": _route_marker(payload), "confidence": "high"}
    if tool_name == "search_agentblaster_notes":
        return {"query": "AgentBlaster deterministic notes"}
    if tool_name == "fetch_agentblaster_context":
        return {"context_id": "agentblaster-fixture-context"}
    if tool_name == "finalize_agentblaster_plan":
        return {"summary": "agentblaster-route-ok"}
    if tool_name == "mcp_fixture_read_resource":
        return {"uri": _fixture_uri(payload)}
    if tool_name == "mcp_fixture_call_tool":
        return {"name": "status", "payload": {"value": "agentblaster-mcp-ok"}}
    if tool_name == "mcp_fixture_list_prompts":
        return {"namespace": "agentblaster"}
    if tool_name.startswith("mcp_wide_tool_"):
        return {"query": "agentblaster", "limit": 1}
    return {"target": _target_marker(payload)}


def _target_marker(payload: dict[str, Any]) -> str:
    text = _payload_text(payload)
    for pattern in (r"target set to ([A-Za-z0-9_.:-]+)", r"marker[:=]\s*([A-Za-z0-9_.:-]+)"):
        match = re.search(pattern, text)
        if match:
            return match.group(1).rstrip(".;,")
    if "agentblaster-ok" in text:
        return "agentblaster-ok"
    return "agentblaster-mock-marker"


def _route_marker(payload: dict[str, Any]) -> str:
    text = _payload_text(payload)
    for pattern in (r"route_id set to ([A-Za-z0-9_.:-]+)", r"route_id[:=]\s*([A-Za-z0-9_.:-]+)"):
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip().strip(".,`")
    return "agentblaster-route-mock"


def _fixture_uri(payload: dict[str, Any]) -> str:
    text = _payload_text(payload)
    match = re.search(r"uri\s+(fixture://[A-Za-z0-9_./:-]+)", text)
    if match:
        return match.group(1).strip().strip(".,`")
    return "fixture://mcp/resource/status"


def _payload_has_tool_result(value: Any) -> bool:
    if isinstance(value, dict):
        role = value.get("role")
        item_type = value.get("type")
        if role == "tool" or item_type == "tool_result":
            return True
        if value.get("tool_call_id") and "content" in value:
            return True
        return any(_payload_has_tool_result(item) for item in value.values())
    if isinstance(value, list):
        return any(_payload_has_tool_result(item) for item in value)
    return False


def _wants_json(payload: dict[str, Any]) -> bool:
    response_format = payload.get("response_format")
    if isinstance(response_format, dict) and response_format.get("type") == "json_object":
        return True
    text = payload.get("text")
    if isinstance(text, dict) and isinstance(text.get("format"), dict):
        return text["format"].get("type") == "json_object"
    return False


def _estimated_tokens(payload: dict[str, Any]) -> int:
    return max(len(_payload_text(payload).split()), 1)


def _usage(payload: dict[str, Any], *, output_text: str) -> dict[str, int]:
    prompt_tokens = _estimated_tokens(payload)
    completion_tokens = max(len(output_text.split()), 1)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


def _responses_usage(payload: dict[str, Any], text: str) -> dict[str, int]:
    usage = _usage(payload, output_text=text)
    return {"input_tokens": usage["prompt_tokens"], "output_tokens": usage["completion_tokens"], "total_tokens": usage["total_tokens"]}
