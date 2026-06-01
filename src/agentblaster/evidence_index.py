from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

from agentblaster.cleanup import CLEANUP_PLAN_SCHEMA_VERSION, RETENTION_CLEANUP_SCHEMA_VERSION
from agentblaster.engine_advisory import ENGINE_ADVISORY_SCHEMA_VERSION
from agentblaster.errors import ConfigError
from agentblaster.harness import HARNESS_REVIEW_SCHEMA_VERSION
from agentblaster.implementation_status import IMPLEMENTATION_STATUS_SCHEMA_VERSION
from agentblaster.matrix_gate import MATRIX_GATE_SCHEMA_VERSION
from agentblaster.matrix_pressure import MATRIX_PRESSURE_SCHEMA_VERSION
from agentblaster.matrix_saturation import MATRIX_SATURATION_SCHEMA_VERSION
from agentblaster.metric_coverage import METRIC_COVERAGE_SCHEMA_VERSION
from agentblaster.protocol_repair import PROTOCOL_REPAIR_POSTURE_SCHEMA_VERSION
from agentblaster.provider_audit import PROVIDER_AUDIT_SCHEMA_VERSION
from agentblaster.publication_brief import PUBLICATION_BRIEF_SCHEMA_VERSION
from agentblaster.quality import SDLC_VALIDATION_MANIFEST_SCHEMA_VERSION, SELFTEST_REPORT_SCHEMA_VERSION
from agentblaster.readiness import READINESS_SCHEMA_VERSION
from agentblaster.security_posture import SECURITY_POSTURE_SCHEMA_VERSION
from agentblaster.suite_audit import SUITE_AUDIT_SCHEMA_VERSION
from agentblaster.suite_calibration import CALIBRATION_REPORT_SCHEMA_VERSION
from agentblaster.workflow_readiness import WORKFLOW_READINESS_SCHEMA_VERSION


EVIDENCE_INDEX_SCHEMA_VERSION = "agentblaster.evidence-index.v1"
MAX_EVIDENCE_INDEX_JSON_BYTES = 1_000_000
PUBLICATION_BUNDLE_MANIFEST = "publication-bundle-manifest.json"
PUBLICATION_BUNDLE_MANIFEST_SCHEMA_VERSION = "agentblaster.publication-bundle.v1"
MATRIX_PUBLICATION_BUNDLE_MANIFEST = "matrix-publication-bundle-manifest.json"
MATRIX_PUBLICATION_BUNDLE_MANIFEST_SCHEMA_VERSION = "agentblaster.matrix-publication-bundle.v1"
MEDIA_KIT_SCHEMA_VERSION = "agentblaster.media-kit.v1"
CAMPAIGN_PREFLIGHT_SCHEMA_VERSION = "agentblaster.campaign-preflight-bundle.v1"
MATRIX_SCORECARD_SCHEMA_VERSION = "agentblaster-matrix-scorecard-v1"
NORMALIZED_TELEMETRY_SCHEMA_VERSION = "agentblaster.normalized-telemetry.v1"
BLOCKED_EVIDENCE_NAMES = {"results.jsonl", "events.jsonl"}
BLOCKING_STATUSES = {
    "fail",
    "invalid-json",
    "invalid-json-root",
    "invalid-zip",
    "invalid-release-manifest",
    "invalid-publication-manifest",
    "invalid-matrix-publication-manifest",
    "skipped-large-json",
    "skipped-large-manifest",
}
REVIEW_STATUSES = {"review", "informational", "not-opened"}


def build_evidence_index(*, name: str, artifacts: list[Path]) -> dict[str, Any]:
    """Build a compact publication-safe index over supplied review artifacts."""

    if not artifacts:
        raise ConfigError("evidence index requires at least one --artifact")
    indexed = [_artifact_entry(path) for path in artifacts]
    return {
        "schema_version": EVIDENCE_INDEX_SCHEMA_VERSION,
        "name": _safe_name(name),
        "artifact_count": len(indexed),
        "status_counts": _status_counts(indexed),
        "readiness": _readiness(indexed),
        "cleanup_evidence": _cleanup_evidence(indexed),
        "artifacts": indexed,
        "security": {
            "contacts_providers": False,
            "executes_benchmarks": False,
            "resolves_secrets": False,
            "reads_keyring_values": False,
            "reads_raw_traces": False,
            "includes_raw_results": False,
            "redacts_artifact_paths": True,
        },
        "notes": [
            "Evidence index reads only supplied compact review artifacts.",
            "Release qualification zip artifacts are summarized from manifest.json only.",
            "Run publication zip artifacts are summarized from publication-bundle-manifest.json only.",
            "Matrix publication zip artifacts are summarized from matrix-publication-bundle-manifest.json only.",
            "Raw traces, result rows, provider payloads, prompts, responses, API keys, and request headers are excluded.",
        ],
    }


