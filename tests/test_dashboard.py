from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from agentblaster.config import ProviderStore
from agentblaster.dashboard import (
    assert_dashboard_bind_allowed,
    dashboard_artifact_path,
    dashboard_campaign_preview,
    dashboard_catalog_index,
    dashboard_engine_targets,
    dashboard_run_payload,
    dashboard_model_targets,
    dashboard_providers,
    dashboard_suites,
    dashboard_telemetry_mappings,
    dashboard_workflow_surfaces,
    list_dashboard_runs,
    make_dashboard_handler,
    render_dashboard_html,
)
from agentblaster.errors import ConfigError
from agentblaster.models import ApiContract, BenchmarkResult, ModelMetadata, ProviderConfig, RawTraceMode, RunManifest


def test_dashboard_lists_runs_with_normalized_metrics(tmp_path) -> None:
    _write_run(tmp_path, run_id="run_test", ok=True)

    runs = list_dashboard_runs(tmp_path)

    assert runs == [
        {
            "run_id": "run_test",
            "suite": "smoke",
            "provider": "local",
            "contract": "openai",
            "model": "qwen-test",
            "model_metadata": {
                "revision": "rev-1",
                "architecture": "qwen3-dense",
                "quantization": "mlx-f16",
                "tokenizer": None,
                "chat_template": None,
                "context_length": 32768,
            },
            "provider_metadata": {
                "base_url": "http://127.0.0.1:9999/v1",
                "base_url_host": "127.0.0.1",
                "remote": False,
                "native_adapter": None,
                "adapter_name": "openai-chat-completions",
                "adapter_version": "agentblaster-adapter-v1",
                "capabilities": {"streaming": True},
                "metrics_url_host": None,
                "tls_verify": True,
                "ca_bundle": None,
            },
            "created_at": "2026-05-31T00:00:00Z",
            "raw_trace_mode": "redacted",
            "retention_policy": {
                "classification": "internal",
                "retain_days": None,
                "raw_trace_retain_days": None,
                "notes": [],
            },
            "concurrency": 2,
            "suite_sha256": "abc123def4567890",
            "suite_snapshot_path": "suite.json",
            "suite_provenance": {
                "origin": "builtin",
                "source_suite": None,
                "generator": None,
                "generator_profile": None,
                "generator_seed": None,
                "generator_repeats": None,
                "primary_source": "AgentBlaster",
                "source_url": None,
                "license": "MIT",
                "risk_labels": [],
                "notes": [],
            },
            "metrics_artifacts": ["metrics/prometheus-summary.json"],
            "total_cases": 1,
            "passed": 1,
            "failed": 0,
            "ok": True,
            "duration_ms": 2000.0,
            "requests_per_second": 0.5,
            "total_cost_usd": 0.000111,
            "avg_queue_ms": 3.0,
            "avg_rate_limit_wait_ms": 2.0,
            "avg_latency_ms": 10.0,
            "avg_ttft_ms": 200.0,
            "avg_decode_tokens_per_second": 25.0,
            "artifacts": [],
        }
    ]


