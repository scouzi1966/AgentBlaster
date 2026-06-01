from __future__ import annotations

import pytest

from agentblaster.errors import SecretError
from agentblaster.models import SecretRef
from agentblaster.secrets import DotenvSecretStore, EnvironmentSecretStore, SecretResolver, dotenv_ref_name, secret_backend_posture


class _FailingSecretStore:
    def __init__(self, message: str) -> None:
        self.message = message

    def get(self, ref: SecretRef) -> str | None:
        raise SecretError(self.message)

    def set(self, ref: SecretRef, value: str) -> None:
        raise SecretError(self.message)

    def delete(self, ref: SecretRef) -> None:
        raise SecretError(self.message)


def test_environment_secret_store_resolves_env_reference(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTBLASTER_TEST_API_KEY", "test-key")
    ref = SecretRef(kind="env", name="AGENTBLASTER_TEST_API_KEY")

    assert SecretResolver(stores=[EnvironmentSecretStore()]).resolve(ref) == "test-key"


def test_dotenv_secret_store_sets_resolves_and_deletes_explicit_plaintext_fallback(tmp_path) -> None:
    dotenv_path = tmp_path / "dev.env"
    dotenv_path.write_text("# keep comments\nOTHER=value\n", encoding="utf-8")
    ref = SecretRef(kind="dotenv", name=dotenv_ref_name("AGENTBLASTER_TEST_API_KEY", dotenv_path))
    resolver = SecretResolver(stores=[DotenvSecretStore()])

    resolver.set(ref, 'secret with # marker and "quotes"')

    assert resolver.resolve(ref) == 'secret with # marker and "quotes"'
    dotenv_text = dotenv_path.read_text(encoding="utf-8")
    assert "# keep comments" in dotenv_text
    assert "OTHER=value" in dotenv_text
    assert "AGENTBLASTER_TEST_API_KEY=" in dotenv_text

    resolver.delete(ref)

    assert resolver.resolve(ref) is None
    assert "AGENTBLASTER_TEST_API_KEY=" not in dotenv_path.read_text(encoding="utf-8")


def test_dotenv_secret_store_rejects_multiline_values(tmp_path) -> None:
    ref = SecretRef(kind="dotenv", name=dotenv_ref_name("AGENTBLASTER_TEST_API_KEY", tmp_path / "dev.env"))
    resolver = SecretResolver(stores=[DotenvSecretStore()])

    with pytest.raises(SecretError, match="single-line"):
        resolver.set(ref, "secret\nINJECTED=value")


def test_secret_backend_posture_is_redaction_safe() -> None:
    posture = secret_backend_posture()

    assert posture["env_reference_portable"] is True
    assert posture["keyring_optional"] is True
    assert isinstance(posture["keyring_dependency_available"], bool)
    assert posture["keyring_reads_values"] is False
    assert posture["recommended_enterprise_backends"] == ["env", "keyring"]


def test_secret_resolver_reports_store_error_when_write_fails() -> None:
    ref = SecretRef(kind="keyring", name="openai:api_key")
    resolver = SecretResolver(stores=[_FailingSecretStore("keyring backend unavailable")])

    with pytest.raises(SecretError, match="keyring backend unavailable"):
        resolver.set(ref, "sk-test")


def test_secret_resolver_reports_store_error_when_delete_fails() -> None:
    ref = SecretRef(kind="keyring", name="openai:api_key")
    resolver = SecretResolver(stores=[_FailingSecretStore("keyring deletion unavailable")])

    with pytest.raises(SecretError, match="keyring deletion unavailable"):
        resolver.delete(ref)
