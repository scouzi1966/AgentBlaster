from __future__ import annotations

import hashlib
import hmac
import html
import json
from http.cookies import SimpleCookie
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

from pydantic import ValidationError

from agentblaster.audit import AuditLogger
from agentblaster.campaign import campaign_plan_preview
from agentblaster.config import ProviderStore
from agentblaster.engine_targets import engine_target_catalog
from agentblaster.errors import ConfigError
from agentblaster.model_catalog import list_model_targets
from agentblaster.models import ModelMetadata, RawTraceMode
from agentblaster.policy import enforce_provider_policy, load_policy, offline_policy
from agentblaster.reports import generate_reports, load_manifest, load_results, summarize_run
from agentblaster.runner import BenchmarkRunner
from agentblaster.suites import BUILTIN_SUITES, get_builtin_suite
from agentblaster.telemetry import telemetry_mapping_catalog
from agentblaster.workflow_surfaces import workflow_surface_catalog


LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
DASHBOARD_AUTH_COOKIE = "agentblaster_dashboard"
REPORT_ARTIFACTS = {
    "report.html": "text/html; charset=utf-8",
    "report.md": "text/markdown; charset=utf-8",
    "summary.json": "application/json; charset=utf-8",
    "publication.json": "application/json; charset=utf-8",
    "report-card.svg": "image/svg+xml; charset=utf-8",
    "metrics/prometheus-summary.json": "application/json; charset=utf-8",
}


def assert_dashboard_bind_allowed(
    host: str,
    *,
    allow_non_loopback: bool = False,
    auth_configured: bool = False,
) -> None:
    """Require explicit opt-in before binding the dashboard beyond loopback."""
    if _is_loopback_host(host):
        return
    if allow_non_loopback and auth_configured:
        return
    if allow_non_loopback:
        raise ConfigError("non-loopback dashboard binding requires token authentication")
    raise ConfigError(
        "dashboard binds to loopback by default; pass --allow-non-loopback only on trusted networks"
    )


def list_dashboard_runs(runs_dir: Path) -> list[dict[str, Any]]:
    """Return compact, redacted summaries for valid run directories."""
    if not runs_dir.exists():
        return []

    runs: list[dict[str, Any]] = []
    for run_dir in sorted((path for path in runs_dir.iterdir() if path.is_dir()), reverse=True):
        try:
            manifest = load_manifest(run_dir)
            results = load_results(run_dir)
            summary = summarize_run(run_dir)
        except ConfigError:
            continue
        runs.append(
            {
                "run_id": manifest.run_id,
                "suite": manifest.suite,
                "provider": manifest.provider,
                "contract": manifest.contract.value,
                "model": manifest.model,
                "model_metadata": manifest.model_metadata.model_dump(mode="json"),
                "provider_metadata": manifest.provider_metadata.model_dump(mode="json"),
                "created_at": manifest.created_at,
                "raw_trace_mode": manifest.raw_trace_mode.value,
                "retention_policy": manifest.retention_policy.model_dump(mode="json"),
                "concurrency": manifest.concurrency,
                "suite_sha256": manifest.suite_sha256,
                "suite_snapshot_path": manifest.suite_snapshot_path,
                "suite_provenance": manifest.suite_provenance.model_dump(mode="json"),
                "metrics_artifacts": manifest.metrics_artifacts,
                "total_cases": summary.total_cases,
                "passed": summary.passed,
                "failed": summary.failed,
                "ok": summary.failed == 0,
                "duration_ms": summary.duration_ms,
                "requests_per_second": summary.requests_per_second,
                "total_cost_usd": _sum_metric([result.total_cost_usd for result in results]),
                "avg_queue_ms": _average_metric([result.queue_ms for result in results]),
                "avg_rate_limit_wait_ms": _average_metric([result.rate_limit_wait_ms for result in results]),
                "avg_latency_ms": _average_metric([result.latency_ms for result in results]),
                "avg_ttft_ms": _average_metric([result.ttft_ms for result in results]),
                "avg_decode_tokens_per_second": _average_metric(
                    [result.tokens_per_second_decode for result in results]
                ),
                "artifacts": _run_artifacts(manifest.run_id, run_dir),
            }
        )
    return runs


def dashboard_run_payload(runs_dir: Path, run_id: str) -> dict[str, Any]:
    if not runs_dir.exists():
        raise ConfigError(f"runs directory does not exist: {runs_dir}")
    for run_dir in sorted(path for path in runs_dir.iterdir() if path.is_dir()):
        try:
            manifest = load_manifest(run_dir)
        except ConfigError:
            continue
        if manifest.run_id != run_id:
            continue
        results = load_results(run_dir)
        summary = summarize_run(run_dir)
        return {
            "manifest": manifest.model_dump(mode="json"),
            "summary": summary.model_dump(mode="json"),
            "results": [result.model_dump(mode="json") for result in results],
        }
    raise ConfigError(f"unknown run: {run_id}")


def generate_dashboard_reports(runs_dir: Path, run_id: str, formats: list[str]) -> dict[str, Any]:
    run_dir = dashboard_run_dir(runs_dir, run_id)
    requested_formats = [item.strip() for item in formats if item.strip()]
    if not requested_formats:
        requested_formats = ["html", "md", "json", "publication", "card"]
    generated = generate_reports(run_dir, requested_formats)
    manifest = load_manifest(run_dir)
    return {
        "run_id": manifest.run_id,
        "generated": [
            {
                "name": path.relative_to(run_dir).as_posix(),
                "label": _artifact_label(path.relative_to(run_dir).as_posix()),
                "href": f"/runs/{quote(manifest.run_id, safe='')}/artifacts/{quote(path.relative_to(run_dir).as_posix(), safe='')}",
            }
            for path in generated
            if path.relative_to(run_dir).as_posix() in REPORT_ARTIFACTS
        ],
    }


