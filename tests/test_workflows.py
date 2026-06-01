from __future__ import annotations

from pathlib import Path


def test_ci_workflow_includes_static_readiness_and_governance_artifacts() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "agentblaster doctor --output-json test-reports/environment-readiness.json --fail-on-required-gaps" in workflow
    assert "agentblaster release packaging-readiness --output-json test-reports/release/packaging-readiness.json --fail-on-gaps" in workflow
    assert "agentblaster release provenance --output test-reports/release-provenance.json" in workflow
    assert "agentblaster security scan test-reports --output-json test-reports/security/redaction-scan.json" in workflow
    assert "pytest -q -m \"not remote and not slow and not gui\"" in workflow
    assert "workflow_dispatch" in workflow


def test_package_workflow_builds_artifacts_without_pypi_publish() -> None:
    workflow = Path(".github/workflows/publish.yml").read_text(encoding="utf-8")

    assert "name: Package" in workflow
    assert "python -m build" in workflow
    assert "agentblaster doctor --output-json release-reports/environment-readiness.json --fail-on-required-gaps" in workflow
    assert "agentblaster release packaging-readiness --output-json release-reports/packaging-readiness.json --fail-on-gaps" in workflow
    assert "agentblaster security scan dist release-reports --output-json release-reports/redaction-scan.json" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "pypi" not in workflow.lower()
