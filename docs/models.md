# AgentBlaster Model Targets

AgentBlaster uses canonical model targets to keep cross-engine comparisons honest. A target defines the intended model family, density, parameter scale, default model identifier, and metadata that should be written into run manifests.

## Initial Targets

- `qwen3.6-27b-dense`: Qwen3.6 27B dense target for local coding and agentic workflows.
- `gemma-4-31b-dense`: Gemma 4 31B dense target for dense-quality comparisons.

List targets:

```bash
agentblaster models targets
agentblaster models show qwen3.6-27b-dense
```

## Matrix Generation

Generate a provider x model matrix:

```bash
agentblaster models matrix \
  --providers afm,lm-studio \
  --targets qwen3.6-27b-dense,gemma-4-31b-dense \
  --suite trace-replay \
  --concurrency 1 \
  --output examples/matrices/qwen-gemma-local.yaml
```

Run the generated matrix:

```bash
agentblaster run \
  --matrix examples/matrices/qwen-gemma-local.yaml \
  --offline \
  --continue-on-error \
  --matrix-summary-json reports/qwen-gemma-matrix-summary.json

agentblaster matrix report reports/qwen-gemma-matrix-summary.json --format html,md,json
```

The matrix summary JSON provides a stable index of attempted Qwen/Gemma x provider runs. Completed entries link to per-run manifests, result rows, and summary artifacts. Failed entries produced under `--continue-on-error` record error type/message, zero cases, and no raw artifacts so reports can show partial coverage without hiding failed matrix cells.

## Stress Matrix Generation

Generate a concurrency and prefill stress matrix across providers, model targets, suites, and concurrency levels:

```bash
agentblaster models stress-matrix \
  --providers afm,lm-studio \
  --targets qwen3.6-27b-dense,gemma-4-31b-dense \
  --suites prefill,trace-replay \
  --concurrency-levels 1,2,4,8 \
  --output examples/matrices/qwen-gemma-stress.yaml \
  --summary-json reports/qwen-gemma-stress-plan.json
```

The generated matrix disables raw traces by default and varies `concurrency` per run so queueing, cache pressure, prompt prefill, and trace replay behavior can be compared consistently.

## Campaign Plans

Create a no-network multi-suite campaign plan for the canonical local-engine comparison:

```bash
agentblaster models campaign-plan \
  --providers afm,mlx-lm,ollama,ollama-native,lm-studio,rapid-mlx,omlx \
  --targets qwen3.6-27b-dense,gemma-4-31b-dense \
  --suites smoke,structured,toolcall,toolsim,trace-replay,prefill,cache-control,lcp-context \
  --policy agentblaster.policy.yaml \
  --output-dir campaigns/qwen-gemma-local
```

The campaign plan writes a combined matrix, `campaign-plan.json`, and a runbook with static preflight catalog commands, readiness dossier commands, offline matrix dry-run/execution commands, matrix reports, matrix scorecards, and matrix gates. Generation does not contact providers, store secrets, or execute benchmarks. Generated matrix entries disable raw traces by default.

## Benchmark Kits

Create a no-network benchmark kit for the initial Qwen/Gemma comparison campaign:

```bash
agentblaster models benchmark-kit \
  --providers afm,lm-studio \
  --targets qwen3.6-27b-dense,gemma-4-31b-dense \
  --suite trace-replay \
  --policy agentblaster.policy.yaml \
  --output-dir benchmark-kits/qwen-gemma-local
```

The kit writes a matrix YAML, a JSON manifest, readiness-dossier command list, report/gate command templates, and a Markdown runbook. Kit generation does not contact providers. Generated run commands default to `--offline` and raw traces disabled.

## Notes

The default model identifiers are starting points. Provider profiles and matrix files can still override exact model IDs to match local naming conventions, quantized artifacts, or model cache paths.

The important invariant is that generated run manifests carry comparable `model_metadata` fields so reports can distinguish model family, architecture, chat template, quantization, tokenizer, and context length when known.

## Engine Target Catalog

Use `agentblaster engines targets` to see which engines should be crossed with the Qwen/Gemma targets, which provider presets and launch recipes apply, and which telemetry mappings should be expected before comparisons are published.
