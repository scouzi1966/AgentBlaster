from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer

from typer.testing import CliRunner

from agentblaster.cli import app
from agentblaster.config import ProviderStore
from agentblaster.contract_check import build_provider_contract_matrix, provider_contract_plan, run_provider_contract_check
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
    assert report["ok"] is False
    assert report["safety"]["contacts_provider"] is False
    assert report["provider"]["remote"] is True
    assert report["summary"]["planned"] == 5
    assert report["contract_surface"]["schema_version"] == "agentblaster.provider-contract-surface.v1"
    assert report["contract_surface"]["adapter_family"] == "openai-chat-completions"
    assert report["contract_surface"]["auth"]["headers"] == ["Authorization"]
    assert {"GET /models", "POST /chat/completions"} == {
        f"{endpoint['method']} {endpoint['path']}" for endpoint in report["contract_surface"]["endpoints"]
    }
    assert "response_format" in report["contract_surface"]["request_features"]
    tool_check = next(check for check in report["checks"] if check["id"] == "tool-call")
    assert tool_check["declared_capability"] is False
    assert "structured_output" in report["capability_evidence"]["directly_checked"]
    assert report["capability_evidence"]["proxy_checked"][0]["capability"] == "judge_rubric"
    uncovered = {item["capability"]: item for item in report["capability_evidence"]["not_covered"]}
    assert uncovered["tool_parser_repair"]["declared"] is None
    assert "tool-parser-repair benchmark runs" in uncovered["tool_parser_repair"]["note"]


def test_anthropic_contract_plan_discloses_uncovered_cache_and_judge_evidence() -> None:
    provider = ProviderConfig(
        name="local-anthropic",
        contract=ApiContract.ANTHROPIC,
        base_url="http://127.0.0.1:1234/v1",
        capabilities={"prompt_caching": True},
    )

    report = provider_contract_plan(provider, model="test-model")
    uncovered = {item["capability"]: item for item in report["capability_evidence"]["not_covered"]}

    assert report["mode"] == "plan-only"
    assert report["contract_surface"]["adapter_family"] == "anthropic-messages"
    assert report["contract_surface"]["auth"]["headers"] == ["x-api-key", "anthropic-version"]
    assert "POST /messages" in {
        f"{endpoint['method']} {endpoint['path']}" for endpoint in report["contract_surface"]["endpoints"]
    }
    assert "response_format" not in report["contract_surface"]["request_features"]
    assert "prompt_caching" in uncovered
    assert uncovered["prompt_caching"]["declared"] is True
    assert "tool_parser_repair" in uncovered
    assert "judge_rubric" in uncovered
    assert "structured_output" not in report["capability_evidence"]["directly_checked"]


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
        assert report["ok"] is True
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


def test_provider_contract_check_executes_responses_stateful_probe_against_mock_provider() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_mock_provider_handler())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        provider = ProviderConfig(
            name="mock-openai-responses",
            contract=ApiContract.OPENAI_RESPONSES,
            base_url=f"http://127.0.0.1:{server.server_address[1]}/v1",
        )
        report = run_provider_contract_check(provider, model="agentblaster-mock-qwen3.6-27b-dense")

        assert report["mode"] == "executed"
        assert report["ok"] is True
        checks = {check["id"]: check for check in report["checks"]}
        assert "responses-stateful" in checks
        assert checks["responses-stateful"]["status"] == "passed"
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


def test_provider_contract_matrix_plan_deduplicates_provider_model_targets(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    ProviderStore().upsert(
        ProviderConfig(
            name="mock-openai",
            contract=ApiContract.OPENAI,
            base_url="http://127.0.0.1:8787/v1",
            default_model="agentblaster-mock-qwen3.6-27b-dense",
        )
    )
    matrix = tmp_path / "matrix.yaml"
    matrix.write_text(
        "\n".join(
            [
                "name: contract-demo",
                "runs:",
                "  - engine: mock-openai",
                "    suite: smoke",
                "    concurrency: 1",
                "  - engine: mock-openai",
                "    suite: agent-fanout",
                "    concurrency: 4",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = build_provider_contract_matrix(matrix)

    assert report["schema_version"] == "agentblaster.provider-contract-matrix.v1"
    assert report["mode"] == "plan-only"
    assert report["ok"] is False
    assert report["summary"]["targets"] == 1
    assert report["entries"][0]["matrix_indices"] == [1, 2]
    assert report["entries"][0]["suites"] == ["agent-fanout", "smoke"]
    assert report["contract_surfaces"]["openai"]["adapter_family"] == "openai-chat-completions"
    assert report["entries"][0]["contract_surface"]["contract"] == "openai"
    assert "structured_output" in report["capability_evidence"]["directly_checked"]
    assert report["entries"][0]["capability_evidence"]["proxy_checked"][0]["capability"] == "judge_rubric"
    assert report["capability_evidence"]["not_covered_counts"] == {"tool_parser_repair": 1}
    assert report["safety"]["contacts_provider"] is False


def test_cli_matrix_contract_checks_writes_plan(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    ProviderStore().upsert(
        ProviderConfig(
            name="mock-openai",
            contract=ApiContract.OPENAI,
            base_url="http://127.0.0.1:8787/v1",
            default_model="agentblaster-mock-qwen3.6-27b-dense",
        )
    )
    matrix = tmp_path / "matrix.yaml"
    output = tmp_path / "contract-matrix.json"
    matrix.write_text(
        "name: contract-demo\nruns:\n  - engine: mock-openai\n    suite: smoke\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "matrix",
            "contract-checks",
            str(matrix),
            "--output-json",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "AgentBlaster provider contract-check matrix" in result.output
    assert output.exists()
