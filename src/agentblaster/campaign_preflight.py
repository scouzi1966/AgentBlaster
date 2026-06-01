from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import tomllib
from typing import Any

from agentblaster.config import ProviderStore
from agentblaster.capabilities import case_capability_surfaces, suite_requirements
from agentblaster.engine_targets import compact_engine_target_for_provider
from agentblaster.environment import build_environment_readiness
from agentblaster.errors import ConfigError
from agentblaster.implementation_status import build_implementation_status
from agentblaster.matrix import MatrixDefinition, MatrixRun, load_matrix_file
from agentblaster.matrix_pressure import audit_matrix_pressure
from agentblaster.policy import estimate_case_prompt_tokens, load_policy
from agentblaster.prompt_footprint import suite_prompt_footprint
from agentblaster.provider_audit import audit_providers
from agentblaster.readiness import READINESS_SCHEMA_VERSION
from agentblaster.release import build_packaging_readiness
from agentblaster.schema_registry import artifact_schema_registry
from agentblaster.suite_audit import audit_suite
from agentblaster.suites import get_builtin_suite, load_suite_file


CAMPAIGN_PREFLIGHT_SCHEMA_VERSION = "agentblaster.campaign-preflight-bundle.v1"


@dataclass(frozen=True)
class CampaignPreflightBundle:
    output_dir: Path
    manifest_path: Path
    artifact_paths: list[Path]
    manifest: dict[str, Any]


def create_campaign_preflight_bundle(
    *,
    output_dir: Path,
    matrices: list[Path],
    policy: Path | None = None,
    project_root: Path | None = None,
    home: Path | None = None,
    include_provider_audit: bool = True,
    benchmark_readiness_reports: list[Path] | None = None,
) -> CampaignPreflightBundle:
    """Create a no-dispatch evidence folder for a benchmark campaign."""

    if not matrices:
        raise ConfigError("campaign preflight requires at least one matrix")

    root = (project_root or Path.cwd()).resolve()
    output_dir = output_dir.expanduser()
    if output_dir.exists() and not output_dir.is_dir():
        raise ConfigError(f"campaign preflight output path is not a directory: {output_dir}")

    loaded_matrices = [(path, load_matrix_file(path)) for path in matrices]
    policy_payload = _policy_payload(policy)
    artifacts: dict[Path, bytes] = {}
    benchmark_readiness_report_count = len(benchmark_readiness_reports or [])

    artifacts[Path("readiness/environment-readiness.json")] = _json_bytes(build_environment_readiness(home=home))
    artifacts[Path("readiness/implementation-status.json")] = _json_bytes(_redacted_implementation_status(root))
    artifacts[Path("readiness/packaging-readiness.json")] = _json_bytes(_packaging_readiness(root))
    artifacts[Path("catalogs/artifact-schemas.json")] = _json_bytes(artifact_schema_registry())
    if policy_payload is not None:
        artifacts[Path("policy/policy-normalized.json")] = _json_bytes(policy_payload["normalized"])
        artifacts[Path("policy/policy.yaml")] = policy_payload["raw"]
    if include_provider_audit:
        provider_policy = load_policy(policy) if policy is not None else load_policy(None)
        artifacts[Path("providers/provider-audit.json")] = _json_bytes(
            _model_payload(audit_providers(ProviderStore().list(), provider_policy))
        )
    if benchmark_readiness_reports:
        artifacts[Path("readiness/benchmark-readiness-index.json")] = _json_bytes(
            _benchmark_readiness_index(benchmark_readiness_reports)
        )

    matrix_artifacts = []
    used_matrix_names: set[str] = set()
    for index, (matrix_path, matrix) in enumerate(loaded_matrices, start=1):
        inventory = _matrix_inventory(matrix_path, matrix)
        artifact_name = _unique_matrix_artifact_name(index, matrix.name, used_matrix_names)
        pressure_artifact_name = artifact_name.replace("-inventory.json", "-pressure.json")
        artifacts[Path("matrices") / artifact_name] = _json_bytes(inventory)
        artifacts[Path("pressure") / pressure_artifact_name] = _json_bytes(audit_matrix_pressure(matrix_path))
        matrix_artifacts.append(
            {
                "matrix": matrix.name,
                "matrix_path": str(matrix_path),
                "matrix_source_name": matrix_path.name,
                "matrix_path_contains_local_context": _looks_like_local_path(str(matrix_path)),
                "artifact_path": f"matrices/{artifact_name}",
                "pressure_artifact_path": f"pressure/{pressure_artifact_name}",
                "run_count": inventory["run_count"],
                "total_cases": inventory["total_cases"],
                "engine_targets": inventory["engine_targets"],
                "dry_run_command": [
                    "agentblaster",
                    "run",
                    "--matrix",
                    str(matrix_path),
                    "--offline",
                    "--dry-run",
                    "--plan-json",
                    f"reports/{_safe_id(matrix.name)}-plan.json",
                ],
            }
        )

    artifacts[Path("matrices/index.json")] = _json_bytes(
        {
            "schema_version": "agentblaster.campaign-preflight-matrix-index.v1",
            "matrix_count": len(matrix_artifacts),
            "matrices": matrix_artifacts,
        }
    )
    artifacts[Path("RUNBOOK.md")] = _markdown_bytes(_runbook(matrix_artifacts, policy=policy))

    manifest = _manifest(
        output_dir=output_dir,
        matrices=matrix_artifacts,
        artifacts=artifacts,
        policy=policy,
        project_root=root,
        home=home,
        include_provider_audit=include_provider_audit,
        includes_benchmark_readiness=bool(benchmark_readiness_reports),
        benchmark_readiness_report_count=benchmark_readiness_report_count,
    )
    artifacts[Path("manifest.json")] = _json_bytes(manifest)

    written = _write_artifacts(output_dir, artifacts)
    return CampaignPreflightBundle(
        output_dir=output_dir,
        manifest_path=output_dir / "manifest.json",
        artifact_paths=written,
        manifest=manifest,
    )


