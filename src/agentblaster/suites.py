from __future__ import annotations

from agentblaster.errors import ConfigError
from agentblaster.models import BenchmarkCase, SuiteDefinition


SMOKE_SUITE = SuiteDefinition(
    name="smoke",
    description="Minimal provider contract smoke test for chat completion.",
    cases=[
        BenchmarkCase(
            id="protocol-smoke-chat",
            title="Chat completion returns expected text",
            prompt="Reply with exactly: agentblaster-ok",
            expected_substring="agentblaster-ok",
            max_tokens=16,
            tags=["protocol", "chat"],
        )
    ],
)

BUILTIN_SUITES: dict[str, SuiteDefinition] = {SMOKE_SUITE.name: SMOKE_SUITE}


def get_builtin_suite(name: str) -> SuiteDefinition:
    try:
        return BUILTIN_SUITES[name]
    except KeyError as exc:
        available = ", ".join(sorted(BUILTIN_SUITES))
        raise ConfigError(f"unknown suite: {name}; available suites: {available}") from exc
