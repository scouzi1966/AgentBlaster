from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from agentblaster.errors import ConfigError
from agentblaster.matrix import MatrixDefinition, MatrixRun
from agentblaster.models import ModelMetadata, RawTraceMode


class ModelTarget(BaseModel):
    """Canonical model target used to keep cross-engine comparisons aligned."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    display_name: str
    family: str
    density: Literal["dense", "moe"] = "dense"
    parameter_count: str
    default_model: str
    metadata: ModelMetadata = Field(default_factory=ModelMetadata)
    notes: str = ""


MODEL_TARGETS: dict[str, ModelTarget] = {
    "qwen3.6-27b-dense": ModelTarget(
        id="qwen3.6-27b-dense",
        display_name="Qwen3.6 27B Dense",
        family="qwen",
        density="dense",
        parameter_count="27B",
        default_model="mlx-community/Qwen3.6-27B",
        metadata=ModelMetadata(
            architecture="qwen3.6-dense",
            chat_template="qwen",
        ),
        notes="Primary dense coding/agentic target for local MLX comparisons.",
    ),
    "gemma-4-31b-dense": ModelTarget(
        id="gemma-4-31b-dense",
        display_name="Gemma 4 31B Dense",
        family="gemma",
        density="dense",
        parameter_count="31B",
        default_model="google/gemma-4-31b",
        metadata=ModelMetadata(
            architecture="gemma-4-dense",
            chat_template="gemma",
        ),
        notes="Dense Gemma 4 quality target for local and remote-compatible comparisons.",
    ),
}


def list_model_targets() -> list[ModelTarget]:
    return list(MODEL_TARGETS.values())


def get_model_target(target_id: str) -> ModelTarget:
    try:
        return MODEL_TARGETS[target_id]
    except KeyError as exc:
        available = ", ".join(sorted(MODEL_TARGETS))
        raise ConfigError(f"unknown model target: {target_id}; available targets: {available}") from exc


def generate_matrix_template(
    *,
    providers: list[str],
    target_ids: list[str],
    suite: str = "smoke",
    suite_file: Path | None = None,
    concurrency: int = 1,
    raw_traces: RawTraceMode = RawTraceMode.REDACTED,
    no_raw_traces: bool = True,
    name: str | None = None,
    description: str | None = None,
) -> MatrixDefinition:
    if not providers:
        raise ConfigError("at least one provider is required")
    if not target_ids:
        raise ConfigError("at least one model target is required")
    targets = [get_model_target(target_id) for target_id in target_ids]
    runs: list[MatrixRun] = []
    for provider in providers:
        provider_name = provider.strip()
        if not provider_name:
            continue
        for target in targets:
            runs.append(
                MatrixRun(
                    engine=provider_name,
                    model=target.default_model,
                    suite=suite,
                    suite_file=suite_file,
                    concurrency=concurrency,
                    raw_traces=raw_traces,
                    no_raw_traces=no_raw_traces,
                    model_metadata=target.metadata,
                )
            )
    if not runs:
        raise ConfigError("matrix generation produced no runs")

    matrix_name = name or _matrix_name(suite, providers, target_ids)
    return MatrixDefinition(
        name=matrix_name,
        description=description
        or f"Canonical {suite} matrix for {', '.join(target.id for target in targets)}.",
        runs=runs,
    )


def matrix_to_yaml(matrix: MatrixDefinition) -> str:
    return (
        yaml.safe_dump(
            matrix.model_dump(mode="json", exclude_none=True),
            sort_keys=False,
            allow_unicode=False,
        )
        + "\n"
    )


def _matrix_name(suite: str, providers: list[str], target_ids: list[str]) -> str:
    provider_part = "providers" if len(providers) > 2 else "-".join(_slug(provider) for provider in providers)
    target_part = "models" if len(target_ids) > 2 else "-".join(_slug(target_id) for target_id in target_ids)
    return _slug(f"{suite}-{provider_part}-{target_part}")[:96]


def _slug(value: str) -> str:
    return "".join(character if character.isalnum() or character in {"-", "."} else "-" for character in value).strip("-")
