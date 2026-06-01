from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentblaster.errors import ConfigError
from agentblaster.matrix import load_matrix_file
from agentblaster.models import BenchmarkCase, SuiteDefinition
from agentblaster.suites import get_builtin_suite, load_suite_file


WORKFLOW_READINESS_SCHEMA_VERSION = "agentblaster.workflow-readiness.v1"
MATRIX_PRESSURE_SCHEMA_VERSION = "agentblaster.matrix-pressure-audit.v1"
HARNESS_REVIEW_SCHEMA_VERSION = "agentblaster.harness-review.v1"


SURFACE_DEFINITIONS: dict[str, dict[str, str]] = {
    "tool-calling": {
        "family": "tool-calling",
        "purpose": "API-native tool declaration, selection, and argument emission.",
    },
    "tool-loop": {
        "family": "tool-calling",
        "purpose": "Multi-step or multi-tool planning loops with bounded tool-call depth.",
    },
    "structured-output": {
        "family": "structured-output",
        "purpose": "JSON object/schema adherence and machine-readable verdicts.",
    },
    "concurrency": {
        "family": "pressure",
        "purpose": "Fan-out, burst, queueing, rate-limit wait, and isolation pressure.",
    },
    "prefill-cache": {
        "family": "pressure",
        "purpose": "Large repeated prefixes, cache reuse, and cache invalidation diagnostics.",
    },
    "mcp": {
        "family": "mcp",
        "purpose": "Fixture MCP-style tool, resource, and prompt catalog expansion.",
    },
    "lcp": {
        "family": "lcp",
        "purpose": "Fixture local-context bundle and scoped memory attachment behavior.",
    },
    "skills": {
        "family": "skills",
        "purpose": "Instruction-heavy skill prefixes and skill-routing overhead.",
    },
    "cancellation": {
        "family": "streaming",
        "purpose": "Streaming abort behavior and cancellation latency.",
    },
    "trace-replay": {
        "family": "agent-history",
        "purpose": "Prior assistant/tool-result replay and conversational state handling.",
    },
    "judge-rubric": {
        "family": "evaluation",
        "purpose": "Structured evaluator prompts and rubric verdict discipline.",
    },
    "harness-engineering": {
        "family": "harness-engineering",
        "purpose": "Generated or transformed benchmark suites for method research.",
    },
    "agent-profile": {
        "family": "agent-profile",
        "purpose": "Representative local-agent workflow profiles such as coding, planning, and tool agents.",
    },
}

DEFAULT_REQUIRED_SURFACES: tuple[str, ...] = (
    "tool-calling",
    "tool-loop",
    "structured-output",
    "concurrency",
    "prefill-cache",
    "mcp",
    "lcp",
    "skills",
    "cancellation",
    "harness-engineering",
)


