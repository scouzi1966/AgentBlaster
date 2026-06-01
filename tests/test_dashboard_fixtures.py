from __future__ import annotations

import json

import pytest

from agentblaster.dashboard import dashboard_artifact_path, dashboard_run_payload, list_dashboard_runs
from agentblaster.fixtures import write_dashboard_fixture


def test_dashboard_fixture_writes_redacted_real_dashboard_artifacts(tmp_path) -> None:
    fixture = write_dashboard_fixture(tmp_path)

    assert fixture.profile == "deterministic-redacted"
    assert fixture.run_ids == ("run_dashboard_fixture_pass", "run_dashboard_fixture_fail")
    assert fixture.manifest_path.exists()
    manifest = json.loads(fixture.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "agentblaster.dashboard-fixture.v1"
    assert manifest["contains_real_secrets"] is False
    assert manifest["contains_remote_calls"] is False

    runs = list_dashboard_runs(tmp_path)
    run_ids = {run["run_id"] for run in runs}
    assert run_ids == {"run_dashboard_fixture_pass", "run_dashboard_fixture_fail"}
    assert all(run["provider"] == "mock-local-dashboard" for run in runs)
    assert all(run["provider_metadata"]["remote"] is False for run in runs)
    assert all(run["raw_trace_mode"] == "redacted" for run in runs)
    assert any(run["ok"] is False for run in runs)
    assert any(item["name"] == "report.html" for run in runs for item in run["artifacts"])

    payload = dashboard_run_payload(tmp_path, "run_dashboard_fixture_pass")
    assert payload["manifest"]["suite"] == "dashboard-fixture"
    assert payload["summary"]["passed"] == 1
    assert payload["results"][0]["message"] == "agentblaster-fixture-ok"

    assert dashboard_artifact_path(tmp_path, "run_dashboard_fixture_pass", "report-card.svg").exists()
    combined_text = "
".join(path.read_text(encoding="utf-8") for path in fixture.artifact_paths if path.is_file())
    assert "sk-" not in combined_text
    assert "Authorization: Bearer" not in combined_text
    assert "Bearer [REDACTED]" in combined_text


def test_dashboard_fixture_rejects_unknown_profile_and_unknown_existing_entries(tmp_path) -> None:
    with pytest.raises(ValueError, match="unknown dashboard fixture profile"):
        write_dashboard_fixture(tmp_path, profile="unknown")

    (tmp_path / "unrelated.txt").write_text("keep me", encoding="utf-8")
    with pytest.raises(ValueError, match="non-fixture entries"):
        write_dashboard_fixture(tmp_path)
