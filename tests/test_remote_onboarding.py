from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from agentblaster.cli import app
from agentblaster.errors import ConfigError
from agentblaster.remote_onboarding import (
    build_remote_provider_onboarding,
    format_remote_provider_onboarding,
    remote_provider_onboarding_json,
)


def test_remote_provider_onboarding_env_mode_is_redaction_safe() -> None:
    plan = build_remote_provider_onboarding(
        preset="openai",
        provider_name="openai-workspace",
        secret_mode="env",
        api_key_env="WORKSPACE_OPENAI_KEY",
        model="gpt-test",
    )
    rendered = json.dumps(plan)

    assert plan["schema_version"] == "agentblaster.remote-provider-onboarding.v1"
    assert plan["provider"]["secret_ref"] == "env:WORKSPACE_OPENAI_KEY"
    assert plan["provider"]["remote"] is True
    assert plan["secret_backend"] == {
        "mode": "env",
        "api_key_value_in_artifact": False,
        "provider_config_stores_reference_only": True,
        "environment_reference_portable": True,
        "keyring_optional": True,
        "keyring_requires_optional_dependency": False,
        "keyring_platform_note": "Uses Python keyring when installed; on macOS this normally maps to Apple Keychain, while Linux/Windows depend on the configured OS backend.",
        "plaintext_dotenv_fallback": False,
        "plaintext_dotenv_allowed_for_corporate": False,
        "prewrite_policy_guard": False,
        "operator_secret_delivery": "set WORKSPACE_OPENAI_KEY in the shell, CI secret manager, or enterprise secret manager before dispatch",
    }
    assert plan["policy_prerequisites"]["allow_remote_providers"] is True
    assert plan["policy_prerequisites"]["allowed_secret_ref_kind"] == "env"
    assert plan["policy_prerequisites"]["allowed_base_url_host"] == "api.openai.com"
    assert plan["commands"]["provider_add"][:5] == ["agentblaster", "providers", "add-preset", "--preset", "openai"]
    assert "--policy" in plan["commands"]["smoke_run"]
    assert "agentblaster.policy.yaml" in plan["commands"]["smoke_run"]
    assert plan["commands"]["smoke_run"][-1] == "--no-raw-traces"
    assert plan["safety"]["stores_secrets"] is False
    assert "sk-" not in rendered
    assert "Bearer " not in rendered
    assert "Authorization" not in rendered


def test_remote_provider_onboarding_keyring_mode_uses_auth_set_plan() -> None:
    plan = build_remote_provider_onboarding(preset="anthropic", provider_name="anthropic-prod", secret_mode="keyring")
    markdown = format_remote_provider_onboarding(plan)

    assert plan["provider"]["secret_ref"] == "keyring:anthropic-prod:api_key"
    assert plan["secret_backend"]["keyring_optional"] is True
    assert plan["secret_backend"]["keyring_requires_optional_dependency"] is True
    assert plan["secret_backend"]["prewrite_policy_guard"] is True
    assert plan["policy_prerequisites"]["allowed_secret_ref_kind"] == "keyring"
    assert plan["commands"]["secret_preparation"] == [
        [
            "agentblaster",
            "providers",
            "auth",
            "set",
            "--provider",
            "anthropic-prod",
            "--api-key-stdin",
            "--policy",
            "agentblaster.policy.yaml",
        ]
    ]
    assert "Codex" not in markdown
    assert "## Secret Backend" in markdown
    assert "keyring_platform_note: Uses Python keyring when installed" in markdown
    assert "agentblaster providers auth status --provider anthropic-prod" in markdown
    assert "agentblaster providers auth set --provider anthropic-prod --api-key-stdin --policy agentblaster.policy.yaml" in markdown


def test_remote_provider_onboarding_dotenv_mode_uses_explicit_plaintext_plan() -> None:
    plan = build_remote_provider_onboarding(
        preset="openai",
        provider_name="openai-dev",
        secret_mode="dotenv",
        api_key_env="WORKSPACE_OPENAI_KEY",
        dotenv_file=".agentblaster.dev.env",
    )
    markdown = format_remote_provider_onboarding(plan)

    assert plan["provider"]["secret_ref"] == "dotenv:WORKSPACE_OPENAI_KEY@<redacted-path>"
    assert plan["provider"]["secret_ref_path_redacted"] is True
    assert plan["secret_backend"]["plaintext_dotenv_fallback"] is True
    assert plan["secret_backend"]["plaintext_dotenv_allowed_for_corporate"] is False
    assert plan["policy_prerequisites"]["allowed_secret_ref_kind"] == "dotenv"
    assert plan["commands"]["secret_preparation"] == [
        [
            "agentblaster",
            "providers",
            "auth",
            "set",
            "--provider",
            "openai-dev",
            "--api-key-dotenv-file",
            ".agentblaster.dev.env",
            "--dotenv-var",
            "WORKSPACE_OPENAI_KEY",
            "--allow-plaintext-secret-file",
            "--policy",
            "agentblaster.policy.yaml",
        ]
    ]
    assert ".agentblaster.dev.env" not in markdown.split("## Commands", 1)[0]
    assert "--allow-plaintext-secret-file" in markdown
    assert "--policy agentblaster.policy.yaml" in markdown
    assert "sk-" not in markdown


def test_remote_provider_onboarding_rejects_local_presets() -> None:
    with pytest.raises(ConfigError, match="intended for remote presets"):
        build_remote_provider_onboarding(preset="afm")


def test_remote_provider_onboarding_json_is_machine_readable() -> None:
    plan = build_remote_provider_onboarding(preset="openai-responses", secret_mode="env")
    payload = json.loads(remote_provider_onboarding_json(plan))

    assert payload["provider"]["preset"] == "openai-responses"
    assert payload["commands"]["contract_check_plan"][0:3] == ["agentblaster", "providers", "contract-check"]
    assert payload["commands"]["smoke_run"][-3:] == ["--policy", "agentblaster.policy.yaml", "--no-raw-traces"]


def test_cli_provider_onboarding_outputs_json() -> None:
    result = CliRunner().invoke(
        app,
        [
            "providers",
            "onboarding",
            "--preset",
            "openai",
            "--name",
            "openai-workspace",
            "--api-key-env",
            "WORKSPACE_OPENAI_KEY",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["provider"]["name"] == "openai-workspace"
    assert payload["provider"]["secret_ref"] == "env:WORKSPACE_OPENAI_KEY"
