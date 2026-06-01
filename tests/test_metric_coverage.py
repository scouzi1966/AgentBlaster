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
    assert openai_fields["provider_request_id"]["source"] == "agentblaster_http safe request-id headers"
    assert openai_fields["provider_rate_limit_remaining"]["status"] == "conditional"
    assert openai_fields["cache_write_tokens"]["status"] == "unavailable"
    assert openai_fields["canceled"]["status"] == "measured"
    assert openai_fields["cancellation_latency_ms"]["source"] == "streaming adapter timer"
    assert openai_fields["tool_loop_stop_reason"]["status"] == "measured"
    assert openai_fields["invalid_tool_call_count"]["source"] == "AgentBlaster validator"
    assert openai_fields["tool_parser_repair_valid"]["status"] == "measured"
    assert openai_fields["judge_verdict_valid"]["source"] == "AgentBlaster validator"
    assert openai["comparability"]["group_count"] == 4
    assert openai["claim_contract"]["schema_version"] == "agentblaster.metric-claim-contract.v1"
    assert openai["claim_contract"]["disclosure_required_groups"]
    assert openai["claim_contract"]["primary_score_policy"] == "standardized-primary-ranking-allowed-when-run-telemetry-audit-passes"
    token_group = next(group for group in openai["comparability"]["groups"] if group["id"] == "token_and_cache_accounting")
    assert token_group["status"] == "partial"
    assert "cache_write_tokens" in token_group["unavailable_fields"]
    token_claim = next(group for group in openai["claim_contract"]["groups"] if group["id"] == "token_and_cache_accounting")
    assert token_claim["claim_status"] == "limited"
    assert token_claim["disclosure_required"] is True
    assert anthropic_fields["cached_input_tokens"]["source"] == "usage.cache_read_input_tokens"
    assert anthropic_fields["cache_write_tokens"]["status"] == "native"
    anthropic_token_group = next(
        group for group in anthropic["comparability"]["groups"] if group["id"] == "token_and_cache_accounting"
    )
    assert anthropic_token_group["status"] == "advisory-only"
    assert "cache_hit_ratio" in anthropic_token_group["advisory_fields"]


def test_metric_coverage_catalog_includes_native_engine_mappings() -> None:
    catalog = metric_coverage_catalog()
    providers = {entry["provider"]["name"]: entry for entry in catalog["providers"]}

    assert catalog["schema_version"] == "agentblaster.metric-coverage-catalog.v1"
    assert "ollama-native" in providers
    assert "lm-studio-native" in providers
    assert "afm-mlx-openai-compatible" in providers
    assert "mlx-lm-openai-compatible" in providers
    assert "rapid-mlx-openai-compatible" in providers
    assert "omlx-openai-compatible" in providers
    assert "lm-studio-anthropic" in providers
    assert "vllm-mlx-anthropic" in providers
    afm_fields = {field["field"]: field for field in providers["afm-mlx-openai-compatible"]["fields"]}
    ollama_fields = {field["field"]: field for field in providers["ollama-native"]["fields"]}
    rapid_fields = {field["field"]: field for field in providers["rapid-mlx-openai-compatible"]["fields"]}
    lmstudio_anthropic_fields = {field["field"]: field for field in providers["lm-studio-anthropic"]["fields"]}
    assert afm_fields["prompt_eval_ms"]["status"] == "native"
    assert afm_fields["tokens_per_second_prefill"]["source"] == "native stats/metrics prefill TPS or derived from prompt tokens and explicit prefill duration"
    assert rapid_fields["prompt_eval_ms"]["status"] == "conditional"
    assert ollama_fields["prompt_eval_ms"]["source"] == "prompt_eval_duration"
    assert ollama_fields["tokens_per_second_prefill"]["status"] == "inferred"
    assert providers["ollama-native"]["comparability"]["publication_grade_group_count"] >= 1
    assert lmstudio_anthropic_fields["cache_write_tokens"]["source"] == "usage.cache_creation_input_tokens"
    assert lmstudio_anthropic_fields["tool_parser_repair_valid"]["status"] == "measured"
    assert lmstudio_anthropic_fields["judge_verdict_valid"]["status"] == "measured"


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
    assert "comparability:" in result.output
    assert "claim_contract:" in result.output
    assert output_json.exists()


def test_cli_metric_coverage_catalog_does_not_require_provider(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    runner = CliRunner()

    result = runner.invoke(app, ["providers", "metric-coverage", "--catalog"])

    assert result.exit_code == 0, result.output
    assert "AgentBlaster metric coverage catalog" in result.output
    assert "ollama-native" in result.output
    assert "publication_groups=" in result.output
