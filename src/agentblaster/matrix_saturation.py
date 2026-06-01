from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from agentblaster.errors import ConfigError
from agentblaster.matrix import MatrixExecutionSummary
from agentblaster.models import BenchmarkResult
from agentblaster.reports import load_matrix_execution_summary, load_results


MATRIX_SATURATION_SCHEMA_VERSION = "agentblaster.matrix-saturation.v1"


def build_matrix_saturation_report(
    summary_json: Path,
    *,
    max_latency_regression_pct: float = 50.0,
    max_decode_drop_pct: float = 25.0,
    max_pass_rate_drop_pct: float = 5.0,
    queue_warning_ms: float = 50.0,
) -> dict[str, Any]:
    """Build an executed-result saturation report from a matrix summary."""

    summary = load_matrix_execution_summary(summary_json)
    base_dir = summary_json.parent
    entries = [_matrix_saturation_entry(run, base_dir=base_dir) for run in summary.runs]
    groups = _saturation_groups(entries)
    findings = _saturation_findings(
        entries,
        groups,
        max_latency_regression_pct=max_latency_regression_pct,
        max_decode_drop_pct=max_decode_drop_pct,
        max_pass_rate_drop_pct=max_pass_rate_drop_pct,
        queue_warning_ms=queue_warning_ms,
    )
    result_artifacts_loaded = sum(1 for entry in entries if entry["result_artifacts_loaded"])
    error_findings = sum(1 for finding in findings if finding["severity"] == "error")
    warning_findings = sum(1 for finding in findings if finding["severity"] == "warning")
    return {
        "schema_version": MATRIX_SATURATION_SCHEMA_VERSION,
        "ok": error_findings == 0,
        "matrix": {
            "name": summary.matrix_name,
            "path": summary.matrix_path,
            "summary_json": str(summary_json),
            "description": summary.description,
            "created_at": summary.created_at,
            "dry_run": summary.dry_run,
            "total_runs": summary.total_runs,
            "attempted_runs": summary.attempted_runs,
            "completed_runs": summary.completed_runs,
            "failed_runs": summary.failed_runs,
        },
        "thresholds": {
            "max_latency_regression_pct": max_latency_regression_pct,
            "max_decode_drop_pct": max_decode_drop_pct,
            "max_pass_rate_drop_pct": max_pass_rate_drop_pct,
            "queue_warning_ms": queue_warning_ms,
        },
        "summary": {
            "entry_count": len(entries),
            "group_count": len(groups),
            "result_artifacts_loaded": result_artifacts_loaded,
            "result_artifacts_missing": len(entries) - result_artifacts_loaded,
            "total_cases": sum(entry["total_cases"] for entry in entries),
            "passed_cases": sum(entry["passed"] for entry in entries),
            "failed_cases": sum(entry["failed"] for entry in entries),
            "max_concurrency": max((entry["concurrency"] for entry in entries), default=0),
            "finding_count": len(findings),
            "error_findings": error_findings,
            "warning_findings": warning_findings,
        },
        "concurrency_evidence": _concurrency_evidence(entries, groups, findings),
        "groups": groups,
        "entries": entries,
        "findings": findings,
        "security": {
            "contains_raw_secrets": False,
            "contains_raw_provider_payloads": False,
            "notes": (
                "Saturation reports are derived from matrix execution summaries and normalized result rows. "
                "They exclude raw provider responses, raw traces, API keys, and request headers."
            ),
        },
    }


def write_matrix_saturation_json(report: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def format_matrix_saturation_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "AgentBlaster matrix saturation report",
        f"matrix: {report['matrix']['name']}",
        f"ok: {str(report['ok']).lower()}",
        f"runs: {report['matrix']['completed_runs']}/{report['matrix']['total_runs']} completed",
        f"result_artifacts_loaded: {summary['result_artifacts_loaded']}/{summary['entry_count']}",
        f"groups: {summary['group_count']}",
        f"max_concurrency: {summary['max_concurrency']}",
        f"concurrency_evidence: {report.get('concurrency_evidence', {}).get('guidance', 'unknown')}",
        f"findings: {summary['finding_count']}",
        "saturation_groups:",
    ]
    for group in report["groups"]:
        lines.append(
            f"- {group['group_id']}: levels={group['concurrency_levels']} "
            f"best_latency_ms={_format_metric(group['best_avg_latency_ms'])} "
            f"best_decode_tps={_format_metric(group['best_avg_decode_tokens_per_second'])}"
        )
        for row in group["series"]:
            lines.append(
                f"  c={row['concurrency']} pass={_format_metric(row['pass_rate_percent'])}% "
                f"latency={_format_metric(row['avg_latency_ms'])}ms "
                f"ttft={_format_metric(row['avg_ttft_ms'])}ms "
                f"queue={_format_metric(row['avg_queue_ms'])}ms "
                f"decode={_format_metric(row['avg_decode_tokens_per_second'])} tok/s "
                f"artifacts={row['result_artifacts_loaded']}/{row['entry_count']}"
            )
    if report["findings"]:
        lines.append("findings:")
        for finding in report["findings"]:
            lines.append(
                f"- {finding['severity']} {finding['category']} {finding['group_id']} "
                f"c={finding.get('concurrency', '-')}: {finding['message']}"
            )
    return "\n".join(lines) + "\n"


