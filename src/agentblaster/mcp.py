from __future__ import annotations

from typing import Any

from agentblaster.errors import ConfigError


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