def dashboard_providers(store: ProviderStore | None = None) -> list[dict[str, Any]]:
    providers = (store or ProviderStore()).list()
    return [
        {
            "name": provider.name,
            "contract": provider.contract.value,
            "base_url": str(provider.base_url).rstrip("/"),
            "default_model": provider.default_model,
            "remote": provider.remote,
            "api_key_ref": provider.api_key_ref.display() if provider.api_key_ref else None,
            "native_adapter": provider.native_adapter,
            "capabilities": provider.capabilities,
            "rate_limits": provider.rate_limits,
            "metrics_url": str(provider.metrics_url).rstrip("/") if provider.metrics_url else None,
            "tls_verify": provider.tls_verify,
            "ca_bundle": str(provider.ca_bundle) if provider.ca_bundle else None,
            "model_metadata": provider.model_metadata.model_dump(mode="json"),
        }
        for provider in providers
    ]


def dashboard_suites() -> list[dict[str, Any]]:
    return [
        {
            "name": suite.name,
            "description": suite.description,
            "provenance": suite.provenance.model_dump(mode="json"),
            "case_count": len(suite.cases),
            "cases": [
                {
                    "id": case.id,
                    "title": case.title,
                    "tags": case.tags,
                    "risk_level": case.risk_level,
                    "provenance": case.provenance,
                }
                for case in suite.cases
            ],
        }
        for suite in BUILTIN_SUITES.values()
    ]


def dashboard_model_targets() -> dict[str, Any]:
    return {
        "schema_version": "agentblaster.dashboard-model-targets.v1",
        "model_targets": [target.model_dump(mode="json") for target in list_model_targets()],
    }


def dashboard_engine_targets() -> dict[str, Any]:
    return engine_target_catalog()


def dashboard_workflow_surfaces() -> dict[str, Any]:
    return workflow_surface_catalog()


def dashboard_telemetry_mappings() -> dict[str, Any]:
    return telemetry_mapping_catalog()


def dashboard_catalog_index() -> dict[str, Any]:
    return {
        "schema_version": "agentblaster.dashboard-catalog-index.v1",
        "catalogs": [
            {"id": "providers", "href": "/api/providers", "description": "Redacted configured provider profiles."},
            {"id": "suites", "href": "/api/suites", "description": "Built-in benchmark suite metadata."},
            {"id": "models", "href": "/api/models", "description": "Canonical model targets for comparable matrices."},
            {"id": "engine-targets", "href": "/api/engine-targets", "description": "Standardized engine target planning metadata."},
            {"id": "workflow-surfaces", "href": "/api/workflow-surfaces", "description": "Tool, MCP, skill, LCP, and harness-engineering surfaces."},
            {"id": "telemetry-mappings", "href": "/api/telemetry-mappings", "description": "Raw-to-normalized telemetry mapping catalog."},
            {"id": "campaign-preview", "href": "/api/campaign-preview", "description": "No-write canonical campaign plan preview."},
            {"id": "runs", "href": "/api/runs", "description": "Completed run summaries."},
        ],
    }


def dashboard_campaign_preview(query: dict[str, list[str]] | None = None) -> dict[str, Any]:
    query = query or {}
    providers = _query_csv(query, "providers")
    targets = _query_csv(query, "targets")
    suites = _query_csv(query, "suites")
    output_dir = Path(_query_value(query, "output_dir") or "campaigns/qwen-gemma-local")
    policy_value = _query_value(query, "policy")
    name = _query_value(query, "name")
    concurrency_value = _query_value(query, "concurrency")
    try:
        concurrency = int(concurrency_value) if concurrency_value else 1
        return campaign_plan_preview(
            output_dir=output_dir,
            providers=providers,
            targets=targets,
            suites=suites,
            concurrency=concurrency,
            policy=Path(policy_value) if policy_value else None,
            name=name,
        )
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc


def launch_dashboard_run(runs_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    provider_name = str(payload.get("engine") or payload.get("provider") or "")
    if not provider_name:
        raise ConfigError("run launch requires provider or engine")
    suite_name = str(payload.get("suite") or "smoke")
    model = payload.get("model")
    concurrency = int(payload.get("concurrency") or 1)
    raw_trace_mode = RawTraceMode.OFF if payload.get("no_raw_traces") else RawTraceMode(str(payload.get("raw_traces") or "redacted"))
    allow_remote = _truthy(payload.get("allow_remote"))
    model_metadata = _payload_model_metadata(payload.get("model_metadata"))

    provider = ProviderStore().get(provider_name)
    suite = get_builtin_suite(suite_name)
    policy = load_policy(None) if allow_remote else offline_policy()
    enforce_provider_policy(
        provider,
        policy,
        raw_trace_mode=raw_trace_mode,
        concurrency=concurrency,
        suite=suite,
    )
    summary = BenchmarkRunner(
        provider,
        suite,
        output_dir=runs_dir,
        raw_trace_mode=raw_trace_mode,
        concurrency=concurrency,
    ).run(model=str(model) if model else None, model_metadata=model_metadata)
    return summary.model_dump(mode="json")


def render_dashboard_html(runs_dir: Path, *, auth_required: bool = False) -> str:
    runs = list_dashboard_runs(runs_dir)
    rows = "\n".join(_run_row(run) for run in runs)
    launch_panel = _launch_panel()
    catalog_panel = _catalog_panel()
    posture_panel = _security_posture_panel(runs, auth_required=auth_required)
    auth_notice = (
        '<p class="kicker" data-testid="auth-status">Dashboard token authentication enabled</p>'
        if auth_required
        else ""
    )
    empty_state = ""
    if not rows:
        empty_state = """
        <section class="empty" data-testid="empty-state">
          <p>No AgentBlaster runs were found in this directory.</p>
        </section>
        """
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentBlaster Dashboard</title>
  <style>
    :root {{
      --ink: #111713;
      --muted: #647067;
      --paper: #f5efe4;
      --card: rgba(255, 252, 245, 0.86);
      --line: #d7cbb7;
      --accent: #d66b1f;
      --accent-dark: #70340e;
      --good: #156c43;
      --bad: #9b2721;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      font-family: "Avenir Next", "Trebuchet MS", "Gill Sans", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(214, 107, 31, 0.22), transparent 34rem),
        linear-gradient(135deg, #fff8ec 0%, var(--paper) 48%, #dfe7d9 100%);
      min-height: 100vh;
    }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 40px 20px 64px; }}
    .hero {{
      display: grid;
      grid-template-columns: 1.3fr 0.7fr;
      gap: 24px;
      align-items: end;
      margin-bottom: 28px;
    }}
    h1 {{
      font-family: "Iowan Old Style", "Palatino", serif;
      font-size: clamp(42px, 8vw, 86px);
      line-height: 0.9;
      margin: 0;
      letter-spacing: -0.06em;
    }}
    .kicker {{ color: var(--accent-dark); font-weight: 800; letter-spacing: 0.14em; text-transform: uppercase; }}
    .posture {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 18px 0 26px; }}
    .posture-card {{ border: 1px solid var(--line); border-radius: 18px; padding: 14px 16px; background: var(--card); box-shadow: 0 10px 32px rgba(42, 31, 18, 0.08); }}
    .posture-card strong {{ display: block; font-size: 22px; margin: 2px 0 4px; }}
    .posture-card span {{ color: var(--muted); font-size: 13px; line-height: 1.35; }}
    .posture-card.good {{ border-color: rgba(21, 108, 67, 0.35); }}
    .posture-card.warn {{ border-color: rgba(155, 39, 33, 0.36); }}
    .subhead {{ color: var(--muted); max-width: 620px; font-size: 18px; line-height: 1.5; }}
    .panel {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 28px;
      box-shadow: 0 24px 70px rgba(76, 53, 25, 0.14);
      overflow: hidden;
      backdrop-filter: blur(12px);
    }}
    .launch {{
      padding: 22px;
      margin-bottom: 24px;
    }}
    .launch h2 {{ margin: 0 0 14px; font-family: "Iowan Old Style", "Palatino", serif; font-size: 32px; }}
    .catalog {{ padding: 22px; margin-bottom: 24px; }}
    .catalog h2 {{ margin: 0 0 8px; font-family: "Iowan Old Style", "Palatino", serif; font-size: 32px; }}
    .catalog-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; margin-top: 16px; }}
    .catalog-card {{ border: 1px solid var(--line); border-radius: 18px; color: var(--ink); padding: 13px 14px; text-decoration: none; background: rgba(255,255,255,0.44); }}
    .catalog-card strong {{ display: block; margin-bottom: 4px; }}
    .catalog-card span {{ color: var(--muted); font-size: 13px; line-height: 1.35; }}
    form {{ display: grid; grid-template-columns: repeat(6, minmax(120px, 1fr)); gap: 12px; align-items: end; }}
    label {{ color: var(--accent-dark); display: grid; font-size: 12px; font-weight: 800; gap: 6px; letter-spacing: 0.08em; text-transform: uppercase; }}
    input, select {{
      border: 1px solid var(--line);
      border-radius: 14px;
      color: var(--ink);
      font: inherit;
      padding: 10px 11px;
      width: 100%;
      background: rgba(255,255,255,0.7);
    }}
    .check {{ align-items: center; display: flex; gap: 8px; letter-spacing: 0; text-transform: none; }}
    .check input {{ width: auto; }}
    button {{
      background: var(--ink);
      border: 0;
      border-radius: 16px;
      color: white;
      cursor: pointer;
      font: inherit;
      font-weight: 900;
      padding: 12px 16px;
    }}
    .links {{ display: flex; flex-wrap: wrap; gap: 7px; }}
    .links a {{
      background: rgba(112, 52, 14, 0.1);
      border: 1px solid rgba(112, 52, 14, 0.18);
      border-radius: 999px;
      color: var(--accent-dark);
      font-size: 12px;
      font-weight: 800;
      padding: 5px 9px;
      text-decoration: none;
    }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ padding: 15px 16px; text-align: left; border-bottom: 1px solid rgba(215, 203, 183, 0.78); }}
    th {{ color: var(--accent-dark); font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; }}
    tr:last-child td {{ border-bottom: 0; }}
    .run-id {{ font-weight: 800; }}
    .meta {{ color: var(--muted); font-size: 13px; margin-top: 3px; }}
    .status {{ border-radius: 999px; color: white; display: inline-block; font-weight: 800; padding: 6px 10px; }}
    .status.pass {{ background: var(--good); }}
    .status.fail {{ background: var(--bad); }}
    .empty {{ background: var(--card); border: 1px dashed var(--line); border-radius: 24px; padding: 28px; }}
    @media (max-width: 760px) {{
      .hero {{ grid-template-columns: 1fr; }}
      form {{ grid-template-columns: 1fr; }}
      .panel {{ overflow-x: auto; }}
      th, td {{ white-space: nowrap; }}
    }}
  </style>
