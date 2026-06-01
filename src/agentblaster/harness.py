from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from typing import Any

import yaml

from agentblaster.errors import ConfigError
from agentblaster.models import BenchmarkCase, SuiteDefinition, SuiteProvenance

HARNESS_REVIEW_SCHEMA_VERSION = "agentblaster.harness-review.v1"


@dataclass(frozen=True)
class HarnessProfile:
    name: str
    purpose: str


HARNESS_PROFILES: tuple[HarnessProfile, ...] = (
    HarnessProfile(
        name="prefill",
        purpose="Generate repeated-prefix variants to expose prompt prefill, cache reuse, and large system prompt costs.",
    ),
    HarnessProfile(
        name="concurrency",
        purpose="Clone deterministic cases into a burst workload to expose queueing, pacing, cancellation, and isolation issues.",
    ),
    HarnessProfile(
        name="contract-fuzz",
        purpose="Generate OpenAI/Anthropic-compatible streaming, structured-output, and tool-call contract edge fixtures.",
    ),
    HarnessProfile(
        name="tool-parser-repair",
        purpose="Generate strict tool-parser repair fixtures that reject raw JSON, XML, markdown, or ReAct text as completed tool calls.",
    ),
    HarnessProfile(
        name="metamorphic",
        purpose="Generate equivalent wording and formatting variants to test agent stability under harmless prompt changes.",
    ),
    HarnessProfile(
        name="cache-replay",
        purpose="Generate warmup, replay, suffix-mutation, and prefix-invalidation variants for prompt-cache diagnostics.",
    ),
    HarnessProfile(
        name="cancellation",
        purpose="Generate streaming cancellation workloads to measure abort behavior and cancellation latency.",
    ),
    HarnessProfile(
        name="orchestration",
        purpose="Generate multi-tool routing workloads to stress agent planning, distractor tools, and tool-loop limits.",
    ),
    HarnessProfile(
        name="skills",
        purpose="Generate skill-prefix workloads to stress local-agent skill selection, static skill catalogs, and instruction routing overhead.",
    ),
    HarnessProfile(
        name="emerging-workflows",
        purpose="Generate mixed MCP/LCP/skills/tool-loop/cache workloads that emulate modern local-agent prompt stacks.",
    ),
    HarnessProfile(
        name="judge-rubric",
        purpose="Generate deterministic model-judge rubric workloads to test evaluator prompt discipline and structured verdicts.",
    ),
)


def list_harness_profiles() -> list[HarnessProfile]:
    return list(HARNESS_PROFILES)


_CACHE_REPLAY_PHASES = ("warmup", "replay", "suffix", "invalidate")
_CACHE_REPLAY_METRICS = (
    "ttft_ms",
    "tokens_per_second_prefill",
    "cached_input_tokens",
    "cache_write_tokens",
    "cache_hit_ratio",
    "latency_ms",
)
_CACHE_REPLAY_TAGS = ("harness", "cache-replay", "cache", "prefill", "synthetic")
_SKILL_CATALOG = (
    "repo-triage",
    "safe-tool-replay",
    "agent-planning",
    "context-summarization",
    "result-synthesis",
    "risk-review",
)


def generate_harness_suite(
    source: SuiteDefinition,
    *,
    profile: str,
    repeats: int = 4,
    seed: int = 0,
) -> SuiteDefinition:
    if repeats < 1:
        raise ConfigError("repeats must be >= 1")
    if profile == "prefill":
        return _prefill_suite(source, repeats=repeats, seed=seed)
    if profile == "concurrency":
        return _concurrency_suite(source, repeats=repeats, seed=seed)
    if profile == "contract-fuzz":
        return _contract_fuzz_suite(source, repeats=repeats, seed=seed)
    if profile == "tool-parser-repair":
        return _tool_parser_repair_suite(source, repeats=repeats, seed=seed)
    if profile == "metamorphic":
        return _metamorphic_suite(source, repeats=repeats, seed=seed)
    if profile == "cache-replay":
        return _cache_replay_suite(source, repeats=repeats, seed=seed)
    if profile == "cancellation":
        return _cancellation_suite(source, repeats=repeats, seed=seed)
    if profile == "orchestration":
        return _orchestration_suite(source, repeats=repeats, seed=seed)
    if profile == "skills":
        return _skills_suite(source, repeats=repeats, seed=seed)
    if profile == "emerging-workflows":
        return _emerging_workflows_suite(source, repeats=repeats, seed=seed)
    if profile == "judge-rubric":
        return _judge_rubric_suite(source, repeats=repeats, seed=seed)
    available = ", ".join(item.name for item in HARNESS_PROFILES)
    raise ConfigError(f"unknown harness profile: {profile}; available profiles: {available}")


def suite_to_yaml(suite: SuiteDefinition) -> str:
    return (
        yaml.safe_dump(
            suite.model_dump(mode="json", exclude_none=True),
            sort_keys=False,
            allow_unicode=False,
        )
        + "\n"
    )


