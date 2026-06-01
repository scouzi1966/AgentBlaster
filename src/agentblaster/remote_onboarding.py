from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any, Literal

from agentblaster.errors import ConfigError
from agentblaster.presets import get_preset


SecretMode = Literal["env", "keyring"]


def build_remote_provider_onboarding(
    *,
    preset: str,
    provider_name: str | None = None,
    secret_mode: SecretMode = "env",
    api_key_env: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    policy: Path | None = None,
) -> dict[str, Any]:
    provider_preset = get_preset(preset)
    if not provider_preset.remote:
        raise ConfigError(f"provider onboarding is intended for remote presets; {preset} is local")
    if secret_mode not in {"env", "keyring"}:
        raise ConfigError("secret_mode must be env or keyring")

    name = provider_name or provider_preset.name
    resolved_base_url = base_url or provider_preset.base_url
    resolved_env = api_key_env or provider_preset.api_key_env or f"{_env_slug(name)}_API_KEY"
    model_arg = model or "<model-id>"
    policy_arg = str(policy) if policy is not None else "agentblaster.policy.yaml"

    provider_command = [
        "agentblaster",
        "providers",
        "add-preset",
        "--preset",
        preset,
        "--name",
        name,
        "--base-url",
        resolved_base_url,
    ]
    if secret_mode == "env":
        provider_command.extend(["--api-key-env", resolved_env])

    auth_commands: list[list[str]] = []
    secret_ref_display = f"env:{resolved_env}"
    if secret_mode == "env":
        auth_commands.append(["export", f"{resolved_env}=<redacted-api-key>"])
    else:
        secret_ref_display = f"keyring:{name}:api_key"
        auth_commands.append(["agentblaster", "providers", "auth", "set", "--provider", name, "--api-key-stdin"])

    cost_command = [
        "agentblaster",
        "providers",
        "cost",
        "set",
        "--provider",
        name,
        "--input-usd-per-1m-tokens",
        "<input-price>",
        "--output-usd-per-1m-tokens",
        "<output-price>",
    ]
    rate_limit_command = [
        "agentblaster",
        "providers",
        "rate-limits",
        "set",
        "--provider",
        name,
        "--max-concurrency",
        "<safe-concurrency>",
        "--requests-per-minute",
        "<safe-rpm>",
    ]
    audit_command = ["agentblaster", "providers", "audit", "--policy", policy_arg, "--output-json", f"reports/{name}-provider-audit.json"]
    readiness_command = [
        "agentblaster",
        "providers",
        "readiness",
        "--provider",
        name,
        "--suite",
        "smoke",
        "--model",
        model_arg,
        "--policy",
        policy_arg,
        "--output-json",
        f"reports/{name}-readiness.json",
    ]
    contract_plan_command = [
        "agentblaster",
        "providers",
        "contract-check",
        "--provider",
        name,
        "--model",
        model_arg,
        "--output-json",
        f"reports/{name}-contract-plan.json",
    ]
    smoke_command = [
        "agentblaster",
        "run",
        "--suite",
        "smoke",
        "--engine",
        name,
        "--model",
        model_arg,
        "--no-raw-traces",
    ]

    return {
        "schema_version": "agentblaster.remote-provider-onboarding.v1",
        "provider": {
            "name": name,
            "preset": preset,
            "contract": provider_preset.contract.value,
            "base_url": resolved_base_url,
            "remote": True,
            "secret_mode": secret_mode,
            "secret_ref": secret_ref_display,
            "model": model_arg,
        },
        "commands": {
            "secret_preparation": auth_commands,
            "provider_add": provider_command,
            "auth_status": ["agentblaster", "providers", "auth", "status", "--provider", name],
            "auth_test": ["agentblaster", "providers", "auth", "test", "--provider", name],
            "cost_model": cost_command,
            "rate_limits": rate_limit_command,
            "provider_audit": audit_command,
            "readiness": readiness_command,
            "contract_check_plan": contract_plan_command,
            "smoke_run": smoke_command,
        },
        "enterprise_controls": [
            "require_api_key_for_remote_providers: true",
            "allow_remote_providers must be explicitly enabled for approved remote hosts",
            "allowed_secret_ref_kinds should include only approved backends",
            "cost model and rate limits should be configured before non-smoke remote runs",
            "raw traces should remain off or redacted for remote providers",
            "TLS verification should remain enabled unless an approved policy exception exists",
        ],
        "safety": {
            "executes_commands": False,
            "stores_secrets": False,
            "contacts_provider": False,
            "prints_raw_secret": False,
            "writes_provider_config": False,
        },
        "notes": [
            "This onboarding plan is static and redaction-safe.",
            "The API key value must be supplied by the operator through the selected secret backend.",
            "Use readiness and audit artifacts before adding the provider to a benchmark matrix.",
        ],
    }


def remote_provider_onboarding_json(plan: dict[str, Any]) -> str:
    return json.dumps(plan, indent=2, sort_keys=True) + "\n"


def format_remote_provider_onboarding(plan: dict[str, Any]) -> str:
    provider = plan["provider"]
    commands = plan["commands"]
    lines = [
        "# AgentBlaster Remote Provider Onboarding",
        "",
        f"Provider: `{provider['name']}`",
        f"Preset: `{provider['preset']}`",
        f"Contract: `{provider['contract']}`",
        f"Base URL: `{provider['base_url']}`",
        f"Secret reference: `{provider['secret_ref']}`",
        "",
        "## Commands",
        "",
    ]
    for label, command in commands.items():
        lines.append(f"### {label.replace('_', ' ').title()}")
        lines.append("")
        lines.append("```bash")
        if command and isinstance(command[0], list):
            lines.extend(_shell(item) for item in command)
        else:
            lines.append(_shell(command))
        lines.append("```")
        lines.append("")
    lines.extend(
        [
            "## Enterprise Controls",
            "",
            *[f"- {item}" for item in plan["enterprise_controls"]],
            "",
            "## Safety",
            "",
            *[f"- {key}: `{str(value).lower()}`" for key, value in plan["safety"].items()],
            "",
        ]
    )
    return "\n".join(lines)


def write_remote_provider_onboarding(plan: dict[str, Any], output: Path, *, markdown: bool = False) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(format_remote_provider_onboarding(plan) if markdown else remote_provider_onboarding_json(plan), encoding="utf-8")
    return output


def _shell(command: list[str]) -> str:
    return shlex.join(command)


def _env_slug(value: str) -> str:
    return "".join(character.upper() if character.isalnum() else "_" for character in value).strip("_")
