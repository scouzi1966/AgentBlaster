from __future__ import annotations

import json

from agentblaster.models import (
    AdapterResponse,
    ApiContract,
    BenchmarkCase,
    BenchmarkResult,
    ModelMetadata,
    ProviderConfig,
    RawTraceMode,
    RetentionPolicy,
    SuiteDefinition,
    ToolCallRecord,
)
from agentblaster.observability import PrometheusScrape
from agentblaster.runner import (
    BenchmarkRunner,
    SmokeRunner,
    case_with_simulated_tools,
    evaluate_case_assertions,
    evaluate_structured_output,
    evaluate_structured_output_validity,
    evaluate_tool_call_arguments,
    estimate_costs,
    case_sha256_map,
    normalize_cache_usage,
    normalize_finish_reason,
    normalize_timings,
    normalize_tool_metrics,
    normalize_usage,
    extract_raw_stats,
    extract_raw_usage,
    run_timing_summary,
    suite_sha256,
    provider_run_metadata,
    result_from_response,
)


class FakeAdapter:
    adapter_name = "fake-adapter"
    adapter_version = "fake-adapter-v1"

    def __init__(self, response: AdapterResponse) -> None:
        self.response = response

    def smoke_chat(self, model: str) -> AdapterResponse:
        return self.response

    def chat_completion(self, model: str, case: BenchmarkCase) -> AdapterResponse:
        return self.response


class FailingAdapter:
    def chat_completion(self, model: str, case: BenchmarkCase) -> AdapterResponse:
        raise RuntimeError("provider exploded")


def test_normalize_openai_usage() -> None:
    assert normalize_usage(
        ApiContract.OPENAI,
        {"usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14}},
    ) == (10, 4, 14)


def test_normalize_openai_finish_reason() -> None:
    assert normalize_finish_reason(
        ApiContract.OPENAI,
        {"choices": [{"finish_reason": "tool_calls"}]},
    ) == "tool_calls"


def test_normalize_openai_cache_usage() -> None:
    assert normalize_cache_usage(
        ApiContract.OPENAI,
        {
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 4,
                "total_tokens": 104,
                "prompt_tokens_details": {"cached_tokens": 75},
            }
        },
        input_tokens=100,
    ) == (75, None, 0.75)


def test_estimate_costs_uses_provider_cost_model() -> None:
    assert estimate_costs(
        {
            "input_usd_per_1m_tokens": 2.0,
            "output_usd_per_1m_tokens": 8.0,
            "cached_input_usd_per_1m_tokens": 0.5,
            "cache_write_usd_per_1m_tokens": 3.0,
            "request_usd": 0.0001,
        },
        input_tokens=100,
        output_tokens=50,
        cached_input_tokens=25,
        cache_write_tokens=10,
    ) == {
        "input_cost_usd": 0.00015,
        "output_cost_usd": 0.0004,
        "cache_read_cost_usd": 0.0000125,
        "cache_write_cost_usd": 0.00003,
        "request_cost_usd": 0.0001,
        "total_cost_usd": 0.0006925,
    }


def test_normalize_openai_responses_usage() -> None:
    assert normalize_usage(
        ApiContract.OPENAI_RESPONSES,
        {"usage": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14}},
    ) == (10, 4, 14)


def test_normalize_openai_responses_cache_usage() -> None:
    assert normalize_cache_usage(
        ApiContract.OPENAI_RESPONSES,
        {
            "usage": {
                "input_tokens": 100,
                "output_tokens": 4,
                "total_tokens": 104,
                "input_tokens_details": {"cached_tokens": 25},
            }
        },
        input_tokens=100,
    ) == (25, None, 0.25)


def test_normalize_anthropic_usage_includes_cache_tokens() -> None:
    assert normalize_usage(
        ApiContract.ANTHROPIC,
        {
            "usage": {
                "input_tokens": 10,
                "output_tokens": 4,
                "cache_read_input_tokens": 20,
                "cache_creation_input_tokens": 3,
            }
        },
    ) == (10, 4, 37)


def test_normalize_anthropic_finish_reason() -> None:
    assert normalize_finish_reason(ApiContract.ANTHROPIC, {"stop_reason": "end_turn"}) == "end_turn"


def test_normalize_anthropic_cache_usage() -> None:
    assert normalize_cache_usage(
        ApiContract.ANTHROPIC,
        {
            "usage": {
                "input_tokens": 10,
                "output_tokens": 4,
                "cache_read_input_tokens": 20,
                "cache_creation_input_tokens": 10,
            }
        },
        input_tokens=10,
    ) == (20, 10, 0.5)


