from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from agentblaster.models import ApiContract


NORMALIZED_TELEMETRY_FIELDS: tuple[str, ...] = (
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
    "load_ms",
    "prompt_eval_ms",
    "decode_ms",
    "tokens_per_second_prefill",
    "tokens_per_second_decode",
    "finish_reason",
    "raw_usage",
    "raw_stats",
)

COMPARABLE_TELEMETRY_FIELDS: tuple[str, ...] = (
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
    "load_ms",
    "prompt_eval_ms",
    "decode_ms",
    "tokens_per_second_prefill",
    "tokens_per_second_decode",
)

PUBLICATION_GRADE_TELEMETRY_QUALITY = {"native", "measured"}
ADVISORY_TELEMETRY_QUALITY = {"inferred", "conditional"}


@dataclass(frozen=True)
class TelemetryMapping:
    profile: str
    contract: str
    native_adapter: str | None
    source_family: str
    metric_sources: dict[str, str]
    notes: tuple[str, ...]


def normalize_response_telemetry(
    contract: ApiContract,
    raw: Mapping[str, Any] | None,
    *,
    native_adapter: str | None = None,
    latency_ms: float | None = None,
    queue_ms: float | None = None,
    rate_limit_wait_ms: float | None = None,
    ttft_ms: float | None = None,
) -> dict[str, Any]:
    """Normalize raw provider usage/stat fields into AgentBlaster's comparable telemetry shape."""
    raw_map = _as_mapping(raw)
    values: dict[str, Any] = {field: None for field in NORMALIZED_TELEMETRY_FIELDS}
    sources: dict[str, str] = {}

    if latency_ms is not None:
        _set(values, sources, "latency_ms", _number(latency_ms), "agentblaster timer")
    if queue_ms is not None:
        _set(values, sources, "queue_ms", _number(queue_ms), "agentblaster scheduler")
    if rate_limit_wait_ms is not None:
        _set(values, sources, "rate_limit_wait_ms", _number(rate_limit_wait_ms), "agentblaster provider pacer")
    if ttft_ms is not None:
        _set(values, sources, "ttft_ms", _number(ttft_ms), "agentblaster streaming timer")

    if contract is ApiContract.OPENAI:
        _normalize_openai_chat(raw_map, values, sources)
    elif contract is ApiContract.OPENAI_RESPONSES:
        _normalize_openai_responses(raw_map, values, sources)
    elif contract is ApiContract.ANTHROPIC:
        _normalize_anthropic(raw_map, values, sources)
    elif contract is ApiContract.NATIVE:
        _normalize_native(raw_map, values, sources, native_adapter=native_adapter)
    _normalize_http_metadata(raw_map, values, sources)

    if not values["raw_usage"]:
        usage = _as_mapping(raw_map.get("usage"))
        if usage:
            values["raw_usage"] = dict(usage)
    if not values["raw_stats"]:
        stats = _stats_map(raw_map)
        if stats:
            values["raw_stats"] = dict(stats)

    _derive_cache_hit_ratio(values, sources)
    quality = _telemetry_quality(values, sources)
    stats_profile = _stats_profile(contract, native_adapter)
    return {
        "schema_version": "agentblaster.normalized-telemetry.v1",
        "contract": contract.value,
        "native_adapter": native_adapter,
        "stats_profile": stats_profile,
        "values": values,
        "sources": sources,
        "quality": quality,
        "comparison_readiness": _telemetry_comparison_readiness(values, quality),
        "stats_comparability": _telemetry_stats_comparability(stats_profile, values, quality),
        "missing": [field for field in NORMALIZED_TELEMETRY_FIELDS if values.get(field) is None and field not in {"raw_usage", "raw_stats"}],
    }


