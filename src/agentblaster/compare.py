from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from agentblaster.reports import load_manifest, load_results

COMPARISON_SCHEMA_VERSION = "agentblaster.comparison.v1"


class RunComparisonRow(BaseModel):
    run_id: str
    suite: str
    provider: str
    model: str
    total_cases: int
    passed: int
    failed: int
    pass_rate: float
    avg_latency_ms: float | None = None
    p50_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    p99_latency_ms: float | None = None
    avg_queue_ms: float | None = None
    avg_rate_limit_wait_ms: float | None = None
    avg_ttft_ms: float | None = None
    avg_cache_hit_ratio: float | None = None
    avg_prefill_tokens_per_second: float | None = None
    avg_decode_tokens_per_second: float | None = None
    total_cost_usd: float | None = None
    scenario_summary: list["ScenarioComparisonRow"] = Field(default_factory=list)


class ScenarioComparisonRow(BaseModel):
    scenario: str
    total_cases: int
    passed: int
    failed: int
    pass_rate: float
    avg_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    avg_queue_ms: float | None = None
    avg_ttft_ms: float | None = None
    avg_cache_hit_ratio: float | None = None
    avg_decode_tokens_per_second: float | None = None


def compare_runs(run_dirs: list[Path]) -> list[RunComparisonRow]:
    rows: list[RunComparisonRow] = []
    for run_dir in run_dirs:
        manifest = load_manifest(run_dir)
        results = load_results(run_dir)
        latencies = [result.latency_ms for result in results if result.latency_ms is not None]
        queues = [result.queue_ms for result in results if result.queue_ms is not None]
        rate_limit_waits = [
            result.rate_limit_wait_ms for result in results if result.rate_limit_wait_ms is not None
        ]
        ttfts = [result.ttft_ms for result in results if result.ttft_ms is not None]
        cache_hit_ratios = [result.cache_hit_ratio for result in results if result.cache_hit_ratio is not None]
        prefill_rates = [
            result.tokens_per_second_prefill
            for result in results
            if result.tokens_per_second_prefill is not None
        ]
        decode_rates = [
            result.tokens_per_second_decode
            for result in results
            if result.tokens_per_second_decode is not None
        ]
        costs = [result.total_cost_usd for result in results if result.total_cost_usd is not None]
        passed = sum(1 for result in results if result.ok)
        failed = sum(1 for result in results if not result.ok)
        rows.append(
            RunComparisonRow(
                run_id=manifest.run_id,
                suite=manifest.suite,
                provider=manifest.provider,
                model=manifest.model,
                total_cases=len(results),
                passed=passed,
                failed=failed,
                pass_rate=round((passed / len(results)) * 100, 3) if results else 0.0,
                avg_latency_ms=_average(latencies),
                p50_latency_ms=_percentile(latencies, 50),
                p95_latency_ms=_percentile(latencies, 95),
                p99_latency_ms=_percentile(latencies, 99),
                avg_queue_ms=_average(queues),
                avg_rate_limit_wait_ms=_average(rate_limit_waits),
                avg_ttft_ms=_average(ttfts),
                avg_cache_hit_ratio=_average(cache_hit_ratios),
                avg_prefill_tokens_per_second=_average(prefill_rates),
                avg_decode_tokens_per_second=_average(decode_rates),
                total_cost_usd=round(sum(costs), 9) if costs else None,
                scenario_summary=_scenario_summary(results),
            )
        )
    return rows


