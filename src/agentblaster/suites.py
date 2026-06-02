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
