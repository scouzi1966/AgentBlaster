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


def test_cli_run_smoke_writes_artifacts(monkeypatch, tmp_path) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
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
        assert "run_id:" in run_result.output
        assert list((tmp_path / "runs").glob("*/results.jsonl"))
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
