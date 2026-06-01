from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import re
import sys
from pathlib import Path
from typing import Annotated

import typer

from agentblaster.adapters import adapter_for
from agentblaster.agent_profiles import generate_agent_suite, list_agent_profiles, suite_to_yaml as agent_suite_to_yaml
from agentblaster.audit import AuditLogger
from agentblaster.benchmark_kit import create_benchmark_kit
from agentblaster.bundle import create_matrix_publication_bundle, create_publication_bundle, create_replay_bundle
from agentblaster.campaign import create_campaign_plan
from agentblaster.campaign_preflight import create_campaign_preflight_bundle, format_campaign_preflight_bundle
from agentblaster.capabilities import (
    CAPABILITY_DESCRIPTIONS,
    check_suite_compatibility,
    format_capability_report,
    suite_requirements,
)
from agentblaster.claim_readiness import build_claim_readiness, format_claim_readiness, write_claim_readiness_json
from agentblaster.publication_brief import (
    build_publication_brief,
    format_publication_brief,
    write_publication_brief_json,
    write_publication_brief_markdown,
)
from agentblaster.cleanup import (
    CLEANUP_PLAN_SCHEMA_VERSION,
    RETENTION_CLEANUP_SCHEMA_VERSION,
    apply_expired_cleanup,
    cleanup_run,
    plan_cleanup_run,
    plan_expired_cleanup,
)
from agentblaster.compare import (
    compare_runs,
    evaluate_comparison_gate,
    format_comparison_gate_report,
    format_comparison_table,
    write_comparison_gate_json,
    write_comparison_json,
)
from agentblaster.config import ProviderStore
from agentblaster.contract_check import (
    build_provider_contract_matrix,
    format_contract_check_matrix_report,
    format_contract_check_report,
    provider_contract_plan,
    run_provider_contract_check,
    write_contract_check_json,
    write_contract_check_matrix_json,
)
from agentblaster.costs import estimate_costs
from agentblaster.dashboard import assert_dashboard_bind_allowed, serve_dashboard
from agentblaster.errors import AgentBlasterError, ConfigError, PolicyError
from agentblaster.evidence import create_evidence_bundle
from agentblaster.evidence_index import build_evidence_index, format_evidence_index, write_evidence_index
from agentblaster.environment import build_environment_readiness, format_environment_readiness, write_environment_readiness
from agentblaster.engine_advisory import (
    build_engine_improvement_advisory,
    format_engine_improvement_advisory,
    write_engine_improvement_advisory,
)
from agentblaster.engine_targets import (
    engine_target_catalog_json,
    format_engine_target_catalog,
    get_engine_target,
)
from agentblaster.engine_onboarding import (
    build_local_engine_onboarding,
    format_local_engine_onboarding_markdown,
    write_local_engine_onboarding,
)
from agentblaster.exports import export_results
from agentblaster.experiment import (
    build_experiment_manifest,
    evaluate_experiment_manifest,
    format_experiment_gate,
    load_experiment_manifest,
    write_experiment_json,
)
from agentblaster.fixtures import write_dashboard_fixture
from agentblaster.harness import (
    build_harness_review_report,
    format_harness_review_report,
    generate_harness_suite,
    list_harness_profiles,
    suite_to_yaml,
)
from agentblaster.implementation_status import (
    build_implementation_status,
    format_implementation_status,
    write_implementation_status,
)
from agentblaster.integrity import sign_run_integrity, verify_run_integrity, verify_run_signature
from agentblaster.lcp import available_lcp_profiles, lcp_profile_catalog
from agentblaster.launch_recipes import (
    build_launch_recipe,
    format_launch_recipe_markdown,
    launch_recipe_catalog,
    write_launch_recipe_json,
)
from agentblaster.matrix import MatrixExecutionRunSummary, MatrixExecutionSummary, load_matrix_file
from agentblaster.matrix_gate import evaluate_matrix_gate, format_matrix_gate_report, write_matrix_gate_json
from agentblaster.matrix_pressure import audit_matrix_pressure, format_matrix_pressure_report, write_matrix_pressure_json
from agentblaster.matrix_saturation import (
    build_matrix_saturation_report,
    format_matrix_saturation_report,
    write_matrix_saturation_json,
)
from agentblaster.mcp import available_mcp_profiles, mcp_profile_tool_schemas
from agentblaster.metric_coverage import (
    format_metric_coverage_report,
    metric_coverage_catalog,
    metric_coverage_for_provider,
    write_metric_coverage_json,
)
from agentblaster.mock_provider import MockProviderSettings, serve_mock_provider
from agentblaster.model_catalog import generate_matrix_template, get_model_target, list_model_targets, matrix_to_yaml
from agentblaster.models import ApiContract, ModelMetadata, ProviderConfig, RawTraceMode, RetentionPolicy, RunSummary, SecretRef
from agentblaster.policy import (
    enterprise_policy_template,
    enterprise_policy_template_yaml,
    enforce_dashboard_policy,
    enforce_matrix_policy,
    enforce_provider_policy,
    estimate_case_prompt_tokens,
    load_policy,
    offline_policy,
    policy_control_summary,
)
from agentblaster.planning import RunPlan, build_run_plan, format_run_plan
from agentblaster.presets import PROVIDER_PRESETS, get_preset
from agentblaster.protocol_repair import (
    build_protocol_repair_posture,
    format_protocol_repair_posture,
    write_protocol_repair_posture_json,
    write_protocol_repair_posture_markdown,
)
from agentblaster.prompt_footprint import (
    format_prompt_footprint_report,
    suite_prompt_footprint,
    write_prompt_footprint_json,
)
from agentblaster.provider_audit import audit_providers, format_provider_audit, provider_audit_json
from agentblaster.readiness import build_readiness_dossier, format_readiness_report, write_readiness_json
from agentblaster.quality import (
    build_selftest_command,
    generate_selftest_reports,
    get_test_tier,
    list_test_tiers,
    render_sdlc_gate_catalog_json,
    render_sdlc_gate_catalog_markdown,
    render_sdlc_validation_manifest_json,
    render_sdlc_validation_manifest_markdown,
    render_chrome_gui_plan_json,
    render_chrome_gui_plan_markdown,
    render_chrome_validation_markdown,
    render_gui_test_spec_json,
    render_gui_test_spec_markdown,
    render_selftest_plan,
    run_selftest_command,
    write_gui_test_artifacts,
)
from agentblaster.release import format_packaging_readiness, write_packaging_readiness, write_release_provenance
from agentblaster.release_qualification import create_release_qualification_bundle
from agentblaster.redaction_scan import format_redaction_scan_report, redaction_scan_json, scan_paths
from agentblaster.remote_onboarding import (
    build_remote_provider_onboarding,
    format_remote_provider_onboarding,
    remote_provider_onboarding_json,
    write_remote_provider_onboarding,
)
from agentblaster.reports import (
    generate_matrix_reports,
    generate_matrix_scorecard_reports,
    generate_reports,
    load_matrix_execution_summary,
)
from agentblaster.runner import BenchmarkRunner
from agentblaster.schema_registry import artifact_schema_registry_json, format_artifact_schema_registry_markdown
from agentblaster.security_posture import (
    build_security_posture_report,
    format_security_posture_report,
    write_security_posture_json,
    write_security_posture_markdown,
)
from agentblaster.secrets import SecretResolver, dotenv_ref_name
from agentblaster.skills import available_skill_packs, skill_pack_text
from agentblaster.stress_matrix import generate_stress_matrix, stress_matrix_summary, stress_matrix_to_yaml
from agentblaster.suites import BUILTIN_SUITES, get_builtin_suite, load_suite_file, validate_case_or_suite_file
from agentblaster.suite_audit import audit_suite, format_suite_audit, suite_audit_json
from agentblaster.suite_calibration import (
    evaluate_suite_calibration,
    format_calibration_report,
    load_calibration,
    write_calibration_report,
    write_calibration_template,
)
from agentblaster.toolsim import SAFE_TOOL_SCHEMAS
from agentblaster.telemetry import (
    format_normalized_response_telemetry,
    format_telemetry_mapping_catalog,
    normalized_response_telemetry_json,
    normalize_response_telemetry,
    telemetry_mapping_catalog_json,
)
from agentblaster.telemetry_audit import audit_run_telemetry, format_telemetry_audit, write_telemetry_audit_json
from agentblaster.workflow_surfaces import (
    workflow_surface_catalog_json,
    workflow_surface_catalog_markdown,
)
from agentblaster.workflow_readiness import (
    build_workflow_readiness_report,
    format_workflow_readiness_report,
    write_workflow_readiness_json,
    write_workflow_readiness_markdown,
)

app = typer.Typer(help="AgentBlaster local agentic benchmark suite.")
engines_app = typer.Typer(help="Inspect and configure benchmark engines.")
providers_app = typer.Typer(help="Manage local and remote provider profiles.")
providers_auth_app = typer.Typer(help="Manage provider authentication references.")
providers_capabilities_app = typer.Typer(help="Declare provider capability support for preflight checks.")
providers_cost_app = typer.Typer(help="Manage provider cost models for remote budget policy.")
providers_rate_limits_app = typer.Typer(help="Manage provider request pacing and concurrency limits.")
quality_app = typer.Typer(help="Inspect AgentBlaster's internal SDLC test harness.")
selftest_app = typer.Typer(help="Run AgentBlaster's internal SDLC test harness.", invoke_without_command=True)
harness_app = typer.Typer(help="Generate deterministic emerging harness-engineering suites.")
agents_app = typer.Typer(help="Generate representative local-agent workflow suites.")
models_app = typer.Typer(help="Inspect canonical model targets and generate model matrices.")
matrix_app = typer.Typer(help="Inspect and report benchmark matrix artifacts.")
release_app = typer.Typer(help="Generate release governance and provenance artifacts.")
catalog_app = typer.Typer(help="Inspect bundled benchmark capability surfaces.")
evidence_app = typer.Typer(help="Create redaction-safe static governance evidence bundles.")
policy_app = typer.Typer(help="Validate and inspect enterprise policy files.")
security_app = typer.Typer(help="Run local security checks against AgentBlaster artifacts.")
experiment_app = typer.Typer(help="Create and gate static benchmark experiment manifests.")
app.add_typer(engines_app, name="engines")
app.add_typer(providers_app, name="providers")
providers_app.add_typer(providers_auth_app, name="auth")
providers_app.add_typer(providers_capabilities_app, name="capabilities")
providers_app.add_typer(providers_cost_app, name="cost")
providers_app.add_typer(providers_rate_limits_app, name="rate-limits")
app.add_typer(quality_app, name="quality")
app.add_typer(selftest_app, name="selftest")
app.add_typer(harness_app, name="harness")
app.add_typer(agents_app, name="agents")
app.add_typer(models_app, name="models")
app.add_typer(matrix_app, name="matrix")
app.add_typer(release_app, name="release")
app.add_typer(catalog_app, name="catalog")
app.add_typer(evidence_app, name="evidence")
app.add_typer(policy_app, name="policy")
app.add_typer(security_app, name="security")
app.add_typer(experiment_app, name="experiment")

BUILT_IN_ENGINES = [
    "afm",
    "mlx-lm",
    "ollama",
    "ollama-native",
    "lm-studio",
    "lm-studio-responses",
    "lm-studio-anthropic",
    "lm-studio-native",
    "omlx",
    "rapid-mlx",
    "vllm-mlx",
    "vllm-mlx-anthropic",
]


@app.command()
def version() -> None:
    """Print the AgentBlaster version."""
    from agentblaster import __version__

    typer.echo(__version__)


@app.command()
def doctor(
    output_json: Annotated[Path | None, typer.Option(help="Optional JSON output path for static environment readiness.")] = None,
    home: Annotated[Path | None, typer.Option(help="Optional AgentBlaster config home to report instead of the default.")] = None,
    policy: Annotated[Path | None, typer.Option(help="Optional security policy path to summarize as redacted readiness controls.")] = None,
    fail_on_required_gaps: Annotated[
        bool,
        typer.Option("--fail-on-required-gaps/--no-fail-on-required-gaps", help="Exit non-zero if required runtime readiness checks fail."),
    ] = False,
) -> None:
    """Report static local runtime readiness without contacting providers or resolving secrets."""
    security_policy = load_policy(policy)
    if output_json is not None:
        path = write_environment_readiness(output_json, home=home, policy=security_policy)
        try:
            report_payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise typer.BadParameter(str(exc)) from exc
    else:
        report_payload = build_environment_readiness(home=home, policy=security_policy)
        path = None
    typer.echo(format_environment_readiness(report_payload), nl=False)
    if path is not None:
        typer.echo(str(path))
    if fail_on_required_gaps and not report_payload["ok"]:
        raise typer.Exit(code=1)


@app.command("implementation-status")
def implementation_status_command(
    project_root: Annotated[Path, typer.Option(help="Project root to inspect for static implementation evidence.")] = Path("."),
    output_json: Annotated[Path | None, typer.Option(help="Optional JSON output path for the implementation status artifact.")] = None,
) -> None:
    """Report static implementation coverage without running tests or contacting providers."""
    if output_json is not None:
        path = write_implementation_status(output_json, project_root=project_root)
        try:
            report_payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise typer.BadParameter(str(exc)) from exc
    else:
        report_payload = build_implementation_status(project_root=project_root)
        path = None
    typer.echo(format_implementation_status(report_payload), nl=False)
    if path is not None:
        typer.echo(str(path))


@selftest_app.callback(invoke_without_command=True)
def selftest(
    ctx: typer.Context,
    tier: Annotated[str, typer.Option(help="App-test tier to run.")] = "normal",
    dry_run: Annotated[bool, typer.Option(help="Print the planned test command without executing it.")] = False,
    report_dir: Annotated[Path | None, typer.Option(help="Optional directory for selftest execution metadata.")] = None,
    junit_xml: Annotated[Path | None, typer.Option(help="Optional pytest JUnit XML output path.")] = None,
    run_id: Annotated[str | None, typer.Option(help="Optional stable selftest run id for deterministic release evidence paths.")] = None,
) -> None:
    """Run AgentBlaster's own SDLC test harness."""
    if ctx.invoked_subcommand is not None:
        return
    try:
        command = build_selftest_command(tier, report_dir=report_dir, junit_xml=junit_xml, run_id=run_id)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if dry_run:
        typer.echo(render_selftest_plan(command), nl=False)
        return
    raise typer.Exit(run_selftest_command(command))


@selftest_app.command("gui")
def selftest_gui(
    browser: Annotated[str, typer.Option(help="Browser target for GUI tests: chromium, chrome, or firefox.")] = "chromium",
    headed: Annotated[bool, typer.Option(help="Run browser tests headed when supported by the GUI harness.")] = False,
    dry_run: Annotated[bool, typer.Option(help="Print the planned GUI test command without executing it.")] = False,
    report_dir: Annotated[Path | None, typer.Option(help="Optional directory for selftest execution metadata.")] = None,
    junit_xml: Annotated[Path | None, typer.Option(help="Optional pytest JUnit XML output path.")] = None,
    run_id: Annotated[str | None, typer.Option(help="Optional stable selftest run id for deterministic release evidence paths.")] = None,
) -> None:
    """Run or plan dashboard GUI tests."""
    command = build_selftest_command(
        "gui",
        browser=browser,
        headed=headed,
        report_dir=report_dir,
        junit_xml=junit_xml,
        run_id=run_id,
    )
    if dry_run:
        typer.echo(render_selftest_plan(command), nl=False)
        return
    raise typer.Exit(run_selftest_command(command))


@selftest_app.command("report")
def selftest_report(
    run: Annotated[str, typer.Option(help="Selftest run id or path containing selftest.json.")],
    formats: Annotated[str, typer.Option("--format", help="Comma-separated report formats: html,json,junit.")] = "html,json",
    base_dir: Annotated[Path, typer.Option(help="Base directory for selftest run ids.")] = Path("test-reports/selftest"),
) -> None:
    """Generate reports for a recorded selftest execution."""
    try:
        generated = generate_selftest_reports(run, _split_csv(formats), base_dir=base_dir)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    for path in generated:
        typer.echo(path)


@app.command("mock-provider")
def mock_provider(
    host: Annotated[str, typer.Option(help="Host for the deterministic mock provider server.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port for the deterministic mock provider server.")] = 8787,
    profile: Annotated[str, typer.Option(help="Mock behavior profile. Currently: deterministic.")] = "deterministic",
    latency_ms: Annotated[int, typer.Option(help="Optional fixed response latency in milliseconds.")] = 0,
    require_auth: Annotated[bool, typer.Option(help="Require Authorization or x-api-key headers for contract tests.")] = False,
) -> None:
    """Serve a deterministic local OpenAI/Anthropic-compatible mock provider."""
    if profile != "deterministic":
        raise typer.BadParameter("profile must be deterministic")
    typer.echo(f"AgentBlaster mock provider listening on http://{host}:{port}/v1", err=True)
    serve_mock_provider(
        host=host,
        port=port,
        settings=MockProviderSettings(profile=profile, latency_ms=latency_ms, require_auth=require_auth),
    )


@engines_app.command("improvement-plan")
def engines_improvement_plan(
    engine: Annotated[str, typer.Option(help="Engine/provider name to generate improvement priorities for.")] = "afm",
    pressure_audit: Annotated[list[Path] | None, typer.Option(help="Matrix pressure audit JSON artifact. Can be repeated.")] = None,
    matrix_saturation_report: Annotated[list[Path] | None, typer.Option(help="Matrix saturation report JSON artifact. Can be repeated.")] = None,
    provider_contract_check: Annotated[list[Path] | None, typer.Option(help="Provider contract-check JSON artifact. Can be repeated.")] = None,
    provider_contract_matrix: Annotated[list[Path] | None, typer.Option(help="Provider contract-check matrix JSON artifact. Can be repeated.")] = None,
    telemetry_audit: Annotated[list[Path] | None, typer.Option(help="Telemetry audit JSON artifact. Can be repeated.")] = None,
    metric_coverage: Annotated[list[Path] | None, typer.Option(help="Metric coverage JSON artifact. Can be repeated.")] = None,
    matrix_gate: Annotated[list[Path] | None, typer.Option(help="Matrix gate JSON artifact. Can be repeated.")] = None,
    comparison_gate: Annotated[list[Path] | None, typer.Option(help="Comparison gate JSON artifact. Can be repeated.")] = None,
    harness_review: Annotated[list[Path] | None, typer.Option(help="Harness review JSON artifact for generated suites. Can be repeated.")] = None,
    output_json: Annotated[Path | None, typer.Option(help="Optional engine improvement advisory JSON output path.")] = None,
) -> None:
    """Create a no-dispatch engine improvement plan from benchmark evidence artifacts."""
    try:
        report = build_engine_improvement_advisory(
            engine=engine,
            pressure_audits=pressure_audit,
            telemetry_audits=telemetry_audit,
            metric_coverage_reports=metric_coverage,
            matrix_gates=matrix_gate,
            comparison_gates=comparison_gate,
            matrix_saturation_reports=matrix_saturation_report,
            provider_contract_checks=provider_contract_check,
            provider_contract_matrices=provider_contract_matrix,
            harness_reviews=harness_review,
        )
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if output_json is not None:
        typer.echo(str(write_engine_improvement_advisory(report, output_json)))
    typer.echo(format_engine_improvement_advisory(report), nl=False)


@evidence_app.command("campaign-preflight")
def campaign_preflight_bundle_command(
    matrix: Annotated[
        list[Path] | None,
        typer.Option("--matrix", help="Matrix file to inventory. Repeat for multi-matrix campaigns."),
    ] = None,
    output_dir: Annotated[Path, typer.Option(help="Directory where the preflight bundle folder is written.")] = Path("campaign-preflight"),
    policy: Annotated[Path | None, typer.Option(help="Optional reviewed policy file to include and normalize.")] = None,
    project_root: Annotated[Path, typer.Option(help="Project root for implementation and packaging readiness.")] = Path("."),
    home: Annotated[Path | None, typer.Option(help="Optional AgentBlaster config home to report in environment readiness.")] = None,
    include_provider_audit: Annotated[
        bool,
        typer.Option("--include-provider-audit/--no-provider-audit", help="Include redacted provider inventory and policy audit."),
    ] = True,
    benchmark_readiness: Annotated[
        list[Path] | None,
        typer.Option("--benchmark-readiness", help="Benchmark readiness dossier JSON artifact to summarize. Can be repeated."),
    ] = None,
    benchmark_readiness_list: Annotated[
        list[Path] | None,
        typer.Option(
            "--benchmark-readiness-list",
            help="Text file with one benchmark readiness dossier JSON path per line. Can be repeated.",
        ),
    ] = None,
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path.")] = None,
) -> None:
    """Create a no-dispatch campaign readiness folder before executing matrices."""
    if not matrix:
        raise typer.BadParameter("provide at least one --matrix")
    resolved_benchmark_readiness = _benchmark_readiness_paths(benchmark_readiness, benchmark_readiness_list)
    audit = AuditLogger(audit_log)
    audit.emit(
        "campaign_preflight_bundle_requested",
        matrix_count=len(matrix),
        output_dir=str(output_dir),
        policy_path=str(policy) if policy else None,
        include_provider_audit=include_provider_audit,
        benchmark_readiness_reports=[str(item) for item in resolved_benchmark_readiness or []],
        benchmark_readiness_lists=[str(item) for item in benchmark_readiness_list or []],
    )
    try:
        bundle = create_campaign_preflight_bundle(
            output_dir=output_dir,
            matrices=matrix,
            policy=policy,
            project_root=project_root,
            home=home,
            include_provider_audit=include_provider_audit,
            benchmark_readiness_reports=resolved_benchmark_readiness,
        )
    except AgentBlasterError as exc:
        audit.emit("campaign_preflight_bundle_failed", output_dir=str(output_dir), reason=str(exc))
        raise typer.BadParameter(str(exc)) from exc
    audit.emit(
        "campaign_preflight_bundle_created",
        output_dir=str(bundle.output_dir),
        manifest_path=str(bundle.manifest_path),
        matrix_count=bundle.manifest["matrix_count"],
        artifact_count=bundle.manifest["artifact_count"],
    )
    typer.echo(format_campaign_preflight_bundle(bundle), nl=False)


