# AgentBlaster Audit Logging

AgentBlaster uses structured JSONL audit logs for security-relevant control-plane and benchmark execution events. Audit logging is opt-in per command through `--audit-log`.

## Commands

Benchmark runs:

```bash
agentblaster run \
  --suite smoke \
  --engine openai \
  --model <model> \
  --no-raw-traces \
  --audit-log runs/audit.jsonl
```

Provider configuration:

```bash
agentblaster providers add \
  --name openai \
  --contract openai \
  --base-url https://api.openai.com/v1 \
  --api-key-env OPENAI_API_KEY \
  --remote \
  --audit-log audit/control-plane.jsonl
```

Secret reference changes:

```bash
agentblaster providers auth set \
  --provider openai \
  --api-key-env OPENAI_API_KEY \
  --audit-log audit/control-plane.jsonl

agentblaster providers auth clear \
  --provider openai \
  --audit-log audit/control-plane.jsonl
```

Report and export generation:

```bash
agentblaster report runs/<run-id> --format html,json --audit-log audit/control-plane.jsonl
agentblaster export runs/<run-id> --format jsonl,csv --audit-log audit/control-plane.jsonl
agentblaster matrix report reports/qwen-gemma-matrix-summary.json --audit-log audit/control-plane.jsonl
agentblaster cleanup-expired --runs runs --execute --audit-log audit/control-plane.jsonl
agentblaster publication-bundle runs/<run-id> --audit-log audit/control-plane.jsonl
```

Dashboard start:

```bash
agentblaster dashboard \
  --runs runs \
  --host 127.0.0.1 \
  --policy agentblaster.policy.yaml \
  --auth-token-env AGENTBLASTER_DASHBOARD_TOKEN \
  --audit-log audit/control-plane.jsonl
```

## Event Types

- `provider_created` and `provider_updated`: provider profile writes.
- `provider_auth_ref_changed`: provider API-key reference changes.
- `provider_auth_ref_cleared`: provider API-key reference clearing and optional keyring deletion.
- `provider_cost_model_changed`: provider cost model metadata changes.
- `provider_cost_model_cleared`: provider cost model metadata clearing.
- `provider_rate_limits_changed`: provider request pacing or concurrency metadata changes.
- `provider_rate_limits_cleared`: provider request pacing or concurrency metadata clearing.
- `dashboard_started`: dashboard start request with bind host, port, auth state, and non-loopback flag.
- `policy_violation`: dashboard or benchmark execution blocked by policy.
- `report_exported`: report artifact generation.
- `matrix_report_exported`: matrix-level report generation.
- `matrix_policy_evaluation`: aggregate matrix size and case-count policy evaluation before dispatch.
- `results_exported`: normalized result export generation.
- `retention_cleanup_planned` and `retention_cleanup_executed`: retention-based cleanup planning and deletion.
- `publication_bundle_created`: shareable report bundle creation.
- `evidence_bundle_created`: static governance evidence bundle creation.
- Benchmark run events such as `run_started`, `run_completed`, `policy_violation`, and `capability_violation`.
- Release governance events such as `release_provenance_created` and `release_qualification_bundle_created`.

## Security Properties

- Audit logs are JSONL for ingestion into SIEM, CI, or corporate logging systems.
- Secret values are redacted before writing.
- Provider config audit events include secret references such as `env:OPENAI_API_KEY` or `keyring:openai:api_key`, never raw API-key values.
- Provider config audit events include TLS verification state and custom CA bundle path when configured.
- Report/export audit events record generated artifact paths, formats, and source run directories.
- Dashboard audit events record whether dashboard auth is enabled, but never the token or token environment variable value.
