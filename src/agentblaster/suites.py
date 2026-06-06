from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from agentblaster.constants import SMOKE_SENTINEL, SMOKE_SENTINEL_MAX_TOKENS, SMOKE_SENTINEL_PROMPT, SMOKE_SENTINEL_SYSTEM_PROMPT
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
            system_prompt=SMOKE_SENTINEL_SYSTEM_PROMPT,
            prompt=SMOKE_SENTINEL_PROMPT,
            expected_substring=SMOKE_SENTINEL,
            max_tokens=SMOKE_SENTINEL_MAX_TOKENS,
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

PREFILL_STATIC_SYSTEM_PROMPT = (
    "You are benchmarking repeated local-agent system prompt handling. "
    "Honor the same static policy, planning rubric, tool-boundary instructions, and final-answer rule across each case. "
    + ("AgentBlaster static agent instruction block for prefill diagnostics. " * 96)
)

PREFILL_METRICS = [
    "ttft_ms",
    "prompt_eval_ms",
    "tokens_per_second_prefill",
    "cached_input_tokens",
    "cache_write_tokens",
    "cache_hit_ratio",
]

PREFILL_SUITE = SuiteDefinition(
    name="prefill",
    description="Repeated-prefix and shared-system-prompt smoke tests for prefill/cache diagnostics.",
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
            metrics=PREFILL_METRICS,
            tags=["prefill", "cache"],
        ),
        BenchmarkCase(
            id="prefill-static-prefix-warmup",
            title="Shared static system prompt warmup",
            scenario="prefill shared prefix",
            system_prompt=PREFILL_STATIC_SYSTEM_PROMPT,
            prompt="Warmup worker: reply with exactly agentblaster-prefill-warmup-ok.",
            expected_substring="agentblaster-prefill-warmup-ok",
            metrics=PREFILL_METRICS,
            max_tokens=24,
            tags=["prefill", "cache", "static-prefix", "repeated-system-prompt", "warmup"],
        ),
        BenchmarkCase(
            id="prefill-static-prefix-replay",
            title="Shared static system prompt replay",
            scenario="prefill shared prefix",
            system_prompt=PREFILL_STATIC_SYSTEM_PROMPT,
            prompt="Replay worker: reply with exactly agentblaster-prefill-replay-ok.",
            expected_substring="agentblaster-prefill-replay-ok",
            metrics=PREFILL_METRICS,
            max_tokens=24,
            tags=["prefill", "cache", "static-prefix", "repeated-system-prompt", "replay"],
        ),
        BenchmarkCase(
            id="prefill-static-prefix-suffix-mutation",
            title="Shared static system prompt with suffix mutation",
            scenario="prefill shared prefix",
            system_prompt=PREFILL_STATIC_SYSTEM_PROMPT,
            prompt=(
                "Mutation worker: preserve the shared static prefix behavior, ignore unrelated suffix noise, "
                "and reply with exactly agentblaster-prefill-mutation-ok. Suffix marker: qwen-gemma-local-agentic."
            ),
            expected_substring="agentblaster-prefill-mutation-ok",
            metrics=PREFILL_METRICS,
            max_tokens=32,
            tags=["prefill", "cache", "static-prefix", "repeated-system-prompt", "suffix-mutation"],
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

AGENT_FANOUT_SUITE = SuiteDefinition(
    name="agent-fanout",
    description="Synthetic planner/worker/synthesizer fan-out workload for concurrent local-agent request bursts.",
    provenance=BUILTIN_PROVENANCE.model_copy(
        update={
            "notes": [
                "Built-in deterministic multi-subagent fan-out workload for queueing, request isolation, and shared prefix diagnostics."
            ]
        }
    ),
    cases=[
        BenchmarkCase(
            id="fanout-planner-outline",
            title="Planner subagent produces sentinel",
            scenario="agent fan-out",
            system_prompt=(
                "You are one worker in a synthetic AgentBlaster fan-out benchmark. "
                "Keep responses short, deterministic, and independent from other workers."
            ),
            prompt="Planner worker: reply with exactly agentblaster-planner-ok.",
            expected_substring="agentblaster-planner-ok",
            metrics=["queue_ms", "rate_limit_wait_ms", "latency_ms", "ttft_ms"],
            max_tokens=32,
            tags=["agentic", "fanout", "planner", "concurrency"],
        ),
        BenchmarkCase(
            id="fanout-code-worker",
            title="Code worker produces sentinel",
            scenario="agent fan-out",
            system_prompt=(
                "You are one worker in a synthetic AgentBlaster fan-out benchmark. "
                "Keep responses short, deterministic, and independent from other workers."
            ),
            prompt="Code worker: reply with exactly agentblaster-code-worker-ok.",
            expected_substring="agentblaster-code-worker-ok",
            metrics=["queue_ms", "rate_limit_wait_ms", "latency_ms", "ttft_ms"],
            max_tokens=32,
            tags=["agentic", "fanout", "worker", "code", "concurrency"],
        ),
        BenchmarkCase(
            id="fanout-doc-worker",
            title="Docs worker produces sentinel",
            scenario="agent fan-out",
            system_prompt=(
                "You are one worker in a synthetic AgentBlaster fan-out benchmark. "
                "Keep responses short, deterministic, and independent from other workers."
            ),
            prompt="Docs worker: reply with exactly agentblaster-doc-worker-ok.",
            expected_substring="agentblaster-doc-worker-ok",
            metrics=["queue_ms", "rate_limit_wait_ms", "latency_ms", "ttft_ms"],
            max_tokens=32,
            tags=["agentic", "fanout", "worker", "docs", "concurrency"],
        ),
        BenchmarkCase(
            id="fanout-synthesizer",
            title="Synthesizer subagent produces sentinel",
            scenario="agent fan-out",
            system_prompt=(
                "You are one worker in a synthetic AgentBlaster fan-out benchmark. "
                "Keep responses short, deterministic, and independent from other workers."
            ),
            prompt="Synthesizer worker: reply with exactly agentblaster-synthesizer-ok.",
            expected_substring="agentblaster-synthesizer-ok",
            metrics=["queue_ms", "rate_limit_wait_ms", "latency_ms", "ttft_ms"],
            max_tokens=32,
            tags=["agentic", "fanout", "synthesizer", "concurrency"],
        ),
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
            tags=["cache-control", "cache", "prefill", "anthropic", "static-prefix"],
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
            tags=["cache-control", "cache", "toolcall", "prefill", "static-prefix"],
        ),
    ],
)


