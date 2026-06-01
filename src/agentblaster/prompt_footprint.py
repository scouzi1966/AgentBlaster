from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from agentblaster.mcp import mcp_profile_tool_schemas
from agentblaster.models import BenchmarkCase, SuiteDefinition
from agentblaster.skills import skill_prefix
from agentblaster.toolsim import simulated_tool_schemas

FOOTPRINT_SCHEMA_VERSION = "agentblaster.prompt-footprint.v1"
COMPONENTS = (
    "system_prompt",
    "cache_control",
    "prompt",
    "messages",
    "tools",
    "simulated_tools",
    "mcp_profile",
    "skills",
)


def suite_prompt_footprint(suite: SuiteDefinition) -> dict[str, Any]:
    cases = [_case_footprint(case) for case in suite.cases]
    component_totals: dict[str, int] = {component: 0 for component in COMPONENTS}
    for case in cases:
        for component, value in case["component_tokens"].items():
            component_totals[component] = component_totals.get(component, 0) + int(value)
    shared_static_prefixes = _shared_static_prefixes(cases)
    max_case_tokens = max((case["estimated_prompt_tokens"] for case in cases), default=0)
    total_tokens = sum(case["estimated_prompt_tokens"] for case in cases)
    return {
        "schema_version": FOOTPRINT_SCHEMA_VERSION,
        "suite": suite.name,
        "description": suite.description,
        "case_count": len(suite.cases),
        "total_estimated_prompt_tokens": total_tokens,
        "max_case_estimated_prompt_tokens": max_case_tokens,
        "component_totals": component_totals,
        "prefill_pressure": _prefill_pressure(total_tokens, max_case_tokens, shared_static_prefixes),
        "shared_static_prefixes": shared_static_prefixes,
        "cases": cases,
        "notes": [
            "Token estimates use a deterministic character-count heuristic and are intended for planning, not billing.",
            "Static prefix tokens include system prompts, tool schemas, simulated tool schemas, MCP catalogs, and skill text.",
            "Repeated shared static prefixes are relevant to provider prompt cache and prefill behavior.",
        ],
    }


