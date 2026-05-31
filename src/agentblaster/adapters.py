from __future__ import annotations

from collections.abc import Mapping
from time import perf_counter
from typing import Any

import httpx

from agentblaster.errors import AdapterError
from agentblaster.models import AdapterResponse, ApiContract, BenchmarkCase, ProbeResult, ProviderConfig
from agentblaster.secrets import SecretResolver


class ProviderAdapter:
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
        self.client = client or httpx.Client(timeout=timeout)

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


class OpenAICompatibleAdapter(ProviderAdapter):
    def _auth_headers(self, api_key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key}"}

    def probe(self) -> ProbeResult:
        url = str(self.provider.base_url).rstrip("/") + "/models"
        try:
            response = self.client.get(url, headers=self._headers())
        except httpx.HTTPError as exc:
            raise AdapterError(f"OpenAI probe failed for {self.provider.name}: {exc}") from exc

        models: list[str] = []
        raw: dict[str, Any] = {}
        if response.headers.get("content-type", "").startswith("application/json"):
            raw = response.json()
            data = raw.get("data", [])
            if isinstance(data, list):
                models = [str(item.get("id")) for item in data if isinstance(item, Mapping) and item.get("id")]

        return ProbeResult(
            provider=self.provider.name,
            contract=ApiContract.OPENAI,
            ok=response.is_success,
            status_code=response.status_code,
            message="ok" if response.is_success else response.text[:240],
            models=models,
            raw=raw,
        )

    def chat_completion(self, model: str, case: BenchmarkCase) -> AdapterResponse:
        url = str(self.provider.base_url).rstrip("/") + "/chat/completions"
        messages = []
        if case.system_prompt:
            messages.append({"role": "system", "content": case.system_prompt})
        messages.append({"role": "user", "content": case.prompt})
        payload = {
            "model": model,
            "messages": messages,
            "temperature": case.temperature,
            "max_tokens": case.max_tokens,
        }
        if case.response_format:
            payload["response_format"] = case.response_format
        if case.tools:
            payload["tools"] = case.tools
        if case.tool_choice:
            payload["tool_choice"] = case.tool_choice
        started = perf_counter()
        try:
            response = self.client.post(url, headers=self._headers(), json=payload)
        except httpx.HTTPError as exc:
            raise AdapterError(f"OpenAI smoke request failed for {self.provider.name}: {exc}") from exc
        latency_ms = (perf_counter() - started) * 1000

        raw: dict[str, Any] = {}
        if response.headers.get("content-type", "").startswith("application/json"):
            raw = response.json()

        text = ""
        choices = raw.get("choices", [])
        if choices and isinstance(choices[0], Mapping):
            message = choices[0].get("message", {})
            if isinstance(message, Mapping):
                text = str(message.get("content") or "")
        tool_names = extract_openai_tool_names(raw)

        return AdapterResponse(
            provider=self.provider.name,
            contract=ApiContract.OPENAI,
            status_code=response.status_code,
            latency_ms=latency_ms,
            raw=raw,
            text=text,
            tool_names=tool_names,
        )


class AnthropicCompatibleAdapter(ProviderAdapter):
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
        raw: dict[str, Any] = {}
        if response.headers.get("content-type", "").startswith("application/json"):
            raw = response.json()
            data = raw.get("data", [])
            if isinstance(data, list):
                models = [str(item.get("id")) for item in data if isinstance(item, Mapping) and item.get("id")]

        return ProbeResult(
            provider=self.provider.name,
            contract=ApiContract.ANTHROPIC,
            ok=response.is_success,
            status_code=response.status_code,
            message="ok" if response.is_success else response.text[:240],
            models=models,
            raw=raw,
        )

    def chat_completion(self, model: str, case: BenchmarkCase) -> AdapterResponse:
        url = str(self.provider.base_url).rstrip("/") + "/messages"
        payload = {
            "model": model,
            "max_tokens": case.max_tokens,
            "temperature": case.temperature,
            "messages": [{"role": "user", "content": case.prompt}],
        }
        if case.system_prompt:
            payload["system"] = case.system_prompt
        if case.tools:
            payload["tools"] = [_openai_tool_to_anthropic(tool) for tool in case.tools]
        if case.tool_choice:
            payload["tool_choice"] = _openai_tool_choice_to_anthropic(case.tool_choice)
        started = perf_counter()
        try:
            response = self.client.post(url, headers=self._headers(), json=payload)
        except httpx.HTTPError as exc:
            raise AdapterError(f"Anthropic smoke request failed for {self.provider.name}: {exc}") from exc
        latency_ms = (perf_counter() - started) * 1000

        raw: dict[str, Any] = {}
        if response.headers.get("content-type", "").startswith("application/json"):
            raw = response.json()

        text_parts: list[str] = []
        content = raw.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, Mapping) and block.get("type") == "text":
                    text_parts.append(str(block.get("text") or ""))
        tool_names = extract_anthropic_tool_names(raw)

        return AdapterResponse(
            provider=self.provider.name,
            contract=ApiContract.ANTHROPIC,
            status_code=response.status_code,
            latency_ms=latency_ms,
            raw=raw,
            text="".join(text_parts),
            tool_names=tool_names,
        )


