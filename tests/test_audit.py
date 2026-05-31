from __future__ import annotations

import json

from agentblaster.audit import AuditLogger


def test_audit_logger_writes_redacted_jsonl(tmp_path) -> None:
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path)

    logger.emit("provider_created", authorization="Bearer abcdefghijklmnopqrstuvwxyz")

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["event"] == "provider_created"
    assert payload["authorization"] == "[REDACTED]"
