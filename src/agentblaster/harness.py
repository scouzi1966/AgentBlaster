from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import yaml

from agentblaster.errors import ConfigError
from agentblaster.models import BenchmarkCase, SuiteDefinition, SuiteProvenance


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
        name="metamorphic",
        purpose="Generate equivalent wording and formatting variants to test agent stability under harmless prompt changes.",
    ),
    HarnessProfile(
        name="cache-replay",
        purpose="Generate warmup, replay, suffix-mutation, and prefix-invalidation variants for prompt-cache diagnostics.",
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
    if profile == "metamorphic":
        return _metamorphic_suite(source, repeats=repeats, seed=seed)
    if profile == "cache-replay":
        return _cache_replay_suite(source, repeats=repeats, seed=seed)
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


def _prefill_block(*, seed: int, source_index: int, repeat_index: int, block_count: int) -> str:
    line = (
        f"AgentBlaster deterministic prefill block seed={seed} "
        f"source={source_index + 1} repeat={repeat_index}. Preserve the final task exactly."
    )
    return "\n".join(line for _ in range(block_count))


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



def _cache_replay_suite(source: BenchmarkSuite, *, repeats: int, seed: int) -> BenchmarkSuite:
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

    return BenchmarkSuite(
        name=f"{source.name}-cache-replay-harness",
        description=(
            "Generated cache replay harness with warmup, identical replay, "
            "suffix mutation, and static-prefix invalidation phases."
        ),
        cases=cases,
        provenance=_generated_provenance(source, "cache-replay", repeats=repeats, seed=seed),
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
