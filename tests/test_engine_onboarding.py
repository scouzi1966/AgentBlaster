from __future__ import annotations

import json

from agentblaster.engine_onboarding import (
    DEFAULT_LOCAL_ENGINES,
    build_local_engine_onboarding,
    format_local_engine_onboarding_markdown,
    write_local_engine_onboarding,
)


def test_local_engine_onboarding_covers_original_local_scope() -> None:
    payload = build_local_engine_onboarding()
    engines = {entry["engine"] for entry in payload["engines"]}

    assert payload["schema_version"] == "agentblaster.local-engine-onboarding.v1"
    assert set(DEFAULT_LOCAL_ENGINES) <= engines
    assert payload["safety"]["executes_commands"] is False
    assert payload["safety"]["contacts_providers"] is False
    assert {"qwen3.6-27b-dense", "gemma-4-31b-dense"} <= {target["id"] for target in payload["model_targets"]}
    afm = next(entry for entry in payload["engines"] if entry["engine"] == "afm")
    assert afm["launch_recipe"]["contract"] == "openai"
    assert afm["launch_recipe"]["provider_add_command"][:3] == ["agentblaster", "providers", "add"]
    assert afm["declared_capabilities"]["tool_calling"] is True
    assert afm["declared_capabilities"]["structured_output"] is True
    assert afm["engine_target"]["id"] == "afm-mlx"
    assert afm["engine_target"]["standardization"]["primary_scoring_contract"] == "openai"
    assert "harness-engineering" in afm["engine_target"]["standardization"]["workflow_surfaces"]
    assert "large repeated system prompts" in afm["engine_target"]["standardization"]["prefill_challenges"]
    assert "agent fan-out bursts" in afm["engine_target"]["standardization"]["concurrency_challenges"]
    assert ["agentblaster", "engines", "targets", "--target", "afm-mlx"] in afm["recommended_static_checks"]
    ollama_native = next(entry for entry in payload["engines"] if entry["engine"] == "ollama-native")
    assert ollama_native["engine_target"]["id"] == "ollama-mlx"
    assert ollama_native["engine_target"]["standardization"]["native_telemetry_profiles"] == ["ollama-native"]
    omlx = next(entry for entry in payload["engines"] if entry["engine"] == "omlx")
    assert omlx["engine_target"]["telemetry_profiles"] == ["omlx-openai-compatible"]
    anthropic_local = next(entry for entry in payload["engines"] if entry["engine"] == "lm-studio-anthropic")
    assert anthropic_local["declared_capabilities"]["tool_calling"] is True
    assert "prompt_caching" not in anthropic_local["declared_capabilities"]
    assert anthropic_local["engine_target"]["id"] == "lm-studio"
    assert payload["standardization"]["engine_target_catalog_command"] == ["agentblaster", "engines", "targets"]


def test_local_engine_onboarding_can_render_and_write(tmp_path) -> None:
    payload = build_local_engine_onboarding(engines=["afm", "lm-studio"], model="model-test")
    markdown = format_local_engine_onboarding_markdown(payload)
    output = tmp_path / "local-engine-onboarding.json"

    path = write_local_engine_onboarding(payload, output)

    assert "AgentBlaster Local Engine Onboarding" in markdown
    assert "model-test" in markdown
    assert "Declared capabilities" in markdown
    assert "Engine target" in markdown
    assert "Native metrics policy" in markdown
    assert "`tool_calling=true`" in markdown
    assert path == output
    assert json.loads(output.read_text(encoding="utf-8"))["engine_count"] == 2
