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

Readiness output includes contract capability evidence from the plan-only provider contract checks. It separates directly checked capabilities, proxy evidence such as `judge_rubric` through `structured_output`, and capabilities not covered by contract checks such as Anthropic prompt caching.

Readiness output also includes a redacted `provider_auth_posture` section and a static `secret_backend_posture` section derived from provider audit evidence. It reports only secret-reference kind and backend posture: whether an API-key reference is configured, whether the backend is writable by AgentBlaster (`keyring` or `dotenv`), whether it is a plaintext dotenv fallback, whether pre-write policy guarding is recommended before storing secret material, whether keyring support is optional/available by dependency discovery, and which enterprise backends are recommended. It does not read keyring values or secret values.

Release qualification bundles and claim-readiness reports accept readiness dossiers with `--benchmark-readiness`; generated campaign list files can be passed with `--benchmark-readiness-list` to campaign preflight, release qualification, and claim readiness. List files use one raw path per line, ignore blank/comment lines, reject inline comments and shell-style quoted paths, and resolve relative paths from the list file directory. Evidence indexes and the dashboard review panel surface compact `benchmark_readiness_summaries` without copying raw provider configs, API keys, request headers, prompts, traces, or endpoint payloads.

Readiness dossiers are useful release evidence because they show whether a planned benchmark was allowed by policy, compatible with declared provider capabilities, covered by contract-check planning, and transparent about metric comparability gaps.
