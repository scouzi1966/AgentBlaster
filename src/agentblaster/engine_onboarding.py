from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentblaster.engine_targets import get_engine_target
from agentblaster.errors import ConfigError
from agentblaster.launch_recipes import build_launch_recipe, format_launch_recipe_markdown
from agentblaster.model_catalog import list_model_targets
from agentblaster.presets import LOCAL_ENGINE_PRESETS


LOCAL_ENGINE_ONBOARDING_SCHEMA_VERSION = "agentblaster.local-engine-onboarding.v1"
DEFAULT_LOCAL_ENGINES = (
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
)
ENGINE_TARGET_BY_PRESET = {
    "afm": "afm-mlx",
    "mlx-lm": "mlx-lm",
    "ollama": "ollama-mlx",
    "ollama-native": "ollama-mlx",
    "lm-studio": "lm-studio",
    "lm-studio-responses": "lm-studio",
    "lm-studio-anthropic": "lm-studio",
    "lm-studio-native": "lm-studio",
    "omlx": "omlx",
    "rapid-mlx": "rapid-mlx",
    "vllm-mlx": "vllm-mlx",
    "vllm-mlx-anthropic": "vllm-mlx",
}


def build_local_engine_onboarding(
    *,
    engines: list[str] | None = None,
    model: str = "mlx-community/Qwen3.6-27B",
) -> dict[str, Any]:
    selected_engines = engines or list(DEFAULT_LOCAL_ENGINES)
    targets = [target.model_dump(mode="json") for target in list_model_targets()]
    entries = []
    for engine in selected_engines:
        name = engine.strip()
        if not name:
            continue
        if name not in LOCAL_ENGINE_PRESETS:
            available = ", ".join(sorted(LOCAL_ENGINE_PRESETS))
            raise ConfigError(f"unknown local engine preset: {name}; available engines: {available}")
        preset = LOCAL_ENGINE_PRESETS[name]
        recipe = build_launch_recipe(name, model=model)
        engine_target = _engine_target_summary(name)
        entries.append(
            {
                "engine": name,
                "description": preset.description,
                "contract": preset.contract.value,
                "base_url": preset.base_url,
                "native_adapter": preset.native_adapter,
                "declared_capabilities": dict(sorted(preset.capabilities.items())),
                "default_remote": preset.remote,
                "engine_target": engine_target,
                "launch_recipe": recipe,
                "provider_preset_command": ["agentblaster", "providers", "add-preset", "--preset", name],
                "recommended_static_checks": [
                    ["agentblaster", "engines", "targets", "--target", engine_target["id"]],
                    ["agentblaster", "engines", "launch-recipes", "--engine", name, "--model", model],
                    ["agentblaster", "providers", "check-suite", "--provider", name, "--suite", "smoke"],
                    ["agentblaster", "providers", "metric-coverage", "--provider", name],
                    ["agentblaster", "providers", "contract-check", "--provider", name, "--model", model],
                ],
            }
        )
    return {
        "schema_version": LOCAL_ENGINE_ONBOARDING_SCHEMA_VERSION,
        "model": model,
        "model_targets": targets,
        "engine_count": len(entries),
        "engines": entries,
        "standardization": {
            "engine_target_catalog_command": ["agentblaster", "engines", "targets"],
            "workflow_surface_catalog_command": ["agentblaster", "catalog", "workflow-surfaces"],
            "telemetry_mapping_catalog_command": ["agentblaster", "catalog", "telemetry-mappings"],
            "provider_metric_coverage_command_template": [
                "agentblaster",
                "providers",
                "metric-coverage",
                "--provider",
                "<provider>",
            ],
            "purpose": "Keep provider setup aligned with standardized engine targets before benchmark dispatch.",
        },
        "recommended_campaigns": [
            "examples/matrices/qwen-gemma-local.yaml",
            "examples/matrices/qwen-gemma-stress.yaml",
            "campaigns/qwen-gemma-local/README.md",
        ],
        "safety": {
            "executes_commands": False,
            "contacts_providers": False,
            "resolves_secrets": False,
            "writes_provider_config": False,
            "remote_provider_setup": False,
        },
        "notes": [
            "Review launch commands against the installed engine version before use.",
            "Declare provider capabilities only after the engine/model combination has been verified.",
            "Use offline dry-run planning before executing Qwen/Gemma campaign matrices.",
        ],
    }


