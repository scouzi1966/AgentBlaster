from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from agentblaster.matrix import MatrixExecutionSummary


MATRIX_GATE_SCHEMA_VERSION = "agentblaster.matrix-gate.v1"


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

    schema_version: str = MATRIX_GATE_SCHEMA_VERSION
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
    failure_class_summary: list[dict[str, int | str]] = Field(default_factory=list)
    failure_class_artifacts_missing: int = Field(default=0, ge=0)
    tool_loop_stop_summary: list[dict[str, int | str]] = Field(default_factory=list)
    tool_loop_artifacts_missing: int = Field(default=0, ge=0)
    judge_rubric_cases: int = Field(default=0, ge=0)
    judge_verdicts_valid: int = Field(default=0, ge=0)
    judge_verdict_valid_rate_percent: float = 0.0
    judge_verdict_artifacts_missing: int = Field(default=0, ge=0)
    invalid_tool_call_count: int = Field(default=0, ge=0)
    tool_parser_repair_cases: int = Field(default=0, ge=0)
    tool_parser_repairs_valid: int = Field(default=0, ge=0)
    tool_parser_repair_valid_rate_percent: float = 0.0
    tool_parser_repair_artifacts_missing: int = Field(default=0, ge=0)
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
    max_failure_class_counts: dict[str, int] | None = None,
    include_failure_class_summary: bool = False,
    max_tool_loop_stop_reason_counts: dict[str, int] | None = None,
    include_tool_loop_summary: bool = False,
    min_judge_verdict_valid_rate: float | None = None,
    include_judge_verdict_summary: bool = False,
    max_invalid_tool_calls: int | None = None,
    min_tool_parser_repair_valid_rate: float | None = None,
    include_tool_parser_repair_summary: bool = False,
    result_base_dir: Path | None = None,
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
            **{
                f"max_failure_class.{failure_class}": max_count
                for failure_class, max_count in (max_failure_class_counts or {}).items()
            },
            **{
                f"max_tool_loop_stop_reason.{reason}": max_count
                for reason, max_count in (max_tool_loop_stop_reason_counts or {}).items()
            },
            "min_judge_verdict_valid_rate": min_judge_verdict_valid_rate,
            "max_invalid_tool_calls": max_invalid_tool_calls,
            "min_tool_parser_repair_valid_rate": min_tool_parser_repair_valid_rate,
        }.items()
        if value is not None
    }
    findings: list[MatrixGateFinding] = []
    failure_class_counts: dict[str, int] = {}
    missing_result_artifacts = 0
    tool_loop_stop_counts: dict[str, int] = {}
    tool_loop_missing_result_artifacts = 0
    judge_rubric_cases = 0
    judge_verdicts_valid = 0
    judge_verdict_missing_result_artifacts = 0
    judge_verdict_valid_rate = 0.0
    invalid_tool_call_count = 0
    tool_parser_repair_cases = 0
    tool_parser_repairs_valid = 0
    tool_parser_repair_missing_result_artifacts = 0
    tool_parser_repair_valid_rate = 0.0

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
    if include_failure_class_summary or max_failure_class_counts:
        failure_class_counts, missing_result_artifacts = _load_failure_class_counts(
            summary,
            base_dir=result_base_dir or Path("."),
        )
        if max_failure_class_counts and missing_result_artifacts:
            findings.append(
                MatrixGateFinding(
                    metric="failure_class_result_artifacts_missing",
                    actual=missing_result_artifacts,
                    threshold=0,
                    message=(
                        f"matrix has {missing_result_artifacts} run(s) without readable normalized "
                        "result artifacts required for failure-class gates"
                    ),
                )
            )
    if max_failure_class_counts:
        for failure_class, max_count in max_failure_class_counts.items():
            actual = failure_class_counts.get(failure_class, 0)
            if actual > max_count:
                findings.append(
                    MatrixGateFinding(
                        metric=f"failure_class.{failure_class}",
                        actual=actual,
                        threshold=max_count,
                        message=(
                            f"matrix failure class {failure_class} count {actual} exceeds maximum {max_count}"
                        ),
                    )
                )
    if include_tool_loop_summary or max_tool_loop_stop_reason_counts:
        tool_loop_stop_counts, tool_loop_missing_result_artifacts = _load_tool_loop_stop_counts(
            summary,
            base_dir=result_base_dir or Path("."),
        )
        if max_tool_loop_stop_reason_counts and tool_loop_missing_result_artifacts:
            findings.append(
                MatrixGateFinding(
                    metric="tool_loop_result_artifacts_missing",
                    actual=tool_loop_missing_result_artifacts,
                    threshold=0,
                    message=(
                        f"matrix has {tool_loop_missing_result_artifacts} run(s) without readable normalized "
                        "result artifacts required for tool-loop gates"
                    ),
                )
            )
    if max_tool_loop_stop_reason_counts:
        for reason, max_count in max_tool_loop_stop_reason_counts.items():
            actual = tool_loop_stop_counts.get(reason, 0)
            if actual > max_count:
                findings.append(
                    MatrixGateFinding(
                        metric=f"tool_loop_stop_reason.{reason}",
                        actual=actual,
                        threshold=max_count,
                        message=f"matrix tool-loop stop reason {reason} count {actual} exceeds maximum {max_count}",
                    )
                )
    if include_judge_verdict_summary or min_judge_verdict_valid_rate is not None:
        judge_rubric_cases, judge_verdicts_valid, judge_verdict_missing_result_artifacts = _load_judge_verdict_counts(
            summary,
            base_dir=result_base_dir or Path("."),
        )
        judge_verdict_valid_rate = (
            round((judge_verdicts_valid / judge_rubric_cases) * 100, 3) if judge_rubric_cases else 0.0
        )
        if min_judge_verdict_valid_rate is not None and judge_verdict_missing_result_artifacts:
            findings.append(
                MatrixGateFinding(
                    metric="judge_verdict_result_artifacts_missing",
                    actual=judge_verdict_missing_result_artifacts,
                    threshold=0,
                    message=(
                        f"matrix has {judge_verdict_missing_result_artifacts} run(s) without readable normalized "
                        "result artifacts required for judge-rubric verdict gates"
                    ),
                )
            )
        if min_judge_verdict_valid_rate is not None and judge_verdict_valid_rate < min_judge_verdict_valid_rate:
            findings.append(
                MatrixGateFinding(
                    metric="judge_verdict_valid_rate",
                    actual=judge_verdict_valid_rate,
                    threshold=min_judge_verdict_valid_rate,
                    message=(
                        f"matrix judge verdict valid rate {judge_verdict_valid_rate:.3f}% "
                        f"is below minimum {min_judge_verdict_valid_rate:.3f}%"
                    ),
                )
            )
    if (
        include_tool_parser_repair_summary
        or max_invalid_tool_calls is not None
        or min_tool_parser_repair_valid_rate is not None
    ):
        (
            invalid_tool_call_count,
            tool_parser_repair_cases,
            tool_parser_repairs_valid,
            tool_parser_repair_missing_result_artifacts,
        ) = _load_tool_parser_repair_counts(
            summary,
            base_dir=result_base_dir or Path("."),
        )
        tool_parser_repair_valid_rate = (
            round((tool_parser_repairs_valid / tool_parser_repair_cases) * 100, 3)
            if tool_parser_repair_cases
            else 0.0
        )
        if (
            (max_invalid_tool_calls is not None or min_tool_parser_repair_valid_rate is not None)
            and tool_parser_repair_missing_result_artifacts
        ):
            findings.append(
                MatrixGateFinding(
                    metric="tool_parser_repair_result_artifacts_missing",
                    actual=tool_parser_repair_missing_result_artifacts,
                    threshold=0,
                    message=(
                        f"matrix has {tool_parser_repair_missing_result_artifacts} run(s) without readable normalized "
                        "result artifacts required for tool-parser repair gates"
                    ),
                )
            )
        if max_invalid_tool_calls is not None and invalid_tool_call_count > max_invalid_tool_calls:
            findings.append(
                MatrixGateFinding(
                    metric="invalid_tool_calls",
                    actual=invalid_tool_call_count,
                    threshold=max_invalid_tool_calls,
                    message=(
                        f"matrix invalid tool-call count {invalid_tool_call_count} exceeds maximum "
                        f"{max_invalid_tool_calls}"
                    ),
                )
            )
        if (
            min_tool_parser_repair_valid_rate is not None
            and tool_parser_repair_valid_rate < min_tool_parser_repair_valid_rate
        ):
            findings.append(
                MatrixGateFinding(
                    metric="tool_parser_repair_valid_rate",
                    actual=tool_parser_repair_valid_rate,
                    threshold=min_tool_parser_repair_valid_rate,
                    message=(
                        f"matrix tool-parser repair valid rate {tool_parser_repair_valid_rate:.3f}% "
                        f"is below minimum {min_tool_parser_repair_valid_rate:.3f}%"
                    ),
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
        failure_class_summary=_failure_class_summary(failure_class_counts),
        failure_class_artifacts_missing=missing_result_artifacts,
        tool_loop_stop_summary=_tool_loop_stop_summary(tool_loop_stop_counts),
        tool_loop_artifacts_missing=tool_loop_missing_result_artifacts,
        judge_rubric_cases=judge_rubric_cases,
        judge_verdicts_valid=judge_verdicts_valid,
        judge_verdict_valid_rate_percent=judge_verdict_valid_rate,
        judge_verdict_artifacts_missing=judge_verdict_missing_result_artifacts,
        invalid_tool_call_count=invalid_tool_call_count,
        tool_parser_repair_cases=tool_parser_repair_cases,
        tool_parser_repairs_valid=tool_parser_repairs_valid,
        tool_parser_repair_valid_rate_percent=tool_parser_repair_valid_rate,
        tool_parser_repair_artifacts_missing=tool_parser_repair_missing_result_artifacts,
        findings=findings,
    )


def format_matrix_gate_report(report: MatrixGateReport) -> str:
    lines = [
        f"schema_version: {report.schema_version}",
        f"matrix: {report.matrix_name}",
        f"ok: {str(report.ok).lower()}",
        f"runs: {report.completed_runs}/{report.total_runs} completed",
        f"attempted_runs: {report.attempted_runs}",
        f"failed_runs: {report.failed_runs}",
        f"cases: {report.passed_cases}/{report.total_cases} passed",
        f"pass_rate_percent: {report.pass_rate_percent}",
        f"failure_classes: {_failure_class_summary_text(report.failure_class_summary)}",
        f"failure_class_artifacts_missing: {report.failure_class_artifacts_missing}",
        f"tool_loop_stop_reasons: {_tool_loop_stop_summary_text(report.tool_loop_stop_summary)}",
        f"tool_loop_artifacts_missing: {report.tool_loop_artifacts_missing}",
        f"judge_verdicts_valid: {report.judge_verdicts_valid}/{report.judge_rubric_cases}",
        f"judge_verdict_valid_rate_percent: {report.judge_verdict_valid_rate_percent}",
        f"judge_verdict_artifacts_missing: {report.judge_verdict_artifacts_missing}",
        f"invalid_tool_call_count: {report.invalid_tool_call_count}",
        f"tool_parser_repairs_valid: {report.tool_parser_repairs_valid}/{report.tool_parser_repair_cases}",
        f"tool_parser_repair_valid_rate_percent: {report.tool_parser_repair_valid_rate_percent}",
        f"tool_parser_repair_artifacts_missing: {report.tool_parser_repair_artifacts_missing}",
        f"findings: {len(report.findings)}",
    ]
    for finding in report.findings:
        lines.append(
            f"{finding.metric}	actual={finding.actual}	threshold={finding.threshold}	{finding.message}"
        )
    return "\n".join(lines) + "\n"


def write_matrix_gate_json(report: MatrixGateReport, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def _load_failure_class_counts(
    summary: MatrixExecutionSummary,
    *,
    base_dir: Path,
) -> tuple[dict[str, int], int]:
    counts: dict[str, int] = {}
    missing = 0
    for run in summary.runs:
        if not run.results_path:
            missing += 1
            continue
        results_path = Path(run.results_path)
        if not results_path.is_absolute():
            results_path = base_dir / results_path
        try:
            lines = results_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            missing += 1
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                missing += 1
                break
            if row.get("ok") is False:
                failure_class = str(row.get("failure_class") or "unclassified")
                counts[failure_class] = counts.get(failure_class, 0) + 1
    return counts, missing


def _load_tool_loop_stop_counts(
    summary: MatrixExecutionSummary,
    *,
    base_dir: Path,
) -> tuple[dict[str, int], int]:
    counts: dict[str, int] = {}
    missing = 0
    for run in summary.runs:
        if not run.results_path:
            missing += 1
            continue
        results_path = Path(run.results_path)
        if not results_path.is_absolute():
            results_path = base_dir / results_path
        try:
            lines = results_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            missing += 1
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                missing += 1
                break
            if row.get("tool_loop_enabled") is True:
                reason = str(row.get("tool_loop_stop_reason") or "unknown")
                counts[reason] = counts.get(reason, 0) + 1
    return counts, missing


def _load_judge_verdict_counts(
    summary: MatrixExecutionSummary,
    *,
    base_dir: Path,
) -> tuple[int, int, int]:
    total = 0
    valid = 0
    missing = 0
    for run in summary.runs:
        if not run.results_path:
            missing += 1
            continue
        results_path = Path(run.results_path)
        if not results_path.is_absolute():
            results_path = base_dir / results_path
        try:
            lines = results_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            missing += 1
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                missing += 1
                break
            verdict = row.get("judge_verdict_valid")
            if verdict is None:
                continue
            total += 1
            if verdict is True:
                valid += 1
    return total, valid, missing


def _load_tool_parser_repair_counts(
    summary: MatrixExecutionSummary,
    *,
    base_dir: Path,
) -> tuple[int, int, int, int]:
    invalid_tool_calls = 0
    total = 0
    valid = 0
    missing = 0
    for run in summary.runs:
        if not run.results_path:
            missing += 1
            continue
        results_path = Path(run.results_path)
        if not results_path.is_absolute():
            results_path = base_dir / results_path
        try:
            lines = results_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            missing += 1
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                missing += 1
                break
            try:
                invalid_tool_calls += int(row.get("invalid_tool_call_count") or 0)
            except (TypeError, ValueError):
                invalid_tool_calls += 0
            repair_valid = row.get("tool_parser_repair_valid")
            if repair_valid is None:
                continue
            total += 1
            if repair_valid is True:
                valid += 1
    return invalid_tool_calls, total, valid, missing


def _failure_class_summary(counts: dict[str, int]) -> list[dict[str, int | str]]:
    return [
        {"failure_class": failure_class, "count": count}
        for failure_class, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _tool_loop_stop_summary(counts: dict[str, int]) -> list[dict[str, int | str]]:
    return [
        {"stop_reason": reason, "count": count}
        for reason, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _failure_class_summary_text(summary: list[dict[str, int | str]]) -> str:
    if not summary:
        return "none"
    return ", ".join(f"{item['failure_class']}={item['count']}" for item in summary)


def _tool_loop_stop_summary_text(summary: list[dict[str, int | str]]) -> str:
    if not summary:
        return "none"
    return ", ".join(f"{item['stop_reason']}={item['count']}" for item in summary)
