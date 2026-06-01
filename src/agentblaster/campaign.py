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
DEFAULT_CAMPAIGN_SUITES = [
    "smoke",
    "structured",
    "toolcall",
    "toolsim",
    "trace-replay",
    "agentic-tool-loop",
    "agent-fanout",
    "prefill",
    "cache-control",
    "cancellation",
    "lcp-context",
]


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
    readiness_input_list_path = Path(manifest["readiness_input_list_path"])
    readiness_input_list_path.write_text(
        "".join(
            f"{_list_relative_path(path, readiness_input_list_path.parent)}\n"
            for path in manifest["publication_artifacts"]["benchmark_readiness_reports"]
        ),
        encoding="utf-8",
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
    contract_matrix_plan = report_dir / f"{name}-provider-contract-matrix-plan.json"
    contract_matrix = report_dir / f"{name}-provider-contract-matrix.json"
    readiness_input_list = report_dir / "benchmark-readiness-inputs.txt"
    campaign_preflight_dir = report_dir / "campaign-preflight"
    experiment_manifest = report_dir / f"{name}-experiment.json"
    experiment_gate = report_dir / f"{name}-experiment-gate.json"
    matrix_pressure = report_dir / f"{name}-matrix-pressure.json"
    matrix_saturation = report_dir / f"{name}-matrix-saturation.json"
    release_provenance = report_dir / "release-provenance.json"
    selftest_run_id = f"{_slug(name)}-selftest"
    selftest_base_dir = report_dir / "selftest"
    selftest_report = selftest_base_dir / selftest_run_id / "selftest-report.json"
    sdlc_validation_manifest = report_dir / "sdlc-validation-manifest.json"
    suite_audit_reports = [
        (suite, report_dir / f"{_slug(suite)}-suite-audit.json")
        for suite in suites
    ]
    suite_audit_args = [
        argument
        for _suite, path in suite_audit_reports
        for argument in ("--suite-audit", str(path))
    ]
    suite_audit_artifact_args = [
        argument
        for _suite, path in suite_audit_reports
        for argument in ("--artifact", str(path))
    ]
    harness_review_reports = [
        (suite, report_dir / f"{_slug(suite)}-harness-review.json")
        for suite in suites
    ]
    harness_review_args = [
        argument
        for _suite, path in harness_review_reports
        for argument in ("--harness-review", str(path))
    ]
    harness_review_artifact_args = [
        argument
        for _suite, path in harness_review_reports
        for argument in ("--artifact", str(path))
    ]
    suite_calibration_templates = [
        (suite, report_dir / f"{_slug(suite)}-calibration.json")
        for suite in suites
    ]
    suite_calibration_reports = [
        (suite, report_dir / f"{_slug(suite)}-calibration-report.json")
        for suite in suites
    ]
    suite_calibration_report_args = [
        argument
        for _suite, path in suite_calibration_reports
        for argument in ("--suite-calibration-report", str(path))
    ]
    suite_calibration_artifact_args = [
        argument
        for _suite, path in suite_calibration_reports
        for argument in ("--artifact", str(path))
    ]
    metric_coverage_reports = [
        (provider, report_dir / f"{_slug(provider)}-metric-coverage.json")
        for provider in providers
    ]
    metric_coverage_args = [
        argument
        for _provider, path in metric_coverage_reports
        for argument in ("--metric-coverage", str(path))
    ]
    metric_coverage_artifact_args = [
        argument
        for _provider, path in metric_coverage_reports
        for argument in ("--artifact", str(path))
    ]
    engine_advisories = [
        (provider, report_dir / f"{_slug(provider)}-improvement-plan.json")
        for provider in providers
    ]
    engine_advisory_args = [
        argument
        for _provider, path in engine_advisories
        for argument in ("--engine-advisory", str(path))
    ]
    engine_advisory_artifact_args = [
        argument
        for _provider, path in engine_advisories
        for argument in ("--artifact", str(path))
    ]
    evidence_index = report_dir / f"{name}-evidence-index.json"
    release_bundle = report_dir / "release-bundles" / f"{name}.agentblaster-release-qualification.zip"
    redaction_scan = report_dir / f"{name}-redaction-scan.json"
    claim_readiness = report_dir / f"{name}-claim-readiness.json"
    publication_brief_json = report_dir / f"{name}-publication-brief.json"
    publication_brief_md = report_dir / f"{name}-publication-brief.md"
    publication_archive_bundle = report_dir / "release-bundles" / f"{name}-publication.agentblaster-release-qualification.zip"
    retention_cleanup_plan = report_dir / f"{name}-retention-cleanup-plan.json"
    manual_cleanup_plan = report_dir / f"{name}-manual-cleanup-plan.json"
    cleanup_audit_log = report_dir / f"{name}-cleanup-audit.jsonl"
    policy_args = ["--policy", str(policy)] if policy is not None else []
    experiment_gate_policy_args = ["--require-policy"] if policy is not None else []
    implementation_status = report_dir / "implementation-status.json"
    readiness_commands = [
        {
            "provider": provider,
            "target": target,
            "suite": suite,
            "output": str(report_dir / "readiness" / f"{provider}-{target}-{suite}-readiness.json"),
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
    readiness_outputs = [item["output"] for item in readiness_commands]
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
        "readiness_input_list_path": str(readiness_input_list),
        "matrix_run_count": len(providers) * len(targets) * len(suites),
        "readiness_commands": readiness_commands,
        "campaign_preflight_command": [
            "agentblaster",
            "evidence",
            "campaign-preflight",
            "--matrix",
            str(matrix_path),
            *policy_args,
            "--benchmark-readiness-list",
            str(readiness_input_list),
            "--output-dir",
            str(campaign_preflight_dir),
        ],
        "preflight_commands": {
            "engine_targets": ["agentblaster", "engines", "targets", "--format", "json", "--output", str(report_dir / "engine-targets.json")],
            "workflow_surfaces": ["agentblaster", "catalog", "workflow-surfaces", "--format", "json", "--output", str(report_dir / "workflow-surfaces.json")],
            "telemetry_mappings": ["agentblaster", "catalog", "telemetry-mappings", "--format", "json", "--output", str(report_dir / "telemetry-mappings.json")],
            "implementation_status": ["agentblaster", "implementation-status", "--output-json", str(implementation_status)],
            "provider_audit": ["agentblaster", "providers", "audit", *policy_args, "--output-json", str(report_dir / "provider-audit.json")],
        },
        "matrix_commands": {
            "dry_run": ["agentblaster", "run", "--matrix", str(matrix_path), "--offline", "--dry-run"],
            "contract_plan": [
                "agentblaster",
                "matrix",
                "contract-checks",
                str(matrix_path),
                "--output-json",
                str(contract_matrix_plan),
            ],
            "contract_execute": [
                "agentblaster",
                "matrix",
                "contract-checks",
                str(matrix_path),
                "--execute",
                "--output-json",
                str(contract_matrix),
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
            "report": ["agentblaster", "matrix", "report", str(matrix_summary), "--format", "html,md,json,pdf"],
            "scorecard": ["agentblaster", "matrix", "scorecard", str(matrix_summary), "--format", "html,md,json,card,png,pdf"],
            "publication_bundle": [
                "agentblaster",
                "matrix",
                "publication-bundle",
                str(matrix_summary),
                "--output-dir",
                str(report_dir / "publication-bundles"),
            ],
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
                "--max-failure-class",
                "engine_protocol_bug=0",
                "--max-tool-loop-stop-reason",
                "max_tool_calls_reached=0",
                "--output-json",
                str(report_dir / f"{name}-matrix-gate.json"),
            ],
        },
        "publication_commands": {
            "experiment_manifest": [
                "agentblaster",
                "experiment",
                "manifest",
                "--name",
                name,
                "--objective",
                f"Compare {', '.join(providers)} across {', '.join(targets)} on {', '.join(suites)}.",
                "--providers",
                ",".join(providers),
                "--targets",
                ",".join(targets),
                "--suites",
                ",".join(suites),
                *policy_args,
                "--matrix",
                str(matrix_path),
                "--output",
                str(experiment_manifest),
            ],
            "experiment_gate": [
                "agentblaster",
                "experiment",
                "gate",
                str(experiment_manifest),
                *experiment_gate_policy_args,
                "--output-json",
                str(experiment_gate),
            ],
            "matrix_pressure_audit": [
                "agentblaster",
                "matrix",
                "pressure-audit",
                str(matrix_path),
                "--output-json",
                str(matrix_pressure),
            ],
            "matrix_saturation_report": [
                "agentblaster",
                "matrix",
                "saturation-report",
                str(matrix_summary),
                "--output-json",
                str(matrix_saturation),
            ],
            "metric_coverage": [
                [
                    "agentblaster",
                    "providers",
                    "metric-coverage",
                    "--provider",
                    provider,
                    "--output-json",
                    str(path),
                ]
                for provider, path in metric_coverage_reports
            ],
            "release_provenance": ["agentblaster", "release", "provenance", "--output", str(release_provenance)],
            "selftest": [
                "agentblaster",
                "selftest",
                "--tier",
                "normal",
                "--report-dir",
                str(selftest_base_dir),
                "--run-id",
                selftest_run_id,
            ],
            "selftest_report": [
                "agentblaster",
                "selftest",
                "report",
                "--run",
                selftest_run_id,
                "--base-dir",
                str(selftest_base_dir),
                "--format",
                "html,json,junit",
            ],
            "sdlc_validation_manifest": [
                "agentblaster",
                "quality",
                "validation-manifest",
                "--format",
                "json",
                "--output",
                str(sdlc_validation_manifest),
                "--name",
                name,
            ],
            "retention_cleanup_plan": [
                "agentblaster",
                "cleanup-expired",
                "--runs",
                "runs",
                *policy_args,
                "--output-json",
                str(retention_cleanup_plan),
                "--audit-log",
                str(cleanup_audit_log),
                "--require-audit-log",
            ],
            "manual_cleanup_plan_template": [
                "agentblaster",
                "cleanup",
                "runs/<run-id>",
                "--raw",
                "--reports",
                "--exports",
                "--caches",
                "--temp",
                "--bundles",
                *policy_args,
                "--output-json",
                str(manual_cleanup_plan),
                "--audit-log",
                str(cleanup_audit_log),
                "--require-audit-log",
            ],
            "suite_audits": [
                _suite_audit_command(suite, path)
                for suite, path in suite_audit_reports
            ],
            "harness_reviews": [
                _harness_review_command(suite, path)
                for suite, path in harness_review_reports
            ],
            "suite_calibration_templates": [
                _suite_calibration_template_command(suite, path)
                for suite, path in suite_calibration_templates
            ],
            "suite_calibration_reports": [
                _suite_calibration_report_command(suite, template, report)
                for (suite, template), (_same_suite, report) in zip(suite_calibration_templates, suite_calibration_reports)
            ],
            "engine_advisories": [
                [
                    "agentblaster",
                    "engines",
                    "improvement-plan",
                    "--engine",
                    provider,
                    "--pressure-audit",
                    str(matrix_pressure),
                    "--matrix-saturation-report",
                    str(matrix_saturation),
                    "--provider-contract-matrix",
                    str(contract_matrix),
                    "--matrix-gate",
                    str(report_dir / f"{name}-matrix-gate.json"),
                    *harness_review_args,
                    *metric_coverage_args,
                    "--output-json",
                    str(path),
                ]
                for provider, path in engine_advisories
            ],
            "evidence_index": [
                "agentblaster",
                "evidence",
                "index",
                "--name",
                name,
                "--artifact",
                str(experiment_gate),
                "--artifact",
                str(report_dir / "provider-audit.json"),
                "--artifact",
                str(contract_matrix),
                "--artifact",
                str(report_dir / f"{name}-matrix-gate.json"),
                "--artifact",
                str(report_dir / f"{name}-matrix-summary-matrix-scorecard.json"),
                "--artifact",
                str(matrix_pressure),
                "--artifact",
                str(matrix_saturation),
                "--artifact",
                str(campaign_preflight_dir / "manifest.json"),
                "--artifact",
                str(campaign_preflight_dir / "readiness" / "benchmark-readiness-index.json"),
                "--artifact",
                str(release_provenance),
                "--artifact",
                str(retention_cleanup_plan),
                "--artifact",
                str(selftest_report),
                "--artifact",
                str(sdlc_validation_manifest),
                *suite_audit_artifact_args,
                *harness_review_artifact_args,
                *suite_calibration_artifact_args,
                *metric_coverage_artifact_args,
                *engine_advisory_artifact_args,
                "--output-json",
                str(evidence_index),
            ],
            "qualification_bundle": [
                "agentblaster",
                "release",
                "qualification-bundle",
                "--name",
                name,
                "--provider-audit",
                str(report_dir / "provider-audit.json"),
                "--provider-contract-matrix",
                str(contract_matrix),
                "--matrix-gate",
                str(report_dir / f"{name}-matrix-gate.json"),
                "--matrix-scorecard",
                str(report_dir / f"{name}-matrix-summary-matrix-scorecard.json"),
                "--matrix-pressure-audit",
                str(matrix_pressure),
                "--matrix-saturation-report",
                str(matrix_saturation),
                "--implementation-status",
                str(implementation_status),
                "--campaign-preflight-manifest",
                str(campaign_preflight_dir / "manifest.json"),
                "--benchmark-readiness-list",
                str(readiness_input_list),
                "--release-provenance",
                str(release_provenance),
                "--evidence-index",
                str(evidence_index),
                *suite_audit_args,
                *harness_review_args,
                *suite_calibration_report_args,
                *metric_coverage_args,
                *engine_advisory_args,
                "--selftest-report",
                str(selftest_report),
                "--sdlc-validation-manifest",
                str(sdlc_validation_manifest),
                "--matrix-publication-bundle",
                str(report_dir / "publication-bundles" / f"{name}-matrix-summary.agentblaster-matrix-publication.zip"),
                "--output-dir",
                str(report_dir / "release-bundles"),
            ],
            "redaction_scan": [
                "agentblaster",
                "security",
                "scan",
                str(release_bundle),
                "--output-json",
                str(redaction_scan),
            ],
            "claim_readiness": [
                "agentblaster",
                "release",
                "claim-readiness",
                "--name",
                name,
                "--experiment-manifest",
                str(experiment_manifest),
                "--experiment-gate",
                str(experiment_gate),
                "--provider-audit",
                str(report_dir / "provider-audit.json"),
                "--provider-contract-matrix",
                str(contract_matrix),
                "--matrix-gate",
                str(report_dir / f"{name}-matrix-gate.json"),
                "--matrix-scorecard",
                str(report_dir / f"{name}-matrix-summary-matrix-scorecard.json"),
                "--matrix-pressure-audit",
                str(matrix_pressure),
                "--matrix-saturation-report",
                str(matrix_saturation),
                "--implementation-status",
                str(implementation_status),
                "--benchmark-readiness-list",
                str(readiness_input_list),
                "--release-provenance",
                str(release_provenance),
                "--release-qualification-bundle",
                str(release_bundle),
                "--redaction-scan",
                str(redaction_scan),
                "--evidence-index",
                str(evidence_index),
                *suite_audit_args,
                *harness_review_args,
                *suite_calibration_report_args,
                *metric_coverage_args,
                *engine_advisory_args,
                "--selftest-report",
                str(selftest_report),
                "--matrix-publication-bundle",
                str(report_dir / "publication-bundles" / f"{name}-matrix-summary.agentblaster-matrix-publication.zip"),
                "--campaign-preflight-manifest",
                str(campaign_preflight_dir / "manifest.json"),
                "--output-json",
                str(claim_readiness),
            ],
            "publication_brief": [
                "agentblaster",
                "release",
                "publication-brief",
                "--name",
                name,
                "--claim-readiness",
                str(claim_readiness),
                "--matrix-scorecard",
                str(report_dir / f"{name}-matrix-summary-matrix-scorecard.json"),
                "--release-provenance",
                str(release_provenance),
                "--evidence-index",
                str(evidence_index),
                "--output-json",
                str(publication_brief_json),
                "--output-md",
                str(publication_brief_md),
            ],
            "publication_archive_bundle": [
                "agentblaster",
                "release",
                "qualification-bundle",
                "--name",
                f"{name}-publication",
                "--provider-audit",
                str(report_dir / "provider-audit.json"),
                "--provider-contract-matrix",
                str(contract_matrix),
                "--matrix-gate",
                str(report_dir / f"{name}-matrix-gate.json"),
                "--matrix-scorecard",
                str(report_dir / f"{name}-matrix-summary-matrix-scorecard.json"),
                "--matrix-pressure-audit",
                str(matrix_pressure),
                "--matrix-saturation-report",
                str(matrix_saturation),
                "--implementation-status",
                str(implementation_status),
                "--campaign-preflight-manifest",
                str(campaign_preflight_dir / "manifest.json"),
                "--benchmark-readiness-list",
                str(readiness_input_list),
                "--release-provenance",
                str(release_provenance),
                "--evidence-index",
                str(evidence_index),
                *suite_audit_args,
                *harness_review_args,
                *suite_calibration_report_args,
                *metric_coverage_args,
                *engine_advisory_args,
                "--selftest-report",
                str(selftest_report),
                "--sdlc-validation-manifest",
                str(sdlc_validation_manifest),
                "--matrix-publication-bundle",
                str(report_dir / "publication-bundles" / f"{name}-matrix-summary.agentblaster-matrix-publication.zip"),
                "--claim-readiness",
                str(claim_readiness),
                "--publication-brief",
                str(publication_brief_json),
                "--output-dir",
                str(report_dir / "release-bundles"),
            ],
        },
        "publication_artifacts": {
            "experiment_manifest": str(experiment_manifest),
            "experiment_gate": str(experiment_gate),
            "provider_contract_matrix": str(contract_matrix),
            "provider_contract_matrix_plan": str(contract_matrix_plan),
            "provider_audit": str(report_dir / "provider-audit.json"),
            "release_provenance": str(release_provenance),
            "implementation_status": str(implementation_status),
            "matrix_summary": str(matrix_summary),
            "matrix_report_json": str(report_dir / f"{name}-matrix-summary-matrix-report.json"),
            "matrix_scorecard_json": str(report_dir / f"{name}-matrix-summary-matrix-scorecard.json"),
            "matrix_scorecard_svg": str(report_dir / f"{name}-matrix-summary-matrix-scorecard.svg"),
            "matrix_scorecard_png": str(report_dir / f"{name}-matrix-summary-matrix-scorecard.png"),
            "matrix_scorecard_pdf": str(report_dir / f"{name}-matrix-summary-matrix-scorecard.pdf"),
            "matrix_pressure_audit": str(matrix_pressure),
            "matrix_saturation_report": str(matrix_saturation),
            "evidence_index": str(evidence_index),
            "selftest_report": str(selftest_report),
            "sdlc_validation_manifest": str(sdlc_validation_manifest),
            "retention_cleanup_plan": str(retention_cleanup_plan),
            "manual_cleanup_plan_template": str(manual_cleanup_plan),
            "suite_audits": [str(path) for _suite, path in suite_audit_reports],
            "harness_reviews": [str(path) for _suite, path in harness_review_reports],
            "suite_calibration_templates": [str(path) for _suite, path in suite_calibration_templates],
            "suite_calibration_reports": [str(path) for _suite, path in suite_calibration_reports],
            "metric_coverage_reports": [str(path) for _provider, path in metric_coverage_reports],
            "engine_advisories": [str(path) for _provider, path in engine_advisories],
            "matrix_publication_bundle": str(report_dir / "publication-bundles" / f"{name}-matrix-summary.agentblaster-matrix-publication.zip"),
            "matrix_gate": str(report_dir / f"{name}-matrix-gate.json"),
            "benchmark_readiness_reports": readiness_outputs,
            "benchmark_readiness_input_list": str(readiness_input_list),
            "campaign_preflight_manifest": str(campaign_preflight_dir / "manifest.json"),
            "campaign_preflight_benchmark_readiness_index": str(campaign_preflight_dir / "readiness" / "benchmark-readiness-index.json"),
            "release_qualification_bundle": str(release_bundle),
            "redaction_scan": str(redaction_scan),
            "claim_readiness": str(claim_readiness),
            "publication_brief_json": str(publication_brief_json),
            "publication_brief_md": str(publication_brief_md),
            "publication_archive_bundle": str(publication_archive_bundle),
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
    lines.append("The implementation-status path is listed in `publication_artifacts.implementation_status` for release qualification and claim-readiness `--implementation-status` inputs.")
    lines.append("The provider-audit path is listed in `publication_artifacts.provider_audit` for release qualification, claim-readiness, evidence-index, and dashboard review `--provider-audit` inputs.")
    lines.append("Readiness output paths are listed in `publication_artifacts.benchmark_readiness_reports` for single-artifact release qualification and claim-readiness `--benchmark-readiness` inputs.")
    lines.append("The generated `publication_artifacts.benchmark_readiness_input_list` file can be reused with `--benchmark-readiness-list` for campaign preflight, release qualification, and claim readiness.")
    lines.append("")
    lines.append("Build the campaign preflight bundle after readiness outputs exist. The generated `benchmark-readiness-inputs.txt` keeps large matrices readable.")
    lines.append("")
    lines.append(_command_block(manifest["campaign_preflight_command"]))
    lines.append("The campaign-preflight manifest path is listed in `publication_artifacts.campaign_preflight_manifest` for release qualification and claim-readiness `--campaign-preflight-manifest` inputs.")
    lines.append("")
    lines.extend(
        [
            "## 3. Matrix execution",
            "",
            _command_block(manifest["matrix_commands"]["contract_plan"]),
            _command_block(manifest["matrix_commands"]["contract_execute"]),
            _command_block(manifest["matrix_commands"]["dry_run"]),
            _command_block(manifest["matrix_commands"]["execute"]),
            "## 4. Reports, scorecards, and gates",
            "",
            _command_block(manifest["matrix_commands"]["report"]),
            _command_block(manifest["matrix_commands"]["scorecard"]),
            _command_block(manifest["matrix_commands"]["publication_bundle"]),
            _command_block(manifest["matrix_commands"]["gate"]),
            "## 5. Publication evidence skeleton",
            "",
            "These commands use generated campaign artifact paths. Add per-run telemetry audits, suite audits, selftest, evidence-index, and advisory artifacts when those are available for a full publication gate.",
            "",
            _command_block(manifest["publication_commands"]["experiment_manifest"]),
            _command_block(manifest["publication_commands"]["experiment_gate"]),
            _command_block(manifest["publication_commands"]["matrix_pressure_audit"]),
            _command_block(manifest["publication_commands"]["matrix_saturation_report"]),
            *[_command_block(command) for command in manifest["publication_commands"]["metric_coverage"]],
            _command_block(manifest["publication_commands"]["release_provenance"]),
            _command_block(manifest["publication_commands"]["selftest"]),
            _command_block(manifest["publication_commands"]["selftest_report"]),
            _command_block(manifest["publication_commands"]["sdlc_validation_manifest"]),
            "Generate lifecycle cleanup evidence before assembling the evidence index. The retention cleanup command is ready to run; replace `runs/<run-id>` in the manual cleanup template only when you need per-run cleanup evidence.",
            "",
            _command_block(manifest["publication_commands"]["retention_cleanup_plan"]),
            _command_block(manifest["publication_commands"]["manual_cleanup_plan_template"]),
            *[_command_block(command) for command in manifest["publication_commands"]["suite_audits"]],
            *[_command_block(command) for command in manifest["publication_commands"]["harness_reviews"]],
            "Complete calibration templates before running the strict calibration report commands below. Failed calibration reports block release-gate qualification when supplied.",
            "",
            *[_command_block(command) for command in manifest["publication_commands"]["suite_calibration_templates"]],
            *[_command_block(command) for command in manifest["publication_commands"]["suite_calibration_reports"]],
            *[_command_block(command) for command in manifest["publication_commands"]["engine_advisories"]],
            _command_block(manifest["publication_commands"]["evidence_index"]),
            _command_block(manifest["publication_commands"]["qualification_bundle"]),
            _command_block(manifest["publication_commands"]["redaction_scan"]),
            _command_block(manifest["publication_commands"]["claim_readiness"]),
            _command_block(manifest["publication_commands"]["publication_brief"]),
            "Create the final archival release bundle after claim readiness and publication brief exist. This second bundle includes the final claim-readiness report, publication brief, and SDLC validation manifest in compact redaction-safe form.",
            "",
            _command_block(manifest["publication_commands"]["publication_archive_bundle"]),
            "## Safety",
            "",
            "Campaign generation writes files only. Generated matrix runs disable raw traces and use `--offline` by default.",
            "",
        ]
    )
    return "\n".join(lines)


def _suite_audit_command(suite: str, output: Path) -> list[str]:
    suite_path = Path(suite)
    command = ["agentblaster", "suite-audit"]
    if suite_path.suffix.lower() in {".yaml", ".yml"} or "/" in suite or "\\" in suite:
        command.extend(["--suite-file", suite])
    else:
        command.extend(["--suite", suite])
    command.extend(["--output-json", str(output)])
    return command


def _harness_review_command(suite: str, output: Path) -> list[str]:
    suite_path = Path(suite)
    command = ["agentblaster", "harness", "review"]
    if suite_path.suffix.lower() in {".yaml", ".yml"} or "/" in suite or "\\" in suite:
        command.extend(["--suite-file", suite])
    else:
        command.extend(["--suite", suite])
    command.extend(["--output-json", str(output)])
    return command


def _suite_calibration_template_command(suite: str, output: Path) -> list[str]:
    command = ["agentblaster", "suite-calibration"]
    command.extend(_suite_selector_args(suite))
    command.extend(["--template-output", str(output)])
    return command


def _suite_calibration_report_command(suite: str, template: Path, output: Path) -> list[str]:
    command = ["agentblaster", "suite-calibration"]
    command.extend(_suite_selector_args(suite))
    command.extend(["--calibration", str(template), "--output-json", str(output)])
    return command


def _suite_selector_args(suite: str) -> list[str]:
    suite_path = Path(suite)
    if suite_path.suffix.lower() in {".yaml", ".yml"} or "/" in suite or "\\" in suite:
        return ["--suite-file", suite]
    return ["--suite", suite]


def _command_block(command: list[str]) -> str:
    return "```bash\n" + shlex.join(command) + "\n```\n"


def _list_relative_path(path: str, parent: Path) -> str:
    candidate = Path(path)
    try:
        return candidate.relative_to(parent).as_posix()
    except ValueError:
        return str(candidate)


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