def test_dashboard_html_is_redacted_and_chrome_testable(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    ProviderStore().upsert(
        ProviderConfig(
            name="remote-openai",
            contract=ApiContract.OPENAI,
            base_url="https://api.openai.com/v1",
            remote=True,
            tls_verify=False,
        )
    )
    run_dir = _write_run(tmp_path, run_id="run_test", ok=True)
    _write_run(tmp_path, run_id="run_full_trace", ok=True, raw_trace_mode=RawTraceMode.FULL)
    raw_dir = run_dir / "raw"
    raw_dir.mkdir()
    (raw_dir / "case-one.response.json").write_text(
        json.dumps({"headers": {"Authorization": "Bearer should-not-render"}}),
        encoding="utf-8",
    )
    (run_dir / "report.html").write_text("<html>report</html>", encoding="utf-8")
    (run_dir / "publication.json").write_text("{}", encoding="utf-8")
    (run_dir / "report-card.svg").write_text("<svg></svg>", encoding="utf-8")
    metrics_dir = run_dir / "metrics"
    metrics_dir.mkdir()
    (metrics_dir / "prometheus-summary.json").write_text("{}", encoding="utf-8")

    html = render_dashboard_html(tmp_path, auth_required=True)

    assert "AgentBlaster" in html
    assert 'data-testid="auth-status"' in html
    assert 'data-testid="security-posture-panel"' in html
    assert 'data-testid="posture-auth"' in html
    assert 'data-testid="posture-remote-providers"' in html
    assert "Remote providers" in html
    assert "Remote launch remains blocked unless explicitly allowed." in html
    assert 'data-testid="posture-tls"' in html
    assert "One or more providers disable certificate verification." in html
    assert 'data-testid="posture-raw-traces"' in html
    assert "Full raw trace runs exist" in html
    assert 'data-testid="posture-artifacts"' in html
    assert "allowlisted" in html
    assert 'data-testid="launch-form"' in html
    assert 'data-testid="catalog-panel"' in html
    assert 'data-testid="catalog-link"' in html
    assert '/api/engine-targets' in html
    assert '/api/models' in html
    assert '/api/workflow-surfaces' in html
    assert '/api/telemetry-mappings' in html
    assert '/api/campaign-preview' in html
    assert 'data-testid="provider-select"' in html
    assert 'data-testid="suite-select"' in html
    assert 'data-testid="runs-table"' in html
    assert 'data-run-id="run_test"' in html
    assert 'data-testid="report-artifact-link"' in html
    assert 'data-testid="report-generate-form"' in html
    assert "/runs/run_test/artifacts/report.html" in html
    assert "/runs/run_test/artifacts/publication.json" in html
    assert "/runs/run_test/artifacts/report-card.svg" in html
    assert "/runs/run_test/artifacts/metrics%2Fprometheus-summary.json" in html
    assert "builtin" in html
    assert "abc123def456" in html
    assert "qwen3-dense / mlx-f16 / ctx 32768" in html
    assert "openai-chat-completions / agentblaster-adapter-v1" in html
    assert "127.0.0.1 / local / tls=verify" in html
    assert "Bearer should-not-render" not in html
    assert "case-one.response.json" not in html


def test_dashboard_run_payload_returns_manifest_summary_and_results(tmp_path) -> None:
    _write_run(tmp_path, run_id="run_test", ok=False)

    payload = dashboard_run_payload(tmp_path, "run_test")

    assert payload["manifest"]["run_id"] == "run_test"
    assert payload["manifest"]["suite_sha256"] == "abc123def4567890"
    assert payload["manifest"]["suite_provenance"]["origin"] == "builtin"
    assert payload["summary"]["failed"] == 1
    assert payload["results"][0]["case_id"] == "case-one"
    assert payload["results"][0]["failure_class"] == "model_quality"


def test_dashboard_provider_and_suite_discovery_is_redacted(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    ProviderStore().upsert(
        ProviderConfig(
            name="local-openai",
            contract=ApiContract.OPENAI,
            base_url="http://127.0.0.1:9999/v1",
            model_metadata=ModelMetadata(architecture="qwen3-dense", quantization="mlx-f16"),
        )
    )

    providers = dashboard_providers()
    suites = dashboard_suites()

    assert providers[0]["name"] == "local-openai"
    assert providers[0]["api_key_ref"] is None
    assert "metrics_url" in providers[0]
    assert providers[0]["tls_verify"] is True
    assert providers[0]["ca_bundle"] is None
    assert providers[0]["model_metadata"]["architecture"] == "qwen3-dense"
    assert any(suite["name"] == "smoke" and "provenance" in suite for suite in suites)


def test_dashboard_planning_catalog_payloads_are_static_and_redaction_safe() -> None:
    models = dashboard_model_targets()
    engine_targets = dashboard_engine_targets()
    workflows = dashboard_workflow_surfaces()
    telemetry = dashboard_telemetry_mappings()
    index = dashboard_catalog_index()
    serialized = json.dumps({
        "models": models,
        "engine_targets": engine_targets,
        "workflows": workflows,
        "telemetry": telemetry,
        "index": index,
    })

    assert models["schema_version"] == "agentblaster.dashboard-model-targets.v1"
    assert {target["id"] for target in models["model_targets"]} >= {"qwen3.6-27b-dense", "gemma-4-31b-dense"}
    assert engine_targets["schema_version"] == "agentblaster.engine-target-catalog.v1"
    assert any(target["id"] == "afm-mlx" for target in engine_targets["targets"])
    assert workflows["schema_version"] == "agentblaster.workflow-surface-catalog.v1"
    assert telemetry["schema_version"] == "agentblaster.telemetry-mapping-catalog.v1"
    assert any(catalog["id"] == "engine-targets" for catalog in index["catalogs"])
    assert "sk-" not in serialized
    assert "Bearer " not in serialized
    assert "Authorization" not in serialized


def test_dashboard_campaign_preview_is_static_and_redaction_safe() -> None:
    preview = dashboard_campaign_preview(
        {
            "providers": ["afm,lm-studio"],
            "targets": ["qwen3.6-27b-dense"],
            "suites": ["smoke,lcp-context"],
            "concurrency": ["2"],
            "output_dir": ["campaigns/local"],
        }
    )
    serialized = json.dumps(preview)

    assert preview["schema_version"] == "agentblaster.campaign-preview.v1"
    assert preview["providers"] == ["afm", "lm-studio"]
    assert preview["suites"] == ["smoke", "lcp-context"]
    assert preview["matrix_run_count"] == 4
    assert preview["safety"]["preview_only"] is True
    assert preview["safety"]["writes_files"] is False
    assert preview["safety"]["contacts_providers"] is False
    assert preview["write_command"][:3] == ["agentblaster", "models", "campaign-plan"]
    assert "sk-" not in serialized
    assert "Bearer " not in serialized
    assert "Authorization" not in serialized


def test_dashboard_http_handler_serves_html_api_and_report_artifacts(tmp_path) -> None:
    run_dir = _write_run(tmp_path, run_id="run_test", ok=True)
    (run_dir / "report-card.svg").write_text("<svg>card</svg>", encoding="utf-8")
    metrics_dir = run_dir / "metrics"
    metrics_dir.mkdir()
    (metrics_dir / "prometheus-summary.json").write_text(
        '{"format":"agentblaster-prometheus-summary-v1"}',
        encoding="utf-8",
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_dashboard_handler(tmp_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        html_response = httpx.get(base_url, timeout=2.0)
        api_response = httpx.get(f"{base_url}/api/runs", timeout=2.0)
        run_response = httpx.get(f"{base_url}/api/runs/run_test", timeout=2.0)
        generated_response = httpx.post(
            f"{base_url}/api/runs/run_test/reports",
            json={"formats": ["html", "publication", "card"]},
            timeout=2.0,
        )
        form_generate_response = httpx.post(
            f"{base_url}/runs/run_test/reports",
            data={"formats": "md,json"},
            timeout=2.0,
        )
        artifact_response = httpx.get(f"{base_url}/runs/run_test/artifacts/report-card.svg", timeout=2.0)
        metrics_response = httpx.get(
            f"{base_url}/runs/run_test/artifacts/metrics%2Fprometheus-summary.json",
            timeout=2.0,
        )
        blocked_response = httpx.get(f"{base_url}/runs/run_test/artifacts/manifest.json", timeout=2.0)

        assert html_response.status_code == 200
        assert html_response.headers["x-content-type-options"] == "nosniff"
        assert "form-action 'self'" in html_response.headers["content-security-policy"]
        assert api_response.json()["runs"][0]["run_id"] == "run_test"
        assert api_response.json()["runs"][0]["artifacts"][0]["name"] == "report-card.svg"
        assert run_response.json()["summary"]["passed"] == 1
        assert generated_response.status_code == 201
        assert generated_response.json()["reports"]["run_id"] == "run_test"
        assert any(item["name"] == "report.html" for item in generated_response.json()["reports"]["generated"])
        assert form_generate_response.status_code == 303
        assert form_generate_response.headers["location"] == "/?reports=run_test"
        assert artifact_response.status_code == 200
        assert artifact_response.headers["content-type"].startswith("image/svg+xml")
        assert "card" in artifact_response.text
        assert metrics_response.status_code == 200
        assert metrics_response.json()["format"] == "agentblaster-prometheus-summary-v1"
        assert blocked_response.status_code == 404
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_http_handler_serves_planning_catalog_apis(tmp_path) -> None:
    _write_run(tmp_path, run_id="run_test", ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_dashboard_handler(tmp_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        catalogs = httpx.get(f"{base_url}/api/catalogs", timeout=2.0)
        models = httpx.get(f"{base_url}/api/models", timeout=2.0)
        engine_targets = httpx.get(f"{base_url}/api/engine-targets", timeout=2.0)
        workflows = httpx.get(f"{base_url}/api/workflow-surfaces", timeout=2.0)
        telemetry = httpx.get(f"{base_url}/api/telemetry-mappings", timeout=2.0)
        campaign = httpx.get(f"{base_url}/api/campaign-preview?providers=afm&targets=qwen3.6-27b-dense&suites=smoke,lcp-context", timeout=2.0)

        assert catalogs.status_code == 200
        assert any(item["href"] == "/api/engine-targets" for item in catalogs.json()["catalogs"])
        assert models.json()["schema_version"] == "agentblaster.dashboard-model-targets.v1"
        assert engine_targets.json()["schema_version"] == "agentblaster.engine-target-catalog.v1"
        assert workflows.json()["schema_version"] == "agentblaster.workflow-surface-catalog.v1"
        assert telemetry.json()["schema_version"] == "agentblaster.telemetry-mapping-catalog.v1"
        assert campaign.json()["schema_version"] == "agentblaster.campaign-preview.v1"
        assert campaign.json()["matrix_run_count"] == 2
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_http_handler_supports_token_auth_for_browser_and_api(tmp_path) -> None:
    _write_run(tmp_path, run_id="run_test", ok=True)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        make_dashboard_handler(tmp_path, auth_token="dashboard-secret-token"),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        unauthenticated_html = httpx.get(base_url, timeout=2.0)
        login_response = httpx.get(f"{base_url}/login", timeout=2.0)
        unauthenticated_api = httpx.get(f"{base_url}/api/runs", timeout=2.0)
        bad_login = httpx.post(f"{base_url}/login", data={"token": "wrong-token"}, timeout=2.0)
        bearer_response = httpx.get(
            f"{base_url}/api/runs",
            headers={"authorization": "Bearer dashboard-secret-token"},
            timeout=2.0,
        )
        browser = httpx.Client(base_url=base_url, follow_redirects=False)
        good_login = browser.post("/login", data={"token": "dashboard-secret-token"}, timeout=2.0)
        cookie_html = browser.get("/", timeout=2.0)
        logout = browser.get("/logout", timeout=2.0)

        assert unauthenticated_html.status_code == 303
        assert unauthenticated_html.headers["location"] == "/login"
        assert login_response.status_code == 200
        assert 'data-testid="dashboard-login"' in login_response.text
        assert unauthenticated_api.status_code == 401
        assert unauthenticated_api.headers["www-authenticate"] == 'Bearer realm="AgentBlaster Dashboard"'
        assert bad_login.status_code == 401
        assert "wrong-token" not in bad_login.text
        assert bearer_response.status_code == 200
        assert bearer_response.json()["runs"][0]["run_id"] == "run_test"
        assert good_login.status_code == 303
        assert "agentblaster_dashboard=" in good_login.headers["set-cookie"]
        assert "dashboard-secret-token" not in good_login.headers["set-cookie"]
        assert cookie_html.status_code == 200
        assert 'data-testid="auth-status"' in cookie_html.text
        assert logout.status_code == 303
        browser.close()
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_artifact_path_allows_only_report_artifacts(tmp_path) -> None:
    run_dir = _write_run(tmp_path, run_id="run_test", ok=True)
    (run_dir / "publication.json").write_text("{}", encoding="utf-8")
    metrics_dir = run_dir / "metrics"
    metrics_dir.mkdir()
    (metrics_dir / "prometheus-summary.json").write_text("{}", encoding="utf-8")

    assert dashboard_artifact_path(tmp_path, "run_test", "publication.json") == run_dir / "publication.json"
    assert (
        dashboard_artifact_path(tmp_path, "run_test", "metrics/prometheus-summary.json")
        == run_dir / "metrics/prometheus-summary.json"
    )
    with pytest.raises(ConfigError, match="unknown dashboard artifact"):
        dashboard_artifact_path(tmp_path, "run_test", "manifest.json")


def test_dashboard_http_handler_can_launch_local_run(monkeypatch, tmp_path) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            content_length = int(self.headers.get("content-length", "0"))
            if content_length:
                self.rfile.read(content_length)
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "choices": [{"message": {"content": "agentblaster-ok"}, "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
                    }
                ).encode()
            )

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

    provider_server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    provider_thread = threading.Thread(target=provider_server.serve_forever, daemon=True)
    provider_thread.start()
    dashboard_server = None

    try:
        monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
        ProviderStore().upsert(
            ProviderConfig(
                name="local-openai",
                contract=ApiContract.OPENAI,
                base_url=f"http://127.0.0.1:{provider_server.server_address[1]}/v1",
            )
        )
        runs_dir = tmp_path / "runs"
        dashboard_server = ThreadingHTTPServer(("127.0.0.1", 0), make_dashboard_handler(runs_dir))
        dashboard_thread = threading.Thread(target=dashboard_server.serve_forever, daemon=True)
        dashboard_thread.start()
        base_url = f"http://127.0.0.1:{dashboard_server.server_address[1]}"

        response = httpx.post(
            f"{base_url}/api/runs",
            json={
                "provider": "local-openai",
                "suite": "smoke",
                "model": "qwen-test",
                "no_raw_traces": True,
            },
            timeout=3.0,
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["summary"]["provider"] == "local-openai"
        assert payload["summary"]["passed"] == 1
        assert list(runs_dir.glob("*/results.jsonl"))

        form_response = httpx.post(
            f"{base_url}/launch",
            data={
                "provider": "local-openai",
                "suite": "smoke",
                "model": "qwen-test",
                "raw_traces": "off",
                "concurrency": "1",
            },
            timeout=3.0,
        )

        assert form_response.status_code == 303
        assert form_response.headers["location"].startswith("/?launched=run_")
    finally:
        provider_server.shutdown()
        provider_server.server_close()
        if dashboard_server is not None:
            dashboard_server.shutdown()
            dashboard_server.server_close()


def test_dashboard_blocks_non_loopback_bind_without_opt_in() -> None:
    with pytest.raises(ConfigError, match="loopback"):
        assert_dashboard_bind_allowed("0.0.0.0")

    with pytest.raises(ConfigError, match="authentication"):
        assert_dashboard_bind_allowed("0.0.0.0", allow_non_loopback=True)

    assert_dashboard_bind_allowed("0.0.0.0", allow_non_loopback=True, auth_configured=True)


def _write_run(tmp_path, *, run_id: str, ok: bool, raw_trace_mode: RawTraceMode = RawTraceMode.REDACTED):
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    manifest = RunManifest(
        run_id=run_id,
        suite="smoke",
        provider="local",
        contract=ApiContract.OPENAI,
        model="qwen-test",
        raw_trace_mode=raw_trace_mode,
        created_at="2026-05-31T00:00:00Z",
        case_count=1,
        concurrency=2,
        suite_sha256="abc123def4567890",
        suite_snapshot_path="suite.json",
        suite_provenance={
            "origin": "builtin",
            "primary_source": "AgentBlaster",
            "license": "MIT",
        },
        provider_metadata={
            "base_url": "http://127.0.0.1:9999/v1",
            "base_url_host": "127.0.0.1",
            "remote": False,
            "adapter_name": "openai-chat-completions",
            "adapter_version": "agentblaster-adapter-v1",
            "capabilities": {"streaming": True},
        },
        metrics_artifacts=["metrics/prometheus-summary.json"],
        model_metadata=ModelMetadata(
            revision="rev-1",
            architecture="qwen3-dense",
            quantization="mlx-f16",
            context_length=32768,
        ),
    )
    result = BenchmarkResult(
        run_id=run_id,
        case_id="case-one",
        suite="smoke",
        provider="local",
        contract=ApiContract.OPENAI,
        model="qwen-test",
        ok=ok,
        request_started_at="2026-05-31T00:00:00+00:00",
        request_completed_at="2026-05-31T00:00:02+00:00",
        queue_ms=3.0,
        rate_limit_wait_ms=2.0,
        latency_ms=10.0,
        ttft_ms=200.0,
        total_cost_usd=0.000111,
        input_tokens=2,
        output_tokens=1,
        total_tokens=3,
        tokens_per_second_decode=25.0,
        failure_class=None if ok else "model_quality",
        message="ok" if ok else "missing expected substring",
        raw_response_path="raw/case-one.response.json",
    )
    (run_dir / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    (run_dir / "results.jsonl").write_text(result.model_dump_json() + "\n", encoding="utf-8")
    return run_dir
