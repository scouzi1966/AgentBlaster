from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentblaster.errors import ConfigError
from agentblaster.models import ApiContract


@dataclass(frozen=True)
class LaunchRecipeTemplate:
    engine: str
    title: str
    contract: ApiContract
    default_port: int
    base_path: str
    native_adapter: str | None
    launch_command: tuple[str, ...]
    metrics_path: str | None = None
    provider_headers: tuple[tuple[str, str], ...] = ()
    setup_commands: tuple[tuple[str, ...], ...] = ()
    notes: tuple[str, ...] = ()


LAUNCH_RECIPES: tuple[LaunchRecipeTemplate, ...] = (
    LaunchRecipeTemplate(
        engine="afm",
        title="AFM MLX OpenAI-compatible local server",
        contract=ApiContract.OPENAI,
        default_port=9999,
        base_path="/v1",
        native_adapter=None,
        launch_command=("afm", "mlx", "-m", "{model}", "--host", "{host}", "--port", "{port}"),
        metrics_path="/metrics",
        notes=("Use the locally built or installed AFM binary.", "Set MACAFM_MLX_MODEL_CACHE externally when using a shared model cache."),
    ),
    LaunchRecipeTemplate(
        engine="mlx-lm",
        title="mlx-lm OpenAI-compatible reference server",
        contract=ApiContract.OPENAI,
        default_port=8080,
        base_path="/v1",
        native_adapter=None,
        launch_command=("python", "-m", "mlx_lm.server", "--model", "{model}", "--host", "{host}", "--port", "{port}"),
        notes=("Install mlx-lm in the active Python environment before using this recipe.",),
    ),
    LaunchRecipeTemplate(
        engine="ollama",
        title="Ollama OpenAI-compatible local endpoint",
        contract=ApiContract.OPENAI,
        default_port=11434,
        base_path="/v1",
        native_adapter=None,
        setup_commands=(("ollama", "pull", "{model}"),),
        launch_command=("ollama", "serve"),
        notes=("Ollama uses its own model names; override --model to match a pulled model.",),
    ),
    LaunchRecipeTemplate(
        engine="ollama-native",
        title="Ollama native local endpoint",
        contract=ApiContract.NATIVE,
        default_port=11434,
        base_path="",
        native_adapter="ollama",
        setup_commands=(("ollama", "pull", "{model}"),),
        launch_command=("ollama", "serve"),
        notes=("Use this recipe when collecting Ollama native timing stats such as prompt_eval_duration and eval_duration.",),
    ),
    LaunchRecipeTemplate(
        engine="lm-studio",
        title="LM Studio OpenAI-compatible server",
        contract=ApiContract.OPENAI,
        default_port=1234,
        base_path="/v1",
        native_adapter=None,
        launch_command=("lms", "server", "start", "--port", "{port}"),
        notes=("LM Studio can also be started from the GUI; confirm the loaded model and server port before benchmarking.",),
    ),
    LaunchRecipeTemplate(
        engine="lm-studio-responses",
        title="LM Studio OpenAI Responses-compatible server",
        contract=ApiContract.OPENAI_RESPONSES,
        default_port=1234,
        base_path="/v1",
        native_adapter=None,
        launch_command=("lms", "server", "start", "--port", "{port}"),
        notes=("Use only when the LM Studio version/model exposes the Responses-compatible surface.",),
    ),
    LaunchRecipeTemplate(
        engine="lm-studio-anthropic",
        title="LM Studio Anthropic Messages-compatible server",
        contract=ApiContract.ANTHROPIC,
        default_port=1234,
        base_path="/v1",
        native_adapter=None,
        provider_headers=(("anthropic-version", "2023-06-01"),),
        launch_command=("lms", "server", "start", "--port", "{port}"),
        notes=("Use only when the LM Studio version/model exposes the Anthropic Messages-compatible surface.",),
    ),
    LaunchRecipeTemplate(
        engine="lm-studio-native",
        title="LM Studio native REST server",
        contract=ApiContract.NATIVE,
        default_port=1234,
        base_path="",
        native_adapter="lm-studio",
        launch_command=("lms", "server", "start", "--port", "{port}"),
        notes=("Use this recipe for LM Studio native stats surfaces; native endpoint availability varies by version.",),
    ),
    LaunchRecipeTemplate(
        engine="omlx",
        title="oMLX OpenAI-compatible local server",
        contract=ApiContract.OPENAI,
        default_port=8000,
        base_path="/v1",
        native_adapter=None,
        launch_command=("omlx", "serve", "--model", "{model}", "--host", "{host}", "--port", "{port}"),
        notes=("Confirm the installed oMLX command and flags; this recipe is a reviewable starting point.",),
    ),
    LaunchRecipeTemplate(
        engine="rapid-mlx",
        title="Rapid-MLX OpenAI-compatible local server",
        contract=ApiContract.OPENAI,
        default_port=8000,
        base_path="/v1",
        native_adapter=None,
        launch_command=("rapid-mlx", "serve", "--model", "{model}", "--host", "{host}", "--port", "{port}"),
        notes=("Confirm the installed Rapid-MLX command and flags before use; do not assume recipe output has been executed.",),
    ),
    LaunchRecipeTemplate(
        engine="vllm-mlx",
        title="vLLM-MLX OpenAI-compatible server",
        contract=ApiContract.OPENAI,
        default_port=8000,
        base_path="/v1",
        native_adapter=None,
        launch_command=("python", "-m", "vllm.entrypoints.openai.api_server", "--model", "{model}", "--host", "{host}", "--port", "{port}"),
        notes=("Use only with an installed vLLM-MLX environment and compatible model artifact.",),
    ),
    LaunchRecipeTemplate(
        engine="vllm-mlx-anthropic",
        title="vLLM-MLX Anthropic Messages-compatible server",
        contract=ApiContract.ANTHROPIC,
        default_port=8000,
        base_path="/v1",
        native_adapter=None,
        provider_headers=(("anthropic-version", "2023-06-01"),),
        launch_command=("python", "-m", "vllm.entrypoints.openai.api_server", "--model", "{model}", "--host", "{host}", "--port", "{port}"),
        notes=("Use only with a vLLM-MLX build that exposes the Anthropic Messages-compatible API.",),
    ),
)


