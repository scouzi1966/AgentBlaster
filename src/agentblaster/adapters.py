from __future__ import annotations

import json
from collections.abc import Mapping
from time import perf_counter
from typing import Any

import httpx

from agentblaster.errors import AdapterError
from agentblaster.models import AdapterResponse, ApiContract, BenchmarkCase, ProbeResult, ProviderConfig, ToolCallRecord
from agentblaster.redaction import redact_value
from agentblaster.secrets import SecretResolver


SAFE_RESPONSE_HEADERS = {
    "request-id",
    "x-request-id",
    "openai-request-id",
    "anthropic-request-id",
    "x-ratelimit-limit-requests",
    "x-ratelimit-remaining-requests",
    "x-ratelimit-reset-requests",
    "x-ratelimit-limit-tokens",
    "x-ratelimit-remaining-tokens",
    "x-ratelimit-reset-tokens",
    "retry-after",
}


class ProviderAdapter:
    adapter_name = "provider"
    adapter_version = "agentblaster-adapter-v1"

    def __init__(
        self,
        provider: ProviderConfig,
        *,
        secrets: SecretResolver | None = None,
        client: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.provider = provider
        self.secrets = secrets or SecretResolver()
        self.client = client or httpx.Client(timeout=timeout, verify=httpx_verify_config(provider))

    def probe(self) -> ProbeResult:
        raise NotImplementedError

    def smoke_chat(self, model: str) -> AdapterResponse:
        case = BenchmarkCase(
            id="protocol-smoke-chat",
            title="Protocol smoke chat",
            prompt="Reply with exactly: agentblaster-ok",
            expected_substring="agentblaster-ok",
            max_tokens=16,
        )
        return self.chat_completion(model, case)

    def chat_completion(self, model: str, case: BenchmarkCase) -> AdapterResponse:
        raise NotImplementedError

    def _headers(self) -> dict[str, str]:
        headers = dict(self.provider.headers)
        api_key = self.secrets.resolve(self.provider.api_key_ref)
        if api_key:
            headers.update(self._auth_headers(api_key))
        return headers

    def _auth_headers(self, api_key: str) -> dict[str, str]:
        raise NotImplementedError


def httpx_verify_config(provider: ProviderConfig) -> bool | str:
    if not provider.tls_verify:
        return False
    if provider.ca_bundle is not None:
        return str(provider.ca_bundle)
    return True


class OpenAICompatibleAdapter(ProviderAdapter):
    adapter_name = "openai-chat-completions"

    def _auth_headers(self, api_key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key}"}

    def probe(self) -> ProbeResult:
        url = str(self.provider.base_url).rstrip("/") + "/models"
        try:
            response = self.client.get(url, headers=self._headers())
        except httpx.HTTPError as exc:
            raise AdapterError(f"OpenAI probe failed for {self.provider.name}: {exc}") from exc

        models: list[str] = []
        raw = response_json_or_metadata(response)
        data = raw.get("data", [])
        if isinstance(data, list):
            models = [str(item.get("id")) for item in data if isinstance(item, Mapping) and item.get("id")]

        return ProbeResult(
            provider=self.provider.name,
            contract=self.provider.contract,
            ok=response.is_success,
            status_code=response.status_code,
            message="ok" if response.is_success else _redacted_response_text(response),
            models=models,
            raw=raw,
        )

    def chat_completion(self, model: str, case: BenchmarkCase) -> AdapterResponse:
        url = str(self.provider.base_url).rstrip("/") + "/chat/completions"
        payload = {
            "model": model,
            "messages": _openai_messages_from_case(case),
            "temperature": case.temperature,
            "max_tokens": case.max_tokens,
        }
        if case.streaming:
            payload["stream"] = True
        if case.response_format:
            payload["response_format"] = case.response_format
        if case.tools:
            payload["tools"] = case.tools
        if case.tool_choice:
            payload["tool_choice"] = case.tool_choice
        started = perf_counter()
        try:
            if case.streaming:
                return self._chat_completion_stream(url, payload, case, started)
            response = self.client.post(url, headers=self._headers(), json=payload, timeout=case.timeout_seconds)
        except httpx.HTTPError as exc:
            raise AdapterError(f"OpenAI smoke request failed for {self.provider.name}: {exc}") from exc
        latency_ms = (perf_counter() - started) * 1000

        raw = response_json_or_metadata(response)

        text = ""
        choices = raw.get("choices", [])
        if choices and isinstance(choices[0], Mapping):
            message = choices[0].get("message", {})
            if isinstance(message, Mapping):
                text = str(message.get("content") or "")
        tool_calls = extract_openai_tool_calls(raw)

        return AdapterResponse(
            provider=self.provider.name,
            contract=ApiContract.OPENAI,
            status_code=response.status_code,
            latency_ms=latency_ms,
            raw=raw,
            text=text,
            tool_names=_tool_names(tool_calls),
            tool_calls=tool_calls,
        )

    def _chat_completion_stream(
        self,
        url: str,
        payload: dict[str, Any],
        case: BenchmarkCase,
        started: float,
    ) -> AdapterResponse:
        text_parts: list[str] = []
        raw_events: list[dict[str, Any]] = []
        status_code = 0
        ttft_ms = None
        canceled = False
        cancellation_latency_ms = None
        tool_call_fragments: dict[int, dict[str, Any]] = {}
        try:
            with self.client.stream(
                "POST",
                url,
                headers=self._headers(),
                json=payload,
                timeout=case.timeout_seconds,
            ) as response:
                status_code = response.status_code
                for line in response.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        raw_events.append({"malformed": data})
                        continue
                    raw_events.append(event)
                    if ttft_ms is None and _openai_stream_event_has_output(event):
                        ttft_ms = (perf_counter() - started) * 1000
                    _accumulate_openai_stream_event(event, text_parts, tool_call_fragments)
                    cancellation_elapsed = _stream_cancellation_elapsed_ms(case, started)
                    if cancellation_elapsed is not None:
                        canceled = True
                        cancellation_latency_ms = cancellation_elapsed
                        break
        except httpx.HTTPError as exc:
            raise AdapterError(f"OpenAI streaming request failed for {self.provider.name}: {exc}") from exc
        latency_ms = (perf_counter() - started) * 1000
        raw = {
            "stream": True,
            "events": raw_events,
            "agentblaster_http": _safe_http_metadata(response),
            "agentblaster_cancelled": canceled,
            "cancel_after_ms": case.cancel_after_ms,
            "cancellation_latency_ms": cancellation_latency_ms,
        }
        tool_calls = _stream_tool_calls(tool_call_fragments)
        return AdapterResponse(
            provider=self.provider.name,
            contract=ApiContract.OPENAI,
            status_code=status_code,
            latency_ms=latency_ms,
            raw=raw,
            text="".join(text_parts),
            tool_names=_tool_names(tool_calls),
            tool_calls=tool_calls,
            streaming=True,
            ttft_ms=round(ttft_ms, 3) if ttft_ms is not None else None,
            canceled=canceled,
            cancellation_latency_ms=cancellation_latency_ms,
        )


class OpenAIResponsesAdapter(OpenAICompatibleAdapter):
    """Adapter for OpenAI Responses-compatible `/responses` endpoints."""

    adapter_name = "openai-responses"

    def chat_completion(self, model: str, case: BenchmarkCase) -> AdapterResponse:
        url = str(self.provider.base_url).rstrip("/") + "/responses"
        payload: dict[str, Any] = {
            "model": model,
            "input": _openai_responses_input_from_case(case),
            "temperature": case.temperature,
            "max_output_tokens": case.max_tokens,
        }
        if case.system_prompt:
            payload["instructions"] = case.system_prompt
        if case.previous_response_id:
            payload["previous_response_id"] = case.previous_response_id
        if case.max_tool_calls:
            payload["max_tool_calls"] = case.max_tool_calls
        if case.streaming:
            payload["stream"] = True
        if case.response_format:
            payload["text"] = {"format": case.response_format}
        if case.tools:
            payload["tools"] = [_openai_chat_tool_to_responses_tool(tool) for tool in case.tools]
        if case.tool_choice:
            payload["tool_choice"] = _openai_chat_tool_choice_to_responses_tool_choice(case.tool_choice)

        started = perf_counter()
        try:
            if case.streaming:
                return self._responses_stream(url, payload, case, started)
            response = self.client.post(url, headers=self._headers(), json=payload, timeout=case.timeout_seconds)
        except httpx.HTTPError as exc:
            raise AdapterError(f"OpenAI Responses request failed for {self.provider.name}: {exc}") from exc
        latency_ms = (perf_counter() - started) * 1000

        raw = response_json_or_metadata(response)
        tool_calls = extract_openai_responses_tool_calls(raw)

        return AdapterResponse(
            provider=self.provider.name,
            contract=ApiContract.OPENAI_RESPONSES,
            status_code=response.status_code,
            latency_ms=latency_ms,
            raw=raw,
            text=extract_openai_responses_text(raw),
            tool_names=_tool_names(tool_calls),
            tool_calls=tool_calls,
        )

    def _responses_stream(
        self,
        url: str,
        payload: dict[str, Any],
        case: BenchmarkCase,
        started: float,
    ) -> AdapterResponse:
        text_parts: list[str] = []
        raw_events: list[dict[str, Any]] = []
        tool_call_fragments: dict[str, dict[str, Any]] = {}
        usage: dict[str, Any] = {}
        status = None
        status_code = 0
        ttft_ms = None
        canceled = False
        cancellation_latency_ms = None
        try:
            with self.client.stream(
                "POST",
                url,
                headers=self._headers(),
                json=payload,
                timeout=case.timeout_seconds,
            ) as response:
                status_code = response.status_code
                for line in response.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        raw_events.append({"malformed": data})
                        continue
                    raw_events.append(event)
                    if ttft_ms is None and _openai_responses_stream_event_has_output(event):
                        ttft_ms = (perf_counter() - started) * 1000
                    _accumulate_openai_responses_stream_event(event, text_parts, tool_call_fragments, usage)
                    response_status = _openai_responses_stream_status(event)
                    if response_status:
                        status = response_status
                    cancellation_elapsed = _stream_cancellation_elapsed_ms(case, started)
                    if cancellation_elapsed is not None:
                        canceled = True
                        cancellation_latency_ms = cancellation_elapsed
                        break
        except httpx.HTTPError as exc:
            raise AdapterError(f"OpenAI Responses streaming request failed for {self.provider.name}: {exc}") from exc

        latency_ms = (perf_counter() - started) * 1000
        raw = {
            "stream": True,
            "events": raw_events,
            "usage": usage,
            "status": status,
            "agentblaster_http": _safe_http_metadata(response),
            "agentblaster_cancelled": canceled,
            "cancel_after_ms": case.cancel_after_ms,
            "cancellation_latency_ms": cancellation_latency_ms,
        }
        tool_calls = _openai_responses_stream_tool_calls(tool_call_fragments)
        return AdapterResponse(
            provider=self.provider.name,
            contract=ApiContract.OPENAI_RESPONSES,
            status_code=status_code,
            latency_ms=latency_ms,
            raw=raw,
            text="".join(text_parts),
            tool_names=_tool_names(tool_calls),
            tool_calls=tool_calls,
            streaming=True,
            ttft_ms=round(ttft_ms, 3) if ttft_ms is not None else None,
            canceled=canceled,
            cancellation_latency_ms=cancellation_latency_ms,
        )


class AnthropicCompatibleAdapter(ProviderAdapter):
    adapter_name = "anthropic-messages"

    def _auth_headers(self, api_key: str) -> dict[str, str]:
        return {
            "x-api-key": api_key,
            "anthropic-version": self.provider.headers.get("anthropic-version", "2023-06-01"),
        }

    def probe(self) -> ProbeResult:
        url = str(self.provider.base_url).rstrip("/") + "/models"
        try:
            response = self.client.get(url, headers=self._headers())
        except httpx.HTTPError as exc:
            raise AdapterError(f"Anthropic probe failed for {self.provider.name}: {exc}") from exc

        models: list[str] = []
        raw = response_json_or_metadata(response)
        data = raw.get("data", [])
        if isinstance(data, list):
            models = [str(item.get("id")) for item in data if isinstance(item, Mapping) and item.get("id")]

        return ProbeResult(
            provider=self.provider.name,
            contract=ApiContract.ANTHROPIC,
            ok=response.is_success,
            status_code=response.status_code,
            message="ok" if response.is_success else _redacted_response_text(response),
            models=models,
            raw=raw,
        )

    def chat_completion(self, model: str, case: BenchmarkCase) -> AdapterResponse:
        url = str(self.provider.base_url).rstrip("/") + "/messages"
        messages, system_prompt = _anthropic_messages_and_system_from_case(case)
        payload = {
            "model": model,
            "max_tokens": case.max_tokens,
            "temperature": case.temperature,
            "messages": messages,
        }
        if case.streaming:
            payload["stream"] = True
        if system_prompt:
            payload["system"] = system_prompt
        if case.tools:
            payload["tools"] = _anthropic_tools_from_case(case)
        if case.tool_choice:
            payload["tool_choice"] = _openai_tool_choice_to_anthropic(case.tool_choice)
        started = perf_counter()
        try:
            if case.streaming:
                return self._chat_completion_stream(url, payload, case, started)
            response = self.client.post(url, headers=self._headers(), json=payload, timeout=case.timeout_seconds)
        except httpx.HTTPError as exc:
            raise AdapterError(f"Anthropic smoke request failed for {self.provider.name}: {exc}") from exc
        latency_ms = (perf_counter() - started) * 1000

        raw = response_json_or_metadata(response)

        text_parts: list[str] = []
        content = raw.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, Mapping) and block.get("type") == "text":
                    text_parts.append(str(block.get("text") or ""))
        tool_calls = extract_anthropic_tool_calls(raw)

        return AdapterResponse(
            provider=self.provider.name,
            contract=ApiContract.ANTHROPIC,
            status_code=response.status_code,
            latency_ms=latency_ms,
            raw=raw,
            text="".join(text_parts),
            tool_names=_tool_names(tool_calls),
            tool_calls=tool_calls,
        )

    def _chat_completion_stream(
        self,
        url: str,
        payload: dict[str, Any],
        case: BenchmarkCase,
        started: float,
    ) -> AdapterResponse:
        text_parts: list[str] = []
        raw_events: list[dict[str, Any]] = []
        tool_call_fragments: dict[int, dict[str, Any]] = {}
        usage: dict[str, Any] = {}
        stop_reason = None
        status_code = 0
        ttft_ms = None
        canceled = False
        cancellation_latency_ms = None
        try:
            with self.client.stream(
                "POST",
                url,
                headers=self._headers(),
                json=payload,
                timeout=case.timeout_seconds,
            ) as response:
                status_code = response.status_code
                for line in response.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        raw_events.append({"malformed": data})
                        continue
                    raw_events.append(event)
                    if ttft_ms is None and _anthropic_stream_event_has_output(event):
                        ttft_ms = (perf_counter() - started) * 1000
                    _accumulate_anthropic_stream_event(event, text_parts, tool_call_fragments, usage)
                    event_stop_reason = _anthropic_stream_stop_reason(event)
                    if event_stop_reason:
                        stop_reason = event_stop_reason
                    cancellation_elapsed = _stream_cancellation_elapsed_ms(case, started)
                    if cancellation_elapsed is not None:
                        canceled = True
                        cancellation_latency_ms = cancellation_elapsed
                        break
        except httpx.HTTPError as exc:
            raise AdapterError(f"Anthropic streaming request failed for {self.provider.name}: {exc}") from exc

        latency_ms = (perf_counter() - started) * 1000
        raw = {
            "stream": True,
            "events": raw_events,
            "usage": usage,
            "stop_reason": stop_reason,
            "agentblaster_http": _safe_http_metadata(response),
            "agentblaster_cancelled": canceled,
            "cancel_after_ms": case.cancel_after_ms,
            "cancellation_latency_ms": cancellation_latency_ms,
        }
        tool_calls = _anthropic_stream_tool_calls(tool_call_fragments)
        return AdapterResponse(
            provider=self.provider.name,
            contract=ApiContract.ANTHROPIC,
            status_code=status_code,
            latency_ms=latency_ms,
            raw=raw,
            text="".join(text_parts),
            tool_names=_tool_names(tool_calls),
            tool_calls=tool_calls,
            streaming=True,
            ttft_ms=round(ttft_ms, 3) if ttft_ms is not None else None,
            canceled=canceled,
            cancellation_latency_ms=cancellation_latency_ms,
        )