def test_normalize_native_ollama_usage_and_timings() -> None:
    raw = {
        "prompt_eval_count": 10,
        "prompt_eval_duration": 100_000_000,
        "eval_count": 5,
        "eval_duration": 50_000_000,
        "load_duration": 25_000_000,
    }

    input_tokens, output_tokens, total_tokens = normalize_usage(ApiContract.NATIVE, raw)
    timings = normalize_timings(ApiContract.NATIVE, raw, input_tokens=input_tokens, output_tokens=output_tokens)

    assert (input_tokens, output_tokens, total_tokens) == (10, 5, 15)
    assert timings["load_ms"] == 25.0
    assert timings["prompt_eval_ms"] == 100.0
    assert timings["decode_ms"] == 50.0
    assert timings["tokens_per_second_prefill"] == 100.0
    assert timings["tokens_per_second_decode"] == 100.0


def test_normalize_native_lmstudio_stats_and_timings() -> None:
    raw = {
        "stats": {
            "input_tokens": 10,
            "total_output_tokens": 5,
            "tokens_per_second": 25.0,
            "time_to_first_token_seconds": 0.2,
            "model_load_time_seconds": 1.5,
        }
    }

    input_tokens, output_tokens, total_tokens = normalize_usage(ApiContract.NATIVE, raw)
    timings = normalize_timings(ApiContract.NATIVE, raw, input_tokens=input_tokens, output_tokens=output_tokens)

    assert (input_tokens, output_tokens, total_tokens) == (10, 5, 15)
    assert timings["ttft_ms"] == 200.0
    assert timings["load_ms"] == 1500.0
    assert timings["decode_ms"] == 200.0
    assert timings["tokens_per_second_decode"] == 25.0


def test_extract_raw_usage_and_stats_preserves_metric_provenance_without_full_payload() -> None:
    raw = {
        "message": {"content": "agentblaster-ok"},
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        "stats": {"tokens_per_second": 25.0, "time_to_first_token_seconds": 0.2},
        "headers": {"Authorization": "Bearer should-not-leak"},
    }

    assert extract_raw_usage(ApiContract.NATIVE, raw) == {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
    }
    assert extract_raw_stats(ApiContract.NATIVE, raw) == {
        "tokens_per_second": 25.0,
        "time_to_first_token_seconds": 0.2,
    }


def test_extract_raw_stats_summarizes_streaming_event_metadata() -> None:
    raw = {
        "stream": True,
        "status": "completed",
        "events": [{"type": "response.output_text.delta"}, {"type": "response.completed"}],
        "headers": {"Authorization": "Bearer should-not-leak"},
    }

    assert extract_raw_stats(ApiContract.OPENAI_RESPONSES, raw) == {
        "stream": True,
        "status": "completed",
        "event_count": 2,
    }


def test_run_timing_summary_computes_duration_and_throughput() -> None:
    results = [
        BenchmarkResult(
            run_id="run_test",
            case_id="case-one",
            suite="smoke",
            provider="local",
            contract=ApiContract.OPENAI,
            model="qwen-test",
            ok=True,
            request_started_at="2026-05-31T00:00:00+00:00",
            request_completed_at="2026-05-31T00:00:01+00:00",
        ),
        BenchmarkResult(
            run_id="run_test",
            case_id="case-two",
            suite="smoke",
            provider="local",
            contract=ApiContract.OPENAI,
            model="qwen-test",
            ok=True,
            request_started_at="2026-05-31T00:00:00.500000+00:00",
            request_completed_at="2026-05-31T00:00:02+00:00",
        ),
    ]

    assert run_timing_summary(results) == {
        "started_at": "2026-05-31T00:00:00+00:00",
        "completed_at": "2026-05-31T00:00:02+00:00",
        "duration_ms": 2000.0,
        "requests_per_second": 1.0,
    }


def test_merge_model_metadata_prefers_run_overrides() -> None:
    from agentblaster.runner import merge_model_metadata

    merged = merge_model_metadata(
        ModelMetadata(revision="provider-rev", architecture="qwen3-dense", quantization="mlx-f16"),
        ModelMetadata(revision="run-rev", context_length=32768),
    )

    assert merged.revision == "run-rev"
    assert merged.architecture == "qwen3-dense"
    assert merged.quantization == "mlx-f16"
    assert merged.context_length == 32768


def test_suite_hashes_are_deterministic_and_prompt_sensitive() -> None:
    suite = SuiteDefinition(
        name="hash-suite",
        description="hash suite",
        cases=[BenchmarkCase(id="case-one", title="case one", prompt="Prompt A")],
    )
    same_suite = SuiteDefinition(
        name="hash-suite",
        description="hash suite",
        cases=[BenchmarkCase(id="case-one", title="case one", prompt="Prompt A")],
    )
    changed_suite = SuiteDefinition(
        name="hash-suite",
        description="hash suite",
        cases=[BenchmarkCase(id="case-one", title="case one", prompt="Prompt B")],
    )

    assert suite_sha256(suite) == suite_sha256(same_suite)
    assert case_sha256_map(suite) == case_sha256_map(same_suite)
    assert suite_sha256(suite) != suite_sha256(changed_suite)
    assert case_sha256_map(suite)["case-one"] != case_sha256_map(changed_suite)["case-one"]


def test_smoke_runner_writes_manifest_result_and_redacted_raw(tmp_path) -> None:
    provider = ProviderConfig(
        name="openai-like",
        contract=ApiContract.OPENAI,
        base_url="https://example.com/v1",
        model_metadata=ModelMetadata(revision="provider-rev", architecture="qwen3-dense"),
        cost_model={
            "input_usd_per_1m_tokens": 2.0,
            "output_usd_per_1m_tokens": 8.0,
            "cached_input_usd_per_1m_tokens": 0.5,
            "request_usd": 0.0001,
        },
        remote=True,
    )
    response = AdapterResponse(
        provider="openai-like",
        contract=ApiContract.OPENAI,
        status_code=200,
        latency_ms=12.3456,
        text="agentblaster-ok",
        raw={
            "choices": [{"message": {"content": "agentblaster-ok"}, "finish_reason": "stop"}],
            "headers": {"Authorization": "Bearer abcdefghijklmnopqrstuvwxyz"},
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 3,
                "total_tokens": 8,
                "prompt_tokens_details": {"cached_tokens": 2},
            },
        },
    )

    result = SmokeRunner(
        provider,
        adapter=FakeAdapter(response),  # type: ignore[arg-type]
        output_dir=tmp_path,
        raw_trace_mode=RawTraceMode.REDACTED,
    ).run(model="qwen-test")

    run_dir = tmp_path / result.run_id
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["model_metadata"]["revision"] == "provider-rev"
    assert manifest["model_metadata"]["architecture"] == "qwen3-dense"
    assert manifest["provider_metadata"]["base_url"] == "https://example.com/v1"
    assert manifest["provider_metadata"]["base_url_host"] == "example.com"
    assert manifest["provider_metadata"]["remote"] is True
    assert manifest["provider_metadata"]["tls_verify"] is True
    assert manifest["provider_metadata"]["ca_bundle"] is None
    assert manifest["provider_metadata"]["adapter_name"] == "fake-adapter"
    assert manifest["provider_metadata"]["adapter_version"] == "fake-adapter-v1"
    assert manifest["suite_snapshot_path"] == "suite.json"
    assert manifest["suite_provenance"]["origin"] == "unknown"
    assert manifest["retention_policy"]["classification"] == "internal"
    assert len(manifest["suite_sha256"]) == 64
    assert len(manifest["case_sha256"]["protocol-smoke-chat"]) == 64
    suite_snapshot = json.loads((run_dir / "suite.json").read_text(encoding="utf-8"))
    assert suite_snapshot["name"] == "smoke"
    assert suite_snapshot["cases"][0]["id"] == "protocol-smoke-chat"
    assert result.ok is True
    assert result.case_title == "Protocol smoke chat"
    assert result.scenario == "smoke"
    assert result.case_provenance == "synthetic_representative"
    assert result.case_risk_level == "low"
    assert result.provider_endpoint_host == "example.com"
    assert result.provider_remote is True
    assert result.adapter_name == "fake-adapter"
    assert result.adapter_version == "fake-adapter-v1"
    assert result.request_started_at is not None
    assert result.request_completed_at is not None
    assert result.queue_ms == 0.0
    assert result.rate_limit_wait_ms == 0.0
    assert result.input_tokens == 5
    assert result.cached_input_tokens == 2
    assert result.cache_hit_ratio == 0.4
    assert result.total_cost_usd == 0.000131
    assert result.finish_reason == "stop"
    assert result.raw_usage["prompt_tokens"] == 5
    assert result.raw_usage["prompt_tokens_details"]["cached_tokens"] == 2
    assert result.raw_stats == {}
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "results.jsonl").exists()
    assert result.raw_response_path == "raw/protocol-smoke-chat.response.json"

    raw_payload = json.loads((run_dir / result.raw_response_path).read_text())
    assert raw_payload["headers"]["Authorization"] == "[REDACTED]"
    integrity = json.loads((run_dir / "integrity.json").read_text(encoding="utf-8"))
    assert integrity["run_id"] == result.run_id
    assert "manifest.json" in integrity["artifacts"]
    assert "suite.json" in integrity["artifacts"]
    assert "results.jsonl" in integrity["artifacts"]
    assert "raw/protocol-smoke-chat.response.json" in integrity["artifacts"]
    assert "integrity.json" not in integrity["artifacts"]
    assert len(integrity["artifacts"]["results.jsonl"]) == 64


