from __future__ import annotations

import pytest

from agentblaster.errors import ConfigError
from agentblaster.suites import BUILTIN_SUITES, load_suite_file, validate_case_or_suite_file


def test_builtin_suites_include_core_mvp_families() -> None:
    assert {
        "smoke",
        "structured",
        "toolcall",
        "prefill",
        "toolsim",
        "agentic-tool-loop",
        "trace-replay",
        "agent-fanout",
        "cache-control",
        "cancellation",
        "lcp-context",
        "tool-parser-repair",
        "harness-engineering",
    }.issubset(BUILTIN_SUITES)


def test_builtin_agent_fanout_suite_declares_parallel_subagent_shape() -> None:
    suite = BUILTIN_SUITES["agent-fanout"]

    assert suite.provenance.origin == "builtin"
    assert len(suite.cases) >= 15
    core_cases = [case for case in suite.cases if case.id in {
        "fanout-planner-outline",
        "fanout-code-worker",
        "fanout-doc-worker",
        "fanout-synthesizer",
    }]
    assert len(core_cases) == 4
    assert all(case.scenario == "agent fan-out" for case in core_cases)
    assert all(case.expected_substring and case.expected_substring.startswith("agentblaster-") for case in core_cases)
    assert all("queue_ms" in case.metrics for case in core_cases)
    assert all("rate_limit_wait_ms" in case.metrics for case in core_cases)
    assert all("fanout" in case.tags for case in core_cases)
    assert all("concurrency" in case.tags for case in core_cases)


def test_builtin_prefill_suite_declares_repeated_static_prefix_shape() -> None:
    suite = BUILTIN_SUITES["prefill"]
    shared_prefix_cases = [case for case in suite.cases if case.scenario == "prefill shared prefix"]

    assert suite.provenance.origin == "builtin"
    assert len(suite.cases) >= 15
    assert {case.id for case in shared_prefix_cases} == {
        "prefill-static-prefix-warmup",
        "prefill-static-prefix-replay",
        "prefill-static-prefix-suffix-mutation",
    }
    assert len({case.system_prompt for case in shared_prefix_cases}) == 1
    assert all(case.system_prompt and "static agent instruction block" in case.system_prompt for case in shared_prefix_cases)
    assert all("tokens_per_second_prefill" in case.metrics for case in suite.cases)
    assert all("cache_hit_ratio" in case.metrics for case in suite.cases)
    assert all("repeated-system-prompt" in case.tags for case in shared_prefix_cases)


def test_builtin_agentic_tool_loop_suite_declares_mcp_lcp_and_boundary_cases() -> None:
    suite = BUILTIN_SUITES["agentic-tool-loop"]

    assert suite.provenance.origin == "builtin"
    assert len(suite.cases) >= 15
    core_cases = [case for case in suite.cases if case.id in {
        "tool-loop-route-final",
        "tool-loop-mcp-lcp-context",
        "tool-loop-max-call-boundary",
    }]
    assert len(core_cases) == 3
    assert all(case.max_tool_calls == 2 for case in core_cases)
    assert all("tool-loop" in case.tags for case in core_cases)
    assert all("tool_loop_stop_reason" in case.metrics for case in core_cases)
    mcp_lcp_case = next(case for case in suite.cases if case.id == "tool-loop-mcp-lcp-context")
    assert mcp_lcp_case.mcp_profile == "fixture-mcp"
    assert mcp_lcp_case.lcp_profile == "fixture-lcp"
    assert mcp_lcp_case.expected_tool_name == "mcp_fixture_read_resource"
    boundary_case = next(case for case in suite.cases if case.id == "tool-loop-max-call-boundary")
    assert boundary_case.expected_substring is None
    assert boundary_case.tool_choice == {"type": "function", "function": {"name": "route_agentblaster_task"}}


def test_builtin_cancellation_suite_declares_stream_abort_contract() -> None:
    suite = BUILTIN_SUITES["cancellation"]
    case = suite.cases[0]

    assert suite.provenance.origin == "builtin"
    assert case.id == "cancellation-stream-abort"
    assert case.streaming is True
    assert case.cancel_after_ms == 100
    assert case.expected_substring is None
    assert "canceled" in case.metrics
    assert "cancellation_latency_ms" in case.metrics
    assert "cancellation" in case.tags