class OllamaNativeAdapter(ProviderAdapter):
    """Adapter for Ollama's native `/api/*` contract."""

    adapter_name = "ollama-native"

    def _auth_headers(self, api_key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key}"}

    def probe(self) -> ProbeResult:
        url = str(self.provider.base_url).rstrip("/") + "/api/tags"
        try:
            response = self.client.get(url, headers=self._headers())
        except httpx.HTTPError as exc:
            raise AdapterError(f"Ollama native probe failed for {self.provider.name}: {exc}") from exc

        models: list[str] = []
        raw = response_json_or_metadata(response)
        data = raw.get("models", [])
        if isinstance(data, list):
            models = [
                str(item.get("name") or item.get("model"))
                for item in data
                if isinstance(item, Mapping) and (item.get("name") or item.get("model"))
            ]

        return ProbeResult(
            provider=self.provider.name,
            contract=ApiContract.NATIVE,
            ok=response.is_success,
            status_code=response.status_code,
            message="ok" if response.is_success else _redacted_response_text(response),
            models=models,
            raw=raw,
        )

    def chat_completion(self, model: str, case: BenchmarkCase) -> AdapterResponse:
        url = str(self.provider.base_url).rstrip("/") + "/api/chat"
        payload: dict[str, Any] = {
            "model": model,
            "messages": _openai_messages_from_case(case),
            "stream": False,
            "options": {
                "temperature": case.temperature,
                "num_predict": case.max_tokens,
            },
        }
        if case.tools:
            payload["tools"] = case.tools
        started = perf_counter()
        try:
            response = self.client.post(url, headers=self._headers(), json=payload, timeout=case.timeout_seconds)
        except httpx.HTTPError as exc:
            raise AdapterError(f"Ollama native chat request failed for {self.provider.name}: {exc}") from exc
        latency_ms = (perf_counter() - started) * 1000

        raw = response_json_or_metadata(response)

        message = raw.get("message", {})
        text = ""
        if isinstance(message, Mapping):
            text = str(message.get("content") or "")

        tool_calls = extract_ollama_tool_calls(raw)
        return AdapterResponse(
            provider=self.provider.name,
            contract=ApiContract.NATIVE,
            status_code=response.status_code,
            latency_ms=latency_ms,
            raw=raw,
            text=text,
            tool_names=_tool_names(tool_calls),
            tool_calls=tool_calls,
        )


