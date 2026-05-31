from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentblaster.redaction import redact_value


class AuditLogger:
    """Structured JSONL audit logger for security-relevant events."""

    def __init__(self, path: Path | None) -> None:
        self.path = path

    def emit(self, event: str, **fields: Any) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event,
            **redact_value(fields),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
