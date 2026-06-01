from __future__ import annotations

import pytest

from agentblaster.errors import ConfigError
from agentblaster.mcp import execute_mcp_profile_tools, available_mcp_profiles, mcp_profile_tool_names, mcp_profile_tool_schemas
from agentblaster.models import ToolCallRecord


def test_fixture_mcp_profile_returns_deterministic_tool_schemas() -> None:
    tools = mcp_profile_tool_schemas("fixture-mcp")

    assert [tool["function"]["name"] for tool in tools] == [
        "mcp_fixture_read_resource",
        "mcp_fixture_call_tool",
        "mcp_fixture_list_prompts",
    ]
    assert tools[0]["function"]["parameters"]["additionalProperties"] is False


def test_wide_mcp_profile_returns_32_tools_for_prefill_stress() -> None:
    tools = mcp_profile_tool_schemas("wide-mcp-32")

    assert len(tools) == 32
    assert tools[0]["function"]["name"] == "mcp_wide_tool_01"
    assert tools[-1]["function"]["name"] == "mcp_wide_tool_32"


def test_unknown_mcp_profile_is_rejected() -> None:
    with pytest.raises(ConfigError, match="unknown MCP profile"):
        mcp_profile_tool_schemas("host-mcp")


def test_available_mcp_profiles_are_stable() -> None:
    assert available_mcp_profiles() == ["fixture-mcp", "wide-mcp-32"]


def test_mcp_profile_tool_names_are_stable() -> None:
    assert mcp_profile_tool_names("fixture-mcp") == [
        "mcp_fixture_read_resource",
        "mcp_fixture_call_tool",
        "mcp_fixture_list_prompts",
    ]


def test_execute_fixture_mcp_profile_tools_returns_deterministic_results() -> None:
    results = execute_mcp_profile_tools(
        [
            ToolCallRecord(name="mcp_fixture_read_resource", arguments={"uri": "fixture://mcp/resource/prd"}),
            ToolCallRecord(name="mcp_fixture_call_tool", arguments={"name": "echo", "payload": {"value": "ok"}}),
            ToolCallRecord(name="mcp_fixture_list_prompts", arguments={"namespace": "agentblaster"}),
        ],
        profile="fixture-mcp",
    )

    assert [result.ok for result in results] == [True, True, True]
    assert results[0].output["sentinel"] == "agentblaster-mcp-ok"
    assert results[1].output["result"] == "ok"
    assert results[2].output["prompts"][0]["sentinel"] == "agentblaster-mcp-ok"


def test_execute_wide_mcp_profile_tool_returns_prefill_fixture_result() -> None:
    results = execute_mcp_profile_tools(
        [ToolCallRecord(name="mcp_wide_tool_01", arguments={"query": "prefill", "limit": 1})],
        profile="wide-mcp-32",
    )

    assert results[0].ok is True
    assert results[0].output["result"] == "agentblaster-mcp-wide-ok"