</head>
<body>
  <main>
    {auth_notice}
    {posture_panel}
    <section class="hero">
      <div>
        <div class="kicker">Local agentic benchmark control</div>
        <h1>AgentBlaster</h1>
      </div>
      <p class="subhead">
        Browse completed runs, compare health signals, and inspect normalized telemetry without exposing raw traces.
      </p>
    </section>
    {launch_panel}
    {catalog_panel}
    {empty_state}
    <section class="panel" data-testid="runs-panel">
      <table data-testid="runs-table">
        <thead>
          <tr>
            <th>Run</th>
            <th>Status</th>
            <th>Provider</th>
            <th>Adapter</th>
            <th>Model</th>
            <th>Suite</th>
            <th>Provenance</th>
            <th>Suite SHA</th>
            <th>Cases</th>
            <th>Req/s</th>
            <th>Cost</th>
            <th>Avg queue</th>
            <th>Rate wait</th>
            <th>Avg latency</th>
            <th>Avg TTFT</th>
            <th>Decode tok/s</th>
            <th>Reports</th>
          </tr>
        </thead>
        <tbody>
          {rows}
        </tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""


def serve_dashboard(
    runs_dir: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    allow_non_loopback: bool = False,
    auth_token: str | None = None,
    audit_log: Path | None = None,
) -> None:
    assert_dashboard_bind_allowed(host, allow_non_loopback=allow_non_loopback, auth_configured=auth_token is not None)
    handler = make_dashboard_handler(runs_dir, auth_token=auth_token)
    server = ThreadingHTTPServer((host, port), handler)
    AuditLogger(audit_log).emit(
        "dashboard_started",
        runs_dir=str(runs_dir),
        host=host,
        port=port,
        allow_non_loopback=allow_non_loopback,
        auth_enabled=auth_token is not None,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return
    finally:
        server.server_close()


def make_dashboard_handler(runs_dir: Path, *, auth_token: str | None = None):
    auth_digest = _dashboard_auth_digest(auth_token) if auth_token else None

    class DashboardRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/login":
                if auth_token is None:
                    self._redirect("/")
                    return
                self._write_html(_login_html())
                return
            if not self._is_authenticated():
                self._reject_unauthenticated(parsed.path)
                return
            if parsed.path == "/logout":
                self._redirect("/login", clear_auth_cookie=True)
                return
            if parsed.path in {"", "/"}:
                self._write_html(render_dashboard_html(runs_dir, auth_required=auth_digest is not None))
                return
            if parsed.path.startswith("/runs/") and "/artifacts/" in parsed.path:
                try:
                    run_id, artifact_name = _parse_artifact_path(parsed.path)
                    artifact_path = dashboard_artifact_path(runs_dir, run_id, artifact_name)
                    self._write_file(artifact_path, REPORT_ARTIFACTS[artifact_name])
                except ConfigError as exc:
                    self._write_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                return
            if parsed.path == "/api/runs":
                self._write_json({"runs": list_dashboard_runs(runs_dir)})
                return
            if parsed.path == "/api/providers":
                try:
                    self._write_json({"providers": dashboard_providers()})
                except ConfigError as exc:
                    self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            if parsed.path == "/api/suites":
                self._write_json({"suites": dashboard_suites()})
                return
            if parsed.path == "/api/models":
                self._write_json(dashboard_model_targets())
                return
            if parsed.path == "/api/engine-targets":
                self._write_json(dashboard_engine_targets())
                return
            if parsed.path == "/api/workflow-surfaces":
                self._write_json(dashboard_workflow_surfaces())
                return
            if parsed.path == "/api/telemetry-mappings":
                self._write_json(dashboard_telemetry_mappings())
                return
            if parsed.path == "/api/catalogs":
                self._write_json(dashboard_catalog_index())
                return
            if parsed.path == "/api/campaign-preview":
                try:
                    self._write_json(dashboard_campaign_preview(parse_qs(parsed.query, keep_blank_values=True)))
                except ConfigError as exc:
                    self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            if parsed.path.startswith("/api/runs/"):
                run_id = unquote(parsed.path.removeprefix("/api/runs/")).strip("/")
                try:
                    self._write_json(dashboard_run_payload(runs_dir, run_id))
                except ConfigError as exc:
                    self._write_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                return
            self._write_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/login":
                if auth_token is None:
                    self._redirect("/")
                    return
                payload = self._read_form_payload()
                if auth_token is not None and hmac.compare_digest(str(payload.get("token") or ""), auth_token):
                    self._redirect("/", set_auth_cookie=auth_digest)
                    return
                self._write_html(_login_html("invalid dashboard token"), status=HTTPStatus.UNAUTHORIZED)
                return
            if not self._is_authenticated():
                self._reject_unauthenticated(parsed.path)
                return
            if parsed.path == "/launch":
                try:
                    payload = self._read_form_payload()
                    summary = launch_dashboard_run(runs_dir, payload)
                except (ConfigError, ValidationError, ValueError) as exc:
                    self._write_html(_error_html(str(exc)), status=HTTPStatus.BAD_REQUEST)
                    return
                self.send_response(HTTPStatus.SEE_OTHER)
                self._security_headers()
                self.send_header("location", f"/?launched={quote(str(summary['run_id']))}")
                self.end_headers()
                return
            if parsed.path.startswith("/runs/") and parsed.path.endswith("/reports"):
                try:
                    run_id = unquote(parsed.path.removeprefix("/runs/").removesuffix("/reports")).strip("/")
                    payload = self._read_form_payload()
                    generate_dashboard_reports(runs_dir, run_id, _split_csv(str(payload.get("formats") or "")))
                except (ConfigError, ValidationError, ValueError) as exc:
                    self._write_html(_error_html(str(exc)), status=HTTPStatus.BAD_REQUEST)
                    return
                self.send_response(HTTPStatus.SEE_OTHER)
                self._security_headers()
                self.send_header("location", f"/?reports={quote(run_id)}")
                self.end_headers()
                return
            if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/reports"):
                try:
                    run_id = unquote(parsed.path.removeprefix("/api/runs/").removesuffix("/reports")).strip("/")
                    payload = self._read_json_payload()
                    formats = payload.get("formats") or ["html", "md", "json", "publication", "card"]
                    if isinstance(formats, str):
                        formats = _split_csv(formats)
                    if not isinstance(formats, list):
                        raise ConfigError("formats must be a list or comma-separated string")
                    result = generate_dashboard_reports(runs_dir, run_id, [str(item) for item in formats])
                except (ConfigError, ValidationError, ValueError) as exc:
                    self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._write_json({"reports": result}, status=HTTPStatus.CREATED)
                return
            if parsed.path != "/api/runs":
                self._write_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
                return
            try:
                payload = self._read_json_payload()
                summary = launch_dashboard_run(runs_dir, payload)
            except (ConfigError, ValidationError, ValueError) as exc:
                self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._write_json({"summary": summary}, status=HTTPStatus.CREATED)

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

        def _is_authenticated(self) -> bool:
            if auth_token is None or auth_digest is None:
                return True
            authorization = self.headers.get("authorization", "")
            if authorization.lower().startswith("bearer "):
                candidate = authorization[7:].strip()
                if hmac.compare_digest(candidate, auth_token):
                    return True
            cookie_header = self.headers.get("cookie", "")
            if cookie_header:
                cookie = SimpleCookie()
                cookie.load(cookie_header)
                morsel = cookie.get(DASHBOARD_AUTH_COOKIE)
                if morsel is not None and hmac.compare_digest(morsel.value, auth_digest):
                    return True
            return False

        def _reject_unauthenticated(self, path: str) -> None:
            if path.startswith("/api/"):
                payload = json.dumps({"error": "dashboard authentication required"}).encode("utf-8")
                self.send_response(HTTPStatus.UNAUTHORIZED)
                self._security_headers()
                self.send_header("www-authenticate", 'Bearer realm="AgentBlaster Dashboard"')
                self.send_header("content-type", "application/json; charset=utf-8")
                self.send_header("content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            self._redirect("/login")

        def _redirect(
            self,
            location: str,
            *,
            set_auth_cookie: str | None = None,
            clear_auth_cookie: bool = False,
        ) -> None:
            self.send_response(HTTPStatus.SEE_OTHER)
            self._security_headers()
            self.send_header("location", location)
            if set_auth_cookie is not None:
                self.send_header(
                    "set-cookie",
                    f"{DASHBOARD_AUTH_COOKIE}={set_auth_cookie}; Path=/; HttpOnly; SameSite=Strict; Max-Age=28800",
                )
            if clear_auth_cookie:
                self.send_header(
                    "set-cookie",
                    f"{DASHBOARD_AUTH_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0",
                )
            self.end_headers()

        def _write_html(self, body: str, *, status: HTTPStatus = HTTPStatus.OK) -> None:
            payload = body.encode("utf-8")
            self.send_response(status)
            self._security_headers()
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _write_file(self, path: Path, content_type: str) -> None:
            payload = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self._security_headers()
            self.send_header("content-type", content_type)
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _write_json(self, body: dict[str, Any], *, status: HTTPStatus = HTTPStatus.OK) -> None:
            payload = (json.dumps(body, sort_keys=True) + "\n").encode("utf-8")
            self.send_response(status)
            self._security_headers()
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _read_json_payload(self) -> dict[str, Any]:
            content_length = int(self.headers.get("content-length", "0"))
            if content_length <= 0:
                return {}
            raw = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ConfigError("JSON payload must be an object")
            return payload

        def _read_form_payload(self) -> dict[str, Any]:
            content_length = int(self.headers.get("content-length", "0"))
            if content_length <= 0:
                return {}
            raw = self.rfile.read(content_length).decode("utf-8")
            parsed = parse_qs(raw, keep_blank_values=True)
            payload = {key: values[-1] for key, values in parsed.items() if values}
            return {
                **payload,
                "allow_remote": _truthy(payload.get("allow_remote")),
                "no_raw_traces": payload.get("raw_traces") == RawTraceMode.OFF.value,
                "concurrency": int(payload.get("concurrency") or 1),
            }

        def _security_headers(self) -> None:
            self.send_header("cache-control", "no-store")
            self.send_header("referrer-policy", "no-referrer")
            self.send_header("x-content-type-options", "nosniff")
            self.send_header(
                "content-security-policy",
                "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                "script-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
            )

    return DashboardRequestHandler


def _query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key) or []
    for value in values:
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def _query_csv(query: dict[str, list[str]], key: str) -> list[str] | None:
    value = _query_value(query, key)
    if value is None:
        return None
    return _split_csv(value)


def _dashboard_auth_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _run_row(run: dict[str, Any]) -> str:
    status_class = "pass" if run["ok"] else "fail"
    status_label = "pass" if run["ok"] else "fail"
    return f"""<tr data-testid="run-row" data-run-id="{html.escape(run["run_id"])}">
  <td>
    <div class="run-id">{html.escape(run["run_id"])}</div>
    <div class="meta">{html.escape(run["created_at"])}</div>
  </td>
  <td><span class="status {status_class}">{status_label}</span></td>
  <td>{html.escape(run["provider"])}<div class="meta">{html.escape(_provider_brief(run["provider_metadata"]))}</div></td>
  <td>{html.escape(_adapter_brief(run["provider_metadata"]))}</td>
  <td>{html.escape(run["model"])}<div class="meta">{html.escape(_model_metadata_brief(run["model_metadata"]))}</div></td>
  <td>{html.escape(run["suite"])}</td>
  <td>{html.escape(_suite_provenance_brief(run["suite_provenance"]))}</td>
  <td><span class="meta">{html.escape(_hash_brief(run.get("suite_sha256")))}</span></td>
  <td>{run["passed"]}/{run["total_cases"]}</td>
  <td>{_display_metric(run["requests_per_second"])}</td>
  <td>{_display_metric(run["total_cost_usd"])}</td>
  <td>{_display_metric(run["avg_queue_ms"])}</td>
  <td>{_display_metric(run["avg_rate_limit_wait_ms"])}</td>
  <td>{_display_metric(run["avg_latency_ms"])}</td>
  <td>{_display_metric(run["avg_ttft_ms"])}</td>
  <td>{_display_metric(run["avg_decode_tokens_per_second"])}</td>
  <td>{_artifact_links(run)}</td>
</tr>"""


def _launch_panel() -> str:
    try:
        providers = dashboard_providers()
        provider_error = ""
    except ConfigError as exc:
        providers = []
        provider_error = f"<p class=\"meta\">Provider config error: {html.escape(str(exc))}</p>"
    provider_options = _provider_options(providers)
    suite_options = _suite_options(dashboard_suites())
    return f"""
    <section class="panel launch" data-testid="launch-panel">
      <h2>Launch a local run</h2>
      <form method="post" action="/launch" data-testid="launch-form">
        <label>Provider
          <select name="provider" required data-testid="provider-select">
            {provider_options}
          </select>
        </label>
        <label>Suite
          <select name="suite" required data-testid="suite-select">
            {suite_options}
          </select>
        </label>
        <label>Model
          <input name="model" placeholder="provider default or model id" data-testid="model-input">
        </label>
        <label>Concurrency
          <input name="concurrency" type="number" min="1" value="1" data-testid="concurrency-input">
        </label>
        <label>Raw traces
          <select name="raw_traces" data-testid="raw-traces-select">
            <option value="redacted">redacted</option>
            <option value="off">off</option>
          </select>
        </label>
        <label class="check">
          <input name="allow_remote" type="checkbox" value="true" data-testid="allow-remote-input">
          allow remote provider
        </label>
        <button type="submit" data-testid="launch-submit">Launch</button>
      </form>
      {provider_error}
      <p class="meta">Remote providers are blocked by default unless explicitly allowed. Secrets are resolved from provider references, not browser input.</p>
    </section>
    """


def _catalog_panel() -> str:
    index = dashboard_catalog_index()
    catalogs = index["catalogs"]
    try:
        model_count = len(dashboard_model_targets()["model_targets"])
        engine_count = len(dashboard_engine_targets()["targets"])
        surface_count = len(dashboard_workflow_surfaces()["surfaces"])
    except Exception:  # noqa: BLE001 - catalog panel must not block run browsing
        model_count = 0
        engine_count = 0
        surface_count = 0
    links = "
".join(
        (
            f'<a class="catalog-card" data-testid="catalog-link" href="{html.escape(item["href"])}">'
            f'<strong>{html.escape(item["id"].replace("-", " ").title())}</strong>'
            f'<span>{html.escape(item["description"])}</span>'
            '</a>'
        )
        for item in catalogs
        if item["id"] in {"models", "engine-targets", "workflow-surfaces", "telemetry-mappings", "campaign-preview", "providers", "suites"}
    )
    return f"""
    <section class="panel catalog" data-testid="catalog-panel" aria-label="Planning catalogs">
      <h2>Planning catalogs</h2>
      <p class="meta">Review setup metadata before dispatch: {engine_count} engine targets, {model_count} model targets, and {surface_count} workflow surfaces. Catalog links are read-only and redaction-safe.</p>
      <div class="catalog-grid">
        {links}
      </div>
    </section>
    """


