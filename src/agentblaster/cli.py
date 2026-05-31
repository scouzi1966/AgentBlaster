from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from agentblaster.adapters import adapter_for
from agentblaster.audit import AuditLogger
from agentblaster.config import ProviderStore
from agentblaster.errors import AgentBlasterError
from agentblaster.exports import export_results
from agentblaster.matrix import load_matrix_file
from agentblaster.models import ApiContract, ProviderConfig, RawTraceMode, SecretRef
from agentblaster.policy import enforce_provider_policy, load_policy, offline_policy
from agentblaster.presets import LOCAL_ENGINE_PRESETS, get_preset
from agentblaster.reports import generate_reports
from agentblaster.runner import BenchmarkRunner
from agentblaster.secrets import SecretResolver
from agentblaster.suites import BUILTIN_SUITES, get_builtin_suite, load_suite_file, validate_case_or_suite_file

app = typer.Typer(help="AgentBlaster local agentic benchmark suite.")
engines_app = typer.Typer(help="Inspect and configure benchmark engines.")
providers_app = typer.Typer(help="Manage local and remote provider profiles.")
providers_auth_app = typer.Typer(help="Manage provider authentication references.")
app.add_typer(engines_app, name="engines")
app.add_typer(providers_app, name="providers")
providers_app.add_typer(providers_auth_app, name="auth")

BUILT_IN_ENGINES = ["afm", "mlx-lm", "ollama", "lm-studio", "omlx", "rapid-mlx", "vllm-mlx"]


@app.command()
def version() -> None:
    """Print the AgentBlaster version."""
    from agentblaster import __version__

    typer.echo(__version__)


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
    raw_traces: Annotated[
        RawTraceMode,
        typer.Option(help="Raw response capture mode."),
    ] = RawTraceMode.REDACTED,
    no_raw_traces: Annotated[bool, typer.Option(help="Disable raw response capture.")] = False,
) -> None:
    """Run a benchmark suite against a configured provider."""
    if matrix is not None:
        _run_matrix(
            matrix=matrix,
            output_dir=output_dir,
            policy=policy,
            audit_log=audit_log,
            offline=offline,
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
    )

    _print_summary(summary)


def _run_matrix(
    *,
    matrix: Path,
    output_dir: Path,
    policy: Path | None,
    audit_log: Path | None,
    offline: bool,
) -> None:
    matrix_definition = load_matrix_file(matrix)
    typer.echo(f"matrix: {matrix_definition.name}")
    for index, run_entry in enumerate(matrix_definition.runs, start=1):
        trace_mode = RawTraceMode.OFF if run_entry.no_raw_traces else run_entry.raw_traces
        summary = _run_one(
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
        )
        typer.echo(f"[{index}/{len(matrix_definition.runs)}] {summary.run_id} {summary.provider} {summary.suite} ok={summary.failed == 0}")


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
        enforce_provider_policy(provider, security_policy, raw_trace_mode=trace_mode, concurrency=concurrency)
    except AgentBlasterError as exc:
        audit.emit("policy_violation", provider=provider.name, reason=str(exc))
        raise typer.BadParameter(str(exc)) from exc

    try:
        audit.emit("run_started", provider=provider.name, suite=suite, remote=provider.remote)
        summary = BenchmarkRunner(
            provider,
            suite_definition,
            output_dir=output_dir,
            raw_trace_mode=trace_mode,
            concurrency=concurrency,
        ).run(model=model)
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


@app.command()
def report(
    run_dir: Annotated[Path, typer.Argument(help="Run artifact directory.")],
    format: Annotated[str, typer.Option(help="Comma-separated formats: html,json.")] = "html,json",
) -> None:
    """Generate reports from a completed run directory."""
    try:
        paths = generate_reports(run_dir, [item.strip() for item in format.split(",")])
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    for path in paths:
        typer.echo(str(path))


@app.command()
def export(
    run_dir: Annotated[Path, typer.Argument(help="Run artifact directory.")],
    format: Annotated[str, typer.Option(help="Comma-separated formats: jsonl,csv.")] = "jsonl,csv",
    output_dir: Annotated[Path | None, typer.Option(help="Optional export output directory.")] = None,
) -> None:
    """Export normalized results from a completed run directory."""
    try:
        paths = export_results(run_dir, [item.strip() for item in format.split(",")], output_dir=output_dir)
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    for path in paths:
        typer.echo(str(path))


