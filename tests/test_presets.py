from __future__ import annotations

import pytest

from agentblaster.errors import ConfigError
from agentblaster.models import ApiContract
from agentblaster.presets import LOCAL_ENGINE_PRESETS, get_preset


def test_local_engine_presets_include_initial_targets() -> None:
    assert {"afm", "mlx-lm", "ollama", "lm-studio", "omlx", "rapid-mlx", "vllm-mlx"}.issubset(
        LOCAL_ENGINE_PRESETS
    )
    assert LOCAL_ENGINE_PRESETS["afm"].contract == ApiContract.OPENAI
    assert LOCAL_ENGINE_PRESETS["ollama-native"].contract == ApiContract.NATIVE
    assert LOCAL_ENGINE_PRESETS["ollama-native"].native_adapter == "ollama"


def test_preset_to_provider_allows_overrides() -> None:
    provider = get_preset("afm").to_provider(name="afm-dev", base_url="http://127.0.0.1:9998/v1")

    assert provider.name == "afm-dev"
    assert str(provider.base_url).rstrip("/") == "http://127.0.0.1:9998/v1"


def test_get_preset_rejects_unknown_name() -> None:
    with pytest.raises(ConfigError, match="unknown provider preset"):
        get_preset("missing")
