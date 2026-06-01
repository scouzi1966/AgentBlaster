from __future__ import annotations

import pytest

from agentblaster.errors import ConfigError
from agentblaster.harness import generate_harness_suite, list_harness_profiles, suite_to_yaml
from agentblaster.models import BenchmarkCase, SuiteDefinition


def test_harness_profiles_include_emerging_generation_lanes() -> None:
    profiles = {profile.name for profile in list_harness_profiles()}

    assert {"prefill", "concurrency", "contract-fuzz", "metamorphic", "cache-replay"} <= profiles


def test_prefill_harness_adds_repeated_prefix_metrics_and_tags() -> None:
    suite = generate_harness_suite(_source_suite(), profile="prefill", repeats=2, seed=11)

    assert suite.name == "source-prefill-harness"
    assert suite.provenance.origin == "harness_generated"
    assert suite.provenance.source_suite == "source"
    assert suite.provenance.generator_profile == "prefill"
    assert suite.provenance.generator_seed == 11
    assert suite.provenance.generator_repeats == 2
    assert "harness-generated" in suite.provenance.risk_labels
    assert len(suite.cases) == 2
    assert suite.cases[0].id == "case-one-prefill-01"
    assert "AgentBlaster deterministic prefill block seed=11" in str(suite.cases[0].system_prompt)
    assert "tokens_per_second_prefill" in suite.cases[0].metrics
    assert "cache_hit_ratio" in suite.cases[0].metrics
    assert "prefill" in suite.cases[0].tags


def test_concurrency_harness_clones_semantically_identical_cases() -> None:
    source = _source_suite()
    suite = generate_harness_suite(source, profile="concurrency", repeats=3, seed=99)

    assert len(suite.cases) == 3
    assert [case.id for case in suite.cases] == [
        "case-one-burst-01-01",
        "case-one-burst-01-02",
        "case-one-burst-01-03",
    ]
    assert all(case.prompt == source.cases[0].prompt for case in suite.cases)
    assert all("queue_ms" in case.metrics for case in suite.cases)
    assert all("concurrency" in case.tags for case in suite.cases)


def test_contract_fuzz_harness_generates_stream_json_and_tool_cases() -> None:
    suite = generate_harness_suite(_source_suite(), profile="contract-fuzz", repeats=1, seed=7)

    assert [case.id for case in suite.cases] == [
        "case-one-stream-contract-01",
        "case-one-json-contract-01",
        "case-one-tool-contract-01",
    ]
    assert suite.cases[0].streaming is True
    assert suite.cases[0].expected_substring == "agentblaster-stream-7-1-1"
    assert suite.cases[1].response_format == {"type": "json_object"}
    assert suite.cases[1].expected_json_fields["marker"] == "agentblaster-json-7-1-1"
    assert suite.cases[2].expected_tool_name == "ping_agentblaster"
    assert suite.cases[2].tools[0]["function"]["name"] == "ping_agentblaster"


def test_metamorphic_harness_preserves_assertions_and_adds_equivalence_variants() -> None:
    source = _source_suite()
    suite = generate_harness_suite(source, profile="metamorphic", repeats=2, seed=13)

    assert suite.name == "source-metamorphic-harness"
    assert suite.provenance.origin == "harness_generated"
    assert suite.provenance.generator_profile == "metamorphic"
    assert suite.provenance.generator_seed == 13
    assert suite.provenance.generator_repeats == 2
    assert [case.id for case in suite.cases] == [
        "case-one-metamorphic-framing-01",
        "case-one-metamorphic-format-02",
    ]
    assert all(case.expected_substring == "agentblaster-ok" for case in suite.cases)
    assert all("Reply with exactly: agentblaster-ok" in case.prompt for case in suite.cases)
    assert all("metamorphic" in case.tags for case in suite.cases)
    assert all("equivalence" in case.tags for case in suite.cases)
    assert all("latency_ms" in case.metrics for case in suite.cases)
    assert "The source task below is authoritative" in suite.cases[0].prompt
    assert "same final answer content and output format" in suite.cases[1].prompt


def test_harness_suite_serializes_to_valid_yaml_shape() -> None:
    suite = generate_harness_suite(_source_suite(), profile="contract-fuzz", repeats=1, seed=3)
    text = suite_to_yaml(suite)

    assert "name: source-contract-fuzz-harness" in text
    assert "provenance:" in text
    assert "origin: harness_generated" in text
    assert "case-one-stream-contract-01" in text
    assert "response_format:" in text


def test_harness_generation_rejects_unknown_profile_and_invalid_repeats() -> None:
    with pytest.raises(ConfigError, match="unknown harness profile"):
        generate_harness_suite(_source_suite(), profile="unknown")

    with pytest.raises(ConfigError, match="repeats"):
        generate_harness_suite(_source_suite(), profile="prefill", repeats=0)


def _source_suite() -> SuiteDefinition:
    return SuiteDefinition(
        name="source",
        description="Source suite",
        cases=[
            BenchmarkCase(
                id="case-one",
                title="Case one",
                prompt="Reply with exactly: agentblaster-ok",
                expected_substring="agentblaster-ok",
                max_tokens=16,
                tags=["source"],
            )
        ],
    )

def test_cache_replay_harness_generates_warmup_replay_suffix_and_invalidation_cases() -> None:
    suite = generate_harness_suite(_source_suite(), profile="cache-replay", repeats=1, seed=5)

    assert suite.name == "source-cache-replay-harness"
    assert suite.provenance.generator_profile == "cache-replay"
    assert [case.id for case in suite.cases] == [
        "case-one-cache-warmup-01",
        "case-one-cache-replay-01",
        "case-one-cache-suffix-01",
        "case-one-cache-invalidate-01",
    ]
    assert all(case.cache_control == {"type": "ephemeral"} for case in suite.cases)
    assert suite.cases[0].system_prompt == suite.cases[1].system_prompt
    assert suite.cases[2].system_prompt == suite.cases[0].system_prompt
    assert suite.cases[3].system_prompt != suite.cases[0].system_prompt
    assert suite.cases[0].prompt == suite.cases[1].prompt
    assert "suffix mutation" in suite.cases[2].prompt
    assert all("cache-replay" in case.tags for case in suite.cases)
    assert all("cache_hit_ratio" in case.metrics for case in suite.cases)

