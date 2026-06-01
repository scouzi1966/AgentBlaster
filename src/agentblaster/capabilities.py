from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agentblaster.models import ApiContract, BenchmarkCase, ProviderConfig, SuiteDefinition


class CapabilityRequirement(BaseModel):
    key: str
    description: str
    case_ids: list[str] = Field(default_factory=list)


class CapabilityFinding(BaseModel):
    key: str
    status: str
    case_ids: list[str] = Field(default_factory=list)
    message: str


class SuiteCapabilityReport(BaseModel):
    provider: str
    suite: str
    compatible: bool
    strict_unknown: bool = False
    requirements: list[CapabilityRequirement] = Field(default_factory=list)
    missing: list[CapabilityFinding] = Field(default_factory=list)
    unknown: list[CapabilityFinding] = Field(default_factory=list)
    supported: list[CapabilityFinding] = Field(default_factory=list)


CAPABILITY_DESCRIPTIONS = {
    "chat": "basic chat completion request/response support",
    "streaming": "server-sent-event or equivalent streaming response support",
    "structured_output": "JSON/structured-output response-format support",
    "judge_rubric": "deterministic structured model-judge rubric verdict support",
    "tool_calling": "API-native tool/function-call envelope support",
    "tool_parser_repair": "strict parser behavior that rejects raw JSON, XML, markdown, or ReAct text as completed tool calls",
    "tool_loop": "bounded deterministic tool-result round trip support",
    "mcp_profile": "deterministic MCP fixture tool-catalog injection",
    "trace_replay": "multi-turn message replay with assistant/tool turns",
    "skills": "large system-prompt skill prefix injection",
    "lcp_context": "deterministic local-context fixture injection",
    "responses_api": "OpenAI Responses-style stateful response input support",
    "prompt_caching": "provider-recognized prompt/cache-control metadata support",
    "cancellation": "request cancellation, stream abort, or equivalent provider-side stop behavior",
}


def suite_requirements(suite: SuiteDefinition) -> list[CapabilityRequirement]:
    required: dict[str, set[str]] = {"chat": set()}
    for case in suite.cases:
        for key in case_required_capabilities(case):
            _require(required, key, case)

    return [
        CapabilityRequirement(
            key=key,
            description=CAPABILITY_DESCRIPTIONS[key],
            case_ids=sorted(case_ids),
        )
        for key, case_ids in sorted(required.items())
    ]


def case_required_capabilities(case: BenchmarkCase) -> list[str]:
    required: list[str] = ["chat"]
    if case.streaming:
        _append_requirement(required, "streaming")
    if case.cancel_after_ms is not None:
        _append_requirement(required, "cancellation")
    if case.response_format or case.expected_json_fields:
        _append_requirement(required, "structured_output")
    if _case_is_judge_rubric(case):
        _append_requirement(required, "judge_rubric")
    if case.cache_control:
        _append_requirement(required, "prompt_caching")
    if _case_uses_tools(case):
        _append_requirement(required, "tool_calling")
    if _case_requires_tool_parser_repair(case):
        _append_requirement(required, "tool_parser_repair")
    if case.max_tool_calls and case.max_tool_calls > 1:
        _append_requirement(required, "tool_loop")
    if case.mcp_profile:
        _append_requirement(required, "mcp_profile")
    if case.messages:
        _append_requirement(required, "trace_replay")
    if case.skills:
        _append_requirement(required, "skills")
    if case.lcp_profile:
        _append_requirement(required, "lcp_context")
    if case.previous_response_id:
        _append_requirement(required, "responses_api")
    return required


def case_capability_surfaces(case: BenchmarkCase) -> list[str]:
    return [key for key in case_required_capabilities(case) if key != "chat"]


def check_suite_compatibility(
    provider: ProviderConfig,
    suite: SuiteDefinition,
    *,
    strict_unknown: bool = False,
) -> SuiteCapabilityReport:
    requirements = suite_requirements(suite)
    missing: list[CapabilityFinding] = []
    unknown: list[CapabilityFinding] = []
    supported: list[CapabilityFinding] = []

    for requirement in requirements:
        support = provider_capability(provider, requirement.key)
        if support is True:
            supported.append(
                CapabilityFinding(
                    key=requirement.key,
                    status="supported",
                    case_ids=requirement.case_ids,
                    message=f"provider supports {requirement.key}",
                )
            )
        elif support is False:
            missing.append(
                CapabilityFinding(
                    key=requirement.key,
                    status="missing",
                    case_ids=requirement.case_ids,
                    message=f"provider does not support {requirement.key}",
                )
            )
        else:
            unknown.append(
                CapabilityFinding(
                    key=requirement.key,
                    status="unknown",
                    case_ids=requirement.case_ids,
                    message=f"provider capability is not declared: {requirement.key}",
                )
            )

    compatible = not missing and (not strict_unknown or not unknown)
    return SuiteCapabilityReport(
        provider=provider.name,
        suite=suite.name,
        compatible=compatible,
        strict_unknown=strict_unknown,
        requirements=requirements,
        missing=missing,
        unknown=unknown,
        supported=supported,
    )


