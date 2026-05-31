from __future__ import annotations

import csv
import shutil
from pathlib import Path

from agentblaster.errors import ConfigError
from agentblaster.reports import load_results


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
    fieldnames = [
        "run_id",
        "case_id",
        "suite",
        "provider",
        "contract",
        "model",
        "ok",
        "status_code",
        "latency_ms",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "load_ms",
        "prompt_eval_ms",
        "decode_ms",
        "tokens_per_second_prefill",
        "tokens_per_second_decode",
        "failure_class",
        "message",
        "raw_response_path",
    ]
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            row = result.model_dump(mode="json")
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    return target