def _benchmark_readiness_paths(paths: list[Path] | None, list_files: list[Path] | None) -> list[Path] | None:
    resolved = list(paths or [])
    for list_file in list_files or []:
        list_file = list_file.expanduser()
        try:
            lines = list_file.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise typer.BadParameter(f"cannot read --benchmark-readiness-list {list_file}: {exc}") from exc
        for line_number, raw_line in enumerate(lines, start=1):
            value = raw_line.strip()
            if not value or value.startswith("#"):
                continue
            if "\0" in value:
                raise typer.BadParameter(f"invalid NUL byte in --benchmark-readiness-list {list_file}:{line_number}")
            if " #" in value or "\t#" in value:
                raise typer.BadParameter(
                    f"inline comments are not supported in --benchmark-readiness-list {list_file}:{line_number}"
                )
            if value[0] in {"'", '"'} or value[-1] in {"'", '"'}:
                raise typer.BadParameter(
                    f"quoted paths are not supported in --benchmark-readiness-list {list_file}:{line_number}"
                )
            entry_path = Path(value).expanduser()
            if not entry_path.is_absolute():
                entry_path = list_file.parent / entry_path
            resolved.append(entry_path)
    return resolved or None


@app.command()
def run(
    engine: Annotated[str | None, typer.Option(help="Configured provider/engine profile name.")] = None,
    model: Annotated[str | None, typer.Option(help="Model id. Required unless provider has a default model.")] = None,
    suite: Annotated[str, typer.Option(help="Built-in benchmark suite to run.")] = "smoke",
    suite_file: Annotated[Path | None, typer.Option(help="YAML suite definition to run.")] = None,
    matrix: Annotated[Path | None, typer.Option(help="YAML matrix file containing multiple runs.")] = None,
    output_dir: Annotated[Path, typer.Option(help="Directory where run artifacts are written.")] = Path("runs"),
    policy: Annotated[Path | None, typer.Option(help="Optional agentblaster.policy.yaml path.")] = None,
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path.")] = None,
    offline: Annotated[bool, typer.Option(help="Block providers marked as remote.")] = False,
    concurrency: Annotated[int, typer.Option(help="Maximum concurrent benchmark cases.")] = 1,
    model_revision: Annotated[str | None, typer.Option(help="Model revision/hash metadata.")] = None,
    model_architecture: Annotated[str | None, typer.Option(help="Model architecture metadata.")] = None,
    quantization: Annotated[str | None, typer.Option(help="Model quantization metadata.")] = None,
    tokenizer: Annotated[str | None, typer.Option(help="Tokenizer metadata.")] = None,
    chat_template: Annotated[str | None, typer.Option(help="Chat template metadata.")] = None,
    context_length: Annotated[int | None, typer.Option(help="Context length metadata.")] = None,
    retention_classification: Annotated[
        str,
        typer.Option(help="Run artifact classification: public, internal, confidential, or restricted."),
    ] = "internal",
    retention_days: Annotated[int | None, typer.Option(help="Optional number of days to retain the run artifact directory.")] = None,
    raw_trace_retention_days: Annotated[
        int | None,
        typer.Option(help="Optional number of days to retain raw trace artifacts."),
    ] = None,
    retention_note: Annotated[
        list[str] | None,
        typer.Option(help="Optional retention/governance note. Can be repeated."),
    ] = None,
    raw_traces: Annotated[
        RawTraceMode,
        typer.Option(help="Raw response capture mode."),
    ] = RawTraceMode.REDACTED,
    no_raw_traces: Annotated[bool, typer.Option(help="Disable raw response capture.")] = False,
    capability_preflight: Annotated[
        bool,
        typer.Option("--capability-preflight/--no-capability-preflight", help="Check provider/suite capability compatibility before dispatch."),
    ] = True,
    strict_unknown_capabilities: Annotated[
        bool,
        typer.Option(help="Treat unknown required provider capabilities as a preflight failure."),
    ] = False,
    dry_run: Annotated[bool, typer.Option(help="Plan the run without dispatching provider requests or writing run artifacts.")] = False,
    plan_json: Annotated[Path | None, typer.Option(help="Optional JSON path for dry-run plan output.")] = None,
    matrix_summary_json: Annotated[Path | None, typer.Option(help="Optional JSON path for executed matrix summary output.")] = None,
    continue_on_error: Annotated[
        bool,
        typer.Option(help="Continue matrix execution after an entry fails and record a partial summary."),
    ] = False,
) -> None:
    """Run a benchmark suite against a configured provider."""
    if matrix is not None:
        matrix_retention_policy = (
            None
            if retention_classification == "internal"
            and retention_days is None
            and raw_trace_retention_days is None
            and not retention_note
            else _retention_policy_from_options(
                classification=retention_classification,
                retain_days=retention_days,
                raw_trace_retain_days=raw_trace_retention_days,
                notes=retention_note,
            )
        )
        _run_matrix(
            matrix=matrix,
            output_dir=output_dir,
            policy=policy,
            audit_log=audit_log,
            offline=offline,
            dry_run=dry_run,
            plan_json=plan_json,
            matrix_summary_json=matrix_summary_json,
            continue_on_error=continue_on_error,
            retention_policy=matrix_retention_policy,
            capability_preflight=capability_preflight,
            strict_unknown_capabilities=strict_unknown_capabilities,
        )
        return

    if engine is None:
        raise typer.BadParameter("--engine is required unless --matrix is provided")

    summary = _run_one(
        engine=engine,
        model=model,
        suite=suite,
        suite_file=suite_file,
        output_dir=output_dir,
        policy=policy,
        audit_log=audit_log,
        offline=offline,
        concurrency=concurrency,
        trace_mode=RawTraceMode.OFF if no_raw_traces else raw_traces,
        capability_preflight=capability_preflight,
        strict_unknown_capabilities=strict_unknown_capabilities,
        dry_run=dry_run,
        model_metadata=_model_metadata_from_options(
            revision=model_revision,
            architecture=model_architecture,
            quantization=quantization,
            tokenizer=tokenizer,
            chat_template=chat_template,
            context_length=context_length,
        ),
        retention_policy=_retention_policy_from_options(
            classification=retention_classification,
            retain_days=retention_days,
            raw_trace_retain_days=raw_trace_retention_days,
            notes=retention_note,
        ),
    )

    if dry_run:
        if plan_json is not None:
            _write_plan_json(summary, plan_json)
        typer.echo(format_run_plan(summary))
        return

    _print_summary(summary)


def _run_matrix(
    *,
    matrix: Path,
    output_dir: Path,
    policy: Path | None,
    audit_log: Path | None,
    offline: bool,
    dry_run: bool = False,
    plan_json: Path | None = None,
    matrix_summary_json: Path | None = None,
    continue_on_error: bool = False,
    retention_policy: RetentionPolicy | None = None,
    capability_preflight: bool = True,
    strict_unknown_capabilities: bool = False,
) -> None:
    if dry_run and matrix_summary_json is not None:
        raise typer.BadParameter("--matrix-summary-json is for executed matrix runs; use --plan-json for dry-run plans")

    matrix_definition = load_matrix_file(matrix)
    audit = AuditLogger(audit_log)
    try:
        security_policy = offline_policy() if offline else load_policy(policy)
        matrix_total_cases = _matrix_total_cases(matrix_definition)
        estimated_matrix_cost = (
            _matrix_estimated_cost(matrix_definition)
            if security_policy.max_estimated_matrix_cost_usd is not None
            else None
        )
        audit.emit(
            "matrix_policy_evaluation",
            matrix=matrix_definition.name,
            total_runs=len(matrix_definition.runs),
            total_cases=matrix_total_cases,
            estimated_cost_usd=estimated_matrix_cost,
            policy_path=str(policy) if policy else None,
            offline=offline,
        )
        enforce_matrix_policy(
            security_policy,
            matrix_name=matrix_definition.name,
            total_runs=len(matrix_definition.runs),
            total_cases=matrix_total_cases,
            estimated_cost_usd=estimated_matrix_cost,
        )
    except AgentBlasterError as exc:
        audit.emit("policy_violation", surface="matrix", matrix=matrix_definition.name, reason=str(exc))
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"matrix: {matrix_definition.name}")
    plans: list[RunPlan] = []
    run_summaries: list[MatrixExecutionRunSummary] = []
    for index, run_entry in enumerate(matrix_definition.runs, start=1):
        trace_mode = RawTraceMode.OFF if run_entry.no_raw_traces else run_entry.raw_traces
        try:
            summary_or_plan = _run_one(
                engine=run_entry.engine,
                model=run_entry.model,
                suite=run_entry.suite,
                suite_file=run_entry.suite_file,
                output_dir=output_dir,
                policy=policy,
                audit_log=audit_log,
                offline=offline,
                concurrency=run_entry.concurrency,
                trace_mode=trace_mode,
                capability_preflight=capability_preflight and run_entry.capability_preflight,
                strict_unknown_capabilities=strict_unknown_capabilities or run_entry.strict_unknown_capabilities,
                dry_run=dry_run,
                model_metadata=run_entry.model_metadata,
                retention_policy=run_entry.retention_policy if retention_policy is None else retention_policy,
            )
        except (AgentBlasterError, ValueError, typer.BadParameter) as exc:
            if not continue_on_error:
                raise
            typer.echo(f"[{index}/{len(matrix_definition.runs)}] failed {run_entry.engine} {run_entry.suite}: {exc}")
            if not dry_run:
                run_summaries.append(_matrix_execution_error_summary(index, run_entry, exc))
            continue
        if dry_run:
            plans.append(summary_or_plan)
            typer.echo(
                f"[{index}/{len(matrix_definition.runs)}] plan {summary_or_plan.provider} "
                f"{summary_or_plan.suite} {summary_or_plan.model} compatible={str(summary_or_plan.capability_compatible).lower()}"
            )
        else:
            summary = summary_or_plan
            summary_base_dir = matrix_summary_json.parent if matrix_summary_json is not None else Path(".")
            run_summaries.append(
                _matrix_execution_run_summary(
                    index,
                    run_entry,
                    summary,
                    output_dir=output_dir,
                    summary_base_dir=summary_base_dir,
                )
            )
            typer.echo(f"[{index}/{len(matrix_definition.runs)}] {summary.run_id} {summary.provider} {summary.suite} ok={summary.failed == 0}")
    if dry_run and plan_json is not None:
        _write_plan_json(plans, plan_json)
    if not dry_run and matrix_summary_json is not None:
        _write_matrix_summary_json(
            matrix_definition,
            matrix,
            run_summaries,
            matrix_summary_json,
            continue_on_error=continue_on_error,
        )


def _matrix_execution_run_summary(
    index: int,
    run_entry,
    summary: RunSummary,
    *,
    output_dir: Path = Path("runs"),
    summary_base_dir: Path = Path("."),
) -> MatrixExecutionRunSummary:
    run_dir = output_dir / summary.run_id
    results_path = _matrix_summary_artifact_path(run_dir / Path(summary.results_path).name, summary_base_dir)
    manifest_path = _matrix_summary_artifact_path(run_dir / Path(summary.manifest_path).name, summary_base_dir)
    summary_path = _matrix_summary_artifact_path(run_dir / "summary.json", summary_base_dir)
    return MatrixExecutionRunSummary(
        index=index,
        engine=run_entry.engine,
        provider=summary.provider,
        engine_target=_matrix_run_engine_target(run_dir / "manifest.json"),
        model=summary.model,
        suite=summary.suite,
        suite_file=str(run_entry.suite_file) if run_entry.suite_file is not None else None,
        run_id=summary.run_id,
        ok=summary.failed == 0,
        total_cases=summary.total_cases,
        passed=summary.passed,
        failed=summary.failed,
        concurrency=summary.concurrency,
        results_path=results_path,
        manifest_path=manifest_path,
        summary_path=summary_path,
    )


def _matrix_summary_artifact_path(path: Path, summary_base_dir: Path) -> str:
    try:
        return os.path.relpath(path, start=summary_base_dir)
    except ValueError:
        return str(path)


def _matrix_run_engine_target(manifest_path: Path) -> dict | None:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    engine_target = payload.get("engine_target") if isinstance(payload, dict) else None
    if not isinstance(engine_target, dict):
        return None
    standardization = engine_target.get("standardization")
    return {
        "id": engine_target.get("id"),
        "display_name": engine_target.get("display_name"),
        "standardization": {
            "primary_scoring_contract": (
                standardization.get("primary_scoring_contract") if isinstance(standardization, dict) else None
            )
        },
    }


def _matrix_total_cases(matrix_definition) -> int:
    total_cases = 0
    for run_entry in matrix_definition.runs:
        suite_definition = load_suite_file(run_entry.suite_file) if run_entry.suite_file else get_builtin_suite(run_entry.suite)
        total_cases += len(suite_definition.cases)
    return total_cases


def _matrix_estimated_cost(matrix_definition) -> float:
    store = ProviderStore()
    estimated_cost = 0.0
    saw_cost = False
    for run_entry in matrix_definition.runs:
        provider = store.get(run_entry.engine)
        if not provider.cost_model:
            raise PolicyError(f"matrix cost policy requires provider.cost_model for {provider.name}")
        suite_definition = load_suite_file(run_entry.suite_file) if run_entry.suite_file else get_builtin_suite(run_entry.suite)
        for case in suite_definition.cases:
            case_cost = estimate_costs(
                provider.cost_model,
                input_tokens=estimate_case_prompt_tokens(case),
                output_tokens=case.max_tokens,
            )["total_cost_usd"]
            if case_cost is None:
                raise PolicyError(
                    f"matrix cost policy requires input/output rates in provider.cost_model for {provider.name}"
                )
            saw_cost = True
            estimated_cost += case_cost
    return round(estimated_cost, 9) if saw_cost else 0.0


def _matrix_execution_error_summary(index: int, run_entry, exc: Exception) -> MatrixExecutionRunSummary:
    return MatrixExecutionRunSummary(
        index=index,
        engine=run_entry.engine,
        provider=run_entry.engine,
        model=run_entry.model or "unresolved",
        suite=run_entry.suite,
        suite_file=str(run_entry.suite_file) if run_entry.suite_file is not None else None,
        ok=False,
        total_cases=0,
        passed=0,
        failed=0,
        concurrency=run_entry.concurrency,
        error_type=exc.__class__.__name__,
        error_message=str(exc),
    )


