from __future__ import annotations

import socket

from agentblaster.environment import build_environment_readiness, capture_environment, format_environment_readiness
from agentblaster.models import ApiContract, RawTraceMode, RunManifest
from agentblaster.policy import SecurityPolicy


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


def test_environment_readiness_is_static_and_redaction_safe(tmp_path) -> None:
    policy = SecurityPolicy(
        allow_remote_providers=False,
        require_dashboard_auth=True,
        require_cleanup_audit_log=True,
    )
    report = build_environment_readiness(home=tmp_path / "config", policy=policy)
    rendered = format_environment_readiness(report)

    assert report["schema_version"] == "agentblaster.environment-readiness.v1"
    assert "python-version" in {check["id"] for check in report["checks"]}
    assert "runtime-dependencies" in {check["id"] for check in report["checks"]}
    assert "keyring" in report["runtime_modules"]["optional"]
    assert report["policy_controls"]["allow_remote_providers"] is False
    assert report["policy_controls"]["require_dashboard_auth"] is True
    assert report["policy_controls"]["require_cleanup_audit_log"] is True
    assert report["config"]["providers_path"] == str(tmp_path / "config" / "providers.json")
    assert report["config"]["providers_config_exists"] is False
    assert "AgentBlaster environment readiness" in rendered
    assert "policy_controls:" in rendered
    assert "- require_cleanup_audit_log: true" in rendered
    assert "providers_path:" in rendered
    assert socket.gethostname() not in str(report)
