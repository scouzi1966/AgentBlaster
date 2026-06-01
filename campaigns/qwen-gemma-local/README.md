# Qwen/Gemma Local Agentic Campaign

This is a starter runbook for the initial AgentBlaster comparison campaign:

- Providers: `afm`, `lm-studio` to start.
- Model targets: `qwen3.6-27b-dense`, `gemma-4-31b-dense`.
- Baseline matrix: `examples/matrices/qwen-gemma-local.yaml`.
- Stress matrix: `examples/matrices/qwen-gemma-stress.yaml`.
- Primary workload families: `trace-replay`, `agentic-tool-loop`, `agent-fanout`, `prefill`, `harness-engineering`.

The runbook is static. It does not prove benchmark completion. Use it to drive setup, execution, and evidence collection.

## 1. Static Readiness

```bash
agentblaster doctor --policy agentblaster.policy.yaml --output-json reports/environment-readiness.json --fail-on-required-gaps
agentblaster implementation-status --output-json reports/implementation-status.json
agentblaster catalog artifact-schemas --format json --output reports/artifact-schemas.json
agentblaster release packaging-readiness --output-json reports/packaging-readiness.json --fail-on-gaps
agentblaster policy validate agentblaster.policy.yaml --output-json reports/policy-normalized.json
agentblaster experiment manifest \
  --name qwen-gemma-local \
  --objective "Compare AFM and LM Studio on Qwen/Gemma dense local-agent suites before expanding to additional MLX engines." \
  --providers afm,lm-studio \
  --targets qwen3.6-27b-dense,gemma-4-31b-dense \
  --suites trace-replay,agentic-tool-loop,agent-fanout,prefill,harness-engineering \
  --policy agentblaster.policy.yaml \
  --matrix examples/matrices/qwen-gemma-local.yaml \
  --output reports/qwen-gemma-experiment.json
agentblaster experiment gate reports/qwen-gemma-experiment.json --require-policy --output-json reports/qwen-gemma-experiment-gate.json
```

## 2. Provider Setup

Start with local provider presets:

```bash
agentblaster providers add-preset --preset afm
agentblaster providers add-preset --preset lm-studio
agentblaster providers audit --policy agentblaster.policy.yaml --output-json reports/provider-audit.json
```

Declare capabilities only after the engine/version/model combination has been verified:

```bash
agentblaster providers capabilities enable --provider afm --capability streaming
agentblaster providers capabilities enable --provider afm --capability structured_output
agentblaster providers capabilities enable --provider afm --capability tool_calling
agentblaster providers capabilities enable --provider afm --capability trace_replay
agentblaster providers capabilities enable --provider afm --capability cancellation
```

Repeat capability declarations for other providers only when supported.

## 3. No-Dispatch Planning

```bash
agentblaster run \
  --matrix examples/matrices/qwen-gemma-local.yaml \
  --offline \
  --dry-run \
  --plan-json reports/qwen-gemma-local-plan.json

agentblaster run \
  --matrix examples/matrices/qwen-gemma-stress.yaml \
  --offline \
  --dry-run \
  --plan-json reports/qwen-gemma-stress-plan.json

agentblaster matrix pressure-audit \
  examples/matrices/qwen-gemma-stress.yaml \
  --output-json reports/qwen-gemma-stress-pressure.json

agentblaster matrix contract-checks \
  examples/matrices/qwen-gemma-local.yaml \
  --output-json reports/qwen-gemma-provider-contract-matrix-plan.json

agentblaster suite-audit --suite trace-replay --output-json reports/trace-replay-suite-audit.json
agentblaster suite-audit --suite agentic-tool-loop --output-json reports/agentic-tool-loop-suite-audit.json
agentblaster suite-audit --suite agent-fanout --output-json reports/agent-fanout-suite-audit.json
agentblaster suite-audit --suite prefill --output-json reports/prefill-suite-audit.json
agentblaster suite-audit --suite harness-engineering --output-json reports/harness-engineering-suite-audit.json
agentblaster harness review --suite trace-replay --output-json reports/trace-replay-harness-review.json
agentblaster harness review --suite agentic-tool-loop --output-json reports/agentic-tool-loop-harness-review.json
agentblaster harness review --suite agent-fanout --output-json reports/agent-fanout-harness-review.json
agentblaster harness review --suite prefill --output-json reports/prefill-harness-review.json
agentblaster harness review --suite harness-engineering --output-json reports/harness-engineering-harness-review.json
agentblaster suite-calibration --suite trace-replay --template-output reports/trace-replay-calibration.json
agentblaster suite-calibration --suite agentic-tool-loop --template-output reports/agentic-tool-loop-calibration.json
agentblaster suite-calibration --suite agent-fanout --template-output reports/agent-fanout-calibration.json
agentblaster suite-calibration --suite prefill --template-output reports/prefill-calibration.json
agentblaster suite-calibration --suite harness-engineering --template-output reports/harness-engineering-calibration.json

agentblaster providers readiness \
  --provider afm \
  --suite trace-replay \
  --model mlx-community/Qwen3.6-27B \
  --policy agentblaster.policy.yaml \
  --strict-unknown \
  --output-json reports/afm-trace-readiness.json

cat > reports/benchmark-readiness-inputs.txt <<'EOF'
afm-trace-readiness.json
EOF

agentblaster evidence campaign-preflight \
  --matrix examples/matrices/qwen-gemma-local.yaml \
  --matrix examples/matrices/qwen-gemma-stress.yaml \
  --policy agentblaster.policy.yaml \
  --benchmark-readiness-list reports/benchmark-readiness-inputs.txt \
  --output-dir campaign-preflight/qwen-gemma-local
```

