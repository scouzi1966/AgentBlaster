from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentblaster.models import ApiContract, ProviderConfig


METRIC_COVERAGE_SCHEMA_VERSION = "agentblaster.metric-coverage.v1"
METRIC_COVERAGE_CATALOG_SCHEMA_VERSION = "agentblaster.metric-coverage-catalog.v1"
METRIC_CLAIM_CONTRACT_SCHEMA_VERSION = "agentblaster.metric-claim-contract.v1"


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
    "status_code",
    "provider_request_id",
    "response_content_type",
    "provider_rate_limit_remaining",
    "provider_retry_after_ms",
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
    "invalid_tool_call_count",
    "tool_parser_repair_valid",
    "tool_loop_enabled",
    "tool_loop_rounds",
    "tool_loop_tool_call_count",
    "tool_loop_max_tool_calls",
    "tool_loop_stop_reason",
    "structured_output_valid",
    "judge_verdict_valid",
    "finish_reason",
    "cancel_after_ms",
    "canceled",
    "cancellation_latency_ms",
    "raw_usage",
    "raw_stats",
)

METRIC_GROUPS: dict[str, tuple[str, ...]] = {
    "timing_and_throughput": (
        "latency_ms",
        "queue_ms",
        "rate_limit_wait_ms",
        "ttft_ms",
        "prompt_eval_ms",
        "decode_ms",
        "tokens_per_second_prefill",
        "tokens_per_second_decode",
    ),
    "token_and_cache_accounting": (
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "cached_input_tokens",
        "cache_write_tokens",
        "cache_hit_ratio",
    ),
    "agent_protocol_behavior": (
        "tool_calls_requested",
        "tool_calls_emitted",
        "tool_calls_valid",
        "invalid_tool_call_count",
        "tool_parser_repair_valid",
        "tool_loop_enabled",
        "tool_loop_rounds",
        "tool_loop_tool_call_count",
        "tool_loop_max_tool_calls",
        "tool_loop_stop_reason",
        "structured_output_valid",
        "judge_verdict_valid",
        "finish_reason",
        "cancel_after_ms",
        "canceled",
        "cancellation_latency_ms",
    ),
    "telemetry_provenance": (
        "status_code",
        "provider_request_id",
        "response_content_type",
        "provider_rate_limit_remaining",
        "provider_retry_after_ms",
        "raw_usage",
        "raw_stats",
    ),
}

STATUS_ORDER = {"native": 0, "measured": 1, "inferred": 2, "conditional": 3, "unavailable": 4}
PUBLICATION_GRADE_STATUSES = {"native", "measured"}
ADVISORY_STATUSES = {"inferred", "conditional"}


def metric_coverage_for_provider(provider: ProviderConfig) -> dict[str, Any]:
    items = _coverage_items(provider)
    counts: dict[str, int] = {status: 0 for status in STATUS_ORDER}
    for item in items:
        counts[item.status] = counts.get(item.status, 0) + 1
    comparability = _comparability_profile(items)
    return {
        "schema_version": METRIC_COVERAGE_SCHEMA_VERSION,
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
        "comparability": comparability,
        "claim_contract": _metric_claim_contract(comparability),
        "fields": [item.__dict__ for item in sorted(items, key=lambda item: (STATUS_ORDER[item.status], item.field))],
        "notes": [
            "Coverage describes expected metric availability by provider contract and adapter, not a live endpoint probe.",
            "Native and measured fields are most comparable; inferred fields should be labeled in reports when used for scoring.",
            "Comparability groups classify metric families as publication-grade, advisory-only, partial, or unavailable.",
            "Prometheus metrics are run-level observability evidence and are intentionally separate from per-case normalized metrics.",
        ],
    }