def test_builtin_tool_parser_repair_suite_rejects_raw_text_tool_calls() -> None:
    suite = BUILTIN_SUITES["tool-parser-repair"]

    assert suite.provenance.origin == "builtin"
    assert len(suite.cases) >= 15
    core_cases = [case for case in suite.cases if case.id in {
        "parser-required-api-envelope",
        "parser-react-xml-boundary",
    }]
    assert len(core_cases) == 2
    assert all(case.scenario == "tool parser repair" for case in core_cases)
    assert all(case.expected_tool_name for case in core_cases)
    assert all(case.tool_choice for case in core_cases)
    assert all("tool_parser_repair_required" in case.metrics for case in core_cases)
    assert all("invalid_tool_call_count" in case.metrics for case in core_cases)
    assert all("repair" in case.tags for case in core_cases)
    assert "Raw JSON" in str(core_cases[0].system_prompt)
    assert "Action:" in core_cases[1].prompt


def test_builtin_harness_engineering_suite_declares_emerging_harness_surfaces() -> None:
    suite = BUILTIN_SUITES["harness-engineering"]

    assert suite.provenance.origin == "builtin"
    assert len(suite.cases) >= 15
    core_cases = [case for case in suite.cases if case.id.startswith("harness-")]
    assert {
        case.scenario for case in core_cases if case.id in {
            "harness-contract-streaming-sentinel",
            "harness-metamorphic-equivalent-wrapper",
            "harness-cache-replay-static-prefix",
            "harness-judge-rubric-json",
        }
    } == {
        "harness contract fuzz",
        "harness metamorphic",
        "harness cache replay",
        "harness judge rubric",
    }
    assert all("harness" in case.tags for case in core_cases)
    assert any(case.streaming for case in core_cases)
    assert any("cache-replay" in case.tags and "tokens_per_second_prefill" in case.metrics for case in core_cases)
    assert any("judge-rubric" in case.tags and "judge_verdict_valid" in case.metrics for case in core_cases)
    assert any("metamorphic" in case.tags for case in core_cases)


def test_builtin_suites_have_real_world_case_depth_and_unique_ids() -> None:
    for suite in BUILTIN_SUITES.values():
        case_ids = [case.id for case in suite.cases]

        assert 15 <= len(suite.cases) <= 20, suite.name
        assert len(case_ids) == len(set(case_ids)), suite.name
        assert any("afm" in case.tags or "local-agent" in case.tags for case in suite.cases), suite.name


def test_load_suite_file(tmp_path) -> None:
    path = tmp_path / "suite.yaml"
    path.write_text(
        """
name: local-smoke
description: Local smoke suite
cases:
  - id: case-one
    title: Case one
    prompt: "Reply with exactly: agentblaster-ok"
    provenance: internal_regression
    risk_level: low
    mcp_profile: fixture-mcp
    lcp_profile: fixture-lcp
    skills:
      - repo-triage
    metrics:
      - ttft_ms
    timeout_seconds: 12.5
    expected_substring: agentblaster-ok
    simulated_tools:
      - search_docs
    messages:
      - role: system
        content: Trace policy.
      - role: user
        content: Read fixture context.
""",
        encoding="utf-8",
    )

    suite = load_suite_file(path)

    assert suite.name == "local-smoke"
    assert suite.provenance.origin == "user_file"
    assert suite.provenance.primary_source == "user-provided suite file"
    assert suite.cases[0].id == "case-one"
    assert suite.cases[0].simulated_tools == ["search_docs"]
    assert suite.cases[0].provenance == "internal_regression"
    assert suite.cases[0].lcp_profile == "fixture-lcp"
    assert suite.cases[0].skills == ["repo-triage"]
    assert suite.cases[0].timeout_seconds == 12.5
    assert suite.cases[0].messages[0].role == "system"
    assert suite.cases[0].messages[1].content == "Read fixture context."


def test_builtin_suites_carry_builtin_provenance() -> None:
    suite = BUILTIN_SUITES["smoke"]

    assert suite.provenance.origin == "builtin"
    assert suite.provenance.primary_source == "AgentBlaster"
    assert suite.provenance.license == "MIT"


def test_validate_case_or_suite_file_accepts_single_case(tmp_path) -> None:
    path = tmp_path / "case.yaml"
    path.write_text(
        """
id: case-one
title: Case one
prompt: "Reply with exactly: agentblaster-ok"
expected_substring: agentblaster-ok
""",
        encoding="utf-8",
    )

    assert validate_case_or_suite_file(path) == "valid case case-one"


def test_validate_case_or_suite_file_rejects_invalid_yaml(tmp_path) -> None:
    path = tmp_path / "case.yaml"
    path.write_text("id: bad\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="invalid benchmark case"):
        validate_case_or_suite_file(path)