def test_runner_writes_native_timing_fields(tmp_path) -> None:
    provider = ProviderConfig(
        name="ollama-native",
        contract=ApiContract.NATIVE,
        base_url="http://example.com",
        native_adapter="ollama",
    )
    response = AdapterResponse(
        provider="ollama-native",
        contract=ApiContract.NATIVE,
        status_code=200,
        latency_ms=12.0,
        text="agentblaster-ok",
        raw={
            "message": {"content": "agentblaster-ok"},
            "prompt_eval_count": 10,
            "prompt_eval_duration": 100_000_000,
            "eval_count": 5,
            "eval_duration": 50_000_000,
            "load_duration": 25_000_000,
        },
    )

    result = SmokeRunner(
        provider,
        adapter=FakeAdapter(response),  # type: ignore[arg-type]
        output_dir=tmp_path,
        raw_trace_mode=RawTraceMode.OFF,
    ).run(model="qwen-test")

    assert result.input_tokens == 10
    assert result.output_tokens == 5
    assert result.load_ms == 25.0
    assert result.ttft_ms is None
    assert result.tokens_per_second_decode == 100.0


def test_provider_run_metadata_sanitizes_endpoint_and_captures_adapter_identity() -> None:
    provider = ProviderConfig(
        name="native",
        contract=ApiContract.NATIVE,
        base_url="http://127.0.0.1:11434/api/",
        metrics_url="http://127.0.0.1:11434/metrics",
        native_adapter="ollama",
        capabilities={"streaming": True},
    )
    adapter = FakeAdapter(AdapterResponse(provider="native", contract=ApiContract.NATIVE, status_code=200, latency_ms=1.0))

    metadata = provider_run_metadata(provider, adapter)  # type: ignore[arg-type]

    assert metadata.base_url == "http://127.0.0.1:11434/api"
    assert metadata.base_url_host == "127.0.0.1"
    assert metadata.metrics_url_host == "127.0.0.1"
    assert metadata.native_adapter == "ollama"
    assert metadata.adapter_name == "fake-adapter"
    assert metadata.adapter_version == "fake-adapter-v1"
    assert metadata.capabilities == {"streaming": True}


