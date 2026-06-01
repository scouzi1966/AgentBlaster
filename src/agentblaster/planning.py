from __future__ import annotations

from pydantic import BaseModel, Field

from agentblaster.capabilities import SuiteCapabilityReport
from agentblaster.costs import estimate_costs
from agentblaster.models import ProviderConfig, RawTraceMode, SuiteDefinition
from agentblaster.policy import estimate_case_prompt_tokens


class PlannedCase(BaseModel):
    case_id: str
    title: str
    estimated_prompt_tokens: int
    max_output_tokens: int
    timeout_seconds: float
    streaming: bool
    tool_schemas: int
    simulated_tools: int
    mcp_profile: str | None = None
    skills: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    estimated_cost_usd: float | None = None


class RunPlan(BaseModel):
    dry_run: bool = True
    provider: str
    suite: str
    model: str
    contract: str
    remote: bool
    raw_trace_mode: str
    concurrency: int
    total_cases: int
    estimated_prompt_tokens: int
    max_output_tokens: int
    estimated_total_cost_usd: float | None = None
    capability_compatible: bool | None = None
    capability_missing: list[str] = Field(default_factory=list)
    capability_unknown: list[str] = Field(default_factory=list)
    cases: list[PlannedCase] = Field(default_factory=list)


def build_run_plan(
    *,
    provider: ProviderConfig,
    suite: SuiteDefinition,
    model: str,
    raw_trace_mode: RawTraceMode,
    concurrency: int,
    capability_report: SuiteCapabilityReport | None = None,
) -> RunPlan:
    planned_cases: list[PlannedCase] = []
    total_cost = 0.0
    saw_cost = False
    for case in suite.cases:
        prompt_tokens = estimate_case_prompt_tokens(case)
        case_cost = _estimate_case_cost(provider, input_tokens=prompt_tokens, output_tokens=case.max_tokens)
        if case_cost is not None:
            saw_cost = True
            total_cost += case_cost
        planned_cases.append(
            PlannedCase(
                case_id=case.id,
                title=case.title,
                estimated_prompt_tokens=prompt_tokens,
                max_output_tokens=case.max_tokens,
                timeout_seconds=case.timeout_seconds,
                streaming=case.streaming,
                tool_schemas=len(case.tools),
                simulated_tools=len(case.simulated_tools),
                mcp_profile=case.mcp_profile,
                skills=case.skills,
                tags=case.tags,
                estimated_cost_usd=case_cost,
            )
        )

    return RunPlan(
        provider=provider.name,
        suite=suite.name,
        model=model,
        contract=provider.contract.value,
        remote=provider.remote,
        raw_trace_mode=raw_trace_mode.value,
        concurrency=concurrency,
        total_cases=len(planned_cases),
        estimated_prompt_tokens=sum(case.estimated_prompt_tokens for case in planned_cases),
        max_output_tokens=sum(case.max_output_tokens for case in planned_cases),
        estimated_total_cost_usd=round(total_cost, 9) if saw_cost else None,
        capability_compatible=capability_report.compatible if capability_report else None,
        capability_missing=[finding.key for finding in capability_report.missing] if capability_report else [],
        capability_unknown=[finding.key for finding in capability_report.unknown] if capability_report else [],
        cases=planned_cases,
    )


def format_run_plan(plan: RunPlan) -> str:
    lines = [
        "dry_run: true",
        f"provider: {plan.provider}",
        f"suite: {plan.suite}",
        f"model: {plan.model}",
        f"contract: {plan.contract}",
        f"remote: {str(plan.remote).lower()}",
        f"raw_trace_mode: {plan.raw_trace_mode}",
        f"concurrency: {plan.concurrency}",
        f"total_cases: {plan.total_cases}",
        f"estimated_prompt_tokens: {plan.estimated_prompt_tokens}",
        f"max_output_tokens: {plan.max_output_tokens}",
        f"estimated_total_cost_usd: {_format_optional(plan.estimated_total_cost_usd)}",
        f"capability_compatible: {_format_optional_bool(plan.capability_compatible)}",
        f"capability_missing: {','.join(plan.capability_missing) if plan.capability_missing else 'none'}",
        f"capability_unknown: {','.join(plan.capability_unknown) if plan.capability_unknown else 'none'}",
        "cases:",
    ]
    for case in plan.cases:
        lines.append(
            f"- {case.case_id}\tprompt_tokens={case.estimated_prompt_tokens}\t"
            f"max_output={case.max_output_tokens}\tstreaming={str(case.streaming).lower()}\t"
            f"tools={case.tool_schemas}\tsimulated_tools={case.simulated_tools}\t"
            f"estimated_cost_usd={_format_optional(case.estimated_cost_usd)}"
        )
    return "\n".join(lines)


def _estimate_case_cost(provider: ProviderConfig, *, input_tokens: int, output_tokens: int) -> float | None:
    if not provider.cost_model:
        return None
    value = estimate_costs(provider.cost_model, input_tokens=input_tokens, output_tokens=output_tokens)["total_cost_usd"]
    return value if value is None else round(value, 9)


def _format_optional(value: float | int | str | None) -> str:
    return "unknown" if value is None else str(value)


def _format_optional_bool(value: bool | None) -> str:
    if value is None:
        return "unknown"
    return str(value).lower()