def build_harness_review_report(suite: SuiteDefinition) -> dict[str, Any]:
    """Build a compact static review artifact for generated harness suites."""
    generated = suite.provenance.origin == "harness_generated" or bool(suite.provenance.generator)
    surface_counts = {
        "streaming_cases": sum(1 for case in suite.cases if case.streaming),
        "cancellation_cases": sum(1 for case in suite.cases if case.cancel_after_ms is not None),
        "tool_schema_cases": sum(1 for case in suite.cases if case.tools),
        "multi_tool_catalog_cases": sum(1 for case in suite.cases if len(case.tools) > 1),
        "expected_tool_cases": sum(1 for case in suite.cases if case.expected_tool_name),
        "tool_loop_cases": sum(1 for case in suite.cases if case.max_tool_calls and case.max_tool_calls > 1),
        "structured_output_cases": sum(1 for case in suite.cases if case.response_format or case.expected_json_fields),
        "simulated_tool_cases": sum(1 for case in suite.cases if case.simulated_tools),
        "mcp_profile_cases": sum(1 for case in suite.cases if case.mcp_profile),
        "lcp_profile_cases": sum(1 for case in suite.cases if case.lcp_profile),
        "skill_cases": sum(1 for case in suite.cases if case.skills),
        "message_trace_cases": sum(1 for case in suite.cases if case.messages),
        "cache_control_cases": sum(1 for case in suite.cases if case.cache_control),
        "tool_parser_repair_cases": sum(
            1 for case in suite.cases if "tool-parser-repair" in case.tags or "tool_parser_repair_required" in case.metrics
        ),
        "judge_rubric_cases": sum(1 for case in suite.cases if "judge-rubric" in case.tags),
    }
    assertion_counts = {
        "substring": sum(1 for case in suite.cases if case.expected_substring),
        "json_fields": sum(1 for case in suite.cases if case.expected_json_fields),
        "tool_name": sum(1 for case in suite.cases if case.expected_tool_name),
        "tool_result": sum(1 for case in suite.cases if case.expected_tool_result_substring),
    }
    high_risk_cases = [case.id for case in suite.cases if case.risk_level == "high"]
    review_status = "calibration-required" if generated else "review-recommended"
    return {
        "schema_version": HARNESS_REVIEW_SCHEMA_VERSION,
        "suite": {
            "name": suite.name,
            "description": suite.description,
            "suite_sha256": _suite_sha256(suite),
            "case_count": len(suite.cases),
        },
        "provenance": suite.provenance.model_dump(mode="json", exclude_none=True),
        "generated": generated,
        "generator": {
            "name": suite.provenance.generator,
            "profile": suite.provenance.generator_profile,
            "seed": suite.provenance.generator_seed,
            "repeats": suite.provenance.generator_repeats,
            "source_suite": suite.provenance.source_suite,
        },
        "surface_counts": surface_counts,
        "assertion_counts": assertion_counts,
        "metrics": sorted({metric for case in suite.cases for metric in case.metrics}),
        "tags": sorted({tag for case in suite.cases for tag in case.tags}),
        "risk": {
            "suite_origin": suite.provenance.origin,
            "suite_risk_labels": sorted(suite.provenance.risk_labels),
            "case_risk_levels": _value_counts(case.risk_level for case in suite.cases),
            "case_provenance": _value_counts(case.provenance for case in suite.cases),
            "high_risk_case_ids": high_risk_cases,
        },
        "review": {
            "status": review_status,
            "human_review_required": generated,
            "calibration_required_before_release_gate": generated,
            "recommended_next_steps": _harness_review_next_steps(generated=generated),
        },
        "case_inventory": [
            {
                "id": case.id,
                "title": case.title,
                "risk_level": case.risk_level,
                "provenance": case.provenance,
                "surfaces": _case_surfaces(case),
                "metrics": sorted(case.metrics),
                "tags": sorted(case.tags),
            }
            for case in suite.cases
        ],
        "safety": {
            "contacts_providers": False,
            "dispatches_requests": False,
            "resolves_secrets": False,
            "reads_keyring_values": False,
            "includes_prompts": False,
            "includes_raw_provider_payloads": False,
            "contains_api_keys": False,
        },
        "notes": [
            "Harness review is static and does not dispatch providers, resolve secrets, or inspect keyring values.",
            "Case prompts, messages, tool arguments, and raw provider payloads are intentionally excluded from this review artifact.",
        ],
    }


def format_harness_review_report(report: dict[str, Any]) -> str:
    lines = [
        "AgentBlaster harness review",
        f"suite: {report['suite']['name']}",
        f"generated: {str(report['generated']).lower()}",
        f"case_count: {report['suite']['case_count']}",
        f"review_status: {report['review']['status']}",
        "surface_counts:",
    ]
    for key, value in sorted(report["surface_counts"].items()):
        lines.append(f"- {key}: {value}")
    lines.append("assertion_counts:")
    for key, value in sorted(report["assertion_counts"].items()):
        lines.append(f"- {key}: {value}")
    lines.append("recommended_next_steps:")
    for step in report["review"]["recommended_next_steps"]:
        lines.append(f"- {step}")
    return "\n".join(lines) + "\n"


def _prefill_suite(source: SuiteDefinition, *, repeats: int, seed: int) -> SuiteDefinition:
    cases: list[BenchmarkCase] = []
    for source_index, case in enumerate(source.cases):
        for repeat_index in range(1, repeats + 1):
            block_count = 64 * repeat_index
            prefix = _prefill_block(seed=seed, source_index=source_index, repeat_index=repeat_index, block_count=block_count)
            cases.append(
                case.model_copy(
                    update={
                        "id": _case_id(case.id, "prefill", repeat_index),
                        "title": f"{case.title} / prefill x{block_count}",
                        "system_prompt": _join_prompt(case.system_prompt, prefix),
                        "metrics": _merge_unique(
                            case.metrics,
                            ["ttft_ms", "tokens_per_second_prefill", "cache_hit_ratio", "cached_input_tokens"],
                        ),
                        "tags": _merge_unique(case.tags, ["harness", "prefill", "cache", "synthetic"]),
                    },
                    deep=True,
                )
            )
    return SuiteDefinition(
        name=f"{source.name}-prefill-harness",
        description=f"Deterministic repeated-prefix harness generated from {source.name}.",
        provenance=_generated_provenance(source, profile="prefill", repeats=repeats, seed=seed),
        cases=cases,
    )


