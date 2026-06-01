from __future__ import annotations

import pytest

from agentblaster.errors import ConfigError
from agentblaster.skills import available_skill_packs, skill_pack_text, skill_prefix


def test_available_skill_packs_are_stable() -> None:
    assert available_skill_packs() == [
        "agent-planning",
        "large-prefix-diagnostic",
        "repo-triage",
        "safe-tool-replay",
    ]


def test_skill_prefix_combines_deterministic_skill_text() -> None:
    prefix = skill_prefix(["repo-triage", "safe-tool-replay"])

    assert prefix.startswith("# AgentBlaster skill instructions")
    assert "# Skill: repo-triage" in prefix
    assert "# Skill: safe-tool-replay" in prefix
    assert "Do not request host filesystem" in prefix


def test_large_prefix_diagnostic_skill_creates_prefill_pressure() -> None:
    text = skill_pack_text("large-prefix-diagnostic")

    assert "Prefix diagnostic rule 01" in text
    assert "Prefix diagnostic rule 32" in text


def test_unknown_skill_pack_is_rejected() -> None:
    with pytest.raises(ConfigError, match="unknown skill pack"):
        skill_pack_text("host-control")