def _security_posture_panel(runs: list[dict[str, Any]], *, auth_required: bool) -> str:
    try:
        providers = dashboard_providers()
        provider_error = ""
    except ConfigError as exc:
        providers = []
        provider_error = f"Provider config unavailable: {html.escape(str(exc))}"
    remote_providers = [provider for provider in providers if provider["remote"]]
    insecure_tls_providers = [provider for provider in providers if provider.get("tls_verify") is False]
    full_trace_runs = [run for run in runs if run["raw_trace_mode"] == RawTraceMode.FULL.value]
    redacted_or_off_runs = [
        run for run in runs if run["raw_trace_mode"] in {RawTraceMode.REDACTED.value, RawTraceMode.OFF.value}
    ]
    cards = [
        _posture_card(
            testid="posture-auth",
            label="Dashboard auth",
            value="enabled" if auth_required else "loopback-only",
            detail="Token required for this session." if auth_required else "No dashboard token configured; keep bind host on loopback.",
            severity="good" if auth_required else "warn",
        ),
        _posture_card(
            testid="posture-remote-providers",
            label="Remote providers",
            value=str(len(remote_providers)),
            detail=(
                "Remote launch remains blocked unless explicitly allowed."
                if remote_providers
                else "No remote providers configured."
            ),
            severity="warn" if remote_providers else "good",
        ),
        _posture_card(
            testid="posture-raw-traces",
            label="Full raw traces",
            value=str(len(full_trace_runs)),
            detail=(
                "Full raw trace runs exist; report downloads remain allowlisted."
                if full_trace_runs
                else f"{len(redacted_or_off_runs)} run(s) use redacted or disabled raw traces."
            ),
            severity="warn" if full_trace_runs else "good",
        ),
        _posture_card(
            testid="posture-artifacts",
            label="Artifact serving",
            value="allowlisted",
            detail="Reports and metrics summaries are served; raw traces and manifests are not linked.",
            severity="good",
        ),
        _posture_card(
            testid="posture-tls",
            label="Insecure TLS providers",
            value=str(len(insecure_tls_providers)),
            detail=(
                "One or more providers disable certificate verification."
                if insecure_tls_providers
                else "TLS certificate verification remains enabled for configured providers."
            ),
            severity="warn" if insecure_tls_providers else "good",
        ),
    ]
    if provider_error:
        cards.append(
            _posture_card(
                testid="posture-provider-config",
                label="Provider config",
                value="error",
                detail=provider_error,
                severity="warn",
            )
        )
    return f"""
    <section class="posture" data-testid="security-posture-panel" aria-label="Security posture">
      {"".join(cards)}
    </section>
    """


