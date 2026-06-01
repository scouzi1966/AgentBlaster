from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from typing import Any

from agentblaster.errors import ConfigError
from agentblaster.reports import load_results


EXPORT_FIELDS = [
    "run_id",
    "case_id",
    "case_title",
    "scenario",
    "case_tags",
    "case_provenance",
    "case_risk_level",
    "case_source_url",
    "case_license",
    "cancel_after_ms",
    "suite",
    "provider",
    "contract",
    "model",
    "ok",
    "provider_endpoint_host",
    "provider_remote",
    "native_adapter",
    "adapter_name",
    "adapter_version",
    "status_code",
    "request_started_at",
    "request_completed_at",
    "queue_ms",
    "rate_limit_wait_ms",
    "latency_ms",
    "ttft_ms",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cached_input_tokens",
    "cache_write_tokens",
    "cache_hit_ratio",
    "input_cost_usd",
    "output_cost_usd",
    "cache_read_cost_usd",
    "cache_write_cost_usd",
    "request_cost_usd",
    "total_cost_usd",
    "load_ms",
    "prompt_eval_ms",
    "decode_ms",
    "tokens_per_second_prefill",
    "tokens_per_second_decode",
    "telemetry_schema_version",
    "stats_profile",
    "telemetry_sources",
    "telemetry_quality",
    "telemetry_comparison_readiness",
    "telemetry_stats_comparability",
    "telemetry_missing",
    "raw_usage",
    "raw_stats",
    "tool_calls_requested",
    "tool_calls_emitted",
    "tool_calls_valid",
    "invalid_tool_call_count",
    "tool_parser_repair_valid",
    "tool_loop_enabled",
    "tool_loop_rounds",
    "tool_loop_tool_call_count",
    "tool_loop_max_tool_calls",
    "tool_loop_stop_reason",
    "structured_output_valid",
    "judge_verdict_valid",
    "finish_reason",
    "canceled",
    "cancellation_latency_ms",
    "failure_class",
    "message",
    "raw_response_path",
]


def export_results(run_dir: Path, formats: list[str], output_dir: Path | None = None) -> list[Path]:
    target_dir = output_dir or run_dir / "exports"
    target_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []
    for export_format in formats:
        normalized = export_format.strip().lower()
        if not normalized:
            continue
        if normalized == "jsonl":
            generated.append(_export_jsonl(run_dir, target_dir))
        elif normalized == "csv":
            generated.append(_export_csv(run_dir, target_dir))
        elif normalized == "parquet":
            generated.append(_export_parquet(run_dir, target_dir))
        else:
            raise ConfigError(f"unsupported export format: {export_format}")
    return generated


def _export_jsonl(run_dir: Path, output_dir: Path) -> Path:
    source = run_dir / "results.jsonl"
    if not source.exists():
        raise ConfigError(f"missing results: {source}")
    target = output_dir / "results.jsonl"
    if source.resolve() != target.resolve():
        shutil.copyfile(source, target)
    return target


def _export_csv(run_dir: Path, output_dir: Path) -> Path:
    results = load_results(run_dir)
    target = output_dir / "results.csv"
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXPORT_FIELDS)
        writer.writeheader()
        for result in results:
            writer.writerow(_result_export_row(result.model_dump(mode="json")))
    return target


def _export_parquet(run_dir: Path, output_dir: Path) -> Path:
    try:
        import pyarrow as pa  # type: ignore[import-not-found]
        import pyarrow.parquet as pq  # type: ignore[import-not-found]
    except Exception as exc:
        raise ConfigError("parquet export requires optional dependency: install agentblaster[exports]") from exc

    rows = [_result_export_row(result.model_dump(mode="json")) for result in load_results(run_dir)]
    target = output_dir / "results.parquet"
    table = pa.Table.from_pylist(rows, metadata={b"agentblaster.schema": b"normalized-results-export-v1"})
    pq.write_table(table, target)
    return target


def _result_export_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    normalized["case_tags"] = json.dumps(normalized.get("case_tags") or [], sort_keys=True)
    normalized["telemetry_sources"] = json.dumps(normalized.get("telemetry_sources") or {}, sort_keys=True)
    normalized["telemetry_quality"] = json.dumps(normalized.get("telemetry_quality") or {}, sort_keys=True)
    normalized["telemetry_comparison_readiness"] = json.dumps(
        normalized.get("telemetry_comparison_readiness") or {},
        sort_keys=True,
    )
    normalized["telemetry_stats_comparability"] = json.dumps(
        normalized.get("telemetry_stats_comparability") or {},
        sort_keys=True,
    )
    normalized["telemetry_missing"] = json.dumps(normalized.get("telemetry_missing") or [], sort_keys=True)
    normalized["raw_usage"] = json.dumps(normalized.get("raw_usage") or {}, sort_keys=True)
    normalized["raw_stats"] = json.dumps(normalized.get("raw_stats") or {}, sort_keys=True)
    return {field: normalized.get(field, "") for field in EXPORT_FIELDS}
