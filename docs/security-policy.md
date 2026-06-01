# Security Policy

AgentBlaster policy files are YAML controls enforced before benchmark dispatch. They are designed for corporate and CI use where benchmark cases, provider configs, and report settings must be reviewable before any request is sent to a local or remote endpoint.


## Policy Validation

Validate and normalize a policy file without launching providers:

```bash
agentblaster policy validate agentblaster.policy.yaml --output-json reports/policy-normalized.json
```

Validation uses the same strict schema as benchmark and dashboard startup. Unknown fields, invalid enum values, and invalid numeric ceilings fail before dispatch.

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
allow_remote_providers: false
require_api_key_for_remote_providers: true
allow_insecure_tls: false
```

Provider controls stop runs when an engine name, API host, metrics host, secret-reference backend, remote-provider flag, remote-auth requirement, or TLS setting violates policy. Non-loopback metrics URLs must be explicitly listed even when provider base URLs are otherwise allowed.

`allowed_secret_ref_kinds` can restrict provider auth references to portable environment variables, OS keyring storage, or both. `require_api_key_for_remote_providers` blocks internet-facing provider profiles unless they carry an `api_key_ref`; this prevents accidental anonymous or misconfigured corporate gateway runs.

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

Current simulated tools and MCP profiles are deterministic fixtures, not arbitrary host execution. These controls still matter because tool descriptions, skill text, and MCP catalogs can change prompt shape, cache behavior, and injection risk.

Use `agentblaster catalog simulated-tools`, `agentblaster catalog mcp-profiles`, and `agentblaster catalog skills` to produce reviewable inventories before approving allowlists. The catalog commands do not execute tools or contact providers.

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

## Recommended Enterprise Defaults

Use `agentblaster providers audit --policy agentblaster.policy.yaml` to review configured providers against policy without resolving secrets or contacting endpoints.

Use `agentblaster.policy.example.yaml` as the starting point for local-only development. For CI or corporate runs, keep remote providers disabled unless the provider, host, API-key reference kind, cost model, and retention policy have been reviewed. Keep full raw traces disabled unless the run is classified, retained, and shared according to internal data-handling rules.

## Remote Provider Onboarding

Use `agentblaster providers onboarding` before configuring internet-facing OpenAI-compatible or Anthropic-compatible providers. The generated artifact is static and redaction-safe, and it lists the required secret reference, cost model, rate limits, audit, readiness, and contract-check commands expected before benchmark dispatch.
