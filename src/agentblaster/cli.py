from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import sys
from pathlib import Path
from typing import Annotated

import typer

from agentblaster.adapters import adapter_for
from agentblaster.agent_profiles import generate_agent_suite, list_agent_profiles, suite_to_yaml as agent_suite_to_yaml
from agentblaster.audit import AuditLogger
from agentblaster.benchmark_kit import create_benchmark_kit
from agentblaster.bundle import create_publication_bundle, create_replay_bundle
from agentblaster.campaign import create_campaign_plan
from agentblaster.capabilities import (
    CAPABILITY_DESCRIPTIONS,
    check_suite_compatibility,
    format_capability_report,
    suite_requirements,
)
from agentblaster.cleanup import apply_expired_cleanup, cleanup_run, plan_expired_cleanup
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
    format_contract_check_report,
    provider_contract_plan,
    run_provider_contract_check,
    write_contract_check_json,
)
from agentblaster.costs import estimate_costs
from agentblaster.dashboard import assert_dashboard_bind_allowed, serve_dashboard
from agentblaster.errors import AgentBlasterError, PolicyError
from agentblaster.evidence import create_evidence_bundle
from agentblaster.engine_targets import (
    engine_target_catalog_json,
    format_engine_target_catalog,
    get_engine_target,
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
from agentblaster.harness import generate_harness_suite, list_harness_profiles, suite_to_yaml
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
    enforce_dashboard_policy,
    enforce_matrix_policy,
    enforce_provider_policy,
    estimate_case_prompt_tokens,
    load_policy,
    offline_policy,
)
from agentblaster.planning import RunPlan, build_run_plan, format_run_plan
from agentblaster.presets import PROVIDER_PRESETS, get_preset
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
    render_chrome_gui_plan_json,
    render_chrome_gui_plan_markdown,
    render_chrome_validation_markdown,
    render_gui_test_spec_json,
    render_gui_test_spec_markdown,
    render_selftest_plan,
    run_selftest_command,
    write_gui_test_artifacts,
)
from agentblaster.release import write_release_provenance
from agentblaster.release_qualification import create_release_qualification_bundle
from agentblaster.redaction_scan import format_redaction_scan_report, redaction_scan_json, scan_paths
from agentblaster.remote_onboarding import (
    build_remote_provider_onboarding,
    format_remote_provider_onboarding,
    remote_provider_onboarding_json,
    write_remote_provider_onboarding,
)
from agentblaster.reports import generate_matrix_reports, generate_matrix_scorecard_reports, generate_reports
from agentblaster.runner import BenchmarkRunner
from agentblaster.secrets import SecretResolver
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
    format_telemetry_mapping_catalog,
    telemetry_mapping_catalog_json,
)
from agentblaster.workflow_surfaces import (
    workflow_surface_catalog_json,
    workflow_surface_catalog_markdown,
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
    "lm-studio-native",
    "omlx",
    "rapid-mlx",
    "vllm-mlx",
]


@app.command()
def version() -> None:
    """Print the AgentBlaster version."""
    from agentblaster import __version__

    typer.echo(__version__)


