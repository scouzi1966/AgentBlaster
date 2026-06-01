from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from agentblaster.adapters import ProviderAdapter, adapter_for
from agentblaster.errors import AdapterError, ConfigError
from agentblaster.models import ApiContract, BenchmarkCase, ProviderConfig


@dataclass(frozen=True)
class ContractCheckSpec:
    id: str
    title: str
    purpose: str
    required_capability: str | None = None


CONTRACT_CHECK_SCHEMA_VERSION = "agentblaster.provider-contract-check.v1"
SUPPORTED_CONTRACTS = {ApiContract.OPENAI, ApiContract.OPENAI_RESPONSES, ApiContract.ANTHROPIC}


def contract_check_specs(
    contract: ApiContract,
    *,
    include_streaming: bool = True,
    include_structured: bool = True,
    include_tools: bool = True,
) -> list[ContractCheckSpec]:
    specs = [
        ContractCheckSpec(
            id="model-list",
            title="Model list probe",
            purpose="Verify the provider exposes a model discovery endpoint with JSON response shape.",
        ),
        ContractCheckSpec(
            id="exact-chat",
            title="Exact chat response",
            purpose="Verify a minimal deterministic prompt can return expected assistant text.",
        ),
    ]
    if include_streaming:
        specs.append(
            ContractCheckSpec(
                id="streaming-text",
                title="Streaming text response",
                purpose="Verify streaming events can be consumed and assembled into assistant text.",
                required_capability="streaming",
            )
        )
    if include_structured and contract in {ApiContract.OPENAI, ApiContract.OPENAI_RESPONSES}:
        specs.append(
            ContractCheckSpec(
                id="structured-json",
                title="Structured JSON response",
                purpose="Verify JSON response-format requests produce parseable JSON content.",
                required_capability="structured_output",
            )
        )
    if include_tools:
        specs.append(
            ContractCheckSpec(
                id="tool-call",
                title="Tool call response",
                purpose="Verify the provider emits a valid call to a requested function/tool schema.",
                required_capability="tool_calling",
            )
        )
    return specs


def provider_contract_plan(
    provider: ProviderConfig,
    *,
    model: str | None = None,
    include_streaming: bool = True,
    include_structured: bool = True,
    include_tools: bool = True,
) -> dict[str, Any]:
    if provider.contract not in SUPPORTED_CONTRACTS:
        raise ConfigError("provider contract-check supports openai, openai-responses, and anthropic providers")
    specs = contract_check_specs(
        provider.contract,
        include_streaming=include_streaming,
        include_structured=include_structured,
        include_tools=include_tools,
    )
    return {
        "schema_version": CONTRACT_CHECK_SCHEMA_VERSION,
        "mode": "plan-only",
        "provider": _provider_identity(provider),
        "model": model or provider.default_model or "<required>",
        "checks": [_planned_check(spec, provider) for spec in specs],
        "summary": {"planned": len(specs), "passed": 0, "failed": 0, "skipped": 0},
        "safety": {
            "contacts_provider": False,
            "remote_execution_requires_allow_remote": True,
            "stores_raw_secrets": False,
        },
    }