def metric_coverage_catalog() -> dict[str, Any]:
    providers = [
        ProviderConfig(name="openai-compatible", contract=ApiContract.OPENAI, base_url="http://127.0.0.1:9999/v1"),
        ProviderConfig(
            name="afm-mlx-openai-compatible",
            contract=ApiContract.OPENAI,
            base_url="http://127.0.0.1:9999/v1",
            native_adapter="afm-mlx",
        ),
        ProviderConfig(
            name="mlx-lm-openai-compatible",
            contract=ApiContract.OPENAI,
            base_url="http://127.0.0.1:8080/v1",
            native_adapter="mlx-lm",
        ),
        ProviderConfig(
            name="rapid-mlx-openai-compatible",
            contract=ApiContract.OPENAI,
            base_url="http://127.0.0.1:8081/v1",
            native_adapter="rapid-mlx",
        ),
        ProviderConfig(
            name="omlx-openai-compatible",
            contract=ApiContract.OPENAI,
            base_url="http://127.0.0.1:8082/v1",
            native_adapter="omlx",
        ),
        ProviderConfig(name="openai-responses", contract=ApiContract.OPENAI_RESPONSES, base_url="http://127.0.0.1:9999/v1"),
        ProviderConfig(name="anthropic-compatible", contract=ApiContract.ANTHROPIC, base_url="http://127.0.0.1:9999/v1"),
        ProviderConfig(name="lm-studio-anthropic", contract=ApiContract.ANTHROPIC, base_url="http://127.0.0.1:1234/v1"),
        ProviderConfig(name="vllm-mlx-anthropic", contract=ApiContract.ANTHROPIC, base_url="http://127.0.0.1:8000/v1"),
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
        "schema_version": METRIC_COVERAGE_CATALOG_SCHEMA_VERSION,
        "normalized_fields": list(NORMALIZED_METRIC_FIELDS),
        "providers": [metric_coverage_for_provider(provider) for provider in providers],
    }


