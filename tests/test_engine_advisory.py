from __future__ import annotations

import json

from typer.testing import CliRunner

from agentblaster.cli import app
from agentblaster.engine_advisory import (
    build_engine_improvement_advisory,
    format_engine_improvement_advisory,
    write_engine_improvement_advisory,
)


def _write_json(path, payload) -> None:
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def test_engine_improvement_advisory_prioritizes_prefill_and_telemetry(tmp_path) -> None:
    pressure = tmp_path / "pressure.json"
    telemetry = tmp_path / "telemetry.json"
    metrics = tmp_path / "metrics.json"
    gate = tmp_path / "matrix-gate.json"
    saturation = tmp_path / "matrix-saturation.json"
    contract_matrix = tmp_path / "provider-contract-matrix.json"
    harness_review = tmp_path / "harness-review.json"
    _write_json(
        pressure,
        {
            "schema_version": "agentblaster.matrix-pressure-audit.v1",
            "runs": [
                {
                    "engine": "afm",
                    "suite": "prefill",
                    "model": "qwen-test",
                    "concurrency": 4,
                    "static_prefix_tokens": 3000,
                    "shared_static_prefix_tokens": 1500,
                    "shared_static_reuse_tokens": 1000,
                    "concurrency_weighted_pressure_score": 12000,
                    "prefill_pressure_level": "high",
                    "surfaces": {"cache-control": 1, "tools": 1},
                }
            ],
        },
    )
    _write_json(
        telemetry,
        {
            "schema_version": "agentblaster.telemetry-audit.v1",
            "summary": {"comparable_core_ok": False},
            "comparison_readiness": {
                "required_advisory_fields": ["tokens_per_second_decode"],
                "required_unknown_quality_fields": [],
                "guidance": "label-inferred-or-conditional-required-fields-before-cross-engine-comparison",
            },
            "findings": [{"severity": "blocker", "field": "prompt_eval_ms"}],
            "fields": [
                {"field": "prompt_eval_ms", "completeness": 0.0},
                {"field": "tokens_per_second_decode", "completeness": 1.0},
            ],
        },
    )
    _write_json(
        metrics,
        {
            "schema_version": "agentblaster.metric-coverage.v1",
            "summary": {"coverage_score": 0.5},
            "claim_contract": {
                "schema_version": "agentblaster.metric-claim-contract.v1",
                "claim_status_counts": {"limited": 1, "standardized": 1},
                "leaderboard_eligible_groups": ["agent_protocol_behavior"],
                "disclosure_required_groups": ["timing_and_throughput"],
                "primary_score_policy": "standardized-primary-ranking-allowed-when-run-telemetry-audit-passes",
            },
            "fields": [
                {"field": "prompt_eval_ms", "status": "unavailable"},
                {"field": "tokens_per_second_decode", "status": "native"},
            ],
        },
    )
    _write_json(
        gate,
        {
            "schema_version": "agentblaster.matrix-gate.v1",
            "ok": False,
            "matrix_name": "qwen-gemma",
            "failure_class_summary": [{"failure_class": "engine_protocol_bug", "count": 2}],
            "failure_class_artifacts_missing": 1,
            "tool_loop_stop_summary": [{"stop_reason": "max_tool_calls_reached", "count": 2}],
            "tool_loop_artifacts_missing": 1,
            "invalid_tool_call_count": 1,
            "tool_parser_repair_cases": 2,
            "tool_parser_repairs_valid": 1,
            "tool_parser_repair_valid_rate_percent": 50.0,
            "tool_parser_repair_artifacts_missing": 1,
            "findings": [
                {"metric": "case_pass_rate"},
                {
                    "metric": "failure_class.engine_protocol_bug",
                    "actual": 2,
                    "threshold": 0,
                    "message": "engine protocol bug threshold exceeded",
                },
                {
                    "metric": "invalid_tool_calls",
                    "actual": 1,
                    "threshold": 0,
                    "message": "invalid tool-call threshold exceeded",
                },
                {
                    "metric": "tool_parser_repair_valid_rate",
                    "actual": 50.0,
                    "threshold": 100.0,
                    "message": "parser repair rate below release threshold",
                },
            ],
        },
    )
    _write_json(
        saturation,
        {
            "schema_version": "agentblaster.matrix-saturation.v1",
            "entries": [
                {
                    "engine": "afm",
                    "group_id": "afm/afm/qwen-test/prefill",
                    "concurrency": 4,
                    "avg_queue_ms": 90.0,
                    "avg_rate_limit_wait_ms": 0.0,
                    "avg_decode_tokens_per_second": 18.0,
                }
            ],
            "groups": [
                {
                    "engine": "afm",
                    "group_id": "afm/afm/qwen-test/prefill",
                }
            ],
            "concurrency_evidence": {
                "guidance": "review-scheduler-queueing-and-provider-pacing-before-publication",
                "highest_queue_wait_entries": [
                    {
                        "engine": "afm",
                        "provider": "afm",
                        "model": "qwen-test",
                        "suite": "prefill",
                        "group_id": "afm/afm/qwen-test/prefill",
                        "run_id": "afm-c4",
                        "concurrency": 4,
                        "rank_metric": "avg_queue_ms",
                        "rank_value": 90.0,
                    }
                ],
            },
            "findings": [
                {
                    "severity": "warning",
                    "category": "decode_throughput_drop",
                    "group_id": "afm/afm/qwen-test/prefill",
                    "concurrency": 4,
                    "message": "decode throughput dropped",
                }
            ],
        },
    )
    _write_json(
        contract_matrix,
        {
            "schema_version": "agentblaster.provider-contract-matrix.v1",
            "mode": "executed",
            "ok": False,
            "summary": {"targets": 2, "failed_targets": 1},
            "entries": [
                {
                    "provider": "afm",
                    "contract": "openai",
                    "model": "qwen-test",
                    "mode": "executed",
                    "status": "failed",
                    "ok": False,
                    "summary": {"planned": 5, "passed": 4, "failed": 1, "skipped": 0},
                    "checks": [
                        {"id": "model-list", "status": "passed"},
                        {
                            "id": "tool-call",
                            "title": "Tool call response",
                            "status": "failed",
                            "required_capability": "tool_calling",
                            "message": "missing function call",
                        },
                    ],
                    "suites": ["toolcall"],
                    "concurrency_levels": [1, 4],
                },
                {
                    "provider": "other",
                    "contract": "openai",
                    "model": "qwen-test",
                    "mode": "executed",
                    "status": "failed",
                    "ok": False,
                    "summary": {"planned": 1, "passed": 0, "failed": 1, "skipped": 0},
                    "checks": [{"id": "exact-chat", "status": "failed"}],
                },
            ],
        },
    )
    _write_json(
        harness_review,
        {
            "schema_version": "agentblaster.harness-review.v1",
            "suite": {"name": "harness-orchestration", "case_count": 4},
            "generated": True,
            "generator": {"profile": "orchestration"},
            "surface_counts": {"multi_tool_catalog_cases": 4, "tool_loop_cases": 4},
            "assertion_counts": {"tool_name": 4},
            "review": {
                "status": "calibration-required",
                "human_review_required": True,
                "calibration_required_before_release_gate": True,
            },
        },
    )

    report = build_engine_improvement_advisory(
        engine="afm",
        pressure_audits=[pressure],
        telemetry_audits=[telemetry],
        metric_coverage_reports=[metrics],
        matrix_gates=[gate],
        matrix_saturation_reports=[saturation],
        provider_contract_matrices=[contract_matrix],
        harness_reviews=[harness_review],
    )

    areas = {item["area"] for item in report["priorities"]}
    assert report["schema_version"] == "agentblaster.engine-improvement-advisory.v1"
    assert {"prefill-cache", "scheduler-concurrency", "measured-saturation", "contract-conformance", "telemetry-instrumentation", "publishable-stats", "benchmark-reliability", "failure-taxonomy-remediation", "harness-calibration", "agentic-loop-control", "agentic-protocol-repair"} <= areas
    assert report["evidence"]["pressure"]["matching_runs"] == 1
    assert report["evidence"]["pressure"]["shared_static_reuse_tokens"] == 1000
    assert report["evidence"]["pressure"]["highest_runs"][0]["shared_static_reuse_tokens"] == 1000
    prefill_priority = next(item for item in report["priorities"] if item["area"] == "prefill-cache")
    assert "potential cache-reuse tokens" in prefill_priority["reason"]
    assert any("shared_static_reuse_tokens" in action for action in prefill_priority["recommended_actions"])
    assert report["evidence"]["saturation"]["finding_count"] == 1
    assert report["evidence"]["saturation"]["concurrency_evidence_guidance"] == [
        "review-scheduler-queueing-and-provider-pacing-before-publication"
    ]
    assert report["evidence"]["saturation"]["highest_queue_wait_entries"][0]["run_id"] == "afm-c4"
    assert report["evidence"]["gates"]["failure_class_summary"] == [
        {"failure_class": "engine_protocol_bug", "count": 2}
    ]
    assert report["evidence"]["gates"]["failure_class_artifacts_missing"] == 1
    assert report["evidence"]["gates"]["tool_loop_stop_summary"] == [
        {"stop_reason": "max_tool_calls_reached", "count": 2}
    ]
    assert report["evidence"]["gates"]["tool_loop_artifacts_missing"] == 1
    assert report["evidence"]["gates"]["failure_class_gate_count"] == 1
    assert "message" not in report["evidence"]["gates"]["failure_class_gate_findings"][0]
    assert report["evidence"]["gates"]["invalid_tool_call_count"] == 1
    assert report["evidence"]["gates"]["tool_parser_repair_cases"] == 2
    assert report["evidence"]["gates"]["tool_parser_repairs_valid"] == 1
    assert report["evidence"]["gates"]["tool_parser_repair_valid_rate_percent"] == 50.0
    assert report["evidence"]["gates"]["tool_parser_repair_artifacts_missing"] == 1
    assert report["evidence"]["gates"]["tool_parser_repair_gate_count"] == 2
    assert {
        finding["metric"] for finding in report["evidence"]["gates"]["tool_parser_repair_gate_findings"]
    } == {"invalid_tool_calls", "tool_parser_repair_valid_rate"}
    assert "message" not in report["evidence"]["gates"]["tool_parser_repair_gate_findings"][0]
    assert report["evidence"]["contract"]["failed_targets"] == 1
    assert report["evidence"]["contract"]["failed_check_ids"] == {"tool-call": 1}
    assert report["evidence"]["metric_coverage"]["claim_contract_present_count"] == 1
    assert report["evidence"]["metric_coverage"]["disclosure_required_groups"] == ["timing_and_throughput"]
    assert report["evidence"]["metric_coverage"]["leaderboard_eligible_groups"] == ["agent_protocol_behavior"]
    assert report["evidence"]["telemetry"]["blocker_count"] == 1
    assert report["evidence"]["telemetry"]["advisory_key_fields"] == ["tokens_per_second_decode"]
    assert report["evidence"]["harness"]["calibration_required_count"] == 1
    assert report["evidence"]["harness"]["generator_profiles"] == {"orchestration": 1}
    assert report["evidence"]["harness"]["surface_counts"]["multi_tool_catalog_cases"] == 4
    assert "AgentBlaster engine improvement advisory" in format_engine_improvement_advisory(report)


