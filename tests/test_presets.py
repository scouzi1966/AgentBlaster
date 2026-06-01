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
        "lm-studio-native",
        "omlx",
        "rapid-mlx",
        "vllm-mlx",
    }.issubset(LOCAL_ENGINE_PRESETS)
    assert LOCAL_ENGINE_PRESETS["afm"].contract == ApiContract.OPENAI
    assert LOCAL_ENGINE_PRESETS["ollama-native"].contract == ApiContract.NATIVE
    assert LOCAL_ENGINE_PRESETS["ollama-native"].native_adapter == "ollama"
    assert LOCAL_ENGINE_PRESETS["lm-studio-responses"].contract == ApiContract.OPENAI_RESPONSES
    assert LOCAL_ENGINE_PRESETS["lm-studio-native"].contract == ApiContract.NATIVE
    assert LOCAL_ENGINE_PRESETS["lm-studio-native"].native_adapter == "lm-studio"


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