def build_workflow_readiness_report(
    *,
    name: str,
    suite_names: list[str] | None = None,
    suite_files: list[Path] | None = None,
    matrices: list[Path] | None = None,
    matrix_pressure_audits: list[Path] | None = None,
    harness_reviews: list[Path] | None = None,
    required_surfaces: list[str] | None = None,
) -> dict[str, Any]:
    """Build a no-dispatch readiness report for intended agentic workflow coverage."""
    required = tuple(required_surfaces or DEFAULT_REQUIRED_SURFACES)
    _validate_surfaces(required)
    sources = _collect_suite_sources(suite_names, suite_files, matrices)
    pressure_sources = [_matrix_pressure_source(_load_json_artifact(path, expected_schema=MATRIX_PRESSURE_SCHEMA_VERSION), path) for path in matrix_pressure_audits or []]
    harness_sources = [_harness_review_source(_load_json_artifact(path, expected_schema=HARNESS_REVIEW_SCHEMA_VERSION), path) for path in harness_reviews or []]
    if not sources and not pressure_sources and not harness_sources:
        raise ConfigError("provide at least one --suite, --suite-file, --matrix, --matrix-pressure-audit, or --harness-review")
    coverage = _empty_coverage(required)
    total_cases = 0
    concurrency_levels: set[int] = set()
    for source in sources:
        total_cases += _int(source.get("case_count"))
        concurrency_levels.update(_int(level) for level in source.get("concurrency_levels", []) if _int(level))
        for surface, count in source.get("surface_counts", {}).items():
            _record_surface(
                coverage,
                surface,
                case_count=_int(count),
                run_count=_int(source.get("run_count")),
                evidence=_source_label(source),
            )
    for source in pressure_sources:
        concurrency_levels.update(_int(level) for level in source.get("concurrency_levels", []) if _int(level))
        for surface, count in source.get("surface_counts", {}).items():
            _record_surface(
                coverage,
                surface,
                case_count=_int(count),
                run_count=_int(source.get("run_count")),
                evidence=_source_label(source),
            )
    for source in harness_sources:
        total_cases += _int(source.get("case_count"))
        for surface, count in source.get("surface_counts", {}).items():
            _record_surface(
                coverage,
                surface,
                case_count=_int(count),
                run_count=0,
                evidence=_source_label(source),
            )
    coverage_rows = list(coverage.values())
    required_rows = [row for row in coverage_rows if row["required"]]
    gaps = [
        {
            "surface": row["surface"],
            "family": row["family"],
            "purpose": row["purpose"],
            "severity": "blocker",
            "message": f"Required workflow surface {row['surface']} has no static coverage evidence.",
        }
        for row in required_rows
        if not row["present"]
    ]
    status = "ready" if not gaps else "review-required"
    source_artifacts = []
    source_artifacts.extend(_artifact_ref("suite_file", path) for path in suite_files or [])
    source_artifacts.extend(_artifact_ref("matrix", path) for path in matrices or [])
    source_artifacts.extend(_artifact_ref("matrix_pressure_audit", path) for path in matrix_pressure_audits or [])
    source_artifacts.extend(_artifact_ref("harness_review", path) for path in harness_reviews or [])
    return {
        "schema_version": WORKFLOW_READINESS_SCHEMA_VERSION,
        "name": _safe_name(name),
        "status": status,
        "ready": status == "ready",
        "required_surfaces": list(required),
        "summary": {
            "source_count": len(sources) + len(pressure_sources) + len(harness_sources),
            "suite_source_count": len(sources),
            "matrix_pressure_audit_count": len(pressure_sources),
            "harness_review_count": len(harness_sources),
            "case_count": total_cases,
            "surface_count": len(coverage_rows),
            "required_surface_count": len(required_rows),
            "covered_required_surface_count": len([row for row in required_rows if row["present"]]),
            "gap_count": len(gaps),
            "concurrency_levels": sorted(concurrency_levels),
            "max_concurrency": max(concurrency_levels) if concurrency_levels else 1,
        },
        "coverage": coverage_rows,
        "gaps": gaps,
        "suite_sources": sources,
        "matrix_pressure_audits": pressure_sources,
        "harness_reviews": harness_sources,
        "recommendations": _recommendations(gaps, coverage_rows),
        "security": {
            "source_artifact_count": len(source_artifacts),
            "source_artifacts": source_artifacts,
            "contains_raw_provider_payloads": False,
            "contains_raw_traces": False,
            "contains_secrets": False,
            "stores_raw_secrets": False,
            "contacts_providers": False,
            "dispatches_requests": False,
            "path_policy": "Input paths are reduced to relative artifact names or basenames for absolute/parent-relative paths.",
            "notes": [
                "Workflow readiness is static and does not dispatch providers, resolve secrets, or inspect keyring values.",
                "Suite prompts, tool arguments, raw results, raw traces, API keys, request headers, and provider payloads are excluded from the report.",
                "Use this artifact before expensive local or remote matrix execution to prove intended workflow-surface coverage.",
            ],
        },
    }