class LMStudioNativeAdapter(ProviderAdapter):
    """Adapter for LM Studio's native `/api/v1/*` REST contract."""

    adapter_name = "lm-studio-native"

    def _auth_headers(self, api_key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key}"}

    def probe(self) -> ProbeResult:
        url = self._api_v1_base_url() + "/models"
        try:
            response = self.client.get(url, headers=self._headers())
        except httpx.HTTPError as exc:
            raise AdapterError(f"LM Studio native probe failed for {self.provider.name}: {exc}") from exc

        models: list[str] = []
        raw = response_json_or_metadata(response)
        data = raw.get("models", raw.get("data", []))
        if isinstance(data, list):
            models = [
                str(item.get("key") or item.get("id") or item.get("model"))
                for item in data
                if isinstance(item, Mapping) and (item.get("key") or item.get("id") or item.get("model"))
            ]

        return ProbeResult(
            provider=self.provider.name,
            contract=ApiContract.NATIVE,
            ok=response.is_success,
            status_code=response.status_code,
            message="ok" if response.is_success else _redacted_response_text(response),
            models=models,
            raw=raw,
        )

    def chat_completion(self, model: str, case: BenchmarkCase) -> AdapterResponse:
        url = self._api_v1_base_url() + "/chat"
        payload: dict[str, Any] = {
            "model": model,
            "input": case.prompt,
            "stream": False,
            "store": False,
            "temperature": case.temperature,
            "max_output_tokens": case.max_tokens,
        }
        if case.system_prompt:
            payload["system_prompt"] = case.system_prompt

        started = perf_counter()
        try:
            response = self.client.post(url, headers=self._headers(), json=payload, timeout=case.timeout_seconds)
        except httpx.HTTPError as exc:
            raise AdapterError(f"LM Studio native chat request failed for {self.provider.name}: {exc}") from exc
        latency_ms = (perf_counter() - started) * 1000

        raw = response_json_or_metadata(response)

        tool_calls = extract_lmstudio_tool_calls(raw)
        return AdapterResponse(
            provider=self.provider.name,
            contract=ApiContract.NATIVE,
            status_code=response.status_code,
            latency_ms=latency_ms,
            raw=raw,
            text=extract_lmstudio_text(raw),
            tool_names=_tool_names(tool_calls),
            tool_calls=tool_calls,
        )

    def _api_v1_base_url(self) -> str:
        base_url = str(self.provider.base_url).rstrip("/")
        if base_url.endswith("/api/v1"):
            return base_url
        return base_url + "/api/v1"


