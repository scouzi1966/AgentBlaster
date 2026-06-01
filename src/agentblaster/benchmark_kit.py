from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentblaster.model_catalog import generate_matrix_template, matrix_to_yaml
from agentblaster.models import RawTraceMode

DEFAULT_KIT_TARGETS = ["qwen3.6-27b-dense", "gemma-4-31b-dense"]
DEFAULT_KIT_PROVIDERS = ["afm", "lm-studio"]


@dataclass(frozen=True)
class BenchmarkKit:
    output_dir: Path
    manifest_path: Path
    matrix_path: Path
    runbook_path: Path
    readiness_dir: Path
    report_dir: Path


def create_benchmark_kit(
    output_dir: Path,
    *,
    providers: list[str] | None = None,
    targets: list[str] | None = None,
    suite: str = "trace-replay",
    concurrency: int = 1,
    policy: Path | None = None,
    name: str | None = None,
    overwrite: bool = False,
) -> BenchmarkKit:
    provider_names = _clean_list(providers or DEFAULT_KIT_PROVIDERS)
    target_ids = _clean_list(targets or DEFAULT_KIT_TARGETS)
    if not provider_names:
        raise ValueError("benchmark kit requires at least one provider")
    if not target_ids:
        raise ValueError("benchmark kit requires at least one target")

    output_dir = output_dir.expanduser()
    _prepare_output_dir(output_dir, overwrite=overwrite)
    output_dir.mkdir(parents=True, exist_ok=True)
    readiness_dir = output_dir / "readiness"
    report_dir = output_dir / "reports"
    readiness_dir.mkdir(exist_ok=True)
    report_dir.mkdir(exist_ok=True)
    matrix_dir = output_dir / "matrices"
    matrix_dir.mkdir(exist_ok=True)

    kit_name = name or _kit_name(suite, provider_names, target_ids)
    matrix = generate_matrix_template(
        providers=provider_names,
        target_ids=target_ids,
        suite=suite,
        concurrency=concurrency,
        raw_traces=RawTraceMode.REDACTED,
        no_raw_traces=True,
        name=kit_name,
        description=f"AgentBlaster benchmark kit matrix for {suite} across {', '.join(provider_names)}.",
    )
    matrix_path = matrix_dir / f"{kit_name}.yaml"
    matrix_path.write_text(matrix_to_yaml(matrix), encoding="utf-8")

    runbook_path = output_dir / "RUNBOOK.md"
    runbook_path.write_text(
        _runbook(
            kit_name=kit_name,
            providers=provider_names,
            targets=target_ids,
            suite=suite,
            concurrency=concurrency,
            matrix_path=matrix_path,
            readiness_dir=readiness_dir,
            report_dir=report_dir,
            policy=policy,
        ),
        encoding="utf-8",
    )
    manifest_path = output_dir / "benchmark-kit.json"
    manifest = _manifest(
        kit_name=kit_name,
        providers=provider_names,
        targets=target_ids,
        suite=suite,
        concurrency=concurrency,
        policy=policy,
        matrix_path=matrix_path,
        runbook_path=runbook_path,
        readiness_dir=readiness_dir,
        report_dir=report_dir,
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return BenchmarkKit(
        output_dir=output_dir,
        manifest_path=manifest_path,
        matrix_path=matrix_path,
        runbook_path=runbook_path,
        readiness_dir=readiness_dir,
        report_dir=report_dir,
    )


def _prepare_output_dir(output_dir: Path, *, overwrite: bool) -> None:
    if not output_dir.exists():
        return
    known = {"benchmark-kit.json", "RUNBOOK.md", "matrices", "readiness", "reports"}
    unknown = [path.name for path in output_dir.iterdir() if path.name not in known]
    if unknown:
        raise ValueError("benchmark kit output directory contains non-kit entries: " + ", ".join(sorted(unknown)[:5]))
    if not overwrite and any(output_dir.iterdir()):
        raise ValueError("benchmark kit output already exists; pass --overwrite to replace kit artifacts")
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


def _manifest(
    *,
    kit_name: str,
    providers: list[str],
    targets: list[str],
    suite: str,
    concurrency: int,
    policy: Path | None,
    matrix_path: Path,
    runbook_path: Path,
    readiness_dir: Path,
    report_dir: Path,
) -> dict[str, Any]:
    readiness_commands = []
    for provider in providers:
        for target in targets:
            model_ref = _default_model_ref(target)
            readiness_path = readiness_dir / f"{provider}-{target}-readiness.json"
            command = [
                "agentblaster",
                "providers",
                "readiness",
                "--provider",
                provider,
                "--suite",
                suite,
                "--model",
                model_ref,
                "--strict-unknown",
                "--output-json",
                str(readiness_path),
            ]
            if policy is not None:
                command.extend(["--policy", str(policy)])
            readiness_commands.append({"provider": provider, "target": target, "output": str(readiness_path), "command": command})
    matrix_summary = report_dir / f"{kit_name}-matrix-summary.json"
    return {
        "schema_version": "agentblaster.benchmark-kit.v1",
        "name": kit_name,
        "suite": suite,
        "providers": providers,
        "targets": targets,
        "concurrency": concurrency,
        "policy": str(policy) if policy else None,
        "matrix_path": str(matrix_path),
        "runbook_path": str(runbook_path),
        "readiness_dir": str(readiness_dir),
        "report_dir": str(report_dir),
        "readiness_commands": readiness_commands,
        "matrix_commands": {
            "dry_run": [
                "agentblaster",
                "run",
                "--matrix",
                str(matrix_path),
                "--offline",
                "--dry-run",
            ],
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
                str(report_dir / f"{kit_name}-matrix-gate.json"),
            ],
        },
        "safety": {
            "generates_only_files": True,
            "contacts_providers": False,
            "raw_traces_disabled_in_matrix": True,
            "offline_commands_default": True,
        },
    }