def provider_capability(provider: ProviderConfig, key: str) -> bool | None:
    if key in provider.capabilities:
        return bool(provider.capabilities[key])

    if key == "chat":
        return True
    if key == "responses_api":
        return provider.contract is ApiContract.OPENAI_RESPONSES
    if key == "structured_output":
        if provider.contract is ApiContract.ANTHROPIC:
            return False
        return None
    if key == "judge_rubric":
        return provider_capability(provider, "structured_output")
    if key == "tool_calling":
        if provider.contract is ApiContract.ANTHROPIC:
            return True
        return None
    if key == "tool_parser_repair":
        tool_calling = provider_capability(provider, "tool_calling")
        if tool_calling is False:
            return False
        return None
    if key == "prompt_caching":
        if provider.contract is ApiContract.ANTHROPIC and provider.remote:
            return True
        if provider.contract is ApiContract.ANTHROPIC:
            return None
        return None
    if key == "trace_replay":
        if provider.contract in {ApiContract.OPENAI, ApiContract.OPENAI_RESPONSES, ApiContract.ANTHROPIC}:
            return True
        if provider.contract is ApiContract.NATIVE and provider.native_adapter == "ollama":
            return True
        if provider.contract is ApiContract.NATIVE and provider.native_adapter == "lm-studio":
            return False
        return None
    if key == "mcp_profile":
        return provider_capability(provider, "tool_calling")
    if key == "tool_loop":
        if provider.contract in {ApiContract.OPENAI, ApiContract.OPENAI_RESPONSES, ApiContract.ANTHROPIC}:
            return True
        if provider.contract is ApiContract.NATIVE and provider.native_adapter == "ollama":
            return True
        if provider.contract is ApiContract.NATIVE and provider.native_adapter == "lm-studio":
            return False
        return None
    if key == "skills":
        return True
    if key == "lcp_context":
        return True
    return None


def format_capability_report(report: SuiteCapabilityReport) -> str:
    lines = [
        f"provider: {report.provider}",
        f"suite: {report.suite}",
        f"compatible: {str(report.compatible).lower()}",
        f"strict_unknown: {str(report.strict_unknown).lower()}",
        "requirements:",
    ]
    if not report.requirements:
        lines.append("- none")
    for requirement in report.requirements:
        cases = ",".join(requirement.case_ids) if requirement.case_ids else "-"
        lines.append(f"- {requirement.key}\tcases={cases}\t{requirement.description}")

    for label, findings in [("missing", report.missing), ("unknown", report.unknown), ("supported", report.supported)]:
        lines.append(f"{label}:")
        if not findings:
            lines.append("- none")
            continue
        for finding in findings:
            cases = ",".join(finding.case_ids) if finding.case_ids else "-"
            lines.append(f"- {finding.key}\tcases={cases}\t{finding.message}")
    return "\n".join(lines)


def _require(required: dict[str, set[str]], key: str, case: BenchmarkCase) -> None:
    required.setdefault(key, set()).add(case.id)


def _append_requirement(required: list[str], key: str) -> None:
    if key not in required:
        required.append(key)


def _case_is_judge_rubric(case: BenchmarkCase) -> bool:
    tags = set(case.tags)
    metrics = set(case.metrics)
    return "judge-rubric" in tags or "model-judge" in tags or "judge_verdict_valid" in metrics


def _case_uses_tools(case: BenchmarkCase) -> bool:
    return bool(
        case.tools
        or case.tool_choice
        or case.expected_tool_name
        or case.simulated_tools
        or case.mcp_profile
        or any(_trace_message_has_tool_calls(message.model_dump(mode="json")) for message in case.messages)
    )


def _case_requires_tool_parser_repair(case: BenchmarkCase) -> bool:
    tags = set(case.tags)
    metrics = set(case.metrics)
    return "tool-parser-repair" in tags or "tool_parser_repair_required" in metrics


def _trace_message_has_tool_calls(message: dict[str, Any]) -> bool:
    tool_calls = message.get("tool_calls")
    return isinstance(tool_calls, list) and bool(tool_calls)
