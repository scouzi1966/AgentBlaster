from __future__ import annotations

import pytest

from agentblaster.errors import ConfigError
from agentblaster.mcp import available_mcp_profiles, mcp_profile_tool_schemas


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
