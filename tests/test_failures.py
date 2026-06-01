from __future__ import annotations

from agentblaster.failures import classify_exception_failure, classify_response_failure


def test_classify_response_failure_handles_success_and_model_quality() -> None:
    assert classify_response_failure(status_code=200, assertion_ok=True, assertion_message="") is None
    assert (
        classify_response_failure(
            status_code=200,
            assertion_ok=False,
            assertion_message="missing expected substring: agentblaster-ok",
        )
        == "model_quality"
    )


def test_classify_response_failure_separates_http_failure_classes() -> None:
    assert classify_response_failure(status_code=429, assertion_ok=False, assertion_message="") == "rate_limit"
    assert classify_response_failure(status_code=401, assertion_ok=False, assertion_message="") == "environmental"
    assert classify_response_failure(status_code=404, assertion_ok=False, assertion_message="") == "engine_feature_gap"
    assert classify_response_failure(status_code=500, assertion_ok=False, assertion_message="") == "engine_runtime_bug"
    assert classify_response_failure(status_code=418, assertion_ok=False, assertion_message="") == "engine_protocol_bug"
    assert classify_response_failure(status_code=200, assertion_ok=False, assertion_message="cancellation was not observed") == "engine_feature_gap"
    assert classify_response_failure(status_code=200, assertion_ok=False, assertion_message="invalid tool call arguments") == "engine_protocol_bug"
    assert classify_response_failure(status_code=200, assertion_ok=False, assertion_message="missing expected tool call: search_docs") == "model_quality"


def test_classify_exception_failure_uses_message_hints() -> None:
    assert classify_exception_failure("429 rate limit exceeded") == "rate_limit"
    assert classify_exception_failure("client disconnect cancellation failed") == "engine_feature_gap"
    assert classify_exception_failure("request timeout") == "engine_runtime_bug"
    assert classify_exception_failure("connection refused on port 9999") == "environmental"
    assert classify_exception_failure("unknown MCP profile: host") == "harness_bug"
    assert classify_exception_failure("malformed tool envelope from provider") == "engine_protocol_bug"
    assert classify_exception_failure("malformed JSON response") == "engine_protocol_bug"
