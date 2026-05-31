from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from typer.testing import CliRunner

from agentblaster.cli import app


def test_cli_adds_and_lists_provider(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path))
    runner = CliRunner()

    add_result = runner.invoke(
        app,
        [
            "providers",
            "add",
            "--name",
            "openai",
            "--contract",
            "openai",
            "--base-url",
            "https://api.openai.com/v1",
            "--api-key-env",
            "OPENAI_API_KEY",
            "--remote",
        ],
    )
    assert add_result.exit_code == 0, add_result.output

    list_result = runner.invoke(app, ["providers", "list"])

    assert list_result.exit_code == 0, list_result.output
    assert "openai\topenai\thttps://api.openai.com/v1" in list_result.output
    assert "secret=env:OPENAI_API_KEY" in list_result.output


def test_cli_adds_provider_from_preset(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path))
    runner = CliRunner()

    presets_result = runner.invoke(app, ["providers", "presets"])
    assert presets_result.exit_code == 0, presets_result.output
    assert "afm\topenai\thttp://127.0.0.1:9999/v1" in presets_result.output

    add_result = runner.invoke(app, ["providers", "add-preset", "--preset", "afm"])
    assert add_result.exit_code == 0, add_result.output

    list_result = runner.invoke(app, ["providers", "list"])
    assert list_result.exit_code == 0, list_result.output
    assert "afm\topenai\thttp://127.0.0.1:9999/v1" in list_result.output


def test_cli_auth_test_resolves_env_secret(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    runner = CliRunner()

    runner.invoke(
        app,
        [
            "providers",
            "add",
            "--name",
            "openai",
            "--contract",
            "openai",
            "--base-url",
            "https://api.openai.com/v1",
            "--api-key-env",
            "OPENAI_API_KEY",
        ],
    )
    result = runner.invoke(app, ["providers", "auth", "test", "--provider", "openai"])

    assert result.exit_code == 0, result.output
    assert "secret reference resolves for openai" in result.output


def test_cli_validate_case_accepts_suite_file(tmp_path) -> None:
    path = tmp_path / "suite.yaml"
    path.write_text(
        """
name: local-smoke
description: Local smoke suite
cases:
  - id: case-one
    title: Case one
    prompt: "Reply with exactly: agentblaster-ok"
    expected_substring: agentblaster-ok
""",
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(app, ["validate-case", str(path)])

    assert result.exit_code == 0, result.output
    assert "valid suite local-smoke with 1 case(s)" in result.output


def test_cli_run_smoke_writes_artifacts(monkeypatch, tmp_path) -> None:
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
                        "choices": [{"message": {"content": "agentblaster-ok"}}],
                        "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
                    }
                ).encode()
            )

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
        runner = CliRunner()
        base_url = f"http://127.0.0.1:{server.server_address[1]}/v1"

        add_result = runner.invoke(
            app,
            [
                "providers",
                "add",
                "--name",
                "local-openai",
                "--contract",
                "openai",
                "--base-url",
                base_url,
            ],
        )
        assert add_result.exit_code == 0, add_result.output

        run_result = runner.invoke(
            app,
            [
                "run",
                "--suite",
                "smoke",
                "--engine",
                "local-openai",
                "--model",
                "qwen-test",
                "--output-dir",
                str(tmp_path / "runs"),
                "--no-raw-traces",
            ],
        )

        assert run_result.exit_code == 0, run_result.output
        assert "ok: true" in run_result.output
        assert "total_cases: 1" in run_result.output
        assert "run_id:" in run_result.output
        assert list((tmp_path / "runs").glob("*/results.jsonl"))
    finally:
        server.shutdown()


def test_cli_run_suite_file(monkeypatch, tmp_path) -> None:
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
                        "choices": [{"message": {"content": "agentblaster-ok"}}],
                        "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
                    }
                ).encode()
            )

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

    suite_file = tmp_path / "suite.yaml"
    suite_file.write_text(
        """
name: custom-smoke
description: Custom smoke suite
cases:
  - id: custom-case
    title: Custom case
    prompt: "Reply with exactly: agentblaster-ok"
    expected_substring: agentblaster-ok
""",
        encoding="utf-8",
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
        runner = CliRunner()
        base_url = f"http://127.0.0.1:{server.server_address[1]}/v1"
        runner.invoke(
            app,
            [
                "providers",
                "add",
                "--name",
                "local-openai",
                "--contract",
                "openai",
                "--base-url",
                base_url,
            ],
        )

        result = runner.invoke(
            app,
            [
                "run",
                "--suite-file",
                str(suite_file),
                "--engine",
                "local-openai",
                "--model",
                "qwen-test",
                "--output-dir",
                str(tmp_path / "runs"),
                "--no-raw-traces",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "suite: custom-smoke" in result.output
        assert list((tmp_path / "runs").glob("*/summary.json"))
    finally:
        server.shutdown()


def test_cli_run_offline_blocks_remote_provider(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    runner = CliRunner()

    add_result = runner.invoke(
        app,
        [
            "providers",
            "add",
            "--name",
            "openai",
            "--contract",
            "openai",
            "--base-url",
            "https://api.openai.com/v1",
            "--remote",
        ],
    )
    assert add_result.exit_code == 0, add_result.output

    result = runner.invoke(
        app,
        [
            "run",
            "--suite",
            "smoke",
            "--engine",
            "openai",
            "--model",
            "qwen-test",
            "--offline",
        ],
    )

    assert result.exit_code != 0
    assert "remote providers are disabled" in result.output


def test_cli_report_generates_html_json_and_audit(monkeypatch, tmp_path) -> None:
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
                        "choices": [{"message": {"content": "agentblaster-ok"}}],
                        "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
                    }
                ).encode()
            )

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
        runner = CliRunner()
        base_url = f"http://127.0.0.1:{server.server_address[1]}/v1"
        runner.invoke(
            app,
            [
                "providers",
                "add",
                "--name",
                "local-openai",
                "--contract",
                "openai",
                "--base-url",
                base_url,
            ],
        )
        run_result = runner.invoke(
            app,
            [
                "run",
                "--suite",
                "smoke",
                "--engine",
                "local-openai",
                "--model",
                "qwen-test",
                "--output-dir",
                str(tmp_path / "runs"),
                "--no-raw-traces",
                "--audit-log",
                str(tmp_path / "audit.jsonl"),
            ],
        )
        assert run_result.exit_code == 0, run_result.output
        run_dir = next((tmp_path / "runs").glob("*"))

        report_result = runner.invoke(app, ["report", str(run_dir), "--format", "html,json"])

        assert report_result.exit_code == 0, report_result.output
        assert (run_dir / "report.html").exists()
        assert (run_dir / "summary.json").exists()
        assert "run_completed" in (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    finally:
        server.shutdown()