CANCELLATION_SUITE = SuiteDefinition(
    name="cancellation",
    description="Streaming cancellation and request-abort behavior smoke tests.",
    provenance=BUILTIN_PROVENANCE.model_copy(
        update={
            "notes": [
                "Built-in deterministic cancellation workload for stream abort, request lifecycle, and cancellation latency validation."
            ]
        }
    ),
    cases=[
        BenchmarkCase(
            id="cancellation-stream-abort",
            title="Streaming response is canceled by the harness",
            scenario="cancellation",
            prompt=(
                "Begin a streaming response with the marker agentblaster-cancel-ok, then continue "
                "with short numbered tokens until the benchmark harness cancels the stream. Do not stop voluntarily."
            ),
            streaming=True,
            cancel_after_ms=100,
            metrics=["canceled", "cancellation_latency_ms", "ttft_ms", "latency_ms"],
            max_tokens=256,
            timeout_seconds=15.0,
            tags=["cancellation", "streaming", "request-lifecycle"],
        )
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


HARNESS_ENGINEERING_STATIC_PREFIX = (
    "You are executing an AgentBlaster emerging harness-engineering benchmark. "
    "Treat contract fuzzing, metamorphic prompt variants, cache replay, and judge-rubric checks as synthetic diagnostics. "
    + ("AgentBlaster harness-engineering static policy block. " * 80)
)

HARNESS_ENGINEERING_SUITE = SuiteDefinition(
    name="harness-engineering",
    description=(
        "First-class emerging harness-engineering workload covering contract fuzzing, metamorphic stability, "
        "cache replay, and deterministic judge-rubric discipline."
    ),
    provenance=BUILTIN_PROVENANCE.model_copy(
        update={
            "notes": [
                "Built-in deterministic emerging harness-engineering workload for benchmark-method research and release preflight."
            ]
        }
    ),
    cases=[
        BenchmarkCase(
            id="harness-contract-streaming-sentinel",
            title="Streaming contract fuzz sentinel",
            scenario="harness contract fuzz",
            prompt="Stream a concise response containing exactly this marker: agentblaster-harness-stream-ok",
            expected_substring="agentblaster-harness-stream-ok",
            streaming=True,
            metrics=["ttft_ms", "latency_ms", "tokens_per_second_decode"],
            max_tokens=48,
            tags=["harness", "contract-fuzz", "streaming", "emerging"],
        ),
        BenchmarkCase(
            id="harness-metamorphic-equivalent-wrapper",
            title="Metamorphic wrapper preserves answer",
            scenario="harness metamorphic",
            system_prompt="You are validating metamorphic prompt invariance. Keep the semantic result unchanged.",
            prompt=(
                "Two equivalent phrasings describe the same task. Ignore wrapper differences and reply with exactly "
                "agentblaster-metamorphic-ok."
            ),
            expected_substring="agentblaster-metamorphic-ok",
            metrics=["latency_ms", "ttft_ms"],
            max_tokens=32,
            tags=["harness", "metamorphic", "prompt-invariance", "emerging"],
        ),
        BenchmarkCase(
            id="harness-cache-replay-static-prefix",
            title="Cache replay static-prefix sentinel",
            scenario="harness cache replay",
            system_prompt=HARNESS_ENGINEERING_STATIC_PREFIX,
            cache_control={"type": "ephemeral"},
            prompt="Cache replay worker: reply with exactly agentblaster-harness-cache-ok.",
            expected_substring="agentblaster-harness-cache-ok",
            metrics=[
                "ttft_ms",
                "tokens_per_second_prefill",
                "cached_input_tokens",
                "cache_write_tokens",
                "cache_hit_ratio",
            ],
            max_tokens=32,
            tags=["harness", "cache-replay", "prefill", "static-prefix", "emerging"],
        ),
        BenchmarkCase(
            id="harness-judge-rubric-json",
            title="Deterministic judge-rubric JSON verdict",
            scenario="harness judge rubric",
            system_prompt="Return only valid JSON. Do not wrap the JSON in markdown.",
            prompt=(
                'Return exactly this JSON object: {"verdict":"pass","score":1,'
                '"marker":"agentblaster-judge-rubric-ok"}'
            ),
            expected_json_fields={
                "verdict": "pass",
                "score": 1,
                "marker": "agentblaster-judge-rubric-ok",
            },
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "agentblaster_judge_rubric",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "required": ["verdict", "score", "marker"],
                        "additionalProperties": False,
                        "properties": {
                            "verdict": {"type": "string", "const": "pass"},
                            "score": {"type": "integer", "const": 1},
                            "marker": {"type": "string", "const": "agentblaster-judge-rubric-ok"},
                        },
                    },
                },
            },
            metrics=["structured_output_valid", "judge_verdict_valid", "latency_ms"],
            max_tokens=80,
            tags=["harness", "judge-rubric", "model-judge", "structured", "emerging"],
        ),
    ],
)


def _agentic_loop_tool_schemas() -> list[dict[str, Any]]:
    return [
        _function_tool_schema(
            "route_agentblaster_task",
            "Select the deterministic route for an AgentBlaster agentic loop workload.",
            {
                "route_id": {"type": "string", "description": "Required route marker."},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            },
            ["route_id"],
        ),
        _function_tool_schema(
            "search_agentblaster_notes",
            "Search deterministic benchmark notes without host, network, or browser access.",
            {"query": {"type": "string"}},
            ["query"],
        ),
        _function_tool_schema(
            "fetch_agentblaster_context",
            "Fetch deterministic benchmark context without host filesystem access.",
            {"context_id": {"type": "string"}},
            ["context_id"],
        ),
        _function_tool_schema(
            "finalize_agentblaster_plan",
            "Finalize a deterministic benchmark plan summary.",
            {"summary": {"type": "string"}},
            ["summary"],
        ),
    ]


def _function_tool_schema(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str],
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


TOOL_PARSER_REPAIR_SUITE = SuiteDefinition(
    name="tool-parser-repair",
    description="Strict local-agent tool-parser repair workloads that reject raw JSON/XML/ReAct text as completed tool calls.",
    provenance=BUILTIN_PROVENANCE.model_copy(
        update={
            "notes": [
                "Built-in deterministic parser-repair workload for local engines that sometimes emit tool arguments as plain text instead of API-native tool envelopes."
            ]
        }
    ),
    cases=[
        BenchmarkCase(
            id="parser-required-api-envelope",
            title="Required tool must be API-native, not raw JSON",
            scenario="tool parser repair",
            system_prompt=(
                "When a tool is required, emit the provider API-native tool-call envelope. "
                "Raw JSON, XML, markdown, or ReAct text is not a completed tool call."
            ),
            prompt="Call search_docs with query set to AgentBlaster PRD. Do not describe the call as text.",
            expected_tool_name="search_docs",
            expected_tool_result_substring="local agentic inference engines",
            simulated_tools=["search_docs"],
            tools=[
                _function_tool_schema(
                    "search_docs",
                    "Search a deterministic in-memory documentation fixture.",
                    {"query": {"type": "string", "description": "Search query."}},
                    ["query"],
                )
            ],
            tool_choice={"type": "function", "function": {"name": "search_docs"}},
            metrics=[
                "tool_calls_valid",
                "invalid_tool_call_count",
                "tool_parser_repair_required",
                "latency_ms",
            ],
            max_tokens=80,
            tags=["tool-parser", "repair", "openclaw", "api-native", "local-model"],
        ),
        BenchmarkCase(
            id="parser-react-xml-boundary",
            title="ReAct/XML-style text is rejected as a tool call",
            scenario="tool parser repair",
            system_prompt=(
                "Use only API-native function/tool calls. Do not emit <tool_call>, Action:, JSON code fences, "
                "or prose that merely describes a call."
            ),
            prompt=(
                "Call route_agentblaster_task with route_id set to agentblaster-parser-repair-ok. "
                "A plain text answer such as Action: route_agentblaster_task is invalid."
            ),
            expected_tool_name="route_agentblaster_task",
            tools=_agentic_loop_tool_schemas(),
            tool_choice={"type": "function", "function": {"name": "route_agentblaster_task"}},
            metrics=[
                "tool_calls_valid",
                "invalid_tool_call_count",
                "tool_parser_repair_required",
                "tool_loop_stop_reason",
                "latency_ms",
            ],
            max_tokens=96,
            tags=["tool-parser", "repair", "react", "xml", "api-native", "local-model"],
        ),
    ],
)


AGENTIC_TOOL_LOOP_SUITE = SuiteDefinition(
    name="agentic-tool-loop",
    description="Bounded deterministic tool-loop workflows for MCP/LCP-heavy local-agent orchestration.",
    provenance=BUILTIN_PROVENANCE.model_copy(
        update={
            "notes": [
                "Built-in deterministic agentic loop workload for tool-result replay, MCP fixture calls, LCP context attachment, and max-tool-call stop-reason diagnostics."
            ]
        }
    ),
    cases=[
        BenchmarkCase(
            id="tool-loop-route-final",
            title="Fixture route tool loop reaches final answer",
            scenario="agentic tool loop",
            prompt=(
                "Use route_agentblaster_task with route_id set to agentblaster-route-loop-final. "
                "After the tool result, reply with exactly: agentblaster-route-ok."
            ),
            expected_tool_name="route_agentblaster_task",
            expected_substring="agentblaster-route-ok",
            expected_tool_result_substring="agentblaster-route-ok",
            tools=_agentic_loop_tool_schemas(),
            tool_choice="auto",
            max_tool_calls=2,
            metrics=[
                "tool_calls_valid",
                "tool_loop_rounds",
                "tool_loop_tool_call_count",
                "tool_loop_stop_reason",
                "latency_ms",
                "ttft_ms",
            ],
            max_tokens=96,
            tags=["agentic", "tool-loop", "tool-result-replay", "fixture"],
        ),
        BenchmarkCase(
            id="tool-loop-mcp-lcp-context",
            title="MCP fixture tool loop with LCP context attachment",
            scenario="agentic mcp lcp loop",
            lcp_profile="fixture-lcp",
            mcp_profile="fixture-mcp",
            prompt=(
                "Using only the attached LCP fixture context, call mcp_fixture_read_resource with uri "
                "fixture://mcp/resource/status. After the MCP fixture result, reply with exactly: agentblaster-mcp-ok."
            ),
            expected_tool_name="mcp_fixture_read_resource",
            expected_substring="agentblaster-mcp-ok",
            expected_tool_result_substring="agentblaster-mcp-ok",
            tool_choice="auto",
            max_tool_calls=2,
            metrics=[
                "tool_calls_valid",
                "tool_loop_rounds",
                "tool_loop_tool_call_count",
                "tool_loop_stop_reason",
                "tokens_per_second_prefill",
                "cached_input_tokens",
            ],
            max_tokens=96,
            tags=["agentic", "tool-loop", "mcp", "lcp", "fixture", "emerging"],
        ),
        BenchmarkCase(
            id="tool-loop-max-call-boundary",
            title="Bounded loop exposes max tool-call stop reason",
            scenario="agentic tool loop boundary",
            prompt=(
                "agentblaster-loop-boundary-repeat. Use route_agentblaster_task with route_id set to "
                "agentblaster-route-loop-boundary on every turn until the harness stops you. "
                "Do not provide a final answer before another tool call."
            ),
            expected_tool_name="route_agentblaster_task",
            expected_tool_result_substring="agentblaster-route-ok",
            tools=_agentic_loop_tool_schemas(),
            tool_choice={"type": "function", "function": {"name": "route_agentblaster_task"}},
            max_tool_calls=2,
            metrics=[
                "tool_calls_valid",
                "tool_loop_rounds",
                "tool_loop_tool_call_count",
                "tool_loop_stop_reason",
                "latency_ms",
                "ttft_ms",
            ],
            max_tokens=96,
            tags=["agentic", "tool-loop", "max-tool-calls", "fixture", "boundary"],
        ),
    ],
)


