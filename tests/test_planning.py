from __future__ import annotations

from agentblaster.capabilities import check_suite_compatibility
from agentblaster.models import ApiContract, BenchmarkCase, ProviderConfig, RawTraceMode, SuiteDefinition
from agentblaster.planning import build_run_plan, format_run_plan


def test_build_run_plan_estimates_tokens_costs_and_capabilities() -> None:
    provider = ProviderConfig(
        name="openai",
        contract=ApiContract.OPENAI,
        base_url="https://api.openai.com/v1",
        remote=True,
        capabilities={"streaming": True},
        cost_model={"input_usd_per_1m_tokens": 2.0, "output_usd_per_1m_tokens": 8.0},
    )
    suite = SuiteDefinition(
        name="stream-suite",
        description="stream suite",
        cases=[
            BenchmarkCase(
                id="case-one",
                title="case one",
                prompt="Stream exactly: agentblaster-ok",
                expected_substring="agentblaster-ok",
                streaming=True,
                cancel_after_ms=250,
                max_tokens=16,
            )
        ],
    )
    capability_report = check_suite_compatibility(provider, suite)

    plan = build_run_plan(
        provider=provider,
        suite=suite,
        model="qwen-test",
        raw_trace_mode=RawTraceMode.OFF,
        concurrency=2,
        capability_report=capability_report,
    )

    assert plan.dry_run is True
    assert plan.provider == "openai"
    assert plan.remote is True
    assert plan.engine_target is not None
    assert plan.engine_target["id"] == "remote-openai-compatible"
    assert plan.engine_target["standardization"]["primary_scoring_contract"] == "openai"
    assert plan.raw_trace_mode == "off"
    assert plan.concurrency == 2
    assert plan.total_cases == 1
    assert plan.estimated_prompt_tokens >= 1
    assert plan.max_output_tokens == 16
    assert plan.prompt_footprint is not None
    assert plan.prompt_footprint.prefill_pressure_score >= plan.estimated_prompt_tokens
    assert plan.prompt_footprint.shared_static_reuse_tokens == 0
    assert plan.estimated_total_cost_usd is not None
    assert plan.capability_compatible is True
    assert plan.capability_missing == []
    assert plan.capability_unknown == ["cancellation"]
    assert plan.cases[0].streaming is True
    assert plan.cases[0].cancel_after_ms == 250
    assert plan.cases[0].capability_surfaces == ["streaming", "cancellation"]
    assert plan.cases[0].dynamic_prompt_tokens >= 1
    assert plan.cases[0].estimated_cost_usd is not None


def test_format_run_plan_is_human_readable() -> None:
    provider = ProviderConfig(name="local", contract=ApiContract.OPENAI, base_url="http://127.0.0.1:9999/v1")
    suite = SuiteDefinition(
        name="smoke",
        description="smoke",
        cases=[BenchmarkCase(id="case-one", title="case one", prompt="hello")],
    )
    plan = build_run_plan(
        provider=provider,
        suite=suite,
        model="qwen-test",
        raw_trace_mode=RawTraceMode.REDACTED,
        concurrency=1,
    )

    text = format_run_plan(plan)

    assert "dry_run: true" in text
    assert "provider: local" in text
    assert "engine_target: unknown" in text
    assert "estimated_prompt_tokens:" in text
    assert "prefill_pressure:" in text
    assert "shared_static_reuse_tokens:" in text
    assert "- case-one" in text
    assert "cancel_after_ms=unknown" in text
    assert "surfaces=none" in text
    assert "prompt_surfaces=none" in text


def test_build_run_plan_exposes_shared_static_prefix_reuse() -> None:
    provider = ProviderConfig(name="local", contract=ApiContract.OPENAI, base_url="http://127.0.0.1:9999/v1")
    suite = SuiteDefinition(
        name="prefill-mini",
        description="prefill mini",
        cases=[
            BenchmarkCase(id="case-one", title="case one", system_prompt="Shared system.", prompt="A"),
            BenchmarkCase(id="case-two", title="case two", system_prompt="Shared system.", prompt="B"),
        ],
    )

    plan = build_run_plan(
        provider=provider,
        suite=suite,
        model="qwen-test",
        raw_trace_mode=RawTraceMode.OFF,
        concurrency=2,
    )

    assert plan.prompt_footprint is not None
    assert plan.prompt_footprint.shared_static_prefix_groups == 1
    assert plan.prompt_footprint.shared_static_reuse_tokens > 0
    assert plan.prompt_footprint.shared_static_reuse_case_count == 1
    assert plan.cases[0].static_prefix_tokens > 0
    assert plan.cases[0].prompt_surfaces == ["system"]


def test_build_run_plan_exposes_known_local_engine_target_metadata() -> None:
    provider = ProviderConfig(name="afm", contract=ApiContract.OPENAI, base_url="http://127.0.0.1:9999/v1")
    suite = SuiteDefinition(
        name="smoke",
        description="smoke",
        cases=[BenchmarkCase(id="case-one", title="case one", prompt="hello")],
    )

    plan = build_run_plan(
        provider=provider,
        suite=suite,
        model="qwen-test",
        raw_trace_mode=RawTraceMode.OFF,
        concurrency=1,
    )
    text = format_run_plan(plan)

    assert plan.engine_target is not None
    assert plan.engine_target["id"] == "afm-mlx"
    assert "harness-engineering" in plan.engine_target["standardization"]["workflow_surfaces"]
    assert "large repeated system prompts" in plan.engine_target["standardization"]["prefill_challenges"]
    assert "engine_target: afm-mlx" in text


def test_parser_repair_cases_surface_strict_capability_requirement() -> None:
    provider = ProviderConfig(
        name="local",
        contract=ApiContract.OPENAI,
        base_url="http://127.0.0.1:9999/v1",
        capabilities={"tool_calling": True},
    )
    suite = SuiteDefinition(
        name="parser-repair-mini",
        description="parser repair mini",
        cases=[
            BenchmarkCase(
                id="parser-case",
                title="parser case",
                prompt="Call ping_agentblaster with target set to agentblaster-ok.",
                expected_tool_name="ping_agentblaster",
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "ping_agentblaster",
                            "description": "Ping fixture.",
                            "parameters": {
                                "type": "object",
                                "properties": {"target": {"type": "string"}},
                                "required": ["target"],
                                "additionalProperties": False,
                            },
                        },
                    }
                ],
                metrics=["tool_calls_valid", "invalid_tool_call_count", "tool_parser_repair_required"],
                tags=["tool-parser-repair"],
            )
        ],
    )
    capability_report = check_suite_compatibility(provider, suite)

    plan = build_run_plan(
        provider=provider,
        suite=suite,
        model="qwen-test",
        raw_trace_mode=RawTraceMode.OFF,
        concurrency=1,
        capability_report=capability_report,
    )
    text = format_run_plan(plan)

    assert "tool_calling" in {requirement.key for requirement in capability_report.requirements}
    assert "tool_parser_repair" in {requirement.key for requirement in capability_report.requirements}
    assert capability_report.compatible is True
    assert [finding.key for finding in capability_report.unknown] == ["tool_parser_repair"]
    assert plan.capability_unknown == ["tool_parser_repair"]
    assert plan.cases[0].capability_surfaces == ["tool_calling", "tool_parser_repair"]
    assert "surfaces=tool_calling,tool_parser_repair" in text
