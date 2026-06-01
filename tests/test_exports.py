from __future__ import annotations

import csv
import json
import sys
import types

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
        cancel_after_ms=150,
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
        stats_profile="afm-mlx-openai-compatible",
        telemetry_quality={"tokens_per_second_decode": "native"},
        telemetry_comparison_readiness={
            "schema_version": "agentblaster.telemetry-comparison-readiness.v1",
            "publication_grade_fields": ["tokens_per_second_decode"],
        },
        telemetry_stats_comparability={
            "schema_version": "agentblaster.response-stats-comparability.v1",
            "profile": "afm-mlx-openai-compatible",
            "requires_labeling": False,
        },
        tool_calls_requested=1,
        tool_calls_emitted=1,
        tool_calls_valid=1,
        invalid_tool_call_count=0,
        tool_parser_repair_valid=True,
        tool_loop_enabled=True,
        tool_loop_rounds=2,
        tool_loop_tool_call_count=1,
        tool_loop_max_tool_calls=2,
        tool_loop_stop_reason="final_response",
        structured_output_valid=True,
        judge_verdict_valid=True,
        finish_reason="stop",
        canceled=True,
        cancellation_latency_ms=155.5,
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
    assert rows[0]["cancel_after_ms"] == "150"
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
    assert rows[0]["invalid_tool_call_count"] == "0"
    assert rows[0]["tool_parser_repair_valid"] == "True"
    assert rows[0]["tool_loop_enabled"] == "True"
    assert rows[0]["tool_loop_rounds"] == "2"
    assert rows[0]["tool_loop_tool_call_count"] == "1"
    assert rows[0]["tool_loop_max_tool_calls"] == "2"
    assert rows[0]["tool_loop_stop_reason"] == "final_response"
    assert rows[0]["structured_output_valid"] == "True"
    assert rows[0]["judge_verdict_valid"] == "True"
    assert rows[0]["finish_reason"] == "stop"
    assert rows[0]["stats_profile"] == "afm-mlx-openai-compatible"
    assert json.loads(rows[0]["telemetry_quality"])["tokens_per_second_decode"] == "native"
    assert json.loads(rows[0]["telemetry_comparison_readiness"])["publication_grade_fields"] == [
        "tokens_per_second_decode"
    ]
    assert json.loads(rows[0]["telemetry_stats_comparability"])["profile"] == "afm-mlx-openai-compatible"
    assert rows[0]["canceled"] == "True"
    assert rows[0]["cancellation_latency_ms"] == "155.5"


def test_export_results_writes_parquet_with_optional_pyarrow(monkeypatch, tmp_path) -> None:
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
        suite="smoke",
        provider="local",
        contract=ApiContract.OPENAI,
        model="qwen-test",
        ok=True,
        message="ok",
    )
    captured = {}

    class FakeTable:
        @classmethod
        def from_pylist(cls, rows, metadata=None):
            captured["rows"] = rows
            captured["metadata"] = metadata
            return {"rows": rows, "metadata": metadata}

    def write_table(table, target):
        captured["table"] = table
        target.write_bytes(b"PAR1\n")

    pyarrow = types.ModuleType("pyarrow")
    pyarrow.__path__ = []
    pyarrow.Table = FakeTable
    parquet = types.ModuleType("pyarrow.parquet")
    parquet.write_table = write_table
    pyarrow.parquet = parquet
    monkeypatch.setitem(sys.modules, "pyarrow", pyarrow)
    monkeypatch.setitem(sys.modules, "pyarrow.parquet", parquet)

    (run_dir / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    (run_dir / "results.jsonl").write_text(result.model_dump_json() + "\n", encoding="utf-8")

    generated = export_results(run_dir, ["parquet"])

    parquet_path = run_dir / "exports" / "results.parquet"
    assert generated == [parquet_path]
    assert parquet_path.read_bytes() == b"PAR1\n"
    assert captured["rows"][0]["case_id"] == "case-one"
    assert captured["rows"][0]["case_tags"] == '["prefill", "cache"]'
    assert captured["metadata"] == {b"agentblaster.schema": b"normalized-results-export-v1"}