Review plan output for:

- Provider/model/suite coverage.
- Capability failures or unknown capabilities.
- Prompt/output token estimates.
- Concurrency levels and raw trace mode.
- Model metadata consistency.
- Prefill/static-prefix/concurrency pressure for stress entries.
- Provider/model contract targets and required endpoint capabilities.
- Suite provenance, risk labels, capability surfaces, and dataset hygiene findings.
- Harness-engineering review status, assertion surfaces, and calibration requirements.
- Calibration templates for known-good, known-bad, failure-taxonomy, human-review, and release-gate approval evidence.
- Benchmark readiness dossier status and redacted provider-auth posture.

The campaign preflight bundle is the static handoff artifact for this review. It collects readiness, provider audit, policy normalization, artifact schemas, and matrix inventories without dispatching provider requests.
It also includes matrix pressure audits for prompt, prefill, static-prefix, output-token, and concurrency review.
Run the section 3 preflight command after `reports/afm-trace-readiness.json` exists so `campaign-preflight/qwen-gemma-local/readiness/benchmark-readiness-index.json` becomes available to dashboard review artifacts and claim readiness. Re-running campaign preflight rewrites generated artifacts in place and removes stale optional readiness/provider audit artifacts that are no longer requested.
The readiness list file resolves relative entries from the list file directory, so `afm-trace-readiness.json` inside `reports/benchmark-readiness-inputs.txt` points to `reports/afm-trace-readiness.json`.

## 4. Execution

```bash
agentblaster run \
  --matrix examples/matrices/qwen-gemma-local.yaml \
  --offline \
  --continue-on-error \
  --matrix-summary-json reports/qwen-gemma-local-summary.json

agentblaster run \
  --matrix examples/matrices/qwen-gemma-stress.yaml \
  --offline \
  --continue-on-error \
  --matrix-summary-json reports/qwen-gemma-stress-summary.json
```

Use `--continue-on-error` so partial matrix coverage is explicit rather than hidden.

## 5. Reports And Gates

```bash
agentblaster matrix report reports/qwen-gemma-local-summary.json --format html,md,json,pdf
agentblaster matrix scorecard reports/qwen-gemma-local-summary.json --format html,md,json,card,png,pdf
agentblaster matrix publication-bundle reports/qwen-gemma-local-summary.json --output-dir publication-bundles
agentblaster matrix gate reports/qwen-gemma-local-summary.json --require-all-runs-complete --max-failed-runs 0 --min-case-pass-rate 95 --max-failure-class engine_protocol_bug=0 --max-tool-loop-stop-reason max_tool_calls_reached=0 --output-json reports/qwen-gemma-local-gate.json
agentblaster matrix contract-checks examples/matrices/qwen-gemma-local.yaml --execute --output-json reports/qwen-gemma-provider-contract-matrix.json

agentblaster matrix report reports/qwen-gemma-stress-summary.json --format html,md,json,pdf
agentblaster matrix scorecard reports/qwen-gemma-stress-summary.json --format html,md,json,card,png,pdf
agentblaster matrix publication-bundle reports/qwen-gemma-stress-summary.json --output-dir publication-bundles
agentblaster matrix saturation-report reports/qwen-gemma-stress-summary.json --output-json reports/qwen-gemma-stress-saturation.json
agentblaster matrix gate reports/qwen-gemma-stress-summary.json --max-failed-runs 0 --min-case-pass-rate 95 --max-failure-class engine_protocol_bug=0 --max-tool-loop-stop-reason max_tool_calls_reached=0 --output-json reports/qwen-gemma-stress-gate.json
```

