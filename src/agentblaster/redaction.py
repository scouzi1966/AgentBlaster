from __future__ import annotations

import re
from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any

SECRET_HEADER_NAMES = {
    "authorization",
    "x-api-key",
    "api-key",
    "openai-api-key",
    "anthropic-api-key",
}

SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"sk-(?!ant-)[A-Za-z0-9_\-]{16,}"),
    re.compile(r"gh[opusr]_[A-Za-z0-9_]{16,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]{16,}", re.IGNORECASE),
]


def redact_text(value: str) -> str:
    redacted = value
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def redact_mapping_headers(headers: Mapping[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in headers.items():
        if key.lower() in SECRET_HEADER_NAMES:
            redacted[key] = "[REDACTED]"
        elif isinstance(value, str):
            redacted[key] = redact_text(value)
        else:
            redacted[key] = redact_value(value)
    return redacted


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return redact_mapping_headers(value)
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | str):
        return [redact_value(item) for item in value]
    return value


def redact_in_place(value: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    for key in list(value.keys()):
        if key.lower() in SECRET_HEADER_NAMES:
            value[key] = "[REDACTED]"
        else:
            value[key] = redact_value(value[key])
    return value
