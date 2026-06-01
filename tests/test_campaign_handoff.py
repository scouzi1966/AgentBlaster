from __future__ import annotations

import json
from pathlib import Path


def test_qwen_gemma_campaign_handoff_links_required_starter_artifacts() -> None:
    handoff = json.loads(Path("campaigns/qwen-gemma-local/campaign-handoff.json").read_text(encoding="utf-8"))
    runbook = Path("campaigns/qwen-gemma-local/README.md").read_text(encoding="utf-8")

    assert handoff["schema_version"] == "agentblaster.campaign-handoff.v1"
    assert handoff["providers"] == ["afm", "lm-studio"]
    assert handoff["model_targets"] == ["qwen3.6-27b-dense", "gemma-4-31b-dense"]
    assert {matrix["path"] for matrix in handoff["matrices"]} == {
        "examples/matrices/qwen-gemma-local.yaml",
        "examples/matrices/qwen-gemma-stress.yaml",
    }
    assert "reports/environment-readiness.json" in handoff["required_preflight_artifacts"]
    assert "reports/qwen-gemma-experiment.json" in handoff["required_preflight_artifacts"]
    assert "reports/qwen-gemma-experiment-gate.json" in handoff["required_preflight_artifacts"]
    assert "reports/afm-trace-readiness.json" in handoff["required_preflight_artifacts"]
    assert "reports/benchmark-readiness-inputs.txt" in handoff["required_preflight_artifacts"]
    assert "campaign-preflight/qwen-gemma-local/manifest.json" in handoff["required_preflight_artifacts"]
    assert "campaign-preflight/qwen-gemma-local/readiness/benchmark-readiness-index.json" in handoff[
        "required_preflight_artifacts"
    ]
    assert "reports/qwen-gemma-provider-contract-matrix-plan.json" in handoff["required_preflight_artifacts"]
    assert "reports/trace-replay-suite-audit.json" in handoff["required_preflight_artifacts"]
    assert "reports/agentic-tool-loop-suite-audit.json" in handoff["required_preflight_artifacts"]
    assert "reports/agent-fanout-suite-audit.json" in handoff["required_preflight_artifacts"]
    assert "reports/prefill-suite-audit.json" in handoff["required_preflight_artifacts"]
    assert "reports/harness-engineering-suite-audit.json" in handoff["required_preflight_artifacts"]
    assert "reports/trace-replay-harness-review.json" in handoff["required_preflight_artifacts"]
    assert "reports/agentic-tool-loop-harness-review.json" in handoff["required_preflight_artifacts"]
    assert "reports/agent-fanout-harness-review.json" in handoff["required_preflight_artifacts"]
    assert "reports/prefill-harness-review.json" in handoff["required_preflight_artifacts"]
    assert "reports/harness-engineering-harness-review.json" in handoff["required_preflight_artifacts"]
    assert "reports/trace-replay-calibration.json" in handoff["required_preflight_artifacts"]
    assert "reports/agentic-tool-loop-calibration.json" in handoff["required_preflight_artifacts"]
    assert "reports/agent-fanout-calibration.json" in handoff["required_preflight_artifacts"]
    assert "reports/prefill-calibration.json" in handoff["required_preflight_artifacts"]
    assert "reports/harness-engineering-calibration.json" in handoff["required_preflight_artifacts"]
    assert "reports/qwen-gemma-provider-contract-matrix.json" in handoff["required_execution_artifacts"]
    assert "reports/qwen-gemma-stress-saturation.json" in handoff["required_execution_artifacts"]
    assert "reports/qwen-gemma-local-summary.json" in handoff["required_execution_artifacts"]
    assert "reports/qwen-gemma-experiment.json" in handoff["publication_artifacts"]
    assert "reports/qwen-gemma-experiment-gate.json" in handoff["publication_artifacts"]
    assert "reports/implementation-status.json" in handoff["publication_artifacts"]
    assert "reports/qwen-gemma-claim-readiness.json" in handoff["publication_artifacts"]
    assert "publication-bundles/qwen-gemma-local-summary.agentblaster-matrix-publication.zip" in handoff["publication_artifacts"]
    assert "reports/qwen-gemma-local-summary-matrix-report.pdf" in handoff["publication_artifacts"]
    assert "reports/qwen-gemma-local-summary-matrix-scorecard.json" in handoff["publication_artifacts"]
    assert "reports/qwen-gemma-local-summary-matrix-scorecard.png" in handoff["publication_artifacts"]
    assert "reports/qwen-gemma-local-summary-matrix-scorecard.pdf" in handoff["publication_artifacts"]
    assert "reports/qwen-gemma-stress-summary-matrix-scorecard.json" in handoff["publication_artifacts"]
    assert "reports/qwen-gemma-stress-summary-matrix-scorecard.png" in handoff["publication_artifacts"]
    assert "reports/trace-replay-suite-audit.json" in handoff["publication_artifacts"]
    assert "reports/agentic-tool-loop-suite-audit.json" in handoff["publication_artifacts"]
    assert "reports/agent-fanout-suite-audit.json" in handoff["publication_artifacts"]
    assert "reports/prefill-suite-audit.json" in handoff["publication_artifacts"]
    assert "reports/harness-engineering-suite-audit.json" in handoff["publication_artifacts"]
    assert "reports/trace-replay-harness-review.json" in handoff["publication_artifacts"]
    assert "reports/agentic-tool-loop-harness-review.json" in handoff["publication_artifacts"]
    assert "reports/agent-fanout-harness-review.json" in handoff["publication_artifacts"]
    assert "reports/prefill-harness-review.json" in handoff["publication_artifacts"]
    assert "reports/harness-engineering-harness-review.json" in handoff["publication_artifacts"]
    assert "reports/trace-replay-calibration-report.json" in handoff["publication_artifacts"]
    assert "reports/agentic-tool-loop-calibration-report.json" in handoff["publication_artifacts"]
    assert "reports/agent-fanout-calibration-report.json" in handoff["publication_artifacts"]
    assert "reports/prefill-calibration-report.json" in handoff["publication_artifacts"]
    assert "reports/harness-engineering-calibration-report.json" in handoff["publication_artifacts"]
    assert "reports/afm-metric-coverage.json" in handoff["publication_artifacts"]
    assert "reports/lm-studio-metric-coverage.json" in handoff["publication_artifacts"]
    assert "reports/afm-improvement-plan.json" in handoff["publication_artifacts"]
    assert "reports/qwen-gemma-retention-cleanup-plan.json" in handoff["publication_artifacts"]
    assert "reports/qwen-gemma-manual-cleanup-plan.json" in handoff["publication_artifacts"]
    assert "reports/qwen-gemma-evidence-index.json" in handoff["publication_artifacts"]
    assert "reports/afm-trace-readiness.json" in handoff["publication_artifacts"]
    assert "reports/benchmark-readiness-inputs.txt" in handoff["publication_artifacts"]
    assert "campaign-preflight/qwen-gemma-local/manifest.json" in handoff["publication_artifacts"]
    assert "test-reports/selftest/qwen-gemma-local-selftest/selftest-report.json" in handoff["publication_artifacts"]
    assert handoff["safety"]["validation_status"] == "not run by this handoff artifact"
    assert "agentblaster run \\" in runbook
    assert "agentblaster matrix contract-checks" in runbook
    assert "agentblaster matrix saturation-report" in runbook
    assert "agentblaster matrix publication-bundle" in runbook
    assert "--format html,md,json,card,png,pdf" in runbook
    assert "--matrix-scorecard reports/qwen-gemma-local-summary-matrix-scorecard.json" in runbook
    assert "agentblaster experiment manifest" in runbook
    assert "agentblaster experiment gate reports/qwen-gemma-experiment.json" in runbook
    assert "agentblaster suite-audit --suite trace-replay" in runbook
    assert "agentblaster suite-audit --suite agentic-tool-loop" in runbook
    assert "agentblaster suite-audit --suite harness-engineering" in runbook
    assert "--suite-audit reports/trace-replay-suite-audit.json" in runbook
    assert "agentblaster harness review --suite trace-replay" in runbook
    assert "agentblaster harness review --suite agentic-tool-loop" in runbook
    assert "agentblaster harness review --suite harness-engineering" in runbook
    assert "--harness-review reports/trace-replay-harness-review.json" in runbook
    assert "agentblaster suite-calibration --suite trace-replay --template-output" in runbook
    assert "agentblaster suite-calibration --suite trace-replay --calibration" in runbook
    assert "agentblaster suite-calibration --suite harness-engineering --template-output" in runbook
    assert "--suite-calibration-report reports/trace-replay-calibration-report.json" in runbook
    assert "agentblaster providers metric-coverage --provider afm" in runbook
    assert "agentblaster providers metric-coverage --provider lm-studio" in runbook
    assert "agentblaster selftest --tier normal --report-dir test-reports/selftest --run-id qwen-gemma-local-selftest" in runbook
    assert "agentblaster selftest report --run qwen-gemma-local-selftest" in runbook
    assert "agentblaster engines improvement-plan" in runbook
    assert "agentblaster cleanup-expired --runs runs" in runbook
    assert "reports/qwen-gemma-retention-cleanup-plan.json" in runbook
    assert "reports/qwen-gemma-manual-cleanup-plan.json" in runbook
    assert "--require-audit-log" in runbook
    assert "--metric-coverage reports/afm-metric-coverage.json" in runbook
    assert "--metric-coverage reports/lm-studio-metric-coverage.json" in runbook
    assert "--engine-advisory reports/afm-improvement-plan.json" in runbook
    assert "agentblaster evidence index" in runbook
    assert "--evidence-index reports/qwen-gemma-evidence-index.json" in runbook
    assert "--artifact test-reports/selftest/qwen-gemma-local-selftest/selftest-report.json" in runbook
    assert "--output-json reports/afm-trace-readiness.json" in runbook
    assert "cat > reports/benchmark-readiness-inputs.txt" in runbook
    assert "--benchmark-readiness-list reports/benchmark-readiness-inputs.txt" in runbook
    assert "campaign-preflight/qwen-gemma-local/readiness/benchmark-readiness-index.json" in runbook
    assert "--campaign-preflight-manifest campaign-preflight/qwen-gemma-local/manifest.json" in runbook
    assert "--selftest-report test-reports/selftest/qwen-gemma-local-selftest/selftest-report.json" in runbook
    assert "--provider-contract-matrix reports/qwen-gemma-provider-contract-matrix.json" in runbook
    assert "GET /api/runs/<run-id>/events" in runbook
