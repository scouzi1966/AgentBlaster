from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from agentblaster.cli import app
from agentblaster.engine_targets import (
    engine_target_catalog,
    engine_target_catalog_json,
    format_engine_target_catalog,
    get_engine_target,
)
from agentblaster.errors import ConfigError


def test_engine_target_catalog_covers_required_local_and_remote_targets() -> None:
    catalog = engine_target_catalog()
    targets = {target["id"]: target for target in catalog["targets"]}

    assert catalog["schema_version"] == "agentblaster.engine-target-catalog.v1"
    assert {
        "afm-mlx",
        "mlx-lm",
        "ollama-mlx",
        "rapid-mlx",
        "omlx",
        "lm-studio",
        "remote-openai-compatible",
        "remote-anthropic-compatible",
    } <= set(targets)
    assert catalog["summary"]["primary_target"] == "afm-mlx"
    assert catalog["summary"]["all_declared_presets_available"] is True
    assert catalog["summary"]["all_declared_launch_recipes_available"] is True
    assert targets["afm-mlx"]["recommended_model_targets"] == ["qwen3.6-27b-dense", "gemma-4-31b-dense"]
    assert "cache-control" in targets["afm-mlx"]["recommended_suites"]
    assert "ollama-native" in targets["ollama-mlx"]["provider_presets"]
    assert "lm-studio-native" in targets["lm-studio"]["telemetry_profiles"]
    assert targets["remote-openai-compatible"]["remote_contract"] is True


def test_engine_target_lookup_json_and_markdown_are_stable() -> None:
    target = get_engine_target("afm-mlx")
    payload = json.loads(engine_target_catalog_json())
    markdown = format_engine_target_catalog(markdown=True)

    assert target["display_name"] == "AFM MLX"
    assert payload["summary"]["target_count"] >= 8
    assert "# AgentBlaster Engine Target Catalog" in markdown
    assert "`afm-mlx`" in markdown


def test_engine_target_lookup_rejects_unknown_targets() -> None:
    with pytest.raises(ConfigError, match="unknown engine target"):
        get_engine_target("missing")


def test_cli_engine_targets_outputs_catalog_text() -> None:
    result = CliRunner().invoke(app, ["engines", "targets"])

    assert result.exit_code == 0, result.output
    assert "AgentBlaster engine target catalog" in result.output
    assert "afm-mlx" in result.output
    assert "lm-studio" in result.output