def _posture_card(*, testid: str, label: str, value: str, detail: str, severity: str) -> str:
    return f"""<div class="posture-card {html.escape(severity)}" data-testid="{html.escape(testid)}">
      <span>{html.escape(label)}</span>
      <strong>{html.escape(value)}</strong>
      <span>{html.escape(detail)}</span>
    </div>"""


def _provider_options(providers: list[dict[str, Any]]) -> str:
    if not providers:
        return '<option value="" disabled selected>No configured providers</option>'
    return "\n".join(
        (
            f'<option value="{html.escape(provider["name"])}">'
            f'{html.escape(provider["name"])} ({html.escape(provider["contract"])})'
            f'{" remote" if provider["remote"] else ""}</option>'
        )
        for provider in providers
    )


def _suite_options(suites: list[dict[str, Any]]) -> str:
    return "\n".join(
        f'<option value="{html.escape(suite["name"])}">{html.escape(suite["name"])} ({suite["case_count"]})</option>'
        for suite in suites
    )


def _run_artifacts(run_id: str, run_dir: Path) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    for artifact_name in REPORT_ARTIFACTS:
        if (run_dir / artifact_name).exists():
            artifacts.append(
                {
                    "name": artifact_name,
                    "label": _artifact_label(artifact_name),
                    "href": f"/runs/{quote(run_id, safe='')}/artifacts/{quote(artifact_name, safe='')}",
                }
            )
    return artifacts