def adapter_for(
    provider: ProviderConfig,
    *,
    secrets: SecretResolver | None = None,
    client: httpx.Client | None = None,
    timeout: float = 10.0,
) -> ProviderAdapter:
    if provider.contract is ApiContract.OPENAI:
        return OpenAICompatibleAdapter(provider, secrets=secrets, client=client, timeout=timeout)
    if provider.contract is ApiContract.OPENAI_RESPONSES:
        return OpenAIResponsesAdapter(provider, secrets=secrets, client=client, timeout=timeout)
    if provider.contract is ApiContract.ANTHROPIC:
        return AnthropicCompatibleAdapter(provider, secrets=secrets, client=client, timeout=timeout)
    if provider.contract is ApiContract.NATIVE and provider.native_adapter == "ollama":
        return OllamaNativeAdapter(provider, secrets=secrets, client=client, timeout=timeout)
    if provider.contract is ApiContract.NATIVE and provider.native_adapter == "lm-studio":
        return LMStudioNativeAdapter(provider, secrets=secrets, client=client, timeout=timeout)
    raise AdapterError(f"no generic adapter exists for native provider: {provider.name}")


def response_json_or_metadata(response: httpx.Response) -> dict[str, Any]:
    content_type = response.headers.get("content-type", "")
    media_type = content_type.split(";", 1)[0].strip().lower()
    raw: dict[str, Any]
    if media_type == "application/json" or media_type.endswith("+json"):
        try:
            parsed = response.json()
        except json.JSONDecodeError:
            raw = {"agentblaster_parse_error": "invalid_json_response"}
        else:
            raw = dict(parsed) if isinstance(parsed, Mapping) else {"agentblaster_json": parsed}
    else:
        raw = {"agentblaster_non_json_response": True}
        preview = _redacted_body_preview(response)
        if preview:
            raw["agentblaster_body_preview"] = preview
    raw["agentblaster_http"] = _safe_http_metadata(response)
    return raw


def _safe_http_metadata(response: httpx.Response) -> dict[str, Any]:
    safe_headers = {
        key.lower(): value
        for key, value in response.headers.items()
        if key.lower() in SAFE_RESPONSE_HEADERS
    }
    return {
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type"),
        "headers": dict(redact_value(safe_headers)),
    }


