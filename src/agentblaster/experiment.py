from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

EXPERIMENT_SCHEMA_VERSION = "agentblaster.experiment-manifest.v1"
EXPERIMENT_GATE_SCHEMA_VERSION = "agentblaster.experiment-gate.v1"


def build_experiment_manifest(
    *,
    name: str,
    objective: str,
    providers: list[str],
    targets: list[str],
    suites: list[str],
    policy: Path | None = None,
    matrix: Path | None = None,
    readiness_required: bool = True,
    contract_checks_required: bool = True,
    metric_coverage_required: bool = True,
    prompt_footprint_required: bool = True,
    calibration_required: bool = False,
    min_case_pass_rate: float = 95.0,
    max_failed_runs: int = 0,
) -> dict[str, Any]:
    cleaned_name = _safe_name(name)
    providers = _clean_list(providers)
    targets = _clean_list(targets)
    suites = _clean_list(suites)
    return {
        "schema_version": EXPERIMENT_SCHEMA_VERSION,
        "name": cleaned_name,
        "created_at": _utc_now(),
        "objective": objective.strip(),
        "scope": {
            "providers": providers,
            "targets": targets,
            "suites": suites,
            "matrix": str(matrix) if matrix else None,
            "policy": str(policy) if policy else None,
        },
        "required_preflight_artifacts": {
            "readiness_dossiers": readiness_required,
            "provider_contract_checks": contract_checks_required,
            "metric_coverage_reports": metric_coverage_required,
            "prompt_footprint_reports": prompt_footprint_required,
            "suite_calibration_reports": calibration_required,
        },
        "acceptance_gates": {
            "min_case_pass_rate": min_case_pass_rate,
            "max_failed_runs": max_failed_runs,
            "require_all_runs_complete": True,
            "require_redaction_scan": True,
            "require_release_provenance": True,
        },
        "publication_rules": {
            "separate_local_and_remote_rankings": True,
            "cite_model_metadata": True,
            "cite_metric_coverage": True,
            "cite_suite_sha256": True,
            "exclude_raw_traces": True,
            "exclude_results_jsonl_from_publication_bundle": True,
        },
        "security": {
            "contains_raw_secrets": False,
            "contains_raw_provider_payloads": False,
            "contacts_providers": False,
            "stores_api_keys": False,
            "notes": "Experiment manifests are static planning artifacts and do not execute benchmarks.",
        },
        "suggested_artifacts": _suggested_artifacts(cleaned_name, providers, targets, suites),
    }


def evaluate_experiment_manifest(manifest: dict[str, Any], *, require_policy: bool = False) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    if manifest.get("schema_version") != EXPERIMENT_SCHEMA_VERSION:
        findings.append(_finding("invalid_schema", "experiment manifest schema_version is missing or unsupported"))
    name = str(manifest.get("name") or "").strip()
    if not name:
        findings.append(_finding("missing_name", "experiment name is required"))
    objective = str(manifest.get("objective") or "").strip()
    if len(objective) < 12:
        findings.append(_finding("weak_objective", "experiment objective should describe the benchmark claim or decision"))
    scope = manifest.get("scope") if isinstance(manifest.get("scope"), dict) else {}
    for key in ("providers", "targets", "suites"):
        values = scope.get(key)
        if not isinstance(values, list) or not values:
            findings.append(_finding(f"missing_{key}", f"scope.{key} must contain at least one value"))
    if require_policy and not scope.get("policy"):
        findings.append(_finding("missing_policy", "policy path is required for this experiment gate"))
    required = manifest.get("required_preflight_artifacts") if isinstance(manifest.get("required_preflight_artifacts"), dict) else {}
    for key in ("readiness_dossiers", "provider_contract_checks", "metric_coverage_reports", "prompt_footprint_reports"):
        if required.get(key) is not True:
            warnings.append(_finding(f"preflight_not_required_{key}", f"{key} is not marked required"))
    gates = manifest.get("acceptance_gates") if isinstance(manifest.get("acceptance_gates"), dict) else {}
    if float(gates.get("min_case_pass_rate") or 0.0) <= 0.0:
        findings.append(_finding("invalid_min_case_pass_rate", "min_case_pass_rate must be positive"))
    if int(gates.get("max_failed_runs") or 0) < 0:
        findings.append(_finding("invalid_max_failed_runs", "max_failed_runs cannot be negative"))
    if gates.get("require_redaction_scan") is not True:
        warnings.append(_finding("redaction_scan_not_required", "publication workflow should require redaction scan"))
    publication = manifest.get("publication_rules") if isinstance(manifest.get("publication_rules"), dict) else {}
    for key in ("cite_model_metadata", "cite_metric_coverage", "exclude_raw_traces"):
        if publication.get(key) is not True:
            warnings.append(_finding(f"publication_rule_disabled_{key}", f"publication rule {key} should be enabled"))
    return {
        "schema_version": EXPERIMENT_GATE_SCHEMA_VERSION,
        "experiment": name,
        "passed": not findings,
        "summary": {
            "findings": len(findings),
            "warnings": len(warnings),
            "providers": len(scope.get("providers") or []),
            "targets": len(scope.get("targets") or []),
            "suites": len(scope.get("suites") or []),
        },
        "findings": findings,
        "warnings": warnings,
        "notes": [
            "Experiment gate is static and does not inspect run artifacts or contact providers.",
            "Use matrix/report gates after execution to evaluate runtime results.",
        ],
    }


def load_experiment_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid experiment manifest at {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"invalid experiment manifest at {path}: root must be an object")
    return payload


def write_experiment_json(payload: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def format_experiment_gate(report: dict[str, Any]) -> str:
    lines = [
        "AgentBlaster experiment gate",
        f"experiment: {report['experiment']}",
        f"passed: {str(report['passed']).lower()}",
        "summary:",
    ]
    for key, value in report["summary"].items():
        lines.append(f"- {key}: {value}")
    lines.append("findings:")
    lines.extend(_format_findings(report["findings"]))
    lines.append("warnings:")
    lines.extend(_format_findings(report["warnings"]))
    return "\n".join(lines) + "\n"


def _format_findings(items: list[dict[str, str]]) -> list[str]:
    if not items:
        return ["- none"]
    return [f"- {item['code']}: {item['message']}" for item in items]


def _suggested_artifacts(name: str, providers: list[str], targets: list[str], suites: list[str]) -> dict[str, Any]:
    return {
        "readiness_dossiers": [
            f"reports/readiness/{provider}-{target}-{suite}-readiness.json"
            for provider in providers
            for target in targets
            for suite in suites
        ],
        "metric_coverage_reports": [f"reports/metrics/{provider}-metric-coverage.json" for provider in providers],
        "prompt_footprint_reports": [f"reports/footprints/{suite}-footprint.json" for suite in suites],
        "matrix_summary": f"reports/{name}-matrix-summary.json",
        "matrix_gate": f"reports/{name}-matrix-gate.json",
        "publication_bundle_dir": f"publication-bundles/{name}",
        "release_qualification_bundle": f"release-bundles/{name}.agentblaster-release-qualification.zip",
    }


def _clean_list(values: list[str]) -> list[str]:
    return [value.strip() for value in values if value.strip()]


def _safe_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in value.strip()).strip("-")
    return cleaned or "agentblaster-experiment"


def _finding(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
