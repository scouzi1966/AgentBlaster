from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

from agentblaster.engine_advisory import ENGINE_ADVISORY_SCHEMA_VERSION
from agentblaster.evidence_index import EVIDENCE_INDEX_SCHEMA_VERSION
from agentblaster.errors import ConfigError
from agentblaster.harness import HARNESS_REVIEW_SCHEMA_VERSION
from agentblaster.implementation_status import IMPLEMENTATION_STATUS_SCHEMA_VERSION
from agentblaster.matrix_gate import MATRIX_GATE_SCHEMA_VERSION
from agentblaster.metric_coverage import METRIC_COVERAGE_SCHEMA_VERSION
from agentblaster.protocol_repair import PROTOCOL_REPAIR_POSTURE_SCHEMA_VERSION
from agentblaster.provider_audit import PROVIDER_AUDIT_SCHEMA_VERSION
from agentblaster.publication_brief import PUBLICATION_BRIEF_SCHEMA_VERSION
from agentblaster.quality import SDLC_VALIDATION_MANIFEST_SCHEMA_VERSION, SELFTEST_REPORT_SCHEMA_VERSION
from agentblaster.readiness import READINESS_SCHEMA_VERSION
from agentblaster.redaction_scan import REDACTION_SCAN_SCHEMA_VERSION
from agentblaster.security_posture import SECURITY_POSTURE_SCHEMA_VERSION
from agentblaster.suite_audit import SUITE_AUDIT_SCHEMA_VERSION
from agentblaster.suite_calibration import CALIBRATION_REPORT_SCHEMA_VERSION
from agentblaster.workflow_readiness import WORKFLOW_READINESS_SCHEMA_VERSION


CLAIM_READINESS_SCHEMA_VERSION = "agentblaster.claim-readiness.v1"
MAX_RELEASE_BUNDLE_MANIFEST_BYTES = 1_000_000
MAX_PUBLICATION_BUNDLE_MANIFEST_BYTES = 1_000_000
PUBLICATION_BUNDLE_MANIFEST = "publication-bundle-manifest.json"
PUBLICATION_BUNDLE_MANIFEST_SCHEMA_VERSION = "agentblaster.publication-bundle.v1"
MATRIX_PUBLICATION_BUNDLE_MANIFEST = "matrix-publication-bundle-manifest.json"
MATRIX_PUBLICATION_BUNDLE_MANIFEST_SCHEMA_VERSION = "agentblaster.matrix-publication-bundle.v1"
MEDIA_KIT_SCHEMA_VERSION = "agentblaster.media-kit.v1"
MATRIX_SCORECARD_SCHEMA_VERSION = "agentblaster-matrix-scorecard-v1"
NORMALIZED_TELEMETRY_SCHEMA_VERSION = "agentblaster.normalized-telemetry.v1"


def build_claim_readiness(
    *,
    name: str,
    experiment_manifest: Path | None = None,
    experiment_gate: Path | None = None,
    provider_contract_checks: list[Path] | None = None,
    provider_contract_matrices: list[Path] | None = None,
    matrix_gates: list[Path] | None = None,
    comparison_gates: list[Path] | None = None,
    telemetry_audits: list[Path] | None = None,
    matrix_pressure_audits: list[Path] | None = None,
    matrix_saturation_reports: list[Path] | None = None,
    matrix_scorecards: list[Path] | None = None,
    implementation_status_reports: list[Path] | None = None,
    release_provenance: Path | None = None,
    release_qualification_bundle: Path | None = None,
    redaction_scan: Path | None = None,
    publication_bundles: list[Path] | None = None,
    matrix_publication_bundles: list[Path] | None = None,
    protocol_repair_postures: list[Path] | None = None,
    workflow_readiness_reports: list[Path] | None = None,
    security_postures: list[Path] | None = None,
    harness_reviews: list[Path] | None = None,
    suite_calibration_reports: list[Path] | None = None,
    engine_advisories: list[Path] | None = None,
    evidence_indexes: list[Path] | None = None,
    suite_audits: list[Path] | None = None,
    metric_coverage_reports: list[Path] | None = None,
    normalized_telemetry_reports: list[Path] | None = None,
    campaign_preflight_manifest: Path | None = None,
    selftest_reports: list[Path] | None = None,
    benchmark_readiness_reports: list[Path] | None = None,
    provider_audits: list[Path] | None = None,
) -> dict[str, Any]:
    """Evaluate whether a benchmark claim has the expected review evidence."""

    checks = [
        _json_check("experiment_manifest", experiment_manifest, required=True, schema="agentblaster.experiment-manifest.v1"),
        _json_check("experiment_gate", experiment_gate, required=True, schema="agentblaster.experiment-gate.v1", ok_field="passed"),
        _provider_contract_evidence_check(provider_contract_checks or [], provider_contract_matrices or []),
        _matrix_gate_evidence_check(matrix_gates or []),
        _json_list_check("comparison_gates", comparison_gates or [], required=False, ok_field="ok"),
        _json_list_check("telemetry_audits", telemetry_audits or [], required=True, schema="agentblaster.telemetry-audit.v1", ok_path=("summary", "comparable_core_ok")),
        _normalized_telemetry_evidence_check(normalized_telemetry_reports or []),
        _json_list_check("matrix_pressure_audits", matrix_pressure_audits or [], required=True, schema="agentblaster.matrix-pressure-audit.v1"),
        _json_list_check("matrix_saturation_reports", matrix_saturation_reports or [], required=True, schema="agentblaster.matrix-saturation.v1", ok_field="ok"),
        _matrix_scorecard_evidence_check(matrix_scorecards or []),
        _implementation_status_evidence_check(implementation_status_reports or []),
        _json_check("release_provenance", release_provenance, required=True, schema="agentblaster.release-provenance"),
        _zip_check("release_qualification_bundle", release_qualification_bundle, required=True, suffix=".agentblaster-release-qualification.zip"),
        _redaction_scan_check(redaction_scan),
        _publication_bundle_evidence_check(publication_bundles or []),
        _matrix_publication_bundle_evidence_check(matrix_publication_bundles or []),
        _protocol_repair_posture_evidence_check(protocol_repair_postures or []),
        _workflow_readiness_evidence_check(workflow_readiness_reports or []),
        _security_posture_evidence_check(security_postures or []),
        _harness_review_evidence_check(harness_reviews or []),
        _suite_calibration_evidence_check(suite_calibration_reports or []),
        _engine_advisory_evidence_check(engine_advisories or []),
        _evidence_index_evidence_check(evidence_indexes or []),
        _suite_audit_evidence_check(suite_audits or []),
        _metric_coverage_evidence_check(metric_coverage_reports or []),
        _campaign_preflight_evidence_check(campaign_preflight_manifest),
        _selftest_report_evidence_check(selftest_reports or []),
        _benchmark_readiness_evidence_check(benchmark_readiness_reports or []),
        _provider_audit_evidence_check(provider_audits or []),
    ]
    flattened = _flatten_checks(checks)
    flattened.extend(_matrix_scorecard_readiness_checks(flattened))
    flattened.extend(_normalized_telemetry_readiness_checks(flattened))
    blockers = [check for check in flattened if check["severity"] == "blocker" and not check["ok"]]
    warnings = [check for check in flattened if check["severity"] == "warning" and not check["ok"]]
    return {
        "schema_version": CLAIM_READINESS_SCHEMA_VERSION,
        "name": _safe_name(name),
        "ready": not blockers,
        "summary": {
            "checks": len(flattened),
            "passed": sum(1 for check in flattened if check["ok"]),
            "blockers": len(blockers),
            "warnings": len(warnings),
        },
        "evidence": {
            "provider_contract_capability_evidence": _aggregate_contract_capability_evidence(flattened),
            "matrix_gate_failure_class_summary": _aggregate_failure_class_checks(flattened),
            "matrix_gate_failure_class_findings": _collect_failure_class_findings(flattened),
            "matrix_gate_failure_class_artifacts_missing": _sum_failure_class_artifacts_missing(flattened),
            "matrix_gate_tool_loop_stop_summary": _aggregate_tool_loop_stop_checks(flattened),
            "matrix_gate_tool_loop_stop_findings": _collect_tool_loop_stop_findings(flattened),
            "matrix_gate_tool_loop_artifacts_missing": _sum_tool_loop_artifacts_missing(flattened),
            "matrix_gate_judge_verdict_summary": _aggregate_judge_verdict_checks(flattened),
            "matrix_gate_judge_verdict_findings": _collect_judge_verdict_findings(flattened),
            "matrix_gate_judge_verdict_artifacts_missing": _sum_judge_verdict_artifacts_missing(flattened),
            "matrix_gate_tool_parser_repair_summary": _aggregate_tool_parser_repair_checks(flattened),
            "matrix_gate_tool_parser_repair_findings": _collect_tool_parser_repair_findings(flattened),
            "matrix_gate_tool_parser_repair_artifacts_missing": _sum_tool_parser_repair_artifacts_missing(flattened),
            "harness_review_summaries": _collect_harness_review_summaries(flattened),
            "suite_calibration_summaries": _collect_suite_calibration_summaries(flattened),
            "engine_advisory_summaries": _collect_engine_advisory_summaries(flattened),
            "evidence_index_summaries": _collect_evidence_index_summaries(flattened),
            "suite_audit_summaries": _collect_suite_audit_summaries(flattened),
            "metric_coverage_summaries": _collect_metric_coverage_summaries(flattened),
            "normalized_telemetry_summaries": _collect_normalized_telemetry_summaries(flattened),
            "redaction_scan_summaries": _collect_redaction_scan_summaries(flattened),
            "publication_bundle_summaries": _collect_publication_bundle_summaries(flattened),
            "matrix_publication_bundle_summaries": _collect_matrix_publication_bundle_summaries(flattened),
            "protocol_repair_posture_summaries": _collect_protocol_repair_posture_summaries(flattened),
            "workflow_readiness_summaries": _collect_workflow_readiness_summaries(flattened),
            "security_posture_summaries": _collect_security_posture_summaries(flattened),
            "publication_brief_summaries": _collect_publication_brief_summaries(flattened),
            "matrix_scorecard_summaries": _collect_matrix_scorecard_summaries(flattened),
            "implementation_status_summaries": _collect_implementation_status_summaries(flattened),
            "campaign_preflight_summaries": _collect_campaign_preflight_summaries(flattened),
            "selftest_report_summaries": _collect_selftest_report_summaries(flattened),
            "sdlc_validation_manifest_summaries": _collect_sdlc_validation_manifest_summaries(flattened),
            "benchmark_readiness_summaries": _collect_benchmark_readiness_summaries(flattened),
            "provider_audit_summaries": _collect_provider_audit_summaries(flattened),
        },
        "checks": flattened,
        "security_notes": [
            "Claim readiness reads only supplied JSON manifests/gates/audits, release bundle manifest.json, run publication-bundle-manifest.json, and matrix publication-bundle manifest metadata.",
            "It does not open raw traces, resolve secrets, inspect keyrings, or contact providers.",
            "A passing readiness report is not a substitute for rerunning validation before release.",
        ],
    }