def _redacted_body_preview(response: httpx.Response, *, limit: int = 240) -> str:
    try:
        text = response.text
    except UnicodeDecodeError:
        return "<binary response>"
    return str(redact_value(text[:limit]))


def _redacted_response_text(response: httpx.Response, *, limit: int = 240) -> str:
    return _redacted_body_preview(response, limit=limit)


def _openai_messages_from_case(case: BenchmarkCase, *, include_system_prompt: bool = True) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if include_system_prompt and case.system_prompt:
        messages.append({"role": "system", "content": case.system_prompt})
    if case.messages:
        messages.extend(_trace_message_to_openai(message) for message in case.messages)
        return messages

    messages.append({"role": "user", "content": case.prompt})
    return messages


def _trace_message_to_openai(message: Any) -> dict[str, Any]:
    data: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.name:
        data["name"] = message.name
    if message.tool_call_id:
        data["tool_call_id"] = message.tool_call_id
    if message.tool_calls:
        data["tool_calls"] = message.tool_calls
    return data


def _openai_responses_input_from_case(case: BenchmarkCase) -> str | list[dict[str, Any]]:
    if case.messages:
        return _openai_messages_from_case(case, include_system_prompt=False)
    return case.prompt


def _anthropic_messages_and_system_from_case(case: BenchmarkCase) -> tuple[list[dict[str, Any]], Any | None]:
    if not case.messages:
        return [{"role": "user", "content": case.prompt}], _anthropic_system_value(case.system_prompt, case.cache_control)

    system_parts: list[str] = []
    if case.system_prompt:
        system_parts.append(case.system_prompt)
    messages: list[dict[str, Any]] = []
    for message in case.messages:
        if message.role == "system":
            system_parts.append(_trace_content_text(message.content))
            continue
        if message.role == "tool":
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": message.tool_call_id or message.name or "toolu_agentblaster",
                            "content": _trace_content_text(message.content),
                        }
                    ],
                }
            )
            continue
        if message.role == "assistant":
            messages.append({"role": "assistant", "content": _anthropic_assistant_content(message)})
            continue
        messages.append({"role": "user", "content": message.content})

    system_text = "\n\n".join(part for part in system_parts if part) or None
    return messages, _anthropic_system_value(system_text, case.cache_control)


def _anthropic_system_value(text: str | None, cache_control: dict[str, Any] | None) -> str | list[dict[str, Any]] | None:
    if not text:
        return None
    if not cache_control:
        return text
    return [{"type": "text", "text": text, "cache_control": dict(cache_control)}]


def _anthropic_assistant_content(message: Any) -> str | list[dict[str, Any]]:
    if not message.tool_calls:
        return message.content

    blocks: list[dict[str, Any]] = []
    text = _trace_content_text(message.content)
    if text:
        blocks.append({"type": "text", "text": text})
    for tool_call in message.tool_calls:
        block = _openai_tool_call_to_anthropic_content_block(tool_call)
        if block is not None:
            blocks.append(block)
    return blocks


def _openai_tool_call_to_anthropic_content_block(tool_call: Mapping[str, Any]) -> dict[str, Any] | None:
    function = tool_call.get("function", {})
    if not isinstance(function, Mapping) or not function.get("name"):
        return None
    return {
        "type": "tool_use",
        "id": str(tool_call.get("id") or f"toolu_{function['name']}"),
        "name": str(function["name"]),
        "input": _parse_tool_arguments(function.get("arguments")),
    }


def _trace_content_text(content: str | list[dict[str, Any]]) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(content, sort_keys=True, separators=(",", ":"))


def extract_openai_tool_names(raw: Mapping[str, Any]) -> list[str]:
    return _tool_names(extract_openai_tool_calls(raw))


def _openai_stream_event_has_output(event: Mapping[str, Any]) -> bool:
    choices = event.get("choices", [])
    if not isinstance(choices, list):
        return False
    for choice in choices:
        if not isinstance(choice, Mapping):
            continue
        delta = choice.get("delta", {})
        if not isinstance(delta, Mapping):
            continue
        if delta.get("content"):
            return True
        if delta.get("tool_calls"):
            return True
    return False


def _accumulate_openai_stream_event(
    event: Mapping[str, Any],
    text_parts: list[str],
    tool_call_fragments: dict[int, dict[str, Any]],
) -> None:
    choices = event.get("choices", [])
    if not isinstance(choices, list):
        return
    for choice in choices:
        if not isinstance(choice, Mapping):
            continue
        delta = choice.get("delta", {})
        if not isinstance(delta, Mapping):
            continue
        if delta.get("content"):
            text_parts.append(str(delta["content"]))
        tool_calls = delta.get("tool_calls", [])
        if not isinstance(tool_calls, list):
            continue
        for tool_call in tool_calls:
            if not isinstance(tool_call, Mapping):
                continue
            index = int(tool_call.get("index") or 0)
            fragment = tool_call_fragments.setdefault(index, {"name": "", "arguments": ""})
            function = tool_call.get("function", {})
            if isinstance(function, Mapping):
                if function.get("name"):
                    fragment["name"] += str(function["name"])
                if function.get("arguments"):
                    fragment["arguments"] += str(function["arguments"])


def _stream_tool_calls(tool_call_fragments: dict[int, dict[str, Any]]) -> list[ToolCallRecord]:
    calls: list[ToolCallRecord] = []
    for index in sorted(tool_call_fragments):
        fragment = tool_call_fragments[index]
        if not fragment.get("name"):
            continue
        calls.append(
            ToolCallRecord(
                name=str(fragment["name"]),
                arguments=_parse_tool_arguments(fragment.get("arguments")),
            )
        )
    return calls


def _openai_responses_stream_event_has_output(event: Mapping[str, Any]) -> bool:
    event_type = event.get("type")
    if event_type in {"response.output_text.delta", "response.refusal.delta"}:
        return bool(event.get("delta"))
    if event_type == "response.function_call_arguments.delta":
        return bool(event.get("delta"))
    if event_type in {"response.output_item.added", "response.output_item.done"}:
        item = event.get("item", {})
        return isinstance(item, Mapping) and item.get("type") in {"function_call", "custom_tool_call"}
    return False


