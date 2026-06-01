from __future__ import annotations

import os
import threading
from http.server import ThreadingHTTPServer

import pytest

from agentblaster.dashboard import make_dashboard_handler
from agentblaster.fixtures import write_dashboard_fixture

pytestmark = pytest.mark.gui


def test_dashboard_fixture_renders_in_optional_browser(tmp_path) -> None:
    browser_tools = pytest.importorskip("playwright.sync_api")
    runs_dir = tmp_path / "dashboard-runs"
    write_dashboard_fixture(runs_dir)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_dashboard_handler(runs_dir))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with browser_tools.sync_playwright() as playwright:
            browser = _launch_browser(playwright, browser_tools)
            page = browser.new_page()
            page.goto(base_url, wait_until="networkidle")

            browser_tools.expect(page.get_by_test_id("runs-table")).to_be_visible()
            browser_tools.expect(page.get_by_test_id("runs-table")).to_contain_text("run_dashboard_fixture_pass")
            browser_tools.expect(page.get_by_test_id("runs-table")).to_contain_text("run_dashboard_fixture_fail")
            browser_tools.expect(page.get_by_test_id("review-artifacts-panel")).to_be_visible()
            browser_tools.expect(page.get_by_test_id("review-artifacts-table")).to_contain_text("dashboard-fixture: model_quality=1")
            browser_tools.expect(page.get_by_test_id("review-artifacts-table")).to_contain_text("tool loops: final_response=2")
            browser_tools.expect(page.get_by_test_id("review-artifacts-table")).to_contain_text("dashboard-fixture-orchestration")
            browser_tools.expect(page.get_by_test_id("review-artifacts-table")).to_contain_text("contract-conformance")
            browser_tools.expect(page.get_by_test_id("launch-form")).to_be_visible()

            html = page.content()
            assert "sk-" not in html
            assert "Authorization" not in html
            assert "Bearer" not in html
            browser.close()
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_fixture_api_and_report_artifacts_are_browser_accessible(tmp_path) -> None:
    browser_tools = pytest.importorskip("playwright.sync_api")
    runs_dir = tmp_path / "dashboard-runs"
    write_dashboard_fixture(runs_dir)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_dashboard_handler(runs_dir))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with browser_tools.sync_playwright() as playwright:
            browser = _launch_browser(playwright, browser_tools)
            page = browser.new_page()

            runs_response = page.request.get(f"{base_url}/api/runs")
            assert runs_response.ok
            runs_body = runs_response.text()
            assert "run_dashboard_fixture_pass" in runs_body
            assert "sk-" not in runs_body
            assert "Authorization" not in runs_body
            review_response = page.request.get(f"{base_url}/api/review-artifacts")
            assert review_response.ok
            review_body = review_response.text()
            assert "dashboard-fixture.agentblaster-release-qualification.zip" in review_body
            assert "model_quality" in review_body
            assert "final_response" in review_body
            assert "dashboard-fixture-orchestration" in review_body
            assert "contract-conformance" in review_body
            assert "results.jsonl" not in review_body

            page.goto(f"{base_url}/runs/run_dashboard_fixture_pass/artifacts/report.html", wait_until="networkidle")
            browser_tools.expect(page.locator("body")).to_contain_text("AgentBlaster fixture report")
            browser_tools.expect(page.locator("body")).to_contain_text("redacted: true")
            pdf_response = page.request.get(f"{base_url}/runs/run_dashboard_fixture_pass/artifacts/report.pdf")
            assert pdf_response.ok
            assert pdf_response.body().startswith(b"%PDF-1.4")
            browser.close()
    finally:
        server.shutdown()
        server.server_close()


def _launch_browser(playwright, browser_tools):
    browser_name = os.environ.get("AGENTBLASTER_GUI_BROWSER", "chromium").strip().lower()
    headed = os.environ.get("AGENTBLASTER_GUI_HEADED") == "1"
    launch_args = {"headless": not headed}
    try:
        if browser_name == "chrome":
            return playwright.chromium.launch(channel="chrome", **launch_args)
        if browser_name == "firefox":
            return playwright.firefox.launch(**launch_args)
        if browser_name == "webkit":
            return playwright.webkit.launch(**launch_args)
        return playwright.chromium.launch(**launch_args)
    except browser_tools.Error as exc:
        pytest.skip(f"browser launch unavailable for {browser_name}: {exc}")
