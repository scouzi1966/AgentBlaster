from __future__ import annotations

import json

from typer.testing import CliRunner

from agentblaster.cli import app
from agentblaster.models import BenchmarkCase, SuiteDefinition, SuiteProvenance
from agentblaster.suite_calibration import evaluate_suite_calibration, suite_calibration_template


def _generated_suite() -> SuiteDefinition:
    return SuiteDefinition(
        name="generated-suite",
        description="Generated suite",
        provenance=SuiteProvenance(origin="harness_generated", generator="agentblaster.harness", generator_profile="metamorphic"),
        cases=[BenchmarkCase(id="case-one", title="Case one", prompt="Reply with exactly: agentblaster-ok")],
    )


def test_suite_calibration_template_targets_generated_suite() -> None:
    suite = _generated_suite()
    template = suite_calibration_template(suite)

    assert template["schema_version"] == "agentblaster.suite-calibration.v1"
    assert template["suite"] == "generated-suite"
    assert template["generated"] is True
    assert template["generator_profile"] == "metamorphic"
    assert template["known_good_runs"] == []


def test_suite_calibration_gate_requires_good_bad_taxonomy_and_approval() -> None:
    suite = _generated_suite()
    report = evaluate_suite_calibration(suite, suite_calibration_template(suite))

    assert report["passed"] is False
    codes = {finding["code"] for finding in report["findings"]}
    assert "missing_known_good_run" in codes
    assert "missing_known_bad_case" in codes
    assert "missing_failure_taxonomy" in codes
    assert "missing_human_review" in codes
    assert "not_approved_for_release_gate" in codes


def test_suite_calibration_gate_passes_with_complete_manifest() -> None:
    suite = _generated_suite()
    manifest = suite_calibration_template(suite)
    manifest.update(
        {
            "known_good_runs": [{"provider": "mock-openai", "result_ref": "runs/good/summary.json", "pass_rate": 100}],
            "known_bad_cases": [{"case_id": "case-one", "expected_failure_class": "model_quality", "result_ref": "runs/bad/results.jsonl"}],
            "failure_taxonomy": ["model_quality", "tool_call_invalid"],
            "human_reviewed": True,
            "approved_for_release_gate": True,
        }
    )

    report = evaluate_suite_calibration(suite, manifest)

    assert report["passed"] is True
    assert report["summary"]["known_good_runs"] == 1
    assert report["summary"]["known_bad_cases"] == 1


def test_cli_suite_calibration_template_and_gate(tmp_path) -> None:
    suite_path = tmp_path / "suite.yaml"
    suite_path.write_text(
        """
name: generated-suite
description: Generated suite
provenance:
  origin: harness_generated
  generator: agentblaster.harness
  generator_profile: metamorphic
cases:
  - id: case-one
    title: Case one
    prompt: Reply with exactly: agentblaster-ok
""",
        encoding="utf-8",
    )
    template_path = tmp_path / "calibration.json"
    report_path = tmp_path / "calibration-report.json"
    runner = CliRunner()

    template_result = runner.invoke(
        app,
        ["suite-calibration", "--suite-file", str(suite_path), "--template-output", str(template_path)],
    )
    assert template_result.exit_code == 0, template_result.output
    manifest = json.loads(template_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "known_good_runs": [{"provider": "mock-openai", "result_ref": "runs/good/summary.json"}],
            "known_bad_cases": [{"case_id": "case-one", "expected_failure_class": "model_quality"}],
            "failure_taxonomy": ["model_quality"],
            "human_reviewed": True,
            "approved_for_release_gate": True,
        }
    )
    template_path.write_text(json.dumps(manifest), encoding="utf-8")

    gate_result = runner.invoke(
        app,
        [
            "suite-calibration",
            "--suite-file",
            str(suite_path),
            "--calibration",
            str(template_path),
            "--output-json",
            str(report_path),
        ],
    )

    assert gate_result.exit_code == 0, gate_result.output
    assert "passed: true" in gate_result.output
    assert report_path.exists()
