from __future__ import annotations

import json

from typer.testing import CliRunner

from agentblaster.cli import app
from agentblaster.matrix_saturation import build_matrix_saturation_report, format_matrix_saturation_report
from agentblaster.models import ApiContract, BenchmarkResult


def test_matrix_saturation_report_detects_concurrency_regressions(tmp_path) -> None:
    _write_result(
        tmp_path / "runs" / "afm_c1",
        BenchmarkResult(
            run_id="afm_c1",
            case_id="case-one",
            suite="prefill",
            scenario="prefill",
            provider="afm",
            contract=ApiContract.OPENAI,
            model="mlx-community/Qwen3.6-27B",
            ok=True,
            queue_ms=1.0,
            rate_limit_wait_ms=0.0,
            latency_ms=100.0,
            ttft_ms=40.0,
            tokens_per_second_decode=50.0,
            message="ok",
        ),
    )
    _write_result(
        tmp_path / "runs" / "afm_c4",
        BenchmarkResult(
            run_id="afm_c4",
            case_id="case-one",
            suite="prefill",
            scenario="prefill",
            provider="afm",
            contract=ApiContract.OPENAI,
            model="mlx-community/Qwen3.6-27B",
            ok=True,
            queue_ms=80.0,
            rate_limit_wait_ms=55.0,
            latency_ms=190.0,
            ttft_ms=90.0,
            tokens_per_second_decode=20.0,
            message="ok",
        ),
    )
    summary = _write_summary(tmp_path)

    report = build_matrix_saturation_report(summary)

    categories = {finding["category"] for finding in report["findings"]}
    assert report["schema_version"] == "agentblaster.matrix-saturation.v1"
    assert report["ok"] is True
    assert report["summary"]["result_artifacts_loaded"] == 2
    assert report["concurrency_evidence"]["schema_version"] == "agentblaster.concurrency-evidence.v1"
    assert report["concurrency_evidence"]["multi_level_group_count"] == 1
    assert report["concurrency_evidence"]["max_avg_queue_ms"] == 80.0
    assert report["concurrency_evidence"]["max_avg_rate_limit_wait_ms"] == 55.0
    assert report["concurrency_evidence"]["highest_queue_wait_entries"][0]["run_id"] == "afm_c4"
    assert (
        report["concurrency_evidence"]["guidance"]
        == "review-scheduler-queueing-and-provider-pacing-before-publication"
    )
    assert report["groups"][0]["concurrency_levels"] == [1, 4]
    assert "latency_regression" in categories
    assert "p95_latency_regression" in categories
    assert "decode_throughput_drop" in categories
    assert "queue_wait" in categories
    assert "rate_limit_wait" in categories
    assert report["security"]["contains_raw_provider_payloads"] is False
    rendered = format_matrix_saturation_report(report)
    assert "AgentBlaster matrix saturation report" in rendered
    assert "concurrency_evidence: review-scheduler-queueing-and-provider-pacing-before-publication" in rendered


def test_cli_matrix_saturation_report_writes_json(tmp_path) -> None:
    _write_result(
        tmp_path / "runs" / "afm_c1",
        BenchmarkResult(
            run_id="afm_c1",
            case_id="case-one",
            suite="prefill",
            provider="afm",
            contract=ApiContract.OPENAI,
            model="mlx-community/Qwen3.6-27B",
            ok=True,
            latency_ms=100.0,
            tokens_per_second_decode=50.0,
            message="ok",
        ),
    )
    _write_result(
        tmp_path / "runs" / "afm_c4",
        BenchmarkResult(
            run_id="afm_c4",
            case_id="case-one",
            suite="prefill",
            provider="afm",
            contract=ApiContract.OPENAI,
            model="mlx-community/Qwen3.6-27B",
            ok=True,
            latency_ms=120.0,
            tokens_per_second_decode=45.0,
            message="ok",
        ),
    )
    summary = _write_summary(tmp_path)
    output = tmp_path / "reports" / "saturation.json"

    result = CliRunner().invoke(
        app,
        [
            "matrix",
            "saturation-report",
            str(summary),
            "--output-json",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "AgentBlaster matrix saturation report" in result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "agentblaster.matrix-saturation.v1"
    assert payload["ok"] is True
    assert payload["summary"]["group_count"] == 1
    assert payload["concurrency_evidence"]["max_concurrency"] == 4


def _write_result(run_dir, result: BenchmarkResult) -> None:
    run_dir.mkdir(parents=True)
    (run_dir / "results.jsonl").write_text(result.model_dump_json() + "\n", encoding="utf-8")


def _write_summary(tmp_path):
    summary = tmp_path / "qwen-gemma-matrix-summary.json"
    summary.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "matrix_name": "qwen-gemma-local",
                "matrix_path": "examples/matrices/qwen-gemma-local.yaml",
                "description": "Qwen/Gemma local matrix",
                "created_at": "2026-05-31T00:00:00Z",
                "total_runs": 2,
                "attempted_runs": 2,
                "completed_runs": 2,
                "failed_runs": 0,
                "runs": [
                    {
                        "index": 1,
                        "engine": "afm",
                        "provider": "afm",
                        "model": "mlx-community/Qwen3.6-27B",
                        "suite": "prefill",
                        "run_id": "afm_c1",
                        "ok": True,
                        "total_cases": 1,
                        "passed": 1,
                        "failed": 0,
                        "concurrency": 1,
                        "results_path": "runs/afm_c1/results.jsonl",
                    },
                    {
                        "index": 2,
                        "engine": "afm",
                        "provider": "afm",
                        "model": "mlx-community/Qwen3.6-27B",
                        "suite": "prefill",
                        "run_id": "afm_c4",
                        "ok": True,
                        "total_cases": 1,
                        "passed": 1,
                        "failed": 0,
                        "concurrency": 4,
                        "results_path": "runs/afm_c4/results.jsonl",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return summary
