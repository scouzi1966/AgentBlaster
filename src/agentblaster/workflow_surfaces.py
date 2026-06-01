from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from agentblaster.errors import ConfigError
from agentblaster.lcp import lcp_profile_catalog
from agentblaster.mcp import available_mcp_profiles, mcp_profile_tool_schemas
from agentblaster.skills import available_skill_packs, skill_pack_text
from agentblaster.toolsim import SAFE_TOOL_SCHEMAS


@dataclass(frozen=True)
class WorkflowSurface:
    id: str
    family: str
    stability: str
    purpose: str
    host_execution: bool
    deterministic: bool
    contract_surfaces: tuple[str, ...]
    benchmark_dimensions: tuple[str, ...]
    safety_controls: tuple[str, ...]
    artifacts: tuple[str, ...] = ()


WORKFLOW_SURFACES: tuple[WorkflowSurface, ...] = (
    WorkflowSurface(
        id="openai-anthropic-tool-calling",
        family="tool-calling",
        stability="stable",
        purpose="Exercise model-native tool declaration, selection, argument JSON, and tool-result replay across OpenAI-compatible and Anthropic-compatible providers.",
        host_execution=False,
        deterministic=True,
        contract_surfaces=(
            "OpenAI Chat Completions tools/tool_choice",
            "OpenAI Responses tool calls",
            "Anthropic Messages tools",
        ),
        benchmark_dimensions=(
            "tool selection accuracy",
            "argument schema validity",
            "tool-loop depth",
            "tool envelope compatibility",
        ),
        safety_controls=(
            "Only deterministic fixture tools are exposed by default.",
            "Provider outputs are parsed before any simulated tool result is returned.",
            "Enterprise policy can allowlist tools and cap declared tool-loop depth.",
        ),
        artifacts=("SAFE_TOOL_SCHEMAS", "ToolCallRecord", "SimulatedToolResult"),
    ),
    WorkflowSurface(
        id="mcp-fixtures",
        family="mcp",
        stability="stable-fixture",
        purpose="Represent MCP-style tool, resource, and prompt surfaces without connecting to host MCP servers.",
        host_execution=False,
        deterministic=True,
        contract_surfaces=(
            "MCP fixture tool schemas serialized as provider tools",
            "MCP resource-read fixture",
            "MCP prompt-list fixture",
        ),
        benchmark_dimensions=(
            "wide tool catalog prefill pressure",
            "MCP schema normalization",
            "MCP-style resource/tool/prompt separation",
        ),
        safety_controls=(
            "Profiles are static and bundled with AgentBlaster.",
            "No external MCP process is launched by the benchmark harness.",
            "Policy can block MCP profiles or require explicit allowlists.",
        ),
        artifacts=("fixture-mcp", "wide-mcp-32"),
    ),
    WorkflowSurface(
        id="skill-packs",
        family="skills",
        stability="stable-fixture",
        purpose="Measure instruction-heavy local-agent workflows with deterministic skill preambles and large repeated prefixes.",
        host_execution=False,
        deterministic=True,
        contract_surfaces=(
            "Benchmark case skill_packs",
            "Static system prompt prefix expansion",
        ),
        benchmark_dimensions=(
            "large system prompt prefill",
            "instruction retention",
            "skill-conditioned tool use",
            "cache reuse under repeated prefixes",
        ),
        safety_controls=(
            "Skill text is bundled and inspectable.",
            "Skills cannot request host tool access outside benchmark-provided fixtures.",
            "Prompt footprint tools expose the added token/character pressure before dispatch.",
        ),
        artifacts=("repo-triage", "safe-tool-replay", "agent-planning", "large-prefix-diagnostic"),
    ),
    WorkflowSurface(
        id="lcp-emerging",
        family="lcp",
        stability="emerging-fixture",
        purpose="Exercise fixture-only local context protocol style workflows: scoped context bundles, session-local memory, and retrieval/context attachment metadata.",
        host_execution=False,
        deterministic=True,
        contract_surfaces=(
            "Context bundle manifest fixtures",
            "Scoped memory fixture metadata",
            "Retrieval/context attachment descriptors",
        ),
        benchmark_dimensions=(
            "context attachment fidelity",
            "session isolation",
            "repeated-context cache behavior",
            "redaction of context metadata",
        ),
        safety_controls=(
            "LCP coverage is fixture-only until real contracts stabilize.",
            "No filesystem, browser, network, or host memory is attached by default.",
            "Enterprise policies should require explicit opt-in before real local context providers are connected.",
        ),
        artifacts=("fixture-lcp", "wide-lcp-context", "lcp-context"),
    ),
    WorkflowSurface(
        id="harness-engineering",
        family="harness-engineering",
        stability="experimental",
        purpose="Support benchmark-method research such as contract fuzzing, metamorphic variants, cache replay, and concurrency/prefill stress profiles.",
        host_execution=False,
        deterministic=True,
        contract_surfaces=(
            "Generated benchmark suite provenance",
            "Harness profile metadata",
            "Static synthetic workload transformations",
        ),
        benchmark_dimensions=(
            "contract robustness",
            "semantic-preservation sensitivity",
            "prompt-cache reuse and invalidation",
            "concurrency fairness",
        ),
        safety_controls=(
            "Generated suites carry deterministic seed and source-suite provenance.",
            "Harness profiles do not call providers during generation.",
            "Calibration gates can reject unstable generated suites before publication.",
        ),
        artifacts=("prefill", "concurrency", "contract-fuzz", "metamorphic", "cache-replay"),
    ),
)