def test_smoke_runner_can_disable_raw_traces(tmp_path) -> None:
    provider = ProviderConfig(name="openai-like", contract=ApiContract.OPENAI, base_url="https://example.com/v1")
    response = AdapterResponse(
        provider="openai-like",
        contract=ApiContract.OPENAI,
        status_code=200,
        latency_ms=1.0,
        text="agentblaster-ok",
        raw={"usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}},
    )

    result = SmokeRunner(
        provider,
        adapter=FakeAdapter(response),  # type: ignore[arg-type]
        output_dir=tmp_path,
        raw_trace_mode=RawTraceMode.OFF,
    ).run(model="qwen-test")

    assert result.raw_response_path is None
    assert not (tmp_path / result.run_id / "raw").exists()


def test_benchmark_runner_writes_summary_for_suite(tmp_path) -> None:
    provider = ProviderConfig(name="openai-like", contract=ApiContract.OPENAI, base_url="https://example.com/v1")
    suite = SuiteDefinition(
        name="custom-smoke",
        description="custom suite",
        cases=[
            BenchmarkCase(
                id="case-one",
                title="case one",
                prompt="Reply with exactly: agentblaster-ok",
                scenario="protocol smoke",
                expected_substring="agentblaster-ok",
            )
        ],
    )
    response = AdapterResponse(
        provider="openai-like",
        contract=ApiContract.OPENAI,
        status_code=200,
        latency_ms=1.0,
        text="agentblaster-ok",
        raw={"usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}},
    )

    summary = BenchmarkRunner(
        provider,
        suite,
        adapter=FakeAdapter(response),  # type: ignore[arg-type]
        output_dir=tmp_path,
        raw_trace_mode=RawTraceMode.OFF,
        concurrency=2,
        retention_policy=RetentionPolicy(
            classification="confidential",
            retain_days=30,
            raw_trace_retain_days=7,
            notes=["delete raw traces first"],
        ),
    ).run(model="qwen-test")

    assert summary.total_cases == 1
    assert summary.passed == 1
    assert summary.concurrency == 2
    assert summary.duration_ms is not None
    assert summary.requests_per_second is not None
    run_dir = tmp_path / summary.run_id
    assert (run_dir / "summary.json").exists()
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    suite_snapshot = json.loads((run_dir / "suite.json").read_text(encoding="utf-8"))
    assert manifest["suite_sha256"] == suite_sha256(suite)
    assert manifest["case_sha256"] == case_sha256_map(suite)
    assert manifest["suite_snapshot_path"] == "suite.json"
    assert manifest["suite_provenance"]["origin"] == "unknown"
    assert manifest["retention_policy"] == {
        "classification": "confidential",
        "retain_days": 30,
        "raw_trace_retain_days": 7,
        "notes": ["delete raw traces first"],
    }
    assert suite_snapshot["name"] == "custom-smoke"
    assert suite_snapshot["cases"][0]["prompt"] == "Reply with exactly: agentblaster-ok"
    result_payload = json.loads((run_dir / "results.jsonl").read_text(encoding="utf-8"))
    assert result_payload["request_started_at"]
    assert result_payload["case_title"] == "case one"
    assert result_payload["scenario"] == "protocol smoke"
    assert result_payload["case_tags"] == []
    assert result_payload["request_completed_at"]
    assert result_payload["queue_ms"] >= 0
    assert result_payload["rate_limit_wait_ms"] == 0.0
    integrity = json.loads((run_dir / "integrity.json").read_text(encoding="utf-8"))
    assert "suite.json" in integrity["artifacts"]
    assert "summary.json" in integrity["artifacts"]


def test_benchmark_runner_writes_prometheus_metrics_artifacts(tmp_path) -> None:
    provider = ProviderConfig(
        name="openai-like",
        contract=ApiContract.OPENAI,
        base_url="https://example.com/v1",
        metrics_url="http://127.0.0.1:9999/metrics",
    )
    suite = SuiteDefinition(
        name="metrics-smoke",
        description="metrics suite",
        cases=[
            BenchmarkCase(
                id="case-one",
                title="case one",
                prompt="Reply with exactly: agentblaster-ok",
                expected_substring="agentblaster-ok",
            )
        ],
    )
    response = AdapterResponse(
        provider="openai-like",
        contract=ApiContract.OPENAI,
        status_code=200,
        latency_ms=1.0,
        text="agentblaster-ok",
        raw={"usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}},
    )
    runner = BenchmarkRunner(
        provider,
        suite,
        adapter=FakeAdapter(response),  # type: ignore[arg-type]
        output_dir=tmp_path,
        raw_trace_mode=RawTraceMode.OFF,
    )

    def fake_scraper(url: str, *, phase: str) -> PrometheusScrape:
        value = 1.0 if phase == "before" else 3.0
        return PrometheusScrape(
            phase=phase,
            url=url,
            scraped_at="2026-05-31T00:00:00+00:00",
            latency_ms=1.0,
            ok=True,
            status_code=200,
            text=f"agentblaster_queue_depth {value}\n",
        )

    runner.metrics_scraper = fake_scraper
    summary = runner.run(model="qwen-test")

    run_dir = tmp_path / summary.run_id
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    prometheus_summary = json.loads((run_dir / "metrics/prometheus-summary.json").read_text(encoding="utf-8"))
    integrity = json.loads((run_dir / "integrity.json").read_text(encoding="utf-8"))
    assert manifest["metrics_artifacts"] == [
        "metrics/prometheus-before.prom",
        "metrics/prometheus-after.prom",
        "metrics/prometheus-summary.json",
    ]
    assert prometheus_summary["deltas"]["agentblaster_queue_depth"]["delta"] == 2.0
    assert "metrics/prometheus-before.prom" in integrity["artifacts"]
    assert "metrics/prometheus-after.prom" in integrity["artifacts"]
    assert "metrics/prometheus-summary.json" in integrity["artifacts"]


def test_benchmark_runner_records_case_runtime_failures(tmp_path) -> None:
    provider = ProviderConfig(name="openai-like", contract=ApiContract.OPENAI, base_url="https://example.com/v1")
    suite = SuiteDefinition(
        name="custom-smoke",
        description="custom suite",
        cases=[
            BenchmarkCase(
                id="case-one",
                title="case one",
                prompt="Reply with exactly: agentblaster-ok",
                expected_substring="agentblaster-ok",
            )
        ],
    )

    summary = BenchmarkRunner(
        provider,
        suite,
        adapter=FailingAdapter(),  # type: ignore[arg-type]
        output_dir=tmp_path,
        raw_trace_mode=RawTraceMode.OFF,
    ).run(model="qwen-test")

    assert summary.failed == 1
    result_line = (tmp_path / summary.run_id / "results.jsonl").read_text(encoding="utf-8")
    assert "engine_runtime_bug" in result_line
    assert "provider exploded" in result_line


def test_evaluate_case_assertions_supports_json_fields() -> None:
    case = BenchmarkCase(
        id="json-case",
        title="json case",
        prompt="Return JSON",
        expected_json_fields={"status": "agentblaster-ok", "nested.count": 1},
    )
    response = AdapterResponse(
        provider="openai-like",
        contract=ApiContract.OPENAI,
        status_code=200,
        latency_ms=1.0,
        text='{"status":"agentblaster-ok","nested":{"count":1}}',
    )

    assert evaluate_case_assertions(case, response) == (True, "")


def test_evaluate_case_assertions_reports_json_mismatch() -> None:
    case = BenchmarkCase(
        id="json-case",
        title="json case",
        prompt="Return JSON",
        expected_json_fields={"status": "agentblaster-ok"},
    )
    response = AdapterResponse(
        provider="openai-like",
        contract=ApiContract.OPENAI,
        status_code=200,
        latency_ms=1.0,
        text='{"status":"wrong"}',
    )

    ok, message = evaluate_case_assertions(case, response)

    assert ok is False
    assert "JSON field status expected" in message


def test_evaluate_case_assertions_supports_tool_name() -> None:
    case = BenchmarkCase(
        id="tool-case",
        title="tool case",
        prompt="Use tool",
        expected_tool_name="ping_agentblaster",
    )
    response = AdapterResponse(
        provider="openai-like",
        contract=ApiContract.OPENAI,
        status_code=200,
        latency_ms=1.0,
        tool_names=["ping_agentblaster"],
    )

    assert evaluate_case_assertions(case, response) == (True, "")


def test_normalize_tool_metrics_counts_requested_emitted_and_valid_calls() -> None:
    case = BenchmarkCase(
        id="tool-case",
        title="tool case",
        prompt="Use tool",
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "ping_agentblaster",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
    )
    response = AdapterResponse(
        provider="openai-like",
        contract=ApiContract.OPENAI,
        status_code=200,
        latency_ms=1.0,
        tool_calls=[ToolCallRecord(name="ping_agentblaster"), ToolCallRecord(name="unknown_tool")],
    )

    assert normalize_tool_metrics(case, response) == {
        "tool_calls_requested": 1,
        "tool_calls_emitted": 2,
        "tool_calls_valid": 1,
    }


def test_normalize_tool_metrics_validates_tool_argument_schema() -> None:
    case = BenchmarkCase(
        id="tool-case",
        title="tool case",
        prompt="Use tool",
        expected_tool_name="ping_agentblaster",
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "ping_agentblaster",
                    "parameters": {
                        "type": "object",
                        "required": ["target"],
                        "additionalProperties": False,
                        "properties": {"target": {"type": "string", "const": "agentblaster-ok"}},
                    },
                },
            }
        ],
    )
    response = AdapterResponse(
        provider="openai-like",
        contract=ApiContract.OPENAI,
        status_code=200,
        latency_ms=1.0,
        tool_calls=[
            ToolCallRecord(name="ping_agentblaster", arguments={"target": "agentblaster-ok"}),
            ToolCallRecord(name="ping_agentblaster", arguments={"target": 123}),
        ],
    )

    assert normalize_tool_metrics(case, response) == {
        "tool_calls_requested": 1,
        "tool_calls_emitted": 2,
        "tool_calls_valid": 1,
    }
    assert evaluate_tool_call_arguments(case, response, expected_tool_name="ping_agentblaster") == (
        False,
        "tool call ping_agentblaster argument schema mismatch: $.target expected type string, got integer",
    )


