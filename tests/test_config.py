from __future__ import annotations

from agentblaster.config import ProviderStore
from agentblaster.models import ApiContract, ProviderConfig, SecretRef


def test_provider_store_round_trips_provider(tmp_path) -> None:
    store = ProviderStore(tmp_path / "providers.json")
    provider = ProviderConfig(
        name="local-afm",
        contract=ApiContract.OPENAI,
        base_url="http://127.0.0.1:9999/v1",
        api_key_ref=SecretRef(kind="env", name="AFM_API_KEY"),
        remote=False,
    )

    store.upsert(provider)
    loaded = store.get("local-afm")

    assert loaded.name == provider.name
    assert loaded.contract == ApiContract.OPENAI
    assert loaded.api_key_ref is not None
    assert loaded.api_key_ref.name == "AFM_API_KEY"
    assert store.list()[0].name == "local-afm"