def write_local_engine_onboarding(payload: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def format_local_engine_onboarding_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# AgentBlaster Local Engine Onboarding",
        "",
        f"Model inserted into launch recipes: `{payload['model']}`",
        "",
        "This artifact is static. It does not execute commands, contact providers, resolve secrets, or write provider config.",
        "",
        "## Engines",
        "",
    ]
    for engine in payload["engines"]:
        lines.extend(
            [
                f"### {engine['engine']}",
                "",
                f"- Description: {engine['description']}",
                f"- Contract: `{engine['contract']}`",
                f"- Base URL: `{engine['base_url']}`",
                f"- Native adapter: `{engine['native_adapter'] or 'none'}`",
                f"- Declared capabilities: {_capability_text(engine['declared_capabilities'])}",
                f"- Engine target: `{engine['engine_target']['id']}` ({engine['engine_target']['display_name']})",
                f"- Primary scoring contract: `{engine['engine_target']['standardization']['primary_scoring_contract']}`",
                f"- Telemetry profiles: {_inline_code_list(engine['engine_target']['telemetry_profiles'])}",
                f"- Workflow surfaces: {_inline_code_list(engine['engine_target']['standardization']['workflow_surfaces'])}",
                f"- Native metrics policy: {engine['engine_target']['standardization']['native_metrics_policy']}",
                "",
                "Register preset:",
                "",
                "```bash",
                _shell(engine["provider_preset_command"]),
                "```",
                "",
                "Launch recipe:",
                "",
                format_launch_recipe_markdown(engine["launch_recipe"]).strip(),
                "",
            ]
        )
    lines.extend(
        [
            "## Recommended Campaigns",
            "",
            *[f"- `{item}`" for item in payload["recommended_campaigns"]],
            "",
            "## Model Targets",
            "",
            *[
                f"- `{target['id']}`: {target['display_name']} ({target['parameter_count']}, {target['density']})"
                for target in payload["model_targets"]
            ],
            "",
        ]
    )
    return "\n".join(lines)


def _engine_target_summary(preset_name: str) -> dict[str, Any]:
    target_id = ENGINE_TARGET_BY_PRESET[preset_name]
    target = get_engine_target(target_id)
    return {
        "id": target["id"],
        "display_name": target["display_name"],
        "lifecycle": target["lifecycle"],
        "contracts": target["contracts"],
        "telemetry_profiles": target["telemetry_profiles"],
        "recommended_model_targets": target["recommended_model_targets"],
        "recommended_suites": target["recommended_suites"],
        "readiness_checks": target["readiness_checks"],
        "standardization": {
            "primary_scoring_contract": target["standardization"]["primary_scoring_contract"],
            "contract_priority": target["standardization"]["contract_priority"],
            "workflow_surfaces": target["standardization"]["workflow_surfaces"],
            "representative_agent_profiles": target["standardization"]["representative_agent_profiles"],
            "prefill_challenges": target["standardization"]["prefill_challenges"],
            "concurrency_challenges": target["standardization"]["concurrency_challenges"],
            "native_telemetry_profiles": target["standardization"]["native_telemetry_profiles"],
            "native_metrics_policy": target["standardization"]["native_metrics_policy"],
        },
    }


def _shell(tokens: list[str]) -> str:
    return " ".join(tokens)


def _capability_text(value: dict[str, bool]) -> str:
    if not value:
        return "`none`"
    return ", ".join(f"`{key}={str(enabled).lower()}`" for key, enabled in sorted(value.items()))


def _inline_code_list(values: list[str]) -> str:
    if not values:
        return "`none`"
    return ", ".join(f"`{value}`" for value in values)
