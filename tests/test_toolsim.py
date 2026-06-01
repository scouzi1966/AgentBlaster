from __future__ import annotations

import pytest

from agentblaster.errors import ConfigError
from agentblaster.models import ToolCallRecord
from agentblaster.toolsim import execute_simulated_tool, execute_simulated_tools, simulated_tool_schema


def test_simulated_tool_schema_returns_openai_function_tool() -> None:
    schema = simulated_tool_schema("search_docs")

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "search_docs"
    assert schema["function"]["parameters"]["required"] == ["query"]


def test_simulated_tool_schema_rejects_unknown_tool() -> None:
    with pytest.raises(ConfigError, match="unknown simulated tool"):
        simulated_tool_schema("host_shell")


def test_execute_search_docs_fixture_is_deterministic() -> None:
    result = execute_simulated_tool(ToolCallRecord(name="search_docs", arguments={"query": "AgentBlaster PRD"}))

    assert result.ok is True
    assert result.output["results"][0]["title"] == "AgentBlaster PRD"
    assert "safe simulated tools" in result.output["results"][0]["snippet"]


def test_execute_simulated_tools_blocks_unallowed_tool() -> None:
    results = execute_simulated_tools(
        [ToolCallRecord(name="shell_fixture", arguments={"command": "pytest -q"})],
        allowed_tools=["search_docs"],
    )

    assert results[0].ok is False
    assert "not allowed" in str(results[0].error)


def test_shell_fixture_never_executes_host_commands() -> None:
    allowed = execute_simulated_tool(ToolCallRecord(name="shell_fixture", arguments={"command": "pytest -q"}))
    denied = execute_simulated_tool(ToolCallRecord(name="shell_fixture", arguments={"command": "rm -rf /"}))

    assert allowed.ok is True
    assert allowed.output["stdout"] == "3 passed\n"
    assert denied.ok is False
    assert "not allowed" in str(denied.error)
