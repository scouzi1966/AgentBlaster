from __future__ import annotations

import json

from agentblaster.compare import (
    compare_runs,
    evaluate_comparison_gate,
    format_comparison_gate_report,
    format_comparison_table,
    write_comparison_gate_json,
    write_comparison_json,
)
from agentblaster.models import ApiContract, BenchmarkResult, RawTraceMode, RunManifest


def make_run(
    run_dir,
    *,
    run_id: str,
    provider: str,
    latency_ms: float | list[float],
    queue_ms: float | None = None,
    rate_limit_wait_ms: float | None = None,
    ttft_ms: float | None = None,
    cache_hit_ratio: float | None = None,
    total_cost_usd: float | None = None,
    prefill_rate: float | None = None,
    decode_rate: float | None = None,
    scenario: str = "smoke",
) -> None:
    latencies = latency_ms if isinstance(latency_ms, list) else [latency_ms]
    run_dir.mkdir()
    manifest = RunManifest(
        run_id=run_id,
        suite="smoke",
        provider=provider,
        contract=ApiContract.OPENAI,
        model="qwen-test",
        raw_trace_mode=RawTraceMode.OFF,
        created_at="2026-05-31T00:00:00Z",
        case_count=len(latencies),
    )
    results = "\n".join(
        BenchmarkResult(
            run_id=run_id,
            case_id=f"case-{index}",
            scenario=scenario,
            suite="smoke",
            provider=provider,
            contract=ApiContract.OPENAI,
            model="qwen-test",
            ok=True,
            queue_ms=queue_ms,
            rate_limit_wait_ms=rate_limit_wait_ms,
            latency_ms=latency,
            ttft_ms=ttft_ms,
            cache_hit_ratio=cache_hit_ratio,
            total_cost_usd=total_cost_usd,
            tokens_per_second_prefill=prefill_rate,
            tokens_per_second_decode=decode_rate,
            message="ok",
        ).model_dump_json()
        for index, latency in enumerate(latencies, start=1)
    )
    (run_dir / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    (run_dir / "results.jsonl").write_text(results + "\n", encoding="utf-8")


def test_compare_runs_summarizes_run_directories(tmp_path) -> None:
    run_a = tmp_path / "run_a"
    run_b = tmp_path / "run_b"
    make_run(
        run_a,
        run_id="run_a",
        provider="afm",
        latency_ms=[10.0, 20.0, 30.0],
        queue_ms=2.0,
        rate_limit_wait_ms=1.0,
        ttft_ms=5.0,
        cache_hit_ratio=0.75,
        total_cost_usd=0.000111,
        prefill_rate=200.0,
        decode_rate=100.0,
        scenario="prefill",
    )
    make_run(run_b, run_id="run_b", provider="ollama", latency_ms=20.0, decode_rate=50.0, scenario="decode")

    rows = compare_runs([run_a, run_b])

    assert rows[0].provider == "afm"
    assert rows[0].pass_rate == 100.0
    assert rows[0].avg_latency_ms == 20.0
    assert rows[0].p50_latency_ms == 20.0
    assert rows[0].p95_latency_ms == 30.0
    assert rows[0].avg_queue_ms == 2.0
    assert rows[0].avg_rate_limit_wait_ms == 1.0
    assert rows[0].avg_ttft_ms == 5.0
    assert rows[0].avg_cache_hit_ratio == 0.75
    assert rows[0].total_cost_usd == 0.000333
    assert rows[0].avg_prefill_tokens_per_second == 200.0
    assert rows[0].scenario_summary[0].scenario == "prefill"
    assert rows[0].scenario_summary[0].avg_latency_ms == 20.0
    assert rows[0].scenario_summary[0].pass_rate == 100.0
    assert rows[1].avg_decode_tokens_per_second == 50.0
    table = format_comparison_table(rows)
    assert "avg_queue_ms" in table
    assert "avg_rate_limit_wait_ms" in table
    assert "avg_ttft_ms" in table
    assert "avg_cache_hit_ratio" in table
    assert "avg_prefill_tok_s" in table
    assert "avg_decode_tok_s" in table
    assert "total_cost_usd" in table
    assert "scenario" in table
    assert "prefill" in table
    assert "decode" in table


def test_write_comparison_json(tmp_path) -> None:
    run_a = tmp_path / "run_a"
    make_run(run_a, run_id="run_a", provider="afm", latency_ms=10.0)
    output = tmp_path / "comparison.json"

    write_comparison_json([run_a], output)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload[0]["run_id"] == "run_a"
    assert "pass_rate" in payload[0]
    assert "p95_latency_ms" in payload[0]
    assert "avg_queue_ms" in payload[0]
    assert "avg_rate_limit_wait_ms" in payload[0]
    assert "avg_cache_hit_ratio" in payload[0]
    assert "total_cost_usd" in payload[0]
    assert payload[0]["scenario_summary"][0]["scenario"] == "smoke"


def test_evaluate_comparison_gate_flags_latency_regression(tmp_path) -> None:
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    make_run(baseline, run_id="baseline", provider="afm", latency_ms=100.0, decode_rate=100.0)
    make_run(candidate, run_id="candidate", provider="afm", latency_ms=130.0, decode_rate=80.0)

    report = evaluate_comparison_gate(
        baseline,
        candidate,
        min_pass_rate=100.0,
        max_avg_latency_regression_pct=20.0,
        min_decode_tokens_per_second_ratio=0.9,
    )

    assert report.ok is False
    assert {finding.metric for finding in report.findings} == {
        "avg_latency_ms",
        "avg_decode_tokens_per_second_ratio",
    }
    text = format_comparison_gate_report(report)
    assert "ok: false" in text
    output = tmp_path / "gate.json"
    write_comparison_gate_json(report, output)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert payload["candidate"]["run_id"] == "candidate"


def test_evaluate_comparison_gate_passes_within_thresholds(tmp_path) -> None:
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    make_run(baseline, run_id="baseline", provider="afm", latency_ms=100.0, decode_rate=100.0)
    make_run(candidate, run_id="candidate", provider="afm", latency_ms=105.0, decode_rate=98.0)

    report = evaluate_comparison_gate(
        baseline,
        candidate,
        min_pass_rate=100.0,
        max_avg_latency_regression_pct=10.0,
        min_decode_tokens_per_second_ratio=0.95,
    )

    assert report.ok is True
    assert report.findings == []
