from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from agentblaster.errors import ConfigError
from agentblaster.models import BenchmarkCase, SuiteDefinition, SuiteProvenance


BUILTIN_PROVENANCE = SuiteProvenance(
    origin="builtin",
    primary_source="AgentBlaster",
    license="MIT",
    risk_labels=["synthetic", "internal-regression"],
    notes=["Built-in deterministic smoke workload for provider and harness validation."],
)


SMOKE_SUITE = SuiteDefinition(
    name="smoke",
    description="Minimal provider contract smoke test for chat completion.",
    provenance=BUILTIN_PROVENANCE,
    cases=[
        BenchmarkCase(
            id="protocol-smoke-chat",
            title="Chat completion returns expected text",
            scenario="protocol smoke",
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
    provenance=BUILTIN_PROVENANCE,
    cases=[
        BenchmarkCase(
            id="structured-json-object",
            title="JSON object with expected status field",
            scenario="structured output",
            system_prompt="Return only valid JSON.",
            prompt='Return exactly this JSON object: {"status":"agentblaster-ok","count":1}',
            expected_json_fields={"status": "agentblaster-ok", "count": 1},
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "agentblaster_status",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "required": ["status", "count"],
                        "additionalProperties": False,
                        "properties": {
                            "status": {"type": "string", "const": "agentblaster-ok"},
                            "count": {"type": "integer"},
                        },
                    },
                },
            },
            max_tokens=64,
            tags=["structured", "json"],
        )
    ],
)

