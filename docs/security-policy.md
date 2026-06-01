# Security Policy

AgentBlaster policy files are YAML controls enforced before benchmark dispatch. They are designed for corporate and CI use where benchmark cases, provider configs, and report settings must be reviewable before any request is sent to a local or remote endpoint.


## Policy Validation

Validate and normalize a policy file without launching providers:

```bash
agentblaster policy validate agentblaster.policy.yaml --output-json reports/policy-normalized.json
```

Validation uses the same strict schema as benchmark and dashboard startup. Unknown fields, invalid enum values, and invalid numeric ceilings fail before dispatch.

## Enterprise Baselines And Control Summaries

Generate a strict no-secret enterprise baseline:

```bash
agentblaster policy template --profile local --output agentblaster.policy.yaml
agentblaster policy template --profile remote-gateway --output agentblaster.remote.policy.yaml --output-json reports/enterprise-policy-template.json
```

`local` disables remote providers and is the default for local MLX/desktop benchmark development. `remote-gateway` enables approved remote providers but still requires API-key references, cost models, rate limits, TLS, endpoint allowlists, dashboard auth, cleanup audit logs, bounded tool calls, suite governance, and raw-trace restrictions. The template artifact uses `agentblaster.enterprise-policy-template.v1`, contains only policy controls, and excludes API-key values. Keyring/Apple Keychain remains optional; environment-variable references are the portable enterprise baseline, and plaintext dotenv fallback is intentionally excluded from the generated enterprise baseline.

Summarize a policy for security review:

```bash
agentblaster policy controls agentblaster.policy.yaml --name local-campaign --output-json reports/policy-control-summary.json
```

The summary artifact uses `agentblaster.policy-control-summary.v1`. It does not resolve secret references, read keyrings, inspect dotenv files, contact providers, or launch benchmarks. Unsafe exceptions such as full raw traces, insecure TLS, non-loopback HTTP, plaintext dotenv secret backends, missing dashboard auth, or missing cleanup audit requirements are surfaced as blockers.

## Provider And Endpoint Controls

```yaml
allowed_providers:
  - afm
  - lm-studio
allowed_base_url_hosts:
  - 127.0.0.1
  - localhost
allowed_metrics_url_hosts:
  - 127.0.0.1
  - localhost
allowed_secret_ref_kinds:
  - env
  - keyring
allowed_secret_ref_prefixes:
  - AGENTBLASTER_
  - OPENAI_
  - ANTHROPIC_
  - WORKSPACE_
  - openai
  - anthropic
allow_remote_providers: false
require_api_key_for_remote_providers: true
require_cost_model_for_remote_providers: true
require_rate_limits_for_remote_providers: true
allow_non_loopback_http_provider_urls: false
allow_non_loopback_http_metrics_urls: false
allow_insecure_tls: false
```

Provider controls stop runs when an engine name, API host, metrics host, secret-reference backend, remote-provider flag, remote-auth requirement, remote cost/rate-limit readiness, transport scheme, or TLS setting violates policy. Non-loopback provider API URLs and metrics URLs must use HTTPS by default. Non-loopback HTTP requires an explicit policy exception through `allow_non_loopback_http_provider_urls` or `allow_non_loopback_http_metrics_urls`. Loopback HTTP remains allowed for local engines.

Non-loopback metrics URLs must be explicitly listed even when provider base URLs are otherwise allowed.

`allowed_secret_ref_kinds` can restrict provider auth references to portable environment variables, OS keyring storage, explicit plaintext dotenv fallback, or an approved subset. Corporate policies should normally allow only `env` and/or `keyring`; add `dotenv` only for approved development workspaces where plaintext secret-file storage is acceptable. `allowed_secret_ref_names` and `allowed_secret_ref_prefixes` can further restrict environment-variable names, keyring entry names, or dotenv `VAR@path` references to corporate-approved naming schemes without listing or resolving secret values. Environment-variable references must be valid environment variable names, and dotenv references must use `VAR@path`, which prevents pasted API keys from being persisted as references. `require_api_key_for_remote_providers` blocks internet-facing provider profiles unless they carry an `api_key_ref`; this prevents accidental anonymous or misconfigured corporate gateway runs. `require_cost_model_for_remote_providers` and `require_rate_limits_for_remote_providers` force budget and concurrency metadata to be configured before dispatch to internet-facing or corporate gateway APIs.

