from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentblaster.errors import ConfigError
from agentblaster.reports import load_manifest, load_results
from agentblaster.telemetry import (
    ADVISORY_TELEMETRY_QUALITY,
    COMPARABLE_TELEMETRY_FIELDS,
    NORMALIZED_TELEMETRY_FIELDS,
    PUBLICATION_GRADE_TELEMETRY_QUALITY,
)


TELEMETRY_AUDIT_SCHEMA_VERSION = "agentblaster.telemetry-audit.v1"
DEFAULT_REQUIRED_FIELDS = (
    "latency_ms",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "ttft_ms",
    "prompt_eval_ms",
    "decode_ms",
    "tokens_per_second_decode",
)


def audit_run_telemetry(
    run_dir: Path,
    *,
    required_fields: list[str] | None = None,
    min_required_completeness: float = 1.0,
) -> dict[str, Any]:
    """Audit normalized telemetry provenance for a completed run."""

    if min_required_completeness < 0 or min_required_completeness > 1:
        raise ConfigError("min_required_completeness must be between 0 and 1")
    required = required_fields or list(DEFAULT_REQUIRED_FIELDS)
    unknown = [field for field in required if field not in NORMALIZED_TELEMETRY_FIELDS]
    if unknown:
        raise ConfigError(f"unknown telemetry field(s): {', '.join(unknown)}")

    manifest = load_manifest(run_dir)
    results = load_results(run_dir)
    fields = [_field_audit(field, results) for field in NORMALIZED_TELEMETRY_FIELDS]
    field_map = {field["field"]: field for field in fields}
    findings = []
    schema_versions = sorted(
        {
            result.telemetry_schema_version
            for result in results
            if result.telemetry_schema_version
        }
    )
    rows_without_schema = sum(1 for result in results if not result.telemetry_schema_version)
    if rows_without_schema:
        findings.append(
            {
                "severity": "warning",
                "field": "telemetry_schema_version",
                "message": f"{rows_without_schema} result row(s) do not record normalized telemetry schema version",
            }
        )
    for field in required:
        item = field_map[field]
        if item["completeness"] < min_required_completeness:
            findings.append(
                {
                    "severity": "blocker",
                    "field": field,
                    "message": (
                        f"{field} completeness {item['completeness']:.3f} is below required "
                        f"{min_required_completeness:.3f}"
                    ),
                }
            )
    comparable_core_ok = not any(finding["severity"] == "blocker" for finding in findings)
    present_fields = [field for field in fields if field["present_count"] > 0]
    fully_present_fields = [field for field in fields if field["present_count"] == len(results) and results]
    comparison_readiness = _comparison_readiness(fields, required)
    return {
        "schema_version": TELEMETRY_AUDIT_SCHEMA_VERSION,
        "run": {
            "run_id": manifest.run_id,
            "suite": manifest.suite,
            "provider": manifest.provider,
            "contract": manifest.contract.value,
            "model": manifest.model,
            "raw_trace_mode": manifest.raw_trace_mode.value,
        },
        "total_cases": len(results),
        "required_fields": required,
        "min_required_completeness": min_required_completeness,
        "summary": {
            "field_count": len(fields),
            "present_field_count": len(present_fields),
            "fully_present_field_count": len(fully_present_fields),
            "missing_field_count": len(fields) - len(present_fields),
            "average_field_completeness": _average([field["completeness"] for field in fields]),
            "telemetry_schema_versions": schema_versions,
            "rows_without_telemetry_schema": rows_without_schema,
            "comparable_core_ok": comparable_core_ok,
            "publication_grade_field_count": comparison_readiness["publication_grade_field_count"],
            "advisory_field_count": comparison_readiness["advisory_field_count"],
            "missing_comparable_field_count": len(comparison_readiness["missing_comparable_fields"]),
            "comparison_readiness_guidance": comparison_readiness["guidance"],
        },
        "comparison_readiness": comparison_readiness,
        "fields": fields,
        "findings": findings,
        "security_notes": [
            "Telemetry audit reads normalized result rows only.",
            "It does not read raw trace artifacts, provider configs, environment variables, keyrings, or remote endpoints.",
            "Source maps identify metric provenance but should not contain prompts, headers, API keys, or raw provider payloads.",
        ],
    }


