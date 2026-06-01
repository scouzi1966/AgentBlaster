# AgentBlaster Engine Target Catalog

AgentBlaster standardizes local and remote benchmark planning through engine targets. A target joins provider presets, launch recipes, API contracts, telemetry mapping expectations, recommended suites, security notes, and Qwen/Gemma model targets into one static planning artifact.

## Target Families

- `afm-mlx`: primary local AFM MLX target for making AFM the best local AI baseline.
- `mlx-lm`: MLX-LM reference local server.
- `ollama-mlx`: Ollama OpenAI-compatible and native profiles, with native timing normalization.
- `rapid-mlx`: Rapid MLX OpenAI-compatible candidate target.
- `omlx`: oMLX OpenAI-compatible candidate target.
- `lm-studio`: LM Studio Chat, Responses, and native surfaces.
- `remote-openai-compatible`: internet-facing OpenAI-compatible APIs with explicit API key and policy controls.
- `remote-anthropic-compatible`: internet-facing Anthropic-compatible APIs with explicit API key and policy controls.

## Commands

```bash
agentblaster engines targets
agentblaster engines targets --target afm-mlx --format json
agentblaster engines targets --format markdown --output reports/engine-targets.md
```

## Recommended Baseline

The initial comparison campaign should cross each configured local provider with these model targets:

- `qwen3.6-27b-dense`
- `gemma-4-31b-dense`

The recommended baseline suites are `smoke`, `structured`, `toolcall`, `toolsim`, `trace-replay`, `prefill`, and `cache-control`. Generated harness profiles such as `concurrency`, `metamorphic`, `contract-fuzz`, and `cache-replay` should be layered on after provider contract checks and metric coverage are understood.

## Security Posture

The catalog is static and does not execute launch commands, probe engines, read API keys, contact remote APIs, or inspect local model caches. Remote targets require explicit provider configuration with `api_key_ref`, enterprise policy opt-in, cost ceilings, rate limits, TLS verification, and redaction-safe reporting.
