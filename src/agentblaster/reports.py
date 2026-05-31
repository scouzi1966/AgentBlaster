from __future__ import annotations

import html
import json
from pathlib import Path

from agentblaster.errors import ConfigError
from agentblaster.models import BenchmarkResult, RunManifest, RunSummary


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
        results_path="results.jsonl",
        manifest_path="manifest.json",
    )


def write_json_summary(run_dir: Path) -> Path:
    summary = summarize_run(run_dir)
    path = run_dir / "summary.json"
    path.write_text(json.dumps(summary.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_html_report(run_dir: Path) -> Path:
    manifest = load_manifest(run_dir)
    results = load_results(run_dir)
    summary = summarize_run(run_dir)
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
      Model: {html.escape(summary.model)}<br>
      Contract: {html.escape(manifest.contract.value)}<br>
      Raw traces: {html.escape(manifest.raw_trace_mode.value)}<br>
      Created: {html.escape(manifest.created_at)}
    </div>
  </header>
  <section class="score">
    <div class="metric"><span>Total</span><strong>{summary.total_cases}</strong></div>
    <div class="metric"><span>Passed</span><strong>{summary.passed}</strong></div>
    <div class="metric"><span>Failed</span><strong>{summary.failed}</strong></div>
  </section>
  <table>
    <thead>
      <tr>
        <th>Case</th>
        <th>Status</th>
        <th>Latency ms</th>
        <th>Input</th>
        <th>Output</th>
        <th>Total</th>
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
    for report_format in formats:
        normalized = report_format.strip().lower()
        if not normalized:
            continue
        if normalized == "html":
            generated.append(write_html_report(run_dir))
        elif normalized == "json":
            generated.append(write_json_summary(run_dir))
        else:
            raise ConfigError(f"unsupported report format: {report_format}")
    return generated


def _result_row(result: BenchmarkResult) -> str:
    status_class = "pass" if result.ok else "fail"
    status = "pass" if result.ok else "fail"
    return f"""<tr>
  <td>{html.escape(result.case_id)}</td>
  <td class="{status_class}">{status}</td>
  <td>{_cell(result.latency_ms)}</td>
  <td>{_cell(result.input_tokens)}</td>
  <td>{_cell(result.output_tokens)}</td>
  <td>{_cell(result.total_tokens)}</td>
  <td>{html.escape(result.message)}</td>
</tr>"""


def _cell(value) -> str:
    if value is None:
        return ""
    return html.escape(str(value))
