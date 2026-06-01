from __future__ import annotations

import pytest

from agentblaster.errors import ConfigError
from agentblaster.model_catalog import generate_matrix_template, get_model_target, list_model_targets, matrix_to_yaml
from agentblaster.models import RawTraceMode


def test_model_catalog_contains_initial_dense_targets() -> None:
    targets = {target.id: target for target in list_model_targets()}

    assert {"qwen3.6-27b-dense", "gemma-4-31b-dense"} <= set(targets)
    assert targets["qwen3.6-27b-dense"].density == "dense"
    assert targets["qwen3.6-27b-dense"].parameter_count == "27B"
    assert targets["qwen3.6-27b-dense"].metadata.architecture == "qwen3.6-dense"
    assert targets["qwen3.6-27b-dense"].comparison_group == "qwen3.6-27b-dense"
    assert "quantization" in targets["qwen3.6-27b-dense"].required_release_metadata
    assert any("separate primary charts" in item for item in targets["qwen3.6-27b-dense"].publication_guidance)
    assert targets["gemma-4-31b-dense"].density == "dense"
    assert targets["gemma-4-31b-dense"].parameter_count == "31B"
    assert targets["gemma-4-31b-dense"].metadata.architecture == "gemma-4-dense"
    assert targets["gemma-4-31b-dense"].comparison_group == "gemma-4-31b-dense"
    assert "revision" in targets["gemma-4-31b-dense"].required_release_metadata
    assert any("quantization class" in item for item in targets["gemma-4-31b-dense"].publication_guidance)


def test_get_model_target_rejects_unknown_target() -> None:
    with pytest.raises(ConfigError, match="unknown model target"):
        get_model_target("missing")


def test_generate_matrix_template_crosses_providers_and_targets() -> None:
    matrix = generate_matrix_template(
        providers=["afm", "lm-studio"],
        target_ids=["qwen3.6-27b-dense", "gemma-4-31b-dense"],
        suite="trace-replay",
        concurrency=2,
        no_raw_traces=True,
    )

    assert matrix.name.startswith("trace-replay-afm-lm-studio")
    assert len(matrix.runs) == 4
    assert matrix.runs[0].engine == "afm"
    assert matrix.runs[0].model == "mlx-community/Qwen3.6-27B"
    assert matrix.runs[0].suite == "trace-replay"
    assert matrix.runs[0].concurrency == 2
    assert matrix.runs[0].raw_traces == RawTraceMode.REDACTED
    assert matrix.runs[0].no_raw_traces is True
    assert matrix.runs[0].model_metadata.architecture == "qwen3.6-dense"
    assert matrix.runs[1].model_metadata.architecture == "gemma-4-dense"


def test_matrix_template_serializes_to_yaml() -> None:
    matrix = generate_matrix_template(
        providers=["afm"],
        target_ids=["qwen3.6-27b-dense"],
        suite="smoke",
        name="local-qwen",
    )
    text = matrix_to_yaml(matrix)

    assert "name: local-qwen" in text
    assert "engine: afm" in text
    assert "model: mlx-community/Qwen3.6-27B" in text
    assert "architecture: qwen3.6-dense" in text


def test_generate_matrix_template_requires_provider_and_target() -> None:
    with pytest.raises(ConfigError, match="provider"):
        generate_matrix_template(providers=[], target_ids=["qwen3.6-27b-dense"])

    with pytest.raises(ConfigError, match="model target"):
        generate_matrix_template(providers=["afm"], target_ids=[])
