from __future__ import annotations

import json

from typer.testing import CliRunner

from agentblaster.cli import app
from agentblaster.publication_brief import build_publication_brief, format_publication_brief


def test_publication_brief_summarizes_claim_readiness_and_scorecard(tmp_path) -> None:
    claim = _write_claim_readiness(tmp_path)
    scorecard = _write_matrix_scorecard(tmp_path)

    report = build_publication_brief(
        name="Qwen/Gemma Local Campaign",
        claim_readiness=claim,
        matrix_scorecards=[scorecard],
    )

    assert report["schema_version"] == "agentblaster.publication-brief.v1"
    assert report["ready"] is True
    assert report["claim_readiness"]["warnings"] == 1
    assert report["engine_targets"] == [
        {"id": "afm-mlx", "display_name": "AFM MLX", "primary_scoring_contract": "openai"}
    ]
    assert report["architecture_summary"][0]["model_architecture"] == "qwen3.6-dense"
    assert report["quantization_summary"][0]["quantization"] == "mlx-f16"
    assert report["matrix_scorecards"][0]["matrix_name"] == "qwen-gemma-local"
    assert report["matrix_scorecards"][0]["engine_targets"] == [
        {"id": "afm-mlx", "display_name": "AFM MLX", "primary_scoring_contract": "openai"}
    ]
    assert report["matrix_scorecards"][0]["architecture_summary"][0]["model_architecture"] == "qwen3.6-dense"
    assert report["matrix_scorecards"][0]["quantization_summary"][0]["quantization"] == "mlx-f16"
    assert report["protocol_repair_summary"]["status"] == "review-required"
    assert report["protocol_repair_summary"]["invalid_tool_call_count"] == 1
    assert report["protocol_repair_summary"]["tool_parser_repair_cases"] == 2
    assert report["protocol_repair_summary"]["tool_parser_repairs_valid"] == 1
    assert report["protocol_repair_summary"]["matrix_gate_tool_parser_repair_cases"] == 2
    assert report["matrix_scorecards"][0]["top_entries"][0]["engine"] == "afm"
    assert report["media_kit"]["status"] == "review-required"
    assert report["media_kit"]["run_bundle_count"] == 1
    assert report["media_kit"]["matrix_bundle_count"] == 1
    assert report["media_kit"]["missing_recommended_assets"] == ["social-card-png"]
    assert report["security"]["contains_raw_provider_payloads"] is False
    assert any("metric_coverage" in item for item in report["disclosures"])
    assert any("Media kit requires review" in item for item in report["disclosures"])
    assert any("Protocol-repair evidence requires review" in item for item in report["disclosures"])
    assert report["media_kit"]["bundles"][1]["engine_targets"] == [
        {"id": "afm-mlx", "display_name": "AFM MLX", "primary_scoring_contract": "openai"}
    ]
    assert report["media_kit"]["bundles"][1]["architecture_summary"][0]["model_architecture"] == "qwen3.6-dense"
    assert report["media_kit"]["bundles"][1]["quantization_summary"][0]["quantization"] == "mlx-f16"
    markdown = format_publication_brief(report)
    assert "AgentBlaster Publication Brief" in markdown
    assert "afm-mlx" in markdown
    assert "qwen3.6-dense" in markdown
    assert "mlx-f16" in markdown
    assert "Agentic Protocol Repair" in markdown
    assert "1/2 valid" in markdown


