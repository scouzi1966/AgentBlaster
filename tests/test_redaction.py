from __future__ import annotations

from agentblaster.redaction import redact_mapping_headers, redact_text, redact_value


def test_redact_text_removes_common_token_shapes() -> None:
    text = "Authorization: Bearer abcdefghijklmnopqrstuvwxyz and sk-testsecretvalue123456789 and sk-ant-api03-secretvalue123456789"

    redacted = redact_text(text)

    assert "abcdefghijklmnopqrstuvwxyz" not in redacted
    assert "sk-testsecretvalue" not in redacted
    assert "sk-ant-api03" not in redacted
    assert "[REDACTED]" in redacted


def test_redact_mapping_headers_redacts_secret_headers() -> None:
    headers = {
        "Authorization": "Bearer abcdefghijklmnopqrstuvwxyz",
        "content-type": "application/json",
    }

    assert redact_mapping_headers(headers) == {
        "Authorization": "[REDACTED]",
        "content-type": "application/json",
    }


def test_redact_value_walks_nested_values() -> None:
    payload = {
        "headers": {"x-api-key": "sk-testsecretvalue123456789"},
        "items": ["safe", "gho_abcdefghijklmnopqrstuvwxyz123456"],
    }

    redacted = redact_value(payload)

    assert redacted["headers"]["x-api-key"] == "[REDACTED]"
    assert redacted["items"][0] == "safe"
    assert redacted["items"][1] == "[REDACTED]"
