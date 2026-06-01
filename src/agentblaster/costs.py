from __future__ import annotations

from typing import Any


def estimate_costs(
    cost_model: dict[str, Any],
    *,
    input_tokens: int | None,
    output_tokens: int | None,
    cached_input_tokens: int | None = None,
    cache_write_tokens: int | None = None,
) -> dict[str, float | None]:
    if not cost_model:
        return {
            "input_cost_usd": None,
            "output_cost_usd": None,
            "cache_read_cost_usd": None,
            "cache_write_cost_usd": None,
            "request_cost_usd": None,
            "total_cost_usd": None,
        }

    cache_read_rate = _cost_rate(cost_model, "cached_input")
    billable_input_tokens = input_tokens
    if input_tokens is not None and cached_input_tokens is not None and cache_read_rate is not None:
        billable_input_tokens = max(input_tokens - cached_input_tokens, 0)
    input_cost = _token_cost(billable_input_tokens, _cost_rate(cost_model, "input"))
    output_cost = _token_cost(output_tokens, _cost_rate(cost_model, "output"))
    cache_read_cost = _token_cost(cached_input_tokens, cache_read_rate)
    cache_write_cost = _token_cost(cache_write_tokens, _cost_rate(cost_model, "cache_write"))
    request_cost = _optional_float(cost_model.get("request_usd"))
    components = [input_cost, output_cost, cache_read_cost, cache_write_cost, request_cost]
    present_components = [component for component in components if component is not None]
    total_cost = round(sum(present_components), 9) if present_components else None
    return {
        "input_cost_usd": input_cost,
        "output_cost_usd": output_cost,
        "cache_read_cost_usd": cache_read_cost,
        "cache_write_cost_usd": cache_write_cost,
        "request_cost_usd": request_cost,
        "total_cost_usd": total_cost,
    }


def _cost_rate(cost_model: dict[str, Any], name: str) -> float | None:
    return _optional_float(
        _first_present(
            cost_model.get(f"{name}_usd_per_1m_tokens"),
            cost_model.get(f"{name}_usd_per_million_tokens"),
        )
    )


def _token_cost(tokens: int | None, usd_per_1m_tokens: float | None) -> float | None:
    if tokens is None or usd_per_1m_tokens is None:
        return None
    return round((tokens / 1_000_000) * usd_per_1m_tokens, 9)


def _optional_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_present(*values):
    for value in values:
        if value is not None:
            return value
    return None