def _extend_suite(suite: SuiteDefinition, cases: list[BenchmarkCase]) -> SuiteDefinition:
    return suite.model_copy(update={"cases": [*suite.cases, *cases]}, deep=True)


def _marker_case(
    *,
    id: str,
    title: str,
    scenario: str,
    prompt: str,
    marker: str,
    tags: list[str],
    system_prompt: str | None = None,
    max_tokens: int = 48,
    metrics: list[str] | None = None,
) -> BenchmarkCase:
    return BenchmarkCase(
        id=id,
        title=title,
        scenario=scenario,
        system_prompt=system_prompt,
        prompt=f"{prompt} Reply with exactly: {marker}",
        expected_substring=marker,
        max_tokens=max_tokens,
        metrics=metrics or [],
        tags=[*tags, "afm", "local-agent"],
    )


def _json_schema_case(id: str, title: str, prompt: str, marker: str, action: str) -> BenchmarkCase:
    extra_tags = ["harness", "emerging", "judge-rubric", "model-judge"] if id.startswith("harness-") else []
    metrics = ["structured_output_valid", "judge_verdict_valid", "latency_ms"] if id.startswith("harness-") else []
    return BenchmarkCase(
        id=id,
        title=title,
        scenario="structured output",
        system_prompt="Return only valid JSON. Do not include markdown, prose, or comments.",
        prompt=(
            f'{prompt} Return exactly this JSON object: '
            f'{{"marker":"{marker}","action":"{action}","ok":true}}'
        ),
        expected_json_fields={"marker": marker, "action": action, "ok": True},
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": id.replace("-", "_"),
                "strict": True,
                "schema": {
                    "type": "object",
                    "required": ["marker", "action", "ok"],
                    "additionalProperties": False,
                    "properties": {
                        "marker": {"type": "string", "const": marker},
                        "action": {"type": "string", "const": action},
                        "ok": {"type": "boolean", "const": True},
                    },
                },
            },
        },
        max_tokens=96,
        metrics=metrics,
        tags=["structured", "json", "afm", "local-agent", action, *extra_tags],
    )


def _single_tool_case(
    *,
    id: str,
    title: str,
    tool_name: str,
    marker: str,
    task: str,
    tags: list[str],
) -> BenchmarkCase:
    return BenchmarkCase(
        id=id,
        title=title,
        scenario="tool calling",
        prompt=f"Call {tool_name} with marker set to {marker} and task set to {task}. Do not answer in prose.",
        expected_tool_name=tool_name,
        tools=[
            _function_tool_schema(
                tool_name,
                f"Deterministic local-agent fixture tool for {task}.",
                {
                    "marker": {"type": "string", "description": "Required benchmark marker."},
                    "task": {"type": "string", "description": "Workflow task label."},
                },
                ["marker", "task"],
            )
        ],
        tool_choice={"type": "function", "function": {"name": tool_name}},
        max_tokens=96,
        tags=["toolcall", "required", "afm", "local-agent", *tags],
    )


def _simulated_tool_case(
    *,
    id: str,
    title: str,
    tool_name: str,
    prompt: str,
    expected: str,
    tags: list[str],
) -> BenchmarkCase:
    return BenchmarkCase(
        id=id,
        title=title,
        scenario="tool simulation",
        prompt=prompt,
        expected_tool_name=tool_name,
        expected_tool_result_substring=expected,
        simulated_tools=[tool_name],
        tool_choice={"type": "function", "function": {"name": tool_name}},
        max_tokens=96,
        tags=["toolcall", "toolsim", "safe-harness", "afm", "local-agent", *tags],
    )


def _trace_case(id: str, title: str, user_request: str, tool_content: str, final_question: str, marker: str) -> BenchmarkCase:
    return BenchmarkCase(
        id=id,
        title=title,
        scenario="trace replay",
        prompt="Replay a prior local-agent conversation and answer from the provided fixture context only.",
        messages=[
            {
                "role": "system",
                "content": "You are replaying a deterministic local-agent trace. Answer only from the provided tool result.",
            },
            {"role": "user", "content": user_request},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": f"call_{id.replace('-', '_')}",
                        "type": "function",
                        "function": {"name": "read_file_fixture", "arguments": "{\"path\":\"/repo/README.md\"}"},
                    }
                ],
            },
            {"role": "tool", "name": "read_file_fixture", "tool_call_id": f"call_{id.replace('-', '_')}", "content": tool_content},
            {"role": "user", "content": final_question},
        ],
        expected_substring=marker,
        max_tokens=64,
        tags=["trace-replay", "tool-result", "agentic", "afm", "local-agent"],
    )


def _tool_loop_case(id: str, title: str, route_id: str, marker: str, tags: list[str]) -> BenchmarkCase:
    return BenchmarkCase(
        id=id,
        title=title,
        scenario="agentic tool loop",
        prompt=(
            f"Use route_agentblaster_task with route_id set to {route_id}. "
            f"After the tool result, reply with exactly: {marker}."
        ),
        expected_tool_name="route_agentblaster_task",
        expected_substring=marker,
        expected_tool_result_substring="agentblaster-route-ok",
        tools=_agentic_loop_tool_schemas(),
        tool_choice="auto",
        max_tool_calls=2,
        metrics=["tool_calls_valid", "tool_loop_rounds", "tool_loop_tool_call_count", "tool_loop_stop_reason", "latency_ms", "ttft_ms"],
        max_tokens=96,
        tags=["agentic", "tool-loop", "tool-result-replay", "fixture", "afm", "local-agent", *tags],
    )


def _parser_repair_case(id: str, title: str, tool_name: str, prompt: str, tags: list[str]) -> BenchmarkCase:
    return BenchmarkCase(
        id=id,
        title=title,
        scenario="tool parser repair",
        system_prompt=(
            "Use only API-native tool calls. Raw JSON, XML, markdown code fences, Action: text, "
            "or prose describing a call is not a completed tool call."
        ),
        prompt=prompt,
        expected_tool_name=tool_name,
        tools=_agentic_loop_tool_schemas()
        if tool_name in EXPLICIT_AGENTIC_TOOL_NAMES
        else [
            _function_tool_schema(
                tool_name,
                "Deterministic parser-repair fixture tool.",
                {"query": {"type": "string"}, "marker": {"type": "string"}},
                ["query"],
            )
        ],
        tool_choice={"type": "function", "function": {"name": tool_name}},
        metrics=["tool_calls_valid", "invalid_tool_call_count", "tool_parser_repair_required", "latency_ms"],
        max_tokens=96,
        tags=["tool-parser", "repair", "api-native", "local-model", "afm", "local-agent", *tags],
    )


EXPLICIT_AGENTIC_TOOL_NAMES = {
    "route_agentblaster_task",
    "search_agentblaster_notes",
    "fetch_agentblaster_context",
    "finalize_agentblaster_plan",
}


