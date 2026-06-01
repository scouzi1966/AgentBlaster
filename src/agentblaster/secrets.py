from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any, Protocol

from agentblaster.errors import SecretError
from agentblaster.models import SecretRef

KEYRING_SERVICE_NAME = "AgentBlaster"
DOTENV_REF_SEPARATOR = "@"


def keyring_dependency_available() -> bool:
    """Return whether the optional Python keyring dependency can be imported.

    This is a static dependency check only. It does not inspect, unlock, list, or
    read any platform keyring entries.
    """

    return importlib.util.find_spec("keyring") is not None


def secret_backend_posture() -> dict[str, Any]:
    """Return a redaction-safe summary of supported credential backends."""

    return {
        "env_reference_supported": True,
        "env_reference_portable": True,
        "env_reference_writable_by_agentblaster": False,
        "keyring_optional": True,
        "keyring_dependency_available": keyring_dependency_available(),
        "keyring_service_name": KEYRING_SERVICE_NAME,
        "keyring_reads_values": False,
        "dotenv_plaintext_fallback_supported": True,
        "dotenv_plaintext_fallback_enterprise_default": False,
        "supported_secret_ref_kinds": ["env", "keyring", "dotenv"],
        "recommended_enterprise_backends": ["env", "keyring"],
    }


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


def dotenv_ref_name(variable: str, path: Path) -> str:
    """Build a dotenv secret reference name without embedding the secret value."""
    return f"{variable}{DOTENV_REF_SEPARATOR}{Path(path).expanduser()}"


def _parse_dotenv_ref_name(name: str) -> tuple[str, Path]:
    variable, separator, path_text = name.partition(DOTENV_REF_SEPARATOR)
    if separator != DOTENV_REF_SEPARATOR or not variable or not path_text:
        raise SecretError("dotenv secret references must use VAR@/path/to/.env")
    return variable, Path(path_text).expanduser()


def _dotenv_key_for_line(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped[7:].lstrip()
    if "=" not in stripped:
        return None
    key = stripped.split("=", 1)[0].strip()
    return key or None


def _decode_double_quoted_dotenv(value: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(value):
        character = value[index]
        if character != "\\" or index + 1 >= len(value):
            output.append(character)
            index += 1
            continue
        escaped = value[index + 1]
        output.append({"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}.get(escaped, escaped))
        index += 2
    return "".join(output)


def _dotenv_value_for_line(line: str) -> str | None:
    if "=" not in line:
        return None
    value = line.split("=", 1)[1].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        body = value[1:-1]
        if value[0] == '"':
            return _decode_double_quoted_dotenv(body)
        return body
    return value


def _encode_dotenv_value(value: str) -> str:
    if value == "" or any(character.isspace() or character in {'#', "'", '"', "\\", "$"} for character in value):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


class DotenvSecretStore:
    """Explicit development-only plaintext .env fallback.

    This backend exists for platforms or development environments where the OS keyring is unavailable.
    It is intentionally opt-in at the CLI/policy layer and provider configs still store only references.
    """

    def get(self, ref: SecretRef) -> str | None:
        if ref.kind != "dotenv":
            return None
        variable, path = _parse_dotenv_ref_name(ref.name)
        if not path.exists():
            return None
        value = None
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise SecretError("unable to read dotenv secret file <redacted-path>") from exc
        for line in lines:
            if _dotenv_key_for_line(line) == variable:
                value = _dotenv_value_for_line(line)
        return value

    def set(self, ref: SecretRef, value: str) -> None:
        if ref.kind != "dotenv":
            raise SecretError("dotenv store can only write dotenv secrets")
        if "\n" in value or "\r" in value:
            raise SecretError("dotenv secret values must be single-line to avoid .env injection")
        variable, path = _parse_dotenv_ref_name(ref.name)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            existing_lines = path.read_text(encoding="utf-8").splitlines(keepends=True) if path.exists() else []
        except OSError as exc:
            raise SecretError("unable to prepare dotenv secret file <redacted-path>") from exc
        new_line = f"{variable}={_encode_dotenv_value(value)}\n"
        replaced = False
        lines: list[str] = []
        for line in existing_lines:
            if _dotenv_key_for_line(line) == variable:
                if not replaced:
                    lines.append(new_line)
                    replaced = True
                continue
            lines.append(line)
        if not replaced:
            if lines and not lines[-1].endswith(("\n", "\r")):
                lines[-1] += "\n"
            lines.append(new_line)
        try:
            path.write_text("".join(lines), encoding="utf-8")
        except OSError as exc:
            raise SecretError("unable to write dotenv secret file <redacted-path>") from exc
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def delete(self, ref: SecretRef) -> None:
        if ref.kind != "dotenv":
            raise SecretError("dotenv store can only delete dotenv secrets")
        variable, path = _parse_dotenv_ref_name(ref.name)
        if not path.exists():
            return
        try:
            lines = [
                line
                for line in path.read_text(encoding="utf-8").splitlines(keepends=True)
                if _dotenv_key_for_line(line) != variable
            ]
            path.write_text("".join(lines), encoding="utf-8")
        except OSError as exc:
            raise SecretError("unable to update dotenv secret file <redacted-path>") from exc


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
        self.stores = stores or [EnvironmentSecretStore(), OptionalKeyringSecretStore(), DotenvSecretStore()]

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
        errors = []
        for store in self.stores:
            try:
                store.set(ref, value)
                return
            except SecretError as exc:
                errors.append(str(exc))
                continue
        detail = f": {'; '.join(errors)}" if errors else ""
        raise SecretError(f"no writable secret store is available for {ref.redacted_display()}{detail}")

    def delete(self, ref: SecretRef) -> None:
        errors = []
        for store in self.stores:
            try:
                store.delete(ref)
                return
            except SecretError as exc:
                errors.append(str(exc))
                continue
        detail = f": {'; '.join(errors)}" if errors else ""
        raise SecretError(f"no deletable secret store is available for {ref.redacted_display()}{detail}")
