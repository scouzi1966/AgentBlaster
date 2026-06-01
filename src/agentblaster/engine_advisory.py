from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentblaster.errors import ConfigError
from agentblaster.harness import HARNESS_REVIEW_SCHEMA_VERSION
from agentblaster.matrix_gate import MATRIX_GATE_SCHEMA_VERSION


ENGINE_ADVISORY_SCHEMA_VERSION = "agentblaster.engine-improvement-advisory.v1"
KEY_TELEMETRY_FIELDS = {
    "latency_ms",
    "ttft_ms",
    "prompt_eval_ms",
    "decode_ms",
    "tokens_per_second_prefill",
    "tokens_per_second_decode",
    "cached_input_tokens",
    "cache_write_tokens",
    "cache_hit_ratio",
}


def build_engine_improvement_advisory(
    *,
    engine: str,
    pressure_audits: list[Path] | None = None,
    telemetry_audits: list[Path] | None = None,
    metric_coverage_reports: list[Path] | None = None,
    matrix_gates: list[Path] | None = None,
    comparison_gates: list[Path] | None = None,
    matrix_saturation_reports: list[Path] | None = None,
    provider_contract_checks: list[Path] | None = None,
    provider_contract_matrices: list[Path] | None = None,
    harness_reviews: list[Path] | None = None,
) -> dict[str, Any]:
    """Build a no-dispatch engine improvement advisory from review artifacts."""

    engine_name = engine.strip()
    if not engine_name:
        raise ConfigError("engine improvement advisory requires an engine name")

    pressure = _pressure_summary(engine_name, [_load_json(path) for path in pressure_audits or []])
    telemetry = _telemetry_summary([_load_json(path) for path in telemetry_audits or []])
    metrics = _metric_coverage_summary([_load_json(path) for path in metric_coverage_reports or []])
    gates = _gate_summary([_load_json(path) for path in matrix_gates or []], [_load_json(path) for path in comparison_gates or []])
    saturation = _saturation_summary(engine_name, [_load_json(path) for path in matrix_saturation_reports or []])
    contract = _contract_summary(
        engine_name,
        [_load_json(path) for path in provider_contract_checks or []],
        [_load_json(path) for path in provider_contract_matrices or []],
    )
    harness = _harness_summary([_load_json(path) for path in harness_reviews or []])
    priorities = _priorities(engine_name, pressure, telemetry, metrics, gates, saturation, contract, harness)
    return {
        "schema_version": ENGINE_ADVISORY_SCHEMA_VERSION,
        "engine": engine_name,
        "summary": {
            "priority_count": len(priorities),
            "highest_priority": priorities[0]["priority"] if priorities else None,
            "evidence_artifacts": sum(
                len(items or [])
                for items in [
                    pressure_audits,
                    telemetry_audits,
                    metric_coverage_reports,
                    matrix_gates,
                    comparison_gates,
                    matrix_saturation_reports,
                    provider_contract_checks,
                    provider_contract_matrices,
                    harness_reviews,
                ]
            ),
            "no_dispatch": True,
        },
        "evidence": {
            "pressure": pressure,
            "telemetry": telemetry,
            "metric_coverage": metrics,
            "gates": gates,
            "saturation": saturation,
            "contract": contract,
            "harness": harness,
        },
        "priorities": priorities,
        "recommended_next_artifacts": [
            f"reports/{engine_name}-telemetry-audit.json",
            f"reports/{engine_name}-metric-coverage.json",
            f"reports/{engine_name}-contract-check.json",
            f"reports/{engine_name}-provider-contract-matrix.json",
            f"reports/{engine_name}-matrix-gate.json",
            f"reports/{engine_name}-matrix-saturation.json",
            f"reports/{engine_name}-harness-review.json",
        ],
        "safety": {
            "contacts_providers": False,
            "executes_benchmarks": False,
            "resolves_secrets": False,
            "reads_raw_traces": False,
            "reads_keyring_values": False,
        },
    }


