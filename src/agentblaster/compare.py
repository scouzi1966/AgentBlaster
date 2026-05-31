from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from agentblaster.reports import load_manifest, load_results


class RunComparisonRow(BaseModel):
    run_id: str
    suite: str
    provider: str
    model: str
    total_cases: int
    passed: int
    failed: int
    avg_latency_ms: float | None = None
    avg_decode_tokens_per_second: float | None = None


def compare_runs(run_dirs: list[Path]) -> list[RunComparisonRow]:
    rows: list[RunComparisonRow] = []
    for run_dir in run_dirs:
        manifest = load_manifest(run_dir)
        results = load_results(run_dir)
        latencies = [result.latency_ms for result in results if result.latency_ms is not None]
        decode_rates = [
            result.tokens_per_second_decode
            for result in results
            if result.tokens_per_second_decode is not None
        ]
        rows.append(
            RunComparisonRow(
                run_id=manifest.run_id,
                suite=manifest.suite,
                provider=manifest.provider,
                model=manifest.model,
                total_cases=len(results),
                passed=sum(1 for result in results if result.ok),
                failed=sum(1 for result in results if not result.ok),
                avg_latency_ms=_average(latencies),
                avg_decode_tokens_per_second=_average(decode_rates),
            )
        )
    return rows


def write_comparison_json(run_dirs: list[Path], output_path: Path) -> Path:
    rows = compare_runs(run_dirs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([row.model_dump(mode="json") for row in rows], indent=2, sort_keys=True) + "\n",
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
        "avg_latency_ms",
        "avg_decode_tok_s",
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
                    _format_float(row.avg_latency_ms),
                    _format_float(row.avg_decode_tokens_per_second),
                ]
            )
        )
    return "\n".join(lines)


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def _format_float(value: float | None) -> str:
    return "" if value is None else str(value)
