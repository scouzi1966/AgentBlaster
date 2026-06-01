from __future__ import annotations

import json

import pytest

from agentblaster.dashboard import dashboard_artifact_path, dashboard_review_artifacts, dashboard_run_payload, list_dashboard_runs
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
    assert manifest["review_artifact_dirs"] == ["campaign-preflight", "release-bundles", "test-reports"]

    runs = list_dashboard_runs(tmp_path)
    run_ids = {run["run_id"] for run in runs}
    assert run_ids == {"run_dashboard_fixture_pass", "run_dashboard_fixture_fail"}
    assert all(run["provider"] == "mock-local-dashboard" for run in runs)
    assert all(run["provider_metadata"]["remote"] is False for run in runs)
    assert all(run["raw_trace_mode"] == "redacted" for run in runs)
    assert any(run["ok"] is False for run in runs)
    assert any(item["name"] == "report.html" for run in runs for item in run["artifacts"])
    assert any(item["name"] == "report.pdf" for run in runs for item in run["artifacts"])

    payload = dashboard_run_payload(tmp_path, "run_dashboard_fixture_pass")
    assert payload["manifest"]["suite"] == "dashboard-fixture"
    assert payload["summary"]["passed"] == 1
    assert payload["results"][0]["message"] == "agentblaster-fixture-ok"

    assert dashboard_artifact_path(tmp_path, "run_dashboard_fixture_pass", "report-card.svg").exists()
    assert dashboard_artifact_path(tmp_path, "run_dashboard_fixture_pass", "report-card.png").exists()
    assert dashboard_artifact_path(tmp_path, "run_dashboard_fixture_pass", "report.pdf").exists()
    review_artifacts = dashboard_review_artifacts(tmp_path)
    assert review_artifacts["project_root"] == "<redacted>"
    assert review_artifacts["project_root_redacted"] is True
    direct_selftest = {
        artifact["path"]: artifact
        for artifact in review_artifacts["artifacts"]
        if artifact["path"].startswith("test-reports/")
    }
    selftest_report = direct_selftest["test-reports/selftest/selftest-report.json"]
    assert selftest_report["schema"] == "agentblaster.selftest-report.v1"
    assert selftest_report["selftest_report_summaries"][0]["tier"] == "gui"
    assert "AGENTBLASTER_INTERNAL_VALUE" not in json.dumps(selftest_report["selftest_report_summaries"])
    campaign_preflight_artifacts = {
        artifact["path"]: artifact
        for artifact in review_artifacts["artifacts"]
        if artifact["path"].startswith("campaign-preflight/")
    }
    campaign_readiness_index = campaign_preflight_artifacts[
        "campaign-preflight/qwen-gemma-local/readiness/benchmark-readiness-index.json"
    ]
    campaign_manifest = campaign_preflight_artifacts["campaign-preflight/qwen-gemma-local/manifest.json"]
    assert campaign_manifest["schema"] == "agentblaster.campaign-preflight-bundle.v1"
    assert campaign_manifest["status"] == "review"
    assert campaign_manifest["campaign_preflight_summaries"][0]["review_summary_schema_version"] == "agentblaster.campaign-preflight-review-summary.v1"
    assert campaign_manifest["campaign_preflight_summaries"][0]["contains_local_paths"] is False
    assert campaign_manifest["campaign_preflight_summaries"][0]["external_publication_safe"] is True
    assert campaign_readiness_index["schema"] == "agentblaster.campaign-preflight-benchmark-readiness-index.v1"
    assert campaign_readiness_index["status"] == "pass"
    assert campaign_readiness_index["status_source"] == "benchmark-readiness-index.reports.ready"
    assert campaign_readiness_index["benchmark_readiness_summaries"][0]["provider"] == "afm"
    assert campaign_readiness_index["benchmark_readiness_summaries"][0]["suite"] == "trace-replay"
    assert campaign_readiness_index["benchmark_readiness_summaries"][0]["model"] == "mlx-community/Qwen3.6-27B"
    assert campaign_readiness_index["benchmark_readiness_summaries"][0]["ready"] is True
    assert campaign_readiness_index["benchmark_readiness_summaries"][0]["provider_auth_posture"] == [
        {
            "provider": "afm",
            "api_key_ref_kind": "keyring",
            "api_key_ref_configured": True,
            "api_key_ref_writable_backend": True,
            "api_key_ref_plaintext_fallback": False,
            "prewrite_policy_guard_recommended": False,
        }
    ]
    release_artifacts = {
        artifact["path"]: artifact
        for artifact in review_artifacts["artifacts"]
        if artifact["path"].startswith("release-bundles/")
    }
    release_bundle = release_artifacts["release-bundles/dashboard-fixture.agentblaster-release-qualification.zip"]
    assert release_bundle["schema"] == "agentblaster.release-qualification-bundle"
    assert release_bundle["matrix_gate_review_summaries"][0]["failure_class_summary"] == [
        {"failure_class": "model_quality", "count": 1}
    ]
    assert release_bundle["matrix_gate_review_summaries"][0]["tool_loop_stop_summary"] == [
        {"stop_reason": "final_response", "count": 2}
    ]
    assert release_bundle["matrix_gate_review_summaries"][0]["tool_loop_artifacts_missing"] == 0
    assert release_bundle["matrix_gate_review_summaries"][0]["invalid_tool_call_count"] == 1
    assert release_bundle["matrix_gate_review_summaries"][0]["tool_parser_repair_cases"] == 2
    assert release_bundle["matrix_gate_review_summaries"][0]["tool_parser_repairs_valid"] == 1
    assert release_bundle["matrix_gate_review_summaries"][0]["tool_parser_repair_valid_rate_percent"] == 50.0
    assert release_bundle["provider_contract_summaries"][0]["matrix"] == "dashboard-fixture"
    assert release_bundle["provider_contract_summaries"][0]["capability_evidence"]["proxy_checked_counts"] == {
        "judge_rubric": 1
    }
    assert release_bundle["provider_contract_summaries"][0]["capability_evidence"]["not_covered_counts"] == {
        "prompt_caching": 1
    }
    assert release_bundle["selftest_report_summaries"][0]["tier"] == "gui"
    assert release_bundle["selftest_report_summaries"][0]["junit_xml_present"] is True
    assert release_bundle["campaign_preflight_summaries"][0]["archive_path"] == (
        "readiness/campaign-preflight/dashboard-fixture-campaign-preflight-manifest.json"
    )
    assert release_bundle["campaign_preflight_summaries"][0]["contains_local_paths"] is False
    assert release_bundle["campaign_preflight_summaries"][0]["external_publication_safe"] is True
    assert release_bundle["harness_review_summaries"][0]["suite_name"] == "dashboard-fixture-orchestration"
    assert release_bundle["harness_review_summaries"][0]["generator_profile"] == "orchestration"
    assert release_bundle["harness_review_summaries"][0]["calibration_required_before_release_gate"] is True
    assert release_bundle["engine_advisory_summaries"][0]["engine"] == "afm"
    assert release_bundle["engine_advisory_summaries"][0]["top_priorities"][0]["area"] == "contract-conformance"
    assert {
        item["area"] for item in release_bundle["engine_advisory_summaries"][0]["top_priorities"]
    } >= {"agentic-protocol-repair"}
    assert release_bundle["evidence_index_summaries"][0]["name"] == "dashboard-fixture"
    assert release_bundle["evidence_index_summaries"][0]["status_counts"] == {
        "fail": 1,
        "pass": 2,
        "review": 1,
    }
    assert release_bundle["evidence_index_summaries"][0]["readiness"]["state"] == "blocked"
    assert release_bundle["evidence_index_summaries"][0]["cleanup_evidence"]["audit_log_required_count"] == 1
    assert release_bundle["suite_audit_summaries"][0]["suite"] == "dashboard-fixture"
    assert release_bundle["suite_audit_summaries"][0]["duplicate_fingerprint_count"] == 1
    assert release_bundle["metric_coverage_summaries"][0]["provider"] == "mock-local-dashboard"
    assert release_bundle["metric_coverage_summaries"][0]["review_required_groups"] == [
        "timing_and_throughput",
        "token_and_cache_accounting",
    ]
    combined_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in fixture.artifact_paths
        if path.is_file() and path.suffix not in {".zip", ".png", ".pdf"}
    )
    assert "sk-" not in combined_text
    assert "Authorization: Bearer" not in combined_text
    assert "Bearer [REDACTED]" in combined_text


def test_dashboard_fixture_rejects_unknown_profile_and_unknown_existing_entries(tmp_path) -> None:
    with pytest.raises(ValueError, match="unknown dashboard fixture profile"):
        write_dashboard_fixture(tmp_path, profile="unknown")

    (tmp_path / "unrelated.txt").write_text("keep me", encoding="utf-8")
    with pytest.raises(ValueError, match="non-fixture entries"):
        write_dashboard_fixture(tmp_path)
