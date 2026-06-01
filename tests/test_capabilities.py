from __future__ import annotations

from agentblaster.capabilities import check_suite_compatibility, format_capability_report, suite_requirements
from agentblaster.models import ApiContract, BenchmarkCase, ProviderConfig, SuiteDefinition


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
                skills=["repo-triage"],
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
    assert requirements["structured_output"] == {"json"}
    assert requirements["tool_calling"] == {"tool", "trace"}
    assert requirements["skills"] == {"tool"}
    assert requirements["trace_replay"] == {"trace"}


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