def telemetry_mapping_catalog() -> dict[str, Any]:
    mappings = (
        TelemetryMapping(
            profile="generic-openai-chat",
            contract=ApiContract.OPENAI.value,
            native_adapter=None,
            source_family="OpenAI-compatible Chat Completions",
            metric_sources={
                "input_tokens": "usage.prompt_tokens",
                "output_tokens": "usage.completion_tokens",
                "total_tokens": "usage.total_tokens",
                "cached_input_tokens": "usage.prompt_tokens_details.cached_tokens",
                "status_code": "agentblaster_http.status_code",
                "provider_request_id": "agentblaster_http safe request-id headers",
                "provider_rate_limit_remaining": "agentblaster_http safe rate-limit headers",
                "finish_reason": "choices[0].finish_reason",
                "ttft_ms": "AgentBlaster streaming timer",
            },
            notes=(
                "Cache-write tokens and native prefill/decode durations are not standardized on Chat Completions.",
                "OpenAI-compatible local engines may expose additional native stats under provider-specific keys.",
            ),
        ),
        TelemetryMapping(
            profile="openai-responses",
            contract=ApiContract.OPENAI_RESPONSES.value,
            native_adapter=None,
            source_family="OpenAI Responses-compatible",
            metric_sources={
                "input_tokens": "usage.input_tokens",
                "output_tokens": "usage.output_tokens",
                "total_tokens": "usage.total_tokens",
                "cached_input_tokens": "usage.input_tokens_details.cached_tokens",
                "status_code": "agentblaster_http.status_code",
                "provider_request_id": "agentblaster_http safe request-id headers",
                "provider_rate_limit_remaining": "agentblaster_http safe rate-limit headers",
                "finish_reason": "status or completion event status",
                "ttft_ms": "AgentBlaster streaming timer",
            },
            notes=("Responses-style status is normalized as finish_reason only when no richer stop reason is present.",),
        ),
        TelemetryMapping(
            profile="anthropic-messages",
            contract=ApiContract.ANTHROPIC.value,
            native_adapter=None,
            source_family="Anthropic Messages-compatible",
            metric_sources={
                "input_tokens": "usage.input_tokens",
                "output_tokens": "usage.output_tokens",
                "cached_input_tokens": "usage.cache_read_input_tokens",
                "cache_write_tokens": "usage.cache_creation_input_tokens",
                "total_tokens": "derived from usage input/output/cache counters",
                "status_code": "agentblaster_http.status_code",
                "provider_request_id": "agentblaster_http safe request-id headers",
                "provider_rate_limit_remaining": "agentblaster_http safe rate-limit headers",
                "finish_reason": "stop_reason",
                "ttft_ms": "AgentBlaster streaming timer",
            },
            notes=("Prompt-cache accounting is standardized enough to report cache read and cache creation tokens separately.",),
        ),
        TelemetryMapping(
            profile="afm-mlx-openai-compatible",
            contract=ApiContract.OPENAI.value,
            native_adapter="afm-mlx",
            source_family="AFM MLX OpenAI-compatible plus optional native stats",
            metric_sources={
                "input_tokens": "usage.prompt_tokens",
                "output_tokens": "usage.completion_tokens",
                "prompt_eval_ms": "stats.prompt_eval_ms or metrics.prefill_ms",
                "decode_ms": "stats.decode_ms or metrics.decode_ms",
                "tokens_per_second_prefill": "stats.tokens_per_second_prefill or metrics.prefill_tokens_per_second",
                "tokens_per_second_decode": "stats.tokens_per_second_decode or metrics.tokens_per_second",
                "cached_input_tokens": "usage.prompt_tokens_details.cached_tokens or stats.cached_input_tokens",
            },
            notes=("AFM should prefer explicit native stats when available so MLX cache/prefill improvements are visible.",),
        ),
        TelemetryMapping(
            profile="ollama-native",
            contract=ApiContract.NATIVE.value,
            native_adapter="ollama",
            source_family="Ollama native generate/chat stats",
            metric_sources={
                "input_tokens": "prompt_eval_count",
                "output_tokens": "eval_count",
                "prompt_eval_ms": "prompt_eval_duration nanoseconds converted to milliseconds",
                "decode_ms": "eval_duration nanoseconds converted to milliseconds",
                "load_ms": "load_duration nanoseconds converted to milliseconds",
                "tokens_per_second_prefill": "prompt_eval_count / prompt_eval_duration",
                "tokens_per_second_decode": "eval_count / eval_duration",
                "finish_reason": "done_reason or done",
            },
            notes=("Ollama duration fields are nanoseconds and must not be compared as milliseconds without conversion.",),
        ),
        TelemetryMapping(
            profile="lm-studio-native",
            contract=ApiContract.NATIVE.value,
            native_adapter="lm-studio",
            source_family="LM Studio native/OpenAI-like stats",
            metric_sources={
                "input_tokens": "usage.prompt_tokens",
                "output_tokens": "usage.completion_tokens",
                "total_tokens": "usage.total_tokens",
                "ttft_ms": "stats.ttft_ms or stats.ttft_seconds",
                "tokens_per_second_decode": "stats.tokens_per_second",
                "finish_reason": "finish_reason or stop_reason",
            },
            notes=("LM Studio-compatible endpoints vary by mode; raw_stats is preserved for audit.",),
        ),
        TelemetryMapping(
            profile="mlx-lm-openai-compatible",
            contract=ApiContract.OPENAI.value,
            native_adapter="mlx-lm",
            source_family="MLX-LM OpenAI-compatible wrappers",
            metric_sources={
                "input_tokens": "usage.prompt_tokens when exposed",
                "output_tokens": "usage.completion_tokens when exposed",
                "tokens_per_second_decode": "stats.tokens_per_second when exposed",
                "ttft_ms": "AgentBlaster streaming timer",
            },
            notes=("MLX-LM wrappers should be treated as OpenAI-compatible first, then enriched with optional native stats.",),
        ),
        TelemetryMapping(
            profile="rapid-mlx-openai-compatible",
            contract=ApiContract.OPENAI.value,
            native_adapter="rapid-mlx",
            source_family="Rapid MLX OpenAI-compatible wrappers",
            metric_sources={
                "input_tokens": "usage.prompt_tokens when exposed",
                "output_tokens": "usage.completion_tokens when exposed",
                "prompt_eval_ms": "stats.prefill_ms when exposed",
                "tokens_per_second_prefill": "stats.prefill_tokens_per_second when exposed",
                "tokens_per_second_decode": "stats.tokens_per_second when exposed",
            },
            notes=("Rapid MLX mappings remain optional until response stats stabilize across versions.",),
        ),
        TelemetryMapping(
            profile="omlx-openai-compatible",
            contract=ApiContract.OPENAI.value,
            native_adapter="omlx",
            source_family="oMLX OpenAI-compatible wrappers",
            metric_sources={
                "input_tokens": "usage.prompt_tokens when exposed",
                "output_tokens": "usage.completion_tokens when exposed",
                "prompt_eval_ms": "stats.prompt_eval_ms or stats.prefill_ms when exposed",
                "tokens_per_second_prefill": "stats.tokens_per_second_prefill or stats.prefill_tokens_per_second when exposed",
                "tokens_per_second_decode": "stats.tokens_per_second_decode or stats.tokens_per_second when exposed",
                "ttft_ms": "AgentBlaster streaming timer",
            },
            notes=("oMLX mappings remain conditional until response stats stabilize across versions.",),
        ),
    )
    return {
        "schema_version": "agentblaster.telemetry-mapping-catalog.v1",
        "normalized_fields": list(NORMALIZED_TELEMETRY_FIELDS),
        "mappings": [asdict(mapping) for mapping in mappings],
        "stats_comparability": _stats_comparability_catalog(),
        "notes": [
            "The catalog documents how raw provider telemetry is normalized; it is not a live endpoint probe.",
            "Missing fields remain null rather than being guessed.",
            "raw_usage and merged stats/metrics/timings raw_stats are retained in compact form for auditability and future mappings.",
            "Optional timing aliases are normalized only when the source key states milliseconds, seconds, or nanoseconds explicitly.",
            "Stats comparability guidance must be preserved in reports when native provider fields use different units or semantics.",
        ],
    }