@selftest_app.callback(invoke_without_command=True)
def selftest(
    ctx: typer.Context,
    tier: Annotated[str, typer.Option(help="App-test tier to run.")] = "normal",
    dry_run: Annotated[bool, typer.Option(help="Print the planned test command without executing it.")] = False,
    report_dir: Annotated[Path | None, typer.Option(help="Optional directory for selftest execution metadata.")] = None,
    junit_xml: Annotated[Path | None, typer.Option(help="Optional pytest JUnit XML output path.")] = None,
) -> None:
    """Run AgentBlaster's own SDLC test harness."""
    if ctx.invoked_subcommand is not None:
        return
    try:
        command = build_selftest_command(tier, report_dir=report_dir, junit_xml=junit_xml)
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
) -> None:
    """Run or plan dashboard GUI tests."""
    command = build_selftest_command(
        "gui",
        browser=browser,
        headed=headed,
        report_dir=report_dir,
        junit_xml=junit_xml,
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
            run_summaries.append(_matrix_execution_run_summary(index, run_entry, summary))
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


def _matrix_execution_run_summary(index: int, run_entry, summary: RunSummary) -> MatrixExecutionRunSummary:
    manifest_path = Path(summary.manifest_path)
    return MatrixExecutionRunSummary(
        index=index,
        engine=run_entry.engine,
        provider=summary.provider,
        model=summary.model,
        suite=summary.suite,
        suite_file=str(run_entry.suite_file) if run_entry.suite_file is not None else None,
        run_id=summary.run_id,
        ok=summary.failed == 0,
        total_cases=summary.total_cases,
        passed=summary.passed,
        failed=summary.failed,
        concurrency=summary.concurrency,
        results_path=summary.results_path,
        manifest_path=summary.manifest_path,
        summary_path=str(manifest_path.with_name("summary.json")),
    )


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
        typer.Option(help="Comma-separated formats: html,md,json,publication,card."),
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
    suites: Annotated[str, typer.Option(help="Comma-separated built-in suite names to stress.")] = "prefill,trace-replay",
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
    suites: Annotated[str, typer.Option(help="Comma-separated built-in suite names for the campaign.")] = "smoke,structured,toolcall,toolsim,trace-replay,prefill,cache-control,lcp-context",
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
        typer.Option(help="Comma-separated formats: html,md,json."),
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


@matrix_app.command("scorecard")
def matrix_scorecard(
    summary_json: Annotated[Path, typer.Argument(help="Matrix execution summary JSON produced by --matrix-summary-json.")],
    format: Annotated[
        str,
        typer.Option(help="Comma-separated formats: html,md,json."),
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
    )
    typer.echo(format_matrix_gate_report(report), nl=False)
    if output_json is not None:
        typer.echo(str(write_matrix_gate_json(report, output_json)))
    if not report.ok:
        raise typer.Exit(code=1)


@app.command()
def export(
    run_dir: Annotated[Path, typer.Argument(help="Run artifact directory.")],
    format: Annotated[str, typer.Option(help="Comma-separated formats: jsonl,csv.")] = "jsonl,csv",
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
        security_policy = load_policy(policy)
        enforce_dashboard_policy(
            security_policy,
            host=host,
            port=port,
            allow_non_loopback=allow_non_loopback,
            auth_configured=auth_token is not None,
        )
        assert_dashboard_bind_allowed(
            host,
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


@app.command()
def cleanup(
    run_dir: Annotated[Path, typer.Argument(help="Run artifact directory.")],
    raw: Annotated[bool, typer.Option(help="Delete raw trace artifacts.")] = True,
    reports: Annotated[bool, typer.Option(help="Delete generated report artifacts.")] = False,
    exports: Annotated[bool, typer.Option(help="Delete exported result artifacts.")] = False,
    all_artifacts: Annotated[bool, typer.Option(help="Delete the entire run directory.")] = False,
) -> None:
    """Clean up generated run artifacts according to retention needs."""
    try:
        removed = cleanup_run(run_dir, raw=raw, reports=reports, exports=exports, all_artifacts=all_artifacts)
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    for path in removed:
        typer.echo(str(path))


@app.command("cleanup-expired")
def cleanup_expired(
    runs: Annotated[Path, typer.Option(help="Directory containing AgentBlaster run artifacts.")] = Path("runs"),
    execute: Annotated[bool, typer.Option(help="Apply planned retention cleanup actions. Defaults to dry-run.")] = False,
    output_json: Annotated[Path | None, typer.Option(help="Optional JSON path for cleanup plan or execution result.")] = None,
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for retention cleanup events.")] = None,
) -> None:
    """Plan or apply cleanup for artifacts whose retention metadata has expired."""
    actions = plan_expired_cleanup(runs)
    result_actions = apply_expired_cleanup(actions) if execute else actions
    payload = [action.model_dump(mode="json") for action in result_actions]
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        typer.echo(str(output_json))
    AuditLogger(audit_log).emit(
        "retention_cleanup_executed" if execute else "retention_cleanup_planned",
        runs_dir=str(runs),
        action_count=len(result_actions),
        actions=payload,
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


@release_app.command("qualification-bundle")
def release_qualification_bundle(
    output_dir: Annotated[Path, typer.Option(help="Directory for the release qualification bundle.")],
    name: Annotated[str, typer.Option(help="Release qualification bundle name.")] = "release-qualification",
    evidence_bundle: Annotated[list[Path] | None, typer.Option(help="Evidence bundle artifact. Can be repeated.")] = None,
    comparison_gate: Annotated[list[Path] | None, typer.Option(help="Comparison gate JSON artifact. Can be repeated.")] = None,
    matrix_gate: Annotated[list[Path] | None, typer.Option(help="Matrix gate JSON artifact. Can be repeated.")] = None,
    release_provenance: Annotated[Path | None, typer.Option(help="Release provenance JSON artifact.")] = None,
    publication_bundle: Annotated[list[Path] | None, typer.Option(help="Publication bundle artifact. Can be repeated.")] = None,
    selftest_report: Annotated[list[Path] | None, typer.Option(help="Selftest report artifact. Can be repeated.")] = None,
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for release qualification events.")] = None,
) -> None:
    """Create a redaction-safe release qualification package from gate and evidence artifacts."""
    try:
        path = create_release_qualification_bundle(
            name=name,
            output_dir=output_dir,
            evidence_bundles=evidence_bundle,
            comparison_gates=comparison_gate,
            matrix_gates=matrix_gate,
            release_provenance=release_provenance,
            publication_bundles=publication_bundle,
            selftest_reports=selftest_report,
        )
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    AuditLogger(audit_log).emit(
        "release_qualification_bundle_created",
        artifact=str(path),
        name=name,
        evidence_bundles=[str(item) for item in evidence_bundle or []],
        comparison_gates=[str(item) for item in comparison_gate or []],
        matrix_gates=[str(item) for item in matrix_gate or []],
        release_provenance=str(release_provenance) if release_provenance else None,
        publication_bundles=[str(item) for item in publication_bundle or []],
        selftest_reports=[str(item) for item in selftest_report or []],
    )
    typer.echo(str(path))


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
    profile: Annotated[str, typer.Option(help="Harness profile: prefill, concurrency, or contract-fuzz.")] = "contract-fuzz",
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


@models_app.command("targets")
def model_targets() -> None:
    """List canonical model targets for standardized comparisons."""
    for target in list_model_targets():
        typer.echo(
            f"{target.id}\t{target.default_model}\t{target.metadata.architecture or 'unknown'}\t"
            f"{target.parameter_count}\t{target.density}\t{target.display_name}"
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
    secret_mode: Annotated[str, typer.Option(help="Secret backend mode for the plan: env or keyring.")] = "env",
    api_key_env: Annotated[str | None, typer.Option(help="Environment variable name for env mode or key staging.")] = None,
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
    metrics_url: Annotated[str | None, typer.Option(help="Optional Prometheus /metrics URL to snapshot before and after runs.")] = None,
    tls_verify: Annotated[
        bool,
        typer.Option("--tls-verify/--no-tls-verify", help="Verify TLS certificates for HTTPS provider requests."),
    ] = True,
    ca_bundle: Annotated[Path | None, typer.Option(help="Optional custom CA bundle path for enterprise TLS gateways.")] = None,
    remote: Annotated[bool, typer.Option(help="Mark provider as internet-facing/remote.")] = False,
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
        metrics_url=metrics_url,
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
        api_key_ref=provider.api_key_ref.display() if provider.api_key_ref else None,
        metrics_url=str(provider.metrics_url).rstrip("/") if provider.metrics_url else None,
        tls_verify=provider.tls_verify,
        ca_bundle=str(provider.ca_bundle) if provider.ca_bundle else None,
    )
    typer.echo(f"saved provider {provider.name}")


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
        api_key_ref=provider.api_key_ref.display() if provider.api_key_ref else None,
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
        secret = provider.api_key_ref.display() if provider.api_key_ref else "none"
        typer.echo(
            f"{provider.name}\t{provider.contract.value}\t{str(provider.base_url).rstrip('/')}\t"
            f"remote={str(provider.remote).lower()}\tsecret={secret}"
        )


@providers_app.command("show")
def show_provider(name: Annotated[str, typer.Argument(help="Provider profile name.")]) -> None:
    """Show a configured provider profile without secret values."""
    provider = ProviderStore().get(name)
    secret = provider.api_key_ref.display() if provider.api_key_ref else "none"
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


@providers_auth_app.command("set")
def set_auth(
    provider: Annotated[str, typer.Option(help="Provider profile name.")],
    api_key_stdin: Annotated[bool, typer.Option(help="Read API key from stdin and store in keyring.")] = False,
    api_key_env: Annotated[
        str | None,
        typer.Option(help="Use an environment variable as the provider API key reference."),
    ] = None,
    audit_log: Annotated[Path | None, typer.Option(help="Optional JSONL audit log path for secret reference changes.")] = None,
) -> None:
    """Configure a provider API-key reference without storing plaintext config secrets."""
    if api_key_stdin and api_key_env:
        raise typer.BadParameter("choose only one of --api-key-stdin or --api-key-env")
    if not api_key_stdin and not api_key_env:
        raise typer.BadParameter("use --api-key-stdin for keyring storage or --api-key-env for portable env refs")

    ref = (
        SecretRef(kind="env", name=api_key_env)
        if api_key_env
        else SecretRef(kind="keyring", name=f"{provider}:api_key")
    )
    store = ProviderStore()
    config = store.get(provider)
    if api_key_stdin:
        api_key = sys.stdin.read().strip()
        try:
            SecretResolver().set(ref, api_key)
        except AgentBlasterError as exc:
            raise typer.BadParameter(str(exc)) from exc
    store.upsert(config.model_copy(update={"api_key_ref": ref}))
    AuditLogger(audit_log).emit(
        "provider_auth_ref_changed",
        provider=provider,
        api_key_ref=ref.display(),
        ref_kind=ref.kind,
        stored_keyring_secret=api_key_stdin,
    )
    typer.echo(f"stored {ref.kind} secret reference for {provider}")


@providers_auth_app.command("test")
def test_auth(provider: Annotated[str, typer.Option(help="Provider profile name.")]) -> None:
    """Confirm that a provider's secret reference resolves without printing it."""
    config = ProviderStore().get(provider)
    if config.api_key_ref is None:
        raise typer.BadParameter(f"provider {provider} has no api_key_ref")
    if not SecretResolver().resolve(config.api_key_ref):
        raise typer.BadParameter(f"secret reference does not resolve: {config.api_key_ref.display()}")
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
    typer.echo(f"api_key_ref: {ref.display()}")
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
        if ref.kind != "keyring":
            raise typer.BadParameter("only keyring secrets can be deleted by AgentBlaster; unset env secrets in your shell or CI")
        try:
            SecretResolver().delete(ref)
        except AgentBlasterError as exc:
            raise typer.BadParameter(str(exc)) from exc
    store.upsert(config.model_copy(update={"api_key_ref": None}))
    AuditLogger(audit_log).emit(
        "provider_auth_ref_cleared",
        provider=provider,
        previous_api_key_ref=ref.display() if ref else None,
        deleted_keyring_secret=delete_secret and ref is not None and ref.kind == "keyring",
    )
    if ref is None:
        typer.echo(f"auth reference already empty for {provider}")
    elif delete_secret:
        typer.echo(f"cleared auth reference and deleted keyring secret for {provider}")
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
