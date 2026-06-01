from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from agentblaster.adapters import ProviderAdapter, adapter_for
from agentblaster.config import ProviderStore
from agentblaster.errors import AdapterError, ConfigError
from agentblaster.matrix import MatrixRun, load_matrix_file
from agentblaster.models import ApiContract, BenchmarkCase, ProviderConfig


@dataclass(frozen=True)
class ContractCheckSpec:
    id: str
    title: str
    purpose: str
    required_capability: str | None = None


CONTRACT_CHECK_SCHEMA_VERSION = "agentblaster.provider-contract-check.v1"
CONTRACT_CHECK_MATRIX_SCHEMA_VERSION = "agentblaster.provider-contract-matrix.v1"
CONTRACT_SURFACE_SCHEMA_VERSION = "agentblaster.provider-contract-surface.v1"
SUPPORTED_CONTRACTS = {ApiContract.OPENAI, ApiContract.OPENAI_RESPONSES, ApiContract.ANTHROPIC}
PROXY_CAPABILITY_COVERAGE = {
    "judge_rubric": "structured_output",
}
SEPARATE_BENCHMARK_EVIDENCE_CAPABILITIES = {
    "tool_parser_repair": (
        "Generic tool-call contract checks prove only API-native call emission for a requested tool. "
        "They do not prove strict rejection, repair, or classification of raw JSON/XML/markdown/ReAct text; "
        "use tool-parser-repair benchmark runs and invalid_tool_call_count evidence."
    ),
}


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
    if contract is ApiContract.OPENAI_RESPONSES and include_tools:
        specs.append(
            ContractCheckSpec(
                id="responses-stateful",
                title="Responses stateful continuation",
                purpose="Verify the provider accepts previous_response_id and max_tool_calls on a follow-up Responses request.",
                required_capability="responses_api",
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
        "ok": False,
        "mode": "plan-only",
        "provider": _provider_identity(provider),
        "model": model or provider.default_model or "<required>",
        "contract_surface": _contract_surface(provider.contract, specs),
        "checks": [_planned_check(spec, provider) for spec in specs],
        "capability_evidence": _capability_evidence(provider, specs),
        "summary": {"planned": len(specs), "passed": 0, "failed": 0, "skipped": 0},
        "safety": {
            "contacts_provider": False,
            "remote_execution_requires_allow_remote": True,
            "stores_raw_secrets": False,
            "release_evidence_requires_execution": True,
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
        "ok": failed == 0,
        "mode": "executed",
        "provider": _provider_identity(provider),
        "model": resolved_model,
        "contract_surface": _contract_surface(provider.contract, specs),
        "checks": results,
        "capability_evidence": _capability_evidence(provider, specs),
        "summary": {"planned": len(specs), "passed": passed, "failed": failed, "skipped": skipped},
        "safety": {
            "contacts_provider": True,
            "remote_execution_allowed": allow_remote,
            "stores_raw_secrets": False,
            "release_evidence_requires_execution": False,
        },
    }


def write_contract_check_json(report: dict[str, Any], output: str | Any) -> None:
    from pathlib import Path

    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_provider_contract_matrix(
    matrix_path: Path,
    *,
    execute: bool = False,
    allow_remote: bool = False,
    include_streaming: bool = True,
    include_structured: bool = True,
    include_tools: bool = True,
    timeout: float = 10.0,
    continue_on_error: bool = True,
    provider_store: ProviderStore | None = None,
) -> dict[str, Any]:
    """Plan or execute contract checks for each unique provider/model target in a benchmark matrix."""

    matrix = load_matrix_file(matrix_path)
    store = provider_store or ProviderStore()
    targets, target_errors = _contract_matrix_targets(matrix.runs, store)
    entries: list[dict[str, Any]] = list(target_errors)
    for target in targets:
        try:
            if execute:
                report = run_provider_contract_check(
                    target["provider_config"],
                    model=None if target["model"] == "<required>" else target["model"],
                    allow_remote=allow_remote,
                    include_streaming=include_streaming,
                    include_structured=include_structured,
                    include_tools=include_tools,
                    timeout=timeout,
                )
            else:
                report = provider_contract_plan(
                    target["provider_config"],
                    model=None if target["model"] == "<required>" else target["model"],
                    include_streaming=include_streaming,
                    include_structured=include_structured,
                    include_tools=include_tools,
                )
            entries.append(_contract_matrix_entry(target, report))
        except (AdapterError, ConfigError, httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            if not continue_on_error:
                raise
            entries.append(_contract_matrix_error_entry(target, exc))

    passed_checks = sum(entry["summary"]["passed"] for entry in entries)
    failed_checks = sum(entry["summary"]["failed"] for entry in entries)
    skipped_checks = sum(entry["summary"]["skipped"] for entry in entries)
    planned_checks = sum(entry["summary"]["planned"] for entry in entries)
    failed_targets = sum(1 for entry in entries if not entry["ok"])
    error_targets = sum(1 for entry in entries if entry["status"] == "error")
    return {
        "schema_version": CONTRACT_CHECK_MATRIX_SCHEMA_VERSION,
        "ok": execute and failed_targets == 0,
        "mode": "executed" if execute else "plan-only",
        "matrix": {
            "name": matrix.name,
            "path": str(matrix_path),
            "description": matrix.description,
            "run_count": len(matrix.runs),
            "target_count": len(entries),
        },
        "summary": {
            "targets": len(entries),
            "passed_targets": sum(1 for entry in entries if entry["ok"]),
            "failed_targets": failed_targets,
            "error_targets": error_targets,
            "planned_checks": planned_checks,
            "passed_checks": passed_checks,
            "failed_checks": failed_checks,
            "skipped_checks": skipped_checks,
            "providers": sorted({entry["provider"] for entry in entries}),
            "models": sorted({entry["model"] for entry in entries}),
        },
        "contract_surfaces": _matrix_contract_surfaces(entries),
        "capability_evidence": _matrix_capability_evidence(entries),
        "entries": sorted(entries, key=lambda item: (item["provider"], item["model"])),
        "safety": {
            "contacts_provider": execute,
            "remote_execution_allowed": allow_remote if execute else None,
            "stores_raw_secrets": False,
            "contains_raw_provider_payloads": False,
            "release_evidence_requires_execution": not execute,
        },
    }


def write_contract_check_matrix_json(report: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def format_contract_check_matrix_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "AgentBlaster provider contract-check matrix",
        f"mode: {report['mode']}",
        f"ok: {str(report['ok']).lower()}",
        f"matrix: {report['matrix']['name']}",
        f"targets: {summary['targets']}",
        f"checks: planned={summary['planned_checks']} passed={summary['passed_checks']} failed={summary['failed_checks']} skipped={summary['skipped_checks']}",
    ]
    if report.get("contract_surfaces"):
        surface_text = "; ".join(
            f"{contract} auth={surface.get('auth', {}).get('scheme', 'unknown')} endpoints={_surface_endpoint_text(surface)}"
            for contract, surface in sorted(report["contract_surfaces"].items())
        )
        lines.append(f"contract_surfaces: {surface_text}")
    lines.append("entries:")
    for entry in report["entries"]:
        status = "PASS" if entry["ok"] else entry["status"].upper()
        indices = ",".join(str(index) for index in entry["matrix_indices"])
        lines.append(
            f"- {status} {entry['provider']} {entry['model']} "
            f"contract={entry['contract']} matrix_indices={indices} "
            f"checks={entry['summary']['passed']}/{entry['summary']['planned']}"
        )
        if entry.get("message"):
            lines.append(f"  {entry['message']}")
    return "\n".join(lines) + "\n"


def format_contract_check_report(report: dict[str, Any]) -> str:
    provider = report["provider"]
    lines = [
        "AgentBlaster provider contract check",
        f"mode: {report['mode']}",
        f"ok: {str(report.get('ok')).lower()}",
        f"provider: {provider['name']} ({provider['contract']})",
        f"endpoint_host: {provider.get('base_url_host') or 'unknown'}",
        f"remote: {str(provider.get('remote')).lower()}",
        f"model: {report['model']}",
        f"contract_surface: auth={report.get('contract_surface', {}).get('auth', {}).get('scheme', 'unknown')} endpoints={_surface_endpoint_text(report.get('contract_surface', {}))}",
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
    return "\n".join(lines) + "\n"


def _contract_matrix_targets(runs: list[MatrixRun], store: ProviderStore) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    targets_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    for index, run in enumerate(runs, start=1):
        try:
            provider = store.get(run.engine)
        except ConfigError as exc:
            errors.append(
                {
                    "provider": run.engine,
                    "contract": "unknown",
                    "endpoint_host": None,
                    "remote": None,
                    "model": run.model or "<required>",
                    "matrix_indices": [index],
                    "suites": [run.suite],
                    "concurrency_levels": [run.concurrency],
                    "mode": "error",
                    "status": "error",
                    "ok": False,
                    "summary": {"planned": 0, "passed": 0, "failed": 0, "skipped": 0},
                    "checks": [],
                    "capability_evidence": _empty_capability_evidence(),
                    "contract_surface": _empty_contract_surface("unknown"),
                    "message": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        model = run.model or provider.default_model or "<required>"
        key = (provider.name, model)
        target = targets_by_key.setdefault(
            key,
            {
                "provider_config": provider,
                "provider": provider.name,
                "contract": provider.contract.value,
                "endpoint_host": _provider_identity(provider).get("base_url_host"),
                "remote": provider.remote,
                "model": model,
                "matrix_indices": [],
                "suites": set(),
                "concurrency_levels": set(),
            },
        )
        target["matrix_indices"].append(index)
        target["suites"].add(run.suite)
        target["concurrency_levels"].add(run.concurrency)
    targets = []
    for target in targets_by_key.values():
        targets.append(
            {
                **target,
                "suites": sorted(target["suites"]),
                "concurrency_levels": sorted(target["concurrency_levels"]),
            }
        )
    return targets, errors


def _contract_matrix_entry(target: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": target["provider"],
        "contract": target["contract"],
        "endpoint_host": target["endpoint_host"],
        "remote": target["remote"],
        "model": target["model"],
        "matrix_indices": target["matrix_indices"],
        "suites": target["suites"],
        "concurrency_levels": target["concurrency_levels"],
        "mode": report["mode"],
        "status": "passed" if report["ok"] else ("planned" if report["mode"] == "plan-only" else "failed"),
        "ok": report["ok"],
        "summary": report["summary"],
        "checks": report["checks"],
        "capability_evidence": report.get("capability_evidence") or _empty_capability_evidence(),
        "contract_surface": report.get("contract_surface") or _empty_contract_surface(target["contract"]),
        "message": None,
    }


def _contract_matrix_error_entry(target: dict[str, Any], exc: Exception) -> dict[str, Any]:
    return {
        "provider": target["provider"],
        "contract": target["contract"],
        "endpoint_host": target["endpoint_host"],
        "remote": target["remote"],
        "model": target["model"],
        "matrix_indices": target["matrix_indices"],
        "suites": target["suites"],
        "concurrency_levels": target["concurrency_levels"],
        "mode": "error",
        "status": "error",
        "ok": False,
        "summary": {"planned": 0, "passed": 0, "failed": 0, "skipped": 0},
        "checks": [],
        "capability_evidence": _empty_capability_evidence(),
        "contract_surface": _empty_contract_surface(target["contract"]),
        "message": f"{type(exc).__name__}: {exc}",
    }


def _matrix_contract_surfaces(entries: list[dict[str, Any]]) -> dict[str, Any]:
    surfaces: dict[str, Any] = {}
    for entry in entries:
        surface = entry.get("contract_surface")
        if not isinstance(surface, dict):
            continue
        contract = str(surface.get("contract") or entry.get("contract") or "unknown")
        if surface.get("endpoints") and contract not in surfaces:
            surfaces[contract] = surface
    return dict(sorted(surfaces.items()))


def _matrix_capability_evidence(entries: list[dict[str, Any]]) -> dict[str, Any]:
    direct: set[str] = set()
    proxy_counts: dict[str, int] = {}
    not_covered_counts: dict[str, int] = {}
    for entry in entries:
        evidence = entry.get("capability_evidence") if isinstance(entry.get("capability_evidence"), dict) else {}
        directly_checked = evidence.get("directly_checked")
        if isinstance(directly_checked, list):
            direct.update(str(item) for item in directly_checked)
        proxy_items = evidence.get("proxy_checked")
        if isinstance(proxy_items, list):
            for item in proxy_items:
                if isinstance(item, dict) and item.get("capability"):
                    capability = str(item["capability"])
                    proxy_counts[capability] = proxy_counts.get(capability, 0) + 1
        uncovered_items = evidence.get("not_covered")
        if isinstance(uncovered_items, list):
            for item in uncovered_items:
                if isinstance(item, dict) and item.get("capability"):
                    capability = str(item["capability"])
                    not_covered_counts[capability] = not_covered_counts.get(capability, 0) + 1
    return {
        "directly_checked": sorted(direct),
        "proxy_checked_counts": dict(sorted(proxy_counts.items())),
        "not_covered_counts": dict(sorted(not_covered_counts.items())),
    }


def _empty_capability_evidence() -> dict[str, Any]:
    return {
        "directly_checked": [],
        "proxy_checked": [],
        "not_covered": [],
        "notes": [],
    }


def _empty_contract_surface(contract: str | None) -> dict[str, Any]:
    return {
        "schema_version": CONTRACT_SURFACE_SCHEMA_VERSION,
        "contract": contract or "unknown",
        "adapter_family": "unknown",
        "transport": "http-json",
        "auth": {"scheme": "unknown", "headers": [], "secret_source": "provider.api_key_ref", "raw_secret_stored": False},
        "endpoints": [],
        "request_features": [],
        "response_evidence": [],
        "notes": ["No contract surface was available because the provider target could not be planned or executed."],
    }


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


def _contract_surface(contract: ApiContract, specs: list[ContractCheckSpec]) -> dict[str, Any]:
    profile = _contract_surface_profile(contract)
    return {
        "schema_version": CONTRACT_SURFACE_SCHEMA_VERSION,
        "contract": contract.value,
        "adapter_family": profile["adapter_family"],
        "transport": "http-json",
        "auth": profile["auth"],
        "endpoints": [
            {
                "check_id": spec.id,
                "method": _contract_surface_endpoint(contract, spec.id)[0],
                "path": _contract_surface_endpoint(contract, spec.id)[1],
                "required_capability": spec.required_capability,
            }
            for spec in specs
        ],
        "request_features": _contract_surface_request_features(contract, specs),
        "response_evidence": profile["response_evidence"],
        "notes": profile["notes"],
    }


def _contract_surface_profile(contract: ApiContract) -> dict[str, Any]:
    if contract is ApiContract.OPENAI_RESPONSES:
        return {
            "adapter_family": "openai-responses",
            "auth": {
                "scheme": "bearer",
                "headers": ["Authorization"],
                "secret_source": "provider.api_key_ref",
                "raw_secret_stored": False,
            },
            "response_evidence": [
                "output_text",
                "output[].content[]",
                "output[].type=function_call",
                "usage",
                "stream data: response.output_text.delta",
            ],
            "notes": [
                "Responses-compatible checks use /responses and keep stateful continuation separate from Chat Completions.",
                "Raw authorization headers and API-key values are never stored in contract artifacts.",
            ],
        }
    if contract is ApiContract.ANTHROPIC:
        return {
            "adapter_family": "anthropic-messages",
            "auth": {
                "scheme": "x-api-key",
                "headers": ["x-api-key", "anthropic-version"],
                "secret_source": "provider.api_key_ref",
                "raw_secret_stored": False,
            },
            "response_evidence": [
                "content[].text",
                "content[].type=tool_use",
                "usage",
                "stop_reason",
                "stream event: content_block_delta",
            ],
            "notes": [
                "Anthropic-compatible checks use /messages and do not claim OpenAI response_format parity.",
                "Prompt caching remains separate benchmark evidence, not provider contract-check evidence.",
            ],
        }
    return {
        "adapter_family": "openai-chat-completions",
        "auth": {
            "scheme": "bearer",
            "headers": ["Authorization"],
            "secret_source": "provider.api_key_ref",
            "raw_secret_stored": False,
        },
        "response_evidence": [
            "choices[].message.content",
            "choices[].message.tool_calls[]",
            "usage",
            "stream data: choices[].delta",
        ],
        "notes": [
            "OpenAI-compatible checks use /chat/completions as the primary local-engine interoperability surface.",
            "Raw authorization headers and API-key values are never stored in contract artifacts.",
        ],
    }


def _contract_surface_endpoint(contract: ApiContract, check_id: str) -> tuple[str, str]:
    if check_id == "model-list":
        return "GET", "/models"
    if contract is ApiContract.OPENAI_RESPONSES:
        return "POST", "/responses"
    if contract is ApiContract.ANTHROPIC:
        return "POST", "/messages"
    return "POST", "/chat/completions"


def _contract_surface_request_features(contract: ApiContract, specs: list[ContractCheckSpec]) -> list[str]:
    check_ids = {spec.id for spec in specs}
    if contract is ApiContract.OPENAI_RESPONSES:
        features = {"input", "instructions", "model", "temperature", "max_output_tokens"}
        if "streaming-text" in check_ids:
            features.add("stream")
        if "structured-json" in check_ids:
            features.add("text.format")
        if "tool-call" in check_ids:
            features.update({"tools", "tool_choice"})
        if "responses-stateful" in check_ids:
            features.update({"previous_response_id", "max_tool_calls"})
        return sorted(features)
    if contract is ApiContract.ANTHROPIC:
        features = {"messages", "system", "model", "temperature", "max_tokens"}
        if "streaming-text" in check_ids:
            features.add("stream")
        if "tool-call" in check_ids:
            features.update({"tools", "tool_choice"})
        return sorted(features)
    features = {"messages", "model", "temperature", "max_tokens"}
    if "streaming-text" in check_ids:
        features.add("stream")
    if "structured-json" in check_ids:
        features.add("response_format")
    if "tool-call" in check_ids:
        features.update({"tools", "tool_choice"})
    return sorted(features)


def _surface_endpoint_text(surface: dict[str, Any]) -> str:
    endpoints = surface.get("endpoints")
    if not isinstance(endpoints, list):
        return "none"
    pairs = []
    for endpoint in endpoints:
        if isinstance(endpoint, dict) and endpoint.get("method") and endpoint.get("path"):
            pairs.append(f"{endpoint['method']} {endpoint['path']}")
    return ",".join(sorted(set(pairs))) if pairs else "none"


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
        if spec.id == "responses-stateful":
            seed_response = adapter.chat_completion(model, _responses_state_seed_case())
            previous_response_id = _response_id(seed_response.raw)
            if not _response_ok(seed_response.status_code) or previous_response_id is None:
                return _result(spec, ok=False, message="seed response did not return a usable response id")
            response = adapter.chat_completion(model, _responses_stateful_case(previous_response_id))
            return _result(
                spec,
                ok=_response_ok(response.status_code) and "agentblaster-ok" in response.text,
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


def _responses_state_seed_case() -> BenchmarkCase:
    return BenchmarkCase(
        id="contract-responses-state-seed",
        title="Responses state seed",
        prompt="Reply with exactly: agentblaster-ok",
        expected_substring="agentblaster-ok",
        max_tokens=16,
        timeout_seconds=10.0,
    )


def _responses_stateful_case(previous_response_id: str) -> BenchmarkCase:
    return BenchmarkCase(
        id="contract-responses-stateful",
        title="Responses stateful continuation",
        prompt="Reply with exactly: agentblaster-ok",
        expected_substring="agentblaster-ok",
        previous_response_id=previous_response_id,
        max_tool_calls=1,
        max_tokens=16,
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


def _response_id(raw: Any) -> str | None:
    if not isinstance(raw, dict):
        return None
    value = raw.get("id")
    if value is None:
        return None
    text = str(value)
    return text if text else None


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


def _capability_evidence(provider: ProviderConfig, specs: list[ContractCheckSpec]) -> dict[str, Any]:
    directly_checked = sorted({spec.required_capability for spec in specs if spec.required_capability})
    proxy_checked = [
        {
            "capability": capability,
            "covered_by": covered_by,
            "declared": provider.capabilities.get(capability),
            "covered_by_declared": provider.capabilities.get(covered_by),
            "note": (
                "Judge-rubric harness cases are evaluated through structured verdict JSON; "
                "the structured_output contract check is the standardized proxy evidence."
            ),
        }
        for capability, covered_by in sorted(PROXY_CAPABILITY_COVERAGE.items())
        if covered_by in directly_checked
    ]
    not_covered = []
    for capability, note in sorted(SEPARATE_BENCHMARK_EVIDENCE_CAPABILITIES.items()):
        not_covered.append(
            {
                "capability": capability,
                "declared": provider.capabilities.get(capability),
                "note": note,
            }
        )
    if provider.contract is ApiContract.ANTHROPIC:
        not_covered.append(
            {
                "capability": "prompt_caching",
                "declared": provider.capabilities.get("prompt_caching"),
                "note": (
                    "Contract checks do not prove Anthropic cache-control reuse or accounting; "
                    "use cache-control benchmark runs and normalized cache token metrics."
                ),
            }
        )
        if "structured_output" not in directly_checked:
            not_covered.append(
                {
                    "capability": "judge_rubric",
                    "declared": provider.capabilities.get("judge_rubric"),
                    "note": (
                        "Anthropic Messages has no standardized response_format field in this harness; "
                        "judge-rubric evidence requires a declared structured-output equivalent or prompt-only calibration."
                    ),
                }
            )
    return {
        "directly_checked": directly_checked,
        "proxy_checked": proxy_checked,
        "not_covered": not_covered,
        "notes": [
            "Plan-only reports describe intended evidence and do not prove provider compatibility.",
            "Executed reports prove only the listed checks; capability declarations still remain operator-owned metadata.",
        ],
    }
