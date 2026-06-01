# Experiment Manifests

Experiment manifests describe benchmark intent before execution. They are static planning artifacts for corporate review, media-supporting benchmark campaigns, and release qualification.

## Create A Manifest

```bash
agentblaster experiment manifest \
  --name qwen-gemma-local \
  --objective "Compare AFM and LM Studio on Qwen/Gemma local-agent suites." \
  --providers afm,lm-studio \
  --targets qwen3.6-27b-dense,gemma-4-31b-dense \
  --suites trace-replay,agent-fanout,prefill \
  --policy agentblaster.policy.yaml \
  --matrix examples/matrices/qwen-gemma-stress.yaml \
  --output reports/qwen-gemma-experiment.json
```

The manifest records scope, required preflight artifacts, acceptance gates, publication rules, and redaction/security notes. It does not contact providers, resolve API keys, or execute benchmarks.

Campaign preflight bundles add matrix-level no-dispatch evidence before the run. Each matrix inventory includes the planned suite capability requirements, per-case capability surfaces, prefill pressure, shared static-prefix groups, potential cache-reuse tokens, and per-case prompt surfaces, so generated harnesses such as `judge-rubric`, `cache-replay`, `orchestration`, `emerging-workflows`, and `cancellation` expose their structured-output, prompt-caching, MCP/LCP/skills, tool-loop, cancellation, and prefill/cache pressure before provider dispatch.

## Gate A Manifest

```bash
agentblaster experiment gate reports/qwen-gemma-experiment.json --require-policy --output-json reports/qwen-gemma-experiment-gate.json
```

Use this before dispatching a matrix so incomplete experiment definitions are blocked early. Runtime results are still governed by matrix gates, comparison gates, redaction scans, and release qualification bundles after execution.

## Claim Readiness

After execution and evidence assembly, use `agentblaster release claim-readiness` to gate the complete claim package. It ties the original experiment manifest/gate to executed provider contract checks or an executed provider contract matrix, matrix gates, telemetry audits, matrix pressure audits, matrix saturation reports, lifecycle cleanup evidence through the evidence index, release provenance, redaction scans, run publication-bundle readiness, and the release qualification bundle.

The claim-readiness report is still no-dispatch. It proves the review package is structurally complete; it does not rerun benchmarks or replace validation.
