from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

from agentblaster.adapters import ProviderAdapter, adapter_for
from agentblaster.costs import estimate_costs
from agentblaster.environment import capture_environment
from agentblaster.failures import classify_exception_failure, classify_response_failure
from agentblaster.lcp import lcp_profile_text
from agentblaster.mcp import mcp_profile_tool_schemas
from agentblaster.models import (
    AdapterResponse,
    ApiContract,
    BenchmarkCase,
    BenchmarkResult,
    ModelMetadata,
    ProviderConfig,
    ProviderRunMetadata,
    RawTraceMode,
    RetentionPolicy,
    RunIntegrityManifest,
    RunManifest,
    RunSummary,
    SuiteDefinition,
)
from agentblaster.observability import (
    PROMETHEUS_ARTIFACTS,
    PrometheusScrape,
    prometheus_summary_json,
    scrape_prometheus_metrics,
)
from agentblaster.redaction import redact_value
from agentblaster.rate_limits import RateLimitPacer
from agentblaster.skills import skill_prefix
from agentblaster.telemetry import normalize_response_telemetry
from agentblaster.toolsim import execute_simulated_tools, simulated_tool_schemas

SMOKE_CASE_ID = "protocol-smoke-chat"
SUITE_SNAPSHOT_FILENAME = "suite.json"


def new_run_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"run_{timestamp}_{uuid4().hex[:8]}"


def merge_model_metadata(base: ModelMetadata, override: ModelMetadata | None) -> ModelMetadata:
    if override is None:
        return base
    merged = base.model_dump()
    for key, value in override.model_dump().items():
        if value is not None:
            merged[key] = value
    return ModelMetadata.model_validate(merged)


def suite_snapshot_payload(suite: SuiteDefinition) -> dict[str, Any]:
    return suite.model_dump(mode="json")


def suite_sha256(suite: SuiteDefinition) -> str:
    return _sha256_json(suite_snapshot_payload(suite))


def case_sha256_map(suite: SuiteDefinition) -> dict[str, str]:
    return {case.id: _sha256_json(case.model_dump(mode="json")) for case in suite.cases}


def provider_run_metadata(provider: ProviderConfig, adapter: ProviderAdapter | None = None) -> ProviderRunMetadata:
    base_url = str(provider.base_url)
    metrics_url = str(provider.metrics_url) if provider.metrics_url is not None else None
    parsed_base = urlparse(base_url)
    parsed_metrics = urlparse(metrics_url) if metrics_url else None
    return ProviderRunMetadata(
        base_url=_safe_url(base_url),
        base_url_host=parsed_base.hostname,
        remote=provider.remote,
        native_adapter=provider.native_adapter,
        adapter_name=getattr(adapter, "adapter_name", None) if adapter is not None else None,
        adapter_version=getattr(adapter, "adapter_version", None) if adapter is not None else None,
        capabilities=dict(provider.capabilities),
        metrics_url_host=parsed_metrics.hostname if parsed_metrics else None,
        tls_verify=provider.tls_verify,
        ca_bundle=str(provider.ca_bundle) if provider.ca_bundle is not None else None,
    )


def provider_result_identity(metadata: ProviderRunMetadata) -> dict[str, Any]:
    return {
        "provider_endpoint_host": metadata.base_url_host,
        "provider_remote": metadata.remote,
        "native_adapter": metadata.native_adapter,
        "adapter_name": metadata.adapter_name,
        "adapter_version": metadata.adapter_version,
    }


def case_result_metadata(case: BenchmarkCase, suite: str) -> dict[str, Any]:
    return {
        "case_title": case.title,
        "scenario": case.scenario or _scenario_from_tags(case.tags, suite),
        "case_tags": list(case.tags),
        "case_provenance": case.provenance,
        "case_risk_level": case.risk_level,
        "case_source_url": case.source_url,
        "case_license": case.license,
    }


class ArtifactWriter:
    def __init__(self, output_dir: Path, manifest: RunManifest, suite: SuiteDefinition | None = None) -> None:
        self.run_dir = output_dir / manifest.run_id
        self.manifest = manifest
        self.suite = suite

    def initialize(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / "manifest.json").write_text(
            json.dumps(self.manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if self.suite is not None:
            (self.run_dir / SUITE_SNAPSHOT_FILENAME).write_text(
                json.dumps(suite_snapshot_payload(self.suite), indent=2, sort_keys=True) + "\n",
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

    def write_prometheus_scrape(self, scrape: PrometheusScrape) -> str:
        metrics_dir = self.run_dir / "metrics"
        metrics_dir.mkdir(exist_ok=True)
        path = metrics_dir / f"prometheus-{scrape.phase}.prom"
        text = scrape.text if scrape.ok else f"# AgentBlaster Prometheus scrape failed: {scrape.error or 'unknown error'}\n"
        path.write_text(text, encoding="utf-8")
        return path.relative_to(self.run_dir).as_posix()

    def write_prometheus_summary(self, before: PrometheusScrape | None, after: PrometheusScrape | None) -> str:
        metrics_dir = self.run_dir / "metrics"
        metrics_dir.mkdir(exist_ok=True)
        path = metrics_dir / "prometheus-summary.json"
        path.write_text(prometheus_summary_json(before, after), encoding="utf-8")
        return path.relative_to(self.run_dir).as_posix()

    def write_integrity_manifest(self) -> None:
        artifacts: dict[str, str] = {}
        for path in sorted(item for item in self.run_dir.rglob("*") if item.is_file()):
            relative_path = path.relative_to(self.run_dir).as_posix()
            if relative_path == "integrity.json":
                continue
            artifacts[relative_path] = _sha256_file(path)
        integrity = RunIntegrityManifest(
            run_id=self.manifest.run_id,
            created_at=datetime.now(UTC).isoformat(),
            artifacts=artifacts,
        )
        (self.run_dir / "integrity.json").write_text(
            json.dumps(integrity.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
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
        retention_policy: RetentionPolicy | None = None,
    ) -> None:
        self.provider = provider
        self.suite = suite
        self.adapter = adapter or adapter_for(provider)
        self.output_dir = output_dir
        self.raw_trace_mode = raw_trace_mode
        self.concurrency = max(1, concurrency)
        self.retention_policy = retention_policy or RetentionPolicy()
        self.rate_limiter = RateLimitPacer(provider.rate_limits)
        self.metrics_scraper = scrape_prometheus_metrics

    def run(self, model: str | None = None, model_metadata: ModelMetadata | None = None) -> RunSummary:
        resolved_model = model or self.provider.default_model
        if not resolved_model:
            raise ValueError("model is required when provider has no default_model")

        run_id = new_run_id()
        provider_metadata = provider_run_metadata(self.provider, self.adapter)
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
            suite_sha256=suite_sha256(self.suite),
            case_sha256=case_sha256_map(self.suite),
            suite_snapshot_path=SUITE_SNAPSHOT_FILENAME,
            suite_provenance=self.suite.provenance,
            metrics_artifacts=PROMETHEUS_ARTIFACTS if self.provider.metrics_url else [],
            provider_metadata=provider_metadata,
            environment=capture_environment(),
            model_metadata=merge_model_metadata(self.provider.model_metadata, model_metadata),
            retention_policy=self.retention_policy,
        )
        writer = ArtifactWriter(self.output_dir, manifest, self.suite)
        writer.initialize()

        prometheus_before = self._scrape_prometheus("before")
        if prometheus_before is not None:
            writer.write_prometheus_scrape(prometheus_before)

        results: list[BenchmarkResult] = []
        for (
            case,
            response,
            error,
            request_started_at,
            request_completed_at,
            queue_ms,
            rate_limit_wait_ms,
        ) in self._execute_cases(resolved_model):
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
                    request_started_at=request_started_at,
                    request_completed_at=request_completed_at,
                    queue_ms=queue_ms,
                    rate_limit_wait_ms=rate_limit_wait_ms,
                    provider_cost_model=self.provider.cost_model,
                    provider_identity=provider_result_identity(provider_metadata),
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
                    request_started_at=request_started_at,
                    request_completed_at=request_completed_at,
                    queue_ms=queue_ms,
                    rate_limit_wait_ms=rate_limit_wait_ms,
                    provider_identity=provider_result_identity(provider_metadata),
                )
            writer.append_result(result)
            results.append(result)

        prometheus_after = self._scrape_prometheus("after")
        if prometheus_before is not None or prometheus_after is not None:
            if prometheus_after is not None:
                writer.write_prometheus_scrape(prometheus_after)
            writer.write_prometheus_summary(prometheus_before, prometheus_after)

        summary = RunSummary(
            run_id=run_id,
            suite=self.suite.name,
            provider=self.provider.name,
            model=resolved_model,
            total_cases=len(results),
            passed=sum(1 for result in results if result.ok),
            failed=sum(1 for result in results if not result.ok),
            concurrency=self.concurrency,
            **run_timing_summary(results),
            results_path="results.jsonl",
            manifest_path="manifest.json",
        )
        writer.write_summary(summary)
        writer.write_integrity_manifest()
        return summary

    def _scrape_prometheus(self, phase: str) -> PrometheusScrape | None:
        if self.provider.metrics_url is None:
            return None
        return self.metrics_scraper(str(self.provider.metrics_url), phase=phase)

    def _execute_cases(
        self,
        model: str,
    ) -> list[tuple[BenchmarkCase, AdapterResponse | None, str | None, str, str, float, float]]:
        if self.concurrency == 1 or len(self.suite.cases) <= 1:
            return [self._execute_case(model, case, datetime.now(UTC)) for case in self.suite.cases]

        submitted_cases = [(case, datetime.now(UTC)) for case in self.suite.cases]
        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            return list(executor.map(lambda item: self._execute_case(model, item[0], item[1]), submitted_cases))

    def _execute_case(
        self,
        model: str,
        case: BenchmarkCase,
        submitted_at: datetime,
    ) -> tuple[BenchmarkCase, AdapterResponse | None, str | None, str, str, float, float]:
        rate_limit_wait_ms = self.rate_limiter.wait()
        started_at = datetime.now(UTC)
        queue_ms = _duration_ms(submitted_at, started_at)
        try:
            response = self.adapter.chat_completion(model, case_with_simulated_tools(case))
            completed_at = datetime.now(UTC)
            return case, response, None, started_at.isoformat(), completed_at.isoformat(), queue_ms, rate_limit_wait_ms
        except Exception as exc:  # noqa: BLE001 - benchmark harness records provider/runtime failures per case
            completed_at = datetime.now(UTC)
            return case, None, str(exc), started_at.isoformat(), completed_at.isoformat(), queue_ms, rate_limit_wait_ms


class SmokeRunner:
    def __init__(
        self,
        provider: ProviderConfig,
        *,
        adapter: ProviderAdapter | None = None,
        output_dir: Path = Path("runs"),
        raw_trace_mode: RawTraceMode = RawTraceMode.REDACTED,
        retention_policy: RetentionPolicy | None = None,
    ) -> None:
        self.provider = provider
        self.adapter = adapter or adapter_for(provider)
        self.output_dir = output_dir
        self.raw_trace_mode = raw_trace_mode
        self.retention_policy = retention_policy or RetentionPolicy()
        self.rate_limiter = RateLimitPacer(provider.rate_limits)
        self.metrics_scraper = scrape_prometheus_metrics

    def run(self, model: str | None = None, model_metadata: ModelMetadata | None = None) -> BenchmarkResult:
        resolved_model = model or self.provider.default_model
        if not resolved_model:
            raise ValueError("model is required when provider has no default_model")

        run_id = new_run_id()
        case = BenchmarkCase(
            id=SMOKE_CASE_ID,
            title="Protocol smoke chat",
            prompt="Reply with exactly: agentblaster-ok",
            expected_substring="agentblaster-ok",
            max_tokens=16,
        )
        suite = SuiteDefinition(name="smoke", description="Protocol smoke chat.", cases=[case])
        provider_metadata = provider_run_metadata(self.provider, self.adapter)
        manifest = RunManifest(
            run_id=run_id,
            suite="smoke",
            provider=self.provider.name,
            contract=self.provider.contract,
            model=resolved_model,
            raw_trace_mode=self.raw_trace_mode,
            created_at=datetime.now(UTC).isoformat(),
            case_count=1,
            suite_sha256=suite_sha256(suite),
            case_sha256=case_sha256_map(suite),
            suite_snapshot_path=SUITE_SNAPSHOT_FILENAME,
            suite_provenance=suite.provenance,
            metrics_artifacts=PROMETHEUS_ARTIFACTS if self.provider.metrics_url else [],
            provider_metadata=provider_metadata,
            environment=capture_environment(),
            model_metadata=merge_model_metadata(self.provider.model_metadata, model_metadata),
            retention_policy=self.retention_policy,
        )
        writer = ArtifactWriter(self.output_dir, manifest, suite)
        writer.initialize()

        prometheus_before = self._scrape_prometheus("before")
        if prometheus_before is not None:
            writer.write_prometheus_scrape(prometheus_before)

        rate_limit_wait_ms = self.rate_limiter.wait()
        request_started_at = datetime.now(UTC)
        response = self.adapter.smoke_chat(resolved_model)
        request_completed_at = datetime.now(UTC)
        raw_response_path = writer.write_raw_response(SMOKE_CASE_ID, response.raw, self.raw_trace_mode)
        result = result_from_response(
            run_id=run_id,
            suite="smoke",
            provider_name=self.provider.name,
            model=resolved_model,
            case=case,
            response=response,
            raw_response_path=raw_response_path,
            request_started_at=request_started_at.isoformat(),
            request_completed_at=request_completed_at.isoformat(),
            queue_ms=rate_limit_wait_ms,
            rate_limit_wait_ms=rate_limit_wait_ms,
            provider_cost_model=self.provider.cost_model,
            provider_identity=provider_result_identity(provider_metadata),
        )
        writer.append_result(result)
        prometheus_after = self._scrape_prometheus("after")
        if prometheus_before is not None or prometheus_after is not None:
            if prometheus_after is not None:
                writer.write_prometheus_scrape(prometheus_after)
            writer.write_prometheus_summary(prometheus_before, prometheus_after)
        writer.write_integrity_manifest()
        return result

    def _scrape_prometheus(self, phase: str) -> PrometheusScrape | None:
        if self.provider.metrics_url is None:
            return None
        return self.metrics_scraper(str(self.provider.metrics_url), phase=phase)

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
    request_started_at: str | None = None,
    request_completed_at: str | None = None,
    queue_ms: float | None = None,
    rate_limit_wait_ms: float | None = None,
    provider_cost_model: dict[str, Any] | None = None,
    provider_identity: dict[str, Any] | None = None,
) -> BenchmarkResult:
    native_adapter = None
    if provider_identity is not None and provider_identity.get("native_adapter"):
        native_adapter = str(provider_identity["native_adapter"])
    telemetry = normalize_response_telemetry(
        response.contract,
        response.raw,
        native_adapter=native_adapter,
        latency_ms=response.latency_ms,
        ttft_ms=response.ttft_ms,
    )
    telemetry_values = telemetry["values"]
    input_tokens = _optional_int(telemetry_values.get("input_tokens"))
    output_tokens = _optional_int(telemetry_values.get("output_tokens"))
    total_tokens = _optional_int(telemetry_values.get("total_tokens"))
    cached_input_tokens = _optional_int(telemetry_values.get("cached_input_tokens"))
    cache_write_tokens = _optional_int(telemetry_values.get("cache_write_tokens"))
    cache_hit_ratio = _optional_float(telemetry_values.get("cache_hit_ratio"))
    costs = estimate_costs(
        provider_cost_model or {},
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_input_tokens,
        cache_write_tokens=cache_write_tokens,
    )
    timings = {
        "ttft_ms": _optional_float(telemetry_values.get("ttft_ms")),
        "load_ms": _optional_float(telemetry_values.get("load_ms")),
        "prompt_eval_ms": _optional_float(telemetry_values.get("prompt_eval_ms")),
        "decode_ms": _optional_float(telemetry_values.get("decode_ms")),
        "tokens_per_second_prefill": _optional_float(telemetry_values.get("tokens_per_second_prefill")),
        "tokens_per_second_decode": _optional_float(telemetry_values.get("tokens_per_second_decode")),
    }
    raw_usage = _redacted_telemetry_mapping(telemetry_values.get("raw_usage"))
    raw_stats = _redacted_telemetry_mapping(telemetry_values.get("raw_stats"))
    finish_reason_value = telemetry_values.get("finish_reason")
    finish_reason = str(finish_reason_value) if finish_reason_value is not None else None
    simulated_tool_results = case_simulated_tool_results(case, response)
    tool_metrics = normalize_tool_metrics(case, response)
    structured_output_valid = evaluate_structured_output_validity(case, response)
    assertion_ok, assertion_message = evaluate_case_assertions(case, response)
    ok = 200 <= response.status_code < 300 and assertion_ok
    message = "ok" if ok else assertion_message or response.text[:240] or f"HTTP {response.status_code}"

    return BenchmarkResult(
        run_id=run_id,
        case_id=case.id,
        **case_result_metadata(case, suite),
        suite=suite,
        provider=provider_name,
        contract=response.contract,
        model=model,
        ok=ok,
        **(provider_identity or {}),
        status_code=response.status_code,
        request_started_at=request_started_at,
        request_completed_at=request_completed_at,
        queue_ms=queue_ms,
        rate_limit_wait_ms=rate_limit_wait_ms,
        latency_ms=round(_optional_float(telemetry_values.get("latency_ms")) or response.latency_ms, 3),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cached_input_tokens=cached_input_tokens,
        cache_write_tokens=cache_write_tokens,
        cache_hit_ratio=cache_hit_ratio,
        input_cost_usd=costs["input_cost_usd"],
        output_cost_usd=costs["output_cost_usd"],
        cache_read_cost_usd=costs["cache_read_cost_usd"],
        cache_write_cost_usd=costs["cache_write_cost_usd"],
        request_cost_usd=costs["request_cost_usd"],
        total_cost_usd=costs["total_cost_usd"],
        ttft_ms=timings["ttft_ms"],
        load_ms=timings["load_ms"],
        prompt_eval_ms=timings["prompt_eval_ms"],
        decode_ms=timings["decode_ms"],
        tokens_per_second_prefill=timings["tokens_per_second_prefill"],
        tokens_per_second_decode=timings["tokens_per_second_decode"],
        raw_usage=raw_usage,
        raw_stats=raw_stats,
        tool_calls_requested=tool_metrics["tool_calls_requested"],
        tool_calls_emitted=tool_metrics["tool_calls_emitted"],
        tool_calls_valid=tool_metrics["tool_calls_valid"],
        structured_output_valid=structured_output_valid,
        finish_reason=finish_reason,
        simulated_tool_results=simulated_tool_results,
        failure_class=classify_response_failure(
            status_code=response.status_code,
            assertion_ok=assertion_ok,
            assertion_message=assertion_message,
        ),
        message=message,
        raw_response_path=raw_response_path,
    )


def run_timing_summary(results: list[BenchmarkResult]) -> dict[str, str | float | None]:
    starts = [result.request_started_at for result in results if result.request_started_at]
    completions = [result.request_completed_at for result in results if result.request_completed_at]
    if not starts or not completions:
        return {
            "started_at": None,
            "completed_at": None,
            "duration_ms": None,
            "requests_per_second": None,
        }

    started_at = min(starts)
    completed_at = max(completions)
    duration_ms = _duration_ms(datetime.fromisoformat(started_at), datetime.fromisoformat(completed_at))
    requests_per_second = None
    if duration_ms > 0:
        requests_per_second = round(len(results) / (duration_ms / 1000), 6)
    return {
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_ms": duration_ms,
        "requests_per_second": requests_per_second,
    }


def result_from_error(
    *,
    run_id: str,
    suite: str,
    provider_name: str,
    contract: ApiContract,
    model: str,
    case: BenchmarkCase,
    message: str,
    request_started_at: str | None = None,
    request_completed_at: str | None = None,
    queue_ms: float | None = None,
    rate_limit_wait_ms: float | None = None,
    provider_identity: dict[str, Any] | None = None,
) -> BenchmarkResult:
    return BenchmarkResult(
        run_id=run_id,
        case_id=case.id,
        **case_result_metadata(case, suite),
        suite=suite,
        provider=provider_name,
        contract=contract,
        model=model,
        ok=False,
        **(provider_identity or {}),
        request_started_at=request_started_at,
        request_completed_at=request_completed_at,
        queue_ms=queue_ms,
        rate_limit_wait_ms=rate_limit_wait_ms,
        failure_class=classify_exception_failure(message),
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
        tool_ok, tool_message = evaluate_tool_call_arguments(case, response, expected_tool_name=case.expected_tool_name)
        if not tool_ok:
            return False, tool_message

    if case.expected_tool_result_substring is not None:
        results = case_simulated_tool_results(case, response)
        if not results:
            return False, "no simulated tool result was produced"
        serialized_results = json.dumps([result.model_dump(mode="json") for result in results], sort_keys=True)
        if case.expected_tool_result_substring.lower() not in serialized_results.lower():
            return False, f"missing expected simulated tool result: {case.expected_tool_result_substring}"
        if any(not result.ok for result in results):
            return False, "one or more simulated tools failed"

    if case.response_format:
        structured_ok, structured_message = evaluate_structured_output(case, response)
        if not structured_ok:
            return False, structured_message

    return True, ""


def case_with_simulated_tools(case: BenchmarkCase) -> BenchmarkCase:
    if not case.simulated_tools and not case.mcp_profile and not case.lcp_profile and not case.skills:
        return case
    existing_names = {
        tool.get("function", {}).get("name")
        for tool in case.tools
        if isinstance(tool, dict) and isinstance(tool.get("function"), dict)
    }
    candidate_schemas = []
    if case.simulated_tools:
        candidate_schemas.extend(simulated_tool_schemas(case.simulated_tools))
    if case.mcp_profile:
        candidate_schemas.extend(mcp_profile_tool_schemas(case.mcp_profile))
    injected = [
        schema
        for schema in candidate_schemas
        if schema.get("function", {}).get("name") not in existing_names
    ]
    system_prompt = case.system_prompt
    if case.lcp_profile:
        lcp_context = lcp_profile_text(case.lcp_profile)
        system_prompt = f"{lcp_context}\n\n{system_prompt}" if system_prompt else lcp_context
    if case.skills:
        prefix = skill_prefix(case.skills)
        system_prompt = f"{prefix}\n\n{system_prompt}" if system_prompt else prefix
    return case.model_copy(update={"tools": [*case.tools, *injected], "system_prompt": system_prompt})


def case_simulated_tool_results(case: BenchmarkCase, response: AdapterResponse):
    if not case.simulated_tools:
        return []
    return execute_simulated_tools(response.tool_calls, allowed_tools=case.simulated_tools)


def normalize_tool_metrics(case: BenchmarkCase, response: AdapterResponse) -> dict[str, int | None]:
    prepared_case = case_with_simulated_tools(case)
    offered_tool_schemas = tool_schema_map(prepared_case)
    offered_tool_names = set(offered_tool_schemas)
    requested = len(offered_tool_names) if offered_tool_names else None
    emitted = len(response.tool_calls) if response.tool_calls else 0 if requested is not None else None
    valid = None
    if emitted is not None:
        valid = sum(
            1
            for call in response.tool_calls
            if _tool_call_is_valid(call, offered_tool_schemas)
        )
    return {
        "tool_calls_requested": requested,
        "tool_calls_emitted": emitted,
        "tool_calls_valid": valid,
    }


def tool_schema_map(case: BenchmarkCase) -> dict[str, dict[str, Any]]:
    schemas: dict[str, dict[str, Any]] = {}
    for tool in case.tools:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function")
        if tool.get("type") == "function" and isinstance(function, dict) and function.get("name"):
            parameters = function.get("parameters")
            schemas[str(function["name"])] = parameters if isinstance(parameters, dict) else {}
            continue
        if tool.get("name"):
            input_schema = tool.get("input_schema") or tool.get("parameters")
            schemas[str(tool["name"])] = input_schema if isinstance(input_schema, dict) else {}
    return schemas


def evaluate_tool_call_arguments(
    case: BenchmarkCase,
    response: AdapterResponse,
    *,
    expected_tool_name: str | None = None,
) -> tuple[bool, str]:
    prepared_case = case_with_simulated_tools(case)
    offered_tool_schemas = tool_schema_map(prepared_case)
    calls = [
        call
        for call in response.tool_calls
        if expected_tool_name is None or call.name == expected_tool_name
    ]
    if expected_tool_name is not None and not calls:
        return False, f"missing expected tool call: {expected_tool_name}"
    for call in calls:
        if not call.valid:
            return False, f"invalid tool call emitted: {call.name}"
        if offered_tool_schemas and call.name not in offered_tool_schemas:
            return False, f"tool call {call.name} was not offered by the suite"
        schema = offered_tool_schemas.get(call.name)
        if schema:
            errors = _validate_json_schema(call.arguments, schema)
            if errors:
                return False, f"tool call {call.name} argument schema mismatch: {errors[0]}"
    return True, ""


def _tool_call_is_valid(call: Any, offered_tool_schemas: dict[str, dict[str, Any]]) -> bool:
    if not call.valid:
        return False
    if not offered_tool_schemas:
        return True
    schema = offered_tool_schemas.get(call.name)
    if schema is None:
        return False
    return not _validate_json_schema(call.arguments, schema)


def extract_raw_usage(contract: ApiContract, raw: dict) -> dict[str, Any]:
    if contract is ApiContract.NATIVE:
        usage = raw.get("usage")
        return redact_value(dict(usage)) if isinstance(usage, dict) else {}
    usage = raw.get("usage")
    return redact_value(dict(usage)) if isinstance(usage, dict) else {}


def extract_raw_stats(contract: ApiContract, raw: dict) -> dict[str, Any]:
    if contract is ApiContract.NATIVE:
        stats = raw.get("stats")
        if isinstance(stats, dict):
            return redact_value(dict(stats))
        keys = [
            "total_duration",
            "load_duration",
            "prompt_eval_count",
            "prompt_eval_duration",
            "eval_count",
            "eval_duration",
            "done_reason",
            "model",
            "created_at",
        ]
        return redact_value({key: raw[key] for key in keys if key in raw})

    if contract is ApiContract.OPENAI_RESPONSES and raw.get("stream") is True:
        return redact_value(
            {
                "stream": raw.get("stream"),
                "status": raw.get("status"),
                "event_count": len(raw.get("events", [])) if isinstance(raw.get("events"), list) else None,
            }
        )

    if contract is ApiContract.OPENAI and raw.get("stream") is True:
        return redact_value(
            {
                "stream": raw.get("stream"),
                "event_count": len(raw.get("events", [])) if isinstance(raw.get("events"), list) else None,
            }
        )

    if contract is ApiContract.ANTHROPIC and raw.get("stream") is True:
        return redact_value(
            {
                "stream": raw.get("stream"),
                "stop_reason": raw.get("stop_reason"),
                "event_count": len(raw.get("events", [])) if isinstance(raw.get("events"), list) else None,
            }
        )

    return {}


def evaluate_structured_output_validity(case: BenchmarkCase, response: AdapterResponse) -> bool | None:
    if not case.response_format and not case.expected_json_fields:
        return None
    ok, _message = evaluate_structured_output(case, response)
    return ok


def evaluate_structured_output(case: BenchmarkCase, response: AdapterResponse) -> tuple[bool, str]:
    parsed = _parse_json_text(response.text)
    if parsed is None:
        return False, "response text is not valid JSON"
    for path, expected_value in case.expected_json_fields.items():
        if _lookup_path(parsed, path) != expected_value:
            return False, f"JSON field {path} expected {expected_value!r}, got {_lookup_path(parsed, path)!r}"
    schema = _response_format_schema(case.response_format)
    if schema is not None:
        errors = _validate_json_schema(parsed, schema)
        if errors:
            return False, f"structured output schema mismatch: {errors[0]}"
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


def _response_format_schema(response_format: dict[str, Any] | None) -> dict[str, Any] | None:
    if not response_format:
        return None
    if response_format.get("type") == "json_schema":
        json_schema = response_format.get("json_schema")
        if isinstance(json_schema, dict) and isinstance(json_schema.get("schema"), dict):
            return json_schema["schema"]
        if isinstance(response_format.get("schema"), dict):
            return response_format["schema"]
    if isinstance(response_format.get("schema"), dict):
        return response_format["schema"]
    return None


def _validate_json_schema(value: Any, schema: dict[str, Any], *, path: str = "$") -> list[str]:
    errors: list[str] = []
    expected_type = schema.get("type")
    if expected_type is not None and not _json_type_matches(value, expected_type):
        errors.append(f"{path} expected type {expected_type}, got {_json_type_name(value)}")
        return errors

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path} expected const {schema['const']!r}, got {value!r}")
    if "enum" in schema and isinstance(schema["enum"], list) and value not in schema["enum"]:
        errors.append(f"{path} expected one of {schema['enum']!r}, got {value!r}")

    if isinstance(value, dict):
        required = schema.get("required", [])
        if isinstance(required, list):
            for key in required:
                if isinstance(key, str) and key not in value:
                    errors.append(f"{path}.{key} is required")
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, child_schema in properties.items():
                if key in value and isinstance(child_schema, dict):
                    errors.extend(_validate_json_schema(value[key], child_schema, path=f"{path}.{key}"))
        if schema.get("additionalProperties") is False and isinstance(properties, dict):
            allowed = set(properties)
            for key in value:
                if key not in allowed:
                    errors.append(f"{path}.{key} is not allowed")

    if isinstance(value, list):
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(value) < min_items:
            errors.append(f"{path} expected at least {min_items} item(s), got {len(value)}")
        max_items = schema.get("maxItems")
        if isinstance(max_items, int) and len(value) > max_items:
            errors.append(f"{path} expected at most {max_items} item(s), got {len(value)}")
        items_schema = schema.get("items")
        if isinstance(items_schema, dict):
            for index, item in enumerate(value):
                errors.extend(_validate_json_schema(item, items_schema, path=f"{path}[{index}]"))

    return errors


def _json_type_matches(value: Any, expected_type: Any) -> bool:
    if isinstance(expected_type, list):
        return any(_json_type_matches(value, item) for item in expected_type)
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return (isinstance(value, int | float) and not isinstance(value, bool))
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "null":
        return value is None
    return True


def _json_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return type(value).__name__


def normalize_usage(contract: ApiContract, raw: dict) -> tuple[int | None, int | None, int | None]:
    if contract is ApiContract.NATIVE:
        stats = raw.get("stats")
        if isinstance(stats, dict):
            input_tokens = _optional_int(_first_present(stats.get("input_tokens"), stats.get("prompt_tokens")))
            output_tokens = _optional_int(
                _first_present(
                    stats.get("total_output_tokens"),
                    stats.get("output_tokens"),
                    stats.get("completion_tokens"),
                )
            )
            total_tokens = _optional_int(stats.get("total_tokens"))
            usage = raw.get("usage")
            if isinstance(usage, dict):
                input_tokens = input_tokens if input_tokens is not None else _optional_int(usage.get("prompt_tokens"))
                output_tokens = (
                    output_tokens
                    if output_tokens is not None
                    else _optional_int(usage.get("completion_tokens"))
                )
                total_tokens = (
                    total_tokens if total_tokens is not None else _optional_int(usage.get("total_tokens"))
                )
            if total_tokens is None and (input_tokens is not None or output_tokens is not None):
                total_tokens = (input_tokens or 0) + (output_tokens or 0)
            return input_tokens, output_tokens, total_tokens

        input_tokens = _optional_int(raw.get("prompt_eval_count"))
        output_tokens = _optional_int(raw.get("eval_count"))
        total_tokens = None
        if input_tokens is not None or output_tokens is not None:
            total_tokens = (input_tokens or 0) + (output_tokens or 0)
        return input_tokens, output_tokens, total_tokens

    usage = raw.get("usage")
    if not isinstance(usage, dict):
        return None, None, None

    if contract is ApiContract.OPENAI:
        input_tokens = _optional_int(usage.get("prompt_tokens"))
        output_tokens = _optional_int(usage.get("completion_tokens"))
        total_tokens = _optional_int(usage.get("total_tokens"))
        return input_tokens, output_tokens, total_tokens

    if contract is ApiContract.OPENAI_RESPONSES:
        input_tokens = _optional_int(usage.get("input_tokens"))
        output_tokens = _optional_int(usage.get("output_tokens"))
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


def normalize_cache_usage(
    contract: ApiContract,
    raw: dict,
    *,
    input_tokens: int | None,
) -> tuple[int | None, int | None, float | None]:
    usage = raw.get("usage")
    if not isinstance(usage, dict):
        return None, None, None

    cached_input_tokens = None
    cache_write_tokens = None
    cache_denominator = input_tokens

    if contract is ApiContract.OPENAI:
        prompt_details = usage.get("prompt_tokens_details")
        if isinstance(prompt_details, dict):
            cached_input_tokens = _optional_int(prompt_details.get("cached_tokens"))

    elif contract is ApiContract.OPENAI_RESPONSES:
        input_details = usage.get("input_tokens_details")
        if isinstance(input_details, dict):
            cached_input_tokens = _optional_int(input_details.get("cached_tokens"))

    elif contract is ApiContract.ANTHROPIC:
        cached_input_tokens = _optional_int(usage.get("cache_read_input_tokens"))
        cache_write_tokens = _optional_int(usage.get("cache_creation_input_tokens"))
        cache_denominator = (input_tokens or 0) + (cached_input_tokens or 0) + (cache_write_tokens or 0)

    if cached_input_tokens is None and cache_write_tokens is None:
        return None, None, None

    return cached_input_tokens, cache_write_tokens, _cache_hit_ratio(cached_input_tokens, cache_denominator)


def normalize_finish_reason(contract: ApiContract, raw: dict) -> str | None:
    if contract in {ApiContract.OPENAI, ApiContract.OPENAI_RESPONSES}:
        choices = raw.get("choices", [])
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            finish_reason = choices[0].get("finish_reason")
            if finish_reason is not None:
                return str(finish_reason)
        status = raw.get("status")
        if status is not None:
            return str(status)

    if contract is ApiContract.ANTHROPIC:
        stop_reason = raw.get("stop_reason")
        if stop_reason is not None:
            return str(stop_reason)

    if contract is ApiContract.NATIVE:
        for key in ("done_reason", "finish_reason", "status"):
            value = raw.get(key)
            if value is not None:
                return str(value)
        stats = raw.get("stats")
        if isinstance(stats, dict):
            for key in ("stop_reason", "finish_reason"):
                value = stats.get(key)
                if value is not None:
                    return str(value)
        if raw.get("done") is True:
            return "done"

    return None


def normalize_timings(
    contract: ApiContract,
    raw: dict,
    *,
    input_tokens: int | None,
    output_tokens: int | None,
) -> dict[str, float | None]:
    if contract is not ApiContract.NATIVE:
        return {
            "ttft_ms": None,
            "load_ms": None,
            "prompt_eval_ms": None,
            "decode_ms": None,
            "tokens_per_second_prefill": None,
            "tokens_per_second_decode": None,
        }

    stats = raw.get("stats")
    if isinstance(stats, dict):
        decode_tps = _optional_float(
            _first_present(stats.get("tokens_per_second"), stats.get("output_tokens_per_second"))
        )
        decode_ms = None
        if output_tokens is not None and decode_tps and decode_tps > 0:
            decode_ms = round((output_tokens / decode_tps) * 1000, 3)
        return {
            "ttft_ms": _seconds_to_ms(
                _first_present(
                    stats.get("time_to_first_token_seconds"),
                    stats.get("time_to_first_token"),
                    stats.get("ttft_seconds"),
                    stats.get("ttft"),
                )
            ),
            "load_ms": _seconds_to_ms(
                _first_present(stats.get("model_load_time_seconds"), stats.get("model_load_time"))
            ),
            "prompt_eval_ms": None,
            "decode_ms": decode_ms,
            "tokens_per_second_prefill": None,
            "tokens_per_second_decode": decode_tps,
        }

    load_ms = _ns_to_ms(raw.get("load_duration"))
    prompt_eval_ms = _ns_to_ms(raw.get("prompt_eval_duration"))
    decode_ms = _ns_to_ms(raw.get("eval_duration"))
    return {
        "ttft_ms": None,
        "load_ms": load_ms,
        "prompt_eval_ms": prompt_eval_ms,
        "decode_ms": decode_ms,
        "tokens_per_second_prefill": _tokens_per_second(input_tokens, prompt_eval_ms),
        "tokens_per_second_decode": _tokens_per_second(output_tokens, decode_ms),
    }


def _redacted_telemetry_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return redact_value(dict(value))


def _optional_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_present(*values):
    for value in values:
        if value is not None:
            return value
    return None


def _optional_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ns_to_ms(value) -> float | None:
    integer = _optional_int(value)
    if integer is None:
        return None
    return round(integer / 1_000_000, 3)


def _seconds_to_ms(value) -> float | None:
    number = _optional_float(value)
    if number is None:
        return None
    return round(number * 1000, 3)


def _tokens_per_second(tokens: int | None, duration_ms: float | None) -> float | None:
    if tokens is None or duration_ms is None or duration_ms <= 0:
        return None
    return round(tokens / (duration_ms / 1000), 3)


def _cache_hit_ratio(cached_input_tokens: int | None, denominator: int | None) -> float | None:
    if cached_input_tokens is None or denominator is None or denominator <= 0:
        return None
    return round(cached_input_tokens / denominator, 6)


def _duration_ms(started_at: datetime, completed_at: datetime) -> float:
    return round(max((completed_at - started_at).total_seconds() * 1000, 0.0), 3)


def _safe_url(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))


def _scenario_from_tags(tags: list[str], suite: str) -> str:
    for tag in tags:
        if tag:
            return tag
    return suite


def _sha256_json(value: Any) -> str:
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