def write_comparison_json(run_dirs: list[Path], output_path: Path) -> Path:
    rows = compare_runs(run_dirs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "schema_version": COMPARISON_SCHEMA_VERSION,
                "run_count": len(rows),
                "rows": [row.model_dump(mode="json") for row in rows],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return output_path


def format_comparison_table(rows: list[RunComparisonRow]) -> str:
    headers = [
        "run_id",
        "provider",
        "suite",
        "passed",
        "failed",
        "pass_rate",
        "avg_latency_ms",
        "p95_latency_ms",
        "avg_queue_ms",
        "avg_rate_limit_wait_ms",
        "avg_ttft_ms",
        "avg_cache_hit_ratio",
        "avg_prefill_tok_s",
        "avg_decode_tok_s",
        "total_cost_usd",
    ]
    lines = ["\t".join(headers)]
    for row in rows:
        lines.append(
            "\t".join(
                [
                    row.run_id,
                    row.provider,
                    row.suite,
                    str(row.passed),
                    str(row.failed),
                    _format_float(row.pass_rate),
                    _format_float(row.avg_latency_ms),
                    _format_float(row.p95_latency_ms),
                    _format_float(row.avg_queue_ms),
                    _format_float(row.avg_rate_limit_wait_ms),
                    _format_float(row.avg_ttft_ms),
                    _format_float(row.avg_cache_hit_ratio),
                    _format_float(row.avg_prefill_tokens_per_second),
                    _format_float(row.avg_decode_tokens_per_second),
                    _format_float(row.total_cost_usd),
                ]
            )
        )
    scenario_lines = [
        "",
        "\t".join(
            [
                "run_id",
                "provider",
                "scenario",
                "passed",
                "failed",
                "pass_rate",
                "avg_latency_ms",
                "p95_latency_ms",
                "avg_queue_ms",
                "avg_ttft_ms",
                "avg_cache_hit_ratio",
                "avg_decode_tok_s",
            ]
        ),
    ]
    for row in rows:
        for scenario in row.scenario_summary:
            scenario_lines.append(
                "\t".join(
                    [
                        row.run_id,
                        row.provider,
                        scenario.scenario,
                        str(scenario.passed),
                        str(scenario.failed),
                        _format_float(scenario.pass_rate),
                        _format_float(scenario.avg_latency_ms),
                        _format_float(scenario.p95_latency_ms),
                        _format_float(scenario.avg_queue_ms),
                        _format_float(scenario.avg_ttft_ms),
                        _format_float(scenario.avg_cache_hit_ratio),
                        _format_float(scenario.avg_decode_tokens_per_second),
                    ]
                )
            )
    return "\n".join([*lines, *scenario_lines])


def _scenario_summary(results) -> list[ScenarioComparisonRow]:
    buckets = {}
    for result in results:
        buckets.setdefault(result.scenario or "unspecified", []).append(result)
    rows: list[ScenarioComparisonRow] = []
    for scenario, scenario_results in sorted(buckets.items()):
        latencies = [result.latency_ms for result in scenario_results if result.latency_ms is not None]
        queues = [result.queue_ms for result in scenario_results if result.queue_ms is not None]
        ttfts = [result.ttft_ms for result in scenario_results if result.ttft_ms is not None]
        cache_hit_ratios = [
            result.cache_hit_ratio for result in scenario_results if result.cache_hit_ratio is not None
        ]
        decode_rates = [
            result.tokens_per_second_decode
            for result in scenario_results
            if result.tokens_per_second_decode is not None
        ]
        passed = sum(1 for result in scenario_results if result.ok)
        failed = sum(1 for result in scenario_results if not result.ok)
        rows.append(
            ScenarioComparisonRow(
                scenario=scenario,
                total_cases=len(scenario_results),
                passed=passed,
                failed=failed,
                pass_rate=round((passed / len(scenario_results)) * 100, 3) if scenario_results else 0.0,
                avg_latency_ms=_average(latencies),
                p95_latency_ms=_percentile(latencies, 95),
                avg_queue_ms=_average(queues),
                avg_ttft_ms=_average(ttfts),
                avg_cache_hit_ratio=_average(cache_hit_ratios),
                avg_decode_tokens_per_second=_average(decode_rates),
            )
        )
    return rows


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def _percentile(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return round(sorted_values[0], 3)
    index = round((percentile / 100) * (len(sorted_values) - 1))
    return round(sorted_values[index], 3)


def _format_float(value: float | None) -> str:
    return "" if value is None else str(value)


class ComparisonGateFinding(BaseModel):
    """Machine-readable release/regression gate finding."""

    metric: str
    baseline: float | None = None
    candidate: float | None = None
    threshold: float
    message: str


class ComparisonGateReport(BaseModel):
    """Machine-readable pass/fail report for a baseline-vs-candidate comparison gate."""

    schema_version: str = "agentblaster.comparison-gate.v1"
    baseline: RunComparisonRow
    candidate: RunComparisonRow
    ok: bool
    thresholds: dict[str, float] = Field(default_factory=dict)
    findings: list[ComparisonGateFinding] = Field(default_factory=list)


def evaluate_comparison_gate(
    baseline_dir: Path,
    candidate_dir: Path,
    *,
    min_pass_rate: float | None = None,
    max_pass_rate_drop: float | None = None,
    max_avg_latency_regression_pct: float | None = None,
    max_p95_latency_regression_pct: float | None = None,
    max_avg_ttft_regression_pct: float | None = None,
    min_decode_tokens_per_second_ratio: float | None = None,
) -> ComparisonGateReport:
    baseline, candidate = compare_runs([baseline_dir, candidate_dir])
    thresholds = {
        key: value
        for key, value in {
            "min_pass_rate": min_pass_rate,
            "max_pass_rate_drop": max_pass_rate_drop,
            "max_avg_latency_regression_pct": max_avg_latency_regression_pct,
            "max_p95_latency_regression_pct": max_p95_latency_regression_pct,
            "max_avg_ttft_regression_pct": max_avg_ttft_regression_pct,
            "min_decode_tokens_per_second_ratio": min_decode_tokens_per_second_ratio,
        }.items()
        if value is not None
    }
    findings: list[ComparisonGateFinding] = []

    if min_pass_rate is not None and candidate.pass_rate < min_pass_rate:
        findings.append(
            ComparisonGateFinding(
                metric="pass_rate",
                baseline=baseline.pass_rate,
                candidate=candidate.pass_rate,
                threshold=min_pass_rate,
                message=f"candidate pass rate {candidate.pass_rate:.3f}% is below minimum {min_pass_rate:.3f}%",
            )
        )

    if max_pass_rate_drop is not None:
        drop = round(baseline.pass_rate - candidate.pass_rate, 3)
        if drop > max_pass_rate_drop:
            findings.append(
                ComparisonGateFinding(
                    metric="pass_rate_drop",
                    baseline=baseline.pass_rate,
                    candidate=candidate.pass_rate,
                    threshold=max_pass_rate_drop,
                    message=f"candidate pass rate dropped {drop:.3f} points, exceeding {max_pass_rate_drop:.3f}",
                )
            )

    _append_latency_regression(
        findings,
        metric="avg_latency_ms",
        baseline=baseline.avg_latency_ms,
        candidate=candidate.avg_latency_ms,
        max_regression_pct=max_avg_latency_regression_pct,
    )
    _append_latency_regression(
        findings,
        metric="p95_latency_ms",
        baseline=baseline.p95_latency_ms,
        candidate=candidate.p95_latency_ms,
        max_regression_pct=max_p95_latency_regression_pct,
    )
    _append_latency_regression(
        findings,
        metric="avg_ttft_ms",
        baseline=baseline.avg_ttft_ms,
        candidate=candidate.avg_ttft_ms,
        max_regression_pct=max_avg_ttft_regression_pct,
    )

    if min_decode_tokens_per_second_ratio is not None:
        baseline_rate = baseline.avg_decode_tokens_per_second
        candidate_rate = candidate.avg_decode_tokens_per_second
        if baseline_rate is not None and baseline_rate > 0 and candidate_rate is not None:
            ratio = round(candidate_rate / baseline_rate, 6)
            if ratio < min_decode_tokens_per_second_ratio:
                findings.append(
                    ComparisonGateFinding(
                        metric="avg_decode_tokens_per_second_ratio",
                        baseline=baseline_rate,
                        candidate=candidate_rate,
                        threshold=min_decode_tokens_per_second_ratio,
                        message=(
                            f"candidate decode throughput ratio {ratio:.6f} is below minimum "
                            f"{min_decode_tokens_per_second_ratio:.6f}"
                        ),
                    )
                )

    return ComparisonGateReport(
        baseline=baseline,
        candidate=candidate,
        ok=not findings,
        thresholds=thresholds,
        findings=findings,
    )


def write_comparison_gate_json(report: ComparisonGateReport, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return output_path


def format_comparison_gate_report(report: ComparisonGateReport) -> str:
    lines = [
        f"baseline_run_id: {report.baseline.run_id}",
        f"candidate_run_id: {report.candidate.run_id}",
        f"ok: {str(report.ok).lower()}",
        f"findings: {len(report.findings)}",
    ]
    for finding in report.findings:
        lines.append(
            f"{finding.metric}	baseline={_format_float(finding.baseline)}	"
            f"candidate={_format_float(finding.candidate)}	threshold={finding.threshold}	{finding.message}"
        )
    return "\n".join(lines) + "\n"


def _append_latency_regression(
    findings: list[ComparisonGateFinding],
    *,
    metric: str,
    baseline: float | None,
    candidate: float | None,
    max_regression_pct: float | None,
) -> None:
    if max_regression_pct is None or baseline is None or baseline <= 0 or candidate is None:
        return
    regression = round(((candidate - baseline) / baseline) * 100, 6)
    if regression > max_regression_pct:
        findings.append(
            ComparisonGateFinding(
                metric=metric,
                baseline=baseline,
                candidate=candidate,
                threshold=max_regression_pct,
                message=f"candidate {metric} regressed {regression:.6f}%, exceeding {max_regression_pct:.6f}%",
            )
        )