Dashboard auth setup also enforces backend separation. Env-mode requests can store only a secret reference name, and raw API-key payloads are rejected unless the operator explicitly selects keyring/Keychain storage or an explicit plaintext dotenv fallback with `allow_plaintext_secret_file`. Plaintext dotenv fallback is warning-gated and policy-controllable. For writable backends such as keyring or dotenv, dashboard auth runs the static policy review before writing raw API-key material; disallowed backends or secret-reference names are rejected without writing the secret. The CLI auth path supports the same pre-write enforcement with `agentblaster providers auth set --policy <policy.yaml>`.

Provider probes and contract checks resolve secrets only at dispatch time. Probe failure messages use redacted response previews so provider-side error bodies cannot echo bearer tokens into CLI output, dashboards, or review artifacts.

## Trace And Cost Controls

```yaml
allow_full_raw_traces: false
max_concurrency: 8
max_cases: 500
max_matrix_runs: 25
max_matrix_total_cases: 2500
max_prompt_tokens: 200000
max_output_tokens: 4096
max_timeout_seconds: 600
max_estimated_case_cost_usd: 1.0
max_estimated_run_cost_usd: 25.0
max_estimated_matrix_cost_usd: 100.0
```

Raw trace and ceiling controls are enforced during run planning. `max_cases` applies to a single suite run. `max_matrix_runs` and `max_matrix_total_cases` apply to an executed matrix before provider dispatch, which prevents accidental large cross-provider or cross-model API runs. Cost ceilings require a provider `cost_model` so a remote API run cannot be dispatched without an explicit cost basis. Configure cost models with `agentblaster providers cost set`. `max_estimated_matrix_cost_usd` sums all matrix entries before dispatch and blocks the whole matrix if the aggregate estimate exceeds policy.

Provider-specific request pacing can be configured with `agentblaster providers rate-limits set`. Policy `max_concurrency` applies globally, while provider `max_concurrency` and request-per-second/minute metadata protect individual APIs or corporate gateways from accidental bursts.

## Suite Capability Controls

```yaml
allow_tool_schemas: true
allowed_tool_names:
  - search_docs
allow_simulated_tools: true
allowed_simulated_tools:
  - search_docs
  - read_file_fixture
allow_mcp_profiles: true
allowed_mcp_profiles:
  - fixture-mcp
allow_lcp_profiles: true
allowed_lcp_profiles:
  - fixture-lcp
allow_skills: true
allowed_skills:
  - safe-tool-replay
require_max_tool_calls_for_tool_cases: true
max_tool_calls_per_case: 8
allowed_case_provenance:
  - synthetic_representative
  - internal_regression
  - customer_trace_sanitized
  - primary_source
  - public_benchmark_adapted
allowed_case_risk_levels:
  - low
  - medium
allow_high_risk_cases: false
require_source_url_for_external_cases: true
require_license_for_external_cases: true
```

Capability controls gate benchmark-supplied prompt and tool surfaces before provider dispatch:

- `allow_tool_schemas` controls explicit OpenAI/Anthropic tool schemas embedded in suite cases.
- `allowed_tool_names` optionally restricts explicit tool schemas by function name.
- `allow_simulated_tools` controls deterministic harness tools executed by AgentBlaster fixtures.
- `allowed_simulated_tools` restricts those fixture tools by name.
- `allow_mcp_profiles` controls deterministic MCP-style profile injection.
- `allowed_mcp_profiles` restricts the permitted MCP fixture catalogs.
- `allow_lcp_profiles` controls deterministic LCP-style context bundle injection.
- `allowed_lcp_profiles` restricts the permitted LCP context fixtures.
- `allow_skills` controls benchmark skill-pack prompt injection.
- `allowed_skills` restricts the permitted skill packs.
- `require_max_tool_calls_for_tool_cases` requires every case with explicit tool schemas, simulated tools, or MCP profiles to declare `max_tool_calls`.
- `max_tool_calls_per_case` caps declared tool-call loop depth before dispatch.