def _artifact_links(run: dict[str, Any]) -> str:
    artifacts = run.get("artifacts", [])
    form = (
        f'<form method="post" action="/runs/{html.escape(quote(run["run_id"], safe=""))}/reports" '
        f'data-testid="report-generate-form">'
        '<input type="hidden" name="formats" value="html,md,json,publication,card">'
        '<button type="submit">Generate</button>'
        "</form>"
    )
    if not artifacts:
        return f'<span class="meta">not generated</span>{form}'
    links = []
    for artifact in artifacts:
        links.append(
            f'<a data-testid="report-artifact-link" href="{html.escape(artifact["href"])}">'
            f'{html.escape(artifact["label"])}</a>'
        )
    return f'<div class="links">{"".join(links)}{form}</div>'


def _artifact_label(artifact_name: str) -> str:
    labels = {
        "report.html": "HTML",
        "report.md": "MD",
        "summary.json": "summary",
        "publication.json": "publication",
        "report-card.svg": "card",
        "metrics/prometheus-summary.json": "metrics",
    }
    return labels.get(artifact_name, artifact_name)


def _parse_artifact_path(path: str) -> tuple[str, str]:
    relative = path.removeprefix("/runs/")
    if "/artifacts/" not in relative:
        raise ConfigError("invalid artifact path")
    run_id, artifact_name = relative.split("/artifacts/", 1)
    run_id = unquote(run_id).strip("/")
    artifact_name = unquote(artifact_name).strip("/")
    if not run_id or not artifact_name or artifact_name not in REPORT_ARTIFACTS:
        raise ConfigError("unknown dashboard artifact")
    return run_id, artifact_name