def _concurrency_suite(source: SuiteDefinition, *, repeats: int, seed: int) -> SuiteDefinition:
    cases: list[BenchmarkCase] = []
    for repeat_index in range(1, repeats + 1):
        for source_index, case in enumerate(source.cases):
            cases.append(
                case.model_copy(
                    update={
                        "id": _case_id(case.id, f"burst-{source_index + 1:02d}", repeat_index),
                        "title": f"{case.title} / concurrency burst {repeat_index}",
                        "metrics": _merge_unique(
                            case.metrics,
                            ["queue_ms", "rate_limit_wait_ms", "latency_ms", "requests_per_second"],
                        ),
                        "tags": _merge_unique(case.tags, ["harness", "concurrency", "burst", "synthetic"]),
                    },
                    deep=True,
                )
            )
    return SuiteDefinition(
        name=f"{source.name}-concurrency-harness",
        description=f"Deterministic concurrency burst harness generated from {source.name}.",
        provenance=_generated_provenance(source, profile="concurrency", repeats=repeats, seed=seed),
        cases=cases,
    )


def _skills_suite(source: SuiteDefinition, *, repeats: int, seed: int) -> SuiteDefinition:
    cases: list[BenchmarkCase] = []
    for source_index, case in enumerate(source.cases):
        for repeat_index in range(1, repeats + 1):
            skills = _skill_catalog(seed=seed, source_index=source_index, repeat_index=repeat_index)
            cases.append(
                case.model_copy(
                    update={
                        "id": _case_id(case.id, "skills", repeat_index),
                        "title": f"{case.title} / skill context {repeat_index}",
                        "system_prompt": _join_prompt(
                            case.system_prompt,
                            _skill_context_block(seed=seed, source_index=source_index, repeat_index=repeat_index, skills=skills),
                        ),
                        "skills": _merge_unique(case.skills, skills),
                        "metrics": _merge_unique(
                            case.metrics,
                            [
                                "ttft_ms",
                                "tokens_per_second_prefill",
                                "cached_input_tokens",
                                "skill_selection_valid",
                                "latency_ms",
                            ],
                        ),
                        "tags": _merge_unique(case.tags, ["harness", "skills", "skill-context", "synthetic"]),
                    },
                    deep=True,
                )
            )
    return SuiteDefinition(
        name=f"{source.name}-skills-harness",
        description=f"Deterministic skill-prefix and skill-selection harness generated from {source.name}.",
        provenance=_generated_provenance(source, profile="skills", repeats=repeats, seed=seed),
        cases=cases,
    )


def _cancellation_suite(source: SuiteDefinition, *, repeats: int, seed: int) -> SuiteDefinition:
    cases: list[BenchmarkCase] = []
    for source_index, case in enumerate(source.cases):
        for repeat_index in range(1, repeats + 1):
            cases.append(
                _cancellation_case(
                    case,
                    source_index=source_index,
                    repeat_index=repeat_index,
                    seed=seed,
                )
            )
    return SuiteDefinition(
        name=f"{source.name}-cancellation-harness",
        description=f"Deterministic streaming cancellation harness generated from {source.name}.",
        provenance=_generated_provenance(source, profile="cancellation", repeats=repeats, seed=seed),
        cases=cases,
    )


def _cancellation_case(
    case: BenchmarkCase,
    *,
    source_index: int,
    repeat_index: int,
    seed: int,
) -> BenchmarkCase:
    marker = f"agentblaster-cancel-{seed}-{source_index + 1}-{repeat_index}"
    cancel_after_ms = 100 * repeat_index
    return case.model_copy(
        update={
            "id": _case_id(case.id, "cancel", repeat_index),
            "title": f"{case.title} / cancellation abort {repeat_index}",
            "prompt": (
                f"Begin a streaming response containing marker {marker}, then continue with short numbered tokens "
                "until the benchmark harness cancels the stream. Do not stop voluntarily."
            ),
            "expected_substring": None,
            "expected_json_fields": {},
            "expected_tool_name": None,
            "response_format": None,
            "tools": [],
            "tool_choice": None,
            "simulated_tools": [],
            "streaming": True,
            "cancel_after_ms": cancel_after_ms,
            "max_tokens": max(case.max_tokens, 256),
            "timeout_seconds": max(case.timeout_seconds, 10.0),
            "metrics": _merge_unique(
                case.metrics,
                ["canceled", "cancellation_latency_ms", "ttft_ms", "latency_ms"],
            ),
            "tags": _merge_unique(case.tags, ["harness", "cancellation", "streaming", "synthetic"]),
        },
        deep=True,
    )


def _contract_fuzz_suite(source: SuiteDefinition, *, repeats: int, seed: int) -> SuiteDefinition:
    cases: list[BenchmarkCase] = []
    for source_index, case in enumerate(source.cases):
        for repeat_index in range(1, repeats + 1):
            cases.extend(
                [
                    _streaming_contract_case(case, source_index=source_index, repeat_index=repeat_index, seed=seed),
                    _structured_contract_case(case, source_index=source_index, repeat_index=repeat_index, seed=seed),
                    _tool_contract_case(case, source_index=source_index, repeat_index=repeat_index, seed=seed),
                ]
            )
    return SuiteDefinition(
        name=f"{source.name}-contract-fuzz-harness",
        description=f"Deterministic streaming, structured-output, and tool-call contract fuzz harness generated from {source.name}.",
        provenance=_generated_provenance(source, profile="contract-fuzz", repeats=repeats, seed=seed),
        cases=cases,
    )


