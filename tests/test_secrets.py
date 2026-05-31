from __future__ import annotations

import pytest

from agentblaster.errors import SecretError
from agentblaster.models import SecretRef
from agentblaster.secrets import EnvironmentSecretStore, SecretResolver


def test_environment_secret_store_resolves_env_var(monkeypatch) -> None:
    monkeypatch.setenv("AGENTBLASTER_TEST_KEY", "secret-value")
    resolver = SecretResolver([EnvironmentSecretStore()])

    assert resolver.resolve(SecretRef(kind="env", name="AGENTBLASTER_TEST_KEY")) == "secret-value"


def test_environment_secret_store_is_read_only() -> None:
    resolver = SecretResolver([EnvironmentSecretStore()])

    with pytest.raises(SecretError):
        resolver.set(SecretRef(kind="env", name="AGENTBLASTER_TEST_KEY"), "secret-value")