def _stats_comparability_catalog() -> dict[str, Any]:
    return {
        "schema_version": "agentblaster.stats-comparability.v1",
        "publication_grade_qualities": sorted(PUBLICATION_GRADE_TELEMETRY_QUALITY),
        "advisory_qualities": sorted(ADVISORY_TELEMETRY_QUALITY),
        "field_semantics": {
            "latency_ms": "AgentBlaster wall-clock request latency; comparable across engines when queue/rate-limit waits are disclosed separately.",
            "queue_ms": "AgentBlaster scheduler queue wait; comparable across local and remote providers.",
            "rate_limit_wait_ms": "AgentBlaster provider-pacer wait; comparable as harness overhead, not model runtime.",
            "ttft_ms": "AgentBlaster streaming timer when measured; provider-native TTFT aliases remain raw_stats unless mapped explicitly.",
            "prompt_eval_ms": "Native or conditional prefill duration; compare only when source units and prompt-token accounting are disclosed.",
            "decode_ms": "Native or conditional decode duration; compare only when source units and output-token accounting are disclosed.",
            "tokens_per_second_prefill": "Native or inferred prefill throughput; publication-grade only when emitted natively or measured consistently.",
            "tokens_per_second_decode": "Native, measured, conditional, or inferred decode throughput depending on provider stats.",
            "cached_input_tokens": "Provider-specific cache-read accounting; OpenAI-compatible cached tokens and Anthropic cache-read tokens are related but not identical claims.",
            "cache_write_tokens": "Provider-specific cache-write/create accounting; Anthropic cache creation and local engine cache writes must be labeled separately.",
            "cache_hit_ratio": "Derived advisory metric unless provider emits a native hit ratio.",
        },
        "profile_guidance": {
            "generic-openai-chat": "Token counts are native when usage is returned; prefill/decode timings are unavailable unless wrapper-specific stats are present.",
            "afm-mlx-openai-compatible": "AFM extension stats can support publication-grade prefill/decode claims when native fields are emitted and retained in normalized telemetry.",
            "mlx-lm-openai-compatible": "Treat wrapper timing fields as conditional unless a specific server version documents them; AgentBlaster-measured TTFT remains comparable.",
            "rapid-mlx-openai-compatible": "Treat prefill/decode stats as emerging and disclose source names before cross-engine publication.",
            "omlx-openai-compatible": "Treat prefill/decode stats as emerging and disclose source names before cross-engine publication.",
            "ollama-native": "Durations are nanoseconds in native responses and must be converted to milliseconds; throughput is inferred from counts and durations.",
            "lm-studio-native": "LM Studio stat aliases vary by mode/version; publish native and measured fields separately from conditional fields.",
            "anthropic-messages": "Cache read/create token counters are native for Anthropic-style prompt caching, but prefill/decode runtime is unavailable in standard usage.",
        },
        "security": {
            "contains_raw_provider_payloads": False,
            "contains_raw_secrets": False,
            "resolves_secrets": False,
            "contacts_providers": False,
        },
    }


def _stats_profile(contract: ApiContract, native_adapter: str | None) -> str:
    if contract is ApiContract.OPENAI:
        if native_adapter in {"afm-mlx", "mlx-lm", "rapid-mlx", "omlx"}:
            return f"{native_adapter}-openai-compatible"
        return "generic-openai-chat"
    if contract is ApiContract.OPENAI_RESPONSES:
        return "openai-responses"
    if contract is ApiContract.ANTHROPIC:
        return "anthropic-messages"
    if contract is ApiContract.NATIVE and native_adapter:
        return f"{native_adapter}-native"
    return "unknown-native"