def format_campaign_preflight_bundle(bundle: CampaignPreflightBundle) -> str:
    manifest = bundle.manifest
    lines = [
        "AgentBlaster campaign preflight bundle",
        f"schema_version: {manifest['schema_version']}",
        f"output_dir: {bundle.output_dir}",
        f"manifest: {bundle.manifest_path}",
        f"matrix_count: {manifest['matrix_count']}",
        f"artifact_count: {manifest['artifact_count']}",
        f"contacts_providers: {str(manifest['security']['contacts_providers']).lower()}",
        f"contains_raw_secrets: {str(manifest['security']['contains_raw_secrets']).lower()}",
        f"includes_benchmark_readiness: {str(manifest.get('includes_benchmark_readiness', False)).lower()}",
    ]
    return "\n".join(lines) + "\n"


def _matrix_inventory(matrix_path: Path, matrix: MatrixDefinition) -> dict[str, Any]:
    runs = [_run_inventory(index, run) for index, run in enumerate(matrix.runs, start=1)]
    return {
        "schema_version": "agentblaster.campaign-preflight-matrix-inventory.v1",
        "matrix": matrix.name,
        "matrix_path": str(matrix_path),
        "description": matrix.description,
        "run_count": len(runs),
        "total_cases": sum(run["case_count"] for run in runs),
        "estimated_prompt_tokens": sum(run["estimated_prompt_tokens"] for run in runs),
        "max_output_tokens": sum(run["max_output_tokens"] for run in runs),
        "prompt_footprint": {
            "prefill_pressure_score": sum(run["prompt_footprint"]["prefill_pressure_score"] for run in runs),
            "shared_static_prefix_groups": sum(run["prompt_footprint"]["shared_static_prefix_groups"] for run in runs),
            "shared_static_reuse_tokens": sum(run["prompt_footprint"]["shared_static_reuse_tokens"] for run in runs),
            "static_prefix_tokens": sum(run["prompt_footprint"]["static_prefix_tokens"] for run in runs),
            "dynamic_prompt_tokens": sum(run["prompt_footprint"]["dynamic_prompt_tokens"] for run in runs),
        },
        "engines": sorted({run["engine"] for run in runs}),
        "engine_targets": sorted(
            {
                run["engine_target"]["id"]
                for run in runs
                if isinstance(run.get("engine_target"), dict) and run["engine_target"].get("id")
            }
        ),
        "models": sorted({run["model"] for run in runs if run["model"]}),
        "suites": sorted({run["suite"] for run in runs}),
        "concurrency_levels": sorted({run["concurrency"] for run in runs}),
        "raw_trace_modes": sorted({run["raw_trace_mode"] for run in runs}),
        "runs": runs,
        "safety": {
            "dispatches_provider_requests": False,
            "resolves_secrets": False,
            "executes_tools": False,
            "loads_suite_definitions": True,
            "uses_static_token_estimates": True,
        },
    }