def _accumulate_openai_responses_stream_event(
    event: Mapping[str, Any],
    text_parts: list[str],
    tool_call_fragments: dict[str, dict[str, Any]],
    usage: dict[str, Any],
) -> None:
    event_type = event.get("type")
    if event_type == "response.output_text.delta":
        delta = event.get("delta")
        if delta:
            text_parts.append(str(delta))
        return
    if event_type == "response.refusal.delta":
        delta = event.get("delta")
        if delta:
            text_parts.append(str(delta))
        return
    if event_type in {"response.output_item.added", "response.output_item.done"}:
        _accumulate_openai_responses_output_item(event, tool_call_fragments)
        _update_openai_responses_usage_from_event(event, usage)
        return
    if event_type == "response.function_call_arguments.delta":
        fragment = _openai_responses_tool_fragment(event, tool_call_fragments)
        fragment["arguments"] += str(event.get("delta") or "")
        return
    if event_type == "response.function_call_arguments.done":
        fragment = _openai_responses_tool_fragment(event, tool_call_fragments)
        if event.get("name"):
            fragment["name"] = str(event["name"])
        if event.get("arguments") is not None:
            fragment["arguments"] = str(event.get("arguments") or "")
        return
    _update_openai_responses_usage_from_event(event, usage)


def _accumulate_openai_responses_output_item(
    event: Mapping[str, Any],
    tool_call_fragments: dict[str, dict[str, Any]],
) -> None:
    item = event.get("item", {})
    if not isinstance(item, Mapping):
        return
    if item.get("type") not in {"function_call", "custom_tool_call"}:
        return
    fragment = _openai_responses_tool_fragment(event, tool_call_fragments)
    if item.get("name"):
        fragment["name"] = str(item["name"])
    if item.get("arguments") is not None:
        fragment["arguments"] = str(item.get("arguments") or "")
    if item.get("input") is not None:
        fragment["arguments"] = json.dumps(item["input"], sort_keys=True) if isinstance(item["input"], Mapping) else str(item["input"])


def _openai_responses_tool_fragment(
    event: Mapping[str, Any],
    tool_call_fragments: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    key = str(event.get("item_id") or event.get("output_index") or len(tool_call_fragments))
    return tool_call_fragments.setdefault(key, {"name": "", "arguments": ""})


def _update_openai_responses_usage_from_event(event: Mapping[str, Any], usage: dict[str, Any]) -> None:
    response = event.get("response")
    if not isinstance(response, Mapping):
        return
    event_usage = response.get("usage")
    if isinstance(event_usage, Mapping):
        usage.update(dict(event_usage))


def _openai_responses_stream_status(event: Mapping[str, Any]) -> str | None:
    response = event.get("response")
    if isinstance(response, Mapping) and response.get("status"):
        return str(response["status"])
    event_type = event.get("type")
    if event_type == "response.completed":
        return "completed"
    if event_type == "response.failed":
        return "failed"
    if event_type == "response.incomplete":
        return "incomplete"
    return None


def _openai_responses_stream_tool_calls(tool_call_fragments: dict[str, dict[str, Any]]) -> list[ToolCallRecord]:
    calls: list[ToolCallRecord] = []
    for key in sorted(tool_call_fragments):
        fragment = tool_call_fragments[key]
        if not fragment.get("name"):
            continue
        calls.append(
            ToolCallRecord(
                name=str(fragment["name"]),
                arguments=_parse_tool_arguments(fragment.get("arguments")),
            )
        )
    return calls


def extract_openai_responses_text(raw: Mapping[str, Any]) -> str:
    if raw.get("output_text"):
        return str(raw["output_text"])

    text_parts: list[str] = []
    output = raw.get("output", [])
    if not isinstance(output, list):
        return ""
    for item in output:
        if not isinstance(item, Mapping) or item.get("type") != "message":
            continue
        content = item.get("content", [])
        if isinstance(content, str):
            text_parts.append(content)
            continue
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, Mapping):
                continue
            if part.get("type") in {"output_text", "text"}:
                text_parts.append(str(part.get("text") or ""))
    return "".join(text_parts)


def extract_openai_responses_tool_calls(raw: Mapping[str, Any]) -> list[ToolCallRecord]:
    calls: list[ToolCallRecord] = []
    output = raw.get("output", [])
    if not isinstance(output, list):
        return calls
    for item in output:
        if not isinstance(item, Mapping):
            continue
        if item.get("type") in {"function_call", "custom_tool_call"} and item.get("name"):
            calls.append(
                ToolCallRecord(
                    name=str(item["name"]),
                    arguments=_parse_tool_arguments(item.get("arguments") or item.get("input")),
                )
            )
    return calls


def extract_openai_tool_calls(raw: Mapping[str, Any]) -> list[ToolCallRecord]:
    calls: list[ToolCallRecord] = []
    choices = raw.get("choices", [])
    if not isinstance(choices, list):
        return calls
    for choice in choices:
        if not isinstance(choice, Mapping):
            continue
        message = choice.get("message", {})
        if not isinstance(message, Mapping):
            continue
        tool_calls = message.get("tool_calls", [])
        if not isinstance(tool_calls, list):
            continue
        for tool_call in tool_calls:
            if not isinstance(tool_call, Mapping):
                continue
            function = tool_call.get("function", {})
            if not isinstance(function, Mapping) or not function.get("name"):
                continue
            calls.append(
                ToolCallRecord(
                    name=str(function["name"]),
                    arguments=_parse_tool_arguments(function.get("arguments")),
                )
            )
    return calls


