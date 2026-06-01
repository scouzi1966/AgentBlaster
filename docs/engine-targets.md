# AgentBlaster Engine Target Catalog

AgentBlaster standardizes local and remote benchmark planning through engine targets. A target joins provider presets, launch recipes, API contracts, telemetry mapping expectations, recommended suites, security notes, and Qwen/Gemma model targets into one static planning artifact.

## Target Families

- `afm-mlx`: primary local AFM MLX target for making AFM the best local AI baseline.
- `mlx-lm`: MLX-LM reference local server.
- `ollama-mlx`: Ollama OpenAI-compatible and native profiles, with native timing normalization.
- `rapid-mlx`: Rapid MLX OpenAI-compatible candidate target.
- `omlx`: oMLX OpenAI-compatible candidate target.
- `vllm-mlx`: vLLM-MLX OpenAI-compatible and Anthropic-compatible candidate target.
- `lm-studio`: LM Studio Chat, Responses, Anthropic-compatible, and native surfaces.
- `remote-openai-compatible`: internet-facing OpenAI-compatible APIs with explicit API key and policy controls.
- `remote-anthropic-compatible`: internet-facing Anthropic-compatible APIs with explicit API key and policy controls.

## Standardization Metadata

Every target now carries a `standardization` block so downstream launch, dashboard, claim-readiness, and media workflows do not infer benchmark intent from prose. The block declares the primary scoring contract, contract priority, representative local-agent profiles, workflow surfaces, prefill challenges, concurrency challenges, native telemetry profiles, and native metric claim policy.

The representative agent profile baseline is `opencode`, `openclaw`, `hermes`, and `pi`. These are workload shapes, not third-party framework executions. Generated profile suites stay deterministic and do not install or call those projects.

The standard workflow surfaces are `openai-anthropic-tool-calling`, `mcp-fixtures`, `skill-packs`, `lcp-emerging`, and `harness-engineering`. This keeps local AFM, mlx-lm, Ollama, Rapid MLX, oMLX, vLLM-MLX, LM Studio, and remote contract endpoints comparable against the same agentic pressure categories.

Native stats are publishable only when the target declares an explicit telemetry profile and metric coverage marks the relevant family as comparable. Missing native TTFT, prefill, cache, or decode stats must remain `null` or `unsupported`; reports should not infer them from generic usage.

## Commands

```bash
agentblaster engines targets
agentblaster engines targets --target afm-mlx --format json
agentblaster engines targets --format markdown --output reports/engine-targets.md
agentblaster engines improvement-plan --engine afm --pressure-audit reports/qwen-gemma-stress-pressure.json --matrix-saturation-report reports/qwen-gemma-matrix-saturation.json --provider-contract-matrix reports/qwen-gemma-provider-contract-matrix.json --telemetry-audit reports/afm-telemetry-audit.json --metric-coverage reports/afm-metric-coverage.json --matrix-gate reports/qwen-gemma-matrix-gate.json --harness-review reports/harness-orchestration-review.json --output-json reports/afm-improvement-plan.json
```

## Recommended Baseline

The initial comparison campaign should cross each configured local provider with these model targets:

- `qwen3.6-27b-dense`
- `gemma-4-31b-dense`

The recommended baseline suites are `smoke`, `structured`, `toolcall`, `toolsim`, `trace-replay`, `agent-fanout`, `prefill`, `cache-control`, and `cancellation`. Generated harness profiles such as `concurrency`, `cancellation`, `metamorphic`, `contract-fuzz`, `cache-replay`, `orchestration`, `emerging-workflows`, and `judge-rubric` should be layered on after provider contract checks and metric coverage are understood.

## Evidence-Driven Improvement Plans

`agentblaster engines improvement-plan` turns static review artifacts into engine roadmap priorities. For AFM, use it after pressure audits, saturation reports, executed provider contract checks or contract matrices, telemetry audits, metric coverage, `agentblaster.matrix-gate.v1` matrix gates, and `agentblaster.harness-review.v1` generated-suite reviews are available. The output identifies prefill/cache pressure, measured scheduler/concurrency saturation, compact concurrency evidence such as queue/rate-limit pressure entries, OpenAI/Responses/Anthropic contract-conformance gaps, contract capability evidence such as direct probes, judge-rubric proxy coverage, and uncovered prompt-caching evidence, telemetry instrumentation gaps, metric claim-contract disclosure and leaderboard-readiness gaps, failure-class remediation priorities, agentic protocol-repair priorities from invalid tool-call and parser-repair gate failures, harness calibration requirements, evidence-integrity problems such as stale matrix-gate or harness-review schemas, and failing benchmark gates without contacting providers or reading raw traces.

## Security Posture

The catalog is static and does not execute launch commands, probe engines, read API keys, contact remote APIs, or inspect local model caches. Remote targets require explicit provider configuration with `api_key_ref`, enterprise policy opt-in, cost ceilings, rate limits, TLS verification, and redaction-safe reporting.
