from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentblaster.matrix import MatrixRun, load_matrix_file
from agentblaster.models import RawTraceMode
from agentblaster.prompt_footprint import suite_prompt_footprint
from agentblaster.suites import get_builtin_suite, load_suite_file


MATRIX_PRESSURE_SCHEMA_VERSION = "agentblaster.matrix-pressure-audit.v1"


def audit_matrix_pressure(matrix_path: Path) -> dict[str, Any]:
    """Build a no-dispatch prompt/prefill pressure audit for a matrix."""

    matrix = load_matrix_file(matrix_path)
    runs = [_run_pressure(index, run) for index, run in enumerate(matrix.runs, start=1)]
    return {
        "schema_version": MATRIX_PRESSURE_SCHEMA_VERSION,
        "matrix": matrix.name,
        "matrix_path": str(matrix_path),
        "description": matrix.description,
        "run_count": len(runs),
        "engines": sorted({run["engine"] for run in runs}),
        "models": sorted({run["model"] for run in runs if run["model"]}),
        "suites": sorted({run["suite"] for run in runs}),
        "concurrency_levels": sorted({run["concurrency"] for run in runs}),
        "totals": {
            "case_count": sum(run["case_count"] for run in runs),
            "scheduled_prompt_tokens": sum(run["scheduled_prompt_tokens"] for run in runs),
            "concurrent_window_prompt_tokens": sum(run["concurrent_window_prompt_tokens"] for run in runs),
            "static_prefix_tokens": sum(run["static_prefix_tokens"] for run in runs),
            "dynamic_prompt_tokens": sum(run["dynamic_prompt_tokens"] for run in runs),
            "output_token_budget": sum(run["output_token_budget"] for run in runs),
            "prefill_pressure_score": sum(run["prefill_pressure_score"] for run in runs),
            "concurrency_weighted_pressure_score": sum(run["concurrency_weighted_pressure_score"] for run in runs),
            "shared_static_prefix_groups": sum(run["shared_static_prefix_groups"] for run in runs),
            "shared_static_prefix_tokens": sum(run["shared_static_prefix_tokens"] for run in runs),
            "shared_static_reuse_tokens": sum(run["shared_static_reuse_tokens"] for run in runs),
        },
        "by_engine": _group_totals(runs, "engine"),
        "by_suite": _group_totals(runs, "suite"),
        "by_model": _group_totals(runs, "model"),
        "highest_pressure_runs": sorted(
            runs,
            key=lambda item: item["concurrency_weighted_pressure_score"],
            reverse=True,
        )[:10],
        "runs": runs,
        "notes": [
            "Pressure audit is static and does not contact providers, resolve secrets, or run benchmark cases.",
            "Token estimates use the same deterministic character-count heuristic as suite-footprint.",
            "Concurrent window prompt tokens estimate the largest prompt-token cases likely to be in flight together for a run.",
            "Concurrency-weighted pressure is a planning signal for local engine queueing, prefill, and cache behavior; it is not a runtime measurement.",
        ],
    }