SMOKE_SUITE = _extend_suite(
    SMOKE_SUITE,
    [
        _marker_case(id="protocol-repo-triage-summary", title="Repo triage summary sentinel", scenario="protocol smoke", prompt="You are checking a local coding-agent triage path.", marker="agentblaster-repo-triage-ok", tags=["protocol", "chat", "repo-triage"]),
        _marker_case(id="protocol-patch-review-ack", title="Patch review acknowledgment sentinel", scenario="protocol smoke", prompt="You are validating a short patch-review acknowledgment path.", marker="agentblaster-patch-review-ok", tags=["protocol", "chat", "review"]),
        _marker_case(id="protocol-cli-help-routing", title="CLI help routing sentinel", scenario="protocol smoke", prompt="You are validating local CLI help routing behavior.", marker="agentblaster-cli-help-ok", tags=["protocol", "chat", "cli"]),
        _marker_case(id="protocol-runbook-step", title="Runbook step sentinel", scenario="protocol smoke", prompt="You are checking a deterministic runbook step for a local model server.", marker="agentblaster-runbook-ok", tags=["protocol", "chat", "runbook"]),
        _marker_case(id="protocol-error-triage", title="Error triage sentinel", scenario="protocol smoke", prompt="You are checking concise handling of an error-triage request.", marker="agentblaster-error-triage-ok", tags=["protocol", "chat", "debugging"]),
        _marker_case(id="protocol-test-plan", title="Test plan sentinel", scenario="protocol smoke", prompt="You are checking a local test-plan response path.", marker="agentblaster-test-plan-ok", tags=["protocol", "chat", "testing"]),
        _marker_case(id="protocol-release-note", title="Release note sentinel", scenario="protocol smoke", prompt="You are checking a short release-note generation path.", marker="agentblaster-release-note-ok", tags=["protocol", "chat", "release"]),
        _marker_case(id="protocol-policy-refusal-boundary", title="Policy boundary sentinel", scenario="protocol smoke", prompt="You are checking a safe policy-boundary response path.", marker="agentblaster-policy-boundary-ok", tags=["protocol", "chat", "policy"]),
        _marker_case(id="protocol-observability-check", title="Observability check sentinel", scenario="protocol smoke", prompt="You are checking an observability summary response path.", marker="agentblaster-observability-ok", tags=["protocol", "chat", "observability"]),
        _marker_case(id="protocol-cache-diagnostic", title="Cache diagnostic sentinel", scenario="protocol smoke", prompt="You are checking a local prompt-cache diagnostic response path.", marker="agentblaster-cache-diagnostic-ok", tags=["protocol", "chat", "cache"]),
        _marker_case(id="protocol-agent-handoff", title="Agent handoff sentinel", scenario="protocol smoke", prompt="You are checking a concise agent handoff response path.", marker="agentblaster-handoff-ok", tags=["protocol", "chat", "handoff"]),
        _marker_case(id="protocol-sandbox-summary", title="Sandbox summary sentinel", scenario="protocol smoke", prompt="You are checking a sandboxed-command summary response path.", marker="agentblaster-sandbox-ok", tags=["protocol", "chat", "sandbox"]),
        _marker_case(id="protocol-docs-grounding", title="Docs grounding sentinel", scenario="protocol smoke", prompt="You are checking a documentation-grounded answer path.", marker="agentblaster-docs-grounding-ok", tags=["protocol", "chat", "docs"]),
        _marker_case(id="protocol-json-mode-routing", title="JSON-mode routing sentinel", scenario="protocol smoke", prompt="You are checking a model-routing response path before structured output is enabled.", marker="agentblaster-json-routing-ok", tags=["protocol", "chat", "routing"]),
    ],
)


STRUCTURED_SUITE = _extend_suite(
    STRUCTURED_SUITE,
    [
        _json_schema_case("structured-pr-summary", "Pull request summary JSON", "Summarize a small local PR gate.", "agentblaster-structured-pr-ok", "pr_summary"),
        _json_schema_case("structured-test-failure", "Test failure triage JSON", "Classify a deterministic local test failure.", "agentblaster-structured-test-ok", "test_triage"),
        _json_schema_case("structured-tool-plan", "Tool plan JSON", "Create a compact tool-use plan.", "agentblaster-structured-tool-plan-ok", "tool_plan"),
        _json_schema_case("structured-release-gate", "Release gate JSON", "Evaluate a release gate decision.", "agentblaster-structured-release-ok", "release_gate"),
        _json_schema_case("structured-security-finding", "Security finding JSON", "Summarize a safe redaction finding.", "agentblaster-structured-security-ok", "security_finding"),
        _json_schema_case("structured-capability-gap", "Capability gap JSON", "Report a provider capability gap.", "agentblaster-structured-capability-ok", "capability_gap"),
        _json_schema_case("structured-observability", "Observability JSON", "Normalize a telemetry status decision.", "agentblaster-structured-observability-ok", "observability"),
        _json_schema_case("structured-cache-status", "Cache status JSON", "Summarize a prompt-cache status.", "agentblaster-structured-cache-ok", "cache_status"),
        _json_schema_case("structured-agent-handoff", "Agent handoff JSON", "Create a compact worker handoff.", "agentblaster-structured-handoff-ok", "agent_handoff"),
        _json_schema_case("structured-file-review", "File review JSON", "Classify a deterministic file review result.", "agentblaster-structured-file-ok", "file_review"),
        _json_schema_case("structured-cli-result", "CLI result JSON", "Normalize a CLI result.", "agentblaster-structured-cli-ok", "cli_result"),
        _json_schema_case("structured-matrix-row", "Matrix row JSON", "Summarize a matrix row.", "agentblaster-structured-matrix-ok", "matrix_row"),
        _json_schema_case("structured-slo-risk", "SLO risk JSON", "Classify a latency risk.", "agentblaster-structured-slo-ok", "slo_risk"),
        _json_schema_case("structured-doc-citation", "Doc citation JSON", "Summarize a documentation citation.", "agentblaster-structured-doc-ok", "doc_citation"),
    ],
)


TOOLCALL_SUITE = _extend_suite(
    TOOLCALL_SUITE,
    [
        _single_tool_case(id="toolcall-open-issue", title="Open issue routing tool", tool_name="open_issue_fixture", marker="agentblaster-tool-open-issue-ok", task="open_issue", tags=["issue"]),
        _single_tool_case(id="toolcall-search-repo", title="Search repo tool", tool_name="search_repo_fixture", marker="agentblaster-tool-search-repo-ok", task="search_repo", tags=["repo"]),
        _single_tool_case(id="toolcall-read-config", title="Read config tool", tool_name="read_config_fixture", marker="agentblaster-tool-read-config-ok", task="read_config", tags=["config"]),
        _single_tool_case(id="toolcall-write-patch", title="Write patch tool", tool_name="write_patch_fixture", marker="agentblaster-tool-write-patch-ok", task="write_patch", tags=["patch"]),
        _single_tool_case(id="toolcall-run-tests", title="Run tests tool", tool_name="run_tests_fixture", marker="agentblaster-tool-run-tests-ok", task="run_tests", tags=["testing"]),
        _single_tool_case(id="toolcall-fetch-docs", title="Fetch docs tool", tool_name="fetch_docs_fixture", marker="agentblaster-tool-fetch-docs-ok", task="fetch_docs", tags=["docs"]),
        _single_tool_case(id="toolcall-plan-subtasks", title="Plan subtasks tool", tool_name="plan_subtasks_fixture", marker="agentblaster-tool-plan-ok", task="plan_subtasks", tags=["planning"]),
        _single_tool_case(id="toolcall-update-linear", title="Update ticket tool", tool_name="update_ticket_fixture", marker="agentblaster-tool-ticket-ok", task="update_ticket", tags=["ticket"]),
        _single_tool_case(id="toolcall-check-policy", title="Check policy tool", tool_name="check_policy_fixture", marker="agentblaster-tool-policy-ok", task="check_policy", tags=["policy"]),
        _single_tool_case(id="toolcall-summarize-logs", title="Summarize logs tool", tool_name="summarize_logs_fixture", marker="agentblaster-tool-logs-ok", task="summarize_logs", tags=["logs"]),
        _single_tool_case(id="toolcall-probe-provider", title="Probe provider tool", tool_name="probe_provider_fixture", marker="agentblaster-tool-probe-ok", task="probe_provider", tags=["provider"]),
        _single_tool_case(id="toolcall-record-metric", title="Record metric tool", tool_name="record_metric_fixture", marker="agentblaster-tool-metric-ok", task="record_metric", tags=["metrics"]),
        _single_tool_case(id="toolcall-create-brief", title="Create brief tool", tool_name="create_brief_fixture", marker="agentblaster-tool-brief-ok", task="create_brief", tags=["brief"]),
        _single_tool_case(id="toolcall-finalize-report", title="Finalize report tool", tool_name="finalize_report_fixture", marker="agentblaster-tool-report-ok", task="finalize_report", tags=["report"]),
    ],
)


