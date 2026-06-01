# AgentBlaster Providers

Provider profiles describe inference endpoints without storing raw API keys. Profiles can target local MLX engines, local OpenAI-compatible servers, internet-facing OpenAI-compatible APIs, Anthropic-compatible APIs, or engine-native APIs.

## Built-In Presets

List built-in presets:

```bash
agentblaster providers presets
```

Local presets:

- `afm`
- `mlx-lm`
- `ollama`
- `ollama-native`
- `lm-studio`
- `lm-studio-responses`
- `lm-studio-native`
- `omlx`
- `rapid-mlx`
- `vllm-mlx`

Internet-facing presets:

- `openai`: OpenAI Chat Completions-compatible endpoint, using `OPENAI_API_KEY`.
- `openai-responses`: OpenAI Responses endpoint, using `OPENAI_API_KEY`.
- `anthropic`: Anthropic Messages endpoint, using `ANTHROPIC_API_KEY`.

## Secure Remote Onboarding Plans

Generate a redaction-safe onboarding plan before creating internet-facing provider profiles:

```bash
agentblaster providers onboarding \
  --preset openai \
  --name openai-workspace \
  --secret-mode env \
  --api-key-env WORKSPACE_OPENAI_KEY \
  --model <openai-model> \
  --policy agentblaster.policy.yaml \
  --format markdown \
  --output reports/openai-workspace-onboarding.md

agentblaster providers onboarding \
  --preset anthropic \
  --name anthropic-prod \
  --secret-mode keyring \
  --model <anthropic-model> \
  --format json \
  --output reports/anthropic-prod-onboarding.json
```

The onboarding command does not store secrets, modify provider config, contact endpoints, or write keyring entries. It produces reviewable commands for secret preparation, provider registration, auth status/test, cost model setup, rate limits, provider audit, readiness, contract-check planning, and a no-raw-traces smoke run. Use it as the first artifact in corporate approvals for remote OpenAI-compatible and Anthropic-compatible providers.

## Add Providers

Local AFM:

```bash
agentblaster providers add-preset --preset afm
```

OpenAI API with the default environment-variable reference:

```bash
export OPENAI_API_KEY=...
agentblaster providers add-preset --preset openai
agentblaster providers auth test --provider openai
```

Anthropic API with the default environment-variable reference:

```bash
export ANTHROPIC_API_KEY=...
agentblaster providers add-preset --preset anthropic
agentblaster providers auth test --provider anthropic
```

Use a workspace-specific environment variable:

```bash
agentblaster providers add-preset --preset openai --name openai-workspace --api-key-env WORKSPACE_OPENAI_KEY
```

Use an enterprise CA bundle while keeping TLS verification enabled:

```bash
agentblaster providers add \
  --name openai-enterprise \
  --contract openai \
  --base-url https://gateway.example.com/v1 \
  --api-key-env OPENAI_API_KEY \
  --ca-bundle /etc/ssl/certs/enterprise-ca.pem \
  --remote
```

Disable TLS verification only for controlled diagnostics and only when policy permits it:

```bash
agentblaster providers add \
  --name lab-gateway \
  --contract openai \
  --base-url https://lab-gateway.example.com/v1 \
  --no-tls-verify \
  --remote
```

Use OS keyring storage instead of an environment variable:

```bash
agentblaster providers add-preset --preset openai
printf '%s' "$OPENAI_API_KEY" | agentblaster providers auth set --provider openai --api-key-stdin
agentblaster providers auth test --provider openai
agentblaster providers auth status --provider openai
```

Keyring support is optional. Install `agentblaster[secrets]` to use the platform credential store, such as Apple Keychain on macOS. Environment-variable references remain portable across macOS, Linux, Windows, and CI systems.

Enterprise policy files can restrict which secret backends are allowed:

```yaml
allowed_secret_ref_kinds:
  - env
  - keyring
require_api_key_for_remote_providers: true
```

Use `require_api_key_for_remote_providers: true` for internet-facing OpenAI-compatible, Anthropic-compatible, or corporate gateway profiles so remote runs cannot dispatch without an explicit credential reference.

Clear auth references without exposing secret material:

```bash
agentblaster providers auth clear --provider openai
agentblaster providers auth clear --provider openai --delete-secret
```

`clear` removes the provider's `api_key_ref` from AgentBlaster config. `--delete-secret` also removes the referenced keyring entry when the reference uses OS keyring storage. Environment-variable secrets cannot be deleted by AgentBlaster; unset them in your shell, CI secret manager, or enterprise credential system.

## Cost Models

Provider cost models are metadata used for dry-run plans and policy ceilings. They do not contain secrets.

```bash
agentblaster providers cost set \
  --provider openai \
  --input-usd-per-1m-tokens 3.0 \
  --output-usd-per-1m-tokens 12.0

agentblaster providers cost show --provider openai
agentblaster providers cost clear --provider openai
```

Optional cache and request prices are also supported:

```bash
agentblaster providers cost set \
  --provider anthropic \
  --input-usd-per-1m-tokens 3.0 \
  --output-usd-per-1m-tokens 15.0 \
  --cached-input-usd-per-1m-tokens 0.3 \
  --cache-write-usd-per-1m-tokens 3.75 \
  --request-usd 0.001
```

Configure cost models for remote providers before enabling `max_estimated_case_cost_usd`, `max_estimated_run_cost_usd`, or `max_estimated_matrix_cost_usd` in policy.

## Rate Limits

Provider rate limits are metadata used to pace requests and enforce provider-specific concurrency ceilings.

```bash
agentblaster providers rate-limits set \
  --provider openai \
  --max-concurrency 2 \
  --requests-per-minute 60

agentblaster providers rate-limits show --provider openai
agentblaster providers rate-limits clear --provider openai
```

