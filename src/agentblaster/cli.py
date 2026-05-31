from __future__ import annotations

import typer

app = typer.Typer(help="AgentBlaster local agentic benchmark suite.")
engines_app = typer.Typer(help="Inspect and configure benchmark engines.")
app.add_typer(engines_app, name="engines")


@app.command()
def version() -> None:
    """Print the AgentBlaster version."""
    from agentblaster import __version__

    typer.echo(__version__)


@engines_app.command("list")
def list_engines() -> None:
    """List planned built-in engine adapters."""
    engines = ["afm", "mlx-lm", "ollama", "lm-studio", "omlx", "rapid-mlx", "vllm-mlx"]
    for engine in engines:
        typer.echo(engine)


@engines_app.command()
def probe(engine: str, base_url: str) -> None:
    """Placeholder for engine capability probing."""
    typer.echo(f"probe pending: engine={engine} base_url={base_url}")


if __name__ == "__main__":
    app()