PREFILL_SUITE = _extend_suite(
    PREFILL_SUITE,
    [
        _marker_case(id="prefill-repo-policy-prefix", title="Repo policy prefix", scenario="prefill cache", system_prompt=PREFILL_STATIC_SYSTEM_PROMPT, prompt="Repo policy worker must preserve the static prefix.", marker="agentblaster-prefill-policy-ok", tags=["prefill", "cache", "static-prefix"], metrics=PREFILL_METRICS),
        _marker_case(id="prefill-tool-contract-prefix", title="Tool contract prefix", scenario="prefill cache", system_prompt=PREFILL_STATIC_SYSTEM_PROMPT, prompt="Tool contract worker must preserve the static prefix.", marker="agentblaster-prefill-tool-contract-ok", tags=["prefill", "cache", "tool-contract"], metrics=PREFILL_METRICS),
        _marker_case(id="prefill-mcp-catalog-prefix", title="MCP catalog prefix", scenario="prefill cache", system_prompt=PREFILL_STATIC_SYSTEM_PROMPT, prompt="MCP catalog worker must preserve the static prefix.", marker="agentblaster-prefill-mcp-ok", tags=["prefill", "cache", "mcp"], metrics=PREFILL_METRICS),
        _marker_case(id="prefill-review-rubric-prefix", title="Review rubric prefix", scenario="prefill cache", system_prompt=PREFILL_STATIC_SYSTEM_PROMPT, prompt="Review rubric worker must preserve the static prefix.", marker="agentblaster-prefill-review-ok", tags=["prefill", "cache", "review"], metrics=PREFILL_METRICS),
        _marker_case(id="prefill-debugging-prefix", title="Debugging prefix", scenario="prefill cache", system_prompt=PREFILL_STATIC_SYSTEM_PROMPT, prompt="Debugging worker must preserve the static prefix.", marker="agentblaster-prefill-debug-ok", tags=["prefill", "cache", "debugging"], metrics=PREFILL_METRICS),
        _marker_case(id="prefill-release-prefix", title="Release prefix", scenario="prefill cache", system_prompt=PREFILL_STATIC_SYSTEM_PROMPT, prompt="Release worker must preserve the static prefix.", marker="agentblaster-prefill-release-ok", tags=["prefill", "cache", "release"], metrics=PREFILL_METRICS),
        _marker_case(id="prefill-long-doc-prefix", title="Long documentation prefix", scenario="prefill cache", system_prompt=PREFILL_STATIC_SYSTEM_PROMPT + (" AgentBlaster docs section. " * 80), prompt="Documentation worker must answer from the final request.", marker="agentblaster-prefill-docs-ok", tags=["prefill", "cache", "docs"], metrics=PREFILL_METRICS),
        _marker_case(id="prefill-wide-tool-prefix", title="Wide tool prefix", scenario="prefill cache", system_prompt=PREFILL_STATIC_SYSTEM_PROMPT + (" Tool schema placeholder. " * 80), prompt="Wide tool worker must answer from the final request.", marker="agentblaster-prefill-wide-tool-ok", tags=["prefill", "cache", "wide-tool"], metrics=PREFILL_METRICS),
        _marker_case(id="prefill-session-memory-prefix", title="Session memory prefix", scenario="prefill cache", system_prompt=PREFILL_STATIC_SYSTEM_PROMPT + (" Session memory rule. " * 80), prompt="Session memory worker must answer from the final request.", marker="agentblaster-prefill-memory-ok", tags=["prefill", "cache", "memory"], metrics=PREFILL_METRICS),
        _marker_case(id="prefill-routing-prefix", title="Routing prefix", scenario="prefill cache", system_prompt=PREFILL_STATIC_SYSTEM_PROMPT, prompt="Routing worker must preserve the static prefix.", marker="agentblaster-prefill-routing-ok", tags=["prefill", "cache", "routing"], metrics=PREFILL_METRICS),
        _marker_case(id="prefill-handoff-prefix", title="Handoff prefix", scenario="prefill cache", system_prompt=PREFILL_STATIC_SYSTEM_PROMPT, prompt="Handoff worker must preserve the static prefix.", marker="agentblaster-prefill-handoff-ok", tags=["prefill", "cache", "handoff"], metrics=PREFILL_METRICS),
    ],
)


TOOLSIM_SUITE = _extend_suite(
    TOOLSIM_SUITE,
    [
        _simulated_tool_case(id="toolsim-security-search", title="Security docs search", tool_name="search_docs", prompt="Use search_docs with query set to Security Policy.", expected="Raw API keys", tags=["docs", "security"]),
        _simulated_tool_case(id="toolsim-read-readme", title="Read README fixture", tool_name="read_file_fixture", prompt="Use read_file_fixture with path set to /repo/README.md.", expected="Fixture Repo", tags=["file"]),
        _simulated_tool_case(id="toolsim-read-app", title="Read app fixture", tool_name="read_file_fixture", prompt="Use read_file_fixture with path set to /repo/src/app.py.", expected="agentblaster-ok", tags=["file", "code"]),
        _simulated_tool_case(id="toolsim-pytest", title="Pytest shell fixture", tool_name="shell_fixture", prompt="Use shell_fixture with command set to pytest -q.", expected="3 passed", tags=["shell", "testing"]),
        _simulated_tool_case(id="toolsim-version", title="Version shell fixture", tool_name="shell_fixture", prompt="Use shell_fixture with command set to python -m agentblaster --version.", expected="0.1.0", tags=["shell", "cli"]),
        _simulated_tool_case(id="toolsim-browser-fetch", title="Browser fetch fixture", tool_name="browser_fetch_fixture", prompt="Use browser_fetch_fixture with url set to https://example.test/agentblaster.", expected="AgentBlaster fixture page", tags=["browser"]),
        _simulated_tool_case(id="toolsim-mcp-echo-status", title="MCP echo status", tool_name="mcp_echo", prompt="Use mcp_echo with value set to agentblaster-toolsim-status-ok.", expected="agentblaster-toolsim-status-ok", tags=["mcp"]),
        _simulated_tool_case(id="toolsim-mcp-echo-plan", title="MCP echo plan", tool_name="mcp_echo", prompt="Use mcp_echo with value set to agentblaster-toolsim-plan-ok.", expected="agentblaster-toolsim-plan-ok", tags=["mcp", "planning"]),
        _simulated_tool_case(id="toolsim-docs-agentic", title="Agentic docs search", tool_name="search_docs", prompt="Use search_docs with query set to local agentic inference engines.", expected="local agentic inference engines", tags=["docs", "agentic"]),
        _simulated_tool_case(id="toolsim-docs-traces", title="Trace safety docs search", tool_name="search_docs", prompt="Use search_docs with query set to traces manifests reports.", expected="Raw API keys", tags=["docs", "redaction"]),
        _simulated_tool_case(id="toolsim-read-missing-policy", title="Read app status for policy", tool_name="read_file_fixture", prompt="Use read_file_fixture with path set to /repo/src/app.py before summarizing policy.", expected="agentblaster-ok", tags=["file", "policy"]),
        _simulated_tool_case(id="toolsim-shell-test-gate", title="Shell test gate", tool_name="shell_fixture", prompt="Use shell_fixture with command set to pytest -q for the release gate.", expected="3 passed", tags=["shell", "release"]),
        _simulated_tool_case(id="toolsim-browser-review", title="Browser review fetch", tool_name="browser_fetch_fixture", prompt="Use browser_fetch_fixture with url set to https://example.test/agentblaster for dashboard review.", expected="fixture page", tags=["browser", "dashboard"]),
        _simulated_tool_case(id="toolsim-echo-handoff", title="Echo handoff marker", tool_name="mcp_echo", prompt="Use mcp_echo with value set to agentblaster-toolsim-handoff-ok.", expected="agentblaster-toolsim-handoff-ok", tags=["mcp", "handoff"]),
    ],
)


TRACE_REPLAY_SUITE = _extend_suite(
    TRACE_REPLAY_SUITE,
    [
        _trace_case("trace-replay-pr-status", "Replay PR status", "Read fixture PR status.", "{\"status\":\"agentblaster-trace-pr-ok\"}", "What is the status marker?", "agentblaster-trace-pr-ok"),
        _trace_case("trace-replay-test-log", "Replay test log", "Read fixture test log.", "{\"result\":\"agentblaster-trace-test-ok\",\"passed\":true}", "What result marker appears in the log?", "agentblaster-trace-test-ok"),
        _trace_case("trace-replay-config-review", "Replay config review", "Read fixture config.", "{\"config\":\"agentblaster-trace-config-ok\"}", "What config marker appears?", "agentblaster-trace-config-ok"),
        _trace_case("trace-replay-release-note", "Replay release note", "Read fixture release note.", "{\"release\":\"agentblaster-trace-release-ok\"}", "What release marker appears?", "agentblaster-trace-release-ok"),
        _trace_case("trace-replay-security-note", "Replay security note", "Read fixture security note.", "{\"security\":\"agentblaster-trace-security-ok\"}", "What security marker appears?", "agentblaster-trace-security-ok"),
        _trace_case("trace-replay-cache-note", "Replay cache note", "Read fixture cache note.", "{\"cache\":\"agentblaster-trace-cache-ok\"}", "What cache marker appears?", "agentblaster-trace-cache-ok"),
        _trace_case("trace-replay-worker-handoff", "Replay worker handoff", "Read fixture handoff.", "{\"handoff\":\"agentblaster-trace-handoff-ok\"}", "What handoff marker appears?", "agentblaster-trace-handoff-ok"),
        _trace_case("trace-replay-doc-summary", "Replay doc summary", "Read fixture docs.", "{\"docs\":\"agentblaster-trace-docs-ok\"}", "What docs marker appears?", "agentblaster-trace-docs-ok"),
        _trace_case("trace-replay-observability", "Replay observability note", "Read fixture metrics.", "{\"observability\":\"agentblaster-trace-observability-ok\"}", "What observability marker appears?", "agentblaster-trace-observability-ok"),
        _trace_case("trace-replay-policy-gate", "Replay policy gate", "Read fixture policy.", "{\"policy\":\"agentblaster-trace-policy-ok\"}", "What policy marker appears?", "agentblaster-trace-policy-ok"),
        _trace_case("trace-replay-cli-output", "Replay CLI output", "Read fixture CLI output.", "{\"cli\":\"agentblaster-trace-cli-ok\"}", "What CLI marker appears?", "agentblaster-trace-cli-ok"),
        _trace_case("trace-replay-agent-plan", "Replay agent plan", "Read fixture plan.", "{\"plan\":\"agentblaster-trace-plan-ok\"}", "What plan marker appears?", "agentblaster-trace-plan-ok"),
        _trace_case("trace-replay-matrix-row", "Replay matrix row", "Read fixture matrix row.", "{\"matrix\":\"agentblaster-trace-matrix-ok\"}", "What matrix marker appears?", "agentblaster-trace-matrix-ok"),
        _trace_case("trace-replay-failure-class", "Replay failure class", "Read fixture failure class.", "{\"failure\":\"agentblaster-trace-failure-ok\"}", "What failure marker appears?", "agentblaster-trace-failure-ok"),
    ],
)