`max_concurrency` is checked before dispatch. `requests_per_second` and `requests_per_minute` are used by the runner's request pacer to avoid accidental remote bursts during concurrent benchmark runs. Provider rate limits complement global policy `max_concurrency`; the stricter effective ceiling should be used for corporate gateways and paid APIs.

Add an optional Prometheus metrics endpoint for local engine observability:

```bash
agentblaster providers add-preset --preset afm --metrics-url http://127.0.0.1:9999/metrics
```

Metrics snapshots are documented in [observability.md](observability.md). AgentBlaster rejects credential-bearing metrics URLs and does not send API keys to metrics endpoints.
Non-loopback metrics URLs require `allowed_metrics_url_hosts` in the active policy file before a run will dispatch.

## Declare Local Capabilities

Local OpenAI-compatible engines often vary by version, launch flags, model template, and parser. Keep presets conservative, then declare capabilities once verified:

```bash
agentblaster providers capabilities enable --provider afm --capability streaming
agentblaster providers capabilities enable --provider afm --capability tool_calling
agentblaster providers capabilities enable --provider afm --capability structured_output
agentblaster providers check-suite --provider afm --suite toolcall --strict-unknown
```

If a provider is known not to support a feature, declare the gap explicitly:

```bash
agentblaster providers capabilities disable --provider lm-studio-native --capability trace_replay
```

## Benchmark Readiness Dossiers

Use readiness dossiers before benchmark dispatch to combine provider audit, suite capability compatibility, contract-check planning, and metric coverage into one redacted artifact:

```bash
agentblaster providers readiness \
  --provider afm \
  --suite trace-replay \
  --model mlx-community/Qwen3.6-27B \
  --policy agentblaster.policy.yaml \
  --strict-unknown \
  --output-json reports/afm-trace-readiness.json
```

The command is no-network and exits non-zero on blocking readiness gaps.

## Provider Contract Checks

Use contract checks to inspect or execute a standardized compatibility probe for configured providers. The command defaults to plan-only mode and does not contact the endpoint unless `--execute` is provided.

```bash
agentblaster providers contract-check \
  --provider mock-openai \
  --model agentblaster-mock-qwen3.6-27b-dense \
  --output-json reports/mock-openai-contract-plan.json

agentblaster providers contract-check \
  --provider mock-openai \
  --model agentblaster-mock-qwen3.6-27b-dense \
  --execute \
  --output-json reports/mock-openai-contract-check.json
```

Remote providers are refused during execution unless `--allow-remote` is set. The checks cover model listing, exact chat, streaming text, structured JSON where supported by the contract, and tool calls. Use `--skip-streaming`, `--skip-structured`, or `--skip-tools` when calibrating providers with partial support.

## Provider Audit

Audit configured providers without contacting endpoints or resolving secrets:

```bash
agentblaster providers audit --policy agentblaster.policy.yaml --output-json reports/provider-audit.json
```

The audit output is redacted. It reports provider names, contracts, endpoint hosts, remote flags, secret reference backend kind, TLS state, cost/rate-limit configuration state, declared capabilities, policy violations, and review warnings. It does not print raw API-key environment variable names, keyring entry names, secret values, headers, raw provider payloads, or run artifacts.

Use this before running remote matrices to confirm every provider has an approved auth backend, cost model, rate limits, TLS posture, and policy-compatible endpoint host.

## Deterministic Mock Provider

AgentBlaster includes a local mock provider for SDLC tests, adapter development, dashboard launch checks, and Chrome/Codex GUI validation. It uses only stdlib HTTP serving and never calls a model or remote API.

Start it on loopback:

```bash
agentblaster mock-provider --host 127.0.0.1 --port 8787
```

Use it as an OpenAI Chat Completions provider:

```bash
agentblaster providers add \
  --name mock-openai \
  --contract openai \
  --base-url http://127.0.0.1:8787/v1

agentblaster run --suite smoke --engine mock-openai --model agentblaster-mock-qwen3.6-27b-dense --offline
```

The same server also serves `/v1/responses`, `/v1/messages`, `/v1/models`, and `/metrics` so contract tests can exercise OpenAI Responses, Anthropic Messages, probe behavior, streaming events, tool calls, JSON mode, auth-denial paths, and Prometheus scraping without storing secrets.

## Security Rules

- Provider config files store `api_key_ref`, never raw API keys.
- Provider cost models store prices only; they never store API keys, billing account IDs, or provider invoices.
- Provider rate limits store request pacing and concurrency metadata only.
- Enterprise policy can restrict auth references to approved secret backends and require `api_key_ref` on remote providers.
- Raw auth headers are rejected in provider headers.
- TLS certificate verification is enabled by default.
- Custom CA bundles are supported through `--ca-bundle`.
- Insecure TLS requires `--no-tls-verify` on the provider and `allow_insecure_tls: true` in policy before runs dispatch.
- `providers auth status` and `providers auth test` report only whether a reference resolves; they never print API-key values.
- `providers auth clear --delete-secret` deletes only OS-keyring entries and refuses to modify environment variables.
- Cloud presets are marked `remote=true` so `--offline` and enterprise policy files can block them.
- The Anthropic preset includes the API version header as non-secret metadata.
- Full raw traces are blocked unless policy explicitly allows them.

## Example Remote Runs

```bash
agentblaster run --suite smoke --engine openai --model <openai-model> --no-raw-traces
agentblaster run --suite trace-replay --engine openai-responses --model <openai-model> --no-raw-traces
agentblaster run --suite trace-replay --engine anthropic --model <anthropic-model> --no-raw-traces
```

Use `--offline` for local-only comparison runs:

```bash
agentblaster run --suite smoke --engine afm --model mlx-community/Qwen3.6-27B --offline
```