def workflow_surface_catalog() -> dict[str, Any]:
    surfaces = [_surface_payload(surface) for surface in WORKFLOW_SURFACES]
    return {
        "schema_version": "agentblaster.workflow-surface-catalog.v1",
        "boundary": "Workflow surfaces define AgentBlaster benchmark inputs and app validation scope; they are not provider capability claims.",
        "surfaces": surfaces,
        "summary": {
            "surface_count": len(surfaces),
            "families": sorted({surface["family"] for surface in surfaces}),
            "host_execution_required": any(surface["host_execution"] for surface in surfaces),
            "deterministic": all(surface["deterministic"] for surface in surfaces),
        },
    }


def list_workflow_surfaces() -> list[dict[str, Any]]:
    return list(workflow_surface_catalog()["surfaces"])


def get_workflow_surface(surface_id: str) -> dict[str, Any]:
    for surface in list_workflow_surfaces():
        if surface["id"] == surface_id:
            return surface
    available = ", ".join(surface["id"] for surface in list_workflow_surfaces())
    raise ConfigError(f"unknown workflow surface: {surface_id}; available surfaces: {available}")


def workflow_surface_catalog_json() -> str:
    return json.dumps(workflow_surface_catalog(), indent=2, sort_keys=True) + "\n"


def workflow_surface_catalog_markdown() -> str:
    catalog = workflow_surface_catalog()
    lines = [
        "# AgentBlaster Workflow Surface Catalog",
        "",
        f"Schema: `{catalog['schema_version']}`",
        "",
        catalog["boundary"],
        "",
        "## Surfaces",
        "",
    ]
    for surface in catalog["surfaces"]:
        lines.extend(
            [
                f"### `{surface['id']}`",
                "",
                f"- Family: `{surface['family']}`",
                f"- Stability: `{surface['stability']}`",
                f"- Deterministic: `{str(surface['deterministic']).lower()}`",
                f"- Host execution required: `{str(surface['host_execution']).lower()}`",
                f"- Purpose: {surface['purpose']}",
                "- Benchmark dimensions: " + ", ".join(surface["benchmark_dimensions"]),
                "- Safety controls: " + "; ".join(surface["safety_controls"]),
                "- Artifacts: " + ", ".join(surface["artifacts"]),
                "",
            ]
        )
    return "\n".join(lines)


def _surface_payload(surface: WorkflowSurface) -> dict[str, Any]:
    payload = asdict(surface)
    payload["contract_surfaces"] = list(surface.contract_surfaces)
    payload["benchmark_dimensions"] = list(surface.benchmark_dimensions)
    payload["safety_controls"] = list(surface.safety_controls)
    payload["artifacts"] = list(surface.artifacts)
    if surface.id == "openai-anthropic-tool-calling":
        payload["simulated_tools"] = _simulated_tool_summary()
    elif surface.id == "mcp-fixtures":
        payload["mcp_profiles"] = _mcp_profile_summary()
    elif surface.id == "skill-packs":
        payload["skill_packs"] = _skill_pack_summary()
    elif surface.id == "lcp-emerging":
        payload["lcp_profiles"] = lcp_profile_catalog()
    return payload


def _simulated_tool_summary() -> dict[str, Any]:
    return {
        "count": len(SAFE_TOOL_SCHEMAS),
        "names": sorted(SAFE_TOOL_SCHEMAS),
    }


def _mcp_profile_summary() -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    for profile in available_mcp_profiles():
        schemas = mcp_profile_tool_schemas(profile)
        profiles.append(
            {
                "name": profile,
                "tool_count": len(schemas),
                "tool_names": [_tool_name(schema) for schema in schemas],
            }
        )
    return profiles


def _skill_pack_summary() -> list[dict[str, Any]]:
    packs: list[dict[str, Any]] = []
    for name in available_skill_packs():
        text = skill_pack_text(name)
        packs.append(
            {
                "name": name,
                "line_count": len(text.splitlines()),
                "char_count": len(text),
            }
        )
    return packs


def _tool_name(schema: dict[str, Any]) -> str:
    function = schema.get("function")
    if isinstance(function, dict) and isinstance(function.get("name"), str):
        return function["name"]
    name = schema.get("name")
    return name if isinstance(name, str) else "unnamed"
