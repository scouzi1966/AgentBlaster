from __future__ import annotations

import json

from typer.testing import CliRunner

from agentblaster.cli import app
from agentblaster.models import ApiContract
from agentblaster.telemetry import (
    normalize_response_telemetry,
    telemetry_mapping_catalog,
    telemetry_mapping_catalog_json,
)


def test_normalize_openai_chat_usage_cache_and_finish_reason() -> None:
    normalized = normalize_response_telemetry(
        ApiContract.OPENAI,
        {
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 25,
                "total_tokens": 125,
                "prompt_tokens_details": {"cached_tokens": 40},
            },
            "choices": [{"finish_reason": "stop"}],
        },
        latency_ms=123.4,
        ttft_ms=22.2,
    )

    values = normalized["values"]
    assert values["input_tokens"] == 100
    assert values["output_tokens"] == 25
    assert values["cached_input_tokens"] == 40
    assert values["cache_hit_ratio"] == 0.4
    assert values["finish_reason"] == "stop"
    assert values["latency_ms"] == 123.4
    assert values["ttft_ms"] == 22.2


def test_normalize_anthropic_cache_accounting() -> None:
    normalized = normalize_response_telemetry(
        ApiContract.ANTHROPIC,
        {
            "usage": {
                "input_tokens": 10,
                "output_tokens": 5,
                "cache_read_input_tokens": 30,
                "cache_creation_input_tokens": 20,
            },
            "stop_reason": "end_turn",
        },
    )

    values = normalized["values"]
    assert values["total_tokens"] == 65
    assert values["cached_input_tokens"] == 30
    assert values["cache_write_tokens"] == 20
    assert values["cache_hit_ratio"] == 0.5
    assert values["finish_reason"] == "end_turn"


def test_normalize_ollama_native_converts_nanosecond_timings() -> None:
    normalized = normalize_response_telemetry(
        ApiContract.NATIVE,
        {
            "prompt_eval_count": 100,
            "prompt_eval_duration": 2_000_000_000,
            "eval_count": 50,
            "eval_duration": 1_000_000_000,
            "load_duration": 500_000_000,
            "done_reason": "stop",
        },
        native_adapter="ollama",
    )

    values = normalized["values"]
    assert values["input_tokens"] == 100
    assert values["output_tokens"] == 50
    assert values["prompt_eval_ms"] == 2000.0
    assert values["decode_ms"] == 1000.0
    assert values["load_ms"] == 500.0
    assert values["tokens_per_second_prefill"] == 50.0
    assert values["tokens_per_second_decode"] == 50.0
    assert values["finish_reason"] == "stop"


def test_telemetry_mapping_catalog_includes_target_engine_families() -> None:
    catalog = telemetry_mapping_catalog()
    profiles = {mapping["profile"] for mapping in catalog["mappings"]}

    assert catalog["schema_version"] == "agentblaster.telemetry-mapping-catalog.v1"
    assert {
        "generic-openai-chat",
        "anthropic-messages",
        "afm-mlx-openai-compatible",
        "ollama-native",
        "lm-studio-native",
        "mlx-lm-openai-compatible",
        "rapid-mlx-openai-compatible",
    } <= profiles
    assert "prompt_eval_ms" in catalog["normalized_fields"]
    assert json.loads(telemetry_mapping_catalog_json())["schema_version"] == catalog["schema_version"]


def test_cli_catalog_telemetry_mappings_outputs_text() -> None:
    result = CliRunner().invoke(app, ["catalog", "telemetry-mappings"])

    assert result.exit_code == 0, result.output
    assert "AgentBlaster telemetry mapping catalog" in result.output
    assert "ollama-native" in result.output


def test_normalize_lm_studio_native_stats_aliases() -> None:
    normalized = normalize_response_telemetry(
        ApiContract.NATIVE,
        {
            "stats": {
                "input_tokens": 10,
                "total_output_tokens": 5,
                "tokens_per_second": 25.0,
                "time_to_first_token_seconds": 0.2,
                "model_load_time_seconds": 1.5,
            }
        },
        native_adapter="lm-studio",
    )

    values = normalized["values"]
    assert values["input_tokens"] == 10
    assert values["output_tokens"] == 5
    assert values["total_tokens"] == 15
    assert values["ttft_ms"] == 200.0
    assert values["load_ms"] == 1500.0
    assert values["decode_ms"] == 200.0
    assert values["tokens_per_second_decode"] == 25.0