def _tool_parser_repair_suite(source: SuiteDefinition, *, repeats: int, seed: int) -> SuiteDefinition:
    cases: list[BenchmarkCase] = []
    for source_index, case in enumerate(source.cases):
        for repeat_index in range(1, repeats + 1):
            cases.append(
                _tool_parser_repair_case(
                    case,
                    source_index=source_index,
                    repeat_index=repeat_index,
                    seed=seed,
                )
            )
    return SuiteDefinition(
        name=f"{source.name}-tool-parser-repair-harness",
        description=f"Deterministic raw-text tool-parser repair harness generated from {source.name}.",
        provenance=_generated_provenance(source, profile="tool-parser-repair", repeats=repeats, seed=seed),
        cases=cases,
    )


def _tool_parser_repair_case(
    case: BenchmarkCase,
    *,
    source_index: int,
    repeat_index: int,
    seed: int,
) -> BenchmarkCase:
    marker = f"agentblaster-parser-{seed}-{source_index + 1}-{repeat_index}"
    return case.model_copy(
        update={
            "id": _case_id(case.id, "tool-parser-repair", repeat_index),
            "title": f"{case.title} / tool parser repair {repeat_index}",
            "scenario": "tool parser repair",
            "system_prompt": (
                "Emit provider API-native tool calls only. Raw JSON, XML tags, markdown code fences, "
                "or ReAct-style Action/Input text are parser failures, not completed tool calls."
            ),
            "prompt": (
                f"Call ping_agentblaster with target set to {marker}. "
                "Do not answer in prose, raw JSON, XML, markdown, or ReAct syntax."
            ),
            "messages": [],
            "expected_substring": None,
            "expected_json_fields": {},
            "expected_tool_name": "ping_agentblaster",
            "response_format": None,
            "tools": [_ping_tool_schema()],
            "tool_choice": {"type": "function", "function": {"name": "ping_agentblaster"}},
            "previous_response_id": None,
            "max_tool_calls": 1,
            "simulated_tools": [],
            "expected_tool_result_substring": None,
            "mcp_profile": None,
            "lcp_profile": None,
            "skills": [],
            "cache_control": None,
            "streaming": False,
            "cancel_after_ms": None,
            "max_tokens": max(case.max_tokens, 64),
            "metrics": _merge_unique(
                case.metrics,
                [
                    "tool_calls_valid",
                    "tool_call_count",
                    "invalid_tool_call_count",
                    "tool_parser_repair_required",
                    "latency_ms",
                    "ttft_ms",
                ],
            ),
            "tags": _merge_unique(case.tags, ["harness", "tool-parser-repair", "api-native", "local-model", "synthetic"]),
        },
        deep=True,
    )


_METAMORPHIC_VARIANTS: tuple[str, ...] = ("framing", "format", "noise")


def _metamorphic_suite(source: SuiteDefinition, *, repeats: int, seed: int) -> SuiteDefinition:
    cases: list[BenchmarkCase] = []
    for source_index, case in enumerate(source.cases):
        for repeat_index in range(1, repeats + 1):
            cases.append(
                _metamorphic_case(
                    case,
                    source_index=source_index,
                    repeat_index=repeat_index,
                    seed=seed,
                )
            )
    return SuiteDefinition(
        name=f"{source.name}-metamorphic-harness",
        description=f"Deterministic metamorphic equivalence harness generated from {source.name}.",
        provenance=_generated_provenance(source, profile="metamorphic", repeats=repeats, seed=seed),
        cases=cases,
    )


def _metamorphic_case(
    case: BenchmarkCase,
    *,
    source_index: int,
    repeat_index: int,
    seed: int,
) -> BenchmarkCase:
    variant = _metamorphic_variant(repeat_index)
    return case.model_copy(
        update={
            "id": _case_id(case.id, f"metamorphic-{variant}", repeat_index),
            "title": f"{case.title} / metamorphic {variant} variant {repeat_index}",
            "prompt": _metamorphic_prompt(
                case.prompt,
                variant=variant,
                seed=seed,
                source_index=source_index,
                repeat_index=repeat_index,
            ),
            "metrics": _merge_unique(
                case.metrics,
                ["latency_ms", "structured_output_valid", "tool_call_count"],
            ),
            "tags": _merge_unique(case.tags, ["harness", "metamorphic", "equivalence", "synthetic"]),
        },
        deep=True,
    )


def _metamorphic_variant(repeat_index: int) -> str:
    return _METAMORPHIC_VARIANTS[(repeat_index - 1) % len(_METAMORPHIC_VARIANTS)]


