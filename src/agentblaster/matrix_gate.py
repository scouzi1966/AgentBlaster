from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from agentblaster.matrix import MatrixExecutionSummary


class MatrixGateFinding(BaseModel):
    """Machine-readable matrix gate finding."""

    model_config = ConfigDict(extra="forbid")

    metric: str
    actual: float | int | bool
    threshold: float | int | bool
    message: str


class MatrixGateReport(BaseModel):
    """Machine-readable pass/fail gate report for a matrix execution summary."""

    model_config = ConfigDict(extra="forbid")

    matrix_name: str
    ok: bool
    total_runs: int = Field(ge=0)
    attempted_runs: int = Field(ge=0)
    completed_runs: int = Field(ge=0)
    failed_runs: int = Field(ge=0)
    total_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    failed_cases: int = Field(ge=0)
    pass_rate_percent: float
    thresholds: dict[str, float | int | bool] = Field(default_factory=dict)
    findings: list[MatrixGateFinding] = Field(default_factory=list)


def evaluate_matrix_gate(
    summary: MatrixExecutionSummary,
    *,
    require_all_runs_complete: bool = False,
    max_failed_runs: int | None = None,
    min_completed_runs: int | None = None,
    min_attempted_runs: int | None = None,
    min_case_pass_rate: float | None = None,
    max_failed_cases: int | None = None,
) -> MatrixGateReport:
    attempted_runs = summary.attempted_runs or len(summary.runs)
    total_cases = sum(run.total_cases for run in summary.runs)
    passed_cases = sum(run.passed for run in summary.runs)
    failed_cases = sum(run.failed for run in summary.runs)
    pass_rate = round((passed_cases / total_cases) * 100, 3) if total_cases else 0.0
    thresholds = {
        key: value
        for key, value in {
            "require_all_runs_complete": require_all_runs_complete if require_all_runs_complete else None,
            "max_failed_runs": max_failed_runs,
            "min_completed_runs": min_completed_runs,
            "min_attempted_runs": min_attempted_runs,
            "min_case_pass_rate": min_case_pass_rate,
            "max_failed_cases": max_failed_cases,
        }.items()
        if value is not None
    }
    findings: list[MatrixGateFinding] = []

    if require_all_runs_complete and summary.completed_runs < summary.total_runs:
        findings.append(
            MatrixGateFinding(
                metric="all_runs_complete",
                actual=False,
                threshold=True,
                message=(
                    f"matrix completed {summary.completed_runs}/{summary.total_runs} runs; "
                    "all runs are required"
                ),
            )
        )
    if max_failed_runs is not None and summary.failed_runs > max_failed_runs:
        findings.append(
            MatrixGateFinding(
                metric="failed_runs",
                actual=summary.failed_runs,
                threshold=max_failed_runs,
                message=f"matrix failed_runs {summary.failed_runs} exceeds maximum {max_failed_runs}",
            )
        )
    if min_completed_runs is not None and summary.completed_runs < min_completed_runs:
        findings.append(
            MatrixGateFinding(
                metric="completed_runs",
                actual=summary.completed_runs,
                threshold=min_completed_runs,
                message=f"matrix completed_runs {summary.completed_runs} is below minimum {min_completed_runs}",
            )
        )
    if min_attempted_runs is not None and attempted_runs < min_attempted_runs:
        findings.append(
            MatrixGateFinding(
                metric="attempted_runs",
                actual=attempted_runs,
                threshold=min_attempted_runs,
                message=f"matrix attempted_runs {attempted_runs} is below minimum {min_attempted_runs}",
            )
        )
    if min_case_pass_rate is not None and pass_rate < min_case_pass_rate:
        findings.append(
            MatrixGateFinding(
                metric="case_pass_rate",
                actual=pass_rate,
                threshold=min_case_pass_rate,
                message=f"matrix case pass rate {pass_rate:.3f}% is below minimum {min_case_pass_rate:.3f}%",
            )
        )
    if max_failed_cases is not None and failed_cases > max_failed_cases:
        findings.append(
            MatrixGateFinding(
                metric="failed_cases",
                actual=failed_cases,
                threshold=max_failed_cases,
                message=f"matrix failed_cases {failed_cases} exceeds maximum {max_failed_cases}",
            )
        )

    return MatrixGateReport(
        matrix_name=summary.matrix_name,
        ok=not findings,
        total_runs=summary.total_runs,
        attempted_runs=attempted_runs,
        completed_runs=summary.completed_runs,
        failed_runs=summary.failed_runs,
        total_cases=total_cases,
        passed_cases=passed_cases,
        failed_cases=failed_cases,
        pass_rate_percent=pass_rate,
        thresholds=thresholds,
        findings=findings,
    )


def format_matrix_gate_report(report: MatrixGateReport) -> str:
    lines = [
        f"matrix: {report.matrix_name}",
        f"ok: {str(report.ok).lower()}",
        f"runs: {report.completed_runs}/{report.total_runs} completed",
        f"attempted_runs: {report.attempted_runs}",
        f"failed_runs: {report.failed_runs}",
        f"cases: {report.passed_cases}/{report.total_cases} passed",
        f"pass_rate_percent: {report.pass_rate_percent}",
        f"findings: {len(report.findings)}",
    ]
    for finding in report.findings:
        lines.append(
            f"{finding.metric}	actual={finding.actual}	threshold={finding.threshold}	{finding.message}"
        )
    return "
".join(lines) + "
"


def write_matrix_gate_json(report: MatrixGateReport, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "
", encoding="utf-8")
    return output_path