def write_telemetry_audit_json(report: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def format_telemetry_audit(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "AgentBlaster telemetry audit",
        f"run_id: {report['run']['run_id']}",
        f"provider: {report['run']['provider']} ({report['run']['contract']})",
        f"suite: {report['run']['suite']}",
        f"total_cases: {report['total_cases']}",
        f"present_fields: {summary['present_field_count']}/{summary['field_count']}",
        f"fully_present_fields: {summary['fully_present_field_count']}/{summary['field_count']}",
        f"average_field_completeness: {summary['average_field_completeness']}",
        f"comparable_core_ok: {str(summary['comparable_core_ok']).lower()}",
        f"comparison_readiness: {summary.get('comparison_readiness_guidance', 'unknown')}",
        f"publication_grade_fields: {summary.get('publication_grade_field_count', 0)}",
        f"advisory_fields: {summary.get('advisory_field_count', 0)}",
        f"findings: {len(report['findings'])}",
    ]
    for finding in report["findings"]:
        lines.append(f"- {finding['severity'].upper()} {finding['field']}: {finding['message']}")
    lines.append("fields:")
    for field in report["fields"]:
        if field["present_count"] or field["field"] in report["required_fields"]:
            lines.append(
                f"- {field['field']}: completeness={field['completeness']} "
                f"present={field['present_count']} missing={field['missing_count']} "
                f"quality={field['source_quality_counts']}"
            )
    return "\n".join(lines) + "\n"


def _field_audit(field: str, results: list[Any]) -> dict[str, Any]:
    present_count = 0
    source_counts: dict[str, int] = {}
    source_quality_counts: dict[str, int] = {
        "native": 0,
        "measured": 0,
        "inferred": 0,
        "conditional": 0,
        "raw_provenance": 0,
        "unknown": 0,
        "unavailable": 0,
    }
    for result in results:
        value = getattr(result, field, None)
        missing = field in (result.telemetry_missing or [])
        source = (result.telemetry_sources or {}).get(field)
        quality = (getattr(result, "telemetry_quality", {}) or {}).get(field)
        if _has_telemetry_value(value):
            present_count += 1
            if source:
                source_counts[source] = source_counts.get(source, 0) + 1
            source_quality_counts[_normalized_quality(field, quality, source)] += 1
        elif missing:
            source_quality_counts["unavailable"] += 1
        else:
            source_quality_counts["unknown"] += 1
    missing_count = max(0, len(results) - present_count)
    return {
        "field": field,
        "present_count": present_count,
        "missing_count": missing_count,
        "completeness": round(present_count / len(results), 6) if results else 0.0,
        "source_counts": dict(sorted(source_counts.items())),
        "source_quality_counts": source_quality_counts,
    }


def _comparison_readiness(fields: list[dict[str, Any]], required_fields: list[str]) -> dict[str, Any]:
    by_name = {field["field"]: field for field in fields}
    publication_grade_fields = []
    advisory_fields = []
    unknown_quality_fields = []
    missing_comparable_fields = []
    incomplete_comparable_fields = []
    for field_name in COMPARABLE_TELEMETRY_FIELDS:
        field = by_name[field_name]
        counts = field["source_quality_counts"]
        present_count = field["present_count"]
        publication_count = sum(counts.get(quality, 0) for quality in PUBLICATION_GRADE_TELEMETRY_QUALITY)
        advisory_count = sum(counts.get(quality, 0) for quality in ADVISORY_TELEMETRY_QUALITY)
        if present_count == 0:
            missing_comparable_fields.append(field_name)
        if field["missing_count"]:
            incomplete_comparable_fields.append(field_name)
        if publication_count and publication_count == present_count:
            publication_grade_fields.append(field_name)
        if advisory_count:
            advisory_fields.append(field_name)
        if counts.get("unknown", 0):
            unknown_quality_fields.append(field_name)
    required_advisory_fields = [field for field in required_fields if field in advisory_fields]
    required_unknown_quality_fields = [field for field in required_fields if field in unknown_quality_fields]
    if required_unknown_quality_fields:
        guidance = "resolve-unknown-required-telemetry-provenance-before-comparison"
    elif required_advisory_fields:
        guidance = "label-inferred-or-conditional-required-fields-before-cross-engine-comparison"
    elif missing_comparable_fields or incomplete_comparable_fields:
        guidance = "publish-only-with-explicit-missing-field-disclosure"
    elif publication_grade_fields:
        guidance = "publication-grade-for-present-required-fields-when-release-gates-pass"
    else:
        guidance = "insufficient-normalized-telemetry-for-comparison"
    return {
        "schema_version": "agentblaster.telemetry-comparison-readiness.v1",
        "comparable_field_count": len(COMPARABLE_TELEMETRY_FIELDS),
        "publication_grade_field_count": len(publication_grade_fields),
        "advisory_field_count": len(advisory_fields),
        "unknown_quality_field_count": len(unknown_quality_fields),
        "publication_grade_fields": publication_grade_fields,
        "advisory_fields": advisory_fields,
        "unknown_quality_fields": unknown_quality_fields,
        "missing_comparable_fields": missing_comparable_fields,
        "incomplete_comparable_fields": incomplete_comparable_fields,
        "required_advisory_fields": required_advisory_fields,
        "required_unknown_quality_fields": required_unknown_quality_fields,
        "guidance": guidance,
    }


def _has_telemetry_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (dict, list, tuple, set, str)) and not value:
        return False
    return True


def _normalized_quality(field: str, quality: Any, source: str | None) -> str:
    if isinstance(quality, str) and quality in {
        "native",
        "measured",
        "inferred",
        "conditional",
        "raw_provenance",
        "unknown",
        "unavailable",
    }:
        return quality
    return _source_quality(field, source)


def _source_quality(field: str, source: str | None) -> str:
    if field in {"raw_usage", "raw_stats"}:
        return "raw_provenance"
    if not source:
        return "unknown"
    lowered = source.lower()
    if lowered.startswith("agentblaster") or " timer" in lowered:
        return "measured"
    if lowered.startswith("derived") or "/" in lowered or " + " in lowered or "input + output" in lowered:
        return "inferred"
    if (
        lowered.startswith("usage.")
        or lowered.startswith("stats.")
        or lowered.startswith("metrics.")
        or lowered.startswith("timings.")
        or lowered.startswith("prompt_eval_")
        or lowered.startswith("eval_")
        or lowered.startswith("load_")
        or lowered.startswith("done_")
        or lowered.startswith("choices")
        or lowered == "status"
        or lowered == "stop_reason"
    ):
        return "native"
    if "when exposed" in lowered or "optional" in lowered:
        return "conditional"
    return "unknown"


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 6)
