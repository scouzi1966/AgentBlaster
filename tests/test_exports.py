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
        suite="smoke",
        provider="local",
        contract=ApiContract.OPENAI,
        model="qwen-test",
        ok=True,
        latency_ms=10.0,
        input_tokens=2,
        output_tokens=1,
        total_tokens=3,
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
    assert rows[0]["ok"] == "True"
