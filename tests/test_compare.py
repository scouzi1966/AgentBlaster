from __future__ import annotations

import json

from agentblaster.compare import compare_runs, format_comparison_table, write_comparison_json
from agentblaster.models import ApiContract, BenchmarkResult, RawTraceMode, RunManifest


def make_run(run_dir, *, run_id: str, provider: str, latency_ms: float, decode_rate: float | None = None) -> None:
    run_dir.mkdir()
    manifest = RunManifest(
        run_id=run_id,
        suite="smoke",
        provider=provider,
        contract=ApiContract.OPENAI,
        model="qwen-test",
        raw_trace_mode=RawTraceMode.OFF,
        created_at="2026-05-31T00:00:00Z",
        case_count=1,
    )
    result = BenchmarkResult(
        run_id=run_id,
        case_id="case-one",
        suite="smoke",
        provider=provider,
        contract=ApiContract.OPENAI,
        model="qwen-test",
        ok=True,
        latency_ms=latency_ms,
        tokens_per_second_decode=decode_rate,
        message="ok",
    )
    (run_dir / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    (run_dir / "results.jsonl").write_text(result.model_dump_json() + "\n", encoding="utf-8")


def test_compare_runs_summarizes_run_directories(tmp_path) -> None:
    run_a = tmp_path / "run_a"
    run_b = tmp_path / "run_b"
    make_run(run_a, run_id="run_a", provider="afm", latency_ms=10.0, decode_rate=100.0)
    make_run(run_b, run_id="run_b", provider="ollama", latency_ms=20.0, decode_rate=50.0)

    rows = compare_runs([run_a, run_b])

    assert rows[0].provider == "afm"
    assert rows[0].avg_latency_ms == 10.0
    assert rows[1].avg_decode_tokens_per_second == 50.0
    assert "avg_decode_tok_s" in format_comparison_table(rows)


def test_write_comparison_json(tmp_path) -> None:
    run_a = tmp_path / "run_a"
    make_run(run_a, run_id="run_a", provider="afm", latency_ms=10.0)
    output = tmp_path / "comparison.json"

    write_comparison_json([run_a], output)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload[0]["run_id"] == "run_a"
