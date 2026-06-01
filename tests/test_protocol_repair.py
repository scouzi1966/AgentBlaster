from __future__ import annotations

import json

from typer.testing import CliRunner

from agentblaster.cli import app
from agentblaster.protocol_repair import build_protocol_repair_posture, format_protocol_repair_posture


def test_protocol_repair_posture_summarizes_scorecard_and_gate(tmp_path) -> None:
    claim = _write_claim_readiness(tmp_path)
    scorecard = _write_matrix_scorecard(tmp_path)
    gate = _write_matrix_gate(tmp_path)

    report = build_protocol_repair_posture(
        name="Qwen/Gemma Local Campaign",
        claim_readiness=claim,
        matrix_scorecards=[scorecard],
        matrix_gates=[gate],
    )

    assert report["schema_version"] == "agentblaster.protocol-repair-posture.v1"
    assert report["status"] == "review-required"
    assert report["ready"] is False
    assert report["scorecard_summary"]["source_count"] == 1
    assert report["scorecard_summary"]["invalid_tool_call_count"] == 1
    assert report["scorecard_summary"]["tool_parser_repair_cases"] == 2
    assert report["scorecard_summary"]["tool_parser_repairs_valid"] == 1
    assert report["matrix_gate_summary"]["source_count"] == 1
    assert report["matrix_gate_summary"]["invalid_tool_call_count"] == 1
    assert report["matrix_gate_summary"]["tool_parser_repair_artifacts_missing"] == 1
    assert report["security"]["contains_raw_provider_payloads"] is False
    assert any("invalid tool-call" in item for item in report["disclosures"])
    markdown = format_protocol_repair_posture(report)
    assert "AgentBlaster Protocol Repair Posture" in markdown
    assert "1/2 valid" in markdown
    assert "Matrix-gate evidence gaps" in markdown


def test_protocol_repair_cli_writes_json_and_markdown(tmp_path) -> None:
    claim = _write_claim_readiness(tmp_path)
    scorecard = _write_matrix_scorecard(tmp_path)
    gate = _write_matrix_gate(tmp_path)
    output_json = tmp_path / "protocol-repair.json"
    output_md = tmp_path / "protocol-repair.md"

    result = CliRunner().invoke(
        app,
        [
            "release",
            "protocol-repair",
            "--claim-readiness",
            str(claim),
            "--matrix-scorecard",
            str(scorecard),
            "--matrix-gate",
            str(gate),
            "--name",
            "Qwen/Gemma Local Campaign",
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ],
    )

    assert result.exit_code == 0, result.output
    assert str(output_json) in result.output
    assert str(output_md) in result.output
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "agentblaster.protocol-repair-posture.v1"
    assert payload["status"] == "review-required"
    assert payload["scorecard_summary"]["tool_parser_repair_cases"] == 2
    assert payload["matrix_gate_summary"]["tool_parser_repair_artifacts_missing"] == 1
    assert "AgentBlaster Protocol Repair Posture" in output_md.read_text(encoding="utf-8")


def _write_claim_readiness(tmp_path):
    path = tmp_path / "claim-readiness.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.claim-readiness.v1",
                "name": "qwen-gemma-local",
                "ready": True,
                "summary": {"checks": 6, "passed": 6, "blockers": 0, "warnings": 0},
                "evidence": {
                    "matrix_gate_tool_parser_repair_summary": {
                        "invalid_tool_call_count": 9,
                        "tool_parser_repair_cases": 9,
                        "tool_parser_repairs_valid": 0,
                        "tool_parser_repair_valid_rate_percent": 0.0,
                    },
                    "matrix_gate_tool_parser_repair_artifacts_missing": 9,
                    "matrix_scorecard_summaries": [
                        {
                            "matrix_name": "embedded",
                            "invalid_tool_call_count": 9,
                            "tool_parser_repair_cases": 9,
                            "tool_parser_repairs_valid": 0,
                            "tool_parser_repair_valid_rate_percent": 0.0,
                        }
                    ],
                },
                "checks": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _write_matrix_scorecard(tmp_path):
    path = tmp_path / "matrix-scorecard.json"
    path.write_text(
        json.dumps(
            {
                "report_type": "agentblaster-matrix-scorecard-v1",
                "matrix": {"name": "qwen-gemma-local", "total_runs": 2, "completed_runs": 2, "failed_runs": 0},
                "scorecard": {
                    "entry_count": 2,
                    "result_artifacts_loaded": 2,
                    "invalid_tool_call_count": 1,
                    "tool_parser_repair_cases": 2,
                    "tool_parser_repairs_valid": 1,
                    "tool_parser_repair_valid_rate_percent": 50.0,
                },
                "security": {"contains_raw_provider_payloads": False, "contains_secrets": False},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _write_matrix_gate(tmp_path):
    path = tmp_path / "matrix-gate.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.matrix-gate.v1",
                "matrix_name": "qwen-gemma-local",
                "ok": False,
                "invalid_tool_call_count": 1,
                "tool_parser_repair_cases": 2,
                "tool_parser_repairs_valid": 1,
                "tool_parser_repair_valid_rate_percent": 50.0,
                "tool_parser_repair_artifacts_missing": 1,
                "findings": [{"code": "tool_parser_repair_valid_rate", "severity": "error"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return path