def write_evidence_index(report: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def format_evidence_index(report: dict[str, Any]) -> str:
    lines = [
        "AgentBlaster evidence index",
        f"name: {report['name']}",
        f"artifact_count: {report['artifact_count']}",
        "status_counts: " + ", ".join(f"{key}={value}" for key, value in report["status_counts"].items()),
        f"readiness: {report.get('readiness', {}).get('state', 'unknown')}",
    ]
    for item in report["artifacts"]:
        lines.append(f"- {item['status']} {item['path']} {item.get('schema') or 'unknown-schema'}")
    return "\n".join(lines) + "\n"


def _artifact_entry(path: Path) -> dict[str, Any]:
    if path.name in BLOCKED_EVIDENCE_NAMES or "/raw/" in path.as_posix() or path.as_posix().endswith("/raw"):
        raise ConfigError(f"raw or result artifact is not allowed in evidence index: {path}")
    if not path.exists() or not path.is_file():
        raise ConfigError(f"missing evidence artifact: {path}")
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _json_artifact_entry(path)
    if suffix == ".zip":
        return _zip_artifact_entry(path)
    raise ConfigError(f"unsupported evidence artifact suffix for {path}; expected .json or .zip")


def _json_artifact_entry(path: Path) -> dict[str, Any]:
    size = path.stat().st_size
    if size > MAX_EVIDENCE_INDEX_JSON_BYTES:
        return {
            "path": _safe_artifact_path(path),
            "path_redacted": _artifact_path_redacted(path),
            "size_bytes": size,
            "schema": None,
            "status": "skipped-large-json",
            "status_source": "file-size",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "path": _safe_artifact_path(path),
            "path_redacted": _artifact_path_redacted(path),
            "size_bytes": size,
            "schema": None,
            "status": "invalid-json",
            "status_source": "json-parse",
        }
    if not isinstance(payload, dict):
        return {
            "path": _safe_artifact_path(path),
            "path_redacted": _artifact_path_redacted(path),
            "size_bytes": size,
            "schema": None,
            "status": "invalid-json-root",
            "status_source": "json-root",
        }
    status, status_source = _payload_status(payload)
    entry: dict[str, Any] = {
        "path": _safe_artifact_path(path),
        "path_redacted": _artifact_path_redacted(path),
        "size_bytes": size,
        "schema": payload.get("schema_version") or payload.get("schema") or payload.get("report_type"),
        "status": status,
        "status_source": status_source,
        "top_level_keys": sorted(str(key) for key in payload.keys())[:20],
    }
    review_summary = _review_summary(payload)
    if review_summary:
        entry["review_summary"] = review_summary
    return entry


def _zip_artifact_entry(path: Path) -> dict[str, Any]:
    schema = _zip_schema(path)
    if schema == "agentblaster.publication-bundle":
        return _publication_bundle_zip_artifact_entry(path, schema)
    if schema == "agentblaster.matrix-publication-bundle":
        return _matrix_publication_bundle_zip_artifact_entry(path, schema)
    if schema != "agentblaster.release-qualification-bundle":
        return {
            "path": _safe_artifact_path(path),
            "path_redacted": _artifact_path_redacted(path),
            "size_bytes": path.stat().st_size,
            "schema": schema,
            "status": "not-opened",
            "status_source": "zip-name",
        }
    try:
        with ZipFile(path) as archive:
            try:
                info = archive.getinfo("manifest.json")
            except KeyError:
                return _zip_error(path, schema, "invalid-release-manifest", "zip-manifest")
            if info.file_size > MAX_EVIDENCE_INDEX_JSON_BYTES:
                return _zip_error(path, schema, "skipped-large-manifest", "zip-manifest-size")
            payload = json.loads(archive.read(info).decode("utf-8"))
    except (BadZipFile, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return _zip_error(path, schema, "invalid-zip", "zip-manifest-parse")
    if not isinstance(payload, dict):
        return _zip_error(path, schema, "invalid-release-manifest", "zip-manifest-root")
    status, status_source = _payload_status(payload)
    entry: dict[str, Any] = {
        "path": _safe_artifact_path(path),
        "path_redacted": _artifact_path_redacted(path),
        "size_bytes": path.stat().st_size,
        "schema": payload.get("schema") or schema,
        "status": status,
        "status_source": "manifest." + status_source,
        "manifest_top_level_keys": sorted(str(key) for key in payload.keys())[:20],
    }
    artifact_status = payload.get("artifact_status")
    if isinstance(artifact_status, dict):
        entry["artifact_status"] = {
            str(key): int(value)
            for key, value in artifact_status.items()
            if isinstance(value, int)
        }
    review_summaries = _release_review_summaries(payload)
    if review_summaries:
        entry["review_summaries"] = review_summaries
    return entry


def _publication_bundle_zip_artifact_entry(path: Path, schema: str | None) -> dict[str, Any]:
    try:
        with ZipFile(path) as archive:
            try:
                info = archive.getinfo(PUBLICATION_BUNDLE_MANIFEST)
            except KeyError:
                return _zip_error(path, schema, "invalid-publication-manifest", "zip-publication-manifest")
            if info.file_size > MAX_EVIDENCE_INDEX_JSON_BYTES:
                return _zip_error(path, schema, "skipped-large-manifest", "zip-publication-manifest-size")
            payload = json.loads(archive.read(info).decode("utf-8"))
    except (BadZipFile, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return _zip_error(path, schema, "invalid-zip", "zip-publication-manifest-parse")
    if not isinstance(payload, dict):
        return _zip_error(path, schema, "invalid-publication-manifest", "zip-publication-manifest-root")
    schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema")) if value is not None}
    if PUBLICATION_BUNDLE_MANIFEST_SCHEMA_VERSION not in schema_values:
        return _zip_error(path, schema, "invalid-publication-manifest", "zip-publication-manifest-schema")
    review_summary = _publication_bundle_summary(payload)
    status, status_source = _publication_bundle_status(review_summary)
    entry: dict[str, Any] = {
        "path": _safe_artifact_path(path),
        "path_redacted": _artifact_path_redacted(path),
        "size_bytes": path.stat().st_size,
        "schema": payload.get("schema_version") or schema,
        "status": status,
        "status_source": "publication-manifest." + status_source,
        "manifest_top_level_keys": sorted(str(key) for key in payload.keys())[:20],
        "review_summary": review_summary,
    }
    return entry


def _matrix_publication_bundle_zip_artifact_entry(path: Path, schema: str | None) -> dict[str, Any]:
    try:
        with ZipFile(path) as archive:
            try:
                info = archive.getinfo(MATRIX_PUBLICATION_BUNDLE_MANIFEST)
            except KeyError:
                return _zip_error(path, schema, "invalid-matrix-publication-manifest", "zip-matrix-publication-manifest")
            if info.file_size > MAX_EVIDENCE_INDEX_JSON_BYTES:
                return _zip_error(path, schema, "skipped-large-manifest", "zip-matrix-publication-manifest-size")
            payload = json.loads(archive.read(info).decode("utf-8"))
    except (BadZipFile, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return _zip_error(path, schema, "invalid-zip", "zip-matrix-publication-manifest-parse")
    if not isinstance(payload, dict):
        return _zip_error(path, schema, "invalid-matrix-publication-manifest", "zip-matrix-publication-manifest-root")
    schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema")) if value is not None}
    if MATRIX_PUBLICATION_BUNDLE_MANIFEST_SCHEMA_VERSION not in schema_values:
        return _zip_error(path, schema, "invalid-matrix-publication-manifest", "zip-matrix-publication-manifest-schema")
    review_summary = _matrix_publication_bundle_summary(payload)
    status, status_source = _matrix_publication_bundle_status(review_summary)
    return {
        "path": _safe_artifact_path(path),
        "path_redacted": _artifact_path_redacted(path),
        "size_bytes": path.stat().st_size,
        "schema": payload.get("schema_version") or schema,
        "status": status,
        "status_source": "matrix-publication-manifest." + status_source,
        "manifest_top_level_keys": sorted(str(key) for key in payload.keys())[:20],
        "review_summary": review_summary,
    }


def _zip_error(path: Path, schema: str | None, status: str, source: str) -> dict[str, Any]:
    return {
        "path": _safe_artifact_path(path),
        "path_redacted": _artifact_path_redacted(path),
        "size_bytes": path.stat().st_size,
        "schema": schema,
        "status": status,
        "status_source": source,
    }


def _payload_status(payload: dict[str, Any]) -> tuple[str, str]:
    schema = payload.get("schema_version") or payload.get("schema") or payload.get("report_type")
    if schema == MATRIX_SCORECARD_SCHEMA_VERSION:
        matrix = payload.get("matrix") if isinstance(payload.get("matrix"), dict) else {}
        scorecard = payload.get("scorecard") if isinstance(payload.get("scorecard"), dict) else {}
        failed_runs = _non_negative_int(matrix.get("failed_runs"))
        failed_cases = _non_negative_int(scorecard.get("failed_cases"))
        return ("pass" if failed_runs == 0 and failed_cases == 0 else "review", "matrix-scorecard.review")
    if schema == SELFTEST_REPORT_SCHEMA_VERSION:
        value = payload.get("ok")
        if isinstance(value, bool):
            return ("pass" if value else "fail", "selftest.ok")
        return "review", "selftest.ok"
    if schema == PUBLICATION_BRIEF_SCHEMA_VERSION:
        security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
        if security.get("contains_secrets") is True or security.get("contains_raw_provider_payloads") is True:
            return "fail", "publication-brief.security"
        value = payload.get("ready")
        if isinstance(value, bool):
            return ("pass" if value else "review", "publication-brief.ready")
        return "review", "publication-brief.ready"
    if schema == PROTOCOL_REPAIR_POSTURE_SCHEMA_VERSION:
        value = payload.get("ready")
        if isinstance(value, bool):
            return ("pass" if value else "review", "protocol-repair.ready")
        return "review", "protocol-repair.ready"
    if schema == WORKFLOW_READINESS_SCHEMA_VERSION:
        value = payload.get("ready")
        if isinstance(value, bool):
            return ("pass" if value else "review", "workflow-readiness.ready")
        return "review", "workflow-readiness.ready"
    if schema == SECURITY_POSTURE_SCHEMA_VERSION:
        value = payload.get("ready")
        if isinstance(value, bool):
            return ("pass" if value else "fail", "security-posture.ready")
        return "review", "security-posture.ready"
    if schema == SDLC_VALIDATION_MANIFEST_SCHEMA_VERSION:
        security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
        if security.get("contains_secrets") is True or security.get("contains_raw_provider_payloads") is True:
            return "fail", "sdlc-validation-manifest.security"
        return "review", "sdlc-validation-manifest.static"
    if schema == PROVIDER_AUDIT_SCHEMA_VERSION:
        if _non_negative_int(payload.get("errors")):
            return "fail", "provider-audit.errors"
        if _non_negative_int(payload.get("warnings")):
            return "review", "provider-audit.warnings"
        return "pass", "provider-audit.errors"
    if schema in {
        HARNESS_REVIEW_SCHEMA_VERSION,
        ENGINE_ADVISORY_SCHEMA_VERSION,
        SUITE_AUDIT_SCHEMA_VERSION,
        METRIC_COVERAGE_SCHEMA_VERSION,
        NORMALIZED_TELEMETRY_SCHEMA_VERSION,
        MATRIX_PRESSURE_SCHEMA_VERSION,
        CLEANUP_PLAN_SCHEMA_VERSION,
        RETENTION_CLEANUP_SCHEMA_VERSION,
        CAMPAIGN_PREFLIGHT_SCHEMA_VERSION,
    }:
        return "review", "schema"
    ready = payload.get("ready")
    if isinstance(ready, bool):
        return ("pass" if ready else "review", "ready")
    for key in ("ok", "passed"):
        value = payload.get(key)
        if isinstance(value, bool):
            return ("pass" if value else "fail", key)
    return "informational", "schema"


def _review_summary(payload: dict[str, Any]) -> dict[str, Any]:
    schema = payload.get("schema_version") or payload.get("schema") or payload.get("report_type")
    if schema == MATRIX_GATE_SCHEMA_VERSION:
        return _matrix_gate_summary(payload)
    if schema == HARNESS_REVIEW_SCHEMA_VERSION:
        return _harness_summary(payload)
    if schema == CALIBRATION_REPORT_SCHEMA_VERSION:
        return _suite_calibration_summary(payload)
    if schema == ENGINE_ADVISORY_SCHEMA_VERSION:
        return _engine_advisory_summary(payload)
    if schema == SUITE_AUDIT_SCHEMA_VERSION:
        return _suite_audit_summary(payload)
    if schema == METRIC_COVERAGE_SCHEMA_VERSION:
        return _metric_coverage_summary(payload)
    if schema == PROVIDER_AUDIT_SCHEMA_VERSION:
        return _provider_audit_summary(payload)
    if schema == NORMALIZED_TELEMETRY_SCHEMA_VERSION:
        return _normalized_telemetry_summary(payload)
    if schema == MATRIX_PRESSURE_SCHEMA_VERSION:
        return _matrix_pressure_summary(payload)
    if schema == MATRIX_SATURATION_SCHEMA_VERSION:
        return _matrix_saturation_summary(payload)
    if schema == MATRIX_SCORECARD_SCHEMA_VERSION:
        return _matrix_scorecard_summary(payload)
    if schema == SELFTEST_REPORT_SCHEMA_VERSION:
        return _selftest_summary(payload)
    if schema == PUBLICATION_BRIEF_SCHEMA_VERSION:
        return _publication_brief_summary(payload)
    if schema == PROTOCOL_REPAIR_POSTURE_SCHEMA_VERSION:
        return _protocol_repair_summary(payload)
    if schema == WORKFLOW_READINESS_SCHEMA_VERSION:
        return _workflow_readiness_summary(payload)
    if schema == SECURITY_POSTURE_SCHEMA_VERSION:
        return _security_posture_summary(payload)
    if schema == SDLC_VALIDATION_MANIFEST_SCHEMA_VERSION:
        return _sdlc_validation_manifest_summary(payload)
    if schema == READINESS_SCHEMA_VERSION:
        return _benchmark_readiness_summary(payload)
    if schema == IMPLEMENTATION_STATUS_SCHEMA_VERSION:
        return _implementation_status_summary(payload)
    if schema in {"agentblaster.provider-contract-check.v1", "agentblaster.provider-contract-matrix.v1"}:
        return _provider_contract_summary(payload)
    if schema in {CLEANUP_PLAN_SCHEMA_VERSION, RETENTION_CLEANUP_SCHEMA_VERSION}:
        return _cleanup_summary(payload, schema=schema)
    if schema == CAMPAIGN_PREFLIGHT_SCHEMA_VERSION:
        return _campaign_preflight_summary(payload)
    return {}


def _matrix_gate_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "schema_version": MATRIX_GATE_SCHEMA_VERSION,
        "matrix_name": payload.get("matrix_name"),
        "pass_rate_percent": payload.get("pass_rate_percent"),
        "failure_class_summary": payload.get("failure_class_summary") if isinstance(payload.get("failure_class_summary"), list) else [],
        "failure_class_artifacts_missing": _non_negative_int(payload.get("failure_class_artifacts_missing")),
        "tool_loop_stop_summary": payload.get("tool_loop_stop_summary") if isinstance(payload.get("tool_loop_stop_summary"), list) else [],
        "tool_loop_artifacts_missing": _non_negative_int(payload.get("tool_loop_artifacts_missing")),
    }
    return {key: value for key, value in summary.items() if value is not None}


def _cleanup_summary(payload: dict[str, Any], *, schema: str) -> dict[str, Any]:
    security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    selectors = payload.get("selectors") if isinstance(payload.get("selectors"), dict) else {}
    actions = payload.get("actions") if isinstance(payload.get("actions"), list) else []
    return {
        "schema_version": schema,
        "report_type": payload.get("report_type"),
        "execute": bool(payload.get("execute")),
        "action_count": _non_negative_int(payload.get("action_count")),
        "selector_count": len([key for key, value in selectors.items() if value is True]),
        "action_types": sorted(
            {
                str(item.get("action"))
                for item in actions
                if isinstance(item, dict) and item.get("action")
            }
        ),
        "contains_raw_secrets": bool(security.get("contains_raw_secrets")),
        "contains_raw_provider_payloads": bool(security.get("contains_raw_provider_payloads")),
        "reads_keyring_values": bool(security.get("reads_keyring_values")),
        "contacts_providers": bool(security.get("contacts_providers")),
        "contains_local_paths": bool(security.get("contains_local_paths", True)),
        "direct_publication_safe": bool(security.get("direct_publication_safe")),
        "audit_log_required": bool(security.get("audit_log_required")),
    }


def _campaign_preflight_summary(payload: dict[str, Any]) -> dict[str, Any]:
    review_summary = payload.get("review_summary") if isinstance(payload.get("review_summary"), dict) else {}
    security = review_summary.get("security") if isinstance(review_summary.get("security"), dict) else {}
    manifest_security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    uses_review_summary = bool(review_summary)
    return {
        "schema_version": CAMPAIGN_PREFLIGHT_SCHEMA_VERSION,
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
            review_summary.get("benchmark_readiness_report_count")
            or (payload.get("benchmark_readiness") if isinstance(payload.get("benchmark_readiness"), dict) else {}).get("report_count")
        ),
        "contains_local_paths": bool(
            security.get("contains_local_paths")
            if uses_review_summary
            else manifest_security.get("contains_local_paths", True)
        ),
        "external_publication_safe": bool(security.get("external_publication_safe")) if uses_review_summary else False,
    }


def _harness_summary(payload: dict[str, Any]) -> dict[str, Any]:
    suite = payload.get("suite") if isinstance(payload.get("suite"), dict) else {}
    review = payload.get("review") if isinstance(payload.get("review"), dict) else {}
    generator = payload.get("generator") if isinstance(payload.get("generator"), dict) else {}
    return {
        "schema_version": HARNESS_REVIEW_SCHEMA_VERSION,
        "suite_name": suite.get("name"),
        "case_count": _non_negative_int(suite.get("case_count")),
        "generated": bool(payload.get("generated")),
        "generator_profile": generator.get("profile"),
        "review_status": review.get("status"),
        "calibration_required_before_release_gate": bool(review.get("calibration_required_before_release_gate")),
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
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "schema_version": ENGINE_ADVISORY_SCHEMA_VERSION,
        "engine": payload.get("engine"),
        "priority_count": _non_negative_int(summary.get("priority_count")),
        "highest_priority": summary.get("highest_priority"),
        "no_dispatch": bool(summary.get("no_dispatch")),
        "top_priorities": _compact_priorities(payload.get("priorities")),
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
    values = payload.get("values") if isinstance(payload.get("values"), dict) else {}
    quality = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
    comparison = payload.get("comparison_readiness") if isinstance(payload.get("comparison_readiness"), dict) else {}
    stats = payload.get("stats_comparability") if isinstance(payload.get("stats_comparability"), dict) else {}
    populated_fields = sorted(
        str(field)
        for field, value in values.items()
        if value is not None and field not in {"raw_usage", "raw_stats"}
    )
    quality_counts: dict[str, int] = {}
    for status in quality.values():
        key = str(status)
        quality_counts[key] = quality_counts.get(key, 0) + 1
    return {
        "schema_version": NORMALIZED_TELEMETRY_SCHEMA_VERSION,
        "contract": payload.get("contract"),
        "native_adapter": payload.get("native_adapter"),
        "stats_profile": payload.get("stats_profile"),
        "populated_field_count": len(populated_fields),
        "missing_field_count": len(payload.get("missing") if isinstance(payload.get("missing"), list) else []),
        "publication_grade_field_count": _non_negative_int(comparison.get("publication_grade_field_count")),
        "advisory_field_count": _non_negative_int(comparison.get("advisory_field_count")),
        "raw_provenance_field_count": _non_negative_int(comparison.get("raw_provenance_field_count")),
        "comparison_guidance": comparison.get("guidance"),
        "quality_counts": quality_counts,
        "stats_requires_labeling": bool(stats.get("requires_labeling")),
        "stats_guidance": stats.get("guidance"),
        "stats_publication_grade_fields": _summary_string_list(stats.get("publication_grade_fields")),
        "stats_advisory_fields": _summary_string_list(stats.get("advisory_fields")),
        "missing_stats_fields": _summary_string_list(stats.get("missing_stats_fields")),
    }


def _matrix_pressure_summary(payload: dict[str, Any]) -> dict[str, Any]:
    totals = payload.get("totals") if isinstance(payload.get("totals"), dict) else {}
    return {
        "schema_version": MATRIX_PRESSURE_SCHEMA_VERSION,
        "matrix": payload.get("matrix"),
        "run_count": _non_negative_int(payload.get("run_count")),
        "case_count": _non_negative_int(totals.get("case_count")),
        "scheduled_prompt_tokens": _non_negative_int(totals.get("scheduled_prompt_tokens")),
        "concurrent_window_prompt_tokens": _non_negative_int(totals.get("concurrent_window_prompt_tokens")),
        "prefill_pressure_score": _non_negative_int(totals.get("prefill_pressure_score")),
        "concurrency_weighted_pressure_score": _non_negative_int(totals.get("concurrency_weighted_pressure_score")),
        "shared_static_prefix_groups": _non_negative_int(totals.get("shared_static_prefix_groups")),
        "shared_static_prefix_tokens": _non_negative_int(totals.get("shared_static_prefix_tokens")),
        "shared_static_reuse_tokens": _non_negative_int(totals.get("shared_static_reuse_tokens")),
        "engines": _string_list(payload.get("engines")),
        "models": _string_list(payload.get("models")),
        "suites": _string_list(payload.get("suites")),
        "concurrency_levels": _int_list(payload.get("concurrency_levels")),
        "highest_pressure_runs": _compact_matrix_pressure_runs(payload.get("highest_pressure_runs")),
    }


def _compact_matrix_pressure_runs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    runs = []
    for item in value:
        if not isinstance(item, dict):
            continue
        runs.append(
            {
                "index": _non_negative_int(item.get("index")),
                "engine": item.get("engine"),
                "model": item.get("model"),
                "suite": item.get("suite"),
                "concurrency": _non_negative_int(item.get("concurrency")),
                "prefill_pressure_level": item.get("prefill_pressure_level"),
                "concurrent_window_prompt_tokens": _non_negative_int(item.get("concurrent_window_prompt_tokens")),
                "concurrency_weighted_pressure_score": _non_negative_int(
                    item.get("concurrency_weighted_pressure_score")
                ),
                "shared_static_reuse_tokens": _non_negative_int(item.get("shared_static_reuse_tokens")),
            }
        )
    return runs[:5]


def _matrix_saturation_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    matrix = payload.get("matrix") if isinstance(payload.get("matrix"), dict) else {}
    evidence = payload.get("concurrency_evidence") if isinstance(payload.get("concurrency_evidence"), dict) else {}
    return {
        "schema_version": MATRIX_SATURATION_SCHEMA_VERSION,
        "matrix": matrix.get("name"),
        "ok": payload.get("ok"),
        "entry_count": _non_negative_int(summary.get("entry_count")),
        "group_count": _non_negative_int(summary.get("group_count")),
        "result_artifacts_loaded": _non_negative_int(summary.get("result_artifacts_loaded")),
        "result_artifacts_missing": _non_negative_int(summary.get("result_artifacts_missing")),
        "max_concurrency": _non_negative_int(evidence.get("max_concurrency") or summary.get("max_concurrency")),
        "multi_level_group_count": _non_negative_int(evidence.get("multi_level_group_count")),
        "concurrency_levels": _int_list(evidence.get("concurrency_levels")),
        "max_avg_queue_ms": _number_or_none(evidence.get("max_avg_queue_ms")),
        "max_avg_rate_limit_wait_ms": _number_or_none(evidence.get("max_avg_rate_limit_wait_ms")),
        "queue_wait_finding_count": _non_negative_int(evidence.get("queue_wait_finding_count")),
        "rate_limit_wait_finding_count": _non_negative_int(evidence.get("rate_limit_wait_finding_count")),
        "guidance": evidence.get("guidance"),
        "highest_queue_wait_entries": _compact_concurrency_entries(evidence.get("highest_queue_wait_entries")),
        "highest_rate_limit_wait_entries": _compact_concurrency_entries(evidence.get("highest_rate_limit_wait_entries")),
    }


def _matrix_scorecard_summary(payload: dict[str, Any]) -> dict[str, Any]:
    matrix = payload.get("matrix") if isinstance(payload.get("matrix"), dict) else {}
    scorecard = payload.get("scorecard") if isinstance(payload.get("scorecard"), dict) else {}
    failure_class_summary = (
        scorecard.get("failure_class_summary") if isinstance(scorecard.get("failure_class_summary"), list) else []
    )
    tool_loop_stop_summary = (
        scorecard.get("tool_loop_stop_summary") if isinstance(scorecard.get("tool_loop_stop_summary"), list) else []
    )
    return {
        "schema_version": MATRIX_SCORECARD_SCHEMA_VERSION,
        "matrix": matrix.get("name"),
        "completed_runs": _non_negative_int(matrix.get("completed_runs")),
        "total_runs": _non_negative_int(matrix.get("total_runs")),
        "failed_runs": _non_negative_int(matrix.get("failed_runs")),
        "entry_count": _non_negative_int(scorecard.get("entry_count")),
        "result_artifacts_loaded": _non_negative_int(scorecard.get("result_artifacts_loaded")),
        "total_cases": _non_negative_int(scorecard.get("total_cases")),
        "passed_cases": _non_negative_int(scorecard.get("passed_cases")),
        "failed_cases": _non_negative_int(scorecard.get("failed_cases")),
        "pass_rate_percent": _number_or_none(scorecard.get("pass_rate_percent")),
        "judge_rubric_cases": _non_negative_int(scorecard.get("judge_rubric_cases")),
        "judge_verdicts_valid": _non_negative_int(scorecard.get("judge_verdicts_valid")),
        "invalid_tool_call_count": _non_negative_int(scorecard.get("invalid_tool_call_count")),
        "tool_parser_repair_cases": _non_negative_int(scorecard.get("tool_parser_repair_cases")),
        "tool_parser_repairs_valid": _non_negative_int(scorecard.get("tool_parser_repairs_valid")),
        "tool_parser_repair_valid_rate_percent": _number_or_none(scorecard.get("tool_parser_repair_valid_rate_percent")),
        "failure_class_summary": failure_class_summary,
        "tool_loop_stop_summary": tool_loop_stop_summary,
        "telemetry_quality_summary": _compact_telemetry_quality_summary(scorecard.get("telemetry_quality_summary")),
        "stats_comparability_summary": _compact_stats_comparability_summary(scorecard.get("stats_comparability_summary")),
        "concurrency_evidence": _compact_scorecard_concurrency_evidence(scorecard.get("concurrency_evidence")),
        "engine_targets": _compact_engine_targets(scorecard.get("engine_targets")),
        "architecture_summary": _compact_scorecard_group_summary(
            payload.get("architecture_summary"),
            key="model_architecture",
        ),
        "quantization_summary": _compact_scorecard_group_summary(
            payload.get("quantization_summary"),
            key="quantization",
        ),
    }


def _selftest_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
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
    }


def _artifact_label(value: Any, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return Path(value).name
    return default


def _publication_brief_summary(payload: dict[str, Any]) -> dict[str, Any]:
    claim_readiness = payload.get("claim_readiness") if isinstance(payload.get("claim_readiness"), dict) else {}
    security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    proof_points = payload.get("proof_points") if isinstance(payload.get("proof_points"), list) else []
    disclosures = payload.get("disclosures") if isinstance(payload.get("disclosures"), list) else []
    matrix_scorecards = payload.get("matrix_scorecards") if isinstance(payload.get("matrix_scorecards"), list) else []
    ready = payload.get("ready")
    status = "informational"
    if ready is True:
        status = "pass"
    elif ready is False:
        status = "review"
    if security.get("contains_secrets") is True or security.get("contains_raw_provider_payloads") is True:
        status = "fail"
    artifact_name = _artifact_label(payload.get("name"), "publication-brief.json")
    return {
        "schema_version": PUBLICATION_BRIEF_SCHEMA_VERSION,
        "status": status,
        "name": artifact_name,
        "ready": ready if isinstance(ready, bool) else None,
        "source_artifact_count": _non_negative_int(security.get("source_artifact_count")),
        "proof_point_count": len(proof_points),
        "disclosure_count": len(disclosures),
        "matrix_scorecard_count": len(matrix_scorecards),
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
        "claim_checks": _non_negative_int(claim_readiness.get("checks")),
        "claim_blockers": _non_negative_int(claim_readiness.get("blockers")),
        "claim_warnings": _non_negative_int(claim_readiness.get("warnings")),
        "contains_raw_provider_payloads": bool(security.get("contains_raw_provider_payloads")),
        "contains_secrets": bool(security.get("contains_secrets")),
        "shareable_summary_only": True,
    }


def _protocol_repair_summary(payload: dict[str, Any]) -> dict[str, Any]:
    scorecard = payload.get("scorecard_summary") if isinstance(payload.get("scorecard_summary"), dict) else {}
    gate = payload.get("matrix_gate_summary") if isinstance(payload.get("matrix_gate_summary"), dict) else {}
    security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    return {
        "schema_version": PROTOCOL_REPAIR_POSTURE_SCHEMA_VERSION,
        "status": payload.get("status"),
        "name": _artifact_label(payload.get("name"), "protocol-repair.json"),
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
        "shareable_summary_only": True,
    }


def _workflow_readiness_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    return {
        "schema_version": WORKFLOW_READINESS_SCHEMA_VERSION,
        "status": payload.get("status"),
        "name": _artifact_label(payload.get("name"), "workflow-readiness.json"),
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
        "shareable_summary_only": True,
    }


def _security_posture_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    secret_backend = (
        payload.get("secret_backend_posture") if isinstance(payload.get("secret_backend_posture"), dict) else {}
    )
    return {
        "schema_version": SECURITY_POSTURE_SCHEMA_VERSION,
        "status": payload.get("status"),
        "name": _artifact_label(payload.get("name"), "security-posture.json"),
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
        "shareable_summary_only": True,
    }


def _sdlc_validation_manifest_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
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
    status = "review"
    if security.get("contains_secrets") is True or security.get("contains_raw_provider_payloads") is True:
        status = "fail"
    artifact_name = _artifact_label(payload.get("name"), "sdlc-validation-manifest.json")
    return {
        "schema_version": SDLC_VALIDATION_MANIFEST_SCHEMA_VERSION,
        "status": status,
        "name": artifact_name,
        "tier_count": _non_negative_int(summary.get("tier_count")),
        "required_gate_count": _non_negative_int(summary.get("required_gate_count")),
        "blocking_gate_count": _non_negative_int(summary.get("blocking_gate_count")),
        "chrome_flow_count": _non_negative_int(summary.get("chrome_flow_count")),
        "chrome_validation_step_count": _non_negative_int(summary.get("chrome_validation_step_count")),
        "chrome_tool": gui.get("chrome_tool"),
        "stable_selector_count": len(stable_selectors),
        "api_surface_count": len(api_surfaces),
        "expected_artifact_count": len(expected_artifacts),
        "runs_tests": bool(security.get("runs_tests")),
        "contacts_providers": bool(security.get("contacts_providers")),
        "contains_raw_provider_payloads": bool(security.get("contains_raw_provider_payloads")),
        "contains_secrets": bool(security.get("contains_secrets")),
        "shareable_summary_only": True,
    }


def _benchmark_readiness_summary(payload: dict[str, Any]) -> dict[str, Any]:
    report_summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else payload
    return {
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
        "keyring_dependency_available": bool(report_summary.get("keyring_dependency_available")),
        "blocking_findings": _non_negative_int(report_summary.get("blocking_findings")),
        "warnings": _non_negative_int(report_summary.get("warnings")),
        "provider_auth_posture": _compact_provider_auth_posture(payload.get("provider_auth_posture")),
    }


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
    auth_posture = _compact_provider_auth_posture(
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
    )
    policy_controls = payload.get("policy_controls") if isinstance(payload.get("policy_controls"), dict) else {}
    secret_backend = _compact_secret_backend_posture(payload.get("secret_backend_posture"))
    return {
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
        "provider_auth_posture": auth_posture,
        "finding_codes": finding_codes[:12],
        "policy_controls": {str(key): bool(value) for key, value in policy_controls.items()},
        "shareable_summary_only": True,
    }


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
    return {
        "schema_version": IMPLEMENTATION_STATUS_SCHEMA_VERSION,
        "status": implementation_status,
        "implementation_status": implementation_status,
        "implemented_areas": _non_negative_int(payload.get("implemented_areas")),
        "partial_areas": _non_negative_int(payload.get("partial_areas")),
        "missing_areas": _non_negative_int(payload.get("missing_areas")),
        "built_in_suite_count": _non_negative_int(suite_inventory.get("built_in_suite_count")),
        "harness_engineering_suite_present": bool(suite_inventory.get("harness_engineering_suite_present")),
        "harness_engineering_case_count": len(_string_list(suite_inventory.get("harness_engineering_cases"))),
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
        "secret_backends": _string_list(enterprise.get("secret_backends")),
        "publication_governance_consumers": len(_string_list(publication.get("redaction_safe_summary_consumers"))),
        "selftest_report_schema": selftest.get("report_schema"),
        "chrome_codex_gate_present": bool(selftest.get("chrome_codex_gate_present")),
        "tests_run_by_this_command": bool(validation.get("tests_run_by_this_command")),
        "validation_required_next_step": validation.get("required_next_step"),
        "shareable_summary_only": True,
    }


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


def _compact_concurrency_entries(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    entries = []
    for item in value:
        if not isinstance(item, dict):
            continue
        entries.append(
            {
                "group_id": item.get("group_id"),
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


def _compact_scorecard_concurrency_evidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "schema_version": value.get("schema_version"),
        "entry_count": _non_negative_int(value.get("entry_count")),
        "artifact_loaded_count": _non_negative_int(value.get("artifact_loaded_count")),
        "concurrency_levels": _int_list(value.get("concurrency_levels")),
        "multi_level": bool(value.get("multi_level")),
        "max_concurrency": _non_negative_int(value.get("max_concurrency")),
        "max_avg_queue_ms": _number_or_none(value.get("max_avg_queue_ms")),
        "max_avg_rate_limit_wait_ms": _number_or_none(value.get("max_avg_rate_limit_wait_ms")),
        "guidance": value.get("guidance"),
        "highest_queue_wait_entries": _compact_concurrency_entries(value.get("highest_queue_wait_entries")),
        "highest_rate_limit_wait_entries": _compact_concurrency_entries(value.get("highest_rate_limit_wait_entries")),
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


def _publication_bundle_summary(payload: dict[str, Any]) -> dict[str, Any]:
    readiness = payload.get("publication_readiness") if isinstance(payload.get("publication_readiness"), dict) else {}
    security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    return {
        "schema_version": PUBLICATION_BUNDLE_MANIFEST_SCHEMA_VERSION,
        "run_id": payload.get("run_id"),
        "artifact_count": _non_negative_int(payload.get("artifact_count")),
        "artifacts": _string_list(payload.get("artifacts")),
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


def _publication_bundle_status(summary: dict[str, Any]) -> tuple[str, str]:
    security = summary.get("security") if isinstance(summary.get("security"), dict) else {}
    if any(
        security.get(key) is True
        for key in ("contains_raw_secrets", "contains_raw_provider_payloads", "contains_results_jsonl")
    ):
        return "fail", "security"
    readiness = summary.get("publication_readiness") if isinstance(summary.get("publication_readiness"), dict) else {}
    status = readiness.get("status")
    if status == "blocked":
        return "fail", "publication_readiness.status"
    media_status, media_status_source = _publication_media_kit_status(summary)
    if media_status == "review":
        return "review", media_status_source
    if status == "ready":
        return "pass", "publication_readiness.status"
    return "review", "publication_readiness.status"


def _publication_media_kit_status(summary: dict[str, Any]) -> tuple[str, str]:
    media_kit = summary.get("media_kit") if isinstance(summary.get("media_kit"), dict) else {}
    if media_kit.get("schema_version") != MEDIA_KIT_SCHEMA_VERSION:
        return "review", "media_kit.schema_version"
    missing = media_kit.get("missing_recommended_assets")
    if isinstance(missing, list) and missing:
        return "review", "media_kit.missing_recommended_assets"
    return "pass", "media_kit"


def _matrix_publication_bundle_summary(payload: dict[str, Any]) -> dict[str, Any]:
    security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    matrix = payload.get("matrix") if isinstance(payload.get("matrix"), dict) else {}
    return {
        "schema_version": MATRIX_PUBLICATION_BUNDLE_MANIFEST_SCHEMA_VERSION,
        "artifact_count": _non_negative_int(payload.get("artifact_count")),
        "artifacts": _string_list(payload.get("artifacts")),
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
        "media_kit": _media_kit_summary(payload.get("media_kit")),
        "security": {
            "contains_raw_secrets": bool(security.get("contains_raw_secrets")),
            "contains_raw_provider_payloads": bool(security.get("contains_raw_provider_payloads")),
            "contains_results_jsonl": bool(security.get("contains_results_jsonl")),
            "contains_per_run_raw_traces": bool(security.get("contains_per_run_raw_traces")),
        },
    }


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
        "missing_recommended_assets": _string_list(value.get("missing_recommended_assets")),
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


def _provider_contract_summary(payload: dict[str, Any]) -> dict[str, Any]:
    schema = payload.get("schema_version") or payload.get("schema")
    provider = payload.get("provider") if isinstance(payload.get("provider"), dict) else {}
    matrix = payload.get("matrix") if isinstance(payload.get("matrix"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    result: dict[str, Any] = {
        "schema_version": schema,
        "mode": payload.get("mode"),
        "ok": payload.get("ok"),
    }
    if provider:
        result["provider"] = provider.get("name")
        result["contract"] = provider.get("contract")
    if matrix:
        result["matrix"] = matrix.get("name")
        result["target_count"] = _non_negative_int(matrix.get("target_count"))
    if payload.get("model") is not None:
        result["model"] = payload.get("model")
    checks = {
        key: _non_negative_int(summary.get(key))
        for key in (
            "planned",
            "passed",
            "failed",
            "skipped",
            "planned_checks",
            "passed_checks",
            "failed_checks",
            "skipped_checks",
        )
        if key in summary
    }
    if checks:
        result["checks"] = checks
    capability_evidence = _contract_capability_evidence_summary(payload.get("capability_evidence"))
    if (
        capability_evidence["directly_checked"]
        or capability_evidence["proxy_checked_counts"]
        or capability_evidence["not_covered_counts"]
    ):
        result["capability_evidence"] = capability_evidence
    return {key: value for key, value in result.items() if value is not None}


def _contract_capability_evidence_summary(value: Any) -> dict[str, Any]:
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


def _release_review_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        category = str(artifact.get("category") or "")
        if category not in {
            "gates/matrix",
            "harness/review",
            "harness/calibration",
            "advisory/engine",
            "evidence/index",
            "governance/suite-audit",
            "metrics/coverage",
            "metrics/normalized-telemetry",
            "security/provider-audit",
            "audits/matrix-pressure",
            "audits/matrix-saturation",
            "reports/matrix-scorecard",
            "audits/provider-contract",
            "audits/provider-contract-matrix",
            "publication",
            "publication/matrix",
            "publication/brief",
            "publication/protocol-repair",
            "selftest",
            "selftest/validation-manifest",
            "readiness/campaign-preflight",
            "readiness/benchmark",
            "readiness/workflow",
            "security/posture",
        }:
            continue
        safe_summary = {
            "category": category,
            "archive_path": artifact.get("archive_path"),
            "schema_version": review_summary.get("schema_version") or artifact.get("schema"),
            "status": artifact.get("status"),
        }
        for key in (
            "matrix_name",
            "failure_class_summary",
            "failure_class_artifacts_missing",
            "tool_loop_stop_summary",
            "tool_loop_artifacts_missing",
            "suite_name",
            "generator_profile",
            "review_status",
            "calibration_required_before_release_gate",
            "require_release_gate",
            "passed",
            "known_good_runs",
            "known_bad_cases",
            "failure_taxonomy_entries",
            "findings",
            "warnings",
            "engine",
            "priority_count",
            "highest_priority",
            "top_priorities",
            "name",
            "artifact_count",
            "status_counts",
            "suite",
            "total_cases",
            "finding_count",
            "finding_codes",
            "provenance_counts",
            "risk_counts",
            "duplicate_fingerprint_count",
            "provider",
            "contract",
            "native_adapter",
            "coverage_score",
            "field_count",
            "counts",
            "publication_grade_group_count",
            "advisory_group_count",
            "partial_group_count",
            "unavailable_group_count",
            "publication_grade_groups",
            "review_required_groups",
            "stats_profile",
            "populated_field_count",
            "missing_field_count",
            "publication_grade_field_count",
            "advisory_field_count",
            "raw_provenance_field_count",
            "comparison_guidance",
            "quality_counts",
            "stats_requires_labeling",
            "stats_guidance",
            "stats_publication_grade_fields",
            "stats_advisory_fields",
            "missing_stats_fields",
            "run_count",
            "case_count",
            "scheduled_prompt_tokens",
            "concurrent_window_prompt_tokens",
            "prefill_pressure_score",
            "concurrency_weighted_pressure_score",
            "shared_static_prefix_groups",
            "shared_static_prefix_tokens",
            "shared_static_reuse_tokens",
            "engines",
            "models",
            "suites",
            "concurrency_levels",
            "highest_pressure_runs",
            "entry_count",
            "group_count",
            "result_artifacts_loaded",
            "result_artifacts_missing",
            "max_concurrency",
            "multi_level_group_count",
            "max_avg_queue_ms",
            "max_avg_rate_limit_wait_ms",
            "queue_wait_finding_count",
            "rate_limit_wait_finding_count",
            "guidance",
            "highest_queue_wait_entries",
            "highest_rate_limit_wait_entries",
            "completed_runs",
            "total_runs",
            "failed_runs",
            "passed_cases",
            "failed_cases",
            "pass_rate_percent",
            "judge_rubric_cases",
            "judge_verdicts_valid",
            "invalid_tool_call_count",
            "tool_parser_repair_cases",
            "tool_parser_repairs_valid",
            "tool_parser_repair_valid_rate_percent",
            "telemetry_quality_summary",
            "concurrency_evidence",
            "mode",
            "ok",
            "model",
            "matrix",
            "target_count",
            "checks",
            "capability_evidence",
            "run_id",
            "artifacts",
            "publication_readiness",
            "matrix",
            "media_kit",
            "security",
            "source_artifact_count",
            "proof_point_count",
            "disclosure_count",
            "matrix_scorecard_count",
            "claim_checks",
            "claim_blockers",
            "claim_warnings",
            "contains_raw_provider_payloads",
            "contains_secrets",
            "shareable_summary_only",
            "scorecard_source_count",
            "scorecard_invalid_tool_call_count",
            "scorecard_tool_parser_repair_cases",
            "scorecard_tool_parser_repairs_valid",
            "matrix_gate_source_count",
            "matrix_gate_invalid_tool_call_count",
            "matrix_gate_tool_parser_repair_cases",
            "matrix_gate_tool_parser_repairs_valid",
            "matrix_gate_tool_parser_repair_artifacts_missing",
            "disclosure_count",
            "recommendation_count",
            "source_count",
            "required_surface_count",
            "covered_required_surface_count",
            "gap_count",
            "required_surfaces",
            "blockers",
            "provider_audit_count",
            "redaction_scan_count",
            "review_artifact_count",
            "redaction_finding_count",
            "unsafe_review_artifact_count",
            "keyring_optional",
            "keyring_dependency_available",
            "reads_keyring_values",
            "resolves_secret_references",
            "tier",
            "exit_code",
            "duration_ms",
            "browser",
            "headed",
            "marker_expression",
            "junit_xml_present",
            "tier_count",
            "required_gate_count",
            "blocking_gate_count",
            "chrome_flow_count",
            "chrome_validation_step_count",
            "chrome_tool",
            "stable_selector_count",
            "api_surface_count",
            "expected_artifact_count",
            "runs_tests",
            "contacts_providers",
            "ready",
            "strict_unknown",
            "policy_ok",
            "suite_compatible",
            "contract_checks_planned",
            "contract_capabilities_directly_checked",
            "contract_capabilities_proxy_checked",
            "contract_capabilities_not_covered",
            "metric_coverage_score",
            "provider_auth_writable_backends",
            "provider_auth_plaintext_fallbacks",
            "provider_auth_prewrite_policy_guards_recommended",
            "blocking_findings",
            "warnings",
            "provider_auth_posture",
            "review_summary_schema_version",
            "matrix_count",
            "includes_provider_audit",
            "includes_benchmark_readiness",
            "benchmark_readiness_report_count",
            "contains_local_paths",
            "external_publication_safe",
            "total_providers",
            "remote_providers",
            "policy_ok_count",
            "error_count",
            "warning_count",
            "plaintext_dotenv_provider_count",
            "writable_secret_backend_count",
            "prewrite_policy_guard_recommended_count",
            "provider_auth_posture",
            "finding_codes",
            "policy_controls",
        ):
            if key in review_summary:
                safe_summary[key] = review_summary[key]
        summaries.append(safe_summary)
    return summaries[:20]


def _compact_priorities(value: Any) -> list[dict[str, Any]]:
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
                "aligned_artifacts_or_suites": _string_list(item.get("aligned_artifacts_or_suites")),
            }
        )
    return priorities[:8]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value[:8] if item is not None]


def _int_list(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    return [_non_negative_int(item) for item in value[:8]]


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


def _zip_schema(path: Path) -> str | None:
    name = path.name
    if name.endswith(".agentblaster-release-qualification.zip"):
        return "agentblaster.release-qualification-bundle"
    if name.endswith(".agentblaster-publication.zip"):
        return "agentblaster.publication-bundle"
    if name.endswith(".agentblaster-matrix-publication.zip"):
        return "agentblaster.matrix-publication-bundle"
    if name.endswith(".agentblaster-evidence.zip"):
        return "agentblaster.evidence-bundle"
    return None


def _status_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        status = str(item.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _int_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _non_negative_int(raw) for key, raw in value.items()}


def _readiness(items: list[dict[str, Any]]) -> dict[str, Any]:
    blocking = [item for item in items if str(item.get("status") or "") in BLOCKING_STATUSES]
    review = [item for item in items if str(item.get("status") or "") in REVIEW_STATUSES]
    blocking_statuses = sorted({str(item.get("status")) for item in blocking})
    review_statuses = sorted({str(item.get("status")) for item in review})
    if blocking:
        state = "blocked"
        guidance = "Resolve failing or unreadable evidence artifacts before publication or release qualification."
    elif review:
        state = "review-required"
        guidance = "Packet has no blocking artifact statuses, but reviewer signoff is required before publication."
    else:
        state = "ready"
        guidance = "Packet has only passing inspected artifact statuses."
    return {
        "ready": state == "ready",
        "state": state,
        "blocking_artifact_count": len(blocking),
        "review_artifact_count": len(review),
        "blocking_statuses": blocking_statuses,
        "review_statuses": review_statuses,
        "guidance": guidance,
    }


def _cleanup_evidence(items: list[dict[str, Any]]) -> dict[str, Any]:
    summaries = [
        item.get("review_summary")
        for item in items
        if item.get("schema") in {CLEANUP_PLAN_SCHEMA_VERSION, RETENTION_CLEANUP_SCHEMA_VERSION}
        and isinstance(item.get("review_summary"), dict)
    ]
    manual = [item for item in summaries if item.get("schema_version") == CLEANUP_PLAN_SCHEMA_VERSION]
    retention = [item for item in summaries if item.get("schema_version") == RETENTION_CLEANUP_SCHEMA_VERSION]
    executed = [item for item in summaries if item.get("execute") is True]
    return {
        "artifact_count": len(summaries),
        "manual_report_count": len(manual),
        "retention_report_count": len(retention),
        "planned_report_count": len(summaries) - len(executed),
        "executed_report_count": len(executed),
        "audit_log_required_count": sum(1 for item in summaries if item.get("audit_log_required") is True),
        "contains_local_paths": any(item.get("contains_local_paths") is True for item in summaries),
        "direct_publication_safe": all(item.get("direct_publication_safe") is True for item in summaries) if summaries else False,
        "shareable_summary_only": bool(summaries),
    }


def _summary_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value[:12] if item is not None]


def _summary_int_list(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    return [_non_negative_int(item) for item in value[:12]]


def _non_negative_int(value: Any) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def _safe_name(name: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in name).strip("-")
    return cleaned or "evidence-index"


def _safe_artifact_path(path: Path) -> str:
    if _artifact_path_redacted(path):
        return path.name
    return path.as_posix()


def _artifact_path_redacted(path: Path) -> bool:
    text = path.as_posix()
    return path.is_absolute() or text.startswith("../") or "/../" in text