def _telemetry_stats_comparability(
    stats_profile: str,
    values: dict[str, Any],
    quality: dict[str, str],
) -> dict[str, Any]:
    timing_fields = ("ttft_ms", "prompt_eval_ms", "decode_ms", "tokens_per_second_prefill", "tokens_per_second_decode")
    cache_fields = ("cached_input_tokens", "cache_write_tokens", "cache_hit_ratio")
    publication_grade = [
        field
        for field in timing_fields + cache_fields
        if values.get(field) is not None and quality.get(field) in PUBLICATION_GRADE_TELEMETRY_QUALITY
    ]
    advisory = [
        field
        for field in timing_fields + cache_fields
        if values.get(field) is not None and quality.get(field) in ADVISORY_TELEMETRY_QUALITY
    ]
    missing = [field for field in timing_fields + cache_fields if values.get(field) is None]
    return {
        "schema_version": "agentblaster.response-stats-comparability.v1",
        "profile": stats_profile,
        "publication_grade_fields": publication_grade,
        "advisory_fields": advisory,
        "missing_stats_fields": missing,
        "requires_labeling": bool(advisory or missing),
        "guidance": (
            "publish-native-and-measured-fields-separately-from-inferred-conditional-or-missing-stats"
            if advisory or missing
            else "stats-fields-ready-for-like-for-like-comparison"
        ),
        "security": {
            "contains_raw_provider_payloads": False,
            "contains_raw_secrets": False,
            "resolves_secrets": False,
        },
    }


def telemetry_mapping_catalog_json() -> str:
    return json.dumps(telemetry_mapping_catalog(), indent=2, sort_keys=True) + "\n"


def normalized_response_telemetry_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def format_normalized_response_telemetry(report: dict[str, Any]) -> str:
    values = report["values"]
    sources = report["sources"]
    present = [field for field in NORMALIZED_TELEMETRY_FIELDS if values.get(field) is not None]
    lines = [
        "AgentBlaster normalized response telemetry",
        f"schema_version: {report['schema_version']}",
        f"contract: {report['contract']}",
        f"native_adapter: {report.get('native_adapter') or 'none'}",
        f"stats_profile: {report.get('stats_profile') or 'unknown'}",
        f"fields_present: {len(present)}",
        f"fields_missing: {len(report['missing'])}",
        "values:",
    ]
    for field in present:
        source = sources.get(field, "unknown")
        lines.append(f"- {field}: {values[field]} [{source}]")
    if report["missing"]:
        lines.append("missing:")
        for field in report["missing"]:
            lines.append(f"- {field}")
    readiness = report.get("comparison_readiness")
    if readiness:
        lines.extend(
            [
                "comparison_readiness:",
                f"- publication_grade_fields: {readiness['publication_grade_field_count']}",
                f"- advisory_fields: {readiness['advisory_field_count']}",
                f"- missing_comparable_fields: {len(readiness['missing_comparable_fields'])}",
                f"- guidance: {readiness['guidance']}",
            ]
        )
    stats_comparability = report.get("stats_comparability")
    if stats_comparability:
        lines.extend(
            [
                "stats_comparability:",
                f"- profile: {stats_comparability.get('profile')}",
                f"- requires_labeling: {str(stats_comparability.get('requires_labeling')).lower()}",
                f"- guidance: {stats_comparability.get('guidance')}",
            ]
        )
    return "\n".join(lines) + "\n"


def format_telemetry_mapping_catalog(markdown: bool = False) -> str:
    catalog = telemetry_mapping_catalog()
    if markdown:
        lines = [
            "# AgentBlaster Telemetry Mapping Catalog",
            "",
            f"Schema: `{catalog['schema_version']}`",
            "",
            "The catalog standardizes raw usage and timing fields across local and remote provider contracts.",
            "",
        ]
        for mapping in catalog["mappings"]:
            lines.extend(
                [
                    f"## `{mapping['profile']}`",
                    "",
                    f"- Contract: `{mapping['contract']}`",
                    f"- Native adapter: `{mapping['native_adapter'] or 'none'}`",
                    f"- Source family: {mapping['source_family']}",
                    "- Metric sources:",
                ]
            )
            for field, source in mapping["metric_sources"].items():
                lines.append(f"  - `{field}`: {source}")
            for note in mapping["notes"]:
                lines.append(f"- Note: {note}")
            lines.append("")
        return "\n".join(lines)

    lines = ["AgentBlaster telemetry mapping catalog", f"normalized_fields: {len(catalog['normalized_fields'])}", "mappings:"]
    for mapping in catalog["mappings"]:
        native = mapping["native_adapter"] or "none"
        lines.append(f"- {mapping['profile']} ({mapping['contract']}, native={native}): {mapping['source_family']}")
    return "\n".join(lines) + "\n"


def _normalize_openai_chat(raw: Mapping[str, Any], values: dict[str, Any], sources: dict[str, str]) -> None:
    usage = _as_mapping(raw.get("usage"))
    _set(values, sources, "raw_usage", dict(usage), "usage")
    _set(values, sources, "input_tokens", _integer(usage.get("prompt_tokens")), "usage.prompt_tokens")
    _set(values, sources, "output_tokens", _integer(usage.get("completion_tokens")), "usage.completion_tokens")
    _set(values, sources, "total_tokens", _integer(usage.get("total_tokens")), "usage.total_tokens")
    details = _as_mapping(usage.get("prompt_tokens_details"))
    _set(values, sources, "cached_input_tokens", _integer(details.get("cached_tokens")), "usage.prompt_tokens_details.cached_tokens")
    _set(values, sources, "finish_reason", _first_choice_finish_reason(raw), "choices[0].finish_reason")
    _normalize_optional_stats(raw, values, sources)


