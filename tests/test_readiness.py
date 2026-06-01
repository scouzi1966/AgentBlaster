from __future__ import annotations

from typer.testing import CliRunner

from agentblaster.cli import app
from agentblaster.config import ProviderStore
from agentblaster.models import ApiContract, BenchmarkCase, ProviderConfig, SuiteDefinition
from agentblaster.policy import load_policy
from agentblaster.readiness import build_readiness_dossier, format_readiness_report


def test_readiness_dossier_combines_policy_capability_contract_and_metrics() -> None:
    provider = ProviderConfig(
        name="local-openai",
        contract=ApiContract.OPENAI,
        base_url="http://127.0.0.1:8787/v1",
        capabilities={"streaming": True, "tool_calling": True, "structured_output": True},
    )
    suite = SuiteDefinition(
        name="agentic-smoke",
        description="agentic smoke",
        cases=[
            BenchmarkCase(
                id="case-one",
                title="case one",
                prompt="Return JSON",
                streaming=True,
                response_format={"type": "json_object"},
                expected_tool_name="ping_agentblaster",
            )
        ],
    )

    report = build_readiness_dossier(
        provider=provider,
        suite=suite,
        policy=load_policy(None),
        model="agentblaster-mock-qwen3.6-27b-dense",
        strict_unknown=True,
    )

    assert report["schema_version"] == "agentblaster.benchmark-readiness.v1"
    assert report["ready"] is True
    assert report["summary"]["policy_ok"] is True
    assert report["summary"]["suite_compatible"] is True
    assert report["summary"]["contract_checks_planned"] == 5
    assert report["metric_coverage"]["provider"]["name"] == "local-openai"
    assert "ready: true" in format_readiness_report(report)


def test_readiness_dossier_blocks_missing_model_and_strict_unknown_capabilities() -> None:
    provider = ProviderConfig(name="local-openai", contract=ApiContract.OPENAI, base_url="http://127.0.0.1:8787/v1")
    suite = SuiteDefinition(
        name="tool-suite",
        description="tool suite",
        cases=[BenchmarkCase(id="case-one", title="case one", prompt="Use tool", expected_tool_name="ping_agentblaster")],
    )

    report = build_readiness_dossier(provider=provider, suite=suite, policy=load_policy(None), strict_unknown=True)

    assert report["ready"] is False
    codes = {finding["code"] for finding in report["blocking_findings"]}
    assert "unknown_tool_calling" in codes
    assert "model_required" in codes


def test_cli_readiness_writes_json_and_exits_nonzero_when_blocked(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    ProviderStore().upsert(
        ProviderConfig(name="local-openai", contract=ApiContract.OPENAI, base_url="http://127.0.0.1:8787/v1")
    )
    output_json = tmp_path / "readiness.json"
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["providers", "readiness", "--provider", "local-openai", "--suite", "smoke", "--output-json", str(output_json)],
    )

    assert result.exit_code == 1
    assert "model_required" in result.output
    assert output_json.exists()
