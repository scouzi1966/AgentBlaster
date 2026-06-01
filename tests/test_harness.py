from __future__ import annotations

import pytest

from agentblaster.errors import ConfigError
from agentblaster.harness import build_harness_review_report, format_harness_review_report, generate_harness_suite, list_harness_profiles, suite_to_yaml
from agentblaster.models import BenchmarkCase, SuiteDefinition


def test_harness_profiles_include_emerging_generation_lanes() -> None:
    profiles = {profile.name for profile in list_harness_profiles()}

    assert {
        "prefill",
        "concurrency",
        "contract-fuzz",
        "tool-parser-repair",
        "metamorphic",
        "cache-replay",
        "cancellation",
        "orchestration",
        "skills",
        "emerging-workflows",
        "judge-rubric",
    } <= profiles


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


def test_skills_harness_adds_skill_prefix_catalog_and_selection_metrics() -> None:
    suite = generate_harness_suite(_source_suite(), profile="skills", repeats=2, seed=23)
    report = build_harness_review_report(suite)

    assert suite.name == "source-skills-harness"
    assert suite.provenance.origin == "harness_generated"
    assert suite.provenance.generator_profile == "skills"
    assert [case.id for case in suite.cases] == [
        "case-one-skills-01",
        "case-one-skills-02",
    ]
    assert all(case.system_prompt and "AgentBlaster deterministic skill context seed=23" in case.system_prompt for case in suite.cases)
    assert all(case.skills for case in suite.cases)
    assert all("skill_selection_valid" in case.metrics for case in suite.cases)
    assert all("tokens_per_second_prefill" in case.metrics for case in suite.cases)
    assert all("skills" in case.tags for case in suite.cases)
    assert report["surface_counts"]["skill_cases"] == 2
    assert "skill_selection_valid" in report["metrics"]


def test_cancellation_harness_generates_stream_abort_cases() -> None:
    suite = generate_harness_suite(_source_suite(), profile="cancellation", repeats=2, seed=17)

    assert suite.name == "source-cancellation-harness"
    assert suite.provenance.origin == "harness_generated"
    assert suite.provenance.generator_profile == "cancellation"
    assert suite.provenance.generator_seed == 17
    assert suite.provenance.generator_repeats == 2
    assert [case.id for case in suite.cases] == [
        "case-one-cancel-01",
        "case-one-cancel-02",
    ]
    assert all(case.streaming is True for case in suite.cases)
    assert [case.cancel_after_ms for case in suite.cases] == [100, 200]
    assert all(case.expected_substring is None for case in suite.cases)
    assert all("canceled" in case.metrics for case in suite.cases)
    assert all("cancellation_latency_ms" in case.metrics for case in suite.cases)
    assert all("cancellation" in case.tags for case in suite.cases)
    assert "agentblaster-cancel-17-1-1" in suite.cases[0].prompt


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


def test_tool_parser_repair_harness_generates_api_native_tool_cases() -> None:
    suite = generate_harness_suite(_source_suite(), profile="tool-parser-repair", repeats=2, seed=41)
    report = build_harness_review_report(suite)

    assert suite.name == "source-tool-parser-repair-harness"
    assert suite.provenance.generator_profile == "tool-parser-repair"
    assert [case.id for case in suite.cases] == [
        "case-one-tool-parser-repair-01",
        "case-one-tool-parser-repair-02",
    ]
    assert all(case.scenario == "tool parser repair" for case in suite.cases)
    assert all(case.expected_tool_name == "ping_agentblaster" for case in suite.cases)
    assert all(case.tool_choice == {"type": "function", "function": {"name": "ping_agentblaster"}} for case in suite.cases)
    assert all("tool_parser_repair_required" in case.metrics for case in suite.cases)
    assert all("invalid_tool_call_count" in case.metrics for case in suite.cases)
    assert all("tool-parser-repair" in case.tags for case in suite.cases)
    assert "agentblaster-parser-41-1-1" in suite.cases[0].prompt
    assert report["surface_counts"]["expected_tool_cases"] == 2
    assert report["surface_counts"]["tool_schema_cases"] == 2
    assert report["surface_counts"]["tool_parser_repair_cases"] == 2


def test_orchestration_harness_generates_multi_tool_routing_cases() -> None:
    suite = generate_harness_suite(_source_suite(), profile="orchestration", repeats=2, seed=19)

    assert suite.name == "source-orchestration-harness"
    assert suite.provenance.generator_profile == "orchestration"
    assert [case.id for case in suite.cases] == [
        "case-one-orchestration-01",
        "case-one-orchestration-02",
    ]
    assert all(case.expected_tool_name == "route_agentblaster_task" for case in suite.cases)
    assert all(len(case.tools) == 4 for case in suite.cases)
    assert all(case.max_tool_calls == 2 for case in suite.cases)
    assert all("orchestration" in case.tags for case in suite.cases)
    assert all("tool_call_count" in case.metrics for case in suite.cases)
    assert "agentblaster-route-19-1-1" in suite.cases[0].prompt


