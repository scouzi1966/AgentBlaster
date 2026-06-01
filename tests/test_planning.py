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
    assert plan.raw_trace_mode == "off"
    assert plan.concurrency == 2
    assert plan.total_cases == 1
    assert plan.estimated_prompt_tokens >= 1
    assert plan.max_output_tokens == 16
    assert plan.estimated_total_cost_usd is not None
    assert plan.capability_compatible is True
    assert plan.capability_missing == []
    assert plan.cases[0].streaming is True
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
    assert "estimated_prompt_tokens:" in text
    assert "- case-one" in text