def test_tool_argument_schema_failure_marks_required_tool_case_not_ok() -> None:
    from agentblaster.runner import result_from_response

    case = BenchmarkCase(
        id="tool-case",
        title="tool case",
        prompt="Use tool",
        expected_tool_name="ping_agentblaster",
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "ping_agentblaster",
                    "parameters": {
                        "type": "object",
                        "required": ["target"],
                        "properties": {"target": {"const": "agentblaster-ok"}},
                    },
                },
            }
        ],
    )
    response = AdapterResponse(
        provider="openai-like",
        contract=ApiContract.OPENAI,
        status_code=200,
        latency_ms=1.0,
        tool_names=["ping_agentblaster"],
        tool_calls=[ToolCallRecord(name="ping_agentblaster", arguments={"target": "wrong"})],
    )

    result = result_from_response(
        run_id="run_test",
        suite="toolcall",
        provider_name="openai-like",
        model="qwen-test",
        case=case,
        response=response,
        raw_response_path=None,
    )

    assert result.ok is False
    assert result.tool_calls_valid == 0
    assert "tool call ping_agentblaster argument schema mismatch" in result.message


def test_evaluate_structured_output_validity_uses_expected_json_fields() -> None:
    case = BenchmarkCase(
        id="json-case",
        title="json case",
        prompt="Return JSON",
        response_format={"type": "json_object"},
        expected_json_fields={"status": "agentblaster-ok"},
    )
    good_response = AdapterResponse(
        provider="openai-like",
        contract=ApiContract.OPENAI,
        status_code=200,
        latency_ms=1.0,
        text='{"status":"agentblaster-ok"}',
    )
    bad_response = AdapterResponse(
        provider="openai-like",
        contract=ApiContract.OPENAI,
        status_code=200,
        latency_ms=1.0,
        text='{"status":"wrong"}',
    )

    assert evaluate_structured_output_validity(case, good_response) is True
    assert evaluate_structured_output_validity(case, bad_response) is False