def _legacy_extract_openai_tool_names(raw: Mapping[str, Any]) -> list[str]:
    names: list[str] = []
    choices = raw.get("choices", [])
    if not isinstance(choices, list):
        return names
    for choice in choices:
        if not isinstance(choice, Mapping):
            continue
        message = choice.get("message", {})
        if not isinstance(message, Mapping):
            continue
        tool_calls = message.get("tool_calls", [])
        if not isinstance(tool_calls, list):
            continue
        for tool_call in tool_calls:
            if not isinstance(tool_call, Mapping):
                continue
            function = tool_call.get("function", {})
            if isinstance(function, Mapping) and function.get("name"):
                names.append(str(function["name"]))
    return names


def extract_anthropic_tool_names(raw: Mapping[str, Any]) -> list[str]:
    return _tool_names(extract_anthropic_tool_calls(raw))


def extract_anthropic_tool_calls(raw: Mapping[str, Any]) -> list[ToolCallRecord]:
    calls: list[ToolCallRecord] = []
    content = raw.get("content", [])
    if not isinstance(content, list):
        return calls
    for block in content:
        if isinstance(block, Mapping) and block.get("type") == "tool_use" and block.get("name"):
            arguments = block.get("input") if isinstance(block.get("input"), Mapping) else {}
            calls.append(ToolCallRecord(name=str(block["name"]), arguments=dict(arguments)))
    return calls


def _anthropic_stream_event_has_output(event: Mapping[str, Any]) -> bool:
    event_type = event.get("type")
    if event_type == "content_block_start":
        content_block = event.get("content_block", {})
        if not isinstance(content_block, Mapping):
            return False
        if content_block.get("type") == "text" and content_block.get("text"):
            return True
        return content_block.get("type") in {"tool_use", "server_tool_use"} and bool(content_block.get("name"))
    if event_type == "content_block_delta":
        delta = event.get("delta", {})
        if not isinstance(delta, Mapping):
            return False
        if delta.get("type") == "text_delta" and delta.get("text"):
            return True
        return delta.get("type") == "input_json_delta" and bool(delta.get("partial_json"))
    return False


def _accumulate_anthropic_stream_event(
    event: Mapping[str, Any],
    text_parts: list[str],
    tool_call_fragments: dict[int, dict[str, Any]],
    usage: dict[str, Any],
) -> None:
    event_type = event.get("type")
    if event_type == "message_start":
        message = event.get("message", {})
        if isinstance(message, Mapping):
            _update_anthropic_stream_usage(usage, message.get("usage"))
        return
    if event_type == "message_delta":
        _update_anthropic_stream_usage(usage, event.get("usage"))
        return
    if event_type == "content_block_start":
        _accumulate_anthropic_content_block_start(event, text_parts, tool_call_fragments)
        return
    if event_type == "content_block_delta":
        _accumulate_anthropic_content_block_delta(event, text_parts, tool_call_fragments)


def _update_anthropic_stream_usage(usage: dict[str, Any], value: Any) -> None:
    if isinstance(value, Mapping):
        usage.update(dict(value))


def _accumulate_anthropic_content_block_start(
    event: Mapping[str, Any],
    text_parts: list[str],
    tool_call_fragments: dict[int, dict[str, Any]],
) -> None:
    content_block = event.get("content_block", {})
    if not isinstance(content_block, Mapping):
        return
    block_type = content_block.get("type")
    if block_type == "text":
        text = content_block.get("text")
        if text:
            text_parts.append(str(text))
        return
    if block_type not in {"tool_use", "server_tool_use"}:
        return

    index = _event_index(event)
    fragment = tool_call_fragments.setdefault(index, {"name": "", "arguments": "", "arguments_object": {}})
    if content_block.get("name"):
        fragment["name"] = str(content_block["name"])
    input_value = content_block.get("input")
    if isinstance(input_value, Mapping) and input_value:
        fragment["arguments_object"] = dict(input_value)


def _accumulate_anthropic_content_block_delta(
    event: Mapping[str, Any],
    text_parts: list[str],
    tool_call_fragments: dict[int, dict[str, Any]],
) -> None:
    delta = event.get("delta", {})
    if not isinstance(delta, Mapping):
        return
    delta_type = delta.get("type")
    if delta_type == "text_delta":
        text = delta.get("text")
        if text:
            text_parts.append(str(text))
        return
    if delta_type != "input_json_delta":
        return

    index = _event_index(event)
    fragment = tool_call_fragments.setdefault(index, {"name": "", "arguments": "", "arguments_object": {}})
    if "partial_json" in delta:
        fragment["arguments"] += str(delta.get("partial_json") or "")


def _anthropic_stream_stop_reason(event: Mapping[str, Any]) -> str | None:
    if event.get("type") != "message_delta":
        return None
    delta = event.get("delta", {})
    if isinstance(delta, Mapping) and delta.get("stop_reason"):
        return str(delta["stop_reason"])
    return None


def _anthropic_stream_tool_calls(tool_call_fragments: dict[int, dict[str, Any]]) -> list[ToolCallRecord]:
    calls: list[ToolCallRecord] = []
    for index in sorted(tool_call_fragments):
        fragment = tool_call_fragments[index]
        if not fragment.get("name"):
            continue
        argument_fragments = fragment.get("arguments")
        if argument_fragments:
            arguments = _parse_tool_arguments(argument_fragments)
        else:
            arguments_object = fragment.get("arguments_object")
            arguments = dict(arguments_object) if isinstance(arguments_object, Mapping) else {}
        calls.append(ToolCallRecord(name=str(fragment["name"]), arguments=arguments))
    return calls


def _event_index(event: Mapping[str, Any]) -> int:
    try:
        return int(event.get("index") or 0)
    except (TypeError, ValueError):
        return 0


def _legacy_extract_anthropic_tool_names(raw: Mapping[str, Any]) -> list[str]:
    names: list[str] = []
    content = raw.get("content", [])
    if not isinstance(content, list):
        return names
    for block in content:
        if isinstance(block, Mapping) and block.get("type") == "tool_use" and block.get("name"):
            names.append(str(block["name"]))
    return names


