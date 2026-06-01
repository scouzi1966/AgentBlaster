from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agentblaster.models import BenchmarkCase, SuiteDefinition


EXTERNAL_PROVENANCE = {"primary_source", "public_benchmark_adapted"}


class SuiteAuditFinding(BaseModel):
    """Static suite governance finding for review before benchmark execution."""

    model_config = ConfigDict(extra="forbid")

    severity: str
    case_id: str | None = None
    code: str
    message: str


class SuiteAuditReport(BaseModel):
    """Static suite governance summary."""

    model_config = ConfigDict(extra="forbid")

    suite: str
    description: str = ""
    total_cases: int = Field(ge=0)
    provenance_counts: dict[str, int] = Field(default_factory=dict)
    risk_counts: dict[str, int] = Field(default_factory=dict)
    scenario_counts: dict[str, int] = Field(default_factory=dict)
    capability_surfaces: dict[str, Any] = Field(default_factory=dict)
    findings: list[SuiteAuditFinding] = Field(default_factory=list)
    security_notes: list[str] = Field(default_factory=list)


def audit_suite(suite: SuiteDefinition) -> SuiteAuditReport:
    provenance_counts: dict[str, int] = {}
    risk_counts: dict[str, int] = {}
    scenario_counts: dict[str, int] = {}
    tool_names: set[str] = set()
    unnamed_tool_cases: set[str] = set()
    simulated_tools: set[str] = set()
    mcp_profiles: set[str] = set()
    skills: set[str] = set()
    response_format_cases = 0
    streaming_cases = 0
    trace_replay_cases = 0
    findings: list[SuiteAuditFinding] = []

    for case in suite.cases:
        provenance_counts[case.provenance] = provenance_counts.get(case.provenance, 0) + 1
        risk_counts[case.risk_level] = risk_counts.get(case.risk_level, 0) + 1
        if case.scenario:
            scenario_counts[case.scenario] = scenario_counts.get(case.scenario, 0) + 1

        if case.provenance in EXTERNAL_PROVENANCE:
            if not case.source_url:
                findings.append(
                    SuiteAuditFinding(
                        severity="warning",
                        case_id=case.id,
                        code="missing_source_url",
                        message=f"case {case.id} uses {case.provenance} provenance without source_url",
                    )
                )
            if not case.license:
                findings.append(
                    SuiteAuditFinding(
                        severity="warning",
                        case_id=case.id,
                        code="missing_license",
                        message=f"case {case.id} uses {case.provenance} provenance without license",
                    )
                )

        if case.risk_level == "high":
            findings.append(
                SuiteAuditFinding(
                    severity="warning",
                    case_id=case.id,
                    code="high_risk_case",
                    message=f"case {case.id} is marked high risk and should be policy-reviewed",
                )
            )

        for tool in case.tools:
            tool_name = _tool_schema_name(tool)
            if tool_name is None:
                unnamed_tool_cases.add(case.id)
            else:
                tool_names.add(tool_name)
        simulated_tools.update(case.simulated_tools)
        if case.mcp_profile:
            mcp_profiles.add(case.mcp_profile)
        skills.update(case.skills)
        if case.response_format:
            response_format_cases += 1
        if case.streaming:
            streaming_cases += 1
        if case.messages:
            trace_replay_cases += 1

    for case_id in sorted(unnamed_tool_cases):
        findings.append(
            SuiteAuditFinding(
                severity="warning",
                case_id=case_id,
                code="unnamed_tool_schema",
                message=f"case {case_id} includes a tool schema without a function name",
            )
        )

    return SuiteAuditReport(
        suite=suite.name,
        description=suite.description,
        total_cases=len(suite.cases),
        provenance_counts=dict(sorted(provenance_counts.items())),
        risk_counts=dict(sorted(risk_counts.items())),
        scenario_counts=dict(sorted(scenario_counts.items())),
        capability_surfaces={
            "tool_schema_names": sorted(tool_names),
            "tool_schema_cases": sum(1 for case in suite.cases if case.tools),
            "simulated_tools": sorted(simulated_tools),
            "simulated_tool_cases": sum(1 for case in suite.cases if case.simulated_tools),
            "mcp_profiles": sorted(mcp_profiles),
            "mcp_profile_cases": sum(1 for case in suite.cases if case.mcp_profile),
            "skills": sorted(skills),
            "skill_cases": sum(1 for case in suite.cases if case.skills),
            "response_format_cases": response_format_cases,
            "streaming_cases": streaming_cases,
            "trace_replay_cases": trace_replay_cases,
        },
        findings=findings,
        security_notes=[
            "Suite audit is static and does not contact providers, resolve secrets, or execute benchmark tools.",
            "Simulated tools, MCP profiles, and skills must still satisfy the active policy file before dispatch.",
        ],
    )


def format_suite_audit(report: SuiteAuditReport) -> str:
    lines = [
        f"suite: {report.suite}",
        f"description: {report.description}",
        f"total_cases: {report.total_cases}",
        f"provenance: {_format_counts(report.provenance_counts)}",
        f"risk: {_format_counts(report.risk_counts)}",
        f"scenarios: {_format_counts(report.scenario_counts)}",
        f"tool_schema_names: {_format_list(report.capability_surfaces['tool_schema_names'])}",
        f"simulated_tools: {_format_list(report.capability_surfaces['simulated_tools'])}",
        f"mcp_profiles: {_format_list(report.capability_surfaces['mcp_profiles'])}",
        f"skills: {_format_list(report.capability_surfaces['skills'])}",
        f"findings: {len(report.findings)}",
    ]
    for finding in report.findings:
        prefix = f"{finding.severity}\t{finding.code}"
        if finding.case_id:
            prefix = f"{prefix}\t{finding.case_id}"
        lines.append(f"{prefix}\t{finding.message}")
    return "\n".join(lines) + "\n"


def suite_audit_json(report: SuiteAuditReport) -> str:
    return json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def _tool_schema_name(tool: dict[str, Any]) -> str | None:
    function = tool.get("function")
    if isinstance(function, dict):
        name = function.get("name")
        if isinstance(name, str) and name:
            return name
    name = tool.get("name")
    if isinstance(name, str) and name:
        return name
    return None


def _format_counts(values: dict[str, int]) -> str:
    if not values:
        return "-"
    return ", ".join(f"{key}={value}" for key, value in values.items())


def _format_list(values: list[str]) -> str:
    return ", ".join(values) if values else "-"