For stress runs, decide before execution whether `--require-all-runs-complete` is appropriate. Early hardware or engine comparison campaigns may intentionally allow partial stress coverage while still preserving failed entries in the summary.

## 6. Publication Evidence

```bash
agentblaster release provenance --output reports/release-provenance.json
agentblaster evidence bundle --policy agentblaster.policy.yaml --include-provider-audit --output-dir evidence
agentblaster selftest --tier normal --report-dir test-reports/selftest --run-id qwen-gemma-local-selftest
agentblaster selftest report --run qwen-gemma-local-selftest --base-dir test-reports/selftest --format html,json,junit
agentblaster providers metric-coverage --provider afm --output-json reports/afm-metric-coverage.json
agentblaster providers metric-coverage --provider lm-studio --output-json reports/lm-studio-metric-coverage.json
agentblaster suite-calibration --suite trace-replay --calibration reports/trace-replay-calibration.json --output-json reports/trace-replay-calibration-report.json
agentblaster suite-calibration --suite agentic-tool-loop --calibration reports/agentic-tool-loop-calibration.json --output-json reports/agentic-tool-loop-calibration-report.json
agentblaster suite-calibration --suite agent-fanout --calibration reports/agent-fanout-calibration.json --output-json reports/agent-fanout-calibration-report.json
agentblaster suite-calibration --suite prefill --calibration reports/prefill-calibration.json --output-json reports/prefill-calibration-report.json
agentblaster suite-calibration --suite harness-engineering --calibration reports/harness-engineering-calibration.json --output-json reports/harness-engineering-calibration-report.json
agentblaster engines improvement-plan \
  --engine afm \
  --pressure-audit reports/qwen-gemma-stress-pressure.json \
  --matrix-saturation-report reports/qwen-gemma-stress-saturation.json \
  --provider-contract-matrix reports/qwen-gemma-provider-contract-matrix.json \
  --matrix-gate reports/qwen-gemma-local-gate.json \
  --matrix-gate reports/qwen-gemma-stress-gate.json \
  --harness-review reports/trace-replay-harness-review.json \
  --harness-review reports/agentic-tool-loop-harness-review.json \
  --harness-review reports/agent-fanout-harness-review.json \
  --harness-review reports/prefill-harness-review.json \
  --harness-review reports/harness-engineering-harness-review.json \
  --metric-coverage reports/afm-metric-coverage.json \
  --metric-coverage reports/lm-studio-metric-coverage.json \
  --output-json reports/afm-improvement-plan.json
agentblaster cleanup-expired --runs runs --policy agentblaster.policy.yaml --output-json reports/qwen-gemma-retention-cleanup-plan.json --audit-log reports/qwen-gemma-cleanup-audit.jsonl --require-audit-log
agentblaster cleanup 'runs/<run-id>' --raw --reports --exports --caches --temp --bundles --policy agentblaster.policy.yaml --output-json reports/qwen-gemma-manual-cleanup-plan.json --audit-log reports/qwen-gemma-cleanup-audit.jsonl --require-audit-log
agentblaster evidence index \
  --name qwen-gemma-local \
  --artifact reports/qwen-gemma-experiment-gate.json \
  --artifact reports/qwen-gemma-provider-contract-matrix.json \
  --artifact reports/qwen-gemma-local-gate.json \
  --artifact reports/qwen-gemma-stress-gate.json \
  --artifact reports/qwen-gemma-local-summary-matrix-scorecard.json \
  --artifact reports/qwen-gemma-stress-summary-matrix-scorecard.json \
  --artifact reports/qwen-gemma-stress-pressure.json \
  --artifact reports/qwen-gemma-stress-saturation.json \
  --artifact campaign-preflight/qwen-gemma-local/manifest.json \
  --artifact campaign-preflight/qwen-gemma-local/readiness/benchmark-readiness-index.json \
  --artifact reports/release-provenance.json \
  --artifact reports/qwen-gemma-retention-cleanup-plan.json \
  --artifact test-reports/selftest/qwen-gemma-local-selftest/selftest-report.json \
  --artifact reports/trace-replay-suite-audit.json \
  --artifact reports/agentic-tool-loop-suite-audit.json \
  --artifact reports/agent-fanout-suite-audit.json \
  --artifact reports/prefill-suite-audit.json \
  --artifact reports/harness-engineering-suite-audit.json \
  --artifact reports/trace-replay-harness-review.json \
  --artifact reports/agentic-tool-loop-harness-review.json \
  --artifact reports/agent-fanout-harness-review.json \
  --artifact reports/prefill-harness-review.json \
  --artifact reports/harness-engineering-harness-review.json \
  --artifact reports/trace-replay-calibration-report.json \
  --artifact reports/agentic-tool-loop-calibration-report.json \
  --artifact reports/agent-fanout-calibration-report.json \
  --artifact reports/prefill-calibration-report.json \
  --artifact reports/harness-engineering-calibration-report.json \
  --artifact reports/afm-metric-coverage.json \
  --artifact reports/lm-studio-metric-coverage.json \
  --artifact reports/afm-improvement-plan.json \
  --output-json reports/qwen-gemma-evidence-index.json
agentblaster release qualification-bundle \
  --name qwen-gemma-local \
  --evidence-bundle evidence/*.agentblaster-evidence.zip \
  --provider-contract-matrix reports/qwen-gemma-provider-contract-matrix.json \
  --matrix-gate reports/qwen-gemma-local-gate.json \
  --matrix-gate reports/qwen-gemma-stress-gate.json \
  --engine-advisory reports/afm-improvement-plan.json \
  --matrix-pressure-audit reports/qwen-gemma-stress-pressure.json \
  --matrix-saturation-report reports/qwen-gemma-stress-saturation.json \
  --release-provenance reports/release-provenance.json \
  --matrix-publication-bundle publication-bundles/qwen-gemma-local-summary.agentblaster-matrix-publication.zip \
  --matrix-publication-bundle publication-bundles/qwen-gemma-stress-summary.agentblaster-matrix-publication.zip \
  --matrix-scorecard reports/qwen-gemma-local-summary-matrix-scorecard.json \
  --matrix-scorecard reports/qwen-gemma-stress-summary-matrix-scorecard.json \
  --implementation-status reports/implementation-status.json \
  --campaign-preflight-manifest campaign-preflight/qwen-gemma-local/manifest.json \
  --benchmark-readiness-list reports/benchmark-readiness-inputs.txt \
  --evidence-index reports/qwen-gemma-evidence-index.json \
  --suite-audit reports/trace-replay-suite-audit.json \
  --suite-audit reports/agentic-tool-loop-suite-audit.json \
  --suite-audit reports/agent-fanout-suite-audit.json \
  --suite-audit reports/prefill-suite-audit.json \
  --suite-audit reports/harness-engineering-suite-audit.json \
  --harness-review reports/trace-replay-harness-review.json \
  --harness-review reports/agentic-tool-loop-harness-review.json \
  --harness-review reports/agent-fanout-harness-review.json \
  --harness-review reports/prefill-harness-review.json \
  --harness-review reports/harness-engineering-harness-review.json \
  --suite-calibration-report reports/trace-replay-calibration-report.json \
  --suite-calibration-report reports/agentic-tool-loop-calibration-report.json \
  --suite-calibration-report reports/agent-fanout-calibration-report.json \
  --suite-calibration-report reports/prefill-calibration-report.json \
  --suite-calibration-report reports/harness-engineering-calibration-report.json \
  --metric-coverage reports/afm-metric-coverage.json \
  --metric-coverage reports/lm-studio-metric-coverage.json \
  --selftest-report test-reports/selftest/qwen-gemma-local-selftest/selftest-report.json \
  --output-dir release-bundles
agentblaster security scan release-bundles/qwen-gemma-local.agentblaster-release-qualification.zip --output-json reports/qwen-gemma-redaction-scan.json
agentblaster release claim-readiness \
  --name qwen-gemma-local \
  --experiment-manifest reports/qwen-gemma-experiment.json \
  --experiment-gate reports/qwen-gemma-experiment-gate.json \
  --provider-contract-matrix reports/qwen-gemma-provider-contract-matrix.json \
  --matrix-gate reports/qwen-gemma-local-gate.json \
  --matrix-gate reports/qwen-gemma-stress-gate.json \
  --telemetry-audit reports/qwen-gemma-telemetry-audit.json \
  --matrix-pressure-audit reports/qwen-gemma-stress-pressure.json \
  --matrix-saturation-report reports/qwen-gemma-stress-saturation.json \
  --release-provenance reports/release-provenance.json \
  --release-qualification-bundle release-bundles/qwen-gemma-local.agentblaster-release-qualification.zip \
  --redaction-scan reports/qwen-gemma-redaction-scan.json \
  --evidence-index reports/qwen-gemma-evidence-index.json \
  --engine-advisory reports/afm-improvement-plan.json \
  --suite-audit reports/trace-replay-suite-audit.json \
  --suite-audit reports/agentic-tool-loop-suite-audit.json \
  --suite-audit reports/agent-fanout-suite-audit.json \
  --suite-audit reports/prefill-suite-audit.json \
  --suite-audit reports/harness-engineering-suite-audit.json \
  --harness-review reports/trace-replay-harness-review.json \
  --harness-review reports/agentic-tool-loop-harness-review.json \
  --harness-review reports/agent-fanout-harness-review.json \
  --harness-review reports/prefill-harness-review.json \
  --harness-review reports/harness-engineering-harness-review.json \
  --suite-calibration-report reports/trace-replay-calibration-report.json \
  --suite-calibration-report reports/agentic-tool-loop-calibration-report.json \
  --suite-calibration-report reports/agent-fanout-calibration-report.json \
  --suite-calibration-report reports/prefill-calibration-report.json \
  --suite-calibration-report reports/harness-engineering-calibration-report.json \
  --metric-coverage reports/afm-metric-coverage.json \
  --metric-coverage reports/lm-studio-metric-coverage.json \
  --matrix-publication-bundle publication-bundles/qwen-gemma-local-summary.agentblaster-matrix-publication.zip \
  --matrix-publication-bundle publication-bundles/qwen-gemma-stress-summary.agentblaster-matrix-publication.zip \
  --matrix-scorecard reports/qwen-gemma-local-summary-matrix-scorecard.json \
  --matrix-scorecard reports/qwen-gemma-stress-summary-matrix-scorecard.json \
  --implementation-status reports/implementation-status.json \
  --benchmark-readiness-list reports/benchmark-readiness-inputs.txt \
  --campaign-preflight-manifest campaign-preflight/qwen-gemma-local/manifest.json \
  --selftest-report test-reports/selftest/qwen-gemma-local-selftest/selftest-report.json \
  --output-json reports/qwen-gemma-claim-readiness.json
```

Before external publication, include:

- Matrix summary JSON.
- Matrix report and scorecard JSON/SVG/PNG/PDF artifacts.
- Gate reports.
- Provider contract matrix.
- Matrix pressure and saturation reports.
- Provider audit.
- Policy file.
- Release provenance.
- Metric coverage reports.
- Suite audit reports.
- Harness review reports.
- Suite calibration reports when suites are promoted to release-gate evidence.
- AgentBlaster selftest report.
- Redaction scan output.
- Notes for skipped, failed, or partial matrix entries.

## 7. Dashboard Review

```bash
agentblaster dashboard --runs runs --host 127.0.0.1 --port 8765 --policy agentblaster.policy.yaml --auth-token-env AGENTBLASTER_DASHBOARD_TOKEN
```

Useful dashboard APIs:

- `GET /api/runs`
- `GET /api/runs/<run-id>`
- `GET /api/runs/<run-id>/events`
- `POST /api/run-plan`
- `POST /api/runs`

Use `/api/run-plan` before `/api/runs` when collecting GUI evidence.