def _normalize_openai_responses(raw: Mapping[str, Any], values: dict[str, Any], sources: dict[str, str]) -> None:
    usage = _as_mapping(raw.get("usage"))
    _set(values, sources, "raw_usage", dict(usage), "usage")
    _set(values, sources, "input_tokens", _integer(usage.get("input_tokens")), "usage.input_tokens")
    _set(values, sources, "output_tokens", _integer(usage.get("output_tokens")), "usage.output_tokens")
    _set(values, sources, "total_tokens", _integer(usage.get("total_tokens")), "usage.total_tokens")
    details = _as_mapping(usage.get("input_tokens_details"))
    _set(values, sources, "cached_input_tokens", _integer(details.get("cached_tokens")), "usage.input_tokens_details.cached_tokens")
    _set(values, sources, "finish_reason", _string(raw.get("status")), "status")
    _normalize_optional_stats(raw, values, sources)


def _normalize_anthropic(raw: Mapping[str, Any], values: dict[str, Any], sources: dict[str, str]) -> None:
    usage = _as_mapping(raw.get("usage"))
    _set(values, sources, "raw_usage", dict(usage), "usage")
    input_tokens = _integer(usage.get("input_tokens"))
    output_tokens = _integer(usage.get("output_tokens"))
    cache_read = _integer(usage.get("cache_read_input_tokens"))
    cache_write = _integer(usage.get("cache_creation_input_tokens"))
    _set(values, sources, "input_tokens", input_tokens, "usage.input_tokens")
    _set(values, sources, "output_tokens", output_tokens, "usage.output_tokens")
    _set(values, sources, "cached_input_tokens", cache_read, "usage.cache_read_input_tokens")
    _set(values, sources, "cache_write_tokens", cache_write, "usage.cache_creation_input_tokens")
    total = _sum_present(input_tokens, output_tokens, cache_read, cache_write)
    _set(values, sources, "total_tokens", total, "derived from Anthropic usage counters")
    _set(values, sources, "finish_reason", _string(raw.get("stop_reason")), "stop_reason")
    _normalize_optional_stats(raw, values, sources)


def _normalize_native(
    raw: Mapping[str, Any],
    values: dict[str, Any],
    sources: dict[str, str],
    *,
    native_adapter: str | None,
) -> None:
    adapter = (native_adapter or "").lower()
    if adapter == "ollama" or "prompt_eval_count" in raw or "eval_count" in raw:
        _normalize_ollama(raw, values, sources)
    elif adapter == "lm-studio" or _looks_like_lm_studio_stats(raw):
        _normalize_lm_studio(raw, values, sources)
    else:
        _normalize_openai_like_usage(raw, values, sources)
        _normalize_optional_stats(raw, values, sources)


def _normalize_ollama(raw: Mapping[str, Any], values: dict[str, Any], sources: dict[str, str]) -> None:
    _set(values, sources, "input_tokens", _integer(raw.get("prompt_eval_count")), "prompt_eval_count")
    _set(values, sources, "output_tokens", _integer(raw.get("eval_count")), "eval_count")
    _set(values, sources, "total_tokens", _sum_present(values.get("input_tokens"), values.get("output_tokens")), "prompt_eval_count + eval_count")
    _set(values, sources, "load_ms", _ns_to_ms(raw.get("load_duration")), "load_duration nanoseconds")
    _set(values, sources, "prompt_eval_ms", _ns_to_ms(raw.get("prompt_eval_duration")), "prompt_eval_duration nanoseconds")
    _set(values, sources, "decode_ms", _ns_to_ms(raw.get("eval_duration")), "eval_duration nanoseconds")
    _set(values, sources, "tokens_per_second_prefill", _tokens_per_second(raw.get("prompt_eval_count"), raw.get("prompt_eval_duration")), "prompt_eval_count / prompt_eval_duration")
    _set(values, sources, "tokens_per_second_decode", _tokens_per_second(raw.get("eval_count"), raw.get("eval_duration")), "eval_count / eval_duration")
    finish = _string(raw.get("done_reason"))
    if finish is None and raw.get("done") is True:
        finish = "done"
    _set(values, sources, "finish_reason", finish, "done_reason or done")
    stats = {key: raw[key] for key in ("load_duration", "prompt_eval_duration", "eval_duration", "prompt_eval_count", "eval_count", "done_reason") if key in raw}
    _set(values, sources, "raw_stats", stats, "ollama native stats")