def write_engine_improvement_advisory(report: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def format_engine_improvement_advisory(report: dict[str, Any]) -> str:
    lines = [
        "AgentBlaster engine improvement advisory",
        f"engine: {report['engine']}",
        f"priority_count: {report['summary']['priority_count']}",
        f"evidence_artifacts: {report['summary']['evidence_artifacts']}",
        "priorities:",
    ]
    if not report["priorities"]:
        lines.append("- none")
    for item in report["priorities"]:
        actions = "; ".join(item["recommended_actions"])
        lines.append(f"- P{item['priority']} {item['area']}: {item['reason']}")
        lines.append(f"  actions: {actions}")
    return "\n".join(lines) + "\n"


def _pressure_summary(engine: str, audits: list[dict[str, Any]]) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    for audit in audits:
        for run in audit.get("runs", []):
            if isinstance(run, dict) and run.get("engine") == engine:
                runs.append(run)
    max_concurrency = max((int(run.get("concurrency") or 1) for run in runs), default=0)
    surfaces: dict[str, int] = {}
    for run in runs:
        for surface, count in (run.get("surfaces") or {}).items():
            surfaces[str(surface)] = surfaces.get(str(surface), 0) + int(count or 0)
    weighted_pressure = sum(int(run.get("concurrency_weighted_pressure_score") or 0) for run in runs)
    static_prefix_tokens = sum(int(run.get("static_prefix_tokens") or 0) for run in runs)
    shared_prefix_tokens = sum(int(run.get("shared_static_prefix_tokens") or 0) for run in runs)
    shared_reuse_tokens = sum(int(run.get("shared_static_reuse_tokens") or 0) for run in runs)
    return {
        "audit_count": len(audits),
        "matching_runs": len(runs),
        "weighted_pressure": weighted_pressure,
        "static_prefix_tokens": static_prefix_tokens,
        "shared_static_prefix_tokens": shared_prefix_tokens,
        "shared_static_reuse_tokens": shared_reuse_tokens,
        "max_concurrency": max_concurrency,
        "surfaces": dict(sorted(surfaces.items())),
        "highest_runs": sorted(
            [
                {
                    "suite": run.get("suite"),
                    "model": run.get("model"),
                    "concurrency": run.get("concurrency"),
                    "weighted_pressure": run.get("concurrency_weighted_pressure_score"),
                    "prefill_level": run.get("prefill_pressure_level"),
                    "shared_static_reuse_tokens": run.get("shared_static_reuse_tokens"),
                }
                for run in runs
            ],
            key=lambda item: int(item.get("weighted_pressure") or 0),
            reverse=True,
        )[:5],
    }


def _telemetry_summary(audits: list[dict[str, Any]]) -> dict[str, Any]:
    weak_fields: dict[str, float] = {}
    advisory_fields: set[str] = set()
    unknown_quality_fields: set[str] = set()
    guidance: set[str] = set()
    blocker_count = 0
    for audit in audits:
        for finding in audit.get("findings", []):
            if isinstance(finding, dict) and finding.get("severity") == "blocker":
                blocker_count += 1
        for field in audit.get("fields", []):
            if not isinstance(field, dict):
                continue
            name = str(field.get("field") or "")
            completeness = float(field.get("completeness") or 0.0)
            if name in KEY_TELEMETRY_FIELDS and completeness < 1.0:
                weak_fields[name] = min(weak_fields.get(name, 1.0), completeness)
        readiness = audit.get("comparison_readiness")
        if isinstance(readiness, dict):
            for name in readiness.get("required_advisory_fields") or readiness.get("advisory_fields") or []:
                if name in KEY_TELEMETRY_FIELDS:
                    advisory_fields.add(str(name))
            for name in readiness.get("required_unknown_quality_fields") or readiness.get("unknown_quality_fields") or []:
                if name in KEY_TELEMETRY_FIELDS:
                    unknown_quality_fields.add(str(name))
            if readiness.get("guidance"):
                guidance.add(str(readiness["guidance"]))
    return {
        "audit_count": len(audits),
        "blocker_count": blocker_count,
        "weak_key_fields": dict(sorted(weak_fields.items())),
        "advisory_key_fields": sorted(advisory_fields),
        "unknown_quality_key_fields": sorted(unknown_quality_fields),
        "comparison_readiness_guidance": sorted(guidance),
    }


def _metric_coverage_summary(reports: list[dict[str, Any]]) -> dict[str, Any]:
    weak_fields: dict[str, set[str]] = {}
    coverage_scores = []
    claim_contract_present = 0
    claim_status_counts: dict[str, int] = {}
    leaderboard_groups: set[str] = set()
    disclosure_groups: set[str] = set()
    primary_score_policies: set[str] = set()
    for report in reports:
        summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
        if "coverage_score" in summary:
            coverage_scores.append(float(summary["coverage_score"]))
        claim_contract = report.get("claim_contract") if isinstance(report.get("claim_contract"), dict) else {}
        if claim_contract:
            claim_contract_present += 1
            _add_int_counts(claim_status_counts, claim_contract.get("claim_status_counts"))
            for group in claim_contract.get("leaderboard_eligible_groups", []):
                leaderboard_groups.add(str(group))
            for group in claim_contract.get("disclosure_required_groups", []):
                disclosure_groups.add(str(group))
            if claim_contract.get("primary_score_policy"):
                primary_score_policies.add(str(claim_contract["primary_score_policy"]))
        for field in report.get("fields", []):
            if not isinstance(field, dict):
                continue
            name = str(field.get("field") or "")
            status = str(field.get("status") or "")
            if name in KEY_TELEMETRY_FIELDS and status in {"unavailable", "conditional", "inferred"}:
                weak_fields.setdefault(name, set()).add(status)
    return {
        "report_count": len(reports),
        "average_coverage_score": round(sum(coverage_scores) / len(coverage_scores), 4) if coverage_scores else None,
        "weak_key_fields": {field: sorted(statuses) for field, statuses in sorted(weak_fields.items())},
        "claim_contract_present_count": claim_contract_present,
        "claim_status_counts": dict(sorted(claim_status_counts.items())),
        "leaderboard_eligible_groups": sorted(leaderboard_groups),
        "disclosure_required_groups": sorted(disclosure_groups),
        "primary_score_policies": sorted(primary_score_policies),
    }


def _gate_summary(matrix_gates: list[dict[str, Any]], comparison_gates: list[dict[str, Any]]) -> dict[str, Any]:
    failed = []
    failure_class_counts: dict[str, int] = {}
    failure_class_artifacts_missing = 0
    failure_class_gate_findings: list[dict[str, Any]] = []
    tool_loop_stop_counts: dict[str, int] = {}
    tool_loop_artifacts_missing = 0
    invalid_tool_call_count = 0
    tool_parser_repair_cases = 0
    tool_parser_repairs_valid = 0
    tool_parser_repair_artifacts_missing = 0
    tool_parser_repair_gate_findings: list[dict[str, Any]] = []
    invalid_matrix_gates: list[dict[str, Any]] = []
    for gate in matrix_gates:
        schema = gate.get("schema_version") or gate.get("schema")
        if _looks_like_matrix_gate(gate) and schema != MATRIX_GATE_SCHEMA_VERSION:
            invalid_matrix_gates.append(
                {
                    "matrix_name": gate.get("matrix_name"),
                    "schema": schema,
                    "expected_schema": MATRIX_GATE_SCHEMA_VERSION,
                    "ok": gate.get("ok"),
                }
            )
            failed.append(
                {
                    "type": "matrix",
                    "name": gate.get("matrix_name"),
                    "findings": [
                        {
                            "metric": "matrix_gate_schema",
                            "actual": schema or "none",
                            "threshold": MATRIX_GATE_SCHEMA_VERSION,
                        }
                    ],
                }
            )
            continue
        findings = [finding for finding in gate.get("findings", []) if isinstance(finding, dict)]
        for item in gate.get("failure_class_summary", []):
            if not isinstance(item, dict):
                continue
            failure_class = str(item.get("failure_class") or "unclassified")
            try:
                count = int(item.get("count") or 0)
            except (TypeError, ValueError):
                count = 0
            if count:
                failure_class_counts[failure_class] = failure_class_counts.get(failure_class, 0) + count
        try:
            missing_artifacts = int(gate.get("failure_class_artifacts_missing") or 0)
        except (TypeError, ValueError):
            missing_artifacts = 0
        if missing_artifacts > 0:
            failure_class_artifacts_missing += missing_artifacts
        for item in gate.get("tool_loop_stop_summary", []):
            if not isinstance(item, dict):
                continue
            stop_reason = str(item.get("stop_reason") or item.get("reason") or "unknown")
            try:
                count = int(item.get("count") or 0)
            except (TypeError, ValueError):
                count = 0
            if count:
                tool_loop_stop_counts[stop_reason] = tool_loop_stop_counts.get(stop_reason, 0) + count
        try:
            missing_tool_loop_artifacts = int(gate.get("tool_loop_artifacts_missing") or 0)
        except (TypeError, ValueError):
            missing_tool_loop_artifacts = 0
        if missing_tool_loop_artifacts > 0:
            tool_loop_artifacts_missing += missing_tool_loop_artifacts
        try:
            invalid_tool_call_count += int(gate.get("invalid_tool_call_count") or 0)
        except (TypeError, ValueError):
            invalid_tool_call_count += 0
        try:
            tool_parser_repair_cases += int(gate.get("tool_parser_repair_cases") or 0)
        except (TypeError, ValueError):
            tool_parser_repair_cases += 0
        try:
            tool_parser_repairs_valid += int(gate.get("tool_parser_repairs_valid") or 0)
        except (TypeError, ValueError):
            tool_parser_repairs_valid += 0
        try:
            missing_tool_parser_artifacts = int(gate.get("tool_parser_repair_artifacts_missing") or 0)
        except (TypeError, ValueError):
            missing_tool_parser_artifacts = 0
        if missing_tool_parser_artifacts > 0:
            tool_parser_repair_artifacts_missing += missing_tool_parser_artifacts
        for finding in findings:
            metric = str(finding.get("metric") or "")
            if metric.startswith("failure_class."):
                failure_class_gate_findings.append(
                    {
                        "matrix_name": gate.get("matrix_name"),
                        "metric": metric,
                        "failure_class": metric.split(".", 1)[1] or "unclassified",
                        "actual": finding.get("actual"),
                        "threshold": finding.get("threshold"),
                    }
                )
            if metric in {
                "invalid_tool_calls",
                "tool_parser_repair_valid_rate",
                "tool_parser_repair_result_artifacts_missing",
            }:
                tool_parser_repair_gate_findings.append(
                    {
                        "matrix_name": gate.get("matrix_name"),
                        "metric": metric,
                        "actual": finding.get("actual"),
                        "threshold": finding.get("threshold"),
                    }
                )
        if gate.get("ok") is not True:
            failed.append({"type": "matrix", "name": gate.get("matrix_name"), "findings": findings})
    for gate in comparison_gates:
        if gate.get("ok") is not True:
            failed.append({"type": "comparison", "findings": gate.get("findings", [])})
    return {
        "matrix_gate_count": len(matrix_gates),
        "comparison_gate_count": len(comparison_gates),
        "failed_gate_count": len(failed),
        "failed_gates": failed,
        "failure_class_summary": [
            {"failure_class": key, "count": value}
            for key, value in sorted(failure_class_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "failure_class_gate_count": len(failure_class_gate_findings),
        "failure_class_gate_findings": failure_class_gate_findings[:12],
        "failure_class_artifacts_missing": failure_class_artifacts_missing,
        "tool_loop_stop_summary": [
            {"stop_reason": key, "count": value}
            for key, value in sorted(tool_loop_stop_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "tool_loop_artifacts_missing": tool_loop_artifacts_missing,
        "invalid_tool_call_count": invalid_tool_call_count,
        "tool_parser_repair_cases": tool_parser_repair_cases,
        "tool_parser_repairs_valid": tool_parser_repairs_valid,
        "tool_parser_repair_valid_rate_percent": (
            round((tool_parser_repairs_valid / tool_parser_repair_cases) * 100, 3)
            if tool_parser_repair_cases
            else 0.0
        ),
        "tool_parser_repair_gate_count": len(tool_parser_repair_gate_findings),
        "tool_parser_repair_gate_findings": tool_parser_repair_gate_findings[:12],
        "tool_parser_repair_artifacts_missing": tool_parser_repair_artifacts_missing,
        "invalid_matrix_gate_count": len(invalid_matrix_gates),
        "invalid_matrix_gates": invalid_matrix_gates[:12],
    }


def _looks_like_matrix_gate(payload: dict[str, Any]) -> bool:
    if payload.get("schema_version") == MATRIX_GATE_SCHEMA_VERSION or payload.get("schema") == MATRIX_GATE_SCHEMA_VERSION:
        return True
    return "matrix_name" in payload and "findings" in payload and (
        "thresholds" in payload
        or "failure_class_summary" in payload
        or "tool_loop_stop_summary" in payload
        or "pass_rate_percent" in payload
    )


def _harness_summary(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    invalid_reviews: list[dict[str, Any]] = []
    review_statuses: dict[str, int] = {}
    generator_profiles: dict[str, int] = {}
    surface_counts: dict[str, int] = {}
    assertion_counts: dict[str, int] = {}
    generated_count = 0
    calibration_required_count = 0
    human_review_required_count = 0
    valid_count = 0
    for review in reviews:
        schema = review.get("schema_version") or review.get("schema")
        if _looks_like_harness_review(review) and schema != HARNESS_REVIEW_SCHEMA_VERSION:
            invalid_reviews.append(
                {
                    "suite_name": _harness_suite_name(review),
                    "schema": schema,
                    "expected_schema": HARNESS_REVIEW_SCHEMA_VERSION,
                }
            )
            continue
        if not _looks_like_harness_review(review):
            continue
        valid_count += 1
        if review.get("generated") is True:
            generated_count += 1
        review_block = review.get("review") if isinstance(review.get("review"), dict) else {}
        status = str(review_block.get("status") or "unknown")
        review_statuses[status] = review_statuses.get(status, 0) + 1
        if review_block.get("calibration_required_before_release_gate") is True:
            calibration_required_count += 1
        if review_block.get("human_review_required") is True:
            human_review_required_count += 1
        generator = review.get("generator") if isinstance(review.get("generator"), dict) else {}
        profile = str(generator.get("profile") or "unknown")
        generator_profiles[profile] = generator_profiles.get(profile, 0) + 1
        _add_int_counts(surface_counts, review.get("surface_counts"))
        _add_int_counts(assertion_counts, review.get("assertion_counts"))
    return {
        "harness_review_count": len(reviews),
        "valid_harness_review_count": valid_count,
        "invalid_harness_review_count": len(invalid_reviews),
        "invalid_harness_reviews": invalid_reviews[:12],
        "generated_review_count": generated_count,
        "calibration_required_count": calibration_required_count,
        "human_review_required_count": human_review_required_count,
        "review_statuses": dict(sorted(review_statuses.items())),
        "generator_profiles": dict(sorted(generator_profiles.items())),
        "surface_counts": dict(sorted(surface_counts.items())),
        "assertion_counts": dict(sorted(assertion_counts.items())),
    }


def _looks_like_harness_review(payload: dict[str, Any]) -> bool:
    if payload.get("schema_version") == HARNESS_REVIEW_SCHEMA_VERSION or payload.get("schema") == HARNESS_REVIEW_SCHEMA_VERSION:
        return True
    return "review" in payload and ("surface_counts" in payload or "assertion_counts" in payload or "generator" in payload)


def _harness_suite_name(payload: dict[str, Any]) -> Any:
    suite = payload.get("suite")
    if isinstance(suite, dict):
        return suite.get("name")
    return None


def _add_int_counts(target: dict[str, int], value: Any) -> None:
    if not isinstance(value, dict):
        return
    for key, raw_count in value.items():
        try:
            count = int(raw_count or 0)
        except (TypeError, ValueError):
            count = 0
        if count > 0:
            label = str(key)
            target[label] = target.get(label, 0) + count


def _saturation_summary(engine: str, reports: list[dict[str, Any]]) -> dict[str, Any]:
    matching_entries: list[dict[str, Any]] = []
    matching_group_ids: set[str] = set()
    guidance: set[str] = set()
    evidence_queue_entries: list[dict[str, Any]] = []
    evidence_rate_limit_entries: list[dict[str, Any]] = []
    for report in reports:
        evidence = report.get("concurrency_evidence") if isinstance(report.get("concurrency_evidence"), dict) else {}
        if evidence.get("guidance"):
            guidance.add(str(evidence["guidance"]))
        evidence_queue_entries.extend(
            item
            for item in evidence.get("highest_queue_wait_entries", [])
            if isinstance(item, dict) and item.get("engine") == engine
        )
        evidence_rate_limit_entries.extend(
            item
            for item in evidence.get("highest_rate_limit_wait_entries", [])
            if isinstance(item, dict) and item.get("engine") == engine
        )
        for entry in report.get("entries", []):
            if isinstance(entry, dict) and entry.get("engine") == engine:
                matching_entries.append(entry)
                if entry.get("group_id"):
                    matching_group_ids.add(str(entry["group_id"]))
        for group in report.get("groups", []):
            if isinstance(group, dict) and group.get("engine") == engine and group.get("group_id"):
                matching_group_ids.add(str(group["group_id"]))

    matching_findings: list[dict[str, Any]] = []
    for report in reports:
        for finding in report.get("findings", []):
            if not isinstance(finding, dict):
                continue
            group_id = str(finding.get("group_id") or "")
            if group_id in matching_group_ids or group_id.startswith(f"{engine}/"):
                matching_findings.append(finding)

    category_counts: dict[str, int] = {}
    for finding in matching_findings:
        category = str(finding.get("category") or "unspecified")
        category_counts[category] = category_counts.get(category, 0) + 1

    return {
        "report_count": len(reports),
        "matching_entries": len(matching_entries),
        "matching_groups": len(matching_group_ids),
        "max_observed_concurrency": max((int(entry.get("concurrency") or 1) for entry in matching_entries), default=0),
        "max_avg_queue_ms": _max_numeric(entry.get("avg_queue_ms") for entry in matching_entries),
        "max_avg_rate_limit_wait_ms": _max_numeric(entry.get("avg_rate_limit_wait_ms") for entry in matching_entries),
        "min_avg_decode_tokens_per_second": _min_numeric(entry.get("avg_decode_tokens_per_second") for entry in matching_entries),
        "concurrency_evidence_guidance": sorted(guidance),
        "highest_queue_wait_entries": _compact_saturation_entries(evidence_queue_entries),
        "highest_rate_limit_wait_entries": _compact_saturation_entries(evidence_rate_limit_entries),
        "finding_count": len(matching_findings),
        "error_findings": sum(1 for finding in matching_findings if finding.get("severity") == "error"),
        "warning_findings": sum(1 for finding in matching_findings if finding.get("severity") == "warning"),
        "finding_categories": dict(sorted(category_counts.items())),
        "top_findings": [
            {
                "severity": finding.get("severity"),
                "category": finding.get("category"),
                "group_id": finding.get("group_id"),
                "concurrency": finding.get("concurrency"),
                "message": finding.get("message"),
            }
            for finding in matching_findings[:8]
        ],
    }


def _compact_saturation_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact = []
    for item in entries:
        compact.append(
            {
                "group_id": item.get("group_id"),
                "run_id": item.get("run_id"),
                "provider": item.get("provider"),
                "model": item.get("model"),
                "suite": item.get("suite"),
                "concurrency": item.get("concurrency"),
                "rank_metric": item.get("rank_metric"),
                "rank_value": item.get("rank_value"),
            }
        )
    return compact[:5]


def _contract_summary(engine: str, checks: list[dict[str, Any]], matrices: list[dict[str, Any]]) -> dict[str, Any]:
    targets: list[dict[str, Any]] = []
    for report in checks:
        provider = report.get("provider") if isinstance(report.get("provider"), dict) else {}
        if provider.get("name") == engine:
            targets.append(_contract_target_summary("provider-contract-check", report, provider))

    for matrix in matrices:
        for entry in matrix.get("entries", []):
            if isinstance(entry, dict) and entry.get("provider") == engine:
                targets.append(_contract_target_summary("provider-contract-matrix", entry, entry))

    failed_targets = [target for target in targets if target["ok"] is not True and not target["plan_only"]]
    plan_only_targets = [target for target in targets if target["plan_only"]]
    failed_check_ids: dict[str, int] = {}
    failed_capabilities: dict[str, int] = {}
    top_failures: list[dict[str, Any]] = []
    for target in failed_targets:
        for check in target["failed_checks"]:
            check_id = str(check.get("id") or "unknown")
            failed_check_ids[check_id] = failed_check_ids.get(check_id, 0) + 1
            capability = check.get("required_capability")
            if capability:
                capability_name = str(capability)
                failed_capabilities[capability_name] = failed_capabilities.get(capability_name, 0) + 1
            if len(top_failures) < 8:
                top_failures.append(
                    {
                        "source": target["source"],
                        "model": target["model"],
                        "contract": target["contract"],
                        "check_id": check_id,
                        "required_capability": capability,
                        "message": check.get("message"),
                    }
                )

    return {
        "contract_check_count": len(checks),
        "contract_matrix_count": len(matrices),
        "matching_targets": len(targets),
        "executed_targets": sum(1 for target in targets if target["mode"] == "executed"),
        "passed_targets": sum(1 for target in targets if target["ok"] is True),
        "failed_targets": len(failed_targets),
        "plan_only_targets": len(plan_only_targets),
        "failed_check_count": sum(int(target["summary"].get("failed") or 0) for target in failed_targets),
        "skipped_check_count": sum(int(target["summary"].get("skipped") or 0) for target in targets),
        "contracts": sorted({str(target["contract"]) for target in targets if target.get("contract")}),
        "models": sorted({str(target["model"]) for target in targets if target.get("model")}),
        "failed_check_ids": dict(sorted(failed_check_ids.items())),
        "failed_required_capabilities": dict(sorted(failed_capabilities.items())),
        "targets": [
            {
                "source": target["source"],
                "contract": target["contract"],
                "model": target["model"],
                "mode": target["mode"],
                "status": target["status"],
                "ok": target["ok"],
                "planned_checks": target["summary"].get("planned"),
                "passed_checks": target["summary"].get("passed"),
                "failed_checks": target["summary"].get("failed"),
                "skipped_checks": target["summary"].get("skipped"),
                "capability_evidence": _compact_contract_capability_evidence(target.get("capability_evidence")),
                "failed_check_ids": [check.get("id") for check in target["failed_checks"]],
                "suites": target.get("suites", []),
                "concurrency_levels": target.get("concurrency_levels", []),
            }
            for target in targets[:12]
        ],
        "top_failures": top_failures,
    }


def _compact_contract_capability_evidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    directly_checked = value.get("directly_checked")
    proxy_items = value.get("proxy_checked")
    not_covered_items = value.get("not_covered")
    if not isinstance(directly_checked, list):
        directly_checked = []
    if not isinstance(proxy_items, list):
        proxy_items = []
    if not isinstance(not_covered_items, list):
        not_covered_items = []
    proxy_checked = [
        {
            "capability": item.get("capability"),
            "covered_by": item.get("covered_by"),
            "declared": item.get("declared"),
            "covered_by_declared": item.get("covered_by_declared"),
        }
        for item in proxy_items
        if isinstance(item, dict)
    ]
    not_covered = [
        {
            "capability": item.get("capability"),
            "declared": item.get("declared"),
        }
        for item in not_covered_items
        if isinstance(item, dict)
    ]
    return {
        "directly_checked": [str(item) for item in directly_checked],
        "proxy_checked": proxy_checked,
        "not_covered": not_covered,
    }


def _contract_target_summary(source: str, payload: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any]:
    mode = str(payload.get("mode") or "unknown")
    status = str(payload.get("status") or ("passed" if payload.get("ok") is True else mode))
    checks = [check for check in payload.get("checks", []) if isinstance(check, dict)]
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    failed_checks = [
        {
            "id": check.get("id"),
            "title": check.get("title"),
            "status": check.get("status"),
            "required_capability": check.get("required_capability"),
            "message": check.get("message"),
        }
        for check in checks
        if check.get("status") == "failed" or check.get("ok") is False
    ]
    summary_counts = {
        "planned": int(summary.get("planned") or len(checks)),
        "passed": int(summary.get("passed") or sum(1 for check in checks if check.get("status") == "passed")),
        "failed": int(summary.get("failed") or len(failed_checks)),
        "skipped": int(summary.get("skipped") or sum(1 for check in checks if check.get("status") == "skipped")),
    }
    return {
        "source": source,
        "provider": identity.get("name") or identity.get("provider"),
        "contract": identity.get("contract"),
        "model": payload.get("model"),
        "mode": mode,
        "status": status,
        "capability_evidence": payload.get("capability_evidence") if isinstance(payload.get("capability_evidence"), dict) else {},
        "ok": payload.get("ok"),
        "summary": summary_counts,
        "failed_checks": failed_checks,
        "plan_only": mode == "plan-only" or status == "planned",
        "suites": payload.get("suites") if isinstance(payload.get("suites"), list) else [],
        "concurrency_levels": payload.get("concurrency_levels") if isinstance(payload.get("concurrency_levels"), list) else [],
    }


def _priorities(
    engine: str,
    pressure: dict[str, Any],
    telemetry: dict[str, Any],
    metrics: dict[str, Any],
    gates: dict[str, Any],
    saturation: dict[str, Any],
    contract: dict[str, Any],
    harness: dict[str, Any],
) -> list[dict[str, Any]]:
    priorities: list[dict[str, Any]] = []
    if pressure["weighted_pressure"] >= 8000 or pressure["static_prefix_tokens"] >= 2500:
        priorities.append(
            _priority(
                1,
                "prefill-cache",
                f"{engine} has high static prompt pressure ({pressure['static_prefix_tokens']} static tokens, {pressure['shared_static_prefix_tokens']} repeated shared-prefix tokens, {pressure['shared_static_reuse_tokens']} potential cache-reuse tokens).",
                ["Improve prefix-cache hit reporting and reuse.", "Optimize system/tool/MCP/skill prefill paths.", "Track shared_static_reuse_tokens in pressure audits before and after cache changes.", "Run cache-control and prefill suites before publishing gains."],
                ["prefill", "cache-control", "matrix pressure-audit"],
            )
        )
    if pressure["max_concurrency"] >= 4:
        priorities.append(
            _priority(
                1,
                "scheduler-concurrency",
                f"{engine} appears in matrix entries up to concurrency {pressure['max_concurrency']}.",
                ["Measure queue_ms and rate_limit_wait_ms under fan-out.", "Tune request scheduling and cancellation isolation.", "Use agent-fanout plus stress matrices for regression tracking."],
                ["agent-fanout", "cancellation", "matrix gate"],
            )
        )
    if saturation["finding_count"]:
        categories = ", ".join(saturation["finding_categories"].keys())
        priorities.append(
            _priority(
                1 if saturation["error_findings"] else 2,
                "measured-saturation",
                f"{engine} has executed matrix saturation findings across concurrency levels: {categories}.",
                [
                    "Profile scheduler queueing and rate-limit wait under the exact failing concurrency levels.",
                    "Separate prompt-prefill bottlenecks from decode throughput collapse using normalized TTFT, prompt_eval, and decode metrics.",
                    "Rerun saturation-report after engine scheduler, cache, or batching fixes.",
                ],
                ["matrix saturation-report", "agent-fanout", "prefill", "cache-control"],
            )
        )
    if contract["failed_targets"] or contract["plan_only_targets"]:
        failed_ids = ", ".join(contract["failed_check_ids"].keys())
        if contract["failed_targets"]:
            reason = f"{engine} has {contract['failed_targets']} provider contract target(s) that did not pass"
            if failed_ids:
                reason += f" ({failed_ids})"
            reason += "."
        else:
            reason = f"{engine} has only plan-only provider contract evidence for {contract['plan_only_targets']} target(s)."
        priorities.append(
            _priority(
                1 if contract["failed_targets"] else 2,
                "contract-conformance",
                reason,
                [
                    "Fix OpenAI, Responses, or Anthropic compatibility gaps before publishing benchmark claims.",
                    "Map failed streaming, structured-output, and tool-call checks to explicit provider capabilities.",
                    "Run provider contract checks or matrix contract-checks with execution enabled after adapter fixes.",
                ],
                ["providers contract-check", "matrix contract-checks", "provider readiness"],
            )
        )
    weak_telemetry = sorted(
        set(telemetry["weak_key_fields"])
        | set(telemetry["advisory_key_fields"])
        | set(telemetry["unknown_quality_key_fields"])
        | set(metrics["weak_key_fields"])
    )
    if weak_telemetry:
        priorities.append(
            _priority(
                2,
                "telemetry-instrumentation",
                "Key normalized telemetry fields are missing, inferred, conditional, or incomplete: " + ", ".join(weak_telemetry[:12]) + ".",
                ["Expose native prompt/decode timings and cache counters.", "Map response stats into OpenAI-compatible usage/stats payloads.", "Require telemetry-audit before scorecard publication."],
                ["metric-coverage", "telemetry-audit", "normalize-telemetry"],
            )
        )
    if metrics["report_count"] and (metrics["disclosure_required_groups"] or not metrics["leaderboard_eligible_groups"]):
        if metrics["leaderboard_eligible_groups"]:
            reason = (
                "Metric claim contracts require disclosure before publication for: "
                + ", ".join(metrics["disclosure_required_groups"][:8])
                + "."
            )
            priority = 2
        else:
            reason = "Metric claim contracts do not mark any metric family as leaderboard-eligible for this engine evidence set."
            priority = 1
        priorities.append(
            _priority(
                priority,
                "publishable-stats",
                reason,
                [
                    "Do not rank AFM on advisory, limited, or unsupported metric families without explicit disclosure.",
                    "Promote timing/cache fields from inferred or conditional to native/measured evidence before media scorecards.",
                    "Keep metric-coverage claim_contract artifacts beside telemetry-audit evidence in release packets.",
                ],
                ["metric-coverage", "telemetry-audit", "matrix-scorecard", "publication brief"],
            )
        )
    if gates["failed_gate_count"]:
        priorities.append(
            _priority(
                1,
                "benchmark-reliability",
                f"{gates['failed_gate_count']} supplied gate artifact(s) did not pass.",
                ["Triage failing matrix/comparison gate findings.", "Separate correctness failures from performance regressions.", "Rerun affected suites after engine fixes."],
                ["matrix gate", "compare-gate", "claim-readiness"],
            )
        )
    if gates["invalid_matrix_gate_count"]:
        priorities.append(
            _priority(
                1,
                "evidence-integrity",
                f"{gates['invalid_matrix_gate_count']} supplied matrix gate artifact(s) are missing schema {MATRIX_GATE_SCHEMA_VERSION}.",
                [
                    "Regenerate matrix gates with the current AgentBlaster CLI before using them for AFM roadmap decisions.",
                    "Reject stale or hand-written gate artifacts in release and publication evidence bundles.",
                    "Keep advisory, dashboard, release qualification, and claim-readiness evidence on the same artifact schema.",
                ],
                ["matrix gate", "artifact schema registry", "release qualification"],
            )
        )
    if gates["failure_class_artifacts_missing"]:
        priorities.append(
            _priority(
                2,
                "evidence-integrity",
                f"{gates['failure_class_artifacts_missing']} matrix run result artifact(s) were missing from failure-class evidence.",
                [
                    "Regenerate matrix summaries with readable result paths before interpreting failure-class counts.",
                    "Treat missing class evidence as a review gap even when aggregate matrix thresholds pass.",
                    "Keep result artifact retention aligned with release qualification and dashboard review needs.",
                ],
                ["matrix gate", "release qualification", "dashboard review artifacts"],
            )
        )
    if gates["tool_loop_artifacts_missing"]:
        priorities.append(
            _priority(
                2,
                "evidence-integrity",
                f"{gates['tool_loop_artifacts_missing']} matrix run result artifact(s) were missing from tool-loop stop-reason evidence.",
                [
                    "Regenerate matrix summaries with readable result paths before interpreting bounded tool-loop behavior.",
                    "Treat missing tool-loop evidence as a review gap for MCP, LCP, and multi-tool agentic workloads.",
                ],
                ["matrix gate", "release qualification", "dashboard review artifacts"],
            )
        )
    if gates["tool_parser_repair_artifacts_missing"]:
        priorities.append(
            _priority(
                2,
                "evidence-integrity",
                (
                    f"{gates['tool_parser_repair_artifacts_missing']} matrix run result artifact(s) were missing "
                    "from tool-parser repair evidence."
                ),
                [
                    "Regenerate matrix summaries with readable result paths before interpreting parser-repair behavior.",
                    "Treat missing parser-repair evidence as a review gap for local-agent tool-call comparisons.",
                    "Keep result artifact retention aligned with parser-repair release gates and dashboard review needs.",
                ],
                ["matrix gate", "tool-parser-repair suite", "release qualification"],
            )
        )
    problematic_tool_loop_stops = [
        item
        for item in gates["tool_loop_stop_summary"]
        if str(item.get("stop_reason") or item.get("reason") or "unknown")
        not in {"completed", "none", "not_applicable", "no_tool_loop"}
    ]
    if problematic_tool_loop_stops:
        stop_text = ", ".join(
            f"{item.get('stop_reason') or item.get('reason') or 'unknown'}={item.get('count', 0)}"
            for item in problematic_tool_loop_stops[:8]
        )
        priorities.append(
            _priority(
                2,
                "agentic-loop-control",
                f"Matrix gates reported bounded tool-loop stop reasons that need AFM review: {stop_text}.",
                [
                    "Inspect scheduler, tool-call continuation, and API message-replay handling for multi-step agentic cases.",
                    "Prioritize max-tool-call, stalled-loop, and tool-result continuation failures before tuning model prompts.",
                    "Keep stop-reason thresholds in matrix gates so loop-control regressions block release even when aggregate pass rate is high.",
                ],
                ["matrix gate", "tool-loop harness", "MCP/LCP agentic suites"],
            )
        )
    parser_repair_invalid = int(gates.get("invalid_tool_call_count") or 0)
    parser_repair_cases = int(gates.get("tool_parser_repair_cases") or 0)
    parser_repairs_valid = int(gates.get("tool_parser_repairs_valid") or 0)
    parser_repair_failures = max(parser_repair_cases - parser_repairs_valid, 0)
    if gates["tool_parser_repair_gate_count"] or parser_repair_invalid or parser_repair_failures:
        priorities.append(
            _priority(
                1 if gates["tool_parser_repair_gate_count"] else 2,
                "agentic-protocol-repair",
                (
                    f"Matrix gates reported {parser_repair_invalid} invalid tool-call emission(s) and "
                    f"{parser_repairs_valid}/{parser_repair_cases} valid parser-repair cases."
                ),
                [
                    "Prioritize malformed OpenAI/Anthropic tool-call emission fixes before model-quality tuning.",
                    "Harden parser repair for malformed JSON, wrong argument shapes, and mixed content/tool-call envelopes.",
                    "Keep tool-parser-repair matrix gates blocking release until invalid tool calls return to zero.",
                ],
                ["matrix gate", "tool-parser-repair suite", "provider adapter", "agentic harness"],
            )
        )
    if gates["failure_class_gate_count"] or gates["failure_class_summary"]:
        class_text = ", ".join(
            f"{item['failure_class']}={item['count']}" for item in gates["failure_class_summary"][:8]
        ) or "class-specific gate findings"
        priorities.append(
            _priority(
                1 if gates["failure_class_gate_count"] else 2,
                "failure-taxonomy-remediation",
                f"{engine} has failure-class evidence from matrix gates: {class_text}.",
                [
                    "Triage engine_protocol_bug and engine_feature_gap separately from model_quality failures.",
                    "Map class-specific gate findings to adapter, scheduler, runtime, or harness ownership.",
                    "Keep release gates on critical failure classes until the class-specific counts return to zero.",
                ],
                ["matrix gate", "failure taxonomy", "provider contract checks"],
            )
        )
    if harness["invalid_harness_review_count"]:
        priorities.append(
            _priority(
                1,
                "evidence-integrity",
                f"{harness['invalid_harness_review_count']} supplied harness-review artifact(s) are missing schema {HARNESS_REVIEW_SCHEMA_VERSION}.",
                [
                    "Regenerate harness-review artifacts with the current AgentBlaster CLI before using generated suites for AFM roadmap decisions.",
                    "Reject stale or hand-written harness-review artifacts in release and advisory evidence.",
                    "Keep harness review, claim readiness, dashboard, and release qualification evidence on the same artifact schema.",
                ],
                ["harness review", "artifact schema registry", "release qualification"],
            )
        )
    if harness["calibration_required_count"] or harness["human_review_required_count"]:
        review_gap_count = max(harness["calibration_required_count"], harness["human_review_required_count"])
        profiles = ", ".join(
            f"{profile}={count}" for profile, count in sorted(harness["generator_profiles"].items())[:8]
        ) or "generated harness profiles"
        priorities.append(
            _priority(
                2,
                "harness-calibration",
                (
                    f"{review_gap_count} generated harness-review artifact(s) still require "
                    f"calibration or human review before release-gate use: {profiles}."
                ),
                [
                    "Complete suite calibration before using generated harness suites as release gates.",
                    "Separate engine regressions from benchmark-method instability when generated suites fail.",
                    "Track orchestration, contract-fuzz, cache-replay, and metamorphic harness evidence as reviewable inputs, not raw score claims.",
                ],
                ["harness review", "suite-calibration", "claim-readiness"],
            )
        )
    if not priorities:
        priorities.append(
            _priority(
                3,
                "evidence-completeness",
                "No high-priority gaps were detected from supplied static artifacts.",
                ["Add provider contract checks, telemetry audits, matrix pressure audits, metric coverage, and gate reports to improve advisory precision.", "Keep AFM improvement plans tied to reproducible evidence artifacts."],
                ["campaign-preflight", "release claim-readiness"],
            )
        )
    return sorted(priorities, key=lambda item: item["priority"])


def _priority(priority: int, area: str, reason: str, actions: list[str], suites: list[str]) -> dict[str, Any]:
    return {
        "priority": priority,
        "area": area,
        "reason": reason,
        "recommended_actions": actions,
        "aligned_artifacts_or_suites": suites,
    }


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"invalid advisory input {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConfigError(f"invalid advisory input {path}: root must be an object")
    return payload


def _max_numeric(values) -> float | None:
    numeric = [float(value) for value in values if value is not None]
    return max(numeric) if numeric else None


def _min_numeric(values) -> float | None:
    numeric = [float(value) for value in values if value is not None]
    return min(numeric) if numeric else None
