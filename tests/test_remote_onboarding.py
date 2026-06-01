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
    assert plan["commands"]["provider_add"][:5] == ["agentblaster", "providers", "add-preset", "--preset", "openai"]
    assert plan["commands"]["smoke_run"][-1] == "--no-raw-traces"
    assert plan["safety"]["stores_secrets"] is False
    assert "sk-" not in rendered
    assert "Bearer " not in rendered
    assert "Authorization" not in rendered


def test_remote_provider_onboarding_keyring_mode_uses_auth_set_plan() -> None:
    plan = build_remote_provider_onboarding(preset="anthropic", provider_name="anthropic-prod", secret_mode="keyring")
    markdown = format_remote_provider_onboarding(plan)

    assert plan["provider"]["secret_ref"] == "keyring:anthropic-prod:api_key"
    assert plan["commands"]["secret_preparation"] == [
        ["agentblaster", "providers", "auth", "set", "--provider", "anthropic-prod", "--api-key-stdin"]
    ]
    assert "Codex" not in markdown
    assert "agentblaster providers auth status --provider anthropic-prod" in markdown


def test_remote_provider_onboarding_rejects_local_presets() -> None:
    with pytest.raises(ConfigError, match="intended for remote presets"):
        build_remote_provider_onboarding(preset="afm")


def test_remote_provider_onboarding_json_is_machine_readable() -> None:
    plan = build_remote_provider_onboarding(preset="openai-responses", secret_mode="env")
    payload = json.loads(remote_provider_onboarding_json(plan))

    assert payload["provider"]["preset"] == "openai-responses"
    assert payload["commands"]["contract_check_plan"][0:3] == ["agentblaster", "providers", "contract-check"]


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
