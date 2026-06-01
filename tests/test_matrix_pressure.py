from __future__ import annotations

import json

from typer.testing import CliRunner

from agentblaster.cli import app
from agentblaster.matrix_pressure import audit_matrix_pressure, format_matrix_pressure_report, write_matrix_pressure_json


def test_audit_matrix_pressure_summarizes_concurrency_and_prefill(tmp_path) -> None:
    matrix = tmp_path / "matrix.yaml"
    matrix.write_text(
        "\n".join(
            [
                "name: pressure-demo",
                "runs:",
                "  - engine: afm",
                "    model: test-model",
                "    suite: agent-fanout",
                "    concurrency: 4",
                "  - engine: lm-studio",
                "    model: test-model",
                "    suite: prefill",
                "    concurrency: 1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = audit_matrix_pressure(matrix)

    assert report["schema_version"] == "agentblaster.matrix-pressure-audit.v1"
    assert report["matrix"] == "pressure-demo"
    assert report["run_count"] == 2
    assert report["totals"]["case_count"] >= 5
    assert report["totals"]["scheduled_prompt_tokens"] > 0
    assert report["totals"]["concurrency_weighted_pressure_score"] >= report["totals"]["prefill_pressure_score"]
    assert report["totals"]["shared_static_reuse_tokens"] > 0
    assert report["by_engine"]["afm"]["run_count"] == 1
    assert report["runs"][0]["concurrent_window_size"] == 4
    assert "system" in report["runs"][0]["surfaces"]
    formatted = format_matrix_pressure_report(report)
    assert "AgentBlaster matrix pressure audit" in formatted
    assert "shared_static_reuse_tokens" in formatted


def test_write_matrix_pressure_json(tmp_path) -> None:
    matrix = tmp_path / "matrix.yaml"
    output = tmp_path / "pressure.json"
    matrix.write_text(
        "name: pressure-demo\nruns:\n  - engine: afm\n    model: test-model\n    suite: smoke\n",
        encoding="utf-8",
    )

    report = audit_matrix_pressure(matrix)
    write_matrix_pressure_json(report, output)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["matrix"] == "pressure-demo"
    assert payload["totals"]["case_count"] == 1


def test_cli_matrix_pressure_audit_writes_json(tmp_path) -> None:
    matrix = tmp_path / "matrix.yaml"
    output = tmp_path / "pressure.json"
    matrix.write_text(
        "name: pressure-demo\nruns:\n  - engine: afm\n    model: test-model\n    suite: prefill\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "matrix",
            "pressure-audit",
            str(matrix),
            "--output-json",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "AgentBlaster matrix pressure audit" in result.output
    assert output.exists()
