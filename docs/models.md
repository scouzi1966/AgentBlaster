# AgentBlaster Model Targets

AgentBlaster uses canonical model targets to keep cross-engine comparisons honest. A target defines the intended model family, density, parameter scale, default model identifier, comparison group, publication metadata requirements, and metadata that should be written into run manifests.

## Initial Targets

- `qwen3.6-27b-dense`: Qwen3.6 27B dense target for local coding and agentic workflows.
- `gemma-4-31b-dense`: Gemma 4 31B dense target for dense-quality comparisons.

List targets:

```bash
agentblaster models targets
agentblaster models show qwen3.6-27b-dense
```

`models targets` prints each canonical target with the default model, architecture, parameter scale, density, display name, comparison group, and comma-separated release metadata fields required for publication. `models show` expands the same target with publication guidance so operators can see charting and disclosure constraints before running a campaign.

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
  --suites agentic-tool-loop,agent-fanout,prefill,harness-engineering,trace-replay \
  --concurrency-levels 1,2,4,8 \
  --output examples/matrices/qwen-gemma-stress.yaml \
  --summary-json reports/qwen-gemma-stress-plan.json
```

The generated matrix disables raw traces by default and varies `concurrency` per run so queueing, agent fan-out, cache pressure, prompt prefill, and trace replay behavior can be compared consistently.

A checked-in starter is available at `examples/matrices/qwen-gemma-stress.yaml`. It intentionally uses concurrency levels `1` and `4` to keep first runs manageable while still exercising low/high queueing behavior. Regenerate it with wider `1,2,4,8` levels when preparing a full stress campaign.

## Campaign Plans

Create a no-network multi-suite campaign plan for the canonical local-engine comparison:

```bash
agentblaster models campaign-plan \
  --providers afm,mlx-lm,ollama,ollama-native,lm-studio,rapid-mlx,omlx,vllm-mlx \
  --targets qwen3.6-27b-dense,gemma-4-31b-dense \
  --suites smoke,structured,toolcall,toolsim,agentic-tool-loop,trace-replay,agent-fanout,prefill,harness-engineering,cache-control,cancellation,lcp-context \
  --policy agentblaster.policy.yaml \
  --output-dir campaigns/qwen-gemma-local
```

The campaign plan writes a combined matrix, `campaign-plan.json`, `reports/benchmark-readiness-inputs.txt`, and a runbook with static preflight catalog commands, provider-audit security posture, readiness dossier commands, campaign-preflight generation, provider contract-matrix planning/execution commands, offline matrix dry-run/execution commands, matrix reports, matrix scorecards including SVG/PNG/PDF outputs, matrix publication bundles, matrix gates, experiment manifest/gate commands, matrix pressure and saturation reports, per-suite suite-audit governance reports, per-suite harness-review artifacts for emerging harness-engineering review, suite-calibration templates and strict calibration-report command slots, per-provider metric coverage reports, deterministic AgentBlaster selftest evidence, static SDLC validation-manifest evidence, per-provider engine improvement advisories, an evidence-index command that includes provider-audit, benchmark, suite-governance, harness-engineering, calibration, and app-harness evidence, release qualification and redaction-scan commands, claim-readiness and publication-brief commands, and a final archival release bundle command that packages the claim readiness report, publication brief, provider audit, and SDLC manifest in compact redaction-safe form. Readiness dossier output paths are listed under `publication_artifacts.benchmark_readiness_reports` for single-artifact `--benchmark-readiness` inputs, while `publication_artifacts.benchmark_readiness_input_list` can be reused with `--benchmark-readiness-list` for campaign preflight, release qualification, and claim readiness. Generation does not contact providers, store secrets, or execute benchmarks. Generated matrix entries disable raw traces by default.

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

The kit writes a matrix YAML, a JSON manifest, readiness-dossier command list, provider contract-matrix commands, report/gate command templates, and a Markdown runbook. Kit generation does not contact providers. Generated run commands default to `--offline` and raw traces disabled.

## Checked-In Campaign Handoff

The initial AFM-vs-LM-Studio Qwen/Gemma handoff is checked in at `campaigns/qwen-gemma-local/README.md` with a structured companion file at `campaigns/qwen-gemma-local/campaign-handoff.json`.

Use this when you want a ready operator checklist rather than generating a new campaign directory. The handoff covers environment readiness, provider setup, dry-run planning, suite governance audits, harness-engineering review, suite calibration, provider contract matrices, execution, matrix reports, matrix scorecards, matrix publication bundles, matrix gates, saturation reports, release provenance, evidence bundles, claim readiness, redaction scan, and dashboard review.

## Notes

The default model identifiers are starting points. Provider profiles and matrix files can still override exact model IDs to match local naming conventions, quantized artifacts, or model cache paths.

The important invariant is that generated run manifests carry comparable `model_metadata` fields so reports can distinguish model family, architecture, chat template, quantization, tokenizer, and context length when known.

For release and media-facing comparisons, each canonical target also declares:

- `comparison_group`: the family/architecture bucket that should be charted together.
- `required_release_metadata`: fields reviewers should expect before treating two runs as equivalent model comparisons.
- `publication_guidance`: warnings that Qwen and Gemma primary charts should remain separate, and that revision/quantization classes must be disclosed before cross-engine claims.

## Engine Target Catalog

Use `agentblaster engines targets` to see which engines should be crossed with the Qwen/Gemma targets, which provider presets and launch recipes apply, and which telemetry mappings should be expected before comparisons are published.
