from __future__ import annotations

from agentblaster.capabilities import check_suite_compatibility, format_capability_report, suite_requirements
from agentblaster.harness import generate_harness_suite
from agentblaster.models import ApiContract, BenchmarkCase, ProviderConfig, SuiteDefinition
from agentblaster.suites import BUILTIN_SUITES


def test_suite_requirements_detect_agentic_features() -> None:
    suite = SuiteDefinition(
        name="agentic",
        description="agentic suite",
        cases=[
            BenchmarkCase(
                id="stream",
                title="stream",
                prompt="stream",
                streaming=True,
                cancel_after_ms=200,
            ),
            BenchmarkCase(
                id="json",
                title="json",
                prompt="json",
                response_format={"type": "json_object"},
                expected_json_fields={"status": "ok"},
            ),
            BenchmarkCase(
                id="tool",
                title="tool",
                prompt="tool",
                expected_tool_name="search_docs",
                simulated_tools=["search_docs"],
                mcp_profile="fixture-mcp",
                lcp_profile="fixture-lcp",
                skills=["repo-triage"],
                max_tool_calls=2,
            ),
            BenchmarkCase(
                id="trace",
                title="trace",
                prompt="trace",
                messages=[
                    {"role": "user", "content": "Use trace context."},
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "read_file_fixture", "arguments": "{}"},
                            }
                        ],
                    },
                ],
            ),
        ],
    )

    requirements = {requirement.key: set(requirement.case_ids) for requirement in suite_requirements(suite)}

    assert requirements["chat"] == {"stream", "json", "tool", "trace"}
    assert requirements["streaming"] == {"stream"}
    assert requirements["cancellation"] == {"stream"}
    assert requirements["structured_output"] == {"json"}
    assert requirements["tool_calling"] == {"tool", "trace"}
    assert requirements["tool_loop"] == {"tool"}
    assert requirements["mcp_profile"] == {"tool"}
    assert requirements["lcp_context"] == {"tool"}
    assert requirements["skills"] == {"tool"}
    assert requirements["trace_replay"] == {"trace"}


def test_builtin_agentic_tool_loop_suite_declares_required_capabilities() -> None:
    requirements = {item.key: set(item.case_ids) for item in suite_requirements(BUILTIN_SUITES["agentic-tool-loop"])}

    assert requirements["tool_calling"] == {
        "tool-loop-route-final",
        "tool-loop-mcp-lcp-context",
        "tool-loop-max-call-boundary",
    }
    assert requirements["tool_loop"] == {
        "tool-loop-route-final",
        "tool-loop-mcp-lcp-context",
        "tool-loop-max-call-boundary",
    }
    assert requirements["mcp_profile"] == {"tool-loop-mcp-lcp-context"}
    assert requirements["lcp_context"] == {"tool-loop-mcp-lcp-context"}


def test_builtin_harness_engineering_suite_declares_required_capabilities() -> None:
    requirements = {item.key: set(item.case_ids) for item in suite_requirements(BUILTIN_SUITES["harness-engineering"])}

    assert requirements["streaming"] == {"harness-contract-streaming-sentinel"}
    assert requirements["structured_output"] == {"harness-judge-rubric-json"}
    assert requirements["judge_rubric"] == {"harness-judge-rubric-json"}
    assert requirements["prompt_caching"] == {"harness-cache-replay-static-prefix"}


def test_check_suite_compatibility_reports_missing_and_unknown_capabilities() -> None:
    suite = SuiteDefinition(
        name="structured-stream",
        description="structured stream suite",
        cases=[
            BenchmarkCase(
                id="case-one",
                title="case one",
                prompt="Return JSON",
                streaming=True,
                response_format={"type": "json_object"},
            )
        ],
    )
    provider = ProviderConfig(
        name="partial",
        contract=ApiContract.OPENAI,
        base_url="https://example.com/v1",
        capabilities={"streaming": False},
    )

    report = check_suite_compatibility(provider, suite)

    assert report.compatible is False
    assert [finding.key for finding in report.missing] == ["streaming"]
    assert [finding.key for finding in report.unknown] == ["structured_output"]
    assert "compatible: false" in format_capability_report(report)


def test_check_suite_compatibility_allows_unknowns_unless_strict() -> None:
    suite = SuiteDefinition(
        name="tool-suite",
        description="tool suite",
        cases=[
            BenchmarkCase(id="case-one", title="case one", prompt="Use tool", expected_tool_name="search_docs")
        ],
    )
    provider = ProviderConfig(name="local", contract=ApiContract.OPENAI, base_url="http://127.0.0.1:9999/v1")

    non_strict = check_suite_compatibility(provider, suite)
    strict = check_suite_compatibility(provider, suite, strict_unknown=True)

    assert non_strict.compatible is True
    assert [finding.key for finding in non_strict.unknown] == ["tool_calling"]
    assert strict.compatible is False