def write_metric_coverage_json(report: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def format_metric_coverage_report(report: dict[str, Any]) -> str:
    if report.get("schema_version") == METRIC_COVERAGE_CATALOG_SCHEMA_VERSION:
        lines = ["AgentBlaster metric coverage catalog", f"normalized_fields: {len(report['normalized_fields'])}", "providers:"]
        for provider_report in report["providers"]:
            provider = provider_report["provider"]
            summary = provider_report["summary"]
            comparability = provider_report["comparability"]
            lines.append(
                f"- {provider['name']} ({provider['contract']}): score={summary['coverage_score']} "
                f"publication_groups={comparability['publication_grade_group_count']} counts={summary['counts']}"
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
        "comparability:",
    ]
    for group in report["comparability"]["groups"]:
        lines.append(f"- {group['status'].upper()} {group['id']}: score={group['coverage_score']} guidance={group['claim_guidance']}")
    claim_contract = report.get("claim_contract") if isinstance(report.get("claim_contract"), dict) else {}
    if claim_contract:
        lines.append("claim_contract:")
        lines.append(f"- leaderboard_eligible_groups: {', '.join(claim_contract.get('leaderboard_eligible_groups', []) or []) or 'none'}")
        lines.append(f"- disclosure_required_groups: {', '.join(claim_contract.get('disclosure_required_groups', []) or []) or 'none'}")
        lines.append(f"- primary_score_policy: {claim_contract.get('primary_score_policy', 'unknown')}")
    lines.append("fields:")
    for field in report["fields"]:
        lines.append(f"- {field['status'].upper()} {field['field']} [{field['source']}]")
        lines.append(f"  {field['notes']}")
    return "\n".join(lines) + "\n"

def _coverage_items(provider: ProviderConfig) -> list[MetricCoverageItem]:
    items = _baseline_items(provider)
    if provider.contract is ApiContract.OPENAI:
        items.extend(_openai_items())
        items.extend(_openai_wrapper_items(provider.native_adapter))
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
        MetricCoverageItem("status_code", "measured", "agentblaster_http.status_code", "HTTP status code captured from safe adapter metadata."),
        MetricCoverageItem("provider_request_id", "conditional", "agentblaster_http safe request-id headers", "Provider request IDs are captured only from allowlisted response headers."),
        MetricCoverageItem("response_content_type", "measured", "agentblaster_http.content_type", "Response content type captured from safe adapter metadata."),
        MetricCoverageItem("provider_rate_limit_remaining", "conditional", "agentblaster_http safe rate-limit headers", "Remaining request/token budget is captured only when providers expose allowlisted rate-limit headers."),
        MetricCoverageItem("provider_retry_after_ms", "conditional", "agentblaster_http.headers.retry-after", "Retry-after is normalized to milliseconds when a provider emits the safe header."),
        MetricCoverageItem("tool_calls_requested", "measured", "suite definition", "Counted from offered/expected tool surfaces before dispatch."),
        MetricCoverageItem("tool_calls_emitted", "measured", "adapter parser", "Counted from parsed provider tool-call output."),
        MetricCoverageItem("tool_calls_valid", "measured", "AgentBlaster validator", "Validated deterministically against offered tool schemas."),
        MetricCoverageItem("invalid_tool_call_count", "measured", "AgentBlaster validator", "Counted from emitted tool calls that fail API-native envelope or schema validation."),
        MetricCoverageItem("tool_parser_repair_valid", "measured", "AgentBlaster validator", "Validated for parser-repair cases that must not treat raw JSON, XML, markdown, or ReAct text as completed tool calls."),
        MetricCoverageItem("tool_loop_enabled", "measured", "suite definition", "Whether the case declares bounded deterministic tool-loop execution."),
        MetricCoverageItem("tool_loop_rounds", "measured", "AgentBlaster tool-loop orchestrator", "Counted from deterministic tool-loop execution rounds."),
        MetricCoverageItem("tool_loop_tool_call_count", "measured", "AgentBlaster tool-loop orchestrator", "Counted from emitted tool calls across deterministic loop rounds."),
        MetricCoverageItem("tool_loop_max_tool_calls", "measured", "suite definition", "Declared maximum deterministic tool-call depth for bounded tool-loop cases."),
        MetricCoverageItem("tool_loop_stop_reason", "measured", "AgentBlaster tool-loop orchestrator", "Normalized stop reason for bounded deterministic tool-loop cases."),
        MetricCoverageItem("structured_output_valid", "measured", "AgentBlaster validator", "Validated deterministically from response text and schema/JSON mode."),
        MetricCoverageItem("judge_verdict_valid", "measured", "AgentBlaster validator", "Validated deterministically for generated judge-rubric structured verdict cases."),
        MetricCoverageItem("cancel_after_ms", "measured", "suite definition", "Cancellation intent declared by benchmark cases before dispatch."),
        MetricCoverageItem("canceled", "measured", "streaming adapter", "Whether AgentBlaster observed an intentional stream abort for cancellation cases."),
        MetricCoverageItem("cancellation_latency_ms", "measured", "streaming adapter timer", "Elapsed milliseconds until AgentBlaster closed a cancellation stream."),
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


def _openai_wrapper_items(native_adapter: str | None) -> list[MetricCoverageItem]:
    if native_adapter == "afm-mlx":
        return [
            MetricCoverageItem("prompt_eval_ms", "native", "stats/metrics prompt_eval/prefill duration aliases with explicit ms, seconds, or ns units", "AFM MLX can expose native prefill duration through OpenAI-compatible extension stats.", stability="adapter-specific"),
            MetricCoverageItem("decode_ms", "native", "stats/metrics decode/generation duration aliases with explicit ms, seconds, or ns units", "AFM MLX can expose native decode duration through extension stats.", stability="adapter-specific"),
            MetricCoverageItem("tokens_per_second_prefill", "native", "native stats/metrics prefill TPS or derived from prompt tokens and explicit prefill duration", "AFM MLX can expose native or consistently derivable prefill throughput for prefix-cache and prefill optimization claims.", stability="adapter-specific"),
            MetricCoverageItem("tokens_per_second_decode", "native", "native stats/metrics decode TPS or derived from output tokens and explicit decode duration", "AFM MLX can expose native or consistently derivable decode throughput through extension stats.", stability="adapter-specific"),
            MetricCoverageItem("cached_input_tokens", "conditional", "usage.prompt_tokens_details.cached_tokens or stats/metrics cache-hit token aliases", "AFM cache-hit accounting is comparable only when cached-token counters are emitted.", stability="adapter-specific"),
            MetricCoverageItem("cache_write_tokens", "conditional", "stats/metrics cache-write token aliases", "AFM cache-write accounting is extension-specific and must be disclosed separately from Anthropic cache creation tokens.", stability="adapter-specific"),
        ]
    if native_adapter == "mlx-lm":
        return [
            MetricCoverageItem("tokens_per_second_decode", "conditional", "stats.tokens_per_second", "MLX-LM wrappers may expose decode throughput; absence should remain null rather than inferred.", stability="adapter-specific"),
            MetricCoverageItem("ttft_ms", "measured", "streaming adapter timer", "AgentBlaster streaming TTFT is comparable when streaming is enabled.", stability="adapter-specific"),
        ]
    if native_adapter == "rapid-mlx":
        return [
            MetricCoverageItem("prompt_eval_ms", "conditional", "stats/metrics prefill duration aliases with explicit units", "Rapid MLX prefill duration mapping remains version-dependent.", stability="emerging"),
            MetricCoverageItem("tokens_per_second_prefill", "conditional", "stats/metrics prefill TPS or derived from prompt tokens and explicit prefill duration", "Rapid MLX prefill throughput mapping remains version-dependent.", stability="emerging"),
            MetricCoverageItem("tokens_per_second_decode", "conditional", "stats/metrics decode TPS or derived from output tokens and explicit decode duration", "Rapid MLX decode throughput mapping remains version-dependent.", stability="emerging"),
        ]
    if native_adapter == "omlx":
        return [
            MetricCoverageItem("prompt_eval_ms", "conditional", "stats/metrics prompt_eval/prefill duration aliases with explicit units", "oMLX prefill timing is wrapper-specific and should be treated as conditional until response stats stabilize.", stability="emerging"),
            MetricCoverageItem("tokens_per_second_prefill", "conditional", "stats/metrics prefill TPS or derived from prompt tokens and explicit prefill duration", "oMLX prefill throughput is wrapper-specific and should be labeled before cross-engine claims.", stability="emerging"),
            MetricCoverageItem("tokens_per_second_decode", "conditional", "stats/metrics decode TPS or derived from output tokens and explicit decode duration", "oMLX decode throughput is wrapper-specific and should be labeled before cross-engine claims.", stability="emerging"),
        ]
    return []


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
        MetricCoverageItem("finish_reason", "native", "done/done_reason", "Ollama native completion reason from the endpoint response."),
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
        if field not in {"latency_ms", "queue_ms", "rate_limit_wait_ms", "status_code", "provider_request_id", "response_content_type", "provider_rate_limit_remaining", "provider_retry_after_ms", "tool_calls_requested", "tool_calls_emitted", "tool_calls_valid", "invalid_tool_call_count", "tool_parser_repair_valid", "structured_output_valid", "raw_usage", "raw_stats"}
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


def _comparability_profile(items: list[MetricCoverageItem]) -> dict[str, Any]:
    field_map = {item.field: item for item in items}
    groups = [_metric_group_profile(group_id, fields, field_map) for group_id, fields in METRIC_GROUPS.items()]
    return {
        "group_count": len(groups),
        "publication_grade_group_count": sum(1 for group in groups if group["status"] == "publication-grade"),
        "advisory_group_count": sum(1 for group in groups if group["status"] == "advisory-only"),
        "partial_group_count": sum(1 for group in groups if group["status"] == "partial"),
        "unavailable_group_count": sum(1 for group in groups if group["status"] == "unavailable"),
        "publication_grade_groups": [group["id"] for group in groups if group["status"] == "publication-grade"],
        "review_required_groups": [
            group["id"]
            for group in groups
            if group["status"] in {"advisory-only", "partial", "unavailable"}
        ],
        "groups": groups,
    }


def _metric_claim_contract(comparability: dict[str, Any]) -> dict[str, Any]:
    groups = comparability.get("groups") if isinstance(comparability.get("groups"), list) else []
    claims = [_claim_contract_group(group) for group in groups if isinstance(group, dict)]
    leaderboard_eligible = [claim["id"] for claim in claims if claim["leaderboard_eligible"]]
    disclosure_required = [claim["id"] for claim in claims if claim["disclosure_required"]]
    status_counts: dict[str, int] = {}
    for claim in claims:
        status = str(claim["claim_status"])
        status_counts[status] = status_counts.get(status, 0) + 1
    primary_policy = (
        "standardized-primary-ranking-allowed-when-run-telemetry-audit-passes"
        if leaderboard_eligible
        else "do-not-rank-on-provider-native-stats-without-additional-calibration"
    )
    return {
        "schema_version": METRIC_CLAIM_CONTRACT_SCHEMA_VERSION,
        "group_count": len(claims),
        "claim_status_counts": dict(sorted(status_counts.items())),
        "leaderboard_eligible_groups": leaderboard_eligible,
        "disclosure_required_groups": disclosure_required,
        "primary_score_policy": primary_policy,
        "required_run_artifacts": ["normalized-results", "telemetry-audit"],
        "groups": claims,
        "security": {
            "contains_raw_provider_payloads": False,
            "contains_secrets": False,
            "contacts_providers": False,
            "resolves_secrets": False,
        },
    }


def _claim_contract_group(group: dict[str, Any]) -> dict[str, Any]:
    status = str(group.get("status") or "unavailable")
    if status == "publication-grade":
        claim_status = "standardized"
        claim_policy = "may-use-for-cross-engine-leaderboard-when-run-telemetry-audit-passes"
    elif status == "advisory-only":
        claim_status = "advisory"
        claim_policy = "label-inferred-or-conditional-fields-and-avoid-primary-ranking"
    elif status == "partial":
        claim_status = "limited"
        claim_policy = "publish-only-with-missing-field-disclosure-and-do-not-rank-on-missing-fields"
    else:
        claim_status = "unsupported"
        claim_policy = "do-not-make-cross-engine-claims-for-this-metric-family"
    return {
        "id": str(group.get("id") or "unknown"),
        "claim_status": claim_status,
        "leaderboard_eligible": claim_status == "standardized",
        "disclosure_required": claim_status != "standardized",
        "claim_policy": claim_policy,
        "claim_guidance": str(group.get("claim_guidance") or ""),
        "publication_grade_fields": [str(item) for item in group.get("publication_grade_fields", []) if item],
        "advisory_fields": [str(item) for item in group.get("advisory_fields", []) if item],
        "unavailable_fields": [str(item) for item in group.get("unavailable_fields", []) if item],
    }


def _metric_group_profile(group_id: str, fields: tuple[str, ...], field_map: dict[str, MetricCoverageItem]) -> dict[str, Any]:
    group_items = [
        field_map.get(
            field,
            MetricCoverageItem(field, "unavailable", "not mapped", "No static metric coverage mapping is available for this field."),
        )
        for field in fields
    ]
    counts = {status: 0 for status in STATUS_ORDER}
    for item in group_items:
        counts[item.status] = counts.get(item.status, 0) + 1
    unavailable_fields = [item.field for item in group_items if item.status == "unavailable"]
    advisory_fields = [item.field for item in group_items if item.status in ADVISORY_STATUSES]
    publication_grade_fields = [item.field for item in group_items if item.status in PUBLICATION_GRADE_STATUSES]
    if len(unavailable_fields) == len(group_items):
        status = "unavailable"
        guidance = "insufficient-for-publication-claim"
    elif unavailable_fields:
        status = "partial"
        guidance = "publish-only-with-explicit-missing-field-disclosure"
    elif advisory_fields:
        status = "advisory-only"
        guidance = "label-inferred-or-conditional-metrics-before-comparison"
    else:
        status = "publication-grade"
        guidance = "suitable-for-standardized-comparison-when-run-telemetry-audit-passes"
    return {
        "id": group_id,
        "status": status,
        "claim_guidance": guidance,
        "field_count": len(group_items),
        "coverage_score": _coverage_score(group_items),
        "counts": counts,
        "publication_grade_fields": publication_grade_fields,
        "advisory_fields": advisory_fields,
        "unavailable_fields": unavailable_fields,
    }