def _runbook(
    *,
    kit_name: str,
    providers: list[str],
    targets: list[str],
    suite: str,
    concurrency: int,
    matrix_path: Path,
    readiness_dir: Path,
    report_dir: Path,
    policy: Path | None,
) -> str:
    policy_part = f" --policy {policy}" if policy else ""
    lines = [
        f"# AgentBlaster Benchmark Kit: {kit_name}",
        "",
        f"Suite: `{suite}`",
        f"Providers: `{', '.join(providers)}`",
        f"Targets: `{', '.join(targets)}`",
        f"Concurrency: `{concurrency}`",
        "",
        "## 1. Generate readiness dossiers",
        "",
        "Run these before dispatch. They do not contact providers.",
        "",
    ]
    for provider in providers:
        for target in targets:
            model_ref = _default_model_ref(target)
            readiness_path = readiness_dir / f"{provider}-{target}-readiness.json"
            lines.extend(
                [
                    "```bash",
                    f"agentblaster providers readiness --provider {provider} --suite {suite} --model {model_ref}{policy_part} --strict-unknown --output-json {readiness_path}",
                    "```",
                    "",
                ]
            )
    matrix_summary = report_dir / f"{kit_name}-matrix-summary.json"
    lines.extend(
        [
            "## 2. Dry-run the matrix",
            "",
            "```bash",
            f"agentblaster run --matrix {matrix_path} --offline --dry-run",
            "```",
            "",
            "## 3. Execute the matrix",
            "",
            "```bash",
            f"agentblaster run --matrix {matrix_path} --offline --continue-on-error --matrix-summary-json {matrix_summary}",
            "```",
            "",
            "## 4. Generate reports and gate results",
            "",
            "```bash",
            f"agentblaster matrix report {matrix_summary} --format html,md,json",
            f"agentblaster matrix gate {matrix_summary} --require-all-runs-complete --max-failed-runs 0 --min-case-pass-rate 95 --output-json {report_dir / (kit_name + '-matrix-gate.json')}",
            "```",
            "",
            "## Safety",
            "",
            "This kit generation step writes files only. The generated matrix disables raw traces and the run commands default to `--offline`.",
        ]
    )
    return "\n".join(lines) + "\n"


def _default_model_ref(target: str) -> str:
    if target == "qwen3.6-27b-dense":
        return "mlx-community/Qwen3.6-27B"
    if target == "gemma-4-31b-dense":
        return "google/gemma-4-31b"
    return target


def _kit_name(suite: str, providers: list[str], targets: list[str]) -> str:
    provider_part = "providers" if len(providers) > 2 else "-".join(_slug(provider) for provider in providers)
    target_part = "models" if len(targets) > 2 else "-".join(_slug(target) for target in targets)
    return _slug(f"{suite}-{provider_part}-{target_part}-kit")[:96]


def _slug(value: str) -> str:
    return "".join(character if character.isalnum() or character in {"-", "."} else "-" for character in value).strip("-")


def _clean_list(values: list[str]) -> list[str]:
    return [value.strip() for value in values if value.strip()]
