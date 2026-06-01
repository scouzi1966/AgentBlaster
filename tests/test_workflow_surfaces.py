from __future__ import annotations

import json

import pytest

from agentblaster.errors import ConfigError
from agentblaster.workflow_surfaces import (
    get_workflow_surface,
    workflow_surface_catalog,
    workflow_surface_catalog_json,
    workflow_surface_catalog_markdown,
)


def test_workflow_surface_catalog_covers_agentic_protocol_families() -> None:
    catalog = workflow_surface_catalog()
    surfaces = {surface["id"]: surface for surface in catalog["surfaces"]}

    assert catalog["schema_version"] == "agentblaster.workflow-surface-catalog.v1"
    assert {
        "openai-anthropic-tool-calling",
        "mcp-fixtures",
        "skill-packs",
        "lcp-emerging",
        "harness-engineering",
    } <= set(surfaces)
    assert catalog["summary"]["host_execution_required"] is False
    assert catalog["summary"]["deterministic"] is True
    assert surfaces["openai-anthropic-tool-calling"]["simulated_tools"]["count"] >= 5
    assert any(profile["name"] == "wide-mcp-32" for profile in surfaces["mcp-fixtures"]["mcp_profiles"])
    assert any(pack["name"] == "large-prefix-diagnostic" for pack in surfaces["skill-packs"]["skill_packs"])
    assert surfaces["lcp-emerging"]["stability"] == "emerging"
    assert "cache replay" in " ".join(surfaces["harness-engineering"]["benchmark_dimensions"])


def test_workflow_surface_lookup_json_and_markdown_are_stable() -> None:
    surface = get_workflow_surface("lcp-emerging")
    payload = json.loads(workflow_surface_catalog_json())
    markdown = workflow_surface_catalog_markdown()

    assert surface["family"] == "lcp"
    assert payload["summary"]["surface_count"] >= 5
    assert "# AgentBlaster Workflow Surface Catalog" in markdown
    assert "`lcp-emerging`" in markdown


def test_workflow_surface_lookup_rejects_unknown_ids() -> None:
    with pytest.raises(ConfigError, match="unknown workflow surface"):
        get_workflow_surface("unknown")