Current simulated tools, MCP profiles, and LCP profiles are deterministic fixtures, not arbitrary host execution. These controls still matter because tool descriptions, skill text, MCP catalogs, and LCP context bundles can change prompt shape, cache behavior, and injection risk.

Use `agentblaster catalog simulated-tools`, `agentblaster catalog mcp-profiles`, `agentblaster catalog lcp-profiles`, and `agentblaster catalog skills` to produce reviewable inventories before approving allowlists. The catalog commands do not execute tools or contact providers.

Use `agentblaster suite-audit` to review a suite's provenance, risk labels, source/license metadata, and requested capability surfaces before approving a policy exception.

Governance controls can also be enforced at dispatch time. `allowed_case_provenance` and `allowed_case_risk_levels` restrict case metadata, `allow_high_risk_cases` can block high-risk fixtures, and `require_source_url_for_external_cases` plus `require_license_for_external_cases` require review metadata for `primary_source` and `public_benchmark_adapted` cases.

## Dashboard Controls

```yaml
allowed_dashboard_hosts:
  - 127.0.0.1
  - localhost
allowed_dashboard_ports:
  - 8765
allow_dashboard_non_loopback: false
require_dashboard_auth: true
```

Dashboard controls prevent accidental exposure of local run data. Non-loopback dashboard binding requires both policy permission and an explicit CLI opt-in.

Dashboard provider setup, provider auth, run-plan, and launch endpoints inherit the policy supplied to `agentblaster dashboard --policy`. Provider setup/auth responses include static `policy_review` metadata so operators can see launch blockers before dispatch. The per-request `allow_remote` checkbox only permits remote dispatch when the configured policy also allows remote providers and the provider satisfies the same secret-reference, host, TLS, cost, rate-limit, trace, concurrency, and suite controls used by CLI runs.

## Recommended Enterprise Defaults

Use `agentblaster providers audit --policy agentblaster.policy.yaml` to review configured providers against policy without resolving secrets or contacting endpoints.

Provider audit JSON uses `agentblaster.provider-audit.v1`. It is intended as a direct corporate-security artifact for endpoint, TLS, remote-provider, cost/rate-limit, capability, and redacted auth-posture review. It reports secret-reference backend kind, static `secret_backend_posture`, optional keyring dependency availability, and per-provider keyring requirement metadata only; raw secret names, API-key values, dotenv paths, environment-variable values, and keyring contents are excluded.

Use `require_cleanup_audit_log: true` to make `agentblaster cleanup` and `agentblaster cleanup-expired` fail closed unless `--audit-log` is supplied. This policy applies to dry-run cleanup planning and executed deletion, and cleanup reports record whether audit logging was required. Provider audit, dashboard setup-status, and environment readiness reports include the cleanup-audit policy posture so reviewers can confirm the control before cleanup commands run.

Use `agentblaster doctor --policy agentblaster.policy.yaml --output-json reports/environment-readiness.json` to capture static runtime readiness before provider setup. The doctor report records redacted boolean policy controls and does not contact providers, resolve API keys, inspect keyring values, read dotenv secret files, or read provider config contents.

Use `agentblaster.policy.example.yaml` as the starting point for local-only development. For CI or corporate runs, keep remote providers disabled unless the provider, host, API-key reference kind, cost model, and retention policy have been reviewed. Keep full raw traces disabled unless the run is classified, retained, and shared according to internal data-handling rules.

## Remote Provider Onboarding

Use `agentblaster providers onboarding` before configuring internet-facing OpenAI-compatible or Anthropic-compatible providers. The generated artifact is static and redaction-safe, lists the required secret reference, cost model, rate limits, audit, readiness, and contract-check commands expected before benchmark dispatch, and includes machine-readable `secret_backend` plus `policy_prerequisites` sections for corporate review. Dotenv secret-reference summaries redact the path while the setup command keeps the operator-supplied file argument. Keyring/Apple Keychain support remains optional; environment-variable references are the portable baseline, and dotenv is documented as a plaintext local-development fallback only.
