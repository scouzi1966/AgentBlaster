from __future__ import annotations

import json

from agentblaster.models import AdapterResponse, ApiContract, BenchmarkCase, ProviderConfig, RawTraceMode, SuiteDefinition
from agentblaster.runner import BenchmarkRunner, SmokeRunner, evaluate_case_assertions, normalize_timings, normalize_usage


class FakeAdapter:
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


def test_smoke_runner_writes_manifest_result_and_redacted_raw(tmp_path) -> None:
    provider = ProviderConfig(
        name="openai-like",
        contract=ApiContract.OPENAI,
        base_url="https://example.com/v1",
        remote=True,
    )
    response = AdapterResponse(
        provider="openai-like",
        contract=ApiContract.OPENAI,
        status_code=200,
        latency_ms=12.3456,
        text="agentblaster-ok",
        raw={
            "choices": [{"message": {"content": "agentblaster-ok"}}],
            "headers": {"Authorization": "Bearer abcdefghijklmnopqrstuvwxyz"},
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        },
    )

    result = SmokeRunner(
        provider,
        adapter=FakeAdapter(response),  # type: ignore[arg-type]
        output_dir=tmp_path,
        raw_trace_mode=RawTraceMode.REDACTED,
    ).run(model="qwen-test")

    run_dir = tmp_path / result.run_id
    assert result.ok is True
    assert result.input_tokens == 5
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "results.jsonl").exists()
    assert result.raw_response_path == "raw/protocol-smoke-chat.response.json"

    raw_payload = json.loads((run_dir / result.raw_response_path).read_text())
    assert raw_payload["headers"]["Authorization"] == "[REDACTED]"


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
    assert result.tokens_per_second_decode == 100.0


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
    ).run(model="qwen-test")

    assert summary.total_cases == 1
    assert summary.passed == 1
    assert summary.concurrency == 2
    assert (tmp_path / summary.run_id / "summary.json").exists()


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