def test_evaluate_structured_output_validates_json_schema_response_format() -> None:
    case = BenchmarkCase(
        id="schema-case",
        title="schema case",
        prompt="Return JSON",
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "agentblaster_status",
                "strict": True,
                "schema": {
                    "type": "object",
                    "required": ["status", "count", "items"],
                    "additionalProperties": False,
                    "properties": {
                        "status": {"type": "string", "enum": ["agentblaster-ok"]},
                        "count": {"type": "integer"},
                        "items": {
                            "type": "array",
                            "minItems": 1,
                            "items": {
                                "type": "object",
                                "required": ["name"],
                                "additionalProperties": False,
                                "properties": {"name": {"type": "string"}},
                            },
                        },
                    },
                },
            },
        },
    )
    good_response = AdapterResponse(
        provider="openai-like",
        contract=ApiContract.OPENAI,
        status_code=200,
        latency_ms=1.0,
        text='{"status":"agentblaster-ok","count":1,"items":[{"name":"case-one"}]}',
    )
    bad_response = AdapterResponse(
        provider="openai-like",
        contract=ApiContract.OPENAI,
        status_code=200,
        latency_ms=1.0,
        text='{"status":"wrong","count":"1","items":[{"name":"case-one","extra":true}]}',
    )

    assert evaluate_structured_output(case, good_response) == (True, "")
    ok, message = evaluate_structured_output(case, bad_response)
    assert ok is False
    assert "structured output schema mismatch" in message


def test_response_format_schema_failure_marks_result_not_ok() -> None:
    from agentblaster.runner import result_from_response

    case = BenchmarkCase(
        id="schema-case",
        title="schema case",
        prompt="Return JSON",
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "agentblaster_status",
                "schema": {
                    "type": "object",
                    "required": ["status"],
                    "properties": {"status": {"const": "agentblaster-ok"}},
                },
            },
        },
    )
    response = AdapterResponse(
        provider="openai-like",
        contract=ApiContract.OPENAI,
        status_code=200,
        latency_ms=1.0,
        text='{"status":"wrong"}',
    )

    result = result_from_response(
        run_id="run_test",
        suite="structured",
        provider_name="openai-like",
        model="qwen-test",
        case=case,
        response=response,
        raw_response_path=None,
    )

    assert result.ok is False
    assert result.structured_output_valid is False
    assert "structured output schema mismatch" in result.message


