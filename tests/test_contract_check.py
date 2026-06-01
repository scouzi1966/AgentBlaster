from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer

from typer.testing import CliRunner

from agentblaster.cli import app
from agentblaster.config import ProviderStore
from agentblaster.contract_check import provider_contract_plan, run_provider_contract_check
from agentblaster.mock_provider import make_mock_provider_handler
from agentblaster.models import ApiContract, ProviderConfig


def test_provider_contract_plan_is_no_network_and_capability_aware() -> None:
    provider = ProviderConfig(
        name="remote-openai",
        contract=ApiContract.OPENAI,
        base_url="https://api.openai.com/v1",
        remote=True,
        capabilities={"streaming": True, "tool_calling": False},
    )

    report = provider_contract_plan(provider, model="test-model")

    assert report["mode"] == "plan-only"
    assert report["safety"]["contacts_provider"] is False
    assert report["provider"]["remote"] is True
    assert report["summary"]["planned"] == 5
    tool_check = next(check for check in report["checks"] if check["id"] == "tool-call")
    assert tool_check["declared_capability"] is False


def test_provider_contract_check_executes_against_mock_openai_provider() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_mock_provider_handler())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        provider = ProviderConfig(
            name="mock-openai",
            contract=ApiContract.OPENAI,
            base_url=f"http://127.0.0.1:{server.server_address[1]}/v1",
        )
        report = run_provider_contract_check(provider, model="agentblaster-mock-qwen3.6-27b-dense")

        assert report["mode"] == "executed"
        assert report["summary"]["failed"] == 0
        assert {check["id"] for check in report["checks"]} == {
            "model-list",
            "exact-chat",
            "streaming-text",
            "structured-json",
            "tool-call",
        }
        assert all(check["status"] == "passed" for check in report["checks"])
    finally:
        server.shutdown()
        server.server_close()


def test_cli_provider_contract_check_defaults_to_plan_only(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    ProviderStore().upsert(
        ProviderConfig(
            name="mock-openai",
            contract=ApiContract.OPENAI,
            base_url="http://127.0.0.1:8787/v1",
        )
    )
    output_json = tmp_path / "contract-check.json"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "providers",
            "contract-check",
            "--provider",
            "mock-openai",
            "--model",
            "agentblaster-mock-qwen3.6-27b-dense",
            "--output-json",
            str(output_json),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "mode: plan-only" in result.output
    assert "PLANNED model-list" in result.output
    assert output_json.exists()
