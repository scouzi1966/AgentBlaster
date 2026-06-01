from __future__ import annotations

import html
import json
from pathlib import Path
from textwrap import wrap

from pydantic import ValidationError

from agentblaster.errors import ConfigError
from agentblaster.matrix import MatrixExecutionSummary
from agentblaster.models import BenchmarkResult, RawTraceMode, RunManifest, RunSummary
from agentblaster.runner import run_timing_summary


def load_manifest(run_dir: Path) -> RunManifest:
    path = run_dir / "manifest.json"
    if not path.exists():
        raise ConfigError(f"missing manifest: {path}")
    return RunManifest.model_validate_json(path.read_text(encoding="utf-8"))


def load_results(run_dir: Path) -> list[BenchmarkResult]:
    path = run_dir / "results.jsonl"
    if not path.exists():
        raise ConfigError(f"missing results: {path}")
    results: list[BenchmarkResult] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            results.append(BenchmarkResult.model_validate_json(line))
    return results


def summarize_run(run_dir: Path) -> RunSummary:
    manifest = load_manifest(run_dir)
    results = load_results(run_dir)
    return RunSummary(
        run_id=manifest.run_id,
        suite=manifest.suite,
        provider=manifest.provider,
        model=manifest.model,
        total_cases=len(results),
        passed=sum(1 for result in results if result.ok),
        failed=sum(1 for result in results if not result.ok),
        concurrency=manifest.concurrency,
        **run_timing_summary(results),
        results_path="results.jsonl",
        manifest_path="manifest.json",
    )


