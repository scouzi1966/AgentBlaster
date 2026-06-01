from __future__ import annotations

import json

from typer.testing import CliRunner

from agentblaster.cli import app
from agentblaster.models import ApiContract
from agentblaster.telemetry import (
    format_normalized_response_telemetry,
    normalize_response_telemetry,
    normalized_response_telemetry_json,
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
            "agentblaster_http": {
                "status_code": 200,
                "content_type": "application/json",
                "headers": {
                    "x-request-id": "req_123",
                    "x-ratelimit-remaining-requests": "99",
                    "x-ratelimit-remaining-tokens": "1000",
                    "retry-after": "2",
                },
            },
        },
        latency_ms=123.4,
        queue_ms=3.0,
        rate_limit_wait_ms=4.0,
        ttft_ms=22.2,
    )

    values = normalized["values"]
    assert values["input_tokens"] == 100
    assert values["output_tokens"] == 25
    assert values["cached_input_tokens"] == 40
    assert values["cache_hit_ratio"] == 0.4
    assert values["finish_reason"] == "stop"
    assert values["latency_ms"] == 123.4
    assert values["queue_ms"] == 3.0
    assert values["rate_limit_wait_ms"] == 4.0
    assert values["status_code"] == 200
    assert values["provider_request_id"] == "req_123"
    assert values["response_content_type"] == "application/json"
    assert values["provider_rate_limit_remaining"] == {"requests": 99, "tokens": 1000}
    assert values["provider_retry_after_ms"] == 2000.0
    assert values["ttft_ms"] == 22.2
    assert normalized["stats_profile"] == "generic-openai-chat"
    assert normalized["stats_comparability"]["schema_version"] == "agentblaster.response-stats-comparability.v1"
    assert normalized["stats_comparability"]["requires_labeling"] is True
    assert normalized["quality"]["input_tokens"] == "native"
    assert normalized["quality"]["ttft_ms"] == "measured"
    assert normalized["quality"]["provider_request_id"] == "measured"
    assert normalized["quality"]["cache_hit_ratio"] == "inferred"
    assert "cache_hit_ratio" in normalized["comparison_readiness"]["advisory_fields"]


def test_normalize_prefers_agentblaster_measured_ttft_over_provider_stats() -> None:
    normalized = normalize_response_telemetry(
        ApiContract.OPENAI,
        {
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "stats": {"ttft_ms": 999.0, "tokens_per_second": 25.0},
            "choices": [{"finish_reason": "stop"}],
        },
        ttft_ms=12.5,
    )

    values = normalized["values"]
    assert values["ttft_ms"] == 12.5
    assert normalized["sources"]["ttft_ms"] == "agentblaster streaming timer"
    assert values["tokens_per_second_decode"] == 25.0
    assert values["raw_stats"]["ttft_ms"] == 999.0


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
    assert normalized["stats_profile"] == "ollama-native"
    assert normalized["quality"]["prompt_eval_ms"] == "native"
    assert normalized["quality"]["tokens_per_second_decode"] == "inferred"
    assert normalized["comparison_readiness"]["guidance"] == "label-inferred-or-conditional-fields-before-cross-engine-comparison"


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
        "omlx-openai-compatible",
    } <= profiles
    assert "prompt_eval_ms" in catalog["normalized_fields"]
    assert "provider_request_id" in catalog["normalized_fields"]
    assert catalog["stats_comparability"]["schema_version"] == "agentblaster.stats-comparability.v1"
    assert catalog["stats_comparability"]["profile_guidance"]["ollama-native"].startswith("Durations are nanoseconds")
    assert catalog["stats_comparability"]["security"]["contacts_providers"] is False
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


def test_normalize_openai_wrapper_stats_with_explicit_unit_aliases() -> None:
    normalized = normalize_response_telemetry(
        ApiContract.OPENAI,
        {
            "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
            "metrics": {
                "prefill_seconds": 0.5,
                "decode_duration_ns": 200_000_000,
                "prefix_cache_hit_tokens": 25,
                "cache_write_tokens": 5,
                "cache_hit_rate": 0.25,
            },
            "choices": [{"finish_reason": "stop"}],
        },
        native_adapter="rapid-mlx",
    )

    values = normalized["values"]
    assert normalized["stats_profile"] == "rapid-mlx-openai-compatible"
    assert values["prompt_eval_ms"] == 500.0
    assert values["decode_ms"] == 200.0
    assert values["tokens_per_second_prefill"] == 100.0
    assert values["tokens_per_second_decode"] == 100.0
    assert values["cached_input_tokens"] == 25
    assert values["cache_write_tokens"] == 5
    assert values["cache_hit_ratio"] == 0.25
    assert normalized["quality"]["prompt_eval_ms"] == "native"
    assert normalized["quality"]["tokens_per_second_prefill"] == "inferred"
    assert "tokens_per_second_prefill" in normalized["stats_comparability"]["advisory_fields"]


def test_format_normalized_response_telemetry_lists_sources() -> None:
    normalized = normalize_response_telemetry(
        ApiContract.OPENAI,
        {
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 25,
                "total_tokens": 125,
            },
            "choices": [{"finish_reason": "stop"}],
        },
    )

    rendered = format_normalized_response_telemetry(normalized)

    assert "AgentBlaster normalized response telemetry" in rendered
    assert "input_tokens: 100 [usage.prompt_tokens]" in rendered
    assert "finish_reason: stop [choices[0].finish_reason]" in rendered
    assert "comparison_readiness:" in rendered
    assert "stats_profile: generic-openai-chat" in rendered
    assert "stats_comparability:" in rendered
    assert json.loads(normalized_response_telemetry_json(normalized))["schema_version"] == "agentblaster.normalized-telemetry.v1"


def test_cli_catalog_normalize_telemetry_writes_json(tmp_path) -> None:
    sample = tmp_path / "ollama-response.json"
    output = tmp_path / "normalized.json"
    sample.write_text(
        json.dumps(
            {
                "prompt_eval_count": 8,
                "prompt_eval_duration": 1_000_000_000,
                "eval_count": 4,
                "eval_duration": 500_000_000,
                "done": True,
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "catalog",
            "normalize-telemetry",
            str(sample),
            "--contract",
            "native",
            "--native-adapter",
            "ollama",
            "--output-json",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "AgentBlaster normalized response telemetry" in result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["values"]["input_tokens"] == 8
    assert payload["values"]["tokens_per_second_decode"] == 8.0
    assert payload["comparison_readiness"]["advisory_fields"] == [
        "tokens_per_second_prefill",
        "tokens_per_second_decode",
    ]