class OllamaNativeAdapter(ProviderAdapter):
    """Adapter for Ollama's native `/api/*` contract."""

    def _auth_headers(self, api_key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key}"}

    def probe(self) -> ProbeResult:
        url = str(self.provider.base_url).rstrip("/") + "/api/tags"
        try:
            response = self.client.get(url, headers=self._headers())
        except httpx.HTTPError as exc:
            raise AdapterError(f"Ollama native probe failed for {self.provider.name}: {exc}") from exc

        models: list[str] = []
        raw: dict[str, Any] = {}
        if response.headers.get("content-type", "").startswith("application/json"):
            raw = response.json()
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
            message="ok" if response.is_success else response.text[:240],
            models=models,
            raw=raw,
        )

    def chat_completion(self, model: str, case: BenchmarkCase) -> AdapterResponse:
        url = str(self.provider.base_url).rstrip("/") + "/api/chat"
        messages = []
        if case.system_prompt:
            messages.append({"role": "system", "content": case.system_prompt})
        messages.append({"role": "user", "content": case.prompt})
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
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
            response = self.client.post(url, headers=self._headers(), json=payload)
        except httpx.HTTPError as exc:
            raise AdapterError(f"Ollama native chat request failed for {self.provider.name}: {exc}") from exc
        latency_ms = (perf_counter() - started) * 1000

        raw: dict[str, Any] = {}
        if response.headers.get("content-type", "").startswith("application/json"):
            raw = response.json()

        message = raw.get("message", {})
        text = ""
        if isinstance(message, Mapping):
            text = str(message.get("content") or "")

        return AdapterResponse(
            provider=self.provider.name,
            contract=ApiContract.NATIVE,
            status_code=response.status_code,
            latency_ms=latency_ms,
            raw=raw,
            text=text,
            tool_names=extract_ollama_tool_names(raw),
        )


def adapter_for(provider: ProviderConfig, *, secrets: SecretResolver | None = None) -> ProviderAdapter:
    if provider.contract is ApiContract.OPENAI:
        return OpenAICompatibleAdapter(provider, secrets=secrets)
    if provider.contract is ApiContract.ANTHROPIC:
        return AnthropicCompatibleAdapter(provider, secrets=secrets)
    if provider.contract is ApiContract.NATIVE and provider.native_adapter == "ollama":
        return OllamaNativeAdapter(provider, secrets=secrets)
    raise AdapterError(f"no generic adapter exists for native provider: {provider.name}")


def extract_openai_tool_names(raw: Mapping[str, Any]) -> list[str]:
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
    names: list[str] = []
    content = raw.get("content", [])
    if not isinstance(content, list):
        return names
    for block in content:
        if isinstance(block, Mapping) and block.get("type") == "tool_use" and block.get("name"):
            names.append(str(block["name"]))
    return names


def extract_ollama_tool_names(raw: Mapping[str, Any]) -> list[str]:
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


def _openai_tool_to_anthropic(tool: Mapping[str, Any]) -> dict[str, Any]:
    if tool.get("type") == "function" and isinstance(tool.get("function"), Mapping):
        function = tool["function"]
        return {
            "name": function.get("name"),
            "description": function.get("description", ""),
            "input_schema": function.get("parameters", {"type": "object", "properties": {}}),
        }
    return dict(tool)


def _openai_tool_choice_to_anthropic(tool_choice: str | Mapping[str, Any]) -> str | dict[str, Any]:
    if isinstance(tool_choice, str):
        if tool_choice in {"auto", "any", "none"}:
            return tool_choice
        return {"type": "tool", "name": tool_choice}
    if tool_choice.get("type") == "function" and isinstance(tool_choice.get("function"), Mapping):
        return {"type": "tool", "name": str(tool_choice["function"].get("name"))}
    return dict(tool_choice)