TOOLCALL_SUITE = SuiteDefinition(
    name="toolcall",
    description="Tool-call envelope correctness smoke tests.",
    provenance=BUILTIN_PROVENANCE,
    cases=[
        BenchmarkCase(
            id="toolcall-required-ping",
            title="Required ping tool call",
            scenario="tool calling",
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
    provenance=BUILTIN_PROVENANCE,
    cases=[
        BenchmarkCase(
            id="prefill-repeated-system-context",
            title="Large repeated context returns sentinel",
            scenario="prefill cache",
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

TOOLSIM_SUITE = SuiteDefinition(
    name="toolsim",
    description="Safe deterministic tool simulator smoke tests for agentic harness workflows.",
    provenance=BUILTIN_PROVENANCE,
    cases=[
        BenchmarkCase(
            id="toolsim-search-docs",
            title="Required deterministic docs search tool",
            scenario="tool simulation",
            prompt="Use search_docs with query set to AgentBlaster PRD.",
            expected_tool_name="search_docs",
            expected_tool_result_substring="local agentic inference engines",
            simulated_tools=["search_docs"],
            tool_choice={"type": "function", "function": {"name": "search_docs"}},
            max_tokens=64,
            tags=["toolcall", "toolsim", "safe-harness"],
        )
    ],
)

TRACE_REPLAY_SUITE = SuiteDefinition(
    name="trace-replay",
    description="Multi-turn trace replay smoke test with prior assistant tool use and deterministic tool result context.",
    provenance=BUILTIN_PROVENANCE,
    cases=[
        BenchmarkCase(
            id="trace-replay-tool-result-summary",
            title="Answer from replayed deterministic tool result",
            scenario="trace replay",
            prompt="Replay a prior tool-use conversation and answer from the tool result.",
            messages=[
                {
                    "role": "system",
                    "content": "You are replaying a deterministic AgentBlaster trace. Answer from the provided tool result only.",
                },
                {
                    "role": "user",
                    "content": "Read /repo/src/app.py and report the status string.",
                },
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_read_app",
                            "type": "function",
                            "function": {
                                "name": "read_file_fixture",
                                "arguments": '{"path":"/repo/src/app.py"}',
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "name": "read_file_fixture",
                    "tool_call_id": "call_read_app",
                    "content": "{\"path\":\"/repo/src/app.py\",\"content\":\"def status():\\n    return 'agentblaster-ok'\\n\"}",
                },
                {
                    "role": "user",
                    "content": "What exact string does status() return? Reply with only that string.",
                },
            ],
            expected_substring="agentblaster-ok",
            max_tokens=32,
            tags=["trace-replay", "tool-result", "agentic"],
        )
    ],
)

CACHE_CONTROL_SUITE = SuiteDefinition(
    name="cache-control",
    description="Anthropic-style cache-control and static-prefix diagnostics for repeated agent prompts.",
    provenance=BUILTIN_PROVENANCE,
    cases=[
        BenchmarkCase(
            id="cache-control-static-system-prefix",
            title="Static system prefix with cache breakpoint metadata",
            scenario="prompt cache",
            system_prompt=(
                "You are benchmarking repeated static agent context. "
                "Preserve the policy block, tool contract, and final answer requirement exactly. "
                + ("AgentBlaster cache diagnostic policy. " * 120)
            ),
            cache_control={"type": "ephemeral"},
            prompt="Reply with exactly: agentblaster-ok",
            expected_substring="agentblaster-ok",
            metrics=["cached_input_tokens", "cache_write_tokens", "cache_hit_ratio", "ttft_ms", "tokens_per_second_prefill"],
            max_tokens=24,
            tags=["cache", "prefill", "anthropic", "static-prefix"],
        ),
        BenchmarkCase(
            id="cache-control-tool-catalog-prefix",
            title="Tool catalog prefix with cache breakpoint metadata",
            scenario="prompt cache",
            system_prompt="Use the static tool catalog and call search_docs only when required.",
            cache_control={"type": "ephemeral"},
            prompt="Use search_docs with query set to AgentBlaster PRD.",
            expected_tool_name="search_docs",
            expected_tool_result_substring="local agentic inference engines",
            simulated_tools=["search_docs"],
            tool_choice={"type": "function", "function": {"name": "search_docs"}},
            metrics=["cached_input_tokens", "cache_write_tokens", "cache_hit_ratio", "tool_calls_valid"],
            max_tokens=80,
            tags=["cache", "toolcall", "prefill", "static-prefix"],
        ),
    ],
)


LCP_CONTEXT_SUITE = SuiteDefinition(
    name="lcp-context",
    description="Fixture-only local context protocol style workflow diagnostics.",
    provenance=BUILTIN_PROVENANCE.model_copy(
        update={
            "notes": [
                "Built-in deterministic LCP-style fixture for context attachment and redaction-boundary validation."
            ]
        }
    ),
    cases=[
        BenchmarkCase(
            id="lcp-fixture-context-sentinel",
            title="Answer from scoped LCP fixture context",
            scenario="lcp context",
            lcp_profile="fixture-lcp",
            prompt="Using only the attached LCP fixture context, what exact project status sentinel is present?",
            expected_substring="agentblaster-lcp-ok",
            metrics=["ttft_ms", "tokens_per_second_prefill", "cached_input_tokens", "cache_hit_ratio"],
            max_tokens=32,
            tags=["lcp", "context", "emerging", "fixture"],
        )
    ],
)

BUILTIN_SUITES: dict[str, SuiteDefinition] = {
    SMOKE_SUITE.name: SMOKE_SUITE,
    STRUCTURED_SUITE.name: STRUCTURED_SUITE,
    TOOLCALL_SUITE.name: TOOLCALL_SUITE,
    PREFILL_SUITE.name: PREFILL_SUITE,
    TOOLSIM_SUITE.name: TOOLSIM_SUITE,
    TRACE_REPLAY_SUITE.name: TRACE_REPLAY_SUITE,
    CACHE_CONTROL_SUITE.name: CACHE_CONTROL_SUITE,
    LCP_CONTEXT_SUITE.name: LCP_CONTEXT_SUITE,
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
        suite = SuiteDefinition.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"invalid suite definition at {path}: {exc}") from exc
    if suite.provenance.origin == "unknown":
        suite = suite.model_copy(
            update={
                "provenance": suite.provenance.model_copy(
                    update={
                        "origin": "user_file",
                        "primary_source": "user-provided suite file",
                        "notes": [*suite.provenance.notes, "Loaded from a user-provided suite file."],
                    }
                )
            },
            deep=True,
        )
    return suite


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
