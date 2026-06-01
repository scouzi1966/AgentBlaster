from __future__ import annotations

import socket

from agentblaster.environment import capture_environment
from agentblaster.models import ApiContract, RawTraceMode, RunManifest


def test_capture_environment_records_reproducibility_metadata_without_raw_hostname() -> None:
    snapshot = capture_environment()

    assert snapshot.python_version
    assert snapshot.os
    assert snapshot.cpu_count is None or snapshot.cpu_count > 0
    assert snapshot.hostname_sha256 is None or len(snapshot.hostname_sha256) == 64
    hostname = socket.gethostname()
    if hostname and snapshot.hostname_sha256 is not None:
        assert hostname not in snapshot.hostname_sha256


def test_run_manifest_has_environment_snapshot_by_default() -> None:
    manifest = RunManifest(
        run_id="run_test",
        suite="smoke",
        provider="local",
        contract=ApiContract.OPENAI,
        model="qwen-test",
        raw_trace_mode=RawTraceMode.OFF,
        created_at="2026-05-31T00:00:00Z",
    )

    payload = manifest.model_dump(mode="json")

    assert "environment" in payload
    assert payload["environment"]["ci"] is False
