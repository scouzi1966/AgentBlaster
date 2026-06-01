from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentblaster.errors import ConfigError


PROTOCOL_REPAIR_POSTURE_SCHEMA_VERSION = "agentblaster.protocol-repair-posture.v1"
CLAIM_READINESS_SCHEMA_VERSION = "agentblaster.claim-readiness.v1"
MATRIX_GATE_SCHEMA_VERSION = "agentblaster.matrix-gate.v1"
MATRIX_SCORECARD_REPORT_TYPE = "agentblaster-matrix-scorecard-v1"


def build_protocol_repair_posture(
    *,
    name: str,
    claim_readiness: Path | None = None,
    matrix_scorecards: list[Path] | None = None,
    matrix_gates: list[Path] | None = None,
) -> dict[str, Any]:
    """Build a redaction-safe protocol-repair posture report from compact review artifacts."""
    claim_payload = (
        _load_json_artifact(claim_readiness, expected_schema=CLAIM_READINESS_SCHEMA_VERSION)
        if claim_readiness is not None
        else {}
    )
    direct_scorecards = [
        _matrix_scorecard_source(_load_json_artifact(path), path)
        for path in matrix_scorecards or []
    ]
    direct_gates = [_matrix_gate_source(_load_json_artifact(path, expected_schema=MATRIX_GATE_SCHEMA_VERSION), path) for path in matrix_gates or []]
    claim_scorecards = _claim_scorecard_sources(claim_payload) if claim_payload and not direct_scorecards else []
    claim_gates = _claim_gate_sources(claim_payload) if claim_payload and not direct_gates else []
    scorecards = direct_scorecards or claim_scorecards
    gates = direct_gates or claim_gates
    scorecard_summary = _source_summary(scorecards, invalid_key="invalid_tool_call_count", missing_key=None)
    gate_summary = _source_summary(gates, invalid_key="invalid_tool_call_count", missing_key="tool_parser_repair_artifacts_missing")
    status = _status(scorecard_summary, gate_summary)
    source_artifacts = []
    if claim_readiness is not None:
        source_artifacts.append(_artifact_ref("claim_readiness", claim_readiness))
    source_artifacts.extend(_artifact_ref("matrix_scorecard", path) for path in matrix_scorecards or [])
    source_artifacts.extend(_artifact_ref("matrix_gate", path) for path in matrix_gates or [])
    disclosures = _disclosures(status, scorecard_summary, gate_summary, bool(claim_payload), bool(direct_scorecards), bool(direct_gates))
    return {
        "schema_version": PROTOCOL_REPAIR_POSTURE_SCHEMA_VERSION,
        "name": _safe_name(name),
        "status": status,
        "ready": status == "ready",
        "scorecard_summary": scorecard_summary,
        "matrix_gate_summary": gate_summary,
        "scorecards": scorecards,
        "matrix_gates": gates,
        "disclosures": disclosures,
        "recommendations": _recommendations(status, scorecard_summary, gate_summary),
        "security": {
            "source_artifact_count": len(source_artifacts),
            "source_artifacts": source_artifacts,
            "contains_raw_provider_payloads": False,
            "contains_raw_traces": False,
            "contains_secrets": False,
            "stores_raw_secrets": False,
            "path_policy": "Input paths are reduced to relative artifact names or basenames for absolute/parent-relative paths.",
            "notes": [
                "Protocol-repair posture reads compact review artifacts only.",
                "It does not open results.jsonl, raw traces, provider configs, keyrings, dotenv files, or remote endpoints.",
                "Direct matrix scorecards and matrix gates take precedence over compact copies embedded in claim-readiness artifacts to avoid double-counting.",
            ],
        },
    }