def dashboard_artifact_path(runs_dir: Path, run_id: str, artifact_name: str) -> Path:
    if artifact_name not in REPORT_ARTIFACTS:
        raise ConfigError("unknown dashboard artifact")
    run_dir = dashboard_run_dir(runs_dir, run_id)
    artifact_path = run_dir / artifact_name
    if not artifact_path.exists() or not artifact_path.is_file():
        raise ConfigError(f"artifact does not exist: {artifact_name}")
    return artifact_path


def dashboard_run_dir(runs_dir: Path, run_id: str) -> Path:
    if not runs_dir.exists():
        raise ConfigError(f"runs directory does not exist: {runs_dir}")
    for run_dir in sorted(path for path in runs_dir.iterdir() if path.is_dir()):
        try:
            manifest = load_manifest(run_dir)
        except ConfigError:
            continue
        if manifest.run_id != run_id:
            continue
        return run_dir
    raise ConfigError(f"unknown run: {run_id}")


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _truthy(value: Any) -> bool:
    return str(value or "").lower() in {"1", "true", "yes", "on"}


def _error_html(message: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>AgentBlaster Dashboard Error</title></head>
<body>
  <h1>AgentBlaster Dashboard Error</h1>
  <p>{html.escape(message)}</p>
  <p><a href="/">Back to dashboard</a></p>
</body>
</html>
"""


def _login_html(error: str | None = None) -> str:
    error_html = f'<p class="error">{html.escape(error)}</p>' if error else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentBlaster Dashboard Login</title>
  <style>
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      font-family: "Avenir Next", "Trebuchet MS", sans-serif;
      color: #111713;
      background:
        radial-gradient(circle at top left, rgba(214, 107, 31, 0.22), transparent 32rem),
        linear-gradient(135deg, #fff8ec 0%, #f5efe4 52%, #dfe7d9 100%);
    }}
    main {{
      width: min(420px, calc(100vw - 32px));
      padding: 28px;
      border: 1px solid #d7cbb7;
      border-radius: 24px;
      background: rgba(255, 252, 245, 0.9);
      box-shadow: 0 22px 70px rgba(40, 30, 18, 0.14);
    }}
    h1 {{ margin: 0 0 8px; font-family: "Iowan Old Style", Georgia, serif; font-size: 42px; }}
    p {{ color: #647067; line-height: 1.5; }}
    label {{ display: grid; gap: 8px; font-weight: 700; }}
    input {{ padding: 12px; border: 1px solid #b9aa93; border-radius: 12px; font: inherit; }}
    button {{ margin-top: 16px; width: 100%; padding: 12px 14px; border: 0; border-radius: 12px; background: #111713; color: #fffdf6; font-weight: 800; cursor: pointer; }}
    .error {{ color: #9b2721; font-weight: 700; }}
  </style>
</head>
<body>
  <main data-testid="dashboard-login">
    <h1>AgentBlaster</h1>
    <p>Enter the dashboard token configured by the operator.</p>
    {error_html}
    <form method="post" action="/login">
      <label>Dashboard token
        <input name="token" type="password" autocomplete="current-password" required autofocus data-testid="dashboard-token-input">
      </label>
      <button type="submit" data-testid="dashboard-login-submit">Unlock dashboard</button>
    </form>
  </main>
</body>
</html>
"""


def _average_metric(values: list[float | int | None]) -> float | None:
    numeric_values = [float(value) for value in values if value is not None]
    if not numeric_values:
        return None
    return round(sum(numeric_values) / len(numeric_values), 3)


def _sum_metric(values: list[float | int | None]) -> float | None:
    numeric_values = [float(value) for value in values if value is not None]
    if not numeric_values:
        return None
    return round(sum(numeric_values), 9)


def _display_metric(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def _payload_model_metadata(value: Any) -> ModelMetadata | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ConfigError("model_metadata must be an object")
    metadata = ModelMetadata.model_validate(value)
    return None if metadata.is_empty() else metadata


def _model_metadata_brief(metadata: dict[str, Any]) -> str:
    parts = [
        metadata.get("architecture"),
        metadata.get("quantization"),
        f"ctx {metadata.get('context_length')}" if metadata.get("context_length") else None,
    ]
    return " / ".join(str(part) for part in parts if part) or "metadata not captured"


def _provider_brief(metadata: dict[str, Any]) -> str:
    parts = [
        metadata.get("base_url_host"),
        "remote" if metadata.get("remote") else "local",
        "tls=verify" if metadata.get("tls_verify", True) else "tls=insecure",
    ]
    return " / ".join(str(part) for part in parts if part)


def _adapter_brief(metadata: dict[str, Any]) -> str:
    parts = [
        metadata.get("adapter_name"),
        metadata.get("adapter_version"),
    ]
    return " / ".join(str(part) for part in parts if part) or "not captured"


def _suite_provenance_brief(provenance: dict[str, Any]) -> str:
    parts = [
        provenance.get("origin"),
        provenance.get("generator_profile"),
        f"seed {provenance.get('generator_seed')}" if provenance.get("generator_seed") is not None else None,
    ]
    return " / ".join(str(part) for part in parts if part) or "not captured"


def _hash_brief(value: Any) -> str:
    if not value:
        return "not captured"
    return str(value)[:12]


def _is_loopback_host(host: str) -> bool:
    if host in LOOPBACK_HOSTS:
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False