def _write_matrix_summary_json(
    matrix_definition,
    matrix_path: Path,
    runs: list[MatrixExecutionRunSummary],
    output: Path,
    *,
    continue_on_error: bool = False,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload = MatrixExecutionSummary(
        matrix_name=matrix_definition.name,
        matrix_path=str(matrix_path),
        description=matrix_definition.description,
        created_at=created_at,
        continue_on_error=continue_on_error,
        total_runs=len(matrix_definition.runs),
        attempted_runs=len(runs),
        completed_runs=sum(1 for run in runs if run.run_id is not None),
        failed_runs=sum(1 for run in runs if not run.ok),
        runs=runs,
    )
    output.write_text(payload.model_dump_json(indent=2) + "\n", encoding="utf-8")
    typer.echo(f"matrix_summary_json: {output}")


def _run_one(
    *,
    engine: str,
    model: str | None,
    suite: str,
    suite_file: Path | None,
    output_dir: Path,
    policy: Path | None,
    audit_log: Path | None,
    offline: bool,
    concurrency: int,
    trace_mode: RawTraceMode,
    capability_preflight: bool,
    strict_unknown_capabilities: bool,
    dry_run: bool,
    model_metadata: ModelMetadata | None = None,
    retention_policy: RetentionPolicy | None = None,
):
    provider = ProviderStore().get(engine)
    suite_definition = load_suite_file(suite_file) if suite_file else get_builtin_suite(suite)
    security_policy = offline_policy() if offline else load_policy(policy)
    audit = AuditLogger(audit_log)
    audit.emit(
        "run_policy_evaluation",
        provider=provider.name,
        suite=suite,
        model=model or provider.default_model,
        raw_trace_mode=trace_mode.value,
        offline=offline,
        policy_path=str(policy) if policy else None,
        concurrency=concurrency,
    )
    try:
        enforce_provider_policy(
            provider,
            security_policy,
            raw_trace_mode=trace_mode,
            concurrency=concurrency,
            suite=suite_definition,
        )
    except AgentBlasterError as exc:
        audit.emit("policy_violation", provider=provider.name, reason=str(exc))
        raise typer.BadParameter(str(exc)) from exc

    capability_report = None
    if capability_preflight:
        report = check_suite_compatibility(
            provider,
            suite_definition,
            strict_unknown=strict_unknown_capabilities,
        )
        capability_report = report
        audit.emit(
            "capability_preflight",
            provider=provider.name,
            suite=suite_definition.name,
            compatible=report.compatible,
            strict_unknown=report.strict_unknown,
            missing=[finding.key for finding in report.missing],
            unknown=[finding.key for finding in report.unknown],
        )
        if not report.compatible:
            audit.emit("capability_violation", provider=provider.name, suite=suite_definition.name)
            raise typer.BadParameter(format_capability_report(report))

    if dry_run:
        resolved_model = model or provider.default_model
        if not resolved_model:
            raise typer.BadParameter("model is required when provider has no default_model")
        plan = build_run_plan(
            provider=provider,
            suite=suite_definition,
            model=resolved_model,
            raw_trace_mode=trace_mode,
            concurrency=concurrency,
            capability_report=capability_report,
        )
        audit.emit(
            "run_planned",
            provider=provider.name,
            suite=suite_definition.name,
            model=resolved_model,
            total_cases=plan.total_cases,
            estimated_prompt_tokens=plan.estimated_prompt_tokens,
            estimated_total_cost_usd=plan.estimated_total_cost_usd,
        )
        return plan

    try:
        audit.emit("run_started", provider=provider.name, suite=suite, remote=provider.remote)
        summary = BenchmarkRunner(
            provider,
            suite_definition,
            output_dir=output_dir,
            raw_trace_mode=trace_mode,
            concurrency=concurrency,
            retention_policy=retention_policy,
        ).run(model=model, model_metadata=model_metadata)
        audit.emit(
            "run_completed",
            run_id=summary.run_id,
            provider=summary.provider,
            suite=summary.suite,
            passed=summary.passed,
            failed=summary.failed,
            concurrency=summary.concurrency,
        )
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    return summary


def _print_summary(summary) -> None:
    typer.echo(f"run_id: {summary.run_id}")
    typer.echo(f"suite: {summary.suite}")
    typer.echo(f"provider: {summary.provider}")
    typer.echo(f"model: {summary.model}")
    typer.echo(f"total_cases: {summary.total_cases}")
    typer.echo(f"passed: {summary.passed}")
    typer.echo(f"failed: {summary.failed}")
    typer.echo(f"concurrency: {summary.concurrency}")
    typer.echo(f"ok: {str(summary.failed == 0).lower()}")


def _model_metadata_from_options(
    *,
    revision: str | None = None,
    architecture: str | None = None,
    quantization: str | None = None,
    tokenizer: str | None = None,
    chat_template: str | None = None,
    context_length: int | None = None,
) -> ModelMetadata | None:
    metadata = ModelMetadata(
        revision=revision,
        architecture=architecture,
        quantization=quantization,
        tokenizer=tokenizer,
        chat_template=chat_template,
        context_length=context_length,
    )
    return None if metadata.is_empty() else metadata


def _retention_policy_from_options(
    *,
    classification: str,
    retain_days: int | None,
    raw_trace_retain_days: int | None,
    notes: list[str] | None,
) -> RetentionPolicy:
    try:
        return RetentionPolicy(
            classification=classification,
            retain_days=retain_days,
            raw_trace_retain_days=raw_trace_retain_days,
            notes=notes or [],
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _write_plan_json(plan: RunPlan | list[RunPlan], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(plan, list):
        payload = [item.model_dump(mode="json") for item in plan]
    else:
        payload = plan.model_dump(mode="json")
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _validate_capability_key(capability: str) -> str:
    key = capability.strip()
    if key not in CAPABILITY_DESCRIPTIONS:
        available = ", ".join(sorted(CAPABILITY_DESCRIPTIONS))
        raise typer.BadParameter(f"unknown capability: {key}; available capabilities: {available}")
    return key


def _set_provider_capability(provider_name: str, capability: str, value: bool) -> None:
    capability_key = _validate_capability_key(capability)
    store = ProviderStore()
    config = store.get(provider_name)
    capabilities = dict(config.capabilities)
    capabilities[capability_key] = value
    store.upsert(config.model_copy(update={"capabilities": capabilities}))



@security_app.command("scan")
def security_scan(
    paths: Annotated[list[Path], typer.Argument(help="Files, directories, or zip artifacts to scan.")],
    output_json: Annotated[Path | None, typer.Option(help="Optional redaction scan JSON output path.")] = None,
    fail_on_findings: Annotated[
        bool,
        typer.Option("--fail-on-findings/--no-fail-on-findings", help="Exit non-zero when findings are detected."),
    ] = True,
    max_bytes: Annotated[int, typer.Option(help="Maximum bytes to scan per file or zip entry.")] = 2_000_000,
) -> None:
    """Scan shareable artifacts for common secret-like patterns without printing matches."""
    try:
        report = scan_paths(paths, max_bytes=max_bytes)
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(format_redaction_scan_report(report), nl=False)
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(redaction_scan_json(report), encoding="utf-8")
        typer.echo(str(output_json))
    if fail_on_findings and not report.ok:
        raise typer.Exit(code=1)


@policy_app.command("validate")
def policy_validate(
    path: Annotated[Path, typer.Argument(help="Policy YAML file to validate and normalize.")],
    output_json: Annotated[Path | None, typer.Option(help="Optional normalized policy JSON output path.")] = None,
) -> None:
    """Validate an enterprise policy file without running benchmarks."""
    try:
        security_policy = load_policy(path)
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    payload = security_policy.model_dump(mode="json", exclude_none=True)
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        typer.echo(str(output_json))
    typer.echo(f"policy: {path}")
    typer.echo("valid: true")
    typer.echo(f"fields: {len(payload)}")


@policy_app.command("template")
def policy_template(
    output: Annotated[Path | None, typer.Option(help="Optional YAML output path for the enterprise policy template.")] = None,
    profile: Annotated[str, typer.Option(help="Template profile: local or remote-gateway.")] = "local",
    output_json: Annotated[Path | None, typer.Option(help="Optional JSON output path with template metadata.")] = None,
) -> None:
    """Generate a strict enterprise policy template without reading secrets or contacting providers."""
    if profile not in {"local", "remote-gateway"}:
        raise typer.BadParameter("profile must be local or remote-gateway")
    payload = enterprise_policy_template(profile=profile)  # type: ignore[arg-type]
    rendered = enterprise_policy_template_yaml(profile=profile)  # type: ignore[arg-type]
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        typer.echo(str(output))
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        typer.echo(str(output_json))
    if output is None and output_json is None:
        typer.echo(rendered, nl=False)


@policy_app.command("controls")
def policy_controls(
    path: Annotated[Path, typer.Argument(help="Policy YAML file to summarize.")],
    name: Annotated[str, typer.Option(help="Review name for the policy summary.")] = "policy",
    output_json: Annotated[Path | None, typer.Option(help="Optional policy-control summary JSON output path.")] = None,
) -> None:
    """Summarize enterprise policy controls without resolving secrets or dispatching providers."""
    try:
        security_policy = load_policy(path)
        summary = policy_control_summary(security_policy, name=name)
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        typer.echo(str(output_json))
    typer.echo(f"policy: {path}")
    typer.echo(f"enterprise_ready: {str(summary['enterprise_ready']).lower()}")
    typer.echo(
        f"controls: enabled={summary['summary']['enabled_controls']}/{summary['summary']['control_count']} "
        f"blockers={summary['summary']['blockers']} warnings={summary['summary']['warnings']}"
    )
    if summary["blockers"]:
        typer.echo("blockers: " + ", ".join(summary["blockers"]))


@app.command("suites")
def list_suites() -> None:
    """List built-in benchmark suites."""
    for suite in BUILTIN_SUITES.values():
        typer.echo(f"{suite.name}\t{len(suite.cases)} case(s)\t{suite.description}")


@app.command("validate-case")
def validate_case(path: Annotated[Path, typer.Argument(help="YAML benchmark case or suite file.")]) -> None:
    """Validate a YAML benchmark case or suite file."""
    try:
        typer.echo(validate_case_or_suite_file(path))
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command("suite-footprint")
def suite_footprint_command(
    suite: Annotated[str, typer.Option(help="Built-in benchmark suite to analyze.")] = "smoke",
    suite_file: Annotated[Path | None, typer.Option(help="YAML suite definition to analyze.")] = None,
    output_json: Annotated[Path | None, typer.Option(help="Optional JSON output path.")] = None,
) -> None:
    """Analyze suite prompt, tool, MCP, and skill footprint without provider dispatch."""
    try:
        suite_definition = load_suite_file(suite_file) if suite_file else get_builtin_suite(suite)
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    report = suite_prompt_footprint(suite_definition)
    if output_json is not None:
        write_prompt_footprint_json(report, output_json)
    typer.echo(format_prompt_footprint_report(report), nl=False)


@app.command("suite-requirements")
def suite_requirements_command(
    suite: Annotated[str, typer.Option(help="Built-in benchmark suite to inspect.")] = "smoke",
    suite_file: Annotated[Path | None, typer.Option(help="YAML suite definition to inspect.")] = None,
) -> None:
    """Show provider capabilities required by a suite."""
    try:
        suite_definition = load_suite_file(suite_file) if suite_file else get_builtin_suite(suite)
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    for requirement in suite_requirements(suite_definition):
        cases = ",".join(requirement.case_ids) if requirement.case_ids else "-"
        typer.echo(f"{requirement.key}\tcases={cases}\t{requirement.description}")


@app.command("suite-audit")
def suite_audit_command(
    suite: Annotated[str, typer.Option(help="Built-in benchmark suite to audit.")] = "smoke",
    suite_file: Annotated[Path | None, typer.Option(help="YAML suite definition to audit.")] = None,
    output_json: Annotated[Path | None, typer.Option(help="Optional JSON output path.")] = None,
) -> None:
    """Audit suite provenance, risk, and capability surfaces without dispatching providers."""
    try:
        suite_definition = load_suite_file(suite_file) if suite_file else get_builtin_suite(suite)
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    report = audit_suite(suite_definition)
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(suite_audit_json(report), encoding="utf-8")
        typer.echo(str(output_json))
        return
    typer.echo(format_suite_audit(report), nl=False)


@app.command("suite-calibration")
def suite_calibration_command(
    suite: Annotated[str, typer.Option(help="Built-in benchmark suite to calibrate.")] = "smoke",
    suite_file: Annotated[Path | None, typer.Option(help="YAML suite definition to calibrate.")] = None,
    calibration: Annotated[Path | None, typer.Option(help="Calibration manifest JSON to evaluate.")] = None,
    template_output: Annotated[Path | None, typer.Option(help="Write a calibration manifest template instead of evaluating.")] = None,
    output_json: Annotated[Path | None, typer.Option(help="Optional JSON output path for the calibration report.")] = None,
    no_release_gate: Annotated[bool, typer.Option(help="Do not require approved_for_release_gate=true.")] = False,
) -> None:
    """Template or evaluate generated-suite calibration evidence."""
    try:
        suite_definition = load_suite_file(suite_file) if suite_file else get_builtin_suite(suite)
        if template_output is not None:
            path = write_calibration_template(suite_definition, template_output)
            typer.echo(str(path))
            return
        if calibration is None:
            raise typer.BadParameter("--calibration is required unless --template-output is set")
        report = evaluate_suite_calibration(
            suite_definition,
            load_calibration(calibration),
            require_release_gate=not no_release_gate,
        )
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if output_json is not None:
        write_calibration_report(report, output_json)
    typer.echo(format_calibration_report(report), nl=False)
    if not report["passed"]:
        raise typer.Exit(1)


@app.command()
def report(
    run_dir: Annotated[Path, typer.Argument(help="Run artifact directory.")],
    format: Annotated[
        str,
        typer.Option(help="Comma-separated formats: html,md,json,publication,card,png,pdf."),
    ] = "html,json",
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for report export events.")] = None,
) -> None:
    """Generate reports from a completed run directory."""
    formats = [item.strip() for item in format.split(",")]
    try:
        paths = generate_reports(run_dir, formats)
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    AuditLogger(audit_log).emit(
        "report_exported",
        run_dir=str(run_dir),
        formats=[item for item in formats if item],
        artifacts=[str(path) for path in paths],
    )
    for path in paths:
        typer.echo(str(path))


@agents_app.command("profiles")
def agents_profiles() -> None:
    """List representative local-agent workflow profiles."""
    for profile in list_agent_profiles():
        features = ",".join(profile.representative_features)
        typer.echo(f"{profile.id}	{profile.display_name}	{features}	{profile.description}")


@agents_app.command("suite")
def agents_suite(
    profile: Annotated[str, typer.Option(help="Agent profile id: opencode, openclaw, hermes, pi, or all.")] = "all",
    output: Annotated[Path | None, typer.Option(help="Optional output YAML path for the generated suite.")] = None,
) -> None:
    """Generate a deterministic representative local-agent workflow suite."""
    include_all = profile == "all"
    try:
        suite = generate_agent_suite(profile, include_all=include_all)
    except ConfigError as exc:
        raise typer.BadParameter(str(exc)) from exc
    rendered = agent_suite_to_yaml(suite)
    if output is None:
        typer.echo(rendered, nl=False)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    typer.echo(str(output))


@models_app.command("stress-matrix")
def models_stress_matrix(
    providers: Annotated[str, typer.Option(help="Comma-separated provider names for the matrix.")],
    targets: Annotated[str, typer.Option(help="Comma-separated model target ids for the matrix.")] = "qwen3.6-27b-dense,gemma-4-31b-dense",
    suites: Annotated[str, typer.Option(help="Comma-separated built-in suite names to stress.")] = "agentic-tool-loop,agent-fanout,prefill,harness-engineering,trace-replay",
    concurrency_levels: Annotated[str, typer.Option(help="Comma-separated concurrency levels, for example 1,2,4,8.")] = "1,2,4,8",
    output: Annotated[Path, typer.Option(help="Output matrix YAML path.")] = Path("examples/matrices/stress-qwen-gemma.yaml"),
    summary_json: Annotated[Path | None, typer.Option(help="Optional JSON summary path for the generated matrix.")] = None,
    strict_unknown_capabilities: Annotated[bool, typer.Option(help="Set strict_unknown_capabilities on generated runs.")] = False,
) -> None:
    """Generate a provider x model x suite x concurrency stress matrix."""
    try:
        levels = [int(value.strip()) for value in _split_csv(concurrency_levels)]
        matrix = generate_stress_matrix(
            providers=_split_csv(providers),
            target_ids=_split_csv(targets),
            suites=_split_csv(suites),
            concurrency_levels=levels,
            strict_unknown_capabilities=strict_unknown_capabilities,
        )
    except ValueError as exc:
        raise typer.BadParameter(f"invalid --concurrency-levels: {exc}") from exc
    except ConfigError as exc:
        raise typer.BadParameter(str(exc)) from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(stress_matrix_to_yaml(matrix), encoding="utf-8")
    typer.echo(str(output))
    if summary_json is not None:
        summary_json.parent.mkdir(parents=True, exist_ok=True)
        summary_json.write_text(json.dumps(stress_matrix_summary(matrix), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        typer.echo(str(summary_json))


@models_app.command("campaign-plan")
def models_campaign_plan(
    output_dir: Annotated[Path, typer.Option(help="Output directory for the campaign plan.")] = Path("campaigns/qwen-gemma-local"),
    providers: Annotated[str, typer.Option(help="Comma-separated provider names for the campaign.")] = "afm,mlx-lm,ollama,ollama-native,lm-studio,rapid-mlx,omlx",
    targets: Annotated[str, typer.Option(help="Comma-separated model target ids for the campaign.")] = "qwen3.6-27b-dense,gemma-4-31b-dense",
    suites: Annotated[str, typer.Option(help="Comma-separated built-in suite names for the campaign.")] = "smoke,structured,toolcall,toolsim,trace-replay,agent-fanout,prefill,cache-control,cancellation,lcp-context",
    concurrency: Annotated[int, typer.Option(help="Matrix concurrency per run.")] = 1,
    policy: Annotated[Path | None, typer.Option(help="Optional policy path referenced by generated commands.")] = None,
    name: Annotated[str | None, typer.Option(help="Optional campaign and matrix name.")] = None,
    overwrite: Annotated[bool, typer.Option(help="Replace known campaign artifacts if the output directory already exists.")] = False,
) -> None:
    """Create a no-network multi-suite Qwen/Gemma benchmark campaign plan."""
    try:
        plan = create_campaign_plan(
            output_dir,
            providers=_split_csv(providers),
            targets=_split_csv(targets),
            suites=_split_csv(suites),
            concurrency=concurrency,
            policy=policy,
            name=name,
            overwrite=overwrite,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"manifest: {plan.manifest_path}")
    typer.echo(f"matrix: {plan.matrix_path}")
    typer.echo(f"runbook: {plan.runbook_path}")
    typer.echo(f"report_dir: {plan.report_dir}")


@models_app.command("benchmark-kit")
def models_benchmark_kit(
    output_dir: Annotated[Path, typer.Option(help="Output directory for the benchmark kit.")] = Path("benchmark-kits/qwen-gemma-local"),
    providers: Annotated[str, typer.Option(help="Comma-separated provider names for the kit.")] = "afm,lm-studio",
    targets: Annotated[str, typer.Option(help="Comma-separated model target ids for the kit.")] = "qwen3.6-27b-dense,gemma-4-31b-dense",
    suite: Annotated[str, typer.Option(help="Built-in suite name for the matrix and readiness commands.")] = "trace-replay",
    concurrency: Annotated[int, typer.Option(help="Matrix concurrency per run.")] = 1,
    policy: Annotated[Path | None, typer.Option(help="Optional policy path to include in readiness commands.")] = None,
    name: Annotated[str | None, typer.Option(help="Optional kit and matrix name.")] = None,
    overwrite: Annotated[bool, typer.Option(help="Replace known kit artifacts if the output directory already exists.")] = False,
) -> None:
    """Create a no-network benchmark kit for model/provider comparison campaigns."""
    try:
        kit = create_benchmark_kit(
            output_dir,
            providers=_split_csv(providers),
            targets=_split_csv(targets),
            suite=suite,
            concurrency=concurrency,
            policy=policy,
            name=name,
            overwrite=overwrite,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"manifest: {kit.manifest_path}")
    typer.echo(f"matrix: {kit.matrix_path}")
    typer.echo(f"runbook: {kit.runbook_path}")
    typer.echo(f"readiness_dir: {kit.readiness_dir}")
    typer.echo(f"report_dir: {kit.report_dir}")


@matrix_app.command("report")
def matrix_report(
    summary_json: Annotated[Path, typer.Argument(help="Matrix execution summary JSON produced by --matrix-summary-json.")],
    format: Annotated[
        str,
        typer.Option(help="Comma-separated formats: html,md,json,pdf."),
    ] = "html,md,json",
    output_dir: Annotated[Path | None, typer.Option(help="Optional directory where matrix reports are written.")] = None,
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for matrix report export events.")] = None,
) -> None:
    """Generate reports from an executed matrix summary artifact."""
    formats = [item.strip() for item in format.split(",")]
    try:
        paths = generate_matrix_reports(summary_json, formats, output_dir=output_dir)
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    AuditLogger(audit_log).emit(
        "matrix_report_exported",
        summary_json=str(summary_json),
        output_dir=str(output_dir) if output_dir else None,
        formats=[item for item in formats if item],
        artifacts=[str(path) for path in paths],
    )
    for path in paths:
        typer.echo(str(path))


@matrix_app.command("pressure-audit")
def matrix_pressure_audit(
    matrix: Annotated[Path, typer.Argument(help="Matrix YAML file to inspect without dispatch.")],
    output_json: Annotated[Path | None, typer.Option(help="Optional JSON output path for the pressure audit.")] = None,
) -> None:
    """Audit matrix-level prompt, prefill, static-prefix, and concurrency pressure."""
    try:
        report = audit_matrix_pressure(matrix)
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if output_json is not None:
        typer.echo(str(write_matrix_pressure_json(report, output_json)))
    typer.echo(format_matrix_pressure_report(report), nl=False)


@matrix_app.command("contract-checks")
def matrix_contract_checks(
    matrix: Annotated[Path, typer.Argument(help="Matrix YAML file whose provider/model targets should be checked.")],
    execute: Annotated[bool, typer.Option(help="Execute checks. Without this flag the command only prints a no-network plan.")] = False,
    allow_remote: Annotated[bool, typer.Option(help="Allow executing checks against providers marked remote.")] = False,
    skip_streaming: Annotated[bool, typer.Option(help="Skip streaming contract checks.")] = False,
    skip_structured: Annotated[bool, typer.Option(help="Skip structured-output contract checks.")] = False,
    skip_tools: Annotated[bool, typer.Option(help="Skip tool-call contract checks.")] = False,
    timeout: Annotated[float, typer.Option(help="Per-request timeout in seconds when executing checks.")] = 10.0,
    fail_fast: Annotated[bool, typer.Option(help="Stop on the first provider/model target error.")] = False,
    output_json: Annotated[Path | None, typer.Option(help="Optional JSON output path for the contract-check matrix report.")] = None,
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for matrix contract-check events.")] = None,
) -> None:
    """Plan or execute standardized provider contract checks for every unique matrix target."""
    try:
        report = build_provider_contract_matrix(
            matrix,
            execute=execute,
            allow_remote=allow_remote,
            include_streaming=not skip_streaming,
            include_structured=not skip_structured,
            include_tools=not skip_tools,
            timeout=timeout,
            continue_on_error=not fail_fast,
        )
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    artifacts: list[str] = []
    if output_json is not None:
        artifacts.append(str(write_contract_check_matrix_json(report, output_json)))
    AuditLogger(audit_log).emit(
        "matrix_contract_checks_created",
        matrix=str(matrix),
        mode=report["mode"],
        ok=report["ok"],
        target_count=report["summary"]["targets"],
        artifacts=artifacts,
    )
    if output_json is not None:
        typer.echo(str(output_json))
    typer.echo(format_contract_check_matrix_report(report), nl=False)
    if execute and not report["ok"]:
        raise typer.Exit(1)


@matrix_app.command("scorecard")
def matrix_scorecard(
    summary_json: Annotated[Path, typer.Argument(help="Matrix execution summary JSON produced by --matrix-summary-json.")],
    format: Annotated[
        str,
        typer.Option(help="Comma-separated formats: html,md,json,card,png,pdf."),
    ] = "html,md,json",
    output_dir: Annotated[Path | None, typer.Option(help="Optional directory where matrix scorecards are written.")] = None,
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for matrix scorecard export events.")] = None,
) -> None:
    """Generate publication-oriented leaderboard scorecards from an executed matrix."""
    formats = [item.strip() for item in format.split(",")]
    try:
        paths = generate_matrix_scorecard_reports(summary_json, formats, output_dir=output_dir)
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    AuditLogger(audit_log).emit(
        "matrix_scorecard_exported",
        summary_json=str(summary_json),
        output_dir=str(output_dir) if output_dir else None,
        formats=[item for item in formats if item],
        artifacts=[str(path) for path in paths],
    )
    for path in paths:
        typer.echo(str(path))


@matrix_app.command("publication-bundle")
def matrix_publication_bundle(
    summary_json: Annotated[Path, typer.Argument(help="Matrix execution summary JSON produced by --matrix-summary-json.")],
    report_dir: Annotated[Path | None, typer.Option(help="Directory containing matrix report and scorecard artifacts. Defaults to summary JSON directory.")] = None,
    output_dir: Annotated[Path | None, typer.Option(help="Directory for the matrix publication bundle.")] = None,
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for matrix publication bundle events.")] = None,
) -> None:
    """Create a shareable bundle containing only redacted matrix publication artifacts."""
    try:
        path = create_matrix_publication_bundle(summary_json, report_dir=report_dir, output_dir=output_dir)
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    AuditLogger(audit_log).emit(
        "matrix_publication_bundle_created",
        summary_json=str(summary_json),
        report_dir=str(report_dir) if report_dir else None,
        output_dir=str(output_dir) if output_dir else None,
        artifact=str(path),
    )
    typer.echo(str(path))


@matrix_app.command("saturation-report")
def matrix_saturation_report(
    summary_json: Annotated[Path, typer.Argument(help="Matrix execution summary JSON produced by --matrix-summary-json.")],
    output_json: Annotated[Path | None, typer.Option(help="Optional JSON output path for the saturation report.")] = None,
    max_latency_regression_pct: Annotated[
        float,
        typer.Option(help="Warn when average or p95 latency increases by more than this percentage from the lowest concurrency baseline."),
    ] = 50.0,
    max_decode_drop_pct: Annotated[
        float,
        typer.Option(help="Warn when decode throughput drops by more than this percentage from the lowest concurrency baseline."),
    ] = 25.0,
    max_pass_rate_drop_pct: Annotated[
        float,
        typer.Option(help="Record an error finding when pass rate drops by more than this percentage from the lowest concurrency baseline."),
    ] = 5.0,
    queue_warning_ms: Annotated[
        float,
        typer.Option(help="Warn when queue or rate-limit wait reaches this average milliseconds threshold."),
    ] = 50.0,
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for matrix saturation report events.")] = None,
) -> None:
    """Analyze executed matrix results for concurrency saturation and queueing regressions."""
    try:
        report = build_matrix_saturation_report(
            summary_json,
            max_latency_regression_pct=max_latency_regression_pct,
            max_decode_drop_pct=max_decode_drop_pct,
            max_pass_rate_drop_pct=max_pass_rate_drop_pct,
            queue_warning_ms=queue_warning_ms,
        )
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    artifacts: list[str] = []
    if output_json is not None:
        artifacts.append(str(write_matrix_saturation_json(report, output_json)))
    AuditLogger(audit_log).emit(
        "matrix_saturation_report_exported",
        summary_json=str(summary_json),
        output_json=str(output_json) if output_json else None,
        artifacts=artifacts,
        finding_count=report["summary"]["finding_count"],
    )
    if output_json is not None:
        typer.echo(str(output_json))
    typer.echo(format_matrix_saturation_report(report), nl=False)


@matrix_app.command("gate")
def matrix_gate(
    summary_json: Annotated[Path, typer.Argument(help="Matrix execution summary JSON produced by --matrix-summary-json.")],
    require_all_runs_complete: Annotated[
        bool,
        typer.Option(help="Fail unless completed_runs equals total_runs."),
    ] = False,
    max_failed_runs: Annotated[int | None, typer.Option(help="Maximum allowed failed matrix entries.")] = None,
    min_completed_runs: Annotated[int | None, typer.Option(help="Minimum required completed matrix entries.")] = None,
    min_attempted_runs: Annotated[int | None, typer.Option(help="Minimum required attempted matrix entries.")] = None,
    min_case_pass_rate: Annotated[float | None, typer.Option(help="Minimum aggregate case pass rate percentage.")] = None,
    max_failed_cases: Annotated[int | None, typer.Option(help="Maximum allowed failed benchmark cases across the matrix.")] = None,
    max_failure_class: Annotated[
        list[str] | None,
        typer.Option(
            help=(
                "Maximum allowed failures for a failure class, formatted as class=count. "
                "Repeat for multiple classes, for example engine_protocol_bug=0."
            )
        ),
    ] = None,
    include_failure_class_summary: Annotated[
        bool,
        typer.Option(
            help=(
                "Read referenced normalized results and include observed failure-class counts "
                "without enforcing failure-class thresholds."
            )
        ),
    ] = False,
    max_tool_loop_stop_reason: Annotated[
        list[str] | None,
        typer.Option(
            help=(
                "Maximum allowed tool-loop stop reason count, formatted as reason=count. "
                "Repeat for multiple reasons, for example max_tool_calls_reached=0."
            )
        ),
    ] = None,
    include_tool_loop_summary: Annotated[
        bool,
        typer.Option(
            help=(
                "Read referenced normalized results and include observed tool-loop stop reason counts "
                "without enforcing tool-loop thresholds."
            )
        ),
    ] = False,
    min_judge_verdict_valid_rate: Annotated[
        float | None,
        typer.Option(help="Minimum valid judge-rubric verdict rate percentage across referenced normalized results."),
    ] = None,
    include_judge_verdict_summary: Annotated[
        bool,
        typer.Option(
            help=(
                "Read referenced normalized results and include observed judge-rubric verdict counts "
                "without enforcing a judge-rubric threshold."
            )
        ),
    ] = False,
    max_invalid_tool_calls: Annotated[
        int | None,
        typer.Option(help="Maximum allowed invalid tool-call emissions across referenced normalized results."),
    ] = None,
    min_tool_parser_repair_valid_rate: Annotated[
        float | None,
        typer.Option(help="Minimum valid tool-parser repair rate percentage across referenced normalized results."),
    ] = None,
    include_tool_parser_repair_summary: Annotated[
        bool,
        typer.Option(
            help=(
                "Read referenced normalized results and include observed invalid tool-call and tool-parser "
                "repair counts without enforcing parser-repair thresholds."
            )
        ),
    ] = False,
    output_json: Annotated[Path | None, typer.Option(help="Optional JSON gate report output path.")] = None,
) -> None:
    """Evaluate matrix-level CI/release thresholds from an execution summary."""
    try:
        summary = load_matrix_execution_summary(summary_json)
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    report = evaluate_matrix_gate(
        summary,
        require_all_runs_complete=require_all_runs_complete,
        max_failed_runs=max_failed_runs,
        min_completed_runs=min_completed_runs,
        min_attempted_runs=min_attempted_runs,
        min_case_pass_rate=min_case_pass_rate,
        max_failed_cases=max_failed_cases,
        max_failure_class_counts=_parse_failure_class_thresholds(max_failure_class),
        include_failure_class_summary=include_failure_class_summary,
        max_tool_loop_stop_reason_counts=_parse_count_thresholds(
            max_tool_loop_stop_reason,
            option_name="--max-tool-loop-stop-reason",
            item_name="tool-loop stop reason",
        ),
        include_tool_loop_summary=include_tool_loop_summary,
        min_judge_verdict_valid_rate=min_judge_verdict_valid_rate,
        include_judge_verdict_summary=include_judge_verdict_summary,
        max_invalid_tool_calls=max_invalid_tool_calls,
        min_tool_parser_repair_valid_rate=min_tool_parser_repair_valid_rate,
        include_tool_parser_repair_summary=include_tool_parser_repair_summary,
        result_base_dir=summary_json.parent,
    )
    typer.echo(format_matrix_gate_report(report), nl=False)
    if output_json is not None:
        typer.echo(str(write_matrix_gate_json(report, output_json)))
    if not report.ok:
        raise typer.Exit(code=1)


def _parse_failure_class_thresholds(items: list[str] | None) -> dict[str, int]:
    return _parse_count_thresholds(items, option_name="--max-failure-class", item_name="failure class")


def _parse_count_thresholds(items: list[str] | None, *, option_name: str, item_name: str) -> dict[str, int]:
    thresholds: dict[str, int] = {}
    for raw in items or []:
        if "=" not in raw:
            raise typer.BadParameter(f"{option_name} must use name=count")
        name, value = raw.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            raise typer.BadParameter(f"{option_name} requires a non-empty {item_name}")
        try:
            max_count = int(value)
        except ValueError as exc:
            raise typer.BadParameter(f"{option_name} count must be an integer") from exc
        if max_count < 0:
            raise typer.BadParameter(f"{option_name} count must be non-negative")
        thresholds[name] = max_count
    return thresholds


@app.command()
def export(
    run_dir: Annotated[Path, typer.Argument(help="Run artifact directory.")],
    format: Annotated[str, typer.Option(help="Comma-separated formats: jsonl,csv,parquet.")] = "jsonl,csv",
    output_dir: Annotated[Path | None, typer.Option(help="Optional export output directory.")] = None,
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for result export events.")] = None,
) -> None:
    """Export normalized results from a completed run directory."""
    formats = [item.strip() for item in format.split(",")]
    try:
        paths = export_results(run_dir, formats, output_dir=output_dir)
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    AuditLogger(audit_log).emit(
        "results_exported",
        run_dir=str(run_dir),
        output_dir=str(output_dir) if output_dir else None,
        formats=[item for item in formats if item],
        artifacts=[str(path) for path in paths],
    )
    for path in paths:
        typer.echo(str(path))


@app.command()
def dashboard(
    runs: Annotated[Path, typer.Option(help="Directory containing AgentBlaster run artifacts.")] = Path("runs"),
    host: Annotated[str, typer.Option(help="Host interface to bind. Defaults to loopback.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port to bind.")] = 8765,
    policy: Annotated[Path | None, typer.Option(help="Optional agentblaster.policy.yaml path for dashboard controls.")] = None,
    allow_non_loopback: Annotated[
        bool,
        typer.Option(help="Allow binding the dashboard beyond loopback on trusted networks only."),
    ] = False,
    auth_token_env: Annotated[
        str | None,
        typer.Option(help="Environment variable containing the dashboard auth token. Required for non-loopback binds."),
    ] = None,
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for dashboard start events.")] = None,
) -> None:
    """Serve the local dashboard for completed benchmark runs."""
    auth_token = _dashboard_auth_token_from_env(auth_token_env)
    try:
        assert_dashboard_bind_allowed(
            host,
            allow_non_loopback=allow_non_loopback,
            auth_configured=auth_token is not None,
        )
        security_policy = load_policy(policy)
        enforce_dashboard_policy(
            security_policy,
            host=host,
            port=port,
            allow_non_loopback=allow_non_loopback,
            auth_configured=auth_token is not None,
        )
    except AgentBlasterError as exc:
        AuditLogger(audit_log).emit(
            "policy_violation",
            surface="dashboard",
            host=host,
            port=port,
            allow_non_loopback=allow_non_loopback,
            auth_enabled=auth_token is not None,
            reason=str(exc),
        )
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"AgentBlaster dashboard: http://{host}:{port}")
    typer.echo(f"dashboard_auth: {'enabled' if auth_token else 'disabled'}")
    serve_dashboard(
        runs,
        host=host,
        port=port,
        allow_non_loopback=allow_non_loopback,
        auth_token=auth_token,
        audit_log=audit_log,
        policy=security_policy,
    )


def _dashboard_auth_token_from_env(env_name: str | None) -> str | None:
    if env_name is None:
        return None
    token = os.environ.get(env_name)
    if not token:
        raise typer.BadParameter(f"dashboard auth token env var is not set: {env_name}")
    if len(token) < 16:
        raise typer.BadParameter("dashboard auth token must be at least 16 characters")
    return token


def _secret_from_env(env_name: str, label: str) -> str:
    value = os.environ.get(env_name)
    if not value:
        raise typer.BadParameter(f"{label} env var is not set: {env_name}")
    return value


@app.command()
def compare(
    run_dirs: Annotated[list[Path], typer.Argument(help="Two or more run artifact directories.")],
    output_json: Annotated[Path | None, typer.Option(help="Optional JSON comparison output path.")] = None,
) -> None:
    """Compare completed run directories."""
    rows = compare_runs(run_dirs)
    typer.echo(format_comparison_table(rows))
    if output_json is not None:
        typer.echo(str(write_comparison_json(run_dirs, output_json)))


@app.command("compare-gate")
def compare_gate(
    baseline_run_dir: Annotated[Path, typer.Argument(help="Baseline run artifact directory.")],
    candidate_run_dir: Annotated[Path, typer.Argument(help="Candidate run artifact directory.")],
    min_pass_rate: Annotated[float | None, typer.Option(help="Minimum candidate pass rate percentage.")] = None,
    max_pass_rate_drop: Annotated[float | None, typer.Option(help="Maximum allowed pass-rate drop in percentage points.")] = None,
    max_avg_latency_regression_pct: Annotated[
        float | None,
        typer.Option(help="Maximum allowed average latency regression percentage."),
    ] = None,
    max_p95_latency_regression_pct: Annotated[
        float | None,
        typer.Option(help="Maximum allowed p95 latency regression percentage."),
    ] = None,
    max_avg_ttft_regression_pct: Annotated[
        float | None,
        typer.Option(help="Maximum allowed average TTFT regression percentage."),
    ] = None,
    min_decode_tokens_per_second_ratio: Annotated[
        float | None,
        typer.Option(help="Minimum candidate/baseline decode throughput ratio."),
    ] = None,
    output_json: Annotated[Path | None, typer.Option(help="Optional JSON gate report output path.")] = None,
) -> None:
    """Evaluate a baseline-vs-candidate comparison gate for CI/release regression checks."""
    report = evaluate_comparison_gate(
        baseline_run_dir,
        candidate_run_dir,
        min_pass_rate=min_pass_rate,
        max_pass_rate_drop=max_pass_rate_drop,
        max_avg_latency_regression_pct=max_avg_latency_regression_pct,
        max_p95_latency_regression_pct=max_p95_latency_regression_pct,
        max_avg_ttft_regression_pct=max_avg_ttft_regression_pct,
        min_decode_tokens_per_second_ratio=min_decode_tokens_per_second_ratio,
    )
    typer.echo(format_comparison_gate_report(report), nl=False)
    if output_json is not None:
        typer.echo(str(write_comparison_gate_json(report, output_json)))
    if not report.ok:
        raise typer.Exit(code=1)


@app.command("telemetry-audit")
def telemetry_audit_command(
    run_dir: Annotated[Path, typer.Argument(help="Completed run artifact directory.")],
    required_field: Annotated[
        list[str] | None,
        typer.Option("--required-field", help="Normalized telemetry field required for comparability. Repeatable."),
    ] = None,
    min_required_completeness: Annotated[
        float,
        typer.Option(help="Minimum completeness ratio for required fields, between 0 and 1."),
    ] = 1.0,
    output_json: Annotated[Path | None, typer.Option(help="Optional telemetry audit JSON output path.")] = None,
    fail_on_findings: Annotated[
        bool,
        typer.Option("--fail-on-findings/--no-fail-on-findings", help="Exit non-zero when blocker findings are present."),
    ] = False,
) -> None:
    """Audit normalized result telemetry provenance for cross-engine comparability."""
    try:
        report = audit_run_telemetry(
            run_dir,
            required_fields=required_field,
            min_required_completeness=min_required_completeness,
        )
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if output_json is not None:
        typer.echo(str(write_telemetry_audit_json(report, output_json)))
    typer.echo(format_telemetry_audit(report), nl=False)
    if fail_on_findings and not report["summary"]["comparable_core_ok"]:
        raise typer.Exit(code=1)


@app.command()
def cleanup(
    run_dir: Annotated[Path, typer.Argument(help="Run artifact directory.")],
    raw: Annotated[bool, typer.Option(help="Delete raw trace artifacts.")] = True,
    reports: Annotated[bool, typer.Option(help="Delete generated report artifacts.")] = False,
    exports: Annotated[bool, typer.Option(help="Delete exported result artifacts.")] = False,
    caches: Annotated[bool, typer.Option(help="Delete generated cache artifacts within the run directory.")] = False,
    temp: Annotated[bool, typer.Option(help="Delete generated temporary artifacts within the run directory.")] = False,
    bundles: Annotated[bool, typer.Option(help="Delete generated publication/evidence bundle artifacts within the run directory.")] = False,
    all_artifacts: Annotated[bool, typer.Option(help="Delete the entire run directory.")] = False,
    execute: Annotated[bool, typer.Option(help="Apply cleanup. Defaults to dry-run planning.")] = False,
    output_json: Annotated[Path | None, typer.Option(help="Optional JSON path for cleanup plan or execution result.")] = None,
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for manual cleanup events.")] = None,
    require_audit_log: Annotated[bool, typer.Option(help="Fail unless --audit-log is supplied.")] = False,
    policy: Annotated[Path | None, typer.Option(help="Optional security policy file for cleanup controls.")] = None,
) -> None:
    """Plan or apply cleanup of generated run artifacts."""
    try:
        cleanup_audit_required = require_audit_log or load_policy(policy).require_cleanup_audit_log
        if cleanup_audit_required and audit_log is None:
            raise ConfigError("--require-audit-log requires --audit-log")
        planned = plan_cleanup_run(
            run_dir,
            raw=raw,
            reports=reports,
            exports=exports,
            caches=caches,
            temp=temp,
            bundles=bundles,
            all_artifacts=all_artifacts,
        )
        removed = (
            cleanup_run(
                run_dir,
                raw=raw,
                reports=reports,
                exports=exports,
                caches=caches,
                temp=temp,
                bundles=bundles,
                all_artifacts=all_artifacts,
            )
            if execute
            else planned
        )
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    payload = {
        "schema_version": CLEANUP_PLAN_SCHEMA_VERSION,
        "report_type": "manual_cleanup_execution" if execute else "manual_cleanup_plan",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "run_dir": str(run_dir),
        "execute": execute,
        "selectors": {
            "raw": raw,
            "reports": reports,
            "exports": exports,
            "caches": caches,
            "temp": temp,
            "bundles": bundles,
            "all_artifacts": all_artifacts,
        },
        "action_count": len(removed),
        "paths": [str(path) for path in removed],
        "security": {
            "contains_raw_secrets": False,
            "contains_raw_provider_payloads": False,
            "reads_keyring_values": False,
            "contacts_providers": False,
            "dry_run_default": True,
            "contains_local_paths": True,
            "direct_publication_safe": False,
            "audit_log_required": cleanup_audit_required,
        },
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        typer.echo(str(output_json))
    AuditLogger(audit_log).emit(
        "manual_cleanup_executed" if execute else "manual_cleanup_planned",
        **payload,
    )
    if not removed:
        typer.echo("no matching cleanup artifacts")
        return
    prefix = "removed" if execute else "would-remove"
    for path in removed:
        typer.echo(f"{prefix}\t{path}")


@app.command("cleanup-expired")
def cleanup_expired(
    runs: Annotated[Path, typer.Option(help="Directory containing AgentBlaster run artifacts.")] = Path("runs"),
    execute: Annotated[bool, typer.Option(help="Apply planned retention cleanup actions. Defaults to dry-run.")] = False,
    output_json: Annotated[Path | None, typer.Option(help="Optional JSON path for cleanup plan or execution result.")] = None,
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for retention cleanup events.")] = None,
    require_audit_log: Annotated[bool, typer.Option(help="Fail unless --audit-log is supplied.")] = False,
    policy: Annotated[Path | None, typer.Option(help="Optional security policy file for cleanup controls.")] = None,
) -> None:
    """Plan or apply cleanup for artifacts whose retention metadata has expired."""
    try:
        cleanup_audit_required = require_audit_log or load_policy(policy).require_cleanup_audit_log
        if cleanup_audit_required and audit_log is None:
            raise ConfigError("--require-audit-log requires --audit-log")
        actions = plan_expired_cleanup(runs)
        result_actions = apply_expired_cleanup(actions) if execute else actions
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    action_payloads = [action.model_dump(mode="json") for action in result_actions]
    payload = {
        "schema_version": RETENTION_CLEANUP_SCHEMA_VERSION,
        "report_type": "retention_cleanup_execution" if execute else "retention_cleanup_plan",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "runs_dir": str(runs),
        "execute": execute,
        "action_count": len(result_actions),
        "actions": action_payloads,
        "security": {
            "contains_raw_secrets": False,
            "contains_raw_provider_payloads": False,
            "reads_keyring_values": False,
            "contacts_providers": False,
            "dry_run_default": True,
            "contains_local_paths": True,
            "direct_publication_safe": False,
            "audit_log_required": cleanup_audit_required,
        },
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        typer.echo(str(output_json))
    AuditLogger(audit_log).emit(
        "retention_cleanup_executed" if execute else "retention_cleanup_planned",
        runs_dir=str(runs),
        execute=execute,
        action_count=len(result_actions),
        actions=action_payloads,
        report_schema=RETENTION_CLEANUP_SCHEMA_VERSION,
        audit_log_required=cleanup_audit_required,
    )
    if not result_actions:
        typer.echo("no expired artifacts")
        return
    for action in result_actions:
        if execute:
            removed = ",".join(action.removed) if action.removed else "-"
            typer.echo(f"{action.action}\t{action.run_id}\tremoved={removed}\t{action.reason}")
        else:
            typer.echo(f"{action.action}\t{action.run_id}\texpires={action.expired_at}\t{action.reason}")


@app.command()
def verify(
    run_dir: Annotated[Path, typer.Argument(help="Run artifact directory.")],
    strict: Annotated[bool, typer.Option(help="Fail if untracked extra files are present.")] = False,
) -> None:
    """Verify a completed run against its integrity manifest."""
    try:
        result = verify_run_integrity(run_dir, allow_extra=not strict)
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"run_id: {result.run_id}")
    typer.echo(f"ok: {str(result.ok).lower()}")
    typer.echo(f"checked: {result.checked}")
    for label, values in [("missing", result.missing), ("changed", result.changed), ("extra", result.extra)]:
        if values:
            typer.echo(f"{label}:")
            for value in values:
                typer.echo(f"- {value}")
    if not result.ok:
        raise typer.Exit(code=1)


@app.command("sign")
def sign(
    run_dir: Annotated[Path, typer.Argument(help="Run artifact directory.")],
    key_env: Annotated[str, typer.Option(help="Environment variable containing the HMAC signing key.")],
    key_id: Annotated[str, typer.Option(help="Non-secret signing key identifier written to signature.json.")] = "local",
) -> None:
    """Create signature.json for a completed run integrity manifest."""
    key = _secret_from_env(key_env, "signing key")
    try:
        path = sign_run_integrity(run_dir, key=key, key_id=key_id)
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(str(path))


@app.command("verify-signature")
def verify_signature(
    run_dir: Annotated[Path, typer.Argument(help="Run artifact directory.")],
    key_env: Annotated[str, typer.Option(help="Environment variable containing the HMAC signing key.")],
    strict: Annotated[bool, typer.Option(help="Fail if untracked extra files are present.")] = False,
) -> None:
    """Verify signature.json and the underlying integrity manifest."""
    key = _secret_from_env(key_env, "signing key")
    try:
        result = verify_run_signature(run_dir, key=key, allow_extra=not strict)
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"run_id: {result.run_id}")
    typer.echo(f"ok: {str(result.ok).lower()}")
    typer.echo(f"signature_ok: {str(result.signature_ok).lower()}")
    typer.echo(f"integrity_ok: {str(result.integrity_ok).lower()}")
    typer.echo(f"key_id: {result.key_id}")
    typer.echo(f"checked: {result.checked}")
    for label, values in [("missing", result.missing), ("changed", result.changed), ("extra", result.extra)]:
        if values:
            typer.echo(f"{label}:")
            for value in values:
                typer.echo(f"- {value}")
    if not result.ok:
        raise typer.Exit(code=1)


@app.command()
def bundle(
    run_dir: Annotated[Path, typer.Argument(help="Run artifact directory.")],
    output_dir: Annotated[Path | None, typer.Option(help="Directory for the replay bundle.")] = None,
    strict: Annotated[bool, typer.Option(help="Fail if untracked extra files are present.")] = False,
) -> None:
    """Create a portable replay bundle from a verified completed run."""
    try:
        path = create_replay_bundle(run_dir, output_dir=output_dir, strict=strict)
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(str(path))


@app.command("publication-bundle")
def publication_bundle(
    run_dir: Annotated[Path, typer.Argument(help="Run artifact directory.")],
    output_dir: Annotated[Path | None, typer.Option(help="Directory for the publication bundle.")] = None,
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for publication bundle events.")] = None,
) -> None:
    """Create a shareable bundle containing only redacted publication artifacts."""
    try:
        path = create_publication_bundle(run_dir, output_dir=output_dir)
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    AuditLogger(audit_log).emit(
        "publication_bundle_created",
        run_dir=str(run_dir),
        output_dir=str(output_dir) if output_dir else None,
        artifact=str(path),
    )
    typer.echo(str(path))


@providers_app.command("readiness")
def providers_readiness(
    provider: Annotated[str, typer.Option(help="Configured provider profile to inspect.")],
    suite: Annotated[str, typer.Option(help="Built-in suite name to inspect.")] = "smoke",
    suite_file: Annotated[Path | None, typer.Option(help="Optional YAML suite definition to inspect instead of a built-in suite.")] = None,
    model: Annotated[str | None, typer.Option(help="Model id intended for this benchmark run.")] = None,
    policy: Annotated[Path | None, typer.Option(help="Optional security policy file.")] = None,
    strict_unknown: Annotated[bool, typer.Option(help="Treat unknown provider capabilities as readiness blockers.")] = False,
    output_json: Annotated[Path | None, typer.Option(help="Optional JSON output path for the readiness dossier.")] = None,
) -> None:
    """Build a no-network benchmark readiness dossier for one provider/suite pair."""
    provider_config = ProviderStore().get(provider)
    suite_definition = load_suite_file(suite_file) if suite_file is not None else get_builtin_suite(suite)
    report = build_readiness_dossier(
        provider=provider_config,
        suite=suite_definition,
        policy=load_policy(policy),
        model=model,
        strict_unknown=strict_unknown,
    )
    if output_json is not None:
        write_readiness_json(report, output_json)
    typer.echo(format_readiness_report(report), nl=False)
    if not report["ready"]:
        raise typer.Exit(1)


@providers_app.command("metric-coverage")
def providers_metric_coverage(
    provider: Annotated[str | None, typer.Option(help="Configured provider profile to inspect. Omit with --catalog.")] = None,
    catalog: Annotated[bool, typer.Option(help="Show static coverage catalog for supported contract families.")] = False,
    output_json: Annotated[Path | None, typer.Option(help="Optional JSON output path for metric coverage.")] = None,
) -> None:
    """Report normalized metric coverage for provider stats comparability."""
    if catalog:
        report = metric_coverage_catalog()
    else:
        if not provider:
            raise typer.BadParameter("--provider is required unless --catalog is set")
        report = metric_coverage_for_provider(ProviderStore().get(provider))
    if output_json is not None:
        write_metric_coverage_json(report, output_json)
    typer.echo(format_metric_coverage_report(report), nl=False)


@catalog_app.command("normalize-telemetry")
def catalog_normalize_telemetry(
    input_json: Annotated[Path, typer.Argument(help="Raw provider response JSON file to normalize.")],
    contract: Annotated[ApiContract, typer.Option(help="Provider contract for the raw response.")],
    native_adapter: Annotated[str | None, typer.Option(help="Optional native adapter hint, for example ollama or lm-studio.")] = None,
    latency_ms: Annotated[float | None, typer.Option(help="Optional measured request latency in milliseconds.")] = None,
    ttft_ms: Annotated[float | None, typer.Option(help="Optional measured time-to-first-token in milliseconds.")] = None,
    output_json: Annotated[Path | None, typer.Option(help="Optional normalized telemetry JSON output path.")] = None,
) -> None:
    """Normalize a raw provider response sample into AgentBlaster telemetry fields."""
    try:
        raw = json.loads(input_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise typer.BadParameter(f"invalid input JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise typer.BadParameter("input JSON must be an object")
    report = normalize_response_telemetry(
        contract,
        raw,
        native_adapter=native_adapter,
        latency_ms=latency_ms,
        ttft_ms=ttft_ms,
    )
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(normalized_response_telemetry_json(report), encoding="utf-8")
        typer.echo(str(output_json))
    typer.echo(format_normalized_response_telemetry(report), nl=False)


@providers_app.command("contract-check")
def providers_contract_check(
    provider: Annotated[str, typer.Option(help="Configured provider profile to inspect or execute against.")],
    model: Annotated[str | None, typer.Option(help="Model id to use when executing checks.")] = None,
    execute: Annotated[bool, typer.Option(help="Execute checks. Without this flag the command only prints a no-network plan.")] = False,
    allow_remote: Annotated[bool, typer.Option(help="Allow executing checks against providers marked remote.")] = False,
    skip_streaming: Annotated[bool, typer.Option(help="Skip streaming contract checks.")] = False,
    skip_structured: Annotated[bool, typer.Option(help="Skip structured-output contract checks.")] = False,
    skip_tools: Annotated[bool, typer.Option(help="Skip tool-call contract checks.")] = False,
    timeout: Annotated[float, typer.Option(help="Per-request timeout in seconds when executing checks.")] = 10.0,
    output_json: Annotated[Path | None, typer.Option(help="Optional JSON output path for the contract-check report.")] = None,
) -> None:
    """Plan or execute standardized provider contract checks."""
    provider_config = ProviderStore().get(provider)
    try:
        if execute:
            report = run_provider_contract_check(
                provider_config,
                model=model,
                allow_remote=allow_remote,
                include_streaming=not skip_streaming,
                include_structured=not skip_structured,
                include_tools=not skip_tools,
                timeout=timeout,
            )
        else:
            report = provider_contract_plan(
                provider_config,
                model=model,
                include_streaming=not skip_streaming,
                include_structured=not skip_structured,
                include_tools=not skip_tools,
            )
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if output_json is not None:
        write_contract_check_json(report, output_json)
    typer.echo(format_contract_check_report(report), nl=False)
    if execute and report["summary"]["failed"]:
        raise typer.Exit(1)


@quality_app.command("tiers")
def quality_tiers() -> None:
    """List internal AgentBlaster app-test tiers."""
    for tier in list_test_tiers():
        ci = "ci" if tier.ci_default else "opt-in"
        typer.echo(f"{tier.name}\t{ci}\t{tier.marker_expression}\t{tier.purpose}")


@quality_app.command("command")
def quality_command(
    tier: Annotated[str, typer.Argument(help="Test tier name, for example normal, security, gui, or release.")],
) -> None:
    """Print the recommended command for an app-test tier without executing it."""
    try:
        typer.echo(get_test_tier(tier).command)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


@quality_app.command("chrome-checklist")
def quality_chrome_checklist(
    output: Annotated[Path | None, typer.Option(help="Optional markdown output path.")] = None,
) -> None:
    """Print or write the Chrome/Codex dashboard validation checklist."""
    checklist = render_chrome_validation_markdown()
    if output is None:
        typer.echo(checklist, nl=False)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(checklist, encoding="utf-8")
    typer.echo(str(output))


@quality_app.command("chrome-plan")
def quality_chrome_plan(
    output: Annotated[Path | None, typer.Option(help="Optional output path for the GUI plan artifact.")] = None,
    output_format: Annotated[str, typer.Option("--format", help="Plan format: json or md.")] = "json",
    dashboard_url: Annotated[str, typer.Option(help="Dashboard URL expected during Chrome/Codex validation.")] = "http://127.0.0.1:8765",
    fixture_profile: Annotated[str, typer.Option(help="Named fixture profile expected for deterministic GUI validation.")] = "deterministic-redacted",
) -> None:
    """Print or write a deterministic Chrome/Codex GUI self-test plan."""
    normalized = output_format.strip().lower()
    if normalized == "json":
        rendered = render_chrome_gui_plan_json(dashboard_url=dashboard_url, fixture_profile=fixture_profile)
    elif normalized in {"md", "markdown"}:
        rendered = render_chrome_gui_plan_markdown(dashboard_url=dashboard_url, fixture_profile=fixture_profile)
    else:
        raise typer.BadParameter("format must be json or md")
    if output is None:
        typer.echo(rendered, nl=False)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    typer.echo(str(output))


@quality_app.command("dashboard-fixture")
def quality_dashboard_fixture(
    output: Annotated[Path, typer.Option(help="Output runs directory for deterministic dashboard GUI fixtures.")] = Path("tests/fixtures/dashboard-runs"),
    profile: Annotated[str, typer.Option(help="Fixture profile name.")] = "deterministic-redacted",
    overwrite: Annotated[bool, typer.Option(help="Replace known deterministic fixture artifacts if they already exist.")] = False,
) -> None:
    """Write deterministic redacted dashboard run fixtures for GUI selftests."""
    try:
        fixture = write_dashboard_fixture(output, profile=profile, overwrite=overwrite)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"profile: {fixture.profile}")
    typer.echo(f"runs_dir: {fixture.runs_dir}")
    typer.echo(f"manifest: {fixture.manifest_path}")
    for run_id in fixture.run_ids:
        typer.echo(f"run: {run_id}")


@evidence_app.command("index")
def evidence_index(
    name: Annotated[str, typer.Option(help="Evidence index name.")] = "evidence-index",
    artifact: Annotated[list[Path] | None, typer.Option(help="Review artifact path. Can be repeated.")] = None,
    output_json: Annotated[Path | None, typer.Option(help="Optional evidence index JSON output path.")] = None,
) -> None:
    """Create a compact no-dispatch index over supplied review artifacts."""
    try:
        report = build_evidence_index(name=name, artifacts=artifact or [])
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if output_json is not None:
        typer.echo(str(write_evidence_index(report, output_json)))
    typer.echo(format_evidence_index(report), nl=False)


@security_app.command("posture")
def security_posture(
    name: Annotated[str, typer.Option(help="Security posture report name.")] = "security-posture",
    policy: Annotated[Path | None, typer.Option(help="Optional enterprise security policy YAML to summarize.")] = None,
    provider_audit: Annotated[list[Path] | None, typer.Option("--provider-audit", help="Provider audit JSON artifact. Can be repeated.")] = None,
    redaction_scan: Annotated[list[Path] | None, typer.Option("--redaction-scan", help="Redaction scan JSON artifact. Can be repeated.")] = None,
    review_artifact: Annotated[list[Path] | None, typer.Option("--review-artifact", help="Review artifact JSON to summarize by security flags. Can be repeated.")] = None,
    output_json: Annotated[Path | None, typer.Option(help="Optional security posture JSON output path.")] = None,
    output_md: Annotated[Path | None, typer.Option(help="Optional security posture Markdown output path.")] = None,
    fail_on_blockers: Annotated[
        bool,
        typer.Option("--fail-on-blockers/--no-fail-on-blockers", help="Exit non-zero when posture blockers are present."),
    ] = False,
) -> None:
    """Create a static enterprise security posture report without resolving secrets or contacting providers."""
    try:
        report = build_security_posture_report(
            name=name,
            policy_path=policy,
            provider_audits=provider_audit,
            redaction_scans=redaction_scan,
            review_artifacts=review_artifact,
        )
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    artifacts: list[str] = []
    if output_json is not None:
        artifacts.append(str(write_security_posture_json(report, output_json)))
    if output_md is not None:
        artifacts.append(str(write_security_posture_markdown(report, output_md)))
    if artifacts:
        for artifact in artifacts:
            typer.echo(artifact)
    else:
        typer.echo(format_security_posture_report(report), nl=False)
    if fail_on_blockers and not report["ready"]:
        raise typer.Exit(code=1)


@release_app.command("provenance")
def release_provenance(
    output: Annotated[Path, typer.Option(help="Output JSON path for the release provenance artifact.")],
    project_root: Annotated[Path, typer.Option(help="Project root containing pyproject.toml.")] = Path("."),
    include_installed: Annotated[
        bool,
        typer.Option(help="Include installed Python package names and versions from the current environment."),
    ] = False,
    no_source_hashes: Annotated[
        bool,
        typer.Option(help="Skip hashing source and metadata files."),
    ] = False,
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for release artifact events.")] = None,
) -> None:
    """Write a redaction-safe release provenance and lightweight SBOM JSON artifact."""
    try:
        path = write_release_provenance(
            output,
            project_root=project_root,
            include_installed=include_installed,
            include_source_hashes=not no_source_hashes,
        )
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    AuditLogger(audit_log).emit(
        "release_provenance_created",
        artifact=str(path),
        project_root=str(project_root),
        include_installed=include_installed,
        include_source_hashes=not no_source_hashes,
    )
    typer.echo(str(path))


@release_app.command("packaging-readiness")
def release_packaging_readiness(
    project_root: Annotated[Path, typer.Option(help="Project root containing pyproject.toml.")] = Path("."),
    output_json: Annotated[Path | None, typer.Option(help="Optional output JSON path for the packaging readiness artifact.")] = None,
    fail_on_gaps: Annotated[
        bool,
        typer.Option("--fail-on-gaps/--no-fail-on-gaps", help="Exit non-zero when static packaging readiness gaps are found."),
    ] = False,
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for release readiness events.")] = None,
) -> None:
    """Generate a static package metadata, entrypoint, docs, and test-marker readiness report."""
    output = output_json or Path("reports/packaging-readiness.json")
    try:
        path = write_packaging_readiness(output, project_root=project_root)
        report_payload = json.loads(path.read_text(encoding="utf-8"))
    except (AgentBlasterError, OSError, json.JSONDecodeError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    AuditLogger(audit_log).emit(
        "packaging_readiness_created",
        artifact=str(path),
        project_root=str(project_root),
        ok=report_payload["ok"],
        failed=report_payload["failed"],
    )
    typer.echo(format_packaging_readiness(report_payload), nl=False)
    typer.echo(str(path))
    if fail_on_gaps and not report_payload["ok"]:
        raise typer.Exit(code=1)


@release_app.command("qualification-bundle")
def release_qualification_bundle(
    output_dir: Annotated[Path, typer.Option(help="Directory for the release qualification bundle.")],
    name: Annotated[str, typer.Option(help="Release qualification bundle name.")] = "release-qualification",
    evidence_bundle: Annotated[list[Path] | None, typer.Option(help="Evidence bundle artifact. Can be repeated.")] = None,
    provider_audit: Annotated[list[Path] | None, typer.Option(help="Provider audit JSON artifact. Can be repeated.")] = None,
    provider_contract_check: Annotated[list[Path] | None, typer.Option(help="Executed provider contract-check JSON artifact. Can be repeated.")] = None,
    provider_contract_matrix: Annotated[list[Path] | None, typer.Option(help="Executed provider contract-check matrix JSON artifact. Can be repeated.")] = None,
    comparison_gate: Annotated[list[Path] | None, typer.Option(help="Comparison gate JSON artifact. Can be repeated.")] = None,
    matrix_gate: Annotated[list[Path] | None, typer.Option(help="Matrix gate JSON artifact. Can be repeated.")] = None,
    telemetry_audit: Annotated[list[Path] | None, typer.Option(help="Telemetry audit JSON artifact. Can be repeated.")] = None,
    matrix_pressure_audit: Annotated[list[Path] | None, typer.Option(help="Matrix pressure audit JSON artifact. Can be repeated.")] = None,
    matrix_saturation_report: Annotated[list[Path] | None, typer.Option(help="Matrix saturation report JSON artifact. Can be repeated.")] = None,
    matrix_scorecard: Annotated[list[Path] | None, typer.Option(help="Matrix scorecard JSON artifact. Can be repeated.")] = None,
    implementation_status: Annotated[list[Path] | None, typer.Option(help="Implementation status JSON artifact. Can be repeated.")] = None,
    campaign_preflight_manifest: Annotated[list[Path] | None, typer.Option(help="Campaign preflight manifest JSON artifact. Can be repeated.")] = None,
    benchmark_readiness: Annotated[list[Path] | None, typer.Option(help="Benchmark readiness dossier JSON artifact. Can be repeated.")] = None,
    benchmark_readiness_list: Annotated[
        list[Path] | None,
        typer.Option(help="Text file with one benchmark readiness dossier JSON path per line. Can be repeated."),
    ] = None,
    claim_readiness: Annotated[list[Path] | None, typer.Option(help="Claim readiness JSON artifact. Can be repeated.")] = None,
    engine_advisory: Annotated[list[Path] | None, typer.Option(help="Engine improvement advisory JSON artifact. Can be repeated.")] = None,
    evidence_index: Annotated[list[Path] | None, typer.Option(help="Evidence index JSON artifact. Can be repeated.")] = None,
    suite_audit: Annotated[list[Path] | None, typer.Option(help="Suite audit JSON artifact. Can be repeated.")] = None,
    metric_coverage: Annotated[list[Path] | None, typer.Option(help="Metric coverage JSON artifact. Can be repeated.")] = None,
    normalized_telemetry: Annotated[list[Path] | None, typer.Option(help="Normalized telemetry sample JSON artifact. Can be repeated.")] = None,
    release_provenance: Annotated[Path | None, typer.Option(help="Release provenance JSON artifact.")] = None,
    publication_bundle: Annotated[list[Path] | None, typer.Option(help="Publication bundle artifact. Can be repeated.")] = None,
    publication_brief: Annotated[list[Path] | None, typer.Option(help="Publication brief JSON artifact. Can be repeated.")] = None,
    protocol_repair_posture: Annotated[list[Path] | None, typer.Option(help="Protocol repair posture JSON artifact. Can be repeated.")] = None,
    matrix_publication_bundle: Annotated[list[Path] | None, typer.Option(help="Matrix publication bundle artifact. Can be repeated.")] = None,
    workflow_readiness: Annotated[list[Path] | None, typer.Option(help="Workflow readiness JSON artifact. Can be repeated.")] = None,
    security_posture: Annotated[list[Path] | None, typer.Option(help="Security posture JSON artifact. Can be repeated.")] = None,
    harness_review: Annotated[list[Path] | None, typer.Option(help="Harness review JSON artifact. Can be repeated.")] = None,
    suite_calibration_report: Annotated[list[Path] | None, typer.Option(help="Suite calibration report JSON artifact. Can be repeated.")] = None,
    selftest_report: Annotated[list[Path] | None, typer.Option(help="Selftest report artifact. Can be repeated.")] = None,
    sdlc_validation_manifest: Annotated[list[Path] | None, typer.Option(help="SDLC validation manifest JSON artifact. Can be repeated.")] = None,
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for release qualification events.")] = None,
) -> None:
    """Create a redaction-safe release qualification package from gate and evidence artifacts."""
    resolved_benchmark_readiness = _benchmark_readiness_paths(benchmark_readiness, benchmark_readiness_list)
    try:
        path = create_release_qualification_bundle(
            name=name,
            output_dir=output_dir,
            evidence_bundles=evidence_bundle,
            provider_audits=provider_audit,
            provider_contract_checks=provider_contract_check,
            provider_contract_matrices=provider_contract_matrix,
            comparison_gates=comparison_gate,
            matrix_gates=matrix_gate,
            telemetry_audits=telemetry_audit,
            matrix_pressure_audits=matrix_pressure_audit,
            matrix_saturation_reports=matrix_saturation_report,
            matrix_scorecards=matrix_scorecard,
            implementation_status_reports=implementation_status,
            campaign_preflight_manifests=campaign_preflight_manifest,
            benchmark_readiness_reports=resolved_benchmark_readiness,
            claim_readiness_reports=claim_readiness,
            engine_advisories=engine_advisory,
            evidence_indexes=evidence_index,
            suite_audits=suite_audit,
            metric_coverage_reports=metric_coverage,
            normalized_telemetry_reports=normalized_telemetry,
            release_provenance=release_provenance,
            publication_bundles=publication_bundle,
            publication_briefs=publication_brief,
            protocol_repair_postures=protocol_repair_posture,
            matrix_publication_bundles=matrix_publication_bundle,
            workflow_readiness_reports=workflow_readiness,
            security_postures=security_posture,
            harness_reviews=harness_review,
            suite_calibration_reports=suite_calibration_report,
            selftest_reports=selftest_report,
            sdlc_validation_manifests=sdlc_validation_manifest,
        )
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    AuditLogger(audit_log).emit(
        "release_qualification_bundle_created",
        artifact=str(path),
        name=name,
        evidence_bundles=[str(item) for item in evidence_bundle or []],
        provider_audits=[str(item) for item in provider_audit or []],
        provider_contract_checks=[str(item) for item in provider_contract_check or []],
        provider_contract_matrices=[str(item) for item in provider_contract_matrix or []],
        comparison_gates=[str(item) for item in comparison_gate or []],
        matrix_gates=[str(item) for item in matrix_gate or []],
        telemetry_audits=[str(item) for item in telemetry_audit or []],
        matrix_pressure_audits=[str(item) for item in matrix_pressure_audit or []],
        matrix_saturation_reports=[str(item) for item in matrix_saturation_report or []],
        matrix_scorecards=[str(item) for item in matrix_scorecard or []],
        implementation_status_reports=[str(item) for item in implementation_status or []],
        campaign_preflight_manifests=[str(item) for item in campaign_preflight_manifest or []],
        benchmark_readiness_reports=[str(item) for item in resolved_benchmark_readiness or []],
        benchmark_readiness_lists=[str(item) for item in benchmark_readiness_list or []],
        claim_readiness_reports=[str(item) for item in claim_readiness or []],
        engine_advisories=[str(item) for item in engine_advisory or []],
        evidence_indexes=[str(item) for item in evidence_index or []],
        suite_audits=[str(item) for item in suite_audit or []],
        metric_coverage_reports=[str(item) for item in metric_coverage or []],
        normalized_telemetry_reports=[str(item) for item in normalized_telemetry or []],
        release_provenance=str(release_provenance) if release_provenance else None,
        publication_bundles=[str(item) for item in publication_bundle or []],
        publication_briefs=[str(item) for item in publication_brief or []],
        protocol_repair_postures=[str(item) for item in protocol_repair_posture or []],
        matrix_publication_bundles=[str(item) for item in matrix_publication_bundle or []],
        workflow_readiness_reports=[str(item) for item in workflow_readiness or []],
        security_postures=[str(item) for item in security_posture or []],
        harness_reviews=[str(item) for item in harness_review or []],
        suite_calibration_reports=[str(item) for item in suite_calibration_report or []],
        selftest_reports=[str(item) for item in selftest_report or []],
        sdlc_validation_manifests=[str(item) for item in sdlc_validation_manifest or []],
    )
    typer.echo(str(path))


@release_app.command("claim-readiness")
def release_claim_readiness(
    name: Annotated[str, typer.Option(help="Benchmark claim or campaign name.")] = "benchmark-claim",
    experiment_manifest: Annotated[Path | None, typer.Option(help="Experiment manifest JSON artifact.")] = None,
    experiment_gate: Annotated[Path | None, typer.Option(help="Experiment gate JSON artifact.")] = None,
    provider_contract_check: Annotated[list[Path] | None, typer.Option(help="Executed provider contract-check JSON artifact. Can be repeated.")] = None,
    provider_contract_matrix: Annotated[list[Path] | None, typer.Option(help="Executed provider contract-check matrix JSON artifact. Can be repeated.")] = None,
    provider_audit: Annotated[list[Path] | None, typer.Option(help="Optional provider audit JSON artifact. Can be repeated.")] = None,
    matrix_gate: Annotated[list[Path] | None, typer.Option(help="Matrix gate JSON artifact. Can be repeated.")] = None,
    comparison_gate: Annotated[list[Path] | None, typer.Option(help="Comparison gate JSON artifact. Can be repeated.")] = None,
    telemetry_audit: Annotated[list[Path] | None, typer.Option(help="Telemetry audit JSON artifact. Can be repeated.")] = None,
    normalized_telemetry: Annotated[list[Path] | None, typer.Option(help="Optional normalized telemetry JSON artifact. Can be repeated.")] = None,
    matrix_pressure_audit: Annotated[list[Path] | None, typer.Option(help="Matrix pressure audit JSON artifact. Can be repeated.")] = None,
    matrix_saturation_report: Annotated[list[Path] | None, typer.Option(help="Matrix saturation report JSON artifact. Can be repeated.")] = None,
    matrix_scorecard: Annotated[list[Path] | None, typer.Option(help="Matrix scorecard JSON artifact. Can be repeated.")] = None,
    implementation_status: Annotated[list[Path] | None, typer.Option(help="Optional implementation status JSON artifact. Can be repeated.")] = None,
    release_provenance: Annotated[Path | None, typer.Option(help="Release provenance JSON artifact.")] = None,
    release_qualification_bundle: Annotated[Path | None, typer.Option(help="Release qualification bundle artifact.")] = None,
    redaction_scan: Annotated[Path | None, typer.Option(help="Redaction scan JSON artifact.")] = None,
    publication_bundle: Annotated[list[Path] | None, typer.Option(help="Publication bundle artifact. Can be repeated.")] = None,
    matrix_publication_bundle: Annotated[list[Path] | None, typer.Option(help="Matrix publication bundle artifact. Can be repeated.")] = None,
    protocol_repair_posture: Annotated[list[Path] | None, typer.Option(help="Optional protocol repair posture JSON artifact. Can be repeated.")] = None,
    workflow_readiness: Annotated[list[Path] | None, typer.Option(help="Optional workflow readiness JSON artifact. Can be repeated.")] = None,
    security_posture: Annotated[list[Path] | None, typer.Option(help="Optional security posture JSON artifact. Can be repeated.")] = None,
    harness_review: Annotated[list[Path] | None, typer.Option(help="Optional harness review JSON artifact for generated suites. Can be repeated.")] = None,
    suite_calibration_report: Annotated[list[Path] | None, typer.Option(help="Optional suite calibration report JSON artifact. Can be repeated.")] = None,
    engine_advisory: Annotated[list[Path] | None, typer.Option(help="Optional engine improvement advisory JSON artifact. Can be repeated.")] = None,
    evidence_index: Annotated[list[Path] | None, typer.Option(help="Optional evidence index JSON artifact. Can be repeated.")] = None,
    suite_audit: Annotated[list[Path] | None, typer.Option(help="Optional suite audit JSON artifact. Can be repeated.")] = None,
    metric_coverage: Annotated[list[Path] | None, typer.Option(help="Optional metric coverage JSON artifact. Can be repeated.")] = None,
    campaign_preflight_manifest: Annotated[Path | None, typer.Option(help="Optional campaign preflight manifest JSON artifact.")] = None,
    selftest_report: Annotated[list[Path] | None, typer.Option(help="Optional AgentBlaster selftest report JSON artifact. Can be repeated.")] = None,
    benchmark_readiness: Annotated[list[Path] | None, typer.Option(help="Optional benchmark readiness dossier JSON artifact. Can be repeated.")] = None,
    benchmark_readiness_list: Annotated[
        list[Path] | None,
        typer.Option(help="Text file with one benchmark readiness dossier JSON path per line. Can be repeated."),
    ] = None,
    output_json: Annotated[Path | None, typer.Option(help="Optional claim readiness JSON output path.")] = None,
    fail_on_blockers: Annotated[
        bool,
        typer.Option("--fail-on-blockers/--no-fail-on-blockers", help="Exit non-zero when required claim evidence is missing or failed."),
    ] = False,
) -> None:
    """Gate whether a benchmark claim has the expected publication evidence."""
    resolved_benchmark_readiness = _benchmark_readiness_paths(benchmark_readiness, benchmark_readiness_list)
    try:
        report = build_claim_readiness(
            name=name,
            experiment_manifest=experiment_manifest,
            experiment_gate=experiment_gate,
            provider_contract_checks=provider_contract_check,
            provider_contract_matrices=provider_contract_matrix,
            provider_audits=provider_audit,
            matrix_gates=matrix_gate,
            comparison_gates=comparison_gate,
            telemetry_audits=telemetry_audit,
            normalized_telemetry_reports=normalized_telemetry,
            matrix_pressure_audits=matrix_pressure_audit,
            matrix_saturation_reports=matrix_saturation_report,
            matrix_scorecards=matrix_scorecard,
            implementation_status_reports=implementation_status,
            release_provenance=release_provenance,
            release_qualification_bundle=release_qualification_bundle,
            redaction_scan=redaction_scan,
            publication_bundles=publication_bundle,
            matrix_publication_bundles=matrix_publication_bundle,
            protocol_repair_postures=protocol_repair_posture,
            workflow_readiness_reports=workflow_readiness,
            security_postures=security_posture,
            harness_reviews=harness_review,
            suite_calibration_reports=suite_calibration_report,
            engine_advisories=engine_advisory,
            evidence_indexes=evidence_index,
            suite_audits=suite_audit,
            metric_coverage_reports=metric_coverage,
            campaign_preflight_manifest=campaign_preflight_manifest,
            selftest_reports=selftest_report,
            benchmark_readiness_reports=resolved_benchmark_readiness,
        )
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if output_json is not None:
        typer.echo(str(write_claim_readiness_json(report, output_json)))
    typer.echo(format_claim_readiness(report), nl=False)
    if fail_on_blockers and not report["ready"]:
        raise typer.Exit(code=1)


@release_app.command("publication-brief")
def release_publication_brief(
    claim_readiness: Annotated[Path, typer.Option(help="Claim readiness JSON artifact to summarize.")],
    name: Annotated[str, typer.Option(help="Benchmark claim or campaign name.")] = "benchmark-claim",
    matrix_scorecard: Annotated[list[Path] | None, typer.Option(help="Matrix scorecard JSON artifact. Can be repeated.")] = None,
    release_provenance: Annotated[Path | None, typer.Option(help="Optional release provenance JSON artifact.")] = None,
    evidence_index: Annotated[Path | None, typer.Option(help="Optional evidence index JSON artifact.")] = None,
    output_json: Annotated[Path | None, typer.Option(help="Optional publication brief JSON output path.")] = None,
    output_md: Annotated[Path | None, typer.Option(help="Optional publication brief Markdown output path.")] = None,
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for publication-brief events.")] = None,
) -> None:
    """Create a redaction-safe executive/media/corporate publication brief from review evidence."""
    try:
        report = build_publication_brief(
            name=name,
            claim_readiness=claim_readiness,
            matrix_scorecards=matrix_scorecard,
            release_provenance=release_provenance,
            evidence_index=evidence_index,
        )
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    artifacts: list[str] = []
    if output_json is not None:
        artifacts.append(str(write_publication_brief_json(report, output_json)))
    if output_md is not None:
        artifacts.append(str(write_publication_brief_markdown(report, output_md)))
    AuditLogger(audit_log).emit(
        "publication_brief_created",
        name=report["name"],
        ready=report["ready"],
        claim_readiness=str(claim_readiness),
        matrix_scorecards=[str(item) for item in matrix_scorecard or []],
        release_provenance=str(release_provenance) if release_provenance else None,
        evidence_index=str(evidence_index) if evidence_index else None,
        artifacts=artifacts,
    )
    if artifacts:
        for artifact in artifacts:
            typer.echo(artifact)
    else:
        typer.echo(format_publication_brief(report), nl=False)


@release_app.command("protocol-repair")
def release_protocol_repair(
    name: Annotated[str, typer.Option(help="Benchmark claim or campaign name.")] = "benchmark-claim",
    claim_readiness: Annotated[Path | None, typer.Option(help="Optional claim readiness JSON artifact to mine for compact protocol-repair evidence.")] = None,
    matrix_scorecard: Annotated[list[Path] | None, typer.Option(help="Matrix scorecard JSON artifact. Can be repeated.")] = None,
    matrix_gate: Annotated[list[Path] | None, typer.Option(help="Matrix gate JSON artifact. Can be repeated.")] = None,
    output_json: Annotated[Path | None, typer.Option(help="Optional protocol-repair posture JSON output path.")] = None,
    output_md: Annotated[Path | None, typer.Option(help="Optional protocol-repair posture Markdown output path.")] = None,
    fail_on_review: Annotated[
        bool,
        typer.Option("--fail-on-review/--no-fail-on-review", help="Exit non-zero when protocol-repair posture is not ready."),
    ] = False,
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for protocol-repair posture events.")] = None,
) -> None:
    """Create a redaction-safe protocol-repair posture artifact from compact review evidence."""
    try:
        report = build_protocol_repair_posture(
            name=name,
            claim_readiness=claim_readiness,
            matrix_scorecards=matrix_scorecard,
            matrix_gates=matrix_gate,
        )
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    artifacts: list[str] = []
    if output_json is not None:
        artifacts.append(str(write_protocol_repair_posture_json(report, output_json)))
    if output_md is not None:
        artifacts.append(str(write_protocol_repair_posture_markdown(report, output_md)))
    AuditLogger(audit_log).emit(
        "protocol_repair_posture_created",
        name=report["name"],
        status=report["status"],
        ready=report["ready"],
        claim_readiness=str(claim_readiness) if claim_readiness else None,
        matrix_scorecards=[str(item) for item in matrix_scorecard or []],
        matrix_gates=[str(item) for item in matrix_gate or []],
        artifacts=artifacts,
    )
    if artifacts:
        for artifact in artifacts:
            typer.echo(artifact)
    else:
        typer.echo(format_protocol_repair_posture(report), nl=False)
    if fail_on_review and not report["ready"]:
        raise typer.Exit(code=1)


@release_app.command("workflow-readiness")
def release_workflow_readiness(
    name: Annotated[str, typer.Option(help="Benchmark campaign or claim name.")] = "workflow-readiness",
    suite: Annotated[list[str] | None, typer.Option("--suite", help="Built-in suite to include. Can be repeated.")] = None,
    suite_file: Annotated[list[Path] | None, typer.Option("--suite-file", help="Suite YAML file to include. Can be repeated.")] = None,
    matrix: Annotated[list[Path] | None, typer.Option("--matrix", help="Matrix YAML file to inspect. Can be repeated.")] = None,
    matrix_pressure_audit: Annotated[list[Path] | None, typer.Option("--matrix-pressure-audit", help="Matrix pressure audit JSON artifact. Can be repeated.")] = None,
    harness_review: Annotated[list[Path] | None, typer.Option("--harness-review", help="Harness review JSON artifact. Can be repeated.")] = None,
    required_surface: Annotated[
        list[str] | None,
        typer.Option("--required-surface", help="Required workflow surface. Defaults to the full agentic readiness set. Can be repeated."),
    ] = None,
    output_json: Annotated[Path | None, typer.Option(help="Optional workflow readiness JSON output path.")] = None,
    output_md: Annotated[Path | None, typer.Option(help="Optional workflow readiness Markdown output path.")] = None,
    fail_on_gaps: Annotated[
        bool,
        typer.Option("--fail-on-gaps/--no-fail-on-gaps", help="Exit non-zero when required workflow surfaces are missing."),
    ] = False,
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for workflow-readiness events.")] = None,
) -> None:
    """Create a no-dispatch readiness artifact for intended agentic workflow-surface coverage."""
    try:
        report = build_workflow_readiness_report(
            name=name,
            suite_names=suite,
            suite_files=suite_file,
            matrices=matrix,
            matrix_pressure_audits=matrix_pressure_audit,
            harness_reviews=harness_review,
            required_surfaces=required_surface,
        )
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    artifacts: list[str] = []
    if output_json is not None:
        artifacts.append(str(write_workflow_readiness_json(report, output_json)))
    if output_md is not None:
        artifacts.append(str(write_workflow_readiness_markdown(report, output_md)))
    AuditLogger(audit_log).emit(
        "workflow_readiness_created",
        name=report["name"],
        status=report["status"],
        ready=report["ready"],
        suites=suite or [],
        suite_files=[str(item) for item in suite_file or []],
        matrices=[str(item) for item in matrix or []],
        matrix_pressure_audits=[str(item) for item in matrix_pressure_audit or []],
        harness_reviews=[str(item) for item in harness_review or []],
        required_surfaces=report["required_surfaces"],
        artifacts=artifacts,
    )
    if artifacts:
        for artifact in artifacts:
            typer.echo(artifact)
    else:
        typer.echo(format_workflow_readiness_report(report), nl=False)
    if fail_on_gaps and not report["ready"]:
        raise typer.Exit(code=1)


@catalog_app.command("simulated-tools")
def catalog_simulated_tools(
    output_json: Annotated[Path | None, typer.Option(help="Optional JSON output path.")] = None,
) -> None:
    """List deterministic simulated tools bundled with AgentBlaster."""
    items = []
    for name, schema in sorted(SAFE_TOOL_SCHEMAS.items()):
        function = schema.get("function", {})
        parameters = function.get("parameters", {}) if isinstance(function, dict) else {}
        required = parameters.get("required", []) if isinstance(parameters, dict) else []
        items.append(
            {
                "name": name,
                "description": str(function.get("description", "")) if isinstance(function, dict) else "",
                "required_arguments": list(required) if isinstance(required, list) else [],
                "host_execution": False,
            }
        )
    _emit_catalog("agentblaster.simulated-tools", items, output_json)


@catalog_app.command("artifact-schemas")
def catalog_artifact_schemas(
    output: Annotated[Path | None, typer.Option(help="Optional output path.")] = None,
    format: Annotated[str, typer.Option("--format", help="Output format: markdown or json.")] = "markdown",
) -> None:
    """Render the static artifact schema registry for reports, runs, matrices, and release evidence."""
    normalized = format.strip().lower()
    if normalized == "json":
        content = artifact_schema_registry_json()
    elif normalized in {"md", "markdown"}:
        content = format_artifact_schema_registry_markdown()
    else:
        raise typer.BadParameter("format must be markdown or json")
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        typer.echo(str(output))
        return
    typer.echo(content, nl=False)


@catalog_app.command("mcp-profiles")
def catalog_mcp_profiles(
    output_json: Annotated[Path | None, typer.Option(help="Optional JSON output path.")] = None,
) -> None:
    """List deterministic MCP fixture profiles bundled with AgentBlaster."""
    items = []
    for profile in available_mcp_profiles():
        schemas = mcp_profile_tool_schemas(profile)
        items.append(
            {
                "name": profile,
                "tool_count": len(schemas),
                "tool_names": [_tool_schema_display_name(schema) for schema in schemas],
                "host_execution": False,
                "deterministic_result_support": True,
            }
        )
    _emit_catalog("agentblaster.mcp-profiles", items, output_json)


@catalog_app.command("skills")
def catalog_skills(
    output_json: Annotated[Path | None, typer.Option(help="Optional JSON output path.")] = None,
) -> None:
    """List bundled benchmark skill packs and prompt footprint metadata."""
    items = []
    for name in available_skill_packs():
        text = skill_pack_text(name)
        lines = text.splitlines()
        heading = next((line.lstrip("# ").strip() for line in lines if line.strip()), name)
        items.append(
            {
                "name": name,
                "heading": heading,
                "line_count": len(lines),
                "char_count": len(text),
                "host_execution": False,
            }
        )
    _emit_catalog("agentblaster.skills", items, output_json)


@catalog_app.command("lcp-profiles")
def catalog_lcp_profiles(
    output_json: Annotated[Path | None, typer.Option(help="Optional JSON output path.")] = None,
) -> None:
    """List deterministic LCP-style context fixture profiles bundled with AgentBlaster."""
    items = lcp_profile_catalog()
    _emit_catalog("agentblaster.lcp-profiles", items, output_json)


@catalog_app.command("workflow-surfaces")
def catalog_workflow_surfaces(
    format: Annotated[str, typer.Option("--format", help="Output format: text, json, or markdown.")] = "text",
    output: Annotated[Path | None, typer.Option(help="Optional output path for JSON or Markdown formats.")] = None,
) -> None:
    """List benchmark workflow surfaces: tools, MCP, skills, LCP, and harness-engineering profiles."""
    normalized = format.strip().lower()
    if normalized == "json":
        content = workflow_surface_catalog_json()
    elif normalized in {"md", "markdown"}:
        content = workflow_surface_catalog_markdown()
    elif normalized == "text":
        payload = json.loads(workflow_surface_catalog_json())
        for surface in payload["surfaces"]:
            typer.echo(f"{surface['id']}\t{surface['family']} | {surface['stability']} | {surface['purpose']}")
        return
    else:
        raise typer.BadParameter("format must be text, json, or markdown")
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        typer.echo(str(output))
        return
    typer.echo(content, nl=False)


@catalog_app.command("telemetry-mappings")
def catalog_telemetry_mappings(
    format: Annotated[str, typer.Option("--format", help="Output format: text, json, or markdown.")] = "text",
    output: Annotated[Path | None, typer.Option(help="Optional output path for JSON or Markdown formats.")] = None,
) -> None:
    """List raw-to-normalized telemetry mappings for supported provider families."""
    normalized = format.strip().lower()
    if normalized == "json":
        content = telemetry_mapping_catalog_json()
    elif normalized in {"md", "markdown"}:
        content = format_telemetry_mapping_catalog(markdown=True)
    elif normalized == "text":
        content = format_telemetry_mapping_catalog()
    else:
        raise typer.BadParameter("format must be text, json, or markdown")
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        typer.echo(str(output))
        return
    typer.echo(content, nl=False)


def _emit_catalog(catalog: str, items: list[dict], output_json: Path | None) -> None:
    payload = {"catalog": catalog, "items": items}
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        typer.echo(str(output_json))
        return

    for item in items:
        summary_parts = []
        if "description" in item:
            summary_parts.append(str(item["description"]))
        if "tool_count" in item:
            summary_parts.append(f"{item['tool_count']} tool(s)")
        if "heading" in item:
            summary_parts.append(str(item["heading"]))
        summary = " | ".join(part for part in summary_parts if part)
        typer.echo(f"{item['name']}\t{summary}")


def _tool_schema_display_name(schema: dict) -> str:
    function = schema.get("function")
    if isinstance(function, dict) and isinstance(function.get("name"), str):
        return function["name"]
    name = schema.get("name")
    return name if isinstance(name, str) else "unnamed"


@evidence_app.command("bundle")
def evidence_bundle(
    output_dir: Annotated[Path, typer.Option(help="Directory for the evidence bundle zip.")],
    suite: Annotated[str, typer.Option(help="Built-in benchmark suite to include in suite audit.")] = "smoke",
    suite_file: Annotated[Path | None, typer.Option(help="YAML suite definition to include instead of a built-in suite.")] = None,
    policy: Annotated[Path | None, typer.Option(help="Optional reviewed policy file to include in the bundle.")] = None,
    project_root: Annotated[Path, typer.Option(help="Project root containing pyproject.toml.")] = Path("."),
    include_provider_audit: Annotated[
        bool,
        typer.Option(help="Include redacted provider audit metadata from configured providers."),
    ] = False,
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for evidence bundle events.")] = None,
) -> None:
    """Create a static redaction-safe governance evidence bundle."""
    try:
        path = create_evidence_bundle(
            output_dir=output_dir,
            suite=suite,
            suite_file=suite_file,
            policy=policy,
            project_root=project_root,
            include_provider_audit=include_provider_audit,
        )
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    AuditLogger(audit_log).emit(
        "evidence_bundle_created",
        artifact=str(path),
        suite=suite,
        suite_file=str(suite_file) if suite_file else None,
        policy=str(policy) if policy else None,
        include_provider_audit=include_provider_audit,
    )
    typer.echo(str(path))


@harness_app.command("profiles")
def harness_profiles() -> None:
    """List deterministic harness-generation profiles."""
    for profile in list_harness_profiles():
        typer.echo(f"{profile.name}\t{profile.purpose}")


@harness_app.command("generate")
def harness_generate(
    output: Annotated[Path, typer.Option(help="Output YAML suite path.")],
    profile: Annotated[
        str,
        typer.Option(
            help=(
                "Harness profile: prefill, concurrency, cancellation, contract-fuzz, "
                "metamorphic, cache-replay, orchestration, skills, emerging-workflows, or judge-rubric."
            )
        ),
    ] = "contract-fuzz",
    suite: Annotated[str, typer.Option(help="Built-in suite to use as the source.")] = "smoke",
    suite_file: Annotated[Path | None, typer.Option(help="YAML suite file to use instead of a built-in suite.")] = None,
    repeats: Annotated[int, typer.Option(help="Number of deterministic repetitions per source case.")] = 4,
    seed: Annotated[int, typer.Option(help="Deterministic generation seed marker.")] = 0,
) -> None:
    """Generate a deterministic benchmark suite for emerging harness-engineering experiments."""
    try:
        source = load_suite_file(suite_file) if suite_file else get_builtin_suite(suite)
        generated = generate_harness_suite(source, profile=profile, repeats=repeats, seed=seed)
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(suite_to_yaml(generated), encoding="utf-8")
    typer.echo(f"wrote {output} with {len(generated.cases)} case(s)")


@harness_app.command("review")
def harness_review(
    suite: Annotated[str, typer.Option(help="Built-in suite to review when --suite-file is not set.")] = "smoke",
    suite_file: Annotated[Path | None, typer.Option(help="YAML suite file to review.")] = None,
    output_json: Annotated[Path | None, typer.Option(help="Optional JSON output path for the review artifact.")] = None,
) -> None:
    """Write a static, redaction-safe review artifact for a harness suite."""
    try:
        suite_definition = load_suite_file(suite_file) if suite_file else get_builtin_suite(suite)
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    report = build_harness_review_report(suite_definition)
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    typer.echo(format_harness_review_report(report), nl=False)


@models_app.command("targets")
def model_targets() -> None:
    """List canonical model targets for standardized comparisons."""
    for target in list_model_targets():
        typer.echo(
            f"{target.id}\t{target.default_model}\t{target.metadata.architecture or 'unknown'}\t"
            f"{target.parameter_count}\t{target.density}\t{target.display_name}\t"
            f"{target.comparison_group}\t{','.join(target.required_release_metadata) or 'none'}"
        )


@models_app.command("show")
def model_target_show(target: Annotated[str, typer.Argument(help="Canonical model target id.")]) -> None:
    """Show canonical model target metadata."""
    try:
        model_target = get_model_target(target)
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"id: {model_target.id}")
    typer.echo(f"display_name: {model_target.display_name}")
    typer.echo(f"family: {model_target.family}")
    typer.echo(f"density: {model_target.density}")
    typer.echo(f"parameter_count: {model_target.parameter_count}")
    typer.echo(f"default_model: {model_target.default_model}")
    typer.echo(f"architecture: {model_target.metadata.architecture or 'none'}")
    typer.echo(f"quantization: {model_target.metadata.quantization or 'none'}")
    typer.echo(f"tokenizer: {model_target.metadata.tokenizer or 'none'}")
    typer.echo(f"chat_template: {model_target.metadata.chat_template or 'none'}")
    typer.echo(f"context_length: {model_target.metadata.context_length or 'none'}")
    typer.echo(f"comparison_group: {model_target.comparison_group}")
    typer.echo(
        "required_release_metadata: "
        f"{', '.join(model_target.required_release_metadata) if model_target.required_release_metadata else 'none'}"
    )
    typer.echo("publication_guidance:")
    if model_target.publication_guidance:
        for item in model_target.publication_guidance:
            typer.echo(f"- {item}")
    else:
        typer.echo("- none")
    typer.echo(f"notes: {model_target.notes or 'none'}")


@models_app.command("matrix")
def model_matrix(
    output: Annotated[Path, typer.Option(help="Output YAML matrix path.")],
    providers: Annotated[str, typer.Option(help="Comma-separated provider profile names.")],
    targets: Annotated[
        str,
        typer.Option(help="Comma-separated model target ids."),
    ] = "qwen3.6-27b-dense,gemma-4-31b-dense",
    suite: Annotated[str, typer.Option(help="Built-in suite name for each matrix run.")] = "smoke",
    suite_file: Annotated[Path | None, typer.Option(help="Optional suite file path for each matrix run.")] = None,
    concurrency: Annotated[int, typer.Option(help="Concurrency for each matrix run.")] = 1,
    raw_traces: Annotated[RawTraceMode, typer.Option(help="Raw trace mode for generated runs.")] = RawTraceMode.REDACTED,
    no_raw_traces: Annotated[bool, typer.Option(help="Disable raw response capture in generated runs.")] = True,
    name: Annotated[str | None, typer.Option(help="Optional matrix name override.")] = None,
) -> None:
    """Generate a canonical provider x model target matrix file."""
    try:
        matrix = generate_matrix_template(
            providers=_split_csv(providers),
            target_ids=_split_csv(targets),
            suite=suite,
            suite_file=suite_file,
            concurrency=concurrency,
            raw_traces=raw_traces,
            no_raw_traces=no_raw_traces,
            name=name,
        )
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(matrix_to_yaml(matrix), encoding="utf-8")
    typer.echo(f"wrote {output} with {len(matrix.runs)} run(s)")


@experiment_app.command("manifest")
def experiment_manifest_command(
    name: Annotated[str, typer.Option(help="Experiment name.")],
    objective: Annotated[str, typer.Option(help="Benchmark objective or decision being tested.")],
    providers: Annotated[str, typer.Option(help="Comma-separated provider names.")],
    targets: Annotated[str, typer.Option(help="Comma-separated model target ids.")],
    suites: Annotated[str, typer.Option(help="Comma-separated suite names.")],
    output: Annotated[Path, typer.Option(help="Output experiment manifest JSON path.")],
    policy: Annotated[Path | None, typer.Option(help="Optional policy file path.")] = None,
    matrix: Annotated[Path | None, typer.Option(help="Optional matrix YAML path.")] = None,
    calibration_required: Annotated[bool, typer.Option(help="Require suite calibration reports in preflight artifacts.")] = False,
    min_case_pass_rate: Annotated[float, typer.Option(help="Minimum accepted matrix case pass rate.")] = 95.0,
    max_failed_runs: Annotated[int, typer.Option(help="Maximum accepted failed matrix runs.")] = 0,
) -> None:
    """Write a static benchmark experiment manifest."""
    manifest = build_experiment_manifest(
        name=name,
        objective=objective,
        providers=_split_csv(providers),
        targets=_split_csv(targets),
        suites=_split_csv(suites),
        policy=policy,
        matrix=matrix,
        calibration_required=calibration_required,
        min_case_pass_rate=min_case_pass_rate,
        max_failed_runs=max_failed_runs,
    )
    write_experiment_json(manifest, output)
    typer.echo(str(output))


@experiment_app.command("gate")
def experiment_gate_command(
    manifest: Annotated[Path, typer.Argument(help="Experiment manifest JSON path.")],
    output_json: Annotated[Path | None, typer.Option(help="Optional gate report JSON output path.")] = None,
    require_policy: Annotated[bool, typer.Option(help="Require the manifest to reference a policy file.")] = False,
) -> None:
    """Evaluate a static experiment manifest before benchmark execution."""
    try:
        report = evaluate_experiment_manifest(load_experiment_manifest(manifest), require_policy=require_policy)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if output_json is not None:
        write_experiment_json(report, output_json)
    typer.echo(format_experiment_gate(report), nl=False)
    if not report["passed"]:
        raise typer.Exit(1)


@engines_app.command("list")
def list_engines() -> None:
    """List planned built-in engine adapters."""
    for engine in BUILT_IN_ENGINES:
        typer.echo(engine)


@engines_app.command("targets")
def engine_targets_command(
    target: Annotated[str | None, typer.Option(help="Optional engine target id to show.")] = None,
    format: Annotated[str, typer.Option("--format", help="Output format: text, json, or markdown.")] = "text",
    output: Annotated[Path | None, typer.Option(help="Optional output path for JSON or Markdown formats.")] = None,
) -> None:
    """List standardized benchmark target engines and readiness metadata."""
    normalized = format.strip().lower()
    try:
        if target:
            payload = {
                "schema_version": "agentblaster.engine-target.v1",
                "target": get_engine_target(target),
            }
            if normalized == "json":
                content = json.dumps(payload, indent=2, sort_keys=True) + "\n"
            elif normalized in {"md", "markdown"}:
                content = format_engine_target_catalog(markdown=True)
            elif normalized == "text":
                item = payload["target"]
                content = (
                    f"{item['id']}\tcontracts={','.join(item['contracts'])}\t"
                    f"presets={','.join(item['provider_presets']) or 'none'}\t"
                    f"telemetry={','.join(item['telemetry_profiles'])}\n"
                )
            else:
                raise typer.BadParameter("format must be text, json, or markdown")
        elif normalized == "json":
            content = engine_target_catalog_json()
        elif normalized in {"md", "markdown"}:
            content = format_engine_target_catalog(markdown=True)
        elif normalized == "text":
            content = format_engine_target_catalog()
        else:
            raise typer.BadParameter("format must be text, json, or markdown")
    except ConfigError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        typer.echo(str(output))
        return
    typer.echo(content, nl=False)


@engines_app.command("launch-recipes")
def launch_recipes_command(
    engine: Annotated[str | None, typer.Option(help="Engine recipe to render. Omit with --catalog.")] = None,
    model: Annotated[str, typer.Option(help="Model id to insert into the launch recipe.")] = "mlx-community/Qwen3.6-27B",
    host: Annotated[str, typer.Option(help="Host to insert into the launch recipe.")] = "127.0.0.1",
    port: Annotated[int | None, typer.Option(help="Optional port override.")] = None,
    provider_name: Annotated[str | None, typer.Option(help="Provider profile name to use in generated commands.")] = None,
    catalog: Annotated[bool, typer.Option(help="Render the launch recipe catalog instead of one recipe.")] = False,
    output_json: Annotated[Path | None, typer.Option(help="Optional JSON output path.")] = None,
    markdown: Annotated[bool, typer.Option(help="Render Markdown instead of compact text.")] = False,
) -> None:
    """Render safe local engine launch and provider setup recipes without executing them."""
    try:
        payload = launch_recipe_catalog() if catalog else build_launch_recipe(
            engine or "afm",
            model=model,
            host=host,
            port=port,
            provider_name=provider_name,
        )
    except ConfigError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if output_json is not None:
        write_launch_recipe_json(payload, output_json)
    if markdown:
        typer.echo(format_launch_recipe_markdown(payload), nl=False)
        return
    if payload.get("schema_version") == "agentblaster.launch-recipe-catalog.v1":
        for item in payload["engines"]:
            typer.echo(f"{item['engine']}	{item['contract']}	port={item['default_port']}	{item['title']}")
        return
    typer.echo(f"engine: {payload['engine']}")
    typer.echo(f"contract: {payload['contract']}")
    typer.echo(f"base_url: {payload['base_url']}")
    typer.echo(f"launch: {' '.join(payload['launch_command'])}")
    typer.echo(f"provider_add: {' '.join(payload['provider_add_command'])}")


@engines_app.command("onboarding")
def engines_onboarding_command(
    engines: Annotated[str | None, typer.Option(help="Comma-separated local engines. Defaults to all local presets.")] = None,
    model: Annotated[str, typer.Option(help="Model id to insert into launch recipes.")] = "mlx-community/Qwen3.6-27B",
    output: Annotated[Path | None, typer.Option(help="Optional output path for the onboarding artifact.")] = None,
    format: Annotated[str, typer.Option("--format", help="Output format: markdown or json.")] = "markdown",
) -> None:
    """Render a static local-engine onboarding checklist for comparable benchmark setup."""
    try:
        payload = build_local_engine_onboarding(
            engines=_split_csv(engines) if engines else None,
            model=model,
        )
    except ConfigError as exc:
        raise typer.BadParameter(str(exc)) from exc
    normalized = format.strip().lower()
    if normalized == "json":
        content = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    elif normalized in {"md", "markdown"}:
        content = format_local_engine_onboarding_markdown(payload)
    else:
        raise typer.BadParameter("format must be markdown or json")
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        if normalized == "json":
            write_local_engine_onboarding(payload, output)
        else:
            output.write_text(content, encoding="utf-8")
        typer.echo(str(output))
        return
    typer.echo(content, nl=False)


@engines_app.command()
def probe(
    engine: Annotated[str, typer.Option(help="Engine profile name.")],
    base_url: Annotated[str, typer.Option(help="OpenAI-compatible base URL.")],
    contract: Annotated[ApiContract, typer.Option(help="API contract to probe.")] = ApiContract.OPENAI,
) -> None:
    """Probe an ad hoc engine endpoint without saving it."""
    provider = ProviderConfig(name=engine, contract=contract, base_url=base_url, remote=False)
    _print_probe(provider)


@providers_app.command("onboarding")
def provider_onboarding(
    preset: Annotated[str, typer.Option(help="Remote provider preset: openai, openai-responses, or anthropic.")],
    name: Annotated[str | None, typer.Option(help="Provider profile name to create in the generated commands.")] = None,
    secret_mode: Annotated[str, typer.Option(help="Secret backend mode for the plan: env, keyring, or dotenv.")] = "env",
    api_key_env: Annotated[str | None, typer.Option(help="Environment variable name for env mode or key staging.")] = None,
    dotenv_file: Annotated[str | None, typer.Option(help="Plaintext dotenv file path for dotenv-mode onboarding plans.")] = None,
    base_url: Annotated[str | None, typer.Option(help="Optional remote base URL override.")] = None,
    model: Annotated[str | None, typer.Option(help="Model id to use in readiness, contract-check, and smoke commands.")] = None,
    policy: Annotated[Path | None, typer.Option(help="Policy file path referenced by audit/readiness commands.")] = None,
    format: Annotated[str, typer.Option("--format", help="Output format: markdown or json.")] = "markdown",
    output: Annotated[Path | None, typer.Option(help="Optional output path for the onboarding artifact.")] = None,
) -> None:
    """Render a secure, redaction-safe onboarding plan for a remote provider."""
    try:
        plan = build_remote_provider_onboarding(
            preset=preset,
            provider_name=name,
            secret_mode=secret_mode,  # type: ignore[arg-type]
            api_key_env=api_key_env,
            dotenv_file=dotenv_file,
            base_url=base_url,
            model=model,
            policy=policy,
        )
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    normalized = format.strip().lower()
    if normalized == "json":
        content = remote_provider_onboarding_json(plan)
        markdown = False
    elif normalized in {"md", "markdown"}:
        content = format_remote_provider_onboarding(plan)
        markdown = True
    else:
        raise typer.BadParameter("format must be markdown or json")
    if output is not None:
        write_remote_provider_onboarding(plan, output, markdown=markdown)
        typer.echo(str(output))
        return
    typer.echo(content, nl=False)


@providers_app.command("add")
def add_provider(
    name: Annotated[str, typer.Option(help="Provider profile name.")],
    contract: Annotated[ApiContract, typer.Option(help="API contract implemented by the provider.")],
    base_url: Annotated[str, typer.Option(help="Provider base URL.")],
    default_model: Annotated[str | None, typer.Option(help="Optional default model id.")] = None,
    model_revision: Annotated[str | None, typer.Option(help="Default model revision/hash metadata.")] = None,
    model_architecture: Annotated[str | None, typer.Option(help="Default model architecture metadata.")] = None,
    quantization: Annotated[str | None, typer.Option(help="Default model quantization metadata.")] = None,
    tokenizer: Annotated[str | None, typer.Option(help="Default tokenizer metadata.")] = None,
    chat_template: Annotated[str | None, typer.Option(help="Default chat template metadata.")] = None,
    context_length: Annotated[int | None, typer.Option(help="Default context length metadata.")] = None,
    api_key_env: Annotated[
        str | None,
        typer.Option(help="Environment variable containing the API key."),
    ] = None,
    header: Annotated[
        list[str] | None,
        typer.Option(help="Non-secret provider header formatted as name=value. Repeat for multiple headers."),
    ] = None,
    metrics_url: Annotated[str | None, typer.Option(help="Optional Prometheus /metrics URL to snapshot before and after runs.")] = None,
    native_adapter: Annotated[
        str | None,
        typer.Option(help="Optional native adapter hint, for example ollama or lm-studio."),
    ] = None,
    tls_verify: Annotated[
        bool,
        typer.Option("--tls-verify/--no-tls-verify", help="Verify TLS certificates for HTTPS provider requests."),
    ] = True,
    ca_bundle: Annotated[Path | None, typer.Option(help="Optional custom CA bundle path for enterprise TLS gateways.")] = None,
    remote: Annotated[bool, typer.Option(help="Mark provider as internet-facing/remote.")] = False,
    include_provider_audit: Annotated[
        bool,
        typer.Option(help="Accepted for compatibility; provider add always emits redacted audit metadata when --audit-log is set."),
    ] = False,
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for provider config events.")] = None,
) -> None:
    """Add or update a provider profile."""
    api_key_ref = SecretRef(kind="env", name=api_key_env) if api_key_env else None
    provider = ProviderConfig(
        name=name,
        contract=contract,
        base_url=base_url,
        default_model=default_model,
        model_metadata=_model_metadata_from_options(
            revision=model_revision,
            architecture=model_architecture,
            quantization=quantization,
            tokenizer=tokenizer,
            chat_template=chat_template,
            context_length=context_length,
        )
        or ModelMetadata(),
        api_key_ref=api_key_ref,
        headers=_parse_header_options(header),
        metrics_url=metrics_url,
        native_adapter=native_adapter,
        tls_verify=tls_verify,
        ca_bundle=ca_bundle,
        remote=remote,
    )
    store = ProviderStore()
    existed = provider.name in store.load().providers
    store.upsert(provider)
    AuditLogger(audit_log).emit(
        "provider_updated" if existed else "provider_created",
        provider=provider.name,
        contract=provider.contract.value,
        base_url=str(provider.base_url).rstrip("/"),
        remote=provider.remote,
        api_key_ref=provider.api_key_ref.redacted_display() if provider.api_key_ref else None,
        api_key_ref_path_redacted=provider.api_key_ref.display_path_redacted() if provider.api_key_ref else False,
        metrics_url=str(provider.metrics_url).rstrip("/") if provider.metrics_url else None,
        native_adapter=provider.native_adapter,
        tls_verify=provider.tls_verify,
        ca_bundle=str(provider.ca_bundle) if provider.ca_bundle else None,
    )
    typer.echo(f"saved provider {provider.name}")


def _parse_header_options(items: list[str] | None) -> dict[str, str]:
    headers: dict[str, str] = {}
    for raw in items or []:
        if "=" not in raw:
            raise typer.BadParameter("--header must use name=value")
        name, value = raw.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            raise typer.BadParameter("--header requires a non-empty header name")
        if not value:
            raise typer.BadParameter("--header requires a non-empty header value")
        headers[name] = value
    return headers


@providers_app.command("presets")
def list_provider_presets() -> None:
    """List built-in provider presets for local and internet-facing endpoints."""
    for preset in PROVIDER_PRESETS.values():
        secret = f"env:{preset.api_key_env}" if preset.api_key_env else "none"
        typer.echo(
            f"{preset.name}\t{preset.contract.value}\t{preset.base_url}\t"
            f"remote={str(preset.remote).lower()}\tsecret={secret}\t{preset.description}"
        )


@providers_app.command("add-preset")
def add_provider_preset(
    preset: Annotated[str, typer.Option(help="Built-in preset name.")],
    name: Annotated[str | None, typer.Option(help="Provider profile name override.")] = None,
    base_url: Annotated[str | None, typer.Option(help="Base URL override.")] = None,
    api_key_env: Annotated[
        str | None,
        typer.Option(help="Environment variable containing the API key. Overrides the preset default env ref."),
    ] = None,
    metrics_url: Annotated[str | None, typer.Option(help="Optional Prometheus /metrics URL override.")] = None,
    tls_verify: Annotated[
        bool,
        typer.Option("--tls-verify/--no-tls-verify", help="Verify TLS certificates for HTTPS provider requests."),
    ] = True,
    ca_bundle: Annotated[Path | None, typer.Option(help="Optional custom CA bundle path for enterprise TLS gateways.")] = None,
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for provider config events.")] = None,
) -> None:
    """Add or update a provider from a built-in preset."""
    provider = get_preset(preset).to_provider(name=name, base_url=base_url, api_key_env=api_key_env)
    if metrics_url is not None:
        provider = ProviderConfig.model_validate({**provider.model_dump(mode="json"), "metrics_url": metrics_url})
    if not tls_verify or ca_bundle is not None:
        provider = ProviderConfig.model_validate(
            {
                **provider.model_dump(mode="json"),
                "tls_verify": tls_verify,
                "ca_bundle": str(ca_bundle) if ca_bundle else None,
            }
        )
    store = ProviderStore()
    existed = provider.name in store.load().providers
    store.upsert(provider)
    AuditLogger(audit_log).emit(
        "provider_updated" if existed else "provider_created",
        provider=provider.name,
        preset=preset,
        contract=provider.contract.value,
        base_url=str(provider.base_url).rstrip("/"),
        remote=provider.remote,
        api_key_ref=provider.api_key_ref.redacted_display() if provider.api_key_ref else None,
        api_key_ref_path_redacted=provider.api_key_ref.display_path_redacted() if provider.api_key_ref else False,
        metrics_url=str(provider.metrics_url).rstrip("/") if provider.metrics_url else None,
        tls_verify=provider.tls_verify,
        ca_bundle=str(provider.ca_bundle) if provider.ca_bundle else None,
    )
    typer.echo(f"saved provider {provider.name}")


@providers_app.command("list")
def list_providers() -> None:
    """List configured provider profiles."""
    providers = ProviderStore().list()
    if not providers:
        typer.echo("no providers configured")
        return
    for provider in providers:
        secret = provider.api_key_ref.redacted_display() if provider.api_key_ref else "none"
        typer.echo(
            f"{provider.name}\t{provider.contract.value}\t{str(provider.base_url).rstrip('/')}\t"
            f"remote={str(provider.remote).lower()}\tsecret={secret}"
        )


@providers_app.command("show")
def show_provider(name: Annotated[str, typer.Argument(help="Provider profile name.")]) -> None:
    """Show a configured provider profile without secret values."""
    provider = ProviderStore().get(name)
    secret = provider.api_key_ref.redacted_display() if provider.api_key_ref else "none"
    typer.echo(f"name: {provider.name}")
    typer.echo(f"contract: {provider.contract.value}")
    typer.echo(f"base_url: {str(provider.base_url).rstrip('/')}")
    typer.echo(f"default_model: {provider.default_model or 'none'}")
    typer.echo(f"model_revision: {provider.model_metadata.revision or 'none'}")
    typer.echo(f"model_architecture: {provider.model_metadata.architecture or 'none'}")
    typer.echo(f"quantization: {provider.model_metadata.quantization or 'none'}")
    typer.echo(f"tokenizer: {provider.model_metadata.tokenizer or 'none'}")
    typer.echo(f"chat_template: {provider.model_metadata.chat_template or 'none'}")
    typer.echo(f"context_length: {provider.model_metadata.context_length or 'none'}")
    typer.echo(f"metrics_url: {str(provider.metrics_url).rstrip('/') if provider.metrics_url else 'none'}")
    typer.echo(f"tls_verify: {str(provider.tls_verify).lower()}")
    typer.echo(f"ca_bundle: {str(provider.ca_bundle) if provider.ca_bundle else 'none'}")
    typer.echo(f"native_adapter: {provider.native_adapter or 'none'}")
    typer.echo(
        "headers: "
        + (", ".join(sorted(provider.headers)) if provider.headers else "none")
    )
    typer.echo(f"remote: {str(provider.remote).lower()}")
    typer.echo(f"api_key_ref: {secret}")
    if provider.capabilities:
        typer.echo("capabilities:")
        for key, value in sorted(provider.capabilities.items()):
            typer.echo(f"- {key}: {str(value).lower()}")
    else:
        typer.echo("capabilities: none")
    typer.echo(f"cost_model: {'configured' if provider.cost_model else 'none'}")
    typer.echo(f"rate_limits: {'configured' if provider.rate_limits else 'none'}")


@providers_cost_app.command("set")
def provider_cost_set(
    provider: Annotated[str, typer.Option(help="Configured provider profile name.")],
    input_usd_per_1m_tokens: Annotated[float, typer.Option(help="Input token price in USD per 1M tokens.")],
    output_usd_per_1m_tokens: Annotated[float, typer.Option(help="Output token price in USD per 1M tokens.")],
    cached_input_usd_per_1m_tokens: Annotated[
        float | None,
        typer.Option(help="Optional cached-input/read price in USD per 1M tokens."),
    ] = None,
    cache_write_usd_per_1m_tokens: Annotated[
        float | None,
        typer.Option(help="Optional cache-write price in USD per 1M tokens."),
    ] = None,
    request_usd: Annotated[float | None, typer.Option(help="Optional fixed request price in USD.")] = None,
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for cost model events.")] = None,
) -> None:
    """Set provider cost model metadata used by dry-run and policy cost ceilings."""
    if input_usd_per_1m_tokens < 0 or output_usd_per_1m_tokens < 0:
        raise typer.BadParameter("input and output token rates must be non-negative")
    for label, value in [
        ("cached input token rate", cached_input_usd_per_1m_tokens),
        ("cache write token rate", cache_write_usd_per_1m_tokens),
        ("request rate", request_usd),
    ]:
        if value is not None and value < 0:
            raise typer.BadParameter(f"{label} must be non-negative")

    store = ProviderStore()
    config = store.get(provider)
    cost_model = {
        "input_usd_per_1m_tokens": input_usd_per_1m_tokens,
        "output_usd_per_1m_tokens": output_usd_per_1m_tokens,
    }
    if cached_input_usd_per_1m_tokens is not None:
        cost_model["cached_input_usd_per_1m_tokens"] = cached_input_usd_per_1m_tokens
    if cache_write_usd_per_1m_tokens is not None:
        cost_model["cache_write_usd_per_1m_tokens"] = cache_write_usd_per_1m_tokens
    if request_usd is not None:
        cost_model["request_usd"] = request_usd
    store.upsert(config.model_copy(update={"cost_model": cost_model}))
    AuditLogger(audit_log).emit(
        "provider_cost_model_changed",
        provider=provider,
        fields=sorted(cost_model),
    )
    typer.echo(f"stored cost model for {provider}")


@providers_cost_app.command("show")
def provider_cost_show(provider: Annotated[str, typer.Option(help="Configured provider profile name.")]) -> None:
    """Show provider cost model metadata without secrets."""
    config = ProviderStore().get(provider)
    if not config.cost_model:
        typer.echo(f"cost_model: none for {provider}")
        return
    typer.echo(f"provider: {provider}")
    typer.echo("cost_model:")
    for key, value in sorted(config.cost_model.items()):
        typer.echo(f"- {key}: {value}")


@providers_cost_app.command("clear")
def provider_cost_clear(
    provider: Annotated[str, typer.Option(help="Configured provider profile name.")],
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for cost model events.")] = None,
) -> None:
    """Remove provider cost model metadata."""
    store = ProviderStore()
    config = store.get(provider)
    store.upsert(config.model_copy(update={"cost_model": {}}))
    AuditLogger(audit_log).emit("provider_cost_model_cleared", provider=provider)
    typer.echo(f"cleared cost model for {provider}")


@providers_rate_limits_app.command("set")
def provider_rate_limits_set(
    provider: Annotated[str, typer.Option(help="Configured provider profile name.")],
    max_concurrency: Annotated[int | None, typer.Option(help="Provider-level maximum concurrent requests.")] = None,
    requests_per_second: Annotated[float | None, typer.Option(help="Provider request rate limit in requests per second.")] = None,
    requests_per_minute: Annotated[float | None, typer.Option(help="Provider request rate limit in requests per minute.")] = None,
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for rate-limit events.")] = None,
) -> None:
    """Set provider request pacing and concurrency metadata."""
    if max_concurrency is None and requests_per_second is None and requests_per_minute is None:
        raise typer.BadParameter("at least one rate-limit option is required")
    if max_concurrency is not None and max_concurrency < 1:
        raise typer.BadParameter("max_concurrency must be at least 1")
    for label, value in [
        ("requests_per_second", requests_per_second),
        ("requests_per_minute", requests_per_minute),
    ]:
        if value is not None and value <= 0:
            raise typer.BadParameter(f"{label} must be greater than 0")

    store = ProviderStore()
    config = store.get(provider)
    rate_limits = dict(config.rate_limits)
    if max_concurrency is not None:
        rate_limits["max_concurrency"] = max_concurrency
    if requests_per_second is not None:
        rate_limits["requests_per_second"] = requests_per_second
    if requests_per_minute is not None:
        rate_limits["requests_per_minute"] = requests_per_minute
    store.upsert(config.model_copy(update={"rate_limits": rate_limits}))
    AuditLogger(audit_log).emit(
        "provider_rate_limits_changed",
        provider=provider,
        fields=sorted(rate_limits),
    )
    typer.echo(f"stored rate limits for {provider}")


@providers_rate_limits_app.command("show")
def provider_rate_limits_show(provider: Annotated[str, typer.Option(help="Configured provider profile name.")]) -> None:
    """Show provider request pacing and concurrency metadata."""
    config = ProviderStore().get(provider)
    if not config.rate_limits:
        typer.echo(f"rate_limits: none for {provider}")
        return
    typer.echo(f"provider: {provider}")
    typer.echo("rate_limits:")
    for key, value in sorted(config.rate_limits.items()):
        typer.echo(f"- {key}: {value}")


@providers_rate_limits_app.command("clear")
def provider_rate_limits_clear(
    provider: Annotated[str, typer.Option(help="Configured provider profile name.")],
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for rate-limit events.")] = None,
) -> None:
    """Remove provider request pacing and concurrency metadata."""
    store = ProviderStore()
    config = store.get(provider)
    store.upsert(config.model_copy(update={"rate_limits": {}}))
    AuditLogger(audit_log).emit("provider_rate_limits_cleared", provider=provider)
    typer.echo(f"cleared rate limits for {provider}")


@providers_app.command("audit")
def audit_provider_profiles(
    policy: Annotated[Path | None, typer.Option(help="Optional agentblaster.policy.yaml path.")] = None,
    output_json: Annotated[Path | None, typer.Option(help="Optional redacted provider audit JSON output path.")] = None,
) -> None:
    """Audit configured providers against policy without resolving secrets or contacting endpoints."""
    try:
        security_policy = load_policy(policy)
        report = audit_providers(ProviderStore().list(), security_policy)
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(provider_audit_json(report), encoding="utf-8")
        typer.echo(format_provider_audit(report), nl=False)
        typer.echo(str(output_json))
        return
    typer.echo(format_provider_audit(report), nl=False)


@providers_app.command("check-suite")
def check_provider_suite(
    provider: Annotated[str, typer.Option(help="Configured provider profile name.")],
    suite: Annotated[str, typer.Option(help="Built-in benchmark suite to check.")] = "smoke",
    suite_file: Annotated[Path | None, typer.Option(help="YAML suite definition to check.")] = None,
    strict_unknown: Annotated[bool, typer.Option(help="Fail when required capabilities are unknown.")] = False,
    output_json: Annotated[Path | None, typer.Option(help="Optional JSON compatibility report path.")] = None,
) -> None:
    """Check whether a provider declares support for a suite's required capabilities."""
    try:
        provider_config = ProviderStore().get(provider)
        suite_definition = load_suite_file(suite_file) if suite_file else get_builtin_suite(suite)
        report = check_suite_compatibility(provider_config, suite_definition, strict_unknown=strict_unknown)
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(format_capability_report(report))
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
        typer.echo(str(output_json))
    if not report.compatible:
        raise typer.Exit(code=1)


@providers_app.command("probe")
def probe_provider(name: Annotated[str, typer.Argument(help="Provider profile name.")]) -> None:
    """Probe a configured provider endpoint."""
    provider = ProviderStore().get(name)
    _print_probe(provider)


@providers_capabilities_app.command("list")
def list_provider_capabilities(
    provider: Annotated[str, typer.Option(help="Provider profile name.")],
) -> None:
    """List declared provider capabilities and supported standard capability names."""
    config = ProviderStore().get(provider)
    typer.echo(f"provider: {config.name}")
    if config.capabilities:
        for key, value in sorted(config.capabilities.items()):
            typer.echo(f"{key}\t{str(value).lower()}\t{CAPABILITY_DESCRIPTIONS.get(key, 'custom capability')}")
    else:
        typer.echo("no capabilities declared")
    typer.echo("standard capabilities:")
    for key, description in sorted(CAPABILITY_DESCRIPTIONS.items()):
        typer.echo(f"- {key}\t{description}")


@providers_capabilities_app.command("enable")
def enable_provider_capability(
    provider: Annotated[str, typer.Option(help="Provider profile name.")],
    capability: Annotated[str, typer.Option(help="Standard capability key to declare as supported.")],
) -> None:
    """Declare that a provider supports a standard capability."""
    _set_provider_capability(provider, capability, True)
    typer.echo(f"enabled capability {capability} for {provider}")


@providers_capabilities_app.command("disable")
def disable_provider_capability(
    provider: Annotated[str, typer.Option(help="Provider profile name.")],
    capability: Annotated[str, typer.Option(help="Standard capability key to declare as unsupported.")],
) -> None:
    """Declare that a provider does not support a standard capability."""
    _set_provider_capability(provider, capability, False)
    typer.echo(f"disabled capability {capability} for {provider}")


@providers_capabilities_app.command("clear")
def clear_provider_capability(
    provider: Annotated[str, typer.Option(help="Provider profile name.")],
    capability: Annotated[str, typer.Option(help="Standard capability key to remove from provider declarations.")],
) -> None:
    """Remove a capability declaration so preflight treats it as unknown unless inferred."""
    capability_key = _validate_capability_key(capability)
    store = ProviderStore()
    config = store.get(provider)
    capabilities = dict(config.capabilities)
    capabilities.pop(capability_key, None)
    store.upsert(config.model_copy(update={"capabilities": capabilities}))
    typer.echo(f"cleared capability {capability_key} for {provider}")


def _default_dotenv_secret_variable(provider: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", provider).strip("_").upper()
    return f"AGENTBLASTER_{normalized or 'PROVIDER'}_API_KEY"


@providers_auth_app.command("set")
def set_auth(
    provider: Annotated[str, typer.Option(help="Provider profile name.")],
    api_key_stdin: Annotated[bool, typer.Option(help="Read API key from stdin and store in keyring.")] = False,
    api_key_env: Annotated[
        str | None,
        typer.Option(help="Use an environment variable as the provider API key reference."),
    ] = None,
    api_key_dotenv_file: Annotated[
        Path | None,
        typer.Option(help="Read API key from stdin and store it in an explicit plaintext .env fallback file."),
    ] = None,
    dotenv_var: Annotated[
        str | None,
        typer.Option(help="Variable name to use with --api-key-dotenv-file."),
    ] = None,
    allow_plaintext_secret_file: Annotated[
        bool,
        typer.Option(help="Required with --api-key-dotenv-file to acknowledge plaintext secret-file storage."),
    ] = False,
    policy: Annotated[Path | None, typer.Option(help="Optional policy file to enforce before storing writable secrets.")] = None,
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for secret reference changes.")] = None,
) -> None:
    """Configure a provider API-key reference without storing plaintext config secrets."""
    secret_source_count = sum(source is not None and source is not False for source in (api_key_stdin, api_key_env, api_key_dotenv_file))
    if secret_source_count > 1:
        raise typer.BadParameter("choose only one of --api-key-stdin, --api-key-env, or --api-key-dotenv-file")
    if secret_source_count == 0:
        raise typer.BadParameter(
            "use --api-key-stdin for keyring storage, --api-key-env for portable env refs, "
            "or --api-key-dotenv-file with --allow-plaintext-secret-file for development fallback"
        )
    if api_key_dotenv_file and not allow_plaintext_secret_file:
        raise typer.BadParameter("--api-key-dotenv-file requires --allow-plaintext-secret-file")

    if api_key_env:
        ref = SecretRef(kind="env", name=api_key_env)
    elif api_key_dotenv_file:
        variable = dotenv_var or _default_dotenv_secret_variable(provider)
        ref = SecretRef(kind="dotenv", name=dotenv_ref_name(variable, api_key_dotenv_file))
    else:
        ref = SecretRef(kind="keyring", name=f"{provider}:api_key")
    store = ProviderStore()
    config = store.get(provider)
    updated_config = config.model_copy(update={"api_key_ref": ref})
    if policy is not None:
        try:
            enforce_provider_policy(
                updated_config,
                load_policy(policy),
                raw_trace_mode=RawTraceMode.REDACTED,
                concurrency=1,
                suite=None,
            )
        except AgentBlasterError as exc:
            AuditLogger(audit_log).emit(
                "provider_auth_ref_rejected",
                provider=provider,
                ref_kind=ref.kind,
                stored_keyring_secret=False,
                stored_dotenv_secret=False,
                plaintext_secret_file="<redacted-path>" if api_key_dotenv_file else None,
                plaintext_secret_file_name=api_key_dotenv_file.name if api_key_dotenv_file else None,
                api_key_ref=ref.redacted_display(),
                api_key_ref_path_redacted=ref.display_path_redacted(),
                plaintext_secret_warning=api_key_dotenv_file is not None,
                policy_path=str(policy),
                policy_ok=False,
                policy_reason=str(exc),
            )
            raise typer.BadParameter("provider auth secret storage blocked by policy") from exc
    if api_key_stdin or api_key_dotenv_file:
        api_key = sys.stdin.read().strip()
        try:
            SecretResolver().set(ref, api_key)
        except AgentBlasterError as exc:
            raise typer.BadParameter(str(exc)) from exc
    store.upsert(updated_config)
    AuditLogger(audit_log).emit(
        "provider_auth_ref_changed",
        provider=provider,
        api_key_ref=ref.redacted_display(),
        api_key_ref_path_redacted=ref.display_path_redacted(),
        ref_kind=ref.kind,
        stored_keyring_secret=api_key_stdin,
        stored_dotenv_secret=api_key_dotenv_file is not None,
        plaintext_secret_file="<redacted-path>" if api_key_dotenv_file else None,
        plaintext_secret_file_name=api_key_dotenv_file.name if api_key_dotenv_file else None,
        plaintext_secret_warning=api_key_dotenv_file is not None,
        policy_path=str(policy) if policy else None,
        policy_ok=True if policy else None,
    )
    if api_key_dotenv_file:
        typer.echo(
            f"WARNING: stored plaintext .env secret fallback for {provider}; "
            "use env or keyring for CI/corporate runs"
        )
    typer.echo(f"stored {ref.kind} secret reference for {provider}")


@providers_auth_app.command("test")
def test_auth(provider: Annotated[str, typer.Option(help="Provider profile name.")]) -> None:
    """Confirm that a provider's secret reference resolves without printing it."""
    config = ProviderStore().get(provider)
    if config.api_key_ref is None:
        raise typer.BadParameter(f"provider {provider} has no api_key_ref")
    if not SecretResolver().resolve(config.api_key_ref):
        raise typer.BadParameter(f"secret reference does not resolve: {config.api_key_ref.redacted_display()}")
    typer.echo(f"secret reference resolves for {provider}")


@providers_auth_app.command("status")
def auth_status(provider: Annotated[str, typer.Option(help="Provider profile name.")]) -> None:
    """Show a provider's auth reference and whether it resolves, without printing the secret."""
    config = ProviderStore().get(provider)
    ref = config.api_key_ref
    typer.echo(f"provider: {provider}")
    if ref is None:
        typer.echo("api_key_ref: none")
        typer.echo("configured: false")
        typer.echo("resolves: false")
        return
    resolves = SecretResolver().resolve(ref) is not None
    typer.echo(f"api_key_ref: {ref.redacted_display()}")
    typer.echo(f"kind: {ref.kind}")
    typer.echo("configured: true")
    typer.echo(f"resolves: {str(resolves).lower()}")


@providers_auth_app.command("clear")
def clear_auth(
    provider: Annotated[str, typer.Option(help="Provider profile name.")],
    delete_secret: Annotated[
        bool,
        typer.Option(help="Also delete the referenced keyring secret when the provider uses a keyring reference."),
    ] = False,
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for secret reference changes.")] = None,
) -> None:
    """Clear a provider API-key reference and optionally delete keyring secret material."""
    store = ProviderStore()
    config = store.get(provider)
    ref = config.api_key_ref
    if ref is not None and delete_secret:
        if ref.kind not in {"keyring", "dotenv"}:
            raise typer.BadParameter(
                "only keyring or dotenv secrets can be deleted by AgentBlaster; "
                "unset env secrets in your shell or CI"
            )
        try:
            SecretResolver().delete(ref)
        except AgentBlasterError as exc:
            raise typer.BadParameter(str(exc)) from exc
    store.upsert(config.model_copy(update={"api_key_ref": None}))
    AuditLogger(audit_log).emit(
        "provider_auth_ref_cleared",
        provider=provider,
        previous_api_key_ref=ref.redacted_display() if ref else None,
        previous_api_key_ref_path_redacted=ref.display_path_redacted() if ref else False,
        deleted_keyring_secret=delete_secret and ref is not None and ref.kind == "keyring",
        deleted_dotenv_secret=delete_secret and ref is not None and ref.kind == "dotenv",
    )
    if ref is None:
        typer.echo(f"auth reference already empty for {provider}")
    elif delete_secret:
        typer.echo(f"cleared auth reference and deleted {ref.kind} secret for {provider}")
    else:
        typer.echo(f"cleared auth reference for {provider}")


def _print_probe(provider: ProviderConfig) -> None:
    try:
        result = adapter_for(provider).probe()
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"provider: {result.provider}")
    typer.echo(f"contract: {result.contract.value}")
    typer.echo(f"ok: {str(result.ok).lower()}")
    if result.status_code is not None:
        typer.echo(f"status_code: {result.status_code}")
    if result.models:
        typer.echo("models:")
        for model in result.models:
            typer.echo(f"- {model}")
    else:
        typer.echo(f"message: {result.message}")



@quality_app.command("gates")
def quality_gates(
    format: Annotated[str, typer.Option("--format", help="Output format: json or markdown.")] = "json",
    output: Annotated[Path | None, typer.Option(help="Optional path to write the SDLC gate catalog.")] = None,
) -> None:
    """Render AgentBlaster's SDLC gate catalog for CI and release evidence."""
    normalized = format.strip().lower()
    if normalized == "json":
        content = render_sdlc_gate_catalog_json()
    elif normalized in {"md", "markdown"}:
        content = render_sdlc_gate_catalog_markdown()
    else:
        raise typer.BadParameter("format must be json or markdown")
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content)
        typer.echo(output)
        return
    typer.echo(content, nl=False)


@quality_app.command("validation-manifest")
def quality_validation_manifest(
    format: Annotated[str, typer.Option("--format", help="Output format: json or markdown.")] = "json",
    output: Annotated[Path | None, typer.Option(help="Optional path to write the SDLC validation manifest.")] = None,
    name: Annotated[str, typer.Option(help="Manifest name for the SDLC validation plan.")] = "agentblaster-sdlc",
    dashboard_url: Annotated[str, typer.Option(help="Dashboard URL used by Chrome/Codex and browser checks.")] = "http://127.0.0.1:8765",
    fixture_dir: Annotated[str, typer.Option(help="Deterministic dashboard fixture directory.")] = "tests/fixtures/dashboard-runs",
    evidence_dir: Annotated[str, typer.Option(help="Directory where Chrome/Codex GUI evidence should be collected.")] = "test-reports/gui",
    browser: Annotated[str, typer.Option(help="Browser target for the CI GUI lane.")] = "chrome",
) -> None:
    """Render the full AgentBlaster SDLC validation manifest without running tests."""
    normalized = format.strip().lower()
    if normalized == "json":
        content = render_sdlc_validation_manifest_json(
            name=name,
            dashboard_url=dashboard_url,
            fixture_dir=fixture_dir,
            evidence_dir=evidence_dir,
            browser=browser,
        )
    elif normalized in {"md", "markdown"}:
        content = render_sdlc_validation_manifest_markdown(
            name=name,
            dashboard_url=dashboard_url,
            fixture_dir=fixture_dir,
            evidence_dir=evidence_dir,
            browser=browser,
        )
    else:
        raise typer.BadParameter("format must be json or markdown")
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        typer.echo(output)
        return
    typer.echo(content, nl=False)


@quality_app.command("gui-spec")
def quality_gui_spec(
    format: Annotated[str, typer.Option("--format", help="Output format: json or markdown.")] = "json",
    output: Annotated[Path | None, typer.Option(help="Optional path to write the GUI test specification.")] = None,
    dashboard_url: Annotated[str, typer.Option(help="Dashboard URL used by Chrome/Codex and browser checks.")] = "http://127.0.0.1:8765",
    fixture_dir: Annotated[str, typer.Option(help="Deterministic dashboard fixture directory.")] = "tests/fixtures/dashboard-runs",
    evidence_dir: Annotated[str, typer.Option(help="Directory where Chrome/Codex GUI evidence should be collected.")] = "test-reports/gui",
    browser: Annotated[str, typer.Option(help="Browser target for the CI GUI lane.")] = "chrome",
) -> None:
    """Render the unified GUI self-test specification for CI and Chrome/Codex validation."""
    normalized = format.strip().lower()
    if normalized == "json":
        content = render_gui_test_spec_json(
            dashboard_url=dashboard_url,
            fixture_dir=fixture_dir,
            evidence_dir=evidence_dir,
            browser=browser,
        )
    elif normalized in {"md", "markdown"}:
        content = render_gui_test_spec_markdown(
            dashboard_url=dashboard_url,
            fixture_dir=fixture_dir,
            evidence_dir=evidence_dir,
            browser=browser,
        )
    else:
        raise typer.BadParameter("format must be json or markdown")
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content)
        typer.echo(output)
        return
    typer.echo(content, nl=False)


@quality_app.command("gui-artifacts")
def quality_gui_artifacts(
    output: Annotated[Path, typer.Option(help="Directory for generated GUI testing artifacts.")] = Path("tests/gui"),
    dashboard_url: Annotated[str, typer.Option(help="Dashboard URL used by Chrome/Codex and browser checks.")] = "http://127.0.0.1:8765",
    fixture_dir: Annotated[str, typer.Option(help="Deterministic dashboard fixture directory.")] = "tests/fixtures/dashboard-runs",
    evidence_dir: Annotated[str, typer.Option(help="Directory where Chrome/Codex GUI evidence should be collected.")] = "test-reports/gui",
    browser: Annotated[str, typer.Option(help="Browser target for the CI GUI lane.")] = "chrome",
    overwrite: Annotated[bool, typer.Option(help="Overwrite existing generated GUI artifacts.")] = False,
) -> None:
    """Generate GUI self-test artifacts for CI, Chrome/Codex validation, and release evidence."""
    try:
        paths = write_gui_test_artifacts(
            output,
            dashboard_url=dashboard_url,
            fixture_dir=fixture_dir,
            evidence_dir=evidence_dir,
            browser=browser,
            overwrite=overwrite,
        )
    except FileExistsError as exc:
        raise typer.BadParameter(str(exc)) from exc
    for path in paths:
        typer.echo(path)

if __name__ == "__main__":
    app()