def write_protocol_repair_posture_json(report: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def write_protocol_repair_posture_markdown(report: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(format_protocol_repair_posture(report), encoding="utf-8")
    return output


def format_protocol_repair_posture(report: dict[str, Any]) -> str:
    scorecard_summary = report.get("scorecard_summary") if isinstance(report.get("scorecard_summary"), dict) else {}
    gate_summary = report.get("matrix_gate_summary") if isinstance(report.get("matrix_gate_summary"), dict) else {}
    lines = [
        "# AgentBlaster Protocol Repair Posture",
        "",
        "## Summary",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Name | `{_markdown_cell(report.get('name'))}` |",
        f"| Status | `{_markdown_cell(report.get('status'))}` |",
        f"| Ready | `{str(report.get('ready')).lower()}` |",
        f"| Scorecard sources | `{scorecard_summary.get('source_count', 0)}` |",
        f"| Scorecard repair cases | `{scorecard_summary.get('tool_parser_repairs_valid', 0)}/{scorecard_summary.get('tool_parser_repair_cases', 0)} valid` |",
        f"| Scorecard repair valid rate | `{_percent(scorecard_summary.get('tool_parser_repair_valid_rate_percent'))}` |",
        f"| Scorecard invalid tool calls | `{scorecard_summary.get('invalid_tool_call_count', 0)}` |",
        f"| Matrix-gate sources | `{gate_summary.get('source_count', 0)}` |",
        f"| Matrix-gate repair cases | `{gate_summary.get('tool_parser_repairs_valid', 0)}/{gate_summary.get('tool_parser_repair_cases', 0)} valid` |",
        f"| Matrix-gate repair valid rate | `{_percent(gate_summary.get('tool_parser_repair_valid_rate_percent'))}` |",
        f"| Matrix-gate invalid tool calls | `{gate_summary.get('invalid_tool_call_count', 0)}` |",
        f"| Matrix-gate evidence gaps | `{gate_summary.get('tool_parser_repair_artifacts_missing', 0)}` |",
        f"| Source artifacts | `{report.get('security', {}).get('source_artifact_count', 0)}` |",
        "",
        "## Scorecards",
        "",
    ]
    scorecards = report.get("scorecards") if isinstance(report.get("scorecards"), list) else []
    if scorecards:
        lines.extend(
            [
                "| Matrix | Source | Repair valid | Repair rate | Invalid tools | Result artifacts |",
                "| --- | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for item in scorecards:
            if isinstance(item, dict):
                lines.append(
                    "| "
                    f"{_markdown_cell(item.get('matrix_name'))} | "
                    f"{_markdown_cell(item.get('source'))} | "
                    f"{item.get('tool_parser_repairs_valid', 0)}/{item.get('tool_parser_repair_cases', 0)} | "
                    f"{_percent(item.get('tool_parser_repair_valid_rate_percent'))} | "
                    f"{item.get('invalid_tool_call_count', 0)} | "
                    f"{item.get('result_artifacts_loaded', 0)}/{item.get('entry_count', 0)} |"
                )
    else:
        lines.append("No matrix scorecard protocol-repair evidence supplied.")
    lines.extend(["", "## Matrix Gates", ""])
    gates = report.get("matrix_gates") if isinstance(report.get("matrix_gates"), list) else []
    if gates:
        lines.extend(
            [
                "| Matrix | Source | Gate OK | Repair valid | Repair rate | Invalid tools | Evidence gaps | Parser findings |",
                "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for item in gates:
            if isinstance(item, dict):
                lines.append(
                    "| "
                    f"{_markdown_cell(item.get('matrix_name'))} | "
                    f"{_markdown_cell(item.get('source'))} | "
                    f"`{str(item.get('ok')).lower()}` | "
                    f"{item.get('tool_parser_repairs_valid', 0)}/{item.get('tool_parser_repair_cases', 0)} | "
                    f"{_percent(item.get('tool_parser_repair_valid_rate_percent'))} | "
                    f"{item.get('invalid_tool_call_count', 0)} | "
                    f"{item.get('tool_parser_repair_artifacts_missing', 0)} | "
                    f"{item.get('parser_repair_finding_count', 0)} |"
                )
    else:
        lines.append("No matrix-gate protocol-repair evidence supplied.")
    lines.extend(["", "## Disclosures", ""])
    lines.extend(f"- {_markdown_cell(item)}" for item in report.get("disclosures", []) or ["No disclosures generated."])
    lines.extend(["", "## Recommendations", ""])
    lines.extend(f"- {_markdown_cell(item)}" for item in report.get("recommendations", []) or ["No recommendations generated."])
    lines.extend(
        [
            "",
            "## Security Boundary",
            "",
            "- This posture report excludes raw provider payloads, raw traces, API keys, request headers, keyring values, and dotenv contents.",
            "- Source artifact paths are reduced before inclusion.",
            "- Direct scorecard and matrix-gate artifacts are preferred over embedded claim-readiness summaries to avoid double-counting.",
            "",
        ]
    )
    return "\n".join(lines)


def _load_json_artifact(path: Path | None, *, expected_schema: str | None = None) -> dict[str, Any]:
    if path is None:
        raise ConfigError("missing JSON artifact path")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"cannot read JSON artifact {path.name}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON artifact {path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConfigError(f"JSON artifact {path.name} must contain an object")
    if expected_schema:
        schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema"), payload.get("report_type")) if value}
        if expected_schema not in schema_values:
            raise ConfigError(f"JSON artifact {path.name} must use schema {expected_schema}")
    return payload


def _matrix_scorecard_source(payload: dict[str, Any], path: Path) -> dict[str, Any]:
    schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema"), payload.get("report_type")) if value}
    if MATRIX_SCORECARD_REPORT_TYPE not in schema_values:
        raise ConfigError(f"matrix scorecard {path.name} must use report_type {MATRIX_SCORECARD_REPORT_TYPE}")
    matrix = payload.get("matrix") if isinstance(payload.get("matrix"), dict) else {}
    scorecard = payload.get("scorecard") if isinstance(payload.get("scorecard"), dict) else {}
    return {
        "source": "matrix-scorecard",
        "artifact": _artifact_ref("matrix_scorecard", path),
        "matrix_name": _safe_text(matrix.get("name")),
        "entry_count": _int(scorecard.get("entry_count")),
        "result_artifacts_loaded": _int(scorecard.get("result_artifacts_loaded")),
        "invalid_tool_call_count": _int(scorecard.get("invalid_tool_call_count")),
        "tool_parser_repair_cases": _int(scorecard.get("tool_parser_repair_cases")),
        "tool_parser_repairs_valid": _int(scorecard.get("tool_parser_repairs_valid")),
        "tool_parser_repair_valid_rate_percent": _rate(
            scorecard.get("tool_parser_repairs_valid"),
            scorecard.get("tool_parser_repair_cases"),
            scorecard.get("tool_parser_repair_valid_rate_percent"),
        ),
    }


def _matrix_gate_source(payload: dict[str, Any], path: Path) -> dict[str, Any]:
    findings = payload.get("findings") if isinstance(payload.get("findings"), list) else []
    parser_findings = [
        item
        for item in findings
        if isinstance(item, dict)
        and str(item.get("code") or item.get("finding") or item.get("category") or "").startswith("tool_parser_repair")
        or (isinstance(item, dict) and str(item.get("code") or item.get("finding") or item.get("category") or "") == "invalid_tool_calls")
    ]
    return {
        "source": "matrix-gate",
        "artifact": _artifact_ref("matrix_gate", path),
        "matrix_name": _safe_text(payload.get("matrix_name")),
        "ok": payload.get("ok") is True,
        "invalid_tool_call_count": _int(payload.get("invalid_tool_call_count")),
        "tool_parser_repair_cases": _int(payload.get("tool_parser_repair_cases")),
        "tool_parser_repairs_valid": _int(payload.get("tool_parser_repairs_valid")),
        "tool_parser_repair_valid_rate_percent": _rate(
            payload.get("tool_parser_repairs_valid"),
            payload.get("tool_parser_repair_cases"),
            payload.get("tool_parser_repair_valid_rate_percent"),
        ),
        "tool_parser_repair_artifacts_missing": _int(payload.get("tool_parser_repair_artifacts_missing")),
        "parser_repair_finding_count": len(parser_findings),
    }


def _claim_scorecard_sources(payload: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    summaries = evidence.get("matrix_scorecard_summaries")
    rows = summaries if isinstance(summaries, list) else []
    scorecards = []
    for index, item in enumerate(rows, start=1):
        if not isinstance(item, dict):
            continue
        scorecards.append(
            {
                "source": "claim-readiness",
                "artifact": {"kind": "claim_readiness_embedded_scorecard", "name": f"matrix scorecard summary {index}"},
                "matrix_name": _safe_text(item.get("matrix_name") or item.get("matrix")),
                "entry_count": _int(item.get("entry_count")),
                "result_artifacts_loaded": _int(item.get("result_artifacts_loaded")),
                "invalid_tool_call_count": _int(item.get("invalid_tool_call_count")),
                "tool_parser_repair_cases": _int(item.get("tool_parser_repair_cases")),
                "tool_parser_repairs_valid": _int(item.get("tool_parser_repairs_valid")),
                "tool_parser_repair_valid_rate_percent": _rate(
                    item.get("tool_parser_repairs_valid"),
                    item.get("tool_parser_repair_cases"),
                    item.get("tool_parser_repair_valid_rate_percent"),
                ),
            }
        )
    return scorecards


def _claim_gate_sources(payload: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    gate = evidence.get("matrix_gate_tool_parser_repair_summary")
    if not isinstance(gate, dict):
        return []
    return [
        {
            "source": "claim-readiness",
            "artifact": {"kind": "claim_readiness_embedded_matrix_gate", "name": "matrix gate tool parser repair summary"},
            "matrix_name": _safe_text(gate.get("matrix_name") or payload.get("name")),
            "ok": gate.get("ok") is True if "ok" in gate else None,
            "invalid_tool_call_count": _int(gate.get("invalid_tool_call_count")),
            "tool_parser_repair_cases": _int(gate.get("tool_parser_repair_cases")),
            "tool_parser_repairs_valid": _int(gate.get("tool_parser_repairs_valid")),
            "tool_parser_repair_valid_rate_percent": _rate(
                gate.get("tool_parser_repairs_valid"),
                gate.get("tool_parser_repair_cases"),
                gate.get("tool_parser_repair_valid_rate_percent"),
            ),
            "tool_parser_repair_artifacts_missing": _int(evidence.get("matrix_gate_tool_parser_repair_artifacts_missing")),
            "parser_repair_finding_count": _int(gate.get("parser_repair_finding_count")),
        }
    ]


def _source_summary(sources: list[dict[str, Any]], *, invalid_key: str, missing_key: str | None) -> dict[str, Any]:
    cases = sum(_int(item.get("tool_parser_repair_cases")) for item in sources)
    valid = sum(_int(item.get("tool_parser_repairs_valid")) for item in sources)
    invalid = sum(_int(item.get(invalid_key)) for item in sources)
    missing = sum(_int(item.get(missing_key)) for item in sources) if missing_key else 0
    findings = sum(_int(item.get("parser_repair_finding_count")) for item in sources)
    return {
        "source_count": len(sources),
        "invalid_tool_call_count": invalid,
        "tool_parser_repair_cases": cases,
        "tool_parser_repairs_valid": valid,
        "tool_parser_repair_valid_rate_percent": round((valid / cases) * 100, 3) if cases else 0.0,
        "tool_parser_repair_artifacts_missing": missing,
        "parser_repair_finding_count": findings,
    }


def _status(scorecard_summary: dict[str, Any], gate_summary: dict[str, Any]) -> str:
    scorecard_cases = _int(scorecard_summary.get("tool_parser_repair_cases"))
    gate_cases = _int(gate_summary.get("tool_parser_repair_cases"))
    if scorecard_cases == 0 and gate_cases == 0:
        return "no-evidence"
    has_invalid = _int(scorecard_summary.get("invalid_tool_call_count")) or _int(gate_summary.get("invalid_tool_call_count"))
    incomplete_repair = (
        _int(scorecard_summary.get("tool_parser_repairs_valid")) < scorecard_cases
        or _int(gate_summary.get("tool_parser_repairs_valid")) < gate_cases
    )
    evidence_gaps = _int(gate_summary.get("tool_parser_repair_artifacts_missing")) or _int(gate_summary.get("parser_repair_finding_count"))
    if has_invalid or incomplete_repair or evidence_gaps:
        return "review-required"
    return "ready"


def _disclosures(
    status: str,
    scorecard_summary: dict[str, Any],
    gate_summary: dict[str, Any],
    has_claim_readiness: bool,
    has_direct_scorecards: bool,
    has_direct_gates: bool,
) -> list[str]:
    disclosures: list[str] = []
    if status == "no-evidence":
        disclosures.append("No protocol-repair scorecard or matrix-gate evidence was supplied.")
    if not has_direct_scorecards and has_claim_readiness:
        disclosures.append("Scorecard posture is derived from compact claim-readiness evidence because no direct matrix scorecard artifact was supplied.")
    if not has_direct_gates and has_claim_readiness:
        disclosures.append("Matrix-gate posture is derived from compact claim-readiness evidence because no direct matrix gate artifact was supplied.")
    invalid = _int(scorecard_summary.get("invalid_tool_call_count")) + _int(gate_summary.get("invalid_tool_call_count"))
    if invalid:
        disclosures.append(f"Protocol-repair evidence reports {invalid} invalid tool-call emission(s).")
    total_cases = _int(scorecard_summary.get("tool_parser_repair_cases")) + _int(gate_summary.get("tool_parser_repair_cases"))
    total_valid = _int(scorecard_summary.get("tool_parser_repairs_valid")) + _int(gate_summary.get("tool_parser_repairs_valid"))
    if total_cases and total_valid < total_cases:
        disclosures.append(f"Only {total_valid}/{total_cases} parser-repair cases are valid across summarized evidence.")
    if _int(gate_summary.get("tool_parser_repair_artifacts_missing")):
        disclosures.append(f"Matrix-gate evidence is missing {_int(gate_summary.get('tool_parser_repair_artifacts_missing'))} referenced result artifact(s).")
    if _int(gate_summary.get("parser_repair_finding_count")):
        disclosures.append(f"Matrix gates include {_int(gate_summary.get('parser_repair_finding_count'))} parser-repair finding(s).")
    return disclosures or ["Protocol-repair evidence is ready for publication review; keep raw logs and traces out of external materials."]


def _recommendations(status: str, scorecard_summary: dict[str, Any], gate_summary: dict[str, Any]) -> list[str]:
    if status == "ready":
        return [
            "Use the scorecard and matrix-gate counts as compact protocol-repair evidence in publication and corporate review packets.",
            "Pair this posture with telemetry and matrix-saturation evidence before making broader engine-quality claims.",
        ]
    if status == "no-evidence":
        return [
            "Generate a matrix scorecard or matrix gate with tool-parser repair summaries before publishing agentic protocol claims.",
            "Use matrix-gate thresholds such as max invalid tool calls and minimum parser-repair valid rate for release blocking.",
        ]
    recommendations = ["Resolve invalid tool-call emissions and parser-repair failures before external publication."]
    if _int(gate_summary.get("tool_parser_repair_artifacts_missing")):
        recommendations.append("Regenerate matrix-gate evidence from a matrix summary whose referenced result artifacts are present.")
    if _int(scorecard_summary.get("tool_parser_repair_cases")) == 0:
        recommendations.append("Add matrix scorecards so reviewers can compare parser-repair behavior across engines and models.")
    if _int(gate_summary.get("tool_parser_repair_cases")) == 0:
        recommendations.append("Add matrix gates so release policy can enforce parser-repair thresholds.")
    return recommendations


def _artifact_ref(kind: str, path: Path) -> dict[str, str]:
    path = path.expanduser()
    safe_name = path.name if path.is_absolute() or ".." in path.parts else str(path)
    return {"kind": kind, "name": safe_name}


def _safe_name(value: Any) -> str:
    text = _safe_text(value) or "benchmark-claim"
    return text[:160]


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\0", "").strip()
    return text[:240]


def _markdown_cell(value: Any) -> str:
    return _safe_text(value).replace("|", "\\|") or "n/a"


def _int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rate(valid: Any, cases: Any, explicit: Any) -> float:
    explicit_num = _num(explicit)
    if explicit_num is not None:
        return round(explicit_num, 3)
    case_count = _int(cases)
    if not case_count:
        return 0.0
    return round((_int(valid) / case_count) * 100, 3)


def _percent(value: Any) -> str:
    number = _num(value)
    if number is None:
        return "n/a"
    return f"{number:.1f}%"
