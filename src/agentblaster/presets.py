from __future__ import annotations

from pydantic import BaseModel, Field

from agentblaster.errors import ConfigError
from agentblaster.models import ApiContract, ProviderConfig, SecretRef


class ProviderPreset(BaseModel):
    name: str
    description: str
    contract: ApiContract
    base_url: str
    api_key_env: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    capabilities: dict[str, bool] = Field(default_factory=dict)
    metrics_url: str | None = None
    native_adapter: str | None = None
    remote: bool = False

    def to_provider(
        self,
        *,
        name: str | None = None,
        base_url: str | None = None,
        api_key_env: str | None = None,
    ) -> ProviderConfig:
        resolved_api_key_env = api_key_env or self.api_key_env
        return ProviderConfig(
            name=name or self.name,
            contract=self.contract,
            base_url=base_url or self.base_url,
            api_key_ref=SecretRef(kind="env", name=resolved_api_key_env) if resolved_api_key_env else None,
            headers=dict(self.headers),
            capabilities=dict(self.capabilities),
            metrics_url=self.metrics_url,
            native_adapter=self.native_adapter,
            remote=self.remote,
        )


OPENAI_AGENTIC_LOCAL_CAPABILITIES = {
    "streaming": True,
    "structured_output": True,
    "judge_rubric": True,
    "tool_calling": True,
    "tool_loop": True,
    "trace_replay": True,
    "cancellation": True,
}

OPENAI_CHAT_LOCAL_CAPABILITIES = {
    "streaming": True,
    "trace_replay": True,
    "cancellation": True,
}

OPENAI_RESPONSES_LOCAL_CAPABILITIES = {
    "streaming": True,
    "structured_output": True,
    "judge_rubric": True,
    "tool_calling": True,
    "tool_loop": True,
    "trace_replay": True,
    "responses_api": True,
    "cancellation": True,
}

ANTHROPIC_LOCAL_CAPABILITIES = {
    "streaming": True,
    "tool_calling": True,
    "tool_loop": True,
    "trace_replay": True,
    "cancellation": True,
}

NATIVE_LOCAL_CAPABILITIES = {
    "streaming": True,
    "trace_replay": True,
    "cancellation": True,
}


