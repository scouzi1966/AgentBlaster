from __future__ import annotations

from collections.abc import Mapping
from time import perf_counter
from typing import Any

import httpx

from agentblaster.errors import AdapterError
from agentblaster.models import AdapterResponse, ApiContract, ProbeResult, ProviderConfig
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

    def smoke_chat(self, model: str) -> AdapterResponse:
        url = str(self.provider.base_url).rstrip("/") + "/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Reply with exactly: agentblaster-ok"}],
            "temperature": 0,
            "max_tokens": 16,
        }
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

        return AdapterResponse(
            provider=self.provider.name,
            contract=ApiContract.OPENAI,
            status_code=response.status_code,
            latency_ms=latency_ms,
            raw=raw,
            text=text,
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

    def smoke_chat(self, model: str) -> AdapterResponse:
        url = str(self.provider.base_url).rstrip("/") + "/messages"
        payload = {
            "model": model,
            "max_tokens": 16,
            "temperature": 0,
            "messages": [{"role": "user", "content": "Reply with exactly: agentblaster-ok"}],
        }
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

        return AdapterResponse(
            provider=self.provider.name,
            contract=ApiContract.ANTHROPIC,
            status_code=response.status_code,
            latency_ms=latency_ms,
            raw=raw,
            text="".join(text_parts),
        )


def adapter_for(provider: ProviderConfig, *, secrets: SecretResolver | None = None) -> ProviderAdapter:
    if provider.contract is ApiContract.OPENAI:
        return OpenAICompatibleAdapter(provider, secrets=secrets)
    if provider.contract is ApiContract.ANTHROPIC:
        return AnthropicCompatibleAdapter(provider, secrets=secrets)
    raise AdapterError(f"no generic adapter exists for native provider: {provider.name}")