def write_workflow_readiness_json(report: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def write_workflow_readiness_markdown(report: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(format_workflow_readiness_report(report), encoding="utf-8")
    return output


def format_workflow_readiness_report(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        "# AgentBlaster Workflow Readiness",
        "",
        "## Summary",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Name | `{_markdown_cell(report.get('name'))}` |",
        f"| Status | `{_markdown_cell(report.get('status'))}` |",
        f"| Ready | `{str(report.get('ready')).lower()}` |",
        f"| Required coverage | `{summary.get('covered_required_surface_count', 0)}/{summary.get('required_surface_count', 0)}` |",
        f"| Gaps | `{summary.get('gap_count', 0)}` |",
        f"| Case count | `{summary.get('case_count', 0)}` |",
        f"| Sources | `{summary.get('source_count', 0)}` |",
        f"| Concurrency levels | `{_join_or_none(summary.get('concurrency_levels', []))}` |",
        f"| Max concurrency | `{summary.get('max_concurrency', 1)}` |",
        "",
        "## Coverage",
        "",
        "| Surface | Required | Present | Cases | Runs | Sources | Purpose |",
        "| --- | --- | --- | ---: | ---: | --- | --- |",
    ]
    for row in report.get("coverage", []) if isinstance(report.get("coverage"), list) else []:
        if not isinstance(row, dict):
            continue
        lines.append(
            "| "
            f"{_markdown_cell(row.get('surface'))} | "
            f"`{str(row.get('required')).lower()}` | "
            f"`{str(row.get('present')).lower()}` | "
            f"{row.get('case_count', 0)} | "
            f"{row.get('run_count', 0)} | "
            f"{_join_or_none(row.get('evidence', []))} | "
            f"{_markdown_cell(row.get('purpose'))} |"
        )
    lines.extend(["", "## Gaps", ""])
    gaps = report.get("gaps") if isinstance(report.get("gaps"), list) else []
    if gaps:
        lines.extend(f"- `{_markdown_cell(item.get('surface'))}`: {_markdown_cell(item.get('message'))}" for item in gaps if isinstance(item, dict))
    else:
        lines.append("No required workflow-surface gaps were found.")
    lines.extend(["", "## Recommendations", ""])
    lines.extend(f"- {_markdown_cell(item)}" for item in report.get("recommendations", []) or ["No recommendations generated."])
    lines.extend(
        [
            "",
            "## Security Boundary",
            "",
            "- This report is static and does not contact providers or resolve secrets.",
            "- Prompts, tool arguments, raw results, raw traces, API keys, request headers, and provider payloads are excluded.",
            "- Source artifact paths are reduced before inclusion.",
            "",
        ]
    )
    return "\n".join(lines)


def _collect_suite_sources(
    suite_names: list[str] | None,
    suite_files: list[Path] | None,
    matrices: list[Path] | None,
) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for suite_name in suite_names or []:
        suite = get_builtin_suite(suite_name)
        sources.append(_suite_source("suite", suite.name, suite, concurrency=1, artifact=None))
    for suite_file in suite_files or []:
        suite = load_suite_file(suite_file)
        sources.append(_suite_source("suite_file", suite.name, suite, concurrency=1, artifact=_artifact_ref("suite_file", suite_file)))
    for matrix_path in matrices or []:
        matrix = load_matrix_file(matrix_path)
        for index, run in enumerate(matrix.runs, start=1):
            suite = load_suite_file(run.suite_file) if run.suite_file is not None else get_builtin_suite(run.suite)
            source = _suite_source(
                "matrix_run",
                suite.name,
                suite,
                concurrency=run.concurrency,
                artifact=_artifact_ref("matrix", matrix_path),
            )
            source.update(
                {
                    "matrix_name": matrix.name,
                    "matrix_run_index": index,
                    "engine": run.engine,
                    "model": run.model,
                    "run_count": 1,
                    "concurrency_levels": [run.concurrency],
                }
            )
            if run.concurrency > 1:
                source["surface_counts"]["concurrency"] = max(source["surface_counts"].get("concurrency", 0), len(suite.cases))
            sources.append(source)
    return sources


def _suite_source(kind: str, name: str, suite: SuiteDefinition, *, concurrency: int, artifact: dict[str, str] | None) -> dict[str, Any]:
    surface_counts = _suite_surface_counts(suite)
    if concurrency > 1:
        surface_counts["concurrency"] = max(surface_counts.get("concurrency", 0), len(suite.cases))
    return {
        "kind": kind,
        "name": name,
        "artifact": artifact,
        "case_count": len(suite.cases),
        "run_count": 1,
        "concurrency_levels": [concurrency],
        "provenance_origin": suite.provenance.origin,
        "generator": suite.provenance.generator,
        "generator_profile": suite.provenance.generator_profile,
        "surface_counts": surface_counts,
    }


def _suite_surface_counts(suite: SuiteDefinition) -> dict[str, int]:
    counts: dict[str, int] = {}
    generated = suite.provenance.origin == "harness_generated" or bool(suite.provenance.generator)
    for case in suite.cases:
        surfaces = _case_surfaces(case)
        if generated:
            surfaces.add("harness-engineering")
        for surface in surfaces:
            counts[surface] = counts.get(surface, 0) + 1
    return dict(sorted(counts.items()))


def _case_surfaces(case: BenchmarkCase) -> set[str]:
    tags = {tag.lower() for tag in case.tags}
    metrics = {metric.lower() for metric in case.metrics}
    surfaces: set[str] = set()
    if case.tools or case.expected_tool_name or case.simulated_tools or case.tool_choice:
        surfaces.add("tool-calling")
    if (case.max_tool_calls and case.max_tool_calls > 1) or len(case.tools) > 1 or tags.intersection({"tool-loop", "orchestration", "multi-tool"}):
        surfaces.add("tool-loop")
    if case.response_format or case.expected_json_fields:
        surfaces.add("structured-output")
    if case.cancel_after_ms is not None or "cancellation" in tags or "cancellation_latency_ms" in metrics:
        surfaces.add("cancellation")
    if case.messages or "trace-replay" in tags:
        surfaces.add("trace-replay")
    if case.mcp_profile or "mcp" in tags or "mcp_profile_applied" in metrics:
        surfaces.add("mcp")
    if case.lcp_profile or "lcp" in tags or "lcp_context_applied" in metrics:
        surfaces.add("lcp")
    if case.skills or "skills" in tags or "skill_selection_valid" in metrics:
        surfaces.add("skills")
    if (
        case.cache_control
        or tags.intersection({"prefill", "cache", "cache-replay", "static-prefix", "repeated-system-prompt"})
        or metrics.intersection({"tokens_per_second_prefill", "cache_hit_ratio", "cached_input_tokens", "cache_write_tokens"})
        or len(case.system_prompt or "") >= 1500
    ):
        surfaces.add("prefill-cache")
    if tags.intersection({"concurrency", "fanout", "burst"}) or metrics.intersection({"queue_ms", "rate_limit_wait_ms", "requests_per_second"}):
        surfaces.add("concurrency")
    if tags.intersection({"harness", "emerging-workflows", "contract-fuzz", "metamorphic", "cache-replay", "tool-parser-repair"}):
        surfaces.add("harness-engineering")
    if "judge-rubric" in tags or "judge_verdict_valid" in metrics:
        surfaces.add("judge-rubric")
    if "agent-profile" in tags:
        surfaces.add("agent-profile")
    return surfaces


def _matrix_pressure_source(payload: dict[str, Any], path: Path) -> dict[str, Any]:
    totals = payload.get("totals") if isinstance(payload.get("totals"), dict) else {}
    runs = payload.get("runs") if isinstance(payload.get("runs"), list) else []
    surface_counts: dict[str, int] = {}
    case_count = _int(totals.get("case_count"))
    if _int(totals.get("prefill_pressure_score")) or _int(totals.get("static_prefix_tokens")) or _int(totals.get("shared_static_reuse_tokens")):
        surface_counts["prefill-cache"] = case_count
    concurrency_levels = [_int(item) for item in payload.get("concurrency_levels", []) if _int(item)] if isinstance(payload.get("concurrency_levels"), list) else []
    if any(level > 1 for level in concurrency_levels):
        surface_counts["concurrency"] = case_count
    for run in runs:
        if not isinstance(run, dict):
            continue
        run_surfaces = run.get("surfaces") if isinstance(run.get("surfaces"), dict) else {}
        _map_pressure_surface(surface_counts, run_surfaces, "tools", "tool-calling")
        _map_pressure_surface(surface_counts, run_surfaces, "mcp", "mcp")
        _map_pressure_surface(surface_counts, run_surfaces, "lcp", "lcp")
        _map_pressure_surface(surface_counts, run_surfaces, "skills", "skills")
        _map_pressure_surface(surface_counts, run_surfaces, "structured", "structured-output")
    return {
        "kind": "matrix_pressure_audit",
        "name": _safe_text(payload.get("matrix") or path.name),
        "artifact": _artifact_ref("matrix_pressure_audit", path),
        "case_count": case_count,
        "run_count": _int(payload.get("run_count")),
        "concurrency_levels": concurrency_levels,
        "surface_counts": dict(sorted(surface_counts.items())),
        "pressure": {
            "scheduled_prompt_tokens": _int(totals.get("scheduled_prompt_tokens")),
            "concurrent_window_prompt_tokens": _int(totals.get("concurrent_window_prompt_tokens")),
            "prefill_pressure_score": _int(totals.get("prefill_pressure_score")),
            "concurrency_weighted_pressure_score": _int(totals.get("concurrency_weighted_pressure_score")),
            "shared_static_reuse_tokens": _int(totals.get("shared_static_reuse_tokens")),
        },
    }


def _harness_review_source(payload: dict[str, Any], path: Path) -> dict[str, Any]:
    suite = payload.get("suite") if isinstance(payload.get("suite"), dict) else {}
    counts = payload.get("surface_counts") if isinstance(payload.get("surface_counts"), dict) else {}
    case_count = _int(suite.get("case_count"))
    surface_counts = {
        "tool-calling": _int(counts.get("tool_schema_cases")) + _int(counts.get("expected_tool_cases")) + _int(counts.get("simulated_tool_cases")),
        "tool-loop": _int(counts.get("tool_loop_cases")) + _int(counts.get("multi_tool_catalog_cases")),
        "structured-output": _int(counts.get("structured_output_cases")),
        "cancellation": _int(counts.get("cancellation_cases")),
        "trace-replay": _int(counts.get("message_trace_cases")),
        "mcp": _int(counts.get("mcp_profile_cases")),
        "lcp": _int(counts.get("lcp_profile_cases")),
        "skills": _int(counts.get("skill_cases")),
        "prefill-cache": _int(counts.get("cache_control_cases")),
        "judge-rubric": _int(counts.get("judge_rubric_cases")),
        "harness-engineering": case_count if payload.get("generated") is True else 0,
    }
    surface_counts = {key: value for key, value in sorted(surface_counts.items()) if value}
    return {
        "kind": "harness_review",
        "name": _safe_text(suite.get("name") or path.name),
        "artifact": _artifact_ref("harness_review", path),
        "case_count": case_count,
        "generated": payload.get("generated") is True,
        "review_status": (payload.get("review") if isinstance(payload.get("review"), dict) else {}).get("status"),
        "surface_counts": surface_counts,
    }


def _map_pressure_surface(counts: dict[str, int], run_surfaces: dict[str, Any], source_key: str, target_key: str) -> None:
    value = _int(run_surfaces.get(source_key))
    if value:
        counts[target_key] = counts.get(target_key, 0) + value


def _empty_coverage(required: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for surface, definition in SURFACE_DEFINITIONS.items():
        rows[surface] = {
            "surface": surface,
            "family": definition["family"],
            "purpose": definition["purpose"],
            "required": surface in required,
            "present": False,
            "case_count": 0,
            "run_count": 0,
            "source_count": 0,
            "evidence": [],
        }
    return rows


def _record_surface(coverage: dict[str, dict[str, Any]], surface: str, *, case_count: int, run_count: int, evidence: str) -> None:
    if surface not in coverage:
        return
    row = coverage[surface]
    row["present"] = True
    row["case_count"] += max(0, case_count)
    row["run_count"] += max(0, run_count)
    if evidence and evidence not in row["evidence"]:
        row["evidence"].append(evidence)
        row["source_count"] = len(row["evidence"])


def _recommendations(gaps: list[dict[str, Any]], coverage_rows: list[dict[str, Any]]) -> list[str]:
    if not gaps:
        return [
            "Use this readiness artifact as the pre-dispatch coverage signoff for local and remote agentic benchmark campaigns.",
            "Pair it with matrix pressure audits and protocol-repair posture before publishing corporate or media claims.",
        ]
    missing = {gap["surface"] for gap in gaps}
    recommendations: list[str] = []
    if "concurrency" in missing:
        recommendations.append("Add an agent-fanout or concurrency harness matrix entry with concurrency greater than one.")
    if "prefill-cache" in missing:
        recommendations.append("Add the prefill suite, cache-replay harness, or repeated-prefix skill workloads.")
    if "mcp" in missing or "lcp" in missing or "skills" in missing:
        recommendations.append("Add emerging-workflows harness or representative agent-profile suites that include MCP, LCP, and skill fixtures.")
    if "tool-calling" in missing or "tool-loop" in missing:
        recommendations.append("Add toolcall, toolsim, orchestration, or tool-parser-repair workloads with required API-native tool envelopes.")
    if "structured-output" in missing:
        recommendations.append("Add structured-output or judge-rubric workloads with JSON object/schema validation.")
    if "cancellation" in missing:
        recommendations.append("Add cancellation harness workloads for streaming abort and cancellation-latency evidence.")
    if "harness-engineering" in missing:
        recommendations.append("Generate at least one deterministic harness suite and include its harness-review artifact.")
    return recommendations or ["Add targeted suites or harness reviews for the missing required workflow surfaces."]


def _validate_surfaces(surfaces: tuple[str, ...]) -> None:
    unknown = [surface for surface in surfaces if surface not in SURFACE_DEFINITIONS]
    if unknown:
        available = ", ".join(sorted(SURFACE_DEFINITIONS))
        raise ConfigError(f"unknown required workflow surface(s): {', '.join(unknown)}; available surfaces: {available}")


def _load_json_artifact(path: Path | None, *, expected_schema: str) -> dict[str, Any]:
    if path is None:
        raise ConfigError("missing JSON artifact path")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"cannot read JSON artifact {path.name}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON artifact {path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConfigError(f"JSON artifact {path.name} must contain an object")
    schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema"), payload.get("report_type")) if value}
    if expected_schema not in schema_values:
        raise ConfigError(f"JSON artifact {path.name} must use schema {expected_schema}")
    return payload


def _source_label(source: dict[str, Any]) -> str:
    parts = [str(source.get("kind") or "source"), str(source.get("name") or "unnamed")]
    if source.get("matrix_name"):
        parts.append(f"matrix={source['matrix_name']}")
    if source.get("matrix_run_index"):
        parts.append(f"run={source['matrix_run_index']}")
    return " ".join(parts)


def _artifact_ref(kind: str, path: Path) -> dict[str, str]:
    path = path.expanduser()
    safe_name = path.name if path.is_absolute() or ".." in path.parts else str(path)
    return {"kind": kind, "name": safe_name}


def _safe_name(value: Any) -> str:
    text = _safe_text(value) or "workflow-readiness"
    return text[:160]


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\0", "").strip()[:240]


def _markdown_cell(value: Any) -> str:
    return _safe_text(value).replace("|", "\\|") or "n/a"


def _join_or_none(values: Any) -> str:
    if not isinstance(values, list) or not values:
        return "none"
    return ", ".join(_safe_text(item) for item in values)


def _int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0
