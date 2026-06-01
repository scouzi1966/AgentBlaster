from __future__ import annotations

from agentblaster.models import RawTraceMode
from agentblaster.matrix import MatrixExecutionRunSummary, MatrixExecutionSummary, load_matrix_file
from agentblaster.matrix_gate import evaluate_matrix_gate, format_matrix_gate_report, write_matrix_gate_json


def test_load_matrix_file_resolves_relative_suite_file(tmp_path) -> None:
    suites_dir = tmp_path / "suites"
    suites_dir.mkdir()
    (suites_dir / "smoke.yaml").write_text(
        """
name: matrix-smoke-suite
description: Matrix smoke suite
cases:
  - id: case-one
    title: Case one
    prompt: "Reply with exactly: agentblaster-ok"
    expected_substring: agentblaster-ok
""",
        encoding="utf-8",
    )
    matrix_path = tmp_path / "matrix.yaml"
    matrix_path.write_text(
        """
name: local-matrix
runs:
  - engine: local-openai
    suite_file: suites/smoke.yaml
    model: qwen-test
    concurrency: 2
    model_metadata:
      revision: rev-1
      architecture: qwen3-dense
      quantization: mlx-f16
      context_length: 32768
    retention_policy:
      classification: confidential
      retain_days: 30
      raw_trace_retain_days: 7
      notes:
        - delete raw traces first
    no_raw_traces: true
    capability_preflight: false
    strict_unknown_capabilities: true
""",
        encoding="utf-8",
    )

    matrix = load_matrix_file(matrix_path)

    assert matrix.name == "local-matrix"
    assert matrix.runs[0].suite_file == suites_dir / "smoke.yaml"
    assert matrix.runs[0].concurrency == 2
    assert matrix.runs[0].model_metadata.revision == "rev-1"
    assert matrix.runs[0].model_metadata.architecture == "qwen3-dense"
    assert matrix.runs[0].model_metadata.context_length == 32768
    assert matrix.runs[0].retention_policy.classification == "confidential"
    assert matrix.runs[0].retention_policy.retain_days == 30
    assert matrix.runs[0].retention_policy.raw_trace_retain_days == 7
    assert matrix.runs[0].retention_policy.notes == ["delete raw traces first"]
    assert matrix.runs[0].raw_traces == RawTraceMode.REDACTED
    assert matrix.runs[0].capability_preflight is False
    assert matrix.runs[0].strict_unknown_capabilities is True


def test_matrix_execution_summary_contract_is_serializable() -> None:
    payload = MatrixExecutionSummary(
        matrix_name="local-matrix",
        matrix_path="examples/matrices/local-smoke.yaml",
        created_at="2026-05-31T00:00:00Z",
        total_runs=1,
        completed_runs=1,
        failed_runs=0,
        runs=[
            MatrixExecutionRunSummary(
                index=1,
                engine="afm",
                provider="afm",
                model="mlx-community/Qwen3.6-27B",
                suite="smoke",
                run_id="run_20260531T000000Z_deadbeef",
                ok=True,
                total_cases=1,
                passed=1,
                failed=0,
                concurrency=1,
                results_path="runs/run_20260531T000000Z_deadbeef/results.jsonl",
                manifest_path="runs/run_20260531T000000Z_deadbeef/manifest.json",
                summary_path="runs/run_20260531T000000Z_deadbeef/summary.json",
            )
        ],
    )

    assert payload.schema_version == 1
    assert payload.runs[0].ok is True


def test_matrix_execution_summary_can_record_failed_attempt() -> None:
    payload = MatrixExecutionSummary(
        matrix_name="local-matrix",
        matrix_path="examples/matrices/local-smoke.yaml",
        created_at="2026-05-31T00:00:00Z",
        continue_on_error=True,
        total_runs=1,
        attempted_runs=1,
        completed_runs=0,
        failed_runs=1,
        runs=[
            MatrixExecutionRunSummary(
                index=1,
                engine="missing-provider",
                provider="missing-provider",
                model="qwen-test",
                suite="smoke",
                ok=False,
                total_cases=0,
                passed=0,
                failed=0,
                concurrency=1,
                error_type="ConfigError",
                error_message="provider not configured: missing-provider",
            )
        ],
    )

    assert payload.continue_on_error is True
    assert payload.attempted_runs == 1
    assert payload.runs[0].run_id is None
    assert payload.runs[0].summary_path is None
    assert payload.runs[0].error_type == "ConfigError"


def test_matrix_gate_flags_incomplete_and_low_pass_rate(tmp_path) -> None:
    summary = MatrixExecutionSummary(
        matrix_name="release-matrix",
        matrix_path="examples/matrices/release.yaml",
        created_at="2026-05-31T00:00:00Z",
        total_runs=2,
        attempted_runs=2,
        completed_runs=1,
        failed_runs=1,
        runs=[
            MatrixExecutionRunSummary(
                index=1,
                engine="afm",
                provider="afm",
                model="qwen-test",
                suite="smoke",
                run_id="run-a",
                ok=True,
                total_cases=10,
                passed=10,
                failed=0,
                concurrency=1,
                results_path="runs/run-a/results.jsonl",
                manifest_path="runs/run-a/manifest.json",
                summary_path="runs/run-a/summary.json",
            ),
            MatrixExecutionRunSummary(
                index=2,
                engine="lm-studio",
                provider="lm-studio",
                model="gemma-test",
                suite="smoke",
                ok=False,
                total_cases=10,
                passed=7,
                failed=3,
                concurrency=1,
                error_type="PolicyError",
                error_message="blocked",
            ),
        ],
    )

    report = evaluate_matrix_gate(
        summary,
        require_all_runs_complete=True,
        max_failed_runs=0,
        min_case_pass_rate=90.0,
        max_failed_cases=0,
    )

    assert report.ok is False
    assert report.pass_rate_percent == 85.0
    assert {finding.metric for finding in report.findings} == {
        "all_runs_complete",
        "failed_runs",
        "case_pass_rate",
        "failed_cases",
    }
    text = format_matrix_gate_report(report)
    assert "ok: false" in text
    output = tmp_path / "matrix-gate.json"
    write_matrix_gate_json(report, output)
    assert "case_pass_rate" in output.read_text(encoding="utf-8")


def test_matrix_gate_passes_within_thresholds() -> None:
    summary = MatrixExecutionSummary(
        matrix_name="release-matrix",
        matrix_path="examples/matrices/release.yaml",
        created_at="2026-05-31T00:00:00Z",
        total_runs=1,
        attempted_runs=1,
        completed_runs=1,
        failed_runs=0,
        runs=[
            MatrixExecutionRunSummary(
                index=1,
                engine="afm",
                provider="afm",
                model="qwen-test",
                suite="smoke",
                run_id="run-a",
                ok=True,
                total_cases=10,
                passed=10,
                failed=0,
                concurrency=1,
                results_path="runs/run-a/results.jsonl",
                manifest_path="runs/run-a/manifest.json",
                summary_path="runs/run-a/summary.json",
            )
        ],
    )

    report = evaluate_matrix_gate(
        summary,
        require_all_runs_complete=True,
        max_failed_runs=0,
        min_completed_runs=1,
        min_attempted_runs=1,
        min_case_pass_rate=100.0,
        max_failed_cases=0,
    )

    assert report.ok is True
    assert report.findings == []
