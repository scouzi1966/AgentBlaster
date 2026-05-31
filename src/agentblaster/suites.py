from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

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


def load_suite_file(path: Path) -> SuiteDefinition:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"invalid suite file at {path}: {exc}") from exc

    try:
        return SuiteDefinition.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"invalid suite definition at {path}: {exc}") from exc


def validate_case_or_suite_file(path: Path) -> str:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"invalid YAML at {path}: {exc}") from exc

    if isinstance(data, dict) and "cases" in data:
        try:
            suite = SuiteDefinition.model_validate(data)
        except ValidationError as exc:
            raise ConfigError(f"invalid suite definition at {path}: {exc}") from exc
        return f"valid suite {suite.name} with {len(suite.cases)} case(s)"

    try:
        case = BenchmarkCase.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"invalid benchmark case at {path}: {exc}") from exc
    return f"valid case {case.id}"
