from __future__ import annotations

from typing import Any

from agentblaster.errors import ConfigError
from agentblaster.models import SimulatedToolResult, ToolCallRecord


SAFE_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "search_docs": {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": "Search a deterministic in-memory documentation fixture.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    "read_file_fixture": {
        "type": "function",
        "function": {
            "name": "read_file_fixture",
            "description": "Read a deterministic fake repository file without touching the host filesystem.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Fixture path to read."},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    "shell_fixture": {
        "type": "function",
        "function": {
            "name": "shell_fixture",
            "description": "Run a deterministic fake shell command without executing on the host.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Fixture command to simulate."},
                },
                "required": ["command"],
                "additionalProperties": False,
            },
        },
    },
    "browser_fetch_fixture": {
        "type": "function",
        "function": {
            "name": "browser_fetch_fixture",
            "description": "Fetch a deterministic fake web page without network access.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Fixture URL to fetch."},
                },
                "required": ["url"],
                "additionalProperties": False,
            },
        },
    },
    "mcp_echo": {
        "type": "function",
        "function": {
            "name": "mcp_echo",
            "description": "Echo a deterministic MCP-style payload for harness validation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {"description": "Value to echo."},
                },
                "required": ["value"],
                "additionalProperties": True,
            },
        },
    },
}


DOC_FIXTURES = [
    {
        "title": "AgentBlaster PRD",
        "url": "fixture://docs/prd",
        "snippet": "AgentBlaster benchmarks local agentic inference engines with safe simulated tools.",
    },
    {
        "title": "Security Policy",
        "url": "fixture://docs/security",
        "snippet": "Raw API keys must never appear in traces, manifests, reports, exports, or dashboard output.",
    },
]


FILE_FIXTURES = {
    "/repo/README.md": "# Fixture Repo\n\nAgentBlaster fixture repository for safe benchmark replay.\n",
    "/repo/src/app.py": "def status():\n    return 'agentblaster-ok'\n",
}


SHELL_FIXTURES = {
    "pytest -q": {"exit_code": 0, "stdout": "3 passed\n", "stderr": ""},
    "python -m agentblaster --version": {"exit_code": 0, "stdout": "0.1.0\n", "stderr": ""},
}


BROWSER_FIXTURES = {
    "https://example.test/agentblaster": {
        "status_code": 200,
        "title": "AgentBlaster fixture page",
        "text": "AgentBlaster fixture page for browser-style benchmark workflows.",
    }
}


def simulated_tool_schemas(names: list[str]) -> list[dict[str, Any]]:
    return [simulated_tool_schema(name) for name in names]


def simulated_tool_schema(name: str) -> dict[str, Any]:
    try:
        return SAFE_TOOL_SCHEMAS[name]
    except KeyError as exc:
        available = ", ".join(sorted(SAFE_TOOL_SCHEMAS))
        raise ConfigError(f"unknown simulated tool: {name}; available tools: {available}") from exc


def execute_simulated_tools(
    calls: list[ToolCallRecord],
    *,
    allowed_tools: list[str],
) -> list[SimulatedToolResult]:
    allowed = set(allowed_tools)
    results: list[SimulatedToolResult] = []
    for call in calls:
        if call.name not in allowed:
            results.append(
                SimulatedToolResult(
                    tool_name=call.name,
                    ok=False,
                    error=f"tool is not allowed for this case: {call.name}",
                )
            )
            continue
        results.append(execute_simulated_tool(call))
    return results


def execute_simulated_tool(call: ToolCallRecord) -> SimulatedToolResult:
    if not call.valid:
        return SimulatedToolResult(tool_name=call.name, ok=False, error="provider emitted an invalid tool call")

    if call.name == "search_docs":
        query = str(call.arguments.get("query") or "")
        terms = {term.lower() for term in query.split() if term}
        results = [
            item
            for item in DOC_FIXTURES
            if not terms or terms.intersection((item["title"] + " " + item["snippet"]).lower().split())
        ]
        return SimulatedToolResult(tool_name=call.name, ok=True, output={"query": query, "results": results})

    if call.name == "read_file_fixture":
        path = str(call.arguments.get("path") or "")
        if path not in FILE_FIXTURES:
            return SimulatedToolResult(tool_name=call.name, ok=False, error=f"fixture path not found: {path}")
        return SimulatedToolResult(tool_name=call.name, ok=True, output={"path": path, "content": FILE_FIXTURES[path]})

    if call.name == "shell_fixture":
        command = str(call.arguments.get("command") or "")
        result = SHELL_FIXTURES.get(command)
        if result is None:
            return SimulatedToolResult(tool_name=call.name, ok=False, error=f"fixture command not allowed: {command}")
        return SimulatedToolResult(tool_name=call.name, ok=True, output={"command": command, **result})

    if call.name == "browser_fetch_fixture":
        url = str(call.arguments.get("url") or "")
        result = BROWSER_FIXTURES.get(url)
        if result is None:
            return SimulatedToolResult(tool_name=call.name, ok=False, error=f"fixture URL not found: {url}")
        return SimulatedToolResult(tool_name=call.name, ok=True, output={"url": url, **result})

    if call.name == "mcp_echo":
        return SimulatedToolResult(tool_name=call.name, ok=True, output={"value": call.arguments.get("value")})

    return SimulatedToolResult(tool_name=call.name, ok=False, error=f"unknown simulated tool: {call.name}")
