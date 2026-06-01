from __future__ import annotations

from agentblaster.models import BenchmarkCase, SuiteDefinition
from agentblaster.suite_audit import audit_suite, format_suite_audit


def test_suite_audit_reports_provenance_risk_and_capability_surfaces() -> None:
    suite = SuiteDefinition(
        name="governance-suite",
        description="Governance suite",
        cases=[
            BenchmarkCase(
                id="external-case",
                title="External case",
                prompt="Use the tool.",
                provenance="public_benchmark_adapted",
                risk_level="high",
                tools=[{"type": "function", "function": {"name": "lookup_fixture", "parameters": {"type": "object"}}}],
                simulated_tools=["search_docs"],
                mcp_profile="fixture-mcp",
                skills=["safe-tool-replay"],
                response_format={"type": "json_object"},
                streaming=True,
                cancel_after_ms=100,
            ),
            BenchmarkCase(
                id="external-case-copy",
                title="External case copy",
                prompt="Use the tool.",
                provenance="public_benchmark_adapted",
                risk_level="medium",
                tools=[{"type": "function", "function": {"name": "lookup_fixture", "parameters": {"type": "object"}}}],
                simulated_tools=["search_docs"],
                mcp_profile="fixture-mcp",
                skills=["safe-tool-replay"],
                response_format={"type": "json_object"},
                streaming=True,
                cancel_after_ms=100,
            )
        ],
    )

    report = audit_suite(suite)

    assert report.suite == "governance-suite"
    assert report.total_cases == 2
    assert report.provenance_counts == {"public_benchmark_adapted": 2}
    assert report.risk_counts == {"high": 1, "medium": 1}
    assert report.capability_surfaces["tool_schema_names"] == ["lookup_fixture"]
    assert report.capability_surfaces["simulated_tools"] == ["search_docs"]
    assert report.capability_surfaces["mcp_profiles"] == ["fixture-mcp"]
    assert report.capability_surfaces["skills"] == ["safe-tool-replay"]
    assert report.capability_surfaces["response_format_cases"] == 2
    assert report.capability_surfaces["streaming_cases"] == 2
    assert report.capability_surfaces["cancellation_cases"] == 2
    assert report.dataset_hygiene["duplicate_fingerprint_count"] == 1
    assert report.dataset_hygiene["duplicate_case_groups"][0]["case_ids"] == ["external-case", "external-case-copy"]
    assert {finding.code for finding in report.findings} == {
        "missing_source_url",
        "missing_license",
        "high_risk_case",
        "duplicate_case_fingerprint",
    }
    assert "Suite audit is static" in report.security_notes[0]


def test_format_suite_audit_includes_findings() -> None:
    suite = SuiteDefinition(
        name="unnamed-tool-suite",
        description="Unnamed tool suite",
        cases=[
            BenchmarkCase(
                id="unnamed-tool-case",
                title="Unnamed tool case",
                prompt="Use the unnamed tool.",
                tools=[{"type": "function", "function": {"parameters": {"type": "object"}}}],
            )
        ],
    )

    text = format_suite_audit(audit_suite(suite))

    assert "suite: unnamed-tool-suite" in text
    assert "tool_schema_names: -" in text
    assert "duplicate_fingerprints: 0" in text
    assert "unnamed_tool_schema" in text