def write_claim_readiness_json(report: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def format_claim_readiness(report: dict[str, Any]) -> str:
    lines = [
        "AgentBlaster claim readiness",
        f"name: {report['name']}",
        f"ready: {str(report['ready']).lower()}",
        f"checks: {report['summary']['checks']}",
        f"passed: {report['summary']['passed']}",
        f"blockers: {report['summary']['blockers']}",
        f"warnings: {report['summary']['warnings']}",
    ]
    failure_classes = _failure_class_summary_text(
        report.get("evidence", {}).get("matrix_gate_failure_class_summary", [])
    )
    if failure_classes != "none":
        lines.append(f"matrix_gate_failure_classes: {failure_classes}")
    missing_failure_artifacts = int(report.get("evidence", {}).get("matrix_gate_failure_class_artifacts_missing") or 0)
    if missing_failure_artifacts:
        lines.append(f"matrix_gate_failure_class_artifacts_missing: {missing_failure_artifacts}")
    tool_loop_stops = _tool_loop_stop_summary_text(
        report.get("evidence", {}).get("matrix_gate_tool_loop_stop_summary", [])
    )
    if tool_loop_stops != "none":
        lines.append(f"matrix_gate_tool_loop_stop_reasons: {tool_loop_stops}")
    missing_tool_loop_artifacts = int(report.get("evidence", {}).get("matrix_gate_tool_loop_artifacts_missing") or 0)
    if missing_tool_loop_artifacts:
        lines.append(f"matrix_gate_tool_loop_artifacts_missing: {missing_tool_loop_artifacts}")
    judge_summary = report.get("evidence", {}).get("matrix_gate_judge_verdict_summary", {})
    if isinstance(judge_summary, dict) and judge_summary.get("judge_rubric_cases"):
        lines.append(
            "matrix_gate_judge_verdicts: "
            f"{judge_summary.get('judge_verdicts_valid', 0)}/{judge_summary.get('judge_rubric_cases', 0)} valid "
            f"({judge_summary.get('judge_verdict_valid_rate_percent', 0)}%)"
        )
    missing_judge_artifacts = int(report.get("evidence", {}).get("matrix_gate_judge_verdict_artifacts_missing") or 0)
    if missing_judge_artifacts:
        lines.append(f"matrix_gate_judge_verdict_artifacts_missing: {missing_judge_artifacts}")
    parser_summary = report.get("evidence", {}).get("matrix_gate_tool_parser_repair_summary", {})
    if isinstance(parser_summary, dict) and parser_summary.get("tool_parser_repair_cases"):
        lines.append(
            "matrix_gate_tool_parser_repairs: "
            f"{parser_summary.get('tool_parser_repairs_valid', 0)}/"
            f"{parser_summary.get('tool_parser_repair_cases', 0)} valid "
            f"({parser_summary.get('tool_parser_repair_valid_rate_percent', 0)}%), "
            f"invalid_tools={parser_summary.get('invalid_tool_call_count', 0)}"
        )
    missing_parser_artifacts = int(
        report.get("evidence", {}).get("matrix_gate_tool_parser_repair_artifacts_missing") or 0
    )
    if missing_parser_artifacts:
        lines.append(f"matrix_gate_tool_parser_repair_artifacts_missing: {missing_parser_artifacts}")
    contract_capability_evidence = _contract_capability_evidence_text(
        report.get("evidence", {}).get("provider_contract_capability_evidence", {})
    )
    if contract_capability_evidence != "none":
        lines.append(f"provider_contract_capability_evidence: {contract_capability_evidence}")
    harness_summaries = report.get("evidence", {}).get("harness_review_summaries", [])
    if isinstance(harness_summaries, list) and harness_summaries:
        lines.append(f"harness_reviews: {_harness_summary_text(harness_summaries)}")
    suite_calibration_summaries = report.get("evidence", {}).get("suite_calibration_summaries", [])
    if isinstance(suite_calibration_summaries, list) and suite_calibration_summaries:
        lines.append(f"suite_calibrations: {_suite_calibration_summary_text(suite_calibration_summaries)}")
    engine_summaries = report.get("evidence", {}).get("engine_advisory_summaries", [])
    if isinstance(engine_summaries, list) and engine_summaries:
        lines.append(f"engine_advisories: {_engine_advisory_summary_text(engine_summaries)}")
    evidence_index_summaries = report.get("evidence", {}).get("evidence_index_summaries", [])
    if isinstance(evidence_index_summaries, list) and evidence_index_summaries:
        lines.append(f"evidence_indexes: {_evidence_index_summary_text(evidence_index_summaries)}")
    suite_audit_summaries = report.get("evidence", {}).get("suite_audit_summaries", [])
    if isinstance(suite_audit_summaries, list) and suite_audit_summaries:
        lines.append(f"suite_audits: {_suite_audit_summary_text(suite_audit_summaries)}")
    metric_coverage_summaries = report.get("evidence", {}).get("metric_coverage_summaries", [])
    if isinstance(metric_coverage_summaries, list) and metric_coverage_summaries:
        lines.append(f"metric_coverage: {_metric_coverage_summary_text(metric_coverage_summaries)}")
    normalized_telemetry_summaries = report.get("evidence", {}).get("normalized_telemetry_summaries", [])
    if isinstance(normalized_telemetry_summaries, list) and normalized_telemetry_summaries:
        lines.append(f"normalized_telemetry: {_normalized_telemetry_summary_text(normalized_telemetry_summaries)}")
    redaction_scan_summaries = report.get("evidence", {}).get("redaction_scan_summaries", [])
    if isinstance(redaction_scan_summaries, list) and redaction_scan_summaries:
        lines.append(f"redaction_scan: {_redaction_scan_summary_text(redaction_scan_summaries)}")
    publication_bundle_summaries = report.get("evidence", {}).get("publication_bundle_summaries", [])
    if isinstance(publication_bundle_summaries, list) and publication_bundle_summaries:
        lines.append(f"publication_bundles: {_publication_bundle_summary_text(publication_bundle_summaries)}")
    matrix_publication_bundle_summaries = report.get("evidence", {}).get("matrix_publication_bundle_summaries", [])
    if isinstance(matrix_publication_bundle_summaries, list) and matrix_publication_bundle_summaries:
        lines.append(
            f"matrix_publication_bundles: {_matrix_publication_bundle_summary_text(matrix_publication_bundle_summaries)}"
        )
    protocol_repair_posture_summaries = report.get("evidence", {}).get("protocol_repair_posture_summaries", [])
    if isinstance(protocol_repair_posture_summaries, list) and protocol_repair_posture_summaries:
        lines.append(f"protocol_repair_posture: {_protocol_repair_posture_summary_text(protocol_repair_posture_summaries)}")
    workflow_readiness_summaries = report.get("evidence", {}).get("workflow_readiness_summaries", [])
    if isinstance(workflow_readiness_summaries, list) and workflow_readiness_summaries:
        lines.append(f"workflow_readiness: {_workflow_readiness_summary_text(workflow_readiness_summaries)}")
    security_posture_summaries = report.get("evidence", {}).get("security_posture_summaries", [])
    if isinstance(security_posture_summaries, list) and security_posture_summaries:
        lines.append(f"security_posture: {_security_posture_summary_text(security_posture_summaries)}")
    publication_brief_summaries = report.get("evidence", {}).get("publication_brief_summaries", [])
    if isinstance(publication_brief_summaries, list) and publication_brief_summaries:
        lines.append(f"publication_briefs: {_publication_brief_summary_text(publication_brief_summaries)}")
    matrix_scorecard_summaries = report.get("evidence", {}).get("matrix_scorecard_summaries", [])
    if isinstance(matrix_scorecard_summaries, list) and matrix_scorecard_summaries:
        lines.append(f"matrix_scorecards: {_matrix_scorecard_summary_text(matrix_scorecard_summaries)}")
    implementation_status_summaries = report.get("evidence", {}).get("implementation_status_summaries", [])
    if isinstance(implementation_status_summaries, list) and implementation_status_summaries:
        lines.append(f"implementation_status: {_implementation_status_summary_text(implementation_status_summaries)}")
    campaign_preflight_summaries = report.get("evidence", {}).get("campaign_preflight_summaries", [])
    if isinstance(campaign_preflight_summaries, list) and campaign_preflight_summaries:
        lines.append(f"campaign_preflight: {_campaign_preflight_summary_text(campaign_preflight_summaries)}")
    selftest_summaries = report.get("evidence", {}).get("selftest_report_summaries", [])
    if isinstance(selftest_summaries, list) and selftest_summaries:
        lines.append(f"selftests: {_selftest_summary_text(selftest_summaries)}")
    sdlc_validation_summaries = report.get("evidence", {}).get("sdlc_validation_manifest_summaries", [])
    if isinstance(sdlc_validation_summaries, list) and sdlc_validation_summaries:
        lines.append(f"sdlc_validation: {_sdlc_validation_manifest_summary_text(sdlc_validation_summaries)}")
    benchmark_readiness_summaries = report.get("evidence", {}).get("benchmark_readiness_summaries", [])
    if isinstance(benchmark_readiness_summaries, list) and benchmark_readiness_summaries:
        lines.append(f"benchmark_readiness: {_benchmark_readiness_summary_text(benchmark_readiness_summaries)}")
    provider_audit_summaries = report.get("evidence", {}).get("provider_audit_summaries", [])
    if isinstance(provider_audit_summaries, list) and provider_audit_summaries:
        lines.append(f"provider_audits: {_provider_audit_summary_text(provider_audit_summaries)}")
    for check in report["checks"]:
        status = "PASS" if check["ok"] else check["severity"].upper()
        lines.append(f"- {status} {check['category']}: {check['message']}")
    return "\n".join(lines) + "\n"


def _json_list_check(
    category: str,
    paths: list[Path],
    *,
    required: bool,
    schema: str | None = None,
    ok_field: str | None = None,
    ok_path: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    if not paths:
        return _missing_check(category, required)
    return {
        "category": category,
        "items": [
            _json_check(f"{category}[{index}]", path, required=True, schema=schema, ok_field=ok_field, ok_path=ok_path)
            for index, path in enumerate(paths, start=1)
        ],
    }


def _provider_contract_evidence_check(contract_checks: list[Path], contract_matrices: list[Path]) -> dict[str, Any]:
    if not contract_checks and not contract_matrices:
        return _missing_check("provider_contract_evidence", required=True)
    return {
        "category": "provider_contract_evidence",
        "items": [
            *[
                _provider_contract_artifact_check(
                    f"provider_contract_checks[{index}]",
                    path,
                    schema="agentblaster.provider-contract-check.v1",
                )
                for index, path in enumerate(contract_checks, start=1)
            ],
            *[
                _provider_contract_artifact_check(
                    f"provider_contract_matrices[{index}]",
                    path,
                    schema="agentblaster.provider-contract-matrix.v1",
                )
                for index, path in enumerate(contract_matrices, start=1)
            ],
        ],
    }


def _provider_contract_artifact_check(category: str, path: Path, *, schema: str) -> dict[str, Any]:
    check = _json_check(category, path, required=True, schema=schema, ok_field="ok")
    if not path.exists() or not path.is_file():
        return check
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return check
    if not isinstance(payload, dict):
        return check
    evidence = _contract_capability_summary(payload.get("capability_evidence"))
    if evidence["directly_checked"] or evidence["proxy_checked_counts"] or evidence["not_covered_counts"]:
        check["contract_capability_evidence"] = evidence
    return check


def _aggregate_contract_capability_evidence(checks: list[dict[str, Any]]) -> dict[str, Any]:
    direct: set[str] = set()
    proxy_counts: dict[str, int] = {}
    not_covered_counts: dict[str, int] = {}
    for check in checks:
        evidence = check.get("contract_capability_evidence")
        if not isinstance(evidence, dict):
            continue
        directly_checked = evidence.get("directly_checked")
        if isinstance(directly_checked, list):
            direct.update(str(item) for item in directly_checked)
        _merge_count_map(proxy_counts, evidence.get("proxy_checked_counts"))
        _merge_count_map(not_covered_counts, evidence.get("not_covered_counts"))
    return {
        "directly_checked": sorted(direct),
        "proxy_checked_counts": dict(sorted(proxy_counts.items())),
        "not_covered_counts": dict(sorted(not_covered_counts.items())),
    }


def _contract_capability_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"directly_checked": [], "proxy_checked_counts": {}, "not_covered_counts": {}}
    directly_checked = value.get("directly_checked") if isinstance(value.get("directly_checked"), list) else []
    proxy_counts: dict[str, int] = {}
    not_covered_counts: dict[str, int] = {}
    proxy_count_map = value.get("proxy_checked_counts")
    if isinstance(proxy_count_map, dict):
        _merge_count_map(proxy_counts, proxy_count_map)
    else:
        _count_capability_items(proxy_counts, value.get("proxy_checked"))
    not_covered_count_map = value.get("not_covered_counts")
    if isinstance(not_covered_count_map, dict):
        _merge_count_map(not_covered_counts, not_covered_count_map)
    else:
        _count_capability_items(not_covered_counts, value.get("not_covered"))
    return {
        "directly_checked": sorted({str(item) for item in directly_checked}),
        "proxy_checked_counts": dict(sorted(proxy_counts.items())),
        "not_covered_counts": dict(sorted(not_covered_counts.items())),
    }


def _count_capability_items(counts: dict[str, int], value: Any) -> None:
    if not isinstance(value, list):
        return
    for item in value:
        if isinstance(item, dict) and item.get("capability"):
            capability = str(item["capability"])
            counts[capability] = counts.get(capability, 0) + 1


def _merge_count_map(target: dict[str, int], value: Any) -> None:
    if not isinstance(value, dict):
        return
    for key, count in value.items():
        target[str(key)] = target.get(str(key), 0) + _non_negative_int(count)


def _matrix_gate_evidence_check(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        return _missing_check("matrix_gates", required=True)
    return {
        "category": "matrix_gates",
        "items": [
            _matrix_gate_check(f"matrix_gates[{index}]", path)
            for index, path in enumerate(paths, start=1)
        ],
    }


def _matrix_gate_check(category: str, path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return _check(category, False, "blocker", str(path), f"missing artifact: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _check(category, False, "blocker", str(path), f"invalid JSON artifact: {exc}")
    if not isinstance(payload, dict):
        return _check(category, False, "blocker", str(path), "JSON artifact root must be an object")
    schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema")) if value is not None}
    if MATRIX_GATE_SCHEMA_VERSION not in schema_values:
        found = ", ".join(sorted(schema_values)) if schema_values else "none"
        return _check(category, False, "blocker", str(path), f"expected schema {MATRIX_GATE_SCHEMA_VERSION}, found {found}")
    extras = {
        "schema_version": MATRIX_GATE_SCHEMA_VERSION,
        "failure_class_summary": _normalize_failure_class_summary(payload.get("failure_class_summary")),
        "failure_class_findings": _failure_class_findings(payload.get("findings")),
        "failure_class_artifacts_missing": _non_negative_int(payload.get("failure_class_artifacts_missing")),
        "tool_loop_stop_summary": _normalize_tool_loop_stop_summary(payload.get("tool_loop_stop_summary")),
        "tool_loop_stop_findings": _tool_loop_stop_findings(payload.get("findings")),
        "tool_loop_artifacts_missing": _non_negative_int(payload.get("tool_loop_artifacts_missing")),
        "judge_rubric_cases": _non_negative_int(payload.get("judge_rubric_cases")),
        "judge_verdicts_valid": _non_negative_int(payload.get("judge_verdicts_valid")),
        "judge_verdict_valid_rate_percent": payload.get("judge_verdict_valid_rate_percent"),
        "judge_verdict_findings": _judge_verdict_findings(payload.get("findings")),
        "judge_verdict_artifacts_missing": _non_negative_int(payload.get("judge_verdict_artifacts_missing")),
        "invalid_tool_call_count": _non_negative_int(payload.get("invalid_tool_call_count")),
        "tool_parser_repair_cases": _non_negative_int(payload.get("tool_parser_repair_cases")),
        "tool_parser_repairs_valid": _non_negative_int(payload.get("tool_parser_repairs_valid")),
        "tool_parser_repair_valid_rate_percent": payload.get("tool_parser_repair_valid_rate_percent"),
        "tool_parser_repair_findings": _tool_parser_repair_findings(payload.get("findings")),
        "tool_parser_repair_artifacts_missing": _non_negative_int(
            payload.get("tool_parser_repair_artifacts_missing")
        ),
    }
    if payload.get("ok") is not True:
        return _check(category, False, "blocker", str(path), "ok is not true", **extras)
    return _check(category, True, "blocker", str(path), "artifact accepted", **extras)


def _matrix_scorecard_evidence_check(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        return _missing_check("matrix_scorecards", required=False)
    return {
        "category": "matrix_scorecards",
        "items": [
            _matrix_scorecard_check(f"matrix_scorecards[{index}]", path)
            for index, path in enumerate(paths, start=1)
        ],
    }


def _matrix_scorecard_check(category: str, path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return _check(category, False, "blocker", str(path), f"missing artifact: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _check(category, False, "blocker", str(path), f"invalid JSON artifact: {exc}")
    if not isinstance(payload, dict):
        return _check(category, False, "blocker", str(path), "JSON artifact root must be an object")
    schema_values = {
        str(value)
        for value in (payload.get("schema_version"), payload.get("schema"), payload.get("report_type"))
        if value is not None
    }
    if MATRIX_SCORECARD_SCHEMA_VERSION not in schema_values:
        found = ", ".join(sorted(schema_values)) if schema_values else "none"
        return _check(category, False, "blocker", str(path), f"expected schema {MATRIX_SCORECARD_SCHEMA_VERSION}, found {found}")
    summary = _matrix_scorecard_summary(payload)
    summary["archive_path"] = _safe_evidence_path(path)
    summary["archive_path_redacted"] = _evidence_path_redacted(path)
    return _check(
        category,
        True,
        "warning",
        str(path),
        "artifact accepted",
        matrix_scorecard_summary=summary,
    )


def _harness_review_evidence_check(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        return _missing_check("harness_reviews", required=False)
    return {
        "category": "harness_reviews",
        "items": [
            _harness_review_check(f"harness_reviews[{index}]", path)
            for index, path in enumerate(paths, start=1)
        ],
    }


def _harness_review_check(category: str, path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return _check(category, False, "blocker", str(path), f"missing artifact: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _check(category, False, "blocker", str(path), f"invalid JSON artifact: {exc}")
    if not isinstance(payload, dict):
        return _check(category, False, "blocker", str(path), "JSON artifact root must be an object")
    schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema")) if value is not None}
    if HARNESS_REVIEW_SCHEMA_VERSION not in schema_values:
        found = ", ".join(sorted(schema_values)) if schema_values else "none"
        return _check(category, False, "blocker", str(path), f"expected schema {HARNESS_REVIEW_SCHEMA_VERSION}, found {found}")
    return _check(
        category,
        True,
        "blocker",
        str(path),
        "artifact accepted",
        harness_review_summary=_harness_review_summary(payload),
    )


def _implementation_status_evidence_check(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        return _missing_check("implementation_status_reports", required=False)
    return {
        "category": "implementation_status_reports",
        "items": [
            _implementation_status_check(f"implementation_status_reports[{index}]", path)
            for index, path in enumerate(paths, start=1)
        ],
    }


def _implementation_status_check(category: str, path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return _check(category, False, "blocker", str(path), f"missing artifact: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _check(category, False, "blocker", str(path), f"invalid JSON artifact: {exc}")
    if not isinstance(payload, dict):
        return _check(category, False, "blocker", str(path), "JSON artifact root must be an object")
    schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema")) if value is not None}
    if IMPLEMENTATION_STATUS_SCHEMA_VERSION not in schema_values:
        found = ", ".join(sorted(schema_values)) if schema_values else "none"
        return _check(category, False, "blocker", str(path), f"expected schema {IMPLEMENTATION_STATUS_SCHEMA_VERSION}, found {found}")
    summary = _implementation_status_summary(payload)
    if summary.get("missing_areas") or summary.get("status") != "implementation-ready-for-validation":
        return _check(
            category,
            False,
            "blocker",
            str(path),
            "implementation status is not ready for validation",
            implementation_status_summary=summary,
        )
    return _check(
        category,
        True,
        "warning",
        str(path),
        "artifact accepted",
        implementation_status_summary=summary,
    )


def _suite_calibration_evidence_check(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        return _missing_check("suite_calibration_reports", required=False)
    return {
        "category": "suite_calibration_reports",
        "items": [
            _suite_calibration_check(f"suite_calibration_reports[{index}]", path)
            for index, path in enumerate(paths, start=1)
        ],
    }


def _suite_calibration_check(category: str, path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return _check(category, False, "blocker", str(path), f"missing artifact: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _check(category, False, "blocker", str(path), f"invalid JSON artifact: {exc}")
    if not isinstance(payload, dict):
        return _check(category, False, "blocker", str(path), "JSON artifact root must be an object")
    schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema")) if value is not None}
    if CALIBRATION_REPORT_SCHEMA_VERSION not in schema_values:
        found = ", ".join(sorted(schema_values)) if schema_values else "none"
        return _check(category, False, "blocker", str(path), f"expected schema {CALIBRATION_REPORT_SCHEMA_VERSION}, found {found}")
    summary = _suite_calibration_summary(payload)
    if payload.get("passed") is not True:
        return _check(
            category,
            False,
            "blocker",
            str(path),
            "suite calibration report did not pass",
            suite_calibration_summary=summary,
        )
    return _check(
        category,
        True,
        "warning",
        str(path),
        "artifact accepted",
        suite_calibration_summary=summary,
    )


def _engine_advisory_evidence_check(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        return _missing_check("engine_advisories", required=False)
    return {
        "category": "engine_advisories",
        "items": [
            _engine_advisory_check(f"engine_advisories[{index}]", path)
            for index, path in enumerate(paths, start=1)
        ],
    }


def _engine_advisory_check(category: str, path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return _check(category, False, "blocker", str(path), f"missing artifact: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _check(category, False, "blocker", str(path), f"invalid JSON artifact: {exc}")
    if not isinstance(payload, dict):
        return _check(category, False, "blocker", str(path), "JSON artifact root must be an object")
    schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema")) if value is not None}
    if ENGINE_ADVISORY_SCHEMA_VERSION not in schema_values:
        found = ", ".join(sorted(schema_values)) if schema_values else "none"
        return _check(category, False, "blocker", str(path), f"expected schema {ENGINE_ADVISORY_SCHEMA_VERSION}, found {found}")
    return _check(
        category,
        True,
        "blocker",
        str(path),
        "artifact accepted",
        engine_advisory_summary=_engine_advisory_summary(payload),
    )


def _evidence_index_evidence_check(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        return _missing_check("evidence_indexes", required=False)
    return {
        "category": "evidence_indexes",
        "items": [
            _evidence_index_check(f"evidence_indexes[{index}]", path)
            for index, path in enumerate(paths, start=1)
        ],
    }


def _evidence_index_check(category: str, path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return _check(category, False, "blocker", str(path), f"missing artifact: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _check(category, False, "blocker", str(path), f"invalid JSON artifact: {exc}")
    if not isinstance(payload, dict):
        return _check(category, False, "blocker", str(path), "JSON artifact root must be an object")
    schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema")) if value is not None}
    if EVIDENCE_INDEX_SCHEMA_VERSION not in schema_values:
        found = ", ".join(sorted(schema_values)) if schema_values else "none"
        return _check(category, False, "blocker", str(path), f"expected schema {EVIDENCE_INDEX_SCHEMA_VERSION}, found {found}")
    summary = _evidence_index_summary(payload)
    readiness = summary.get("readiness")
    if isinstance(readiness, dict) and readiness.get("state") == "blocked":
        return _check(
            category,
            False,
            "blocker",
            str(path),
            "evidence index readiness is blocked",
            evidence_index_summary=summary,
        )
    return _check(
        category,
        True,
        "blocker",
        str(path),
        "artifact accepted",
        evidence_index_summary=summary,
    )


def _suite_audit_evidence_check(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        return _missing_check("suite_audits", required=False)
    return {
        "category": "suite_audits",
        "items": [
            _suite_audit_check(f"suite_audits[{index}]", path)
            for index, path in enumerate(paths, start=1)
        ],
    }


def _suite_audit_check(category: str, path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return _check(category, False, "blocker", str(path), f"missing artifact: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _check(category, False, "blocker", str(path), f"invalid JSON artifact: {exc}")
    if not isinstance(payload, dict):
        return _check(category, False, "blocker", str(path), "JSON artifact root must be an object")
    schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema")) if value is not None}
    if SUITE_AUDIT_SCHEMA_VERSION not in schema_values:
        found = ", ".join(sorted(schema_values)) if schema_values else "none"
        return _check(category, False, "blocker", str(path), f"expected schema {SUITE_AUDIT_SCHEMA_VERSION}, found {found}")
    summary = _suite_audit_summary(payload)
    if summary["finding_count"] > 0:
        return _check(
            category,
            False,
            "warning",
            str(path),
            "suite audit has governance findings requiring review",
            suite_audit_summary=summary,
        )
    return _check(
        category,
        True,
        "warning",
        str(path),
        "artifact accepted",
        suite_audit_summary=summary,
    )


def _metric_coverage_evidence_check(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        return _missing_check("metric_coverage_reports", required=False)
    return {
        "category": "metric_coverage_reports",
        "items": [
            _metric_coverage_check(f"metric_coverage_reports[{index}]", path)
            for index, path in enumerate(paths, start=1)
        ],
    }


def _metric_coverage_check(category: str, path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return _check(category, False, "blocker", str(path), f"missing artifact: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _check(category, False, "blocker", str(path), f"invalid JSON artifact: {exc}")
    if not isinstance(payload, dict):
        return _check(category, False, "blocker", str(path), "JSON artifact root must be an object")
    schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema")) if value is not None}
    if METRIC_COVERAGE_SCHEMA_VERSION not in schema_values:
        found = ", ".join(sorted(schema_values)) if schema_values else "none"
        return _check(category, False, "blocker", str(path), f"expected schema {METRIC_COVERAGE_SCHEMA_VERSION}, found {found}")
    summary = _metric_coverage_summary(payload)
    if summary["review_required_groups"]:
        return _check(
            category,
            False,
            "warning",
            str(path),
            "metric coverage has comparability groups requiring disclosure",
            metric_coverage_summary=summary,
        )
    return _check(
        category,
        True,
        "warning",
        str(path),
        "artifact accepted",
        metric_coverage_summary=summary,
    )


def _normalized_telemetry_evidence_check(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        return _missing_check("normalized_telemetry_reports", required=False)
    return {
        "category": "normalized_telemetry_reports",
        "items": [
            _normalized_telemetry_check(f"normalized_telemetry_reports[{index}]", path)
            for index, path in enumerate(paths, start=1)
        ],
    }


def _normalized_telemetry_check(category: str, path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return _check(category, False, "blocker", str(path), f"missing artifact: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _check(category, False, "blocker", str(path), f"invalid JSON artifact: {exc}")
    if not isinstance(payload, dict):
        return _check(category, False, "blocker", str(path), "JSON artifact root must be an object")
    schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema")) if value is not None}
    if NORMALIZED_TELEMETRY_SCHEMA_VERSION not in schema_values:
        found = ", ".join(sorted(schema_values)) if schema_values else "none"
        return _check(
            category,
            False,
            "blocker",
            str(path),
            f"expected schema {NORMALIZED_TELEMETRY_SCHEMA_VERSION}, found {found}",
        )
    return _check(
        category,
        True,
        "warning",
        str(path),
        "artifact accepted",
        normalized_telemetry_summary=_normalized_telemetry_summary(payload),
    )


def _selftest_report_evidence_check(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        return _missing_check("selftest_reports", required=False)
    return {
        "category": "selftest_reports",
        "items": [
            _selftest_report_check(f"selftest_reports[{index}]", path)
            for index, path in enumerate(paths, start=1)
        ],
    }


def _selftest_report_check(category: str, path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return _check(category, False, "blocker", str(path), f"missing artifact: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _check(category, False, "blocker", str(path), f"invalid JSON artifact: {exc}")
    if not isinstance(payload, dict):
        return _check(category, False, "blocker", str(path), "JSON artifact root must be an object")
    schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema")) if value is not None}
    if SELFTEST_REPORT_SCHEMA_VERSION not in schema_values:
        found = ", ".join(sorted(schema_values)) if schema_values else "none"
        return _check(category, False, "blocker", str(path), f"expected schema {SELFTEST_REPORT_SCHEMA_VERSION}, found {found}")
    summary = _selftest_summary(payload)
    if payload.get("ok") is not True:
        return _check(
            category,
            False,
            "blocker",
            str(path),
            "selftest report ok is not true",
            selftest_report_summary=summary,
        )
    return _check(
        category,
        True,
        "warning",
        str(path),
        "artifact accepted",
        selftest_report_summary=summary,
    )


def _benchmark_readiness_evidence_check(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        return _missing_check("benchmark_readiness_reports", required=False)
    return {
        "category": "benchmark_readiness_reports",
        "items": [
            _benchmark_readiness_check(f"benchmark_readiness_reports[{index}]", path)
            for index, path in enumerate(paths, start=1)
        ],
    }


def _benchmark_readiness_check(category: str, path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return _check(category, False, "blocker", str(path), f"missing artifact: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _check(category, False, "blocker", str(path), f"invalid JSON artifact: {exc}")
    if not isinstance(payload, dict):
        return _check(category, False, "blocker", str(path), "JSON artifact root must be an object")
    schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema")) if value is not None}
    if READINESS_SCHEMA_VERSION not in schema_values:
        found = ", ".join(sorted(schema_values)) if schema_values else "none"
        return _check(category, False, "blocker", str(path), f"expected schema {READINESS_SCHEMA_VERSION}, found {found}")
    summary = _benchmark_readiness_summary(payload)
    if payload.get("ready") is not True:
        return _check(
            category,
            False,
            "blocker",
            str(path),
            "benchmark readiness is not true",
            benchmark_readiness_summary=summary,
        )
    return _check(
        category,
        True,
        "warning",
        str(path),
        "artifact accepted",
        benchmark_readiness_summary=summary,
    )


def _provider_audit_evidence_check(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        return _missing_check("provider_audits", required=False)
    return {
        "category": "provider_audits",
        "items": [
            _provider_audit_check(f"provider_audits[{index}]", path)
            for index, path in enumerate(paths, start=1)
        ],
    }


def _provider_audit_check(category: str, path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return _check(category, False, "blocker", str(path), f"missing artifact: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _check(category, False, "blocker", str(path), f"invalid JSON artifact: {exc}")
    if not isinstance(payload, dict):
        return _check(category, False, "blocker", str(path), "JSON artifact root must be an object")
    schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema")) if value is not None}
    if PROVIDER_AUDIT_SCHEMA_VERSION not in schema_values:
        found = ", ".join(sorted(schema_values)) if schema_values else "none"
        return _check(category, False, "blocker", str(path), f"expected schema {PROVIDER_AUDIT_SCHEMA_VERSION}, found {found}")
    summary = _provider_audit_summary(payload)
    summary["archive_path"] = _safe_evidence_path(path)
    summary["archive_path_redacted"] = _evidence_path_redacted(path)
    if summary.get("error_count"):
        return _check(
            category,
            False,
            "blocker",
            str(path),
            "provider audit reports policy errors",
            provider_audit_summary=summary,
        )
    return _check(
        category,
        True,
        "warning",
        str(path),
        "artifact accepted",
        provider_audit_summary=summary,
    )


def _protocol_repair_posture_evidence_check(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        return _missing_check("protocol_repair_postures", required=False)
    return {
        "category": "protocol_repair_postures",
        "items": [
            _protocol_repair_posture_check(f"protocol_repair_postures[{index}]", path)
            for index, path in enumerate(paths, start=1)
        ],
    }


def _protocol_repair_posture_check(category: str, path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return _check(category, False, "blocker", str(path), f"missing artifact: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _check(category, False, "blocker", str(path), f"invalid JSON artifact: {exc}")
    if not isinstance(payload, dict):
        return _check(category, False, "blocker", str(path), "JSON artifact root must be an object")
    schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema")) if value is not None}
    if PROTOCOL_REPAIR_POSTURE_SCHEMA_VERSION not in schema_values:
        found = ", ".join(sorted(schema_values)) if schema_values else "none"
        return _check(category, False, "blocker", str(path), f"expected schema {PROTOCOL_REPAIR_POSTURE_SCHEMA_VERSION}, found {found}")
    summary = _protocol_repair_posture_summary(payload)
    summary["archive_path"] = _safe_evidence_path(path)
    summary["archive_path_redacted"] = _evidence_path_redacted(path)
    if payload.get("ready") is not True:
        return _check(category, False, "warning", str(path), "protocol repair posture requires review", protocol_repair_posture_summary=summary)
    return _check(category, True, "warning", str(path), "artifact accepted", protocol_repair_posture_summary=summary)


def _workflow_readiness_evidence_check(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        return _missing_check("workflow_readiness_reports", required=False)
    return {
        "category": "workflow_readiness_reports",
        "items": [
            _workflow_readiness_check(f"workflow_readiness_reports[{index}]", path)
            for index, path in enumerate(paths, start=1)
        ],
    }


def _workflow_readiness_check(category: str, path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return _check(category, False, "blocker", str(path), f"missing artifact: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _check(category, False, "blocker", str(path), f"invalid JSON artifact: {exc}")
    if not isinstance(payload, dict):
        return _check(category, False, "blocker", str(path), "JSON artifact root must be an object")
    schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema")) if value is not None}
    if WORKFLOW_READINESS_SCHEMA_VERSION not in schema_values:
        found = ", ".join(sorted(schema_values)) if schema_values else "none"
        return _check(category, False, "blocker", str(path), f"expected schema {WORKFLOW_READINESS_SCHEMA_VERSION}, found {found}")
    summary = _workflow_readiness_summary(payload)
    summary["archive_path"] = _safe_evidence_path(path)
    summary["archive_path_redacted"] = _evidence_path_redacted(path)
    if payload.get("ready") is not True:
        return _check(category, False, "warning", str(path), "workflow readiness has required surface gaps", workflow_readiness_summary=summary)
    return _check(category, True, "warning", str(path), "artifact accepted", workflow_readiness_summary=summary)


def _security_posture_evidence_check(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        return _missing_check("security_postures", required=False)
    return {
        "category": "security_postures",
        "items": [
            _security_posture_check(f"security_postures[{index}]", path)
            for index, path in enumerate(paths, start=1)
        ],
    }


def _security_posture_check(category: str, path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return _check(category, False, "blocker", str(path), f"missing artifact: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _check(category, False, "blocker", str(path), f"invalid JSON artifact: {exc}")
    if not isinstance(payload, dict):
        return _check(category, False, "blocker", str(path), "JSON artifact root must be an object")
    schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema")) if value is not None}
    if SECURITY_POSTURE_SCHEMA_VERSION not in schema_values:
        found = ", ".join(sorted(schema_values)) if schema_values else "none"
        return _check(category, False, "blocker", str(path), f"expected schema {SECURITY_POSTURE_SCHEMA_VERSION}, found {found}")
    summary = _security_posture_summary(payload)
    summary["archive_path"] = _safe_evidence_path(path)
    summary["archive_path_redacted"] = _evidence_path_redacted(path)
    if payload.get("ready") is not True:
        return _check(category, False, "blocker", str(path), "security posture has blockers", security_posture_summary=summary)
    return _check(category, True, "blocker", str(path), "artifact accepted", security_posture_summary=summary)


def _campaign_preflight_evidence_check(path: Path | None) -> dict[str, Any]:
    category = "campaign_preflight_manifest"
    if path is None:
        return _missing_check(category, required=False)
    if not path.exists() or not path.is_file():
        return _check(category, False, "blocker", str(path), f"missing artifact: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _check(category, False, "blocker", str(path), f"invalid JSON artifact: {exc}")
    if not isinstance(payload, dict):
        return _check(category, False, "blocker", str(path), "JSON artifact root must be an object")
    schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema")) if value is not None}
    if "agentblaster.campaign-preflight-bundle.v1" not in schema_values:
        found = ", ".join(sorted(schema_values)) if schema_values else "none"
        return _check(category, False, "blocker", str(path), f"expected schema agentblaster.campaign-preflight-bundle.v1, found {found}")
    try:
        readiness_summaries = _campaign_preflight_readiness_summaries(path, payload)
    except ConfigError as exc:
        return _check(category, False, "blocker", str(path), str(exc))
    preflight_summary = _campaign_preflight_manifest_summary(payload)
    if any(summary.get("ready") is not True for summary in readiness_summaries):
        return _check(
            category,
            False,
            "blocker",
            str(path),
            "campaign preflight benchmark readiness is not true",
            benchmark_readiness_summaries=readiness_summaries,
            campaign_preflight_summary=preflight_summary,
        )
    return _check(
        category,
        True,
        "warning",
        str(path),
        "artifact accepted",
        benchmark_readiness_summaries=readiness_summaries,
        campaign_preflight_summary=preflight_summary,
    )


def _campaign_preflight_manifest_summary(payload: dict[str, Any]) -> dict[str, Any]:
    review_summary = payload.get("review_summary") if isinstance(payload.get("review_summary"), dict) else {}
    security = review_summary.get("security") if isinstance(review_summary.get("security"), dict) else {}
    manifest_security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    uses_review_summary = bool(review_summary)
    benchmark_readiness = payload.get("benchmark_readiness") if isinstance(payload.get("benchmark_readiness"), dict) else {}
    return {
        "schema_version": "agentblaster.campaign-preflight-bundle.v1",
        "review_summary_schema_version": review_summary.get("schema_version"),
        "matrix_count": _non_negative_int(review_summary.get("matrix_count") or payload.get("matrix_count")),
        "run_count": _non_negative_int(review_summary.get("run_count")),
        "total_cases": _non_negative_int(review_summary.get("total_cases")),
        "includes_provider_audit": bool(
            review_summary.get("includes_provider_audit") or payload.get("includes_provider_audit")
        ),
        "includes_benchmark_readiness": bool(
            review_summary.get("includes_benchmark_readiness") or payload.get("includes_benchmark_readiness")
        ),
        "benchmark_readiness_report_count": _non_negative_int(
            review_summary.get("benchmark_readiness_report_count") or benchmark_readiness.get("report_count")
        ),
        "contains_local_paths": bool(
            security.get("contains_local_paths")
            if uses_review_summary
            else manifest_security.get("contains_local_paths", True)
        ),
        "external_publication_safe": bool(security.get("external_publication_safe")) if uses_review_summary else False,
    }


def _campaign_preflight_readiness_summaries(manifest_path: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    readiness = payload.get("benchmark_readiness")
    if not isinstance(readiness, dict):
        return []
    artifact_path = readiness.get("artifact_path")
    if not artifact_path:
        return []
    index_path = manifest_path.parent / str(artifact_path)
    try:
        index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"invalid campaign preflight benchmark readiness index at {index_path}: {exc}") from exc
    if not isinstance(index_payload, dict):
        raise ConfigError(f"campaign preflight benchmark readiness index root must be an object: {index_path}")
    schema_values = {
        str(value)
        for value in (index_payload.get("schema_version"), index_payload.get("schema"))
        if value is not None
    }
    if "agentblaster.campaign-preflight-benchmark-readiness-index.v1" not in schema_values:
        found = ", ".join(sorted(schema_values)) if schema_values else "none"
        raise ConfigError(
            "expected campaign preflight benchmark readiness index schema "
            f"agentblaster.campaign-preflight-benchmark-readiness-index.v1, found {found}"
        )
    reports = index_payload.get("reports")
    if not isinstance(reports, list):
        raise ConfigError(f"campaign preflight benchmark readiness index reports must be a list: {index_path}")
    summaries = []
    for report in reports[:20]:
        if isinstance(report, dict):
            summaries.append(_benchmark_readiness_summary(report))
    return summaries


def _publication_bundle_evidence_check(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        return _missing_check("publication_bundles", required=False)
    return {
        "category": "publication_bundles",
        "items": [
            _publication_bundle_check(f"publication_bundles[{index}]", path)
            for index, path in enumerate(paths, start=1)
        ],
    }


def _publication_bundle_check(category: str, path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return _check(category, False, "blocker", str(path), f"missing artifact: {path}")
    if not path.name.endswith(".agentblaster-publication.zip"):
        return _check(category, False, "blocker", str(path), "artifact must end with .agentblaster-publication.zip")
    manifest_check = _publication_bundle_manifest_check(category, path)
    if manifest_check is not None:
        return manifest_check
    return _check(category, True, "warning", str(path), "artifact accepted")


def _publication_bundle_manifest_check(category: str, path: Path) -> dict[str, Any] | None:
    try:
        with ZipFile(path) as archive:
            try:
                info = archive.getinfo(PUBLICATION_BUNDLE_MANIFEST)
            except KeyError:
                return _check(category, False, "blocker", str(path), f"publication bundle is missing {PUBLICATION_BUNDLE_MANIFEST}")
            if info.file_size > MAX_PUBLICATION_BUNDLE_MANIFEST_BYTES:
                return _check(category, False, "blocker", str(path), "publication bundle manifest is too large")
            payload = json.loads(archive.read(info).decode("utf-8"))
    except (BadZipFile, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _check(category, False, "blocker", str(path), f"invalid publication bundle manifest: {exc}")
    if not isinstance(payload, dict):
        return _check(category, False, "blocker", str(path), "publication bundle manifest root must be an object")
    schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema")) if value is not None}
    if PUBLICATION_BUNDLE_MANIFEST_SCHEMA_VERSION not in schema_values:
        found = ", ".join(sorted(schema_values)) if schema_values else "none"
        return _check(category, False, "blocker", str(path), f"expected schema {PUBLICATION_BUNDLE_MANIFEST_SCHEMA_VERSION}, found {found}")
    summary = _publication_bundle_summary(payload)
    security = summary.get("security") if isinstance(summary.get("security"), dict) else {}
    if any(
        security.get(key) is True
        for key in ("contains_raw_secrets", "contains_raw_provider_payloads", "contains_results_jsonl")
    ):
        return _check(
            category,
            False,
            "blocker",
            str(path),
            "publication bundle manifest reports unsafe content",
            publication_bundle_summary=summary,
        )
    readiness = summary.get("publication_readiness") if isinstance(summary.get("publication_readiness"), dict) else {}
    status = readiness.get("status")
    if status == "blocked":
        return _check(
            category,
            False,
            "blocker",
            str(path),
            "publication readiness is blocked",
            publication_bundle_summary=summary,
        )
    if status == "review-required":
        return _check(
            category,
            False,
            "warning",
            str(path),
            "publication readiness requires review",
            publication_bundle_summary=summary,
        )
    if status not in {"ready", "review-required"}:
        return _check(
            category,
            False,
            "warning",
            str(path),
            "publication readiness status is unknown",
            publication_bundle_summary=summary,
        )
    media_status, media_status_source = _publication_media_kit_status(summary)
    if media_status == "review":
        return _check(
            category,
            False,
            "warning",
            str(path),
            f"publication media kit requires review: {media_status_source}",
            publication_bundle_summary=summary,
        )
    return _check(category, True, "warning", str(path), "artifact accepted", publication_bundle_summary=summary)


def _publication_media_kit_status(summary: dict[str, Any]) -> tuple[str, str]:
    media_kit = summary.get("media_kit") if isinstance(summary.get("media_kit"), dict) else {}
    if media_kit.get("schema_version") != MEDIA_KIT_SCHEMA_VERSION:
        return "review", "media_kit.schema_version"
    missing = media_kit.get("missing_recommended_assets")
    if isinstance(missing, list) and missing:
        return "review", "media_kit.missing_recommended_assets"
    return "pass", "media_kit"


def _matrix_publication_bundle_evidence_check(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        return _missing_check("matrix_publication_bundles", required=False)
    return {
        "category": "matrix_publication_bundles",
        "items": [
            _matrix_publication_bundle_check(f"matrix_publication_bundles[{index}]", path)
            for index, path in enumerate(paths, start=1)
        ],
    }


def _matrix_publication_bundle_check(category: str, path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return _check(category, False, "blocker", str(path), f"missing artifact: {path}")
    if not path.name.endswith(".agentblaster-matrix-publication.zip"):
        return _check(category, False, "blocker", str(path), "artifact must end with .agentblaster-matrix-publication.zip")
    try:
        with ZipFile(path) as archive:
            try:
                info = archive.getinfo(MATRIX_PUBLICATION_BUNDLE_MANIFEST)
            except KeyError:
                return _check(category, False, "blocker", str(path), f"matrix publication bundle is missing {MATRIX_PUBLICATION_BUNDLE_MANIFEST}")
            if info.file_size > MAX_PUBLICATION_BUNDLE_MANIFEST_BYTES:
                return _check(category, False, "blocker", str(path), "matrix publication bundle manifest is too large")
            payload = json.loads(archive.read(info).decode("utf-8"))
    except (BadZipFile, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _check(category, False, "blocker", str(path), f"invalid matrix publication bundle manifest: {exc}")
    if not isinstance(payload, dict):
        return _check(category, False, "blocker", str(path), "matrix publication bundle manifest root must be an object")
    schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema")) if value is not None}
    if MATRIX_PUBLICATION_BUNDLE_MANIFEST_SCHEMA_VERSION not in schema_values:
        found = ", ".join(sorted(schema_values)) if schema_values else "none"
        return _check(category, False, "blocker", str(path), f"expected schema {MATRIX_PUBLICATION_BUNDLE_MANIFEST_SCHEMA_VERSION}, found {found}")
    summary = _matrix_publication_bundle_summary(payload)
    status, status_source = _matrix_publication_bundle_status(summary)
    if status == "fail":
        return _check(
            category,
            False,
            "blocker",
            str(path),
            "matrix publication bundle manifest reports unsafe content",
            matrix_publication_bundle_summary=summary,
        )
    if status == "review":
        return _check(
            category,
            False,
            "warning",
            str(path),
            f"matrix publication bundle requires review: {status_source}",
            matrix_publication_bundle_summary=summary,
        )
    return _check(category, True, "warning", str(path), "artifact accepted", matrix_publication_bundle_summary=summary)


def _zip_list_check(category: str, paths: list[Path], *, required: bool, suffix: str) -> dict[str, Any]:
    if not paths:
        return _missing_check(category, required)
    return {
        "category": category,
        "items": [
            _zip_check(f"{category}[{index}]", path, required=True, suffix=suffix)
            for index, path in enumerate(paths, start=1)
        ],
    }


def _json_check(
    category: str,
    path: Path | None,
    *,
    required: bool,
    schema: str | None = None,
    ok_field: str | None = None,
    ok_path: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    if path is None:
        return _missing_check(category, required)
    if not path.exists() or not path.is_file():
        return _check(category, False, "blocker", str(path), f"missing artifact: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _check(category, False, "blocker", str(path), f"invalid JSON artifact: {exc}")
    if not isinstance(payload, dict):
        return _check(category, False, "blocker", str(path), "JSON artifact root must be an object")
    schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema")) if value is not None}
    if schema is not None and schema not in schema_values:
        found = ", ".join(sorted(schema_values)) if schema_values else "none"
        return _check(category, False, "blocker", str(path), f"expected schema {schema}, found {found}")
    if ok_field is not None and payload.get(ok_field) is not True:
        return _check(category, False, "blocker", str(path), f"{ok_field} is not true")
    if ok_path is not None and _lookup_path(payload, ok_path) is not True:
        return _check(category, False, "blocker", str(path), ".".join(ok_path) + " is not true")
    return _check(category, True, "blocker" if required else "warning", str(path), "artifact accepted")


def _redaction_scan_check(path: Path | None) -> dict[str, Any]:
    category = "redaction_scan"
    if path is None:
        return _missing_check(category, required=True)
    if not path.exists() or not path.is_file():
        return _check(category, False, "blocker", str(path), f"missing artifact: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _check(category, False, "blocker", str(path), f"invalid JSON artifact: {exc}")
    if not isinstance(payload, dict):
        return _check(category, False, "blocker", str(path), "JSON artifact root must be an object")
    schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema")) if value is not None}
    if REDACTION_SCAN_SCHEMA_VERSION not in schema_values:
        found = ", ".join(sorted(schema_values)) if schema_values else "none"
        return _check(category, False, "blocker", str(path), f"expected schema {REDACTION_SCAN_SCHEMA_VERSION}, found {found}")
    summary = _redaction_scan_summary(payload)
    if payload.get("ok") is not True:
        return _check(
            category,
            False,
            "blocker",
            str(path),
            "redaction scan ok is not true",
            redaction_scan_summary=summary,
        )
    return _check(
        category,
        True,
        "blocker",
        str(path),
        "artifact accepted",
        redaction_scan_summary=summary,
    )


def _zip_check(category: str, path: Path | None, *, required: bool, suffix: str) -> dict[str, Any]:
    if path is None:
        return _missing_check(category, required)
    if not path.exists() or not path.is_file():
        return _check(category, False, "blocker", str(path), f"missing artifact: {path}")
    if not path.name.endswith(suffix):
        return _check(category, False, "blocker", str(path), f"artifact must end with {suffix}")
    if suffix == ".agentblaster-release-qualification.zip":
        return _release_bundle_manifest_check(category, path)
    return _check(category, True, "blocker" if required else "warning", str(path), "artifact accepted")


def _release_bundle_manifest_check(category: str, path: Path) -> dict[str, Any] | None:
    try:
        with ZipFile(path) as archive:
            try:
                info = archive.getinfo("manifest.json")
            except KeyError:
                return _check(category, False, "blocker", str(path), "release qualification bundle is missing manifest.json")
            if info.file_size > MAX_RELEASE_BUNDLE_MANIFEST_BYTES:
                return _check(category, False, "blocker", str(path), "release qualification manifest is too large")
            payload = json.loads(archive.read(info).decode("utf-8"))
    except (BadZipFile, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _check(category, False, "blocker", str(path), f"invalid release qualification bundle manifest: {exc}")
    if not isinstance(payload, dict):
        return _check(category, False, "blocker", str(path), "release qualification manifest root must be an object")
    schema_values = {str(value) for value in (payload.get("schema"), payload.get("schema_version")) if value is not None}
    if "agentblaster.release-qualification-bundle" not in schema_values:
        found = ", ".join(sorted(schema_values)) if schema_values else "none"
        return _check(category, False, "blocker", str(path), f"expected release qualification schema, found {found}")
    publication_summaries = _release_publication_bundle_summaries(payload)
    matrix_publication_summaries = _release_matrix_publication_bundle_summaries(payload)
    publication_brief_summaries = _release_publication_brief_summaries(payload)
    matrix_scorecard_summaries = _release_matrix_scorecard_summaries(payload)
    implementation_status_summaries = _release_implementation_status_summaries(payload)
    campaign_preflight_summaries = _release_campaign_preflight_summaries(payload)
    selftest_report_summaries = _release_selftest_report_summaries(payload)
    sdlc_validation_manifest_summaries = _release_sdlc_validation_manifest_summaries(payload)
    benchmark_readiness_summaries = _release_benchmark_readiness_summaries(payload)
    provider_audit_summaries = _release_provider_audit_summaries(payload)
    normalized_telemetry_summaries = _release_normalized_telemetry_summaries(payload)
    protocol_repair_posture_summaries = _release_protocol_repair_posture_summaries(payload)
    workflow_readiness_summaries = _release_workflow_readiness_summaries(payload)
    security_posture_summaries = _release_security_posture_summaries(payload)
    if payload.get("ok") is not True:
        status = payload.get("artifact_status")
        return _check(
            category,
            False,
            "blocker",
            str(path),
            f"release qualification bundle ok is not true; artifact_status={status}",
            publication_bundle_summaries=publication_summaries,
            matrix_publication_bundle_summaries=matrix_publication_summaries,
            publication_brief_summaries=publication_brief_summaries,
            matrix_scorecard_summaries=matrix_scorecard_summaries,
            implementation_status_summaries=implementation_status_summaries,
            campaign_preflight_summaries=campaign_preflight_summaries,
            selftest_report_summaries=selftest_report_summaries,
            sdlc_validation_manifest_summaries=sdlc_validation_manifest_summaries,
            benchmark_readiness_summaries=benchmark_readiness_summaries,
            provider_audit_summaries=provider_audit_summaries,
            normalized_telemetry_summaries=normalized_telemetry_summaries,
            protocol_repair_posture_summaries=protocol_repair_posture_summaries,
            workflow_readiness_summaries=workflow_readiness_summaries,
            security_posture_summaries=security_posture_summaries,
        )
    if any(summary.get("ready") is not True for summary in benchmark_readiness_summaries):
        return _check(
            category,
            False,
            "blocker",
            str(path),
            "release qualification bundle contains benchmark readiness that is not true",
            publication_bundle_summaries=publication_summaries,
            matrix_publication_bundle_summaries=matrix_publication_summaries,
            publication_brief_summaries=publication_brief_summaries,
            matrix_scorecard_summaries=matrix_scorecard_summaries,
            implementation_status_summaries=implementation_status_summaries,
            campaign_preflight_summaries=campaign_preflight_summaries,
            selftest_report_summaries=selftest_report_summaries,
            sdlc_validation_manifest_summaries=sdlc_validation_manifest_summaries,
            benchmark_readiness_summaries=benchmark_readiness_summaries,
            provider_audit_summaries=provider_audit_summaries,
            normalized_telemetry_summaries=normalized_telemetry_summaries,
            protocol_repair_posture_summaries=protocol_repair_posture_summaries,
            workflow_readiness_summaries=workflow_readiness_summaries,
            security_posture_summaries=security_posture_summaries,
        )
    if any(summary.get("error_count") for summary in provider_audit_summaries):
        return _check(
            category,
            False,
            "blocker",
            str(path),
            "release qualification bundle contains provider audit policy errors",
            publication_bundle_summaries=publication_summaries,
            matrix_publication_bundle_summaries=matrix_publication_summaries,
            publication_brief_summaries=publication_brief_summaries,
            matrix_scorecard_summaries=matrix_scorecard_summaries,
            implementation_status_summaries=implementation_status_summaries,
            campaign_preflight_summaries=campaign_preflight_summaries,
            selftest_report_summaries=selftest_report_summaries,
            sdlc_validation_manifest_summaries=sdlc_validation_manifest_summaries,
            benchmark_readiness_summaries=benchmark_readiness_summaries,
            provider_audit_summaries=provider_audit_summaries,
            normalized_telemetry_summaries=normalized_telemetry_summaries,
            protocol_repair_posture_summaries=protocol_repair_posture_summaries,
            workflow_readiness_summaries=workflow_readiness_summaries,
            security_posture_summaries=security_posture_summaries,
        )
    if any(
        summary.get("missing_areas")
        or (summary.get("implementation_status") or summary.get("status")) != "implementation-ready-for-validation"
        for summary in implementation_status_summaries
    ):
        return _check(
            category,
            False,
            "blocker",
            str(path),
            "release qualification bundle contains implementation status that is not ready for validation",
            publication_bundle_summaries=publication_summaries,
            matrix_publication_bundle_summaries=matrix_publication_summaries,
            publication_brief_summaries=publication_brief_summaries,
            matrix_scorecard_summaries=matrix_scorecard_summaries,
            implementation_status_summaries=implementation_status_summaries,
            campaign_preflight_summaries=campaign_preflight_summaries,
            selftest_report_summaries=selftest_report_summaries,
            sdlc_validation_manifest_summaries=sdlc_validation_manifest_summaries,
            benchmark_readiness_summaries=benchmark_readiness_summaries,
            provider_audit_summaries=provider_audit_summaries,
            normalized_telemetry_summaries=normalized_telemetry_summaries,
            protocol_repair_posture_summaries=protocol_repair_posture_summaries,
            workflow_readiness_summaries=workflow_readiness_summaries,
            security_posture_summaries=security_posture_summaries,
        )
    return _check(
        category,
        True,
        "blocker",
        str(path),
        "artifact accepted",
        publication_bundle_summaries=publication_summaries,
        matrix_publication_bundle_summaries=matrix_publication_summaries,
        publication_brief_summaries=publication_brief_summaries,
        matrix_scorecard_summaries=matrix_scorecard_summaries,
        implementation_status_summaries=implementation_status_summaries,
        campaign_preflight_summaries=campaign_preflight_summaries,
        selftest_report_summaries=selftest_report_summaries,
        sdlc_validation_manifest_summaries=sdlc_validation_manifest_summaries,
        benchmark_readiness_summaries=benchmark_readiness_summaries,
        provider_audit_summaries=provider_audit_summaries,
        normalized_telemetry_summaries=normalized_telemetry_summaries,
        protocol_repair_posture_summaries=protocol_repair_posture_summaries,
        workflow_readiness_summaries=workflow_readiness_summaries,
        security_posture_summaries=security_posture_summaries,
    )


def _release_publication_bundle_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        is_run_publication = category == "publication" or (
            archive_path.startswith("publication/")
            and not archive_path.startswith("publication/matrix/")
            and not archive_path.startswith("publication/brief/")
        )
        if not is_run_publication:
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        summaries.append(_publication_bundle_review_summary(review_summary, archive_path=archive_path))
    return summaries[:12]


def _release_matrix_publication_bundle_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if category != "publication/matrix" and not archive_path.startswith("publication/matrix/"):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        summaries.append(_matrix_publication_bundle_summary(review_summary, archive_path=archive_path))
    return summaries[:12]


def _release_publication_brief_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if category != "publication/brief" and not archive_path.startswith("publication/brief/"):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        summary = _publication_brief_summary(review_summary)
        if archive_path:
            summary["archive_path"] = archive_path
        summaries.append(summary)
    return summaries[:12]


def _release_matrix_scorecard_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if category != "reports/matrix-scorecard" and not archive_path.startswith("reports/matrix-scorecard/"):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        summary = _matrix_scorecard_summary(review_summary)
        if archive_path:
            summary["archive_path"] = archive_path
        summaries.append(summary)
    return summaries[:12]


def _release_implementation_status_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if category != "readiness/implementation" and not archive_path.startswith("readiness/implementation/"):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        summary = _implementation_status_summary(review_summary)
        if archive_path:
            summary["archive_path"] = archive_path
        summaries.append(summary)
    return summaries[:12]


def _release_campaign_preflight_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if category != "readiness/campaign-preflight" and not archive_path.startswith("readiness/campaign-preflight/"):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        summary = {
            "archive_path": archive_path,
            "schema_version": review_summary.get("schema_version") or artifact.get("schema"),
            "review_summary_schema_version": review_summary.get("review_summary_schema_version"),
            "status": artifact.get("status"),
            "matrix_count": _non_negative_int(review_summary.get("matrix_count")),
            "run_count": _non_negative_int(review_summary.get("run_count")),
            "total_cases": _non_negative_int(review_summary.get("total_cases")),
            "includes_provider_audit": bool(review_summary.get("includes_provider_audit")),
            "includes_benchmark_readiness": bool(review_summary.get("includes_benchmark_readiness")),
            "benchmark_readiness_report_count": _non_negative_int(
                review_summary.get("benchmark_readiness_report_count")
            ),
            "contains_local_paths": bool(review_summary.get("contains_local_paths")),
            "external_publication_safe": bool(review_summary.get("external_publication_safe")),
        }
        summaries.append({key: value for key, value in summary.items() if value is not None})
    return summaries[:12]


def _release_selftest_report_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if (
            category == "selftest/validation-manifest"
            or archive_path.startswith("selftest/validation-manifest/")
            or archive_path.endswith("/sdlc-validation-manifest.json")
        ):
            continue
        if category != "selftest" and not archive_path.startswith("selftest/"):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        summary = _selftest_summary(review_summary)
        if archive_path:
            summary["archive_path"] = archive_path
        summaries.append(summary)
    return summaries[:12]


def _release_sdlc_validation_manifest_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if (
            category != "selftest/validation-manifest"
            and not archive_path.startswith("selftest/validation-manifest/")
            and not archive_path.endswith("/sdlc-validation-manifest.json")
        ):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        summary = _sdlc_validation_manifest_summary(review_summary)
        if archive_path:
            summary["archive_path"] = archive_path
        summaries.append(summary)
    return summaries[:12]


def _release_benchmark_readiness_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if category != "readiness/benchmark" and not archive_path.startswith("readiness/benchmark/"):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        summary = _benchmark_readiness_summary(review_summary)
        if archive_path:
            summary["archive_path"] = archive_path
        summaries.append(summary)
    return summaries[:12]


def _release_provider_audit_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if category != "security/provider-audit" and not archive_path.startswith("security/provider-audit/"):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        summary = _provider_audit_summary(review_summary)
        if archive_path:
            summary["archive_path"] = archive_path
        summaries.append(summary)
    return summaries[:12]


def _release_normalized_telemetry_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if category != "metrics/normalized-telemetry" and not archive_path.startswith("metrics/normalized-telemetry/"):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        summary = _normalized_telemetry_summary(review_summary)
        if archive_path:
            summary["archive_path"] = archive_path
        summaries.append(summary)
    return summaries[:12]


def _release_protocol_repair_posture_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return _release_review_summaries_for_categories(
        payload,
        categories={"publication/protocol-repair"},
        archive_prefixes=("publication/protocol-repair/",),
    )


def _release_workflow_readiness_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return _release_review_summaries_for_categories(
        payload,
        categories={"readiness/workflow"},
        archive_prefixes=("readiness/workflow/",),
    )


def _release_security_posture_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return _release_review_summaries_for_categories(
        payload,
        categories={"security/posture"},
        archive_prefixes=("security/posture/",),
    )


def _release_review_summaries_for_categories(
    payload: dict[str, Any],
    *,
    categories: set[str],
    archive_prefixes: tuple[str, ...],
) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries: list[dict[str, Any]] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if category not in categories and not any(archive_path.startswith(prefix) for prefix in archive_prefixes):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        summary = {str(key): value for key, value in review_summary.items()}
        if archive_path:
            summary["archive_path"] = archive_path
        if artifact.get("status") is not None:
            summary["artifact_status"] = artifact.get("status")
        summaries.append(summary)
    return summaries[:12]


def _missing_check(category: str, required: bool) -> dict[str, Any]:
    severity = "blocker" if required else "warning"
    message = "required artifact was not supplied" if required else "optional artifact was not supplied"
    return _check(category, not required, severity, None, message)


def _check(category: str, ok: bool, severity: str, path: str | None, message: str, **extra: Any) -> dict[str, Any]:
    safe_path = _safe_evidence_path(path) if path else None
    payload = {
        "category": category,
        "ok": ok,
        "severity": severity,
        "path": safe_path,
        "path_redacted": _evidence_path_redacted(path) if path else False,
        "message": message,
    }
    payload.update(extra)
    return payload


def _safe_evidence_path(path: str | Path) -> str:
    if _evidence_path_redacted(path):
        return _path_leaf(str(path))
    return Path(path).as_posix()


def _evidence_path_redacted(path: str | Path) -> bool:
    text = str(path).strip().replace("\\", "/")
    return (
        Path(path).is_absolute()
        or text.startswith(("/", "~/", "../"))
        or "/../" in text
        or (len(text) >= 3 and text[1] == ":" and text[2] == "/")
    )


def _path_leaf(path: str) -> str:
    normalized = path.strip().replace("\\", "/").rstrip("/")
    return normalized.rsplit("/", 1)[-1] or "artifact"


def _flatten_checks(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for item in items:
        if "items" in item:
            flattened.extend(item["items"])
        else:
            flattened.append(item)
    return flattened


def _lookup_path(payload: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = payload
    for part in path:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _sum_failure_class_artifacts_missing(checks: list[dict[str, Any]]) -> int:
    return sum(_non_negative_int(check.get("failure_class_artifacts_missing")) for check in checks)


def _sum_tool_loop_artifacts_missing(checks: list[dict[str, Any]]) -> int:
    return sum(_non_negative_int(check.get("tool_loop_artifacts_missing")) for check in checks)


def _sum_judge_verdict_artifacts_missing(checks: list[dict[str, Any]]) -> int:
    return sum(_non_negative_int(check.get("judge_verdict_artifacts_missing")) for check in checks)


def _sum_tool_parser_repair_artifacts_missing(checks: list[dict[str, Any]]) -> int:
    return sum(_non_negative_int(check.get("tool_parser_repair_artifacts_missing")) for check in checks)


def _collect_harness_review_summaries(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for check in checks:
        summary = check.get("harness_review_summary")
        if isinstance(summary, dict):
            summaries.append(summary)
    return summaries


def _collect_suite_calibration_summaries(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for check in checks:
        summary = check.get("suite_calibration_summary")
        if isinstance(summary, dict):
            summaries.append(summary)
    return summaries


def _collect_engine_advisory_summaries(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for check in checks:
        summary = check.get("engine_advisory_summary")
        if isinstance(summary, dict):
            summaries.append(summary)
    return summaries


def _collect_evidence_index_summaries(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for check in checks:
        summary = check.get("evidence_index_summary")
        if isinstance(summary, dict):
            summaries.append(summary)
    return summaries


def _collect_suite_audit_summaries(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for check in checks:
        summary = check.get("suite_audit_summary")
        if isinstance(summary, dict):
            summaries.append(summary)
    return summaries


def _collect_metric_coverage_summaries(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for check in checks:
        summary = check.get("metric_coverage_summary")
        if isinstance(summary, dict):
            summaries.append(summary)
    return summaries


def _collect_normalized_telemetry_summaries(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for check in checks:
        summary = check.get("normalized_telemetry_summary")
        if isinstance(summary, dict):
            summaries.append(summary)
        embedded = check.get("normalized_telemetry_summaries")
        if isinstance(embedded, list):
            summaries.extend(item for item in embedded if isinstance(item, dict))
    return summaries


def _collect_redaction_scan_summaries(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for check in checks:
        summary = check.get("redaction_scan_summary")
        if isinstance(summary, dict):
            summaries.append(summary)
    return summaries


def _collect_publication_bundle_summaries(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for check in checks:
        summary = check.get("publication_bundle_summary")
        if isinstance(summary, dict):
            summaries.append(summary)
        embedded = check.get("publication_bundle_summaries")
        if isinstance(embedded, list):
            summaries.extend(item for item in embedded if isinstance(item, dict))
    return summaries


def _collect_matrix_publication_bundle_summaries(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for check in checks:
        summary = check.get("matrix_publication_bundle_summary")
        if isinstance(summary, dict):
            summaries.append(summary)
        embedded = check.get("matrix_publication_bundle_summaries")
        if isinstance(embedded, list):
            summaries.extend(item for item in embedded if isinstance(item, dict))
    return summaries


def _collect_publication_brief_summaries(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for check in checks:
        summary = check.get("publication_brief_summary")
        if isinstance(summary, dict):
            summaries.append(summary)
        embedded = check.get("publication_brief_summaries")
        if isinstance(embedded, list):
            summaries.extend(item for item in embedded if isinstance(item, dict))
    return summaries


def _collect_matrix_scorecard_summaries(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for check in checks:
        summary = check.get("matrix_scorecard_summary")
        if isinstance(summary, dict):
            summaries.append(summary)
        embedded = check.get("matrix_scorecard_summaries")
        if isinstance(embedded, list):
            summaries.extend(item for item in embedded if isinstance(item, dict))
    return summaries


def _collect_implementation_status_summaries(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for check in checks:
        summary = check.get("implementation_status_summary")
        if isinstance(summary, dict):
            summaries.append(summary)
        embedded = check.get("implementation_status_summaries")
        if isinstance(embedded, list):
            summaries.extend(item for item in embedded if isinstance(item, dict))
    return summaries


def _collect_campaign_preflight_summaries(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for check in checks:
        summary = check.get("campaign_preflight_summary")
        if isinstance(summary, dict):
            summaries.append(summary)
        embedded = check.get("campaign_preflight_summaries")
        if isinstance(embedded, list):
            summaries.extend(item for item in embedded if isinstance(item, dict))
    return summaries


def _collect_selftest_report_summaries(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for check in checks:
        summary = check.get("selftest_report_summary")
        if isinstance(summary, dict):
            summaries.append(summary)
        embedded = check.get("selftest_report_summaries")
        if isinstance(embedded, list):
            summaries.extend(item for item in embedded if isinstance(item, dict))
    return summaries


def _collect_sdlc_validation_manifest_summaries(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for check in checks:
        summary = check.get("sdlc_validation_manifest_summary")
        if isinstance(summary, dict):
            summaries.append(summary)
        embedded = check.get("sdlc_validation_manifest_summaries")
        if isinstance(embedded, list):
            summaries.extend(item for item in embedded if isinstance(item, dict))
    return summaries


def _collect_benchmark_readiness_summaries(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for check in checks:
        summary = check.get("benchmark_readiness_summary")
        if isinstance(summary, dict):
            summaries.append(summary)
        embedded = check.get("benchmark_readiness_summaries")
        if isinstance(embedded, list):
            summaries.extend(item for item in embedded if isinstance(item, dict))
    return summaries


def _collect_provider_audit_summaries(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for check in checks:
        summary = check.get("provider_audit_summary")
        if isinstance(summary, dict):
            summaries.append(summary)
        embedded = check.get("provider_audit_summaries")
        if isinstance(embedded, list):
            summaries.extend(item for item in embedded if isinstance(item, dict))
    return summaries


def _collect_protocol_repair_posture_summaries(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for check in checks:
        summary = check.get("protocol_repair_posture_summary")
        if isinstance(summary, dict):
            summaries.append(summary)
        embedded = check.get("protocol_repair_posture_summaries")
        if isinstance(embedded, list):
            summaries.extend(item for item in embedded if isinstance(item, dict))
    return summaries


def _collect_workflow_readiness_summaries(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for check in checks:
        summary = check.get("workflow_readiness_summary")
        if isinstance(summary, dict):
            summaries.append(summary)
        embedded = check.get("workflow_readiness_summaries")
        if isinstance(embedded, list):
            summaries.extend(item for item in embedded if isinstance(item, dict))
    return summaries


def _collect_security_posture_summaries(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for check in checks:
        summary = check.get("security_posture_summary")
        if isinstance(summary, dict):
            summaries.append(summary)
        embedded = check.get("security_posture_summaries")
        if isinstance(embedded, list):
            summaries.extend(item for item in embedded if isinstance(item, dict))
    return summaries


def _normalized_telemetry_readiness_checks(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    readiness_checks = []
    for index, summary in enumerate(_collect_normalized_telemetry_summaries(checks), start=1):
        stats_requires_labeling = bool(summary.get("stats_requires_labeling"))
        advisory_fields = _non_negative_int(summary.get("advisory_field_count"))
        raw_provenance_fields = _non_negative_int(summary.get("raw_provenance_field_count"))
        missing_stats_fields = _summary_string_list(summary.get("missing_stats_fields"))
        if not stats_requires_labeling and not advisory_fields and not raw_provenance_fields and not missing_stats_fields:
            continue
        readiness_checks.append(
            _check(
                f"normalized_telemetry[{index}].stats_comparability",
                False,
                "warning",
                summary.get("archive_path"),
                "normalized telemetry has advisory, raw-provenance, or missing stats fields requiring disclosure",
                normalized_telemetry_summary=summary,
            )
        )
    return readiness_checks


def _matrix_scorecard_readiness_checks(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = _collect_matrix_scorecard_summaries(checks)
    if not summaries:
        return [
            _check(
                "matrix_scorecard_evidence",
                False,
                "warning",
                None,
                "matrix scorecard evidence was not supplied",
            )
        ]
    review_checks = []
    for index, summary in enumerate(summaries, start=1):
        telemetry = summary.get("telemetry_quality_summary") if isinstance(summary.get("telemetry_quality_summary"), dict) else {}
        quality_counts = telemetry.get("quality_counts") if isinstance(telemetry.get("quality_counts"), dict) else {}
        advisory_quality_count = sum(
            _non_negative_int(quality_counts.get(key))
            for key in ("inferred", "conditional", "raw_provenance", "unknown", "unavailable")
        )
        if not quality_counts:
            review_checks.append(
                _check(
                    f"matrix_scorecard_evidence[{index}].telemetry_quality",
                    False,
                    "warning",
                    summary.get("archive_path"),
                    "matrix scorecard has no telemetry quality summary",
                )
            )
        elif advisory_quality_count or _non_negative_int(telemetry.get("entries_with_comparison_guidance")):
            review_checks.append(
                _check(
                    f"matrix_scorecard_evidence[{index}].telemetry_quality",
                    False,
                    "warning",
                    summary.get("archive_path"),
                    "matrix scorecard telemetry quality requires disclosure",
                )
            )
        stats = summary.get("stats_comparability_summary") if isinstance(summary.get("stats_comparability_summary"), dict) else {}
        if _non_negative_int(stats.get("entries_requiring_labeling")):
            review_checks.append(
                _check(
                    f"matrix_scorecard_evidence[{index}].stats_comparability",
                    False,
                    "warning",
                    summary.get("archive_path"),
                    "matrix scorecard stats comparability requires disclosure",
                )
            )
        invalid_tool_calls = _non_negative_int(summary.get("invalid_tool_call_count"))
        parser_repair_cases = _non_negative_int(summary.get("tool_parser_repair_cases"))
        parser_repairs_valid = _non_negative_int(summary.get("tool_parser_repairs_valid"))
        if parser_repair_cases == 0:
            review_checks.append(
                _check(
                    f"matrix_scorecard_evidence[{index}].tool_parser_repair",
                    False,
                    "warning",
                    summary.get("archive_path"),
                    "matrix scorecard has no tool-parser repair evidence",
                )
            )
        elif parser_repairs_valid < parser_repair_cases:
            review_checks.append(
                _check(
                    f"matrix_scorecard_evidence[{index}].tool_parser_repair",
                    False,
                    "warning",
                    summary.get("archive_path"),
                    "matrix scorecard tool-parser repair validity requires disclosure",
                )
            )
        if invalid_tool_calls:
            review_checks.append(
                _check(
                    f"matrix_scorecard_evidence[{index}].invalid_tool_calls",
                    False,
                    "warning",
                    summary.get("archive_path"),
                    "matrix scorecard includes invalid tool-call emissions",
                )
            )
        evidence = summary.get("concurrency_evidence") if isinstance(summary.get("concurrency_evidence"), dict) else {}
        levels = evidence.get("concurrency_levels") if isinstance(evidence.get("concurrency_levels"), list) else []
        if not levels:
            review_checks.append(
                _check(
                    f"matrix_scorecard_evidence[{index}].concurrency",
                    False,
                    "warning",
                    summary.get("archive_path"),
                    "matrix scorecard has no concurrency evidence levels",
                )
            )
        elif len(levels) < 2:
            review_checks.append(
                _check(
                    f"matrix_scorecard_evidence[{index}].concurrency",
                    False,
                    "warning",
                    summary.get("archive_path"),
                    "matrix scorecard covers only one concurrency level",
                )
            )
    return review_checks


def _harness_review_summary(payload: dict[str, Any]) -> dict[str, Any]:
    suite = payload.get("suite") if isinstance(payload.get("suite"), dict) else {}
    review = payload.get("review") if isinstance(payload.get("review"), dict) else {}
    generator = payload.get("generator") if isinstance(payload.get("generator"), dict) else {}
    surface_counts = payload.get("surface_counts") if isinstance(payload.get("surface_counts"), dict) else {}
    assertion_counts = payload.get("assertion_counts") if isinstance(payload.get("assertion_counts"), dict) else {}
    summary: dict[str, Any] = {
        "schema_version": HARNESS_REVIEW_SCHEMA_VERSION,
        "suite_name": suite.get("name"),
        "case_count": _non_negative_int(suite.get("case_count")),
        "generated": bool(payload.get("generated")),
        "generator_profile": generator.get("profile"),
        "review_status": review.get("status"),
        "human_review_required": bool(review.get("human_review_required")),
        "calibration_required_before_release_gate": bool(review.get("calibration_required_before_release_gate")),
    }
    compact_surfaces = {
        key: _non_negative_int(surface_counts.get(key))
        for key in (
            "tool_schema_cases",
            "multi_tool_catalog_cases",
            "tool_loop_cases",
            "mcp_profile_cases",
            "lcp_profile_cases",
            "skill_cases",
            "cache_control_cases",
            "cancellation_cases",
        )
        if key in surface_counts
    }
    compact_assertions = {
        key: _non_negative_int(assertion_counts.get(key))
        for key in ("substring", "json_fields", "tool_name", "tool_result")
        if key in assertion_counts
    }
    if compact_surfaces:
        summary["surface_counts"] = compact_surfaces
    if compact_assertions:
        summary["assertion_counts"] = compact_assertions
    return {key: value for key, value in summary.items() if value is not None}


def _protocol_repair_posture_summary(payload: dict[str, Any]) -> dict[str, Any]:
    scorecard = payload.get("scorecard_summary") if isinstance(payload.get("scorecard_summary"), dict) else {}
    gate = payload.get("matrix_gate_summary") if isinstance(payload.get("matrix_gate_summary"), dict) else {}
    security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    return {
        "schema_version": PROTOCOL_REPAIR_POSTURE_SCHEMA_VERSION,
        "name": payload.get("name"),
        "status": payload.get("status"),
        "ready": payload.get("ready") if isinstance(payload.get("ready"), bool) else None,
        "scorecard_source_count": _non_negative_int(scorecard.get("source_count")),
        "scorecard_invalid_tool_call_count": _non_negative_int(scorecard.get("invalid_tool_call_count")),
        "scorecard_tool_parser_repair_cases": _non_negative_int(scorecard.get("tool_parser_repair_cases")),
        "scorecard_tool_parser_repairs_valid": _non_negative_int(scorecard.get("tool_parser_repairs_valid")),
        "matrix_gate_source_count": _non_negative_int(gate.get("source_count")),
        "matrix_gate_invalid_tool_call_count": _non_negative_int(gate.get("invalid_tool_call_count")),
        "matrix_gate_tool_parser_repair_cases": _non_negative_int(gate.get("tool_parser_repair_cases")),
        "matrix_gate_tool_parser_repairs_valid": _non_negative_int(gate.get("tool_parser_repairs_valid")),
        "matrix_gate_tool_parser_repair_artifacts_missing": _non_negative_int(
            gate.get("tool_parser_repair_artifacts_missing")
        ),
        "disclosure_count": len(payload.get("disclosures") if isinstance(payload.get("disclosures"), list) else []),
        "recommendation_count": len(payload.get("recommendations") if isinstance(payload.get("recommendations"), list) else []),
        "contains_raw_provider_payloads": bool(security.get("contains_raw_provider_payloads")),
        "contains_secrets": bool(security.get("contains_secrets")),
    }


def _workflow_readiness_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    return {
        "schema_version": WORKFLOW_READINESS_SCHEMA_VERSION,
        "name": payload.get("name"),
        "status": payload.get("status"),
        "ready": payload.get("ready") if isinstance(payload.get("ready"), bool) else None,
        "source_count": _non_negative_int(summary.get("source_count")),
        "case_count": _non_negative_int(summary.get("case_count")),
        "required_surface_count": _non_negative_int(summary.get("required_surface_count")),
        "covered_required_surface_count": _non_negative_int(summary.get("covered_required_surface_count")),
        "gap_count": _non_negative_int(summary.get("gap_count")),
        "max_concurrency": _non_negative_int(summary.get("max_concurrency")),
        "concurrency_levels": _summary_int_list(summary.get("concurrency_levels")),
        "required_surfaces": _summary_string_list(payload.get("required_surfaces")),
        "contains_raw_provider_payloads": bool(security.get("contains_raw_provider_payloads")),
        "contains_secrets": bool(security.get("contains_secrets")),
        "contacts_providers": bool(security.get("contacts_providers")),
    }


def _security_posture_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    secret_backend = (
        payload.get("secret_backend_posture") if isinstance(payload.get("secret_backend_posture"), dict) else {}
    )
    security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    return {
        "schema_version": SECURITY_POSTURE_SCHEMA_VERSION,
        "name": payload.get("name"),
        "status": payload.get("status"),
        "ready": payload.get("ready") if isinstance(payload.get("ready"), bool) else None,
        "blockers": _non_negative_int(summary.get("blockers")),
        "warnings": _non_negative_int(summary.get("warnings")),
        "provider_audit_count": _non_negative_int(summary.get("provider_audit_count")),
        "redaction_scan_count": _non_negative_int(summary.get("redaction_scan_count")),
        "review_artifact_count": _non_negative_int(summary.get("review_artifact_count")),
        "redaction_finding_count": _non_negative_int(summary.get("redaction_finding_count")),
        "unsafe_review_artifact_count": _non_negative_int(summary.get("unsafe_review_artifact_count")),
        "keyring_optional": bool(secret_backend.get("keyring_optional")),
        "keyring_dependency_available": bool(secret_backend.get("keyring_dependency_available")),
        "contains_raw_provider_payloads": bool(security.get("contains_raw_provider_payloads")),
        "contains_secrets": bool(security.get("contains_secrets")),
        "reads_keyring_values": bool(security.get("reads_keyring_values")),
        "resolves_secret_references": bool(security.get("resolves_secret_references")),
        "contacts_providers": bool(security.get("contacts_providers")),
    }


def _suite_calibration_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "schema_version": CALIBRATION_REPORT_SCHEMA_VERSION,
        "suite": payload.get("suite"),
        "generated": bool(payload.get("generated")),
        "require_release_gate": bool(payload.get("require_release_gate")),
        "passed": bool(payload.get("passed")),
        "known_good_runs": _non_negative_int(summary.get("known_good_runs")),
        "known_bad_cases": _non_negative_int(summary.get("known_bad_cases")),
        "failure_taxonomy_entries": _non_negative_int(summary.get("failure_taxonomy_entries")),
        "findings": _non_negative_int(summary.get("findings")),
        "warnings": _non_negative_int(summary.get("warnings")),
    }


def _engine_advisory_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary_block = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    summary = {
        "schema_version": ENGINE_ADVISORY_SCHEMA_VERSION,
        "engine": payload.get("engine"),
        "priority_count": _non_negative_int(summary_block.get("priority_count")),
        "highest_priority": summary_block.get("highest_priority"),
        "no_dispatch": bool(summary_block.get("no_dispatch")),
        "top_priorities": _compact_engine_priorities(payload.get("priorities")),
    }
    return {key: value for key, value in summary.items() if value is not None}


def _evidence_index_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "schema_version": EVIDENCE_INDEX_SCHEMA_VERSION,
        "name": payload.get("name"),
        "artifact_count": _non_negative_int(payload.get("artifact_count")),
        "status_counts": _int_map(payload.get("status_counts")),
        "readiness": _readiness_summary(payload.get("readiness")),
    }
    cleanup_evidence = _cleanup_evidence_summary(payload.get("cleanup_evidence"))
    if cleanup_evidence:
        summary["cleanup_evidence"] = cleanup_evidence
    return summary


def _cleanup_evidence_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "artifact_count": _non_negative_int(value.get("artifact_count")),
        "manual_report_count": _non_negative_int(value.get("manual_report_count")),
        "retention_report_count": _non_negative_int(value.get("retention_report_count")),
        "planned_report_count": _non_negative_int(value.get("planned_report_count")),
        "executed_report_count": _non_negative_int(value.get("executed_report_count")),
        "audit_log_required_count": _non_negative_int(value.get("audit_log_required_count")),
        "contains_local_paths": bool(value.get("contains_local_paths")),
        "direct_publication_safe": bool(value.get("direct_publication_safe")),
        "shareable_summary_only": bool(value.get("shareable_summary_only")),
    }


def _suite_audit_summary(payload: dict[str, Any]) -> dict[str, Any]:
    findings = payload.get("findings") if isinstance(payload.get("findings"), list) else []
    dataset_hygiene = payload.get("dataset_hygiene") if isinstance(payload.get("dataset_hygiene"), dict) else {}
    finding_codes = sorted(
        {
            str(item.get("code"))
            for item in findings
            if isinstance(item, dict) and item.get("code")
        }
    )
    return {
        "schema_version": SUITE_AUDIT_SCHEMA_VERSION,
        "suite": payload.get("suite"),
        "total_cases": _non_negative_int(payload.get("total_cases")),
        "finding_count": len(findings),
        "finding_codes": finding_codes[:12],
        "provenance_counts": _int_map(payload.get("provenance_counts")),
        "risk_counts": _int_map(payload.get("risk_counts")),
        "duplicate_fingerprint_count": _non_negative_int(dataset_hygiene.get("duplicate_fingerprint_count")),
    }


def _metric_coverage_summary(payload: dict[str, Any]) -> dict[str, Any]:
    provider = payload.get("provider") if isinstance(payload.get("provider"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    comparability = payload.get("comparability") if isinstance(payload.get("comparability"), dict) else {}
    claim_contract = payload.get("claim_contract") if isinstance(payload.get("claim_contract"), dict) else {}
    return {
        "schema_version": METRIC_COVERAGE_SCHEMA_VERSION,
        "provider": provider.get("name"),
        "contract": provider.get("contract"),
        "native_adapter": provider.get("native_adapter"),
        "coverage_score": summary.get("coverage_score"),
        "field_count": _non_negative_int(summary.get("field_count")),
        "counts": _int_map(summary.get("counts")),
        "publication_grade_group_count": _non_negative_int(comparability.get("publication_grade_group_count")),
        "advisory_group_count": _non_negative_int(comparability.get("advisory_group_count")),
        "partial_group_count": _non_negative_int(comparability.get("partial_group_count")),
        "unavailable_group_count": _non_negative_int(comparability.get("unavailable_group_count")),
        "publication_grade_groups": _summary_string_list(comparability.get("publication_grade_groups")),
        "review_required_groups": _summary_string_list(comparability.get("review_required_groups")),
        "claim_contract": _compact_metric_claim_contract(claim_contract),
    }


def _compact_metric_claim_contract(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "schema_version": value.get("schema_version"),
        "claim_status_counts": _int_map(value.get("claim_status_counts")),
        "leaderboard_eligible_groups": _summary_string_list(value.get("leaderboard_eligible_groups")),
        "disclosure_required_groups": _summary_string_list(value.get("disclosure_required_groups")),
        "primary_score_policy": value.get("primary_score_policy"),
    }


def _normalized_telemetry_summary(payload: dict[str, Any]) -> dict[str, Any]:
    existing = payload.get("review_summary") if isinstance(payload.get("review_summary"), dict) else {}
    source = existing if existing.get("schema_version") == NORMALIZED_TELEMETRY_SCHEMA_VERSION else payload
    values = payload.get("values") if isinstance(payload.get("values"), dict) else {}
    quality = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
    comparison = payload.get("comparison_readiness") if isinstance(payload.get("comparison_readiness"), dict) else {}
    stats = payload.get("stats_comparability") if isinstance(payload.get("stats_comparability"), dict) else {}
    quality_counts = source.get("quality_counts")
    if not isinstance(quality_counts, dict):
        quality_counts = {}
        for status in quality.values():
            key = str(status)
            quality_counts[key] = quality_counts.get(key, 0) + 1
    populated_field_count = source.get("populated_field_count")
    if populated_field_count is None:
        populated_field_count = len(
            [
                field
                for field, value in values.items()
                if value is not None and field not in {"raw_usage", "raw_stats"}
            ]
        )
    missing = payload.get("missing") if isinstance(payload.get("missing"), list) else []
    summary = {
        "schema_version": NORMALIZED_TELEMETRY_SCHEMA_VERSION,
        "contract": source.get("contract") or payload.get("contract"),
        "native_adapter": source.get("native_adapter") or payload.get("native_adapter"),
        "stats_profile": source.get("stats_profile") or payload.get("stats_profile") or stats.get("profile"),
        "populated_field_count": _non_negative_int(populated_field_count),
        "missing_field_count": _non_negative_int(source.get("missing_field_count") if source.get("missing_field_count") is not None else len(missing)),
        "publication_grade_field_count": _non_negative_int(
            source.get("publication_grade_field_count")
            if source.get("publication_grade_field_count") is not None
            else comparison.get("publication_grade_field_count")
        ),
        "advisory_field_count": _non_negative_int(
            source.get("advisory_field_count")
            if source.get("advisory_field_count") is not None
            else comparison.get("advisory_field_count")
        ),
        "raw_provenance_field_count": _non_negative_int(
            source.get("raw_provenance_field_count")
            if source.get("raw_provenance_field_count") is not None
            else comparison.get("raw_provenance_field_count")
        ),
        "comparison_guidance": source.get("comparison_guidance") or comparison.get("guidance"),
        "quality_counts": _int_map(quality_counts),
        "stats_requires_labeling": bool(
            source.get("stats_requires_labeling")
            if source.get("stats_requires_labeling") is not None
            else stats.get("requires_labeling")
        ),
        "stats_guidance": source.get("stats_guidance") or stats.get("guidance"),
        "stats_publication_grade_fields": _summary_string_list(
            source.get("stats_publication_grade_fields") or stats.get("publication_grade_fields")
        ),
        "stats_advisory_fields": _summary_string_list(
            source.get("stats_advisory_fields") or stats.get("advisory_fields")
        ),
        "missing_stats_fields": _summary_string_list(source.get("missing_stats_fields") or stats.get("missing_stats_fields")),
    }
    return {key: value for key, value in summary.items() if value is not None}


def _redaction_scan_summary(payload: dict[str, Any]) -> dict[str, Any]:
    findings = payload.get("findings") if isinstance(payload.get("findings"), list) else []
    pattern_counts: dict[str, int] = {}
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        pattern = str(finding.get("pattern") or "unknown")
        pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
    return {
        "schema_version": REDACTION_SCAN_SCHEMA_VERSION,
        "ok": payload.get("ok") if isinstance(payload.get("ok"), bool) else None,
        "total_paths": _non_negative_int(payload.get("total_paths")),
        "scanned_items": _non_negative_int(payload.get("scanned_items")),
        "skipped_items": _non_negative_int(payload.get("skipped_items")),
        "finding_count": len([finding for finding in findings if isinstance(finding, dict)]),
        "pattern_counts": dict(sorted(pattern_counts.items())),
        "shareable_summary_only": True,
    }


def _publication_bundle_summary(payload: dict[str, Any]) -> dict[str, Any]:
    readiness = payload.get("publication_readiness") if isinstance(payload.get("publication_readiness"), dict) else {}
    security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    return {
        "schema_version": PUBLICATION_BUNDLE_MANIFEST_SCHEMA_VERSION,
        "run_id": payload.get("run_id"),
        "artifact_count": _non_negative_int(payload.get("artifact_count")),
        "artifacts": _summary_string_list(payload.get("artifacts")),
        "media_kit": _media_kit_summary(payload.get("media_kit")),
        "publication_readiness": {
            "schema_version": readiness.get("schema_version"),
            "status": str(readiness.get("status") or "unknown"),
            "ready_for_external_publication": bool(readiness.get("ready_for_external_publication")),
            "ready_for_internal_review": bool(readiness.get("ready_for_internal_review")),
            "blocker_count": _non_negative_int(readiness.get("blocker_count")),
            "warning_count": _non_negative_int(readiness.get("warning_count")),
        },
        "security": {
            "contains_raw_secrets": bool(security.get("contains_raw_secrets")),
            "contains_raw_provider_payloads": bool(security.get("contains_raw_provider_payloads")),
            "contains_results_jsonl": bool(security.get("contains_results_jsonl")),
        },
    }


def _publication_bundle_review_summary(payload: dict[str, Any], *, archive_path: str) -> dict[str, Any]:
    summary = _publication_bundle_summary(payload)
    if archive_path:
        summary["archive_path"] = archive_path
    return summary


def _matrix_publication_bundle_summary(payload: dict[str, Any], *, archive_path: str = "") -> dict[str, Any]:
    security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    matrix = payload.get("matrix") if isinstance(payload.get("matrix"), dict) else {}
    media_kit = _media_kit_summary(payload.get("media_kit"))
    summary: dict[str, Any] = {
        "schema_version": MATRIX_PUBLICATION_BUNDLE_MANIFEST_SCHEMA_VERSION,
        "artifact_count": _non_negative_int(payload.get("artifact_count")),
        "artifacts": _summary_string_list(payload.get("artifacts")),
        "matrix": {
            "artifact_stem": matrix.get("artifact_stem"),
            "summary_artifact": matrix.get("summary_artifact"),
            "scorecard_artifact": matrix.get("scorecard_artifact"),
        },
        "engine_targets": _compact_engine_targets(payload.get("engine_targets")),
        "architecture_summary": _compact_scorecard_group_summary(
            payload.get("architecture_summary"),
            key="model_architecture",
        ),
        "quantization_summary": _compact_scorecard_group_summary(
            payload.get("quantization_summary"),
            key="quantization",
        ),
        "media_kit": media_kit,
        "security": {
            "contains_raw_secrets": bool(security.get("contains_raw_secrets")),
            "contains_raw_provider_payloads": bool(security.get("contains_raw_provider_payloads")),
            "contains_results_jsonl": bool(security.get("contains_results_jsonl")),
            "contains_per_run_raw_traces": bool(security.get("contains_per_run_raw_traces")),
        },
    }
    if archive_path:
        summary["archive_path"] = archive_path
    return summary


def _matrix_publication_bundle_status(summary: dict[str, Any]) -> tuple[str, str]:
    security = summary.get("security") if isinstance(summary.get("security"), dict) else {}
    if any(
        security.get(key) is True
        for key in (
            "contains_raw_secrets",
            "contains_raw_provider_payloads",
            "contains_results_jsonl",
            "contains_per_run_raw_traces",
        )
    ):
        return "fail", "security"
    media_kit = summary.get("media_kit") if isinstance(summary.get("media_kit"), dict) else {}
    if media_kit.get("schema_version") != MEDIA_KIT_SCHEMA_VERSION:
        return "review", "media_kit.schema_version"
    missing = media_kit.get("missing_recommended_assets")
    if isinstance(missing, list) and missing:
        return "review", "media_kit.missing_recommended_assets"
    return "pass", "media_kit"


def _media_kit_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {
            "schema_version": None,
            "asset_count": 0,
            "missing_recommended_assets": [],
            "available_recommended_sets": [],
            "asset_roles": [],
        }
    assets = value.get("assets") if isinstance(value.get("assets"), list) else []
    recommended_sets = value.get("recommended_sets") if isinstance(value.get("recommended_sets"), list) else []
    return {
        "schema_version": value.get("schema_version"),
        "asset_count": _non_negative_int(value.get("asset_count")),
        "missing_recommended_assets": _summary_string_list(value.get("missing_recommended_assets")),
        "available_recommended_sets": [
            str(item.get("name"))
            for item in recommended_sets
            if isinstance(item, dict) and item.get("available") is True and item.get("name")
        ][:12],
        "asset_roles": [
            {
                "artifact": str(item.get("artifact")),
                "role": str(item.get("role")),
                "media_type": str(item.get("media_type")),
                "present": bool(item.get("present")),
            }
            for item in assets[:20]
            if isinstance(item, dict) and item.get("artifact")
        ],
    }


def _publication_brief_summary(payload: dict[str, Any]) -> dict[str, Any]:
    claim_readiness = payload.get("claim_readiness") if isinstance(payload.get("claim_readiness"), dict) else {}
    security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    proof_points = payload.get("proof_points") if isinstance(payload.get("proof_points"), list) else []
    disclosures = payload.get("disclosures") if isinstance(payload.get("disclosures"), list) else []
    matrix_scorecards = payload.get("matrix_scorecards") if isinstance(payload.get("matrix_scorecards"), list) else []
    ready = payload.get("ready")
    status = payload.get("status")
    if status is None:
        status = "pass" if ready is True else ("review" if ready is False else "informational")
    if security.get("contains_secrets") is True or security.get("contains_raw_provider_payloads") is True:
        status = "fail"
    summary = {
        "schema_version": PUBLICATION_BRIEF_SCHEMA_VERSION,
        "status": status,
        "name": _safe_artifact_label(payload.get("name"), "publication-brief.json"),
        "ready": ready if isinstance(ready, bool) else None,
        "source_artifact_count": _non_negative_int(
            payload.get("source_artifact_count") or security.get("source_artifact_count")
        ),
        "proof_point_count": _non_negative_int(payload.get("proof_point_count") or len(proof_points)),
        "disclosure_count": _non_negative_int(payload.get("disclosure_count") or len(disclosures)),
        "matrix_scorecard_count": _non_negative_int(payload.get("matrix_scorecard_count") or len(matrix_scorecards)),
        "engine_targets": _compact_engine_targets(payload.get("engine_targets")),
        "architecture_summary": _compact_scorecard_group_summary(
            payload.get("architecture_summary"),
            key="model_architecture",
        ),
        "quantization_summary": _compact_scorecard_group_summary(
            payload.get("quantization_summary"),
            key="quantization",
        ),
        **(
            {"protocol_repair_summary": _compact_protocol_repair_summary(payload.get("protocol_repair_summary"))}
            if isinstance(payload.get("protocol_repair_summary"), dict)
            else {}
        ),
        "claim_checks": _non_negative_int(payload.get("claim_checks") or claim_readiness.get("checks")),
        "claim_blockers": _non_negative_int(payload.get("claim_blockers") or claim_readiness.get("blockers")),
        "claim_warnings": _non_negative_int(payload.get("claim_warnings") or claim_readiness.get("warnings")),
        "contains_raw_provider_payloads": bool(
            payload.get("contains_raw_provider_payloads") or security.get("contains_raw_provider_payloads")
        ),
        "contains_secrets": bool(payload.get("contains_secrets") or security.get("contains_secrets")),
        "shareable_summary_only": True,
        "archive_path": payload.get("archive_path"),
    }
    return {key: value for key, value in summary.items() if value is not None}


def _matrix_scorecard_summary(payload: dict[str, Any]) -> dict[str, Any]:
    matrix = payload.get("matrix") if isinstance(payload.get("matrix"), dict) else {}
    scorecard = payload.get("scorecard") if isinstance(payload.get("scorecard"), dict) else {}
    source = scorecard if scorecard else payload
    summary = {
        "schema_version": MATRIX_SCORECARD_SCHEMA_VERSION,
        "matrix": matrix.get("name") if matrix else payload.get("matrix"),
        "completed_runs": _non_negative_int(matrix.get("completed_runs") if matrix else payload.get("completed_runs")),
        "total_runs": _non_negative_int(matrix.get("total_runs") if matrix else payload.get("total_runs")),
        "failed_runs": _non_negative_int(matrix.get("failed_runs") if matrix else payload.get("failed_runs")),
        "entry_count": _non_negative_int(source.get("entry_count")),
        "result_artifacts_loaded": _non_negative_int(source.get("result_artifacts_loaded")),
        "total_cases": _non_negative_int(source.get("total_cases")),
        "passed_cases": _non_negative_int(source.get("passed_cases")),
        "failed_cases": _non_negative_int(source.get("failed_cases")),
        "pass_rate_percent": _number_or_none(source.get("pass_rate_percent")),
        "judge_rubric_cases": _non_negative_int(source.get("judge_rubric_cases")),
        "judge_verdicts_valid": _non_negative_int(source.get("judge_verdicts_valid")),
        "invalid_tool_call_count": _non_negative_int(source.get("invalid_tool_call_count")),
        "tool_parser_repair_cases": _non_negative_int(source.get("tool_parser_repair_cases")),
        "tool_parser_repairs_valid": _non_negative_int(source.get("tool_parser_repairs_valid")),
        "tool_parser_repair_valid_rate_percent": _number_or_none(source.get("tool_parser_repair_valid_rate_percent")),
        "failure_class_summary": _normalize_failure_class_summary(source.get("failure_class_summary")),
        "tool_loop_stop_summary": _normalize_tool_loop_stop_summary(source.get("tool_loop_stop_summary")),
        "telemetry_quality_summary": _compact_telemetry_quality_summary(source.get("telemetry_quality_summary")),
        "stats_comparability_summary": _compact_stats_comparability_summary(source.get("stats_comparability_summary")),
        "concurrency_evidence": _compact_scorecard_concurrency_evidence(source.get("concurrency_evidence")),
        "engine_targets": _compact_engine_targets(source.get("engine_targets") or payload.get("engine_targets")),
        "architecture_summary": _compact_scorecard_group_summary(
            payload.get("architecture_summary") or source.get("architecture_summary"),
            key="model_architecture",
        ),
        "quantization_summary": _compact_scorecard_group_summary(
            payload.get("quantization_summary") or source.get("quantization_summary"),
            key="quantization",
        ),
    }
    return {key: value for key, value in summary.items() if value is not None}


def _selftest_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "schema_version": SELFTEST_REPORT_SCHEMA_VERSION,
        "run_id": payload.get("run_id"),
        "tier": payload.get("tier"),
        "ok": payload.get("ok"),
        "exit_code": _non_negative_int(payload.get("exit_code")),
        "duration_ms": _number_or_none(payload.get("duration_ms")),
        "browser": payload.get("browser"),
        "headed": bool(payload.get("headed")),
        "marker_expression": payload.get("marker_expression"),
        "junit_xml_present": bool(payload.get("junit_xml") or payload.get("junit_xml_present")),
        "archive_path": payload.get("archive_path"),
    }
    return {key: value for key, value in summary.items() if value is not None}


def _compact_protocol_repair_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "status": value.get("status"),
        "source_scorecard_count": _non_negative_int(value.get("source_scorecard_count")),
        "invalid_tool_call_count": _non_negative_int(value.get("invalid_tool_call_count")),
        "tool_parser_repair_cases": _non_negative_int(value.get("tool_parser_repair_cases")),
        "tool_parser_repairs_valid": _non_negative_int(value.get("tool_parser_repairs_valid")),
        "tool_parser_repair_valid_rate_percent": _number_or_none(
            value.get("tool_parser_repair_valid_rate_percent")
        ),
        "matrix_gate_invalid_tool_call_count": _non_negative_int(
            value.get("matrix_gate_invalid_tool_call_count")
        ),
        "matrix_gate_tool_parser_repair_cases": _non_negative_int(
            value.get("matrix_gate_tool_parser_repair_cases")
        ),
        "matrix_gate_tool_parser_repairs_valid": _non_negative_int(
            value.get("matrix_gate_tool_parser_repairs_valid")
        ),
        "matrix_gate_tool_parser_repair_valid_rate_percent": _number_or_none(
            value.get("matrix_gate_tool_parser_repair_valid_rate_percent")
        ),
        "matrix_gate_tool_parser_repair_artifacts_missing": _non_negative_int(
            value.get("matrix_gate_tool_parser_repair_artifacts_missing")
        ),
    }


def _sdlc_validation_manifest_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary_block = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    gui = payload.get("gui") if isinstance(payload.get("gui"), dict) else {}
    release_evidence = payload.get("release_evidence") if isinstance(payload.get("release_evidence"), dict) else {}
    security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    stable_selectors = gui.get("stable_selectors") if isinstance(gui.get("stable_selectors"), list) else []
    api_surfaces = gui.get("api_surfaces") if isinstance(gui.get("api_surfaces"), list) else []
    expected_artifacts = (
        release_evidence.get("expected_artifacts")
        if isinstance(release_evidence.get("expected_artifacts"), list)
        else []
    )
    status = payload.get("status") or "review"
    if security.get("contains_secrets") is True or security.get("contains_raw_provider_payloads") is True:
        status = "fail"
    summary = {
        "schema_version": SDLC_VALIDATION_MANIFEST_SCHEMA_VERSION,
        "status": status,
        "name": _safe_artifact_label(payload.get("name"), "sdlc-validation-manifest.json"),
        "tier_count": _non_negative_int(payload.get("tier_count") or summary_block.get("tier_count")),
        "required_gate_count": _non_negative_int(payload.get("required_gate_count") or summary_block.get("required_gate_count")),
        "blocking_gate_count": _non_negative_int(payload.get("blocking_gate_count") or summary_block.get("blocking_gate_count")),
        "chrome_flow_count": _non_negative_int(payload.get("chrome_flow_count") or summary_block.get("chrome_flow_count")),
        "chrome_validation_step_count": _non_negative_int(
            payload.get("chrome_validation_step_count") or summary_block.get("chrome_validation_step_count")
        ),
        "chrome_tool": payload.get("chrome_tool") or gui.get("chrome_tool"),
        "stable_selector_count": _non_negative_int(payload.get("stable_selector_count") or len(stable_selectors)),
        "api_surface_count": _non_negative_int(payload.get("api_surface_count") or len(api_surfaces)),
        "expected_artifact_count": _non_negative_int(payload.get("expected_artifact_count") or len(expected_artifacts)),
        "runs_tests": bool(payload.get("runs_tests") or security.get("runs_tests")),
        "contacts_providers": bool(payload.get("contacts_providers") or security.get("contacts_providers")),
        "contains_raw_provider_payloads": bool(
            payload.get("contains_raw_provider_payloads") or security.get("contains_raw_provider_payloads")
        ),
        "contains_secrets": bool(payload.get("contains_secrets") or security.get("contains_secrets")),
        "shareable_summary_only": True,
        "archive_path": payload.get("archive_path"),
    }
    return {key: value for key, value in summary.items() if value is not None}


def _safe_artifact_label(value: Any, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return Path(value).name
    return default


def _benchmark_readiness_summary(payload: dict[str, Any]) -> dict[str, Any]:
    report_summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else payload
    summary = {
        "schema_version": READINESS_SCHEMA_VERSION,
        "provider": payload.get("provider"),
        "suite": payload.get("suite"),
        "model": payload.get("model"),
        "ready": payload.get("ready") if isinstance(payload.get("ready"), bool) else None,
        "strict_unknown": payload.get("strict_unknown") if isinstance(payload.get("strict_unknown"), bool) else None,
        "policy_ok": report_summary.get("policy_ok") if isinstance(report_summary.get("policy_ok"), bool) else None,
        "suite_compatible": report_summary.get("suite_compatible") if isinstance(report_summary.get("suite_compatible"), bool) else None,
        "contract_checks_planned": _non_negative_int(report_summary.get("contract_checks_planned")),
        "contract_capabilities_directly_checked": _non_negative_int(
            report_summary.get("contract_capabilities_directly_checked")
        ),
        "contract_capabilities_proxy_checked": _non_negative_int(
            report_summary.get("contract_capabilities_proxy_checked")
        ),
        "contract_capabilities_not_covered": _non_negative_int(
            report_summary.get("contract_capabilities_not_covered")
        ),
        "metric_coverage_score": report_summary.get("metric_coverage_score"),
        "provider_auth_writable_backends": _non_negative_int(report_summary.get("provider_auth_writable_backends")),
        "provider_auth_plaintext_fallbacks": _non_negative_int(report_summary.get("provider_auth_plaintext_fallbacks")),
        "provider_auth_prewrite_policy_guards_recommended": _non_negative_int(
            report_summary.get("provider_auth_prewrite_policy_guards_recommended")
        ),
        "blocking_findings": _non_negative_int(report_summary.get("blocking_findings")),
        "warnings": _non_negative_int(report_summary.get("warnings")),
        "provider_auth_posture": _compact_provider_auth_posture(payload.get("provider_auth_posture")),
        "archive_path": payload.get("archive_path"),
    }
    return {key: value for key, value in summary.items() if value is not None}


def _provider_audit_summary(payload: dict[str, Any]) -> dict[str, Any]:
    embedded = payload.get("provider_audit_summaries")
    if isinstance(embedded, list) and embedded and isinstance(embedded[0], dict):
        return {str(key): value for key, value in embedded[0].items()}
    providers = payload.get("providers") if isinstance(payload.get("providers"), list) else []
    finding_codes = sorted(
        {
            str(finding.get("code"))
            for provider in providers
            if isinstance(provider, dict)
            for finding in (provider.get("findings") if isinstance(provider.get("findings"), list) else [])
            if isinstance(finding, dict) and finding.get("code")
        }
    )
    policy_controls = payload.get("policy_controls") if isinstance(payload.get("policy_controls"), dict) else {}
    secret_backend = _compact_secret_backend_posture(payload.get("secret_backend_posture"))
    summary = {
        "schema_version": PROVIDER_AUDIT_SCHEMA_VERSION,
        "total_providers": _non_negative_int(payload.get("total_providers")),
        "remote_providers": _non_negative_int(payload.get("remote_providers")),
        "policy_ok_count": _non_negative_int(payload.get("policy_ok")),
        "error_count": _non_negative_int(payload.get("errors")),
        "warning_count": _non_negative_int(payload.get("warnings")),
        "plaintext_dotenv_provider_count": sum(
            1 for provider in providers if isinstance(provider, dict) and provider.get("api_key_ref_plaintext_fallback")
        ),
        "writable_secret_backend_count": sum(
            1 for provider in providers if isinstance(provider, dict) and provider.get("api_key_ref_writable_backend")
        ),
        "prewrite_policy_guard_recommended_count": sum(
            1 for provider in providers if isinstance(provider, dict) and provider.get("prewrite_policy_guard_recommended")
        ),
        "keyring_required_provider_count": sum(
            1 for provider in providers if isinstance(provider, dict) and provider.get("keyring_backend_required")
        ),
        "keyring_dependency_available": secret_backend.get("keyring_dependency_available"),
        "secret_backend_posture": secret_backend,
        "provider_auth_posture": _compact_provider_auth_posture(
            [
                {
                    "provider": provider.get("name"),
                    "api_key_ref_kind": provider.get("api_key_ref_kind"),
                    "api_key_ref_configured": provider.get("api_key_ref_configured"),
                    "api_key_ref_writable_backend": provider.get("api_key_ref_writable_backend"),
                    "api_key_ref_plaintext_fallback": provider.get("api_key_ref_plaintext_fallback"),
                    "prewrite_policy_guard_recommended": provider.get("prewrite_policy_guard_recommended"),
                }
                for provider in providers
                if isinstance(provider, dict)
            ]
        ),
        "finding_codes": finding_codes[:12],
        "policy_controls": {str(key): bool(value) for key, value in policy_controls.items()},
        "shareable_summary_only": True,
        "archive_path": payload.get("archive_path"),
    }
    return {key: value for key, value in summary.items() if value is not None}


def _implementation_status_summary(payload: dict[str, Any]) -> dict[str, Any]:
    suite_inventory = payload.get("suite_inventory") if isinstance(payload.get("suite_inventory"), dict) else {}
    requirements = payload.get("requirements_inventory") if isinstance(payload.get("requirements_inventory"), dict) else {}
    target_engines = requirements.get("target_engines") if isinstance(requirements.get("target_engines"), dict) else {}
    provider_contracts = (
        requirements.get("provider_contracts") if isinstance(requirements.get("provider_contracts"), dict) else {}
    )
    model_targets = requirements.get("model_targets") if isinstance(requirements.get("model_targets"), dict) else {}
    agentic = requirements.get("agentic_workflows") if isinstance(requirements.get("agentic_workflows"), dict) else {}
    harness = requirements.get("harness_engineering") if isinstance(requirements.get("harness_engineering"), dict) else {}
    stats = requirements.get("stats_comparability") if isinstance(requirements.get("stats_comparability"), dict) else {}
    enterprise = (
        requirements.get("enterprise_controls") if isinstance(requirements.get("enterprise_controls"), dict) else {}
    )
    publication = (
        requirements.get("publication_governance")
        if isinstance(requirements.get("publication_governance"), dict)
        else {}
    )
    selftest = requirements.get("selftest_harness") if isinstance(requirements.get("selftest_harness"), dict) else {}
    validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else {}
    implementation_status = payload.get("implementation_status") or payload.get("status")
    summary = {
        "schema_version": IMPLEMENTATION_STATUS_SCHEMA_VERSION,
        "status": implementation_status,
        "implementation_status": implementation_status,
        "implemented_areas": _non_negative_int(payload.get("implemented_areas")),
        "partial_areas": _non_negative_int(payload.get("partial_areas")),
        "missing_areas": _non_negative_int(payload.get("missing_areas")),
        "built_in_suite_count": _non_negative_int(suite_inventory.get("built_in_suite_count")),
        "harness_engineering_suite_present": bool(suite_inventory.get("harness_engineering_suite_present")),
        "harness_engineering_case_count": len(_summary_string_list(suite_inventory.get("harness_engineering_cases"))),
        "target_engine_count": _non_negative_int(target_engines.get("count")),
        "provider_preset_count": _non_negative_int(provider_contracts.get("preset_count")),
        "model_target_count": _non_negative_int(model_targets.get("catalog_count")),
        "initial_model_targets_present": bool(model_targets.get("initial_targets_present")),
        "agent_profile_count": _non_negative_int(agentic.get("profile_count")),
        "harness_profile_count": _non_negative_int(harness.get("profile_count")),
        "stats_profile_count": _non_negative_int(stats.get("profile_count")),
        "stats_metric_provider_count": _non_negative_int(stats.get("metric_provider_count")),
        "stats_publication_requires_labels": bool(stats.get("publication_requires_labels_for_non_native_stats")),
        "keyring_optional": bool(enterprise.get("keyring_optional")),
        "secret_backends": _summary_string_list(enterprise.get("secret_backends")),
        "publication_governance_consumers": len(_summary_string_list(publication.get("redaction_safe_summary_consumers"))),
        "selftest_report_schema": selftest.get("report_schema"),
        "chrome_codex_gate_present": bool(selftest.get("chrome_codex_gate_present")),
        "tests_run_by_this_command": bool(validation.get("tests_run_by_this_command")),
        "validation_required_next_step": validation.get("required_next_step"),
        "shareable_summary_only": True,
        "archive_path": payload.get("archive_path"),
    }
    return {key: value for key, value in summary.items() if value is not None}


def _compact_provider_auth_posture(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    posture = []
    for item in value:
        if not isinstance(item, dict):
            continue
        posture.append(
            {
                "provider": item.get("provider"),
                "api_key_ref_kind": item.get("api_key_ref_kind"),
                "api_key_ref_configured": bool(item.get("api_key_ref_configured")),
                "api_key_ref_writable_backend": bool(item.get("api_key_ref_writable_backend")),
                "api_key_ref_plaintext_fallback": bool(item.get("api_key_ref_plaintext_fallback")),
                "prewrite_policy_guard_recommended": bool(item.get("prewrite_policy_guard_recommended")),
            }
        )
    return posture[:12]


def _compact_secret_backend_posture(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    supported = value.get("supported_secret_ref_kinds") if isinstance(value.get("supported_secret_ref_kinds"), list) else []
    recommended = (
        value.get("recommended_enterprise_backends") if isinstance(value.get("recommended_enterprise_backends"), list) else []
    )
    return {
        "env_reference_portable": bool(value.get("env_reference_portable")),
        "keyring_optional": bool(value.get("keyring_optional")),
        "keyring_dependency_available": bool(value.get("keyring_dependency_available")),
        "dotenv_plaintext_fallback_supported": bool(value.get("dotenv_plaintext_fallback_supported")),
        "dotenv_plaintext_fallback_enterprise_default": bool(value.get("dotenv_plaintext_fallback_enterprise_default")),
        "supported_secret_ref_kinds": [str(item) for item in supported[:6]],
        "recommended_enterprise_backends": [str(item) for item in recommended[:6]],
    }


def _compact_telemetry_quality_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "quality_counts": _int_map(value.get("quality_counts")),
        "guidance_counts": _int_map(value.get("guidance_counts")),
        "entries_with_advisory_quality": _non_negative_int(value.get("entries_with_advisory_quality")),
        "entries_with_unknown_quality": _non_negative_int(value.get("entries_with_unknown_quality")),
        "entries_with_comparison_guidance": _non_negative_int(value.get("entries_with_comparison_guidance")),
    }


def _compact_stats_comparability_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "schema_version": value.get("schema_version"),
        "profile_counts": _int_map(value.get("profile_counts")),
        "guidance_counts": _int_map(value.get("guidance_counts")),
        "entries_requiring_labeling": _non_negative_int(value.get("entries_requiring_labeling")),
    }


def _compact_scorecard_concurrency_evidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "schema_version": value.get("schema_version"),
        "entry_count": _non_negative_int(value.get("entry_count")),
        "artifact_loaded_count": _non_negative_int(value.get("artifact_loaded_count")),
        "concurrency_levels": _summary_int_list(value.get("concurrency_levels")),
        "multi_level": bool(value.get("multi_level")),
        "max_concurrency": _non_negative_int(value.get("max_concurrency")),
        "max_avg_queue_ms": _number_or_none(value.get("max_avg_queue_ms")),
        "max_avg_rate_limit_wait_ms": _number_or_none(value.get("max_avg_rate_limit_wait_ms")),
        "guidance": value.get("guidance"),
        "highest_queue_wait_entries": _compact_scorecard_concurrency_entries(value.get("highest_queue_wait_entries")),
        "highest_rate_limit_wait_entries": _compact_scorecard_concurrency_entries(value.get("highest_rate_limit_wait_entries")),
    }


def _compact_engine_targets(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    targets: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        targets.append(
            {
                "id": str(item.get("id")),
                "display_name": str(item.get("display_name")) if item.get("display_name") is not None else None,
                "primary_scoring_contract": (
                    str(item.get("primary_scoring_contract"))
                    if item.get("primary_scoring_contract") is not None
                    else None
                ),
            }
        )
    return targets[:12]


def _compact_scorecard_group_summary(value: Any, *, key: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                key: str(item.get(key) or "unknown"),
                "runs": _non_negative_int(item.get("runs")),
                "failed_runs": _non_negative_int(item.get("failed_runs")),
                "completed_runs": _non_negative_int(item.get("completed_runs")),
                "result_artifacts_loaded": _non_negative_int(item.get("result_artifacts_loaded")),
                "total_cases": _non_negative_int(item.get("total_cases")),
                "passed": _non_negative_int(item.get("passed")),
                "failed": _non_negative_int(item.get("failed")),
                "pass_rate_percent": _number_or_none(item.get("pass_rate_percent")),
                "avg_latency_ms": _number_or_none(item.get("avg_latency_ms")),
                "avg_decode_tokens_per_second": _number_or_none(item.get("avg_decode_tokens_per_second")),
                "judge_rubric_cases": _non_negative_int(item.get("judge_rubric_cases")),
                "judge_verdicts_valid": _non_negative_int(item.get("judge_verdicts_valid")),
                "invalid_tool_call_count": _non_negative_int(item.get("invalid_tool_call_count")),
                "tool_parser_repair_cases": _non_negative_int(item.get("tool_parser_repair_cases")),
                "tool_parser_repairs_valid": _non_negative_int(item.get("tool_parser_repairs_valid")),
                "tool_parser_repair_valid_rate_percent": _number_or_none(
                    item.get("tool_parser_repair_valid_rate_percent")
                ),
            }
        )
    return rows[:12]


def _compact_scorecard_concurrency_entries(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    entries = []
    for item in value:
        if not isinstance(item, dict):
            continue
        entries.append(
            {
                "run_id": item.get("run_id"),
                "engine": item.get("engine"),
                "provider": item.get("provider"),
                "model": item.get("model"),
                "suite": item.get("suite"),
                "concurrency": _non_negative_int(item.get("concurrency")),
                "rank_metric": item.get("rank_metric"),
                "rank_value": _number_or_none(item.get("rank_value")),
                "avg_queue_ms": _number_or_none(item.get("avg_queue_ms")),
                "avg_rate_limit_wait_ms": _number_or_none(item.get("avg_rate_limit_wait_ms")),
            }
        )
    return entries[:5]


def _readiness_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "ready": bool(value.get("ready")),
        "state": str(value.get("state") or "unknown"),
        "blocking_artifact_count": _non_negative_int(value.get("blocking_artifact_count")),
        "review_artifact_count": _non_negative_int(value.get("review_artifact_count")),
        "blocking_statuses": _summary_string_list(value.get("blocking_statuses")),
        "review_statuses": _summary_string_list(value.get("review_statuses")),
    }


def _summary_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value[:12] if item is not None]


def _summary_int_list(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    return [_non_negative_int(item) for item in value[:12]]


def _compact_engine_priorities(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    priorities = []
    for item in value:
        if not isinstance(item, dict):
            continue
        priorities.append(
            {
                "priority": _non_negative_int(item.get("priority")),
                "area": str(item.get("area") or "unknown"),
                "aligned_artifacts_or_suites": _compact_string_list(item.get("aligned_artifacts_or_suites")),
            }
        )
    return priorities[:8]


def _compact_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value[:8] if item is not None]


def _int_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _non_negative_int(raw) for key, raw in value.items()}


def _harness_summary_text(summaries: list[dict[str, Any]]) -> str:
    parts = []
    for item in summaries[:6]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("suite_name") or "harness")
        status = str(item.get("review_status") or "review")
        profile = item.get("generator_profile")
        label = f"{name}={status}"
        if profile:
            label += f" ({profile})"
        parts.append(label)
    return ", ".join(parts) if parts else "none"


def _engine_advisory_summary_text(summaries: list[dict[str, Any]]) -> str:
    parts = []
    for item in summaries[:6]:
        if not isinstance(item, dict):
            continue
        engine = str(item.get("engine") or "engine")
        priorities = item.get("top_priorities")
        if isinstance(priorities, list) and priorities:
            areas = [str(priority.get("area")) for priority in priorities[:3] if isinstance(priority, dict) and priority.get("area")]
            label = f"{engine}: {', '.join(areas)}" if areas else engine
        else:
            label = engine
        parts.append(label)
    return ", ".join(parts) if parts else "none"


def _evidence_index_summary_text(summaries: list[dict[str, Any]]) -> str:
    parts = []
    for item in summaries[:6]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "evidence-index")
        status_counts = item.get("status_counts")
        if isinstance(status_counts, dict):
            counts = ", ".join(f"{key}={value}" for key, value in sorted(status_counts.items()))
            readiness = item.get("readiness")
            state = readiness.get("state") if isinstance(readiness, dict) else None
            parts.append(f"{name}: {counts}" + (f" ({state})" if state else ""))
        else:
            parts.append(name)
    return ", ".join(parts) if parts else "none"


def _suite_audit_summary_text(summaries: list[dict[str, Any]]) -> str:
    parts = []
    for item in summaries[:6]:
        if not isinstance(item, dict):
            continue
        suite = str(item.get("suite") or "suite")
        findings = _non_negative_int(item.get("finding_count"))
        duplicates = _non_negative_int(item.get("duplicate_fingerprint_count"))
        parts.append(f"{suite}: findings={findings}, duplicates={duplicates}")
    return ", ".join(parts) if parts else "none"


def _suite_calibration_summary_text(summaries: list[dict[str, Any]]) -> str:
    parts = []
    for item in summaries[:6]:
        if not isinstance(item, dict):
            continue
        suite = str(item.get("suite") or "suite")
        passed = str(bool(item.get("passed"))).lower()
        good = _non_negative_int(item.get("known_good_runs"))
        bad = _non_negative_int(item.get("known_bad_cases"))
        findings = _non_negative_int(item.get("findings"))
        parts.append(f"{suite}: passed={passed}, good={good}, bad={bad}, findings={findings}")
    return ", ".join(parts) if parts else "none"


def _metric_coverage_summary_text(summaries: list[dict[str, Any]]) -> str:
    parts = []
    for item in summaries[:6]:
        if not isinstance(item, dict):
            continue
        provider = str(item.get("provider") or "provider")
        score = item.get("coverage_score")
        review_groups = item.get("review_required_groups")
        review_count = len(review_groups) if isinstance(review_groups, list) else 0
        parts.append(f"{provider}: score={score}, review_groups={review_count}")
    return ", ".join(parts) if parts else "none"


def _normalized_telemetry_summary_text(summaries: list[dict[str, Any]]) -> str:
    parts = []
    for item in summaries[:6]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("stats_profile") or item.get("native_adapter") or item.get("contract") or "telemetry")
        populated = _non_negative_int(item.get("populated_field_count"))
        advisory = _non_negative_int(item.get("advisory_field_count"))
        raw_provenance = _non_negative_int(item.get("raw_provenance_field_count"))
        labeling = str(bool(item.get("stats_requires_labeling"))).lower()
        parts.append(f"{label}: populated={populated},advisory={advisory},raw_provenance={raw_provenance},labeling={labeling}")
    return ", ".join(parts) if parts else "none"


def _redaction_scan_summary_text(summaries: list[dict[str, Any]]) -> str:
    parts = []
    for item in summaries[:6]:
        if not isinstance(item, dict):
            continue
        ok = str(item.get("ok")).lower()
        scanned = _non_negative_int(item.get("scanned_items"))
        skipped = _non_negative_int(item.get("skipped_items"))
        findings = _non_negative_int(item.get("finding_count"))
        patterns = item.get("pattern_counts")
        pattern_text = _count_map_text(patterns) if isinstance(patterns, dict) and patterns else "none"
        parts.append(f"ok={ok},scanned={scanned},skipped={skipped},findings={findings},patterns={pattern_text}")
    return ", ".join(parts) if parts else "none"


def _publication_bundle_summary_text(summaries: list[dict[str, Any]]) -> str:
    parts = []
    for item in summaries[:6]:
        if not isinstance(item, dict):
            continue
        readiness = item.get("publication_readiness")
        status = readiness.get("status") if isinstance(readiness, dict) else "unknown"
        media_kit = item.get("media_kit") if isinstance(item.get("media_kit"), dict) else {}
        missing = media_kit.get("missing_recommended_assets")
        missing_count = len(missing) if isinstance(missing, list) else 0
        parts.append(f"{item.get('run_id') or 'unknown'}={status},missing_media:{missing_count}")
    return ", ".join(parts) if parts else "none"


def _matrix_publication_bundle_summary_text(summaries: list[dict[str, Any]]) -> str:
    parts = []
    for item in summaries[:6]:
        if not isinstance(item, dict):
            continue
        matrix = item.get("matrix") if isinstance(item.get("matrix"), dict) else {}
        media_kit = item.get("media_kit") if isinstance(item.get("media_kit"), dict) else {}
        missing = media_kit.get("missing_recommended_assets")
        missing_count = len(missing) if isinstance(missing, list) else 0
        parts.append(
            f"{matrix.get('artifact_stem') or item.get('archive_path') or 'matrix'}="
            f"missing_media:{missing_count},targets:{_engine_target_ids_text(item.get('engine_targets'))},"
            f"architectures:{_scorecard_group_names_text(item.get('architecture_summary'), 'model_architecture')},"
            f"quantization:{_scorecard_group_names_text(item.get('quantization_summary'), 'quantization')}"
        )
    return ", ".join(parts) if parts else "none"


def _publication_brief_summary_text(summaries: list[dict[str, Any]]) -> str:
    parts = []
    for item in summaries[:6]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "publication-brief")
        ready = str(bool(item.get("ready"))).lower()
        blockers = _non_negative_int(item.get("claim_blockers"))
        warnings = _non_negative_int(item.get("claim_warnings"))
        parts.append(
            f"{name}: ready={ready},blockers={blockers},warnings={warnings},"
            f"targets:{_engine_target_ids_text(item.get('engine_targets'))}"
        )
    return ", ".join(parts) if parts else "none"


def _engine_target_ids_text(value: Any) -> str:
    if not isinstance(value, list):
        return "none"
    ids = [str(item.get("id")) for item in value if isinstance(item, dict) and item.get("id")]
    return ",".join(ids) if ids else "none"


def _matrix_scorecard_summary_text(summaries: list[dict[str, Any]]) -> str:
    parts = []
    for item in summaries[:6]:
        if not isinstance(item, dict):
            continue
        matrix = str(item.get("matrix") or "matrix")
        pass_rate = item.get("pass_rate_percent")
        telemetry = item.get("telemetry_quality_summary") if isinstance(item.get("telemetry_quality_summary"), dict) else {}
        quality_counts = _count_map_text(telemetry.get("quality_counts"))
        concurrency = item.get("concurrency_evidence") if isinstance(item.get("concurrency_evidence"), dict) else {}
        levels = concurrency.get("concurrency_levels")
        level_text = ",".join(str(level) for level in levels) if isinstance(levels, list) and levels else "n/a"
        parts.append(
            f"{matrix}: pass={pass_rate}, telemetry={quality_counts}, concurrency={level_text}, "
            f"parser_repair={item.get('tool_parser_repairs_valid')}/{item.get('tool_parser_repair_cases')}, "
            f"invalid_tools={item.get('invalid_tool_call_count')}, "
            f"architectures={_scorecard_group_names_text(item.get('architecture_summary'), 'model_architecture')}, "
            f"quantization={_scorecard_group_names_text(item.get('quantization_summary'), 'quantization')}"
        )
    return ", ".join(parts) if parts else "none"


def _scorecard_group_names_text(value: Any, key: str) -> str:
    if not isinstance(value, list):
        return "none"
    names = [str(item.get(key)) for item in value if isinstance(item, dict) and item.get(key)]
    return ",".join(names) if names else "none"


def _selftest_summary_text(summaries: list[dict[str, Any]]) -> str:
    parts = []
    for item in summaries[:6]:
        if not isinstance(item, dict):
            continue
        run_id = str(item.get("run_id") or "selftest")
        tier = str(item.get("tier") or "unknown")
        status = "pass" if item.get("ok") is True else "fail"
        exit_code = _non_negative_int(item.get("exit_code"))
        parts.append(f"{run_id}: {tier}={status} exit={exit_code}")
    return ", ".join(parts) if parts else "none"


def _sdlc_validation_manifest_summary_text(summaries: list[dict[str, Any]]) -> str:
    parts = []
    for item in summaries[:6]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("archive_path") or "sdlc-validation")
        gates = _non_negative_int(item.get("required_gate_count"))
        chrome_steps = _non_negative_int(item.get("chrome_validation_step_count"))
        expected = _non_negative_int(item.get("expected_artifact_count"))
        parts.append(f"{name}: gates={gates},chrome_steps={chrome_steps},expected_artifacts={expected}")
    return ", ".join(parts) if parts else "none"


def _implementation_status_summary_text(summaries: list[dict[str, Any]]) -> str:
    parts = []
    for item in summaries[:6]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("archive_path") or "implementation")
        status = str(item.get("implementation_status") or item.get("status") or "unknown")
        missing = _non_negative_int(item.get("missing_areas"))
        harness_cases = _non_negative_int(item.get("harness_engineering_case_count"))
        stats_profiles = _non_negative_int(item.get("stats_profile_count"))
        parts.append(f"{label}: {status},missing={missing},harness_cases={harness_cases},stats_profiles={stats_profiles}")
    return ", ".join(parts) if parts else "none"


def _campaign_preflight_summary_text(summaries: list[dict[str, Any]]) -> str:
    parts = []
    for item in summaries[:6]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("archive_path") or "campaign-preflight")
        matrices = _non_negative_int(item.get("matrix_count"))
        runs = _non_negative_int(item.get("run_count"))
        cases = _non_negative_int(item.get("total_cases"))
        readiness = _non_negative_int(item.get("benchmark_readiness_report_count"))
        external_safe = str(bool(item.get("external_publication_safe"))).lower()
        local_paths = str(bool(item.get("contains_local_paths"))).lower()
        parts.append(
            f"{label}: matrices={matrices},runs={runs},cases={cases},readiness={readiness},external_safe={external_safe},local_paths={local_paths}"
        )
    return ", ".join(parts) if parts else "none"


def _benchmark_readiness_summary_text(summaries: list[dict[str, Any]]) -> str:
    parts = []
    for item in summaries[:6]:
        if not isinstance(item, dict):
            continue
        provider = str(item.get("provider") or item.get("archive_path") or "readiness")
        ready = str(item.get("ready")).lower()
        writable = _non_negative_int(item.get("provider_auth_writable_backends"))
        plaintext = _non_negative_int(item.get("provider_auth_plaintext_fallbacks"))
        policy_guards = _non_negative_int(item.get("provider_auth_prewrite_policy_guards_recommended"))
        parts.append(f"{provider}=ready:{ready},auth_writable:{writable},plaintext:{plaintext},policy_guards:{policy_guards}")
    return ", ".join(parts) if parts else "none"


def _provider_audit_summary_text(summaries: list[dict[str, Any]]) -> str:
    parts = []
    for item in summaries[:6]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("archive_path") or "provider-audit")
        errors = _non_negative_int(item.get("error_count"))
        warnings = _non_negative_int(item.get("warning_count"))
        remote = _non_negative_int(item.get("remote_providers"))
        writable = _non_negative_int(item.get("writable_secret_backend_count"))
        plaintext = _non_negative_int(item.get("plaintext_dotenv_provider_count"))
        parts.append(f"{label}=remote:{remote},errors:{errors},warnings:{warnings},writable:{writable},plaintext:{plaintext}")
    return ", ".join(parts) if parts else "none"


def _protocol_repair_posture_summary_text(summaries: list[dict[str, Any]]) -> str:
    parts = []
    for item in summaries[:6]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("archive_path") or item.get("name") or "protocol-repair")
        ready = str(item.get("ready")).lower()
        scorecard_cases = _non_negative_int(item.get("scorecard_tool_parser_repair_cases"))
        scorecard_valid = _non_negative_int(item.get("scorecard_tool_parser_repairs_valid"))
        gate_cases = _non_negative_int(item.get("matrix_gate_tool_parser_repair_cases"))
        gate_valid = _non_negative_int(item.get("matrix_gate_tool_parser_repairs_valid"))
        invalid = _non_negative_int(item.get("scorecard_invalid_tool_call_count")) + _non_negative_int(
            item.get("matrix_gate_invalid_tool_call_count")
        )
        parts.append(f"{label}=ready:{ready},scorecard:{scorecard_valid}/{scorecard_cases},gate:{gate_valid}/{gate_cases},invalid:{invalid}")
    return ", ".join(parts) if parts else "none"


def _workflow_readiness_summary_text(summaries: list[dict[str, Any]]) -> str:
    parts = []
    for item in summaries[:6]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("archive_path") or item.get("name") or "workflow-readiness")
        ready = str(item.get("ready")).lower()
        covered = _non_negative_int(item.get("covered_required_surface_count"))
        required = _non_negative_int(item.get("required_surface_count"))
        gaps = _non_negative_int(item.get("gap_count"))
        max_concurrency = _non_negative_int(item.get("max_concurrency"))
        parts.append(f"{label}=ready:{ready},surfaces:{covered}/{required},gaps:{gaps},max_concurrency:{max_concurrency}")
    return ", ".join(parts) if parts else "none"


def _security_posture_summary_text(summaries: list[dict[str, Any]]) -> str:
    parts = []
    for item in summaries[:6]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("archive_path") or item.get("name") or "security-posture")
        ready = str(item.get("ready")).lower()
        blockers = _non_negative_int(item.get("blockers"))
        warnings = _non_negative_int(item.get("warnings"))
        redaction = _non_negative_int(item.get("redaction_finding_count"))
        unsafe = _non_negative_int(item.get("unsafe_review_artifact_count"))
        parts.append(f"{label}=ready:{ready},blockers:{blockers},warnings:{warnings},redaction:{redaction},unsafe_artifacts:{unsafe}")
    return ", ".join(parts) if parts else "none"


def _number_or_none(value: Any) -> float | int | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed.is_integer():
        return int(parsed)
    return parsed


def _non_negative_int(value: Any) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def _normalize_failure_class_summary(value: Any) -> list[dict[str, int | str]]:
    if not isinstance(value, list):
        return []
    summary = []
    for item in value:
        if not isinstance(item, dict):
            continue
        failure_class = str(item.get("failure_class") or "unclassified")
        try:
            count = int(item.get("count") or 0)
        except (TypeError, ValueError):
            count = 0
        if count:
            summary.append({"failure_class": failure_class, "count": count})
    return sorted(summary, key=lambda item: (-int(item["count"]), str(item["failure_class"])))


def _normalize_tool_loop_stop_summary(value: Any) -> list[dict[str, int | str]]:
    if not isinstance(value, list):
        return []
    summary = []
    for item in value:
        if not isinstance(item, dict):
            continue
        reason = str(item.get("stop_reason") or item.get("reason") or "unknown").strip() or "unknown"
        count = _non_negative_int(item.get("count"))
        if count:
            summary.append({"stop_reason": reason, "count": count})
    return sorted(summary, key=lambda item: (-int(item["count"]), str(item["stop_reason"])))


def _failure_class_findings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    findings = []
    for item in value:
        if not isinstance(item, dict):
            continue
        metric = str(item.get("metric") or "")
        if metric.startswith("failure_class."):
            findings.append(
                {
                    "metric": metric,
                    "failure_class": metric.split(".", 1)[1] or "unclassified",
                    "actual": item.get("actual"),
                    "threshold": item.get("threshold"),
                }
            )
    return findings


def _tool_loop_stop_findings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    findings = []
    for item in value:
        if not isinstance(item, dict):
            continue
        metric = str(item.get("metric") or "")
        if metric.startswith("tool_loop_stop_reason."):
            findings.append(
                {
                    "metric": metric,
                    "stop_reason": metric.split(".", 1)[1] or "unknown",
                    "actual": item.get("actual"),
                    "threshold": item.get("threshold"),
                }
            )
    return findings


def _aggregate_failure_class_checks(checks: list[dict[str, Any]]) -> list[dict[str, int | str]]:
    counts: dict[str, int] = {}
    for check in checks:
        for item in check.get("failure_class_summary", []):
            if not isinstance(item, dict):
                continue
            failure_class = str(item.get("failure_class") or "unclassified")
            try:
                count = int(item.get("count") or 0)
            except (TypeError, ValueError):
                count = 0
            if count:
                counts[failure_class] = counts.get(failure_class, 0) + count
    return [
        {"failure_class": key, "count": value}
        for key, value in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _aggregate_tool_loop_stop_checks(checks: list[dict[str, Any]]) -> list[dict[str, int | str]]:
    counts: dict[str, int] = {}
    for check in checks:
        for item in check.get("tool_loop_stop_summary", []):
            if not isinstance(item, dict):
                continue
            reason = str(item.get("stop_reason") or item.get("reason") or "unknown")
            try:
                count = int(item.get("count") or 0)
            except (TypeError, ValueError):
                count = 0
            if count:
                counts[reason] = counts.get(reason, 0) + count
    return [
        {"stop_reason": key, "count": value}
        for key, value in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _collect_failure_class_findings(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings = []
    for check in checks:
        category = check.get("category")
        for item in check.get("failure_class_findings", []):
            if isinstance(item, dict):
                findings.append({"category": category, **item})
    return findings


def _collect_tool_loop_stop_findings(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings = []
    for check in checks:
        category = check.get("category")
        for item in check.get("tool_loop_stop_findings", []):
            if isinstance(item, dict):
                findings.append({"category": category, **item})
    return findings


def _aggregate_judge_verdict_checks(checks: list[dict[str, Any]]) -> dict[str, int | float]:
    cases = sum(_non_negative_int(check.get("judge_rubric_cases")) for check in checks)
    valid = sum(_non_negative_int(check.get("judge_verdicts_valid")) for check in checks)
    rate = round((valid / cases) * 100, 3) if cases else 0.0
    return {
        "judge_rubric_cases": cases,
        "judge_verdicts_valid": valid,
        "judge_verdict_valid_rate_percent": rate,
    }


def _collect_judge_verdict_findings(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings = []
    for check in checks:
        category = check.get("category")
        for item in check.get("judge_verdict_findings", []):
            if isinstance(item, dict):
                findings.append({"category": category, **item})
    return findings


def _aggregate_tool_parser_repair_checks(checks: list[dict[str, Any]]) -> dict[str, int | float]:
    invalid = sum(_non_negative_int(check.get("invalid_tool_call_count")) for check in checks)
    cases = sum(_non_negative_int(check.get("tool_parser_repair_cases")) for check in checks)
    valid = sum(_non_negative_int(check.get("tool_parser_repairs_valid")) for check in checks)
    rate = round((valid / cases) * 100, 3) if cases else 0.0
    return {
        "invalid_tool_call_count": invalid,
        "tool_parser_repair_cases": cases,
        "tool_parser_repairs_valid": valid,
        "tool_parser_repair_valid_rate_percent": rate,
    }


def _collect_tool_parser_repair_findings(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings = []
    for check in checks:
        category = check.get("category")
        for item in check.get("tool_parser_repair_findings", []):
            if isinstance(item, dict):
                findings.append({"category": category, **item})
    return findings


def _judge_verdict_findings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    findings = []
    for item in value:
        if not isinstance(item, dict):
            continue
        metric = str(item.get("metric") or "")
        if metric in {"judge_verdict_valid_rate", "judge_verdict_result_artifacts_missing"}:
            findings.append(
                {
                    "metric": metric,
                    "actual": item.get("actual"),
                    "threshold": item.get("threshold"),
                }
            )
    return findings


def _tool_parser_repair_findings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    findings = []
    for item in value:
        if not isinstance(item, dict):
            continue
        metric = str(item.get("metric") or "")
        if metric in {
            "invalid_tool_calls",
            "tool_parser_repair_valid_rate",
            "tool_parser_repair_result_artifacts_missing",
        }:
            findings.append(
                {
                    "metric": metric,
                    "actual": item.get("actual"),
                    "threshold": item.get("threshold"),
                }
            )
    return findings


def _failure_class_summary_text(summary: Any) -> str:
    if not isinstance(summary, list) or not summary:
        return "none"
    parts = []
    for item in summary:
        if isinstance(item, dict):
            parts.append(f"{item.get('failure_class', 'unclassified')}={item.get('count', 0)}")
    return ", ".join(parts) if parts else "none"


def _tool_loop_stop_summary_text(summary: Any) -> str:
    if not isinstance(summary, list) or not summary:
        return "none"
    parts = []
    for item in summary:
        if isinstance(item, dict):
            parts.append(f"{item.get('stop_reason') or item.get('reason') or 'unknown'}={item.get('count', 0)}")
    return ", ".join(parts) if parts else "none"


def _contract_capability_evidence_text(evidence: Any) -> str:
    if not isinstance(evidence, dict):
        return "none"
    parts = []
    directly_checked = evidence.get("directly_checked")
    if isinstance(directly_checked, list) and directly_checked:
        parts.append("direct=" + ",".join(str(item) for item in directly_checked))
    proxy = _count_map_text(evidence.get("proxy_checked_counts"))
    if proxy != "none":
        parts.append("proxy=" + proxy)
    not_covered = _count_map_text(evidence.get("not_covered_counts"))
    if not_covered != "none":
        parts.append("not_covered=" + not_covered)
    return "; ".join(parts) if parts else "none"


def _count_map_text(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return "none"
    return ",".join(f"{key}={value[key]}" for key in sorted(value))


def _safe_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in value.strip()).strip("-")
    return cleaned or "benchmark-claim"
