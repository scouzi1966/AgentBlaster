from __future__ import annotations

import os
from typing import Protocol

from agentblaster.errors import SecretError
from agentblaster.models import SecretRef

KEYRING_SERVICE_NAME = "AgentBlaster"


class SecretStore(Protocol):
    def get(self, ref: SecretRef) -> str | None:
        ...

    def set(self, ref: SecretRef, value: str) -> None:
        ...

    def delete(self, ref: SecretRef) -> None:
        ...


class EnvironmentSecretStore:
    def get(self, ref: SecretRef) -> str | None:
        if ref.kind != "env":
            return None
        return os.environ.get(ref.name)

    def set(self, ref: SecretRef, value: str) -> None:
        raise SecretError("environment secrets are read-only; set the variable in your shell or CI")

    def delete(self, ref: SecretRef) -> None:
        raise SecretError("environment secrets cannot be deleted by AgentBlaster; unset the variable in your shell or CI")


class OptionalKeyringSecretStore:
    def __init__(self, service_name: str = KEYRING_SERVICE_NAME) -> None:
        self.service_name = service_name

    def _keyring(self):
        try:
            import keyring  # type: ignore[import-not-found]
        except Exception as exc:  # pragma: no cover - exercised through unit behavior
            raise SecretError(
                "keyring support is not installed; install agentblaster[secrets] or use an env secret"
            ) from exc
        return keyring

    def get(self, ref: SecretRef) -> str | None:
        if ref.kind != "keyring":
            return None
        return self._keyring().get_password(self.service_name, ref.name)

    def set(self, ref: SecretRef, value: str) -> None:
        if ref.kind != "keyring":
            raise SecretError("keyring store can only write keyring secrets")
        self._keyring().set_password(self.service_name, ref.name, value)

    def delete(self, ref: SecretRef) -> None:
        if ref.kind != "keyring":
            raise SecretError("keyring store can only delete keyring secrets")
        keyring = self._keyring()
        existing = keyring.get_password(self.service_name, ref.name)
        if existing is None:
            return
        try:
            keyring.delete_password(self.service_name, ref.name)
        except AttributeError as exc:
            raise SecretError("keyring backend does not support secret deletion") from exc


class SecretResolver:
    def __init__(self, stores: list[SecretStore] | None = None) -> None:
        self.stores = stores or [EnvironmentSecretStore(), OptionalKeyringSecretStore()]

    def resolve(self, ref: SecretRef | None) -> str | None:
        if ref is None:
            return None
        for store in self.stores:
            try:
                value = store.get(ref)
            except SecretError:
                continue
            if value:
                return value
        return None

    def set(self, ref: SecretRef, value: str) -> None:
        if not value:
            raise SecretError("refusing to store an empty secret")
        for store in self.stores:
            try:
                store.set(ref, value)
                return
            except SecretError:
                continue
        raise SecretError(f"no writable secret store is available for {ref.display()}")

    def delete(self, ref: SecretRef) -> None:
        for store in self.stores:
            try:
                store.delete(ref)
                return
            except SecretError:
                continue
        raise SecretError(f"no deletable secret store is available for {ref.display()}")
