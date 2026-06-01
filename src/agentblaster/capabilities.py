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
    "tool_calling": "API-native tool/function-call envelope support",
    "trace_replay": "multi-turn message replay with assistant/tool turns",
    "skills": "large system-prompt skill prefix injection",
    "lcp_context": "deterministic local-context fixture injection",
    "responses_api": "OpenAI Responses-style stateful response input support",
    "prompt_caching": "provider-recognized prompt/cache-control metadata support",
}


def suite_requirements(suite: SuiteDefinition) -> list[CapabilityRequirement]:
    required: dict[str, set[str]] = {"chat": set()}
    for case in suite.cases:
        _require(required, "chat", case)
        if case.streaming:
            _require(required, "streaming", case)
        if case.response_format or case.expected_json_fields:
            _require(required, "structured_output", case)
        if case.cache_control:
            _require(required, "prompt_caching", case)
        if _case_uses_tools(case):
            _require(required, "tool_calling", case)
        if case.messages:
            _require(required, "trace_replay", case)
        if case.skills:
            _require(required, "skills", case)
        if case.lcp_profile:
            _require(required, "lcp_context", case)
        if case.previous_response_id or case.max_tool_calls:
            _require(required, "responses_api", case)

    return [
        CapabilityRequirement(
            key=key,
            description=CAPABILITY_DESCRIPTIONS[key],
            case_ids=sorted(case_ids),
        )
        for key, case_ids in sorted(required.items())
    ]


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
    if key == "prompt_caching":
        return provider.contract is ApiContract.ANTHROPIC or provider.capabilities.get("prompt_caching") is True
    if key == "trace_replay":
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


def _case_uses_tools(case: BenchmarkCase) -> bool:
    return bool(
        case.tools
        or case.tool_choice
        or case.expected_tool_name
        or case.simulated_tools
        or case.mcp_profile
        or any(_trace_message_has_tool_calls(message.model_dump(mode="json")) for message in case.messages)
    )


def _trace_message_has_tool_calls(message: dict[str, Any]) -> bool:
    tool_calls = message.get("tool_calls")
    return isinstance(tool_calls, list) and bool(tool_calls)