def _run_inventory(index: int, run: MatrixRun) -> dict[str, Any]:
    suite = load_suite_file(run.suite_file) if run.suite_file is not None else get_builtin_suite(run.suite)
    suite_audit = audit_suite(suite)
    capability_requirements = suite_requirements(suite)
    footprint = suite_prompt_footprint(suite)
    footprint_summary = _prompt_footprint_summary(footprint)
    prompt_tokens = [estimate_case_prompt_tokens(case) for case in suite.cases]
    trace_mode = "off" if run.no_raw_traces else run.raw_traces.value
    engine_target = compact_engine_target_for_provider(run.engine)
    return {
        "index": index,
        "engine": run.engine,
        "engine_target": engine_target,
        "model": run.model,
        "suite": suite.name,
        "suite_file": str(run.suite_file) if run.suite_file is not None else None,
        "concurrency": run.concurrency,
        "raw_trace_mode": trace_mode,
        "no_raw_traces": run.no_raw_traces,
        "capability_preflight": run.capability_preflight,
        "strict_unknown_capabilities": run.strict_unknown_capabilities,
        "case_count": len(suite.cases),
        "estimated_prompt_tokens": sum(prompt_tokens),
        "max_output_tokens": sum(case.max_tokens for case in suite.cases),
        "prompt_footprint": footprint_summary,
        "case_ids": [case.id for case in suite.cases],
        "capability_requirement_keys": [requirement.key for requirement in capability_requirements],
        "capability_requirements": [
            requirement.model_dump(mode="json", exclude_none=True) for requirement in capability_requirements
        ],
        "case_capability_surfaces": [
            {"case_id": case.id, "surfaces": case_capability_surfaces(case)} for case in suite.cases
        ],
        "case_prompt_surfaces": [
            {
                "case_id": case["case_id"],
                "static_prefix_tokens": case["static_prefix_tokens"],
                "dynamic_prompt_tokens": case["dynamic_prompt_tokens"],
                "surfaces": case["surfaces"],
            }
            for case in footprint["cases"]
        ],
        "suite_audit": {
            "finding_count": len(suite_audit.findings),
            "finding_codes": sorted({finding.code for finding in suite_audit.findings}),
            "provenance_counts": suite_audit.provenance_counts,
            "risk_counts": suite_audit.risk_counts,
            "dataset_hygiene": suite_audit.dataset_hygiene,
        },
        "model_metadata": run.model_metadata.model_dump(mode="json"),
    }


def _prompt_footprint_summary(footprint: dict[str, Any]) -> dict[str, Any]:
    pressure = footprint.get("prefill_pressure") if isinstance(footprint.get("prefill_pressure"), dict) else {}
    reuse = footprint.get("shared_static_reuse") if isinstance(footprint.get("shared_static_reuse"), dict) else {}
    component_totals = footprint.get("component_totals") if isinstance(footprint.get("component_totals"), dict) else {}
    return {
        "prefill_pressure_level": str(pressure.get("level") or "unknown"),
        "prefill_pressure_score": _int(pressure.get("score")),
        "shared_static_prefix_groups": _int(reuse.get("group_count")),
        "shared_static_reuse_tokens": _int(reuse.get("potential_cache_reuse_tokens")),
        "shared_static_reuse_case_count": _int(reuse.get("repeated_case_count")),
        "max_shared_static_group_cases": _int(reuse.get("max_group_case_count")),
        "static_prefix_tokens": sum(
            _int(component_totals.get(key))
            for key in ("system_prompt", "cache_control", "tools", "simulated_tools", "mcp_profile", "lcp_profile", "skills")
        ),
        "dynamic_prompt_tokens": _int(component_totals.get("prompt")) + _int(component_totals.get("messages")),
    }


def _int(value: Any) -> int:
    return int(value) if isinstance(value, int | float) else 0


