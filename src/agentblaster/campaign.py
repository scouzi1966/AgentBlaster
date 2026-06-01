from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentblaster.engine_targets import RECOMMENDED_MODEL_TARGETS
from agentblaster.matrix import MatrixDefinition, MatrixRun
from agentblaster.model_catalog import get_model_target, matrix_to_yaml
from agentblaster.models import RawTraceMode


DEFAULT_CAMPAIGN_PROVIDERS = ["afm", "mlx-lm", "ollama", "ollama-native", "lm-studio", "rapid-mlx", "omlx"]
DEFAULT_CAMPAIGN_TARGETS = list(RECOMMENDED_MODEL_TARGETS)
DEFAULT_CAMPAIGN_SUITES = ["smoke", "structured", "toolcall", "toolsim", "trace-replay", "prefill", "cache-control", "lcp-context"]


@dataclass(frozen=True)
class CampaignPlan:
    output_dir: Path
    manifest_path: Path
    matrix_path: Path
    runbook_path: Path
    report_dir: Path


def create_campaign_plan(
    output_dir: Path,
    *,
    providers: list[str] | None = None,
    targets: list[str] | None = None,
    suites: list[str] | None = None,
    concurrency: int = 1,
    policy: Path | None = None,
    name: str | None = None,
    overwrite: bool = False,
) -> CampaignPlan:
    provider_names = _clean_list(providers or DEFAULT_CAMPAIGN_PROVIDERS)
    target_ids = _clean_list(targets or DEFAULT_CAMPAIGN_TARGETS)
    suite_names = _clean_list(suites or DEFAULT_CAMPAIGN_SUITES)
    if not provider_names:
        raise ValueError("campaign plan requires at least one provider")
    if not target_ids:
        raise ValueError("campaign plan requires at least one target")
    if not suite_names:
        raise ValueError("campaign plan requires at least one suite")

    output_dir = output_dir.expanduser()
    _prepare_output_dir(output_dir, overwrite=overwrite)
    output_dir.mkdir(parents=True, exist_ok=True)
    matrix_dir = output_dir / "matrices"
    report_dir = output_dir / "reports"
    matrix_dir.mkdir(exist_ok=True)
    report_dir.mkdir(exist_ok=True)
    (report_dir / "readiness").mkdir(exist_ok=True)

    campaign_name = name or _campaign_name(provider_names, target_ids, suite_names)
    matrix = _campaign_matrix(
        name=campaign_name,
        providers=provider_names,
        targets=target_ids,
        suites=suite_names,
        concurrency=concurrency,
    )
    matrix_path = matrix_dir / f"{campaign_name}.yaml"
    matrix_path.write_text(matrix_to_yaml(matrix), encoding="utf-8")

    manifest_path = output_dir / "campaign-plan.json"
    manifest = _manifest(
        name=campaign_name,
        providers=provider_names,
        targets=target_ids,
        suites=suite_names,
        concurrency=concurrency,
        policy=policy,
        matrix_path=matrix_path,
        report_dir=report_dir,
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    runbook_path = output_dir / "RUNBOOK.md"
    runbook_path.write_text(_runbook(manifest), encoding="utf-8")

    return CampaignPlan(
        output_dir=output_dir,
        manifest_path=manifest_path,
        matrix_path=matrix_path,
        runbook_path=runbook_path,
        report_dir=report_dir,
    )


def campaign_plan_preview(
    *,
    output_dir: Path = Path("campaigns/qwen-gemma-local"),
    providers: list[str] | None = None,
    targets: list[str] | None = None,
    suites: list[str] | None = None,
    concurrency: int = 1,
    policy: Path | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    provider_names = _clean_list(providers or DEFAULT_CAMPAIGN_PROVIDERS)
    target_ids = _clean_list(targets or DEFAULT_CAMPAIGN_TARGETS)
    suite_names = _clean_list(suites or DEFAULT_CAMPAIGN_SUITES)
    if not provider_names:
        raise ValueError("campaign preview requires at least one provider")
    if not target_ids:
        raise ValueError("campaign preview requires at least one target")
    if not suite_names:
        raise ValueError("campaign preview requires at least one suite")
    if concurrency < 1:
        raise ValueError("campaign preview concurrency must be at least 1")

    output_dir = output_dir.expanduser()
    campaign_name = name or _campaign_name(provider_names, target_ids, suite_names)
    matrix_path = output_dir / "matrices" / f"{campaign_name}.yaml"
    report_dir = output_dir / "reports"
    manifest = _manifest(
        name=campaign_name,
        providers=provider_names,
        targets=target_ids,
        suites=suite_names,
        concurrency=concurrency,
        policy=policy,
        matrix_path=matrix_path,
        report_dir=report_dir,
    )
    manifest["schema_version"] = "agentblaster.campaign-preview.v1"
    manifest["output_dir"] = str(output_dir)
    manifest["runbook_path"] = str(output_dir / "RUNBOOK.md")
    manifest["write_command"] = [
        "agentblaster",
        "models",
        "campaign-plan",
        "--output-dir",
        str(output_dir),
        "--providers",
        ",".join(provider_names),
        "--targets",
        ",".join(target_ids),
        "--suites",
        ",".join(suite_names),
        "--concurrency",
        str(concurrency),
    ]
    if policy is not None:
        manifest["write_command"].extend(["--policy", str(policy)])
    if name is not None:
        manifest["write_command"].extend(["--name", name])
    manifest["safety"] = {
        **manifest["safety"],
        "writes_files": False,
        "preview_only": True,
    }
    return manifest


def _campaign_matrix(
    *,
    name: str,
    providers: list[str],
    targets: list[str],
    suites: list[str],
    concurrency: int,
) -> MatrixDefinition:
    runs: list[MatrixRun] = []
    for provider in providers:
        for target_id in targets:
            target = get_model_target(target_id)
            for suite in suites:
                runs.append(
                    MatrixRun(
                        engine=provider,
                        model=target.default_model,
                        suite=suite,
                        concurrency=concurrency,
                        raw_traces=RawTraceMode.REDACTED,
                        no_raw_traces=True,
                        model_metadata=target.metadata,
                    )
                )
    return MatrixDefinition(
        name=name,
        description=(
            "AgentBlaster canonical campaign matrix across providers, Qwen/Gemma targets, "
            "and baseline agentic suites."
        ),
        runs=runs,
    )


def _manifest(
    *,
    name: str,
    providers: list[str],
    targets: list[str],
    suites: list[str],
    concurrency: int,
    policy: Path | None,
    matrix_path: Path,
    report_dir: Path,
) -> dict[str, Any]:
    matrix_summary = report_dir / f"{name}-matrix-summary.json"
    policy_args = ["--policy", str(policy)] if policy is not None else []
    readiness_commands = [
        {
            "provider": provider,
            "target": target,
            "suite": suite,
            "command": [
                "agentblaster",
                "providers",
                "readiness",
                "--provider",
                provider,
                "--suite",
                suite,
                "--model",
                get_model_target(target).default_model,
                *policy_args,
                "--strict-unknown",
                "--output-json",
                str(report_dir / "readiness" / f"{provider}-{target}-{suite}-readiness.json"),
            ],
        }
        for provider in providers
        for target in targets
        for suite in suites
    ]
    return {
        "schema_version": "agentblaster.campaign-plan.v1",
        "name": name,
        "providers": providers,
        "targets": targets,
        "suites": suites,
        "concurrency": concurrency,
        "policy": str(policy) if policy else None,
        "matrix_path": str(matrix_path),
        "report_dir": str(report_dir),
        "matrix_run_count": len(providers) * len(targets) * len(suites),
        "readiness_commands": readiness_commands,
        "preflight_commands": {
            "engine_targets": ["agentblaster", "engines", "targets", "--format", "json", "--output", str(report_dir / "engine-targets.json")],
            "workflow_surfaces": ["agentblaster", "catalog", "workflow-surfaces", "--format", "json", "--output", str(report_dir / "workflow-surfaces.json")],
            "telemetry_mappings": ["agentblaster", "catalog", "telemetry-mappings", "--format", "json", "--output", str(report_dir / "telemetry-mappings.json")],
            "provider_audit": ["agentblaster", "providers", "audit", *policy_args, "--output-json", str(report_dir / "provider-audit.json")],
        },
        "matrix_commands": {
            "dry_run": ["agentblaster", "run", "--matrix", str(matrix_path), "--offline", "--dry-run"],
            "execute": [
                "agentblaster",
                "run",
                "--matrix",
                str(matrix_path),
                "--offline",
                "--continue-on-error",
                "--matrix-summary-json",
                str(matrix_summary),
            ],
            "report": ["agentblaster", "matrix", "report", str(matrix_summary), "--format", "html,md,json"],
            "scorecard": ["agentblaster", "matrix", "scorecard", str(matrix_summary), "--format", "html,md,json"],
            "gate": [
                "agentblaster",
                "matrix",
                "gate",
                str(matrix_summary),
                "--require-all-runs-complete",
                "--max-failed-runs",
                "0",
                "--min-case-pass-rate",
                "95",
                "--output-json",
                str(report_dir / f"{name}-matrix-gate.json"),
            ],
        },
        "publication_artifacts": {
            "matrix_summary": str(matrix_summary),
            "matrix_report_json": str(report_dir / f"{name}-matrix-summary-matrix-report.json"),
            "matrix_scorecard_json": str(report_dir / f"{name}-matrix-summary-matrix-scorecard.json"),
            "matrix_gate": str(report_dir / f"{name}-matrix-gate.json"),
        },
        "safety": {
            "generates_only_files": True,
            "contacts_providers": False,
            "stores_secrets": False,
            "raw_traces_disabled_in_matrix": True,
            "offline_commands_default": True,
        },
    }


def _runbook(manifest: dict[str, Any]) -> str:
    lines = [
        f"# AgentBlaster Campaign Plan: {manifest['name']}",
        "",
        f"Providers: `{', '.join(manifest['providers'])}`",
        f"Targets: `{', '.join(manifest['targets'])}`",
        f"Suites: `{', '.join(manifest['suites'])}`",
        f"Matrix runs: `{manifest['matrix_run_count']}`",
        "",
        "## 1. Static preflight catalogs",
        "",
        *[_command_block(command) for command in manifest["preflight_commands"].values()],
        "## 2. Readiness dossiers",
        "",
        "Generate readiness dossiers before provider dispatch. These commands are no-network.",
        "",
    ]
    for item in manifest["readiness_commands"][:12]:
        lines.append(_command_block(item["command"]))
    if len(manifest["readiness_commands"]) > 12:
        lines.append(f"Additional readiness commands are listed in `campaign-plan.json` ({len(manifest['readiness_commands'])} total).")
        lines.append("")
    lines.extend(
        [
            "## 3. Matrix execution",
            "",
            _command_block(manifest["matrix_commands"]["dry_run"]),
            _command_block(manifest["matrix_commands"]["execute"]),
            "## 4. Reports, scorecards, and gates",
            "",
            _command_block(manifest["matrix_commands"]["report"]),
            _command_block(manifest["matrix_commands"]["scorecard"]),
            _command_block(manifest["matrix_commands"]["gate"]),
            "## Safety",
            "",
            "Campaign generation writes files only. Generated matrix runs disable raw traces and use `--offline` by default.",
            "",
        ]
    )
    return "\n".join(lines)


def _command_block(command: list[str]) -> str:
    return "```bash\n" + shlex.join(command) + "\n```\n"


def _prepare_output_dir(output_dir: Path, *, overwrite: bool) -> None:
    if not output_dir.exists():
        return
    known = {"campaign-plan.json", "RUNBOOK.md", "matrices", "reports"}
    unknown = [path.name for path in output_dir.iterdir() if path.name not in known]
    if unknown:
        raise ValueError("campaign plan output directory contains non-campaign entries: " + ", ".join(sorted(unknown)[:5]))
    if not overwrite and any(output_dir.iterdir()):
        raise ValueError("campaign plan output already exists; pass --overwrite to replace campaign artifacts")
    if overwrite:
        for path in output_dir.iterdir():
            if path.is_dir():
                for child in sorted(path.rglob("*"), reverse=True):
                    if child.is_file() or child.is_symlink():
                        child.unlink()
                    elif child.is_dir():
                        child.rmdir()
                path.rmdir()
            else:
                path.unlink()


def _campaign_name(providers: list[str], targets: list[str], suites: list[str]) -> str:
    provider_part = "providers" if len(providers) > 2 else "-".join(_slug(provider) for provider in providers)
    target_part = "models" if len(targets) > 2 else "-".join(_slug(target) for target in targets)
    suite_part = "suites" if len(suites) > 2 else "-".join(_slug(suite) for suite in suites)
    return _slug(f"{provider_part}-{target_part}-{suite_part}-campaign")[:96]


def _slug(value: str) -> str:
    return "".join(character if character.isalnum() or character in {"-", "."} else "-" for character in value).strip("-")


def _clean_list(values: list[str]) -> list[str]:
    return [value.strip() for value in values if value.strip()]