def run_provider_contract_check(
    provider: ProviderConfig,
    *,
    model: str | None = None,
    allow_remote: bool = False,
    include_streaming: bool = True,
    include_structured: bool = True,
    include_tools: bool = True,
    timeout: float = 10.0,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    if provider.contract not in SUPPORTED_CONTRACTS:
        raise ConfigError("provider contract-check supports openai, openai-responses, and anthropic providers")
    if provider.remote and not allow_remote:
        raise ConfigError("contract-check refuses remote providers unless --allow-remote is set")
    resolved_model = model or provider.default_model
    if not resolved_model:
        raise ConfigError("contract-check execution requires --model or a provider default_model")
    adapter_kwargs: dict[str, Any] = {"timeout": timeout}
    if client is not None:
        adapter_kwargs["client"] = client
    adapter = adapter_for(provider, **adapter_kwargs)
    specs = contract_check_specs(
        provider.contract,
        include_streaming=include_streaming,
        include_structured=include_structured,
        include_tools=include_tools,
    )
    results = [_execute_check(adapter, spec, resolved_model) for spec in specs]
    passed = sum(1 for result in results if result["status"] == "passed")
    failed = sum(1 for result in results if result["status"] == "failed")
    skipped = sum(1 for result in results if result["status"] == "skipped")
    return {
        "schema_version": CONTRACT_CHECK_SCHEMA_VERSION,
        "mode": "executed",
        "provider": _provider_identity(provider),
        "model": resolved_model,
        "checks": results,
        "summary": {"planned": len(specs), "passed": passed, "failed": failed, "skipped": skipped},
        "safety": {
            "contacts_provider": True,
            "remote_execution_allowed": allow_remote,
            "stores_raw_secrets": False,
        },
    }


def write_contract_check_json(report: dict[str, Any], output: str | Any) -> None:
    from pathlib import Path

    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "
", encoding="utf-8")


def format_contract_check_report(report: dict[str, Any]) -> str:
    provider = report["provider"]
    lines = [
        "AgentBlaster provider contract check",
        f"mode: {report['mode']}",
        f"provider: {provider['name']} ({provider['contract']})",
        f"endpoint_host: {provider.get('base_url_host') or 'unknown'}",
        f"remote: {str(provider.get('remote')).lower()}",
        f"model: {report['model']}",
        "checks:",
    ]
    for check in report["checks"]:
        status = check["status"].upper()
        capability = f" capability={check['required_capability']}" if check.get("required_capability") else ""
        lines.append(f"- {status} {check['id']}: {check['title']}{capability}")
        if check.get("message"):
            lines.append(f"  {check['message']}")
    summary = report["summary"]
    lines.append(
        f"summary: planned={summary['planned']} passed={summary['passed']} failed={summary['failed']} skipped={summary['skipped']}"
    )
    return "
".join(lines) + "
"


def _planned_check(spec: ContractCheckSpec, provider: ProviderConfig) -> dict[str, Any]:
    declared = None
    if spec.required_capability:
        declared = provider.capabilities.get(spec.required_capability)
    return {
        "id": spec.id,
        "title": spec.title,
        "purpose": spec.purpose,
        "required_capability": spec.required_capability,
        "declared_capability": declared,
        "status": "planned",
    }


def _execute_check(adapter: ProviderAdapter, spec: ContractCheckSpec, model: str) -> dict[str, Any]:
    try:
        if spec.id == "model-list":
            probe = adapter.probe()
            ok = probe.ok and probe.status_code is not None and 200 <= probe.status_code < 300
            return _result(spec, ok=ok, message=f"status={probe.status_code} models={len(probe.models)}")
        if spec.id == "exact-chat":
            response = adapter.chat_completion(model, _exact_case())
            return _result(spec, ok=_response_ok(response.status_code) and "agentblaster-ok" in response.text, message=_response_message(response))
        if spec.id == "streaming-text":
            response = adapter.chat_completion(model, _streaming_case())
            return _result(
                spec,
                ok=_response_ok(response.status_code) and response.streaming and "agentblaster-ok" in response.text,
                message=_response_message(response),
            )
        if spec.id == "structured-json":
            response = adapter.chat_completion(model, _structured_case())
            parsed = _json_object(response.text)
            return _result(
                spec,
                ok=_response_ok(response.status_code) and parsed is not None and parsed.get("status") == "agentblaster-ok",
                message=_response_message(response),
            )
        if spec.id == "tool-call":
            response = adapter.chat_completion(model, _tool_case())
            return _result(
                spec,
                ok=_response_ok(response.status_code) and "ping_agentblaster" in response.tool_names,
                message=_response_message(response),
            )
        return _result(spec, status="skipped", ok=False, message="unknown check id")
    except (AdapterError, ConfigError, httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
        return _result(spec, ok=False, message=f"{type(exc).__name__}: {exc}")


def _result(
    spec: ContractCheckSpec,
    *,
    ok: bool,
    message: str,
    status: str | None = None,
) -> dict[str, Any]:
    resolved_status = status or ("passed" if ok else "failed")
    return {
        "id": spec.id,
        "title": spec.title,
        "purpose": spec.purpose,
        "required_capability": spec.required_capability,
        "status": resolved_status,
        "ok": resolved_status == "passed",
        "message": message[:500],
    }


def _exact_case() -> BenchmarkCase:
    return BenchmarkCase(
        id="contract-exact-chat",
        title="Contract exact chat",
        prompt="Reply with exactly: agentblaster-ok",
        expected_substring="agentblaster-ok",
        max_tokens=16,
        timeout_seconds=10.0,
    )


def _streaming_case() -> BenchmarkCase:
    return BenchmarkCase(
        id="contract-streaming-text",
        title="Contract streaming text",
        prompt="Reply with exactly: agentblaster-ok",
        expected_substring="agentblaster-ok",
        streaming=True,
        max_tokens=16,
        timeout_seconds=10.0,
    )


def _structured_case() -> BenchmarkCase:
    return BenchmarkCase(
        id="contract-structured-json",
        title="Contract structured JSON",
        system_prompt="Return only valid JSON. Do not use markdown.",
        prompt='Return exactly this JSON object: {"status":"agentblaster-ok","marker":"contract-json"}',
        expected_json_fields={"status": "agentblaster-ok", "marker": "contract-json"},
        response_format={"type": "json_object"},
        max_tokens=64,
        timeout_seconds=10.0,
    )


def _tool_case() -> BenchmarkCase:
    return BenchmarkCase(
        id="contract-tool-call",
        title="Contract tool call",
        prompt="Call ping_agentblaster with target set to contract-tool.",
        expected_tool_name="ping_agentblaster",
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "ping_agentblaster",
                    "description": "Ping the AgentBlaster contract checker.",
                    "parameters": {
                        "type": "object",
                        "properties": {"target": {"type": "string"}},
                        "required": ["target"],
                        "additionalProperties": False,
                    },
                },
            }
        ],
        tool_choice={"type": "function", "function": {"name": "ping_agentblaster"}},
        max_tokens=64,
        timeout_seconds=10.0,
    )


def _response_ok(status_code: int | None) -> bool:
    return status_code is not None and 200 <= status_code < 300


def _response_message(response: Any) -> str:
    parts = [f"status={response.status_code}"]
    if getattr(response, "text", None):
        parts.append(f"text={str(response.text)[:120]}")
    tool_names = getattr(response, "tool_names", None)
    if tool_names:
        parts.append(f"tools={','.join(tool_names)}")
    if getattr(response, "ttft_ms", None) is not None:
        parts.append(f"ttft_ms={response.ttft_ms}")
    return " ".join(parts)


def _json_object(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _provider_identity(provider: ProviderConfig) -> dict[str, Any]:
    parsed = urlparse(str(provider.base_url))
    return {
        "name": provider.name,
        "contract": provider.contract.value,
        "base_url_host": parsed.hostname,
        "remote": provider.remote,
        "native_adapter": provider.native_adapter,
        "capabilities": dict(provider.capabilities),
        "tls_verify": provider.tls_verify,
        "has_api_key_ref": provider.api_key_ref is not None,
    }