def test_publication_brief_cli_writes_json_and_markdown(tmp_path) -> None:
    claim = _write_claim_readiness(tmp_path)
    scorecard = _write_matrix_scorecard(tmp_path)
    output_json = tmp_path / "brief.json"
    output_md = tmp_path / "brief.md"

    result = CliRunner().invoke(
        app,
        [
            "release",
            "publication-brief",
            "--claim-readiness",
            str(claim),
            "--matrix-scorecard",
            str(scorecard),
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
    assert payload["schema_version"] == "agentblaster.publication-brief.v1"
    assert payload["engine_targets"][0]["id"] == "afm-mlx"
    assert payload["architecture_summary"][0]["model_architecture"] == "qwen3.6-dense"
    assert payload["quantization_summary"][0]["quantization"] == "mlx-f16"
    assert payload["media_kit"]["expected_schema_version"] == "agentblaster.media-kit.v1"
    assert payload["protocol_repair_summary"]["status"] == "review-required"
    assert payload["protocol_repair_summary"]["tool_parser_repair_cases"] == 2
    assert "Recommended Language" in output_md.read_text(encoding="utf-8")
    assert "Agentic Protocol Repair" in output_md.read_text(encoding="utf-8")
    assert "Media Kit Readiness" in output_md.read_text(encoding="utf-8")


def _write_claim_readiness(tmp_path):
    path = tmp_path / "claim-readiness.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.claim-readiness.v1",
                "name": "qwen-gemma-local",
                "ready": True,
                "summary": {"checks": 6, "passed": 5, "blockers": 0, "warnings": 1},
                "evidence": {
                    "provider_contract_capability_evidence": {
                        "directly_checked": ["streaming", "structured_output", "tool_calling"],
                        "proxy_checked_counts": {"judge_rubric": 1},
                        "not_covered_counts": {"prompt_caching": 1},
                    },
                    "matrix_gate_tool_parser_repair_summary": {
                        "invalid_tool_call_count": 1,
                        "tool_parser_repair_cases": 2,
                        "tool_parser_repairs_valid": 1,
                        "tool_parser_repair_valid_rate_percent": 50.0,
                    },
                    "matrix_gate_tool_parser_repair_artifacts_missing": 0,
                    "publication_bundle_summaries": [
                        {
                            "artifact": "qwen-gemma-run-publication.zip",
                            "status": "ready",
                            "artifact_count": 5,
                            "media_kit": {
                                "schema_version": "agentblaster.media-kit.v1",
                                "status": "ready",
                                "asset_count": 5,
                                "recommended_sets": ["corporate-review-packet"],
                                "missing_recommended_assets": [],
                            },
                        }
                    ],
                    "matrix_publication_bundle_summaries": [
                        {
                            "artifact": "qwen-gemma-matrix-publication.zip",
                            "status": "review",
                            "artifact_count": 4,
                            "engine_targets": [
                                {
                                    "id": "afm-mlx",
                                    "display_name": "AFM MLX",
                                    "primary_scoring_contract": "openai",
                                }
                            ],
                            "architecture_summary": [
                                {
                                    "model_architecture": "qwen3.6-dense",
                                    "runs": 2,
                                    "completed_runs": 2,
                                    "failed_runs": 0,
                                    "result_artifacts_loaded": 2,
                                    "total_cases": 20,
                                    "passed": 18,
                                    "failed": 2,
                                    "pass_rate_percent": 90.0,
                                    "avg_latency_ms": 123.4,
                                    "avg_decode_tokens_per_second": 42.5,
                                    "judge_rubric_cases": 2,
                                    "judge_verdicts_valid": 2,
                                }
                            ],
                            "quantization_summary": [
                                {
                                    "quantization": "mlx-f16",
                                    "runs": 2,
                                    "completed_runs": 2,
                                    "failed_runs": 0,
                                    "result_artifacts_loaded": 2,
                                    "total_cases": 20,
                                    "passed": 18,
                                    "failed": 2,
                                    "pass_rate_percent": 90.0,
                                    "avg_latency_ms": 123.4,
                                    "avg_decode_tokens_per_second": 42.5,
                                    "judge_rubric_cases": 2,
                                    "judge_verdicts_valid": 2,
                                }
                            ],
                            "media_kit": {
                                "schema_version": "agentblaster.media-kit.v1",
                                "status": "review",
                                "asset_count": 3,
                                "recommended_sets": ["media-post-packet"],
                                "missing_recommended_assets": ["social-card-png"],
                            },
                        }
                    ],
                },
                "checks": [
                    {"category": "provider_contract_evidence", "severity": "blocker", "ok": True},
                    {"category": "metric_coverage", "severity": "warning", "ok": False},
                ],
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
                "matrix": {
                    "name": "qwen-gemma-local",
                    "total_runs": 2,
                    "completed_runs": 2,
                    "failed_runs": 0,
                },
                "scorecard": {
                    "entry_count": 2,
                    "total_cases": 20,
                    "passed_cases": 18,
                    "failed_cases": 2,
                    "pass_rate_percent": 90.0,
                    "invalid_tool_call_count": 1,
                    "tool_parser_repair_cases": 2,
                    "tool_parser_repairs_valid": 1,
                    "tool_parser_repair_valid_rate_percent": 50.0,
                    "result_artifacts_loaded": 2,
                    "engine_targets": [
                        {
                            "id": "afm-mlx",
                            "display_name": "AFM MLX",
                            "primary_scoring_contract": "openai",
                        }
                    ],
                    "telemetry_quality_summary": {"publication_grade": 6, "advisory": 1},
                    "stats_comparability_summary": {"publication_grade": 5},
                    "concurrency_evidence": {"concurrency_levels": [1, 4]},
                },
                "architecture_summary": [
                    {
                        "model_architecture": "qwen3.6-dense",
                        "runs": 2,
                        "completed_runs": 2,
                        "failed_runs": 0,
                        "result_artifacts_loaded": 2,
                        "total_cases": 20,
                        "passed": 18,
                        "failed": 2,
                        "pass_rate_percent": 90.0,
                        "avg_latency_ms": 123.4,
                        "avg_decode_tokens_per_second": 42.5,
                        "judge_rubric_cases": 2,
                        "judge_verdicts_valid": 2,
                        "invalid_tool_call_count": 1,
                        "tool_parser_repair_cases": 2,
                        "tool_parser_repairs_valid": 1,
                        "tool_parser_repair_valid_rate_percent": 50.0,
                    }
                ],
                "quantization_summary": [
                    {
                        "quantization": "mlx-f16",
                        "runs": 2,
                        "completed_runs": 2,
                        "failed_runs": 0,
                        "result_artifacts_loaded": 2,
                        "total_cases": 20,
                        "passed": 18,
                        "failed": 2,
                        "pass_rate_percent": 90.0,
                        "avg_latency_ms": 123.4,
                        "avg_decode_tokens_per_second": 42.5,
                        "judge_rubric_cases": 2,
                        "judge_verdicts_valid": 2,
                        "invalid_tool_call_count": 1,
                        "tool_parser_repair_cases": 2,
                        "tool_parser_repairs_valid": 1,
                        "tool_parser_repair_valid_rate_percent": 50.0,
                    }
                ],
                "leaderboard": [
                    {
                        "rank": 1,
                        "engine": "afm",
                        "provider": "afm-local",
                        "model": "qwen3.6-27b-dense",
                        "suite": "agentic-tool-loop",
                        "pass_rate_percent": 95.0,
                        "avg_latency_ms": 123.4,
                        "avg_decode_tokens_per_second": 42.5,
                    }
                ],
                "security": {"contains_raw_provider_payloads": False, "contains_secrets": False},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return path
