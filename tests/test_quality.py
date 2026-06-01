from __future__ import annotations

import json

from agentblaster.quality import (
    get_test_tier,
    list_chrome_gui_test_flows,
    list_sdlc_gates,
    list_chrome_validation_steps,
    list_test_tiers,
    render_chrome_gui_plan_json,
    render_chrome_gui_plan_markdown,
    render_chrome_validation_markdown,
    render_gui_test_spec_json,
    render_gui_test_spec_markdown,
    render_sdlc_gate_catalog_json,
    render_sdlc_gate_catalog_markdown,
    write_gui_test_artifacts,
)


def test_quality_tiers_define_sdlc_lanes() -> None:
    tiers = {tier.name: tier for tier in list_test_tiers()}

    assert {"fast", "normal", "security", "gui", "remote", "slow", "packaging", "release"} <= set(tiers)
    assert tiers["normal"].ci_default is True
    assert "not remote" in tiers["normal"].marker_expression
    assert tiers["gui"].ci_default is False
    assert "gui" in tiers["gui"].marker_expression




def test_sdlc_gate_catalog_maps_quality_commands_to_release_evidence() -> None:
    gates = {gate.id: gate for gate in list_sdlc_gates()}
    catalog = json.loads(render_sdlc_gate_catalog_json())
    markdown = render_sdlc_gate_catalog_markdown()

    assert catalog["schema_version"] == "agentblaster.sdlc-gates.v1"
    assert catalog["boundary"] == "These gates validate AgentBlaster itself, not benchmarked inference engines or model quality."
    assert {"local-fast", "premerge-normal", "security-required", "packaging-release", "release-qualification", "redaction-scan"} <= set(gates)
    assert gates["security-required"].required is True
    assert gates["security-required"].blocking is True
    assert gates["remote-provider-optional"].required is False
    assert any(gate["command"].startswith("agentblaster selftest") for gate in catalog["gates"])
    assert any(gate["id"] == "chrome-codex-review" for gate in catalog["gates"])
    assert "# AgentBlaster SDLC Gate Catalog" in markdown
    assert "release-qualification" in markdown

def test_quality_tier_lookup_rejects_unknown_tier() -> None:
    try:
        get_test_tier("unknown")
    except ValueError as exc:
        assert "available tiers" in str(exc)
    else:
        raise AssertionError("expected unknown tier to raise ValueError")


def test_chrome_gui_plan_is_structured_redaction_safe_and_chrome_oriented() -> None:
    flows = list_chrome_gui_test_flows()
    plan = json.loads(render_chrome_gui_plan_json(dashboard_url="http://127.0.0.1:9999", fixture_profile="fixture-a"))
    markdown = render_chrome_gui_plan_markdown(dashboard_url="http://127.0.0.1:9999", fixture_profile="fixture-a")

    assert plan["schema_version"] == "agentblaster.chrome-gui-plan.v1"
    assert plan["dashboard_url"] == "http://127.0.0.1:9999"
    assert plan["fixture_profile"] == "fixture-a"
    assert "Codex Chrome plugin" in plan["tooling"]
    assert any("real API keys" in item for item in plan["safety"])
    assert {flow.id for flow in flows} >= {"dashboard-smoke-redaction", "provider-and-launch-flow", "report-artifact-review"}
    assert any('data-testid="runs-table"' in flow["selectors"] for flow in plan["flows"])
    assert "# AgentBlaster Chrome GUI Self-Test Plan" in markdown
    assert "Dashboard URL: `http://127.0.0.1:9999`" in markdown


def test_chrome_validation_checklist_covers_dashboard_security_and_evidence() -> None:
    steps = list_chrome_validation_steps()
    markdown = render_chrome_validation_markdown()

    assert any(step.id == "chrome-redaction-check" for step in steps)
    assert any(step.id == "chrome-api-surfaces" for step in steps)
    assert "Codex Chrome plugin" in markdown
    assert "Every finding should be converted into a deterministic Playwright or pytest fixture" in markdown


def test_gui_test_spec_unifies_playwright_chrome_and_release_evidence() -> None:
    spec = json.loads(
        render_gui_test_spec_json(
            dashboard_url="http://127.0.0.1:8765",
            fixture_dir="fixtures/gui",
            evidence_dir="evidence/gui",
            browser="chrome",
        )
    )
    markdown = render_gui_test_spec_markdown(
        dashboard_url="http://127.0.0.1:8765",
        fixture_dir="fixtures/gui",
        evidence_dir="evidence/gui",
        browser="chrome",
    )

    assert spec["schema_version"] == "agentblaster.gui-test-spec.v1"
    assert spec["boundary"] == "These checks validate AgentBlaster, not benchmarked inference engines."
    assert "pytest -q tests/gui -m gui" in spec["ci"]["pytest_command"]
    assert spec["chrome_codex"]["tool"] == "Codex Chrome plugin"
    assert spec["chrome_codex"]["plan"]["schema_version"] == "agentblaster.chrome-gui-plan.v1"
    assert "sk-" in spec["security_canaries"]
    assert "# AgentBlaster GUI Self-Test Specification" in markdown
    assert "Chrome/Codex Evidence Lane" in markdown


def test_gui_test_artifact_writer_creates_release_evidence_files(tmp_path) -> None:
    paths = write_gui_test_artifacts(
        tmp_path,
        dashboard_url="http://127.0.0.1:8765",
        fixture_dir="fixtures/gui",
        evidence_dir="evidence/gui",
        browser="chrome",
        overwrite=True,
    )

    names = {path.name for path in paths}
    assert names == {
        "gui-test-spec.json",
        "gui-test-spec.md",
        "chrome-dashboard-plan.json",
        "chrome-dashboard-checklist.md",
    }
    assert json.loads((tmp_path / "gui-test-spec.json").read_text())["schema_version"] == "agentblaster.gui-test-spec.v1"
    assert "Codex Chrome plugin" in (tmp_path / "chrome-dashboard-checklist.md").read_text()