def write_json_summary(run_dir: Path) -> Path:
    summary = summarize_run(run_dir)
    path = run_dir / "summary.json"
    path.write_text(json.dumps(summary.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_publication_manifest(run_dir: Path) -> Path:
    manifest = load_manifest(run_dir)
    results = load_results(run_dir)
    summary = summarize_run(run_dir)
    metrics = _aggregate_metrics(results)
    failure_class_summary = _failure_class_summary(results)
    tool_loop_stop_summary = _tool_loop_stop_summary(results)
    payload = {
        "report_type": "agentblaster-publication-v1",
        "run": {
            "run_id": summary.run_id,
            "suite": summary.suite,
            "provider": summary.provider,
            "model": summary.model,
            "contract": manifest.contract.value,
            "created_at": manifest.created_at,
            "raw_trace_mode": manifest.raw_trace_mode.value,
            "concurrency": manifest.concurrency,
            "suite_sha256": manifest.suite_sha256,
            "case_sha256": manifest.case_sha256,
            "suite_snapshot_path": manifest.suite_snapshot_path,
            "suite_provenance": manifest.suite_provenance.model_dump(mode="json"),
            "provider_metadata": manifest.provider_metadata.model_dump(mode="json"),
            "engine_target": manifest.engine_target,
            "duration_ms": summary.duration_ms,
            "requests_per_second": summary.requests_per_second,
            "model_metadata": manifest.model_metadata.model_dump(mode="json"),
            "retention_policy": manifest.retention_policy.model_dump(mode="json"),
            "environment": _environment_summary(manifest),
        },
        "scorecard": {
            "total_cases": summary.total_cases,
            "passed": summary.passed,
            "failed": summary.failed,
            "pass_rate_percent": _percent_value(summary.passed, summary.total_cases),
            "avg_latency_ms": metrics["avg_latency_ms"],
            "avg_ttft_ms": metrics["avg_ttft_ms"],
            "avg_queue_ms": metrics["avg_queue_ms"],
            "avg_rate_limit_wait_ms": metrics["avg_rate_limit_wait_ms"],
            "avg_cache_hit_ratio": metrics["avg_cache_hit_ratio"],
            "avg_prefill_tokens_per_second": metrics["avg_prefill_tokens_per_second"],
            "avg_decode_tokens_per_second": metrics["avg_decode_tokens_per_second"],
            "total_cost_usd": metrics["total_cost_usd"],
            "tool_calls_emitted": metrics["tool_calls_emitted"],
            "tool_calls_valid": metrics["tool_calls_valid"],
            "invalid_tool_call_count": metrics["invalid_tool_call_count"],
            "tool_parser_repair_cases": metrics["tool_parser_repair_cases"],
            "tool_parser_repairs_valid": metrics["tool_parser_repairs_valid"],
            "tool_loop_cases": metrics["tool_loop_cases"],
            "tool_loop_rounds": metrics["tool_loop_rounds"],
            "tool_loop_tool_call_count": metrics["tool_loop_tool_call_count"],
            "judge_rubric_cases": metrics["judge_rubric_cases"],
            "judge_verdicts_valid": metrics["judge_verdicts_valid"],
            "judge_verdict_valid_rate_percent": metrics["judge_verdict_valid_rate_percent"],
            "cancellation_cases": metrics["cancellation_cases"],
            "cancellations_observed": metrics["cancellations_observed"],
            "avg_cancellation_latency_ms": metrics["avg_cancellation_latency_ms"],
            "failure_class_summary": failure_class_summary,
            "tool_loop_stop_summary": tool_loop_stop_summary,
        },
        "highlights": _publication_highlights(summary, metrics),
        "publication_readiness": _publication_readiness(run_dir, manifest, summary),
        "case_failures": [
            {
                "case_id": result.case_id,
                "case_title": result.case_title,
                "scenario": result.scenario,
                "risk_level": result.case_risk_level,
                "failure_class": result.failure_class,
                "message": result.message,
            }
            for result in results
            if not result.ok
        ],
        "scenario_summary": _scenario_summary(results),
        "artifact_hints": {
            "html": "report.html",
            "markdown": "report.md",
            "pdf": "report.pdf",
            "summary": "summary.json",
            "suite_snapshot": manifest.suite_snapshot_path or "suite.json",
            "card_svg": "report-card.svg",
            "card_png": "report-card.png",
        },
        "security": {
            "raw_trace_mode": manifest.raw_trace_mode.value,
            "contains_raw_secrets": False,
            "notes": "Publication manifest is derived from normalized results and excludes raw provider payloads. Per-case results include compact redacted raw_usage/raw_stats metric provenance.",
        },
    }
    path = run_dir / "publication.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_svg_report_card(run_dir: Path) -> Path:
    manifest = load_manifest(run_dir)
    results = load_results(run_dir)
    summary = summarize_run(run_dir)
    metrics = _aggregate_metrics(results)
    pass_rate = _format_percent(summary.passed, summary.total_cases) or "n/a"
    status = "PASS" if summary.failed == 0 else "REVIEW"
    status_color = "#156c43" if summary.failed == 0 else "#9b2721"
    model_metadata = _model_metadata_summary(manifest)
    subtitle = f"{summary.provider} / {manifest.contract.value} / {summary.suite}"
    card = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630" role="img" aria-label="AgentBlaster benchmark report card">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#fff7e8"/>
      <stop offset="0.58" stop-color="#f1e2c8"/>
      <stop offset="1" stop-color="#d7e3d2"/>
    </linearGradient>
    <radialGradient id="flare" cx="18%" cy="0%" r="70%">
      <stop offset="0" stop-color="#d66b1f" stop-opacity="0.36"/>
      <stop offset="1" stop-color="#d66b1f" stop-opacity="0"/>
    </radialGradient>
    <style>
      .label {{ font: 700 22px Avenir Next, Trebuchet MS, sans-serif; letter-spacing: 3px; fill: #70340e; }}
      .title {{ font: 800 82px Iowan Old Style, Georgia, serif; fill: #111713; letter-spacing: -4px; }}
      .sub {{ font: 500 28px Avenir Next, Trebuchet MS, sans-serif; fill: #455149; }}
      .metric-label {{ font: 800 19px Avenir Next, Trebuchet MS, sans-serif; fill: #70340e; letter-spacing: 1.5px; }}
      .metric-value {{ font: 800 42px Avenir Next, Trebuchet MS, sans-serif; fill: #111713; }}
      .small {{ font: 500 21px Avenir Next, Trebuchet MS, sans-serif; fill: #56635b; }}
      .status {{ font: 900 34px Avenir Next, Trebuchet MS, sans-serif; fill: white; letter-spacing: 2px; }}
    </style>
  </defs>
  <rect width="1200" height="630" fill="url(#bg)"/>
  <rect width="1200" height="630" fill="url(#flare)"/>
  <circle cx="1040" cy="108" r="136" fill="#111713" opacity="0.08"/>
  <circle cx="1088" cy="508" r="220" fill="#d66b1f" opacity="0.12"/>
  <text x="72" y="82" class="label">LOCAL AGENTIC BENCHMARK</text>
  <text x="72" y="176" class="title">AgentBlaster</text>
  <text x="76" y="226" class="sub">{_svg_escape(subtitle)}</text>
  <rect x="890" y="68" rx="31" ry="31" width="216" height="62" fill="{status_color}"/>
  <text x="998" y="109" text-anchor="middle" class="status">{status}</text>
  <g transform="translate(72 292)">
    {_svg_metric(0, 0, "PASS RATE", pass_rate)}
    {_svg_metric(264, 0, "CASES", f"{summary.passed}/{summary.total_cases}")}
    {_svg_metric(528, 0, "AVG LATENCY", _metric_with_unit(metrics["avg_latency_ms"], "ms"))}
    {_svg_metric(792, 0, "AVG TTFT", _metric_with_unit(metrics["avg_ttft_ms"], "ms"))}
    {_svg_metric(0, 144, "DECODE", _metric_with_unit(metrics["avg_decode_tokens_per_second"], "tok/s"))}
    {_svg_metric(264, 144, "CACHE HIT", _ratio_percent(metrics["avg_cache_hit_ratio"]))}
    {_svg_metric(528, 144, "REQ/S", _format_metric(summary.requests_per_second) or "n/a")}
    {_svg_metric(792, 144, "EST COST", _usd_metric(metrics["total_cost_usd"]))}
  </g>
  <text x="76" y="582" class="small">Model: {_svg_escape(summary.model)}</text>
  <text x="76" y="612" class="small">Metadata: {_svg_escape(model_metadata)}</text>
  <text x="1124" y="612" text-anchor="end" class="small">{_svg_escape(summary.run_id)}</text>
</svg>
"""
    path = run_dir / "report-card.svg"
    path.write_text(card, encoding="utf-8")
    return path


def write_png_report_card(run_dir: Path) -> Path:
    svg_path = write_svg_report_card(run_dir)
    target = run_dir / "report-card.png"
    _svg_to_png(svg_path, target)
    return target


def write_pdf_report(run_dir: Path) -> Path:
    manifest = load_manifest(run_dir)
    results = load_results(run_dir)
    summary = summarize_run(run_dir)
    metrics = _aggregate_metrics(results)
    failure_class_summary = _failure_class_summary(results)
    tool_loop_stop_summary = _tool_loop_stop_summary(results)
    status = "PASS" if summary.failed == 0 else "REVIEW"
    lines = [
        "AgentBlaster Benchmark Report",
        "",
        f"Run: {summary.run_id}",
        f"Suite: {summary.suite}",
        f"Provider: {summary.provider}",
        f"Contract: {manifest.contract.value}",
        f"Model: {summary.model}",
        f"Created: {manifest.created_at}",
        f"Status: {status}",
        "",
        "Scorecard",
        f"Cases: {summary.passed}/{summary.total_cases} passed",
        f"Pass rate: {_format_percent(summary.passed, summary.total_cases) or 'n/a'}",
        f"Average latency: {_metric_with_unit(metrics['avg_latency_ms'], 'ms')}",
        f"Average TTFT: {_metric_with_unit(metrics['avg_ttft_ms'], 'ms')}",
        f"Average queue wait: {_metric_with_unit(metrics['avg_queue_ms'], 'ms')}",
        f"Average rate-limit wait: {_metric_with_unit(metrics['avg_rate_limit_wait_ms'], 'ms')}",
        f"Average prefill: {_metric_with_unit(metrics['avg_prefill_tokens_per_second'], 'tok/s')}",
        f"Average decode: {_metric_with_unit(metrics['avg_decode_tokens_per_second'], 'tok/s')}",
        f"Average cache hit: {_ratio_percent(metrics['avg_cache_hit_ratio'])}",
        f"Estimated cost: {_usd_metric(metrics['total_cost_usd'])}",
        f"Tool calls valid/emitted: {metrics['tool_calls_valid']}/{metrics['tool_calls_emitted']}",
        f"Invalid tool calls: {metrics['invalid_tool_call_count']}",
        f"Tool-parser repair valid: {metrics['tool_parser_repairs_valid']}/{metrics['tool_parser_repair_cases']}",
        f"Tool-loop stop reasons: {_tool_loop_stop_summary_text(tool_loop_stop_summary)}",
        f"Failure classes: {_failure_class_summary_text(failure_class_summary)}",
        "",
        "Model and environment",
        _model_metadata_summary(manifest),
        _environment_summary(manifest),
        "",
        "Security",
        f"Raw traces: {manifest.raw_trace_mode.value}",
        "This PDF is derived from normalized metrics and excludes raw provider payloads, raw traces, API keys, and request headers.",
    ]
    failures = [result for result in results if not result.ok]
    if failures:
        lines.extend(["", "Failures"])
        for result in failures[:8]:
            lines.append(f"- {result.case_id}: {result.failure_class or 'failure'} - {result.message}")
    path = run_dir / "report.pdf"
    path.write_bytes(_simple_pdf_bytes(lines))
    return path


def write_markdown_report(run_dir: Path) -> Path:
    manifest = load_manifest(run_dir)
    results = load_results(run_dir)
    summary = summarize_run(run_dir)
    metrics = _aggregate_metrics(results)
    failure_class_summary = _failure_class_summary(results)
    tool_loop_stop_summary = _tool_loop_stop_summary(results)
    rows = "\n".join(_markdown_result_row(result) for result in results)
    report = f"""# AgentBlaster Benchmark Report

## Executive Summary

| Field | Value |
| --- | --- |
| Run | `{_markdown_cell(summary.run_id)}` |
| Suite | `{_markdown_cell(summary.suite)}` |
| Provider | `{_markdown_cell(summary.provider)}` |
| Engine target | `{_markdown_cell(_engine_target_summary(manifest))}` |
| Provider endpoint | `{_markdown_cell(manifest.provider_metadata.base_url)}` |
| Provider remote | `{str(manifest.provider_metadata.remote).lower()}` |
| TLS verify | `{str(manifest.provider_metadata.tls_verify).lower()}` |
| CA bundle | `{_markdown_cell(manifest.provider_metadata.ca_bundle)}` |
| Adapter | `{_markdown_cell(_adapter_summary(manifest))}` |
| Model | `{_markdown_cell(summary.model)}` |
| Model metadata | {_markdown_cell(_model_metadata_summary(manifest))} |
| Contract | `{_markdown_cell(manifest.contract.value)}` |
| Raw traces | `{_markdown_cell(manifest.raw_trace_mode.value)}` |
| Retention | {_markdown_cell(_retention_summary(manifest))} |
| Suite SHA-256 | `{_markdown_cell(manifest.suite_sha256)}` |
| Suite snapshot | `{_markdown_cell(manifest.suite_snapshot_path)}` |
| Suite provenance | {_markdown_cell(_suite_provenance_summary(manifest))} |
| Concurrency | `{manifest.concurrency}` |
| Duration ms | {_format_metric(summary.duration_ms)} |
| Requests/sec | {_format_metric(summary.requests_per_second)} |
| Created | `{_markdown_cell(manifest.created_at)}` |
| Environment | {_markdown_cell(_environment_summary(manifest))} |

## Scorecard

| Metric | Value |
| --- | ---: |
| Total cases | {summary.total_cases} |
| Passed | {summary.passed} |
| Failed | {summary.failed} |
| Pass rate | {_format_percent(summary.passed, summary.total_cases)} |
| Average latency ms | {_format_metric(metrics["avg_latency_ms"])} |
| Average TTFT ms | {_format_metric(metrics["avg_ttft_ms"])} |
| Average queue ms | {_format_metric(metrics["avg_queue_ms"])} |
| Average rate-limit wait ms | {_format_metric(metrics["avg_rate_limit_wait_ms"])} |
| Average cache hit ratio | {_format_metric(metrics["avg_cache_hit_ratio"])} |
| Average prefill tok/s | {_format_metric(metrics["avg_prefill_tokens_per_second"])} |
| Average decode tok/s | {_format_metric(metrics["avg_decode_tokens_per_second"])} |
| Estimated cost USD | {_format_metric(metrics["total_cost_usd"])} |
| Tool calls emitted | {_format_metric(metrics["tool_calls_emitted"])} |
| Tool calls valid | {_format_metric(metrics["tool_calls_valid"])} |
| Invalid tool calls | {_format_metric(metrics["invalid_tool_call_count"])} |
| Tool-parser repair valid | {_format_metric(metrics["tool_parser_repairs_valid"])}/{_format_metric(metrics["tool_parser_repair_cases"])} |
| Tool-loop cases | {_format_metric(metrics["tool_loop_cases"])} |
| Tool-loop rounds | {_format_metric(metrics["tool_loop_rounds"])} |
| Judge rubric cases | {_format_metric(metrics["judge_rubric_cases"])} |
| Judge verdicts valid | {_format_metric(metrics["judge_verdicts_valid"])} |
| Judge verdict valid rate | {_format_metric(metrics["judge_verdict_valid_rate_percent"])}% |
| Tool-loop stop reasons | {_markdown_cell(_tool_loop_stop_summary_text(tool_loop_stop_summary))} |
| Failure classes | {_markdown_cell(_failure_class_summary_text(failure_class_summary))} |

## Case Results

| Case | Scenario | Status | Queue ms | Rate-limit ms | Latency ms | TTFT ms | Input | Cached | Output | Cost USD | Tools | Judge | Finish | Message |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
{rows}
"""
    path = run_dir / "report.md"
    path.write_text(report, encoding="utf-8")
    return path


def write_html_report(run_dir: Path) -> Path:
    manifest = load_manifest(run_dir)
    results = load_results(run_dir)
    summary = summarize_run(run_dir)
    metrics = _aggregate_metrics(results)
    failure_class_summary = _failure_class_summary(results)
    tool_loop_stop_summary = _tool_loop_stop_summary(results)
    rows = "\n".join(_result_row(result) for result in results)
    report = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>AgentBlaster Report {html.escape(summary.run_id)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 40px; color: #172026; }}
    header {{ border-bottom: 1px solid #d7dde2; margin-bottom: 24px; padding-bottom: 16px; }}
    h1 {{ margin: 0 0 8px; }}
    .meta {{ color: #52616b; line-height: 1.5; }}
    .score {{ display: flex; gap: 16px; margin: 24px 0; }}
    .metric {{ border: 1px solid #d7dde2; border-radius: 6px; padding: 14px 18px; min-width: 110px; }}
    .metric strong {{ display: block; font-size: 28px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #e6eaee; padding: 10px; text-align: left; vertical-align: top; }}
    th {{ background: #f7f9fb; }}
    .pass {{ color: #0b6b3a; font-weight: 600; }}
    .fail {{ color: #a52222; font-weight: 600; }}
  </style>
</head>
<body>
  <header>
    <h1>AgentBlaster Benchmark Report</h1>
    <div class="meta">
      Run: {html.escape(summary.run_id)}<br>
      Suite: {html.escape(summary.suite)}<br>
      Provider: {html.escape(summary.provider)}<br>
      Engine target: {html.escape(_engine_target_summary(manifest))}<br>
      Provider endpoint: {html.escape(manifest.provider_metadata.base_url or "")}<br>
      Provider remote: {str(manifest.provider_metadata.remote).lower()}<br>
      TLS verify: {str(manifest.provider_metadata.tls_verify).lower()}<br>
      CA bundle: {html.escape(manifest.provider_metadata.ca_bundle or "")}<br>
      Adapter: {html.escape(_adapter_summary(manifest))}<br>
      Model: {html.escape(summary.model)}<br>
      Model metadata: {html.escape(_model_metadata_summary(manifest))}<br>
      Contract: {html.escape(manifest.contract.value)}<br>
      Raw traces: {html.escape(manifest.raw_trace_mode.value)}<br>
      Retention: {html.escape(_retention_summary(manifest))}<br>
      Suite SHA-256: {html.escape(manifest.suite_sha256 or "")}<br>
      Suite snapshot: {html.escape(manifest.suite_snapshot_path or "")}<br>
      Suite provenance: {html.escape(_suite_provenance_summary(manifest))}<br>
      Concurrency: {manifest.concurrency}<br>
      Duration ms: {_cell(summary.duration_ms)}<br>
      Requests/sec: {_cell(summary.requests_per_second)}<br>
      Created: {html.escape(manifest.created_at)}<br>
      Environment: {html.escape(_environment_summary(manifest))}
    </div>
  </header>
  <section class="score">
    <div class="metric"><span>Total</span><strong>{summary.total_cases}</strong></div>
    <div class="metric"><span>Passed</span><strong>{summary.passed}</strong></div>
    <div class="metric"><span>Failed</span><strong>{summary.failed}</strong></div>
    <div class="metric"><span>Judge verdicts</span><strong>{_cell(metrics["judge_verdicts_valid"])}/{_cell(metrics["judge_rubric_cases"])}</strong></div>
    <div class="metric"><span>Tool-loop stops</span><strong>{html.escape(_tool_loop_stop_summary_text(tool_loop_stop_summary))}</strong></div>
    <div class="metric"><span>Failure classes</span><strong>{html.escape(_failure_class_summary_text(failure_class_summary))}</strong></div>
  </section>
  <table>
    <thead>
      <tr>
        <th>Case</th>
        <th>Scenario</th>
        <th>Status</th>
        <th>Queue ms</th>
        <th>Rate-limit ms</th>
        <th>Latency ms</th>
        <th>TTFT ms</th>
        <th>Input</th>
        <th>Cached</th>
        <th>Cache hit</th>
        <th>Output</th>
        <th>Cost USD</th>
        <th>Total</th>
        <th>Prefill tok/s</th>
        <th>Decode tok/s</th>
        <th>Tools</th>
        <th>Structured</th>
        <th>Judge</th>
        <th>Finish</th>
        <th>Message</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
</body>
</html>
"""
    path = run_dir / "report.html"
    path.write_text(report, encoding="utf-8")
    return path


def generate_reports(run_dir: Path, formats: list[str]) -> list[Path]:
    generated: list[Path] = []
    write_publication = False
    for report_format in formats:
        normalized = report_format.strip().lower()
        if not normalized:
            continue
        if normalized == "html":
            generated.append(write_html_report(run_dir))
        elif normalized in {"md", "markdown"}:
            generated.append(write_markdown_report(run_dir))
        elif normalized == "json":
            generated.append(write_json_summary(run_dir))
        elif normalized in {"publication", "pubjson"}:
            write_publication = True
        elif normalized in {"card", "svg"}:
            generated.append(write_svg_report_card(run_dir))
        elif normalized == "png":
            generated.append(write_png_report_card(run_dir))
        elif normalized == "pdf":
            generated.append(write_pdf_report(run_dir))
        else:
            raise ConfigError(f"unsupported report format: {report_format}")
    if write_publication:
        generated.append(write_publication_manifest(run_dir))
    return generated


def generate_matrix_reports(summary_json: Path, formats: list[str], output_dir: Path | None = None) -> list[Path]:
    summary = load_matrix_execution_summary(summary_json)
    target_dir = output_dir or summary_json.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []
    for report_format in formats:
        normalized = report_format.strip().lower()
        if not normalized:
            continue
        if normalized == "html":
            generated.append(write_matrix_html_report(summary, target_dir, summary_json.stem))
        elif normalized in {"md", "markdown"}:
            generated.append(write_matrix_markdown_report(summary, target_dir, summary_json.stem))
        elif normalized in {"json", "publication", "pubjson"}:
            generated.append(write_matrix_json_report(summary, target_dir, summary_json.stem))
        elif normalized == "pdf":
            generated.append(write_matrix_pdf_report(summary, target_dir, summary_json.stem))
        else:
            raise ConfigError(f"unsupported matrix report format: {report_format}")
    return generated


def generate_matrix_scorecard_reports(summary_json: Path, formats: list[str], output_dir: Path | None = None) -> list[Path]:
    summary = load_matrix_execution_summary(summary_json)
    target_dir = output_dir or summary_json.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []
    for report_format in formats:
        normalized = report_format.strip().lower()
        if not normalized:
            continue
        if normalized == "html":
            generated.append(write_matrix_scorecard_html(summary, target_dir, summary_json.stem, summary_json.parent))
        elif normalized in {"md", "markdown"}:
            generated.append(write_matrix_scorecard_markdown(summary, target_dir, summary_json.stem, summary_json.parent))
        elif normalized in {"json", "publication", "pubjson"}:
            generated.append(write_matrix_scorecard_json(summary, target_dir, summary_json.stem, summary_json.parent))
        elif normalized in {"card", "svg"}:
            generated.append(write_matrix_scorecard_svg(summary, target_dir, summary_json.stem, summary_json.parent))
        elif normalized == "png":
            generated.append(write_matrix_scorecard_png(summary, target_dir, summary_json.stem, summary_json.parent))
        elif normalized == "pdf":
            generated.append(write_matrix_scorecard_pdf(summary, target_dir, summary_json.stem, summary_json.parent))
        else:
            raise ConfigError(f"unsupported matrix scorecard format: {report_format}")
    return generated


def write_matrix_scorecard_json(summary: MatrixExecutionSummary, output_dir: Path, stem: str, base_dir: Path) -> Path:
    payload = matrix_scorecard_payload(summary, base_dir=base_dir)
    path = output_dir / f"{stem}-matrix-scorecard.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_matrix_scorecard_markdown(summary: MatrixExecutionSummary, output_dir: Path, stem: str, base_dir: Path) -> Path:
    payload = matrix_scorecard_payload(summary, base_dir=base_dir)
    architecture_rows = "\n".join(
        _matrix_scorecard_group_markdown_row(row, "model_architecture") for row in payload["architecture_summary"]
    )
    quantization_rows = "\n".join(
        _matrix_scorecard_group_markdown_row(row, "quantization") for row in payload["quantization_summary"]
    )
    rows = "\n".join(_matrix_scorecard_markdown_row(row) for row in payload["leaderboard"])
    telemetry_quality_text = _telemetry_quality_summary_text(payload["scorecard"]["telemetry_quality_summary"])
    concurrency_evidence_text = _scorecard_concurrency_evidence_text(payload["scorecard"]["concurrency_evidence"])
    report = f"""# AgentBlaster Matrix Scorecard

## Executive Summary

| Field | Value |
| --- | --- |
| Matrix | `{_markdown_cell(payload['matrix']['name'])}` |
| Source | `{_markdown_cell(payload['matrix']['path'])}` |
| Created | `{_markdown_cell(payload['matrix']['created_at'])}` |
| Completed runs | {payload['matrix']['completed_runs']}/{payload['matrix']['total_runs']} |
| Failed runs | {payload['matrix']['failed_runs']} |
| Cases | {payload['scorecard']['passed_cases']}/{payload['scorecard']['total_cases']} passed |
| Pass rate | {_format_metric(payload['scorecard']['pass_rate_percent'])}% |
| Result artifacts loaded | {payload['scorecard']['result_artifacts_loaded']}/{payload['scorecard']['entry_count']} |
| Telemetry quality | {_markdown_cell(telemetry_quality_text)} |
| Concurrency evidence | {_markdown_cell(concurrency_evidence_text)} |
| Judge verdicts valid | {payload['scorecard']['judge_verdicts_valid']}/{payload['scorecard']['judge_rubric_cases']} |
| Judge verdict valid rate | {_format_metric(payload['scorecard']['judge_verdict_valid_rate_percent'])}% |
| Invalid tool calls | {_format_metric(payload['scorecard']['invalid_tool_call_count'])} |
| Tool-parser repair valid | {payload['scorecard']['tool_parser_repairs_valid']}/{payload['scorecard']['tool_parser_repair_cases']} |
| Tool-parser repair valid rate | {_format_metric(payload['scorecard']['tool_parser_repair_valid_rate_percent'])}% |
| Tool-loop stop reasons | {_markdown_cell(_tool_loop_stop_summary_text(payload['scorecard']['tool_loop_stop_summary']))} |
| Failure classes | {_markdown_cell(_failure_class_summary_text(payload['scorecard']['failure_class_summary']))} |

## Architecture Summary

| Architecture | Runs | Failed runs | Cases | Passed | Failed | Pass rate | Avg latency ms | Avg TTFT ms | Decode tok/s | Cache hit | Judge | Telemetry |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{architecture_rows}

## Quantization Summary

| Quantization | Runs | Failed runs | Cases | Passed | Failed | Pass rate | Avg latency ms | Avg TTFT ms | Decode tok/s | Cache hit | Judge | Telemetry |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{quantization_rows}

## Leaderboard

| Rank | Engine | Provider | Model | Suite | Status | Pass rate | Cases | Queue ms | Rate-limit ms | Avg latency ms | Avg TTFT ms | Decode tok/s | Cache hit | Judge | Cancel | Cost USD | Telemetry | Run |
| ---: | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
{rows}

## Security

This scorecard is derived from normalized summaries and result rows. It excludes raw provider responses, raw traces, API keys, and request headers.
"""
    path = output_dir / f"{stem}-matrix-scorecard.md"
    path.write_text(report, encoding="utf-8")
    return path


def write_matrix_scorecard_html(summary: MatrixExecutionSummary, output_dir: Path, stem: str, base_dir: Path) -> Path:
    payload = matrix_scorecard_payload(summary, base_dir=base_dir)
    architecture_rows = "\n".join(
        _matrix_scorecard_group_html_row(row, "model_architecture") for row in payload["architecture_summary"]
    )
    quantization_rows = "\n".join(
        _matrix_scorecard_group_html_row(row, "quantization") for row in payload["quantization_summary"]
    )
    rows = "\n".join(_matrix_scorecard_html_row(row) for row in payload["leaderboard"])
    telemetry_quality_text = _telemetry_quality_summary_text(payload["scorecard"]["telemetry_quality_summary"])
    concurrency_evidence_text = _scorecard_concurrency_evidence_text(payload["scorecard"]["concurrency_evidence"])
    report = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>AgentBlaster Matrix Scorecard {html.escape(summary.matrix_name)}</title>
  <style>
    body {{ font-family: Avenir Next, Trebuchet MS, sans-serif; margin: 40px; color: #172026; background: #fbf7ef; }}
    h1, h2 {{ font-family: Iowan Old Style, Georgia, serif; color: #111713; }}
    h1 {{ margin: 0 0 8px; font-size: 52px; letter-spacing: -1.5px; }}
    .meta {{ color: #52616b; line-height: 1.5; }}
    .score {{ display: flex; flex-wrap: wrap; gap: 16px; margin: 24px 0; }}
    .metric {{ background: #fffdf6; border: 1px solid #d8c7ab; border-radius: 16px; padding: 16px 20px; min-width: 150px; }}
    .metric strong {{ display: block; font-size: 30px; color: #111713; }}
    table {{ border-collapse: collapse; width: 100%; background: #fffdf6; }}
    th, td {{ border-bottom: 1px solid #e7dccb; padding: 10px; text-align: left; vertical-align: top; }}
    th {{ background: #efe2cd; color: #4a3015; }}
    .pass {{ color: #0b6b3a; font-weight: 800; }}
    .fail {{ color: #a52222; font-weight: 800; }}
    .muted {{ color: #66737d; }}
  </style>
</head>
<body>
  <header>
    <h1>AgentBlaster Matrix Scorecard</h1>
    <div class="meta">
      Matrix: {html.escape(payload['matrix']['name'])}<br>
      Source: {html.escape(payload['matrix']['path'])}<br>
      Created: {html.escape(payload['matrix']['created_at'])}<br>
      Description: {html.escape(payload['matrix']['description'])}
    </div>
  </header>
  <section class="score">
    <div class="metric"><span>Runs</span><strong>{payload['matrix']['completed_runs']}/{payload['matrix']['total_runs']}</strong></div>
    <div class="metric"><span>Failed runs</span><strong>{payload['matrix']['failed_runs']}</strong></div>
    <div class="metric"><span>Cases</span><strong>{payload['scorecard']['passed_cases']}/{payload['scorecard']['total_cases']}</strong></div>
    <div class="metric"><span>Pass rate</span><strong>{_format_metric(payload['scorecard']['pass_rate_percent'])}%</strong></div>
    <div class="metric"><span>Artifacts loaded</span><strong>{payload['scorecard']['result_artifacts_loaded']}/{payload['scorecard']['entry_count']}</strong></div>
    <div class="metric"><span>Telemetry quality</span><strong>{html.escape(telemetry_quality_text)}</strong></div>
    <div class="metric"><span>Concurrency evidence</span><strong>{html.escape(concurrency_evidence_text)}</strong></div>
    <div class="metric"><span>Judge verdicts</span><strong>{payload['scorecard']['judge_verdicts_valid']}/{payload['scorecard']['judge_rubric_cases']}</strong></div>
    <div class="metric"><span>Parser repair</span><strong>{payload['scorecard']['tool_parser_repairs_valid']}/{payload['scorecard']['tool_parser_repair_cases']}</strong></div>
    <div class="metric"><span>Invalid tool calls</span><strong>{payload['scorecard']['invalid_tool_call_count']}</strong></div>
    <div class="metric"><span>Tool-loop stops</span><strong>{html.escape(_tool_loop_stop_summary_text(payload['scorecard']['tool_loop_stop_summary']))}</strong></div>
    <div class="metric"><span>Failure classes</span><strong>{html.escape(_failure_class_summary_text(payload['scorecard']['failure_class_summary']))}</strong></div>
  </section>
  <h2>Architecture Summary</h2>
  <table>
    <thead><tr><th>Architecture</th><th>Runs</th><th>Failed runs</th><th>Cases</th><th>Passed</th><th>Failed</th><th>Pass rate</th><th>Avg latency</th><th>Avg TTFT</th><th>Decode tok/s</th><th>Cache hit</th><th>Judge</th><th>Telemetry</th></tr></thead>
    <tbody>{architecture_rows}</tbody>
  </table>
  <h2>Quantization Summary</h2>
  <table>
    <thead><tr><th>Quantization</th><th>Runs</th><th>Failed runs</th><th>Cases</th><th>Passed</th><th>Failed</th><th>Pass rate</th><th>Avg latency</th><th>Avg TTFT</th><th>Decode tok/s</th><th>Cache hit</th><th>Judge</th><th>Telemetry</th></tr></thead>
    <tbody>{quantization_rows}</tbody>
  </table>
  <h2>Leaderboard</h2>
  <table>
    <thead><tr><th>Rank</th><th>Engine</th><th>Provider</th><th>Model</th><th>Suite</th><th>Status</th><th>Pass rate</th><th>Cases</th><th>Queue</th><th>Rate wait</th><th>Avg latency</th><th>Avg TTFT</th><th>Decode tok/s</th><th>Cache hit</th><th>Judge</th><th>Cancel</th><th>Cost</th><th>Telemetry</th><th>Run</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>
"""
    path = output_dir / f"{stem}-matrix-scorecard.html"
    path.write_text(report, encoding="utf-8")
    return path


def write_matrix_scorecard_svg(summary: MatrixExecutionSummary, output_dir: Path, stem: str, base_dir: Path) -> Path:
    payload = matrix_scorecard_payload(summary, base_dir=base_dir)
    scorecard = payload["scorecard"]
    matrix = payload["matrix"]
    top_rows = "\n".join(
        _matrix_scorecard_svg_leader_row(row, y=296 + (index * 58))
        for index, row in enumerate(payload["leaderboard"][:3])
    )
    architecture_rows = "\n".join(
        _matrix_scorecard_svg_group_row(row, y=296 + (index * 50))
        for index, row in enumerate(payload["architecture_summary"][:3])
    )
    status = "PASS" if matrix["failed_runs"] == 0 and scorecard["failed_cases"] == 0 else "REVIEW"
    status_color = "#156c43" if status == "PASS" else "#9b2721"
    pass_rate = _format_metric(scorecard["pass_rate_percent"])
    pass_rate_label = f"{pass_rate}%" if pass_rate else "n/a"
    top_engine = payload["leaderboard"][0]["engine"] if payload["leaderboard"] else "none"
    telemetry_quality_text = _scorecard_telemetry_card_text(scorecard["telemetry_quality_summary"])
    concurrency_evidence_text = _scorecard_concurrency_card_text(scorecard["concurrency_evidence"])
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630" role="img" aria-label="AgentBlaster matrix scorecard">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#f8efe2"/>
      <stop offset="0.52" stop-color="#e7d4b7"/>
      <stop offset="1" stop-color="#ccd9d2"/>
    </linearGradient>
    <radialGradient id="flare" cx="86%" cy="12%" r="70%">
      <stop offset="0" stop-color="#0f6a61" stop-opacity="0.28"/>
      <stop offset="1" stop-color="#0f6a61" stop-opacity="0"/>
    </radialGradient>
    <style>
      .label {{ font: 700 22px Avenir Next, Trebuchet MS, sans-serif; letter-spacing: 3px; fill: #6a3814; }}
      .title {{ font: 800 66px Iowan Old Style, Georgia, serif; fill: #111713; letter-spacing: -3px; }}
      .sub {{ font: 500 25px Avenir Next, Trebuchet MS, sans-serif; fill: #435148; }}
      .metric-label {{ font: 800 17px Avenir Next, Trebuchet MS, sans-serif; fill: #6a3814; letter-spacing: 1.4px; }}
      .metric-value {{ font: 800 34px Avenir Next, Trebuchet MS, sans-serif; fill: #111713; }}
      .table-head {{ font: 800 17px Avenir Next, Trebuchet MS, sans-serif; fill: #6a3814; letter-spacing: 1px; }}
      .row-main {{ font: 800 22px Avenir Next, Trebuchet MS, sans-serif; fill: #111713; }}
      .row-sub {{ font: 500 18px Avenir Next, Trebuchet MS, sans-serif; fill: #5b675f; }}
      .small {{ font: 500 18px Avenir Next, Trebuchet MS, sans-serif; fill: #56635b; }}
      .status {{ font: 900 31px Avenir Next, Trebuchet MS, sans-serif; fill: white; letter-spacing: 2px; }}
    </style>
  </defs>
  <rect width="1200" height="630" fill="url(#bg)"/>
  <rect width="1200" height="630" fill="url(#flare)"/>
  <circle cx="1046" cy="104" r="150" fill="#111713" opacity="0.08"/>
  <circle cx="1110" cy="520" r="238" fill="#d66b1f" opacity="0.12"/>
  <text x="70" y="72" class="label">MATRIX SCORECARD</text>
  <text x="70" y="150" class="title">AgentBlaster</text>
  <text x="74" y="196" class="sub">{_svg_escape(matrix['name'])}</text>
  <rect x="906" y="62" rx="30" ry="30" width="206" height="60" fill="{status_color}"/>
  <text x="1009" y="102" text-anchor="middle" class="status">{status}</text>
  <g transform="translate(70 226)">
    {_svg_metric(0, 0, "PASS RATE", pass_rate_label)}
    {_svg_metric(244, 0, "RUNS", f"{matrix['completed_runs']}/{matrix['total_runs']}")}
    {_svg_metric(488, 0, "CASES", f"{scorecard['passed_cases']}/{scorecard['total_cases']}")}
    {_svg_metric(732, 0, "TOP ENGINE", str(top_engine))}
  </g>
  <text x="74" y="284" class="table-head">LEADERBOARD</text>
  <text x="682" y="284" class="table-head">ARCHITECTURES</text>
  <g>{top_rows}</g>
  <g>{architecture_rows}</g>
  <text x="74" y="586" class="small">Source: {_svg_escape(matrix['path'])}</text>
  <text x="1124" y="586" text-anchor="end" class="small">Artifacts loaded: {scorecard['result_artifacts_loaded']}/{scorecard['entry_count']} - Parser repair: {scorecard['tool_parser_repairs_valid']}/{scorecard['tool_parser_repair_cases']} - Invalid tools: {scorecard['invalid_tool_call_count']}</text>
  <text x="74" y="614" class="small">No raw traces, provider payloads, API keys, or request headers included.</text>
  <text x="1124" y="614" text-anchor="end" class="small">Telemetry: {_svg_escape(telemetry_quality_text)} - Concurrency: {_svg_escape(concurrency_evidence_text)}</text>
</svg>
"""
    path = output_dir / f"{stem}-matrix-scorecard.svg"
    path.write_text(svg, encoding="utf-8")
    return path


def write_matrix_scorecard_png(summary: MatrixExecutionSummary, output_dir: Path, stem: str, base_dir: Path) -> Path:
    svg_path = write_matrix_scorecard_svg(summary, output_dir, stem, base_dir)
    target = output_dir / f"{stem}-matrix-scorecard.png"
    _svg_to_png(svg_path, target)
    return target


def write_matrix_scorecard_pdf(summary: MatrixExecutionSummary, output_dir: Path, stem: str, base_dir: Path) -> Path:
    payload = matrix_scorecard_payload(summary, base_dir=base_dir)
    matrix = payload["matrix"]
    scorecard = payload["scorecard"]
    lines = [
        "AgentBlaster Matrix Scorecard",
        "",
        f"Matrix: {matrix['name']}",
        f"Source: {matrix['path']}",
        f"Created: {matrix['created_at']}",
        f"Runs: {matrix['completed_runs']}/{matrix['total_runs']} completed",
        f"Failed runs: {matrix['failed_runs']}",
        f"Cases: {scorecard['passed_cases']}/{scorecard['total_cases']} passed",
        f"Pass rate: {_format_metric(scorecard['pass_rate_percent']) or 'n/a'}%",
        f"Result artifacts loaded: {scorecard['result_artifacts_loaded']}/{scorecard['entry_count']}",
        f"Telemetry quality: {_telemetry_quality_summary_text(scorecard['telemetry_quality_summary'])}",
        f"Concurrency evidence: {_scorecard_concurrency_evidence_text(scorecard['concurrency_evidence'])}",
        f"Judge verdicts valid: {scorecard['judge_verdicts_valid']}/{scorecard['judge_rubric_cases']}",
        f"Tool-parser repair valid: {scorecard['tool_parser_repairs_valid']}/{scorecard['tool_parser_repair_cases']}",
        f"Invalid tool calls: {scorecard['invalid_tool_call_count']}",
        f"Tool-loop stop reasons: {_tool_loop_stop_summary_text(scorecard['tool_loop_stop_summary'])}",
        f"Failure classes: {_failure_class_summary_text(scorecard['failure_class_summary'])}",
        "",
        "Top leaderboard entries",
    ]
    for row in payload["leaderboard"][:8]:
        lines.append(
            f"#{row['rank']} {row['engine']} / {row['model']} / {row['suite']}: "
            f"{_format_metric(row['pass_rate_percent'])}% pass, "
            f"latency={_metric_with_unit(row['avg_latency_ms'], 'ms')}, "
            f"decode={_metric_with_unit(row['avg_decode_tokens_per_second'], 'tok/s')}"
        )
    if payload["architecture_summary"]:
        lines.extend(["", "Architecture summary"])
        for row in payload["architecture_summary"][:6]:
            lines.append(
                f"{row['model_architecture']}: {row['passed']}/{row['total_cases']} passed, "
                f"decode={_metric_with_unit(row['avg_decode_tokens_per_second'], 'tok/s')}, "
                f"telemetry={_format_metric(row['telemetry_completeness_percent']) or 'n/a'}%"
            )
    lines.extend(
        [
            "",
            "Security",
            "This PDF is derived from normalized matrix summaries, run manifests, and result rows where available.",
            "It excludes raw provider payloads, raw traces, API keys, request headers, and per-case raw responses.",
        ]
    )
    path = output_dir / f"{stem}-matrix-scorecard.pdf"
    path.write_bytes(_simple_pdf_bytes(lines))
    return path


def matrix_scorecard_payload(summary: MatrixExecutionSummary, *, base_dir: Path) -> dict:
    entries = [_matrix_scorecard_entry(run, base_dir=base_dir) for run in summary.runs]
    ranked = sorted(
        entries,
        key=lambda row: (
            -(row["pass_rate_percent"] if row["pass_rate_percent"] is not None else -1),
            row["avg_latency_ms"] if row["avg_latency_ms"] is not None else float("inf"),
            -(row["avg_decode_tokens_per_second"] if row["avg_decode_tokens_per_second"] is not None else -1),
            row["engine"],
            row["model"],
            row["suite"],
        ),
    )
    leaderboard = [dict(row, rank=index) for index, row in enumerate(ranked, start=1)]
    total_cases = sum(row["total_cases"] for row in entries)
    passed_cases = sum(row["passed"] for row in entries)
    failed_cases = sum(row["failed"] for row in entries)
    judge_rubric_cases = sum(int(row["judge_rubric_cases"] or 0) for row in entries)
    judge_verdicts_valid = sum(int(row["judge_verdicts_valid"] or 0) for row in entries)
    invalid_tool_call_count = sum(int(row["invalid_tool_call_count"] or 0) for row in entries)
    tool_parser_repair_cases = sum(int(row["tool_parser_repair_cases"] or 0) for row in entries)
    tool_parser_repairs_valid = sum(int(row["tool_parser_repairs_valid"] or 0) for row in entries)
    failure_class_summary = _combine_failure_class_summaries([row["failure_class_summary"] for row in entries])
    tool_loop_stop_summary = _combine_tool_loop_stop_summaries([row["tool_loop_stop_summary"] for row in entries])
    telemetry_quality_summary = _telemetry_quality_summary(entries)
    stats_comparability_summary = _stats_comparability_summary(entries)
    concurrency_evidence = _scorecard_concurrency_evidence(entries)
    return {
        "report_type": "agentblaster-matrix-scorecard-v1",
        "matrix": {
            "name": summary.matrix_name,
            "path": summary.matrix_path,
            "description": summary.description,
            "created_at": summary.created_at,
            "dry_run": summary.dry_run,
            "continue_on_error": summary.continue_on_error,
            "total_runs": summary.total_runs,
            "attempted_runs": summary.attempted_runs,
            "completed_runs": summary.completed_runs,
            "failed_runs": summary.failed_runs,
        },
        "scorecard": {
            "entry_count": len(entries),
            "total_cases": total_cases,
            "passed_cases": passed_cases,
            "failed_cases": failed_cases,
            "pass_rate_percent": _percent_value(passed_cases, total_cases),
            "result_artifacts_loaded": sum(1 for row in entries if row["result_artifacts_loaded"]),
            "invalid_tool_call_count": invalid_tool_call_count,
            "tool_parser_repair_cases": tool_parser_repair_cases,
            "tool_parser_repairs_valid": tool_parser_repairs_valid,
            "tool_parser_repair_valid_rate_percent": _percent_value(tool_parser_repairs_valid, tool_parser_repair_cases),
            "judge_rubric_cases": judge_rubric_cases,
            "judge_verdicts_valid": judge_verdicts_valid,
            "judge_verdict_valid_rate_percent": _percent_value(judge_verdicts_valid, judge_rubric_cases),
            "failure_class_summary": failure_class_summary,
            "tool_loop_stop_summary": tool_loop_stop_summary,
            "telemetry_quality_summary": telemetry_quality_summary,
            "stats_comparability_summary": stats_comparability_summary,
            "concurrency_evidence": concurrency_evidence,
            "engine_targets": _matrix_engine_targets(summary),
        },
        "architecture_summary": _matrix_scorecard_group_summary(entries, key="model_architecture"),
        "quantization_summary": _matrix_scorecard_group_summary(entries, key="quantization"),
        "leaderboard": leaderboard,
        "entries": entries,
        "security": {
            "contains_raw_secrets": False,
            "contains_raw_provider_payloads": False,
            "notes": "Scorecards are derived from normalized summaries and result rows. They exclude raw provider responses, raw traces, API keys, and request headers.",
        },
    }


def _matrix_scorecard_entry(run, *, base_dir: Path) -> dict:
    results = _load_matrix_run_results(run, base_dir=base_dir)
    manifest = _load_matrix_run_manifest(run, base_dir=base_dir)
    metrics = _aggregate_metrics(results) if results else _empty_matrix_metrics()
    failure_class_summary = _failure_class_summary(results)
    tool_loop_stop_summary = _tool_loop_stop_summary(results)
    telemetry_fields = _available_telemetry_fields(results)
    telemetry_quality_counts = _telemetry_quality_counts(results)
    telemetry_comparison_guidance = _telemetry_comparison_guidance(results)
    stats_comparability = _telemetry_stats_comparability(results)
    pass_rate = _percent_value(run.passed, run.total_cases)
    engine_target = run.engine_target or (manifest.engine_target if manifest is not None else None)
    return {
        "index": run.index,
        "engine": run.engine,
        "provider": run.provider,
        "engine_target": engine_target,
        "engine_target_id": _engine_target_id(engine_target),
        "model": run.model,
        "model_architecture": _matrix_model_architecture(run.model, manifest),
        "quantization": _matrix_model_quantization(manifest),
        "suite": run.suite,
        "run_id": run.run_id,
        "ok": run.ok,
        "status": "pass" if run.ok else "fail",
        "total_cases": run.total_cases,
        "passed": run.passed,
        "failed": run.failed,
        "pass_rate_percent": pass_rate,
        "concurrency": run.concurrency,
        "avg_latency_ms": metrics["avg_latency_ms"],
        "avg_ttft_ms": metrics["avg_ttft_ms"],
        "avg_queue_ms": metrics["avg_queue_ms"],
        "avg_rate_limit_wait_ms": metrics["avg_rate_limit_wait_ms"],
        "scenario_count": len(_scenario_names(results)),
        "scenarios": _scenario_names(results),
        "fanout_cases": sum(1 for result in results if result.scenario == "agent fan-out" or "fanout" in result.case_tags),
        "avg_cache_hit_ratio": metrics["avg_cache_hit_ratio"],
        "avg_prefill_tokens_per_second": metrics["avg_prefill_tokens_per_second"],
        "avg_decode_tokens_per_second": metrics["avg_decode_tokens_per_second"],
        "total_cost_usd": metrics["total_cost_usd"],
        "tool_calls_emitted": metrics["tool_calls_emitted"],
        "tool_calls_valid": metrics["tool_calls_valid"],
        "invalid_tool_call_count": metrics["invalid_tool_call_count"],
        "tool_parser_repair_cases": metrics["tool_parser_repair_cases"],
        "tool_parser_repairs_valid": metrics["tool_parser_repairs_valid"],
        "tool_loop_cases": metrics["tool_loop_cases"],
        "tool_loop_rounds": metrics["tool_loop_rounds"],
        "tool_loop_tool_call_count": metrics["tool_loop_tool_call_count"],
        "judge_rubric_cases": metrics["judge_rubric_cases"],
        "judge_verdicts_valid": metrics["judge_verdicts_valid"],
        "judge_verdict_valid_rate_percent": metrics["judge_verdict_valid_rate_percent"],
        "cancellation_cases": metrics["cancellation_cases"],
        "cancellations_observed": metrics["cancellations_observed"],
        "avg_cancellation_latency_ms": metrics["avg_cancellation_latency_ms"],
        "failure_class_summary": failure_class_summary,
        "tool_loop_stop_summary": tool_loop_stop_summary,
        "telemetry_fields_available": telemetry_fields,
        "telemetry_completeness_percent": _percent_value(len(telemetry_fields), len(_SCORECARD_TELEMETRY_FIELDS)),
        "telemetry_quality_counts": telemetry_quality_counts,
        "telemetry_comparison_guidance": telemetry_comparison_guidance,
        "stats_profiles": stats_comparability["profiles"],
        "stats_comparability_guidance": stats_comparability["guidance_counts"],
        "stats_comparability_requires_labeling": stats_comparability["requires_labeling_count"],
        "result_artifacts_loaded": bool(results),
        "results_path": run.results_path,
        "manifest_path": run.manifest_path,
        "summary_path": run.summary_path,
        "error_type": run.error_type,
        "error_message": run.error_message,
    }


_SCORECARD_TELEMETRY_FIELDS = (
    "latency_ms",
    "ttft_ms",
    "input_tokens",
    "output_tokens",
    "cached_input_tokens",
    "cache_hit_ratio",
    "prompt_eval_ms",
    "decode_ms",
    "tokens_per_second_prefill",
    "tokens_per_second_decode",
    "total_cost_usd",
    "canceled",
    "cancellation_latency_ms",
)


def _load_matrix_run_results(run, *, base_dir: Path) -> list[BenchmarkResult]:
    run_dir = _matrix_run_dir(run, base_dir=base_dir)
    if run_dir is None or not run_dir.exists():
        return []
    try:
        return load_results(run_dir)
    except ConfigError:
        return []


def _load_matrix_run_manifest(run, *, base_dir: Path) -> RunManifest | None:
    run_dir = _matrix_run_dir(run, base_dir=base_dir)
    if run_dir is None or not run_dir.exists():
        return None
    try:
        return load_manifest(run_dir)
    except ConfigError:
        return None


def _matrix_model_architecture(model: str, manifest: RunManifest | None) -> str:
    if manifest is not None and manifest.model_metadata.architecture:
        return manifest.model_metadata.architecture
    normalized = model.lower()
    if "qwen" in normalized and "3.6" in normalized and "27" in normalized:
        return "qwen3.6-27b-dense"
    if "gemma" in normalized and "4" in normalized and "31" in normalized:
        return "gemma-4-31b-dense"
    return "unknown"


def _matrix_model_quantization(manifest: RunManifest | None) -> str:
    if manifest is not None and manifest.model_metadata.quantization:
        return manifest.model_metadata.quantization
    return "unknown"


def _matrix_run_dir(run, *, base_dir: Path) -> Path | None:
    for artifact in (run.results_path, run.summary_path, run.manifest_path):
        if not artifact:
            continue
        path = Path(artifact)
        resolved = path if path.is_absolute() else base_dir / path
        if resolved.name in {"results.jsonl", "summary.json", "manifest.json"}:
            return resolved.parent
    return None


def _matrix_scorecard_group_summary(entries: list[dict], *, key: str) -> list[dict]:
    buckets: dict[str, list[dict]] = {}
    for entry in entries:
        buckets.setdefault(str(entry.get(key) or "unknown"), []).append(entry)
    rows: list[dict] = []
    for name, grouped_entries in sorted(buckets.items()):
        total_cases = sum(int(entry["total_cases"] or 0) for entry in grouped_entries)
        passed = sum(int(entry["passed"] or 0) for entry in grouped_entries)
        failed = sum(int(entry["failed"] or 0) for entry in grouped_entries)
        rows.append(
            {
                key: name,
                "runs": len(grouped_entries),
                "failed_runs": sum(1 for entry in grouped_entries if entry["ok"] is not True),
                "completed_runs": sum(1 for entry in grouped_entries if entry.get("run_id")),
                "result_artifacts_loaded": sum(1 for entry in grouped_entries if entry["result_artifacts_loaded"]),
                "total_cases": total_cases,
                "passed": passed,
                "failed": failed,
                "pass_rate_percent": _percent_value(passed, total_cases),
                "avg_latency_ms": _average([entry["avg_latency_ms"] for entry in grouped_entries]),
                "avg_ttft_ms": _average([entry["avg_ttft_ms"] for entry in grouped_entries]),
                "avg_cache_hit_ratio": _average([entry["avg_cache_hit_ratio"] for entry in grouped_entries]),
                "avg_prefill_tokens_per_second": _average(
                    [entry["avg_prefill_tokens_per_second"] for entry in grouped_entries]
                ),
                "avg_decode_tokens_per_second": _average(
                    [entry["avg_decode_tokens_per_second"] for entry in grouped_entries]
                ),
                "telemetry_completeness_percent": _average(
                    [entry["telemetry_completeness_percent"] for entry in grouped_entries]
                ),
                "invalid_tool_call_count": sum(int(entry["invalid_tool_call_count"] or 0) for entry in grouped_entries),
                "tool_parser_repair_cases": sum(int(entry["tool_parser_repair_cases"] or 0) for entry in grouped_entries),
                "tool_parser_repairs_valid": sum(int(entry["tool_parser_repairs_valid"] or 0) for entry in grouped_entries),
                "tool_parser_repair_valid_rate_percent": _percent_value(
                    sum(int(entry["tool_parser_repairs_valid"] or 0) for entry in grouped_entries),
                    sum(int(entry["tool_parser_repair_cases"] or 0) for entry in grouped_entries),
                ),
                "judge_rubric_cases": sum(int(entry["judge_rubric_cases"] or 0) for entry in grouped_entries),
                "judge_verdicts_valid": sum(int(entry["judge_verdicts_valid"] or 0) for entry in grouped_entries),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            -(row["pass_rate_percent"] if row["pass_rate_percent"] is not None else -1),
            row["avg_latency_ms"] if row["avg_latency_ms"] is not None else float("inf"),
            str(row[key]),
        ),
    )


def _available_telemetry_fields(results: list[BenchmarkResult]) -> list[str]:
    available: list[str] = []
    for field in _SCORECARD_TELEMETRY_FIELDS:
        if any(getattr(result, field) is not None for result in results):
            available.append(field)
    return available


_TELEMETRY_QUALITY_ORDER = (
    "native",
    "measured",
    "inferred",
    "conditional",
    "raw_provenance",
    "unknown",
    "unavailable",
)


def _telemetry_quality_counts(results: list[BenchmarkResult]) -> dict[str, int]:
    counts = {quality: 0 for quality in _TELEMETRY_QUALITY_ORDER}
    for result in results:
        quality_map = getattr(result, "telemetry_quality", None) or {}
        for field in _SCORECARD_TELEMETRY_FIELDS:
            if getattr(result, field) is None:
                continue
            quality = str(quality_map.get(field) or "unknown")
            if quality not in counts:
                quality = "unknown"
            counts[quality] += 1
    return {quality: count for quality, count in counts.items() if count}


def _telemetry_comparison_guidance(results: list[BenchmarkResult]) -> dict[str, int]:
    guidance_counts: dict[str, int] = {}
    for result in results:
        readiness = getattr(result, "telemetry_comparison_readiness", None) or {}
        guidance = readiness.get("guidance") if isinstance(readiness, dict) else None
        if isinstance(guidance, list):
            guidance_values = guidance
        elif guidance:
            guidance_values = [guidance]
        else:
            guidance_values = []
        for value in guidance_values:
            label = str(value)
            guidance_counts[label] = guidance_counts.get(label, 0) + 1
    return dict(sorted(guidance_counts.items()))


def _telemetry_stats_comparability(results: list[BenchmarkResult]) -> dict[str, Any]:
    profile_counts: dict[str, int] = {}
    guidance_counts: dict[str, int] = {}
    requires_labeling_count = 0
    for result in results:
        profile = getattr(result, "stats_profile", None)
        if profile:
            label = str(profile)
            profile_counts[label] = profile_counts.get(label, 0) + 1
        comparability = getattr(result, "telemetry_stats_comparability", None) or {}
        if bool(comparability.get("requires_labeling")):
            requires_labeling_count += 1
        guidance = comparability.get("guidance") if isinstance(comparability, dict) else None
        if guidance:
            guidance_label = str(guidance)
            guidance_counts[guidance_label] = guidance_counts.get(guidance_label, 0) + 1
    return {
        "profiles": dict(sorted(profile_counts.items())),
        "guidance_counts": dict(sorted(guidance_counts.items())),
        "requires_labeling_count": requires_labeling_count,
    }


def _telemetry_quality_summary(entries: list[dict]) -> dict:
    counts = {quality: 0 for quality in _TELEMETRY_QUALITY_ORDER}
    guidance_counts: dict[str, int] = {}
    entries_with_advisory_quality = 0
    entries_with_unknown_quality = 0
    entries_with_comparison_guidance = 0
    for entry in entries:
        entry_counts = entry.get("telemetry_quality_counts") or {}
        for quality, count in entry_counts.items():
            key = quality if quality in counts else "unknown"
            counts[key] += int(count or 0)
        if any(int(entry_counts.get(quality) or 0) for quality in ("inferred", "conditional", "raw_provenance")):
            entries_with_advisory_quality += 1
        if any(int(entry_counts.get(quality) or 0) for quality in ("unknown", "unavailable")):
            entries_with_unknown_quality += 1
        entry_guidance = entry.get("telemetry_comparison_guidance") or {}
        if entry_guidance:
            entries_with_comparison_guidance += 1
        for guidance, count in entry_guidance.items():
            guidance_counts[str(guidance)] = guidance_counts.get(str(guidance), 0) + int(count or 0)
    return {
        "quality_counts": {quality: count for quality, count in counts.items() if count},
        "guidance_counts": dict(sorted(guidance_counts.items())),
        "entries_with_advisory_quality": entries_with_advisory_quality,
        "entries_with_unknown_quality": entries_with_unknown_quality,
        "entries_with_comparison_guidance": entries_with_comparison_guidance,
    }


def _stats_comparability_summary(entries: list[dict]) -> dict:
    profile_counts: dict[str, int] = {}
    guidance_counts: dict[str, int] = {}
    entries_requiring_labeling = 0
    for entry in entries:
        for profile, count in (entry.get("stats_profiles") or {}).items():
            profile_counts[str(profile)] = profile_counts.get(str(profile), 0) + int(count or 0)
        entry_guidance = entry.get("stats_comparability_guidance") or {}
        if entry.get("stats_comparability_requires_labeling"):
            entries_requiring_labeling += 1
        for guidance, count in entry_guidance.items():
            guidance_counts[str(guidance)] = guidance_counts.get(str(guidance), 0) + int(count or 0)
    return {
        "schema_version": "agentblaster.scorecard-stats-comparability.v1",
        "profile_counts": dict(sorted(profile_counts.items())),
        "guidance_counts": dict(sorted(guidance_counts.items())),
        "entries_requiring_labeling": entries_requiring_labeling,
    }


def _scorecard_concurrency_evidence(entries: list[dict]) -> dict:
    levels = sorted(
        {
            int(level)
            for level in (_scorecard_number(entry.get("concurrency")) for entry in entries)
            if level is not None
        }
    )
    queue_values = [
        value for value in (_scorecard_number(entry.get("avg_queue_ms")) for entry in entries) if value is not None
    ]
    rate_limit_values = [
        value
        for value in (_scorecard_number(entry.get("avg_rate_limit_wait_ms")) for entry in entries)
        if value is not None
    ]
    artifact_loaded_count = sum(1 for entry in entries if entry.get("result_artifacts_loaded"))
    max_queue = max(queue_values) if queue_values else None
    max_rate_limit = max(rate_limit_values) if rate_limit_values else None
    if not entries:
        guidance = "no-scorecard-entries-available"
    elif not levels:
        guidance = "concurrency-not-reported-by-matrix-summary"
    elif len(levels) < 2:
        guidance = "single-concurrency-level-advisory-only"
    elif (max_queue is not None and max_queue > 0) or (max_rate_limit is not None and max_rate_limit > 0):
        guidance = "review-queue-and-rate-limit-pressure-before-publication"
    else:
        guidance = "concurrency-evidence-ready-when-release-gates-pass"
    return {
        "schema_version": "agentblaster.scorecard-concurrency-evidence.v1",
        "entry_count": len(entries),
        "artifact_loaded_count": artifact_loaded_count,
        "concurrency_levels": levels,
        "multi_level": len(levels) > 1,
        "max_concurrency": max(levels) if levels else None,
        "max_avg_queue_ms": max_queue,
        "max_avg_rate_limit_wait_ms": max_rate_limit,
        "highest_queue_wait_entries": _top_scorecard_concurrency_entries(entries, "avg_queue_ms"),
        "highest_rate_limit_wait_entries": _top_scorecard_concurrency_entries(entries, "avg_rate_limit_wait_ms"),
        "guidance": guidance,
    }


def _top_scorecard_concurrency_entries(entries: list[dict], metric_key: str) -> list[dict]:
    rows: list[dict] = []
    for entry in entries:
        value = _scorecard_number(entry.get(metric_key))
        if value is None:
            continue
        rows.append(
            {
                "engine": entry.get("engine"),
                "provider": entry.get("provider"),
                "model": entry.get("model"),
                "suite": entry.get("suite"),
                "run_id": entry.get("run_id"),
                "concurrency": entry.get("concurrency"),
                "rank_metric": metric_key,
                "rank_value": value,
                "pass_rate_percent": entry.get("pass_rate_percent"),
                "avg_latency_ms": entry.get("avg_latency_ms"),
                "avg_queue_ms": entry.get("avg_queue_ms"),
                "avg_rate_limit_wait_ms": entry.get("avg_rate_limit_wait_ms"),
            }
        )
    rows.sort(key=lambda row: (-(row["rank_value"] or 0), str(row.get("engine") or ""), str(row.get("suite") or "")))
    return rows[:3]


def _scorecard_number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _telemetry_quality_summary_text(summary: dict) -> str:
    counts = summary.get("quality_counts") or {}
    if not counts:
        return "none"
    parts = [f"{quality}={count}" for quality, count in counts.items()]
    comparison_guidance_count = summary.get("entries_with_comparison_guidance") or 0
    if comparison_guidance_count:
        parts.append(f"guidance_entries={comparison_guidance_count}")
    return ", ".join(parts)


def _scorecard_concurrency_evidence_text(evidence: dict) -> str:
    levels = evidence.get("concurrency_levels") or []
    levels_text = ",".join(str(level) for level in levels) if levels else "n/a"
    return (
        f"levels={levels_text}, "
        f"max_queue={_metric_with_unit(evidence.get('max_avg_queue_ms'), 'ms')}, "
        f"max_rate_wait={_metric_with_unit(evidence.get('max_avg_rate_limit_wait_ms'), 'ms')}, "
        f"guidance={evidence.get('guidance') or 'n/a'}"
    )


def _scorecard_telemetry_card_text(summary: dict) -> str:
    counts = summary.get("quality_counts") or {}
    if not counts:
        return "none"
    return " ".join(f"{quality}={count}" for quality, count in list(counts.items())[:3])


def _scorecard_concurrency_card_text(evidence: dict) -> str:
    levels = evidence.get("concurrency_levels") or []
    levels_text = ",".join(str(level) for level in levels) if levels else "n/a"
    return f"levels={levels_text} queue={_metric_with_unit(evidence.get('max_avg_queue_ms'), 'ms')}"


def _scenario_names(results: list[BenchmarkResult]) -> list[str]:
    return sorted({result.scenario or "unspecified" for result in results})


def _empty_matrix_metrics() -> dict[str, float | int | None]:
    return {
        "avg_latency_ms": None,
        "avg_ttft_ms": None,
        "avg_queue_ms": None,
        "avg_rate_limit_wait_ms": None,
        "avg_cache_hit_ratio": None,
        "avg_prefill_tokens_per_second": None,
        "avg_decode_tokens_per_second": None,
        "total_cost_usd": None,
        "tool_calls_emitted": None,
        "tool_calls_valid": None,
        "invalid_tool_call_count": None,
        "tool_parser_repair_cases": None,
        "tool_parser_repairs_valid": None,
        "tool_loop_cases": None,
        "tool_loop_rounds": None,
        "tool_loop_tool_call_count": None,
        "judge_rubric_cases": None,
        "judge_verdicts_valid": None,
        "judge_verdict_valid_rate_percent": None,
        "cancellation_cases": None,
        "cancellations_observed": None,
        "avg_cancellation_latency_ms": None,
    }


def _matrix_scorecard_markdown_row(row: dict) -> str:
    return (
        f"| {row['rank']} "
        f"| {_markdown_cell(row['engine'])} "
        f"| {_markdown_cell(row['provider'])} "
        f"| {_markdown_cell(row['model'])} "
        f"| {_markdown_cell(row['suite'])} "
        f"| {row['status']} "
        f"| {_format_metric(row['pass_rate_percent'])} "
        f"| {row['passed']}/{row['total_cases']} "
        f"| {_format_metric(row['avg_queue_ms'])} "
        f"| {_format_metric(row['avg_rate_limit_wait_ms'])} "
        f"| {_format_metric(row['avg_latency_ms'])} "
        f"| {_format_metric(row['avg_ttft_ms'])} "
        f"| {_format_metric(row['avg_decode_tokens_per_second'])} "
        f"| {_format_metric(row['avg_cache_hit_ratio'])} "
        f"| {row['judge_verdicts_valid']}/{row['judge_rubric_cases']} "
        f"| {row['cancellations_observed']}/{row['cancellation_cases']} "
        f"| {_format_metric(row['total_cost_usd'])} "
        f"| {_format_metric(row['telemetry_completeness_percent'])} "
        f"| `{_markdown_cell(row['run_id'] or '-')}` |"
    )


def _matrix_scorecard_group_markdown_row(row: dict, key: str) -> str:
    return (
        f"| {_markdown_cell(row.get(key) or 'unknown')} "
        f"| {row['runs']} "
        f"| {row['failed_runs']} "
        f"| {row['total_cases']} "
        f"| {row['passed']} "
        f"| {row['failed']} "
        f"| {_format_metric(row['pass_rate_percent'])} "
        f"| {_format_metric(row['avg_latency_ms'])} "
        f"| {_format_metric(row['avg_ttft_ms'])} "
        f"| {_format_metric(row['avg_decode_tokens_per_second'])} "
        f"| {_format_metric(row['avg_cache_hit_ratio'])} "
        f"| {row['judge_verdicts_valid']}/{row['judge_rubric_cases']} "
        f"| {_format_metric(row['telemetry_completeness_percent'])} |"
    )


def _matrix_scorecard_html_row(row: dict) -> str:
    status_class = "pass" if row["ok"] else "fail"
    return f"""<tr>
  <td>{row['rank']}</td>
  <td>{html.escape(row['engine'])}</td>
  <td>{html.escape(row['provider'])}</td>
  <td>{html.escape(row['model'])}</td>
  <td>{html.escape(row['suite'])}</td>
  <td class="{status_class}">{html.escape(row['status'])}</td>
  <td>{_cell(row['pass_rate_percent'])}</td>
  <td>{row['passed']}/{row['total_cases']}</td>
  <td>{_cell(row['avg_queue_ms'])}</td>
  <td>{_cell(row['avg_rate_limit_wait_ms'])}</td>
  <td>{_cell(row['avg_latency_ms'])}</td>
  <td>{_cell(row['avg_ttft_ms'])}</td>
  <td>{_cell(row['avg_decode_tokens_per_second'])}</td>
  <td>{_cell(row['avg_cache_hit_ratio'])}</td>
  <td>{row['judge_verdicts_valid']}/{row['judge_rubric_cases']}</td>
  <td>{row['cancellations_observed']}/{row['cancellation_cases']}</td>
  <td>{_cell(row['total_cost_usd'])}</td>
  <td>{_cell(row['telemetry_completeness_percent'])}</td>
  <td><code>{html.escape(row['run_id'] or '-')}</code></td>
</tr>"""


def _matrix_scorecard_group_html_row(row: dict, key: str) -> str:
    return f"""<tr>
  <td>{html.escape(str(row.get(key) or 'unknown'))}</td>
  <td>{row['runs']}</td>
  <td>{row['failed_runs']}</td>
  <td>{row['total_cases']}</td>
  <td>{row['passed']}</td>
  <td>{row['failed']}</td>
  <td>{_cell(row['pass_rate_percent'])}</td>
  <td>{_cell(row['avg_latency_ms'])}</td>
  <td>{_cell(row['avg_ttft_ms'])}</td>
  <td>{_cell(row['avg_decode_tokens_per_second'])}</td>
  <td>{_cell(row['avg_cache_hit_ratio'])}</td>
  <td>{row['judge_verdicts_valid']}/{row['judge_rubric_cases']}</td>
  <td>{_cell(row['telemetry_completeness_percent'])}</td>
</tr>"""


def _matrix_scorecard_svg_leader_row(row: dict, *, y: int) -> str:
    status_color = "#156c43" if row["ok"] else "#9b2721"
    return f"""<g transform="translate(74 {y})">
  <rect width="560" height="46" rx="16" fill="#fffdf6" opacity="0.86" stroke="#d7cbb7"/>
  <text x="18" y="29" class="row-main">#{row['rank']} {_svg_escape(row['engine'])}</text>
  <text x="208" y="29" class="row-sub">{_svg_escape(row['suite'])}</text>
  <text x="374" y="29" class="row-sub">{_format_metric(row['pass_rate_percent'])}%</text>
  <text x="480" y="29" class="row-sub">{_format_metric(row['avg_latency_ms'])} ms</text>
  <circle cx="536" cy="23" r="7" fill="{status_color}"/>
</g>"""


def _matrix_scorecard_svg_group_row(row: dict, *, y: int) -> str:
    name = row.get("model_architecture") or row.get("quantization") or "unknown"
    return f"""<g transform="translate(682 {y})">
  <rect width="448" height="40" rx="14" fill="#fffdf6" opacity="0.82" stroke="#d7cbb7"/>
  <text x="16" y="26" class="row-main">{_svg_escape(name)}</text>
  <text x="280" y="26" class="row-sub">{row['passed']}/{row['total_cases']}</text>
  <text x="356" y="26" class="row-sub">{_format_metric(row['avg_decode_tokens_per_second'])} tok/s</text>
</g>"""


def load_matrix_execution_summary(summary_json: Path) -> MatrixExecutionSummary:
    if not summary_json.exists():
        raise ConfigError(f"missing matrix summary: {summary_json}")
    try:
        return MatrixExecutionSummary.model_validate_json(summary_json.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise ConfigError(f"invalid matrix summary at {summary_json}: {exc}") from exc


def write_matrix_json_report(summary: MatrixExecutionSummary, output_dir: Path, stem: str) -> Path:
    payload = matrix_publication_payload(summary)
    path = output_dir / f"{stem}-matrix-report.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_matrix_pdf_report(summary: MatrixExecutionSummary, output_dir: Path, stem: str) -> Path:
    payload = matrix_publication_payload(summary)
    scorecard = payload["scorecard"]
    lines = [
        "AgentBlaster Matrix Report",
        "",
        f"Matrix: {summary.matrix_name}",
        f"Source: {summary.matrix_path}",
        f"Created: {summary.created_at}",
        f"Runs: {summary.completed_runs}/{summary.total_runs} completed",
        f"Attempted runs: {summary.attempted_runs}",
        f"Failed runs: {summary.failed_runs}",
        f"Cases: {scorecard['passed_cases']}/{scorecard['total_cases']} passed",
        f"Pass rate: {_format_percent(scorecard['passed_cases'], scorecard['total_cases']) or 'n/a'}",
        "",
        "Provider summary",
    ]
    for row in payload["provider_summary"][:8]:
        lines.append(
            f"{row['provider']}: runs={row['runs']}, failed_runs={row['failed_runs']}, "
            f"cases={row['passed']}/{row['total_cases']}, pass_rate={_format_metric(row['pass_rate_percent'])}%"
        )
    if payload["model_summary"]:
        lines.extend(["", "Model summary"])
        for row in payload["model_summary"][:8]:
            lines.append(
                f"{row['model']}: runs={row['runs']}, failed_runs={row['failed_runs']}, "
                f"cases={row['passed']}/{row['total_cases']}, pass_rate={_format_metric(row['pass_rate_percent'])}%"
            )
    failed_entries = [run for run in summary.runs if not run.ok]
    if failed_entries:
        lines.extend(["", "Failed or incomplete entries"])
        for run in failed_entries[:8]:
            lines.append(f"#{run.index} {run.engine} / {run.model} / {run.suite}: {run.error_message or 'failed'}")
    lines.extend(
        [
            "",
            "Security",
            "This PDF is derived from the matrix execution summary and aggregate report payload.",
            "It excludes raw provider payloads, raw traces, API keys, request headers, and per-case raw responses.",
        ]
    )
    path = output_dir / f"{stem}-matrix-report.pdf"
    path.write_bytes(_simple_pdf_bytes(lines))
    return path


def write_matrix_markdown_report(summary: MatrixExecutionSummary, output_dir: Path, stem: str) -> Path:
    payload = matrix_publication_payload(summary)
    rows = "\n".join(_matrix_markdown_row(run) for run in summary.runs)
    provider_rows = "\n".join(_aggregate_markdown_row(row) for row in payload["provider_summary"])
    model_rows = "\n".join(_aggregate_markdown_row(row) for row in payload["model_summary"])
    report = f"""# AgentBlaster Matrix Report

## Executive Summary

| Field | Value |
| --- | --- |
| Matrix | `{_markdown_cell(summary.matrix_name)}` |
| Source | `{_markdown_cell(summary.matrix_path)}` |
| Created | `{_markdown_cell(summary.created_at)}` |
| Runs | {summary.completed_runs}/{summary.total_runs} completed |
| Attempted runs | {summary.attempted_runs} |
| Failed runs | {summary.failed_runs} |
| Cases | {payload["scorecard"]["passed_cases"]}/{payload["scorecard"]["total_cases"]} passed |
| Pass rate | {_format_percent(payload["scorecard"]["passed_cases"], payload["scorecard"]["total_cases"])} |

## Provider Summary

| Provider | Runs | Failed runs | Cases | Passed | Failed | Pass rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
{provider_rows}

## Model Summary

| Model | Runs | Failed runs | Cases | Passed | Failed | Pass rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
{model_rows}

## Run Entries

| # | Engine | Target | Provider | Model | Suite | Run | Cases | Status | Summary/Error |
| ---: | --- | --- | --- | --- | --- | --- | ---: | --- | --- |
{rows}
"""
    path = output_dir / f"{stem}-matrix-report.md"
    path.write_text(report, encoding="utf-8")
    return path


def write_matrix_html_report(summary: MatrixExecutionSummary, output_dir: Path, stem: str) -> Path:
    payload = matrix_publication_payload(summary)
    run_rows = "\n".join(_matrix_html_row(run) for run in summary.runs)
    provider_rows = "\n".join(_aggregate_html_row(row) for row in payload["provider_summary"])
    model_rows = "\n".join(_aggregate_html_row(row) for row in payload["model_summary"])
    pass_rate = _format_percent(payload["scorecard"]["passed_cases"], payload["scorecard"]["total_cases"]) or "n/a"
    report = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>AgentBlaster Matrix Report {html.escape(summary.matrix_name)}</title>
  <style>
    body {{ font-family: Avenir Next, Trebuchet MS, sans-serif; margin: 40px; color: #172026; background: #fbf7ef; }}
    header {{ border-bottom: 1px solid #d8c7ab; margin-bottom: 24px; padding-bottom: 16px; }}
    h1, h2 {{ font-family: Iowan Old Style, Georgia, serif; color: #111713; }}
    h1 {{ margin: 0 0 8px; font-size: 48px; letter-spacing: -1px; }}
    .meta {{ color: #52616b; line-height: 1.5; }}
    .score {{ display: flex; flex-wrap: wrap; gap: 16px; margin: 24px 0; }}
    .metric {{ background: #fffdf6; border: 1px solid #d8c7ab; border-radius: 14px; padding: 16px 20px; min-width: 130px; }}
    .metric strong {{ display: block; font-size: 30px; color: #111713; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 28px; background: #fffdf6; }}
    th, td {{ border-bottom: 1px solid #e7dccb; padding: 10px; text-align: left; vertical-align: top; }}
    th {{ background: #efe2cd; color: #4a3015; }}
    .pass {{ color: #0b6b3a; font-weight: 700; }}
    .fail {{ color: #a52222; font-weight: 700; }}
    .muted {{ color: #66737d; }}
    code {{ white-space: nowrap; }}
  </style>
</head>
<body>
  <header>
    <h1>AgentBlaster Matrix Report</h1>
    <div class="meta">
      Matrix: {html.escape(summary.matrix_name)}<br>
      Source: {html.escape(summary.matrix_path)}<br>
      Created: {html.escape(summary.created_at)}<br>
      Description: {html.escape(summary.description)}
    </div>
  </header>
  <section class="score">
    <div class="metric"><span>Runs</span><strong>{summary.completed_runs}/{summary.total_runs}</strong></div>
    <div class="metric"><span>Attempted</span><strong>{summary.attempted_runs}</strong></div>
    <div class="metric"><span>Failed runs</span><strong>{summary.failed_runs}</strong></div>
    <div class="metric"><span>Cases</span><strong>{payload["scorecard"]["passed_cases"]}/{payload["scorecard"]["total_cases"]}</strong></div>
    <div class="metric"><span>Pass rate</span><strong>{html.escape(pass_rate)}</strong></div>
  </section>
  <h2>Provider Summary</h2>
  <table>
    <thead><tr><th>Provider</th><th>Runs</th><th>Failed runs</th><th>Cases</th><th>Passed</th><th>Failed</th><th>Pass rate</th></tr></thead>
    <tbody>{provider_rows}</tbody>
  </table>
  <h2>Model Summary</h2>
  <table>
    <thead><tr><th>Model</th><th>Runs</th><th>Failed runs</th><th>Cases</th><th>Passed</th><th>Failed</th><th>Pass rate</th></tr></thead>
    <tbody>{model_rows}</tbody>
  </table>
  <h2>Run Entries</h2>
  <table>
    <thead><tr><th>#</th><th>Engine</th><th>Target</th><th>Provider</th><th>Model</th><th>Suite</th><th>Run</th><th>Cases</th><th>Status</th><th>Summary/Error</th></tr></thead>
    <tbody>{run_rows}</tbody>
  </table>
</body>
</html>
"""
    path = output_dir / f"{stem}-matrix-report.html"
    path.write_text(report, encoding="utf-8")
    return path


def matrix_publication_payload(summary: MatrixExecutionSummary) -> dict:
    total_cases = sum(run.total_cases for run in summary.runs)
    passed_cases = sum(run.passed for run in summary.runs)
    failed_cases = sum(run.failed for run in summary.runs)
    return {
        "report_type": "agentblaster-matrix-report-v1",
        "matrix": {
            "name": summary.matrix_name,
            "path": summary.matrix_path,
            "description": summary.description,
            "created_at": summary.created_at,
            "schema_version": summary.schema_version,
            "dry_run": summary.dry_run,
            "continue_on_error": summary.continue_on_error,
            "total_runs": summary.total_runs,
            "attempted_runs": summary.attempted_runs,
            "completed_runs": summary.completed_runs,
            "failed_runs": summary.failed_runs,
        },
        "scorecard": {
            "total_cases": total_cases,
            "passed_cases": passed_cases,
            "failed_cases": failed_cases,
            "pass_rate_percent": _percent_value(passed_cases, total_cases),
            "engine_targets": _matrix_engine_targets(summary),
        },
        "provider_summary": _matrix_aggregate(summary, key="provider"),
        "model_summary": _matrix_aggregate(summary, key="model"),
        "runs": [run.model_dump(mode="json") for run in summary.runs],
        "security": {
            "contains_raw_secrets": False,
            "contains_raw_provider_payloads": False,
            "notes": "Matrix reports are derived from run summaries and artifact paths. They exclude raw provider responses, raw traces, and API keys.",
        },
    }


def _matrix_engine_targets(summary: MatrixExecutionSummary) -> list[dict]:
    targets: dict[str, dict] = {}
    for run in summary.runs:
        target = run.engine_target
        if not isinstance(target, dict) or not target.get("id"):
            continue
        targets[str(target["id"])] = {
            "id": target.get("id"),
            "display_name": target.get("display_name"),
            "primary_scoring_contract": (
                target.get("standardization", {}).get("primary_scoring_contract")
                if isinstance(target.get("standardization"), dict)
                else None
            ),
        }
    return [targets[key] for key in sorted(targets)]


def _matrix_run_engine_target_id(run) -> str | None:
    target = getattr(run, "engine_target", None)
    return _engine_target_id(target)


def _engine_target_id(target) -> str | None:
    if isinstance(target, dict) and target.get("id"):
        return str(target["id"])
    return None


def _matrix_aggregate(summary: MatrixExecutionSummary, *, key: str) -> list[dict]:
    buckets: dict[str, list] = {}
    for run in summary.runs:
        buckets.setdefault(str(getattr(run, key)), []).append(run)
    rows: list[dict] = []
    for name, runs in sorted(buckets.items()):
        total_cases = sum(run.total_cases for run in runs)
        passed = sum(run.passed for run in runs)
        failed = sum(run.failed for run in runs)
        rows.append(
            {
                key: name,
                "runs": len(runs),
                "failed_runs": sum(1 for run in runs if not run.ok),
                "total_cases": total_cases,
                "passed": passed,
                "failed": failed,
                "pass_rate_percent": _percent_value(passed, total_cases),
            }
        )
    return rows


def _matrix_html_row(run) -> str:
    status_class = "pass" if run.ok else "fail"
    status = "pass" if run.ok else "fail"
    run_id = run.run_id or "-"
    summary_or_error = (
        f"<code>{html.escape(run.summary_path)}</code>"
        if run.summary_path
        else f"<span class=\"muted\">{html.escape(run.error_message or 'no summary artifact')}</span>"
    )
    return f"""<tr>
  <td>{run.index}</td>
  <td>{html.escape(run.engine)}</td>
  <td>{html.escape(_matrix_run_engine_target_id(run) or '-')}</td>
  <td>{html.escape(run.provider)}</td>
  <td>{html.escape(run.model)}</td>
  <td>{html.escape(run.suite)}</td>
  <td><code>{html.escape(run_id)}</code></td>
  <td>{run.passed}/{run.total_cases}</td>
  <td class="{status_class}">{status}</td>
  <td>{summary_or_error}</td>
</tr>"""


def _matrix_markdown_row(run) -> str:
    status = "pass" if run.ok else "fail"
    run_id = run.run_id or "-"
    summary_or_error = run.summary_path or run.error_message or "no summary artifact"
    return (
        f"| {run.index} "
        f"| {_markdown_cell(run.engine)} "
        f"| {_markdown_cell(_matrix_run_engine_target_id(run) or '-')} "
        f"| {_markdown_cell(run.provider)} "
        f"| {_markdown_cell(run.model)} "
        f"| {_markdown_cell(run.suite)} "
        f"| `{_markdown_cell(run_id)}` "
        f"| {run.passed}/{run.total_cases} "
        f"| {status} "
        f"| `{_markdown_cell(summary_or_error)}` |"
    )


def _aggregate_html_row(row: dict) -> str:
    name = row.get("provider") or row.get("model") or ""
    return f"""<tr>
  <td>{html.escape(str(name))}</td>
  <td>{row["runs"]}</td>
  <td>{row["failed_runs"]}</td>
  <td>{row["total_cases"]}</td>
  <td>{row["passed"]}</td>
  <td>{row["failed"]}</td>
  <td>{_cell(row["pass_rate_percent"])}</td>
</tr>"""


def _aggregate_markdown_row(row: dict) -> str:
    name = row.get("provider") or row.get("model") or ""
    return (
        f"| {_markdown_cell(name)} "
        f"| {row['runs']} "
        f"| {row['failed_runs']} "
        f"| {row['total_cases']} "
        f"| {row['passed']} "
        f"| {row['failed']} "
        f"| {_format_metric(row['pass_rate_percent'])} |"
    )


def _result_row(result: BenchmarkResult) -> str:
    status_class = "pass" if result.ok else "fail"
    status = "pass" if result.ok else "fail"
    return f"""<tr>
  <td>{html.escape(result.case_id)}</td>
  <td>{html.escape(result.scenario or "")}</td>
  <td class="{status_class}">{status}</td>
  <td>{_cell(result.queue_ms)}</td>
  <td>{_cell(result.rate_limit_wait_ms)}</td>
  <td>{_cell(result.latency_ms)}</td>
  <td>{_cell(result.ttft_ms)}</td>
  <td>{_cell(result.input_tokens)}</td>
  <td>{_cell(result.cached_input_tokens)}</td>
  <td>{_cell(result.cache_hit_ratio)}</td>
  <td>{_cell(result.output_tokens)}</td>
  <td>{_cell(result.total_cost_usd)}</td>
  <td>{_cell(result.total_tokens)}</td>
  <td>{_cell(result.tokens_per_second_prefill)}</td>
  <td>{_cell(result.tokens_per_second_decode)}</td>
  <td>{_cell(_tool_cell(result))}</td>
  <td>{_cell(result.structured_output_valid)}</td>
  <td>{_cell(result.judge_verdict_valid)}</td>
  <td>{_cell(result.finish_reason)}</td>
  <td>{html.escape(result.message)}</td>
</tr>"""


def _cell(value) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def _markdown_result_row(result: BenchmarkResult) -> str:
    status = "pass" if result.ok else "fail"
    return (
        f"| `{_markdown_cell(result.case_id)}` "
        f"| {_markdown_cell(result.scenario)} "
        f"| {status} "
        f"| {_format_metric(result.queue_ms)} "
        f"| {_format_metric(result.rate_limit_wait_ms)} "
        f"| {_format_metric(result.latency_ms)} "
        f"| {_format_metric(result.ttft_ms)} "
        f"| {_format_metric(result.input_tokens)} "
        f"| {_format_metric(result.cached_input_tokens)} "
        f"| {_format_metric(result.output_tokens)} "
        f"| {_format_metric(result.total_cost_usd)} "
        f"| {_format_metric(_tool_cell(result))} "
        f"| {_markdown_cell(result.judge_verdict_valid)} "
        f"| {_markdown_cell(result.finish_reason)} "
        f"| {_markdown_cell(result.message)} |"
    )


def _aggregate_metrics(results: list[BenchmarkResult]) -> dict[str, float | int | None]:
    judge_rubric_cases = sum(1 for result in results if result.judge_verdict_valid is not None)
    judge_verdicts_valid = sum(1 for result in results if result.judge_verdict_valid is True)
    return {
        "avg_latency_ms": _average([result.latency_ms for result in results]),
        "avg_ttft_ms": _average([result.ttft_ms for result in results]),
        "avg_queue_ms": _average([result.queue_ms for result in results]),
        "avg_rate_limit_wait_ms": _average([result.rate_limit_wait_ms for result in results]),
        "avg_cache_hit_ratio": _average([result.cache_hit_ratio for result in results]),
        "avg_prefill_tokens_per_second": _average([result.tokens_per_second_prefill for result in results]),
        "avg_decode_tokens_per_second": _average([result.tokens_per_second_decode for result in results]),
        "total_cost_usd": _sum_metric([result.total_cost_usd for result in results]),
        "tool_calls_emitted": sum(result.tool_calls_emitted or 0 for result in results),
        "tool_calls_valid": sum(result.tool_calls_valid or 0 for result in results),
        "invalid_tool_call_count": sum(result.invalid_tool_call_count or 0 for result in results),
        "tool_parser_repair_cases": sum(1 for result in results if result.tool_parser_repair_valid is not None),
        "tool_parser_repairs_valid": sum(1 for result in results if result.tool_parser_repair_valid is True),
        "tool_loop_cases": sum(1 for result in results if result.tool_loop_enabled is True),
        "tool_loop_rounds": sum(result.tool_loop_rounds or 0 for result in results),
        "tool_loop_tool_call_count": sum(result.tool_loop_tool_call_count or 0 for result in results),
        "judge_rubric_cases": judge_rubric_cases,
        "judge_verdicts_valid": judge_verdicts_valid,
        "judge_verdict_valid_rate_percent": _percent_value(judge_verdicts_valid, judge_rubric_cases),
        "cancellation_cases": sum(1 for result in results if result.cancel_after_ms is not None),
        "cancellations_observed": sum(1 for result in results if result.canceled is True),
        "avg_cancellation_latency_ms": _average([result.cancellation_latency_ms for result in results]),
    }


def _failure_class_summary(results: list[BenchmarkResult]) -> list[dict[str, int | str]]:
    counts: dict[str, int] = {}
    for result in results:
        if result.ok:
            continue
        key = result.failure_class or "unclassified"
        counts[key] = counts.get(key, 0) + 1
    return [{"failure_class": key, "count": value} for key, value in sorted(counts.items())]


def _combine_failure_class_summaries(summaries: list[list[dict]]) -> list[dict[str, int | str]]:
    counts: dict[str, int] = {}
    for summary in summaries:
        for item in summary:
            key = str(item.get("failure_class") or "unclassified")
            counts[key] = counts.get(key, 0) + int(item.get("count") or 0)
    return [{"failure_class": key, "count": value} for key, value in sorted(counts.items())]


def _combine_tool_loop_stop_summaries(summaries: list[list[dict]]) -> list[dict[str, int | str]]:
    counts: dict[str, int] = {}
    for summary in summaries:
        for item in summary:
            key = str(item.get("stop_reason") or item.get("reason") or "unknown")
            counts[key] = counts.get(key, 0) + int(item.get("count") or 0)
    return [
        {"stop_reason": key, "count": value}
        for key, value in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _tool_loop_stop_summary(results: list[BenchmarkResult]) -> list[dict[str, int | str]]:
    counts: dict[str, int] = {}
    for result in results:
        if not getattr(result, "tool_loop_enabled", False):
            continue
        reason = str(getattr(result, "tool_loop_stop_reason", "") or "").strip()
        if not reason:
            continue
        counts[reason] = counts.get(reason, 0) + 1
    return [
        {"stop_reason": key, "count": value}
        for key, value in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _failure_class_summary_text(summary: list[dict]) -> str:
    if not summary:
        return "none"
    return ", ".join(f"{item['failure_class']}={item['count']}" for item in summary)


def _tool_loop_stop_summary_text(summary: list[dict]) -> str:
    if not summary:
        return "none"
    return ", ".join(
        f"{item.get('stop_reason') or item.get('reason') or 'unknown'}={item.get('count', 0)}"
        for item in summary
    )


def _scenario_summary(results: list[BenchmarkResult]) -> list[dict[str, Any]]:
    buckets: dict[str, list[BenchmarkResult]] = {}
    for result in results:
        buckets.setdefault(result.scenario or "unspecified", []).append(result)
    summary: list[dict[str, Any]] = []
    for scenario, scenario_results in sorted(buckets.items()):
        summary.append(
            {
                "scenario": scenario,
                "total_cases": len(scenario_results),
                "passed": sum(1 for result in scenario_results if result.ok),
                "failed": sum(1 for result in scenario_results if not result.ok),
                "avg_latency_ms": _average([result.latency_ms for result in scenario_results]),
                "avg_ttft_ms": _average([result.ttft_ms for result in scenario_results]),
                "avg_decode_tokens_per_second": _average(
                    [result.tokens_per_second_decode for result in scenario_results]
                ),
            }
        )
    return summary


def _average(values: list[float | int | None]) -> float | None:
    numeric_values = [float(value) for value in values if value is not None]
    if not numeric_values:
        return None
    return round(sum(numeric_values) / len(numeric_values), 3)


def _sum_metric(values: list[float | int | None]) -> float | None:
    numeric_values = [float(value) for value in values if value is not None]
    if not numeric_values:
        return None
    return round(sum(numeric_values), 9)


def _svg_to_png(svg_path: Path, target: Path) -> None:
    try:
        import cairosvg  # type: ignore[import-not-found]
    except Exception as exc:
        raise ConfigError("png report-card export requires optional dependency: install agentblaster[reports]") from exc
    cairosvg.svg2png(url=str(svg_path), write_to=str(target), output_width=1200, output_height=630)


def _simple_pdf_bytes(lines: list[str]) -> bytes:
    wrapped_lines: list[str] = []
    for line in lines:
        if line == "":
            wrapped_lines.append("")
            continue
        wrapped_lines.extend(wrap(_pdf_text(line), width=92) or [""])
    visible_lines = wrapped_lines[:44]
    text_commands = ["BT", "/F1 12 Tf", "50 780 Td", "16 TL"]
    for index, line in enumerate(visible_lines):
        if index:
            text_commands.append("T*")
        text_commands.append(f"({_pdf_escape(line)}) Tj")
    text_commands.append("ET")
    stream = "\n".join(text_commands).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


def _pdf_text(value: object) -> str:
    return str(value).encode("ascii", "replace").decode("ascii")


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _format_metric(value) -> str:
    return "" if value is None else str(value)


def _format_percent(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return ""
    return f"{round((numerator / denominator) * 100, 1)}%"


def _percent_value(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round((numerator / denominator) * 100, 3)


def _publication_highlights(summary: RunSummary, metrics: dict[str, float | int | None]) -> list[dict[str, str]]:
    highlights = [
        {"label": "Pass rate", "value": _format_percent(summary.passed, summary.total_cases) or "n/a"},
        {"label": "Cases", "value": f"{summary.passed}/{summary.total_cases} passed"},
    ]
    if metrics["avg_latency_ms"] is not None:
        highlights.append({"label": "Average latency", "value": _metric_with_unit(metrics["avg_latency_ms"], "ms")})
    if metrics["avg_ttft_ms"] is not None:
        highlights.append({"label": "Average TTFT", "value": _metric_with_unit(metrics["avg_ttft_ms"], "ms")})
    if metrics["avg_decode_tokens_per_second"] is not None:
        highlights.append(
            {"label": "Average decode rate", "value": _metric_with_unit(metrics["avg_decode_tokens_per_second"], "tok/s")}
        )
    if metrics["avg_cache_hit_ratio"] is not None:
        highlights.append({"label": "Average cache hit", "value": _ratio_percent(metrics["avg_cache_hit_ratio"])})
    if metrics["total_cost_usd"] is not None:
        highlights.append({"label": "Estimated cost", "value": _usd_metric(metrics["total_cost_usd"])})
    if metrics.get("judge_rubric_cases"):
        highlights.append(
            {
                "label": "Judge verdicts",
                "value": f"{metrics['judge_verdicts_valid']}/{metrics['judge_rubric_cases']} valid",
            }
        )
    return highlights


def _publication_readiness(run_dir: Path, manifest: RunManifest, summary: RunSummary) -> dict[str, object]:
    blockers: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    artifact_requirements = [
        {"artifact": "summary.json", "purpose": "automation summary", "present": (run_dir / "summary.json").exists()},
        {"artifact": "report.html", "purpose": "human-readable report", "present": (run_dir / "report.html").exists()},
        {"artifact": "report.pdf", "purpose": "corporate review packet", "present": (run_dir / "report.pdf").exists()},
        {"artifact": "report-card.svg", "purpose": "media card or slide asset", "present": (run_dir / "report-card.svg").exists()},
        {"artifact": "integrity.json", "purpose": "artifact checksum manifest", "present": (run_dir / "integrity.json").exists()},
    ]
    if manifest.raw_trace_mode is RawTraceMode.FULL:
        blockers.append(
            {
                "code": "full_raw_traces",
                "message": "Full raw traces were enabled; generate a redacted/off run or exclude raw artifacts before publication.",
            }
        )
    if manifest.retention_policy.classification == "restricted":
        blockers.append(
            {
                "code": "restricted_classification",
                "message": "Retention classification is restricted; external publication requires reclassification or explicit approval.",
            }
        )
    if manifest.retention_policy.classification in {"internal", "confidential"}:
        warnings.append(
            {
                "code": "non_public_classification",
                "message": f"Retention classification is {manifest.retention_policy.classification}; external publication needs review.",
            }
        )
    if summary.failed:
        warnings.append(
            {
                "code": "failed_cases_present",
                "message": f"{summary.failed} failed case(s) are present; claims should disclose failure classes and scope.",
            }
        )
    missing_artifacts = [item["artifact"] for item in artifact_requirements if not item["present"]]
    if missing_artifacts:
        warnings.append(
            {
                "code": "missing_publication_artifacts",
                "message": "Generate companion artifacts before packaging: " + ", ".join(str(item) for item in missing_artifacts),
            }
        )
    status = "blocked" if blockers else "review-required" if warnings else "ready"
    return {
        "schema_version": "agentblaster.publication-readiness.v1",
        "status": status,
        "ready_for_external_publication": status == "ready",
        "ready_for_internal_review": not blockers,
        "blocker_count": len(blockers),
        "warning_count": len(warnings),
        "blockers": blockers,
        "warnings": warnings,
        "artifact_requirements": artifact_requirements,
        "recommended_next_steps": [
            "Generate html, publication, card, and pdf report formats before sharing externally.",
            "Create a publication bundle so consumers receive the structured manifest and visual assets together.",
            "Run the redaction scanner on the publication bundle before external distribution.",
        ],
    }


def _metric_with_unit(value: float | None, unit: str) -> str:
    if value is None:
        return "n/a"
    return f"{value} {unit}"


def _ratio_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{round(value * 100, 1)}%"


def _usd_metric(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"${value:.6f}".rstrip("0").rstrip(".")


def _svg_metric(x: int, y: int, label: str, value: str) -> str:
    return f"""<g transform="translate({x} {y})">
      <rect width="224" height="104" rx="22" ry="22" fill="#fffdf6" opacity="0.82" stroke="#d7cbb7"/>
      <text x="24" y="34" class="metric-label">{_svg_escape(label)}</text>
      <text x="24" y="82" class="metric-value">{_svg_escape(value)}</text>
    </g>"""


def _svg_escape(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _markdown_cell(value) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")


def _tool_cell(result: BenchmarkResult) -> str:
    if result.tool_calls_emitted is None:
        return ""
    if result.tool_calls_valid is None:
        return str(result.tool_calls_emitted)
    return f"{result.tool_calls_valid}/{result.tool_calls_emitted}"


def _environment_summary(manifest: RunManifest) -> str:
    environment = manifest.environment
    parts = [
        environment.os,
        environment.platform_release,
        environment.machine,
        f"Python {environment.python_version}" if environment.python_version else None,
        f"{environment.cpu_count} CPU(s)" if environment.cpu_count else None,
    ]
    return " / ".join(part for part in parts if part) or "not captured"


def _model_metadata_summary(manifest: RunManifest) -> str:
    metadata = manifest.model_metadata
    parts = [
        f"revision={metadata.revision}" if metadata.revision else None,
        f"architecture={metadata.architecture}" if metadata.architecture else None,
        f"quantization={metadata.quantization}" if metadata.quantization else None,
        f"tokenizer={metadata.tokenizer}" if metadata.tokenizer else None,
        f"chat_template={metadata.chat_template}" if metadata.chat_template else None,
        f"context_length={metadata.context_length}" if metadata.context_length else None,
    ]
    return " / ".join(part for part in parts if part) or "not captured"


def _retention_summary(manifest: RunManifest) -> str:
    retention = manifest.retention_policy
    parts = [
        f"classification={retention.classification}",
        f"retain_days={retention.retain_days}" if retention.retain_days is not None else None,
        (
            f"raw_trace_retain_days={retention.raw_trace_retain_days}"
            if retention.raw_trace_retain_days is not None
            else None
        ),
        f"notes={'; '.join(retention.notes)}" if retention.notes else None,
    ]
    return " / ".join(part for part in parts if part)


def _adapter_summary(manifest: RunManifest) -> str:
    metadata = manifest.provider_metadata
    parts = [
        metadata.adapter_name,
        metadata.adapter_version,
        f"native={metadata.native_adapter}" if metadata.native_adapter else None,
        f"host={metadata.base_url_host}" if metadata.base_url_host else None,
    ]
    return " / ".join(part for part in parts if part) or "not captured"


def _engine_target_summary(manifest: RunManifest) -> str:
    target = manifest.engine_target
    if not isinstance(target, dict):
        return "not captured"
    standardization = target.get("standardization") if isinstance(target.get("standardization"), dict) else {}
    parts = [
        str(target.get("id")) if target.get("id") else None,
        str(target.get("display_name")) if target.get("display_name") else None,
        f"primary={standardization.get('primary_scoring_contract')}" if standardization.get("primary_scoring_contract") else None,
    ]
    return " / ".join(part for part in parts if part) or "not captured"


def _suite_provenance_summary(manifest: RunManifest) -> str:
    provenance = manifest.suite_provenance
    parts = [
        f"origin={provenance.origin}" if provenance.origin else None,
        f"source_suite={provenance.source_suite}" if provenance.source_suite else None,
        f"generator={provenance.generator}" if provenance.generator else None,
        f"profile={provenance.generator_profile}" if provenance.generator_profile else None,
        f"seed={provenance.generator_seed}" if provenance.generator_seed is not None else None,
        f"repeats={provenance.generator_repeats}" if provenance.generator_repeats is not None else None,
        f"license={provenance.license}" if provenance.license else None,
    ]
    return " / ".join(part for part in parts if part) or "not captured"