def _matrix_saturation_entry(run, *, base_dir: Path) -> dict[str, Any]:
    results = _load_run_results(run, base_dir=base_dir)
    metrics = _aggregate_results(results) if results else _summary_only_metrics(run)
    return {
        "index": run.index,
        "engine": run.engine,
        "provider": run.provider,
        "model": run.model,
        "suite": run.suite,
        "group_id": _group_id(run.engine, run.provider, run.model, run.suite),
        "run_id": run.run_id,
        "ok": run.ok,
        "concurrency": run.concurrency,
        "total_cases": metrics["total_cases"],
        "passed": metrics["passed"],
        "failed": metrics["failed"],
        "pass_rate_percent": metrics["pass_rate_percent"],
        "avg_queue_ms": metrics["avg_queue_ms"],
        "avg_rate_limit_wait_ms": metrics["avg_rate_limit_wait_ms"],
        "avg_latency_ms": metrics["avg_latency_ms"],
        "p95_latency_ms": metrics["p95_latency_ms"],
        "avg_ttft_ms": metrics["avg_ttft_ms"],
        "avg_prefill_tokens_per_second": metrics["avg_prefill_tokens_per_second"],
        "avg_decode_tokens_per_second": metrics["avg_decode_tokens_per_second"],
        "avg_cache_hit_ratio": metrics["avg_cache_hit_ratio"],
        "cancellation_cases": metrics["cancellation_cases"],
        "cancellations_observed": metrics["cancellations_observed"],
        "result_artifacts_loaded": bool(results),
        "results_path": run.results_path,
        "manifest_path": run.manifest_path,
        "summary_path": run.summary_path,
        "error_type": run.error_type,
        "error_message": run.error_message,
    }


def _load_run_results(run, *, base_dir: Path) -> list[BenchmarkResult]:
    run_dir = _run_dir_from_artifacts(run, base_dir=base_dir)
    if run_dir is None or not run_dir.exists():
        return []
    try:
        return load_results(run_dir)
    except ConfigError:
        return []


def _run_dir_from_artifacts(run, *, base_dir: Path) -> Path | None:
    for artifact in (run.results_path, run.summary_path, run.manifest_path):
        if not artifact:
            continue
        path = Path(artifact)
        resolved = path if path.is_absolute() else base_dir / path
        if resolved.name in {"results.jsonl", "summary.json", "manifest.json"}:
            return resolved.parent
    return None


def _aggregate_results(results: list[BenchmarkResult]) -> dict[str, Any]:
    latency_values = _values(results, "latency_ms")
    cancellation_cases = [result for result in results if result.cancel_after_ms is not None]
    cancellations_observed = [result for result in cancellation_cases if result.canceled]
    return {
        "total_cases": len(results),
        "passed": sum(1 for result in results if result.ok),
        "failed": sum(1 for result in results if not result.ok),
        "pass_rate_percent": _percent(sum(1 for result in results if result.ok), len(results)),
        "avg_queue_ms": _avg(_values(results, "queue_ms")),
        "avg_rate_limit_wait_ms": _avg(_values(results, "rate_limit_wait_ms")),
        "avg_latency_ms": _avg(latency_values),
        "p95_latency_ms": _p95(latency_values),
        "avg_ttft_ms": _avg(_values(results, "ttft_ms")),
        "avg_prefill_tokens_per_second": _avg(_values(results, "tokens_per_second_prefill")),
        "avg_decode_tokens_per_second": _avg(_values(results, "tokens_per_second_decode")),
        "avg_cache_hit_ratio": _avg(_values(results, "cache_hit_ratio")),
        "cancellation_cases": len(cancellation_cases),
        "cancellations_observed": len(cancellations_observed),
    }