def _metamorphic_prompt(
    prompt: str,
    *,
    variant: str,
    seed: int,
    source_index: int,
    repeat_index: int,
) -> str:
    source_prompt = prompt or "Use the original benchmark case messages and tool context as the authoritative task."
    marker = f"Metamorphic equivalence check seed={seed} source={source_index + 1} repeat={repeat_index}."
    if variant == "framing":
        instruction = "The source task below is authoritative. Satisfy it exactly, including exact-output, schema, or tool-call constraints."
        return f"{marker}\n{instruction}\n\n{source_prompt}"
    if variant == "format":
        instruction = "Keep the same final answer content and output format requested by the source task. Do not add commentary."
        return f"{marker}\n{instruction}\n\nSource task:\n{source_prompt}"
    instruction = "Treat the following harmless wrapper text as non-semantic noise. Complete the source task exactly as written."
    return f"{marker}\n{instruction}\n\n--- source task begins ---\n{source_prompt}\n--- source task ends ---"


def _streaming_contract_case(
    case: BenchmarkCase,
    *,
    source_index: int,
    repeat_index: int,
    seed: int,
) -> BenchmarkCase:
    marker = f"agentblaster-stream-{seed}-{source_index + 1}-{repeat_index}"
    return case.model_copy(
        update={
            "id": _case_id(case.id, "stream-contract", repeat_index),
            "title": f"{case.title} / streaming contract fuzz {repeat_index}",
            "prompt": f"Stream a concise response containing exactly this marker: {marker}",
            "expected_substring": marker,
            "streaming": True,
            "max_tokens": max(case.max_tokens, 24),
            "metrics": _merge_unique(case.metrics, ["ttft_ms", "latency_ms", "tokens_per_second_decode"]),
            "tags": _merge_unique(case.tags, ["harness", "contract-fuzz", "streaming", "synthetic"]),
        },
        deep=True,
    )


def _structured_contract_case(
    case: BenchmarkCase,
    *,
    source_index: int,
    repeat_index: int,
    seed: int,
) -> BenchmarkCase:
    marker = f"agentblaster-json-{seed}-{source_index + 1}-{repeat_index}"
    expected = {"status": "agentblaster-ok", "marker": marker}
    return case.model_copy(
        update={
            "id": _case_id(case.id, "json-contract", repeat_index),
            "title": f"{case.title} / structured-output contract fuzz {repeat_index}",
            "system_prompt": "Return only valid JSON. Do not wrap the JSON in markdown.",
            "prompt": f"Return exactly this JSON object: {json.dumps(expected, sort_keys=True)}",
            "expected_substring": None,
            "expected_json_fields": expected,
            "response_format": {"type": "json_object"},
            "tools": [],
            "tool_choice": None,
            "max_tokens": max(case.max_tokens, 64),
            "metrics": _merge_unique(case.metrics, ["structured_output_valid", "latency_ms"]),
            "tags": _merge_unique(case.tags, ["harness", "contract-fuzz", "structured", "json", "synthetic"]),
        },
        deep=True,
    )


def _tool_contract_case(
    case: BenchmarkCase,
    *,
    source_index: int,
    repeat_index: int,
    seed: int,
) -> BenchmarkCase:
    marker = f"agentblaster-tool-{seed}-{source_index + 1}-{repeat_index}"
    return case.model_copy(
        update={
            "id": _case_id(case.id, "tool-contract", repeat_index),
            "title": f"{case.title} / tool-call contract fuzz {repeat_index}",
            "prompt": f"Call ping_agentblaster with target set to {marker}.",
            "expected_substring": None,
            "expected_json_fields": {},
            "expected_tool_name": "ping_agentblaster",
            "tools": [_ping_tool_schema()],
            "tool_choice": {"type": "function", "function": {"name": "ping_agentblaster"}},
            "max_tokens": max(case.max_tokens, 64),
            "metrics": _merge_unique(case.metrics, ["tool_call_count", "invalid_tool_call_count", "latency_ms"]),
            "tags": _merge_unique(case.tags, ["harness", "contract-fuzz", "toolcall", "synthetic"]),
        },
        deep=True,
    )


def _orchestration_suite(source: SuiteDefinition, *, repeats: int, seed: int) -> SuiteDefinition:
    cases: list[BenchmarkCase] = []
    for source_index, case in enumerate(source.cases):
        for repeat_index in range(1, repeats + 1):
            cases.append(
                _orchestration_case(
                    case,
                    source_index=source_index,
                    repeat_index=repeat_index,
                    seed=seed,
                )
            )
    return SuiteDefinition(
        name=f"{source.name}-orchestration-harness",
        description=f"Deterministic multi-tool orchestration harness generated from {source.name}.",
        provenance=_generated_provenance(source, profile="orchestration", repeats=repeats, seed=seed),
        cases=cases,
    )


def _orchestration_case(
    case: BenchmarkCase,
    *,
    source_index: int,
    repeat_index: int,
    seed: int,
) -> BenchmarkCase:
    marker = f"agentblaster-route-{seed}-{source_index + 1}-{repeat_index}"
    return case.model_copy(
        update={
            "id": _case_id(case.id, "orchestration", repeat_index),
            "title": f"{case.title} / tool orchestration {repeat_index}",
            "prompt": (
                f"Use the route_agentblaster_task tool with route_id set to {marker}. "
                "Ignore distractor tools unless they are necessary. After the tool call, provide a concise final answer."
            ),
            "expected_substring": None,
            "expected_json_fields": {},
            "expected_tool_name": "route_agentblaster_task",
            "tools": _orchestration_tool_schemas(),
            "tool_choice": "auto",
            "max_tool_calls": max(case.max_tool_calls or 1, 2),
            "max_tokens": max(case.max_tokens, 96),
            "metrics": _merge_unique(
                case.metrics,
                ["tool_call_count", "invalid_tool_call_count", "latency_ms", "ttft_ms"],
            ),
            "tags": _merge_unique(case.tags, ["harness", "orchestration", "tool-routing", "synthetic"]),
        },
        deep=True,
    )