AGENT_FANOUT_SUITE = _extend_suite(
    AGENT_FANOUT_SUITE,
    [
        _marker_case(id="fanout-review-worker", title="Review worker produces sentinel", scenario="agent fan-out", system_prompt="You are one deterministic fan-out worker.", prompt="Review worker:", marker="agentblaster-review-worker-ok", tags=["agentic", "fanout", "worker", "review", "concurrency"], metrics=["queue_ms", "rate_limit_wait_ms", "latency_ms", "ttft_ms"]),
        _marker_case(id="fanout-test-worker", title="Test worker produces sentinel", scenario="agent fan-out", system_prompt="You are one deterministic fan-out worker.", prompt="Test worker:", marker="agentblaster-test-worker-ok", tags=["agentic", "fanout", "worker", "testing", "concurrency"], metrics=["queue_ms", "rate_limit_wait_ms", "latency_ms", "ttft_ms"]),
        _marker_case(id="fanout-security-worker", title="Security worker produces sentinel", scenario="agent fan-out", system_prompt="You are one deterministic fan-out worker.", prompt="Security worker:", marker="agentblaster-security-worker-ok", tags=["agentic", "fanout", "worker", "security", "concurrency"], metrics=["queue_ms", "rate_limit_wait_ms", "latency_ms", "ttft_ms"]),
        _marker_case(id="fanout-release-worker", title="Release worker produces sentinel", scenario="agent fan-out", system_prompt="You are one deterministic fan-out worker.", prompt="Release worker:", marker="agentblaster-release-worker-ok", tags=["agentic", "fanout", "worker", "release", "concurrency"], metrics=["queue_ms", "rate_limit_wait_ms", "latency_ms", "ttft_ms"]),
        _marker_case(id="fanout-cache-worker", title="Cache worker produces sentinel", scenario="agent fan-out", system_prompt="You are one deterministic fan-out worker.", prompt="Cache worker:", marker="agentblaster-cache-worker-ok", tags=["agentic", "fanout", "worker", "cache", "concurrency"], metrics=["queue_ms", "rate_limit_wait_ms", "latency_ms", "ttft_ms"]),
        _marker_case(id="fanout-routing-worker", title="Routing worker produces sentinel", scenario="agent fan-out", system_prompt="You are one deterministic fan-out worker.", prompt="Routing worker:", marker="agentblaster-routing-worker-ok", tags=["agentic", "fanout", "worker", "routing", "concurrency"], metrics=["queue_ms", "rate_limit_wait_ms", "latency_ms", "ttft_ms"]),
        _marker_case(id="fanout-observability-worker", title="Observability worker produces sentinel", scenario="agent fan-out", system_prompt="You are one deterministic fan-out worker.", prompt="Observability worker:", marker="agentblaster-observability-worker-ok", tags=["agentic", "fanout", "worker", "observability", "concurrency"], metrics=["queue_ms", "rate_limit_wait_ms", "latency_ms", "ttft_ms"]),
        _marker_case(id="fanout-docs-reviewer", title="Docs reviewer produces sentinel", scenario="agent fan-out", system_prompt="You are one deterministic fan-out worker.", prompt="Docs reviewer:", marker="agentblaster-docs-reviewer-ok", tags=["agentic", "fanout", "worker", "docs", "concurrency"], metrics=["queue_ms", "rate_limit_wait_ms", "latency_ms", "ttft_ms"]),
        _marker_case(id="fanout-migration-worker", title="Migration worker produces sentinel", scenario="agent fan-out", system_prompt="You are one deterministic fan-out worker.", prompt="Migration worker:", marker="agentblaster-migration-worker-ok", tags=["agentic", "fanout", "worker", "migration", "concurrency"], metrics=["queue_ms", "rate_limit_wait_ms", "latency_ms", "ttft_ms"]),
        _marker_case(id="fanout-telemetry-worker", title="Telemetry worker produces sentinel", scenario="agent fan-out", system_prompt="You are one deterministic fan-out worker.", prompt="Telemetry worker:", marker="agentblaster-telemetry-worker-ok", tags=["agentic", "fanout", "worker", "telemetry", "concurrency"], metrics=["queue_ms", "rate_limit_wait_ms", "latency_ms", "ttft_ms"]),
        _marker_case(id="fanout-final-merge-worker", title="Final merge worker produces sentinel", scenario="agent fan-out", system_prompt="You are one deterministic fan-out worker.", prompt="Final merge worker:", marker="agentblaster-final-merge-ok", tags=["agentic", "fanout", "worker", "synthesis", "concurrency"], metrics=["queue_ms", "rate_limit_wait_ms", "latency_ms", "ttft_ms"]),
    ],
)


