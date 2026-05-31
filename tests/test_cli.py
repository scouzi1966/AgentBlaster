from __future__ import annotations

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
