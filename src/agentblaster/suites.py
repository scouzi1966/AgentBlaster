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

STRUCTURED_SUITE = SuiteDefinition(
    name="structured",
    description="JSON structured-output correctness smoke tests.",
    cases=[
        BenchmarkCase(
            id="structured-json-object",
            title="JSON object with expected status field",
            system_prompt="Return only valid JSON.",
            prompt='Return exactly this JSON object: {"status":"agentblaster-ok","count":1}',
            expected_json_fields={"status": "agentblaster-ok", "count": 1},
            response_format={"type": "json_object"},
            max_tokens=64,
            tags=["structured", "json"],
        )
    ],
)

TOOLCALL_SUITE = SuiteDefinition(
    name="toolcall",
    description="Tool-call envelope correctness smoke tests.",
    cases=[
        BenchmarkCase(
            id="toolcall-required-ping",
            title="Required ping tool call",
            prompt="Use the ping_agentblaster tool with target set to agentblaster-ok.",
            expected_tool_name="ping_agentblaster",
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "ping_agentblaster",
                        "description": "Ping the AgentBlaster benchmark harness.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "target": {"type": "string", "description": "Ping target."},
                            },
                            "required": ["target"],
                            "additionalProperties": False,
                        },
                    },
                }
            ],
            tool_choice={"type": "function", "function": {"name": "ping_agentblaster"}},
            max_tokens=64,
            tags=["toolcall", "required"],
        )
    ],
)

PREFILL_SUITE = SuiteDefinition(
    name="prefill",
    description="Repeated-prefix prompt smoke tests for prefill/cache diagnostics.",
    cases=[
        BenchmarkCase(
            id="prefill-repeated-system-context",
            title="Large repeated context returns sentinel",
            system_prompt="You are benchmarking repeated prefix handling. Keep answers short.",
            prompt=(
                ("AgentBlaster repeated prefix block. " * 160)
                + "\nReply with exactly: agentblaster-ok"
            ),
            expected_substring="agentblaster-ok",
            max_tokens=16,
            tags=["prefill", "cache"],
        )
    ],
)

BUILTIN_SUITES: dict[str, SuiteDefinition] = {
    SMOKE_SUITE.name: SMOKE_SUITE,
    STRUCTURED_SUITE.name: STRUCTURED_SUITE,
    TOOLCALL_SUITE.name: TOOLCALL_SUITE,
    PREFILL_SUITE.name: PREFILL_SUITE,
}


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