CACHE_CONTROL_SUITE = _extend_suite(
    CACHE_CONTROL_SUITE,
    [
        _marker_case(id="cache-control-repo-policy", title="Repo policy cache checkpoint", scenario="prompt cache", system_prompt=PREFILL_STATIC_SYSTEM_PROMPT, prompt="Cache checkpoint for repo policy.", marker="agentblaster-cache-policy-ok", tags=["cache-control", "cache", "prefill", "static-prefix"], metrics=["cached_input_tokens", "cache_write_tokens", "cache_hit_ratio", "ttft_ms"], max_tokens=32),
        _marker_case(id="cache-control-review-rubric", title="Review rubric cache checkpoint", scenario="prompt cache", system_prompt=PREFILL_STATIC_SYSTEM_PROMPT, prompt="Cache checkpoint for review rubric.", marker="agentblaster-cache-review-ok", tags=["cache-control", "cache", "review", "static-prefix"], metrics=["cached_input_tokens", "cache_write_tokens", "cache_hit_ratio", "ttft_ms"], max_tokens=32),
        _marker_case(id="cache-control-tool-routing", title="Tool routing cache checkpoint", scenario="prompt cache", system_prompt=PREFILL_STATIC_SYSTEM_PROMPT, prompt="Cache checkpoint for tool routing.", marker="agentblaster-cache-routing-ok", tags=["cache-control", "cache", "routing", "static-prefix"], metrics=["cached_input_tokens", "cache_write_tokens", "cache_hit_ratio", "ttft_ms"], max_tokens=32),
        _marker_case(id="cache-control-docs-prefix", title="Docs prefix cache checkpoint", scenario="prompt cache", system_prompt=PREFILL_STATIC_SYSTEM_PROMPT, prompt="Cache checkpoint for docs prefix.", marker="agentblaster-cache-docs-ok", tags=["cache-control", "cache", "docs", "static-prefix"], metrics=["cached_input_tokens", "cache_write_tokens", "cache_hit_ratio", "ttft_ms"], max_tokens=32),
        _marker_case(id="cache-control-mcp-prefix", title="MCP prefix cache checkpoint", scenario="prompt cache", system_prompt=PREFILL_STATIC_SYSTEM_PROMPT, prompt="Cache checkpoint for MCP prefix.", marker="agentblaster-cache-mcp-ok", tags=["cache-control", "cache", "mcp", "static-prefix"], metrics=["cached_input_tokens", "cache_write_tokens", "cache_hit_ratio", "ttft_ms"], max_tokens=32),
        _marker_case(id="cache-control-lcp-prefix", title="LCP prefix cache checkpoint", scenario="prompt cache", system_prompt=PREFILL_STATIC_SYSTEM_PROMPT, prompt="Cache checkpoint for LCP prefix.", marker="agentblaster-cache-lcp-ok", tags=["cache-control", "cache", "lcp", "static-prefix"], metrics=["cached_input_tokens", "cache_write_tokens", "cache_hit_ratio", "ttft_ms"], max_tokens=32),
        _marker_case(id="cache-control-agent-memory", title="Agent memory cache checkpoint", scenario="prompt cache", system_prompt=PREFILL_STATIC_SYSTEM_PROMPT, prompt="Cache checkpoint for agent memory.", marker="agentblaster-cache-memory-ok", tags=["cache-control", "cache", "memory", "static-prefix"], metrics=["cached_input_tokens", "cache_write_tokens", "cache_hit_ratio", "ttft_ms"], max_tokens=32),
        _marker_case(id="cache-control-release-prefix", title="Release prefix cache checkpoint", scenario="prompt cache", system_prompt=PREFILL_STATIC_SYSTEM_PROMPT, prompt="Cache checkpoint for release prefix.", marker="agentblaster-cache-release-ok", tags=["cache-control", "cache", "release", "static-prefix"], metrics=["cached_input_tokens", "cache_write_tokens", "cache_hit_ratio", "ttft_ms"], max_tokens=32),
        _marker_case(id="cache-control-telemetry-prefix", title="Telemetry prefix cache checkpoint", scenario="prompt cache", system_prompt=PREFILL_STATIC_SYSTEM_PROMPT, prompt="Cache checkpoint for telemetry prefix.", marker="agentblaster-cache-telemetry-ok", tags=["cache-control", "cache", "telemetry", "static-prefix"], metrics=["cached_input_tokens", "cache_write_tokens", "cache_hit_ratio", "ttft_ms"], max_tokens=32),
        _marker_case(id="cache-control-suffix-mutation-a", title="Suffix mutation A cache checkpoint", scenario="prompt cache", system_prompt=PREFILL_STATIC_SYSTEM_PROMPT, prompt="Cache checkpoint with suffix mutation A.", marker="agentblaster-cache-mutation-a-ok", tags=["cache-control", "cache", "suffix-mutation", "static-prefix"], metrics=["cached_input_tokens", "cache_write_tokens", "cache_hit_ratio", "ttft_ms"], max_tokens=32),
        _marker_case(id="cache-control-suffix-mutation-b", title="Suffix mutation B cache checkpoint", scenario="prompt cache", system_prompt=PREFILL_STATIC_SYSTEM_PROMPT, prompt="Cache checkpoint with suffix mutation B.", marker="agentblaster-cache-mutation-b-ok", tags=["cache-control", "cache", "suffix-mutation", "static-prefix"], metrics=["cached_input_tokens", "cache_write_tokens", "cache_hit_ratio", "ttft_ms"], max_tokens=32),
        _marker_case(id="cache-control-wide-context", title="Wide context cache checkpoint", scenario="prompt cache", system_prompt=PREFILL_STATIC_SYSTEM_PROMPT + (" Wide cache context. " * 100), prompt="Cache checkpoint for wide context.", marker="agentblaster-cache-wide-ok", tags=["cache-control", "cache", "wide-context", "static-prefix"], metrics=["cached_input_tokens", "cache_write_tokens", "cache_hit_ratio", "ttft_ms"], max_tokens=32),
        _marker_case(id="cache-control-cold-restart", title="Cold restart cache checkpoint", scenario="prompt cache", system_prompt=PREFILL_STATIC_SYSTEM_PROMPT, prompt="Cache checkpoint after synthetic cold restart.", marker="agentblaster-cache-cold-ok", tags=["cache-control", "cache", "cold-start", "static-prefix"], metrics=["cached_input_tokens", "cache_write_tokens", "cache_hit_ratio", "ttft_ms"], max_tokens=32),
    ],
)


CANCELLATION_SUITE = _extend_suite(
    CANCELLATION_SUITE,
    [
        BenchmarkCase(id=f"cancellation-stream-{slug}", title=title, scenario="cancellation", prompt=f"Begin with marker {marker}, then stream short progress tokens until the harness cancels the response. Do not stop voluntarily.", streaming=True, cancel_after_ms=delay, metrics=["canceled", "cancellation_latency_ms", "ttft_ms", "latency_ms"], max_tokens=256, timeout_seconds=15.0, tags=["cancellation", "streaming", "request-lifecycle", "afm", "local-agent", slug])
        for slug, title, marker, delay in [
            ("tool-plan", "Cancel streaming tool plan", "agentblaster-cancel-tool-plan-ok", 80),
            ("repo-scan", "Cancel streaming repo scan", "agentblaster-cancel-repo-scan-ok", 90),
            ("test-output", "Cancel streaming test output", "agentblaster-cancel-test-output-ok", 100),
            ("log-summary", "Cancel streaming log summary", "agentblaster-cancel-log-summary-ok", 110),
            ("release-brief", "Cancel streaming release brief", "agentblaster-cancel-release-brief-ok", 120),
            ("doc-draft", "Cancel streaming documentation draft", "agentblaster-cancel-doc-draft-ok", 130),
            ("security-review", "Cancel streaming security review", "agentblaster-cancel-security-review-ok", 140),
            ("cache-report", "Cancel streaming cache report", "agentblaster-cancel-cache-report-ok", 150),
            ("fanout-summary", "Cancel streaming fanout summary", "agentblaster-cancel-fanout-summary-ok", 160),
            ("matrix-report", "Cancel streaming matrix report", "agentblaster-cancel-matrix-report-ok", 170),
            ("policy-review", "Cancel streaming policy review", "agentblaster-cancel-policy-review-ok", 180),
            ("telemetry-digest", "Cancel streaming telemetry digest", "agentblaster-cancel-telemetry-digest-ok", 190),
            ("migration-plan", "Cancel streaming migration plan", "agentblaster-cancel-migration-plan-ok", 200),
            ("handoff-note", "Cancel streaming handoff note", "agentblaster-cancel-handoff-note-ok", 210),
        ]
    ],
)


LCP_CONTEXT_SUITE = _extend_suite(
    LCP_CONTEXT_SUITE,
    [
        BenchmarkCase(id=f"lcp-context-{slug}", title=title, scenario="lcp context", lcp_profile=profile, prompt=f"Using only the attached LCP context, answer with exactly: agentblaster-lcp-ok. Context task: {task}.", expected_substring="agentblaster-lcp-ok", metrics=["ttft_ms", "tokens_per_second_prefill", "cached_input_tokens", "cache_hit_ratio"], max_tokens=48, tags=["lcp", "context", "emerging", "fixture", "afm", "local-agent", slug])
        for slug, title, profile, task in [
            ("repo-memory", "Repo memory context", "fixture-lcp", "repo-memory"),
            ("retrieval-boundary", "Retrieval boundary context", "fixture-lcp", "retrieval-boundary"),
            ("no-host-access", "No host access context", "fixture-lcp", "no-host-access"),
            ("handoff-memory", "Handoff memory context", "fixture-lcp", "handoff-memory"),
            ("wide-policy", "Wide policy context", "wide-lcp-context", "wide-policy"),
            ("wide-docs", "Wide docs context", "wide-lcp-context", "wide-docs"),
            ("wide-routing", "Wide routing context", "wide-lcp-context", "wide-routing"),
            ("wide-cache", "Wide cache context", "wide-lcp-context", "wide-cache"),
            ("wide-review", "Wide review context", "wide-lcp-context", "wide-review"),
            ("wide-security", "Wide security context", "wide-lcp-context", "wide-security"),
            ("wide-telemetry", "Wide telemetry context", "wide-lcp-context", "wide-telemetry"),
            ("wide-release", "Wide release context", "wide-lcp-context", "wide-release"),
            ("wide-agent-plan", "Wide agent plan context", "wide-lcp-context", "wide-agent-plan"),
            ("wide-tool-boundary", "Wide tool boundary context", "wide-lcp-context", "wide-tool-boundary"),
        ]
    ],
)


