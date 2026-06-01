# AgentBlaster Examples

These examples are checked-in starter artifacts. They are safe to inspect and edit manually; running them still depends on local provider profiles and policy.

## Matrices

- `matrices/local-smoke.yaml`: minimal local smoke matrix for AFM and LM Studio.
- `matrices/qwen-gemma-local.yaml`: Qwen/Gemma trace-replay baseline across AFM and LM Studio.
- `matrices/qwen-gemma-stress.yaml`: starter agentic stress matrix across Qwen/Gemma, AFM/LM Studio, `agentic-tool-loop`, `agent-fanout`, `prefill`, `trace-replay`, and concurrency `1`/`4`.

Dry-run a matrix before execution:

```bash
agentblaster run \
  --matrix examples/matrices/qwen-gemma-stress.yaml \
  --offline \
  --dry-run \
  --plan-json reports/qwen-gemma-stress-plan.json
```

Execute with partial-summary capture:

```bash
agentblaster run \
  --matrix examples/matrices/qwen-gemma-stress.yaml \
  --offline \
  --continue-on-error \
  --matrix-summary-json reports/qwen-gemma-stress-summary.json
```

For a broader stress run, regenerate the matrix:

```bash
agentblaster models stress-matrix \
  --providers afm,lm-studio \
  --targets qwen3.6-27b-dense,gemma-4-31b-dense \
  --suites agentic-tool-loop,agent-fanout,prefill,trace-replay \
  --concurrency-levels 1,2,4,8 \
  --output examples/matrices/qwen-gemma-stress.yaml
```

## Suites

Suite examples mirror built-in workload families and are useful when testing custom YAML editing, policy review, and suite audit flows.