def test_emerging_workflows_harness_combines_mcp_lcp_skills_tools_and_cache() -> None:
    suite = generate_harness_suite(_source_suite(), profile="emerging-workflows", repeats=2, seed=37)
    report = build_harness_review_report(suite)

    assert suite.name == "source-emerging-workflows-harness"
    assert suite.provenance.generator_profile == "emerging-workflows"
    assert [case.id for case in suite.cases] == [
        "case-one-emerging-workflows-01",
        "case-one-emerging-workflows-02",
    ]
    assert suite.cases[0].mcp_profile == "fixture-mcp"
    assert suite.cases[0].lcp_profile == "fixture-lcp"
    assert suite.cases[1].mcp_profile == "wide-mcp-32"
    assert suite.cases[1].lcp_profile == "wide-lcp-context"
    assert all(case.expected_tool_name == "route_agentblaster_task" for case in suite.cases)
    assert all(case.cache_control == {"type": "ephemeral"} for case in suite.cases)
    assert all(case.skills for case in suite.cases)
    assert all("search_docs" in case.simulated_tools for case in suite.cases)
    assert all("AgentBlaster emerging workflow stack seed=37" in str(case.system_prompt) for case in suite.cases)
    assert all("tokens_per_second_prefill" in case.metrics for case in suite.cases)
    assert all("mcp_profile_applied" in case.metrics for case in suite.cases)
    assert all("lcp_context_applied" in case.metrics for case in suite.cases)
    assert all("skill_selection_valid" in case.metrics for case in suite.cases)
    assert all("emerging-workflows" in case.tags for case in suite.cases)
    assert report["surface_counts"]["mcp_profile_cases"] == 2
    assert report["surface_counts"]["lcp_profile_cases"] == 2
    assert report["surface_counts"]["skill_cases"] == 2
    assert report["surface_counts"]["cache_control_cases"] == 2
    assert report["surface_counts"]["tool_loop_cases"] == 2


def test_judge_rubric_harness_generates_structured_evaluator_cases() -> None:
    suite = generate_harness_suite(_source_suite(), profile="judge-rubric", repeats=2, seed=31)

    assert suite.name == "source-judge-rubric-harness"
    assert suite.provenance.generator_profile == "judge-rubric"
    assert [case.id for case in suite.cases] == [
        "case-one-judge-rubric-01",
        "case-one-judge-rubric-02",
    ]
    assert all(case.expected_substring is None for case in suite.cases)
    assert all(case.expected_tool_name is None for case in suite.cases)
    assert all(case.tools == [] for case in suite.cases)
    assert all(case.skills == [] for case in suite.cases)
    assert all(case.response_format["type"] == "json_schema" for case in suite.cases)
    assert suite.cases[0].expected_json_fields == {
        "verdict": "pass",
        "score": 1,
        "rationale_code": "agentblaster-judge-31-1-1",
        "source_case_id": "case-one",
    }
    assert "Do not answer the original task" in suite.cases[0].prompt
    assert "judge-rubric" in suite.cases[0].tags
    assert "model-judge" in suite.cases[0].tags
    assert "judge_verdict_valid" in suite.cases[0].metrics


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


def test_harness_review_report_summarizes_surfaces_without_prompts() -> None:
    suite = generate_harness_suite(_source_suite(), profile="contract-fuzz", repeats=1, seed=3)
    report = build_harness_review_report(suite)
    text = format_harness_review_report(report)
    serialized = str(report)

    assert report["schema_version"] == "agentblaster.harness-review.v1"
    assert report["suite"]["name"] == "source-contract-fuzz-harness"
    assert report["generated"] is True
    assert report["surface_counts"]["streaming_cases"] == 1
    assert report["surface_counts"]["structured_output_cases"] == 1
    assert report["surface_counts"]["tool_schema_cases"] == 1
    assert report["surface_counts"]["multi_tool_catalog_cases"] == 0
    assert report["surface_counts"]["tool_loop_cases"] == 0
    assert report["surface_counts"]["judge_rubric_cases"] == 0
    assert report["review"]["calibration_required_before_release_gate"] is True
    assert report["safety"]["includes_prompts"] is False
    assert "Reply with exactly: agentblaster-ok" not in serialized
    assert "AgentBlaster harness review" in text


def test_harness_review_counts_judge_rubric_cases_without_prompts() -> None:
    suite = generate_harness_suite(_source_suite(), profile="judge-rubric", repeats=1, seed=31)
    report = build_harness_review_report(suite)
    serialized = str(report)

    assert report["surface_counts"]["judge_rubric_cases"] == 1
    assert report["surface_counts"]["structured_output_cases"] == 1
    assert report["assertion_counts"]["json_fields"] == 1
    assert "Reply with exactly: agentblaster-ok" not in serialized


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