def test_check_suite_compatibility_uses_contract_defaults() -> None:
    suite = SuiteDefinition(
        name="responses-suite",
        description="responses suite",
        cases=[
            BenchmarkCase(
                id="case-one",
                title="case one",
                prompt="Continue",
                previous_response_id="resp_previous",
            )
        ],
    )
    chat_provider = ProviderConfig(name="chat", contract=ApiContract.OPENAI, base_url="https://example.com/v1")
    responses_provider = ProviderConfig(
        name="responses",
        contract=ApiContract.OPENAI_RESPONSES,
        base_url="https://example.com/v1",
    )

    chat_report = check_suite_compatibility(chat_provider, suite)
    responses_report = check_suite_compatibility(responses_provider, suite)

    assert chat_report.compatible is False
    assert [finding.key for finding in chat_report.missing] == ["responses_api"]
    assert responses_report.compatible is True
    assert any(finding.key == "responses_api" for finding in responses_report.supported)


def test_check_suite_compatibility_flags_native_trace_replay_gap() -> None:
    suite = SuiteDefinition(
        name="trace",
        description="trace suite",
        cases=[
            BenchmarkCase(
                id="case-one",
                title="case one",
                prompt="trace",
                messages=[{"role": "user", "content": "trace"}],
            )
        ],
    )
    provider = ProviderConfig(
        name="lmstudio-native",
        contract=ApiContract.NATIVE,
        base_url="http://127.0.0.1:1234",
        native_adapter="lm-studio",
    )

    report = check_suite_compatibility(provider, suite)

    assert report.compatible is False
    assert [finding.key for finding in report.missing] == ["trace_replay"]


def test_check_suite_compatibility_treats_tool_loop_as_contract_trace_feature() -> None:
    suite = SuiteDefinition(
        name="tool-loop",
        description="tool loop suite",
        cases=[
            BenchmarkCase(
                id="case-one",
                title="case one",
                prompt="Use tool then final answer",
                expected_tool_name="search_docs",
                simulated_tools=["search_docs"],
                max_tool_calls=2,
            )
        ],
    )
    openai_provider = ProviderConfig(name="chat", contract=ApiContract.OPENAI, base_url="https://example.com/v1")
    lmstudio_native = ProviderConfig(
        name="lmstudio-native",
        contract=ApiContract.NATIVE,
        base_url="http://127.0.0.1:1234",
        native_adapter="lm-studio",
    )

    assert check_suite_compatibility(openai_provider, suite).compatible is True
    native_report = check_suite_compatibility(lmstudio_native, suite)
    assert native_report.compatible is False
    assert [finding.key for finding in native_report.missing] == ["tool_loop"]


def test_generated_judge_rubric_suite_declares_judge_and_structured_requirements() -> None:
    source = SuiteDefinition(
        name="source",
        description="source",
        cases=[
            BenchmarkCase(
                id="case-one",
                title="case one",
                prompt="Return exactly agentblaster-ok",
                expected_substring="agentblaster-ok",
            )
        ],
    )
    suite = generate_harness_suite(source, profile="judge-rubric", repeats=1, seed=31)

    requirements = {item.key: set(item.case_ids) for item in suite_requirements(suite)}

    assert requirements["structured_output"] == {"case-one-judge-rubric-01"}
    assert requirements["judge_rubric"] == {"case-one-judge-rubric-01"}


def test_anthropic_messages_requires_declared_structured_output_for_judge_rubric() -> None:
    suite = SuiteDefinition(
        name="judge",
        description="judge",
        cases=[
            BenchmarkCase(
                id="judge-one",
                title="judge one",
                prompt="Return JSON",
                response_format={"type": "json_schema", "json_schema": {"name": "verdict", "schema": {"type": "object"}}},
                expected_json_fields={"verdict": "pass"},
                metrics=["judge_verdict_valid"],
                tags=["judge-rubric", "model-judge"],
            )
        ],
    )
    provider = ProviderConfig(
        name="lm-studio-anthropic",
        contract=ApiContract.ANTHROPIC,
        base_url="http://127.0.0.1:1234/v1",
    )
    declared_provider = provider.model_copy(update={"capabilities": {"structured_output": True}})

    report = check_suite_compatibility(provider, suite)
    declared_report = check_suite_compatibility(declared_provider, suite)

    assert report.compatible is False
    assert [finding.key for finding in report.missing] == ["judge_rubric", "structured_output"]
    assert declared_report.compatible is True


def test_local_anthropic_prompt_caching_is_unknown_until_declared() -> None:
    suite = SuiteDefinition(
        name="cache",
        description="cache",
        cases=[
            BenchmarkCase(
                id="cache-one",
                title="cache one",
                system_prompt="Static prefix",
                prompt="Reply ok",
                cache_control={"type": "ephemeral"},
            )
        ],
    )
    local_provider = ProviderConfig(
        name="local-anthropic",
        contract=ApiContract.ANTHROPIC,
        base_url="http://127.0.0.1:1234/v1",
    )
    remote_provider = local_provider.model_copy(update={"name": "remote-anthropic", "remote": True})

    local_report = check_suite_compatibility(local_provider, suite)
    remote_report = check_suite_compatibility(remote_provider, suite)

    assert local_report.compatible is True
    assert [finding.key for finding in local_report.unknown] == ["prompt_caching"]
    assert any(finding.key == "prompt_caching" for finding in remote_report.supported)
