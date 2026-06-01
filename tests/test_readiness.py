from __future__ import annotations

import json

from typer.testing import CliRunner

from agentblaster.cli import app
from agentblaster.config import ProviderStore
from agentblaster.evidence_index import build_evidence_index
from agentblaster.models import ApiContract, BenchmarkCase, ProviderConfig, SecretRef, SuiteDefinition
from agentblaster.policy import load_policy
from agentblaster.readiness import build_readiness_dossier, format_readiness_report


def test_readiness_dossier_combines_policy_capability_contract_and_metrics() -> None:
    provider = ProviderConfig(
        name="local-openai",
        contract=ApiContract.OPENAI,
        base_url="http://127.0.0.1:8787/v1",
        api_key_ref=SecretRef(kind="keyring", name="agentblaster/local-openai"),
        capabilities={"streaming": True, "tool_calling": True, "structured_output": True},
    )
    suite = SuiteDefinition(
        name="agentic-smoke",
        description="agentic smoke",
        cases=[
            BenchmarkCase(
                id="case-one",
                title="case one",
                prompt="Return JSON",
                streaming=True,
                response_format={"type": "json_object"},
                expected_tool_name="ping_agentblaster",
            )
        ],
    )

    report = build_readiness_dossier(
        provider=provider,
        suite=suite,
        policy=load_policy(None),
        model="agentblaster-mock-qwen3.6-27b-dense",
        strict_unknown=True,
    )

    assert report["schema_version"] == "agentblaster.benchmark-readiness.v1"
    assert report["ready"] is True
    assert report["summary"]["policy_ok"] is True
    assert report["summary"]["suite_compatible"] is True
    assert report["summary"]["contract_checks_planned"] == 5
    assert report["summary"]["contract_capabilities_directly_checked"] >= 3
    assert report["summary"]["contract_capabilities_proxy_checked"] == 1
    assert report["contract_capability_evidence"]["proxy_checked"][0]["capability"] == "judge_rubric"
    assert report["metric_coverage"]["provider"]["name"] == "local-openai"
    assert report["summary"]["provider_auth_writable_backends"] == 1
    assert report["summary"]["provider_auth_plaintext_fallbacks"] == 0
    assert report["summary"]["provider_auth_prewrite_policy_guards_recommended"] == 1
    assert report["summary"]["provider_auth_keyring_required"] == 1
    assert isinstance(report["summary"]["keyring_dependency_available"], bool)
    assert report["secret_backend_posture"]["keyring_optional"] is True
    assert "keyring" in report["secret_backend_posture"]["recommended_enterprise_backends"]
    assert report["provider_auth_posture"] == [
        {
            "provider": "local-openai",
            "api_key_ref_kind": "keyring",
            "api_key_ref_configured": True,
            "api_key_ref_writable_backend": True,
            "api_key_ref_plaintext_fallback": False,
            "prewrite_policy_guard_recommended": True,
        }
    ]
    assert "ready: true" in format_readiness_report(report)
    assert "provider_auth_posture:" in format_readiness_report(report)
    assert "secret_backend_posture:" in format_readiness_report(report)
    assert "secret=keyring configured=true writable=true plaintext=false prewrite_policy_guard_recommended=true" in format_readiness_report(report)


def test_readiness_dossier_surfaces_plaintext_dotenv_auth_posture(tmp_path) -> None:
    provider = ProviderConfig(
        name="remote-openai",
        contract=ApiContract.OPENAI,
        base_url="https://api.example.com/v1",
        api_key_ref=SecretRef(kind="dotenv", name=f"OPENAI_API_KEY@{tmp_path / '.agentblaster.env'}"),
        remote=True,
    )
    suite = SuiteDefinition(
        name="basic",
        description="basic suite",
        cases=[BenchmarkCase(id="case-one", title="case one", prompt="Return ok")],
    )

    report = build_readiness_dossier(
        provider=provider,
        suite=suite,
        policy=load_policy(None),
        model="remote-model",
    )

    assert report["provider_auth_posture"][0]["api_key_ref_kind"] == "dotenv"
    assert report["provider_auth_posture"][0]["api_key_ref_writable_backend"] is True
    assert report["provider_auth_posture"][0]["api_key_ref_plaintext_fallback"] is True
    assert report["summary"]["provider_auth_plaintext_fallbacks"] == 1
    assert report["summary"]["provider_auth_keyring_required"] == 0
    assert "plaintext_dotenv_secret_backend" in {warning["code"] for warning in report["warnings"]}
    assert "secret=dotenv configured=true writable=true plaintext=true prewrite_policy_guard_recommended=true" in format_readiness_report(report)


def test_evidence_index_summarizes_benchmark_readiness_auth_posture(tmp_path) -> None:
    provider = ProviderConfig(
        name="local-openai",
        contract=ApiContract.OPENAI,
        base_url="http://127.0.0.1:8787/v1",
        api_key_ref=SecretRef(kind="keyring", name="agentblaster/local-openai"),
    )
    suite = SuiteDefinition(
        name="basic",
        description="basic suite",
        cases=[BenchmarkCase(id="case-one", title="case one", prompt="Return ok")],
    )
    report = build_readiness_dossier(
        provider=provider,
        suite=suite,
        policy=load_policy(None),
        model="local-model",
    )
    path = tmp_path / "benchmark-readiness.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    index = build_evidence_index(name="readiness-evidence", artifacts=[path])

    assert index["artifacts"][0]["schema"] == "agentblaster.benchmark-readiness.v1"
    assert index["artifacts"][0]["review_summary"]["provider_auth_writable_backends"] == 1
    assert index["artifacts"][0]["review_summary"]["provider_auth_posture"][0]["api_key_ref_kind"] == "keyring"
    assert isinstance(index["artifacts"][0]["review_summary"]["keyring_dependency_available"], bool)


def test_readiness_dossier_blocks_missing_model_and_strict_unknown_capabilities() -> None:
    provider = ProviderConfig(name="local-openai", contract=ApiContract.OPENAI, base_url="http://127.0.0.1:8787/v1")
    suite = SuiteDefinition(
        name="tool-suite",
        description="tool suite",
        cases=[BenchmarkCase(id="case-one", title="case one", prompt="Use tool", expected_tool_name="ping_agentblaster")],
    )

    report = build_readiness_dossier(provider=provider, suite=suite, policy=load_policy(None), strict_unknown=True)

    assert report["ready"] is False
    codes = {finding["code"] for finding in report["blocking_findings"]}
    assert "unknown_tool_calling" in codes
    assert "model_required" in codes


def test_cli_readiness_writes_json_and_exits_nonzero_when_blocked(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "config"))
    ProviderStore().upsert(
        ProviderConfig(name="local-openai", contract=ApiContract.OPENAI, base_url="http://127.0.0.1:8787/v1")
    )
    output_json = tmp_path / "readiness.json"
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["providers", "readiness", "--provider", "local-openai", "--suite", "smoke", "--output-json", str(output_json)],
    )

    assert result.exit_code == 1
    assert "model_required" in result.output
    assert output_json.exists()
