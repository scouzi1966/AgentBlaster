from __future__ import annotations

import json
import sys
import types

from agentblaster.models import ApiContract, BenchmarkResult, ModelMetadata, RawTraceMode, RunManifest
from agentblaster.reports import generate_matrix_reports, generate_matrix_scorecard_reports, generate_reports, summarize_run


def _install_fake_cairosvg(monkeypatch) -> None:
    cairosvg = types.ModuleType("cairosvg")

    def svg2png(*, url, write_to, output_width=None, output_height=None):
        assert url
        assert output_width == 1200
        assert output_height == 630
        with open(write_to, "wb") as handle:
            handle.write(b"\x89PNG\r\n\x1a\nagentblaster")

    cairosvg.svg2png = svg2png
    monkeypatch.setitem(sys.modules, "cairosvg", cairosvg)


def test_generate_reports_writes_html_markdown_json_and_media_cards(monkeypatch, tmp_path) -> None:
    _install_fake_cairosvg(monkeypatch)
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
        engine_target={
            "id": "afm-mlx",
            "display_name": "AFM MLX",
            "standardization": {"primary_scoring_contract": "openai"},
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
        cancel_after_ms=150,
        canceled=True,
        cancellation_latency_ms=155.5,
        message="ok",
    )
    (run_dir / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    (run_dir / "results.jsonl").write_text(result.model_dump_json() + "\n", encoding="utf-8")

    generated = generate_reports(run_dir, ["html", "md", "json", "publication", "card", "pdf", "png"])

    assert run_dir / "report.html" in generated
    assert run_dir / "report.md" in generated
    assert run_dir / "summary.json" in generated
    assert run_dir / "publication.json" in generated
    assert run_dir / "report-card.svg" in generated
    assert run_dir / "report.pdf" in generated
    assert run_dir / "report-card.png" in generated
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
    assert "Failure classes" in report_html
    assert "Judge verdicts" in report_html
    assert "Finish" in report_html
    assert "openai-chat-completions" in report_html
    assert "200.0" in report_html
    report_md = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "# AgentBlaster Benchmark Report" in report_md
    assert "architecture=qwen3-dense" in report_md
    assert "quantization=mlx-f16" in report_md
    assert "| Provider endpoint | `http://127.0.0.1:9999/v1` |" in report_md
    assert "| Engine target | `afm-mlx / AFM MLX / primary=openai` |" in report_md
    assert "| Adapter | `openai-chat-completions / agentblaster-adapter-v1 / host=127.0.0.1` |" in report_md
    assert "| Retention | classification=internal |" in report_md
    assert "| Pass rate | 100.0% |" in report_md
    assert "| Duration ms | 2000.0 |" in report_md
    assert "| Requests/sec | 0.5 |" in report_md
    assert "| Average queue ms | 3.0 |" in report_md
    assert "| Average rate-limit wait ms | 2.0 |" in report_md
    assert "| Average cache hit ratio | 0.5 |" in report_md
    assert "| Failure classes | none |" in report_md
    assert "| Estimated cost USD | 0.000111 |" in report_md
    assert "| Tool calls emitted | 1 |" in report_md
    assert "| Tool calls valid | 1 |" in report_md
    assert "| Invalid tool calls | 0 |" in report_md
    assert "| Tool-parser repair valid | 1/1 |" in report_md
    assert "| Judge rubric cases | 1 |" in report_md
    assert "| Judge verdicts valid | 1 |" in report_md
    assert "| Judge verdict valid rate | 100.0% |" in report_md
    assert "| `case-one` | prefill | pass | 3.0 | 2.0 | 10.0 | 200.0 | 4 | 2 | 2 | 0.000111 | 1/1 | True | stop | ok |" in report_md
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["passed"] == 1
    assert summary["concurrency"] == 1
    publication = json.loads((run_dir / "publication.json").read_text(encoding="utf-8"))
    assert publication["report_type"] == "agentblaster-publication-v1"
    assert publication["run"]["provider_metadata"]["adapter_name"] == "openai-chat-completions"
    assert publication["run"]["engine_target"]["id"] == "afm-mlx"
    assert publication["run"]["model_metadata"]["architecture"] == "qwen3-dense"
    assert publication["run"]["retention_policy"]["classification"] == "internal"
    assert publication["scenario_summary"][0]["scenario"] == "prefill"
    assert publication["scenario_summary"][0]["passed"] == 1
    assert publication["scorecard"]["pass_rate_percent"] == 100.0
    assert publication["scorecard"]["avg_latency_ms"] == 10.0
    assert publication["scorecard"]["failure_class_summary"] == []
    assert publication["scorecard"]["tool_loop_cases"] == 1
    assert publication["scorecard"]["invalid_tool_call_count"] == 0
    assert publication["scorecard"]["tool_parser_repair_cases"] == 1
    assert publication["scorecard"]["tool_parser_repairs_valid"] == 1
    assert publication["scorecard"]["tool_loop_rounds"] == 2
    assert publication["scorecard"]["tool_loop_tool_call_count"] == 1
    assert publication["scorecard"]["judge_rubric_cases"] == 1
    assert publication["scorecard"]["judge_verdicts_valid"] == 1
    assert publication["scorecard"]["judge_verdict_valid_rate_percent"] == 100.0
    assert publication["scorecard"]["tool_loop_stop_summary"] == [{"stop_reason": "final_response", "count": 1}]
    assert {"label": "Judge verdicts", "value": "1/1 valid"} in publication["highlights"]
    assert publication["scorecard"]["cancellation_cases"] == 1
    assert publication["scorecard"]["cancellations_observed"] == 1
    assert publication["scorecard"]["avg_cancellation_latency_ms"] == 155.5
    assert publication["publication_readiness"]["schema_version"] == "agentblaster.publication-readiness.v1"
    assert publication["publication_readiness"]["status"] == "review-required"
    assert publication["publication_readiness"]["ready_for_internal_review"] is True
    assert publication["publication_readiness"]["ready_for_external_publication"] is False
    assert publication["publication_readiness"]["warning_count"] == 2
    warning_codes = {item["code"] for item in publication["publication_readiness"]["warnings"]}
    assert warning_codes == {"non_public_classification", "missing_publication_artifacts"}
    artifact_requirements = {
        item["artifact"]: item["present"]
        for item in publication["publication_readiness"]["artifact_requirements"]
    }
    assert artifact_requirements["summary.json"] is True
    assert artifact_requirements["report.html"] is True
    assert artifact_requirements["report.pdf"] is True
    assert artifact_requirements["report-card.svg"] is True
    assert artifact_requirements["integrity.json"] is False
    assert publication["security"]["contains_raw_secrets"] is False
    assert publication["artifact_hints"]["pdf"] == "report.pdf"
    assert publication["artifact_hints"]["card_svg"] == "report-card.svg"
    assert publication["artifact_hints"]["card_png"] == "report-card.png"
    card = (run_dir / "report-card.svg").read_text(encoding="utf-8")
    assert "<svg" in card
    assert "AgentBlaster" in card
    assert "PASS RATE" in card
    assert "100.0%" in card
    assert "qwen-test" in card
    pdf = (run_dir / "report.pdf").read_bytes()
    assert pdf.startswith(b"%PDF-1.4")
    assert b"AgentBlaster Benchmark Report" in pdf
    assert (run_dir / "report-card.png").read_bytes().startswith(b"\x89PNG")
    assert summarize_run(run_dir).failed == 0


def test_generate_reports_include_failure_class_summary(tmp_path) -> None:
    run_dir = tmp_path / "run_failure"
    run_dir.mkdir()
    manifest = RunManifest(
        run_id="run_failure",
        suite="toolcall",
        provider="local",
        contract=ApiContract.OPENAI,
        model="qwen-test",
        raw_trace_mode=RawTraceMode.OFF,
        created_at="2026-05-31T00:00:00Z",
        case_count=1,
    )
    result = BenchmarkResult(
        run_id="run_failure",
        case_id="tool-case",
        case_title="Tool case",
        scenario="tool parser strictness",
        case_tags=["toolcall"],
        suite="toolcall",
        provider="local",
        contract=ApiContract.OPENAI,
        model="qwen-test",
        ok=False,
        failure_class="engine_protocol_bug",
        message="invalid tool-call envelope",
    )
    (run_dir / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    (run_dir / "results.jsonl").write_text(result.model_dump_json() + "\n", encoding="utf-8")

    generate_reports(run_dir, ["html", "md", "publication"])

    publication = json.loads((run_dir / "publication.json").read_text(encoding="utf-8"))
    assert publication["scorecard"]["failure_class_summary"] == [
        {"failure_class": "engine_protocol_bug", "count": 1}
    ]
    report_md = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "| Failure classes | engine_protocol_bug=1 |" in report_md
    report_html = (run_dir / "report.html").read_text(encoding="utf-8")
    assert "engine_protocol_bug=1" in report_html


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
                        "engine_target": {
                            "id": "afm-mlx",
                            "display_name": "AFM MLX",
                            "standardization": {"primary_scoring_contract": "openai"},
                        },
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
                        "engine_target": {
                            "id": "lm-studio",
                            "display_name": "LM Studio",
                            "standardization": {"primary_scoring_contract": "openai"},
                        },
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

    generated = generate_matrix_reports(summary_path, ["html", "md", "json", "pdf"])

    assert tmp_path / "qwen-gemma-matrix-summary-matrix-report.html" in generated
    assert tmp_path / "qwen-gemma-matrix-summary-matrix-report.md" in generated
    assert tmp_path / "qwen-gemma-matrix-summary-matrix-report.json" in generated
    assert tmp_path / "qwen-gemma-matrix-summary-matrix-report.pdf" in generated
    html_report = (tmp_path / "qwen-gemma-matrix-summary-matrix-report.html").read_text(encoding="utf-8")
    assert "AgentBlaster Matrix Report" in html_report
    assert "qwen-gemma-local" in html_report
    md_report = (tmp_path / "qwen-gemma-matrix-summary-matrix-report.md").read_text(encoding="utf-8")
    assert "| 1 | afm | afm-mlx | afm | mlx-community/Qwen3.6-27B | trace-replay | `run_qwen` | 10/10 | pass | `runs/run_qwen/summary.json` |" in md_report
    assert "| afm | 1 | 0 | 10 | 10 | 0 | 100.0 |" in md_report
    payload = json.loads((tmp_path / "qwen-gemma-matrix-summary-matrix-report.json").read_text(encoding="utf-8"))
    assert payload["report_type"] == "agentblaster-matrix-report-v1"
    assert payload["scorecard"]["passed_cases"] == 18
    assert payload["scorecard"]["pass_rate_percent"] == 90.0
    assert payload["scorecard"]["engine_targets"] == [
        {"display_name": "AFM MLX", "id": "afm-mlx", "primary_scoring_contract": "openai"},
        {"display_name": "LM Studio", "id": "lm-studio", "primary_scoring_contract": "openai"},
    ]
    assert payload["security"]["contains_raw_secrets"] is False
    pdf_report = (tmp_path / "qwen-gemma-matrix-summary-matrix-report.pdf").read_bytes()
    assert pdf_report.startswith(b"%PDF-1.4")
    assert b"AgentBlaster Matrix Report" in pdf_report


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

def test_generate_matrix_scorecard_reports_rank_completed_runs_with_loaded_metrics(monkeypatch, tmp_path) -> None:
    _install_fake_cairosvg(monkeypatch)
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
        scenario="agent fan-out",
        case_tags=["fanout", "concurrency"],
        provider="afm",
        contract=ApiContract.OPENAI,
        model="mlx-community/Qwen3.6-27B",
        ok=True,
        queue_ms=3.0,
        rate_limit_wait_ms=2.0,
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
        tool_calls_emitted=1,
        tool_calls_valid=1,
        invalid_tool_call_count=0,
        tool_parser_repair_valid=True,
        judge_verdict_valid=True,
        cancel_after_ms=100,
        canceled=True,
        cancellation_latency_ms=110.0,
        stats_profile="afm-mlx-openai-compatible",
        telemetry_quality={
            "latency_ms": "measured",
            "tokens_per_second_decode": "native",
            "cache_hit_ratio": "inferred",
        },
        telemetry_comparison_readiness={
            "guidance": "label-inferred-or-conditional-fields-before-cross-engine-comparison",
            "advisory_fields": ["cache_hit_ratio"],
        },
        telemetry_stats_comparability={
            "schema_version": "agentblaster.response-stats-comparability.v1",
            "profile": "afm-mlx-openai-compatible",
            "requires_labeling": True,
            "guidance": "publish-native-and-measured-fields-separately-from-inferred-conditional-or-missing-stats",
        },
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
                        "engine_target": {
                            "id": "afm-mlx",
                            "display_name": "AFM MLX",
                            "standardization": {"primary_scoring_contract": "openai"},
                        },
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

    generated = generate_matrix_scorecard_reports(summary_path, ["html", "md", "json", "card", "pdf", "png"])

    assert tmp_path / "qwen-gemma-matrix-summary-matrix-scorecard.html" in generated
    assert tmp_path / "qwen-gemma-matrix-summary-matrix-scorecard.md" in generated
    assert tmp_path / "qwen-gemma-matrix-summary-matrix-scorecard.json" in generated
    assert tmp_path / "qwen-gemma-matrix-summary-matrix-scorecard.svg" in generated
    assert tmp_path / "qwen-gemma-matrix-summary-matrix-scorecard.pdf" in generated
    assert tmp_path / "qwen-gemma-matrix-summary-matrix-scorecard.png" in generated
    payload = json.loads((tmp_path / "qwen-gemma-matrix-summary-matrix-scorecard.json").read_text(encoding="utf-8"))
    assert payload["report_type"] == "agentblaster-matrix-scorecard-v1"
    assert payload["scorecard"]["result_artifacts_loaded"] == 1
    assert payload["leaderboard"][0]["engine"] == "afm"
    assert payload["leaderboard"][0]["model_architecture"] == "qwen3.6-dense"
    assert payload["leaderboard"][0]["quantization"] == "mlx-f16"
    assert payload["leaderboard"][0]["avg_ttft_ms"] == 100.0
    assert payload["leaderboard"][0]["avg_queue_ms"] == 3.0
    assert payload["leaderboard"][0]["avg_rate_limit_wait_ms"] == 2.0
    assert payload["leaderboard"][0]["fanout_cases"] == 1
    assert payload["leaderboard"][0]["scenarios"] == ["agent fan-out"]
    assert payload["leaderboard"][0]["cancellation_cases"] == 1
    assert payload["leaderboard"][0]["cancellations_observed"] == 1
    assert payload["leaderboard"][0]["avg_cancellation_latency_ms"] == 110.0
    assert payload["leaderboard"][0]["judge_rubric_cases"] == 1
    assert payload["leaderboard"][0]["judge_verdicts_valid"] == 1
    assert payload["leaderboard"][0]["judge_verdict_valid_rate_percent"] == 100.0
    assert payload["leaderboard"][0]["invalid_tool_call_count"] == 0
    assert payload["leaderboard"][0]["tool_parser_repair_cases"] == 1
    assert payload["leaderboard"][0]["tool_parser_repairs_valid"] == 1
    assert payload["leaderboard"][0]["telemetry_quality_counts"]["measured"] == 1
    assert payload["leaderboard"][0]["telemetry_quality_counts"]["native"] == 1
    assert payload["leaderboard"][0]["telemetry_quality_counts"]["inferred"] == 1
    assert payload["leaderboard"][0]["telemetry_comparison_guidance"][
        "label-inferred-or-conditional-fields-before-cross-engine-comparison"
    ] == 1
    assert payload["leaderboard"][0]["stats_profiles"]["afm-mlx-openai-compatible"] == 1
    assert payload["leaderboard"][0]["stats_comparability_requires_labeling"] == 1
    assert payload["leaderboard"][0]["stats_comparability_guidance"][
        "publish-native-and-measured-fields-separately-from-inferred-conditional-or-missing-stats"
    ] == 1
    assert payload["scorecard"]["judge_rubric_cases"] == 1
    assert payload["scorecard"]["judge_verdicts_valid"] == 1
    assert payload["scorecard"]["judge_verdict_valid_rate_percent"] == 100.0
    assert payload["scorecard"]["invalid_tool_call_count"] == 0
    assert payload["scorecard"]["tool_parser_repair_cases"] == 1
    assert payload["scorecard"]["tool_parser_repairs_valid"] == 1
    assert payload["scorecard"]["tool_parser_repair_valid_rate_percent"] == 100.0
    assert payload["scorecard"]["telemetry_quality_summary"]["quality_counts"]["measured"] == 1
    assert payload["scorecard"]["telemetry_quality_summary"]["quality_counts"]["native"] == 1
    assert payload["scorecard"]["telemetry_quality_summary"]["quality_counts"]["inferred"] == 1
    assert payload["scorecard"]["telemetry_quality_summary"]["entries_with_advisory_quality"] == 1
    assert payload["scorecard"]["telemetry_quality_summary"]["entries_with_comparison_guidance"] == 1
    assert payload["scorecard"]["stats_comparability_summary"]["schema_version"] == (
        "agentblaster.scorecard-stats-comparability.v1"
    )
    assert payload["scorecard"]["stats_comparability_summary"]["profile_counts"]["afm-mlx-openai-compatible"] == 1
    assert payload["scorecard"]["stats_comparability_summary"]["entries_requiring_labeling"] == 1
    assert payload["scorecard"]["concurrency_evidence"]["schema_version"] == (
        "agentblaster.scorecard-concurrency-evidence.v1"
    )
    assert payload["scorecard"]["concurrency_evidence"]["max_concurrency"] == 1
    assert payload["scorecard"]["concurrency_evidence"]["max_avg_queue_ms"] == 3.0
    assert payload["scorecard"]["concurrency_evidence"]["max_avg_rate_limit_wait_ms"] == 2.0
    assert payload["scorecard"]["concurrency_evidence"]["guidance"] == "single-concurrency-level-advisory-only"
    assert payload["scorecard"]["concurrency_evidence"]["highest_queue_wait_entries"][0]["engine"] == "afm"
    assert "canceled" in payload["leaderboard"][0]["telemetry_fields_available"]
    assert "cancellation_latency_ms" in payload["leaderboard"][0]["telemetry_fields_available"]
    assert payload["leaderboard"][0]["telemetry_completeness_percent"] is not None
    assert payload["architecture_summary"][0]["model_architecture"] == "qwen3.6-dense"
    assert payload["architecture_summary"][0]["passed"] == 1
    assert payload["architecture_summary"][0]["avg_decode_tokens_per_second"] == 50.0
    assert payload["architecture_summary"][0]["judge_rubric_cases"] == 1
    assert payload["architecture_summary"][0]["judge_verdicts_valid"] == 1
    assert payload["architecture_summary"][0]["invalid_tool_call_count"] == 0
    assert payload["architecture_summary"][0]["tool_parser_repair_cases"] == 1
    assert payload["architecture_summary"][0]["tool_parser_repairs_valid"] == 1
    assert payload["architecture_summary"][0]["tool_parser_repair_valid_rate_percent"] == 100.0
    assert payload["quantization_summary"][0]["quantization"] == "mlx-f16"
    assert payload["quantization_summary"][0]["tool_parser_repair_cases"] == 1
    assert payload["security"]["contains_raw_secrets"] is False
    md_report = (tmp_path / "qwen-gemma-matrix-summary-matrix-scorecard.md").read_text(encoding="utf-8")
    assert "# AgentBlaster Matrix Scorecard" in md_report
    assert "Architecture Summary" in md_report
    assert "| qwen3.6-dense | 1 | 0 | 1 | 1 | 0 | 100.0 | 10.0 | 100.0 | 50.0 | 0.5 |" in md_report
    assert "Quantization Summary" in md_report
    assert "Queue ms" in md_report
    assert "Rate-limit ms" in md_report
    assert "Telemetry quality" in md_report
    assert "Concurrency evidence" in md_report
    assert "Judge verdicts valid" in md_report
    assert "Tool-parser repair valid" in md_report
    assert "Cancel" in md_report
    assert "| 1 | afm | afm | mlx-community/Qwen3.6-27B | prefill | pass | 100.0 | 1/1 | 3.0 | 2.0 | 10.0 | 100.0 | 50.0 | 0.5 | 1/1 | 1/1 | 0.0 |" in md_report
    svg_card = (tmp_path / "qwen-gemma-matrix-summary-matrix-scorecard.svg").read_text(encoding="utf-8")
    assert "<svg" in svg_card
    assert "MATRIX SCORECARD" in svg_card
    assert "qwen3.6-dense" in svg_card
    assert "Parser repair: 1/1" in svg_card
    assert "Telemetry:" in svg_card
    assert "Concurrency:" in svg_card
    assert "No raw traces" in svg_card
    pdf_scorecard = (tmp_path / "qwen-gemma-matrix-summary-matrix-scorecard.pdf").read_bytes()
    assert pdf_scorecard.startswith(b"%PDF-1.4")
    assert b"AgentBlaster Matrix Scorecard" in pdf_scorecard
    assert (tmp_path / "qwen-gemma-matrix-summary-matrix-scorecard.png").read_bytes().startswith(b"\x89PNG")


def test_generate_matrix_scorecard_reports_include_failure_class_summary(tmp_path) -> None:
    run_dir = tmp_path / "runs" / "run_failure"
    run_dir.mkdir(parents=True)
    result = BenchmarkResult(
        run_id="run_failure",
        case_id="tool-case",
        case_title="Tool case",
        scenario="tool parser strictness",
        case_tags=["toolcall"],
        suite="toolcall",
        provider="afm",
        contract=ApiContract.OPENAI,
        model="qwen-test",
        ok=False,
        failure_class="engine_protocol_bug",
        message="invalid tool-call envelope",
    )
    (run_dir / "results.jsonl").write_text(result.model_dump_json() + "\n", encoding="utf-8")
    summary_path = tmp_path / "failure-matrix-summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "matrix_name": "failure-matrix",
                "matrix_path": "examples/matrices/failure.yaml",
                "description": "Failure matrix",
                "created_at": "2026-05-31T00:00:00Z",
                "dry_run": False,
                "total_runs": 1,
                "completed_runs": 1,
                "failed_runs": 0,
                "runs": [
                    {
                        "index": 1,
                        "engine": "afm",
                        "provider": "afm",
                        "model": "qwen-test",
                        "suite": "toolcall",
                        "run_id": "run_failure",
                        "ok": True,
                        "total_cases": 1,
                        "passed": 0,
                        "failed": 1,
                        "concurrency": 1,
                        "results_path": "runs/run_failure/results.jsonl",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    generate_matrix_scorecard_reports(summary_path, ["json", "md"])

    payload = json.loads((tmp_path / "failure-matrix-summary-matrix-scorecard.json").read_text(encoding="utf-8"))
    assert payload["scorecard"]["failure_class_summary"] == [
        {"failure_class": "engine_protocol_bug", "count": 1}
    ]
    assert payload["leaderboard"][0]["failure_class_summary"] == [
        {"failure_class": "engine_protocol_bug", "count": 1}
    ]
    md_report = (tmp_path / "failure-matrix-summary-matrix-scorecard.md").read_text(encoding="utf-8")
    assert "| Failure classes | engine_protocol_bug=1 |" in md_report