def write_prompt_footprint_json(report: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def format_prompt_footprint_report(report: dict[str, Any]) -> str:
    lines = [
        "AgentBlaster prompt footprint",
        f"suite: {report['suite']}",
        f"case_count: {report['case_count']}",
        f"total_estimated_prompt_tokens: {report['total_estimated_prompt_tokens']}",
        f"max_case_estimated_prompt_tokens: {report['max_case_estimated_prompt_tokens']}",
        f"prefill_pressure: {report['prefill_pressure']['level']} ({report['prefill_pressure']['score']})",
        "component_totals:",
    ]
    for component, value in report["component_totals"].items():
        lines.append(f"- {component}: {value}")
    lines.append("shared_static_prefixes:")
    if not report["shared_static_prefixes"]:
        lines.append("- none")
    else:
        for item in report["shared_static_prefixes"]:
            lines.append(
                f"- {item['fingerprint']} cases={item['case_count']} static_tokens={item['static_tokens']} ids={','.join(item['case_ids'])}"
            )
    lines.append("largest_cases:")
    for case in sorted(report["cases"], key=lambda item: item["estimated_prompt_tokens"], reverse=True)[:10]:
        lines.append(
            f"- {case['case_id']}: total={case['estimated_prompt_tokens']} static={case['static_prefix_tokens']} dynamic={case['dynamic_prompt_tokens']} surfaces={','.join(case['surfaces']) or '-'}"
        )
    return "\n".join(lines) + "\n"


def _case_footprint(case: BenchmarkCase) -> dict[str, Any]:
    components = _case_components(case)
    component_tokens = {name: _estimate_tokens(value) for name, value in components.items()}
    static_tokens = sum(
        component_tokens[name]
        for name in ("system_prompt", "cache_control", "tools", "simulated_tools", "mcp_profile", "skills")
    )
    dynamic_tokens = component_tokens["prompt"] + component_tokens["messages"]
    total_tokens = max(1, static_tokens + dynamic_tokens)
    static_payload = "\n".join(
        components[name]
        for name in ("system_prompt", "cache_control", "tools", "simulated_tools", "mcp_profile", "skills")
        if components[name]
    )
    return {
        "case_id": case.id,
        "title": case.title,
        "scenario": case.scenario,
        "estimated_prompt_tokens": total_tokens,
        "static_prefix_tokens": static_tokens,
        "dynamic_prompt_tokens": dynamic_tokens,
        "component_tokens": component_tokens,
        "static_prefix_fingerprint": _fingerprint(static_payload) if static_payload else None,
        "surfaces": _surfaces(case),
        "max_tokens": case.max_tokens,
        "timeout_seconds": case.timeout_seconds,
        "tags": list(case.tags),
    }


def _case_components(case: BenchmarkCase) -> dict[str, str]:
    explicit_tools = json.dumps(case.tools, sort_keys=True, separators=(",", ":")) if case.tools else ""
    sim_tools = json.dumps(simulated_tool_schemas(case.simulated_tools), sort_keys=True, separators=(",", ":")) if case.simulated_tools else ""
    mcp_tools = json.dumps(mcp_profile_tool_schemas(case.mcp_profile), sort_keys=True, separators=(",", ":")) if case.mcp_profile else ""
    messages = (
        json.dumps(
            [message.model_dump(mode="json", exclude_none=True) for message in case.messages],
            sort_keys=True,
            separators=(",", ":"),
        )
        if case.messages
        else ""
    )
    return {
        "system_prompt": case.system_prompt or "",
        "cache_control": json.dumps(case.cache_control, sort_keys=True, separators=(",", ":")) if case.cache_control else "",
        "prompt": case.prompt or "",
        "messages": messages,
        "tools": explicit_tools,
        "simulated_tools": sim_tools,
        "mcp_profile": mcp_tools,
        "skills": skill_prefix(case.skills) if case.skills else "",
    }


def _surfaces(case: BenchmarkCase) -> list[str]:
    surfaces: list[str] = []
    if case.system_prompt:
        surfaces.append("system")
    if case.cache_control:
        surfaces.append("cache-control")
    if case.messages:
        surfaces.append("trace")
    if case.tools:
        surfaces.append("tools")
    if case.simulated_tools:
        surfaces.append("simulated-tools")
    if case.mcp_profile:
        surfaces.append("mcp")
    if case.skills:
        surfaces.append("skills")
    if case.response_format:
        surfaces.append("structured")
    if case.streaming:
        surfaces.append("streaming")
    return surfaces


def _shared_static_prefixes(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        fingerprint = case.get("static_prefix_fingerprint")
        if fingerprint:
            groups.setdefault(str(fingerprint), []).append(case)
    shared: list[dict[str, Any]] = []
    for fingerprint, grouped in sorted(groups.items()):
        if len(grouped) < 2:
            continue
        shared.append(
            {
                "fingerprint": fingerprint,
                "case_count": len(grouped),
                "case_ids": [case["case_id"] for case in grouped],
                "static_tokens": grouped[0]["static_prefix_tokens"],
            }
        )
    return shared


def _prefill_pressure(total_tokens: int, max_case_tokens: int, shared_static_prefixes: list[dict[str, Any]]) -> dict[str, Any]:
    shared_bonus = sum(item["case_count"] * item["static_tokens"] for item in shared_static_prefixes)
    score = total_tokens + max_case_tokens + shared_bonus
    if score >= 20000:
        level = "extreme"
    elif score >= 8000:
        level = "high"
    elif score >= 2500:
        level = "moderate"
    else:
        level = "low"
    return {"score": score, "level": level, "shared_static_bonus": shared_bonus}


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
