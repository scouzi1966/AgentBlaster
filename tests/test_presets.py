from __future__ import annotations

import pytest

from agentblaster.errors import ConfigError
from agentblaster.models import ApiContract
from agentblaster.presets import CLOUD_PROVIDER_PRESETS, LOCAL_ENGINE_PRESETS, PROVIDER_PRESETS, get_preset


def test_local_engine_presets_include_initial_targets() -> None:
    assert {
        "afm",
        "mlx-lm",
        "ollama",
        "ollama-native",
        "lm-studio",
        "lm-studio-responses",
        "lm-studio-anthropic",
        "lm-studio-native",
        "omlx",
        "rapid-mlx",
        "vllm-mlx",
        "vllm-mlx-anthropic",
    }.issubset(LOCAL_ENGINE_PRESETS)
    assert LOCAL_ENGINE_PRESETS["afm"].contract == ApiContract.OPENAI
    assert LOCAL_ENGINE_PRESETS["ollama-native"].contract == ApiContract.NATIVE
    assert LOCAL_ENGINE_PRESETS["ollama-native"].native_adapter == "ollama"
    assert LOCAL_ENGINE_PRESETS["lm-studio-responses"].contract == ApiContract.OPENAI_RESPONSES
    assert LOCAL_ENGINE_PRESETS["lm-studio-anthropic"].contract == ApiContract.ANTHROPIC
    assert LOCAL_ENGINE_PRESETS["lm-studio-anthropic"].headers["anthropic-version"] == "2023-06-01"
    assert LOCAL_ENGINE_PRESETS["lm-studio-native"].contract == ApiContract.NATIVE
    assert LOCAL_ENGINE_PRESETS["lm-studio-native"].native_adapter == "lm-studio"
    assert LOCAL_ENGINE_PRESETS["vllm-mlx-anthropic"].contract == ApiContract.ANTHROPIC


def test_local_engine_presets_declare_campaign_preflight_capabilities() -> None:
    assert LOCAL_ENGINE_PRESETS["afm"].capabilities["tool_calling"] is True
    assert LOCAL_ENGINE_PRESETS["afm"].capabilities["tool_loop"] is True
    assert LOCAL_ENGINE_PRESETS["afm"].capabilities["structured_output"] is True
    assert LOCAL_ENGINE_PRESETS["afm"].capabilities["judge_rubric"] is True
    assert LOCAL_ENGINE_PRESETS["lm-studio-responses"].capabilities["responses_api"] is True
    assert LOCAL_ENGINE_PRESETS["lm-studio-anthropic"].capabilities["tool_calling"] is True
    assert "prompt_caching" not in LOCAL_ENGINE_PRESETS["lm-studio-anthropic"].capabilities
    assert LOCAL_ENGINE_PRESETS["ollama-native"].capabilities["streaming"] is True
    assert all(preset.capabilities for preset in LOCAL_ENGINE_PRESETS.values())


def test_cloud_provider_presets_include_secure_api_key_refs() -> None:
    assert {"openai", "openai-responses", "anthropic"}.issubset(CLOUD_PROVIDER_PRESETS)
    assert {"openai", "anthropic"}.issubset(PROVIDER_PRESETS)
    assert CLOUD_PROVIDER_PRESETS["openai"].remote is True
    assert CLOUD_PROVIDER_PRESETS["openai"].api_key_env == "OPENAI_API_KEY"
    assert CLOUD_PROVIDER_PRESETS["openai-responses"].contract == ApiContract.OPENAI_RESPONSES
    assert CLOUD_PROVIDER_PRESETS["anthropic"].contract == ApiContract.ANTHROPIC
    assert CLOUD_PROVIDER_PRESETS["anthropic"].api_key_env == "ANTHROPIC_API_KEY"
    assert CLOUD_PROVIDER_PRESETS["anthropic"].headers["anthropic-version"] == "2023-06-01"


def test_preset_to_provider_allows_overrides() -> None:
    provider = get_preset("afm").to_provider(name="afm-dev", base_url="http://127.0.0.1:9998/v1")

    assert provider.name == "afm-dev"
    assert str(provider.base_url).rstrip("/") == "http://127.0.0.1:9998/v1"
    assert provider.capabilities["tool_calling"] is True


def test_local_anthropic_preset_preserves_version_header() -> None:
    provider = get_preset("lm-studio-anthropic").to_provider()

    assert provider.contract == ApiContract.ANTHROPIC
    assert provider.headers["anthropic-version"] == "2023-06-01"
    assert provider.api_key_ref is None


def test_cloud_preset_to_provider_sets_remote_env_ref_without_raw_key() -> None:
    provider = get_preset("openai").to_provider()

    assert provider.remote is True
    assert provider.api_key_ref is not None
    assert provider.api_key_ref.kind == "env"
    assert provider.api_key_ref.name == "OPENAI_API_KEY"
    assert str(provider.base_url).rstrip("/") == "https://api.openai.com/v1"


def test_cloud_preset_to_provider_allows_api_key_env_override() -> None:
    provider = get_preset("anthropic").to_provider(api_key_env="WORKSPACE_ANTHROPIC_KEY")

    assert provider.api_key_ref is not None
    assert provider.api_key_ref.name == "WORKSPACE_ANTHROPIC_KEY"
    assert provider.headers["anthropic-version"] == "2023-06-01"


def test_get_preset_rejects_unknown_name() -> None:
    with pytest.raises(ConfigError, match="unknown provider preset"):
        get_preset("missing")
