# Benchmark Readiness Dossiers

A readiness dossier is a no-network preflight artifact for one provider, suite, and model target. It combines security policy posture, provider audit findings, suite capability requirements, planned contract checks, and metric coverage.

Generate a dossier before running a benchmark:

```bash
agentblaster providers readiness \
  --provider afm \
  --suite trace-replay \
  --model mlx-community/Qwen3.6-27B \
  --policy agentblaster.policy.yaml \
  --strict-unknown \
  --output-json reports/afm-trace-readiness.json
```

The command does not contact endpoints, resolve API keys, read raw traces, or execute providers. It exits non-zero when a blocking readiness issue is found, such as a policy violation, missing required suite capability, strict unknown capability, or missing model id.

Readiness dossiers are useful release evidence because they show whether a planned benchmark was allowed by policy, compatible with declared provider capabilities, covered by contract-check planning, and transparent about metric comparability gaps.