def _normalize_lm_studio(raw: Mapping[str, Any], values: dict[str, Any], sources: dict[str, str]) -> None:
    _normalize_openai_like_usage(raw, values, sources)
    stats = _stats_map(raw)
    _set(values, sources, "raw_stats", dict(stats), "stats")
    _set(values, sources, "input_tokens", _first_integer(stats, "input_tokens", "prompt_tokens"), "stats.input_tokens")
    _set(values, sources, "output_tokens", _first_integer(stats, "total_output_tokens", "output_tokens", "completion_tokens"), "stats.total_output_tokens")
    if values.get("total_tokens") is None and (values.get("input_tokens") is not None or values.get("output_tokens") is not None):
        _set(values, sources, "total_tokens", _sum_present(values.get("input_tokens"), values.get("output_tokens")), "stats input + output tokens")
    _set_if_missing(values, sources, "ttft_ms", _first_number(stats, "ttft_ms", "time_to_first_token_ms"), "stats.ttft_ms")
    if values.get("ttft_ms") is None:
        ttft_seconds = _first_number(stats, "time_to_first_token_seconds", "ttft_seconds", "ttft")
        _set(values, sources, "ttft_ms", ttft_seconds * 1000 if ttft_seconds is not None else None, "stats.ttft_seconds")
    load_seconds = _first_number(stats, "model_load_time_seconds", "model_load_time")
    if load_seconds is not None:
        _set(values, sources, "load_ms", load_seconds * 1000, "stats.model_load_time_seconds")
    _set(values, sources, "tokens_per_second_decode", _first_number(stats, "tokens_per_second", "decode_tokens_per_second", "output_tokens_per_second"), "stats.tokens_per_second")
    decode_tps = _number(values.get("tokens_per_second_decode"))
    output_tokens = _number(values.get("output_tokens"))
    if decode_tps is not None and output_tokens is not None and decode_tps > 0:
        _set(values, sources, "decode_ms", round((output_tokens / decode_tps) * 1000, 3), "output_tokens / stats.tokens_per_second")
    _set(values, sources, "finish_reason", _first_string(raw, "finish_reason", "stop_reason"), "finish_reason or stop_reason")


def _normalize_openai_like_usage(raw: Mapping[str, Any], values: dict[str, Any], sources: dict[str, str]) -> None:
    usage = _as_mapping(raw.get("usage"))
    _set(values, sources, "raw_usage", dict(usage), "usage")
    _set(values, sources, "input_tokens", _integer(usage.get("prompt_tokens")), "usage.prompt_tokens")
    _set(values, sources, "output_tokens", _integer(usage.get("completion_tokens")), "usage.completion_tokens")
    _set(values, sources, "total_tokens", _integer(usage.get("total_tokens")), "usage.total_tokens")
    details = _as_mapping(usage.get("prompt_tokens_details"))
    _set(values, sources, "cached_input_tokens", _integer(details.get("cached_tokens")), "usage.prompt_tokens_details.cached_tokens")


def _normalize_http_metadata(raw: Mapping[str, Any], values: dict[str, Any], sources: dict[str, str]) -> None:
    metadata = _as_mapping(raw.get("agentblaster_http"))
    if not metadata:
        return
    headers = _as_mapping(metadata.get("headers"))
    _set(values, sources, "status_code", _integer(metadata.get("status_code")), "agentblaster_http.status_code")
    _set(values, sources, "response_content_type", _string(metadata.get("content_type")), "agentblaster_http.content_type")
    request_id = _first_string(headers, "x-request-id", "openai-request-id", "anthropic-request-id", "request-id")
    _set(values, sources, "provider_request_id", request_id, "agentblaster_http.headers.request-id")
    rate_limit_remaining = _rate_limit_remaining(headers)
    _set(values, sources, "provider_rate_limit_remaining", rate_limit_remaining, "agentblaster_http.headers.x-ratelimit-remaining")
    retry_after_ms = _retry_after_ms(headers.get("retry-after"))
    _set(values, sources, "provider_retry_after_ms", retry_after_ms, "agentblaster_http.headers.retry-after")


def _telemetry_quality(values: Mapping[str, Any], sources: Mapping[str, str]) -> dict[str, str]:
    return {
        field: _telemetry_field_quality(field, sources.get(field))
        for field in NORMALIZED_TELEMETRY_FIELDS
        if values.get(field) is not None
    }


def _telemetry_field_quality(field: str, source: str | None) -> str:
    if field in {"raw_usage", "raw_stats"}:
        return "raw_provenance"
    if not source:
        return "unknown"
    normalized_source = source.lower()
    if normalized_source.startswith("agentblaster"):
        return "measured"
    if (
        " / " in normalized_source
        or "derived" in normalized_source
        or "input + output" in normalized_source
        or "stats input + output" in normalized_source
    ):
        return "inferred"
    if normalized_source.startswith(("usage", "stats", "metrics", "timings", "choices")):
        return "native"
    if normalized_source in {
        "stop_reason",
        "status",
        "done_reason",
        "done",
        "prompt_eval_count",
        "eval_count",
        "load_duration",
        "prompt_eval_duration",
        "eval_duration",
    }:
        return "native"
    if "when exposed" in normalized_source or "optional" in normalized_source:
        return "conditional"
    return "native"


