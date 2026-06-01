# AgentBlaster Providers

Provider profiles describe inference endpoints without storing raw API keys. Profiles can target local MLX engines, local OpenAI-compatible servers, internet-facing OpenAI-compatible APIs, Anthropic-compatible APIs, or engine-native APIs.

## Built-In Presets

List built-in presets:

```bash
agentblaster providers presets
```

Generate a local-engine onboarding checklist that joins local presets, declared preflight capabilities, launch recipes, post-launch checks, Qwen/Gemma model targets, and campaign starter artifacts:

```bash
agentblaster engines onboarding --format markdown --output reports/local-engine-onboarding.md
```

Local presets:

- `afm`
- `mlx-lm`
- `ollama`
- `ollama-native`
- `lm-studio`
- `lm-studio-responses`
- `lm-studio-anthropic`
- `lm-studio-native`
- `omlx`
- `rapid-mlx`
- `vllm-mlx`
- `vllm-mlx-anthropic`

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

The onboarding command does not store secrets, modify provider config, contact endpoints, or write keyring/dotenv entries. It produces reviewable commands for secret preparation, provider registration, auth status/test, cost model setup, rate limits, provider audit, readiness, contract-check planning, and a policy-backed no-raw-traces smoke run. Generated JSON includes `secret_backend` and `policy_prerequisites` sections so reviewers can confirm that provider config stores references only, environment-variable mode is portable, keyring/Apple Keychain is optional, dotenv is an explicit plaintext fallback, and remote dispatch requires approved hosts, auth references, cost models, rate limits, TLS, and disabled full raw traces. Displayed dotenv secret references are path-redacted in the provider summary while the command block still shows the operator-supplied dotenv file argument needed to execute setup. Generated keyring and dotenv auth setup commands include `--policy` so writable secret storage is blocked before persistence when enterprise policy disallows the backend or reference. Use onboarding as the first artifact in corporate approvals for remote OpenAI-compatible and Anthropic-compatible providers.

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

Keyring support is optional. Install `agentblaster[secrets]` to use the platform credential store, such as Apple Keychain on macOS. Environment-variable references remain portable across macOS, Linux, Windows, and CI systems. Provider audits expose a redaction-safe `secret_backend_posture` block with static keyring dependency availability and per-provider keyring requirement metadata; this does not read keyring entries or secret values.

For local development only, AgentBlaster can write an explicit plaintext `.env` fallback when OS keyring support is unavailable:

```bash
printf '%s\n' "$OPENAI_API_KEY" | agentblaster providers auth set \
  --provider openai \
  --api-key-dotenv-file .agentblaster.local.env \
  --policy agentblaster.policy.yaml \
  --allow-plaintext-secret-file
```

This stores `api_key_ref` as `dotenv:VAR@path` in the local provider config and writes the secret value to the named `.env` file. CLI, dashboard, and audit-log response surfaces redact the path as `dotenv:VAR@<redacted-path>` and set path-redaction metadata where structured output is emitted. The high-friction `--allow-plaintext-secret-file` flag is required every time plaintext storage is requested. When `--policy` is supplied, the CLI checks the proposed provider profile before writing to keyring or dotenv storage, so disallowed secret backends or reference names are blocked without persisting the API key. Do not use this mode for CI, corporate benchmark evidence, shared machines, or publication runs unless policy explicitly approves it.

Dashboard provider auth follows the same separation: environment mode accepts only an environment-variable reference, while raw API-key entry is accepted only for the optional keyring/Keychain backend or an explicit plaintext dotenv fallback request with `allow_plaintext_secret_file`. If an env-mode dashboard request includes raw API-key material, AgentBlaster rejects the request instead of ignoring or echoing the key. `/api/setup-status` includes a redacted `auth_setup` posture block for env, keyring, and dotenv methods, including availability, policy allowance, raw-key-entry behavior, plaintext fallback status, and enterprise recommendation without reading secret values. When the dashboard is started with `--policy`, provider setup/auth responses include static `policy_review` metadata without contacting endpoints or resolving secret values. Writable dashboard auth backends run that policy review before writing raw API-key material, so a policy-disallowed keyring/dotenv backend or secret-reference name is blocked without persisting the secret.

Enterprise policy files can restrict which secret backends are allowed:

```yaml
allowed_secret_ref_kinds:
  - env
  - keyring
allowed_secret_ref_prefixes:
  - AGENTBLASTER_
  - WORKSPACE_
require_api_key_for_remote_providers: true
```

Use `require_api_key_for_remote_providers: true` for internet-facing OpenAI-compatible, Anthropic-compatible, or corporate gateway profiles so remote runs cannot dispatch without an explicit credential reference. Use `allowed_secret_ref_names` or `allowed_secret_ref_prefixes` when a corporate policy requires credentials to come from approved CI variables or managed keyring entry names. Add `dotenv` to `allowed_secret_ref_kinds` only for approved development workspaces where plaintext `.env` fallback is acceptable.

Clear auth references without exposing secret material:

```bash
agentblaster providers auth clear --provider openai
agentblaster providers auth clear --provider openai --delete-secret
```

`clear` removes the provider's `api_key_ref` from AgentBlaster config. `--delete-secret` also removes the referenced keyring entry or dotenv variable when the reference uses a writable backend. Environment-variable secrets cannot be deleted by AgentBlaster; unset them in your shell, CI secret manager, or enterprise credential system.

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

The command is no-network and exits non-zero on blocking readiness gaps. The readiness dossier includes the contract plan's capability evidence, separating direct probes, proxy evidence such as `judge_rubric` through `structured_output`, and capabilities that need separate benchmark evidence such as Anthropic prompt caching.

Readiness dossiers also carry a compact `provider_auth_posture` section from provider audit evidence. It is redaction-safe and shows secret-reference kind, configured state, writable backend status, plaintext dotenv fallback status, and whether pre-write policy guarding is recommended before storing API-key material.

Add readiness dossiers to release packages with `agentblaster release qualification-bundle --benchmark-readiness reports/<provider>-<suite>-readiness.json` and to claim gates with `agentblaster release claim-readiness --benchmark-readiness reports/<provider>-<suite>-readiness.json`. For generated campaigns, reuse `reports/benchmark-readiness-inputs.txt` with `--benchmark-readiness-list` across campaign preflight, release qualification, and claim readiness; list files use one raw path per line, ignore blank/comment lines, and resolve relative paths from the list file directory. Evidence indexes and dashboard review artifacts expose them as compact `benchmark_readiness_summaries` for operator review.

`agentblaster providers audit --output-json reports/provider-audit.json` writes `agentblaster.provider-audit.v1`, a direct corporate-security review artifact. It is static and does not contact endpoints, resolve API keys, read environment variables, inspect keyring values, or read dotenv secret files. Secret references are summarized by backend kind and booleans only, and writable keyring/dotenv backends are flagged so reviewers can confirm policy-guarded auth setup was used before any API-key material was stored.

## Response Stats Normalization

Different engines expose stats through incompatible fields. Use sample normalization to check mappings before using a metric in reports:

```bash
agentblaster catalog normalize-telemetry \
  samples/provider-response.json \
  --contract openai \
  --output-json reports/provider-normalized-telemetry.json
```

For native endpoints, pass the native adapter hint:

```bash
agentblaster catalog normalize-telemetry \
  samples/ollama-response.json \
  --contract native \
  --native-adapter ollama
```

The command is no-network and does not resolve secrets. Prefer minimized response samples containing only `usage`, `stats`, `metrics`, or timing fields.

Normalized telemetry includes field-level `quality` and `comparison_readiness` metadata. Use that metadata to label native/measured fields separately from inferred or conditional throughput/cache metrics before making cross-engine claims.

## Provider Contract Checks

Use contract checks to inspect or execute a standardized compatibility probe for configured providers. The command defaults to plan-only mode and does not contact the endpoint unless `--execute` is provided.
The same contract-check engine covers OpenAI Chat Completions, OpenAI Responses, and Anthropic Messages providers, plus supported native adapters where separate native checks are added. Executed checks use the configured adapter path, including custom clients in tests and controlled harnesses, so mock-provider results exercise the same adapter factory used by benchmark runs.

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

Contract-check reports include a `contract_surface` block with schema `agentblaster.provider-contract-surface.v1`. It records the standardized adapter family, HTTP JSON transport, redaction-safe auth scheme and header names, canonical endpoint paths, request features, and response evidence fields used by the probes. This makes OpenAI Chat Completions, OpenAI Responses, and Anthropic Messages compatibility claims reviewable without copying raw provider payloads or secrets.

