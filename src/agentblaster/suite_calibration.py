from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import hashlib

from agentblaster.models import SuiteDefinition

CALIBRATION_SCHEMA_VERSION = "agentblaster.suite-calibration.v1"
CALIBRATION_REPORT_SCHEMA_VERSION = "agentblaster.suite-calibration-report.v1"
GENERATED_ORIGINS = {"harness_generated", "synthetic_representative"}


def suite_calibration_template(suite: SuiteDefinition) -> dict[str, Any]:
    return {
        "schema_version": CALIBRATION_SCHEMA_VERSION,
        "suite": suite.name,
        "suite_sha256": _suite_sha256(suite),
        "generated": _is_generated_suite(suite),
        "generator": suite.provenance.generator,
        "generator_profile": suite.provenance.generator_profile,
        "known_good_runs": [],
        "known_bad_cases": [],
        "failure_taxonomy": [],
        "human_reviewed": False,
        "approved_for_release_gate": False,
        "review_notes": [
            "Fill this manifest after at least one known-good provider result and one known-bad calibration case are documented.",
            "Do not promote generated suites to release gates until this calibration passes.",
        ],
    }


def load_calibration(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid calibration manifest at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"invalid calibration manifest at {path}: root must be an object")
    return data


def write_calibration_template(suite: SuiteDefinition, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(suite_calibration_template(suite), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def evaluate_suite_calibration(
    suite: SuiteDefinition,
    calibration: dict[str, Any],
    *,
    require_release_gate: bool = True,
) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    generated = _is_generated_suite(suite)

    if calibration.get("schema_version") != CALIBRATION_SCHEMA_VERSION:
        findings.append(_finding("invalid_schema", "calibration manifest schema_version is missing or unsupported"))
    if calibration.get("suite") != suite.name:
        findings.append(_finding("suite_mismatch", f"calibration suite {calibration.get('suite')!r} does not match {suite.name!r}"))
    expected_sha = _suite_sha256(suite)
    if calibration.get("suite_sha256") and calibration.get("suite_sha256") != expected_sha:
        findings.append(_finding("suite_hash_mismatch", "calibration suite_sha256 does not match the current suite"))
    if generated and not calibration.get("suite_sha256"):
        warnings.append(_finding("missing_suite_hash", "generated suite calibration should include suite_sha256"))

    known_good_runs = calibration.get("known_good_runs") or []
    known_bad_cases = calibration.get("known_bad_cases") or []
    failure_taxonomy = calibration.get("failure_taxonomy") or []

    if generated or require_release_gate:
        if not isinstance(known_good_runs, list) or not known_good_runs:
            findings.append(_finding("missing_known_good_run", "calibration requires at least one known-good provider/run result"))
        if not isinstance(known_bad_cases, list) or not known_bad_cases:
            findings.append(_finding("missing_known_bad_case", "calibration requires at least one known-bad calibration case"))
        if not isinstance(failure_taxonomy, list) or not failure_taxonomy:
            findings.append(_finding("missing_failure_taxonomy", "calibration requires documented failure taxonomy coverage"))
        if not bool(calibration.get("human_reviewed")):
            findings.append(_finding("missing_human_review", "calibration requires human_reviewed=true"))
        if require_release_gate and not bool(calibration.get("approved_for_release_gate")):
            findings.append(_finding("not_approved_for_release_gate", "release-gate use requires approved_for_release_gate=true"))

    if isinstance(known_good_runs, list):
        for index, run in enumerate(known_good_runs, start=1):
            if not isinstance(run, dict):
                findings.append(_finding("invalid_known_good_run", f"known_good_runs[{index}] must be an object"))
                continue
            if not run.get("provider") or not run.get("result_ref"):
                findings.append(_finding("incomplete_known_good_run", f"known_good_runs[{index}] requires provider and result_ref"))
    if isinstance(known_bad_cases, list):
        suite_case_ids = {case.id for case in suite.cases}
        for index, bad_case in enumerate(known_bad_cases, start=1):
            if not isinstance(bad_case, dict):
                findings.append(_finding("invalid_known_bad_case", f"known_bad_cases[{index}] must be an object"))
                continue
            case_id = bad_case.get("case_id")
            if not case_id or case_id not in suite_case_ids:
                findings.append(_finding("unknown_known_bad_case", f"known_bad_cases[{index}] references unknown case {case_id!r}"))
            if not bad_case.get("expected_failure_class"):
                findings.append(_finding("missing_expected_failure_class", f"known_bad_cases[{index}] requires expected_failure_class"))

    return {
        "schema_version": CALIBRATION_REPORT_SCHEMA_VERSION,
        "suite": suite.name,
        "suite_sha256": expected_sha,
        "generated": generated,
        "require_release_gate": require_release_gate,
        "passed": not findings,
        "summary": {
            "known_good_runs": len(known_good_runs) if isinstance(known_good_runs, list) else 0,
            "known_bad_cases": len(known_bad_cases) if isinstance(known_bad_cases, list) else 0,
            "failure_taxonomy_entries": len(failure_taxonomy) if isinstance(failure_taxonomy, list) else 0,
            "findings": len(findings),
            "warnings": len(warnings),
        },
        "findings": findings,
        "warnings": warnings,
        "notes": [
            "Suite calibration is static and does not contact providers or inspect raw traces.",
            "Generated suites should remain exploratory until this gate passes with release-gate approval.",
        ],
    }


def write_calibration_report(report: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def format_calibration_report(report: dict[str, Any]) -> str:
    lines = [
        "AgentBlaster suite calibration gate",
        f"suite: {report['suite']}",
        f"generated: {str(report['generated']).lower()}",
        f"require_release_gate: {str(report['require_release_gate']).lower()}",
        f"passed: {str(report['passed']).lower()}",
        "summary:",
    ]
    for key, value in report["summary"].items():
        lines.append(f"- {key}: {value}")
    lines.append("findings:")
    if not report["findings"]:
        lines.append("- none")
    else:
        for finding in report["findings"]:
            lines.append(f"- {finding['code']}: {finding['message']}")
    lines.append("warnings:")
    if not report["warnings"]:
        lines.append("- none")
    else:
        for warning in report["warnings"]:
            lines.append(f"- {warning['code']}: {warning['message']}")
    return "\n".join(lines) + "\n"


def _is_generated_suite(suite: SuiteDefinition) -> bool:
    return bool(suite.provenance.generator) or suite.provenance.origin in GENERATED_ORIGINS


def _suite_sha256(suite: SuiteDefinition) -> str:
    payload = suite.model_dump(mode="json", exclude_none=True)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _finding(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}