def _telemetry_comparison_readiness(values: Mapping[str, Any], quality: Mapping[str, str]) -> dict[str, Any]:
    comparable_fields = [field for field in COMPARABLE_TELEMETRY_FIELDS if values.get(field) is not None]
    publication_grade_fields = [
        field for field in comparable_fields if quality.get(field) in PUBLICATION_GRADE_TELEMETRY_QUALITY
    ]
    advisory_fields = [field for field in comparable_fields if quality.get(field) in ADVISORY_TELEMETRY_QUALITY]
    raw_provenance_fields = [field for field, status in quality.items() if status == "raw_provenance"]
    missing_comparable_fields = [field for field in COMPARABLE_TELEMETRY_FIELDS if values.get(field) is None]
    if advisory_fields:
        guidance = "label-inferred-or-conditional-fields-before-cross-engine-comparison"
    elif publication_grade_fields:
        guidance = "publication-grade-for-present-fields-when-run-telemetry-audit-passes"
    else:
        guidance = "insufficient-normalized-telemetry-for-comparison"
    return {
        "schema_version": "agentblaster.telemetry-comparison-readiness.v1",
        "field_count": len(comparable_fields),
        "publication_grade_field_count": len(publication_grade_fields),
        "advisory_field_count": len(advisory_fields),
        "raw_provenance_field_count": len(raw_provenance_fields),
        "publication_grade_fields": publication_grade_fields,
        "advisory_fields": advisory_fields,
        "raw_provenance_fields": raw_provenance_fields,
        "missing_comparable_fields": missing_comparable_fields,
        "guidance": guidance,
    }
    _set(values, sources, "finish_reason", _first_choice_finish_reason(raw) or _first_string(raw, "finish_reason", "stop_reason"), "finish_reason")


def _normalize_optional_stats(raw: Mapping[str, Any], values: dict[str, Any], sources: dict[str, str]) -> None:
    stats = _stats_map(raw)
    if not stats:
        return
    _set(values, sources, "raw_stats", dict(stats), "stats/metrics/timings")
    _set_duration_ms(
        values,
        sources,
        "ttft_ms",
        stats,
        only_if_missing=True,
        millisecond_keys=("ttft_ms", "time_to_first_token_ms"),
        second_keys=("ttft_seconds", "time_to_first_token_seconds", "ttft"),
        nanosecond_keys=("ttft_ns", "time_to_first_token_ns"),
    )
    _set_duration_ms(
        values,
        sources,
        "load_ms",
        stats,
        millisecond_keys=("load_ms", "model_load_ms"),
        second_keys=("load_seconds", "model_load_seconds", "model_load_time_seconds"),
        nanosecond_keys=("load_ns", "load_duration_ns", "model_load_ns"),
    )
    _set_duration_ms(
        values,
        sources,
        "prompt_eval_ms",
        stats,
        millisecond_keys=("prompt_eval_ms", "prompt_time_ms", "prefill_ms", "prefill_time_ms"),
        second_keys=("prompt_eval_seconds", "prompt_time_seconds", "prefill_seconds", "prefill_time_seconds"),
        nanosecond_keys=("prompt_eval_ns", "prompt_eval_duration_ns", "prefill_ns", "prefill_duration_ns"),
    )
    _set_duration_ms(
        values,
        sources,
        "decode_ms",
        stats,
        millisecond_keys=("decode_ms", "decode_time_ms", "generation_ms", "generation_time_ms"),
        second_keys=("decode_seconds", "decode_time_seconds", "generation_seconds", "generation_time_seconds"),
        nanosecond_keys=("decode_ns", "decode_duration_ns", "generation_ns", "generation_duration_ns"),
    )
    _set(values, sources, "tokens_per_second_prefill", _first_number(stats, "tokens_per_second_prefill", "prefill_tokens_per_second", "prompt_tokens_per_second", "prompt_tps", "prefill_tps"), "stats.tokens_per_second_prefill")
    _set(values, sources, "tokens_per_second_decode", _first_number(stats, "tokens_per_second_decode", "decode_tokens_per_second", "generation_tokens_per_second", "output_tokens_per_second", "tokens_per_second", "eval_tps", "decode_tps", "output_tps"), "stats.tokens_per_second_decode")
    if values.get("tokens_per_second_prefill") is None:
        prefill_tokens = _first_number(stats, "prompt_eval_count", "prefill_tokens", "prompt_tokens", "input_tokens")
        if prefill_tokens is None:
            prefill_tokens = _number(values.get("input_tokens"))
        _set(values, sources, "tokens_per_second_prefill", _tokens_per_second_ms(prefill_tokens, values.get("prompt_eval_ms")), "prompt/input tokens / prompt_eval_ms")
    if values.get("tokens_per_second_decode") is None:
        decode_tokens = _first_number(stats, "eval_count", "decode_tokens", "generation_tokens", "output_tokens", "completion_tokens")
        if decode_tokens is None:
            decode_tokens = _number(values.get("output_tokens"))
        _set(values, sources, "tokens_per_second_decode", _tokens_per_second_ms(decode_tokens, values.get("decode_ms")), "output/decode tokens / decode_ms")
    _set(values, sources, "cached_input_tokens", _first_integer(stats, "cached_input_tokens", "cache_read_tokens", "cache_hit_tokens", "prefix_cache_hit_tokens", "prompt_cache_hit_tokens"), "stats.cached_input_tokens")
    _set(values, sources, "cache_write_tokens", _first_integer(stats, "cache_write_tokens", "cache_creation_tokens", "cache_miss_tokens", "prefix_cache_write_tokens", "prompt_cache_write_tokens"), "stats.cache_write_tokens")
    _set(values, sources, "cache_hit_ratio", _first_ratio(stats, "cache_hit_ratio", "cache_hit_rate", "prefix_cache_hit_ratio", "prefix_cache_hit_rate", "cache_hit_percent", "cache_hit_percentage"), "stats.cache_hit_ratio")


