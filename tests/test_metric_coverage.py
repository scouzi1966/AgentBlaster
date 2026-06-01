from __future__ import annotations

from typer.testing import CliRunner

from agentblaster.cli import app
from agentblaster.config import ProviderStore
from agentblaster.metric_coverage import metric_coverage_catalog, metric_coverage_for_provider
from agentblaster.models import ApiContract, ProviderConfig


def test_metric_coverage_reports_contract_specific_token_and_cache_sources() -> None:
    openai = metric_coverage_for_provider(
        ProviderConfig(name="openai-like", contract=ApiContract.OPENAI, base_url="http://127.0.0.1:9999/v1")
    )
    anthropic = metric_coverage_for_provider(
        ProviderConfig(name="anthropic-like", contract=ApiContract.ANTHROPIC, base_url="http://127.0.0.1:9999/v1")
    )

    openai_fields = {field["field"]: field for field in openai["fields"]}
    anthropic_fields = {field["field"]: field for field in anthropic["fields"]}

    assert openai["schema_version"] == "agentblaster.metric-coverage.v1"
    assert openai_fields["input_tokens"]["source"] == "usage.prompt_tokens"
    assert openai_fields["cache_write_tokens"]["status"] == "unavailable"
    assert anthropic_fields["cached_input_tokens"]["source"] == "usage.cache_read_input_tokens"
    assert anthropic_fields["cache_write_tokens"]["status"] == "native"


def test_metric_coverage_catalog_includes_native_engine_mappings() -> None:
    catalog = metric_coverage_catalog()
    providers = {entry["provider"]["name"]: entry for entry in catalog["providers"]}

    assert catalog["schema_version"] == "agentblaster.metric-coverage-catalog.v1"
    assert "ollama-native" in providers
    assert "lm-studio-native" in providers
    ollama_fields = {field["field"]: field for field in providers["ollama-native"]["fields"]}
    assert ollama_fields["prompt_eval_ms"]["source"] == "prompt_eval_duration"
    assert ollama_fields["tokens_per_second_prefill"]["status"] == "inferred"


def test_cli_metric_coverage_writes_provider_report(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    ProviderStore().upsert(
        ProviderConfig(name="mock-openai", contract=ApiContract.OPENAI, base_url="http://127.0.0.1:8787/v1")
    )
    output_json = tmp_path / "metric-coverage.json"
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["providers", "metric-coverage", "--provider", "mock-openai", "--output-json", str(output_json)],
    )

    assert result.exit_code == 0, result.output
    assert "AgentBlaster metric coverage" in result.output
    assert "mock-openai (openai)" in result.output
    assert output_json.exists()


def test_cli_metric_coverage_catalog_does_not_require_provider(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    runner = CliRunner()

    result = runner.invoke(app, ["providers", "metric-coverage", "--catalog"])

    assert result.exit_code == 0, result.output
    assert "AgentBlaster metric coverage catalog" in result.output
    assert "ollama-native" in result.output
