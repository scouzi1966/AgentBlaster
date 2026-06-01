from __future__ import annotations

import json

from typer.testing import CliRunner

from agentblaster.cli import app
from agentblaster.workflow_readiness import build_workflow_readiness_report, format_workflow_readiness_report


def test_workflow_readiness_covers_agentic_surfaces_from_matrix(tmp_path) -> None:
    suite = _write_emerging_suite(tmp_path)
    matrix = _write_matrix(tmp_path, suite)

    report = build_workflow_readiness_report(name="agentic-campaign", matrices=[matrix])

    assert report["schema_version"] == "agentblaster.workflow-readiness.v1"
    assert report["status"] == "ready"
    assert report["ready"] is True
    assert report["summary"]["covered_required_surface_count"] == report["summary"]["required_surface_count"]
    assert report["summary"]["max_concurrency"] == 4
    coverage = {row["surface"]: row for row in report["coverage"]}
    assert coverage["tool-calling"]["present"] is True
    assert coverage["tool-loop"]["present"] is True
    assert coverage["structured-output"]["present"] is True
    assert coverage["concurrency"]["present"] is True
    assert coverage["prefill-cache"]["present"] is True
    assert coverage["mcp"]["present"] is True
    assert coverage["lcp"]["present"] is True
    assert coverage["skills"]["present"] is True
    assert coverage["cancellation"]["present"] is True
    assert coverage["harness-engineering"]["present"] is True
    assert report["security"]["contacts_providers"] is False
    markdown = format_workflow_readiness_report(report)
    assert "AgentBlaster Workflow Readiness" in markdown
    assert "tool-calling" in markdown
    assert "No required workflow-surface gaps" in markdown


def test_workflow_readiness_reports_required_surface_gaps() -> None:
    report = build_workflow_readiness_report(
        name="smoke-only",
        suite_names=["smoke"],
        required_surfaces=["tool-calling", "concurrency"],
    )

    assert report["status"] == "review-required"
    assert report["ready"] is False
    assert {gap["surface"] for gap in report["gaps"]} == {"tool-calling", "concurrency"}
    assert any("agent-fanout" in item for item in report["recommendations"])


def test_workflow_readiness_cli_writes_json_and_markdown(tmp_path) -> None:
    suite = _write_emerging_suite(tmp_path)
    matrix = _write_matrix(tmp_path, suite)
    output_json = tmp_path / "workflow-readiness.json"
    output_md = tmp_path / "workflow-readiness.md"

    result = CliRunner().invoke(
        app,
        [
            "release",
            "workflow-readiness",
            "--name",
            "agentic-campaign",
            "--matrix",
            str(matrix),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ],
    )

    assert result.exit_code == 0, result.output
    assert str(output_json) in result.output
    assert str(output_md) in result.output
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "agentblaster.workflow-readiness.v1"
    assert payload["ready"] is True
    assert payload["summary"]["max_concurrency"] == 4
    assert "AgentBlaster Workflow Readiness" in output_md.read_text(encoding="utf-8")


def _write_emerging_suite(tmp_path):
    path = tmp_path / "emerging-suite.yaml"
    path.write_text(
        """
name: emerging-suite
description: Static emerging agentic workflow fixture.
provenance:
  origin: harness_generated
  generator: agentblaster.harness
  generator_profile: emerging-workflows
  generator_seed: 42
  generator_repeats: 1
cases:
  - id: emerging-case
    title: Emerging workflow mixed surface
    prompt: Call route_agentblaster_task, respect the context bundle, then return the requested JSON sentinel.
    scenario: emerging workflow
    system_prompt: >
      AgentBlaster emerging workflow stack. Use fixture tools only. Preserve the repeated skill and context prefix.
    expected_json_fields:
      status: agentblaster-ok
    expected_tool_name: route_agentblaster_task
    response_format:
      type: json_object
    tools:
      - type: function
        function:
          name: route_agentblaster_task
          description: Route a deterministic benchmark task.
          parameters:
            type: object
            properties:
              destination:
                type: string
            required:
              - destination
            additionalProperties: false
      - type: function
        function:
          name: search_docs
          description: Search deterministic docs.
          parameters:
            type: object
            properties:
              query:
                type: string
            required:
              - query
            additionalProperties: false
    tool_choice:
      type: function
      function:
        name: route_agentblaster_task
    max_tool_calls: 2
    simulated_tools:
      - search_docs
    expected_tool_result_substring: agentblaster-ok
    mcp_profile: fixture-mcp
    lcp_profile: fixture-lcp
    skills:
      - repo-triage
      - safe-tool-replay
    cache_control:
      type: ephemeral
    metrics:
      - tokens_per_second_prefill
      - cache_hit_ratio
      - queue_ms
      - rate_limit_wait_ms
      - cancellation_latency_ms
      - mcp_profile_applied
      - lcp_context_applied
      - skill_selection_valid
    cancel_after_ms: 100
    streaming: true
    max_tokens: 64
    tags:
      - harness
      - emerging-workflows
      - concurrency
      - prefill
      - mcp
      - lcp
      - skills
""".lstrip(),
        encoding="utf-8",
    )
    return path


def _write_matrix(tmp_path, suite):
    path = tmp_path / "matrix.yaml"
    path.write_text(
        f"""
name: workflow-demo
runs:
  - engine: afm
    model: qwen3.6-27b-dense
    suite_file: {suite.name}
    concurrency: 4
""".lstrip(),
        encoding="utf-8",
    )
    return path