LOCAL_ENGINE_PRESETS: dict[str, ProviderPreset] = {
    "afm": ProviderPreset(
        name="afm",
        description="AFM OpenAI-compatible local server",
        contract=ApiContract.OPENAI,
        base_url="http://127.0.0.1:9999/v1",
        capabilities=OPENAI_AGENTIC_LOCAL_CAPABILITIES,
    ),
    "mlx-lm": ProviderPreset(
        name="mlx-lm",
        description="mlx-lm OpenAI-compatible local server",
        contract=ApiContract.OPENAI,
        base_url="http://127.0.0.1:8080/v1",
        capabilities=OPENAI_CHAT_LOCAL_CAPABILITIES,
    ),
    "ollama": ProviderPreset(
        name="ollama",
        description="Ollama OpenAI-compatible local server",
        contract=ApiContract.OPENAI,
        base_url="http://127.0.0.1:11434/v1",
        capabilities=OPENAI_CHAT_LOCAL_CAPABILITIES,
    ),
    "ollama-native": ProviderPreset(
        name="ollama-native",
        description="Ollama native local server with engine-native metrics",
        contract=ApiContract.NATIVE,
        base_url="http://127.0.0.1:11434",
        native_adapter="ollama",
        capabilities=NATIVE_LOCAL_CAPABILITIES,
    ),
    "lm-studio": ProviderPreset(
        name="lm-studio",
        description="LM Studio OpenAI-compatible local server",
        contract=ApiContract.OPENAI,
        base_url="http://127.0.0.1:1234/v1",
        capabilities=OPENAI_AGENTIC_LOCAL_CAPABILITIES,
    ),
    "lm-studio-responses": ProviderPreset(
        name="lm-studio-responses",
        description="LM Studio OpenAI Responses-compatible local server",
        contract=ApiContract.OPENAI_RESPONSES,
        base_url="http://127.0.0.1:1234/v1",
        capabilities=OPENAI_RESPONSES_LOCAL_CAPABILITIES,
    ),
    "lm-studio-anthropic": ProviderPreset(
        name="lm-studio-anthropic",
        description="LM Studio Anthropic Messages-compatible local server",
        contract=ApiContract.ANTHROPIC,
        base_url="http://127.0.0.1:1234/v1",
        headers={"anthropic-version": "2023-06-01"},
        capabilities=ANTHROPIC_LOCAL_CAPABILITIES,
    ),
    "lm-studio-native": ProviderPreset(
        name="lm-studio-native",
        description="LM Studio native REST API with engine-native stats",
        contract=ApiContract.NATIVE,
        base_url="http://127.0.0.1:1234",
        native_adapter="lm-studio",
        capabilities=NATIVE_LOCAL_CAPABILITIES,
    ),
    "omlx": ProviderPreset(
        name="omlx",
        description="oMLX OpenAI-compatible local server",
        contract=ApiContract.OPENAI,
        base_url="http://127.0.0.1:8000/v1",
        capabilities=OPENAI_AGENTIC_LOCAL_CAPABILITIES,
    ),
    "rapid-mlx": ProviderPreset(
        name="rapid-mlx",
        description="Rapid-MLX OpenAI-compatible local server",
        contract=ApiContract.OPENAI,
        base_url="http://127.0.0.1:8000/v1",
        capabilities=OPENAI_AGENTIC_LOCAL_CAPABILITIES,
    ),
    "vllm-mlx": ProviderPreset(
        name="vllm-mlx",
        description="vLLM-MLX OpenAI-compatible local server",
        contract=ApiContract.OPENAI,
        base_url="http://127.0.0.1:8000/v1",
        capabilities=OPENAI_AGENTIC_LOCAL_CAPABILITIES,
    ),
    "vllm-mlx-anthropic": ProviderPreset(
        name="vllm-mlx-anthropic",
        description="vLLM-MLX Anthropic Messages-compatible local server",
        contract=ApiContract.ANTHROPIC,
        base_url="http://127.0.0.1:8000/v1",
        headers={"anthropic-version": "2023-06-01"},
        capabilities=ANTHROPIC_LOCAL_CAPABILITIES,
    ),
}


CLOUD_PROVIDER_PRESETS: dict[str, ProviderPreset] = {
    "openai": ProviderPreset(
        name="openai",
        description="OpenAI API Chat Completions endpoint",
        contract=ApiContract.OPENAI,
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        capabilities={"streaming": True, "tool_calling": True, "structured_output": True},
        remote=True,
    ),
    "openai-responses": ProviderPreset(
        name="openai-responses",
        description="OpenAI API Responses endpoint",
        contract=ApiContract.OPENAI_RESPONSES,
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        capabilities={"streaming": True, "tool_calling": True, "structured_output": True},
        remote=True,
    ),
    "anthropic": ProviderPreset(
        name="anthropic",
        description="Anthropic Messages API endpoint",
        contract=ApiContract.ANTHROPIC,
        base_url="https://api.anthropic.com/v1",
        api_key_env="ANTHROPIC_API_KEY",
        headers={"anthropic-version": "2023-06-01"},
        capabilities={"streaming": True, "tool_calling": True, "structured_output": False},
        remote=True,
    ),
}


PROVIDER_PRESETS: dict[str, ProviderPreset] = {
    **LOCAL_ENGINE_PRESETS,
    **CLOUD_PROVIDER_PRESETS,
}


def get_preset(name: str) -> ProviderPreset:
    try:
        return PROVIDER_PRESETS[name]
    except KeyError as exc:
        available = ", ".join(sorted(PROVIDER_PRESETS))
        raise ConfigError(f"unknown provider preset: {name}; available presets: {available}") from exc
