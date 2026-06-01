from __future__ import annotations

import json

from typer.testing import CliRunner

from agentblaster.cli import app
from agentblaster.models import ApiContract, BenchmarkResult, RawTraceMode, RunManifest
from agentblaster.telemetry_audit import audit_run_telemetry, format_telemetry_audit, write_telemetry_audit_json


def _write_run(run_dir) -> None:
    run_dir.mkdir()
    manifest = RunManifest(
        run_id="run_telemetry",
        suite="smoke",
        provider="ollama-native",
        contract=ApiContract.NATIVE,
        model="qwen-test",
        raw_trace_mode=RawTraceMode.OFF,
        created_at="2026-05-31T00:00:00Z",
        case_count=2,
    )
    results = [
        BenchmarkResult(
            run_id="run_telemetry",
            case_id="case-1",
            suite="smoke",
            provider="ollama-native",
            contract=ApiContract.NATIVE,
            model="qwen-test",
            ok=True,
            latency_ms=10.0,
            input_tokens=8,
            output_tokens=4,
            total_tokens=12,
            tokens_per_second_decode=8.0,
            telemetry_schema_version="agentblaster.normalized-telemetry.v1",
            telemetry_sources={
                "latency_ms": "agentblaster timer",
                "input_tokens": "prompt_eval_count",
                "output_tokens": "eval_count",
                "total_tokens": "prompt_eval_count + eval_count",
                "tokens_per_second_decode": "eval_count / eval_duration",
            },
            telemetry_quality={
                "latency_ms": "measured",
                "input_tokens": "native",
                "output_tokens": "native",
                "total_tokens": "inferred",
                "tokens_per_second_decode": "inferred",
            },
            telemetry_comparison_readiness={
                "schema_version": "agentblaster.telemetry-comparison-readiness.v1",
                "advisory_fields": ["total_tokens", "tokens_per_second_decode"],
            },
            telemetry_missing=["ttft_ms", "prompt_eval_ms", "decode_ms"],
            message="ok",
        ),
        BenchmarkResult(
            run_id="run_telemetry",
            case_id="case-2",
            suite="smoke",
            provider="ollama-native",
            contract=ApiContract.NATIVE,
            model="qwen-test",
            ok=True,
            latency_ms=12.0,
            input_tokens=9,
            output_tokens=3,
            total_tokens=12,
            telemetry_schema_version="agentblaster.normalized-telemetry.v1",
            telemetry_sources={
                "latency_ms": "agentblaster timer",
                "input_tokens": "prompt_eval_count",
                "output_tokens": "eval_count",
                "total_tokens": "prompt_eval_count + eval_count",
            },
            telemetry_quality={
                "latency_ms": "measured",
                "input_tokens": "native",
                "output_tokens": "native",
                "total_tokens": "inferred",
            },
            telemetry_missing=["tokens_per_second_decode"],
            message="ok",
        ),
    ]
    (run_dir / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    (run_dir / "results.jsonl").write_text(
        "\n".join(result.model_dump_json() for result in results) + "\n",
        encoding="utf-8",
    )


def test_audit_run_telemetry_reports_required_field_gaps(tmp_path) -> None:
    run_dir = tmp_path / "run_telemetry"
    _write_run(run_dir)

    report = audit_run_telemetry(
        run_dir,
        required_fields=["latency_ms", "tokens_per_second_decode"],
        min_required_completeness=1.0,
    )

    assert report["schema_version"] == "agentblaster.telemetry-audit.v1"
    assert report["summary"]["comparable_core_ok"] is False
    assert report["summary"]["telemetry_schema_versions"] == ["agentblaster.normalized-telemetry.v1"]
    fields = {field["field"]: field for field in report["fields"]}
    assert fields["latency_ms"]["completeness"] == 1.0
    assert fields["latency_ms"]["source_quality_counts"]["measured"] == 2
    assert fields["tokens_per_second_decode"]["completeness"] == 0.5
    assert fields["tokens_per_second_decode"]["source_quality_counts"]["inferred"] == 1
    assert report["summary"]["advisory_field_count"] >= 1
    assert report["comparison_readiness"]["required_advisory_fields"] == ["tokens_per_second_decode"]
    assert (
        report["comparison_readiness"]["guidance"]
        == "label-inferred-or-conditional-required-fields-before-cross-engine-comparison"
    )
    assert report["findings"][0]["field"] == "tokens_per_second_decode"
    assert "comparable_core_ok: false" in format_telemetry_audit(report)
    assert "comparison_readiness: label-inferred-or-conditional-required-fields-before-cross-engine-comparison" in format_telemetry_audit(report)


def test_write_telemetry_audit_json(tmp_path) -> None:
    run_dir = tmp_path / "run_telemetry"
    output = tmp_path / "telemetry-audit.json"
    _write_run(run_dir)

    report = audit_run_telemetry(run_dir, required_fields=["latency_ms"])
    write_telemetry_audit_json(report, output)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["run"]["run_id"] == "run_telemetry"
    assert payload["summary"]["comparable_core_ok"] is True
    assert payload["comparison_readiness"]["schema_version"] == "agentblaster.telemetry-comparison-readiness.v1"


def test_cli_telemetry_audit_writes_report(tmp_path) -> None:
    run_dir = tmp_path / "run_telemetry"
    output = tmp_path / "telemetry-audit.json"
    _write_run(run_dir)

    result = CliRunner().invoke(
        app,
        [
            "telemetry-audit",
            str(run_dir),
            "--required-field",
            "tokens_per_second_decode",
            "--output-json",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "AgentBlaster telemetry audit" in result.output
    assert output.exists()
