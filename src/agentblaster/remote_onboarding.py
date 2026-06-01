from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any, Literal

from agentblaster.errors import ConfigError
from agentblaster.presets import get_preset


SecretMode = Literal["env", "keyring", "dotenv"]


def build_remote_provider_onboarding(
    *,
    preset: str,
    provider_name: str | None = None,
    secret_mode: SecretMode = "env",
    api_key_env: str | None = None,
    dotenv_file: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    policy: Path | None = None,
) -> dict[str, Any]:
    provider_preset = get_preset(preset)
    if not provider_preset.remote:
        raise ConfigError(f"provider onboarding is intended for remote presets; {preset} is local")
    if secret_mode not in {"env", "keyring", "dotenv"}:
        raise ConfigError("secret_mode must be env, keyring, or dotenv")

    name = provider_name or provider_preset.name
    resolved_base_url = base_url or provider_preset.base_url
    resolved_env = api_key_env or provider_preset.api_key_env or f"{_env_slug(name)}_API_KEY"
    resolved_dotenv_file = dotenv_file or f".agentblaster.{_env_slug(name).lower()}.env"
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
    elif secret_mode == "keyring":
        secret_ref_display = f"keyring:{name}:api_key"
        auth_commands.append(
            [
                "agentblaster",
                "providers",
                "auth",
                "set",
                "--provider",
                name,
                "--api-key-stdin",
                "--policy",
                policy_arg,
            ]
        )
    else:
        secret_ref_display = f"dotenv:{resolved_env}@<redacted-path>"
        auth_commands.append(
            [
                "agentblaster",
                "providers",
                "auth",
                "set",
                "--provider",
                name,
                "--api-key-dotenv-file",
                resolved_dotenv_file,
                "--dotenv-var",
                resolved_env,
                "--allow-plaintext-secret-file",
                "--policy",
                policy_arg,
            ]
        )

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
        "--policy",
        policy_arg,
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
            "secret_ref_path_redacted": secret_mode == "dotenv",
            "model": model_arg,
        },
        "secret_backend": {
            "mode": secret_mode,
            "api_key_value_in_artifact": False,
            "provider_config_stores_reference_only": True,
            "environment_reference_portable": secret_mode == "env",
            "keyring_optional": True,
            "keyring_requires_optional_dependency": secret_mode == "keyring",
            "keyring_platform_note": "Uses Python keyring when installed; on macOS this normally maps to Apple Keychain, while Linux/Windows depend on the configured OS backend.",
            "plaintext_dotenv_fallback": secret_mode == "dotenv",
            "plaintext_dotenv_allowed_for_corporate": False,
            "prewrite_policy_guard": secret_mode in {"keyring", "dotenv"},
            "operator_secret_delivery": _operator_secret_delivery(secret_mode, resolved_env),
        },
        "policy_prerequisites": {
            "allow_remote_providers": True,
            "require_api_key_for_remote_providers": True,
            "allowed_secret_ref_kind": secret_mode,
            "allowed_base_url_host": _host_placeholder(resolved_base_url),
            "require_cost_model_for_remote_providers": True,
            "require_rate_limits_for_remote_providers": True,
            "allow_full_raw_traces": False,
            "tls_verify_required": True,
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
            "Keyring and dotenv auth setup commands include --policy so writable secret storage is blocked before persistence when enterprise policy disallows the backend or reference.",
            "Use readiness and audit artifacts before adding the provider to a benchmark matrix.",
            "Do not paste raw API keys into provider add commands, provider config files, policies, benchmark matrices, or reports.",
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
        "## Secret Backend",
        "",
        *[f"- {key}: `{str(value).lower()}`" for key, value in plan["secret_backend"].items() if isinstance(value, bool)],
        f"- operator_secret_delivery: `{plan['secret_backend']['operator_secret_delivery']}`",
        f"- keyring_platform_note: {plan['secret_backend']['keyring_platform_note']}",
        "",
        "## Policy Prerequisites",
        "",
        *[f"- {key}: `{value}`" for key, value in plan["policy_prerequisites"].items()],
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


def _operator_secret_delivery(secret_mode: str, env_name: str) -> str:
    if secret_mode == "env":
        return f"set {env_name} in the shell, CI secret manager, or enterprise secret manager before dispatch"
    if secret_mode == "keyring":
        return "pipe the API key on stdin to providers auth set; the key is not accepted as a CLI argument"
    return "pipe the API key on stdin to providers auth set for explicit local plaintext dotenv fallback"


def _host_placeholder(base_url: str) -> str:
    host = base_url.split("//", 1)[-1].split("/", 1)[0].split("@")[-1].split(":", 1)[0]
    return host or "<approved-host>"