@engines_app.command("list")
def list_engines() -> None:
    """List planned built-in engine adapters."""
    for engine in BUILT_IN_ENGINES:
        typer.echo(engine)


@engines_app.command()
def probe(
    engine: Annotated[str, typer.Option(help="Engine profile name.")],
    base_url: Annotated[str, typer.Option(help="OpenAI-compatible base URL.")],
    contract: Annotated[ApiContract, typer.Option(help="API contract to probe.")] = ApiContract.OPENAI,
) -> None:
    """Probe an ad hoc engine endpoint without saving it."""
    provider = ProviderConfig(name=engine, contract=contract, base_url=base_url, remote=False)
    _print_probe(provider)


@providers_app.command("add")
def add_provider(
    name: Annotated[str, typer.Option(help="Provider profile name.")],
    contract: Annotated[ApiContract, typer.Option(help="API contract implemented by the provider.")],
    base_url: Annotated[str, typer.Option(help="Provider base URL.")],
    default_model: Annotated[str | None, typer.Option(help="Optional default model id.")] = None,
    api_key_env: Annotated[
        str | None,
        typer.Option(help="Environment variable containing the API key."),
    ] = None,
    remote: Annotated[bool, typer.Option(help="Mark provider as internet-facing/remote.")] = False,
) -> None:
    """Add or update a provider profile."""
    api_key_ref = SecretRef(kind="env", name=api_key_env) if api_key_env else None
    provider = ProviderConfig(
        name=name,
        contract=contract,
        base_url=base_url,
        default_model=default_model,
        api_key_ref=api_key_ref,
        remote=remote,
    )
    ProviderStore().upsert(provider)
    typer.echo(f"saved provider {provider.name}")


@providers_app.command("presets")
def list_provider_presets() -> None:
    """List built-in provider presets for common local engines."""
    for preset in LOCAL_ENGINE_PRESETS.values():
        typer.echo(f"{preset.name}\t{preset.contract.value}\t{preset.base_url}\t{preset.description}")


@providers_app.command("add-preset")
def add_provider_preset(
    preset: Annotated[str, typer.Option(help="Built-in preset name.")],
    name: Annotated[str | None, typer.Option(help="Provider profile name override.")] = None,
    base_url: Annotated[str | None, typer.Option(help="Base URL override.")] = None,
) -> None:
    """Add or update a provider from a built-in local-engine preset."""
    provider = get_preset(preset).to_provider(name=name, base_url=base_url)
    ProviderStore().upsert(provider)
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
    typer.echo(f"remote: {str(provider.remote).lower()}")
    typer.echo(f"api_key_ref: {secret}")


@providers_app.command("probe")
def probe_provider(name: Annotated[str, typer.Argument(help="Provider profile name.")]) -> None:
    """Probe a configured provider endpoint."""
    provider = ProviderStore().get(name)
    _print_probe(provider)


@providers_auth_app.command("set")
def set_auth(
    provider: Annotated[str, typer.Option(help="Provider profile name.")],
    api_key_stdin: Annotated[bool, typer.Option(help="Read API key from stdin and store in keyring.")] = False,
) -> None:
    """Store a provider API key in the optional OS keyring backend."""
    if not api_key_stdin:
        raise typer.BadParameter("only --api-key-stdin is supported to avoid shell history leakage")

    api_key = sys.stdin.read().strip()
    ref = SecretRef(kind="keyring", name=f"{provider}:api_key")
    SecretResolver().set(ref, api_key)

    store = ProviderStore()
    config = store.get(provider)
    store.upsert(config.model_copy(update={"api_key_ref": ref}))
    typer.echo(f"stored keyring secret reference for {provider}")


@providers_auth_app.command("test")
def test_auth(provider: Annotated[str, typer.Option(help="Provider profile name.")]) -> None:
    """Confirm that a provider's secret reference resolves without printing it."""
    config = ProviderStore().get(provider)
    if config.api_key_ref is None:
        raise typer.BadParameter(f"provider {provider} has no api_key_ref")
    if not SecretResolver().resolve(config.api_key_ref):
        raise typer.BadParameter(f"secret reference does not resolve: {config.api_key_ref.display()}")
    typer.echo(f"secret reference resolves for {provider}")


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


if __name__ == "__main__":
    app()
