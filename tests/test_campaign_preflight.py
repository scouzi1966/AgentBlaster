from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from agentblaster.campaign_preflight import create_campaign_preflight_bundle
from agentblaster.cli import app


def _write_benchmark_readiness(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "agentblaster.benchmark-readiness.v1",
                "provider": "afm",
                "suite": "smoke",
                "model": "test-model",
                "ready": True,
                "strict_unknown": True,
                "summary": {
                    "policy_ok": True,
                    "suite_compatible": True,
                    "contract_checks_planned": 5,
                    "contract_capabilities_directly_checked": 3,
                    "contract_capabilities_proxy_checked": 1,
                    "contract_capabilities_not_covered": 0,
                    "metric_coverage_score": 0.75,
                    "provider_auth_writable_backends": 1,
                    "provider_auth_plaintext_fallbacks": 0,
                    "provider_auth_prewrite_policy_guards_recommended": 1,
                    "blocking_findings": 0,
                    "warnings": 1,
                },
                "provider_auth_posture": [
                    {
                        "provider": "afm",
                        "api_key_ref_kind": "keyring",
                        "api_key_ref_configured": True,
                        "api_key_ref_writable_backend": True,
                        "api_key_ref_plaintext_fallback": False,
                        "prewrite_policy_guard_recommended": True,
                    }
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def test_campaign_preflight_bundle_writes_no_dispatch_artifacts(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "home"))
    matrix = tmp_path / "matrix.yaml"
    readiness = tmp_path / "afm-smoke-readiness.json"
    _write_benchmark_readiness(readiness)
    matrix.write_text(
        "\n".join(
            [
                "name: demo-campaign",
                "runs:",
                "  - engine: afm",
                "    model: test-model",
                "    suite: smoke",
                "    concurrency: 2",
                "    no_raw_traces: true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    bundle = create_campaign_preflight_bundle(
        output_dir=tmp_path / "preflight",
        matrices=[matrix],
        project_root=Path("."),
        include_provider_audit=False,
        benchmark_readiness_reports=[readiness],
    )

    manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
    inventory = json.loads((bundle.output_dir / "matrices" / "001-demo-campaign-inventory.json").read_text(encoding="utf-8"))
    pressure = json.loads((bundle.output_dir / "pressure" / "001-demo-campaign-pressure.json").read_text(encoding="utf-8"))
    implementation_status = json.loads((bundle.output_dir / "readiness" / "implementation-status.json").read_text(encoding="utf-8"))
    readiness_index = json.loads((bundle.output_dir / "readiness" / "benchmark-readiness-index.json").read_text(encoding="utf-8"))

    assert manifest["schema_version"] == "agentblaster.campaign-preflight-bundle.v1"
    assert manifest["includes_benchmark_readiness"] is True
    assert manifest["benchmark_readiness"] == {
        "artifact_path": "readiness/benchmark-readiness-index.json",
        "report_count": 1,
    }
    assert manifest["matrix_count"] == 1
    assert manifest["matrices"][0]["pressure_artifact_path"] == "pressure/001-demo-campaign-pressure.json"
    assert manifest["security"]["contacts_providers"] is False
    assert manifest["security"]["resolves_secrets"] is False
    assert manifest["security"]["contains_raw_provider_payloads"] is False
    assert manifest["security"]["contains_local_paths"] is True
    assert manifest["security"]["external_publication_safe"] is False
    assert manifest["review_summary"]["schema_version"] == "agentblaster.campaign-preflight-review-summary.v1"
    assert manifest["review_summary"]["matrices"][0]["engine_targets"] == ["afm-mlx"]
    assert manifest["review_summary"]["security"]["contains_local_paths"] is False
    assert manifest["review_summary"]["security"]["external_publication_safe"] is True
    assert str(tmp_path) not in json.dumps(manifest["review_summary"])
    assert manifest["matrices"][0]["matrix_source_name"] == "matrix.yaml"
    assert manifest["matrices"][0]["engine_targets"] == ["afm-mlx"]
    assert manifest["matrices"][0]["matrix_path_contains_local_context"] is True
    assert implementation_status["project_root"] == "<redacted>"
    assert implementation_status["project_root_redacted"] is True
    assert str(tmp_path) not in json.dumps(implementation_status)
    assert inventory["matrix"] == "demo-campaign"
    assert inventory["engine_targets"] == ["afm-mlx"]
    assert pressure["schema_version"] == "agentblaster.matrix-pressure-audit.v1"
    assert pressure["matrix"] == "demo-campaign"
    assert readiness_index["schema_version"] == "agentblaster.campaign-preflight-benchmark-readiness-index.v1"
    assert readiness_index["reports"][0]["provider"] == "afm"
    assert readiness_index["reports"][0]["source_path"] == "afm-smoke-readiness.json"
    assert readiness_index["reports"][0]["source_path_redacted"] is True
    assert str(tmp_path) not in readiness_index["reports"][0]["source_path"]
    assert readiness_index["reports"][0]["provider_auth_writable_backends"] == 1
    assert readiness_index["reports"][0]["provider_auth_posture"][0]["api_key_ref_kind"] == "keyring"
    assert inventory["run_count"] == 1
    assert inventory["runs"][0]["engine"] == "afm"
    assert inventory["runs"][0]["engine_target"]["id"] == "afm-mlx"
    assert inventory["runs"][0]["engine_target"]["standardization"]["primary_scoring_contract"] == "openai"
    assert "harness-engineering" in inventory["runs"][0]["engine_target"]["standardization"]["workflow_surfaces"]
    assert inventory["runs"][0]["raw_trace_mode"] == "off"
    assert inventory["prompt_footprint"]["prefill_pressure_score"] >= inventory["estimated_prompt_tokens"]
    assert inventory["prompt_footprint"]["shared_static_reuse_tokens"] == 0
    assert inventory["runs"][0]["prompt_footprint"]["shared_static_reuse_tokens"] == 0
    assert inventory["runs"][0]["capability_requirement_keys"] == ["chat"]
    assert inventory["runs"][0]["capability_requirements"][0]["key"] == "chat"
    assert inventory["runs"][0]["case_capability_surfaces"][0]["surfaces"] == []
    assert inventory["runs"][0]["case_prompt_surfaces"][0]["dynamic_prompt_tokens"] >= 1
    assert inventory["runs"][0]["suite_audit"]["finding_count"] == 0
    assert inventory["runs"][0]["suite_audit"]["dataset_hygiene"]["duplicate_fingerprint_count"] == 0
    assert (bundle.output_dir / "readiness" / "environment-readiness.json").exists()
    assert (bundle.output_dir / "readiness" / "benchmark-readiness-index.json").exists()
    assert (bundle.output_dir / "catalogs" / "artifact-schemas.json").exists()
    assert not (bundle.output_dir / "providers" / "provider-audit.json").exists()


def test_campaign_preflight_inventory_summarizes_shared_prefix_reuse(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "home"))
    matrix = tmp_path / "matrix.yaml"
    readiness = tmp_path / "afm-smoke-readiness.json"
    _write_benchmark_readiness(readiness)
    matrix.write_text(
        "\n".join(
            [
                "name: prefill-campaign",
                "runs:",
                "  - engine: afm",
                "    model: test-model",
                "    suite: prefill",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    bundle = create_campaign_preflight_bundle(
        output_dir=tmp_path / "preflight",
        matrices=[matrix],
        project_root=Path("."),
        include_provider_audit=False,
    )

    inventory = json.loads((bundle.output_dir / "matrices" / "001-prefill-campaign-inventory.json").read_text(encoding="utf-8"))

    assert inventory["prompt_footprint"]["shared_static_prefix_groups"] >= 1
    assert inventory["prompt_footprint"]["shared_static_reuse_tokens"] > 0
    assert inventory["runs"][0]["prompt_footprint"]["shared_static_reuse_case_count"] >= 1
    assert any("system" in item["surfaces"] for item in inventory["runs"][0]["case_prompt_surfaces"])


def test_campaign_preflight_rewrites_stale_optional_artifacts(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "home"))
    matrix = tmp_path / "matrix.yaml"
    readiness = tmp_path / "afm-smoke-readiness.json"
    output_dir = tmp_path / "preflight"
    _write_benchmark_readiness(readiness)
    matrix.write_text(
        "\n".join(
            [
                "name: rewrite-demo",
                "runs:",
                "  - engine: afm",
                "    model: test-model",
                "    suite: smoke",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    create_campaign_preflight_bundle(
        output_dir=output_dir,
        matrices=[matrix],
        project_root=Path("."),
        include_provider_audit=False,
        benchmark_readiness_reports=[readiness],
    )
    (output_dir / "matrices" / "999-stale-inventory.json").write_text("stale\n", encoding="utf-8")
    (output_dir / "pressure" / "999-stale-pressure.json").write_text("stale\n", encoding="utf-8")
    second = create_campaign_preflight_bundle(
        output_dir=output_dir,
        matrices=[matrix],
        project_root=Path("."),
        include_provider_audit=False,
    )

    assert second.manifest["includes_benchmark_readiness"] is False
    assert not (output_dir / "readiness" / "benchmark-readiness-index.json").exists()
    assert not (output_dir / "providers" / "provider-audit.json").exists()
    assert not (output_dir / "matrices" / "999-stale-inventory.json").exists()
    assert not (output_dir / "pressure" / "999-stale-pressure.json").exists()


def test_cli_campaign_preflight_bundle_writes_manifest(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "home"))
    matrix = tmp_path / "matrix.yaml"
    readiness = tmp_path / "afm-smoke-readiness.json"
    readiness_list = tmp_path / "benchmark-readiness-inputs.txt"
    _write_benchmark_readiness(readiness)
    readiness_list.write_text(f"# generated readiness inputs\n{readiness.name}\n\n", encoding="utf-8")
    matrix.write_text(
        "\n".join(
            [
                "name: cli-demo",
                "runs:",
                "  - engine: afm",
                "    model: test-model",
                "    suite: smoke",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "preflight"
    audit_log = tmp_path / "audit.jsonl"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "evidence",
            "campaign-preflight",
            "--matrix",
            str(matrix),
            "--output-dir",
            str(output_dir),
            "--benchmark-readiness-list",
            str(readiness_list),
            "--no-provider-audit",
            "--audit-log",
            str(audit_log),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "AgentBlaster campaign preflight bundle" in result.output
    assert (output_dir / "manifest.json").exists()
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    audit_events = [json.loads(line) for line in audit_log.read_text(encoding="utf-8").splitlines()]
    assert manifest["schema_version"] == "agentblaster.campaign-preflight-bundle.v1"
    assert manifest["includes_benchmark_readiness"] is True
    assert manifest["benchmark_readiness"]["report_count"] == 1
    assert manifest["security"]["contacts_providers"] is False
    assert (output_dir / "readiness" / "benchmark-readiness-index.json").exists()
    assert [event["event"] for event in audit_events] == [
        "campaign_preflight_bundle_requested",
        "campaign_preflight_bundle_created",
    ]


def test_cli_campaign_preflight_rejects_malformed_readiness_list_entries(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "home"))
    matrix = tmp_path / "matrix.yaml"
    readiness_list = tmp_path / "benchmark-readiness-inputs.txt"
    matrix.write_text(
        "\n".join(
            [
                "name: cli-demo",
                "runs:",
                "  - engine: afm",
                "    model: test-model",
                "    suite: smoke",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    readiness_list.write_text("afm-smoke-readiness.json # inline note\n", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "evidence",
            "campaign-preflight",
            "--matrix",
            str(matrix),
            "--output-dir",
            str(tmp_path / "preflight"),
            "--benchmark-readiness-list",
            str(readiness_list),
        ],
    )

    assert result.exit_code != 0
    assert "inline comments are not supported" in result.output