def extract_ollama_tool_names(raw: Mapping[str, Any]) -> list[str]:
    return _tool_names(extract_ollama_tool_calls(raw))


def extract_ollama_tool_calls(raw: Mapping[str, Any]) -> list[ToolCallRecord]:
    calls: list[ToolCallRecord] = []
    message = raw.get("message", {})
    if not isinstance(message, Mapping):
        return calls
    tool_calls = message.get("tool_calls", [])
    if not isinstance(tool_calls, list):
        return calls
    for tool_call in tool_calls:
        if not isinstance(tool_call, Mapping):
            continue
        function = tool_call.get("function", {})
        if isinstance(function, Mapping) and function.get("name"):
            calls.append(
                ToolCallRecord(
                    name=str(function["name"]),
                    arguments=_parse_tool_arguments(function.get("arguments")),
                )
            )
    return calls


def _legacy_extract_ollama_tool_names(raw: Mapping[str, Any]) -> list[str]:
    names: list[str] = []
    message = raw.get("message", {})
    if not isinstance(message, Mapping):
        return names
    tool_calls = message.get("tool_calls", [])
    if not isinstance(tool_calls, list):
        return names
    for tool_call in tool_calls:
        if not isinstance(tool_call, Mapping):
            continue
        function = tool_call.get("function", {})
        if isinstance(function, Mapping) and function.get("name"):
            names.append(str(function["name"]))
    return names


def extract_lmstudio_text(raw: Mapping[str, Any]) -> str:
    output = raw.get("output", [])
    if isinstance(output, list):
        text_parts = [
            str(item.get("content") or "")
            for item in output
            if isinstance(item, Mapping) and item.get("type") == "message"
        ]
        if text_parts:
            return "".join(text_parts)

    choices = raw.get("choices", [])
    if choices and isinstance(choices, list) and isinstance(choices[0], Mapping):
        message = choices[0].get("message", {})
        if isinstance(message, Mapping):
            return str(message.get("content") or "")

    message = raw.get("message", {})
    if isinstance(message, Mapping):
        return str(message.get("content") or "")

    return ""


def extract_lmstudio_tool_names(raw: Mapping[str, Any]) -> list[str]:
    return _tool_names(extract_lmstudio_tool_calls(raw))


def extract_lmstudio_tool_calls(raw: Mapping[str, Any]) -> list[ToolCallRecord]:
    calls: list[ToolCallRecord] = []
    output = raw.get("output", [])
    if not isinstance(output, list):
        return calls
    for item in output:
        if not isinstance(item, Mapping):
            continue
        if item.get("type") == "tool_call" and item.get("tool"):
            arguments = item.get("arguments") if isinstance(item.get("arguments"), Mapping) else {}
            calls.append(ToolCallRecord(name=str(item["tool"]), arguments=dict(arguments)))
        elif item.get("type") == "invalid_tool_call":
            metadata = item.get("metadata", {})
            if isinstance(metadata, Mapping) and metadata.get("tool_name"):
                arguments = metadata.get("arguments") if isinstance(metadata.get("arguments"), Mapping) else {}
                calls.append(ToolCallRecord(name=str(metadata["tool_name"]), arguments=dict(arguments), valid=False))
    return calls


def _tool_names(calls: list[ToolCallRecord]) -> list[str]:
    return [call.name for call in calls]


def _stream_cancellation_elapsed_ms(case: BenchmarkCase, started: float) -> float | None:
    if case.cancel_after_ms is None:
        return None
    elapsed_ms = (perf_counter() - started) * 1000
    if elapsed_ms < case.cancel_after_ms:
        return None
    return round(elapsed_ms, 3)


def _parse_tool_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, Mapping):
            return dict(parsed)
    return {}


def _openai_tool_to_anthropic(tool: Mapping[str, Any]) -> dict[str, Any]:
    if tool.get("type") == "function" and isinstance(tool.get("function"), Mapping):
        function = tool["function"]
        converted = {
            "name": function.get("name"),
            "description": function.get("description", ""),
            "input_schema": function.get("parameters", {"type": "object", "properties": {}}),
        }
        cache_control = tool.get("cache_control") or function.get("cache_control")
        if isinstance(cache_control, Mapping):
            converted["cache_control"] = dict(cache_control)
        return converted
    return dict(tool)


def _anthropic_tools_from_case(case: BenchmarkCase) -> list[dict[str, Any]]:
    tools = [_openai_tool_to_anthropic(tool) for tool in case.tools]
    if tools and case.cache_control and "cache_control" not in tools[-1]:
        tools[-1] = {**tools[-1], "cache_control": dict(case.cache_control)}
    return tools


def _openai_chat_tool_to_responses_tool(tool: Mapping[str, Any]) -> dict[str, Any]:
    if tool.get("type") == "function" and isinstance(tool.get("function"), Mapping):
        function = tool["function"]
        converted = {
            "type": "function",
            "name": function.get("name"),
            "description": function.get("description", ""),
            "parameters": function.get("parameters", {"type": "object", "properties": {}}),
        }
        if "strict" in function:
            converted["strict"] = function["strict"]
        return converted
    return dict(tool)


def _openai_chat_tool_choice_to_responses_tool_choice(tool_choice: str | Mapping[str, Any]) -> str | dict[str, Any]:
    if isinstance(tool_choice, str):
        return tool_choice
    if tool_choice.get("type") == "function" and isinstance(tool_choice.get("function"), Mapping):
        function = tool_choice["function"]
        if function.get("name"):
            return {"type": "function", "name": function["name"]}
    return dict(tool_choice)


def _openai_tool_choice_to_anthropic(tool_choice: str | Mapping[str, Any]) -> str | dict[str, Any]:
    if isinstance(tool_choice, str):
        if tool_choice in {"auto", "any", "none"}:
            return tool_choice
        return {"type": "tool", "name": tool_choice}
    if tool_choice.get("type") == "function" and isinstance(tool_choice.get("function"), Mapping):
        return {"type": "tool", "name": str(tool_choice["function"].get("name"))}
    return dict(tool_choice)
