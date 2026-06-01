from __future__ import annotations

import csv

from agentblaster.exports import export_results
from agentblaster.models import ApiContract, BenchmarkResult, RawTraceMode, RunManifest


def test_export_results_writes_jsonl_and_csv(tmp_path) -> None:
    run_dir = tmp_path / "run_test"
    run_dir.mkdir()
    manifest = RunManifest(
        run_id="run_test",
        suite="smoke",
        provider="local",
        contract=ApiContract.OPENAI,
        model="qwen-test",
        raw_trace_mode=RawTraceMode.OFF,
        created_at="2026-05-31T00:00:00Z",
        case_count=1,
    )
    result = BenchmarkResult(
        run_id="run_test",
        case_id="case-one",
        case_title="Case one",
        scenario="prefill",
        case_tags=["prefill", "cache"],
        case_provenance="internal_regression",
        case_risk_level="medium",
        case_source_url="fixture://case-one",
        case_license="MIT",
        suite="smoke",
        provider="local",
        contract=ApiContract.OPENAI,
        model="qwen-test",
        ok=True,
        provider_endpoint_host="127.0.0.1",
        provider_remote=False,
        adapter_name="openai-chat-completions",
        adapter_version="agentblaster-adapter-v1",
        request_started_at="2026-05-31T00:00:00Z",
        request_completed_at="2026-05-31T00:00:01Z",
        queue_ms=3.0,
        rate_limit_wait_ms=2.0,
        latency_ms=10.0,
        ttft_ms=200.0,
        input_tokens=2,
        output_tokens=1,
        total_tokens=3,
        cached_input_tokens=1,
        cache_write_tokens=0,
        cache_hit_ratio=0.5,
        input_cost_usd=0.000002,
        output_cost_usd=0.000008,
        cache_read_cost_usd=0.000001,
        cache_write_cost_usd=0.0,
        request_cost_usd=0.0001,
        total_cost_usd=0.000111,
        load_ms=25.0,
        tokens_per_second_decode=100.0,
        tool_calls_requested=1,
        tool_calls_emitted=1,
        tool_calls_valid=1,
        structured_output_valid=True,
        finish_reason="stop",
        message="ok",
    )
    (run_dir / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    (run_dir / "results.jsonl").write_text(result.model_dump_json() + "\n", encoding="utf-8")

    generated = export_results(run_dir, ["jsonl", "csv"])

    jsonl_path = run_dir / "exports" / "results.jsonl"
    csv_path = run_dir / "exports" / "results.csv"
    assert jsonl_path in generated
    assert csv_path in generated
    assert jsonl_path.read_text(encoding="utf-8").strip()
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["case_id"] == "case-one"
    assert rows[0]["case_title"] == "Case one"
    assert rows[0]["scenario"] == "prefill"
    assert rows[0]["case_tags"] == '["prefill", "cache"]'
    assert rows[0]["case_provenance"] == "internal_regression"
    assert rows[0]["case_risk_level"] == "medium"
    assert rows[0]["case_source_url"] == "fixture://case-one"
    assert rows[0]["case_license"] == "MIT"
    assert rows[0]["ok"] == "True"
    assert rows[0]["provider_endpoint_host"] == "127.0.0.1"
    assert rows[0]["provider_remote"] == "False"
    assert rows[0]["adapter_name"] == "openai-chat-completions"
    assert rows[0]["adapter_version"] == "agentblaster-adapter-v1"
    assert rows[0]["request_started_at"] == "2026-05-31T00:00:00Z"
    assert rows[0]["request_completed_at"] == "2026-05-31T00:00:01Z"
    assert rows[0]["queue_ms"] == "3.0"
    assert rows[0]["rate_limit_wait_ms"] == "2.0"
    assert rows[0]["ttft_ms"] == "200.0"
    assert rows[0]["cached_input_tokens"] == "1"
    assert rows[0]["cache_write_tokens"] == "0"
    assert rows[0]["cache_hit_ratio"] == "0.5"
    assert rows[0]["input_cost_usd"] == "2e-06"
    assert rows[0]["output_cost_usd"] == "8e-06"
    assert rows[0]["cache_read_cost_usd"] == "1e-06"
    assert rows[0]["cache_write_cost_usd"] == "0.0"
    assert rows[0]["request_cost_usd"] == "0.0001"
    assert rows[0]["total_cost_usd"] == "0.000111"
    assert rows[0]["load_ms"] == "25.0"
    assert rows[0]["tokens_per_second_decode"] == "100.0"
    assert rows[0]["tool_calls_requested"] == "1"
    assert rows[0]["tool_calls_emitted"] == "1"
    assert rows[0]["tool_calls_valid"] == "1"
    assert rows[0]["structured_output_valid"] == "True"
    assert rows[0]["finish_reason"] == "stop"
