from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from agentblaster.models import ApiContract


NORMALIZED_TELEMETRY_FIELDS: tuple[str, ...] = (
    "latency_ms",
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
    ttft_ms: float | None = None,
) -> dict[str, Any]:
    """Normalize raw provider usage/stat fields into AgentBlaster's comparable telemetry shape."""
    raw_map = _as_mapping(raw)
    values: dict[str, Any] = {field: None for field in NORMALIZED_TELEMETRY_FIELDS}
    sources: dict[str, str] = {}

    if latency_ms is not None:
        _set(values, sources, "latency_ms", _number(latency_ms), "agentblaster timer")
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

    if not values["raw_usage"]:
        usage = _as_mapping(raw_map.get("usage"))
        if usage:
            values["raw_usage"] = dict(usage)
    if not values["raw_stats"]:
        stats = _stats_map(raw_map)
        if stats:
            values["raw_stats"] = dict(stats)

    _derive_cache_hit_ratio(values, sources)
    return {
        "schema_version": "agentblaster.normalized-telemetry.v1",
        "contract": contract.value,
        "native_adapter": native_adapter,
        "values": values,
        "sources": sources,
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
    )
    return {
        "schema_version": "agentblaster.telemetry-mapping-catalog.v1",
        "normalized_fields": list(NORMALIZED_TELEMETRY_FIELDS),
        "mappings": [asdict(mapping) for mapping in mappings],
        "notes": [
            "The catalog documents how raw provider telemetry is normalized; it is not a live endpoint probe.",
            "Missing fields remain null rather than being guessed.",
            "raw_usage and raw_stats are retained in compact form for auditability and future mappings.",
        ],
    }


def telemetry_mapping_catalog_json() -> str:
    return json.dumps(telemetry_mapping_catalog(), indent=2, sort_keys=True) + "\n"


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
    _set(values, sources, "ttft_ms", _first_number(stats, "ttft_ms", "time_to_first_token_ms"), "stats.ttft_ms")
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
    _set(values, sources, "finish_reason", _first_choice_finish_reason(raw) or _first_string(raw, "finish_reason", "stop_reason"), "finish_reason")


def _normalize_optional_stats(raw: Mapping[str, Any], values: dict[str, Any], sources: dict[str, str]) -> None:
    stats = _stats_map(raw)
    if not stats:
        return
    _set(values, sources, "raw_stats", dict(stats), "stats/metrics/timings")
    _set(values, sources, "ttft_ms", _first_number(stats, "ttft_ms", "time_to_first_token_ms"), "stats.ttft_ms")
    ttft_seconds = _first_number(stats, "ttft_seconds", "ttft")
    if values.get("ttft_ms") is None and ttft_seconds is not None:
        _set(values, sources, "ttft_ms", ttft_seconds * 1000, "stats.ttft_seconds")
    _set(values, sources, "load_ms", _first_number(stats, "load_ms", "model_load_ms"), "stats.load_ms")
    _set(values, sources, "prompt_eval_ms", _first_number(stats, "prompt_eval_ms", "prompt_time_ms", "prefill_ms", "prefill_time_ms"), "stats.prompt_eval_ms/prefill_ms")
    _set(values, sources, "decode_ms", _first_number(stats, "decode_ms", "decode_time_ms", "generation_ms"), "stats.decode_ms")
    _set(values, sources, "tokens_per_second_prefill", _first_number(stats, "tokens_per_second_prefill", "prefill_tokens_per_second", "prompt_tps"), "stats.tokens_per_second_prefill")
    _set(values, sources, "tokens_per_second_decode", _first_number(stats, "tokens_per_second_decode", "decode_tokens_per_second", "tokens_per_second", "eval_tps"), "stats.tokens_per_second_decode")
    _set(values, sources, "cached_input_tokens", _first_integer(stats, "cached_input_tokens", "cache_read_tokens"), "stats.cached_input_tokens")
    _set(values, sources, "cache_write_tokens", _first_integer(stats, "cache_write_tokens", "cache_creation_tokens"), "stats.cache_write_tokens")


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
    for key in ("stats", "metrics", "timings"):
        candidate = raw.get(key)
        if isinstance(candidate, Mapping):
            return candidate
    return {}


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


def _tokens_per_second(count: Any, duration_ns: Any) -> float | None:
    token_count = _number(count)
    duration = _number(duration_ns)
    if token_count is None or duration is None or duration <= 0:
        return None
    return round(token_count / (duration / 1_000_000_000), 3)
