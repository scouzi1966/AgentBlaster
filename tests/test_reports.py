from __future__ import annotations

import json

from agentblaster.models import ApiContract, BenchmarkResult, ModelMetadata, RawTraceMode, RunManifest
from agentblaster.reports import generate_matrix_reports, generate_matrix_scorecard_reports, generate_reports, summarize_run


def test_generate_reports_writes_html_markdown_and_json(tmp_path) -> None:
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
        provider_metadata={
            "base_url": "http://127.0.0.1:9999/v1",
            "base_url_host": "127.0.0.1",
            "remote": False,
            "adapter_name": "openai-chat-completions",
            "adapter_version": "agentblaster-adapter-v1",
            "capabilities": {"streaming": True},
        },
        model_metadata=ModelMetadata(
            revision="rev-1",
            architecture="qwen3-dense",
            quantization="mlx-f16",
            context_length=32768,
        ),
    )
    result = BenchmarkResult(
        run_id="run_test",
        case_id="case-one",
        case_title="Case one",
        scenario="prefill",
        case_tags=["prefill", "cache"],
        case_provenance="internal_regression",
        case_risk_level="medium",
        suite="smoke",
        provider="local",
        contract=ApiContract.OPENAI,
        model="qwen-test",
        ok=True,
        request_started_at="2026-05-31T00:00:00+00:00",
        request_completed_at="2026-05-31T00:00:02+00:00",
        queue_ms=3.0,
        rate_limit_wait_ms=2.0,
        latency_ms=10.0,
        ttft_ms=200.0,
        input_tokens=4,
        cached_input_tokens=2,
        cache_hit_ratio=0.5,
        output_tokens=2,
        total_cost_usd=0.000111,
        tokens_per_second_decode=25.0,
        tool_calls_requested=1,
        tool_calls_emitted=1,
        tool_calls_valid=1,
        structured_output_valid=True,
        finish_reason="stop",
        message="ok",
    )
    (run_dir / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    (run_dir / "results.jsonl").write_text(result.model_dump_json() + "\n", encoding="utf-8")

    generated = generate_reports(run_dir, ["html", "md", "json", "publication", "card"])

    assert run_dir / "report.html" in generated
    assert run_dir / "report.md" in generated
    assert run_dir / "summary.json" in generated
    assert run_dir / "publication.json" in generated
    assert run_dir / "report-card.svg" in generated
    report_html = (run_dir / "report.html").read_text(encoding="utf-8")
    assert "AgentBlaster Benchmark Report" in report_html
    assert "qwen3-dense" in report_html
    assert "mlx-f16" in report_html
    assert "TTFT ms" in report_html
    assert "classification=internal" in report_html
    assert "Queue ms" in report_html
    assert "Rate-limit ms" in report_html
    assert "Requests/sec" in report_html
    assert "Cache hit" in report_html
    assert "Finish" in report_html
    assert "openai-chat-completions" in report_html
    assert "200.0" in report_html
    report_md = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "# AgentBlaster Benchmark Report" in report_md
    assert "architecture=qwen3-dense" in report_md
    assert "quantization=mlx-f16" in report_md
    assert "| Provider endpoint | `http://127.0.0.1:9999/v1` |" in report_md
    assert "| Adapter | `openai-chat-completions / agentblaster-adapter-v1 / host=127.0.0.1` |" in report_md
    assert "| Retention | classification=internal |" in report_md
    assert "| Pass rate | 100.0% |" in report_md
    assert "| Duration ms | 2000.0 |" in report_md
    assert "| Requests/sec | 0.5 |" in report_md
    assert "| Average queue ms | 3.0 |" in report_md
    assert "| Average rate-limit wait ms | 2.0 |" in report_md
    assert "| Average cache hit ratio | 0.5 |" in report_md
    assert "| Estimated cost USD | 0.000111 |" in report_md
    assert "| Tool calls emitted | 1 |" in report_md
    assert "| Tool calls valid | 1 |" in report_md
    assert "| `case-one` | prefill | pass | 3.0 | 2.0 | 10.0 | 200.0 | 4 | 2 | 2 | 0.000111 | 1/1 | stop | ok |" in report_md
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["passed"] == 1
    assert summary["concurrency"] == 1
    publication = json.loads((run_dir / "publication.json").read_text(encoding="utf-8"))
    assert publication["report_type"] == "agentblaster-publication-v1"
    assert publication["run"]["provider_metadata"]["adapter_name"] == "openai-chat-completions"
    assert publication["run"]["model_metadata"]["architecture"] == "qwen3-dense"
    assert publication["run"]["retention_policy"]["classification"] == "internal"
    assert publication["scenario_summary"][0]["scenario"] == "prefill"
    assert publication["scenario_summary"][0]["passed"] == 1
    assert publication["scorecard"]["pass_rate_percent"] == 100.0
    assert publication["scorecard"]["avg_latency_ms"] == 10.0
    assert publication["security"]["contains_raw_secrets"] is False
    assert publication["artifact_hints"]["card_svg"] == "report-card.svg"
    card = (run_dir / "report-card.svg").read_text(encoding="utf-8")
    assert "<svg" in card
    assert "AgentBlaster" in card
    assert "PASS RATE" in card
    assert "100.0%" in card
    assert "qwen-test" in card
    assert summarize_run(run_dir).failed == 0


def test_generate_matrix_reports_writes_html_markdown_and_json(tmp_path) -> None:
    summary_path = tmp_path / "qwen-gemma-matrix-summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "matrix_name": "qwen-gemma-local",
                "matrix_path": "examples/matrices/qwen-gemma-local.yaml",
                "description": "Qwen/Gemma local matrix",
                "created_at": "2026-05-31T00:00:00Z",
                "dry_run": False,
                "total_runs": 2,
                "completed_runs": 2,
                "failed_runs": 1,
                "runs": [
                    {
                        "index": 1,
                        "engine": "afm",
                        "provider": "afm",
                        "model": "mlx-community/Qwen3.6-27B",
                        "suite": "trace-replay",
                        "run_id": "run_qwen",
                        "ok": True,
                        "total_cases": 10,
                        "passed": 10,
                        "failed": 0,
                        "concurrency": 2,
                        "results_path": "runs/run_qwen/results.jsonl",
                        "manifest_path": "runs/run_qwen/manifest.json",
                        "summary_path": "runs/run_qwen/summary.json",
                    },
                    {
                        "index": 2,
                        "engine": "lm-studio",
                        "provider": "lm-studio",
                        "model": "google/gemma-4-31b",
                        "suite": "trace-replay",
                        "run_id": "run_gemma",
                        "ok": False,
                        "total_cases": 10,
                        "passed": 8,
                        "failed": 2,
                        "concurrency": 2,
                        "results_path": "runs/run_gemma/results.jsonl",
                        "manifest_path": "runs/run_gemma/manifest.json",
                        "summary_path": "runs/run_gemma/summary.json",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    generated = generate_matrix_reports(summary_path, ["html", "md", "json"])

    assert tmp_path / "qwen-gemma-matrix-summary-matrix-report.html" in generated
    assert tmp_path / "qwen-gemma-matrix-summary-matrix-report.md" in generated
    assert tmp_path / "qwen-gemma-matrix-summary-matrix-report.json" in generated
    html_report = (tmp_path / "qwen-gemma-matrix-summary-matrix-report.html").read_text(encoding="utf-8")
    assert "AgentBlaster Matrix Report" in html_report
    assert "qwen-gemma-local" in html_report
    md_report = (tmp_path / "qwen-gemma-matrix-summary-matrix-report.md").read_text(encoding="utf-8")
    assert "| afm | 1 | 0 | 10 | 10 | 0 | 100.0 |" in md_report
    payload = json.loads((tmp_path / "qwen-gemma-matrix-summary-matrix-report.json").read_text(encoding="utf-8"))
    assert payload["report_type"] == "agentblaster-matrix-report-v1"
    assert payload["scorecard"]["passed_cases"] == 18
    assert payload["scorecard"]["pass_rate_percent"] == 90.0
    assert payload["security"]["contains_raw_secrets"] is False


def test_generate_matrix_reports_include_failed_attempt_errors(tmp_path) -> None:
    summary_path = tmp_path / "partial-matrix-summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "matrix_name": "partial-matrix",
                "matrix_path": "examples/matrices/partial.yaml",
                "description": "Partial matrix",
                "created_at": "2026-05-31T00:00:00Z",
                "continue_on_error": True,
                "total_runs": 1,
                "attempted_runs": 1,
                "completed_runs": 0,
                "failed_runs": 1,
                "runs": [
                    {
                        "index": 1,
                        "engine": "missing-provider",
                        "provider": "missing-provider",
                        "model": "qwen-test",
                        "suite": "smoke",
                        "ok": False,
                        "total_cases": 0,
                        "passed": 0,
                        "failed": 0,
                        "concurrency": 1,
                        "error_type": "ConfigError",
                        "error_message": "provider not configured: missing-provider",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    generated = generate_matrix_reports(summary_path, ["html", "md", "json"])

    assert tmp_path / "partial-matrix-summary-matrix-report.html" in generated
    html_report = (tmp_path / "partial-matrix-summary-matrix-report.html").read_text(encoding="utf-8")
    assert "provider not configured: missing-provider" in html_report
    md_report = (tmp_path / "partial-matrix-summary-matrix-report.md").read_text(encoding="utf-8")
    assert "Attempted runs" in md_report
    payload = json.loads((tmp_path / "partial-matrix-summary-matrix-report.json").read_text(encoding="utf-8"))
    assert payload["matrix"]["continue_on_error"] is True
    assert payload["matrix"]["attempted_runs"] == 1

def test_generate_matrix_scorecard_reports_rank_completed_runs_with_loaded_metrics(tmp_path) -> None:
    run_dir = tmp_path / "runs" / "run_afm"
    run_dir.mkdir(parents=True)
    manifest = RunManifest(
        run_id="run_afm",
        suite="prefill",
        provider="afm",
        contract=ApiContract.OPENAI,
        model="mlx-community/Qwen3.6-27B",
        raw_trace_mode=RawTraceMode.OFF,
        created_at="2026-05-31T00:00:00Z",
        case_count=1,
        model_metadata=ModelMetadata(architecture="qwen3.6-dense", quantization="mlx-f16"),
    )
    result = BenchmarkResult(
        run_id="run_afm",
        case_id="case-one",
        suite="prefill",
        provider="afm",
        contract=ApiContract.OPENAI,
        model="mlx-community/Qwen3.6-27B",
        ok=True,
        latency_ms=10.0,
        ttft_ms=100.0,
        input_tokens=100,
        cached_input_tokens=50,
        cache_hit_ratio=0.5,
        output_tokens=20,
        prompt_eval_ms=200.0,
        decode_ms=400.0,
        tokens_per_second_prefill=500.0,
        tokens_per_second_decode=50.0,
        total_cost_usd=0.0,
        message="ok",
    )
    (run_dir / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    (run_dir / "results.jsonl").write_text(result.model_dump_json() + "\n", encoding="utf-8")
    summary_path = tmp_path / "qwen-gemma-matrix-summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "matrix_name": "qwen-gemma-local",
                "matrix_path": "examples/matrices/qwen-gemma-local.yaml",
                "description": "Qwen/Gemma local matrix",
                "created_at": "2026-05-31T00:00:00Z",
                "total_runs": 2,
                "attempted_runs": 2,
                "completed_runs": 1,
                "failed_runs": 1,
                "runs": [
                    {
                        "index": 1,
                        "engine": "afm",
                        "provider": "afm",
                        "model": "mlx-community/Qwen3.6-27B",
                        "suite": "prefill",
                        "run_id": "run_afm",
                        "ok": True,
                        "total_cases": 1,
                        "passed": 1,
                        "failed": 0,
                        "concurrency": 1,
                        "results_path": "runs/run_afm/results.jsonl",
                        "manifest_path": "runs/run_afm/manifest.json",
                        "summary_path": "runs/run_afm/summary.json",
                    },
                    {
                        "index": 2,
                        "engine": "lm-studio",
                        "provider": "lm-studio",
                        "model": "google/gemma-4-31b",
                        "suite": "prefill",
                        "ok": False,
                        "total_cases": 1,
                        "passed": 0,
                        "failed": 1,
                        "concurrency": 1,
                        "error_type": "ConfigError",
                        "error_message": "provider not configured",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    generated = generate_matrix_scorecard_reports(summary_path, ["html", "md", "json"])

    assert tmp_path / "qwen-gemma-matrix-summary-matrix-scorecard.html" in generated
    assert tmp_path / "qwen-gemma-matrix-summary-matrix-scorecard.md" in generated
    assert tmp_path / "qwen-gemma-matrix-summary-matrix-scorecard.json" in generated
    payload = json.loads((tmp_path / "qwen-gemma-matrix-summary-matrix-scorecard.json").read_text(encoding="utf-8"))
    assert payload["report_type"] == "agentblaster-matrix-scorecard-v1"
    assert payload["scorecard"]["result_artifacts_loaded"] == 1
    assert payload["leaderboard"][0]["engine"] == "afm"
    assert payload["leaderboard"][0]["avg_ttft_ms"] == 100.0
    assert payload["leaderboard"][0]["telemetry_completeness_percent"] is not None
    assert payload["security"]["contains_raw_secrets"] is False
    md_report = (tmp_path / "qwen-gemma-matrix-summary-matrix-scorecard.md").read_text(encoding="utf-8")
    assert "# AgentBlaster Matrix Scorecard" in md_report
    assert "| 1 | afm | afm | mlx-community/Qwen3.6-27B | prefill | pass | 100.0 | 1/1 | 10.0 | 100.0 | 50.0 | 0.5 | 0.0 |" in md_report

