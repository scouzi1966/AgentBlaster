from __future__ import annotations

import json

from agentblaster.models import ApiContract, BenchmarkResult, RawTraceMode, RunManifest
from agentblaster.reports import generate_reports, summarize_run


def test_generate_reports_writes_html_and_json(tmp_path) -> None:
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
        suite="smoke",
        provider="local",
        contract=ApiContract.OPENAI,
        model="qwen-test",
        ok=True,
        latency_ms=10.0,
        message="ok",
    )
    (run_dir / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    (run_dir / "results.jsonl").write_text(result.model_dump_json() + "\n", encoding="utf-8")

    generated = generate_reports(run_dir, ["html", "json"])

    assert run_dir / "report.html" in generated
    assert run_dir / "summary.json" in generated
    assert "AgentBlaster Benchmark Report" in (run_dir / "report.html").read_text(encoding="utf-8")
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["passed"] == 1
    assert summary["concurrency"] == 1
    assert summarize_run(run_dir).failed == 0