def list_launch_recipe_templates() -> list[LaunchRecipeTemplate]:
    return list(LAUNCH_RECIPES)


def get_launch_recipe_template(engine: str) -> LaunchRecipeTemplate:
    for recipe in LAUNCH_RECIPES:
        if recipe.engine == engine:
            return recipe
    available = ", ".join(recipe.engine for recipe in LAUNCH_RECIPES)
    raise ConfigError(f"unknown launch recipe engine: {engine}; available engines: {available}")


def build_launch_recipe(
    engine: str,
    *,
    model: str,
    host: str | None = None,
    port: int | None = None,
    provider_name: str | None = None,
) -> dict[str, Any]:
    template = get_launch_recipe_template(engine)
    resolved_host = host or "127.0.0.1"
    resolved_port = port or template.default_port
    resolved_provider = provider_name or template.engine
    base_url = f"http://{resolved_host}:{resolved_port}{template.base_path}"
    metrics_url = f"http://{resolved_host}:{resolved_port}{template.metrics_path}" if template.metrics_path else None
    context = {"model": model, "host": resolved_host, "port": str(resolved_port)}
    provider_command = [
        "agentblaster",
        "providers",
        "add",
        "--name",
        resolved_provider,
        "--contract",
        template.contract.value,
        "--base-url",
        base_url,
        "--default-model",
        model,
    ]
    if metrics_url:
        provider_command.extend(["--metrics-url", metrics_url])
    if template.native_adapter:
        provider_command.extend(["--native-adapter", template.native_adapter])
    for header_name, header_value in template.provider_headers:
        provider_command.extend(["--header", f"{header_name}={header_value}"])
    return {
        "schema_version": "agentblaster.launch-recipe.v1",
        "engine": template.engine,
        "title": template.title,
        "contract": template.contract.value,
        "native_adapter": template.native_adapter,
        "host": resolved_host,
        "port": resolved_port,
        "model": model,
        "provider_name": resolved_provider,
        "base_url": base_url,
        "metrics_url": metrics_url,
        "setup_commands": [_render_tokens(command, context) for command in template.setup_commands],
        "launch_command": _render_tokens(template.launch_command, context),
        "provider_add_command": provider_command,
        "post_launch_checks": [
            ["agentblaster", "providers", "probe", resolved_provider],
            ["agentblaster", "providers", "contract-check", "--provider", resolved_provider, "--model", model],
            ["agentblaster", "providers", "metric-coverage", "--provider", resolved_provider],
        ],
        "safety": {
            "executes_commands": False,
            "stores_secrets": False,
            "remote": False,
            "review_required": True,
        },
        "notes": list(template.notes),
    }


def launch_recipe_catalog() -> dict[str, Any]:
    return {
        "schema_version": "agentblaster.launch-recipe-catalog.v1",
        "engines": [
            {
                "engine": recipe.engine,
                "title": recipe.title,
                "contract": recipe.contract.value,
                "default_port": recipe.default_port,
                "native_adapter": recipe.native_adapter,
                "provider_header_names": [name for name, _value in recipe.provider_headers],
                "has_metrics_url": recipe.metrics_path is not None,
                "notes": list(recipe.notes),
            }
            for recipe in LAUNCH_RECIPES
        ],
    }


def write_launch_recipe_json(payload: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def format_launch_recipe_markdown(recipe: dict[str, Any]) -> str:
    if recipe.get("schema_version") == "agentblaster.launch-recipe-catalog.v1":
        lines = ["# AgentBlaster Launch Recipe Catalog", ""]
        for engine in recipe["engines"]:
            lines.append(f"- `{engine['engine']}`: {engine['title']} ({engine['contract']}, port {engine['default_port']})")
        return "\n".join(lines) + "\n"
    lines = [
        f"# Launch Recipe: {recipe['engine']}",
        "",
        recipe["title"],
        "",
        "## Provider",
        "",
        f"- Contract: `{recipe['contract']}`",
        f"- Base URL: `{recipe['base_url']}`",
        f"- Model: `{recipe['model']}`",
        "",
    ]
    if recipe.get("setup_commands"):
        lines.extend(["## Setup commands", "", "```bash"])
        lines.extend(_shell(command) for command in recipe["setup_commands"])
        lines.extend(["```", ""])
    lines.extend(["## Launch command", "", "```bash", _shell(recipe["launch_command"]), "```", ""])
    lines.extend(["## Provider configuration", "", "```bash", _shell(recipe["provider_add_command"]), "```", ""])
    lines.extend(["## Post-launch checks", "", "```bash"])
    lines.extend(_shell(command) for command in recipe["post_launch_checks"])
    lines.extend(["```", "", "## Notes", ""])
    lines.extend(f"- {note}" for note in recipe.get("notes", []))
    lines.extend(["", "## Safety", "", "This recipe only renders commands. AgentBlaster does not execute launch commands or store secrets from this output."])
    return "\n".join(lines).rstrip() + "\n"


def _render_tokens(tokens: tuple[str, ...], context: dict[str, str]) -> list[str]:
    return [token.format(**context) for token in tokens]


def _shell(tokens: list[str]) -> str:
    return shlex.join(tokens)
