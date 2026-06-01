from __future__ import annotations

import json

from typer.testing import CliRunner

from agentblaster.cli import app
from agentblaster.models import BenchmarkCase, SuiteDefinition
from agentblaster.prompt_footprint import format_prompt_footprint_report, suite_prompt_footprint


def test_suite_prompt_footprint_breaks_down_prefill_surfaces() -> None:
    suite = SuiteDefinition(
        name="footprint-suite",
        description="Footprint suite",
        cases=[
            BenchmarkCase(
                id="case-one",
                title="Case one",
                system_prompt="Shared system prompt.",
                prompt="Reply with exactly: agentblaster-ok",
                simulated_tools=["search_docs"],
                mcp_profile="fixture-mcp",
                skills=["repo-triage"],
                response_format={"type": "json_object"},
            ),
            BenchmarkCase(
                id="case-two",
                title="Case two",
                system_prompt="Shared system prompt.",
                prompt="Reply with exactly: agentblaster-ok",
                simulated_tools=["search_docs"],
                mcp_profile="fixture-mcp",
                skills=["repo-triage"],
            ),
        ],
    )

    report = suite_prompt_footprint(suite)

    assert report["schema_version"] == "agentblaster.prompt-footprint.v1"
    assert report["case_count"] == 2
    assert report["component_totals"]["simulated_tools"] > 0
    assert report["component_totals"]["mcp_profile"] > 0
    assert report["component_totals"]["skills"] > 0
    assert report["shared_static_prefixes"][0]["case_count"] == 2
    assert "structured" in report["cases"][0]["surfaces"]
    assert "prefill_pressure" in report
    assert "AgentBlaster prompt footprint" in format_prompt_footprint_report(report)


def test_cli_suite_footprint_writes_json_for_suite_file(tmp_path) -> None:
    suite_path = tmp_path / "suite.yaml"
    suite_path.write_text(
        """
name: footprint-suite
description: Footprint suite
cases:
  - id: case-one
    title: Case one
    system_prompt: Shared system prompt.
    prompt: Reply with exactly: agentblaster-ok
    simulated_tools:
      - search_docs
    skills:
      - repo-triage
""",
        encoding="utf-8",
    )
    output_json = tmp_path / "footprint.json"
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["suite-footprint", "--suite-file", str(suite_path), "--output-json", str(output_json)],
    )

    assert result.exit_code == 0, result.output
    assert "suite: footprint-suite" in result.output
    assert output_json.exists()
    assert json.loads(output_json.read_text(encoding="utf-8"))["suite"] == "footprint-suite"