def _summary_only_metrics(run) -> dict[str, Any]:
    return {
        "total_cases": run.total_cases,
        "passed": run.passed,
        "failed": run.failed,
        "pass_rate_percent": _percent(run.passed, run.total_cases),
        "avg_queue_ms": None,
        "avg_rate_limit_wait_ms": None,
        "avg_latency_ms": None,
        "p95_latency_ms": None,
        "avg_ttft_ms": None,
        "avg_prefill_tokens_per_second": None,
        "avg_decode_tokens_per_second": None,
        "avg_cache_hit_ratio": None,
        "cancellation_cases": None,
        "cancellations_observed": None,
    }


def _saturation_groups(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        grouped.setdefault(entry["group_id"], []).append(entry)

    groups: list[dict[str, Any]] = []
    for group_id, group_entries in sorted(grouped.items()):
        by_concurrency: dict[int, list[dict[str, Any]]] = {}
        for entry in group_entries:
            by_concurrency.setdefault(entry["concurrency"], []).append(entry)
        series = [
            _concurrency_row(concurrency, rows)
            for concurrency, rows in sorted(by_concurrency.items())
        ]
        groups.append(
            {
                "group_id": group_id,
                "engine": group_entries[0]["engine"],
                "provider": group_entries[0]["provider"],
                "model": group_entries[0]["model"],
                "suite": group_entries[0]["suite"],
                "entry_count": len(group_entries),
                "concurrency_levels": [row["concurrency"] for row in series],
                "result_artifacts_loaded": sum(row["result_artifacts_loaded"] for row in series),
                "best_avg_latency_ms": _min_present(row["avg_latency_ms"] for row in series),
                "best_avg_decode_tokens_per_second": _max_present(
                    row["avg_decode_tokens_per_second"] for row in series
                ),
                "series": series,
            }
        )
    return groups


def _concurrency_evidence(
    entries: list[dict[str, Any]],
    groups: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    multi_level_groups = [group for group in groups if len(group["concurrency_levels"]) > 1]
    queue_findings = [finding for finding in findings if finding.get("category") == "queue_wait"]
    rate_limit_findings = [finding for finding in findings if finding.get("category") == "rate_limit_wait"]
    result_artifacts_loaded = sum(1 for entry in entries if entry["result_artifacts_loaded"])
    if not multi_level_groups:
        guidance = "insufficient-concurrency-levels-for-saturation-claim"
    elif queue_findings or rate_limit_findings:
        guidance = "review-scheduler-queueing-and-provider-pacing-before-publication"
    else:
        guidance = "concurrency-evidence-ready-when-release-gates-pass"
    return {
        "schema_version": "agentblaster.concurrency-evidence.v1",
        "group_count": len(groups),
        "multi_level_group_count": len(multi_level_groups),
        "concurrency_levels": sorted({entry["concurrency"] for entry in entries}),
        "max_concurrency": max((entry["concurrency"] for entry in entries), default=0),
        "result_artifacts_loaded": result_artifacts_loaded,
        "result_artifacts_missing": len(entries) - result_artifacts_loaded,
        "max_avg_queue_ms": _max_metric(entries, "avg_queue_ms"),
        "max_avg_rate_limit_wait_ms": _max_metric(entries, "avg_rate_limit_wait_ms"),
        "queue_wait_finding_count": len(queue_findings),
        "rate_limit_wait_finding_count": len(rate_limit_findings),
        "highest_queue_wait_entries": _top_entries(entries, "avg_queue_ms"),
        "highest_rate_limit_wait_entries": _top_entries(entries, "avg_rate_limit_wait_ms"),
        "guidance": guidance,
    }


def _concurrency_row(concurrency: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_cases = sum(row["total_cases"] for row in rows)
    passed = sum(row["passed"] for row in rows)
    failed = sum(row["failed"] for row in rows)
    return {
        "concurrency": concurrency,
        "entry_count": len(rows),
        "result_artifacts_loaded": sum(1 for row in rows if row["result_artifacts_loaded"]),
        "total_cases": total_cases,
        "passed": passed,
        "failed": failed,
        "pass_rate_percent": _percent(passed, total_cases),
        "avg_queue_ms": _weighted_metric(rows, "avg_queue_ms"),
        "avg_rate_limit_wait_ms": _weighted_metric(rows, "avg_rate_limit_wait_ms"),
        "avg_latency_ms": _weighted_metric(rows, "avg_latency_ms"),
        "p95_latency_ms": _max_present(row["p95_latency_ms"] for row in rows),
        "avg_ttft_ms": _weighted_metric(rows, "avg_ttft_ms"),
        "avg_prefill_tokens_per_second": _weighted_metric(rows, "avg_prefill_tokens_per_second"),
        "avg_decode_tokens_per_second": _weighted_metric(rows, "avg_decode_tokens_per_second"),
        "avg_cache_hit_ratio": _weighted_metric(rows, "avg_cache_hit_ratio"),
        "cancellation_cases": _sum_optional(rows, "cancellation_cases"),
        "cancellations_observed": _sum_optional(rows, "cancellations_observed"),
        "runs": [
            {
                "index": row["index"],
                "run_id": row["run_id"],
                "ok": row["ok"],
                "result_artifacts_loaded": row["result_artifacts_loaded"],
            }
            for row in rows
        ],
    }


def _max_metric(entries: list[dict[str, Any]], metric: str) -> float | None:
    values = [float(entry[metric]) for entry in entries if entry.get(metric) is not None]
    if not values:
        return None
    return round(max(values), 6)


def _top_entries(entries: list[dict[str, Any]], metric: str, *, limit: int = 5) -> list[dict[str, Any]]:
    ranked = sorted(
        (entry for entry in entries if entry.get(metric) is not None),
        key=lambda entry: float(entry[metric]),
        reverse=True,
    )
    return [
        {
            "group_id": entry["group_id"],
            "run_id": entry["run_id"],
            "engine": entry["engine"],
            "provider": entry["provider"],
            "model": entry["model"],
            "suite": entry["suite"],
            "concurrency": entry["concurrency"],
            "rank_metric": metric,
            "rank_value": entry[metric],
            "avg_queue_ms": entry["avg_queue_ms"],
            "avg_rate_limit_wait_ms": entry["avg_rate_limit_wait_ms"],
            "avg_latency_ms": entry["avg_latency_ms"],
            "pass_rate_percent": entry["pass_rate_percent"],
        }
        for entry in ranked[:limit]
    ]


def _saturation_findings(
    entries: list[dict[str, Any]],
    groups: list[dict[str, Any]],
    *,
    max_latency_regression_pct: float,
    max_decode_drop_pct: float,
    max_pass_rate_drop_pct: float,
    queue_warning_ms: float,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for entry in entries:
        if not entry["ok"]:
            findings.append(
                {
                    "severity": "error",
                    "category": "run_failure",
                    "group_id": entry["group_id"],
                    "concurrency": entry["concurrency"],
                    "run_id": entry["run_id"],
                    "message": entry["error_message"] or "matrix run did not complete successfully",
                }
            )
        if entry["ok"] and not entry["result_artifacts_loaded"]:
            findings.append(
                {
                    "severity": "warning",
                    "category": "missing_result_artifacts",
                    "group_id": entry["group_id"],
                    "concurrency": entry["concurrency"],
                    "run_id": entry["run_id"],
                    "message": "completed run has no normalized result artifacts available for saturation metrics",
                }
            )

    for group in groups:
        series = group["series"]
        if len(series) < 2:
            continue
        baseline = series[0]
        for row in series[1:]:
            _append_regression_findings(
                findings,
                group_id=group["group_id"],
                baseline=baseline,
                row=row,
                max_latency_regression_pct=max_latency_regression_pct,
                max_decode_drop_pct=max_decode_drop_pct,
                max_pass_rate_drop_pct=max_pass_rate_drop_pct,
                queue_warning_ms=queue_warning_ms,
            )
    return findings


def _append_regression_findings(
    findings: list[dict[str, Any]],
    *,
    group_id: str,
    baseline: dict[str, Any],
    row: dict[str, Any],
    max_latency_regression_pct: float,
    max_decode_drop_pct: float,
    max_pass_rate_drop_pct: float,
    queue_warning_ms: float,
) -> None:
    pass_drop = _drop_percent(baseline["pass_rate_percent"], row["pass_rate_percent"])
    if pass_drop is not None and pass_drop > max_pass_rate_drop_pct:
        findings.append(
            {
                "severity": "error",
                "category": "pass_rate_drop",
                "group_id": group_id,
                "baseline_concurrency": baseline["concurrency"],
                "concurrency": row["concurrency"],
                "actual": pass_drop,
                "threshold": max_pass_rate_drop_pct,
                "message": (
                    f"pass rate dropped {pass_drop:.3f}% from concurrency "
                    f"{baseline['concurrency']} to {row['concurrency']}"
                ),
            }
        )

    latency_regression = _increase_percent(baseline["avg_latency_ms"], row["avg_latency_ms"])
    if latency_regression is not None and latency_regression > max_latency_regression_pct:
        findings.append(
            {
                "severity": "warning",
                "category": "latency_regression",
                "group_id": group_id,
                "baseline_concurrency": baseline["concurrency"],
                "concurrency": row["concurrency"],
                "actual": latency_regression,
                "threshold": max_latency_regression_pct,
                "message": (
                    f"average latency increased {latency_regression:.3f}% from concurrency "
                    f"{baseline['concurrency']} to {row['concurrency']}"
                ),
            }
        )

    p95_regression = _increase_percent(baseline["p95_latency_ms"], row["p95_latency_ms"])
    if p95_regression is not None and p95_regression > max_latency_regression_pct:
        findings.append(
            {
                "severity": "warning",
                "category": "p95_latency_regression",
                "group_id": group_id,
                "baseline_concurrency": baseline["concurrency"],
                "concurrency": row["concurrency"],
                "actual": p95_regression,
                "threshold": max_latency_regression_pct,
                "message": (
                    f"p95 latency increased {p95_regression:.3f}% from concurrency "
                    f"{baseline['concurrency']} to {row['concurrency']}"
                ),
            }
        )

    decode_drop = _drop_percent(baseline["avg_decode_tokens_per_second"], row["avg_decode_tokens_per_second"])
    if decode_drop is not None and decode_drop > max_decode_drop_pct:
        findings.append(
            {
                "severity": "warning",
                "category": "decode_throughput_drop",
                "group_id": group_id,
                "baseline_concurrency": baseline["concurrency"],
                "concurrency": row["concurrency"],
                "actual": decode_drop,
                "threshold": max_decode_drop_pct,
                "message": (
                    f"decode throughput dropped {decode_drop:.3f}% from concurrency "
                    f"{baseline['concurrency']} to {row['concurrency']}"
                ),
            }
        )

    for metric, category in (
        ("avg_queue_ms", "queue_wait"),
        ("avg_rate_limit_wait_ms", "rate_limit_wait"),
    ):
        value = row[metric]
        if value is not None and value >= queue_warning_ms:
            findings.append(
                {
                    "severity": "warning",
                    "category": category,
                    "group_id": group_id,
                    "concurrency": row["concurrency"],
                    "actual": value,
                    "threshold": queue_warning_ms,
                    "message": f"{metric} reached {value:.3f} ms at concurrency {row['concurrency']}",
                }
            )


def _group_id(engine: str, provider: str, model: str, suite: str) -> str:
    return f"{engine}/{provider}/{model}/{suite}"


def _values(results: list[BenchmarkResult], field: str) -> list[float]:
    values: list[float] = []
    for result in results:
        value = getattr(result, field)
        if value is not None:
            values.append(float(value))
    return values


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 6) if values else None


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return round(ordered[index], 6)


def _percent(numerator: float | int, denominator: float | int) -> float | None:
    if not denominator:
        return None
    return round((float(numerator) / float(denominator)) * 100.0, 6)


def _weighted_metric(rows: list[dict[str, Any]], field: str) -> float | None:
    weighted_total = 0.0
    weight_total = 0
    for row in rows:
        value = row[field]
        if value is None:
            continue
        weight = max(1, int(row["total_cases"]))
        weighted_total += float(value) * weight
        weight_total += weight
    if not weight_total:
        return None
    return round(weighted_total / weight_total, 6)


def _sum_optional(rows: list[dict[str, Any]], field: str) -> int | None:
    values = [row[field] for row in rows if row[field] is not None]
    return sum(values) if values else None


def _min_present(values) -> float | None:
    present = [value for value in values if value is not None]
    return min(present) if present else None


def _max_present(values) -> float | None:
    present = [value for value in values if value is not None]
    return max(present) if present else None


def _increase_percent(baseline: float | None, current: float | None) -> float | None:
    if baseline is None or current is None or baseline <= 0:
        return None
    return round(((current - baseline) / baseline) * 100.0, 6)


def _drop_percent(baseline: float | None, current: float | None) -> float | None:
    if baseline is None or current is None or baseline <= 0:
        return None
    return round(((baseline - current) / baseline) * 100.0, 6)


def _format_metric(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)
