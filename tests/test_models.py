from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentblaster.models import ApiContract, ProviderConfig, SecretRef


def test_provider_accepts_env_secret_reference() -> None:
    provider = ProviderConfig(
        name="openai",
        contract=ApiContract.OPENAI,
        base_url="https://api.openai.com/v1",
        api_key_ref=SecretRef(kind="env", name="OPENAI_API_KEY"),
        remote=True,
    )

    assert provider.api_key_ref is not None
    assert provider.api_key_ref.display() == "env:OPENAI_API_KEY"


def test_provider_rejects_raw_auth_header() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            name="bad",
            contract=ApiContract.OPENAI,
            base_url="https://example.com/v1",
            headers={"Authorization": "Bearer sk-testshouldnotbehere1234567890"},
        )