def write_matrix_pressure_json(report: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def format_matrix_pressure_report(report: dict[str, Any]) -> str:
    totals = report["totals"]
    lines = [
        "AgentBlaster matrix pressure audit",
        f"matrix: {report['matrix']}",
        f"run_count: {report['run_count']}",
        f"case_count: {totals['case_count']}",
        f"scheduled_prompt_tokens: {totals['scheduled_prompt_tokens']}",
        f"concurrent_window_prompt_tokens: {totals['concurrent_window_prompt_tokens']}",
        f"static_prefix_tokens: {totals['static_prefix_tokens']}",
        f"dynamic_prompt_tokens: {totals['dynamic_prompt_tokens']}",
        f"prefill_pressure_score: {totals['prefill_pressure_score']}",
        f"concurrency_weighted_pressure_score: {totals['concurrency_weighted_pressure_score']}",
        f"shared_static_prefix_groups: {totals['shared_static_prefix_groups']}",
        f"shared_static_reuse_tokens: {totals['shared_static_reuse_tokens']}",
        "by_engine:",
    ]
    for engine, values in report["by_engine"].items():
        lines.append(
            f"- {engine}: runs={values['run_count']} cases={values['case_count']} "
            f"weighted_pressure={values['concurrency_weighted_pressure_score']}"
        )
    lines.append("highest_pressure_runs:")
    for run in report["highest_pressure_runs"]:
        lines.append(
            f"- #{run['index']} {run['engine']} {run['suite']} concurrency={run['concurrency']} "
            f"weighted_pressure={run['concurrency_weighted_pressure_score']} "
            f"window_tokens={run['concurrent_window_prompt_tokens']}"
        )
    return "\n".join(lines) + "\n"


def _run_pressure(index: int, run: MatrixRun) -> dict[str, Any]:
    suite = load_suite_file(run.suite_file) if run.suite_file is not None else get_builtin_suite(run.suite)
    footprint = suite_prompt_footprint(suite)
    cases = footprint["cases"]
    concurrency = max(1, run.concurrency)
    window_size = min(concurrency, len(cases))
    largest_cases = sorted(cases, key=lambda item: item["estimated_prompt_tokens"], reverse=True)
    window_cases = largest_cases[:window_size]
    static_prefix_tokens = sum(case["static_prefix_tokens"] for case in cases)
    dynamic_prompt_tokens = sum(case["dynamic_prompt_tokens"] for case in cases)
    output_token_budget = sum(case["max_tokens"] for case in cases)
    shared_static_prefix_tokens = sum(
        item["static_tokens"] * item["case_count"]
        for item in footprint["shared_static_prefixes"]
    )
    shared_static_reuse = footprint.get("shared_static_reuse", {})
    prefill_pressure_score = int(footprint["prefill_pressure"]["score"])
    trace_mode = RawTraceMode.OFF.value if run.no_raw_traces else run.raw_traces.value
    return {
        "index": index,
        "engine": run.engine,
        "model": run.model,
        "suite": suite.name,
        "suite_file": str(run.suite_file) if run.suite_file is not None else None,
        "concurrency": concurrency,
        "raw_trace_mode": trace_mode,
        "case_count": len(cases),
        "scheduled_prompt_tokens": int(footprint["total_estimated_prompt_tokens"]),
        "concurrent_window_size": window_size,
        "concurrent_window_prompt_tokens": sum(case["estimated_prompt_tokens"] for case in window_cases),
        "max_case_estimated_prompt_tokens": int(footprint["max_case_estimated_prompt_tokens"]),
        "static_prefix_tokens": static_prefix_tokens,
        "dynamic_prompt_tokens": dynamic_prompt_tokens,
        "output_token_budget": output_token_budget,
        "shared_static_prefix_groups": len(footprint["shared_static_prefixes"]),
        "shared_static_prefix_tokens": shared_static_prefix_tokens,
        "shared_static_reuse_tokens": int(shared_static_reuse.get("potential_cache_reuse_tokens") or 0),
        "prefill_pressure_score": prefill_pressure_score,
        "prefill_pressure_level": footprint["prefill_pressure"]["level"],
        "concurrency_weighted_pressure_score": prefill_pressure_score * concurrency,
        "surfaces": _surface_counts(cases),
        "largest_cases": [
            {
                "case_id": case["case_id"],
                "estimated_prompt_tokens": case["estimated_prompt_tokens"],
                "static_prefix_tokens": case["static_prefix_tokens"],
                "dynamic_prompt_tokens": case["dynamic_prompt_tokens"],
                "surfaces": case["surfaces"],
            }
            for case in largest_cases[:5]
        ],
    }


def _surface_counts(cases: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in cases:
        for surface in case["surfaces"]:
            counts[surface] = counts.get(surface, 0) + 1
    return dict(sorted(counts.items()))


def _group_totals(runs: list[dict[str, Any]], key: str) -> dict[str, dict[str, int]]:
    grouped: dict[str, dict[str, int]] = {}
    for run in runs:
        group = str(run.get(key) or "unspecified")
        values = grouped.setdefault(
            group,
            {
                "run_count": 0,
                "case_count": 0,
                "scheduled_prompt_tokens": 0,
                "concurrent_window_prompt_tokens": 0,
                "static_prefix_tokens": 0,
                "dynamic_prompt_tokens": 0,
                "output_token_budget": 0,
                "prefill_pressure_score": 0,
                "concurrency_weighted_pressure_score": 0,
                "shared_static_prefix_groups": 0,
                "shared_static_prefix_tokens": 0,
                "shared_static_reuse_tokens": 0,
            },
        )
        values["run_count"] += 1
        for field in values:
            if field != "run_count":
                values[field] += int(run[field])
    return dict(sorted(grouped.items()))