def _orchestration_tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "route_agentblaster_task",
                "description": "Select the deterministic route for an AgentBlaster orchestration workload.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "route_id": {"type": "string", "description": "Required route marker."},
                        "confidence": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                            "description": "Routing confidence.",
                        },
                    },
                    "required": ["route_id"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_agentblaster_notes",
                "description": "Distractor search tool for benchmark note lookup.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "fetch_agentblaster_context",
                "description": "Distractor context retrieval tool for local-agent planning.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "context_id": {"type": "string"},
                    },
                    "required": ["context_id"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "finalize_agentblaster_plan",
                "description": "Distractor finalization tool for multi-step agent planning.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                    },
                    "required": ["summary"],
                    "additionalProperties": False,
                },
            },
        },
    ]


def _emerging_workflows_suite(source: SuiteDefinition, *, repeats: int, seed: int) -> SuiteDefinition:
    cases: list[BenchmarkCase] = []
    for source_index, case in enumerate(source.cases):
        for repeat_index in range(1, repeats + 1):
            cases.append(
                _emerging_workflow_case(
                    case,
                    source_index=source_index,
                    repeat_index=repeat_index,
                    seed=seed,
                )
            )
    return SuiteDefinition(
        name=f"{source.name}-emerging-workflows-harness",
        description=(
            "Deterministic mixed MCP/LCP/skills/tool-loop/cache harness generated "
            f"from {source.name}."
        ),
        provenance=_generated_provenance(source, profile="emerging-workflows", repeats=repeats, seed=seed),
        cases=cases,
    )


def _emerging_workflow_case(
    case: BenchmarkCase,
    *,
    source_index: int,
    repeat_index: int,
    seed: int,
) -> BenchmarkCase:
    marker = f"agentblaster-emerging-{seed}-{source_index + 1}-{repeat_index}"
    skills = _skill_catalog(seed=seed, source_index=source_index, repeat_index=repeat_index)
    mcp_profile = "wide-mcp-32" if repeat_index % 2 == 0 else "fixture-mcp"
    lcp_profile = "wide-lcp-context" if repeat_index % 2 == 0 else "fixture-lcp"
    return case.model_copy(
        update={
            "id": _case_id(case.id, "emerging-workflows", repeat_index),
            "title": f"{case.title} / emerging workflow stack {repeat_index}",
            "system_prompt": _join_prompt(
                case.system_prompt,
                _emerging_workflow_context_block(
                    seed=seed,
                    source_index=source_index,
                    repeat_index=repeat_index,
                    skills=skills,
                    mcp_profile=mcp_profile,
                    lcp_profile=lcp_profile,
                ),
            ),
            "prompt": (
                f"Use the available MCP/LCP/skill context to route marker {marker} through "
                "route_agentblaster_task, then provide a concise final answer. "
                "Do not invent unavailable tools, context bundles, or skills."
            ),
            "expected_substring": None,
            "expected_json_fields": {},
            "expected_tool_name": "route_agentblaster_task",
            "tools": _orchestration_tool_schemas(),
            "tool_choice": "auto",
            "simulated_tools": _merge_unique(case.simulated_tools, ["search_docs"]),
            "mcp_profile": mcp_profile,
            "lcp_profile": lcp_profile,
            "skills": _merge_unique(case.skills, skills),
            "cache_control": case.cache_control or {"type": "ephemeral"},
            "max_tool_calls": max(case.max_tool_calls or 1, 3),
            "max_tokens": max(case.max_tokens, 128),
            "metrics": _merge_unique(
                case.metrics,
                [
                    "ttft_ms",
                    "tokens_per_second_prefill",
                    "cached_input_tokens",
                    "cache_hit_ratio",
                    "tool_call_count",
                    "invalid_tool_call_count",
                    "mcp_profile_applied",
                    "lcp_context_applied",
                    "skill_selection_valid",
                    "latency_ms",
                ],
            ),
            "tags": _merge_unique(
                case.tags,
                [
                    "harness",
                    "emerging-workflows",
                    "mcp",
                    "lcp",
                    "skills",
                    "tool-loop",
                    "cache",
                    "prefill",
                    "synthetic",
                ],
            ),
        },
        deep=True,
    )


def _emerging_workflow_context_block(
    *,
    seed: int,
    source_index: int,
    repeat_index: int,
    skills: list[str],
    mcp_profile: str,
    lcp_profile: str,
) -> str:
    skill_lines = "\n".join(f"- {skill}: available local-agent skill fixture." for skill in skills)
    static_line = (
        f"AgentBlaster emerging workflow stack seed={seed} source={source_index + 1} "
        f"repeat={repeat_index} mcp={mcp_profile} lcp={lcp_profile}."
    )
    return (
        "\n".join(static_line for _ in range(48))
        + "\n"
        "Use only declared fixture surfaces. MCP and LCP content is deterministic benchmark context, not host access.\n"
        "Available skill fixtures:\n"
        f"{skill_lines}"
    )


def _judge_rubric_suite(source: SuiteDefinition, *, repeats: int, seed: int) -> SuiteDefinition:
    cases: list[BenchmarkCase] = []
    for source_index, case in enumerate(source.cases):
        for repeat_index in range(1, repeats + 1):
            cases.append(
                _judge_rubric_case(
                    case,
                    source_index=source_index,
                    repeat_index=repeat_index,
                    seed=seed,
                )
            )
    return SuiteDefinition(
        name=f"{source.name}-judge-rubric-harness",
        description=f"Deterministic model-judge rubric harness generated from {source.name}.",
        provenance=_generated_provenance(source, profile="judge-rubric", repeats=repeats, seed=seed),
        cases=cases,
    )