def test_write_engine_improvement_advisory(tmp_path) -> None:
    output = tmp_path / "advisory.json"
    report = build_engine_improvement_advisory(engine="afm")
    write_engine_improvement_advisory(report, output)

    assert json.loads(output.read_text(encoding="utf-8"))["engine"] == "afm"


def test_engine_improvement_advisory_flags_stale_matrix_gate_schema(tmp_path) -> None:
    gate = tmp_path / "stale-matrix-gate.json"
    _write_json(
        gate,
        {
            "ok": True,
            "matrix_name": "qwen-gemma",
            "pass_rate_percent": 100.0,
            "failure_class_summary": [],
            "findings": [],
        },
    )

    report = build_engine_improvement_advisory(engine="afm", matrix_gates=[gate])

    areas = {item["area"] for item in report["priorities"]}
    assert "evidence-integrity" in areas
    assert report["evidence"]["gates"]["invalid_matrix_gate_count"] == 1
    assert report["evidence"]["gates"]["invalid_matrix_gates"][0]["expected_schema"] == "agentblaster.matrix-gate.v1"
    assert report["evidence"]["gates"]["failed_gate_count"] == 1


def test_engine_improvement_advisory_flags_stale_harness_review_schema(tmp_path) -> None:
    harness_review = tmp_path / "harness-review.json"
    _write_json(
        harness_review,
        {
            "suite": {"name": "harness-orchestration"},
            "review": {"status": "calibration-required"},
            "surface_counts": {"multi_tool_catalog_cases": 4},
        },
    )

    report = build_engine_improvement_advisory(engine="afm", harness_reviews=[harness_review])

    areas = {item["area"] for item in report["priorities"]}
    assert "evidence-integrity" in areas
    assert report["evidence"]["harness"]["invalid_harness_review_count"] == 1
    assert report["evidence"]["harness"]["invalid_harness_reviews"][0]["expected_schema"] == "agentblaster.harness-review.v1"


