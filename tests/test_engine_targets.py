from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from agentblaster.cli import app
from agentblaster.engine_targets import (
    compact_engine_target_for_provider,
    engine_target_catalog,
    engine_target_catalog_json,
    format_engine_target_catalog,
    get_engine_target,
    get_engine_target_for_provider,
)
from agentblaster.errors import ConfigError


def test_engine_target_catalog_covers_required_local_and_remote_targets() -> None:
    catalog = engine_target_catalog()
    targets = {target["id"]: target for target in catalog["targets"]}

    assert catalog["schema_version"] == "agentblaster.engine-target-catalog.v1"
    assert catalog["representative_agent_profiles"] == ["opencode", "openclaw", "hermes", "pi"]
    assert "mcp-fixtures" in catalog["standard_workflow_surfaces"]
    assert "large repeated system prompts" in catalog["standardization"]["prefill_challenges"]
    assert "agent fan-out bursts" in catalog["standardization"]["concurrency_challenges"]
    assert {
        "afm-mlx",
        "mlx-lm",
        "ollama-mlx",
        "rapid-mlx",
        "omlx",
        "vllm-mlx",
        "lm-studio",
        "remote-openai-compatible",
        "remote-anthropic-compatible",
    } <= set(targets)
    assert catalog["summary"]["primary_target"] == "afm-mlx"
    assert catalog["summary"]["all_declared_presets_available"] is True
    assert catalog["summary"]["all_declared_launch_recipes_available"] is True
    assert targets["afm-mlx"]["recommended_model_targets"] == ["qwen3.6-27b-dense", "gemma-4-31b-dense"]
    assert "agentic-tool-loop" in targets["afm-mlx"]["recommended_suites"]
    assert "agent-fanout" in targets["afm-mlx"]["recommended_suites"]
    assert "cache-control" in targets["afm-mlx"]["recommended_suites"]
    assert "harness-engineering" in targets["afm-mlx"]["recommended_suites"]
    assert "cancellation" in targets["afm-mlx"]["recommended_suites"]
    assert "agent-fanout" in targets["mlx-lm"]["recommended_suites"]
    assert "harness-engineering" in targets["mlx-lm"]["recommended_suites"]
    assert "ollama-native" in targets["ollama-mlx"]["provider_presets"]
    assert targets["ollama-mlx"]["standardization"]["native_telemetry_profiles"] == ["ollama-native"]
    assert targets["ollama-mlx"]["standardization"]["primary_scoring_contract"] == "openai"
    assert "openai" == targets["ollama-mlx"]["standardization"]["contract_priority"][0]
    assert "harness-engineering" in targets["rapid-mlx"]["recommended_suites"]
    assert "harness-engineering" in targets["omlx"]["recommended_suites"]
    assert "omlx-openai-compatible" in targets["omlx"]["telemetry_profiles"]
    assert targets["omlx"]["standardization"]["native_telemetry_profiles"] == []
    assert "vllm-mlx" in targets["vllm-mlx"]["provider_presets"]
    assert "vllm-mlx-anthropic" in targets["vllm-mlx"]["provider_presets"]
    assert "anthropic" in targets["vllm-mlx"]["contracts"]
    assert "agent-fanout" in targets["vllm-mlx"]["recommended_suites"]
    assert "harness-engineering" in targets["vllm-mlx"]["recommended_suites"]
    assert "lm-studio-native" in targets["lm-studio"]["telemetry_profiles"]
    assert "lm-studio-anthropic" in targets["lm-studio"]["provider_presets"]
    assert "anthropic" in targets["lm-studio"]["contracts"]
    assert targets["lm-studio"]["standardization"]["native_telemetry_profiles"] == ["lm-studio-native"]
    assert targets["remote-openai-compatible"]["remote_contract"] is True
    assert "harness-engineering" in targets["remote-openai-compatible"]["recommended_suites"]
    for target in targets.values():
        assert "harness-engineering" in target["standardization"]["workflow_surfaces"]
        assert "pi" in target["standardization"]["representative_agent_profiles"]
        assert "large repeated system prompts" in target["standardization"]["prefill_challenges"]
        assert "queue fairness under repeated static prefixes" in target["standardization"]["concurrency_challenges"]


def test_engine_target_lookup_json_and_markdown_are_stable() -> None:
    target = get_engine_target("afm-mlx")
    from_preset = get_engine_target_for_provider("afm")
    compact_from_preset = compact_engine_target_for_provider("ollama-native")
    payload = json.loads(engine_target_catalog_json())
    markdown = format_engine_target_catalog(markdown=True)

    assert target["display_name"] == "AFM MLX"
    assert from_preset is not None
    assert from_preset["id"] == "afm-mlx"
    assert compact_from_preset is not None
    assert compact_from_preset["id"] == "ollama-mlx"
    assert compact_from_preset["standardization"]["native_telemetry_profiles"] == ["ollama-native"]
    assert payload["summary"]["target_count"] >= 9
    assert "# AgentBlaster Engine Target Catalog" in markdown
    assert "`afm-mlx`" in markdown
    assert "Primary scoring contract" in markdown


def test_engine_target_lookup_rejects_unknown_targets() -> None:
    with pytest.raises(ConfigError, match="unknown engine target"):
        get_engine_target("missing")
    assert get_engine_target_for_provider("missing-provider") is None
    assert compact_engine_target_for_provider("missing-provider") is None


def test_cli_engine_targets_outputs_catalog_text() -> None:
    result = CliRunner().invoke(app, ["engines", "targets"])

    assert result.exit_code == 0, result.output
    assert "AgentBlaster engine target catalog" in result.output
    assert "afm-mlx" in result.output
    assert "lm-studio" in result.output
