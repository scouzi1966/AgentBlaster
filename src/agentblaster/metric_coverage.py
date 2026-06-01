from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentblaster.models import ApiContract, ProviderConfig


@dataclass(frozen=True)
class MetricCoverageItem:
    field: str
    status: str
    source: str
    notes: str
    stability: str = "stable"


NORMALIZED_METRIC_FIELDS: tuple[str, ...] = (
    "latency_ms",
    "queue_ms",
    "rate_limit_wait_ms",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cached_input_tokens",
    "cache_write_tokens",
    "cache_hit_ratio",
    "ttft_ms",
    "prompt_eval_ms",
    "decode_ms",
    "tokens_per_second_prefill",
    "tokens_per_second_decode",
    "tool_calls_requested",
    "tool_calls_emitted",
    "tool_calls_valid",
    "structured_output_valid",
    "finish_reason",
    "raw_usage",
    "raw_stats",
)

STATUS_ORDER = {"native": 0, "measured": 1, "inferred": 2, "conditional": 3, "unavailable": 4}


def metric_coverage_for_provider(provider: ProviderConfig) -> dict[str, Any]:
    items = _coverage_items(provider)
    counts: dict[str, int] = {status: 0 for status in STATUS_ORDER}
    for item in items:
        counts[item.status] = counts.get(item.status, 0) + 1
    return {
        "schema_version": "agentblaster.metric-coverage.v1",
        "provider": {
            "name": provider.name,
            "contract": provider.contract.value,
            "native_adapter": provider.native_adapter,
            "remote": provider.remote,
            "capabilities": dict(provider.capabilities),
            "metrics_url_configured": provider.metrics_url is not None,
        },
        "summary": {
            "field_count": len(items),
            "counts": counts,
            "coverage_score": _coverage_score(items),
        },
        "fields": [item.__dict__ for item in sorted(items, key=lambda item: (STATUS_ORDER[item.status], item.field))],
        "notes": [
            "Coverage describes expected metric availability by provider contract and adapter, not a live endpoint probe.",
            "Native and measured fields are most comparable; inferred fields should be labeled in reports when used for scoring.",
            "Prometheus metrics are run-level observability evidence and are intentionally separate from per-case normalized metrics.",
        ],
    }


def metric_coverage_catalog() -> dict[str, Any]:
    providers = [
        ProviderConfig(name="openai-compatible", contract=ApiContract.OPENAI, base_url="http://127.0.0.1:9999/v1"),
        ProviderConfig(name="openai-responses", contract=ApiContract.OPENAI_RESPONSES, base_url="http://127.0.0.1:9999/v1"),
        ProviderConfig(name="anthropic-compatible", contract=ApiContract.ANTHROPIC, base_url="http://127.0.0.1:9999/v1"),
        ProviderConfig(
            name="ollama-native",
            contract=ApiContract.NATIVE,
            base_url="http://127.0.0.1:11434",
            native_adapter="ollama",
        ),
        ProviderConfig(
            name="lm-studio-native",
            contract=ApiContract.NATIVE,
            base_url="http://127.0.0.1:1234",
            native_adapter="lm-studio",
        ),
    ]
    return {
        "schema_version": "agentblaster.metric-coverage-catalog.v1",
        "normalized_fields": list(NORMALIZED_METRIC_FIELDS),
        "providers": [metric_coverage_for_provider(provider) for provider in providers],
    }


