from __future__ import annotations

from typer.testing import CliRunner

from agentblaster.agent_profiles import generate_agent_suite, list_agent_profiles, suite_to_yaml
from agentblaster.cli import app


def test_agent_profiles_include_named_local_agent_patterns() -> None:
    profiles = {profile.id: profile for profile in list_agent_profiles()}

    assert {"opencode", "openclaw", "hermes", "pi", "aider", "cline", "continue", "codex"} <= set(profiles)
    assert "repo tools" in profiles["opencode"].representative_features
    assert "parser strictness" in profiles["openclaw"].representative_features
    assert "MCP" in profiles["hermes"].representative_features
    assert "LCP" in profiles["hermes"].representative_features
    assert "diff reasoning" in profiles["aider"].representative_features
    assert "plan-act loop" in profiles["cline"].representative_features
    assert "IDE retrieval" in profiles["continue"].representative_features
    assert "sandbox policy" in profiles["codex"].representative_features


def test_generate_all_agent_profile_suite_uses_existing_harness_surfaces() -> None:
    suite = generate_agent_suite("all", include_all=True)
    case_ids = {case.id for case in suite.cases}

    assert suite.name == "agentic-local-profiles"
    assert suite.provenance.origin == "synthetic_representative"
    assert "opencode-read-plan" in case_ids
    assert "openclaw-required-tool-envelope" in case_ids
    assert "hermes-mcp-planner-tool" in case_ids
    assert "hermes-lcp-context-boundary" in case_ids
    assert "pi-lean-local-chat" in case_ids
    assert "aider-diff-test-replay" in case_ids
    assert "cline-plan-act-read" in case_ids
    assert "continue-doc-retrieval-summary" in case_ids
    assert "codex-sandbox-command-plan" in case_ids
    assert any(case.simulated_tools for case in suite.cases)
    assert any(case.mcp_profile == "fixture-mcp" for case in suite.cases)
    assert any(case.lcp_profile == "fixture-lcp" for case in suite.cases)
    assert any(case.skills for case in suite.cases)
    assert any(case.response_format for case in suite.cases)


def test_agent_profile_suite_serializes_to_yaml() -> None:
    suite = generate_agent_suite("opencode")
    text = suite_to_yaml(suite)

    assert "name: agentic-opencode" in text
    assert "read_file_fixture" in text
    assert "repo-triage" in text


def test_cli_agents_profiles_and_suite_generation(tmp_path) -> None:
    runner = CliRunner()
    output = tmp_path / "agentic.yaml"

    profiles = runner.invoke(app, ["agents", "profiles"])
    generated = runner.invoke(app, ["agents", "suite", "--profile", "all", "--output", str(output)])

    assert profiles.exit_code == 0, profiles.output
    assert "opencode" in profiles.output
    assert "openclaw" in profiles.output
    assert "hermes" in profiles.output
    assert "pi" in profiles.output
    assert "aider" in profiles.output
    assert "cline" in profiles.output
    assert "continue" in profiles.output
    assert "codex" in profiles.output
    assert generated.exit_code == 0, generated.output
    assert output.exists()
    assert "agentic-local-profiles" in output.read_text(encoding="utf-8")