def test_cli_engines_improvement_plan_writes_json(tmp_path) -> None:
    pressure = tmp_path / "pressure.json"
    contract = tmp_path / "contract.json"
    harness_review = tmp_path / "harness-review.json"
    output = tmp_path / "advisory.json"
    _write_json(
        pressure,
        {
            "schema_version": "agentblaster.matrix-pressure-audit.v1",
            "runs": [
                {
                    "engine": "afm",
                    "suite": "prefill",
                    "concurrency": 1,
                    "static_prefix_tokens": 100,
                    "shared_static_prefix_tokens": 0,
                    "shared_static_reuse_tokens": 0,
                    "concurrency_weighted_pressure_score": 100,
                    "surfaces": {},
                }
            ],
        },
    )
    _write_json(
        contract,
        {
            "schema_version": "agentblaster.provider-contract-check.v1",
            "ok": False,
            "mode": "plan-only",
            "provider": {"name": "afm", "contract": "openai", "remote": False},
            "model": "qwen-test",
            "summary": {"planned": 5, "passed": 0, "failed": 0, "skipped": 0},
            "checks": [{"id": "model-list", "status": "planned"}],
            "capability_evidence": {
                "directly_checked": ["streaming", "structured_output", "tool_calling"],
                "proxy_checked": [
                    {"capability": "judge_rubric", "covered_by": "structured_output", "declared": None}
                ],
                "not_covered": [],
            },
        },
    )
    _write_json(
        harness_review,
        {
            "schema_version": "agentblaster.harness-review.v1",
            "suite": {"name": "harness-orchestration", "case_count": 4},
            "generated": True,
            "generator": {"profile": "orchestration"},
            "review": {"status": "calibration-required", "calibration_required_before_release_gate": True},
        },
    )

    result = CliRunner().invoke(
        app,
        [
            "engines",
            "improvement-plan",
            "--engine",
            "afm",
            "--pressure-audit",
            str(pressure),
            "--provider-contract-check",
            str(contract),
            "--harness-review",
            str(harness_review),
            "--output-json",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "AgentBlaster engine improvement advisory" in result.output
    assert output.exists()
    advisory = json.loads(output.read_text(encoding="utf-8"))
    assert advisory["evidence"]["contract"]["plan_only_targets"] == 1
    assert advisory["evidence"]["contract"]["targets"][0]["capability_evidence"]["proxy_checked"][0][
        "capability"
    ] == "judge_rubric"
    assert advisory["evidence"]["harness"]["generator_profiles"] == {"orchestration": 1}
