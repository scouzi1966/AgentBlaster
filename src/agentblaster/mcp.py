from __future__ import annotations

from typing import Any

from agentblaster.errors import ConfigError
from agentblaster.models import SimulatedToolResult, ToolCallRecord


MCP_RESOURCE_FIXTURES: dict[str, dict[str, Any]] = {
    "fixture://mcp/resource/prd": {
        "uri": "fixture://mcp/resource/prd",
        "mime_type": "text/plain",
        "text": "AgentBlaster MCP fixture resource for local agentic benchmark planning.",
        "sentinel": "agentblaster-mcp-ok",
    },
    "fixture://mcp/resource/status": {
        "uri": "fixture://mcp/resource/status",
        "mime_type": "application/json",
        "json": {"status": "agentblaster-mcp-ok", "host_execution": False},
    },
    "fixture://docs/prd": {
        "uri": "fixture://docs/prd",
        "mime_type": "text/plain",
        "text": "AgentBlaster benchmarks local agentic inference engines with deterministic MCP fixtures.",
        "sentinel": "agentblaster-mcp-ok",
    },
}


def mcp_profile_tool_schemas(profile: str) -> list[dict[str, Any]]:
    """Return deterministic OpenAI-compatible tool schemas for an MCP fixture profile."""
    if profile == "fixture-mcp":
        return [
            _tool_schema(
                "mcp_fixture_read_resource",
                "Read a deterministic MCP resource fixture.",
                {"uri": {"type": "string", "description": "Fixture resource URI."}},
                ["uri"],
            ),
            _tool_schema(
                "mcp_fixture_call_tool",
                "Call a deterministic MCP tool fixture.",
                {"name": {"type": "string"}, "payload": {"type": "object"}},
                ["name", "payload"],
            ),
            _tool_schema(
                "mcp_fixture_list_prompts",
                "List deterministic MCP prompt fixtures.",
                {"namespace": {"type": "string"}},
                ["namespace"],
            ),
        ]

    if profile == "wide-mcp-32":
        return [
            _tool_schema(
                f"mcp_wide_tool_{index:02d}",
                (
                    "Synthetic MCP catalog entry used to stress repeated prompt/tool-schema "
                    f"prefill behavior. Deterministic fixture tool number {index:02d}."
                ),
                {
                    "query": {"type": "string", "description": "Synthetic query."},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                ["query"],
            )
            for index in range(1, 33)
        ]

    available = ", ".join(available_mcp_profiles())
    raise ConfigError(f"unknown MCP profile: {profile}; available profiles: {available}")


def available_mcp_profiles() -> list[str]:
    return ["fixture-mcp", "wide-mcp-32"]


def mcp_profile_tool_names(profile: str) -> list[str]:
    return [
        str(schema["function"]["name"])
        for schema in mcp_profile_tool_schemas(profile)
        if isinstance(schema.get("function"), dict) and schema["function"].get("name")
    ]


def execute_mcp_profile_tools(
    calls: list[ToolCallRecord],
    *,
    profile: str,
) -> list[SimulatedToolResult]:
    allowed = set(mcp_profile_tool_names(profile))
    results: list[SimulatedToolResult] = []
    for call in calls:
        if call.name not in allowed:
            results.append(
                SimulatedToolResult(
                    tool_name=call.name,
                    ok=False,
                    error=f"MCP tool is not allowed for profile {profile}: {call.name}",
                )
            )
            continue
        results.append(execute_mcp_profile_tool(call))
    return results


def execute_mcp_profile_tool(call: ToolCallRecord) -> SimulatedToolResult:
    if not call.valid:
        return SimulatedToolResult(tool_name=call.name, ok=False, error="provider emitted an invalid MCP tool call")

    if call.name == "mcp_fixture_read_resource":
        uri = str(call.arguments.get("uri") or "")
        resource = MCP_RESOURCE_FIXTURES.get(uri)
        if resource is None:
            return SimulatedToolResult(tool_name=call.name, ok=False, error=f"MCP fixture resource not found: {uri}")
        return SimulatedToolResult(tool_name=call.name, ok=True, output=resource)

    if call.name == "mcp_fixture_call_tool":
        name = str(call.arguments.get("name") or "")
        payload = call.arguments.get("payload")
        normalized_payload = payload if isinstance(payload, dict) else {}
        if name in {"echo", "mcp_echo", "status"}:
            return SimulatedToolResult(
                tool_name=call.name,
                ok=True,
                output={
                    "name": name,
                    "payload": normalized_payload,
                    "result": normalized_payload.get("value", "agentblaster-mcp-ok"),
                    "host_execution": False,
                },
            )
        return SimulatedToolResult(tool_name=call.name, ok=False, error=f"MCP fixture tool not found: {name}")

    if call.name == "mcp_fixture_list_prompts":
        namespace = str(call.arguments.get("namespace") or "default")
        return SimulatedToolResult(
            tool_name=call.name,
            ok=True,
            output={
                "namespace": namespace,
                "prompts": [
                    {
                        "name": "agentblaster_status",
                        "description": "Return the deterministic MCP fixture sentinel.",
                        "sentinel": "agentblaster-mcp-ok",
                    }
                ],
                "host_execution": False,
            },
        )

    if call.name.startswith("mcp_wide_tool_"):
        return SimulatedToolResult(
            tool_name=call.name,
            ok=True,
            output={
                "query": str(call.arguments.get("query") or ""),
                "limit": call.arguments.get("limit", 1),
                "result": "agentblaster-mcp-wide-ok",
                "host_execution": False,
            },
        )

    return SimulatedToolResult(tool_name=call.name, ok=False, error=f"unknown MCP fixture tool: {call.name}")


def _tool_schema(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str],
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }
