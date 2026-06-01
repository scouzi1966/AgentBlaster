from __future__ import annotations

import pytest

from agentblaster.errors import ConfigError
from agentblaster.lcp import available_lcp_profiles, lcp_profile_catalog, lcp_profile_text


def test_lcp_profiles_are_deterministic_and_host_safe() -> None:
    profiles = {item["name"]: item for item in lcp_profile_catalog()}

    assert {"fixture-lcp", "wide-lcp-context"} <= set(available_lcp_profiles())
    assert profiles["fixture-lcp"]["host_execution"] is False
    assert profiles["fixture-lcp"]["deterministic"] is True
    assert "agentblaster-lcp-ok" in lcp_profile_text("fixture-lcp")


def test_lcp_profile_rejects_unknown_names() -> None:
    with pytest.raises(ConfigError, match="unknown LCP profile"):
        lcp_profile_text("missing")
