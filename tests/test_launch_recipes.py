from __future__ import annotations

from typer.testing import CliRunner

from agentblaster.cli import app
from agentblaster.launch_recipes import build_launch_recipe, format_launch_recipe_markdown, launch_recipe_catalog


def test_launch_recipe_catalog_includes_target_local_engines() -> None:
    catalog = launch_recipe_catalog()
    engines = {item["engine"] for item in catalog["engines"]}

    assert {"afm", "mlx-lm", "ollama", "lm-studio", "omlx", "rapid-mlx", "vllm-mlx"} <= engines
    assert catalog["schema_version"] == "agentblaster.launch-recipe-catalog.v1"


def test_afm_launch_recipe_renders_provider_setup_without_execution() -> None:
    recipe = build_launch_recipe("afm", model="mlx-community/Qwen3.6-27B", port=9999, provider_name="afm-qwen")

    assert recipe["schema_version"] == "agentblaster.launch-recipe.v1"
    assert recipe["base_url"] == "http://127.0.0.1:9999/v1"
    assert recipe["metrics_url"] == "http://127.0.0.1:9999/metrics"
    assert recipe["launch_command"][:4] == ["afm", "mlx", "-m", "mlx-community/Qwen3.6-27B"]
    assert "--metrics-url" in recipe["provider_add_command"]
    assert recipe["safety"]["executes_commands"] is False


def test_native_launch_recipe_declares_native_adapter() -> None:
    recipe = build_launch_recipe("ollama-native", model="qwen3.6:27b")

    assert recipe["contract"] == "native"
    assert recipe["native_adapter"] == "ollama"
    assert "--native-adapter" in recipe["provider_add_command"]
    assert "ollama" in format_launch_recipe_markdown(recipe)


def test_cli_launch_recipes_catalog_and_single_recipe(tmp_path) -> None:
    runner = CliRunner()
    output = tmp_path / "recipe.json"

    catalog = runner.invoke(app, ["engines", "launch-recipes", "--catalog"])
    recipe = runner.invoke(
        app,
        [
            "engines",
            "launch-recipes",
            "--engine",
            "afm",
            "--model",
            "mlx-community/Qwen3.6-27B",
            "--output-json",
            str(output),
        ],
    )

    assert catalog.exit_code == 0, catalog.output
    assert "afm" in catalog.output
    assert "lm-studio" in catalog.output
    assert recipe.exit_code == 0, recipe.output
    assert "base_url: http://127.0.0.1:9999/v1" in recipe.output
    assert output.exists()
