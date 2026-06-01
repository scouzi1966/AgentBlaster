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

    with pytest.raises(SecretError):
        resolver.delete(SecretRef(kind="env", name="AGENTBLASTER_TEST_KEY"))


def test_secret_resolver_treats_optional_store_failures_as_missing() -> None:
    class MissingOptionalStore:
        def get(self, ref: SecretRef) -> str | None:
            raise SecretError("optional backend unavailable")

        def set(self, ref: SecretRef, value: str) -> None:
            raise SecretError("optional backend unavailable")

    resolver = SecretResolver([MissingOptionalStore()])

    assert resolver.resolve(SecretRef(kind="keyring", name="provider:api_key")) is None


def test_secret_resolver_can_delete_from_writable_store() -> None:
    class WritableStore:
        values = {"provider:api_key": "secret-value"}

        def get(self, ref: SecretRef) -> str | None:
            return self.values.get(ref.name)

        def set(self, ref: SecretRef, value: str) -> None:
            self.values[ref.name] = value

        def delete(self, ref: SecretRef) -> None:
            self.values.pop(ref.name, None)

    resolver = SecretResolver([WritableStore()])
    ref = SecretRef(kind="keyring", name="provider:api_key")

    resolver.delete(ref)

    assert resolver.resolve(ref) is None