def _derive_cache_hit_ratio(values: dict[str, Any], sources: dict[str, str]) -> None:
    if values.get("cache_hit_ratio") is not None:
        return
    cached = _number(values.get("cached_input_tokens"))
    if cached is None:
        return
    input_tokens = _number(values.get("input_tokens"))
    cache_write = _number(values.get("cache_write_tokens"))
    if cache_write is not None:
        denominator = (input_tokens or 0) + cached + cache_write
    elif input_tokens is not None:
        denominator = input_tokens
    else:
        denominator = cached
    if denominator <= 0:
        return
    _set(values, sources, "cache_hit_ratio", round(cached / denominator, 6), "derived from cache/input token counters")


def _set(values: dict[str, Any], sources: dict[str, str], field: str, value: Any, source: str) -> None:
    if value is None or value == {}:
        return
    values[field] = value
    sources[field] = source


def _set_if_missing(values: dict[str, Any], sources: dict[str, str], field: str, value: Any, source: str) -> None:
    if values.get(field) is not None:
        return
    _set(values, sources, field, value, source)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _looks_like_lm_studio_stats(raw: Mapping[str, Any]) -> bool:
    stats = raw.get("stats")
    if not isinstance(stats, Mapping):
        return False
    return any(
        key in stats
        for key in (
            "total_output_tokens",
            "time_to_first_token_seconds",
            "model_load_time_seconds",
            "tokens_per_second",
        )
    )


def _stats_map(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    merged: dict[str, Any] = {}
    for key in ("stats", "metrics", "timings"):
        candidate = raw.get(key)
        if isinstance(candidate, Mapping):
            merged.update(candidate)
    return merged


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _first_number(mapping: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _number(mapping.get(key))
        if value is not None:
            return value
    return None


def _first_ratio(mapping: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _number(mapping.get(key))
        if value is None:
            continue
        if 0 <= value <= 1:
            return round(value, 6)
        if ("percent" in key or key.endswith("_pct")) and 0 <= value <= 100:
            return round(value / 100, 6)
    return None


def _first_integer(mapping: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = _integer(mapping.get(key))
        if value is not None:
            return value
    return None


def _first_string(mapping: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = _string(mapping.get(key))
        if value is not None:
            return value
    return None


def _first_choice_finish_reason(raw: Mapping[str, Any]) -> str | None:
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, Mapping):
        return None
    return _string(first.get("finish_reason"))


def _sum_present(*values: Any) -> int | None:
    present = [_integer(value) for value in values if _integer(value) is not None]
    if not present:
        return None
    return sum(present)


def _ns_to_ms(value: Any) -> float | None:
    number = _number(value)
    if number is None:
        return None
    return round(number / 1_000_000, 3)


def _set_duration_ms(
    values: dict[str, Any],
    sources: dict[str, str],
    field: str,
    stats: Mapping[str, Any],
    *,
    millisecond_keys: tuple[str, ...],
    second_keys: tuple[str, ...] = (),
    nanosecond_keys: tuple[str, ...] = (),
    only_if_missing: bool = False,
) -> None:
    if only_if_missing and values.get(field) is not None:
        return
    value, source = _first_duration_ms(
        stats,
        millisecond_keys=millisecond_keys,
        second_keys=second_keys,
        nanosecond_keys=nanosecond_keys,
    )
    if source is not None:
        _set(values, sources, field, value, source)


def _first_duration_ms(
    mapping: Mapping[str, Any],
    *,
    millisecond_keys: tuple[str, ...],
    second_keys: tuple[str, ...] = (),
    nanosecond_keys: tuple[str, ...] = (),
) -> tuple[float | None, str | None]:
    for key in millisecond_keys:
        value = _number(mapping.get(key))
        if value is not None:
            return value, f"stats/metrics.{key}"
    for key in second_keys:
        value = _number(mapping.get(key))
        if value is not None:
            return round(value * 1000, 3), f"stats/metrics.{key}"
    for key in nanosecond_keys:
        value = _number(mapping.get(key))
        if value is not None:
            return _ns_to_ms(value), f"stats/metrics.{key}"
    return None, None


def _tokens_per_second(count: Any, duration_ns: Any) -> float | None:
    token_count = _number(count)
    duration = _number(duration_ns)
    if token_count is None or duration is None or duration <= 0:
        return None
    return round(token_count / (duration / 1_000_000_000), 3)


def _tokens_per_second_ms(count: Any, duration_ms: Any) -> float | None:
    token_count = _number(count)
    duration = _number(duration_ms)
    if token_count is None or duration is None or duration <= 0:
        return None
    return round(token_count / (duration / 1000), 3)


def _rate_limit_remaining(headers: Mapping[str, Any]) -> dict[str, int]:
    remaining: dict[str, int] = {}
    requests = _integer(headers.get("x-ratelimit-remaining-requests"))
    tokens = _integer(headers.get("x-ratelimit-remaining-tokens"))
    if requests is not None:
        remaining["requests"] = requests
    if tokens is not None:
        remaining["tokens"] = tokens
    return remaining


def _retry_after_ms(value: Any) -> float | None:
    seconds = _number(value)
    if seconds is None:
        return None
    return round(seconds * 1000, 3)