def _manifest(
    *,
    output_dir: Path,
    matrices: list[dict[str, Any]],
    artifacts: dict[Path, bytes],
    policy: Path | None,
    project_root: Path,
    home: Path | None,
    include_provider_audit: bool,
    includes_benchmark_readiness: bool,
    benchmark_readiness_report_count: int,
) -> dict[str, Any]:
    artifact_entries = [
        {
            "path": str(path),
            "sha256": sha256(data).hexdigest(),
            "size_bytes": len(data),
        }
        for path, data in sorted(artifacts.items(), key=lambda item: str(item[0]))
    ]
    return {
        "schema_version": CAMPAIGN_PREFLIGHT_SCHEMA_VERSION,
        "created_at": _utc_now(),
        "output_dir": str(output_dir),
        "project_root": str(project_root),
        "home": str(home) if home else None,
        "policy": str(policy) if policy else None,
        "includes_provider_audit": include_provider_audit,
        "includes_benchmark_readiness": includes_benchmark_readiness,
        "benchmark_readiness": {
            "artifact_path": "readiness/benchmark-readiness-index.json" if includes_benchmark_readiness else None,
            "report_count": benchmark_readiness_report_count,
        },
        "review_summary": _review_summary(
            matrices=matrices,
            includes_provider_audit=include_provider_audit,
            includes_benchmark_readiness=includes_benchmark_readiness,
            benchmark_readiness_report_count=benchmark_readiness_report_count,
        ),
        "matrix_count": len(matrices),
        "matrices": matrices,
        "artifact_count": len(artifact_entries),
        "artifacts": artifact_entries,
        "security": {
            "contacts_providers": False,
            "resolves_secrets": False,
            "reads_keyring_values": False,
            "stores_provider_configs": False,
            "contains_raw_secrets": False,
            "contains_raw_provider_payloads": False,
            "contains_raw_traces": False,
            "contains_local_paths": True,
            "external_publication_safe": False,
            "writes_run_artifacts": False,
            "notes": [
                "Preflight bundles are static operator evidence and do not execute benchmark cases.",
                "Raw campaign preflight folders can include local output, matrix, policy, and dry-run command paths for operator handoff.",
                "The embedded implementation-status artifact redacts project-root and local file evidence paths.",
                "manifest.review_summary is the compact no-local-path summary intended for external evidence indexes and dashboard review.",
                "For external publication, route campaign preflight evidence through release qualification bundles, evidence indexes, dashboard summaries, or an explicit redaction review.",
                "Provider audit output is redacted and contains secret reference metadata only.",
                "Benchmark readiness summaries include redacted provider-auth posture by backend kind only.",
                "Policy files are included only when explicitly supplied and are expected to be reviewed governance artifacts.",
            ],
        },
    }


def _review_summary(
    *,
    matrices: list[dict[str, Any]],
    includes_provider_audit: bool,
    includes_benchmark_readiness: bool,
    benchmark_readiness_report_count: int,
) -> dict[str, Any]:
    return {
        "schema_version": "agentblaster.campaign-preflight-review-summary.v1",
        "matrix_count": len(matrices),
        "run_count": sum(_int(matrix.get("run_count")) for matrix in matrices),
        "total_cases": sum(_int(matrix.get("total_cases")) for matrix in matrices),
        "matrices": [
            {
                "matrix": matrix.get("matrix"),
                "artifact_path": matrix.get("artifact_path"),
                "pressure_artifact_path": matrix.get("pressure_artifact_path"),
                "run_count": _int(matrix.get("run_count")),
                "total_cases": _int(matrix.get("total_cases")),
                "engine_targets": list(matrix.get("engine_targets") or []),
            }
            for matrix in matrices
        ],
        "includes_provider_audit": includes_provider_audit,
        "includes_benchmark_readiness": includes_benchmark_readiness,
        "benchmark_readiness_report_count": benchmark_readiness_report_count,
        "security": {
            "contains_local_paths": False,
            "contains_raw_secrets": False,
            "contains_raw_provider_payloads": False,
            "contains_raw_traces": False,
            "external_publication_safe": True,
            "notes": "Compact campaign preflight summary only; local matrix paths, policy paths, output paths, dry-run commands, and source report paths are excluded.",
        },
    }


def _redacted_implementation_status(project_root: Path) -> dict[str, Any]:
    payload = _redact_local_paths(build_implementation_status(project_root=project_root))
    if not isinstance(payload, dict):
        raise ConfigError("implementation status builder returned a non-object payload")
    payload["project_root"] = "<redacted>"
    payload["project_root_redacted"] = True
    security_notes = payload.get("security_notes")
    note = "Campaign preflight redacts local project-root and file evidence paths from the embedded implementation-status artifact."
    if isinstance(security_notes, list):
        if note not in security_notes:
            security_notes.append(note)
    else:
        payload["security_notes"] = [note]
    return payload