Contract-check reports also include a `capability_evidence` block. `directly_checked` lists capabilities with explicit probes, `proxy_checked` lists capabilities such as `judge_rubric` that are covered through structured-output verdict JSON probes, and `not_covered` lists declared capabilities that still need separate benchmark evidence. Anthropic prompt caching is intentionally reported as not covered by contract checks; use the `cache-control` suite and normalized cache token metrics to prove cache-control behavior.

Executed contract-check artifacts emit `agentblaster.provider-contract-check.v1` with top-level `ok: true` only when every planned check passes. Plan-only artifacts keep `ok: false`; they are acceptable for preflight review but not sufficient for release claim readiness. Add executed contract checks to release packages with `agentblaster release qualification-bundle --provider-contract-check ...` and to publication gates with `agentblaster release claim-readiness --provider-contract-check ...`.

For matrix campaigns, generate one artifact across every unique provider/model target referenced by the matrix:

```bash
agentblaster matrix contract-checks \
  examples/matrices/qwen-gemma-local.yaml \
  --output-json reports/qwen-gemma-contract-matrix-plan.json

agentblaster matrix contract-checks \
  examples/matrices/qwen-gemma-local.yaml \
  --execute \
  --output-json reports/qwen-gemma-provider-contract-matrix.json
```

The matrix command deduplicates repeated provider/model entries across suites and concurrency levels. Executed matrix artifacts emit `agentblaster.provider-contract-matrix.v1` with top-level `ok: true` only when every target passes. Matrix artifacts include top-level `contract_surfaces` plus per-entry `contract_surface` blocks so mixed OpenAI/Responses/Anthropic campaigns remain auditable. Use `--provider-contract-matrix` in release qualification and claim-readiness commands when one matrix-level artifact should cover the whole campaign.

Remote providers are refused during execution unless `--allow-remote` is set. The checks cover model listing, exact chat, streaming text, structured JSON where supported by the contract, tool calls, and OpenAI Responses stateful continuation with `previous_response_id` plus `max_tool_calls`. Use `--skip-streaming`, `--skip-structured`, or `--skip-tools` when calibrating providers with partial support; `--skip-tools` also suppresses the Responses stateful check because it sends `max_tool_calls`.

Adapters preserve provider-native JSON bodies for telemetry normalization and add a safe `agentblaster_http` metadata block with status, content type, request IDs, and rate-limit headers when present. Non-JSON provider responses are represented with a redacted short body preview instead of raw headers or full payloads, which keeps contract diagnostics useful without storing authorization headers, cookies, or raw API keys.

## Provider Audit

Audit configured providers without contacting endpoints or resolving secrets:

```bash
agentblaster providers audit --policy agentblaster.policy.yaml --output-json reports/provider-audit.json
```

The audit output is redacted. It reports provider names, contracts, endpoint hosts, remote flags, secret reference backend kind, whether the backend is writable, whether it is plaintext dotenv fallback, TLS state, cost/rate-limit configuration state, declared capabilities, policy violations, and review warnings. It does not print raw API-key environment variable names, keyring entry names, secret values, headers, raw provider payloads, or run artifacts.

Use this before running remote matrices to confirm every provider has an approved auth backend, approved secret reference name, cost model, rate limits, TLS posture, and policy-compatible endpoint host.

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
- Environment-variable secret references must be valid environment variable names, which prevents pasted raw API keys from being saved as reference names.
- Plaintext dotenv fallback is explicit, single-line only, emits warning/audit metadata, and should be disabled by corporate policy unless specifically approved for local development.
- Enterprise policy can restrict auth references to approved secret backends, exact reference names, or reference-name prefixes, and can require `api_key_ref` on remote providers.
- Raw auth headers are rejected in provider headers.
- TLS certificate verification is enabled by default.
- Custom CA bundles are supported through `--ca-bundle`.
- Insecure TLS requires `--no-tls-verify` on the provider and `allow_insecure_tls: true` in policy before runs dispatch.
- `providers auth status` and `providers auth test` report only whether a reference resolves; they never print API-key values, and dotenv reference paths are redacted in CLI/dashboard/audit output.
- Provider probes redact error-body previews before printing failure messages, so an upstream service that echoes an `Authorization` bearer value does not copy it into probe output.
- `providers auth clear --delete-secret` deletes only writable keyring/dotenv entries and refuses to modify environment variables.
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
