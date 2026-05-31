from __future__ import annotations

from pydantic import BaseModel

from agentblaster.errors import ConfigError
from agentblaster.models import ApiContract, ProviderConfig


class ProviderPreset(BaseModel):
    name: str
    description: str
    contract: ApiContract
    base_url: str
    native_adapter: str | None = None
    remote: bool = False

    def to_provider(self, *, name: str | None = None, base_url: str | None = None) -> ProviderConfig:
        return ProviderConfig(
            name=name or self.name,
            contract=self.contract,
            base_url=base_url or self.base_url,
            native_adapter=self.native_adapter,
            remote=self.remote,
        )


LOCAL_ENGINE_PRESETS: dict[str, ProviderPreset] = {
    "afm": ProviderPreset(
        name="afm",
        description="AFM OpenAI-compatible local server",
        contract=ApiContract.OPENAI,
        base_url="http://127.0.0.1:9999/v1",
    ),
    "mlx-lm": ProviderPreset(
        name="mlx-lm",
        description="mlx-lm OpenAI-compatible local server",
        contract=ApiContract.OPENAI,
        base_url="http://127.0.0.1:8080/v1",
    ),
    "ollama": ProviderPreset(
        name="ollama",
        description="Ollama OpenAI-compatible local server",
        contract=ApiContract.OPENAI,
        base_url="http://127.0.0.1:11434/v1",
    ),
    "ollama-native": ProviderPreset(
        name="ollama-native",
        description="Ollama native local server with engine-native metrics",
        contract=ApiContract.NATIVE,
        base_url="http://127.0.0.1:11434",
        native_adapter="ollama",
    ),
    "lm-studio": ProviderPreset(
        name="lm-studio",
        description="LM Studio OpenAI-compatible local server",
        contract=ApiContract.OPENAI,
        base_url="http://127.0.0.1:1234/v1",
    ),
    "omlx": ProviderPreset(
        name="omlx",
        description="oMLX OpenAI-compatible local server",
        contract=ApiContract.OPENAI,
        base_url="http://127.0.0.1:8000/v1",
    ),
    "rapid-mlx": ProviderPreset(
        name="rapid-mlx",
        description="Rapid-MLX OpenAI-compatible local server",
        contract=ApiContract.OPENAI,
        base_url="http://127.0.0.1:8000/v1",
    ),
    "vllm-mlx": ProviderPreset(
        name="vllm-mlx",
        description="vLLM-MLX OpenAI-compatible local server",
        contract=ApiContract.OPENAI,
        base_url="http://127.0.0.1:8000/v1",
    ),
}


def get_preset(name: str) -> ProviderPreset:
    try:
        return LOCAL_ENGINE_PRESETS[name]
    except KeyError as exc:
        available = ", ".join(sorted(LOCAL_ENGINE_PRESETS))
        raise ConfigError(f"unknown provider preset: {name}; available presets: {available}") from exc