def _judge_rubric_case(
    case: BenchmarkCase,
    *,
    source_index: int,
    repeat_index: int,
    seed: int,
) -> BenchmarkCase:
    rationale_code = f"agentblaster-judge-{seed}-{source_index + 1}-{repeat_index}"
    candidate_answer = _judge_candidate_answer(case)
    expected = {
        "verdict": "pass",
        "score": 1,
        "rationale_code": rationale_code,
        "source_case_id": case.id,
    }
    return case.model_copy(
        update={
            "id": _case_id(case.id, "judge-rubric", repeat_index),
            "title": f"{case.title} / judge rubric {repeat_index}",
            "scenario": "model judge rubric",
            "system_prompt": (
                "You are an AgentBlaster deterministic benchmark judge. "
                "Return only valid JSON matching the requested schema. "
                "Do not solve the original task and do not include chain-of-thought."
            ),
            "prompt": _judge_rubric_prompt(
                case,
                candidate_answer=candidate_answer,
                rationale_code=rationale_code,
                seed=seed,
                source_index=source_index,
                repeat_index=repeat_index,
            ),
            "messages": [],
            "expected_substring": None,
            "expected_json_fields": expected,
            "expected_tool_name": None,
            "response_format": _judge_rubric_response_format(expected),
            "tools": [],
            "tool_choice": None,
            "previous_response_id": None,
            "max_tool_calls": None,
            "simulated_tools": [],
            "expected_tool_result_substring": None,
            "mcp_profile": None,
            "lcp_profile": None,
            "skills": [],
            "cache_control": None,
            "streaming": False,
            "cancel_after_ms": None,
            "max_tokens": max(case.max_tokens, 128),
            "temperature": 0.0,
            "metrics": _merge_unique(
                case.metrics,
                ["structured_output_valid", "judge_verdict_valid", "latency_ms", "ttft_ms"],
            ),
            "tags": _merge_unique(case.tags, ["harness", "judge-rubric", "model-judge", "structured", "synthetic"]),
        },
        deep=True,
    )


def _judge_candidate_answer(case: BenchmarkCase) -> str:
    if case.expected_substring:
        return case.expected_substring
    if case.expected_json_fields:
        return json.dumps(case.expected_json_fields, sort_keys=True)
    if case.expected_tool_name:
        return f"called tool {case.expected_tool_name}"
    return "source assertion satisfied"


def _judge_rubric_prompt(
    case: BenchmarkCase,
    *,
    candidate_answer: str,
    rationale_code: str,
    seed: int,
    source_index: int,
    repeat_index: int,
) -> str:
    return (
        f"Judge fixture seed={seed} source={source_index + 1} repeat={repeat_index}.\n"
        "Evaluate the fixed candidate answer for benchmark-calibration purposes. "
        "Do not answer the original task.\n\n"
        f"Source case id: {case.id}\n"
        f"Original task:\n{case.prompt}\n\n"
        f"Candidate answer:\n{candidate_answer}\n\n"
        "Rubric:\n"
        "- verdict must be pass because the candidate answer satisfies the source-case assertion.\n"
        "- score must be 1 for pass.\n"
        f"- rationale_code must be {rationale_code}.\n"
        f"- source_case_id must be {case.id}.\n\n"
        "Return exactly one JSON object with keys verdict, score, rationale_code, and source_case_id."
    )


def _judge_rubric_response_format(expected: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "agentblaster_judge_rubric",
            "strict": True,
            "schema": {
                "type": "object",
                "required": ["verdict", "score", "rationale_code", "source_case_id"],
                "additionalProperties": False,
                "properties": {
                    "verdict": {"type": "string", "const": expected["verdict"]},
                    "score": {"type": "integer", "const": expected["score"]},
                    "rationale_code": {"type": "string", "const": expected["rationale_code"]},
                    "source_case_id": {"type": "string", "const": expected["source_case_id"]},
                },
            },
        },
    }


def _prefill_block(*, seed: int, source_index: int, repeat_index: int, block_count: int) -> str:
    line = (
        f"AgentBlaster deterministic prefill block seed={seed} "
        f"source={source_index + 1} repeat={repeat_index}. Preserve the final task exactly."
    )
    return "\n".join(line for _ in range(block_count))


def _skill_catalog(*, seed: int, source_index: int, repeat_index: int) -> list[str]:
    offset = (seed + source_index + repeat_index) % len(_SKILL_CATALOG)
    ordered = list(_SKILL_CATALOG[offset:] + _SKILL_CATALOG[:offset])
    width = min(len(ordered), 2 + (repeat_index % 3))
    return ordered[:width]


def _skill_context_block(*, seed: int, source_index: int, repeat_index: int, skills: list[str]) -> str:
    skill_lines = "\n".join(f"- {skill}: deterministic AgentBlaster skill fixture." for skill in skills)
    return (
        f"AgentBlaster deterministic skill context seed={seed} source={source_index + 1} repeat={repeat_index}.\n"
        "Select only the relevant local-agent skill fixtures. Do not invent unavailable skills.\n"
        "Available skill fixtures:\n"
        f"{skill_lines}"
    )