def write_metric_coverage_json(report: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def format_metric_coverage_report(report: dict[str, Any]) -> str:
    if report.get("schema_version") == "agentblaster.metric-coverage-catalog.v1":
        lines = ["AgentBlaster metric coverage catalog", f"normalized_fields: {len(report['normalized_fields'])}", "providers:"]
        for provider_report in report["providers"]:
            provider = provider_report["provider"]
            summary = provider_report["summary"]
            lines.append(
                f"- {provider['name']} ({provider['contract']}): score={summary['coverage_score']} counts={summary['counts']}"
            )
        return "\n".join(lines) + "\n"
    provider = report["provider"]
    summary = report["summary"]
    lines = [
        "AgentBlaster metric coverage",
        f"provider: {provider['name']} ({provider['contract']})",
        f"native_adapter: {provider.get('native_adapter') or 'none'}",
        f"remote: {str(provider['remote']).lower()}",
        f"metrics_url_configured: {str(provider['metrics_url_configured']).lower()}",
        f"coverage_score: {summary['coverage_score']}",
        f"counts: {summary['counts']}",
        "fields:",
    ]
    for field in report["fields"]:
        lines.append(f"- {field['status'].upper()} {field['field']} [{field['source']}]")
        lines.append(f"  {field['notes']}")
    return "\n".join(lines) + "\n"

def _coverage_items(provider: ProviderConfig) -> list[MetricCoverageItem]:
    items = _baseline_items(provider)
    if provider.contract is ApiContract.OPENAI:
        items.extend(_openai_items())
    elif provider.contract is ApiContract.OPENAI_RESPONSES:
        items.extend(_openai_responses_items())
    elif provider.contract is ApiContract.ANTHROPIC:
        items.extend(_anthropic_items())
    elif provider.contract is ApiContract.NATIVE and provider.native_adapter == "ollama":
        items.extend(_ollama_native_items())
    elif provider.contract is ApiContract.NATIVE and provider.native_adapter == "lm-studio":
        items.extend(_lmstudio_native_items())
    else:
        items.extend(_unknown_native_items())
    return _dedupe_by_field(items)


def _baseline_items(provider: ProviderConfig) -> list[MetricCoverageItem]:
    return [
        MetricCoverageItem("latency_ms", "measured", "agentblaster timer", "Wall-clock request latency measured around adapter dispatch."),
        MetricCoverageItem("queue_ms", "measured", "agentblaster scheduler", "Queue wait measured before request dispatch when concurrency is used."),
        MetricCoverageItem("rate_limit_wait_ms", "measured", "agentblaster pacer", "Rate-limit wait measured by AgentBlaster provider pacer."),
        MetricCoverageItem("tool_calls_requested", "measured", "suite definition", "Counted from offered/expected tool surfaces before dispatch."),
        MetricCoverageItem("tool_calls_emitted", "measured", "adapter parser", "Counted from parsed provider tool-call output."),
        MetricCoverageItem("tool_calls_valid", "measured", "AgentBlaster validator", "Validated deterministically against offered tool schemas."),
        MetricCoverageItem("structured_output_valid", "measured", "AgentBlaster validator", "Validated deterministically from response text and schema/JSON mode."),
        MetricCoverageItem("raw_usage", "conditional", "provider response", "Compact usage object is stored when the response exposes one."),
        MetricCoverageItem("raw_stats", "conditional", "provider/native response", "Compact native stats are stored when adapters expose timing/stat fields."),
    ]


def _openai_items() -> list[MetricCoverageItem]:
    return [
        MetricCoverageItem("input_tokens", "native", "usage.prompt_tokens", "OpenAI-compatible usage prompt token count when endpoint returns usage."),
        MetricCoverageItem("output_tokens", "native", "usage.completion_tokens", "OpenAI-compatible usage completion token count when endpoint returns usage."),
        MetricCoverageItem("total_tokens", "native", "usage.total_tokens", "OpenAI-compatible total token count when endpoint returns usage."),
        MetricCoverageItem("cached_input_tokens", "conditional", "usage.prompt_tokens_details.cached_tokens", "Available only on providers that expose cached prompt token details."),
        MetricCoverageItem("cache_write_tokens", "unavailable", "not in OpenAI Chat usage", "Chat Completions does not standardize cache-write token accounting."),
        MetricCoverageItem("cache_hit_ratio", "inferred", "cached_input_tokens / prompt denominator", "Derived only when cached token details are present."),
        MetricCoverageItem("ttft_ms", "measured", "streaming adapter timer", "Measured by AgentBlaster for streaming responses; absent for non-streaming cases."),
        MetricCoverageItem("prompt_eval_ms", "unavailable", "not in OpenAI Chat usage", "Generic OpenAI-compatible responses do not expose prefill duration."),
        MetricCoverageItem("decode_ms", "unavailable", "not in OpenAI Chat usage", "Generic OpenAI-compatible responses do not expose decode duration."),
        MetricCoverageItem("tokens_per_second_prefill", "unavailable", "not in OpenAI Chat usage", "Requires native prompt timing or external telemetry."),
        MetricCoverageItem("tokens_per_second_decode", "unavailable", "not in OpenAI Chat usage", "Requires native decode timing or external telemetry."),
        MetricCoverageItem("finish_reason", "native", "choices[].finish_reason", "Finish reason from the first choice when present."),
    ]


def _openai_responses_items() -> list[MetricCoverageItem]:
    return [
        MetricCoverageItem("input_tokens", "native", "usage.input_tokens", "Responses input token count when endpoint returns usage."),
        MetricCoverageItem("output_tokens", "native", "usage.output_tokens", "Responses output token count when endpoint returns usage."),
        MetricCoverageItem("total_tokens", "native", "usage.total_tokens", "Responses total token count when endpoint returns usage."),
        MetricCoverageItem("cached_input_tokens", "conditional", "usage.input_tokens_details.cached_tokens", "Available only when Responses usage includes cached-token details."),
        MetricCoverageItem("cache_write_tokens", "unavailable", "not standardized", "Responses-compatible endpoints do not consistently expose cache-write tokens."),
        MetricCoverageItem("cache_hit_ratio", "inferred", "cached_input_tokens / input denominator", "Derived only when cached token details are present."),
        MetricCoverageItem("ttft_ms", "measured", "streaming adapter timer", "Measured by AgentBlaster for streaming response events."),
        MetricCoverageItem("prompt_eval_ms", "unavailable", "not in Responses usage", "Requires native prompt timing or external telemetry."),
        MetricCoverageItem("decode_ms", "unavailable", "not in Responses usage", "Requires native decode timing or external telemetry."),
        MetricCoverageItem("tokens_per_second_prefill", "unavailable", "not in Responses usage", "Requires native prompt timing or external telemetry."),
        MetricCoverageItem("tokens_per_second_decode", "unavailable", "not in Responses usage", "Requires native decode timing or external telemetry."),
        MetricCoverageItem("finish_reason", "conditional", "response status/events", "Responses surfaces status and completion events rather than a Chat-style finish reason."),
    ]


def _anthropic_items() -> list[MetricCoverageItem]:
    return [
        MetricCoverageItem("input_tokens", "native", "usage.input_tokens", "Anthropic input token count when returned."),
        MetricCoverageItem("output_tokens", "native", "usage.output_tokens", "Anthropic output token count when returned."),
        MetricCoverageItem("total_tokens", "inferred", "usage input/output/cache tokens", "Derived from input, output, cache read, and cache creation tokens."),
        MetricCoverageItem("cached_input_tokens", "native", "usage.cache_read_input_tokens", "Prompt-cache read token count when cache control is used and returned."),
        MetricCoverageItem("cache_write_tokens", "native", "usage.cache_creation_input_tokens", "Prompt-cache creation token count when cache control is used and returned."),
        MetricCoverageItem("cache_hit_ratio", "inferred", "cache_read / input+cache denominator", "Derived from Anthropic cache read/create accounting."),
        MetricCoverageItem("ttft_ms", "measured", "streaming adapter timer", "Measured by AgentBlaster for streaming message events."),
        MetricCoverageItem("prompt_eval_ms", "unavailable", "not in Anthropic usage", "Provider does not expose prefill duration in standard Messages usage."),
        MetricCoverageItem("decode_ms", "unavailable", "not in Anthropic usage", "Provider does not expose decode duration in standard Messages usage."),
        MetricCoverageItem("tokens_per_second_prefill", "unavailable", "not in Anthropic usage", "Requires native telemetry."),
        MetricCoverageItem("tokens_per_second_decode", "unavailable", "not in Anthropic usage", "Requires native telemetry."),
        MetricCoverageItem("finish_reason", "native", "stop_reason", "Anthropic stop reason from message response or stream delta."),
    ]


def _ollama_native_items() -> list[MetricCoverageItem]:
    return [
        MetricCoverageItem("input_tokens", "native", "prompt_eval_count", "Ollama native prompt token count."),
        MetricCoverageItem("output_tokens", "native", "eval_count", "Ollama native generated token count."),
        MetricCoverageItem("total_tokens", "inferred", "prompt_eval_count + eval_count", "Derived from native prompt and eval counts."),
        MetricCoverageItem("cached_input_tokens", "unavailable", "not in Ollama native stats", "Prompt cache reads are not normalized from Ollama native responses."),
        MetricCoverageItem("cache_write_tokens", "unavailable", "not in Ollama native stats", "Prompt cache writes are not normalized from Ollama native responses."),
        MetricCoverageItem("cache_hit_ratio", "unavailable", "not in Ollama native stats", "Requires explicit cache read/write counters."),
        MetricCoverageItem("ttft_ms", "unavailable", "not in non-stream native stats", "AgentBlaster does not currently derive TTFT from Ollama native non-stream responses."),
        MetricCoverageItem("prompt_eval_ms", "native", "prompt_eval_duration", "Ollama prompt-eval duration converted from nanoseconds."),
        MetricCoverageItem("decode_ms", "native", "eval_duration", "Ollama decode duration converted from nanoseconds."),
        MetricCoverageItem("tokens_per_second_prefill", "inferred", "prompt_eval_count / prompt_eval_duration", "Derived from Ollama native prompt count and duration."),
        MetricCoverageItem("tokens_per_second_decode", "inferred", "eval_count / eval_duration", "Derived from Ollama native eval count and duration."),
        MetricCoverageItem("finish_reason", "conditional", "done/done_reason", "Ollama native completion reason availability depends on endpoint/version."),
    ]


def _lmstudio_native_items() -> list[MetricCoverageItem]:
    return [
        MetricCoverageItem("input_tokens", "conditional", "usage.prompt_tokens", "LM Studio native responses may include OpenAI-style usage."),
        MetricCoverageItem("output_tokens", "conditional", "usage.completion_tokens", "LM Studio native responses may include OpenAI-style usage."),
        MetricCoverageItem("total_tokens", "conditional", "usage.total_tokens", "LM Studio native responses may include total token usage."),
        MetricCoverageItem("cached_input_tokens", "unavailable", "not standardized", "LM Studio native cache counters are not currently normalized."),
        MetricCoverageItem("cache_write_tokens", "unavailable", "not standardized", "LM Studio native cache-write counters are not currently normalized."),
        MetricCoverageItem("cache_hit_ratio", "unavailable", "not standardized", "Requires explicit cache counters."),
        MetricCoverageItem("ttft_ms", "native", "stats.ttft/ttft_seconds", "LM Studio native stats can expose TTFT."),
        MetricCoverageItem("prompt_eval_ms", "unavailable", "not standardized", "Prompt-eval duration is not consistently exposed."),
        MetricCoverageItem("decode_ms", "unavailable", "not standardized", "Decode duration is not consistently exposed."),
        MetricCoverageItem("tokens_per_second_prefill", "unavailable", "not standardized", "Requires prompt-eval duration/count."),
        MetricCoverageItem("tokens_per_second_decode", "native", "stats.tokens_per_second", "LM Studio native stats can expose output tokens/sec."),
        MetricCoverageItem("finish_reason", "conditional", "finish_reason/stop_reason", "Finish reason availability depends on native endpoint/version."),
    ]


def _unknown_native_items() -> list[MetricCoverageItem]:
    return [
        MetricCoverageItem(field, "unavailable", "unknown native adapter", "No static metric mapping is declared for this native adapter.")
        for field in NORMALIZED_METRIC_FIELDS
        if field not in {"latency_ms", "queue_ms", "rate_limit_wait_ms", "tool_calls_requested", "tool_calls_emitted", "tool_calls_valid", "structured_output_valid", "raw_usage", "raw_stats"}
    ]


def _dedupe_by_field(items: list[MetricCoverageItem]) -> list[MetricCoverageItem]:
    by_field: dict[str, MetricCoverageItem] = {}
    for item in items:
        current = by_field.get(item.field)
        if current is None or STATUS_ORDER[item.status] < STATUS_ORDER[current.status]:
            by_field[item.field] = item
    missing = [
        MetricCoverageItem(field, "unavailable", "not mapped", "No static metric coverage mapping is available for this field.")
        for field in NORMALIZED_METRIC_FIELDS
        if field not in by_field
    ]
    return [*by_field.values(), *missing]


def _coverage_score(items: list[MetricCoverageItem]) -> float:
    weights = {"native": 1.0, "measured": 0.9, "inferred": 0.65, "conditional": 0.4, "unavailable": 0.0}
    if not items:
        return 0.0
    return round(sum(weights[item.status] for item in items) / len(items), 4)