def _redact_local_paths(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _redact_local_paths(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_local_paths(item) for item in value]
    if isinstance(value, str) and _looks_like_local_path(value):
        return "<redacted-path>"
    return value


def _looks_like_local_path(value: str) -> bool:
    stripped = value.strip()
    normalized = stripped.replace("\\", "/")
    if normalized.startswith(("/", "~/")):
        return True
    return len(normalized) >= 3 and normalized[1] == ":" and normalized[2] == "/"


def _benchmark_readiness_index(paths: list[Path]) -> dict[str, Any]:
    reports = [_benchmark_readiness_summary(path) for path in paths]
    return {
        "schema_version": "agentblaster.campaign-preflight-benchmark-readiness-index.v1",
        "report_count": len(reports),
        "reports": reports,
        "security": {
            "contacts_providers": False,
            "resolves_secrets": False,
            "reads_keyring_values": False,
            "contains_raw_secrets": False,
            "contains_raw_provider_payloads": False,
            "contains_raw_traces": False,
            "notes": "Contains compact summaries from benchmark readiness dossiers only; raw provider configs, API keys, prompts, traces, and endpoint payloads are excluded.",
        },
    }


def _benchmark_readiness_summary(path: Path) -> dict[str, Any]:
    try:
        data = path.read_bytes()
        payload = json.loads(data.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"invalid benchmark readiness report {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConfigError(f"benchmark readiness report root must be an object: {path}")
    schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema")) if value is not None}
    if READINESS_SCHEMA_VERSION not in schema_values:
        found = ", ".join(sorted(schema_values)) if schema_values else "none"
        raise ConfigError(f"expected benchmark readiness schema {READINESS_SCHEMA_VERSION} in {path}, found {found}")
    report_summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "source_path": path.name,
        "source_name": path.name,
        "source_path_redacted": True,
        "source_sha256": sha256(data).hexdigest(),
        "schema_version": READINESS_SCHEMA_VERSION,
        "provider": payload.get("provider"),
        "suite": payload.get("suite"),
        "model": payload.get("model"),
        "ready": payload.get("ready") if isinstance(payload.get("ready"), bool) else None,
        "strict_unknown": payload.get("strict_unknown") if isinstance(payload.get("strict_unknown"), bool) else None,
        "policy_ok": report_summary.get("policy_ok") if isinstance(report_summary.get("policy_ok"), bool) else None,
        "suite_compatible": report_summary.get("suite_compatible") if isinstance(report_summary.get("suite_compatible"), bool) else None,
        "contract_checks_planned": _int(report_summary.get("contract_checks_planned")),
        "contract_capabilities_directly_checked": _int(report_summary.get("contract_capabilities_directly_checked")),
        "contract_capabilities_proxy_checked": _int(report_summary.get("contract_capabilities_proxy_checked")),
        "contract_capabilities_not_covered": _int(report_summary.get("contract_capabilities_not_covered")),
        "metric_coverage_score": report_summary.get("metric_coverage_score"),
        "provider_auth_writable_backends": _int(report_summary.get("provider_auth_writable_backends")),
        "provider_auth_plaintext_fallbacks": _int(report_summary.get("provider_auth_plaintext_fallbacks")),
        "provider_auth_prewrite_policy_guards_recommended": _int(
            report_summary.get("provider_auth_prewrite_policy_guards_recommended")
        ),
        "blocking_findings": _int(report_summary.get("blocking_findings")),
        "warnings": _int(report_summary.get("warnings")),
        "provider_auth_posture": _compact_provider_auth_posture(payload.get("provider_auth_posture")),
    }


def _compact_provider_auth_posture(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    posture = []
    for item in value:
        if not isinstance(item, dict):
            continue
        posture.append(
            {
                "provider": item.get("provider"),
                "api_key_ref_kind": item.get("api_key_ref_kind"),
                "api_key_ref_configured": bool(item.get("api_key_ref_configured")),
                "api_key_ref_writable_backend": bool(item.get("api_key_ref_writable_backend")),
                "api_key_ref_plaintext_fallback": bool(item.get("api_key_ref_plaintext_fallback")),
                "prewrite_policy_guard_recommended": bool(item.get("prewrite_policy_guard_recommended")),
            }
        )
    return posture[:12]


def _policy_payload(policy: Path | None) -> dict[str, Any] | None:
    if policy is None:
        return None
    try:
        raw = policy.read_bytes()
    except OSError as exc:
        raise ConfigError(f"unable to read policy file {policy}: {exc}") from exc
    return {
        "raw": raw,
        "normalized": _model_payload(load_policy(policy)),
    }


def _packaging_readiness(project_root: Path) -> dict[str, Any]:
    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        raise ConfigError(f"pyproject.toml not found at project root: {project_root}")
    try:
        pyproject_data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"invalid pyproject.toml at {pyproject}: {exc}") from exc
    return build_packaging_readiness(pyproject_data, project_root=project_root)


def _write_artifacts(output_dir: Path, artifacts: dict[Path, bytes]) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    _remove_stale_generated_artifacts(output_dir, artifacts)
    written: list[Path] = []
    for relative_path, data in sorted(artifacts.items(), key=lambda item: str(item[0])):
        destination = output_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        written.append(destination)
    return written


def _remove_stale_generated_artifacts(output_dir: Path, artifacts: dict[Path, bytes]) -> None:
    expected = set(artifacts)
    optional_paths = {
        Path("readiness/benchmark-readiness-index.json"),
        Path("providers/provider-audit.json"),
        Path("policy/policy-normalized.json"),
        Path("policy/policy.yaml"),
    }
    for relative_path in sorted(optional_paths - expected):
        path = output_dir / relative_path
        if path.exists() and path.is_file():
            path.unlink()
    generated_patterns = {
        Path("matrices"): ("*-inventory.json", "index.json"),
        Path("pressure"): ("*-pressure.json",),
    }
    for relative_dir, patterns in generated_patterns.items():
        directory = output_dir / relative_dir
        if not directory.is_dir():
            continue
        for pattern in patterns:
            for path in directory.glob(pattern):
                relative_path = path.relative_to(output_dir)
                if relative_path not in expected and path.is_file():
                    path.unlink()
    for relative_dir in (Path("providers"), Path("policy"), Path("matrices"), Path("pressure")):
        directory = output_dir / relative_dir
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()


def _runbook(matrices: list[dict[str, Any]], *, policy: Path | None) -> str:
    lines = [
        "# AgentBlaster Campaign Preflight Bundle",
        "",
        "This folder is a no-dispatch campaign readiness package. It does not contact providers, resolve secrets, execute tools, or create run artifacts.",
        "",
        "## Included Evidence",
        "",
        "- `manifest.json`: checksum index and security posture.",
        "- `readiness/environment-readiness.json`: static local runtime readiness.",
        "- `readiness/implementation-status.json`: static implementation, harness-engineering suite, and stats-comparability inventory.",
        "- `readiness/packaging-readiness.json`: static package metadata readiness.",
        "- `readiness/benchmark-readiness-index.json`: optional compact benchmark readiness summaries when supplied.",
        "- `catalogs/artifact-schemas.json`: artifact schema registry for downstream review.",
        "- `matrices/index.json`: campaign matrix inventory index.",
        "- `pressure/*.json`: static matrix pressure audits for prompt, prefill, and concurrency review.",
        "- `providers/provider-audit.json`: optional redacted provider audit when requested.",
        "- `policy/policy-normalized.json`: normalized policy when a policy file is supplied.",
        "",
        "## Next No-Dispatch Step",
        "",
    ]
    for matrix in matrices:
        lines.extend(
            [
                f"### {matrix['matrix']}",
                "",
                "```bash",
                " ".join(matrix["dry_run_command"]),
                "```",
                "",
            ]
        )
    if policy is not None:
        lines.extend(
            [
                "## Policy",
                "",
                f"This bundle was generated with `{policy}`. Treat policy files as reviewed governance artifacts and do not place raw secrets in them.",
                "",
            ]
        )
    lines.extend(
        [
            "## Publication Guidance",
            "",
            "Review this folder before running costly local or remote campaign matrices. Do not publish the raw folder externally without redaction review because manifest entries and dry-run commands can include local operator paths. After execution, pair it with matrix summaries, scorecards, gates, release provenance, evidence indexes, release qualification bundles, and a redaction scan before publishing claims.",
            "",
        ]
    )
    return "\n".join(lines)


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _markdown_bytes(markdown: str) -> bytes:
    return markdown.encode("utf-8")


def _model_payload(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _unique_matrix_artifact_name(index: int, matrix_name: str, used: set[str]) -> str:
    stem = f"{index:03d}-{_safe_id(matrix_name)}"
    candidate = f"{stem}-inventory.json"
    suffix = 2
    while candidate in used:
        candidate = f"{stem}-{suffix}-inventory.json"
        suffix += 1
    used.add(candidate)
    return candidate


def _safe_id(name: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in name).strip("-") or "campaign"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