def _ping_tool_schema() -> dict[str, Any]:
    return {
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


def _case_id(base: str, profile: str, repeat_index: int) -> str:
    return f"{base}-{profile}-{repeat_index:02d}"[:96]


def _join_prompt(first: str | None, second: str) -> str:
    if not first:
        return second
    return f"{first.rstrip()}\n\n{second}"



def _cache_replay_suite(source: SuiteDefinition, *, repeats: int, seed: int) -> SuiteDefinition:
    cases: list[BenchmarkCase] = []
    for repeat_index in range(1, repeats + 1):
        for source_index, case in enumerate(source.cases, start=1):
            for phase in _CACHE_REPLAY_PHASES:
                cases.append(
                    _cache_replay_case(
                        case,
                        source_index=source_index,
                        repeat_index=repeat_index,
                        seed=seed,
                        phase=phase,
                    )
                )

    return SuiteDefinition(
        name=f"{source.name}-cache-replay-harness",
        description=(
            "Generated cache replay harness with warmup, identical replay, "
            "suffix mutation, and static-prefix invalidation phases."
        ),
        cases=cases,
        provenance=_generated_provenance(source, profile="cache-replay", repeats=repeats, seed=seed),
    )


def _cache_replay_case(
    case: BenchmarkCase,
    *,
    source_index: int,
    repeat_index: int,
    seed: int,
    phase: str,
) -> BenchmarkCase:
    static_prefix = _cache_replay_prefix(seed=seed, source_index=source_index, repeat_index=repeat_index)
    system_prompt = _cache_replay_join(case.system_prompt, static_prefix)
    prompt = case.prompt

    if phase == "suffix":
        prompt = _cache_replay_join(
            prompt,
            (
                f"Cache replay suffix mutation seed={seed} source={source_index} repeat={repeat_index}: "
                "preserve the requested final answer and output format."
            ),
        )
    elif phase == "invalidate":
        system_prompt = _cache_replay_join(
            system_prompt,
            f"AgentBlaster cache invalidation salt seed={seed} source={source_index} repeat={repeat_index}.",
        )

    tags = _merge_unique(case.tags, (*_CACHE_REPLAY_TAGS, phase))
    metrics = _merge_unique(case.metrics, _CACHE_REPLAY_METRICS)

    return case.model_copy(
        update={
            "id": f"{case.id}-cache-{phase}-{repeat_index:02d}",
            "title": f"{case.title} / cache replay {phase} {repeat_index}",
            "system_prompt": system_prompt,
            "prompt": prompt,
            "tags": tags,
            "metrics": metrics,
            "cache_control": case.cache_control or {"type": "ephemeral"},
        },
        deep=True,
    )


def _cache_replay_prefix(*, seed: int, source_index: int, repeat_index: int) -> str:
    line = (
        f"AgentBlaster cache replay static prefix seed={seed} source={source_index} repeat={repeat_index}. "
        "Keep this prefix stable across warmup, replay, and suffix-mutation phases."
    )
    return "\n".join(line for _ in range(96))


def _cache_replay_join(left: str | None, right: str) -> str:
    if left:
        return f"{left.rstrip()}\n\n{right.lstrip()}"
    return right


def _suite_sha256(suite: SuiteDefinition) -> str:
    payload = suite.model_dump(mode="json", exclude_none=True)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _value_counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _case_surfaces(case: BenchmarkCase) -> list[str]:
    surfaces: list[str] = []
    if case.streaming:
        surfaces.append("streaming")
    if case.cancel_after_ms is not None:
        surfaces.append("cancellation")
    if case.tools:
        surfaces.append("tool_schema")
    if case.expected_tool_name:
        surfaces.append("expected_tool")
    if case.response_format or case.expected_json_fields:
        surfaces.append("structured_output")
    if case.simulated_tools:
        surfaces.append("simulated_tools")
    if case.mcp_profile:
        surfaces.append("mcp_profile")
    if case.lcp_profile:
        surfaces.append("lcp_profile")
    if case.skills:
        surfaces.append("skills")
    if case.messages:
        surfaces.append("message_trace")
    if case.cache_control:
        surfaces.append("cache_control")
    return surfaces


def _harness_review_next_steps(*, generated: bool) -> list[str]:
    if generated:
        return [
            "Inspect the generated YAML before dispatch.",
            "Create and complete a suite-calibration manifest before using this suite as a release gate.",
            "Run dry-run planning against target providers before any executed benchmark run.",
        ]
    return [
        "Review capability surfaces and provenance before dispatch.",
        "Use suite-calibration when promoting this suite to release-gate evidence.",
    ]


def _merge_unique(base: list[str], additions: list[str]) -> list[str]:
    values = list(base)
    for item in additions:
        if item not in values:
            values.append(item)
    return values


def _generated_provenance(source: SuiteDefinition, *, profile: str, repeats: int, seed: int) -> SuiteProvenance:
    risk_labels = _merge_unique(source.provenance.risk_labels, ["synthetic", "harness-generated"])
    notes = _merge_unique(
        source.provenance.notes,
        [
            f"Generated by AgentBlaster harness profile {profile}.",
            "Review generated cases before using them as public benchmark claims.",
        ],
    )
    return SuiteProvenance(
        origin="harness_generated",
        source_suite=source.name,
        generator="agentblaster.harness",
        generator_profile=profile,
        generator_seed=seed,
        generator_repeats=repeats,
        primary_source=source.provenance.primary_source or source.name,
        source_url=source.provenance.source_url,
        license=source.provenance.license,
        risk_labels=risk_labels,
        notes=notes,
    )
