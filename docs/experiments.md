# Experiment Manifests

Experiment manifests describe benchmark intent before execution. They are static planning artifacts for corporate review, media-supporting benchmark campaigns, and release qualification.

## Create A Manifest

```bash
agentblaster experiment manifest \
  --name qwen-gemma-local \
  --objective "Compare AFM and LM Studio on Qwen/Gemma local-agent suites." \
  --providers afm,lm-studio \
  --targets qwen3.6-27b-dense,gemma-4-31b-dense \
  --suites trace-replay,prefill \
  --policy agentblaster.policy.yaml \
  --matrix examples/matrices/qwen-gemma-stress.yaml \
  --output reports/qwen-gemma-experiment.json
```

The manifest records scope, required preflight artifacts, acceptance gates, publication rules, and redaction/security notes. It does not contact providers, resolve API keys, or execute benchmarks.

## Gate A Manifest

```bash
agentblaster experiment gate reports/qwen-gemma-experiment.json --require-policy --output-json reports/qwen-gemma-experiment-gate.json
```

Use this before dispatching a matrix so incomplete experiment definitions are blocked early. Runtime results are still governed by matrix gates, comparison gates, redaction scans, and release qualification bundles after execution.