def test_result_from_response_classifies_rate_limit() -> None:
    from agentblaster.runner import result_from_response

    case = BenchmarkCase(
        id="rate-limit-case",
        title="rate limit case",
        prompt="Hello",
        expected_substring="agentblaster-ok",
    )
    response = AdapterResponse(
        provider="openai-like",
        contract=ApiContract.OPENAI,
        status_code=429,
        latency_ms=1.0,
        text="rate limited",
        raw={},
    )

    result = result_from_response(
        run_id="run_test",
        suite="smoke",
        provider_name="openai-like",
        model="qwen-test",
        case=case,
        response=response,
        raw_response_path=None,
    )

    assert result.ok is False
    assert result.failure_class == "rate_limit"


def test_case_with_simulated_tools_injects_safe_tool_schema() -> None:
    case = BenchmarkCase(
        id="toolsim-case",
        title="toolsim case",
        prompt="Search docs",
        simulated_tools=["search_docs"],
    )

    prepared = case_with_simulated_tools(case)

    assert prepared.tools[0]["function"]["name"] == "search_docs"
    assert case.tools == []


def test_case_with_skills_injects_skill_prefix_into_system_prompt() -> None:
    case = BenchmarkCase(
        id="skill-case",
        title="skill case",
        prompt="Use skills",
        system_prompt="Existing policy.",
        skills=["repo-triage", "agent-planning"],
    )

    prepared = case_with_simulated_tools(case)

    assert prepared.system_prompt is not None
    assert prepared.system_prompt.startswith("# AgentBlaster skill instructions")
    assert "# Skill: repo-triage" in prepared.system_prompt
    assert "# Skill: agent-planning" in prepared.system_prompt
    assert prepared.system_prompt.endswith("Existing policy.")


def test_case_with_mcp_profile_injects_fixture_tool_schemas() -> None:
    case = BenchmarkCase(
        id="mcp-case",
        title="mcp case",
        prompt="Use MCP tools",
        mcp_profile="fixture-mcp",
    )

    prepared = case_with_simulated_tools(case)

    assert [tool["function"]["name"] for tool in prepared.tools] == [
        "mcp_fixture_read_resource",
        "mcp_fixture_call_tool",
        "mcp_fixture_list_prompts",
    ]
    assert case.tools == []


def test_evaluate_case_assertions_supports_simulated_tool_result() -> None:
    case = BenchmarkCase(
        id="toolsim-case",
        title="toolsim case",
        prompt="Search docs",
        simulated_tools=["search_docs"],
        expected_tool_name="search_docs",
        expected_tool_result_substring="local agentic inference engines",
    )
    response = AdapterResponse(
        provider="openai-like",
        contract=ApiContract.OPENAI,
        status_code=200,
        latency_ms=1.0,
        tool_names=["search_docs"],
        tool_calls=[ToolCallRecord(name="search_docs", arguments={"query": "AgentBlaster PRD"})],
    )

    assert evaluate_case_assertions(case, response) == (True, "")

def test_result_from_response_uses_normalized_provider_telemetry() -> None:
    case = BenchmarkCase(id="case-one", title="case one", prompt="Reply ok", expected_substring="ok")
    response = AdapterResponse(
        provider="ollama-local",
        contract=ApiContract.NATIVE,
        status_code=200,
        latency_ms=31.2,
        text="ok",
        raw={
            "prompt_eval_count": 100,
            "prompt_eval_duration": 2_000_000_000,
            "eval_count": 50,
            "eval_duration": 1_000_000_000,
            "done_reason": "stop",
        },
    )

    result = result_from_response(
        run_id="run_test",
        suite="native-suite",
        provider_name="ollama-local",
        model="qwen-test",
        case=case,
        response=response,
        raw_response_path=None,
        provider_identity={"native_adapter": "ollama"},
    )

    assert result.ok is True
    assert result.input_tokens == 100
    assert result.output_tokens == 50
    assert result.prompt_eval_ms == 2000.0
    assert result.decode_ms == 1000.0
    assert result.tokens_per_second_prefill == 50.0
    assert result.tokens_per_second_decode == 50.0
    assert result.raw_stats["prompt_eval_duration"] == 2_000_000_000
    assert result.finish_reason == "stop"

def test_case_with_simulated_tools_injects_lcp_context() -> None:
    case = BenchmarkCase(
        id="case-one",
        title="case one",
        prompt="Use attached context",
        system_prompt="Base system prompt.",
        lcp_profile="fixture-lcp",
    )

    prepared = case_with_simulated_tools(case)

    assert prepared.system_prompt is not None
    assert "AgentBlaster LCP Fixture" in prepared.system_prompt
    assert "agentblaster-lcp-ok" in prepared.system_prompt
    assert prepared.system_prompt.endswith("Base system prompt.")