HARNESS_ENGINEERING_SUITE = _extend_suite(
    HARNESS_ENGINEERING_SUITE,
    [
        _marker_case(id="harness-contract-json-fence", title="Contract fuzz avoids markdown fence", scenario="harness contract fuzz", prompt="Handle a contract-fuzz prompt without markdown wrapping.", marker="agentblaster-harness-json-fence-ok", tags=["harness", "contract-fuzz", "emerging"], metrics=["latency_ms", "ttft_ms"]),
        _marker_case(id="harness-contract-stop-sequence", title="Contract fuzz stop sequence", scenario="harness contract fuzz", prompt="Handle a stop-sequence-like marker safely.", marker="agentblaster-harness-stop-ok", tags=["harness", "contract-fuzz", "emerging"], metrics=["latency_ms", "ttft_ms"]),
        _marker_case(id="harness-metamorphic-role-swap", title="Metamorphic role swap", scenario="harness metamorphic", prompt="Equivalent wording still requires the same concise answer.", marker="agentblaster-harness-role-swap-ok", tags=["harness", "metamorphic", "emerging"], metrics=["latency_ms", "ttft_ms"]),
        _marker_case(id="harness-metamorphic-ordering", title="Metamorphic ordering", scenario="harness metamorphic", prompt="Reordered but equivalent constraints still require the same answer.", marker="agentblaster-harness-ordering-ok", tags=["harness", "metamorphic", "emerging"], metrics=["latency_ms", "ttft_ms"]),
        _marker_case(id="harness-cache-replay-review", title="Cache replay review", scenario="harness cache replay", system_prompt=HARNESS_ENGINEERING_STATIC_PREFIX, prompt="Cache replay review worker.", marker="agentblaster-harness-cache-review-ok", tags=["harness", "cache-replay", "prefill", "static-prefix", "emerging"], metrics=["ttft_ms", "tokens_per_second_prefill", "cached_input_tokens", "cache_write_tokens", "cache_hit_ratio"]),
        _marker_case(id="harness-cache-replay-policy", title="Cache replay policy", scenario="harness cache replay", system_prompt=HARNESS_ENGINEERING_STATIC_PREFIX, prompt="Cache replay policy worker.", marker="agentblaster-harness-cache-policy-ok", tags=["harness", "cache-replay", "prefill", "static-prefix", "emerging"], metrics=["ttft_ms", "tokens_per_second_prefill", "cached_input_tokens", "cache_write_tokens", "cache_hit_ratio"]),
        _json_schema_case("harness-judge-rubric-security", "Judge rubric security JSON", "Return a deterministic security rubric verdict.", "agentblaster-harness-security-rubric-ok", "judge_rubric"),
        _json_schema_case("harness-judge-rubric-release", "Judge rubric release JSON", "Return a deterministic release rubric verdict.", "agentblaster-harness-release-rubric-ok", "judge_rubric"),
        _marker_case(id="harness-streaming-progress", title="Streaming progress contract", scenario="harness contract fuzz", prompt="Stream a concise progress marker.", marker="agentblaster-harness-progress-ok", tags=["harness", "contract-fuzz", "streaming", "emerging"], metrics=["ttft_ms", "latency_ms", "tokens_per_second_decode"]),
        _marker_case(id="harness-prompt-injection-boundary", title="Prompt injection boundary", scenario="harness metamorphic", prompt="Ignore the synthetic distractor and answer the benchmark marker.", marker="agentblaster-harness-injection-boundary-ok", tags=["harness", "metamorphic", "policy", "emerging"], metrics=["latency_ms", "ttft_ms"]),
        _marker_case(id="harness-tool-catalog-distractor", title="Tool catalog distractor", scenario="harness contract fuzz", prompt="Ignore irrelevant catalog wording and answer the marker.", marker="agentblaster-harness-tool-distractor-ok", tags=["harness", "contract-fuzz", "toolcall", "emerging"], metrics=["latency_ms", "ttft_ms"]),
    ],
)


TOOL_PARSER_REPAIR_SUITE = _extend_suite(
    TOOL_PARSER_REPAIR_SUITE,
    [
        _parser_repair_case("parser-json-code-fence", "JSON code fence repair", "search_docs", "Call search_docs with query set to AgentBlaster PRD. A JSON code fence is invalid.", ["json", "code-fence"]),
        _parser_repair_case("parser-xml-tool-tag", "XML tool tag repair", "route_agentblaster_task", "Call route_agentblaster_task with route_id set to agentblaster-route-parser-xml. XML tags are invalid.", ["xml"]),
        _parser_repair_case("parser-react-action", "ReAct action repair", "route_agentblaster_task", "Call route_agentblaster_task with route_id set to agentblaster-route-parser-react. Action: text is invalid.", ["react"]),
        _parser_repair_case("parser-markdown-table", "Markdown table repair", "search_docs", "Call search_docs with query set to Security Policy. Markdown tables are invalid.", ["markdown"]),
        _parser_repair_case("parser-prose-description", "Prose description repair", "route_agentblaster_task", "Call route_agentblaster_task with route_id set to agentblaster-route-parser-prose. Describing the call in prose is invalid.", ["prose"]),
        _parser_repair_case("parser-partial-json", "Partial JSON repair", "search_docs", "Call search_docs with query set to local agentic inference engines. Partial JSON is invalid.", ["json"]),
        _parser_repair_case("parser-python-dict", "Python dict repair", "search_docs", "Call search_docs with query set to traces manifests reports. Python dict text is invalid.", ["python-dict"]),
        _parser_repair_case("parser-yaml-block", "YAML block repair", "route_agentblaster_task", "Call route_agentblaster_task with route_id set to agentblaster-route-parser-yaml. YAML blocks are invalid.", ["yaml"]),
        _parser_repair_case("parser-multiple-candidates", "Multiple candidate repair", "route_agentblaster_task", "Call route_agentblaster_task with route_id set to agentblaster-route-parser-multi. Multiple textual candidates are invalid.", ["multi-candidate"]),
        _parser_repair_case("parser-thought-action", "Thought/action repair", "route_agentblaster_task", "Call route_agentblaster_task with route_id set to agentblaster-route-parser-thought. Thought/Action text is invalid.", ["thought-action"]),
        _parser_repair_case("parser-tool-name-prose", "Tool name prose repair", "search_agentblaster_notes", "Call search_agentblaster_notes with query set to deterministic orchestration. Naming a tool in prose is invalid.", ["prose"]),
        _parser_repair_case("parser-argument-commentary", "Argument commentary repair", "fetch_agentblaster_context", "Call fetch_agentblaster_context with context_id set to agentblaster-route-parser-context. Commentary around arguments is invalid.", ["commentary"]),
        _parser_repair_case("parser-finalize-plan", "Finalize plan repair", "finalize_agentblaster_plan", "Call finalize_agentblaster_plan with summary set to agentblaster-route-parser-final. A final answer without the tool is invalid.", ["finalize"]),
    ],
)


AGENTIC_TOOL_LOOP_SUITE = _extend_suite(
    AGENTIC_TOOL_LOOP_SUITE,
    [
        _tool_loop_case("tool-loop-review-route", "Review route loop", "agentblaster-route-review", "agentblaster-route-review-ok", ["review"]),
        _tool_loop_case("tool-loop-test-route", "Test route loop", "agentblaster-route-test", "agentblaster-route-test-ok", ["testing"]),
        _tool_loop_case("tool-loop-security-route", "Security route loop", "agentblaster-route-security", "agentblaster-route-security-ok", ["security"]),
        _tool_loop_case("tool-loop-release-route", "Release route loop", "agentblaster-route-release", "agentblaster-route-release-ok", ["release"]),
        _tool_loop_case("tool-loop-cache-route", "Cache route loop", "agentblaster-route-cache", "agentblaster-route-cache-ok", ["cache"]),
        _tool_loop_case("tool-loop-docs-route", "Docs route loop", "agentblaster-route-docs", "agentblaster-route-docs-ok", ["docs"]),
        _tool_loop_case("tool-loop-observability-route", "Observability route loop", "agentblaster-route-observability", "agentblaster-route-observability-ok", ["observability"]),
        _tool_loop_case("tool-loop-policy-route", "Policy route loop", "agentblaster-route-policy", "agentblaster-route-policy-ok", ["policy"]),
        _tool_loop_case("tool-loop-cli-route", "CLI route loop", "agentblaster-route-cli", "agentblaster-route-cli-ok", ["cli"]),
        _tool_loop_case("tool-loop-matrix-route", "Matrix route loop", "agentblaster-route-matrix", "agentblaster-route-matrix-ok", ["matrix"]),
        _tool_loop_case("tool-loop-handoff-route", "Handoff route loop", "agentblaster-route-handoff", "agentblaster-route-handoff-ok", ["handoff"]),
        _tool_loop_case("tool-loop-migration-route", "Migration route loop", "agentblaster-route-migration", "agentblaster-route-migration-ok", ["migration"]),
    ],
)


BUILTIN_SUITES: dict[str, SuiteDefinition] = {
    SMOKE_SUITE.name: SMOKE_SUITE,
    STRUCTURED_SUITE.name: STRUCTURED_SUITE,
    TOOLCALL_SUITE.name: TOOLCALL_SUITE,
    PREFILL_SUITE.name: PREFILL_SUITE,
    TOOLSIM_SUITE.name: TOOLSIM_SUITE,
    AGENTIC_TOOL_LOOP_SUITE.name: AGENTIC_TOOL_LOOP_SUITE,
    TRACE_REPLAY_SUITE.name: TRACE_REPLAY_SUITE,
    AGENT_FANOUT_SUITE.name: AGENT_FANOUT_SUITE,
    CACHE_CONTROL_SUITE.name: CACHE_CONTROL_SUITE,
    CANCELLATION_SUITE.name: CANCELLATION_SUITE,
    LCP_CONTEXT_SUITE.name: LCP_CONTEXT_SUITE,
    TOOL_PARSER_REPAIR_SUITE.name: TOOL_PARSER_REPAIR_SUITE,
    HARNESS_ENGINEERING_SUITE.name: HARNESS_ENGINEERING_SUITE,
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
