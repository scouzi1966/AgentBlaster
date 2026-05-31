from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from agentblaster.adapters import adapter_for
from agentblaster.config import ProviderStore
from agentblaster.errors import AgentBlasterError
from agentblaster.models import ApiContract, ProviderConfig, RawTraceMode, SecretRef
from agentblaster.policy import enforce_provider_policy, load_policy, offline_policy
from agentblaster.runner import SmokeRunner
from agentblaster.secrets import SecretResolver

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
    suite: Annotated[str, typer.Option(help="Benchmark suite to run. Currently: smoke.")],
    engine: Annotated[str, typer.Option(help="Configured provider/engine profile name.")],
    model: Annotated[str | None, typer.Option(help="Model id. Required unless provider has a default model.")] = None,
    output_dir: Annotated[Path, typer.Option(help="Directory where run artifacts are written.")] = Path("runs"),
    policy: Annotated[Path | None, typer.Option(help="Optional agentblaster.policy.yaml path.")] = None,
    offline: Annotated[bool, typer.Option(help="Block providers marked as remote.")] = False,
    raw_traces: Annotated[
        RawTraceMode,
        typer.Option(help="Raw response capture mode."),
    ] = RawTraceMode.REDACTED,
    no_raw_traces: Annotated[bool, typer.Option(help="Disable raw response capture.")] = False,
) -> None:
    """Run a benchmark suite against a configured provider."""
    if suite != "smoke":
        raise typer.BadParameter("only the smoke suite is implemented in this slice")

    provider = ProviderStore().get(engine)
    trace_mode = RawTraceMode.OFF if no_raw_traces else raw_traces
    security_policy = offline_policy() if offline else load_policy(policy)
    try:
        enforce_provider_policy(provider, security_policy, raw_trace_mode=trace_mode)
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc

    try:
        result = SmokeRunner(provider, output_dir=output_dir, raw_trace_mode=trace_mode).run(model=model)
    except AgentBlasterError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"run_id: {result.run_id}")
    typer.echo(f"case_id: {result.case_id}")
    typer.echo(f"ok: {str(result.ok).lower()}")
    typer.echo(f"latency_ms: {result.latency_ms}")
    if result.raw_response_path:
        typer.echo(f"raw_response_path: {result.raw_response_path}")


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
