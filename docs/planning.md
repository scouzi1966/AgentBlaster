# AgentBlaster Dry-Run Planning

Dry-run planning validates and summarizes a run before any provider request is sent or run artifact directory is created.

## Single Run

```bash
agentblaster run \
  --suite smoke \
  --engine afm \
  --model mlx-community/Qwen3.6-27B \
  --dry-run \
  --plan-json reports/afm-smoke-plan.json
```

The plan includes:

- Provider, suite, model, contract, raw-trace mode, remote flag, and concurrency.
- Policy and capability preflight results.
- Estimated prompt tokens per case and total.
- Maximum output-token budget per case and total.
- Estimated cost when the provider profile includes a cost model.
- Case-level streaming, tool, simulated-tool, MCP, skill, and tag metadata.

## Matrix Run

```bash
agentblaster run \
  --matrix examples/matrices/qwen-gemma-local.yaml \
  --offline \
  --dry-run \
  --plan-json reports/qwen-gemma-plan.json
```

Matrix dry-run writes a JSON list of per-run plans.

Executed matrices can also write a durable execution summary:

```bash
agentblaster run \
  --matrix examples/matrices/qwen-gemma-local.yaml \
  --offline \
  --continue-on-error \
  --matrix-summary-json reports/qwen-gemma-matrix-summary.json
```

The matrix execution summary is a JSON artifact with:

- Matrix name, source path, description, creation timestamp, and schema version.
- Total run entries, attempted entries, completed entries, and failed entries.
- One row per attempted matrix entry with engine, provider, model, suite, pass/fail counts, concurrency, and either per-run artifact paths or error details.
- `attempted_runs` and `continue_on_error` fields so CI and report consumers can distinguish fail-fast runs from partial matrix runs.

Matrix execution also evaluates aggregate policy ceilings before dispatch. `max_matrix_runs` limits provider/model matrix width, `max_matrix_total_cases` limits the sum of resolved suite cases across all matrix entries, and `max_estimated_matrix_cost_usd` can cap aggregate estimated spend when all referenced providers define cost models.

Cost estimates come from provider cost models configured with `agentblaster providers cost set`. If a cost ceiling is active and a referenced provider lacks input/output token rates, the run or matrix fails before dispatch instead of silently estimating zero cost.

Use `--plan-json` for dry-run planning and `--matrix-summary-json` for executed matrix reporting. The execution summary intentionally avoids raw responses and secrets so it can be attached to CI runs, media-supporting evidence bundles, and corporate benchmark reports.

Generate shareable matrix-level reports from the summary:

```bash
agentblaster matrix report reports/qwen-gemma-matrix-summary.json --format html,md,json
agentblaster matrix gate reports/qwen-gemma-matrix-summary.json --require-all-runs-complete --max-failed-runs 0 --min-case-pass-rate 95
```

## Failure Behavior

Dry-run uses the same pre-dispatch checks as a real run:

- Enterprise policy failures stop the plan.
- Explicitly missing suite-required capabilities stop the plan.
- Unknown capabilities are allowed unless `--strict-unknown-capabilities` is set or the matrix entry enables `strict_unknown_capabilities`.

Use `--no-capability-preflight` only when intentionally exploring how a provider fails at runtime.


## Prompt Footprint Analysis

Use `suite-footprint` when you need a deeper prompt/prefix breakdown than a dry-run plan provides:

```bash
agentblaster suite-footprint --suite trace-replay --output-json reports/trace-replay-footprint.json
```

The footprint report separates system prompts, user prompts, trace messages, tool schemas, simulated tools, MCP catalogs, and skill text. This helps explain prefill pressure and prompt-cache opportunities before running expensive or hardware-sensitive matrices.


## Cache-Control Planning

Use the built-in `cache-control` suite when evaluating repeated static-prefix behavior and provider cache accounting:

```bash
agentblaster suite-footprint --suite cache-control --output-json reports/cache-control-footprint.json
```

Cases can declare `cache_control` metadata. Anthropic-compatible adapters serialize it on the static system prefix; other adapters retain it as benchmark metadata for planning and reporting.
