from __future__ import annotations


def classify_response_failure(
    *,
    status_code: int | None,
    assertion_ok: bool,
    assertion_message: str,
) -> str | None:
    if status_code is not None and 200 <= status_code < 300 and assertion_ok:
        return None

    if status_code == 429:
        return "rate_limit"
    if status_code in {401, 403}:
        return "environmental"
    if status_code in {400, 404, 405, 415, 422}:
        return "engine_feature_gap"
    if status_code in {408, 500, 502, 503, 504}:
        return "engine_runtime_bug"
    if status_code is not None and not 200 <= status_code < 300:
        return "engine_protocol_bug"

    lowered = assertion_message.lower()
    if "not valid json" in lowered or "json field" in lowered:
        return "model_quality"
    if "missing expected tool call" in lowered:
        return "model_quality"
    if "simulated tool" in lowered:
        return "harness_bug"
    return "model_quality"


def classify_exception_failure(message: str) -> str:
    lowered = message.lower()
    if "rate limit" in lowered or "429" in lowered:
        return "rate_limit"
    if "timeout" in lowered or "timed out" in lowered:
        return "engine_runtime_bug"
    if "connection refused" in lowered or "connecterror" in lowered or "name or service" in lowered:
        return "environmental"
    if "unknown simulated tool" in lowered or "unknown mcp profile" in lowered or "unknown skill pack" in lowered:
        return "harness_bug"
    if "json" in lowered or "malformed" in lowered or "invalid response" in lowered:
        return "engine_protocol_bug"
    return "engine_runtime_bug"
