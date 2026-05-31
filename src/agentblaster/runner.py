from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from agentblaster.adapters import ProviderAdapter, adapter_for
from agentblaster.models import (
    AdapterResponse,
    ApiContract,
    BenchmarkCase,
    BenchmarkResult,
    ProviderConfig,
    RawTraceMode,
    RunManifest,
    RunSummary,
    SuiteDefinition,
)
from agentblaster.redaction import redact_value

SMOKE_CASE_ID = "protocol-smoke-chat"


def new_run_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"run_{timestamp}_{uuid4().hex[:8]}"


class ArtifactWriter:
    def __init__(self, output_dir: Path, manifest: RunManifest) -> None:
        self.run_dir = output_dir / manifest.run_id
        self.manifest = manifest

    def initialize(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / "manifest.json").write_text(
            json.dumps(self.manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def write_raw_response(self, case_id: str, raw: dict, mode: RawTraceMode) -> str | None:
        if mode is RawTraceMode.OFF:
            return None
        raw_dir = self.run_dir / "raw"
        raw_dir.mkdir(exist_ok=True)
        payload = raw if mode is RawTraceMode.FULL else redact_value(raw)
        path = raw_dir / f"{case_id}.response.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path.relative_to(self.run_dir).as_posix()

    def append_result(self, result: BenchmarkResult) -> None:
        with (self.run_dir / "results.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(result.model_dump_json(exclude_none=True) + "\n")

    def write_summary(self, summary: RunSummary) -> None:
        (self.run_dir / "summary.json").write_text(
            json.dumps(summary.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


class BenchmarkRunner:
    def __init__(
        self,
        provider: ProviderConfig,
        suite: SuiteDefinition,
        *,
        adapter: ProviderAdapter | None = None,
        output_dir: Path = Path("runs"),
        raw_trace_mode: RawTraceMode = RawTraceMode.REDACTED,
        concurrency: int = 1,
    ) -> None:
        self.provider = provider
        self.suite = suite
        self.adapter = adapter or adapter_for(provider)
        self.output_dir = output_dir
        self.raw_trace_mode = raw_trace_mode
        self.concurrency = max(1, concurrency)

    def run(self, model: str | None = None) -> RunSummary:
        resolved_model = model or self.provider.default_model
        if not resolved_model:
            raise ValueError("model is required when provider has no default_model")

        run_id = new_run_id()
        manifest = RunManifest(
            run_id=run_id,
            suite=self.suite.name,
            provider=self.provider.name,
            contract=self.provider.contract,
            model=resolved_model,
            raw_trace_mode=self.raw_trace_mode,
            created_at=datetime.now(UTC).isoformat(),
            case_count=len(self.suite.cases),
            concurrency=self.concurrency,
        )
        writer = ArtifactWriter(self.output_dir, manifest)
        writer.initialize()

        results: list[BenchmarkResult] = []
        for case, response, error in self._execute_cases(resolved_model):
            if response is not None:
                raw_response_path = writer.write_raw_response(case.id, response.raw, self.raw_trace_mode)
                result = result_from_response(
                    run_id=run_id,
                    suite=self.suite.name,
                    provider_name=self.provider.name,
                    model=resolved_model,
                    case=case,
                    response=response,
                    raw_response_path=raw_response_path,
                )
            else:
                result = result_from_error(
                    run_id=run_id,
                    suite=self.suite.name,
                    provider_name=self.provider.name,
                    contract=self.provider.contract,
                    model=resolved_model,
                    case=case,
                    message=error or "unknown case execution error",
                )
            writer.append_result(result)
            results.append(result)

        summary = RunSummary(
            run_id=run_id,
            suite=self.suite.name,
            provider=self.provider.name,
            model=resolved_model,
            total_cases=len(results),
            passed=sum(1 for result in results if result.ok),
            failed=sum(1 for result in results if not result.ok),
            concurrency=self.concurrency,
            results_path="results.jsonl",
            manifest_path="manifest.json",
        )
        writer.write_summary(summary)
        return summary

    def _execute_cases(self, model: str) -> list[tuple[BenchmarkCase, AdapterResponse | None, str | None]]:
        if self.concurrency == 1 or len(self.suite.cases) <= 1:
            return [self._execute_case(model, case) for case in self.suite.cases]

        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            return list(executor.map(lambda case: self._execute_case(model, case), self.suite.cases))

    def _execute_case(self, model: str, case: BenchmarkCase) -> tuple[BenchmarkCase, AdapterResponse | None, str | None]:
        try:
            return case, self.adapter.chat_completion(model, case), None
        except Exception as exc:  # noqa: BLE001 - benchmark harness records provider/runtime failures per case
            return case, None, str(exc)


class SmokeRunner:
    def __init__(
        self,
        provider: ProviderConfig,
        *,
        adapter: ProviderAdapter | None = None,
        output_dir: Path = Path("runs"),
        raw_trace_mode: RawTraceMode = RawTraceMode.REDACTED,
    ) -> None:
        self.provider = provider
        self.adapter = adapter or adapter_for(provider)
        self.output_dir = output_dir
        self.raw_trace_mode = raw_trace_mode

    def run(self, model: str | None = None) -> BenchmarkResult:
        resolved_model = model or self.provider.default_model
        if not resolved_model:
            raise ValueError("model is required when provider has no default_model")

        run_id = new_run_id()
        manifest = RunManifest(
            run_id=run_id,
            suite="smoke",
            provider=self.provider.name,
            contract=self.provider.contract,
            model=resolved_model,
            raw_trace_mode=self.raw_trace_mode,
            created_at=datetime.now(UTC).isoformat(),
        )
        writer = ArtifactWriter(self.output_dir, manifest)
        writer.initialize()

        response = self.adapter.smoke_chat(resolved_model)
        raw_response_path = writer.write_raw_response(SMOKE_CASE_ID, response.raw, self.raw_trace_mode)
        case = BenchmarkCase(
            id=SMOKE_CASE_ID,
            title="Protocol smoke chat",
            prompt="Reply with exactly: agentblaster-ok",
            expected_substring="agentblaster-ok",
            max_tokens=16,
        )
        result = result_from_response(
            run_id=run_id,
            suite="smoke",
            provider_name=self.provider.name,
            model=resolved_model,
            case=case,
            response=response,
            raw_response_path=raw_response_path,
        )
        writer.append_result(result)
        return result

    def _result_from_response(
        self,
        run_id: str,
        model: str,
        response: AdapterResponse,
        raw_response_path: str | None,
    ) -> BenchmarkResult:
        case = BenchmarkCase(
            id=SMOKE_CASE_ID,
            title="Protocol smoke chat",
            prompt="Reply with exactly: agentblaster-ok",
            expected_substring="agentblaster-ok",
        )
        return result_from_response(
            run_id=run_id,
            suite="smoke",
            provider_name=self.provider.name,
            model=model,
            case=case,
            response=response,
            raw_response_path=raw_response_path,
        )


def result_from_response(
    *,
    run_id: str,
    suite: str,
    provider_name: str,
    model: str,
    case: BenchmarkCase,
    response: AdapterResponse,
    raw_response_path: str | None,
) -> BenchmarkResult:
    input_tokens, output_tokens, total_tokens = normalize_usage(response.contract, response.raw)
    assertion_ok, assertion_message = evaluate_case_assertions(case, response)
    ok = 200 <= response.status_code < 300 and assertion_ok
    message = "ok" if ok else assertion_message or response.text[:240] or f"HTTP {response.status_code}"

    return BenchmarkResult(
        run_id=run_id,
        case_id=case.id,
        suite=suite,
        provider=provider_name,
        contract=response.contract,
        model=model,
        ok=ok,
        status_code=response.status_code,
        latency_ms=round(response.latency_ms, 3),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        failure_class=None if ok else "model_quality",
        message=message,
        raw_response_path=raw_response_path,
    )


def result_from_error(
    *,
    run_id: str,
    suite: str,
    provider_name: str,
    contract: ApiContract,
    model: str,
    case: BenchmarkCase,
    message: str,
) -> BenchmarkResult:
    return BenchmarkResult(
        run_id=run_id,
        case_id=case.id,
        suite=suite,
        provider=provider_name,
        contract=contract,
        model=model,
        ok=False,
        failure_class="engine_runtime_bug",
        message=message,
    )


def evaluate_case_assertions(case: BenchmarkCase, response: AdapterResponse) -> tuple[bool, str]:
    if case.expected_substring is not None:
        if case.expected_substring.lower() not in response.text.lower():
            return False, f"missing expected substring: {case.expected_substring}"

    if case.expected_json_fields:
        parsed = _parse_json_text(response.text)
        if parsed is None:
            return False, "response text is not valid JSON"
        for path, expected_value in case.expected_json_fields.items():
            actual = _lookup_path(parsed, path)
            if actual != expected_value:
                return False, f"JSON field {path} expected {expected_value!r}, got {actual!r}"

    if case.expected_tool_name is not None:
        if case.expected_tool_name not in response.tool_names:
            return False, f"missing expected tool call: {case.expected_tool_name}"

    return True, ""


def _parse_json_text(text: str) -> Any | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None


def _lookup_path(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if index < len(current) else None
        else:
            return None
    return current


def normalize_usage(contract: ApiContract, raw: dict) -> tuple[int | None, int | None, int | None]:
    usage = raw.get("usage")
    if not isinstance(usage, dict):
        return None, None, None

    if contract is ApiContract.OPENAI:
        input_tokens = _optional_int(usage.get("prompt_tokens"))
        output_tokens = _optional_int(usage.get("completion_tokens"))
        total_tokens = _optional_int(usage.get("total_tokens"))
        return input_tokens, output_tokens, total_tokens

    if contract is ApiContract.ANTHROPIC:
        input_tokens = _optional_int(usage.get("input_tokens"))
        output_tokens = _optional_int(usage.get("output_tokens"))
        cache_read = _optional_int(usage.get("cache_read_input_tokens")) or 0
        cache_write = _optional_int(usage.get("cache_creation_input_tokens")) or 0
        total_tokens = None
        if input_tokens is not None or output_tokens is not None:
            total_tokens = (input_tokens or 0) + (output_tokens or 0) + cache_read + cache_write
        return input_tokens, output_tokens, total_tokens

    return None, None, None


def _optional_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
